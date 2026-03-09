"""
分布式连接池管理
Distributed Connection Pool Management
提供跨服务器实例的连接池状态同步和负载均衡
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, asdict
from enum import Enum

from app.core import logger, settings
from .redis_manager import get_redis_manager


@dataclass
class ServerInstance:
    """服务器实例信息"""
    instance_id: str
    host: str
    port: int
    start_time: datetime
    last_heartbeat: datetime
    connection_count: int = 0
    max_connections: int = 1000
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    status: str = "active"
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['start_time'] = self.start_time.isoformat()
        data['last_heartbeat'] = self.last_heartbeat.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServerInstance':
        """从字典创建"""
        if 'start_time' in data and isinstance(data['start_time'], str):
            data['start_time'] = datetime.fromisoformat(data['start_time'])
        if 'last_heartbeat' in data and isinstance(data['last_heartbeat'], str):
            data['last_heartbeat'] = datetime.fromisoformat(data['last_heartbeat'])
        return cls(**data)
    
    @property
    def load_factor(self) -> float:
        """计算负载因子"""
        if self.max_connections == 0:
            return 1.0
        connection_load = self.connection_count / self.max_connections
        cpu_load = self.cpu_usage / 100.0
        memory_load = self.memory_usage / 100.0
        return (connection_load * 0.5 + cpu_load * 0.3 + memory_load * 0.2)
    
    @property
    def is_healthy(self) -> bool:
        """检查实例是否健康"""
        if self.status != "active":
            return False
        
        # 检查心跳超时
        heartbeat_timeout = timedelta(seconds=60)  # 60秒心跳超时
        if datetime.now() - self.last_heartbeat > heartbeat_timeout:
            return False
        
        # 检查负载
        if self.load_factor > 0.95:  # 95%负载阈值
            return False
        
        return True


@dataclass
class ConnectionDistribution:
    """连接分布统计"""
    total_connections: int = 0
    total_capacity: int = 0
    active_instances: int = 0
    instance_stats: Dict[str, Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.instance_stats is None:
            self.instance_stats = {}
    
    @property
    def utilization_rate(self) -> float:
        """计算总体利用率"""
        if self.total_capacity == 0:
            return 0.0
        return self.total_connections / self.total_capacity
    
    @property
    def average_load(self) -> float:
        """计算平均负载"""
        if not self.instance_stats:
            return 0.0
        
        total_load = sum(stats.get('load_factor', 0) for stats in self.instance_stats.values())
        return total_load / len(self.instance_stats)


class DistributedConnectionPool:
    """分布式连接池管理器"""
    
    def __init__(self):
        """初始化分布式连接池"""
        self.redis_manager = get_redis_manager()
        self.instance_id = f"server_{int(time.time())}_{id(self)}"
        
        # 本实例信息
        self.local_instance = ServerInstance(
            instance_id=self.instance_id,
            host=settings.HOST,
            port=settings.PORT,
            start_time=datetime.now(),
            last_heartbeat=datetime.now(),
            max_connections=settings.MAX_CONNECTIONS
        )
        
        # 后台任务
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._discovery_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 其他实例缓存
        self.known_instances: Dict[str, ServerInstance] = {}
        
        # 配置
        self.heartbeat_interval = 30  # 心跳间隔(秒)
        self.discovery_interval = 60  # 发现间隔(秒)
        self.cleanup_interval = 120  # 清理间隔(秒)
        
        logger.info(f"🔧 分布式连接池初始化完成 (实例: {self.instance_id})")
    
    async def start(self):
        """启动分布式连接池"""
        if not settings.ENABLE_REDIS or not self.redis_manager.is_connected():
            logger.info("⏸️ 分布式连接池已禁用或Redis未连接")
            return
        
        logger.info("🚀 启动分布式连接池管理...")
        
        self._running = True
        
        # 注册本实例
        await self._register_instance()
        
        # 启动后台任务
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("✅ 分布式连接池管理启动完成")
    
    async def stop(self):
        """停止分布式连接池"""
        logger.info("⏹️ 停止分布式连接池管理...")
        
        self._running = False
        
        # 取消后台任务
        tasks = [self._heartbeat_task, self._discovery_task, self._cleanup_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 注销本实例
        await self._unregister_instance()
        
        logger.info("✅ 分布式连接池管理已停止")
    
    async def update_connection_count(self, count: int):
        """更新连接数"""
        try:
            self.local_instance.connection_count = count
            self.local_instance.last_heartbeat = datetime.now()
            
            # 同步到Redis
            await self._sync_instance_info()
            
        except Exception as e:
            logger.error(f"❌ 更新连接数失败: {e}")
    
    async def update_system_metrics(self, cpu_usage: float, memory_usage: float):
        """更新系统指标"""
        try:
            self.local_instance.cpu_usage = cpu_usage
            self.local_instance.memory_usage = memory_usage
            self.local_instance.last_heartbeat = datetime.now()
            
        except Exception as e:
            logger.error(f"❌ 更新系统指标失败: {e}")
    
    async def get_best_instance(self, exclude_current: bool = True) -> Optional[ServerInstance]:
        """获取最佳实例（负载最低）"""
        try:
            await self._refresh_instances()
            
            candidates = []
            for instance in self.known_instances.values():
                if not instance.is_healthy:
                    continue
                if exclude_current and instance.instance_id == self.instance_id:
                    continue
                candidates.append(instance)
            
            if not candidates:
                return None
            
            # 按负载因子排序，选择负载最低的
            candidates.sort(key=lambda x: x.load_factor)
            return candidates[0]
            
        except Exception as e:
            logger.error(f"❌ 获取最佳实例失败: {e}")
            return None
    
    async def get_all_instances(self) -> List[ServerInstance]:
        """获取所有实例"""
        try:
            await self._refresh_instances()
            return list(self.known_instances.values())
            
        except Exception as e:
            logger.error(f"❌ 获取所有实例失败: {e}")
            return []
    
    async def get_healthy_instances(self) -> List[ServerInstance]:
        """获取健康的实例"""
        try:
            all_instances = await self.get_all_instances()
            return [instance for instance in all_instances if instance.is_healthy]
            
        except Exception as e:
            logger.error(f"❌ 获取健康实例失败: {e}")
            return []
    
    async def get_connection_distribution(self) -> ConnectionDistribution:
        """获取连接分布统计"""
        try:
            healthy_instances = await self.get_healthy_instances()
            
            distribution = ConnectionDistribution()
            distribution.active_instances = len(healthy_instances)
            
            for instance in healthy_instances:
                distribution.total_connections += instance.connection_count
                distribution.total_capacity += instance.max_connections
                
                distribution.instance_stats[instance.instance_id] = {
                    'host': instance.host,
                    'port': instance.port,
                    'connections': instance.connection_count,
                    'max_connections': instance.max_connections,
                    'load_factor': instance.load_factor,
                    'cpu_usage': instance.cpu_usage,
                    'memory_usage': instance.memory_usage,
                    'status': instance.status
                }
            
            return distribution
            
        except Exception as e:
            logger.error(f"❌ 获取连接分布失败: {e}")
            return ConnectionDistribution()
    
    async def should_accept_connection(self) -> bool:
        """判断是否应该接受新连接（负载均衡）"""
        try:
            # 检查本实例负载
            if self.local_instance.load_factor > 0.8:  # 80%负载阈值
                # 检查是否有更好的实例
                best_instance = await self.get_best_instance()
                if best_instance and best_instance.load_factor < self.local_instance.load_factor:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 判断连接接受失败: {e}")
            return True  # 默认接受
    
    async def get_redirect_instance(self) -> Optional[Dict[str, Any]]:
        """获取重定向实例信息"""
        try:
            best_instance = await self.get_best_instance()
            if best_instance:
                return {
                    'host': best_instance.host,
                    'port': best_instance.port,
                    'load_factor': best_instance.load_factor
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取重定向实例失败: {e}")
            return None
    
    async def _register_instance(self):
        """注册实例"""
        try:
            key = self._build_instance_key(self.instance_id)
            await self.redis_manager.set_json(key, self.local_instance.to_dict(), 
                                            ex=self.heartbeat_interval * 3)
            
            logger.info(f"📝 注册服务器实例: {self.instance_id}")
            
        except Exception as e:
            logger.error(f"❌ 注册实例失败: {e}")
    
    async def _unregister_instance(self):
        """注销实例"""
        try:
            key = self._build_instance_key(self.instance_id)
            await self.redis_manager.delete(key)
            
            logger.info(f"🗑️ 注销服务器实例: {self.instance_id}")
            
        except Exception as e:
            logger.error(f"❌ 注销实例失败: {e}")
    
    async def _sync_instance_info(self):
        """同步实例信息到Redis"""
        try:
            key = self._build_instance_key(self.instance_id)
            await self.redis_manager.set_json(key, self.local_instance.to_dict(), 
                                            ex=self.heartbeat_interval * 3)
            
        except Exception as e:
            logger.error(f"❌ 同步实例信息失败: {e}")
    
    async def _refresh_instances(self):
        """刷新实例列表"""
        try:
            pattern = self._build_instance_key("*")
            keys = await self.redis_manager.execute_command('keys', pattern)
            
            current_instances = {}
            for key in keys:
                try:
                    data = await self.redis_manager.get_json(key.replace(f"{settings.REDIS_KEY_PREFIX}:", ""))
                    if data:
                        instance = ServerInstance.from_dict(data)
                        current_instances[instance.instance_id] = instance
                except Exception as e:
                    logger.debug(f"解析实例信息失败 {key}: {e}")
            
            self.known_instances = current_instances
            
        except Exception as e:
            logger.error(f"❌ 刷新实例列表失败: {e}")
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        logger.info("💓 启动分布式连接池心跳循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 心跳循环异常: {e}", exc_info=True)
    
    async def _send_heartbeat(self):
        """发送心跳"""
        try:
            self.local_instance.last_heartbeat = datetime.now()
            await self._sync_instance_info()
            
            logger.debug(f"💓 发送心跳: {self.instance_id}")
            
        except Exception as e:
            logger.error(f"❌ 发送心跳失败: {e}")
    
    async def _discovery_loop(self):
        """实例发现循环"""
        logger.info("🔍 启动实例发现循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.discovery_interval)
                await self._discover_instances()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 实例发现循环异常: {e}", exc_info=True)
    
    async def _discover_instances(self):
        """发现其他实例"""
        try:
            await self._refresh_instances()
            
            healthy_count = len([i for i in self.known_instances.values() if i.is_healthy])
            total_count = len(self.known_instances)
            
            logger.debug(f"🔍 发现实例: 总数={total_count}, 健康={healthy_count}")
            
        except Exception as e:
            logger.error(f"❌ 发现实例失败: {e}")
    
    async def _cleanup_loop(self):
        """清理循环"""
        logger.info("🧹 启动实例清理循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_dead_instances()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 实例清理循环异常: {e}", exc_info=True)
    
    async def _cleanup_dead_instances(self):
        """清理死实例"""
        try:
            await self._refresh_instances()
            
            dead_instances = []
            for instance_id, instance in self.known_instances.items():
                if not instance.is_healthy:
                    dead_instances.append(instance_id)
            
            # 删除死实例
            for instance_id in dead_instances:
                try:
                    key = self._build_instance_key(instance_id)
                    await self.redis_manager.delete(key)
                    logger.debug(f"🧹 清理死实例: {instance_id}")
                except Exception as e:
                    logger.warning(f"⚠️ 清理实例失败 {instance_id}: {e}")
            
            if dead_instances:
                logger.info(f"🧹 清理了 {len(dead_instances)} 个死实例")
                
        except Exception as e:
            logger.error(f"❌ 清理死实例失败: {e}")
    
    def _build_instance_key(self, instance_id: str) -> str:
        """构建实例键名"""
        return f"server_instance:{instance_id}"
    
    def get_local_instance_info(self) -> Dict[str, Any]:
        """获取本地实例信息"""
        return self.local_instance.to_dict()


# 全局分布式连接池实例
_distributed_pool: Optional[DistributedConnectionPool] = None


def get_distributed_pool() -> DistributedConnectionPool:
    """获取分布式连接池实例"""
    global _distributed_pool
    if _distributed_pool is None:
        _distributed_pool = DistributedConnectionPool()
    return _distributed_pool


async def initialize_distributed_pool():
    """初始化分布式连接池"""
    pool = get_distributed_pool()
    await pool.start()
    return pool


async def shutdown_distributed_pool():
    """关闭分布式连接池"""
    global _distributed_pool
    if _distributed_pool:
        await _distributed_pool.stop()
        _distributed_pool = None
