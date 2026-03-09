"""
用户状态同步服务
User State Synchronization Service
提供分布式用户状态管理、在线状态同步和跨实例用户数据共享
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, asdict
from enum import Enum

from app.core import logger, settings
from .redis_manager import get_redis_manager


class UserStatus(Enum):
    """用户状态枚举"""
    OFFLINE = "offline"
    ONLINE = "online"
    AWAY = "away"
    BUSY = "busy"
    INVISIBLE = "invisible"


@dataclass
class UserState:
    """用户状态数据"""
    user_id: str
    status: UserStatus = UserStatus.OFFLINE
    last_activity: datetime = None
    server_instance: str = ""
    connection_count: int = 0
    client_info: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.last_activity is None:
            self.last_activity = datetime.now()
        if self.client_info is None:
            self.client_info = {}
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        data['last_activity'] = self.last_activity.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserState':
        """从字典创建"""
        if 'status' in data:
            data['status'] = UserStatus(data['status'])
        if 'last_activity' in data and isinstance(data['last_activity'], str):
            data['last_activity'] = datetime.fromisoformat(data['last_activity'])
        return cls(**data)


class UserStateService:
    """用户状态同步服务"""
    
    def __init__(self):
        """初始化用户状态服务"""
        self.redis_manager = get_redis_manager()
        self.server_instance = f"server_{int(time.time())}_{id(self)}"
        self.local_states: Dict[str, UserState] = {}
        
        # 状态同步任务
        self._sync_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 配置
        self.sync_interval = 10  # 状态同步间隔(秒)
        self.cleanup_interval = 60  # 清理间隔(秒)
        self.offline_threshold = 300  # 离线阈值(秒)
        
        logger.info(f"🔧 用户状态服务初始化完成 (实例: {self.server_instance})")
    
    async def start(self):
        """启动用户状态服务"""
        if not settings.ENABLE_USER_STATE_SYNC or not self.redis_manager.is_connected():
            logger.info("⏸️ 用户状态同步已禁用或Redis未连接")
            return
        
        logger.info("🚀 启动用户状态同步服务...")
        
        self._running = True
        
        # 启动后台任务
        self._sync_task = asyncio.create_task(self._sync_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("✅ 用户状态同步服务启动完成")
    
    async def stop(self):
        """停止用户状态服务"""
        logger.info("⏹️ 停止用户状态同步服务...")
        
        self._running = False
        
        # 取消后台任务
        tasks = [self._sync_task, self._cleanup_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 清理本实例的用户状态
        await self._cleanup_instance_states()
        
        logger.info("✅ 用户状态同步服务已停止")
    
    async def update_user_status(self, user_id: str, status: UserStatus, 
                                client_info: Optional[Dict[str, Any]] = None,
                                metadata: Optional[Dict[str, Any]] = None):
        """更新用户状态"""
        try:
            # 更新本地状态
            if user_id not in self.local_states:
                self.local_states[user_id] = UserState(
                    user_id=user_id,
                    server_instance=self.server_instance
                )
            
            user_state = self.local_states[user_id]
            user_state.status = status
            user_state.last_activity = datetime.now()
            
            if client_info:
                user_state.client_info.update(client_info)
            if metadata:
                user_state.metadata.update(metadata)
            
            # 同步到Redis
            await self._sync_user_state_to_redis(user_state)
            
            logger.debug(f"📊 更新用户状态: {user_id} -> {status.value}")
            
        except Exception as e:
            logger.error(f"❌ 更新用户状态失败 {user_id}: {e}", exc_info=True)
    
    async def user_connected(self, user_id: str, client_info: Optional[Dict[str, Any]] = None):
        """用户连接"""
        try:
            # 增加连接计数
            if user_id in self.local_states:
                self.local_states[user_id].connection_count += 1
            else:
                self.local_states[user_id] = UserState(
                    user_id=user_id,
                    server_instance=self.server_instance,
                    connection_count=1
                )
            
            # 更新状态为在线
            await self.update_user_status(user_id, UserStatus.ONLINE, client_info)
            
            logger.info(f"👤 用户连接: {user_id} (连接数: {self.local_states[user_id].connection_count})")
            
        except Exception as e:
            logger.error(f"❌ 处理用户连接失败 {user_id}: {e}", exc_info=True)
    
    async def user_disconnected(self, user_id: str):
        """用户断开连接"""
        try:
            if user_id not in self.local_states:
                return
            
            user_state = self.local_states[user_id]
            user_state.connection_count = max(0, user_state.connection_count - 1)
            
            # 如果没有连接了，设置为离线
            if user_state.connection_count == 0:
                await self.update_user_status(user_id, UserStatus.OFFLINE)
                # 从本地状态中移除
                del self.local_states[user_id]
            else:
                # 更新活动时间
                user_state.last_activity = datetime.now()
                await self._sync_user_state_to_redis(user_state)
            
            logger.info(f"👤 用户断开: {user_id} (剩余连接: {user_state.connection_count})")
            
        except Exception as e:
            logger.error(f"❌ 处理用户断开失败 {user_id}: {e}", exc_info=True)
    
    async def update_user_activity(self, user_id: str):
        """更新用户活动时间"""
        try:
            if user_id in self.local_states:
                self.local_states[user_id].last_activity = datetime.now()
                # 定期同步到Redis（不是每次活动都同步）
                
        except Exception as e:
            logger.error(f"❌ 更新用户活动失败 {user_id}: {e}")
    
    async def get_user_state(self, user_id: str) -> Optional[UserState]:
        """获取用户状态"""
        try:
            # 先检查本地状态
            if user_id in self.local_states:
                return self.local_states[user_id]
            
            # 从Redis获取
            return await self._get_user_state_from_redis(user_id)
            
        except Exception as e:
            logger.error(f"❌ 获取用户状态失败 {user_id}: {e}")
            return None
    
    async def get_online_users(self) -> List[UserState]:
        """获取所有在线用户"""
        try:
            online_users = []
            
            # 获取所有用户状态键
            pattern = self._build_user_state_key("*")
            keys = await self.redis_manager.execute_command('keys', pattern)
            
            for key in keys:
                try:
                    data = await self.redis_manager.get_json(key.replace(f"{settings.REDIS_KEY_PREFIX}:", ""))
                    if data:
                        user_state = UserState.from_dict(data)
                        if user_state.status != UserStatus.OFFLINE:
                            online_users.append(user_state)
                except Exception as e:
                    logger.debug(f"解析用户状态失败 {key}: {e}")
            
            return online_users
            
        except Exception as e:
            logger.error(f"❌ 获取在线用户失败: {e}")
            return []
    
    async def get_user_count_by_status(self) -> Dict[str, int]:
        """获取各状态用户数量统计"""
        try:
            status_counts = {status.value: 0 for status in UserStatus}
            
            online_users = await self.get_online_users()
            for user_state in online_users:
                status_counts[user_state.status.value] += 1
            
            return status_counts
            
        except Exception as e:
            logger.error(f"❌ 获取用户状态统计失败: {e}")
            return {}
    
    async def find_user_server(self, user_id: str) -> Optional[str]:
        """查找用户所在的服务器实例"""
        try:
            user_state = await self.get_user_state(user_id)
            if user_state and user_state.status != UserStatus.OFFLINE:
                return user_state.server_instance
            return None
            
        except Exception as e:
            logger.error(f"❌ 查找用户服务器失败 {user_id}: {e}")
            return None
    
    async def broadcast_to_online_users(self, message: Dict[str, Any], 
                                      exclude_users: Optional[Set[str]] = None) -> int:
        """向所有在线用户广播消息"""
        try:
            exclude_users = exclude_users or set()
            online_users = await self.get_online_users()
            
            broadcast_count = 0
            for user_state in online_users:
                if user_state.user_id not in exclude_users:
                    # 这里需要与连接池管理器集成来实际发送消息
                    # 暂时只记录日志
                    logger.debug(f"📢 广播消息到用户: {user_state.user_id}")
                    broadcast_count += 1
            
            return broadcast_count
            
        except Exception as e:
            logger.error(f"❌ 广播消息失败: {e}")
            return 0
    
    async def _sync_user_state_to_redis(self, user_state: UserState):
        """同步用户状态到Redis"""
        try:
            key = self._build_user_state_key(user_state.user_id)
            await self.redis_manager.set_json(key, user_state.to_dict(), ex=settings.USER_STATE_TTL)
            
        except Exception as e:
            logger.error(f"❌ 同步用户状态到Redis失败 {user_state.user_id}: {e}")
    
    async def _get_user_state_from_redis(self, user_id: str) -> Optional[UserState]:
        """从Redis获取用户状态"""
        try:
            key = self._build_user_state_key(user_id)
            data = await self.redis_manager.get_json(key)
            if data:
                return UserState.from_dict(data)
            return None
            
        except Exception as e:
            logger.error(f"❌ 从Redis获取用户状态失败 {user_id}: {e}")
            return None
    
    async def _sync_loop(self):
        """状态同步循环"""
        logger.info("🔄 启动用户状态同步循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.sync_interval)
                await self._sync_all_states()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 状态同步循环异常: {e}", exc_info=True)
    
    async def _sync_all_states(self):
        """同步所有本地状态到Redis"""
        try:
            sync_count = 0
            for user_state in self.local_states.values():
                await self._sync_user_state_to_redis(user_state)
                sync_count += 1
            
            if sync_count > 0:
                logger.debug(f"🔄 同步 {sync_count} 个用户状态到Redis")
                
        except Exception as e:
            logger.error(f"❌ 同步所有状态失败: {e}")
    
    async def _cleanup_loop(self):
        """清理循环"""
        logger.info("🧹 启动用户状态清理循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired_states()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 状态清理循环异常: {e}", exc_info=True)
    
    async def _cleanup_expired_states(self):
        """清理过期状态"""
        try:
            now = datetime.now()
            expired_users = []
            
            # 检查本地状态
            for user_id, user_state in self.local_states.items():
                if (now - user_state.last_activity).total_seconds() > self.offline_threshold:
                    expired_users.append(user_id)
            
            # 清理过期用户
            for user_id in expired_users:
                await self.update_user_status(user_id, UserStatus.OFFLINE)
                del self.local_states[user_id]
                logger.debug(f"🧹 清理过期用户状态: {user_id}")
            
            if expired_users:
                logger.info(f"🧹 清理了 {len(expired_users)} 个过期用户状态")
                
        except Exception as e:
            logger.error(f"❌ 清理过期状态失败: {e}")
    
    async def _cleanup_instance_states(self):
        """清理本实例的所有用户状态"""
        try:
            cleanup_count = 0
            for user_id in list(self.local_states.keys()):
                await self.update_user_status(user_id, UserStatus.OFFLINE)
                cleanup_count += 1
            
            self.local_states.clear()
            
            if cleanup_count > 0:
                logger.info(f"🧹 清理本实例 {cleanup_count} 个用户状态")
                
        except Exception as e:
            logger.error(f"❌ 清理实例状态失败: {e}")
    
    def _build_user_state_key(self, user_id: str) -> str:
        """构建用户状态键名"""
        return f"user_state:{user_id}"
    
    def get_local_user_count(self) -> int:
        """获取本地用户数量"""
        return len(self.local_states)
    
    def get_local_users(self) -> List[str]:
        """获取本地用户列表"""
        return list(self.local_states.keys())


# 全局用户状态服务实例
_user_state_service: Optional[UserStateService] = None


def get_user_state_service() -> UserStateService:
    """获取用户状态服务实例"""
    global _user_state_service
    if _user_state_service is None:
        _user_state_service = UserStateService()
    return _user_state_service


async def initialize_user_state_service():
    """初始化用户状态服务"""
    service = get_user_state_service()
    await service.start()
    return service


async def shutdown_user_state_service():
    """关闭用户状态服务"""
    global _user_state_service
    if _user_state_service:
        await _user_state_service.stop()
        _user_state_service = None
