"""
心情处理器
Mood Handler
处理心情签到和心情统计功能
"""

from typing import Dict, Any
import websockets

from app.core import logger
from app.web.message_handlers.base_handler import BaseMessageHandler
from app.shared.agents.adapters.mood_adapter import get_mood_service


class MoodHandler(BaseMessageHandler):
    """心情处理器"""
    
    async def handle_mood_checkin(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """处理心情签到"""
        try:
            user_id = self.get_user_id(websocket)
            mood_score = data.get("mood_score", 5)
            mood_note = data.get("mood_note", "")
            mood_id = data.get("mood", "calm")  # 前端发送的具体情绪ID
            intensity = data.get("intensity", mood_score)  # 强度值
            
            # 调试日志：显示接收到的数据
            logger.info(f"收到心情签到数据: mood_id={mood_id}, intensity={intensity}, mood_score={mood_score}, note='{mood_note}'")
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "error", "游客模式无法使用心情签到")
                return
            
            # 保存心情数据 - 使用前端发送的具体情绪ID
            mood_service = get_mood_service()
            success = mood_service.save_mood_with_id(user_id, mood_id, intensity, mood_note)
            
            if success:
                # 获取情绪的中文名称和表情符号用于显示
                mood_display = self._get_mood_display(mood_id)
                
                # 同步心情数据到MemoryAgent的情绪记忆
                await self._sync_mood_to_memory(user_id, mood_id, intensity, mood_note, mood_display)
                
                await self.send_message(websocket, "mood_checkin_success", {
                    "message": "心情签到成功",
                    "mood_id": mood_id,
                    "mood_name": mood_display["name"],
                    "mood_emoji": mood_display["emoji"],
                    "intensity": intensity,
                    "mood_note": mood_note
                })
                logger.info(f"用户 {user_id} 心情签到: {mood_display['name']} {mood_display['emoji']}")
            else:
                await self.send_message(websocket, "error", "心情签到失败")
                
        except Exception as e:
            logger.error(f"心情签到失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "心情签到失败")
    
    async def handle_get_mood_history(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取心情历史"""
        try:
            user_id = self.get_user_id(websocket)
            days = data.get("days", 30)
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "mood_history", [])
                return
            
            # 获取心情历史
            mood_service = get_mood_service()
            mood_history = mood_service.get_mood_history(user_id, days=days)
            
            await self.send_message(websocket, "mood_history", mood_history)
            logger.info(f"获取用户 {user_id} 心情历史: {len(mood_history)} 条")
            
        except Exception as e:
            logger.error(f"获取心情历史失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取心情历史失败")
    
    async def handle_get_mood_statistics(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取心情统计"""
        try:
            user_id = self.get_user_id(websocket)
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "mood_statistics", {})
                return
            
            # 获取心情统计
            mood_service = get_mood_service()
            statistics = mood_service.get_mood_statistics(user_id)
            
            await self.send_message(websocket, "mood_statistics", statistics)
            logger.info(f"获取用户 {user_id} 心情统计")
            
        except Exception as e:
            logger.error(f"获取心情统计失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取心情统计失败")
    
    def _get_mood_display(self, mood_id: str) -> dict:
        """获取情绪的显示信息"""
        mood_mapping = {
            'happy': {'name': '开心', 'emoji': '😊'},
            'excited': {'name': '兴奋', 'emoji': '🤩'},
            'calm': {'name': '平静', 'emoji': '😌'},
            'sad': {'name': '难过', 'emoji': '😢'},
            'angry': {'name': '生气', 'emoji': '😠'},
            'anxious': {'name': '焦虑', 'emoji': '😰'},
            'tired': {'name': '疲惫', 'emoji': '😴'},
            'confused': {'name': '迷茫', 'emoji': '😕'}
        }
        return mood_mapping.get(mood_id, {'name': '平静', 'emoji': '😌'})
    
    async def _sync_mood_to_memory(self, user_id: str, mood_id: str, intensity: int, mood_note: str, mood_display: dict):
        """将心情签到数据同步到MemoryAgent的情绪记忆"""
        try:
            from app.shared.agents.base_agent import make_memory, MemoryType, AgentMode
            
            # 构建情绪记忆内容
            emotion_content = f"心情签到: {mood_display['name']} (强度: {intensity}/5)"
            if mood_note:
                emotion_content += f" - {mood_note}"
            
            # 创建情绪记忆记录
            emotion_memory = make_memory(
                user_id=user_id,
                type=MemoryType.AFFECT_BASELINE,
                content=emotion_content,
                importance=7,  # 心情签到是重要的情绪数据
                meta={
                    "mood_id": mood_id,
                    "mood_name": mood_display['name'],
                    "mood_emoji": mood_display['emoji'],
                    "intensity": intensity,
                    "note": mood_note,
                    "type": "mood_checkin"
                }
            )
            
            # 获取MemoryAgent并写入情绪记忆
            memory_agent = self.ws_handler.memory_agent
            # 使用BaseAgent的memory接口写入情绪记忆
            memory_agent.memory.remember(user_id, [emotion_memory], AgentMode.NORMAL)
            
            logger.info(f"✅ 心情签到数据已同步到MemoryAgent: {user_id} - {mood_display['name']} {mood_display['emoji']}")
            
        except Exception as e:
            logger.error(f"同步心情数据到MemoryAgent失败: {e}", exc_info=True)
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理心情相关请求
        
        Args:
            websocket: WebSocket连接
            data: 请求数据
        """
        # 这个方法由具体的消息类型调用对应的处理方法
        pass
