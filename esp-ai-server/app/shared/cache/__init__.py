"""
缓存优化模块
Cache Optimization Module
提供LLM响应缓存、用户画像缓存和智能缓存管理
"""

from .cache_manager import (
    CacheManager, 
    get_cache_manager, 
    initialize_cache_manager, 
    shutdown_cache_manager
)
from .llm_cache import LLMCache, get_llm_cache
from .user_profile_cache import UserProfileCache, get_user_profile_cache
from .cache_strategies import CacheStrategy, LRUStrategy, TTLStrategy
from .cache_monitor import CacheMonitor, get_cache_monitor

__all__ = [
    'CacheManager',
    'get_cache_manager',
    'initialize_cache_manager',
    'shutdown_cache_manager',
    'LLMCache',
    'get_llm_cache',
    'UserProfileCache',
    'get_user_profile_cache',
    'CacheStrategy',
    'LRUStrategy',
    'TTLStrategy',
    'CacheMonitor',
    'get_cache_monitor',
]
