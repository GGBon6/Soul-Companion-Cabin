"""
青少年心理对话意图识别服务
Youth Psychology Intent Recognition Service
专门为青少年心理对话场景设计的意图识别服务
基于LLM的智能意图分析，支持心理健康相关的多种意图类型
"""

import json
import time
import hashlib
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
import logging

from app.shared.services.llm_service import get_llm_service
from app.devices.config.youth_psychology_config import get_youth_psychology_config
from app.core import settings


class PsychologyIntentType(Enum):
    """青少年心理对话意图类型"""
    
    # 基础对话意图
    GREETING = "greeting"                   # 问候
    CASUAL_CHAT = "casual_chat"            # 日常闲聊
    FAREWELL = "farewell"                  # 告别
    
    # 心理健康相关意图
    EMOTIONAL_SUPPORT = "emotional_support"     # 情感支持需求
    STRESS_RELIEF = "stress_relief"            # 压力缓解
    ANXIETY_HELP = "anxiety_help"              # 焦虑帮助
    DEPRESSION_SUPPORT = "depression_support"   # 抑郁支持
    SELF_HARM_CRISIS = "self_harm_crisis"      # 自伤危机 (高优先级)
    SUICIDE_CRISIS = "suicide_crisis"          # 自杀危机 (紧急)
    
    # 学习和成长相关
    STUDY_PRESSURE = "study_pressure"          # 学习压力
    EXAM_ANXIETY = "exam_anxiety"              # 考试焦虑
    CAREER_GUIDANCE = "career_guidance"        # 职业指导
    GOAL_SETTING = "goal_setting"              # 目标设定
    
    # 人际关系相关
    FAMILY_ISSUES = "family_issues"            # 家庭问题
    FRIENDSHIP_TROUBLES = "friendship_troubles" # 友谊困扰
    ROMANTIC_CONCERNS = "romantic_concerns"     # 恋爱关系
    SOCIAL_ANXIETY = "social_anxiety"          # 社交焦虑
    BULLYING_ISSUES = "bullying_issues"        # 霸凌问题
    
    # 自我认知和发展
    IDENTITY_EXPLORATION = "identity_exploration" # 身份探索
    SELF_ESTEEM = "self_esteem"                # 自尊问题
    BODY_IMAGE = "body_image"                  # 身体形象
    CONFIDENCE_BUILDING = "confidence_building" # 自信建立
    
    # 生活技能和习惯
    TIME_MANAGEMENT = "time_management"        # 时间管理
    SLEEP_ISSUES = "sleep_issues"              # 睡眠问题
    HEALTHY_HABITS = "healthy_habits"          # 健康习惯
    DIGITAL_WELLNESS = "digital_wellness"     # 数字健康
    
    # 功能性意图
    RESOURCE_REQUEST = "resource_request"      # 资源请求
    PROFESSIONAL_REFERRAL = "professional_referral" # 专业转介
    CRISIS_INTERVENTION = "crisis_intervention" # 危机干预
    
    # 其他
    UNKNOWN = "unknown"                        # 未知意图
    INAPPROPRIATE = "inappropriate"            # 不当内容


class IntentPriority(Enum):
    """意图优先级"""
    EMERGENCY = "emergency"     # 紧急 (自杀、自伤)
    HIGH = "high"              # 高 (危机干预)
    MEDIUM = "medium"          # 中 (心理支持)
    LOW = "low"               # 低 (日常对话)


@dataclass
class IntentAnalysisResult:
    """意图分析结果"""
    primary_intent: PsychologyIntentType    # 主要意图
    secondary_intents: List[PsychologyIntentType] = None  # 次要意图
    confidence: float = 0.0                 # 置信度 (0.0-1.0)
    priority: IntentPriority = IntentPriority.LOW  # 优先级
    
    # 情感分析
    emotional_state: Optional[str] = None   # 情感状态
    emotional_intensity: float = 0.0        # 情感强度 (0.0-1.0)
    
    # 风险评估
    risk_level: str = "low"                # 风险等级 (low/medium/high/critical)
    risk_factors: List[str] = None         # 风险因素
    
    # 响应建议
    response_strategy: str = "supportive"   # 响应策略
    suggested_resources: List[str] = None   # 建议资源
    
    # 元数据
    processing_time: float = 0.0           # 处理时间
    model_version: str = ""                # 模型版本
    metadata: Dict[str, Any] = None        # 其他元数据


class YouthPsychologyIntentService:
    """青少年心理对话意图识别服务"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.llm_service = None  # 延迟初始化
        self.config = get_youth_psychology_config()
        
        # 从配置加载参数
        self.max_history_length = self.config.get_max_history_length()
        self.confidence_threshold = self.config.get_emotional_intensity_threshold()
        self.cache_ttl = self.config.get_cache_ttl()
        self.enable_cache = self.config.is_cache_enabled()
        self.enable_crisis_detection = self.config.is_crisis_detection_enabled()
        self.crisis_sensitivity = self.config.get_crisis_sensitivity()
        
        # 缓存
        self._intent_cache: Dict[str, IntentAnalysisResult] = {}
        
        # 危机关键词 (用于快速检测)
        self.crisis_keywords = {
            "suicide": ["自杀", "想死", "不想活", "结束生命", "了结", "suicide", "kill myself"],
            "self_harm": ["自伤", "自残", "割腕", "伤害自己", "self harm", "cut myself"],
            "severe_depression": ["绝望", "无助", "没有希望", "活着没意思", "痛苦不堪"],
            "abuse": ["被打", "家暴", "性侵", "虐待", "被欺负", "霸凌"]
        }
        
        # 意图关键词映射
        self.intent_keywords = {
            PsychologyIntentType.STRESS_RELIEF: ["压力", "紧张", "焦虑", "烦躁", "压抑"],
            PsychologyIntentType.STUDY_PRESSURE: ["学习", "考试", "成绩", "作业", "升学"],
            PsychologyIntentType.FAMILY_ISSUES: ["父母", "家人", "家庭", "爸爸", "妈妈"],
            PsychologyIntentType.FRIENDSHIP_TROUBLES: ["朋友", "同学", "友谊", "孤独", "被排斥"],
            PsychologyIntentType.SELF_ESTEEM: ["自信", "自卑", "不够好", "失败", "自我价值"],
            PsychologyIntentType.SLEEP_ISSUES: ["睡眠", "失眠", "睡不着", "熬夜", "疲惫"]
        }
        
        self.logger.info("青少年心理对话意图识别服务初始化完成")
    
    async def _ensure_llm_service_initialized(self):
        """确保LLM服务已初始化"""
        if self.llm_service is None:
            try:
                from app.core.application import get_app
                try:
                    app = get_app()
                    self.llm_service = await app.get_llm_service('esp32')
                except RuntimeError:
                    # 应用未初始化，降级到同步方式
                    self.llm_service = get_llm_service()
            except Exception as e:
                self.logger.warning(f"LLM服务初始化失败，将在需要时重试: {e}")
                # 降级到同步方式
                self.llm_service = get_llm_service()
    
    async def analyze_intent(self, 
                           user_text: str, 
                           dialogue_history: List[Dict] = None,
                           user_profile: Dict = None) -> IntentAnalysisResult:
        """
        分析用户意图
        
        Args:
            user_text: 用户输入文本
            dialogue_history: 对话历史
            user_profile: 用户档案
            
        Returns:
            IntentAnalysisResult: 意图分析结果
        """
        start_time = time.time()
        
        # 确保LLM服务已初始化
        await self._ensure_llm_service_initialized()
        
        try:
            # 检查缓存
            cache_key = self._generate_cache_key(user_text, dialogue_history)
            if cache_key in self._intent_cache:
                cached_result = self._intent_cache[cache_key]
                if time.time() - cached_result.metadata.get("timestamp", 0) < self.cache_ttl:
                    self.logger.debug("使用缓存的意图分析结果")
                    return cached_result
            
            # 快速危机检测
            crisis_result = self._quick_crisis_detection(user_text)
            if crisis_result:
                self.logger.warning(f"检测到危机意图: {crisis_result.primary_intent.value}")
                return crisis_result
            
            # 使用LLM进行深度意图分析
            llm_result = await self._analyze_with_llm(user_text, dialogue_history, user_profile)
            
            processing_time = time.time() - start_time
            llm_result.processing_time = processing_time
            
            # 缓存结果
            llm_result.metadata = llm_result.metadata or {}
            llm_result.metadata["timestamp"] = time.time()
            self._intent_cache[cache_key] = llm_result
            
            self.logger.info(f"意图分析完成: {llm_result.primary_intent.value}, "
                           f"置信度: {llm_result.confidence:.2f}, "
                           f"耗时: {processing_time*1000:.1f}ms")
            
            return llm_result
            
        except Exception as e:
            self.logger.error(f"意图分析失败: {e}", exc_info=True)
            return self._create_fallback_result(user_text, time.time() - start_time)
    
    def _quick_crisis_detection(self, text: str) -> Optional[IntentAnalysisResult]:
        """
        快速危机检测
        
        Args:
            text: 用户文本
            
        Returns:
            Optional[IntentAnalysisResult]: 如果检测到危机则返回结果
        """
        text_lower = text.lower()
        
        # 检查自杀意图
        for keyword in self.crisis_keywords["suicide"]:
            if keyword in text_lower:
                return IntentAnalysisResult(
                    primary_intent=PsychologyIntentType.SUICIDE_CRISIS,
                    confidence=0.95,
                    priority=IntentPriority.EMERGENCY,
                    emotional_state="极度痛苦",
                    emotional_intensity=0.9,
                    risk_level="critical",
                    risk_factors=["自杀倾向"],
                    response_strategy="crisis_intervention",
                    suggested_resources=["紧急心理热线", "专业心理医生", "危机干预中心"],
                    metadata={"detection_method": "keyword_match", "crisis_type": "suicide"}
                )
        
        # 检查自伤意图
        for keyword in self.crisis_keywords["self_harm"]:
            if keyword in text_lower:
                return IntentAnalysisResult(
                    primary_intent=PsychologyIntentType.SELF_HARM_CRISIS,
                    confidence=0.9,
                    priority=IntentPriority.HIGH,
                    emotional_state="痛苦",
                    emotional_intensity=0.8,
                    risk_level="high",
                    risk_factors=["自伤行为"],
                    response_strategy="crisis_intervention",
                    suggested_resources=["心理热线", "心理咨询师"],
                    metadata={"detection_method": "keyword_match", "crisis_type": "self_harm"}
                )
        
        return None
    
    async def _analyze_with_llm(self, 
                               user_text: str, 
                               dialogue_history: List[Dict] = None,
                               user_profile: Dict = None) -> IntentAnalysisResult:
        """
        使用LLM进行深度意图分析
        
        Args:
            user_text: 用户文本
            dialogue_history: 对话历史
            user_profile: 用户档案
            
        Returns:
            IntentAnalysisResult: 分析结果
        """
        # 构建分析提示
        system_prompt = self._build_analysis_prompt()
        
        # 构建上下文
        context_info = self._build_context_info(dialogue_history, user_profile)
        
        # 构建用户消息
        user_message = f"""
请分析以下青少年用户的话语意图：

用户输入: "{user_text}"

{context_info}

请按照JSON格式返回分析结果。
"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        try:
            # 调用LLM
            response = await self.llm_service.chat_async(messages, temperature=0.3)
            
            if not response:
                return self._create_fallback_result(user_text, 0.0)
            
            # 解析LLM响应
            return self._parse_llm_response(response, user_text)
            
        except Exception as e:
            self.logger.error(f"LLM意图分析失败: {e}")
            return self._create_fallback_result(user_text, 0.0)
    
    def _build_analysis_prompt(self) -> str:
        """构建意图分析提示"""
        intent_descriptions = {
            "greeting": "问候、打招呼",
            "casual_chat": "日常闲聊、轻松话题",
            "farewell": "告别、结束对话",
            "emotional_support": "需要情感支持、安慰",
            "stress_relief": "压力缓解、放松需求",
            "anxiety_help": "焦虑帮助、担心害怕",
            "depression_support": "抑郁支持、情绪低落",
            "study_pressure": "学习压力、学业困扰",
            "exam_anxiety": "考试焦虑、考试压力",
            "family_issues": "家庭问题、亲子关系",
            "friendship_troubles": "友谊困扰、人际关系",
            "self_esteem": "自尊问题、自信不足",
            "sleep_issues": "睡眠问题、失眠困扰",
            "crisis_intervention": "危机干预、紧急情况"
        }
        
        intent_list = "\n".join([f"- {key}: {desc}" for key, desc in intent_descriptions.items()])
        
        return f"""你是一个专业的青少年心理健康意图识别专家。你需要分析青少年用户的话语，识别其真实意图和情感需求。

支持的意图类型：
{intent_list}

分析维度：
1. 主要意图：用户的核心需求
2. 情感状态：用户当前的情感状态
3. 情感强度：情感的强烈程度 (0.0-1.0)
4. 风险等级：心理健康风险 (low/medium/high/critical)
5. 响应策略：建议的回应方式

请返回JSON格式：
{{
    "primary_intent": "意图类型",
    "confidence": 0.8,
    "emotional_state": "情感状态描述",
    "emotional_intensity": 0.6,
    "risk_level": "风险等级",
    "risk_factors": ["风险因素列表"],
    "response_strategy": "响应策略",
    "suggested_resources": ["建议资源列表"],
    "analysis_reasoning": "分析推理过程"
}}

注意：
- 对于危机情况（自杀、自伤）要特别敏感
- 考虑青少年的心理发展特点
- 关注隐含的求助信号
- 提供温暖、专业的分析"""
    
    def _build_context_info(self, 
                           dialogue_history: List[Dict] = None, 
                           user_profile: Dict = None) -> str:
        """构建上下文信息"""
        context_parts = []
        
        # 添加对话历史
        if dialogue_history:
            recent_history = dialogue_history[-self.max_history_length:]
            history_text = "\n".join([
                f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                for msg in recent_history
            ])
            context_parts.append(f"对话历史：\n{history_text}")
        
        # 添加用户档案
        if user_profile:
            profile_info = []
            if user_profile.get("age"):
                profile_info.append(f"年龄: {user_profile['age']}")
            if user_profile.get("grade"):
                profile_info.append(f"年级: {user_profile['grade']}")
            if user_profile.get("concerns"):
                profile_info.append(f"关注问题: {', '.join(user_profile['concerns'])}")
            
            if profile_info:
                context_parts.append(f"用户信息：{', '.join(profile_info)}")
        
        return "\n\n".join(context_parts) if context_parts else "无额外上下文信息"
    
    def _parse_llm_response(self, response: str, user_text: str) -> IntentAnalysisResult:
        """解析LLM响应"""
        try:
            # 尝试解析JSON
            result_data = json.loads(response)
            
            # 解析主要意图
            primary_intent_str = result_data.get("primary_intent", "unknown")
            try:
                primary_intent = PsychologyIntentType(primary_intent_str)
            except ValueError:
                primary_intent = PsychologyIntentType.UNKNOWN
            
            # 确定优先级
            priority = self._determine_priority(primary_intent, result_data.get("risk_level", "low"))
            
            return IntentAnalysisResult(
                primary_intent=primary_intent,
                confidence=float(result_data.get("confidence", 0.5)),
                priority=priority,
                emotional_state=result_data.get("emotional_state"),
                emotional_intensity=float(result_data.get("emotional_intensity", 0.0)),
                risk_level=result_data.get("risk_level", "low"),
                risk_factors=result_data.get("risk_factors", []),
                response_strategy=result_data.get("response_strategy", "supportive"),
                suggested_resources=result_data.get("suggested_resources", []),
                metadata={
                    "analysis_reasoning": result_data.get("analysis_reasoning", ""),
                    "llm_response": response
                }
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.error(f"解析LLM响应失败: {e}")
            return self._create_fallback_result(user_text, 0.0)
    
    def _determine_priority(self, intent: PsychologyIntentType, risk_level: str) -> IntentPriority:
        """确定意图优先级"""
        if intent in [PsychologyIntentType.SUICIDE_CRISIS]:
            return IntentPriority.EMERGENCY
        elif intent in [PsychologyIntentType.SELF_HARM_CRISIS, PsychologyIntentType.CRISIS_INTERVENTION]:
            return IntentPriority.HIGH
        elif risk_level == "critical":
            return IntentPriority.EMERGENCY
        elif risk_level == "high":
            return IntentPriority.HIGH
        elif intent in [PsychologyIntentType.EMOTIONAL_SUPPORT, PsychologyIntentType.DEPRESSION_SUPPORT]:
            return IntentPriority.MEDIUM
        else:
            return IntentPriority.LOW
    
    def _create_fallback_result(self, user_text: str, processing_time: float) -> IntentAnalysisResult:
        """创建降级结果"""
        # 基于关键词的简单意图识别
        text_lower = user_text.lower()
        
        for intent_type, keywords in self.intent_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return IntentAnalysisResult(
                        primary_intent=intent_type,
                        confidence=0.6,
                        priority=IntentPriority.MEDIUM,
                        emotional_state="需要关注",
                        emotional_intensity=0.5,
                        risk_level="medium",
                        response_strategy="supportive",
                        processing_time=processing_time,
                        metadata={"fallback": True, "method": "keyword_match"}
                    )
        
        # 默认结果
        return IntentAnalysisResult(
            primary_intent=PsychologyIntentType.CASUAL_CHAT,
            confidence=0.3,
            priority=IntentPriority.LOW,
            emotional_state="平静",
            emotional_intensity=0.2,
            risk_level="low",
            response_strategy="casual",
            processing_time=processing_time,
            metadata={"fallback": True, "method": "default"}
        )
    
    def _generate_cache_key(self, user_text: str, dialogue_history: List[Dict] = None) -> str:
        """生成缓存键"""
        content = user_text
        if dialogue_history:
            # 只考虑最近的对话
            recent_history = dialogue_history[-2:] if len(dialogue_history) > 2 else dialogue_history
            history_content = json.dumps(recent_history, sort_keys=True)
            content += history_content
        
        return hashlib.md5(content.encode()).hexdigest()
    
    def get_intent_statistics(self) -> Dict[str, Any]:
        """获取意图识别统计"""
        return {
            "cache_size": len(self._intent_cache),
            "supported_intents": len(PsychologyIntentType),
            "crisis_keywords_count": sum(len(keywords) for keywords in self.crisis_keywords.values()),
            "service_status": "active"
        }
    
    def clear_cache(self) -> None:
        """清空缓存"""
        cache_size = len(self._intent_cache)
        self._intent_cache.clear()
        self.logger.info(f"已清空意图识别缓存: {cache_size}个条目")


# 全局服务实例
_intent_service: Optional[YouthPsychologyIntentService] = None


def get_youth_psychology_intent_service() -> YouthPsychologyIntentService:
    """获取青少年心理意图识别服务实例"""
    global _intent_service
    if _intent_service is None:
        _intent_service = YouthPsychologyIntentService()
    return _intent_service


# 为了兼容现有代码，提供简化接口
async def analyze_youth_intent(user_text: str, 
                              dialogue_history: List[Dict] = None,
                              user_profile: Dict = None) -> IntentAnalysisResult:
    """
    分析青少年心理对话意图的便捷函数
    
    Args:
        user_text: 用户输入文本
        dialogue_history: 对话历史
        user_profile: 用户档案
        
    Returns:
        IntentAnalysisResult: 意图分析结果
    """
    service = get_youth_psychology_intent_service()
    return await service.analyze_intent(user_text, dialogue_history, user_profile)
