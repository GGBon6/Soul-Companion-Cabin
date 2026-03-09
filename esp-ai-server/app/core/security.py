"""
安全工具模块
Security Utilities
密码加密、验证等安全相关功能
"""

import hashlib
import secrets
from typing import Optional

from .config import settings


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """
    密码哈希加密
    
    Args:
        password: 原始密码
        salt: 盐值（可选）
    
    Returns:
        str: 加密后的密码哈希
    """
    if salt is None:
        salt = settings.PASSWORD_SALT
    
    # 使用SHA256加密
    password_with_salt = f"{password}{salt}".encode('utf-8')
    return hashlib.sha256(password_with_salt).hexdigest()


def verify_password(plain_password: str, hashed_password: str, salt: Optional[str] = None) -> bool:
    """
    验证密码
    
    Args:
        plain_password: 原始密码
        hashed_password: 加密后的密码
        salt: 盐值（可选）
    
    Returns:
        bool: 密码是否匹配
    """
    return hash_password(plain_password, salt) == hashed_password


def generate_token(length: int = 32) -> str:
    """
    生成随机Token
    
    Args:
        length: Token长度
    
    Returns:
        str: 随机Token
    """
    return secrets.token_urlsafe(length)


def generate_user_id() -> str:
    """
    生成用户ID
    
    Returns:
        str: UUID格式的用户ID
    """
    import uuid
    return str(uuid.uuid4())


def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除危险字符
    
    Args:
        filename: 原始文件名
    
    Returns:
        str: 清理后的文件名
    """
    import re
    # 移除危险字符
    filename = re.sub(r'[^\w\s\-\.]', '', filename)
    # 限制长度
    filename = filename[:255]
    return filename


def validate_username(username: str) -> tuple[bool, str]:
    """
    验证用户名
    
    Args:
        username: 用户名
    
    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not username:
        return False, "用户名不能为空"
    
    if len(username) < settings.MIN_USERNAME_LENGTH:
        return False, f"用户名至少需要{settings.MIN_USERNAME_LENGTH}个字符"
    
    if len(username) > 50:
        return False, "用户名不能超过50个字符"
    
    # 检查字符（只允许字母、数字、下划线）
    import re
    if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]+$', username):
        return False, "用户名只能包含字母、数字、下划线和中文"
    
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    """
    验证密码强度
    
    Args:
        password: 密码
    
    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not password:
        return False, "密码不能为空"
    
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        return False, f"密码至少需要{settings.MIN_PASSWORD_LENGTH}个字符"
    
    if len(password) > 128:
        return False, "密码不能超过128个字符"
    
    return True, ""


if __name__ == "__main__":
    # 测试安全工具
    print("=" * 50)
    print("测试密码加密")
    password = "test123456"
    hashed = hash_password(password)
    print(f"原始密码: {password}")
    print(f"加密后: {hashed}")
    print(f"验证结果: {verify_password(password, hashed)}")
    print(f"错误密码: {verify_password('wrong', hashed)}")
    
    print("\n" + "=" * 50)
    print("测试Token生成")
    token = generate_token()
    print(f"随机Token: {token}")
    
    print("\n" + "=" * 50)
    print("测试用户ID生成")
    user_id = generate_user_id()
    print(f"用户ID: {user_id}")
    
    print("\n" + "=" * 50)
    print("测试用户名验证")
    test_usernames = ["abc", "test_user", "测试用户", "user@123", "a" * 51]
    for username in test_usernames:
        valid, message = validate_username(username)
        print(f"{username}: {'✓' if valid else '✗'} {message}")
    
    print("\n" + "=" * 50)
    print("测试密码验证")
    test_passwords = ["123", "123456", "a" * 129]
    for pwd in test_passwords:
        valid, message = validate_password(pwd)
        print(f"{pwd[:20]}...: {'✓' if valid else '✗'} {message}")

