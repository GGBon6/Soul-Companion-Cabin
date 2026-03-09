"""
Redis连接管理器
Redis Connection Manager
提供Redis连接池管理、连接健康检查和故障恢复功能
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass
from enum import Enum
import redis.asyncio as redis
from redis.asyncio import ConnectionPool
from redis.exceptions import ConnectionError, TimeoutError, RedisError

from app.core import logger, settings


class RedisConnectionState(Enum):
    """Redis连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


@dataclass
class RedisMetrics:
    """Redis指标"""
    connection_state: RedisConnectionState = RedisConnectionState.DISCONNECTED
    total_commands: int = 0
    successful_commands: int = 0
    failed_commands: int = 0
    connection_errors: int = 0
    last_ping_time: Optional[datetime] = None
    last_error: Optional[str] = None
    uptime_seconds: float = 0.0
    memory_usage: Optional[Dict[str, Any]] = None


class RedisManager:
    """Redis连接管理器"""
    
    def __init__(self):
        """初始化Redis管理器"""
        self.pool: Optional[ConnectionPool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.metrics = RedisMetrics()
        self.start_time = time.time()
        
        # 健康检查任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 重连配置
        self.max_retries = 3
        self.retry_delay = 1.0
        self.backoff_factor = 2.0
        
        logger.info("🔧 Redis管理器初始化完成")
    
    async def start(self) -> bool:
        """启动Redis连接"""
        if not settings.ENABLE_REDIS:
            logger.info("⏸️ Redis功能已禁用")
            return False
        
        logger.info("🚀 启动Redis连接管理器...")
        
        try:
            # 创建连接池
            await self._create_connection_pool()
            
            # 创建Redis客户端
            self.redis_client = redis.Redis(connection_pool=self.pool)
            
            # 测试连接
            await self._test_connection()
            
            # 启动健康检查
            self._running = True
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            self.metrics.connection_state = RedisConnectionState.CONNECTED
            logger.info("✅ Redis连接管理器启动成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ Redis连接管理器启动失败: {e}", exc_info=True)
            self.metrics.connection_state = RedisConnectionState.ERROR
            self.metrics.last_error = str(e)
            self.metrics.connection_errors += 1
            return False
    
    async def stop(self):
        """停止Redis连接"""
        logger.info("⏹️ 停止Redis连接管理器...")
        
        self._running = False
        
        # 停止健康检查任务
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # 关闭Redis连接
        if self.redis_client:
            try:
                await self.redis_client.close()
            except Exception as e:
                logger.warning(f"⚠️ 关闭Redis客户端异常: {e}")
        
        # 关闭连接池
        if self.pool:
            try:
                await self.pool.disconnect()
            except Exception as e:
                logger.warning(f"⚠️ 关闭Redis连接池异常: {e}")
        
        self.metrics.connection_state = RedisConnectionState.DISCONNECTED
        logger.info("✅ Redis连接管理器已停止")
    
    async def _create_connection_pool(self):
        """创建Redis连接池"""
        try:
            # 构建连接参数
            connection_kwargs = {
                'max_connections': settings.REDIS_MAX_CONNECTIONS,
                'socket_timeout': settings.REDIS_SOCKET_TIMEOUT,
                'socket_connect_timeout': settings.REDIS_CONNECTION_TIMEOUT,
                'retry_on_timeout': settings.REDIS_RETRY_ON_TIMEOUT,
                'health_check_interval': 30,
            }
            
            # 使用Redis URL或单独的参数
            if settings.REDIS_URL:
                self.pool = ConnectionPool.from_url(
                    settings.REDIS_URL,
                    **connection_kwargs
                )
                logger.info(f"📡 使用Redis URL创建连接池: {settings.REDIS_URL}")
            else:
                connection_kwargs.update({
                    'host': settings.REDIS_HOST,
                    'port': settings.REDIS_PORT,
                    'db': settings.REDIS_DB,
                })
                
                if settings.REDIS_PASSWORD:
                    connection_kwargs['password'] = settings.REDIS_PASSWORD
                if settings.REDIS_USERNAME:
                    connection_kwargs['username'] = settings.REDIS_USERNAME
                
                self.pool = ConnectionPool(**connection_kwargs)
                logger.info(f"📡 创建Redis连接池: {settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}")
            
        except Exception as e:
            logger.error(f"❌ 创建Redis连接池失败: {e}")
            raise
    
    async def _test_connection(self):
        """测试Redis连接"""
        try:
            # 执行ping命令测试连接
            result = await asyncio.wait_for(
                self.redis_client.ping(),
                timeout=settings.REDIS_PING_TIMEOUT
            )
            
            if result:
                self.metrics.last_ping_time = datetime.now()
                logger.info("✅ Redis连接测试成功")
            else:
                raise ConnectionError("Redis ping失败")
                
        except Exception as e:
            logger.error(f"❌ Redis连接测试失败: {e}")
            raise
    
    async def _health_check_loop(self):
        """健康检查循环"""
        logger.info("🏥 启动Redis健康检查循环")
        
        while self._running:
            try:
                await asyncio.sleep(settings.REDIS_HEALTH_CHECK_INTERVAL)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Redis健康检查循环异常: {e}", exc_info=True)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        try:
            # 执行ping命令
            start_time = time.time()
            result = await asyncio.wait_for(
                self.redis_client.ping(),
                timeout=settings.REDIS_PING_TIMEOUT
            )
            ping_time = time.time() - start_time
            
            if result:
                self.metrics.last_ping_time = datetime.now()
                self.metrics.connection_state = RedisConnectionState.CONNECTED
                logger.debug(f"🏥 Redis健康检查成功 (延迟: {ping_time:.3f}s)")
                
                # 获取Redis信息
                await self._collect_redis_info()
            else:
                raise ConnectionError("Redis ping返回False")
                
        except Exception as e:
            logger.warning(f"⚠️ Redis健康检查失败: {e}")
            self.metrics.connection_state = RedisConnectionState.ERROR
            self.metrics.last_error = str(e)
            self.metrics.connection_errors += 1
            
            # 尝试重连
            if self._running:
                await self._attempt_reconnect()
    
    async def _collect_redis_info(self):
        """收集Redis信息"""
        try:
            info = await self.redis_client.info('memory')
            self.metrics.memory_usage = {
                'used_memory': info.get('used_memory', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'used_memory_peak': info.get('used_memory_peak', 0),
                'used_memory_peak_human': info.get('used_memory_peak_human', '0B'),
            }
            self.metrics.uptime_seconds = time.time() - self.start_time
        except Exception as e:
            logger.debug(f"收集Redis信息失败: {e}")
    
    async def _attempt_reconnect(self):
        """尝试重连"""
        if self.metrics.connection_state == RedisConnectionState.RECONNECTING:
            return  # 已在重连中
        
        self.metrics.connection_state = RedisConnectionState.RECONNECTING
        logger.info("🔄 尝试重连Redis...")
        
        for attempt in range(self.max_retries):
            try:
                # 等待重连延迟
                delay = self.retry_delay * (self.backoff_factor ** attempt)
                await asyncio.sleep(delay)
                
                # 重新创建连接
                await self._create_connection_pool()
                self.redis_client = redis.Redis(connection_pool=self.pool)
                await self._test_connection()
                
                self.metrics.connection_state = RedisConnectionState.CONNECTED
                logger.info(f"✅ Redis重连成功 (尝试 {attempt + 1}/{self.max_retries})")
                return
                
            except Exception as e:
                logger.warning(f"⚠️ Redis重连失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    self.metrics.connection_state = RedisConnectionState.ERROR
                    self.metrics.last_error = f"重连失败: {e}"
    
    async def execute_command(self, command: str, *args, **kwargs) -> Any:
        """执行Redis命令"""
        if not self.is_connected():
            raise ConnectionError("Redis未连接")
        
        try:
            self.metrics.total_commands += 1
            
            # 获取Redis客户端方法
            method = getattr(self.redis_client, command.lower())
            if not method:
                raise AttributeError(f"Redis命令不存在: {command}")
            
            # 执行命令
            result = await method(*args, **kwargs)
            self.metrics.successful_commands += 1
            return result
            
        except Exception as e:
            self.metrics.failed_commands += 1
            logger.error(f"❌ Redis命令执行失败 {command}: {e}")
            raise
    
    async def get(self, key: str) -> Optional[str]:
        """获取键值"""
        result = await self.execute_command('get', self._build_key(key))
        if result is None:
            return None
        # 如果结果是字节对象，解码为字符串
        if isinstance(result, bytes):
            return result.decode('utf-8')
        return str(result)
    
    async def set(self, key: str, value: Union[str, bytes, int, float], 
                 ex: Optional[int] = None, px: Optional[int] = None,
                 nx: bool = False, xx: bool = False) -> bool:
        """设置键值"""
        return await self.execute_command('set', self._build_key(key), value, 
                                        ex=ex, px=px, nx=nx, xx=xx)
    
    async def delete(self, *keys: str) -> int:
        """删除键"""
        prefixed_keys = [self._build_key(key) for key in keys]
        return await self.execute_command('delete', *prefixed_keys)
    
    async def exists(self, *keys: str) -> int:
        """检查键是否存在"""
        prefixed_keys = [self._build_key(key) for key in keys]
        return await self.execute_command('exists', *prefixed_keys)
    
    async def expire(self, key: str, time: int) -> bool:
        """设置键过期时间"""
        return await self.execute_command('expire', self._build_key(key), time)
    
    async def ttl(self, key: str) -> int:
        """获取键剩余生存时间"""
        return await self.execute_command('ttl', self._build_key(key))
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        """获取哈希字段值"""
        return await self.execute_command('hget', self._build_key(name), key)
    
    async def hset(self, name: str, key: str, value: Union[str, bytes, int, float]) -> int:
        """设置哈希字段值"""
        return await self.execute_command('hset', self._build_key(name), key, value)
    
    async def hgetall(self, name: str) -> Dict[str, str]:
        """获取哈希所有字段"""
        return await self.execute_command('hgetall', self._build_key(name))
    
    async def hdel(self, name: str, *keys: str) -> int:
        """删除哈希字段"""
        return await self.execute_command('hdel', self._build_key(name), *keys)
    
    async def sadd(self, name: str, *values: Union[str, bytes, int, float]) -> int:
        """添加集合成员"""
        return await self.execute_command('sadd', self._build_key(name), *values)
    
    async def srem(self, name: str, *values: Union[str, bytes, int, float]) -> int:
        """移除集合成员"""
        return await self.execute_command('srem', self._build_key(name), *values)
    
    async def smembers(self, name: str) -> set:
        """获取集合所有成员"""
        return await self.execute_command('smembers', self._build_key(name))
    
    async def sismember(self, name: str, value: Union[str, bytes, int, float]) -> bool:
        """检查是否为集合成员"""
        return await self.execute_command('sismember', self._build_key(name), value)
    
    async def publish(self, channel: str, message: Union[str, bytes]) -> int:
        """发布消息到频道"""
        return await self.execute_command('publish', self._build_key(channel), message)
    
    async def set_json(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """设置JSON值"""
        json_value = json.dumps(value, ensure_ascii=False)
        return await self.set(key, json_value, ex=ex)
    
    async def get_json(self, key: str) -> Optional[Any]:
        """获取JSON值"""
        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON解析失败 {key}: {e}")
            return None
    
    def _build_key(self, key: str) -> str:
        """构建带前缀的键名"""
        return f"{settings.REDIS_KEY_PREFIX}:{key}"
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return (self.metrics.connection_state == RedisConnectionState.CONNECTED and 
                self.redis_client is not None)
    
    def get_metrics(self) -> RedisMetrics:
        """获取Redis指标"""
        return self.metrics
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        info = {
            'state': self.metrics.connection_state.value,
            'total_commands': self.metrics.total_commands,
            'successful_commands': self.metrics.successful_commands,
            'failed_commands': self.metrics.failed_commands,
            'connection_errors': self.metrics.connection_errors,
            'uptime_seconds': self.metrics.uptime_seconds,
            'last_ping': self.metrics.last_ping_time.isoformat() if self.metrics.last_ping_time else None,
            'last_error': self.metrics.last_error,
        }
        
        if self.metrics.memory_usage:
            info['memory_usage'] = self.metrics.memory_usage
        
        return info


# 全局Redis管理器实例
_redis_manager: Optional[RedisManager] = None


def get_redis_manager() -> RedisManager:
    """获取Redis管理器实例"""
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = RedisManager()
    return _redis_manager


async def initialize_redis_manager() -> bool:
    """初始化Redis管理器"""
    manager = get_redis_manager()
    return await manager.start()


async def shutdown_redis_manager():
    """关闭Redis管理器"""
    global _redis_manager
    if _redis_manager:
        await _redis_manager.stop()
        _redis_manager = None
