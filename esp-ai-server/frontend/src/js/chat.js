/**
 * 心灵小屋 - 对话系统核心类
 * 处理WebSocket通信、消息显示、语音交互等
 * 版本: 20251113163800 - 修复消息解析和teenFeatures引用
 */
console.log('🔧 chat.js 已加载 - 版本: 20251113163800 - 修复消息解析和teenFeatures引用');

class VoiceChat {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        
        // 心跳保活机制
        this.heartbeatInterval = null;      // 心跳定时器
        this.heartbeatTimeout = null;       // 心跳超时定时器
        this.idleTimeout = null;            // 空闲超时定时器
        this.lastActivityTime = Date.now(); // 最后活动时间
        this.HEARTBEAT_INTERVAL = 30000;    // 心跳间隔30秒
        this.HEARTBEAT_TIMEOUT = 60000;     // 心跳超时60秒（TTS合成长文本可能需要较长时间）
        this.IDLE_TIMEOUT = 300000;         // 空闲超时5分钟（无任何活动）
        this.isIdle = false;                // 是否处于空闲状态
        
        // 音频相关
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.audioContext = null;
        this.audioQueue = [];
        this.isPlaying = false;
        this.currentAudioSource = null;     // 当前播放的音频源（AudioContext）
        this.currentHtmlAudio = null;        // 当前播放的HTML5音频
        
        // DOM 元素
        this.messagesContainer = document.getElementById('messages');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.recordBtn = document.getElementById('recordBtn');
        this.statusIndicator = document.getElementById('statusIndicator');
        this.statusText = document.getElementById('statusText');
        this.chatContainer = document.getElementById('chatContainer');
        this.voiceModeToggle = document.getElementById('voiceModeToggle');
        this.statusBar = document.getElementById('statusBar');
        this.audioVisualizer = document.getElementById('audioVisualizer');
        
        // 状态
        this.isRecording = false;
        this.isTyping = false;
        this.typingElement = null;
        this.voiceEnabled = true;
        this.lastMessageTime = null;  // 上一条消息的时间戳
        
        // Toast 容器
        this.toastContainer = document.getElementById('toastContainer');
        
        // 语音消息存储
        this.pendingAssistantTexts = [];    // 待显示的助手文本（数组，支持多条）
        this.audioMessages = new Map();      // 存储语音消息数据
        this.unplayedVoices = [];            // 未播放的语音队列
        this.currentPlayingVoice = null;     // 当前正在播放的语音ID
        
        // 用户信息
        this.userMode = localStorage.getItem('userMode') || 'guest';
        this.userInfo = null;
        if (this.userMode === 'user') {
            const userInfoStr = localStorage.getItem('userInfo');
            this.userInfo = userInfoStr ? JSON.parse(userInfoStr) : null;
        }
        this.historyLoaded = false;  // 历史消息是否已加载
        this.pendingCharacterSync = null;  // 待同步的角色设置
        
        // 游客模式：清除可能存在的旧缓存
        if (this.userMode === 'guest') {
            const guestKey = 'CHAT_HISTORY:guest';
            localStorage.removeItem(guestKey);
        }
        
        this.init();
    }
    
    async init() {
        // 检查登录状态并显示用户信息
        this.displayUserInfo();
        // 预渲染：从本地缓存快速展示最近对话，避免空白/闪烁（游客模式跳过）
        if (this.userMode !== 'guest') {
            try { this.preloadConversationFromCache(); } catch (e) { console.warn('预渲染失败', e); }
        }
        
        // 初始化音频上下文
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        
        // 在用户第一次交互时恢复AudioContext（浏览器安全限制）
        const resumeAudioContext = async () => {
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
                console.log('🔊 AudioContext已在用户交互后恢复');
                
                // 恢复后，如果有未播放的语音，自动播放
                if (this.unplayedVoices && this.unplayedVoices.length > 0) {
                    console.log(`📢 开始自动播放 ${this.unplayedVoices.length} 条待播语音`);
                    setTimeout(() => this.playNextUnplayedVoice(), 500);
                }
            }
        };
        
        // 监听多种用户交互事件
        document.addEventListener('click', resumeAudioContext, { once: true });
        document.addEventListener('keydown', resumeAudioContext, { once: true });
        document.addEventListener('touchstart', resumeAudioContext, { once: true });
        
        // 绑定事件
        this.sendBtn.addEventListener('click', () => this.sendTextMessage());
        this.voiceModeToggle.addEventListener('change', (e) => {
            this.voiceEnabled = e.target.checked;
            // 发送语音设置到后端
            this.updateVoiceSettings(this.voiceEnabled);
        });
        
        // 录音按钮 - 按住说话
        this.recordBtn.addEventListener('mousedown', () => this.startRecording());
        this.recordBtn.addEventListener('mouseup', () => this.stopRecording());
        this.recordBtn.addEventListener('mouseleave', () => {
            if (this.isRecording) this.stopRecording();
        });
        
        // 触摸设备支持
        this.recordBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.startRecording();
        });
        this.recordBtn.addEventListener('touchend', (e) => {
            e.preventDefault();
            this.stopRecording();
        });
        
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendTextMessage();
            }
        });
        
        this.messageInput.addEventListener('input', () => {
            this.autoResizeTextarea();
        });
        
        // 绑定设置按钮事件
        const settingsBtn = document.getElementById('settingsBtn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => {
                document.getElementById('settingsModal').style.display = 'flex';
                // 打开设置面板时加载个人信息
                if (this.userMode === 'user') {
                    setTimeout(() => this.loadProfileInfo(), 100);
                }
            });
        }
        
        // 绑定保存个人信息按钮
        const saveProfileBtn = document.getElementById('saveProfileBtn');
        if (saveProfileBtn) {
            saveProfileBtn.addEventListener('click', () => this.saveProfileInfo());
        }
        
        // 绑定退出登录按钮
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.logout());
        }
        
        // 连接 WebSocket
        this.connect();
    }
    
    connect() {
        const wsUrl = 'ws://localhost:8766';  // 语音服务器端口
        this.updateStatus('connecting', '正在连接...');
        
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket 连接成功');
                this.reconnectAttempts = 0;
                this.updateStatus('connected', '在线');
                this.enableInput();
                
                // 启动心跳和空闲检测
                this.startHeartbeat();
                this.startIdleDetection();
                this.updateActivity();
                
                // 如果是已登录用户，发送登录信息并加载历史
                if (this.userMode === 'user' && this.userInfo && !this.historyLoaded) {
                    this.loginToServer();
                    setTimeout(() => {
                        this.loadHistory();
                    }, 500);  // 延迟加载历史，等待登录完成
                } else if (this.userMode === 'guest') {
                    // 游客模式：清空消息区域，每次都是全新对话
                    this.messagesContainer.innerHTML = '';
                    console.log('🎭 游客模式：开始全新对话');
                }
            };
            
            this.ws.onmessage = (event) => {
                this.handleMessage(event.data);
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket 连接断开');
                this.updateStatus('disconnected', '已断开');
                this.disableInput();
                
                // 停止心跳和空闲检测
                this.stopHeartbeat();
                this.stopIdleDetection();
                
                // 如果不是空闲状态导致的断开，尝试重连
                if (!this.isIdle) {
                    this.attemptReconnect();
                }
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket 错误:', error);
                this.updateStatus('error', '连接错误');
            };
            
        } catch (error) {
            console.error('连接失败:', error);
            this.updateStatus('error', '连接失败');
            this.attemptReconnect();
        }
    }
    
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.updateStatus('connecting', `重连中 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
            
            setTimeout(() => {
                console.log(`尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                this.connect();
            }, this.reconnectDelay);
        } else {
            this.updateStatus('error', '连接失败，请刷新页面');
            this.addSystemMessage('连接失败，请检查服务器是否运行并刷新页面重试');
        }
    }
    
    // ==================== 心跳保活机制 ====================
    
    startHeartbeat() {
        // 清除旧的心跳
        this.stopHeartbeat();
        
        // 定期发送心跳
        this.heartbeatInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                console.log('💓 发送心跳包');
                this.sendMessage({
                    type: 'ping',
                    timestamp: Date.now()
                });
                
                // 设置心跳超时检测
                this.heartbeatTimeout = setTimeout(() => {
                    console.warn('⚠️ 心跳超时，连接可能已断开');
                    this.ws.close();
                }, this.HEARTBEAT_TIMEOUT);
            }
        }, this.HEARTBEAT_INTERVAL);
    }
    
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
        if (this.heartbeatTimeout) {
            clearTimeout(this.heartbeatTimeout);
            this.heartbeatTimeout = null;
        }
    }
    
    sendMessage(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            console.warn('⚠️ WebSocket 未连接，无法发送消息');
        }
    }
    
    // ==================== 空闲超时检测 ====================
    
    startIdleDetection() {
        // 清除旧的空闲检测
        this.stopIdleDetection();
        
        // 重置空闲状态
        this.isIdle = false;
        
        // 设置空闲超时
        this.resetIdleTimer();
        
        // 监听用户活动
        const activityEvents = ['mousedown', 'keydown', 'touchstart', 'scroll'];
        activityEvents.forEach(event => {
            document.addEventListener(event, this.onUserActivity.bind(this));
        });
    }
    
    stopIdleDetection() {
        if (this.idleTimeout) {
            clearTimeout(this.idleTimeout);
            this.idleTimeout = null;
        }
    }
    
    onUserActivity() {
        if (this.isIdle) {
            console.log('🎉 用户重新活跃，唤醒连接');
            this.wakeUp();
        }
        this.updateActivity();
        this.resetIdleTimer();
    }
    
    updateActivity() {
        this.lastActivityTime = Date.now();
    }
    
    resetIdleTimer() {
        this.stopIdleDetection();
        
        this.idleTimeout = setTimeout(() => {
            console.log('😴 检测到长时间无活动，进入空闲状态');
            this.enterIdleMode();
        }, this.IDLE_TIMEOUT);
    }
    
    enterIdleMode() {
        this.isIdle = true;
        this.updateStatus('idle', '空闲中（点击唤醒）');
        
        // 关闭连接以节省资源
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            console.log('📴 关闭空闲连接');
            this.ws.close();
        }
        
        // 显示唤醒提示
        this.showWakeUpPrompt();
    }
    
    wakeUp() {
        if (!this.isIdle) return;
        
        console.log('🔄 唤醒连接...');
        this.isIdle = false;
        this.hideWakeUpPrompt();
        this.reconnectAttempts = 0;  // 重置重连次数
        this.connect();
    }
    
    showWakeUpPrompt() {
        // 在聊天窗口显示唤醒提示
        const prompt = document.createElement('div');
        prompt.id = 'wakeUpPrompt';
        prompt.className = 'wake-up-prompt';
        prompt.innerHTML = `
            <div class="wake-up-content">
                <div class="wake-up-icon">😴</div>
                <div class="wake-up-text">AI小伙伴休息中...</div>
                <div class="wake-up-hint">点击任意位置唤醒</div>
            </div>
        `;
        
        this.messagesContainer.appendChild(prompt);
        
        // 点击唤醒
        prompt.addEventListener('click', () => {
            this.wakeUp();
        });
    }
    
    hideWakeUpPrompt() {
        const prompt = document.getElementById('wakeUpPrompt');
        if (prompt) {
            prompt.remove();
        }
    }
    
    handleMessage(data) {
        try {
            const message = JSON.parse(data);
            const { type, content, audio, timestamp } = message;
            
            // 收到任何消息都重置心跳超时（表示连接正常）
            if (this.heartbeatTimeout) {
                clearTimeout(this.heartbeatTimeout);
                this.heartbeatTimeout = null;
            }
            
            switch (type) {
                case 'connection_established':
                    // 连接建立成功
                    console.log('🎉 连接建立成功:', content || message);
                    break;
                    
                case 'pong':
                    // 心跳响应，连接正常
                    console.log('💓 收到心跳响应');
                    break;
                
                case 'avatar_updated':
                    // 头像更新成功
                    if (this.userInfo) {
                        this.userInfo.avatar = content.avatar;
                        localStorage.setItem('userInfo', JSON.stringify(this.userInfo));
                    }
                    this.displayUserInfo();
                    // 同步更新历史弹窗与消息列表里的用户头像
                    this.refreshAllUserAvatars();
                    this.showToast('头像更新成功！', 'success');
                    break;
                
                case 'profile_data':
                case 'profile_sync':
                    // 个人信息数据
                    console.log('收到个人信息:', content || message);
                    const profilePayload = (message.content && (message.content.profile || message.content)) || (message.data && (message.data.profile || message.data)) || content || {};
                    this.fillProfileForm(profilePayload);
                    
                    // 同步角色设置到前端 - 支持延迟同步
                    if (profilePayload.current_character) {
                        if (this.teenFeatures) {
                            console.log('🎭 准备同步角色设置:', profilePayload.current_character);
                            this.teenFeatures.currentCharacter = profilePayload.current_character;
                            this.teenFeatures.updateCharacterUI(profilePayload.current_character);
                            console.log('🎭 角色UI已更新到:', profilePayload.current_character);
                        } else {
                            // teenFeatures 还未初始化，保存角色信息等待后续同步
                            console.log('🎭 teenFeatures未就绪，缓存角色设置:', profilePayload.current_character);
                            this.pendingCharacterSync = profilePayload.current_character;
                            
                            // 延迟重试同步
                            setTimeout(() => {
                                if (this.teenFeatures && this.pendingCharacterSync) {
                                    console.log('🎭 延迟同步角色设置:', this.pendingCharacterSync);
                                    this.teenFeatures.currentCharacter = this.pendingCharacterSync;
                                    this.teenFeatures.updateCharacterUI(this.pendingCharacterSync);
                                    this.pendingCharacterSync = null;
                                }
                            }, 1000);
                        }
                    } else {
                        console.log('⚠️ 角色同步失败 - current_character为空');
                    }
                    break;
                
                case 'profile_updated':
                    // 个人信息更新成功
                    this.showToast('✨ 个人信息已保存！AI已经记住你啦~', 'success');
                    // 更新本地用户信息的昵称
                    if (content.profile && content.profile.nickname && this.userInfo) {
                        this.userInfo.nickname = content.profile.nickname;
                        localStorage.setItem('userInfo', JSON.stringify(this.userInfo));
                    }
                    // 关闭设置弹窗
                    setTimeout(() => {
                        closeModal('settingsModal');
                    }, 1000);
                    break;
                
                case 'voice_settings_updated':
                    // 语音设置更新成功
                    this.showToast(content.message || '语音设置已更新', 'success');
                    // 更新本地语音设置状态
                    if (typeof content.voice_enabled !== 'undefined') {
                        this.voiceEnabled = content.voice_enabled;
                        if (this.voiceModeToggle) {
                            this.voiceModeToggle.checked = content.voice_enabled;
                        }
                    }
                    break;
                
                case 'login_success':
                    // 登录成功（已在login.js处理，这里仅记录）
                    console.log('✅ 服务器确认登录成功');
                    break;
                
                case 'history_loaded':
                case 'history':
                    // 历史消息加载完成（对话框历史，按时间正序，旧消息在上）
                    console.log('📜 收到历史消息，完整数据:', message);
                    // 后端直接返回消息数组作为content
                    let historyMessages = [];
                    if (Array.isArray(message.content)) {
                        historyMessages = message.content;
                    } else if (Array.isArray(message.data)) {
                        historyMessages = message.data;
                    } else if (message.content?.messages) {
                        historyMessages = message.content.messages;
                    } else if (message.data?.messages) {
                        historyMessages = message.data.messages;
                    } else if (message.messages) {
                        historyMessages = message.messages;
                    }
                    console.log('📜 消息结构分析:', {
                        'message.content': message.content,
                        'message.data': message.data,
                        'Array.isArray(message.data)': Array.isArray(message.data),
                        '提取结果': historyMessages
                    });
                    console.log('📜 提取的历史消息:', historyMessages);
                    this.onHistoryLoaded(historyMessages);
                    break;
                    
                case 'greeting':
                    // 显示问候消息（新用户首次问候 或 老用户回归问候）
                    this.removeTypingIndicator();
                    this.addMessage('assistant', content, timestamp);
                    console.log('👋 收到问候消息:', content);
                    break;
                    
                case 'assistant_message':
                    // 如果启用语音回复，暂存文本等待对应的语音（不显示文本消息，只等语音）
                    if (this.voiceEnabled) {
                        // 提取文本内容 - 增强调试
                        console.log('🔍 assistant_message调试:', {
                            'message': message,
                            'content': content,
                            'message.text': message.text,
                            'message.payload': message.payload
                        });
                        
                        const msgText = (typeof content === 'string' && content) || message.text || (message.payload && message.payload.text) || '';
                        if (!msgText) {
                            console.warn('⚠️ assistant_message: content 参数为空，完整消息:', message);
                            break;
                        }
                        
                        this.pendingAssistantTexts.push(msgText);
                        console.log(`💬 收到文本(语音模式，不显示): ${msgText || 'undefined'}`);
                        
                        // 动态计算超时时间：根据文本长度调整
                        // 基础时间5秒 + 每10个字增加1秒，最大30秒
                        const textLength = msgText.length;
                        const baseTimeout = 5000;
                        const additionalTimeout = Math.floor(textLength / 10) * 2000;
                        const maxTimeout = 30000;
                        const timeout = Math.min(baseTimeout + additionalTimeout, maxTimeout);
                        
                        console.log(`⏱️ 设置语音等待超时: ${timeout}ms (文本长度: ${textLength}字)`);
                        
                        // 超时兜底：若超时未配对到语音，则直接展示文本
                        setTimeout(() => {
                            const idx = this.pendingAssistantTexts.indexOf(msgText);
                            if (idx !== -1) {
                                this.pendingAssistantTexts.splice(idx, 1);
                                if (this.isTyping) this.removeTypingIndicator();
                                console.warn(`⚠️ 语音超时(${timeout}ms)，显示文本消息`);
                                this.addMessage('assistant', msgText, timestamp);
                            }
                        }, timeout);
                    } else {
                        // 未启用语音回复，移除加载动画并直接显示文本
                        this.removeTypingIndicator();
                        const msgText = (typeof content === 'string' && content) || message.text || (message.payload && message.payload.text) || '';
                        if (!msgText) {
                            console.warn('⚠️ assistant_message: 无可显示文本');
                            break;
                        }
                        this.addMessage('assistant', msgText, timestamp);
                    }
                    break;
                    
                case 'asr_result':
                    // 显示语音识别结果
                    this.addMessage('user', `🎤 ${content}`, timestamp);
                    this.hideStatusBar();
                    // 显示"AI正在思考"动画
                    this.showTypingIndicator();
                    break;
                    
                case 'audio_chunk':
                    // 接收音频块并播放
                    this.playAudioChunk(audio);
                    break;
                
                case 'audio':
                    // 接收完整音频（WAV）
                    if (this.voiceEnabled) {
                        // 检查 content 参数是否有效 - 增强调试
                        console.log('🔍 audio消息调试:', {
                            'message': message,
                            'content': content,
                            'message.audio': message.audio,
                            'message.data': message.data
                        });
                        
                        if (!content && !message.audio && !message.data) {
                            console.warn('⚠️ audio消息: 所有音频字段都为空，完整消息:', message);
                            break;
                        }
                        
                        // 尝试从多个位置提取音频数据
                        const audioContent = content || message.audio || message.data;
                        
                        console.log(`📦 收到audio消息，当前待匹配文本队列: ${this.pendingAssistantTexts.length}条`);
                        console.log(`📦 audio数据大小: ${audioContent && audioContent.audio ? audioContent.audio.length : 'N/A'} 字符`);
                        console.log(`📦 audio携带的text: ${audioContent && audioContent.text || 'N/A'}`);
                        
                        // 取出第一条待显示的文本（FIFO队列）
                        let textContent = this.pendingAssistantTexts.shift();
                        if (!textContent) {
                            // 兼容：若没有待配对文本，尝试使用服务端随音频携带的文本
                            textContent = (audioContent && audioContent.text) || '';
                        }
                        if (textContent) {
                            console.log(`🎵 匹配成功，对应文本: ${textContent.substring(0, 50)}...`);
                            console.log(`🎵 队列剩余: ${this.pendingAssistantTexts.length}条`);
                            
                            // 只在第一条语音到达时移除加载动画
                            if (this.isTyping) {
                                this.removeTypingIndicator();
                            }
                            
                            // 创建微信式语音消息（audioContent是对象，包含text和audio）
                            const audioBase64 = (audioContent && audioContent.audio) || audioContent;  // 兼容不同格式
                            this.addVoiceMessage(audioBase64, textContent);
                        } else {
                            console.warn('⚠️ 收到语音但没有对应的文本，可能是重复的audio消息！');
                            console.warn(`⚠️ audio内容: ${JSON.stringify(content).substring(0, 200)}...`);
                        }
                    } else {
                        console.log('🔇 语音回复已关闭，跳过');
                    }
                    break;
                    
                case 'tts_complete':
                    // TTS 合成完成
                    console.log('语音合成完成');
                    this.hideStatusBar();
                    break;
                    
                case 'typing':
                    this.showTypingIndicator();
                    break;
                    
                case 'status':
                    this.showStatusBar(content);
                    break;
                    
                case 'system':
                    this.addSystemMessage(content);
                    break;
                
                case 'reset_ack':
                    // 使用状态栏短暂提示，不写入消息区
                    this.showStatusBar(content);
                    setTimeout(() => this.hideStatusBar(), 1500);
                    break;
                
                case 'pong':
                    // 收到心跳响应，清除超时
                    console.log('💚 收到心跳响应');
                    if (this.heartbeatTimeout) {
                        clearTimeout(this.heartbeatTimeout);
                        this.heartbeatTimeout = null;
                    }
                    break;
                    
                case 'error':
                    this.removeTypingIndicator();
                    // ASR/TTS 相关错误使用 Toast 提示，其他错误使用系统消息
                    if (content.includes('语音识别') || content.includes('语音合成') || content.includes('TTS') || content.includes('ASR')) {
                        this.showToast(content, 'error');
                    } else {
                        this.addSystemMessage(`错误: ${content}`);
                    }
                    this.hideStatusBar();
                    break;
                
                case 'history_grouped':
                    // 处理按日期分组的历史消息
                    console.log('收到按日期分组的历史消息:', content);
                    // 这里可以根据需要处理分组的历史消息
                    // 目前只是记录日志，避免未知消息类型警告
                    break;
                
                case 'character_switched':
                    // 角色切换事件（后端通知）
                    const roleName = (typeof content === 'string')
                        ? content
                        : (content?.character_name || content?.name || content?.character_id || '');
                    console.log('🎭 角色已切换为:', roleName, '完整数据:', content);
                    this.showToast(content?.message || `已切换角色：${roleName}`, 'success');
                    
                    // 确保前端UI也同步更新
                    if (content?.character_id && this.teenFeatures) {
                        this.teenFeatures.currentCharacter = content.character_id;
                        this.teenFeatures.updateCharacterUI(content.character_id);
                    }
                    break;
                
                case 'mood_history':
                case 'mood_statistics':
                case 'diary_generated':
                case 'diary_content':
                case 'diary_list':
                case 'bedtime_story':
                case 'characters_list':
                case 'proactive_chat_check':
                case 'profile_sync':
                case 'tree_hole_mode_updated':
                    // 这些消息类型由 teen-features.js 处理
                    console.log(`📋 收到 ${type} 消息，转发给 teen-features 模块处理`);
                    if (window.teenFeatures) {
                        window.teenFeatures.handleWebSocketMessage(message);
                    }
                    break;
                    
                default:
                    console.warn('未知消息类型:', type);
            }
        } catch (error) {
            console.error('解析消息失败:', error);
        }
    }
    
    sendTextMessage() {
        const content = this.messageInput.value.trim();
        
        if (!content || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }
        
        // 更新活动时间
        this.updateActivity();
        this.resetIdleTimer();
        
        // 显示用户消息
        this.addMessage('user', content);
        
        // 显示"AI正在输入"动画
        this.showTypingIndicator();
        
        // 发送到服务器
        const message = {
            type: 'text_message',
            content: content,
            enable_voice: this.voiceEnabled
        };
        
        this.sendMessage(message);
        
        // 清空输入框
        this.messageInput.value = '';
        this.autoResizeTextarea();
        this.messageInput.focus();
    }
    
    async startRecording() {
        if (this.isRecording || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }
        
        try {
            // 请求麦克风权限
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    channelCount: 1,
                    sampleRate: 16000
                } 
            });
            
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });
            
            this.audioChunks = [];
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };
            
            this.mediaRecorder.onstop = () => {
                // 停止录音后发送音频
                this.sendAudioMessage();
                
                // 停止媒体流
                stream.getTracks().forEach(track => track.stop());
            };
            
            this.mediaRecorder.start();
            this.isRecording = true;
            
            // 更新 UI
            this.recordBtn.classList.add('recording');
            this.audioVisualizer.classList.add('active');
            this.showStatusBar('正在录音... 松开发送');
            
            console.log('开始录音');
            
        } catch (error) {
            console.error('录音失败:', error);
            this.showToast('无法访问麦克风，请检查权限设置', 'error');
        }
    }
    
    stopRecording() {
        if (!this.isRecording || !this.mediaRecorder) {
            return;
        }
        
        this.mediaRecorder.stop();
        this.isRecording = false;
        
        // 更新 UI
        this.recordBtn.classList.remove('recording');
        this.audioVisualizer.classList.remove('active');
        
        console.log('停止录音');
    }
    
    async sendAudioMessage() {
        if (this.audioChunks.length === 0) {
            return;
        }
        
        try {
            // 合并音频块
            const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
            
            // 转换为 base64
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64Audio = reader.result.split(',')[1];
                
                // 发送到服务器
                const message = {
                    type: 'audio_message',
                    audio: base64Audio
                };
                
                this.sendMessage(message);
                
                console.log('发送音频消息，大小:', audioBlob.size);
                this.showStatusBar('正在识别语音...');
            };
            
            reader.readAsDataURL(audioBlob);
            
        } catch (error) {
            console.error('发送音频失败:', error);
            this.showToast('发送音频失败', 'error');
        }
    }
    
    async playAudioChunk(base64Audio) {
        try {
            // 解码 base64
            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            
            // 解码音频数据
            const audioBuffer = await this.audioContext.decodeAudioData(bytes.buffer);
            
            // 播放音频
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            source.start(0);
            
        } catch (error) {
            console.error('播放音频失败:', error);
        }
    }

    stopCurrentAudio() {
        // 停止 AudioContext 音频源
        if (this.currentAudioSource) {
            try {
                this.currentAudioSource.stop();
                console.log('🛑 已停止之前的音频播放（AudioContext）');
            } catch (e) {
                // 如果音频已经停止或还未开始，会抛出错误，忽略即可
            }
            this.currentAudioSource = null;
        }
        
        // 停止 HTML5 Audio
        if (this.currentHtmlAudio) {
            try {
                this.currentHtmlAudio.pause();
                this.currentHtmlAudio.currentTime = 0;
                console.log('🛑 已停止之前的音频播放（HTML5 Audio）');
            } catch (e) {
                // 忽略错误
            }
            this.currentHtmlAudio = null;
        }
    }
    
    stopAllAudio() {
        // 先停止通过 playAudioBase64 播放的音频
        this.stopCurrentAudio();
        
        // 停止所有语音消息的播放
        this.audioMessages.forEach((audioData, messageId) => {
            if (audioData.isPlaying && audioData.source) {
                try {
                    audioData.source.stop();
                } catch (e) {
                    // 忽略已停止的音频
                }
                audioData.isPlaying = false;
                audioData.source = null;
                
                // 更新UI
                const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
                if (messageDiv) {
                    const playBtn = messageDiv.querySelector('.voice-play-btn');
                    const waveform = messageDiv.querySelector('.voice-waveform');
                    if (playBtn) {
                        playBtn.innerHTML = `
                            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                                <path d="M8 5v14l11-7z"/>
                            </svg>
                        `;
                    }
                    if (waveform) {
                        waveform.classList.remove('playing');
                    }
                }
            }
        });
        
        // 清除当前播放标记
        this.currentPlayingVoice = null;
        
        console.log('🛑 已停止所有正在播放的音频');
    }
    
    async playAudioBase64(base64Audio) {
        try {
            console.log('🎵 开始播放音频，数据大小:', base64Audio.length);
            
            // 停止所有正在播放的音频
            this.stopAllAudio();
            
            // 确保音频上下文已启动
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
                console.log('🔊 音频上下文已恢复');
            }
            
            // 解码 base64 音频数据
            const binary = atob(base64Audio);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {
                bytes[i] = binary.charCodeAt(i);
            }
            
            console.log('📊 解码后音频大小:', bytes.length, '字节');
            
            // 解码音频数据
            const audioBuffer = await this.audioContext.decodeAudioData(bytes.buffer);
            console.log('🎼 音频解码成功，时长:', audioBuffer.duration.toFixed(2), '秒');
            
            // 创建音频源并播放
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            
            // 保存当前音频源
            this.currentAudioSource = source;
            
            // 播放完成回调
            source.onended = () => {
                console.log('✅ 音频播放完成');
                if (this.currentAudioSource === source) {
                    this.currentAudioSource = null;
                }
            };
            
            source.start(0);
            console.log('🎤 AI开始说话...');
            
        } catch (e) {
            console.error('❌ 播放完整音频失败:', e);
            console.error('错误详情:', e.message);
            
            // 尝试使用 HTML5 Audio 作为备选方案
            try {
                console.log('🔄 尝试备选播放方案...');
                const audioBlob = new Blob([Uint8Array.from(atob(base64Audio), c => c.charCodeAt(0))], {
                    type: 'audio/wav'
                });
                const audioUrl = URL.createObjectURL(audioBlob);
                const audio = new Audio(audioUrl);
                
                // 保存当前HTML5音频
                this.currentHtmlAudio = audio;
                
                audio.onended = () => {
                    URL.revokeObjectURL(audioUrl);
                    console.log('✅ 备选方案播放完成');
                    if (this.currentHtmlAudio === audio) {
                        this.currentHtmlAudio = null;
                    }
                };
                
                audio.onerror = (err) => {
                    console.error('❌ 备选方案也失败:', err);
                    if (this.currentHtmlAudio === audio) {
                        this.currentHtmlAudio = null;
                    }
                };
                
                await audio.play();
                console.log('🎤 AI开始说话（备选方案）...');
                
            } catch (fallbackError) {
                console.error('❌ 备选播放方案也失败:', fallbackError);
                this.showToast('音频播放失败，请检查浏览器音频权限', 'error');
            }
        }
    }
    
    
    addMessage(role, content, timestamp = null) {
        // 获取当前消息时间
        const currentTime = timestamp ? new Date(timestamp.replace(' ', 'T')) : new Date();
        
        // 检查是否需要显示时间分隔
        this.checkAndAddTimeDivider(currentTime);
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        if (role === 'assistant') {
            // 使用emoji作为头像
            avatar.textContent = '💙';
            avatar.style.fontSize = '24px';
        } else {
            // 显示用户自定义头像或默认头像
            if (this.userInfo && this.userInfo.avatar) {
                // 判断是否为图片（base64格式）
                if (this.userInfo.avatar.startsWith('data:image')) {
                    const img = document.createElement('img');
                    img.src = this.userInfo.avatar;
                    img.alt = '用户头像';
                    img.style.cssText = 'width: 100%; height: 100%; object-fit: cover; border-radius: 50%;';
                    img.onerror = () => { avatar.textContent = '👤'; };
                    avatar.appendChild(img);
                } else {
                    // emoji头像
                    avatar.textContent = this.userInfo.avatar;
                }
            } else {
                avatar.textContent = '👤';
            }
        }
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = content;
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
        
        // 更新最后消息时间
        this.lastMessageTime = currentTime;

        // 写入本地缓存（预渲染使用）
        if (!this.suppressCacheUpdate) {
            this.cacheMessage(role, content, currentTime.toISOString());
        }
    }
    
    /**
     * 添加微信式语音消息
     * @param {string} audioBase64 - Base64编码的音频数据
     * @param {string} textContent - 对应的文本内容
     */
    addVoiceMessage(audioBase64, textContent) {
        const messageId = `voice_${Date.now()}`;
        
        // 检查是否需要显示时间分隔
        const currentTime = new Date();
        this.checkAndAddTimeDivider(currentTime);
        
        // 存储音频数据和文本
        this.audioMessages.set(messageId, {
            audio: audioBase64,
            text: textContent,
            duration: 0,
            isPlaying: false,
            hasPlayed: false  // 标记是否已播放
        });
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.dataset.messageId = messageId;
        
        // 头像
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        // 使用emoji作为头像
        avatar.textContent = '💙';
        avatar.style.fontSize = '24px';
        
        // 语音消息内容
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content voice-message-content';

        // 语音气泡容器
        const voiceContainer = document.createElement('div');
        voiceContainer.className = 'voice-container';

        // 语音气泡（点击播放）
        const bubble = document.createElement('div');
        bubble.className = 'voice-bubble unplayed';
        bubble.title = '点击播放';

        // 波形图标
        const waveIcon = document.createElement('span');
        waveIcon.className = 'voice-wave-icon';
        waveIcon.textContent = '))';

        // 时长
        const duration = document.createElement('span');
        duration.className = 'voice-duration';
        duration.textContent = '--"';

        // 未读红点
        const unreadDot = document.createElement('span');
        unreadDot.className = 'voice-unread-dot';

        bubble.appendChild(waveIcon);
        bubble.appendChild(duration);
        bubble.appendChild(unreadDot);

        // 转文字按钮
        const convertBtn = document.createElement('button');
        convertBtn.className = 'voice-convert-btn';
        convertBtn.textContent = '转文字';
        convertBtn.title = '点击显示文本';

        voiceContainer.appendChild(bubble);
        voiceContainer.appendChild(convertBtn);
        contentDiv.appendChild(voiceContainer);
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
        
        // 计算音频时长
        this.calculateAudioDuration(messageId, audioBase64);
        
        // 绑定播放事件（点击气泡播放）
        bubble.addEventListener('click', () => this.toggleVoicePlay(messageId));
        
        // 绑定转文本事件
        convertBtn.addEventListener('click', () => this.toggleVoiceText(messageId));
        
        // 添加到未播放队列
        this.unplayedVoices.push(messageId);
        console.log(`✅ 语音消息已添加: ${messageId}，未播放队列: ${this.unplayedVoices.length}条`);
        
        // 如果当前没有正在播放的语音，自动播放第一条
        if (!this.currentPlayingVoice) {
            this.playNextUnplayedVoice();
            
            // 如果AudioContext被挂起，显示提示
            if (this.audioContext.state === 'suspended' && this.unplayedVoices.length === 1) {
                this.showToast('🔊 点击页面任意位置以播放语音', 'info', 3000);
            }
        }
        
        // 更新最后消息时间
        this.lastMessageTime = currentTime;
    }
    
    addSystemMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message system';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = content;
        
        messageDiv.appendChild(contentDiv);
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    showTypingIndicator() {
        if (this.isTyping) return;
        
        this.isTyping = true;
        this.typingElement = document.createElement('div');
        this.typingElement.className = 'message assistant typing-indicator';
        this.typingElement.innerHTML = `
            <div class="message-avatar" style="font-size: 24px;">
                💙
            </div>
            <div class="message-content">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;
        
        this.messagesContainer.appendChild(this.typingElement);
        this.scrollToBottom();
    }
    
    removeTypingIndicator() {
        if (this.isTyping && this.typingElement) {
            this.typingElement.remove();
            this.typingElement = null;
            this.isTyping = false;
        }
    }
    
    showStatusBar(text) {
        this.statusBar.textContent = text;
        this.statusBar.classList.add('active');
    }
    
    hideStatusBar() {
        this.statusBar.classList.remove('active');
    }
    
    updateStatus(status, text) {
        this.statusText.textContent = text;
        this.statusIndicator.className = 'status-indicator';
        
        if (status === 'connected') {
            this.statusIndicator.classList.add('connected');
        } else if (status === 'idle') {
            this.statusIndicator.classList.add('idle');
        }
    }
    
    enableInput() {
        this.messageInput.disabled = false;
        this.sendBtn.disabled = false;
        this.recordBtn.disabled = false;
        this.messageInput.placeholder = '输入消息或使用语音...';
    }
    
    disableInput() {
        this.messageInput.disabled = true;
        this.sendBtn.disabled = true;
        this.recordBtn.disabled = true;
        this.messageInput.placeholder = '未连接到服务器...';
    }
    
    autoResizeTextarea() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = this.messageInput.scrollHeight + 'px';
    }
    
    scrollToBottom() {
        setTimeout(() => {
            this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
        }, 100);
    }
    
    /**
     * 检查并添加时间分隔条（超过5分钟显示）
     * @param {Date} currentTime - 当前消息时间
     */
    checkAndAddTimeDivider(currentTime) {
        if (!this.lastMessageTime) {
            // 第一条消息，显示时间分隔条
            this.addTimeDivider(currentTime);
            return;
        }
        
        // 计算时间差（毫秒）
        const timeDiff = currentTime - this.lastMessageTime;
        const minutesDiff = timeDiff / (1000 * 60);
        
        // 超过5分钟显示时间分隔
        if (minutesDiff >= 5) {
            this.addTimeDivider(currentTime);
        }
    }
    
    /**
     * 添加时间分隔条
     * @param {Date} time - 时间对象
     */
    addTimeDivider(time) {
        const divider = document.createElement('div');
        divider.className = 'time-divider';
        divider.textContent = this.formatTimeDivider(time);
        this.messagesContainer.appendChild(divider);
    }
    
    /**
     * 格式化时间分隔条显示
     * @param {Date} time - 时间对象
     * @returns {string} - 格式化后的时间字符串
     */
    formatTimeDivider(time) {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        
        const messageDate = new Date(time.getFullYear(), time.getMonth(), time.getDate());
        
        const hours = time.getHours();
        const minutes = time.getMinutes().toString().padStart(2, '0');
        const timeStr = `${hours}:${minutes}`;
        
        // 判断日期
        if (messageDate.getTime() === today.getTime()) {
            // 今天
            return timeStr;
        } else if (messageDate.getTime() === yesterday.getTime()) {
            // 昨天
            return `昨天 ${timeStr}`;
        } else if (now - messageDate < 7 * 24 * 60 * 60 * 1000) {
            // 一周内，显示星期
            const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
            return `${weekdays[time.getDay()]} ${timeStr}`;
        } else if (time.getFullYear() === now.getFullYear()) {
            // 今年，显示月日
            const month = (time.getMonth() + 1).toString();
            const day = time.getDate().toString();
            return `${month}月${day}日 ${timeStr}`;
        } else {
            // 更早，显示完整日期
            const year = time.getFullYear();
            const month = (time.getMonth() + 1).toString();
            const day = time.getDate().toString();
            return `${year}年${month}月${day}日 ${timeStr}`;
        }
    }
    
    showToast(message, type = 'info', duration = 3000) {
        /**
         * 显示 Toast 提示
         * @param {string} message - 提示消息
         * @param {string} type - 类型: error, warning, success, info
         * @param {number} duration - 显示时长(ms)
         */
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        // 图标映射
        const icons = {
            error: '❌',
            warning: '⚠️',
            success: '✅',
            info: 'ℹ️'
        };
        
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-message">${message}</span>
        `;
        
        this.toastContainer.appendChild(toast);
        
        // 自动消失
        setTimeout(() => {
            toast.classList.add('fadeOut');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, duration);
    }
    
    /**
     * 计算音频时长
     */
    async calculateAudioDuration(messageId, audioBase64) {
        try {
            const audioData = this.audioMessages.get(messageId);
            if (!audioData) return;
            
            // 解码Base64
            const binaryString = atob(audioBase64);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            
            // 解码音频获取时长
            const audioBuffer = await this.audioContext.decodeAudioData(bytes.buffer);
            const duration = Math.ceil(audioBuffer.duration);
            
            // 更新存储的时长
            audioData.duration = duration;
            
            // 更新UI显示
            const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
            if (messageDiv) {
                const durationSpan = messageDiv.querySelector('.voice-duration');
                const bubble = messageDiv.querySelector('.voice-bubble');
                
                if (durationSpan) {
                    durationSpan.textContent = `${duration}"`;
                }
                
                // 设置气泡的data-duration属性，用于动态调整宽度
                if (bubble) {
                    bubble.setAttribute('data-duration', duration);
                }
            }
        } catch (error) {
            console.error('计算音频时长失败:', error);
            // 默认显示未知时长
            const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
            if (messageDiv) {
                const durationSpan = messageDiv.querySelector('.voice-duration');
                if (durationSpan) {
                    durationSpan.textContent = '???"';
                }
            }
        }
    }
    
    /**
     * 切换语音播放/暂停
     */
    async toggleVoicePlay(messageId, autoPlay = false) {
        const audioData = this.audioMessages.get(messageId);
        if (!audioData) return;
        
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageDiv) return;
        
        const bubble = messageDiv.querySelector('.voice-bubble');
        const waveIcon = messageDiv.querySelector('.voice-wave-icon');
        
        // 如果正在播放，停止
        if (audioData.isPlaying) {
            if (audioData.source) {
                audioData.source.stop();
                audioData.source = null;
            }
            audioData.isPlaying = false;
            if (bubble) bubble.classList.remove('playing');
            if (waveIcon) waveIcon.classList.remove('playing');
            // 如果是暂停，清除当前播放标记
            if (this.currentPlayingVoice === messageId) {
                this.currentPlayingVoice = null;
            }
            return;
        }
        
        // 如果是自动播放，检查是否有其他语音正在播放
        if (autoPlay && this.currentPlayingVoice && this.currentPlayingVoice !== messageId) {
            console.log(`⏸️ 已有语音正在播放 (${this.currentPlayingVoice})，等待播放完毕`);
            return;
        }
        
        // 开始播放
        try {
            console.log(`🎵 播放语音消息: ${messageId}`);
            
            // 如果是手动点击播放（非自动播放），停止其他正在播放的音频
            if (!autoPlay) {
                this.stopAllAudio();
            }
            
            // 确保音频上下文处于运行状态
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
                console.log('🔊 音频上下文已恢复');
            }
            
            // 解码Base64
            const binaryString = atob(audioData.audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            
            // 解码音频
            const audioBuffer = await this.audioContext.decodeAudioData(bytes.buffer);
            
            // 创建音频源
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            
            // 播放结束处理
            source.onended = () => {
                audioData.isPlaying = false;
                audioData.source = null;
                if (bubble) bubble.classList.remove('playing');
                if (waveIcon) waveIcon.classList.remove('playing');
                console.log('✅ 语音播放完成');
                
                // 标记为已播放，移除小红点
                this.markVoiceAsPlayed(messageId);
                
                // 播放下一条未播放的语音
                this.playNextUnplayedVoice();
            };
            
            // 更新状态
            audioData.isPlaying = true;
            audioData.source = source;
            
            // 标记为当前正在播放
            if (!autoPlay) {
                // 手动播放时设置当前播放
                this.currentPlayingVoice = messageId;
            }
            // 自动播放时已经在 playNextUnplayedVoice() 中设置了
            
            // 更新UI - 添加播放动画
            if (bubble) {
                bubble.classList.add('playing');
                bubble.classList.remove('unplayed');
            }
            if (waveIcon) {
                waveIcon.classList.add('playing');
            }
            
            // 开始播放
            source.start(0);
            console.log('🎤 AI开始说话...');
            
        } catch (error) {
            console.error('❌ 播放语音失败:', error);
            audioData.isPlaying = false;
            
            // 清除播放标记（如果是当前播放的）
            if (this.currentPlayingVoice === messageId) {
                this.currentPlayingVoice = null;
            }
            
            this.showToast('播放失败，请重试', 'error');
            
            // 尝试备选方案：HTML5 Audio
            try {
                console.log('🔄 尝试备选播放方案...');
                const audio = new Audio('data:audio/wav;base64,' + audioData.audio);
                
                // 更新状态
                audioData.isPlaying = true;
                if (!autoPlay) {
                    this.currentPlayingVoice = messageId;
                }
                
                // 更新UI
                playBtn.innerHTML = `
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                        <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
                    </svg>
                `;
                waveform.classList.add('playing');
                
                audio.onended = () => {
                    audioData.isPlaying = false;
                    playBtn.innerHTML = `
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                    `;
                    waveform.classList.remove('playing');
                    console.log('✅ 语音播放完成（备选方案）');
                    
                    // 标记为已播放，移除小红点
                    this.markVoiceAsPlayed(messageId);
                    
                    // 播放下一条未播放的语音
                    this.playNextUnplayedVoice();
                };
                
                audio.onerror = () => {
                    console.error('❌ 备选播放方案也失败');
                    audioData.isPlaying = false;
                    playBtn.innerHTML = `
                        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                    `;
                    waveform.classList.remove('playing');
                    
                    // 清除当前播放标记，尝试播放下一条
                    if (this.currentPlayingVoice === messageId) {
                        this.currentPlayingVoice = null;
                    }
                    this.playNextUnplayedVoice();
                };
                
                audio.play();
                console.log('🎤 AI开始说话（备选方案）...');
                
            } catch (fallbackError) {
                console.error('❌ 所有播放方案均失败:', fallbackError);
                // 清除当前播放标记，尝试播放下一条
                if (this.currentPlayingVoice === messageId) {
                    this.currentPlayingVoice = null;
                }
                this.playNextUnplayedVoice();
            }
        }
    }
    
    /**
     * 标记语音为已播放
     */
    markVoiceAsPlayed(messageId) {
        const audioData = this.audioMessages.get(messageId);
        if (!audioData) return;
        
        // 标记为已播放
        audioData.hasPlayed = true;
        
        // 从未播放队列中移除
        const index = this.unplayedVoices.indexOf(messageId);
        if (index > -1) {
            this.unplayedVoices.splice(index, 1);
            console.log(`🎯 语音已标记为已播放: ${messageId}，剩余未播放: ${this.unplayedVoices.length}条`);
        }
        
        // 移除UI上的未播放标记
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageDiv) {
            const bubble = messageDiv.querySelector('.voice-bubble');
            if (bubble) {
                bubble.classList.remove('unplayed');
                const dot = bubble.querySelector('.voice-unread-dot');
                if (dot) dot.remove();
            }
        }
        
        // 清除当前播放标记
        this.currentPlayingVoice = null;
    }
    
    /**
     * 播放下一条未播放的语音
     */
    async playNextUnplayedVoice() {
        // 如果没有未播放的语音，返回
        if (this.unplayedVoices.length === 0) {
            console.log('✅ 所有语音消息已播放完毕');
            this.currentPlayingVoice = null;
            return;
        }
        
        // 如果当前正在播放，不要开始新的
        if (this.currentPlayingVoice) {
            console.log(`⏸️ 当前正在播放: ${this.currentPlayingVoice}，等待播放完毕后再播放队列中的 ${this.unplayedVoices.length} 条语音`);
            return;
        }
        
        // 检查AudioContext状态，如果被挂起则不自动播放（等待用户手动点击）
        if (this.audioContext.state === 'suspended') {
            console.log('⏸️ AudioContext被挂起，等待用户交互后播放');
            console.log('💡 提示：点击页面任意位置或点击语音气泡即可播放');
            return;
        }
        
        // 取出第一条未播放的语音
        const nextVoiceId = this.unplayedVoices[0];
        console.log(`▶️ 自动播放下一条语音: ${nextVoiceId}，队列剩余: ${this.unplayedVoices.length} 条`);
        
        // 标记为当前播放
        this.currentPlayingVoice = nextVoiceId;
        
        // 短暂延迟后播放
        await new Promise(resolve => setTimeout(resolve, 300));
        
        // 开始播放（传入 autoPlay=true 表示自动播放）
        await this.toggleVoicePlay(nextVoiceId, true);
    }
    
    /**
     * 切换显示/隐藏文本内容
     */
    toggleVoiceText(messageId) {
        const audioData = this.audioMessages.get(messageId);
        if (!audioData || !audioData.text) return;
        
        const messageDiv = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageDiv) return;
        
        const contentDiv = messageDiv.querySelector('.message-content');
        let textDiv = messageDiv.querySelector('.voice-text-content');
        const convertBtn = messageDiv.querySelector('.voice-convert-btn');
        
        if (textDiv) {
            // 已显示文本，隐藏它
            textDiv.remove();
            convertBtn.textContent = '转文字';
            convertBtn.classList.remove('active');
        } else {
            // 显示文本
            textDiv = document.createElement('div');
            textDiv.className = 'voice-text-content';
            textDiv.textContent = audioData.text;
            contentDiv.appendChild(textDiv);
            convertBtn.textContent = '隐藏';
            convertBtn.classList.add('active');
            
            // 滚动到底部
            this.scrollToBottom();
        }
    }
    
    // ==================== 用户管理方法 ====================
    
    /**
     * 显示用户信息
     */
    displayUserInfo() {
        const header = document.querySelector('.header-content');
        if (!header) return;
        
        // 移除旧的用户信息（如果存在）
        const oldUserInfo = document.getElementById('userInfoDisplay');
        if (oldUserInfo) {
            oldUserInfo.remove();
        }
        
        // 创建用户信息显示区域
        const userInfoDiv = document.createElement('div');
        userInfoDiv.id = 'userInfoDisplay';
        userInfoDiv.style.cssText = `
            margin-left: auto;
            display: flex;
            align-items: center;
            gap: 12px;
            color: white;
            font-size: 14px;
        `;
        
        if (this.userMode === 'user' && this.userInfo) {
            const userAvatar = this.userInfo.avatar || '👤';
            const isImageAvatar = userAvatar.startsWith('data:image');
            
            if (isImageAvatar) {
                userInfoDiv.innerHTML = `
                    <div id="userAvatarDisplay" style="
                        width: 32px;
                        height: 32px;
                        border-radius: 50%;
                        overflow: hidden;
                        cursor: pointer;
                        margin-right: 8px;
                        border: 2px solid rgba(255, 255, 255, 0.5);
                    " title="点击更换头像">
                        <img src="${userAvatar}" style="width: 100%; height: 100%; object-fit: cover;">
                    </div>
                    <span>${this.userInfo.nickname || this.userInfo.username}</span>
                    <button id="logoutBtn" style="
                        background: rgba(255, 255, 255, 0.2);
                        color: white;
                        border: 1px solid rgba(255, 255, 255, 0.3);
                        padding: 6px 12px;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 13px;
                        transition: all 0.2s;
                    " onmouseover="this.style.background='rgba(255,255,255,0.3)'" 
                       onmouseout="this.style.background='rgba(255,255,255,0.2)'">
                        退出登录
                    </button>
                `;
            } else {
                userInfoDiv.innerHTML = `
                    <span id="userAvatarDisplay" style="cursor: pointer; font-size: 20px; margin-right: 4px;" title="点击更换头像">${userAvatar}</span>
                    <span>${this.userInfo.nickname || this.userInfo.username}</span>
                    <button id="logoutBtn" style="
                        background: rgba(255, 255, 255, 0.2);
                        color: white;
                        border: 1px solid rgba(255, 255, 255, 0.3);
                        padding: 6px 12px;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 13px;
                        transition: all 0.2s;
                    " onmouseover="this.style.background='rgba(255,255,255,0.3)'" 
                       onmouseout="this.style.background='rgba(255,255,255,0.2)'">
                        退出登录
                    </button>
                `;
            }
            
            // 不再显示在顶部，改为在设置面板中显示
            // header.appendChild(userInfoDiv);
        } else {
            // 游客模式也不再显示在顶部
            // userInfoDiv.innerHTML = `...`;
            // header.appendChild(userInfoDiv);
        }
    }
    
    /**
     * 向服务器发送登录信息（重新认证WebSocket会话）
     */
    loginToServer() {
        if (!this.userInfo) return;
        
        console.log('🔐 向服务器发送登录信息（会话认证）...');
        
        // 发送用户ID给服务器，让服务器初始化该用户的会话
        // 注意：这里使用特殊的消息类型，告诉服务器这是会话认证
        this.sendMessage({
            type: 'session_auth',
            user_id: this.userInfo.user_id,
            username: this.userInfo.username
        });
        
        // 获取用户档案信息，包括当前角色设置
        setTimeout(() => {
            this.loadProfileInfo();
        }, 1000);
    }
    
    /**
     * 加载历史消息
     */
    loadHistory(limit = 50, force = false) {
        // 游客模式不加载历史
        if (this.userMode === 'guest') {
            console.log('🎭 游客模式：不加载历史消息');
            return;
        }
        
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('⚠️ WebSocket 未连接，无法加载历史');
            return;
        }
        
        if (this.historyLoaded && !force) {
            console.log('📜 历史消息已加载，跳过');
            return;
        }
        
        console.log('📜 请求加载历史消息...');
        
        this.sendMessage({
            type: 'load_history',
            limit: limit
        });
    }
    
    /**
     * 处理加载的历史消息
     */
    onHistoryLoaded(messages) {
        console.log('📜 onHistoryLoaded 被调用，收到消息:', messages);
        console.log('📜 preRenderedFromCache 状态:', this.preRenderedFromCache);
        this.historyLoaded = true;
        
        const displayMessages = (messages || []).filter(msg => msg.role === 'user' || msg.role === 'assistant');
        console.log('📜 过滤后的显示消息数量:', displayMessages.length);
        
        // 如果已做本地预渲染，则不打断当前界面，只同步缓存
        if (this.preRenderedFromCache) {
            console.log('📜 检测到预渲染状态，调用 replaceCacheWithServer');
            this.replaceCacheWithServer(displayMessages);
            return;
        }
        
        // 批量渲染历史消息（无动画，静默加载）
        console.log('📜 直接调用 batchRenderHistory');
        this.batchRenderHistory(displayMessages);
    }
    
    /**
     * 批量渲染历史消息（预加载，无动画）
     */
    batchRenderHistory(messages) {
        this.messagesContainer.innerHTML = '';
        this.suppressCacheUpdate = true;
        
        // 初始化lastMessageTime为第一条消息的时间（如果有的话）
        if (messages.length > 0 && messages[0].timestamp) {
            // 设置为第一条消息之前很久的时间，让第一条消息不显示时间戳
            const firstTime = new Date(messages[0].timestamp);
            this.lastMessageTime = new Date(firstTime.getTime() - 1000); // 1秒前，不足5分钟
        } else {
            this.lastMessageTime = null;
        }
        
        // 批量生成所有消息的HTML
        messages.forEach((msg) => {
            const isUserVoice = msg.metadata && msg.metadata.is_voice_input;
            const isAssistantVoice = msg.metadata && msg.metadata.is_voice_response && msg.metadata.audio_base64;
            
            if (isUserVoice || isAssistantVoice) {
                // 渲染为语音消息
                const audioBase64 = isAssistantVoice ? msg.metadata.audio_base64 : (msg.metadata.audio_base64 || '');
                this.renderVoiceMessageToDOM(msg.role, audioBase64, msg.content, msg.timestamp);
            } else {
                // 渲染为普通文本消息
                this.addMessage(msg.role, msg.content, msg.timestamp);
            }
        });
        
        this.suppressCacheUpdate = false;
        this.scrollToBottom();
    }
    
    /**
     * 将语音消息直接渲染到DOM（用于批量加载历史）
     */
    renderVoiceMessageToDOM(role, audioBase64, textContent, timestamp) {
        const messageId = `voice_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        
        // 检查是否需要显示时间分隔
        if (timestamp) {
            const msgTime = new Date(timestamp);
            this.checkAndAddTimeDivider(msgTime);
            this.lastMessageTime = msgTime;  // 更新最后消息时间
        }
        
        // 存储音频数据和文本
        if (audioBase64) {
            this.audioMessages.set(messageId, {
                audio: audioBase64,
                text: textContent,
                duration: 0,
                isPlaying: false,
                hasPlayed: true  // 历史消息标记为已播放，不显示小红点
            });
        }
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        messageDiv.dataset.messageId = messageId;
        
        // 头像
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        if (role === 'assistant') {
            // 使用emoji作为头像
            avatar.textContent = '💙';
            avatar.style.fontSize = '24px';
        } else {
            const userAvatar = (this.userInfo && this.userInfo.avatar) || '👤';
            const isImageAvatar = userAvatar.startsWith('data:image');
            if (isImageAvatar) {
                const imgEl = document.createElement('img');
                imgEl.src = userAvatar;
                imgEl.alt = '用户头像';
                imgEl.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:50%;';
                avatar.appendChild(imgEl);
            } else {
                avatar.textContent = userAvatar;
            }
        }
        
        // 语音消息内容 - 使用新的UI结构
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content voice-message-content';

        // 语音气泡容器
        const voiceContainer = document.createElement('div');
        voiceContainer.className = 'voice-container';

        // 语音气泡（点击播放）- 历史消息不显示小红点
        const bubble = document.createElement('div');
        bubble.className = 'voice-bubble';
        bubble.title = '点击播放';

        // 波形图标
        const waveIcon = document.createElement('span');
        waveIcon.className = 'voice-wave-icon';
        waveIcon.textContent = '))';

        // 时长
        const duration = document.createElement('span');
        duration.className = 'voice-duration';
        duration.textContent = '--"';

        bubble.appendChild(waveIcon);
        bubble.appendChild(duration);
        // 历史消息不添加未读红点

        // 转文字按钮
        const convertBtn = document.createElement('button');
        convertBtn.className = 'voice-convert-btn';
        convertBtn.textContent = '转文字';
        convertBtn.title = '点击显示文本';

        voiceContainer.appendChild(bubble);
        voiceContainer.appendChild(convertBtn);
        contentDiv.appendChild(voiceContainer);
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
        
        this.messagesContainer.appendChild(messageDiv);
        
        // 计算音频时长
        if (audioBase64) {
            this.calculateAudioDuration(messageId, audioBase64);
        }
        
        // 绑定播放事件（点击气泡播放）
        bubble.addEventListener('click', () => this.toggleVoicePlay(messageId));
        
        // 绑定转文本事件
        convertBtn.addEventListener('click', () => this.toggleVoiceText(messageId));
    }
    
    /**
     * 退出登录
     */
    logout() {
        if (confirm('确定要退出登录吗？')) {
            // 清除本地存储
            localStorage.removeItem('userMode');
            localStorage.removeItem('userInfo');
            
            // 断开WebSocket连接
            if (this.ws) {
                this.ws.close();
            }
            
            // 跳转到登录页面
            window.location.href = 'login.html';
        }
    }
    
    /**
     * 显示头像选择器
     */
    showAvatarSelector() {
        // 预设头像列表
        const avatars = [
            '👤', '😊', '😎', '🥰', '😇', '🤗', '🥳', '😺', 
            '🐱', '🐶', '🐼', '🐰', '🦊', '🐻', '🐯', '🦁',
            '🌸', '🌺', '🌻', '🌹', '🍀', '⭐', '✨', '🌙',
            '❤️', '💙', '💚', '💜', '🧡', '💛', '💖', '💗'
        ];
        
        // 创建弹窗
        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        `;
        
        const content = document.createElement('div');
        content.style.cssText = `
            background: white;
            border-radius: 16px;
            padding: 24px;
            max-width: 400px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        `;
        
        content.innerHTML = `
            <h3 style="margin: 0 0 16px 0; color: var(--primary-color);">选择头像</h3>
            <div style="margin-bottom: 16px;">
                <label for="avatarUpload" style="
                    display: block;
                    width: 100%;
                    padding: 12px;
                    background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-dark) 100%);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 14px;
                    text-align: center;
                    transition: all 0.3s;
                ">
                    📸 上传自定义图片
                </label>
                <input type="file" id="avatarUpload" accept="image/*" style="display: none;">
                <div id="uploadPreview" style="
                    margin-top: 12px;
                    display: none;
                    align-items: center;
                    gap: 12px;
                ">
                    <img id="previewImage" style="
                        width: 60px;
                        height: 60px;
                        border-radius: 50%;
                        object-fit: cover;
                        border: 2px solid var(--primary-color);
                    ">
                    <button id="confirmUpload" style="
                        padding: 8px 16px;
                        background: #4CAF50;
                        color: white;
                        border: none;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 13px;
                    ">确认使用</button>
                    <button id="cancelUpload" style="
                        padding: 8px 16px;
                        background: #f44336;
                        color: white;
                        border: none;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 13px;
                    ">取消</button>
                </div>
            </div>
            <div style="
                text-align: center;
                color: var(--text-secondary);
                font-size: 12px;
                margin-bottom: 12px;
            ">或选择预设头像</div>
            <div id="avatarGrid" style="
                display: grid;
                grid-template-columns: repeat(8, 1fr);
                gap: 8px;
                margin-bottom: 16px;
            "></div>
            <button id="closeAvatarSelector" style="
                width: 100%;
                padding: 12px;
                background: #e0e0e0;
                color: #666;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
            ">取消</button>
        `;
        
        modal.appendChild(content);
        document.body.appendChild(modal);
        
        // 添加头像选项
        const grid = content.querySelector('#avatarGrid');
        avatars.forEach(avatar => {
            const btn = document.createElement('button');
            btn.textContent = avatar;
            btn.style.cssText = `
                font-size: 24px;
                padding: 8px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                background: white;
                cursor: pointer;
                transition: all 0.2s;
            `;
            
            btn.onmouseover = () => {
                btn.style.borderColor = 'var(--primary-color)';
                btn.style.transform = 'scale(1.1)';
            };
            
            btn.onmouseout = () => {
                btn.style.borderColor = '#e0e0e0';
                btn.style.transform = 'scale(1)';
            };
            
            btn.onclick = () => {
                this.updateAvatar(avatar);
                modal.remove();
            };
            
            grid.appendChild(btn);
        });
        
        // 图片上传处理
        const uploadInput = content.querySelector('#avatarUpload');
        const uploadPreview = content.querySelector('#uploadPreview');
        const previewImage = content.querySelector('#previewImage');
        let uploadedImageData = null;
        
        uploadInput.onchange = (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            // 验证文件类型
            if (!file.type.startsWith('image/')) {
                this.showToast('请选择图片文件', 'error');
                return;
            }
            
            // 验证文件大小（限制2MB）
            if (file.size > 2 * 1024 * 1024) {
                this.showToast('图片大小不能超过2MB', 'error');
                return;
            }
            
            // 读取并预览图片
            const reader = new FileReader();
            reader.onload = (event) => {
                const img = new Image();
                img.onload = () => {
                    // 压缩图片到合适大小
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    
                    // 设置最大尺寸
                    const maxSize = 200;
                    let width = img.width;
                    let height = img.height;
                    
                    if (width > height) {
                        if (width > maxSize) {
                            height *= maxSize / width;
                            width = maxSize;
                        }
                    } else {
                        if (height > maxSize) {
                            width *= maxSize / height;
                            height = maxSize;
                        }
                    }
                    
                    canvas.width = width;
                    canvas.height = height;
                    ctx.drawImage(img, 0, 0, width, height);
                    
                    // 转换为base64
                    uploadedImageData = canvas.toDataURL('image/jpeg', 0.8);
                    
                    // 显示预览
                    previewImage.src = uploadedImageData;
                    uploadPreview.style.display = 'flex';
                };
                img.src = event.target.result;
            };
            reader.readAsDataURL(file);
        };
        
        // 确认上传
        content.querySelector('#confirmUpload').onclick = () => {
            if (uploadedImageData) {
                this.updateAvatar(uploadedImageData);
                modal.remove();
            }
        };
        
        // 取消上传
        content.querySelector('#cancelUpload').onclick = () => {
            uploadPreview.style.display = 'none';
            uploadInput.value = '';
            uploadedImageData = null;
        };
        
        // 关闭按钮
        content.querySelector('#closeAvatarSelector').onclick = () => {
            modal.remove();
        };
        
        // 点击背景关闭
        modal.onclick = (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        };
    }
    
    /**
     * 更新头像
     */
    updateAvatar(avatar) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            this.showToast('连接已断开，请刷新页面', 'error');
            return;
        }
        
        this.sendMessage({
            type: 'update_avatar',
            avatar: avatar
        });
    }
    
    /**
     * 加载个人信息到设置面板
     */
    loadProfileInfo() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('WebSocket未连接，无法加载个人信息');
            return;
        }
        
        this.sendMessage({
            type: 'get_profile'
        });
    }
    
    /**
     * 更新语音设置
     */
    updateVoiceSettings(voiceEnabled) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }
        
        this.sendMessage({
            type: 'update_voice_settings',
            voice_enabled: voiceEnabled
        });
    }
    
    /**
     * 保存个人信息
     */
    saveProfileInfo() {
        const profileData = {
            nickname: document.getElementById('profileNickname').value.trim(),
            birthday: document.getElementById('profileBirthday').value,
            hobby: document.getElementById('profileHobby').value.trim(),
            occupation: document.getElementById('profileOccupation').value.trim(),
            city: document.getElementById('profileCity').value.trim(),
            bio: document.getElementById('profileBio').value.trim()
        };
        
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            this.showToast('连接已断开，请刷新页面', 'error');
            return;
        }
        
        this.sendMessage({
            type: 'update_profile',
            profile: profileData
        });
    }
    
    /**
     * 填充个人信息到表单
     */
    fillProfileForm(profile) {
        if (!profile) return;
        
        if (profile.nickname) document.getElementById('profileNickname').value = profile.nickname;
        if (profile.birthday) document.getElementById('profileBirthday').value = profile.birthday;
        if (profile.hobby) document.getElementById('profileHobby').value = profile.hobby;
        if (profile.occupation) document.getElementById('profileOccupation').value = profile.occupation;
        if (profile.city) document.getElementById('profileCity').value = profile.city;
        if (profile.bio) document.getElementById('profileBio').value = profile.bio;
        
        // 同步语音设置
        if (typeof profile.voice_enabled !== 'undefined') {
            this.voiceEnabled = profile.voice_enabled;
            if (this.voiceModeToggle) {
                this.voiceModeToggle.checked = profile.voice_enabled;
            }
        }
    }
    
    /**
     * 初始化历史记录侧边栏
     */
    initHistorySidebar() {
        const historyBtn = document.getElementById('historyBtn');
        const sidebar = document.getElementById('historySidebar');
        const searchInput = document.getElementById('historySearch');
        
        if (!historyBtn || !sidebar) {
            console.warn('⚠️ 聊天记录按钮或侧边栏未找到');
            return;
        }
        
        // 打开侧边栏
        historyBtn.addEventListener('click', () => {
            sidebar.classList.add('show');
            this.loadHistorySidebar();
        });
        
        // 搜索功能
        if (searchInput) {
            let searchTimeout;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    this.searchHistorySidebar(e.target.value);
                }, 500);
            });
        }
    }
    
    /**
     * 加载历史记录到侧边栏
     */
    loadHistorySidebar() {
        // 游客模式不显示历史记录
        if (this.userMode === 'guest') {
            const contentDiv = document.getElementById('historyContent');
            if (contentDiv) {
                contentDiv.innerHTML = '<div class="history-empty">游客模式下不保存历史记录</div>';
            }
            return;
        }
        
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            this.showToast('连接已断开，请刷新页面', 'error');
            return;
        }
        
        const contentDiv = document.getElementById('historyContent');
        if (!contentDiv) return;
        
        contentDiv.innerHTML = '<div class="loading">正在加载...</div>';
        
        // 请求按日期分组的历史记录
        this.sendMessage({
            type: 'get_grouped_history'
        });
    }

    /**
     * 打开日期选择器
     */
    openDatePopover(anchor, popover) {
        if (!anchor || !popover) return;
        const rect = anchor.getBoundingClientRect();
        const offsetTop = window.scrollY || document.documentElement.scrollTop;
        popover.style.display = 'block';
        popover.style.left = (rect.left) + 'px';
        popover.style.top = (rect.bottom + offsetTop + 6) + 'px';
        // 初始化月份为当前
        const now = new Date();
        this.dpYear = now.getFullYear();
        this.dpMonth = now.getMonth() + 1;
        this.renderDatePicker();
    }

    closeDatePopover() {
        const popover = document.getElementById('historyDatePopover');
        if (popover) popover.style.display = 'none';
    }

    renderDatePicker() {
        const yEl = document.getElementById('dpYear');
        const mEl = document.getElementById('dpMonth');
        const grid = document.getElementById('dpGrid');
        if (!yEl || !mEl || !grid) return;
        yEl.textContent = this.dpYear;
        mEl.textContent = this.dpMonth < 10 ? `0${this.dpMonth}` : `${this.dpMonth}`;

        // 头部导航
        const prevY = document.getElementById('dpPrevYear');
        const nextY = document.getElementById('dpNextYear');
        const prevM = document.getElementById('dpPrevMonth');
        const nextM = document.getElementById('dpNextMonth');
        prevY.onclick = () => { this.dpYear -= 1; this.renderDatePicker(); };
        nextY.onclick = () => { this.dpYear += 1; this.renderDatePicker(); };
        prevM.onclick = () => { this.dpMonth = this.dpMonth === 1 ? (this.dpYear -= 1, 12) : this.dpMonth - 1; this.renderDatePicker(); };
        nextM.onclick = () => { this.dpMonth = this.dpMonth === 12 ? (this.dpYear += 1, 1) : this.dpMonth + 1; this.renderDatePicker(); };

        // 计算当月
        const firstDay = new Date(this.dpYear, this.dpMonth - 1, 1);
        const startWeek = firstDay.getDay();
        const daysInMonth = new Date(this.dpYear, this.dpMonth, 0).getDate();
        grid.innerHTML = '';
        const todayStr = this.formatDateString(new Date());
        for (let i = 0; i < startWeek; i++) {
            const empty = document.createElement('div');
            grid.appendChild(empty);
        }
        for (let d = 1; d <= daysInMonth; d++) {
            const cell = document.createElement('div');
            cell.className = 'date-cell';
            const dateStr = `${this.dpYear}-${this.dpMonth.toString().padStart(2,'0')}-${d.toString().padStart(2,'0')}`;
            if (dateStr === todayStr) cell.classList.add('today');
            cell.textContent = d;
            cell.onclick = () => {
                this.selectHistoryDate(dateStr);
            };
            grid.appendChild(cell);
        }
    }

    formatDateString(d) {
        const yyyy = d.getFullYear();
        const mm = (d.getMonth() + 1).toString().padStart(2,'0');
        const dd = d.getDate().toString().padStart(2,'0');
        return `${yyyy}-${mm}-${dd}`;
    }

    selectHistoryDate(dateStr) {
        this.closeDatePopover();
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        const contentDiv = document.getElementById('historyContentSidebar');
        if (contentDiv) contentDiv.innerHTML = '<div class="history-loading">正在加载...</div>';
        this.sendMessage({
            type: 'get_history_by_date',
            start_date: dateStr,
            end_date: dateStr
        });
    }
    
    /**
     * 渲染历史记录到侧边栏
     */
    renderHistorySidebar(groupedHistory) {
        const contentDiv = document.getElementById('historyContentSidebar');
        if (!contentDiv) return;
        
        if (!groupedHistory || Object.keys(groupedHistory).length === 0) {
            contentDiv.innerHTML = '<div class="history-empty">暂无聊天记录</div>';
            return;
        }
        
        let html = '';
        
        for (const [date, messages] of Object.entries(groupedHistory)) {
            html += `<div class="history-date-group">`;
            html += `<div class="history-date-header">${this.formatHistoryDate(date)}</div>`;
            
            for (const msg of messages) {
                if (msg.role === 'system') continue;
                if (!this.shouldKeepMessageByFilter(msg)) continue;
                
                const sender = msg.role === 'user' ? '我' : 'AI小伙伴';
                const avatarClass = msg.role === 'user' ? 'user' : 'assistant';
                const time = this.formatHistoryTime(msg.timestamp);
                
                // 检查是否是语音消息
                const isVoiceInput = msg.metadata && msg.metadata.is_voice_input;
                const isVoiceResponse = msg.metadata && msg.metadata.is_voice_response;
                const hasAudio = msg.metadata && msg.metadata.audio_base64;
                const isVoice = isVoiceInput || isVoiceResponse;
                
                let contentHTML = '';
                if (isVoice) {
                    // 语音消息显示为迷你语音气泡
                    const messageId = `sidebar_voice_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                    if (hasAudio) {
                        // 存储音频数据供播放
                        this.audioMessages.set(messageId, {
                            audio: msg.metadata.audio_base64,
                            text: msg.content,
                            duration: 0,
                            isPlaying: false,
                            hasPlayed: true
                        });
                    }
                    
                    contentHTML = `
                        <div class="history-message-header">
                            <span class="history-message-sender">${sender}</span>
                            <span class="history-message-time">${time}</span>
                        </div>
                        <div class="history-voice-bubble" data-message-id="${messageId}" ${hasAudio ? 'onclick="chat.toggleVoicePlay(\'' + messageId + '\')"' : ''} style="cursor: ${hasAudio ? 'pointer' : 'default'};">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" style="margin-right:4px;">
                                <path d="M8 5v14l11-7z"/>
                            </svg>
                            <span style="font-size:12px;">3"</span>
                        </div>
                    `;
                } else {
                    // 文本消息
                    const preview = msg.content.substring(0, 80) + (msg.content.length > 80 ? '...' : '');
                    contentHTML = `
                        <div class="history-message-header">
                            <span class="history-message-sender">${sender}</span>
                            <span class="history-message-time">${time}</span>
                        </div>
                        <div class="history-message-text">${this.escapeHtml(preview)}</div>
                    `;
                }
                
                html += `
                    <div class="history-message-item" data-timestamp="${msg.timestamp}">
                        <div class="history-message-avatar ${avatarClass}">` +
                            (avatarClass === 'assistant'
                                ? `<span style="font-size:24px;">💙</span>`
                                : this.buildUserAvatarHTML()) +
                        `</div>
                        <div class="history-message-content">
                            ${contentHTML}
                        </div>
                    </div>
                `;
            }
            
            html += `</div>`;
        }
        
        contentDiv.innerHTML = html;
    }
    
    /**
     * 搜索历史记录
     */
    searchHistorySidebar(query) {
        if (!query.trim()) {
            this.loadHistorySidebar();
            return;
        }
        
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }
        
        const contentDiv = document.getElementById('historyContentSidebar');
        if (!contentDiv) return;
        
        contentDiv.innerHTML = '<div class="history-loading">正在搜索...</div>';
        
        this.sendMessage({
            type: 'search_messages',
            query: query,
            limit: 50
        });
    }
    
    /**
     * 渲染搜索结果到侧边栏
     */
    renderSearchResults(results, query) {
        const contentDiv = document.getElementById('historyContentSidebar');
        if (!contentDiv) return;
        
        if (!results || results.length === 0) {
            contentDiv.innerHTML = `<div class="history-empty">没有找到包含 "${this.escapeHtml(query)}" 的消息</div>`;
            return;
        }
        
        let html = `<div style="padding: 12px 16px; color: #999; font-size: 13px; background: #3a3a3a; border-bottom: 1px solid #444;">找到 ${results.length} 条结果</div>`;
        
        for (const result of results) {
            const msg = result.matched_message;
            const sender = msg.role === 'user' ? '我' : '巴卫';
            const avatarClass = msg.role === 'user' ? 'user' : 'assistant';
            const time = this.formatHistoryTime(msg.timestamp);
            
            // 检查是否是语音消息
            const isVoiceInput = msg.metadata && msg.metadata.is_voice_input;
            const isVoiceResponse = msg.metadata && msg.metadata.is_voice_response;
            const hasAudio = msg.metadata && msg.metadata.audio_base64;
            const isVoice = isVoiceInput || isVoiceResponse;
            
            let contentHTML = '';
            if (isVoice) {
                // 语音消息显示为迷你语音气泡
                const messageId = `sidebar_voice_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                if (hasAudio) {
                    this.audioMessages.set(messageId, {
                        audio: msg.metadata.audio_base64,
                        text: msg.content,
                        duration: 0,
                        isPlaying: false,
                        hasPlayed: true
                    });
                }
                
                contentHTML = `
                    <div class="history-message-header">
                        <span class="history-message-sender">${sender}</span>
                        <span class="history-message-time">${time}</span>
                    </div>
                    <div class="history-voice-bubble" data-message-id="${messageId}" ${hasAudio ? 'onclick="chat.toggleVoicePlayback(\'' + messageId + '\')"' : ''} style="cursor: ${hasAudio ? 'pointer' : 'default'};">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" style="margin-right:4px;">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                        <span style="font-size:12px;">3"</span>
                    </div>
                `;
            } else {
                // 高亮搜索关键词
                const highlightedContent = this.highlightSearchTerm(msg.content, query);
                contentHTML = `
                    <div class="history-message-header">
                        <span class="history-message-sender">${sender}</span>
                        <span class="history-message-time">${time}</span>
                    </div>
                    <div class="history-message-text" style="white-space: normal; -webkit-line-clamp: unset;">${highlightedContent}</div>
                `;
            }
            
            html += `
                <div class="history-message-item" data-timestamp="${msg.timestamp}">
                    <div class="history-message-avatar ${avatarClass}">` +
                        (avatarClass === 'assistant'
                            ? `<span style="font-size:24px;">💙</span>`
                            : this.buildUserAvatarHTML()) +
                    `</div>
                    <div class="history-message-content">
                        ${contentHTML}
                    </div>
                </div>
            `;
        }
        
        contentDiv.innerHTML = html;
    }

    /**
     * 过滤规则（基于消息文本的简单判定）
     */
    shouldKeepMessageByFilter(msg) {
        // 仅支持 all/date，两者都不过滤消息
        return true;
    }
    
    /**
     * 高亮搜索关键词
     */
    highlightSearchTerm(text, term) {
        const escapedText = this.escapeHtml(text);
        const escapedTerm = this.escapeHtml(term);
        const regex = new RegExp(`(${escapedTerm})`, 'gi');
        return escapedText.replace(regex, '<span style="background: yellow; color: black; padding: 2px;">$1</span>');
    }

    /**
     * 读取当前用户头像
     */
    getCurrentUserAvatar() {
        // 优先使用内存中的 userInfo，其次从本地存储读取
        if (!this.userInfo || !this.userInfo.avatar) {
            try {
                const info = (typeof AuthManager !== 'undefined' && AuthManager.getUserInfo)
                    ? AuthManager.getUserInfo()
                    : null;
                if (info) this.userInfo = info;
            } catch (e) {}
        }
        return (this.userInfo && this.userInfo.avatar) ? this.userInfo.avatar : '👤';
    }

    /**
     * 生成用户头像 HTML
     */
    buildUserAvatarHTML() {
        const avatar = this.getCurrentUserAvatar();
        if (typeof avatar === 'string' && avatar.startsWith('data:image')) {
            return `<img src="${avatar}" alt="用户" style="width:100%;height:100%;object-fit:cover;">`;
        }
        // emoji 或单字符
        return this.escapeHtml(avatar);
    }

    /**
     * 刷新所有用户头像（头像更新后调用）
     */
    refreshAllUserAvatars() {
        const html = this.buildUserAvatarHTML();
        document.querySelectorAll('.history-message-avatar.user').forEach(el => {
            el.innerHTML = html;
        });
    }
    
    /**
     * 格式化历史日期
     */
    formatHistoryDate(dateString) {
        const date = new Date(dateString);
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        
        if (date.toDateString() === today.toDateString()) {
            return '今天';
        } else if (date.toDateString() === yesterday.toDateString()) {
            return '昨天';
        } else {
            return date.toLocaleDateString('zh-CN', {
                month: 'long',
                day: 'numeric'
            });
        }
    }
    
    /**
     * 格式化历史时间
     */
    formatHistoryTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }
    
    /**
     * HTML转义
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * 预渲染：从本地缓存快速显示消息
     */
    preloadConversationFromCache() {
        // 游客模式不预加载
        if (this.userMode === 'guest') {
            return;
        }
        
        const key = this.getHistoryStorageKey();
        const str = localStorage.getItem(key);
        if (!str) return;
        let list = [];
        try { list = JSON.parse(str) || []; } catch (e) { return; }
        if (!Array.isArray(list) || list.length === 0) return;
        this.preRenderedFromCache = true;
        this.suppressCacheUpdate = true;
        this.messagesContainer.innerHTML = '';
        this.lastMessageTime = null;
        list.forEach(m => {
            if (m.role === 'user' || m.role === 'assistant') {
                this.addMessage(m.role, m.content, m.timestamp);
            }
        });
        this.suppressCacheUpdate = false;
        this.scrollToBottom();
    }

    getHistoryStorageKey() {
        const uid = (this.userInfo && this.userInfo.user_id) ? this.userInfo.user_id : 'guest';
        return `CHAT_HISTORY:${uid}`;
    }

    /**
     * 清理本地缓存的聊天历史
     */
    clearLocalCache() {
        const key = this.getHistoryStorageKey();
        try {
            localStorage.removeItem(key);
            console.log('🗑️ 已清理本地聊天历史缓存');
            return true;
        } catch (e) {
            console.error('❌ 清理缓存失败:', e);
            return false;
        }
    }

    cacheMessage(role, content, timestamp) {
        // 游客模式不缓存消息
        if (this.userMode === 'guest') {
            return;
        }
        
        const key = this.getHistoryStorageKey();
        let list = [];
        try { list = JSON.parse(localStorage.getItem(key) || '[]'); } catch (e) { list = []; }
        list.push({ role, content, timestamp });
        if (list.length > 100) list = list.slice(-100);
        
        try {
            localStorage.setItem(key, JSON.stringify(list));
        } catch (e) {
            if (e.name === 'QuotaExceededError') {
                console.warn('💾 localStorage空间不足，只保留最近50条消息');
                try {
                    localStorage.setItem(key, JSON.stringify(list.slice(-50)));
                } catch (e2) {
                    console.error('❌ 无法缓存消息:', e2);
                }
            } else {
                console.error('❌ 缓存消息失败:', e);
            }
        }
    }

    replaceCacheWithServer(messages) {
        // 游客模式不缓存消息
        if (this.userMode === 'guest') {
            return;
        }
        
        console.log('🔄 replaceCacheWithServer 被调用，服务器消息数量:', messages.length);
        
        const key = this.getHistoryStorageKey();
        
        // 清理消息数据：移除音频base64以节省存储空间
        const cleanedMessages = messages.slice(-100).map(msg => {
            const cleaned = { ...msg };
            // 移除metadata中的音频数据
            if (cleaned.metadata) {
                const cleanedMetadata = { ...cleaned.metadata };
                delete cleanedMetadata.audio_base64;
                cleaned.metadata = cleanedMetadata;
            }
            return cleaned;
        });
        
        try {
            localStorage.setItem(key, JSON.stringify(cleanedMessages));
            console.log('✅ 缓存已更新，消息数量:', cleanedMessages.length);
        } catch (e) {
            if (e.name === 'QuotaExceededError') {
                console.warn('💾 localStorage空间不足，清理旧数据后重试');
                // 只保留最近50条消息
                try {
                    localStorage.setItem(key, JSON.stringify(cleanedMessages.slice(-50)));
                } catch (e2) {
                    console.error('❌ 无法保存聊天历史到localStorage:', e2);
                }
            } else {
                console.error('❌ 保存聊天历史失败:', e);
            }
        }
        
        // 🔥 关键修复：检查服务器消息是否比当前显示的更完整
        const currentMessages = this.getCurrentDisplayedMessages();
        console.log('🔍 当前显示消息数量:', currentMessages.length, '服务器消息数量:', messages.length);
        
        if (messages.length > currentMessages.length) {
            console.log('🔄 服务器消息更完整，重新渲染页面');
            // 服务器的消息更完整，重新渲染
            this.batchRenderHistory(messages);
        } else {
            console.log('✅ 当前显示已是最新，无需重新渲染');
        }
    }

    /**
     * 获取当前页面显示的消息
     */
    getCurrentDisplayedMessages() {
        const messageElements = this.messagesContainer.querySelectorAll('.message');
        const messages = [];
        messageElements.forEach(el => {
            const role = el.classList.contains('user') ? 'user' : 'assistant';
            const content = el.querySelector('.message-text')?.textContent || '';
            const timestamp = el.dataset.timestamp || new Date().toISOString();
            messages.push({ role, content, timestamp });
        });
        return messages;
    }

    /**
     * 渲染侧边栏历史记录
     */
    renderHistorySidebar(groupedMessages) {
        const contentDiv = document.getElementById('historyContent');
        if (!contentDiv) return;
        
        if (!groupedMessages || Object.keys(groupedMessages).length === 0) {
            contentDiv.innerHTML = '<div class="history-empty">暂无聊天记录</div>';
            return;
        }
        
        let html = '';
        const dates = Object.keys(groupedMessages).sort().reverse(); // 最新的在前
        
        dates.forEach(date => {
            const messages = groupedMessages[date];
            const dateObj = new Date(date);
            const dateStr = this.formatDateChinese(dateObj);
            
            html += `<div class="history-date-group">`;
            html += `<div class="history-date">${dateStr}</div>`;
            
            messages.forEach(msg => {
                if (msg.role === 'user' || msg.role === 'assistant') {
                    const preview = msg.content.length > 50 ? msg.content.substring(0, 50) + '...' : msg.content;
                    const time = new Date(msg.timestamp).toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
                    html += `
                        <div class="history-item">
                            <div class="history-time">${time}</div>
                            <div class="history-preview">${msg.role === 'user' ? '我' : 'AI'}: ${preview}</div>
                        </div>
                    `;
                }
            });
            
            html += `</div>`;
        });
        
        contentDiv.innerHTML = html;
    }
    
    /**
     * 格式化日期为中文
     */
    formatDateChinese(date) {
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        
        if (date.toDateString() === today.toDateString()) {
            return '今天';
        } else if (date.toDateString() === yesterday.toDateString()) {
            return '昨天';
        } else {
            return date.toLocaleDateString('zh-CN', {month: 'long', day: 'numeric'});
        }
    }
    
    /**
     * 渲染指定日期的历史列表
     */
    renderHistoryForDate(messages, dateLabel) {
        const contentDiv = document.getElementById('historyContent');
        if (!contentDiv) return;
        
        if (!messages || messages.length === 0) {
            contentDiv.innerHTML = '<div class="history-empty">暂无聊天记录</div>';
            return;
        }
        
        let html = '';
        html += `<div class="history-date-header">${this.escapeHtml(dateLabel || '所选日期')}</div>`;
        
        for (const msg of messages) {
            const sender = msg.role === 'user' ? '我' : '巴卫';
            const avatarClass = msg.role === 'user' ? 'user' : 'assistant';
            const time = this.formatHistoryTime(msg.timestamp);
            
            // 检查是否是语音消息
            const isVoiceInput = msg.metadata && msg.metadata.is_voice_input;
            const isVoiceResponse = msg.metadata && msg.metadata.is_voice_response;
            const hasAudio = msg.metadata && msg.metadata.audio_base64;
            const isVoice = isVoiceInput || isVoiceResponse;
            
            let contentHTML = '';
            if (isVoice) {
                // 语音消息显示为迷你语音气泡
                const messageId = `sidebar_voice_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                if (hasAudio) {
                    this.audioMessages.set(messageId, {
                        audio: msg.metadata.audio_base64,
                        text: msg.content,
                        duration: 0,
                        isPlaying: false,
                        hasPlayed: true
                    });
                }
                
                contentHTML = `
                    <div class="history-message-header">
                        <span class="history-message-sender">${sender}</span>
                        <span class="history-message-time">${time}</span>
                    </div>
                    <div class="history-voice-bubble" data-message-id="${messageId}" ${hasAudio ? 'onclick="chat.toggleVoicePlayback(\'' + messageId + '\')"' : ''} style="cursor: ${hasAudio ? 'pointer' : 'default'};">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" style="margin-right:4px;">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                        <span style="font-size:12px;">3"</span>
                    </div>
                `;
            } else {
                const preview = (msg.content || '').toString();
                contentHTML = `
                    <div class="history-message-header">
                        <span class="history-message-sender">${sender}</span>
                        <span class="history-message-time">${time}</span>
                    </div>
                    <div class="history-message-text">${this.escapeHtml(preview)}</div>
                `;
            }
            
            html += `
                <div class="history-message-item" data-timestamp="${msg.timestamp}">
                    <div class="history-message-avatar ${avatarClass}">` +
                        (avatarClass === 'assistant'
                            ? `<span style="font-size:24px;">💙</span>`
                            : this.buildUserAvatarHTML()) +
                    `</div>
                    <div class="history-message-content">
                        ${contentHTML}
                    </div>
                </div>
            `;
        }
        
        contentDiv.innerHTML = html;
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    const chat = new VoiceChat();
    
    // 处理历史记录侧边栏消息
    const originalHandleMessage = chat.handleMessage.bind(chat);
    chat.handleMessage = function(data) {
        const message = typeof data === 'string' ? JSON.parse(data) : data;
        const payload = message.content || message; // 后端通过 content 包裹
        
        // 处理侧边栏相关消息
        if (message.type === 'grouped_history') {
            const grouped = payload.grouped_messages || {};
            this.groupedHistoryCache = grouped;
            this.renderHistorySidebar(grouped);
            return;
        } else if (message.type === 'search_results') {
            this.renderSearchResults(payload.results || message.results || [], payload.query || message.query || '');
            return;
        } else if (message.type === 'history_by_date') {
            const msgs = (payload.messages || []).filter(m => m.role === 'user' || m.role === 'assistant');
            const dateInfo = (payload.start_date && payload.end_date && payload.start_date === payload.end_date)
                ? payload.start_date
                : `${payload.start_date || ''}${payload.end_date ? ' - ' + payload.end_date : ''}`;
            this.renderHistoryForDate(msgs, dateInfo);
            return;
        }
        
        // 其他消息交给原处理函数
        originalHandleMessage(data);
    };
    
    // 初始化侧边栏 - 已禁用聊天记录功能，但后端继续保存数据
    // chat.initHistorySidebar();
    
    // 初始化青少年心理健康功能
    if (typeof TeenMentalHealthFeatures !== 'undefined') {
        window.teenFeatures = new TeenMentalHealthFeatures(chat);
        chat.teenFeatures = window.teenFeatures;  
        console.log('✅ 青少年心理健康功能已启用');
        console.log('🔗 teenFeatures引用已设置:', !!chat.teenFeatures);
    } else {
        console.warn('⚠️ TeenMentalHealthFeatures未加载');
    }
});
