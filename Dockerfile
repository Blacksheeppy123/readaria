# ========== 阶段 1: 构建 Vue PWA ==========
FROM node:20-alpine AS frontend-builder

# VITE_DEMO_MODE=true 构建公开演示版前端（DemoView/BYOK 面板）；默认正常前端
ARG VITE_DEMO_MODE=false
ENV VITE_DEMO_MODE=$VITE_DEMO_MODE

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ========== 阶段 2: 构建 Python 依赖 ==========
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# 安装构建依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖到独立目录（使用生产环境依赖）
COPY requirements.prod.txt .
RUN pip install --prefix=/install -r requirements.prod.txt

# ========== 阶段 3: 运行时镜像 ==========
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 只安装运行时依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 从构建阶段复制依赖
COPY --from=builder /install /usr/local

# 创建非 root 用户和必要目录
RUN groupadd -r jasmine && \
    useradd -r -g jasmine -u 1001 jasmine && \
    mkdir -p logs audio_cache podcast_cache && \
    chown -R jasmine:jasmine /app

# 复制应用代码
COPY --chown=jasmine:jasmine backend backend
COPY --from=frontend-builder --chown=jasmine:jasmine /app/frontend/dist backend/static/web
COPY --chown=jasmine:jasmine core core
COPY --chown=jasmine:jasmine manage.py manage.py
COPY --chown=jasmine:jasmine scripts scripts

# 切换到非 root 用户
USER jasmine

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

EXPOSE 8000

CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

