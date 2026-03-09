"""
角色处理器
Character Handler
处理角色切换和角色管理功能
"""

from typing import Dict, Any
import websockets

from app.core import logger
from app.prompts.system_prompts import get_all_characters
from app.web.message_handlers.base_handler import BaseMessageHandler


class CharacterHandler(BaseMessageHandler):
    """角色处理器"""
    
    async def handle_switch_character(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """处理角色切换"""
        try:
            user_id = self.get_user_id(websocket)
            character_id = data.get("character_id", "").strip()
            
            if not character_id:
                await self.send_message(websocket, "error", "角色ID不能为空")
                return
            
            # 验证角色ID是否有效
            all_characters = get_all_characters()
            valid_character_ids = [char["id"] for char in all_characters]
            if character_id not in valid_character_ids:
                await self.send_message(websocket, "error", "无效的角色ID")
                return
            
            # 更新用户档案中的当前角色
            success = self.profile_service.switch_character(user_id, character_id)
            
            if success:
                # 重新初始化对话（使用新角色的系统提示词）
                self.ws_handler.conversations[websocket] = self.ws_handler._init_conversation(websocket, user_id)
                
                # 找到对应的角色信息
                character_info = next((char for char in all_characters if char["id"] == character_id), None)
                await self.send_message(websocket, "character_switched", {
                    "character_id": character_id,
                    "character_name": character_info["name"] if character_info else character_id,
                    "message": f"已切换到角色：{character_info['name'] if character_info else character_id}"
                })
                logger.info(f"用户 {user_id} 切换到角色: {character_id}")
            else:
                await self.send_message(websocket, "error", "角色切换失败")
                
        except Exception as e:
            logger.error(f"角色切换失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "角色切换失败")
    
    async def handle_get_characters(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """获取所有可用角色"""
        try:
            user_id = self.get_user_id(websocket)
            
            # 获取所有角色信息
            all_characters = get_all_characters()
            
            # 获取用户当前选择的角色
            profile = self.profile_service.get_profile(user_id)
            current_character = profile.current_character
            
            # 格式化角色数据
            characters_data = []
            for char_id, char_info in all_characters.items():
                characters_data.append({
                    "id": char_id,
                    "name": char_info["name"],
                    "description": char_info.get("description", ""),
                    "avatar": char_info.get("avatar", ""),
                    "is_current": char_id == current_character
                })
            
            await self.send_message(websocket, "characters_list", {
                "characters": characters_data,
                "current_character": current_character
            })
            
        except Exception as e:
            logger.error(f"获取角色列表失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "获取角色列表失败")
    
    async def handle_toggle_tree_hole_mode(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """切换树洞模式"""
        try:
            user_id = self.get_user_id(websocket)
            enabled = data.get("enabled", False)
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "error", "游客模式无法使用树洞功能")
                return
            
            # 更新树洞模式设置
            success = self.profile_service.toggle_tree_hole_mode(user_id, enabled)
            
            if success:
                status = "开启" if enabled else "关闭"
                await self.send_message(websocket, "tree_hole_mode_updated", {
                    "enabled": enabled,
                    "message": f"树洞模式已{status}"
                })
                logger.info(f"用户 {user_id} {status}树洞模式")
            else:
                await self.send_message(websocket, "error", "树洞模式切换失败")
                
        except Exception as e:
            logger.error(f"切换树洞模式失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "树洞模式切换失败")
    
    async def handle_update_proactive_settings(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """更新主动聊天设置"""
        try:
            user_id = self.get_user_id(websocket)
            enabled = data.get("enabled", False)
            chat_time = data.get("chat_time", "20:00")
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "error", "游客模式无法设置主动聊天")
                return
            
            # 更新主动聊天设置
            success = self.profile_service.update_proactive_settings(user_id, enabled, chat_time)
            
            if success:
                status = "开启" if enabled else "关闭"
                await self.send_message(websocket, "proactive_settings_updated", {
                    "enabled": enabled,
                    "chat_time": chat_time,
                    "message": f"主动聊天已{status}" + (f"，时间设置为 {chat_time}" if enabled else "")
                })
                logger.info(f"用户 {user_id} {status}主动聊天，时间: {chat_time}")
            else:
                await self.send_message(websocket, "error", "主动聊天设置失败")
                
        except Exception as e:
            logger.error(f"更新主动聊天设置失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "主动聊天设置失败")
    
    async def handle_check_proactive_chat(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]):
        """检查主动聊天"""
        try:
            user_id = self.get_user_id(websocket)
            
            if user_id.startswith("guest_"):
                await self.send_message(websocket, "proactive_chat_result", {"should_chat": False})
                return
            
            # 检查是否应该主动聊天
            proactive_service = self.ws_handler.proactive_chat_service
            chat_result = proactive_service.should_initiate_chat(user_id)
            
            result = {
                "should_chat": chat_result.get("should_chat", False),
                "message": chat_result.get("message") if chat_result.get("should_chat") else None,
                "reason": chat_result.get("reason")
            }
            
            await self.send_message(websocket, "proactive_chat_result", result)
            
            if result.get("should_chat"):
                message = result.get("message", "")
                logger.info(f"为用户 {user_id} 生成主动聊天: {message[:30] if message else 'N/A'}...")
                
        except Exception as e:
            logger.error(f"检查主动聊天失败: {e}", exc_info=True)
            await self.send_message(websocket, "error", "检查主动聊天失败")
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理角色相关请求
        
        Args:
            websocket: WebSocket连接
            data: 请求数据
        """
        # 这个方法由具体的消息类型调用对应的处理方法
        pass
