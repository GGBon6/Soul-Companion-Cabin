"""
流式语音识别服务
Streaming ASR Service
基于Fun-ASR官方示例实现，支持持续音频流识别
参考: https://help.aliyun.com/zh/model-studio/developer-reference/realtime-asr-api
"""

import time
import threading
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

from app.core import settings, logger
from app.core.exceptions import ASRError, APIKeyError


class RecognitionState(Enum):
    """识别状态"""
    IDLE = "idle"           # 空闲
    STARTING = "starting"   # 启动中
    RUNNING = "running"     # 运行中
    STOPPING = "stopping"   # 停止中
    STOPPED = "stopped"      # 已停止
    ERROR = "error"          # 错误


@dataclass
class StreamingASRResult:
    """流式ASR结果"""
    text: str                    # 识别文本
    is_partial: bool             # 是否为部分结果
    confidence: float            # 置信度
    timestamp: float             # 时间戳
    metadata: Dict[str, Any]     # 元数据


class StreamingASRCallback(RecognitionCallback):
    """流式ASR回调处理"""
    
    def __init__(
        self,
        on_sentence: Optional[Callable[[str], None]] = None,
        on_partial: Optional[Callable[[str], None]] = None,
        silent: bool = False
    ):
        """
        初始化回调
        
        Args:
            on_sentence: 当识别出完整句子时的回调函数
            on_partial: 当识别出部分结果时的回调函数
            silent: 是否静默模式（减少日志输出）
        """
        self.on_sentence = on_sentence
        self.on_partial = on_partial
        self.silent = silent
        self.sentences: List[str] = []
        self.partial_results: List[str] = []
        self._lock = threading.Lock()
        
    def on_open(self) -> None:
        """连接建立时调用"""
        if not self.silent:
            logger.debug("🔗 [流式ASR] 连接已建立")
        
    def on_close(self) -> None:
        """连接关闭时调用"""
        if not self.silent:
            logger.debug("🔌 [流式ASR] 连接已关闭")
    
    def on_event(self, result: RecognitionResult) -> None:
        """接收识别结果时调用"""
        try:
            if not self.silent:
                logger.debug(f"📨 [流式ASR] 收到识别事件")
            
            # 获取句子结果
            sentence = result.get_sentence()
            if sentence:
                text = sentence.get('text', '')
                is_final = sentence.get('is_final', False)
                
                with self._lock:
                    if is_final:
                        # 完整句子
                        self.sentences.append(text)
                        if not self.silent:
                            logger.info(f"✅ [流式ASR] 完整句子: '{text}'")
                        
                        # 触发完整句子回调
                        if self.on_sentence:
                            try:
                                self.on_sentence(text)
                            except Exception as e:
                                logger.error(f"完整句子回调执行失败: {e}")
                    else:
                        # 部分结果
                        self.partial_results.append(text)
                        if not self.silent:
                            logger.debug(f"🔄 [流式ASR] 部分结果: '{text}'")
                        
                        # 触发部分结果回调
                        if self.on_partial:
                            try:
                                self.on_partial(text)
                            except Exception as e:
                                logger.error(f"部分结果回调执行失败: {e}")
            
        except Exception as e:
            logger.error(f"处理ASR回调事件失败: {e}", exc_info=True)
    
    def get_all_sentences(self) -> List[str]:
        """获取所有完整句子"""
        with self._lock:
            return self.sentences.copy()
    
    def get_latest_partial(self) -> Optional[str]:
        """获取最新的部分结果"""
        with self._lock:
            return self.partial_results[-1] if self.partial_results else None
    
    def clear(self):
        """清空结果"""
        with self._lock:
            self.sentences.clear()
            self.partial_results.clear()


class StreamingASRService:
    """流式语音识别服务（基于Fun-ASR官方示例）"""
    
    def __init__(self, connection_id: Optional[str] = None, client_type: str = "web"):
        """
        初始化流式ASR服务
        
        Args:
            connection_id: 连接池分配的连接ID
            client_type: 客户端类型 ("esp32" 或 "web")
        """
        self.api_key = settings.DASHSCOPE_API_KEY
        
        if not self.api_key:
            logger.error("DASHSCOPE_API_KEY 未配置")
            raise APIKeyError("DASHSCOPE_API_KEY 未配置")
        
        # 设置DashScope API Key
        dashscope.api_key = self.api_key
        
        # 模型配置
        self.model = "fun-asr-realtime"
        self.format = "pcm"
        self.sample_rate = 16000  # 16kHz - Fun-ASR只支持16kHz
        
        # 连接池信息
        self.connection_id = connection_id
        self.client_type = client_type
        
        # 识别器状态
        self.recognition: Optional[Recognition] = None
        self.callback: Optional[StreamingASRCallback] = None
        self.state = RecognitionState.IDLE
        self._lock = threading.Lock()
        
        # 统计信息
        self.total_frames_sent = 0
        self.total_bytes_sent = 0
        self.start_time: Optional[float] = None
        
        logger.debug(f"流式ASR服务实例创建: connection_id={connection_id}, client_type={client_type}")
    
    def start(
        self,
        on_sentence: Optional[Callable[[str], None]] = None,
        on_partial: Optional[Callable[[str], None]] = None,
        silent: bool = False
    ) -> bool:
        """
        启动流式识别
        
        Args:
            on_sentence: 完整句子回调
            on_partial: 部分结果回调
            silent: 是否静默模式
        
        Returns:
            bool: 是否启动成功
        
        Raises:
            ASRError: 启动失败
        """
        with self._lock:
            if self.state == RecognitionState.RUNNING:
                logger.warning("流式识别已在运行中")
                return False
            
            if self.state == RecognitionState.STARTING:
                logger.warning("流式识别正在启动中")
                return False
            
            self.state = RecognitionState.STARTING
        
        try:
            # 创建回调
            self.callback = StreamingASRCallback(
                on_sentence=on_sentence,
                on_partial=on_partial,
                silent=silent
            )
            
            # 创建识别器
            self.recognition = Recognition(
                model=self.model,
                format=self.format,
                sample_rate=self.sample_rate,
                callback=self.callback
            )
            
            # 启动识别
            self.recognition.start()
            
            with self._lock:
                self.state = RecognitionState.RUNNING
                self.start_time = time.time()
                self.total_frames_sent = 0
                self.total_bytes_sent = 0
            
            if not silent:
                logger.info(f"🚀 [流式ASR] 识别已启动 (模型: {self.model}, 格式: {self.format}, 采样率: {self.sample_rate}Hz)")
            
            return True
            
        except Exception as e:
            with self._lock:
                self.state = RecognitionState.ERROR
            logger.error(f"启动流式识别失败: {e}", exc_info=True)
            raise ASRError(f"启动流式识别失败: {e}")
    
    def send_audio_frame(self, audio_data: bytes) -> bool:
        """
        发送音频帧（推荐100ms间隔，1KB-16KB大小）
        
        根据Fun-ASR官方示例：
        - 建议每100ms发送一次音频数据
        - 每次发送1KB-16KB的音频数据
        - 对于16kHz单声道PCM，100ms = 1600样本 = 3200字节
        
        Args:
            audio_data: 音频数据块
        
        Returns:
            bool: 是否发送成功
        """
        with self._lock:
            if self.state != RecognitionState.RUNNING:
                logger.warning(f"流式识别未运行，当前状态: {self.state.value}")
                return False
            
            if not self.recognition:
                logger.error("识别器未初始化")
                return False
        
        try:
            # 发送音频帧
            self.recognition.send_audio_frame(audio_data)
            
            with self._lock:
                self.total_frames_sent += 1
                self.total_bytes_sent += len(audio_data)
            
            return True
            
        except Exception as e:
            logger.error(f"发送音频帧失败: {e}", exc_info=True)
            return False
    
    def stop(self, timeout: float = 2.0) -> bool:
        """
        停止流式识别
        
        Args:
            timeout: 超时时间（秒）
        
        Returns:
            bool: 是否成功停止
        """
        with self._lock:
            if self.state == RecognitionState.STOPPED:
                return True
            
            if self.state == RecognitionState.STOPPING:
                logger.warning("流式识别正在停止中")
                return False
            
            self.state = RecognitionState.STOPPING
        
        result = [False]
        
        def stop_worker():
            try:
                if self.recognition:
                    self.recognition.stop()
                    result[0] = True
            except Exception as e:
                if "Speech recognition has stopped" in str(e):
                    logger.debug(f"识别器已停止: {e}")
                    result[0] = True
                else:
                    logger.warning(f"停止识别器时出现异常: {e}")
        
        # 使用线程执行停止操作，避免阻塞
        stop_thread = threading.Thread(target=stop_worker)
        stop_thread.daemon = True
        stop_thread.start()
        stop_thread.join(timeout=timeout)
        
        with self._lock:
            if stop_thread.is_alive():
                logger.warning(f"识别器停止超时 ({timeout}s)，强制继续")
                self.state = RecognitionState.ERROR
            else:
                self.state = RecognitionState.STOPPED
                self.recognition = None
            
            # 记录统计信息
            if self.start_time:
                duration = time.time() - self.start_time
                logger.info(
                    f"📊 [流式ASR] 识别统计: "
                    f"时长={duration:.2f}s, "
                    f"帧数={self.total_frames_sent}, "
                    f"总字节={self.total_bytes_sent}, "
                    f"平均帧大小={self.total_bytes_sent // max(self.total_frames_sent, 1)}字节"
                )
        
        return result[0]
    
    def get_state(self) -> RecognitionState:
        """获取当前状态"""
        with self._lock:
            return self.state
    
    def is_running(self) -> bool:
        """检查是否正在运行"""
        with self._lock:
            return self.state == RecognitionState.RUNNING
    
    def get_results(self) -> Dict[str, Any]:
        """
        获取识别结果
        
        Returns:
            Dict: 包含完整句子和部分结果的字典
        """
        if not self.callback:
            return {
                "sentences": [],
                "partial_results": [],
                "latest_partial": None
            }
        
        return {
            "sentences": self.callback.get_all_sentences(),
            "partial_results": self.callback.partial_results.copy(),
            "latest_partial": self.callback.get_latest_partial()
        }
    
    def clear_results(self):
        """清空识别结果"""
        if self.callback:
            self.callback.clear()


# 服务实例缓存（按连接ID）
_streaming_asr_service_instances: dict[str, StreamingASRService] = {}


def get_streaming_asr_service(
    connection_id: Optional[str] = None,
    client_type: str = "web"
) -> StreamingASRService:
    """
    获取流式ASR服务实例
    
    Args:
        connection_id: 连接池分配的连接ID
        client_type: 客户端类型
    
    Returns:
        StreamingASRService实例
    """
    # 如果没有connection_id，创建临时实例（向后兼容）
    if connection_id is None:
        return StreamingASRService(connection_id=None, client_type=client_type)
    
    # 从缓存获取或创建新实例
    if connection_id not in _streaming_asr_service_instances:
        _streaming_asr_service_instances[connection_id] = StreamingASRService(
            connection_id=connection_id,
            client_type=client_type
        )
    
    return _streaming_asr_service_instances[connection_id]


def remove_streaming_asr_service(connection_id: str):
    """移除流式ASR服务实例"""
    if connection_id in _streaming_asr_service_instances:
        service = _streaming_asr_service_instances[connection_id]
        if service.is_running():
            service.stop()
        del _streaming_asr_service_instances[connection_id]
        logger.debug(f"流式ASR服务实例已移除: connection_id={connection_id}")


if __name__ == "__main__":
    # 测试流式ASR服务
    logger.info("=" * 70)
    logger.info("🎤 Fun-ASR 流式识别测试")
    logger.info("=" * 70)
    
    service = StreamingASRService()
    logger.info(f"模型: {service.model}")
    logger.info(f"格式: {service.format}")
    logger.info(f"采样率: {service.sample_rate}Hz")
    
    # 注意：实际测试需要提供音频数据
    logger.info("流式ASR服务已创建，等待音频数据...")

