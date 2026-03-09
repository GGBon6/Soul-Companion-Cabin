"""
ESP32 TTS服务集成器
ESP32 TTS Service Integration
集成现有TTS服务到ESP32新架构中，解决音频格式转换和协议适配问题
参考开源项目的TTS处理模式，优化音频分帧和发送流程
"""

import asyncio
import time
import struct
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
import logging

from app.shared.services.tts_service import TTSService, get_tts_service
from ..audio import AudioFrame
from ..websocket.protocol import ESP32AudioFormat


class TTSQuality(Enum):
    """TTS合成质量等级"""
    HIGH = "high"           # 高质量
    MEDIUM = "medium"       # 中等质量
    LOW = "low"            # 低质量
    ERROR = "error"        # 错误


@dataclass
class TTSRequest:
    """TTS合成请求"""
    text: str                           # 合成文本
    voice: Optional[str] = None         # 声音ID
    character_id: Optional[str] = None  # 角色ID
    speech_rate: float = 1.0           # 语速
    pitch_rate: float = 1.0            # 音调
    volume: int = 50                   # 音量
    priority: int = 0                  # 优先级 (0=最高)
    metadata: Dict[str, Any] = None    # 元数据


@dataclass
class TTSResult:
    """TTS合成结果"""
    request: TTSRequest                 # 原始请求
    audio_data: bytes                   # 音频数据
    audio_frames: List[AudioFrame]      # 分帧后的音频
    quality: TTSQuality                 # 质量等级
    processing_time: float              # 处理时间（秒）
    audio_duration: float               # 音频时长（秒）
    frame_count: int                    # 帧数
    total_bytes: int                    # 总字节数
    sample_rate: int                    # 采样率
    is_success: bool                    # 是否成功
    error_message: Optional[str] = None # 错误信息
    metadata: Dict[str, Any] = None     # 元数据


@dataclass
class TTSStatistics:
    """TTS统计信息"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cached_requests: int = 0            # 缓存命中次数
    
    total_processing_time: float = 0.0
    total_audio_duration: float = 0.0
    total_characters: int = 0
    total_bytes_generated: int = 0
    
    # 质量统计
    high_quality_count: int = 0
    medium_quality_count: int = 0
    low_quality_count: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        if self.total_requests == 0:
            return 0.0
        return (self.cached_requests / self.total_requests) * 100
    
    @property
    def avg_processing_time(self) -> float:
        """平均处理时间"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_processing_time / self.successful_requests


class ESP32TTSServiceIntegration:
    """ESP32 TTS服务集成器"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.tag = f"ESP32TTS[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # TTS服务实例
        self.tts_service = get_tts_service()
        
        # 音频配置（匹配ESP32要求）
        self.sample_rate = 16000           # 16kHz采样率
        self.frame_duration = 60           # 60ms帧长
        self.channels = 1                  # 单声道
        self.bit_depth = 16               # 16位深度
        self.audio_format = ESP32AudioFormat.PCM  # PCM格式
        
        # 分帧配置
        self.samples_per_frame = (self.sample_rate * self.frame_duration) // 1000  # 960采样点/帧
        self.bytes_per_frame = self.samples_per_frame * 2  # 16位 = 2字节/采样点
        
        # 质量控制
        self.min_text_length = 1           # 最小文本长度
        self.max_text_length = 500         # 最大文本长度
        self.max_processing_time = 10.0    # 最大处理时间
        
        # 缓存配置
        self.enable_cache = True           # 启用缓存
        self.cache_size = 100              # 缓存大小
        self._audio_cache: Dict[str, bytes] = {}
        
        # 统计信息
        self.statistics = TTSStatistics()
        
        # 回调函数
        self._result_callbacks: List[Callable[[TTSResult], None]] = []
        
        self.logger.info(f"[{self.tag}] TTS服务集成器初始化完成")
        self.logger.info(f"[{self.tag}]   采样率: {self.sample_rate}Hz")
        self.logger.info(f"[{self.tag}]   帧长: {self.frame_duration}ms")
        self.logger.info(f"[{self.tag}]   每帧采样点: {self.samples_per_frame}")
        self.logger.info(f"[{self.tag}]   每帧字节数: {self.bytes_per_frame}")
    
    def add_result_callback(self, callback: Callable[[TTSResult], None]) -> None:
        """添加结果回调"""
        self._result_callbacks.append(callback)
    
    async def synthesize_text(self, request: TTSRequest) -> Optional[TTSResult]:
        """
        合成文本为音频
        
        Args:
            request: TTS合成请求
            
        Returns:
            Optional[TTSResult]: 合成结果或None
        """
        if not self._validate_request(request):
            return None
        
        start_time = time.time()
        self.statistics.total_requests += 1
        self.statistics.total_characters += len(request.text)
        
        try:
            self.logger.info(f"[{self.tag}] 🎵 开始TTS合成: '{request.text[:50]}...' "
                           f"({len(request.text)}字符)")
            self.logger.info(f"[{self.tag}] 📋 音频参数: {self.sample_rate}Hz, {self.frame_duration}ms帧长, {self.channels}声道")
            
            # 检查缓存
            cache_key = self._generate_cache_key(request)
            audio_data = None
            
            if self.enable_cache and cache_key in self._audio_cache:
                audio_data = self._audio_cache[cache_key]
                self.statistics.cached_requests += 1
                self.logger.debug(f"[{self.tag}] 使用缓存音频: {len(audio_data)}字节")
            else:
                # 调用TTS服务
                audio_data = await self._call_tts_service(request)
                
                # 添加到缓存
                if self.enable_cache and audio_data:
                    self._add_to_cache(cache_key, audio_data)
            
            if not audio_data:
                self.statistics.failed_requests += 1
                return self._create_error_result(request, "TTS合成失败，未获得音频数据")
            
            # 处理音频数据
            result = await self._process_audio_data(request, audio_data, start_time)
            
            # 触发回调
            if result:
                for callback in self._result_callbacks:
                    try:
                        callback(result)
                    except Exception as e:
                        self.logger.error(f"[{self.tag}] TTS结果回调执行失败: {e}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] TTS合成失败: {e}", exc_info=True)
            self.statistics.failed_requests += 1
            return self._create_error_result(request, str(e))
    
    def _validate_request(self, request: TTSRequest) -> bool:
        """
        验证TTS请求
        
        Args:
            request: TTS请求
            
        Returns:
            bool: 是否有效
        """
        # 检查文本长度
        text_length = len(request.text.strip())
        if text_length < self.min_text_length:
            self.logger.debug(f"[{self.tag}] 文本太短: {text_length} < {self.min_text_length}")
            return False
        
        if text_length > self.max_text_length:
            self.logger.debug(f"[{self.tag}] 文本太长: {text_length} > {self.max_text_length}")
            return False
        
        # 检查文本内容
        if not request.text.strip():
            self.logger.debug(f"[{self.tag}] 文本为空")
            return False
        
        return True
    
    def _generate_cache_key(self, request: TTSRequest) -> str:
        """
        生成缓存键
        
        Args:
            request: TTS请求
            
        Returns:
            str: 缓存键
        """
        # 基于文本、声音、语速等参数生成唯一键
        key_parts = [
            request.text.strip(),
            request.voice or "default",
            str(request.speech_rate),
            str(request.pitch_rate),
            str(request.volume)
        ]
        
        import hashlib
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _add_to_cache(self, cache_key: str, audio_data: bytes) -> None:
        """
        添加到缓存
        
        Args:
            cache_key: 缓存键
            audio_data: 音频数据
        """
        # 如果缓存已满，移除最旧的条目
        if len(self._audio_cache) >= self.cache_size:
            oldest_key = next(iter(self._audio_cache))
            del self._audio_cache[oldest_key]
        
        self._audio_cache[cache_key] = audio_data
        self.logger.debug(f"[{self.tag}] 音频已缓存: {len(audio_data)}字节")
    
    async def _call_tts_service(self, request: TTSRequest) -> Optional[bytes]:
        """
        调用TTS服务
        
        Args:
            request: TTS请求
            
        Returns:
            Optional[bytes]: 音频数据或None
        """
        try:
            # 设置TTS参数
            if request.character_id:
                self.tts_service.set_character(request.character_id)
            
            if request.voice:
                self.tts_service.set_voice(request.voice)
            
            self.tts_service.set_speech_rate(request.speech_rate)
            self.tts_service.set_pitch_rate(request.pitch_rate)
            self.tts_service.set_volume(request.volume)
            
            # 异步调用TTS服务
            audio_data = await self.tts_service.synthesize_async(
                request.text,
                voice=request.voice,
                client_type="esp32"
            )
            
            self.logger.debug(f"[{self.tag}] TTS服务调用成功: {len(audio_data)}字节")
            return audio_data
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] TTS服务调用失败: {e}")
            return None
    
    async def _process_audio_data(self, request: TTSRequest, audio_data: bytes, start_time: float) -> TTSResult:
        """
        处理音频数据
        
        Args:
            request: TTS请求
            audio_data: 原始音频数据
            start_time: 开始时间
            
        Returns:
            TTSResult: 处理结果
        """
        processing_time = time.time() - start_time
        
        # 转换音频格式（如果需要）
        processed_audio = self._convert_audio_format(audio_data)
        
        # 分帧
        audio_frames = self._split_audio_to_frames(processed_audio)
        
        # 计算音频时长
        audio_duration = len(processed_audio) / (self.sample_rate * 2)  # 16位 = 2字节
        
        # 确定质量等级
        quality = self._determine_quality(processed_audio, processing_time, len(request.text))
        
        # 更新统计
        self._update_success_statistics(processing_time, audio_duration, len(processed_audio), quality)
        
        result = TTSResult(
            request=request,
            audio_data=processed_audio,
            audio_frames=audio_frames,
            quality=quality,
            processing_time=processing_time,
            audio_duration=audio_duration,
            frame_count=len(audio_frames),
            total_bytes=len(processed_audio),
            sample_rate=self.sample_rate,
            is_success=True,
            metadata={
                "device_id": self.device_id,
                "timestamp": time.time(),
                "original_size": len(audio_data),
                "processed_size": len(processed_audio)
            }
        )
        
        self.logger.info(f"[{self.tag}] ✅ TTS合成完成: {len(audio_frames)}帧, "
                        f"{len(processed_audio)}字节, {audio_duration:.2f}秒, 质量={quality.value}")
        self.logger.info(f"[{self.tag}] 🚀 准备发送音频到ESP32设备...")
        
        return result
    
    def _convert_audio_format(self, audio_data: bytes) -> bytes:
        """
        转换音频格式
        
        Args:
            audio_data: 原始音频数据（WAV格式）
            
        Returns:
            bytes: 转换后的PCM数据
        """
        try:
            # 如果是WAV格式，跳过WAV头部，提取PCM数据
            if audio_data.startswith(b'RIFF') and b'WAVE' in audio_data[:12]:
                # 查找data chunk
                data_offset = audio_data.find(b'data')
                if data_offset != -1:
                    # data chunk header: 'data' + size(4字节)
                    pcm_data = audio_data[data_offset + 8:]
                    self.logger.debug(f"[{self.tag}] WAV转PCM: {len(audio_data)} -> {len(pcm_data)}字节")
                    return pcm_data
            
            # 如果不是WAV格式，直接返回
            self.logger.debug(f"[{self.tag}] 音频格式无需转换: {len(audio_data)}字节")
            return audio_data
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 音频格式转换失败: {e}")
            return audio_data  # 返回原始数据
    
    def _split_audio_to_frames(self, audio_data: bytes) -> List[AudioFrame]:
        """
        将音频数据分割为帧
        
        Args:
            audio_data: PCM音频数据
            
        Returns:
            List[AudioFrame]: 音频帧列表
        """
        frames = []
        frame_count = 0
        
        # 按固定字节数分帧
        for i in range(0, len(audio_data), self.bytes_per_frame):
            frame_data = audio_data[i:i + self.bytes_per_frame]
            
            # 如果最后一帧不足，用静音填充
            if len(frame_data) < self.bytes_per_frame:
                padding = b'\x00' * (self.bytes_per_frame - len(frame_data))
                frame_data += padding
            
            frame_count += 1
            
            frame = AudioFrame(
                data=frame_data,
                timestamp=time.time() + (frame_count * self.frame_duration / 1000.0),
                sequence_number=frame_count,
                frame_size=len(frame_data),
                sample_rate=self.sample_rate,
                channels=self.channels,
                format="pcm",
                metadata={
                    "device_id": self.device_id,
                    "frame_duration": self.frame_duration,
                    "is_tts_frame": True
                }
            )
            
            frames.append(frame)
        
        self.logger.debug(f"[{self.tag}] 音频分帧完成: {len(audio_data)}字节 -> {len(frames)}帧")
        
        return frames
    
    def _determine_quality(self, audio_data: bytes, processing_time: float, text_length: int) -> TTSQuality:
        """
        确定TTS质量等级
        
        Args:
            audio_data: 音频数据
            processing_time: 处理时间
            text_length: 文本长度
            
        Returns:
            TTSQuality: 质量等级
        """
        # 基于处理时间和音频大小的启发式判断
        if processing_time > self.max_processing_time:
            return TTSQuality.LOW
        
        # 检查音频数据大小是否合理
        expected_min_size = text_length * 100  # 每字符至少100字节音频
        if len(audio_data) < expected_min_size:
            return TTSQuality.LOW
        
        # 基于处理时间判断
        if processing_time < 1.0:
            return TTSQuality.HIGH
        elif processing_time < 3.0:
            return TTSQuality.MEDIUM
        else:
            return TTSQuality.LOW
    
    def _create_error_result(self, request: TTSRequest, error_message: str) -> TTSResult:
        """
        创建错误结果
        
        Args:
            request: TTS请求
            error_message: 错误信息
            
        Returns:
            TTSResult: 错误结果
        """
        return TTSResult(
            request=request,
            audio_data=b'',
            audio_frames=[],
            quality=TTSQuality.ERROR,
            processing_time=0.0,
            audio_duration=0.0,
            frame_count=0,
            total_bytes=0,
            sample_rate=self.sample_rate,
            is_success=False,
            error_message=error_message
        )
    
    def _update_success_statistics(self, processing_time: float, audio_duration: float, 
                                 total_bytes: int, quality: TTSQuality) -> None:
        """
        更新成功统计信息
        
        Args:
            processing_time: 处理时间
            audio_duration: 音频时长
            total_bytes: 总字节数
            quality: 质量等级
        """
        self.statistics.successful_requests += 1
        self.statistics.total_processing_time += processing_time
        self.statistics.total_audio_duration += audio_duration
        self.statistics.total_bytes_generated += total_bytes
        
        # 更新质量统计
        if quality == TTSQuality.HIGH:
            self.statistics.high_quality_count += 1
        elif quality == TTSQuality.MEDIUM:
            self.statistics.medium_quality_count += 1
        elif quality == TTSQuality.LOW:
            self.statistics.low_quality_count += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "device_id": self.device_id,
            "requests": {
                "total": self.statistics.total_requests,
                "successful": self.statistics.successful_requests,
                "failed": self.statistics.failed_requests,
                "cached": self.statistics.cached_requests,
                "success_rate": round(self.statistics.success_rate, 2),
                "cache_hit_rate": round(self.statistics.cache_hit_rate, 2)
            },
            "performance": {
                "avg_processing_time": round(self.statistics.avg_processing_time, 3),
                "total_audio_duration": round(self.statistics.total_audio_duration, 2),
                "total_characters": self.statistics.total_characters,
                "total_bytes_generated": self.statistics.total_bytes_generated
            },
            "quality": {
                "high": self.statistics.high_quality_count,
                "medium": self.statistics.medium_quality_count,
                "low": self.statistics.low_quality_count
            },
            "cache": {
                "enabled": self.enable_cache,
                "size": len(self._audio_cache),
                "max_size": self.cache_size
            },
            "config": {
                "sample_rate": self.sample_rate,
                "frame_duration": self.frame_duration,
                "samples_per_frame": self.samples_per_frame,
                "bytes_per_frame": self.bytes_per_frame
            }
        }
    
    def clear_cache(self) -> None:
        """清空缓存"""
        cache_size = len(self._audio_cache)
        self._audio_cache.clear()
        self.logger.info(f"[{self.tag}] 缓存已清空: {cache_size}个条目")
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        self.statistics = TTSStatistics()
        self.logger.info(f"[{self.tag}] 统计信息已重置")


# 全局TTS集成器字典
_tts_integrations: Dict[str, ESP32TTSServiceIntegration] = {}


def get_esp32_tts_integration(device_id: str) -> ESP32TTSServiceIntegration:
    """
    获取ESP32 TTS服务集成器
    
    Args:
        device_id: 设备ID
        
    Returns:
        ESP32TTSServiceIntegration: TTS服务集成器实例
    """
    if device_id not in _tts_integrations:
        _tts_integrations[device_id] = ESP32TTSServiceIntegration(device_id)
    
    return _tts_integrations[device_id]


def remove_esp32_tts_integration(device_id: str) -> None:
    """
    移除ESP32 TTS服务集成器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _tts_integrations:
        integration = _tts_integrations[device_id]
        integration.clear_cache()
        integration.reset_statistics()
        del _tts_integrations[device_id]
