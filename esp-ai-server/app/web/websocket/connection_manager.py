"""
WebSocket连接管理器
WebSocket Connection Manager
管理WebSocket连接的生命周期和状态
"""

import asyncio
import json
import time
from typing import Dict, Set, List
from app.core import logger


class WebSocketConnection:
    """WebSocket连接封装"""
    
    def __init__(self, websocket, user_id: str, client_id: str = None):
        """初始化连接"""
        self.websocket = websocket
        self.user_id = user_id
        self.client_id = client_id or f"client_{int(time.time())}"
        self.connected_at = time.time()
        self.last_ping = time.time()
        self.is_alive = True
    
    async def send_json(self, data: dict):
        """发送JSON消息"""
        try:
            if self.is_alive:
                await self.websocket.send(json.dumps(data))
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            self.is_alive = False
    
    async def send_text(self, text: str):
        """发送文本消息"""
        try:
            if self.is_alive:
                await self.websocket.send(text)
        except Exception as e:
            logger.error(f"发送文本失败: {e}")
            self.is_alive = False
    
    def update_ping(self):
        """更新ping时间"""
        self.last_ping = time.time()
    
    def is_timeout(self, timeout_seconds: int = 300) -> bool:
        """检查是否超时"""
        return time.time() - self.last_ping > timeout_seconds
    
    async def close(self):
        """关闭连接"""
        try:
            self.is_alive = False
            if not self.websocket.closed:
                await self.websocket.close()
        except Exception as e:
            logger.error(f"关闭连接失败: {e}")


class WebSocketConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        """初始化连接管理器"""
        # 存储所有活跃连接 {connection_id: WebSocketConnection}
        self.connections: Dict[str, WebSocketConnection] = {}
        
        # 按用户ID索引连接 {user_id: Set[connection_id]}
        self.user_connections: Dict[str, Set[str]] = {}
        
        # 启动清理任务（延迟到有事件循环时）
        self._cleanup_task = None
        # 不在初始化时启动任务，避免事件循环问题
        
        logger.info("WebSocket连接管理器初始化完成")
    
    def _start_cleanup_task(self):
        """启动连接清理任务"""
        async def cleanup_loop():
            while True:
                try:
                    await self.cleanup_dead_connections()
                    await asyncio.sleep(60)  # 每分钟清理一次
                except Exception as e:
                    logger.error(f"连接清理任务失败: {e}")
                    await asyncio.sleep(60)
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
    
    async def add_connection(self, websocket, user_id: str, client_id: str = None) -> str:
        """添加新连接"""
        connection_id = f"{user_id}_{client_id or int(time.time())}"
        connection = WebSocketConnection(websocket, user_id, client_id)
        
        # 存储连接
        self.connections[connection_id] = connection
        
        # 按用户ID索引
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)
        
        # 首次添加连接时启动清理任务
        if self._cleanup_task is None:
            try:
                self._start_cleanup_task()
            except RuntimeError:
                # 如果没有事件循环，跳过清理任务
                pass
        
        logger.info(f"新增WebSocket连接: {connection_id} (用户: {user_id})")
        return connection_id
    
    async def remove_connection(self, connection_id: str):
        """移除连接"""
        if connection_id not in self.connections:
            return
        
        connection = self.connections[connection_id]
        user_id = connection.user_id
        
        # 关闭连接
        await connection.close()
        
        # 从索引中移除
        del self.connections[connection_id]
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        logger.info(f"移除WebSocket连接: {connection_id} (用户: {user_id})")
    
    def get_connection(self, connection_id: str) -> WebSocketConnection:
        """获取连接"""
        return self.connections.get(connection_id)
    
    def get_user_connections(self, user_id: str) -> List[WebSocketConnection]:
        """获取用户的所有连接"""
        if user_id not in self.user_connections:
            return []
        
        connections = []
        for connection_id in self.user_connections[user_id]:
            if connection_id in self.connections:
                connections.append(self.connections[connection_id])
        
        return connections
    
    async def broadcast_to_user(self, user_id: str, data: dict):
        """向用户的所有连接广播消息"""
        connections = self.get_user_connections(user_id)
        if not connections:
            logger.warning(f"用户 {user_id} 没有活跃连接")
            return
        
        # 并发发送消息
        tasks = [conn.send_json(data) for conn in connections if conn.is_alive]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def broadcast_to_all(self, data: dict):
        """向所有连接广播消息"""
        tasks = [
            conn.send_json(data) 
            for conn in self.connections.values() 
            if conn.is_alive
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def cleanup_dead_connections(self):
        """清理死连接"""
        dead_connections = []
        
        for connection_id, connection in self.connections.items():
            if not connection.is_alive or connection.is_timeout():
                dead_connections.append(connection_id)
        
        for connection_id in dead_connections:
            await self.remove_connection(connection_id)
        
        if dead_connections:
            logger.info(f"清理了 {len(dead_connections)} 个死连接")
    
    def get_stats(self) -> dict:
        """获取连接统计信息"""
        alive_connections = sum(1 for conn in self.connections.values() if conn.is_alive)
        
        return {
            'total_connections': len(self.connections),
            'alive_connections': alive_connections,
            'unique_users': len(self.user_connections),
            'average_connections_per_user': (
                alive_connections / len(self.user_connections) 
                if self.user_connections else 0
            )
        }
    
    async def shutdown(self):
        """关闭连接管理器"""
        # 停止清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # 关闭所有连接
        close_tasks = [
            self.remove_connection(connection_id) 
            for connection_id in list(self.connections.keys())
        ]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        logger.info("WebSocket连接管理器已关闭")


# 创建全局实例
_connection_manager = None

def get_connection_manager() -> WebSocketConnectionManager:
    """获取连接管理器单例"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = WebSocketConnectionManager()
    return _connection_manager
