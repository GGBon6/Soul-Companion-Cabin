"""
消息数据模型
Message Data Model
"""

from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass, field


MessageRole = Literal["system", "user", "assistant"]


@dataclass
class Message:
    """消息模型"""
    
    role: MessageRole
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    message_id: Optional[str] = None
    metadata: Optional[dict] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        data = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        
        if self.message_id:
            data["message_id"] = self.message_id
        
        if self.metadata:
            data["metadata"] = self.metadata
        
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """从字典创建消息对象"""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            message_id=data.get("message_id"),
            metadata=data.get("metadata"),
        )
    
    def to_llm_format(self) -> dict:
        """转换为LLM API格式"""
        return {
            "role": self.role,
            "content": self.content,
        }
    
    def is_user_message(self) -> bool:
        """是否为用户消息"""
        return self.role == "user"
    
    def is_assistant_message(self) -> bool:
        """是否为助手消息"""
        return self.role == "assistant"
    
    def is_system_message(self) -> bool:
        """是否为系统消息"""
        return self.role == "system"
    
    def __repr__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"Message(role='{self.role}', content='{content_preview}')"

