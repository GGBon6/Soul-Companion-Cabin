"""
知识库模块
Knowledge Base
存储和检索青少年心理健康相关的知识片段
"""

from .system_prompts import (
    TEEN_KNOWLEDGE_SNIPPETS, 
    TOMOE_KNOWLEDGE_SNIPPETS,  # 向后兼容
    get_relevant_knowledge
)


__all__ = [
    'TEEN_KNOWLEDGE_SNIPPETS',
    'TOMOE_KNOWLEDGE_SNIPPETS',  # 向后兼容
    'get_relevant_knowledge'
]
