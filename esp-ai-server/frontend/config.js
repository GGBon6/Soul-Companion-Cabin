/**
 * 前端配置文件
 * Frontend Configuration
 */

const CONFIG = {
    // WebSocket配置
    WEBSOCKET: {
        // 根据环境自动选择协议和主机
        get URL() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.hostname || 'localhost';
            const port = 8766;
            return `${protocol}//${host}:${port}`;
        },
        RECONNECT_ATTEMPTS: 5,
        RECONNECT_DELAY: 3000,
        HEARTBEAT_INTERVAL: 30000,    // 30秒
        HEARTBEAT_TIMEOUT: 60000,      // 60秒
        IDLE_TIMEOUT: 300000           // 5分钟
    },
    
    // 音频配置
    AUDIO: {
        SAMPLE_RATE: 16000,
        CHUNK_SIZE: 3200,
        FORMAT: 'webm',
        MIME_TYPE: 'audio/webm;codecs=opus'
    },
    
    // UI配置
    UI: {
        MESSAGE_MAX_LENGTH: 500,
        TOAST_DURATION: 3000,
        TYPING_INDICATOR_DELAY: 100,
        TIME_DIVIDER_THRESHOLD: 5 * 60 * 1000  // 5分钟
    },
    
    // 本地存储键名
    STORAGE_KEYS: {
        USER_MODE: 'userMode',
        USER_INFO: 'userInfo',
        CHAT_HISTORY: 'chatHistory'
    },
    
    // API端点（预留）
    API: {
        BASE_URL: '/api'
    },
    
    // 调试模式
    DEBUG: false,
    
    // 版本信息
    VERSION: '1.0.0',
    APP_NAME: '心灵小屋 - 青少年心理健康对话系统'
};

// 导出配置（ES6模块）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG;
}

// 全局变量（用于脚本标签引入）
if (typeof window !== 'undefined') {
    window.CONFIG = CONFIG;
}

