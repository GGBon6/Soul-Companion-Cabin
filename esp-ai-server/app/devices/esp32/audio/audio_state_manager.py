"""
ESP32音频状态管理器
ESP32 Audio State Manager
管理音频处理的各种状态，包括播放状态、缓冲状态等
参考开源项目的音频状态管理模式
"""

import asyncio
import time
from enum import Enum
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
import logging

from ..websocket.protocol import ESP32AudioFormat


class ESP32AudioState(Enum):
    """ESP32音频状态枚举"""
    IDLE = "idle"                        # 空闲状态
    LISTENING = "listening"              # 监听中（等待语音输入）
    RECORDING = "recording"              # 录音中
    PROCESSING = "processing"            # 音频处理中（ASR识别）
    SPEAKING = "speaking"                # 播放中（TTS输出）
    BUFFERING = "buffering"              # 缓冲中
    ERROR = "error"                      # 错误状态
    DISCONNECTED = "disconnected"        # 连接断开


class ESP32BufferState(Enum):
    """音频缓冲状态枚举"""
    EMPTY = "empty"                      # 缓冲区空
    FILLING = "filling"                  # 填充中
    READY = "ready"                      # 准备就绪
    FULL = "full"                        # 缓冲区满
    OVERFLOW = "overflow"                # 溢出


@dataclass
class ESP32AudioStateInfo:
    """音频状态信息"""
    current_state: ESP32AudioState
    previous_state: Optional[ESP32AudioState] = None
    state_start_time: float = field(default_factory=time.time)
    state_duration: float = 0.0
    
    # 缓冲相关状态
    input_buffer_state: ESP32BufferState = ESP32BufferState.EMPTY
    output_buffer_state: ESP32BufferState = ESP32BufferState.EMPTY
    buffer_usage_percent: float = 0.0
    
    # 音频参数
    sample_rate: int = 16000
    frame_duration: int = 60  # 毫秒
    audio_format: ESP32AudioFormat = ESP32AudioFormat.OPUS
    
    # 统计信息
    total_frames_received: int = 0
    total_frames_sent: int = 0
    total_bytes_received: int = 0
    total_bytes_sent: int = 0
    
    # 错误信息
    last_error: Optional[str] = None
    error_count: int = 0


class ESP32AudioStateManager:
    """ESP32音频状态管理器"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.tag = f"ESP32AudioState[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # 状态信息
        self.state_info = ESP32AudioStateInfo(
            current_state=ESP32AudioState.IDLE
        )
        
        # 状态变化回调
        self._state_change_callbacks: List[Callable] = []
        self._buffer_change_callbacks: List[Callable] = []
        
        # 超时配置
        self.silence_timeout = 3.0  # 静音超时（秒）
        self.speech_timeout = 30.0  # 语音超时（秒）
        self.processing_timeout = 10.0  # 处理超时（秒）
        
        # 异步任务
        self._timeout_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        
        self.logger.info(f"[{self.tag}] 音频状态管理器初始化完成")
    
    def add_state_change_callback(self, callback: Callable[[ESP32AudioState, ESP32AudioState], None]) -> None:
        """添加状态变化回调"""
        self._state_change_callbacks.append(callback)
    
    def add_buffer_change_callback(self, callback: Callable[[ESP32BufferState, ESP32BufferState], None]) -> None:
        """添加缓冲状态变化回调"""
        self._buffer_change_callbacks.append(callback)
    
    async def set_audio_state(self, new_state: ESP32AudioState, reason: str = "") -> None:
        """
        设置音频状态
        
        Args:
            new_state: 新的音频状态
            reason: 状态变化原因
        """
        if new_state == self.state_info.current_state:
            return
        
        old_state = self.state_info.current_state
        current_time = time.time()
        
        # 更新状态持续时间
        self.state_info.state_duration = current_time - self.state_info.state_start_time
        
        # 更新状态信息
        self.state_info.previous_state = old_state
        self.state_info.current_state = new_state
        self.state_info.state_start_time = current_time
        
        self.logger.info(f"[{self.tag}] 音频状态变化: {old_state.value} -> {new_state.value}")
        if reason:
            self.logger.info(f"[{self.tag}] 状态变化原因: {reason}")
        
        # 触发回调
        for callback in self._state_change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(old_state, new_state)
                else:
                    callback(old_state, new_state)
            except Exception as e:
                self.logger.error(f"[{self.tag}] 状态变化回调执行失败: {e}")
        
        # 处理状态相关的逻辑
        await self._handle_state_transition(old_state, new_state)
    
    async def set_buffer_state(self, buffer_type: str, new_buffer_state: ESP32BufferState) -> None:
        """
        设置缓冲状态
        
        Args:
            buffer_type: 缓冲类型 ("input" 或 "output")
            new_buffer_state: 新的缓冲状态
        """
        if buffer_type == "input":
            old_state = self.state_info.input_buffer_state
            self.state_info.input_buffer_state = new_buffer_state
        elif buffer_type == "output":
            old_state = self.state_info.output_buffer_state
            self.state_info.output_buffer_state = new_buffer_state
        else:
            self.logger.error(f"[{self.tag}] 未知的缓冲类型: {buffer_type}")
            return
        
        if old_state != new_buffer_state:
            self.logger.debug(f"[{self.tag}] {buffer_type}缓冲状态变化: {old_state.value} -> {new_buffer_state.value}")
            
            # 触发回调
            for callback in self._buffer_change_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(old_state, new_buffer_state)
                    else:
                        callback(old_state, new_buffer_state)
                except Exception as e:
                    self.logger.error(f"[{self.tag}] 缓冲状态变化回调执行失败: {e}")
    
    def update_audio_stats(self, 
                          frames_received: int = 0, 
                          frames_sent: int = 0,
                          bytes_received: int = 0, 
                          bytes_sent: int = 0) -> None:
        """
        更新音频统计信息
        
        Args:
            frames_received: 接收的帧数
            frames_sent: 发送的帧数
            bytes_received: 接收的字节数
            bytes_sent: 发送的字节数
        """
        self.state_info.total_frames_received += frames_received
        self.state_info.total_frames_sent += frames_sent
        self.state_info.total_bytes_received += bytes_received
        self.state_info.total_bytes_sent += bytes_sent
    
    def set_audio_params(self, sample_rate: int, frame_duration: int, audio_format: ESP32AudioFormat) -> None:
        """
        设置音频参数
        
        Args:
            sample_rate: 采样率
            frame_duration: 帧时长（毫秒）
            audio_format: 音频格式
        """
        self.state_info.sample_rate = sample_rate
        self.state_info.frame_duration = frame_duration
        self.state_info.audio_format = audio_format
        
        self.logger.info(f"[{self.tag}] 音频参数更新:")
        self.logger.info(f"[{self.tag}]   采样率: {sample_rate}Hz")
        self.logger.info(f"[{self.tag}]   帧时长: {frame_duration}ms")
        self.logger.info(f"[{self.tag}]   音频格式: {audio_format.value}")
    
    def set_error(self, error_message: str) -> None:
        """
        设置错误信息
        
        Args:
            error_message: 错误消息
        """
        self.state_info.last_error = error_message
        self.state_info.error_count += 1
        self.logger.error(f"[{self.tag}] 音频错误: {error_message}")
    
    def clear_error(self) -> None:
        """清除错误信息"""
        self.state_info.last_error = None
    
    def get_state_info(self) -> ESP32AudioStateInfo:
        """获取完整的状态信息"""
        # 更新当前状态持续时间
        current_time = time.time()
        self.state_info.state_duration = current_time - self.state_info.state_start_time
        
        return self.state_info
    
    def get_state_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        state_info = self.get_state_info()
        
        return {
            "device_id": self.device_id,
            "audio_state": state_info.current_state.value,
            "state_duration": round(state_info.state_duration, 2),
            "buffer_usage": round(state_info.buffer_usage_percent, 1),
            "frames_received": state_info.total_frames_received,
            "frames_sent": state_info.total_frames_sent,
            "error_count": state_info.error_count,
            "last_error": state_info.last_error
        }
    
    async def _handle_state_transition(self, old_state: ESP32AudioState, new_state: ESP32AudioState) -> None:
        """
        处理状态转换逻辑
        
        Args:
            old_state: 旧状态
            new_state: 新状态
        """
        # 取消之前的超时任务
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        
        # 根据新状态设置超时
        timeout_duration = None
        
        if new_state == ESP32AudioState.LISTENING:
            timeout_duration = self.silence_timeout
        elif new_state == ESP32AudioState.RECORDING:
            timeout_duration = self.speech_timeout
        elif new_state == ESP32AudioState.PROCESSING:
            timeout_duration = self.processing_timeout
        
        if timeout_duration:
            self._timeout_task = asyncio.create_task(
                self._handle_state_timeout(new_state, timeout_duration)
            )
    
    async def _handle_state_timeout(self, state: ESP32AudioState, timeout_duration: float) -> None:
        """
        处理状态超时
        
        Args:
            state: 当前状态
            timeout_duration: 超时时长
        """
        try:
            await asyncio.sleep(timeout_duration)
            
            # 检查状态是否仍然相同
            if self.state_info.current_state == state:
                self.logger.warning(f"[{self.tag}] 状态 {state.value} 超时 ({timeout_duration}s)")
                
                if state == ESP32AudioState.LISTENING:
                    await self.set_audio_state(ESP32AudioState.IDLE, "监听超时")
                elif state == ESP32AudioState.RECORDING:
                    await self.set_audio_state(ESP32AudioState.PROCESSING, "录音超时")
                elif state == ESP32AudioState.PROCESSING:
                    await self.set_audio_state(ESP32AudioState.IDLE, "处理超时")
                    
        except asyncio.CancelledError:
            # 超时任务被取消，正常情况
            pass
        except Exception as e:
            self.logger.error(f"[{self.tag}] 处理状态超时时发生异常: {e}")
    
    async def start_monitoring(self) -> None:
        """开始状态监控"""
        if self._monitor_task and not self._monitor_task.done():
            return
        
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self.logger.info(f"[{self.tag}] 状态监控已启动")
    
    async def stop_monitoring(self) -> None:
        """停止状态监控"""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info(f"[{self.tag}] 状态监控已停止")
    
    async def _monitor_loop(self) -> None:
        """状态监控循环"""
        try:
            while True:
                await asyncio.sleep(1.0)  # 每秒检查一次
                
                # 可以在这里添加其他监控逻辑
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"[{self.tag}] 状态监控循环异常: {e}")


# 全局状态管理器字典
_audio_state_managers: Dict[str, ESP32AudioStateManager] = {}


def get_esp32_audio_state_manager(device_id: str) -> ESP32AudioStateManager:
    """
    获取ESP32音频状态管理器
    
    Args:
        device_id: 设备ID
        
    Returns:
        ESP32AudioStateManager: 音频状态管理器实例
    """
    if device_id not in _audio_state_managers:
        _audio_state_managers[device_id] = ESP32AudioStateManager(device_id)
    
    return _audio_state_managers[device_id]


def remove_esp32_audio_state_manager(device_id: str) -> None:
    """
    移除ESP32音频状态管理器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _audio_state_managers:
        manager = _audio_state_managers[device_id]
        # 停止监控（如果正在运行）
        asyncio.create_task(manager.stop_monitoring())
        del _audio_state_managers[device_id]
