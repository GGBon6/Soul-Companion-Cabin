/**
 * 音频处理模块
 * Audio Processing Module
 * 处理音频录制、播放、可视化等功能
 */

class AudioManager {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.audioContext = null;
        this.audioQueue = [];
        this.isPlaying = false;
        this.currentAudioSource = null;
        this.currentHtmlAudio = null;
        this.audioMessages = new Map();
        this.unplayedVoices = [];
        this.currentPlayingVoice = null;
        
        // 初始化AudioContext
        this.initAudioContext();
    }
    
    /**
     * 初始化音频上下文
     */
    initAudioContext() {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            Utils.log('AudioContext initialized');
        } catch (error) {
            Utils.error('Failed to initialize AudioContext:', error);
        }
    }
    
    /**
     * 开始录音
     * @returns {Promise<boolean>} 是否成功开始录音
     */
    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: window.CONFIG?.AUDIO?.SAMPLE_RATE || 16000
                } 
            });
            
            const mimeType = window.CONFIG?.AUDIO?.MIME_TYPE || 'audio/webm;codecs=opus';
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: mimeType
            });
            
            this.audioChunks = [];
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };
            
            this.mediaRecorder.start();
            Utils.log('Recording started');
            return true;
            
        } catch (error) {
            Utils.error('Failed to start recording:', error);
            Utils.showToast('无法访问麦克风，请检查权限设置', 'error');
            return false;
        }
    }
    
    /**
     * 停止录音
     * @returns {Promise<Blob>} 录音的音频Blob
     */
    stopRecording() {
        return new Promise((resolve, reject) => {
            if (!this.mediaRecorder || this.mediaRecorder.state === 'inactive') {
                reject(new Error('MediaRecorder is not active'));
                return;
            }
            
            this.mediaRecorder.onstop = () => {
                const audioBlob = new Blob(this.audioChunks, { 
                    type: window.CONFIG?.AUDIO?.FORMAT || 'audio/webm' 
                });
                
                // 停止所有音轨
                this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
                
                Utils.log('Recording stopped, size:', audioBlob.size);
                resolve(audioBlob);
            };
            
            this.mediaRecorder.stop();
        });
    }
    
    /**
     * 播放Base64编码的音频
     * @param {string} audioBase64 - Base64编码的音频数据
     * @param {string} messageId - 消息ID（可选）
     * @returns {Promise<void>}
     */
    async playAudioBase64(audioBase64, messageId = null) {
        try {
            // 停止当前正在播放的所有音频
            this.stopAllAudio();
            
            const audioBlob = Utils.base64ToBlob(audioBase64, 'audio/wav');
            const audioUrl = URL.createObjectURL(audioBlob);
            
            // 使用HTML5 Audio播放
            const audio = new Audio(audioUrl);
            this.currentHtmlAudio = audio;
            
            if (messageId) {
                this.currentPlayingVoice = messageId;
            }
            
            audio.onended = () => {
                URL.revokeObjectURL(audioUrl);
                this.currentHtmlAudio = null;
                if (messageId) {
                    this.currentPlayingVoice = null;
                    this.playNextVoice();
                }
                Utils.log('Audio playback ended');
            };
            
            audio.onerror = (error) => {
                Utils.error('Audio playback error:', error);
                URL.revokeObjectURL(audioUrl);
                this.currentHtmlAudio = null;
                if (messageId) {
                    this.currentPlayingVoice = null;
                    this.playNextVoice();
                }
            };
            
            await audio.play();
            Utils.log('Audio playback started');
            
        } catch (error) {
            Utils.error('Failed to play audio:', error);
            if (messageId) {
                this.currentPlayingVoice = null;
                this.playNextVoice();
            }
        }
    }
    
    /**
     * 播放下一个语音
     */
    playNextVoice() {
        if (this.unplayedVoices.length > 0 && !this.currentPlayingVoice) {
            const nextVoiceId = this.unplayedVoices.shift();
            const voiceData = this.audioMessages.get(nextVoiceId);
            
            if (voiceData && voiceData.audio) {
                this.playAudioBase64(voiceData.audio, nextVoiceId);
            }
        }
    }
    
    /**
     * 停止当前正在播放的音频
     */
    stopCurrentAudio() {
        // 停止 AudioContext 音频源
        if (this.currentAudioSource) {
            try {
                this.currentAudioSource.stop();
                this.currentAudioSource.disconnect();
            } catch (e) {
                // 忽略错误
            }
            this.currentAudioSource = null;
        }
        
        // 停止 HTML5 Audio
        if (this.currentHtmlAudio) {
            try {
                this.currentHtmlAudio.pause();
                this.currentHtmlAudio.currentTime = 0;
            } catch (e) {
                // 忽略错误
            }
            this.currentHtmlAudio = null;
        }
    }
    
    /**
     * 停止所有音频
     */
    stopAllAudio() {
        // 停止当前正在播放的音频
        this.stopCurrentAudio();
        
        // 停止所有可能的音频元素
        const audioElements = document.querySelectorAll('audio');
        audioElements.forEach(audio => {
            try {
                audio.pause();
                audio.currentTime = 0;
            } catch (e) {
                // 忽略错误
            }
        });
        
        // 清理 audioMessages 中的音频元素
        this.audioMessages.forEach((data) => {
            if (data.audioElement) {
                try {
                    data.audioElement.pause();
                    data.audioElement.currentTime = 0;
                } catch (e) {
                    // 忽略错误
                }
            }
        });
        
        // 重置播放状态
        this.currentPlayingVoice = null;
        this.isPlaying = false;
        
        Utils.log('All audio stopped');
    }
    
    /**
     * 切换语音播放/暂停
     * @param {string} messageId - 消息ID
     */
    toggleVoicePlay(messageId) {
        this.stopAllAudio();
        
        const voiceData = this.audioMessages.get(messageId);
        if (!voiceData) {
            Utils.warn('Voice data not found for message:', messageId);
            return;
        }
        
        if (this.currentPlayingVoice === messageId) {
            // 如果正在播放这条语音，则停止
            this.stopCurrentAudio();
            this.currentPlayingVoice = null;
        } else {
            // 播放这条语音
            if (voiceData.audio) {
                this.playAudioBase64(voiceData.audio, messageId);
            }
        }
    }
    
    /**
     * 添加语音消息到队列
     * @param {string} messageId - 消息ID
     * @param {string} audioBase64 - Base64编码的音频数据
     */
    addVoiceMessage(messageId, audioBase64) {
        this.audioMessages.set(messageId, {
            audio: audioBase64,
            audioElement: null
        });
        
        // 如果没有正在播放的语音，添加到未播放队列
        if (!this.currentPlayingVoice) {
            this.unplayedVoices.push(messageId);
        } else {
            this.unplayedVoices.push(messageId);
        }
        
        Utils.log('Voice message added to queue:', messageId);
    }
    
    /**
     * 清理资源
     */
    cleanup() {
        this.stopAllAudio();
        
        if (this.audioContext) {
            this.audioContext.close();
        }
        
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        
        this.audioMessages.clear();
        this.unplayedVoices = [];
        
        Utils.log('AudioManager cleaned up');
    }
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AudioManager;
}

if (typeof window !== 'undefined') {
    window.AudioManager = AudioManager;
}

