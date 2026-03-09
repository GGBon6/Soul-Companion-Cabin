"""
日记生成服务
Diary Generation Service
根据对话内容和情绪记录自动生成日记
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

from app.core import settings, logger


class DiaryEntry:
    """日记条目"""
    
    def __init__(
        self,
        user_id: str,
        date: str,
        title: str,
        content: str,
        mood: str,
        mood_emoji: str,
        highlights: List[str],
        generated_at: str,
        character_id: str = "xiaonuan"
    ):
        """
        初始化日记条目
        
        Args:
            user_id: 用户ID
            date: 日期 (YYYY-MM-DD)
            title: 标题
            content: 正文内容
            mood: 主要情绪
            mood_emoji: 情绪表情符号
            highlights: 当日亮点/关键词
            generated_at: 生成时间
            character_id: 生成日记时使用的角色ID
        """
        self.user_id = user_id
        self.date = date
        self.title = title
        self.content = content
        self.mood = mood
        self.mood_emoji = mood_emoji
        self.highlights = highlights
        self.generated_at = generated_at
        self.character_id = character_id
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "date": self.date,
            "title": self.title,
            "content": self.content,
            "mood": self.mood,
            "mood_emoji": self.mood_emoji,
            "highlights": self.highlights,
            "generated_at": self.generated_at,
            "character_id": self.character_id
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DiaryEntry":
        """从字典创建"""
        return cls(
            user_id=data["user_id"],
            date=data["date"],
            title=data["title"],
            content=data["content"],
            mood=data["mood"],
            mood_emoji=data["mood_emoji"],
            highlights=data.get("highlights", []),
            generated_at=data["generated_at"],
            character_id=data.get("character_id", "xiaonuan")
        )


class DiaryService:
    """日记生成服务"""
    
    def __init__(self, llm_service, mood_service, history_service):
        """初始化服务
        
        Args:
            llm_service: 已配置好的 LLMService 实例
            mood_service: 情绪记录服务实例
            history_service: 对话历史服务实例
        """
        self.data_dir = Path(settings.BASE_DIR) / "data" / "diaries"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.llm_service = llm_service
        self.mood_service = mood_service
        self.history_service = history_service
    
    def _get_diary_file_path(self, user_id: str) -> Path:
        """获取用户日记文件路径"""
        return self.data_dir / f"{user_id}_diaries.json"
    
    def _load_diaries(self, user_id: str) -> List[DiaryEntry]:
        """
        加载用户的日记
        
        Args:
            user_id: 用户ID
        
        Returns:
            List[DiaryEntry]: 日记列表
        """
        file_path = self._get_diary_file_path(user_id)
        
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [DiaryEntry.from_dict(entry) for entry in data]
        except Exception as e:
            logger.error(f"加载日记失败: {e}")
            return []
    
    def _save_diaries(self, user_id: str, diaries: List[DiaryEntry]):
        """
        保存用户的日记
        
        Args:
            user_id: 用户ID
            diaries: 日记列表
        """
        file_path = self._get_diary_file_path(user_id)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                data = [diary.to_dict() for diary in diaries]
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存日记失败: {e}")
    
    async def generate_diary_async(
        self,
        user_id: str,
        date: str = None,
        character_id: str = "xiaonuan"
    ) -> Optional[DiaryEntry]:
        """
        异步生成指定日期的日记
        
        Args:
            user_id: 用户ID
            date: 日期 (YYYY-MM-DD)，默认为今天
            character_id: 角色ID
        
        Returns:
            Optional[DiaryEntry]: 生成的日记，如果没有对话内容则返回None
        """
        # 默认为今天
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"开始为用户 {user_id} 生成 {date} 的日记...")
        
        # 获取当天的对话记录
        try:
            # 使用适配器的方法获取历史记录
            messages = self.history_service.get_history_by_date_range(user_id, date, date)
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return None
        
        if not messages:
            logger.info(f"用户 {user_id} 在 {date} 没有对话记录")
            return None
        
        # 过滤出用户的消息（不包括系统消息）
        user_messages = [msg for msg in messages if msg.role == "user"]
        assistant_messages = [msg for msg in messages if msg.role == "assistant"]
        
        if not user_messages:
            logger.info(f"用户 {user_id} 在 {date} 没有有效的对话内容")
            return None
        
        # 获取当天的情绪记录
        mood_history = self.mood_service.get_mood_history(user_id, days=1)
        today_moods = [m for m in mood_history if m["timestamp"].startswith(date)]
        
        # 确定主要情绪
        if today_moods:
            # 使用最新的情绪记录
            main_mood = today_moods[-1]
        else:
            # 默认情绪
            main_mood = {
                "mood": "calm",
                "emoji": "😌",
                "name": "平静"
            }
        
        # 构建对话摘要
        conversation_summary = self._build_conversation_summary(user_messages, assistant_messages)
        
        # 使用LLM生成日记
        diary_content = await self._generate_diary_content_with_llm(
            date=date,
            conversation_summary=conversation_summary,
            mood=main_mood,
            character_id=character_id
        )
        
        if not diary_content:
            logger.error("日记内容生成失败")
            return None
        
        # 提取关键词/亮点
        highlights = self._extract_highlights(user_messages)
        
        # 创建日记条目
        diary_entry = DiaryEntry(
            user_id=user_id,
            date=date,
            title=diary_content.get("title", f"{date}的记录"),
            content=diary_content.get("content", ""),
            mood=main_mood["mood"],
            mood_emoji=main_mood["emoji"],
            highlights=highlights,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            character_id=character_id
        )
        
        # 保存日记
        diaries = self._load_diaries(user_id)
        
        # 检查是否已存在该日期的日记，如果有则替换
        diaries = [d for d in diaries if d.date != date]
        diaries.append(diary_entry)
        
        # 按日期排序
        diaries.sort(key=lambda x: x.date, reverse=True)
        
        self._save_diaries(user_id, diaries)
        
        logger.info(f"✅ 成功为用户 {user_id} 生成 {date} 的日记")
        
        return diary_entry
    
    def generate_diary(self, user_id: str, date: str = None) -> Optional[Dict]:
        """
        生成日记（同步方法，兼容现有处理器）
        
        Args:
            user_id: 用户ID
            date: 日期 (YYYY-MM-DD)，默认为今天
        
        Returns:
            Optional[Dict]: 生成的日记数据，如果失败则返回None
        """
        try:
            # 检查是否已有事件循环在运行
            import asyncio
            try:
                # 尝试获取当前事件循环
                loop = asyncio.get_running_loop()
                # 如果有运行中的循环，创建任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._sync_generate_diary, user_id, date)
                    return future.result(timeout=30)  # 30秒超时
            except RuntimeError:
                # 没有运行中的循环，创建新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    diary_entry = loop.run_until_complete(
                        self.generate_diary_async(user_id, date)
                    )
                    if diary_entry:
                        return diary_entry.to_dict()
                    return None
                finally:
                    loop.close()
        except Exception as e:
            logger.error(f"同步生成日记失败: {e}")
            return None
    
    def _sync_generate_diary(self, user_id: str, date: str = None) -> Optional[Dict]:
        """在新线程中同步生成日记"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            diary_entry = loop.run_until_complete(
                self.generate_diary_async(user_id, date)
            )
            if diary_entry:
                return diary_entry.to_dict()
            return None
        finally:
            loop.close()
    
    def _build_conversation_summary(
        self,
        user_messages: List,
        assistant_messages: List
    ) -> str:
        """
        构建对话摘要
        
        Args:
            user_messages: 用户消息列表
            assistant_messages: 助手消息列表
        
        Returns:
            str: 对话摘要文本
        """
        summary_parts = []
        
        # 提取用户说的话（前10条）
        user_contents = [msg.content for msg in user_messages[:10]]
        summary_parts.append("用户说了：" + "；".join(user_contents))
        
        # 提取助手的回复（前10条）
        assistant_contents = [msg.content for msg in assistant_messages[:10]]
        summary_parts.append("回复内容：" + "；".join(assistant_contents))
        
        return "\n".join(summary_parts)
    
    async def _generate_diary_content_with_llm(
        self,
        date: str,
        conversation_summary: str,
        mood: dict,
        character_id: str
    ) -> Optional[Dict]:
        """
        使用LLM生成日记内容
        
        Args:
            date: 日期
            conversation_summary: 对话摘要
            mood: 情绪信息
            character_id: 角色ID
        
        Returns:
            Optional[Dict]: 生成的日记内容 {"title": "标题", "content": "正文"}
        """
        # 根据角色调整日记风格
        character_styles = {
            "xiaonuan": "温暖、关怀的语气，像朋友在记录这一天",
            "xiaocheng": "积极、有活力的语气，发现生活中的美好",
            "xiaozhi": "理性、深度的语气，总结和思考",
            "xiaoshu": "简洁、包容的语气，客观记录"
        }
        
        style = character_styles.get(character_id, character_styles["xiaonuan"])
        
        # 构建提示词
        prompt = f"""请根据以下信息，为青少年用户生成一篇温馨的日记。

日期：{date}
主要情绪：{mood['name']} {mood['emoji']}

今天的对话内容摘要：
{conversation_summary}

要求：
1. 用第一人称（"我"）写日记，就像是用户自己在写
2. 语气：{style}
3. 不要说教，不要用"应该"、"必须"等词
4. 要包含情绪感受和具体事件
5. 长度：150-300字
6. 格式：返回JSON，包含title（标题，10字以内）和content（正文内容）

示例格式：
{{
    "title": "忙碌但充实的一天",
    "content": "今天过得挺充实的。早上起来心情还不错..."
}}

请生成日记："""

        try:
            # 调用LLM
            messages = [
                {"role": "system", "content": "你是一个善于总结和记录的助手，帮助青少年用户生成温馨的日记。"},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm_service.chat_async(messages, temperature=0.8)
            
            # 尝试解析JSON
            # 先清理可能的markdown代码块标记
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            diary_data = json.loads(response)
            
            return diary_data
            
        except json.JSONDecodeError:
            logger.error(f"解析日记JSON失败: {response}")
            # 降级处理：如果解析失败，使用简单的格式
            return {
                "title": f"{date}的记录",
                "content": response[:500]  # 截取前500字符
            }
        except Exception as e:
            logger.error(f"生成日记内容失败: {e}")
            return None
    
    def _extract_highlights(self, user_messages: List) -> List[str]:
        """
        提取对话亮点/关键词
        
        Args:
            user_messages: 用户消息列表
        
        Returns:
            List[str]: 关键词列表
        """
        # 简单的关键词提取（可以后续使用更复杂的NLP方法）
        keywords = []
        
        # 常见的有意义的词
        meaningful_words = set()
        
        for msg in user_messages:
            words = msg.content.split()
            for word in words:
                # 过滤短词和常见词
                if len(word) >= 2 and word not in ['今天', '昨天', '明天', '然后', '但是', '所以']:
                    meaningful_words.add(word)
        
        # 取前5个
        keywords = list(meaningful_words)[:5]
        
        return keywords
    
    def get_diary(
        self,
        user_id: str,
        date: str
    ) -> Optional[DiaryEntry]:
        """
        获取指定日期的日记
        
        Args:
            user_id: 用户ID
            date: 日期 (YYYY-MM-DD)
        
        Returns:
            Optional[DiaryEntry]: 日记条目，不存在则返回None
        """
        diaries = self._load_diaries(user_id)
        
        for diary in diaries:
            if diary.date == date:
                return diary
        
        return None
    
    def get_diary_list(
        self,
        user_id: str,
        limit: int = 30
    ) -> List[Dict]:
        """
        获取日记列表
        
        Args:
            user_id: 用户ID
            limit: 返回数量限制
        
        Returns:
            List[Dict]: 日记列表
        """
        diaries = self._load_diaries(user_id)
        
        # 按日期倒序排列
        diaries.sort(key=lambda x: x.date, reverse=True)
        
        # 限制数量
        diaries = diaries[:limit]
        
        return [diary.to_dict() for diary in diaries]
    
    def delete_diary(
        self,
        user_id: str,
        date: str
    ) -> bool:
        """
        删除指定日期的日记
        
        Args:
            user_id: 用户ID
            date: 日期 (YYYY-MM-DD)
        
        Returns:
            bool: 是否删除成功
        """
        diaries = self._load_diaries(user_id)
        
        # 过滤掉指定日期的日记
        original_count = len(diaries)
        diaries = [d for d in diaries if d.date != date]
        
        if len(diaries) < original_count:
            self._save_diaries(user_id, diaries)
            logger.info(f"用户 {user_id} 删除了 {date} 的日记")
            return True
        
        return False
    
    def get_diary_calendar(
        self,
        user_id: str,
        year: int = None,
        month: int = None
    ) -> Dict:
        """
        获取日记日历（某个月有日记的日期）
        
        Args:
            user_id: 用户ID
            year: 年份（默认当前年）
            month: 月份（默认当前月）
        
        Returns:
            Dict: 日历数据
        """
        now = datetime.now()
        year = year or now.year
        month = month or now.month
        
        diaries = self._load_diaries(user_id)
        
        # 过滤指定月份的日记
        calendar_data = {}
        for diary in diaries:
            diary_date = datetime.strptime(diary.date, "%Y-%m-%d")
            if diary_date.year == year and diary_date.month == month:
                calendar_data[diary.date] = {
                    "date": diary.date,
                    "title": diary.title,
                    "mood_emoji": diary.mood_emoji,
                    "has_diary": True
                }
        
        return {
            "year": year,
            "month": month,
            "data": calendar_data
        }


_diary_service = None


def get_diary_service() -> DiaryService:
    """获取日记服务单例（向后兼容工厂）"""
    global _diary_service
    if _diary_service is None:
        # 仍然使用原有的全局getter组装依赖，保证旧代码可以工作
        from app.shared.services.llm_service import get_llm_service
        from app.shared.agents.adapters.mood_adapter import get_mood_service
        from app.shared.agents.adapters.history_adapter import get_history_service

        llm_service = get_llm_service()
        mood_service = get_mood_service()
        history_service = get_history_service()

        _diary_service = DiaryService(
            llm_service=llm_service,
            mood_service=mood_service,
            history_service=history_service,
        )
    return _diary_service

