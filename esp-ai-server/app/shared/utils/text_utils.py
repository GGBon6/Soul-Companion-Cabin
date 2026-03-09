"""
通用工具函数
Helper Functions
"""

from datetime import datetime
from typing import List
import re


def format_timestamp(timestamp: str = None) -> str:
    """
    格式化时间戳
    
    Args:
        timestamp: 时间戳字符串，如果为None则使用当前时间
    
    Returns:
        str: 格式化后的时间字符串
    """
    if timestamp is None:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return timestamp


def split_text_by_sentence(text: str, max_length: int = 100) -> List[str]:
    """
    按句子分割文本
    
    Args:
        text: 待分割的文本
        max_length: 每个片段的最大长度
    
    Returns:
        List[str]: 分割后的句子列表
    """
    # 中文句子分隔符
    sentences = re.split(r'([。！？\n])', text)
    
    results = []
    current = ""
    
    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        delimiter = sentences[i + 1] if i + 1 < len(sentences) else ""
        full_sentence = sentence + delimiter
        
        if len(current) + len(full_sentence) > max_length and current:
            results.append(current.strip())
            current = full_sentence
        else:
            current += full_sentence
    
    if current:
        results.append(current.strip())
    
    return results


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    截断文本
    
    Args:
        text: 待截断的文本
        max_length: 最大长度
        suffix: 后缀
    
    Returns:
        str: 截断后的文本
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def clean_text(text: str) -> str:
    """
    清理文本
    
    Args:
        text: 待清理的文本
    
    Returns:
        str: 清理后的文本
    """
    # 移除多余空格
    text = re.sub(r'\s+', ' ', text)
    # 去除首尾空格
    text = text.strip()
    return text

