# Packaging

AVScope 当前使用 `C++20 + Qt 6.9 Widgets` 桌面层，并将 Python 解析核心打包为同目录 `AVScopeEngine.exe` 侧车。

- `scripts/build_qt.ps1`：使用现有 Qt 6.9、CMake、Ninja 和 MinGW 构建桌面程序。
- `scripts/build_qt_engine.ps1`：使用现有 PyInstaller 打包解析引擎，并携带 ffprobe/ffmpeg。
- `scripts/deploy_qt.ps1`：生成 `dist/AVScopeQt` 独立运行目录。
- `packaging/AVScope.nsi`：从 `dist/AVScopeQt` 制作 Windows 安装包。

Qt、PyInstaller、NSIS 均复用 E 盘现有工具。需要安装或更新任何工具时，开发 Agent 必须先询问用户。
