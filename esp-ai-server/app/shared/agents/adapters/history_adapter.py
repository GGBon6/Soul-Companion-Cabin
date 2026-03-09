"""
历史消息适配器
将 BaseAgent 的存储接口适配为传统的 HistoryService 接口
使用专门的对话历史存储来实现持久化
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from app.core import logger, settings
from app.shared.services.chat_history_service import ChatHistoryService, ChatMessage


class MessageAdapter:
    """消息适配器，兼容原有的 Message 接口"""
    
    def __init__(self, role: str, content: str, timestamp: str, metadata: dict = None):
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.metadata = metadata or {}
    
    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }


class HistoryAdapter:
    """历史消息适配器，使用专门的对话历史存储"""
    
    def __init__(self):
        self._memory_agent = None
        
        # 创建专门的对话历史服务
        self.chat_history_service = ChatHistoryService()
        logger.info("✅ 创建 HistoryService 适配器，使用专门的对话历史存储")
    
    @property
    def memory_agent(self):
        """延迟初始化 memory_agent"""
        if self._memory_agent is None:
            from app.shared.agents import get_memory_agent
            self._memory_agent = get_memory_agent()
        return self._memory_agent
    
    @property
    def working_cache(self):
        """获取 WorkingCache 实例"""
        return self.memory_agent.memory.wk_cache
    
    @property
    def episodic_store(self):
        """获取 EpisodicStore 实例"""
        return self.memory_agent.memory.ep_store
    
    def get_working_cache(self):
        """获取 WorkingCache 实例"""
        return self.working_cache
    
    def get_episodic_store(self):
        """获取 EpisodicStore 实例"""
        return self.memory_agent.memory.ep_store
    
    def get_chat_history_service(self):
        """获取对话历史服务实例"""
        return self.chat_history_service
    
    def load_history(self, user_id: str, limit: Optional[int] = None) -> List['MessageAdapter']:
        """
        加载用户的对话历史
        
        Args:
            user_id: 用户ID
            limit: 限制返回的消息数量（从最新开始）
        
        Returns:
            List[MessageAdapter]: 消息对象列表
        """
        try:
            # 从专门的对话历史服务获取消息
            chat_messages = self.chat_history_service.load_history(user_id, limit=limit)
            
            # 转换为 MessageAdapter 对象
            messages = []
            for chat_msg in chat_messages:
                message = MessageAdapter(
                    role=chat_msg.role,
                    content=chat_msg.content,
                    timestamp=chat_msg.timestamp,
                    metadata=chat_msg.metadata
                )
                messages.append(message)
            
            logger.debug(f"加载用户 {user_id} 的对话历史: {len(messages)} 条")
            return messages
            
        except Exception as e:
            logger.error(f"加载用户 {user_id} 的对话历史失败: {e}")
            return []
    
    def save_message(
        self, 
        user_id: str, 
        role: str,
        content: str,
        timestamp: str,
        metadata: dict = None
    ):
        """
        保存单条消息到对话历史
        
        Args:
            user_id: 用户ID
            role: 消息角色
            content: 消息内容
            timestamp: 时间戳
            metadata: 元数据
        """
        try:
            # 同时保存到工作缓存（用于短期上下文）和对话历史（用于持久化）
            self.working_cache.save_message(user_id, role, content, timestamp, metadata)
            self.chat_history_service.save_message(user_id, role, content, timestamp, metadata)
            logger.debug(f"保存消息到对话历史: {user_id} -> {role}")
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
    
    def save_messages_batch(
        self, 
        user_id: str, 
        messages: List['MessageAdapter']
    ) -> None:
        """
        批量保存消息
        
        Args:
            user_id: 用户ID
            messages: 消息对象列表
        """
        try:
            # 转换为对话历史格式
            chat_messages = []
            for msg in messages:
                chat_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "metadata": msg.metadata
                })
            
            # 保存到对话历史服务
            self.chat_history_service.save_messages_batch(user_id, chat_messages)
            
            # 同时保存到工作缓存
            self.working_cache.save_messages_batch(user_id, messages)
            
            logger.info(f"✅ 批量保存 {len(messages)} 条消息到对话历史")
            
        except Exception as e:
            logger.error(f"批量保存消息失败: {e}")
    
    def get_recent_context(self, user_id: str, max_messages: int = 20) -> List[dict]:
        """
        获取最近的对话历史作为上下文（用于LLM）
        
        Args:
            user_id: 用户ID
            max_messages: 最大消息数量
        
        Returns:
            List[dict]: 对话历史列表 [{"role": "user", "content": "..."}, ...]
        """
        try:
            messages = self.load_history(user_id, limit=max_messages)
            
            # 转换为LLM需要的格式
            context = []
            for message in messages:
                if message.role in ["user", "assistant"]:
                    context.append({
                        "role": message.role,
                        "content": message.content
                    })
            
            return context
            
        except Exception as e:
            logger.error(f"获取对话上下文失败: {e}")
            return []
    
    def get_grouped_history(
        self, 
        user_id: str, 
        days: int = 30
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取按日期分组的历史消息
        
        Args:
            user_id: 用户ID
            days: 获取最近N天的历史
        
        Returns:
            dict: 包含消息列表和分页信息的字典
        """
        try:
            grouped_messages = self.chat_history_service.get_grouped_history(user_id, days)
            
            # 转换为字典格式
            result = {}
            for date, chat_messages in grouped_messages.items():
                result[date] = [msg.to_dict() for msg in chat_messages]
            
            return result
            
        except Exception as e:
            logger.error(f"获取分组历史失败: {e}")
            return {}
    
    def get_history_by_date(
        self, 
        user_id: str, 
        start_date: str, 
        end_date: str = None
    ) -> List['MessageAdapter']:
        """
        根据日期范围获取历史消息
        
        Args:
            user_id: 用户ID
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)，默认为开始日期
        
        Returns:
            List[MessageAdapter]: 消息列表
        """
        try:
            if not end_date:
                end_date = start_date
            
            chat_messages = self.chat_history_service.load_history(user_id)
            
            # 转换为 MessageAdapter 对象
            messages = []
            for chat_msg in chat_messages:
                message = MessageAdapter(
                    role=chat_msg.role,
                    content=chat_msg.content,
                    timestamp=chat_msg.timestamp,
                    metadata=chat_msg.metadata
                )
                messages.append(message)
            
            return messages
            
        except Exception as e:
            logger.error(f"根据日期获取历史失败: {e}")
            return []
    
    def search_messages(
        self, 
        user_id: str, 
        query: str, 
        limit: int = 50
    ) -> List[dict]:
        """
        搜索聊天消息
        
        Args:
            user_id: 用户ID
            query: 搜索关键词
            limit: 最大返回结果数
        
        Returns:
            List[dict]: 匹配的消息列表，包含上下文信息
        """
        try:
            search_results = self.chat_history_service.search_messages(user_id, query, limit)
            
            results = []
            for chat_msg in search_results:
                result = {
                    "matched_message": chat_msg.to_dict(),
                    "score": 1.0  # ChatHistoryService 不返回分数，设置默认值
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"搜索消息失败: {e}")
            return []
    
    def get_statistics(self, user_id: str) -> dict:
        """
        获取用户的对话统计信息
        
        Args:
            user_id: 用户ID
        
        Returns:
            dict: 统计信息
        """
        try:
            return self.chat_history_service.get_statistics(user_id)
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "total_messages": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "first_message_time": None,
                "last_message_time": None,
                "conversation_days": 0
            }
    
    def delete_history(self, user_id: str, before_date: str = None) -> int:
        """
        删除用户的对话历史
        
        Args:
            user_id: 用户ID
            before_date: 删除指定日期之前的消息 (YYYY-MM-DD)，None表示删除全部
        
        Returns:
            int: 删除的消息数量
        """
        try:
            # 从对话历史服务删除
            deleted_count = self.chat_history_service.delete_history(user_id, before_date)
            
            # 同时清理工作缓存
            if before_date is None:
                self.working_cache.wipe(user_id)
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"删除历史失败: {e}")
            return 0


# 全局单例
_history_adapter = None


def get_history_service():
    """
    获取 HistoryService 适配器单例
    替换原有的 get_history_service 函数
    """
    global _history_adapter
    if _history_adapter is None:
        _history_adapter = HistoryAdapter()
        logger.info("✅ 创建 HistoryService 适配器，使用专门的对话历史存储")
    return _history_adapter
