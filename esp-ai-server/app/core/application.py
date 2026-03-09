"""
应用上下文 - 统一管理应用生命周期和服务
Application Context - Unified Application Lifecycle and Service Management
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
import asyncio
from pathlib import Path

from app.core import logger
from app.core.service_pool import ServicePool, ServicePoolConfig
from app.core.llm_config import LLMConfig


@dataclass
class ApplicationConfig:
    """应用配置"""
    name: str = "心理对话AI"
    version: str = "2.0.0"
    environment: str = "production"  # development, staging, production
    
    # 功能开关
    enable_esp32: bool = True
    enable_web: bool = True
    enable_monitoring: bool = True
    enable_cache: bool = True
    
    # API密钥
    dashscope_api_key: str = ""


class Application:
    """
    应用上下文 - 整个应用的核心管理器
    
    职责：
    1. 管理所有服务的生命周期
    2. 提供统一的服务访问接口
    3. 处理应用启动和关闭
    4. 监控应用健康状态
    
    特点：
    - ESP32和Web端使用不同的LLM服务实例
    - 自动健康检查和实例替换
    - 统一的配置管理
    - 优雅的启动和关闭
    """
    
    def __init__(self, config: ApplicationConfig):
        self.config = config
        
        # 服务池
        self.service_pools: Dict[str, ServicePool] = {}
        
        # 监控系统
        self.metrics = None
        
        # 运行状态
        self.is_running = False
        self._shutdown_event = asyncio.Event()
        
        logger.info(f"🏗️ 创建应用上下文: {config.name} v{config.version}")
    
    async def initialize(self):
        """初始化应用"""
        logger.info("=" * 70)
        logger.info(f"💙 {self.config.name} v{self.config.version}")
        logger.info(f"🌍 环境: {self.config.environment}")
        logger.info("=" * 70)
        logger.info("")
        
        try:
            # 1. 初始化服务池
            logger.info("🔧 初始化服务池...")
            await self._initialize_service_pools()
            
            # 2. 初始化监控系统
            if self.config.enable_monitoring:
                logger.info("🔧 初始化监控系统...")
                await self._initialize_monitoring()
            
            # 3. 初始化缓存系统
            if self.config.enable_cache:
                logger.info("🔧 初始化缓存系统...")
                await self._initialize_cache()
            
            self.is_running = True
            logger.info("✅ 应用初始化完成")
            logger.info("")
            
        except Exception as e:
            logger.error(f"❌ 应用初始化失败: {e}", exc_info=True)
            raise
    
    async def _initialize_service_pools(self):
        """初始化服务池"""
        from app.shared.services.llm_service import LLMService
        
        # LLM服务池配置工厂
        def llm_config_factory(client_type: str) -> LLMConfig:
            """根据客户端类型创建LLM配置"""
            api_key = self.config.dashscope_api_key
            
            if client_type == 'esp32':
                return LLMConfig.for_esp32(api_key)
            elif client_type == 'web':
                return LLMConfig.for_web(api_key)
            elif client_type == 'system':
                return LLMConfig.for_system(api_key)
            else:
                # 默认配置
                return LLMConfig(
                    api_key=api_key,
                    model="qwen-plus",
                    max_tokens=2000,
                    temperature=0.8,
                    max_concurrent=50,
                    client_type=client_type
                )
        
        # 创建LLM服务池
        llm_pool_config = ServicePoolConfig(
            min_instances=1,
            max_instances=5,
            instance_per_client_type=True,
            enable_health_check=True,
            health_check_interval=60
        )
        
        llm_pool = ServicePool(
            service_class=LLMService,
            config=llm_pool_config,
            config_factory=llm_config_factory
        )
        
        await llm_pool.start()
        self.service_pools['llm'] = llm_pool
        
        logger.info("✅ LLM服务池初始化完成")
        
        # TODO: 可以添加其他服务池（TTS、ASR等）
    
    async def _initialize_monitoring(self):
        """初始化监控系统"""
        try:
            # TODO: 实现监控系统
            logger.info("✅ 监控系统初始化完成（占位）")
        except Exception as e:
            logger.warning(f"⚠️ 监控系统初始化失败: {e}")
    
    async def _initialize_cache(self):
        """初始化缓存系统"""
        try:
            from app.shared.cache import initialize_cache_manager
            await initialize_cache_manager()
            logger.info("✅ 缓存系统初始化完成")
        except Exception as e:
            logger.warning(f"⚠️ 缓存系统初始化失败: {e}")
    
    async def get_llm_service(self, client_type: str = 'default'):
        """
        获取LLM服务实例
        
        Args:
            client_type: 客户端类型 ('esp32', 'web', 'system', 'default')
        
        Returns:
            LLMService实例
        """
        if not self.is_running:
            raise RuntimeError("应用未初始化，请先调用 initialize()")
        
        pool = self.service_pools.get('llm')
        if not pool:
            raise RuntimeError("LLM服务池未初始化")
        
        return await pool.get_instance(client_type)
    
    async def shutdown(self):
        """关闭应用"""
        logger.info("⏹️ 正在关闭应用...")
        
        self.is_running = False
        
        try:
            # 1. 关闭服务池
            for name, pool in self.service_pools.items():
                logger.info(f"⏹️ 关闭服务池: {name}")
                await pool.shutdown_all()
            
            # 2. 关闭缓存系统
            if self.config.enable_cache:
                from app.shared.cache import shutdown_cache_manager
                await shutdown_cache_manager()
                logger.info("✅ 缓存系统已关闭")
            
            self._shutdown_event.set()
            logger.info("✅ 应用已关闭")
            
        except Exception as e:
            logger.error(f"❌ 应用关闭过程中发生错误: {e}", exc_info=True)
    
    async def wait_for_shutdown(self):
        """等待关闭信号"""
        await self._shutdown_event.wait()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取应用统计信息"""
        stats = {
            'name': self.config.name,
            'version': self.config.version,
            'environment': self.config.environment,
            'is_running': self.is_running,
            'service_pools': {}
        }
        
        # 收集服务池统计
        for name, pool in self.service_pools.items():
            stats['service_pools'][name] = pool.get_stats()
        
        return stats


# ==================== 应用实例管理 ====================
# 
# ✅ 推荐方式：将应用实例作为参数传递
#     app = create_app()
#     await handler.handle(app, request)
#
# ⚠️ 兼容方式：使用全局访问（仅用于向后兼容）
#     app = get_app()
#
# ====================================================

# 全局应用实例（仅用于向后兼容）
_app: Optional[Application] = None


def get_app() -> Application:
    """
    获取应用实例（向后兼容）
    
    ⚠️ 不推荐：这是全局单例模式
    
    推荐方式：将应用实例作为参数传递
        app = create_app()
        await some_function(app, ...)
    
    Returns:
        Application实例
    
    Raises:
        RuntimeError: 如果应用未初始化
    """
    global _app
    if _app is None:
        raise RuntimeError(
            "应用未初始化。\n"
            "推荐方式：\n"
            "  app = create_app()\n"
            "  await app.initialize()\n"
            "  # 将app作为参数传递给需要的地方"
        )
    return _app


def create_app(config: Optional[ApplicationConfig] = None) -> Application:
    """
    创建应用实例
    
    Args:
        config: 应用配置，如果为None则使用默认配置
    
    Returns:
        Application实例（不是单例，可以创建多个）
    """
    if config is None:
        # 从settings创建默认配置
        from app.core.config import settings
        config = ApplicationConfig(
            name="心理对话AI",
            version="2.0.0",
            environment=getattr(settings, 'ENVIRONMENT', 'production'),
            enable_esp32=True,
            enable_web=True,
            enable_monitoring=getattr(settings, 'ENABLE_METRICS', False),
            enable_cache=getattr(settings, 'ENABLE_CACHE', True),
            dashscope_api_key=settings.DASHSCOPE_API_KEY
        )
    
    # 创建新实例（不使用全局变量）
    app = Application(config)
    
    # 为了向后兼容，设置全局实例
    global _app
    if _app is None:
        _app = app
    
    return app


def set_global_app(app: Application):
    """
    设置全局应用实例（用于向后兼容）
    
    Args:
        app: 应用实例
    """
    global _app
    _app = app


def reset_app():
    """重置应用实例（用于测试）"""
    global _app
    _app = None
