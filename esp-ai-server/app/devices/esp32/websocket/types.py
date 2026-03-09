"""
ESP32 WebSocket类型定义
ESP32 WebSocket Type Definitions
定义ESP32 WebSocket连接相关的数据类型
"""

import time
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


class ConnectionState(Enum):
    """连接状态"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ACTIVE = "active"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class ESP32DeviceInfo:
    """ESP32设备信息"""
    device_id: str
    client_id: Optional[str] = None
    client_ip: str = ""
    user_agent: str = ""
    protocol_version: str = "1.0"
    features: Dict[str, Any] = field(default_factory=dict)
    audio_params: Dict[str, Any] = field(default_factory=dict)
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


@dataclass
class ConnectionStats:
    """连接统计信息"""
    total_connections: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    average_response_time: float = 0.0
    last_reset: float = field(default_factory=time.time)
