"""
设备配置模块
Device Configuration Module
统一管理各种设备的配置文件和参数
"""

from .esp32_config import ESP32Config, get_esp32_config
from .youth_psychology_config import YouthPsychologyConfig, get_youth_psychology_config, CrisisHotline, OnlinePlatform, ReferralResource

__all__ = [
    # ESP32设备配置
    'ESP32Config',
    'get_esp32_config',
    
    # 青少年心理对话配置
    'YouthPsychologyConfig',
    'get_youth_psychology_config',
    'CrisisHotline',
    'OnlinePlatform', 
    'ReferralResource'
]
