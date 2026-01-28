FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖（如果需要构建某些python包）
# RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# 安装 MATLAB 运行所需的系统库
RUN apt-get update && apt-get install -y \
    libgdk-pixbuf-2.0-0 \
    libxt6 \
    libxext6 \
    libx11-6 \
    libgl1 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libasound2 \
    libxinerama1 \
    libxcursor1 \
    libxrandr2 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建任务数据目录
RUN mkdir -p /app/data/tasks

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
