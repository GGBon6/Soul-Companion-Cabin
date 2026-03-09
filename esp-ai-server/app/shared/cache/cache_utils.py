"""
缓存工具类
Cache Utilities
提供缓存相关的工具函数和辅助类
"""

import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum


class CacheLevel(Enum):
    """缓存级别"""
    MEMORY = "memory"      # 内存缓存
    REDIS = "redis"        # Redis缓存
    HYBRID = "hybrid"      # 混合缓存


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.last_accessed is None:
            self.last_accessed = self.created_at
    
    @property
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    @property
    def age_seconds(self) -> float:
        """获取缓存年龄（秒）"""
        return (datetime.now() - self.created_at).total_seconds()
    
    @property
    def ttl_seconds(self) -> Optional[float]:
        """获取剩余生存时间（秒）"""
        if self.expires_at is None:
            return None
        remaining = (self.expires_at - datetime.now()).total_seconds()
        return max(0, remaining)
    
    def access(self):
        """记录访问"""
        self.access_count += 1
        self.last_accessed = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'key': self.key,
            'value': self.value,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'access_count': self.access_count,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
            'metadata': self.metadata
        }


@dataclass
class CacheStats:
    """缓存统计"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_sets: int = 0
    cache_deletes: int = 0
    cache_evictions: int = 0
    total_size: int = 0
    memory_usage: int = 0
    
    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        if self.total_requests == 0:
            return 0.0
        return self.cache_hits / self.total_requests
    
    @property
    def miss_rate(self) -> float:
        """缓存未命中率"""
        return 1.0 - self.hit_rate
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_requests': self.total_requests,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_sets': self.cache_sets,
            'cache_deletes': self.cache_deletes,
            'cache_evictions': self.cache_evictions,
            'total_size': self.total_size,
            'memory_usage': self.memory_usage,
            'hit_rate': self.hit_rate,
            'miss_rate': self.miss_rate
        }


class CacheKeyBuilder:
    """缓存键构建器"""
    
    @staticmethod
    def build_llm_key(prompt: str, model: str = "", temperature: float = 0.7, 
                     max_tokens: int = 1000, **kwargs) -> str:
        """构建LLM缓存键"""
        # 创建包含所有参数的字典
        params = {
            'prompt': prompt,
            'model': model,
            'temperature': temperature,
            'max_tokens': max_tokens,
            **kwargs
        }
        
        # 排序并序列化参数
        sorted_params = json.dumps(params, sort_keys=True, ensure_ascii=False)
        
        # 生成哈希
        hash_obj = hashlib.sha256(sorted_params.encode('utf-8'))
        return f"llm:{hash_obj.hexdigest()[:16]}"
    
    @staticmethod
    def build_user_profile_key(user_id: str, profile_type: str = "full") -> str:
        """构建用户画像缓存键"""
        return f"profile:{user_id}:{profile_type}"
    
    @staticmethod
    def build_conversation_key(user_id: str, conversation_id: str = "") -> str:
        """构建对话缓存键"""
        if conversation_id:
            return f"conv:{user_id}:{conversation_id}"
        return f"conv:{user_id}"
    
    @staticmethod
    def build_memory_key(user_id: str, memory_type: str, query_hash: str = "") -> str:
        """构建记忆缓存键"""
        if query_hash:
            return f"memory:{user_id}:{memory_type}:{query_hash}"
        return f"memory:{user_id}:{memory_type}"


class CacheSerializer:
    """缓存序列化器"""
    
    @staticmethod
    def serialize(value: Any) -> str:
        """序列化值"""
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as e:
            raise ValueError(f"无法序列化值: {e}")
    
    @staticmethod
    def deserialize(data: str) -> Any:
        """反序列化值"""
        try:
            return json.loads(data)
        except (TypeError, ValueError) as e:
            raise ValueError(f"无法反序列化数据: {e}")


class SimilarityCalculator:
    """相似度计算器"""
    
    @staticmethod
    def text_similarity(text1: str, text2: str) -> float:
        """计算文本相似度（简单的Jaccard相似度）"""
        if not text1 or not text2:
            return 0.0
        
        # 转换为小写并分词
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        # 计算Jaccard相似度
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    @staticmethod
    def prompt_similarity(prompt1: str, prompt2: str, threshold: float = 0.8) -> bool:
        """判断两个提示是否相似"""
        similarity = SimilarityCalculator.text_similarity(prompt1, prompt2)
        return similarity >= threshold


class CacheMetrics:
    """缓存指标收集器"""
    
    def __init__(self):
        self.stats = CacheStats()
        self.start_time = datetime.now()
        self.last_reset = datetime.now()
    
    def record_hit(self):
        """记录缓存命中"""
        self.stats.total_requests += 1
        self.stats.cache_hits += 1
    
    def record_miss(self):
        """记录缓存未命中"""
        self.stats.total_requests += 1
        self.stats.cache_misses += 1
    
    def record_set(self):
        """记录缓存设置"""
        self.stats.cache_sets += 1
    
    def record_delete(self):
        """记录缓存删除"""
        self.stats.cache_deletes += 1
    
    def record_eviction(self):
        """记录缓存驱逐"""
        self.stats.cache_evictions += 1
    
    def update_size(self, size: int):
        """更新缓存大小"""
        self.stats.total_size = size
    
    def update_memory_usage(self, usage: int):
        """更新内存使用量"""
        self.stats.memory_usage = usage
    
    def get_stats(self) -> CacheStats:
        """获取统计信息"""
        return self.stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = CacheStats()
        self.last_reset = datetime.now()
    
    def get_uptime_seconds(self) -> float:
        """获取运行时间（秒）"""
        return (datetime.now() - self.start_time).total_seconds()


def calculate_cache_size(data: Any) -> int:
    """计算数据的缓存大小（字节）"""
    try:
        if isinstance(data, str):
            return len(data.encode('utf-8'))
        elif isinstance(data, (int, float)):
            return 8  # 假设8字节
        elif isinstance(data, dict):
            return len(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        elif isinstance(data, list):
            return len(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        else:
            return len(str(data).encode('utf-8'))
    except:
        return 0


def is_cache_key_valid(key: str) -> bool:
    """验证缓存键是否有效"""
    if not key or not isinstance(key, str):
        return False
    
    # 检查长度
    if len(key) > 250:  # Redis键长度限制
        return False
    
    # 检查字符
    invalid_chars = [' ', '\n', '\r', '\t']
    for char in invalid_chars:
        if char in key:
            return False
    
    return True


def normalize_cache_key(key: str) -> str:
    """规范化缓存键"""
    if not key:
        return ""
    
    # 替换无效字符
    key = key.replace(' ', '_')
    key = key.replace('\n', '')
    key = key.replace('\r', '')
    key = key.replace('\t', '_')
    
    # 限制长度
    if len(key) > 250:
        # 保留前缀和后缀，中间用哈希
        prefix = key[:100]
        suffix = key[-50:]
        middle_hash = hashlib.md5(key.encode('utf-8')).hexdigest()[:16]
        key = f"{prefix}_{middle_hash}_{suffix}"
    
    return key
