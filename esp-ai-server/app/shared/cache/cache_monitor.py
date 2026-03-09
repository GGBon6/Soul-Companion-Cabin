"""
缓存监控
Cache Monitor
提供缓存性能监控、告警和统计分析
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import deque

from app.core import logger, settings


@dataclass
class CacheMetricSnapshot:
    """缓存指标快照"""
    timestamp: datetime
    cache_name: str
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_sets: int = 0
    cache_size: int = 0
    hit_rate: float = 0.0
    response_time_ms: float = 0.0
    memory_usage_mb: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'cache_name': self.cache_name,
            'total_requests': self.total_requests,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_sets': self.cache_sets,
            'cache_size': self.cache_size,
            'hit_rate': self.hit_rate,
            'response_time_ms': self.response_time_ms,
            'memory_usage_mb': self.memory_usage_mb
        }


@dataclass
class CacheAlert:
    """缓存告警"""
    alert_id: str
    cache_name: str
    alert_type: str
    severity: str  # info, warning, error, critical
    message: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'alert_id': self.alert_id,
            'cache_name': self.cache_name,
            'alert_type': self.alert_type,
            'severity': self.severity,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata,
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }


class CacheMonitor:
    """缓存监控器"""
    
    def __init__(self):
        """初始化缓存监控器"""
        self.enabled = settings.ENABLE_CACHE
        
        # 监控配置
        self.stats_interval = settings.CACHE_STATS_INTERVAL
        self.max_snapshots = 1000  # 最大保存的快照数量
        
        # 数据存储
        self.snapshots: Dict[str, deque] = {}  # 缓存名 -> 快照队列
        self.alerts: List[CacheAlert] = []
        self.alert_handlers: List[Callable[[CacheAlert], None]] = []
        
        # 告警阈值
        self.alert_thresholds = {
            'low_hit_rate': 0.5,      # 命中率低于50%
            'high_memory_usage': 0.9,  # 内存使用率高于90%
            'high_response_time': 1000, # 响应时间高于1000ms
            'cache_full': 0.95,        # 缓存使用率高于95%
        }
        
        # 后台任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info("🔧 缓存监控器初始化完成")
    
    async def start(self):
        """启动缓存监控"""
        if self._running:
            # 已经启动，跳过
            return
        
        if not self.enabled:
            logger.info("⏸️ 缓存监控已禁用")
            return
        
        logger.info("🚀 启动缓存监控...")
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("✅ 缓存监控启动完成")
    
    async def stop(self):
        """停止缓存监控"""
        logger.info("⏹️ 停止缓存监控...")
        
        self._running = False
        
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ 缓存监控已停止")
    
    def add_alert_handler(self, handler: Callable[[CacheAlert], None]):
        """添加告警处理器"""
        self.alert_handlers.append(handler)
        logger.info(f"📢 添加缓存告警处理器: {handler.__name__}")
    
    def remove_alert_handler(self, handler: Callable[[CacheAlert], None]):
        """移除告警处理器"""
        if handler in self.alert_handlers:
            self.alert_handlers.remove(handler)
            logger.info(f"📢 移除缓存告警处理器: {handler.__name__}")
    
    async def record_cache_stats(self, cache_name: str, stats: Dict[str, Any]):
        """记录缓存统计"""
        try:
            snapshot = CacheMetricSnapshot(
                timestamp=datetime.now(),
                cache_name=cache_name,
                total_requests=stats.get('total_requests', 0),
                cache_hits=stats.get('cache_hits', 0),
                cache_misses=stats.get('cache_misses', 0),
                cache_sets=stats.get('cache_sets', 0),
                cache_size=stats.get('cache_size', 0),
                hit_rate=stats.get('hit_rate', 0.0),
                response_time_ms=stats.get('response_time_ms', 0.0),
                memory_usage_mb=stats.get('memory_usage_mb', 0.0)
            )
            
            # 添加到快照队列
            if cache_name not in self.snapshots:
                self.snapshots[cache_name] = deque(maxlen=self.max_snapshots)
            
            self.snapshots[cache_name].append(snapshot)
            
            # 检查告警条件
            await self._check_alerts(snapshot)
            
        except Exception as e:
            logger.error(f"❌ 记录缓存统计失败 {cache_name}: {e}")
    
    async def _check_alerts(self, snapshot: CacheMetricSnapshot):
        """检查告警条件"""
        try:
            alerts_to_trigger = []
            
            # 检查命中率（只有在有请求时才检查）
            if snapshot.total_requests > 0 and snapshot.hit_rate < self.alert_thresholds['low_hit_rate']:
                alerts_to_trigger.append({
                    'type': 'low_hit_rate',
                    'severity': 'warning',
                    'message': f"缓存命中率过低: {snapshot.hit_rate:.2%}",
                    'metadata': {'hit_rate': snapshot.hit_rate, 'total_requests': snapshot.total_requests}
                })
            
            # 检查响应时间
            if snapshot.response_time_ms > self.alert_thresholds['high_response_time']:
                alerts_to_trigger.append({
                    'type': 'high_response_time',
                    'severity': 'warning',
                    'message': f"缓存响应时间过高: {snapshot.response_time_ms:.2f}ms",
                    'metadata': {'response_time_ms': snapshot.response_time_ms}
                })
            
            # 检查内存使用
            if snapshot.memory_usage_mb > 0:
                # 假设最大内存为1GB
                max_memory_mb = 1024
                usage_rate = snapshot.memory_usage_mb / max_memory_mb
                
                if usage_rate > self.alert_thresholds['high_memory_usage']:
                    alerts_to_trigger.append({
                        'type': 'high_memory_usage',
                        'severity': 'error',
                        'message': f"缓存内存使用率过高: {usage_rate:.2%}",
                        'metadata': {'memory_usage_mb': snapshot.memory_usage_mb, 'usage_rate': usage_rate}
                    })
            
            # 触发告警
            for alert_data in alerts_to_trigger:
                await self._trigger_alert(snapshot.cache_name, alert_data)
                
        except Exception as e:
            logger.error(f"❌ 检查缓存告警失败: {e}")
    
    async def _trigger_alert(self, cache_name: str, alert_data: Dict[str, Any]):
        """触发告警"""
        try:
            alert_id = f"{cache_name}_{alert_data['type']}_{int(time.time())}"
            
            alert = CacheAlert(
                alert_id=alert_id,
                cache_name=cache_name,
                alert_type=alert_data['type'],
                severity=alert_data['severity'],
                message=alert_data['message'],
                timestamp=datetime.now(),
                metadata=alert_data.get('metadata', {})
            )
            
            # 添加到告警列表
            self.alerts.append(alert)
            
            # 限制告警数量
            max_alerts = 1000
            if len(self.alerts) > max_alerts:
                self.alerts = self.alerts[-max_alerts:]
            
            # 调用告警处理器
            for handler in self.alert_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(alert)
                    else:
                        handler(alert)
                except Exception as e:
                    logger.error(f"❌ 告警处理器异常: {e}")
            
            logger.warning(f"🚨 缓存告警: {cache_name} - {alert.message}")
            
        except Exception as e:
            logger.error(f"❌ 触发缓存告警失败: {e}")
    
    async def _monitor_loop(self):
        """监控循环"""
        logger.info("📊 启动缓存监控循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.stats_interval)
                await self._collect_cache_stats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 缓存监控循环异常: {e}", exc_info=True)
    
    async def _collect_cache_stats(self):
        """收集缓存统计"""
        try:
            # 这里需要从各个缓存实例收集统计
            # 由于循环依赖问题，我们通过回调方式收集
            
            # 收集LLM缓存统计
            try:
                from .llm_cache import get_llm_cache
                llm_cache = get_llm_cache()
                if llm_cache.enabled:
                    stats = llm_cache.get_stats()
                    await self.record_cache_stats('llm', stats)
            except Exception as e:
                logger.debug(f"收集LLM缓存统计失败: {e}")
            
            # 收集用户画像缓存统计
            try:
                from .user_profile_cache import get_user_profile_cache
                profile_cache = get_user_profile_cache()
                if profile_cache.enabled:
                    stats = profile_cache.get_stats()
                    await self.record_cache_stats('user_profile', stats)
            except Exception as e:
                logger.debug(f"收集用户画像缓存统计失败: {e}")
                
        except Exception as e:
            logger.error(f"❌ 收集缓存统计失败: {e}")
    
    def get_cache_metrics(self, cache_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        """获取缓存指标"""
        try:
            if cache_name not in self.snapshots:
                return []
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            metrics = []
            
            for snapshot in self.snapshots[cache_name]:
                if snapshot.timestamp >= cutoff_time:
                    metrics.append(snapshot.to_dict())
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ 获取缓存指标失败 {cache_name}: {e}")
            return []
    
    def get_cache_summary(self, cache_name: str) -> Dict[str, Any]:
        """获取缓存摘要"""
        try:
            if cache_name not in self.snapshots or not self.snapshots[cache_name]:
                return {}
            
            snapshots = list(self.snapshots[cache_name])
            latest = snapshots[-1]
            
            # 计算趋势（最近10个快照）
            recent_snapshots = snapshots[-10:] if len(snapshots) >= 10 else snapshots
            
            hit_rates = [s.hit_rate for s in recent_snapshots]
            response_times = [s.response_time_ms for s in recent_snapshots]
            
            summary = {
                'cache_name': cache_name,
                'latest_snapshot': latest.to_dict(),
                'total_snapshots': len(snapshots),
                'trends': {
                    'avg_hit_rate': sum(hit_rates) / len(hit_rates) if hit_rates else 0,
                    'avg_response_time': sum(response_times) / len(response_times) if response_times else 0,
                    'hit_rate_trend': self._calculate_trend(hit_rates),
                    'response_time_trend': self._calculate_trend(response_times)
                }
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ 获取缓存摘要失败 {cache_name}: {e}")
            return {}
    
    def _calculate_trend(self, values: List[float]) -> str:
        """计算趋势"""
        if len(values) < 2:
            return "stable"
        
        # 简单的线性趋势计算
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]
        
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        
        diff_percent = (second_avg - first_avg) / first_avg if first_avg > 0 else 0
        
        if diff_percent > 0.1:  # 10%增长
            return "increasing"
        elif diff_percent < -0.1:  # 10%下降
            return "decreasing"
        else:
            return "stable"
    
    def get_alerts(self, severity: Optional[str] = None, resolved: Optional[bool] = None, 
                   hours: int = 24) -> List[Dict[str, Any]]:
        """获取告警列表"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            filtered_alerts = []
            
            for alert in self.alerts:
                # 时间过滤
                if alert.timestamp < cutoff_time:
                    continue
                
                # 严重性过滤
                if severity and alert.severity != severity:
                    continue
                
                # 解决状态过滤
                if resolved is not None and alert.resolved != resolved:
                    continue
                
                filtered_alerts.append(alert.to_dict())
            
            # 按时间倒序排列
            filtered_alerts.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return filtered_alerts
            
        except Exception as e:
            logger.error(f"❌ 获取告警列表失败: {e}")
            return []
    
    def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        try:
            for alert in self.alerts:
                if alert.alert_id == alert_id and not alert.resolved:
                    alert.resolved = True
                    alert.resolved_at = datetime.now()
                    logger.info(f"✅ 已解决告警: {alert_id}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ 解决告警失败 {alert_id}: {e}")
            return False
    
    def get_monitor_stats(self) -> Dict[str, Any]:
        """获取监控统计"""
        try:
            total_snapshots = sum(len(snapshots) for snapshots in self.snapshots.values())
            active_alerts = len([a for a in self.alerts if not a.resolved])
            
            return {
                'enabled': self.enabled,
                'monitored_caches': list(self.snapshots.keys()),
                'total_snapshots': total_snapshots,
                'total_alerts': len(self.alerts),
                'active_alerts': active_alerts,
                'alert_handlers': len(self.alert_handlers),
                'stats_interval': self.stats_interval,
                'max_snapshots': self.max_snapshots
            }
            
        except Exception as e:
            logger.error(f"❌ 获取监控统计失败: {e}")
            return {'enabled': self.enabled, 'error': str(e)}


# 全局缓存监控实例
_cache_monitor: Optional[CacheMonitor] = None


def get_cache_monitor() -> CacheMonitor:
    """获取缓存监控实例"""
    global _cache_monitor
    if _cache_monitor is None:
        _cache_monitor = CacheMonitor()
    return _cache_monitor


async def initialize_cache_monitor():
    """初始化缓存监控"""
    monitor = get_cache_monitor()
    await monitor.start()
    return monitor


async def shutdown_cache_monitor():
    """关闭缓存监控"""
    global _cache_monitor
    if _cache_monitor:
        await _cache_monitor.stop()
        _cache_monitor = None
