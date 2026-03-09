"""
ProfileService 到 ProfileStore 的适配器
提供向后兼容的接口，让现有代码无缝迁移到 memory_agent 架构
"""

from typing import Dict, Optional
# 延迟导入避免循环依赖
from app.core import logger


class ProfileServiceAdapter:
    """
    ProfileService 适配器
    将原有的 ProfileService 接口适配到 memory_agent.ProfileStore
    """
    
    def __init__(self):
        self._memory_agent = None
    
    @property
    def memory_agent(self):
        """延迟初始化 memory_agent"""
        if self._memory_agent is None:
            from app.shared.agents import get_memory_agent
            self._memory_agent = get_memory_agent()
        return self._memory_agent
    
    @property
    def profile_store(self):
        """获取 ProfileStore 实例"""
        return self.memory_agent.memory.pr_store
    
    def get_profile(self, user_id: str) -> 'UserProfile':
        """
        获取用户档案（带缓存）
        
        Args:
            user_id: 用户ID
        
        Returns:
            UserProfile: 用户档案对象
        """
        try:
            profile_data = self.profile_store.get_profile(user_id)
            return UserProfileAdapter(profile_data, self.profile_store)
        except Exception as e:
            logger.error(f"获取用户档案失败: {e}")
            # 返回默认档案
            default_data = {
                "user_id": user_id,
                "nickname": user_id,
                "intimacy_level": 1,
                "intimacy_points": 0,
                "preferences": {},
                "memories": [],
                "milestones": []
            }
            return UserProfileAdapter(default_data, self.profile_store)
    
    def save_profile(self, profile: 'UserProfile'):
        """
        保存用户档案
        
        Args:
            profile: 用户档案对象
        """
        try:
            if hasattr(profile, '_data'):
                self.profile_store.save_profile(profile._data)
            else:
                logger.error("档案对象缺少 _data 属性")
        except Exception as e:
            logger.error(f"保存用户档案失败: {e}")
    
    def update_activity(self, user_id: str):
        """
        更新用户活跃时间
        
        Args:
            user_id: 用户ID
        """
        try:
            self.profile_store.update_activity(user_id)
        except Exception as e:
            logger.error(f"更新用户活跃时间失败: {e}")
    
    def add_intimacy(self, user_id: str, points: int):
        """
        增加亲密度
        
        Args:
            user_id: 用户ID
            points: 亲密度点数
        """
        try:
            self.profile_store.add_intimacy(user_id, points)
        except Exception as e:
            logger.error(f"增加亲密度失败: {e}")
    
    def add_memory(self, user_id: str, memory: str):
        """
        添加记忆
        
        Args:
            user_id: 用户ID
            memory: 记忆内容
        """
        try:
            self.profile_store.add_memory(user_id, memory)
        except Exception as e:
            logger.error(f"添加记忆失败: {e}")
    
    def update_mood(self, user_id: str, mood: str):
        """
        更新用户心情
        
        Args:
            user_id: 用户ID
            mood: 心情状态
        """
        try:
            self.profile_store.update_mood(user_id, mood)
        except Exception as e:
            logger.error(f"更新用户心情失败: {e}")
    
    def set_nickname(self, user_id: str, nickname: str):
        """
        设置用户昵称
        
        Args:
            user_id: 用户ID
            nickname: 昵称
        """
        try:
            self.profile_store.set_nickname(user_id, nickname)
        except Exception as e:
            logger.error(f"设置用户昵称失败: {e}")
    
    def add_preference(self, user_id: str, key: str, value):
        """
        添加用户偏好
        
        Args:
            user_id: 用户ID
            key: 偏好键
            value: 偏好值
        """
        try:
            self.profile_store.add_preference(user_id, key, value)
        except Exception as e:
            logger.error(f"添加用户偏好失败: {e}")
    
    def get_context_prompt(self, user_id: str) -> str:
        """
        获取用户上下文提示词（用于LLM）
        
        Args:
            user_id: 用户ID
        
        Returns:
            str: 用户上下文提示词
        """
        try:
            return self.profile_store.get_context_prompt(user_id)
        except Exception as e:
            logger.error(f"获取用户上下文提示词失败: {e}")
            return f"用户ID: {user_id}"
    
    def switch_character(self, user_id: str, character_id: str) -> bool:
        """
        切换用户角色
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
        
        Returns:
            bool: 是否成功
        """
        try:
            profile_data = self.profile_store.get_profile(user_id)
            profile_data["current_character"] = character_id
            self.profile_store.update_profile(user_id, profile_data)
            logger.info(f"用户 {user_id} 切换角色到: {character_id}")
            return True
        except Exception as e:
            logger.error(f"切换角色失败: {e}")
            return False
    
    def toggle_tree_hole_mode(self, user_id: str, enabled: bool) -> bool:
        """
        切换树洞模式
        
        Args:
            user_id: 用户ID
            enabled: 是否启用
        
        Returns:
            bool: 是否成功
        """
        try:
            profile_data = self.profile_store.get_profile(user_id)
            profile_data["tree_hole_mode"] = enabled
            self.profile_store.update_profile(user_id, profile_data)
            logger.info(f"用户 {user_id} 树洞模式: {'开启' if enabled else '关闭'}")
            return True
        except Exception as e:
            logger.error(f"切换树洞模式失败: {e}")
            return False
    
    def update_proactive_settings(self, user_id: str, enabled: bool, chat_time: str) -> bool:
        """
        更新主动聊天设置
        
        Args:
            user_id: 用户ID
            enabled: 是否启用
            chat_time: 聊天时间
        
        Returns:
            bool: 是否成功
        """
        try:
            profile_data = self.profile_store.get_profile(user_id)
            profile_data["proactive_chat_enabled"] = enabled
            profile_data["proactive_chat_time"] = chat_time
            self.profile_store.update_profile(user_id, profile_data)
            logger.info(f"用户 {user_id} 主动聊天设置: {'开启' if enabled else '关闭'}, 时间: {chat_time}")
            return True
        except Exception as e:
            logger.error(f"更新主动聊天设置失败: {e}")
            return False


class UserProfileAdapter:
    """
    UserProfile 适配器
    模拟原有的 UserProfile 类接口
    """
    
    def __init__(self, profile_data: Dict, profile_store):
        self._data = profile_data
        self._store = profile_store
    
    @property
    def user_id(self) -> str:
        return self._data.get("user_id", "")
    
    @property
    def nickname(self) -> str:
        return self._data.get("nickname", self.user_id)
    
    @property
    def intimacy_level(self) -> int:
        return self._data.get("intimacy_level", 1)
    
    @property
    def intimacy_points(self) -> int:
        return self._data.get("intimacy_points", 0)
    
    @property
    def mood(self) -> str:
        return self._data.get("mood", "neutral")
    
    @property
    def preferences(self) -> Dict:
        return self._data.get("preferences", {})
    
    @property
    def memories(self) -> list:
        return self._data.get("memories", [])
    
    @property
    def milestones(self) -> list:
        return self._data.get("milestones", [])
    
    @property
    def current_character(self) -> str:
        return self._data.get("current_character", "xiaonuan")
    
    @property
    def tree_hole_mode(self) -> bool:
        return self._data.get("tree_hole_mode", False)
    
    @property
    def proactive_chat_enabled(self) -> bool:
        return self._data.get("proactive_chat_enabled", False)
    
    @property
    def proactive_chat_time(self) -> str:
        return self._data.get("proactive_chat_time", "20:00")
    
    @property
    def avatar(self) -> str:
        return self._data.get("avatar", "")
    
    @property
    def voice_enabled(self) -> bool:
        return self._data.get("voice_enabled", True)
    
    def update_activity(self):
        """更新活跃时间"""
        self._store.update_activity(self.user_id)
    
    def add_intimacy(self, points: int):
        """增加亲密度"""
        self._store.add_intimacy(self.user_id, points)
        # 更新本地数据
        self._data = self._store.get_profile(self.user_id)
    
    def add_memory(self, memory: str):
        """添加记忆"""
        self._store.add_memory(self.user_id, memory)
        # 更新本地数据
        self._data = self._store.get_profile(self.user_id)
    
    def update_mood(self, mood: str):
        """更新心情"""
        self._store.update_mood(self.user_id, mood)
        # 更新本地数据
        self._data["mood"] = mood
    
    def set_nickname(self, nickname: str):
        """设置昵称"""
        self._store.set_nickname(self.user_id, nickname)
        # 更新本地数据
        self._data["nickname"] = nickname
    
    def add_preference(self, key: str, value):
        """添加偏好"""
        self._store.add_preference(self.user_id, key, value)
        # 更新本地数据
        preferences = self._data.get("preferences", {})
        preferences[key] = value
        self._data["preferences"] = preferences
    
    def add_milestone(self, milestone: str):
        """添加里程碑"""
        self._store.add_milestone(self.user_id, milestone)
        # 更新本地数据
        self._data = self._store.get_profile(self.user_id)
    
    def get_context_prompt(self) -> str:
        """获取上下文提示词"""
        return self._store.get_context_prompt(self.user_id)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return self._data.copy()
    
    @classmethod
    def from_dict(cls, data: Dict):
        """从字典创建（兼容方法）"""
        # 这个方法在适配器模式下不太适用，但为了兼容保留
        return cls(data, None)


# 全局单例
_profile_adapter = None


def get_profile_service():
    """
    获取 ProfileService 适配器单例
    替换原有的 get_profile_service 函数
    """
    global _profile_adapter
    if _profile_adapter is None:
        _profile_adapter = ProfileServiceAdapter()
        logger.info("✅ 创建 ProfileService 适配器，使用 memory_agent.ProfileStore")
    return _profile_adapter
