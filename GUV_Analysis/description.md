## 1. 需求落地解读与关键约束
文档明确的目标/约束（摘取并工程化）：

+ **网络与角色**：实验室内网，多台 Windows 显微镜采集电脑 + 1 台 Linux 服务器做分析，浏览器通过端口访问服务（文档第 1 页）。
+ **任务输入**：显微镜采集的图像文件 **.nd2** + 参数 **.json**（文档第 1~2 页）。
+ **核心流程**（文档第 12 页）：
    1. 上传大文件（阶段1）
    2. Web UI 调参生成/覆盖 json（阶段2）
    3. debug=true 输出视频/图片回传前端，循环调参（阶段3）
    4. debug=false 正式运行，实时日志/状态，产出 csv（阶段4）
    5. CSV 预览与下载，历史记录（阶段5）
+ **多用户**：必须有**用户系统**、**任务队列（上传队列/运行队列）**、**状态展示**、**日志/进度**、**历史任务**（文档第 2、12~13 页）。
+ **MinIO**：用于提升上传速度（SCP/VSCode 上传仅 <sub>10MB/s，MinIO 端口中转更快，文档第 4 页）；并给出了 MATLAB 端 </sub>`aws.s3`<sub> 连接 MinIO 的配置要点（文档第 5</sub>10 页）。
+ **服务器信息页**：CPU/Mem/Disk、MATLAB 版本 `ver('MATLAB')`、分析包版本（文件夹 ID）、队列长度、Worker/Redis 健康（文档第 12~13 页）。
+ **安全要求**：仅内网 IP 白名单 + 用户 ID 管理（文档第 11 页）。
+ **分析包路径**：`/home/guv_Analysis/Run_Pipeline/20251230_V1.1`，服务器 `10.30.70.108`（文档第 2 页）。

---

## 2. 总体架构（可维护、可扩展、对 MATLAB 友好）
### 2.1 组件划分
**推荐技术栈（稳定、工程化、便于扩展）**：

+ 前端：Vue 3 + TypeScript + Vite + Element Plus（或 React + Antd 也行）
+ 后端 API：FastAPI（Python）
+ 任务队列：Celery + Redis（**并发控制=1** 或按许可证限制）
+ 元数据数据库：PostgreSQL（任务、用户、产物索引、事件日志索引）
+ 对象存储：MinIO（存 nd2/json/产物/csv/log 等）
+ 反向代理：Nginx（统一入口、静态资源、API 代理、可做 IP 白名单）

> 为什么建议“MATLAB 不直接写 S3/MinIO”作为默认路径？  
因为 ND2 通常需要本地路径读取、稳定性更好；MinIO 的主要价值在**客户端高速上传与统一存储**。我们可以：  
**前端→MinIO（直传）**，**Worker 下载到本地 run_dir**，调用 MATLAB 读本地文件，产物再由 Worker 上传回 MinIO。  
同时保留文档里的 MATLAB `aws.s3` 直连 MinIO 作为“可选增强/灾备”（文档第 5~10 页）。
>

### 2.2 数据流（对照文档第 3 页流程图）
+ 用户创建任务 → 生成 `task_id`
+ 前端将 `.nd2` 上传到 MinIO：`{username}_{task_id}/raw/xxx.nd2`
+ 前端编辑参数 → 保存为 json 上传 MinIO：`{username}_{task_id}/params/params_vN.json`（覆盖或版本化）
+ debug=true：Worker 拉取 nd2+params 到本地 → MATLAB debug → 产出 `preview.mp4/png` → 上传 MinIO → 前端展示 → 用户继续调参循环
+ debug=false：Worker 运行正式流程 → 产出 `result.csv` → 上传 MinIO → 前端预览/下载 → 记录历史

---

## 3. 任务状态机与阶段定义（直接用于代码）
按照文档（第12页）“待运行/等待/运行/完成/失败/取消”，再补齐工程必需状态：

### 3.1 状态（TaskStatus）
+ `DRAFT`：任务创建但尚未上传完成（等同“待运行”的早期）
+ `UPLOADING`：上传中（阶段1）
+ `READY`：上传完成 + 参数已保存，但未进入运行队列（待提交）
+ `QUEUED`：已进入 Celery 队列（文档“等待”）
+ `RUNNING_DEBUG`：debug 运行中（阶段3的一次执行）
+ `RUNNING_FINAL`：正式运行中（阶段4）
+ `SUCCEEDED`：完成（文档“完成”）
+ `FAILED`：失败（文档“失败”）
+ `CANCELED`：取消（文档“取消”）

### 3.2 阶段（TaskStage）
+ `STAGE_1_UPLOAD`
+ `STAGE_2_PARAMS`
+ `STAGE_3_DEBUG`
+ `STAGE_4_FINAL`
+ `STAGE_5_RESULT`

---

## 4. 目录与命名规范（MinIO Key + 本地 run_dir）
### 4.1 MinIO Bucket 与 Key 约定
建议统一一个 bucket：`lab-analysis`（也可拆 raw/results）

对象 Key：

```plain
{uid}/raw/{filename}.nd2
{uid}/params/params_v{N}.json
{uid}/debug/{run_id}/preview.mp4
{uid}/debug/{run_id}/preview.png
{uid}/final/{run_id}/result.csv
{uid}/logs/{run_id}/matlab.log
{uid}/meta/task.json
```

其中：

+ `uid = {username}_{task_id}`（与文档第 11 页 python 片段一致：`uid = f"{username}_{proposal_id}"`）

### 4.2 Linux 本地运行目录（Worker 用）
```plain
/data/analysis/tasks/{task_id}/
  input/
    raw.nd2
    params.json
  output/
    debug/
    final/
  logs/
    matlab.log
  control/
    CANCEL   (取消请求文件)
```

---

## 5. 数据库设计（可直接建表/写 ORM）
### 5.1 表结构（PostgreSQL）
**users**

+ id (uuid, pk)
+ username (text, unique)
+ password_hash (text)
+ role (text: admin/user)
+ created_at

**tasks**

+ id (uuid, pk)
+ user_id (uuid, fk users)
+ name (text)
+ status (text)
+ stage (text)
+ created_at / updated_at
+ nd2_object_key (text)
+ nd2_size (bigint)
+ params_object_key_current (text)
+ params_version (int)
+ debug_mode (bool)  // 当前模式开关
+ cancel_requested (bool)
+ last_error (text)
+ run_id_current (text)  // 本次运行标识
+ result_csv_key (text)
+ last_preview_key (text)
+ pipeline_path (text)  // /home/.../20251230_V1.1
+ matlab_version (text)
+ pipeline_version (text) // 可从文件夹名或 git hash 读

**task_artifacts**

+ id (uuid, pk)
+ task_id (uuid, fk)
+ kind (text: raw/params/preview/csv/log/...)
+ object_key (text)
+ created_at
+ meta (jsonb)

**task_events**（用于历史与审计）

+ id (uuid, pk)
+ task_id (uuid, fk)
+ ts
+ level (info/warn/error)
+ message (text)

> 日志全文不建议都塞 DB：  
**全文 log 存 MinIO / 本地文件**，DB 只存事件索引与摘要，前端实时日志通过 websocket/redis 推送。
>

---

## 6. 后端实现方案（FastAPI + Celery），含可直接开工的骨架
### 6.1 后端项目结构（建议照抄）
```plain
backend/
  app/
    main.py
    core/
      config.py
      security.py
    db/
      session.py
      base.py
      models.py
      crud.py
    api/
      deps.py
      routes/
        auth.py
        tasks.py
        system.py
        artifacts.py
        ws.py
    services/
      minio_service.py
      pipeline_service.py
      log_service.py
      system_service.py
    worker/
      celery_app.py
      tasks.py
  alembic/
  alembic.ini
  requirements.txt
  .env.example
  docker-compose.yml   (minio+redis+postgres)
  scripts/
    run_matlab_task.sh
    run_matlab_task.m
```

---

### 6.2 docker-compose（只跑基础设施，MATLAB 跑宿主机）
`backend/docker-compose.yml`（示例，可直接用）：

```yaml
services:
  redis:
    image: redis:7
    ports: ["6379:6379"]
    command: ["redis-server", "--appendonly", "yes"]

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: lab
      POSTGRES_PASSWORD: labpass
      POSTGRES_DB: lab_analysis
    ports: ["5432:5432"]
    volumes:
      - pgdata:/var/lib/postgresql/data

  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadminpassword
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"  # S3 API
      - "9001:9001"  # Console
    volumes:
      - miniodata:/data

volumes:
  pgdata:
  miniodata:
```

> 内网部署时，MinIO 9000/9001 端口按需开；再配合 Nginx 做 IP 白名单（文档第 11 页）。
>

---

### 6.3 配置（.env.example）
```bash
# DB
DATABASE_URL=postgresql+psycopg://lab:labpass@127.0.0.1:5432/lab_analysis

# Redis
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2

# MinIO
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadminpassword
MINIO_BUCKET=lab-analysis
MINIO_SECURE=false   # 内网 HTTP 可先 false

# Security
JWT_SECRET=change_me
JWT_EXPIRE_MIN=720

# MATLAB / Pipeline
PIPELINE_ROOT=/home/guv_Analysis/Run_Pipeline/20251230_V1.1
MATLAB_BIN=/usr/local/MATLAB/R2023b/bin/matlab   # 按实际安装路径
RUN_BASE_DIR=/data/analysis/tasks
MAX_CONCURRENCY=1
```

---

### 6.4 FastAPI 关键接口设计（与你们前端页面一一对应）
#### 6.4.1 认证
+ `POST /api/auth/login`：返回 JWT
+ `GET /api/auth/me`

#### 6.4.2 任务创建/上传
+ `POST /api/tasks`
    - 入参：`name, filename, size`
    - 返回：`task_id, uid, nd2_object_key, presigned_put_url`
+ `POST /api/tasks/{task_id}/upload/complete`
    - 上传完成后回调，后端校验对象存在、大小一致，状态置 `READY`

> 大文件如果需要断点续传：再扩展 multipart（后面给可选增强）。
>

#### 6.4.3 参数编辑/保存
+ `GET /api/tasks/{task_id}/params`：返回当前 json（可从 MinIO 拉）
+ `PUT /api/tasks/{task_id}/params`
    - 入参：json（或表单字段后端生成 json）
    - 行为：写入 MinIO（覆盖或 version+1），更新 `params_version`，返回新的 `params_object_key_current`

#### 6.4.4 debug / final 运行
+ `POST /api/tasks/{task_id}/debug/run`
    - 行为：入队 debug worker（状态 `QUEUED` → `RUNNING_DEBUG`）
+ `POST /api/tasks/{task_id}/final/run`
    - 行为：将 `debug_mode=false` 入参写入 params 或单独字段，入队 final worker（`RUNNING_FINAL`）

#### 6.4.5 状态、队列、历史
+ `GET /api/tasks/{task_id}`：状态、阶段、进度、最新产物 key
+ `GET /api/tasks?status=&page=&page_size=`：任务历史列表（文档第 13 页）
+ `POST /api/tasks/{task_id}/cancel`：取消（等待中直接撤销；运行中写 CANCEL 文件 + best-effort 发信号）

#### 6.4.6 产物查看/下载
+ `GET /api/tasks/{task_id}/artifacts`：列出 preview/csv/log 等
+ `GET /api/artifacts/presign?object_key=`：返回下载 presigned url（前端直接下）

#### 6.4.7 系统信息页（文档第 12~13 页）
+ `GET /api/system/info`：CPU/Mem/Disk、MATLAB 版本、pipeline 版本、队列长度、RUNNING 数量、redis/minio health

#### 6.4.8 WebSocket：实时日志/进度
+ `WS /ws/tasks/{task_id}/logs`：推送 stdout 行、事件、进度

---

### 6.5 后端关键代码骨架（可直接复制开始填充）
#### 6.5.1 MinIO service（生成预签名上传/下载）
```python
# app/services/minio_service.py
from minio import Minio
from datetime import timedelta

class MinioService:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool):
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    def ensure_bucket(self, bucket: str):
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def presign_put(self, bucket: str, object_key: str, expires_sec: int = 3600) -> str:
        return self.client.presigned_put_object(bucket, object_key, expires=timedelta(seconds=expires_sec))

    def presign_get(self, bucket: str, object_key: str, expires_sec: int = 3600) -> str:
        return self.client.presigned_get_object(bucket, object_key, expires=timedelta(seconds=expires_sec))
```

#### 6.5.2 任务创建接口（返回直传 URL）
```python
# app/api/routes/tasks.py
import uuid, time
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter()

class TaskCreateIn(BaseModel):
    name: str
    filename: str
    size: int

@router.post("")
def create_task(payload: TaskCreateIn, user=Depends(...), db=Depends(...), minio=Depends(...)):
    task_id = str(uuid.uuid4())
    uid = f"{user.username}_{task_id}"
    nd2_key = f"{uid}/raw/{payload.filename}"

    # DB: insert task(status=DRAFT/UPLOADING)
    # ...

    put_url = minio.presign_put(bucket="lab-analysis", object_key=nd2_key, expires_sec=7200)
    return {
        "task_id": task_id,
        "uid": uid,
        "nd2_object_key": nd2_key,
        "presigned_put_url": put_url,
    }
```

#### 6.5.3 Celery Worker：下载→调用 MATLAB→上传结果→更新 DB
```python
# app/worker/tasks.py
import os, subprocess, uuid, json, signal, time
from app.services.minio_service import MinioService

def run_matlab_process(cmd, log_path, on_line):
    with open(log_path, "a", buffering=1) as f:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in p.stdout:
            f.write(line)
            on_line(line)
        return p.wait()

def make_run_dirs(run_base, task_id):
    run_id = str(uuid.uuid4())
    base = os.path.join(run_base, task_id, run_id)
    os.makedirs(os.path.join(base, "input"), exist_ok=True)
    os.makedirs(os.path.join(base, "output", "debug"), exist_ok=True)
    os.makedirs(os.path.join(base, "output", "final"), exist_ok=True)
    os.makedirs(os.path.join(base, "logs"), exist_ok=True)
    os.makedirs(os.path.join(base, "control"), exist_ok=True)
    return run_id, base

def check_cancel(control_dir):
    return os.path.exists(os.path.join(control_dir, "CANCEL"))

# Celery task（伪代码示意）
def worker_run(task_id: str, mode: str):
    # mode in {"debug","final"}
    # 1) DB: set status RUNNING_*
    # 2) MinIO: download nd2 + params 到 base/input
    # 3) call bash -> matlab -batch
    # 4) upload artifacts
    # 5) DB: update status

    run_id, base = make_run_dirs(os.getenv("RUN_BASE_DIR"), task_id)
    input_nd2 = os.path.join(base, "input", "raw.nd2")
    input_params = os.path.join(base, "input", "params.json")
    log_path = os.path.join(base, "logs", "matlab.log")
    control_dir = os.path.join(base, "control")

    # TODO: 从 DB 读 nd2_key / params_key
    # minio.fget_object(...) 下载到 input_nd2 / input_params

    # 调用脚本（见后面 scripts/run_matlab_task.sh）
    cmd = ["bash", "scripts/run_matlab_task.sh", task_id, run_id, mode, input_nd2, input_params, base]

    def on_line(line: str):
        # 这里可解析进度，例如 MATLAB 输出: "PROGRESS 0.35"
        # 然后推送到 redis pubsub 或 websocket
        pass

    exit_code = run_matlab_process(cmd, log_path, on_line)

    if exit_code != 0:
        # DB: FAILED + last_error
        return

    # 产物约定：debug -> output/debug/preview.mp4/png
    # final -> output/final/result.csv
    # 上传到 MinIO 并写入 task_artifacts
```

---

## 7. MATLAB 集成“契约”与脚本（让后端能稳定调用）
你们文档说明 MATLAB 在服务器路径中运行包：`/home/guv_Analysis/Run_Pipeline/20251230_V1.1`（文档第 2 页），并且需要 debug 输出视频/图片与最终 CSV（文档第 2、12 页）。

### 7.1 推荐的“统一入口”方式（强烈建议你们实现一次）
新增一个最薄的 MATLAB 包装入口：`scripts/run_matlab_task.m`

**输入**：

+ nd2 本地路径
+ params json 本地路径
+ output_dir
+ mode: debug/final

**输出**：

+ debug：写 `preview.mp4` 或 `preview.png` 到 `output_dir/output/debug/`
+ final：写 `result.csv` 到 `output_dir/output/final/`
+ 所有 `disp()` / `fprintf()` 输出被 Worker 捕获成为实时日志

示例（需要你们把“真实分析包入口函数”填进去）：

```matlab
% scripts/run_matlab_task.m
function run_matlab_task(mode, nd2_path, params_path, out_dir, pipeline_root)
    fprintf("MODE=%s\n", mode);
    fprintf("ND2=%s\n", nd2_path);
    fprintf("PARAMS=%s\n", params_path);
    fprintf("OUT=%s\n", out_dir);

    % 读取参数
    txt = fileread(params_path);
    params = jsondecode(txt);

    % TODO: 调用你们现有分析包入口（需要你们确认入口函数名）
    % 例：addpath(genpath(pipeline_root));
    % result = pipeline_main(nd2_path, params, out_dir, mode);

    % 建议：在关键阶段输出进度，便于前端显示
    fprintf("PROGRESS 0.10 DownloadedInputs\n");

    if isfield(params, "debug") && params.debug == true
        % 产出预览（示例）
        % imwrite(preview_img, fullfile(out_dir, "output/debug/preview.png"));
        fprintf("PROGRESS 0.80 DebugArtifactReady\n");
    else
        % writetable(T, fullfile(out_dir, "output/final/result.csv"));
        fprintf("PROGRESS 0.90 CSVReady\n");
    end

    fprintf("PROGRESS 1.00 Done\n");
end
```

### 7.2 Bash 包装（后端只需调用 bash）
`scripts/run_matlab_task.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

TASK_ID="$1"
RUN_ID="$2"
MODE="$3"
ND2_PATH="$4"
PARAMS_PATH="$5"
BASE_DIR="$6"

PIPELINE_ROOT="${PIPELINE_ROOT:-/home/guv_Analysis/Run_Pipeline/20251230_V1.1}"
MATLAB_BIN="${MATLAB_BIN:-matlab}"

cd "$PIPELINE_ROOT"

# -batch 会将输出打印到 stdout，便于 Worker 捕获
"$MATLAB_BIN" -batch "addpath(genpath('$PIPELINE_ROOT')); addpath(genpath('$(pwd)/scripts')); run_matlab_task('$MODE','$ND2_PATH','$PARAMS_PATH','$BASE_DIR','$PIPELINE_ROOT');"
```

> 你们文档第 12 页提到“运行中取消通常做请求取消由脚本轮询退出”。  
做法：Worker 创建 `control/CANCEL` 文件，MATLAB 在关键循环处 `exist(fullfile(out_dir,'control','CANCEL'),'file')` 就提前退出并打印“Canceled”。
>

---

## 8. 前端实现方案（页面、组件、数据结构、可直接开工）
### 8.1 前端项目结构（Vue3 示例）
```plain
frontend/
  src/
    api/
      http.ts
      tasks.ts
      system.ts
    router/
      index.ts
    store/
      auth.ts
      tasks.ts
    pages/
      Login.vue
      TaskCreate.vue
      TaskParams.vue
      TaskDebug.vue
      TaskResult.vue
      Queue.vue
      History.vue
      SystemInfo.vue
    components/
      UploadNd2.vue
      JsonParamForm.vue
      LogViewer.vue
      ArtifactViewer.vue
      TaskStatusBadge.vue
```

### 8.2 页面与接口一一对应（对照文档第 12~13 页）
1. **访问/登录页**（文档 3.1）
+ 登录获取 JWT，axios 拦截器注入 token
2. **分析任务创建页**（文档 3.2 阶段1）
+ 选择 `.nd2` 文件（浏览器 file input）
+ 调 `POST /api/tasks` 拿 `presigned_put_url`
+ 用 XHR/axios 直传到 MinIO（显示进度条）
+ 上传成功后调 `POST /api/tasks/{id}/upload/complete`
+ 跳转到参数页
3. **参数调整页**（阶段2 + 3）
+ 动态表单（toggle/slider/input），保存为 json
+ `PUT /api/tasks/{id}/params`
+ 点击“运行预览(debug)”→ `POST /api/tasks/{id}/debug/run`
+ 页面右侧展示最新 preview 图片/视频（ArtifactViewer）
4. **任务队列状态页**（文档 3.3）
+ `GET /api/tasks?status=QUEUED/RUNNING...`
+ 显示：等待/运行/完成/失败/取消（文档给定状态文本）
+ 支持取消按钮：`POST /api/tasks/{id}/cancel`
5. **系统信息页**（文档 3.4）
+ `GET /api/system/info` 展示 CPU/Mem/Disk、Matlab版本、分析包版本、队列长度、RUNNING 数量、Redis/Celery health
6. **任务历史页**（文档 3.5）
+ `GET /api/tasks` 分页
+ 点击进入详情：日志、参数版本、产物下载、CSV 预览

### 8.3 关键前端实现点（能直接写代码）
#### 8.3.1 ND2 直传 MinIO（带进度条）
核心思路：后端给 presigned PUT，前端用 `XMLHttpRequest` 获取 `upload.onprogress`。

伪代码：

```typescript
async function uploadToMinio(putUrl: string, file: File, onProgress: (p:number)=>void) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("PUT", putUrl)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(xhr.responseText))
    xhr.onerror = () => reject(new Error("upload error"))
    xhr.send(file)
  })
}
```

#### 8.3.2 debug 产物展示
+ 图片：`<img :src="presignedGetUrl">`
+ 视频：`<video controls :src="presignedGetUrl" />`

下载链接：后端 `GET /api/artifacts/presign?object_key=` 返回 URL。

#### 8.3.3 实时日志（WebSocket）
前端 `LogViewer.vue`：

+ 连接 `ws://server/ws/tasks/{task_id}/logs`
+ 逐行 append 到窗口（虚拟列表避免卡顿）
+ 遇到 `PROGRESS x.xx` 更新进度条

---

## 9. 队列与并发策略（满足“多人提交 + 有序运行”）
文档要求必须队列（上传队列、运行队列）（第 2、12 页）。工程落地建议：

+ **上传队列**：通常前端直传 MinIO，不需要后台排队；若要做“从共享盘拉取”的导入任务，才需要上传队列。
+ **运行队列**：Celery queue `matlab_run`，worker 并发设为 1（或按 MATLAB license/CPU 设定）。
+ **同一任务的 debug 重复提交**：建议后端实现“幂等/合并”：
    - 若该 task 正在 `RUNNING_DEBUG`，再次点击“运行预览”，后端返回 409 并提示“正在运行”
    - 或写一个 `debug_rerun_requested` 标志，当前 debug 结束后自动跑一次最新 params（更友好但复杂）

---

## 10. 取消机制（按文档“请求取消，脚本轮询退出”）
文档第 12 页：运行中取消要看 MATLAB 支持，通常做请求取消。

实现方案：

1. `POST /api/tasks/{id}/cancel`：
+ 若 `QUEUED`：从队列撤销（Celery revoke），状态 `CANCELED`
+ 若 `RUNNING_*`：
    - DB `cancel_requested=true`
    - 在 run_dir 创建 `control/CANCEL`
    - Worker 尝试向 MATLAB 进程发 `SIGTERM`（不保证立即退出）
3. MATLAB 在关键循环/长处理步骤里检查 CANCEL 文件存在则 `return`。

---

## 11. 系统信息页实现（CPU/Mem/Disk + 版本）
后端 `GET /api/system/info` 输出示例：

```json
{
  "cpu_percent": 23.5,
  "mem_used_gb": 18.2,
  "mem_total_gb": 64.0,
  "disk_used_gb": 420.1,
  "disk_total_gb": 1800.0,
  "matlab_version": "R2023b",
  "pipeline_version": "20251230_V1.1",
  "queue_length": 3,
  "running_count": 1,
  "redis_ok": true,
  "minio_ok": true,
  "worker_ok": true
}
```

MATLAB 版本获取：

+ 简单方式：后端启动时调用一次 `matlab -batch "ver('MATLAB')"` 并缓存
+ 或在 pipeline wrapper 输出版本行并解析

分析包版本：从目录名 `/home/.../20251230_V1.1` 提取即可（文档第 2 页）。

---

## 12. 可选增强：MATLAB 直连 MinIO（按文档第 5~10 页）
如果你们希望 MATLAB 直接从 MinIO 读写（减少 Worker 下载/上传），文档给出关键配置点：

+ `usePathStyleAccess = true`
+ 指定 `endpointURI`
+ `Region='us-east-1'`（MinIO 兼容）
+ 自签名证书问题可在测试环境禁用校验（仅限开发）

这一路径建议作为“增强模式”，默认仍建议 Worker 本地化，减少 MATLAB 对网络/证书的敏感性。

---

## 13. 开发实施步骤（按里程碑拆解，直接排期开发）
### M0：确认分析包入口与参数 schema（1~2 天）
+ 在 `/home/guv_Analysis/Run_Pipeline/20251230_V1.1` 找到当前运行方式（文档第 2 页有 cd/matlab 的提示）
+ 确认 debug 模式与 final 模式需要的参数字段
+ 输出一份 `params.schema.json`（用于前端动态表单）

### M1：基础设施与后端骨架（2~3 天）
+ docker-compose 拉起 redis/postgres/minio
+ FastAPI：login、task create、presign put/get、task status
+ Alembic 建表

### M2：上传 + 参数保存 + 历史列表（2~4 天）
+ 前端 TaskCreate 上传进度条
+ 参数页保存 json 到 MinIO（版本化）
+ 历史页分页列表

### M3：Worker + MATLAB 调用打通（3~5 天）
+ Worker：下载输入 → 调用 bash/matlab → 捕获日志 → 上传产物 → 更新 DB
+ debug 产物展示、final csv 下载
+ websocket 日志流

### M4：队列页 + 系统信息页 + 取消（2~4 天）
+ 队列状态、RUNNING 数、队列长度
+ system info：psutil + healthcheck
+ cancel：队列 revoke + CANCEL 文件机制

### M5：上线与加固（1~3 天）
+ Nginx 反代、IP 白名单（文档第 11 页）
+ 权限角色（admin 可看全部历史，user 只看自己）
+ 运行目录与 MinIO 生命周期策略（定期清理旧 debug）

---

## 14. 你们现在就可以开始的“最小可跑通版本”清单
如果要最快看到效果（1 个迭代内跑通）：

1. 后端：`POST /tasks` 返回 presigned PUT
2. 前端：ND2 文件直传 MinIO + upload complete
3. 参数：简单 JSON editor（先不做复杂动态表单）保存到 MinIO
4. Worker：固定并发 1，调用 MATLAB 输出一张 preview.png（debug）和一个 result.csv（final）
5. 前端：展示 preview + 下载 csv + 任务状态轮询

---

## 15.待行
需要给出完整 `requirements.txt`、`main.py`、路由、SQLAlchemy 模型、Celery 配置、websocket 推送实现、以及 Vue3 页面最小实现（上传/参数/预览/历史）。并需要告知：**现有分析包的入口脚本/函数名是什么**（比如某个 `.m` 或 bash 命令），以及 debug 输出目前是“视频/图片”的哪一种、默认文件名是什么，我就能把 `run_matlab_task.m` 里的 TODO 精确填实。

