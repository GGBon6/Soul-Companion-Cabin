"""
ESP32 WebSocket集成模块测试（修复版）
Test ESP32 WebSocket Integration Module (Fixed Version)
修复依赖初始化和事件循环问题的测试版本
"""

import asyncio
import json
import pytest
import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import time
import uuid
import sys
import os
from types import SimpleNamespace, ModuleType

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 提供假opuslib模块，避免测试依赖本地Opus库
if 'opuslib' not in sys.modules:
    fake_opuslib = ModuleType("opuslib")
    fake_api = ModuleType("opuslib.api")
    fake_api.info = ModuleType("opuslib.api.info")
    fake_api.decoder = ModuleType("opuslib.api.decoder")
    fake_api.encoder = ModuleType("opuslib.api.encoder")
    fake_api.ctl = ModuleType("opuslib.api.ctl")
    fake_exceptions = ModuleType("opuslib.exceptions")

    class DummyOpusError(Exception):
        pass

    fake_exceptions.OpusError = DummyOpusError

    fake_opuslib.api = fake_api
    fake_opuslib.exceptions = fake_exceptions

    sys.modules['opuslib'] = fake_opuslib
    sys.modules['opuslib.api'] = fake_api
    sys.modules['opuslib.api.info'] = fake_api.info
    sys.modules['opuslib.api.decoder'] = fake_api.decoder
    sys.modules['opuslib.api.encoder'] = fake_api.encoder
    sys.modules['opuslib.api.ctl'] = fake_api.ctl
    sys.modules['opuslib.exceptions'] = fake_exceptions


class TestESP32WebSocketManagerFixed(unittest.TestCase):
    """测试ESP32 WebSocket管理器（修复版）"""
    
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
        
        # Mock所有依赖
        with patch('app.devices.esp32.websocket.websocket_manager.get_llm_service'), \
             patch('app.devices.esp32.websocket.websocket_manager.get_chat_history_service'), \
             patch('app.devices.esp32.websocket.websocket_manager.get_esp32_asr_integration'), \
             patch('app.devices.esp32.websocket.websocket_manager.get_esp32_tts_integration'), \
             patch('app.devices.esp32.websocket.websocket_manager.get_esp32_intent_processor'), \
             patch('app.devices.esp32.websocket.websocket_manager.get_esp32_speech_coordinator'):
            
            from app.devices.esp32.websocket.websocket_manager import ESP32WebSocketManager
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


class TestESP32MessageRouterFixed(unittest.TestCase):
    """测试ESP32消息路由器（修复版）"""
    
    def setUp(self):
        """设置测试环境"""
        # Mock所有依赖服务
        with patch('app.devices.esp32.websocket.message_router.get_esp32_asr_integration'), \
             patch('app.devices.esp32.websocket.message_router.get_esp32_tts_integration'), \
             patch('app.devices.esp32.websocket.message_router.get_esp32_intent_processor'), \
             patch('app.devices.esp32.websocket.message_router.get_esp32_speech_coordinator'):
            
            from app.devices.esp32.websocket.message_router import ESP32MessageRouter
            self.router = ESP32MessageRouter()
        
        # Mock连接处理器
        from app.devices.esp32.websocket.websocket_manager import ESP32DeviceInfo
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
        expected_types = ["hello", "control", "status"]  # 只测试不依赖外部服务的处理器
        
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
            from app.devices.esp32.websocket.message_router import MessageType
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
            from app.devices.esp32.websocket.message_router import MessageType
            self.assertEqual(context.message_type, MessageType.AUDIO)
            self.assertEqual(context.parsed_data["audio_data"], binary_data)
            
        finally:
            loop.close()
    
    def test_hello_message_handler(self):
        """测试Hello消息处理器"""
        from app.devices.esp32.websocket.message_router import HelloMessageHandler, MessageContext, MessageType, MessagePriority
        
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

    @patch('app.devices.esp32.websocket.message_router.get_esp32_speech_coordinator')
    def test_streaming_final_text_triggers_full_flow(self, mock_get_coordinator):
        """识别出完整句子后应触发语音交互协调器并发送TTS"""
        from app.devices.esp32.websocket.message_router import AudioMessageHandler, MessageContext, MessageType, MessagePriority
        from app.devices.esp32.services.asr_service_integration import ASRResult, ASRQuality
        from app.devices.esp32.services.intent_processor import IntentRequest, IntentResult, IntentType, ProcessingStatus
        from app.devices.esp32.services.tts_service_integration import TTSRequest, TTSResult, TTSQuality
        from app.devices.esp32.services.speech_interaction_coordinator import InteractionRequest, InteractionResponse, InteractionResult
        from app.devices.esp32.audio import AudioFrame

        handler = AudioMessageHandler()
        context = MessageContext(
            message_id="msg-001",
            message_type=MessageType.AUDIO,
            priority=MessagePriority.HIGH,
            timestamp=time.time(),
            device_id="device-test-001",
            session_id="session-test-001",
            raw_data=b"",
            parsed_data={},
            metadata={}
        )

        connection_handler = SimpleNamespace(
            session=SimpleNamespace(session_id=context.session_id),
            send_message=AsyncMock(),
            send_audio_data=AsyncMock()
        )

        asr_result = ASRResult(
            text="你好，世界",
            confidence=0.95,
            quality=ASRQuality.GOOD,
            processing_time=0.05,
            audio_duration=0.5,
            frame_count=1,
            total_bytes=2,
            is_valid=True,
            metadata={"source": "test"}
        )

        intent_request = IntentRequest(
            user_text="你好，世界",
            device_id=context.device_id,
            session_id=context.session_id,
            metadata={}
        )
        intent_result = IntentResult(
            request=intent_request,
            intent_type=IntentType.CHAT,
            response_text="你好，很高兴见到你！",
            processing_status=ProcessingStatus.SUCCESS,
            processing_time=0.05,
            confidence=0.9,
            metadata={}
        )

        tts_request = TTSRequest(text=intent_result.response_text)
        tts_result = TTSResult(
            request=tts_request,
            audio_data=b"\x00\x01",
            audio_frames=[],
            quality=TTSQuality.HIGH,
            processing_time=0.1,
            audio_duration=0.5,
            frame_count=1,
            total_bytes=2,
            sample_rate=16000,
            is_success=True,
            metadata={}
        )

        interaction_request = InteractionRequest(
            audio_frames=[
                AudioFrame(
                    data=b"\x00\x01",
                    timestamp=time.time(),
                    sequence_number=0,
                    frame_size=2,
                    sample_rate=16000,
                    channels=1,
                    format="pcm",
                    metadata={}
                )
            ],
            device_id=context.device_id,
            session_id=context.session_id,
            metadata={}
        )

        interaction_response = InteractionResponse(
            request=interaction_request,
            result=InteractionResult.SUCCESS,
            state_history=[],
            asr_result=asr_result,
            intent_result=intent_result,
            tts_result=tts_result,
            total_time=0.2,
            asr_time=0.05,
            intent_time=0.05,
            tts_time=0.1,
            metadata={}
        )

        mock_coordinator = MagicMock()
        mock_coordinator.process_speech_interaction = AsyncMock(return_value=interaction_response)
        mock_get_coordinator.return_value = mock_coordinator

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                handler._handle_streaming_asr_result(
                    context,
                    connection_handler,
                    "你好，世界",
                    is_partial=False
                )
            )
        finally:
            loop.close()

        mock_get_coordinator.assert_called_once_with(context.device_id)
        mock_coordinator.process_speech_interaction.assert_awaited()

        # 验证交互请求携带了skip_asr信息
        coordinator_request = mock_coordinator.process_speech_interaction.call_args[0][0]
        self.assertTrue(coordinator_request.metadata.get("skip_asr"))
        self.assertEqual(coordinator_request.metadata["asr_result"].text, "你好，世界")
        self.assertTrue(coordinator_request.audio_frames[0].metadata.get("skip_asr"))

        # 确认TTS结果被发送到ESP32
        connection_handler.send_message.assert_awaited()
        connection_handler.send_audio_data.assert_awaited()
    
    def test_control_message_handler(self):
        """测试控制消息处理器"""
        from app.devices.esp32.websocket.message_router import ControlMessageHandler, MessageContext, MessageType, MessagePriority
        
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


class TestESP32SessionManagerFixed(unittest.TestCase):
    """测试ESP32会话管理器（修复版）"""
    
    def setUp(self):
        """设置测试环境"""
        self.config = {
            "session_timeout": 60,
            "max_sessions": 100,
            "cleanup_interval": 10,
            "auto_save": False  # 测试时禁用自动保存
        }
        
        # Mock依赖服务和禁用后台任务
        with patch('app.devices.esp32.websocket.session_manager.get_chat_history_service'), \
             patch('app.devices.esp32.websocket.session_manager.get_youth_psychology_config'):
            
            from app.devices.esp32.websocket.session_manager import ESP32SessionManager
            
            # 创建管理器但不启动后台任务
            self.session_manager = ESP32SessionManager.__new__(ESP32SessionManager)
            self.session_manager.config = self.config
            self.session_manager.sessions = {}
            self.session_manager.device_sessions = {}
            self.session_manager.user_sessions = {}
            self.session_manager.session_timeout = 60
            self.session_manager.max_sessions = 100
            self.session_manager.auto_save = False
            self.session_manager.max_history_length = 50
            self.session_manager.cleanup_task = None
            
            # Mock服务
            self.session_manager.chat_history_service = Mock()
            self.session_manager.psychology_config = Mock()
            self.session_manager.psychology_config.get_max_history_length.return_value = 50
            
            import logging
            self.session_manager.logger = logging.getLogger(__name__)
    
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
            # Mock _load_conversation_history方法
            self.session_manager._load_conversation_history = AsyncMock()
            
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
            from app.devices.esp32.websocket.session_manager import SessionState
            self.assertEqual(session.state, SessionState.ACTIVE)
            self.assertEqual(session.audio_context.sample_rate, 16000)
            self.assertEqual(session.audio_context.format, "opus")
            
            # 验证会话注册
            self.assertIn(session.session_id, self.session_manager.sessions)
            self.assertIn("test_device_001", self.session_manager.device_sessions)
            
        finally:
            loop.close()
    
    def test_session_expiration(self):
        """测试会话过期"""
        from app.devices.esp32.websocket.session_manager import ESP32Session
        
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


class TestESP32ConnectionHandlerFixed(unittest.TestCase):
    """测试ESP32连接处理器（修复版）"""
    
    def setUp(self):
        """设置测试环境"""
        # Mock WebSocket
        self.mock_websocket = AsyncMock()
        self.mock_websocket.closed = False
        
        # 创建设备信息
        from app.devices.esp32.websocket.websocket_manager import ESP32DeviceInfo
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
        
        # Mock所有服务组件
        with patch('app.devices.esp32.websocket.connection_handler.get_esp32_asr_integration'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_tts_integration'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_intent_processor'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_speech_coordinator'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_audio_converter'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_message_router'), \
             patch('app.devices.esp32.websocket.connection_handler.get_esp32_session_manager'):
            
            from app.devices.esp32.websocket.connection_handler import ESP32ConnectionHandler
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


class TestIntegrationScenariosFixed(unittest.TestCase):
    """集成测试场景（修复版）"""
    
    def test_message_type_enum(self):
        """测试消息类型枚举"""
        from app.devices.esp32.websocket.message_router import MessageType
        
        # 验证所有消息类型
        expected_types = ["hello", "audio", "text", "control", "intent", "tts", "status", "heartbeat", "error", "unknown"]
        
        for msg_type in expected_types:
            self.assertTrue(hasattr(MessageType, msg_type.upper()))
    
    def test_connection_state_enum(self):
        """测试连接状态枚举"""
        from app.devices.esp32.websocket.websocket_manager import ConnectionState
        
        # 验证所有连接状态
        expected_states = ["connecting", "connected", "authenticated", "active", "disconnecting", "disconnected", "error"]
        
        for state in expected_states:
            self.assertTrue(hasattr(ConnectionState, state.upper()))
    
    def test_session_state_enum(self):
        """测试会话状态枚举"""
        from app.devices.esp32.websocket.session_manager import SessionState
        
        # 验证所有会话状态
        expected_states = ["initializing", "active", "paused", "idle", "expired", "terminated"]
        
        for state in expected_states:
            self.assertTrue(hasattr(SessionState, state.upper()))
    
    def test_data_classes(self):
        """测试数据类"""
        from app.devices.esp32.websocket.websocket_manager import ESP32DeviceInfo
        from app.devices.esp32.websocket.session_manager import ESP32Session, AudioContext, ConversationContext
        
        # 测试设备信息
        device_info = ESP32DeviceInfo(
            device_id="test_device",
            client_id="test_client"
        )
        self.assertEqual(device_info.device_id, "test_device")
        self.assertEqual(device_info.client_id, "test_client")
        
        # 测试会话
        session = ESP32Session(
            session_id="test_session",
            device_id="test_device",
            user_id="test_user"
        )
        self.assertEqual(session.session_id, "test_session")
        self.assertEqual(session.device_id, "test_device")
        
        # 测试音频上下文
        audio_context = AudioContext(sample_rate=16000, format="opus")
        self.assertEqual(audio_context.sample_rate, 16000)
        self.assertEqual(audio_context.format, "opus")
        
        # 测试对话上下文
        conv_context = ConversationContext()
        self.assertEqual(conv_context.conversation_count, 0)
        self.assertEqual(len(conv_context.dialogue_history), 0)


def run_async_test(test_func):
    """运行异步测试的辅助函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


if __name__ == "__main__":
    print("🧪 开始测试ESP32 WebSocket集成模块（修复版）...")
    print("=" * 70)
    
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestESP32WebSocketManagerFixed,
        TestESP32MessageRouterFixed,
        TestESP32SessionManagerFixed,
        TestESP32ConnectionHandlerFixed,
        TestIntegrationScenariosFixed
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
        print("  ✅ 数据结构 - 枚举类型、数据类验证")
        print("  ✅ 核心逻辑 - 消息处理、状态转换、错误处理")
    else:
        print("❌ 部分测试失败")
        print(f"📊 运行了 {result.testsRun} 个测试")
        print(f"❌ 失败: {len(result.failures)}")
        print(f"⚠️  错误: {len(result.errors)}")
        
        if result.failures:
            print("\n失败的测试:")
            for test, traceback in result.failures:
                print(f"  - {test}")
                print(f"    {traceback.split('AssertionError:')[-1].strip()}")
        
        if result.errors:
            print("\n错误的测试:")
            for test, traceback in result.errors:
                print(f"  - {test}")
                print(f"    {traceback.split('Error:')[-1].strip()}")
    
    print("=" * 70)
