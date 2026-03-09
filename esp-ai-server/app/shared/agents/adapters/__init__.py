"""
MemoryAgent 适配器模块
提供与传统 services 的兼容性接口
"""

from .mood_adapter import MoodServiceAdapter, get_mood_service
from .profile_adapter import ProfileServiceAdapter, UserProfileAdapter, get_profile_service
from .history_adapter import HistoryAdapter, MessageAdapter, get_history_service

__all__ = [
    'MoodServiceAdapter', 'get_mood_service',
    'ProfileServiceAdapter', 'UserProfileAdapter', 'get_profile_service', 
    'HistoryAdapter', 'MessageAdapter', 'get_history_service'
]
