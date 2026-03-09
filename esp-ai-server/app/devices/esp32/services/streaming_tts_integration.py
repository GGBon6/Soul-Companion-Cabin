"""
ESP32流式TTS集成器
ESP32 Streaming TTS Integration
基于CosyVoice官方示例实现流式语音合成集成
支持分片提交文本，实时获取合成音频并分帧发送
"""

import asyncio
import time
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
import logging

from app.shared.services.streaming_tts_service import (
    StreamingTTSService, 
    StreamingTTSConfig,
    StreamingTTSState
)
from app.shared.services.tts_service import CHARACTER_VOICE_MAP
from dashscope.audio.tts_v2 import AudioFormat
from ..audio import AudioFrame


class StreamingTTSMode(Enum):
    """流式TTS模式"""
    CONTINUOUS = "continuous"      # 持续模式：分片发送文本，实时获取音频
    BATCH = "batch"                # 批处理模式：收集所有文本后一次性发送


@dataclass
class StreamingTTSRequest:
    """流式TTS请求"""
    text_chunks: List[str]         # 文本片段列表
    device_id: str                 # 设备ID
    session_id: str                # 会话ID
    voice: Optional[str] = None    # 音色
    character_id: Optional[str] = None  # 角色ID
    speech_rate: float = 1.0       # 语速
    pitch_rate: float = 1.0        # 音调
    volume: int = 50               # 音量
    metadata: Dict[str, Any] = None  # 元数据


class ESP32StreamingTTSIntegration:
    """ESP32流式TTS集成器"""
    
    def __init__(self, device_id: str, config: Optional[StreamingTTSConfig] = None):
        """
        初始化ESP32流式TTS集成器
        
        Args:
            device_id: 设备ID
            config: 流式TTS配置
        """
        self.device_id = device_id
        self.tag = f"ESP32StreamingTTS[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # 音频配置（匹配ESP32要求）
        self.sample_rate = 16000           # 16kHz采样率
        self.frame_duration = 60           # 60ms帧长
        self.channels = 1                  # 单声道
        self.bit_depth = 16               # 16位深度
        
        # 创建流式TTS配置
        if config is None:
            config = StreamingTTSConfig(
                model="cosyvoice-v2",
                voice="longyue_v2",
                format=AudioFormat.PCM_16000HZ_MONO_16BIT,  # 匹配ESP32要求
                volume=50,
                speech_rate=1.0,
                pitch_rate=1.0,
                max_text_chunk_size=2000,
                max_total_text_size=200000,
                chunk_interval=0.1,
                complete_timeout=600000
            )
        
        # 创建流式TTS服务
        self.streaming_tts = StreamingTTSService(config)
        
        # 音频帧队列
        self._audio_frames: List[AudioFrame] = []
        self._audio_data_buffer: bytes = b""
        
        # 分帧配置
        self.samples_per_frame = (self.sample_rate * self.frame_duration) // 1000  # 960采样点/帧
        self.bytes_per_frame = self.samples_per_frame * 2  # 16位 = 2字节/采样点
        
        # 回调函数
        self._frame_callbacks: List[Callable[[AudioFrame], None]] = []
        self._complete_callbacks: List[Callable[[], None]] = []
        self._error_callbacks: List[Callable[[str], None]] = []
        
        # 状态
        self.is_active = False
        
        # 设置音频数据回调
        self.streaming_tts.add_audio_data_callback(self._on_audio_data)
        self.streaming_tts.add_complete_callback(self._on_complete)
        self.streaming_tts.add_error_callback(self._on_error)
        
        self.logger.info(f"[{self.tag}] 流式TTS集成器初始化完成")
        self.logger.info(f"[{self.tag}]   采样率: {self.sample_rate}Hz")
        self.logger.info(f"[{self.tag}]   帧长: {self.frame_duration}ms")
        self.logger.info(f"[{self.tag}]   每帧字节数: {self.bytes_per_frame}")
    
    def add_frame_callback(self, callback: Callable[[AudioFrame], None]) -> None:
        """添加音频帧回调"""
        self._frame_callbacks.append(callback)
    
    def add_complete_callback(self, callback: Callable[[], None]) -> None:
        """添加完成回调"""
        self._complete_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable[[str], None]) -> None:
        """添加错误回调"""
        self._error_callbacks.append(callback)
    
    def _on_audio_data(self, data: bytes) -> None:
        """音频数据回调：实时处理音频数据并分帧"""
        try:
            # 将音频数据添加到缓冲区
            self._audio_data_buffer += data
            
            # 分帧处理
            while len(self._audio_data_buffer) >= self.bytes_per_frame:
                # 提取一帧数据
                frame_data = self._audio_data_buffer[:self.bytes_per_frame]
                self._audio_data_buffer = self._audio_data_buffer[self.bytes_per_frame:]
                
                # 创建音频帧
                frame = AudioFrame(
                    data=frame_data,
                    timestamp=time.time(),
                    sequence_number=len(self._audio_frames) + 1,
                    frame_size=len(frame_data),
                    sample_rate=self.sample_rate,
                    channels=self.channels,
                    format="pcm",
                    metadata={
                        "device_id": self.device_id,
                        "frame_duration": self.frame_duration,
                        "is_streaming_tts_frame": True
                    }
                )
                
                self._audio_frames.append(frame)
                
                # 触发帧回调
                for callback in self._frame_callbacks:
                    try:
                        callback(frame)
                    except Exception as e:
                        self.logger.error(f"[{self.tag}] 音频帧回调执行失败: {e}")
            
            self.logger.debug(f"[{self.tag}] 音频数据已处理: {len(data)}字节, "
                            f"剩余缓冲区: {len(self._audio_data_buffer)}字节")
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 音频数据处理失败: {e}", exc_info=True)
    
    def _on_complete(self) -> None:
        """完成回调"""
        try:
            # 处理剩余的音频数据
            if self._audio_data_buffer:
                # 用静音填充最后一帧
                padding = b'\x00' * (self.bytes_per_frame - len(self._audio_data_buffer))
                frame_data = self._audio_data_buffer + padding
                
                frame = AudioFrame(
                    data=frame_data,
                    timestamp=time.time(),
                    sequence_number=len(self._audio_frames) + 1,
                    frame_size=len(frame_data),
                    sample_rate=self.sample_rate,
                    channels=self.channels,
                    format="pcm",
                    metadata={
                        "device_id": self.device_id,
                        "frame_duration": self.frame_duration,
                        "is_streaming_tts_frame": True,
                        "is_last_frame": True
                    }
                )
                
                self._audio_frames.append(frame)
                
                # 触发帧回调
                for callback in self._frame_callbacks:
                    try:
                        callback(frame)
                    except Exception as e:
                        self.logger.error(f"[{self.tag}] 音频帧回调执行失败: {e}")
                
                self._audio_data_buffer = b""
            
            self.is_active = False
            
            self.logger.info(f"[{self.tag}] 流式TTS合成完成: {len(self._audio_frames)}帧")
            
            # 触发完成回调
            for callback in self._complete_callbacks:
                try:
                    callback()
                except Exception as e:
                    self.logger.error(f"[{self.tag}] 完成回调执行失败: {e}")
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 完成回调处理失败: {e}", exc_info=True)
    
    def _on_error(self, message: str) -> None:
        """错误回调"""
        try:
            self.is_active = False
            
            self.logger.error(f"[{self.tag}] 流式TTS错误: {message}")
            
            # 触发错误回调
            for callback in self._error_callbacks:
                try:
                    callback(message)
                except Exception as e:
                    self.logger.error(f"[{self.tag}] 错误回调执行失败: {e}")
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 错误回调处理失败: {e}", exc_info=True)
    
    async def synthesize_streaming(self, request: StreamingTTSRequest) -> List[AudioFrame]:
        """
        流式合成文本为音频
        
        Args:
            request: 流式TTS请求
        
        Returns:
            List[AudioFrame]: 音频帧列表
        """
        if self.is_active:
            raise RuntimeError("流式TTS服务正在使用中")
        
        try:
            self.is_active = True
            self._audio_frames.clear()
            self._audio_data_buffer = b""
            
            # 设置音色
            voice = request.voice
            if not voice and request.character_id:
                voice = CHARACTER_VOICE_MAP.get(request.character_id, "longyue_v2")
            
            if voice:
                self.streaming_tts.config.voice = voice
            
            self.streaming_tts.config.speech_rate = request.speech_rate
            self.streaming_tts.config.pitch_rate = request.pitch_rate
            self.streaming_tts.config.volume = request.volume
            
            # 启动流式TTS服务
            self.streaming_tts.start()
            
            self.logger.info(f"[{self.tag}] 🎵 开始流式TTS合成: {len(request.text_chunks)}个文本片段")
            
            # 分片发送文本（基于CosyVoice官方示例）
            for i, text_chunk in enumerate(request.text_chunks):
                # 检查文本长度
                if len(text_chunk) > 2000:
                    self.logger.warning(f"[{self.tag}] 文本片段过长，将截断: {len(text_chunk)}字符")
                    text_chunk = text_chunk[:2000]
                
                # 发送文本片段
                self.streaming_tts.streaming_call(text_chunk)
                
                # 等待一小段时间（模拟流式发送）
                if i < len(request.text_chunks) - 1:  # 不是最后一个片段
                    await asyncio.sleep(0.1)
            
            # 结束流式语音合成
            self.streaming_tts.streaming_complete()
            
            # 等待完成（通过回调处理）
            # 注意：streaming_complete是阻塞的，会等待回调完成
            # 所以这里不需要额外等待
            
            self.logger.info(f"[{self.tag}] ✅ 流式TTS合成完成: {len(self._audio_frames)}帧")
            
            return self._audio_frames.copy()
            
        except Exception as e:
            self.is_active = False
            self.logger.error(f"[{self.tag}] 流式TTS合成失败: {e}", exc_info=True)
            raise
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        tts_stats = self.streaming_tts.get_statistics()
        return {
            "device_id": self.device_id,
            "is_active": self.is_active,
            "audio_frames_count": len(self._audio_frames),
            "buffer_size": len(self._audio_data_buffer),
            "streaming_tts": tts_stats,
            "audio_config": {
                "sample_rate": self.sample_rate,
                "frame_duration": self.frame_duration,
                "samples_per_frame": self.samples_per_frame,
                "bytes_per_frame": self.bytes_per_frame
            }
        }
    
    def reset(self) -> None:
        """重置集成器"""
        self.is_active = False
        self._audio_frames.clear()
        self._audio_data_buffer = b""
        self.streaming_tts.reset()
        self.logger.debug(f"[{self.tag}] 流式TTS集成器已重置")


# 全局流式TTS集成器字典
_streaming_tts_integrations: Dict[str, ESP32StreamingTTSIntegration] = {}


def get_streaming_tts_integration(device_id: str, config: Optional[StreamingTTSConfig] = None) -> ESP32StreamingTTSIntegration:
    """
    获取ESP32流式TTS集成器
    
    Args:
        device_id: 设备ID
        config: 流式TTS配置
    
    Returns:
        ESP32StreamingTTSIntegration: 流式TTS集成器实例
    """
    if device_id not in _streaming_tts_integrations:
        _streaming_tts_integrations[device_id] = ESP32StreamingTTSIntegration(device_id, config)
    
    return _streaming_tts_integrations[device_id]


def remove_streaming_tts_integration(device_id: str) -> None:
    """
    移除ESP32流式TTS集成器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _streaming_tts_integrations:
        integration = _streaming_tts_integrations[device_id]
        integration.reset()
        del _streaming_tts_integrations[device_id]

