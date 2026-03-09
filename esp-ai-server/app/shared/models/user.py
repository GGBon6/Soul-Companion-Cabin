"""
用户数据模型
User Data Model
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class User:
    """用户模型"""
    
    user_id: str
    username: str
    password_hash: str
    nickname: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    last_login: Optional[str] = None
    
    def to_dict(self, include_password: bool = False) -> dict:
        """
        转换为字典
        
        Args:
            include_password: 是否包含密码哈希
        
        Returns:
            dict: 用户信息字典
        """
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "nickname": self.nickname or self.username,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }
        
        if include_password:
            data["password"] = self.password_hash
        
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """
        从字典创建用户对象
        
        Args:
            data: 用户数据字典
        
        Returns:
            User: 用户对象
        """
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            password_hash=data.get("password", ""),
            nickname=data.get("nickname"),
            created_at=data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            last_login=data.get("last_login"),
        )
    
    def update_last_login(self):
        """更新最后登录时间"""
        self.last_login = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def __repr__(self) -> str:
        return f"User(user_id='{self.user_id}', username='{self.username}', nickname='{self.nickname}')"

