"""
ESP32会话管理器
ESP32 Session Manager
管理ESP32设备的会话状态、上下文和持久化
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

from app.shared.services.chat_history_service import get_chat_history_service
from app.devices.config.youth_psychology_config import get_youth_psychology_config


class SessionState(Enum):
    """会话状态"""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    IDLE = "idle"
    EXPIRED = "expired"
    TERMINATED = "terminated"


@dataclass
class AudioContext:
    """音频上下文"""
    sample_rate: int = 16000
    format: str = "opus"
    channels: int = 1
    frame_duration: int = 60
    last_audio_time: float = field(default_factory=time.time)
    total_audio_frames: int = 0
    audio_quality_score: float = 1.0


@dataclass
class ConversationContext:
    """对话上下文"""
    dialogue_history: List[Dict[str, Any]] = field(default_factory=list)
    current_topic: Optional[str] = None
    emotional_state: Optional[str] = None
    risk_level: str = "low"
    last_intent: Optional[str] = None
    conversation_count: int = 0
    total_interactions: int = 0


@dataclass
class UserProfile:
    """用户档案"""
    user_id: str
    device_id: str
    age: Optional[int] = None
    grade: Optional[str] = None
    concerns: List[str] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class ESP32Session:
    """ESP32会话"""
    session_id: str
    device_id: str
    user_id: str
    state: SessionState = SessionState.INITIALIZING
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    
    # 上下文信息
    audio_context: AudioContext = field(default_factory=AudioContext)
    conversation_context: ConversationContext = field(default_factory=ConversationContext)
    user_profile: Optional[UserProfile] = None
    
    # 会话配置
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_activity(self):
        """更新活动时间"""
        self.last_activity = time.time()
    
    def is_expired(self, timeout: float = 1800) -> bool:
        """检查会话是否过期"""
        if self.expires_at:
            return time.time() > self.expires_at
        return (time.time() - self.last_activity) > timeout
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class ESP32SessionManager:
    """ESP32会话管理器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.logger = logging.getLogger(__name__)
        self.config = config or self._get_default_config()
        
        # 会话存储
        self.sessions: Dict[str, ESP32Session] = {}
        self.device_sessions: Dict[str, str] = {}  # device_id -> session_id
        self.user_sessions: Dict[str, List[str]] = {}  # user_id -> [session_ids]
        
        # 服务依赖
        self.chat_history_service = get_chat_history_service()
        self.psychology_config = get_youth_psychology_config()
        
        # 配置参数
        self.session_timeout = self.config.get("session_timeout", 1800)  # 30分钟
        self.max_sessions = self.config.get("max_sessions", 10000)
        self.cleanup_interval = self.config.get("cleanup_interval", 300)  # 5分钟
        self.auto_save = self.config.get("auto_save", True)
        self.max_history_length = self.psychology_config.get_max_history_length()
        
        # 启动清理任务
        self.cleanup_task = None
        self._start_cleanup_task()
        
        self.logger.info(f"ESP32会话管理器初始化完成，会话超时: {self.session_timeout}秒")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "session_timeout": 1800,
            "max_sessions": 10000,
            "cleanup_interval": 300,
            "auto_save": True,
            "max_history_length": 50,
            "persistence": {
                "enabled": True,
                "save_interval": 60,
                "compress": True
            }
        }
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
    
    async def create_session(self, device_id: str, user_id: Optional[str] = None, 
                           device_info: Optional[Dict[str, Any]] = None) -> ESP32Session:
        """创建新会话"""
        try:
            # 检查会话数量限制
            if len(self.sessions) >= self.max_sessions:
                await self._cleanup_expired_sessions()
                if len(self.sessions) >= self.max_sessions:
                    raise RuntimeError("会话数量已达上限")
            
            # 生成会话ID
            session_id = str(uuid.uuid4())
            user_id = user_id or device_id
            
            # 关闭设备的旧会话
            await self._close_device_sessions(device_id)
            
            # 创建会话
            session = ESP32Session(
                session_id=session_id,
                device_id=device_id,
                user_id=user_id,
                state=SessionState.INITIALIZING
            )
            
            # 设置过期时间
            session.expires_at = time.time() + self.session_timeout
            
            # 初始化用户档案
            if device_info:
                session.user_profile = UserProfile(
                    user_id=user_id,
                    device_id=device_id,
                    age=device_info.get("age"),
                    grade=device_info.get("grade"),
                    concerns=device_info.get("concerns", []),
                    preferences=device_info.get("preferences", {})
                )
            
            # 初始化音频上下文
            if device_info and "audio_params" in device_info:
                audio_params = device_info["audio_params"]
                session.audio_context = AudioContext(
                    sample_rate=audio_params.get("sample_rate", 16000),
                    format=audio_params.get("format", "opus"),
                    channels=audio_params.get("channels", 1),
                    frame_duration=audio_params.get("frame_duration", 60)
                )
            
            # 加载历史对话
            await self._load_conversation_history(session)
            
            # 注册会话
            self.sessions[session_id] = session
            self.device_sessions[device_id] = session_id
            
            # 注册用户会话
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = []
            self.user_sessions[user_id].append(session_id)
            
            # 激活会话
            session.state = SessionState.ACTIVE
            
            self.logger.info(f"创建会话: {session_id[:8]}... (设备: {device_id}, 用户: {user_id})")
            
            return session
            
        except Exception as e:
            self.logger.error(f"创建会话失败: {e}")
            raise
    
    async def get_session(self, session_id: str) -> Optional[ESP32Session]:
        """获取会话"""
        session = self.sessions.get(session_id)
        if session:
            session.update_activity()
            return session
        return None
    
    async def get_device_session(self, device_id: str) -> Optional[ESP32Session]:
        """获取设备会话"""
        session_id = self.device_sessions.get(device_id)
        if session_id:
            return await self.get_session(session_id)
        return None
    
    async def update_session_state(self, session_id: str, state: SessionState) -> bool:
        """更新会话状态"""
        session = self.sessions.get(session_id)
        if session:
            session.state = state
            session.update_activity()
            
            if self.auto_save:
                await self._save_session(session)
            
            return True
        return False
    
    async def add_conversation_message(self, session_id: str, role: str, content: str, 
                                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        """添加对话消息"""
        try:
            session = self.sessions.get(session_id)
            if not session:
                return False
            
            # 创建消息
            message = {
                "role": role,
                "content": content,
                "timestamp": time.time(),
                "metadata": metadata or {}
            }
            
            # 添加到会话历史
            session.conversation_context.dialogue_history.append(message)
            session.conversation_context.total_interactions += 1
            
            # 限制历史长度
            if len(session.conversation_context.dialogue_history) > self.max_history_length:
                session.conversation_context.dialogue_history = \
                    session.conversation_context.dialogue_history[-self.max_history_length:]
            
            # 更新统计
            if role == "user":
                session.conversation_context.conversation_count += 1
            
            # 持久化保存
            if self.auto_save:
                await self._save_conversation_message(session, message)
            
            session.update_activity()
            
            return True
            
        except Exception as e:
            self.logger.error(f"添加对话消息失败: {e}")
            return False
    
    async def update_emotional_state(self, session_id: str, emotional_state: str, 
                                   risk_level: str = "low") -> bool:
        """更新情感状态"""
        session = self.sessions.get(session_id)
        if session:
            session.conversation_context.emotional_state = emotional_state
            session.conversation_context.risk_level = risk_level
            session.update_activity()
            
            if self.auto_save:
                await self._save_session(session)
            
            return True
        return False
    
    async def update_audio_context(self, session_id: str, audio_data: bytes, 
                                 quality_score: Optional[float] = None) -> bool:
        """更新音频上下文"""
        session = self.sessions.get(session_id)
        if session:
            session.audio_context.last_audio_time = time.time()
            session.audio_context.total_audio_frames += 1
            
            if quality_score is not None:
                # 使用移动平均更新音频质量分数
                current_score = session.audio_context.audio_quality_score
                session.audio_context.audio_quality_score = \
                    0.9 * current_score + 0.1 * quality_score
            
            session.update_activity()
            return True
        return False
    
    async def pause_session(self, session_id: str) -> bool:
        """暂停会话"""
        return await self.update_session_state(session_id, SessionState.PAUSED)
    
    async def resume_session(self, session_id: str) -> bool:
        """恢复会话"""
        return await self.update_session_state(session_id, SessionState.ACTIVE)
    
    async def close_session(self, session_id: str, reason: str = "normal") -> bool:
        """关闭会话"""
        try:
            session = self.sessions.get(session_id)
            if not session:
                return False
            
            # 更新状态
            session.state = SessionState.TERMINATED
            session.metadata["close_reason"] = reason
            session.metadata["closed_at"] = time.time()
            
            # 最终保存
            if self.auto_save:
                await self._save_session(session)
            
            # 清理引用
            device_id = session.device_id
            user_id = session.user_id
            
            if device_id in self.device_sessions:
                del self.device_sessions[device_id]
            
            if user_id in self.user_sessions:
                if session_id in self.user_sessions[user_id]:
                    self.user_sessions[user_id].remove(session_id)
                if not self.user_sessions[user_id]:
                    del self.user_sessions[user_id]
            
            # 删除会话
            del self.sessions[session_id]
            
            self.logger.info(f"关闭会话: {session_id[:8]}... (原因: {reason})")
            
            return True
            
        except Exception as e:
            self.logger.error(f"关闭会话失败: {e}")
            return False
    
    async def _close_device_sessions(self, device_id: str):
        """关闭设备的所有会话"""
        session_id = self.device_sessions.get(device_id)
        if session_id:
            await self.close_session(session_id, "new_connection")
    
    async def _load_conversation_history(self, session: ESP32Session):
        """加载对话历史"""
        try:
            if not self.chat_history_service:
                return
            
            # 获取最近的对话历史
            history = await self.chat_history_service.get_recent_messages(
                user_id=session.user_id,
                limit=self.max_history_length
            )
            
            if history:
                # 转换格式
                dialogue_history = []
                for msg in history:
                    dialogue_history.append({
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp.timestamp() if hasattr(msg.timestamp, 'timestamp') else time.time(),
                        "metadata": msg.metadata or {}
                    })
                
                session.conversation_context.dialogue_history = dialogue_history
                session.conversation_context.conversation_count = len([
                    msg for msg in dialogue_history if msg["role"] == "user"
                ])
                session.conversation_context.total_interactions = len(dialogue_history)
                
                self.logger.info(f"加载对话历史: {len(dialogue_history)} 条消息")
            
        except Exception as e:
            self.logger.error(f"加载对话历史失败: {e}")
    
    async def _save_conversation_message(self, session: ESP32Session, message: Dict[str, Any]):
        """保存对话消息"""
        try:
            if not self.chat_history_service:
                return
            
            await self.chat_history_service.save_message(
                user_id=session.user_id,
                role=message["role"],
                content=message["content"],
                metadata={
                    "session_id": session.session_id,
                    "device_id": session.device_id,
                    **message.get("metadata", {})
                }
            )
            
        except Exception as e:
            self.logger.error(f"保存对话消息失败: {e}")
    
    async def _save_session(self, session: ESP32Session):
        """保存会话状态"""
        try:
            # 这里可以实现会话状态的持久化
            # 目前只是更新活动时间
            session.update_activity()
            
        except Exception as e:
            self.logger.error(f"保存会话状态失败: {e}")
    
    async def _cleanup_expired_sessions(self):
        """清理过期会话"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                current_time = time.time()
                expired_sessions = []
                
                for session_id, session in self.sessions.items():
                    if session.is_expired(self.session_timeout):
                        expired_sessions.append(session_id)
                
                # 清理过期会话
                for session_id in expired_sessions:
                    await self.close_session(session_id, "expired")
                
                if expired_sessions:
                    self.logger.info(f"清理了 {len(expired_sessions)} 个过期会话")
                
            except Exception as e:
                self.logger.error(f"会话清理任务出错: {e}")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        active_sessions = sum(1 for s in self.sessions.values() if s.state == SessionState.ACTIVE)
        paused_sessions = sum(1 for s in self.sessions.values() if s.state == SessionState.PAUSED)
        
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": active_sessions,
            "paused_sessions": paused_sessions,
            "device_sessions": len(self.device_sessions),
            "user_sessions": len(self.user_sessions),
            "session_timeout": self.session_timeout,
            "max_sessions": self.max_sessions
        }
    
    def get_user_sessions(self, user_id: str) -> List[ESP32Session]:
        """获取用户的所有会话"""
        session_ids = self.user_sessions.get(user_id, [])
        return [self.sessions[sid] for sid in session_ids if sid in self.sessions]
    
    async def shutdown(self):
        """关闭会话管理器"""
        self.logger.info("正在关闭ESP32会话管理器...")
        
        # 取消清理任务
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # 保存所有活跃会话
        if self.auto_save:
            save_tasks = []
            for session in self.sessions.values():
                if session.state in [SessionState.ACTIVE, SessionState.PAUSED]:
                    save_tasks.append(self._save_session(session))
            
            if save_tasks:
                await asyncio.gather(*save_tasks, return_exceptions=True)
        
        # 关闭所有会话
        close_tasks = []
        for session_id in list(self.sessions.keys()):
            close_tasks.append(self.close_session(session_id, "shutdown"))
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        self.logger.info("ESP32会话管理器已关闭")


# 全局实例
_esp32_session_manager: Optional[ESP32SessionManager] = None


def get_esp32_session_manager(config: Optional[Dict[str, Any]] = None) -> ESP32SessionManager:
    """获取ESP32会话管理器实例"""
    global _esp32_session_manager
    if _esp32_session_manager is None:
        _esp32_session_manager = ESP32SessionManager(config)
    return _esp32_session_manager


def reset_esp32_session_manager():
    """重置ESP32会话管理器实例"""
    global _esp32_session_manager
    if _esp32_session_manager:
        asyncio.create_task(_esp32_session_manager.shutdown())
    _esp32_session_manager = None
