"""
Web API模块
Web API Module
包含REST API处理器
"""

# 导入本地的API处理器
from .http_api_handler import HTTPAPIHandler
from .chat_api import get_chat_api, ChatAPI
from .user_api import get_user_api, UserAPI
from .health_api import get_health_api, HealthAPI

__all__ = [
    'HTTPAPIHandler',
    'get_chat_api',
    'ChatAPI',
    'get_user_api', 
    'UserAPI',
    'get_health_api',
    'HealthAPI'
]
