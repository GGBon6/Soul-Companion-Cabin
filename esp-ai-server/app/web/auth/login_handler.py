"""
登录处理器
Login Handler
处理用户登录、密码重置、会话认证等功能
"""

import asyncio
from datetime import datetime
from typing import Dict, Any
import websockets

from app.core import logger
from app.core.exceptions import AuthException
from app.prompts.system_prompts import get_initial_greeting
from app.shared.services.tts_service import get_character_voice
from app.web.message_handlers.base_handler import BaseMessageHandler


class LoginHandler(BaseMessageHandler):
    """登录处理器"""
    
    async def handle_login(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """处理用户登录"""
        try:
            username = data.get("username", "").strip()
            password = data.get("password", "").strip()
            
            if not username or not password:
                await self.send_message(websocket, "login_failed", "用户名和密码不能为空")
                return
            
            # 验证登录
            auth_service = self.ws_handler.auth_service
            success, message, user_info = auth_service.login(username, password)
            
            if success:
                user_id = user_info["user_id"]
                # 重新初始化对话（加载该用户的历史）
                self.ws_handler.conversations[websocket] = self.ws_handler._init_conversation(websocket, user_id)
                
                # 更新连接池中的用户ID
                self.ws_handler.connection_pool.update_user_id(websocket, user_id)
                
                # 更新Redis中的用户状态
                if self.ws_handler.redis_manager.is_connected():
                    try:
                        from app.shared.redis.user_state_service import UserStatus
                        await self.ws_handler.user_state_service.user_connected(
                            user_id, 
                            {
                                "client_type": "web",
                                "login_time": datetime.now().isoformat(),
                                "user_agent": user_info.get("user_agent", ""),
                                "nickname": user_info["nickname"]
                            }
                        )
                        
                        # 创建分布式会话
                        session = await self.ws_handler.session_store.create_session(
                            user_id,
                            {
                                "username": username,
                                "nickname": user_info["nickname"],
                                "login_time": datetime.now().isoformat(),
                                "client_info": {
                                    "type": "web",
                                    "connection_id": id(websocket)
                                }
                            }
                        )
                        
                        # 广播用户连接事件
                        await self.ws_handler.pubsub_service.broadcast_connection_event(
                            "connected",
                            user_id,
                            {
                                "username": username,
                                "nickname": user_info["nickname"],
                                "client_type": "web",
                                "session_id": session.session_id
                            }
                        )
                        
                        logger.info(f"✅ 用户状态已同步到Redis: {user_id}")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ 同步用户状态到Redis失败: {e}")
                
                # 获取用户档案信息（包括头像）
                profile = self.profile_service.get_profile(user_id)
                
                await self.send_message(websocket, "login_success", {
                    "message": message,
                    "user_id": user_id,
                    "username": username,
                    "nickname": user_info["nickname"],
                    "avatar": profile.avatar
                })
                logger.info(f"用户登录成功: {username}")
            else:
                await self.send_message(websocket, "login_failed", message)
                
        except AuthException as e:
            await self.send_message(websocket, "login_failed", str(e))
        except Exception as e:
            logger.error(f"登录失败: {e}", exc_info=True)
            await self.send_message(websocket, "login_failed", "登录失败")
    
    async def handle_reset_password(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """处理密码重置"""
        try:
            username = data.get("username", "").strip()
            new_password = data.get("new_password", "").strip()
            
            if not username or not new_password:
                await self.send_message(websocket, "reset_password_failed", "用户名和新密码不能为空")
                return
            
            # 重置密码
            auth_service = self.ws_handler.auth_service
            success, message = auth_service.reset_password(username, new_password)
            
            if success:
                await self.send_message(websocket, "reset_password_success", {
                    "message": message,
                    "username": username
                })
                logger.info(f"密码重置成功: {username}")
            else:
                await self.send_message(websocket, "reset_password_failed", message)
                
        except Exception as e:
            logger.error(f"密码重置失败: {e}", exc_info=True)
            await self.send_message(websocket, "reset_password_failed", f"密码重置失败: {str(e)}")
    
    async def handle_session_auth(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """处理会话认证"""
        user_id = data.get("user_id")
        username = data.get("username")
        
        if user_id:
            # 存储用户ID映射
            self.ws_handler.websocket_to_user[websocket] = user_id
            
            # 获取用户档案
            profile = self.profile_service.get_profile(user_id)
            
            # 重新初始化对话
            self.ws_handler.conversations[websocket] = self.ws_handler._init_conversation(websocket, user_id)
            logger.info(f"会话认证成功: {username} ({user_id}), 当前角色: {profile.current_character}")
            
            # 返回用户档案信息
            await self.send_message(websocket, "profile_sync", {
                "current_character": profile.current_character,
                "tree_hole_mode": profile.tree_hole_mode,
                "proactive_chat_enabled": profile.proactive_chat_enabled,
                "proactive_chat_time": profile.proactive_chat_time
            })

            # 发送历史消息给前端
            await self._send_history_messages(websocket, user_id)

            # 判断是新用户还是老用户，发送不同的问候
            await self._send_greeting_if_needed(websocket, user_id, username, profile)
    
    async def _send_history_messages(self, websocket: websockets.WebSocketServerProtocol, user_id: str):
        """发送历史消息给前端"""
        try:
            # 加载历史消息
            messages = self.history_service.load_history(user_id, limit=50)
            
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
            logger.error(f"发送历史消息失败: {e}", exc_info=True)
    
    async def _send_greeting_if_needed(self, websocket: websockets.WebSocketServerProtocol, 
                                     user_id: str, username: str, profile):
        """为新用户发送问候消息"""
        try:
            # 加载最近的几条历史消息
            history = self.history_service.load_history(user_id, limit=5)
            
            if not history:
                # 新用户：发送首次问候
                greeting = get_initial_greeting(profile.current_character)
                logger.info(f"👋 新用户 {username}，发送首次问候: {greeting[:30]}...")
                
                # 获取用户角色对应的声音
                character_voice = get_character_voice(profile.current_character)
                
                # 尝试从缓存获取音频
                audio_cache_service = self.ws_handler.audio_cache_service
                audio_base64 = audio_cache_service.get_cached_audio(greeting, character_voice)
                
                if audio_base64:
                    # 使用缓存的音频，立即发送
                    logger.info(f"✅ 使用缓存音频，立即发送问候")
                    await self.send_message(websocket, "audio", {
                        "text": greeting,
                        "audio": audio_base64
                    })
                else:
                    # 缓存未命中，先发文字，后台生成语音
                    logger.warning(f"⚠️ 音频缓存未命中，先发送文字消息")
                    await self.send_message(websocket, "assistant_message", greeting)
                    
                    # 后台生成语音并缓存
                    async def generate_voice_background():
                        try:
                            audio_b64 = await audio_cache_service.cache_audio(greeting, character_voice)
                            if audio_b64:
                                await self.send_message(websocket, "audio", {
                                    "text": greeting,
                                    "audio": audio_b64,
                                    "is_delayed": True
                                })
                            return audio_b64
                        except Exception as e:
                            logger.error(f"后台语音生成失败: {e}")
                            return None
                    
                    voice_task = asyncio.create_task(generate_voice_background())
                    
                    # 后台保存
                    async def save_with_audio():
                        audio_b64 = await voice_task
                        metadata = {"is_voice_response": True}
                        if audio_b64:
                            metadata["audio_base64"] = audio_b64
                        self.add_message(websocket, "assistant", greeting, metadata=metadata)
                    
                    asyncio.create_task(save_with_audio())
                    return
                
                # 保存问候到聊天记录
                metadata = {"is_voice_response": True}
                if audio_base64:
                    metadata["audio_base64"] = audio_base64
                self.add_message(websocket, "assistant", greeting, metadata=metadata)
            else:
                # 老用户：发送回归问候
                from app.prompts.system_prompts import get_contextual_greeting
                # 获取最后一条用户消息作为上下文
                last_user_msg = None
                if history:
                    for msg in reversed(history):
                        # MessageAdapter 对象使用属性访问，不是字典
                        if hasattr(msg, 'role') and msg.role == 'user':
                            last_user_msg = getattr(msg, 'content', '')
                            break
                        # 兼容字典格式
                        elif isinstance(msg, dict) and msg.get('role') == 'user':
                            last_user_msg = msg.get('content', '')
                            break
                
                greeting = get_contextual_greeting(profile.current_character, last_user_msg)
                if not greeting:
                    # 如果contextual greeting为空，使用默认问候
                    greeting = get_initial_greeting(profile.current_character)
                
                if greeting:
                    logger.info(f"👋 老用户 {username}，发送回归问候: {greeting[:30]}...")
                    
                    # 为老用户问候也生成语音
                    try:
                        from app.shared.services.tts_service import get_tts_service
                        tts_service = get_tts_service()
                        
                        # 获取角色对应的声音
                        voice_name = get_character_voice(profile.current_character)
                        
                        # 生成语音
                        audio_bytes = await tts_service.synthesize_async(greeting, voice_name)
                        
                        # 转换为base64
                        import base64
                        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                        
                        if audio_base64:
                            # 发送带语音的消息
                            await self.send_message(websocket, "audio", {
                                "text": greeting,
                                "audio": audio_base64
                            })
                            
                            # 保存带语音元数据的消息
                            metadata = {"is_voice_response": True, "audio_base64": audio_base64}
                            self.add_message(websocket, "assistant", greeting, metadata=metadata)
                        else:
                            # 语音生成失败，发送纯文本
                            await self.send_message(websocket, "assistant_message", greeting)
                            self.add_message(websocket, "assistant", greeting)
                            
                    except Exception as e:
                        logger.error(f"老用户问候语音生成失败: {e}")
                        # 语音生成失败，发送纯文本
                        await self.send_message(websocket, "assistant_message", greeting)
                        self.add_message(websocket, "assistant", greeting)
                else:
                    logger.warning(f"⚠️ 无法生成问候语，角色: {profile.current_character}")
                    
        except Exception as e:
            logger.error(f"发送问候消息失败: {e}", exc_info=True)
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理认证相关请求
        
        Args:
            websocket: WebSocket连接
            data: 请求数据
        """
        # 这个方法由具体的消息类型调用对应的处理方法
        pass
