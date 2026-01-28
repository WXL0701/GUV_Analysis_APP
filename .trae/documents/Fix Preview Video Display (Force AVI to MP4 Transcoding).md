关于您的提议，经过调研确认：**目前所有主流浏览器（Chrome/Firefox/Edge/Safari）的原生 `<video>` 标签均不支持直接播放 AVI 格式**。虽然可以通过 WebAssembly（如 ffmpeg.wasm）在前端强行解码，但会消耗大量用户 CPU、导致页面卡顿，且加载速度极慢（AVI 文件体积通常比 MP4 大很多）。

因此，**最快且最稳健**的方案仍然是在**后端进行转码**。当前的瓶颈在于转码逻辑可能被跳过或失败，导致前端拿到了原始 AVI。

我将执行以下优化方案，确保后端能稳定输出前端可用的 MP4：

## 1. 验证转码工具 (ffmpeg)
- **操作**：检查 Worker 容器中是否已成功安装 `ffmpeg`。
- **目的**：确保转码能力就绪。

## 2. 增强后端转码逻辑 (run_matlab_task.m)
- **文件**：[run_matlab_task.m](file:///home/guv_Analysis/GUV_Analysis_APP/GUV_Analysis/backend/scripts/run_matlab_task.m)
- **修改**：在“标准化产物”阶段增加**强制转码兜底逻辑**。
  - **现状**：如果第一步批量转码失败，脚本会直接拷贝 AVI 到 `output/debug/preview.avi`。
  - **优化**：如果找不到 MP4 但找到了 AVI，**在拷贝前再次尝试将其转码为 `output/debug/preview.mp4`**。
  - **命令**：`ffmpeg -y -loglevel error -i input.avi -pix_fmt yuv420p output.mp4`
- **优势**：即使 MATLAB 批量转码漏了，这里也能确保前端拿到的是 MP4。

## 3. 验证修复
- **操作**：
  1. 重启服务（确保新代码生效）。
  2. 请您重新运行一个 Debug 任务。
  3. 检查生成的 `preview` 文件是否为 MP4 格式，并确认前端能正常播放。
