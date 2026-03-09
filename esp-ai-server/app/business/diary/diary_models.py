"""
日记数据模型
Diary Data Models
定义日记功能相关的数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import json


@dataclass
class DiaryEntry:
    """日记条目模型"""
    
    user_id: str
    date: str  # YYYY-MM-DD格式
    content: str
    mood: Optional[str] = None
    weather: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    emotions: Dict[str, float] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'date': self.date,
            'content': self.content,
            'mood': self.mood,
            'weather': self.weather,
            'keywords': self.keywords,
            'emotions': self.emotions,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DiaryEntry':
        """从字典创建日记条目"""
        created_at = None
        updated_at = None
        
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])
        
        return cls(
            user_id=data['user_id'],
            date=data['date'],
            content=data['content'],
            mood=data.get('mood'),
            weather=data.get('weather'),
            keywords=data.get('keywords', []),
            emotions=data.get('emotions', {}),
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get('metadata', {})
        )
    
    def update_content(self, content: str):
        """更新日记内容"""
        self.content = content
        self.updated_at = datetime.now()
    
    def add_keyword(self, keyword: str):
        """添加关键词"""
        if keyword not in self.keywords:
            self.keywords.append(keyword)
            self.updated_at = datetime.now()
    
    def set_emotion(self, emotion: str, score: float):
        """设置情绪分数"""
        self.emotions[emotion] = score
        self.updated_at = datetime.now()
    
    def get_word_count(self) -> int:
        """获取字数"""
        return len(self.content)


@dataclass
class DiaryStatistics:
    """日记统计模型"""
    
    user_id: str
    total_entries: int = 0
    total_words: int = 0
    date_range: Dict[str, str] = field(default_factory=dict)  # start_date, end_date
    mood_distribution: Dict[str, int] = field(default_factory=dict)
    emotion_trends: Dict[str, List[float]] = field(default_factory=dict)
    keywords_frequency: Dict[str, int] = field(default_factory=dict)
    monthly_counts: Dict[str, int] = field(default_factory=dict)  # YYYY-MM -> count
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'total_entries': self.total_entries,
            'total_words': self.total_words,
            'date_range': self.date_range,
            'mood_distribution': self.mood_distribution,
            'emotion_trends': self.emotion_trends,
            'keywords_frequency': self.keywords_frequency,
            'monthly_counts': self.monthly_counts
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DiaryStatistics':
        """从字典创建统计数据"""
        return cls(
            user_id=data['user_id'],
            total_entries=data.get('total_entries', 0),
            total_words=data.get('total_words', 0),
            date_range=data.get('date_range', {}),
            mood_distribution=data.get('mood_distribution', {}),
            emotion_trends=data.get('emotion_trends', {}),
            keywords_frequency=data.get('keywords_frequency', {}),
            monthly_counts=data.get('monthly_counts', {})
        )


@dataclass
class DiaryTemplate:
    """日记模板模型"""
    
    template_id: str
    name: str
    description: str
    prompts: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    is_active: bool = True
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'template_id': self.template_id,
            'name': self.name,
            'description': self.description,
            'prompts': self.prompts,
            'categories': self.categories,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DiaryTemplate':
        """从字典创建模板"""
        created_at = None
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        return cls(
            template_id=data['template_id'],
            name=data['name'],
            description=data['description'],
            prompts=data.get('prompts', []),
            categories=data.get('categories', []),
            is_active=data.get('is_active', True),
            created_at=created_at
        )


@dataclass
class DiaryCalendar:
    """日记日历模型"""
    
    user_id: str
    year: int
    month: int
    entries: Dict[str, bool] = field(default_factory=dict)  # date -> has_entry
    mood_colors: Dict[str, str] = field(default_factory=dict)  # date -> mood_color
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'year': self.year,
            'month': self.month,
            'entries': self.entries,
            'mood_colors': self.mood_colors
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DiaryCalendar':
        """从字典创建日历"""
        return cls(
            user_id=data['user_id'],
            year=data['year'],
            month=data['month'],
            entries=data.get('entries', {}),
            mood_colors=data.get('mood_colors', {})
        )
    
    def add_entry(self, date: str, mood: str = None):
        """添加日记条目"""
        self.entries[date] = True
        if mood:
            self.mood_colors[date] = self._get_mood_color(mood)
    
    def _get_mood_color(self, mood: str) -> str:
        """获取情绪对应的颜色"""
        mood_colors = {
            'happy': '#FFD700',      # 金色
            'sad': '#4169E1',        # 蓝色
            'angry': '#FF4500',      # 红橙色
            'excited': '#FF69B4',    # 粉色
            'calm': '#98FB98',       # 浅绿色
            'anxious': '#DDA0DD',    # 紫色
            'neutral': '#D3D3D3'     # 浅灰色
        }
        return mood_colors.get(mood.lower(), '#D3D3D3')
