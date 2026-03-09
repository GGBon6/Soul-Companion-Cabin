"""
会话数据模型
Session Data Model
定义用户会话的数据结构
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
import time


@dataclass
class Session:
    """会话模型"""
    
    session_id: str
    user_id: str
    client_id: Optional[str] = None
    created_at: float = None
    last_activity: float = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_activity is None:
            self.last_activity = time.time()
        if self.metadata is None:
            self.metadata = {}
    
    def update_activity(self):
        """更新最后活动时间"""
        self.last_activity = time.time()
    
    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """检查会话是否过期"""
        return time.time() - self.last_activity > timeout_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'client_id': self.client_id,
            'created_at': self.created_at,
            'last_activity': self.last_activity,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        """从字典创建会话"""
        return cls(
            session_id=data['session_id'],
            user_id=data['user_id'],
            client_id=data.get('client_id'),
            created_at=data.get('created_at'),
            last_activity=data.get('last_activity'),
            metadata=data.get('metadata', {})
        )
