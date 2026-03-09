"""
注册处理器
Register Handler
处理用户注册功能
"""

from typing import Dict, Any
import websockets

from app.core import logger
from app.core.exceptions import AuthException
from app.web.message_handlers.base_handler import BaseMessageHandler


class RegisterHandler(BaseMessageHandler):
    """注册处理器"""
    
    async def handle_register(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """处理用户注册"""
        try:
            username = data.get("username", "").strip()
            password = data.get("password", "").strip()
            nickname = data.get("nickname", "").strip()
            
            if not username or not password:
                await self.send_message(websocket, "register_failed", "用户名和密码不能为空")
                return
            
            # 注册用户
            auth_service = self.ws_handler.auth_service
            success, message, user_id = auth_service.register(
                username, password, nickname or username
            )
            
            if success:
                await self.send_message(websocket, "register_success", {
                    "message": message,
                    "user_id": user_id,
                    "username": username,
                    "nickname": nickname
                })
                logger.info(f"用户注册成功: {username}")
            else:
                await self.send_message(websocket, "register_failed", message)
                
        except AuthException as e:
            await self.send_message(websocket, "register_failed", str(e))
        except Exception as e:
            logger.error(f"注册失败: {e}", exc_info=True)
            await self.send_message(websocket, "register_failed", "注册失败")
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理注册相关请求
        
        Args:
            websocket: WebSocket连接
            data: 请求数据
        """
        # 这个方法由具体的消息类型调用对应的处理方法
        pass
