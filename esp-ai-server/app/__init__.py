"""
巴卫对话系统 - 后端应用
Tomoe Chat System - Backend Application

重构后的模块化架构：
- shared: 共享服务层（LLM、ASR、TTS等）
- web: Web服务模块（WebSocket、HTTP API）
- devices: 设备服务模块（ESP32等）
- business: 业务逻辑模块（日记、故事、对话）
"""

__version__ = "2.1.0"
__author__ = "Tomoe Chat Team"

# 导出主要模块
from . import shared
from . import web
from . import devices
from . import business

