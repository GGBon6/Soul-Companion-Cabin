"""
二进制协议处理器
Binary Protocol Handler
处理ESP32二进制数据协议，包含Opus编解码功能
"""

import struct
import time
import json
import os
from typing import Optional, Tuple, Dict, Any
from enum import Enum
from io import BytesIO

from app.core import logger

# Windows系统需要设置DLL搜索路径
if os.name == 'nt':  # Windows
    # 查找项目根目录（包含opus.dll的目录）
    current_file = os.path.abspath(__file__)
    project_root = current_file
    
    # 向上查找直到找到opus.dll
    for _ in range(10):  # 最多向上查找10级目录
        project_root = os.path.dirname(project_root)
        opus_path = os.path.join(project_root, 'opus.dll')
        if os.path.exists(opus_path):
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(project_root)
                    logger.debug(f"✅ 已添加DLL搜索路径: {project_root}")
                    break
                except Exception as e:
                    logger.debug(f"添加DLL搜索路径失败: {e}")
            else:
                # 对于较老的Python版本，设置PATH
                os.environ['PATH'] = project_root + os.pathsep + os.environ.get('PATH', '')
                logger.debug(f"✅ 已设置PATH环境变量: {project_root}")
                break

# 尝试导入opuslib，如果没有安装或Opus库未找到则使用占位符
try:
    import opuslib
    OPUS_AVAILABLE = True
    logger.info("✅ Opus库导入成功，ESP32音频功能可用")
except (ImportError, Exception) as e:
    OPUS_AVAILABLE = False
    if "Could not find Opus library" in str(e):
        logger.warning("❌ Opus系统库未找到，ESP32音频功能将不可用")
        logger.info("💡 解决方案: 确保opus.dll在项目根目录或系统PATH中")
    else:
        logger.warning(f"❌ opuslib导入失败: {e}")


class BinaryProtocolVersion(Enum):
    """二进制协议版本"""
    VERSION_1 = 1
    VERSION_2 = 2
    VERSION_3 = 3


class BinaryMessageType(Enum):
    """二进制消息类型"""
    AUDIO = 0
    JSON = 1
    CONTROL = 2


class BinaryProtocolHandler:
    """二进制协议处理器"""
    
    def __init__(self):
        self.logger = logger
        self.tag = self.__class__.__name__
        
        # Opus编解码器（按设备ID存储）
        self.opus_decoders: Dict[str, any] = {}
        self.opus_encoders: Dict[str, any] = {}
        
        # 检查Opus库状态
        if OPUS_AVAILABLE:
            logger.info("✅ Opus库可用，ESP32音频功能正常")
        else:
            logger.warning("⚠️ Opus库不可用，ESP32音频功能将不可用")
            logger.info("💡 解决方案: pip install opuslib 或下载 opus.dll 到系统PATH")
    
    def parse_binary_message(self, data: bytes) -> Optional[Dict[str, Any]]:
        """
        解析二进制消息
        
        Args:
            data: 二进制数据
            
        Returns:
            Dict[str, Any]: 解析结果，包含协议信息和载荷数据
        """
        try:
            if len(data) < 4:
                self.logger.warning(f"[{self.tag}] 数据太短，无法解析协议头")
                return None
            
            # 尝试解析协议版本
            version = self._detect_protocol_version(data)
            
            if version == BinaryProtocolVersion.VERSION_1:
                return self._parse_protocol_v1(data)
            elif version == BinaryProtocolVersion.VERSION_2:
                return self._parse_protocol_v2(data)
            elif version == BinaryProtocolVersion.VERSION_3:
                return self._parse_protocol_v3(data)
            else:
                self.logger.warning(f"[{self.tag}] 未知协议版本: {version}")
                return None
                
        except Exception as e:
            self.logger.error(f"[{self.tag}] 解析二进制消息失败: {e}")
            return None
    
    def _detect_protocol_version(self, data: bytes) -> Optional[BinaryProtocolVersion]:
        """检测协议版本"""
        try:
            # 尝试从前两个字节读取版本号
            version_bytes = data[:2]
            version = struct.unpack('>H', version_bytes)[0]  # 大端字节序
            
            if version in [1, 2, 3]:
                return BinaryProtocolVersion(version)
            
            # 如果前两字节不是版本号，可能是旧格式，默认为版本1
            return BinaryProtocolVersion.VERSION_1
            
        except Exception:
            return BinaryProtocolVersion.VERSION_1
    
    def _parse_protocol_v1(self, data: bytes) -> Optional[Dict[str, Any]]:
        """解析协议版本1 (原始音频数据)"""
        return {
            "version": 1,
            "type": "audio",
            "payload": data,
            "payload_size": len(data),
            "timestamp": int(time.time() * 1000)
        }
    
    def _parse_protocol_v2(self, data: bytes) -> Optional[Dict[str, Any]]:
        """
        解析协议版本2 - 匹配ESP32硬件端格式
        ESP32格式: version(2) + type(2) + timestamp(4) + payload_size(4) + payload
        """
        try:
            if len(data) < 12:  # ESP32实际头部长度：12字节
                self.logger.warning(f"[{self.tag}] 协议v2数据长度不足: {len(data)} < 12")
                return None
            
            # 解析头部 (大端字节序) - 匹配ESP32 BinaryProtocol2结构
            header = struct.unpack('>HHII', data[:12])  # 12字节头部
            version, msg_type, timestamp, payload_size = header
            reserved = 0  # ESP32没有reserved字段
            
            # 验证版本
            if version != 2:
                self.logger.warning(f"[{self.tag}] 协议v2版本不匹配: {version}")
                return None
            
            # 验证载荷大小 - 使用12字节头部
            expected_total_size = 12 + payload_size
            if len(data) < expected_total_size:
                self.logger.warning(f"[{self.tag}] 协议v2载荷大小不匹配: 期望{expected_total_size}, 实际{len(data)}")
                return None
            
            # 提取载荷 - 从第12字节开始
            payload = data[12:12+payload_size] if payload_size > 0 else b''
            
            return {
                "version": version,
                "type": "audio" if msg_type == 0 else "json" if msg_type == 1 else "control",
                "reserved": reserved,
                "timestamp": timestamp,
                "payload_size": payload_size,
                "payload": payload
            }
            
        except struct.error as e:
            self.logger.error(f"[{self.tag}] 协议v2解析错误: {e}")
            return None
    
    def _parse_protocol_v3(self, data: bytes) -> Optional[Dict[str, Any]]:
        """
        解析协议版本3
        格式: version(2) + type(2) + payload_size(4) + payload
        """
        try:
            if len(data) < 8:  # 最小头部长度
                self.logger.warning(f"[{self.tag}] 协议v3数据长度不足")
                return None
            
            # 解析头部 (大端字节序)
            header = struct.unpack('>HHI', data[:8])
            version, msg_type, payload_size = header
            
            # 验证版本
            if version != 3:
                self.logger.warning(f"[{self.tag}] 协议v3版本不匹配: {version}")
                return None
            
            # 验证载荷大小
            expected_total_size = 8 + payload_size
            if len(data) < expected_total_size:
                self.logger.warning(f"[{self.tag}] 协议v3载荷大小不匹配: 期望{expected_total_size}, 实际{len(data)}")
                return None
            
            # 提取载荷
            payload = data[8:8+payload_size] if payload_size > 0 else b''
            
            return {
                "version": version,
                "type": "audio" if msg_type == 0 else "json" if msg_type == 1 else "control",
                "payload_size": payload_size,
                "payload": payload,
                "timestamp": int(time.time() * 1000)  # 生成时间戳
            }
            
        except struct.error as e:
            self.logger.error(f"[{self.tag}] 协议v3解析错误: {e}")
            return None
    
    def create_binary_message(self, payload: bytes, version: int = 2, msg_type: int = 0, timestamp: Optional[int] = None) -> bytes:
        """
        创建二进制消息
        
        Args:
            payload: 载荷数据
            version: 协议版本
            msg_type: 消息类型 (0=音频, 1=JSON, 2=控制)
            timestamp: 时间戳 (毫秒)
            
        Returns:
            bytes: 二进制消息数据
        """
        try:
            if timestamp is None:
                timestamp = int(time.time() * 1000)
            
            payload_size = len(payload)
            
            if version == 2:
                # 协议版本2: version(2) + type(2) + reserved(4) + timestamp(4) + payload_size(4) + payload
                header = struct.pack('>HHIII', version, msg_type, 0, timestamp, payload_size)
                return header + payload
            elif version == 3:
                # 协议版本3: version(2) + type(2) + payload_size(4) + payload
                header = struct.pack('>HHI', version, msg_type, payload_size)
                return header + payload
            else:
                # 协议版本1: 原始载荷
                return payload
                
        except Exception as e:
            self.logger.error(f"[{self.tag}] 创建二进制消息失败: {e}")
            return b''
    
    def validate_binary_message(self, data: bytes) -> Tuple[bool, Optional[str]]:
        """
        验证二进制消息格式
        
        Args:
            data: 二进制数据
            
        Returns:
            Tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        if not data:
            return False, "数据为空"
        
        if len(data) < 4:
            return False, "数据长度不足"
        
        try:
            parsed = self.parse_binary_message(data)
            if parsed is None:
                return False, "无法解析协议格式"
            
            # 验证载荷大小
            payload_size = parsed.get("payload_size", 0)
            actual_payload_size = len(parsed.get("payload", b''))
            
            if payload_size != actual_payload_size:
                return False, f"载荷大小不匹配: 声明{payload_size}, 实际{actual_payload_size}"
            
            return True, None
            
        except Exception as e:
            return False, f"验证失败: {e}"
    
    # ==================== Opus 编解码功能 ====================
    
    def _get_or_create_decoder(self, device_id: str, sample_rate: int = 16000, channels: int = 1):
        """获取或创建Opus解码器"""
        if not OPUS_AVAILABLE:
            return None
            
        if device_id not in self.opus_decoders:
            try:
                self.opus_decoders[device_id] = opuslib.Decoder(sample_rate, channels)
            except Exception as e:
                self.logger.error(f"创建Opus解码器失败: {e}")
                return None
        return self.opus_decoders[device_id]
    
    def _get_or_create_encoder(self, device_id: str, sample_rate: int = 16000, channels: int = 1):
        """获取或创建Opus编码器"""
        if not OPUS_AVAILABLE:
            return None
            
        if device_id not in self.opus_encoders:
            try:
                self.opus_encoders[device_id] = opuslib.Encoder(
                    sample_rate, channels, opuslib.APPLICATION_VOIP
                )
            except Exception as e:
                self.logger.error(f"创建Opus编码器失败: {e}")
                return None
        return self.opus_encoders[device_id]
    
    def decode_opus_audio(self, device_id: str, opus_data: bytes, frame_size: int, sample_rate: int) -> Optional[bytes]:
        """解码Opus音频为PCM"""
        decoder = self._get_or_create_decoder(device_id, sample_rate, 1)
        if not decoder:
            self.logger.error("Opus解码器不可用")
            return None
        
        try:
            pcm_data = decoder.decode(opus_data, frame_size)
            return pcm_data
        except Exception as e:
            self.logger.error(f"Opus解码失败: {e}")
            return None
    
    def encode_pcm_to_opus(self, device_id: str, pcm_data: bytes, frame_size: int, sample_rate: int) -> Optional[bytes]:
        """编码PCM音频为Opus"""
        if not OPUS_AVAILABLE:
            self.logger.error("🚨 Opus库不可用，无法进行Opus编码")
            self.logger.error("💡 解决方案: pip install opuslib")
            self.logger.error("💡 或者下载opus.dll到系统PATH")
            return None
            
        encoder = self._get_or_create_encoder(device_id, sample_rate, 1)
        if not encoder:
            self.logger.error(f"🚨 Opus编码器创建失败: device_id={device_id}, sample_rate={sample_rate}")
            return None
        
        try:
            # 验证PCM数据长度
            expected_bytes = frame_size * 2  # 16位 = 2字节
            if len(pcm_data) != expected_bytes:
                self.logger.warning(f"⚠️ PCM数据长度不匹配: 期望{expected_bytes}字节, 实际{len(pcm_data)}字节")
                # 补齐或截断到正确长度
                if len(pcm_data) < expected_bytes:
                    pcm_data += b'\x00' * (expected_bytes - len(pcm_data))
                else:
                    pcm_data = pcm_data[:expected_bytes]
            
            self.logger.debug(f"🎵 Opus编码: PCM长度={len(pcm_data)}, frame_size={frame_size}, sample_rate={sample_rate}")
            opus_data = encoder.encode(pcm_data, frame_size)
            
            if opus_data and len(opus_data) > 0:
                self.logger.debug(f"✅ Opus编码成功: 输出长度={len(opus_data)}字节")
                return opus_data
            else:
                self.logger.error(f"❌ Opus编码返回空数据: PCM长度={len(pcm_data)}, frame_size={frame_size}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Opus编码异常: {e}")
            self.logger.error(f"   PCM长度={len(pcm_data)}, frame_size={frame_size}, sample_rate={sample_rate}")
            import traceback
            self.logger.debug(f"   异常详情: {traceback.format_exc()}")
            return None
    
    # ==================== 音频格式转换功能 ====================
    
    def pcm_to_wav(self, pcm_data: bytes, sample_rate: int, channels: int) -> bytes:
        """将PCM数据转换为WAV格式"""
        import wave
        
        wav_buffer = BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)  # 16位
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        
        return wav_buffer.getvalue()
    
    def audio_to_pcm(self, audio_data: bytes, sample_rate: int, channels: int) -> bytes:
        """
        将音频数据转换为PCM格式
        注意：这里需要根据你的TTS服务返回的格式进行转换
        """
        try:
            import wave
            wav_buffer = BytesIO(audio_data)
            with wave.open(wav_buffer, 'rb') as wav_file:
                # 读取PCM数据
                pcm_data = wav_file.readframes(wav_file.getnframes())
                return pcm_data
        except Exception as e:
            self.logger.error(f"音频格式转换失败: {e}")
            # 如果转换失败，假设已经是PCM格式
            return audio_data
    
    # ==================== Hello消息处理功能 ====================
    
    def parse_hello_message(self, message: str) -> Optional[Dict]:
        """解析Hello消息"""
        try:
            data = json.loads(message)
            if data.get("type") != "hello":
                return None
            return data
        except json.JSONDecodeError:
            return None
    
    def create_hello_response(self, session_id: str, audio_params: Dict) -> str:
        """创建Hello响应消息"""
        response = {
            "type": "hello",
            "transport": "websocket", 
            "session_id": session_id,
            "audio_params": audio_params
        }
        return json.dumps(response)
    
    def create_connection_established_message(self) -> str:
        """创建连接确认消息（备用触发方式）"""
        response = {
            "type": "connection_established",
            "status": "connected",
            "timestamp": time.time()
        }
        return json.dumps(response)
    
    # ==================== 设备资源管理 ====================
    
    def cleanup_device(self, device_id: str):
        """清理设备相关的编解码器"""
        if device_id in self.opus_decoders:
            del self.opus_decoders[device_id]
        if device_id in self.opus_encoders:
            del self.opus_encoders[device_id]
        self.logger.debug(f"🧹 已清理ESP32设备协议资源: {device_id}")


# 全局实例
_binary_protocol_handler: Optional[BinaryProtocolHandler] = None


def get_binary_protocol_handler() -> BinaryProtocolHandler:
    """获取二进制协议处理器实例"""
    global _binary_protocol_handler
    if _binary_protocol_handler is None:
        _binary_protocol_handler = BinaryProtocolHandler()
    return _binary_protocol_handler
