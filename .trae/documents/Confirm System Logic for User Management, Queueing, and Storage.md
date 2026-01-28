我将按照您的要求，强制设置 Celery 并发数为 1，并添加队列排位显示功能。

### 1. 强制单任务串行执行 (Concurrency = 1)

*   **修改** `docker-compose.yml`:
    *   在 `celery_worker` 的启动命令中显式添加 `--concurrency=1` 参数。
    *   这将确保所有用户的任务都进入同一个队列，并严格按照 FIFO（先进先出）顺序，一次只运行一个任务，避免多任务争抢服务器资源。

### 2. 实现队列排位查询功能

*   **修改** `backend/app/services/queue_service.py`:
    *   新增方法 `get_queue_position(db: Session, task_id: str) -> dict`。
    *   **逻辑**：查询所有状态为 `QUEUED` 的任务，按 `created_at` 排序，计算目标任务前面有多少个任务。
    *   **返回值**：`{ "position": 3, "is_running": false }` （例如：排在第3位）。

*   **修改** `backend/app/api/routes/tasks.py`:
    *   新增 API 接口 `GET /tasks/{task_id}/queue-position`，调用上述 Service 方法。

### 3. 前端显示排队状态

*   **修改** `frontend/src/pages/TaskParams.vue`:
    *   在 `fetchTransferStatus` 或轮询逻辑中，增加对 `queue-position` 接口的调用。
    *   在任务状态栏（Run Status）中，当状态为 `QUEUED` 时，显示“当前排队位置：第 X 位”。

### 4. 多用户并发安全性确认

*   **确认结果**：是的，当前设计完全支持多用户同时使用。
    *   **隔离性**：`tasks.py` 中的 API 严格检查 `user_id`，用户只能看到自己的任务。
    *   **存储隔离**：MinIO 路径使用 `UUID` (TaskID) 作为前缀，不同用户上传同名文件不会冲突。
    *   **执行隔离**：虽然共享一个运行池，但 Celery + Redis 机制天然支持多生产者投递。设置并发数为 1 后，无论多少用户同时点击运行，任务都会乖乖排队，互不干扰。

**验证计划**：
1.  修改配置并重启后端容器。
2.  模拟多个任务进入队列，验证 `queue-position` 接口返回的数值是否正确递增。
