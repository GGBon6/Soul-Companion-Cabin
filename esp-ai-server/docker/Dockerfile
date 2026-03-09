# 小智AI服务 - Docker镜像
# Xiaozhi AI Service - Docker Image

# 使用Python 3.11官方镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p /app/data /app/logs \
    /app/data/users \
    /app/data/chat_history \
    /app/data/user_profiles

# 设置数据目录权限
RUN chmod -R 755 /app/data /app/logs

# 暴露端口
# 8080: HTTP API和OTA服务
# 8766: WebSocket服务
EXPOSE 8080 8766

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import socket; s = socket.socket(); s.connect(('localhost', 8766)); s.close()" || exit 1

# 启动命令
CMD ["python", "main.py"]
