"""
档案处理器
Profile Handler
处理用户档案管理功能（头像、个人信息等）
"""

from typing import Dict, Any
import websockets

from app.core import logger
from app.web.message_handlers.base_handler import BaseMessageHandler


class ProfileHandler(BaseMessageHandler):
    """档案处理器"""
    
    async def handle_get_profile(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取用户档案"""
        try:
            user_id = self.get_user_id(websocket)
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "error", "游客模式无法获取档案")
                return
            
            # 获取用户档案
            profile = self.profile_service.get_profile(user_id)
            
            # 获取用户认证信息
            auth_service = self.ws_handler.auth_service
            user_profile = auth_service.get_user_profile(user_id)
            
            profile_data = {
                "user_id": user_id,
                "avatar": profile.avatar,
                "current_character": profile.current_character,
                "intimacy_level": profile.intimacy_level,
                "tree_hole_mode": profile.tree_hole_mode,
                "proactive_chat_enabled": profile.proactive_chat_enabled,
                "proactive_chat_time": profile.proactive_chat_time,
                "voice_enabled": profile.voice_enabled,
            }
            
            # 添加用户个人信息
            if user_profile:
                profile_data.update({
                    "username": user_profile.get("username", ""),
                    "nickname": user_profile.get("nickname", ""),
                    "birthday": user_profile.get("birthday", ""),
                    "hobby": user_profile.get("hobby", ""),
                    "occupation": user_profile.get("occupation", ""),
                    "city": user_profile.get("city", ""),
                    "bio": user_profile.get("bio", ""),
                })
            
            await self.send_message(websocket, "profile_data", profile_data)
            
        except Exception as e:
            logger.error(f"获取档案失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取档案失败")
    
    async def handle_update_profile(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """更新用户档案"""
        try:
            user_id = self.get_user_id(websocket)
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "error", "游客模式无法更新档案")
                return
            
            # 获取profile数据（前端发送的格式）
            profile_data = data.get("profile", data)  # 兼容两种格式
            
            # 更新用户认证信息
            auth_service = self.ws_handler.auth_service
            profile_updates = {}
            
            # 提取可更新的字段
            updatable_fields = ["nickname", "birthday", "hobby", "occupation", "city", "bio"]
            for field in updatable_fields:
                if field in profile_data:
                    profile_updates[field] = profile_data[field]
            
            if profile_updates:
                success = auth_service.update_user_profile(user_id, profile_updates)
                if success:
                    logger.info(f"用户 {user_id} 档案更新成功: {list(profile_updates.keys())}")
                    await self.send_message(websocket, "profile_updated", "档案更新成功")
                    
                    # 同时发送更新后的档案数据
                    await self.handle_get_profile(websocket, {})
                else:
                    await self.send_message(websocket, "error", "档案更新失败")
            else:
                await self.send_message(websocket, "error", "没有可更新的字段")
                
        except Exception as e:
            logger.error(f"更新档案失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "更新档案失败")
    
    async def handle_update_avatar(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """更新用户头像"""
        try:
            user_id = self.get_user_id(websocket)
            avatar_data = data.get("avatar", "")
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "error", "游客模式无法更新头像")
                return
            
            if not avatar_data:
                await self.send_message(websocket, "error", "头像数据不能为空")
                return
            
            # 更新头像
            success = self.profile_service.update_avatar(user_id, avatar_data)
            
            if success:
                await self.send_message(websocket, "avatar_updated", "头像更新成功")
                logger.info(f"用户 {user_id} 头像更新成功")
            else:
                await self.send_message(websocket, "error", "头像更新失败")
                
        except Exception as e:
            logger.error(f"更新头像失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "更新头像失败")
    
    async def handle_load_history(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """加载历史消息"""
        try:
            user_id = self.get_user_id(websocket)
            limit = data.get("limit", 50)
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "history", [])
                return
            
            # 使用专门的对话历史服务加载消息
            from app.shared.services.chat_history_service import get_chat_history_service
            chat_history_service = get_chat_history_service()
            messages = chat_history_service.load_history(user_id, limit=limit)
            
            # 转换为前端需要的格式
            history_data = []
            for msg in messages:
                history_data.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "metadata": msg.metadata or {}
                })
            
            await self.send_message(websocket, "history", history_data)
            logger.info(f"加载用户 {user_id} 历史消息: {len(history_data)} 条")
            
        except Exception as e:
            logger.error(f"加载历史失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "加载历史失败")
    
    async def handle_reset(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """重置对话"""
        try:
            user_id = self.get_user_id(websocket)
            
            # 清空当前会话的对话历史
            if websocket in self.ws_handler.conversations:
                # 保留系统提示词，清空其他消息
                system_message = self.ws_handler.conversations[websocket][0]
                self.ws_handler.conversations[websocket] = [system_message]
            
            await self.send_message(websocket, "reset_success", "对话已重置")
            logger.info(f"用户 {user_id} 重置对话")
            
        except Exception as e:
            logger.error(f"重置对话失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "重置对话失败")
    
    async def handle_update_voice_settings(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """更新语音设置"""
        try:
            user_id = self.get_user_id(websocket)
            voice_enabled = data.get("voice_enabled", True)
            
            if user_id.startswith("guest_"):
                # 游客模式也允许设置语音，但不保存到档案
                await self.send_message(websocket, "voice_settings_updated", {
                    "voice_enabled": voice_enabled,
                    "message": "语音设置已更新（游客模式不保存）"
                })
                return
            
            # 更新用户档案中的语音设置
            profile_updates = {"voice_enabled": voice_enabled}
            success = self.profile_service.update_profile(user_id, profile_updates)
            
            if success:
                await self.send_message(websocket, "voice_settings_updated", {
                    "voice_enabled": voice_enabled,
                    "message": "语音设置已保存"
                })
                logger.info(f"用户 {user_id} 语音设置更新: {voice_enabled}")
            else:
                await self.send_message(websocket, "error", "语音设置保存失败")
                
        except Exception as e:
            logger.error(f"更新语音设置失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "更新语音设置失败")
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理档案相关请求
        
        Args:
            websocket: WebSocket连接
            data: 请求数据
        """
        # 这个方法由具体的消息类型调用对应的处理方法
        pass
