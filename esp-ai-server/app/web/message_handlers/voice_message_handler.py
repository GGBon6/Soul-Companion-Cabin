"""
语音消息处理器
Voice Message Handler
处理用户发送的语音消息
"""

import base64
from typing import Dict, Any
import websockets

from app.core import logger
from app.core.exceptions import ASRError, TTSError
from app.shared.services import acquire_asr_service  # 使用连接池
from app.shared.services.tts_service import get_character_voice
from .base_handler import BaseMessageHandler
from .memory_handler import MemoryHandler


class VoiceMessageHandler(BaseMessageHandler):
    """语音消息处理器"""
    
    def __init__(self, websocket_handler):
        super().__init__(websocket_handler)
        self.memory_handler = MemoryHandler(websocket_handler)
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理语音消息
        
        Args:
            websocket: WebSocket连接
            data: 消息数据
        """
        try:
            audio_data = data.get("audio", "")
            if not audio_data:
                return
            
            logger.info("收到语音消息，开始处理...")
            
            # 解码音频数据
            try:
                audio_bytes = base64.b64decode(audio_data)
            except Exception as e:
                logger.error(f"音频数据解码失败: {e}")
                await self.send_message(websocket, "error", "音频数据格式错误")
                return
            
            # 语音识别
            text = await self._transcribe_audio(websocket, audio_bytes)
            if not text:
                return
            
            # 获取用户信息
            user_id = self.get_user_id(websocket)
            is_tree_hole_mode = self.is_tree_hole_mode(user_id)
            
            # 添加用户消息到历史（标记为语音输入）
            self.add_message(websocket, "user", text, metadata={
                "is_voice_input": True,
                "audio_base64": audio_data
            }, skip_save=is_tree_hole_mode)
            
            # 处理记忆召回
            await self.memory_handler.process_memory_recall(websocket, user_id, text)
            
            # 添加相关知识
            await self.memory_handler.add_knowledge_context(websocket, text)
            
            # 确保对话已初始化
            self.ensure_conversation_initialized(websocket)
            
            # 添加时间上下文
            temp_conversation = self.add_time_context(self.get_conversations(websocket))
            
            # 调用LLM生成回复
            response = await self.llm_service.chat_async(
                temp_conversation,
                temperature=0.85
            )
            
            logger.info(f"AI回复: {response}")
            
            # 生成语音回复
            audio_base64 = await self._generate_voice_response(websocket, response, user_id)
            
            # 保存助手回复
            metadata = {"is_voice_response": True}
            if audio_base64:
                metadata["audio_base64"] = audio_base64
            self.add_message(websocket, "assistant", response, metadata=metadata, skip_save=is_tree_hole_mode)
            
            # 处理记忆提取
            await self.memory_handler.process_memory_extraction(websocket, user_id, text)
            
            # 更新亲密度（语音对话额外加分）
            await self.update_intimacy(user_id, text, response, is_voice=True)
            
        except Exception as e:
            logger.error(f"处理语音消息失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "处理语音消息失败")
    
    async def _transcribe_audio(self, websocket: websockets.WebSocketServerProtocol, 
                              audio_bytes: bytes) -> str:
        """
        语音识别（使用连接池）
        
        Args:
            websocket: WebSocket连接
            audio_bytes: 音频数据
            
        Returns:
            str: 识别的文本，失败返回空字符串
        """
        try:
            # 获取用户ID作为client_id
            user_id = self.get_user_id(websocket)
            
            # 从连接池获取ASR服务
            async with acquire_asr_service(
                client_type="web",
                client_id=user_id,
                timeout=30.0
            ) as asr_service:
                # 使用同步方法（ASR服务内部会处理）
                text = asr_service.transcribe(audio_bytes, format="webm")
                
                if not text or not text.strip():
                    await self.send_message(websocket, "error", "语音识别失败，请重试")
                    return ""
                
                logger.info(f"✅ 语音识别成功 (用户: {user_id}): {text}")
                await self.send_message(websocket, "asr_result", text)
                return text
            
        except TimeoutError:
            logger.error("ASR连接池获取超时")
            await self.send_message(websocket, "error", "语音识别服务繁忙，请稍后重试")
            return ""
        except ASRError as e:
            logger.error(f"ASR处理失败: {e}")
            await self.send_message(websocket, "error", "语音识别服务不可用")
            return ""
        except Exception as e:
            logger.error(f"语音识别异常: {e}", exc_info=True)
            await self.send_message(websocket, "error", "语音识别失败")
            return ""
    
    async def _generate_voice_response(self, websocket: websockets.WebSocketServerProtocol, 
                                     response: str, user_id: str) -> str:
        """
        生成语音回复
        
        Args:
            websocket: WebSocket连接
            response: AI回复文本
            user_id: 用户ID
            
        Returns:
            str: base64编码的音频数据，失败返回空字符串
        """
        try:
            # 获取用户当前角色的声音
            profile = self.profile_service.get_profile(user_id)
            character_voice = get_character_voice(profile.current_character)
            logger.info(f"🎤 使用角色 {profile.current_character} 的声音: {character_voice}")
            
            audio_data = await self.tts_service.synthesize_async(response, voice=character_voice)
            if audio_data:
                audio_base64 = base64.b64encode(audio_data).decode()
                await self.send_message(websocket, "audio", {
                    "text": response,
                    "audio": audio_base64
                })
                return audio_base64
            else:
                # 如果语音合成失败，至少发送文本
                await self.send_message(websocket, "assistant_message", response)
                return ""
                
        except TTSError as e:
            logger.error(f"TTS合成失败: {e}")
            await self.send_message(websocket, "assistant_message", response)
            return ""
