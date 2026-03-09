"""
WebSocket处理模块
WebSocket Handler Module
包含WebSocket消息处理和连接管理
"""

# 重新导出原有WebSocket处理器，保持向后兼容
from app.web.message_handlers import TextMessageHandler, VoiceMessageHandler

# 创建消息处理器注册表
class MessageHandlerRegistry:
    """消息处理器注册表"""
    
    def __init__(self):
        self.text_handler = TextMessageHandler()
        self.voice_handler = VoiceMessageHandler()
    
    def get_text_handler(self):
        return self.text_handler
    
    def get_voice_handler(self):
        return self.voice_handler

__all__ = [
    'TextMessageHandler',
    'VoiceMessageHandler', 
    'MessageHandlerRegistry'
]
