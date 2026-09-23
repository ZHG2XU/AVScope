# 更新日志

本文档记录 AVScope 的用户可见变化，版本号遵循语义化版本格式。

## 0.2.1 - 2026-08-20

### 新增

- 新增 AVI 2.0/OpenDML 识别，可根据 OpenDML 头、索引或 `AVIX` 分段判断 AVI 版本。

### 改进

- 移除构建与发布校验中的固定盘符依赖，提升不同开发环境下的可移植性。
- 更新项目简介，使 GitHub 页面更清楚地说明 AVScope 的用途。

## 0.2.0 - 2026-08-16

首个公开下载版本。

### 新增

- Qt 6/C++20 音视频分析工作台及独立 Python 分析引擎。
- MP4/MOV、AVI、FLV、Matroska/WebM、MPEG-PS/TS、WAV、AAC、H.264/H.265、Raw PCM/YUV 与 PCAP 解析。
- RTP/RTCP 传输会话、SIP/SDP、NACK/PLI/FIR、TWCC、REMB、Jitter 和视频负载诊断。
- 协议树、字段表、Hex、帧/包列表、时间线、媒体预览、码流健康与书签页面。
- HTML、JSON、CSV 报告、工程快照及二进制/协议/帧级对比。
- Windows 安装版和绿色便携版。

### 改进

- 新增 AVScope 品牌化 Modern UI 2 安装向导。
- 默认安装到 `%ProgramFiles%\AVScope`，支持桌面和开始菜单快捷方式。
- 完善深色/浅色主题、异步任务、窗口布局、媒体播放控制和高 DPI 显示。
