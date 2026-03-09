"""
仅启动Web客户端服务器
Web Client Server Only
用于特殊部署场景，只启动Web客户端WebSocket服务器
"""

import asyncio
from app.core import settings, logger
from app.web.handlers.websocket_handler import WebSocketHandler
from app.core.application import create_app, ApplicationConfig, set_global_app
from app.business.diary.diary_service import DiaryService
from app.business.story.story_service import StoryService
from app.shared.agents.memory_agent import MemoryAgent
from app.shared.agents.stores import create_memory_manager
from app.shared.agents.adapters.mood_adapter import get_mood_service
from app.shared.agents.adapters.history_adapter import get_history_service

async def main():
    """启动Web客户端服务器"""
    try:
        logger.info("🚀 启动Web客户端专用服务器...")
        
        # 创建应用上下文（Web专用配置）
        app = create_app(ApplicationConfig(
            name="Web Server",
            version="2.0.0",
            environment=getattr(settings, 'ENVIRONMENT', 'production'),
            enable_esp32=False,
            enable_web=True,
            enable_monitoring=getattr(settings, 'ENABLE_METRICS', False),
            enable_cache=getattr(settings, 'ENABLE_CACHE', True),
            dashscope_api_key=settings.DASHSCOPE_API_KEY
        ))
        set_global_app(app)
        await app.initialize()
        
        # 从应用上下文获取Web专用LLM服务
        llm_service = await app.get_llm_service('web')

        # 组装业务服务（构造注入）
        mood_service = get_mood_service()
        history_service = get_history_service()

        diary_service = DiaryService(
            llm_service=llm_service,
            mood_service=mood_service,
            history_service=history_service,
        )
        story_service = StoryService(llm_service=llm_service)
        memory_manager = create_memory_manager()
        memory_agent = MemoryAgent(memory_manager=memory_manager, llm_service=llm_service)

        # 创建Web处理器并注入所有依赖服务
        web_handler = WebSocketHandler(
            llm_service=llm_service,
            diary_service=diary_service,
            story_service=story_service,
            memory_agent=memory_agent,
        )
        
        logger.info(f"📱 Web客户端服务器: ws://{settings.HOST}:{settings.PORT}")
        
        # 只启动Web服务器
        await web_handler.start()
        await app.shutdown()
        
    except KeyboardInterrupt:
        logger.info("\n⏹️ Web服务器已停止")
        try:
            await app.shutdown()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"❌ Web服务器启动失败: {e}")
        try:
            await app.shutdown()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
