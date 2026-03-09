"""
语音合成服务
TTS (Text-to-Speech) Service
基于 tts_client.py 迁移，封装DashScope CosyVoice API
支持客户端区分和监控（产品化版本）
"""

import os
import asyncio
import time
import threading
from typing import Optional, AsyncIterator, Dict
from dataclasses import dataclass
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat, ResultCallback

from app.core import settings, logger
from app.core.exceptions import TTSError, APIKeyError


@dataclass
class TTSMetrics:
    """TTS服务指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_time: float = 0.0
    total_chars: int = 0  # 总字符数
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def avg_time(self) -> float:
        """平均响应时间（秒）"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_time / self.successful_requests
    
    @property
    def avg_chars(self) -> float:
        """平均字符数"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_chars / self.successful_requests
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': round(self.success_rate, 2),
            'avg_time_ms': round(self.avg_time * 1000, 2),
            'total_chars': self.total_chars,
            'avg_chars': round(self.avg_chars, 1)
        }


# 角色到声音的映射
CHARACTER_VOICE_MAP = {
    "xiaonuan": "longyue_v2",      # 小暖 - 温暖磁性女
    "xiaocheng": "longshao_v2",    # 小橙 - 积极向上男
    "xiaozhi": "longcheng_v2",     # 小智 - 智慧青年男
    "xiaoshu": "longxiaoxia_v2",   # 小树 - 沉稳权威女
}


class TTSService:
    """
    语音合成服务类（产品化版本）
    支持客户端区分、并发控制和监控
    """
    
    def __init__(self, character_id: str = "xiaonuan"):
        """
        初始化TTS服务
        
        Args:
            character_id: 角色ID (xiaonuan, xiaocheng, xiaozhi, xiaoshu)
        """
        self.api_key = settings.DASHSCOPE_API_KEY
        
        if not self.api_key:
            logger.error("DASHSCOPE_API_KEY 未配置")
            raise APIKeyError("DASHSCOPE_API_KEY 未配置")
        
        # 设置API Key到环境变量（DashScope SDK需要）
        # 确保API Key是字符串类型
        if self.api_key:
            os.environ["DASHSCOPE_API_KEY"] = str(self.api_key)
        
        # CosyVoice 配置
        self.model = "cosyvoice-v2"

        # 根据角色设置音色
        self.character_id = character_id
        self.voice = CHARACTER_VOICE_MAP.get(character_id, "longyue_v2")
        
        # 并发控制
        self.max_concurrent = getattr(settings, 'TTS_MAX_CONCURRENT', 20)
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        logger.info(f"🔧 TTS并发控制: 最大{self.max_concurrent}个并发请求")
        
        # 客户端指标统计
        self.metrics = {
            'web': TTSMetrics(),
            'esp32': TTSMetrics(),
            'system': TTSMetrics()
        }
        
        """
        角色声音映射：
        - 小暖 (xiaonuan): longyue_v2 - 温暖磁性女
        - 小橙 (xiaocheng): longshao_v2 - 积极向上男
        - 小智 (xiaozhi): longcheng_v2 - 智慧青年男
        - 小树 (xiaoshu): longxiaoxia_v2 - 沉稳权威女
        
        其他可用音色：
        消费电子-儿童陪伴:longwangwang(台湾少年音),longpaopao(飞天泡泡音)
        消费电子-儿童有声书:longshanshan(戏剧化童声),longniuniu(阳光男童声)
        童声:longjielidou_v2(阳光顽皮男),longling_v2(稚气呆板女),longke_v2(懵懂乖乖女),longxian_v2(豪放可爱女)
        童声（标杆音色）:longhuhu(天真烂漫女童)
        社交陪伴:longanqin(亲和活泼女),longanling(思维灵动女),longhua_v2(元气甜美女),
                 longwan_v2(积极知性女),longcheng_v2(智慧青年男),longshao_v2(积极向上男)
        短视频配音:longhouge(经典猴哥),longgaoseng(得道高僧音),longjiqi(呆萌机器人)
        有声书:longyue_v2(温暖磁性女)
        语音助手:longxiaoxia_v2(沉稳权威女)
        """

        # 音频格式配置（匹配ESP32设备要求）
        self.format = AudioFormat.WAV_16000HZ_MONO_16BIT  # WAV格式，16kHz采样率
        self.sample_rate = 16000  # 采样率
        
        # 合成参数
        self.volume = 50  # 音量 0-100
        self.speech_rate = 1.0  # 语速 0.5-2.0
        self.pitch_rate = 1.0  # 音调 0.5-2.0
        
        # 并发控制
        self.max_concurrent = getattr(settings, 'TTS_MAX_CONCURRENT', 20)
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # 线程锁（保护SpeechSynthesizer创建）
        self._synthesis_lock = threading.Lock()
        
        # 客户端指标统计
        self.metrics = {
            'web': TTSMetrics(),
            'esp32': TTSMetrics(),
            'system': TTSMetrics()
        }
        
        logger.info(f"✅ TTS服务初始化完成: {self.model}/{self.voice} (角色: {character_id}, 支持客户端区分)")
    
    def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """
        非流式语音合成（同步调用）
        
        Args:
            text: 要合成的文本
            voice: 声音ID（可选）
        
        Returns:
            bytes: 音频数据（WAV格式字节）
        
        Raises:
            TTSError: 合成失败
        """
        try:
            logger.debug(f"开始TTS合成，文本长度: {len(text)} 字符")
            
            # 使用线程锁保护SpeechSynthesizer的创建和调用
            # 避免并发时WebSocket连接冲突
            with self._synthesis_lock:
                # 每次调用前需要重新初始化SpeechSynthesizer实例
                # 确保API Key被正确传递
                import dashscope
                dashscope.api_key = self.api_key
                
                synthesizer = SpeechSynthesizer(
                    model=self.model,
                    voice=voice or self.voice,
                    format=self.format,
                    volume=self.volume,
                    speech_rate=self.speech_rate,
                    pitch_rate=self.pitch_rate
                )
                
                # 同步调用，直接返回音频数据
                audio_data = synthesizer.call(text)
            
            if audio_data:
                logger.info(f"TTS合成成功，音频大小: {len(audio_data)} 字节")
                return audio_data
            else:
                logger.error("TTS合成失败：未接收到音频数据")
                raise TTSError("未接收到音频数据")
                
        except Exception as e:
            logger.error(f"TTS 合成失败: {e}", exc_info=True)
            raise TTSError(f"语音合成失败: {e}")

    async def synthesize_async(
        self, 
        text: str, 
        voice: Optional[str] = None,
        client_type: str = 'system'
    ) -> bytes:
        """
        非流式语音合成（异步封装，支持客户端区分）
        
        Args:
            text: 要合成的文本
            voice: 声音ID（可选）
            client_type: 客户端类型 ('web', 'esp32', 'system')
            
        Returns:
            bytes: 音频数据
        """
        # 验证客户端类型
        if client_type not in self.metrics:
            logger.warning(f"未知客户端类型: {client_type}，使用'system'")
            client_type = 'system'
        
        metrics = self.metrics[client_type]
        metrics.total_requests += 1
        metrics.total_chars += len(text)
        
        start_time = time.time()
        
        try:
            # 并发控制
            async with self.semaphore:
                current_concurrent = self.max_concurrent - self.semaphore._value
                logger.debug(
                    f"🔄 TTS请求 (client={client_type}, "
                    f"chars={len(text)}, "
                    f"并发={current_concurrent}/{self.max_concurrent})"
                )
                
                # 调用同步方法
                audio = await asyncio.to_thread(self.synthesize, text, voice)
                
                # 记录成功
                elapsed = time.time() - start_time
                metrics.successful_requests += 1
                metrics.total_time += elapsed
                
                logger.debug(
                    f"✅ TTS完成 (client={client_type}, "
                    f"time={elapsed*1000:.1f}ms, "
                    f"size={len(audio)}bytes, "
                    f"success_rate={metrics.success_rate:.1f}%)"
                )
                
                return audio
                
        except Exception as e:
            metrics.failed_requests += 1
            logger.error(f"❌ TTS失败 (client={client_type}): {e}")
            raise TTSError(f"语音合成失败: {e}")
    
    def get_metrics(self, client_type: Optional[str] = None) -> Dict:
        """
        获取TTS服务指标
        
        Args:
            client_type: 客户端类型，None表示获取所有
            
        Returns:
            Dict: 指标数据
        """
        if client_type:
            if client_type in self.metrics:
                return {client_type: self.metrics[client_type].to_dict()}
            else:
                return {}
        
        # 返回所有客户端的指标
        return {
            client_type: metrics.to_dict()
            for client_type, metrics in self.metrics.items()
        }
    
    def get_concurrent_info(self) -> Dict:
        """获取并发信息"""
        return {
            'max_concurrent': self.max_concurrent,
            'current_concurrent': self.max_concurrent - self.semaphore._value,
            'available_slots': self.semaphore._value
        }
    
    class _StreamCallback(ResultCallback):
        """流式调用回调类"""
        
        def __init__(self):
            self.audio_chunks = []
            self.error = None
            self.completed = False
            
        def on_data(self, data: bytes) -> None:
            """接收音频数据"""
            self.audio_chunks.append(data)
            
        def on_complete(self) -> None:
            """合成完成"""
            self.completed = True
            
        def on_error(self, message) -> None:
            """发生错误"""
            self.error = message
            self.completed = True
    
    async def synthesize_stream(
        self,
        text: str,
        voice: Optional[str] = None
    ) -> AsyncIterator[bytes]:
        """
        流式语音合成（异步调用方式）
        
        Args:
            text: 要合成的文本
            voice: 声音ID（可选）
        
        Yields:
            bytes: 音频数据块（WAV格式）
        
        Raises:
            TTSError: 合成失败
        """
        try:
            logger.debug(f"开始流式TTS合成，文本长度: {len(text)} 字符")
            
            # 创建回调实例
            callback = self._StreamCallback()
            
            # 创建SpeechSynthesizer实例（使用回调）
            synthesizer = SpeechSynthesizer(
                model=self.model,
                voice=voice or self.voice,
                format=self.format,
                volume=self.volume,
                speech_rate=self.speech_rate,
                pitch_rate=self.pitch_rate,
                callback=callback
            )
            
            # 异步调用（在单独的线程中执行）
            def _call_tts():
                synthesizer.call(text)
            
            # 在后台线程中执行TTS调用
            thread = threading.Thread(target=_call_tts)
            thread.start()
            
            # 流式返回音频块
            last_index = 0
            while not callback.completed:
                # 检查是否有新的音频块
                if len(callback.audio_chunks) > last_index:
                    for i in range(last_index, len(callback.audio_chunks)):
                        yield callback.audio_chunks[i]
                    last_index = len(callback.audio_chunks)
                await asyncio.sleep(0.01)  # 短暂休眠避免CPU占用
            
            # 返回剩余的音频块
            if len(callback.audio_chunks) > last_index:
                for i in range(last_index, len(callback.audio_chunks)):
                    yield callback.audio_chunks[i]
            
            # 等待线程结束
            thread.join()
            
            # 检查错误
            if callback.error:
                logger.error(f"流式 TTS 合成失败: {callback.error}")
                raise TTSError(f"流式 TTS 合成失败: {callback.error}")
            
            logger.info("流式TTS合成完成")
                        
        except Exception as e:
            logger.error(f"流式 TTS 合成失败: {e}", exc_info=True)
            raise TTSError(f"流式 TTS 合成失败: {e}")
    
    def synthesize_to_file(self, text: str, output_path: str, voice: Optional[str] = None):
        """
        合成音频并保存到文件
        
        Args:
            text: 要合成的文本
            output_path: 输出文件路径
            voice: 声音ID（可选）
        
        Raises:
            TTSError: 合成失败
        """
        try:
            audio_data = self.synthesize(text, voice)
            
            with open(output_path, 'wb') as f:
                f.write(audio_data)
            
            logger.info(f"音频已保存到: {output_path}")
            
        except Exception as e:
            logger.error(f"保存音频失败: {e}", exc_info=True)
            raise TTSError(f"保存音频失败: {e}")
    
    def set_character(self, character_id: str):
        """
        根据角色ID设置对应的声音
        
        Args:
            character_id: 角色ID (xiaonuan, xiaocheng, xiaozhi, xiaoshu)
        """
        if character_id in CHARACTER_VOICE_MAP:
            self.character_id = character_id
            self.voice = CHARACTER_VOICE_MAP[character_id]
            logger.info(f"切换到角色 {character_id}，声音: {self.voice}")
        else:
            logger.warning(f"未知角色ID: {character_id}，保持当前声音")
    
    def set_voice(self, voice: str):
        """
        直接设置声音（用于自定义声音）
        
        Args:
            voice: 声音ID (例如: longyue_v2, longshao_v2等)
        """
        self.voice = voice
        logger.info(f"设置声音: {voice}")
    
    def set_speech_rate(self, rate: float):
        """
        设置语速
        
        Args:
            rate: 语速，取值范围 0.5-2.0
        """
        self.speech_rate = max(0.5, min(2.0, rate))
        logger.debug(f"设置语速: {self.speech_rate}")
    
    def set_pitch_rate(self, rate: float):
        """
        设置音调
        
        Args:
            rate: 音调，取值范围 0.5-2.0
        """
        self.pitch_rate = max(0.5, min(2.0, rate))
        logger.debug(f"设置音调: {self.pitch_rate}")
    
    def set_volume(self, volume: int):
        """
        设置音量
        
        Args:
            volume: 音量，取值范围 0-100
        """
        self.volume = max(0, min(100, volume))
        logger.debug(f"设置音量: {self.volume}")


# 全局单例
_tts_service = None


def get_tts_service() -> TTSService:
    """获取TTS服务单例"""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service


def get_character_voice(character_id: str) -> str:
    """
    根据角色ID获取对应的声音
    
    Args:
        character_id: 角色ID (xiaonuan, xiaocheng, xiaozhi, xiaoshu)
    
    Returns:
        str: 对应的声音ID
    """
    return CHARACTER_VOICE_MAP.get(character_id, "longyue_v2")


if __name__ == "__main__":
    # 测试TTS服务
    logger.info("=" * 70)
    logger.info("🎙️ CosyVoice TTS 测试")
    logger.info("=" * 70)
    
    service = TTSService()
    logger.info(f"模型: {service.model}")
    logger.info(f"声音: {service.voice}")
    logger.info(f"音频格式: WAV 16kHz")
    logger.info(f"音量: {service.volume}")
    logger.info(f"语速: {service.speech_rate}")
    logger.info(f"音调: {service.pitch_rate}")
    
    # 测试非流式合成
    test_text = "哼，又是你啊。有什么事吗？"
    logger.info(f"测试文本: {test_text}")
    logger.info("开始合成...")
    
    audio_data = service.synthesize(test_text)
    
    if audio_data:
        filename = "test_tts.wav"
        with open(filename, 'wb') as f:
            f.write(audio_data)
        logger.info(f"测试成功！音频已保存: {filename}")
        logger.info(f"文件大小: {len(audio_data)} 字节")
