# 💙 心灵小屋 - 青少年心理健康对话系统
(Soul Companion Cabin - Youth Mental Health Dialogue System)

<div align="center">

![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

**基于大模型与情感计算的青少年心理伴陪伴与危机干预平台**

[快速开始](#🚀-快速开始) • [功能特性](#✨-功能特性) • [系统架构](#🏗️-系统架构) • [接入指南](#🔌-接入指南)

</div>

---

## 📖 项目简介

**心灵小屋** 是一个专为青少年设计的智能心理健康对话系统。系统不仅提供日常的陪伴与倾听，还内置了危机干预、情绪分析、记忆系统等专业心理健康辅助功能。支持多种客户端（Web、ESP32硬件设备端）接入，通过WebSocket提供低延迟的实时语音对话体验。

### 🌟 核心理念
- **专业且温暖**：提供支持性、引导性的陪伴，不作冰冷的机器回答。
- **隐私保护优先**：具备“树洞模式”设计，敏感对话全方位加密及本地化处理。
- **多端触达**：无论是在网页端还是通过ESP32智能硬件，都能随时随地获得倾听。

---

## ✨ 功能特性

### � 丰富的角色陪伴系统
内置多位个性鲜明的AI伙伴，满足不同场景下的交流需求：
- **小暖**：温暖贴心的知心大姐姐，擅长共情与倾听。
- **小橙**：活力四射的阳光小教员，带来正能量与鼓励。
- **小树**：冷静睿智的树洞倾听者，适合倾吐深藏的秘密。
- **小智**：充满智慧的全能百科，解答生活与学习上的疑惑。

### 🧠 深度情绪与心理干预引擎
- **实时意图与情绪检测**：多维度情绪检测（支持情感强度分析 1-10级）。
- **危机干预与转介系统** (Crisis Intervention)：智能识别高风险词汇（如自杀、自残意向），并触发不同的响应策略（如直接给出干预热线 `400-161-9995`、`12355` 等）。
- **个性化长期记忆** (Memory System)：记录用户的偏好与状态，实现有记忆连贯性的长期陪伴。

### 🛠️ 丰富的核心扩展玩法
- **心情签到** (Mood Check-in)
- **情绪日记** (Emotional Diary)
- **睡前故事** (Bedtime Stories)
- **知识百科注入** (Knowledge Injection)

### 💻 强大的底层支持
- **WebSocket 实时语音流**：支持 Opus 编解码，适配 ESP32 硬件端极速响应。
- **AI 核心驱动**：对接阿里云百炼（通义千问大模型）、Paraformer（实时ASR）、CosyVoice（高拟真TTS）。
- **高可用与分布式支持**：引入 Redis 集群管理、连接池控制、分布式缓存等企业级架构。

---

## 🚀 快速开始

### 环境要求

- Python 3.8 或以上版本
- 阿里云 DashScope API 密钥
- Redis 服务（推荐，如无则回退本地缓存）

### 安装与运行步骤

1. **克隆代码并进入项目**
   ```bash
   git clone https://github.com/yourusername/esp-ai-server.git
   cd esp-ai-server
   ```

2. **安装依赖环境**
   本项目依赖 `opuslib`（ESP32音频必需），部分系统可能需要前置安装环境库。
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   ```bash
   # 复制环境变量模板
   cp env.example .env
   ```
   编辑 `.env` 文件，必须填入核心 AI API Key：
   ```env
   DASHSCOPE_API_KEY=your-dashscope-api-key-here
   LLM_MODEL=qwen3-max
   ```

4. **启动服务**
   ```bash
   python main.py
   ```
   启动成功后，控制台会输出如下端口信息：
   - WebSocket 语音交互端口: `ws://0.0.0.0:8766`
   - OTA 硬件空中升级服务器: `http://0.0.0.0:8080/ota/`

---

## � 接入指南

### 1. Web 客户端接入
Web项目可以通过 WebSocket 协议实现沉浸式对话（参考项目内的 `frontend` 目录）：
```javascript
const ws = new WebSocket('ws://localhost:8766');
ws.onopen = () => {
  ws.send(JSON.stringify({ type: 'text', content: '小暖你好，我今天有点难过。' }));
};
```

### 2. ESP32 硬件设备接入
为桌面智能硬件（如屏幕音箱）赋予灵魂。
ESP32 配置指南：
- 确保硬件烧录了配套固件。
- 在配网或配置平台中，将 WebSocket 地址指向 `ws://<服务器IP>:8766`。
- OTA 固件升级地址指向 `http://<服务器IP>:8080/ota/`。

---

## 🏗️ 系统架构

```text
esp-ai-server/
├── app/                        # 核心业务逻辑
│   ├── business/               # 业务模块 (对话/日记/睡前故事)
│   ├── core/                   # 核心基座 (缓存/连接池/应用上下文)
│   ├── devices/                # 硬件设备侧协议支持 (ESP32/OTA)
│   ├── web/                    # Web端通信与HTTP支持
│   ├── prompts/                # 系统人设与知识库提示词
│   └── shared/                 # 跨模块共享服务 (音频缓存/大模型/Redis)
├── frontend/                   # Web 端界面参考代码
├── config/                     # 情绪、心理及引擎的 YAML 详细配置文件
├── docker/                     # Docker 快速部署编排方案
└── main.py                     # 启动主函数入口
```

---

## 🐳 Docker 一键部署

本项目推荐使用 Docker Compose 进行生产环境部署：

1. 确认配置好 `.env` 文件
2. 执行启动指令：
   ```bash
   docker-compose -f docker/docker-compose.yml up -d
   ```
3. 查看运行日志：
   ```bash
   docker-compose -f docker/docker-compose.yml logs -f
   ```

---

## ⚙️ 高级配置项设定
本项目的行为逻辑深度可控，配置文件均存放在 `/config` 目录下：
- `youth_psychology_config.yaml`：设定青少年意图识别阈值、危机干预关键词和专业转介热线。
- `agent_config.yaml`：配置记忆系统（写入门阀、召回策略）及底层 Agent 运转表现。

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 许可证。

## 🙏 致谢

- [阿里云大模型服务平台 (DashScope)](https://dashscope.aliyun.com/)
- 所有致力于青少年心理健康事业的开源贡献者及心理工作者。
