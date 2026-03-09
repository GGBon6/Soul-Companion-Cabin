"""
ESP32音频处理模块
ESP32 Audio Processing Module
包含音频状态管理、缓冲管理等核心音频处理组件
"""

from .audio_state_manager import ESP32AudioStateManager, ESP32AudioState, get_esp32_audio_state_manager
from .audio_buffer_manager import ESP32AudioBufferManager, AudioFrame, get_esp32_audio_buffer_manager
from .protocol_adapter import ESP32AudioProtocolAdapter, ESP32AudioProtocol, ProtocolHeader, get_esp32_audio_protocol_adapter

__all__ = [
    # 音频状态管理
    'ESP32AudioStateManager',
    'ESP32AudioState',
    'get_esp32_audio_state_manager',
    
    # 音频缓冲管理
    'ESP32AudioBufferManager',
    'AudioFrame',
    'get_esp32_audio_buffer_manager',
    
    # 协议适配
    'ESP32AudioProtocolAdapter',
    'ESP32AudioProtocol',
    'ProtocolHeader',
    'get_esp32_audio_protocol_adapter'
]
