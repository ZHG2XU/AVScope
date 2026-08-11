# Packaging

AVScope MVP 当前不主动安装新工具。

可选打包路径：

- PyInstaller：将 `run_avscope.py` 打成绿色版 `.exe`。
- NSIS 或 WiX：制作 Windows 安装包。
- Qt/C++ 迁移路线：当本机有 Qt 6/qmake/CMake package 后，可把当前 core/parser 模型迁移到 C++17/Qt Widgets。

需要安装 PyInstaller、NSIS、WiX 或 Qt 时，开发 Agent 必须先询问用户。
