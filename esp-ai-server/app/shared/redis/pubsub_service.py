"""
发布订阅服务
Publish-Subscribe Service
提供跨实例消息传递、事件通知和实时同步功能
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Set
from dataclasses import dataclass
from enum import Enum
import redis.asyncio as redis

from app.core import logger, settings
from .redis_manager import get_redis_manager


class MessageType(Enum):
    """消息类型"""
    USER_STATUS_CHANGE = "user_status_change"
    CONNECTION_EVENT = "connection_event"
    BROADCAST_MESSAGE = "broadcast_message"
    SYSTEM_NOTIFICATION = "system_notification"
    INSTANCE_EVENT = "instance_event"
    CUSTOM = "custom"


@dataclass
class PubSubMessage:
    """发布订阅消息"""
    type: MessageType
    source_instance: str
    target: Optional[str] = None  # 目标实例ID，None表示广播
    payload: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.payload is None:
            self.payload = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'type': self.type.value,
            'source_instance': self.source_instance,
            'target': self.target,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PubSubMessage':
        """从字典创建"""
        if 'type' in data:
            data['type'] = MessageType(data['type'])
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class PubSubService:
    """发布订阅服务"""
    
    def __init__(self):
        """初始化发布订阅服务"""
        self.redis_manager = get_redis_manager()
        self.instance_id = f"server_{int(time.time())}_{id(self)}"
        
        # 订阅管理
        self.subscriptions: Dict[str, Set[Callable]] = {}
        self.pubsub: Optional[redis.client.PubSub] = None
        
        # 后台任务
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 频道配置
        self.channels = {
            'broadcast': f"{settings.REDIS_KEY_PREFIX}:broadcast",
            'instance': f"{settings.REDIS_KEY_PREFIX}:instance:{self.instance_id}",
            'system': f"{settings.REDIS_KEY_PREFIX}:system",
            'user_events': f"{settings.REDIS_KEY_PREFIX}:user_events",
        }
        
        # 统计
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'subscriptions_count': 0,
            'last_activity': None
        }
        
        logger.info(f"🔧 发布订阅服务初始化完成 (实例: {self.instance_id})")
    
    async def start(self):
        """启动发布订阅服务"""
        if not settings.ENABLE_REDIS_PUBSUB or not self.redis_manager.is_connected():
            logger.info("⏸️ Redis发布订阅已禁用或Redis未连接")
            return
        
        logger.info("🚀 启动发布订阅服务...")
        
        try:
            # 创建pubsub客户端
            self.pubsub = self.redis_manager.redis_client.pubsub()
            
            # 订阅默认频道
            await self._subscribe_default_channels()
            
            # 启动消息监听任务
            self._running = True
            self._listener_task = asyncio.create_task(self._message_listener())
            
            logger.info("✅ 发布订阅服务启动完成")
            
        except Exception as e:
            logger.error(f"❌ 启动发布订阅服务失败: {e}", exc_info=True)
    
    async def stop(self):
        """停止发布订阅服务"""
        logger.info("⏹️ 停止发布订阅服务...")
        
        self._running = False
        
        # 停止消息监听任务
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        # 关闭pubsub连接
        if self.pubsub:
            try:
                await self.pubsub.close()
            except Exception as e:
                logger.warning(f"⚠️ 关闭pubsub连接异常: {e}")
        
        # 清理订阅
        self.subscriptions.clear()
        
        logger.info("✅ 发布订阅服务已停止")
    
    async def publish(self, message: PubSubMessage, channel: Optional[str] = None) -> bool:
        """发布消息"""
        try:
            # 确定发布频道
            if channel is None:
                if message.target:
                    # 发送到特定实例
                    channel = f"{settings.REDIS_KEY_PREFIX}:instance:{message.target}"
                else:
                    # 广播消息
                    channel = self.channels['broadcast']
            
            # 设置源实例
            message.source_instance = self.instance_id
            
            # 发布消息
            message_data = json.dumps(message.to_dict(), ensure_ascii=False)
            result = await self.redis_manager.publish(channel, message_data)
            
            self.stats['messages_sent'] += 1
            self.stats['last_activity'] = datetime.now()
            
            logger.debug(f"📤 发布消息: {message.type.value} -> {channel} (订阅者: {result})")
            return result > 0
            
        except Exception as e:
            logger.error(f"❌ 发布消息失败: {e}", exc_info=True)
            return False
    
    async def subscribe(self, message_type: MessageType, handler: Callable[[PubSubMessage], None]):
        """订阅消息类型"""
        try:
            type_key = message_type.value
            if type_key not in self.subscriptions:
                self.subscriptions[type_key] = set()
            
            self.subscriptions[type_key].add(handler)
            self.stats['subscriptions_count'] = sum(len(handlers) for handlers in self.subscriptions.values())
            
            logger.info(f"📥 订阅消息类型: {message_type.value}")
            
        except Exception as e:
            logger.error(f"❌ 订阅消息失败: {e}")
    
    async def unsubscribe(self, message_type: MessageType, handler: Callable[[PubSubMessage], None]):
        """取消订阅"""
        try:
            type_key = message_type.value
            if type_key in self.subscriptions:
                self.subscriptions[type_key].discard(handler)
                if not self.subscriptions[type_key]:
                    del self.subscriptions[type_key]
            
            self.stats['subscriptions_count'] = sum(len(handlers) for handlers in self.subscriptions.values())
            
            logger.info(f"📤 取消订阅: {message_type.value}")
            
        except Exception as e:
            logger.error(f"❌ 取消订阅失败: {e}")
    
    async def broadcast_user_status_change(self, user_id: str, old_status: str, new_status: str):
        """广播用户状态变化"""
        message = PubSubMessage(
            type=MessageType.USER_STATUS_CHANGE,
            source_instance=self.instance_id,
            payload={
                'user_id': user_id,
                'old_status': old_status,
                'new_status': new_status
            }
        )
        await self.publish(message)
    
    async def broadcast_connection_event(self, event_type: str, user_id: str, connection_info: Dict[str, Any]):
        """广播连接事件"""
        message = PubSubMessage(
            type=MessageType.CONNECTION_EVENT,
            source_instance=self.instance_id,
            payload={
                'event_type': event_type,  # 'connected', 'disconnected'
                'user_id': user_id,
                'connection_info': connection_info
            }
        )
        await self.publish(message)
    
    async def send_to_instance(self, target_instance: str, message_type: MessageType, payload: Dict[str, Any]):
        """发送消息到特定实例"""
        message = PubSubMessage(
            type=message_type,
            source_instance=self.instance_id,
            target=target_instance,
            payload=payload
        )
        await self.publish(message)
    
    async def broadcast_system_notification(self, notification_type: str, data: Dict[str, Any]):
        """广播系统通知"""
        message = PubSubMessage(
            type=MessageType.SYSTEM_NOTIFICATION,
            source_instance=self.instance_id,
            payload={
                'notification_type': notification_type,
                'data': data
            }
        )
        await self.publish(message, self.channels['system'])
    
    async def broadcast_message_to_users(self, message_content: Dict[str, Any], exclude_instance: Optional[str] = None):
        """广播消息给用户"""
        message = PubSubMessage(
            type=MessageType.BROADCAST_MESSAGE,
            source_instance=self.instance_id,
            payload={
                'message': message_content,
                'exclude_instance': exclude_instance
            }
        )
        await self.publish(message)
    
    async def _subscribe_default_channels(self):
        """订阅默认频道"""
        try:
            # 订阅广播频道
            await self.pubsub.subscribe(self.channels['broadcast'])
            
            # 订阅实例专用频道
            await self.pubsub.subscribe(self.channels['instance'])
            
            # 订阅系统频道
            await self.pubsub.subscribe(self.channels['system'])
            
            # 订阅用户事件频道
            await self.pubsub.subscribe(self.channels['user_events'])
            
            logger.info(f"📥 订阅默认频道: {list(self.channels.keys())}")
            
        except Exception as e:
            logger.error(f"❌ 订阅默认频道失败: {e}")
    
    async def _message_listener(self):
        """消息监听器"""
        logger.info("👂 启动消息监听器")
        
        try:
            while self._running:
                try:
                    # 获取消息
                    message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message is None:
                        continue
                    
                    # 处理消息
                    await self._handle_message(message)
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"❌ 处理消息异常: {e}", exc_info=True)
                    
        except asyncio.CancelledError:
            logger.info("👂 消息监听器已取消")
        except Exception as e:
            logger.error(f"❌ 消息监听器异常: {e}", exc_info=True)
    
    async def _handle_message(self, redis_message):
        """处理接收到的消息"""
        try:
            if redis_message['type'] != 'message':
                return
            
            # 解析消息
            message_data = json.loads(redis_message['data'])
            message = PubSubMessage.from_dict(message_data)
            
            # 忽略自己发送的消息
            if message.source_instance == self.instance_id:
                return
            
            self.stats['messages_received'] += 1
            self.stats['last_activity'] = datetime.now()
            
            logger.debug(f"📨 收到消息: {message.type.value} 来自 {message.source_instance}")
            
            # 分发给订阅者
            await self._dispatch_message(message)
            
        except Exception as e:
            logger.error(f"❌ 处理消息失败: {e}", exc_info=True)
    
    async def _dispatch_message(self, message: PubSubMessage):
        """分发消息给订阅者"""
        try:
            type_key = message.type.value
            if type_key not in self.subscriptions:
                return
            
            # 调用所有订阅者
            handlers = self.subscriptions[type_key].copy()  # 复制以避免并发修改
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(message)
                    else:
                        handler(message)
                except Exception as e:
                    logger.error(f"❌ 消息处理器异常: {e}", exc_info=True)
            
            logger.debug(f"📬 分发消息给 {len(handlers)} 个处理器")
            
        except Exception as e:
            logger.error(f"❌ 分发消息失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'instance_id': self.instance_id,
            'channels': list(self.channels.keys()),
            'subscription_types': list(self.subscriptions.keys()),
            'is_running': self._running
        }
    
    def get_channels(self) -> Dict[str, str]:
        """获取频道列表"""
        return self.channels.copy()


# 全局发布订阅服务实例
_pubsub_service: Optional[PubSubService] = None


def get_pubsub_service() -> PubSubService:
    """获取发布订阅服务实例"""
    global _pubsub_service
    if _pubsub_service is None:
        _pubsub_service = PubSubService()
    return _pubsub_service


async def initialize_pubsub_service():
    """初始化发布订阅服务"""
    service = get_pubsub_service()
    await service.start()
    return service


async def shutdown_pubsub_service():
    """关闭发布订阅服务"""
    global _pubsub_service
    if _pubsub_service:
        await _pubsub_service.stop()
        _pubsub_service = None
