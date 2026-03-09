"""
工作缓存实现
短期记忆和会话缓存，支持TTL和LRU策略
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from collections import deque, OrderedDict

from app.core import logger
from app.shared.agents.base_agent import MemoryRecord


class MemoryWorkingCache:
    """内存工作缓存，支持TTL和LRU策略"""
    
    def __init__(self, default_ttl_hours: int = 2, max_users: int = 1000):
        # user_id -> OrderedDict[record_id, (record, expire_time)]
        self.cache: Dict[str, OrderedDict[str, Tuple[MemoryRecord, datetime]]] = {}
        self.default_ttl_hours = default_ttl_hours
        self.max_users = max_users
        
        logger.debug(f"初始化工作缓存: TTL={default_ttl_hours}h, 最大用户数={max_users}")
    
    def add(self, user_id: str, items: List[MemoryRecord], ttl_hours: int) -> None:
        """添加缓存项"""
        if not items:
            return
        
        # 确保用户缓存存在
        if user_id not in self.cache:
            self.cache[user_id] = OrderedDict()
        
        user_cache = self.cache[user_id]
        expire_time = datetime.now() + timedelta(hours=ttl_hours)
        
        # 添加新项目
        for item in items:
            # 如果已存在，更新（移到最后）
            if item.id in user_cache:
                del user_cache[item.id]
            
            user_cache[item.id] = (item, expire_time)
        
        # 清理过期项
        self._cleanup_expired_user(user_id)
        
        # 全局缓存管理
        self._manage_global_cache()
        
        logger.debug(f"添加工作缓存: {user_id} -> +{len(items)} 项，TTL={ttl_hours}h")
    
    def get(self, user_id: str) -> List[MemoryRecord]:
        """获取用户缓存"""
        if user_id not in self.cache:
            return []
        
        # 清理过期项
        self._cleanup_expired_user(user_id)
        
        user_cache = self.cache[user_id]
        records = []
        
        # 获取所有有效记录，并更新访问顺序（LRU）
        for record_id, (record, expire_time) in list(user_cache.items()):
            if datetime.now() < expire_time:
                # 移到最后（最近使用）
                user_cache.move_to_end(record_id)
                records.append(record)
        
        return records
    
    def trim(self, user_id: str, max_items: int = 100) -> None:
        """修剪缓存数量（保留最近使用的）"""
        if user_id not in self.cache:
            return
        
        user_cache = self.cache[user_id]
        
        # 先清理过期项
        self._cleanup_expired_user(user_id)
        
        # 如果仍然超过限制，移除最旧的项目
        while len(user_cache) > max_items:
            # OrderedDict 的 popitem(last=False) 移除最旧的项目
            removed_id, (removed_record, _) = user_cache.popitem(last=False)
            logger.debug(f"修剪缓存: {user_id} -> 移除 {removed_id}")
    
    def wipe(self, user_id: str) -> None:
        """清空用户缓存"""
        if user_id in self.cache:
            item_count = len(self.cache[user_id])
            del self.cache[user_id]
            logger.debug(f"清空工作缓存: {user_id} -> 移除 {item_count} 项")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息（工程化监控）"""
        total_users = len(self.cache)
        total_items = sum(len(user_cache) for user_cache in self.cache.values())
        
        # 统计过期项
        expired_items = 0
        now = datetime.now()
        for user_cache in self.cache.values():
            for _, (_, expire_time) in user_cache.items():
                if now >= expire_time:
                    expired_items += 1
        
        return {
            "total_users": total_users,
            "total_items": total_items,
            "expired_items": expired_items,
            "active_items": total_items - expired_items
        }
    
    def cleanup_all_expired(self) -> int:
        """清理所有过期项（定期维护任务）"""
        cleaned_count = 0
        
        for user_id in list(self.cache.keys()):
            cleaned_count += self._cleanup_expired_user(user_id)
        
        if cleaned_count > 0:
            logger.info(f"清理过期工作缓存: {cleaned_count} 项")
        
        return cleaned_count
    
    def _cleanup_expired_user(self, user_id: str) -> int:
        """清理单个用户的过期项"""
        if user_id not in self.cache:
            return 0
        
        user_cache = self.cache[user_id]
        now = datetime.now()
        expired_ids = []
        
        # 找出过期项
        for record_id, (_, expire_time) in user_cache.items():
            if now >= expire_time:
                expired_ids.append(record_id)
        
        # 移除过期项
        for record_id in expired_ids:
            del user_cache[record_id]
        
        # 如果用户缓存为空，移除用户
        if not user_cache:
            del self.cache[user_id]
        
        return len(expired_ids)
    
    def _manage_global_cache(self) -> None:
        """管理全局缓存大小"""
        if len(self.cache) <= self.max_users:
            return
        
        # 如果用户数超过限制，移除最不活跃的用户
        # 简单策略：移除缓存项最少的用户
        users_by_activity = sorted(
            self.cache.items(),
            key=lambda x: len(x[1])
        )
        
        users_to_remove = len(self.cache) - self.max_users
        for i in range(users_to_remove):
            user_id, user_cache = users_by_activity[i]
            item_count = len(user_cache)
            del self.cache[user_id]
            logger.debug(f"全局缓存管理: 移除用户 {user_id} ({item_count} 项)")
    
    def get_user_cache_info(self, user_id: str) -> Dict[str, any]:
        """获取用户缓存信息（调试用）"""
        if user_id not in self.cache:
            return {"exists": False}
        
        user_cache = self.cache[user_id]
        now = datetime.now()
        
        active_count = 0
        expired_count = 0
        
        for _, (_, expire_time) in user_cache.items():
            if now < expire_time:
                active_count += 1
            else:
                expired_count += 1
        
        return {
            "exists": True,
            "total_items": len(user_cache),
            "active_items": active_count,
            "expired_items": expired_count
        }

    # ==================== 兼容 history_service 的功能 ====================
    
    def save_message(
        self, 
        user_id: str, 
        role: str,
        content: str,
        timestamp: str,
        metadata: dict = None
    ) -> None:
        """
        保存单条消息（兼容 history_service 接口）
        
        Args:
            user_id: 用户ID
            role: 消息角色 (user/assistant)
            content: 消息内容
            timestamp: 时间戳
            metadata: 元数据
        """
        from app.shared.agents.base_agent import make_memory, MemoryType
        
        # 创建工作记忆记录
        memory = make_memory(
            user_id=user_id,
            type=MemoryType.WORKING_MEMORY,
            content=content,
            importance=4,
            meta={
                "role": role,
                "timestamp": timestamp,
                "metadata": metadata or {}
            }
        )
        
        # 添加到缓存
        self.add(user_id, [memory], self.default_ttl_hours)
        logger.debug(f"保存消息到工作缓存: {user_id} -> {role}")
    
    def save_messages_batch(
        self, 
        user_id: str, 
        messages: List['Message']
    ) -> None:
        """
        批量保存消息（兼容 history_service 接口）
        
        Args:
            user_id: 用户ID
            messages: 消息对象列表
        """
        from app.agents.base_agent import make_memory, MemoryType
        
        memories = []
        for msg in messages:
            memory = make_memory(
                user_id=user_id,
                type=MemoryType.WORKING_MEMORY,
                content=msg.content,
                importance=4,
                meta={
                    "role": msg.role,
                    "timestamp": msg.timestamp,
                    "metadata": getattr(msg, 'metadata', {})
                }
            )
            memories.append(memory)
        
        # 批量添加到缓存
        self.add(user_id, memories, self.default_ttl_hours)
        logger.info(f"✅ 批量保存 {len(messages)} 条消息到工作缓存")
    
    def get_recent_context(self, user_id: str, max_messages: int = 20) -> List[dict]:
        """
        获取最近的对话历史作为上下文（用于LLM）
        
        Args:
            user_id: 用户ID
            max_messages: 最大消息数量
        
        Returns:
            List[dict]: 对话历史列表 [{"role": "user", "content": "..."}, ...]
        """
        records = self.get(user_id)
        
        # 按时间排序
        records.sort(key=lambda r: r.timestamp)
        
        # 转换为LLM需要的格式
        context = []
        for record in records[-max_messages:]:
            meta = record.meta or {}
            role = meta.get("role", "user")
            if role in ["user", "assistant"]:
                context.append({
                    "role": role,
                    "content": record.content
                })
        
        return context
    
    def get_statistics(self, user_id: str) -> dict:
        """
        获取用户的对话统计信息
        
        Args:
            user_id: 用户ID
        
        Returns:
            dict: 统计信息
        """
        records = self.get(user_id)
        
        if not records:
            return {
                "total_messages": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "first_message_time": None,
                "last_message_time": None
            }
        
        user_count = 0
        assistant_count = 0
        timestamps = []
        
        for record in records:
            meta = record.meta or {}
            role = meta.get("role", "user")
            if role == "user":
                user_count += 1
            elif role == "assistant":
                assistant_count += 1
            
            timestamps.append(record.timestamp)
        
        timestamps.sort()
        
        return {
            "total_messages": len(records),
            "user_messages": user_count,
            "assistant_messages": assistant_count,
            "first_message_time": timestamps[0] if timestamps else None,
            "last_message_time": timestamps[-1] if timestamps else None
        }
