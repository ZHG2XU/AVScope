# AVScope 明早验收清单

## 产物位置

- GUI 绿色版目录：`G:\AVScope\dist\AVScope`
- GUI 主程序：`G:\AVScope\dist\AVScope\AVScope.exe`
- Windows 安装包：`G:\AVScope\dist\AVScope-Setup.exe`
- 绿色版压缩包：`G:\AVScope\dist\AVScope-portable-win-x64.zip`
- 源码压缩包：`G:\AVScope\dist\AVScope-portable-source.zip`
- 示例报告：`G:\AVScope\samples\sample_wav_report.html`
- 工具安装记录：`G:\AVScope\INSTALLATIONS.md`
- E 盘工具清单：`E:\AVScopeTools\INSTALL_MANIFEST.txt`

## 一键验证

```powershell
PowerShell -ExecutionPolicy Bypass -File G:\AVScope\scripts\validate_release.ps1
```

验证内容包括：

- 单元测试。
- 关键产物存在性检查。
- UI/报告源码乱码扫描。
- C 盘写入目标扫描。
- 绿色版 GUI 启动烟测。
- 安装包静默安装到 G 盘、启动、卸载烟测。

## 手工验收建议

1. 打开 `G:\AVScope\dist\AVScope\AVScope.exe`。
2. 使用“打开”载入 `G:\AVScope\samples\sample.wav`。
3. 查看协议树、Hex、字段、时间线、预览、诊断面板。
4. 在 WAV `fmt ` 和 `data` 节点里检查 `sample_rate`、`byte_rate`、`block_align`、`data_bytes`、`duration_seconds`。
5. 打开 `G:\AVScope\samples\sample.h264`，检查 SPS 节点里是否显示 `profile_idc`、`level_idc`、`derived_width`、`derived_height`。
6. 打开 `G:\AVScope\samples\sample.aac`，检查 ADTS frame 字段里是否显示 `profile`、`sample_rate`、`channel_configuration`、`duration_seconds`。
7. 在工具栏搜索框输入 `RIFF`，模式选择 `text`，点击“查找下一个”。
8. 打开 `G:\AVScope\samples\sample.mp4`，检查 `moov/mvhd` 节点里是否显示 `timescale`、`duration`、`duration_seconds`。
9. 使用“分析 / 协议结构对比”对比：
   - `G:\AVScope\samples\sample.mp4`
   - `G:\AVScope\samples\sample_changed.mp4`
10. 导出 HTML/JSON 报告并打开检查。
11. 运行安装包，默认安装目录应为 `G:\AVScopeInstalled\AVScope`。

## 当前已知边界

- 当前是可安装 MVP，不是完整播放器。
- 视频画面解码预览尚未做到逐帧渲染，当前优先提供 ffprobe 流信息、packet 时间线和协议结构。
- MP4/H.264/H.265 字段解析仍是基础级，后续可继续补 SPS/PPS 深度字段、sample table 和 GOP 视图。
- 安装包不创建桌面或开始菜单快捷方式，以避免向 C 盘用户目录写入文件。
