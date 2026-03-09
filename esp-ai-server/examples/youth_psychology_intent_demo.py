"""
青少年心理对话意图识别演示
Youth Psychology Intent Recognition Demo
展示青少年心理意图识别服务的功能和使用方法
"""

import asyncio
import json
import sys
import os
from typing import List, Dict

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.core.youth_psychology_config import get_youth_psychology_config
from app.shared.services.intent_recognition_service import get_youth_psychology_intent_service
from app.devices.esp32.services.intent_processor import get_esp32_intent_processor


class YouthPsychologyIntentDemo:
    """青少年心理意图识别演示"""
    
    def __init__(self):
        self.config = get_youth_psychology_config()
        self.intent_service = get_youth_psychology_intent_service()
        self.esp32_processor = get_esp32_intent_processor("demo_device_001")
        
        # 测试用例
        self.test_cases = [
            # 基础对话
            {
                "category": "基础对话",
                "cases": [
                    "你好",
                    "今天天气不错",
                    "再见，谢谢你的帮助"
                ]
            },
            
            # 学习压力
            {
                "category": "学习压力",
                "cases": [
                    "考试快到了，我好紧张",
                    "学习压力好大，感觉快撑不住了",
                    "父母总是要求我考第一名"
                ]
            },
            
            # 人际关系
            {
                "category": "人际关系",
                "cases": [
                    "我和朋友吵架了，很难过",
                    "感觉同学们都不喜欢我",
                    "和父母的关系很紧张"
                ]
            },
            
            # 情感支持
            {
                "category": "情感支持",
                "cases": [
                    "我感觉很孤独",
                    "最近心情很低落",
                    "觉得自己什么都做不好"
                ]
            },
            
            # 危机情况（模拟，仅用于测试检测机制）
            {
                "category": "危机检测",
                "cases": [
                    "我想自伤",  # 自伤危机
                    "感觉绝望，没有希望",  # 严重抑郁
                    "被同学霸凌了"  # 霸凌问题
                ]
            }
        ]
    
    async def run_demo(self):
        """运行演示"""
        print("🎭 青少年心理对话意图识别演示")
        print("=" * 60)
        
        # 显示配置信息
        await self._show_configuration()
        
        # 运行测试用例
        await self._run_test_cases()
        
        # 显示统计信息
        await self._show_statistics()
        
        # 交互式测试
        await self._interactive_test()
    
    async def _show_configuration(self):
        """显示配置信息"""
        print("\n📋 当前配置:")
        config_summary = self.config.get_config_summary()
        
        for key, value in config_summary.items():
            print(f"  • {key}: {value}")
        
        print(f"\n🔧 危机检测敏感度: {self.config.get_crisis_sensitivity()}")
        print(f"🔧 情感强度阈值: {self.config.get_emotional_intensity_threshold()}")
        print(f"🔧 响应模式: {self.config.get_response_mode()}")
    
    async def _run_test_cases(self):
        """运行测试用例"""
        print("\n🧪 测试用例演示:")
        print("-" * 60)
        
        for category_data in self.test_cases:
            category = category_data["category"]
            cases = category_data["cases"]
            
            print(f"\n📂 {category}")
            print("-" * 30)
            
            for i, text in enumerate(cases, 1):
                print(f"\n{i}. 用户输入: \"{text}\"")
                
                try:
                    # 使用意图识别服务分析
                    result = await self.intent_service.analyze_intent(text)
                    
                    # 显示分析结果
                    self._display_intent_result(result)
                    
                    # 如果是危机情况，显示特别提醒
                    if result.risk_level in ["high", "critical"]:
                        print("   ⚠️  高风险检测 - 需要特别关注！")
                    
                except Exception as e:
                    print(f"   ❌ 分析失败: {e}")
                
                print()
    
    def _display_intent_result(self, result):
        """显示意图分析结果"""
        print(f"   🎯 意图类型: {result.primary_intent.value}")
        print(f"   📊 置信度: {result.confidence:.2f}")
        print(f"   💭 情感状态: {result.emotional_state or '未知'}")
        print(f"   📈 情感强度: {result.emotional_intensity:.2f}")
        print(f"   ⚡ 优先级: {result.priority.value}")
        print(f"   🚨 风险等级: {result.risk_level}")
        
        if result.risk_factors:
            print(f"   ⚠️  风险因素: {', '.join(result.risk_factors)}")
        
        if result.suggested_resources:
            print(f"   💡 建议资源: {', '.join(result.suggested_resources[:2])}...")
        
        print(f"   ⏱️  处理时间: {result.processing_time*1000:.1f}ms")
    
    async def _show_statistics(self):
        """显示统计信息"""
        print("\n📊 服务统计信息:")
        print("-" * 30)
        
        stats = self.intent_service.get_intent_statistics()
        
        print(f"缓存大小: {stats['cache_size']}")
        print(f"支持意图类型: {stats['supported_intents']}")
        print(f"危机关键词数量: {stats['crisis_keywords_count']}")
        print(f"服务状态: {stats['service_status']}")
        
        # ESP32处理器统计
        esp32_stats = self.esp32_processor.get_statistics()
        print(f"\nESP32处理器统计:")
        print(f"总请求数: {esp32_stats['requests']['total']}")
        print(f"成功率: {esp32_stats['requests']['success_rate']}%")
    
    async def _interactive_test(self):
        """交互式测试"""
        print("\n🎮 交互式测试 (输入 'quit' 退出):")
        print("-" * 40)
        
        dialogue_history = []
        
        while True:
            try:
                user_input = input("\n👤 请输入: ").strip()
                
                if user_input.lower() in ['quit', 'exit', '退出']:
                    print("👋 再见！")
                    break
                
                if not user_input:
                    continue
                
                print("🤔 分析中...")
                
                # 分析意图
                result = await self.intent_service.analyze_intent(
                    user_text=user_input,
                    dialogue_history=dialogue_history
                )
                
                # 显示结果
                print(f"\n🎯 分析结果:")
                self._display_intent_result(result)
                
                # 使用ESP32意图处理器生成回复
                from app.devices.esp32.services.intent_processor import IntentRequest
                
                intent_request = IntentRequest(
                    user_text=user_input,
                    device_id="demo_device_001",
                    session_id="demo_session",
                    dialogue_history=dialogue_history
                )
                
                intent_response = await self.esp32_processor.process_intent(intent_request)
                
                print(f"\n🤖 AI回复: {intent_response.response_text[:200]}...")
                
                # 更新对话历史
                dialogue_history.append({"role": "user", "content": user_input})
                dialogue_history.append({"role": "assistant", "content": intent_response.response_text})
                
                # 保持历史长度
                if len(dialogue_history) > 10:
                    dialogue_history = dialogue_history[-10:]
                
                # 危机提醒
                if result.risk_level in ["high", "critical"]:
                    print("\n⚠️  检测到高风险情况，建议寻求专业帮助！")
                    if result.suggested_resources:
                        print("📞 建议联系:")
                        for resource in result.suggested_resources[:3]:
                            print(f"   • {resource}")
                
            except KeyboardInterrupt:
                print("\n\n👋 用户中断，再见！")
                break
            except Exception as e:
                print(f"\n❌ 处理错误: {e}")
    
    async def _demo_esp32_integration(self):
        """演示ESP32集成"""
        print("\n🔌 ESP32集成演示:")
        print("-" * 30)
        
        test_messages = [
            "你好，我是新用户",
            "我最近学习压力很大",
            "感觉有点焦虑"
        ]
        
        for msg in test_messages:
            print(f"\n📱 ESP32设备输入: \"{msg}\"")
            
            # 创建意图请求
            from app.devices.esp32.services.intent_processor import IntentRequest
            
            request = IntentRequest(
                user_text=msg,
                device_id="esp32_demo_001",
                session_id="esp32_session_001"
            )
            
            # 处理意图
            result = await self.esp32_processor.process_intent(request)
            
            print(f"🎯 识别意图: {result.intent_result.primary_intent.value}")
            print(f"🤖 回复: {result.response_text[:100]}...")
            print(f"⏱️  处理时间: {result.total_time*1000:.1f}ms")


async def main():
    """主函数"""
    try:
        demo = YouthPsychologyIntentDemo()
        await demo.run_demo()
    except KeyboardInterrupt:
        print("\n\n👋 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示运行错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("🚀 启动青少年心理对话意图识别演示...")
    
    # 检查依赖
    try:
        import yaml
        print("✅ 依赖检查通过")
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install pyyaml")
        sys.exit(1)
    
    # 运行演示
    asyncio.run(main())
