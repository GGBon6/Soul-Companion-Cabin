"""
ESP32服务集成模块
ESP32 Services Integration Module
包含ASR、TTS、意图处理等服务的集成组件
"""

from .asr_service_integration import ESP32ASRServiceIntegration, ASRResult, get_esp32_asr_integration
from .streaming_asr_integration import ESP32StreamingASRIntegration, StreamingASRConfig, StreamingASRMode, get_streaming_asr_integration
from .tts_service_integration import ESP32TTSServiceIntegration, TTSRequest, TTSResult, get_esp32_tts_integration
from .streaming_tts_integration import ESP32StreamingTTSIntegration, StreamingTTSRequest, get_streaming_tts_integration
from .intent_processor import ESP32IntentProcessor, IntentRequest, IntentResult, get_esp32_intent_processor
from .speech_interaction_coordinator import ESP32SpeechInteractionCoordinator, InteractionRequest, InteractionResponse, InteractionResult, get_esp32_speech_coordinator
from .service_connection_manager import ESP32ServiceConnectionManager, get_esp32_service_manager
from .audio_format_converter import ESP32AudioFormatConverter, get_esp32_audio_converter
from .audio_processor import ESP32AudioProcessor, ESP32AudioEvent, get_esp32_audio_processor

__all__ = [
    # ASR服务集成
    'ESP32ASRServiceIntegration',
    'ASRResult',
    'get_esp32_asr_integration',
    
    # 流式ASR服务集成
    'ESP32StreamingASRIntegration',
    'StreamingASRConfig',
    'StreamingASRMode',
    'get_streaming_asr_integration',
    
    # TTS服务集成
    'ESP32TTSServiceIntegration',
    'TTSRequest',
    'TTSResult',
    'get_esp32_tts_integration',
    
    # 流式TTS服务集成
    'ESP32StreamingTTSIntegration',
    'StreamingTTSRequest',
    'get_streaming_tts_integration',
    
    # 意图处理
    'ESP32IntentProcessor',
    'IntentRequest',
    'IntentResult',
    'get_esp32_intent_processor',
    
    # 语音交互协调
    'ESP32SpeechInteractionCoordinator',
    'InteractionRequest',
    'InteractionResponse',
    'InteractionResult',
    'get_esp32_speech_coordinator',
    
    # 服务连接管理
    'ESP32ServiceConnectionManager',
    'get_esp32_service_manager',
    
    # 音频格式转换
    'ESP32AudioFormatConverter',
    'get_esp32_audio_converter',
    
    # 音频处理
    'ESP32AudioProcessor',
    'ESP32AudioEvent', 
    'get_esp32_audio_processor'
]
