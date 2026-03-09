"""
对话API模块
Chat API Module
提供对话相关的REST API接口
"""

from aiohttp import web
from app.shared.services import get_llm_service, get_chat_history_service
from app.shared.agents import get_memory_agent
from app.core import logger


class ChatAPI:
    """对话API处理器"""
    
    def __init__(self):
        """初始化对话API"""
        self.llm_service = get_llm_service()
        self.chat_history_service = get_chat_history_service()
        self.memory_agent = get_memory_agent()
        logger.info("对话API初始化完成")
    
    async def chat(self, request: web.Request) -> web.Response:
        """
        对话接口
        POST /api/chat
        """
        try:
            data = await request.json()
            user_id = data.get('user_id')
            message = data.get('message')
            
            if not user_id or not message:
                return web.json_response(
                    {'error': '缺少必要参数'}, 
                    status=400
                )
            
            # 调用LLM服务生成回复
            response = await self.llm_service.chat_async([
                {"role": "user", "content": message}
            ])
            
            # 保存对话历史
            await self.chat_history_service.save_message(
                user_id=user_id,
                session_id=f"api_{user_id}",
                role="user",
                content=message,
                message_type="text"
            )
            
            await self.chat_history_service.save_message(
                user_id=user_id,
                session_id=f"api_{user_id}",
                role="assistant",
                content=response,
                message_type="text"
            )
            
            return web.json_response({
                'response': response,
                'user_id': user_id
            })
            
        except Exception as e:
            logger.error(f"对话API处理失败: {e}")
            return web.json_response(
                {'error': '服务器内部错误'}, 
                status=500
            )
    
    async def get_history(self, request: web.Request) -> web.Response:
        """
        获取对话历史
        GET /api/chat/history?user_id=xxx&limit=20
        """
        try:
            user_id = request.query.get('user_id')
            limit = int(request.query.get('limit', 20))
            
            if not user_id:
                return web.json_response(
                    {'error': '缺少user_id参数'}, 
                    status=400
                )
            
            # 获取对话历史
            messages = await self.chat_history_service.get_messages(
                user_id=user_id,
                session_id=f"api_{user_id}",
                limit=limit
            )
            
            return web.json_response({
                'messages': messages,
                'user_id': user_id,
                'count': len(messages)
            })
            
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return web.json_response(
                {'error': '服务器内部错误'}, 
                status=500
            )


# 创建全局实例
_chat_api = None

def get_chat_api() -> ChatAPI:
    """获取对话API单例"""
    global _chat_api
    if _chat_api is None:
        _chat_api = ChatAPI()
    return _chat_api
