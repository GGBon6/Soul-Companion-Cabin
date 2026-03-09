"""
用户API模块
User API Module
提供用户相关的REST API接口
"""

from aiohttp import web
from app.shared.services import AuthService
from app.shared.agents import get_memory_agent
from app.core import logger


class UserAPI:
    """用户API处理器"""
    
    def __init__(self):
        """初始化用户API"""
        self.auth_service = AuthService()
        self.memory_agent = get_memory_agent()
        logger.info("用户API初始化完成")
    
    async def get_profile(self, request: web.Request) -> web.Response:
        """
        获取用户档案
        GET /api/user/profile?user_id=xxx
        """
        try:
            user_id = request.query.get('user_id')
            
            if not user_id:
                return web.json_response(
                    {'error': '缺少user_id参数'}, 
                    status=400
                )
            
            # 从memory_agent获取用户档案
            profile = self.memory_agent.memory.pr_store.get_profile(user_id)
            
            return web.json_response({
                'user_id': user_id,
                'profile': profile
            })
            
        except Exception as e:
            logger.error(f"获取用户档案失败: {e}")
            return web.json_response(
                {'error': '服务器内部错误'}, 
                status=500
            )
    
    async def update_profile(self, request: web.Request) -> web.Response:
        """
        更新用户档案
        POST /api/user/profile
        """
        try:
            data = await request.json()
            user_id = data.get('user_id')
            profile_data = data.get('profile', {})
            
            if not user_id:
                return web.json_response(
                    {'error': '缺少user_id参数'}, 
                    status=400
                )
            
            # 更新用户档案
            self.memory_agent.memory.pr_store.update_profile(user_id, profile_data)
            
            return web.json_response({
                'user_id': user_id,
                'message': '档案更新成功'
            })
            
        except Exception as e:
            logger.error(f"更新用户档案失败: {e}")
            return web.json_response(
                {'error': '服务器内部错误'}, 
                status=500
            )
    
    async def get_mood(self, request: web.Request) -> web.Response:
        """
        获取用户情绪
        GET /api/user/mood?user_id=xxx
        """
        try:
            user_id = request.query.get('user_id')
            
            if not user_id:
                return web.json_response(
                    {'error': '缺少user_id参数'}, 
                    status=400
                )
            
            # 从memory_agent获取情绪数据
            affects = self.memory_agent.memory.af_store.get_recent_affects(user_id, limit=10)
            
            return web.json_response({
                'user_id': user_id,
                'affects': affects
            })
            
        except Exception as e:
            logger.error(f"获取用户情绪失败: {e}")
            return web.json_response(
                {'error': '服务器内部错误'}, 
                status=500
            )


# 创建全局实例
_user_api = None

def get_user_api() -> UserAPI:
    """获取用户API单例"""
    global _user_api
    if _user_api is None:
        _user_api = UserAPI()
    return _user_api
