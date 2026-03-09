"""
对话历史服务
专门负责用户对话记录的存储和检索，类似微信聊天记录
与记忆智能体完全分离
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

from app.core import logger, settings


class ChatMessage:
    """对话消息数据类"""
    
    def __init__(self, role: str, content: str, timestamp: str = None, metadata: Dict = None):
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now().isoformat()
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """从字典创建消息对象"""
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )


class ChatHistoryService:
    """对话历史服务 - 专门负责聊天记录的存储和检索"""
    
    def __init__(self):
        self.data_dir = settings.DATA_DIR / "chat_history"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("✅ 对话历史服务初始化完成")
    
    def _get_user_file(self, user_id: str) -> Path:
        """获取用户的对话历史文件路径"""
        return self.data_dir / f"{user_id}_chat.json"
    
    def save_message(
        self, 
        user_id: str, 
        role: str, 
        content: str, 
        timestamp: str = None,
        metadata: Dict = None
    ) -> None:
        """
        保存单条消息
        
        Args:
            user_id: 用户ID
            role: 消息角色 (user/assistant/system)
            content: 消息内容
            timestamp: 时间戳
            metadata: 元数据
        """
        if user_id.startswith("guest_"):
            return  # 游客模式不保存历史
        
        message = ChatMessage(role, content, timestamp, metadata)
        self._append_message(user_id, message)
        logger.debug(f"💬 保存对话消息: {user_id} -> {role}")
    
    def load_history(
        self, 
        user_id: str, 
        limit: int = None
    ) -> List[ChatMessage]:
        """
        加载用户的对话历史
        
        Args:
            user_id: 用户ID
            limit: 限制返回的消息数量（从最新开始）
        
        Returns:
            List[ChatMessage]: 消息列表，按时间正序排列
        """
        if user_id.startswith("guest_"):
            return []
        
        file_path = self._get_user_file(user_id)
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                messages_data = data.get("messages", [])
            
            logger.info(f"📜 从文件加载原始数据: {len(messages_data)} 条消息")
            
            # 转换为消息对象
            messages = [ChatMessage.from_dict(msg) for msg in messages_data]
            
            # 按时间排序（最旧的在前面，最新的在后面）
            messages.sort(key=lambda m: m.timestamp)
            
            # 限制数量（保留最新的N条）
            if limit and limit > 0:
                messages = messages[-limit:]
            
            logger.info(f"📜 加载对话历史: {user_id} -> {len(messages)} 条 (限制: {limit})")
            return messages
            
        except Exception as e:
            logger.error(f"加载对话历史失败 {user_id}: {e}")
            return []
    
    def get_recent_context(self, user_id: str, max_messages: int = 20) -> List[Dict[str, str]]:
        """
        获取最近的对话上下文（用于LLM）
        
        Args:
            user_id: 用户ID
            max_messages: 最大消息数量
        
        Returns:
            List[Dict]: LLM格式的对话历史 [{"role": "user", "content": "..."}, ...]
        """
        messages = self.load_history(user_id, limit=max_messages)
        
        # 转换为LLM需要的格式，只保留用户和助手的消息
        context = []
        for message in messages:
            if message.role in ["user", "assistant"]:
                context.append({
                    "role": message.role,
                    "content": message.content
                })
        
        return context
    
    async def get_recent_messages(self, user_id: str, limit: int = 20) -> List[ChatMessage]:
        """
        获取最近的消息（异步版本，兼容ESP32模块调用）
        
        Args:
            user_id: 用户ID
            limit: 限制返回的消息数量
        
        Returns:
            List[ChatMessage]: 最近的消息列表
        """
        return self.load_history(user_id, limit=limit)
    
    def search_messages(
        self, 
        user_id: str, 
        query: str, 
        limit: int = 50
    ) -> List[ChatMessage]:
        """
        搜索消息内容
        
        Args:
            user_id: 用户ID
            query: 搜索关键词
            limit: 限制返回数量
        
        Returns:
            List[ChatMessage]: 匹配的消息列表
        """
        messages = self.load_history(user_id)
        query_lower = query.lower()
        
        results = []
        for message in messages:
            if query_lower in message.content.lower():
                results.append(message)
        
        # 按时间倒序排列（最新的在前）
        results.sort(key=lambda m: m.timestamp, reverse=True)
        return results[:limit]
    
    def get_grouped_history(self, user_id: str, days: int = 30) -> Dict[str, List[ChatMessage]]:
        """
        获取按日期分组的对话历史
        
        Args:
            user_id: 用户ID
            days: 获取最近N天的历史
        
        Returns:
            Dict[str, List[ChatMessage]]: 按日期分组的消息
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        messages = self.load_history(user_id)
        
        # 过滤日期范围
        filtered_messages = []
        for message in messages:
            try:
                msg_date = datetime.fromisoformat(message.timestamp)
                if start_date <= msg_date <= end_date:
                    filtered_messages.append(message)
            except Exception:
                # 如果时间戳解析失败，包含在结果中
                filtered_messages.append(message)
        
        # 按日期分组
        grouped = defaultdict(list)
        for message in filtered_messages:
            try:
                msg_date = datetime.fromisoformat(message.timestamp).strftime('%Y-%m-%d')
                grouped[msg_date].append(message)
            except Exception:
                # 如果时间戳解析失败，放到今天
                today = datetime.now().strftime('%Y-%m-%d')
                grouped[today].append(message)
        
        return dict(grouped)
    
    def get_statistics(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户的对话统计信息
        
        Args:
            user_id: 用户ID
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        messages = self.load_history(user_id)
        
        if not messages:
            return {
                "total_messages": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "first_message_time": None,
                "last_message_time": None,
                "conversation_days": 0
            }
        
        user_count = sum(1 for m in messages if m.role == "user")
        assistant_count = sum(1 for m in messages if m.role == "assistant")
        
        timestamps = [m.timestamp for m in messages]
        timestamps.sort()
        
        # 计算对话天数
        try:
            first_date = datetime.fromisoformat(timestamps[0]).date()
            last_date = datetime.fromisoformat(timestamps[-1]).date()
            conversation_days = (last_date - first_date).days + 1
        except Exception:
            conversation_days = 1
        
        return {
            "total_messages": len(messages),
            "user_messages": user_count,
            "assistant_messages": assistant_count,
            "first_message_time": timestamps[0] if timestamps else None,
            "last_message_time": timestamps[-1] if timestamps else None,
            "conversation_days": conversation_days
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
        if before_date is None:
            # 删除全部历史
            file_path = self._get_user_file(user_id)
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        count = len(data.get("messages", []))
                    
                    file_path.unlink()
                    logger.info(f"🗑️ 删除用户 {user_id} 的全部对话历史: {count} 条")
                    return count
                except Exception as e:
                    logger.error(f"删除对话历史失败: {e}")
                    return 0
            return 0
        else:
            # 删除指定日期之前的消息
            messages = self.load_history(user_id)
            cutoff_date = datetime.strptime(before_date, '%Y-%m-%d')
            
            remaining_messages = []
            deleted_count = 0
            
            for message in messages:
                try:
                    msg_date = datetime.fromisoformat(message.timestamp)
                    if msg_date >= cutoff_date:
                        remaining_messages.append(message)
                    else:
                        deleted_count += 1
                except Exception:
                    # 如果时间戳解析失败，保留消息
                    remaining_messages.append(message)
            
            # 保存剩余消息
            if remaining_messages:
                self._save_messages(user_id, remaining_messages)
            else:
                # 如果没有剩余消息，删除文件
                file_path = self._get_user_file(user_id)
                if file_path.exists():
                    file_path.unlink()
            
            logger.info(f"🗑️ 删除用户 {user_id} 在 {before_date} 之前的对话历史: {deleted_count} 条")
            return deleted_count
    
    def _append_message(self, user_id: str, message: ChatMessage) -> None:
        """追加单条消息到文件"""
        file_path = self._get_user_file(user_id)
        
        # 加载现有数据
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"读取对话历史文件失败: {e}")
                data = {"user_id": user_id, "messages": []}
        else:
            data = {"user_id": user_id, "messages": []}
        
        # 添加新消息
        data["messages"].append(message.to_dict())
        data["last_updated"] = datetime.now().isoformat()
        data["message_count"] = len(data["messages"])
        
        # 保存到文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存对话历史失败: {e}")
            raise
    
    def _save_messages(self, user_id: str, messages: List[ChatMessage]) -> None:
        """完全覆盖保存消息到文件"""
        file_path = self._get_user_file(user_id)
        
        data = {
            "user_id": user_id,
            "messages": [msg.to_dict() for msg in messages],
            "last_updated": datetime.now().isoformat(),
            "message_count": len(messages)
        }
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存对话历史失败: {e}")
            raise


# 全局单例
_chat_history_service = None


def get_chat_history_service() -> ChatHistoryService:
    """获取对话历史服务单例"""
    global _chat_history_service
    if _chat_history_service is None:
        _chat_history_service = ChatHistoryService()
    return _chat_history_service
