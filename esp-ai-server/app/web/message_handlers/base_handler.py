"""
基础消息处理器
Base Message Handler
提供消息处理的基础功能和接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
import websockets
from datetime import datetime

from app.core import logger


class BaseMessageHandler(ABC):
    """基础消息处理器"""
    
    def __init__(self, websocket_handler):
        """
        初始化基础处理器
        
        Args:
            websocket_handler: 主WebSocket处理器实例
        """
        self.ws_handler = websocket_handler
        self.llm_service = websocket_handler.llm_service
        # ASR服务改用连接池，不再从handler获取
        # self.asr_service = websocket_handler.asr_service  # 已移除
        self.tts_service = websocket_handler.tts_service
        self.memory_agent = websocket_handler.memory_agent
        
        # 使用新架构的适配器服务
        from app.shared.agents.adapters.profile_adapter import get_profile_service
        from app.shared.agents.adapters.history_adapter import get_history_service
        self.profile_service = get_profile_service()
        self.history_service = get_history_service()
        
    @abstractmethod
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理消息的抽象方法
        
        Args:
            websocket: WebSocket连接
            data: 消息数据
        """
        pass
    
    def get_user_id(self, websocket: websockets.WebSocketServerProtocol) -> str:
        """获取用户ID"""
        user_id = self.ws_handler.websocket_to_user.get(websocket)
        if not user_id:
            user_id = f"guest_{id(websocket)}"
            self.ws_handler.websocket_to_user[websocket] = user_id
        return user_id
    
    def is_tree_hole_mode(self, user_id: str) -> bool:
        """检查是否为树洞模式"""
        if user_id.startswith("guest_"):
            return False
        profile = self.profile_service.get_profile(user_id)
        return profile.tree_hole_mode
    
    def add_message(self, websocket: websockets.WebSocketServerProtocol, role: str, content: str, 
                   metadata: Dict = None, skip_save: bool = False):
        """添加消息到对话历史"""
        self.ws_handler._add_message(websocket, role, content, metadata, skip_save)
    
    async def send_message(self, websocket: websockets.WebSocketServerProtocol, 
                          message_type: str, data: Any):
        """发送消息"""
        await self.ws_handler.send_message(websocket, message_type, data)
    
    def get_conversations(self, websocket: websockets.WebSocketServerProtocol) -> List[Dict]:
        """获取对话历史"""
        return self.ws_handler.conversations.get(websocket, [])
    
    def ensure_conversation_initialized(self, websocket: websockets.WebSocketServerProtocol):
        """确保对话已初始化"""
        if websocket not in self.ws_handler.conversations:
            self.ws_handler.conversations[websocket] = self.ws_handler._init_conversation(websocket)
    
    def add_time_context(self, conversations: List[Dict]) -> List[Dict]:
        """添加时间上下文信息"""
        current_time = datetime.now()
        hour = current_time.hour
        minute = current_time.minute
        
        # 时间段描述
        if 0 <= hour < 6:
            time_period = "凌晨"
        elif 6 <= hour < 9:
            time_period = "早上"
        elif 9 <= hour < 12:
            time_period = "上午"
        elif 12 <= hour < 13:
            time_period = "中午"
        elif 13 <= hour < 18:
            time_period = "下午"
        else:
            time_period = "晚上"
        
        time_info = f"[系统时间] 现在是 {current_time.strftime('%Y年%m月%d日')}（星期{['一','二','三','四','五','六','日'][current_time.weekday()]}）{time_period}{hour}点{minute}分"
        
        temp_conversation = conversations.copy()
        temp_conversation.append({
            "role": "system",
            "content": time_info
        })
        
        return temp_conversation
    
    def calculate_intimacy_gain(self, user_message: str, assistant_response: str, is_voice: bool = False) -> int:
        """计算亲密度增长"""
        return self.ws_handler._calculate_intimacy_gain(user_message, assistant_response, is_voice)
    
    async def update_intimacy(self, user_id: str, user_message: str, assistant_response: str, is_voice: bool = False):
        """更新用户亲密度"""
        if user_id.startswith("guest_"):
            return
            
        try:
            intimacy_points = self.calculate_intimacy_gain(user_message, assistant_response, is_voice)
            if intimacy_points > 0:
                profile = self.profile_service.get_profile(user_id)
                old_level = profile.intimacy_level
                self.profile_service.add_intimacy(user_id, intimacy_points)
                new_level = self.profile_service.get_profile(user_id).intimacy_level
                
                voice_tag = "[语音]" if is_voice else ""
                logger.info(f"💕 用户 {user_id} 亲密度 +{intimacy_points} {voice_tag} (当前: {new_level})")
                
                # 检查里程碑
                if old_level < 10 <= new_level:
                    logger.info(f"🎉 用户 {user_id} 达成里程碑: 初识")
                elif old_level < 30 <= new_level:
                    logger.info(f"🎉 用户 {user_id} 达成里程碑: 熟悉")
                elif old_level < 60 <= new_level:
                    logger.info(f"🎉 用户 {user_id} 达成里程碑: 亲密")
                elif old_level < 100 <= new_level:
                    logger.info(f"🎉 用户 {user_id} 达成里程碑: 挚爱")
        except Exception as e:
            logger.error(f"更新亲密度失败: {e}")
