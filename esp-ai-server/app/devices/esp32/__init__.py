"""
ESP32设备模块
ESP32 Device Module
专门处理ESP32设备的连接、协议适配和对话管理
"""

# 导入本地的ESP32组件 (原有组件)
from .chat_service import ESP32ChatService, get_esp32_chat_service
from ..config import ESP32Config, get_esp32_config

# 导入处理器组件
from .handlers import ESP32WebSocketHandler, get_esp32_websocket_handler

# 导入WebSocket模块化架构
from .websocket import (
    ESP32WebSocketManager, get_esp32_websocket_manager,
    ESP32MessageRouter, get_esp32_message_router,
    ESP32ConnectionHandler,
    # 导入枚举类型（已迁移到websocket/protocol/中）
    ESP32MessageType, ESP32AudioFormat, ESP32DeviceCapability, ESP32ConnectionState,
    ESP32ProcessingState, ESP32ErrorCode
)
from .websocket.session_manager import ESP32SessionManager as ESP32WebSocketSessionManager, get_esp32_session_manager as get_esp32_websocket_session_manager

__all__ = [
    # 原有组件
    'ESP32ChatService', 
    'get_esp32_chat_service',
    'ESP32Config',
    'get_esp32_config',
    
    # 处理器组件
    'ESP32WebSocketHandler',
    'get_esp32_websocket_handler',
    
    # 消息类型（已迁移到websocket/protocol/中）
    'ESP32MessageType',
    'ESP32AudioFormat',
    'ESP32DeviceCapability', 
    'ESP32ConnectionState',
    'ESP32ProcessingState',
    'ESP32ErrorCode',
    
    # WebSocket模块化架构
    'ESP32WebSocketManager',
    'get_esp32_websocket_manager',
    'ESP32MessageRouter',
    'get_esp32_message_router',
    'ESP32WebSocketSessionManager',
    'get_esp32_websocket_session_manager',
    'ESP32ConnectionHandler'
]
