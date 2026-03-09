"""
ESP32服务连接管理器
ESP32 Service Connection Manager
管理ASR、TTS、LLM等服务的连接池、负载均衡和故障转移
优化服务连接的复用和资源管理
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass
from enum import Enum
import logging

from app.core.asr_connection_pool import get_asr_connection_pool
from app.shared.services.asr_service import acquire_asr_service
from app.shared.services.tts_service import get_tts_service
from app.shared.services.llm_service import get_llm_service


class ServiceType(Enum):
    """服务类型"""
    ASR = "asr"
    TTS = "tts"
    LLM = "llm"


class ServiceStatus(Enum):
    """服务状态"""
    HEALTHY = "healthy"         # 健康
    DEGRADED = "degraded"       # 降级
    UNAVAILABLE = "unavailable" # 不可用
    MAINTENANCE = "maintenance" # 维护中


@dataclass
class ServiceMetrics:
    """服务指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_requests: int = 0
    
    total_response_time: float = 0.0
    min_response_time: float = float('inf')
    max_response_time: float = 0.0
    
    active_connections: int = 0
    max_connections: int = 0
    
    last_request_time: Optional[float] = None
    last_success_time: Optional[float] = None
    last_failure_time: Optional[float] = None
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def avg_response_time(self) -> float:
        """平均响应时间"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time / self.successful_requests
    
    @property
    def connection_utilization(self) -> float:
        """连接利用率"""
        if self.max_connections == 0:
            return 0.0
        return (self.active_connections / self.max_connections) * 100


@dataclass
class ServiceHealth:
    """服务健康状态"""
    service_type: ServiceType
    status: ServiceStatus
    metrics: ServiceMetrics
    last_check_time: float
    error_message: Optional[str] = None
    
    def is_healthy(self) -> bool:
        """是否健康"""
        return self.status in [ServiceStatus.HEALTHY, ServiceStatus.DEGRADED]
    
    def is_available(self) -> bool:
        """是否可用"""
        return self.status != ServiceStatus.UNAVAILABLE


class ESP32ServiceConnectionManager:
    """ESP32服务连接管理器"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.tag = f"ESP32ServiceManager[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # 服务健康状态
        self.service_health: Dict[ServiceType, ServiceHealth] = {}
        
        # 连接池配置
        self.asr_pool_config = {
            "max_connections": 10,
            "timeout": 30.0,
            "health_check_interval": 60.0
        }
        
        self.tts_config = {
            "max_concurrent": 5,
            "timeout": 15.0,
            "cache_enabled": True
        }
        
        self.llm_config = {
            "timeout": 30.0,
            "max_retries": 2,
            "temperature": 0.7
        }
        
        # 故障转移配置
        self.circuit_breaker_config = {
            "failure_threshold": 5,      # 连续失败阈值
            "recovery_timeout": 60.0,    # 恢复超时时间
            "half_open_max_calls": 3     # 半开状态最大调用数
        }
        
        # 断路器状态
        self.circuit_breakers: Dict[ServiceType, Dict[str, Any]] = {}
        
        # 活跃连接跟踪
        self.active_connections: Dict[ServiceType, Set[str]] = {
            ServiceType.ASR: set(),
            ServiceType.TTS: set(),
            ServiceType.LLM: set()
        }
        
        # 初始化服务健康状态
        self._initialize_service_health()
        
        # 启动健康检查任务
        self._health_check_task = None
        
        self.logger.info(f"[{self.tag}] 服务连接管理器初始化完成")
    
    def _initialize_service_health(self) -> None:
        """初始化服务健康状态"""
        for service_type in ServiceType:
            self.service_health[service_type] = ServiceHealth(
                service_type=service_type,
                status=ServiceStatus.HEALTHY,
                metrics=ServiceMetrics(),
                last_check_time=time.time()
            )
            
            # 初始化断路器
            self.circuit_breakers[service_type] = {
                "state": "closed",  # closed, open, half_open
                "failure_count": 0,
                "last_failure_time": 0,
                "next_attempt_time": 0,
                "half_open_calls": 0
            }
    
    async def start_health_monitoring(self) -> None:
        """启动健康监控"""
        if self._health_check_task is None:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            self.logger.info(f"[{self.tag}] 健康监控已启动")
    
    async def stop_health_monitoring(self) -> None:
        """停止健康监控"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            self.logger.info(f"[{self.tag}] 健康监控已停止")
    
    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while True:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(60)  # 每分钟检查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"[{self.tag}] 健康检查失败: {e}")
                await asyncio.sleep(30)  # 出错时减少检查频率
    
    async def _perform_health_checks(self) -> None:
        """执行健康检查"""
        self.logger.debug(f"[{self.tag}] 开始健康检查")
        
        # 检查ASR服务
        await self._check_asr_health()
        
        # 检查TTS服务
        await self._check_tts_health()
        
        # 检查LLM服务
        await self._check_llm_health()
        
        # 更新断路器状态
        self._update_circuit_breakers()
        
        self.logger.debug(f"[{self.tag}] 健康检查完成")
    
    async def _check_asr_health(self) -> None:
        """检查ASR服务健康状态"""
        try:
            start_time = time.time()
            
            # 尝试获取ASR连接
            pool = get_asr_connection_pool()
            pool_stats = pool.get_stats()
            
            health = self.service_health[ServiceType.ASR]
            health.metrics.active_connections = pool_stats.get("active_connections", 0)
            health.metrics.max_connections = pool_stats.get("max_connections", 0)
            health.last_check_time = time.time()
            
            # 根据连接池状态判断健康状态
            utilization = health.metrics.connection_utilization
            if utilization < 80:
                health.status = ServiceStatus.HEALTHY
            elif utilization < 95:
                health.status = ServiceStatus.DEGRADED
            else:
                health.status = ServiceStatus.UNAVAILABLE
                
        except Exception as e:
            health = self.service_health[ServiceType.ASR]
            health.status = ServiceStatus.UNAVAILABLE
            health.error_message = str(e)
            health.last_check_time = time.time()
            self.logger.error(f"[{self.tag}] ASR健康检查失败: {e}")
    
    async def _check_tts_health(self) -> None:
        """检查TTS服务健康状态"""
        try:
            # 获取TTS服务实例
            tts_service = get_tts_service()
            concurrent_info = tts_service.get_concurrent_info()
            
            health = self.service_health[ServiceType.TTS]
            health.metrics.active_connections = concurrent_info.get("current_concurrent", 0)
            health.metrics.max_connections = concurrent_info.get("max_concurrent", 0)
            health.last_check_time = time.time()
            
            # 根据并发情况判断健康状态
            utilization = health.metrics.connection_utilization
            if utilization < 80:
                health.status = ServiceStatus.HEALTHY
            elif utilization < 95:
                health.status = ServiceStatus.DEGRADED
            else:
                health.status = ServiceStatus.UNAVAILABLE
                
        except Exception as e:
            health = self.service_health[ServiceType.TTS]
            health.status = ServiceStatus.UNAVAILABLE
            health.error_message = str(e)
            health.last_check_time = time.time()
            self.logger.error(f"[{self.tag}] TTS健康检查失败: {e}")
    
    async def _check_llm_health(self) -> None:
        """检查LLM服务健康状态"""
        try:
            # 简单的LLM健康检查（发送测试消息）
            from app.core.application import get_app
            try:
                app = get_app()
                llm_service = await app.get_llm_service('esp32')
            except RuntimeError:
                # 应用未初始化，降级到同步方式
                llm_service = get_llm_service()
            
            start_time = time.time()
            test_messages = [{"role": "user", "content": "ping"}]
            
            # 设置较短的超时时间进行健康检查
            response = await asyncio.wait_for(
                llm_service.chat_async(test_messages, temperature=0.1),
                timeout=5.0
            )
            
            response_time = time.time() - start_time
            
            health = self.service_health[ServiceType.LLM]
            health.last_check_time = time.time()
            
            if response and response_time < 3.0:
                health.status = ServiceStatus.HEALTHY
            elif response and response_time < 8.0:
                health.status = ServiceStatus.DEGRADED
            else:
                health.status = ServiceStatus.UNAVAILABLE
                
        except asyncio.TimeoutError:
            health = self.service_health[ServiceType.LLM]
            health.status = ServiceStatus.DEGRADED
            health.error_message = "响应超时"
            health.last_check_time = time.time()
        except Exception as e:
            health = self.service_health[ServiceType.LLM]
            health.status = ServiceStatus.UNAVAILABLE
            health.error_message = str(e)
            health.last_check_time = time.time()
            self.logger.error(f"[{self.tag}] LLM健康检查失败: {e}")
    
    def _update_circuit_breakers(self) -> None:
        """更新断路器状态"""
        current_time = time.time()
        
        for service_type, health in self.service_health.items():
            breaker = self.circuit_breakers[service_type]
            
            if breaker["state"] == "open":
                # 检查是否可以尝试恢复
                if current_time >= breaker["next_attempt_time"]:
                    breaker["state"] = "half_open"
                    breaker["half_open_calls"] = 0
                    self.logger.info(f"[{self.tag}] {service_type.value}断路器进入半开状态")
            
            elif breaker["state"] == "half_open":
                # 半开状态下，如果服务健康则关闭断路器
                if health.is_healthy():
                    breaker["state"] = "closed"
                    breaker["failure_count"] = 0
                    self.logger.info(f"[{self.tag}] {service_type.value}断路器已关闭")
    
    async def acquire_asr_service(self, timeout: Optional[float] = None) -> Optional[Any]:
        """
        获取ASR服务
        
        Args:
            timeout: 超时时间
            
        Returns:
            ASR服务实例或None
        """
        if not self._can_call_service(ServiceType.ASR):
            return None
        
        try:
            start_time = time.time()
            
            async with acquire_asr_service("esp32", self.device_id, timeout) as asr_service:
                # 记录成功指标
                self._record_service_success(ServiceType.ASR, time.time() - start_time)
                return asr_service
                
        except Exception as e:
            self._record_service_failure(ServiceType.ASR, str(e))
            self.logger.error(f"[{self.tag}] 获取ASR服务失败: {e}")
            return None
    
    async def call_tts_service(self, text: str, **kwargs) -> Optional[bytes]:
        """
        调用TTS服务
        
        Args:
            text: 合成文本
            **kwargs: 其他参数
            
        Returns:
            音频数据或None
        """
        if not self._can_call_service(ServiceType.TTS):
            return None
        
        try:
            start_time = time.time()
            
            tts_service = get_tts_service()
            audio_data = await tts_service.synthesize_async(text, client_type="esp32", **kwargs)
            
            # 记录成功指标
            self._record_service_success(ServiceType.TTS, time.time() - start_time)
            return audio_data
            
        except Exception as e:
            self._record_service_failure(ServiceType.TTS, str(e))
            self.logger.error(f"[{self.tag}] TTS服务调用失败: {e}")
            return None
    
    async def call_llm_service(self, messages: List[Dict], **kwargs) -> Optional[str]:
        """
        调用LLM服务
        
        Args:
            messages: 对话消息
            **kwargs: 其他参数
            
        Returns:
            回复文本或None
        """
        if not self._can_call_service(ServiceType.LLM):
            return None
        
        try:
            start_time = time.time()
            
            from app.core.application import get_app
            try:
                app = get_app()
                llm_service = await app.get_llm_service('esp32')
            except RuntimeError:
                # 应用未初始化，降级到同步方式
                llm_service = get_llm_service()
            response = await llm_service.chat_async(messages, **kwargs)
            
            # 记录成功指标
            self._record_service_success(ServiceType.LLM, time.time() - start_time)
            return response
            
        except Exception as e:
            self._record_service_failure(ServiceType.LLM, str(e))
            self.logger.error(f"[{self.tag}] LLM服务调用失败: {e}")
            return None
    
    def _can_call_service(self, service_type: ServiceType) -> bool:
        """
        检查是否可以调用服务
        
        Args:
            service_type: 服务类型
            
        Returns:
            bool: 是否可以调用
        """
        breaker = self.circuit_breakers[service_type]
        
        if breaker["state"] == "open":
            return False
        
        if breaker["state"] == "half_open":
            if breaker["half_open_calls"] >= self.circuit_breaker_config["half_open_max_calls"]:
                return False
            breaker["half_open_calls"] += 1
        
        health = self.service_health[service_type]
        return health.is_available()
    
    def _record_service_success(self, service_type: ServiceType, response_time: float) -> None:
        """
        记录服务成功调用
        
        Args:
            service_type: 服务类型
            response_time: 响应时间
        """
        metrics = self.service_health[service_type].metrics
        metrics.total_requests += 1
        metrics.successful_requests += 1
        metrics.total_response_time += response_time
        metrics.min_response_time = min(metrics.min_response_time, response_time)
        metrics.max_response_time = max(metrics.max_response_time, response_time)
        metrics.last_request_time = time.time()
        metrics.last_success_time = time.time()
        
        # 重置断路器失败计数
        breaker = self.circuit_breakers[service_type]
        if breaker["state"] == "half_open":
            breaker["state"] = "closed"
            breaker["failure_count"] = 0
    
    def _record_service_failure(self, service_type: ServiceType, error_message: str) -> None:
        """
        记录服务失败调用
        
        Args:
            service_type: 服务类型
            error_message: 错误信息
        """
        metrics = self.service_health[service_type].metrics
        metrics.total_requests += 1
        metrics.failed_requests += 1
        metrics.last_request_time = time.time()
        metrics.last_failure_time = time.time()
        
        # 更新断路器状态
        breaker = self.circuit_breakers[service_type]
        breaker["failure_count"] += 1
        breaker["last_failure_time"] = time.time()
        
        # 检查是否需要打开断路器
        if breaker["failure_count"] >= self.circuit_breaker_config["failure_threshold"]:
            breaker["state"] = "open"
            breaker["next_attempt_time"] = time.time() + self.circuit_breaker_config["recovery_timeout"]
            self.logger.warning(f"[{self.tag}] {service_type.value}断路器已打开")
        
        # 更新健康状态
        health = self.service_health[service_type]
        health.error_message = error_message
        if breaker["state"] == "open":
            health.status = ServiceStatus.UNAVAILABLE
    
    def get_service_health(self, service_type: Optional[ServiceType] = None) -> Dict[str, Any]:
        """
        获取服务健康状态
        
        Args:
            service_type: 服务类型，None表示获取所有
            
        Returns:
            健康状态信息
        """
        if service_type:
            health = self.service_health[service_type]
            breaker = self.circuit_breakers[service_type]
            
            return {
                "service_type": service_type.value,
                "status": health.status.value,
                "metrics": {
                    "total_requests": health.metrics.total_requests,
                    "success_rate": round(health.metrics.success_rate, 2),
                    "avg_response_time": round(health.metrics.avg_response_time, 3),
                    "active_connections": health.metrics.active_connections,
                    "connection_utilization": round(health.metrics.connection_utilization, 2)
                },
                "circuit_breaker": {
                    "state": breaker["state"],
                    "failure_count": breaker["failure_count"]
                },
                "last_check_time": health.last_check_time,
                "error_message": health.error_message
            }
        
        # 返回所有服务的健康状态
        return {
            service_type.value: self.get_service_health(service_type)
            for service_type in ServiceType
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "device_id": self.device_id,
            "service_health": self.get_service_health(),
            "config": {
                "asr_pool": self.asr_pool_config,
                "tts": self.tts_config,
                "llm": self.llm_config,
                "circuit_breaker": self.circuit_breaker_config
            }
        }
    
    async def cleanup(self) -> None:
        """清理资源"""
        await self.stop_health_monitoring()
        
        # 清空活跃连接
        for connections in self.active_connections.values():
            connections.clear()
        
        self.logger.info(f"[{self.tag}] 服务连接管理器已清理")


# 全局服务管理器字典
_service_managers: Dict[str, ESP32ServiceConnectionManager] = {}


def get_esp32_service_manager(device_id: str) -> ESP32ServiceConnectionManager:
    """
    获取ESP32服务连接管理器
    
    Args:
        device_id: 设备ID
        
    Returns:
        ESP32ServiceConnectionManager: 服务连接管理器实例
    """
    if device_id not in _service_managers:
        _service_managers[device_id] = ESP32ServiceConnectionManager(device_id)
    
    return _service_managers[device_id]


async def remove_esp32_service_manager(device_id: str) -> None:
    """
    移除ESP32服务连接管理器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _service_managers:
        manager = _service_managers[device_id]
        await manager.cleanup()
        del _service_managers[device_id]
