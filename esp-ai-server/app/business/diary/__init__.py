"""
日记业务模块
Diary Business Module
包含日记功能的业务逻辑
"""

# 导入本地的日记服务和模型
from .diary_service import get_diary_service, DiaryService
from .diary_models import (
    DiaryEntry, DiaryStatistics, DiaryTemplate, 
    DiaryCalendar
)

__all__ = [
    # 服务
    'get_diary_service',
    'DiaryService',
    
    # 模型
    'DiaryEntry',
    'DiaryStatistics', 
    'DiaryTemplate',
    'DiaryCalendar'
]
