"""
ESP32处理器模块
ESP32 Handlers Module
包含ESP32 WebSocket处理器，消息处理器已迁移到websocket/message_handlers/
"""

from .websocket_handler import ESP32WebSocketHandler, get_esp32_websocket_handler

__all__ = [
    'ESP32WebSocketHandler',
    'get_esp32_websocket_handler'
]

# 注意：具体的消息处理器已迁移到 websocket/message_handlers/ 目录
# 新的架构使用 WebSocketHelloHandler, WebSocketAudioHandler 等
