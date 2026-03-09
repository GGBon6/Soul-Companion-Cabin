"""
ESP32新架构集成示例
ESP32 New Architecture Integration Demo
演示如何使用新的消息注册表、设备会话管理和处理器框架
"""

import asyncio
import json
import logging
from unittest.mock import Mock, AsyncMock
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.devices.esp32 import (
    ESP32MessageRegistry, get_esp32_message_registry,
    ESP32DeviceSession, ESP32SessionManager, get_esp32_session_manager,
    ESP32MessageType, ESP32ConnectionState,
    ESP32HelloHandler
)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ESP32ArchitectureDemo:
    """ESP32新架构演示类"""
    
    def __init__(self):
        self.message_registry = get_esp32_message_registry()
        self.session_manager = get_esp32_session_manager()
        
    async def demo_hello_message_processing(self):
        """演示Hello消息处理流程"""
        print("\n🚀 演示Hello消息处理流程")
        print("=" * 50)
        
        # 1. 创建模拟WebSocket连接
        mock_websocket = Mock()
        mock_websocket.remote_address = ("192.168.1.100", 12345)
        mock_websocket.closed = False
        mock_websocket.send = AsyncMock()
        
        # 2. 创建设备会话
        device_session = ESP32DeviceSession(
            websocket=mock_websocket,
            device_id="demo_esp32_001",
            client_id="demo_client"
        )
        
        # 3. 添加到会话管理器
        self.session_manager.add_session(device_session)
        print(f"✅ 设备会话已创建: {device_session.device_id}")
        print(f"📊 当前活跃会话数: {self.session_manager.get_session_count()}")
        
        # 4. 构造Hello消息
        hello_message = {
            "type": "hello",
            "version": "2.0",
            "audio_params": {
                "sample_rate": 16000,
                "frame_duration": 60,
                "format": "opus",
                "channels": 1
            },
            "capabilities": ["audio_input", "audio_output", "tts", "asr"],
            "features": {
                "mcp": True,
                "wakeup_word": True
            },
            "device_type": "esp32",
            "firmware_version": "1.2.3",
            "hardware_version": "v2.1"
        }
        
        print(f"📨 构造Hello消息: {json.dumps(hello_message, indent=2, ensure_ascii=False)}")
        
        # 5. 通过消息注册表处理消息
        success = await self.message_registry.process_message(
            device_session, hello_message
        )
        
        if success:
            print("✅ Hello消息处理成功")
            print(f"🔐 设备认证状态: {device_session.is_authenticated}")
            print(f"🔗 连接状态: {device_session.connection_state.value}")
            print(f"🎵 音频参数: {device_session.audio_params}")
            print(f"⚡ 设备能力: {device_session.capabilities}")
            print(f"🎯 设备特性: {device_session.features}")
        else:
            print("❌ Hello消息处理失败")
        
        # 6. 验证发送的响应消息
        if mock_websocket.send.called:
            call_args = mock_websocket.send.call_args[0][0]
            response_message = json.loads(call_args)
            print(f"📤 服务器响应: {json.dumps(response_message, indent=2, ensure_ascii=False)}")
        
        return device_session
    
    async def demo_message_registry_features(self):
        """演示消息注册表功能"""
        print("\n🔧 演示消息注册表功能")
        print("=" * 50)
        
        # 1. 显示支持的消息类型
        supported_types = self.message_registry.get_supported_types()
        print(f"📋 支持的消息类型: {supported_types}")
        
        # 2. 显示处理器信息
        handler_info = self.message_registry.get_handler_info()
        print("🛠️  处理器映射:")
        for msg_type, handler_class in handler_info.items():
            print(f"   {msg_type} -> {handler_class}")
        
        # 3. 获取特定处理器
        hello_handler = self.message_registry.get_handler("hello")
        print(f"🎯 Hello处理器: {hello_handler.__class__.__name__}")
        print(f"📝 处理器消息类型: {hello_handler.message_type.value}")
        
        # 4. 测试未知消息类型
        unknown_handler = self.message_registry.get_handler("unknown_type")
        print(f"❓ 未知处理器: {unknown_handler}")
    
    async def demo_session_management(self):
        """演示会话管理功能"""
        print("\n👥 演示会话管理功能")
        print("=" * 50)
        
        # 创建多个模拟会话
        sessions = []
        for i in range(3):
            mock_websocket = Mock()
            mock_websocket.remote_address = (f"192.168.1.{100+i}", 12345+i)
            mock_websocket.closed = False
            
            session = ESP32DeviceSession(
                websocket=mock_websocket,
                device_id=f"demo_device_{i:03d}",
                client_id=f"demo_client_{i}"
            )
            
            # 设置不同的连接状态
            if i == 0:
                session.set_connection_state(ESP32ConnectionState.ACTIVE)
            elif i == 1:
                session.set_connection_state(ESP32ConnectionState.AUTHENTICATED)
            else:
                session.set_connection_state(ESP32ConnectionState.HELLO_PENDING)
            
            sessions.append(session)
            self.session_manager.add_session(session)
        
        print(f"📊 总会话数: {self.session_manager.get_session_count()}")
        
        # 显示所有会话信息
        all_sessions = self.session_manager.get_all_sessions()
        print("\n📋 所有会话信息:")
        for session in all_sessions:
            print(f"   设备: {session.device_id}")
            print(f"   状态: {session.connection_state.value}")
            print(f"   地址: {session.remote_address}")
            print(f"   空闲时间: {session.get_idle_time():.2f}秒")
            print()
        
        # 按设备ID查找会话
        target_session = self.session_manager.get_session("demo_device_001")
        if target_session:
            print(f"🔍 找到设备 demo_device_001: {target_session.session_id}")
        
        # 按WebSocket查找会话
        websocket_session = self.session_manager.get_session_by_websocket(sessions[0].websocket)
        if websocket_session:
            print(f"🔍 通过WebSocket找到会话: {websocket_session.device_id}")
        
        # 移除一个会话
        removed_session = self.session_manager.remove_session("demo_device_002")
        if removed_session:
            print(f"🗑️  移除会话: {removed_session.device_id}")
            print(f"📊 剩余会话数: {self.session_manager.get_session_count()}")
    
    async def demo_error_handling(self):
        """演示错误处理"""
        print("\n⚠️  演示错误处理")
        print("=" * 50)
        
        # 创建模拟会话
        mock_websocket = Mock()
        mock_websocket.remote_address = ("192.168.1.200", 12345)
        mock_websocket.closed = False
        mock_websocket.send = AsyncMock()
        
        device_session = ESP32DeviceSession(
            websocket=mock_websocket,
            device_id="error_test_device",
            client_id="error_test_client"
        )
        
        # 1. 测试无效的Hello消息
        invalid_hello = {
            "type": "hello"
            # 缺少version字段
        }
        
        print("🧪 测试无效Hello消息处理...")
        success = await self.message_registry.process_message(
            device_session, invalid_hello
        )
        
        if not success:
            print("✅ 正确拒绝了无效的Hello消息")
        else:
            print("❌ 意外接受了无效的Hello消息")
        
        # 2. 测试未知消息类型
        unknown_message = {
            "type": "unknown_message_type",
            "data": "some data"
        }
        
        print("🧪 测试未知消息类型处理...")
        success = await self.message_registry.process_message(
            device_session, unknown_message
        )
        
        if not success:
            print("✅ 正确拒绝了未知消息类型")
        else:
            print("❌ 意外接受了未知消息类型")
    
    async def run_full_demo(self):
        """运行完整演示"""
        print("🎭 ESP32新架构完整演示")
        print("=" * 60)
        
        try:
            # 1. 演示消息注册表功能
            await self.demo_message_registry_features()
            
            # 2. 演示Hello消息处理
            device_session = await self.demo_hello_message_processing()
            
            # 3. 演示会话管理
            await self.demo_session_management()
            
            # 4. 演示错误处理
            await self.demo_error_handling()
            
            print("\n🎉 演示完成！")
            print("=" * 60)
            print("✅ 消息注册表系统正常工作")
            print("✅ 设备会话管理正常工作") 
            print("✅ Hello消息处理器正常工作")
            print("✅ 错误处理机制正常工作")
            print("=" * 60)
            
        except Exception as e:
            print(f"\n❌ 演示过程中发生错误: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数"""
    demo = ESP32ArchitectureDemo()
    await demo.run_full_demo()


if __name__ == "__main__":
    # 运行演示
    asyncio.run(main())
