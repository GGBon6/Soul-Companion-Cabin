"""
业务逻辑模块
Business Logic Module
包含具体的业务功能实现
"""

# 导入日记模块
from .diary import (
    get_diary_service, DiaryService,
    DiaryEntry, DiaryStatistics, DiaryTemplate, DiaryCalendar
)

# 导入故事模块
from .story import (
    get_story_service, StoryService,
    Story, StoryRequest, StoryLibrary, StoryTemplate,
    StoryStatus, StoryTheme, StoryCharacter
)

# 导入对话模块
from .chat import (
    get_proactive_chat_service, ProactiveChatService,
    ChatMessage, ChatSession, ProactiveChatTrigger,
    ChatAnalytics, ChatPreferences,
    ChatType, ChatStatus, MessageRole
)

__all__ = [
    # 日记服务
    'get_diary_service',
    'DiaryService',
    'DiaryEntry',
    'DiaryStatistics',
    'DiaryTemplate',
    'DiaryCalendar',
    
    # 故事服务
    'get_story_service',
    'StoryService',
    'Story',
    'StoryRequest',
    'StoryLibrary',
    'StoryTemplate',
    'StoryStatus',
    'StoryTheme',
    'StoryCharacter',
    
    # 对话服务
    'get_proactive_chat_service',
    'ProactiveChatService',
    'ChatMessage',
    'ChatSession',
    'ProactiveChatTrigger',
    'ChatAnalytics',
    'ChatPreferences',
    'ChatType',
    'ChatStatus',
    'MessageRole'
]
