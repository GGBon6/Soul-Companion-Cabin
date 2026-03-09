"""
故事数据模型
Story Data Models
定义故事功能相关的数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class StoryStatus(Enum):
    """故事状态枚举"""
    DRAFT = "draft"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class StoryTheme(Enum):
    """故事主题枚举"""
    ADVENTURE = "adventure"      # 冒险
    FRIENDSHIP = "friendship"    # 友谊
    FANTASY = "fantasy"         # 奇幻
    SCIENCE = "science"         # 科学
    NATURE = "nature"           # 自然


class StoryCharacter(Enum):
    """故事角色枚举"""
    XIAONUAN = "xiaonuan"       # 小暖
    WISE_OWL = "wise_owl"       # 智慧猫头鹰
    BRAVE_RABBIT = "brave_rabbit"  # 勇敢小兔
    KIND_BEAR = "kind_bear"     # 善良小熊


@dataclass
class Story:
    """故事模型"""
    
    story_id: str
    user_id: str
    title: str
    content: str
    theme: StoryTheme
    character: StoryCharacter
    status: StoryStatus = StoryStatus.DRAFT
    age_group: str = "3-8"  # 适合年龄段
    duration_minutes: int = 5  # 预计阅读时长
    keywords: List[str] = field(default_factory=list)
    moral_lesson: Optional[str] = None  # 寓意
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
            'story_id': self.story_id,
            'user_id': self.user_id,
            'title': self.title,
            'content': self.content,
            'theme': self.theme.value,
            'character': self.character.value,
            'status': self.status.value,
            'age_group': self.age_group,
            'duration_minutes': self.duration_minutes,
            'keywords': self.keywords,
            'moral_lesson': self.moral_lesson,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Story':
        """从字典创建故事"""
        created_at = None
        updated_at = None
        
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            updated_at = datetime.fromisoformat(data['updated_at'])
        
        return cls(
            story_id=data['story_id'],
            user_id=data['user_id'],
            title=data['title'],
            content=data['content'],
            theme=StoryTheme(data['theme']),
            character=StoryCharacter(data['character']),
            status=StoryStatus(data.get('status', 'draft')),
            age_group=data.get('age_group', '3-8'),
            duration_minutes=data.get('duration_minutes', 5),
            keywords=data.get('keywords', []),
            moral_lesson=data.get('moral_lesson'),
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get('metadata', {})
        )
    
    def update_status(self, status: StoryStatus):
        """更新故事状态"""
        self.status = status
        self.updated_at = datetime.now()
    
    def add_keyword(self, keyword: str):
        """添加关键词"""
        if keyword not in self.keywords:
            self.keywords.append(keyword)
            self.updated_at = datetime.now()
    
    def get_word_count(self) -> int:
        """获取字数"""
        return len(self.content)


@dataclass
class StoryRequest:
    """故事生成请求模型"""
    
    user_id: str
    theme: StoryTheme
    character: StoryCharacter
    custom_elements: List[str] = field(default_factory=list)  # 自定义元素
    age_group: str = "3-8"
    duration_minutes: int = 5
    mood_context: Optional[str] = None  # 情绪上下文
    previous_stories: List[str] = field(default_factory=list)  # 之前的故事ID
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'theme': self.theme.value,
            'character': self.character.value,
            'custom_elements': self.custom_elements,
            'age_group': self.age_group,
            'duration_minutes': self.duration_minutes,
            'mood_context': self.mood_context,
            'previous_stories': self.previous_stories,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoryRequest':
        """从字典创建请求"""
        created_at = None
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        return cls(
            user_id=data['user_id'],
            theme=StoryTheme(data['theme']),
            character=StoryCharacter(data['character']),
            custom_elements=data.get('custom_elements', []),
            age_group=data.get('age_group', '3-8'),
            duration_minutes=data.get('duration_minutes', 5),
            mood_context=data.get('mood_context'),
            previous_stories=data.get('previous_stories', []),
            created_at=created_at
        )


@dataclass
class StoryLibrary:
    """故事库模型"""
    
    user_id: str
    stories: List[Story] = field(default_factory=list)
    favorites: List[str] = field(default_factory=list)  # 收藏的故事ID
    recent_themes: List[StoryTheme] = field(default_factory=list)
    preferred_characters: List[StoryCharacter] = field(default_factory=list)
    total_stories: int = 0
    total_reading_time: int = 0  # 总阅读时长（分钟）
    
    def add_story(self, story: Story):
        """添加故事"""
        self.stories.append(story)
        self.total_stories += 1
        self.total_reading_time += story.duration_minutes
        
        # 更新最近主题
        if story.theme not in self.recent_themes:
            self.recent_themes.insert(0, story.theme)
            if len(self.recent_themes) > 5:
                self.recent_themes = self.recent_themes[:5]
        
        # 更新偏好角色
        if story.character not in self.preferred_characters:
            self.preferred_characters.append(story.character)
    
    def add_favorite(self, story_id: str):
        """添加收藏"""
        if story_id not in self.favorites:
            self.favorites.append(story_id)
    
    def remove_favorite(self, story_id: str):
        """移除收藏"""
        if story_id in self.favorites:
            self.favorites.remove(story_id)
    
    def get_stories_by_theme(self, theme: StoryTheme) -> List[Story]:
        """按主题获取故事"""
        return [story for story in self.stories if story.theme == theme]
    
    def get_stories_by_character(self, character: StoryCharacter) -> List[Story]:
        """按角色获取故事"""
        return [story for story in self.stories if story.character == character]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'stories': [story.to_dict() for story in self.stories],
            'favorites': self.favorites,
            'recent_themes': [theme.value for theme in self.recent_themes],
            'preferred_characters': [char.value for char in self.preferred_characters],
            'total_stories': self.total_stories,
            'total_reading_time': self.total_reading_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoryLibrary':
        """从字典创建故事库"""
        stories = [Story.from_dict(story_data) for story_data in data.get('stories', [])]
        recent_themes = [StoryTheme(theme) for theme in data.get('recent_themes', [])]
        preferred_characters = [StoryCharacter(char) for char in data.get('preferred_characters', [])]
        
        return cls(
            user_id=data['user_id'],
            stories=stories,
            favorites=data.get('favorites', []),
            recent_themes=recent_themes,
            preferred_characters=preferred_characters,
            total_stories=data.get('total_stories', 0),
            total_reading_time=data.get('total_reading_time', 0)
        )


@dataclass
class StoryTemplate:
    """故事模板模型"""
    
    template_id: str
    name: str
    theme: StoryTheme
    character: StoryCharacter
    plot_structure: List[str] = field(default_factory=list)  # 情节结构
    character_traits: Dict[str, str] = field(default_factory=dict)  # 角色特征
    setting_description: str = ""  # 场景描述
    moral_lessons: List[str] = field(default_factory=list)  # 可能的寓意
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
            'theme': self.theme.value,
            'character': self.character.value,
            'plot_structure': self.plot_structure,
            'character_traits': self.character_traits,
            'setting_description': self.setting_description,
            'moral_lessons': self.moral_lessons,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoryTemplate':
        """从字典创建模板"""
        created_at = None
        if data.get('created_at'):
            created_at = datetime.fromisoformat(data['created_at'])
        
        return cls(
            template_id=data['template_id'],
            name=data['name'],
            theme=StoryTheme(data['theme']),
            character=StoryCharacter(data['character']),
            plot_structure=data.get('plot_structure', []),
            character_traits=data.get('character_traits', {}),
            setting_description=data.get('setting_description', ''),
            moral_lessons=data.get('moral_lessons', []),
            is_active=data.get('is_active', True),
            created_at=created_at
        )
