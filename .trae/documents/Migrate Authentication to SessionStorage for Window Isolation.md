我将实施以下计划，解决浏览器多窗口会话冲突的问题，实现不同窗口的用户隔离。

### 1. 会话存储机制迁移 (`localStorage` -> `sessionStorage`)

*   **问题根源**：目前使用 `localStorage` 存储 `token` 和 `username`。`localStorage` 的数据在同一域名的所有标签页/窗口间共享，导致一个窗口登录新用户，所有窗口都会读取到新 Token。
*   **解决方案**：将存储位置迁移至 `sessionStorage`。
    *   `sessionStorage` 仅在当前标签页/窗口有效，关闭窗口即销毁，且不同窗口间数据完全隔离。
    *   **修改文件**：
        *   `frontend/src/pages/Login.vue`: 登录/注册成功后，将 Token 写入 `sessionStorage` 而非 `localStorage`。
        *   `frontend/src/api/http.ts`: 请求拦截器从 `sessionStorage` 读取 Token。
        *   `frontend/src/router/index.ts`: 路由守卫从 `sessionStorage` 检查 Token。
        *   `frontend/src/App.vue`: 登出逻辑清除 `sessionStorage`；初始化用户信息时从 `sessionStorage` 读取。

### 2. 会话冲突检测机制

*   **目的**：虽然 `sessionStorage` 隔离了数据，但为了安全起见，应检测是否存在“用户以为自己是A，但系统认为他是B”的情况（极少见，主要用于防御性编程或localStorage遗留清理）。
*   **实现**：
    *   在 `frontend/src/App.vue` 中，监听 `storage` 事件（针对 `localStorage` 的变动）。
    *   虽然主要逻辑迁移到了 `sessionStorage`，但如果我们在 `localStorage` 中保留一个 `last_login_uid` 或类似标记，当其他窗口发生登录事件时，可以提示用户“检测到在其他窗口登录，当前会话不受影响”。
    *   **简化版**：鉴于用户要求“独立维护”，完全迁移到 `sessionStorage` 即可天然解决冲突。我们主要需要清理旧代码对 `localStorage` 的依赖。

### 3. 清理与兼容

*   **清理**：确保所有涉及 `localStorage.getItem('token')` 的地方都改为 `sessionStorage`。
*   **兼容**：为了防止旧用户升级后残留 `localStorage` token 导致混淆，可以在 `App.vue` 挂载时检查并清除 `localStorage` 中的 token（或者将其迁移一次到 session，但为了安全最好直接清除让用户重登）。

### 4. 具体实施步骤

1.  **修改 `http.ts`**: 将 `localStorage.getItem` 替换为 `sessionStorage.getItem`。
2.  **修改 `router/index.ts`**: 将路由守卫中的 Token 检查改为 `sessionStorage`。
3.  **修改 `Login.vue`**: 登录成功后写入 `sessionStorage`。
4.  **修改 `App.vue`**:
    *   更新用户信息的读取源。
    *   登出时清除 `sessionStorage`。
    *   **新增**：在 `onMounted` 中检测并清除 `localStorage` 中的旧 token，防止干扰。
    *   **新增**：监听 `storage` 事件，如果发现其他窗口更新了 `global_login_event`（可选，用于提示），或者保持完全隔离不提示。根据用户要求“新登录操作不应影响其他已打开窗口”，完全隔离是最佳选择，不需要提示，除非为了防止用户混淆。我们保持完全隔离即可。

### 5. 验证方案

*   打开窗口 A，登录用户 User1。
*   打开窗口 B，登录用户 User2。
*   刷新窗口 A，确认 User1 仍处于登录状态且操作不受 User2 影响。
*   刷新窗口 B，确认 User2 仍处于登录状态。
