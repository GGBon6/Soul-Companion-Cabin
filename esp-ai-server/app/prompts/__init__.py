"""
提示词管理模块
Prompts Management Module
"""

from .system_prompts import get_system_prompt, get_initial_greeting
from .knowledge_base import get_relevant_knowledge

__all__ = [
    "get_system_prompt",
    "get_initial_greeting",
    "get_relevant_knowledge",
]

