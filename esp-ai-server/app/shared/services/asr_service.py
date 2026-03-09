"""
语音识别服务
ASR Service
基于 asr_client.py 迁移，封装DashScope Fun-ASR Realtime API
"""

import time
import threading
from typing import Optional, Callable, AsyncContextManager
from contextlib import asynccontextmanager
import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

from app.core import settings, logger
from app.core.exceptions import ASRError, APIKeyError
from app.core.asr_connection_pool import get_asr_connection_pool


class RealtimeASRCallback(RecognitionCallback):
    """实时ASR回调处理"""
    
    def __init__(self, on_sentence: Optional[Callable[[str], None]] = None, silent: bool = False):
        """
        初始化回调
        
        Args:
            on_sentence: 当识别出完整句子时的回调函数
            silent: 是否静默模式（减少日志输出）
        """
        self.on_sentence = on_sentence
        self.sentences = []
        self.silent = silent
        
    def on_open(self) -> None:
        """连接建立时调用"""
        if not self.silent:
            logger.debug("ASR 连接已建立")
        
    def on_close(self) -> None:
        """连接关闭时调用"""
        if not self.silent:
            logger.debug("ASR 连接已关闭")
        
    def on_event(self, result: RecognitionResult) -> None:
        """接收识别结果时调用"""
        if not self.silent:
            logger.info(f"🔊 [ASR详细日志] 收到识别事件")
            logger.info(f"   📋 原始结果: {result}")
        
        sentence = result.get_sentence()
        if sentence:
            # 保存句子
            self.sentences.append(sentence['text'])
            
            if not self.silent:
                logger.info(f"   📝 解析句子: '{sentence['text']}'")
                logger.info(f"   📊 当前句子总数: {len(self.sentences)}")
                if 'confidence' in sentence:
                    logger.info(f"   🎯 置信度: {sentence.get('confidence', 'N/A')}")
            
            # 触发回调
            if self.on_sentence:
                if not self.silent:
                    logger.info(f"   📞 触发句子回调")
                self.on_sentence(sentence['text'])
            
            # 记录结果（只在非静默模式下）
            if not self.silent:
                logger.info(f"✅ [ASR详细日志] ASR识别: {sentence['text']}")
        else:
            if not self.silent:
                logger.info(f"   ❌ 未解析到句子内容")


class ASRService:
    """语音识别服务类（支持连接池）"""
    
    def __init__(self, connection_id: Optional[str] = None, client_type: str = "web"):
        """初始化ASR服务
        
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
        
        # 识别器
        self.recognition = None
        
        logger.debug(f"ASR服务实例创建: connection_id={connection_id}, client_type={client_type}")
    
    def _safe_stop_recognition(self, recognition, timeout: float = 2.0) -> bool:
        """
        安全停止识别器，带超时机制
        
        Args:
            recognition: 识别器实例
            timeout: 超时时间（秒）
        
        Returns:
            bool: 是否成功停止
        """
        result = [False]  # 使用列表来存储结果，避免闭包问题
        
        def stop_worker():
            try:
                recognition.stop()
                result[0] = True
            except Exception as e:
                # 忽略常见的停止异常
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
        
        if stop_thread.is_alive():
            logger.debug(f"识别器停止超时 ({timeout}s)，强制继续")
            return False
        
        return result[0]
    
    def transcribe(self, audio_data: bytes, format: str = "webm", enable_detailed_logs: bool = False) -> str:
        """
        非流式语音识别（优化版，减少连接开销）
        
        Args:
            audio_data: 音频二进制数据
            format: 音频格式 (pcm, wav, mp3, opus, speex, aac, amr等)
                    FUN-ASR支持多种格式，包括opus（需Ogg封装）
            enable_detailed_logs: 是否启用详细日志
        
        Returns:
            str: 识别出的文本
        
        Raises:
            ASRError: 识别失败
        """
        try:
            # 验证音频数据
            if not audio_data or len(audio_data) < 100:
                if enable_detailed_logs:
                    logger.info(f"🔍 [ASR详细日志] 音频数据验证失败: {len(audio_data) if audio_data else 0} 字节 < 100字节最小阈值")
                else:
                    logger.warning(f"音频数据太小或为空: {len(audio_data) if audio_data else 0} 字节")
                return ""
            
            if enable_detailed_logs:
                logger.info(f"🎤 [ASR详细日志] 开始语音识别")
                logger.info(f"   📊 音频数据大小: {len(audio_data)} 字节")
                logger.info(f"   🎵 音频格式: {format}")
                logger.info(f"   🔧 采样率: {self.sample_rate}Hz")
                logger.info(f"   🏷️ 模型: {self.model}")
                logger.info(f"   🆔 连接ID: {self.connection_id}")
                logger.info(f"   📱 客户端类型: {self.client_type}")
                
                # 音频数据十六进制预览（前32字节）
                hex_preview = audio_data[:32].hex() if len(audio_data) >= 32 else audio_data.hex()
                logger.info(f"   🔢 音频数据预览(前32字节): {hex_preview}")
            else:
                logger.debug(f"开始ASR识别，音频大小: {len(audio_data)} 字节，格式: {format}")
            
            # 创建回调收集结果
            callback = RealtimeASRCallback(silent=not enable_detailed_logs)
            
            # 创建识别器（减少日志输出）
            recognition = Recognition(
                model=self.model,
                format=format,
                sample_rate=self.sample_rate,
                callback=callback
            )
            
            try:
                # 启动识别
                if enable_detailed_logs:
                    logger.info(f"🚀 [ASR详细日志] 启动识别器")
                recognition.start()
                
                # 发送音频数据（分块发送）
                chunk_size = 3200  # 每次发送3200字节
                total_chunks = (len(audio_data) + chunk_size - 1) // chunk_size
                
                if enable_detailed_logs:
                    logger.info(f"📦 [ASR详细日志] 开始分块发送音频数据")
                    logger.info(f"   📏 块大小: {chunk_size} 字节")
                    logger.info(f"   📊 总块数: {total_chunks}")
                
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i:i + chunk_size]
                    chunk_num = i // chunk_size + 1
                    
                    if enable_detailed_logs:
                        logger.info(f"   📤 发送块 {chunk_num}/{total_chunks}: {len(chunk)} 字节")
                        # 显示块的十六进制预览（前16字节）
                        chunk_hex = chunk[:16].hex() if len(chunk) >= 16 else chunk.hex()
                        logger.info(f"      🔢 块数据预览: {chunk_hex}")
                    
                    recognition.send_audio_frame(chunk)
                    time.sleep(0.01)  # 小延迟，模拟实时输入
                
                if enable_detailed_logs:
                    logger.info(f"✅ [ASR详细日志] 音频数据发送完成")
                
                # 等待一小段时间让识别完成
                if enable_detailed_logs:
                    logger.info(f"⏳ [ASR详细日志] 等待识别完成...")
                time.sleep(0.1)
                
                # 安全停止识别（使用超时机制）
                if enable_detailed_logs:
                    logger.info(f"🛑 [ASR详细日志] 停止识别器")
                self._safe_stop_recognition(recognition, timeout=1.0)
                
                # 返回识别结果
                if callback.sentences:
                    result = ' '.join(callback.sentences)
                    if enable_detailed_logs:
                        logger.info(f"🎯 [ASR详细日志] 识别成功")
                        logger.info(f"   📝 识别结果: '{result}'")
                        logger.info(f"   📊 句子数量: {len(callback.sentences)}")
                        logger.info(f"   📏 文本长度: {len(result)} 字符")
                    else:
                        logger.info(f"ASR识别成功: {result}")
                    return result
                else:
                    if enable_detailed_logs:
                        logger.info(f"❌ [ASR详细日志] 识别无结果")
                        logger.info(f"   📊 回调句子数: {len(callback.sentences)}")
                    # 静默返回空结果，不输出日志（避免刷屏）
                    return ""
                    
            except KeyboardInterrupt:
                # 处理键盘中断（通常是系统关闭时触发）
                logger.debug("ASR识别被系统中断")
                self._safe_stop_recognition(recognition, timeout=0.2)
                return ""
            except Exception as inner_e:
                # 确保连接被正确关闭
                logger.error(f"ASR识别过程中出现异常: {inner_e}")
                self._safe_stop_recognition(recognition, timeout=0.5)
                raise inner_e
                
        except Exception as e:
            logger.error(f"ASR识别失败: {e}", exc_info=True)
            raise ASRError(f"语音识别失败: {e}")
    
    def start_realtime_recognition(self, 
                                   on_sentence: Optional[Callable[[str], None]] = None):
        """
        启动实时识别（用于麦克风输入）
        
        Args:
            on_sentence: 识别出句子时的回调函数
        
        Returns:
            Recognition: 识别器对象（需要手动调用 send_audio_frame 和 stop）
        
        Raises:
            ASRError: 启动失败
        """
        try:
            # 创建回调
            callback = RealtimeASRCallback(on_sentence=on_sentence)
            
            # 创建识别器
            self.recognition = Recognition(
                model=self.model,
                format=self.format,
                sample_rate=self.sample_rate,
                callback=callback
            )
            
            # 启动识别
            self.recognition.start()
            
            logger.info(f"实时识别已启动 (模型: {self.model})")
            return self.recognition
            
        except Exception as e:
            logger.error(f"启动实时识别失败: {e}", exc_info=True)
            raise ASRError(f"启动实时识别失败: {e}")
    
    def send_audio(self, audio_data: bytes):
        """
        发送音频数据到识别器
        
        Args:
            audio_data: 音频数据块
        """
        if self.recognition:
            self.recognition.send_audio_frame(audio_data)
    
    def stop_recognition(self):
        """停止实时识别"""
        if self.recognition:
            self.recognition.stop()
            self.recognition = None
            logger.info("实时识别已停止")
    
    def transcribe_file(self, file_path: str) -> str:
        """
        识别音频文件
        
        Args:
            file_path: 音频文件路径
        
        Returns:
            str: 识别出的文本
        
        Raises:
            ASRError: 识别失败
        """
        try:
            logger.debug(f"读取音频文件: {file_path}")
            
            with open(file_path, 'rb') as f:
                audio_data = f.read()
            
            logger.debug(f"文件大小: {len(audio_data)} 字节")
            
            # 获取文件扩展名
            file_ext = file_path.split('.')[-1].lower()
            
            # 识别
            result = self.transcribe(audio_data, file_ext)
            return result
            
        except Exception as e:
            logger.error(f"文件识别失败: {e}", exc_info=True)
            raise ASRError(f"文件识别失败: {e}")


# 服务实例缓存（按连接ID）
_asr_service_instances: dict[str, ASRService] = {}


def get_asr_service(connection_id: Optional[str] = None, client_type: str = "web") -> ASRService:
    """获取ASR服务实例
    
    Args:
        connection_id: 连接池分配的连接ID
        client_type: 客户端类型
    
    Returns:
        ASRService实例
    """
    # 如果没有connection_id，创建临时实例（向后兼容）
    if connection_id is None:
        return ASRService(connection_id=None, client_type=client_type)
    
    # 从缓存获取或创建新实例
    if connection_id not in _asr_service_instances:
        _asr_service_instances[connection_id] = ASRService(
            connection_id=connection_id,
            client_type=client_type
        )
    
    return _asr_service_instances[connection_id]


@asynccontextmanager
async def acquire_asr_service(
    client_type: str = "web",
    client_id: Optional[str] = None,
    timeout: Optional[float] = None
) -> AsyncContextManager[ASRService]:
    """从连接池获取ASR服务（上下文管理器）
    
    Args:
        client_type: 客户端类型 ("esp32" 或 "web")
        client_id: 客户端唯一标识
        timeout: 超时时间（秒）
    
    Yields:
        ASRService实例
    
    Example:
        async with acquire_asr_service("esp32", "device_123") as asr:
            result = asr.transcribe(audio_data)
    """
    pool = get_asr_connection_pool()
    conn_id = None
    start_time = time.time()
    success = True
    
    try:
        # 从连接池获取连接
        conn_id = await pool.acquire(
            client_type=client_type,
            client_id=client_id,
            timeout=timeout
        )
        
        # 获取或创建ASR服务实例
        asr_service = get_asr_service(connection_id=conn_id, client_type=client_type)
        
        logger.debug(f"ASR服务已获取: conn_id={conn_id}, client_type={client_type}")
        
        yield asr_service
        
    except Exception as e:
        success = False
        logger.error(f"ASR服务使用失败: {e}")
        raise
    
    finally:
        # 释放连接回连接池
        if conn_id:
            processing_time = time.time() - start_time
            await pool.release(conn_id, success=success, processing_time=processing_time)
            logger.debug(f"ASR服务已释放: conn_id={conn_id}, 处理时间={processing_time:.2f}s")


if __name__ == "__main__":
    # 测试ASR服务
    logger.info("=" * 70)
    logger.info("🎤 Fun-ASR Realtime 测试")
    logger.info("=" * 70)
    
    service = ASRService()
    logger.info(f"模型: {service.model}")
    logger.info(f"格式: {service.format}")
    logger.info(f"采样率: {service.sample_rate}Hz")
