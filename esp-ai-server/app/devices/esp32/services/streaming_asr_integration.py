"""
ESP32流式ASR集成器
ESP32 Streaming ASR Integration
基于Fun-ASR官方示例的流式识别服务集成
"""

import asyncio
import time
import logging
from typing import Optional, List, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum

from app.shared.services.streaming_asr_service import (
    StreamingASRService,
    get_streaming_asr_service,
    remove_streaming_asr_service,
    RecognitionState
)
from app.core.asr_connection_pool import get_asr_connection_pool
from app.core import logger as core_logger
from ..audio import AudioFrame


class StreamingASRMode(Enum):
    """流式ASR模式"""
    CONTINUOUS = "continuous"    # 持续模式：持续接收音频帧，实时识别
    BATCH = "batch"             # 批处理模式：累积一定帧数后识别


@dataclass
class StreamingASRConfig:
    """流式ASR配置"""
    mode: StreamingASRMode = StreamingASRMode.CONTINUOUS
    frame_interval_ms: int = 100        # 发送音频帧的间隔（毫秒）
    min_frame_size: int = 1024          # 最小帧大小（字节）- 1KB
    max_frame_size: int = 16384         # 最大帧大小（字节）- 16KB
    batch_size: int = 25                # 批处理模式下的批大小（帧数）
    silence_timeout: float = 2.0        # 静音超时（秒）- 超过此时间无音频则停止
    auto_stop: bool = True              # 是否自动停止（检测到静音后）


class ESP32StreamingASRIntegration:
    """ESP32流式ASR集成器"""
    
    def __init__(self, device_id: str, config: Optional[StreamingASRConfig] = None):
        """
        初始化流式ASR集成器
        
        Args:
            device_id: 设备ID
            config: 流式ASR配置
        """
        self.device_id = device_id
        self.tag = f"StreamingASR[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # 配置
        self.config = config or StreamingASRConfig()
        
        # 流式ASR服务
        self.streaming_asr: Optional[StreamingASRService] = None
        self.connection_id: Optional[str] = None
        
        # 状态
        self.is_active = False
        self.last_audio_time: Optional[float] = None
        self.frame_buffer: List[bytes] = []
        self.total_frames_received = 0
        self.total_bytes_received = 0
        self._pending_buffer_bytes = 0
        self._last_flush_time: float = 0.0
        
        # 回调函数
        self._sentence_callbacks: List[Callable[[str], None]] = []
        self._partial_callbacks: List[Callable[[str], None]] = []
        
        # 统计信息
        self.stats = {
            "sessions_started": 0,
            "sessions_stopped": 0,
            "total_frames_sent": 0,
            "total_bytes_sent": 0,
            "sentences_received": 0,
            "partial_results_received": 0
        }
        
        self.logger.info(f"[{self.tag}] 流式ASR集成器初始化完成")
    
    def add_sentence_callback(self, callback: Callable[[str], None]) -> None:
        """添加完整句子回调"""
        self._sentence_callbacks.append(callback)
    
    def add_partial_callback(self, callback: Callable[[str], None]) -> None:
        """添加部分结果回调"""
        self._partial_callbacks.append(callback)
    
    def _flush_frame_buffer(self) -> bool:
        """将缓冲区中的音频帧发送到ASR服务"""
        if not self.frame_buffer:
            self._pending_buffer_bytes = 0
            self._last_flush_time = time.time()
            return True
        
        if not self.streaming_asr:
            self.frame_buffer.clear()
            self._pending_buffer_bytes = 0
            self._last_flush_time = time.time()
            return False
        
        combined = b"".join(self.frame_buffer)
        self.frame_buffer.clear()
        self._pending_buffer_bytes = 0
        
        max_chunk_size = max(self.config.max_frame_size, self.config.min_frame_size, 1024)
        success = True
        
        for offset in range(0, len(combined), max_chunk_size):
            chunk = combined[offset:offset + max_chunk_size]
            if not chunk:
                continue
            chunk_success = self.streaming_asr.send_audio_frame(chunk)
            success = success and chunk_success
            if chunk_success:
                self.stats["total_frames_sent"] += 1
                self.stats["total_bytes_sent"] += len(chunk)
        
        self._last_flush_time = time.time()
        return success
    
    async def start(self) -> bool:
        """
        启动流式识别
        
        Returns:
            bool: 是否启动成功
        """
        if self.is_active:
            self.logger.warning(f"[{self.tag}] 流式识别已在运行中")
            return False
        
        try:
            # 从连接池获取连接
            pool = get_asr_connection_pool()
            self.connection_id = await pool.acquire(
                client_type="esp32",
                client_id=self.device_id,
                timeout=5.0
            )
            
            # 获取流式ASR服务
            self.streaming_asr = get_streaming_asr_service(
                connection_id=self.connection_id,
                client_type="esp32"
            )
            
            # 定义回调函数
            def on_sentence(text: str):
                """完整句子回调"""
                self.stats["sentences_received"] += 1
                self.logger.info(f"[{self.tag}] ✅ 完整句子: '{text}'")
                
                # 触发所有回调
                for callback in self._sentence_callbacks:
                    try:
                        callback(text)
                    except Exception as e:
                        self.logger.error(f"[{self.tag}] 句子回调执行失败: {e}")
            
            def on_partial(text: str):
                """部分结果回调"""
                self.stats["partial_results_received"] += 1
                self.logger.debug(f"[{self.tag}] 🔄 部分结果: '{text}'")
                
                # 触发所有回调
                for callback in self._partial_callbacks:
                    try:
                        callback(text)
                    except Exception as e:
                        self.logger.error(f"[{self.tag}] 部分结果回调执行失败: {e}")
            
            # 启动流式识别
            success = self.streaming_asr.start(
                on_sentence=on_sentence,
                on_partial=on_partial,
                silent=False
            )
            
            if success:
                self.is_active = True
                self.last_audio_time = time.time()
                self.frame_buffer.clear()
                self.total_frames_received = 0
                self.total_bytes_received = 0
                self._pending_buffer_bytes = 0
                self._last_flush_time = time.time()
                self.stats["sessions_started"] += 1
                
                self.logger.info(f"[{self.tag}] 🚀 流式识别已启动 (连接ID: {self.connection_id})")
                return True
            else:
                # 释放连接
                await pool.release(self.connection_id, success=False, processing_time=0.0)
                self.connection_id = None
                return False
                
        except Exception as e:
            self.logger.error(f"[{self.tag}] 启动流式识别失败: {e}", exc_info=True)
            if self.connection_id:
                try:
                    pool = get_asr_connection_pool()
                    await pool.release(self.connection_id, success=False, processing_time=0.0)
                except:
                    pass
                self.connection_id = None
            return False
    
    async def send_audio_frame(self, audio_data: bytes) -> bool:
        """
        发送音频帧到流式识别服务
        
        根据Fun-ASR官方示例：
        - 建议每100ms发送一次音频数据
        - 每次发送1KB-16KB的音频数据
        - 对于16kHz单声道PCM，100ms = 1600样本 = 3200字节
        
        Args:
            audio_data: 音频数据（PCM格式）
        
        Returns:
            bool: 是否发送成功
        """
        if not self.is_active or not self.streaming_asr:
            self.logger.warning(f"[{self.tag}] 流式识别未运行，无法发送音频帧")
            return False
        
        try:
            # 更新最后音频时间
            self.last_audio_time = time.time()
            
            # 根据模式处理
            if self.config.mode == StreamingASRMode.CONTINUOUS:
                flush_interval = max(self.config.frame_interval_ms, 20) / 1000.0
                now = time.time()
                if self._last_flush_time == 0.0:
                    self._last_flush_time = now
                
                self.frame_buffer.append(audio_data)
                self._pending_buffer_bytes += len(audio_data)
                
                should_flush = self._pending_buffer_bytes >= self.config.min_frame_size
                if not should_flush and (now - self._last_flush_time) >= flush_interval:
                    should_flush = True
                
                if should_flush:
                    return self._flush_frame_buffer()
                
                return True
                    
            elif self.config.mode == StreamingASRMode.BATCH:
                # 批处理模式：累积到批大小后发送
                self.frame_buffer.append(audio_data)
                self.total_frames_received += 1
                self.total_bytes_received += len(audio_data)
                
                if len(self.frame_buffer) >= self.config.batch_size:
                    # 合并并发送
                    combined = b''.join(self.frame_buffer)
                    success = self.streaming_asr.send_audio_frame(combined)
                    if success:
                        self.stats["total_frames_sent"] += 1
                        self.stats["total_bytes_sent"] += len(combined)
                    self.frame_buffer.clear()
                    return success
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 发送音频帧失败: {e}", exc_info=True)
            return False
    
    async def stop(self, timeout: float = 2.0) -> bool:
        """
        停止流式识别
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            bool: 是否成功停止
        """
        if not self.is_active:
            return True
        
        try:
            # 发送缓冲区中剩余的音频
            if self.frame_buffer:
                self._flush_frame_buffer()
            
            # 停止流式识别
            if self.streaming_asr:
                success = self.streaming_asr.stop(timeout=timeout)
            else:
                success = True
            
            # 释放连接
            if self.connection_id:
                pool = get_asr_connection_pool()
                processing_time = time.time() - (self.last_audio_time or time.time())
                await pool.release(
                    self.connection_id,
                    success=success,
                    processing_time=processing_time
                )
                self.connection_id = None
            
            self.is_active = False
            self.stats["sessions_stopped"] += 1
            
            self.logger.info(f"[{self.tag}] 🛑 流式识别已停止")
            return success
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 停止流式识别失败: {e}", exc_info=True)
            self.is_active = False
            return False
    
    async def check_silence_timeout(self) -> bool:
        """
        检查静音超时
        
        Returns:
            bool: 是否超时
        """
        if not self.is_active or not self.config.auto_stop:
            return False
        
        if self.last_audio_time is None:
            return False
        
        elapsed = time.time() - self.last_audio_time
        if elapsed > self.config.silence_timeout:
            self.logger.info(f"[{self.tag}] ⏱️ 检测到静音超时 ({elapsed:.2f}s > {self.config.silence_timeout}s)")
            await self.stop()
            return True
        
        return False
    
    def get_results(self) -> Dict[str, Any]:
        """获取识别结果"""
        if not self.streaming_asr:
            return {
                "sentences": [],
                "partial_results": [],
                "latest_partial": None
            }
        
        return self.streaming_asr.get_results()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "device_id": self.device_id,
            "is_active": self.is_active,
            "connection_id": self.connection_id,
            "config": {
                "mode": self.config.mode.value,
                "frame_interval_ms": self.config.frame_interval_ms,
                "min_frame_size": self.config.min_frame_size,
                "max_frame_size": self.config.max_frame_size,
                "batch_size": self.config.batch_size,
                "silence_timeout": self.config.silence_timeout,
                "auto_stop": self.config.auto_stop
            },
            "session_stats": {
                "sessions_started": self.stats["sessions_started"],
                "sessions_stopped": self.stats["sessions_stopped"],
                "total_frames_sent": self.stats["total_frames_sent"],
                "total_bytes_sent": self.stats["total_bytes_sent"],
                "sentences_received": self.stats["sentences_received"],
                "partial_results_received": self.stats["partial_results_received"]
            },
            "current_session": {
                "frames_received": self.total_frames_received,
                "bytes_received": self.total_bytes_received,
                "buffer_size": len(self.frame_buffer),
                "last_audio_time": self.last_audio_time
            }
        }


# 全局流式ASR集成器字典
_streaming_asr_integrations: Dict[str, ESP32StreamingASRIntegration] = {}


def get_streaming_asr_integration(
    device_id: str,
    config: Optional[StreamingASRConfig] = None
) -> ESP32StreamingASRIntegration:
    """
    获取ESP32流式ASR集成器
    
    Args:
        device_id: 设备ID
        config: 流式ASR配置
    
    Returns:
        ESP32StreamingASRIntegration: 流式ASR集成器实例
    """
    if device_id not in _streaming_asr_integrations:
        _streaming_asr_integrations[device_id] = ESP32StreamingASRIntegration(
            device_id=device_id,
            config=config
        )
    
    return _streaming_asr_integrations[device_id]


def remove_streaming_asr_integration(device_id: str) -> None:
    """
    移除ESP32流式ASR集成器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _streaming_asr_integrations:
        integration = _streaming_asr_integrations[device_id]
        if integration.is_active:
            asyncio.create_task(integration.stop())
        del _streaming_asr_integrations[device_id]

