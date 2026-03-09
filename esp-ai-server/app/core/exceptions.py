"""
自定义异常类
Custom Exceptions
"""


class TomoeBaseException(Exception):
    """巴卫系统基础异常"""
    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code
        super().__init__(self.message)


# ==================== 认证相关异常 ====================

class AuthenticationError(TomoeBaseException):
    """认证失败异常"""
    pass


class InvalidCredentialsError(AuthenticationError):
    """无效的凭证"""
    pass


class UserAlreadyExistsError(AuthenticationError):
    """用户已存在"""
    pass


class UserNotFoundError(AuthenticationError):
    """用户不存在"""
    pass


class InvalidTokenError(AuthenticationError):
    """无效的Token"""
    pass


# ==================== 业务逻辑异常 ====================

class BusinessLogicError(TomoeBaseException):
    """业务逻辑异常"""
    pass


class InvalidInputError(BusinessLogicError):
    """无效的输入"""
    pass


class DataNotFoundError(BusinessLogicError):
    """数据不存在"""
    pass


class OperationFailedError(BusinessLogicError):
    """操作失败"""
    pass


# ==================== AI服务异常 ====================

class AIServiceError(TomoeBaseException):
    """AI服务异常"""
    pass


class LLMError(AIServiceError):
    """大语言模型错误"""
    pass


class ASRError(AIServiceError):
    """语音识别错误"""
    pass


class TTSError(AIServiceError):
    """语音合成错误"""
    pass


class APIKeyError(AIServiceError):
    """API密钥错误"""
    pass


# ==================== WebSocket异常 ====================

class WebSocketError(TomoeBaseException):
    """WebSocket错误"""
    pass


class ConnectionClosedError(WebSocketError):
    """连接已关闭"""
    pass


class MessageParseError(WebSocketError):
    """消息解析错误"""
    pass


# ==================== 数据存储异常 ====================

class StorageError(TomoeBaseException):
    """存储错误"""
    pass


class FileNotFoundError(StorageError):
    """文件不存在"""
    pass


class FileWriteError(StorageError):
    """文件写入错误"""
    pass


class FileReadError(StorageError):
    """文件读取错误"""
    pass


# ==================== 配置异常 ====================

class ConfigurationError(TomoeBaseException):
    """配置错误"""
    pass


class MissingConfigError(ConfigurationError):
    """缺少必要的配置"""
    pass


class InvalidConfigError(ConfigurationError):
    """无效的配置"""
    pass


# ==================== 别名（为了兼容性） ====================

# 认证异常别名
AuthException = AuthenticationError
InvalidCredentialsException = InvalidCredentialsError
UserAlreadyExistsException = UserAlreadyExistsError
UserNotFoundException = UserNotFoundError

# AI服务异常别名
ASRException = ASRError
TTSException = TTSError
LLMException = LLMError

# 业务逻辑异常别名
InvalidInputException = InvalidInputError
ChatException = BusinessLogicError
ServiceException = AIServiceError
