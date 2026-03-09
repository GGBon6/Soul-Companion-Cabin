"""
青少年心理对话配置管理器
Youth Psychology Configuration Manager
管理青少年心理对话相关的配置参数
"""

import os
import yaml
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging


@dataclass
class CrisisHotline:
    """危机干预热线信息"""
    name: str
    number: str
    description: str


@dataclass
class OnlinePlatform:
    """在线心理健康平台"""
    name: str
    url: str
    description: str


@dataclass
class ReferralResource:
    """转介资源"""
    type: str
    name: str
    contact: str
    description: str


class YouthPsychologyConfig:
    """青少年心理对话配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        
        # 默认配置文件路径
        if config_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            config_path = os.path.join(project_root, "config", "youth_psychology_config.yaml")
        
        self.config_path = config_path
        self.config_data = {}
        
        # 加载配置
        self.load_config()
    
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config_data = yaml.safe_load(f) or {}
                self.logger.info(f"青少年心理对话配置已加载: {self.config_path}")
            else:
                self.logger.warning(f"配置文件不存在，使用默认配置: {self.config_path}")
                self.config_data = self._get_default_config()
        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}")
            self.config_data = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "intent_recognition": {
                "enabled": True,
                "crisis_detection": {
                    "enabled": True,
                    "sensitivity": 0.8,
                    "auto_referral_risk_levels": ["critical"]
                },
                "emotional_analysis": {
                    "enabled": True,
                    "intensity_threshold": 0.7
                },
                "cache": {
                    "enabled": True,
                    "ttl": 300,
                    "max_entries": 1000
                }
            },
            "response_generation": {
                "mode": "supportive",
                "use_templates": True,
                "llm_params": {
                    "temperature": 0.7,
                    "max_tokens": 500,
                    "timeout": 10.0
                }
            },
            "resources": {
                "crisis_hotlines": [
                    {
                        "name": "全国心理危机干预热线",
                        "number": "400-161-9995",
                        "description": "24小时心理危机干预服务"
                    }
                ]
            },
            "risk_assessment": {
                "thresholds": {
                    "low": 0.3,
                    "medium": 0.6,
                    "high": 0.8,
                    "critical": 0.9
                }
            }
        }
    
    # 意图识别配置
    def is_intent_recognition_enabled(self) -> bool:
        """是否启用意图识别"""
        return self.config_data.get("intent_recognition", {}).get("enabled", True)
    
    def is_crisis_detection_enabled(self) -> bool:
        """是否启用危机检测"""
        return self.config_data.get("intent_recognition", {}).get("crisis_detection", {}).get("enabled", True)
    
    def get_crisis_sensitivity(self) -> float:
        """获取危机检测敏感度"""
        return self.config_data.get("intent_recognition", {}).get("crisis_detection", {}).get("sensitivity", 0.8)
    
    def get_auto_referral_risk_levels(self) -> List[str]:
        """获取自动转介的风险等级"""
        return self.config_data.get("intent_recognition", {}).get("crisis_detection", {}).get("auto_referral_risk_levels", ["critical"])
    
    def is_emotional_analysis_enabled(self) -> bool:
        """是否启用情感分析"""
        return self.config_data.get("intent_recognition", {}).get("emotional_analysis", {}).get("enabled", True)
    
    def get_emotional_intensity_threshold(self) -> float:
        """获取情感强度阈值"""
        return self.config_data.get("intent_recognition", {}).get("emotional_analysis", {}).get("intensity_threshold", 0.7)
    
    # 缓存配置
    def is_cache_enabled(self) -> bool:
        """是否启用缓存"""
        return self.config_data.get("intent_recognition", {}).get("cache", {}).get("enabled", True)
    
    def get_cache_ttl(self) -> int:
        """获取缓存TTL"""
        return self.config_data.get("intent_recognition", {}).get("cache", {}).get("ttl", 300)
    
    def get_cache_max_entries(self) -> int:
        """获取缓存最大条目数"""
        return self.config_data.get("intent_recognition", {}).get("cache", {}).get("max_entries", 1000)
    
    # 响应生成配置
    def get_response_mode(self) -> str:
        """获取响应模式"""
        return self.config_data.get("response_generation", {}).get("mode", "supportive")
    
    def use_response_templates(self) -> bool:
        """是否使用响应模板"""
        return self.config_data.get("response_generation", {}).get("use_templates", True)
    
    def get_llm_temperature(self) -> float:
        """获取LLM温度参数"""
        return self.config_data.get("response_generation", {}).get("llm_params", {}).get("temperature", 0.7)
    
    def get_llm_max_tokens(self) -> int:
        """获取LLM最大token数"""
        return self.config_data.get("response_generation", {}).get("llm_params", {}).get("max_tokens", 500)
    
    def get_llm_timeout(self) -> float:
        """获取LLM超时时间"""
        return self.config_data.get("response_generation", {}).get("llm_params", {}).get("timeout", 10.0)
    
    # 资源配置
    def get_crisis_hotlines(self) -> List[CrisisHotline]:
        """获取危机干预热线列表"""
        hotlines_data = self.config_data.get("resources", {}).get("crisis_hotlines", [])
        return [
            CrisisHotline(
                name=hotline.get("name", ""),
                number=hotline.get("number", ""),
                description=hotline.get("description", "")
            )
            for hotline in hotlines_data
        ]
    
    def get_online_platforms(self) -> List[OnlinePlatform]:
        """获取在线心理健康平台列表"""
        platforms_data = self.config_data.get("resources", {}).get("online_platforms", [])
        return [
            OnlinePlatform(
                name=platform.get("name", ""),
                url=platform.get("url", ""),
                description=platform.get("description", "")
            )
            for platform in platforms_data
        ]
    
    def get_self_help_resources(self) -> List[Dict[str, str]]:
        """获取自助资源列表"""
        return self.config_data.get("resources", {}).get("self_help", [])
    
    # 风险评估配置
    def get_risk_thresholds(self) -> Dict[str, float]:
        """获取风险等级阈值"""
        return self.config_data.get("risk_assessment", {}).get("thresholds", {
            "low": 0.3,
            "medium": 0.6,
            "high": 0.8,
            "critical": 0.9
        })
    
    def get_risk_factors_weights(self) -> Dict[str, float]:
        """获取风险因素权重"""
        return self.config_data.get("risk_assessment", {}).get("risk_factors", {
            "suicide_keywords": 0.9,
            "self_harm_keywords": 0.8,
            "severe_depression": 0.7,
            "social_isolation": 0.6,
            "family_conflict": 0.5,
            "academic_pressure": 0.4
        })
    
    # 对话管理配置
    def get_max_history_length(self) -> int:
        """获取最大对话历史长度"""
        return self.config_data.get("conversation", {}).get("max_history_length", 10)
    
    def get_session_timeout(self) -> int:
        """获取会话超时时间（分钟）"""
        return self.config_data.get("conversation", {}).get("session_timeout", 30)
    
    def should_save_sensitive_conversations(self) -> bool:
        """是否保存敏感对话记录"""
        return self.config_data.get("conversation", {}).get("save_sensitive_conversations", False)
    
    def should_auto_summarize(self) -> bool:
        """是否自动总结会话"""
        return self.config_data.get("conversation", {}).get("auto_summarize", True)
    
    # 专业转介配置
    def get_auto_referral_conditions(self) -> List[str]:
        """获取自动转介条件"""
        return self.config_data.get("professional_referral", {}).get("auto_referral_conditions", [
            "suicide_crisis", "self_harm_crisis", "severe_depression"
        ])
    
    def get_referral_resources(self) -> List[ReferralResource]:
        """获取转介资源列表"""
        resources_data = self.config_data.get("professional_referral", {}).get("referral_resources", [])
        return [
            ReferralResource(
                type=resource.get("type", ""),
                name=resource.get("name", ""),
                contact=resource.get("contact", ""),
                description=resource.get("description", "")
            )
            for resource in resources_data
        ]
    
    # 隐私和安全配置
    def should_encrypt_sensitive_data(self) -> bool:
        """是否加密敏感数据"""
        return self.config_data.get("privacy", {}).get("encrypt_sensitive_data", True)
    
    def get_data_retention_days(self) -> int:
        """获取数据保留期限（天）"""
        return self.config_data.get("privacy", {}).get("data_retention_days", 30)
    
    def should_anonymize_data(self) -> bool:
        """是否匿名化数据"""
        return self.config_data.get("privacy", {}).get("anonymize_data", True)
    
    # 监控配置
    def is_statistics_enabled(self) -> bool:
        """是否启用统计收集"""
        return self.config_data.get("monitoring", {}).get("enable_statistics", True)
    
    def get_report_frequency(self) -> int:
        """获取统计报告频率（小时）"""
        return self.config_data.get("monitoring", {}).get("report_frequency", 24)
    
    def is_anomaly_detection_enabled(self) -> bool:
        """是否启用异常检测"""
        return self.config_data.get("monitoring", {}).get("anomaly_detection", {}).get("enabled", True)
    
    # 个性化配置
    def is_adaptive_responses_enabled(self) -> bool:
        """是否启用自适应响应"""
        return self.config_data.get("personalization", {}).get("adaptive_responses", True)
    
    def should_learn_preferences(self) -> bool:
        """是否学习用户偏好"""
        return self.config_data.get("personalization", {}).get("learn_preferences", True)
    
    def is_personalized_suggestions_enabled(self) -> bool:
        """是否启用个性化建议"""
        return self.config_data.get("personalization", {}).get("personalized_suggestions", True)
    
    # 语言配置
    def get_default_language(self) -> str:
        """获取默认语言"""
        return self.config_data.get("language", {}).get("default", "zh-CN")
    
    def get_supported_languages(self) -> List[str]:
        """获取支持的语言列表"""
        return self.config_data.get("language", {}).get("supported", ["zh-CN", "en-US"])
    
    def is_auto_language_detect_enabled(self) -> bool:
        """是否启用自动语言检测"""
        return self.config_data.get("language", {}).get("auto_detect", True)
    
    # 配置更新
    def update_config(self, key_path: str, value: Any) -> bool:
        """
        更新配置值
        
        Args:
            key_path: 配置键路径，如 "intent_recognition.enabled"
            value: 新值
            
        Returns:
            bool: 是否更新成功
        """
        try:
            keys = key_path.split('.')
            current = self.config_data
            
            # 导航到父级配置
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            
            # 设置值
            current[keys[-1]] = value
            
            # 保存配置文件
            self.save_config()
            
            self.logger.info(f"配置已更新: {key_path} = {value}")
            return True
            
        except Exception as e:
            self.logger.error(f"更新配置失败: {e}")
            return False
    
    def save_config(self) -> bool:
        """保存配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config_data, f, default_flow_style=False, allow_unicode=True)
            return True
        except Exception as e:
            self.logger.error(f"保存配置文件失败: {e}")
            return False
    
    def reload_config(self) -> None:
        """重新加载配置"""
        self.load_config()
        self.logger.info("配置已重新加载")
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            "intent_recognition_enabled": self.is_intent_recognition_enabled(),
            "crisis_detection_enabled": self.is_crisis_detection_enabled(),
            "emotional_analysis_enabled": self.is_emotional_analysis_enabled(),
            "response_mode": self.get_response_mode(),
            "cache_enabled": self.is_cache_enabled(),
            "statistics_enabled": self.is_statistics_enabled(),
            "supported_languages": self.get_supported_languages(),
            "crisis_hotlines_count": len(self.get_crisis_hotlines()),
            "referral_resources_count": len(self.get_referral_resources())
        }


# 全局配置实例
_youth_psychology_config: Optional[YouthPsychologyConfig] = None


def get_youth_psychology_config() -> YouthPsychologyConfig:
    """获取青少年心理对话配置实例"""
    global _youth_psychology_config
    if _youth_psychology_config is None:
        _youth_psychology_config = YouthPsychologyConfig()
    return _youth_psychology_config


def reload_youth_psychology_config() -> None:
    """重新加载青少年心理对话配置"""
    global _youth_psychology_config
    if _youth_psychology_config is not None:
        _youth_psychology_config.reload_config()
    else:
        _youth_psychology_config = YouthPsychologyConfig()
