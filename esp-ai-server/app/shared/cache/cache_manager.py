"""
缓存管理器
Cache Manager
统一管理所有类型的缓存，提供统一的接口和监控
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass

from app.core import logger, settings
from .llm_cache import LLMCache, get_llm_cache, LLMRequest, LLMResponse
from .user_profile_cache import UserProfileCache, get_user_profile_cache, UserProfile
from .cache_monitor import CacheMonitor, get_cache_monitor


@dataclass
class CacheManagerStats:
    """缓存管理器统计"""
    total_caches: int = 0
    enabled_caches: int = 0
    total_size: int = 0
    total_hits: int = 0
    total_misses: int = 0
    total_sets: int = 0
    uptime_seconds: float = 0.0
    
    @property
    def hit_rate(self) -> float:
        """总体命中率"""
        total_requests = self.total_hits + self.total_misses
        if total_requests == 0:
            return 0.0
        return self.total_hits / total_requests
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_caches': self.total_caches,
            'enabled_caches': self.enabled_caches,
            'total_size': self.total_size,
            'total_hits': self.total_hits,
            'total_misses': self.total_misses,
            'total_sets': self.total_sets,
            'uptime_seconds': self.uptime_seconds,
            'hit_rate': self.hit_rate
        }


class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        """初始化缓存管理器"""
        self.enabled = settings.ENABLE_CACHE
        self.start_time = datetime.now()
        self._running = False  # 添加运行状态标志
        
        # 初始化各种缓存
        self.llm_cache = get_llm_cache()
        self.user_profile_cache = get_user_profile_cache()
        self.cache_monitor = get_cache_monitor()
        
        # 缓存注册表
        self.caches = {
            'llm': self.llm_cache,
            'user_profile': self.user_profile_cache
        }
        
        logger.info(f"🔧 缓存管理器初始化完成 (启用: {self.enabled})")
    
    async def start(self):
        """启动缓存管理器"""
        if self._running:
            # 已经启动，跳过
            return
        
        if not self.enabled:
            logger.info("⏸️ 缓存管理器已禁用")
            return
        
        logger.info("🚀 启动缓存管理器...")
        
        try:
            # 启动各种缓存
            await self.llm_cache.start()
            await self.user_profile_cache.start()
            await self.cache_monitor.start()
            
            self._running = True
            logger.info("✅ 缓存管理器启动完成")
            
        except Exception as e:
            logger.error(f"❌ 缓存管理器启动失败: {e}", exc_info=True)
    
    async def stop(self):
        """停止缓存管理器"""
        if not self._running:
            # 已经停止，跳过
            return
        
        logger.info("⏹️ 停止缓存管理器...")
        
        try:
            # 停止各种缓存
            await self.cache_monitor.stop()
            await self.user_profile_cache.stop()
            await self.llm_cache.stop()
            
            self._running = False
            logger.info("✅ 缓存管理器已停止")
            
        except Exception as e:
            logger.error(f"❌ 停止缓存管理器失败: {e}", exc_info=True)
    
    # ==================== LLM缓存接口 ====================
    
    async def get_llm_response(self, request: LLMRequest) -> Optional[LLMResponse]:
        """获取LLM响应缓存"""
        if not self.enabled:
            return None
        
        try:
            return await self.llm_cache.get(request)
        except Exception as e:
            logger.error(f"❌ 获取LLM缓存失败: {e}")
            return None
    
    async def cache_llm_response(self, request: LLMRequest, response: LLMResponse) -> bool:
        """缓存LLM响应"""
        if not self.enabled:
            return False
        
        try:
            return await self.llm_cache.set(request, response)
        except Exception as e:
            logger.error(f"❌ 缓存LLM响应失败: {e}")
            return False
    
    async def invalidate_llm_cache_by_user(self, user_id: str) -> int:
        """按用户失效LLM缓存"""
        if not self.enabled:
            return 0
        
        try:
            return await self.llm_cache.invalidate_user_cache(user_id)
        except Exception as e:
            logger.error(f"❌ 失效用户LLM缓存失败 {user_id}: {e}")
            return 0
    
    async def invalidate_llm_cache_by_pattern(self, pattern: str) -> int:
        """按模式失效LLM缓存"""
        if not self.enabled:
            return 0
        
        try:
            return await self.llm_cache.invalidate_pattern(pattern)
        except Exception as e:
            logger.error(f"❌ 失效模式LLM缓存失败 {pattern}: {e}")
            return 0
    
    # ==================== 用户画像缓存接口 ====================
    
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像缓存"""
        if not self.enabled:
            return None
        
        try:
            return await self.user_profile_cache.get_profile(user_id)
        except Exception as e:
            logger.error(f"❌ 获取用户画像缓存失败 {user_id}: {e}")
            return None
    
    async def cache_user_profile(self, profile: UserProfile, immediate: bool = False) -> bool:
        """缓存用户画像"""
        if not self.enabled:
            return False
        
        try:
            return await self.user_profile_cache.set_profile(profile, immediate)
        except Exception as e:
            logger.error(f"❌ 缓存用户画像失败 {profile.user_id}: {e}")
            return False
    
    async def update_user_profile_field(self, user_id: str, field: str, value: Any) -> bool:
        """更新用户画像字段"""
        if not self.enabled:
            return False
        
        try:
            return await self.user_profile_cache.update_profile_field(user_id, field, value)
        except Exception as e:
            logger.error(f"❌ 更新用户画像字段失败 {user_id}.{field}: {e}")
            return False
    
    async def add_user_interaction(self, user_id: str, interaction_data: Dict[str, Any]) -> bool:
        """添加用户交互数据"""
        if not self.enabled:
            return False
        
        try:
            return await self.user_profile_cache.add_interaction(user_id, interaction_data)
        except Exception as e:
            logger.error(f"❌ 添加用户交互数据失败 {user_id}: {e}")
            return False
    
    async def add_user_mood_entry(self, user_id: str, mood_data: Dict[str, Any]) -> bool:
        """添加用户心情记录"""
        if not self.enabled:
            return False
        
        try:
            return await self.user_profile_cache.add_mood_entry(user_id, mood_data)
        except Exception as e:
            logger.error(f"❌ 添加用户心情记录失败 {user_id}: {e}")
            return False
    
    async def invalidate_user_profile(self, user_id: str) -> bool:
        """失效用户画像缓存"""
        if not self.enabled:
            return False
        
        try:
            return await self.user_profile_cache.invalidate_profile(user_id)
        except Exception as e:
            logger.error(f"❌ 失效用户画像缓存失败 {user_id}: {e}")
            return False
    
    # ==================== 统一缓存操作 ====================
    
    async def invalidate_user_all_caches(self, user_id: str) -> Dict[str, int]:
        """失效用户的所有缓存"""
        results = {}
        
        if not self.enabled:
            return results
        
        try:
            # 失效LLM缓存
            llm_count = await self.invalidate_llm_cache_by_user(user_id)
            results['llm_cache'] = llm_count
            
            # 失效用户画像缓存
            profile_success = await self.invalidate_user_profile(user_id)
            results['profile_cache'] = 1 if profile_success else 0
            
            total_invalidated = sum(results.values())
            if total_invalidated > 0:
                logger.info(f"🗑️ 已失效用户 {user_id} 的所有缓存: {results}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ 失效用户所有缓存失败 {user_id}: {e}")
            return results
    
    async def clear_all_caches(self):
        """清空所有缓存"""
        if not self.enabled:
            return
        
        try:
            self.llm_cache.clear_cache()
            self.user_profile_cache.clear_cache()
            
            logger.info("🗑️ 已清空所有缓存")
            
        except Exception as e:
            logger.error(f"❌ 清空所有缓存失败: {e}")
    
    async def get_cached_users(self) -> List[str]:
        """获取所有已缓存的用户"""
        try:
            cached_users = set()
            
            # 从用户画像缓存获取
            profile_users = await self.user_profile_cache.get_cached_users()
            cached_users.update(profile_users)
            
            return list(cached_users)
            
        except Exception as e:
            logger.error(f"❌ 获取缓存用户列表失败: {e}")
            return []
    
    # ==================== 统计和监控 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        try:
            stats = CacheManagerStats()
            
            # 收集各缓存的统计
            cache_stats = {}
            
            # LLM缓存统计
            llm_stats = self.llm_cache.get_stats()
            cache_stats['llm'] = llm_stats
            
            if llm_stats.get('enabled', False):
                stats.enabled_caches += 1
                stats.total_hits += llm_stats.get('cache_hits', 0)
                stats.total_misses += llm_stats.get('cache_misses', 0)
                stats.total_sets += llm_stats.get('cache_sets', 0)
            
            # 用户画像缓存统计
            profile_stats = self.user_profile_cache.get_stats()
            cache_stats['user_profile'] = profile_stats
            
            if profile_stats.get('enabled', False):
                stats.enabled_caches += 1
                stats.total_hits += profile_stats.get('cache_hits', 0)
                stats.total_misses += profile_stats.get('cache_misses', 0)
                stats.total_sets += profile_stats.get('cache_sets', 0)
            
            # 总体统计
            stats.total_caches = len(self.caches)
            stats.uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            
            return {
                'manager': stats.to_dict(),
                'caches': cache_stats,
                'enabled': self.enabled
            }
            
        except Exception as e:
            logger.error(f"❌ 获取缓存统计失败: {e}")
            return {'enabled': self.enabled, 'error': str(e)}
    
    def get_cache_health(self) -> Dict[str, Any]:
        """获取缓存健康状态"""
        try:
            health = {
                'overall_status': 'healthy',
                'caches': {},
                'issues': []
            }
            
            # 检查各缓存的健康状态
            for cache_name, cache in self.caches.items():
                cache_health = {
                    'status': 'healthy',
                    'enabled': getattr(cache, 'enabled', False),
                    'running': getattr(cache, '_running', False)
                }
                
                # 检查缓存大小
                if hasattr(cache, 'get_stats'):
                    stats = cache.get_stats()
                    cache_size = stats.get('cache_size', 0)
                    max_size = stats.get('max_size', 1000)
                    
                    if cache_size > max_size * 0.9:  # 90%阈值
                        cache_health['status'] = 'warning'
                        health['issues'].append(f"{cache_name}缓存接近满载")
                    
                    cache_health['size'] = cache_size
                    cache_health['max_size'] = max_size
                    cache_health['utilization'] = cache_size / max_size if max_size > 0 else 0
                
                health['caches'][cache_name] = cache_health
            
            # 确定总体状态
            if any(c['status'] == 'warning' for c in health['caches'].values()):
                health['overall_status'] = 'warning'
            
            return health
            
        except Exception as e:
            logger.error(f"❌ 获取缓存健康状态失败: {e}")
            return {
                'overall_status': 'error',
                'error': str(e)
            }


# 全局缓存管理器实例
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取缓存管理器实例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


async def initialize_cache_manager():
    """初始化缓存管理器"""
    manager = get_cache_manager()
    await manager.start()
    return manager


async def shutdown_cache_manager():
    """关闭缓存管理器"""
    global _cache_manager
    if _cache_manager:
        await _cache_manager.stop()
        _cache_manager = None
