"""
WebSocket文本处理器
WebSocket Text Handler
处理文本消息和对话
"""

from typing import Dict, Any

from .base_handler import WebSocketBaseHandler, WebSocketMessageValidator


class WebSocketTextHandler(WebSocketBaseHandler):
    """WebSocket文本处理器"""
    
    @property
    def message_type(self) -> str:
        """消息类型"""
        return "text"
    
    async def handle(self, websocket, message_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        处理文本消息
        
        Args:
            websocket: WebSocket连接
            message_data: 文本消息数据
            context: 上下文信息
            
        Returns:
            bool: 是否处理成功
        """
        try:
            # 验证文本消息格式
            is_valid, error_msg = WebSocketMessageValidator.validate_text_message(message_data)
            if not is_valid:
                self.logger.error(f"[{self.tag}] 文本消息验证失败: {error_msg}")
                await self.send_error(websocket, "INVALID_TEXT", error_msg)
                return False
            
            # 提取文本内容
            text_content = message_data.get("content", "").strip()
            device_id = context.get("device_id", "unknown")
            
            self.logger.info(f"[{self.tag}] 设备 {device_id} 发送文本: {text_content}")
            
            # 处理文本消息
            result = await self._process_text_message(websocket, text_content, context)
            
            return result
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 文本处理失败: {e}", exc_info=True)
            await self.send_error(websocket, "TEXT_ERROR", str(e))
            return False
    
    async def _process_text_message(self, websocket, text_content: str, context: Dict[str, Any]) -> bool:
        """处理文本消息"""
        device_id = context.get("device_id", "unknown")
        
        try:
            # TODO: 集成对话服务
            # from ..services import get_esp32_chat_service
            # chat_service = get_esp32_chat_service()
            # response = await chat_service.process_user_message(device_id, text_content)
            
            # 模拟对话处理
            mock_response = f"收到您的消息: {text_content}"
            
            # 发送文本处理结果
            await self.send_response(websocket, "text_processed", {
                "original_text": text_content,
                "processed": True,
                "response": mock_response
            })
            
            # TODO: 集成TTS服务发送语音回复
            # from ..services import get_esp32_tts_integration
            # tts_service = get_esp32_tts_integration(device_id)
            # await tts_service.synthesize_and_send(websocket, mock_response)
            
            self.logger.info(f"[{self.tag}] 设备 {device_id} 文本处理完成")
            return True
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 设备 {device_id} 文本处理失败: {e}")
            return False
