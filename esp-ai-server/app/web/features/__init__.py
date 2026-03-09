"""
Web功能模块
Web Features Module
包含Web相关的功能处理器
"""

# 导入本地的功能处理器
from .character_handler import CharacterHandler
from .mood_handler import MoodHandler
from .diary_handler import DiaryHandler
from .story_handler import StoryHandler

__all__ = [
    'CharacterHandler',
    'MoodHandler', 
    'DiaryHandler',
    'StoryHandler'
]
