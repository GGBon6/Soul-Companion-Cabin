"""
安全合规存储实现
风险监控和审计记录的存储
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

from app.core import logger
from app.shared.agents.base_agent import BaseAgent, MemoryType, MemoryRecord, RetentionPolicy


class FileSafetyStore:
    """基于文件的安全合规存储"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "safety"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"初始化安全合规存储: {self.data_dir}")
    
    def _get_user_file(self, user_id: str) -> Path:
        """获取用户安全记录文件路径"""
        return self.data_dir / f"{user_id}_safety.json"
    
    def append(self, user_id: str, rows: List[Dict[str, Any]]) -> None:
        """追加安全记录"""
        if not rows:
            return
            
        file_path = self._get_user_file(user_id)
        
        # 加载现有记录
        existing_records = []
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_records = data.get("records", [])
            except Exception as e:
                logger.error(f"加载安全记录失败 {user_id}: {e}")
        
        # 添加新记录
        for row in rows:
            # 确保有时间戳
            if "timestamp" not in row:
                row["timestamp"] = datetime.now().isoformat()
            elif isinstance(row["timestamp"], datetime):
                row["timestamp"] = row["timestamp"].isoformat()
            
            # 添加记录ID（用于去重和追踪）
            if "record_id" not in row:
                row["record_id"] = f"{user_id}_{len(existing_records)}_{datetime.now().timestamp()}"
            
            existing_records.append(row)
        
        # 按时间排序
        existing_records.sort(key=lambda r: r.get("timestamp", ""))
        
        # 限制记录数量（安全记录很重要，但也要考虑存储）
        max_records = 5000  # 可配置
        if len(existing_records) > max_records:
            # 保留最新的记录
            existing_records = existing_records[-max_records:]
        
        # 保存
        self._save_user_safety(user_id, existing_records)
        
        logger.debug(f"追加安全记录: {user_id} -> +{len(rows)} 条记录")
        
        # 如果有高风险记录，记录警告
        high_risk_count = sum(1 for row in rows if row.get("severity", 1) >= 3)
        if high_risk_count > 0:
            logger.warning(f"检测到高风险安全记录: {user_id} -> {high_risk_count} 条")
    
    def get_recent(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近安全记录"""
        file_path = self._get_user_file(user_id)
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                records = data.get("records", [])
            
            # 返回最近的记录（已按时间排序）
            return records[-limit:] if len(records) > limit else records
            
        except Exception as e:
            logger.error(f"获取安全记录失败 {user_id}: {e}")
            return []
    
    def get_risk_summary(self, user_id: str, days: int = 7) -> Dict[str, Any]:
        """获取风险摘要（工程化扩展功能）"""
        file_path = self._get_user_file(user_id)
        if not file_path.exists():
            return {"total": 0, "high_risk": 0, "medium_risk": 0, "low_risk": 0}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                records = data.get("records", [])
            
            # 过滤最近N天的记录
            cutoff = datetime.now() - timedelta(days=days)
            recent_records = []
            
            for record in records:
                try:
                    record_time = datetime.fromisoformat(record["timestamp"])
                    if record_time > cutoff:
                        recent_records.append(record)
                except Exception:
                    continue
            
            # 统计风险等级
            summary = {"total": len(recent_records), "high_risk": 0, "medium_risk": 0, "low_risk": 0}
            
            for record in recent_records:
                severity = record.get("severity", 1)
                if severity >= 3:
                    summary["high_risk"] += 1
                elif severity >= 2:
                    summary["medium_risk"] += 1
                else:
                    summary["low_risk"] += 1
            
            return summary
            
        except Exception as e:
            logger.error(f"获取风险摘要失败 {user_id}: {e}")
            return {"total": 0, "high_risk": 0, "medium_risk": 0, "low_risk": 0}
    
    def delete_expired(self, now: datetime, policy: RetentionPolicy) -> int:
        """删除过期安全记录（安全记录通常需要长期保存）"""
        if not policy.ttl_hours:
            return 0
        
        deleted_count = 0
        cutoff_time = now - timedelta(hours=policy.ttl_hours)
        
        for file_path in self.data_dir.glob("*_safety.json"):
            try:
                deleted_count += self._clean_expired_safety(file_path, cutoff_time, now)
            except Exception as e:
                logger.error(f"清理过期安全记录失败 {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"清理过期安全记录: {deleted_count} 条")
        
        return deleted_count
    
    def _clean_expired_safety(self, file_path: Path, cutoff_time: datetime, now: datetime) -> int:
        """清理单个文件中的过期安全记录"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        records = data.get("records", [])
        original_count = len(records)
        
        # 过滤过期记录（但保留高风险记录）
        valid_records = []
        for record in records:
            try:
                record_time = datetime.fromisoformat(record["timestamp"])
                severity = record.get("severity", 1)
                
                # 高风险记录延长保存时间
                if severity >= 3:
                    extended_cutoff = cutoff_time - timedelta(days=365)  # 高风险记录保存更久
                    if record_time > extended_cutoff:
                        valid_records.append(record)
                elif record_time > cutoff_time:
                    valid_records.append(record)
            except Exception:
                # 如果时间解析失败，保留记录
                valid_records.append(record)
        
        deleted_count = original_count - len(valid_records)
        
        # 如果有记录被删除，更新文件
        if deleted_count > 0:
            data["records"] = valid_records
            data["last_updated"] = now.isoformat()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        return deleted_count
    
    def _save_user_safety(self, user_id: str, records: List[Dict[str, Any]]) -> None:
        """保存用户安全记录到文件"""
        file_path = self._get_user_file(user_id)
        
        try:
            data = {
                "user_id": user_id,
                "last_updated": datetime.now().isoformat(),
                "record_count": len(records),
                "records": records
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存安全记录失败 {user_id}: {e}")
            raise
