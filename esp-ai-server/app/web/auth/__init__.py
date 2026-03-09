"""
Web认证模块
Web Authentication Module
包含Web相关的认证处理器
"""

# 导入本地的认证处理器
from .login_handler import LoginHandler
from .register_handler import RegisterHandler
from .profile_handler import ProfileHandler

__all__ = [
    'LoginHandler',
    'RegisterHandler',
    'ProfileHandler'
]
