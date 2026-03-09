"""
数据验证工具
Data Validators
"""

import re
from typing import Tuple


def validate_email(email: str) -> Tuple[bool, str]:
    """
    验证邮箱格式
    
    Args:
        email: 邮箱地址
    
    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not email:
        return False, "邮箱不能为空"
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "邮箱格式不正确"
    
    return True, ""


def validate_phone(phone: str) -> Tuple[bool, str]:
    """
    验证手机号格式（中国大陆）
    
    Args:
        phone: 手机号
    
    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not phone:
        return False, "手机号不能为空"
    
    pattern = r'^1[3-9]\d{9}$'
    if not re.match(pattern, phone):
        return False, "手机号格式不正确"
    
    return True, ""


def validate_text_length(text: str, min_length: int = 1, max_length: int = 10000) -> Tuple[bool, str]:
    """
    验证文本长度
    
    Args:
        text: 文本内容
        min_length: 最小长度
        max_length: 最大长度
    
    Returns:
        tuple: (是否有效, 错误信息)
    """
    if not text:
        return False, "内容不能为空"
    
    length = len(text)
    
    if length < min_length:
        return False, f"内容至少需要{min_length}个字符"
    
    if length > max_length:
        return False, f"内容不能超过{max_length}个字符"
    
    return True, ""

