"""
WebSocket Hello消息处理器
WebSocket Hello Message Handler
处理设备握手和初始化
"""

import json
import time
from typing import Dict, Any

from .base_handler import WebSocketBaseHandler, WebSocketMessageValidator


class WebSocketHelloHandler(WebSocketBaseHandler):
    """WebSocket Hello消息处理器"""
    
    @property
    def message_type(self) -> str:
        """消息类型"""
        return "hello"
    
    async def handle(self, websocket, message_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        处理Hello消息
        
        Args:
            websocket: WebSocket连接
            message_data: Hello消息数据
            context: 上下文信息
            
        Returns:
            bool: 是否处理成功
        """
        try:
            # 验证Hello消息格式
            is_valid, error_msg = WebSocketMessageValidator.validate_hello_message(message_data)
            if not is_valid:
                self.logger.error(f"[{self.tag}] Hello消息验证失败: {error_msg}")
                await self.send_error(websocket, "INVALID_HELLO", error_msg)
                return False
            
            # 提取设备信息
            device_info = self._extract_device_info(message_data)
            context.update(device_info)
            
            # 构建欢迎消息
            welcome_message = await self._build_welcome_message(context, message_data)
            
            # 发送Hello响应
            await self.send_response(websocket, "hello", welcome_message)
            
            self.logger.info(f"[{self.tag}] Hello处理成功: {device_info.get('device_id')}")
            return True
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] Hello处理失败: {e}", exc_info=True)
            await self.send_error(websocket, "HELLO_ERROR", str(e))
            return False
    
    def _extract_device_info(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """提取设备信息"""
        # 获取设备ID (ESP32设备现在会发送基于MAC地址的固定device_id)
        device_id = message_data.get("device_id")
        if not device_id:
            # 备用方案：如果仍然没有device_id，生成一个临时ID
            import uuid
            device_id = f"esp32_temp_{uuid.uuid4().hex[:8]}"
            self.logger.warning(f"ESP32设备未提供device_id，生成临时ID: {device_id}")
            self.logger.warning(f"请确保ESP32设备发送基于MAC地址的固定device_id")
        else:
            # 验证device_id格式
            if device_id.startswith("esp32_") and len(device_id) >= 14:
                self.logger.info(f"✅ 接收到ESP32固定设备ID: {device_id}")
            else:
                self.logger.warning(f"⚠️ 设备ID格式可能不正确: {device_id}")
                self.logger.info(f"建议格式: esp32_aabbccddeeff (基于MAC地址)")
        
        # 兼容version和protocol_version字段
        protocol_version = message_data.get("protocol_version") or message_data.get("version", "1.0")
        
        return {
            "device_id": device_id,
            "client_id": message_data.get("client_id"),
            "protocol_version": str(protocol_version),
            "features": message_data.get("features", {}),
            "audio_params": message_data.get("audio_params", {
                "format": "opus",
                "sample_rate": 16000,
                "channels": 1,
                "frame_duration": 20  # 更新为ESP32新的默认值
            }),
            "device_info": message_data.get("device_info", {}),
            "capabilities": message_data.get("capabilities", [])
        }
    
    async def _build_welcome_message(self, context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建欢迎消息"""
        session_id = f"ws_{context.get('device_id')}_{int(time.time())}"
        context["session_id"] = session_id
        
        return {
            "status": "success",
            "message": "Hello消息处理成功",
            "session_id": session_id,
            "server_time": self.format_timestamp(),
            "server_info": {
                "name": "ESP-AI-Server",
                "version": "2.0.0",
                "capabilities": [
                    "audio_processing",
                    "text_processing", 
                    "intent_recognition",
                    "tts_synthesis",
                    "conversation_memory"
                ]
            },
            "audio_params": {
                "sample_rate": 16000,
                "format": "opus",
                "channels": 1,
                "frame_duration": 60
            },
            "supported_features": [
                "mcp",
                "conversation_history",
                "intent_recognition",
                "emotion_analysis"
            ]
        }
