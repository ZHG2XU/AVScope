<p align="center">
  <img src="qt/resources/avscope.png" width="112" alt="AVScope 图标">
</p>

<h1 align="center">AVScope</h1>

<p align="center">面向音视频工程排障的桌面分析工作台</p>

<p align="center">
  <a href="https://github.com/ZHG2XU/AVScope/releases/latest"><img src="https://img.shields.io/github/v/release/ZHG2XU/AVScope?display_name=tag&sort=semver" alt="Latest release"></a>
  <a href="https://github.com/ZHG2XU/AVScope/releases/latest"><img src="https://img.shields.io/github/downloads/ZHG2XU/AVScope/total" alt="Downloads"></a>
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011-1674EA" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/Qt-6.9-41CD52" alt="Qt 6.9">
</p>

AVScope 用于快速查看媒体文件、裸码流和网络抓包的协议结构、字段、Hex、帧/包时间线与诊断结果。桌面端采用 `C++20 + Qt 6.9 Widgets`，分析引擎使用 Python，并以独立侧车进程运行。

## 下载

前往 [GitHub Releases](https://github.com/ZHG2XU/AVScope/releases/latest) 获取最新版本。

| 版本 | 适用场景 | 下载 |
| --- | --- | --- |
| Windows 安装版 | 推荐大多数用户使用，带安装向导和快捷方式选项 | [下载 AVScope-Setup.exe](https://github.com/ZHG2XU/AVScope/releases/latest/download/AVScope-Setup.exe) |
| Windows 绿色版 | 解压即用，不写入安装目录和注册表 | [下载 AVScope-portable-win-x64.zip](https://github.com/ZHG2XU/AVScope/releases/latest/download/AVScope-portable-win-x64.zip) |
| 源码包 | 开发、审阅或自行构建 | [查看全部发布文件](https://github.com/ZHG2XU/AVScope/releases/latest) |

系统要求：Windows 10/11 64 位。安装版默认安装到 `C:\Program Files\AVScope`，需要管理员授权。当前安装包尚未进行商业代码签名；运行前可使用 Release 附带的 `AVScope-release-manifest.json` 核对 SHA256。

## 快速使用

1. 安装或解压 AVScope，启动 `AVScope.exe`。
2. 拖入媒体文件、裸码流或 PCAP 抓包，也可以通过“文件 / 打开”选择文件。
3. 使用协议树、字段表、Hex、帧列表、时间线、媒体预览和诊断面板定位问题。
4. 需要共享结果时，导出 HTML、JSON 或 CSV 报告。

## 核心能力

- 结构分析：按协议层级展示节点、字段值、Offset、长度、原始 Hex 与诊断级别。
- Hex 工作台：分页读取、Offset 跳转、字段联动、书签、搜索和双文件差异对比。
- 时间线诊断：帧/包大小、PTS/DTS、码率、GOP、RTP sequence、PCR 与异常标记。
- 网络媒体分析：RTP/RTCP 会话、丢包/重复/乱序、Jitter、NACK/PLI/FIR、TWCC、REMB、SIP/SDP。
- 码流健康：H.264/H.265 参数集引用、关键帧、分辨率变化与分片完整性诊断。
- 媒体预览：视频帧、WAV/PCM 波形、Raw YUV、音频片段播放和流信息。
- 报告与快照：HTML/JSON/CSV 报告、`.avscope.json` 工程快照和 Offset 书签。
- 稳健解析：遇到截断或畸形输入时返回结构化诊断，避免因单个坏文件崩溃。

## 支持格式

| 类别 | 格式 |
| --- | --- |
| 容器与音频 | MP4/MOV、AVI、FLV、Matroska/WebM、WAV、AAC ADTS |
| 广播与系统流 | MPEG-PS、MPEG-TS |
| 视频裸流 | H.264 Annex-B、H.265 Annex-B |
| 原始媒体 | Raw PCM、Raw YUV（`yuv420p`、`nv12`、`nv21`、`yuyv422`） |
| 网络抓包 | PCAP、Ethernet II、IPv4、UDP、RTP、RTCP、SIP、SDP |
| 扩展格式 | `plugins/*.json` 声明式私有格式模板 |

## 命令行

从仓库根目录运行：

```powershell
$env:PYTHONPATH = (Get-Location).Path

python -m avscope analyze samples\sample.wav `
  --html tmp\sample.html `
  --json tmp\sample.json `
  --csv tmp\sample.csv

python -m avscope compare-protocol samples\sample.mp4 samples\sample_changed.mp4 `
  --json tmp\protocol-compare.json
```

## 开发与验证

```powershell
Set-Location G:\AVScope
$env:PYTHONPATH = (Get-Location).Path

# Python 测试
python -m unittest discover -s tests -v

# Qt 构建与部署
PowerShell -ExecutionPolicy Bypass -File scripts\build_qt.ps1
PowerShell -ExecutionPolicy Bypass -File scripts\deploy_qt.ps1

# 安装包、绿色版和完整发布验证
PowerShell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
PowerShell -ExecutionPolicy Bypass -File scripts\make_portable_zip.ps1
PowerShell -ExecutionPolicy Bypass -File scripts\validate_release.ps1
```

本机构建默认复用已配置的 Qt、CMake、Ninja、MinGW、Python、PyInstaller、NSIS 和 FFmpeg。具体要求见 [packaging/README.md](packaging/README.md)。

## 项目结构

```text
avscope/       Python 分析引擎、CLI、报告与格式解析器
qt/            Qt 6/C++20 桌面端
tests/         unittest 回归测试
samples/       示例媒体与抓包
scripts/       构建、打包和发布验证脚本
packaging/     NSIS 安装器及品牌资源
docs/          验收说明、已知问题与规划
```

## 发布与许可说明

- 版本变化见 [CHANGELOG.md](CHANGELOG.md)。
- 第三方组件及其许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
- 当前仓库尚未声明项目自身的开源许可证；未经版权方许可，不应将源码的公开可见视为获得了复制、修改或再分发授权。
