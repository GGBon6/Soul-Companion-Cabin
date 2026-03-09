"""
消息协议处理器
Message Protocol Handler
处理WebSocket消息的编码和解码
"""

import json
import time
from typing import Dict, Any, Optional, Union
from datetime import datetime
from enum import Enum

from app.core import logger


class ESP32MessageType(Enum):
    """ESP32消息类型枚举"""
    
    # 基础控制消息
    HELLO = "hello"                    # 握手消息
    HEARTBEAT = "heartbeat"            # 心跳消息
    STATUS = "status"                  # 状态查询
    
    # 音频相关消息
    AUDIO = "audio"                    # 音频数据
    START_LISTENING = "start_listening" # 开始监听
    STOP_LISTENING = "stop_listening"   # 停止监听
    
    # 文本相关消息
    TEXT = "text"                      # 文本消息
    INTENT = "intent"                  # 意图识别
    
    # TTS相关消息
    TTS = "tts"                        # TTS消息
    TTS_START = "tts_start"            # TTS开始
    TTS_STOP = "tts_stop"              # TTS结束
    
    # 控制消息
    CONTROL = "control"                # 控制指令
    ABORT = "abort"                    # 中止操作
    ABORT_SPEAKING = "abort_speaking"  # 中止说话
    
    # 其他消息
    ERROR = "error"                    # 错误消息
    UNKNOWN = "unknown"                # 未知消息


class ESP32AudioFormat(Enum):
    """ESP32音频格式枚举"""
    
    PCM = "pcm"                        # PCM格式
    OPUS = "opus"                      # Opus格式
    WAV = "wav"                        # WAV格式
    MP3 = "mp3"                        # MP3格式


class ESP32DeviceCapability(Enum):
    """ESP32设备能力枚举"""
    
    AUDIO_RECORDING = "audio_recording"    # 音频录制
    AUDIO_PLAYBACK = "audio_playback"      # 音频播放
    TEXT_INPUT = "text_input"              # 文本输入
    DISPLAY = "display"                    # 显示功能
    SENSORS = "sensors"                    # 传感器
    NETWORK = "network"                    # 网络连接
    STORAGE = "storage"                    # 存储功能


class ESP32ConnectionState(Enum):
    """ESP32连接状态枚举"""
    
    DISCONNECTED = "disconnected"          # 未连接
    CONNECTING = "connecting"              # 连接中
    HELLO_PENDING = "hello_pending"        # 等待Hello
    AUTHENTICATED = "authenticated"        # 已认证
    ACTIVE = "active"                      # 活跃状态
    ERROR = "error"                        # 错误状态
    TIMEOUT = "timeout"                    # 超时状态


class ESP32ProcessingState(Enum):
    """ESP32处理状态枚举"""
    
    IDLE = "idle"                          # 空闲
    LISTENING = "listening"                # 监听中
    PROCESSING = "processing"              # 处理中
    SPEAKING = "speaking"                  # 说话中
    ERROR = "error"                        # 错误状态


class ESP32ErrorCode(Enum):
    """ESP32错误代码枚举"""
    
    UNKNOWN_ERROR = "unknown_error"        # 未知错误
    INVALID_MESSAGE = "invalid_message"    # 无效消息
    AUDIO_ERROR = "audio_error"            # 音频错误
    NETWORK_ERROR = "network_error"        # 网络错误
    TIMEOUT_ERROR = "timeout_error"        # 超时错误
    AUTHENTICATION_ERROR = "auth_error"    # 认证错误
    PROCESSING_ERROR = "processing_error"  # 处理错误


class MessageFormat(Enum):
    """消息格式"""
    JSON = "json"
    BINARY = "binary"
    TEXT = "text"


class MessagePriority(Enum):
    """消息优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class MessageProtocolHandler:
    """消息协议处理器"""
    
    def __init__(self):
        self.logger = logger
        self.tag = self.__class__.__name__
        
        # 消息序列号
        self._sequence_number = 0
    
    def create_message(self, 
                      message_type: str, 
                      data: Any, 
                      priority: MessagePriority = MessagePriority.NORMAL,
                      target_device: Optional[str] = None) -> Dict[str, Any]:
        """
        创建标准消息格式
        
        Args:
            message_type: 消息类型
            data: 消息数据
            priority: 消息优先级
            target_device: 目标设备ID
            
        Returns:
            Dict[str, Any]: 标准消息格式
        """
        self._sequence_number += 1
        
        message = {
            "type": message_type,
            "data": data,
            "metadata": {
                "sequence": self._sequence_number,
                "timestamp": datetime.now().isoformat(),
                "priority": priority.value,
                "format": MessageFormat.JSON.value
            }
        }
        
        if target_device:
            message["metadata"]["target_device"] = target_device
        
        return message
    
    def encode_message(self, message: Dict[str, Any], format_type: MessageFormat = MessageFormat.JSON) -> Union[str, bytes]:
        """
        编码消息
        
        Args:
            message: 消息对象
            format_type: 编码格式
            
        Returns:
            Union[str, bytes]: 编码后的消息
        """
        try:
            if format_type == MessageFormat.JSON:
                return json.dumps(message, ensure_ascii=False)
            elif format_type == MessageFormat.TEXT:
                return str(message.get("data", ""))
            elif format_type == MessageFormat.BINARY:
                # 对于二进制格式，假设data是bytes类型
                if isinstance(message.get("data"), bytes):
                    return message["data"]
                else:
                    # 将JSON转换为bytes
                    return json.dumps(message, ensure_ascii=False).encode('utf-8')
            else:
                raise ValueError(f"不支持的编码格式: {format_type}")
                
        except Exception as e:
            self.logger.error(f"[{self.tag}] 消息编码失败: {e}")
            return ""
    
    def decode_message(self, raw_message: Union[str, bytes]) -> Optional[Dict[str, Any]]:
        """
        解码消息
        
        Args:
            raw_message: 原始消息数据
            
        Returns:
            Optional[Dict[str, Any]]: 解码后的消息对象
        """
        try:
            if isinstance(raw_message, bytes):
                # 尝试解码为文本
                try:
                    text_message = raw_message.decode('utf-8')
                    return self._decode_text_message(text_message)
                except UnicodeDecodeError:
                    # 如果不是文本，当作二进制数据处理
                    return self._decode_binary_message(raw_message)
            
            elif isinstance(raw_message, str):
                return self._decode_text_message(raw_message)
            
            else:
                self.logger.warning(f"[{self.tag}] 不支持的消息类型: {type(raw_message)}")
                return None
                
        except Exception as e:
            self.logger.error(f"[{self.tag}] 消息解码失败: {e}")
            return None
    
    def _decode_text_message(self, text_message: str) -> Optional[Dict[str, Any]]:
        """解码文本消息"""
        try:
            # 尝试解析JSON
            data = json.loads(text_message)
            
            # 验证消息格式
            if not isinstance(data, dict):
                return None
            
            # 如果没有标准格式，包装成标准格式
            if "type" not in data:
                return {
                    "type": "text",
                    "data": data,
                    "metadata": {
                        "timestamp": datetime.now().isoformat(),
                        "format": MessageFormat.TEXT.value
                    }
                }
            
            return data
            
        except json.JSONDecodeError:
            # 如果不是JSON，当作纯文本处理
            return {
                "type": "text",
                "data": {"content": text_message},
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "format": MessageFormat.TEXT.value
                }
            }
    
    def _decode_binary_message(self, binary_message: bytes) -> Dict[str, Any]:
        """解码二进制消息"""
        return {
            "type": "binary",
            "data": binary_message,
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "format": MessageFormat.BINARY.value,
                "size": len(binary_message)
            }
        }
    
    def validate_message(self, message: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        验证消息格式
        
        Args:
            message: 消息对象
            
        Returns:
            tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        try:
            # 检查必需字段
            if not isinstance(message, dict):
                return False, "消息必须是字典格式"
            
            if "type" not in message:
                return False, "消息缺少type字段"
            
            if "data" not in message:
                return False, "消息缺少data字段"
            
            # 检查消息类型
            message_type = message.get("type")
            if not isinstance(message_type, str) or not message_type.strip():
                return False, "消息类型必须是非空字符串"
            
            # 检查元数据
            metadata = message.get("metadata", {})
            if metadata and not isinstance(metadata, dict):
                return False, "metadata必须是字典格式"
            
            return True, None
            
        except Exception as e:
            return False, f"验证失败: {e}"
    
    def create_response(self, original_message: Dict[str, Any], response_data: Any, status: str = "success") -> Dict[str, Any]:
        """
        创建响应消息
        
        Args:
            original_message: 原始消息
            response_data: 响应数据
            status: 响应状态
            
        Returns:
            Dict[str, Any]: 响应消息
        """
        original_type = original_message.get("type", "unknown")
        original_sequence = original_message.get("metadata", {}).get("sequence")
        
        response = self.create_message(
            message_type=f"{original_type}_response",
            data={
                "status": status,
                "result": response_data
            }
        )
        
        # 添加关联信息
        if original_sequence:
            response["metadata"]["reply_to"] = original_sequence
        
        return response
    
    def create_error_response(self, original_message: Dict[str, Any], error_code: str, error_message: str) -> Dict[str, Any]:
        """
        创建错误响应
        
        Args:
            original_message: 原始消息
            error_code: 错误代码
            error_message: 错误信息
            
        Returns:
            Dict[str, Any]: 错误响应消息
        """
        return self.create_response(
            original_message=original_message,
            response_data={
                "error_code": error_code,
                "error_message": error_message
            },
            status="error"
        )
    
    def get_message_info(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取消息信息
        
        Args:
            message: 消息对象
            
        Returns:
            Dict[str, Any]: 消息信息
        """
        metadata = message.get("metadata", {})
        
        return {
            "type": message.get("type"),
            "sequence": metadata.get("sequence"),
            "timestamp": metadata.get("timestamp"),
            "priority": metadata.get("priority", MessagePriority.NORMAL.value),
            "format": metadata.get("format", MessageFormat.JSON.value),
            "target_device": metadata.get("target_device"),
            "data_size": len(str(message.get("data", "")))
        }
