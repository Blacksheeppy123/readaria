# ========== 阶段 1: 构建依赖 ==========
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

# ========== 阶段 2: 运行时镜像 ==========
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
COPY --chown=jasmine:jasmine core core
COPY --chown=jasmine:jasmine manage.py manage.py

# 切换到非 root 用户
USER jasmine

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

EXPOSE 8000

CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

