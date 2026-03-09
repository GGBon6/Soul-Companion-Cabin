"""
ASR连接池监控API
ASR Connection Pool Monitoring API
提供连接池状态查询、指标监控和管理接口
"""

from typing import Dict, Any
from app.core import logger
from app.core.asr_connection_pool import get_asr_connection_pool


class ASRPoolMonitor:
    """ASR连接池监控器"""
    
    def __init__(self):
        """初始化监控器"""
        self.pool = get_asr_connection_pool()
        logger.info("✅ ASR连接池监控器初始化完成")
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态
        
        Returns:
            连接池状态信息
        """
        stats = self.pool.get_stats()
        metrics = self.pool.get_metrics()
        
        return {
            "status": "healthy" if stats['total_connections'] > 0 else "unhealthy",
            "pool_config": {
                "min_connections": self.pool.min_connections,
                "max_connections": self.pool.max_connections,
                "max_idle_time": self.pool.max_idle_time,
                "health_check_interval": self.pool.health_check_interval,
                "acquire_timeout": self.pool.acquire_timeout
            },
            "current_state": {
                "total_connections": stats['total_connections'],
                "idle_connections": stats['idle_connections'],
                "busy_connections": stats['busy_connections'],
                "unhealthy_connections": stats['unhealthy_connections'],
                "wait_queue_size": stats['wait_queue_size']
            },
            "performance_metrics": {
                "total_requests": stats['total_requests'],
                "successful_requests": stats['successful_requests'],
                "failed_requests": stats['failed_requests'],
                "success_rate": stats['success_rate'],
                "avg_processing_time": stats['avg_processing_time'],
                "avg_wait_time": stats['avg_wait_time']
            },
            "connections_by_type": stats['connections_by_type'],
            "last_updated": metrics.last_updated.isoformat()
        }
    
    def get_connection_details(self) -> Dict[str, Any]:
        """
        获取所有连接的详细信息
        
        Returns:
            连接详细信息列表
        """
        connections = []
        
        for conn_id, conn_info in self.pool.connections.items():
            connections.append({
                "connection_id": conn_id,
                "client_type": conn_info.client_type,
                "client_id": conn_info.client_id,
                "state": conn_info.state.value,
                "created_at": conn_info.created_at.isoformat(),
                "last_used": conn_info.last_used.isoformat(),
                "use_count": conn_info.use_count,
                "error_count": conn_info.error_count,
                "total_processing_time": conn_info.total_processing_time,
                "avg_processing_time": (
                    conn_info.total_processing_time / conn_info.use_count
                    if conn_info.use_count > 0 else 0.0
                ),
                "metadata": conn_info.metadata
            })
        
        return {
            "total_connections": len(connections),
            "connections": connections
        }
    
    def get_health_report(self) -> Dict[str, Any]:
        """
        获取健康报告
        
        Returns:
            健康报告
        """
        stats = self.pool.get_stats()
        
        # 计算健康分数
        health_score = 100.0
        issues = []
        
        # 检查连接池利用率
        utilization = stats['busy_connections'] / stats['total_connections'] * 100 if stats['total_connections'] > 0 else 0
        if utilization > 90:
            health_score -= 20
            issues.append("连接池利用率过高 (>90%)")
        elif utilization > 75:
            health_score -= 10
            issues.append("连接池利用率较高 (>75%)")
        
        # 检查不健康连接
        if stats['unhealthy_connections'] > 0:
            health_score -= stats['unhealthy_connections'] * 10
            issues.append(f"存在 {stats['unhealthy_connections']} 个不健康连接")
        
        # 检查等待队列
        if stats['wait_queue_size'] > 0:
            health_score -= stats['wait_queue_size'] * 5
            issues.append(f"等待队列中有 {stats['wait_queue_size']} 个请求")
        
        # 检查成功率
        if stats['success_rate'] < 95:
            health_score -= (95 - stats['success_rate'])
            issues.append(f"成功率低于95% (当前: {stats['success_rate']:.1f}%)")
        
        # 检查平均等待时间
        if stats['avg_wait_time'] > 5.0:
            health_score -= 15
            issues.append(f"平均等待时间过长 (>{stats['avg_wait_time']:.2f}s)")
        
        health_score = max(0, health_score)
        
        return {
            "health_score": health_score,
            "status": self._get_health_status(health_score),
            "issues": issues,
            "recommendations": self._get_recommendations(stats, health_score),
            "metrics": {
                "utilization": utilization,
                "success_rate": stats['success_rate'],
                "avg_wait_time": stats['avg_wait_time'],
                "avg_processing_time": stats['avg_processing_time']
            }
        }
    
    def _get_health_status(self, score: float) -> str:
        """根据健康分数获取状态"""
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 60:
            return "fair"
        elif score >= 40:
            return "poor"
        else:
            return "critical"
    
    def _get_recommendations(self, stats: Dict, health_score: float) -> list:
        """获取优化建议"""
        recommendations = []
        
        utilization = stats['busy_connections'] / stats['total_connections'] * 100 if stats['total_connections'] > 0 else 0
        
        if utilization > 80:
            recommendations.append("建议增加最大连接数以应对高负载")
        
        if stats['wait_queue_size'] > 5:
            recommendations.append("等待队列过长，建议增加连接池容量")
        
        if stats['success_rate'] < 95:
            recommendations.append("成功率较低，建议检查ASR服务稳定性")
        
        if stats['avg_wait_time'] > 5.0:
            recommendations.append("等待时间过长，建议优化连接获取策略")
        
        if stats['unhealthy_connections'] > 0:
            recommendations.append("存在不健康连接，建议检查健康检查配置")
        
        if health_score < 60:
            recommendations.append("连接池健康状况不佳，建议进行全面检查和优化")
        
        return recommendations
    
    def get_performance_trends(self) -> Dict[str, Any]:
        """
        获取性能趋势（简化版，实际应该从时序数据库读取）
        
        Returns:
            性能趋势数据
        """
        stats = self.pool.get_stats()
        
        return {
            "current_metrics": {
                "total_requests": stats['total_requests'],
                "success_rate": stats['success_rate'],
                "avg_processing_time": stats['avg_processing_time'],
                "avg_wait_time": stats['avg_wait_time']
            },
            "note": "完整的趋势分析需要集成时序数据库（如InfluxDB或Prometheus）"
        }


# 全局监控器实例
_asr_pool_monitor = None


def get_asr_pool_monitor() -> ASRPoolMonitor:
    """获取ASR连接池监控器实例"""
    global _asr_pool_monitor
    if _asr_pool_monitor is None:
        _asr_pool_monitor = ASRPoolMonitor()
    return _asr_pool_monitor


# ==================== HTTP API端点（示例） ====================

async def handle_pool_status_request() -> Dict[str, Any]:
    """处理连接池状态查询请求"""
    monitor = get_asr_pool_monitor()
    return {
        "success": True,
        "data": monitor.get_pool_status()
    }


async def handle_connection_details_request() -> Dict[str, Any]:
    """处理连接详情查询请求"""
    monitor = get_asr_pool_monitor()
    return {
        "success": True,
        "data": monitor.get_connection_details()
    }


async def handle_health_report_request() -> Dict[str, Any]:
    """处理健康报告查询请求"""
    monitor = get_asr_pool_monitor()
    return {
        "success": True,
        "data": monitor.get_health_report()
    }


async def handle_performance_trends_request() -> Dict[str, Any]:
    """处理性能趋势查询请求"""
    monitor = get_asr_pool_monitor()
    return {
        "success": True,
        "data": monitor.get_performance_trends()
    }
