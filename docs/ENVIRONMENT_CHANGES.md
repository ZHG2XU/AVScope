# 环境与新增安装记录

## 2026-08-12

- 本轮未安装新的工具、运行库或依赖文件。
- 继续使用现有 `python`。
- FFmpeg 与 ffprobe 通过 `PATH` 或 `AVSCOPE_FFMPEG` / `AVSCOPE_FFPROBE` 环境变量提供。
- 继续使用现有 `%AVSCOPE_TOOLS%` 下的 PyInstaller 与 NSIS。
- 现代桌面界面重构复用现有 `%AVSCOPE_QT_HOME%`、`%AVSCOPE_MINGW%`、`%AVSCOPE_CMAKE_HOME%` 和 `%AVSCOPE_NINJA_HOME%`，未安装新工具。
- Qt 源码位于 `.\qt`，构建缓存位于 `.\build\qt6`，独立运行目录位于 `.\dist\AVScopeQt`。
- 项目、临时文件、构建产物和样例报告均放置在 `.`。
