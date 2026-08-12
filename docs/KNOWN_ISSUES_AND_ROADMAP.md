# AVScope 已知边界与后续规划

本文用于明早验收时说明当前 MVP 的能力边界和下一阶段演进方向。

## 当前已知边界

- 当前版本是可安装 MVP，不是完整播放器；视频预览支持按 1 秒生成上一/下一预览帧、按秒跳转预览时间、按帧号跳转、上一/下一关键帧预览并显示当前帧元信息，音频预览支持 Peak/RMS 能量摘要和按起始时间/时长播放短片段，暂不提供连续播放列表或精确逐帧解码控制。
- MP4、H.264、H.265 的字段解析覆盖常用排障字段；H.26x 已支持参数集引用链、关键帧前参数集和分辨率变化健康诊断，深层级 Slice 语法、GOP 图和解码质量指标仍需后续扩展。
- Raw YUV 当前支持 `yuv420p`、`nv12`、`nv21`、`yuyv422` 逐帧预览，暂不支持所有像素格式。
- PCAP/RTP/RTCP 当前支持按端点与 SSRC 聚合会话、sequence 回绕、估算丢包/重复/乱序、marker 和 payload 码率，支持 RTCP Compound、SR/RR、SDES/BYE、Generic NACK、PLI/FIR、H.264/H.265 Single/Aggregation/FU 视频负载，以及 SIP/SDP 动态 PT 与 Clock Rate 关联；暂未扩展到 TWCC/REMB/XR、RTSP/GB28181 专用信令和 TCP SIP 重组。
- 插件系统当前提供声明式魔数识别和字段模板示例，暂不执行第三方代码插件。
- 安装包默认安装到 `G:\AVScopeInstalled\AVScope`，不创建桌面或开始菜单快捷方式，以避免写入 C 盘用户目录。
- 大文件验证覆盖 128MB+ 随机访问和窗口读取；10GB 级文件仍建议在真实验收环境追加手工压力测试。

## 后续版本规划

- 视频预览：增加播放/暂停、精确逐帧控制和更完整的 GOP 图。
- 音频预览：增加声道选择和波形差异对比。
- 时间线：继续增加 RTP sequence 多流同轴对齐和 RTCP 报告随时间趋势；当前会话表已完成 RTP/RTCP SSRC 关联与质量汇总。
- 对比：扩展视频画面差分、PSNR/SSIM/VMAF、音频波形差分和按时间戳对齐的帧级对比。
- 解析器：补充更完整的 SPS/PPS/VPS 语法、MP4 sample table 深度导航和私有安防封装样例。
- 插件：增加可视化模板编辑器、插件校验器、沙箱策略和示例插件包。
- 性能：增加后台索引构建、可取消解析任务和更大规模文件的自动化压力测试。

## 验收参考

- 一键验证：`PowerShell -ExecutionPolicy Bypass -File G:\AVScope\scripts\validate_release.ps1`
- 手工清单：`G:\AVScope\docs\ACCEPTANCE.md`
- 发布验证报告：`G:\AVScope\dist\AVScope-validation-report.md`

## 本轮更新状态

- 已补充基础时间线曲线摘要：PTS/DTS 范围、非单调计数、时间戳异常点、码率 bucket、关键帧/GOP 间隔、GOP 分组结构、RTP sequence 摘要、MPEG-TS PCR 摘要和抽样曲线点会写入 `timeline_summary`。
- PCAP 已按 Ethernet/IPv4/UDP/RTP/RTCP 分层展示，新增 RTCP SR/RR、Report Block、丢包与边界诊断；Qt 媒体预览、HTML 和 CSV 会显示同一份会话质量摘要。
- 新增“传输会话”工作页，按端点与 SSRC 展示 RTP 包、payload、sequence 范围、估算丢失、重复、乱序、marker、码率和 RTCP 指标，并支持异常筛选与首包 Hex 定位。
- 新增“码流健康”工作页，汇总 H.264/H.265 参数集、Slice/关键帧、缺失引用和分辨率事件；问题可按精确 Offset 定位 Hex，并同步导出 HTML/JSON/CSV。新增两个正式异常码流样例用于回归验证。
- 新增 RTP H.264/H.265 视频负载检查，支持 STAP-A/AP/FU 分层协议节点、分片状态机、NALU 类型汇总和 payload Hex 定位；负载问题与传输会话状态联动，并提供正式多 SSRC 测试抓包及 HTML/JSON/CSV 示例报告。
- 新增 SIP/SDP 信令协商分析，支持 SIP 请求/响应、Call-ID/CSeq、完整 Header、SDP 媒体/方向/rtpmap/fmtp、按端口作用域的动态 PT 映射和 RTP Clock Rate 修正；Qt 提供信令/媒体上下分栏，并附带同 PT 跨会话、音频排除测试抓包及报告。
- 新增 RTCP 控制反馈分析，支持 SDES CNAME、BYE 原因、Generic NACK PID/BLP 丢失序号展开、PLI 和 FIR sequence；反馈与 RTP SSRC 会话关联，Qt 提供控制反馈上下分栏，HTML/JSON/CSV 与专用 PCAP 样例同步覆盖。
- GUI 时间线页已叠加 PTS/DTS 曲线、码率曲线、GOP 分段、RTP sequence 曲线、PCR 曲线和异常标记，时间戳、RTP sequence 与带行号 PCR 异常会在表格中高亮并通过 `Issue` 列说明原因，同时提供“只看时间线异常”筛选；预览页会显示时间线曲线摘要和统一的时间线异常原因摘要；HTML 报告会汇总时间戳、RTP sequence 和 PCR 异常清单，并在帧列表/Packet 时间线中标注 `Issue` 原因，宽表在窄屏下可横向滚动；CSV 导出会写入可筛选的 `timeline_issue` section；HTML/JSON/CSV 导出已包含同一份结构化数据，PCAP/RTP/RTCP 还会显示 sequence 曲线、跳变点与 RTCP 会话质量，MPEG-TS 会显示 PCR 曲线。
- 后续仍建议继续扩展 RTP sequence 多流对齐视图、后台索引、取消任务和 10GB 级自动化压力测试。
