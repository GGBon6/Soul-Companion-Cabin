"""
Agent配置管理器
- 加载和管理Agent相关配置
- 提供配置热更新功能
- 支持环境变量覆盖
"""

import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
from app.core import logger


class AgentConfig:
    """Agent配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认为项目根目录下的config/agent_config.yaml
        """
        if config_path is None:
            # 默认配置文件路径
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "agent_config.yaml"
        
        self.config_path = Path(config_path)
        self._config_data: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config_data = yaml.safe_load(f) or {}
                logger.info(f"✅ 加载Agent配置文件: {self.config_path}")
            else:
                logger.warning(f"⚠️ Agent配置文件不存在: {self.config_path}，使用默认配置")
                self._config_data = self._get_default_config()
        except Exception as e:
            logger.error(f"❌ 加载Agent配置文件失败: {e}，使用默认配置")
            self._config_data = self._get_default_config()
        
        # 应用环境变量覆盖
        self._apply_env_overrides()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "chat_agent": {
                "enabled": True,
                "max_context_messages": 10,
                "max_user_input_length": 2000,
                "default_timeout_s": 15.0,
                "max_concurrency": 3
            },
            "memory_system": {
                "enable_memory_recall": True,
                "enable_memory_write": True
            },
            "emotion_analysis": {
                "enabled": True,
                "emotion_threshold": 0.5
            },
            "risk_detection": {
                "enabled": True
            },
            "knowledge_injection": {
                "enabled": True
            },
            "personalization": {
                "enabled": True
            },
            "safety_compliance": {
                "content_filtering": {"enabled": True},
                "privacy_protection": {"anonymize_exports": True}
            },
            "performance": {
                "caching": {"enabled": True, "ttl_seconds": 3600}
            },
            "development": {
                "debug_mode": False,
                "verbose_logging": False
            }
        }
    
    def _apply_env_overrides(self):
        """应用环境变量覆盖"""
        env_mappings = {
            "CHAT_AGENT_ENABLED": ("chat_agent", "enabled"),
            "ENABLE_MEMORY_RECALL": ("memory_system", "enable_memory_recall"),
            "ENABLE_EMOTION_ANALYSIS": ("emotion_analysis", "enabled"),
            "ENABLE_RISK_DETECTION": ("risk_detection", "enabled"),
            "ENABLE_KNOWLEDGE_INJECTION": ("knowledge_injection", "enabled"),
            "AGENT_DEBUG_MODE": ("development", "debug_mode"),
            "AGENT_VERBOSE_LOGGING": ("development", "verbose_logging")
        }
        
        for env_var, (section, key) in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                # 转换布尔值
                if env_value.lower() in ('true', '1', 'yes', 'on'):
                    value = True
                elif env_value.lower() in ('false', '0', 'no', 'off'):
                    value = False
                else:
                    # 尝试转换为数字
                    try:
                        value = int(env_value)
                    except ValueError:
                        try:
                            value = float(env_value)
                        except ValueError:
                            value = env_value
                
                # 设置配置值
                if section not in self._config_data:
                    self._config_data[section] = {}
                self._config_data[section][key] = value
                logger.info(f"✅ 环境变量覆盖配置: {env_var} -> {section}.{key} = {value}")
    
    def get(self, section: str, key: str = None, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            section: 配置段名
            key: 配置键名，如果为None则返回整个段
            default: 默认值
        
        Returns:
            配置值
        """
        if section not in self._config_data:
            return default
        
        section_data = self._config_data[section]
        
        if key is None:
            return section_data
        
        return section_data.get(key, default)
    
    def set(self, section: str, key: str, value: Any):
        """
        设置配置值（运行时修改）
        
        Args:
            section: 配置段名
            key: 配置键名
            value: 配置值
        """
        if section not in self._config_data:
            self._config_data[section] = {}
        
        old_value = self._config_data[section].get(key)
        self._config_data[section][key] = value
        
        logger.info(f"✅ 配置更新: {section}.{key} = {value} (原值: {old_value})")
    
    def reload(self):
        """重新加载配置文件"""
        logger.info("🔄 重新加载Agent配置文件...")
        self._load_config()
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config_data.copy()
    
    # ==================== 便捷访问方法 ====================
    
    @property
    def chat_agent_enabled(self) -> bool:
        """ChatAgent是否启用"""
        return self.get("chat_agent", "enabled", True)
    
    @property
    def memory_recall_enabled(self) -> bool:
        """记忆召回是否启用"""
        return self.get("memory_system", "enable_memory_recall", True)
    
    @property
    def emotion_analysis_enabled(self) -> bool:
        """情绪分析是否启用"""
        return self.get("emotion_analysis", "enabled", True)
    
    @property
    def risk_detection_enabled(self) -> bool:
        """风险检测是否启用"""
        return self.get("risk_detection", "enabled", True)
    
    @property
    def knowledge_injection_enabled(self) -> bool:
        """知识注入是否启用"""
        return self.get("knowledge_injection", "enabled", True)
    
    @property
    def debug_mode(self) -> bool:
        """调试模式是否启用"""
        return self.get("development", "debug_mode", False)
    
    @property
    def verbose_logging(self) -> bool:
        """详细日志是否启用"""
        return self.get("development", "verbose_logging", False)
    
    def get_chat_agent_config(self) -> Dict[str, Any]:
        """获取ChatAgent配置"""
        return self.get("chat_agent", default={})
    
    def get_memory_config(self) -> Dict[str, Any]:
        """获取记忆系统配置"""
        return self.get("memory_system", default={})
    
    def get_emotion_config(self) -> Dict[str, Any]:
        """获取情绪分析配置"""
        return self.get("emotion_analysis", default={})
    
    def get_risk_config(self) -> Dict[str, Any]:
        """获取风险检测配置"""
        return self.get("risk_detection", default={})
    
    def get_knowledge_config(self) -> Dict[str, Any]:
        """获取知识注入配置"""
        return self.get("knowledge_injection", default={})
    
    def get_performance_config(self) -> Dict[str, Any]:
        """获取性能配置"""
        return self.get("performance", default={})
    
    # ==================== 配置验证 ====================
    
    def validate_config(self) -> Dict[str, Any]:
        """
        验证配置的有效性
        
        Returns:
            验证结果字典
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # 验证ChatAgent配置
        chat_config = self.get_chat_agent_config()
        if chat_config.get("max_context_messages", 0) <= 0:
            validation_result["errors"].append("chat_agent.max_context_messages 必须大于0")
            validation_result["valid"] = False
        
        if chat_config.get("default_timeout_s", 0) <= 0:
            validation_result["errors"].append("chat_agent.default_timeout_s 必须大于0")
            validation_result["valid"] = False
        
        # 验证记忆系统配置
        memory_config = self.get_memory_config()
        recall_policy = memory_config.get("recall_policy", {})
        if recall_policy.get("min_similarity", 0) < 0 or recall_policy.get("min_similarity", 0) > 1:
            validation_result["warnings"].append("memory_system.recall_policy.min_similarity 建议在0-1之间")
        
        # 验证情绪分析配置
        emotion_config = self.get_emotion_config()
        if emotion_config.get("emotion_threshold", 0) < 0 or emotion_config.get("emotion_threshold", 0) > 1:
            validation_result["warnings"].append("emotion_analysis.emotion_threshold 建议在0-1之间")
        
        return validation_result


# 全局配置实例
_agent_config = None


def get_agent_config() -> AgentConfig:
    """获取Agent配置管理器单例"""
    global _agent_config
    if _agent_config is None:
        _agent_config = AgentConfig()
        
        # 验证配置
        validation = _agent_config.validate_config()
        if not validation["valid"]:
            logger.error(f"❌ Agent配置验证失败: {validation['errors']}")
        if validation["warnings"]:
            logger.warning(f"⚠️ Agent配置警告: {validation['warnings']}")
    
    return _agent_config


def reload_agent_config():
    """重新加载Agent配置"""
    global _agent_config
    if _agent_config:
        _agent_config.reload()
    else:
        _agent_config = AgentConfig()


# ==================== 配置装饰器 ====================

def require_agent_feature(feature: str):
    """
    装饰器：要求特定Agent功能启用
    
    Args:
        feature: 功能名称 (chat_agent, memory_recall, emotion_analysis, risk_detection, knowledge_injection)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            config = get_agent_config()
            
            feature_enabled = {
                "chat_agent": config.chat_agent_enabled,
                "memory_recall": config.memory_recall_enabled,
                "emotion_analysis": config.emotion_analysis_enabled,
                "risk_detection": config.risk_detection_enabled,
                "knowledge_injection": config.knowledge_injection_enabled
            }.get(feature, False)
            
            if not feature_enabled:
                logger.warning(f"⚠️ 功能 {feature} 未启用，跳过执行")
                return None
            
            return func(*args, **kwargs)
        return wrapper
    return decorator
