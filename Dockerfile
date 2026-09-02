# 呼吸机心智系统 - 生产镜像（Python 3.12，单容器直绑 80）
FROM python:3.12-slim

# 系统工具：curl 用于健康检查
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) 先装依赖（利用 Docker 缓存，改代码不重装 pip）
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 2) 复制后端、前端、数据、env 模板
COPY backend/      backend/
COPY frontend/     frontend/
COPY data/         data/
COPY .env.example  .env.example

# 3) 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost/api/health || exit 1

EXPOSE 80
WORKDIR /app/backend

# 容器内以 root 绑 80（host 网络下端口直通到宿主机 118.25.50.63）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "2"]
