"""
会话存储服务
Session Store Service
提供分布式会话管理、用户会话共享和跨实例会话同步
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

from app.core import logger, settings
from .redis_manager import get_redis_manager


@dataclass
class UserSession:
    """用户会话数据"""
    session_id: str
    user_id: str
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime
    server_instance: str = ""
    data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['last_accessed'] = self.last_accessed.isoformat()
        data['expires_at'] = self.expires_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserSession':
        """从字典创建"""
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'last_accessed' in data and isinstance(data['last_accessed'], str):
            data['last_accessed'] = datetime.fromisoformat(data['last_accessed'])
        if 'expires_at' in data and isinstance(data['expires_at'], str):
            data['expires_at'] = datetime.fromisoformat(data['expires_at'])
        return cls(**data)
    
    @property
    def is_expired(self) -> bool:
        """检查会话是否过期"""
        return datetime.now() > self.expires_at
    
    def refresh(self, extend_seconds: int = None):
        """刷新会话"""
        now = datetime.now()
        self.last_accessed = now
        if extend_seconds:
            self.expires_at = now + timedelta(seconds=extend_seconds)
        else:
            self.expires_at = now + timedelta(seconds=settings.SESSION_TTL)


class SessionStore:
    """会话存储服务"""
    
    def __init__(self):
        """初始化会话存储"""
        self.redis_manager = get_redis_manager()
        self.server_instance = f"server_{int(time.time())}_{id(self)}"
        
        # 本地会话缓存
        self.local_sessions: Dict[str, UserSession] = {}
        
        # 后台任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 配置
        self.cleanup_interval = 300  # 清理间隔(秒)
        self.sync_interval = 60     # 同步间隔(秒)
        self.default_ttl = settings.SESSION_TTL
        
        logger.info(f"🔧 会话存储服务初始化完成 (实例: {self.server_instance})")
    
    async def start(self):
        """启动会话存储服务"""
        if not settings.ENABLE_DISTRIBUTED_SESSIONS or not self.redis_manager.is_connected():
            logger.info("⏸️ 分布式会话存储已禁用或Redis未连接")
            return
        
        logger.info("🚀 启动会话存储服务...")
        
        self._running = True
        
        # 启动后台任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._sync_task = asyncio.create_task(self._sync_loop())
        
        logger.info("✅ 会话存储服务启动完成")
    
    async def stop(self):
        """停止会话存储服务"""
        logger.info("⏹️ 停止会话存储服务...")
        
        self._running = False
        
        # 取消后台任务
        tasks = [self._cleanup_task, self._sync_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 清理本地会话
        self.local_sessions.clear()
        
        logger.info("✅ 会话存储服务已停止")
    
    async def create_session(self, user_id: str, session_data: Optional[Dict[str, Any]] = None,
                           ttl_seconds: Optional[int] = None) -> UserSession:
        """创建新会话"""
        try:
            session_id = self._generate_session_id(user_id)
            now = datetime.now()
            ttl = ttl_seconds or self.default_ttl
            
            session = UserSession(
                session_id=session_id,
                user_id=user_id,
                created_at=now,
                last_accessed=now,
                expires_at=now + timedelta(seconds=ttl),
                server_instance=self.server_instance,
                data=session_data or {}
            )
            
            # 保存到本地缓存和Redis
            self.local_sessions[session_id] = session
            await self._save_session_to_redis(session)
            
            logger.info(f"📝 创建用户会话: {user_id} -> {session_id}")
            return session
            
        except Exception as e:
            logger.error(f"❌ 创建会话失败 {user_id}: {e}", exc_info=True)
            raise
    
    async def get_session(self, session_id: str) -> Optional[UserSession]:
        """获取会话"""
        try:
            # 先检查本地缓存
            if session_id in self.local_sessions:
                session = self.local_sessions[session_id]
                if not session.is_expired:
                    session.refresh()
                    return session
                else:
                    # 本地会话过期，删除
                    del self.local_sessions[session_id]
            
            # 从Redis获取
            session = await self._load_session_from_redis(session_id)
            if session and not session.is_expired:
                # 缓存到本地
                self.local_sessions[session_id] = session
                session.refresh()
                await self._save_session_to_redis(session)
                return session
            elif session:
                # Redis中的会话也过期了，删除
                await self._delete_session_from_redis(session_id)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取会话失败 {session_id}: {e}")
            return None
    
    async def get_user_sessions(self, user_id: str) -> List[UserSession]:
        """获取用户的所有会话"""
        try:
            sessions = []
            
            # 从Redis获取用户会话列表
            pattern = self._build_session_key("*")
            keys = await self.redis_manager.execute_command('keys', pattern)
            
            for key in keys:
                try:
                    data = await self.redis_manager.get_json(key.replace(f"{settings.REDIS_KEY_PREFIX}:", ""))
                    if data and data.get('user_id') == user_id:
                        session = UserSession.from_dict(data)
                        if not session.is_expired:
                            sessions.append(session)
                        else:
                            # 删除过期会话
                            await self._delete_session_from_redis(session.session_id)
                except Exception as e:
                    logger.debug(f"解析会话失败 {key}: {e}")
            
            return sessions
            
        except Exception as e:
            logger.error(f"❌ 获取用户会话失败 {user_id}: {e}")
            return []
    
    async def update_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """更新会话数据"""
        try:
            session = await self.get_session(session_id)
            if not session:
                return False
            
            # 更新数据
            session.data.update(data)
            session.refresh()
            
            # 保存到Redis
            await self._save_session_to_redis(session)
            
            logger.debug(f"📝 更新会话数据: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 更新会话失败 {session_id}: {e}")
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        try:
            # 从本地缓存删除
            if session_id in self.local_sessions:
                del self.local_sessions[session_id]
            
            # 从Redis删除
            await self._delete_session_from_redis(session_id)
            
            logger.info(f"🗑️ 删除会话: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 删除会话失败 {session_id}: {e}")
            return False
    
    async def delete_user_sessions(self, user_id: str) -> int:
        """删除用户的所有会话"""
        try:
            user_sessions = await self.get_user_sessions(user_id)
            deleted_count = 0
            
            for session in user_sessions:
                if await self.delete_session(session.session_id):
                    deleted_count += 1
            
            logger.info(f"🗑️ 删除用户会话: {user_id} ({deleted_count} 个)")
            return deleted_count
            
        except Exception as e:
            logger.error(f"❌ 删除用户会话失败 {user_id}: {e}")
            return 0
    
    async def refresh_session(self, session_id: str, extend_seconds: Optional[int] = None) -> bool:
        """刷新会话"""
        try:
            session = await self.get_session(session_id)
            if not session:
                return False
            
            session.refresh(extend_seconds)
            await self._save_session_to_redis(session)
            
            logger.debug(f"🔄 刷新会话: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 刷新会话失败 {session_id}: {e}")
            return False
    
    async def get_session_count(self) -> Dict[str, int]:
        """获取会话统计"""
        try:
            pattern = self._build_session_key("*")
            keys = await self.redis_manager.execute_command('keys', pattern)
            
            total_sessions = 0
            active_sessions = 0
            expired_sessions = 0
            
            for key in keys:
                try:
                    data = await self.redis_manager.get_json(key.replace(f"{settings.REDIS_KEY_PREFIX}:", ""))
                    if data:
                        session = UserSession.from_dict(data)
                        total_sessions += 1
                        if session.is_expired:
                            expired_sessions += 1
                        else:
                            active_sessions += 1
                except Exception as e:
                    logger.debug(f"统计会话失败 {key}: {e}")
            
            return {
                'total': total_sessions,
                'active': active_sessions,
                'expired': expired_sessions,
                'local_cached': len(self.local_sessions)
            }
            
        except Exception as e:
            logger.error(f"❌ 获取会话统计失败: {e}")
            return {'total': 0, 'active': 0, 'expired': 0, 'local_cached': 0}
    
    async def _save_session_to_redis(self, session: UserSession):
        """保存会话到Redis"""
        try:
            key = self._build_session_key(session.session_id)
            ttl = int((session.expires_at - datetime.now()).total_seconds())
            if ttl > 0:
                await self.redis_manager.set_json(key, session.to_dict(), ex=ttl)
            
        except Exception as e:
            logger.error(f"❌ 保存会话到Redis失败 {session.session_id}: {e}")
    
    async def _load_session_from_redis(self, session_id: str) -> Optional[UserSession]:
        """从Redis加载会话"""
        try:
            key = self._build_session_key(session_id)
            data = await self.redis_manager.get_json(key)
            if data:
                return UserSession.from_dict(data)
            return None
            
        except Exception as e:
            logger.error(f"❌ 从Redis加载会话失败 {session_id}: {e}")
            return None
    
    async def _delete_session_from_redis(self, session_id: str):
        """从Redis删除会话"""
        try:
            key = self._build_session_key(session_id)
            await self.redis_manager.delete(key)
            
        except Exception as e:
            logger.error(f"❌ 从Redis删除会话失败 {session_id}: {e}")
    
    async def _cleanup_loop(self):
        """清理循环"""
        logger.info("🧹 启动会话清理循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 会话清理循环异常: {e}", exc_info=True)
    
    async def _cleanup_expired_sessions(self):
        """清理过期会话"""
        try:
            # 清理本地过期会话
            local_expired = []
            for session_id, session in self.local_sessions.items():
                if session.is_expired:
                    local_expired.append(session_id)
            
            for session_id in local_expired:
                del self.local_sessions[session_id]
            
            # 清理Redis中的过期会话
            pattern = self._build_session_key("*")
            keys = await self.redis_manager.execute_command('keys', pattern)
            
            redis_expired = []
            for key in keys:
                try:
                    data = await self.redis_manager.get_json(key.replace(f"{settings.REDIS_KEY_PREFIX}:", ""))
                    if data:
                        session = UserSession.from_dict(data)
                        if session.is_expired:
                            redis_expired.append(session.session_id)
                except Exception as e:
                    logger.debug(f"检查会话过期失败 {key}: {e}")
            
            # 删除过期会话
            for session_id in redis_expired:
                await self._delete_session_from_redis(session_id)
            
            total_cleaned = len(local_expired) + len(redis_expired)
            if total_cleaned > 0:
                logger.info(f"🧹 清理过期会话: 本地={len(local_expired)}, Redis={len(redis_expired)}")
                
        except Exception as e:
            logger.error(f"❌ 清理过期会话失败: {e}")
    
    async def _sync_loop(self):
        """同步循环"""
        logger.info("🔄 启动会话同步循环")
        
        while self._running:
            try:
                await asyncio.sleep(self.sync_interval)
                await self._sync_local_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 会话同步循环异常: {e}", exc_info=True)
    
    async def _sync_local_sessions(self):
        """同步本地会话到Redis"""
        try:
            sync_count = 0
            for session in self.local_sessions.values():
                if not session.is_expired:
                    await self._save_session_to_redis(session)
                    sync_count += 1
            
            if sync_count > 0:
                logger.debug(f"🔄 同步 {sync_count} 个本地会话到Redis")
                
        except Exception as e:
            logger.error(f"❌ 同步本地会话失败: {e}")
    
    def _generate_session_id(self, user_id: str) -> str:
        """生成会话ID"""
        import hashlib
        timestamp = str(int(time.time() * 1000))
        raw = f"{user_id}:{timestamp}:{self.server_instance}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    
    def _build_session_key(self, session_id: str) -> str:
        """构建会话键名"""
        return f"session:{session_id}"
    
    def get_local_session_count(self) -> int:
        """获取本地会话数量"""
        return len(self.local_sessions)


# 全局会话存储实例
_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """获取会话存储实例"""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


async def initialize_session_store():
    """初始化会话存储"""
    store = get_session_store()
    await store.start()
    return store


async def shutdown_session_store():
    """关闭会话存储"""
    global _session_store
    if _session_store:
        await _session_store.stop()
        _session_store = None
