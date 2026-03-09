/**
 * 认证模块
 * Authentication Module
 * 处理用户登录、注册、会话管理
 */

class AuthManager {
    constructor() {
        this.wsUrl = null;
        this.ws = null;
        this.pendingAuth = false;
        this.onAuthSuccess = null;
        this.onAuthFailed = null;
    }
    
    /**
     * 初始化WebSocket URL
     */
    initWebSocketUrl() {
        if (window.CONFIG && window.CONFIG.WEBSOCKET) {
            this.wsUrl = window.CONFIG.WEBSOCKET.URL;
        } else {
            // 回退到默认配置
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.hostname || 'localhost';
            this.wsUrl = `${protocol}//${host}:8766`;
        }
    }
    
    /**
     * 连接WebSocket
     * @returns {Promise<WebSocket>}
     */
    async connectWebSocket() {
        return new Promise((resolve, reject) => {
            try {
                if (!this.wsUrl) {
                    this.initWebSocketUrl();
                }
                
                this.ws = new WebSocket(this.wsUrl);
                
                this.ws.onopen = () => {
                    Utils.log('WebSocket connected for authentication');
                    resolve(this.ws);
                };
                
                this.ws.onerror = (error) => {
                    Utils.error('WebSocket connection error:', error);
                    reject(new Error('无法连接到服务器'));
                };
                
                this.ws.onmessage = (event) => {
                    this.handleMessage(event.data);
                };
                
            } catch (error) {
                reject(error);
            }
        });
    }
    
    /**
     * 处理WebSocket消息
     * @param {string} data - 消息数据
     */
    handleMessage(data) {
        try {
            const message = JSON.parse(data);
            const type = message.type;
            
            switch(type) {
                case 'login_success':
                    this.onLoginSuccess(message.content);
                    break;
                
                case 'login_failed':
                    this.onLoginFailed(message.content);
                    break;
                
                case 'register_success':
                    this.onRegisterSuccess(message.content);
                    break;
                
                case 'register_failed':
                    this.onRegisterFailed(message.content);
                    break;
                
                case 'reset_password_success':
                    this.onResetPasswordSuccess(message.content);
                    break;
                
                case 'reset_password_failed':
                    this.onResetPasswordFailed(message.content);
                    break;
            }
        } catch (error) {
            Utils.error('Failed to parse message:', error);
        }
    }
    
    /**
     * 用户登录
     * @param {string} username - 用户名
     * @param {string} password - 密码
     * @returns {Promise<Object>} 用户信息
     */
    async login(username, password) {
        return new Promise(async (resolve, reject) => {
            try {
                // 验证输入
                if (!username || !password) {
                    reject(new Error('请填写完整信息'));
                    return;
                }
                
                // 连接WebSocket
                if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                    await this.connectWebSocket();
                }
                
                this.pendingAuth = true;
                
                // 设置回调
                this.onAuthSuccess = (userInfo) => {
                    this.pendingAuth = false;
                    resolve(userInfo);
                };
                
                this.onAuthFailed = (message) => {
                    this.pendingAuth = false;
                    reject(new Error(message));
                };
                
                // 发送登录请求
                this.ws.send(JSON.stringify({
                    type: 'login',
                    username: username,
                    password: password
                }));
                
            } catch (error) {
                this.pendingAuth = false;
                reject(error);
            }
        });
    }
    
    /**
     * 用户注册
     * @param {string} username - 用户名
     * @param {string} password - 密码
     * @param {string} nickname - 昵称
     * @returns {Promise<Object>} 用户信息
     */
    async register(username, password, nickname = null) {
        return new Promise(async (resolve, reject) => {
            try {
                // 验证输入
                if (!username || !password) {
                    reject(new Error('请填写完整信息'));
                    return;
                }
                
                if (username.length < 3) {
                    reject(new Error('用户名至少需要3个字符'));
                    return;
                }
                
                if (password.length < 6) {
                    reject(new Error('密码至少需要6个字符'));
                    return;
                }
                
                // 连接WebSocket
                if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                    await this.connectWebSocket();
                }
                
                this.pendingAuth = true;
                
                // 设置回调
                this.onAuthSuccess = (userInfo) => {
                    this.pendingAuth = false;
                    resolve(userInfo);
                };
                
                this.onAuthFailed = (message) => {
                    this.pendingAuth = false;
                    reject(new Error(message));
                };
                
                // 发送注册请求
                this.ws.send(JSON.stringify({
                    type: 'register',
                    username: username,
                    password: password,
                    nickname: nickname || username
                }));
                
            } catch (error) {
                this.pendingAuth = false;
                reject(error);
            }
        });
    }
    
    /**
     * 登录成功回调
     * @param {Object} userInfo - 用户信息
     */
    onLoginSuccess(userInfo) {
        Utils.log('Login successful:', userInfo);
        
        // 存储用户信息
        this.saveUserInfo(userInfo);
        
        if (this.onAuthSuccess) {
            this.onAuthSuccess(userInfo);
        }
    }
    
    /**
     * 登录失败回调
     * @param {string} message - 错误消息
     */
    onLoginFailed(message) {
        Utils.error('Login failed:', message);
        
        if (this.onAuthFailed) {
            this.onAuthFailed(message || '登录失败');
        }
    }
    
    /**
     * 注册成功回调
     * @param {Object} userInfo - 用户信息
     */
    onRegisterSuccess(userInfo) {
        Utils.log('Registration successful:', userInfo);
        
        // 存储用户信息
        this.saveUserInfo(userInfo);
        
        if (this.onAuthSuccess) {
            this.onAuthSuccess(userInfo);
        }
    }
    
    /**
     * 注册失败回调
     * @param {string} message - 错误消息
     */
    onRegisterFailed(message) {
        Utils.error('Registration failed:', message);
        
        if (this.onAuthFailed) {
            this.onAuthFailed(message || '注册失败');
        }
    }
    
    /**
     * 重置密码
     * @param {string} username - 用户名
     * @param {string} newPassword - 新密码
     * @returns {Promise<Object>} 重置结果
     */
    async resetPassword(username, newPassword) {
        return new Promise(async (resolve, reject) => {
            try {
                // 验证输入
                if (!username || !newPassword) {
                    reject(new Error('请填写完整信息'));
                    return;
                }
                
                if (newPassword.length < 6) {
                    reject(new Error('密码至少需要6个字符'));
                    return;
                }
                
                // 连接WebSocket
                if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                    await this.connectWebSocket();
                }
                
                this.pendingAuth = true;
                
                // 设置回调
                this.onAuthSuccess = (result) => {
                    this.pendingAuth = false;
                    resolve(result);
                };
                
                this.onAuthFailed = (message) => {
                    this.pendingAuth = false;
                    reject(new Error(message));
                };
                
                // 发送重置密码请求
                this.ws.send(JSON.stringify({
                    type: 'reset_password',
                    username: username,
                    new_password: newPassword
                }));
                
            } catch (error) {
                this.pendingAuth = false;
                reject(error);
            }
        });
    }
    
    /**
     * 重置密码成功回调
     * @param {Object} result - 重置结果
     */
    onResetPasswordSuccess(result) {
        Utils.log('Password reset successful:', result);
        
        if (this.onAuthSuccess) {
            this.onAuthSuccess(result);
        }
    }
    
    /**
     * 重置密码失败回调
     * @param {string} message - 错误消息
     */
    onResetPasswordFailed(message) {
        Utils.error('Password reset failed:', message);
        
        if (this.onAuthFailed) {
            this.onAuthFailed(message || '密码重置失败');
        }
    }
    
    /**
     * 保存用户信息到本地存储
     * @param {Object} userInfo - 用户信息
     */
    saveUserInfo(userInfo) {
        const storageKeys = window.CONFIG?.STORAGE_KEYS || {
            USER_MODE: 'userMode',
            USER_INFO: 'userInfo'
        };
        
        localStorage.setItem(storageKeys.USER_MODE, 'user');
        localStorage.setItem(storageKeys.USER_INFO, JSON.stringify(userInfo));
    }
    
    /**
     * 获取当前用户信息
     * @returns {Object|null} 用户信息
     */
    getUserInfo() {
        const storageKeys = window.CONFIG?.STORAGE_KEYS || {
            USER_MODE: 'userMode',
            USER_INFO: 'userInfo'
        };
        
        const userMode = localStorage.getItem(storageKeys.USER_MODE);
        const userInfoStr = localStorage.getItem(storageKeys.USER_INFO);
        
        if (userMode === 'user' && userInfoStr) {
            try {
                return JSON.parse(userInfoStr);
            } catch (error) {
                Utils.error('Failed to parse user info:', error);
                return null;
            }
        }
        
        return null;
    }
    
    /**
     * 静态方法：获取当前用户信息
     * @returns {Object|null} 用户信息
     */
    static getUserInfo() {
        const storageKeys = window.CONFIG?.STORAGE_KEYS || {
            USER_MODE: 'userMode',
            USER_INFO: 'userInfo'
        };
        
        const userMode = localStorage.getItem(storageKeys.USER_MODE);
        const userInfoStr = localStorage.getItem(storageKeys.USER_INFO);
        
        if (userMode === 'user' && userInfoStr) {
            try {
                return JSON.parse(userInfoStr);
            } catch (error) {
                console.error('Failed to parse user info:', error);
                return null;
            }
        }
        
        return null;
    }
    
    /**
     * 检查是否已登录
     * @returns {boolean} 是否已登录
     */
    isLoggedIn() {
        return this.getUserInfo() !== null;
    }
    
    /**
     * 是否游客模式
     * @returns {boolean} 是否游客模式
     */
    isGuestMode() {
        const storageKeys = window.CONFIG?.STORAGE_KEYS || {
            USER_MODE: 'userMode'
        };
        
        const userMode = localStorage.getItem(storageKeys.USER_MODE);
        return userMode === 'guest';
    }
    
    /**
     * 设置游客模式
     */
    setGuestMode() {
        const storageKeys = window.CONFIG?.STORAGE_KEYS || {
            USER_MODE: 'userMode',
            USER_INFO: 'userInfo'
        };
        
        localStorage.setItem(storageKeys.USER_MODE, 'guest');
        localStorage.removeItem(storageKeys.USER_INFO);
    }
    
    /**
     * 登出
     */
    logout() {
        const storageKeys = window.CONFIG?.STORAGE_KEYS || {
            USER_MODE: 'userMode',
            USER_INFO: 'userInfo'
        };
        
        localStorage.removeItem(storageKeys.USER_MODE);
        localStorage.removeItem(storageKeys.USER_INFO);
        
        Utils.log('User logged out');
    }
    
    /**
     * 关闭WebSocket连接
     */
    close() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AuthManager;
}

if (typeof window !== 'undefined') {
    window.AuthManager = AuthManager;
}

