"""
缓存策略
Cache Strategies
实现不同的缓存淘汰和管理策略
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import OrderedDict
import heapq

from app.core import logger
from .cache_utils import CacheEntry, CacheStats


class CacheStrategy(ABC):
    """缓存策略基类"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: Dict[str, CacheEntry] = {}
        self.stats = CacheStats()
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        pass
    
    @abstractmethod
    def clear(self):
        """清空缓存"""
        pass
    
    @abstractmethod
    def evict(self) -> List[str]:
        """执行缓存淘汰"""
        pass
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return key in self.cache and not self.cache[key].is_expired
    
    def size(self) -> int:
        """获取缓存大小"""
        return len(self.cache)
    
    def keys(self) -> List[str]:
        """获取所有键"""
        return list(self.cache.keys())
    
    def cleanup_expired(self) -> int:
        """清理过期条目"""
        expired_keys = []
        for key, entry in self.cache.items():
            if entry.is_expired:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        return len(expired_keys)
    
    def get_stats(self) -> CacheStats:
        """获取统计信息"""
        self.stats.total_size = len(self.cache)
        return self.stats


class LRUStrategy(CacheStrategy):
    """LRU (Least Recently Used) 缓存策略"""
    
    def __init__(self, max_size: int = 1000):
        super().__init__(max_size)
        self.access_order = OrderedDict()  # 维护访问顺序
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        self.stats.total_requests += 1
        
        if key not in self.cache:
            self.stats.cache_misses += 1
            return None
        
        entry = self.cache[key]
        
        # 检查是否过期
        if entry.is_expired:
            del self.cache[key]
            if key in self.access_order:
                del self.access_order[key]
            self.stats.cache_misses += 1
            return None
        
        # 更新访问信息
        entry.access()
        self.access_order.move_to_end(key)
        
        self.stats.cache_hits += 1
        return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            # 计算过期时间
            expires_at = None
            if ttl is not None:
                expires_at = datetime.now() + timedelta(seconds=ttl)
            
            # 如果键已存在，更新
            if key in self.cache:
                self.cache[key].value = value
                self.cache[key].expires_at = expires_at
                self.cache[key].created_at = datetime.now()
                self.access_order.move_to_end(key)
            else:
                # 检查是否需要淘汰
                if len(self.cache) >= self.max_size:
                    self.evict()
                
                # 创建新条目
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=datetime.now(),
                    expires_at=expires_at
                )
                
                self.cache[key] = entry
                self.access_order[key] = True
            
            self.stats.cache_sets += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ LRU缓存设置失败 {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        if key in self.cache:
            del self.cache[key]
            if key in self.access_order:
                del self.access_order[key]
            self.stats.cache_deletes += 1
            return True
        return False
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.access_order.clear()
        self.stats = CacheStats()
    
    def evict(self) -> List[str]:
        """执行LRU淘汰"""
        evicted_keys = []
        
        # 淘汰最少使用的条目
        while len(self.cache) >= self.max_size and self.access_order:
            lru_key = next(iter(self.access_order))
            del self.cache[lru_key]
            del self.access_order[lru_key]
            evicted_keys.append(lru_key)
            self.stats.cache_evictions += 1
        
        return evicted_keys


class TTLStrategy(CacheStrategy):
    """TTL (Time To Live) 缓存策略"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        super().__init__(max_size)
        self.default_ttl = default_ttl
        self.expiry_heap = []  # 最小堆，按过期时间排序
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        self.stats.total_requests += 1
        
        if key not in self.cache:
            self.stats.cache_misses += 1
            return None
        
        entry = self.cache[key]
        
        # 检查是否过期
        if entry.is_expired:
            del self.cache[key]
            self.stats.cache_misses += 1
            return None
        
        # 更新访问信息
        entry.access()
        
        self.stats.cache_hits += 1
        return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            # 使用默认TTL或指定TTL
            actual_ttl = ttl if ttl is not None else self.default_ttl
            expires_at = datetime.now() + timedelta(seconds=actual_ttl)
            
            # 如果键已存在，更新
            if key in self.cache:
                self.cache[key].value = value
                self.cache[key].expires_at = expires_at
                self.cache[key].created_at = datetime.now()
            else:
                # 检查是否需要淘汰
                if len(self.cache) >= self.max_size:
                    self.evict()
                
                # 创建新条目
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=datetime.now(),
                    expires_at=expires_at
                )
                
                self.cache[key] = entry
                
                # 添加到过期堆
                heapq.heappush(self.expiry_heap, (expires_at.timestamp(), key))
            
            self.stats.cache_sets += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ TTL缓存设置失败 {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        if key in self.cache:
            del self.cache[key]
            self.stats.cache_deletes += 1
            return True
        return False
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.expiry_heap.clear()
        self.stats = CacheStats()
    
    def evict(self) -> List[str]:
        """执行TTL淘汰"""
        evicted_keys = []
        current_time = time.time()
        
        # 清理过期的条目
        while self.expiry_heap:
            expire_time, key = self.expiry_heap[0]
            if expire_time <= current_time:
                heapq.heappop(self.expiry_heap)
                if key in self.cache:
                    del self.cache[key]
                    evicted_keys.append(key)
                    self.stats.cache_evictions += 1
            else:
                break
        
        # 如果还是超过大小限制，随机删除一些
        while len(self.cache) >= self.max_size:
            key = next(iter(self.cache))
            del self.cache[key]
            evicted_keys.append(key)
            self.stats.cache_evictions += 1
        
        return evicted_keys
    
    def cleanup_expired(self) -> int:
        """清理过期条目"""
        evicted = self.evict()
        return len(evicted)


class LFUStrategy(CacheStrategy):
    """LFU (Least Frequently Used) 缓存策略"""
    
    def __init__(self, max_size: int = 1000):
        super().__init__(max_size)
        self.frequency = {}  # 访问频率计数
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        self.stats.total_requests += 1
        
        if key not in self.cache:
            self.stats.cache_misses += 1
            return None
        
        entry = self.cache[key]
        
        # 检查是否过期
        if entry.is_expired:
            del self.cache[key]
            if key in self.frequency:
                del self.frequency[key]
            self.stats.cache_misses += 1
            return None
        
        # 更新访问信息和频率
        entry.access()
        self.frequency[key] = self.frequency.get(key, 0) + 1
        
        self.stats.cache_hits += 1
        return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            # 计算过期时间
            expires_at = None
            if ttl is not None:
                expires_at = datetime.now() + timedelta(seconds=ttl)
            
            # 如果键已存在，更新
            if key in self.cache:
                self.cache[key].value = value
                self.cache[key].expires_at = expires_at
                self.cache[key].created_at = datetime.now()
            else:
                # 检查是否需要淘汰
                if len(self.cache) >= self.max_size:
                    self.evict()
                
                # 创建新条目
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=datetime.now(),
                    expires_at=expires_at
                )
                
                self.cache[key] = entry
                self.frequency[key] = 0
            
            self.stats.cache_sets += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ LFU缓存设置失败 {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        if key in self.cache:
            del self.cache[key]
            if key in self.frequency:
                del self.frequency[key]
            self.stats.cache_deletes += 1
            return True
        return False
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.frequency.clear()
        self.stats = CacheStats()
    
    def evict(self) -> List[str]:
        """执行LFU淘汰"""
        evicted_keys = []
        
        # 找到频率最低的键
        while len(self.cache) >= self.max_size and self.frequency:
            min_freq_key = min(self.frequency.keys(), key=lambda k: self.frequency[k])
            del self.cache[min_freq_key]
            del self.frequency[min_freq_key]
            evicted_keys.append(min_freq_key)
            self.stats.cache_evictions += 1
        
        return evicted_keys


class HybridStrategy(CacheStrategy):
    """混合缓存策略（LRU + TTL）"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        super().__init__(max_size)
        self.default_ttl = default_ttl
        self.access_order = OrderedDict()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        self.stats.total_requests += 1
        
        if key not in self.cache:
            self.stats.cache_misses += 1
            return None
        
        entry = self.cache[key]
        
        # 检查是否过期
        if entry.is_expired:
            del self.cache[key]
            if key in self.access_order:
                del self.access_order[key]
            self.stats.cache_misses += 1
            return None
        
        # 更新访问信息
        entry.access()
        self.access_order.move_to_end(key)
        
        self.stats.cache_hits += 1
        return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            # 使用默认TTL或指定TTL
            actual_ttl = ttl if ttl is not None else self.default_ttl
            expires_at = datetime.now() + timedelta(seconds=actual_ttl)
            
            # 如果键已存在，更新
            if key in self.cache:
                self.cache[key].value = value
                self.cache[key].expires_at = expires_at
                self.cache[key].created_at = datetime.now()
                self.access_order.move_to_end(key)
            else:
                # 检查是否需要淘汰
                if len(self.cache) >= self.max_size:
                    self.evict()
                
                # 创建新条目
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=datetime.now(),
                    expires_at=expires_at
                )
                
                self.cache[key] = entry
                self.access_order[key] = True
            
            self.stats.cache_sets += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ 混合缓存设置失败 {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        if key in self.cache:
            del self.cache[key]
            if key in self.access_order:
                del self.access_order[key]
            self.stats.cache_deletes += 1
            return True
        return False
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.access_order.clear()
        self.stats = CacheStats()
    
    def evict(self) -> List[str]:
        """执行混合淘汰（优先淘汰过期的，然后是LRU）"""
        evicted_keys = []
        
        # 首先清理过期的条目
        expired_keys = []
        for key, entry in self.cache.items():
            if entry.is_expired:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
            if key in self.access_order:
                del self.access_order[key]
            evicted_keys.append(key)
            self.stats.cache_evictions += 1
        
        # 如果还需要更多空间，使用LRU淘汰
        while len(self.cache) >= self.max_size and self.access_order:
            lru_key = next(iter(self.access_order))
            del self.cache[lru_key]
            del self.access_order[lru_key]
            evicted_keys.append(lru_key)
            self.stats.cache_evictions += 1
        
        return evicted_keys
