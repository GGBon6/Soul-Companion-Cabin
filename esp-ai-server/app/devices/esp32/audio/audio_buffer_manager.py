"""
ESP32音频缓冲管理器
ESP32 Audio Buffer Manager
管理音频数据的缓冲、存储和流控制
参考开源项目的音频缓冲管理模式
"""

import asyncio
import threading
import time
from typing import Optional, List, Dict, Any, Callable
from collections import deque
from dataclasses import dataclass
import logging
import numpy as np

from .audio_state_manager import ESP32BufferState


@dataclass
class AudioFrame:
    """音频帧数据结构"""
    data: bytes                          # 音频数据
    timestamp: float                     # 时间戳
    sequence_number: int                 # 序列号
    frame_size: int                      # 帧大小
    sample_rate: int                     # 采样率
    channels: int                        # 声道数
    format: str                          # 音频格式
    is_silence: bool = False             # 是否为静音帧
    energy_level: float = 0.0            # 能量级别
    metadata: Dict[str, Any] = None      # 元数据


class CircularBuffer:
    """循环缓冲区实现"""
    
    def __init__(self, max_size: int):
        self.max_size = max_size
        self.buffer = deque(maxlen=max_size)
        self.lock = threading.RLock()
        self._total_added = 0
        self._total_removed = 0
    
    def put(self, item: AudioFrame) -> bool:
        """
        添加数据到缓冲区
        
        Args:
            item: 音频帧
            
        Returns:
            bool: 是否成功添加
        """
        with self.lock:
            if len(self.buffer) >= self.max_size:
                # 缓冲区满，移除最老的数据
                self.buffer.popleft()
            
            self.buffer.append(item)
            self._total_added += 1
            return True
    
    def get(self) -> Optional[AudioFrame]:
        """
        从缓冲区获取数据
        
        Returns:
            Optional[AudioFrame]: 音频帧或None
        """
        with self.lock:
            if self.buffer:
                self._total_removed += 1
                return self.buffer.popleft()
            return None
    
    def peek(self) -> Optional[AudioFrame]:
        """
        查看缓冲区第一个元素但不移除
        
        Returns:
            Optional[AudioFrame]: 音频帧或None
        """
        with self.lock:
            if self.buffer:
                return self.buffer[0]
            return None
    
    def size(self) -> int:
        """获取当前缓冲区大小"""
        with self.lock:
            return len(self.buffer)
    
    def is_empty(self) -> bool:
        """检查缓冲区是否为空"""
        with self.lock:
            return len(self.buffer) == 0
    
    def is_full(self) -> bool:
        """检查缓冲区是否已满"""
        with self.lock:
            return len(self.buffer) >= self.max_size
    
    def clear(self) -> None:
        """清空缓冲区"""
        with self.lock:
            self.buffer.clear()
    
    def get_usage_percent(self) -> float:
        """获取缓冲区使用率百分比"""
        with self.lock:
            return (len(self.buffer) / self.max_size) * 100.0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓冲区统计信息"""
        with self.lock:
            return {
                "current_size": len(self.buffer),
                "max_size": self.max_size,
                "usage_percent": self.get_usage_percent(),
                "total_added": self._total_added,
                "total_removed": self._total_removed,
                "is_empty": self.is_empty(),
                "is_full": self.is_full()
            }


class ESP32AudioBufferManager:
    """ESP32音频缓冲管理器"""
    
    def __init__(self, device_id: str, 
                 input_buffer_size: int = 100,
                 output_buffer_size: int = 50,
                 prebuffer_size: int = 5):
        self.device_id = device_id
        self.tag = f"ESP32AudioBuffer[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # 创建缓冲区
        self.input_buffer = CircularBuffer(input_buffer_size)    # 输入缓冲区（接收音频）
        self.output_buffer = CircularBuffer(output_buffer_size)  # 输出缓冲区（发送音频）
        self.prebuffer = CircularBuffer(prebuffer_size)         # 预缓冲区
        
        # 缓冲区状态回调
        self._buffer_state_callbacks: List[Callable] = []
        
        # 配置参数
        self.low_water_mark = 0.2   # 低水位标记（20%）
        self.high_water_mark = 0.8  # 高水位标记（80%）
        self.prebuffer_threshold = 0.6  # 预缓冲阈值（60%）
        
        # 统计信息
        self.stats = {
            "frames_processed": 0,
            "bytes_processed": 0,
            "buffer_overflows": 0,
            "buffer_underruns": 0,
            "silence_frames_filtered": 0,
            "start_time": time.time()
        }
        
        # 音频参数
        self.sample_rate = 16000
        self.frame_duration = 60  # 毫秒
        self.channels = 1
        
        # 序列号管理
        self._input_sequence = 0
        self._output_sequence = 0
        self._sequence_lock = threading.Lock()
        
        self.logger.info(f"[{self.tag}] 音频缓冲管理器初始化完成")
        self.logger.info(f"[{self.tag}]   输入缓冲区大小: {input_buffer_size}")
        self.logger.info(f"[{self.tag}]   输出缓冲区大小: {output_buffer_size}")
        self.logger.info(f"[{self.tag}]   预缓冲区大小: {prebuffer_size}")
    
    def add_buffer_state_callback(self, callback: Callable[[str, ESP32BufferState], None]) -> None:
        """添加缓冲状态变化回调"""
        self._buffer_state_callbacks.append(callback)
    
    def set_audio_params(self, sample_rate: int, frame_duration: int, channels: int = 1) -> None:
        """
        设置音频参数
        
        Args:
            sample_rate: 采样率
            frame_duration: 帧时长（毫秒）
            channels: 声道数
        """
        self.sample_rate = sample_rate
        self.frame_duration = frame_duration
        self.channels = channels
        
        self.logger.info(f"[{self.tag}] 音频参数更新:")
        self.logger.info(f"[{self.tag}]   采样率: {sample_rate}Hz")
        self.logger.info(f"[{self.tag}]   帧时长: {frame_duration}ms")
        self.logger.info(f"[{self.tag}]   声道数: {channels}")
    
    def put_input_frame(self, audio_data: bytes, audio_format: str = "opus", 
                       metadata: Dict[str, Any] = None) -> bool:
        """
        添加输入音频帧
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            metadata: 元数据
            
        Returns:
            bool: 是否成功添加
        """
        try:
            # 检查数据有效性
            if not audio_data or len(audio_data) == 0:
                self.logger.debug(f"[{self.tag}] 跳过空音频帧")
                return False
            
            # 检查是否为静音帧
            is_silence = self._detect_silence(audio_data, audio_format)
            if is_silence:
                self.stats["silence_frames_filtered"] += 1
                self.logger.debug(f"[{self.tag}] 过滤静音帧")
                return True  # 静音帧也算成功处理
            
            # 计算能量级别
            energy_level = self._calculate_energy(audio_data, audio_format)
            
            # 生成序列号
            with self._sequence_lock:
                self._input_sequence += 1
                sequence_number = self._input_sequence
            
            # 创建音频帧
            frame = AudioFrame(
                data=audio_data,
                timestamp=time.time(),
                sequence_number=sequence_number,
                frame_size=len(audio_data),
                sample_rate=self.sample_rate,
                channels=self.channels,
                format=audio_format,
                is_silence=is_silence,
                energy_level=energy_level,
                metadata=metadata or {}
            )
            
            # 添加到输入缓冲区
            success = self.input_buffer.put(frame)
            
            if success:
                self.stats["frames_processed"] += 1
                self.stats["bytes_processed"] += len(audio_data)
                
                # 检查缓冲区状态（异步执行）
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self._check_buffer_state("input"))
                except RuntimeError:
                    # 没有运行的事件循环，跳过异步检查
                    pass
                
                self.logger.debug(f"[{self.tag}] 输入帧已添加: seq={sequence_number}, size={len(audio_data)}, energy={energy_level:.2f}")
            else:
                self.stats["buffer_overflows"] += 1
                self.logger.warning(f"[{self.tag}] 输入缓冲区溢出")
            
            return success
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 添加输入帧失败: {e}")
            return False
    
    def get_input_frame(self) -> Optional[AudioFrame]:
        """
        获取输入音频帧
        
        Returns:
            Optional[AudioFrame]: 音频帧或None
        """
        try:
            frame = self.input_buffer.get()
            
            if frame:
                self.logger.debug(f"[{self.tag}] 获取输入帧: seq={frame.sequence_number}, size={frame.frame_size}")
                # 异步检查缓冲区状态
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self._check_buffer_state("input"))
                except RuntimeError:
                    pass
            else:
                self.stats["buffer_underruns"] += 1
            
            return frame
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 获取输入帧失败: {e}")
            return None
    
    def put_output_frame(self, audio_data: bytes, audio_format: str = "opus",
                        metadata: Dict[str, Any] = None) -> bool:
        """
        添加输出音频帧
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            metadata: 元数据
            
        Returns:
            bool: 是否成功添加
        """
        try:
            if not audio_data or len(audio_data) == 0:
                self.logger.debug(f"[{self.tag}] 跳过空输出帧")
                return False
            
            # 生成序列号
            with self._sequence_lock:
                self._output_sequence += 1
                sequence_number = self._output_sequence
            
            # 创建音频帧
            frame = AudioFrame(
                data=audio_data,
                timestamp=time.time(),
                sequence_number=sequence_number,
                frame_size=len(audio_data),
                sample_rate=self.sample_rate,
                channels=self.channels,
                format=audio_format,
                metadata=metadata or {}
            )
            
            # 添加到输出缓冲区
            success = self.output_buffer.put(frame)
            
            if success:
                # 检查缓冲区状态（异步执行）
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self._check_buffer_state("output"))
                except RuntimeError:
                    # 没有运行的事件循环，跳过异步检查
                    pass
                
                self.logger.debug(f"[{self.tag}] 输出帧已添加: seq={sequence_number}, size={len(audio_data)}")
            else:
                self.stats["buffer_overflows"] += 1
                self.logger.warning(f"[{self.tag}] 输出缓冲区溢出")
            
            return success
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 添加输出帧失败: {e}")
            return False
    
    def get_output_frame(self) -> Optional[AudioFrame]:
        """
        获取输出音频帧
        
        Returns:
            Optional[AudioFrame]: 音频帧或None
        """
        try:
            frame = self.output_buffer.get()
            
            if frame:
                self.logger.debug(f"[{self.tag}] 获取输出帧: seq={frame.sequence_number}, size={frame.frame_size}")
                # 异步检查缓冲区状态
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self._check_buffer_state("output"))
                except RuntimeError:
                    pass
            
            return frame
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 获取输出帧失败: {e}")
            return None
    
    def get_input_frames_batch(self, max_frames: int = 10) -> List[AudioFrame]:
        """
        批量获取输入音频帧
        
        Args:
            max_frames: 最大帧数
            
        Returns:
            List[AudioFrame]: 音频帧列表
        """
        frames = []
        
        for _ in range(max_frames):
            frame = self.get_input_frame()
            if frame:
                frames.append(frame)
            else:
                break
        
        if frames:
            self.logger.debug(f"[{self.tag}] 批量获取输入帧: {len(frames)}帧")
        
        return frames
    
    def get_output_frames_batch(self, max_frames: int = 5) -> List[AudioFrame]:
        """
        批量获取输出音频帧
        
        Args:
            max_frames: 最大帧数
            
        Returns:
            List[AudioFrame]: 音频帧列表
        """
        frames = []
        
        for _ in range(max_frames):
            frame = self.get_output_frame()
            if frame:
                frames.append(frame)
            else:
                break
        
        if frames:
            self.logger.debug(f"[{self.tag}] 批量获取输出帧: {len(frames)}帧")
        
        return frames
    
    def clear_buffers(self) -> None:
        """清空所有缓冲区"""
        self.input_buffer.clear()
        self.output_buffer.clear()
        self.prebuffer.clear()
        
        self.logger.info(f"[{self.tag}] 所有缓冲区已清空")
    
    def get_buffer_stats(self) -> Dict[str, Any]:
        """获取缓冲区统计信息"""
        current_time = time.time()
        uptime = current_time - self.stats["start_time"]
        
        return {
            "device_id": self.device_id,
            "uptime_seconds": round(uptime, 2),
            "input_buffer": self.input_buffer.get_stats(),
            "output_buffer": self.output_buffer.get_stats(),
            "prebuffer": self.prebuffer.get_stats(),
            "processing_stats": {
                "frames_processed": self.stats["frames_processed"],
                "bytes_processed": self.stats["bytes_processed"],
                "buffer_overflows": self.stats["buffer_overflows"],
                "buffer_underruns": self.stats["buffer_underruns"],
                "silence_frames_filtered": self.stats["silence_frames_filtered"],
                "frames_per_second": round(self.stats["frames_processed"] / uptime, 2) if uptime > 0 else 0,
                "bytes_per_second": round(self.stats["bytes_processed"] / uptime, 2) if uptime > 0 else 0
            }
        }
    
    def _detect_silence(self, audio_data: bytes, audio_format: str) -> bool:
        """
        检测静音帧
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            
        Returns:
            bool: 是否为静音
        """
        try:
            # 对于Opus格式，检查数据长度
            if audio_format.lower() == "opus":
                # Opus静音帧通常很小（< 10字节）
                return len(audio_data) < 10
            
            # 对于PCM格式，检查音频能量
            elif audio_format.lower() in ["pcm", "wav"]:
                # 将字节转换为numpy数组进行分析
                if len(audio_data) < 2:
                    return True
                
                # 假设16位PCM
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                max_amplitude = np.max(np.abs(audio_array))
                
                # 静音阈值
                silence_threshold = 100
                return max_amplitude < silence_threshold
            
            # 其他格式默认不是静音
            return False
            
        except Exception as e:
            self.logger.debug(f"[{self.tag}] 静音检测失败: {e}")
            return False
    
    def _calculate_energy(self, audio_data: bytes, audio_format: str) -> float:
        """
        计算音频能量级别
        
        Args:
            audio_data: 音频数据
            audio_format: 音频格式
            
        Returns:
            float: 能量级别
        """
        try:
            if audio_format.lower() == "opus":
                # 对于Opus，使用数据长度作为能量指标
                return float(len(audio_data))
            
            elif audio_format.lower() in ["pcm", "wav"]:
                if len(audio_data) < 2:
                    return 0.0
                
                # 计算RMS能量
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                return float(rms)
            
            return float(len(audio_data))
            
        except Exception as e:
            self.logger.debug(f"[{self.tag}] 能量计算失败: {e}")
            return 0.0
    
    async def _check_buffer_state(self, buffer_type: str) -> None:
        """
        检查缓冲区状态并触发回调
        
        Args:
            buffer_type: 缓冲区类型 ("input" 或 "output")
        """
        try:
            if buffer_type == "input":
                buffer = self.input_buffer
            elif buffer_type == "output":
                buffer = self.output_buffer
            else:
                return
            
            usage_percent = buffer.get_usage_percent()
            
            # 确定缓冲区状态
            if buffer.is_empty():
                new_state = ESP32BufferState.EMPTY
            elif usage_percent < self.low_water_mark * 100:
                new_state = ESP32BufferState.FILLING
            elif usage_percent > self.high_water_mark * 100:
                new_state = ESP32BufferState.FULL
            elif buffer.is_full():
                new_state = ESP32BufferState.OVERFLOW
            else:
                new_state = ESP32BufferState.READY
            
            # 触发回调
            for callback in self._buffer_state_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(buffer_type, new_state)
                    else:
                        callback(buffer_type, new_state)
                except Exception as e:
                    self.logger.error(f"[{self.tag}] 缓冲状态回调执行失败: {e}")
                    
        except Exception as e:
            self.logger.error(f"[{self.tag}] 检查缓冲区状态失败: {e}")


# 全局缓冲管理器字典
_audio_buffer_managers: Dict[str, ESP32AudioBufferManager] = {}


def get_esp32_audio_buffer_manager(device_id: str, 
                                  input_buffer_size: int = 100,
                                  output_buffer_size: int = 50,
                                  prebuffer_size: int = 5) -> ESP32AudioBufferManager:
    """
    获取ESP32音频缓冲管理器
    
    Args:
        device_id: 设备ID
        input_buffer_size: 输入缓冲区大小
        output_buffer_size: 输出缓冲区大小
        prebuffer_size: 预缓冲区大小
        
    Returns:
        ESP32AudioBufferManager: 音频缓冲管理器实例
    """
    if device_id not in _audio_buffer_managers:
        _audio_buffer_managers[device_id] = ESP32AudioBufferManager(
            device_id, input_buffer_size, output_buffer_size, prebuffer_size
        )
    
    return _audio_buffer_managers[device_id]


def remove_esp32_audio_buffer_manager(device_id: str) -> None:
    """
    移除ESP32音频缓冲管理器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _audio_buffer_managers:
        manager = _audio_buffer_managers[device_id]
        manager.clear_buffers()
        del _audio_buffer_managers[device_id]
