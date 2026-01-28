您要求整合修复“停止按钮无响应”的问题，并优化前端参数配置（引入完整 JSON 模板 + 增加 Compute/Video 模块控制）。

## 1. 修复后端停止逻辑 (Backend)
- **问题**: 当前 `stop_task` 仅修改数据库标志，Worker 可能轮询不及时或逻辑有漏洞。
- **文件**: `backend/app/worker/tasks.py`
- **操作**: 增强 `_should_cancel` 检测逻辑，并确保 `run_analysis_task` 中的子进程能被正确终止（使用 `process.terminate()` 后接 `kill()` 兜底）。同时检查 API 路由是否正确触发了 DB 更新。

## 2. 前端参数模板标准化 (Frontend)
- **文件**: 
  - 源: `MATLAB_Package/GUV_Image_Processor_V1.2/guvPipeline_config_template.json`
  - 目标: `frontend/src/config/defaultParams.json`
- **操作**: 将源文件复制到前端目录，作为参数初始化的**唯一真理源**。

## 3. 更新参数初始化与 GUI (Frontend)
- **文件**: `frontend/src/pages/TaskParams.vue`, `frontend/src/config/taskParamsSchema.ts`
- **操作**:
  - 修改 `createDefaultParams`：不再硬编码，而是直接加载 `defaultParams.json`。
  - 修改 `taskParamsSchema.ts`：增加 `Compute` 和 `Video` 模块的配置组（包含 Enable 开关和其他关键参数），使其在 GUI 上显示为可交互的表单项。
  - 确保 GUI 修改能双向同步回 JSON 预览框。

## 4. 部署更新
- 重建后端（修复停止逻辑）和前端（更新参数界面）容器。

此方案将解决无法停止任务的问题，并实现您要求的参数配置全面化。
