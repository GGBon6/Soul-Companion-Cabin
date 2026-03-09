"""
ESP32音频处理模块演示
ESP32 Audio Processing Module Demo
演示音频状态管理、缓冲管理、VAD检测和协议适配的完整功能
"""

import asyncio
import time
import numpy as np
from unittest.mock import Mock
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.devices.esp32.audio import (
    get_esp32_audio_state_manager, ESP32AudioState, ESP32VADState,
    get_esp32_audio_buffer_manager, AudioFrame,
    get_esp32_vad_detector, VADConfig,
    get_esp32_audio_protocol_adapter, ESP32AudioProtocol
)


class ESP32AudioProcessingDemo:
    """ESP32音频处理演示类"""
    
    def __init__(self):
        self.device_id = "demo_audio_device_001"
        
        # 初始化音频处理组件
        self.state_manager = get_esp32_audio_state_manager(self.device_id)
        self.buffer_manager = get_esp32_audio_buffer_manager(self.device_id, 20, 10, 5)
        
        # 创建VAD配置
        vad_config = VADConfig(
            energy_threshold=200.0,
            min_speech_duration=0.2,
            min_silence_duration=0.5,
            window_size=5,
            adaptive_threshold=True
        )
        self.vad_detector = get_esp32_vad_detector(self.device_id, vad_config)
        self.protocol_adapter = get_esp32_audio_protocol_adapter(self.device_id)
        
        # 添加状态变化回调
        self.state_manager.add_state_change_callback(self._on_audio_state_change)
        self.state_manager.add_vad_change_callback(self._on_vad_state_change)
        
        print(f"🎵 ESP32音频处理演示初始化完成: {self.device_id}")
    
    async def demo_audio_state_management(self):
        """演示音频状态管理"""
        print("\n🔄 演示音频状态管理")
        print("=" * 50)
        
        # 设置音频参数
        from app.devices.esp32.message_types import ESP32AudioFormat
        self.state_manager.set_audio_params(16000, 60, ESP32AudioFormat.OPUS)
        
        # 启动状态监控
        await self.state_manager.start_monitoring()
        
        # 演示状态转换
        states = [
            (ESP32AudioState.LISTENING, "开始监听"),
            (ESP32AudioState.VAD_DETECTED, "检测到语音"),
            (ESP32AudioState.RECORDING, "开始录音"),
            (ESP32AudioState.PROCESSING, "处理音频"),
            (ESP32AudioState.SPEAKING, "播放回复"),
            (ESP32AudioState.IDLE, "回到空闲")
        ]
        
        for state, reason in states:
            await self.state_manager.set_audio_state(state, reason)
            await asyncio.sleep(0.5)  # 等待状态稳定
            
            state_info = self.state_manager.get_state_info()
            print(f"  状态: {state.value} | 持续时间: {state_info.state_duration:.2f}s")
        
        # 显示状态摘要
        summary = self.state_manager.get_state_summary()
        print(f"\n📊 状态摘要:")
        print(f"  设备ID: {summary['device_id']}")
        print(f"  当前状态: {summary['audio_state']}")
        print(f"  VAD状态: {summary['vad_state']}")
        print(f"  状态持续时间: {summary['state_duration']}s")
        
        # 停止状态监控
        await self.state_manager.stop_monitoring()
    
    async def demo_vad_detection(self):
        """演示VAD检测"""
        print("\n🎤 演示VAD检测")
        print("=" * 50)
        
        # 生成测试音频数据
        test_cases = [
            ("静音PCM", self._generate_silence_pcm(960)),
            ("语音PCM", self._generate_speech_pcm(960)),
            ("小Opus包", b'\x01\x02'),  # 静音
            ("大Opus包", b'\x01' * 50),  # 语音
        ]
        
        for name, audio_data in test_cases:
            audio_format = "pcm" if "PCM" in name else "opus"
            
            # 进行VAD检测
            result = self.vad_detector.detect(audio_data, audio_format, 16000)
            
            print(f"  {name}:")
            print(f"    是否语音: {result.is_speech}")
            print(f"    置信度: {result.confidence:.2f}")
            print(f"    能量级别: {result.energy_level:.1f}")
            print(f"    零交叉率: {result.zcr_value:.4f}")
        
        # 显示VAD统计
        stats = self.vad_detector.get_stats()
        print(f"\n📈 VAD统计:")
        print(f"  总帧数: {stats['frame_count']}")
        print(f"  语音帧数: {stats['speech_frame_count']}")
        print(f"  静音帧数: {stats['silence_frame_count']}")
        print(f"  语音比例: {stats['speech_ratio']:.2%}")
        print(f"  背景能量: {stats['background_energy']:.1f}")
        print(f"  当前阈值: {stats['current_threshold']:.1f}")
    
    async def demo_buffer_management(self):
        """演示缓冲管理"""
        print("\n💾 演示缓冲管理")
        print("=" * 50)
        
        # 设置音频参数
        self.buffer_manager.set_audio_params(16000, 60, 1)
        
        # 添加输入音频帧
        print("添加输入音频帧...")
        for i in range(8):
            audio_data = bytes([i] * 100)
            success = self.buffer_manager.put_input_frame(audio_data, "opus", 
                                                        metadata={"frame_id": i})
            print(f"  帧 {i}: {'✅' if success else '❌'}")
        
        # 批量获取输入帧
        frames = self.buffer_manager.get_input_frames_batch(5)
        print(f"\n批量获取输入帧: {len(frames)}帧")
        for frame in frames:
            print(f"  序列号: {frame.sequence_number}, 大小: {frame.frame_size}字节")
        
        # 添加输出音频帧
        print("\n添加输出音频帧...")
        for i in range(5):
            audio_data = bytes([i + 10] * 80)
            success = self.buffer_manager.put_output_frame(audio_data, "pcm")
            print(f"  输出帧 {i}: {'✅' if success else '❌'}")
        
        # 获取缓冲区统计
        stats = self.buffer_manager.get_buffer_stats()
        print(f"\n📊 缓冲区统计:")
        print(f"  设备ID: {stats['device_id']}")
        print(f"  运行时间: {stats['uptime_seconds']}s")
        print(f"  输入缓冲区: {stats['input_buffer']['current_size']}/{stats['input_buffer']['max_size']}")
        print(f"  输出缓冲区: {stats['output_buffer']['current_size']}/{stats['output_buffer']['max_size']}")
        print(f"  处理帧数: {stats['processing_stats']['frames_processed']}")
        print(f"  处理字节数: {stats['processing_stats']['bytes_processed']}")
        print(f"  缓冲区溢出: {stats['processing_stats']['buffer_overflows']}")
        print(f"  缓冲区欠载: {stats['processing_stats']['buffer_underruns']}")
    
    async def demo_protocol_adaptation(self):
        """演示协议适配"""
        print("\n🔌 演示协议适配")
        print("=" * 50)
        
        # 创建测试音频帧
        test_frame = AudioFrame(
            data=b'\x01\x02\x03\x04\x05' * 20,  # 100字节测试数据
            timestamp=time.time(),
            sequence_number=1,
            frame_size=100,
            sample_rate=16000,
            channels=1,
            format="opus"
        )
        
        # 测试不同协议的编码
        protocols = [
            ESP32AudioProtocol.RAW_AUDIO,
            ESP32AudioProtocol.WEBSOCKET_BINARY,
            ESP32AudioProtocol.BINARY_PROTOCOL_V2,
            ESP32AudioProtocol.BINARY_PROTOCOL_V3,
            ESP32AudioProtocol.MQTT_GATEWAY
        ]
        
        for protocol in protocols:
            # 切换协议
            self.protocol_adapter.set_protocol(protocol)
            
            # 编码音频帧
            encoded = self.protocol_adapter.encode_audio_frame(test_frame, protocol, 0)
            
            if encoded:
                print(f"  {protocol.value}:")
                print(f"    原始大小: {len(test_frame.data)}字节")
                print(f"    编码大小: {len(encoded)}字节")
                print(f"    头部开销: {len(encoded) - len(test_frame.data)}字节")
                
                # 尝试检测协议
                detected = self.protocol_adapter._detect_protocol(encoded)
                print(f"    检测协议: {detected.value}")
                print(f"    检测正确: {'✅' if detected == protocol else '❌'}")
            else:
                print(f"  {protocol.value}: ❌ 编码失败")
            
            print()
        
        # 显示协议统计
        stats = self.protocol_adapter.get_protocol_stats()
        print(f"📈 协议统计:")
        print(f"  当前协议: {stats['current_protocol']}")
        print(f"  编码包数: {stats['packets_encoded']}")
        print(f"  编码字节数: {stats['bytes_encoded']}")
        print(f"  协议切换次数: {stats['protocol_switches']}")
        print(f"  编码错误率: {stats['error_rate']['encoding']:.2%}")
    
    async def demo_integrated_audio_flow(self):
        """演示集成音频流程"""
        print("\n🔄 演示集成音频流程")
        print("=" * 50)
        
        # 模拟完整的音频处理流程
        print("1. 开始音频接收...")
        await self.state_manager.set_audio_state(ESP32AudioState.LISTENING, "开始监听")
        
        # 模拟接收多个音频帧
        print("2. 接收音频数据...")
        speech_detected = False
        
        for i in range(10):
            # 前5帧是静音，后5帧是语音
            if i < 5:
                audio_data = self._generate_silence_pcm(960)
                frame_type = "静音"
            else:
                audio_data = self._generate_speech_pcm(960)
                frame_type = "语音"
            
            # VAD检测
            vad_result = self.vad_detector.detect(audio_data, "pcm", 16000)
            
            # 添加到缓冲区
            self.buffer_manager.put_input_frame(audio_data, "pcm", 
                                              metadata={"frame_id": i, "type": frame_type})
            
            # 更新状态
            if vad_result.is_speech and not speech_detected:
                await self.state_manager.set_vad_state(ESP32VADState.SPEECH_START)
                await self.state_manager.set_audio_state(ESP32AudioState.RECORDING, "检测到语音")
                speech_detected = True
                print(f"   帧 {i}: {frame_type} -> 🎤 开始录音")
            elif not vad_result.is_speech and speech_detected:
                await self.state_manager.set_vad_state(ESP32VADState.SPEECH_END)
                await self.state_manager.set_audio_state(ESP32AudioState.PROCESSING, "语音结束")
                print(f"   帧 {i}: {frame_type} -> 🔄 开始处理")
                break
            else:
                print(f"   帧 {i}: {frame_type} -> {'🎤' if speech_detected else '🔇'}")
            
            await asyncio.sleep(0.06)  # 模拟60ms帧间隔
        
        print("3. 处理音频数据...")
        # 获取录音数据
        recorded_frames = self.buffer_manager.get_input_frames_batch(10)
        total_audio_data = b''.join(frame.data for frame in recorded_frames)
        print(f"   录音数据: {len(recorded_frames)}帧, {len(total_audio_data)}字节")
        
        # 模拟ASR处理
        await asyncio.sleep(0.2)
        print("   ASR识别结果: '你好，ESP32'")
        
        print("4. 生成TTS回复...")
        await self.state_manager.set_audio_state(ESP32AudioState.SPEAKING, "开始TTS播放")
        
        # 模拟TTS音频数据
        tts_audio = self._generate_speech_pcm(4800)  # 300ms的音频
        
        # 分帧并添加到输出缓冲区
        frame_size = 960  # 60ms帧
        for i in range(0, len(tts_audio), frame_size):
            frame_data = tts_audio[i:i+frame_size]
            if len(frame_data) > 0:
                self.buffer_manager.put_output_frame(frame_data, "pcm")
        
        # 编码并"发送"音频帧
        output_frames = self.buffer_manager.get_output_frames_batch(10)
        total_sent = 0
        
        for frame in output_frames:
            # 编码为协议数据包
            packet = self.protocol_adapter.encode_audio_frame(frame, 
                                                            ESP32AudioProtocol.BINARY_PROTOCOL_V2, 0)
            if packet:
                total_sent += len(packet)
        
        print(f"   TTS音频: {len(output_frames)}帧, {total_sent}字节已发送")
        
        print("5. 完成音频流程...")
        await self.state_manager.set_audio_state(ESP32AudioState.IDLE, "音频流程完成")
        
        # 显示最终统计
        state_summary = self.state_manager.get_state_summary()
        buffer_stats = self.buffer_manager.get_buffer_stats()
        vad_stats = self.vad_detector.get_stats()
        protocol_stats = self.protocol_adapter.get_protocol_stats()
        
        print(f"\n📊 流程统计:")
        print(f"  音频状态: {state_summary['audio_state']}")
        print(f"  处理帧数: {buffer_stats['processing_stats']['frames_processed']}")
        print(f"  VAD检测帧数: {vad_stats['frame_count']}")
        print(f"  协议编码包数: {protocol_stats['packets_encoded']}")
    
    def _generate_silence_pcm(self, samples: int) -> bytes:
        """生成静音PCM数据"""
        # 生成低振幅的随机噪音
        audio_array = np.random.randint(-50, 50, samples, dtype=np.int16)
        return audio_array.tobytes()
    
    def _generate_speech_pcm(self, samples: int) -> bytes:
        """生成语音PCM数据"""
        # 生成正弦波模拟语音
        t = np.linspace(0, samples/16000, samples)
        frequency = 440  # A4音符
        amplitude = 5000
        audio_array = (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.int16)
        return audio_array.tobytes()
    
    async def _on_audio_state_change(self, old_state: ESP32AudioState, new_state: ESP32AudioState):
        """音频状态变化回调"""
        print(f"    🔄 音频状态: {old_state.value} -> {new_state.value}")
    
    async def _on_vad_state_change(self, old_vad_state: ESP32VADState, new_vad_state: ESP32VADState):
        """VAD状态变化回调"""
        print(f"    🎤 VAD状态: {old_vad_state.value} -> {new_vad_state.value}")
    
    async def run_full_demo(self):
        """运行完整演示"""
        print("🎵 ESP32音频处理模块完整演示")
        print("=" * 60)
        
        try:
            # 1. 音频状态管理演示
            await self.demo_audio_state_management()
            
            # 2. VAD检测演示
            await self.demo_vad_detection()
            
            # 3. 缓冲管理演示
            await self.demo_buffer_management()
            
            # 4. 协议适配演示
            await self.demo_protocol_adaptation()
            
            # 5. 集成音频流程演示
            await self.demo_integrated_audio_flow()
            
            print("\n🎉 演示完成！")
            print("=" * 60)
            print("✅ 音频状态管理正常工作")
            print("✅ VAD检测正常工作")
            print("✅ 音频缓冲管理正常工作")
            print("✅ 协议适配正常工作")
            print("✅ 集成音频流程正常工作")
            print("=" * 60)
            
        except Exception as e:
            print(f"\n❌ 演示过程中发生错误: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数"""
    demo = ESP32AudioProcessingDemo()
    await demo.run_full_demo()


if __name__ == "__main__":
    # 运行演示
    asyncio.run(main())
