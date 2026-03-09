# 小智AI服务 - 独立大模型服务

<div align="center">

![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

**基于WebSocket的AI对话服务，支持多种客户端接入**

[快速开始](#快速开始) • [功能特性](#功能特性) • [API文档](#api文档) • [部署指南](#部署指南)

</div>

---

## 📖 项目简介

小智AI服务是一个独立的、可扩展的AI对话服务系统，基于WebSocket协议提供实时对话能力。支持语音识别（ASR）、大模型对话（LLM）、语音合成（TTS）等核心功能，可以轻松接入ESP32设备、Web应用、移动应用和桌面应用。

### ✨ 功能特性

- 🎯 **多协议支持**
  - WebSocket实时通信
  - HTTP REST API（可选）
  - OTA固件更新（ESP32）

- 🤖 **AI核心能力**
  - 语音识别（ASR）- 支持实时语音转文字
  - 大模型对话（LLM）- 基于通义千问
  - 语音合成（TTS）- 高质量语音输出
  - 多角色对话系统

- 🔌 **多客户端支持**
  - ESP32硬件设备
  - Web浏览器应用
  - 移动端应用（iOS/Android）
  - 桌面应用

- 📝 **数据管理**
  - 对话历史记录
  - 用户配置管理
  - 音频缓存优化

- 🔒 **安全特性**
  - 用户认证系统
  - 数据加密存储
  - 隐私保护机制

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip 包管理器
- 阿里云DashScope API密钥

### 安装步骤

1. **克隆项目**
```bash
git clone https://github.com/yourusername/xiaozhi-ai-service.git
cd xiaozhi-ai-service
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置环境变量**
```bash
# 复制环境变量模板
cp env.example .env

# 编辑.env文件，填写必要的配置
# 最重要的是填写 DASHSCOPE_API_KEY
```

4. **启动服务**
```bash
python main.py
```

服务启动后，你将看到：
- WebSocket服务器：`ws://0.0.0.0:8766`
- OTA服务器：`http://0.0.0.0:8080/ota/`
- HTTP API（如果启用）：`http://0.0.0.0:8080/api/`

---

## 📋 配置说明

### 核心配置项

在 `.env` 文件中配置以下关键参数：

```bash
# 服务配置
SERVICE_NAME=小智AI服务
SERVICE_VERSION=2.0.0
SUPPORTED_CLIENTS=esp32,web,mobile,desktop

# 服务器配置
HOST=0.0.0.0
PORT=8766          # WebSocket端口
HTTP_PORT=8080     # HTTP API端口

# 功能开关
ENABLE_OTA=true
ENABLE_WEBSOCKET=true
ENABLE_HTTP_API=false

# AI服务配置
DASHSCOPE_API_KEY=your-api-key-here
LLM_MODEL=qwen-plus
TTS_MODEL=cosyvoice-v2
ASR_MODEL=paraformer-realtime-v2
```

完整配置说明请查看 [env.example](env.example)

---

## 🔌 客户端接入

### WebSocket协议

任何支持WebSocket的客户端都可以连接：

```javascript
// JavaScript示例
const ws = new WebSocket('ws://localhost:8766');

ws.onopen = () => {
  console.log('连接成功');
  // 发送消息
  ws.send(JSON.stringify({
    type: 'text',
    content: '你好'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('收到消息:', data);
};
```

```python
# Python示例
import websockets
import asyncio
import json

async def connect():
    uri = "ws://localhost:8766"
    async with websockets.connect(uri) as websocket:
        # 发送消息
        await websocket.send(json.dumps({
            'type': 'text',
            'content': '你好'
        }))
        
        # 接收消息
        response = await websocket.recv()
        print(f"收到: {response}")

asyncio.run(connect())
```

### HTTP API（可选）

启用HTTP API后，可以通过REST接口调用：

```bash
# 文本对话
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'

# 语音合成
curl -X POST http://localhost:8080/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，我是小智"}' \
  --output audio.wav

# 语音识别
curl -X POST http://localhost:8080/api/asr \
  -F "audio=@voice.wav"
```

---

## 🐳 Docker部署

### 使用Docker Compose（推荐）

1. **构建并启动**
```bash
docker-compose -f docker/docker-compose.yml up -d
```

2. **查看日志**
```bash
docker-compose -f docker/docker-compose.yml logs -f
```

3. **停止服务**
```bash
docker-compose -f docker/docker-compose.yml down
```

### 使用Dockerfile

```bash
# 构建镜像
docker build -f docker/Dockerfile -t xiaozhi-ai-service .

# 运行容器
docker run -d \
  --name xiaozhi-ai \
  -p 8080:8080 \
  -p 8766:8766 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  --env-file .env \
  xiaozhi-ai-service
```

---

## 📦 作为Python包使用

### 安装

```bash
pip install -e .
```

### 命令行启动

```bash
xiaozhi-ai
```

### 在代码中使用

```python
from app.core import settings
from app.handlers.websocket_handler import WebSocketHandler

# 创建处理器
handler = WebSocketHandler()

# 启动服务
await handler.start()
```

---

## 🏗️ 项目结构

```
xiaozhi-ai-service/
├── app/                      # 应用核心代码
│   ├── core/                 # 核心模块（配置、日志、安全）
│   ├── handlers/             # 请求处理器（WebSocket、HTTP、OTA）
│   ├── services/             # 业务服务（ASR、LLM、TTS）
│   ├── models/               # 数据模型
│   ├── agents/               # AI代理
│   └── utils/                # 工具函数
├── data/                     # 数据目录
│   ├── users/                # 用户数据
│   ├── chat_history/         # 对话历史
│   └── user_profiles/        # 用户配置
├── logs/                     # 日志目录
├── tests/                    # 测试代码
├── main.py                   # 主入口
├── requirements.txt          # 依赖列表
├── setup.py                  # 安装配置
├── Dockerfile                # Docker镜像
├── docker-compose.yml        # Docker编排
├── .env.example              # 环境变量模板
└── README.md                 # 项目文档
```

---

## 🔧 开发指南

### 运行测试

```bash
pytest tests/
```

### 代码格式化

```bash
black app/
flake8 app/
```

### 添加新功能

1. 在 `app/services/` 中添加新服务
2. 在 `app/handlers/` 中添加处理器
3. 在 `main.py` 中注册路由
4. 更新配置和文档

---

## 📊 性能优化

- ✅ 音频缓存预生成
- ✅ 异步I/O处理
- ✅ 连接池管理
- ✅ 日志轮转
- ✅ 资源自动清理

---

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

1. Fork本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 🙏 致谢

- [阿里云DashScope](https://dashscope.aliyun.com/) - AI服务提供
- [WebSockets](https://websockets.readthedocs.io/) - WebSocket库
- [aiohttp](https://docs.aiohttp.org/) - 异步HTTP框架

---

## 📮 联系方式

- 项目主页：https://github.com/yourusername/xiaozhi-ai-service
- 问题反馈：https://github.com/yourusername/xiaozhi-ai-service/issues
- 邮箱：your.email@example.com

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给一个Star！⭐**

Made with ❤️ by [Your Name]

</div>
