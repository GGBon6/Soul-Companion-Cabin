"""
Web处理器模块
Web Handlers Module
包含WebSocket和HTTP的主要处理器
"""

# 导入本地的处理器
from .websocket_handler import WebSocketHandler

__all__ = [
    'WebSocketHandler'
]
