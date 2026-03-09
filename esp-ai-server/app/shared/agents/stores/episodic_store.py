"""
情节记忆存储实现
基于文件的向量检索存储，支持相似度搜索和过期清理
"""

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict, Any
from collections import defaultdict

from app.core import logger
from app.shared.agents.base_agent import BaseAgent, MemoryType, MemoryRecord, RetentionPolicy


class FileEpisodicStore:
    """基于文件的情节记忆存储"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "episodic"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"初始化情节记忆存储: {self.data_dir}")
    
    def _get_user_file(self, user_id: str) -> Path:
        """获取用户的情节记忆文件路径"""
        return self.data_dir / f"{user_id}_episodic.json"
    
    def upsert(self, records: List[MemoryRecord]) -> None:
        """插入或更新记忆记录"""
        if not records:
            return
        
        # 按用户分组处理
        user_records = defaultdict(list)
        for record in records:
            if record.type == MemoryType.EPISODIC_MEMORY:
                user_records[record.user_id].append(record)
        
        # 为每个用户更新文件
        for user_id, user_memories in user_records.items():
            self._upsert_user_memories(user_id, user_memories)
    
    def _upsert_user_memories(self, user_id: str, new_memories: List[MemoryRecord]) -> None:
        """为单个用户更新情节记忆"""
        file_path = self._get_user_file(user_id)
        
        # 加载现有记忆
        existing_memories = []
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_memories = [
                        self._dict_to_record(item) 
                        for item in data.get("memories", [])
                    ]
            except Exception as e:
                logger.error(f"加载情节记忆失败 {user_id}: {e}")
        
        # 合并记忆（简单追加，实际项目中应该去重）
        all_memories = existing_memories + new_memories
        
        # 按时间排序，保留最新的记忆
        all_memories.sort(key=lambda m: datetime.fromisoformat(m.timestamp), reverse=True)
        
        # 限制记忆数量（工程化考虑）
        max_memories = 1000  # 可配置
        if len(all_memories) > max_memories:
            all_memories = all_memories[:max_memories]
        
        # 保存到文件
        self._save_user_memories(user_id, all_memories)
        
        logger.debug(f"更新情节记忆: {user_id} -> +{len(new_memories)} 条，总计 {len(all_memories)} 条")
    
    def search(self, user_id: str, query_vec: List[float], top_k: int) -> List[Tuple[MemoryRecord, float]]:
        """向量相似度搜索记忆"""
        if not query_vec:
            return []
            
        file_path = self._get_user_file(user_id)
        if not file_path.exists():
            return []
        
        try:
            # 加载用户记忆
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                memories = [
                    self._dict_to_record(item) 
                    for item in data.get("memories", [])
                ]
            
            # 计算相似度
            results = []
            for memory in memories:
                if hasattr(memory, 'embedding') and memory.embedding:
                    similarity = self._cosine_similarity(query_vec, memory.embedding)
                    if similarity > 0.1:  # 最小相似度阈值
                        results.append((memory, similarity))
            
            # 按相似度排序并返回 top_k
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"搜索情节记忆失败 {user_id}: {e}")
            return []
    
    def delete_expired(self, now: datetime, policy: RetentionPolicy) -> int:
        """删除过期记忆"""
        if not policy.ttl_hours:
            return 0
        
        deleted_count = 0
        cutoff_time = now - timedelta(hours=policy.ttl_hours)
        
        for file_path in self.data_dir.glob("*_episodic.json"):
            try:
                deleted_count += self._clean_expired_file(file_path, cutoff_time, now)
            except Exception as e:
                logger.error(f"清理过期记忆失败 {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"清理过期情节记忆: {deleted_count} 条")
        
        return deleted_count
    
    def _clean_expired_file(self, file_path: Path, cutoff_time: datetime, now: datetime) -> int:
        """清理单个文件中的过期记忆"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        memories = [self._dict_to_record(item) for item in data.get("memories", [])]
        original_count = len(memories)
        
        # 过滤过期记忆
        valid_memories = [m for m in memories if datetime.fromisoformat(m.timestamp) > cutoff_time]
        deleted_count = original_count - len(valid_memories)
        
        # 如果有记忆被删除，更新文件
        if deleted_count > 0:
            data["memories"] = [self._record_to_dict(m) for m in valid_memories]
            data["last_updated"] = now.isoformat()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        return deleted_count
    
    def _save_user_memories(self, user_id: str, memories: List[MemoryRecord]) -> None:
        """保存用户记忆到文件"""
        file_path = self._get_user_file(user_id)
        
        try:
            data = {
                "user_id": user_id,
                "last_updated": datetime.now().isoformat(),
                "memory_count": len(memories),
                "memories": [self._record_to_dict(m) for m in memories]
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存情节记忆失败 {user_id}: {e}")
            raise
    
    def _record_to_dict(self, record: MemoryRecord) -> Dict[str, Any]:
        """MemoryRecord 转字典"""
        return {
            "id": record.id,
            "user_id": record.user_id,
            "type": record.type.value,
            "content": record.content,
            "importance": record.importance,
            "timestamp": record.timestamp,
            "related_event": record.related_event,
            "event_date": record.event_date,
            "meta": record.meta or {},
            "embedding": getattr(record, 'embedding', [])
        }
    
    def _dict_to_record(self, data: Dict[str, Any]) -> MemoryRecord:
        """字典转 MemoryRecord"""
        from app.shared.agents.base_agent import make_memory
        
        record = make_memory(
            user_id=data["user_id"],
            type=MemoryType(data["type"]),
            content=data["content"],
            importance=data["importance"],
            related_event=data.get("related_event"),
            event_date=data.get("event_date"),
            meta=data.get("meta", {})
        )
        
        # 恢复额外属性
        record.id = data["id"]
        record.timestamp = data.get("timestamp", record.timestamp)
        record.embedding = data.get("embedding", [])
        
        return record
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        if not a or not b or len(a) != len(b):
            return 0.0
        
        try:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(y * y for y in b))
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            return dot / (norm_a * norm_b)
        except Exception:
            return 0.0
