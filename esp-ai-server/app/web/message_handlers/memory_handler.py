"""
记忆处理器
Memory Handler
处理智能记忆Agent的调用和记忆管理
"""

from typing import Dict, Any
import websockets

from app.core import logger
from app.prompts.knowledge_base import get_relevant_knowledge
from .base_handler import BaseMessageHandler


class MemoryHandler(BaseMessageHandler):
    """记忆处理器"""
    
    async def process_memory_recall(self, websocket: websockets.WebSocketServerProtocol, 
                                  user_id: str, user_message: str) -> bool:
        """
        处理记忆召回
        
        Args:
            websocket: WebSocket连接
            user_id: 用户ID
            user_message: 用户消息
            
        Returns:
            bool: 是否成功处理记忆召回
        """
        if user_id.startswith("guest_") or self.is_tree_hole_mode(user_id):
            return False
            
        try:
            # 调用记忆Agent进行分析和召回
            memory_analysis = await self.memory_agent.analyze({
                "user_id": user_id,
                "user_message": user_message,
                "conversation_history": self.get_conversations(websocket)
            })
            
            # 执行记忆写入和召回
            if memory_analysis.get("should_execute", True):
                memory_result = await self.memory_agent.execute(memory_analysis)
                
                # 处理召回的记忆
                recall_data = memory_result.get("recall", {})
                if recall_data:
                    # 格式化召回的记忆为上下文
                    context_parts = []
                    
                    # 导入 MemoryType 枚举
                    from app.shared.agents.base_agent import MemoryType
                    
                    # 处理情节记忆
                    episodic_memories = recall_data.get(MemoryType.EPISODIC_MEMORY, [])
                    if episodic_memories:
                        context_parts.append("【相关记忆】")
                        for memory, score in episodic_memories:
                            context_parts.append(f"- {memory.content}")
                    
                    # 处理语义档案记忆
                    profile_memories = recall_data.get(MemoryType.SEMANTIC_PROFILE, [])
                    if profile_memories:
                        if not context_parts:
                            context_parts.append("【用户档案】")
                        else:
                            context_parts.append("\n【用户档案】")
                        for memory, score in profile_memories:
                            context_parts.append(f"- {memory.content}")
                    
                    if context_parts:
                        memory_context = "\n".join(context_parts)
                        self.add_message(websocket, "system", memory_context)
                        total_memories = len(episodic_memories) + len(profile_memories)
                        logger.info(f"🧠 智能召回了 {total_memories} 条相关记忆 (情节:{len(episodic_memories)}, 档案:{len(profile_memories)})")
                
                # 处理风险标记
                risk_flags = memory_result.get("risk_flags", [])
                if risk_flags:
                    logger.warning(f"⚠️ 检测到风险信号: {[rf.get('keyword', str(rf)) for rf in risk_flags]}")
                    
            return True
            
        except Exception as e:
            logger.error(f"智能记忆Agent失败: {e}", exc_info=True)
            return False
    
    async def process_memory_extraction(self, websocket: websockets.WebSocketServerProtocol, 
                                      user_id: str, user_message: str) -> bool:
        """
        处理记忆提取
        
        Args:
            websocket: WebSocket连接
            user_id: 用户ID
            user_message: 用户消息
            
        Returns:
            bool: 是否成功处理记忆提取
        """
        if user_id.startswith("guest_") or self.is_tree_hole_mode(user_id):
            return False
            
        try:
            # 调用记忆Agent进行分析和提取
            memory_analysis = await self.memory_agent.analyze({
                "user_id": user_id,
                "user_message": user_message,
                "conversation_history": self.get_conversations(websocket)
            })
            
            # 执行记忆写入（提取新记忆）
            if memory_analysis.get("should_execute", True):
                memory_result = await self.memory_agent.execute(memory_analysis)
                
                # 记录提取的记忆数量（从分析结果中获取）
                analysis_result = memory_result.get("analysis", {})
                emotion = analysis_result.get("emotion")
                events = analysis_result.get("events", [])
                preferences = analysis_result.get("preferences", [])
                
                total_extracted = 0
                if emotion:
                    total_extracted += 1
                total_extracted += len(events) + len(preferences)
                
                if total_extracted > 0:
                    logger.info(f"🧠 智能提取了 {total_extracted} 条新记忆 (情绪:{1 if emotion else 0}, 事件:{len(events)}, 偏好:{len(preferences)})")
                
                # 处理风险标记
                risk_flags = memory_result.get("risk_flags", [])
                if risk_flags:
                    logger.warning(f"⚠️ 检测到风险信号: {[rf.get('keyword', str(rf)) for rf in risk_flags]}")
                    
            return True
            
        except Exception as e:
            logger.error(f"智能记忆Agent提取失败: {e}", exc_info=True)
            return False
    
    async def add_knowledge_context(self, websocket: websockets.WebSocketServerProtocol, user_message: str):
        """添加相关知识到上下文"""
        try:
            knowledge = get_relevant_knowledge(user_message)
            if knowledge:
                knowledge_text = f"【相关知识】\n{knowledge}"
                self.add_message(websocket, "system", knowledge_text)
                logger.info(f"💡 添加相关知识: {knowledge[:50]}...")
        except Exception as e:
            logger.error(f"添加知识上下文失败: {e}")
    
    async def handle(self, websocket: websockets.WebSocketServerProtocol, data: Dict[str, Any]) -> None:
        """
        处理记忆相关请求
        
        Args:
            websocket: WebSocket连接
            data: 请求数据
        """
        action = data.get("action")
        user_id = self.get_user_id(websocket)
        user_message = data.get("user_message", "")
        
        if action == "recall":
            await self.process_memory_recall(websocket, user_id, user_message)
        elif action == "extract":
            await self.process_memory_extraction(websocket, user_id, user_message)
        elif action == "add_knowledge":
            await self.add_knowledge_context(websocket, user_message)
        else:
            logger.warning(f"未知的记忆处理动作: {action}")
