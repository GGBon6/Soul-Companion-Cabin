"""
LLM配置数据类
LLM Configuration Dataclass
支持多客户端类型的独立配置
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class LLMConfig:
    """
    LLM服务配置
    
    支持为不同客户端类型（ESP32、Web、System）配置不同的参数
    """
    # API配置
    api_key: str
    
    # 模型配置
    model: str = "qwen-plus"
    max_tokens: int = 2000
    temperature: float = 0.8
    top_p: float = 0.9
    
    # 并发控制
    max_concurrent: int = 50
    
    # 缓存配置
    enable_cache: bool = True
    
    # 客户端标识
    client_type: str = "default"
    
    # 心理对话特殊配置
    enable_emotion_analysis: bool = True  # 启用情绪分析
    enable_risk_detection: bool = True    # 启用风险检测
    enable_memory: bool = True            # 启用记忆功能
    
    # 扩展配置
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """验证配置"""
        if not self.api_key:
            raise ValueError("api_key不能为空")
        
        if self.temperature < 0 or self.temperature > 2:
            raise ValueError("temperature必须在0-2之间")
        
        if self.max_tokens < 1:
            raise ValueError("max_tokens必须大于0")
    
    @classmethod
    def for_esp32(cls, api_key: str) -> 'LLMConfig':
        """
        创建ESP32设备优化配置
        
        特点：
        - 使用更快的模型（qwen-turbo）
        - 限制token数量，加快响应
        - 较低并发
        """
        return cls(
            api_key=api_key,
            model="qwen-turbo",
            max_tokens=500,
            temperature=0.7,
            max_concurrent=10,
            client_type="esp32",
            enable_cache=True,
            metadata={
                "description": "ESP32设备优化配置",
                "priority": "low_latency"
            }
        )
    
    @classmethod
    def for_web(cls, api_key: str) -> 'LLMConfig':
        """
        创建Web端优化配置
        
        特点：
        - 使用更智能的模型（qwen-plus）
        - 支持更长回复
        - 高并发支持
        """
        return cls(
            api_key=api_key,
            model="qwen-plus",
            max_tokens=2000,
            temperature=0.8,
            max_concurrent=30,
            client_type="web",
            enable_cache=True,
            metadata={
                "description": "Web端优化配置",
                "priority": "quality"
            }
        )
    
    @classmethod
    def for_system(cls, api_key: str) -> 'LLMConfig':
        """
        创建系统内部配置
        
        特点：
        - 平衡的模型选择
        - 中等并发
        - 用于后台任务（日记生成、故事生成等）
        """
        return cls(
            api_key=api_key,
            model="qwen-plus",
            max_tokens=1500,
            temperature=0.8,
            max_concurrent=5,
            client_type="system",
            enable_cache=True,
            metadata={
                "description": "系统内部配置",
                "priority": "balanced"
            }
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'model': self.model,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'top_p': self.top_p,
            'max_concurrent': self.max_concurrent,
            'enable_cache': self.enable_cache,
            'client_type': self.client_type,
            'enable_emotion_analysis': self.enable_emotion_analysis,
            'enable_risk_detection': self.enable_risk_detection,
            'enable_memory': self.enable_memory,
            'metadata': self.metadata
        }
