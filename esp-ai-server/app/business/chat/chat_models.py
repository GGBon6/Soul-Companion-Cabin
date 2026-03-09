"""
对话数据模型
Chat Data Models
定义对话功能相关的数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class ChatType(Enum):
    """对话类型枚举"""
    NORMAL = "normal"           # 普通对话
    PROACTIVE = "proactive"     # 主动对话
    TREE_HOLE = "tree_hole"     # 树洞模式
    CRISIS = "crisis"           # 危机干预


class ChatStatus(Enum):
    """对话状态枚举"""
    ACTIVE = "active"           # 活跃
    PAUSED = "paused"          # 暂停
    ENDED = "ended"            # 结束
    ARCHIVED = "archived"       # 已归档


class MessageRole(Enum):
    """消息角色枚举"""
    USER = "user"              # 用户
    ASSISTANT = "assistant"     # 助手
    SYSTEM = "system"          # 系统


@dataclass
class ChatMessage:
    """对话消息模型"""
    
    message_id: str
    session_id: str
    user_id: str
    role: MessageRole
    content: str
    message_type: str = "text"  # text, audio, image
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'message_id': self.message_id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'role': self.role.value,
            'content': self.content,
            'message_type': self.message_type,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """从字典创建消息"""
        created_at = None
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        return cls(
            message_id=data['message_id'],
            session_id=data['session_id'],
            user_id=data['user_id'],
            role=MessageRole(data['role']),
            content=data['content'],
            message_type=data.get('message_type', 'text'),
            metadata=data.get('metadata', {}),
            created_at=created_at
        )


@dataclass
class ChatSession:
    """对话会话模型"""
    
    session_id: str
    user_id: str
    chat_type: ChatType
    status: ChatStatus = ChatStatus.ACTIVE
    title: Optional[str] = None
    summary: Optional[str] = None
    messages: List[ChatMessage] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
    
    def add_message(self, message: ChatMessage):
        """添加消息"""
        self.messages.append(message)
        self.updated_at = datetime.now()
    
    def end_session(self):
        """结束会话"""
        self.status = ChatStatus.ENDED
        self.ended_at = datetime.now()
        self.updated_at = datetime.now()
    
    def get_message_count(self) -> int:
        """获取消息数量"""
        return len(self.messages)
    
    def get_duration_minutes(self) -> int:
        """获取会话时长（分钟）"""
        if self.ended_at:
            delta = self.ended_at - self.created_at
        else:
            delta = datetime.now() - self.created_at
        return int(delta.total_seconds() / 60)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'chat_type': self.chat_type.value,
            'status': self.status.value,
            'title': self.title,
            'summary': self.summary,
            'messages': [msg.to_dict() for msg in self.messages],
            'context': self.context,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatSession':
        """从字典创建会话"""
        created_at = None
        updated_at = None
        ended_at = None
        
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])
        if data.get('ended_at'):
            ended_at = datetime.fromisoformat(data['ended_at'])
        
        messages = [ChatMessage.from_dict(msg_data) for msg_data in data.get('messages', [])]
        
        return cls(
            session_id=data['session_id'],
            user_id=data['user_id'],
            chat_type=ChatType(data['chat_type']),
            status=ChatStatus(data.get('status', 'active')),
            title=data.get('title'),
            summary=data.get('summary'),
            messages=messages,
            context=data.get('context', {}),
            created_at=created_at,
            updated_at=updated_at,
            ended_at=ended_at
        )


@dataclass
class ProactiveChatTrigger:
    """主动对话触发器模型"""
    
    trigger_id: str
    name: str
    description: str
    conditions: Dict[str, Any] = field(default_factory=dict)  # 触发条件
    message_templates: List[str] = field(default_factory=list)  # 消息模板
    priority: int = 1  # 优先级 1-10
    is_active: bool = True
    cooldown_hours: int = 24  # 冷却时间（小时）
    max_triggers_per_day: int = 3  # 每天最大触发次数
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'trigger_id': self.trigger_id,
            'name': self.name,
            'description': self.description,
            'conditions': self.conditions,
            'message_templates': self.message_templates,
            'priority': self.priority,
            'is_active': self.is_active,
            'cooldown_hours': self.cooldown_hours,
            'max_triggers_per_day': self.max_triggers_per_day,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProactiveChatTrigger':
        """从字典创建触发器"""
        created_at = None
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        return cls(
            trigger_id=data['trigger_id'],
            name=data['name'],
            description=data['description'],
            conditions=data.get('conditions', {}),
            message_templates=data.get('message_templates', []),
            priority=data.get('priority', 1),
            is_active=data.get('is_active', True),
            cooldown_hours=data.get('cooldown_hours', 24),
            max_triggers_per_day=data.get('max_triggers_per_day', 3),
            created_at=created_at
        )


@dataclass
class ChatAnalytics:
    """对话分析模型"""
    
    user_id: str
    date_range: Dict[str, str] = field(default_factory=dict)  # start_date, end_date
    total_sessions: int = 0
    total_messages: int = 0
    average_session_duration: float = 0.0  # 平均会话时长（分钟）
    chat_type_distribution: Dict[str, int] = field(default_factory=dict)
    daily_activity: Dict[str, int] = field(default_factory=dict)  # date -> message_count
    hourly_activity: Dict[str, int] = field(default_factory=dict)  # hour -> message_count
    emotion_trends: Dict[str, List[float]] = field(default_factory=dict)
    topic_frequency: Dict[str, int] = field(default_factory=dict)
    response_satisfaction: Dict[str, int] = field(default_factory=dict)  # rating -> count
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'date_range': self.date_range,
            'total_sessions': self.total_sessions,
            'total_messages': self.total_messages,
            'average_session_duration': self.average_session_duration,
            'chat_type_distribution': self.chat_type_distribution,
            'daily_activity': self.daily_activity,
            'hourly_activity': self.hourly_activity,
            'emotion_trends': self.emotion_trends,
            'topic_frequency': self.topic_frequency,
            'response_satisfaction': self.response_satisfaction
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatAnalytics':
        """从字典创建分析数据"""
        return cls(
            user_id=data['user_id'],
            date_range=data.get('date_range', {}),
            total_sessions=data.get('total_sessions', 0),
            total_messages=data.get('total_messages', 0),
            average_session_duration=data.get('average_session_duration', 0.0),
            chat_type_distribution=data.get('chat_type_distribution', {}),
            daily_activity=data.get('daily_activity', {}),
            hourly_activity=data.get('hourly_activity', {}),
            emotion_trends=data.get('emotion_trends', {}),
            topic_frequency=data.get('topic_frequency', {}),
            response_satisfaction=data.get('response_satisfaction', {})
        )


@dataclass
class ChatPreferences:
    """对话偏好模型"""
    
    user_id: str
    preferred_chat_types: List[ChatType] = field(default_factory=list)
    response_style: str = "friendly"  # friendly, professional, casual
    enable_proactive_chat: bool = True
    proactive_frequency: str = "moderate"  # low, moderate, high
    preferred_topics: List[str] = field(default_factory=list)
    avoided_topics: List[str] = field(default_factory=list)
    notification_settings: Dict[str, bool] = field(default_factory=dict)
    privacy_level: str = "normal"  # low, normal, high
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if not self.notification_settings:
            self.notification_settings = {
                'proactive_chat': True,
                'daily_summary': True,
                'mood_check': True
            }
    
    def update_preferences(self, **kwargs):
        """更新偏好设置"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'preferred_chat_types': [ct.value for ct in self.preferred_chat_types],
            'response_style': self.response_style,
            'enable_proactive_chat': self.enable_proactive_chat,
            'proactive_frequency': self.proactive_frequency,
            'preferred_topics': self.preferred_topics,
            'avoided_topics': self.avoided_topics,
            'notification_settings': self.notification_settings,
            'privacy_level': self.privacy_level,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatPreferences':
        """从字典创建偏好"""
        updated_at = None
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])
        
        preferred_chat_types = [ChatType(ct) for ct in data.get('preferred_chat_types', [])]
        
        return cls(
            user_id=data['user_id'],
            preferred_chat_types=preferred_chat_types,
            response_style=data.get('response_style', 'friendly'),
            enable_proactive_chat=data.get('enable_proactive_chat', True),
            proactive_frequency=data.get('proactive_frequency', 'moderate'),
            preferred_topics=data.get('preferred_topics', []),
            avoided_topics=data.get('avoided_topics', []),
            notification_settings=data.get('notification_settings', {}),
            privacy_level=data.get('privacy_level', 'normal'),
            updated_at=updated_at
        )
