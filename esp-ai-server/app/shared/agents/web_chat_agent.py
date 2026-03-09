"""
网页端对话Agent
Web Chat Agent
继承PureChatAgent，扩展网页端特有功能
"""

from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum

from app.core import logger
from .chat_agent import PureChatAgent, ChatRequest, ChatResponse, AgentMode
from .base_agent import MemoryType, make_memory
from app.shared.agents.adapters.profile_adapter import get_profile_service
from app.shared.agents.adapters.mood_adapter import get_mood_service
from app.prompts.system_prompts import get_character_prompt


class TreeHoleMode(Enum):
    """树洞模式"""
    NORMAL = "normal"      # 正常模式，保存对话
    TREE_HOLE = "tree_hole"  # 树洞模式，不保存对话


@dataclass
class WebChatRequest(ChatRequest):
    """网页端对话请求（扩展）"""
    enable_voice: bool = False  # 是否启用语音回复
    tree_hole_mode: bool = False  # 是否为树洞模式
    character: Optional[str] = None  # 指定角色
    include_knowledge: bool = True  # 是否包含知识库
    include_time_context: bool = True  # 是否包含时间上下文
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保metadata存在
        if not hasattr(self, 'metadata') or self.metadata is None:
            self.metadata = {}


@dataclass
class WebChatResponse(ChatResponse):
    """网页端对话响应（扩展）"""
    audio_base64: Optional[str] = None  # 语音回复的base64
    character_used: Optional[str] = None  # 使用的角色
    mood_detected: Optional[str] = None  # 检测到的情绪
    intimacy_change: float = 0.0  # 亲密度变化
    
    @property
    def response(self) -> str:
        """获取AI回复文本（兼容性属性）"""
        if self.conversation_context and len(self.conversation_context) > 0:
            return self.conversation_context[-1].get('content', '')
        return ''


class WebChatAgent(PureChatAgent):
    """
    网页端对话Agent
    继承PureChatAgent，扩展网页端特有功能：
    1. 树洞模式（不保存对话）
    2. 角色系统（多种AI角色）
    3. 情绪检测和响应
    4. 知识库增强
    5. 时间上下文
    6. 亲密度系统
    """
    
    def __init__(self):
        """初始化网页端对话Agent"""
        super().__init__()
        self.profile_service = get_profile_service()
        self.mood_service = get_mood_service()
        
        # 网页端特有配置
        self.enable_tree_hole = True
        self.enable_character_system = True
        self.enable_intimacy_system = True
        
        logger.info("✅ WebChatAgent初始化完成")
    
    async def process_web_chat(self, request: WebChatRequest) -> WebChatResponse:
        """
        处理网页端对话请求
        
        Args:
            request: 网页端对话请求
            
        Returns:
            WebChatResponse: 网页端对话响应
        """
        try:
            # 1. 获取用户档案和角色
            character = await self._get_character(request)
            
            # 2. 准备系统提示词
            system_prompt = self._prepare_system_prompt(request, character)
            
            # 3. 添加知识上下文（如果启用）
            if request.include_knowledge:
                await self._add_knowledge_context(request)
            
            # 4. 添加时间上下文（如果启用）
            if request.include_time_context:
                self._add_time_context(request)
            
            # 5. 调用基础ChatAgent处理
            base_request = ChatRequest(
                user_id=request.user_id,
                message=request.message,
                mode=request.mode,
                system_prompt=system_prompt
            )
            
            # 调用父类处理
            base_response = await self.process_chat(base_request)
            
            # 6. 检测情绪
            mood_detected = await self._detect_mood(request.user_id, request.message)
            
            # 7. 更新亲密度（如果不是树洞模式）
            intimacy_change = 0.0
            if not request.tree_hole_mode and self.enable_intimacy_system:
                # 从对话上下文获取AI回复
                ai_response = base_response.conversation_context[-1].get('content', '') if base_response.conversation_context else ''
                intimacy_change = await self._update_intimacy(
                    request.user_id, 
                    request.message,
                    ai_response,
                    request.enable_voice
                )
            
            # 8. 构建网页端响应
            web_response = WebChatResponse(
                conversation_context=base_response.conversation_context,
                strategy=base_response.strategy,
                risk_level=base_response.risk_level,
                emotion_analysis=base_response.emotion_analysis,
                processing_time_ms=base_response.processing_time_ms,
                metadata=base_response.metadata or {},
                # 网页端扩展字段
                audio_base64=None,  # 语音合成在外部处理
                character_used=character,
                mood_detected=mood_detected,
                intimacy_change=intimacy_change
            )
            
            logger.info(f"✅ WebChatAgent处理完成: user={request.user_id}, character={character}")
            return web_response
            
        except Exception as e:
            logger.error(f"WebChatAgent处理失败: {e}", exc_info=True)
            raise
    
    async def _get_character(self, request: WebChatRequest) -> str:
        """获取当前使用的角色"""
        try:
            # 优先使用请求中指定的角色
            if request.character:
                return request.character
            
            # 从用户档案获取
            profile = self.profile_service.get_profile(request.user_id)
            return profile.current_character if profile else "知心姐姐"
            
        except Exception as e:
            logger.warning(f"获取角色失败，使用默认: {e}")
            return "知心姐姐"
    
    def _prepare_system_prompt(self, request: WebChatRequest, character: str) -> str:
        """准备系统提示词"""
        try:
            # 获取角色提示词
            character_prompt = get_character_prompt(character)
            
            # 添加树洞模式提示
            if request.tree_hole_mode:
                character_prompt += "\n\n【树洞模式】用户希望倾诉，请提供温暖的陪伴，不要追问细节。"
            
            return character_prompt
            
        except Exception as e:
            logger.warning(f"准备系统提示词失败: {e}")
            return "你是一个温暖、善解人意的AI助手。"
    
    async def _add_knowledge_context(self, request: WebChatRequest):
        """添加知识库上下文"""
        # TODO: 集成知识库检索
        # 这里可以调用向量数据库检索相关知识
        pass
    
    def _add_time_context(self, request: WebChatRequest):
        """添加时间上下文"""
        from datetime import datetime
        
        now = datetime.now()
        time_context = f"当前时间: {now.strftime('%Y年%m月%d日 %H:%M')} {self._get_time_period(now.hour)}"
        
        # 添加到metadata
        if not request.metadata:
            request.metadata = {}
        request.metadata['time_context'] = time_context
    
    def _get_time_period(self, hour: int) -> str:
        """获取时间段描述"""
        if 5 <= hour < 8:
            return "清晨"
        elif 8 <= hour < 11:
            return "上午"
        elif 11 <= hour < 13:
            return "中午"
        elif 13 <= hour < 17:
            return "下午"
        elif 17 <= hour < 19:
            return "傍晚"
        elif 19 <= hour < 22:
            return "晚上"
        else:
            return "深夜"
    
    async def _detect_mood(self, user_id: str, message: str) -> Optional[str]:
        """检测用户情绪"""
        try:
            # TODO: 实现情绪检测逻辑
            # 可以使用情感分析模型或关键词匹配
            return None
        except Exception as e:
            logger.warning(f"情绪检测失败: {e}")
            return None
    
    async def _update_intimacy(self, user_id: str, user_message: str, 
                              ai_response: str, is_voice: bool = False) -> float:
        """
        更新用户亲密度
        
        Args:
            user_id: 用户ID
            user_message: 用户消息
            ai_response: AI回复
            is_voice: 是否为语音对话
            
        Returns:
            float: 亲密度变化值
        """
        try:
            # 基础亲密度增加
            base_intimacy = 1.0
            
            # 语音对话额外加分
            if is_voice:
                base_intimacy += 0.5
            
            # 消息长度加分（深度对话）
            if len(user_message) > 50:
                base_intimacy += 0.3
            
            # TODO: 保存到数据库
            # self.profile_service.update_intimacy(user_id, base_intimacy)
            
            return base_intimacy
            
        except Exception as e:
            logger.warning(f"更新亲密度失败: {e}")
            return 0.0
    
    async def get_conversation_summary(self, user_id: str, limit: int = 10) -> str:
        """
        获取对话摘要
        
        Args:
            user_id: 用户ID
            limit: 获取最近N条对话
            
        Returns:
            str: 对话摘要
        """
        try:
            # 获取最近的对话
            memories = await self.memory_agent.recall_memories(
                user_id=user_id,
                memory_types=[MemoryType.EPISODIC_MEMORY],
                limit=limit
            )
            
            if not memories or MemoryType.EPISODIC_MEMORY not in memories:
                return "暂无对话历史"
            
            # 构建摘要
            episodes = memories[MemoryType.EPISODIC_MEMORY]
            summary_parts = []
            
            for episode in episodes[:5]:  # 最多5条
                content = episode.get('content', '')
                if content:
                    summary_parts.append(f"- {content}")
            
            return "\n".join(summary_parts) if summary_parts else "暂无对话历史"
            
        except Exception as e:
            logger.error(f"获取对话摘要失败: {e}")
            return "获取对话历史失败"


# 全局WebChatAgent实例
_web_chat_agent = None


def get_web_chat_agent() -> WebChatAgent:
    """获取WebChatAgent单例"""
    global _web_chat_agent
    if _web_chat_agent is None:
        _web_chat_agent = WebChatAgent()
    return _web_chat_agent
