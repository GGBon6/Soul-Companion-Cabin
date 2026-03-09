"""
日记处理器
Diary Handler
处理日记生成和管理功能
"""

from typing import Dict, Any
import websockets

from app.core import logger
from app.web.message_handlers.base_handler import BaseMessageHandler


class DiaryHandler(BaseMessageHandler):
    """日记处理器"""
    
    async def handle_generate_diary(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """生成日记"""
        try:
            user_id = self.get_user_id(websocket)
            date = data.get("date", "")
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "error", "游客模式无法使用日记功能")
                return
            
            # 生成日记
            diary_service = self.ws_handler.diary_service
            diary = diary_service.generate_diary(user_id, date)
            
            if diary:
                await self.send_message(websocket, "diary_generated", {
                    "diary": diary,
                    "date": date
                })
                logger.info(f"为用户 {user_id} 生成日记: {date}")
            else:
                await self.send_message(websocket, "error", "日记生成失败")
                
        except Exception as e:
            logger.error(f"生成日记失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "生成日记失败")
    
    async def handle_get_diary(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取指定日期的日记"""
        try:
            user_id = self.get_user_id(websocket)
            date = data.get("date", "")
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "diary_data", None)
                return
            
            # 获取日记
            diary_service = self.ws_handler.diary_service
            diary = diary_service.get_diary(user_id, date)
            
            await self.send_message(websocket, "diary_data", diary)
            logger.info(f"获取用户 {user_id} 的日记: {date}")
            
        except Exception as e:
            logger.error(f"获取日记失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取日记失败")
    
    async def handle_get_diary_list(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取日记列表"""
        try:
            user_id = self.get_user_id(websocket)
            limit = data.get("limit", 30)
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "diary_list", [])
                return
            
            # 获取日记列表
            diary_service = self.ws_handler.diary_service
            diary_list = diary_service.get_diary_list(user_id, limit=limit)
            
            await self.send_message(websocket, "diary_list", diary_list)
            logger.info(f"获取用户 {user_id} 的日记列表: {len(diary_list)} 条")
            
        except Exception as e:
            logger.error(f"获取日记列表失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取日记列表失败")
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理日记相关请求
        
        Args:
            websocket: WebSocket连接
            data: 请求数据
        """
        # 这个方法由具体的消息类型调用对应的处理方法
        pass
