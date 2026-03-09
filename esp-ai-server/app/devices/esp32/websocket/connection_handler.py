"""
ESP32连接处理器
ESP32 Connection Handler
参考core/connection.py的设计，为ESP32设备提供完整的连接处理逻辑
"""

import asyncio
import json
import time
import uuid
import struct
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import logging
import websockets

from .types import ESP32DeviceInfo, ConnectionState
from .message_router import get_esp32_message_router, MessageType
from .session_manager import get_esp32_session_manager, ESP32Session, SessionState
from app.devices.esp32.services import (
    get_esp32_asr_integration,
    get_esp32_tts_integration,
    get_esp32_intent_processor,
    get_esp32_speech_coordinator,
    get_esp32_audio_converter
)


@dataclass
class ProcessingState:
    """处理状态"""
    is_processing_audio: bool = False
    is_processing_text: bool = False
    is_generating_tts: bool = False
    is_paused: bool = False
    last_processing_time: float = 0.0


class ESP32ConnectionHandler:
    """ESP32连接处理器"""
    
    def __init__(self, connection_id: str, websocket, device_info: ESP32DeviceInfo, manager):
        self.connection_id = connection_id
        self.websocket = websocket
        self.device_info = device_info
        self.manager = manager
        self.logger = logging.getLogger(f"{__name__}.{device_info.device_id}")
        
        # 会话管理
        self.session_id = str(uuid.uuid4())
        self.session: Optional[ESP32Session] = None
        
        # 组件实例
        self.message_router = get_esp32_message_router()
        self.session_manager = get_esp32_session_manager()
        
        # 服务组件
        self.asr_service = get_esp32_asr_integration(device_info.device_id)
        self.tts_service = get_esp32_tts_integration(device_info.device_id)
        self.intent_processor = get_esp32_intent_processor(device_info.device_id)
        self.speech_coordinator = get_esp32_speech_coordinator(device_info.device_id)
        self.audio_converter = get_esp32_audio_converter(device_info.device_id)
        
        # 处理状态
        self.processing_state = ProcessingState()
        self.response_times: List[float] = []
        
        # 连接状态
        self.is_connected = True
        self.close_reason = ""
        
        # 消息队列
        self.message_queue = asyncio.Queue(maxsize=1000)
        self.send_queue = asyncio.Queue(maxsize=1000)
        
        # 任务管理
        self.background_tasks: List[asyncio.Task] = []
        
        self.logger.info(f"🔧 ESP32连接处理器初始化完成: {connection_id[:8]}... (设备: {device_info.device_id})")
    
    async def handle_connection(self):
        """处理连接的主循环"""
        try:
            # 启动后台任务
            await self._start_background_tasks()
            
            # 等待Hello消息
            await self._wait_for_hello()
            
            # 主消息处理循环
            self.logger.info(f"ESP32设备 {self.device_info.device_id} 监听状态消息")
            async for message in self.websocket:
                if not self.is_connected:
                    break
                
                # 更新活动时间
                self.device_info.last_activity = time.time()
                
                # 路由消息
                await self._handle_message(message)
                
                # 定期输出监听状态
                if hasattr(self, '_last_status_log'):
                    if time.time() - self._last_status_log > 20:  # 每20秒输出一次
                        self.logger.info(f"ESP32设备 {self.device_info.device_id} 监听状态消息")
                        self._last_status_log = time.time()
                else:
                    self._last_status_log = time.time()
            
        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"设备 {self.device_info.device_id} 连接关闭")
        except Exception as e:
            self.logger.error(f"连接处理出错: {e}", exc_info=True)
        finally:
            await self._cleanup()
    
    async def _start_background_tasks(self):
        """启动后台任务"""
        # 消息发送任务
        send_task = asyncio.create_task(self._message_send_task())
        self.background_tasks.append(send_task)
        
        # 状态监控任务
        monitor_task = asyncio.create_task(self._connection_monitor_task())
        self.background_tasks.append(monitor_task)
        
        self.logger.debug("后台任务已启动")
    
    async def _wait_for_hello(self, timeout: float = 20.0):
        """等待Hello消息"""
        try:
            # 等待第一条消息（应该是Hello）
            hello_message = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=timeout
            )
            
            # 处理Hello消息
            response = await self.message_router.route_message(hello_message, self)
            
            if response:
                await self.send_message(json.dumps(response))
            
            self.logger.info(f"🤝 Hello握手完成: {self.device_info.device_id} (会话: {self.session_id[:8]}...)")
            
        except asyncio.TimeoutError:
            self.logger.error("等待Hello消息超时")
            await self.close("Hello超时")
        except Exception as e:
            self.logger.error(f"Hello握手失败: {e}")
            await self.close("Hello失败")
    
    async def _handle_message(self, message):
        """处理单个消息"""
        try:
            start_time = time.time()
            
            # 显示接收到的消息类型和内容
            if isinstance(message, bytes):
                self.logger.info(f"🔍 [连接处理] 收到二进制消息: {len(message)} 字节, 前16字节: {message[:16].hex()}")
            elif isinstance(message, str):
                self.logger.info(f"🔍 [连接处理] 收到文本消息: {message[:100]}...")
            else:
                self.logger.info(f"🔍 [连接处理] 收到其他类型消息: type={type(message)}, len={len(message) if hasattr(message, '__len__') else 'N/A'}")
            
            # 路由消息
            response = await self.message_router.route_message(message, self)
            
            # 发送响应
            if response:
                await self.send_message(json.dumps(response))
            
            # 记录处理时间
            processing_time = time.time() - start_time
            self.response_times.append(processing_time)
            
            # 限制响应时间记录数量
            if len(self.response_times) > 100:
                self.response_times = self.response_times[-50:]
            
        except Exception as e:
            self.logger.error(f"消息处理失败: {e}")
            await self.send_message(json.dumps({
                "type": "error",
                "message": f"消息处理失败: {str(e)}"
            }))
    
    async def initialize_session(self):
        """初始化会话"""
        try:
            # 创建会话
            self.session = await self.session_manager.create_session(
                device_id=self.device_info.device_id,
                user_id=self.device_info.client_id or self.device_info.device_id,
                device_info={
                    "features": self.device_info.features,
                    "audio_params": self.device_info.audio_params,
                    "client_ip": self.device_info.client_ip,
                    "protocol_version": self.device_info.protocol_version
                }
            )
            
            self.session_id = self.session.session_id
            
            self.logger.info(f"会话初始化完成: {self.session_id[:8]}...")
            
        except Exception as e:
            self.logger.error(f"会话初始化失败: {e}")
            raise
    
    async def send_message(self, message):
        """发送文本消息（支持字符串或字典）"""
        if not self.is_connected:
            return
        
        try:
            # 如果传入的是字典，转换为JSON字符串
            if isinstance(message, dict):
                message = json.dumps(message, ensure_ascii=False)
            elif not isinstance(message, str):
                self.logger.error(f"❌ 不支持的消息类型: {type(message)}, 消息: {message}")
                return
            
            await self.send_queue.put(("text", message))
        except asyncio.QueueFull:
            self.logger.warning("发送队列已满，丢弃消息")
        except Exception as e:
            self.logger.error(f"❌ 发送消息失败: {e}, 消息类型: {type(message)}")
    
    async def send_audio_data(self, audio_data: bytes, audio_format: str = "opus"):
        """发送音频数据"""
        if not self.is_connected:
            return
        
        try:
            self.logger.info(f"📤 发送TTS音频到ESP32: {len(audio_data)}字节, 格式={audio_format}")
            
            # 使用二进制协议发送音频
            binary_data = await self._encode_audio_packet(audio_data, audio_format)
            await self.send_queue.put(("binary", binary_data))
            
            self.logger.info(f"✅ 音频数据已加入发送队列: {len(binary_data)}字节 (包含协议头)")
            
        except Exception as e:
            self.logger.error(f"❌ 发送音频数据失败: {e}")
    
    async def send_audio_frame(self, audio_frame):
        """发送音频帧（用于流式TTS）"""
        if not self.is_connected:
            return
        
        try:
            # 从AudioFrame对象中提取音频数据
            if hasattr(audio_frame, 'data'):
                audio_data = audio_frame.data
                audio_format = getattr(audio_frame, 'format', 'opus')
            elif isinstance(audio_frame, bytes):
                # 如果直接传入bytes，直接使用
                audio_data = audio_frame
                audio_format = 'opus'
            else:
                self.logger.error(f"❌ 不支持的音频帧类型: {type(audio_frame)}")
                return
            
            # 使用二进制协议发送音频
            binary_data = await self._encode_audio_packet(audio_data, audio_format)
            await self.send_queue.put(("binary", binary_data))
            
        except Exception as e:
            self.logger.error(f"❌ 发送音频帧失败: {e}")
            raise
    
    async def _encode_audio_packet(self, audio_data: bytes, audio_format: str) -> bytes:
        """编码音频数据包"""
        try:
            # 使用BinaryProtocol2格式（大端字节序，完全匹配ESP32硬件端结构体）
            version = 2
            msg_type = 1  # TTS音频数据 (硬件端期望类型1)
            timestamp = int(time.time() * 1000) & 0xFFFFFFFF  # 限制在32位范围内
            payload_size = len(audio_data)
            
            # 构建数据包头部（大端字节序，匹配ESP32 BinaryProtocol2结构体）
            # ESP32结构体：version(2) + type(2) + timestamp(4) + payload_size(4)
            header = struct.pack('>HHII', version, msg_type, timestamp, payload_size)
            
            # 组合完整数据包
            packet = header + audio_data
            
            self.logger.info(f"🔧 编码音频包: 版本={version}, 类型={msg_type}, 时间戳={timestamp}, 负载={payload_size}字节")
            self.logger.debug(f"   协议头: {header.hex()[:32]}...")
            
            return packet
            
        except Exception as e:
            self.logger.error(f"编码音频包失败: {e}")
            return b""
    
    async def _message_send_task(self):
        """消息发送任务"""
        while self.is_connected:
            try:
                # 获取待发送消息
                message_type, message_data = await asyncio.wait_for(
                    self.send_queue.get(),
                    timeout=1.0
                )
                
                # 发送消息
                if message_type == "text":
                    await self.websocket.send(message_data)
                elif message_type == "binary":
                    await self.websocket.send(message_data)
                
                # 更新统计
                if hasattr(self.manager, 'stats'):
                    self.manager.stats.messages_sent += 1
                    self.manager.stats.bytes_sent += len(message_data)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self.is_connected:
                    self.logger.error(f"消息发送失败: {e}")
                break
    
    async def _connection_monitor_task(self):
        """连接监控任务"""
        while self.is_connected:
            try:
                await asyncio.sleep(30)  # 每30秒检查一次
                
                # 检查连接状态
                if hasattr(self.websocket, 'closed') and self.websocket.closed:
                    self.logger.info("检测到连接已关闭")
                    break
                
                # 更新会话活动时间
                if self.session:
                    self.session.update_activity()
                
            except Exception as e:
                self.logger.error(f"连接监控出错: {e}")
                break
    
    async def stop_all_processing(self):
        """停止所有处理"""
        self.processing_state.is_paused = True
        self.processing_state.is_processing_audio = False
        self.processing_state.is_processing_text = False
        self.processing_state.is_generating_tts = False
        
        self.logger.info("已停止所有处理")
    
    async def pause_processing(self):
        """暂停处理"""
        self.processing_state.is_paused = True
        
        if self.session:
            await self.session_manager.pause_session(self.session.session_id)
        
        self.logger.info("处理已暂停")
    
    async def resume_processing(self):
        """恢复处理"""
        self.processing_state.is_paused = False
        
        if self.session:
            await self.session_manager.resume_session(self.session.session_id)
        
        self.logger.info("处理已恢复")
    
    async def reset_session(self):
        """重置会话"""
        if self.session:
            # 关闭当前会话
            await self.session_manager.close_session(self.session.session_id, "reset")
            
            # 创建新会话
            await self.initialize_session()
        
        # 重置处理状态
        self.processing_state = ProcessingState()
        
        self.logger.info("会话已重置")
    
    async def get_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            "connection_id": self.connection_id,
            "device_id": self.device_info.device_id,
            "session_id": self.session_id,
            "is_connected": self.is_connected,
            "processing_state": {
                "is_processing_audio": self.processing_state.is_processing_audio,
                "is_processing_text": self.processing_state.is_processing_text,
                "is_generating_tts": self.processing_state.is_generating_tts,
                "is_paused": self.processing_state.is_paused
            },
            "device_info": {
                "client_ip": self.device_info.client_ip,
                "protocol_version": self.device_info.protocol_version,
                "connected_at": self.device_info.connected_at,
                "last_activity": self.device_info.last_activity,
                "features": self.device_info.features,
                "audio_params": self.device_info.audio_params
            },
            "session_info": {
                "state": self.session.state.value if self.session else "none",
                "conversation_count": self.session.conversation_context.conversation_count if self.session else 0,
                "total_interactions": self.session.conversation_context.total_interactions if self.session else 0,
                "emotional_state": self.session.conversation_context.emotional_state if self.session else None,
                "risk_level": self.session.conversation_context.risk_level if self.session else "low"
            },
            "performance": {
                "average_response_time": sum(self.response_times) / len(self.response_times) if self.response_times else 0,
                "total_responses": len(self.response_times),
                "queue_sizes": {
                    "message_queue": self.message_queue.qsize(),
                    "send_queue": self.send_queue.qsize()
                }
            }
        }
    
    async def get_services_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            "asr_service": {
                "available": self.asr_service is not None,
                "status": "active" if self.asr_service else "unavailable"
            },
            "tts_service": {
                "available": self.tts_service is not None,
                "status": "active" if self.tts_service else "unavailable"
            },
            "intent_processor": {
                "available": self.intent_processor is not None,
                "status": "active" if self.intent_processor else "unavailable"
            },
            "speech_coordinator": {
                "available": self.speech_coordinator is not None,
                "status": "active" if self.speech_coordinator else "unavailable"
            },
            "audio_converter": {
                "available": self.audio_converter is not None,
                "status": "active" if self.audio_converter else "unavailable"
            }
        }
    
    async def close(self, reason: str = "normal"):
        """关闭连接"""
        if not self.is_connected:
            return
        
        self.is_connected = False
        self.close_reason = reason
        
        try:
            # 取消后台任务
            for task in self.background_tasks:
                if not task.done():
                    task.cancel()
            
            # 等待任务完成
            if self.background_tasks:
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
            
            # 关闭会话
            if self.session:
                await self.session_manager.close_session(self.session.session_id, reason)
            
            # 关闭WebSocket连接
            if not self.websocket.closed:
                await self.websocket.close()
            
            self.logger.info(f"连接已关闭: {reason}")
            
        except Exception as e:
            self.logger.error(f"关闭连接时出错: {e}")
    
    async def _cleanup(self):
        """清理资源"""
        try:
            # 标记为已断开
            self.is_connected = False
            
            # 取消所有后台任务
            for task in self.background_tasks:
                if not task.done():
                    task.cancel()
            
            # 等待任务完成
            if self.background_tasks:
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
            
            # 清空队列
            while not self.message_queue.empty():
                try:
                    self.message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            while not self.send_queue.empty():
                try:
                    self.send_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            # 关闭会话
            if self.session:
                await self.session_manager.close_session(
                    self.session.session_id, 
                    self.close_reason or "cleanup"
                )
            
            # 清空设备的流式ASR缓冲区（防止残留数据）
            if hasattr(self.message_router, 'clear_device_buffer'):
                self.message_router.clear_device_buffer(self.device_info.device_id)
            
            self.logger.info("连接资源清理完成")
            
        except Exception as e:
            self.logger.error(f"资源清理失败: {e}")
    
    def __del__(self):
        """析构函数"""
        if self.is_connected:
            # 在事件循环中安排清理任务
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._cleanup())
            except:
                pass
