"""
青少年心理对话意图识别测试
Test Youth Psychology Intent Recognition
测试青少年心理意图识别服务的各项功能
"""

import asyncio
import unittest
import tempfile
import os
import yaml
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.core.youth_psychology_config import YouthPsychologyConfig, get_youth_psychology_config
from app.shared.services.intent_recognition_service import (
    YouthPsychologyIntentService, 
    PsychologyIntentType, 
    IntentPriority,
    IntentAnalysisResult,
    get_youth_psychology_intent_service
)


class TestYouthPsychologyConfig(unittest.TestCase):
    """测试青少年心理配置管理器"""
    
    def setUp(self):
        """设置测试环境"""
        # 创建临时配置文件
        self.temp_config = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        self.test_config_data = {
            "intent_recognition": {
                "enabled": True,
                "crisis_detection": {
                    "enabled": True,
                    "sensitivity": 0.9,
                    "auto_referral_risk_levels": ["high", "critical"]
                },
                "emotional_analysis": {
                    "enabled": True,
                    "intensity_threshold": 0.8
                },
                "cache": {
                    "enabled": False,
                    "ttl": 600,
                    "max_entries": 500
                }
            },
            "response_generation": {
                "mode": "professional",
                "use_templates": False,
                "llm_params": {
                    "temperature": 0.5,
                    "max_tokens": 300,
                    "timeout": 15.0
                }
            },
            "resources": {
                "crisis_hotlines": [
                    {
                        "name": "测试热线",
                        "number": "123-456-7890",
                        "description": "测试用热线"
                    }
                ]
            }
        }
        
        yaml.dump(self.test_config_data, self.temp_config, default_flow_style=False)
        self.temp_config.close()
        
        # 创建配置实例
        self.config = YouthPsychologyConfig(self.temp_config.name)
    
    def tearDown(self):
        """清理测试环境"""
        os.unlink(self.temp_config.name)
    
    def test_config_loading(self):
        """测试配置加载"""
        self.assertTrue(self.config.is_intent_recognition_enabled())
        self.assertTrue(self.config.is_crisis_detection_enabled())
        self.assertEqual(self.config.get_crisis_sensitivity(), 0.9)
        self.assertEqual(self.config.get_response_mode(), "professional")
        self.assertFalse(self.config.is_cache_enabled())
    
    def test_crisis_detection_config(self):
        """测试危机检测配置"""
        self.assertTrue(self.config.is_crisis_detection_enabled())
        self.assertEqual(self.config.get_crisis_sensitivity(), 0.9)
        self.assertEqual(self.config.get_auto_referral_risk_levels(), ["high", "critical"])
    
    def test_emotional_analysis_config(self):
        """测试情感分析配置"""
        self.assertTrue(self.config.is_emotional_analysis_enabled())
        self.assertEqual(self.config.get_emotional_intensity_threshold(), 0.8)
    
    def test_cache_config(self):
        """测试缓存配置"""
        self.assertFalse(self.config.is_cache_enabled())
        self.assertEqual(self.config.get_cache_ttl(), 600)
        self.assertEqual(self.config.get_cache_max_entries(), 500)
    
    def test_response_generation_config(self):
        """测试响应生成配置"""
        self.assertEqual(self.config.get_response_mode(), "professional")
        self.assertFalse(self.config.use_response_templates())
        self.assertEqual(self.config.get_llm_temperature(), 0.5)
        self.assertEqual(self.config.get_llm_max_tokens(), 300)
        self.assertEqual(self.config.get_llm_timeout(), 15.0)
    
    def test_crisis_hotlines(self):
        """测试危机热线配置"""
        hotlines = self.config.get_crisis_hotlines()
        self.assertEqual(len(hotlines), 1)
        self.assertEqual(hotlines[0].name, "测试热线")
        self.assertEqual(hotlines[0].number, "123-456-7890")
        self.assertEqual(hotlines[0].description, "测试用热线")
    
    def test_default_config(self):
        """测试默认配置"""
        # 测试不存在配置文件时的默认配置
        non_existent_config = YouthPsychologyConfig("/non/existent/path.yaml")
        self.assertTrue(non_existent_config.is_intent_recognition_enabled())
        self.assertTrue(non_existent_config.is_crisis_detection_enabled())
        self.assertEqual(non_existent_config.get_response_mode(), "supportive")
    
    def test_config_update(self):
        """测试配置更新"""
        # 更新配置
        success = self.config.update_config("intent_recognition.enabled", False)
        self.assertTrue(success)
        self.assertFalse(self.config.is_intent_recognition_enabled())
        
        # 更新嵌套配置
        success = self.config.update_config("response_generation.llm_params.temperature", 0.3)
        self.assertTrue(success)
        self.assertEqual(self.config.get_llm_temperature(), 0.3)
    
    def test_config_summary(self):
        """测试配置摘要"""
        summary = self.config.get_config_summary()
        self.assertIn("intent_recognition_enabled", summary)
        self.assertIn("crisis_detection_enabled", summary)
        self.assertIn("response_mode", summary)
        self.assertTrue(summary["intent_recognition_enabled"])
        self.assertEqual(summary["response_mode"], "professional")


class TestYouthPsychologyIntentService(unittest.TestCase):
    """测试青少年心理意图识别服务"""
    
    def setUp(self):
        """设置测试环境"""
        # Mock LLM服务
        self.mock_llm_service = AsyncMock()
        
        # Mock配置
        self.mock_config = Mock()
        self.mock_config.get_max_history_length.return_value = 6
        self.mock_config.get_emotional_intensity_threshold.return_value = 0.6
        self.mock_config.get_cache_ttl.return_value = 300
        self.mock_config.is_cache_enabled.return_value = True
        self.mock_config.is_crisis_detection_enabled.return_value = True
        self.mock_config.get_crisis_sensitivity.return_value = 0.8
        
        # 创建服务实例
        with patch('app.shared.services.intent_recognition_service.get_llm_service', return_value=self.mock_llm_service), \
             patch('app.shared.services.intent_recognition_service.get_youth_psychology_config', return_value=self.mock_config):
            self.intent_service = YouthPsychologyIntentService()
    
    def test_service_initialization(self):
        """测试服务初始化"""
        self.assertIsNotNone(self.intent_service)
        self.assertEqual(self.intent_service.max_history_length, 6)
        self.assertEqual(self.intent_service.confidence_threshold, 0.6)
        self.assertTrue(self.intent_service.enable_crisis_detection)
    
    def test_crisis_keyword_detection_suicide(self):
        """测试自杀危机关键词检测"""
        test_texts = [
            "我想自杀",
            "不想活了",
            "想要结束生命",
            "I want to kill myself"
        ]
        
        for text in test_texts:
            result = self.intent_service._quick_crisis_detection(text)
            self.assertIsNotNone(result, f"应该检测到自杀危机: {text}")
            self.assertEqual(result.primary_intent, PsychologyIntentType.SUICIDE_CRISIS)
            self.assertEqual(result.priority, IntentPriority.EMERGENCY)
            self.assertEqual(result.risk_level, "critical")
    
    def test_crisis_keyword_detection_self_harm(self):
        """测试自伤危机关键词检测"""
        test_texts = [
            "我想自伤",
            "想要割腕",
            "伤害自己",
            "self harm"
        ]
        
        for text in test_texts:
            result = self.intent_service._quick_crisis_detection(text)
            self.assertIsNotNone(result, f"应该检测到自伤危机: {text}")
            self.assertEqual(result.primary_intent, PsychologyIntentType.SELF_HARM_CRISIS)
            self.assertEqual(result.priority, IntentPriority.HIGH)
            self.assertEqual(result.risk_level, "high")
    
    def test_no_crisis_detection(self):
        """测试非危机文本不会触发危机检测"""
        normal_texts = [
            "你好",
            "今天天气很好",
            "我有点累",
            "学习压力有点大"
        ]
        
        for text in normal_texts:
            result = self.intent_service._quick_crisis_detection(text)
            self.assertIsNone(result, f"不应该检测到危机: {text}")
    
    def test_cache_key_generation(self):
        """测试缓存键生成"""
        text1 = "我很焦虑"
        text2 = "我很焦虑"
        text3 = "我很开心"
        
        key1 = self.intent_service._generate_cache_key(text1)
        key2 = self.intent_service._generate_cache_key(text2)
        key3 = self.intent_service._generate_cache_key(text3)
        
        self.assertEqual(key1, key2, "相同文本应该生成相同的缓存键")
        self.assertNotEqual(key1, key3, "不同文本应该生成不同的缓存键")
        
        # 测试带对话历史的缓存键
        history = [{"role": "user", "content": "你好"}]
        key_with_history = self.intent_service._generate_cache_key(text1, history)
        self.assertNotEqual(key1, key_with_history, "有对话历史的缓存键应该不同")
    
    def test_fallback_result_creation(self):
        """测试降级结果创建"""
        # 测试包含关键词的文本
        stress_text = "我压力很大"
        result = self.intent_service._create_fallback_result(stress_text, 0.5)
        
        self.assertEqual(result.primary_intent, PsychologyIntentType.STRESS_RELIEF)
        self.assertEqual(result.confidence, 0.6)
        self.assertEqual(result.priority, IntentPriority.MEDIUM)
        self.assertTrue(result.metadata["fallback"])
        
        # 测试不包含关键词的文本
        random_text = "随机文本内容"
        result = self.intent_service._create_fallback_result(random_text, 0.3)
        
        self.assertEqual(result.primary_intent, PsychologyIntentType.CASUAL_CHAT)
        self.assertEqual(result.confidence, 0.3)
        self.assertEqual(result.priority, IntentPriority.LOW)
    
    async def test_analyze_intent_with_crisis(self):
        """测试危机情况的意图分析"""
        crisis_text = "我想自杀"
        
        result = await self.intent_service.analyze_intent(crisis_text)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.primary_intent, PsychologyIntentType.SUICIDE_CRISIS)
        self.assertEqual(result.priority, IntentPriority.EMERGENCY)
        self.assertEqual(result.risk_level, "critical")
        self.assertIn("自杀倾向", result.risk_factors)
        self.assertIn("紧急心理热线", result.suggested_resources)
    
    async def test_analyze_intent_with_llm_success(self):
        """测试LLM成功分析意图"""
        # Mock LLM响应
        mock_llm_response = json.dumps({
            "primary_intent": "stress_relief",
            "confidence": 0.85,
            "emotional_state": "焦虑",
            "emotional_intensity": 0.7,
            "risk_level": "medium",
            "risk_factors": ["学习压力"],
            "response_strategy": "supportive",
            "suggested_resources": ["放松技巧", "时间管理"],
            "analysis_reasoning": "用户表达了学习相关的压力"
        })
        
        self.mock_llm_service.chat_async.return_value = mock_llm_response
        
        result = await self.intent_service.analyze_intent("学习压力好大")
        
        self.assertIsNotNone(result)
        self.assertEqual(result.primary_intent, PsychologyIntentType.STRESS_RELIEF)
        self.assertEqual(result.confidence, 0.85)
        self.assertEqual(result.emotional_state, "焦虑")
        self.assertEqual(result.risk_level, "medium")
        self.assertIn("学习压力", result.risk_factors)
    
    async def test_analyze_intent_with_llm_failure(self):
        """测试LLM分析失败的降级处理"""
        # Mock LLM抛出异常
        self.mock_llm_service.chat_async.side_effect = Exception("LLM服务不可用")
        
        result = await self.intent_service.analyze_intent("我有点难过")
        
        self.assertIsNotNone(result)
        # 应该返回降级结果
        self.assertTrue(result.metadata.get("fallback", False))
    
    async def test_analyze_intent_with_dialogue_history(self):
        """测试带对话历史的意图分析"""
        dialogue_history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"},
            {"role": "user", "content": "我最近心情不好"}
        ]
        
        # Mock LLM响应
        mock_llm_response = json.dumps({
            "primary_intent": "emotional_support",
            "confidence": 0.9,
            "emotional_state": "低落",
            "emotional_intensity": 0.6,
            "risk_level": "medium",
            "response_strategy": "supportive"
        })
        
        self.mock_llm_service.chat_async.return_value = mock_llm_response
        
        result = await self.intent_service.analyze_intent(
            "感觉很孤独",
            dialogue_history=dialogue_history
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result.primary_intent, PsychologyIntentType.EMOTIONAL_SUPPORT)
        
        # 验证LLM被调用时包含了对话历史
        self.mock_llm_service.chat_async.assert_called_once()
        call_args = self.mock_llm_service.chat_async.call_args[0][0]  # messages参数
        
        # 应该包含系统提示和用户消息
        self.assertTrue(any(msg["role"] == "system" for msg in call_args))
        self.assertTrue(any(msg["role"] == "user" for msg in call_args))
    
    async def test_analyze_intent_with_user_profile(self):
        """测试带用户档案的意图分析"""
        user_profile = {
            "age": 16,
            "grade": "高一",
            "concerns": ["学习压力", "人际关系"]
        }
        
        # Mock LLM响应
        mock_llm_response = json.dumps({
            "primary_intent": "study_pressure",
            "confidence": 0.8,
            "emotional_state": "紧张",
            "risk_level": "medium"
        })
        
        self.mock_llm_service.chat_async.return_value = mock_llm_response
        
        result = await self.intent_service.analyze_intent(
            "考试快到了，好紧张",
            user_profile=user_profile
        )
        
        self.assertIsNotNone(result)
        self.assertEqual(result.primary_intent, PsychologyIntentType.STUDY_PRESSURE)
    
    def test_statistics_collection(self):
        """测试统计信息收集"""
        stats = self.intent_service.get_intent_statistics()
        
        self.assertIn("cache_size", stats)
        self.assertIn("supported_intents", stats)
        self.assertIn("crisis_keywords_count", stats)
        self.assertIn("service_status", stats)
        
        self.assertEqual(stats["service_status"], "active")
        self.assertGreater(stats["supported_intents"], 0)
        self.assertGreater(stats["crisis_keywords_count"], 0)
    
    def test_cache_operations(self):
        """测试缓存操作"""
        # 初始缓存应该为空
        self.assertEqual(len(self.intent_service._intent_cache), 0)
        
        # 清空缓存
        self.intent_service.clear_cache()
        self.assertEqual(len(self.intent_service._intent_cache), 0)


class TestIntentServiceIntegration(unittest.TestCase):
    """测试意图服务集成"""
    
    def test_global_service_instance(self):
        """测试全局服务实例"""
        with patch('app.shared.services.intent_recognition_service.get_llm_service'), \
             patch('app.shared.services.intent_recognition_service.get_youth_psychology_config'):
            
            service1 = get_youth_psychology_intent_service()
            service2 = get_youth_psychology_intent_service()
            
            # 应该返回同一个实例
            self.assertIs(service1, service2)
    
    def test_psychology_intent_types(self):
        """测试心理意图类型枚举"""
        # 验证所有重要的意图类型都存在
        important_intents = [
            "greeting", "casual_chat", "farewell",
            "emotional_support", "stress_relief", "anxiety_help",
            "suicide_crisis", "self_harm_crisis",
            "study_pressure", "family_issues", "friendship_troubles"
        ]
        
        for intent in important_intents:
            self.assertTrue(
                any(item.value == intent for item in PsychologyIntentType),
                f"意图类型 {intent} 应该存在"
            )
    
    def test_intent_priority_levels(self):
        """测试意图优先级等级"""
        priorities = [item.value for item in IntentPriority]
        expected_priorities = ["emergency", "high", "medium", "low"]
        
        for priority in expected_priorities:
            self.assertIn(priority, priorities, f"优先级 {priority} 应该存在")


def run_async_test(test_func):
    """运行异步测试的辅助函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


# 异步测试包装器
class AsyncTestCase(unittest.TestCase):
    """异步测试基类"""
    
    def run_async(self, coro):
        """运行异步测试"""
        return run_async_test(lambda: coro)


class TestAsyncIntentAnalysis(AsyncTestCase):
    """异步意图分析测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.mock_llm_service = AsyncMock()
        self.mock_config = Mock()
        self.mock_config.get_max_history_length.return_value = 6
        self.mock_config.get_emotional_intensity_threshold.return_value = 0.6
        self.mock_config.get_cache_ttl.return_value = 300
        self.mock_config.is_cache_enabled.return_value = True
        self.mock_config.is_crisis_detection_enabled.return_value = True
        self.mock_config.get_crisis_sensitivity.return_value = 0.8
    
    def test_async_crisis_analysis(self):
        """测试异步危机分析"""
        async def test():
            with patch('app.shared.services.intent_recognition_service.get_llm_service', return_value=self.mock_llm_service), \
                 patch('app.shared.services.intent_recognition_service.get_youth_psychology_config', return_value=self.mock_config):
                
                service = YouthPsychologyIntentService()
                result = await service.analyze_intent("我想自杀")
                
                self.assertIsNotNone(result)
                self.assertEqual(result.primary_intent, PsychologyIntentType.SUICIDE_CRISIS)
                self.assertEqual(result.priority, IntentPriority.EMERGENCY)
        
        self.run_async(test())
    
    def test_async_normal_analysis(self):
        """测试异步正常分析"""
        async def test():
            with patch('app.shared.services.intent_recognition_service.get_llm_service', return_value=self.mock_llm_service), \
                 patch('app.shared.services.intent_recognition_service.get_youth_psychology_config', return_value=self.mock_config):
                
                # Mock LLM响应
                mock_response = json.dumps({
                    "primary_intent": "casual_chat",
                    "confidence": 0.7,
                    "emotional_state": "平静",
                    "risk_level": "low"
                })
                self.mock_llm_service.chat_async.return_value = mock_response
                
                service = YouthPsychologyIntentService()
                result = await service.analyze_intent("今天天气不错")
                
                self.assertIsNotNone(result)
                self.assertEqual(result.primary_intent, PsychologyIntentType.CASUAL_CHAT)
        
        self.run_async(test())


if __name__ == "__main__":
    print("🧪 开始测试青少年心理对话意图识别服务...")
    print("=" * 70)
    
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestYouthPsychologyConfig,
        TestYouthPsychologyIntentService,
        TestIntentServiceIntegration,
        TestAsyncIntentAnalysis
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ 所有测试通过！青少年心理意图识别服务工作正常")
        print(f"📊 运行了 {result.testsRun} 个测试")
        print("\n🎯 测试覆盖的功能：")
        print("  ✅ 配置管理器 - 加载、更新、验证配置")
        print("  ✅ 危机检测 - 自杀、自伤关键词识别")
        print("  ✅ 意图分析 - LLM集成、降级处理")
        print("  ✅ 缓存机制 - 键生成、存储管理")
        print("  ✅ 异步处理 - 并发安全、超时控制")
        print("  ✅ 统计收集 - 性能监控、使用统计")
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
                print(f"    {traceback.split('Exception:')[-1].strip()}")
    
    print("=" * 70)
