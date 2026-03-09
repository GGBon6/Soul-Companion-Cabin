"""
ESP32语音交互协调器
ESP32 Speech Interaction Coordinator
协调ASR、意图处理、TTS的完整语音交互流程
实现端到端的语音对话管理和状态控制
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
import logging

from ..audio import AudioFrame, ESP32AudioState
from .asr_service_integration import (
    ESP32ASRServiceIntegration,
    ASRResult,
    ASRQuality,
    get_esp32_asr_integration
)
from .tts_service_integration import ESP32TTSServiceIntegration, TTSRequest, TTSResult, get_esp32_tts_integration
from .streaming_tts_integration import ESP32StreamingTTSIntegration, StreamingTTSRequest, get_streaming_tts_integration
from .intent_processor import ESP32IntentProcessor, IntentRequest, IntentResult, get_esp32_intent_processor
from .service_connection_manager import ESP32ServiceConnectionManager, get_esp32_service_manager


class InteractionState(Enum):
    """交互状态"""
    IDLE = "idle"                       # 空闲
    LISTENING = "listening"             # 监听中
    PROCESSING_ASR = "processing_asr"   # ASR处理中
    PROCESSING_INTENT = "processing_intent"  # 意图处理中
    GENERATING_TTS = "generating_tts"   # TTS生成中
    SPEAKING = "speaking"               # 播放中
    ERROR = "error"                     # 错误状态
    INTERRUPTED = "interrupted"         # 中断状态


class InteractionResult(Enum):
    """交互结果"""
    SUCCESS = "success"                 # 成功
    ASR_FAILED = "asr_failed"          # ASR失败
    INTENT_FAILED = "intent_failed"    # 意图处理失败
    TTS_FAILED = "tts_failed"          # TTS失败
    TIMEOUT = "timeout"                # 超时
    INTERRUPTED = "interrupted"        # 中断
    INVALID_INPUT = "invalid_input"    # 无效输入


@dataclass
class InteractionRequest:
    """交互请求"""
    audio_frames: List[AudioFrame]      # 音频帧
    device_id: str                      # 设备ID
    session_id: str                     # 会话ID
    user_id: Optional[str] = None       # 用户ID
    priority: int = 0                   # 优先级
    timeout: float = 30.0               # 超时时间
    metadata: Dict[str, Any] = None     # 元数据


@dataclass
class InteractionResponse:
    """交互响应"""
    request: InteractionRequest         # 原始请求
    result: InteractionResult           # 交互结果
    state_history: List[InteractionState]  # 状态历史
    
    # 各阶段结果
    asr_result: Optional[ASRResult] = None
    intent_result: Optional[IntentResult] = None
    tts_result: Optional[TTSResult] = None
    
    # 时间统计
    total_time: float = 0.0
    asr_time: float = 0.0
    intent_time: float = 0.0
    tts_time: float = 0.0
    
    # 错误信息
    error_message: Optional[str] = None
    error_stage: Optional[str] = None
    
    # 元数据
    metadata: Dict[str, Any] = None


@dataclass
class InteractionStatistics:
    """交互统计"""
    total_interactions: int = 0
    successful_interactions: int = 0
    failed_interactions: int = 0
    interrupted_interactions: int = 0
    
    # 按结果类型统计
    asr_failures: int = 0
    intent_failures: int = 0
    tts_failures: int = 0
    timeouts: int = 0
    
    # 时间统计
    total_interaction_time: float = 0.0
    total_asr_time: float = 0.0
    total_intent_time: float = 0.0
    total_tts_time: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_interactions == 0:
            return 0.0
        return (self.successful_interactions / self.total_interactions) * 100
    
    @property
    def avg_interaction_time(self) -> float:
        """平均交互时间"""
        if self.successful_interactions == 0:
            return 0.0
        return self.total_interaction_time / self.successful_interactions


class ESP32SpeechInteractionCoordinator:
    """ESP32语音交互协调器"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.tag = f"ESP32SpeechCoordinator[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # 服务组件
        self.asr_integration = get_esp32_asr_integration(device_id)
        self.tts_integration = get_esp32_tts_integration(device_id)
        self.streaming_tts_integration = get_streaming_tts_integration(device_id)
        self.intent_processor = get_esp32_intent_processor(device_id)
        self.service_manager = get_esp32_service_manager(device_id)
        
        # 当前状态
        self.current_state = InteractionState.IDLE
        self.current_request: Optional[InteractionRequest] = None
        self.current_task: Optional[asyncio.Task] = None
        
        # 配置参数
        self.max_concurrent_interactions = 1   # 最大并发交互数
        self.default_timeout = 30.0           # 默认超时时间
        self.enable_interruption = True       # 启用中断
        self.enable_state_callbacks = True    # 启用状态回调
        self.use_streaming_tts = True         # 是否使用流式TTS（可配置）
        
        # 统计信息
        self.statistics = InteractionStatistics()
        
        # 回调函数
        self._state_change_callbacks: List[Callable[[InteractionState, InteractionState], None]] = []
        self._interaction_callbacks: List[Callable[[InteractionResponse], None]] = []
        
        # 延迟启动服务管理器的健康监控（在异步环境中启动）
        self._health_monitoring_started = False
        
        self.logger.info(f"[{self.tag}] 语音交互协调器初始化完成")
    
    def add_state_change_callback(self, callback: Callable[[InteractionState, InteractionState], None]) -> None:
        """添加状态变化回调"""
        self._state_change_callbacks.append(callback)
    
    def add_interaction_callback(self, callback: Callable[[InteractionResponse], None]) -> None:
        """添加交互结果回调"""
        self._interaction_callbacks.append(callback)
    
    async def process_speech_interaction(self, request: InteractionRequest) -> InteractionResponse:
        """
        处理语音交互
        
        Args:
            request: 交互请求
            
        Returns:
            InteractionResponse: 交互响应
        """
        start_time = time.time()
        self.statistics.total_interactions += 1
        
        # 首次调用时启动健康监控
        if not self._health_monitoring_started:
            try:
                asyncio.create_task(self.service_manager.start_health_monitoring())
                self._health_monitoring_started = True
            except Exception as e:
                self.logger.warning(f"[{self.tag}] 健康监控启动失败: {e}")
        
        # 检查并发限制
        if self.current_request and self.enable_interruption:
            await self._interrupt_current_interaction()
        elif self.current_request:
            return self._create_error_response(
                request, InteractionResult.INTERRUPTED, "系统繁忙，请稍后再试"
            )
        
        self.current_request = request
        state_history = []
        request_metadata = request.metadata or {}
        request.metadata = request_metadata
        
        provided_asr_result = request_metadata.get("asr_result")
        skip_asr = bool(request_metadata.get("skip_asr"))
        
        first_frame_metadata: Dict[str, Any] = {}
        if request.audio_frames:
            first_frame_metadata = request.audio_frames[0].metadata or {}
            if first_frame_metadata.get("skip_asr"):
                skip_asr = True
            if not provided_asr_result and first_frame_metadata.get("asr_result"):
                provided_asr_result = first_frame_metadata.get("asr_result")
        
        if skip_asr and not provided_asr_result:
            self.logger.warning(f"[{self.tag}] skip_asr 标记存在但未提供 asr_result，回退到正常ASR流程")
            skip_asr = False
        
        try:
            self.logger.info(f"[{self.tag}] 开始语音交互处理: {len(request.audio_frames)}帧")
            
            # 1. ASR阶段
            await self._change_state(InteractionState.PROCESSING_ASR, state_history)
            asr_start = time.time()
            
            if skip_asr and provided_asr_result:
                asr_result = self._normalize_external_asr_result(provided_asr_result, request_metadata)
                asr_time = time.time() - asr_start
                self.logger.info(f"[{self.tag}] 跳过ASR阶段，使用外部结果: '{asr_result.text}'")
            else:
                asr_result = await self.asr_integration.process_audio_frames(request.audio_frames)
                asr_time = time.time() - asr_start
            
            if not asr_result or not asr_result.is_valid:
                self.statistics.asr_failures += 1
                return self._create_error_response(
                    request, InteractionResult.ASR_FAILED, "语音识别失败",
                    state_history, asr_result=asr_result, asr_time=asr_time
                )
            
            self.logger.info(f"[{self.tag}] ASR识别成功: '{asr_result.text}'")
            
            # 2. 意图处理阶段
            await self._change_state(InteractionState.PROCESSING_INTENT, state_history)
            intent_start = time.time()
            
            intent_request = IntentRequest(
                user_text=asr_result.text,
                device_id=request.device_id,
                session_id=request.session_id,
                user_id=request.user_id,
                metadata=request.metadata
            )
            
            intent_result = await self.intent_processor.process_intent(intent_request)
            intent_time = time.time() - intent_start
            
            if not intent_result or intent_result.processing_status.value != "success":
                self.statistics.intent_failures += 1
                return self._create_error_response(
                    request, InteractionResult.INTENT_FAILED, "意图处理失败",
                    state_history, asr_result=asr_result, intent_result=intent_result,
                    asr_time=asr_time, intent_time=intent_time
                )
            
            self.logger.info(f"[{self.tag}] 意图处理成功: '{intent_result.response_text[:50]}...'")
            
            # 检查是否需要退出
            if intent_result.metadata and intent_result.metadata.get("should_close"):
                await self._change_state(InteractionState.IDLE, state_history)
                return self._create_success_response(
                    request, state_history, asr_result, intent_result, None,
                    asr_time, intent_time, 0.0, time.time() - start_time
                )
            
            # 3. TTS阶段
            await self._change_state(InteractionState.GENERATING_TTS, state_history)
            tts_start = time.time()
            
            if self.use_streaming_tts:
                # 使用流式TTS（基于CosyVoice官方示例）
                tts_result = await self._synthesize_with_streaming_tts(
                    intent_result.response_text,
                    request.device_id,
                    request.session_id,
                    request.user_id
                )
            else:
                # 使用普通TTS
                tts_request = TTSRequest(
                    text=intent_result.response_text,
                    metadata={"device_id": request.device_id, "session_id": request.session_id}
                )
                tts_result = await self.tts_integration.synthesize_text(tts_request)
            
            tts_time = time.time() - tts_start
            
            if not tts_result or not tts_result.is_success:
                self.statistics.tts_failures += 1
                return self._create_error_response(
                    request, InteractionResult.TTS_FAILED, "语音合成失败",
                    state_history, asr_result=asr_result, intent_result=intent_result,
                    tts_result=tts_result, asr_time=asr_time, intent_time=intent_time, tts_time=tts_time
                )
            
            self.logger.info(f"[{self.tag}] TTS合成成功: {len(tts_result.audio_frames)}帧")
            
            # 4. 播放阶段
            await self._change_state(InteractionState.SPEAKING, state_history)
            
            # 这里应该触发音频发送，但在协调器中我们只负责协调
            # 实际的音频发送由音频发送处理器完成
            
            # 5. 完成
            await self._change_state(InteractionState.IDLE, state_history)
            
            total_time = time.time() - start_time
            
            # 更新统计
            self.statistics.successful_interactions += 1
            self.statistics.total_interaction_time += total_time
            self.statistics.total_asr_time += asr_time
            self.statistics.total_intent_time += intent_time
            self.statistics.total_tts_time += tts_time
            
            response = self._create_success_response(
                request, state_history, asr_result, intent_result, tts_result,
                asr_time, intent_time, tts_time, total_time
            )
            
            # 触发交互完成回调
            for callback in self._interaction_callbacks:
                try:
                    callback(response)
                except Exception as e:
                    self.logger.error(f"[{self.tag}] 交互回调执行失败: {e}")
            
            return response
            
        except asyncio.TimeoutError:
            self.statistics.timeouts += 1
            return self._create_error_response(
                request, InteractionResult.TIMEOUT, "处理超时", state_history
            )
        
        except Exception as e:
            self.logger.error(f"[{self.tag}] 语音交互处理失败: {e}", exc_info=True)
            self.statistics.failed_interactions += 1
            return self._create_error_response(
                request, InteractionResult.ASR_FAILED, str(e), state_history
            )
        
        finally:
            self.current_request = None
            if self.current_state != InteractionState.IDLE:
                await self._change_state(InteractionState.IDLE, state_history)
    
    async def _change_state(self, new_state: InteractionState, state_history: List[InteractionState]) -> None:
        """
        改变交互状态
        
        Args:
            new_state: 新状态
            state_history: 状态历史
        """
        old_state = self.current_state
        self.current_state = new_state
        state_history.append(new_state)
        
        self.logger.debug(f"[{self.tag}] 状态变化: {old_state.value} -> {new_state.value}")
        
        # 触发状态变化回调
        if self.enable_state_callbacks:
            for callback in self._state_change_callbacks:
                try:
                    callback(old_state, new_state)
                except Exception as e:
                    self.logger.error(f"[{self.tag}] 状态变化回调执行失败: {e}")
    
    async def _interrupt_current_interaction(self) -> None:
        """中断当前交互"""
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            try:
                await self.current_task
            except asyncio.CancelledError:
                pass
        
        self.statistics.interrupted_interactions += 1
        self.current_request = None
        await self._change_state(InteractionState.INTERRUPTED, [])
        
        self.logger.info(f"[{self.tag}] 当前交互已中断")
    
    def _create_success_response(self, request: InteractionRequest, state_history: List[InteractionState],
                               asr_result: ASRResult, intent_result: IntentResult, tts_result: Optional[TTSResult],
                               asr_time: float, intent_time: float, tts_time: float, total_time: float) -> InteractionResponse:
        """创建成功响应"""
        return InteractionResponse(
            request=request,
            result=InteractionResult.SUCCESS,
            state_history=state_history,
            asr_result=asr_result,
            intent_result=intent_result,
            tts_result=tts_result,
            total_time=total_time,
            asr_time=asr_time,
            intent_time=intent_time,
            tts_time=tts_time,
            metadata={
                "device_id": self.device_id,
                "timestamp": time.time()
            }
        )
    
    def _normalize_external_asr_result(self, provided_asr_result: Any, request_metadata: Dict[str, Any]) -> ASRResult:
        """将外部提供的ASR结果统一为ASRResult对象"""
        extra_metadata = dict(request_metadata or {})
        extra_metadata.setdefault("source", extra_metadata.get("source", "external_asr"))
        
        if isinstance(provided_asr_result, ASRResult):
            merged_metadata = dict(provided_asr_result.metadata or {})
            merged_metadata.update(extra_metadata)
            provided_asr_result.metadata = merged_metadata
            if provided_asr_result.is_valid is None:
                provided_asr_result.is_valid = bool(provided_asr_result.text)
            return provided_asr_result
        
        if isinstance(provided_asr_result, str):
            text = provided_asr_result
            confidence = 0.9
            quality = ASRQuality.GOOD
            metadata = extra_metadata
            processing_time = 0.0
            audio_duration = 0.0
            frame_count = 0
            total_bytes = 0
        elif isinstance(provided_asr_result, dict):
            text = provided_asr_result.get("text", "")
            confidence = provided_asr_result.get("confidence", 0.9)
            quality_value = provided_asr_result.get("quality", ASRQuality.GOOD)
            if isinstance(quality_value, ASRQuality):
                quality = quality_value
            else:
                try:
                    quality = ASRQuality(quality_value)
                except Exception:
                    quality = ASRQuality.GOOD
            metadata = {
                **provided_asr_result.get("metadata", {}),
                **extra_metadata
            }
            processing_time = provided_asr_result.get("processing_time", 0.0)
            audio_duration = provided_asr_result.get("audio_duration", 0.0)
            frame_count = provided_asr_result.get("frame_count", 0)
            total_bytes = provided_asr_result.get("total_bytes", 0)
        else:
            text = str(provided_asr_result)
            confidence = 0.9
            quality = ASRQuality.GOOD
            metadata = extra_metadata
            processing_time = 0.0
            audio_duration = 0.0
            frame_count = 0
            total_bytes = 0
        
        return ASRResult(
            text=text,
            confidence=confidence,
            quality=quality,
            processing_time=processing_time,
            audio_duration=audio_duration,
            frame_count=frame_count,
            total_bytes=total_bytes,
            is_valid=bool(text.strip()),
            metadata=metadata
        )
    
    def _split_text_into_chunks(self, text: str, max_chunk_size: int = 2000) -> List[str]:
        """
        将文本分片（基于CosyVoice官方示例要求）
        
        Args:
            text: 待分片的文本
            max_chunk_size: 最大片段大小（字符数，默认2000）
        
        Returns:
            List[str]: 文本片段列表
        """
        if len(text) <= max_chunk_size:
            return [text]
        
        chunks = []
        # 按标点符号分片，尽量保持语义完整
        import re
        # 使用标点符号作为分片点
        punctuation_pattern = r'[。！？；\n]'
        
        current_chunk = ""
        for char in text:
            current_chunk += char
            
            # 如果遇到标点符号且当前片段足够长，进行分片
            if re.match(punctuation_pattern, char) and len(current_chunk) >= max_chunk_size * 0.5:
                chunks.append(current_chunk)
                current_chunk = ""
            # 如果当前片段超过最大长度，强制分片
            elif len(current_chunk) >= max_chunk_size:
                # 尝试在最后一个标点符号处分片
                last_punct = -1
                for i in range(len(current_chunk) - 1, max(0, len(current_chunk) - 100), -1):
                    if re.match(punctuation_pattern, current_chunk[i]):
                        last_punct = i + 1
                        break
                
                if last_punct > 0:
                    chunks.append(current_chunk[:last_punct])
                    current_chunk = current_chunk[last_punct:]
                else:
                    # 没有找到标点符号，直接截断
                    chunks.append(current_chunk[:max_chunk_size])
                    current_chunk = current_chunk[max_chunk_size:]
        
        # 添加剩余文本
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    async def _synthesize_with_streaming_tts(self, text: str, device_id: str, 
                                            session_id: str, user_id: Optional[str] = None) -> Optional[TTSResult]:
        """
        使用流式TTS合成文本（基于CosyVoice官方示例）
        
        Args:
            text: 待合成文本
            device_id: 设备ID
            session_id: 会话ID
            user_id: 用户ID
        
        Returns:
            Optional[TTSResult]: TTS结果
        """
        try:
            from .tts_service_integration import TTSRequest, TTSResult, TTSQuality
            
            # 将文本分片
            text_chunks = self._split_text_into_chunks(text, max_chunk_size=2000)
            
            self.logger.info(f"[{self.tag}] 流式TTS: 文本已分片为{len(text_chunks)}个片段")
            
            # 创建流式TTS请求
            streaming_request = StreamingTTSRequest(
                text_chunks=text_chunks,
                device_id=device_id,
                session_id=session_id,
                speech_rate=1.0,
                pitch_rate=1.0,
                volume=50,
                metadata={"user_id": user_id}
            )
            
            # 调用流式TTS合成
            audio_frames = await self.streaming_tts_integration.synthesize_streaming(streaming_request)
            
            if not audio_frames:
                return None
            
            # 创建TTSResult（兼容现有接口）
            # 创建一个虚拟的TTSRequest
            tts_request = TTSRequest(
                text=text,
                metadata={"device_id": device_id, "session_id": session_id, "streaming": True}
            )
            
            # 计算音频时长
            audio_duration = len(audio_frames) * (60.0 / 1000.0)  # 60ms per frame
            
            # 合并所有音频数据
            audio_data = b"".join([frame.data for frame in audio_frames])
            
            result = TTSResult(
                request=tts_request,
                audio_data=audio_data,
                audio_frames=audio_frames,
                quality=TTSQuality.HIGH,  # 流式TTS通常质量较高
                processing_time=0.0,  # 流式处理，无固定处理时间
                audio_duration=audio_duration,
                frame_count=len(audio_frames),
                total_bytes=len(audio_data),
                sample_rate=16000,
                is_success=True,
                metadata={
                    "device_id": device_id,
                    "session_id": session_id,
                    "streaming": True,
                    "chunk_count": len(text_chunks)
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 流式TTS合成失败: {e}", exc_info=True)
            return None
    
    def _create_error_response(self, request: InteractionRequest, result: InteractionResult,
                             error_message: str, state_history: List[InteractionState] = None,
                             asr_result: Optional[ASRResult] = None,
                             intent_result: Optional[IntentResult] = None,
                             tts_result: Optional[TTSResult] = None,
                             asr_time: float = 0.0, intent_time: float = 0.0, tts_time: float = 0.0) -> InteractionResponse:
        """创建错误响应"""
        self.statistics.failed_interactions += 1
        
        return InteractionResponse(
            request=request,
            result=result,
            state_history=state_history or [],
            asr_result=asr_result,
            intent_result=intent_result,
            tts_result=tts_result,
            total_time=asr_time + intent_time + tts_time,
            asr_time=asr_time,
            intent_time=intent_time,
            tts_time=tts_time,
            error_message=error_message,
            error_stage=result.value,
            metadata={
                "device_id": self.device_id,
                "timestamp": time.time()
            }
        )
    
    def get_current_state(self) -> InteractionState:
        """获取当前状态"""
        return self.current_state
    
    def is_busy(self) -> bool:
        """是否繁忙"""
        return self.current_request is not None
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "device_id": self.device_id,
            "current_state": self.current_state.value,
            "is_busy": self.is_busy(),
            "interactions": {
                "total": self.statistics.total_interactions,
                "successful": self.statistics.successful_interactions,
                "failed": self.statistics.failed_interactions,
                "interrupted": self.statistics.interrupted_interactions,
                "success_rate": round(self.statistics.success_rate, 2)
            },
            "failures": {
                "asr_failures": self.statistics.asr_failures,
                "intent_failures": self.statistics.intent_failures,
                "tts_failures": self.statistics.tts_failures,
                "timeouts": self.statistics.timeouts
            },
            "performance": {
                "avg_interaction_time": round(self.statistics.avg_interaction_time, 3),
                "avg_asr_time": round(self.statistics.total_asr_time / max(1, self.statistics.successful_interactions), 3),
                "avg_intent_time": round(self.statistics.total_intent_time / max(1, self.statistics.successful_interactions), 3),
                "avg_tts_time": round(self.statistics.total_tts_time / max(1, self.statistics.successful_interactions), 3)
            },
            "config": {
                "max_concurrent_interactions": self.max_concurrent_interactions,
                "default_timeout": self.default_timeout,
                "enable_interruption": self.enable_interruption,
                "enable_state_callbacks": self.enable_state_callbacks
            }
        }
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        self.statistics = InteractionStatistics()
        self.logger.info(f"[{self.tag}] 统计信息已重置")
    
    async def cleanup(self) -> None:
        """清理资源"""
        # 中断当前交互
        if self.current_request:
            await self._interrupt_current_interaction()
        
        # 停止服务管理器
        await self.service_manager.cleanup()
        
        self.logger.info(f"[{self.tag}] 语音交互协调器已清理")


# 全局语音交互协调器字典
_speech_coordinators: Dict[str, ESP32SpeechInteractionCoordinator] = {}


def get_esp32_speech_coordinator(device_id: str) -> ESP32SpeechInteractionCoordinator:
    """
    获取ESP32语音交互协调器
    
    Args:
        device_id: 设备ID
        
    Returns:
        ESP32SpeechInteractionCoordinator: 语音交互协调器实例
    """
    if device_id not in _speech_coordinators:
        _speech_coordinators[device_id] = ESP32SpeechInteractionCoordinator(device_id)
    
    return _speech_coordinators[device_id]


async def remove_esp32_speech_coordinator(device_id: str) -> None:
    """
    移除ESP32语音交互协调器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _speech_coordinators:
        coordinator = _speech_coordinators[device_id]
        await coordinator.cleanup()
        del _speech_coordinators[device_id]
