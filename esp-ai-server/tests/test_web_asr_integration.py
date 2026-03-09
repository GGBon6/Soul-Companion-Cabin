"""
网页端ASR连接池集成测试
Web ASR Connection Pool Integration Tests
验证网页端和设备端ASR服务的隔离性和并发性
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.core.asr_connection_pool import ASRConnectionPool, get_asr_connection_pool, initialize_asr_connection_pool
from app.shared.services import acquire_asr_service


class TestWebASRIntegration:
    """网页端ASR集成测试"""
    
    @pytest.mark.asyncio
    async def test_web_client_isolation(self):
        """测试网页客户端之间的隔离"""
        pool = ASRConnectionPool(min_connections=0, max_connections=10)
        await pool.start()
        
        try:
            # 模拟3个不同的网页用户
            users = ["user_001", "user_002", "user_003"]
            connections = []
            
            for user_id in users:
                conn_id = await pool.acquire(client_type="web", client_id=user_id)
                connections.append((user_id, conn_id))
            
            # 验证每个用户获取了不同的连接
            conn_ids = [conn_id for _, conn_id in connections]
            assert len(set(conn_ids)) == 3, "每个用户应该获取不同的连接"
            
            # 验证连接类型都是web
            for user_id, conn_id in connections:
                conn_info = pool.get_connection_info(conn_id)
                assert conn_info.client_type == "web"
                assert conn_info.client_id == user_id
            
            # 释放所有连接
            for _, conn_id in connections:
                await pool.release(conn_id, success=True)
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_web_esp32_isolation(self):
        """测试网页端和ESP32设备端的隔离"""
        pool = ASRConnectionPool(min_connections=0, max_connections=10)
        await pool.start()
        
        try:
            # 获取网页连接
            web_conn = await pool.acquire(client_type="web", client_id="web_user_001")
            
            # 获取ESP32连接
            esp32_conn = await pool.acquire(client_type="esp32", client_id="device_001")
            
            # 验证连接类型
            web_info = pool.get_connection_info(web_conn)
            esp32_info = pool.get_connection_info(esp32_conn)
            
            assert web_info.client_type == "web"
            assert esp32_info.client_type == "esp32"
            assert web_conn != esp32_conn, "Web和ESP32应该使用不同的连接"
            
            # 释放连接
            await pool.release(web_conn, success=True)
            await pool.release(esp32_conn, success=True)
            
            # 检查指标
            metrics = pool.get_metrics()
            assert "web" in metrics.connections_by_type
            assert "esp32" in metrics.connections_by_type
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_web_requests(self):
        """测试并发网页请求"""
        pool = ASRConnectionPool(min_connections=0, max_connections=20)
        await pool.start()
        
        try:
            async def simulate_web_request(user_id: str):
                """模拟一个网页ASR请求"""
                async with acquire_asr_service(
                    client_type="web",
                    client_id=user_id,
                    timeout=10.0
                ) as asr_service:
                    # 模拟ASR处理
                    await asyncio.sleep(0.01)
                    return f"processed_{user_id}"
            
            # 并发10个网页请求
            tasks = [simulate_web_request(f"user_{i:03d}") for i in range(10)]
            results = await asyncio.gather(*tasks)
            
            # 验证所有请求都成功
            assert len(results) == 10
            assert all(r.startswith("processed_") for r in results)
            
            # 检查连接池状态
            stats = pool.get_stats()
            assert stats['total_requests'] >= 10
            assert stats['success_rate'] == 100.0
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_mixed_client_types(self):
        """测试混合客户端类型的并发请求"""
        pool = ASRConnectionPool(min_connections=0, max_connections=20)
        await pool.start()
        
        try:
            async def web_request(user_id: str):
                async with acquire_asr_service("web", user_id) as asr:
                    await asyncio.sleep(0.01)
                    return "web"
            
            async def esp32_request(device_id: str):
                async with acquire_asr_service("esp32", device_id) as asr:
                    await asyncio.sleep(0.01)
                    return "esp32"
            
            # 混合请求：5个web + 5个esp32
            tasks = []
            tasks.extend([web_request(f"user_{i}") for i in range(5)])
            tasks.extend([esp32_request(f"device_{i}") for i in range(5)])
            
            results = await asyncio.gather(*tasks)
            
            # 验证结果
            assert results.count("web") == 5
            assert results.count("esp32") == 5
            
            # 检查指标
            metrics = pool.get_metrics()
            assert metrics.connections_by_type.get("web", 0) > 0
            assert metrics.connections_by_type.get("esp32", 0) > 0
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_connection_reuse(self):
        """测试连接复用"""
        pool = ASRConnectionPool(min_connections=0, max_connections=5)
        await pool.start()
        
        try:
            user_id = "test_user_001"
            
            # 第一次请求
            async with acquire_asr_service("web", user_id) as asr1:
                conn_id_1 = asr1.connection_id
            
            # 第二次请求（应该复用相同连接）
            async with acquire_asr_service("web", user_id) as asr2:
                conn_id_2 = asr2.connection_id
            
            # 验证连接复用
            assert conn_id_1 == conn_id_2, "同一用户应该复用相同连接"
            
            # 检查连接使用次数
            conn_info = pool.get_connection_info(conn_id_1)
            assert conn_info.use_count == 2
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """测试超时处理"""
        pool = ASRConnectionPool(min_connections=0, max_connections=1)
        await pool.start()
        
        try:
            # 获取唯一的连接
            async with acquire_asr_service("web", "user_001") as asr1:
                # 尝试获取第二个连接（应该超时）
                with pytest.raises(TimeoutError):
                    async with acquire_asr_service("web", "user_002", timeout=0.5) as asr2:
                        pass
            
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """测试错误恢复"""
        pool = ASRConnectionPool(min_connections=1, max_connections=5)
        await pool.start()
        
        try:
            user_id = "test_user_001"
            
            # 模拟失败请求
            try:
                async with acquire_asr_service("web", user_id) as asr:
                    raise Exception("模拟ASR处理失败")
            except Exception:
                pass
            
            # 后续请求应该仍然可以成功
            async with acquire_asr_service("web", user_id) as asr:
                assert asr is not None
            
            # 检查错误统计
            stats = pool.get_stats()
            assert stats['failed_requests'] >= 1
            
        finally:
            await pool.stop()


@pytest.mark.asyncio
async def test_pool_metrics_accuracy():
    """测试连接池指标准确性"""
    pool = ASRConnectionPool(min_connections=2, max_connections=10)
    await pool.start()
    
    try:
        # 执行一系列操作
        for i in range(5):
            async with acquire_asr_service("web", f"user_{i}") as asr:
                await asyncio.sleep(0.01)
        
        # 检查指标
        stats = pool.get_stats()
        assert stats['total_requests'] == 5
        assert stats['successful_requests'] == 5
        assert stats['failed_requests'] == 0
        assert stats['success_rate'] == 100.0
        
        metrics = pool.get_metrics()
        assert metrics.total_requests == 5
        assert metrics.successful_requests == 5
        
    finally:
        await pool.stop()


@pytest.mark.asyncio
async def test_global_pool_initialization():
    """测试全局连接池初始化"""
    # 初始化全局连接池
    pool = await initialize_asr_connection_pool()
    assert pool is not None
    assert pool._started
    
    # 获取全局连接池
    pool2 = get_asr_connection_pool()
    assert pool is pool2
    
    # 测试使用全局连接池
    async with acquire_asr_service("web", "test_user") as asr:
        assert asr is not None
    
    await pool.stop()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
