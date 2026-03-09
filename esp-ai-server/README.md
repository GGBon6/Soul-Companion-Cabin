# 💙 心灵小屋 - 网页端 (Soul Companion Cabin - Web Frontend)

<div align="center">

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Javascript](https://img.shields.io/badge/javascript-vanilla-yellow.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

**青少年心理健康对话系统的官方网页客户端**

[快速开始](#🚀-快速开始) • [核心功能](#✨-核心功能) • [技术架构](#🏗️-技术架构) • [开发指南](#🛠️-开发指南)

</div>

---

## 📖 项目简介

**心灵小屋 - 网页端** 是配套“心灵小屋”AI 服务端的沉浸式 Web 交互界面。通过简洁、温馨的设计语言，为青少年提供一个私密、安全的心理倾诉空间。该前端采用原生 JavaScript (Vanilla JS) 开发，无需复杂的库依赖，轻量且高效，支持实时语音对话、情绪看板及多样化的心理陪伴功能。

---

## ✨ 核心功能

- 🎙️ **实时语音对话**：基于 Web Audio API 和 WebSockets，实现高效的音频流式传输。
- 💬 **沉浸式聊天体验**：温馨的 UI 设计，支持多种 AI 角色切换（小暖、小橙、小树等）。
- 🔒 **隐私保护**：支持游客模式与加密登录，本地化存储对话偏好。
- 📊 **青少年专属功能**：内置情绪监控、心理引导及青少年特化交互逻辑。
- 🎨 **响应式设计**：完美适配桌面浏览器，提供丝滑的视觉过渡效果。

---

## 🏗️ 技术架构

- **核心语言**：原生 HTML5 + CSS3 (现代 CSS 特性) + ES6 JavaScript。
- **通信协议**：WebSocket 实现全双工实时通信（支持重连机制与心跳检测）。
- **音频处理**：使用 MediaRecorder 与 Web Audio API 进行音频采集，搭配服务端进行 Opus 编解码。
- **模块化设计**：逻辑划分为 `auth` (鉴权)、`chat` (聊天控制)、`audio` (音频流) 和 `teen-features` (业务特化) 等独立模块。

---

## 🚀 快速开始

### 1. 基础配置

在 `/frontend/config.js` 中配置您的服务端地址：

```javascript
// config.js
const CONFIG = {
    WEBSOCKET: {
        // 修改为您的 esp-ai-server 运行地址
        URL: 'ws://your-server-ip:8766', 
        RECONNECT_ATTEMPTS: 5
    },
    // ... 其他配置项
};
```

### 2. 运行项目

由于本项目采用现代浏览器原生支持的模块化 JS，您只需使用任何静态服务器启动 `frontend` 文件夹即可。

**方式一：VS Code 插件 (推荐)**
- 使用 `Live Server` 插件在 `index.html` 上右键点击 "Open with Live Server"。

**方式二：Python HTTP Server**
```bash
cd frontend
python -m http.server 8000
```
启动后访问 `http://localhost:8000/public/` 即可进入欢迎页面。

---

## 📁 目录结构

```text
esp-ai-frontend/
├── frontend/
│   ├── public/             # 页面入口 (index.html, chat.html, login.html)
│   ├── src/
│   │   ├── css/            # 样式文件 (main.css, chat.css)
│   │   ├── js/             # 核心逻辑
│   │   │   ├── audio.js    # 音频采集与播放处理
│   │   │   ├── chat.js     # 聊天会话逻辑控制
│   │   │   ├── auth.js     # 用户登录与存储管理
│   │   │   └── teen-features.js # 青少年专项业务逻辑
│   │   └── assets/         # 静态资源 (图片、图标等)
│   └── config.js           # 全局前端配置项
└── node_modules/           # (可选) 开发辅助工具
```

---

## 🛠️ 开发指南

- **样式修改**：主要全局变量定义在 `main.css` 顶部的 `:root` 节点中（如主题色、边距等）。
- **增加角色**：在服务端增加新角色后，前端会自动根据 WebSocket 消息中的 `role` 字段进行适配。
- **音频调试**：开启 `config.js` 中的 `DEBUG: true` 可以在控制台查看到详细的音频包发送频率日志。

---

## 📄 许可证

本项目基于 [MIT](LICENSE) 许可证发布。

---

<div align="center">

**💙 每一个青少年的心理健康都值得被诚实对待。**

Made with ❤️ for Youth Mental Health

</div>
