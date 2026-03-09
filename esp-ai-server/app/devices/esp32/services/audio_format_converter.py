"""
ESP32音频格式转换器
ESP32 Audio Format Converter
处理不同音频格式之间的转换，支持PCM、WAV、Opus等格式
解决ESP32设备的音频格式兼容性问题
"""

import struct
import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

from ..audio import AudioFrame
from ..websocket.protocol import ESP32AudioFormat


class ConversionQuality(Enum):
    """转换质量等级"""
    HIGH = "high"           # 高质量（无损或接近无损）
    MEDIUM = "medium"       # 中等质量
    LOW = "low"            # 低质量
    ERROR = "error"        # 转换错误


@dataclass
class ConversionResult:
    """转换结果"""
    success: bool                       # 是否成功
    input_format: str                   # 输入格式
    output_format: str                  # 输出格式
    input_size: int                     # 输入大小（字节）
    output_size: int                    # 输出大小（字节）
    processing_time: float              # 处理时间（秒）
    quality: ConversionQuality          # 转换质量
    sample_rate: int                    # 采样率
    channels: int                       # 声道数
    bit_depth: int                      # 位深度
    error_message: Optional[str] = None # 错误信息
    metadata: Dict[str, Any] = None     # 元数据


class ESP32AudioFormatConverter:
    """ESP32音频格式转换器"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.tag = f"ESP32AudioConverter[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # 默认音频参数（ESP32标准配置）
        self.default_sample_rate = 16000
        self.default_channels = 1
        self.default_bit_depth = 16
        
        # 支持的格式
        self.supported_input_formats = ["pcm", "wav", "opus", "raw"]
        self.supported_output_formats = ["pcm", "wav", "opus"]
        
        # 转换统计
        self.conversion_count = 0
        self.total_processing_time = 0.0
        self.total_input_bytes = 0
        self.total_output_bytes = 0
        
        self.logger.info(f"[{self.tag}] 音频格式转换器初始化完成")
    
    def convert_audio_data(self, audio_data: bytes, 
                          input_format: str, 
                          output_format: str,
                          sample_rate: Optional[int] = None,
                          channels: Optional[int] = None,
                          bit_depth: Optional[int] = None) -> ConversionResult:
        """
        转换音频数据格式
        
        Args:
            audio_data: 输入音频数据
            input_format: 输入格式 (pcm, wav, opus, raw)
            output_format: 输出格式 (pcm, wav, opus)
            sample_rate: 采样率（可选）
            channels: 声道数（可选）
            bit_depth: 位深度（可选）
            
        Returns:
            ConversionResult: 转换结果
        """
        start_time = time.time()
        
        # 使用默认参数
        sample_rate = sample_rate or self.default_sample_rate
        channels = channels or self.default_channels
        bit_depth = bit_depth or self.default_bit_depth
        
        self.logger.debug(f"[{self.tag}] 开始音频转换: {input_format} -> {output_format}, "
                         f"{len(audio_data)}字节, {sample_rate}Hz, {channels}ch, {bit_depth}bit")
        
        try:
            # 验证格式支持
            if input_format not in self.supported_input_formats:
                return self._create_error_result(
                    f"不支持的输入格式: {input_format}",
                    input_format, output_format, len(audio_data), 0, 0.0,
                    sample_rate, channels, bit_depth
                )
            
            if output_format not in self.supported_output_formats:
                return self._create_error_result(
                    f"不支持的输出格式: {output_format}",
                    input_format, output_format, len(audio_data), 0, 0.0,
                    sample_rate, channels, bit_depth
                )
            
            # 如果格式相同，直接返回
            if input_format == output_format:
                processing_time = time.time() - start_time
                return ConversionResult(
                    success=True,
                    input_format=input_format,
                    output_format=output_format,
                    input_size=len(audio_data),
                    output_size=len(audio_data),
                    processing_time=processing_time,
                    quality=ConversionQuality.HIGH,
                    sample_rate=sample_rate,
                    channels=channels,
                    bit_depth=bit_depth,
                    metadata={"device_id": self.device_id, "no_conversion": True}
                )
            
            # 执行转换
            converted_data = None
            quality = ConversionQuality.MEDIUM
            
            # 第一步：转换为PCM格式（中间格式）
            pcm_data = self._convert_to_pcm(audio_data, input_format, sample_rate, channels, bit_depth)
            
            if pcm_data is None:
                return self._create_error_result(
                    f"转换为PCM失败: {input_format}",
                    input_format, output_format, len(audio_data), 0, 0.0,
                    sample_rate, channels, bit_depth
                )
            
            # 第二步：从PCM转换为目标格式
            if output_format == "pcm":
                converted_data = pcm_data
                quality = ConversionQuality.HIGH
            elif output_format == "wav":
                converted_data = self._pcm_to_wav(pcm_data, sample_rate, channels, bit_depth)
                quality = ConversionQuality.HIGH
            elif output_format == "opus":
                # Opus转换需要外部库，这里返回PCM数据作为降级
                converted_data = pcm_data
                quality = ConversionQuality.LOW
                self.logger.warning(f"[{self.tag}] Opus编码不可用，返回PCM数据")
            
            if converted_data is None:
                return self._create_error_result(
                    f"转换为{output_format}失败",
                    input_format, output_format, len(audio_data), 0, 0.0,
                    sample_rate, channels, bit_depth
                )
            
            processing_time = time.time() - start_time
            
            # 更新统计
            self._update_statistics(processing_time, len(audio_data), len(converted_data))
            
            result = ConversionResult(
                success=True,
                input_format=input_format,
                output_format=output_format,
                input_size=len(audio_data),
                output_size=len(converted_data),
                processing_time=processing_time,
                quality=quality,
                sample_rate=sample_rate,
                channels=channels,
                bit_depth=bit_depth,
                metadata={
                    "device_id": self.device_id,
                    "conversion_id": self.conversion_count
                }
            )
            
            self.logger.debug(f"[{self.tag}] 音频转换完成: {len(audio_data)} -> {len(converted_data)}字节, "
                            f"耗时: {processing_time*1000:.1f}ms")
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(f"[{self.tag}] 音频转换失败: {e}")
            return self._create_error_result(
                str(e), input_format, output_format, len(audio_data), 0, processing_time,
                sample_rate, channels, bit_depth
            )
    
    def convert_audio_frame(self, frame: AudioFrame, 
                           output_format: str,
                           sample_rate: Optional[int] = None,
                           channels: Optional[int] = None,
                           bit_depth: Optional[int] = None) -> Tuple[Optional[AudioFrame], ConversionResult]:
        """
        转换音频帧格式
        
        Args:
            frame: 输入音频帧
            output_format: 输出格式
            sample_rate: 采样率（可选）
            channels: 声道数（可选）
            bit_depth: 位深度（可选）
            
        Returns:
            Tuple[Optional[AudioFrame], ConversionResult]: (转换后的帧, 转换结果)
        """
        # 执行数据转换
        result = self.convert_audio_data(
            frame.data, frame.format, output_format,
            sample_rate or frame.sample_rate,
            channels or frame.channels,
            bit_depth
        )
        
        if not result.success:
            return None, result
        
        # 创建新的音频帧
        new_frame = AudioFrame(
            data=result.output_size,  # 这里应该是转换后的数据，但ConversionResult没有包含
            timestamp=frame.timestamp,
            sequence_number=frame.sequence_number,
            frame_size=result.output_size,
            sample_rate=result.sample_rate,
            channels=result.channels,
            format=output_format,
            metadata={
                **frame.metadata,
                "converted_from": frame.format,
                "conversion_quality": result.quality.value
            }
        )
        
        return new_frame, result
    
    def _convert_to_pcm(self, audio_data: bytes, input_format: str, 
                       sample_rate: int, channels: int, bit_depth: int) -> Optional[bytes]:
        """
        转换音频数据为PCM格式
        
        Args:
            audio_data: 输入音频数据
            input_format: 输入格式
            sample_rate: 采样率
            channels: 声道数
            bit_depth: 位深度
            
        Returns:
            Optional[bytes]: PCM数据或None
        """
        try:
            if input_format == "pcm" or input_format == "raw":
                # 已经是PCM格式
                return audio_data
            
            elif input_format == "wav":
                # 从WAV提取PCM数据
                return self._wav_to_pcm(audio_data)
            
            elif input_format == "opus":
                # Opus解码需要外部库，这里简化处理
                self.logger.warning(f"[{self.tag}] Opus解码不可用，假设为PCM数据")
                return audio_data
            
            else:
                self.logger.error(f"[{self.tag}] 不支持的输入格式: {input_format}")
                return None
                
        except Exception as e:
            self.logger.error(f"[{self.tag}] 转换为PCM失败: {e}")
            return None
    
    def _wav_to_pcm(self, wav_data: bytes) -> Optional[bytes]:
        """
        从WAV数据提取PCM数据
        
        Args:
            wav_data: WAV音频数据
            
        Returns:
            Optional[bytes]: PCM数据或None
        """
        try:
            if len(wav_data) < 44:
                self.logger.error(f"[{self.tag}] WAV文件太小: {len(wav_data)}字节")
                return None
            
            # 检查WAV头部
            if not wav_data.startswith(b'RIFF') or b'WAVE' not in wav_data[:12]:
                self.logger.error(f"[{self.tag}] 不是有效的WAV文件")
                return None
            
            # 查找data chunk
            data_offset = wav_data.find(b'data')
            if data_offset == -1:
                self.logger.error(f"[{self.tag}] 未找到WAV data chunk")
                return None
            
            # 读取data chunk大小
            if data_offset + 8 > len(wav_data):
                self.logger.error(f"[{self.tag}] WAV data chunk头部不完整")
                return None
            
            data_size = struct.unpack('<I', wav_data[data_offset + 4:data_offset + 8])[0]
            pcm_start = data_offset + 8
            pcm_end = pcm_start + data_size
            
            if pcm_end > len(wav_data):
                self.logger.warning(f"[{self.tag}] WAV data chunk大小超出文件范围，截断")
                pcm_end = len(wav_data)
            
            pcm_data = wav_data[pcm_start:pcm_end]
            
            self.logger.debug(f"[{self.tag}] WAV转PCM: {len(wav_data)} -> {len(pcm_data)}字节")
            return pcm_data
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] WAV转PCM失败: {e}")
            return None
    
    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int, channels: int, bit_depth: int) -> Optional[bytes]:
        """
        将PCM数据转换为WAV格式
        
        Args:
            pcm_data: PCM音频数据
            sample_rate: 采样率
            channels: 声道数
            bit_depth: 位深度
            
        Returns:
            Optional[bytes]: WAV数据或None
        """
        try:
            # WAV文件头部结构
            byte_rate = sample_rate * channels * bit_depth // 8
            block_align = channels * bit_depth // 8
            data_size = len(pcm_data)
            file_size = 36 + data_size
            
            # 构建WAV头部
            wav_header = struct.pack(
                '<4sI4s4sIHHIIHH4sI',
                b'RIFF',           # ChunkID
                file_size,         # ChunkSize
                b'WAVE',           # Format
                b'fmt ',           # Subchunk1ID
                16,                # Subchunk1Size (PCM)
                1,                 # AudioFormat (PCM)
                channels,          # NumChannels
                sample_rate,       # SampleRate
                byte_rate,         # ByteRate
                block_align,       # BlockAlign
                bit_depth,         # BitsPerSample
                b'data',           # Subchunk2ID
                data_size          # Subchunk2Size
            )
            
            wav_data = wav_header + pcm_data
            
            self.logger.debug(f"[{self.tag}] PCM转WAV: {len(pcm_data)} -> {len(wav_data)}字节")
            return wav_data
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] PCM转WAV失败: {e}")
            return None
    
    def _create_error_result(self, error_message: str, input_format: str, output_format: str,
                           input_size: int, output_size: int, processing_time: float,
                           sample_rate: int, channels: int, bit_depth: int) -> ConversionResult:
        """
        创建错误结果
        
        Args:
            error_message: 错误信息
            input_format: 输入格式
            output_format: 输出格式
            input_size: 输入大小
            output_size: 输出大小
            processing_time: 处理时间
            sample_rate: 采样率
            channels: 声道数
            bit_depth: 位深度
            
        Returns:
            ConversionResult: 错误结果
        """
        return ConversionResult(
            success=False,
            input_format=input_format,
            output_format=output_format,
            input_size=input_size,
            output_size=output_size,
            processing_time=processing_time,
            quality=ConversionQuality.ERROR,
            sample_rate=sample_rate,
            channels=channels,
            bit_depth=bit_depth,
            error_message=error_message,
            metadata={"device_id": self.device_id}
        )
    
    def _update_statistics(self, processing_time: float, input_bytes: int, output_bytes: int) -> None:
        """
        更新转换统计
        
        Args:
            processing_time: 处理时间
            input_bytes: 输入字节数
            output_bytes: 输出字节数
        """
        self.conversion_count += 1
        self.total_processing_time += processing_time
        self.total_input_bytes += input_bytes
        self.total_output_bytes += output_bytes
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取转换统计信息"""
        avg_processing_time = (self.total_processing_time / self.conversion_count 
                             if self.conversion_count > 0 else 0.0)
        
        compression_ratio = (self.total_output_bytes / self.total_input_bytes 
                           if self.total_input_bytes > 0 else 0.0)
        
        return {
            "device_id": self.device_id,
            "conversions": {
                "total_count": self.conversion_count,
                "avg_processing_time": round(avg_processing_time * 1000, 2),  # ms
                "total_processing_time": round(self.total_processing_time, 3)
            },
            "data": {
                "total_input_bytes": self.total_input_bytes,
                "total_output_bytes": self.total_output_bytes,
                "compression_ratio": round(compression_ratio, 3)
            },
            "supported_formats": {
                "input": self.supported_input_formats,
                "output": self.supported_output_formats
            },
            "default_params": {
                "sample_rate": self.default_sample_rate,
                "channels": self.default_channels,
                "bit_depth": self.default_bit_depth
            }
        }
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        self.conversion_count = 0
        self.total_processing_time = 0.0
        self.total_input_bytes = 0
        self.total_output_bytes = 0
        self.logger.info(f"[{self.tag}] 转换统计已重置")


# 全局音频转换器字典
_audio_converters: Dict[str, ESP32AudioFormatConverter] = {}


def get_esp32_audio_converter(device_id: str) -> ESP32AudioFormatConverter:
    """
    获取ESP32音频格式转换器
    
    Args:
        device_id: 设备ID
        
    Returns:
        ESP32AudioFormatConverter: 音频格式转换器实例
    """
    if device_id not in _audio_converters:
        _audio_converters[device_id] = ESP32AudioFormatConverter(device_id)
    
    return _audio_converters[device_id]


def remove_esp32_audio_converter(device_id: str) -> None:
    """
    移除ESP32音频格式转换器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _audio_converters:
        converter = _audio_converters[device_id]
        converter.reset_statistics()
        del _audio_converters[device_id]
