"""
共享工具模块
Shared Utils Module
包含Web和设备服务共用的工具函数
"""

# 导入本地的工具文件
from . import text_utils
from . import audio_utils

__all__ = [
    'text_utils',
    'audio_utils'
]
