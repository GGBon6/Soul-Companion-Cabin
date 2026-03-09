"""
硬件设备服务器连接日志系统
Hardware Device Server Connection Logging System
专门用于记录ESP32等硬件设备的连接、通信和服务状态
"""

import logging
import sys
import json
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

from .config import settings


class DeviceLogLevel(Enum):
    """设备日志级别"""
    CONNECTION = "CONNECTION"    # 连接相关
    PROTOCOL = "PROTOCOL"       # 协议相关
    AUDIO = "AUDIO"            # 音频相关
    SERVICE = "SERVICE"        # 服务相关
    ERROR = "ERROR"            # 错误相关
    PERFORMANCE = "PERFORMANCE" # 性能相关


class DeviceLogger:
    """硬件设备专用日志管理器"""
    
    def __init__(
        self,
        device_type: str = "ESP32",
        log_dir: Optional[Path] = None,
        enable_console: bool = True,
        enable_file: bool = True,
        enable_json_log: bool = True
    ):
        """
        初始化设备日志器
        
        Args:
            device_type: 设备类型 (ESP32, Arduino等)
            log_dir: 日志目录
            enable_console: 是否启用控制台输出
            enable_file: 是否启用文件日志
            enable_json_log: 是否启用JSON格式日志
        """
        self.device_type = device_type
        self.log_dir = log_dir or Path("logs/devices")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建不同类型的日志器
        self.connection_logger = self._create_logger("connection", enable_console, enable_file)
        self.protocol_logger = self._create_logger("protocol", enable_console, enable_file)
        self.audio_logger = self._create_logger("audio", enable_console, enable_file)
        self.service_logger = self._create_logger("service", enable_console, enable_file)
        self.error_logger = self._create_logger("error", enable_console, enable_file)
        self.performance_logger = self._create_logger("performance", enable_console, enable_file)
        
        # JSON结构化日志
        if enable_json_log:
            self.json_logger = self._create_json_logger()
        else:
            self.json_logger = None
        
        # 设备连接统计
        self.connection_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "total_messages": 0,
            "audio_frames": 0,
            "errors": 0,
            "start_time": time.time()
        }
        
        # 活跃设备列表
        self.active_devices: Dict[str, Dict[str, Any]] = {}
    
    def _create_logger(self, log_type: str, enable_console: bool, enable_file: bool) -> logging.Logger:
        """创建特定类型的日志器"""
        logger_name = f"{self.device_type.lower()}_{log_type}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        
        # 避免重复添加handler
        if logger.handlers:
            return logger
        
        # 日志格式
        formatter = logging.Formatter(
            fmt=f"%(asctime)s - {self.device_type} - %(levelname)s - [%(name)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # 控制台处理器
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # 文件处理器（按日期轮转）
        if enable_file:
            try:
                log_file = self.log_dir / f"{self.device_type.lower()}_{log_type}.log"
                file_handler = TimedRotatingFileHandler(
                    filename=log_file,
                    when='midnight',
                    interval=1,
                    backupCount=7,  # 保留7天的日志
                    encoding='utf-8'
                )
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                print(f"⚠️ 无法创建{log_type}日志文件: {e}")
        
        return logger
    
    def _create_json_logger(self) -> logging.Logger:
        """创建JSON格式日志器"""
        logger = logging.getLogger(f"{self.device_type.lower()}_json")
        logger.setLevel(logging.INFO)
        
        if logger.handlers:
            return logger
        
        # JSON格式化器
        class JsonFormatter(logging.Formatter):
            def __init__(self, device_type):
                super().__init__()
                self.device_type = device_type
            
            def format(self, record):
                log_entry = {
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "device_type": self.device_type,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno
                }
                
                # 添加额外字段
                if hasattr(record, 'device_id'):
                    log_entry['device_id'] = record.device_id
                if hasattr(record, 'session_id'):
                    log_entry['session_id'] = record.session_id
                if hasattr(record, 'message_type'):
                    log_entry['message_type'] = record.message_type
                if hasattr(record, 'data_size'):
                    log_entry['data_size'] = record.data_size
                if hasattr(record, 'processing_time'):
                    log_entry['processing_time'] = record.processing_time
                
                return json.dumps(log_entry, ensure_ascii=False)
        
        # JSON文件处理器
        try:
            json_log_file = self.log_dir / f"{self.device_type.lower()}_structured.jsonl"
            json_handler = TimedRotatingFileHandler(
                filename=json_log_file,
                when='midnight',
                interval=1,
                backupCount=30,  # JSON日志保留30天
                encoding='utf-8'
            )
            json_handler.setLevel(logging.INFO)
            json_handler.setFormatter(JsonFormatter(self.device_type))
            logger.addHandler(json_handler)
        except Exception as e:
            print(f"⚠️ 无法创建JSON日志文件: {e}")
        
        return logger
    
    def log_connection(self, device_id: str, event: str, details: Dict[str, Any] = None):
        """记录连接事件"""
        details = details or {}
        message = f"🔗 [{device_id}] {event}"
        
        if details:
            detail_str = ", ".join([f"{k}={v}" for k, v in details.items()])
            message += f" - {detail_str}"
        
        self.connection_logger.info(message)
        
        # 更新统计
        if event == "连接建立":
            self.connection_stats["total_connections"] += 1
            self.connection_stats["active_connections"] += 1
            self.active_devices[device_id] = {
                "connect_time": time.time(),
                "last_activity": time.time(),
                "message_count": 0,
                "audio_frames": 0
            }
        elif event == "连接断开":
            self.connection_stats["active_connections"] = max(0, self.connection_stats["active_connections"] - 1)
            if device_id in self.active_devices:
                del self.active_devices[device_id]
        elif event == "连接失败":
            self.connection_stats["failed_connections"] += 1
        
        # JSON日志
        if self.json_logger:
            self.json_logger.info(
                f"Connection event: {event}",
                extra={
                    "device_id": device_id,
                    "event": event,
                    **details
                }
            )
    
    def log_protocol(self, device_id: str, message_type: str, data_size: int, details: Dict[str, Any] = None):
        """记录协议消息"""
        details = details or {}
        message = f"📡 [{device_id}] {message_type} - {data_size}字节"
        
        if details:
            detail_str = ", ".join([f"{k}={v}" for k, v in details.items()])
            message += f" - {detail_str}"
        
        self.protocol_logger.info(message)
        
        # 更新统计
        self.connection_stats["total_messages"] += 1
        if device_id in self.active_devices:
            self.active_devices[device_id]["message_count"] += 1
            self.active_devices[device_id]["last_activity"] = time.time()
        
        # JSON日志
        if self.json_logger:
            self.json_logger.info(
                f"Protocol message: {message_type}",
                extra={
                    "device_id": device_id,
                    "message_type": message_type,
                    "data_size": data_size,
                    **details
                }
            )
    
    def log_audio(self, device_id: str, event: str, audio_info: Dict[str, Any] = None):
        """记录音频事件"""
        audio_info = audio_info or {}
        message = f"🎵 [{device_id}] {event}"
        
        if audio_info:
            info_str = ", ".join([f"{k}={v}" for k, v in audio_info.items()])
            message += f" - {info_str}"
        
        self.audio_logger.info(message)
        
        # 更新统计
        if "音频帧" in event:
            self.connection_stats["audio_frames"] += 1
            if device_id in self.active_devices:
                self.active_devices[device_id]["audio_frames"] += 1
        
        # JSON日志
        if self.json_logger:
            self.json_logger.info(
                f"Audio event: {event}",
                extra={
                    "device_id": device_id,
                    "event": event,
                    **audio_info
                }
            )
    
    def log_service(self, service_name: str, event: str, details: Dict[str, Any] = None):
        """记录服务事件"""
        details = details or {}
        message = f"⚙️ [{service_name}] {event}"
        
        if details:
            detail_str = ", ".join([f"{k}={v}" for k, v in details.items()])
            message += f" - {detail_str}"
        
        self.service_logger.info(message)
        
        # JSON日志
        if self.json_logger:
            self.json_logger.info(
                f"Service event: {event}",
                extra={
                    "service_name": service_name,
                    "event": event,
                    **details
                }
            )
    
    def log_error(self, device_id: str, error_type: str, error_message: str, details: Dict[str, Any] = None):
        """记录错误事件"""
        details = details or {}
        message = f"❌ [{device_id}] {error_type}: {error_message}"
        
        if details:
            detail_str = ", ".join([f"{k}={v}" for k, v in details.items()])
            message += f" - {detail_str}"
        
        self.error_logger.error(message)
        
        # 更新统计
        self.connection_stats["errors"] += 1
        
        # JSON日志
        if self.json_logger:
            self.json_logger.error(
                f"Error: {error_type}",
                extra={
                    "device_id": device_id,
                    "error_type": error_type,
                    "error_message": error_message,
                    **details
                }
            )
    
    def log_performance(self, operation: str, processing_time: float, details: Dict[str, Any] = None):
        """记录性能指标"""
        details = details or {}
        message = f"⚡ {operation} - {processing_time:.3f}s"
        
        if details:
            detail_str = ", ".join([f"{k}={v}" for k, v in details.items()])
            message += f" - {detail_str}"
        
        self.performance_logger.info(message)
        
        # JSON日志
        if self.json_logger:
            self.json_logger.info(
                f"Performance: {operation}",
                extra={
                    "operation": operation,
                    "processing_time": processing_time,
                    **details
                }
            )
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        current_time = time.time()
        uptime = current_time - self.connection_stats["start_time"]
        
        return {
            **self.connection_stats,
            "uptime_seconds": uptime,
            "uptime_formatted": self._format_duration(uptime),
            "active_devices": list(self.active_devices.keys()),
            "device_details": self.active_devices.copy()
        }
    
    def get_device_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """获取特定设备信息"""
        if device_id not in self.active_devices:
            return None
        
        device_info = self.active_devices[device_id].copy()
        current_time = time.time()
        device_info["connection_duration"] = current_time - device_info["connect_time"]
        device_info["idle_time"] = current_time - device_info["last_activity"]
        
        return device_info
    
    def log_system_status(self):
        """记录系统状态"""
        stats = self.get_connection_stats()
        
        status_message = (
            f"📊 系统状态报告:\n"
            f"   运行时间: {stats['uptime_formatted']}\n"
            f"   总连接数: {stats['total_connections']}\n"
            f"   活跃连接: {stats['active_connections']}\n"
            f"   失败连接: {stats['failed_connections']}\n"
            f"   总消息数: {stats['total_messages']}\n"
            f"   音频帧数: {stats['audio_frames']}\n"
            f"   错误数量: {stats['errors']}\n"
            f"   活跃设备: {', '.join(stats['active_devices']) if stats['active_devices'] else '无'}"
        )
        
        self.service_logger.info(status_message)
        
        # JSON日志
        if self.json_logger:
            self.json_logger.info(
                "System status report",
                extra=stats
            )
    
    def _format_duration(self, seconds: float) -> str:
        """格式化时间长度"""
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}分钟"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}小时"
    
    def cleanup_inactive_devices(self, timeout_seconds: int = 300):
        """清理非活跃设备"""
        current_time = time.time()
        inactive_devices = []
        
        for device_id, device_info in self.active_devices.items():
            if current_time - device_info["last_activity"] > timeout_seconds:
                inactive_devices.append(device_id)
        
        for device_id in inactive_devices:
            self.log_connection(device_id, "超时清理", {"timeout": timeout_seconds})
            del self.active_devices[device_id]
            self.connection_stats["active_connections"] -= 1


# 全局设备日志实例
esp32_logger = DeviceLogger(device_type="ESP32")


# 便捷函数
def log_esp32_connection(device_id: str, event: str, details: Dict[str, Any] = None):
    """记录ESP32连接事件"""
    esp32_logger.log_connection(device_id, event, details)


def log_esp32_protocol(device_id: str, message_type: str, data_size: int, details: Dict[str, Any] = None):
    """记录ESP32协议消息"""
    esp32_logger.log_protocol(device_id, message_type, data_size, details)


def log_esp32_audio(device_id: str, event: str, audio_info: Dict[str, Any] = None):
    """记录ESP32音频事件"""
    esp32_logger.log_audio(device_id, event, audio_info)


def log_esp32_service(service_name: str, event: str, details: Dict[str, Any] = None):
    """记录ESP32服务事件"""
    esp32_logger.log_service(service_name, event, details)


def log_esp32_error(device_id: str, error_type: str, error_message: str, details: Dict[str, Any] = None):
    """记录ESP32错误事件"""
    esp32_logger.log_error(device_id, error_type, error_message, details)


def log_esp32_performance(operation: str, processing_time: float, details: Dict[str, Any] = None):
    """记录ESP32性能指标"""
    esp32_logger.log_performance(operation, processing_time, details)


def get_esp32_stats() -> Dict[str, Any]:
    """获取ESP32连接统计"""
    return esp32_logger.get_connection_stats()


def get_esp32_device_info(device_id: str) -> Optional[Dict[str, Any]]:
    """获取ESP32设备信息"""
    return esp32_logger.get_device_info(device_id)


if __name__ == "__main__":
    # 测试设备日志系统
    print("🧪 测试硬件设备日志系统")
    
    # 模拟设备连接
    log_esp32_connection("ESP32_001", "连接建立", {"ip": "192.168.1.100", "port": 8767})
    log_esp32_connection("ESP32_002", "连接建立", {"ip": "192.168.1.101", "port": 8767})
    
    # 模拟协议消息
    log_esp32_protocol("ESP32_001", "hello", 128, {"version": 2, "features": ["audio", "tts"]})
    log_esp32_protocol("ESP32_001", "audio", 1024, {"format": "opus", "sample_rate": 16000})
    
    # 模拟音频事件
    log_esp32_audio("ESP32_001", "音频帧接收", {"size": 1024, "format": "opus", "duration": 40})
    log_esp32_audio("ESP32_001", "TTS音频发送", {"size": 2048, "frames": 5})
    
    # 模拟服务事件
    log_esp32_service("ASR服务", "语音识别完成", {"text": "你好", "confidence": 0.95, "time": 1.2})
    log_esp32_service("TTS服务", "语音合成完成", {"text": "你好！", "audio_size": 2048, "time": 0.8})
    
    # 模拟错误
    log_esp32_error("ESP32_002", "协议错误", "无效的消息格式", {"message_type": "unknown"})
    
    # 模拟性能指标
    log_esp32_performance("语音识别", 1.234, {"audio_size": 1024, "text_length": 10})
    
    # 显示统计信息
    stats = get_esp32_stats()
    print(f"\n📊 连接统计: {stats}")
    
    # 显示设备信息
    device_info = get_esp32_device_info("ESP32_001")
    print(f"\n📱 设备信息: {device_info}")
    
    # 系统状态报告
    esp32_logger.log_system_status()
    
    print("\n✅ 设备日志系统测试完成")
