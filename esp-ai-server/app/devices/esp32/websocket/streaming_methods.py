"""
ESP32流式交互辅助方法
"""
import time
import asyncio
from typing import Dict, Any


class StreamingMethods:
    """流式交互辅助方法类"""
    
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
            
            log_esp32_audio(context.device_id, "✅ 流式TTS完成", {
                "session_id": context.session_id,
                "sent_frames": len(frames_to_send)
            })
            
        except Exception as e:
            from app.core.device_logger import log_esp32_error
            log_esp32_error(context.device_id, "流式TTS发送失败", f"流式TTS发送异常: {e}", {
                "session_id": context.session_id,
                "error_type": type(e).__name__
            })
