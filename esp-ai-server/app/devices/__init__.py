"""
设备服务模块
Device Services Module
包含各种设备的连接、协议适配和管理功能
"""

# 导入ESP32设备模块 (已迁移到WebSocket集成模块)
from .esp32 import (
    ESP32ChatService,
    get_esp32_chat_service,
    ESP32Config,
    get_esp32_config,
    # WebSocket集成模块 (模块4)
    ESP32WebSocketManager,
    get_esp32_websocket_manager,
    ESP32MessageRouter,
    get_esp32_message_router,
    ESP32ConnectionHandler,
    # 枚举类型（已迁移到websocket/protocol/中）
    ESP32MessageType,
    ESP32AudioFormat,
    ESP32DeviceCapability,
    ESP32ConnectionState
)

# 导入设备配置模块
from .config import (
    YouthPsychologyConfig,
    get_youth_psychology_config,
    CrisisHotline,
    OnlinePlatform,
    ReferralResource
)

# 协议模块已完全迁移到ESP32专用模块中
# WebSocket协议：app.devices.esp32.websocket
# 音频协议：app.devices.esp32.audio

# 导入OTA模块
from .ota import OtaServer, OTAServer

__all__ = [
    # ESP32设备 (已迁移到WebSocket集成模块)
    'ESP32ChatService',
    'get_esp32_chat_service',
    'ESP32Config',
    'get_esp32_config',
    # WebSocket集成模块 (模块4)
    'ESP32WebSocketManager',
    'get_esp32_websocket_manager',
    'ESP32MessageRouter',
    'get_esp32_message_router',
    'ESP32ConnectionHandler',
    # 枚举类型（已迁移到websocket/protocol/中）
    'ESP32MessageType',
    'ESP32AudioFormat',
    'ESP32DeviceCapability',
    'ESP32ConnectionState',
    
    # 设备配置
    'YouthPsychologyConfig',
    'get_youth_psychology_config',
    'CrisisHotline',
    'OnlinePlatform',
    'ReferralResource',
    
    # OTA更新
    'OtaServer',
    'OTAServer',
]
