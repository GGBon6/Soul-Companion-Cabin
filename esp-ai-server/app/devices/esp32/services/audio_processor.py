"""
ESP32 音频处理服务
直接处理ESP32音频数据
"""

import time
import logging
import asyncio
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

# Opus解码支持
try:
    import opuslib
    OPUS_AVAILABLE = True
except ImportError:
    OPUS_AVAILABLE = False


@dataclass
class ESP32AudioEvent:
    """ESP32 音频事件"""
    event_type: str  # voice_end
    session_id: str
    device_id: str
    timestamp: float
    audio_data: Optional[bytes] = None
    metadata: Optional[Dict[str, Any]] = None


class ESP32AudioProcessor:
    """ESP32 音频处理服务"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.logger = logging.getLogger(f"{__name__}[{device_id}]")
        
        # 简单的音频处理服务 - 只做Opus到PCM转换和累积
        self.logger.info("ESP32 音频处理服务：直接处理音频数据")
        
        # 会话管理
        self.session_id: Optional[str] = None
        
        # 事件回调（只保留语音结束事件）
        self.event_callbacks: Dict[str, list[Callable]] = {
            "voice_end": []
        }
        
        # 统计信息
        self.stats = {
            "total_audio_processed": 0,
            "avg_processing_time_ms": 0.0,
            "voice_segments": 0,
            "total_voice_duration": 0.0
        }
        
        # 音频累积缓冲区
        self.accumulated_audio = bytearray()
        
        self.logger.info(f"ESP32 音频处理服务初始化完成 - 设备: {device_id}")
    
    def start_session(self, session_id: str):
        """开始音频会话"""
        if self.session_id:
            self.logger.warning(f"会话已存在，将重置: {self.session_id}")
            self.end_session()
        
        self.session_id = session_id
        self.accumulated_audio.clear()
        
        self.logger.info(f"开始音频会话: {session_id}")
    
    def end_session(self):
        """结束音频会话"""
        if self.session_id:
            # 如果有累积音频，触发语音结束事件
            if self.accumulated_audio:
                audio_event = ESP32AudioEvent(
                    event_type="voice_end",
                    session_id=self.session_id,
                    device_id=self.device_id,
                    timestamp=time.time(),
                    audio_data=bytes(self.accumulated_audio)
                )
                self._trigger_event("voice_end", audio_event)
            
            self.logger.info(f"结束音频会话: {self.session_id}")
        
        self.session_id = None
        self.accumulated_audio.clear()
    
    def process_audio(self, audio_data: bytes) -> bool:
        """处理音频数据"""
        if not self.session_id:
            raise ValueError("音频会话未初始化")
        
        start_time = time.time()
        
        try:
            # 直接处理ESP32音频数据
            self.logger.debug(f"接收ESP32音频数据: {len(audio_data)}字节")
            
            # 转换Opus为PCM格式用于ASR
            pcm_data = self._opus_to_pcm(audio_data)
            if pcm_data:
                self.accumulated_audio.extend(pcm_data)
                self.logger.debug(f"累积PCM音频: Opus {len(audio_data)}字节 -> PCM {len(pcm_data)}字节")
                result = True
            else:
                self.logger.warning(f"Opus解码失败: {len(audio_data)}字节")
                result = False
            
            # 更新统计信息
            self.stats["total_audio_processed"] += len(audio_data)
            processing_time = (time.time() - start_time) * 1000
            self.stats["avg_processing_time_ms"] = processing_time
            
            return result
            
        except Exception as e:
            self.logger.error(f"音频处理失败: {e}")
            return False
    
    def _opus_to_pcm(self, opus_data: bytes) -> Optional[bytes]:
        """将Opus音频数据转换为PCM格式"""
        if not OPUS_AVAILABLE:
            self.logger.warning("Opus库不可用，无法转换音频格式")
            return None
        
        try:
            # 创建Opus解码器 (16kHz, 单声道)
            decoder = opuslib.Decoder(fs=16000, channels=1)
            
            # 尝试不同的frame_size来解码Opus数据
            # ESP32可能发送20ms、40ms或60ms的帧
            possible_frame_sizes = [320, 640, 960, 480]  # 20ms, 40ms, 60ms, 30ms @ 16kHz
            
            for frame_size in possible_frame_sizes:
                try:
                    pcm_data = decoder.decode(opus_data, frame_size=frame_size)
                    self.logger.debug(f"Opus解码成功: {len(opus_data)}字节 -> {len(pcm_data)}字节 (frame_size={frame_size})")
                    return pcm_data
                except Exception:
                    continue
            
            # 如果所有frame_size都失败，记录错误
            self.logger.error(f"Opus解码失败: 尝试了所有frame_size都无法解码 {len(opus_data)}字节")
            return None
            
        except Exception as e:
            self.logger.error(f"Opus解码失败: {e}")
            self.logger.error(f"Opus解码失败: {len(opus_data)}字节")
            return None
    
    def _trigger_event(self, event_type: str, event: ESP32AudioEvent):
        """触发事件回调"""
        callbacks = self.event_callbacks.get(event_type, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(event))
                else:
                    callback(event)
            except Exception as e:
                self.logger.error(f"音频事件回调失败 [{event_type}]: {e}")
    
    def add_event_callback(self, event_type: str, callback: Callable):
        """添加事件回调"""
        if event_type in self.event_callbacks:
            self.event_callbacks[event_type].append(callback)
            self.logger.debug(f"添加音频事件回调: {event_type}")
        else:
            self.logger.warning(f"未知的音频事件类型: {event_type}")
    
    def remove_event_callback(self, event_type: str, callback: Callable):
        """移除事件回调"""
        if event_type in self.event_callbacks and callback in self.event_callbacks[event_type]:
            self.event_callbacks[event_type].remove(callback)
            self.logger.debug(f"移除音频事件回调: {event_type}")
    
    def get_current_audio(self) -> bytes:
        """获取当前累积的音频数据"""
        return bytes(self.accumulated_audio)
    
    def is_voice_complete(self) -> bool:
        """判断语音是否完整结束（简化版）"""
        if not self.session_id:
            return False
        # 简单判断：有累积音频就认为语音完整
        return len(self.accumulated_audio) > 0
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        return {
            **self.stats,
            "accumulated_audio_size": len(self.accumulated_audio),
            "session_id": self.session_id,
            "device_id": self.device_id
        }
    
    def _update_avg_processing_time(self, processing_time: float):
        """更新平均处理时间"""
        if self.stats["avg_processing_time_ms"] == 0:
            self.stats["avg_processing_time_ms"] = processing_time
        else:
            # 指数移动平均
            alpha = 0.1
            self.stats["avg_processing_time"] = (
                alpha * processing_time + 
                (1 - alpha) * self.stats["avg_processing_time"]
            )


# 全局ESP32 音频处理实例管理
_esp32_audio_processors: Dict[str, ESP32AudioProcessor] = {}


def get_esp32_audio_processor(device_id: str) -> ESP32AudioProcessor:
    """获取ESP32 音频处理实例"""
    if device_id not in _esp32_audio_processors:
        _esp32_audio_processors[device_id] = ESP32AudioProcessor(device_id)
    return _esp32_audio_processors[device_id]


def remove_esp32_audio_processor(device_id: str):
    """移除ESP32 音频处理实例"""
    if device_id in _esp32_audio_processors:
        processor = _esp32_audio_processors[device_id]
        processor.end_session()
        del _esp32_audio_processors[device_id]


def cleanup_esp32_audio_processors():
    """清理所有ESP32 音频处理实例"""
    for device_id in list(_esp32_audio_processors.keys()):
        remove_esp32_audio_processor(device_id)
