"""
ESP32 ASR服务集成器
ESP32 ASR Service Integration
集成现有ASR服务到ESP32新架构中，解决连接管理和性能问题
参考开源项目的ASR处理模式，优化连接复用和错误处理
"""

import asyncio
import time
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
import logging

from app.shared.services.asr_service import ASRService, acquire_asr_service
from ..audio import AudioFrame

# 导入Opus解码器
try:
    import opuslib
    OPUS_AVAILABLE = True
except ImportError:
    OPUS_AVAILABLE = False
    logging.warning("opuslib not available, Opus decoding will fail")


class ASRQuality(Enum):
    """ASR识别质量等级"""
    EXCELLENT = "excellent"     # 优秀 (>95%置信度)
    GOOD = "good"              # 良好 (80-95%置信度)
    FAIR = "fair"              # 一般 (60-80%置信度)
    POOR = "poor"              # 较差 (<60%置信度)
    INVALID = "invalid"        # 无效 (空结果或错误)


@dataclass
class ASRResult:
    """ASR识别结果"""
    text: str                           # 识别文本
    confidence: float                   # 置信度 (0.0-1.0)
    quality: ASRQuality                 # 质量等级
    processing_time: float              # 处理时间（秒）
    audio_duration: float               # 音频时长（秒）
    frame_count: int                    # 音频帧数
    total_bytes: int                    # 音频总字节数
    is_valid: bool                      # 是否有效
    error_message: Optional[str] = None # 错误信息
    metadata: Dict[str, Any] = None     # 元数据


@dataclass
class ASRStatistics:
    """ASR统计信息"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    empty_results: int = 0
    filtered_requests: int = 0          # 被过滤的请求（空音频等）
    
    total_processing_time: float = 0.0
    total_audio_duration: float = 0.0
    total_bytes_processed: int = 0
    
    # 质量统计
    excellent_count: int = 0
    good_count: int = 0
    fair_count: int = 0
    poor_count: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def avg_processing_time(self) -> float:
        """平均处理时间"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_processing_time / self.successful_requests
    
    @property
    def avg_audio_duration(self) -> float:
        """平均音频时长"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_audio_duration / self.successful_requests


class ESP32ASRServiceIntegration:
    """ESP32 ASR服务集成器"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.tag = f"ESP32ASR[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # ASR配置
        self.min_audio_duration = 0.04     # 最小音频时长（秒）- 降低以支持流式识别
        self.max_audio_duration = 60.0     # 最大音频时长（秒）
        self.min_audio_bytes = 200         # 最小音频字节数 (降低以支持流式识别)
        self.max_retries = 2               # 最大重试次数
        self.timeout = 10.0                # 超时时间（秒）
        
        # 质量控制
        self.min_confidence = 0.6          # 最小置信度阈值
        self.min_text_length = 1           # 最小文本长度
        self.max_text_length = 1000        # 最大文本长度
        
        # 过滤配置
        self.enable_silence_filter = True  # 启用静音过滤
        self.enable_quality_filter = True  # 启用质量过滤
        self.enable_duplicate_filter = True # 启用重复过滤
        
        # 统计信息
        self.statistics = ASRStatistics()
        
        # 结果缓存（用于重复检测）
        self._result_cache: List[str] = []
        self._cache_size = 10
        
        # 回调函数
        self._result_callbacks: List[Callable[[ASRResult], None]] = []
        
        self.logger.info(f"[{self.tag}] ASR服务集成器初始化完成")
    
    def add_result_callback(self, callback: Callable[[ASRResult], None]) -> None:
        """添加结果回调"""
        self._result_callbacks.append(callback)
    
    async def process_audio_frames(self, frames: List[AudioFrame]) -> Optional[ASRResult]:
        """
        处理音频帧进行ASR识别
        
        Args:
            frames: 音频帧列表
            
        Returns:
            Optional[ASRResult]: 识别结果或None
        """
        # 添加明显的调试日志
        self.logger.debug(f"[{self.tag}] ASR处理开始: {len(frames) if frames else 0}帧")
        
        # 添加更详细的帧信息
        if frames:
            total_bytes = sum(len(frame.data) for frame in frames)
            self.logger.debug(f"[{self.tag}] 音频帧详情: 总字节={total_bytes}, 第一帧大小={len(frames[0].data)}")
        
        if not frames:
            self.logger.debug(f"[{self.tag}] 音频帧列表为空")
            return None
        
        try:
            # 合并音频数据（返回数据和帧边界信息）
            audio_data, frame_sizes = self._merge_audio_frames(frames)
            
            # 保存帧边界信息到frames的metadata中，供后续解码使用
            if frames:
                if not hasattr(frames[0], 'metadata') or frames[0].metadata is None:
                    frames[0].metadata = {}
                frames[0].metadata['frame_sizes'] = frame_sizes
            
            # 验证音频数据
            self.logger.debug(f"[{self.tag}] 开始音频验证: {len(audio_data)}字节")
            validation_result = self._validate_audio_data(audio_data, frames)
            self.logger.debug(f"[{self.tag}] 音频验证结果: {validation_result}")
            
            if not validation_result:
                self.statistics.filtered_requests += 1
                self.logger.info(f"[{self.tag}] 🚫 音频数据验证失败，跳过ASR处理")
                return None
            
            # 计算音频时长
            audio_duration = self._calculate_audio_duration(frames)
            
            self.logger.info(f"[{self.tag}] 开始ASR处理: {len(frames)}帧, "
                           f"{len(audio_data)}字节, {audio_duration:.2f}秒")
            
            # 进行ASR识别
            result = await self._perform_asr_recognition(audio_data, audio_duration, len(frames), frames)
            
            # 触发回调
            if result:
                for callback in self._result_callbacks:
                    try:
                        callback(result)
                    except Exception as e:
                        self.logger.error(f"[{self.tag}] ASR结果回调执行失败: {e}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 处理音频帧失败: {e}", exc_info=True)
            self.statistics.failed_requests += 1
            return ASRResult(
                text="",
                confidence=0.0,
                quality=ASRQuality.INVALID,
                processing_time=0.0,
                audio_duration=0.0,
                frame_count=len(frames),
                total_bytes=sum(len(frame.data) for frame in frames),
                is_valid=False,
                error_message=str(e)
            )
    
    def _merge_audio_frames(self, frames: List[AudioFrame]) -> tuple[bytes, List[int]]:
        """
        合并音频帧数据，并返回帧边界信息
        
        注意：对于ESP32发送的Opus数据，每个frame.data都是一个完整的40ms Opus帧
        我们需要保持这些帧的独立性，而不是简单拼接
        
        Args:
            frames: 音频帧列表
            
        Returns:
            tuple: (合并后的音频数据, 帧边界列表)
        """
        # 按序列号排序
        sorted_frames = sorted(frames, key=lambda f: f.sequence_number)
        
        # 检查是否是合并的Opus数据（来自流式缓冲区）
        if len(frames) == 1 and frames[0].metadata and frames[0].metadata.get('opus_frames_merged'):
            # 这是已经合并的Opus数据，直接返回
            audio_data = frames[0].data
            # 尝试从metadata获取帧边界信息
            frame_sizes = frames[0].metadata.get('frame_sizes', [])
            total_frames = frames[0].metadata.get('total_frames', 1)
            
            # 调试日志
            self.logger.debug(f"[{self.tag}] 🔍 合并Opus数据检查: frame_sizes长度={len(frame_sizes) if frame_sizes else 0}, "
                            f"total_frames={total_frames}, opus_data={len(audio_data)}字节")
            
            if not frame_sizes or len(frame_sizes) == 0:
                # 如果没有帧边界信息，尝试估算（每个帧约40-80字节）
                # 这是一个粗略估算，可能不准确
                if total_frames > 0:
                    estimated_frame_size = len(audio_data) // total_frames
                    frame_sizes = [estimated_frame_size] * total_frames
                    self.logger.warning(f"[{self.tag}] ⚠️ 没有帧大小信息，使用估算: {estimated_frame_size}字节/帧 × {total_frames}帧")
                else:
                    # 如果连total_frames都没有，使用默认估算
                    estimated_frame_size = 60  # 默认40-80字节之间
                    estimated_frame_count = len(audio_data) // estimated_frame_size
                    frame_sizes = [estimated_frame_size] * estimated_frame_count
                    self.logger.warning(f"[{self.tag}] ⚠️ 没有帧信息，使用默认估算: {estimated_frame_size}字节/帧 × {estimated_frame_count}帧")
            else:
                # 验证frame_sizes长度是否匹配total_frames
                if len(frame_sizes) != total_frames:
                    self.logger.warning(f"[{self.tag}] ⚠️ frame_sizes长度({len(frame_sizes)})与total_frames({total_frames})不匹配，使用实际长度")
                    # 如果frame_sizes更多，截断；如果更少，用平均值填充
                    if len(frame_sizes) > total_frames:
                        frame_sizes = frame_sizes[:total_frames]
                    elif len(frame_sizes) < total_frames:
                        avg_size = sum(frame_sizes) // len(frame_sizes) if frame_sizes else 60
                        frame_sizes.extend([avg_size] * (total_frames - len(frame_sizes)))
            
            self.logger.debug(f"[{self.tag}] ✅ 使用已合并的Opus数据: {len(audio_data)}字节, {len(frame_sizes)}帧, "
                            f"帧大小总和={sum(frame_sizes)}字节")
        else:
            # 这是独立的Opus帧，需要拼接
            # 记录每个帧的大小，用于后续解码
            frame_sizes = [len(frame.data) for frame in sorted_frames]
            audio_data = b''.join(frame.data for frame in sorted_frames)
            self.logger.debug(f"[{self.tag}] 拼接独立Opus帧: {len(frames)}帧 -> {len(audio_data)}字节")
        
        self.logger.debug(f"[{self.tag}] 合并音频帧: {len(frames)}帧 -> {len(audio_data)}字节")
        
        return audio_data, frame_sizes
    
    def _validate_audio_data(self, audio_data: bytes, frames: List[AudioFrame]) -> bool:
        """
        验证音频数据有效性
        
        Args:
            audio_data: 音频数据
            frames: 音频帧列表
            
        Returns:
            bool: 是否有效
        """
        # 检查数据长度
        self.logger.debug(f"[{self.tag}] 检查数据长度: {len(audio_data)} >= {self.min_audio_bytes}")
        if len(audio_data) < self.min_audio_bytes:
            self.logger.info(f"[{self.tag}] 🚫 音频数据太小: {len(audio_data)} < {self.min_audio_bytes}")
            return False
        
        # 检查音频时长
        audio_duration = self._calculate_audio_duration(frames)
        self.logger.debug(f"[{self.tag}] 检查音频时长: {audio_duration:.2f}s (范围: {self.min_audio_duration}s - {self.max_audio_duration}s)")
        if audio_duration < self.min_audio_duration:
            self.logger.info(f"[{self.tag}] 🚫 音频时长太短: {audio_duration:.2f}s < {self.min_audio_duration}s")
            return False
        
        if audio_duration > self.max_audio_duration:
            self.logger.info(f"[{self.tag}] 🚫 音频时长太长: {audio_duration:.2f}s > {self.max_audio_duration}s")
            return False
        
        # 静音检测（如果启用）
        self.logger.debug(f"[{self.tag}] 静音检测启用: {self.enable_silence_filter}")
        if self.enable_silence_filter and self._is_silence_audio(audio_data, frames):
            avg_frame_size = len(audio_data) / len(frames) if frames else 0
            self.logger.info(f"[{self.tag}] 🚫 检测到静音音频: 平均帧大小={avg_frame_size:.1f}字节")
            return False
        
        # 验证通过，记录详细信息
        self.logger.debug(f"[{self.tag}] 音频验证通过")
        self.logger.info(f"[{self.tag}] ✅ 音频验证通过: {len(audio_data)}字节, {audio_duration:.2f}秒, {len(frames)}帧")
        
        return True
    
    def _calculate_audio_duration(self, frames: List[AudioFrame]) -> float:
        """
        计算音频时长
        
        Args:
            frames: 音频帧列表
            
        Returns:
            float: 音频时长（秒）
        """
        if not frames:
            return 0.0
        
        # 使用第一帧的采样率和格式信息
        first_frame = frames[0]
        sample_rate = getattr(first_frame, 'sample_rate', 16000)
        audio_format = getattr(first_frame, 'format', 'opus').lower()
        
        if audio_format == "opus":
            # 对于Opus格式，使用帧数和帧时长计算
            # ESP32使用40ms帧时长
            frame_duration_ms = 40  # ESP32固定使用40ms帧
            
            # 检查是否有合并的Opus数据
            total_frames = 0
            for frame in frames:
                if hasattr(frame, 'metadata') and frame.metadata:
                    # 如果有total_frames信息，使用它
                    frame_total = frame.metadata.get('total_frames', 1)
                    total_frames += frame_total
                else:
                    # 否则按单帧计算
                    total_frames += 1
            
            total_duration = total_frames * frame_duration_ms / 1000.0
            self.logger.debug(f"[{self.tag}] Opus时长计算: {total_frames}帧 × {frame_duration_ms}ms = {total_duration:.3f}s")
            return total_duration
        else:
            # 对于PCM格式，使用字节数计算
            total_bytes = sum(len(frame.data) for frame in frames)
            total_samples = total_bytes // 2  # 16位 = 2字节
            duration = total_samples / sample_rate
            return duration
    
    def _decode_opus_to_pcm(self, opus_data: bytes, frame_count: int, frame_sizes: Optional[List[int]] = None) -> Optional[bytes]:
        """
        将Opus数据解码为PCM数据
        
        注意：设备端现在输出固定大小的完整帧（40ms @ 16kHz = 640 samples），
        不再有小包问题。Opus编码后的帧大小可能因内容而异（变长编码）。
        
        Args:
            opus_data: 合并的Opus数据
            frame_count: Opus帧数量
            frame_sizes: 每个Opus帧的大小列表（可选）
            
        Returns:
            Optional[bytes]: 解码后的PCM数据，失败返回None
        """
        if not OPUS_AVAILABLE:
            self.logger.error(f"[{self.tag}] opuslib不可用，无法解码Opus数据")
            return None
        
        try:
            # 创建Opus解码器（16kHz, 单声道）
            # opuslib的API: Decoder(fs=采样率, channels=声道数)
            decoder = opuslib.Decoder(fs=16000, channels=1)
            
            # 计算每帧的PCM样本数（40ms @ 16kHz = 640 samples）
            # 设备端现在确保输出完整的40ms帧
            frame_size_samples = 640  # ESP32使用40ms帧
            
            pcm_frames = []
            
            # 如果有帧大小信息，尽量使用它（即使长度不完全匹配）
            if frame_sizes and len(frame_sizes) > 0:
                # 如果长度不匹配，调整frame_sizes或frame_count
                if len(frame_sizes) != frame_count:
                    self.logger.warning(f"[{self.tag}] ⚠️ frame_sizes长度({len(frame_sizes)})与frame_count({frame_count})不匹配")
                    if len(frame_sizes) > frame_count:
                        # frame_sizes更多，只使用前frame_count个
                        frame_sizes = frame_sizes[:frame_count]
                        self.logger.debug(f"[{self.tag}] 截断frame_sizes到{frame_count}个")
                    else:
                        # frame_sizes更少，用平均值填充或调整frame_count
                        avg_size = sum(frame_sizes) // len(frame_sizes) if frame_sizes else 60
                        frame_sizes.extend([avg_size] * (frame_count - len(frame_sizes)))
                        self.logger.debug(f"[{self.tag}] 扩展frame_sizes到{frame_count}个，使用平均值{avg_size}字节")
                
                # 现在frame_sizes长度应该匹配frame_count了
                if len(frame_sizes) == frame_count:
                    # 如果有帧大小信息，按帧解码
                    offset = 0
                    success_count = 0
                    skip_count = 0
                    error_count = 0
                    
                    # 统计帧大小分布（用于调试）
                    if frame_count > 0:
                        min_frame_size = min(frame_sizes)
                        max_frame_size = max(frame_sizes)
                        avg_frame_size = sum(frame_sizes) // len(frame_sizes)
                        self.logger.debug(f"[{self.tag}] 帧大小统计: 最小={min_frame_size}, 最大={max_frame_size}, 平均={avg_frame_size}, 总计={frame_count}帧")
                    
                    for i, frame_size in enumerate(frame_sizes):
                        if offset + frame_size > len(opus_data):
                            self.logger.warning(f"[{self.tag}] 帧#{i}: 超出数据范围 (offset={offset}, frame_size={frame_size}, total={len(opus_data)})")
                            break
                        
                        opus_frame = opus_data[offset:offset + frame_size]
                        offset += frame_size
                        
                        # 设备端现在输出完整帧，所有帧都应该可以解码
                        # 但Opus是变长编码，帧大小可能因内容而异
                        try:
                            # opuslib的API: decode(data, frame_size=样本数)
                            pcm_frame = decoder.decode(opus_frame, frame_size=frame_size_samples)
                            if pcm_frame and len(pcm_frame) > 0:
                                pcm_frames.append(pcm_frame)
                                success_count += 1
                                # 只记录前3帧和后3帧的详细信息，避免日志过多
                                if i < 3 or i >= len(frame_sizes) - 3:
                                    self.logger.debug(f"[{self.tag}] 帧#{i}: 解码成功 ({frame_size}字节 -> {len(pcm_frame)}字节PCM)")
                            else:
                                error_count += 1
                                if i < 3 or i >= len(frame_sizes) - 3:
                                    self.logger.warning(f"[{self.tag}] 帧#{i}: 解码返回空数据 ({frame_size}字节)")
                        except Exception as e:
                            error_count += 1
                            # 对于非常小的帧（<10字节），可能是无效帧或静音帧
                            if frame_size < 10:
                                skip_count += 1
                                if i < 3 or i >= len(frame_sizes) - 3:
                                    self.logger.debug(f"[{self.tag}] 帧#{i}: 小帧跳过 ({frame_size}字节): {e}")
                            else:
                                # 正常大小的帧解码失败，需要记录警告
                                if i < 3 or i >= len(frame_sizes) - 3:
                                    self.logger.warning(f"[{self.tag}] 帧#{i}: 解码失败 ({frame_size}字节): {e}")
                    
                    # 记录解码统计信息
                    success_rate = (success_count / frame_count * 100) if frame_count > 0 else 0
                    self.logger.warning(f"[{self.tag}] 🔍 Opus解码统计: 成功={success_count}/{frame_count} ({success_rate:.1f}%), 跳过={skip_count}, 失败={error_count}")
                    if success_count == 0:
                        self.logger.error(f"[{self.tag}] ❌ 所有帧解码失败！Opus数据可能无效")
                        # 显示Opus数据的前64字节用于调试
                        hex_preview = opus_data[:64].hex() if len(opus_data) >= 64 else opus_data.hex()
                        self.logger.error(f"[{self.tag}]   Opus数据预览(前64字节): {hex_preview}")
            else:
                # 如果没有帧大小信息，尝试估算
                # 设备端现在输出固定大小的完整帧（40ms），Opus编码后通常在40-100字节之间
                estimated_frame_size = len(opus_data) // frame_count if frame_count > 0 else 60
                self.logger.debug(f"[{self.tag}] 无帧大小信息，使用估算: {estimated_frame_size}字节/帧")
                
                offset = 0
                success_count = 0
                for i in range(frame_count):
                    remaining = len(opus_data) - offset
                    if remaining < 10:  # 最小Opus帧大小
                        self.logger.warning(f"[{self.tag}] 帧#{i}: 剩余数据不足 ({remaining}字节)")
                        break
                    
                    # 尝试不同的帧大小（40-120字节，覆盖正常Opus帧范围）
                    decoded = False
                    for try_size in range(40, min(120, remaining + 1)):
                        try:
                            opus_frame = opus_data[offset:offset + try_size]
                            pcm_frame = decoder.decode(opus_frame, frame_size=frame_size_samples)
                            if pcm_frame and len(pcm_frame) > 0:
                                pcm_frames.append(pcm_frame)
                                offset += try_size
                                success_count += 1
                                decoded = True
                                if i < 3:
                                    self.logger.debug(f"[{self.tag}] 帧#{i}: 估算解码成功 (尝试大小={try_size}字节 -> {len(pcm_frame)}字节PCM)")
                                break
                        except:
                            continue
                    
                    if not decoded:
                        # 如果所有尝试都失败，跳过1字节继续
                        offset += 1
                        if offset >= len(opus_data):
                            break
                
                self.logger.warning(f"[{self.tag}] 🔍 Opus解码统计（估算模式）: 成功={success_count}/{frame_count}")
                if success_count == 0:
                    self.logger.error(f"[{self.tag}] ❌ 估算模式下所有帧解码失败！")
                    hex_preview = opus_data[:64].hex() if len(opus_data) >= 64 else opus_data.hex()
                    self.logger.error(f"[{self.tag}]   Opus数据预览(前64字节): {hex_preview}")
            
            if not pcm_frames:
                self.logger.warning(f"[{self.tag}] ⚠️ Opus解码失败: 没有成功解码任何帧")
                self.logger.warning(f"   Opus数据: {len(opus_data)}字节, 期望帧数: {frame_count}")
                if frame_sizes:
                    # 显示帧大小统计信息
                    unique_sizes = set(frame_sizes)
                    self.logger.warning(f"   帧大小分布: {len(unique_sizes)}种不同大小, 范围={min(frame_sizes)}-{max(frame_sizes)}字节")
                    if len(frame_sizes) <= 20:
                        self.logger.warning(f"   帧大小列表: {frame_sizes}")
                    else:
                        self.logger.warning(f"   前10个帧大小: {frame_sizes[:10]}, 后10个: {frame_sizes[-10:]}")
                return None
            
            # 合并所有PCM帧
            pcm_data = b''.join(pcm_frames)
            
            # 验证PCM数据质量
            expected_pcm_size = len(pcm_frames) * frame_size_samples * 2  # 每帧640样本 * 2字节/样本
            if len(pcm_data) < 100:
                self.logger.warning(f"[{self.tag}] ⚠️ PCM数据太小: {len(pcm_data)}字节 < 100字节")
                return None
            
            # 检查PCM数据是否包含有效音频（非全0）
            import numpy as np
            try:
                # 检查前1000字节和随机采样点
                check_samples = min(1000, len(pcm_data))
                pcm_array = np.frombuffer(pcm_data[:check_samples], dtype=np.int16)
                max_amplitude = np.max(np.abs(pcm_array))
                mean_amplitude = np.mean(np.abs(pcm_array))
                
                # 如果前1000字节都是0，检查中间部分
                if max_amplitude < 10 and len(pcm_data) > 2000:
                    mid_start = len(pcm_data) // 2
                    mid_array = np.frombuffer(pcm_data[mid_start:mid_start+1000], dtype=np.int16)
                    max_amplitude = max(max_amplitude, np.max(np.abs(mid_array)))
                    mean_amplitude = (mean_amplitude + np.mean(np.abs(mid_array))) / 2
                
                if max_amplitude < 10:  # 可能是静音
                    self.logger.error(f"[{self.tag}] ❌ PCM数据可能是静音: max_amplitude={max_amplitude}, mean_amplitude={mean_amplitude:.2f}")
                    self.logger.error(f"   Opus数据: {len(opus_data)}字节, 解码后PCM: {len(pcm_data)}字节 (期望≈{expected_pcm_size}字节)")
                    self.logger.error(f"   成功解码: {len(pcm_frames)}/{frame_count}帧")
                    # 显示PCM数据的前64字节用于调试
                    pcm_hex_preview = pcm_data[:64].hex() if len(pcm_data) >= 64 else pcm_data.hex()
                    self.logger.error(f"   PCM数据预览(前64字节): {pcm_hex_preview}")
                    # 显示前20个样本值
                    sample_values = pcm_array[:20].tolist()
                    self.logger.error(f"   前20个样本值: {sample_values}")
                else:
                    self.logger.warning(f"[{self.tag}] ✅ Opus解码成功: {len(opus_data)}字节 -> {len(pcm_data)}字节PCM")
                    self.logger.warning(f"   成功解码: {len(pcm_frames)}/{frame_count}帧, PCM大小: {len(pcm_data)}字节 (期望≈{expected_pcm_size}字节)")
                    self.logger.warning(f"   音频质量: max_amplitude={max_amplitude}, mean_amplitude={mean_amplitude:.2f}")
            except Exception as e:
                self.logger.warning(f"[{self.tag}] PCM数据验证失败: {e}")
            
            return pcm_data
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] Opus解码失败: {e}", exc_info=True)
            return None
    
    def _is_silence_audio(self, audio_data: bytes, frames: List[AudioFrame]) -> bool:
        """
        检测是否为静音音频
        
        Args:
            audio_data: 音频数据
            frames: 音频帧列表
            
        Returns:
            bool: 是否为静音
        """
        try:
            # 检查帧格式
            if frames and frames[0].format.lower() == "opus":
                # 对于Opus格式，检查平均帧大小
                avg_frame_size = len(audio_data) / len(frames)
                # ESP32使用复杂度0，静音帧会更小，调整阈值
                return avg_frame_size < 15  # 降低阈值，ESP32低复杂度编码的静音帧更小
            
            # 对于PCM格式，检查音频能量
            if len(audio_data) >= 100:
                import numpy as np
                audio_array = np.frombuffer(audio_data[:1000], dtype=np.int16)  # 只检查前1000字节
                max_amplitude = np.max(np.abs(audio_array))
                return max_amplitude < 200  # 静音阈值
            
            return False
            
        except Exception as e:
            self.logger.debug(f"[{self.tag}] 静音检测失败: {e}")
            return False
    
    async def _perform_asr_recognition(self, audio_data: bytes, audio_duration: float, frame_count: int, frames: Optional[List[AudioFrame]] = None) -> Optional[ASRResult]:
        """
        执行ASR识别
        
        Args:
            audio_data: 音频数据（Opus格式）
            audio_duration: 音频时长
            frame_count: 帧数
            
        Returns:
            Optional[ASRResult]: 识别结果
        """
        start_time = time.time()
        self.statistics.total_requests += 1
        
        for attempt in range(self.max_retries + 1):
            try:
                self.logger.debug(f"[{self.tag}] ASR识别尝试 {attempt + 1}/{self.max_retries + 1}")
                
                # 使用ASR服务进行识别
                async with acquire_asr_service("esp32", self.device_id, self.timeout) as asr_service:
                    # ESP32发送的是Opus编码的音频数据
                    # FUN-ASR实时识别API需要PCM格式，需要先解码Opus
                    if attempt == 0:  # 只在第一次尝试时记录日志
                        self.logger.debug(f"[{self.tag}] 🎤 ASR识别: {len(audio_data)}字节Opus, {frame_count}帧")
                    
                    # 将Opus数据解码为PCM
                    # 注意：合并的Opus数据需要按帧解码
                    # 从frames的metadata中获取帧大小信息和实际帧数
                    frame_sizes = None
                    actual_frame_count = frame_count  # 默认使用传入的frame_count
                    if frames and frames[0].metadata:
                        frame_sizes = frames[0].metadata.get('frame_sizes')
                        # 如果metadata中有total_frames，使用它作为实际帧数（合并的Opus数据）
                        total_frames = frames[0].metadata.get('total_frames')
                        if total_frames and total_frames > 0:
                            actual_frame_count = total_frames
                            if attempt == 0:
                                self.logger.debug(f"[{self.tag}] 🔍 使用metadata中的total_frames: {total_frames} (而不是frame_count={frame_count})")
                        # 调试：检查metadata内容
                        if attempt == 0:
                            self.logger.debug(f"[{self.tag}] 🔍 Metadata检查: frame_sizes={frame_sizes is not None}, "
                                            f"len={len(frame_sizes) if frame_sizes else 0}, "
                                            f"total_frames={frames[0].metadata.get('total_frames')}, "
                                            f"opus_frames_merged={frames[0].metadata.get('opus_frames_merged')}, "
                                            f"actual_frame_count={actual_frame_count}")
                    
                    # 添加详细日志
                    if attempt == 0:  # 只在第一次尝试时记录详细日志
                        self.logger.info(f"[{self.tag}] 🔍 Opus解码准备: {len(audio_data)}字节, {actual_frame_count}帧 (AudioFrame数={frame_count})")
                        if frame_sizes and len(frame_sizes) > 0:
                            # 设备端现在输出固定大小的完整帧（40ms），但Opus编码后大小可能因内容而异
                            unique_sizes = set(frame_sizes)
                            min_size, max_size = min(frame_sizes), max(frame_sizes)
                            avg_size = sum(frame_sizes) // len(frame_sizes)
                            self.logger.info(f"[{self.tag}]   帧大小信息: {len(frame_sizes)}个帧, 总和={sum(frame_sizes)}字节")
                            self.logger.info(f"[{self.tag}]   帧大小统计: 最小={min_size}, 最大={max_size}, 平均={avg_size}, 种类={len(unique_sizes)}")
                            if len(frame_sizes) <= 20:
                                self.logger.debug(f"[{self.tag}]   所有帧大小: {frame_sizes}")
                            else:
                                self.logger.debug(f"[{self.tag}]   前5个帧大小: {frame_sizes[:5]}, 后5个: {frame_sizes[-5:]}")
                        else:
                            self.logger.warning(f"[{self.tag}]   ⚠️ 没有帧大小信息（frame_sizes={frame_sizes}），将使用估算方法（设备端应输出固定大小完整帧）")
                            self.logger.warning(f"[{self.tag}]   估算: {len(audio_data)}字节 / {actual_frame_count}帧 ≈ {len(audio_data) // actual_frame_count if actual_frame_count > 0 else 0}字节/帧")
                    
                    pcm_data = self._decode_opus_to_pcm(audio_data, actual_frame_count, frame_sizes)
                    
                    if not pcm_data or len(pcm_data) < 100:
                        if attempt == self.max_retries:
                            self.logger.warning(f"[{self.tag}] ❌ Opus解码失败: {len(pcm_data) if pcm_data else 0}字节PCM")
                            self.logger.warning(f"   原始Opus数据: {len(audio_data)}字节, {frame_count}帧")
                            if audio_data:
                                # 显示Opus数据的前32字节（十六进制）
                                hex_preview = audio_data[:32].hex()
                                self.logger.warning(f"   Opus数据预览(前32字节): {hex_preview}")
                            self.statistics.failed_requests += 1
                            return ASRResult(
                                text="",
                                confidence=0.0,
                                quality=ASRQuality.INVALID,
                                processing_time=time.time() - start_time,
                                audio_duration=audio_duration,
                                frame_count=frame_count,
                                total_bytes=len(audio_data),
                                is_valid=False,
                                error_message="Opus解码失败"
                            )
                        continue
                    
                    # 验证PCM数据格式（16位小端序，16kHz，单声道）
                    if attempt == 0:  # 只在第一次尝试时记录详细日志
                        import numpy as np
                        try:
                            pcm_array = np.frombuffer(pcm_data[:1000], dtype=np.int16)
                            expected_samples = len(pcm_data) // 2
                            actual_samples = len(pcm_array)
                            self.logger.info(f"[{self.tag}] 🔍 PCM数据验证:")
                            self.logger.info(f"   PCM大小: {len(pcm_data)}字节 ({expected_samples}个16位样本)")
                            self.logger.info(f"   前10个样本值: {pcm_array[:10].tolist()}")
                            self.logger.info(f"   最大振幅: {np.max(np.abs(pcm_array))}")
                            self.logger.info(f"   平均振幅: {np.mean(np.abs(pcm_array)):.2f}")
                            
                            # 检查是否全为0或接近0（静音）
                            if np.max(np.abs(pcm_array)) < 10:
                                self.logger.warning(f"[{self.tag}] ⚠️ 警告: PCM数据可能是静音（最大振幅 < 10）")
                        except Exception as e:
                            self.logger.warning(f"[{self.tag}] PCM数据验证失败: {e}")
                    
                    # 使用PCM格式进行ASR识别（启用详细日志以便诊断）
                    text = asr_service.transcribe(pcm_data, "pcm", enable_detailed_logs=(attempt == 0))
                    
                    if attempt == 0:  # 只在第一次尝试时记录结果
                        if text:
                            self.logger.info(f"[{self.tag}] ✅ ASR识别成功: '{text}'")
                        else:
                            self.logger.warning(f"[{self.tag}] ⚠️ ASR识别返回空结果")
                            self.logger.warning(f"   PCM数据: {len(pcm_data)}字节, 音频时长: {audio_duration:.2f}秒")
                
                processing_time = time.time() - start_time
                
                # 创建结果
                result = self._create_asr_result(
                    text, processing_time, audio_duration, frame_count, len(audio_data)
                )
                
                # 验证结果质量
                if self._validate_asr_result(result):
                    self._update_success_statistics(result)
                    return result
                else:
                    self.logger.debug(f"[{self.tag}] ASR结果质量不合格: {text}")
                    if attempt == self.max_retries:
                        self.statistics.failed_requests += 1
                        return result  # 返回最后一次的结果
                
            except asyncio.TimeoutError:
                self.logger.warning(f"[{self.tag}] ASR识别超时 (尝试 {attempt + 1})")
                if attempt == self.max_retries:
                    self.statistics.failed_requests += 1
                    return self._create_error_result("ASR识别超时", audio_duration, frame_count, len(audio_data))
            
            except Exception as e:
                self.logger.error(f"[{self.tag}] ASR识别失败 (尝试 {attempt + 1}): {e}")
                if attempt == self.max_retries:
                    self.statistics.failed_requests += 1
                    return self._create_error_result(str(e), audio_duration, frame_count, len(audio_data))
            
            # 重试前等待
            if attempt < self.max_retries:
                await asyncio.sleep(0.1 * (attempt + 1))  # 递增延迟
        
        return None
    
    def _create_asr_result(self, text: str, processing_time: float, audio_duration: float, 
                          frame_count: int, total_bytes: int) -> ASRResult:
        """
        创建ASR结果
        
        Args:
            text: 识别文本
            processing_time: 处理时间
            audio_duration: 音频时长
            frame_count: 帧数
            total_bytes: 总字节数
            
        Returns:
            ASRResult: ASR结果
        """
        # 计算置信度（基于文本长度和处理时间的启发式方法）
        confidence = self._estimate_confidence(text, processing_time, audio_duration)
        
        # 确定质量等级
        quality = self._determine_quality(text, confidence)
        
        # 检查是否有效
        is_valid = bool(text.strip()) and confidence >= self.min_confidence
        
        return ASRResult(
            text=text.strip(),
            confidence=confidence,
            quality=quality,
            processing_time=processing_time,
            audio_duration=audio_duration,
            frame_count=frame_count,
            total_bytes=total_bytes,
            is_valid=is_valid,
            metadata={
                "device_id": self.device_id,
                "timestamp": time.time(),
                "attempt_count": 1  # 这里简化，实际可以传递尝试次数
            }
        )
    
    def _create_error_result(self, error_message: str, audio_duration: float, 
                           frame_count: int, total_bytes: int) -> ASRResult:
        """
        创建错误结果
        
        Args:
            error_message: 错误信息
            audio_duration: 音频时长
            frame_count: 帧数
            total_bytes: 总字节数
            
        Returns:
            ASRResult: 错误结果
        """
        return ASRResult(
            text="",
            confidence=0.0,
            quality=ASRQuality.INVALID,
            processing_time=0.0,
            audio_duration=audio_duration,
            frame_count=frame_count,
            total_bytes=total_bytes,
            is_valid=False,
            error_message=error_message
        )
    
    def _estimate_confidence(self, text: str, processing_time: float, audio_duration: float) -> float:
        """
        估算识别置信度（启发式方法）
        
        Args:
            text: 识别文本
            processing_time: 处理时间
            audio_duration: 音频时长
            
        Returns:
            float: 置信度 (0.0-1.0)
        """
        if not text.strip():
            return 0.0
        
        # 基础置信度（基于文本长度）
        text_length = len(text.strip())
        if text_length < 2:
            base_confidence = 0.3
        elif text_length < 5:
            base_confidence = 0.6
        elif text_length < 20:
            base_confidence = 0.8
        else:
            base_confidence = 0.9
        
        # 处理时间因子（处理时间过短或过长都可能表示质量问题）
        if audio_duration > 0:
            time_ratio = processing_time / audio_duration
            if 0.1 <= time_ratio <= 2.0:  # 合理的处理时间比例
                time_factor = 1.0
            else:
                time_factor = 0.8
        else:
            time_factor = 0.5
        
        # 文本质量因子（检查是否包含常见的识别错误模式）
        quality_factor = 1.0
        if any(pattern in text.lower() for pattern in ["嗯", "啊", "呃", "额"]):
            quality_factor *= 0.7
        
        # 计算最终置信度
        confidence = base_confidence * time_factor * quality_factor
        
        return min(max(confidence, 0.0), 1.0)
    
    def _determine_quality(self, text: str, confidence: float) -> ASRQuality:
        """
        确定识别质量等级
        
        Args:
            text: 识别文本
            confidence: 置信度
            
        Returns:
            ASRQuality: 质量等级
        """
        if not text.strip():
            return ASRQuality.INVALID
        
        if confidence >= 0.95:
            return ASRQuality.EXCELLENT
        elif confidence >= 0.8:
            return ASRQuality.GOOD
        elif confidence >= 0.6:
            return ASRQuality.FAIR
        else:
            return ASRQuality.POOR
    
    def _validate_asr_result(self, result: ASRResult) -> bool:
        """
        验证ASR结果质量
        
        Args:
            result: ASR结果
            
        Returns:
            bool: 是否合格
        """
        # 基本验证
        if not result.is_valid:
            return False
        
        # 质量过滤
        if self.enable_quality_filter and result.quality == ASRQuality.POOR:
            return False
        
        # 重复过滤
        if self.enable_duplicate_filter and self._is_duplicate_result(result.text):
            self.logger.debug(f"[{self.tag}] 检测到重复结果: {result.text}")
            return False
        
        # 文本长度检查
        text_length = len(result.text)
        if text_length < self.min_text_length or text_length > self.max_text_length:
            return False
        
        return True
    
    def _is_duplicate_result(self, text: str) -> bool:
        """
        检查是否为重复结果
        
        Args:
            text: 识别文本
            
        Returns:
            bool: 是否重复
        """
        if text in self._result_cache:
            return True
        
        # 添加到缓存
        self._result_cache.append(text)
        if len(self._result_cache) > self._cache_size:
            self._result_cache.pop(0)
        
        return False
    
    def _update_success_statistics(self, result: ASRResult) -> None:
        """
        更新成功统计信息
        
        Args:
            result: ASR结果
        """
        self.statistics.successful_requests += 1
        self.statistics.total_processing_time += result.processing_time
        self.statistics.total_audio_duration += result.audio_duration
        self.statistics.total_bytes_processed += result.total_bytes
        
        # 更新质量统计
        if result.quality == ASRQuality.EXCELLENT:
            self.statistics.excellent_count += 1
        elif result.quality == ASRQuality.GOOD:
            self.statistics.good_count += 1
        elif result.quality == ASRQuality.FAIR:
            self.statistics.fair_count += 1
        elif result.quality == ASRQuality.POOR:
            self.statistics.poor_count += 1
        
        if not result.text.strip():
            self.statistics.empty_results += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "device_id": self.device_id,
            "requests": {
                "total": self.statistics.total_requests,
                "successful": self.statistics.successful_requests,
                "failed": self.statistics.failed_requests,
                "filtered": self.statistics.filtered_requests,
                "empty_results": self.statistics.empty_results,
                "success_rate": round(self.statistics.success_rate, 2)
            },
            "performance": {
                "avg_processing_time": round(self.statistics.avg_processing_time, 3),
                "avg_audio_duration": round(self.statistics.avg_audio_duration, 3),
                "total_bytes_processed": self.statistics.total_bytes_processed
            },
            "quality": {
                "excellent": self.statistics.excellent_count,
                "good": self.statistics.good_count,
                "fair": self.statistics.fair_count,
                "poor": self.statistics.poor_count
            },
            "config": {
                "min_audio_duration": self.min_audio_duration,
                "max_audio_duration": self.max_audio_duration,
                "min_confidence": self.min_confidence,
                "max_retries": self.max_retries,
                "timeout": self.timeout
            }
        }
        
        return stats
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        self.statistics = ASRStatistics()
        self._result_cache.clear()
        self.logger.info(f"[{self.tag}] 统计信息已重置")


# 全局ASR集成器字典
_asr_integrations: Dict[str, ESP32ASRServiceIntegration] = {}


def get_esp32_asr_integration(device_id: str) -> ESP32ASRServiceIntegration:
    """
    获取ESP32 ASR服务集成器
    
    Args:
        device_id: 设备ID
        
    Returns:
        ESP32ASRServiceIntegration: ASR服务集成器实例
    """
    if device_id not in _asr_integrations:
        _asr_integrations[device_id] = ESP32ASRServiceIntegration(device_id)
    
    return _asr_integrations[device_id]


def remove_esp32_asr_integration(device_id: str) -> None:
    """
    移除ESP32 ASR服务集成器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _asr_integrations:
        integration = _asr_integrations[device_id]
        integration.reset_statistics()
        del _asr_integrations[device_id]
