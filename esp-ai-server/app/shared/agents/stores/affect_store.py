"""
情绪状态存储实现
时序情绪数据的存储和检索
提供心情签到、统计等功能
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.core import logger
from app.shared.agents.base_agent import RetentionPolicy


class FileAffectStore:
    """基于文件的情绪状态存储"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir / "affects"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"初始化情绪状态存储: {self.data_dir}")
    
    def _get_user_file(self, user_id: str) -> Path:
        """获取用户情绪文件路径"""
        return self.data_dir / f"{user_id}_affects.json"
    
    def append_points(self, user_id: str, points: List[Dict[str, Any]]) -> None:
        """追加情绪数据点"""
        if not points:
            return
            
        file_path = self._get_user_file(user_id)
        
        # 加载现有数据
        existing_points = []
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_points = data.get("points", [])
            except Exception as e:
                logger.error(f"加载情绪数据失败 {user_id}: {e}")
        
        # 添加新数据点
        for point in points:
            # 确保有时间戳
            if "timestamp" not in point:
                point["timestamp"] = datetime.now().isoformat()
            elif isinstance(point["timestamp"], datetime):
                point["timestamp"] = point["timestamp"].isoformat()
            
            existing_points.append(point)
        
        # 按时间排序
        existing_points.sort(key=lambda p: p.get("timestamp", ""))
        
        # 限制数据点数量（工程化考虑）
        max_points = 10000  # 可配置
        if len(existing_points) > max_points:
            existing_points = existing_points[-max_points:]
        
        # 保存
        self._save_user_affects(user_id, existing_points)
        
        logger.debug(f"追加情绪数据: {user_id} -> +{len(points)} 个数据点")
    
    def get_series(self, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """获取情绪时序数据"""
        file_path = self._get_user_file(user_id)
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                points = data.get("points", [])
            
            # 过滤最近N天的数据
            cutoff = datetime.now() - timedelta(days=days)
            recent_points = []
            
            for point in points:
                try:
                    point_time = datetime.fromisoformat(point["timestamp"])
                    if point_time > cutoff:
                        recent_points.append(point)
                except Exception:
                    # 如果时间解析失败，跳过该数据点
                    continue
            
            return recent_points
            
        except Exception as e:
            logger.error(f"获取情绪时序数据失败 {user_id}: {e}")
            return []
    
    def delete_expired(self, now: datetime, policy: RetentionPolicy) -> int:
        """删除过期情绪记录"""
        if not policy.ttl_hours:
            return 0
        
        deleted_count = 0
        cutoff_time = now - timedelta(hours=policy.ttl_hours)
        
        for file_path in self.data_dir.glob("*_affects.json"):
            try:
                deleted_count += self._clean_expired_affects(file_path, cutoff_time, now)
            except Exception as e:
                logger.error(f"清理过期情绪数据失败 {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"清理过期情绪数据: {deleted_count} 个数据点")
        
        return deleted_count
    
    def _clean_expired_affects(self, file_path: Path, cutoff_time: datetime, now: datetime) -> int:
        """清理单个文件中的过期情绪数据"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        points = data.get("points", [])
        original_count = len(points)
        
        # 过滤过期数据点
        valid_points = []
        for point in points:
            try:
                point_time = datetime.fromisoformat(point["timestamp"])
                if point_time > cutoff_time:
                    valid_points.append(point)
            except Exception:
                # 如果时间解析失败，保留数据点
                valid_points.append(point)
        
        deleted_count = original_count - len(valid_points)
        
        # 如果有数据点被删除，更新文件
        if deleted_count > 0:
            data["points"] = valid_points
            data["last_updated"] = now.isoformat()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        return deleted_count
    
    def _save_user_affects(self, user_id: str, points: List[Dict[str, Any]]) -> None:
        """保存用户情绪数据到文件"""
        file_path = self._get_user_file(user_id)
        
        try:
            data = {
                "user_id": user_id,
                "last_updated": datetime.now().isoformat(),
                "point_count": len(points),
                "points": points
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存情绪数据失败 {user_id}: {e}")
            raise

    # ==================== 兼容 mood_service 的功能 ====================
    
    # 可用的情绪类型和对应的表情符号（从 mood_service 迁移）
    MOOD_TYPES = {
        "happy": {"name": "开心", "emoji": "😊", "color": "#FFD93D"},
        "excited": {"name": "兴奋", "emoji": "🤩", "color": "#FF6B6B"},
        "calm": {"name": "平静", "emoji": "😌", "color": "#95E1D3"},
        "sad": {"name": "难过", "emoji": "😢", "color": "#6C9BCF"},
        "angry": {"name": "生气", "emoji": "😠", "color": "#FF4757"},
        "anxious": {"name": "焦虑", "emoji": "😰", "color": "#FFA502"},
        "tired": {"name": "疲惫", "emoji": "😴", "color": "#A4B0BD"},
        "confused": {"name": "迷茫", "emoji": "😕", "color": "#B8B8B8"},
    }
    
    def check_in(
        self,
        user_id: str,
        mood: str,
        note: str = "",
        intensity: int = 3
    ) -> Dict:
        """
        心情签到（兼容 mood_service 接口）
        
        Args:
            user_id: 用户ID
            mood: 情绪类型
            note: 备注说明
            intensity: 情绪强度 (1-5)
        
        Returns:
            Dict: 签到结果
        """
        # 验证情绪类型
        if mood not in self.MOOD_TYPES:
            raise ValueError(f"无效的情绪类型: {mood}")
        
        # 验证强度
        if not 1 <= intensity <= 5:
            intensity = 3
        
        # 创建情绪数据点
        mood_info = self.MOOD_TYPES[mood]
        now = datetime.now()
        point = {
            "timestamp": now.isoformat(),
            "mood": mood,
            "emoji": mood_info["emoji"],
            "note": note,
            "intensity": intensity,
            "type": "check_in"  # 标记为签到类型
        }
        
        # 检查今天是否已签到
        today = now.date()
        today_entries = self._get_today_entries(user_id, today)
        
        # 追加新数据点
        self.append_points(user_id, [point])
        
        logger.info(f"用户 {user_id} 心情签到: {mood_info['name']} {mood_info['emoji']}")
        
        return {
            "success": True,
            "mood": mood,
            "emoji": mood_info["emoji"],
            "name": mood_info["name"],
            "timestamp": point["timestamp"],
            "is_first_today": len(today_entries) == 0,
            "today_count": len(today_entries) + 1
        }
    
    def get_today_mood(self, user_id: str) -> Optional[Dict]:
        """
        获取今日心情签到记录
        
        Args:
            user_id: 用户ID
        
        Returns:
            Optional[Dict]: 今日最新的心情记录，如果没有则返回None
        """
        today = datetime.now().date()
        today_entries = self._get_today_entries(user_id, today)
        
        if not today_entries:
            return None
        
        # 返回今天最新的记录
        latest = today_entries[-1]
        mood_info = self.MOOD_TYPES.get(latest["mood"], {})
        
        return {
            "mood": latest["mood"],
            "emoji": latest.get("emoji", mood_info.get("emoji", "😐")),
            "name": mood_info.get("name", "未知"),
            "timestamp": latest["timestamp"],
            "note": latest.get("note", ""),
            "intensity": latest.get("intensity", 3)
        }
    
    def get_mood_history(
        self,
        user_id: str,
        days: int = 7
    ) -> List[Dict]:
        """
        获取历史情绪记录（兼容 mood_service 接口）
        
        Args:
            user_id: 用户ID
            days: 获取最近多少天的记录
        
        Returns:
            List[Dict]: 情绪记录列表
        """
        points = self.get_series(user_id, days)
        
        # 过滤签到类型的记录并转换格式
        result = []
        for point in points:
            if point.get("type") == "check_in" and "mood" in point:
                mood_info = self.MOOD_TYPES.get(point["mood"], {})
                result.append({
                    "mood": point["mood"],
                    "emoji": point.get("emoji", mood_info.get("emoji", "😐")),
                    "name": mood_info.get("name", "未知"),
                    "timestamp": point["timestamp"],
                    "note": point.get("note", ""),
                    "intensity": point.get("intensity", 3),
                    "color": mood_info.get("color", "#B8B8B8")
                })
        
        return result
    
    def get_mood_statistics(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict:
        """
        获取情绪统计数据（兼容 mood_service 接口）
        
        Args:
            user_id: 用户ID
            days: 统计最近多少天
        
        Returns:
            Dict: 统计数据
        """
        history = self.get_mood_history(user_id, days)
        
        if not history:
            return {
                "total_count": 0,
                "days_checked": 0,
                "mood_distribution": {},
                "most_common_mood": None,
                "average_intensity": 0,
                "trend": "neutral"
            }
        
        # 统计各情绪的出现次数
        mood_count = {}
        total_intensity = 0
        dates_checked = set()
        
        for entry in history:
            mood = entry["mood"]
            mood_count[mood] = mood_count.get(mood, 0) + 1
            total_intensity += entry["intensity"]
            
            # 提取日期
            try:
                date_str = entry["timestamp"].split("T")[0]
                dates_checked.add(date_str)
            except Exception:
                pass
        
        # 计算最常见的情绪
        most_common_mood = max(mood_count.items(), key=lambda x: x[1])[0] if mood_count else None
        
        # 计算情绪分布百分比
        total = len(history)
        mood_distribution = {
            mood: {
                "count": count,
                "percentage": round(count / total * 100, 1),
                "name": self.MOOD_TYPES[mood]["name"],
                "emoji": self.MOOD_TYPES[mood]["emoji"]
            }
            for mood, count in mood_count.items()
        }
        
        # 计算平均强度
        average_intensity = round(total_intensity / total, 1) if total > 0 else 0
        
        # 简单趋势分析（比较前半段和后半段的正面情绪比例）
        positive_moods = {"happy", "excited", "calm"}
        mid_point = len(history) // 2
        
        first_half_positive = sum(1 for e in history[:mid_point] if e["mood"] in positive_moods)
        second_half_positive = sum(1 for e in history[mid_point:] if e["mood"] in positive_moods)
        
        if mid_point > 0:
            first_half_ratio = first_half_positive / mid_point
            second_half_ratio = second_half_positive / (len(history) - mid_point)
            
            if second_half_ratio > first_half_ratio + 0.1:
                trend = "improving"
            elif second_half_ratio < first_half_ratio - 0.1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "neutral"
        
        return {
            "total_count": total,
            "days_checked": len(dates_checked),
            "mood_distribution": mood_distribution,
            "most_common_mood": {
                "mood": most_common_mood,
                "name": self.MOOD_TYPES[most_common_mood]["name"],
                "emoji": self.MOOD_TYPES[most_common_mood]["emoji"]
            } if most_common_mood else None,
            "average_intensity": average_intensity,
            "trend": trend,
            "trend_text": {
                "improving": "最近情绪在好转哦！继续保持！",
                "stable": "情绪比较稳定呢",
                "declining": "最近似乎有些低落，要好好照顾自己哦",
                "neutral": "数据还不够，继续记录吧"
            }[trend]
        }
    
    def get_mood_calendar(
        self,
        user_id: str,
        year: int = None,
        month: int = None
    ) -> Dict:
        """
        获取情绪日历（某个月每天的情绪）
        
        Args:
            user_id: 用户ID
            year: 年份（默认当前年）
            month: 月份（默认当前月）
        
        Returns:
            Dict: 日历数据 {date: mood_info}
        """
        now = datetime.now()
        year = year or now.year
        month = month or now.month
        
        # 获取整个月的数据
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        days_in_month = (end_date - start_date).days
        points = self.get_series(user_id, days_in_month + 30)  # 多取一些确保覆盖
        
        # 过滤指定月份的记录
        calendar_data = {}
        for point in points:
            if point.get("type") == "check_in" and "mood" in point:
                try:
                    point_time = datetime.fromisoformat(point["timestamp"])
                    if point_time.year == year and point_time.month == month:
                        date_key = point_time.strftime("%Y-%m-%d")
                        mood_info = self.MOOD_TYPES.get(point["mood"], {})
                        
                        # 如果同一天有多条记录，保留最新的
                        if date_key not in calendar_data or point["timestamp"] > calendar_data[date_key]["timestamp"]:
                            calendar_data[date_key] = {
                                "mood": point["mood"],
                                "emoji": point.get("emoji", mood_info.get("emoji", "😐")),
                                "name": mood_info.get("name", "未知"),
                                "timestamp": point["timestamp"],
                                "intensity": point.get("intensity", 3),
                                "color": mood_info.get("color", "#B8B8B8")
                            }
                except Exception:
                    continue
        
        return {
            "year": year,
            "month": month,
            "data": calendar_data
        }
    
    def get_available_moods(self) -> List[Dict]:
        """
        获取所有可用的情绪类型
        
        Returns:
            List[Dict]: 情绪类型列表
        """
        return [
            {
                "id": mood_id,
                "name": info["name"],
                "emoji": info["emoji"],
                "color": info["color"]
            }
            for mood_id, info in self.MOOD_TYPES.items()
        ]
    
    def _get_today_entries(self, user_id: str, target_date: datetime.date) -> List[Dict]:
        """获取指定日期的签到记录"""
        points = self.get_series(user_id, days=1)
        today_entries = []
        
        for point in points:
            if point.get("type") == "check_in":
                try:
                    point_time = datetime.fromisoformat(point["timestamp"])
                    if point_time.date() == target_date:
                        today_entries.append(point)
                except Exception:
                    continue
        
        return today_entries
