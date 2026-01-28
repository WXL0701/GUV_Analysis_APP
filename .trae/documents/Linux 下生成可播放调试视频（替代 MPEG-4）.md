你这次的分析是对的：当前在 [guvDebug_makeDebugVideo.m](file:///home/guv_Analysis/GUV_Analysis_APP/MATLAB_Package/GUV_Image_Processor_V1.2/functions/Debug/guvDebug_makeDebugVideo.m#L12-L15) 用 `VideoWriter(...,'MPEG-4')`，该 profile 在 Linux 下通常不可用，所以触发 `The specified profile is not valid.`。要做到“快速生成 + 前端可展示”，推荐走“Linux 先产 AVI（Motion JPEG）→ 容器内转码成 MP4”这条最稳的链路。

## 目标
- Debug 模式下依旧生成调试视频。
- 前端继续按现有逻辑播放 MP4（不依赖浏览器对 AVI 的支持）。
- 只改与“调试视频生成/展示”直接相关的代码。

## 1) MATLAB 侧：在 Linux 上改用可用的 VideoWriter profile
**文件**
- [guvDebug_makeDebugVideo.m](file:///home/guv_Analysis/GUV_Analysis_APP/MATLAB_Package/GUV_Image_Processor_V1.2/functions/Debug/guvDebug_makeDebugVideo.m)
- [guvSeries_makeDebugVideo.m](file:///home/guv_Analysis/GUV_Analysis_APP/MATLAB_Package/GUV_Image_Processor_V1.2/functions/Series/guvSeries_makeDebugVideo.m)

**改动**
- 在 `guvDebug_makeDebugVideo` 内检测 `VideoWriter.getProfiles()`：
  - 若存在 `MPEG-4`，沿用 MP4。
  - 否则使用 `Motion JPEG AVI`，并把输出扩展名改为 `.avi`（避免“内容是 AVI 但文件名是 .mp4”）。
- 在 `guvSeries_makeDebugVideo` 里生成 `SavePath` 时不再硬编码 `.mp4`，而是根据上面的选择生成 `.mp4` 或 `.avi`。

## 2) Worker 侧：把 AVI 自动转码成 MP4（用于前端播放）
**文件**
- [run_matlab_task.m](file:///home/guv_Analysis/GUV_Analysis_APP/GUV_Analysis/backend/scripts/run_matlab_task.m#L72-L88)

**改动**
- 在“Standardize Artifacts”之前加一步：
  - 遍历 `out_dir` 下所有 `*.avi`（优先仅限 `**/DebugVideo/*.avi` 也可以），对每个 `xxx.avi` 生成同目录 `xxx.mp4`。
  - 生成后，原来的 `mp4s = dir(...'*.mp4')` 就能命中，从而继续复制出 `output/debug/preview.mp4`。
- 转码命令使用 `ffmpeg -y -i input.avi -pix_fmt yuv420p output.mp4`（兼容浏览器）。

## 3) Docker 镜像：安装 ffmpeg（转码所需）
**文件**
- [Dockerfile](file:///home/guv_Analysis/GUV_Analysis_APP/GUV_Analysis/backend/Dockerfile)

**改动**
- 在 `apt-get install` 中加入 `ffmpeg`。
- 同时把日志里仍提示缺的 `libXrandr.so.2` 对应包 `libxrandr2` 加上（它当前是报错行里的缺库来源，虽然任务能继续跑，但会反复刷错）。

## 4) 重新构建并验证（生产 Docker 部署方式）
- 在正确目录重建并重启后端与 worker 镜像。
- 重新跑一次 debug 任务：
  - 期望不再出现 `The specified profile is not valid.`
  - 期望 `artifacts/list` 中存在 DebugVideo 的 `*_Debug_refC*.mp4`（由转码生成）
  - 前端 `<video>` 可直接播放（仍然是 mp4 线路，不改前端也能工作）
