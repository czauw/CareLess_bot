# CareLess Bot Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip install --no-cache-dir nonebot2[fastapi]

# 复制源码
COPY src/ ./src/

# 使用非 root 用户
RUN useradd --create-home --shell /bin/bash bot
USER bot

# 启动
CMD ["python", "-m", "bot.src.bot"]
