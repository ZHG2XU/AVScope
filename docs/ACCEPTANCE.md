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

- 单元测试
- 关键产物存在性检查
- UI/报告源码乱码扫描
- C 盘写入目标扫描
- 绿色版 GUI 启动冒烟测试
- 安装包静默安装到 G 盘、启动、卸载冒烟测试

## 手工验收建议

1. 打开 `G:\AVScope\dist\AVScope\AVScope.exe`。
2. 使用“打开”加载 `G:\AVScope\samples\sample.wav`。
3. 查看协议树、Hex、字段、时间线、预览、诊断面板。
4. 在 WAV `fmt ` 和 `data` 节点里检查 `sample_rate`、`byte_rate`、`block_align`、`data_bytes`、`duration_seconds`。
5. 打开 `G:\AVScope\samples\sample.h264`，检查 SPS 节点里是否显示 `profile_idc`、`level_idc`、`derived_width`、`derived_height`。
6. 打开 `G:\AVScope\samples\sample.h265`，检查 VPS/SPS 节点里是否显示 `general_profile_idc`、`general_level_idc`、`derived_width`、`derived_height`、`bit_depth_luma`。
7. 打开 `G:\AVScope\samples\sample.aac`，检查 ADTS frame 字段里是否显示 `profile`、`sample_rate`、`channel_configuration`、`duration_seconds`。
8. 在工具栏搜索框输入 `RIFF`，模式选择 `text`，点击“查找下一个”。
9. 打开 `G:\AVScope\samples\sample.mp4`，检查 `moov/mvhd` 节点里是否显示 `timescale`、`duration`、`duration_seconds`，并检查 `trak/tkhd/mdia/mdhd/hdlr/stbl` 相关节点里的 `track_id`、`width`、`height`、`handler_type`、`sample_count`、`chunk_offset`。
10. 打开 `G:\AVScope\samples\sample.avi`，检查 `hdrl/avih` 节点里是否显示 `dwWidth`、`dwHeight`、`dwTotalFrames`、`fps`。
11. 打开 `G:\AVScope\samples\sample.pcm` 或 `G:\AVScope\samples\sample.yuv`，检查是否弹出 Raw 参数输入框；也可通过“工具 / 设置当前 Raw 参数”重新指定参数。
12. 使用“分析 / 协议结构对比”对比：
    - `G:\AVScope\samples\sample.mp4`
    - `G:\AVScope\samples\sample_changed.mp4`
13. 导出 HTML/JSON 报告并打开检查。
14. 运行安装包，默认安装目录应为 `G:\AVScopeInstalled\AVScope`。

## 当前已知边界

- 当前是可安装 MVP，不是完整播放器。
- 视频画面解码预览尚未做到逐帧渲染，当前优先提供 ffprobe 流信息、packet 时间线和协议结构。
- MP4/H.264/H.265 字段解析仍是基础层级，后续可继续补 SPS/PPS 深度字段、sample table 和 GOP 视图。
- 安装包不创建桌面或开始菜单快捷方式，以避免向 C 盘用户目录写入文件。
