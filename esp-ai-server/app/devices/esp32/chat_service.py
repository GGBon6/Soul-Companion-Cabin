"""
ESP32专用对话服务
ESP32 Chat Service
基于ChatAgent架构，为ESP32设备提供完整的对话功能和持久化保存
"""

import time
from typing import Dict, Optional, List
from app.core import logger
from app.shared.agents import PureChatAgent, ChatRequest, AgentMode
from app.core.agent_config import AgentConfig
from app.shared.services.chat_history_service import get_chat_history_service


class ESP32ChatService:
    """ESP32专用对话服务"""
    
    def __init__(self):
        """初始化ESP32对话服务"""
        self.chat_history_service = get_chat_history_service()
        self.agent_config = AgentConfig()
        
        # 存储每个设备的PureChatAgent实例
        self.device_agents: Dict[str, PureChatAgent] = {}
        
        # 存储设备会话信息
        self.device_sessions: Dict[str, Dict] = {}
    
    def create_device_session(self, device_id: str, client_id: str) -> str:
        """创建设备会话"""
        session_id = f"esp32_{device_id}_{int(time.time())}"
        user_id = f"esp32_{device_id}"
        
        # 创建会话信息
        self.device_sessions[device_id] = {
            "device_id": device_id,
            "client_id": client_id,
            "session_id": session_id,
            "user_id": user_id,
            "created_at": time.time(),
            "sample_rate": 16000,
            "frame_duration": 40,
            "protocol_version": 2
        }
        
        # 为设备创建专用的PureChatAgent
        self.device_agents[device_id] = PureChatAgent()
        
        logger.info(f"✅ 创建ESP32设备会话: {device_id} -> {session_id}")
        return session_id
    
    def update_session_params(self, device_id: str, audio_params: Dict, protocol_version: int):
        """更新会话参数"""
        if device_id not in self.device_sessions:
            logger.error(f"设备会话不存在: {device_id}")
            return
        
        session = self.device_sessions[device_id]
        session.update({
            "sample_rate": audio_params.get("sample_rate", 16000),
            "frame_duration": audio_params.get("frame_duration", 40),
            "protocol_version": protocol_version
        })
        
        logger.debug(f"更新ESP32设备参数: {device_id} - {audio_params}")
    
    def get_session(self, device_id: str) -> Optional[Dict]:
        """获取设备会话"""
        return self.device_sessions.get(device_id)
    
    def get_agent(self, device_id: str) -> Optional[PureChatAgent]:
        """获取设备的ChatAgent"""
        return self.device_agents.get(device_id)
    
    async def process_user_message(self, device_id: str, text: str) -> Optional[str]:
        """
        处理用户消息并生成回复
        使用ChatAgent架构，包含完整的记忆管理和持久化保存
        """
        try:
            session = self.get_session(device_id)
            agent = self.get_agent(device_id)
            
            if not session or not agent:
                logger.error(f"设备会话或Agent不存在: {device_id}")
                return None
            
            user_id = session["user_id"]
            session_id = session["session_id"]
            
            logger.info(f"🎤 ESP32用户消息: {device_id} -> {text}")
            
            # 保存用户消息到历史记录
            self.chat_history_service.save_message(
                user_id=user_id,
                role="user",
                content=text,
                metadata={"session_id": session_id, "message_type": "text"}
            )
            
            # 使用PureChatAgent处理消息（包含记忆管理）
            chat_request = ChatRequest(
                user_id=user_id,
                message=text,
                mode=AgentMode.NORMAL,
                client_type='esp32'  # 标识为ESP32设备请求
            )
            chat_response = await agent.process_chat(chat_request)
            response = chat_response.conversation_context[-1]["content"] if chat_response.conversation_context else None
            
            if not response:
                logger.warning(f"ChatAgent返回空回复: {device_id}")
                return None
            
            logger.info(f"🤖 ESP32 Agent回复: {device_id} -> {response}")
            
            # 保存助手回复到历史记录
            self.chat_history_service.save_message(
                user_id=user_id,
                role="assistant", 
                content=response,
                metadata={"session_id": session_id, "message_type": "text"}
            )
            
            return response
            
        except Exception as e:
            logger.error(f"处理ESP32消息失败: {device_id} - {e}", exc_info=True)
            return None
    
    async def get_conversation_history(self, device_id: str, limit: int = 20) -> List[Dict]:
        """获取设备的对话历史"""
        session = self.get_session(device_id)
        if not session:
            return []
        
        try:
            user_id = session["user_id"]
            session_id = session["session_id"]
            
            # 从数据库获取历史记录
            messages = await self.chat_history_service.get_messages(
                user_id=user_id,
                session_id=session_id,
                limit=limit
            )
            
            # 转换为对话格式
            conversation = []
            for msg in messages:
                conversation.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                    "timestamp": msg.get("created_at")
                })
            
            return conversation
            
        except Exception as e:
            logger.error(f"获取ESP32对话历史失败: {device_id} - {e}")
            return []
    
    def cleanup_device(self, device_id: str):
        """清理设备资源"""
        try:
            # 清理ChatAgent
            if device_id in self.device_agents:
                agent = self.device_agents[device_id]
                # 如果Agent有清理方法，调用它
                if hasattr(agent, 'cleanup'):
                    agent.cleanup()
                del self.device_agents[device_id]
            
            # 清理会话信息
            if device_id in self.device_sessions:
                del self.device_sessions[device_id]
            
            logger.info(f"🧹 已清理ESP32设备资源: {device_id}")
            
        except Exception as e:
            logger.error(f"清理ESP32设备资源失败: {device_id} - {e}")
    
    def get_device_count(self) -> int:
        """获取当前连接的设备数量"""
        return len(self.device_sessions)
    
    def get_device_list(self) -> List[Dict]:
        """获取设备列表"""
        devices = []
        for device_id, session in self.device_sessions.items():
            devices.append({
                "device_id": device_id,
                "client_id": session.get("client_id"),
                "session_id": session.get("session_id"),
                "user_id": session.get("user_id"),
                "created_at": session.get("created_at"),
                "connected_duration": time.time() - session.get("created_at", 0)
            })
        return devices


# 全局ESP32对话服务实例
_esp32_chat_service = None

def get_esp32_chat_service() -> ESP32ChatService:
    """获取ESP32对话服务单例"""
    global _esp32_chat_service
    if _esp32_chat_service is None:
        _esp32_chat_service = ESP32ChatService()
    return _esp32_chat_service
