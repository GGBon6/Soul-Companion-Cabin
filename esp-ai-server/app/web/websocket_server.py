"""
统一WebSocket服务管理器
Unified WebSocket Server Manager
管理Web客户端和ESP32设备的WebSocket服务器
"""

import asyncio
from typing import Optional

from app.core import settings, logger
from app.web.handlers.websocket_handler import WebSocketHandler
from app.devices.esp32.handlers import get_esp32_websocket_handler


class WebSocketServerManager:
    """WebSocket服务管理器"""
    
    def __init__(self):
        """初始化服务管理器"""
        logger.info("🔧 初始化WebSocket服务管理器...")
        
        # Web客户端处理器
        self.web_handler = WebSocketHandler()
        
        # ESP32设备处理器
        self.esp32_handler = get_esp32_websocket_handler()
        
        # 服务器任务
        self.web_server_task: Optional[asyncio.Task] = None
        self.esp32_server_task: Optional[asyncio.Task] = None
        
        logger.info("✅ WebSocket服务管理器初始化完成")
    
    async def start_all_servers(self):
        """启动所有WebSocket服务器"""
        logger.info("🚀 启动所有WebSocket服务器...")
        
        # 启动Web客户端服务器 (端口8766)
        web_port = settings.PORT
        logger.info(f"📱 启动Web客户端服务器: {settings.HOST}:{web_port}")
        self.web_server_task = asyncio.create_task(
            self.web_handler.start()
        )
        
        # 启动ESP32设备服务器 (端口8767)
        esp32_port = settings.PORT + 1
        logger.info(f"🔌 启动ESP32设备服务器: {settings.HOST}:{esp32_port}")
        self.esp32_server_task = asyncio.create_task(
            self.esp32_handler.start(settings.HOST, esp32_port)
        )
        
        # 等待一小段时间确保服务器启动
        await asyncio.sleep(0.5)
        
        logger.info("✅ 所有WebSocket服务器启动完成")
        logger.info("")
        logger.info("📋 服务器信息:")
        logger.info(f"   Web客户端: ws://{settings.HOST}:{web_port}")
        logger.info(f"   ESP32设备: ws://{settings.HOST}:{esp32_port}")
        logger.info("")
        
        # 等待所有服务器运行
        await asyncio.gather(
            self.web_server_task,
            self.esp32_server_task,
            return_exceptions=True
        )
    
    async def stop_all_servers(self):
        """停止所有WebSocket服务器"""
        logger.info("⏹️ 停止所有WebSocket服务器...")
        
        tasks_to_cancel = []
        
        if self.web_server_task and not self.web_server_task.done():
            tasks_to_cancel.append(self.web_server_task)
        
        if self.esp32_server_task and not self.esp32_server_task.done():
            tasks_to_cancel.append(self.esp32_server_task)
        
        if tasks_to_cancel:
            for task in tasks_to_cancel:
                task.cancel()
            
            # 等待任务取消完成
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        
        logger.info("✅ 所有WebSocket服务器已停止")
    
    def get_server_status(self) -> dict:
        """获取服务器状态"""
        return {
            "web_server": {
                "running": self.web_server_task and not self.web_server_task.done(),
                "port": settings.PORT,
                "endpoint": f"ws://{settings.HOST}:{settings.PORT}"
            },
            "esp32_server": {
                "running": self.esp32_server_task and not self.esp32_server_task.done(),
                "port": settings.PORT + 1,
                "endpoint": f"ws://{settings.HOST}:{settings.PORT + 1}"
            },
            "connected_devices": self.esp32_handler.get_connected_devices()
        }
    
    async def send_to_esp32_device(self, device_id: str, message_type: str, data: dict) -> bool:
        """向指定ESP32设备发送消息"""
        return await self.esp32_handler.send_to_device(device_id, message_type, data)
    
    async def broadcast_to_esp32_devices(self, message_type: str, data: dict) -> int:
        """向所有ESP32设备广播消息"""
        return await self.esp32_handler.broadcast_to_devices(message_type, data)


# 全局服务管理器实例
_websocket_server_manager = None

def get_websocket_server_manager() -> WebSocketServerManager:
    """获取WebSocket服务管理器单例"""
    global _websocket_server_manager
    if _websocket_server_manager is None:
        _websocket_server_manager = WebSocketServerManager()
    return _websocket_server_manager
