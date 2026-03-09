"""
共享服务模块
Shared Services Module
包含Web和设备服务共用的核心服务
"""

# 导入本地的服务文件
from .llm_service import get_llm_service, LLMService
from .asr_service import get_asr_service, ASRService, acquire_asr_service
from .tts_service import get_tts_service, TTSService
from .auth_service import AuthService
from .chat_history_service import get_chat_history_service, ChatHistoryService
from .audio_cache_service import get_audio_cache_service, AudioCacheService

__all__ = [
    # LLM服务
    'get_llm_service',
    'LLMService',
    
    # ASR服务
    'get_asr_service', 
    'ASRService',
    'acquire_asr_service',  # ASR连接池上下文管理器
    
    # TTS服务
    'get_tts_service',
    'TTSService',
    
    # 认证服务
    'AuthService',
    
    # 对话历史服务
    'get_chat_history_service',
    'ChatHistoryService',
    
    # 音频缓存服务
    'get_audio_cache_service',
    'AudioCacheService'
]
