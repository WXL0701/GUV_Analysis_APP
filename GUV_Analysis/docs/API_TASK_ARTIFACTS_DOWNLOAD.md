# 三方对接文档：GUV 任务结果（AVI/CSV 等）下载接口

本文档面向第三方系统，用于说明：当通过 GUV 的 `auto-run` 创建并运行任务后，如何通过后端 API 拉取任务产物（AVI/MP4/CSV/JSON 等）与运行日志。

## 1. 鉴权

当前下载类接口鉴权默认使用 JWT Bearer（与其它 tasks 接口一致）：

- 方式 A：JWT Bearer
  - Header：`Authorization: Bearer <access_token>`

如需三方系统“免登录下载”，可复用 `auto-run` 的固定外部令牌方案，将下载端点鉴权改为支持以下 Header（需要后端配套改造后才能使用）：

- 方式 B：固定外部令牌
  - Header：`X-External-Token: <external_token>`
  - 说明：需要后端配置 `EXTERNAL_AUTORUN_TOKEN`

权限规则：

- `admin` 可访问所有任务
- 普通用户只能访问自己创建的任务
- 第三方固定外部令牌默认映射到 `auto-exp` 用户，因此只可下载 `auto-exp` 产生的任务结果

## 2. 运行实例（run_id）选择规则

多数下载接口支持可选参数 `run_id`：

- 若传 `run_id`：下载该次运行目录下的产物
- 若不传 `run_id`：后端按以下优先级选择
  1) `task.run_id_current`
  2) 否则取该 task 最新的 `TaskRun`（created_at 最大）

## 3. 列出可下载产物（推荐入口）

### 3.1 接口

- 方法与路径：`GET /api/tasks/{task_id}/artifacts/list`
- Query：
  - `run_id`：可选

### 3.2 返回（JSON）

```json
{
  "run_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "videos": [
    { "path": "output/debug/preview.avi", "name": "preview.avi" }
  ],
  "csvs": [
    { "path": "output/final/AllXYResults.csv", "name": "AllXYResults.csv" }
  ]
}
```

说明：

- `path` 为相对 `run_dir` 的相对路径（服务端已做安全校验，禁止目录穿越）
- `videos` 会收集 `.mp4/.avi`，`csvs` 会收集 `.csv`

## 4. 下载任意产物文件（AVI/MP4/CSV/JSON）

### 4.1 接口

- 方法与路径：`GET /api/tasks/{task_id}/artifacts/file`
- Query：
  - `path`：必填，来自 `artifacts/list` 返回的 `path`
  - `run_id`：可选
  - `download`：可选，`true|false`，默认 `false`

### 4.2 示例

下载 CSV 并强制浏览器下载文件名：

```bash
curl -L -o AllXYResults.csv \
  -H "Authorization: Bearer <access_token>" \
  "http://<HOST>:8000/api/tasks/ABCD_0001/artifacts/file?path=output/final/AllXYResults.csv&download=true"
```

如后端已按“固定外部令牌方案”扩展下载鉴权，可将上述 Header 替换为：`-H "X-External-Token: <external_token>"`。

下载 AVI：

```bash
curl -L -o preview.avi \
  -H "Authorization: Bearer <access_token>" \
  "http://<HOST>:8000/api/tasks/ABCD_0001/artifacts/file?path=output/debug/preview.avi&download=true"
```

## 5. 快捷接口：下载 Debug 预览视频

### 5.1 接口

- 方法与路径：`GET /api/tasks/{task_id}/preview/download`
- Query：
  - `run_id`：可选

说明：后端会在以下路径中二选一存在即返回：

- `output/debug/preview.mp4`
- `output/debug/preview.avi`

### 5.2 示例

```bash
curl -L -o preview.mp4 \
  -H "Authorization: Bearer <access_token>" \
  "http://<HOST>:8000/api/tasks/ABCD_0001/preview/download"
```

## 6. 快捷接口：下载结果 CSV

### 6.1 接口

- 方法与路径：`GET /api/tasks/{task_id}/results/download`
- Query：
  - `run_id`：可选

说明：后端会按优先级查找并返回一个 CSV：

1) `output/final/AllXYResults.csv`
2) `output/final/result.csv`
3) `AllXYResults.csv`
4) 以上都不存在时，在 run_dir 下递归查找任意 `.csv` 并返回首个命中

### 6.2 示例

```bash
curl -L -o results.csv \
  -H "Authorization: Bearer <access_token>" \
  "http://<HOST>:8000/api/tasks/ABCD_0001/results/download"
```

## 7. 读取运行日志（JSON 返回）

### 7.1 接口

- 方法与路径：`GET /api/tasks/{task_id}/history/{run_id}/log`

### 7.2 返回

```json
{
  "exists": true,
  "content": "......runtime.log 内容......"
}
```

## 8. 常见错误

- 401：未提供鉴权信息
- 403：无权限访问（非 admin 且不是任务 owner）
- 404：
  - Task 不存在
  - run_id 不存在或 run_dir 不存在
  - 下载目标文件不存在（例如 preview/result 未生成）
- 400：`path` 非法（安全校验未通过）
