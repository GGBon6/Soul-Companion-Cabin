"""
主动对话服务
Proactive Chat Service
AI主动发起话题，增强互动性
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path

from app.core import settings, logger
from app.prompts.system_prompts import get_proactive_topic


class ProactiveChatRecord:
    """主动对话记录"""
    
    def __init__(self, user_id: str, timestamp: str, topic: str):
        self.user_id = user_id
        self.timestamp = timestamp
        self.topic = topic
    
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "topic": self.topic
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ProactiveChatRecord":
        return cls(
            user_id=data["user_id"],
            timestamp=data["timestamp"],
            topic=data["topic"]
        )


class ProactiveChatService:
    """主动对话服务"""
    
    def __init__(self):
        """初始化服务"""
        self.data_dir = Path(settings.BASE_DIR) / "data" / "proactive_chats"
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_record_file_path(self, user_id: str) -> Path:
        """获取用户主动对话记录文件路径"""
        return self.data_dir / f"{user_id}_proactive.json"
    
    def _load_records(self, user_id: str) -> list:
        """
        加载用户的主动对话记录
        
        Args:
            user_id: 用户ID
        
        Returns:
            list: 记录列表
        """
        file_path = self._get_record_file_path(user_id)
        
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [ProactiveChatRecord.from_dict(record) for record in data]
        except Exception as e:
            logger.error(f"加载主动对话记录失败: {e}")
            return []
    
    def _save_records(self, user_id: str, records: list):
        """
        保存用户的主动对话记录
        
        Args:
            user_id: 用户ID
            records: 记录列表
        """
        file_path = self._get_record_file_path(user_id)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                data = [record.to_dict() for record in records]
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存主动对话记录失败: {e}")
    
    def should_initiate_chat(
        self,
        user_id: str,
        proactive_chat_time: str = "20:00",
        proactive_chat_enabled: bool = True
    ) -> Dict:
        """
        检查是否应该发起主动对话
        
        Args:
            user_id: 用户ID
            proactive_chat_time: 设定的主动对话时间 (HH:MM)
            proactive_chat_enabled: 是否启用主动对话
        
        Returns:
            Dict: 检查结果
        """
        # 如果功能未启用
        if not proactive_chat_enabled:
            return {
                "should_chat": False,
                "reason": "proactive_chat_disabled"
            }
        
        # 获取当前时间
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")
        
        # 解析设定时间
        try:
            target_hour, target_minute = map(int, proactive_chat_time.split(":"))
        except:
            logger.error(f"无效的主动对话时间格式: {proactive_chat_time}")
            return {
                "should_chat": False,
                "reason": "invalid_time_format"
            }
        
        # 检查当前时间是否在目标时间的前后15分钟内
        target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        time_diff = abs((now - target_time).total_seconds() / 60)  # 分钟差
        
        if time_diff > 15:  # 不在15分钟窗口内
            return {
                "should_chat": False,
                "reason": "not_in_time_window",
                "next_time": proactive_chat_time
            }
        
        # 检查今天是否已经发起过主动对话
        records = self._load_records(user_id)
        today_records = [
            r for r in records 
            if r.timestamp.startswith(current_date)
        ]
        
        if today_records:
            return {
                "should_chat": False,
                "reason": "already_chatted_today",
                "last_chat": today_records[-1].timestamp
            }
        
        # 所有检查通过，可以发起主动对话
        return {
            "should_chat": True,
            "reason": "time_matched"
        }
    
    def generate_proactive_message(
        self,
        user_id: str,
        character_id: str = "xiaonuan",
        context: Dict = None
    ) -> str:
        """
        生成主动对话消息
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            context: 上下文信息（如最近的情绪、对话等）
        
        Returns:
            str: 主动对话内容
        """
        # 使用system_prompts中的get_proactive_topic函数
        topic = get_proactive_topic(character_id)
        
        # 记录这次主动对话
        self._record_chat(user_id, topic)
        
        logger.info(f"生成主动对话 - 用户: {user_id}, 角色: {character_id}")
        
        return topic
    
    def _record_chat(self, user_id: str, topic: str):
        """
        记录一次主动对话
        
        Args:
            user_id: 用户ID
            topic: 话题内容
        """
        records = self._load_records(user_id)
        
        # 创建新记录
        new_record = ProactiveChatRecord(
            user_id=user_id,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            topic=topic
        )
        
        records.append(new_record)
        
        # 只保留最近30天的记录
        cutoff_date = datetime.now() - timedelta(days=30)
        records = [
            r for r in records 
            if datetime.strptime(r.timestamp, "%Y-%m-%d %H:%M:%S") > cutoff_date
        ]
        
        self._save_records(user_id, records)
    
    def get_last_proactive_chat(self, user_id: str) -> Optional[Dict]:
        """
        获取最后一次主动对话的信息
        
        Args:
            user_id: 用户ID
        
        Returns:
            Optional[Dict]: 最后一次主动对话的信息
        """
        records = self._load_records(user_id)
        
        if not records:
            return None
        
        last_record = records[-1]
        return {
            "timestamp": last_record.timestamp,
            "topic": last_record.topic
        }
    
    def get_proactive_chat_history(
        self,
        user_id: str,
        days: int = 7
    ) -> list:
        """
        获取主动对话历史
        
        Args:
            user_id: 用户ID
            days: 获取最近多少天的记录
        
        Returns:
            list: 历史记录列表
        """
        records = self._load_records(user_id)
        
        # 计算起始日期
        start_date = datetime.now() - timedelta(days=days)
        
        # 过滤
        filtered_records = [
            r for r in records 
            if datetime.strptime(r.timestamp, "%Y-%m-%d %H:%M:%S") >= start_date
        ]
        
        return [r.to_dict() for r in filtered_records]
    
    def update_proactive_settings(
        self,
        user_id: str,
        enabled: bool = None,
        time: str = None
    ) -> Dict:
        """
        更新主动对话设置（这个函数主要用于验证和返回状态，实际设置保存在UserProfile中）
        
        Args:
            user_id: 用户ID
            enabled: 是否启用
            time: 主动对话时间
        
        Returns:
            Dict: 更新结果
        """
        result = {
            "success": True,
            "user_id": user_id
        }
        
        if enabled is not None:
            result["enabled"] = enabled
        
        if time is not None:
            # 验证时间格式
            try:
                hour, minute = map(int, time.split(":"))
                if not (0 <= hour < 24 and 0 <= minute < 60):
                    raise ValueError("时间超出范围")
                result["time"] = time
            except:
                result["success"] = False
                result["error"] = "无效的时间格式，应为 HH:MM"
        
        return result


# 全局单例
_proactive_chat_service = None


def get_proactive_chat_service() -> ProactiveChatService:
    """获取主动对话服务单例"""
    global _proactive_chat_service
    if _proactive_chat_service is None:
        _proactive_chat_service = ProactiveChatService()
    return _proactive_chat_service

