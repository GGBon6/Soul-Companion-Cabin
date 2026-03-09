#!/usr/bin/env python3
"""
新架构验证脚本
Test New Architecture
验证重构后的模块化架构是否正常工作
"""

import sys
import asyncio


def test_imports():
    """测试所有关键导入"""
    print("🧪 测试导入...")
    
    try:
        # 测试共享服务层
        from app.shared.services import get_llm_service, get_asr_service, get_tts_service
        print("  ✅ app.shared.services 导入成功")
        
        # 测试 Web 层
        from app.web.handlers import WebSocketHandler
        from app.web.message_handlers import BaseMessageHandler, TextMessageHandler, VoiceMessageHandler
        from app.web.auth import LoginHandler, RegisterHandler, ProfileHandler
        from app.web.features import CharacterHandler, MoodHandler, DiaryHandler, StoryHandler
        print("  ✅ app.web 导入成功")
        
        # 测试设备层
        from app.devices import ESP32Adapter, get_esp32_adapter, ESP32Protocol, get_esp32_protocol
        from app.devices import ESP32ChatService, get_esp32_chat_service
        print("  ✅ app.devices 导入成功")
        
        # 测试业务层
        from app.business.diary import get_diary_service, DiaryEntry
        from app.business.story import get_story_service, Story
        from app.business.chat import get_proactive_chat_service, ChatMessage
        print("  ✅ app.business 导入成功")
        
        # 测试 Agent 层
        from app.shared.agents import get_memory_agent, PureChatAgent
        from app.shared.agents.base_agent import BaseAgent, AgentMode
        print("  ✅ app.shared.agents 导入成功")
        
        return True
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_services():
    """测试服务初始化"""
    print("\n🧪 测试服务初始化...")
    
    try:
        from app.shared.services import get_llm_service
        llm_service = get_llm_service()
        print(f"  ✅ LLM 服务初始化成功: {type(llm_service).__name__}")
        
        from app.business.diary import get_diary_service
        diary_service = get_diary_service()
        print(f"  ✅ 日记服务初始化成功: {type(diary_service).__name__}")
        
        from app.business.story import get_story_service
        story_service = get_story_service()
        print(f"  ✅ 故事服务初始化成功: {type(story_service).__name__}")
        
        from app.devices import get_esp32_adapter
        esp32_adapter = get_esp32_adapter()
        print(f"  ✅ ESP32 适配器初始化成功: {type(esp32_adapter).__name__}")
        
        return True
    except Exception as e:
        print(f"  ❌ 服务初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_message_handlers():
    """测试消息处理器"""
    print("\n🧪 测试消息处理器...")
    
    try:
        from app.web.message_handlers import BaseMessageHandler, TextMessageHandler, VoiceMessageHandler
        from app.web.auth import LoginHandler, RegisterHandler, ProfileHandler
        from app.web.features import CharacterHandler, MoodHandler, DiaryHandler, StoryHandler
        
        handlers = [
            ("TextMessageHandler", TextMessageHandler),
            ("VoiceMessageHandler", VoiceMessageHandler),
            ("LoginHandler", LoginHandler),
            ("RegisterHandler", RegisterHandler),
            ("ProfileHandler", ProfileHandler),
            ("CharacterHandler", CharacterHandler),
            ("MoodHandler", MoodHandler),
            ("DiaryHandler", DiaryHandler),
            ("StoryHandler", StoryHandler),
        ]
        
        for name, handler_class in handlers:
            # 检查是否继承自 BaseMessageHandler
            if issubclass(handler_class, BaseMessageHandler):
                print(f"  ✅ {name} 继承自 BaseMessageHandler")
            else:
                print(f"  ❌ {name} 未继承自 BaseMessageHandler")
                return False
        
        return True
    except Exception as e:
        print(f"  ❌ 消息处理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("🚀 新架构验证脚本")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(("导入测试", test_imports()))
    results.append(("服务初始化测试", test_services()))
    results.append(("消息处理器测试", test_message_handlers()))
    
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
        print("\n🎉 所有测试通过！新架构已正常工作。")
        return 0
    else:
        print("\n⚠️ 部分测试失败，请检查上述错误。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
