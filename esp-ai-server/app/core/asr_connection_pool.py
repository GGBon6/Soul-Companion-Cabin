"""
ASR连接池管理器
ASR Connection Pool Manager
提供ASR服务连接的生命周期管理、资源复用和负载均衡功能
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import threading

from app.core import logger
from app.core.config import settings


class ASRConnectionState(Enum):
    """ASR连接状态枚举"""
    IDLE = "idle"  # 空闲可用
    BUSY = "busy"  # 正在使用
    UNHEALTHY = "unhealthy"  # 不健康
    CLOSED = "closed"  # 已关闭


@dataclass
class ASRConnectionInfo:
    """ASR连接信息"""
    connection_id: str
    client_type: str  # "esp32" 或 "web"
    client_id: Optional[str] = None  # 客户端唯一标识
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    state: ASRConnectionState = ASRConnectionState.IDLE
    use_count: int = 0  # 使用次数
    error_count: int = 0  # 错误次数
    total_processing_time: float = 0.0  # 总处理时间（秒）
    metadata: Dict = field(default_factory=dict)


@dataclass
class ASRPoolMetrics:
    """ASR连接池指标"""
    total_connections: int = 0
    idle_connections: int = 0
    busy_connections: int = 0
    unhealthy_connections: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_wait_time: float = 0.0  # 总等待时间（秒）
    avg_processing_time: float = 0.0  # 平均处理时间（秒）
    connections_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_updated: datetime = field(default_factory=datetime.now)


class ASRConnectionPool:
    """ASR连接池管理器"""
    
    def __init__(
        self,
        min_connections: int = 2,
        max_connections: int = 10,
        max_idle_time: int = 300,  # 5分钟
        health_check_interval: int = 60,  # 1分钟
        acquire_timeout: float = 30.0,  # 30秒
    ):
        """
        初始化ASR连接池
        
        Args:
            min_connections: 最小连接数
            max_connections: 最大连接数
            max_idle_time: 最大空闲时间（秒）
            health_check_interval: 健康检查间隔（秒）
            acquire_timeout: 获取连接超时时间（秒）
        """
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.max_idle_time = max_idle_time
        self.health_check_interval = health_check_interval
        self.acquire_timeout = acquire_timeout
        
        # 连接池
        self.connections: Dict[str, ASRConnectionInfo] = {}
        self.idle_connections: deque = deque()  # 空闲连接队列
        self.busy_connections: Set[str] = set()  # 忙碌连接集合
        
        # 客户端连接映射
        self.client_connections: Dict[str, str] = {}  # client_id -> connection_id
        
        # 等待队列
        self.wait_queue: deque = deque()  # (client_type, client_id, future)
        
        # 指标
        self.metrics = ASRPoolMetrics()
        
        # 锁
        self._lock = asyncio.Lock()
        
        # 后台任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._started = False
        
        logger.info(f"🔧 ASR连接池初始化: min={min_connections}, max={max_connections}")
    
    async def start(self):
        """启动连接池"""
        if self._started:
            # 已经启动，静默返回（避免重复初始化时的警告日志）
            return
        
        logger.info("🚀 启动ASR连接池...")
        
        # 创建最小连接数
        for i in range(self.min_connections):
            await self._create_connection(f"init_{i}", "system")
        
        # 启动后台任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        self._started = True
        logger.info(f"✅ ASR连接池启动完成，初始连接数: {len(self.connections)}")
    
    async def stop(self):
        """停止连接池"""
        if not self._started:
            return
        
        logger.info("⏹️ 停止ASR连接池...")
        
        # 取消后台任务
        for task in [self._health_check_task, self._cleanup_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 关闭所有连接
        async with self._lock:
            for conn_id in list(self.connections.keys()):
                await self._close_connection(conn_id)
        
        self._started = False
        logger.info("✅ ASR连接池已停止")
    
    async def acquire(
        self, 
        client_type: str = "web",
        client_id: Optional[str] = None,
        timeout: Optional[float] = None
    ) -> str:
        """
        获取ASR连接
        
        Args:
            client_type: 客户端类型 ("esp32" 或 "web")
            client_id: 客户端唯一标识
            timeout: 超时时间（秒），None使用默认值
        
        Returns:
            str: 连接ID
        
        Raises:
            TimeoutError: 获取连接超时
            RuntimeError: 连接池未启动或已满
        """
        if not self._started:
            raise RuntimeError("ASR连接池未启动")
        
        timeout = timeout or self.acquire_timeout
        start_time = time.time()
        
        # 检查是否已有专属连接
        if client_id and client_id in self.client_connections:
            conn_id = self.client_connections[client_id]
            if conn_id in self.connections:
                conn_info = self.connections[conn_id]
                if conn_info.state == ASRConnectionState.IDLE:
                    return await self._acquire_connection(conn_id)
        
        # 尝试获取空闲连接
        async with self._lock:
            # 优先获取相同类型的空闲连接
            for conn_id in list(self.idle_connections):
                conn_info = self.connections.get(conn_id)
                if conn_info and conn_info.client_type == client_type:
                    self.idle_connections.remove(conn_id)
                    return await self._acquire_connection(conn_id, client_id)
            
            # 如果没有相同类型的空闲连接，创建新连接（而不是复用不同类型的连接）
            if len(self.connections) < self.max_connections:
                # 使用更精确的时间戳和计数器确保唯一性
                import random
                conn_id = f"{client_type}_{int(time.time() * 1000000)}_{random.randint(1000, 9999)}"
                await self._create_connection(conn_id, client_type)
                return await self._acquire_connection(conn_id, client_id)
            
            # 连接池已满且没有相同类型的空闲连接，尝试复用其他类型的连接
            if self.idle_connections:
                conn_id = self.idle_connections.popleft()
                # 更新连接类型以匹配当前请求
                conn_info = self.connections[conn_id]
                old_type = conn_info.client_type
                conn_info.client_type = client_type
                # 更新指标
                self.metrics.connections_by_type[old_type] -= 1
                if self.metrics.connections_by_type[old_type] <= 0:
                    del self.metrics.connections_by_type[old_type]
                self.metrics.connections_by_type[client_type] += 1
                logger.debug(f"连接 {conn_id} 类型从 {old_type} 更新为 {client_type}")
                return await self._acquire_connection(conn_id, client_id)
        
        # 连接池已满，等待空闲连接
        logger.warning(f"ASR连接池已满，等待空闲连接... (client_type={client_type})")
        future = asyncio.Future()
        self.wait_queue.append((client_type, client_id, future))
        
        try:
            conn_id = await asyncio.wait_for(future, timeout=timeout)
            wait_time = time.time() - start_time
            self.metrics.total_wait_time += wait_time
            logger.info(f"获取ASR连接成功，等待时间: {wait_time:.2f}秒")
            return conn_id
        except asyncio.TimeoutError:
            # 从等待队列中移除
            try:
                self.wait_queue.remove((client_type, client_id, future))
            except ValueError:
                pass
            raise TimeoutError(f"获取ASR连接超时 ({timeout}秒)")
    
    async def release(self, conn_id: str, success: bool = True, processing_time: float = 0.0):
        """
        释放ASR连接
        
        Args:
            conn_id: 连接ID
            success: 是否成功完成
            processing_time: 处理时间（秒）
        """
        async with self._lock:
            if conn_id not in self.connections:
                logger.warning(f"尝试释放不存在的连接: {conn_id}")
                return
            
            conn_info = self.connections[conn_id]
            
            # 更新连接信息
            conn_info.state = ASRConnectionState.IDLE
            conn_info.last_used = datetime.now()
            conn_info.use_count += 1
            conn_info.total_processing_time += processing_time
            
            if not success:
                conn_info.error_count += 1
                # 如果错误次数过多，标记为不健康
                if conn_info.error_count >= 3:
                    conn_info.state = ASRConnectionState.UNHEALTHY
                    logger.warning(f"ASR连接 {conn_id} 错误次数过多，标记为不健康")
            
            # 从忙碌集合移除
            self.busy_connections.discard(conn_id)
            
            # 更新指标
            self.metrics.total_requests += 1
            if success:
                self.metrics.successful_requests += 1
            else:
                self.metrics.failed_requests += 1
            
            # 检查是否有等待的请求
            if self.wait_queue and conn_info.state == ASRConnectionState.IDLE:
                client_type, client_id, future = self.wait_queue.popleft()
                if not future.done():
                    future.set_result(conn_id)
                    await self._acquire_connection(conn_id, client_id)
                    return
            
            # 添加到空闲队列
            if conn_info.state == ASRConnectionState.IDLE:
                self.idle_connections.append(conn_id)
            
            logger.debug(f"ASR连接已释放: {conn_id} (使用次数: {conn_info.use_count})")
    
    async def _acquire_connection(self, conn_id: str, client_id: Optional[str] = None) -> str:
        """内部方法：获取连接"""
        conn_info = self.connections[conn_id]
        conn_info.state = ASRConnectionState.BUSY
        self.busy_connections.add(conn_id)
        
        # 从空闲队列移除（如果存在）
        try:
            self.idle_connections.remove(conn_id)
        except ValueError:
            pass  # 连接可能已经不在空闲队列中
        
        # 绑定客户端
        if client_id:
            self.client_connections[client_id] = conn_id
        
        logger.debug(f"ASR连接已获取: {conn_id} (client_id={client_id})")
        return conn_id
    
    async def _create_connection(self, conn_id: str, client_type: str):
        """创建新连接"""
        conn_info = ASRConnectionInfo(
            connection_id=conn_id,
            client_type=client_type,
            state=ASRConnectionState.IDLE
        )
        
        self.connections[conn_id] = conn_info
        self.idle_connections.append(conn_id)
        
        # 更新指标
        self.metrics.total_connections = len(self.connections)
        self.metrics.connections_by_type[client_type] += 1
        
        logger.debug(f"创建ASR连接: {conn_id} (类型: {client_type})")
    
    async def _close_connection(self, conn_id: str):
        """关闭连接"""
        if conn_id not in self.connections:
            return
        
        conn_info = self.connections[conn_id]
        conn_info.state = ASRConnectionState.CLOSED
        
        # 从各个集合中移除
        try:
            self.idle_connections.remove(conn_id)
        except ValueError:
            pass
        self.busy_connections.discard(conn_id)
        
        # 从客户端映射中移除
        for client_id, cid in list(self.client_connections.items()):
            if cid == conn_id:
                del self.client_connections[client_id]
        
        # 删除连接
        client_type = conn_info.client_type
        del self.connections[conn_id]
        
        # 更新指标
        self.metrics.total_connections = len(self.connections)
        self.metrics.connections_by_type[client_type] -= 1
        if self.metrics.connections_by_type[client_type] <= 0:
            del self.metrics.connections_by_type[client_type]
        
        logger.debug(f"关闭ASR连接: {conn_id}")
    
    async def _health_check_loop(self):
        """健康检查循环"""
        logger.info("🏥 启动ASR连接池健康检查循环")
        
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._perform_health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ ASR健康检查循环异常: {e}", exc_info=True)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        logger.debug("🏥 执行ASR连接池健康检查...")
        
        now = datetime.now()
        unhealthy_connections = []
        
        async with self._lock:
            for conn_id, conn_info in self.connections.items():
                # 检查空闲超时
                if (conn_info.state == ASRConnectionState.IDLE and
                    now - conn_info.last_used > timedelta(seconds=self.max_idle_time)):
                    
                    # 保持最小连接数
                    if len(self.connections) > self.min_connections:
                        unhealthy_connections.append(conn_id)
                        logger.debug(f"ASR连接空闲超时: {conn_id}")
                
                # 检查不健康连接
                elif conn_info.state == ASRConnectionState.UNHEALTHY:
                    unhealthy_connections.append(conn_id)
            
            # 移除不健康的连接
            for conn_id in unhealthy_connections:
                await self._close_connection(conn_id)
            
            # 确保最小连接数
            while len(self.connections) < self.min_connections:
                conn_id = f"health_check_{int(time.time() * 1000)}"
                await self._create_connection(conn_id, "system")
        
        if unhealthy_connections:
            logger.info(f"🏥 健康检查完成，移除 {len(unhealthy_connections)} 个连接")
    
    async def _cleanup_loop(self):
        """清理循环"""
        logger.info("🧹 启动ASR连接池清理循环")
        
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                await self._cleanup_stale_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ ASR清理循环异常: {e}", exc_info=True)
    
    async def _cleanup_stale_data(self):
        """清理过期数据"""
        async with self._lock:
            # 清理过期的客户端映射
            expired_clients = []
            for client_id, conn_id in self.client_connections.items():
                if conn_id not in self.connections:
                    expired_clients.append(client_id)
            
            for client_id in expired_clients:
                del self.client_connections[client_id]
            
            if expired_clients:
                logger.debug(f"清理 {len(expired_clients)} 个过期客户端映射")
    
    def get_metrics(self) -> ASRPoolMetrics:
        """获取连接池指标"""
        self.metrics.total_connections = len(self.connections)
        self.metrics.idle_connections = len(self.idle_connections)
        self.metrics.busy_connections = len(self.busy_connections)
        self.metrics.unhealthy_connections = len([
            c for c in self.connections.values() 
            if c.state == ASRConnectionState.UNHEALTHY
        ])
        
        # 计算平均处理时间
        total_time = sum(c.total_processing_time for c in self.connections.values())
        total_uses = sum(c.use_count for c in self.connections.values())
        self.metrics.avg_processing_time = total_time / total_uses if total_uses > 0 else 0.0
        
        self.metrics.last_updated = datetime.now()
        return self.metrics
    
    def get_connection_info(self, conn_id: str) -> Optional[ASRConnectionInfo]:
        """获取连接信息"""
        return self.connections.get(conn_id)
    
    def get_stats(self) -> Dict:
        """获取连接池统计信息"""
        metrics = self.get_metrics()
        return {
            "total_connections": metrics.total_connections,
            "idle_connections": metrics.idle_connections,
            "busy_connections": metrics.busy_connections,
            "unhealthy_connections": metrics.unhealthy_connections,
            "total_requests": metrics.total_requests,
            "successful_requests": metrics.successful_requests,
            "failed_requests": metrics.failed_requests,
            "success_rate": (
                metrics.successful_requests / metrics.total_requests * 100
                if metrics.total_requests > 0 else 0.0
            ),
            "avg_processing_time": metrics.avg_processing_time,
            "avg_wait_time": (
                metrics.total_wait_time / metrics.total_requests
                if metrics.total_requests > 0 else 0.0
            ),
            "connections_by_type": dict(metrics.connections_by_type),
            "wait_queue_size": len(self.wait_queue),
        }


# 全局ASR连接池实例
_asr_connection_pool: Optional[ASRConnectionPool] = None


def get_asr_connection_pool() -> ASRConnectionPool:
    """获取ASR连接池实例"""
    global _asr_connection_pool
    if _asr_connection_pool is None:
        # 从配置读取参数
        min_conn = getattr(settings, 'ASR_POOL_MIN_CONNECTIONS', 2)
        max_conn = getattr(settings, 'ASR_POOL_MAX_CONNECTIONS', 10)
        max_idle = getattr(settings, 'ASR_POOL_MAX_IDLE_TIME', 300)
        health_interval = getattr(settings, 'ASR_POOL_HEALTH_CHECK_INTERVAL', 60)
        acquire_timeout = getattr(settings, 'ASR_POOL_ACQUIRE_TIMEOUT', 30.0)
        
        _asr_connection_pool = ASRConnectionPool(
            min_connections=min_conn,
            max_connections=max_conn,
            max_idle_time=max_idle,
            health_check_interval=health_interval,
            acquire_timeout=acquire_timeout
        )
    return _asr_connection_pool


async def initialize_asr_connection_pool():
    """初始化ASR连接池"""
    pool = get_asr_connection_pool()
    await pool.start()
    return pool


async def shutdown_asr_connection_pool():
    """关闭ASR连接池"""
    global _asr_connection_pool
    if _asr_connection_pool:
        await _asr_connection_pool.stop()
        _asr_connection_pool = None
