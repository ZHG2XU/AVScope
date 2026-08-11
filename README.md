# AVScope

AVScope 是面向音视频工程排障的桌面分析工具 MVP。当前版本使用 Python 标准库实现，优先保证在现有电脑环境中可运行，不需要安装新依赖。

## 当前能力

- 只读打开本地媒体文件，支持菜单选择、打开文件夹、拖拽到窗口，以及将文件拖到 exe 图标上启动打开。
- 支持打开文件夹、最近文件列表，以及 Hex/text 流式搜索。
- 支持协议树节点搜索，以及只显示 warning/error 异常节点的过滤视图。
- 支持 Ctrl+O、Ctrl+R、Ctrl+F、F3 等快捷键，以及 Hex 右键菜单复制当前 offset、选中字节、ASCII 并按大小端解释整数/浮点。
- 工具菜单提供时间戳计算器和码率计算器，便于换算 PTS/time_base、帧序号/FPS 和文件码率。
- 自动识别 MP4/MOV、AVI、FLV、Matroska/WebM、MPEG-TS、WAV、AAC ADTS、H.264 Annex-B、H.265 Annex-B、raw PCM、raw YUV。
- 大文件路径使用 `ByteSource` 只读随机访问，测试覆盖 128MB+ 文件头部、中部、尾部窗口读取。
- H.264 SPS/PPS 可解析 profile、level、SPS/PPS id、PPS 引用关系和推导宽高。
- H.265 VPS/SPS/PPS 可解析 profile、level、VPS/SPS/PPS id、PPS 引用关系、位深和推导宽高。
- MP4 `mvhd` 可解析 timescale、duration 和秒级时长。
- MP4 `tkhd/mdhd/hdlr` 可解析 track id、宽高、媒体 timescale、duration、语言和 handler 类型。
- MP4 `stsd/stts/stsc/stsz/stco/co64` 可解析样本描述、时间映射、chunk 映射、sample size 和 chunk offset。
- AVI 可解析 RIFF/LIST 结构、`avih` 主头、基础 stream header、宽高、帧数和帧率。
- FLV 可解析 header、tag 类型、data size、timestamp、stream id 和 PreviousTagSize。
- Matroska/WebM 可解析 EBML header、Segment/Info/Tracks/Cluster、DocType、时长、轨道、视频宽高和 SimpleBlock 帧。
- MPEG-TS 可解析 188 字节 packet、PID、payload start、adaptation control 和 continuity counter，统计 PID 分布，并诊断 continuity counter 跳变。
- AAC ADTS 可解析 profile、采样率、声道布局、帧时长、平均码率，并在字段表和 HTML 报告中显示 header 字段 bit offset/bit length。
- WAV 可解析 PCM 格式参数、data 字节数、帧数、时长，并校验 byte_rate/block_align。
- Raw PCM/YUV 支持在 CLI 和 GUI 中手动指定采样率、声道、位深、宽高、像素格式和帧率。
- 显示协议树、字段表、Hex 分页视图、帧列表和基础时间线，协议树、字段表和帧列表均可联动跳转 Hex。
- 使用现有 FFmpeg/ffprobe 补充媒体流信息和 packet 时间线。
- 对含视频流的文件使用现有 FFmpeg 生成首帧 PNG 预览，预览缓存写入 `G:\AVScope\tmp\previews`。
- 为 WAV/PCM 生成抽样波形摘要。
- 桌面端提供深色/浅色专业工作台主题、品牌图标、关键指标摘要条和空状态，导出 HTML 报告带结构化视觉样式。
- 输出基础诊断 warning/error，ffprobe 媒体流或 packet 时间线探测失败会转为可读 warning，并基于 packet 时间线提示 PTS/DTS 非单调和音视频时长差异。
- 单元测试覆盖 MP4/WAV/AAC/H.264/AVI/FLV/Matroska/MPEG-TS 典型损坏文件，验证解析失败不会导致程序崩溃并会输出诊断。
- 支持保存 `.avscope.json` 工程快照，记录当前分析结果、源文件路径和 Raw 参数。
- 导出独立 HTML、JSON、CSV 报告，HTML 报告包含帧列表、packet 时间线和协议结构，CSV 可按 section 筛选媒体摘要、诊断、帧、packet、节点和字段。
- 支持两个文件的二进制差异扫描，并输出 offset 对齐的左右 Hex/ASCII 并排差异表。
- 预留声明式插件模板机制，可在 `plugins\*.json` 中按魔数扩展私有格式识别和字段展示。
- 深色/浅色主题。

## 运行

```powershell
Set-Location G:\AVScope
E:\DevelopmentEnvironment\python\python.exe run_avscope.py
```

也可以运行：

```powershell
G:\AVScope\scripts\run_avscope.bat
```

Windows 桌面端支持把媒体文件直接拖入窗口打开；也支持把文件拖到 `AVScope.exe` 图标上启动打开。

## 命令行

生成示例文件：

```powershell
Set-Location G:\AVScope
$env:PYTHONPATH='G:\AVScope'
E:\DevelopmentEnvironment\python\python.exe -m avscope make-samples --out G:\AVScope\samples
```

分析并导出报告：

```powershell
E:\DevelopmentEnvironment\python\python.exe -m avscope analyze G:\AVScope\samples\sample.wav --html G:\AVScope\samples\sample_report.html --json G:\AVScope\samples\sample_report.json --csv G:\AVScope\samples\sample_report.csv
E:\DevelopmentEnvironment\python\python.exe -m avscope analyze G:\AVScope\samples\sample.pcm --sample-rate 8000 --channels 1 --bits-per-sample 16 --json G:\AVScope\samples\sample_pcm_report.json
E:\DevelopmentEnvironment\python\python.exe -m avscope analyze G:\AVScope\samples\sample.yuv --width 64 --height 48 --pixel-format yuv420p --fps 30 --json G:\AVScope\samples\sample_yuv_report.json
```

协议结构对比：

```powershell
E:\DevelopmentEnvironment\python\python.exe -m avscope compare-protocol G:\AVScope\samples\sample.mp4 G:\AVScope\samples\sample_changed.mp4 --json G:\AVScope\samples\protocol_compare.json
```

## 测试

```powershell
Set-Location G:\AVScope
$env:PYTHONPATH='G:\AVScope'
$env:TEMP='G:\AVScope\tmp'
$env:TMP='G:\AVScope\tmp'
E:\DevelopmentEnvironment\python\python.exe -m unittest discover -s tests
```

明早验收前可运行完整验证：

```powershell
PowerShell -ExecutionPolicy Bypass -File G:\AVScope\scripts\validate_release.ps1
```

验收清单见 `G:\AVScope\docs\ACCEPTANCE.md`。

## 目录结构

```text
G:\AVScope
├── avscope\             核心代码与桌面 UI
│   ├── parsers\         格式解析器
│   ├── analyzer.py      格式识别与解析入口
│   ├── byte_source.py   大文件随机读取抽象
│   ├── compare.py       二进制对比
│   ├── report.py        HTML/JSON 报告
│   └── app.py           Tkinter 桌面 UI
├── tests\               单元测试
├── samples\             示例文件目录
├── packaging\           打包说明
├── scripts\             启动和交付辅助脚本
├── data\                本地设置与最近文件列表
└── run_avscope.py       启动入口
```

## 打包说明

已安装的打包工具记录见 `G:\AVScope\INSTALLATIONS.md`。

生成 GUI `.exe` 目录：

```powershell
Set-Location G:\AVScope
$env:PYTHONPATH='G:\AVScope;E:\AVScopeTools\python-packages'
$env:PYINSTALLER_CONFIG_DIR='E:\AVScopeTools\pyinstaller-config'
$env:TEMP='E:\AVScopeTools\tmp'
$env:TMP='E:\AVScopeTools\tmp'
E:\DevelopmentEnvironment\python\python.exe -m PyInstaller --noconfirm --clean --windowed --name AVScope --add-binary "E:\DevelopmentEnvironment\ffmpeg-8.1-essentials_build\bin\ffprobe.exe;." --add-binary "E:\DevelopmentEnvironment\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe;." --add-data "G:\AVScope\plugins;plugins" --distpath G:\AVScope\dist --workpath G:\AVScope\build --specpath G:\AVScope\packaging G:\AVScope\run_avscope.py
```

当前交付构建会额外携带现有 `E:\DevelopmentEnvironment\ffmpeg-8.1-essentials_build\bin\ffprobe.exe` 和 `ffmpeg.exe`，用于补充媒体流信息、packet 时间线和视频首帧预览。

生成安装包：

```powershell
E:\AVScopeTools\nsis_extract\nsis-3.12\makensis.exe G:\AVScope\packaging\AVScope.nsi
```

当前安装包默认安装到 `G:\AVScopeInstalled\AVScope`，不创建桌面或开始菜单快捷方式，避免向 `C:\` 写入文件。
