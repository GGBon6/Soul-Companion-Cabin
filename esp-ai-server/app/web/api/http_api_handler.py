"""
HTTP REST API处理器
HTTP REST API Handler
提供HTTP接口用于AI服务调用
"""

import json
import asyncio
from typing import Optional
from aiohttp import web
from app.core import logger, settings
from app.shared.services.llm_service import get_llm_service
from app.shared.services.tts_service import get_tts_service
# ASR服务改用连接池
# from app.shared.services.asr_service import get_asr_service


class HTTPAPIHandler:
    """HTTP API处理器"""
    
    def __init__(self):
        """初始化HTTP API处理器"""
        self.llm_service = get_llm_service()
        self.tts_service = get_tts_service()
        # ASR服务改用连接池，不再持有单例
        # self.asr_service = get_asr_service()
        logger.info("HTTP API处理器已初始化")
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """
        健康检查端点
        GET /api/health
        """
        return web.json_response({
            "status": "healthy",
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
            "supported_clients": settings.SUPPORTED_CLIENTS,
        })
    
    async def handle_info(self, request: web.Request) -> web.Response:
        """
        服务信息端点
        GET /api/info
        """
        return web.json_response({
            "service_name": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
            "description": settings.DESCRIPTION,
            "supported_clients": settings.SUPPORTED_CLIENTS,
            "features": {
                "websocket": settings.ENABLE_WEBSOCKET,
                "http_api": settings.ENABLE_HTTP_API,
                "ota": settings.ENABLE_OTA,
            },
            "models": {
                "llm": settings.LLM_MODEL,
                "asr": settings.ASR_MODEL,
                "tts": settings.TTS_MODEL,
            }
        })
    
    async def handle_chat(self, request: web.Request) -> web.Response:
        """
        文本对话端点
        POST /api/chat
        Body: {"message": "你好", "role": "小智", "user_id": "optional"}
        """
        try:
            # 解析请求体
            data = await request.json()
            message = data.get('message', '')
            role = data.get('role', '小智')
            user_id = data.get('user_id', 'api_user')
            
            if not message:
                return web.json_response({
                    "error": "消息内容不能为空"
                }, status=400)
            
            # 调用LLM服务
            logger.info(f"API请求 - 用户: {user_id}, 角色: {role}, 消息: {message}")
            
            # 这里需要根据实际的LLM服务接口调整
            # 简化版本，实际使用时需要完整的上下文管理
            response_text = f"收到消息: {message}"  # 占位符
            
            return web.json_response({
                "success": True,
                "response": response_text,
                "role": role,
                "user_id": user_id,
            })
            
        except json.JSONDecodeError:
            return web.json_response({
                "error": "无效的JSON格式"
            }, status=400)
        except Exception as e:
            logger.error(f"对话处理失败: {e}", exc_info=True)
            return web.json_response({
                "error": f"处理失败: {str(e)}"
            }, status=500)
    
    async def handle_tts(self, request: web.Request) -> web.Response:
        """
        文字转语音端点
        POST /api/tts
        Body: {"text": "你好", "voice": "optional"}
        """
        try:
            # 解析请求体
            data = await request.json()
            text = data.get('text', '')
            voice = data.get('voice', settings.TTS_VOICE)
            
            if not text:
                return web.json_response({
                    "error": "文本内容不能为空"
                }, status=400)
            
            logger.info(f"TTS请求 - 文本: {text[:50]}..., 音色: {voice}")
            
            # 调用TTS服务
            audio_data = await self.tts_service.synthesize(
                text=text,
                voice=voice
            )
            
            if audio_data:
                # 返回音频数据
                return web.Response(
                    body=audio_data,
                    content_type='audio/wav',
                    headers={
                        'Content-Disposition': 'attachment; filename="speech.wav"'
                    }
                )
            else:
                return web.json_response({
                    "error": "语音合成失败"
                }, status=500)
                
        except json.JSONDecodeError:
            return web.json_response({
                "error": "无效的JSON格式"
            }, status=400)
        except Exception as e:
            logger.error(f"TTS处理失败: {e}", exc_info=True)
            return web.json_response({
                "error": f"处理失败: {str(e)}"
            }, status=500)
    
    async def handle_asr(self, request: web.Request) -> web.Response:
        """
        语音识别端点
        POST /api/asr
        Body: multipart/form-data with 'audio' field
        """
        try:
            # 读取上传的音频文件
            reader = await request.multipart()
            audio_data = None
            
            async for field in reader:
                if field.name == 'audio':
                    audio_data = await field.read()
                    break
            
            if not audio_data:
                return web.json_response({
                    "error": "未找到音频数据"
                }, status=400)
            
            logger.info(f"ASR请求 - 音频大小: {len(audio_data)} bytes")
            
            # 调用ASR服务
            # 注意：这里需要根据实际的ASR服务接口调整
            text = "识别结果占位符"  # 占位符
            
            return web.json_response({
                "success": True,
                "text": text,
            })
            
        except Exception as e:
            logger.error(f"ASR处理失败: {e}", exc_info=True)
            return web.json_response({
                "error": f"处理失败: {str(e)}"
            }, status=500)
    
    def setup_routes(self, app: web.Application):
        """
        设置路由
        
        Args:
            app: aiohttp应用实例
        """
        # 健康检查
        app.router.add_route('GET', '/api/health', self.handle_health)
        
        # 服务信息
        app.router.add_route('GET', '/api/info', self.handle_info)
        
        # AI功能端点
        app.router.add_route('POST', '/api/chat', self.handle_chat)
        app.router.add_route('POST', '/api/tts', self.handle_tts)
        app.router.add_route('POST', '/api/asr', self.handle_asr)
        
        logger.info("HTTP API路由已配置")


# 全局实例
_http_api_handler: Optional[HTTPAPIHandler] = None


def get_http_api_handler() -> HTTPAPIHandler:
    """获取HTTP API处理器单例"""
    global _http_api_handler
    if _http_api_handler is None:
        _http_api_handler = HTTPAPIHandler()
    return _http_api_handler
