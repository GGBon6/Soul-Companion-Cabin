"""
WebSocket基础处理器
WebSocket Base Handler
提供WebSocket消息处理器的基础类和验证工具
"""

import json
import time
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

from app.core import logger


class WebSocketBaseHandler(ABC):
    """WebSocket基础消息处理器"""
    
    def __init__(self):
        self.logger = logger
        self.tag = self.__class__.__name__
    
    @property
    @abstractmethod
    def message_type(self) -> str:
        """消息类型"""
        pass
    
    @abstractmethod
    async def handle(self, websocket, message_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        处理消息
        
        Args:
            websocket: WebSocket连接
            message_data: 消息数据
            context: 上下文信息
            
        Returns:
            bool: 是否处理成功
        """
        pass
    
    def validate_message(self, message_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        验证消息格式
        
        Args:
            message_data: 消息数据
            
        Returns:
            Tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        if not isinstance(message_data, dict):
            return False, "消息数据必须是字典格式"
        
        if "type" not in message_data:
            return False, "消息缺少type字段"
        
        return True, None
    
    async def send_response(self, websocket, response_type: str, data: Dict[str, Any]):
        """发送响应消息"""
        try:
            response = {
                "type": response_type,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            
            await websocket.send(json.dumps(response, ensure_ascii=False))
            self.logger.debug(f"[{self.tag}] 发送响应: {response_type}")
                
        except Exception as e:
            self.logger.error(f"[{self.tag}] 发送响应失败: {e}")
    
    async def send_error(self, websocket, error_code: str, error_message: str):
        """发送错误消息"""
        await self.send_response(websocket, "error", {
            "code": error_code,
            "message": error_message
        })
    
    def get_timestamp(self) -> float:
        """获取当前时间戳"""
        return time.time()
    
    def format_timestamp(self, timestamp: float = None) -> str:
        """格式化时间戳"""
        if timestamp is None:
            timestamp = self.get_timestamp()
        return datetime.fromtimestamp(timestamp).isoformat()


class WebSocketMessageValidator:
    """WebSocket消息验证器"""
    
    @staticmethod
    def validate_hello_message(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """验证Hello消息"""
        # 验证消息类型
        if data.get("type") != "hello":
            return False, "消息类型必须是hello"
        
        # 验证协议版本 (兼容 version 和 protocol_version 字段)
        version = data.get("version") or data.get("protocol_version")
        if version is None:
            return False, "Hello消息缺少版本信息 (version 或 protocol_version)"
        
        if not isinstance(version, (str, int, float)):
            return False, "版本信息必须是字符串或数字"
        
        # 验证传输方式
        transport = data.get("transport")
        if transport and transport != "websocket":
            return False, "仅支持websocket传输方式"
        
        # 验证音频参数 (可选)
        audio_params = data.get("audio_params")
        if audio_params and isinstance(audio_params, dict):
            required_audio_fields = ["format", "sample_rate", "channels"]
            for field in required_audio_fields:
                if field not in audio_params:
                    return False, f"音频参数缺少必需字段: {field}"
        
        return True, None
    
    @staticmethod
    def validate_audio_message(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """验证音频消息"""
        if isinstance(data, bytes):
            # 二进制音频数据
            if len(data) == 0:
                return False, "音频数据为空"
            return True, None
        
        if isinstance(data, dict):
            # JSON格式的音频消息
            if "audio_data" not in data:
                return False, "音频消息缺少audio_data字段"
            return True, None
        
        return False, "音频消息格式无效"
    
    @staticmethod
    def validate_text_message(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """验证文本消息"""
        if "content" not in data:
            return False, "文本消息缺少content字段"
        
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            return False, "content必须是非空字符串"
        
        return True, None
    
    @staticmethod
    def validate_control_message(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """验证控制消息"""
        if "command" not in data:
            return False, "控制消息缺少command字段"
        
        command = data.get("command")
        valid_commands = ["start", "stop", "pause", "resume", "abort"]
        
        if command not in valid_commands:
            return False, f"无效的控制命令: {command}"
        
        return True, None
