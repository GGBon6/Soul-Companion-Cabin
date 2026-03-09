"""
ESP32消息路由系统
ESP32 Message Router System
参考core/handle/的设计模式，为ESP32设备提供智能消息路由和处理
"""

import json
import asyncio
import time
from datetime import datetime
from typing import Dict, Optional, Any, Callable, List, Type
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod
import logging

from app.devices.esp32.services import (
    get_esp32_asr_integration,
    get_esp32_tts_integration,
    get_esp32_intent_processor,
    get_esp32_speech_coordinator,
    get_streaming_asr_integration,
    StreamingASRConfig,
    StreamingASRMode
)
from app.devices.esp32.services.speech_interaction_coordinator import InteractionResult

# 流式交互常量
STREAMING_WINDOW = 25      # 流式窗口大小(帧)
SILENCE_THRESHOLD = 15     # 静音阈值(帧)
MAX_BUFFER_FRAMES = 200    # 最大缓冲帧数


class MessageType(Enum):
    """消息类型"""
    HELLO = "hello"
    AUDIO = "audio"
    TEXT = "text"
    CONTROL = "control"
    INTENT = "intent"
    TTS = "tts"
    STATUS = "status"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    # ESP32特有的消息类型
    LISTEN = "listen"      # 监听控制消息
    ABORT = "abort"        # 中止消息
    MCP = "mcp"           # MCP消息
    UNKNOWN = "unknown"


class MessagePriority(Enum):
    """消息优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    EMERGENCY = 5


@dataclass
class MessageContext:
    """消息上下文"""
    message_id: str
    message_type: MessageType
    priority: MessagePriority
    timestamp: float
    device_id: str
    session_id: str
    raw_data: Any
    parsed_data: Dict[str, Any]
    metadata: Dict[str, Any]


class MessageHandler(ABC):
    """消息处理器基类"""
    
    def __init__(self, message_type: MessageType):
        self.message_type = message_type
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @abstractmethod
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理消息"""
        pass
    
    @abstractmethod
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证消息格式"""
        pass
    
    def get_priority(self, data: Dict[str, Any]) -> MessagePriority:
        """获取消息优先级"""
        return MessagePriority.NORMAL


class HelloMessageHandler(MessageHandler):
    """Hello消息处理器"""
    
    def __init__(self):
        super().__init__(MessageType.HELLO)
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证Hello消息格式"""
        # 验证消息类型
        if data.get("type") != "hello":
            return False
        
        # 验证协议版本 (兼容 version 和 protocol_version 字段)
        version = data.get("version") or data.get("protocol_version")
        if version is None:
            return False
        
        # device_id是可选的，如果没有会自动生成
        return True
    
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理Hello消息"""
        try:
            # 详细的Hello消息日志
            self.logger.info("收到Hello消息:")
            self.logger.info(f"   消息类型: {type(context.raw_data)}")
            self.logger.info(f"   消息长度: {len(context.raw_data)}")
            self.logger.info(f"   消息内容: {context.raw_data[:200]}...")
            
            # 解析Hello消息数据
            data = json.loads(context.raw_data)
            
            # 提取设备信息
            device_id = data.get("device_id")
            if not device_id:
                # 为ESP32设备生成device_id（如果没有提供）
                import uuid
                device_id = f"esp32_{uuid.uuid4().hex[:8]}"
            
            # 兼容version和protocol_version字段
            protocol_version = data.get("protocol_version") or data.get("version", "1.0")
            features = data.get("features", {})
            audio_params = data.get("audio_params", {})
            
            # 详细的解析结果日志
            self.logger.info("Hello消息解析成功:")
            self.logger.info(f"   设备ID: {device_id}")
            self.logger.info(f"   客户端ID: {data.get('client_id', 'N/A')}")
            self.logger.info(f"   协议版本: {protocol_version}")
            self.logger.info(f"   音频参数: {audio_params}")
            self.logger.info(f"   设备能力: {list(features.keys())}")
            
            # 更新设备信息
            old_device_id = connection_handler.device_info.device_id
            connection_handler.device_info.device_id = device_id
            connection_handler.device_info.protocol_version = protocol_version
            connection_handler.device_info.features = features
            connection_handler.device_info.audio_params = audio_params
            
            # 如果设备ID发生变化（从临时ID更新为真实ID），需要更新管理器中的映射
            if old_device_id != device_id and hasattr(connection_handler, 'manager'):
                # 更新设备连接映射
                if old_device_id in connection_handler.manager.device_connections:
                    connection_id = connection_handler.manager.device_connections.pop(old_device_id)
                    connection_handler.manager.device_connections[device_id] = connection_id
                    self.logger.info(f"设备ID已更新: {old_device_id} -> {device_id}")
                # 清空旧设备ID的缓冲区（防止残留数据）
                if hasattr(connection_handler, "message_router") and hasattr(
                    connection_handler.message_router, "clear_device_buffer"
                ):
                    connection_handler.message_router.clear_device_buffer(old_device_id)
            
            # 初始化设备会话
            await connection_handler.initialize_session()
            
            # 清空当前设备ID的流式ASR缓冲区（防止残留数据）
            if hasattr(connection_handler, "message_router") and hasattr(
                connection_handler.message_router, "clear_device_buffer"
            ):
                connection_handler.message_router.clear_device_buffer(device_id)
            
            self.logger.info(f"🔗 ESP32设备连接: {device_id} (Client: {data.get('client_id', 'N/A')})")
            self.logger.info(f"✅ 创建ESP32设备会话: {device_id} -> {connection_handler.session_id}")
            self.logger.info(f"📋 设备参数: 采样率={audio_params.get('sample_rate', 16000)}Hz, 帧长={audio_params.get('frame_duration', 40)}ms, 协议版本={protocol_version}")
            
            # 构建Hello响应 - 完全兼容ESP32硬件端期望格式
            response = {
                "type": "hello",
                "version": protocol_version,  # 回显ESP32发送的版本
                "transport": "websocket",     # ESP32必需的transport字段
                "status": "success",
                "session_id": connection_handler.session_id,
                "features": {
                    "mcp": True,
                    "audio_processing": True,
                    "conversation_history": True,
                    "intent_recognition": True,
                    "emotion_analysis": True
                },
                "server_info": {
                    "name": "ESP32-AI-Server",
                    "version": "2.0.0",
                    "supported_protocols": ["1.0", "2.0"],
                    "capabilities": [
                        "asr", "tts", "intent", "psychology_intent", 
                        "audio_processing", "speech_interaction"
                    ]
                },
                "audio_params": {
                    "sample_rate": audio_params.get("sample_rate", 16000),
                    "format": audio_params.get("format", "opus"),
                    "channels": audio_params.get("channels", 1),
                    "frame_duration": audio_params.get("frame_duration", 40)  # 匹配ESP32的40ms
                }
            }
            
            # 使用设备日志系统记录Hello响应
            from app.core.device_logger import log_esp32_protocol
            log_esp32_protocol(device_id, "hello_response", len(str(response)), {
                "session_id": connection_handler.session_id,
                "protocol_version": protocol_version,
                "transport": "websocket",
                "features": list(response["features"].keys())
            })
            
            return response
            
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error("unknown", "Hello处理异常", f"处理Hello消息时发生异常: {e}", {
                "error_type": type(e).__name__
            })
            return {
                "type": "error",
                "message": f"Hello消息处理失败: {str(e)}"
            }


class AudioMessageHandler(MessageHandler):
    """音频消息处理器 - 集成流式音频交互处理"""
    
    def __init__(self):
        super().__init__(MessageType.AUDIO)
        self.asr_service = None  # 延迟初始化
        self.speech_coordinator = None  # 延迟初始化
        self.device_audio_sessions = {}  # 设备音频会话管理
        
        # 流式ASR缓冲区
        self.streaming_buffers = {}  # {device_id: {"opus_buffer": bytearray, "frame_count": int, "frame_sizes": List[int], ...}}
        
        # 流式ASR服务（基于Fun-ASR官方示例）
        self.streaming_asr_integrations = {}  # {device_id: ESP32StreamingASRIntegration}
        self.use_streaming_asr = True  # 是否使用流式ASR（可配置）
        
        # 保存事件循环引用，用于在回调中安全地调度协程
        self._event_loop = None

        # 流式部分识别提前触发配置
        self.partial_promotion_min_chars = 1          # 最短可提前提交的字数
        self.partial_repeat_threshold = 1             # 相同partial累计次数
        self.partial_stable_duration = 0.4            # 相同partial保持时间(秒)
        self.partial_sentence_endings = ("。", "！", "？", ".", "!", "?")
        self.completed_dedup_window = 1.0             # 完整句子去重时间窗口(秒)
        self.partial_force_timeout = 0.6              # 静音后强制晋升partial的等待时间(秒)

    def _get_or_create_streaming_buffer(self, device_id: str) -> Dict[str, Any]:
        """确保设备拥有独立的流式缓冲区"""
        buffer_info = self.streaming_buffers.get(device_id)
        if buffer_info is None:
            buffer_info = {
                "opus_buffer": bytearray(),
                "frame_count": 0,
                "frame_sizes": [],
                "last_asr_time": 0,
                "last_trigger_time": time.time(),
                "partial_results": [],
                "is_speaking": False,
                "silence_frames": 0,
                "last_partial_text": "",
                "partial_first_seen": 0.0,
                "partial_repeat_count": 0,
                "last_partial_time": 0.0,
                "last_promoted_text": "",
                "last_completed_text": "",
                "last_completed_time": 0.0
            }
            self.streaming_buffers[device_id] = buffer_info
        return buffer_info

    def _reset_partial_tracking(self, buffer_info: Dict[str, Any]):
        """复位与partial识别相关的追踪状态"""
        buffer_info.setdefault("partial_results", [])
        buffer_info["partial_results"].clear()
        buffer_info["last_partial_text"] = ""
        buffer_info["partial_first_seen"] = 0.0
        buffer_info["partial_repeat_count"] = 0
        buffer_info["last_partial_time"] = 0.0
        buffer_info["last_promoted_text"] = ""
    
    async def _promote_pending_partial(self, context: MessageContext, connection_handler, buffer_info: Dict[str, Any], reason: str, force: bool = False) -> bool:
        """在静音或超时情况下强制晋升仍未完成的partial结果"""
        partial_text = (buffer_info.get("last_partial_text") or "").strip()
        if not partial_text:
            return False
        
        if partial_text == buffer_info.get("last_promoted_text"):
            return False
        
        last_partial_time = buffer_info.get("last_partial_time", 0.0)
        if not force:
            if not last_partial_time:
                return False
            if time.time() - last_partial_time < self.partial_force_timeout:
                return False
        
        from app.core.device_logger import log_esp32_audio
        log_esp32_audio(context.device_id, "⚠️ 静音期间晋升partial结果", {
            "session_id": context.session_id,
            "reason": reason,
            "text": partial_text
        })
        
        buffer_info["last_promoted_text"] = partial_text
        buffer_info["partial_repeat_count"] = 0
        buffer_info["last_partial_text"] = ""
        
        await self._handle_streaming_asr_result(
            context,
            connection_handler,
            partial_text,
            is_partial=False
        )
        return True
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证音频消息格式"""
        return "audio_data" in data or isinstance(data, bytes)
    
    def get_priority(self, data: Dict[str, Any]) -> MessagePriority:
        """音频消息优先级较高"""
        return MessagePriority.HIGH
    
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理音频消息"""
        try:
            # 保存当前事件循环引用（用于回调中安全地调度协程）
            if self._event_loop is None:
                self._event_loop = asyncio.get_event_loop()
            
            # 延迟初始化服务（使用实际的device_id）
            if self.asr_service is None:
                self.asr_service = get_esp32_asr_integration(context.device_id)
            if self.speech_coordinator is None:
                self.speech_coordinator = get_esp32_speech_coordinator(context.device_id)
            
            # 使用设备日志系统记录音频数据接收
            from app.core.device_logger import log_esp32_audio, log_esp32_protocol
            
            # 提取音频数据
            if isinstance(context.raw_data, bytes):
                audio_data = context.raw_data
                data_source = "原始字节数据"
            else:
                audio_data = context.parsed_data.get("audio_data")
                data_source = "解析后数据"
            
            if not audio_data:
                from app.core.device_logger import log_esp32_error
                log_esp32_error(context.device_id, "音频数据无效", "音频消息中没有有效的音频数据", {
                    "session_id": context.session_id,
                    "message_type": context.message_type,
                    "data_source": data_source
                })
                return {"type": "error", "message": "无效的音频数据"}
            
            # 记录音频数据接收
            from app.core.device_logger import log_esp32_audio
            log_esp32_audio(context.device_id, "音频帧接收", {
                "session_id": context.session_id,
                "data_size": len(audio_data),
                "data_source": data_source,
                "timestamp": context.timestamp,
                "hex_preview": audio_data[:16].hex() if len(audio_data) >= 16 else audio_data.hex()
            })
            
            # 检查音频数据大小，过滤空音频帧
            if len(audio_data) < 10:  # 小于10字节的认为是空音频帧
                log_esp32_audio(context.device_id, "跳过空音频帧", {
                    "data_size": len(audio_data),
                    "threshold": 10,
                    "reason": "数据包过小"
                })
                return None  # 不处理空音频帧
            
            # 检查是否包含BinaryProtocol2头部（ESP32发送的音频数据格式）
            opus_data = audio_data
            if len(audio_data) >= 12:
                # 检查前两个字节是否是协议版本标识（00 02）
                if audio_data[0] == 0x00 and audio_data[1] == 0x02:
                    # 这是BinaryProtocol2格式，提取实际的Opus数据
                    # 格式：version(2) + type(2) + timestamp(4) + payload_size(4) + opus_data
                    opus_data = audio_data[12:]  # 跳过12字节头部
                    log_esp32_audio(context.device_id, "提取Opus数据", {
                        "原始大小": len(audio_data),
                        "头部大小": 12,
                        "Opus大小": len(opus_data),
                        "协议版本": "BinaryProtocol2"
                    })
            
            # 再次检查提取后的Opus数据大小
            if len(opus_data) < 5:  # Opus数据至少需要几个字节
                log_esp32_audio(context.device_id, "跳过无效Opus数据", {
                    "opus_size": len(opus_data),
                    "threshold": 5,
                    "reason": "Opus数据过小"
                })
                return None
            
            # 确保音频会话已记录
            session_key = f"{context.device_id}_{context.session_id}"
            if session_key not in self.device_audio_sessions:
                self.device_audio_sessions[session_key] = {
                    "device_id": context.device_id,
                    "session_id": context.session_id,
                    "connection_handler": connection_handler
                }
                from app.core.device_logger import log_esp32_service
                log_esp32_service("音频会话", "启动音频处理会话", {
                    "device_id": context.device_id,
                    "session_id": context.session_id,
                    "session_key": session_key
                })
            
            # 根据配置选择处理方式
            if self.use_streaming_asr:
                # 使用基于Fun-ASR官方示例的流式ASR服务
                await self._process_realtime_streaming_asr(context, connection_handler, opus_data)
            else:
                # 使用原有的批处理流式ASR
                await self._process_streaming_asr(context, connection_handler, opus_data)
            
            return None
            
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error(context.device_id, "音频处理异常", f"处理音频消息时发生异常: {e}", {
                "session_id": context.session_id,
                "message_type": context.message_type,
                "error_type": type(e).__name__
            })
            return {
                "type": "error",
                "message": f"音频处理失败: {str(e)}"
            }
    
    async def _process_realtime_streaming_asr(self, context: MessageContext, connection_handler, opus_data: bytes):
        """
        实时流式ASR处理（基于Fun-ASR官方示例）
        持续接收音频帧，实时发送到流式ASR服务进行识别
        """
        try:
            from app.core.device_logger import log_esp32_audio
            from app.devices.esp32.services.asr_service_integration import get_esp32_asr_integration
            
            # 获取或创建流式ASR集成器
            if context.device_id not in self.streaming_asr_integrations:
                # 创建流式ASR配置
                config = StreamingASRConfig(
                    mode=StreamingASRMode.CONTINUOUS,
                    frame_interval_ms=40,   # 更快推送短语音片段
                    min_frame_size=1280,    # 单个40ms帧即可触发发送
                    max_frame_size=8192,    # 保持低延迟的最大帧
                    silence_timeout=0.8,    # 更快检测短语音结束
                    auto_stop=True
                )
                
                streaming_asr = get_streaming_asr_integration(context.device_id, config)
                
                # 添加回调函数
                # 获取事件循环引用（在异步上下文中）
                event_loop = asyncio.get_event_loop()
                
                def on_sentence(text: str):
                    """完整句子回调"""
                    log_esp32_audio(context.device_id, "流式ASR完整句子", {
                        "session_id": context.session_id,
                        "text": text
                    })
                    # 触发后续处理（意图识别、LLM对话等）
                    # 安全地在事件循环中调度协程
                    try:
                        # 尝试在当前线程的事件循环中创建任务
                        try:
                            asyncio.get_running_loop()
                            # 如果成功获取到运行中的事件循环，使用 create_task
                            asyncio.create_task(self._handle_streaming_asr_result(
                                context, connection_handler, text, is_partial=False
                            ))
                        except RuntimeError:
                            # 如果没有运行的事件循环，使用 run_coroutine_threadsafe
                            # 这适用于回调在不同线程中被调用的情况
                            asyncio.run_coroutine_threadsafe(
                                self._handle_streaming_asr_result(
                                    context, connection_handler, text, is_partial=False
                                ),
                                event_loop
                            )
                    except Exception as e:
                        # 如果所有方法都失败，记录错误但不抛出异常
                        logging.getLogger(__name__).error(
                            f"[AudioMessageHandler] 无法调度完整句子处理协程: {e}"
                        )
                
                def on_partial(text: str):
                    """部分结果回调"""
                    log_esp32_audio(context.device_id, "流式ASR部分结果", {
                        "session_id": context.session_id,
                        "text": text
                    })
                    # 可以发送部分结果到客户端（可选）
                    # 安全地在事件循环中调度协程
                    try:
                        # 尝试在当前线程的事件循环中创建任务
                        try:
                            asyncio.get_running_loop()
                            # 如果成功获取到运行中的事件循环，使用 create_task
                            asyncio.create_task(self._handle_streaming_asr_result(
                                context, connection_handler, text, is_partial=True
                            ))
                        except RuntimeError:
                            # 如果没有运行的事件循环，使用 run_coroutine_threadsafe
                            # 这适用于回调在不同线程中被调用的情况
                            asyncio.run_coroutine_threadsafe(
                                self._handle_streaming_asr_result(
                                    context, connection_handler, text, is_partial=True
                                ),
                                event_loop
                            )
                    except Exception as e:
                        # 如果所有方法都失败，记录错误但不抛出异常
                        logging.getLogger(__name__).error(
                            f"[AudioMessageHandler] 无法调度部分结果处理协程: {e}"
                        )
                
                streaming_asr.add_sentence_callback(on_sentence)
                streaming_asr.add_partial_callback(on_partial)
                
                # 启动流式识别
                await streaming_asr.start()
                self.streaming_asr_integrations[context.device_id] = streaming_asr
                
                log_esp32_audio(context.device_id, "流式ASR服务已启动", {
                    "session_id": context.session_id,
                    "mode": "continuous"
                })
            
            streaming_asr = self.streaming_asr_integrations[context.device_id]
            
            # 将Opus数据解码为PCM
            asr_integration = get_esp32_asr_integration(context.device_id)
            frame_sizes = [len(opus_data)]
            pcm_data = asr_integration._decode_opus_to_pcm(opus_data, 1, frame_sizes)
            
            if not pcm_data:
                log_esp32_audio(context.device_id, "Opus解码失败", {
                    "session_id": context.session_id,
                    "opus_size": len(opus_data)
                })
                return
            
            # 发送PCM数据到流式ASR服务
            success = await streaming_asr.send_audio_frame(pcm_data)
            
            if success:
                log_esp32_audio(context.device_id, "音频帧已发送到流式ASR", {
                    "session_id": context.session_id,
                    "pcm_size": len(pcm_data),
                    "opus_size": len(opus_data)
                })
            
            # 检查静音超时
            silence_stopped = await streaming_asr.check_silence_timeout()
            if silence_stopped:
                timeout_buffer_info = self._get_or_create_streaming_buffer(context.device_id)
                await self._promote_pending_partial(
                    context,
                    connection_handler,
                    timeout_buffer_info,
                    "静音超时自动停止",
                    force=True
                )
            
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error(context.device_id, "实时流式ASR处理异常", f"处理实时流式ASR时发生异常: {e}", {
                "session_id": context.session_id,
                "error_type": type(e).__name__
            })
    
    async def _handle_streaming_asr_result(self, context: MessageContext, connection_handler, text: str, is_partial: bool):
        """处理流式ASR识别结果"""
        try:
            from app.core.device_logger import log_esp32_audio
            from app.devices.esp32.services.asr_service_integration import ASRResult, ASRQuality
            
            buffer_info = self._get_or_create_streaming_buffer(context.device_id)
            
            if is_partial:
                partial_text = (text or "").strip()
                log_esp32_audio(context.device_id, "流式ASR部分结果", {
                    "session_id": context.session_id,
                    "text": partial_text
                })

                if not partial_text:
                    return

                current_time = time.time()
                buffer_info["last_partial_time"] = current_time

                # 如果该partial已经被提升为完整句子，则忽略重复回调
                if partial_text == buffer_info.get("last_promoted_text"):
                    return

                # 记录partial稳定性
                last_partial = buffer_info.get("last_partial_text", "")
                if partial_text == last_partial:
                    buffer_info["partial_repeat_count"] = buffer_info.get("partial_repeat_count", 0) + 1
                else:
                    buffer_info["last_partial_text"] = partial_text
                    buffer_info["partial_repeat_count"] = 1
                    buffer_info["partial_first_seen"] = current_time

                stable_duration = current_time - buffer_info.get("partial_first_seen", current_time)
                should_promote = False

                # 规则1：末尾出现句子终止符号
                if partial_text.endswith(self.partial_sentence_endings):
                    should_promote = len(partial_text) >= self.partial_promotion_min_chars
                # 规则2：partial在一定时间窗口内保持稳定
                elif (buffer_info["partial_repeat_count"] >= self.partial_repeat_threshold and
                      stable_duration >= self.partial_stable_duration and
                      len(partial_text) >= self.partial_promotion_min_chars):
                    should_promote = True

                if should_promote:
                    buffer_info["last_promoted_text"] = partial_text
                    buffer_info["partial_repeat_count"] = 0
                    buffer_info["last_partial_text"] = ""
                    await self._handle_streaming_asr_result(
                        context,
                        connection_handler,
                        partial_text,
                        is_partial=False
                    )
                return
            else:
                # 完整句子：触发后续处理
                log_esp32_audio(context.device_id, "流式ASR完整句子", {
                    "session_id": context.session_id,
                    "text": text
                })

                final_text = (text or "").strip()
                if not final_text:
                    return

                current_time = time.time()
                last_completed = buffer_info.get("last_completed_text")
                last_completed_time = buffer_info.get("last_completed_time", 0.0)
                if (last_completed and final_text == last_completed and
                        current_time - last_completed_time < self.completed_dedup_window):
                    log_esp32_audio(context.device_id, "⚠️ 流式ASR重复句子已忽略", {
                        "session_id": context.session_id,
                        "text": final_text
                    })
                    return

                buffer_info["last_completed_text"] = final_text
                buffer_info["last_completed_time"] = current_time
                buffer_info["last_promoted_text"] = final_text
                buffer_info["partial_repeat_count"] = 0
                buffer_info["last_partial_text"] = ""
                
                # 创建ASRResult对象（兼容现有流程）
                asr_result = ASRResult(
                    text=final_text,
                    confidence=0.9,  # 流式ASR的置信度
                    quality=ASRQuality.GOOD,
                    processing_time=0.0,  # 流式处理，无固定处理时间
                    audio_duration=0.0,   # 流式处理，无固定音频时长
                    frame_count=0,        # 流式处理，无固定帧数
                    total_bytes=0,         # 流式处理，无固定字节数
                    is_valid=True,
                    metadata={
                        "source": "streaming_asr",
                        "device_id": context.device_id,
                        "session_id": context.session_id
                    }
                )
                
                # 创建交互请求（使用空的音频帧，因为ASR已经完成）
                from app.devices.esp32.services import InteractionRequest
                from app.devices.esp32.audio import AudioFrame
                
                # 创建一个虚拟的音频帧，用于兼容现有接口
                # 注意：这个音频帧不会被用于ASR，因为ASR已经完成
                virtual_audio_frame = AudioFrame(
                    data=b"",  # 空数据
                    timestamp=time.time(),
                    sequence_number=0,
                    frame_size=0,
                    sample_rate=16000,
                    channels=1,
                    format="pcm",
                    metadata={
                        "source": "streaming_asr",
                        "asr_result": final_text,  # 保存识别结果
                        "skip_asr": True     # 标记跳过ASR
                    }
                )
                
                interaction_request = InteractionRequest(
                    audio_frames=[virtual_audio_frame],
                    device_id=context.device_id,
                    session_id=context.session_id,
                    metadata={
                        "asr_result": asr_result,  # 传递ASR结果
                        "skip_asr": True          # 标记跳过ASR阶段
                    }
                )
                
                # 调用语音交互协调器
                # 注意：需要修改协调器以支持跳过ASR阶段
                if self.speech_coordinator is None:
                    self.speech_coordinator = get_esp32_speech_coordinator(context.device_id)
                
                response = await self.speech_coordinator.process_speech_interaction(interaction_request)
                await self._handle_streaming_response(
                    context,
                    connection_handler,
                    response,
                    "实时流式ASR结果",
                    buffer_info
                )
                
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error(context.device_id, "流式ASR结果处理异常", f"处理流式ASR结果时发生异常: {e}", {
                "session_id": context.session_id,
                "error_type": type(e).__name__
            })
    
    async def _process_streaming_asr(self, context: MessageContext, connection_handler, opus_data: bytes):
        """流式ASR处理 - 实时流式语音交互"""
        try:
            from app.core.device_logger import log_esp32_audio
            
            # 记录进入流式ASR处理
            log_esp32_audio(context.device_id, "进入流式ASR处理", {
                "session_id": context.session_id,
                "opus_data_size": len(opus_data) if opus_data else 0
            })
            
            # 延迟初始化语音交互协调器
            if self.speech_coordinator is None:
                from app.devices.esp32.services import get_esp32_speech_coordinator
                self.speech_coordinator = get_esp32_speech_coordinator(context.device_id)
            
            # 验证Opus数据有效性
            if not opus_data or len(opus_data) < 10:
                log_esp32_audio(context.device_id, "流式ASR跳过", {
                    "reason": "Opus数据无效或过小",
                    "opus_size": len(opus_data) if opus_data else 0
                })
                return
            
            # 流式交互参数配置
            STREAMING_WINDOW = 5  # 流式窗口：5帧 (约200ms) - 降低阈值以更快响应短句子
            MIN_FRAMES_FOR_SHORT_SENTENCE = 3  # 短句子最小帧数：3帧 (约120ms)
            SILENCE_THRESHOLD = 8  # 静音阈值：8帧 (约320ms) - 降低以更快检测句子结束
            MAX_BUFFER_FRAMES = 200  # 最大缓冲：200帧 (约4秒)
            TIMEOUT_SECONDS = 0.2  # 超时触发：0.2秒没有触发就强制触发 - 降低以更快响应
            
            # 获取当前时间（用于初始化）
            current_time = time.time()
            
            buffer_info = self._get_or_create_streaming_buffer(context.device_id)
            buffer_info.setdefault("last_trigger_time", current_time)
            buffer_info["opus_buffer"].extend(opus_data)
            buffer_info["frame_sizes"].append(len(opus_data))  # 保存帧大小
            buffer_info["frame_count"] += 1
            
            # 确保 last_trigger_time 已初始化
            if "last_trigger_time" not in buffer_info:
                buffer_info["last_trigger_time"] = current_time
            
            # 添加调试日志：显示缓冲区状态
            if buffer_info["frame_count"] % 5 == 0:  # 每5帧记录一次
                log_esp32_audio(context.device_id, "流式缓冲区状态", {
                    "session_id": context.session_id,
                    "frame_count": buffer_info["frame_count"],
                    "buffer_size": len(buffer_info["opus_buffer"]),
                    "next_trigger_at": STREAMING_WINDOW - (buffer_info["frame_count"] % STREAMING_WINDOW),
                    "is_speaking": buffer_info.get("is_speaking", False),
                    "silence_frames": buffer_info.get("silence_frames", 0),
                    "time_since_last_trigger": current_time - buffer_info.get("last_trigger_time", current_time)
                })
            
            # 流式ASR触发策略
            current_time = time.time()
            should_trigger_asr = False
            trigger_reason = ""
            should_force_promote_partial = False
            
            # 检测当前帧是否为静音
            is_current_silence = self._is_silence_frame(opus_data)
            
            # 策略1: 定期流式识别 (每5帧，约200ms)
            if buffer_info["frame_count"] % STREAMING_WINDOW == 0:
                should_trigger_asr = True
                trigger_reason = "定期流式识别"
                log_esp32_audio(context.device_id, "触发流式ASR", {
                    "session_id": context.session_id,
                    "trigger_reason": trigger_reason,
                    "frame_count": buffer_info["frame_count"],
                    "buffer_size": len(buffer_info["opus_buffer"])
                })
            
            # 策略2: 超时触发 (如果超过0.2秒没有触发，强制触发)
            elif current_time - buffer_info.get("last_trigger_time", current_time) >= TIMEOUT_SECONDS:
                should_trigger_asr = True
                trigger_reason = "超时触发"
                log_esp32_audio(context.device_id, "触发流式ASR", {
                    "session_id": context.session_id,
                    "trigger_reason": trigger_reason,
                    "frame_count": buffer_info["frame_count"],
                    "buffer_size": len(buffer_info["opus_buffer"]),
                    "time_since_last_trigger": current_time - buffer_info.get("last_trigger_time", current_time)
                })
            
            # 策略3: 短句子检测 - 如果已经有3帧以上，且连续3帧静音，立即触发
            if not should_trigger_asr:
                if is_current_silence:
                    # 当前帧是静音，增加静音计数
                    buffer_info["silence_frames"] = buffer_info.get("silence_frames", 0) + 1
                    
                    # 如果已经有足够的帧数（>=3帧），且之前有语音，且连续3帧静音，可能是短句子结束
                    if (buffer_info["frame_count"] >= MIN_FRAMES_FOR_SHORT_SENTENCE and 
                        buffer_info.get("is_speaking", False) and 
                        buffer_info["silence_frames"] >= 3):
                        should_trigger_asr = True
                        trigger_reason = "短句子检测触发"
                        should_force_promote_partial = True
                        buffer_info["is_speaking"] = False
                        log_esp32_audio(context.device_id, "触发流式ASR", {
                            "session_id": context.session_id,
                            "trigger_reason": trigger_reason,
                            "frame_count": buffer_info["frame_count"],
                            "silence_frames": buffer_info["silence_frames"],
                            "note": "检测到可能的短句子结束（3帧静音）"
                        })
                else:
                    # 非静音帧，重置静音计数，标记为正在说话
                    buffer_info["silence_frames"] = 0
                    buffer_info["is_speaking"] = True
            
            # 策略4: 静音检测触发完整识别（长句子）- 连续8帧静音
            if not should_trigger_asr:
                if is_current_silence:
                    # 如果连续静音达到阈值，且之前有语音，触发完整识别
                    if buffer_info.get("silence_frames", 0) >= SILENCE_THRESHOLD and buffer_info.get("is_speaking", False):
                        should_trigger_asr = True
                        trigger_reason = "静音检测触发"
                        should_force_promote_partial = True
                        buffer_info["is_speaking"] = False
                        log_esp32_audio(context.device_id, "触发流式ASR", {
                            "session_id": context.session_id,
                            "trigger_reason": trigger_reason,
                            "frame_count": buffer_info["frame_count"],
                            "silence_frames": buffer_info["silence_frames"]
                        })
            
            # 策略5: 缓冲区满时强制识别
            if buffer_info["frame_count"] >= MAX_BUFFER_FRAMES:
                should_trigger_asr = True
                trigger_reason = "缓冲区满"
                log_esp32_audio(context.device_id, "触发流式ASR", {
                    "session_id": context.session_id,
                    "trigger_reason": trigger_reason,
                    "frame_count": buffer_info["frame_count"]
                })
            
            # 执行流式ASR识别
            if should_trigger_asr:
                # 检查缓冲区是否有有效的音频数据
                buffer_size = len(buffer_info["opus_buffer"])
                frame_count = buffer_info["frame_count"]
                
                # 如果缓冲区为空，跳过识别
                if buffer_size == 0:
                    log_esp32_audio(context.device_id, "跳过ASR识别", {
                        "session_id": context.session_id,
                        "trigger_reason": trigger_reason,
                        "reason": "缓冲区为空，无需识别"
                    })
                    # 更新触发时间，避免频繁触发
                    buffer_info["last_trigger_time"] = current_time
                    return
                
                # 如果缓冲区数据过小（小于一个有效Opus帧的最小大小，通常至少需要几十字节）
                # 或者帧数为0，说明没有有效的音频数据
                MIN_VALID_OPUS_SIZE = 20  # Opus帧的最小有效大小（字节）
                if buffer_size < MIN_VALID_OPUS_SIZE or frame_count == 0:
                    log_esp32_audio(context.device_id, "跳过ASR识别", {
                        "session_id": context.session_id,
                        "trigger_reason": trigger_reason,
                        "reason": f"缓冲区数据过小（{buffer_size}字节，{frame_count}帧），可能是空音频",
                        "buffer_size": buffer_size,
                        "frame_count": frame_count
                    })
                    # 清空缓冲区并更新触发时间
                    buffer_info["opus_buffer"].clear()
                    buffer_info["frame_count"] = 0
                    buffer_info["frame_sizes"].clear()
                    self._reset_partial_tracking(buffer_info)
                    buffer_info["last_trigger_time"] = current_time
                    return
                
                # 保存当前缓冲区大小，用于判断是否识别成功
                buffer_size_before = len(buffer_info["opus_buffer"])
                await self._execute_streaming_asr(context, connection_handler, buffer_info, trigger_reason)
                
                # 清理策略：根据触发原因决定清理程度
                if trigger_reason == "静音检测触发":
                    # 完整识别后清空缓冲区
                    buffer_info["opus_buffer"].clear()
                    buffer_info["frame_count"] = 0
                    buffer_info["frame_sizes"].clear()
                    self._reset_partial_tracking(buffer_info)
                elif trigger_reason == "缓冲区满":
                    # 保留最后25%的数据作为上下文
                    keep_size = len(buffer_info["opus_buffer"]) // 4
                    buffer_info["opus_buffer"] = buffer_info["opus_buffer"][-keep_size:]
                    # 同步清理帧大小信息
                    keep_frames = len(buffer_info["frame_sizes"]) // 4
                    buffer_info["frame_sizes"] = buffer_info["frame_sizes"][-keep_frames:]
                    buffer_info["frame_count"] = buffer_info["frame_count"] // 4
                # 对于"定期流式识别"和"超时触发"，如果识别成功，也应该清空缓冲区
                # 避免重复识别相同的内容
                # 注意：缓冲区清空会在_handle_streaming_response中根据识别结果决定
                
                buffer_info["last_asr_time"] = current_time
                buffer_info["last_trigger_time"] = current_time  # 更新触发时间戳

                if should_force_promote_partial:
                    await self._promote_pending_partial(
                        context,
                        connection_handler,
                        buffer_info,
                        trigger_reason,
                        force=True
                    )
        
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error(context.device_id, "流式ASR异常", f"流式ASR处理异常: {e}", {
                "session_id": context.session_id,
                "error_type": type(e).__name__
            })
    
    async def _execute_streaming_asr(self, context: MessageContext, connection_handler, buffer_info: dict, trigger_reason: str):
        """执行流式ASR识别"""
        try:
            from app.core.device_logger import log_esp32_audio
            import time
            
            # 准备ASR数据 - 修复Opus帧处理
            # ESP32发送的每个数据包都是独立的40ms Opus帧
            # 我们需要发送完整的累积数据，但标记为合并的Opus流
            asr_data = bytes(buffer_info["opus_buffer"])
            
            # 添加调试信息
            print(f"🔥 [DEBUG] ASR数据准备: {len(asr_data)}字节, 来自{buffer_info['frame_count']}个ESP32数据包")
            
            log_esp32_audio(context.device_id, "流式ASR执行", {
                "session_id": context.session_id,
                "trigger_reason": trigger_reason,
                "opus_data_size": len(asr_data),
                "total_frames": buffer_info["frame_count"]
            })
            
            # 创建音频帧和交互请求
            from app.devices.esp32.services import InteractionRequest
            from app.devices.esp32.audio import AudioFrame
            
            # 创建单个AudioFrame包含所有Opus数据
            # 不要分割Opus数据，保持完整性
            audio_frame = AudioFrame(
                data=bytes(asr_data),
                timestamp=time.time(),
                sequence_number=buffer_info["frame_count"],
                frame_size=len(asr_data),
                sample_rate=16000,
                channels=1,
                format="opus",
                metadata={
                    "source": "streaming_asr", 
                    "device_id": context.device_id,
                    "trigger_reason": trigger_reason,
                    "total_frames": buffer_info["frame_count"],
                    "opus_frames_merged": True,  # 标记这是合并的Opus数据
                    "frame_sizes": buffer_info.get("frame_sizes", [])  # 保存帧大小信息用于解码
                }
            )
            audio_frames = [audio_frame]
            
            interaction_request = InteractionRequest(
                audio_frames=audio_frames,
                device_id=context.device_id,
                session_id=context.session_id
            )
            
            # 添加调试日志
            log_esp32_audio(context.device_id, "🔧 AudioFrame创建完成", {
                "session_id": context.session_id,
                "创建帧数": len(audio_frames),
                "总帧数": buffer_info["frame_count"],
                "Opus数据大小": len(asr_data),
                "保持完整性": True
            })
            
            # 调用语音交互协调器进行流式对话处理
            response = await self.speech_coordinator.process_speech_interaction(interaction_request)
            
            # 处理流式响应
            await self._handle_streaming_response(context, connection_handler, response, trigger_reason, buffer_info)
            
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error(context.device_id, "流式ASR执行异常", f"执行流式ASR时发生异常: {e}", {
                "session_id": context.session_id,
                "error_type": type(e).__name__
            })
    
    async def _handle_streaming_response(self, context: MessageContext, connection_handler, response, trigger_reason: str, buffer_info: dict):
        """处理流式响应"""
        try:
            from app.core.device_logger import log_esp32_audio
            from app.devices.esp32.services import InteractionResult
            
            # 检查session_id是否匹配当前会话（防止使用旧的session_id）
            if connection_handler.session and connection_handler.session.session_id != context.session_id:
                log_esp32_audio(context.device_id, "⚠️ 会话ID不匹配，跳过响应", {
                    "request_session_id": context.session_id,
                    "current_session_id": connection_handler.session.session_id,
                    "result": str(response.result) if hasattr(response, 'result') else "无result属性"
                })
                return  # 跳过处理，因为这是旧会话的响应
            
            # 调试：检查response的详细内容
            log_esp32_audio(context.device_id, "流式响应处理", {
                "session_id": context.session_id,
                "trigger_reason": trigger_reason,
                "response_result": str(response.result) if hasattr(response, 'result') else "无result属性",
                "has_asr_result": response.asr_result is not None if hasattr(response, 'asr_result') else False,
                "asr_text": response.asr_result.text if (hasattr(response, 'asr_result') and response.asr_result and hasattr(response.asr_result, 'text')) else "无ASR文本",
                "tts_frames": len(response.tts_result.audio_frames) if (hasattr(response, 'tts_result') and response.tts_result and hasattr(response.tts_result, 'audio_frames')) else 0
            })
            
            # 流式响应处理策略
            if response.result == InteractionResult.SUCCESS:
                # 处理ASR识别结果
                if response.asr_result:
                    if response.asr_result.text and response.asr_result.text.strip():
                        asr_text = response.asr_result.text.strip()
                        
                        # 更新部分结果缓存
                        if trigger_reason == "定期流式识别":
                            buffer_info["partial_results"].append(asr_text)
                            # 发送部分识别结果给ESP32
                            await self._send_partial_result(connection_handler, context, asr_text)
                            
                            # 即使是在定期流式识别时，也记录意图识别和LLM回复（如果存在）
                            if response.intent_result:
                                log_esp32_audio(context.device_id, "🧠 意图识别完成", {
                                    "session_id": context.session_id,
                                    "意图类型": str(response.intent_result.intent_type) if hasattr(response.intent_result, 'intent_type') else "未知",
                                    "情绪状态": getattr(response.intent_result, 'emotional_state', '未知'),
                                    "风险等级": getattr(response.intent_result, 'risk_level', '未知')
                                })
                                
                            if response.intent_result and response.intent_result.response_text:
                                log_esp32_audio(context.device_id, "💬 LLM回复生成", {
                                    "session_id": context.session_id,
                                    "回复内容": response.intent_result.response_text[:50] + "..." if len(response.intent_result.response_text) > 50 else response.intent_result.response_text,
                                    "回复长度": len(response.intent_result.response_text)
                                })
                        else:
                            # 完整识别结果
                            full_text = " ".join(buffer_info["partial_results"] + [asr_text])
                            log_esp32_audio(context.device_id, "✅ 完整ASR识别", {
                                "session_id": context.session_id,
                                "full_text": full_text,
                                "trigger_reason": trigger_reason,
                                "识别文本": response.asr_result.text,
                                "置信度": getattr(response.asr_result, 'confidence', 0.0)
                            })
                            
                            # 完整识别成功后，清空缓冲区，避免重复识别
                            buffer_info["opus_buffer"].clear()
                            buffer_info["frame_count"] = 0
                            buffer_info["frame_sizes"].clear()
                            buffer_info["partial_results"].clear()
                            self._reset_partial_tracking(buffer_info)
                            log_esp32_audio(context.device_id, "🧹 完整识别后清空缓冲区", {
                                "session_id": context.session_id
                            })
                            
                            # 2. 记录意图识别结果
                            if response.intent_result:
                                log_esp32_audio(context.device_id, "🧠 意图识别完成", {
                                    "session_id": context.session_id,
                                    "意图类型": str(response.intent_result.intent_type) if hasattr(response.intent_result, 'intent_type') else "未知",
                                    "情绪状态": getattr(response.intent_result, 'emotional_state', '未知'),
                                    "风险等级": getattr(response.intent_result, 'risk_level', '未知')
                                })
                                
                            # 3. 记录LLM回复生成结果
                            if response.intent_result and response.intent_result.response_text:
                                log_esp32_audio(context.device_id, "💬 LLM回复生成", {
                                    "session_id": context.session_id,
                                    "回复内容": response.intent_result.response_text[:50] + "..." if len(response.intent_result.response_text) > 50 else response.intent_result.response_text,
                                    "回复长度": len(response.intent_result.response_text)
                                })
                                
                            # 4. 记录TTS合成结果
                            if response.tts_result:
                                if hasattr(response.tts_result, 'audio_frames') and response.tts_result.audio_frames:
                                    log_esp32_audio(context.device_id, "🎵 TTS合成完成", {
                                        "session_id": context.session_id,
                                        "音频帧数": len(response.tts_result.audio_frames),
                                        "音频大小": sum(len(frame.data) if hasattr(frame, 'data') else len(frame) for frame in response.tts_result.audio_frames),
                                        "格式": "opus"
                                    })
                                elif hasattr(response.tts_result, 'audio_data') and response.tts_result.audio_data:
                                    log_esp32_audio(context.device_id, "🎵 TTS合成完成", {
                                        "session_id": context.session_id,
                                        "音频大小": len(response.tts_result.audio_data),
                                        "格式": "opus"
                                    })
                                
                            # 5. 发送TTS开始消息和音频到ESP32设备
                            try:
                                # 先发送TTS开始消息，让ESP32切换到Speaking状态
                                tts_start_message = {
                                    "type": "tts",
                                    "state": "start",
                                    "session_id": context.session_id
                                }
                                await connection_handler.send_message(tts_start_message)
                                
                                # 检查TTS结果的音频数据格式
                                if hasattr(response.tts_result, 'audio_data') and response.tts_result.audio_data:
                                    await connection_handler.send_audio_data(
                                        response.tts_result.audio_data,
                                        audio_format="opus"
                                    )
                                    log_esp32_audio(context.device_id, "📤 音频发送到ESP32", {
                                        "session_id": context.session_id,
                                        "音频大小": len(response.tts_result.audio_data),
                                        "格式": "opus"
                                    })
                                elif hasattr(response.tts_result, 'audio_frames') and response.tts_result.audio_frames:
                                    # 如果是音频帧格式，需要合并
                                    audio_data = b''.join(frame.data if hasattr(frame, 'data') else frame for frame in response.tts_result.audio_frames)
                                    await connection_handler.send_audio_data(
                                        audio_data,
                                        audio_format="opus"
                                    )
                                    log_esp32_audio(context.device_id, "📤 音频发送到ESP32", {
                                        "session_id": context.session_id,
                                        "音频帧数": len(response.tts_result.audio_frames),
                                        "合并后大小": len(audio_data),
                                        "格式": "opus"
                                    })
                                else:
                                    log_esp32_audio(context.device_id, "❌ TTS发送跳过", {
                                        "session_id": context.session_id,
                                        "reason": "没有找到音频数据"
                                    })
                                
                                # 发送TTS结束消息，让ESP32知道音频播放完成
                                tts_stop_message = {
                                    "type": "tts",
                                    "state": "stop",
                                    "session_id": context.session_id
                                }
                                await connection_handler.send_message(tts_stop_message)
                            except Exception as e:
                                log_esp32_audio(context.device_id, "❌ TTS发送失败", {
                                    "session_id": context.session_id,
                                    "error": str(e)
                                })
                    else:
                        # ASR结果为空，发送空结果响应给设备
                        log_esp32_audio(context.device_id, "⚠️ ASR结果为空", {
                            "session_id": context.session_id,
                            "trigger_reason": trigger_reason
                        })
                        try:
                            asr_empty_response = {
                                "type": "asr_result",
                                "session_id": context.session_id,
                                "text": "",
                                "status": "empty",
                                "timestamp": time.time()
                            }
                            await connection_handler.send_message(asr_empty_response)
                            log_esp32_audio(context.device_id, "📤 ASR空结果响应已发送", {
                                "session_id": context.session_id
                            })
                        except Exception as e:
                            log_esp32_audio(context.device_id, "❌ 发送ASR空结果响应失败", {
                                "session_id": context.session_id,
                                "error": str(e)
                            })
                else:
                    # 没有ASR结果，发送错误响应
                    log_esp32_audio(context.device_id, "⚠️ 没有ASR结果", {
                        "session_id": context.session_id,
                        "trigger_reason": trigger_reason
                    })
                    try:
                        asr_error_response = {
                            "type": "asr_result",
                            "session_id": context.session_id,
                            "text": "",
                            "status": "failed",
                            "error": "ASR结果为空",
                            "timestamp": time.time()
                        }
                        await connection_handler.send_message(asr_error_response)
                        log_esp32_audio(context.device_id, "📤 ASR错误响应已发送", {
                            "session_id": context.session_id
                        })
                    except Exception as e:
                        log_esp32_audio(context.device_id, "❌ 发送ASR错误响应失败", {
                            "session_id": context.session_id,
                            "error": str(e)
                        })
                
                # 处理TTS结果
                if response.tts_result and hasattr(response.tts_result, 'audio_frames'):
                    await self._send_streaming_tts(connection_handler, context, response.tts_result, trigger_reason)
            
            else:
                # 处理失败的情况
                error_message = response.error_message if hasattr(response, 'error_message') else "语音处理失败"
                result_type = str(response.result) if hasattr(response, 'result') else "未知错误"
                
                log_esp32_audio(context.device_id, "语音交互失败", {
                    "session_id": context.session_id,
                    "result": result_type,
                    "error_message": error_message
                })
                
                # 检查ASR是否识别成功（即使后续处理失败）
                # 如果ASR识别成功了，应该清空缓冲区，避免重复识别相同的内容
                asr_success = False
                if response.asr_result and hasattr(response.asr_result, 'text'):
                    asr_text = response.asr_result.text
                    if asr_text and asr_text.strip():
                        asr_success = True
                        log_esp32_audio(context.device_id, "⚠️ ASR识别成功但后续处理失败，清空缓冲区避免重复识别", {
                            "session_id": context.session_id,
                            "asr_text": asr_text.strip(),
                            "result": result_type
                        })
                        # 清空缓冲区，避免重复识别相同的内容
                        buffer_info["opus_buffer"].clear()
                        buffer_info["frame_count"] = 0
                        buffer_info["frame_sizes"].clear()
                        self._reset_partial_tracking(buffer_info)
                
                # 发送错误响应给ESP32设备
                try:
                    error_response = {
                        "type": "error",
                        "session_id": context.session_id,
                        "error_type": result_type,
                        "message": error_message,
                        "timestamp": time.time()
                    }
                    
                    # 根据错误类型发送不同的消息
                    if response.result == InteractionResult.ASR_FAILED:
                        # ASR失败时发送asr_result消息，即使结果为空
                        asr_response = {
                            "type": "asr_result",
                            "session_id": context.session_id,
                            "text": "",
                            "status": "failed",
                            "error": error_message,
                            "timestamp": time.time()
                        }
                        await connection_handler.send_message(asr_response)
                        log_esp32_audio(context.device_id, "📤 ASR失败响应已发送", {
                            "session_id": context.session_id,
                            "error": error_message
                        })
                    else:
                        # 其他错误类型发送通用错误消息
                        await connection_handler.send_message(error_response)
                        log_esp32_audio(context.device_id, "📤 错误响应已发送", {
                            "session_id": context.session_id,
                            "error_type": result_type,
                            "error": error_message
                        })
                except Exception as e:
                    log_esp32_audio(context.device_id, "❌ 发送错误响应失败", {
                        "session_id": context.session_id,
                        "error": str(e)
                    })
            
            # 清理过大的缓冲区，保持滑动窗口
            if buffer_info["frame_count"] > MAX_BUFFER_FRAMES:
                # 只保留最后25%的数据
                keep_size = len(buffer_info["opus_buffer"]) // 4
                if len(buffer_info["opus_buffer"]) > keep_size:
                    buffer_info["opus_buffer"] = buffer_info["opus_buffer"][-keep_size:]
                    # 同步清理帧大小信息
                    keep_frames = len(buffer_info.get("frame_sizes", [])) // 4
                    if len(buffer_info.get("frame_sizes", [])) > keep_frames:
                        buffer_info["frame_sizes"] = buffer_info["frame_sizes"][-keep_frames:]
                    buffer_info["frame_count"] = MAX_BUFFER_FRAMES // 4
                
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error(context.device_id, "流式响应处理异常", f"处理流式响应时发生异常: {e}", {
                "session_id": context.session_id,
                "error_type": type(e).__name__
            })
    
    def _is_silence_frame(self, opus_data: bytes) -> bool:
        """简单的静音检测 - 基于Opus数据大小"""
        # Opus编码的静音帧通常很小
        return len(opus_data) < 15
    
    async def _send_partial_result(self, connection_handler, context, partial_text: str):
        """发送部分识别结果给ESP32"""
        try:
            from app.core.device_logger import log_esp32_audio
            
            # 发送部分识别结果
            partial_message = {
                "type": "asr_partial",
                "text": partial_text,
                "session_id": context.session_id,
                "timestamp": time.time()
            }
            
            await connection_handler.send_message(partial_message)
            
            log_esp32_audio(context.device_id, "📝 部分识别结果", {
                "session_id": context.session_id,
                "partial_text": partial_text[:50] + "..." if len(partial_text) > 50 else partial_text
            })
            
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error(context.device_id, "部分结果发送失败", f"发送部分识别结果失败: {e}", {
                "session_id": context.session_id,
                "error_type": type(e).__name__
            })
    
    async def _send_streaming_tts(self, connection_handler, context, tts_result, trigger_reason: str):
        """发送流式TTS音频"""
        try:
            from app.core.device_logger import log_esp32_audio
            import asyncio
            
            if not tts_result or not hasattr(tts_result, 'audio_frames'):
                return
            
            # 流式TTS发送策略
            if trigger_reason == "定期流式识别":
                # 部分结果：快速发送小段TTS
                max_frames = min(10, len(tts_result.audio_frames))
                frames_to_send = tts_result.audio_frames[:max_frames]
            else:
                # 完整结果：发送全部TTS
                frames_to_send = tts_result.audio_frames
            
            log_esp32_audio(context.device_id, "🔊 流式TTS开始", {
                "session_id": context.session_id,
                "trigger_reason": trigger_reason,
                "total_frames": len(tts_result.audio_frames),
                "sending_frames": len(frames_to_send)
            })
            
            # 发送TTS开始消息
            tts_start_message = {
                "type": "tts",
                "state": "start",
                "session_id": context.session_id,
                "frame_count": len(frames_to_send)
            }
            await connection_handler.send_message(tts_start_message)
            
            # 流式发送TTS音频帧
            for i, audio_frame in enumerate(frames_to_send):
                try:
                    # 发送音频数据
                    await connection_handler.send_audio_frame(audio_frame)
                    
                    # 流式发送间隔控制
                    if trigger_reason == "定期流式识别":
                        await asyncio.sleep(0.02)  # 20ms间隔，更快响应
                    else:
                        await asyncio.sleep(0.05)  # 50ms间隔，稳定播放
                        
                except Exception as frame_error:
                    from app.core.device_logger import log_esp32_error
                    log_esp32_error(context.device_id, "TTS帧发送失败", f"发送第{i+1}帧失败: {frame_error}", {
                        "session_id": context.session_id,
                        "frame_index": i
                    })
                    break
            
            # 发送TTS结束消息
            tts_stop_message = {
                "type": "tts",
                "state": "stop",
                "session_id": context.session_id
            }
            await connection_handler.send_message(tts_stop_message)
            
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error(context.device_id, "流式TTS发送失败", f"流式TTS发送异常: {e}", {
                "session_id": context.session_id,
                "error_type": type(e).__name__
            })
    
    def _extract_voice_segments(self, pcm_samples):
        """激进的语音提取，专为稀疏语音信号优化"""
        # 更激进的参数配置
        VOICE_THRESHOLD = 100   # 降低语音检测阈值
        MIN_VOICE_LENGTH = 80   # 最小语音段长度 (5ms @ 16kHz)
        MAX_SILENCE_GAP = 800   # 增大静音间隔容忍度 (50ms @ 16kHz)
        AMPLIFY_FACTOR = 2      # 音频放大倍数
        
        # 第一步：找出所有非零样本
        non_zero_samples = []
        for i, sample in enumerate(pcm_samples):
            if abs(sample) > VOICE_THRESHOLD:
                non_zero_samples.append((i, sample))
        
        if len(non_zero_samples) < 100:  # 如果有效样本太少，返回空
            return []
        
        # 第二步：构建连续的语音段
        voice_segments = []
        current_segment = []
        last_index = -1
        
        for index, sample in non_zero_samples:
            # 如果与上一个样本距离太远，开始新段
            if last_index >= 0 and (index - last_index) > MAX_SILENCE_GAP:
                if len(current_segment) >= MIN_VOICE_LENGTH:
                    # 放大音频信号
                    amplified_segment = [min(32767, max(-32768, int(s * AMPLIFY_FACTOR))) for s in current_segment]
                    voice_segments.extend(amplified_segment)
                    # 添加短静音分隔
                    voice_segments.extend([0] * 160)  # 10ms静音
                current_segment = []
            
            # 填充中间的静音（如果距离不太远）
            if last_index >= 0 and (index - last_index) <= MAX_SILENCE_GAP:
                gap_size = index - last_index - 1
                if gap_size > 0:
                    current_segment.extend([0] * gap_size)
            
            current_segment.append(sample)
            last_index = index
        
        # 处理最后一个语音段
        if len(current_segment) >= MIN_VOICE_LENGTH:
            amplified_segment = [min(32767, max(-32768, int(s * AMPLIFY_FACTOR))) for s in current_segment]
            voice_segments.extend(amplified_segment)
        
        return voice_segments
    
    async def _process_speech_interaction(self, request, connection_handler):
        """处理语音交互"""
        try:
            from app.core.device_logger import log_esp32_audio, log_esp32_service
            
            # 记录开始处理语音交互
            log_esp32_service("ASR处理", "开始语音识别", {
                "device_id": request.device_id,
                "session_id": request.session_id,
                "音频帧数": len(request.audio_frames),
                "总音频大小": sum(len(frame.data) for frame in request.audio_frames)
            })
            
            # 使用语音交互协调器处理
            response = await self.speech_coordinator.process_speech_interaction(request)
            
            # 记录ASR识别结果
            if response.asr_result:
                if response.asr_result.text:
                    log_esp32_service("ASR识别", "语音识别成功", {
                        "device_id": request.device_id,
                        "session_id": request.session_id,
                        "识别文本": response.asr_result.text,
                        "置信度": getattr(response.asr_result, 'confidence', 'N/A'),
                        "处理时长": getattr(response.asr_result, 'processing_time', 'N/A')
                    })
                else:
                    log_esp32_service("ASR识别", "语音识别无结果", {
                        "device_id": request.device_id,
                        "session_id": request.session_id,
                        "原因": "识别文本为空"
                    })
            else:
                log_esp32_service("ASR识别", "ASR处理失败", {
                    "device_id": request.device_id,
                    "session_id": request.session_id,
                    "错误": "ASR结果为空"
                })
            
            # 记录意图识别结果
            if response.intent_result:
                log_esp32_service("意图识别", "意图分析完成", {
                    "device_id": request.device_id,
                    "session_id": request.session_id,
                    "意图类型": response.intent_result.intent_type.value if response.intent_result.intent_type else "未知",
                    "响应文本": response.intent_result.response_text[:100] + "..." if response.intent_result.response_text and len(response.intent_result.response_text) > 100 else response.intent_result.response_text
                })
            
            if response.result == InteractionResult.SUCCESS:
                # 记录处理成功
                log_esp32_service("语音交互", "处理成功", {
                    "device_id": request.device_id,
                    "session_id": request.session_id,
                    "用户输入": response.asr_result.text if response.asr_result else "无",
                    "AI回复": response.intent_result.response_text[:50] + "..." if response.intent_result and response.intent_result.response_text and len(response.intent_result.response_text) > 50 else (response.intent_result.response_text if response.intent_result else "无")
                })
                
                # 发送TTS音频响应
                if response.tts_result and response.tts_result.audio_data:
                    log_esp32_service("TTS发送", "发送语音回复", {
                        "device_id": request.device_id,
                        "音频大小": len(response.tts_result.audio_data),
                        "格式": "opus"
                    })
                    await connection_handler.send_audio_data(
                        response.tts_result.audio_data,
                        audio_format="opus"
                    )
                
                # 发送文本响应
                if response.intent_result and response.intent_result.response_text:
                    await connection_handler.send_message(json.dumps({
                        "type": "assistant_message",
                        "content": response.intent_result.response_text,
                        "intent": response.intent_result.intent_type.value if response.intent_result.intent_type else None
                    }))
            else:
                # 记录处理失败
                log_esp32_service("语音交互", "处理失败", {
                    "device_id": request.device_id,
                    "session_id": request.session_id,
                    "错误原因": response.error_message or "未知错误",
                    "结果状态": response.result.value if response.result else "未知"
                })
                
                # 发送错误响应
                await connection_handler.send_message(json.dumps({
                    "type": "error",
                    "message": response.error_message or "语音处理失败"
                }))
                
        except Exception as e:
            self.logger.error(f"语音交互处理失败: {e}")
            await connection_handler.send_message(json.dumps({
                "type": "error",
                "message": f"语音交互失败: {str(e)}"
            }))


class TextMessageHandler(MessageHandler):
    """文本消息处理器"""
    
    def __init__(self):
        super().__init__(MessageType.TEXT)
        self.intent_processor = get_esp32_intent_processor("text_handler")
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证文本消息格式"""
        return "content" in data and isinstance(data["content"], str)
    
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理文本消息"""
        try:
            content = context.parsed_data.get("content", "")
            
            self.logger.info(f"收到文本消息: {content[:50]}...")
            
            # 使用意图处理器处理文本
            from app.devices.esp32.services import IntentRequest
            
            intent_request = IntentRequest(
                user_text=content,
                device_id=context.device_id,
                session_id=context.session_id,
                user_id=connection_handler.device_info.client_id or context.device_id
            )
            
            # 处理意图
            intent_response = await self.intent_processor.process_intent(intent_request)
            
            # 构建响应
            response = {
                "type": "assistant_message",
                "content": intent_response.response_text,
                "intent": intent_response.intent_result.primary_intent.value if intent_response.intent_result else None,
                "confidence": intent_response.intent_result.confidence if intent_response.intent_result else 0.0,
                "processing_time": intent_response.total_time
            }
            
            # 如果是危机情况，添加特殊标记
            if (intent_response.intent_result and 
                intent_response.intent_result.risk_level in ["high", "critical"]):
                response["crisis_detected"] = True
                response["risk_level"] = intent_response.intent_result.risk_level
                response["suggested_resources"] = intent_response.intent_result.suggested_resources
            
            return response
            
        except Exception as e:
            self.logger.error(f"处理文本消息失败: {e}")
            return {
                "type": "error",
                "message": f"文本处理失败: {str(e)}"
            }


class ControlMessageHandler(MessageHandler):
    """控制消息处理器"""
    
    def __init__(self):
        super().__init__(MessageType.CONTROL)
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证控制消息格式"""
        return "command" in data
    
    def get_priority(self, data: Dict[str, Any]) -> MessagePriority:
        """控制消息优先级高"""
        command = data.get("command", "")
        if command in ["stop", "abort", "emergency"]:
            return MessagePriority.EMERGENCY
        elif command in ["pause", "resume"]:
            return MessagePriority.URGENT
        else:
            return MessagePriority.HIGH
    
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理控制消息"""
        try:
            command = context.parsed_data.get("command")
            params = context.parsed_data.get("params", {})
            
            self.logger.info(f"收到控制命令: {command}")
            
            # 处理不同的控制命令
            if command == "stop":
                await connection_handler.stop_all_processing()
                return {"type": "control_response", "command": command, "status": "stopped"}
            
            elif command == "pause":
                await connection_handler.pause_processing()
                return {"type": "control_response", "command": command, "status": "paused"}
            
            elif command == "resume":
                await connection_handler.resume_processing()
                return {"type": "control_response", "command": command, "status": "resumed"}
            
            elif command == "status":
                status = await connection_handler.get_status()
                return {"type": "status_response", "status": status}
            
            elif command == "reset":
                await connection_handler.reset_session()
                return {"type": "control_response", "command": command, "status": "reset"}
            
            else:
                return {"type": "error", "message": f"未知控制命令: {command}"}
                
        except Exception as e:
            self.logger.error(f"处理控制消息失败: {e}")
            return {
                "type": "error",
                "message": f"控制命令处理失败: {str(e)}"
            }


class StatusMessageHandler(MessageHandler):
    """状态消息处理器"""
    
    def __init__(self):
        super().__init__(MessageType.STATUS)
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证状态消息格式"""
        return True  # 状态消息格式较简单
    
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理状态消息"""
        try:
            data = context.parsed_data
            
            # 获取设备状态
            device_status = {
                "device_id": context.device_id,
                "session_id": context.session_id,
                "connection_time": connection_handler.device_info.connected_at,
                "last_activity": connection_handler.device_info.last_activity,
                "message_count": len(connection_handler.response_times),
                "avg_response_time": sum(connection_handler.response_times) / len(connection_handler.response_times) if connection_handler.response_times else 0
            }
            
            # 获取服务状态
            service_status = {
                "asr": "available",
                "tts": "available", 
                "intent": "available",
                "memory": "available"
            }
            
            response = {
                "type": "status",
                "device_status": device_status,
                "service_status": service_status,
                "server_time": datetime.now().isoformat()
            }
            
            return response
            
        except Exception as e:
            self.logger.error(f"处理状态消息失败: {e}")
            return {
                "type": "error",
                "message": f"状态查询失败: {str(e)}"
            }


class HeartbeatMessageHandler(MessageHandler):
    """心跳消息处理器"""
    
    def __init__(self):
        super().__init__(MessageType.HEARTBEAT)
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证心跳消息格式"""
        return True  # 心跳消息格式简单，只需要type字段
    
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理心跳消息"""
        try:
            # 更新设备活动时间
            connection_handler.device_info.last_activity = time.time()
            
            # 返回心跳响应
            response = {
                "type": "heartbeat",
                "timestamp": time.time(),
                "server_time": datetime.now().isoformat(),
                "status": "alive"
            }
            
            self.logger.debug(f"处理心跳消息: {context.device_id}")
            return response
            
        except Exception as e:
            self.logger.error(f"处理心跳消息失败: {e}")
            return {
                "type": "error",
                "message": f"心跳处理失败: {str(e)}"
            }


class ListenMessageHandler(MessageHandler):
    """监听控制消息处理器"""
    
    def __init__(self):
        super().__init__(MessageType.LISTEN)
    
    def validate(self, data: Dict[str, Any]) -> bool:
        return "state" in data
    
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理监听控制消息"""
        state = context.parsed_data.get("state")
        self.logger.info(f"收到监听控制消息: state={state}")
        
        # 简单确认响应
        return {
            "type": "status",
            "status": "listening_state_updated",
            "state": state,
            "message": f"监听状态已更新为: {state}"
        }


class AbortMessageHandler(MessageHandler):
    """中止消息处理器"""
    
    def __init__(self):
        super().__init__(MessageType.ABORT)
    
    def validate(self, data: Dict[str, Any]) -> bool:
        return True
    
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理中止消息"""
        reason = context.parsed_data.get("reason", "unknown")
        self.logger.info(f"收到中止消息: reason={reason}")
        
        # 简单确认响应
        return {
            "type": "status",
            "status": "aborted",
            "reason": reason,
            "message": "操作已中止"
        }


class McpMessageHandler(MessageHandler):
    """MCP消息处理器"""
    
    def __init__(self):
        super().__init__(MessageType.MCP)
    
    def validate(self, data: Dict[str, Any]) -> bool:
        return "payload" in data
    
    async def handle(self, context: MessageContext, connection_handler) -> Optional[Dict[str, Any]]:
        """处理MCP消息"""
        payload = context.parsed_data.get("payload")
        self.logger.info(f"收到MCP消息: payload={payload}")
        
        # 简单确认响应
        return {
            "type": "status",
            "status": "mcp_received",
            "message": "MCP消息已接收"
        }


class ESP32MessageRouter:
    """ESP32消息路由器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.handlers: Dict[MessageType, MessageHandler] = {}
        self.message_queue = asyncio.Queue(maxsize=1000)
        self.processing_tasks: Dict[str, asyncio.Task] = {}
        self.streaming_buffers: Dict[str, Dict[str, Any]] = {}
        
        # 注册默认处理器
        self._register_default_handlers()
        
        # 启动消息处理任务
        self.processing_task = None
        
        self.logger.info("ESP32消息路由器初始化完成")
    
    def _register_default_handlers(self):
        """注册默认消息处理器"""
        handlers = [
            HelloMessageHandler(),
            AudioMessageHandler(),
            TextMessageHandler(),
            ControlMessageHandler(),
            StatusMessageHandler(),
            HeartbeatMessageHandler()
        ]
        
        # 尝试注册ESP32特有的处理器，如果失败则跳过
        try:
            handlers.extend([
                ListenMessageHandler(),
                AbortMessageHandler(),
                McpMessageHandler()
            ])
        except NameError as e:
            self.logger.warning(f"ESP32特有处理器注册失败: {e}")
        
        for handler in handlers:
            self.register_handler(handler)
    
    def register_handler(self, handler: MessageHandler):
        """注册消息处理器"""
        self.handlers[handler.message_type] = handler
        self.logger.info(f"注册消息处理器: {handler.message_type.value}")
    
    def get_handler(self, message_type: MessageType) -> Optional[MessageHandler]:
        """获取消息处理器"""
        return self.handlers.get(message_type)
    
    def get_supported_types(self) -> List[str]:
        """获取支持的消息类型"""
        return [msg_type.value for msg_type in self.handlers.keys()]
    
    def clear_device_buffer(self, device_id: str):
        """清空指定设备的流式ASR缓冲区"""
        def _reset_buffer(buffer_info: dict):
            buffer_info["opus_buffer"].clear()
            buffer_info["frame_count"] = 0
            buffer_info["frame_sizes"].clear()
            buffer_info["partial_results"].clear()
            buffer_info["last_partial_text"] = ""
            buffer_info["partial_first_seen"] = 0.0
            buffer_info["partial_repeat_count"] = 0
            buffer_info["last_partial_time"] = 0.0
            buffer_info["last_promoted_text"] = ""
            buffer_info["last_completed_text"] = ""
            buffer_info["last_completed_time"] = 0.0
            buffer_info["is_speaking"] = False
            buffer_info["silence_frames"] = 0
            buffer_info["last_asr_time"] = 0
            buffer_info["last_trigger_time"] = time.time()

        cleared = False

        audio_handler = self.handlers.get(MessageType.AUDIO)
        if isinstance(audio_handler, AudioMessageHandler):
            buffer_info = audio_handler.streaming_buffers.get(device_id)
            if buffer_info:
                _reset_buffer(buffer_info)
                cleared = True
                self.logger.info(f"🧹 已清空设备 {device_id} 的 ESP32AudioHandler 缓冲区")

        if device_id in self.streaming_buffers:
            _reset_buffer(self.streaming_buffers[device_id])
            cleared = True
            self.logger.info(f"🧹 已清空设备 {device_id} 的 MessageRouter 缓冲区")

        if not cleared:
            self.logger.debug(f"设备 {device_id} 没有可清空的流式ASR缓冲区")

    def _get_or_create_streaming_buffer(self, device_id: str) -> dict:
        """获取或初始化设备的流式缓冲区"""
        if device_id not in self.streaming_buffers:
            self.streaming_buffers[device_id] = {
                "opus_buffer": bytearray(),
                "frame_count": 0,
                "frame_sizes": [],
                "last_asr_time": 0,
                "last_trigger_time": time.time(),
                "partial_results": [],
                "is_speaking": False,
                "silence_frames": 0
            }
        return self.streaming_buffers[device_id]
    
    async def route_message(self, raw_data: Any, connection_handler) -> Optional[Dict[str, Any]]:
        """路由消息"""
        try:
            # 解析消息
            message_context = await self._parse_message(raw_data, connection_handler)
            if not message_context:
                return {"type": "error", "message": "消息解析失败"}
            
            # 获取处理器
            handler = self.get_handler(message_context.message_type)
            if not handler:
                self.logger.warning(f"❌ [消息路由] 未找到处理器: {message_context.message_type.value}")
                self.logger.debug(f"   可用处理器: {list(self.handlers.keys())}")
                return {"type": "error", "message": f"不支持的消息类型: {message_context.message_type.value}"}
            
            self.logger.info(f"✅ [消息路由] 找到处理器: {message_context.message_type.value} -> {handler.__class__.__name__}")
            
            # 验证消息
            if not handler.validate(message_context.parsed_data):
                return {"type": "error", "message": "消息格式验证失败"}
            
            # 处理消息
            start_time = time.time()
            result = await handler.handle(message_context, connection_handler)
            processing_time = time.time() - start_time
            
            # 记录处理时间
            if hasattr(connection_handler, 'response_times'):
                connection_handler.response_times.append(processing_time)
            
            self.logger.debug(
                f"消息处理完成: {message_context.message_type.value}, "
                f"耗时: {processing_time*1000:.1f}ms"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"消息路由失败: {e}", exc_info=True)
            return {"type": "error", "message": f"消息处理失败: {str(e)}"}
    
    async def _parse_message(self, raw_data: Any, connection_handler) -> Optional[MessageContext]:
        """解析消息"""
        try:
            import uuid
            
            message_id = str(uuid.uuid4())
            timestamp = time.time()
            device_id = connection_handler.device_info.device_id
            session_id = connection_handler.session_id
            
            # 解析不同类型的数据
            if isinstance(raw_data, bytes):
                self.logger.info(f"🔍 [消息路由] 收到二进制数据: {len(raw_data)} 字节, 前16字节: {raw_data[:16].hex()}")
                
                # 二进制数据 - 使用二进制协议处理器解析
                from .protocol.binary_protocol import get_binary_protocol_handler
                binary_handler = get_binary_protocol_handler()
                
                # 解析二进制协议
                protocol_data = binary_handler.parse_binary_message(raw_data)
                if protocol_data:
                    # 成功解析二进制协议
                    message_type = MessageType.AUDIO if protocol_data.get("type") == "audio" else MessageType.UNKNOWN
                    parsed_data = {
                        "audio_data": protocol_data.get("payload", b''),
                        "protocol_version": protocol_data.get("version", 1),
                        "timestamp": protocol_data.get("timestamp", 0),
                        "payload_size": protocol_data.get("payload_size", 0)
                    }
                    self.logger.info(f"✅ [消息路由] 二进制协议解析成功: v{protocol_data.get('version')}, "
                                   f"type={protocol_data.get('type')}, "
                                   f"payload={len(protocol_data.get('payload', b''))} 字节")
                else:
                    # 解析失败，当作原始音频数据处理
                    message_type = MessageType.AUDIO
                    parsed_data = {"audio_data": raw_data}
                    self.logger.warning(f"❌ [消息路由] 二进制协议解析失败，当作原始音频处理: {len(raw_data)} 字节")
                
            elif isinstance(raw_data, str):
                self.logger.info(f"🔍 收到文本消息: {raw_data[:200]}...")
                try:
                    # JSON字符串
                    parsed_data = json.loads(raw_data)
                    message_type_str = parsed_data.get("type", "unknown")
                    message_type = MessageType(message_type_str) if message_type_str in [t.value for t in MessageType] else MessageType.UNKNOWN
                    self.logger.info(f"📝 JSON消息解析: type='{message_type_str}' -> {message_type.value}")
                    if message_type == MessageType.UNKNOWN:
                        self.logger.warning(f"❌ 未知消息类型: '{message_type_str}', 支持的类型: {[t.value for t in MessageType]}")
                except json.JSONDecodeError:
                    # 纯文本
                    message_type = MessageType.TEXT
                    parsed_data = {"content": raw_data}
                    
            elif isinstance(raw_data, dict):
                # 字典数据
                parsed_data = raw_data
                message_type_str = parsed_data.get("type", "unknown")
                message_type = MessageType(message_type_str) if message_type_str in [t.value for t in MessageType] else MessageType.UNKNOWN
                
            else:
                self.logger.warning(f"❌ 未知数据类型: {type(raw_data)}, 数据: {repr(raw_data)[:100]}")
                return None
            
            # 获取优先级
            handler = self.get_handler(message_type)
            priority = handler.get_priority(parsed_data) if handler else MessagePriority.NORMAL
            
            # 创建消息上下文
            context = MessageContext(
                message_id=message_id,
                message_type=message_type,
                priority=priority,
                timestamp=timestamp,
                device_id=device_id,
                session_id=session_id,
                raw_data=raw_data,
                parsed_data=parsed_data,
                metadata={}
            )
            
            return context
            
        except Exception as e:
            self.logger.error(f"消息解析失败: {e}")
            return None
    
    def get_router_stats(self) -> Dict[str, Any]:
        """获取路由器统计信息"""
        return {
            "registered_handlers": len(self.handlers),
            "supported_types": self.get_supported_types(),
            "queue_size": self.message_queue.qsize(),
            "active_tasks": len(self.processing_tasks)
        }


# 全局实例
_esp32_message_router: Optional[ESP32MessageRouter] = None


def get_esp32_message_router() -> ESP32MessageRouter:
    """获取ESP32消息路由器实例"""
    global _esp32_message_router
    if _esp32_message_router is None:
        _esp32_message_router = ESP32MessageRouter()
    return _esp32_message_router


def reset_esp32_message_router():
    """重置ESP32消息路由器实例"""
    global _esp32_message_router
    _esp32_message_router = None
