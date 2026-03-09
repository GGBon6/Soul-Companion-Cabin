"""
OTA更新模块
OTA Update Module
包含设备固件的OTA更新服务
"""

# 导入本地的OTA服务器
from .ota_server import OtaServer

# 为了保持一致性，也导出为OTAServer
OTAServer = OtaServer

__all__ = [
    'OtaServer',
    'OTAServer'
]
