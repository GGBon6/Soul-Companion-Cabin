"""
主入口文件
Main Entry Point
启动WebSocket服务器，处理语音对话
"""

# 首先设置Opus库DLL路径（必须在导入任何使用opuslib的模块之前）
from setup_opus import setup_opus_dll
setup_opus_dll()

import asyncio
import os
import sys

# 添加app目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.core import settings, logger
from app.web.handlers.websocket_handler import WebSocketHandler
from app.devices.ota.ota_server import get_ota_server
from app.shared.services.audio_cache_service import get_audio_cache_service
from app.core.connection_pool import initialize_connection_pool, shutdown_connection_pool
from app.core.reconnect_manager import initialize_reconnect_manager, shutdown_reconnect_manager
from app.shared.redis import (
    initialize_redis_manager, shutdown_redis_manager,
    initialize_user_state_service, shutdown_user_state_service,
    initialize_distributed_pool, shutdown_distributed_pool,
    initialize_session_store, shutdown_session_store,
    initialize_pubsub_service, shutdown_pubsub_service,
    initialize_redis_health_monitor, shutdown_redis_health_monitor
)
from app.shared.cache import initialize_cache_manager, shutdown_cache_manager
from aiohttp import web


async def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("💙 心灵小屋 - 青少年心理健康对话系统")
    logger.info("=" * 70)
    logger.info("")
    logger.info("🌸 可用角色: 小暖 | 小橙 | 小智 | 小树")
    logger.info("📝 核心功能: 角色对话 | 心情签到 | 情绪日记 | 睡前故事 | 树洞模式")
    logger.info("🔒 隐私保护: 本地存储 | 树洞模式 | 用户控制")
    logger.info("")
    
    # 创建应用上下文（依赖注入的根）
    from app.core.application import create_app, ApplicationConfig, set_global_app
    
    app = create_app(ApplicationConfig(
        name="心灵小屋",
        version="2.0.0",
        environment=getattr(settings, 'ENVIRONMENT', 'production'),
        enable_esp32=True,
        enable_web=True,
        enable_monitoring=getattr(settings, 'ENABLE_METRICS', False),
        enable_cache=getattr(settings, 'ENABLE_CACHE', True),
        dashscope_api_key=settings.DASHSCOPE_API_KEY
    ))
    
    # 设置为全局实例（用于向后兼容）
    set_global_app(app)
    
    try:
        # 初始化应用上下文（包含LLM服务池）
        await app.initialize()
        
        # 初始化Redis服务
        logger.info("🔧 初始化Redis共享存储服务...")
        redis_success = await initialize_redis_manager()
        if redis_success:
            await initialize_user_state_service()
            await initialize_distributed_pool()
            await initialize_session_store()
            await initialize_pubsub_service()
            await initialize_redis_health_monitor()
            logger.info("✅ Redis共享存储服务初始化完成")
        else:
            logger.warning("⚠️ Redis服务初始化失败，将使用本地模式")
        logger.info("")
        
        # 创建统一WebSocket服务管理器
        from app.web.websocket_server import get_websocket_server_manager
        server_manager = get_websocket_server_manager()
        
        # 预生成音频缓存（提升用户体验）
        logger.info("🎵 预生成问候语音频缓存...")
        audio_cache_service = get_audio_cache_service()
        success, total = await audio_cache_service.pregenerate_greetings()
        if success == total:
            logger.info(f"✅ 音频缓存预生成完成: {success}/{total} 个角色")
        else:
            logger.warning(f"⚠️ 音频缓存部分生成: {success}/{total} 个角色")
        logger.info("")
        
        # 创建OTA服务器
        ota_server = get_ota_server()
        
        # 创建HTTP服务器（用于OTA端点）
        http_app = web.Application()
        http_app.router.add_route('GET', '/ota/', ota_server.handle_ota_request)
        http_app.router.add_route('POST', '/ota/', ota_server.handle_ota_request)
        http_app.router.add_route('OPTIONS', '/ota/', ota_server.handle_options)
        
        # 启动HTTP服务器（OTA端点）
        http_runner = web.AppRunner(http_app)
        await http_runner.setup()
        http_site = web.TCPSite(http_runner, settings.HOST, 8080)  # OTA服务器使用8080端口
        await http_site.start()
        logger.info(f"📡 OTA服务器已启动: http://{settings.HOST}:8080/ota/")
        
        # 启动服务器
        logger.info(f"🚀 启动WebSocket服务器...")
        logger.info(f"   主机: {settings.HOST}")
        logger.info(f"   端口: {settings.PORT}")
        logger.info("")
        logger.info("✅ 服务器已启动，等待客户端连接...")
        logger.info("💡 提示: 按 Ctrl+C 停止服务器")
        logger.info("")
        logger.info(f"📋 ESP32配置信息:")
        logger.info(f"   OTA地址: http://{ota_server.websocket_host}:8080/ota/")
        logger.info(f"   WebSocket地址: {ota_server.websocket_url}")
        logger.info("")
        
        # 运行所有WebSocket服务器
        await server_manager.start_all_servers()
        
    except KeyboardInterrupt:
        logger.info("\n⏹️  正在关闭服务器...")
        
        # 关闭应用上下文（包含LLM服务池）
        try:
            await app.shutdown()
            logger.info("✅ 应用上下文已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭应用上下文失败: {e}")
        
        # 关闭所有服务
        try:
            await shutdown_connection_pool()
            await shutdown_reconnect_manager()
            logger.info("✅ 连接池管理器已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭连接池管理器失败: {e}")
        
        # 关闭Redis服务
        try:
            await shutdown_redis_health_monitor()
            await shutdown_pubsub_service()
            await shutdown_session_store()
            await shutdown_distributed_pool()
            await shutdown_user_state_service()
            await shutdown_redis_manager()
            logger.info("✅ Redis共享存储服务已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭Redis服务失败: {e}")
        
        logger.info("👋 再见！期待下次相遇~")
    except Exception as e:
        logger.error(f"❌ 服务器启动失败: {e}", exc_info=True)
        logger.error("💡 请检查:")
        logger.error("   1. .env 配置是否正确")
        logger.error("   2. 端口是否被占用")
        logger.error("   3. 依赖是否完整安装")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

