"""
ESP32 WebSocket集成模块
ESP32 WebSocket Integration Module
参考core目录的优秀设计，为ESP32设备提供完整的WebSocket通信支持
"""

from .websocket_manager import ESP32WebSocketManager, get_esp32_websocket_manager
from .message_router import ESP32MessageRouter, get_esp32_message_router
from .session_manager import ESP32SessionManager, get_esp32_session_manager
from .connection_handler import ESP32ConnectionHandler

# 导入消息处理器
from .message_handlers import (
    WebSocketBaseHandler, WebSocketMessageValidator,
    WebSocketHelloHandler, WebSocketAudioHandler, WebSocketTextHandler,
    WebSocketControlHandler, WebSocketIntentHandler
)

# 导入协议处理器（WebSocketProtocolHandler已迁移到消息路由器）
from .protocol import (
    BinaryProtocolHandler, get_binary_protocol_handler, MessageProtocolHandler,
    ESP32MessageType, ESP32AudioFormat, ESP32DeviceCapability, ESP32ConnectionState,
    ESP32ProcessingState, ESP32ErrorCode
)

__all__ = [
    # WebSocket管理
    'ESP32WebSocketManager',
    'get_esp32_websocket_manager',
    
    # 消息路由
    'ESP32MessageRouter', 
    'get_esp32_message_router',
    
    # 会话管理
    'ESP32SessionManager',
    'get_esp32_session_manager',
    
    # 连接处理
    'ESP32ConnectionHandler',
    
    # 消息处理器
    'WebSocketBaseHandler',
    'WebSocketMessageValidator', 
    'WebSocketHelloHandler',
    'WebSocketAudioHandler',
    'WebSocketTextHandler',
    'WebSocketControlHandler',
    'WebSocketIntentHandler',
    
    # 协议处理器（WebSocketProtocolHandler已迁移）
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
