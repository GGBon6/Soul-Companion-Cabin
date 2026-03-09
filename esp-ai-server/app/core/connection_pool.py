"""
连接池管理器
Connection Pool Manager
提供WebSocket连接的生命周期管理、健康检查和自动重连功能
"""

import asyncio
import time
import json
import weakref
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from app.core import logger
from app.core.config import settings


class ConnectionState(Enum):
    """连接状态枚举"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    UNHEALTHY = "unhealthy"
    RECONNECTING = "reconnecting"


@dataclass
class ConnectionInfo:
    """连接信息"""
    websocket: websockets.WebSocketServerProtocol
    user_id: Optional[str] = None
    client_ip: str = ""
    client_type: str = "unknown"  # web, esp32, mobile, etc.
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    last_ping: Optional[datetime] = None
    last_pong: Optional[datetime] = None
    state: ConnectionState = ConnectionState.CONNECTING
    reconnect_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectionMetrics:
    """连接池指标"""
    total_connections: int = 0
    active_connections: int = 0
    connections_by_ip: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    connections_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_connects: int = 0
    total_disconnects: int = 0
    total_reconnects: int = 0
    failed_connections: int = 0
    health_check_failures: int = 0
    last_updated: datetime = field(default_factory=datetime.now)


class ConnectionPoolManager:
    """连接池管理器"""
    
    def __init__(self):
        """初始化连接池管理器"""
        self.connections: Dict[websockets.WebSocketServerProtocol, ConnectionInfo] = {}
        self.user_connections: Dict[str, Set[websockets.WebSocketServerProtocol]] = defaultdict(set)
        self.ip_connections: Dict[str, Set[websockets.WebSocketServerProtocol]] = defaultdict(set)
        self.metrics = ConnectionMetrics()
        
        # 速率限制
        self.connection_timestamps: deque = deque()
        
        # 健康检查任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._metrics_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # 事件回调
        self.on_connection_established = None
        self.on_connection_lost = None
        self.on_connection_limit_exceeded = None
        
        logger.info("🔧 连接池管理器初始化完成")
    
    async def start(self):
        """启动连接池管理器"""
        logger.info("🚀 启动连接池管理器...")
        
        # 启动后台任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        if settings.ENABLE_CONNECTION_METRICS:
            self._metrics_task = asyncio.create_task(self._metrics_collection_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("✅ 连接池管理器启动完成")
    
    async def stop(self):
        """停止连接池管理器"""
        logger.info("⏹️ 停止连接池管理器...")
        
        # 取消后台任务
        tasks = [self._health_check_task, self._metrics_task, self._cleanup_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 关闭所有连接
        await self._close_all_connections()
        
        logger.info("✅ 连接池管理器已停止")
    
    def can_accept_connection(self, client_ip: str) -> Tuple[bool, str]:
        """检查是否可以接受新连接"""
        # 检查总连接数限制
        if len(self.connections) >= settings.MAX_CONNECTIONS:
            return False, f"已达到最大连接数限制: {settings.MAX_CONNECTIONS}"
        
        # 检查单IP连接数限制
        ip_count = len(self.ip_connections.get(client_ip, set()))
        if ip_count >= settings.MAX_CONNECTIONS_PER_IP:
            return False, f"IP {client_ip} 已达到最大连接数限制: {settings.MAX_CONNECTIONS_PER_IP}"
        
        # 检查连接速率限制
        now = time.time()
        # 清理过期的连接时间戳
        while self.connection_timestamps and now - self.connection_timestamps[0] > 1.0:
            self.connection_timestamps.popleft()
        
        if len(self.connection_timestamps) >= settings.CONNECTION_RATE_LIMIT:
            return False, f"连接速率过快，每秒最多 {settings.CONNECTION_RATE_LIMIT} 个新连接"
        
        return True, "可以接受连接"
    
    async def add_connection(
        self, 
        websocket: websockets.WebSocketServerProtocol,
        user_id: Optional[str] = None,
        client_type: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """添加新连接"""
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        
        # 检查是否可以接受连接
        can_accept, reason = self.can_accept_connection(client_ip)
        if not can_accept:
            logger.warning(f"❌ 拒绝连接 {client_ip}: {reason}")
            if self.on_connection_limit_exceeded:
                await self.on_connection_limit_exceeded(websocket, reason)
            return False
        
        # 记录连接时间戳
        self.connection_timestamps.append(time.time())
        
        # 创建连接信息
        conn_info = ConnectionInfo(
            websocket=websocket,
            user_id=user_id,
            client_ip=client_ip,
            client_type=client_type,
            state=ConnectionState.CONNECTED,
            metadata=metadata or {}
        )
        
        # 添加到连接池
        self.connections[websocket] = conn_info
        self.ip_connections[client_ip].add(websocket)
        if user_id:
            self.user_connections[user_id].add(websocket)
        
        # 更新指标
        self.metrics.total_connections = len(self.connections)
        self.metrics.active_connections = len([c for c in self.connections.values() 
                                             if c.state == ConnectionState.CONNECTED])
        self.metrics.connections_by_ip[client_ip] += 1
        self.metrics.connections_by_type[client_type] += 1
        self.metrics.total_connects += 1
        
        logger.info(f"✅ 新连接已添加: {client_ip} (用户: {user_id}, 类型: {client_type})")
        logger.info(f"📊 当前连接数: {len(self.connections)}/{settings.MAX_CONNECTIONS}")
        
        # 触发连接建立回调
        if self.on_connection_established:
            await self.on_connection_established(websocket, conn_info)
        
        return True
    
    async def remove_connection(self, websocket: websockets.WebSocketServerProtocol, reason: str = "unknown"):
        """移除连接"""
        if websocket not in self.connections:
            return
        
        conn_info = self.connections[websocket]
        
        # 从连接池中移除
        del self.connections[websocket]
        self.ip_connections[conn_info.client_ip].discard(websocket)
        if conn_info.user_id:
            self.user_connections[conn_info.user_id].discard(websocket)
            # 清理空的用户连接集合
            if not self.user_connections[conn_info.user_id]:
                del self.user_connections[conn_info.user_id]
        
        # 清理空的IP连接集合
        if not self.ip_connections[conn_info.client_ip]:
            del self.ip_connections[conn_info.client_ip]
        
        # 更新指标
        self.metrics.total_connections = len(self.connections)
        self.metrics.active_connections = len([c for c in self.connections.values() 
                                             if c.state == ConnectionState.CONNECTED])
        self.metrics.connections_by_ip[conn_info.client_ip] -= 1
        if self.metrics.connections_by_ip[conn_info.client_ip] <= 0:
            del self.metrics.connections_by_ip[conn_info.client_ip]
        
        self.metrics.connections_by_type[conn_info.client_type] -= 1
        if self.metrics.connections_by_type[conn_info.client_type] <= 0:
            del self.metrics.connections_by_type[conn_info.client_type]
        
        self.metrics.total_disconnects += 1
        
        logger.info(f"📴 连接已移除: {conn_info.client_ip} (用户: {conn_info.user_id}, 原因: {reason})")
        logger.info(f"📊 当前连接数: {len(self.connections)}/{settings.MAX_CONNECTIONS}")
        
        # 触发连接丢失回调
        if self.on_connection_lost:
            await self.on_connection_lost(websocket, conn_info, reason)
    
    def get_connection_info(self, websocket: websockets.WebSocketServerProtocol) -> Optional[ConnectionInfo]:
        """获取连接信息"""
        return self.connections.get(websocket)
    
    def get_user_connections(self, user_id: str) -> Set[websockets.WebSocketServerProtocol]:
        """获取用户的所有连接"""
        return self.user_connections.get(user_id, set()).copy()
    
    def update_connection_activity(self, websocket: websockets.WebSocketServerProtocol):
        """更新连接活动时间"""
        if websocket in self.connections:
            self.connections[websocket].last_activity = datetime.now()
    
    def update_user_id(self, websocket: websockets.WebSocketServerProtocol, user_id: str):
        """更新连接的用户ID"""
        if websocket not in self.connections:
            return
        
        conn_info = self.connections[websocket]
        old_user_id = conn_info.user_id
        
        # 从旧用户ID中移除
        if old_user_id:
            self.user_connections[old_user_id].discard(websocket)
            if not self.user_connections[old_user_id]:
                del self.user_connections[old_user_id]
        
        # 添加到新用户ID
        conn_info.user_id = user_id
        self.user_connections[user_id].add(websocket)
        
        logger.debug(f"🔄 连接用户ID已更新: {old_user_id} -> {user_id}")
    
    async def send_to_user(self, user_id: str, message: dict) -> int:
        """向用户的所有连接发送消息"""
        connections = self.get_user_connections(user_id)
        sent_count = 0
        
        for websocket in connections:
            try:
                await websocket.send(json.dumps(message, ensure_ascii=False))
                sent_count += 1
                self.update_connection_activity(websocket)
            except Exception as e:
                logger.warning(f"⚠️ 向用户 {user_id} 发送消息失败: {e}")
                # 标记连接为不健康
                if websocket in self.connections:
                    self.connections[websocket].state = ConnectionState.UNHEALTHY
        
        return sent_count
    
    async def broadcast(self, message: dict, exclude_users: Optional[Set[str]] = None) -> int:
        """广播消息到所有连接"""
        sent_count = 0
        exclude_users = exclude_users or set()
        
        for websocket, conn_info in self.connections.items():
            if conn_info.user_id in exclude_users:
                continue
            
            try:
                await websocket.send(json.dumps(message, ensure_ascii=False))
                sent_count += 1
                self.update_connection_activity(websocket)
            except Exception as e:
                logger.warning(f"⚠️ 广播消息失败 {conn_info.client_ip}: {e}")
                conn_info.state = ConnectionState.UNHEALTHY
        
        return sent_count
    
    def get_metrics(self) -> ConnectionMetrics:
        """获取连接池指标"""
        # 更新实时指标
        self.metrics.total_connections = len(self.connections)
        self.metrics.active_connections = len([c for c in self.connections.values() 
                                             if c.state == ConnectionState.CONNECTED])
        self.metrics.last_updated = datetime.now()
        return self.metrics
    
    async def _health_check_loop(self):
        """健康检查循环"""
        logger.info("🏥 启动连接健康检查循环")
        
        while True:
            try:
                await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 健康检查循环异常: {e}", exc_info=True)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        logger.debug("🏥 执行连接健康检查...")
        
        now = datetime.now()
        unhealthy_connections = []
        
        for websocket, conn_info in self.connections.items():
            try:
                # 检查连接是否超时
                if now - conn_info.last_activity > timedelta(seconds=settings.IDLE_TIMEOUT):
                    logger.warning(f"⚠️ 连接空闲超时: {conn_info.client_ip}")
                    unhealthy_connections.append((websocket, "idle_timeout"))
                    continue
                
                # 发送ping检查连接状态
                if (not conn_info.last_ping or 
                    now - conn_info.last_ping > timedelta(seconds=settings.PING_INTERVAL)):
                    
                    await self._send_ping(websocket, conn_info)
                
                # 检查pong超时
                if (conn_info.last_ping and 
                    (not conn_info.last_pong or conn_info.last_pong < conn_info.last_ping) and
                    now - conn_info.last_ping > timedelta(seconds=settings.PONG_TIMEOUT)):
                    
                    logger.warning(f"⚠️ Pong超时: {conn_info.client_ip}")
                    unhealthy_connections.append((websocket, "pong_timeout"))
                
            except Exception as e:
                logger.warning(f"⚠️ 健康检查异常 {conn_info.client_ip}: {e}")
                unhealthy_connections.append((websocket, f"health_check_error: {e}"))
        
        # 移除不健康的连接
        for websocket, reason in unhealthy_connections:
            self.metrics.health_check_failures += 1
            await self.remove_connection(websocket, reason)
            try:
                await websocket.close()
            except:
                pass
        
        if unhealthy_connections:
            logger.info(f"🏥 健康检查完成，移除 {len(unhealthy_connections)} 个不健康连接")
    
    async def _send_ping(self, websocket: websockets.WebSocketServerProtocol, conn_info: ConnectionInfo):
        """发送ping消息"""
        try:
            ping_message = {
                "type": "ping",
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(ping_message))
            conn_info.last_ping = datetime.now()
            logger.debug(f"📡 发送ping到 {conn_info.client_ip}")
        except Exception as e:
            logger.warning(f"⚠️ 发送ping失败 {conn_info.client_ip}: {e}")
            conn_info.state = ConnectionState.UNHEALTHY
    
    async def handle_pong(self, websocket: websockets.WebSocketServerProtocol):
        """处理pong响应"""
        if websocket in self.connections:
            self.connections[websocket].last_pong = datetime.now()
            logger.debug(f"📡 收到pong从 {self.connections[websocket].client_ip}")
    
    async def _metrics_collection_loop(self):
        """指标收集循环"""
        logger.info("📊 启动连接指标收集循环")
        
        while True:
            try:
                await asyncio.sleep(settings.METRICS_COLLECTION_INTERVAL)
                await self._collect_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 指标收集循环异常: {e}", exc_info=True)
    
    async def _collect_metrics(self):
        """收集连接指标"""
        metrics = self.get_metrics()
        
        logger.info(f"📊 连接池指标 - 总连接: {metrics.total_connections}, "
                   f"活跃连接: {metrics.active_connections}, "
                   f"总连接数: {metrics.total_connects}, "
                   f"总断开数: {metrics.total_disconnects}")
        
        # 这里可以将指标发送到监控系统
        # 例如: Prometheus, InfluxDB, 或其他监控后端
    
    async def _cleanup_loop(self):
        """清理循环"""
        logger.info("🧹 启动连接清理循环")
        
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                await self._cleanup_stale_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 清理循环异常: {e}", exc_info=True)
    
    async def _cleanup_stale_data(self):
        """清理过期数据"""
        # 清理过期的连接时间戳
        now = time.time()
        while self.connection_timestamps and now - self.connection_timestamps[0] > 3600:  # 1小时
            self.connection_timestamps.popleft()
        
        logger.debug("🧹 清理过期数据完成")
    
    async def _close_all_connections(self):
        """关闭所有连接"""
        logger.info(f"🔌 关闭所有连接 ({len(self.connections)} 个)...")
        
        close_tasks = []
        for websocket in list(self.connections.keys()):
            close_tasks.append(self._close_connection_gracefully(websocket))
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        self.connections.clear()
        self.user_connections.clear()
        self.ip_connections.clear()
        
        logger.info("✅ 所有连接已关闭")
    
    async def _close_connection_gracefully(self, websocket: websockets.WebSocketServerProtocol):
        """优雅关闭连接"""
        try:
            # 发送关闭通知
            close_message = {
                "type": "server_shutdown",
                "message": "服务器正在关闭，连接即将断开"
            }
            await websocket.send(json.dumps(close_message))
            await asyncio.sleep(0.1)  # 给客户端一点时间处理消息
            
            await websocket.close()
        except Exception as e:
            logger.debug(f"关闭连接时出现异常: {e}")


# 全局连接池管理器实例
_connection_pool_manager: Optional[ConnectionPoolManager] = None


def get_connection_pool_manager() -> ConnectionPoolManager:
    """获取连接池管理器实例"""
    global _connection_pool_manager
    if _connection_pool_manager is None:
        _connection_pool_manager = ConnectionPoolManager()
    return _connection_pool_manager


async def initialize_connection_pool():
    """初始化连接池管理器"""
    manager = get_connection_pool_manager()
    await manager.start()
    return manager


async def shutdown_connection_pool():
    """关闭连接池管理器"""
    global _connection_pool_manager
    if _connection_pool_manager:
        await _connection_pool_manager.stop()
        _connection_pool_manager = None
