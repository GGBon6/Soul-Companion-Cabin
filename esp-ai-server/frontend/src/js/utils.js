/**
 * 工具函数模块
 * Utility Functions
 */

class Utils {
    /**
     * 格式化时间戳
     * @param {string|Date} timestamp - 时间戳
     * @returns {string} 格式化后的时间
     */
    static formatTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        
        // 如果是今天，只显示时间
        if (date.toDateString() === now.toDateString()) {
            return `${hours}:${minutes}`;
        }
        
        // 如果是昨天
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (date.toDateString() === yesterday.toDateString()) {
            return `昨天 ${hours}:${minutes}`;
        }
        
        // 如果是今年，显示月日
        if (date.getFullYear() === now.getFullYear()) {
            const month = (date.getMonth() + 1).toString();
            const day = date.getDate().toString();
            return `${month}月${day}日 ${hours}:${minutes}`;
        }
        
        // 其他情况显示完整日期
        return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${hours}:${minutes}`;
    }
    
    /**
     * 格式化时间分隔符
     * @param {Date} time - 时间对象
     * @returns {string} 格式化后的时间
     */
    static formatTimeDivider(time) {
        const now = new Date();
        const date = new Date(time);
        
        // 如果是今天
        if (date.toDateString() === now.toDateString()) {
            const hours = date.getHours().toString().padStart(2, '0');
            const minutes = date.getMinutes().toString().padStart(2, '0');
            return `今天 ${hours}:${minutes}`;
        }
        
        // 如果是昨天
        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (date.toDateString() === yesterday.toDateString()) {
            const hours = date.getHours().toString().padStart(2, '0');
            const minutes = date.getMinutes().toString().padStart(2, '0');
            return `昨天 ${hours}:${minutes}`;
        }
        
        // 如果是本周内
        const weekAgo = new Date(now);
        weekAgo.setDate(weekAgo.getDate() - 7);
        if (date > weekAgo) {
            const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
            const hours = date.getHours().toString().padStart(2, '0');
            const minutes = date.getMinutes().toString().padStart(2, '0');
            return `${weekdays[date.getDay()]} ${hours}:${minutes}`;
        }
        
        // 其他情况
        const month = (date.getMonth() + 1).toString();
        const day = date.getDate().toString();
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        
        if (date.getFullYear() === now.getFullYear()) {
            return `${month}月${day}日 ${hours}:${minutes}`;
        }
        
        return `${date.getFullYear()}年${month}月${day}日 ${hours}:${minutes}`;
    }
    
    /**
     * 显示Toast提示
     * @param {string} message - 提示消息
     * @param {string} type - 类型 (success, error, warning, info)
     * @param {number} duration - 显示时长（毫秒）
     */
    static showToast(message, type = 'info', duration = 3000) {
        const container = document.getElementById('toastContainer') || document.body;
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        container.appendChild(toast);
        
        // 触发动画
        setTimeout(() => toast.classList.add('show'), 10);
        
        // 自动移除
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
    
    /**
     * 转义HTML特殊字符
     * @param {string} text - 原始文本
     * @returns {string} 转义后的文本
     */
    static escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    /**
     * 滚动到容器底部
     * @param {HTMLElement} container - 容器元素
     * @param {boolean} smooth - 是否平滑滚动
     */
    static scrollToBottom(container, smooth = true) {
        if (!container) return;
        
        if (smooth) {
            container.scrollTo({
                top: container.scrollHeight,
                behavior: 'smooth'
            });
        } else {
            container.scrollTop = container.scrollHeight;
        }
    }
    
    /**
     * 检查是否接近底部
     * @param {HTMLElement} container - 容器元素
     * @param {number} threshold - 阈值（像素）
     * @returns {boolean} 是否接近底部
     */
    static isNearBottom(container, threshold = 100) {
        if (!container) return true;
        return container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
    }
    
    /**
     * 防抖函数
     * @param {Function} func - 要防抖的函数
     * @param {number} wait - 等待时间（毫秒）
     * @returns {Function} 防抖后的函数
     */
    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    /**
     * 节流函数
     * @param {Function} func - 要节流的函数
     * @param {number} limit - 时间限制（毫秒）
     * @returns {Function} 节流后的函数
     */
    static throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
    
    /**
     * 生成唯一ID
     * @returns {string} 唯一ID
     */
    static generateId() {
        return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }
    
    /**
     * 将Base64转换为Blob
     * @param {string} base64 - Base64字符串
     * @param {string} mimeType - MIME类型
     * @returns {Blob} Blob对象
     */
    static base64ToBlob(base64, mimeType = 'audio/wav') {
        const byteCharacters = atob(base64);
        const byteNumbers = new Array(byteCharacters.length);
        
        for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        
        const byteArray = new Uint8Array(byteNumbers);
        return new Blob([byteArray], { type: mimeType });
    }
    
    /**
     * 日志输出（支持调试模式控制）
     * @param  {...any} args - 日志参数
     */
    static log(...args) {
        if (window.CONFIG && window.CONFIG.DEBUG) {
            console.log('[VoiceChat]', ...args);
        }
    }
    
    /**
     * 错误日志输出
     * @param  {...any} args - 错误参数
     */
    static error(...args) {
        console.error('[VoiceChat Error]', ...args);
    }
    
    /**
     * 警告日志输出
     * @param  {...any} args - 警告参数
     */
    static warn(...args) {
        console.warn('[VoiceChat Warning]', ...args);
    }
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Utils;
}

if (typeof window !== 'undefined') {
    window.Utils = Utils;
}

