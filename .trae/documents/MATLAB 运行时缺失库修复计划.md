# 解决 MATLAB 运行时缺失系统依赖问题

## 问题分析

根据报错信息 `error while loading shared libraries: libgdk_pixbuf-2.0.so.0` 和 `libXt.so.6: cannot open shared object file`，可以确定问题的根本原因是：
**Celery Worker 容器基于** **`python:3.10-slim`** **最小化镜像构建，缺少 MATLAB 运行所需的图形界面支持库（GDK, X11, Xt 等）。**
虽然我们使用 `-nodisplay` 模式运行，但 MATLAB 的部分内部组件（如 ServiceHost 和 Graphics UI 加载器）在启动时仍会检查或动态链接这些基础库。

## 实施计划

### 1. 修改 Dockerfile 添加系统依赖

我们将更新 `/home/guv_Analysis/GUV_Analysis_APP/GUV_Analysis/backend/Dockerfile`，在安装 Python 依赖前添加系统库的安装命令。
需要安装的库包括：

* `libgdk-pixbuf2.0-0` (解决 libgdk\_pixbuf-2.0.so.0)

* `libxt6` (解决 libXt.so.6)

* `libxext6`, `libx11-6`, `libgl1-mesa-glx`, `libglib2.0-0` (常见的 MATLAB 关联依赖，预防性安装)

**修改预览：**

```dockerfile
# ...
WORKDIR /app

# 新增：安装 MATLAB 所需的系统库
RUN apt-get update && apt-get install -y \
    libgdk-pixbuf2.0-0 \
    libxt6 \
    libxext6 \
    libx11-6 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖
COPY requirements.txt .
# ...
```

### 2. 重建镜像并重启服务

由于修改了 Dockerfile，必须重新构建镜像才能生效。

```bash
cd /home/guv_Analysis/GUV_Analysis_APP/GUV_Analysis/backend
docker compose up -d --build backend celery_worker
```

### 3. 验证修复

* 在 Celery Worker 容器内检查库是否已安装。

* 重新提交一个 Debug 任务，观察日志是否不再报错并正常启动 MATLAB 进程。

