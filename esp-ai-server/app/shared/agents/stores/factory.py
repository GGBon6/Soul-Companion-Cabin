"""
存储工厂
创建和配置完整的 MemoryManager 实例
"""

from pathlib import Path
from typing import Optional

from app.core import settings, logger
from app.shared.agents.base_agent import MemoryManager, MemoryPolicies

from .vector_ops import SimpleVectorOps
from .episodic_store import FileEpisodicStore
from .profile_store import FileProfileStore
from .affect_store import FileAffectStore
from .safety_store import FileSafetyStore
from .working_cache import MemoryWorkingCache


def create_memory_manager(
    data_dir: Optional[Path] = None,
    policies: Optional[MemoryPolicies] = None
) -> MemoryManager:
    """
    创建完整的 MemoryManager 实例
    
    Args:
        data_dir: 数据存储目录，默认使用 settings.DATA_DIR
        policies: 记忆策略，默认使用标准策略
    
    Returns:
        配置完整的 MemoryManager 实例
    """
    if data_dir is None:
        data_dir = settings.DATA_DIR
    
    if policies is None:
        policies = MemoryPolicies()
    
    # 创建所有存储组件
    vector_ops = SimpleVectorOps()
    episodic_store = FileEpisodicStore(data_dir)
    profile_store = FileProfileStore(data_dir)
    affect_store = FileAffectStore(data_dir)
    safety_store = FileSafetyStore(data_dir)
    working_cache = MemoryWorkingCache()
    
    # 创建 MemoryManager
    memory_manager = MemoryManager(
        vector_ops=vector_ops,
        episodic_store=episodic_store,
        profile_store=profile_store,
        affect_store=affect_store,
        safety_store=safety_store,
        working_cache=working_cache,
        policies=policies
    )
    
    logger.info("✅ 创建完整的 BaseAgent MemoryManager")
    
    return memory_manager


def create_custom_memory_manager(
    vector_ops=None,
    episodic_store=None,
    profile_store=None,
    affect_store=None,
    safety_store=None,
    working_cache=None,
    policies=None,
    data_dir: Optional[Path] = None
) -> MemoryManager:
    """
    创建自定义的 MemoryManager 实例
    允许替换特定的存储组件
    """
    if data_dir is None:
        data_dir = settings.DATA_DIR
    
    # 使用提供的组件或创建默认组件
    if vector_ops is None:
        vector_ops = SimpleVectorOps()
    
    if episodic_store is None:
        episodic_store = FileEpisodicStore(data_dir)
    
    if profile_store is None:
        profile_store = FileProfileStore(data_dir)
    
    if affect_store is None:
        affect_store = FileAffectStore(data_dir)
    
    if safety_store is None:
        safety_store = FileSafetyStore(data_dir)
    
    if working_cache is None:
        working_cache = MemoryWorkingCache()
    
    if policies is None:
        policies = MemoryPolicies()
    
    memory_manager = MemoryManager(
        vector_ops=vector_ops,
        episodic_store=episodic_store,
        profile_store=profile_store,
        affect_store=affect_store,
        safety_store=safety_store,
        working_cache=working_cache,
        policies=policies
    )
    
    logger.info("✅ 创建自定义 BaseAgent MemoryManager")
    
    return memory_manager
