# GUV Analysis 部署指南

## 1. 环境准备 (Linux Server)
确保服务器已安装：
- Python 3.9+
- Node.js 18+
- Redis (用于 Celery 消息队列)
- PostgreSQL (数据库)
- MinIO (对象存储，或使用 Docker 部署)

## 2. 后端设置 (Backend)

```bash
cd backend

# 1. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
# 创建 .env 文件并修改路径配置
cp .env.example .env  # 如果没有 .env.example，请手动创建 .env
nano .env
```

**关键配置 (.env) 修改建议：**
由于原代码中有硬编码的 Windows 路径，您必须在 `.env` 中覆盖它们：
```ini
PIPELINE_ROOT=/path/to/server/GUV_Analysis_V1.1.2
RUN_BASE_DIR=/path/to/server/data/tasks
POSTGRES_SERVER=localhost
REDIS_HOST=localhost
MINIO_ENDPOINT=localhost:9000
```

**启动后端：**
```bash
# 开发模式
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 生产模式 (建议使用 Gunicorn + UvicornWorkers)
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

**启动 Celery Worker：**
```bash
# Linux 下不需要 -P solo
celery -A app.worker.celery_app worker --loglevel=info --logfile=celery.log
```

## 3. 前端设置 (Frontend)

```bash
cd frontend

# 1. 安装依赖
npm install

# 2. 构建生产环境代码
npm run build
```

构建完成后，生成的 `dist` 目录即为静态资源。建议使用 **Nginx** 进行托管。

**Nginx 配置示例：**
```nginx
server {
    listen 80;
    server_name your_server_ip;

    location / {
        root /path/to/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```