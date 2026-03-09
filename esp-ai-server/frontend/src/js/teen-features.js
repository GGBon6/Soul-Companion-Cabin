/**
 * 心灵小屋 - 青少年心理健康功能扩展
 * 角色选择、心情签到、日记、睡前故事、树洞模式等
 * 版本: 20251113164600 - 修复handleWebSocketMessage变量引用错误
 */
console.log('🔧 teen-features.js 已加载 - 版本: 20251113164600 - 修复变量引用错误');

// 角色数据
const CHARACTERS = [
    { id: 'xiaonuan', name: '小暖', icon: '🌸', desc: '温柔陪伴，善解人意' },
    { id: 'xiaocheng', name: '小橙', icon: '🌟', desc: '活力满满，积极向上' },
    { id: 'xiaozhi', name: '小智', icon: '💡', desc: '睿智引导，解答疑惑' },
    { id: 'xiaoshu', name: '小树', icon: '🌳', desc: '安静倾听，包容一切' }
];

// 情绪数据
const MOODS = [
    { id: 'happy', name: '开心', emoji: '😊', color: '#FFD93D' },
    { id: 'excited', name: '兴奋', emoji: '🤩', color: '#FF6B6B' },
    { id: 'calm', name: '平静', emoji: '😌', color: '#95E1D3' },
    { id: 'sad', name: '难过', emoji: '😢', color: '#6C9BCF' },
    { id: 'angry', name: '生气', emoji: '😠', color: '#FF4757' },
    { id: 'anxious', name: '焦虑', emoji: '😰', color: '#FFA502' },
    { id: 'tired', name: '疲惫', emoji: '😴', color: '#A4B0BD' },
    { id: 'confused', name: '迷茫', emoji: '😕', color: '#B8B8B8' }
];

class TeenMentalHealthFeatures {
    constructor(chatInstance) {
        this.chat = chatInstance;
        this.currentCharacter = 'xiaonuan';
        
        // 检查是否有待同步的角色设置
        if (this.chat.pendingCharacterSync) {
            console.log('🎭 发现待同步角色设置:', this.chat.pendingCharacterSync);
            this.currentCharacter = this.chat.pendingCharacterSync;
            this.chat.pendingCharacterSync = null;
            
            // 延迟更新UI，确保DOM已加载
            setTimeout(() => {
                this.updateCharacterUI(this.currentCharacter);
                console.log('🎭 已应用缓存的角色设置:', this.currentCharacter);
            }, 100);
        }
        
        // 延迟获取用户当前角色设置
        setTimeout(() => {
            this.syncCurrentCharacter();
        }, 1500);
        this.treeHoleMode = false;
        this.selectedMood = null;
        this.init();
    }

    init() {
        this.initCharacterSelector();
        this.initMoodCheckin();
        this.initDiaryViewer();
        this.initBedtimeStory();
        this.initSettings();
        this.initQuickActions();
        this.bindEvents();
        
        // 定期检查主动对话
        this.startProactiveChatChecker();
    }

    // ==================== 角色选择 ====================
    
    initCharacterSelector() {
        const grid = document.getElementById('characterGrid');
        if (!grid) return;
        
        grid.innerHTML = CHARACTERS.map(char => `
            <div class="character-card ${char.id === this.currentCharacter ? 'active' : ''}" 
                 data-character-id="${char.id}">
                <span class="character-icon">${char.icon}</span>
                <div class="character-name">${char.name}</div>
                <div class="character-desc">${char.desc}</div>
            </div>
        `).join('');
        
        // 绑定点击事件
        grid.querySelectorAll('.character-card').forEach(card => {
            card.addEventListener('click', () => {
                const characterId = card.dataset.characterId;
                this.switchCharacter(characterId);
            });
        });
    }

    switchCharacter(characterId) {
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) {
            this.chat.showToast('连接已断开，请刷新页面', 'error');
            return;
        }

        this.currentCharacter = characterId;
        
        // 发送切换请求
        this.chat.sendMessage({
            type: 'switch_character',
            character_id: characterId
        });

        // 更新UI
        this.updateCharacterUI(characterId);

        closeModal('characterModal');
        const character = CHARACTERS.find(c => c.id === characterId);
        this.chat.showToast(`已切换到 ${character ? character.name : characterId}`, 'success');
    }

    updateCharacterUI(characterId) {
        const character = CHARACTERS.find(c => c.id === characterId);
        if (character) {
            // 更新顶部角色显示
            const characterName = document.getElementById('characterName');
            const characterAvatar = document.getElementById('characterAvatar');
            
            if (characterName) {
                characterName.textContent = character.name;
            }
            
            if (characterAvatar) {
                const avatarEmoji = characterAvatar.querySelector('.avatar-emoji');
                if (avatarEmoji) {
                    avatarEmoji.textContent = character.icon;
                }
            }
            
            // 更新角色卡片激活状态
            document.querySelectorAll('.character-card').forEach(card => {
                card.classList.toggle('active', card.dataset.characterId === characterId);
            });
        }
    }

    syncCurrentCharacter() {
        // 请求获取用户档案信息，包括当前角色
        console.log('🎭 syncCurrentCharacter 被调用');
        console.log('🎭 WebSocket状态:', this.chat.ws ? this.chat.ws.readyState : 'null');
        
        if (this.chat.ws && this.chat.ws.readyState === WebSocket.OPEN) {
            console.log('🎭 发送get_profile请求...');
            this.chat.sendMessage({ type: 'get_profile' });
        } else {
            console.log('⚠️ WebSocket未连接，延迟重试...');
            setTimeout(() => this.syncCurrentCharacter(), 1000);
        }
    }

    // ==================== 心情签到 ====================
    
    initMoodCheckin() {
        const grid = document.getElementById('moodGrid');
        if (!grid) return;
        
        grid.innerHTML = MOODS.map(mood => `
            <button class="mood-btn" data-mood-id="${mood.id}">
                <span class="mood-emoji">${mood.emoji}</span>
                <span class="mood-name">${mood.name}</span>
            </button>
        `).join('');
        
        // 更新日期
        const dateEl = document.getElementById('moodDate');
        if (dateEl) {
            const today = new Date();
            dateEl.textContent = today.toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                weekday: 'long'
            });
        }
        
        // 绑定点击事件
        grid.querySelectorAll('.mood-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const moodId = btn.dataset.moodId;
                this.selectMood(moodId);
            });
        });
        
        // 强度滑块
        const slider = document.getElementById('intensitySlider');
        const valueDisplay = document.getElementById('intensityValue');
        if (slider && valueDisplay) {
            slider.addEventListener('input', (e) => {
                valueDisplay.textContent = e.target.value;
            });
        }
        
        // 备注字数统计
        const noteInput = document.getElementById('moodNoteInput');
        const charCount = document.getElementById('noteCharCount');
        if (noteInput && charCount) {
            noteInput.addEventListener('input', (e) => {
                charCount.textContent = e.target.value.length;
            });
        }
        
        // 确认按钮
        const confirmBtn = document.getElementById('confirmMoodBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => this.submitMoodCheckin());
        }
    }

    selectMood(moodId) {
        this.selectedMood = moodId;
        
        // 更新UI
        document.querySelectorAll('.mood-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.moodId === moodId);
        });
        
        // 显示强度和备注区域
        document.getElementById('moodIntensitySection').style.display = 'block';
        document.getElementById('moodNoteSection').style.display = 'block';
        document.getElementById('confirmMoodBtn').disabled = false;
    }

    async submitMoodCheckin() {
        if (!this.selectedMood) return;
        
        const intensity = parseInt(document.getElementById('intensitySlider').value);
        const note = document.getElementById('moodNoteInput').value.trim();
        
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) {
            this.chat.showToast('连接已断开，请刷新页面', 'error');
            return;
        }

        // 发送签到请求
        this.chat.sendMessage({
            type: 'mood_checkin',
            // 与后端遗留处理器保持一致：使用 mood_score / mood_note
            mood_score: intensity,
            mood_note: note,
            // 兼容保留：如果后端以后支持直接按情绪ID记录
            mood: this.selectedMood,
            intensity: intensity
        });

        const mood = MOODS.find(m => m.id === this.selectedMood);
        this.chat.showToast(`${mood.emoji} 签到成功！`, 'success');
        
        // 重置表单
        this.selectedMood = null;
        document.getElementById('moodNoteInput').value = '';
        document.getElementById('intensitySlider').value = 3;
        document.getElementById('intensityValue').textContent = 3;
        document.getElementById('noteCharCount').textContent = 0;
        document.querySelectorAll('.mood-btn').forEach(btn => btn.classList.remove('active'));
        document.getElementById('moodIntensitySection').style.display = 'none';
        document.getElementById('moodNoteSection').style.display = 'none';
        document.getElementById('confirmMoodBtn').disabled = true;
        
        // 加载统计数据
        setTimeout(() => this.loadMoodStats(), 500);
    }

    loadMoodStats() {
        // 游客模式不加载统计
        if (this.chat.userMode === 'guest') return;
        
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) return;
        
        this.chat.sendMessage({
            type: 'get_mood_history',
            days: 7
        });
        
        document.getElementById('moodStats').style.display = 'block';
    }

    renderMoodStats(history) {
        const chartEl = document.getElementById('moodChart');
        if (!chartEl || !history || history.length === 0) return;
        
        // 简单的文本统计展示
        const moodCounts = {};
        history.forEach(entry => {
            moodCounts[entry.mood] = (moodCounts[entry.mood] || 0) + 1;
        });
        
        let html = '<div style="display: flex; gap: 12px; flex-wrap: wrap;">';
        Object.entries(moodCounts).forEach(([moodId, count]) => {
            const mood = MOODS.find(m => m.id === moodId);
            if (mood) {
                html += `
                    <div style="background: white; padding: 12px 16px; border-radius: 10px; text-align: center; flex: 1; min-width: 80px;">
                        <div style="font-size: 24px;">${mood.emoji}</div>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">${mood.name}</div>
                        <div style="font-size: 16px; font-weight: 600; color: var(--primary-color); margin-top: 4px;">${count}次</div>
                    </div>
                `;
            }
        });
        html += '</div>';
        chartEl.innerHTML = html;
    }

    renderMoodStatistics(statistics) {
        const chartEl = document.getElementById('moodChart');
        if (!chartEl || !statistics) return;
        
        // 处理统计数据格式
        const moodCounts = statistics.mood_counts || statistics;
        
        if (!moodCounts || Object.keys(moodCounts).length === 0) {
            chartEl.innerHTML = '<div style="text-align: center; color: var(--text-secondary); padding: 20px;">暂无心情数据</div>';
            return;
        }
        
        let html = '<div style="display: flex; gap: 12px; flex-wrap: wrap;">';
        Object.entries(moodCounts).forEach(([moodId, count]) => {
            const mood = MOODS.find(m => m.id === moodId);
            if (mood && count > 0) {
                html += `
                    <div style="background: white; padding: 12px 16px; border-radius: 10px; text-align: center; flex: 1; min-width: 80px;">
                        <div style="font-size: 24px;">${mood.emoji}</div>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">${mood.name}</div>
                        <div style="font-size: 16px; font-weight: 600; color: var(--primary-color); margin-top: 4px;">${count}次</div>
                    </div>
                `;
            }
        });
        html += '</div>';
        chartEl.innerHTML = html;
    }

    // ==================== 日记功能 ====================
    
    initDiaryViewer() {
        // 生成日记按钮
        const generateBtn = document.getElementById('generateDiaryBtn');
        if (generateBtn) {
            generateBtn.addEventListener('click', () => this.generateDiary());
        }
        
        // 返回按钮
        const backBtn = document.getElementById('backToDiaryList');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                document.getElementById('diaryList').style.display = 'block';
                document.getElementById('diaryDetail').style.display = 'none';
            });
        }
        
        // 加载日记列表
        this.loadDiaryList();
    }

    generateDiary() {
        // 游客模式提示
        if (this.chat.userMode === 'guest') {
            this.chat.showToast('💙 日记生成需要登录后才能使用哦～', 'info');
            return;
        }
        
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) {
            this.chat.showToast('连接已断开，请刷新页面', 'error');
            return;
        }

        this.chat.sendMessage({
            type: 'generate_diary'
        });

        this.chat.showToast('正在生成日记，请稍候...', 'info');
        document.getElementById('loadingOverlay').style.display = 'flex';
    }

    loadDiaryList() {
        // 游客模式不加载日记
        if (this.chat.userMode === 'guest') return;
        
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) return;
        
        this.chat.sendMessage({
            type: 'get_diary_list',
            limit: 30
        });
    }

    renderDiaryList(diaries) {
        const listEl = document.getElementById('diaryList');
        if (!listEl) return;
        
        if (!diaries || diaries.length === 0) {
            listEl.innerHTML = '<div class="diary-empty">还没有日记哦<br>和我聊聊天，系统会自动生成日记</div>';
            return;
        }
        
        listEl.innerHTML = diaries.map(diary => `
            <div class="diary-item" data-date="${diary.date}">
                <div class="diary-item-header">
                    <div class="diary-title">${this.escapeHtml(diary.title)}</div>
                    <div class="diary-date">${this.formatDiaryDate(diary.date)}</div>
                </div>
                <div class="diary-preview">${this.escapeHtml(diary.content)}</div>
            </div>
        `).join('');
        
        // 绑定点击事件
        listEl.querySelectorAll('.diary-item').forEach(item => {
            item.addEventListener('click', () => {
                const date = item.dataset.date;
                this.viewDiary(date);
            });
        });
    }

    viewDiary(date) {
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) return;
        
        this.chat.sendMessage({
            type: 'get_diary',
            date: date
        });
    }

    showDiaryDetail(diary) {
        const detailEl = document.getElementById('diaryDetail');
        const wrapperEl = document.getElementById('diaryContentWrapper');
        if (!detailEl || !wrapperEl) return;
        
        wrapperEl.innerHTML = `
            <div class="diary-full-date">${this.formatDiaryDate(diary.date)}</div>
            <div class="diary-full-title">${this.escapeHtml(diary.title)}</div>
            <div class="diary-full-content">${this.escapeHtml(diary.content)}</div>
        `;
        
        document.getElementById('diaryList').style.display = 'none';
        detailEl.style.display = 'block';
    }

    // ==================== 睡前故事 ====================
    
    initBedtimeStory() {
        this.selectedStoryType = 'preset'; // 'preset' or 'generated'
        this.selectedTheme = null;
        this.currentStory = null;
        
        // 故事类型切换按钮
        const typeButtons = document.querySelectorAll('.story-type-btn');
        typeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const type = btn.dataset.type;
                this.selectStoryType(type);
            });
        });
        
        // 获取故事按钮
        const getStoryBtn = document.getElementById('getStoryBtn');
        if (getStoryBtn) {
            getStoryBtn.addEventListener('click', () => this.requestBedtimeStory());
        }
        
        // 再听一遍按钮
        const readAgainBtn = document.getElementById('readAgainBtn');
        if (readAgainBtn) {
            readAgainBtn.addEventListener('click', () => this.readStoryAgain());
        }
        
        // 换一个故事按钮
        const getAnotherBtn = document.getElementById('getAnotherStoryBtn');
        if (getAnotherBtn) {
            getAnotherBtn.addEventListener('click', () => {
                this.hideStoryContent();
                this.requestBedtimeStory();
            });
        }
        
        // 延迟加载主题列表，等待WebSocket连接
        this.scheduleThemeLoading();
    }
    
    selectStoryType(type) {
        this.selectedStoryType = type;
        
        // 更新按钮状态
        document.querySelectorAll('.story-type-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.type === type);
        });
        
        // 显示/隐藏主题选择
        const themesSection = document.getElementById('storyThemes');
        if (type === 'generated') {
            themesSection.style.display = 'block';
        } else {
            themesSection.style.display = 'none';
            this.selectedTheme = null;
        }
    }
    
    scheduleThemeLoading() {
        // 检查WebSocket连接状态
        if (this.chat.ws && this.chat.ws.readyState === WebSocket.OPEN) {
            // 连接已建立，直接加载主题
            this.loadStoryThemes();
        } else {
            // 连接未建立，使用默认主题并设置重试
            console.log('🔄 WebSocket未连接，使用默认主题，稍后重试加载');
            this.loadDefaultThemes();
            
            // 设置重试机制
            this.themeLoadRetryCount = 0;
            this.scheduleThemeRetry();
        }
    }
    
    scheduleThemeRetry() {
        if (this.themeLoadRetryCount >= 10) {
            console.log('📋 主题加载重试次数已达上限，使用默认主题');
            return;
        }
        
        setTimeout(() => {
            if (this.chat.ws && this.chat.ws.readyState === WebSocket.OPEN) {
                console.log('🎯 WebSocket已连接，重新加载故事主题');
                this.loadStoryThemes();
            } else {
                this.themeLoadRetryCount++;
                this.scheduleThemeRetry();
            }
        }, 1000); // 每秒重试一次
    }
    
    loadStoryThemes() {
        // 从后端获取故事主题列表
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) {
            console.warn('WebSocket未连接，使用默认主题');
            this.loadDefaultThemes();
            return;
        }
        
        // 请求故事主题
        this.chat.sendMessage({
            type: 'get_story_themes'
        });
    }
    
    loadDefaultThemes() {
        // 默认主题（作为降级方案）
        const defaultThemes = [
            { name: '智慧的寓言', description: '富有哲理的小故事，启发思考' },
            { name: '思考的旅程', description: '引导深入思考的成长故事' },
            { name: '古老的传说', description: '神秘而富有文化底蕴的传说故事' },
            { name: '哲理的故事', description: '蕴含人生道理的温暖故事' },
            { name: '成长的启示', description: '关于成长和自我发现的故事' }
        ];
        
        this.renderThemes(defaultThemes);
    }
    
    renderThemes(themes) {
        const themeGrid = document.getElementById('themeGrid');
        
        if (themeGrid) {
            themeGrid.innerHTML = themes.map(theme => `
                <button class="theme-btn" data-theme="${theme.name}" title="${theme.description}">
                    <div class="theme-name">${theme.name}</div>
                    <div class="theme-desc">${theme.description}</div>
                </button>
            `).join('');
            
            // 绑定主题选择事件
            themeGrid.querySelectorAll('.theme-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    this.selectedTheme = btn.dataset.theme;
                    themeGrid.querySelectorAll('.theme-btn').forEach(b => {
                        b.classList.toggle('active', b === btn);
                    });
                });
            });
        }
    }
    
    requestBedtimeStory() {
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) {
            this.chat.showToast('连接已断开，请刷新页面', 'error');
            return;
        }
        
        // 如果是生成模式但没选主题，提示用户
        if (this.selectedStoryType === 'generated' && !this.selectedTheme) {
            this.chat.showToast('请先选择一个故事主题', 'info');
            return;
        }
        
        // 显示加载状态
        document.getElementById('storyLoading').style.display = 'block';
        document.getElementById('storyContentArea').style.display = 'none';
        document.getElementById('getStoryBtn').disabled = true;
        
        // 发送请求
        const message = {
            type: 'get_bedtime_story',
            story_type: this.selectedStoryType,
        };
        
        if (this.selectedStoryType === 'generated' && this.selectedTheme) {
            message.theme = this.selectedTheme;
        }
        
        this.chat.sendMessage(message);
    }
    
    showBedtimeStory(story) {
        this.currentStory = story;
        
        // 隐藏加载状态
        document.getElementById('storyLoading').style.display = 'none';
        document.getElementById('getStoryBtn').disabled = false;
        
        // 显示故事内容
        document.getElementById('storyContentArea').style.display = 'block';
        document.getElementById('storyTitle').textContent = story.title || '睡前故事';
        
        // 显示角色和类型信息
        const characterName = CHARACTERS.find(c => c.id === story.character_id)?.name || '小暖';
        const typeName = story.type === 'preset' ? '精选故事' : '创作故事';
        document.getElementById('storyCharacter').textContent = `${characterName} 讲述`;
        document.getElementById('storyTypeBadge').textContent = typeName;
        
        // 显示故事内容（保留换行）
        const storyText = document.getElementById('storyText');
        storyText.innerHTML = this.escapeHtml(story.content).replace(/\n/g, '<br>');
        
        // 滚动到故事内容
        setTimeout(() => {
            storyText.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
    }
    
    hideStoryContent() {
        document.getElementById('storyContentArea').style.display = 'none';
        this.currentStory = null;
    }
    
    readStoryAgain() {
        if (!this.currentStory) return;
        
        // 滚动到故事顶部
        const storyText = document.getElementById('storyText');
        storyText.scrollIntoView({ behavior: 'smooth', block: 'start' });
        
        // 提示可以使用语音朗读
        this.chat.showToast('提示：您可以向AI说"把故事读给我听"来使用语音朗读', 'info');
    }

    // ==================== 树洞模式 ====================
    
    toggleTreeHoleMode() {
        this.treeHoleMode = !this.treeHoleMode;
        
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) {
            this.chat.showToast('连接已断开，请刷新页面', 'error');
            return;
        }

        this.chat.sendMessage({
            type: 'toggle_tree_hole_mode',
            enabled: this.treeHoleMode
        });

        // 更新UI
        const notice = document.getElementById('treeHoleNotice');
        const btn = document.getElementById('treeHoleBtn');
        
        if (this.treeHoleMode) {
            notice.style.display = 'flex';
            btn.style.background = 'linear-gradient(135deg, var(--accent-color) 0%, #B9F3E4 100%)';
            btn.style.borderColor = 'var(--accent-color)';
            this.chat.showToast('🌳 树洞模式已开启', 'info');
        } else {
            notice.style.display = 'none';
            btn.style.background = '';
            btn.style.borderColor = '';
            this.chat.showToast('树洞模式已关闭', 'info');
        }
    }

    // ==================== 主动对话 ====================
    
    startProactiveChatChecker() {
        // 每5分钟检查一次
        setInterval(() => {
            if (this.chat.ws && this.chat.ws.readyState === WebSocket.OPEN) {
                this.checkProactiveChat();
            }
        }, 5 * 60 * 1000);
    }

    checkProactiveChat() {
        // 游客模式不启用主动对话
        if (this.chat.userMode === 'guest') return;
        
        const enabled = document.getElementById('proactiveChatToggle')?.checked;
        if (!enabled) return;
        
        this.chat.sendMessage({
            type: 'check_proactive_chat'
        });
    }

    // ==================== 设置 ====================
    
    initSettings() {
        // 主动对话开关
        const proactiveToggle = document.getElementById('proactiveChatToggle');
        const timeSection = document.getElementById('proactiveChatTimeSection');
        
        if (proactiveToggle && timeSection) {
            proactiveToggle.addEventListener('change', (e) => {
                timeSection.style.display = e.target.checked ? 'flex' : 'none';
                this.updateProactiveSettings();
            });
        }
        
        // 主动对话时间
        const timeInput = document.getElementById('proactiveChatTime');
        if (timeInput) {
            timeInput.addEventListener('change', () => {
                this.updateProactiveSettings();
            });
        }
    }

    updateProactiveSettings() {
        // 游客模式不保存设置
        if (this.chat.userMode === 'guest') return;
        
        const enabled = document.getElementById('proactiveChatToggle')?.checked;
        const time = document.getElementById('proactiveChatTime')?.value;
        
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) return;
        
        this.chat.sendMessage({
            type: 'update_proactive_settings',
            enabled: enabled,
            chat_time: time
        });
    }

    // ==================== 快捷操作 ====================
    
    initQuickActions() {
        // 睡前故事
        const storyBtn = document.getElementById('storyBtn');
        if (storyBtn) {
            storyBtn.addEventListener('click', () => {
                openModal('storyModal');
                // 切换角色时重新加载主题
                this.loadStoryThemes();
            });
        }
        
        // 树洞模式
        const treeHoleBtn = document.getElementById('treeHoleBtn');
        if (treeHoleBtn) {
            treeHoleBtn.addEventListener('click', () => this.toggleTreeHoleMode());
        }
        
        // 切换角色
        const switchCharacterBtn = document.getElementById('switchCharacterBtn');
        if (switchCharacterBtn) {
            switchCharacterBtn.addEventListener('click', () => openModal('characterModal'));
        }
    }

    // ==================== 事件绑定 ====================
    
    bindEvents() {
        // 心情签到按钮
        const moodBtn = document.getElementById('moodBtn');
        if (moodBtn) {
            moodBtn.addEventListener('click', () => {
                // 检查是否为游客模式
                if (this.chat.userMode === 'guest') {
                    this.chat.showToast('💙 心情签到需要登录后才能使用哦～', 'info');
                    return;
                }
                openModal('moodModal');
                this.loadMoodStats();
            });
        }
        
        // 日记按钮
        const diaryBtn = document.getElementById('diaryBtn');
        if (diaryBtn) {
            diaryBtn.addEventListener('click', () => {
                // 检查是否为游客模式
                if (this.chat.userMode === 'guest') {
                    this.chat.showToast('💙 心情日记需要登录后才能使用哦～', 'info');
                    return;
                }
                openModal('diaryModal');
                this.loadDiaryList();
            });
        }
        
        // 设置按钮
        const settingsBtn = document.getElementById('settingsBtn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => openModal('settingsModal'));
        }
        
        // 退出登录
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => {
                if (confirm('确定要退出登录吗？')) {
                    localStorage.removeItem('userMode');
                    localStorage.removeItem('userInfo');
                    window.location.href = 'login.html';
                }
            });
        }
    }

    // ==================== 同步用户档案 ====================
    
    syncProfile(profile) {
        console.log('🔧 syncProfile 被调用 - 版本: 20251113143500', profile);
        // 检查 profile 参数是否有效
        if (!profile || typeof profile !== 'object') {
            console.warn('⚠️ syncProfile: profile 参数无效');
            return;
        }
        
        // 同步角色
        if (profile.current_character) {
            this.currentCharacter = profile.current_character;
            console.log(`🔄 同步角色: ${this.currentCharacter}`);
            
            // 更新UI
            const character = CHARACTERS.find(c => c.id === this.currentCharacter);
            if (character) {
                console.log(`🎭 找到角色信息:`, character);
                
                // 更新角色名称
                const nameEl = document.getElementById('characterName');
                if (nameEl) {
                    nameEl.textContent = character.name;
                    console.log(`✅ 更新角色名称: ${character.name}`);
                } else {
                    console.warn('⚠️ 未找到characterName元素');
                }
                
                // 更新角色头像
                const avatarEl = document.getElementById('characterAvatar');
                if (avatarEl) {
                    const emojiEl = avatarEl.querySelector('.avatar-emoji');
                    if (emojiEl) {
                        emojiEl.textContent = character.icon;
                        console.log(`✅ 更新角色头像: ${character.icon}`);
                    } else {
                        console.warn('⚠️ 未找到.avatar-emoji元素');
                    }
                } else {
                    console.warn('⚠️ 未找到characterAvatar元素');
                }
                
                // 更新角色卡片激活状态
                const cards = document.querySelectorAll('.character-card');
                console.log(`🎯 找到${cards.length}个角色卡片`);
                cards.forEach(card => {
                    const isActive = card.dataset.characterId === this.currentCharacter;
                    card.classList.toggle('active', isActive);
                    if (isActive) {
                        console.log(`✅ 激活角色卡片: ${card.dataset.characterId}`);
                    }
                });
            } else {
                console.warn(`⚠️ 未找到角色信息: ${this.currentCharacter}`);
            }
        } else {
            console.warn('⚠️ profile中没有current_character字段');
        }
        
        // 同步树洞模式
        if (profile.tree_hole_mode !== undefined) {
            this.treeHoleMode = profile.tree_hole_mode;
            const notice = document.getElementById('treeHoleNotice');
            if (notice) {
                notice.style.display = this.treeHoleMode ? 'flex' : 'none';
            }
        }
        
        // 同步主动对话设置
        if (profile.proactive_chat_enabled !== undefined) {
            const toggle = document.getElementById('proactiveChatToggle');
            if (toggle) {
                toggle.checked = profile.proactive_chat_enabled;
                const timeSection = document.getElementById('proactiveChatTimeSection');
                if (timeSection) {
                    timeSection.style.display = profile.proactive_chat_enabled ? 'flex' : 'none';
                }
            }
        }
        
        if (profile.proactive_chat_time) {
            const timeInput = document.getElementById('proactiveChatTime');
            if (timeInput) {
                timeInput.value = profile.proactive_chat_time;
            }
        }
    }
    
    // ==================== WebSocket消息处理 ====================
    
    handleWebSocketMessage(message) {
        // 检查 message 参数是否有效
        if (!message) {
            console.warn('⚠️ handleWebSocketMessage: message 参数为空');
            return;
        }
        
        try {
            const type = message.type;
            const payload = message.content || message.data || message;
            
            switch (type) {
                case 'profile_data':
                case 'profile_sync': {
                    // 同步用户档案信息 - 增强错误处理
                    console.log(`🔄 收到 ${type} 消息，原始数据:`, message);
                    console.log(`🔄 提取的payload:`, payload);
                    
                    let profile = {};
                    if (payload && typeof payload === 'object') {
                        profile = payload.profile || payload;
                    }
                    
                    console.log(`🔄 最终profile对象:`, profile);
                    this.syncProfile(profile);
                    break;
                }
                
            case 'character_switched':
                // 角色切换成功
                break;
                
            case 'characters_list':
                // 接收角色列表（如果需要动态加载）
                break;
                
            case 'mood_checkin_success':
                // 心情签到成功
                const moodData = data.data || data;
                const displayText = moodData.mood_emoji 
                    ? `${moodData.mood_emoji} ${moodData.mood_name} 签到成功！`
                    : '心情签到成功！';
                this.chat.showToast(displayText, 'success');
                
                // 关闭心情签到弹窗
                closeModal('moodModal');
                
                // 重置表单
                this.selectedMood = null;
                document.getElementById('intensitySlider').value = 3;
                document.getElementById('intensityValue').textContent = 3;
                document.getElementById('moodNoteInput').value = '';
                document.getElementById('moodIntensitySection').style.display = 'none';
                document.getElementById('moodNoteSection').style.display = 'none';
                document.getElementById('confirmMoodBtn').disabled = true;
                
                // 移除所有心情按钮的选中状态
                document.querySelectorAll('.mood-btn').forEach(btn => {
                    btn.classList.remove('selected');
                });
                break;

            case 'mood_history':
                // 心情历史数据
                this.renderMoodStats(payload);
                break;

            case 'mood_statistics':
                // 心情统计数据
                this.renderMoodStatistics(payload);
                break;

            case 'diary_generated':
                document.getElementById('loadingOverlay').style.display = 'none';
                this.chat.showToast('日记生成成功！', 'success');
                this.loadDiaryList();
                break;

            case 'diary_data':
                this.showDiaryDetail(payload);
                break;

            case 'diary_list':
                // 后端返回数组
                this.renderDiaryList(payload);
                break;

            case 'story_themes':
                // 接收故事主题列表
                if (payload && payload.themes) {
                    this.renderThemes(payload.themes);
                }
                break;

            case 'story_types':
                // 接收故事类型列表
                if (payload && payload.types) {
                    this.renderStoryTypes(payload.types);
                }
                break;

            case 'story_recommendation':
                // 接收故事推荐
                if (payload) {
                    this.showStoryRecommendation(payload);
                }
                break;

            case 'bedtime_story':
                // 接收睡前故事
                if (payload && payload.story) {
                    this.showBedtimeStory(payload.story);
                } else {
                    this.showBedtimeStory(payload);
                }
                break;

            case 'tree_hole_mode_updated':
                // 树洞模式更新确认
                break;

            case 'proactive_settings_updated':
                this.chat.showToast('设置已保存', 'success');
                break;

            case 'proactive_chat_result':
                if (payload && payload.should_chat && payload.message) {
                    // 主动对话已由服务器发送
                }
                break;

            case 'history':
                // 处理历史消息
                console.log('📜 收到历史消息:', payload);
                if (payload && payload.messages) {
                    // 如果有历史消息数据，可以在这里处理显示逻辑
                    // 例如：this.displayHistoryMessages(payload.messages);
                }
                break;
        }
        } catch (error) {
            console.error('⚠️ teen-features handleWebSocketMessage 错误:', error);
        }
    }
    
    // ==================== 睡前故事辅助方法 ====================
    
    renderStoryTypes(types) {
        // 渲染故事类型选择按钮
        console.log('渲染故事类型:', types);
    }
    
    showStoryRecommendation(recommendation) {
        // 显示智能推荐
        console.log('显示故事推荐:', recommendation);
    }
    
    readStoryAgain() {
        // 再听一遍故事
        if (!this.currentStory) {
            this.chat.showToast('没有可重复的故事', 'error');
            return;
        }
        
        if (!this.chat.ws || this.chat.ws.readyState !== WebSocket.OPEN) {
            this.chat.showToast('连接已断开，请刷新页面', 'error');
            return;
        }
        
        // 发送重复播放请求
        this.chat.sendMessage({
            type: 'repeat_story',
            last_story: this.currentStory
        });
    }
    
    // ==================== 工具方法 ====================
    
    formatRelativeDate(dateString) {
        const date = new Date(dateString);
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        
        const dateOnly = new Date(date.getFullYear(), date.getMonth(), date.getDate());
        const todayOnly = new Date(today.getFullYear(), today.getMonth(), today.getDate());
        const yesterdayOnly = new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate());
        
        if (dateOnly.getTime() === todayOnly.getTime()) {
            return '今天';
        } else if (dateOnly.getTime() === yesterdayOnly.getTime()) {
            return '昨天';
        } else {
            return date.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' });
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// ==================== 弹窗辅助函数 ====================

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('show');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('show');
    }
}

// 点击背景关闭弹窗
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.classList.remove('show');
    }
});

// 导出给chat.js使用
window.TeenMentalHealthFeatures = TeenMentalHealthFeatures;

