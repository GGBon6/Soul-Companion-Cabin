#!/usr/bin/env python3
"""
ESP32 设备模块测试
Test ESP32 Device Module
验证 ESP32 设备相关功能是否正常工作
"""

import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

def test_esp32_imports():
    """测试 ESP32 模块导入"""
    print("🧪 测试 ESP32 模块导入...")
    
    try:
        from app.devices import (
            ESP32Adapter, get_esp32_adapter,
            ESP32Protocol, get_esp32_protocol,
            ESP32ChatService, get_esp32_chat_service,
            ESP32Config, get_esp32_config
        )
        print("  ✅ ESP32 核心模块导入成功")
        
        # 协议模块已完全迁移到ESP32专用模块
        # WebSocket协议：app.devices.esp32.websocket
        # 音频协议：app.devices.esp32.audio
        print("  ✅ 协议模块已迁移到ESP32专用模块")
        
        from app.devices import OtaServer, OTAServer
        print("  ✅ OTA 模块导入成功")
        
        return True
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_esp32_initialization():
    """测试 ESP32 服务初始化"""
    print("\n🧪 测试 ESP32 服务初始化...")
    
    try:
        from app.devices import get_esp32_adapter, get_esp32_protocol, get_esp32_chat_service
        
        # 测试适配器初始化
        adapter = get_esp32_adapter()
        print(f"  ✅ ESP32 适配器初始化成功: {type(adapter).__name__}")
        
        # 测试协议初始化
        protocol = get_esp32_protocol()
        print(f"  ✅ ESP32 协议初始化成功: {type(protocol).__name__}")
        
        # 测试聊天服务初始化
        chat_service = get_esp32_chat_service()
        print(f"  ✅ ESP32 聊天服务初始化成功: {type(chat_service).__name__}")
        
        return True
    except Exception as e:
        print(f"  ❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_esp32_protocol_parsing():
    """测试 ESP32 协议解析"""
    print("\n🧪 测试 ESP32 协议解析...")
    
    try:
        from app.devices import get_esp32_protocol
        import json
        
        protocol = get_esp32_protocol()
        
        # 测试 Hello 消息解析
        hello_msg = json.dumps({
            "type": "hello",
            "version": 2,
            "audio_params": {
                "sample_rate": 16000,
                "frame_duration": 20
            }
        })
        
        result = protocol.parse_hello_message(hello_msg)
        if result and result.get("type") == "hello":
            print("  ✅ Hello 消息解析成功")
        else:
            print("  ❌ Hello 消息解析失败")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ 协议解析测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_esp32_config():
    """测试 ESP32 配置"""
    print("\n🧪 测试 ESP32 配置...")

    try:
        from app.devices import get_esp32_config
        
        config = get_esp32_config()
        device_config = config.get_device_config()
        print(f"  ✅ ESP32 配置加载成功")
        print(f"     - 设备超时: {device_config.get('connection_timeout')}s")
        print(f"     - 心跳间隔: {device_config.get('heartbeat_interval')}s")

        return True
    except Exception as e:
        print(f"  ❌ 配置加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("🚀 ESP32 设备模块测试")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(("导入测试", test_esp32_imports()))
    results.append(("初始化测试", test_esp32_initialization()))
    results.append(("协议解析测试", test_esp32_protocol_parsing()))
    results.append(("配置测试", test_esp32_config()))
    
    # 打印总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    print(f"\n总体: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有 ESP32 测试通过！设备模块正常工作。")
        return 0
    else:
        print("\n⚠️ 部分测试失败，请检查上述错误。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
