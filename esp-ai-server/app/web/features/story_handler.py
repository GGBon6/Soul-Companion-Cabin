"""
故事处理器
Story Handler
处理睡前故事功能
"""

from typing import Dict, Any
import websockets

from app.core import logger
from app.web.message_handlers.base_handler import BaseMessageHandler
from app.business.story import get_story_service


class StoryHandler(BaseMessageHandler):
    """故事处理器"""
    
    async def handle_get_story_types(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取故事类型选项"""
        try:
            story_service = get_story_service()
            story_types = story_service.get_story_types()
            
            await self.send_message(websocket, "story_types", {
                "types": story_types
            })
            logger.info("发送故事类型选项")
            
        except Exception as e:
            logger.error(f"获取故事类型失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取故事类型失败")
    
    async def handle_get_story_themes(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取故事主题列表"""
        try:
            story_service = get_story_service()
            themes = story_service.get_available_themes()
            
            await self.send_message(websocket, "story_themes", {
                "themes": themes
            })
            logger.info("发送故事主题列表")
            
        except Exception as e:
            logger.error(f"获取故事主题失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取故事主题失败")
    
    async def handle_get_story_recommendation(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取智能故事推荐"""
        try:
            user_id = self.get_user_id(websocket)
            
            # 获取用户当前角色
            profile = self.profile_service.get_profile(user_id)
            character_id = profile.current_character
            
            # 获取用户当前情绪（可选）
            mood = data.get("mood")
            
            story_service = get_story_service()
            recommendation = story_service.get_story_recommendation(character_id, mood)
            
            await self.send_message(websocket, "story_recommendation", recommendation)
            logger.info(f"为用户 {user_id} 生成故事推荐: {recommendation['recommended_theme']}")
            
        except Exception as e:
            logger.error(f"获取故事推荐失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取故事推荐失败")
    
    async def handle_get_bedtime_story(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取睡前故事（主要功能）"""
        try:
            user_id = self.get_user_id(websocket)
            
            # 获取用户当前角色
            profile = self.profile_service.get_profile(user_id)
            character_id = profile.current_character
            
            # 只有在用户有真正的昵称时才使用，避免传入长ID
            user_name = None
            if profile.nickname and profile.nickname != user_id and len(profile.nickname) <= 10:
                user_name = profile.nickname
            
            # 获取请求参数
            story_type = data.get("story_type", "preset")  # "preset" 或 "generated"
            theme = data.get("theme")  # 故事主题（可选）
            
            logger.info(f"用户 {user_id} 请求睡前故事: 类型={story_type}, 主题={theme}")
            
            # 获取故事服务
            story_service = get_story_service()
            story = await story_service.get_bedtime_story(
                user_id=user_id,
                character_id=character_id,
                story_type=story_type,
                theme=theme,
                user_name=user_name
            )
            
            if story:
                await self.send_message(websocket, "bedtime_story", {
                    "story": story,
                    "request_params": {
                        "story_type": story_type,
                        "theme": theme,
                        "character_id": character_id
                    }
                })
                logger.info(f"成功为用户 {user_id} 生成睡前故事: {story['title']}")
            else:
                await self.send_message(websocket, "error", "故事生成失败")
                
        except Exception as e:
            logger.error(f"获取睡前故事失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取睡前故事失败")
    
    async def handle_repeat_story(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """再听一遍故事"""
        try:
            user_id = self.get_user_id(websocket)
            
            # 获取上一个故事的参数
            last_story = data.get("last_story")
            if not last_story:
                await self.send_message(websocket, "error", "没有找到上一个故事")
                return
            
            # 重新发送相同的故事
            await self.send_message(websocket, "bedtime_story", {
                "story": last_story,
                "is_repeat": True
            })
            logger.info(f"用户 {user_id} 重复播放故事: {last_story.get('title', '未知')}")
            
        except Exception as e:
            logger.error(f"重复播放故事失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "重复播放故事失败")
    
    async def handle_change_story(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """换一个故事"""
        try:
            user_id = self.get_user_id(websocket)
            
            # 获取用户当前角色
            profile = self.profile_service.get_profile(user_id)
            character_id = profile.current_character
            
            # 只有在用户有真正的昵称时才使用，避免传入长ID
            user_name = None
            if profile.nickname and profile.nickname != user_id and len(profile.nickname) <= 10:
                user_name = profile.nickname
            
            # 使用相同的参数但生成不同的故事
            story_type = data.get("story_type", "preset")
            theme = data.get("theme")
            
            story_service = get_story_service()
            story = await story_service.get_bedtime_story(
                user_id=user_id,
                character_id=character_id,
                story_type=story_type,
                theme=theme,
                user_name=user_name
            )
            
            if story:
                await self.send_message(websocket, "bedtime_story", {
                    "story": story,
                    "is_new": True,
                    "request_params": {
                        "story_type": story_type,
                        "theme": theme,
                        "character_id": character_id
                    }
                })
                logger.info(f"用户 {user_id} 更换故事: {story['title']}")
            else:
                await self.send_message(websocket, "error", "生成新故事失败")
                
        except Exception as e:
            logger.error(f"更换故事失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "更换故事失败")
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理故事相关请求
        
        Args:
            websocket: WebSocket连接
            data: 请求数据
        """
        # 这个方法由具体的消息类型调用对应的处理方法
        pass
