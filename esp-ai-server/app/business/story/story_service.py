"""
睡前故事服务
Bedtime Story Service
不同角色讲述不同风格的睡前故事
"""

import random
from typing import Dict, List, Optional

from app.core import logger
from app.shared.services import get_llm_service


class StoryService:
    """睡前故事服务"""
    
    # 故事主题配置（对应UI界面的主题选择）
    STORY_THEMES = {
        "智慧的寓言": {
            "description": "富有哲理的小故事，启发思考",
            "keywords": ["智慧", "寓言", "哲理", "启发", "思考"],
            "suitable_characters": ["xiaozhi", "xiaonuan"]
        },
        "思考的旅程": {
            "description": "引导深入思考的成长故事",
            "keywords": ["成长", "思考", "旅程", "探索", "发现"],
            "suitable_characters": ["xiaozhi", "xiaocheng"]
        },
        "古老的传说": {
            "description": "神秘而富有文化底蕴的传说故事",
            "keywords": ["传说", "神话", "古老", "文化", "神秘"],
            "suitable_characters": ["xiaozhi", "xiaoshu"]
        },
        "哲理的故事": {
            "description": "蕴含人生道理的温暖故事",
            "keywords": ["哲理", "人生", "道理", "温暖", "感悟"],
            "suitable_characters": ["xiaozhi", "xiaonuan"]
        },
        "成长的启示": {
            "description": "关于成长和自我发现的故事",
            "keywords": ["成长", "启示", "自我", "发现", "勇气"],
            "suitable_characters": ["xiaocheng", "xiaonuan"]
        }
    }
    
    # 角色风格配置
    CHARACTER_STYLES = {
        "xiaonuan": {
            "name": "小暖",
            "style": "温柔、治愈、充满温暖和希望的故事",
            "tone": "温和亲切，像姐姐一样关怀"
        },
        "xiaocheng": {
            "name": "小橙", 
            "style": "轻松、有趣、充满正能量和惊喜的故事",
            "tone": "活泼开朗，充满活力和好奇心"
        },
        "xiaozhi": {
            "name": "小智",
            "style": "富有哲理、引人思考、启发智慧的故事", 
            "tone": "睿智沉稳，善于启发和引导"
        },
        "xiaoshu": {
            "name": "小树",
            "style": "平静、简洁、让人放松和安心的故事",
            "tone": "宁静平和，如大自然般包容"
        }
    }
    
    # 预设的故事库（每个角色一些经典故事）
    PRESET_STORIES = {
        "xiaonuan": [
            {
                "title": "小星星的愿望",
                "content": """很久以前，天上有一颗小星星，它总是静静地看着地球上的人们。\n\n小星星有一个愿望，它想让每个人都能在夜晚看到它的光芒，感受到温暖和希望。\n\n于是，小星星每晚都努力地闪烁着，即使是在最黑暗的夜晚。\n\n渐渐地，人们发现了这颗特别的星星，他们会在夜晚抬头寻找它，向它许愿。\n\n小星星虽然不能实现所有的愿望，但它用自己的光芒告诉人们：无论多么黑暗，总有光明在守候着你。\n\n就像这颗小星星一样，你的心中也有一份温暖的光，它会陪伴你度过每一个夜晚。\n\n现在，让我们一起闭上眼睛，感受那份温暖，慢慢进入甜美的梦乡吧。💫\n\n晚安，好梦。"""
            },
            {
                "title": "温暖的森林",
                "content": """在一片神奇的森林里，住着许多可爱的小动物。\n\n每当夜晚降临，月亮婆婆就会讲述一个温暖的故事。\n\n小兔子、小松鼠、小刺猬都会围坐在大橡树下，静静地倾听。\n\n月亮婆婆说："每个生命都有自己的光芒，即使是最小的萤火虫，也能照亮黑暗的夜晚。"\n\n小动物们听着故事，感受着森林的温暖，慢慢地进入了梦乡。\n\n在梦里，它们梦见了更美好的明天，梦见了彼此的微笑。\n\n现在，让我们也像森林里的小动物一样，带着温暖和期待，进入美好的梦境吧。🌙\n\n晚安，愿你有个温暖的梦。"""
            }
        ],
        "xiaocheng": [
            {
                "title": "云朵的冒险",
                "content": """有一朵特别活泼的小云朵，它总是喜欢到处飘荡，看看世界各地的风景。\n\n今天，小云朵决定来一次大冒险！它飘过高山，越过海洋，遇见了许多新朋友。\n\n"你好呀！"小云朵向太阳打招呼。\n"你好！"太阳微笑着说，"你看起来很开心呢！"\n\n小云朵继续飘啊飘，它看到了彩虹，听到了小鸟的歌声，感受到了微风的拥抱。\n\n傍晚时分，小云朵累了，它慢慢地变成了各种各样有趣的形状——有时像棉花糖，有时像小兔子。\n\n最后，小云朵带着满满的快乐，在夕阳的怀抱中休息了。\n\n你也可以像小云朵一样，带着今天的快乐，在梦里继续冒险哦！✨\n\n晚安，明天见！愿你的梦里充满快乐的冒险！"""
            }
        ],
        "xiaozhi": [
            {
                "title": "种子的智慧",
                "content": """从前有一颗小种子，它被埋在了土壤深处。\n\n周围很黑，小种子有些害怕，它问大地："我什么时候能看到光明？"\n\n大地温柔地说："耐心等待，积蓄力量，时机到了，你就会破土而出。"\n\n小种子虽然看不见外面的世界，但它相信大地的话，于是它静静地等待，慢慢地成长。\n\n终于有一天，小种子感受到了温暖的阳光，它发现自己已经长出了嫩芽。\n\n它明白了：有时候，沉默和等待并不是停滞，而是在为更好的自己做准备。\n\n就像这颗种子一样，你现在的每一个夜晚，都是在为明天的成长积蓄能量。\n\n现在，让我们安静地休息，在沉睡中继续成长吧。🌱\n\n晚安，愿你在梦中获得智慧。"""
            }
        ],
        "xiaoshu": [
            {
                "title": "宁静的夜",
                "content": """夜深了，整个世界都安静下来。\n\n树叶停止了舞动，小鸟回到了巢中，连风也变得轻柔。\n\n在这宁静的时刻，一切都是那么平和。\n\n没有白天的喧嚣，没有纷扰的思绪，只有这一刻的安宁。\n\n大树静静地站立，它见证了无数个这样的夜晚。\n\n它知道，每一个宁静的夜晚，都是对白天的温柔告别，也是对明天的静静期待。\n\n现在，让我们也成为这宁静的一部分。\n\n放下所有的念头，只是静静地呼吸，感受这一刻的平和。🌳\n\n晚安。"""
            }
        ]
    }
    
    def __init__(self, llm_service):
        """初始化服务
        
        Args:
            llm_service: 已配置好的 LLMService 实例
        """
        self.llm_service = llm_service
    
    def get_random_preset_story(self, character_id: str = "xiaonuan") -> Dict:
        """
        获取随机预设故事
        
        Args:
            character_id: 角色ID
        
        Returns:
            Dict: 故事内容
        """
        stories = self.PRESET_STORIES.get(character_id, self.PRESET_STORIES["xiaonuan"])
        story = random.choice(stories)
        
        return {
            "title": story["title"],
            "content": story["content"],
            "character_id": character_id,
            "type": "preset"
        }
    
    def generate_bedtime_story(self, user_id: str, story_type: str = "preset") -> Dict:
        """
        生成睡前故事（同步方法，兼容现有处理器）
        
        Args:
            user_id: 用户ID
            story_type: 故事类型 ("preset" 或 "generated")
        
        Returns:
            Dict: 故事内容
        """
        if story_type == "preset":
            # 返回预设故事
            return self.get_random_preset_story("xiaonuan")  # 默认使用小暖角色
        else:
            # 对于生成类型，返回预设故事作为降级处理
            logger.info("故事生成模式降级为预设故事")
            return self.get_random_preset_story("xiaonuan")
    
    async def generate_story_async(
        self,
        character_id: str = "xiaonuan",
        theme: str = None,
        user_name: str = None
    ) -> Optional[Dict]:
        """
        异步生成睡前故事
        
        Args:
            character_id: 角色ID
            theme: 故事主题（可选，不指定则随机选择）
            user_name: 用户昵称（可选，用于个性化）
        
        Returns:
            Optional[Dict]: 生成的故事
        """
        # 获取角色的故事风格
        character_info = self.CHARACTER_STYLES.get(character_id, self.CHARACTER_STYLES["xiaonuan"])
        
        # 如果没有指定主题，随机选择一个
        if not theme:
            theme = random.choice(list(self.STORY_THEMES.keys()))
        
        logger.info(f"开始生成 {character_id} 角色的睡前故事，主题：{theme}")
        
        # 构建提示词
        prompt = f"""请创作一个适合青少年的睡前故事。

角色：{character_id}
主题：{theme}
风格：{character_info['style']}

要求：
1. 故事长度：300-500字
2. 语言温和、平静，适合入睡前阅读
3. 内容积极向上，有治愈感
4. 可以包含一些生活哲理，但不要说教
5. 结尾要给人安心、放松的感觉
6. 使用第三人称叙述
7. 适当使用分段，让阅读更舒适
8. 最后用温柔的话语引导入睡

"""

        if user_name:
            prompt += f"\n提示：可以在故事中提到用户的名字「{user_name}」，让故事更有代入感。\n"
        
        prompt += "\n请开始创作故事："
        
        try:
            # 调用LLM
            messages = [
                {"role": "system", "content": f"你是{character_id}，正在为青少年讲述睡前故事。你的故事{character_info['style']}。"},
                {"role": "user", "content": prompt}
            ]
            
            story_content = await self.llm_service.chat_async(messages, temperature=0.9)
            
            return {
                "title": theme,
                "content": story_content,
                "character_id": character_id,
                "type": "generated",
                "theme": theme
            }
            
        except Exception as e:
            logger.error(f"生成睡前故事失败: {e}", exc_info=True)
            # 降级：返回None，让上层处理
            logger.info("故事生成模式降级为预设故事")
            return None
    
    def get_available_themes(self) -> List[Dict]:
        """
        获取可用的故事主题列表（对应UI界面）
        
        Returns:
            List[Dict]: 主题列表，包含主题名称和描述
        """
        themes = []
        for theme_name, theme_info in self.STORY_THEMES.items():
            themes.append({
                "name": theme_name,
                "description": theme_info["description"],
                "suitable_characters": theme_info["suitable_characters"]
            })
        return themes
    
    def get_story_types(self) -> List[Dict]:
        """
        获取故事类型选项（对应UI界面）
        
        Returns:
            List[Dict]: 故事类型列表
        """
        return [
            {
                "type": "preset",
                "name": "精选故事",
                "description": "精心挑选的经典睡前故事",
                "icon": "📚"
            },
            {
                "type": "generated", 
                "name": "创作新故事",
                "description": "根据你的喜好创作全新故事",
                "icon": "✨"
            }
        ]
    
    def get_story_by_mood(
        self,
        character_id: str,
        mood: str
    ) -> Dict:
        """
        根据当前情绪推荐故事主题
        
        Args:
            character_id: 角色ID
            mood: 当前情绪 (happy, sad, anxious, tired, etc.)
        
        Returns:
            Dict: 推荐的故事信息
        """
        # 根据情绪推荐合适的主题
        mood_to_theme = {
            "happy": "快乐的小伙伴",
            "excited": "冒险旅程",
            "calm": "宁静的夜",
            "sad": "温暖的友谊",
            "anxious": "安静的夜晚",
            "tired": "大自然的声音",
            "angry": "平和的日常",
            "confused": "智慧的寓言"
        }
        
        recommended_theme = mood_to_theme.get(mood, "星星的故事")
        
        return {
            "recommended_theme": recommended_theme,
            "reason": self._get_recommendation_reason(mood),
            "character_id": character_id
        }
    
    def _get_recommendation_reason(self, mood: str) -> str:
        """获取推荐理由"""
        reasons = {
            "happy": "你现在心情不错，来听个轻松愉快的故事吧！",
            "excited": "你现在很兴奋呢，让我们一起经历一场冒险吧！",
            "calm": "你现在很平静，适合听一个宁静的故事。",
            "sad": "感觉你有点难过，来听个温暖的故事吧，会让你感觉好一些的。",
            "anxious": "感觉你有些焦虑，让我给你讲个能让人放松的故事吧。",
            "tired": "你看起来累了，来听听大自然的声音，放松一下吧。",
            "angry": "深呼吸，让我给你讲个平和的故事，帮你平静下来。",
            "confused": "感觉有些迷茫吗？也许这个故事能给你一些启发。"
        }
        return reasons.get(mood, "让我给你讲个故事吧~")
    
    async def get_bedtime_story(
        self,
        user_id: str,
        character_id: str = "xiaonuan",
        story_type: str = "preset",
        theme: str = None,
        user_name: str = None
    ) -> Dict:
        """
        获取睡前故事（主要接口方法）
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            story_type: 故事类型 ("preset" 或 "generated")
            theme: 故事主题（可选）
            user_name: 用户昵称（可选）
        
        Returns:
            Dict: 完整的故事数据
        """
        logger.info(f"用户 {user_id} 请求睡前故事: 角色={character_id}, 类型={story_type}, 主题={theme}")
        
        try:
            if story_type == "preset":
                # 获取精选故事
                story = self.get_random_preset_story(character_id)
            else:
                # 生成新故事
                story = await self.generate_story_async(character_id, theme, user_name)
                if not story:
                    # 生成失败，降级为预设故事
                    story = self.get_random_preset_story(character_id)
            
            # 添加角色信息
            character_info = self.CHARACTER_STYLES.get(character_id, self.CHARACTER_STYLES["xiaonuan"])
            story["character_name"] = character_info["name"]
            story["character_style"] = character_info["style"]
            
            # 添加时间戳
            from datetime import datetime
            story["created_at"] = datetime.now().isoformat()
            story["user_id"] = user_id
            
            logger.info(f"成功生成睡前故事: {story['title']}")
            return story
            
        except Exception as e:
            logger.error(f"获取睡前故事失败: {e}")
            # 最终降级方案
            return self.get_random_preset_story(character_id)
    
    def get_story_recommendation(self, character_id: str, mood: str = None) -> Dict:
        """
        获取故事推荐（智能推荐功能）
        
        Args:
            character_id: 角色ID
            mood: 用户当前情绪（可选）
        
        Returns:
            Dict: 推荐信息
        """
        if mood:
            # 基于情绪推荐
            mood_recommendations = {
                "happy": ["成长的启示", "思考的旅程"],
                "sad": ["哲理的故事", "智慧的寓言"], 
                "anxious": ["古老的传说", "哲理的故事"],
                "tired": ["智慧的寓言", "哲理的故事"],
                "excited": ["思考的旅程", "成长的启示"],
                "calm": ["古老的传说", "智慧的寓言"]
            }
            
            recommended_themes = mood_recommendations.get(mood, ["智慧的寓言"])
            recommended_theme = random.choice(recommended_themes)
        else:
            # 随机推荐
            recommended_theme = random.choice(list(self.STORY_THEMES.keys()))
        
        theme_info = self.STORY_THEMES[recommended_theme]
        character_info = self.CHARACTER_STYLES.get(character_id, self.CHARACTER_STYLES["xiaonuan"])
        
        return {
            "recommended_theme": recommended_theme,
            "theme_description": theme_info["description"],
            "character_name": character_info["name"],
            "reason": self._get_recommendation_reason(mood) if mood else f"推荐你听{character_info['name']}讲的{recommended_theme}",
            "suitable_story_type": "generated" if character_id in theme_info["suitable_characters"] else "preset"
        }


# 全局单例
_story_service = None


def get_story_service() -> StoryService:
    """获取故事服务单例"""
    global _story_service
    if _story_service is None:
        # 使用全局 LLM 服务实例构造 StoryService
        llm_service = get_llm_service()
        _story_service = StoryService(llm_service)
    return _story_service

