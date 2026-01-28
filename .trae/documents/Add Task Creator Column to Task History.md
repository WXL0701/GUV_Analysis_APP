我将实施以下计划，在任务历史界面中添加一列显示任务创建人的账户名称。

### 1. 后端修改

*   **修改数据模型 (`TaskOut`)**:
    *   在 `backend/app/schemas.py` 中，更新 `TaskOut` 模型，增加 `owner_name` 字段（类型 `Optional[str]`）。
*   **更新查询逻辑 (`tasks.py`)**:
    *   在 `backend/app/api/routes/tasks.py` 的 `read_tasks` 接口中，在构建返回的 `TaskOut` 对象时，通过 `task.owner.username` 获取创建人名称并赋值给 `owner_name`。
    *   **注意**：`Task` 模型已经通过 `user_id` 关联了 `User` 表 (`owner` 关系)，因此可以直接访问 `task.owner.username`，无需修改数据库结构。

### 2. 前端修改

*   **更新任务列表界面 (`TaskList.vue`)**:
    *   在 `frontend/src/pages/TaskList.vue` 中，更新 `Task` 接口定义，增加 `owner_name?: string` 字段。
    *   在 `<el-table>` 中添加一个新的 `<el-table-column>`，标题为 "Creator" (创建人)，绑定 `owner_name` 字段。
    *   将该列放置在 "Name" 列之后或 "Status" 列之前。

### 3. 验证

*   **重启服务**: 修改完成后，需要重启后端容器以应用 schema 和路由的变更。
*   **功能测试**: 登录不同账号创建任务，查看任务列表是否正确显示了每个任务的创建人用户名为其对应的账号名。
