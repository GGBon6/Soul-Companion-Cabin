"""
仅启动ESP32设备服务器
ESP32 Device Server Only
用于特殊部署场景，只启动ESP32设备WebSocket服务器
包含完整的日志输出用于测试和调试
"""

# 首先设置Opus库DLL路径（必须在导入任何使用opuslib的模块之前）
from setup_opus import setup_opus_dll
setup_opus_dll()

import asyncio
import logging
from app.core import settings, logger
from app.devices.esp32.handlers.websocket_handler import get_esp32_websocket_handler
from app.core.device_logger import (
    log_esp32_service,
    log_esp32_connection,
    log_esp32_performance,
    get_esp32_stats,
    esp32_logger
)

# 导入必要的服务进行完整初始化
from app.shared.services import (
    get_asr_service, get_tts_service
)
from app.shared.services.audio_cache_service import get_audio_cache_service
# ESP32服务器不需要网页端连接池
# from app.core.connection_pool import initialize_connection_pool, get_connection_pool_manager
from app.core.asr_connection_pool import initialize_asr_connection_pool, get_asr_connection_pool
# 注意：ESP32适配器已迁移到新的WebSocket集成模块中
from app.shared.cache import initialize_cache_manager
from app.core.application import create_app, ApplicationConfig, set_global_app

async def initialize_esp32_services(app):
    """初始化ESP32服务器所需的所有服务"""
    import time
    start_time = time.time()
    
    log_esp32_service("服务器启动", "开始初始化ESP32服务器依赖服务", {})
    
    # 初始化缓存系统
    log_esp32_service("缓存管理器", "开始初始化", {})
    await initialize_cache_manager()
    log_esp32_service("缓存管理器", "初始化完成", {})
    
    # # ESP32服务器不需要网页端连接池，跳过初始化
    # log_esp32_service("连接池管理器", "ESP32服务器跳过网页端连接池初始化", {
    #     "reason": "ESP32设备使用专用的WebSocket管理器"
    # })
    
    # 初始化ASR连接池
    log_esp32_service("ASR连接池", "开始初始化", {})
    await initialize_asr_connection_pool()
    asr_pool = get_asr_connection_pool()
    pool_stats = asr_pool.get_stats()
    log_esp32_service("ASR连接池", "初始化完成", {
        "min_connections": settings.ASR_POOL_MIN_CONNECTIONS,
        "max_connections": settings.ASR_POOL_MAX_CONNECTIONS,
        "current_connections": pool_stats.get("total_connections", 0)
    })
    
    # 初始化核心服务（这些服务在第一次调用时自动初始化）
    log_esp32_service("LLM服务", "开始初始化", {"client_type": "esp32"})
    llm_service = await app.get_llm_service('esp32')
    log_esp32_service("LLM服务", "初始化完成", {
        "service_class": llm_service.__class__.__name__
    })
    
    log_esp32_service("ASR服务", "开始初始化", {})
    asr_service = get_asr_service()
    log_esp32_service("ASR服务", "初始化完成", {
        "service_class": asr_service.__class__.__name__
    })
    
    log_esp32_service("TTS服务", "开始初始化", {})
    tts_service = get_tts_service()
    log_esp32_service("TTS服务", "初始化完成", {
        "service_class": tts_service.__class__.__name__
    })
    
    # 初始化音频缓存
    log_esp32_service("音频缓存服务", "开始初始化", {})
    audio_cache_service = get_audio_cache_service()
    log_esp32_service("音频缓存服务", "初始化完成", {})
    
    # ESP32适配器已集成到WebSocket处理器中
    log_esp32_service("ESP32适配器", "功能已集成到WebSocket处理器", {})
    
    # 记录初始化性能
    initialization_time = time.time() - start_time
    log_esp32_performance("服务器初始化", initialization_time, {
        "services_count": 6,
        "initialization_time": f"{initialization_time:.2f}s"
    })
    
    log_esp32_service("服务器启动", "所有ESP32服务初始化完成", {
        "total_time": f"{initialization_time:.2f}s"
    })
    return True

async def main():
    """启动ESP32设备服务器"""
    try:
        # 设置详细日志级别，确保所有ESP32相关日志都显示
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger('app.devices.esp32').setLevel(logging.INFO)
        logging.getLogger('app.devices.esp32.websocket').setLevel(logging.INFO)
        logging.getLogger('app.devices.esp32.services').setLevel(logging.INFO)
        
        # 使用设备日志系统记录服务器启动
        log_esp32_service("服务器启动", "ESP32设备专用服务器启动中", {})
        
        # 记录配置信息
        log_esp32_service("服务器配置", "显示配置信息", {
            "host": settings.HOST,
            "web_port": settings.PORT,
            "esp32_port": settings.PORT + 1,
            "max_connections": settings.MAX_CONNECTIONS,
            "max_connections_per_ip": settings.MAX_CONNECTIONS_PER_IP
        })
        
        # 创建应用上下文（ESP32专用配置）
        app = create_app(ApplicationConfig(
            name="ESP32 Server",
            version="2.0.0",
            environment=getattr(settings, 'ENVIRONMENT', 'production'),
            enable_esp32=True,
            enable_web=False,
            enable_monitoring=getattr(settings, 'ENABLE_METRICS', False),
            enable_cache=getattr(settings, 'ENABLE_CACHE', True),
            dashscope_api_key=settings.DASHSCOPE_API_KEY
        ))
        set_global_app(app)
        await app.initialize()
        
        # 初始化所有必要的服务（使用依赖注入）
        await initialize_esp32_services(app)
        
        # 创建ESP32处理器
        log_esp32_service("ESP32处理器", "开始创建WebSocket处理器", {})
        esp32_handler = get_esp32_websocket_handler()
        log_esp32_service("ESP32处理器", "WebSocket处理器创建完成", {})
        
        # 启动服务器
        esp32_port = settings.PORT + 1
        log_esp32_service("WebSocket服务器", "启动ESP32 WebSocket服务器", {
            "host": settings.HOST,
            "port": esp32_port,
            "connection_url": f"ws://{settings.HOST}:{esp32_port}"
        })
        # 记录服务器就绪状态
        log_esp32_service("WebSocket服务器", "服务器就绪，等待ESP32设备连接", {
            "log_categories": [
                "设备连接/断开",
                "消息接收/发送", 
                "音频数据处理",
                "AI对话处理",
                "TTS音频生成",
                "错误和警告"
            ]
        })
        # 最终启动确认
        log_esp32_service("服务器启动", "ESP32服务器已就绪，开始监听连接", {
            "status": "ready",
            "listening_address": f"{settings.HOST}:{esp32_port}"
        })
        
        # 启动ESP32服务器
        await esp32_handler.start(settings.HOST, esp32_port)
        
        # 正常退出前关闭应用
        await app.shutdown()

    except KeyboardInterrupt:
        logger.info("")
        logger.info("=" * 60)
        logger.info("⏹️  收到停止信号，正在关闭ESP32服务器...")
        logger.info("=" * 60)
        
        # 显示ESP32设备连接统计信息
        try:
            from app.core.device_logger import get_esp32_stats, get_esp32_device_info, esp32_logger
            
            # 获取ESP32设备统计
            stats = get_esp32_stats()
            logger.info(f"📊 ESP32设备服务器统计:")
            logger.info(f"   运行时间: {stats['uptime_formatted']}")
            logger.info(f"   总连接数: {stats['total_connections']}")
            logger.info(f"   活跃连接: {stats['active_connections']}")
            logger.info(f"   失败连接: {stats['failed_connections']}")
            logger.info(f"   总消息数: {stats['total_messages']}")
            logger.info(f"   音频帧数: {stats['audio_frames']}")
            logger.info(f"   错误数量: {stats['errors']}")
            
            if stats['active_devices']:
                logger.info("   活跃设备:")
                for device_id in stats['active_devices']:
                    device_info = get_esp32_device_info(device_id)
                    if device_info:
                        logger.info(f"     - {device_id}: 连接时长{device_info['connection_duration']:.1f}秒")
            else:
                logger.info("   无活跃设备")
                
            # 记录最终系统状态
            esp32_logger.log_system_status()
            
        except Exception as e:
            logger.debug(f"获取ESP32设备统计信息失败: {e}")
        
        logger.info("✅ ESP32服务器已安全停止")
        
        try:
            await app.shutdown()
        except Exception as e:
            logger.error(f"关闭应用上下文失败: {e}")

    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ ESP32服务器启动失败: {e}")
        logger.error("=" * 60)
        import traceback
        logger.error("详细错误信息:")
        logger.error(traceback.format_exc())
        try:
            await app.shutdown()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
