"""
对话业务模块
Chat Business Module
包含对话功能的业务逻辑
"""

# 导入本地的主动对话服务和模型
from .proactive_chat_service import get_proactive_chat_service, ProactiveChatService
from .chat_models import (
    ChatMessage, ChatSession, ProactiveChatTrigger,
    ChatAnalytics, ChatPreferences,
    ChatType, ChatStatus, MessageRole
)

__all__ = [
    # 服务
    'get_proactive_chat_service',
    'ProactiveChatService',
    
    # 模型
    'ChatMessage',
    'ChatSession',
    'ProactiveChatTrigger',
    'ChatAnalytics',
    'ChatPreferences',
    
    # 枚举
    'ChatType',
    'ChatStatus', 
    'MessageRole'
]
