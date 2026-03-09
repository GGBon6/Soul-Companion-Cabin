"""
自动重连管理器
Auto Reconnect Manager
为客户端提供自动重连功能和重连策略
"""

import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass, field
from enum import Enum
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from app.core import logger
from app.core.config import settings


class ReconnectState(Enum):
    """重连状态"""
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class ReconnectConfig:
    """重连配置"""
    enabled: bool = True
    max_attempts: int = settings.MAX_RECONNECT_ATTEMPTS
    initial_interval: float = settings.RECONNECT_INTERVAL
    backoff_factor: float = settings.RECONNECT_BACKOFF_FACTOR
    max_interval: float = 300.0  # 最大重连间隔5分钟
    timeout: float = 30.0  # 连接超时
    
    def get_next_interval(self, attempt: int) -> float:
        """计算下次重连间隔"""
        interval = self.initial_interval * (self.backoff_factor ** attempt)
        return min(interval, self.max_interval)


@dataclass
class ReconnectSession:
    """重连会话"""
    session_id: str
    websocket_url: str
    user_id: Optional[str] = None
    client_type: str = "unknown"
    state: ReconnectState = ReconnectState.IDLE
    current_websocket: Optional[websockets.WebSocketCommonProtocol] = None
    
    # 重连统计
    attempt_count: int = 0
    last_attempt: Optional[datetime] = None
    last_success: Optional[datetime] = None
    total_reconnects: int = 0
    
    # 配置
    config: ReconnectConfig = field(default_factory=ReconnectConfig)
    
    # 回调函数
    on_connected: Optional[Callable] = None
    on_disconnected: Optional[Callable] = None
    on_message: Optional[Callable] = None
    on_reconnect_failed: Optional[Callable] = None
    
    # 消息队列（断线期间的消息）
    pending_messages: List[Dict[str, Any]] = field(default_factory=list)
    max_pending_messages: int = 100


class ReconnectManager:
    """自动重连管理器"""
    
    def __init__(self):
        """初始化重连管理器"""
        self.sessions: Dict[str, ReconnectSession] = {}
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        
        logger.info("🔧 自动重连管理器初始化完成")
    
    async def start(self):
        """启动重连管理器"""
        self._running = True
        logger.info("🚀 自动重连管理器已启动")
    
    async def stop(self):
        """停止重连管理器"""
        self._running = False
        
        # 取消所有重连任务
        for task in self._reconnect_tasks.values():
            if not task.done():
                task.cancel()
        
        # 等待任务完成
        if self._reconnect_tasks:
            await asyncio.gather(*self._reconnect_tasks.values(), return_exceptions=True)
        
        # 关闭所有会话
        for session in self.sessions.values():
            await self._close_session(session)
        
        self.sessions.clear()
        self._reconnect_tasks.clear()
        
        logger.info("✅ 自动重连管理器已停止")
    
    def create_session(
        self,
        session_id: str,
        websocket_url: str,
        user_id: Optional[str] = None,
        client_type: str = "unknown",
        config: Optional[ReconnectConfig] = None,
        **callbacks
    ) -> ReconnectSession:
        """创建重连会话"""
        if session_id in self.sessions:
            logger.warning(f"⚠️ 重连会话已存在: {session_id}")
            return self.sessions[session_id]
        
        session = ReconnectSession(
            session_id=session_id,
            websocket_url=websocket_url,
            user_id=user_id,
            client_type=client_type,
            config=config or ReconnectConfig()
        )
        
        # 设置回调函数
        for callback_name, callback_func in callbacks.items():
            if hasattr(session, callback_name):
                setattr(session, callback_name, callback_func)
        
        self.sessions[session_id] = session
        
        logger.info(f"✅ 创建重连会话: {session_id} -> {websocket_url}")
        return session
    
    async def connect_session(self, session_id: str) -> bool:
        """连接会话"""
        if session_id not in self.sessions:
            logger.error(f"❌ 重连会话不存在: {session_id}")
            return False
        
        session = self.sessions[session_id]
        
        if not session.config.enabled:
            logger.info(f"⏸️ 重连已禁用: {session_id}")
            return False
        
        if session.state in [ReconnectState.CONNECTING, ReconnectState.CONNECTED]:
            logger.info(f"⚠️ 会话已连接或正在连接: {session_id}")
            return True
        
        return await self._attempt_connect(session)
    
    async def disconnect_session(self, session_id: str, disable_reconnect: bool = False):
        """断开会话连接"""
        if session_id not in self.sessions:
            return
        
        session = self.sessions[session_id]
        
        if disable_reconnect:
            session.config.enabled = False
            session.state = ReconnectState.DISABLED
        
        await self._close_session(session)
        
        # 取消重连任务
        if session_id in self._reconnect_tasks:
            task = self._reconnect_tasks[session_id]
            if not task.done():
                task.cancel()
            del self._reconnect_tasks[session_id]
        
        logger.info(f"📴 会话已断开: {session_id}")
    
    def remove_session(self, session_id: str):
        """移除会话"""
        if session_id in self.sessions:
            asyncio.create_task(self.disconnect_session(session_id, disable_reconnect=True))
            del self.sessions[session_id]
            logger.info(f"🗑️ 会话已移除: {session_id}")
    
    async def send_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """发送消息到会话"""
        if session_id not in self.sessions:
            logger.error(f"❌ 会话不存在: {session_id}")
            return False
        
        session = self.sessions[session_id]
        
        # 如果连接正常，直接发送
        if session.state == ReconnectState.CONNECTED and session.current_websocket:
            try:
                await session.current_websocket.send(json.dumps(message, ensure_ascii=False))
                return True
            except Exception as e:
                logger.warning(f"⚠️ 发送消息失败: {e}")
                # 连接可能已断开，触发重连
                asyncio.create_task(self._handle_connection_lost(session))
        
        # 连接断开时，将消息加入待发送队列
        if len(session.pending_messages) < session.max_pending_messages:
            session.pending_messages.append(message)
            logger.debug(f"📝 消息已加入待发送队列: {session_id}")
        else:
            logger.warning(f"⚠️ 待发送队列已满，丢弃消息: {session_id}")
        
        return False
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态"""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        return {
            "session_id": session_id,
            "state": session.state.value,
            "websocket_url": session.websocket_url,
            "user_id": session.user_id,
            "client_type": session.client_type,
            "attempt_count": session.attempt_count,
            "total_reconnects": session.total_reconnects,
            "last_attempt": session.last_attempt.isoformat() if session.last_attempt else None,
            "last_success": session.last_success.isoformat() if session.last_success else None,
            "pending_messages": len(session.pending_messages),
            "config_enabled": session.config.enabled
        }
    
    def get_all_sessions_status(self) -> List[Dict[str, Any]]:
        """获取所有会话状态"""
        return [self.get_session_status(sid) for sid in self.sessions.keys()]
    
    async def _attempt_connect(self, session: ReconnectSession) -> bool:
        """尝试连接"""
        session.state = ReconnectState.CONNECTING
        session.attempt_count += 1
        session.last_attempt = datetime.now()
        
        logger.info(f"🔌 尝试连接 ({session.attempt_count}/{session.config.max_attempts}): {session.session_id}")
        
        try:
            # 建立WebSocket连接
            websocket = await asyncio.wait_for(
                websockets.connect(
                    session.websocket_url,
                    ping_interval=settings.PING_INTERVAL,
                    ping_timeout=settings.PONG_TIMEOUT,
                    close_timeout=10
                ),
                timeout=session.config.timeout
            )
            
            session.current_websocket = websocket
            session.state = ReconnectState.CONNECTED
            session.last_success = datetime.now()
            session.attempt_count = 0  # 重置尝试计数
            
            logger.info(f"✅ 连接成功: {session.session_id}")
            
            # 触发连接成功回调
            if session.on_connected:
                try:
                    await session.on_connected(session)
                except Exception as e:
                    logger.error(f"❌ 连接回调异常: {e}", exc_info=True)
            
            # 发送待发送的消息
            await self._send_pending_messages(session)
            
            # 启动消息监听
            asyncio.create_task(self._message_listener(session))
            
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ 连接超时: {session.session_id}")
        except Exception as e:
            logger.warning(f"⚠️ 连接失败: {session.session_id} - {e}")
        
        session.state = ReconnectState.FAILED
        
        # 如果还有重连次数，启动重连
        if session.attempt_count < session.config.max_attempts and session.config.enabled:
            await self._schedule_reconnect(session)
        else:
            logger.error(f"❌ 重连失败，已达到最大尝试次数: {session.session_id}")
            session.state = ReconnectState.FAILED
            
            # 触发重连失败回调
            if session.on_reconnect_failed:
                try:
                    await session.on_reconnect_failed(session)
                except Exception as e:
                    logger.error(f"❌ 重连失败回调异常: {e}", exc_info=True)
        
        return False
    
    async def _schedule_reconnect(self, session: ReconnectSession):
        """安排重连"""
        if not self._running or not session.config.enabled:
            return
        
        interval = session.config.get_next_interval(session.attempt_count - 1)
        session.state = ReconnectState.RECONNECTING
        
        logger.info(f"⏰ 安排重连: {session.session_id} (间隔: {interval:.1f}秒)")
        
        # 取消之前的重连任务
        if session.session_id in self._reconnect_tasks:
            old_task = self._reconnect_tasks[session.session_id]
            if not old_task.done():
                old_task.cancel()
        
        # 创建新的重连任务
        self._reconnect_tasks[session.session_id] = asyncio.create_task(
            self._reconnect_after_delay(session, interval)
        )
    
    async def _reconnect_after_delay(self, session: ReconnectSession, delay: float):
        """延迟后重连"""
        try:
            await asyncio.sleep(delay)
            if session.config.enabled and self._running:
                await self._attempt_connect(session)
        except asyncio.CancelledError:
            logger.debug(f"重连任务被取消: {session.session_id}")
        except Exception as e:
            logger.error(f"❌ 重连任务异常: {e}", exc_info=True)
        finally:
            # 清理任务引用
            if session.session_id in self._reconnect_tasks:
                del self._reconnect_tasks[session.session_id]
    
    async def _message_listener(self, session: ReconnectSession):
        """消息监听器"""
        logger.debug(f"👂 启动消息监听: {session.session_id}")
        
        try:
            async for message in session.current_websocket:
                if not self._running:
                    break
                
                try:
                    data = json.loads(message)
                    
                    # 处理pong消息
                    if data.get("type") == "pong":
                        logger.debug(f"📡 收到pong: {session.session_id}")
                        continue
                    
                    # 触发消息回调
                    if session.on_message:
                        await session.on_message(session, data)
                        
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ 无效JSON消息: {session.session_id}")
                except Exception as e:
                    logger.error(f"❌ 消息处理异常: {e}", exc_info=True)
                    
        except ConnectionClosed:
            logger.info(f"📴 连接已关闭: {session.session_id}")
        except Exception as e:
            logger.warning(f"⚠️ 消息监听异常: {e}")
        finally:
            await self._handle_connection_lost(session)
    
    async def _handle_connection_lost(self, session: ReconnectSession):
        """处理连接丢失"""
        if session.state == ReconnectState.DISCONNECTED:
            return  # 已经处理过了
        
        logger.info(f"📴 连接丢失: {session.session_id}")
        
        session.state = ReconnectState.DISCONNECTED
        session.current_websocket = None
        session.total_reconnects += 1
        
        # 触发断开连接回调
        if session.on_disconnected:
            try:
                await session.on_disconnected(session)
            except Exception as e:
                logger.error(f"❌ 断开连接回调异常: {e}", exc_info=True)
        
        # 如果启用了自动重连，开始重连
        if session.config.enabled and self._running:
            session.attempt_count = 0  # 重置计数器
            await self._schedule_reconnect(session)
    
    async def _send_pending_messages(self, session: ReconnectSession):
        """发送待发送的消息"""
        if not session.pending_messages:
            return
        
        logger.info(f"📤 发送待发送消息: {session.session_id} ({len(session.pending_messages)} 条)")
        
        sent_count = 0
        failed_messages = []
        
        for message in session.pending_messages:
            try:
                await session.current_websocket.send(json.dumps(message, ensure_ascii=False))
                sent_count += 1
            except Exception as e:
                logger.warning(f"⚠️ 发送待发送消息失败: {e}")
                failed_messages.append(message)
        
        # 保留发送失败的消息
        session.pending_messages = failed_messages
        
        logger.info(f"📤 待发送消息处理完成: {sent_count} 成功, {len(failed_messages)} 失败")
    
    async def _close_session(self, session: ReconnectSession):
        """关闭会话连接"""
        if session.current_websocket:
            try:
                await session.current_websocket.close()
            except Exception as e:
                logger.debug(f"关闭连接异常: {e}")
            finally:
                session.current_websocket = None
        
        session.state = ReconnectState.DISCONNECTED


# 全局重连管理器实例
_reconnect_manager: Optional[ReconnectManager] = None


def get_reconnect_manager() -> ReconnectManager:
    """获取重连管理器实例"""
    global _reconnect_manager
    if _reconnect_manager is None:
        _reconnect_manager = ReconnectManager()
    return _reconnect_manager


async def initialize_reconnect_manager():
    """初始化重连管理器"""
    manager = get_reconnect_manager()
    await manager.start()
    return manager


async def shutdown_reconnect_manager():
    """关闭重连管理器"""
    global _reconnect_manager
    if _reconnect_manager:
        await _reconnect_manager.stop()
        _reconnect_manager = None
