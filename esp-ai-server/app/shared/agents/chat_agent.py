"""
Agent架构的对话处理器
- 现代化异步API
- 无循环依赖
"""

import asyncio
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from app.core import logger


class AgentMode(str, Enum):
    """Agent模式"""
    NORMAL = "normal"
    TREE_HOLE = "tree_hole"
    PARENT_VIEW = "parent_view"
    SCHOOL_VIEW = "school_view"


class ConversationStrategy(str, Enum):
    """对话策略"""
    EMPATHY = "empathy"      # 共情陪伴
    GUIDANCE = "guidance"    # 引导建议
    KNOWLEDGE = "knowledge"  # 知识问答
    CASUAL = "casual"        # 日常聊天
    CRISIS = "crisis"        # 危机干预


@dataclass
class ChatRequest:
    """对话请求"""
    user_id: str
    message: str
    history: List[Dict[str, str]] = None
    mode: AgentMode = AgentMode.NORMAL
    system_prompt: Optional[str] = None
    enable_emotion: bool = True
    enable_risk: bool = True
    client_type: str = 'system'  # 客户端类型: 'web', 'esp32', 'system'


@dataclass
class ChatResponse:
    """对话响应"""
    conversation_context: List[Dict[str, str]]
    strategy: ConversationStrategy
    risk_level: int
    emotion_analysis: Optional[Dict[str, Any]] = None
    processing_time_ms: int = 0
    metadata: Optional[Dict[str, Any]] = None


class PureChatAgent:
    """
    纯Agent对话处理器
    - 无Service层依赖
    - 完整智能功能
    - 高性能处理
    """
    
    def __init__(self):
        self.name = "PureChatAgent"
        
        # 策略提示词映射
        self.strategy_prompts = {
            ConversationStrategy.EMPATHY: "请以共情和理解的方式回应，关注用户的情感需求。",
            ConversationStrategy.GUIDANCE: "请提供建设性的建议和引导，帮助用户思考和成长。",
            ConversationStrategy.KNOWLEDGE: "请提供准确、易懂的知识解答，满足用户的学习需求。",
            ConversationStrategy.CASUAL: "请以轻松、自然的方式对话，营造愉快的交流氛围。",
            ConversationStrategy.CRISIS: "⚠️ 用户可能处于情绪危机中，请优先关注其安全，提供专业的心理支持。"
        }
        
        logger.info(f"✅ {self.name} 初始化完成，纯Agent架构")
    
    async def process_chat(self, request: ChatRequest) -> ChatResponse:
        """处理对话请求"""
        start_time = time.time()
        
        try:
            # 1. 分析用户意图
            intent = self._analyze_intent(request.message)
            
            # 2. 分析风险等级
            risk = self._analyze_risk(request.message)
            
            # 3. 确定对话策略
            strategy = self._determine_strategy(intent, risk)
            
            # 4. 分析情绪（如果启用）
            emotion = None
            if request.enable_emotion:
                emotion = self._analyze_emotion(request.message)
            
            # 5. 构建对话上下文
            context = self._build_context(request, strategy)
            
            # 6. 调用LLM生成回复
            ai_response = await self._generate_ai_response(context, request.client_type)
            
            # 7. 将AI回复添加到上下文
            if ai_response:
                context.append({"role": "assistant", "content": ai_response})
            
            # 8. 构建响应
            processing_time = int((time.time() - start_time) * 1000)
            
            response = ChatResponse(
                conversation_context=context,
                strategy=strategy,
                risk_level=risk["level"],
                emotion_analysis=emotion,
                processing_time_ms=processing_time,
                metadata={
                    "agent_name": self.name,
                    "mode": request.mode.value,
                    "intent": intent,
                    "risk_details": risk
                }
            )
            
            logger.info(f"✅ {self.name} 处理完成: strategy={strategy.value}, risk={risk['level']}, time={processing_time}ms")
            return response
            
        except Exception as e:
            logger.error(f"❌ {self.name} 处理失败: {e}")
            # 返回安全的默认响应
            return ChatResponse(
                conversation_context=[
                    {"role": "system", "content": "你是一个友善的AI助手。"},
                    {"role": "user", "content": request.message}
                ],
                strategy=ConversationStrategy.CASUAL,
                risk_level=0,
                processing_time_ms=int((time.time() - start_time) * 1000),
                metadata={"error": str(e)}
            )
    
    def _analyze_intent(self, message: str) -> Dict[str, Any]:
        """分析用户意图"""
        # 知识查询关键词
        knowledge_keywords = ["是谁", "什么", "为什么", "怎么", "如何", "告诉我", "解释", "介绍", "定义"]
        is_knowledge = any(keyword in message for keyword in knowledge_keywords)
        
        # 情绪表达关键词
        negative_emotions = ["难过", "伤心", "痛苦", "焦虑", "害怕", "愤怒", "绝望", "孤独", "沮丧", "失望"]
        positive_emotions = ["开心", "高兴", "兴奋", "满足", "感激", "幸福", "快乐", "激动", "愉快"]
        
        has_negative = any(emotion in message for emotion in negative_emotions)
        has_positive = any(emotion in message for emotion in positive_emotions)
        
        return {
            "is_knowledge_query": is_knowledge,
            "has_negative_emotion": has_negative,
            "has_positive_emotion": has_positive,
            "message_length": len(message),
            "complexity": "complex" if len(message) > 50 else "simple"
        }
    
    def _analyze_risk(self, message: str) -> Dict[str, Any]:
        """分析风险等级"""
        # 高风险关键词
        high_risk_keywords = ["不想活", "想死", "自杀", "结束生命", "撑不住", "崩溃", "想要死", "活着没意思"]
        
        # 中等风险关键词
        medium_risk_keywords = ["压力很大", "很累", "想逃避", "没有希望", "很痛苦", "受不了", "太难了"]
        
        high_count = sum(1 for keyword in high_risk_keywords if keyword in message)
        medium_count = sum(1 for keyword in medium_risk_keywords if keyword in message)
        
        if high_count > 0:
            level, severity = 3, "high"
        elif medium_count > 0:
            level, severity = 2, "medium"
        else:
            level, severity = 0, "none"
        
        return {
            "level": level,
            "severity": severity,
            "high_risk_matches": high_count,
            "medium_risk_matches": medium_count,
            "keywords_matched": high_count + medium_count
        }
    
    def _determine_strategy(self, intent: Dict, risk: Dict) -> ConversationStrategy:
        """确定对话策略"""
        # 风险优先处理
        if risk["level"] >= 2:
            return ConversationStrategy.CRISIS
        
        # 负面情绪需要共情
        if intent["has_negative_emotion"]:
            return ConversationStrategy.EMPATHY
        
        # 知识查询
        if intent["is_knowledge_query"]:
            return ConversationStrategy.KNOWLEDGE
        
        # 积极情绪保持轻松
        if intent["has_positive_emotion"]:
            return ConversationStrategy.CASUAL
        
        # 复杂消息可能需要引导
        if intent["complexity"] == "complex":
            return ConversationStrategy.GUIDANCE
        
        # 默认策略
        return ConversationStrategy.CASUAL
    
    def _analyze_emotion(self, message: str) -> Dict[str, Any]:
        """分析情绪"""
        emotions = {
            "joy": ["开心", "高兴", "快乐", "兴奋", "满足", "幸福", "愉快", "激动"],
            "sadness": ["难过", "伤心", "痛苦", "失落", "沮丧", "失望", "悲伤"],
            "anger": ["愤怒", "生气", "恼火", "烦躁", "气愤", "恼怒"],
            "fear": ["害怕", "恐惧", "担心", "焦虑", "紧张", "不安"],
            "surprise": ["惊讶", "意外", "震惊", "吃惊"]
        }
        
        detected = []
        for emotion, keywords in emotions.items():
            if any(keyword in message for keyword in keywords):
                detected.append(emotion)
        
        if detected:
            primary = detected[0]
            intensity = min(len(detected) / len(emotions), 1.0)
        else:
            primary = "neutral"
            intensity = 0.0
        
        return {
            "primary_emotion": primary,
            "intensity": intensity,
            "detected_emotions": detected,
            "confidence": 0.8 if detected else 0.1
        }
    
    def _build_context(self, request: ChatRequest, strategy: ConversationStrategy) -> List[Dict[str, str]]:
        """构建对话上下文"""
        # 基础系统提示词
        base_prompt = "你是一个温暖、理解、专业的AI陪伴者。"
        
        # 策略相关提示词
        strategy_prompt = self.strategy_prompts.get(strategy, "")
        
        # 模式相关提示词
        mode_prompts = {
            AgentMode.TREE_HOLE: "这是一个安全的树洞空间，用户可以自由表达，请保护隐私。",
            AgentMode.PARENT_VIEW: "请从家长的角度提供建议和支持。",
            AgentMode.SCHOOL_VIEW: "请从教育的角度提供指导和帮助。"
        }
        
        mode_prompt = mode_prompts.get(request.mode, "")
        
        # 组合所有提示词
        prompts = [p for p in [base_prompt, strategy_prompt, mode_prompt, request.system_prompt] if p]
        system_prompt = "\n\n".join(prompts)
        
        # 构建对话上下文
        context = [{"role": "system", "content": system_prompt}]
        
        # 添加历史消息（限制数量避免上下文过长）
        if request.history:
            max_history = 10
            recent_history = request.history[-max_history:]
            for msg in recent_history:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    context.append(msg)
        
        # 添加当前用户消息
        context.append({"role": "user", "content": request.message})
        
        return context
    
    async def _generate_ai_response(self, context: List[Dict[str, str]], client_type: str = 'system') -> str:
        """调用LLM生成AI回复"""
        try:
            # 导入LLM服务
            from app.shared.services.llm_service import get_llm_service
            
            llm_service = get_llm_service()
            
            # 调用LLM生成回复，传递client_type用于统计和并发控制
            response = await llm_service.chat_async(
                messages=context,
                temperature=0.7,
                client_type=client_type
            )
            
            return response.strip() if response else None
            
        except Exception as e:
            logger.error(f"LLM生成回复失败 (client={client_type}): {e}")
            # 返回默认回复
            return "抱歉，我现在无法回复，请稍后再试。"


# -------------------------------------------------------
# 全局实例管理
# -------------------------------------------------------

_pure_chat_agent = None


def get_chat_agent() -> PureChatAgent:
    """获取纯Agent实例（替代原有的get_chat_agent）"""
    global _pure_chat_agent
    if _pure_chat_agent is None:
        _pure_chat_agent = PureChatAgent()
    return _pure_chat_agent


# -------------------------------------------------------
# 现代化异步接口
# -------------------------------------------------------

async def chat_with_agent(
    user_id: str,
    message: str,
    history: List[Dict[str, str]] = None,
    mode: AgentMode = AgentMode.NORMAL,
    system_prompt: Optional[str] = None,
    enable_emotion: bool = True,
    enable_risk: bool = True
) -> ChatResponse:
    """
    主要对话接口（替代所有Service调用）
    
    Args:
        user_id: 用户ID
        message: 用户消息
        history: 对话历史 [{"role": "user", "content": "..."}]
        mode: Agent模式
        system_prompt: 自定义系统提示词
        enable_emotion: 是否启用情绪分析
        enable_risk: 是否启用风险检测
    
    Returns:
        ChatResponse: 完整的对话响应
    """
    request = ChatRequest(
        user_id=user_id,
        message=message,
        history=history or [],
        mode=mode,
        system_prompt=system_prompt,
        enable_emotion=enable_emotion,
        enable_risk=enable_risk
    )
    
    agent = get_chat_agent()
    return await agent.process_chat(request)


async def quick_chat(user_id: str, message: str) -> List[Dict[str, str]]:
    """快速对话（仅返回上下文）"""
    response = await chat_with_agent(user_id, message)
    return response.conversation_context


async def empathy_chat(user_id: str, message: str, history: List[Dict[str, str]] = None) -> ChatResponse:
    """共情对话"""
    return await chat_with_agent(
        user_id=user_id,
        message=message,
        history=history,
        system_prompt="请特别关注用户的情感需求，提供温暖的理解和支持。",
        enable_emotion=True
    )


async def crisis_chat(user_id: str, message: str, history: List[Dict[str, str]] = None) -> ChatResponse:
    """危机干预对话"""
    return await chat_with_agent(
        user_id=user_id,
        message=message,
        history=history,
        system_prompt="用户可能处于心理危机中，请提供专业的心理支持和安全建议。如有必要，建议寻求专业帮助。",
        enable_risk=True
    )


async def knowledge_chat(user_id: str, message: str, history: List[Dict[str, str]] = None) -> ChatResponse:
    """知识问答对话"""
    return await chat_with_agent(
        user_id=user_id,
        message=message,
        history=history,
        system_prompt="请提供准确、详细的知识解答，帮助用户学习和理解。"
    )


async def tree_hole_chat(user_id: str, message: str) -> ChatResponse:
    """树洞模式对话"""
    return await chat_with_agent(
        user_id=user_id,
        message=message,
        mode=AgentMode.TREE_HOLE,
        system_prompt="这是一个安全的树洞空间，用户可以自由表达，请保护隐私，不会记录任何信息。"
    )


# -------------------------------------------------------
# 兼容性接口（用于平滑迁移）
# -------------------------------------------------------

async def intelligent_chat_process(
    user_id: str,
    user_message: str,
    history: List = None,
    mode: AgentMode = AgentMode.NORMAL
) -> Dict[str, Any]:
    """
    兼容性接口：模拟原有的intelligent_chat_process
    """
    # 转换历史消息格式
    converted_history = []
    if history:
        for msg in history:
            if hasattr(msg, 'to_llm_format'):
                converted_history.append(msg.to_llm_format())
            elif isinstance(msg, dict):
                converted_history.append(msg)
    
    response = await chat_with_agent(
        user_id=user_id,
        message=user_message,
        history=converted_history,
        mode=mode
    )
    
    # 转换为原有格式
    return {
        "conversation_context": response.conversation_context,
        "conversation_strategy": response.strategy.value,
        "risk_level": response.risk_level,
        "emotion_analysis": response.emotion_analysis,
        "processing_time_ms": response.processing_time_ms,
        "agent_metadata": response.metadata
    }


def build_conversation_context(
    system_prompt: str,
    history: List,
    current_message: str
) -> List[Dict[str, str]]:
    """
    兼容性接口：模拟原有的build_conversation_context
    """
    context = [{"role": "system", "content": system_prompt}]
    
    # 添加历史消息
    if history:
        for msg in history[-10:]:  # 限制历史数量
            if hasattr(msg, 'to_llm_format'):
                context.append(msg.to_llm_format())
            elif isinstance(msg, dict):
                context.append(msg)
    
    # 添加当前消息
    context.append({"role": "user", "content": current_message})
    
    return context


def process_user_input(content: str) -> str:
    """
    兼容性接口：模拟原有的process_user_input
    """
    # 基础处理
    content = content.strip()
    
    # 长度限制
    max_length = 2000
    if len(content) > max_length:
        content = content[:max_length]
        logger.warning(f"用户输入过长，已截断至 {max_length} 字符")
    
    return content


def should_inject_knowledge(content: str) -> bool:
    """
    兼容性接口：模拟原有的should_inject_knowledge
    """
    knowledge_keywords = ["是谁", "什么", "为什么", "怎么", "如何", "告诉我", "解释", "介绍"]
    return any(keyword in content for keyword in knowledge_keywords)


# -------------------------------------------------------
# 批量处理
# -------------------------------------------------------

async def batch_chat(requests: List[ChatRequest]) -> List[ChatResponse]:
    """批量对话处理"""
    agent = get_chat_agent()
    tasks = [agent.process_chat(req) for req in requests]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理异常结果
    responses = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"批量处理第{i}个请求失败: {result}")
            # 创建错误响应
            error_response = ChatResponse(
                conversation_context=[{"role": "system", "content": "处理失败，请重试"}],
                strategy=ConversationStrategy.CASUAL,
                risk_level=0,
                processing_time_ms=0,
                metadata={"error": str(result)}
            )
            responses.append(error_response)
        else:
            responses.append(result)
    
    return responses
