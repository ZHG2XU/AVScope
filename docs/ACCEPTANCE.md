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
- 128MB+ 大文件只读随机访问测试
- 损坏 MP4/WAV/AAC/H.264/AVI 文件与 ffprobe 探测失败的诊断回归测试
- 关键产物存在性检查
- UI/报告源码乱码扫描
- C 盘写入目标扫描
- 绿色版 GUI 启动冒烟测试
- 安装包静默安装到 G 盘、启动、卸载冒烟测试

## 手工验收建议

1. 打开 `G:\AVScope\dist\AVScope\AVScope.exe`。
2. 使用“打开”加载 `G:\AVScope\samples\sample.wav`。
3. 将 `G:\AVScope\samples\sample.aac` 拖入主窗口，确认可自动打开；也可把样例文件拖到 `AVScope.exe` 图标上验证启动打开。
4. 查看协议树、Hex、字段、帧列表、时间线、预览、诊断面板。
5. 在搜索框输入 `fmt`，模式选择 `node`，点击“查找下一个”，确认协议树可定位匹配节点；勾选“只看异常”确认协议树可过滤 warning/error 节点。
6. 在 WAV `fmt ` 和 `data` 节点里检查 `sample_rate`、`byte_rate`、`block_align`、`data_bytes`、`duration_seconds`。
7. 打开 `G:\AVScope\samples\sample.h264`，检查 SPS/PPS 节点里是否显示 `profile_idc`、`level_idc`、`derived_width`、`derived_height`、`pic_parameter_set_id`、`seq_parameter_set_id`。
8. 打开 `G:\AVScope\samples\sample.h265`，检查 VPS/SPS/PPS 节点里是否显示 `general_profile_idc`、`general_level_idc`、`derived_width`、`derived_height`、`bit_depth_luma`、`pps_pic_parameter_set_id`。
9. 打开 `G:\AVScope\samples\sample.aac`，检查 ADTS frame 字段里是否显示 `profile`、`sample_rate`、`channel_configuration`、`duration_seconds`，并确认 `syncword`、`profile`、`sampling_frequency_index`、`frame_length` 显示 bit offset/bit length；切换到“帧列表”页，确认 AAC frame 可按 offset、size、duration 列表查看，选中行后 Hex 跳转到对应位置。
10. 在工具栏搜索框输入 `RIFF`，模式选择 `text`，点击“查找下一个”；同时检查 `Ctrl+F` 聚焦搜索框、`F3` 查找下一个、Hex 右键菜单可复制当前 offset、选中字节和 ASCII，并可通过 `Endian` 选择后解释选中字节为整数/浮点。
11. 打开 `G:\AVScope\samples\sample.mp4`，检查 `moov/mvhd` 节点里是否显示 `timescale`、`duration`、`duration_seconds`，并检查 `trak/tkhd/mdia/mdhd/hdlr/stbl` 相关节点里的 `track_id`、`width`、`height`、`handler_type`、`sample_count`、`chunk_offset`。
12. 打开 `G:\AVScope\samples\sample.avi`，检查 `hdrl/avih` 节点里是否显示 `dwWidth`、`dwHeight`、`dwTotalFrames`、`fps`。
13. 打开 `G:\AVScope\samples\sample.pcm` 或 `G:\AVScope\samples\sample.yuv`，检查是否弹出 Raw 参数输入框；也可通过“工具 / 设置当前 Raw 参数”重新指定参数。
14. 打开“工具 / 时间戳计算器”和“工具 / 码率计算器”，确认可在诊断面板输出秒级时间码和 kbps/Mbps 码率。
15. 查看诊断面板，确认工具可在 ffprobe 媒体流探测失败、packet 时间线探测失败、packet PTS/DTS 非单调或音视频时长差异时输出 warning。
16. 使用“分析 / 协议结构对比”对比：
    - `G:\AVScope\samples\sample.mp4`
    - `G:\AVScope\samples\sample_changed.mp4`
17. 使用“分析 / 二进制对比”对比任意两个样例文件，确认预览区显示 offset 对齐的左右 Hex/ASCII 并排差异表和 `^^` 差异标记。
18. 使用“文件 / 保存工程”保存 `.avscope.json`，确认文件包含当前分析结果、源文件路径和 Raw 参数。
19. 检查绿色版目录中存在 `G:\AVScope\dist\AVScope\_internal\plugins\demo_magic.json`，确认声明式插件模板随产物交付。
20. 导出 HTML/JSON 报告并打开检查，确认 HTML 字段表的 `Bit / Size` 列会显示 AAC ADTS bit 字段位置，并包含“帧列表”章节。
21. 运行安装包，默认安装目录应为 `G:\AVScopeInstalled\AVScope`。

## 当前已知边界

- 当前是可安装 MVP，不是完整播放器。
- 视频画面解码预览尚未做到逐帧渲染，当前优先提供 ffprobe 流信息、packet 时间线和协议结构。
- MP4/H.264/H.265 字段解析仍是基础层级，后续可继续补更深层 SPS/PPS 字段和 GOP 视图。
- 安装包不创建桌面或开始菜单快捷方式，以避免向 C 盘用户目录写入文件。
