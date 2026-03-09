"""
WebSocket消息处理器
WebSocket Message Handlers
处理WebSocket消息的具体逻辑
"""

from app.shared.services import get_llm_service, get_tts_service, acquire_asr_service
from app.shared.agents import get_memory_agent
from app.core import logger


class MessageHandlers:
    """消息处理器集合（已废弃，建议使用message_handlers模块）"""
    
    def __init__(self):
        """初始化消息处理器"""
        self.llm_service = get_llm_service()
        # ASR服务改用连接池，不再持有单例
        # self.asr_service = get_asr_service()  # 已移除
        self.tts_service = get_tts_service()
        self.memory_agent = get_memory_agent()


class WebSocketMessageHandler:
    """WebSocket消息处理器基类"""
    
    def __init__(self):
        """初始化消息处理器"""
        self.llm_service = get_llm_service()
        self.tts_service = get_tts_service()
        self.memory_agent = get_memory_agent()


class TextMessageHandler(WebSocketMessageHandler):
    """文本消息处理器"""
    
    async def handle(self, websocket, data: dict, user_id: str):
        """处理文本消息"""
        try:
            message = data.get('message', '')
            if not message:
                await websocket.send_json({
                    'type': 'error',
                    'message': '消息内容不能为空'
                })
                return
            
            logger.info(f"收到文本消息: {user_id} -> {message}")
            
            # 调用LLM生成回复
            response = await self.llm_service.chat_async([
                {"role": "user", "content": message}
            ])
            
            # 发送回复
            await websocket.send_json({
                'type': 'text_response',
                'message': response,
                'user_id': user_id
            })
            
            logger.info(f"发送文本回复: {user_id} -> {response}")
            
        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            await websocket.send_json({
                'type': 'error',
                'message': '处理消息失败'
            })


class VoiceMessageHandler(WebSocketMessageHandler):
    """语音消息处理器"""
    
    async def handle(self, websocket, data: dict, user_id: str):
        """处理语音消息"""
        try:
            audio_data = data.get('audio_data')
            if not audio_data:
                await websocket.send_json({
                    'type': 'error',
                    'message': '音频数据不能为空'
                })
                return
            
            logger.info(f"收到语音消息: {user_id}")
            
            # 解码base64音频数据
            import base64
            audio_bytes = base64.b64decode(audio_data)
            
            # 使用连接池获取ASR服务
            try:
                async with acquire_asr_service(
                    client_type="web",
                    client_id=user_id,
                    timeout=30.0
                ) as asr_service:
                    text = asr_service.transcribe(audio_bytes, format="webm")
            except TimeoutError:
                await websocket.send_json({
                    'type': 'error',
                    'message': '语音识别服务繁忙，请稍后重试'
                })
                return
            except Exception as e:
                logger.error(f"ASR识别失败: {e}")
                await websocket.send_json({
                    'type': 'error',
                    'message': '语音识别失败'
                })
                return
            
            if not text:
                await websocket.send_json({
                    'type': 'error',
                    'message': '语音识别失败'
                })
                return
            
            logger.info(f"语音识别结果: {user_id} -> {text}")
            
            # 发送识别结果
            await websocket.send_json({
                'type': 'stt_result',
                'text': text,
                'user_id': user_id
            })
            
            # 调用LLM生成回复
            response = await self.llm_service.chat_async([
                {"role": "user", "content": text}
            ])
            
            # 调用TTS生成语音
            tts_audio = await self.tts_service.synthesize_async(response)
            if tts_audio:
                # 编码为base64
                tts_base64 = base64.b64encode(tts_audio).decode('utf-8')
                
                await websocket.send_json({
                    'type': 'voice_response',
                    'text': response,
                    'audio_data': tts_base64,
                    'user_id': user_id
                })
            else:
                # 如果TTS失败，发送文本回复
                await websocket.send_json({
                    'type': 'text_response',
                    'message': response,
                    'user_id': user_id
                })
            
            logger.info(f"发送语音回复: {user_id} -> {response}")
            
        except Exception as e:
            logger.error(f"处理语音消息失败: {e}")
            await websocket.send_json({
                'type': 'error',
                'message': '处理语音消息失败'
            })


class SystemMessageHandler(WebSocketMessageHandler):
    """系统消息处理器"""
    
    async def handle(self, websocket, data: dict, user_id: str):
        """处理系统消息"""
        try:
            command = data.get('command')
            
            if command == 'ping':
                await websocket.send_json({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                })
            elif command == 'get_status':
                await websocket.send_json({
                    'type': 'status',
                    'user_id': user_id,
                    'connected': True
                })
            else:
                await websocket.send_json({
                    'type': 'error',
                    'message': f'未知系统命令: {command}'
                })
                
        except Exception as e:
            logger.error(f"处理系统消息失败: {e}")
            await websocket.send_json({
                'type': 'error',
                'message': '处理系统消息失败'
            })


# 创建全局实例
_text_handler = None
_voice_handler = None
_system_handler = None

def get_text_handler() -> TextMessageHandler:
    """获取文本消息处理器单例"""
    global _text_handler
    if _text_handler is None:
        _text_handler = TextMessageHandler()
    return _text_handler

def get_voice_handler() -> VoiceMessageHandler:
    """获取语音消息处理器单例"""
    global _voice_handler
    if _voice_handler is None:
        _voice_handler = VoiceMessageHandler()
    return _voice_handler

def get_system_handler() -> SystemMessageHandler:
    """获取系统消息处理器单例"""
    global _system_handler
    if _system_handler is None:
        _system_handler = SystemMessageHandler()
    return _system_handler
