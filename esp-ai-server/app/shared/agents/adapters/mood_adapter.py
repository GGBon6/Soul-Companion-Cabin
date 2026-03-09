"""
MoodService 到 AffectStore 的适配器
提供向后兼容的接口，让现有代码无缝迁移到 memory_agent 架构
"""

from typing import Dict, List, Optional
# 延迟导入避免循环依赖
from app.core import logger


class MoodServiceAdapter:
    """
    MoodService 适配器
    将原有的 MoodService 接口适配到 memory_agent.AffectStore
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
    def affect_store(self):
        """获取 AffectStore 实例"""
        return self.memory_agent.memory.af_store
    
    def check_in(
        self,
        user_id: str,
        mood: str,
        note: str = "",
        intensity: int = 3
    ) -> Dict:
        """
        心情签到（适配到 AffectStore）
        
        Args:
            user_id: 用户ID
            mood: 情绪类型
            note: 备注说明
            intensity: 情绪强度 (1-5)
        
        Returns:
            Dict: 签到结果
        """
        try:
            return self.affect_store.check_in(user_id, mood, note, intensity)
        except Exception as e:
            logger.error(f"心情签到失败: {e}")
            raise
    
    def save_mood_with_id(self, user_id: str, mood_id: str, intensity: int, mood_note: str = "") -> bool:
        """保存心情数据（兼容性方法）"""
        try:
            result = self.check_in(user_id, mood_id, mood_note, intensity)
            return result is not None
        except Exception as e:
            logger.error(f"保存心情失败: {e}")
            return False
    
    def get_today_mood(self, user_id: str) -> Optional[Dict]:
        """
        获取今日心情签到记录
        
        Args:
            user_id: 用户ID
        
        Returns:
            Optional[Dict]: 今日最新的心情记录，如果没有则返回None
        """
        try:
            return self.affect_store.get_today_mood(user_id)
        except Exception as e:
            logger.error(f"获取今日心情失败: {e}")
            return None
    
    def get_mood_history(
        self,
        user_id: str,
        days: int = 7
    ) -> List[Dict]:
        """
        获取历史情绪记录
        
        Args:
            user_id: 用户ID
            days: 获取最近多少天的记录
        
        Returns:
            List[Dict]: 情绪记录列表
        """
        try:
            return self.affect_store.get_mood_history(user_id, days)
        except Exception as e:
            logger.error(f"获取心情历史失败: {e}")
            return []
    
    def get_mood_statistics(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict:
        """
        获取情绪统计数据
        
        Args:
            user_id: 用户ID
            days: 统计最近多少天
        
        Returns:
            Dict: 统计数据
        """
        try:
            return self.affect_store.get_mood_statistics(user_id, days)
        except Exception as e:
            logger.error(f"获取心情统计失败: {e}")
            return {
                "total_count": 0,
                "days_checked": 0,
                "mood_distribution": {},
                "most_common_mood": None,
                "average_intensity": 0,
                "trend": "neutral"
            }
    
    def get_mood_calendar(
        self,
        user_id: str,
        year: int = None,
        month: int = None
    ) -> Dict:
        """
        获取情绪日历（某个月每天的情绪）
        
        Args:
            user_id: 用户ID
            year: 年份（默认当前年）
            month: 月份（默认当前月）
        
        Returns:
            Dict: 日历数据 {date: mood_info}
        """
        try:
            return self.affect_store.get_mood_calendar(user_id, year, month)
        except Exception as e:
            logger.error(f"获取心情日历失败: {e}")
            return {"year": year, "month": month, "data": {}}
    
    def get_available_moods(self) -> List[Dict]:
        """
        获取所有可用的情绪类型
        
        Returns:
            List[Dict]: 情绪类型列表
        """
        try:
            return self.affect_store.get_available_moods()
        except Exception as e:
            logger.error(f"获取可用心情类型失败: {e}")
            return []
    
    # 兼容原有的属性访问
    @property
    def MOOD_TYPES(self):
        """兼容原有的 MOOD_TYPES 属性"""
        return self.affect_store.MOOD_TYPES


# 全局单例
_mood_adapter = None


def get_mood_service():
    """
    获取 MoodService 适配器单例
    替换原有的 get_mood_service 函数
    """
    global _mood_adapter
    if _mood_adapter is None:
        _mood_adapter = MoodServiceAdapter()
        logger.info("✅ 创建 MoodService 适配器，使用 memory_agent.AffectStore")
    return _mood_adapter
