"""
WebSocket处理器
Refactored WebSocket Handler
模块化的WebSocket连接和消息分发处理
"""

import asyncio
import websockets
import json
import time
from datetime import datetime
from typing import Dict, List

from app.core import settings, logger
from app.core.exceptions import AuthException, ASRError, TTSError, LLMError
from app.shared.services import get_llm_service, get_tts_service  # 移除get_asr_service，改用连接池
from app.shared.services.auth_service import AuthService
from app.business.diary import get_diary_service
from app.business.story import get_story_service
from app.business.chat import get_proactive_chat_service
from app.shared.services.audio_cache_service import get_audio_cache_service
from app.shared.agents import get_memory_agent
from app.prompts.system_prompts import (
    get_character_prompt, 
    get_initial_greeting, 
    get_contextual_greeting,
    get_all_characters
)
# ESP32设备现在使用专用的WebSocket服务器处理
from app.core.connection_pool import get_connection_pool_manager, ConnectionState
from app.core.reconnect_manager import get_reconnect_manager
from app.shared.redis import (
    get_redis_manager, get_user_state_service, get_distributed_pool,
    get_session_store, get_pubsub_service, get_redis_health_monitor
)
from app.shared.redis.user_state_service import UserStatus

# 导入处理器模块
from app.web.message_handlers import TextMessageHandler, VoiceMessageHandler
from app.web.auth import LoginHandler, RegisterHandler, ProfileHandler
from app.web.features import CharacterHandler, MoodHandler, DiaryHandler, StoryHandler
from app.web.handlers.connection_status_handler import ConnectionStatusHandler


class WebSocketHandler:
    """WebSocket连接处理器"""
    
    def __init__(self, *, llm_service=None, diary_service=None, story_service=None, memory_agent=None):
        """初始化处理器
        
        Args:
            llm_service: 可选注入的LLM服务实例，未提供时回退到全局接口
            diary_service: 可选注入的日记服务实例
            story_service: 可选注入的故事服务实例
            memory_agent: 可选注入的记忆Agent实例
        """
        logger.info("🔧 初始化WebSocket处理器...")
        self._injected_llm_service = llm_service
        self._injected_diary_service = diary_service
        self._injected_story_service = story_service
        self._injected_memory_agent = memory_agent
        
        # 初始化各个服务
        self._init_services()
        
        # 存储每个客户端的对话历史（内存中）
        self.conversations: Dict[websockets.WebSocketServerProtocol, List[Dict]] = {}
        
        # 存储WebSocket连接到用户ID的映射
        self.websocket_to_user: Dict[websockets.WebSocketServerProtocol, str] = {}
        
        # 初始化连接池管理器
        self.connection_pool = get_connection_pool_manager()
        self.reconnect_manager = get_reconnect_manager()
        
        # 初始化Redis服务
        self.redis_manager = get_redis_manager()
        self.user_state_service = get_user_state_service()
        self.distributed_pool = get_distributed_pool()
        self.session_store = get_session_store()
        self.pubsub_service = get_pubsub_service()
        self.redis_health_monitor = get_redis_health_monitor()
        
        # 设置连接池回调
        self.connection_pool.on_connection_established = self._on_connection_established
        self.connection_pool.on_connection_lost = self._on_connection_lost
        self.connection_pool.on_connection_limit_exceeded = self._on_connection_limit_exceeded
        
        # 初始化处理器模块
        self._init_handlers()
        
        logger.info("✅ WebSocket处理器初始化完成")
    
    def _ensure_services_initialized(self):
        """确保服务已初始化"""
        try:
            if self.llm_service is None:
                self.llm_service = get_llm_service()
            
            if self.tts_service is None:
                self.tts_service = get_tts_service()
            
            if self.auth_service is None:
                self.auth_service = AuthService()
            
            if self.diary_service is None:
                self.diary_service = get_diary_service()
            
            if self.story_service is None:
                self.story_service = get_story_service()
            
            if self.proactive_chat_service is None:
                self.proactive_chat_service = get_proactive_chat_service()
            
            if self.audio_cache_service is None:
                self.audio_cache_service = get_audio_cache_service()
            
            if self.memory_agent is None:
                self.memory_agent = get_memory_agent()
                
        except Exception as e:
            logger.warning(f"部分服务初始化失败，将在需要时重试: {e}")
    
    def _init_services(self):
        """初始化各种服务（延迟初始化）"""
        # 使用注入的服务或延迟初始化
        if self._injected_llm_service is not None:
            self.llm_service = self._injected_llm_service
        else:
            self.llm_service = None  # 延迟初始化
        
        # ASR服务改用连接池，不再持有单例
        # self.asr_service = get_asr_service()  # 已移除，使用acquire_asr_service上下文管理器
        
        # 其他服务也延迟初始化
        self.tts_service = None
        self.auth_service = None
        
        # 业务服务优先使用构造注入的实例
        if self._injected_diary_service is not None:
            self.diary_service = self._injected_diary_service
        else:
            self.diary_service = None  # 延迟初始化

        if self._injected_story_service is not None:
            self.story_service = self._injected_story_service
        else:
            self.story_service = None  # 延迟初始化

        # 主动服务延迟初始化
        self.proactive_chat_service = None
        self.audio_cache_service = None
        
        # 初始化智能体（记忆Agent）
        if self._injected_memory_agent is not None:
            self.memory_agent = self._injected_memory_agent
        else:
            self.memory_agent = None  # 延迟初始化
    
    def _init_handlers(self):
        """初始化处理器模块"""
        self.text_handler = TextMessageHandler(self)
        self.voice_handler = VoiceMessageHandler(self)
        self.login_handler = LoginHandler(self)
        self.register_handler = RegisterHandler(self)
        self.profile_handler = ProfileHandler(self)
        self.character_handler = CharacterHandler(self)
        self.mood_handler = MoodHandler(self)
        self.diary_handler = DiaryHandler(self)
        self.story_handler = StoryHandler(self)
        self.connection_status_handler = ConnectionStatusHandler(self)
        
        # 消息类型到处理器的映射
        self.message_handlers = {
            # 消息处理
            "text": self.text_handler.handle,
            "text_message": self.text_handler.handle,
            "voice": self.voice_handler.handle,
            "audio_message": self.voice_handler.handle,
            
            # 认证相关
            "login": self.login_handler.handle_login,
            "register": self.register_handler.handle_register,
            "reset_password": self.login_handler.handle_reset_password,
            "session_auth": self.login_handler.handle_session_auth,
            
            # 档案管理
            "load_history": self.profile_handler.handle_load_history,
            "get_profile": self.profile_handler.handle_get_profile,
            "update_profile": self.profile_handler.handle_update_profile,
            "update_avatar": self.profile_handler.handle_update_avatar,
            "reset": self.profile_handler.handle_reset,
            
            # 角色和功能
            "switch_character": self.character_handler.handle_switch_character,
            "get_characters": self.character_handler.handle_get_characters,
            "toggle_tree_hole_mode": self.character_handler.handle_toggle_tree_hole_mode,
            "update_proactive_settings": self.character_handler.handle_update_proactive_settings,
            "check_proactive_chat": self.character_handler.handle_check_proactive_chat,
            
            # 心理健康功能
            "mood_checkin": self.mood_handler.handle_mood_checkin,
            "get_mood_history": self.mood_handler.handle_get_mood_history,
            "get_mood_statistics": self.mood_handler.handle_get_mood_statistics,
            "generate_diary": self.diary_handler.handle_generate_diary,
            "get_diary": self.diary_handler.handle_get_diary,
            "get_diary_list": self.diary_handler.handle_get_diary_list,
            # 睡前故事功能
            "get_story_types": self.story_handler.handle_get_story_types,
            "get_story_themes": self.story_handler.handle_get_story_themes,
            "get_story_recommendation": self.story_handler.handle_get_story_recommendation,
            "get_bedtime_story": self.story_handler.handle_get_bedtime_story,
            "repeat_story": self.story_handler.handle_repeat_story,
            "change_story": self.story_handler.handle_change_story,
            "get_grouped_history": self._handle_get_grouped_history,
            "get_history_by_date": self._handle_get_history_by_date,
            "search_messages": self._handle_search_messages,
            
            # 设置相关
            "update_voice_settings": self.profile_handler.handle_update_voice_settings,
            
            # 连接状态管理
            "get_connection_status": self.connection_status_handler.handle_get_connection_status,
            "get_pool_metrics": self.connection_status_handler.handle_get_pool_metrics,
            "get_user_connections": self.connection_status_handler.handle_get_user_connections,
            "send_to_user": self.connection_status_handler.handle_send_to_user,
            "broadcast_message": self.connection_status_handler.handle_broadcast_message,
            "get_reconnect_sessions": self.connection_status_handler.handle_get_reconnect_sessions,
            "force_disconnect": self.connection_status_handler.handle_force_disconnect,
            
            # ESP32设备消息（作为后备处理）
            "listen": self._handle_esp32_fallback,
            "start_listening": self._handle_esp32_fallback,
            "stop_listening": self._handle_esp32_fallback,
            "abort_speaking": self._handle_esp32_fallback,
            "hello": self._handle_esp32_fallback,
            
            # 其他
            "ping": self._handle_ping,
        }
    
    async def start(self):
        """启动WebSocket服务器"""
        # 确保服务已初始化
        self._ensure_services_initialized()
        
        # 启动连接池管理器
        await self.connection_pool.start()
        await self.reconnect_manager.start()
        
        async with websockets.serve(
            self.handle_client,
            settings.HOST,
            settings.PORT,
            max_size=10 * 1024 * 1024,  # 增加到10MB
            max_queue=32
        ):
            logger.info(f"🚀 WebSocket服务器启动成功: {settings.HOST}:{settings.PORT}")
            logger.info(f"📊 连接池配置: 最大连接数={settings.MAX_CONNECTIONS}, 单IP限制={settings.MAX_CONNECTIONS_PER_IP}")
            await asyncio.Future()  # 永久运行
    
    async def handle_client(self, websocket, path=None):
        """处理客户端连接"""
        client_id = id(websocket)
        client_addr = websocket.remote_address
        client_ip = client_addr[0] if client_addr else "unknown"
        
        logger.info(f"🔗 新客户端连接: {client_addr} (ID: {client_id})")
        
        # 检查连接池是否可以接受新连接
        can_accept, reason = self.connection_pool.can_accept_connection(client_ip)
        if not can_accept:
            logger.warning(f"❌ 拒绝连接 {client_ip}: {reason}")
            await websocket.close(code=1013, reason=reason)
            return
        
        # 注意：ESP32设备应该连接到专用端口 (PORT+1)
        # 如果ESP32设备错误连接到Web端口，给出提示
        logger.debug(f"Web客户端连接: {client_addr}")
        
        # 添加Web客户端连接到连接池
        success = await self.connection_pool.add_connection(
            websocket, 
            client_type="web",
            metadata={"client_id": client_id}
        )
        
        if not success:
            await websocket.close(code=1013, reason="连接池已满")
            return
        
        # Web客户端处理
        try:
            async for message in websocket:
                # 更新连接活动时间
                self.connection_pool.update_connection_activity(websocket)
                
                # 处理pong消息
                try:
                    data = json.loads(message)
                    if data.get("type") == "pong":
                        await self.connection_pool.handle_pong(websocket)
                        continue
                except:
                    pass
                
                await self.process_message(websocket, message)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"📴 客户端断开连接: {client_addr} (ID: {client_id})")
        except Exception as e:
            logger.error(f"❌ 处理客户端连接时出错: {e}", exc_info=True)
        finally:
            # 从连接池移除连接
            await self.connection_pool.remove_connection(websocket, "client_disconnected")
            # 清理资源
            self._cleanup_client(websocket, client_id)
    
    
    def _cleanup_client(self, websocket, client_id):
        """清理客户端资源"""
        if websocket in self.conversations:
            del self.conversations[websocket]
        if websocket in self.websocket_to_user:
            del self.websocket_to_user[websocket]
        logger.debug(f"🧹 已清理客户端资源: {client_id}")
    
    async def _on_connection_established(self, websocket, conn_info):
        """连接建立回调"""
        logger.info(f"🎉 连接已建立: {conn_info.client_ip} (类型: {conn_info.client_type})")
        
        # 更新分布式连接池统计
        if self.redis_manager.is_connected():
            try:
                current_count = len(self.connection_pool.connections)
                await self.distributed_pool.update_connection_count(current_count)
            except Exception as e:
                logger.warning(f"⚠️ 更新分布式连接池失败: {e}")
        
        # 发送连接成功消息
        welcome_message = {
            "type": "connection_established",
            "data": {
                "message": "连接已建立",
                "server_time": datetime.now().isoformat(),
                "connection_id": id(websocket),
                "redis_enabled": self.redis_manager.is_connected()
            }
        }
        try:
            await websocket.send(json.dumps(welcome_message, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"⚠️ 发送欢迎消息失败: {e}")
    
    async def _on_connection_lost(self, websocket, conn_info, reason):
        """连接丢失回调"""
        logger.info(f"💔 连接已丢失: {conn_info.client_ip} (用户: {conn_info.user_id}, 原因: {reason})")
        
        # 更新用户状态
        if conn_info.user_id and self.redis_manager.is_connected():
            try:
                await self.user_state_service.user_disconnected(conn_info.user_id)
                
                # 广播连接事件
                await self.pubsub_service.broadcast_connection_event(
                    "disconnected", 
                    conn_info.user_id, 
                    {
                        "client_ip": conn_info.client_ip,
                        "client_type": conn_info.client_type,
                        "reason": reason
                    }
                )
            except Exception as e:
                logger.warning(f"⚠️ 更新用户断开状态失败: {e}")
        
        # 更新分布式连接池统计
        if self.redis_manager.is_connected():
            try:
                current_count = len(self.connection_pool.connections)
                await self.distributed_pool.update_connection_count(current_count)
            except Exception as e:
                logger.warning(f"⚠️ 更新分布式连接池失败: {e}")
    
    async def _on_connection_limit_exceeded(self, websocket, reason):
        """连接限制超出回调"""
        logger.warning(f"🚫 连接被拒绝: {reason}")
        
        # 发送拒绝连接消息
        reject_message = {
            "type": "connection_rejected",
            "data": {
                "reason": reason,
                "retry_after": 60  # 建议60秒后重试
            }
        }
        try:
            await websocket.send(json.dumps(reject_message, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"⚠️ 发送拒绝消息失败: {e}")
    
    async def process_message(self, websocket, message):
        """处理接收到的消息"""
        try:
            # 检查消息类型：二进制数据 vs 文本数据
            if isinstance(message, bytes):
                logger.debug(f"收到二进制消息，长度: {len(message)} bytes")
                # 二进制消息可能是音频数据，不应该用JSON解析
                logger.warning("收到二进制消息，但当前处理器只支持JSON文本消息")
                return
            
            # 确保消息是字符串类型
            if not isinstance(message, str):
                logger.error(f"消息类型错误: {type(message)}")
                await self.send_message(websocket, "error", "消息类型错误")
                return
            
            # 检查消息编码和内容
            try:
                # 尝试确保消息是有效的UTF-8编码
                message_bytes = message.encode('utf-8')
                message = message_bytes.decode('utf-8')
            except UnicodeError as e:
                logger.error(f"消息编码错误: {e}")
                await self.send_message(websocket, "error", "消息编码错误")
                return
            
            # 检查消息是否为空或过短
            if not message.strip():
                logger.warning("收到空消息")
                return
            
            # 记录原始消息用于调试
            logger.debug(f"原始消息内容: {message[:200]}...")  # 只记录前200字符
            
            # 解析JSON
            data = json.loads(message)
            message_type = data.get("type")
            
            logger.debug(f"收到消息类型: {message_type}")
            
            # 查找对应的处理器
            handler = self.message_handlers.get(message_type)
            if handler:
                await handler(websocket, data)
            else:
                logger.warning(f"未知消息类型: {message_type}")
                await self.send_message(websocket, "error", f"未知消息类型: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            logger.error(f"问题消息内容: {repr(message[:100])}")  # 显示消息的原始表示
            await self.send_message(websocket, "error", "无效的JSON格式")
        except UnicodeDecodeError as e:
            logger.error(f"Unicode解码失败: {e}")
            logger.error(f"问题消息类型: {type(message)}")
            await self.send_message(websocket, "error", "消息编码错误")
        except Exception as e:
            logger.error(f"处理消息时出错: {e}", exc_info=True)
            logger.error(f"问题消息类型: {type(message)}, 内容: {repr(message[:100]) if hasattr(message, '__getitem__') else str(message)}")
            await self.send_message(websocket, "error", "服务器内部错误")
    
    async def send_message(self, websocket, message_type: str, data):
        """发送消息到客户端"""
        try:
            message = {
                "type": message_type,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(message, ensure_ascii=False))
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
    
    # 以下是原有的辅助方法，保持不变
    def _init_conversation(self, websocket, user_id: str = None) -> List[Dict]:
        """初始化对话历史（保持原有逻辑）"""
        # 这里保持原有的_init_conversation方法逻辑
        if not user_id:
            user_id = f"guest_{id(websocket)}"
        
        self.websocket_to_user[websocket] = user_id
        # 使用 memory_agent 的 ProfileStore
        profile_data = self.memory_agent.memory.pr_store.get_profile(user_id)
        self.memory_agent.memory.pr_store.update_activity(user_id)
        
        character_id = profile_data.get("current_character", "xiaonuan")
        system_prompt = get_character_prompt(character_id)
        logger.info(f"🎭 用户 {user_id} 初始化对话，使用角色: {character_id}")
        
        # 添加用户个人信息到系统提示词（如果是注册用户）
        if not user_id.startswith("guest_"):
            try:
                user_profile = self.auth_service.get_user_profile(user_id)
                if user_profile:
                    profile_info = self._format_user_profile_info(user_profile)
                    if profile_info:
                        system_prompt += profile_info
                        logger.info(f"✅ 已将用户 {user_id} 的个人信息添加到系统提示词中")
            except Exception as e:
                logger.warning(f"⚠️ 获取用户个人信息失败: {e}")
        
        conversation = [{"role": "system", "content": system_prompt}]
        
        # 加载历史消息（如果是注册用户）- 使用对话历史服务
        if not user_id.startswith("guest_"):
            try:
                from app.shared.services.chat_history_service import get_chat_history_service
                chat_history_service = get_chat_history_service()
                logger.info(f"🔍 开始加载用户 {user_id} 的历史消息...")
                recent_context = chat_history_service.get_recent_context(user_id, max_messages=10)
                conversation.extend(recent_context)
                logger.info(f"✅ 加载用户 {user_id} 的历史消息: {len(recent_context)} 条")
                if recent_context:
                    logger.info(f"📝 历史消息预览: {recent_context[0]['role']}: {recent_context[0]['content'][:50]}...")
            except Exception as e:
                logger.error(f"❌ 加载历史消息失败: {e}", exc_info=True)
        
        return conversation
    
    def _format_user_profile_info(self, user_profile: dict) -> str:
        """格式化用户个人信息"""
        profile_info = []
        
        if user_profile.get('nickname'):
            profile_info.append(f"昵称：{user_profile['nickname']}")
        
        if user_profile.get('birthday'):
            try:
                birthday = datetime.strptime(user_profile['birthday'], '%Y-%m-%d')
                today = datetime.now()
                age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
                
                this_year_birthday = birthday.replace(year=today.year)
                if this_year_birthday < today:
                    this_year_birthday = birthday.replace(year=today.year + 1)
                days_until_birthday = (this_year_birthday - today).days
                
                birthday_info = f"生日：{user_profile['birthday']}（{age}岁）"
                if days_until_birthday <= 7:
                    birthday_info += f"，距离生日还有{days_until_birthday}天"
                profile_info.append(birthday_info)
            except:
                profile_info.append(f"生日：{user_profile['birthday']}")
        
        for field, label in [('hobby', '爱好'), ('occupation', '职业/学校'), 
                           ('city', '所在城市'), ('bio', '个性签名')]:
            if user_profile.get(field):
                profile_info.append(f"{label}：{user_profile[field]}")
        
        if profile_info:
            user_info_text = "\n\n【用户个人信息】\n" + "\n".join(profile_info)
            user_info_text += "\n\n💡 使用原则：\n"
            user_info_text += "- 可以用昵称称呼对方（自然、不刻意）\n"
            user_info_text += "- 根据年龄调整对话风格，但不要频繁提及年龄\n"
            user_info_text += "- 只在用户主动谈及相关话题时，才结合个人信息回答\n"
            user_info_text += "- 例如：用户说到爱好时才提及他的爱好；聊到天气时才联系所在城市\n"
            user_info_text += "- 不要在每次对话中都刻意提及这些信息，保持对话自然\n"
            return user_info_text
        
        return ""
    
    def _add_message(self, websocket, role: str, content: str, metadata: dict = None, skip_save: bool = False):
        """添加消息到对话历史（内存+持久化）"""
        if websocket not in self.conversations:
            self.conversations[websocket] = self._init_conversation(websocket)
        
        self.conversations[websocket].append({
            "role": role,
            "content": content
        })
        
        # 保存到对话历史存储（与记忆智能体分离）
        user_id = self.websocket_to_user.get(websocket)
        if user_id and not user_id.startswith("guest_") and not skip_save:
            timestamp = datetime.now().isoformat()
            # 使用专门的对话历史服务保存消息
            from app.shared.services.chat_history_service import get_chat_history_service
            chat_history_service = get_chat_history_service()
            chat_history_service.save_message(user_id, role, content, timestamp, metadata)
        
        # 限制历史长度
        if len(self.conversations[websocket]) > 21:
            self.conversations[websocket] = (
                [self.conversations[websocket][0]] +
                self.conversations[websocket][-20:]
            )
    
    def _calculate_intimacy_gain(self, user_message: str, assistant_response: str, is_voice: bool = False) -> int:
        """计算本次对话应该增加的亲密度点数（保持原有逻辑）"""
        points = 1  # 基础对话分
        
        if is_voice:
            points += 1
        
        if len(user_message) > 50:
            points += 1
        
        # 情感表达奖励
        emotional_keywords = [
            "喜欢", "爱", "想你", "想念", "思念", "开心", "高兴", 
            "难过", "伤心", "害怕", "担心", "感谢", "谢谢",
            "对不起", "抱歉", "生气", "讨厌", "在乎", "关心"
        ]
        if any(keyword in user_message for keyword in emotional_keywords):
            points += 1
        
        # 生活分享奖励
        sharing_keywords = [
            "今天", "明天", "昨天", "刚才", "刚刚",
            "工作", "上班", "下班", "学校", "考试", "作业",
            "吃饭", "睡觉", "起床", "累", "忙", "休息"
        ]
        if any(keyword in user_message for keyword in sharing_keywords):
            points += 1
        
        # 主动关心奖励
        care_keywords = ["你呢", "你怎么样", "你好吗", "你在做什么", "你在干嘛"]
        if any(keyword in user_message for keyword in care_keywords):
            points += 1
        
        # 时段奖励
        current_hour = datetime.now().hour
        if current_hour < 6 or current_hour >= 23 or 6 <= current_hour < 8:
            points += 1
        
        # 回复质量奖励
        if len(assistant_response) > 100:
            points += 1
        
        return points
    
    # 临时处理器方法（待迁移到专门的处理器）
    async def _handle_ping(self, websocket, data):
        """处理ping消息"""
        await self.send_message(websocket, "pong", "pong")
    
    async def _handle_get_grouped_history(self, websocket, data):
        """获取分组历史（待实现）"""
        await self.send_message(websocket, "error", "功能开发中")
    
    async def _handle_get_history_by_date(self, websocket, data):
        """按日期获取历史（待实现）"""
        await self.send_message(websocket, "error", "功能开发中")
    
    async def _handle_search_messages(self, websocket, data):
        """搜索消息（待实现）"""
        await self.send_message(websocket, "error", "功能开发中")
    
    async def _handle_esp32_fallback(self, websocket, data):
        """ESP32设备消息后备处理器"""
        message_type = data.get("type")
        logger.warning(f"⚠️ ESP32消息被错误路由到Web处理器: {message_type}")
        logger.info("🔄 尝试将连接重新路由到ESP32适配器...")
        
        try:
            # 生成设备ID
            device_id = f"esp32_{websocket.remote_address[0]}_{int(time.time())}"
            client_id = "esp32_client"
            
            # 记录原始消息
            logger.info(f"🔌 后备检测到ESP32设备，消息类型: {message_type}")
            
            # 发送错误消息告知客户端需要重新连接
            await self.send_message(websocket, "error", {
                "message": "设备类型检测错误，请重新连接",
                "code": "DEVICE_DETECTION_ERROR",
                "device_type": "esp32"
            })
            
            # 关闭当前连接，让ESP32设备重新连接
            await websocket.close(code=1000, reason="Device type detection error")
            
        except Exception as e:
            logger.error(f"❌ ESP32后备处理失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "设备处理失败")
