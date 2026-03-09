# ESP32新架构使用指南

## 概述

ESP32新架构采用模块化设计，提供了更好的可维护性、可扩展性和健壮性。本指南详细介绍了如何使用新架构的各个组件。

## 架构组件

### 1. 消息类型定义 (`message_types.py`)

定义了ESP32设备通信中使用的所有枚举类型：

```python
from app.devices.esp32.message_types import (
    ESP32MessageType,      # 消息类型
    ESP32AudioFormat,      # 音频格式
    ESP32DeviceCapability, # 设备能力
    ESP32ConnectionState   # 连接状态
)

# 使用示例
message_type = ESP32MessageType.HELLO
audio_format = ESP32AudioFormat.OPUS_16KHZ_MONO
capability = ESP32DeviceCapability.TTS
state = ESP32ConnectionState.ACTIVE
```

### 2. 消息注册表 (`message_registry.py`)

消息处理器的注册和管理中心：

```python
from app.devices.esp32 import get_esp32_message_registry

# 获取全局注册表实例
registry = get_esp32_message_registry()

# 查看支持的消息类型
supported_types = registry.get_supported_types()
print(f"支持的消息类型: {supported_types}")

# 获取特定处理器
hello_handler = registry.get_handler("hello")

# 处理消息
success = await registry.process_message(device_session, message_data)
```

### 3. 设备会话管理 (`device_session.py`)

管理单个设备的连接状态和信息：

```python
from app.devices.esp32 import ESP32DeviceSession, get_esp32_session_manager

# 创建设备会话
session = ESP32DeviceSession(
    websocket=websocket,
    device_id="esp32_001",
    client_id="client_001"
)

# 更新设备信息
device_info = {
    "version": "2.0",
    "audio_params": {
        "sample_rate": 16000,
        "frame_duration": 60,
        "format": "opus"
    },
    "capabilities": ["audio_input", "tts", "asr"]
}
session.update_device_info(device_info)

# 发送消息
message = {"type": "response", "content": "Hello"}
await session.send_message(message)

# 使用会话管理器
manager = get_esp32_session_manager()
manager.add_session(session)
retrieved_session = manager.get_session("esp32_001")
```

### 4. 基础处理器框架 (`handlers/base_handler.py`)

所有消息处理器的基类：

```python
from app.devices.esp32.handlers.base_handler import ESP32BaseHandler
from app.devices.esp32.message_types import ESP32MessageType

class CustomHandler(ESP32BaseHandler):
    @property
    def message_type(self) -> ESP32MessageType:
        return ESP32MessageType.TEXT
    
    async def handle(self, device_session, message_data):
        # 处理逻辑
        content = message_data.get("content", "")
        
        # 发送响应
        response = {"type": "response", "content": f"收到: {content}"}
        await device_session.send_message(response)
        
        return True
```

### 5. Hello消息处理器 (`handlers/hello_handler.py`)

处理设备握手和初始化：

```python
from app.devices.esp32.handlers.hello_handler import ESP32HelloHandler

# Hello处理器会自动：
# 1. 验证Hello消息格式
# 2. 更新设备信息
# 3. 设置连接状态
# 4. 发送欢迎响应
# 5. 初始化MCP协议（如果支持）
```

## 使用流程

### 1. 基本使用流程

```python
import asyncio
from app.devices.esp32 import (
    get_esp32_message_registry,
    get_esp32_session_manager,
    ESP32DeviceSession
)

async def handle_esp32_connection(websocket, device_id, client_id):
    # 1. 创建设备会话
    session = ESP32DeviceSession(
        websocket=websocket,
        device_id=device_id,
        client_id=client_id
    )
    
    # 2. 添加到会话管理器
    session_manager = get_esp32_session_manager()
    session_manager.add_session(session)
    
    # 3. 获取消息注册表
    registry = get_esp32_message_registry()
    
    try:
        # 4. 处理消息循环
        async for message in websocket:
            message_data = json.loads(message)
            success = await registry.process_message(session, message_data)
            
            if not success:
                print(f"消息处理失败: {message_data}")
                
    except Exception as e:
        print(f"连接异常: {e}")
    finally:
        # 5. 清理会话
        session_manager.remove_session(device_id)
```

### 2. 自定义处理器

```python
from app.devices.esp32.handlers.base_handler import ESP32BaseHandler
from app.devices.esp32.message_types import ESP32MessageType
from app.devices.esp32 import register_custom_handler

class MyCustomHandler(ESP32BaseHandler):
    @property
    def message_type(self) -> ESP32MessageType:
        return ESP32MessageType.TEXT  # 或自定义类型
    
    async def handle(self, device_session, message_data):
        # 自定义处理逻辑
        try:
            content = message_data.get("content", "")
            
            # 处理业务逻辑
            result = await self.process_custom_logic(content)
            
            # 发送响应
            response = {
                "type": "custom_response",
                "result": result,
                "timestamp": time.time()
            }
            
            success = await device_session.send_message(response)
            return success
            
        except Exception as e:
            self.logger.error(f"处理自定义消息失败: {e}")
            await self.send_error(device_session, "CUSTOM_ERROR", str(e))
            return False
    
    async def process_custom_logic(self, content):
        # 实现自定义业务逻辑
        return f"处理结果: {content}"

# 注册自定义处理器
custom_handler = MyCustomHandler()
register_custom_handler(custom_handler)
```

### 3. 消息验证

```python
from app.devices.esp32.handlers.base_handler import ESP32MessageValidator

# 验证Hello消息
hello_message = {"type": "hello", "version": "2.0"}
is_valid, error_msg = ESP32MessageValidator.validate_hello_message(hello_message)

if not is_valid:
    print(f"验证失败: {error_msg}")

# 验证文本消息
text_message = {"type": "text", "content": "Hello World"}
is_valid, error_msg = ESP32MessageValidator.validate_text_message(text_message)
```

## 最佳实践

### 1. 错误处理

```python
class MyHandler(ESP32BaseHandler):
    async def handle(self, device_session, message_data):
        try:
            # 验证消息格式
            if not self.validate_message(message_data):
                await self.send_error(device_session, "INVALID_FORMAT", "消息格式错误")
                return False
            
            # 处理业务逻辑
            result = await self.process_message(message_data)
            
            # 发送成功响应
            await self.send_success(device_session, result)
            return True
            
        except Exception as e:
            # 记录错误并发送错误响应
            self.logger.error(f"处理消息失败: {e}", exc_info=True)
            await self.send_error(device_session, "PROCESSING_ERROR", str(e))
            return False
```

### 2. 异步处理

```python
class AsyncHandler(ESP32BaseHandler):
    async def handle(self, device_session, message_data):
        # 对于耗时操作，使用异步处理
        task = asyncio.create_task(self.long_running_task(message_data))
        
        # 立即发送确认响应
        await device_session.send_message({
            "type": "ack",
            "message": "消息已接收，正在处理"
        })
        
        # 等待任务完成
        result = await task
        
        # 发送最终结果
        await device_session.send_message({
            "type": "result",
            "data": result
        })
        
        return True
```

### 3. 状态管理

```python
# 检查设备状态
if not device_session.is_authenticated:
    await self.send_error(device_session, "NOT_AUTHENTICATED", "设备未认证")
    return False

# 更新设备活动时间
device_session.update_activity()

# 检查设备能力
if not device_session.has_capability(ESP32DeviceCapability.TTS):
    await self.send_error(device_session, "TTS_NOT_SUPPORTED", "设备不支持TTS")
    return False
```

## 测试

### 1. 单元测试

运行完整的单元测试套件：

```bash
python tests/test_esp32_new_architecture.py
```

### 2. 集成演示

运行集成演示查看完整功能：

```bash
python examples/esp32_new_architecture_demo.py
```

## 扩展指南

### 1. 添加新的消息类型

1. 在`message_types.py`中添加新的枚举值
2. 创建对应的处理器类
3. 在消息注册表中注册处理器

### 2. 添加新的设备能力

1. 在`ESP32DeviceCapability`枚举中添加新能力
2. 在设备会话中添加相关方法
3. 在处理器中添加能力检查

### 3. 自定义验证规则

```python
class CustomValidator:
    @staticmethod
    def validate_custom_message(message_data):
        # 自定义验证逻辑
        if not message_data.get("custom_field"):
            return False, "缺少自定义字段"
        return True, "验证通过"
```

## 性能优化

### 1. 连接池管理

- 定期清理空闲连接
- 限制最大连接数
- 实现连接复用

### 2. 消息处理优化

- 异步处理耗时操作
- 批量处理消息
- 缓存常用数据

### 3. 内存管理

- 及时清理会话数据
- 限制消息缓存大小
- 监控内存使用情况

## 故障排除

### 1. 常见问题

**问题**: 消息处理器未找到
```
解决方案: 检查消息类型是否正确注册，确认处理器类名和消息类型匹配
```

**问题**: 设备会话创建失败
```
解决方案: 检查WebSocket连接是否正常，确认设备ID和客户端ID唯一
```

**问题**: 消息验证失败
```
解决方案: 检查消息格式是否符合规范，确认必需字段是否存在
```

### 2. 调试技巧

1. 启用详细日志记录
2. 使用演示程序测试功能
3. 检查设备会话状态
4. 验证消息格式

## 总结

ESP32新架构提供了：

- ✅ **模块化设计**: 清晰的组件分离和职责划分
- ✅ **可扩展性**: 易于添加新的消息类型和处理器
- ✅ **健壮性**: 完善的错误处理和状态管理
- ✅ **可测试性**: 全面的单元测试和集成测试
- ✅ **可维护性**: 清晰的代码结构和文档

通过遵循本指南，您可以有效地使用和扩展ESP32新架构，构建稳定可靠的设备通信系统。
