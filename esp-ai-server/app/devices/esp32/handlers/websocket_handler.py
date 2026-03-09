"""
ESP32专用WebSocket处理器 (基于模块化架构)
ESP32 Dedicated WebSocket Handler (Based on Modular Architecture)
使用模块化的WebSocket架构提供ESP32设备连接服务
"""

import asyncio
from typing import Optional, Dict, Any

from app.core import logger
from app.devices.esp32.websocket import get_esp32_websocket_manager


class ESP32WebSocketHandler:
    """ESP32专用WebSocket处理器 (基于模块化架构)"""
    
    def __init__(self):
        """初始化ESP32处理器"""
        logger.info("🔧 初始化ESP32 WebSocket处理器 (模块化架构)...")
        
        # 使用新的WebSocket集成模块
        self.websocket_manager = get_esp32_websocket_manager({
            "max_connections": 1000,
            "connection_timeout": 300,
            "heartbeat_interval": 30,
            "auth": {
                "enabled": False,
                "device_whitelist": [],
                "jwt_secret": ""
            },
            "message": {
                "max_size": 10 * 1024 * 1024,  # 10MB (支持大音频文件)
                "queue_size": 1000,
                "processing_timeout": 30
            },
            "performance": {
                "max_workers": 10,
                "enable_compression": True,
                "buffer_size": 8192
            }
        })
        
        logger.info("✅ ESP32 WebSocket处理器初始化完成 (模块化架构)")
    
    async def start(self, host: str = "0.0.0.0", port: int = 8767):
        """启动ESP32 WebSocket服务器"""
        logger.info(f"🚀 启动ESP32 WebSocket服务器 (模块化架构): {host}:{port}")
        logger.info("🎯 模块化功能: 协议处理、消息路由、会话管理、音频处理")
        
        try:
            # 使用新的WebSocket管理器启动服务器
            await self.websocket_manager.start_server(host=host, port=port)
            
        except Exception as e:
            logger.error(f"❌ ESP32 WebSocket服务器启动失败: {e}")
            raise
    
    async def stop(self):
        """停止ESP32 WebSocket服务器"""
        logger.info("⏹️ 停止ESP32 WebSocket服务器...")
        
        try:
            await self.websocket_manager.shutdown()
            logger.info("✅ ESP32 WebSocket服务器已停止")
            
        except Exception as e:
            logger.error(f"❌ 停止ESP32 WebSocket服务器失败: {e}")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        stats = self.websocket_manager.get_connection_stats()
        
        # 添加从旧适配器迁移的统计信息
        stats.update({
            "websocket_version": "4.0",
            "architecture": "modular_integration",
            "features": [
                "hello_handshake",
                "audio_processing", 
                "text_messaging",
                "tts_streaming",
                "session_management",
                "chunked_audio_sending",
                "opus_encoding",
                "silence_detection",
                "buffer_management"
            ]
        })
        
        return stats
    
    def get_device_list(self) -> list:
        """获取设备列表"""
        devices = self.websocket_manager.get_device_list()
        
        # 为每个设备添加从旧适配器迁移的信息
        for device in devices:
            device.update({
                "websocket_version": "4.0",
                "supported_features": [
                    "audio_streaming",
                    "text_messaging", 
                    "tts_playback",
                    "session_persistence"
                ]
            })
        
        return devices


# 全局实例
_esp32_websocket_handler: Optional[ESP32WebSocketHandler] = None


def get_esp32_websocket_handler() -> ESP32WebSocketHandler:
    """获取ESP32 WebSocket处理器实例"""
    global _esp32_websocket_handler
    if _esp32_websocket_handler is None:
        _esp32_websocket_handler = ESP32WebSocketHandler()
    return _esp32_websocket_handler


def reset_esp32_websocket_handler():
    """重置ESP32 WebSocket处理器实例"""
    global _esp32_websocket_handler
    _esp32_websocket_handler = None
