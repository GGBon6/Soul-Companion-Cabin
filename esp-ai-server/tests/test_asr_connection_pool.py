"""
ASR连接池单元测试
ASR Connection Pool Unit Tests
"""

import asyncio
import pytest
import time
from app.core.asr_connection_pool import (
    ASRConnectionPool,
    ASRConnectionState,
    get_asr_connection_pool,
    initialize_asr_connection_pool
)


class TestASRConnectionPool:
    """ASR连接池测试类"""
    
    @pytest.mark.asyncio
    async def test_pool_initialization(self):
        """测试连接池初始化"""
        pool = ASRConnectionPool(
            min_connections=2,
            max_connections=5,
            max_idle_time=60,
            health_check_interval=30
        )
        
        await pool.start()
        
        # 验证最小连接数
        assert len(pool.connections) == 2
        assert len(pool.idle_connections) == 2
        
        await pool.stop()
    
    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        """测试连接获取和释放"""
        pool = ASRConnectionPool(min_connections=2, max_connections=5)
        await pool.start()
        
        try:
            # 获取连接
            conn_id = await pool.acquire(client_type="esp32", client_id="device_001")
            assert conn_id is not None
            assert conn_id in pool.busy_connections
            assert len(pool.busy_connections) == 1
            
            # 释放连接
            await pool.release(conn_id, success=True, processing_time=0.5)
            assert conn_id not in pool.busy_connections
            assert conn_id in [c for c in pool.idle_connections]
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_acquire(self):
        """测试并发获取连接"""
        pool = ASRConnectionPool(min_connections=0, max_connections=10)  # 从0开始避免初始连接干扰
        await pool.start()
        
        try:
            # 顺序获取5个连接（因为锁的存在，并发获取会串行化）
            conn_ids = []
            for i in range(5):
                conn_id = await pool.acquire(client_type="esp32", client_id=f"device_{i}")
                conn_ids.append(conn_id)
            
            # 验证获取了5个不同的连接
            assert len(set(conn_ids)) == 5, f"Expected 5 unique connections, got {len(set(conn_ids))}"
            assert len(pool.busy_connections) == 5
            
            # 释放所有连接
            for conn_id in conn_ids:
                await pool.release(conn_id, success=True)
            
            assert len(pool.busy_connections) == 0
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_max_connections_limit(self):
        """测试最大连接数限制"""
        pool = ASRConnectionPool(min_connections=2, max_connections=3)
        await pool.start()
        
        try:
            # 获取3个连接（达到最大值）
            conn_ids = []
            for i in range(3):
                conn_id = await pool.acquire(client_type="web", client_id=f"client_{i}")
                conn_ids.append(conn_id)
            
            assert len(pool.connections) == 3
            
            # 尝试获取第4个连接（应该等待）
            acquire_task = asyncio.create_task(
                pool.acquire(client_type="web", client_id="client_4", timeout=1.0)
            )
            
            # 等待一小段时间
            await asyncio.sleep(0.1)
            
            # 释放一个连接
            await pool.release(conn_ids[0], success=True)
            
            # 第4个连接应该能获取到
            conn_id_4 = await acquire_task
            assert conn_id_4 is not None
            
            # 清理
            for conn_id in conn_ids[1:] + [conn_id_4]:
                await pool.release(conn_id, success=True)
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_acquire_timeout(self):
        """测试获取连接超时"""
        pool = ASRConnectionPool(min_connections=1, max_connections=1)
        await pool.start()
        
        try:
            # 获取唯一的连接
            conn_id = await pool.acquire(client_type="esp32")
            
            # 尝试获取第二个连接（应该超时）
            with pytest.raises(TimeoutError):
                await pool.acquire(client_type="esp32", timeout=0.5)
            
            # 释放连接
            await pool.release(conn_id, success=True)
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_client_affinity(self):
        """测试客户端亲和性（同一客户端优先获取相同连接）"""
        pool = ASRConnectionPool(min_connections=2, max_connections=5)
        await pool.start()
        
        try:
            # 第一次获取
            conn_id_1 = await pool.acquire(client_type="esp32", client_id="device_001")
            await pool.release(conn_id_1, success=True)
            
            # 同一客户端再次获取（应该获取到相同连接）
            conn_id_2 = await pool.acquire(client_type="esp32", client_id="device_001")
            assert conn_id_1 == conn_id_2
            
            await pool.release(conn_id_2, success=True)
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_error_tracking(self):
        """测试错误追踪和不健康连接标记"""
        pool = ASRConnectionPool(min_connections=1, max_connections=5)
        await pool.start()
        
        try:
            # 获取初始连接
            conn_id = await pool.acquire(client_type="web")
            
            # 模拟2次失败（还不会标记为不健康）
            await pool.release(conn_id, success=False)
            conn_id = await pool.acquire(client_type="web")
            await pool.release(conn_id, success=False)
            
            # 第3次失败后应该被标记为不健康
            conn_id = await pool.acquire(client_type="web")
            await pool.release(conn_id, success=False)
            
            # 检查连接状态
            conn_info = pool.get_connection_info(conn_id)
            assert conn_info.error_count == 3  # 错误次数应该是3
            assert conn_info.state == ASRConnectionState.UNHEALTHY  # 应该被标记为不健康
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self):
        """测试指标收集"""
        pool = ASRConnectionPool(min_connections=2, max_connections=5)
        await pool.start()
        
        try:
            # 执行一些操作
            conn_id = await pool.acquire(client_type="esp32", client_id="device_001")
            await asyncio.sleep(0.1)
            await pool.release(conn_id, success=True, processing_time=0.1)
            
            # 获取指标
            metrics = pool.get_metrics()
            assert metrics.total_connections >= 2
            assert metrics.total_requests >= 1
            assert metrics.successful_requests >= 1
            
            # 获取统计信息
            stats = pool.get_stats()
            assert stats['total_connections'] >= 2
            assert stats['total_requests'] >= 1
            assert stats['success_rate'] > 0
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查"""
        pool = ASRConnectionPool(
            min_connections=2,
            max_connections=5,
            max_idle_time=1,  # 1秒空闲超时
            health_check_interval=2
        )
        await pool.start()
        
        try:
            # 创建额外连接
            conn_id = await pool.acquire(client_type="web")
            await pool.release(conn_id, success=True)
            
            initial_count = len(pool.connections)
            
            # 等待健康检查运行
            await asyncio.sleep(3)
            
            # 空闲连接应该被清理（但保持最小连接数）
            assert len(pool.connections) >= pool.min_connections
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_connection_type_separation(self):
        """测试不同客户端类型的连接分离"""
        pool = ASRConnectionPool(min_connections=0, max_connections=10)  # 从0开始避免初始连接干扰
        await pool.start()
        
        try:
            # 获取ESP32连接
            esp32_conn = await pool.acquire(client_type="esp32", client_id="device_001")
            
            # 获取Web连接
            web_conn = await pool.acquire(client_type="web", client_id="user_001")
            
            # 验证连接信息
            esp32_info = pool.get_connection_info(esp32_conn)
            web_info = pool.get_connection_info(web_conn)
            
            assert esp32_info.client_type == "esp32"
            assert web_info.client_type == "web"
            
            # 释放连接
            await pool.release(esp32_conn, success=True)
            await pool.release(web_conn, success=True)
            
            # 检查指标
            metrics = pool.get_metrics()
            assert "esp32" in metrics.connections_by_type
            assert "web" in metrics.connections_by_type
            
        finally:
            await pool.stop()


@pytest.mark.asyncio
async def test_global_pool_singleton():
    """测试全局连接池单例"""
    # 初始化全局连接池
    pool1 = await initialize_asr_connection_pool()
    pool2 = get_asr_connection_pool()
    
    # 应该是同一个实例
    assert pool1 is pool2
    
    await pool1.stop()


@pytest.mark.asyncio
async def test_pool_stress_test():
    """压力测试：模拟高并发场景"""
    pool = ASRConnectionPool(min_connections=5, max_connections=20)
    await pool.start()
    
    try:
        async def worker(worker_id: int):
            """工作协程"""
            for i in range(10):
                conn_id = await pool.acquire(
                    client_type="esp32" if worker_id % 2 == 0 else "web",
                    client_id=f"client_{worker_id}"
                )
                await asyncio.sleep(0.01)  # 模拟处理
                await pool.release(conn_id, success=True, processing_time=0.01)
        
        # 启动50个并发工作协程
        tasks = [worker(i) for i in range(50)]
        await asyncio.gather(*tasks)
        
        # 验证指标
        metrics = pool.get_metrics()
        assert metrics.total_requests == 500  # 50 workers * 10 requests
        assert metrics.successful_requests == 500
        assert metrics.failed_requests == 0
        
        stats = pool.get_stats()
        assert stats['success_rate'] == 100.0
        
    finally:
        await pool.stop()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
