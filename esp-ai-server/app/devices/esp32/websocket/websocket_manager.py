"""
ESP32 WebSocket连接管理器
ESP32 WebSocket Connection Manager
参考core/websocket_server.py的设计，为ESP32设备提供专用的WebSocket连接管理
"""

import asyncio
import json
import time
import logging
import uuid
import websockets
from typing import Dict, Optional, Set, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from .message_router import ESP32MessageRouter
from .types import ESP32DeviceInfo, ConnectionState, ConnectionStats
from app.core import settings
from app.core.device_logger import (
    log_esp32_connection, 
    log_esp32_protocol, 
    log_esp32_service,
    log_esp32_error,
    log_esp32_performance,
    get_esp32_stats,
    esp32_logger
)
from app.shared.services.llm_service import get_llm_service
from app.shared.services.chat_history_service import get_chat_history_service
from app.devices.esp32.services import (
    get_esp32_asr_integration,
    get_esp32_tts_integration,
    get_esp32_intent_processor,
    get_esp32_speech_coordinator
)



class ESP32WebSocketManager:
    """ESP32 WebSocket连接管理器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.logger = logging.getLogger(__name__)
        self.config = config or self._get_default_config()
        
        # 连接管理
        self.active_connections: Dict[str, 'ESP32ConnectionHandler'] = {}
        self.device_connections: Dict[str, str] = {}  # device_id -> connection_id
        self.connection_states: Dict[str, ConnectionState] = {}
        
        # 统计信息
        self.stats = ConnectionStats()
        
        # 服务组件 (延迟初始化)
        self.llm_service = None
        self.chat_history_service = None
        
        # 线程池
        self.executor = ThreadPoolExecutor(
            max_workers=self.config.get("max_workers", 10),
            thread_name_prefix="ESP32WebSocket"
        )
        
        # 认证配置
        self.auth_enabled = self.config.get("auth", {}).get("enabled", False)
        self.device_whitelist = set(self.config.get("auth", {}).get("device_whitelist", []))
        self.jwt_secret = self.config.get("auth", {}).get("jwt_secret", "")
        
        # 连接限制
        self.max_connections = self.config.get("max_connections", 1000)
        self.connection_timeout = self.config.get("connection_timeout", 300)
        self.heartbeat_interval = self.config.get("heartbeat_interval", 30)
        
        # 启动后台任务
        self._background_tasks: Set[asyncio.Task] = set()
        
        self.logger.info(f"ESP32WebSocket管理器初始化完成，最大连接数: {self.max_connections}")
    
    async def _ensure_services_initialized(self):
        """确保服务已初始化"""
        if self.llm_service is None:
            try:
                from app.core.application import get_app
                try:
                    app = get_app()
                    self.llm_service = await app.get_llm_service('esp32')
                except RuntimeError:
                    # 应用未初始化，降级到同步方式
                    self.llm_service = get_llm_service()
            except Exception as e:
                self.logger.warning(f"LLM服务初始化失败，将在需要时重试: {e}")
        
        if self.chat_history_service is None:
            try:
                self.chat_history_service = get_chat_history_service()
            except Exception as e:
                self.logger.warning(f"聊天历史服务初始化失败，将在需要时重试: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "max_connections": 1000,
            "connection_timeout": 300,
            "heartbeat_interval": 30,
            "max_workers": 10,
            "auth": {
                "enabled": False,
                "device_whitelist": [],
                "jwt_secret": ""
            },
            "message": {
                "max_size": 1048576,  # 1MB
                "queue_size": 1000,
                "processing_timeout": 30
            }
        }
    
    async def start_server(self, host: str = "0.0.0.0", port: int = 8766):
        """启动WebSocket服务器"""
        try:
            self.logger.info(f"🚀 启动ESP32 WebSocket服务器: {host}:{port}")
            self.logger.info("🎯 模块化功能: 协议处理、消息路由、会话管理、音频处理")
            
            # 初始化服务
            await self._ensure_services_initialized()
            
            # 启动后台任务
            await self._start_background_tasks()
            
            # 启动WebSocket服务器
            async with websockets.serve(
                self._handle_connection,
                host,
                port,
                process_request=self._process_http_request,
                max_size=self.config.get("message", {}).get("max_size", 1048576),
                ping_interval=self.heartbeat_interval,
                ping_timeout=self.heartbeat_interval * 2
            ):
                self.logger.info(f"✅ ESP32 WebSocket服务器已启动在 {host}:{port}")
                self.logger.info("🔍 等待ESP32设备连接...")
                await asyncio.Future()  # 保持服务器运行
                
        except Exception as e:
            self.logger.error(f"❌ 启动WebSocket服务器失败: {e}")
            raise
    
    async def _start_background_tasks(self):
        """启动后台任务"""
        # 连接清理任务
        cleanup_task = asyncio.create_task(self._connection_cleanup_task())
        self._background_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(self._background_tasks.discard)
        
        # 统计更新任务
        stats_task = asyncio.create_task(self._stats_update_task())
        self._background_tasks.add(stats_task)
        stats_task.add_done_callback(self._background_tasks.discard)
        
        # 心跳检测任务
        heartbeat_task = asyncio.create_task(self._heartbeat_task())
        self._background_tasks.add(heartbeat_task)
        heartbeat_task.add_done_callback(self._background_tasks.discard)
        
        self.logger.info("后台任务已启动")
    
    async def _process_http_request(self, websocket, request_headers):
        """处理HTTP请求"""
        if request_headers.headers.get("connection", "").lower() == "upgrade":
            return None  # WebSocket升级请求
        else:
            return websocket.respond(200, "ESP32 WebSocket Server is running\n")
    
    async def _handle_connection(self, websocket):
        """处理新的WebSocket连接"""
        connection_id = str(uuid.uuid4())
        device_info = None
        
        try:
            # 使用设备日志系统记录连接信息
            client_addr = websocket.remote_address
            client_ip = client_addr[0] if client_addr else 'unknown'
            
            # 记录连接尝试
            log_esp32_connection("unknown", "连接尝试", {
                "client_ip": client_ip,
                "client_port": client_addr[1] if client_addr else 0,
                "connection_time": datetime.now().isoformat(),
                "connection_id": connection_id
            })
            
            # 检查连接数限制
            if len(self.active_connections) >= self.max_connections:
                log_esp32_connection("unknown", "连接失败", {
                    "reason": "连接数已达上限",
                    "current_connections": len(self.active_connections),
                    "max_connections": self.max_connections,
                    "client_ip": client_ip
                })
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "服务器连接数已达上限"
                }))
                await websocket.close()
                return
            
            log_esp32_service("连接管理", "连接池检查通过", {
                "current_connections": len(self.active_connections),
                "max_connections": self.max_connections
            })
            
            # 提取设备信息
            device_info = await self._extract_device_info(websocket)
            if not device_info:
                log_esp32_error("unknown", "设备信息提取失败", "无效的Hello消息格式", {
                    "client_ip": client_ip,
                    "connection_id": connection_id
                })
                await websocket.send(json.dumps({
                    "type": "error", 
                    "message": "无效的设备信息"
                }))
                await websocket.close()
                return
            
            # 记录设备信息提取成功
            log_esp32_connection(device_info.device_id, "设备信息提取成功", {
                "client_ip": client_ip,
                "protocol_version": device_info.protocol_version,
                "features": device_info.features,
                "audio_params": device_info.audio_params
            })
            
            # 认证检查
            if not await self._authenticate_device(websocket, device_info):
                log_esp32_error(device_info.device_id, "认证失败", "设备认证检查未通过", {
                    "client_ip": client_ip,
                    "device_id": device_info.device_id
                })
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "设备认证失败"
                }))
                await websocket.close()
                return
            
            # 创建连接处理器
            from .connection_handler import ESP32ConnectionHandler
            
            handler = ESP32ConnectionHandler(
                connection_id=connection_id,
                websocket=websocket,
                device_info=device_info,
                manager=self
            )
            
            # 注册连接
            await self._register_connection(connection_id, handler, device_info)
            
            # 记录连接建立成功
            log_esp32_connection(device_info.device_id, "连接建立", {
                "client_ip": client_ip,
                "connection_id": connection_id,
                "protocol_version": device_info.protocol_version,
                "features": list(device_info.features.keys()) if device_info.features else []
            })
            
            # 处理连接
            log_esp32_service("连接管理", "开始处理连接", {
                "device_id": device_info.device_id,
                "connection_id": connection_id
            })
            await handler.handle_connection()
            
        except websockets.exceptions.ConnectionClosed:
            device_id = device_info.device_id if device_info else 'unknown'
            log_esp32_connection(device_id, "连接断开", {
                "reason": "客户端主动断开",
                "connection_id": connection_id
            })
        except Exception as e:
            device_id = device_info.device_id if device_info else 'unknown'
            log_esp32_error(device_id, "连接错误", f"处理连接时出错: {e}", {
                "connection_id": connection_id,
                "error_type": type(e).__name__
            })
            self.stats.failed_connections += 1
        finally:
            # 清理连接
            await self._unregister_connection(connection_id)
    
    async def _extract_device_info(self, websocket) -> Optional[ESP32DeviceInfo]:
        """提取设备信息"""
        try:
            headers = dict(websocket.request.headers)
            
            # 获取设备ID
            device_id = headers.get("device-id")
            if not device_id:
                # 尝试从URL参数获取
                from urllib.parse import parse_qs, urlparse
                parsed_url = urlparse(websocket.request.path)
                query_params = parse_qs(parsed_url.query)
                device_id = query_params.get("device-id", [None])[0]
            
            # ESP32设备通常不在HTTP头中发送device-id，而是在Hello消息中发送
            # 为了兼容ESP32，我们创建一个临时的设备信息，真正的设备ID会在Hello消息处理时更新
            if not device_id:
                # 生成临时设备ID，将在Hello消息处理时替换
                import uuid
                device_id = f"temp_{uuid.uuid4().hex[:8]}"
                self.logger.debug(f"ESP32设备未在头部提供device_id，使用临时ID: {device_id}")
            
            # 创建设备信息
            device_info = ESP32DeviceInfo(
                device_id=device_id,
                client_id=headers.get("client-id"),
                client_ip=self._get_client_ip(websocket),
                user_agent=headers.get("user-agent", ""),
                protocol_version=headers.get("protocol-version", "1.0")
            )
            
            # 解析features
            features_header = headers.get("features")
            if features_header:
                try:
                    device_info.features = json.loads(features_header)
                except json.JSONDecodeError:
                    pass
            
            return device_info
            
        except Exception as e:
            self.logger.error(f"提取设备信息失败: {e}")
            return None
    
    def _get_client_ip(self, websocket) -> str:
        """获取客户端IP"""
        headers = dict(websocket.request.headers)
        
        # 优先使用代理头
        real_ip = headers.get("x-real-ip") or headers.get("x-forwarded-for")
        if real_ip:
            return real_ip.split(",")[0].strip()
        
        # 使用WebSocket远程地址
        if hasattr(websocket, 'remote_address') and websocket.remote_address:
            return websocket.remote_address[0]
        
        return "unknown"
    
    async def _authenticate_device(self, websocket, device_info: ESP32DeviceInfo) -> bool:
        """设备认证"""
        if not self.auth_enabled:
            return True
        
        try:
            # 检查设备白名单
            if self.device_whitelist and device_info.device_id in self.device_whitelist:
                self.logger.info(f"设备 {device_info.device_id} 在白名单中，跳过token验证")
                return True
            
            # JWT token验证
            headers = dict(websocket.request.headers)
            auth_header = headers.get("authorization", "")
            
            if not auth_header.startswith("Bearer "):
                return False
            
            token = auth_header[7:]  # 移除 "Bearer " 前缀
            
            # 这里应该实现JWT验证逻辑
            # 暂时返回True，实际项目中需要实现完整的JWT验证
            return True
            
        except Exception as e:
            self.logger.error(f"设备认证失败: {e}")
            return False
    
    async def _register_connection(self, connection_id: str, handler: 'ESP32ConnectionHandler', device_info: ESP32DeviceInfo):
        """注册连接"""
        self.active_connections[connection_id] = handler
        self.device_connections[device_info.device_id] = connection_id
        self.connection_states[connection_id] = ConnectionState.CONNECTED
        
        self.stats.total_connections += 1
        self.stats.active_connections += 1
        
        self.logger.info(f"✅ 新连接已添加: {device_info.client_ip} (用户: {device_info.device_id}, 类型: esp32)")
        self.logger.info(f"📊 当前连接数: {self.stats.active_connections}/{self.max_connections}")
        self.logger.info(f"🎉 ESP32设备连接成功: {device_info.device_id}")
        self.logger.info(f"📊 当前连接设备数: {self.stats.active_connections}")
        self.logger.info("🔄 转交给ESP32适配器处理...")
    
    async def _unregister_connection(self, connection_id: str):
        """注销连接"""
        if connection_id in self.active_connections:
            handler = self.active_connections.pop(connection_id)
            device_id = handler.device_info.device_id
            
            # 清理设备映射
            if device_id in self.device_connections:
                del self.device_connections[device_id]
            
            # 清理状态
            if connection_id in self.connection_states:
                del self.connection_states[connection_id]
            
            self.stats.active_connections -= 1
            
            self.logger.info(f"设备连接已注销: {device_id} (连接ID: {connection_id[:8]}...)")
    
    async def _connection_cleanup_task(self):
        """连接清理任务"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                
                current_time = time.time()
                expired_connections = []
                
                for connection_id, handler in self.active_connections.items():
                    # 检查连接超时
                    if (current_time - handler.device_info.last_activity) > self.connection_timeout:
                        expired_connections.append(connection_id)
                
                # 清理过期连接
                for connection_id in expired_connections:
                    handler = self.active_connections.get(connection_id)
                    if handler:
                        self.logger.info(f"清理过期连接: {handler.device_info.device_id}")
                        await handler.close("连接超时")
                
                if expired_connections:
                    self.logger.info(f"清理了 {len(expired_connections)} 个过期连接")
                    
            except Exception as e:
                self.logger.error(f"连接清理任务出错: {e}")
    
    async def _stats_update_task(self):
        """统计更新任务"""
        while True:
            try:
                await asyncio.sleep(30)  # 每30秒更新一次，匹配原来的频率
                
                # 计算平均响应时间
                total_response_time = 0
                response_count = 0
                
                for handler in self.active_connections.values():
                    if hasattr(handler, 'response_times') and handler.response_times:
                        total_response_time += sum(handler.response_times)
                        response_count += len(handler.response_times)
                        handler.response_times.clear()  # 清空已统计的数据
                
                if response_count > 0:
                    self.stats.average_response_time = total_response_time / response_count
                
                # 使用设备日志系统记录统计信息
                esp32_logger.log_system_status()
                
                # 记录性能指标
                if response_count > 0:
                    log_esp32_performance("连接响应", self.stats.average_response_time, {
                        "response_count": response_count,
                        "active_connections": self.stats.active_connections
                    })
                
            except Exception as e:
                self.logger.error(f"统计更新任务出错: {e}")
    
    async def _heartbeat_task(self):
        """心跳检测任务"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                # 发送心跳到所有活跃连接
                heartbeat_message = json.dumps({
                    "type": "heartbeat",
                    "timestamp": time.time()
                })
                
                failed_connections = []
                
                for connection_id, handler in self.active_connections.items():
                    try:
                        await handler.send_message(heartbeat_message)
                    except Exception as e:
                        self.logger.warning(f"心跳发送失败: {handler.device_info.device_id}, {e}")
                        failed_connections.append(connection_id)
                
                # 清理失败的连接
                for connection_id in failed_connections:
                    await self._unregister_connection(connection_id)
                
            except Exception as e:
                self.logger.error(f"心跳任务出错: {e}")
    
    async def send_to_device(self, device_id: str, message: str) -> bool:
        """发送消息到指定设备"""
        connection_id = self.device_connections.get(device_id)
        if not connection_id:
            return False
        
        handler = self.active_connections.get(connection_id)
        if not handler:
            return False
        
        try:
            await handler.send_message(message)
            self.stats.messages_sent += 1
            self.stats.bytes_sent += len(message.encode('utf-8'))
            return True
        except Exception as e:
            self.logger.error(f"发送消息到设备 {device_id} 失败: {e}")
            return False
    
    async def broadcast_message(self, message: str, exclude_devices: Optional[List[str]] = None) -> int:
        """广播消息到所有设备"""
        exclude_devices = exclude_devices or []
        sent_count = 0
        
        for handler in self.active_connections.values():
            if handler.device_info.device_id not in exclude_devices:
                try:
                    await handler.send_message(message)
                    sent_count += 1
                except Exception as e:
                    self.logger.warning(f"广播消息失败: {handler.device_info.device_id}, {e}")
        
        self.stats.messages_sent += sent_count
        self.stats.bytes_sent += sent_count * len(message.encode('utf-8'))
        
        return sent_count
    
    def get_device_list(self) -> List[Dict[str, Any]]:
        """获取设备列表"""
        devices = []
        
        for handler in self.active_connections.values():
            device_info = handler.device_info
            devices.append({
                "device_id": device_info.device_id,
                "client_id": device_info.client_id,
                "client_ip": device_info.client_ip,
                "protocol_version": device_info.protocol_version,
                "connected_at": device_info.connected_at,
                "last_activity": device_info.last_activity,
                "features": device_info.features,
                "audio_params": device_info.audio_params,
                "state": self.connection_states.get(handler.connection_id, ConnectionState.UNKNOWN).value
            })
        
        return devices
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计"""
        return {
            "total_connections": self.stats.total_connections,
            "active_connections": self.stats.active_connections,
            "failed_connections": self.stats.failed_connections,
            "messages_sent": self.stats.messages_sent,
            "messages_received": self.stats.messages_received,
            "bytes_sent": self.stats.bytes_sent,
            "bytes_received": self.stats.bytes_received,
            "average_response_time": self.stats.average_response_time,
            "uptime": time.time() - self.stats.last_reset
        }
    
    async def shutdown(self):
        """关闭管理器"""
        self.logger.info("正在关闭ESP32 WebSocket管理器...")
        
        # 取消后台任务
        for task in self._background_tasks:
            task.cancel()
        
        # 关闭所有连接
        close_tasks = []
        for handler in self.active_connections.values():
            close_tasks.append(handler.close("服务器关闭"))
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        self.logger.info("ESP32 WebSocket管理器已关闭")


# 全局实例
_esp32_websocket_manager: Optional[ESP32WebSocketManager] = None


def get_esp32_websocket_manager(config: Optional[Dict[str, Any]] = None) -> ESP32WebSocketManager:
    """获取ESP32 WebSocket管理器实例"""
    global _esp32_websocket_manager
    if _esp32_websocket_manager is None:
        _esp32_websocket_manager = ESP32WebSocketManager(config)
    return _esp32_websocket_manager


def reset_esp32_websocket_manager():
    """重置ESP32 WebSocket管理器实例"""
    global _esp32_websocket_manager
    _esp32_websocket_manager = None
