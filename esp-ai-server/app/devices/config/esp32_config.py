"""
ESP32设备配置模块
ESP32 Device Configuration Module
管理ESP32设备的配置参数和设置
"""

import os
import yaml
from typing import Dict, Any, Optional
from app.core import logger


class ESP32Config:
    """ESP32设备配置管理器"""
    
    def __init__(self, config_file: str = None):
        """初始化ESP32配置"""
        self.config_file = config_file or "config/esp32_config.yaml"
        self.config_data = {}
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config_data = yaml.safe_load(f) or {}
                logger.info(f"✅ 加载ESP32配置文件: {self.config_file}")
            else:
                logger.warning(f"⚠️ ESP32配置文件不存在: {self.config_file}")
                self.config_data = self._get_default_config()
        except Exception as e:
            logger.error(f"❌ 加载ESP32配置失败: {e}")
            self.config_data = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "device": {
                "max_connections": 100,
                "connection_timeout": 300,
                "heartbeat_interval": 30,
                "max_message_size": 1024 * 1024,  # 1MB
                "supported_audio_formats": ["opus", "pcm", "wav"]
            },
            "audio": {
                "sample_rate": 16000,
                "channels": 1,
                "bit_depth": 16,
                "opus_bitrate": 16000,
                "opus_frame_duration": 20
            },
            "protocol": {
                "version": "1.0",
                "message_types": [
                    "hello", "audio_data", "text_message", 
                    "heartbeat", "goodbye", "error"
                ],
                "compression_enabled": True,
                "encryption_enabled": False
            },
            "chat": {
                "enable_memory": True,
                "enable_emotion": True,
                "enable_risk_detection": True,
                "max_history_length": 50,
                "response_timeout": 30
            },
            "features": {
                "tts_enabled": True,
                "asr_enabled": True,
                "chat_enabled": True,
                "file_transfer_enabled": False
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config_data
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        config = self.config_data
        
        # 导航到最后一级
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # 设置值
        config[keys[-1]] = value
    
    def save_config(self):
        """保存配置到文件"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.config_data, f, default_flow_style=False, 
                         allow_unicode=True, indent=2)
            logger.info(f"✅ 保存ESP32配置文件: {self.config_file}")
        except Exception as e:
            logger.error(f"❌ 保存ESP32配置失败: {e}")
    
    def reload_config(self):
        """重新加载配置"""
        self.load_config()
    
    def get_device_config(self) -> Dict[str, Any]:
        """获取设备配置"""
        return self.get('device', {})
    
    def get_audio_config(self) -> Dict[str, Any]:
        """获取音频配置"""
        return self.get('audio', {})
    
    def get_protocol_config(self) -> Dict[str, Any]:
        """获取协议配置"""
        return self.get('protocol', {})
    
    def get_chat_config(self) -> Dict[str, Any]:
        """获取对话配置"""
        return self.get('chat', {})
    
    def get_features_config(self) -> Dict[str, Any]:
        """获取功能配置"""
        return self.get('features', {})
    
    def is_feature_enabled(self, feature: str) -> bool:
        """检查功能是否启用"""
        return self.get(f'features.{feature}_enabled', False)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.config_data.copy()


# 全局配置实例
_esp32_config = None

def get_esp32_config() -> ESP32Config:
    """获取ESP32配置单例"""
    global _esp32_config
    if _esp32_config is None:
        _esp32_config = ESP32Config()
    return _esp32_config

def reload_esp32_config():
    """重新加载ESP32配置"""
    global _esp32_config
    if _esp32_config is not None:
        _esp32_config.reload_config()
    else:
        _esp32_config = ESP32Config()
