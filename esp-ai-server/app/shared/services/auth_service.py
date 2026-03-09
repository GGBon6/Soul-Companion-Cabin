"""
认证服务
Authentication Service
处理用户注册、登录、认证等功能
"""

import json
from typing import Optional, Tuple
from pathlib import Path

from app.core import settings, logger, hash_password, verify_password, generate_user_id
from app.core.security import validate_username, validate_password
from app.core.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
    InvalidCredentialsError,
    InvalidInputError,
)
from app.shared.models import User


class AuthService:
    """认证服务类"""
    
    def __init__(self):
        """初始化认证服务"""
        self.users_dir = settings.USERS_DIR
        self.users_file = self.users_dir / "users.json"
        self._ensure_dirs()
        self.users = self._load_users()
    
    def _ensure_dirs(self):
        """确保用户数据目录存在"""
        self.users_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_users(self) -> dict:
        """加载用户列表"""
        if self.users_file.exists():
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载用户列表失败: {e}")
                return {}
        return {}
    
    def _save_users(self):
        """保存用户列表"""
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, ensure_ascii=False, indent=2)
            logger.debug(f"用户列表已保存，共 {len(self.users)} 个用户")
        except Exception as e:
            logger.error(f"保存用户列表失败: {e}")
            raise
    
    def register(
        self, 
        username: str, 
        password: str, 
        nickname: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        注册新用户
        
        Args:
            username: 用户名
            password: 密码
            nickname: 昵称（可选）
        
        Returns:
            tuple: (success, message, user_id)
        
        Raises:
            UserAlreadyExistsError: 用户已存在
            InvalidInputError: 输入验证失败
        """
        try:
            # 验证用户名
            valid, message = validate_username(username)
            if not valid:
                logger.warning(f"用户名验证失败: {username} - {message}")
                return False, message, None
            
            # 验证密码
            valid, message = validate_password(password)
            if not valid:
                logger.warning(f"密码验证失败: {message}")
                return False, message, None
            
            # 检查用户是否已存在
            if username in self.users:
                logger.warning(f"注册失败：用户 {username} 已存在")
                return False, "用户名已存在", None
            
            # 生成用户ID
            user_id = generate_user_id()
            
            # 创建用户对象
            user = User(
                user_id=user_id,
                username=username,
                password_hash=hash_password(password),
                nickname=nickname or username
            )
            
            # 保存用户
            self.users[username] = user.to_dict(include_password=True)
            self._save_users()
            
            logger.info(f"✅ 用户注册成功: {username} (ID: {user_id})")
            return True, "注册成功", user_id
            
        except Exception as e:
            logger.error(f"注册用户时发生错误: {e}", exc_info=True)
            return False, f"注册失败: {str(e)}", None
    
    def login(
        self, 
        username: str, 
        password: str
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        用户登录
        
        Args:
            username: 用户名
            password: 密码
        
        Returns:
            tuple: (success, message, user_info)
        
        Raises:
            UserNotFoundError: 用户不存在
            InvalidCredentialsError: 密码错误
        """
        try:
            # 检查用户是否存在
            if username not in self.users:
                logger.warning(f"登录失败：用户 {username} 不存在")
                return False, "用户不存在", None
            
            user_data = self.users[username]
            
            # 验证密码
            if not verify_password(password, user_data["password"]):
                logger.warning(f"登录失败：用户 {username} 密码错误")
                return False, "密码错误", None
            
            # 更新最后登录时间
            user = User.from_dict(user_data)
            user.update_last_login()
            self.users[username] = user.to_dict(include_password=True)
            self._save_users()
            
            logger.info(f"✅ 用户登录成功: {username} (ID: {user.user_id})")
            
            # 返回用户信息（不包含密码）
            return True, "登录成功", user.to_dict(include_password=False)
            
        except Exception as e:
            logger.error(f"用户登录时发生错误: {e}", exc_info=True)
            return False, f"登录失败: {str(e)}", None
    
    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        """
        通过用户ID获取用户信息
        
        Args:
            user_id: 用户ID
        
        Returns:
            dict: 用户信息（不包含密码）
        """
        for username, user_data in self.users.items():
            if user_data["user_id"] == user_id:
                user = User.from_dict(user_data)
                return user.to_dict(include_password=False)
        return None
    
    def get_user_by_username(self, username: str) -> Optional[dict]:
        """
        通过用户名获取用户信息
        
        Args:
            username: 用户名
        
        Returns:
            dict: 用户信息（不包含密码）
        """
        if username in self.users:
            user = User.from_dict(self.users[username])
            return user.to_dict(include_password=False)
        return None
    
    def update_nickname(self, user_id: str, nickname: str) -> bool:
        """
        更新用户昵称
        
        Args:
            user_id: 用户ID
            nickname: 新昵称
        
        Returns:
            bool: 是否成功
        """
        for username, user_data in self.users.items():
            if user_data["user_id"] == user_id:
                user_data["nickname"] = nickname
                self._save_users()
                logger.info(f"✅ 更新昵称成功: {username} -> {nickname}")
                return True
        return False
    
    def reset_password(self, username: str, new_password: str) -> Tuple[bool, str]:
        """
        重置用户密码
        
        Args:
            username: 用户名
            new_password: 新密码
        
        Returns:
            tuple: (success, message)
        """
        try:
            # 验证用户是否存在
            if username not in self.users:
                logger.warning(f"重置密码失败：用户 {username} 不存在")
                return False, "用户不存在"
            
            # 验证新密码
            valid, message = validate_password(new_password)
            if not valid:
                logger.warning(f"密码验证失败: {message}")
                return False, message
            
            # 更新密码
            self.users[username]["password"] = hash_password(new_password)
            self._save_users()
            
            logger.info(f"✅ 密码重置成功: {username}")
            return True, "密码重置成功"
            
        except Exception as e:
            logger.error(f"重置密码时发生错误: {e}", exc_info=True)
            return False, f"重置密码失败: {str(e)}"
    
    def user_exists(self, username: str) -> bool:
        """
        检查用户是否存在
        
        Args:
            username: 用户名
        
        Returns:
            bool: 是否存在
        """
        return username in self.users
    
    def get_user_count(self) -> int:
        """获取用户总数"""
        return len(self.users)
    
    def get_user_profile(self, identifier: str) -> Optional[dict]:
        """
        获取用户个人信息
        
        Args:
            identifier: 用户名或用户ID
        
        Returns:
            dict: 个人信息字典，如果用户不存在返回None
        """
        try:
            # 先尝试按用户名查找
            if identifier in self.users:
                user = self.users[identifier]
                profile = user.get('profile', {})
                logger.info(f"获取用户 {identifier} 的个人信息")
                return profile
            
            # 如果不是用户名，尝试按user_id查找
            for username, user_data in self.users.items():
                if user_data.get('user_id') == identifier:
                    profile = user_data.get('profile', {})
                    logger.info(f"通过user_id获取用户 {username} 的个人信息")
                    return profile
            
            logger.warning(f"用户 {identifier} 不存在")
            return None
            
        except Exception as e:
            logger.error(f"获取用户个人信息失败: {e}", exc_info=True)
            return None
    
    def update_user_profile(self, identifier: str, profile: dict) -> Tuple[bool, str]:
        """
        更新用户个人信息
        
        Args:
            identifier: 用户名或用户ID
            profile: 个人信息字典
        
        Returns:
            tuple: (success, message)
        """
        try:
            # 先尝试按用户名查找
            if identifier in self.users:
                self.users[identifier]['profile'] = profile
                self._save_users()
                logger.info(f"✅ 用户 {identifier} 的个人信息已更新")
                return True, "个人信息已保存"
            
            # 如果不是用户名，尝试按user_id查找
            for username, user_data in self.users.items():
                if user_data.get('user_id') == identifier:
                    self.users[username]['profile'] = profile
                    self._save_users()
                    logger.info(f"✅ 用户 {username} 的个人信息已更新（通过user_id）")
                    return True, "个人信息已保存"
            
            logger.warning(f"用户 {identifier} 不存在")
            return False, "用户不存在"
            
        except Exception as e:
            logger.error(f"更新用户个人信息失败: {e}", exc_info=True)
            return False, f"更新失败: {str(e)}"


# 全局单例
_auth_service = None


def get_auth_service() -> AuthService:
    """获取认证服务单例"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


if __name__ == "__main__":
    # 测试认证服务
    service = AuthService()
    
    # 测试注册
    success, msg, user_id = service.register("test_user", "test123456", "测试用户")
    print(f"注册: {success} - {msg} - {user_id}")
    
    # 测试登录
    success, msg, user_info = service.login("test_user", "test123456")
    print(f"登录: {success} - {msg}")
    print(f"用户信息: {user_info}")
    
    # 测试获取用户
    info = service.get_user_by_id(user_id)
    print(f"获取用户: {info}")

