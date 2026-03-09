"""
文本消息处理器
Text Message Handler
处理用户发送的文本消息
"""

import base64
import random
from typing import Dict, Any
import websockets

from app.core import logger
from app.core.exceptions import LLMError, TTSError
from app.shared.services.tts_service import get_character_voice
from .base_handler import BaseMessageHandler
from .memory_handler import MemoryHandler


class TextMessageHandler(BaseMessageHandler):
    """文本消息处理器"""
    
    def __init__(self, websocket_handler):
        super().__init__(websocket_handler)
        self.memory_handler = MemoryHandler(websocket_handler)
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理文本消息
        
        Args:
            websocket: WebSocket连接
            data: 消息数据
        """
        call_id = random.randint(1000, 9999)
        logger.info(f"📨 [handle_text_message #{call_id}] 开始处理")
        
        try:
            content = data.get("content", "").strip()
            if not content:
                return
            
            logger.info(f"收到文本消息: {content}")
            
            # 获取用户信息
            user_id = self.get_user_id(websocket)
            is_tree_hole_mode = self.is_tree_hole_mode(user_id)
            
            # 添加用户消息到历史
            self.add_message(websocket, "user", content, skip_save=is_tree_hole_mode)
            
            # 处理记忆召回
            await self.memory_handler.process_memory_recall(websocket, user_id, content)
            
            # 添加相关知识
            await self.memory_handler.add_knowledge_context(websocket, content)
            
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
            
            # 处理语音回复
            enable_voice = data.get("enable_voice", False)
            logger.info(f"🔊 [#{call_id}] enable_voice = {enable_voice}")
            
            if enable_voice:
                await self._handle_voice_response(websocket, response, user_id, call_id, is_tree_hole_mode)
            else:
                # 纯文本回复
                await self.send_message(websocket, "assistant_message", response)
                self.add_message(websocket, "assistant", response, skip_save=is_tree_hole_mode)
            
            # 处理记忆提取（异步执行）
            await self.memory_handler.process_memory_extraction(websocket, user_id, content)
            
            # 更新亲密度
            await self.update_intimacy(user_id, content, response)
            
            logger.info(f"✅ [handle_text_message #{call_id}] 处理完成")
            
        except LLMError as e:
            logger.error(f"❌ [handle_text_message #{call_id}] LLM处理失败: {e}")
            await self.send_message(websocket, "error", "AI服务暂时不可用")
        except Exception as e:
            logger.error(f"❌ [handle_text_message #{call_id}] 处理文本消息失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "处理消息失败")
    
    async def _handle_voice_response(self, websocket: websockets.WebSocketServerProtocol, 
                                   response: str, user_id: str, call_id: int, 
                                   is_tree_hole_mode: bool):
        """
        处理语音回复
        
        Args:
            websocket: WebSocket连接
            response: AI回复文本
            user_id: 用户ID
            call_id: 调用ID
            is_tree_hole_mode: 是否为树洞模式
        """
        # 先发送文本消息
        await self.send_message(websocket, "assistant_message", response)
        
        # 生成语音回复
        audio_base64 = None
        try:
            # 获取用户当前角色的声音
            profile = self.profile_service.get_profile(user_id)
            character_voice = get_character_voice(profile.current_character)
            
            # 清理TTS文本，移除表情符号
            clean_text = self._clean_text_for_tts(response)
            
            logger.info(f"🎵 [#{call_id}] TTS原始文本:\n{repr(response)}")
            logger.info(f"🎵 [#{call_id}] TTS清理后文本:\n{repr(clean_text)}")
            logger.info(f"🎵 [#{call_id}] TTS文本长度: {len(clean_text)} 字符")
            logger.info(f"🎤 [#{call_id}] 使用角色 {profile.current_character} 的声音: {character_voice}")
            
            audio_data = await self.tts_service.synthesize_async(clean_text, voice=character_voice)
            if audio_data:
                audio_base64 = base64.b64encode(audio_data).decode()
                logger.info(f"✅ [#{call_id}] TTS合成完成，发送audio消息")
                await self.send_message(websocket, "audio", {
                    "text": response,
                    "audio": audio_base64
                })
        except TTSError as e:
            logger.error(f"❌ [#{call_id}] TTS合成失败: {e}")
        
        # 保存助手回复（包含音频数据的metadata）
        metadata = {"is_voice_response": True}
        if audio_base64:
            metadata["audio_base64"] = audio_base64
        self.add_message(websocket, "assistant", response, metadata=metadata, skip_save=is_tree_hole_mode)
    
    def _clean_text_for_tts(self, text: str) -> str:
        """
        清理文本用于TTS合成，移除表情符号和特殊字符
        
        Args:
            text: 原始文本
            
        Returns:
            str: 清理后的文本
        """
        import re
        
        # 更精确的表情符号正则表达式
        emoji_pattern = re.compile(
            r'[\U0001F600-\U0001F64F]|'  # emoticons
            r'[\U0001F300-\U0001F5FF]|'  # symbols & pictographs
            r'[\U0001F680-\U0001F6FF]|'  # transport & map symbols
            r'[\U0001F1E0-\U0001F1FF]|'  # flags (iOS)
            r'[\U00002702-\U000027B0]|'  # dingbats
            r'[\U0001F900-\U0001F9FF]|'  # supplemental symbols
            r'[\U0001FA70-\U0001FAFF]',   # symbols and pictographs extended-a
            flags=re.UNICODE
        )
        
        # 移除表情符号
        clean_text = emoji_pattern.sub('', text)
        
        # 移除多余的空格和换行符
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # 如果清理后文本为空，返回原文本（避免完全无声）
        if not clean_text.strip():
            return text
            
        return clean_text
