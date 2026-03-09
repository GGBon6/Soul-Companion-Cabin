"""
WebSocket协议模块
WebSocket Protocol Module
提供WebSocket通信的协议处理功能，包含Opus编解码
"""

# 注意：WebSocketProtocolHandler已迁移到新的消息路由器架构
# 使用 app.devices.esp32.websocket.message_router 替代
from .binary_protocol import BinaryProtocolHandler, get_binary_protocol_handler
from .message_protocol import (
    MessageProtocolHandler,
    ESP32MessageType, ESP32AudioFormat, ESP32DeviceCapability, ESP32ConnectionState,
    ESP32ProcessingState, ESP32ErrorCode
)

__all__ = [
    # 'WebSocketProtocolHandler',  # 已迁移到消息路由器
    'BinaryProtocolHandler',
    'get_binary_protocol_handler',
    'MessageProtocolHandler',
    # ESP32枚举类型
    'ESP32MessageType',
    'ESP32AudioFormat', 
    'ESP32DeviceCapability',
    'ESP32ConnectionState',
    'ESP32ProcessingState',
    'ESP32ErrorCode'
]
