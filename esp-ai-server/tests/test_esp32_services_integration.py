"""
ESP32服务集成模块测试
Test ESP32 Services Integration Modules
测试ASR、TTS、意图处理等服务集成组件
"""

import asyncio
import unittest
import time
import numpy as np
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.devices.esp32.services import (
    ESP32ASRServiceIntegration, get_esp32_asr_integration,
    ESP32TTSServiceIntegration, TTSRequest, get_esp32_tts_integration,
    ESP32IntentProcessor, IntentRequest, get_esp32_intent_processor,
    ESP32SpeechInteractionCoordinator, InteractionRequest, get_esp32_speech_coordinator,
    ESP32ServiceConnectionManager, get_esp32_service_manager,
    ESP32AudioFormatConverter, get_esp32_audio_converter
)
from app.devices.esp32.audio import AudioFrame


class TestESP32ASRServiceIntegration(unittest.TestCase):
    """测试ESP32 ASR服务集成器"""
    
    def setUp(self):
        """设置测试环境"""
        self.device_id = "test_asr_device_001"
        self.asr_integration = ESP32ASRServiceIntegration(self.device_id)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.asr_integration.device_id, self.device_id)
        self.assertEqual(self.asr_integration.statistics.total_requests, 0)
        self.assertTrue(self.asr_integration.enable_silence_filter)
    
    def test_audio_frame_merging(self):
        """测试音频帧合并"""
        # 创建测试音频帧
        frames = []
        for i in range(3):
            frame = AudioFrame(
                data=bytes([i] * 100),
                timestamp=time.time(),
                sequence_number=i + 1,
                frame_size=100,
                sample_rate=16000,
                channels=1,
                format="pcm"
            )
            frames.append(frame)
        
        # 测试合并
        merged_data = self.asr_integration._merge_audio_frames(frames)
        
        self.assertEqual(len(merged_data), 300)
        self.assertEqual(merged_data[:100], bytes([0] * 100))
        self.assertEqual(merged_data[100:200], bytes([1] * 100))
        self.assertEqual(merged_data[200:300], bytes([2] * 100))
    
    def test_audio_validation(self):
        """测试音频数据验证"""
        # 创建测试帧
        frame = AudioFrame(
            data=b'\x01' * 2000,  # 足够大的数据
            timestamp=time.time(),
            sequence_number=1,
            frame_size=2000,
            sample_rate=16000,
            channels=1,
            format="pcm"
        )
        
        # 有效数据
        self.assertTrue(self.asr_integration._validate_audio_data(frame.data, [frame]))
        
        # 无效数据（太小）
        small_frame = AudioFrame(
            data=b'\x01' * 100,  # 太小
            timestamp=time.time(),
            sequence_number=1,
            frame_size=100,
            sample_rate=16000,
            channels=1,
            format="pcm"
        )
        
        self.assertFalse(self.asr_integration._validate_audio_data(small_frame.data, [small_frame]))
    
    def test_silence_detection(self):
        """测试静音检测"""
        # PCM静音数据
        silence_data = np.zeros(1000, dtype=np.int16).tobytes()
        frame = AudioFrame(
            data=silence_data,
            timestamp=time.time(),
            sequence_number=1,
            frame_size=len(silence_data),
            sample_rate=16000,
            channels=1,
            format="pcm"
        )
        
        self.assertTrue(self.asr_integration._is_silence_audio(silence_data, [frame]))
        
        # 有声音的数据
        speech_data = np.random.randint(-1000, 1000, 1000, dtype=np.int16).tobytes()
        frame.data = speech_data
        
        self.assertFalse(self.asr_integration._is_silence_audio(speech_data, [frame]))
    
    def test_confidence_estimation(self):
        """测试置信度估算"""
        # 测试不同文本长度的置信度
        confidence1 = self.asr_integration._estimate_confidence("你好", 0.5, 1.0)
        confidence2 = self.asr_integration._estimate_confidence("你好，今天天气怎么样？", 0.5, 1.0)
        confidence3 = self.asr_integration._estimate_confidence("", 0.5, 1.0)
        
        self.assertGreater(confidence2, confidence1)  # 长文本置信度更高
        self.assertEqual(confidence3, 0.0)  # 空文本置信度为0
        self.assertLessEqual(confidence1, 1.0)
        self.assertGreaterEqual(confidence1, 0.0)
    
    def test_statistics(self):
        """测试统计信息"""
        # 更新统计
        self.asr_integration.statistics.total_requests = 10
        self.asr_integration.statistics.successful_requests = 8
        self.asr_integration.statistics.failed_requests = 2
        
        stats = self.asr_integration.get_statistics()
        
        self.assertEqual(stats["device_id"], self.device_id)
        self.assertEqual(stats["requests"]["total"], 10)
        self.assertEqual(stats["requests"]["successful"], 8)
        self.assertEqual(stats["requests"]["success_rate"], 80.0)


class TestESP32TTSServiceIntegration(unittest.TestCase):
    """测试ESP32 TTS服务集成器"""
    
    def setUp(self):
        """设置测试环境"""
        self.device_id = "test_tts_device_001"
        # Mock TTS服务以避免实际调用
        with patch('app.shared.services.tts_service.get_tts_service'):
            self.tts_integration = ESP32TTSServiceIntegration(self.device_id)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.tts_integration.device_id, self.device_id)
        self.assertEqual(self.tts_integration.sample_rate, 16000)
        self.assertEqual(self.tts_integration.frame_duration, 60)
        self.assertEqual(self.tts_integration.samples_per_frame, 960)
    
    def test_request_validation(self):
        """测试请求验证"""
        # 有效请求
        valid_request = TTSRequest(text="你好，世界！")
        self.assertTrue(self.tts_integration._validate_request(valid_request))
        
        # 无效请求（文本太短）
        invalid_request = TTSRequest(text="")
        self.assertFalse(self.tts_integration._validate_request(invalid_request))
        
        # 无效请求（文本太长）
        long_text = "a" * 1000
        long_request = TTSRequest(text=long_text)
        self.assertFalse(self.tts_integration._validate_request(long_request))
    
    def test_cache_key_generation(self):
        """测试缓存键生成"""
        request1 = TTSRequest(text="你好", voice="voice1", speech_rate=1.0)
        request2 = TTSRequest(text="你好", voice="voice1", speech_rate=1.0)
        request3 = TTSRequest(text="你好", voice="voice2", speech_rate=1.0)
        
        key1 = self.tts_integration._generate_cache_key(request1)
        key2 = self.tts_integration._generate_cache_key(request2)
        key3 = self.tts_integration._generate_cache_key(request3)
        
        self.assertEqual(key1, key2)  # 相同参数生成相同键
        self.assertNotEqual(key1, key3)  # 不同参数生成不同键
    
    def test_audio_format_conversion(self):
        """测试音频格式转换"""
        # 创建模拟WAV数据
        wav_header = b'RIFF' + b'\x24\x00\x00\x00' + b'WAVE' + b'fmt ' + b'\x10\x00\x00\x00'
        wav_header += b'\x01\x00\x01\x00\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00'
        wav_header += b'data' + b'\x10\x00\x00\x00'
        pcm_data = b'\x01\x02' * 8  # 16字节PCM数据
        wav_data = wav_header + pcm_data
        
        converted = self.tts_integration._convert_audio_format(wav_data)
        
        self.assertEqual(converted, pcm_data)
    
    def test_audio_framing(self):
        """测试音频分帧"""
        # 创建测试PCM数据
        audio_data = b'\x01\x02' * 2000  # 4000字节，约2帧
        
        frames = self.tts_integration._split_audio_to_frames(audio_data)
        
        self.assertGreater(len(frames), 0)
        self.assertEqual(frames[0].format, "pcm")
        self.assertEqual(frames[0].sample_rate, 16000)
        self.assertEqual(frames[0].channels, 1)
    
    def test_quality_determination(self):
        """测试质量判断"""
        # 高质量（快速处理，合理大小）
        quality1 = self.tts_integration._determine_quality(b'\x01' * 1000, 0.5, 10)
        
        # 低质量（慢速处理）
        quality2 = self.tts_integration._determine_quality(b'\x01' * 1000, 15.0, 10)
        
        # 低质量（数据太小）
        quality3 = self.tts_integration._determine_quality(b'\x01' * 10, 0.5, 100)
        
        self.assertEqual(quality1.value, "high")
        self.assertEqual(quality2.value, "low")
        self.assertEqual(quality3.value, "low")


class TestESP32IntentProcessor(unittest.TestCase):
    """测试ESP32意图处理器"""
    
    def setUp(self):
        """设置测试环境"""
        self.device_id = "test_intent_device_001"
        # Mock服务以避免实际调用
        with patch('app.shared.services.llm_service.get_llm_service'), \
             patch('app.shared.services.chat_history_service.get_chat_history_service'):
            self.intent_processor = ESP32IntentProcessor(self.device_id)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.intent_processor.device_id, self.device_id)
        self.assertGreater(len(self.intent_processor.exit_commands), 0)
        self.assertGreater(len(self.intent_processor.wakeup_words), 0)
    
    def test_text_preprocessing(self):
        """测试文本预处理"""
        # JSON格式文本
        json_text = '{"content": "你好世界", "speaker": "user"}'
        processed = self.intent_processor._preprocess_text(json_text)
        self.assertEqual(processed, "你好世界")
        
        # 普通文本
        normal_text = "你好，世界！"
        processed = self.intent_processor._preprocess_text(normal_text)
        self.assertEqual(processed, "你好世界")
    
    def test_exit_command_detection(self):
        """测试退出命令检测"""
        self.assertTrue(self.intent_processor._check_exit_command("退出"))
        self.assertTrue(self.intent_processor._check_exit_command("再见"))
        self.assertTrue(self.intent_processor._check_exit_command("exit"))
        self.assertFalse(self.intent_processor._check_exit_command("你好"))
    
    def test_wakeup_word_detection(self):
        """测试唤醒词检测"""
        self.assertTrue(self.intent_processor._check_wakeup_word("小助手"))
        self.assertTrue(self.intent_processor._check_wakeup_word("你好"))
        self.assertTrue(self.intent_processor._check_wakeup_word("hello"))
        self.assertFalse(self.intent_processor._check_wakeup_word("天气"))
    
    def test_intent_type_parsing(self):
        """测试意图类型解析"""
        from app.devices.esp32.services.intent_processor import IntentType
        
        self.assertEqual(self.intent_processor._parse_intent_type("chat"), IntentType.CHAT)
        self.assertEqual(self.intent_processor._parse_intent_type("function_call"), IntentType.FUNCTION_CALL)
        self.assertEqual(self.intent_processor._parse_intent_type("invalid"), IntentType.UNKNOWN)
    
    def test_system_prompt_building(self):
        """测试系统提示构建"""
        prompt = self.intent_processor._build_system_prompt()
        
        self.assertIn("智能语音助手", prompt)
        self.assertIn("function_call", prompt)
        self.assertIn("chat", prompt)
        self.assertIn("JSON格式", prompt)


class TestESP32AudioFormatConverter(unittest.TestCase):
    """测试ESP32音频格式转换器"""
    
    def setUp(self):
        """设置测试环境"""
        self.device_id = "test_converter_device_001"
        self.converter = ESP32AudioFormatConverter(self.device_id)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.converter.device_id, self.device_id)
        self.assertEqual(self.converter.default_sample_rate, 16000)
        self.assertIn("pcm", self.converter.supported_input_formats)
        self.assertIn("wav", self.converter.supported_output_formats)
    
    def test_same_format_conversion(self):
        """测试相同格式转换"""
        audio_data = b'\x01\x02' * 100
        
        result = self.converter.convert_audio_data(audio_data, "pcm", "pcm")
        
        self.assertTrue(result.success)
        self.assertEqual(result.input_size, len(audio_data))
        self.assertEqual(result.output_size, len(audio_data))
        self.assertEqual(result.quality.value, "high")
    
    def test_unsupported_format(self):
        """测试不支持的格式"""
        audio_data = b'\x01\x02' * 100
        
        result = self.converter.convert_audio_data(audio_data, "mp3", "pcm")
        
        self.assertFalse(result.success)
        self.assertIn("不支持的输入格式", result.error_message)
    
    def test_wav_to_pcm_conversion(self):
        """测试WAV到PCM转换"""
        # 创建简单的WAV数据
        wav_header = b'RIFF' + b'\x24\x00\x00\x00' + b'WAVE'
        wav_data = wav_header + b'data' + b'\x10\x00\x00\x00' + b'\x01\x02' * 8
        
        pcm_data = self.converter._wav_to_pcm(wav_data)
        
        self.assertIsNotNone(pcm_data)
        self.assertEqual(len(pcm_data), 16)
    
    def test_pcm_to_wav_conversion(self):
        """测试PCM到WAV转换"""
        pcm_data = b'\x01\x02' * 100
        
        wav_data = self.converter._pcm_to_wav(pcm_data, 16000, 1, 16)
        
        self.assertIsNotNone(wav_data)
        self.assertGreater(len(wav_data), len(pcm_data))  # WAV包含头部
        self.assertTrue(wav_data.startswith(b'RIFF'))
    
    def test_statistics_tracking(self):
        """测试统计跟踪"""
        audio_data = b'\x01\x02' * 100
        
        # 执行几次转换
        for _ in range(3):
            self.converter.convert_audio_data(audio_data, "pcm", "pcm")
        
        stats = self.converter.get_statistics()
        
        self.assertEqual(stats["conversions"]["total_count"], 3)
        self.assertGreater(stats["conversions"]["total_processing_time"], 0)


class TestESP32ServiceConnectionManager(unittest.TestCase):
    """测试ESP32服务连接管理器"""
    
    def setUp(self):
        """设置测试环境"""
        self.device_id = "test_manager_device_001"
        # Mock各种服务以避免实际连接
        with patch('app.core.asr_connection_pool.get_asr_connection_pool'), \
             patch('app.shared.services.tts_service.get_tts_service'), \
             patch('app.shared.services.llm_service.get_llm_service'):
            self.service_manager = ESP32ServiceConnectionManager(self.device_id)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.service_manager.device_id, self.device_id)
        self.assertEqual(len(self.service_manager.service_health), 3)  # ASR, TTS, LLM
        self.assertEqual(len(self.service_manager.circuit_breakers), 3)
    
    def test_circuit_breaker_initialization(self):
        """测试断路器初始化"""
        from app.devices.esp32.services.service_connection_manager import ServiceType
        
        for service_type in ServiceType:
            breaker = self.service_manager.circuit_breakers[service_type]
            self.assertEqual(breaker["state"], "closed")
            self.assertEqual(breaker["failure_count"], 0)
    
    def test_service_health_tracking(self):
        """测试服务健康跟踪"""
        from app.devices.esp32.services.service_connection_manager import ServiceType, ServiceStatus
        
        # 模拟服务失败
        self.service_manager._record_service_failure(ServiceType.ASR, "Test error")
        
        health = self.service_manager.service_health[ServiceType.ASR]
        self.assertEqual(health.metrics.failed_requests, 1)
        self.assertIsNotNone(health.error_message)
    
    def test_can_call_service(self):
        """测试服务调用检查"""
        from app.devices.esp32.services.service_connection_manager import ServiceType
        
        # 正常情况下应该可以调用
        self.assertTrue(self.service_manager._can_call_service(ServiceType.ASR))
        
        # 断路器打开后不能调用
        breaker = self.service_manager.circuit_breakers[ServiceType.ASR]
        breaker["state"] = "open"
        
        self.assertFalse(self.service_manager._can_call_service(ServiceType.ASR))


def run_async_test(test_func):
    """运行异步测试的辅助函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


if __name__ == "__main__":
    print("🧪 开始测试ESP32服务集成模块...")
    print("=" * 60)
    
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestESP32ASRServiceIntegration,
        TestESP32TTSServiceIntegration,
        TestESP32IntentProcessor,
        TestESP32AudioFormatConverter,
        TestESP32ServiceConnectionManager
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ 所有测试通过！ESP32服务集成模块工作正常")
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
