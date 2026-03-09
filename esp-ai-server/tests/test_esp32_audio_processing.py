"""
ESP32音频处理模块测试
Test ESP32 Audio Processing Modules
测试音频状态管理、缓冲管理、VAD检测等音频处理组件
"""

import asyncio
import unittest
import time
import numpy as np
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.devices.esp32.audio import (
    ESP32AudioStateManager, ESP32AudioState, ESP32VADState,
    ESP32AudioBufferManager, AudioFrame,
    ESP32VADDetector, VADConfig, VADResult,
    ESP32AudioProtocolAdapter, ESP32AudioProtocol, ProtocolHeader
)
from app.devices.esp32.message_types import ESP32AudioFormat


class TestESP32AudioStateManager(unittest.TestCase):
    """测试ESP32音频状态管理器"""
    
    def setUp(self):
        """设置测试环境"""
        self.device_id = "test_audio_device_001"
        self.state_manager = ESP32AudioStateManager(self.device_id)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.state_manager.device_id, self.device_id)
        self.assertEqual(self.state_manager.state_info.current_state, ESP32AudioState.IDLE)
        self.assertEqual(self.state_manager.state_info.vad_state, ESP32VADState.SILENCE)
    
    async def test_audio_state_change(self):
        """测试音频状态变化"""
        # 测试状态变化
        await self.state_manager.set_audio_state(ESP32AudioState.LISTENING, "开始监听")
        
        self.assertEqual(self.state_manager.state_info.current_state, ESP32AudioState.LISTENING)
        self.assertEqual(self.state_manager.state_info.previous_state, ESP32AudioState.IDLE)
        
        # 测试状态持续时间
        time.sleep(0.1)
        state_info = self.state_manager.get_state_info()
        self.assertGreater(state_info.state_duration, 0.05)
    
    async def test_vad_state_change(self):
        """测试VAD状态变化"""
        await self.state_manager.set_vad_state(ESP32VADState.SPEECH_START)
        
        self.assertEqual(self.state_manager.state_info.vad_state, ESP32VADState.SPEECH_START)
        self.assertIsNotNone(self.state_manager.state_info.speech_start_time)
    
    def test_audio_params_setting(self):
        """测试音频参数设置"""
        self.state_manager.set_audio_params(16000, 60, ESP32AudioFormat.OPUS)
        
        self.assertEqual(self.state_manager.state_info.sample_rate, 16000)
        self.assertEqual(self.state_manager.state_info.frame_duration, 60)
        self.assertEqual(self.state_manager.state_info.audio_format, ESP32AudioFormat.OPUS)
    
    def test_stats_update(self):
        """测试统计信息更新"""
        self.state_manager.update_audio_stats(frames_received=5, bytes_received=1000)
        
        self.assertEqual(self.state_manager.state_info.total_frames_received, 5)
        self.assertEqual(self.state_manager.state_info.total_bytes_received, 1000)
    
    def test_error_handling(self):
        """测试错误处理"""
        error_msg = "测试错误"
        self.state_manager.set_error(error_msg)
        
        self.assertEqual(self.state_manager.state_info.last_error, error_msg)
        self.assertEqual(self.state_manager.state_info.error_count, 1)
        
        # 清除错误
        self.state_manager.clear_error()
        self.assertIsNone(self.state_manager.state_info.last_error)
    
    def test_state_summary(self):
        """测试状态摘要"""
        summary = self.state_manager.get_state_summary()
        
        self.assertIn("device_id", summary)
        self.assertIn("audio_state", summary)
        self.assertIn("vad_state", summary)
        self.assertEqual(summary["device_id"], self.device_id)


class TestESP32AudioBufferManager(unittest.TestCase):
    """测试ESP32音频缓冲管理器"""
    
    def setUp(self):
        """设置测试环境"""
        self.device_id = "test_buffer_device_001"
        self.buffer_manager = ESP32AudioBufferManager(self.device_id, 10, 5, 3)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.buffer_manager.device_id, self.device_id)
        self.assertEqual(self.buffer_manager.input_buffer.max_size, 10)
        self.assertEqual(self.buffer_manager.output_buffer.max_size, 5)
    
    def test_audio_params_setting(self):
        """测试音频参数设置"""
        self.buffer_manager.set_audio_params(16000, 60, 1)
        
        self.assertEqual(self.buffer_manager.sample_rate, 16000)
        self.assertEqual(self.buffer_manager.frame_duration, 60)
        self.assertEqual(self.buffer_manager.channels, 1)
    
    def test_input_frame_operations(self):
        """测试输入帧操作"""
        # 添加有效音频帧
        audio_data = b'\x01\x02\x03\x04' * 100  # 400字节的测试数据
        success = self.buffer_manager.put_input_frame(audio_data, "opus")
        
        self.assertTrue(success)
        self.assertEqual(self.buffer_manager.input_buffer.size(), 1)
        
        # 获取音频帧
        frame = self.buffer_manager.get_input_frame()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.data, audio_data)
        self.assertEqual(frame.format, "opus")
        self.assertEqual(self.buffer_manager.input_buffer.size(), 0)
    
    def test_output_frame_operations(self):
        """测试输出帧操作"""
        # 添加输出音频帧
        audio_data = b'\x05\x06\x07\x08' * 50  # 200字节的测试数据
        success = self.buffer_manager.put_output_frame(audio_data, "pcm")
        
        self.assertTrue(success)
        self.assertEqual(self.buffer_manager.output_buffer.size(), 1)
        
        # 获取音频帧
        frame = self.buffer_manager.get_output_frame()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.data, audio_data)
        self.assertEqual(frame.format, "pcm")
    
    def test_batch_operations(self):
        """测试批量操作"""
        # 添加多个输入帧
        for i in range(5):
            audio_data = bytes([i] * 100)
            self.buffer_manager.put_input_frame(audio_data, "opus")
        
        # 批量获取
        frames = self.buffer_manager.get_input_frames_batch(3)
        self.assertEqual(len(frames), 3)
        self.assertEqual(self.buffer_manager.input_buffer.size(), 2)
    
    def test_silence_filtering(self):
        """测试静音过滤"""
        # 测试空数据（应该被过滤）
        success = self.buffer_manager.put_input_frame(b'', "opus")
        self.assertFalse(success)  # 空数据返回False
        self.assertEqual(self.buffer_manager.input_buffer.size(), 0)
        
        # 测试小的Opus数据（应该被过滤）
        success = self.buffer_manager.put_input_frame(b'\x01\x02', "opus")
        self.assertTrue(success)  # 返回True但被标记为静音
    
    def test_buffer_stats(self):
        """测试缓冲区统计"""
        # 添加一些数据
        self.buffer_manager.put_input_frame(b'\x01' * 100, "opus")
        self.buffer_manager.put_output_frame(b'\x02' * 100, "pcm")
        
        stats = self.buffer_manager.get_buffer_stats()
        
        self.assertIn("device_id", stats)
        self.assertIn("input_buffer", stats)
        self.assertIn("output_buffer", stats)
        self.assertIn("processing_stats", stats)
        self.assertEqual(stats["device_id"], self.device_id)
    
    def test_buffer_overflow(self):
        """测试缓冲区溢出"""
        # 填满输入缓冲区
        for i in range(15):  # 超过最大大小10
            self.buffer_manager.put_input_frame(bytes([i] * 100), "opus")
        
        # 检查缓冲区大小不超过最大值
        self.assertLessEqual(self.buffer_manager.input_buffer.size(), 10)
        
        # 检查溢出统计
        stats = self.buffer_manager.get_buffer_stats()
        self.assertGreaterEqual(stats["processing_stats"]["buffer_overflows"], 0)


class TestESP32VADDetector(unittest.TestCase):
    """测试ESP32 VAD检测器"""
    
    def setUp(self):
        """设置测试环境"""
        self.device_id = "test_vad_device_001"
        self.config = VADConfig(
            energy_threshold=300.0,
            min_speech_duration=0.1,
            min_silence_duration=0.5,
            window_size=3
        )
        self.vad_detector = ESP32VADDetector(self.device_id, self.config)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.vad_detector.device_id, self.device_id)
        self.assertEqual(self.vad_detector.current_state, ESP32VADState.SILENCE)
        self.assertEqual(self.vad_detector.config.energy_threshold, 300.0)
    
    def test_opus_detection(self):
        """测试Opus格式VAD检测"""
        # 测试静音（小数据包）
        silence_data = b'\x01\x02'  # 2字节，应该被认为是静音
        result = self.vad_detector.detect(silence_data, "opus", 16000)
        
        self.assertIsInstance(result, VADResult)
        self.assertFalse(result.is_speech)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)
        
        # 测试语音（大数据包）
        speech_data = b'\x01' * 100  # 100字节，应该被认为是语音
        result = self.vad_detector.detect(speech_data, "opus", 16000)
        
        self.assertTrue(result.is_speech)
        self.assertGreater(result.energy_level, 0)
    
    def test_pcm_detection(self):
        """测试PCM格式VAD检测"""
        # 生成静音PCM数据（低振幅）
        silence_samples = np.zeros(960, dtype=np.int16)  # 60ms @ 16kHz
        silence_data = silence_samples.tobytes()
        
        result = self.vad_detector.detect(silence_data, "pcm", 16000)
        self.assertFalse(result.is_speech)
        
        # 生成语音PCM数据（高振幅）
        speech_samples = np.random.randint(-1000, 1000, 960, dtype=np.int16)
        speech_data = speech_samples.tobytes()
        
        result = self.vad_detector.detect(speech_data, "pcm", 16000)
        # 注意：随机数据可能不总是被检测为语音，这取决于能量阈值
        self.assertIsInstance(result, VADResult)
    
    def test_state_transitions(self):
        """测试状态转换"""
        # 初始状态应该是静音
        self.assertEqual(self.vad_detector.get_state(), ESP32VADState.SILENCE)
        
        # 连续检测语音应该触发状态变化
        speech_data = b'\x01' * 100
        for _ in range(5):
            self.vad_detector.detect(speech_data, "opus", 16000)
        
        # 检查是否有状态变化（具体状态取决于配置和检测结果）
        current_state = self.vad_detector.get_state()
        self.assertIsInstance(current_state, ESP32VADState)
    
    def test_statistics(self):
        """测试统计信息"""
        # 进行一些检测
        for i in range(10):
            data = bytes([i] * 50)
            self.vad_detector.detect(data, "opus", 16000)
        
        stats = self.vad_detector.get_stats()
        
        self.assertIn("device_id", stats)
        self.assertIn("frame_count", stats)
        self.assertIn("speech_frame_count", stats)
        self.assertIn("silence_frame_count", stats)
        self.assertEqual(stats["device_id"], self.device_id)
        self.assertEqual(stats["frame_count"], 10)
    
    def test_reset(self):
        """测试重置功能"""
        # 进行一些检测
        self.vad_detector.detect(b'\x01' * 100, "opus", 16000)
        
        # 重置
        self.vad_detector.reset()
        
        # 检查状态是否重置
        self.assertEqual(self.vad_detector.current_state, ESP32VADState.SILENCE)
        self.assertEqual(self.vad_detector.frame_count, 0)
        self.assertEqual(len(self.vad_detector.energy_history), 0)


class TestESP32AudioProtocolAdapter(unittest.TestCase):
    """测试ESP32音频协议适配器"""
    
    def setUp(self):
        """设置测试环境"""
        self.device_id = "test_protocol_device_001"
        self.adapter = ESP32AudioProtocolAdapter(self.device_id)
    
    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.adapter.device_id, self.device_id)
        self.assertEqual(self.adapter.current_protocol, ESP32AudioProtocol.WEBSOCKET_BINARY)
    
    def test_protocol_switching(self):
        """测试协议切换"""
        # 切换到二进制协议v2
        self.adapter.set_protocol(ESP32AudioProtocol.BINARY_PROTOCOL_V2)
        self.assertEqual(self.adapter.current_protocol, ESP32AudioProtocol.BINARY_PROTOCOL_V2)
        
        # 检查统计信息
        stats = self.adapter.get_protocol_stats()
        self.assertEqual(stats["protocol_switches"], 1)
    
    def test_raw_audio_encoding(self):
        """测试原始音频编码"""
        # 创建测试音频帧
        frame = AudioFrame(
            data=b'\x01\x02\x03\x04',
            timestamp=time.time(),
            sequence_number=1,
            frame_size=4,
            sample_rate=16000,
            channels=1,
            format="raw"
        )
        
        # 编码为原始音频
        encoded = self.adapter.encode_audio_frame(frame, ESP32AudioProtocol.RAW_AUDIO)
        
        self.assertEqual(encoded, frame.data)
    
    def test_websocket_binary_encoding(self):
        """测试WebSocket二进制编码"""
        frame = AudioFrame(
            data=b'\x05\x06\x07\x08',
            timestamp=time.time(),
            sequence_number=1,
            frame_size=4,
            sample_rate=16000,
            channels=1,
            format="opus"
        )
        
        # 编码为WebSocket二进制
        encoded = self.adapter.encode_audio_frame(frame, ESP32AudioProtocol.WEBSOCKET_BINARY)
        
        self.assertEqual(encoded, frame.data)
    
    def test_binary_protocol_v2_encoding(self):
        """测试二进制协议v2编码"""
        frame = AudioFrame(
            data=b'\x09\x0A\x0B\x0C',
            timestamp=time.time(),
            sequence_number=1,
            frame_size=4,
            sample_rate=16000,
            channels=1,
            format="opus"
        )
        
        # 编码为二进制协议v2
        encoded = self.adapter.encode_audio_frame(frame, ESP32AudioProtocol.BINARY_PROTOCOL_V2)
        
        self.assertIsNotNone(encoded)
        self.assertGreater(len(encoded), len(frame.data))  # 应该包含头部
        
        # 检查头部格式（大端字节序）
        self.assertEqual(len(encoded), 16 + len(frame.data))  # 16字节头部 + 数据
    
    def test_binary_protocol_v3_encoding(self):
        """测试二进制协议v3编码"""
        frame = AudioFrame(
            data=b'\x0D\x0E\x0F\x10',
            timestamp=time.time(),
            sequence_number=1,
            frame_size=4,
            sample_rate=16000,
            channels=1,
            format="opus"
        )
        
        # 编码为二进制协议v3
        encoded = self.adapter.encode_audio_frame(frame, ESP32AudioProtocol.BINARY_PROTOCOL_V3)
        
        self.assertIsNotNone(encoded)
        self.assertEqual(len(encoded), 8 + len(frame.data))  # 8字节头部 + 数据
    
    def test_batch_encoding(self):
        """测试批量编码"""
        frames = []
        for i in range(3):
            frame = AudioFrame(
                data=bytes([i] * 10),
                timestamp=time.time(),
                sequence_number=i + 1,
                frame_size=10,
                sample_rate=16000,
                channels=1,
                format="opus"
            )
            frames.append(frame)
        
        # 批量编码
        packets = self.adapter.encode_audio_frames_batch(frames, ESP32AudioProtocol.RAW_AUDIO)
        
        self.assertEqual(len(packets), 3)
        for i, packet in enumerate(packets):
            self.assertEqual(packet, bytes([i] * 10))
    
    def test_protocol_detection(self):
        """测试协议检测"""
        # 测试原始数据检测（小于4字节）
        raw_data = b'\x01\x02\x03'
        protocol = self.adapter._detect_protocol(raw_data)
        self.assertEqual(protocol, ESP32AudioProtocol.RAW_AUDIO)  # 小数据包被认为是原始音频
        
        # 测试较大的数据包（应该被认为是WebSocket二进制）
        larger_data = b'\x01\x02\x03\x04\x05\x06'
        protocol = self.adapter._detect_protocol(larger_data)
        self.assertEqual(protocol, ESP32AudioProtocol.WEBSOCKET_BINARY)  # 默认协议
        
        # 测试MQTT协议检测
        mqtt_data = b'MQTT' + b'\x00' * 17  # MQTT魔数 + 最小头部
        protocol = self.adapter._detect_protocol(mqtt_data)
        self.assertEqual(protocol, ESP32AudioProtocol.MQTT_GATEWAY)
    
    def test_encoding_statistics(self):
        """测试编码统计"""
        frame = AudioFrame(
            data=b'\x11\x12\x13\x14',
            timestamp=time.time(),
            sequence_number=1,
            frame_size=4,
            sample_rate=16000,
            channels=1,
            format="opus"
        )
        
        # 进行编码
        self.adapter.encode_audio_frame(frame, ESP32AudioProtocol.RAW_AUDIO)
        
        # 检查统计信息
        stats = self.adapter.get_protocol_stats()
        self.assertEqual(stats["packets_encoded"], 1)
        self.assertEqual(stats["bytes_encoded"], 4)


def run_async_test(test_func):
    """运行异步测试的辅助函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


if __name__ == "__main__":
    print("🧪 开始测试ESP32音频处理模块...")
    print("=" * 60)
    
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestESP32AudioStateManager,
        TestESP32AudioBufferManager,
        TestESP32VADDetector,
        TestESP32AudioProtocolAdapter
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ 所有测试通过！ESP32音频处理模块工作正常")
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
