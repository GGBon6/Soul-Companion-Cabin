"""
LLM服务 V2 - 支持依赖注入和配置
LLM Service V2 - Dependency Injection Support
基于 DashScope Generation API，支持应用上下文模式
"""

import asyncio
import time
from typing import List, Dict, Optional
from http import HTTPStatus
from dataclasses import dataclass
import dashscope
from dashscope import Generation

from app.core import logger
from app.core.llm_config import LLMConfig
from app.core.exceptions import LLMError, APIKeyError


@dataclass
class LLMMetrics:
    """LLM服务指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_requests: int = 0
    total_time: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def avg_time(self) -> float:
        """平均响应时间（秒）"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_time / self.successful_requests
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'timeout_requests': self.timeout_requests,
            'success_rate': round(self.success_rate, 2),
            'avg_time_ms': round(self.avg_time * 1000, 2)
        }


class LLMService:
    """
    LLM服务类 V2 - 支持配置注入
    
    改进：
    1. 通过LLMConfig注入配置，不再依赖全局settings
    2. 支持为不同客户端类型创建独立实例
    3. 更好的生命周期管理
    4. 支持健康检查
    """
    
    def __init__(self, config: LLMConfig):
        """
        初始化LLM服务
        
        Args:
            config: LLM配置对象
        """
        self.config = config
        self.api_key = config.api_key
        self.model = config.model
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature
        self.top_p = config.top_p
        self.client_type = config.client_type
        
        if not self.api_key:
            logger.error("DASHSCOPE_API_KEY 未配置")
            raise APIKeyError("DASHSCOPE_API_KEY 未配置")
        
        # 设置DashScope API Key
        dashscope.api_key = self.api_key
        
        # 并发控制
        self.max_concurrent = config.max_concurrent
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # 性能指标
        self.metrics = LLMMetrics()
        
        # 缓存管理器
        self.cache_manager = None
        if config.enable_cache:
            self._init_cache()
        
        # 健康状态
        self._is_healthy = True
        self._last_error_time = None
        
        logger.info(
            f"✅ LLM服务初始化: model={self.model}, "
            f"client_type={self.client_type}, "
            f"max_concurrent={self.max_concurrent}"
        )
    
    def _init_cache(self):
        """初始化缓存"""
        try:
            from app.core.config import settings
            if settings.ENABLE_CACHE and settings.ENABLE_LLM_CACHE:
                from app.shared.cache import get_cache_manager
                self.cache_manager = get_cache_manager()
                logger.info(f"✅ LLM缓存已启用 (client_type={self.client_type})")
            else:
                logger.info(f"⏸️ LLM缓存已禁用 (client_type={self.client_type})")
        except Exception as e:
            logger.warning(f"⚠️ LLM缓存初始化失败: {e}")
            self.cache_manager = None
    
    async def initialize(self):
        """异步初始化"""
        logger.info(f"🔧 初始化LLM服务 (client_type={self.client_type})")
        # 可以在这里做一些异步初始化工作
        # 例如：预热模型、测试连接等
        pass
    
    async def shutdown(self):
        """关闭服务"""
        logger.info(f"⏹️ 关闭LLM服务 (client_type={self.client_type})")
        # 清理资源
        self._is_healthy = False
    
    async def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            bool: 服务是否健康
        """
        try:
            # 简单的健康检查：检查成功率
            if self.metrics.total_requests > 10:
                if self.metrics.success_rate < 50:
                    logger.warning(
                        f"⚠️ LLM服务健康检查失败: 成功率过低 "
                        f"({self.metrics.success_rate:.1f}%, client_type={self.client_type})"
                    )
                    self._is_healthy = False
                    return False
            
            self._is_healthy = True
            return True
        except Exception as e:
            logger.error(f"❌ LLM健康检查异常: {e}")
            self._is_healthy = False
            return False
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = None, user_id: str = "") -> str:
        """
        调用LLM进行对话（同步方法）
        
        Args:
            messages: 对话历史
            temperature: 温度参数
            user_id: 用户ID
        
        Returns:
            str: LLM生成的回复文本
        """
        if temperature is None:
            temperature = self.temperature
        
        # 尝试从缓存获取响应
        cached_response = self._get_cached_response(messages, temperature, user_id)
        if cached_response:
            logger.debug(f"🎯 LLM缓存命中 (client_type={self.client_type}, user={user_id})")
            return cached_response
        
        # 模型回退列表
        preferred_models = [
            self.model,
            "qwen-plus",
            "qwen-turbo"
        ]
        
        last_error = None
        start_time = time.time()
        
        for model in preferred_models:
            try:
                logger.debug(f"尝试使用模型: {model} (client_type={self.client_type})")
                
                response = Generation.call(
                    model=model,
                    messages=messages,
                    result_format='message',
                    temperature=temperature,
                    max_tokens=self.max_tokens,
                    top_p=self.top_p
                )
                
                if response.status_code == HTTPStatus.OK:
                    reply = response.output.choices[0].message.content.strip()
                    response_time = (time.time() - start_time) * 1000
                    
                    # 缓存响应
                    self._cache_response(messages, temperature, user_id, reply, model, response_time)
                    
                    logger.info(
                        f"LLM调用成功 (model={model}, client_type={self.client_type}, "
                        f"length={len(reply)}, time={response_time:.1f}ms)"
                    )
                    return reply
                else:
                    error_msg = f"请求失败: {response.code} - {response.message}"
                    logger.warning(f"模型 {model}: {error_msg}")
                    last_error = error_msg
                    
                    if "InvalidModel" in response.code or "ModelNotFound" in response.code:
                        continue
                    else:
                        return f"抱歉，我现在有些不舒服...（{response.message}）"
                
            except Exception as e:
                last_error = e
                logger.error(f"调用LLM失败: {e}", exc_info=True)
                continue
        
        # 所有模型都失败
        logger.error(f"所有模型调用均失败 (client_type={self.client_type}), 最后错误: {last_error}")
        self._last_error_time = time.time()
        return f"抱歉，我现在有些不舒服...（错误：{str(last_error)}）"
    
    async def chat_async(self, messages: List[Dict[str, str]], temperature: float = None, user_id: str = "") -> str:
        """
        异步调用LLM进行对话
        
        Args:
            messages: 对话历史
            temperature: 温度参数
            user_id: 用户ID
        
        Returns:
            str: LLM生成的回复文本
        """
        self.metrics.total_requests += 1
        start_time = time.time()
        
        try:
            # 并发控制
            async with self.semaphore:
                current_concurrent = self.max_concurrent - self.semaphore._value
                
                logger.debug(
                    f"🔄 LLM请求 (client_type={self.client_type}, "
                    f"concurrent={current_concurrent}/{self.max_concurrent})"
                )
                
                # 检查并发压力
                if current_concurrent > self.max_concurrent * 0.8:
                    logger.warning(
                        f"⚠️ LLM并发压力过高: {current_concurrent}/{self.max_concurrent} "
                        f"(client_type={self.client_type})"
                    )
                
                # 使用asyncio.to_thread在异步环境中调用同步方法
                response = await asyncio.to_thread(self.chat, messages, temperature, user_id)
                
                # 记录成功
                elapsed_time = time.time() - start_time
                self.metrics.successful_requests += 1
                self.metrics.total_time += elapsed_time
                
                logger.debug(
                    f"✅ LLM完成 (client_type={self.client_type}, "
                    f"time={elapsed_time*1000:.1f}ms, "
                    f"success_rate={self.metrics.success_rate:.1f}%)"
                )
                
                return response
            
        except Exception as e:
            self.metrics.failed_requests += 1
            logger.error(f"❌ LLM失败 (client_type={self.client_type}): {e}")
            raise
    
    def _get_cached_response(self, messages: List[Dict[str, str]], temperature: float, user_id: str) -> Optional[str]:
        """从缓存获取响应"""
        if not self.cache_manager:
            return None
        
        try:
            from app.shared.cache.llm_cache import LLMRequest
            
            prompt = self._build_prompt_from_messages(messages)
            request = LLMRequest(
                prompt=prompt,
                model=self.model,
                temperature=temperature,
                max_tokens=self.max_tokens,
                user_id=user_id
            )
            
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return None
                else:
                    cached_response = loop.run_until_complete(self.cache_manager.get_llm_response(request))
            except RuntimeError:
                cached_response = asyncio.run(self.cache_manager.get_llm_response(request))
            
            if cached_response:
                return cached_response.content
                
        except Exception as e:
            logger.debug(f"获取LLM缓存失败: {e}")
        
        return None
    
    def _cache_response(self, messages: List[Dict[str, str]], temperature: float, user_id: str, 
                      reply: str, model: str, response_time: float):
        """缓存响应"""
        if not self.cache_manager:
            return
        
        try:
            from app.shared.cache.llm_cache import LLMRequest, LLMResponse
            
            prompt = self._build_prompt_from_messages(messages)
            request = LLMRequest(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=self.max_tokens,
                user_id=user_id
            )
            
            response = LLMResponse(
                content=reply,
                model=model,
                response_time=response_time,
                metadata={'user_id': user_id, 'client_type': self.client_type}
            )
            
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.cache_manager.cache_llm_response(request, response))
                else:
                    loop.run_until_complete(self.cache_manager.cache_llm_response(request, response))
            except RuntimeError:
                asyncio.run(self.cache_manager.cache_llm_response(request, response))
                
        except Exception as e:
            logger.debug(f"缓存LLM响应失败: {e}")
    
    def _build_prompt_from_messages(self, messages: List[Dict[str, str]]) -> str:
        """从消息列表构建提示"""
        prompt_parts = []
        for msg in messages:
            role = msg.get('role', '')
            content = msg.get('content', '')
            if role and content:
                prompt_parts.append(f"{role}: {content}")
        return "\n".join(prompt_parts)
    
    def get_metrics(self) -> Dict:
        """获取服务指标"""
        return {
            'client_type': self.client_type,
            'model': self.model,
            'is_healthy': self._is_healthy,
            **self.metrics.to_dict()
        }
    
    def get_config(self) -> Dict:
        """获取配置信息"""
        return self.config.to_dict()


# 全局服务实例
_llm_service: Optional[LLMService] = None


def get_llm_service(client_type: str = 'default') -> LLMService:
    """
    获取LLM服务实例
    
    Args:
        client_type: 客户端类型，用于配置和统计
        
    Returns:
        LLMService: LLM服务实例
    """
    global _llm_service
    
    # 尝试从应用上下文获取
    try:
        from app.core.application import get_app
        app = get_app()
        if app and app.is_running:
            # 如果应用已初始化，使用应用上下文的服务
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 在异步上下文中，建议使用 await app.get_llm_service(client_type)
                    from app.core import logger
                    logger.warning(f"⚠️ 在异步上下文中调用 get_llm_service()，请尽快改为 await app.get_llm_service(client_type)")
                    # 降级到同步方式
                    pass
                else:
                    # 同步上下文，可以直接调用
                    return loop.run_until_complete(app.get_llm_service(client_type))
            except RuntimeError:
                # 没有事件循环，继续使用全局实例
                pass
    except ImportError:
        # 应用未初始化，使用全局实例
        pass
    
    # 降级到全局单例模式
    if _llm_service is None:
        from app.core.config import settings
        from app.core.llm_config import LLMConfig
        
        # 根据客户端类型创建配置
        if client_type == 'esp32':
            config = LLMConfig.for_esp32(settings.DASHSCOPE_API_KEY)
        elif client_type == 'web':
            config = LLMConfig.for_web(settings.DASHSCOPE_API_KEY)
        else:
            config = LLMConfig.for_default(settings.DASHSCOPE_API_KEY)
        
        _llm_service = LLMService(config, client_type)
    
    return _llm_service


def reset_llm_service():
    """重置LLM服务实例"""
    global _llm_service
    _llm_service = None
