"""
日志系统
Logging System
支持文件日志、控制台日志、日志轮转
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import settings


class Logger:
    """日志管理类"""
    
    def __init__(
        self,
        name: str = "tomoe-chat",
        level: Optional[str] = None,
        log_file: Optional[Path] = None,
    ):
        """
        初始化日志器
        
        Args:
            name: 日志器名称
            level: 日志级别
            log_file: 日志文件路径
        """
        self.name = name
        self.level = level or settings.LOG_LEVEL
        self.log_file = log_file or settings.get_log_file_path()
        
        # 创建日志器
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self._get_log_level())
        
        # 避免重复添加handler
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _get_log_level(self) -> int:
        """获取日志级别"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(self.level.upper(), logging.INFO)
    
    def _setup_handlers(self):
        """设置日志处理器"""
        # 日志格式
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # 控制台处理器（设置UTF-8编码以支持emoji）
        # 在Windows上重新配置stdout以使用UTF-8
        if sys.platform == 'win32':
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self._get_log_level())
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 文件处理器（支持日志轮转）
        try:
            file_handler = RotatingFileHandler(
                filename=self.log_file,
                maxBytes=settings.LOG_MAX_BYTES,
                backupCount=settings.LOG_BACKUP_COUNT,
                encoding="utf-8"
            )
            file_handler.setLevel(self._get_log_level())
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except Exception as e:
            self.logger.warning(f"无法创建文件日志处理器: {e}")
    
    def debug(self, message: str, *args, **kwargs):
        """调试日志"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """信息日志"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """警告日志"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """错误日志"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """严重错误日志"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """异常日志（包含堆栈跟踪）"""
        self.logger.exception(message, *args, **kwargs)


# 全局日志实例
logger = Logger()


# 便捷函数
def debug(message: str, *args, **kwargs):
    """调试日志"""
    logger.debug(message, *args, **kwargs)


def info(message: str, *args, **kwargs):
    """信息日志"""
    logger.info(message, *args, **kwargs)


def warning(message: str, *args, **kwargs):
    """警告日志"""
    logger.warning(message, *args, **kwargs)


def error(message: str, *args, **kwargs):
    """错误日志"""
    logger.error(message, *args, **kwargs)


def critical(message: str, *args, **kwargs):
    """严重错误日志"""
    logger.critical(message, *args, **kwargs)


def exception(message: str, *args, **kwargs):
    """异常日志（包含堆栈跟踪）"""
    logger.exception(message, *args, **kwargs)


if __name__ == "__main__":
    # 测试日志系统
    logger.debug("这是一条调试消息")
    logger.info("这是一条信息消息")
    logger.warning("这是一条警告消息")
    logger.error("这是一条错误消息")
    logger.critical("这是一条严重错误消息")
    
    try:
        1 / 0
    except Exception:
        logger.exception("这是一条异常消息")

