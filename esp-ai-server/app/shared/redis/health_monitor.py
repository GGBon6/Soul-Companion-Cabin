"""
Redis健康监控
Redis Health Monitor
提供Redis连接健康监控、性能指标收集和故障告警
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from app.core import logger, settings
from .redis_manager import get_redis_manager


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthMetric:
    """健康指标"""
    name: str
    value: float
    unit: str
    status: HealthStatus
    threshold_warning: float = 0.0
    threshold_critical: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def update_status(self):
        """根据阈值更新状态"""
        if self.value >= self.threshold_critical:
            self.status = HealthStatus.CRITICAL
        elif self.value >= self.threshold_warning:
            self.status = HealthStatus.WARNING
        else:
            self.status = HealthStatus.HEALTHY


@dataclass
class HealthReport:
    """健康报告"""
    overall_status: HealthStatus
    metrics: Dict[str, HealthMetric]
    alerts: List[str]
    timestamp: datetime
    uptime_seconds: float
    
    def add_alert(self, message: str):
        """添加告警"""
        self.alerts.append(f"{datetime.now().isoformat()}: {message}")
    
    def get_critical_metrics(self) -> List[HealthMetric]:
        """获取严重状态的指标"""
        return [metric for metric in self.metrics.values() 
                if metric.status == HealthStatus.CRITICAL]
    
    def get_warning_metrics(self) -> List[HealthMetric]:
        """获取警告状态的指标"""
        return [metric for metric in self.metrics.values() 
                if metric.status == HealthStatus.WARNING]


class RedisHealthMonitor:
    """Redis健康监控器"""
    
    def __init__(self):
        """初始化健康监控器"""
        self.redis_manager = get_redis_manager()
        self.start_time = time.time()
        
        # 监控配置
        self.check_interval = settings.REDIS_HEALTH_CHECK_INTERVAL
        self.alert_handlers: List[Callable[[HealthReport], None]] = []
        
        # 历史数据
        self.metric_history: Dict[str, List[HealthMetric]] = {}
        self.max_history_size = 100
        
        # 后台任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 阈值配置
        self.thresholds = {
            'response_time': {'warning': 100.0, 'critical': 500.0},  # 毫秒
            'memory_usage': {'warning': 80.0, 'critical': 95.0},    # 百分比
            'connection_count': {'warning': 80.0, 'critical': 95.0}, # 百分比
            'command_failure_rate': {'warning': 5.0, 'critical': 15.0}, # 百分比
            'cpu_usage': {'warning': 80.0, 'critical': 95.0},       # 百分比
        }
        
        logger.info("🔧 Redis健康监控器初始化完成")
    
    async def start(self):
        """启动健康监控"""
        if not settings.ENABLE_REDIS or not self.redis_manager.is_connected():
            logger.info("⏸️ Redis健康监控已禁用或Redis未连接")
            return
        
        logger.info("🚀 启动Redis健康监控...")
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("✅ Redis健康监控启动完成")
    
    async def stop(self):
        """停止健康监控"""
        logger.info("⏹️ 停止Redis健康监控...")
        
        self._running = False
        
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("✅ Redis健康监控已停止")
    
    def add_alert_handler(self, handler: Callable[[HealthReport], None]):
        """添加告警处理器"""
        self.alert_handlers.append(handler)
        logger.info(f"📢 添加告警处理器: {handler.__name__}")
    
    def remove_alert_handler(self, handler: Callable[[HealthReport], None]):
        """移除告警处理器"""
        if handler in self.alert_handlers:
            self.alert_handlers.remove(handler)
            logger.info(f"📢 移除告警处理器: {handler.__name__}")
    
    async def get_health_report(self) -> HealthReport:
        """获取健康报告"""
        try:
            metrics = await self._collect_metrics()
            
            # 计算总体状态
            overall_status = HealthStatus.HEALTHY
            alerts = []
            
            critical_metrics = []
            warning_metrics = []
            
            for metric in metrics.values():
                if metric.status == HealthStatus.CRITICAL:
                    critical_metrics.append(metric)
                    overall_status = HealthStatus.CRITICAL
                elif metric.status == HealthStatus.WARNING:
                    warning_metrics.append(metric)
                    if overall_status == HealthStatus.HEALTHY:
                        overall_status = HealthStatus.WARNING
            
            # 生成告警信息
            for metric in critical_metrics:
                alerts.append(f"CRITICAL: {metric.name} = {metric.value}{metric.unit}")
            
            for metric in warning_metrics:
                alerts.append(f"WARNING: {metric.name} = {metric.value}{metric.unit}")
            
            report = HealthReport(
                overall_status=overall_status,
                metrics=metrics,
                alerts=alerts,
                timestamp=datetime.now(),
                uptime_seconds=time.time() - self.start_time
            )
            
            return report
            
        except Exception as e:
            logger.error(f"❌ 获取健康报告失败: {e}", exc_info=True)
            return HealthReport(
                overall_status=HealthStatus.UNKNOWN,
                metrics={},
                alerts=[f"获取健康报告失败: {e}"],
                timestamp=datetime.now(),
                uptime_seconds=time.time() - self.start_time
            )
    
    async def _collect_metrics(self) -> Dict[str, HealthMetric]:
        """收集健康指标"""
        metrics = {}
        
        try:
            # 响应时间
            response_time = await self._measure_response_time()
            metrics['response_time'] = HealthMetric(
                name='response_time',
                value=response_time,
                unit='ms',
                status=HealthStatus.HEALTHY,
                threshold_warning=self.thresholds['response_time']['warning'],
                threshold_critical=self.thresholds['response_time']['critical']
            )
            metrics['response_time'].update_status()
            
            # Redis信息
            redis_info = await self._get_redis_info()
            
            # 内存使用率
            if 'used_memory' in redis_info and 'maxmemory' in redis_info:
                max_memory = redis_info['maxmemory']
                if max_memory > 0:
                    memory_usage = (redis_info['used_memory'] / max_memory) * 100
                    metrics['memory_usage'] = HealthMetric(
                        name='memory_usage',
                        value=memory_usage,
                        unit='%',
                        status=HealthStatus.HEALTHY,
                        threshold_warning=self.thresholds['memory_usage']['warning'],
                        threshold_critical=self.thresholds['memory_usage']['critical']
                    )
                    metrics['memory_usage'].update_status()
            
            # 连接数使用率
            if 'connected_clients' in redis_info and 'maxclients' in redis_info:
                max_clients = redis_info['maxclients']
                if max_clients > 0:
                    connection_usage = (redis_info['connected_clients'] / max_clients) * 100
                    metrics['connection_count'] = HealthMetric(
                        name='connection_count',
                        value=connection_usage,
                        unit='%',
                        status=HealthStatus.HEALTHY,
                        threshold_warning=self.thresholds['connection_count']['warning'],
                        threshold_critical=self.thresholds['connection_count']['critical']
                    )
                    metrics['connection_count'].update_status()
            
            # 命令失败率
            redis_metrics = self.redis_manager.get_metrics()
            if redis_metrics.total_commands > 0:
                failure_rate = (redis_metrics.failed_commands / redis_metrics.total_commands) * 100
                metrics['command_failure_rate'] = HealthMetric(
                    name='command_failure_rate',
                    value=failure_rate,
                    unit='%',
                    status=HealthStatus.HEALTHY,
                    threshold_warning=self.thresholds['command_failure_rate']['warning'],
                    threshold_critical=self.thresholds['command_failure_rate']['critical']
                )
                metrics['command_failure_rate'].update_status()
            
            # CPU使用率（如果可用）
            if 'used_cpu_sys' in redis_info:
                cpu_usage = redis_info['used_cpu_sys']
                metrics['cpu_usage'] = HealthMetric(
                    name='cpu_usage',
                    value=cpu_usage,
                    unit='%',
                    status=HealthStatus.HEALTHY,
                    threshold_warning=self.thresholds['cpu_usage']['warning'],
                    threshold_critical=self.thresholds['cpu_usage']['critical']
                )
                metrics['cpu_usage'].update_status()
            
        except Exception as e:
            logger.error(f"❌ 收集指标失败: {e}")
        
        return metrics
    
    async def _measure_response_time(self) -> float:
        """测量响应时间"""
        try:
            start_time = time.time()
            await self.redis_manager.execute_command('ping')
            end_time = time.time()
            return (end_time - start_time) * 1000  # 转换为毫秒
        except Exception as e:
            logger.error(f"❌ 测量响应时间失败: {e}")
            return 999999.0  # 返回一个很大的值表示失败
    
    async def _get_redis_info(self) -> Dict[str, Any]:
        """获取Redis信息"""
        try:
            info = await self.redis_manager.execute_command('info')
            
            # 解析info字符串
            parsed_info = {}
            for line in info.split('\r\n'):
                if ':' in line and not line.startswith('#'):
                    key, value = line.split(':', 1)
                    # 尝试转换为数字
                    try:
                        if '.' in value:
                            parsed_info[key] = float(value)
                        else:
                            parsed_info[key] = int(value)
                    except ValueError:
                        parsed_info[key] = value
            
            return parsed_info
            
        except Exception as e:
            logger.error(f"❌ 获取Redis信息失败: {e}")
            return {}
    
    async def _monitor_loop(self):
        """监控循环"""
        logger.info("🏥 启动Redis健康监控循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 健康监控循环异常: {e}", exc_info=True)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        try:
            report = await self.get_health_report()
            
            # 记录历史数据
            self._record_metrics_history(report.metrics)
            
            # 检查是否需要告警
            if report.overall_status in [HealthStatus.WARNING, HealthStatus.CRITICAL]:
                await self._trigger_alerts(report)
            
            # 记录健康状态
            if report.overall_status == HealthStatus.CRITICAL:
                logger.error(f"🚨 Redis健康状态严重: {len(report.get_critical_metrics())} 个严重指标")
            elif report.overall_status == HealthStatus.WARNING:
                logger.warning(f"⚠️ Redis健康状态警告: {len(report.get_warning_metrics())} 个警告指标")
            else:
                logger.debug("✅ Redis健康状态正常")
                
        except Exception as e:
            logger.error(f"❌ 执行健康检查失败: {e}")
    
    def _record_metrics_history(self, metrics: Dict[str, HealthMetric]):
        """记录指标历史"""
        try:
            for name, metric in metrics.items():
                if name not in self.metric_history:
                    self.metric_history[name] = []
                
                self.metric_history[name].append(metric)
                
                # 限制历史记录大小
                if len(self.metric_history[name]) > self.max_history_size:
                    self.metric_history[name] = self.metric_history[name][-self.max_history_size:]
                    
        except Exception as e:
            logger.error(f"❌ 记录指标历史失败: {e}")
    
    async def _trigger_alerts(self, report: HealthReport):
        """触发告警"""
        try:
            for handler in self.alert_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(report)
                    else:
                        handler(report)
                except Exception as e:
                    logger.error(f"❌ 告警处理器异常: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"❌ 触发告警失败: {e}")
    
    def get_metric_history(self, metric_name: str, hours: int = 24) -> List[HealthMetric]:
        """获取指标历史"""
        if metric_name not in self.metric_history:
            return []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [metric for metric in self.metric_history[metric_name] 
                if metric.timestamp >= cutoff_time]
    
    def get_all_metrics_summary(self) -> Dict[str, Dict[str, Any]]:
        """获取所有指标摘要"""
        summary = {}
        
        for name, history in self.metric_history.items():
            if not history:
                continue
            
            latest = history[-1]
            values = [m.value for m in history[-10:]]  # 最近10个值
            
            summary[name] = {
                'latest_value': latest.value,
                'latest_status': latest.status.value,
                'unit': latest.unit,
                'avg_recent': sum(values) / len(values) if values else 0,
                'min_recent': min(values) if values else 0,
                'max_recent': max(values) if values else 0,
                'threshold_warning': latest.threshold_warning,
                'threshold_critical': latest.threshold_critical,
                'history_count': len(history)
            }
        
        return summary


# 全局Redis健康监控实例
_redis_health_monitor: Optional[RedisHealthMonitor] = None


def get_redis_health_monitor() -> RedisHealthMonitor:
    """获取Redis健康监控实例"""
    global _redis_health_monitor
    if _redis_health_monitor is None:
        _redis_health_monitor = RedisHealthMonitor()
    return _redis_health_monitor


async def initialize_redis_health_monitor():
    """初始化Redis健康监控"""
    monitor = get_redis_health_monitor()
    await monitor.start()
    return monitor


async def shutdown_redis_health_monitor():
    """关闭Redis健康监控"""
    global _redis_health_monitor
    if _redis_health_monitor:
        await _redis_health_monitor.stop()
        _redis_health_monitor = None
