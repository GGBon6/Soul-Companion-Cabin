"""
健康检查API模块
Health Check API Module
提供系统健康状态检查接口
"""

from aiohttp import web
from app.shared.services import get_llm_service, get_tts_service
from app.core.asr_connection_pool import get_asr_connection_pool
from app.core import logger
import time


class HealthAPI:
    """健康检查API"""
    
    def __init__(self):
        """初始化健康检查API"""
        self.llm_service = get_llm_service()
        # ASR服务改用连接池
        self.asr_pool = get_asr_connection_pool()
        self.tts_service = get_tts_service()
        logger.info("健康检查API初始化完成")
    
    async def health(self, request: web.Request) -> web.Response:
        """
        基础健康检查
        GET /api/health
        """
        return web.json_response({
            'status': 'healthy',
            'timestamp': int(time.time()),
            'message': 'ESP-AI-Server is running'
        })
    
    async def health_detailed(self, request: web.Request) -> web.Response:
        """
        详细健康检查
        GET /api/health/detailed
        """
        try:
            # 检查各个服务状态
            services_status = {
                'llm': 'healthy',
                'asr': 'healthy', 
                'tts': 'healthy'
            }
            
            # 简单的服务可用性检查
            try:
                # 检查LLM服务
                if not self.llm_service:
                    services_status['llm'] = 'unhealthy'
            except Exception:
                services_status['llm'] = 'unhealthy'
            
            try:
                # 检查ASR连接池
                if not self.asr_pool or not self.asr_pool._started:
                    services_status['asr'] = 'unhealthy'
                else:
                    # 检查连接池状态
                    stats = self.asr_pool.get_stats()
                    if stats['total_connections'] == 0:
                        services_status['asr'] = 'degraded'
            except Exception:
                services_status['asr'] = 'unhealthy'
            
            try:
                # 检查TTS服务
                if not self.tts_service:
                    services_status['tts'] = 'unhealthy'
            except Exception:
                services_status['tts'] = 'unhealthy'
            
            # 计算整体状态
            overall_status = 'healthy' if all(
                status == 'healthy' for status in services_status.values()
            ) else 'degraded'
            
            return web.json_response({
                'status': overall_status,
                'timestamp': int(time.time()),
                'services': services_status,
                'version': '2.1.0'
            })
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return web.json_response({
                'status': 'unhealthy',
                'timestamp': int(time.time()),
                'error': str(e)
            }, status=500)
    
    async def metrics(self, request: web.Request) -> web.Response:
        """
        系统指标
        GET /api/health/metrics
        """
        try:
            import psutil
            import os
            
            # 获取系统指标
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            metrics = {
                'timestamp': int(time.time()),
                'system': {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_used_mb': memory.used // (1024 * 1024),
                    'memory_total_mb': memory.total // (1024 * 1024),
                    'disk_percent': disk.percent,
                    'disk_used_gb': disk.used // (1024 * 1024 * 1024),
                    'disk_total_gb': disk.total // (1024 * 1024 * 1024)
                },
                'process': {
                    'pid': os.getpid(),
                    'uptime_seconds': int(time.time() - psutil.Process().create_time())
                }
            }
            
            return web.json_response(metrics)
            
        except ImportError:
            return web.json_response({
                'error': 'psutil not available',
                'message': 'Install psutil for detailed metrics'
            }, status=503)
        except Exception as e:
            logger.error(f"获取系统指标失败: {e}")
            return web.json_response({
                'error': str(e)
            }, status=500)


# 创建全局实例
_health_api = None

def get_health_api() -> HealthAPI:
    """获取健康检查API单例"""
    global _health_api
    if _health_api is None:
        _health_api = HealthAPI()
    return _health_api
