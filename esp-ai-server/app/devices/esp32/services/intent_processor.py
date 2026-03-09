"""
ESP32意图处理器
ESP32 Intent Processor
参考core/handle/intentHandler.py的设计模式，实现模块化的意图处理系统
集成LLM服务、对话管理和功能调用路由
"""

import asyncio
import json
import uuid
import time
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
import logging

from app.shared.services.llm_service import get_llm_service
from app.shared.services.chat_history_service import get_chat_history_service
from app.shared.services.intent_recognition_service import get_youth_psychology_intent_service


class IntentType(Enum):
    """意图类型"""
    CHAT = "chat"                       # 普通对话
    FUNCTION_CALL = "function_call"     # 功能调用
    CONTEXT_QUERY = "context_query"     # 上下文查询
    EXIT_COMMAND = "exit_command"       # 退出命令
    WAKEUP_WORD = "wakeup_word"        # 唤醒词
    UNKNOWN = "unknown"                 # 未知意图


class ProcessingStatus(Enum):
    """处理状态"""
    SUCCESS = "success"                 # 成功
    FAILED = "failed"                   # 失败
    TIMEOUT = "timeout"                 # 超时
    INTERRUPTED = "interrupted"         # 中断
    SKIPPED = "skipped"                # 跳过


@dataclass
class IntentRequest:
    """意图处理请求"""
    user_text: str                      # 用户输入文本
    device_id: str                      # 设备ID
    session_id: str                     # 会话ID
    user_id: Optional[str] = None       # 用户ID
    dialogue_history: List[Dict] = None # 对话历史
    metadata: Dict[str, Any] = None     # 元数据


@dataclass
class IntentResult:
    """意图处理结果"""
    request: IntentRequest              # 原始请求
    intent_type: IntentType             # 识别的意图类型
    response_text: str                  # 回复文本
    processing_status: ProcessingStatus # 处理状态
    processing_time: float              # 处理时间（秒）
    confidence: float                   # 置信度 (0.0-1.0)
    
    # 功能调用相关
    function_name: Optional[str] = None # 功能名称
    function_args: Optional[Dict] = None # 功能参数
    function_result: Optional[str] = None # 功能执行结果
    
    # 错误信息
    error_message: Optional[str] = None # 错误信息
    
    # 元数据
    sentence_id: Optional[str] = None   # 句子ID
    metadata: Dict[str, Any] = None     # 元数据


@dataclass
class IntentStatistics:
    """意图处理统计"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # 按意图类型统计
    chat_count: int = 0
    function_call_count: int = 0
    context_query_count: int = 0
    exit_command_count: int = 0
    wakeup_word_count: int = 0
    unknown_count: int = 0
    
    total_processing_time: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def avg_processing_time(self) -> float:
        """平均处理时间"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_processing_time / self.successful_requests


class ESP32IntentProcessor:
    """ESP32意图处理器"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.tag = f"ESP32Intent[{device_id}]"
        self.logger = logging.getLogger(__name__)
        
        # 服务实例（延迟初始化）
        self.llm_service = None
        self.chat_history_service = get_chat_history_service()
        self.youth_intent_service = get_youth_psychology_intent_service()
        
        # 配置参数
        self.max_processing_time = 30.0    # 最大处理时间
        self.min_confidence = 0.6          # 最小置信度
        self.max_dialogue_history = 10     # 最大对话历史条数
        
        # 退出命令列表
        self.exit_commands = [
            "退出", "结束", "再见", "拜拜", "停止", "关闭",
            "exit", "quit", "bye", "goodbye", "stop", "close"
        ]
        
        # 唤醒词列表
        self.wakeup_words = [
            "小助手", "你好", "在吗", "听我说",
            "hello", "hi", "hey"
        ]
        
        # 统计信息
        self.statistics = IntentStatistics()
        
        # 回调函数
        self._result_callbacks: List[Callable[[IntentResult], None]] = []
        
        self.logger.info(f"[{self.tag}] 意图处理器初始化完成")
    
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
                self.logger.warning(f"[{self.tag}] LLM服务初始化失败，将在需要时重试: {e}")
                # 降级到同步方式
                self.llm_service = get_llm_service()
    
    def add_result_callback(self, callback: Callable[[IntentResult], None]) -> None:
        """添加结果回调"""
        self._result_callbacks.append(callback)
    
    async def process_intent(self, request: IntentRequest) -> IntentResult:
        """
        处理用户意图
        
        Args:
            request: 意图处理请求
            
        Returns:
            IntentResult: 处理结果
        """
        start_time = time.time()
        self.statistics.total_requests += 1
        
        # 确保LLM服务已初始化
        await self._ensure_llm_service_initialized()
        
        # 生成句子ID
        sentence_id = str(uuid.uuid4().hex)
        
        try:
            self.logger.info(f"[{self.tag}] 开始意图处理: '{request.user_text[:50]}...'")
            
            # 预处理输入文本
            processed_text = self._preprocess_text(request.user_text)
            
            # 检查退出命令
            if self._check_exit_command(processed_text):
                return self._create_exit_result(request, sentence_id, start_time)
            
            # 检查唤醒词
            if self._check_wakeup_word(processed_text):
                return self._create_wakeup_result(request, sentence_id, start_time)
            
            # 获取对话历史
            dialogue_history = await self._get_dialogue_history(request)
            
            # 使用LLM进行意图分析
            intent_analysis = await self._analyze_intent_with_llm(request, dialogue_history)
            
            if not intent_analysis:
                return self._create_error_result(request, sentence_id, start_time, "意图分析失败")
            
            # 处理意图分析结果
            result = await self._process_intent_analysis(request, intent_analysis, dialogue_history, sentence_id, start_time)
            
            # 保存对话历史
            await self._save_dialogue_history(request, result)
            
            # 触发回调
            for callback in self._result_callbacks:
                try:
                    callback(result)
                except Exception as e:
                    self.logger.error(f"[{self.tag}] 意图结果回调执行失败: {e}")
            
            return result
            
        except asyncio.TimeoutError:
            self.statistics.failed_requests += 1
            return self._create_timeout_result(request, sentence_id, start_time)
        
        except Exception as e:
            self.logger.error(f"[{self.tag}] 意图处理失败: {e}", exc_info=True)
            self.statistics.failed_requests += 1
            return self._create_error_result(request, sentence_id, start_time, str(e))
    
    def _preprocess_text(self, text: str) -> str:
        """
        预处理输入文本
        
        Args:
            text: 原始文本
            
        Returns:
            str: 处理后的文本
        """
        try:
            # 尝试解析JSON格式
            if text.strip().startswith('{') and text.strip().endswith('}'):
                parsed_data = json.loads(text)
                if isinstance(parsed_data, dict) and "content" in parsed_data:
                    text = parsed_data["content"]
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 去除标点符号和多余空格
        import re
        text = re.sub(r'[^\w\s]', '', text)
        text = ' '.join(text.split())
        
        return text.strip()
    
    def _check_exit_command(self, text: str) -> bool:
        """
        检查是否为退出命令
        
        Args:
            text: 处理后的文本
            
        Returns:
            bool: 是否为退出命令
        """
        text_lower = text.lower()
        for cmd in self.exit_commands:
            if text_lower == cmd.lower():
                self.logger.info(f"[{self.tag}] 识别到退出命令: {text}")
                return True
        return False
    
    def _check_wakeup_word(self, text: str) -> bool:
        """
        检查是否为唤醒词
        
        Args:
            text: 处理后的文本
            
        Returns:
            bool: 是否为唤醒词
        """
        text_lower = text.lower()
        for word in self.wakeup_words:
            if word.lower() in text_lower:
                self.logger.info(f"[{self.tag}] 识别到唤醒词: {text}")
                return True
        return False
    
    async def _get_dialogue_history(self, request: IntentRequest) -> List[Dict]:
        """
        获取对话历史
        
        Args:
            request: 意图请求
            
        Returns:
            List[Dict]: 对话历史
        """
        try:
            if request.dialogue_history:
                return request.dialogue_history[-self.max_dialogue_history:]
            
            # 从数据库获取历史
            if request.user_id:
                history = await self.chat_history_service.get_recent_messages(
                    request.user_id, limit=self.max_dialogue_history
                )
                return [{"role": msg.role, "content": msg.content} for msg in history]
            
            return []
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 获取对话历史失败: {e}")
            return []
    
    async def _analyze_intent_with_llm(self, request: IntentRequest, dialogue_history: List[Dict]) -> Optional[Dict]:
        """
        使用青少年心理意图识别服务分析用户意图
        
        Args:
            request: 意图请求
            dialogue_history: 对话历史
            
        Returns:
            Optional[Dict]: 意图分析结果
        """
        try:
            # 构建用户档案
            user_profile = {
                "device_id": request.device_id,
                "session_id": request.session_id,
                "user_id": request.user_id
            }
            
            self.logger.info(f"[{self.tag}] 🧠 开始LLM意图分析: '{request.user_text}'")
            
            # 调用青少年心理意图识别服务
            intent_result = await self.youth_intent_service.analyze_intent(
                user_text=request.user_text,
                dialogue_history=dialogue_history,
                user_profile=user_profile
            )
            
            if intent_result:
                self.logger.info(f"[{self.tag}] ✅ LLM意图分析完成: 意图={intent_result.primary_intent.value}, 置信度={intent_result.confidence:.2f}")
                self.logger.info(f"[{self.tag}] 🎭 情绪状态: {intent_result.emotional_state}, 强度: {intent_result.emotional_intensity}")
                self.logger.info(f"[{self.tag}] ⚠️ 风险等级: {intent_result.risk_level}")
            else:
                self.logger.warning(f"[{self.tag}] ❌ LLM意图分析失败")
            
            if not intent_result:
                return None
            
            # 转换为兼容格式
            result_dict = {
                "intent_type": self._map_psychology_intent_to_standard(intent_result.primary_intent.value),
                "confidence": intent_result.confidence,
                "emotional_state": intent_result.emotional_state,
                "emotional_intensity": intent_result.emotional_intensity,
                "risk_level": intent_result.risk_level,
                "priority": intent_result.priority.value,
                "response_strategy": intent_result.response_strategy,
                "suggested_resources": intent_result.suggested_resources,
                "psychology_intent": intent_result.primary_intent.value  # 保留原始心理意图
            }
            
            # 根据风险等级和意图类型决定响应方式
            if intent_result.risk_level in ["high", "critical"]:
                # 高风险情况，使用专门的危机干预响应
                self.logger.info(f"[{self.tag}] 🚨 生成危机干预响应")
                result_dict["response"] = self._generate_crisis_response(intent_result)
                result_dict["requires_intervention"] = True
            elif intent_result.primary_intent.value in ["greeting", "farewell", "casual_chat"]:
                # 基础对话，生成友好回复
                self.logger.info(f"[{self.tag}] 😊 生成友好对话响应")
                result_dict["response"] = self._generate_friendly_response(intent_result, request.user_text)
            else:
                # 心理健康相关话题，生成支持性回复
                self.logger.info(f"[{self.tag}] 💝 生成心理支持响应")
                result_dict["response"] = await self._generate_supportive_response(intent_result, request.user_text, dialogue_history)
            
            # 记录生成的回复
            response_preview = result_dict["response"][:50] + "..." if len(result_dict["response"]) > 50 else result_dict["response"]
            self.logger.info(f"[{self.tag}] 💬 AI回复生成: '{response_preview}'")
            
            return result_dict
                
        except Exception as e:
            self.logger.error(f"[{self.tag}] 青少年心理意图分析失败: {e}")
            return None
    
    def _build_system_prompt(self) -> str:
        """
        构建系统提示
        
        Returns:
            str: 系统提示
        """
        return """你是一个智能语音助手，需要分析用户意图并给出合适的回复。

请根据用户输入判断意图类型：
1. chat - 普通对话，直接回复
2. function_call - 需要调用特定功能
3. context_query - 需要上下文信息的查询

如果是function_call，请返回JSON格式：
{
    "intent_type": "function_call",
    "function_call": {
        "name": "函数名",
        "arguments": {"参数": "值"}
    },
    "confidence": 0.9
}

如果是普通对话，请返回JSON格式：
{
    "intent_type": "chat",
    "response": "你的回复内容",
    "confidence": 0.8
}

请保持回复简洁友好，符合语音交互的特点。"""
    
    async def _process_intent_analysis(self, request: IntentRequest, intent_analysis: Dict,
                                     dialogue_history: List[Dict], sentence_id: str, start_time: float) -> IntentResult:
        """
        处理意图分析结果
        
        Args:
            request: 原始请求
            intent_analysis: 意图分析结果
            dialogue_history: 对话历史
            sentence_id: 句子ID
            start_time: 开始时间
            
        Returns:
            IntentResult: 处理结果
        """
        processing_time = time.time() - start_time
        
        # 解析意图类型
        intent_type_str = intent_analysis.get("intent_type", "chat")
        intent_type = self._parse_intent_type(intent_type_str)
        
        # 获取置信度
        confidence = intent_analysis.get("confidence", 0.5)
        
        # 更新统计
        self._update_intent_statistics(intent_type)
        
        if intent_type == IntentType.FUNCTION_CALL:
            return await self._handle_function_call(
                request, intent_analysis, sentence_id, processing_time, confidence
            )
        elif intent_type == IntentType.CONTEXT_QUERY:
            return await self._handle_context_query(
                request, intent_analysis, dialogue_history, sentence_id, processing_time, confidence
            )
        else:  # CHAT
            return self._handle_chat_response(
                request, intent_analysis, sentence_id, processing_time, confidence
            )
    
    async def _handle_function_call(self, request: IntentRequest, intent_analysis: Dict,
                                  sentence_id: str, processing_time: float, confidence: float) -> IntentResult:
        """
        处理功能调用
        
        Args:
            request: 原始请求
            intent_analysis: 意图分析结果
            sentence_id: 句子ID
            processing_time: 处理时间
            confidence: 置信度
            
        Returns:
            IntentResult: 处理结果
        """
        function_call = intent_analysis.get("function_call", {})
        function_name = function_call.get("name", "")
        function_args = function_call.get("arguments", {})
        
        self.logger.info(f"[{self.tag}] 处理功能调用: {function_name}")
        
        # 这里应该集成功能调用处理器
        # 暂时返回模拟结果
        function_result = f"功能 {function_name} 执行完成"
        response_text = f"好的，我已经为您{function_result}"
        
        self.statistics.successful_requests += 1
        self.statistics.total_processing_time += processing_time
        
        return IntentResult(
            request=request,
            intent_type=IntentType.FUNCTION_CALL,
            response_text=response_text,
            processing_status=ProcessingStatus.SUCCESS,
            processing_time=processing_time,
            confidence=confidence,
            function_name=function_name,
            function_args=function_args,
            function_result=function_result,
            sentence_id=sentence_id,
            metadata={"device_id": self.device_id}
        )
    
    async def _handle_context_query(self, request: IntentRequest, intent_analysis: Dict,
                                   dialogue_history: List[Dict], sentence_id: str,
                                   processing_time: float, confidence: float) -> IntentResult:
        """
        处理上下文查询
        
        Args:
            request: 原始请求
            intent_analysis: 意图分析结果
            dialogue_history: 对话历史
            sentence_id: 句子ID
            processing_time: 处理时间
            confidence: 置信度
            
        Returns:
            IntentResult: 处理结果
        """
        # 获取当前时间信息
        from datetime import datetime
        current_time = datetime.now()
        
        # 构建上下文提示
        context_prompt = f"""当前时间：{current_time.strftime('%Y-%m-%d %H:%M:%S')}
今天是：{current_time.strftime('%A')}

请根据以上信息回答用户的问题：{request.user_text}"""
        
        try:
            # 重新调用LLM生成带上下文的回复
            messages = [
                {"role": "system", "content": "你是一个智能助手，请根据提供的上下文信息回答用户问题。"},
                {"role": "user", "content": context_prompt}
            ]
            
            response = await self.llm_service.chat_async(messages, temperature=0.7)
            
            self.statistics.successful_requests += 1
            self.statistics.total_processing_time += processing_time
            
            return IntentResult(
                request=request,
                intent_type=IntentType.CONTEXT_QUERY,
                response_text=response or "抱歉，我无法获取相关信息。",
                processing_status=ProcessingStatus.SUCCESS,
                processing_time=processing_time,
                confidence=confidence,
                sentence_id=sentence_id,
                metadata={"device_id": self.device_id, "context_used": True}
            )
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 上下文查询处理失败: {e}")
            return self._create_error_result(request, sentence_id, start_time, str(e))
    
    def _handle_chat_response(self, request: IntentRequest, intent_analysis: Dict,
                            sentence_id: str, processing_time: float, confidence: float) -> IntentResult:
        """
        处理普通对话回复
        
        Args:
            request: 原始请求
            intent_analysis: 意图分析结果
            sentence_id: 句子ID
            processing_time: 处理时间
            confidence: 置信度
            
        Returns:
            IntentResult: 处理结果
        """
        response_text = intent_analysis.get("response", "我明白了，还有什么可以帮助您的吗？")
        
        self.statistics.successful_requests += 1
        self.statistics.total_processing_time += processing_time
        
        return IntentResult(
            request=request,
            intent_type=IntentType.CHAT,
            response_text=response_text,
            processing_status=ProcessingStatus.SUCCESS,
            processing_time=processing_time,
            confidence=confidence,
            sentence_id=sentence_id,
            metadata={"device_id": self.device_id}
        )
    
    def _create_exit_result(self, request: IntentRequest, sentence_id: str, start_time: float) -> IntentResult:
        """创建退出命令结果"""
        processing_time = time.time() - start_time
        self.statistics.successful_requests += 1
        self.statistics.exit_command_count += 1
        self.statistics.total_processing_time += processing_time
        
        return IntentResult(
            request=request,
            intent_type=IntentType.EXIT_COMMAND,
            response_text="好的，再见！",
            processing_status=ProcessingStatus.SUCCESS,
            processing_time=processing_time,
            confidence=1.0,
            sentence_id=sentence_id,
            metadata={"device_id": self.device_id, "should_close": True}
        )
    
    def _create_wakeup_result(self, request: IntentRequest, sentence_id: str, start_time: float) -> IntentResult:
        """创建唤醒词结果"""
        processing_time = time.time() - start_time
        self.statistics.successful_requests += 1
        self.statistics.wakeup_word_count += 1
        self.statistics.total_processing_time += processing_time
        
        return IntentResult(
            request=request,
            intent_type=IntentType.WAKEUP_WORD,
            response_text="我在这里，有什么可以帮助您的吗？",
            processing_status=ProcessingStatus.SUCCESS,
            processing_time=processing_time,
            confidence=1.0,
            sentence_id=sentence_id,
            metadata={"device_id": self.device_id}
        )
    
    def _create_error_result(self, request: IntentRequest, sentence_id: str, 
                           start_time: float, error_message: str) -> IntentResult:
        """创建错误结果"""
        processing_time = time.time() - start_time
        
        return IntentResult(
            request=request,
            intent_type=IntentType.UNKNOWN,
            response_text="抱歉，我现在无法理解您的意思，请稍后再试。",
            processing_status=ProcessingStatus.FAILED,
            processing_time=processing_time,
            confidence=0.0,
            error_message=error_message,
            sentence_id=sentence_id,
            metadata={"device_id": self.device_id}
        )
    
    def _create_timeout_result(self, request: IntentRequest, sentence_id: str, start_time: float) -> IntentResult:
        """创建超时结果"""
        processing_time = time.time() - start_time
        
        return IntentResult(
            request=request,
            intent_type=IntentType.UNKNOWN,
            response_text="抱歉，处理时间过长，请稍后再试。",
            processing_status=ProcessingStatus.TIMEOUT,
            processing_time=processing_time,
            confidence=0.0,
            error_message="处理超时",
            sentence_id=sentence_id,
            metadata={"device_id": self.device_id}
        )
    
    def _parse_intent_type(self, intent_type_str: str) -> IntentType:
        """解析意图类型"""
        try:
            return IntentType(intent_type_str.lower())
        except ValueError:
            return IntentType.UNKNOWN
    
    def _update_intent_statistics(self, intent_type: IntentType) -> None:
        """更新意图统计"""
        if intent_type == IntentType.CHAT:
            self.statistics.chat_count += 1
        elif intent_type == IntentType.FUNCTION_CALL:
            self.statistics.function_call_count += 1
        elif intent_type == IntentType.CONTEXT_QUERY:
            self.statistics.context_query_count += 1
        elif intent_type == IntentType.EXIT_COMMAND:
            self.statistics.exit_command_count += 1
        elif intent_type == IntentType.WAKEUP_WORD:
            self.statistics.wakeup_word_count += 1
        else:
            self.statistics.unknown_count += 1
    
    async def _save_dialogue_history(self, request: IntentRequest, result: IntentResult) -> None:
        """保存对话历史"""
        try:
            if not request.user_id:
                return
            
            # 保存用户消息
            await self.chat_history_service.save_message(
                user_id=request.user_id,
                role="user",
                content=request.user_text,
                session_id=request.session_id
            )
            
            # 保存助手回复
            await self.chat_history_service.save_message(
                user_id=request.user_id,
                role="assistant",
                content=result.response_text,
                session_id=request.session_id
            )
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] 保存对话历史失败: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "device_id": self.device_id,
            "requests": {
                "total": self.statistics.total_requests,
                "successful": self.statistics.successful_requests,
                "failed": self.statistics.failed_requests,
                "success_rate": round(self.statistics.success_rate, 2)
            },
            "intent_types": {
                "chat": self.statistics.chat_count,
                "function_call": self.statistics.function_call_count,
                "context_query": self.statistics.context_query_count,
                "exit_command": self.statistics.exit_command_count,
                "wakeup_word": self.statistics.wakeup_word_count,
                "unknown": self.statistics.unknown_count
            },
            "performance": {
                "avg_processing_time": round(self.statistics.avg_processing_time, 3),
                "total_processing_time": round(self.statistics.total_processing_time, 3)
            },
            "config": {
                "max_processing_time": self.max_processing_time,
                "min_confidence": self.min_confidence,
                "max_dialogue_history": self.max_dialogue_history
            }
        }
    
    def reset_statistics(self) -> None:
        """重置统计信息"""
        self.statistics = IntentStatistics()
        self.logger.info(f"[{self.tag}] 统计信息已重置")
    
    def _map_psychology_intent_to_standard(self, psychology_intent: str) -> str:
        """
        将心理意图映射到标准意图类型
        
        Args:
            psychology_intent: 心理意图类型
            
        Returns:
            str: 标准意图类型
        """
        # 危机情况映射为功能调用
        crisis_intents = [
            "suicide_crisis", "self_harm_crisis", "crisis_intervention"
        ]
        
        if psychology_intent in crisis_intents:
            return "function_call"
        
        # 基础对话意图
        basic_intents = ["greeting", "casual_chat", "farewell"]
        if psychology_intent in basic_intents:
            return "chat"
        
        # 需要上下文的查询
        context_intents = ["career_guidance", "resource_request", "professional_referral"]
        if psychology_intent in context_intents:
            return "context_query"
        
        # 其他心理健康相关意图都映射为对话
        return "chat"
    
    def _generate_crisis_response(self, intent_result) -> str:
        """
        生成危机干预响应
        
        Args:
            intent_result: 意图分析结果
            
        Returns:
            str: 危机干预响应
        """
        crisis_responses = {
            "suicide_crisis": """我非常担心你现在的状态。你的生命很珍贵，你并不孤单。

🆘 请立即寻求帮助：
• 全国心理危机干预热线：400-161-9995
• 青少年心理热线：12355

如果你现在就有危险，请立即拨打120或联系身边的人。我会一直陪伴你，但专业的心理医生能给你更好的帮助。""",
            
            "self_harm_crisis": """我很担心你，自伤并不能真正解决问题。

💙 你可以尝试这些替代方法：
• 握紧冰块或用冷水冲手
• 剧烈运动或大声唱歌
• 深呼吸或写日记

🆘 寻求专业帮助：
• 青少年心理咨询热线：12355
• 当地心理健康中心

你现在的痛苦是真实的，但伤害自己不是解决办法。让我们一起找到更好的方式，好吗？""",
            
            "crisis_intervention": f"""我注意到你现在可能遇到了困难，这让我很关心你。

建议寻求以下帮助：
{chr(10).join(f'• {resource}' for resource in (intent_result.suggested_resources or ['专业心理咨询师', '学校心理老师']))}

记住，寻求帮助是勇敢的表现。你愿意告诉我更多关于你现在的感受吗？"""
        }
        
        return crisis_responses.get(
            intent_result.primary_intent.value,
            "我很关心你现在的状况。如果你感到困扰，建议寻求专业心理帮助。你不是一个人在面对这些。"
        )
    
    def _generate_friendly_response(self, intent_result, user_text: str) -> str:
        """
        生成友好的基础对话响应
        
        Args:
            intent_result: 意图分析结果
            user_text: 用户文本
            
        Returns:
            str: 友好响应
        """
        friendly_responses = {
            "greeting": [
                "你好！很高兴见到你。今天过得怎么样？",
                "嗨！欢迎来聊天。有什么想分享的吗？",
                "你好！我是你的心理健康小助手，随时准备倾听你的心声。"
            ],
            "farewell": [
                "谢谢你今天和我聊天！记住，你很重要，你的感受很重要。如果需要帮助，随时可以回来找我。照顾好自己！",
                "再见！祝你一切都好。记住，如果遇到困难，我随时在这里支持你。",
                "保重！记住你值得被好好对待。如果需要聊天，我随时都在。"
            ],
            "casual_chat": [
                "听起来很有趣！能告诉我更多吗？",
                "我很高兴你愿意和我分享这些。你对此有什么感受？",
                "这听起来不错。你最近还有什么其他想法吗？"
            ]
        }
        
        responses = friendly_responses.get(intent_result.primary_intent.value, ["我明白了，请继续。"])
        
        import random
        return random.choice(responses)
    
    async def _generate_supportive_response(self, intent_result, user_text: str, dialogue_history: List[Dict]) -> str:
        """
        生成支持性心理健康响应
        
        Args:
            intent_result: 意图分析结果
            user_text: 用户文本
            dialogue_history: 对话历史
            
        Returns:
            str: 支持性响应
        """
        # 根据具体的心理意图类型生成专业的支持性回复
        supportive_templates = {
            "emotional_support": f"""我能感受到你现在的{intent_result.emotional_state or '情绪'}。你的感受是完全正常和有效的。

💝 一些可能有帮助的方法：
• 深呼吸：慢慢吸气4秒，屏住4秒，呼气4秒
• 写下你的感受，不用担心语法或逻辑
• 听一些舒缓的音乐或做你喜欢的事

你想和我分享更多关于让你困扰的事情吗？我会认真倾听，不做任何评判。""",
            
            "stress_relief": """压力是现代生活的一部分，但我们可以学会更好地管理它。

🧘‍♀️ 快速减压技巧：
• 5-4-3-2-1感官练习：说出5个你能看到的、4个能摸到的、3个能听到的
• 渐进性肌肉放松：从脚趾开始，依次紧张和放松每个肌肉群
• 正念呼吸：专注于呼吸的感觉

你现在面临的主要压力来源是什么？让我们一起想想应对的方法。""",
            
            "study_pressure": """学习压力是很多同学都面临的挑战，你的感受完全可以理解。

📚 学习压力管理：
• 设定现实的目标：把大目标分解成小的、可达成的步骤
• 番茄工作法：学习25分钟，休息5分钟
• 记住，成绩不能定义你的价值

你在学习上遇到的最大困难是什么？是某个科目、学习方法，还是时间管理？""",
            
            "family_issues": """家庭关系的困扰很常见，特别是在青少年时期。你的感受是正常的。

👨‍👩‍👧‍👦 改善家庭关系的方法：
• 尝试从父母的角度理解他们的担心和期望
• 选择合适的时机，冷静地表达你的想法和感受
• 寻找共同点，从小事开始改善关系

你和家人之间主要的矛盾是什么？让我们聊聊具体的情况。"""
        }
        
        # 如果有预定义的模板，使用模板
        if intent_result.primary_intent.value in supportive_templates:
            return supportive_templates[intent_result.primary_intent.value]
        
        # 否则使用LLM生成个性化回复
        try:
            system_prompt = f"""你是一个专业的青少年心理健康助手。用户表达了关于{intent_result.primary_intent.value}的困扰。

用户当前情感状态：{intent_result.emotional_state or '需要关注'}
情感强度：{intent_result.emotional_intensity:.1f}/1.0
风险等级：{intent_result.risk_level}

请提供温暖、专业、有帮助的回复。要：
1. 表达理解和共情
2. 提供具体的建议或方法
3. 鼓励用户分享更多
4. 保持积极但现实的语调

回复应该适合青少年，语言亲切但专业。"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ]
            
            response = await self.llm_service.chat_async(messages, temperature=0.7)
            return response if response else self._get_default_supportive_response()
            
        except Exception as e:
            self.logger.error(f"[{self.tag}] LLM生成支持性回复失败: {e}")
            return self._get_default_supportive_response()
    
    def _get_default_supportive_response(self) -> str:
        """获取默认支持性回复"""
        return """我能感受到你想要表达什么，虽然我可能没有完全理解。

💙 无论你现在面临什么，请记住：
• 你的感受是有效的和重要的
• 寻求帮助是勇敢的表现
• 你不需要独自面对困难

能告诉我更多关于你现在的情况吗？我会认真倾听，尽我所能帮助你。"""


# 全局意图处理器字典
_intent_processors: Dict[str, ESP32IntentProcessor] = {}


def get_esp32_intent_processor(device_id: str) -> ESP32IntentProcessor:
    """
    获取ESP32意图处理器
    
    Args:
        device_id: 设备ID
        
    Returns:
        ESP32IntentProcessor: 意图处理器实例
    """
    if device_id not in _intent_processors:
        _intent_processors[device_id] = ESP32IntentProcessor(device_id)
    
    return _intent_processors[device_id]


def remove_esp32_intent_processor(device_id: str) -> None:
    """
    移除ESP32意图处理器
    
    Args:
        device_id: 设备ID
    """
    if device_id in _intent_processors:
        processor = _intent_processors[device_id]
        processor.reset_statistics()
        del _intent_processors[device_id]
