# ESP32设备模块

ESP32设备专用模块，提供完整的设备连接、协议处理和对话管理功能。

## 🏗️ 架构设计

### 模块结构
```
app/devices/
├── __init__.py              # 模块导出
├── esp32_adapter.py         # ESP32协议适配器（重构版）
├── esp32_protocol.py        # ESP32协议处理模块
├── esp32_chat_service.py    # ESP32专用对话服务
└── README.md               # 本文档
```

### 核心组件

#### 1. ESP32Adapter (esp32_adapter.py)
- **功能**：ESP32设备连接和消息处理的主入口
- **特性**：
  - ✅ 基于Agent架构的对话管理
  - ✅ 完整的WebSocket连接处理
  - ✅ 音频数据的接收和发送
  - ✅ 错误处理和资源清理

#### 2. ESP32Protocol (esp32_protocol.py)
- **功能**：ESP32协议解析和音频编解码
- **特性**：
  - ✅ 支持协议版本2和3
  - ✅ Opus音频编解码
  - ✅ 二进制协议解析
  - ✅ 音频格式转换

#### 3. ESP32ChatService (esp32_chat_service.py)
- **功能**：基于ChatAgent的对话服务
- **特性**：
  - ✅ 集成ChatAgent架构
  - ✅ 持久化保存对话历史
  - ✅ 记忆管理和个性化
  - ✅ 设备会话管理

## 🔧 核心改进

### 解决的问题
1. **❌ 原问题**：对话只保存在内存中，设备断开后丢失
2. **✅ 新方案**：使用`chat_history_service.save_message()`持久化保存

3. **❌ 原问题**：直接调用LLM服务，缺少高级功能
4. **✅ 新方案**：基于ChatAgent架构，支持记忆管理、情绪分析等

5. **❌ 原问题**：代码耦合度高，难以维护
6. **✅ 新方案**：模块化设计，职责分离

### 技术特性

#### 持久化保存
```python
# 保存用户消息
await self.chat_history_service.save_message(
    user_id=user_id,
    session_id=session_id,
    role="user",
    content=text,
    message_type="text"
)

# 保存助手回复
await self.chat_history_service.save_message(
    user_id=user_id,
    session_id=session_id,
    role="assistant", 
    content=response,
    message_type="text"
)
```

#### ChatAgent集成
```python
# 创建设备专用的ChatAgent
self.device_agents[device_id] = ChatAgent(
    user_id=user_id,
    config=self.agent_config
)

# 使用Agent处理消息
response = await agent.process_message(text)
```

#### 模块化协议处理
```python
# 解析音频数据
parsed_data = self.protocol.parse_audio_data(audio_data, protocol_version)

# 解码音频
pcm_data = self.protocol.decode_opus_audio(device_id, opus_data, frame_size, sample_rate)

# 编码音频
opus_data = self.protocol.encode_pcm_to_opus(device_id, pcm_data, frame_size, sample_rate)
```

## 🚀 使用方法

### 基本使用
```python
from app.devices import get_esp32_adapter

# 获取适配器实例
adapter = get_esp32_adapter()

# 处理设备连接
await adapter.handle_esp32_connection(websocket, device_id, client_id)
```

### 获取设备统计
```python
stats = adapter.get_device_stats()
print(f"连接设备数: {stats['connected_devices']}")
print(f"设备列表: {stats['device_list']}")
```

### 获取对话历史
```python
from app.devices import get_esp32_chat_service

chat_service = get_esp32_chat_service()
history = await chat_service.get_conversation_history(device_id, limit=20)
```

## 📋 配置文件

配置文件位置：`config/esp32_config.yaml`

### 主要配置项
- **连接配置**：超时时间、最大设备数
- **音频配置**：采样率、帧时长、Opus参数
- **对话配置**：ChatAgent开关、记忆管理
- **性能配置**：缓冲区大小、并发限制
- **安全配置**：设备验证、速率限制

## 🔄 向后兼容

原有的`app/handlers/esp32_adapter.py`已重构为兼容性包装器：

```python
# 自动重定向到新模块
from app.devices.esp32_adapter import ESP32Adapter, get_esp32_adapter
```

现有代码无需修改，自动使用新的架构。

## 🛠️ 开发指南

### 添加新功能
1. 在相应模块中添加方法
2. 更新配置文件（如需要）
3. 添加单元测试
4. 更新文档

### 调试技巧
1. 查看日志：`logger.info/debug/error`
2. 检查设备状态：`adapter.get_device_stats()`
3. 验证对话历史：`chat_service.get_conversation_history()`

### 性能优化
1. 调整音频缓冲区大小
2. 优化Opus编解码参数
3. 控制并发处理数量
4. 定期清理资源

## 📊 监控指标

### 关键指标
- 连接设备数量
- 音频处理延迟
- 对话响应时间
- 内存使用情况
- 错误率统计

### 日志级别
- **INFO**：设备连接/断开、对话处理
- **DEBUG**：音频数据、协议解析
- **ERROR**：异常情况、失败处理
- **WARNING**：性能问题、资源不足

## 🔮 未来规划

### 计划功能
- [ ] 设备状态监控面板
- [ ] 音频质量分析
- [ ] 多设备会话同步
- [ ] 设备固件更新支持
- [ ] 高级音频处理算法

### 性能优化
- [ ] 音频流式处理
- [ ] 智能缓存策略
- [ ] 负载均衡支持
- [ ] 集群部署方案
