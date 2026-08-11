# AVScope 明早验收清单

## 产物位置

- GUI 绿色版目录：`G:\AVScope\dist\AVScope`
- GUI 主程序：`G:\AVScope\dist\AVScope\AVScope.exe`
- Windows 安装包：`G:\AVScope\dist\AVScope-Setup.exe`
- 绿色版压缩包：`G:\AVScope\dist\AVScope-portable-win-x64.zip`
- 源码压缩包：`G:\AVScope\dist\AVScope-portable-source.zip`
- 发布产物清单：`G:\AVScope\dist\AVScope-release-manifest.json`
- 发布验证报告：`G:\AVScope\dist\AVScope-validation-report.md`
- 示例报告目录：`G:\AVScope\dist\sample-reports`
- 示例报告：`G:\AVScope\samples\sample_wav_report.html`
- 已知边界与后续规划：`G:\AVScope\docs\KNOWN_ISSUES_AND_ROADMAP.md`
- 工具安装记录：`G:\AVScope\INSTALLATIONS.md`
- E 盘工具清单：`E:\AVScopeTools\INSTALL_MANIFEST.txt`

## 一键验证

```powershell
PowerShell -ExecutionPolicy Bypass -File G:\AVScope\scripts\validate_release.ps1
```

验证内容包括：

- 单元测试
- 128MB+ 大文件只读随机访问测试
- 损坏 MP4/WAV/AAC/H.264/AVI/FLV/Matroska/MPEG-PS/MPEG-TS/PCAP 文件、MP4 chunk offset 异常、ffprobe 探测失败与帧/packet 大小尖峰 warning 的诊断回归测试
- 关键产物存在性检查
- 发布产物清单 SHA256/size 校验
- UI/报告源码乱码扫描
- C 盘写入目标扫描
- 音频波形/能量与短片段、视频预览帧步进、RTP sequence 摘要和 Raw YUV 逐帧预览冒烟测试
- 绿色版 GUI 启动冒烟测试
- 安装包静默安装到 G 盘、启动、卸载冒烟测试
- 发布验证报告生成
- WAV/MP4 示例报告与对比 JSON 生成
- 插件模板创建与加载冒烟测试
- 音频、视频和关键帧提取冒烟测试

## 手工验收建议

1. 打开 `G:\AVScope\dist\AVScope\AVScope.exe`。
2. 使用“打开”加载 `G:\AVScope\samples\sample.wav`。
3. 将 `G:\AVScope\samples\sample.aac` 拖入主窗口，确认可自动打开；也可把样例文件拖到 `AVScope.exe` 图标上验证启动打开。
4. 查看协议树、Hex、字段、帧列表、时间线、预览、诊断面板，并确认顶部摘要条和底部状态栏显示本次解析耗时。
5. 使用“视图”菜单切换 Hex、字段表、帧列表、时间线、预览和诊断面板，并按 `Ctrl+L` 显示/隐藏底部日志。
6. 打开 `G:\AVScope\samples\sample.wav`，检查“预览”页是否显示音频波形图、Peak/RMS 音频能量和裁剪样本数；使用“分析 / 播放音频片段”“分析 / 播放指定音频片段”和“分析 / 停止音频播放”确认可试听短片段、可指定起始时间/时长且不会阻塞界面。
7. 对真实含视频流文件打开后，在“预览”页检查是否出现“视频预览帧”和当前帧 PTS/DTS、duration、帧类型、关键帧、帧大小、分辨率、像素格式等信息；使用“分析 / 下一预览帧”“分析 / 上一预览帧”“分析 / 跳转预览时间”“分析 / 跳转预览帧号”“分析 / 下一关键帧预览”和“分析 / 上一关键帧预览”确认可按 1 秒步进、按秒跳转、按帧号跳转或按关键帧跳转刷新画面；若文件不可解码，预览区应给出 ffmpeg/ffprobe 错误文本而不是崩溃。
8. 在搜索框输入 `fmt`，模式选择 `node`，点击“查找下一个”，确认协议树可定位匹配节点；勾选“只看异常”确认协议树可过滤 warning/error 节点。
9. 在 WAV `fmt ` 和 `data` 节点里检查 `sample_rate`、`byte_rate`、`block_align`、`data_bytes`、`duration_seconds`。
10. 打开 `G:\AVScope\samples\sample.h264`，检查 SPS/PPS 节点里是否显示 `profile_idc`、`level_idc`、`derived_width`、`derived_height`、`pic_parameter_set_id`、`seq_parameter_set_id`，并在“预览”页确认帧统计摘要包含关键帧数量和关键帧间隔。
11. 打开 `G:\AVScope\samples\sample.h265`，检查 VPS/SPS/PPS 节点里是否显示 `general_profile_idc`、`general_level_idc`、`derived_width`、`derived_height`、`bit_depth_luma`、`pps_pic_parameter_set_id`，并在“预览”页确认帧统计摘要包含关键帧数量和关键帧间隔。
12. 打开 `G:\AVScope\samples\sample.aac`，检查 ADTS frame 字段里是否显示 `profile`、`sample_rate`、`channel_configuration`、`duration_seconds`，并确认 `syncword`、`profile`、`sampling_frequency_index`、`frame_length` 显示 bit offset/bit length；在字段表选中 `syncword` 时 Hex 应跳转并高亮对应字节；切换到“帧列表”页，确认 AAC frame 可按 offset、size、duration 列表查看，选中行后 Hex 跳转到对应位置；在“预览”页确认可看到帧统计摘要。
13. 在工具栏搜索框输入 `RIFF`，模式选择 `text`，点击“查找下一个”；同时检查 `Ctrl+F` 聚焦搜索框、`F3` 查找下一个、Hex 右键菜单可复制当前 offset、选中字节和 ASCII，并可通过 `Endian` 选择后解释选中字节为整数/浮点。
14. 打开 `G:\AVScope\samples\sample.mp4`，检查 `moov/mvhd` 节点里是否显示 `timescale`、`duration`、`duration_seconds`，并检查 `trak/tkhd/mdia/mdhd/hdlr/stbl` 相关节点里的 `track_id`、`width`、`height`、`handler_type`、`sample_count`、`chunk_offset`；构造异常 MP4 时应能提示 chunk offset 越界或未落入 `mdat` 数据区。
15. 打开 `G:\AVScope\samples\sample.avi`，检查 `hdrl/avih` 节点里是否显示 `dwWidth`、`dwHeight`、`dwTotalFrames`、`fps`。
16. 打开 `G:\AVScope\samples\sample.flv`，检查 FLV tag 节点中是否显示 `tag_type`、`data_size`、`timestamp`、`stream_id` 和 `previous_tag_size`。
17. 打开 `G:\AVScope\samples\sample.mkv`，检查 Matroska/WebM 节点中是否显示 `DocType`、`TimecodeScale`、`Duration`、`TrackEntry`、`PixelWidth`、`PixelHeight` 和 `SimpleBlock` 帧。
18. 打开 `G:\AVScope\samples\sample.ps`，检查 MPEG-PS 节点中是否显示 `pack_header`、`system_header`、`video_stream[0]`、`packet_length`、`pts_seconds` 和 `payload_offset`。
19. 打开 `G:\AVScope\samples\sample.ts`，检查“时间线”页顶部是否显示帧/packet 大小柱状图，“预览”页是否显示 packet 统计摘要，并检查 MPEG-TS packet 节点中是否显示 `pid`、`payload_unit_start_indicator`、`adaptation_field_control` 和 `continuity_counter`，确认诊断规则可覆盖 continuity counter 跳变。
20. 打开 `G:\AVScope\samples\sample.pcap`，检查 PCAP/RTP 节点中是否显示 `src_ip`、`dst_ip`、`udp_src_port`、`rtp_payload_type`、`rtp_sequence`、`rtp_timestamp` 和 `rtp_ssrc`；在“预览”页和导出的 HTML/JSON/CSV 报告中确认可看到 RTP sequence 摘要、SSRC 分组、marker 包数量和 sequence 跳变异常点。
21. 打开 `G:\AVScope\samples\sample.pcm` 或 `G:\AVScope\samples\sample.yuv`，检查是否弹出 Raw 参数输入框；`sample.pcm` 可设置采样率、声道、位深、大小端和有符号/无符号，也可通过“工具 / 设置当前 Raw 参数”重新指定参数。
22. 打开 `G:\AVScope\samples\sample.yuv` 时输入 `64x48 / yuv420p / 30fps`，检查“预览”页是否显示 Raw YUV 预览帧；对多帧 Raw YUV 文件使用“分析 / 下一 YUV 帧”和“分析 / 上一 YUV 帧”确认可逐帧刷新画面。
23. 打开“工具 / 时间戳计算器”和“工具 / 码率计算器”，确认可在诊断面板输出秒级时间码和 kbps/Mbps 码率。
24. 使用“分析 / 提取音频”“分析 / 提取视频”“分析 / 提取首个关键帧”对真实音视频文件导出到 G 盘临时验收目录，确认失败时有可读错误、成功时状态栏显示输出路径和大小。
25. 打开“插件 / 查看已加载模板”，确认可看到 `Demo Magic Container`；使用“插件 / 新建协议模板”可在 `G:\AVScope\plugins` 下生成声明式 JSON 模板，随后“插件 / 重新加载协议模板”可加载新模板；打开“帮助 / 快捷键”和“帮助 / 示例文件”，确认可看到验收操作提示。
26. 查看诊断面板，确认工具可在 MP4 chunk offset 异常、ffprobe 媒体流探测失败、packet 时间线探测失败、packet PTS/DTS 非单调、音视频时长差异或帧/packet 大小尖峰时输出 warning/error。
27. 使用“分析 / 协议结构对比”对比：
    - `G:\AVScope\samples\sample.mp4`
    - `G:\AVScope\samples\sample_changed.mp4`
28. 使用“分析 / 二进制对比”对比任意两个样例文件，确认预览区显示 offset 对齐的左右 Hex/ASCII 并排差异表和 `^^` 差异标记；按 `F4` 或使用“分析 / 下一个二进制差异”确认可跳转高亮下一个差异窗口。
29. 使用“分析 / 帧级对比”对比两个 AAC/H.264/H.265 等可提取帧列表的样例文件，确认预览区显示新增帧、删除帧和 size/PTS/DTS/duration/type/keyframe 差异，并可保存 JSON。
30. 使用“文件 / 保存工程”保存 `.avscope.json`，确认文件包含当前分析结果、源文件路径、Raw 参数和可选用户备注。
31. 检查绿色版目录中存在 `G:\AVScope\dist\AVScope\_internal\plugins\demo_magic.json`，并打开 `G:\AVScope\dist\AVScope-release-manifest.json` 确认安装包、绿色版、源码包和内置 FFmpeg/插件文件均记录 size 与 SHA256。
32. 打开 `G:\AVScope\dist\sample-reports\sample_wav_report.html` 和 `G:\AVScope\dist\sample-reports\sample_mp4_report.json`，确认交付目录包含示例分析报告。
33. 打开 `G:\AVScope\dist\AVScope-validation-report.md`，确认一键验证通过项和关键产物大小已写入测试报告。
34. 导出 HTML/JSON/CSV 报告并打开检查，确认可选用户备注会写入报告；HTML 字段表的 `Bit / Size` 列会显示 AAC ADTS bit 字段位置，并包含音频波形图、结构化统计摘要表、帧/packet 大小图和“帧列表”章节；CSV 应包含 `media`、`notes`、`frame_stats`、`packet_stats`、`frame`、`node`、`field` 等 section。
35. 打开 `G:\AVScope\docs\KNOWN_ISSUES_AND_ROADMAP.md`，确认当前 MVP 边界和后续规划已有明确说明。
36. 运行安装包，默认安装目录应为 `G:\AVScopeInstalled\AVScope`。

## 当前已知边界

详见 `G:\AVScope\docs\KNOWN_ISSUES_AND_ROADMAP.md`。

## 本轮新增验收点：时间线曲线摘要

- 打开 `G:\AVScope\samples\sample.aac`、`sample.pcap`、`sample.ts` 或包含可探测 packet 的媒体文件后，预览页应显示“时间线曲线摘要”，包括 PTS/DTS 范围、码率曲线、GOP/keyframe 摘要、GOP 分组结构、RTP sequence 摘要、PCR 摘要和时间戳异常数量。
- 切换到“时间线”页，顶部图表应保留帧/packet 大小柱状图，并叠加 PTS/DTS 曲线、码率曲线、GOP 分段、RTP sequence 曲线、PCR 曲线和时间戳异常标记。
- 导出 HTML/JSON/CSV 报告后，HTML 应包含“时间线曲线摘要”、PTS/DTS 曲线、码率曲线、GOP 结构图、RTP sequence 曲线、PCR 曲线和异常点，JSON/CSV 应包含 `timeline_summary`。
- 一键验证脚本 `G:\AVScope\scripts\validate_release.ps1` 已包含该功能的冒烟测试。
