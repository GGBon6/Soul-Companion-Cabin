"""
Web服务模块
Web Services Module
专门处理网页相关的WebSocket和HTTP请求
"""

from .handlers import WebSocketHandler
from .api import HTTPAPIHandler
from .websocket import MessageHandlerRegistry
from .auth import LoginHandler, RegisterHandler, ProfileHandler
from .features import CharacterHandler, MoodHandler, DiaryHandler, StoryHandler

__all__ = [
    # 主要处理器
    'WebSocketHandler',
    'HTTPAPIHandler',
    
    # WebSocket相关
    'MessageHandlerRegistry',
    
    # 认证处理器
    'LoginHandler',
    'RegisterHandler', 
    'ProfileHandler',
    
    # 功能处理器
    'CharacterHandler',
    'MoodHandler',
    'DiaryHandler',
    'StoryHandler'
]
