"""
共享Agent模块
Shared Agents Module
包含Web和设备服务共用的Agent架构
"""

# 导入本地的Agent文件
from .memory_agent import get_memory_agent, MemoryAgent
from .chat_agent import PureChatAgent, ChatRequest, ChatResponse, AgentMode
from .web_chat_agent import WebChatAgent, WebChatRequest, WebChatResponse, get_web_chat_agent, TreeHoleMode

__all__ = [
    # 记忆Agent
    'get_memory_agent',
    'MemoryAgent',
    
    # 对话Agent
    'PureChatAgent',
    'ChatRequest', 
    'ChatResponse',
    'AgentMode',
    
    # 网页端对话Agent
    'WebChatAgent',
    'WebChatRequest',
    'WebChatResponse',
    'get_web_chat_agent',
    'TreeHoleMode'
]
