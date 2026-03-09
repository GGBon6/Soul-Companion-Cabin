"""
用户画像缓存
User Profile Cache
提供用户画像的智能缓存，提升个性化响应速度
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field

from app.core import logger, settings
from .cache_strategies import LRUStrategy, CacheStrategy
from .cache_utils import CacheKeyBuilder, CacheMetrics


@dataclass
class UserProfile:
    """用户画像"""
    user_id: str
    nickname: str = ""
    avatar: str = ""
    preferences: Dict[str, Any] = field(default_factory=dict)
    personality: Dict[str, Any] = field(default_factory=dict)
    conversation_style: Dict[str, Any] = field(default_factory=dict)
    interests: List[str] = field(default_factory=list)
    mood_history: List[Dict[str, Any]] = field(default_factory=list)
    interaction_patterns: Dict[str, Any] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'nickname': self.nickname,
            'avatar': self.avatar,
            'preferences': self.preferences,
            'personality': self.personality,
            'conversation_style': self.conversation_style,
            'interests': self.interests,
            'mood_history': self.mood_history,
            'interaction_patterns': self.interaction_patterns,
            'last_updated': self.last_updated.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserProfile':
        """从字典创建"""
        if 'last_updated' in data and isinstance(data['last_updated'], str):
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data)
    
    def is_stale(self, max_age_seconds: int = 1800) -> bool:
        """检查画像是否过时"""
        age = (datetime.now() - self.last_updated).total_seconds()
        return age > max_age_seconds
    
    def update_interaction(self, interaction_data: Dict[str, Any]):
        """更新交互数据"""
        self.interaction_patterns.update(interaction_data)
        self.last_updated = datetime.now()
    
    def add_mood_entry(self, mood_data: Dict[str, Any]):
        """添加心情记录"""
        mood_entry = {
            **mood_data,
            'timestamp': datetime.now().isoformat()
        }
        self.mood_history.append(mood_entry)
        
        # 保持最近的记录
        max_mood_history = 50
        if len(self.mood_history) > max_mood_history:
            self.mood_history = self.mood_history[-max_mood_history:]
        
        self.last_updated = datetime.now()


@dataclass
class ProfileCacheEntry:
    """画像缓存条目"""
    profile: UserProfile
    cached_at: datetime
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    
    def access(self):
        """记录访问"""
        self.access_count += 1
        self.last_accessed = datetime.now()
    
    @property
    def age_seconds(self) -> float:
        """获取缓存年龄"""
        return (datetime.now() - self.cached_at).total_seconds()


class UserProfileCache:
    """用户画像缓存"""
    
    def __init__(self):
        """初始化用户画像缓存"""
        self.enabled = settings.ENABLE_USER_PROFILE_CACHE
        
        # 初始化缓存策略
        self.cache_strategy: CacheStrategy = LRUStrategy(
            max_size=settings.USER_PROFILE_CACHE_MAX_SIZE
        )
        
        # 用户画像缓存（内存中的快速访问）
        self.profile_cache: Dict[str, ProfileCacheEntry] = {}
        
        # 待更新的画像（批量更新优化）
        self.pending_updates: Dict[str, UserProfile] = {}
        
        # 性能监控
        self.metrics = CacheMetrics()
        
        # 后台任务
        self._refresh_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._batch_update_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 配置
        self.refresh_interval = settings.USER_PROFILE_REFRESH_INTERVAL
        self.max_age_seconds = settings.USER_PROFILE_CACHE_TTL
        
        logger.info(f"🔧 用户画像缓存初始化完成 (启用: {self.enabled})")
    
    async def start(self):
        """启动用户画像缓存"""
        if self._running:
            # 已经启动，跳过
            return
        
        if not self.enabled:
            logger.info("⏸️ 用户画像缓存已禁用")
            return
        
        logger.info("🚀 启动用户画像缓存服务...")
        
        self._running = True
        
        # 启动后台任务
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._batch_update_task = asyncio.create_task(self._batch_update_loop())
        
        logger.info("✅ 用户画像缓存服务启动完成")
    
    async def stop(self):
        """停止用户画像缓存"""
        logger.info("⏹️ 停止用户画像缓存服务...")
        
        self._running = False
        
        # 停止后台任务
        tasks = [self._refresh_task, self._cleanup_task, self._batch_update_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 处理待更新的画像
        if self.pending_updates:
            await self._flush_pending_updates()
        
        logger.info("✅ 用户画像缓存服务已停止")
    
    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        if not self.enabled:
            return None
        
        try:
            # 首先检查内存缓存
            if user_id in self.profile_cache:
                entry = self.profile_cache[user_id]
                
                # 检查是否过时
                if not entry.profile.is_stale(self.max_age_seconds):
                    entry.access()
                    self.metrics.record_hit()
                    logger.debug(f"🎯 用户画像缓存命中: {user_id}")
                    return entry.profile
                else:
                    # 过时的缓存，删除
                    del self.profile_cache[user_id]
            
            # 检查策略缓存
            cache_key = CacheKeyBuilder.build_user_profile_key(user_id)
            cached_data = self.cache_strategy.get(cache_key)
            
            if cached_data:
                profile = UserProfile.from_dict(cached_data)
                
                # 检查是否过时
                if not profile.is_stale(self.max_age_seconds):
                    # 添加到内存缓存
                    self.profile_cache[user_id] = ProfileCacheEntry(
                        profile=profile,
                        cached_at=datetime.now()
                    )
                    
                    self.metrics.record_hit()
                    logger.debug(f"🎯 用户画像策略缓存命中: {user_id}")
                    return profile
                else:
                    # 删除过时的缓存
                    self.cache_strategy.delete(cache_key)
            
            self.metrics.record_miss()
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取用户画像缓存失败 {user_id}: {e}")
            self.metrics.record_miss()
            return None
    
    async def set_profile(self, profile: UserProfile, immediate: bool = False) -> bool:
        """设置用户画像缓存"""
        if not self.enabled:
            return False
        
        try:
            user_id = profile.user_id
            
            # 更新内存缓存
            self.profile_cache[user_id] = ProfileCacheEntry(
                profile=profile,
                cached_at=datetime.now()
            )
            
            if immediate:
                # 立即更新策略缓存
                cache_key = CacheKeyBuilder.build_user_profile_key(user_id)
                success = self.cache_strategy.set(
                    cache_key,
                    profile.to_dict(),
                    ttl=self.max_age_seconds
                )
                
                if success:
                    self.metrics.record_set()
                    logger.debug(f"💾 用户画像立即缓存: {user_id}")
                
                return success
            else:
                # 添加到待更新队列（批量处理）
                self.pending_updates[user_id] = profile
                self.metrics.record_set()
                logger.debug(f"📝 用户画像加入待更新队列: {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"❌ 设置用户画像缓存失败 {profile.user_id}: {e}")
            return False
    
    async def update_profile_field(self, user_id: str, field: str, value: Any) -> bool:
        """更新用户画像字段"""
        try:
            # 获取当前画像
            profile = await self.get_profile(user_id)
            if not profile:
                # 创建新画像
                profile = UserProfile(user_id=user_id)
            
            # 更新字段
            if hasattr(profile, field):
                setattr(profile, field, value)
                profile.last_updated = datetime.now()
                
                # 更新缓存
                return await self.set_profile(profile)
            else:
                # 更新元数据
                profile.metadata[field] = value
                profile.last_updated = datetime.now()
                return await self.set_profile(profile)
                
        except Exception as e:
            logger.error(f"❌ 更新用户画像字段失败 {user_id}.{field}: {e}")
            return False
    
    async def add_interaction(self, user_id: str, interaction_data: Dict[str, Any]) -> bool:
        """添加用户交互数据"""
        try:
            profile = await self.get_profile(user_id)
            if not profile:
                profile = UserProfile(user_id=user_id)
            
            profile.update_interaction(interaction_data)
            return await self.set_profile(profile)
            
        except Exception as e:
            logger.error(f"❌ 添加用户交互数据失败 {user_id}: {e}")
            return False
    
    async def add_mood_entry(self, user_id: str, mood_data: Dict[str, Any]) -> bool:
        """添加用户心情记录"""
        try:
            profile = await self.get_profile(user_id)
            if not profile:
                profile = UserProfile(user_id=user_id)
            
            profile.add_mood_entry(mood_data)
            return await self.set_profile(profile)
            
        except Exception as e:
            logger.error(f"❌ 添加用户心情记录失败 {user_id}: {e}")
            return False
    
    async def invalidate_profile(self, user_id: str) -> bool:
        """失效用户画像缓存"""
        try:
            # 从内存缓存删除
            if user_id in self.profile_cache:
                del self.profile_cache[user_id]
            
            # 从待更新队列删除
            if user_id in self.pending_updates:
                del self.pending_updates[user_id]
            
            # 从策略缓存删除
            cache_key = CacheKeyBuilder.build_user_profile_key(user_id)
            success = self.cache_strategy.delete(cache_key)
            
            if success:
                logger.info(f"🗑️ 已失效用户画像缓存: {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 失效用户画像缓存失败 {user_id}: {e}")
            return False
    
    async def get_cached_users(self) -> List[str]:
        """获取已缓存的用户列表"""
        try:
            cached_users = set()
            
            # 内存缓存中的用户
            cached_users.update(self.profile_cache.keys())
            
            # 策略缓存中的用户
            for key in self.cache_strategy.keys():
                if key.startswith("profile:"):
                    user_id = key.split(":")[1]
                    cached_users.add(user_id)
            
            return list(cached_users)
            
        except Exception as e:
            logger.error(f"❌ 获取缓存用户列表失败: {e}")
            return []
    
    async def _refresh_loop(self):
        """刷新循环"""
        logger.info("🔄 启动用户画像刷新循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.refresh_interval)
                await self._refresh_stale_profiles()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 用户画像刷新循环异常: {e}", exc_info=True)
    
    async def _refresh_stale_profiles(self):
        """刷新过时的画像"""
        try:
            stale_users = []
            
            # 检查内存缓存中的过时画像
            for user_id, entry in list(self.profile_cache.items()):
                if entry.profile.is_stale(self.max_age_seconds):
                    stale_users.append(user_id)
            
            if stale_users:
                logger.debug(f"🔄 发现 {len(stale_users)} 个过时的用户画像")
                
                # 这里可以添加从数据库重新加载画像的逻辑
                # 暂时只是标记为需要刷新
                for user_id in stale_users:
                    if user_id in self.profile_cache:
                        del self.profile_cache[user_id]
                        
        except Exception as e:
            logger.error(f"❌ 刷新过时画像失败: {e}")
    
    async def _cleanup_loop(self):
        """清理循环"""
        logger.info("🧹 启动用户画像缓存清理循环")
        
        while self._running:
            try:
                await asyncio.sleep(settings.CACHE_CLEANUP_INTERVAL)
                await self._perform_cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 用户画像缓存清理循环异常: {e}", exc_info=True)
    
    async def _perform_cleanup(self):
        """执行清理"""
        try:
            # 清理策略缓存中的过期条目
            expired_count = self.cache_strategy.cleanup_expired()
            
            # 清理内存缓存中的过时条目
            stale_memory_count = 0
            for user_id in list(self.profile_cache.keys()):
                entry = self.profile_cache[user_id]
                if entry.profile.is_stale(self.max_age_seconds):
                    del self.profile_cache[user_id]
                    stale_memory_count += 1
            
            if expired_count > 0 or stale_memory_count > 0:
                logger.debug(f"🧹 用户画像缓存清理: 策略缓存={expired_count}, 内存缓存={stale_memory_count}")
                
        except Exception as e:
            logger.error(f"❌ 用户画像缓存清理失败: {e}")
    
    async def _batch_update_loop(self):
        """批量更新循环"""
        logger.info("📦 启动用户画像批量更新循环")
        
        while self._running:
            try:
                await asyncio.sleep(30)  # 每30秒批量更新一次
                await self._flush_pending_updates()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 用户画像批量更新循环异常: {e}", exc_info=True)
    
    async def _flush_pending_updates(self):
        """刷新待更新的画像"""
        try:
            if not self.pending_updates:
                return
            
            update_count = 0
            updates_to_process = dict(self.pending_updates)
            self.pending_updates.clear()
            
            for user_id, profile in updates_to_process.items():
                try:
                    cache_key = CacheKeyBuilder.build_user_profile_key(user_id)
                    success = self.cache_strategy.set(
                        cache_key,
                        profile.to_dict(),
                        ttl=self.max_age_seconds
                    )
                    
                    if success:
                        update_count += 1
                        
                except Exception as e:
                    logger.error(f"❌ 批量更新用户画像失败 {user_id}: {e}")
            
            if update_count > 0:
                logger.debug(f"📦 批量更新了 {update_count} 个用户画像")
                
        except Exception as e:
            logger.error(f"❌ 刷新待更新画像失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        cache_stats = self.cache_strategy.get_stats()
        
        return {
            'enabled': self.enabled,
            'memory_cache_size': len(self.profile_cache),
            'strategy_cache_size': self.cache_strategy.size(),
            'max_size': settings.USER_PROFILE_CACHE_MAX_SIZE,
            'pending_updates': len(self.pending_updates),
            'refresh_interval': self.refresh_interval,
            'max_age_seconds': self.max_age_seconds,
            **cache_stats.to_dict()
        }
    
    def clear_cache(self):
        """清空缓存"""
        self.profile_cache.clear()
        self.pending_updates.clear()
        self.cache_strategy.clear()
        self.metrics.reset_stats()
        logger.info("🗑️ 用户画像缓存已清空")


# 全局用户画像缓存实例
_user_profile_cache: Optional[UserProfileCache] = None


def get_user_profile_cache() -> UserProfileCache:
    """获取用户画像缓存实例"""
    global _user_profile_cache
    if _user_profile_cache is None:
        _user_profile_cache = UserProfileCache()
    return _user_profile_cache


async def initialize_user_profile_cache():
    """初始化用户画像缓存"""
    cache = get_user_profile_cache()
    await cache.start()
    return cache


async def shutdown_user_profile_cache():
    """关闭用户画像缓存"""
    global _user_profile_cache
    if _user_profile_cache:
        await _user_profile_cache.stop()
        _user_profile_cache = None
