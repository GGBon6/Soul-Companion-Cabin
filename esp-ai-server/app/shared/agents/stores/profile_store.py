"""
用户档案存储实现
支持多证据验证的稳定特征和偏好存储
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

from app.core import logger
from app.shared.agents.base_agent import BaseAgent, MemoryType, MemoryRecord, RetentionPolicy


class FileProfileStore:
    """基于文件的用户档案存储"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "profiles"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 支持信号存储（内存中，重启会丢失，实际项目中应该持久化）
        self.support_signals = defaultdict(lambda: defaultdict(list))  # user_id -> key -> [signals]
        
        logger.debug(f"初始化用户档案存储: {self.data_dir}")
    
    def _get_user_file(self, user_id: str) -> Path:
        """获取用户档案文件路径"""
        return self.data_dir / f"{user_id}_profile.json"
    
    def upsert(self, records: List[MemoryRecord]) -> None:
        """插入或更新档案记录"""
        profile_records = [r for r in records if r.type == MemoryType.SEMANTIC_PROFILE]
        if not profile_records:
            return
        
        # 按用户分组处理
        user_records = defaultdict(list)
        for record in profile_records:
            user_records[record.user_id].append(record)
        
        for user_id, user_profiles in user_records.items():
            self._upsert_user_profiles(user_id, user_profiles)
    
    def _upsert_user_profiles(self, user_id: str, new_profiles: List[MemoryRecord]) -> None:
        """为单个用户更新档案"""
        file_path = self._get_user_file(user_id)
        
        # 加载现有档案
        existing_profiles = []
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_profiles = data.get("profiles", [])
            except Exception as e:
                logger.error(f"加载用户档案失败 {user_id}: {e}")
        
        # 添加新档案
        for record in new_profiles:
            profile_data = {
                "id": record.id,
                "content": record.content,
                "importance": record.importance,
                "created_at": record.timestamp,
                "meta": record.meta or {}
            }
            existing_profiles.append(profile_data)
        
        # 去重和排序（基于内容相似性，简化实现）
        existing_profiles = self._deduplicate_profiles(existing_profiles)
        
        # 保存
        self._save_user_profiles(user_id, existing_profiles)
        
        logger.debug(f"更新用户档案: {user_id} -> +{len(new_profiles)} 条")
    
    def get_recent_support(self, user_id: str, normalized_key: str, window_days: int) -> int:
        """获取特征支持证据数量"""
        signals = self.support_signals[user_id][normalized_key]
        cutoff = datetime.now() - timedelta(days=window_days)
        
        recent_count = 0
        for signal in signals:
            try:
                signal_time = signal.get("timestamp")
                if isinstance(signal_time, str):
                    signal_time = datetime.fromisoformat(signal_time)
                elif isinstance(signal_time, datetime):
                    pass
                else:
                    continue
                    
                if signal_time > cutoff:
                    recent_count += 1
            except Exception:
                continue
        
        return recent_count
    
    def add_support_signal(self, user_id: str, normalized_key: str, content: str) -> None:
        """添加特征支持信号"""
        signal = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "normalized_key": normalized_key
        }
        
        self.support_signals[user_id][normalized_key].append(signal)
        
        # 限制信号数量（工程化考虑）
        max_signals = 50
        if len(self.support_signals[user_id][normalized_key]) > max_signals:
            self.support_signals[user_id][normalized_key] = \
                self.support_signals[user_id][normalized_key][-max_signals:]
        
        logger.debug(f"添加支持信号: {user_id} -> {normalized_key}")
    
    def delete_expired(self, now: datetime, policy: RetentionPolicy) -> int:
        """删除过期档案（档案通常长期保存，这里简单实现）"""
        if not policy.ttl_hours:
            return 0
        
        deleted_count = 0
        cutoff_time = now - timedelta(hours=policy.ttl_hours)
        
        for file_path in self.data_dir.glob("*_profile.json"):
            try:
                deleted_count += self._clean_expired_profiles(file_path, cutoff_time, now)
            except Exception as e:
                logger.error(f"清理过期档案失败 {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"清理过期用户档案: {deleted_count} 条")
        
        return deleted_count
    
    def _clean_expired_profiles(self, file_path: Path, cutoff_time: datetime, now: datetime) -> int:
        """清理单个文件中的过期档案"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        profiles = data.get("profiles", [])
        original_count = len(profiles)
        
        # 过滤过期档案
        valid_profiles = []
        for profile in profiles:
            try:
                created_at = datetime.fromisoformat(profile["created_at"])
                if created_at > cutoff_time:
                    valid_profiles.append(profile)
            except Exception:
                # 如果时间解析失败，保留档案
                valid_profiles.append(profile)
        
        deleted_count = original_count - len(valid_profiles)
        
        # 如果有档案被删除，更新文件
        if deleted_count > 0:
            data["profiles"] = valid_profiles
            data["last_updated"] = now.isoformat()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        return deleted_count
    
    def _save_user_profiles(self, user_id: str, profiles: List[Dict[str, Any]]) -> None:
        """保存用户档案到文件"""
        file_path = self._get_user_file(user_id)
        
        try:
            data = {
                "user_id": user_id,
                "last_updated": datetime.now().isoformat(),
                "profile_count": len(profiles),
                "profiles": profiles
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存用户档案失败 {user_id}: {e}")
            raise
    
    def _deduplicate_profiles(self, profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重档案（简化实现，基于内容）"""
        seen_contents = set()
        unique_profiles = []
        
        # 按时间倒序排序，保留最新的
        profiles.sort(key=lambda p: p.get("created_at", ""), reverse=True)
        
        for profile in profiles:
            content = profile.get("content", "").strip().lower()
            if content and content not in seen_contents:
                seen_contents.add(content)
                unique_profiles.append(profile)
        
        return unique_profiles

    # ==================== 兼容 profile_service 的功能 ====================
    
    def get_profile(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户档案（兼容 profile_service 接口）
        
        Args:
            user_id: 用户ID
        
        Returns:
            Dict: 用户档案数据
        """
        file_path = self._get_user_file(user_id)
        
        if not file_path.exists():
            # 创建默认档案
            default_profile = {
                "user_id": user_id,
                "nickname": user_id,
                "intimacy_level": 1,
                "intimacy_points": 0,
                "last_active": datetime.now().isoformat(),
                "mood": "neutral",
                "preferences": {},
                "memories": [],
                "milestones": [],
                "created_at": datetime.now().isoformat(),
                # 兼容前端/处理器读取的字段
                "avatar": "",
                "current_character": "xiaonuan",
                "tree_hole_mode": False,
                "proactive_chat_enabled": False,
                "proactive_chat_time": "20:00",
            }
            self._save_user_profile_data(user_id, default_profile)
            return default_profile
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 兼容新旧格式
                if "profiles" in data:
                    # 新格式：从 profiles 列表中提取用户信息
                    profile_data = self._extract_user_info_from_profiles(user_id, data["profiles"])
                else:
                    # 旧格式：直接是用户档案数据
                    profile_data = data
                
                # 确保必要字段存在
                profile_data.setdefault("user_id", user_id)
                profile_data.setdefault("nickname", user_id)
                profile_data.setdefault("intimacy_level", 1)
                profile_data.setdefault("intimacy_points", 0)
                profile_data.setdefault("preferences", {})
                profile_data.setdefault("memories", [])
                profile_data.setdefault("milestones", [])
                # 兼容字段
                profile_data.setdefault("avatar", "")
                profile_data.setdefault("current_character", "xiaonuan")
                profile_data.setdefault("tree_hole_mode", False)
                profile_data.setdefault("proactive_chat_enabled", False)
                profile_data.setdefault("proactive_chat_time", "20:00")
                profile_data.setdefault("voice_enabled", True)
                
                return profile_data
                
        except Exception as e:
            logger.error(f"加载用户档案失败 {user_id}: {e}")
            # 返回默认档案
            return {
                "user_id": user_id,
                "nickname": user_id,
                "intimacy_level": 1,
                "intimacy_points": 0,
                "last_active": datetime.now().isoformat(),
                "mood": "neutral",
                "preferences": {},
                "memories": [],
                "milestones": []
            }
    
    def save_profile(self, profile_data: Dict[str, Any]) -> None:
        """
        保存用户档案（兼容 profile_service 接口）
        
        Args:
            profile_data: 用户档案数据
        """
        user_id = profile_data.get("user_id")
        if not user_id:
            raise ValueError("档案数据缺少 user_id")
        
        self._save_user_profile_data(user_id, profile_data)
        logger.debug(f"保存用户档案: {user_id}")
    
    def update_activity(self, user_id: str) -> None:
        """
        更新用户活跃时间
        
        Args:
            user_id: 用户ID
        """
        profile = self.get_profile(user_id)
        profile["last_active"] = datetime.now().isoformat()
        self.save_profile(profile)
    
    def add_intimacy(self, user_id: str, points: int) -> int:
        """
        增加亲密度
        
        Args:
            user_id: 用户ID
            points: 亲密度点数
        
        Returns:
            int: 新的亲密度等级
        """
        profile = self.get_profile(user_id)
        old_level = profile.get("intimacy_level", 1)
        old_points = profile.get("intimacy_points", 0)
        
        new_points = old_points + points
        new_level = self._calculate_intimacy_level(new_points)
        
        profile["intimacy_points"] = new_points
        profile["intimacy_level"] = new_level
        
        # 检查是否升级
        if new_level > old_level:
            logger.info(f"用户 {user_id} 亲密度升级: {old_level} → {new_level}")
            self.add_milestone(user_id, f"亲密度达到等级{new_level}")
        
        self.save_profile(profile)
        return new_level
    
    def add_memory(self, user_id: str, memory: str) -> None:
        """
        添加记忆
        
        Args:
            user_id: 用户ID
            memory: 记忆内容
        """
        profile = self.get_profile(user_id)
        memories = profile.get("memories", [])
        
        memory_entry = {
            "content": memory,
            "timestamp": datetime.now().isoformat()
        }
        
        memories.append(memory_entry)
        
        # 限制记忆数量
        max_memories = 100
        if len(memories) > max_memories:
            memories = memories[-max_memories:]
        
        profile["memories"] = memories
        self.save_profile(profile)
        logger.debug(f"为用户 {user_id} 添加记忆: {memory}")
    
    def update_mood(self, user_id: str, mood: str) -> None:
        """
        更新用户心情
        
        Args:
            user_id: 用户ID
            mood: 心情状态
        """
        profile = self.get_profile(user_id)
        profile["mood"] = mood
        profile["last_mood_update"] = datetime.now().isoformat()
        self.save_profile(profile)
        logger.debug(f"更新用户 {user_id} 心情: {mood}")
    
    def set_nickname(self, user_id: str, nickname: str) -> None:
        """
        设置用户昵称
        
        Args:
            user_id: 用户ID
            nickname: 昵称
        """
        profile = self.get_profile(user_id)
        profile["nickname"] = nickname
        self.save_profile(profile)
        logger.info(f"设置用户 {user_id} 昵称: {nickname}")
    
    def add_preference(self, user_id: str, key: str, value) -> None:
        """
        添加用户偏好
        
        Args:
            user_id: 用户ID
            key: 偏好键
            value: 偏好值
        """
        profile = self.get_profile(user_id)
        preferences = profile.get("preferences", {})
        preferences[key] = value
        profile["preferences"] = preferences
        self.save_profile(profile)
        logger.debug(f"为用户 {user_id} 添加偏好: {key}={value}")
    
    def add_milestone(self, user_id: str, milestone: str) -> None:
        """
        添加里程碑
        
        Args:
            user_id: 用户ID
            milestone: 里程碑内容
        """
        profile = self.get_profile(user_id)
        milestones = profile.get("milestones", [])
        
        milestone_entry = {
            "content": milestone,
            "timestamp": datetime.now().isoformat()
        }
        
        milestones.append(milestone_entry)
        profile["milestones"] = milestones
        self.save_profile(profile)
        logger.info(f"为用户 {user_id} 添加里程碑: {milestone}")
    
    def get_context_prompt(self, user_id: str) -> str:
        """
        获取用户上下文提示词（用于LLM）
        
        Args:
            user_id: 用户ID
        
        Returns:
            str: 用户上下文提示词
        """
        profile = self.get_profile(user_id)
        
        context_parts = []
        
        # 基本信息
        nickname = profile.get("nickname", user_id)
        intimacy_level = profile.get("intimacy_level", 1)
        context_parts.append(f"用户昵称: {nickname}")
        context_parts.append(f"亲密度等级: {intimacy_level}")
        
        # 当前心情
        mood = profile.get("mood")
        if mood and mood != "neutral":
            context_parts.append(f"当前心情: {mood}")
        
        # 偏好
        preferences = profile.get("preferences", {})
        if preferences:
            pref_items = [f"{k}: {v}" for k, v in preferences.items()]
            context_parts.append(f"偏好: {', '.join(pref_items)}")
        
        # 最近记忆
        memories = profile.get("memories", [])
        if memories:
            recent_memories = memories[-3:]  # 最近3条记忆
            memory_texts = [m.get("content", "") for m in recent_memories if m.get("content")]
            if memory_texts:
                context_parts.append(f"最近记忆: {'; '.join(memory_texts)}")
        
        return "\n".join(context_parts)
    
    def _calculate_intimacy_level(self, points: int) -> int:
        """
        根据亲密度点数计算等级
        
        Args:
            points: 亲密度点数
        
        Returns:
            int: 亲密度等级
        """
        if points < 50:
            return 1
        elif points < 150:
            return 2
        elif points < 300:
            return 3
        elif points < 500:
            return 4
        elif points < 800:
            return 5
        else:
            return 6
        

    # ========== 额外：提供 update_profile / update_avatar 以兼容适配器调用 ==========
    def update_profile(self, user_id: str, updated_data: Dict[str, Any]) -> None:
        """更新用户档案数据（整体替换/合并保存）"""
        if not isinstance(updated_data, dict):
            raise ValueError("updated_data 必须是字典")
        updated = {**self.get_profile(user_id), **updated_data}
        updated["user_id"] = user_id
        self._save_user_profile_data(user_id, updated)

    def update_avatar(self, user_id: str, avatar_data: str) -> bool:
        """更新用户头像数据，返回是否成功"""
        try:
            profile = self.get_profile(user_id)
            profile["avatar"] = avatar_data or ""
            self._save_user_profile_data(user_id, profile)
            return True
        except Exception as e:
            logger.error(f"更新头像失败 {user_id}: {e}")
            return False
    
    def _save_user_profile_data(self, user_id: str, profile_data: Dict[str, Any]) -> None:
        """
        保存用户档案数据到文件（兼容格式）
        
        Args:
            user_id: 用户ID
            profile_data: 档案数据
        """
        file_path = self._get_user_file(user_id)
        
        try:
            # 更新时间戳
            profile_data["last_updated"] = datetime.now().isoformat()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存用户档案数据失败 {user_id}: {e}")
            raise
    
    def _extract_user_info_from_profiles(self, user_id: str, profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        从 profiles 列表中提取指定用户的信息
        
        Args:
            user_id: 用户ID
            profiles: 用户档案列表
            
        Returns:
            Dict[str, Any]: 用户档案数据
        """
        # 查找匹配的用户档案
        for profile in profiles:
            if profile.get("user_id") == user_id:
                return profile
        
        # 如果没找到，返回默认档案
        logger.warning(f"在 profiles 列表中未找到用户 {user_id} 的档案，使用默认档案")
        return {
            "user_id": user_id,
            "nickname": user_id,
            "intimacy_level": 1,
            "intimacy_points": 0,
            "last_active": datetime.now().isoformat(),
            "mood": "neutral",
            "preferences": {},
            "memories": [],
            "milestones": [],
            "avatar": "",
            "current_character": "xiaonuan",
            "tree_hole_mode": False,
            "proactive_chat_enabled": False,
            "proactive_chat_time": "20:00",
            "voice_enabled": True
        }
