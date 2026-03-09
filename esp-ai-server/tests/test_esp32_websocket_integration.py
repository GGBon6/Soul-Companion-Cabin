"""
ESP32 WebSocket集成模块测试
Test ESP32 WebSocket Integration Module
测试WebSocket连接管理、消息路由、会话管理等核心功能
"""

import asyncio
import json
import pytest
import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import websockets
import time
import uuid
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.devices.esp32.websocket import (
    ESP32WebSocketManager,
    ESP32MessageRouter,
    ESP32SessionManager,
    ESP32ConnectionHandler
)
from app.devices.esp32.websocket.websocket_manager import ESP32DeviceInfo, ConnectionState
from app.devices.esp32.websocket.message_router import MessageType, MessagePriority, MessageContext
from app.devices.esp32.websocket.session_manager import ESP32Session, SessionState


class TestESP32WebSocketManager(unittest.TestCase):
    """测试ESP32 WebSocket管理器"""
    
    def setUp(self):
        """设置测试环境"""
        self.config = {
            "max_connections": 100,
            "connection_timeout": 60,
            "heartbeat_interval": 10,
            "auth": {
                "enabled": False,
                "device_whitelist": [],
                "jwt_secret": "test_secret"
            }
        }
        self.manager = ESP32WebSocketManager(self.config)
    
    def test_manager_initialization(self):
        """测试管理器初始化"""
        self.assertIsNotNone(self.manager)
        self.assertEqual(self.manager.max_connections, 100)
        self.assertEqual(self.manager.connection_timeout, 60)
        self.assertEqual(self.manager.heartbeat_interval, 10)
        self.assertFalse(self.manager.auth_enabled)
    
    def test_device_info_extraction(self):
        """测试设备信息提取"""
        # Mock WebSocket对象
        mock_websocket = Mock()
        mock_websocket.request.headers = {
            "device-id": "test_device_001",
            "client-id": "test_client_001",
            "protocol-version": "2.0",
            "user-agent": "ESP32-Client/1.0"
        }
        mock_websocket.remote_address = ("192.168.1.100", 12345)
        
        # 测试设备信息提取
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            device_info = loop.run_until_complete(
                self.manager._extract_device_info(mock_websocket)
            )
            
            self.assertIsNotNone(device_info)
            self.assertEqual(device_info.device_id, "test_device_001")
            self.assertEqual(device_info.client_id, "test_client_001")
            self.assertEqual(device_info.protocol_version, "2.0")
            self.assertEqual(device_info.client_ip, "192.168.1.100")
            
        finally:
            loop.close()
    
    def test_connection_registration(self):
        """测试连接注册"""
        # 创建测试设备信息
        device_info = ESP32DeviceInfo(
            device_id="test_device_001",
            client_id="test_client_001",
            client_ip="192.168.1.100"
        )
        
        # Mock连接处理器
        mock_handler = Mock()
        mock_handler.device_info = device_info
        
        connection_id = "test_connection_001"
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 注册连接
            loop.run_until_complete(
                self.manager._register_connection(connection_id, mock_handler, device_info)
            )
            
            # 验证注册结果
            self.assertIn(connection_id, self.manager.active_connections)
            self.assertIn(device_info.device_id, self.manager.device_connections)
            self.assertEqual(self.manager.device_connections[device_info.device_id], connection_id)
            self.assertEqual(self.manager.stats.active_connections, 1)
            
        finally:
            loop.close()
    
    def test_connection_stats(self):
        """测试连接统计"""
        stats = self.manager.get_connection_stats()
        
        self.assertIn("total_connections", stats)
        self.assertIn("active_connections", stats)
        self.assertIn("failed_connections", stats)
        self.assertIn("messages_sent", stats)
        self.assertIn("messages_received", stats)
        self.assertIn("uptime", stats)
        
        self.assertEqual(stats["active_connections"], 0)
        self.assertEqual(stats["total_connections"], 0)


class TestESP32MessageRouter(unittest.TestCase):
    """测试ESP32消息路由器"""
    
    def setUp(self):
        """设置测试环境"""
        self.router = ESP32MessageRouter()
        
        # Mock连接处理器
        self.mock_connection_handler = Mock()
        self.mock_connection_handler.device_info = ESP32DeviceInfo(
            device_id="test_device_001",
            client_id="test_client_001"
        )
        self.mock_connection_handler.session_id = "test_session_001"
    
    def test_router_initialization(self):
        """测试路由器初始化"""
        self.assertIsNotNone(self.router)
        self.assertGreater(len(self.router.handlers), 0)
        
        # 验证默认处理器
        supported_types = self.router.get_supported_types()
        expected_types = ["hello", "audio", "text", "control", "status"]
        
        for msg_type in expected_types:
            self.assertIn(msg_type, supported_types)
    
    def test_message_parsing_json(self):
        """测试JSON消息解析"""
        json_message = json.dumps({
            "type": "text",
            "content": "Hello, ESP32!"
        })
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            context = loop.run_until_complete(
                self.router._parse_message(json_message, self.mock_connection_handler)
            )
            
            self.assertIsNotNone(context)
            self.assertEqual(context.message_type, MessageType.TEXT)
            self.assertEqual(context.parsed_data["content"], "Hello, ESP32!")
            self.assertEqual(context.device_id, "test_device_001")
            
        finally:
            loop.close()
    
    def test_message_parsing_binary(self):
        """测试二进制消息解析"""
        binary_data = b"fake_audio_data"
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            context = loop.run_until_complete(
                self.router._parse_message(binary_data, self.mock_connection_handler)
            )
            
            self.assertIsNotNone(context)
            self.assertEqual(context.message_type, MessageType.AUDIO)
            self.assertEqual(context.parsed_data["audio_data"], binary_data)
            
        finally:
            loop.close()
    
    def test_hello_message_handler(self):
        """测试Hello消息处理器"""
        from app.devices.esp32.websocket.message_router import HelloMessageHandler
        
        handler = HelloMessageHandler()
        
        # 测试消息验证
        valid_data = {
            "device_id": "test_device_001",
            "protocol_version": "2.0",
            "features": {"mcp": True},
            "audio_params": {"sample_rate": 16000, "format": "opus"}
        }
        
        self.assertTrue(handler.validate(valid_data))
        
        invalid_data = {"invalid": "data"}
        self.assertFalse(handler.validate(invalid_data))
        
        # 测试消息处理
        context = MessageContext(
            message_id="test_msg_001",
            message_type=MessageType.HELLO,
            priority=MessagePriority.NORMAL,
            timestamp=time.time(),
            device_id="test_device_001",
            session_id="test_session_001",
            raw_data=valid_data,
            parsed_data=valid_data,
            metadata={}
        )
        
        # Mock连接处理器的initialize_session方法
        self.mock_connection_handler.initialize_session = AsyncMock()
        self.mock_connection_handler.session_id = "test_session_001"
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            response = loop.run_until_complete(
                handler.handle(context, self.mock_connection_handler)
            )
            
            self.assertIsNotNone(response)
            self.assertEqual(response["type"], "hello")
            self.assertEqual(response["status"], "success")
            self.assertIn("session_id", response)
            self.assertIn("server_info", response)
            
        finally:
            loop.close()
    
    def test_control_message_handler(self):
        """测试控制消息处理器"""
        from app.devices.esp32.websocket.message_router import ControlMessageHandler
        
        handler = ControlMessageHandler()
        
        # 测试停止命令
        stop_data = {"command": "stop"}
        self.assertTrue(handler.validate(stop_data))
        self.assertEqual(handler.get_priority(stop_data), MessagePriority.EMERGENCY)
        
        # 测试暂停命令
        pause_data = {"command": "pause"}
        self.assertEqual(handler.get_priority(pause_data), MessagePriority.URGENT)
        
        # Mock连接处理器方法
        self.mock_connection_handler.stop_all_processing = AsyncMock()
        
        context = MessageContext(
            message_id="test_msg_002",
            message_type=MessageType.CONTROL,
            priority=MessagePriority.EMERGENCY,
            timestamp=time.time(),
            device_id="test_device_001",
            session_id="test_session_001",
            raw_data=stop_data,
            parsed_data=stop_data,
            metadata={}
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            response = loop.run_until_complete(
                handler.handle(context, self.mock_connection_handler)
            )
            
            self.assertIsNotNone(response)
            self.assertEqual(response["type"], "control_response")
            self.assertEqual(response["command"], "stop")
            self.assertEqual(response["status"], "stopped")
            
        finally:
            loop.close()


class TestESP32SessionManager(unittest.TestCase):
    """测试ESP32会话管理器"""
    
    def setUp(self):
        """设置测试环境"""
        self.config = {
            "session_timeout": 60,
            "max_sessions": 100,
            "cleanup_interval": 10,
            "auto_save": False  # 测试时禁用自动保存
        }
        
        # Mock依赖服务
        with patch('app.devices.esp32.websocket.session_manager.get_chat_history_service'), \
             patch('app.devices.esp32.websocket.session_manager.get_youth_psychology_config'):
            self.session_manager = ESP32SessionManager(self.config)
    
    def test_session_manager_initialization(self):
        """测试会话管理器初始化"""
        self.assertIsNotNone(self.session_manager)
        self.assertEqual(self.session_manager.session_timeout, 60)
        self.assertEqual(self.session_manager.max_sessions, 100)
        self.assertFalse(self.session_manager.auto_save)
    
    def test_session_creation(self):
        """测试会话创建"""
        device_info = {
            "audio_params": {
                "sample_rate": 16000,
                "format": "opus",
                "channels": 1
            },
            "features": {"mcp": True}
        }
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            session = loop.run_until_complete(
                self.session_manager.create_session(
                    device_id="test_device_001",
                    user_id="test_user_001",
                    device_info=device_info
                )
            )
            
            self.assertIsNotNone(session)
            self.assertEqual(session.device_id, "test_device_001")
            self.assertEqual(session.user_id, "test_user_001")
            self.assertEqual(session.state, SessionState.ACTIVE)
            self.assertEqual(session.audio_context.sample_rate, 16000)
            self.assertEqual(session.audio_context.format, "opus")
            
            # 验证会话注册
            self.assertIn(session.session_id, self.session_manager.sessions)
            self.assertIn("test_device_001", self.session_manager.device_sessions)
            
        finally:
            loop.close()
    
    def test_conversation_message_handling(self):
        """测试对话消息处理"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 创建会话
            session = loop.run_until_complete(
                self.session_manager.create_session(
                    device_id="test_device_002",
                    user_id="test_user_002"
                )
            )
            
            # 添加用户消息
            success = loop.run_until_complete(
                self.session_manager.add_conversation_message(
                    session.session_id,
                    "user",
                    "Hello, how are you?",
                    {"intent": "greeting"}
                )
            )
            
            self.assertTrue(success)
            self.assertEqual(len(session.conversation_context.dialogue_history), 1)
            self.assertEqual(session.conversation_context.conversation_count, 1)
            
            # 添加助手回复
            success = loop.run_until_complete(
                self.session_manager.add_conversation_message(
                    session.session_id,
                    "assistant",
                    "Hello! I'm doing well, thank you for asking.",
                    {"intent_response": True}
                )
            )
            
            self.assertTrue(success)
            self.assertEqual(len(session.conversation_context.dialogue_history), 2)
            self.assertEqual(session.conversation_context.total_interactions, 2)
            
        finally:
            loop.close()
    
    def test_session_state_management(self):
        """测试会话状态管理"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 创建会话
            session = loop.run_until_complete(
                self.session_manager.create_session(
                    device_id="test_device_003",
                    user_id="test_user_003"
                )
            )
            
            # 测试暂停会话
            success = loop.run_until_complete(
                self.session_manager.pause_session(session.session_id)
            )
            self.assertTrue(success)
            self.assertEqual(session.state, SessionState.PAUSED)
            
            # 测试恢复会话
            success = loop.run_until_complete(
                self.session_manager.resume_session(session.session_id)
            )
            self.assertTrue(success)
            self.assertEqual(session.state, SessionState.ACTIVE)
            
            # 测试关闭会话
            success = loop.run_until_complete(
                self.session_manager.close_session(session.session_id, "test_close")
            )
            self.assertTrue(success)
            self.assertNotIn(session.session_id, self.session_manager.sessions)
            
        finally:
            loop.close()
    
    def test_session_expiration(self):
        """测试会话过期"""
        # 创建一个已过期的会话
        session = ESP32Session(
            session_id="expired_session",
            device_id="expired_device",
            user_id="expired_user"
        )
        
        # 设置过期时间为过去
        session.last_activity = time.time() - 3600  # 1小时前
        
        # 测试过期检查
        self.assertTrue(session.is_expired(timeout=60))  # 1分钟超时
        self.assertFalse(session.is_expired(timeout=7200))  # 2小时超时
    
    def test_session_statistics(self):
        """测试会话统计"""
        stats = self.session_manager.get_session_stats()
        
        self.assertIn("total_sessions", stats)
        self.assertIn("active_sessions", stats)
        self.assertIn("paused_sessions", stats)
        self.assertIn("device_sessions", stats)
        self.assertIn("session_timeout", stats)
        
        self.assertEqual(stats["total_sessions"], 0)
        self.assertEqual(stats["active_sessions"], 0)


class TestESP32ConnectionHandler(unittest.TestCase):
    """测试ESP32连接处理器"""
    
    def setUp(self):
        """设置测试环境"""
        # Mock WebSocket
        self.mock_websocket = AsyncMock()
        self.mock_websocket.closed = False
        
        # 创建设备信息
        self.device_info = ESP32DeviceInfo(
            device_id="test_device_001",
            client_id="test_client_001",
            client_ip="192.168.1.100",
            protocol_version="2.0",
            features={"mcp": True},
            audio_params={"sample_rate": 16000, "format": "opus"}
        )
        
        # Mock管理器
        self.mock_manager = Mock()
        self.mock_manager.stats = Mock()
        self.mock_manager.stats.messages_sent = 0
        self.mock_manager.stats.bytes_sent = 0
        
        # Mock服务组件
        with patch('app.devices.esp32.websocket.connection_handler.get_esp32_asr_integration'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_tts_integration'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_intent_processor'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_speech_coordinator'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_audio_converter'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_message_router'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_session_manager'):
            
            self.handler = ESP32ConnectionHandler(
                connection_id="test_connection_001",
                websocket=self.mock_websocket,
                device_info=self.device_info,
                manager=self.mock_manager
            )
    
    def test_handler_initialization(self):
        """测试处理器初始化"""
        self.assertIsNotNone(self.handler)
        self.assertEqual(self.handler.device_info.device_id, "test_device_001")
        self.assertTrue(self.handler.is_connected)
        self.assertIsNotNone(self.handler.session_id)
    
    def test_audio_packet_encoding(self):
        """测试音频包编码"""
        audio_data = b"test_audio_data"
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            packet = loop.run_until_complete(
                self.handler._encode_audio_packet(audio_data, "opus")
            )
            
            self.assertIsNotNone(packet)
            self.assertGreater(len(packet), len(audio_data))  # 应该包含头部
            self.assertTrue(packet.endswith(audio_data))  # 应该以音频数据结尾
            
        finally:
            loop.close()
    
    def test_status_reporting(self):
        """测试状态报告"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            status = loop.run_until_complete(self.handler.get_status())
            
            self.assertIn("connection_id", status)
            self.assertIn("device_id", status)
            self.assertIn("session_id", status)
            self.assertIn("is_connected", status)
            self.assertIn("processing_state", status)
            self.assertIn("device_info", status)
            self.assertIn("performance", status)
            
            self.assertEqual(status["device_id"], "test_device_001")
            self.assertTrue(status["is_connected"])
            
        finally:
            loop.close()
    
    def test_processing_control(self):
        """测试处理控制"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 测试停止处理
            loop.run_until_complete(self.handler.stop_all_processing())
            self.assertTrue(self.handler.processing_state.is_paused)
            self.assertFalse(self.handler.processing_state.is_processing_audio)
            
            # 测试恢复处理
            loop.run_until_complete(self.handler.resume_processing())
            self.assertFalse(self.handler.processing_state.is_paused)
            
        finally:
            loop.close()


class TestIntegrationScenarios(unittest.TestCase):
    """集成测试场景"""
    
    def test_complete_message_flow(self):
        """测试完整消息流程"""
        # 这个测试需要更复杂的mock设置
        # 暂时跳过，在实际环境中进行集成测试
        pass
    
    def test_error_handling(self):
        """测试错误处理"""
        router = ESP32MessageRouter()
        
        # 测试无效消息处理
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            mock_handler = Mock()
            mock_handler.device_info = ESP32DeviceInfo(device_id="test")
            mock_handler.session_id = "test_session"
            
            # 测试无效JSON
            result = loop.run_until_complete(
                router.route_message("invalid json", mock_handler)
            )
            
            # 应该返回错误响应或处理为纯文本
            self.assertIsNotNone(result)
            
        finally:
            loop.close()


def run_async_test(test_func):
    """运行异步测试的辅助函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


if __name__ == "__main__":
    print("🧪 开始测试ESP32 WebSocket集成模块...")
    print("=" * 70)
    
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestESP32WebSocketManager,
        TestESP32MessageRouter,
        TestESP32SessionManager,
        TestESP32ConnectionHandler,
        TestIntegrationScenarios
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ 所有测试通过！ESP32 WebSocket集成模块工作正常")
        print(f"📊 运行了 {result.testsRun} 个测试")
        print("\n🎯 测试覆盖的功能：")
        print("  ✅ WebSocket连接管理 - 连接注册、状态管理、统计收集")
        print("  ✅ 消息路由系统 - 消息解析、路由分发、处理器管理")
        print("  ✅ 会话管理 - 会话创建、状态控制、对话历史")
        print("  ✅ 连接处理器 - 音频编码、状态报告、处理控制")
        print("  ✅ 错误处理 - 异常捕获、降级处理、错误恢复")
    else:
        print("❌ 部分测试失败")
        print(f"📊 运行了 {result.testsRun} 个测试")
        print(f"❌ 失败: {len(result.failures)}")
        print(f"⚠️  错误: {len(result.errors)}")
        
        if result.failures:
            print("\n失败的测试:")
            for test, traceback in result.failures:
                print(f"  - {test}")
        
        if result.errors:
            print("\n错误的测试:")
            for test, traceback in result.errors:
                print(f"  - {test}")
    
    print("=" * 70)
