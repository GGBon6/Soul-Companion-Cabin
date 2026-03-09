# 项目架构重构方案

## 🎯 重构目标

将web网页服务和ESP32设备服务分类区分，同时保持大模型服务的共用。

## 📊 当前架构分析

### Web相关服务
- **WebSocket处理器**: `app/handlers/websocket_handler.py`
- **HTTP API处理器**: `app/handlers/http_api_handler.py`
- **消息处理器**: `app/handlers/message_handlers/`
- **认证处理器**: `app/handlers/auth_handlers/`
- **功能处理器**: `app/handlers/feature_handlers/`
- **前端静态文件**: `frontend/`

### ESP32设备相关服务
- **ESP32适配器**: `app/devices/esp32_adapter.py`
- **ESP32协议**: `app/devices/esp32_protocol.py`
- **ESP32对话服务**: `app/devices/esp32_chat_service.py`
- **OTA服务器**: `app/handlers/ota_server.py`

### 共享服务（大模型等）
- **LLM服务**: `app/services/llm_service.py`
- **ASR服务**: `app/services/asr_service.py`
- **TTS服务**: `app/services/tts_service.py`
- **认证服务**: `app/services/auth_service.py`
- **对话历史服务**: `app/services/chat_history_service.py`
- **音频缓存服务**: `app/services/audio_cache_service.py`

### 业务逻辑服务
- **日记服务**: `app/services/diary_service.py`
- **故事服务**: `app/services/story_service.py`
- **主动对话服务**: `app/services/proactive_chat_service.py`

## 🏗️ 新架构设计

```
esp-ai-server/
├── app/
│   ├── core/                    # 核心模块（配置、日志、异常等）
│   ├── shared/                  # 共享服务层
│   │   ├── services/           # 共享服务（LLM、ASR、TTS等）
│   │   ├── agents/             # Agent架构
│   │   ├── models/             # 数据模型
│   │   └── utils/              # 工具函数
│   ├── web/                    # Web服务模块
│   │   ├── handlers/           # Web处理器
│   │   ├── api/                # REST API
│   │   ├── websocket/          # WebSocket处理
│   │   ├── auth/               # Web认证
│   │   └── features/           # Web功能模块
│   ├── devices/                # 设备服务模块
│   │   ├── esp32/              # ESP32设备
│   │   ├── protocols/          # 设备协议
│   │   └── ota/                # OTA更新
│   └── business/               # 业务逻辑模块
│       ├── diary/              # 日记功能
│       ├── story/              # 故事功能
│       └── chat/               # 对话功能
├── frontend/                   # 前端静态文件
├── config/                     # 配置文件
├── tests/                      # 测试文件
└── docs/                       # 文档
```

## 📁 详细目录结构

### 共享服务层 (`app/shared/`)
```
app/shared/
├── __init__.py
├── services/                   # 共享服务
│   ├── __init__.py
│   ├── llm_service.py         # 大模型服务
│   ├── asr_service.py         # 语音识别服务
│   ├── tts_service.py         # 语音合成服务
│   ├── auth_service.py        # 认证服务
│   ├── chat_history_service.py # 对话历史服务
│   └── audio_cache_service.py # 音频缓存服务
├── agents/                     # Agent架构
│   ├── __init__.py
│   ├── base_agent.py          # 基础Agent
│   ├── memory_agent.py        # 记忆Agent
│   └── chat_agent.py          # 对话Agent
├── models/                     # 数据模型
│   ├── __init__.py
│   ├── user.py
│   ├── message.py
│   └── session.py
└── utils/                      # 工具函数
    ├── __init__.py
    ├── audio_utils.py
    └── text_utils.py
```

### Web服务模块 (`app/web/`)
```
app/web/
├── __init__.py
├── handlers/                   # Web处理器
│   ├── __init__.py
│   └── websocket_handler.py   # WebSocket主处理器
├── api/                        # REST API
│   ├── __init__.py
│   ├── chat_api.py            # 对话API
│   ├── user_api.py            # 用户API
│   └── health_api.py          # 健康检查API
├── websocket/                  # WebSocket处理
│   ├── __init__.py
│   ├── message_handlers.py    # 消息处理器
│   └── connection_manager.py  # 连接管理器
├── auth/                       # Web认证
│   ├── __init__.py
│   ├── login_handler.py       # 登录处理
│   ├── register_handler.py    # 注册处理
│   └── profile_handler.py     # 档案处理
└── features/                   # Web功能模块
    ├── __init__.py
    ├── character_handler.py    # 角色处理
    ├── mood_handler.py         # 情绪处理
    ├── diary_handler.py        # 日记处理
    └── story_handler.py        # 故事处理
```

### 设备服务模块 (`app/devices/`)
```
app/devices/
├── __init__.py
├── esp32/                      # ESP32设备
│   ├── __init__.py
│   ├── adapter.py             # ESP32适配器
│   ├── protocol.py            # ESP32协议
│   ├── chat_service.py        # ESP32对话服务
│   └── config.py              # ESP32配置
├── protocols/                  # 设备协议
│   ├── __init__.py
│   ├── websocket_protocol.py  # WebSocket协议
│   └── audio_protocol.py      # 音频协议
└── ota/                        # OTA更新
    ├── __init__.py
    └── ota_server.py          # OTA服务器
```

### 业务逻辑模块 (`app/business/`)
```
app/business/
├── __init__.py
├── diary/                      # 日记功能
│   ├── __init__.py
│   ├── diary_service.py       # 日记服务
│   └── diary_models.py        # 日记模型
├── story/                      # 故事功能
│   ├── __init__.py
│   ├── story_service.py       # 故事服务
│   └── story_models.py        # 故事模型
└── chat/                       # 对话功能
    ├── __init__.py
    ├── proactive_chat_service.py # 主动对话服务
    └── chat_models.py         # 对话模型
```

## 🔄 迁移策略

### 阶段1: 创建新目录结构
1. 创建新的目录结构
2. 移动共享服务到 `app/shared/services/`
3. 保持原有导入路径的兼容性

### 阶段2: 重构Web服务
1. 移动Web相关处理器到 `app/web/`
2. 重构WebSocket和HTTP API处理
3. 更新导入路径

### 阶段3: 重构设备服务
1. 移动ESP32相关代码到 `app/devices/esp32/`
2. 重构设备协议和适配器
3. 更新配置文件

### 阶段4: 重构业务逻辑
1. 移动业务服务到 `app/business/`
2. 重构服务依赖关系
3. 更新测试文件

### 阶段5: 清理和优化
1. 删除旧的目录结构
2. 更新文档和配置
3. 运行完整测试

## 🎯 重构收益

### 1. **清晰的架构分层**
- 共享服务层：提供通用功能
- Web服务层：处理网页相关请求
- 设备服务层：处理设备连接和协议
- 业务逻辑层：实现具体业务功能

### 2. **更好的代码组织**
- 按功能模块分组
- 减少跨模块依赖
- 提高代码可维护性

### 3. **便于扩展**
- 新增设备类型更容易
- Web功能模块化开发
- 业务逻辑独立演进

### 4. **测试友好**
- 模块间依赖清晰
- 便于单元测试
- 集成测试更简单

## 📋 实施计划

1. **第1周**: 创建新目录结构，移动共享服务
2. **第2周**: 重构Web服务模块
3. **第3周**: 重构设备服务模块
4. **第4周**: 重构业务逻辑模块，清理优化

每个阶段都会保持系统的正常运行，采用渐进式重构策略。
