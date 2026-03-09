"""
Redis共享存储模块
Redis Shared Storage Module
提供分布式用户状态同步、会话管理和连接池功能
"""

from .redis_manager import RedisManager, get_redis_manager, initialize_redis_manager, shutdown_redis_manager
from .user_state_service import UserStateService, get_user_state_service, initialize_user_state_service, shutdown_user_state_service
from .session_store import SessionStore, get_session_store, initialize_session_store, shutdown_session_store
from .distributed_pool import DistributedConnectionPool, get_distributed_pool, initialize_distributed_pool, shutdown_distributed_pool
from .pubsub_service import PubSubService, get_pubsub_service, initialize_pubsub_service, shutdown_pubsub_service
from .health_monitor import RedisHealthMonitor, get_redis_health_monitor, initialize_redis_health_monitor, shutdown_redis_health_monitor

__all__ = [
    'RedisManager',
    'get_redis_manager',
    'initialize_redis_manager',
    'shutdown_redis_manager',
    'UserStateService', 
    'get_user_state_service',
    'initialize_user_state_service',
    'shutdown_user_state_service',
    'SessionStore',
    'get_session_store',
    'initialize_session_store',
    'shutdown_session_store',
    'DistributedConnectionPool',
    'get_distributed_pool',
    'initialize_distributed_pool',
    'shutdown_distributed_pool',
    'PubSubService',
    'get_pubsub_service',
    'initialize_pubsub_service',
    'shutdown_pubsub_service',
    'RedisHealthMonitor',
    'get_redis_health_monitor',
    'initialize_redis_health_monitor',
    'shutdown_redis_health_monitor',
]
