"""
配置管理系统
Configuration Management System
支持环境变量和多环境配置
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量，指定编码
try:
    load_dotenv(encoding='utf-8')
except UnicodeDecodeError:
    # 如果UTF-8失败，尝试其他编码
    try:
        load_dotenv(encoding='gbk')
    except UnicodeDecodeError:
        load_dotenv(encoding='latin1')


class Settings:
    """应用配置类"""
    
    # ==================== 项目信息 ====================
    PROJECT_NAME: str = "Tomoe Chat System"
    VERSION: str = "2.0.0"
    DESCRIPTION: str = "心理健康对话系统"
    
    # 服务配置
    SERVICE_NAME: str = os.getenv("SERVICE_NAME", "小智AI服务")
    SERVICE_VERSION: str = os.getenv("SERVICE_VERSION", "2.0.0")
    
    # 客户端类型支持
    SUPPORTED_CLIENTS: list = os.getenv("SUPPORTED_CLIENTS", "esp32,web,mobile,desktop").split(",")
    
    # ==================== 环境配置 ====================
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")  # development/production/test
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    
    # ==================== 服务器配置 ====================
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8766"))
    HTTP_PORT: int = int(os.getenv("HTTP_PORT", "8080"))  # HTTP API端口
    
    # 协议配置
    ENABLE_OTA: bool = os.getenv("ENABLE_OTA", "true").lower() == "true"
    ENABLE_WEBSOCKET: bool = os.getenv("ENABLE_WEBSOCKET", "true").lower() == "true"
    ENABLE_HTTP_API: bool = os.getenv("ENABLE_HTTP_API", "false").lower() == "true"
    
    # ==================== 路径配置 ====================
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = BASE_DIR / "logs"
    
    # 数据子目录
    USERS_DIR: Path = DATA_DIR / "users"
    CHAT_HISTORY_DIR: Path = DATA_DIR / "chat_history"
    USER_PROFILES_DIR: Path = DATA_DIR / "user_profiles"
    
    # ==================== 安全配置 ====================
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    PASSWORD_SALT: str = os.getenv("PASSWORD_SALT", "tomoe-chat-salt")
    
    # JWT配置（预留）
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24小时
    
    # ==================== AI服务配置 ====================
    # DashScope API配置
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    
    # LLM配置
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-plus")
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.8"))
    
    # LLM并发控制配置
    LLM_MAX_CONCURRENT: int = int(os.getenv("LLM_MAX_CONCURRENT", "50"))  # 全局最大并发数
    LLM_WEB_MAX_CONCURRENT: int = int(os.getenv("LLM_WEB_MAX_CONCURRENT", "30"))  # Web端最大并发
    LLM_ESP32_MAX_CONCURRENT: int = int(os.getenv("LLM_ESP32_MAX_CONCURRENT", "15"))  # ESP32最大并发
    LLM_SYSTEM_MAX_CONCURRENT: int = int(os.getenv("LLM_SYSTEM_MAX_CONCURRENT", "5"))  # 系统最大并发
    
    # ASR配置
    ASR_MODEL: str = os.getenv("ASR_MODEL", "paraformer-realtime-v2")
    ASR_SAMPLE_RATE: int = int(os.getenv("ASR_SAMPLE_RATE", "16000"))
    
    # ASR连接池配置
    ASR_POOL_MIN_CONNECTIONS: int = int(os.getenv("ASR_POOL_MIN_CONNECTIONS", "2"))
    ASR_POOL_MAX_CONNECTIONS: int = int(os.getenv("ASR_POOL_MAX_CONNECTIONS", "10"))
    ASR_POOL_MAX_IDLE_TIME: int = int(os.getenv("ASR_POOL_MAX_IDLE_TIME", "300"))
    ASR_POOL_HEALTH_CHECK_INTERVAL: int = int(os.getenv("ASR_POOL_HEALTH_CHECK_INTERVAL", "60"))
    ASR_POOL_ACQUIRE_TIMEOUT: float = float(os.getenv("ASR_POOL_ACQUIRE_TIMEOUT", "30.0"))
    
    # TTS配置
    TTS_MODEL: str = os.getenv("TTS_MODEL", "cosyvoice-v2")
    TTS_VOICE: str = os.getenv("TTS_VOICE", "longhan_v2")
    TTS_SAMPLE_RATE: int = int(os.getenv("TTS_SAMPLE_RATE", "22050"))
    TTS_VOLUME: int = int(os.getenv("TTS_VOLUME", "50"))
    TTS_SPEECH_RATE: float = float(os.getenv("TTS_SPEECH_RATE", "1.0"))
    
    # ==================== 业务配置 ====================
    # 对话历史
    MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "50"))
    MAX_CONTEXT_MESSAGES: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
    
    # WebSocket配置
    HEARTBEAT_INTERVAL: int = int(os.getenv("HEARTBEAT_INTERVAL", "30"))  # 秒
    HEARTBEAT_TIMEOUT: int = int(os.getenv("HEARTBEAT_TIMEOUT", "60"))  # 秒
    IDLE_TIMEOUT: int = int(os.getenv("IDLE_TIMEOUT", "300"))  # 秒
    
    # ==================== 连接池配置 ====================
    # 连接数限制
    MAX_CONNECTIONS: int = int(os.getenv("MAX_CONNECTIONS", "1000"))  # 最大连接数
    MAX_CONNECTIONS_PER_IP: int = int(os.getenv("MAX_CONNECTIONS_PER_IP", "10"))  # 单IP最大连接数
    CONNECTION_RATE_LIMIT: int = int(os.getenv("CONNECTION_RATE_LIMIT", "5"))  # 每秒最大新连接数
    
    # 连接健康检查
    HEALTH_CHECK_INTERVAL: int = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))  # 健康检查间隔(秒)
    HEALTH_CHECK_TIMEOUT: int = int(os.getenv("HEALTH_CHECK_TIMEOUT", "10"))  # 健康检查超时(秒)
    PING_INTERVAL: int = int(os.getenv("PING_INTERVAL", "30"))  # Ping间隔(秒)
    PONG_TIMEOUT: int = int(os.getenv("PONG_TIMEOUT", "10"))  # Pong超时(秒)
    
    # 自动重连配置
    ENABLE_AUTO_RECONNECT: bool = os.getenv("ENABLE_AUTO_RECONNECT", "true").lower() == "true"
    RECONNECT_INTERVAL: int = int(os.getenv("RECONNECT_INTERVAL", "5"))  # 重连间隔(秒)
    MAX_RECONNECT_ATTEMPTS: int = int(os.getenv("MAX_RECONNECT_ATTEMPTS", "3"))  # 最大重连次数
    RECONNECT_BACKOFF_FACTOR: float = float(os.getenv("RECONNECT_BACKOFF_FACTOR", "1.5"))  # 重连退避因子
    
    # 连接池监控
    ENABLE_CONNECTION_METRICS: bool = os.getenv("ENABLE_CONNECTION_METRICS", "true").lower() == "true"
    METRICS_COLLECTION_INTERVAL: int = int(os.getenv("METRICS_COLLECTION_INTERVAL", "30"))  # 指标收集间隔(秒)
    
    # 用户配置
    MIN_USERNAME_LENGTH: int = 3
    MIN_PASSWORD_LENGTH: int = 6
    
    # ==================== 日志配置 ====================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")  # DEBUG/INFO/WARNING/ERROR/CRITICAL
    LOG_FILE: str = os.getenv("LOG_FILE", "app.log")
    LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # ==================== 数据库配置 ====================
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL", None)
    
    # ==================== Redis配置 ====================
    # Redis连接配置
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    REDIS_USERNAME: Optional[str] = os.getenv("REDIS_USERNAME", None)
    
    # Redis连接池配置
    REDIS_MAX_CONNECTIONS: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))
    REDIS_CONNECTION_TIMEOUT: int = int(os.getenv("REDIS_CONNECTION_TIMEOUT", "5"))
    REDIS_SOCKET_TIMEOUT: int = int(os.getenv("REDIS_SOCKET_TIMEOUT", "5"))
    REDIS_RETRY_ON_TIMEOUT: bool = os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"
    
    # Redis功能开关
    ENABLE_REDIS: bool = os.getenv("ENABLE_REDIS", "false").lower() == "true"
    ENABLE_DISTRIBUTED_SESSIONS: bool = os.getenv("ENABLE_DISTRIBUTED_SESSIONS", "false").lower() == "true"
    ENABLE_USER_STATE_SYNC: bool = os.getenv("ENABLE_USER_STATE_SYNC", "false").lower() == "true"
    ENABLE_REDIS_PUBSUB: bool = os.getenv("ENABLE_REDIS_PUBSUB", "false").lower() == "true"
    
    # Redis键前缀和TTL配置
    REDIS_KEY_PREFIX: str = os.getenv("REDIS_KEY_PREFIX", "esp_ai")
    USER_STATE_TTL: int = int(os.getenv("USER_STATE_TTL", "3600"))  # 用户状态TTL(秒)
    SESSION_TTL: int = int(os.getenv("SESSION_TTL", "86400"))  # 会话TTL(秒)
    CONNECTION_STATE_TTL: int = int(os.getenv("CONNECTION_STATE_TTL", "300"))  # 连接状态TTL(秒)
    
    # Redis健康检查
    REDIS_HEALTH_CHECK_INTERVAL: int = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))  # 健康检查间隔(秒)
    REDIS_PING_TIMEOUT: int = int(os.getenv("REDIS_PING_TIMEOUT", "3"))  # Ping超时(秒)
    
    # ==================== 缓存优化配置 ====================
    # 缓存功能开关
    ENABLE_CACHE: bool = os.getenv("ENABLE_CACHE", "true").lower() == "true"
    ENABLE_LLM_CACHE: bool = os.getenv("ENABLE_LLM_CACHE", "true").lower() == "true"
    ENABLE_USER_PROFILE_CACHE: bool = os.getenv("ENABLE_USER_PROFILE_CACHE", "true").lower() == "true"
    ENABLE_MEMORY_CACHE: bool = os.getenv("ENABLE_MEMORY_CACHE", "true").lower() == "true"
    
    # LLM缓存配置
    LLM_CACHE_TTL: int = int(os.getenv("LLM_CACHE_TTL", "3600"))  # LLM缓存TTL(秒) - 1小时
    LLM_CACHE_MAX_SIZE: int = int(os.getenv("LLM_CACHE_MAX_SIZE", "10000"))  # LLM缓存最大条目数
    LLM_CACHE_SIMILARITY_THRESHOLD: float = float(os.getenv("LLM_CACHE_SIMILARITY_THRESHOLD", "0.9"))  # 相似度阈值
    
    # 用户画像缓存配置
    USER_PROFILE_CACHE_TTL: int = int(os.getenv("USER_PROFILE_CACHE_TTL", "1800"))  # 用户画像缓存TTL(秒) - 30分钟
    USER_PROFILE_CACHE_MAX_SIZE: int = int(os.getenv("USER_PROFILE_CACHE_MAX_SIZE", "5000"))  # 用户画像缓存最大条目数
    USER_PROFILE_REFRESH_INTERVAL: int = int(os.getenv("USER_PROFILE_REFRESH_INTERVAL", "300"))  # 画像刷新间隔(秒)
    
    # 内存缓存配置
    MEMORY_CACHE_MAX_SIZE: int = int(os.getenv("MEMORY_CACHE_MAX_SIZE", "1000"))  # 内存缓存最大条目数
    MEMORY_CACHE_TTL: int = int(os.getenv("MEMORY_CACHE_TTL", "600"))  # 内存缓存TTL(秒) - 10分钟
    
    # 缓存清理配置
    CACHE_CLEANUP_INTERVAL: int = int(os.getenv("CACHE_CLEANUP_INTERVAL", "300"))  # 缓存清理间隔(秒)
    CACHE_STATS_INTERVAL: int = int(os.getenv("CACHE_STATS_INTERVAL", "60"))  # 缓存统计间隔(秒)
    
    # ==================== CORS配置 ====================
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")
    
    # ==================== 监控配置（预留） ====================
    ENABLE_METRICS: bool = os.getenv("ENABLE_METRICS", "False").lower() == "true"
    METRICS_PORT: int = int(os.getenv("METRICS_PORT", "9090"))
    
    def __init__(self):
        """初始化配置，创建必要的目录"""
        self._create_directories()
    
    def _create_directories(self):
        """创建必要的目录"""
        directories = [
            self.DATA_DIR,
            self.LOGS_DIR,
            self.USERS_DIR,
            self.CHAT_HISTORY_DIR,
            self.USER_PROFILES_DIR,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self.ENVIRONMENT == "production"
    
    def is_development(self) -> bool:
        """是否为开发环境"""
        return self.ENVIRONMENT == "development"
    
    def is_test(self) -> bool:
        """是否为测试环境"""
        return self.ENVIRONMENT == "test"
    
    def get_log_file_path(self) -> Path:
        """获取日志文件完整路径"""
        return self.LOGS_DIR / self.LOG_FILE
    
    def dict(self) -> dict:
        """返回配置字典（隐藏敏感信息）"""
        return {
            "PROJECT_NAME": self.PROJECT_NAME,
            "VERSION": self.VERSION,
            "SERVICE_NAME": self.SERVICE_NAME,
            "SERVICE_VERSION": self.SERVICE_VERSION,
            "SUPPORTED_CLIENTS": self.SUPPORTED_CLIENTS,
            "ENVIRONMENT": self.ENVIRONMENT,
            "DEBUG": self.DEBUG,
            "HOST": self.HOST,
            "PORT": self.PORT,
            "HTTP_PORT": self.HTTP_PORT,
            "ENABLE_OTA": self.ENABLE_OTA,
            "ENABLE_WEBSOCKET": self.ENABLE_WEBSOCKET,
            "ENABLE_HTTP_API": self.ENABLE_HTTP_API,
            "LLM_MODEL": self.LLM_MODEL,
            "ASR_MODEL": self.ASR_MODEL,
            "TTS_MODEL": self.TTS_MODEL,
            "TTS_VOICE": self.TTS_VOICE,
        }


# 全局配置实例
settings = Settings()


if __name__ == "__main__":
    # 测试配置
    print("=" * 50)
    print(f"项目名称: {settings.PROJECT_NAME}")
    print(f"版本: {settings.VERSION}")
    print(f"环境: {settings.ENVIRONMENT}")
    print(f"调试模式: {settings.DEBUG}")
    print(f"服务器: {settings.HOST}:{settings.PORT}")
    print("=" * 50)
    print(f"数据目录: {settings.DATA_DIR}")
    print(f"日志目录: {settings.LOGS_DIR}")
    print("=" * 50)
    print(f"LLM模型: {settings.LLM_MODEL}")
    print(f"ASR模型: {settings.ASR_MODEL}")
    print(f"TTS模型: {settings.TTS_MODEL}")
    print(f"TTS音色: {settings.TTS_VOICE}")
    print("=" * 50)

