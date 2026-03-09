"""
服务池 - 为不同客户端类型提供独立的服务实例
Service Pool - Dedicated Service Instances for Different Client Types
"""
from typing import Dict, Optional, Type, Callable, Any
from dataclasses import dataclass
import asyncio
from app.core import logger


@dataclass
class ServicePoolConfig:
    """服务池配置"""
    min_instances: int = 1  # 最小实例数
    max_instances: int = 10  # 最大实例数
    instance_per_client_type: bool = True  # 每个客户端类型独立实例
    enable_health_check: bool = True  # 启用健康检查
    health_check_interval: int = 60  # 健康检查间隔（秒）


class ServicePool:
    """
    服务池 - 管理多个服务实例
    
    特点：
    - ESP32设备使用专用实例（优化配置）
    - Web端使用专用实例（高并发配置）
    - 自动健康检查和实例替换
    - 支持实例预热和延迟创建
    """
    
    def __init__(
        self, 
        service_class: Type,
        config: ServicePoolConfig,
        config_factory: Optional[Callable[[str], Any]] = None
    ):
        """
        初始化服务池
        
        Args:
            service_class: 服务类
            config: 服务池配置
            config_factory: 配置工厂函数，接收client_type返回服务配置
        """
        self.service_class = service_class
        self.config = config
        self.config_factory = config_factory
        
        # 客户端类型 -> 服务实例
        self.instances: Dict[str, Any] = {}
        
        # 实例健康状态
        self.health_status: Dict[str, bool] = {}
        
        # 初始化锁
        self._locks: Dict[str, asyncio.Lock] = {}
        
        # 健康检查任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            f"✅ 服务池初始化: {service_class.__name__} "
            f"(min={config.min_instances}, max={config.max_instances})"
        )
    
    async def start(self):
        """启动服务池"""
        self._running = True
        
        # 启动健康检查
        if self.config.enable_health_check:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info(f"🏥 启动健康检查 (interval={self.config.health_check_interval}s)")
    
    async def stop(self):
        """停止服务池"""
        self._running = False
        
        # 停止健康检查
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
    
    async def get_instance(self, client_type: str = 'default') -> Any:
        """
        获取服务实例
        
        Args:
            client_type: 客户端类型 ('esp32', 'web', 'system', 'default')
        
        Returns:
            服务实例
        """
        # 如果实例不存在，创建它
        if client_type not in self.instances:
            await self._create_instance(client_type)
        
        # 检查实例健康状态
        if not self.health_status.get(client_type, False):
            logger.warning(f"⚠️ 服务实例不健康，重新创建: {client_type}")
            await self._create_instance(client_type)
        
        return self.instances[client_type]
    
    async def _create_instance(self, client_type: str):
        """创建服务实例"""
        # 获取锁，避免重复创建
        if client_type not in self._locks:
            self._locks[client_type] = asyncio.Lock()
        
        async with self._locks[client_type]:
            # 双重检查
            if client_type in self.instances and self.health_status.get(client_type, False):
                return
            
            try:
                # 获取配置
                if self.config_factory:
                    service_config = self.config_factory(client_type)
                else:
                    service_config = None
                
                # 创建实例
                if service_config:
                    instance = self.service_class(service_config)
                else:
                    instance = self.service_class()
                
                # 如果有异步初始化方法，调用它
                if hasattr(instance, 'initialize'):
                    await instance.initialize()
                
                self.instances[client_type] = instance
                self.health_status[client_type] = True
                
                logger.info(
                    f"✅ 创建服务实例: {self.service_class.__name__} "
                    f"(client_type={client_type})"
                )
                
            except Exception as e:
                logger.error(f"❌ 创建服务实例失败 (client_type={client_type}): {e}")
                self.health_status[client_type] = False
                raise
    
    async def _health_check_loop(self):
        """健康检查循环"""
        logger.info("🏥 启动服务池健康检查循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 健康检查循环异常: {e}", exc_info=True)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        for client_type, instance in list(self.instances.items()):
            try:
                # 如果实例有health_check方法，调用它
                if hasattr(instance, 'health_check'):
                    is_healthy = await instance.health_check()
                    self.health_status[client_type] = is_healthy
                    
                    if not is_healthy:
                        logger.warning(
                            f"⚠️ 服务实例健康检查失败: {client_type}, "
                            f"将在下次请求时重新创建"
                        )
                else:
                    # 没有health_check方法，默认认为健康
                    self.health_status[client_type] = True
                    
            except Exception as e:
                logger.error(f"❌ 健康检查失败 (client_type={client_type}): {e}")
                self.health_status[client_type] = False
    
    async def shutdown_all(self):
        """关闭所有实例"""
        logger.info(f"⏹️ 关闭服务池: {self.service_class.__name__}")
        
        # 停止健康检查
        await self.stop()
        
        # 关闭所有实例
        for client_type, instance in list(self.instances.items()):
            try:
                if hasattr(instance, 'shutdown'):
                    await instance.shutdown()
                logger.info(f"✅ 关闭服务实例: {client_type}")
            except Exception as e:
                logger.error(f"❌ 关闭服务实例失败 (client_type={client_type}): {e}")
        
        self.instances.clear()
        self.health_status.clear()
        logger.info(f"✅ 服务池已关闭: {self.service_class.__name__}")
    
    def get_stats(self) -> Dict:
        """获取服务池统计信息"""
        return {
            'service_class': self.service_class.__name__,
            'total_instances': len(self.instances),
            'healthy_instances': sum(1 for h in self.health_status.values() if h),
            'client_types': list(self.instances.keys()),
            'health_status': self.health_status.copy()
        }
