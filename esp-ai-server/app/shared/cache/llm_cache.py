"""
LLM响应缓存
LLM Response Cache
提供LLM响应的智能缓存，减少重复计算，提升响应速度
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from app.core import logger, settings
from .cache_strategies import HybridStrategy, CacheStrategy
from .cache_utils import CacheKeyBuilder, SimilarityCalculator, CacheMetrics


@dataclass
class LLMRequest:
    """LLM请求"""
    prompt: str
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 1000
    system_prompt: str = ""
    user_id: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_cache_key(self) -> str:
        """生成缓存键"""
        return CacheKeyBuilder.build_llm_key(
            prompt=self.prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            system_prompt=self.system_prompt,
            **self.metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'prompt': self.prompt,
            'model': self.model,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'system_prompt': self.system_prompt,
            'user_id': self.user_id,
            'metadata': self.metadata
        }


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    model: str = ""
    usage: Dict[str, Any] = None
    finish_reason: str = ""
    response_time: float = 0.0
    created_at: datetime = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.usage is None:
            self.usage = {}
        if self.metadata is None:
            self.metadata = {}
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'content': self.content,
            'model': self.model,
            'usage': self.usage,
            'finish_reason': self.finish_reason,
            'response_time': self.response_time,
            'created_at': self.created_at.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMResponse':
        """从字典创建"""
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


class LLMCache:
    """LLM响应缓存"""
    
    def __init__(self):
        """初始化LLM缓存"""
        self.enabled = settings.ENABLE_LLM_CACHE
        self.similarity_threshold = settings.LLM_CACHE_SIMILARITY_THRESHOLD
        
        # 初始化缓存策略
        self.cache_strategy: CacheStrategy = HybridStrategy(
            max_size=settings.LLM_CACHE_MAX_SIZE,
            default_ttl=settings.LLM_CACHE_TTL
        )
        
        # 相似性缓存（用于快速查找相似的提示）
        self.similarity_index: Dict[str, List[str]] = {}  # 提示哈希 -> 缓存键列表
        
        # 性能监控
        self.metrics = CacheMetrics()
        
        # 后台任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"🔧 LLM缓存初始化完成 (启用: {self.enabled})")
    
    async def start(self):
        """启动LLM缓存"""
        if self._running:
            # 已经启动，跳过
            return
        
        if not self.enabled:
            logger.info("⏸️ LLM缓存已禁用")
            return
        
        logger.info("🚀 启动LLM缓存服务...")
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("✅ LLM缓存服务启动完成")
    
    async def stop(self):
        """停止LLM缓存"""
        logger.info("⏹️ 停止LLM缓存服务...")
        
        self._running = False
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ LLM缓存服务已停止")
    
    async def get(self, request: LLMRequest) -> Optional[LLMResponse]:
        """获取缓存的LLM响应"""
        if not self.enabled:
            return None
        
        try:
            # 首先尝试精确匹配
            cache_key = request.to_cache_key()
            cached_data = self.cache_strategy.get(cache_key)
            
            if cached_data:
                self.metrics.record_hit()
                logger.debug(f"🎯 LLM缓存命中 (精确): {cache_key[:16]}...")
                return LLMResponse.from_dict(cached_data)
            
            # 如果启用相似性匹配，尝试找到相似的提示
            if self.similarity_threshold > 0:
                similar_response = await self._find_similar_response(request)
                if similar_response:
                    self.metrics.record_hit()
                    logger.debug(f"🎯 LLM缓存命中 (相似): {request.prompt[:50]}...")
                    return similar_response
            
            self.metrics.record_miss()
            return None
            
        except Exception as e:
            logger.error(f"❌ LLM缓存获取失败: {e}")
            self.metrics.record_miss()
            return None
    
    async def set(self, request: LLMRequest, response: LLMResponse) -> bool:
        """设置LLM响应缓存"""
        if not self.enabled:
            return False
        
        try:
            cache_key = request.to_cache_key()
            
            # 存储响应
            success = self.cache_strategy.set(
                cache_key, 
                response.to_dict(), 
                ttl=settings.LLM_CACHE_TTL
            )
            
            if success:
                # 更新相似性索引
                await self._update_similarity_index(request, cache_key)
                
                self.metrics.record_set()
                logger.debug(f"💾 LLM响应已缓存: {cache_key[:16]}...")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ LLM缓存设置失败: {e}")
            return False
    
    async def invalidate_user_cache(self, user_id: str):
        """失效用户相关的缓存"""
        try:
            invalidated_count = 0
            keys_to_remove = []
            
            # 查找用户相关的缓存键
            for key in self.cache_strategy.keys():
                try:
                    # 检查缓存条目的元数据
                    cached_data = self.cache_strategy.get(key)
                    if cached_data and isinstance(cached_data, dict):
                        metadata = cached_data.get('metadata', {})
                        if metadata.get('user_id') == user_id:
                            keys_to_remove.append(key)
                except:
                    continue
            
            # 删除相关缓存
            for key in keys_to_remove:
                if self.cache_strategy.delete(key):
                    invalidated_count += 1
            
            if invalidated_count > 0:
                logger.info(f"🗑️ 已失效用户 {user_id} 的 {invalidated_count} 个LLM缓存")
            
            return invalidated_count
            
        except Exception as e:
            logger.error(f"❌ 失效用户缓存失败 {user_id}: {e}")
            return 0
    
    async def invalidate_pattern(self, pattern: str):
        """根据模式失效缓存"""
        try:
            invalidated_count = 0
            keys_to_remove = []
            
            # 查找匹配模式的缓存键
            for key in self.cache_strategy.keys():
                if pattern in key:
                    keys_to_remove.append(key)
            
            # 删除匹配的缓存
            for key in keys_to_remove:
                if self.cache_strategy.delete(key):
                    invalidated_count += 1
            
            if invalidated_count > 0:
                logger.info(f"🗑️ 已失效模式 '{pattern}' 的 {invalidated_count} 个LLM缓存")
            
            return invalidated_count
            
        except Exception as e:
            logger.error(f"❌ 失效模式缓存失败 {pattern}: {e}")
            return 0
    
    async def _find_similar_response(self, request: LLMRequest) -> Optional[LLMResponse]:
        """查找相似的响应"""
        try:
            prompt_hash = self._get_prompt_hash(request.prompt)
            
            # 查找相似的提示
            if prompt_hash in self.similarity_index:
                for cache_key in self.similarity_index[prompt_hash]:
                    cached_data = self.cache_strategy.get(cache_key)
                    if cached_data:
                        # 检查相似度
                        cached_request_data = cached_data.get('metadata', {}).get('request', {})
                        cached_prompt = cached_request_data.get('prompt', '')
                        
                        if SimilarityCalculator.prompt_similarity(
                            request.prompt, 
                            cached_prompt, 
                            self.similarity_threshold
                        ):
                            return LLMResponse.from_dict(cached_data)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 查找相似响应失败: {e}")
            return None
    
    async def _update_similarity_index(self, request: LLMRequest, cache_key: str):
        """更新相似性索引"""
        try:
            prompt_hash = self._get_prompt_hash(request.prompt)
            
            if prompt_hash not in self.similarity_index:
                self.similarity_index[prompt_hash] = []
            
            if cache_key not in self.similarity_index[prompt_hash]:
                self.similarity_index[prompt_hash].append(cache_key)
            
            # 限制每个哈希的缓存键数量
            max_keys_per_hash = 10
            if len(self.similarity_index[prompt_hash]) > max_keys_per_hash:
                self.similarity_index[prompt_hash] = self.similarity_index[prompt_hash][-max_keys_per_hash:]
                
        except Exception as e:
            logger.error(f"❌ 更新相似性索引失败: {e}")
    
    def _get_prompt_hash(self, prompt: str) -> str:
        """获取提示的哈希（用于相似性索引）"""
        # 简化提示（去除标点、转小写、去重复空格）
        simplified = ' '.join(prompt.lower().split())
        return hashlib.md5(simplified.encode('utf-8')).hexdigest()[:8]
    
    async def _cleanup_loop(self):
        """清理循环"""
        logger.info("🧹 启动LLM缓存清理循环")
        
        while self._running:
            try:
                await asyncio.sleep(settings.CACHE_CLEANUP_INTERVAL)
                await self._perform_cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ LLM缓存清理循环异常: {e}", exc_info=True)
    
    async def _perform_cleanup(self):
        """执行清理"""
        try:
            # 清理过期条目
            expired_count = self.cache_strategy.cleanup_expired()
            
            # 清理相似性索引中的无效键
            cleaned_similarity_count = 0
            for prompt_hash, cache_keys in list(self.similarity_index.items()):
                valid_keys = []
                for cache_key in cache_keys:
                    if self.cache_strategy.exists(cache_key):
                        valid_keys.append(cache_key)
                    else:
                        cleaned_similarity_count += 1
                
                if valid_keys:
                    self.similarity_index[prompt_hash] = valid_keys
                else:
                    del self.similarity_index[prompt_hash]
            
            if expired_count > 0 or cleaned_similarity_count > 0:
                logger.debug(f"🧹 LLM缓存清理: 过期={expired_count}, 相似性索引={cleaned_similarity_count}")
                
        except Exception as e:
            logger.error(f"❌ LLM缓存清理失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        cache_stats = self.cache_strategy.get_stats()
        
        return {
            'enabled': self.enabled,
            'cache_size': self.cache_strategy.size(),
            'max_size': settings.LLM_CACHE_MAX_SIZE,
            'similarity_index_size': len(self.similarity_index),
            'similarity_threshold': self.similarity_threshold,
            'ttl_seconds': settings.LLM_CACHE_TTL,
            **cache_stats.to_dict()
        }
    
    def clear_cache(self):
        """清空缓存"""
        self.cache_strategy.clear()
        self.similarity_index.clear()
        self.metrics.reset_stats()
        logger.info("🗑️ LLM缓存已清空")


# 全局LLM缓存实例
_llm_cache: Optional[LLMCache] = None


def get_llm_cache() -> LLMCache:
    """获取LLM缓存实例"""
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMCache()
    return _llm_cache


async def initialize_llm_cache():
    """初始化LLM缓存"""
    cache = get_llm_cache()
    await cache.start()
    return cache


async def shutdown_llm_cache():
    """关闭LLM缓存"""
    global _llm_cache
    if _llm_cache:
        await _llm_cache.stop()
        _llm_cache = None
