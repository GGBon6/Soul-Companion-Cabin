"""
音频缓存服务
Audio Cache Service
用于预生成和缓存固定文本的音频
"""

import os
import json
import base64
import hashlib
from pathlib import Path
from typing import Optional, Dict
from app.core import settings, logger
from app.shared.services.tts_service import get_tts_service, get_character_voice
from app.prompts.system_prompts import get_initial_greeting, get_all_characters


class AudioCacheService:
    """音频缓存服务"""
    
    def __init__(self):
        """初始化缓存服务"""
        self.tts_service = get_tts_service()
        
        # 缓存目录
        self.cache_dir = Path("backend/data/audio_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 缓存索引文件
        self.index_file = self.cache_dir / "cache_index.json"
        self.cache_index: Dict[str, str] = {}
        
        # 加载缓存索引
        self._load_cache_index()
        
        logger.info(f"🎵 音频缓存服务已初始化，缓存目录: {self.cache_dir}")
    
    def _load_cache_index(self):
        """加载缓存索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self.cache_index = json.load(f)
                logger.info(f"✅ 加载音频缓存索引: {len(self.cache_index)} 条")
            except Exception as e:
                logger.error(f"加载缓存索引失败: {e}")
                self.cache_index = {}
    
    def _save_cache_index(self):
        """保存缓存索引"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存索引失败: {e}")
    
    def _get_cache_key(self, text: str, voice: str) -> str:
        """生成缓存键"""
        content = f"{text}|{voice}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.mp3"
    
    def get_cached_audio(self, text: str, voice: str) -> Optional[str]:
        """
        获取缓存的音频（base64编码）
        
        Args:
            text: 文本内容
            voice: 语音名称
            
        Returns:
            Optional[str]: base64编码的音频数据，如果缓存不存在则返回None
        """
        cache_key = self._get_cache_key(text, voice)
        
        # 检查缓存是否存在
        if cache_key in self.cache_index:
            cache_path = self._get_cache_path(cache_key)
            if cache_path.exists():
                try:
                    with open(cache_path, 'rb') as f:
                        audio_data = f.read()
                    audio_base64 = base64.b64encode(audio_data).decode()
                    logger.debug(f"✅ 从缓存读取音频: {text[:30]}...")
                    return audio_base64
                except Exception as e:
                    logger.error(f"读取缓存音频失败: {e}")
        
        return None
    
    async def cache_audio(self, text: str, voice: str) -> Optional[str]:
        """
        生成并缓存音频
        
        Args:
            text: 文本内容
            voice: 语音名称
            
        Returns:
            Optional[str]: base64编码的音频数据，如果生成失败则返回None
        """
        cache_key = self._get_cache_key(text, voice)
        
        # 检查是否已缓存
        cached = self.get_cached_audio(text, voice)
        if cached:
            return cached
        
        try:
            logger.info(f"🎵 生成音频缓存: {text[:30]}... (voice: {voice})")
            
            # 清理文本用于TTS合成
            clean_text = self._clean_text_for_tts(text)
            logger.info(f"🎵 TTS清理后文本: {clean_text[:30]}...")
            
            # 生成音频
            audio_data = await self.tts_service.synthesize_async(clean_text, voice=voice)
            if not audio_data:
                logger.error("音频生成失败")
                return None
            
            # 保存到文件
            cache_path = self._get_cache_path(cache_key)
            with open(cache_path, 'wb') as f:
                f.write(audio_data)
            
            # 更新索引
            self.cache_index[cache_key] = {
                "text": text[:50],  # 只保存前50个字符用于调试
                "voice": voice,
                "file": cache_path.name
            }
            self._save_cache_index()
            
            # 返回base64编码
            audio_base64 = base64.b64encode(audio_data).decode()
            logger.info(f"✅ 音频缓存生成成功: {cache_key}")
            return audio_base64
            
        except Exception as e:
            logger.error(f"生成音频缓存失败: {e}", exc_info=True)
            return None
    
    async def pregenerate_greetings(self):
        """预生成所有角色的固定问候语音频"""
        logger.info("🎬 开始预生成角色问候语音频缓存...")
        
        characters = get_all_characters()
        success_count = 0
        
        for character in characters:
            character_id = character['id']
            character_name = character['name']
            
            try:
                # 获取该角色的问候语
                greeting = get_initial_greeting(character_id)
                
                # 获取该角色的声音
                voice = get_character_voice(character_id)
                
                # 生成并缓存音频
                audio_base64 = await self.cache_audio(greeting, voice)
                
                if audio_base64:
                    success_count += 1
                    logger.info(f"✅ {character_name} 的问候语音频已缓存")
                else:
                    logger.warning(f"⚠️ {character_name} 的问候语音频生成失败")
                    
            except Exception as e:
                logger.error(f"❌ 预生成 {character_name} 的问候语音频失败: {e}")
        
        logger.info(f"🎉 问候语音频预生成完成: {success_count}/{len(characters)} 个角色")
        return success_count, len(characters)
    
    def clear_cache(self):
        """清除所有缓存"""
        try:
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_index = {}
            self._save_cache_index()
            logger.info("🗑️ 音频缓存已清除")
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
    
    def _clean_text_for_tts(self, text: str) -> str:
        """
        清理文本用于TTS合成，移除表情符号和特殊字符
        
        Args:
            text: 原始文本
            
        Returns:
            str: 清理后的文本
        """
        import re
        
        # 更精确的表情符号正则表达式
        emoji_pattern = re.compile(
            r'[\U0001F600-\U0001F64F]|'  # emoticons
            r'[\U0001F300-\U0001F5FF]|'  # symbols & pictographs
            r'[\U0001F680-\U0001F6FF]|'  # transport & map symbols
            r'[\U0001F1E0-\U0001F1FF]|'  # flags (iOS)
            r'[\U00002702-\U000027B0]|'  # dingbats
            r'[\U0001F900-\U0001F9FF]|'  # supplemental symbols
            r'[\U0001FA70-\U0001FAFF]',   # symbols and pictographs extended-a
            flags=re.UNICODE
        )
        
        # 移除表情符号
        clean_text = emoji_pattern.sub('', text)
        
        # 移除多余的空格和换行符
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # 如果清理后文本为空，返回原文本（避免完全无声）
        if not clean_text.strip():
            return text
            
        return clean_text


# 全局单例
_audio_cache_service = None

def get_audio_cache_service() -> AudioCacheService:
    """获取音频缓存服务单例"""
    global _audio_cache_service
    if _audio_cache_service is None:
        _audio_cache_service = AudioCacheService()
    return _audio_cache_service

