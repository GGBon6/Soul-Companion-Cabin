"""
ESP32音频协议适配器
ESP32 Audio Protocol Adapter
处理不同音频传输协议的适配和转换
参考开源项目的协议适配模式
"""

import struct
import time
from typing import Dict, Any, Optional, List, Tuple, Union
from enum import Enum
from dataclasses import dataclass
import logging

from .audio_buffer_manager import AudioFrame


class ESP32AudioProtocol(Enum):
    """ESP32音频协议类型"""
    WEBSOCKET_BINARY = "websocket_binary"    # WebSocket二进制协议
    WEBSOCKET_TEXT = "websocket_text"        # WebSocket文本协议
    MQTT_GATEWAY = "mqtt_gateway"            # MQTT Gateway协议
    BINARY_PROTOCOL_V2 = "binary_v2"        # 二进制协议v2
    BINARY_PROTOCOL_V3 = "binary_v3"        # 二进制协议v3
    RAW_AUDIO = "raw_audio"                  # 原始音频数据


@dataclass
class ProtocolHeader:
    """协议头信息"""
    version: int                             # 协议版本
    message_type: int                        # 消息类型
    timestamp: int                           # 时间戳
    payload_size: int                        # 负载大小
    sequence_number: Optional[int] = None    # 序列号
    flags: Optional[int] = None              # 标志位
    reserved: Optional[int] = None           # 保留字段


@dataclass
class ProtocolPacket:
    """协议数据包"""
    header: ProtocolHeader                   # 协议头
    payload: bytes                           # 负载数据
    checksum: Optional[int] = None           # 校验和
    raw_data: Optional[bytes] = None         # 原始数据


class ESP32AudioProtocolAdapter:
    """ESP32音频协议适配器"""
    
    def __init__(self, device_id: str, default_protocol: ESP32AudioProtocol = ESP32AudioProtocol.WEBSOCKET_BINARY):
        self.device_id = device_id
        self.tag = f"ESP32AudioProtocol[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        self.default_protocol = default_protocol
        self.current_protocol = default_protocol
        
        # 协议配置
        self.protocol_configs = {
            ESP32AudioProtocol.BINARY_PROTOCOL_V2: {
                # 匹配ESP32硬件端实际格式：version(2) + type(2) + timestamp(4) + payload_size(4) = 12字节
                # 注意：硬件端没有reserved字段，实际只有12字节头部
                "header_format": ">HHII",  # 大端字节序：version(2) + type(2) + timestamp(4) + payload_size(4)
                "header_size": 12,
                "version": 2,
                "use_checksum": False
            },
            ESP32AudioProtocol.BINARY_PROTOCOL_V3: {
                "header_format": ">HHI",    # 大端字节序：type(2) + reserved(2) + payload_size(4)
                "header_size": 8,
                "version": 3,
                "use_checksum": False
            },
            ESP32AudioProtocol.WEBSOCKET_BINARY: {
                "header_format": None,      # WebSocket自带帧格式
                "header_size": 0,
                "version": 1,
                "use_checksum": False
            }
        }
        
        # 统计信息
        self.stats = {
            "packets_encoded": 0,
            "packets_decoded": 0,
            "bytes_encoded": 0,
            "bytes_decoded": 0,
            "encoding_errors": 0,
            "decoding_errors": 0,
            "protocol_switches": 0
        }
        
        # 序列号管理
        self._sequence_number = 0
        
        self.logger.info(f"[{self.tag}] 音频协议适配器初始化完成")
        self.logger.info(f"[{self.tag}]   默认协议: {default_protocol.value}")
    
    def set_protocol(self, protocol: ESP32AudioProtocol) -> None:
        """
        设置当前协议
        
        Args:
            protocol: 协议类型
        """
        if protocol != self.current_protocol:
            old_protocol = self.current_protocol
            self.current_protocol = protocol
            self.stats["protocol_switches"] += 1
            
            self.logger.info(f"[{self.tag}] 协议切换: {old_protocol.value} -> {protocol.value}")
    
    def encode_audio_frame(self, frame: AudioFrame, 
                          protocol: Optional[ESP32AudioProtocol] = None,
                          message_type: int = 0) -> Optional[bytes]:
        """
        编码音频帧为协议数据包
        
        Args:
            frame: 音频帧
            protocol: 协议类型（可选，使用当前协议）
            message_type: 消息类型
            
        Returns:
            Optional[bytes]: 编码后的数据包或None
        """
        try:
            protocol = protocol or self.current_protocol
            
            if protocol == ESP32AudioProtocol.RAW_AUDIO:
                # 原始音频数据，直接返回
                self.stats["packets_encoded"] += 1
                self.stats["bytes_encoded"] += len(frame.data)
                return frame.data
            
            elif protocol == ESP32AudioProtocol.WEBSOCKET_BINARY:
                # WebSocket二进制协议，直接返回音频数据
                self.stats["packets_encoded"] += 1
                self.stats["bytes_encoded"] += len(frame.data)
                return frame.data
            
            elif protocol in [ESP32AudioProtocol.BINARY_PROTOCOL_V2, ESP32AudioProtocol.BINARY_PROTOCOL_V3]:
                # 二进制协议，需要添加协议头
                packet = self._encode_binary_protocol(frame, protocol, message_type)
                if packet:
                    self.stats["packets_encoded"] += 1
                    self.stats["bytes_encoded"] += len(packet)
                return packet
            
            elif protocol == ESP32AudioProtocol.MQTT_GATEWAY:
                # MQTT Gateway协议
                packet = self._encode_mqtt_protocol(frame, message_type)
                if packet:
                    self.stats["packets_encoded"] += 1
                    self.stats["bytes_encoded"] += len(packet)
                return packet
            
            else:
                self.logger.error(f"[{self.tag}] 不支持的编码协议: {protocol.value}")
                return None
                
        except Exception as e:
            self.logger.error(f"[{self.tag}] 音频帧编码失败: {e}")
            self.stats["encoding_errors"] += 1
            return None
    
    def decode_audio_packet(self, data: bytes, 
                           protocol: Optional[ESP32AudioProtocol] = None) -> Optional[AudioFrame]:
        """
        解码协议数据包为音频帧
        
        Args:
            data: 协议数据包
            protocol: 协议类型（可选，自动检测）
            
        Returns:
            Optional[AudioFrame]: 解码后的音频帧或None
        """
        try:
            if not data or len(data) == 0:
                return None
            
            # 自动检测协议类型
            if protocol is None:
                protocol = self._detect_protocol(data)
            
            if protocol == ESP32AudioProtocol.RAW_AUDIO:
                # 原始音频数据
                frame = self._decode_raw_audio(data)
            
            elif protocol == ESP32AudioProtocol.WEBSOCKET_BINARY:
                # WebSocket二进制协议
                frame = self._decode_websocket_binary(data)
            
            elif protocol in [ESP32AudioProtocol.BINARY_PROTOCOL_V2, ESP32AudioProtocol.BINARY_PROTOCOL_V3]:
                # 二进制协议
                frame = self._decode_binary_protocol(data, protocol)
            
            elif protocol == ESP32AudioProtocol.MQTT_GATEWAY:
                # MQTT Gateway协议
                frame = self._decode_mqtt_protocol(data)
            
            else:
                self.logger.error(f"[{self.tag}] 不支持的解码协议: {protocol.value}")
                return None
            
            if frame:
                self.stats["packets_decoded"] += 1
                self.stats["bytes_decoded"] += len(data)
            
            return frame
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 音频包解码失败: {e}")
            self.stats["decoding_errors"] += 1
            return None
    
    def encode_audio_frames_batch(self, frames: List[AudioFrame],
                                 protocol: Optional[ESP32AudioProtocol] = None,
                                 message_type: int = 0) -> List[bytes]:
        """
        批量编码音频帧
        
        Args:
            frames: 音频帧列表
            protocol: 协议类型
            message_type: 消息类型
            
        Returns:
            List[bytes]: 编码后的数据包列表
        """
        packets = []
        
        for frame in frames:
            packet = self.encode_audio_frame(frame, protocol, message_type)
            if packet:
                packets.append(packet)
        
        if packets:
            self.logger.debug(f"[{self.tag}] 批量编码完成: {len(packets)}个数据包")
        
        return packets
    
    def get_protocol_stats(self) -> Dict[str, Any]:
        """获取协议统计信息"""
        return {
            "device_id": self.device_id,
            "current_protocol": self.current_protocol.value,
            "default_protocol": self.default_protocol.value,
            "packets_encoded": self.stats["packets_encoded"],
            "packets_decoded": self.stats["packets_decoded"],
            "bytes_encoded": self.stats["bytes_encoded"],
            "bytes_decoded": self.stats["bytes_decoded"],
            "encoding_errors": self.stats["encoding_errors"],
            "decoding_errors": self.stats["decoding_errors"],
            "protocol_switches": self.stats["protocol_switches"],
            "error_rate": {
                "encoding": self.stats["encoding_errors"] / max(self.stats["packets_encoded"], 1),
                "decoding": self.stats["decoding_errors"] / max(self.stats["packets_decoded"], 1)
            }
        }
    
    def _encode_binary_protocol(self, frame: AudioFrame, 
                               protocol: ESP32AudioProtocol, 
                               message_type: int) -> Optional[bytes]:
        """
        编码二进制协议
        
        Args:
            frame: 音频帧
            protocol: 协议类型
            message_type: 消息类型
            
        Returns:
            Optional[bytes]: 编码后的数据包
        """
        try:
            config = self.protocol_configs[protocol]
            
            if protocol == ESP32AudioProtocol.BINARY_PROTOCOL_V2:
                # BinaryProtocol2: version(2) + type(2) + timestamp(4) + payload_size(4) = 12字节
                # 匹配ESP32硬件端实际格式，没有reserved字段
                # 确保时间戳在32位无符号整数范围内
                timestamp_ms = int(frame.timestamp * 1000) % (2**32)
                header = struct.pack(
                    config["header_format"],
                    config["version"],          # version
                    message_type,               # type
                    timestamp_ms,               # timestamp (ms)
                    len(frame.data)             # payload_size
                )
            
            elif protocol == ESP32AudioProtocol.BINARY_PROTOCOL_V3:
                # BinaryProtocol3: type(2) + reserved(2) + payload_size(4)
                header = struct.pack(
                    config["header_format"],
                    message_type,               # type
                    0,                          # reserved
                    len(frame.data)             # payload_size
                )
            
            else:
                return None
            
            # 组合头部和负载
            packet = header + frame.data
            
            self.logger.debug(f"[{self.tag}] {protocol.value}编码: "
                            f"header_size={len(header)}, payload_size={len(frame.data)}")
            
            return packet
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 二进制协议编码失败: {e}")
            return None
    
    def _encode_mqtt_protocol(self, frame: AudioFrame, message_type: int) -> Optional[bytes]:
        """
        编码MQTT Gateway协议
        
        Args:
            frame: 音频帧
            message_type: 消息类型
            
        Returns:
            Optional[bytes]: 编码后的数据包
        """
        try:
            # MQTT Gateway协议格式（简化版）
            # 格式：magic(4) + type(1) + seq(4) + timestamp(8) + size(4) + data
            magic = b'MQTT'
            
            self._sequence_number += 1
            
            # 确保时间戳在64位无符号整数范围内
            timestamp_us = int(frame.timestamp * 1000000) % (2**64)
            header = struct.pack(
                ">4sBIQI",
                magic,                          # magic
                message_type,                   # type
                self._sequence_number,          # sequence
                timestamp_us,                   # timestamp (microseconds)
                len(frame.data)                 # size
            )
            
            packet = header + frame.data
            
            self.logger.debug(f"[{self.tag}] MQTT协议编码: "
                            f"seq={self._sequence_number}, size={len(frame.data)}")
            
            return packet
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] MQTT协议编码失败: {e}")
            return None
    
    def _decode_raw_audio(self, data: bytes) -> Optional[AudioFrame]:
        """
        解码原始音频数据
        
        Args:
            data: 原始音频数据
            
        Returns:
            Optional[AudioFrame]: 音频帧
        """
        return AudioFrame(
            data=data,
            timestamp=time.time(),
            sequence_number=0,
            frame_size=len(data),
            sample_rate=16000,  # 默认采样率
            channels=1,
            format="raw"
        )
    
    def _decode_websocket_binary(self, data: bytes) -> Optional[AudioFrame]:
        """
        解码WebSocket二进制数据
        
        Args:
            data: WebSocket二进制数据
            
        Returns:
            Optional[AudioFrame]: 音频帧
        """
        return AudioFrame(
            data=data,
            timestamp=time.time(),
            sequence_number=0,
            frame_size=len(data),
            sample_rate=16000,  # 默认采样率
            channels=1,
            format="opus"  # 通常是Opus格式
        )
    
    def _decode_binary_protocol(self, data: bytes, protocol: ESP32AudioProtocol) -> Optional[AudioFrame]:
        """
        解码二进制协议
        
        Args:
            data: 协议数据
            protocol: 协议类型
            
        Returns:
            Optional[AudioFrame]: 音频帧
        """
        try:
            config = self.protocol_configs[protocol]
            header_size = config["header_size"]
            
            if len(data) < header_size:
                self.logger.error(f"[{self.tag}] 数据包太小，无法解析头部: {len(data)} < {header_size}")
                return None
            
            # 解析头部
            header_data = data[:header_size]
            payload_data = data[header_size:]
            
            if protocol == ESP32AudioProtocol.BINARY_PROTOCOL_V2:
                # BinaryProtocol2: version(2) + type(2) + timestamp(4) + payload_size(4) = 12字节
                # 匹配ESP32硬件端实际格式，没有reserved字段
                version, msg_type, timestamp, payload_size = struct.unpack(
                    config["header_format"], header_data
                )
                
                header = ProtocolHeader(
                    version=version,
                    message_type=msg_type,
                    timestamp=timestamp,
                    payload_size=payload_size,
                    reserved=0  # 硬件端没有reserved字段，设为0
                )
            
            elif protocol == ESP32AudioProtocol.BINARY_PROTOCOL_V3:
                # BinaryProtocol3
                msg_type, reserved, payload_size = struct.unpack(
                    config["header_format"], header_data
                )
                
                header = ProtocolHeader(
                    version=config["version"],
                    message_type=msg_type,
                    timestamp=int(time.time() * 1000),
                    payload_size=payload_size,
                    reserved=reserved
                )
            
            else:
                return None
            
            # 验证负载大小
            if len(payload_data) != header.payload_size:
                self.logger.warning(f"[{self.tag}] 负载大小不匹配: "
                                  f"expected={header.payload_size}, actual={len(payload_data)}")
            
            # 创建音频帧
            frame = AudioFrame(
                data=payload_data,
                timestamp=header.timestamp / 1000.0,  # 转换为秒
                sequence_number=0,
                frame_size=len(payload_data),
                sample_rate=16000,  # 默认采样率
                channels=1,
                format="opus",
                metadata={"protocol_header": header}
            )
            
            self.logger.debug(f"[{self.tag}] {protocol.value}解码: "
                            f"version={header.version}, type={header.message_type}, "
                            f"payload_size={header.payload_size}")
            
            return frame
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 二进制协议解码失败: {e}")
            return None
    
    def _decode_mqtt_protocol(self, data: bytes) -> Optional[AudioFrame]:
        """
        解码MQTT Gateway协议
        
        Args:
            data: MQTT协议数据
            
        Returns:
            Optional[AudioFrame]: 音频帧
        """
        try:
            # MQTT Gateway协议头部大小：4 + 1 + 4 + 8 + 4 = 21字节
            header_size = 21
            
            if len(data) < header_size:
                self.logger.error(f"[{self.tag}] MQTT数据包太小: {len(data)} < {header_size}")
                return None
            
            # 解析头部
            header_data = data[:header_size]
            payload_data = data[header_size:]
            
            magic, msg_type, sequence, timestamp, payload_size = struct.unpack(
                ">4sBIQI", header_data
            )
            
            # 验证魔数
            if magic != b'MQTT':
                self.logger.error(f"[{self.tag}] MQTT协议魔数错误: {magic}")
                return None
            
            # 验证负载大小
            if len(payload_data) != payload_size:
                self.logger.warning(f"[{self.tag}] MQTT负载大小不匹配: "
                                  f"expected={payload_size}, actual={len(payload_data)}")
            
            # 创建音频帧
            frame = AudioFrame(
                data=payload_data,
                timestamp=timestamp / 1000000.0,  # 转换为秒
                sequence_number=sequence,
                frame_size=len(payload_data),
                sample_rate=16000,  # 默认采样率
                channels=1,
                format="opus",
                metadata={"mqtt_type": msg_type}
            )
            
            self.logger.debug(f"[{self.tag}] MQTT协议解码: "
                            f"seq={sequence}, type={msg_type}, payload_size={payload_size}")
            
            return frame
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] MQTT协议解码失败: {e}")
            return None
    
    def _detect_protocol(self, data: bytes) -> ESP32AudioProtocol:
        """
        自动检测协议类型
        
        Args:
            data: 协议数据
            
        Returns:
            ESP32AudioProtocol: 检测到的协议类型
        """
        try:
            if len(data) < 4:
                return ESP32AudioProtocol.RAW_AUDIO
            
            # 检查MQTT魔数
            if data[:4] == b'MQTT':
                return ESP32AudioProtocol.MQTT_GATEWAY
            
            # 检查二进制协议
            if len(data) >= 8:
                try:
                    # 尝试解析为BinaryProtocol3
                    msg_type, reserved, payload_size = struct.unpack(">HHI", data[:8])
                    if payload_size == len(data) - 8:
                        return ESP32AudioProtocol.BINARY_PROTOCOL_V3
                except:
                    pass
            
            if len(data) >= 16:
                try:
                    # 尝试解析为BinaryProtocol2
                    version, msg_type, timestamp, payload_size, reserved = struct.unpack(">HHIII", data[:16])
                    if version == 2 and payload_size == len(data) - 16:
                        return ESP32AudioProtocol.BINARY_PROTOCOL_V2
                except:
                    pass
            
            # 默认为WebSocket二进制协议
            return ESP32AudioProtocol.WEBSOCKET_BINARY
            
        except Exception as e:
            self.logger.debug(f"[{self.tag}] 协议检测失败: {e}")
            return self.current_protocol


# 全局协议适配器字典
_protocol_adapters: Dict[str, ESP32AudioProtocolAdapter] = {}


def get_esp32_audio_protocol_adapter(device_id: str, 
                                    default_protocol: ESP32AudioProtocol = ESP32AudioProtocol.WEBSOCKET_BINARY) -> ESP32AudioProtocolAdapter:
    """
    获取ESP32音频协议适配器
    
    Args:
        device_id: 设备ID
        default_protocol: 默认协议
        
    Returns:
        ESP32AudioProtocolAdapter: 协议适配器实例
    """
    if device_id not in _protocol_adapters:
        _protocol_adapters[device_id] = ESP32AudioProtocolAdapter(device_id, default_protocol)
    
    return _protocol_adapters[device_id]


def remove_esp32_audio_protocol_adapter(device_id: str) -> None:
    """
    移除ESP32音频协议适配器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _protocol_adapters:
        del _protocol_adapters[device_id]
