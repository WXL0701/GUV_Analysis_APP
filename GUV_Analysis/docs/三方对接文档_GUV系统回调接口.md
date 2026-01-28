# 三方对接文档：GUV 专用数据处理系统回调 auto-exp 接口

本文档面向「GUV专用数据处理系统」研发，用于说明：当任务运行完成（或失败）后，如何回调 auto-exp 的回调接收接口，以推进对应任务步骤。

## 1. 接口信息

- 方法与路径：`POST /api/v1/notifications/callback/guv`
- Content-Type：`application/json`
- 鉴权（可选）：`X-Callback-Token`
  - Header：`X-Callback-Token: <callback_token>`
  - 说明：当 auto-exp 配置了 `guv.processing.callback-token` 时必须携带，且值必须一致；未配置时不校验该 header。

## 2. 回调触发时机与语义

当 GUV 系统侧发起的 auto-run 任务（run_id 对应的那次运行）结束后，应调用本回调接口告知结果：

- 成功：`success=true`
  - auto-exp 将把当前步骤 `GUV_DATA_PROCESSING` 标记为 `COMPLETED`，并自动推进到下一步继续执行。
- 失败：`success=false`
  - auto-exp 将把当前步骤标记为 `FAILED`，并记录失败原因（任务将停留在失败/中断态，需人工处理或重试策略）。

## 3. 请求体（JSON）

请求体结构（与现有外部系统回调统一）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| taskId | string | 是 | 任务标识（建议传 GUV 的 task_id，即 auto-run 请求中的 id；auto-exp 也兼容直接传 auto-exp 的 taskId） |
| success | boolean | 是 | 是否成功 |
| errorCode | string | 否 | 失败时可填写错误码 |
| errorMessage | string | 否 | 失败时可填写错误原因 |
| data | object | 否 | 附加数据（建议至少包含 run_id 及关键产物信息） |

### 3.1 taskId 兼容规则（重要）

auto-exp 对 `taskId` 的匹配规则如下：

1. 优先把 `taskId` 当作 auto-exp 的 taskId 直接查找；
2. 若找不到，再将 `taskId` 当作 GUV 侧 `task_id`（即 `guvTaskId`）去反查 auto-exp 当前处于 `WAITING/EXECUTING` 的 `GUV_DATA_PROCESSING` 步骤，匹配其 step_params 中的 `guvTaskId`，从而定位到 auto-exp 任务。

因此，推荐回调时直接传 GUV 自身的 `task_id`（与 auto-run 返回体中的 `task_id` 一致），即可保证定位准确。

## 4. 请求示例

### 4.1 成功回调

```http
POST /api/v1/notifications/callback/guv
Content-Type: application/json
X-Callback-Token: <可选>

{
  "taskId": "ABCD_0001",
  "success": true,
  "data": {
    "run_id": "f5e8f2b4-7ef8-4c1d-9b51-0d8c1f2caa12",
    "status": "completed",
    "result_location": "tasks/ABCD_0001/output/"
  }
}
```

### 4.2 失败回调

```http
POST /api/v1/notifications/callback/guv
Content-Type: application/json
X-Callback-Token: <可选>

{
  "taskId": "ABCD_0001",
  "success": false,
  "errorCode": "GUV_RUN_FAILED",
  "errorMessage": "算法执行失败：xxx",
  "data": {
    "run_id": "f5e8f2b4-7ef8-4c1d-9b51-0d8c1f2caa12"
  }
}
```

## 5. 返回体（JSON）

本接口正常返回（HTTP 200）为统一包装对象 `Result<Boolean>`：

成功示例：

```json
{
  "code": "200",
  "codeNum": "200",
  "data": true,
  "message": "操作成功",
  "success": true
}
```

鉴权失败（当 auto-exp 启用了 callback-token 且未携带/不匹配）示例（通常 HTTP 200，业务 code=400）：

```json
{
  "code": "400",
  "codeNum": "400",
  "data": null,
  "message": "GUV回调鉴权失败",
  "success": false
}
```

入参校验失败时，可能返回 HTTP 400 的错误体（字段缺失等），建议调用方将其作为失败处理并记录响应内容。

## 6. 字段建议与最佳实践

- 建议 `data` 至少带：
  - `run_id`：对应 GUV auto-run 返回的 run_id
  - 产物位置/对象 key（如果有）：便于 auto-exp 侧排障与追溯
- 回调建议幂等：
  - 同一 `taskId + run_id` 的回调可能因网络重试重复发送，auto-exp 会按当前步骤状态进行更新；建议调用侧自行做到“至多一次”或“可重复提交不影响最终一致性”的幂等重试。

## 7. GUV 侧配置与触发规则（实现说明）

### 7.1 GUV 侧配置（环境变量）

- `AUTOEXP_CALLBACK_URL`：auto-exp 回调接收地址（完整 URL），例如：`http://<AUTO_EXP_HOST>/api/v1/notifications/callback/guv`
  - 为空则不回调
- `AUTOEXP_CALLBACK_TOKEN`：可选；对应本接口的 `X-Callback-Token`（auto-exp 启用了 callback-token 时需要配置并发送）
- `AUTOEXP_CALLBACK_TIMEOUT_SECONDS`：回调 HTTP 超时（秒）
- `AUTOEXP_CALLBACK_MAX_RETRIES`：回调失败重试次数（建议保持较小，避免阻塞任务队列）

### 7.2 触发规则（只对三方任务回调）

- 仅当任务为“第三方系统调用产生的任务”才触发回调（即通过固定外部令牌 `X-External-Token` 发起的 `POST /api/tasks/auto-run`）
- GUV 在回调请求体的 `data` 中会附带 `task_type=external_autorun` 用于标识外部任务来源
