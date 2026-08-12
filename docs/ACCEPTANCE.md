# AVScope 明早验收清单

## 快速验收入口

1. 打开 Qt 6 主程序：`G:\AVScope\dist\AVScopeQt\AVScope.exe`。
2. 查看完整验证报告：`G:\AVScope\dist\AVScope-validation-report.md`。
3. 查看发布产物清单：`G:\AVScope\dist\AVScope-release-manifest.json`。
4. 打开示例报告目录：`G:\AVScope\dist\sample-reports`。
5. 需要安装包验收时运行：`G:\AVScope\dist\AVScope-Setup.exe`，默认安装目录为 `G:\AVScopeInstalled\AVScope`。
6. 需要重新验证时运行：

```powershell
PowerShell -ExecutionPolicy Bypass -File G:\AVScope\scripts\validate_release.ps1
```

## 产物位置

- Qt GUI 绿色版目录：`G:\AVScope\dist\AVScopeQt`
- Qt GUI 主程序：`G:\AVScope\dist\AVScopeQt\AVScope.exe`
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

1. 打开 `G:\AVScope\dist\AVScopeQt\AVScope.exe`。
2. 使用“打开”加载 `G:\AVScope\samples\sample.wav`。
3. 将 `G:\AVScope\samples\sample.aac` 拖入主窗口，确认可自动打开；也可把样例文件拖到 `AVScope.exe` 图标上验证启动打开。
4. 查看协议树、Hex、字段、帧列表、时间线、预览、诊断面板，并确认顶部摘要条和底部状态栏显示本次解析耗时。
5. 使用“视图”菜单切换 Hex、字段表、帧列表、时间线、预览和诊断面板，并按 `Ctrl+L` 显示/隐藏底部日志；在协议树展开任意节点，确认字段和值以子项直接显示，长值可通过底部横向滚动条查看。
6. 在协议树分别选中节点、数值字段、文本字段和异常字段，确认选中背景与选中文字保持清晰对比，未选中字段按数值、文本、Hex、布尔值和 warning/error 使用不同颜色；通过“视图 / 深色主题”和“视图 / 浅色主题”切换后再次确认上述对比度和可读性。
7. 在 Qt 工作台输入字段名确认协议树实时过滤且保留祖先路径；勾选“只看异常”确认只保留 warning/error 路径；使用展开/折叠、字段/帧选择、`Ctrl+C`、`Ctrl+Shift+O` 和 `Esc`，确认详情、Hex 跳转、复制与取消分析生效。关闭后重新打开，确认主题、窗口、分栏、当前标签和最近文件恢复，且状态只写入 `G:\AVScope\data\qt-settings.ini`。
8. 运行 `PowerShell -ExecutionPolicy Bypass -File G:\AVScope\scripts\validate_qt_ui.ps1`，确认 Qt 构建、协议树数据契约、深浅主题、时间线、媒体流表、Raw PCM 波形、Raw YUV 第 1/2 帧、工程书签恢复、协议对比截图、高 DPI、异步任务约束和 G 盘状态文件检查通过；验证证据位于 `G:\AVScope\tmp\qt-ui-validation`。
9. 打开 `sample.pcap`、`sample.ts` 和带帧视频，确认时间线显示帧大小、PTS/DTS、码率、关键帧和异常标记；悬停显示帧详情，点击图形跳到帧表并联动 Hex。点击全局诊断中带 Offset 的行，确认直接切到 Hex 对应位置。
6. 打开 `G:\AVScope\samples\sample.wav`，检查“预览”页是否显示音频波形图、Peak/RMS 音频能量和裁剪样本数；使用“分析 / 播放音频片段”“分析 / 播放指定音频片段”和“分析 / 停止音频播放”确认可试听短片段、可指定起始时间/时长且不会阻塞界面。
7. 对真实含视频流文件打开后，在“预览”页检查是否出现“视频预览帧”和当前帧 PTS/DTS、duration、帧类型、关键帧、帧大小、分辨率、像素格式等信息；使用“分析 / 下一预览帧”“分析 / 上一预览帧”“分析 / 跳转预览时间”“分析 / 跳转预览帧号”“分析 / 下一关键帧预览”和“分析 / 上一关键帧预览”确认可按 1 秒步进、按秒跳转、按帧号跳转或按关键帧跳转刷新画面；若文件不可解码，预览区应给出 ffmpeg/ffprobe 错误文本而不是崩溃。
8. 在搜索框输入 `fmt`，模式选择 `node`，点击“查找下一个”，确认协议树可定位匹配节点；勾选“只看异常”确认协议树可过滤 warning/error 节点。
9. 在 WAV `fmt ` 和 `data` 节点里检查 `sample_rate`、`byte_rate`、`block_align`、`data_bytes`、`duration_seconds`。
10. 打开 `G:\AVScope\samples\sample.h264`，检查 SPS/PPS 节点里是否显示 `profile_idc`、`level_idc`、`derived_width`、`derived_height`、`pic_parameter_set_id`、`seq_parameter_set_id`，并在“预览”页确认帧统计摘要包含关键帧数量和关键帧间隔。
11. 打开 `G:\AVScope\samples\sample.h265`，检查 VPS/SPS/PPS 节点里是否显示 `general_profile_idc`、`general_level_idc`、`derived_width`、`derived_height`、`bit_depth_luma`、`pps_pic_parameter_set_id`，并在“预览”页确认帧统计摘要包含关键帧数量和关键帧间隔。
12. 打开 `G:\AVScope\samples\sample.aac`，检查 ADTS frame 字段里是否显示 `profile`、`sample_rate`、`channel_configuration`、`duration_seconds`，并确认 `syncword`、`profile`、`sampling_frequency_index`、`frame_length` 显示 bit offset/bit length；在字段表选中 `syncword` 时 Hex 应跳转并高亮对应字节；切换到“帧列表”页，确认 AAC frame 可按 offset、size、duration 列表查看，选中行后 Hex 跳转到对应位置；在“预览”页确认可看到帧统计摘要。
13. 在工具栏搜索框输入 `RIFF`，检查 `Ctrl+F` 聚焦搜索框、`F3` 查找下一个、`Ctrl+G` 可按十进制或十六进制跳转 Offset、`Ctrl+1~8` 可切换工作区标签，并可复制当前 Offset、值和文件完整路径。
14. 打开 `G:\AVScope\samples\sample.mp4`，检查 `moov/mvhd` 节点里是否显示 `timescale`、`duration`、`duration_seconds`，并检查 `trak/tkhd/mdia/mdhd/hdlr/stbl` 相关节点里的 `track_id`、`width`、`height`、`handler_type`、`sample_count`、`chunk_offset`；构造异常 MP4 时应能提示 chunk offset 越界或未落入 `mdat` 数据区。
15. 打开 `G:\AVScope\samples\sample.avi`，检查 `hdrl/avih` 节点里是否显示 `dwWidth`、`dwHeight`、`dwTotalFrames`、`fps`。
16. 打开 `G:\AVScope\samples\sample.flv`，检查 FLV tag 节点中是否显示 `tag_type`、`data_size`、`timestamp`、`stream_id` 和 `previous_tag_size`。
17. 打开 `G:\AVScope\samples\sample.mkv`，检查 Matroska/WebM 节点中是否显示 `DocType`、`TimecodeScale`、`Duration`、`TrackEntry`、`PixelWidth`、`PixelHeight` 和 `SimpleBlock` 帧。
18. 打开 `G:\AVScope\samples\sample.ps`，检查 MPEG-PS 节点中是否显示 `pack_header`、`system_header`、`video_stream[0]`、`packet_length`、`pts_seconds` 和 `payload_offset`。
19. 打开 `G:\AVScope\samples\sample.ts`，检查“时间线”页顶部是否显示帧/packet 大小柱状图，“预览”页是否显示 packet 统计摘要，并检查 MPEG-TS packet 节点中是否显示 `pid`、`payload_unit_start_indicator`、`adaptation_field_control` 和 `continuity_counter`，确认诊断规则可覆盖 continuity counter 跳变。
20. 打开 `G:\AVScope\samples\sample.pcap`，检查 PCAP/RTP 节点中是否显示 `src_ip`、`dst_ip`、`udp_src_port`、`rtp_payload_type`、`rtp_sequence`、`rtp_timestamp` 和 `rtp_ssrc`；在“预览”页和导出的 HTML/JSON/CSV 报告中确认可看到 RTP sequence 摘要、SSRC 分组、marker 包数量和 sequence 跳变异常点。
21. 打开 `G:\AVScope\samples\sample.pcm` 或 `G:\AVScope\samples\sample.yuv`，检查是否弹出 Raw 参数输入框；`sample.pcm` 可设置采样率、声道、位深、大小端和有符号/无符号，关闭后再次打开时应沿用上次设置。
22. 打开 `G:\AVScope\samples\sample.yuv` 时输入 `64x48 / yuv420p / 30fps`，检查“媒体预览”页是否显示八段 Raw YUV 彩条、帧 1/3 和宽高/像素格式/帧率；点击右上角下一箭头应异步显示帧 2/3 且彩条相位变化。打开 `sample.pcm` 应显示可见正弦波形和采样参数；真实视频可用同一组箭头按 1 秒步进。
23. 打开“工具 / 时间戳计算器”和“工具 / 码率计算器”，确认可在诊断面板输出秒级时间码和 kbps/Mbps 码率。
24. 使用“分析 / 提取音频”“分析 / 提取视频”“分析 / 提取首个关键帧”对真实音视频文件导出到 G 盘临时验收目录，确认失败时有可读错误、成功时状态栏显示输出路径和大小。
25. 打开“插件 / 查看已加载模板”，确认可看到 `Demo Magic Container`；使用“插件 / 新建协议模板”可在 `G:\AVScope\plugins` 下生成声明式 JSON 模板，随后“插件 / 重新加载协议模板”可加载新模板；打开“帮助 / 快捷键”和“帮助 / 示例文件”，确认可看到验收操作提示。
26. 查看诊断面板，确认工具可在 MP4 chunk offset 异常、ffprobe 媒体流探测失败、packet 时间线探测失败、packet PTS/DTS 非单调、音视频时长差异或帧/packet 大小尖峰时输出 warning/error。
27. 使用“对比 / 协议结构对比”对比：
    - `G:\AVScope\samples\sample.mp4`
    - `G:\AVScope\samples\sample_changed.mp4`
28. 使用“对比 / 二进制对比”对比任意两个样例文件，确认“对比结果”页显示 offset、左右 Hex 差异，双击差异可跳转左侧 Hex；对比期间窗口可拖动和切换标签，顶部“取消”可终止任务。
29. 使用“对比 / 帧级对比”对比两个 AAC/H.264/H.265 等可提取帧列表的样例文件，确认“对比结果”页按新增、删除和变化分组显示 size/PTS/DTS/duration/type/keyframe 左右值，长任务不会冻结窗口。
30. 在可疑协议位置按 `Ctrl+B` 添加 Offset 书签并写备注，确认“书签”页双击可返回 Hex；使用“文件 / 保存工程快照”保存 `.avscope.json`，确认文件包含当前分析结果、源文件路径、Raw 参数、主题、标签页和书签。关闭后重新打开快照应恢复全部内容；源文件移动时应提示但仍能离线查看协议树、诊断和书签。
31. 打开 WAV 或真实多路音视频文件，在“媒体流”页检查每路流的 codec、profile、分辨率/声道、采样率、帧率、time_base、duration、bitrate 和像素/采样格式；音频与视频使用不同文字色。
31. 检查 Qt 绿色版目录中存在 `platforms\qwindows.dll`、`engine\AVScopeEngine.exe`、`engine\_internal\ffprobe.exe`、`ffmpeg.exe` 和 `plugins\demo_magic.json`，并打开发布清单确认安装包、绿色版、源码包、Qt DLL、引擎与插件文件均记录 size 和 SHA256。
32. 打开 `G:\AVScope\dist\sample-reports\sample_wav_report.html` 和 `G:\AVScope\dist\sample-reports\sample_mp4_report.json`，确认交付目录包含示例分析报告。
33. 打开 `G:\AVScope\dist\AVScope-validation-report.md`，确认一键验证通过项和关键产物大小已写入测试报告。
34. 导出 HTML/JSON/CSV 报告并打开检查，确认可选用户备注会写入报告；HTML 字段表的 `Bit / Size` 列会显示 AAC ADTS bit 字段位置，并包含音频波形图、结构化统计摘要表、帧/packet 大小图和“帧列表”章节；CSV 应包含 `media`、`notes`、`diagnostic`、`timeline_issue`、`frame_stats`、`packet_stats`、`frame`、`packet`、`node`、`field` 等 section。
35. 打开 `G:\AVScope\docs\KNOWN_ISSUES_AND_ROADMAP.md`，确认当前 MVP 边界和后续规划已有明确说明。
36. 运行安装包，默认安装目录应为 `G:\AVScopeInstalled\AVScope`。

## 当前已知边界

详见 `G:\AVScope\docs\KNOWN_ISSUES_AND_ROADMAP.md`。

## 本轮新增验收点：时间线曲线摘要

- 打开 `G:\AVScope\samples\sample.aac`、`sample.pcap`、`sample.ts` 或包含可探测 packet 的媒体文件后，预览页应显示“时间线曲线摘要”，包括 PTS/DTS 范围、码率曲线、GOP/keyframe 摘要、GOP 分组结构、RTP sequence 摘要、PCR 摘要、时间戳异常数量和统一的时间线异常原因摘要。
- 切换到“时间线”页，顶部图表应保留帧/packet 大小柱状图，并叠加 PTS/DTS 曲线、码率曲线、GOP 分段、RTP sequence 曲线、PCR 曲线和时间戳异常标记。
- 切换到“时间线”页后，PTS/DTS 回退、RTP sequence 跳变和带行号的 PCR 回退等时间线异常点应以警告底色高亮，并在 `Issue` 列显示原因；勾选“只看时间线异常”应只保留这些异常点，取消勾选后应恢复完整时间线表格。
- 导出 HTML/JSON/CSV 报告后，HTML 应包含“时间线曲线摘要”、时间线异常清单、PTS/DTS 曲线、码率曲线、GOP 结构图、RTP sequence 曲线、PCR 曲线和异常点，帧列表与 Packet 时间线的 `Issue` 列应显示异常原因，JSON/CSV 应包含 `timeline_summary`，CSV 还应包含可筛选的 `timeline_issue` section。
- 在窄屏或较小浏览器窗口打开 HTML 报告时，字段表、帧表、Packet 表和异常清单不应挤出页面主体，可在对应区块内横向滚动查看。
- 一键验证脚本 `G:\AVScope\scripts\validate_release.ps1` 已包含该功能的冒烟测试。
