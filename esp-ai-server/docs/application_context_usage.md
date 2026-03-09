# 应用上下文使用指南

## 概述

应用上下文模式是一种现代化的服务管理架构，为心理对话AI系统提供：
- ✅ **多客户端优化**：ESP32和Web端使用不同的LLM配置
- ✅ **服务池管理**：自动健康检查和实例替换
- ✅ **统一生命周期**：优雅的启动和关闭
- ✅ **向后兼容**：保留旧的API接口

## 架构图

```
Application (应用上下文)
    ├── ServicePool (LLM服务池)
    │   ├── LLMService (ESP32实例) - qwen-turbo, 500 tokens, 10并发
    │   ├── LLMService (Web实例)   - qwen-plus, 2000 tokens, 30并发
    │   └── LLMService (System实例) - qwen-plus, 1500 tokens, 5并发
    ├── CacheManager (缓存系统)
    └── Metrics (监控系统)
```

## 使用方式

### 1. 在main.py中初始化（已完成）

```python
from app.core.application import create_app, ApplicationConfig

# 创建应用
app = create_app(ApplicationConfig(
    name="心灵小屋",
    version="2.0.0",
    environment="production",
    enable_esp32=True,
    enable_web=True,
    dashscope_api_key=settings.DASHSCOPE_API_KEY
))

# 初始化
await app.initialize()

# 关闭
await app.shutdown()
```

### 2. 在业务代码中使用（推荐）

#### 方式A: 异步上下文中使用（推荐）

```python
from app.core.application import get_app

async def handle_esp32_message(message: str):
    """处理ESP32设备消息"""
    # 获取应用实例
    app = get_app()
    
    # 获取ESP32优化的LLM服务
    llm_service = await app.get_llm_service(client_type='esp32')
    
    # 调用LLM
    response = await llm_service.chat_async(
        messages=[{"role": "user", "content": message}],
        user_id="esp32_device_001"
    )
    
    return response

async def handle_web_message(message: str):
    """处理Web端消息"""
    app = get_app()
    
    # 获取Web优化的LLM服务
    llm_service = await app.get_llm_service(client_type='web')
    
    response = await llm_service.chat_async(
        messages=[{"role": "user", "content": message}],
        user_id="web_user_123"
    )
    
    return response
```

#### 方式B: 向后兼容方式（不推荐）

```python
from app.shared.services import get_llm_service

# 旧的方式仍然可用，但会使用默认配置
llm_service = get_llm_service()
response = await llm_service.chat_async(messages=[...])
```

### 3. 在WebSocket处理器中使用

```python
# app/web/handlers/websocket_handler.py

from app.core.application import get_app

class WebSocketHandler:
    async def handle_text_message(self, websocket, message, client_type='web'):
        """处理文本消息"""
        # 获取应用实例
        app = get_app()
        
        # 根据客户端类型获取优化的LLM服务
        llm_service = await app.get_llm_service(client_type)
        
        # 调用LLM
        response = await llm_service.chat_async(
            messages=[{"role": "user", "content": message}],
            user_id=websocket.user_id
        )
        
        return response
```

### 4. 在ChatAgent中使用

```python
# app/shared/agents/chat_agent.py

from app.core.application import get_app

class ChatAgent:
    async def process_chat(self, request: ChatRequest):
        """处理对话请求"""
        # 获取应用实例
        app = get_app()
        
        # 根据请求的client_type获取对应的LLM服务
        llm_service = await app.get_llm_service(request.client_type)
        
        # 调用LLM生成回复
        response = await llm_service.chat_async(
            messages=context,
            temperature=0.7,
            user_id=request.user_id
        )
        
        return response
```

## 配置说明

### LLM配置类型

#### ESP32设备配置
```python
LLMConfig.for_esp32(api_key)
- 模型: qwen-turbo (更快)
- Max Tokens: 500 (限制长度)
- 并发: 10 (低并发)
- 温度: 0.7
- 适用场景: 硬件设备，需要快速响应
```

#### Web端配置
```python
LLMConfig.for_web(api_key)
- 模型: qwen-plus (更智能)
- Max Tokens: 2000 (支持长回复)
- 并发: 30 (高并发)
- 温度: 0.8
- 适用场景: Web浏览器，需要高质量回复
```

#### 系统内部配置
```python
LLMConfig.for_system(api_key)
- 模型: qwen-plus
- Max Tokens: 1500
- 并发: 5 (中等并发)
- 温度: 0.8
- 适用场景: 后台任务（日记生成、故事生成）
```

## 监控和调试

### 获取应用统计信息

```python
from app.core.application import get_app

app = get_app()
stats = app.get_stats()

print(stats)
# {
#     'name': '心灵小屋',
#     'version': '2.0.0',
#     'environment': 'production',
#     'is_running': True,
#     'service_pools': {
#         'llm': {
#             'service_class': 'LLMService',
#             'total_instances': 3,
#             'healthy_instances': 3,
#             'client_types': ['esp32', 'web', 'system'],
#             'health_status': {
#                 'esp32': True,
#                 'web': True,
#                 'system': True
#             }
#         }
#     }
# }
```

### 获取LLM服务指标

```python
app = get_app()
llm_service = await app.get_llm_service('esp32')

metrics = llm_service.get_metrics()
print(metrics)
# {
#     'client_type': 'esp32',
#     'model': 'qwen-turbo',
#     'is_healthy': True,
#     'total_requests': 150,
#     'successful_requests': 148,
#     'failed_requests': 2,
#     'success_rate': 98.67,
#     'avg_time_ms': 850.5
# }
```

## 测试

### 单元测试示例

```python
import pytest
from app.core.application import create_app, reset_app, ApplicationConfig
from app.core.llm_config import LLMConfig

@pytest.fixture
async def app():
    """创建测试应用"""
    reset_app()  # 重置全局实例
    
    app = create_app(ApplicationConfig(
        name="测试应用",
        dashscope_api_key="test_key"
    ))
    
    await app.initialize()
    yield app
    await app.shutdown()

@pytest.mark.asyncio
async def test_get_llm_service_esp32(app):
    """测试获取ESP32 LLM服务"""
    llm_service = await app.get_llm_service('esp32')
    
    assert llm_service.model == 'qwen-turbo'
    assert llm_service.max_tokens == 500
    assert llm_service.max_concurrent == 10

@pytest.mark.asyncio
async def test_get_llm_service_web(app):
    """测试获取Web LLM服务"""
    llm_service = await app.get_llm_service('web')
    
    assert llm_service.model == 'qwen-plus'
    assert llm_service.max_tokens == 2000
    assert llm_service.max_concurrent == 30
```

## 迁移指南

### 从旧代码迁移

#### 旧代码
```python
from app.shared.services import get_llm_service

llm_service = get_llm_service()
response = await llm_service.chat_async(messages, client_type='esp32')
```

#### 新代码（推荐）
```python
from app.core.application import get_app

app = get_app()
llm_service = await app.get_llm_service('esp32')
response = await llm_service.chat_async(messages)
```

### 优势对比

| 特性 | 旧方式 | 新方式 |
|------|--------|--------|
| 配置灵活性 | ❌ 固定配置 | ✅ 多配置支持 |
| 客户端隔离 | ❌ 共享实例 | ✅ 独立实例 |
| 健康检查 | ❌ 无 | ✅ 自动检查 |
| 生命周期管理 | ❌ 混乱 | ✅ 清晰 |
| 测试友好 | ❌ 困难 | ✅ 容易 |

## 常见问题

### Q1: 如何添加新的客户端类型？

在`application.py`的`llm_config_factory`中添加新的配置：

```python
def llm_config_factory(client_type: str) -> LLMConfig:
    if client_type == 'mobile':  # 新增移动端
        return LLMConfig(
            api_key=api_key,
            model="qwen-turbo",
            max_tokens=800,
            max_concurrent=20,
            client_type='mobile'
        )
```

### Q2: 如何自定义配置？

创建自定义配置：

```python
custom_config = LLMConfig(
    api_key="your_key",
    model="qwen-max",
    max_tokens=3000,
    temperature=0.9,
    max_concurrent=50,
    client_type="custom"
)

# 手动创建服务
from app.shared.services.llm_service_v2 import LLMService
llm_service = LLMService(custom_config)
```

### Q3: 旧代码会受影响吗？

不会！旧的`get_llm_service()`仍然可用，会自动从应用上下文获取服务。

## 最佳实践

1. ✅ **优先使用应用上下文**：`await app.get_llm_service(client_type)`
2. ✅ **明确指定client_type**：让系统使用优化的配置
3. ✅ **监控服务健康**：定期检查`app.get_stats()`
4. ✅ **优雅关闭**：确保调用`await app.shutdown()`
5. ✅ **测试时重置**：使用`reset_app()`避免状态污染

## 总结

应用上下文模式为心理对话AI系统提供了：
- 🎯 **专业化**：不同客户端使用优化的配置
- 🏥 **可靠性**：自动健康检查和故障恢复
- 📊 **可观测性**：详细的监控和统计
- 🧪 **可测试性**：易于编写单元测试
- 🔄 **向后兼容**：无需修改现有代码
