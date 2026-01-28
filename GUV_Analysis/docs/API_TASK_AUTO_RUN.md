# 创建任务并自动运行接口（中文文档）

本接口用于“ND2 已经存在于 MinIO”的场景：一次调用完成创建任务记录、写入 `params.json`、并立即入队运行（`debug/final`），返回 `run_id` 供后续查询使用。

## 接口信息

- 方法与路径：`POST /api/tasks/auto-run`
- Content-Type：`application/json`
- 鉴权：二选一
  - 方式 A：JWT Bearer（与其它 tasks 接口一致）
    - Header：`Authorization: Bearer <access_token>`
  - 方式 B：第三方固定外部令牌（无需登录）
    - Header：`X-External-Token: <external_token>`
    - 后端配置：
      - `EXTERNAL_AUTORUN_TOKEN`：固定令牌；为空时禁用该通道（仅接受 JWT）
      - `EXTERNAL_AUTORUN_USERNAME`：外部系统默认用户名（默认 `auto-exp`）
    - 行为说明：
      - 命中外部令牌时，本次创建的任务用户默认归属到 `EXTERNAL_AUTORUN_USERNAME`（默认 `auto-exp`）
      - 如该用户不存在，后端会自动创建该用户

## 前置条件（必须满足）

- 调用前，ND2 文件必须已经上传到 MinIO 的以下 object_key：
  - `tasks/{id}/{filename}`
- 该 `id` 必须在系统中尚不存在（接口会创建新的 Task；若 `id` 已存在会返回 400）

## 请求体（JSON）

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| id | string | 是 | 任务ID：字母开头，4-32 位，字母数字下划线 |
| name | string | 是 | 任务显示名 |
| filename | string | 是 | ND2 文件名（用于拼出 object_key：`tasks/{id}/{filename}`） |
| params | object | 否 | 分析参数；会写入 `tasks/{id}/params.json`（默认 `{}`） |
| run_mode | string | 否 | `final` 或 `debug`（默认 `final`） |
| size | number | 否 | ND2 大小（字节）；不填则通过 MinIO `head_object` 获取 |

请求示例：

```json
{
  "id": "ABCD_0001",
  "name": "Test Run 001",
  "filename": "sample.nd2",
  "run_mode": "final",
  "params": {
    "some_param": 123
  }
}
```

## 返回体（JSON）

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| task_id | string | 任务ID |
| run_id | string | 本次运行的 run_id（TaskRun.id） |
| nd2_object_key | string | ND2 的 object_key（`tasks/{id}/{filename}`） |
| params_key | string | params.json 的 object_key（`tasks/{id}/params.json`） |
| status | string | 固定返回 `queued`（表示已入队） |

返回示例：

```json
{
  "task_id": "ABCD_0001",
  "run_id": "f5e8f2b4-7ef8-4c1d-9b51-0d8c1f2caa12",
  "nd2_object_key": "tasks/ABCD_0001/sample.nd2",
  "params_key": "tasks/ABCD_0001/params.json",
  "status": "queued"
}
```

## curl 调用示例

### 1）第三方固定外部令牌（无需登录）

```bash
curl -sS -X POST "http://<HOST>:8000/api/tasks/auto-run" \
  -H "X-External-Token: <external_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "ABCD_0001",
    "name": "Test Run 001",
    "filename": "sample.nd2",
    "run_mode": "final",
    "params": {
      "some_param": 123
    }
  }'
```

### 2）JWT 方式：登录获取 token

```bash
curl -sS -X POST "http://<HOST>:8000/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=<USER>&password=<PASS>"
```

返回的 `access_token` 用于后续请求头：

- `Authorization: Bearer <access_token>`

### 3）确保 ND2 已上传到 MinIO 的指定 key

你需要自行通过具备 MinIO 写权限的方式上传 ND2 到：

- `tasks/<id>/<filename>`

例如：`tasks/ABCD_0001/sample.nd2`

### 4）JWT 方式：创建任务并立即入队运行

```bash
curl -sS -X POST "http://<HOST>:8000/api/tasks/auto-run" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "ABCD_0001",
    "name": "Test Run 001",
    "filename": "sample.nd2",
    "run_mode": "final",
    "params": {
      "some_param": 123
    }
  }'
```

## 常见错误码

- 400
  - `Task ID already exists`：任务ID已存在
  - `ND2 object not found in storage`：MinIO 中找不到 `tasks/{id}/{filename}` 对应对象
- 401：未提供鉴权信息（未带 JWT 且未带外部令牌，或外部令牌通道未启用）
- 403：JWT 无效或已过期
- 404：JWT 对应的用户不存在
- 500：后端内部错误（含 MinIO 写入失败、入队失败等）

## 关联接口（现有能力）

说明：固定外部令牌仅用于本接口；其它接口仍按系统现有策略需要 JWT。

- 任务详情：`GET /api/tasks/{task_id}`
- 查看队列位置：`GET /api/tasks/{task_id}/queue-position`
- 查看运行日志：`GET /api/tasks/{task_id}/history/{run_id}/log`

## 部署与配置（Docker 生产式）

- 启用固定外部令牌：为后端容器配置环境变量 `EXTERNAL_AUTORUN_TOKEN`（建议 32+ 随机字符）
- 可选：配置 `EXTERNAL_AUTORUN_USERNAME`（默认 `auto-exp`）
- 更新后：在 `backend` 目录重启后端服务使配置生效（如你的生产流程习惯，必要时可同时重启 `celery_worker`）

