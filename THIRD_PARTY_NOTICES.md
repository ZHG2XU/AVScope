# 第三方组件声明

AVScope 的 Windows 分发包包含或依赖以下第三方组件。各组件仍由其权利人所有，并适用各自许可证。本文件用于提供来源和许可信息，不替代相应许可证正文，也不构成法律意见。

## Qt 6.9

- 用途：AVScope 桌面界面和多媒体支持。
- 分发方式：Qt 动态链接库及平台插件。
- 许可证：GNU Lesser General Public License v3（或 Qt 提供的其他适用许可选项）。
- 项目主页：<https://www.qt.io/>
- 开源义务说明：<https://www.qt.io/licensing/open-source-obligations>
- 源码：<https://download.qt.io/official_releases/qt/6.9/6.9.0/submodules/>

## FFmpeg 8.1 essentials build

- 用途：媒体流探测、Packet 时间线、预览帧和媒体提取。
- 分发方式：独立的 `ffmpeg.exe` 和 `ffprobe.exe`。
- 构建来源：gyan.dev essentials build。
- 当前构建配置包含 `--enable-gpl --enable-version3`，按 GNU General Public License v3 分发。
- 项目主页和源码：<https://ffmpeg.org/>
- 构建来源：<https://www.gyan.dev/ffmpeg/builds/>
- GPLv3：<https://www.gnu.org/licenses/gpl-3.0.html>

## Python 3.12

- 用途：AVScope 分析引擎运行时。
- 许可证：Python Software Foundation License。
- 项目主页及许可证：<https://www.python.org/about/legal/>

## PyInstaller

- 用途：将 Python 分析引擎打包为 Windows 可执行程序。
- 许可证：GPL 2.0 with a special exception that permits distributing bundled applications。
- 项目主页：<https://pyinstaller.org/>

## NSIS

- 用途：构建 Windows 安装程序。
- 许可证：zlib/libpng license。
- 项目主页：<https://nsis.sourceforge.io/>

如果分发包中的实际组件版本发生变化，发布者应在发布前同步更新本文件并重新核对相应许可证要求。
