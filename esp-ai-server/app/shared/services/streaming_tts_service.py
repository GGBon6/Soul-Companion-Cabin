"""
流式TTS服务
Streaming TTS Service
基于CosyVoice官方示例实现流式语音合成
支持分片提交文本，实时获取合成结果
"""

import asyncio
import time
import threading
from typing import Optional, List, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import logging

from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat, ResultCallback
import dashscope

from app.core import settings, logger
from app.core.exceptions import TTSError, APIKeyError


class StreamingTTSState(Enum):
    """流式TTS状态"""
    IDLE = "idle"                    # 空闲
    CONNECTING = "connecting"        # 连接中
    STREAMING = "streaming"          # 流式传输中
    COMPLETING = "completing"        # 完成中
    COMPLETED = "completed"          # 已完成
    ERROR = "error"                  # 错误
    CLOSED = "closed"                # 已关闭


@dataclass
class StreamingTTSConfig:
    """流式TTS配置"""
    model: str = "cosyvoice-v2"                    # 模型
    voice: str = "longyue_v2"                      # 音色
    format: AudioFormat = AudioFormat.PCM_16000HZ_MONO_16BIT  # 音频格式
    volume: int = 50                                # 音量 (0-100)
    speech_rate: float = 1.0                      # 语速 (0.5-2.0)
    pitch_rate: float = 1.0                       # 音调 (0.5-2.0)
    max_text_chunk_size: int = 2000               # 单次发送最大文本长度（字符）
    max_total_text_size: int = 200000             # 累计最大文本长度（字符）
    chunk_interval: float = 0.1                   # 文本片段发送间隔（秒）
    complete_timeout: int = 600000                 # 完成超时时间（毫秒，默认10分钟）


class StreamingTTSCallback(ResultCallback):
    """流式TTS回调接口（基于CosyVoice官方示例）"""
    
    def __init__(self, 
                 on_audio_data: Optional[Callable[[bytes], None]] = None,
                 on_complete: Optional[Callable[[], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None,
                 on_open: Optional[Callable[[], None]] = None,
                 on_close: Optional[Callable[[], None]] = None,
                 on_event: Optional[Callable[[str], None]] = None):
        """
        初始化回调接口
        
        Args:
            on_audio_data: 音频数据回调 (data: bytes) -> None
            on_complete: 完成回调 () -> None
            on_error: 错误回调 (message: str) -> None
            on_open: 连接建立回调 () -> None
            on_close: 连接关闭回调 () -> None
            on_event: 事件回调 (message: str) -> None
        """
        self.on_audio_data_callback = on_audio_data
        self.on_complete_callback = on_complete
        self.on_error_callback = on_error
        self.on_open_callback = on_open
        self.on_close_callback = on_close
        self.on_event_callback = on_event
        
        self._logger = logging.getLogger(__name__)
    
    def on_open(self) -> None:
        """连接建立完成"""
        self._logger.debug("流式TTS连接已建立")
        if self.on_open_callback:
            try:
                self.on_open_callback()
            except Exception as e:
                self._logger.error(f"on_open回调执行失败: {e}")
    
    def on_complete(self) -> None:
        """所有合成数据全部返回"""
        self._logger.debug("流式TTS合成完成，所有合成结果已被接收")
        if self.on_complete_callback:
            try:
                self.on_complete_callback()
            except Exception as e:
                self._logger.error(f"on_complete回调执行失败: {e}")
    
    def on_error(self, message: str) -> None:
        """发生异常"""
        self._logger.error(f"流式TTS出现异常: {message}")
        if self.on_error_callback:
            try:
                self.on_error_callback(message)
            except Exception as e:
                self._logger.error(f"on_error回调执行失败: {e}")
    
    def on_close(self) -> None:
        """服务已关闭连接"""
        self._logger.debug("流式TTS连接已关闭")
        if self.on_close_callback:
            try:
                self.on_close_callback()
            except Exception as e:
                self._logger.error(f"on_close回调执行失败: {e}")
    
    def on_event(self, message: str) -> None:
        """服务有回复时会被回调"""
        self._logger.debug(f"流式TTS事件: {message}")
        if self.on_event_callback:
            try:
                self.on_event_callback(message)
            except Exception as e:
                self._logger.error(f"on_event回调执行失败: {e}")
    
    def on_data(self, data: bytes) -> None:
        """服务器有合成音频返回时被回调"""
        self._logger.debug(f"流式TTS音频数据: {len(data)}字节")
        if self.on_audio_data_callback:
            try:
                self.on_audio_data_callback(data)
            except Exception as e:
                self._logger.error(f"on_data回调执行失败: {e}")


class StreamingTTSService:
    """流式TTS服务（基于CosyVoice官方示例）"""
    
    def __init__(self, config: Optional[StreamingTTSConfig] = None):
        """
        初始化流式TTS服务
        
        Args:
            config: 流式TTS配置
        """
        self.config = config or StreamingTTSConfig()
        self.logger = logging.getLogger(__name__)
        
        # API Key检查
        self.api_key = settings.DASHSCOPE_API_KEY
        if not self.api_key:
            raise APIKeyError("DASHSCOPE_API_KEY 未配置")
        
        # 设置API Key
        import os
        os.environ["DASHSCOPE_API_KEY"] = str(self.api_key)
        dashscope.api_key = self.api_key
        
        # 状态管理
        self.state = StreamingTTSState.IDLE
        self.synthesizer: Optional[SpeechSynthesizer] = None
        
        # 回调函数
        self._audio_data_callbacks: List[Callable[[bytes], None]] = []
        self._complete_callbacks: List[Callable[[], None]] = []
        self._error_callbacks: List[Callable[[str], None]] = []
        
        # 统计信息
        self.total_text_size = 0
        self.total_audio_bytes = 0
        self.chunk_count = 0
        self.start_time: Optional[float] = None
        self.first_package_delay: Optional[int] = None
        self.last_request_id: Optional[str] = None
        
        # 线程锁
        self._lock = threading.Lock()
        
        self.logger.info("流式TTS服务初始化完成")
    
    def add_audio_data_callback(self, callback: Callable[[bytes], None]) -> None:
        """添加音频数据回调"""
        self._audio_data_callbacks.append(callback)
    
    def add_complete_callback(self, callback: Callable[[], None]) -> None:
        """添加完成回调"""
        self._complete_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable[[str], None]) -> None:
        """添加错误回调"""
        self._error_callbacks.append(callback)
    
    def _create_callback(self) -> StreamingTTSCallback:
        """创建回调接口"""
        def on_audio_data(data: bytes):
            """音频数据回调"""
            self.total_audio_bytes += len(data)
            if self.start_time and self.first_package_delay is None:
                self.first_package_delay = int((time.time() - self.start_time) * 1000)
            
            # 触发所有回调
            for callback in self._audio_data_callbacks:
                try:
                    callback(data)
                except Exception as e:
                    self.logger.error(f"音频数据回调执行失败: {e}")
        
        def on_complete():
            """完成回调"""
            self.state = StreamingTTSState.COMPLETED
            self.logger.info(f"流式TTS合成完成: {self.chunk_count}个文本片段, "
                           f"{self.total_text_size}字符, {self.total_audio_bytes}字节音频")
            
            # 触发所有回调
            for callback in self._complete_callbacks:
                try:
                    callback()
                except Exception as e:
                    self.logger.error(f"完成回调执行失败: {e}")
        
        def on_error(message: str):
            """错误回调"""
            self.state = StreamingTTSState.ERROR
            self.logger.error(f"流式TTS错误: {message}")
            
            # 触发所有回调
            for callback in self._error_callbacks:
                try:
                    callback(message)
                except Exception as e:
                    self.logger.error(f"错误回调执行失败: {e}")
        
        def on_open():
            """连接建立回调"""
            self.state = StreamingTTSState.STREAMING
            self.logger.debug("流式TTS连接已建立")
        
        def on_close():
            """连接关闭回调"""
            self.state = StreamingTTSState.CLOSED
            self.logger.debug("流式TTS连接已关闭")
        
        def on_event(message: str):
            """事件回调"""
            self.logger.debug(f"流式TTS事件: {message}")
            # 可以解析message获取task_id等信息
        
        return StreamingTTSCallback(
            on_audio_data=on_audio_data,
            on_complete=on_complete,
            on_error=on_error,
            on_open=on_open,
            on_close=on_close,
            on_event=on_event
        )
    
    def start(self) -> None:
        """
        启动流式TTS服务
        实例化SpeechSynthesizer类，绑定请求参数和回调接口
        """
        with self._lock:
            if self.state != StreamingTTSState.IDLE:
                raise TTSError(f"流式TTS服务状态不正确: {self.state.value}")
            
            try:
                self.state = StreamingTTSState.CONNECTING
                self.start_time = time.time()
                self.total_text_size = 0
                self.total_audio_bytes = 0
                self.chunk_count = 0
                self.first_package_delay = None
                
                # 创建回调接口
                callback = self._create_callback()
                
                # 实例化SpeechSynthesizer（基于CosyVoice官方示例）
                self.synthesizer = SpeechSynthesizer(
                    model=self.config.model,
                    voice=self.config.voice,
                    format=self.config.format,
                    volume=self.config.volume,
                    speech_rate=self.config.speech_rate,
                    pitch_rate=self.config.pitch_rate,
                    callback=callback
                )
                
                self.logger.info(f"流式TTS服务已启动: {self.config.model}/{self.config.voice}")
                
            except Exception as e:
                self.state = StreamingTTSState.ERROR
                self.logger.error(f"启动流式TTS服务失败: {e}", exc_info=True)
                raise TTSError(f"启动流式TTS服务失败: {e}")
    
    def streaming_call(self, text: str) -> None:
        """
        流式发送待合成文本片段
        
        Args:
            text: 待合成文本片段（长度不得超过2000字符）
        
        Raises:
            TTSError: 如果状态不正确或文本长度超限
        """
        with self._lock:
            if self.state not in [StreamingTTSState.STREAMING, StreamingTTSState.CONNECTING]:
                raise TTSError(f"流式TTS服务状态不正确: {self.state.value}")
            
            if not self.synthesizer:
                raise TTSError("流式TTS服务未启动")
            
            # 检查文本长度
            text_length = len(text)
            if text_length > self.config.max_text_chunk_size:
                raise TTSError(f"文本片段长度超过限制: {text_length} > {self.config.max_text_chunk_size}")
            
            # 检查累计文本长度
            if self.total_text_size + text_length > self.config.max_total_text_size:
                raise TTSError(f"累计文本长度超过限制: {self.total_text_size + text_length} > {self.config.max_total_text_size}")
            
            try:
                # 调用streaming_call方法分片提交文本（基于CosyVoice官方示例）
                self.synthesizer.streaming_call(text)
                
                self.total_text_size += text_length
                self.chunk_count += 1
                
                self.logger.debug(f"流式TTS文本片段已发送: {text_length}字符 (累计: {self.total_text_size}字符)")
                
            except Exception as e:
                self.state = StreamingTTSState.ERROR
                self.logger.error(f"流式TTS发送文本片段失败: {e}", exc_info=True)
                raise TTSError(f"流式TTS发送文本片段失败: {e}")
    
    def streaming_complete(self, complete_timeout_millis: Optional[int] = None) -> None:
        """
        结束流式语音合成
        
        Args:
            complete_timeout_millis: 等待时间（毫秒），默认使用配置值
        
        Raises:
            TTSError: 如果状态不正确
        """
        with self._lock:
            if self.state not in [StreamingTTSState.STREAMING, StreamingTTSState.CONNECTING]:
                raise TTSError(f"流式TTS服务状态不正确: {self.state.value}")
            
            if not self.synthesizer:
                raise TTSError("流式TTS服务未启动")
            
            try:
                self.state = StreamingTTSState.COMPLETING
                
                # 调用streaming_complete方法结束流式语音合成（基于CosyVoice官方示例）
                timeout = complete_timeout_millis or self.config.complete_timeout
                self.synthesizer.streaming_complete(complete_timeout_millis=timeout)
                
                # 获取统计信息
                self.last_request_id = self.synthesizer.get_last_request_id()
                if self.start_time:
                    self.first_package_delay = self.synthesizer.get_first_package_delay()
                
                self.logger.info(f"流式TTS合成已结束: requestId={self.last_request_id}, "
                               f"首包延迟={self.first_package_delay}ms")
                
            except Exception as e:
                self.state = StreamingTTSState.ERROR
                self.logger.error(f"流式TTS完成失败: {e}", exc_info=True)
                raise TTSError(f"流式TTS完成失败: {e}")
            finally:
                # 无论成功或失败，都要确保状态恢复到可再次启动的空闲状态
                # 这样可以避免第二次调用时因为状态不正确而直接抛出异常
                if self.synthesizer is not None:
                    # 释放当前的synthesizer实例，防止引用未被清理
                    self.synthesizer = None
                self.state = StreamingTTSState.IDLE
                self.logger.debug("流式TTS服务已重置为IDLE状态，准备下一次合成任务")
    
    def get_last_request_id(self) -> Optional[str]:
        """获取上一个任务的request_id"""
        return self.last_request_id
    
    def get_first_package_delay(self) -> Optional[int]:
        """获取首包延迟（毫秒）"""
        return self.first_package_delay
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "state": self.state.value,
            "chunk_count": self.chunk_count,
            "total_text_size": self.total_text_size,
            "total_audio_bytes": self.total_audio_bytes,
            "first_package_delay_ms": self.first_package_delay,
            "last_request_id": self.last_request_id,
            "processing_time": time.time() - self.start_time if self.start_time else 0.0
        }
    
    def reset(self) -> None:
        """重置服务状态"""
        with self._lock:
            self.state = StreamingTTSState.IDLE
            self.synthesizer = None
            self.total_text_size = 0
            self.total_audio_bytes = 0
            self.chunk_count = 0
            self.start_time = None
            self.first_package_delay = None
            self.last_request_id = None
            self.logger.debug("流式TTS服务已重置")

