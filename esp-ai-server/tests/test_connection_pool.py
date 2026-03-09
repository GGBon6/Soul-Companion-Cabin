"""
连接池管理器测试
Connection Pool Manager Tests
测试连接池的各种功能和限制
"""

import asyncio
import json
import time
import sys
import os
from typing import List
import websockets
from websockets.exceptions import ConnectionClosed

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core import logger
from app.core.config import settings


class ConnectionPoolTester:
    """连接池测试器"""
    
    def __init__(self, server_url: str = None):
        # 使用localhost而不是0.0.0.0进行客户端连接
        host = "localhost" if settings.HOST == "0.0.0.0" else settings.HOST
        self.server_url = server_url or f"ws://{host}:{settings.PORT}"
        self.connections: List[websockets.WebSocketCommonProtocol] = []
        self.test_results = {}
    
    async def test_basic_connection(self):
        """测试基本连接功能"""
        logger.info("🧪 测试基本连接功能...")
        
        try:
            websocket = await websockets.connect(self.server_url)
            self.connections.append(websocket)
            
            # 发送ping消息
            ping_message = {"type": "ping"}
            await websocket.send(json.dumps(ping_message))
            
            # 等待响应
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(response)
            
            success = data.get("type") == "pong"
            self.test_results["basic_connection"] = success
            
            logger.info(f"✅ 基本连接测试: {'成功' if success else '失败'}")
            return success
            
        except Exception as e:
            logger.error(f"❌ 基本连接测试失败: {e}")
            self.test_results["basic_connection"] = False
            return False
    
    async def test_connection_limit(self, max_connections: int = 10):
        """测试连接数限制"""
        logger.info(f"🧪 测试连接数限制 (最大: {max_connections})...")
        
        successful_connections = 0
        rejected_connections = 0
        
        tasks = []
        for i in range(max_connections + 5):  # 尝试超过限制的连接数
            tasks.append(self._create_connection_task(i))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                rejected_connections += 1
                logger.debug(f"连接 {i} 被拒绝: {result}")
            elif result:
                successful_connections += 1
                logger.debug(f"连接 {i} 成功")
            else:
                rejected_connections += 1
        
        # 验证是否正确限制了连接数
        limit_working = rejected_connections > 0
        self.test_results["connection_limit"] = {
            "successful": successful_connections,
            "rejected": rejected_connections,
            "limit_working": limit_working
        }
        
        logger.info(f"✅ 连接限制测试: 成功连接={successful_connections}, 拒绝连接={rejected_connections}")
        return limit_working
    
    async def _create_connection_task(self, connection_id: int):
        """创建连接任务"""
        try:
            websocket = await asyncio.wait_for(
                websockets.connect(self.server_url), 
                timeout=5.0
            )
            self.connections.append(websocket)
            
            # 发送一个简单的消息确认连接
            test_message = {
                "type": "ping",
                "connection_id": connection_id
            }
            await websocket.send(json.dumps(test_message))
            
            # 等待响应
            await asyncio.wait_for(websocket.recv(), timeout=3.0)
            return True
            
        except Exception as e:
            logger.debug(f"连接 {connection_id} 失败: {e}")
            return False
    
    async def test_health_check(self):
        """测试健康检查功能"""
        logger.info("🧪 测试健康检查功能...")
        
        try:
            if not self.connections:
                await self.test_basic_connection()
            
            if not self.connections:
                self.test_results["health_check"] = False
                return False
            
            websocket = self.connections[0]
            
            # 等待服务器发送ping
            logger.info("等待服务器ping消息...")
            
            ping_received = False
            start_time = time.time()
            timeout = 90  # 等待90秒
            
            while time.time() - start_time < timeout:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    
                    if data.get("type") == "ping":
                        ping_received = True
                        logger.info("📡 收到服务器ping消息")
                        
                        # 发送pong响应
                        pong_message = {"type": "pong"}
                        await websocket.send(json.dumps(pong_message))
                        logger.info("📡 发送pong响应")
                        break
                        
                except asyncio.TimeoutError:
                    continue
                except ConnectionClosed:
                    logger.warning("连接已关闭")
                    break
            
            self.test_results["health_check"] = ping_received
            logger.info(f"✅ 健康检查测试: {'成功' if ping_received else '失败'}")
            return ping_received
            
        except Exception as e:
            logger.error(f"❌ 健康检查测试失败: {e}")
            self.test_results["health_check"] = False
            return False
    
    async def test_connection_metrics(self):
        """测试连接指标功能"""
        logger.info("🧪 测试连接指标功能...")
        
        try:
            if not self.connections:
                await self.test_basic_connection()
            
            if not self.connections:
                self.test_results["metrics"] = False
                return False
            
            websocket = self.connections[0]
            
            # 请求连接池指标
            metrics_request = {"type": "get_pool_metrics"}
            await websocket.send(json.dumps(metrics_request))
            
            # 等待响应
            response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            data = json.loads(response)
            
            success = (data.get("type") == "pool_metrics" and 
                      "total_connections" in data.get("data", {}))
            
            if success:
                metrics_data = data["data"]
                logger.info(f"📊 连接池指标: 总连接={metrics_data.get('total_connections')}, "
                           f"活跃连接={metrics_data.get('active_connections')}")
            
            self.test_results["metrics"] = success
            logger.info(f"✅ 连接指标测试: {'成功' if success else '失败'}")
            return success
            
        except Exception as e:
            logger.error(f"❌ 连接指标测试失败: {e}")
            self.test_results["metrics"] = False
            return False
    
    async def test_user_login_and_tracking(self):
        """测试用户登录和连接跟踪"""
        logger.info("🧪 测试用户登录和连接跟踪...")
        
        try:
            websocket = await websockets.connect(self.server_url)
            self.connections.append(websocket)
            
            # 模拟用户登录
            login_message = {
                "type": "login",
                "username": "test_user",
                "password": "test_password"
            }
            await websocket.send(json.dumps(login_message))
            
            # 等待登录响应
            response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            data = json.loads(response)
            
            login_success = data.get("type") in ["login_success", "login_failed"]
            
            if login_success:
                # 请求连接状态
                status_request = {"type": "get_connection_status"}
                await websocket.send(json.dumps(status_request))
                
                status_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                status_data = json.loads(status_response)
                
                tracking_success = status_data.get("type") == "connection_status"
                
                if tracking_success:
                    conn_info = status_data.get("data", {})
                    logger.info(f"📊 连接状态: IP={conn_info.get('client_ip')}, "
                               f"类型={conn_info.get('client_type')}, "
                               f"用户={conn_info.get('user_id')}")
            else:
                tracking_success = False
            
            success = login_success and tracking_success
            self.test_results["user_tracking"] = success
            
            logger.info(f"✅ 用户跟踪测试: {'成功' if success else '失败'}")
            return success
            
        except Exception as e:
            logger.error(f"❌ 用户跟踪测试失败: {e}")
            self.test_results["user_tracking"] = False
            return False
    
    async def cleanup(self):
        """清理测试连接"""
        logger.info("🧹 清理测试连接...")
        
        close_tasks = []
        for websocket in self.connections:
            close_tasks.append(self._close_connection(websocket))
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        self.connections.clear()
        logger.info("✅ 测试连接清理完成")
    
    async def _close_connection(self, websocket):
        """关闭单个连接"""
        try:
            await websocket.close()
        except Exception as e:
            logger.debug(f"关闭连接异常: {e}")
    
    def print_test_results(self):
        """打印测试结果"""
        logger.info("=" * 50)
        logger.info("📋 连接池测试结果汇总")
        logger.info("=" * 50)
        
        for test_name, result in self.test_results.items():
            if isinstance(result, dict):
                logger.info(f"{test_name}: {result}")
            else:
                status = "✅ 通过" if result else "❌ 失败"
                logger.info(f"{test_name}: {status}")
        
        passed_tests = sum(1 for r in self.test_results.values() 
                          if (isinstance(r, bool) and r) or 
                             (isinstance(r, dict) and r.get("limit_working", False)))
        total_tests = len(self.test_results)
        
        logger.info("=" * 50)
        logger.info(f"总体结果: {passed_tests}/{total_tests} 个测试通过")
        logger.info("=" * 50)


async def run_connection_pool_tests():
    """运行连接池测试"""
    logger.info("🚀 开始连接池管理器测试...")
    
    tester = ConnectionPoolTester()
    
    try:
        # 运行各项测试
        await tester.test_basic_connection()
        await asyncio.sleep(1)
        
        await tester.test_connection_limit(max_connections=5)  # 测试较小的限制
        await asyncio.sleep(1)
        
        await tester.test_health_check()
        await asyncio.sleep(1)
        
        await tester.test_connection_metrics()
        await asyncio.sleep(1)
        
        await tester.test_user_login_and_tracking()
        
    finally:
        await tester.cleanup()
        tester.print_test_results()


if __name__ == "__main__":
    # 运行测试
    asyncio.run(run_connection_pool_tests())
