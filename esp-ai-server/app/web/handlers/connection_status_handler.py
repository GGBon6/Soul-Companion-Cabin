"""
连接状态处理器
Connection Status Handler
提供连接池状态查询和管理功能
"""

import json
from datetime import datetime
from typing import Dict, Any
import websockets

from app.core import logger
from app.core.connection_pool import get_connection_pool_manager
from app.core.reconnect_manager import get_reconnect_manager
from app.web.message_handlers.base_handler import BaseMessageHandler


class ConnectionStatusHandler(BaseMessageHandler):
    """连接状态处理器"""
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """处理连接状态相关消息"""
        message_type = data.get("type")
        
        # 根据消息类型分发到具体处理方法
        handler_map = {
            "get_connection_status": self.handle_get_connection_status,
            "get_pool_metrics": self.handle_get_pool_metrics,
            "get_user_connections": self.handle_get_user_connections,
            "send_to_user": self.handle_send_to_user,
            "broadcast_message": self.handle_broadcast_message,
            "get_reconnect_sessions": self.handle_get_reconnect_sessions,
            "force_disconnect": self.handle_force_disconnect,
        }
        
        handler = handler_map.get(message_type)
        if handler:
            await handler(websocket, data)
        else:
            await self.send_message(websocket, "error", f"未知的连接状态消息类型: {message_type}")
    
    async def handle_get_connection_status(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取连接状态"""
        try:
            connection_pool = get_connection_pool_manager()
            
            # 获取当前连接的信息
            conn_info = connection_pool.get_connection_info(websocket)
            if not conn_info:
                await self.send_message(websocket, "connection_status", {
                    "error": "连接信息不存在"
                })
                return
            
            status_data = {
                "connection_id": id(websocket),
                "user_id": conn_info.user_id,
                "client_ip": conn_info.client_ip,
                "client_type": conn_info.client_type,
                "connected_at": conn_info.connected_at.isoformat(),
                "last_activity": conn_info.last_activity.isoformat(),
                "state": conn_info.state.value,
                "reconnect_count": conn_info.reconnect_count,
                "metadata": conn_info.metadata
            }
            
            await self.send_message(websocket, "connection_status", status_data)
            
        except Exception as e:
            logger.error(f"❌ 获取连接状态失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取连接状态失败")
    
    async def handle_get_pool_metrics(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取连接池指标"""
        try:
            connection_pool = get_connection_pool_manager()
            metrics = connection_pool.get_metrics()
            
            metrics_data = {
                "total_connections": metrics.total_connections,
                "active_connections": metrics.active_connections,
                "connections_by_ip": dict(metrics.connections_by_ip),
                "connections_by_type": dict(metrics.connections_by_type),
                "total_connects": metrics.total_connects,
                "total_disconnects": metrics.total_disconnects,
                "total_reconnects": metrics.total_reconnects,
                "failed_connections": metrics.failed_connections,
                "health_check_failures": metrics.health_check_failures,
                "last_updated": metrics.last_updated.isoformat()
            }
            
            await self.send_message(websocket, "pool_metrics", metrics_data)
            
        except Exception as e:
            logger.error(f"❌ 获取连接池指标失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取连接池指标失败")
    
    async def handle_get_user_connections(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取用户的所有连接"""
        try:
            user_id = data.get("user_id")
            if not user_id:
                await self.send_message(websocket, "error", "缺少用户ID")
                return
            
            connection_pool = get_connection_pool_manager()
            user_connections = connection_pool.get_user_connections(user_id)
            
            connections_data = []
            for conn_websocket in user_connections:
                conn_info = connection_pool.get_connection_info(conn_websocket)
                if conn_info:
                    connections_data.append({
                        "connection_id": id(conn_websocket),
                        "client_ip": conn_info.client_ip,
                        "client_type": conn_info.client_type,
                        "connected_at": conn_info.connected_at.isoformat(),
                        "last_activity": conn_info.last_activity.isoformat(),
                        "state": conn_info.state.value,
                        "metadata": conn_info.metadata
                    })
            
            await self.send_message(websocket, "user_connections", {
                "user_id": user_id,
                "connections": connections_data,
                "total_count": len(connections_data)
            })
            
        except Exception as e:
            logger.error(f"❌ 获取用户连接失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取用户连接失败")
    
    async def handle_send_to_user(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """向指定用户发送消息"""
        try:
            target_user_id = data.get("target_user_id")
            message_data = data.get("message")
            
            if not target_user_id or not message_data:
                await self.send_message(websocket, "error", "缺少目标用户ID或消息内容")
                return
            
            connection_pool = get_connection_pool_manager()
            sent_count = await connection_pool.send_to_user(target_user_id, message_data)
            
            await self.send_message(websocket, "send_result", {
                "target_user_id": target_user_id,
                "sent_count": sent_count,
                "success": sent_count > 0
            })
            
        except Exception as e:
            logger.error(f"❌ 发送消息到用户失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "发送消息失败")
    
    async def handle_broadcast_message(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """广播消息"""
        try:
            message_data = data.get("message")
            exclude_users = set(data.get("exclude_users", []))
            
            if not message_data:
                await self.send_message(websocket, "error", "缺少消息内容")
                return
            
            connection_pool = get_connection_pool_manager()
            sent_count = await connection_pool.broadcast(message_data, exclude_users)
            
            await self.send_message(websocket, "broadcast_result", {
                "sent_count": sent_count,
                "excluded_users": list(exclude_users)
            })
            
        except Exception as e:
            logger.error(f"❌ 广播消息失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "广播消息失败")
    
    async def handle_get_reconnect_sessions(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取重连会话状态"""
        try:
            reconnect_manager = get_reconnect_manager()
            sessions_status = reconnect_manager.get_all_sessions_status()
            
            await self.send_message(websocket, "reconnect_sessions", {
                "sessions": sessions_status,
                "total_count": len(sessions_status)
            })
            
        except Exception as e:
            logger.error(f"❌ 获取重连会话失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取重连会话失败")
    
    async def handle_force_disconnect(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """强制断开连接"""
        try:
            # 检查权限（这里简单检查，实际应该有更严格的权限控制）
            conn_info = get_connection_pool_manager().get_connection_info(websocket)
            if not conn_info or not conn_info.user_id or not conn_info.user_id.startswith("admin_"):
                await self.send_message(websocket, "error", "权限不足")
                return
            
            target_connection_id = data.get("connection_id")
            reason = data.get("reason", "管理员强制断开")
            
            if not target_connection_id:
                await self.send_message(websocket, "error", "缺少连接ID")
                return
            
            connection_pool = get_connection_pool_manager()
            
            # 查找目标连接
            target_websocket = None
            for ws, info in connection_pool.connections.items():
                if id(ws) == target_connection_id:
                    target_websocket = ws
                    break
            
            if not target_websocket:
                await self.send_message(websocket, "error", "连接不存在")
                return
            
            # 发送断开通知
            disconnect_message = {
                "type": "force_disconnect",
                "data": {
                    "reason": reason,
                    "by_admin": conn_info.user_id
                }
            }
            
            try:
                await target_websocket.send(json.dumps(disconnect_message, ensure_ascii=False))
                await target_websocket.close(code=1000, reason=reason)
            except:
                pass
            
            await self.send_message(websocket, "disconnect_result", {
                "connection_id": target_connection_id,
                "success": True,
                "reason": reason
            })
            
        except Exception as e:
            logger.error(f"❌ 强制断开连接失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "强制断开连接失败")
