"""
ESP32新架构模块测试
Test ESP32 New Architecture Modules
测试新的消息注册表、设备会话管理和处理器框架
"""

import asyncio
import json
import unittest
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.devices.esp32.message_types import ESP32MessageType, ESP32ConnectionState, ESP32DeviceCapability
from app.devices.esp32.message_registry import ESP32MessageRegistry, get_esp32_message_registry
from app.devices.esp32.device_session import ESP32DeviceSession, ESP32SessionManager
from app.devices.esp32.handlers.hello_handler import ESP32HelloHandler
from app.devices.esp32.handlers.base_handler import ESP32MessageValidator


class TestESP32MessageTypes(unittest.TestCase):
    """测试ESP32消息类型定义"""
    
    def test_message_types(self):
        """测试消息类型枚举"""
        self.assertEqual(ESP32MessageType.HELLO.value, "hello")
        self.assertEqual(ESP32MessageType.AUDIO.value, "audio")
        self.assertEqual(ESP32MessageType.TEXT.value, "text")
        self.assertEqual(ESP32MessageType.ABORT.value, "abort")
    
    def test_connection_states(self):
        """测试连接状态枚举"""
        self.assertEqual(ESP32ConnectionState.CONNECTING.value, "connecting")
        self.assertEqual(ESP32ConnectionState.AUTHENTICATED.value, "authenticated")
        self.assertEqual(ESP32ConnectionState.ACTIVE.value, "active")
    
    def test_device_capabilities(self):
        """测试设备能力枚举"""
        self.assertEqual(ESP32DeviceCapability.AUDIO_INPUT.value, "audio_input")
        self.assertEqual(ESP32DeviceCapability.TTS.value, "tts")
        self.assertEqual(ESP32DeviceCapability.ASR.value, "asr")


class TestESP32MessageRegistry(unittest.TestCase):
    """测试ESP32消息注册表"""
    
    def setUp(self):
        """设置测试环境"""
        self.registry = ESP32MessageRegistry()
    
    def test_registry_initialization(self):
        """测试注册表初始化"""
        self.assertIsInstance(self.registry, ESP32MessageRegistry)
        self.assertTrue(len(self.registry.get_supported_types()) > 0)
    
    def test_get_handler(self):
        """测试获取处理器"""
        hello_handler = self.registry.get_handler("hello")
        self.assertIsNotNone(hello_handler)
        self.assertIsInstance(hello_handler, ESP32HelloHandler)
    
    def test_unsupported_message_type(self):
        """测试不支持的消息类型"""
        unknown_handler = self.registry.get_handler("unknown_type")
        self.assertIsNone(unknown_handler)
    
    def test_supported_types(self):
        """测试支持的消息类型列表"""
        supported_types = self.registry.get_supported_types()
        self.assertIn("hello", supported_types)
        self.assertIn("audio", supported_types)
        self.assertIn("text", supported_types)
        self.assertIn("abort", supported_types)
    
    def test_handler_info(self):
        """测试处理器信息"""
        handler_info = self.registry.get_handler_info()
        self.assertIsInstance(handler_info, dict)
        self.assertIn("hello", handler_info)
        self.assertEqual(handler_info["hello"], "ESP32HelloHandler")


class TestESP32DeviceSession(unittest.TestCase):
    """测试ESP32设备会话"""
    
    def setUp(self):
        """设置测试环境"""
        # 创建模拟的WebSocket连接
        self.mock_websocket = Mock()
        self.mock_websocket.remote_address = ("192.168.1.100", 12345)
        self.mock_websocket.closed = False
        
        # 创建设备会话
        self.session = ESP32DeviceSession(
            websocket=self.mock_websocket,
            device_id="test_device_001",
            client_id="test_client"
        )
    
    def test_session_initialization(self):
        """测试会话初始化"""
        self.assertEqual(self.session.device_id, "test_device_001")
        self.assertEqual(self.session.client_id, "test_client")
        self.assertEqual(self.session.connection_state, ESP32ConnectionState.HELLO_PENDING)
        self.assertFalse(self.session.is_authenticated)
    
    def test_update_device_info(self):
        """测试更新设备信息"""
        device_info = {
            "version": "2.0",
            "audio_params": {
                "sample_rate": 16000,
                "frame_duration": 60,
                "format": "opus"
            },
            "capabilities": ["audio_input", "audio_output", "tts"],
            "features": {"mcp": True}
        }
        
        self.session.update_device_info(device_info)
        
        self.assertEqual(self.session.protocol_version, "2.0")
        self.assertEqual(self.session.audio_params["sample_rate"], 16000)
        self.assertTrue(self.session.has_capability(ESP32DeviceCapability.AUDIO_INPUT))
        self.assertTrue(self.session.get_feature("mcp"))
    
    def test_connection_state_management(self):
        """测试连接状态管理"""
        # 测试状态转换
        self.session.set_connection_state(ESP32ConnectionState.AUTHENTICATED)
        self.assertEqual(self.session.connection_state, ESP32ConnectionState.AUTHENTICATED)
        self.assertTrue(self.session.is_authenticated)
        
        self.session.set_connection_state(ESP32ConnectionState.ACTIVE)
        self.assertEqual(self.session.connection_state, ESP32ConnectionState.ACTIVE)
    
    def test_activity_tracking(self):
        """测试活动时间跟踪"""
        initial_time = self.session.last_activity_time
        
        # 等待一小段时间确保时间戳不同
        import time
        time.sleep(0.001)
        
        # 更新活动时间
        self.session.update_activity()
        
        self.assertGreater(self.session.last_activity_time, initial_time)
        self.assertGreaterEqual(self.session.get_idle_time(), 0)
    
    async def test_send_message(self):
        """测试发送消息"""
        # 设置异步mock
        self.mock_websocket.send = AsyncMock()
        
        message = {"type": "test", "content": "hello"}
        result = await self.session.send_message(message)
        
        self.assertTrue(result)
        self.mock_websocket.send.assert_called_once()
        
        # 检查消息是否包含session_id
        call_args = self.mock_websocket.send.call_args[0][0]
        sent_message = json.loads(call_args)
        self.assertIn("session_id", sent_message)
        self.assertEqual(sent_message["session_id"], self.session.session_id)
    
    def test_session_serialization(self):
        """测试会话序列化"""
        session_dict = self.session.to_dict()
        
        self.assertIn("session_id", session_dict)
        self.assertIn("device_id", session_dict)
        self.assertIn("connection_state", session_dict)
        self.assertIn("audio_params", session_dict)
        self.assertEqual(session_dict["device_id"], "test_device_001")


class TestESP32SessionManager(unittest.TestCase):
    """测试ESP32会话管理器"""
    
    def setUp(self):
        """设置测试环境"""
        self.manager = ESP32SessionManager()
        
        # 创建测试会话
        mock_websocket = Mock()
        mock_websocket.remote_address = ("192.168.1.100", 12345)
        mock_websocket.closed = False
        
        self.test_session = ESP32DeviceSession(
            websocket=mock_websocket,
            device_id="test_device_001",
            client_id="test_client"
        )
    
    def test_manager_initialization(self):
        """测试管理器初始化"""
        self.assertIsInstance(self.manager, ESP32SessionManager)
        self.assertEqual(self.manager.get_session_count(), 0)
    
    def test_add_session(self):
        """测试添加会话"""
        self.manager.add_session(self.test_session)
        
        self.assertEqual(self.manager.get_session_count(), 1)
        retrieved_session = self.manager.get_session("test_device_001")
        self.assertEqual(retrieved_session, self.test_session)
    
    def test_remove_session(self):
        """测试移除会话"""
        self.manager.add_session(self.test_session)
        self.assertEqual(self.manager.get_session_count(), 1)
        
        removed_session = self.manager.remove_session("test_device_001")
        self.assertEqual(removed_session, self.test_session)
        self.assertEqual(self.manager.get_session_count(), 0)
    
    def test_get_session_by_websocket(self):
        """测试通过WebSocket获取会话"""
        self.manager.add_session(self.test_session)
        
        retrieved_session = self.manager.get_session_by_websocket(self.test_session.websocket)
        self.assertEqual(retrieved_session, self.test_session)
    
    def test_get_all_sessions(self):
        """测试获取所有会话"""
        self.manager.add_session(self.test_session)
        
        all_sessions = self.manager.get_all_sessions()
        self.assertEqual(len(all_sessions), 1)
        self.assertIn(self.test_session, all_sessions)


class TestESP32MessageValidator(unittest.TestCase):
    """测试ESP32消息验证器"""
    
    def test_validate_hello_message(self):
        """测试Hello消息验证"""
        # 有效的Hello消息
        valid_hello = {
            "type": "hello",
            "version": "2.0"
        }
        is_valid, error_msg = ESP32MessageValidator.validate_hello_message(valid_hello)
        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "验证通过")
        
        # 无效的Hello消息 - 缺少version
        invalid_hello = {
            "type": "hello"
        }
        is_valid, error_msg = ESP32MessageValidator.validate_hello_message(invalid_hello)
        self.assertFalse(is_valid)
        self.assertIn("缺少必需字段", error_msg)
        
        # 无效的Hello消息 - 错误类型
        invalid_hello2 = {
            "type": "not_hello",
            "version": "2.0"
        }
        is_valid, error_msg = ESP32MessageValidator.validate_hello_message(invalid_hello2)
        self.assertFalse(is_valid)
        self.assertIn("消息类型不是hello", error_msg)
    
    def test_validate_text_message(self):
        """测试文本消息验证"""
        # 有效的文本消息
        valid_text = {
            "type": "text",
            "content": "Hello, world!"
        }
        is_valid, error_msg = ESP32MessageValidator.validate_text_message(valid_text)
        self.assertTrue(is_valid)
        
        # 无效的文本消息 - 缺少content
        invalid_text = {
            "type": "text"
        }
        is_valid, error_msg = ESP32MessageValidator.validate_text_message(invalid_text)
        self.assertFalse(is_valid)
        self.assertIn("缺少content字段", error_msg)


class TestESP32HelloHandler(unittest.TestCase):
    """测试ESP32 Hello处理器"""
    
    def setUp(self):
        """设置测试环境"""
        self.handler = ESP32HelloHandler()
        
        # 创建模拟设备会话
        mock_websocket = Mock()
        mock_websocket.remote_address = ("192.168.1.100", 12345)
        mock_websocket.closed = False
        
        self.mock_session = ESP32DeviceSession(
            websocket=mock_websocket,
            device_id="test_device_001",
            client_id="test_client"
        )
        self.mock_session.send_message = AsyncMock(return_value=True)
    
    def test_handler_message_type(self):
        """测试处理器消息类型"""
        self.assertEqual(self.handler.message_type, ESP32MessageType.HELLO)
    
    async def test_handle_valid_hello(self):
        """测试处理有效的Hello消息"""
        hello_message = {
            "type": "hello",
            "version": "2.0",
            "audio_params": {
                "sample_rate": 16000,
                "frame_duration": 60,
                "format": "opus"
            },
            "capabilities": ["audio_input", "audio_output", "tts"],
            "features": {"mcp": True}
        }
        
        result = await self.handler.handle(self.mock_session, hello_message)
        
        self.assertTrue(result)
        self.assertEqual(self.mock_session.connection_state, ESP32ConnectionState.ACTIVE)
        self.assertTrue(self.mock_session.is_authenticated)
        self.mock_session.send_message.assert_called_once()
    
    async def test_handle_invalid_hello(self):
        """测试处理无效的Hello消息"""
        invalid_hello = {
            "type": "hello"
            # 缺少version字段
        }
        
        result = await self.handler.handle(self.mock_session, invalid_hello)
        
        self.assertFalse(result)
        # 应该发送错误响应
        self.mock_session.send_message.assert_called()


def run_async_test(test_func):
    """运行异步测试的辅助函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


if __name__ == "__main__":
    print("🧪 开始测试ESP32新架构模块...")
    print("=" * 60)
    
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestESP32MessageTypes,
        TestESP32MessageRegistry,
        TestESP32DeviceSession,
        TestESP32SessionManager,
        TestESP32MessageValidator,
        TestESP32HelloHandler
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ 所有测试通过！ESP32新架构模块工作正常")
        print(f"📊 运行了 {result.testsRun} 个测试")
    else:
        print("❌ 部分测试失败")
        print(f"📊 运行了 {result.testsRun} 个测试")
        print(f"❌ 失败: {len(result.failures)}")
        print(f"⚠️  错误: {len(result.errors)}")
        
        if result.failures:
            print("\n失败的测试:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback}")
        
        if result.errors:
            print("\n错误的测试:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback}")
    
    print("=" * 60)
