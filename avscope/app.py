from __future__ import annotations

import json
import re
import struct
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from time import perf_counter
from tkinter import filedialog, messagebox, simpledialog, ttk

from avscope.analyzer import Analyzer
from avscope.audio_preview import build_audio_preview_clip, play_audio_preview_clip, stop_audio_preview
from avscope.byte_source import ByteSource
from avscope.compare import compare_binary, compare_frames, compare_protocol, format_binary_compare, format_frame_compare, format_protocol_compare
from avscope.extract import extract_media_stream
from avscope.ffmpeg_preview import build_video_preview, find_video_frame_time, find_video_keyframe_time
from avscope.hexview import format_hex, parse_offset
from avscope.models import CompareResult, FieldInfo, FrameInfo, ParseNode, ParseResult, Severity
from avscope.plugins import DEFAULT_PLUGIN_DIR, write_plugin_template
from avscope.report import export_csv, export_html, export_json, export_project
from avscope.search import SearchPatternError, find_pattern, parse_search_pattern
from avscope.settings import AppSettings
from avscope.timeline_viz import timeline_chart_items
from avscope.waveform import build_waveform_preview
from avscope.yuv_preview import build_yuv_preview


HEX_BYTE_RE = re.compile(r"\b[0-9A-Fa-f]{2}\b")


PALETTES = {
    "dark": {
        "bg": "#0F1419",
        "panel": "#151B22",
        "panel2": "#1B232D",
        "fg": "#E6EDF3",
        "muted": "#9AA7B4",
        "accent": "#4EA1D3",
        "accent2": "#77C0A4",
        "border": "#2A3441",
        "select": "#2B6E91",
        "select_fg": "#FFFFFF",
        "field_number": "#8FD694",
        "field_text": "#8BC6FF",
        "field_hex": "#C5A3FF",
        "field_bool": "#FFC978",
        "warning": "#D7A84A",
        "error": "#F06A6A",
        "ok_bg": "#14231F",
        "warning_bg": "#2A2417",
        "error_bg": "#2A171B",
        "text_bg": "#101820",
    },
    "light": {
        "bg": "#F4F7FA",
        "panel": "#FFFFFF",
        "panel2": "#EEF3F7",
        "fg": "#17212B",
        "muted": "#5E6B78",
        "accent": "#176B9A",
        "accent2": "#287A5C",
        "border": "#D8E0E8",
        "select": "#B9D9F2",
        "select_fg": "#102A43",
        "field_number": "#176B3A",
        "field_text": "#1D5D92",
        "field_hex": "#6641A5",
        "field_bool": "#8A5300",
        "warning": "#9A6700",
        "error": "#B42318",
        "ok_bg": "#EDF8F1",
        "warning_bg": "#FFF8E5",
        "error_bg": "#FFF0EE",
        "text_bg": "#FFFFFF",
    },
}

SUPPORTED_EXTENSIONS = {
    ".aac",
    ".avi",
    ".flv",
    ".h264",
    ".h265",
    ".mkv",
    ".264",
    ".265",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mov",
    ".pcap",
    ".pcm",
    ".ps",
    ".ts",
    ".vob",
    ".wav",
    ".webm",
    ".yuv",
}

VIDEO_PREVIEW_STEP_SECONDS = 1.0
YUV_PREVIEW_STEP_FRAMES = 1


def format_shortcuts_help() -> str:
    return "\n".join(
        [
            "常用快捷键",
            "",
            "Ctrl+O：打开文件",
            "Ctrl+R：重新解析当前文件",
            "Ctrl+S：保存工程快照",
            "Ctrl+F：聚焦搜索框",
            "F3：查找下一个",
            "Ctrl+1：切换到 Hex 视图",
            "Ctrl+2：切换到字段表",
            "Ctrl+3：切换到帧列表",
            "Ctrl+4：切换到时间线",
            "Ctrl+5：切换到预览",
            "Ctrl+L：显示或隐藏底部日志",
            "F4：跳转到下一个二进制差异",
            "Ctrl+Shift+H：导出 HTML 报告",
            "Ctrl+Shift+J：导出 JSON 报告",
            "Ctrl+Shift+O：复制当前 Offset",
            "Ctrl+Shift+C：复制选中 Hex 字节",
            "Ctrl+Shift+I：解释选中字节",
            "",
            "Hex 视图右键菜单可复制 offset、选中字节、ASCII，并按当前 Endian 解释整数/浮点。",
        ]
    )


def format_sample_files_help() -> str:
    return "\n".join(
        [
            "示例文件位置",
            "",
            "G:\\AVScope\\samples",
            "",
            "建议验收顺序：",
            "1. sample.wav：检查 WAV 字段、音频波形和报告导出。",
            "2. sample.aac：检查 ADTS bit 字段、帧列表和帧统计。",
            "3. sample.h264 / sample.h265：检查 SPS/PPS/VPS 和关键帧间隔。",
            "4. sample.mp4 / sample_changed.mp4：检查 MP4 box、chunk offset 诊断和协议对比。",
            "5. sample.pcm / sample.yuv：检查 Raw 参数输入、波形和 YUV 逐帧预览。",
            "",
            "完整验收清单：G:\\AVScope\\docs\\ACCEPTANCE.md",
        ]
    )


def format_empty_state_text() -> str:
    return "\n".join(
        [
            "工作区待命",
            "",
            "打开或拖入一个音视频文件开始分析。",
            "",
            "支持格式",
            "MP4/MOV、AVI、FLV、Matroska/WebM、MPEG-PS、MPEG-TS、PCAP/RTP/RTCP、WAV、AAC ADTS、H.264/H.265 Annex-B、PCM、YUV。",
            "",
            "常用验收入口",
            "打开示例文件: G:\\AVScope\\samples",
            "导出报告: 文件 / 导出 HTML、JSON、CSV",
            "媒体提取: 分析 / 提取音频、提取视频、提取首个关键帧",
        ]
    )


def format_plugin_template_summary(parsers: list[object]) -> str:
    lines = [
        "插件模板状态",
        "",
        "模板目录：G:\\AVScope\\plugins",
        "交付目录：G:\\AVScope\\dist\\AVScope\\_internal\\plugins",
        "",
    ]
    if not parsers:
        lines.append("当前未发现可加载的声明式插件模板。")
        return "\n".join(lines)
    lines.append(f"已加载 {len(parsers)} 个模板：")
    for parser in parsers:
        name = getattr(parser, "name", "<unnamed>")
        extensions = ", ".join(getattr(parser, "extensions", ()) or ("无扩展名",))
        manifest_path = getattr(parser, "manifest_path", "")
        lines.append(f"- {name} ({extensions})")
        if manifest_path:
            lines.append(f"  {manifest_path}")
    return "\n".join(lines)


def binary_compare_offsets(result: CompareResult) -> list[int]:
    return [chunk.offset for chunk in result.chunks]


def binary_compare_preview_indices(text: str, offsets: list[int]) -> list[str]:
    wanted = {f"0x{offset:08X}" for offset in offsets}
    indices = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line[:10] in wanted:
            indices.append(f"{line_number}.0")
    return indices


def format_elapsed_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    return f"{seconds:.3f} s"


ABOUT_TEXT = "\n".join(
    [
        "AVScope",
        "",
        "面向音视频工程排障的桌面分析工具。",
        "支持协议树、Hex/字段联动、帧时间线、预览、双文件对比、自动诊断和报告导出。",
        "",
        "项目目录：G:\\AVScope",
        "交付产物：G:\\AVScope\\dist",
    ]
)


class AVScopeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AVScope")
        self.geometry("1360x840")
        self.minsize(1040, 660)
        self.analyzer = Analyzer()
        self.result: ParseResult | None = None
        self.current_file: Path | None = None
        self.current_hex_offset = 0
        self.last_parse_elapsed_seconds: float | None = None
        self._node_by_iid: dict[str, ParseNode] = {}
        self._field_by_tree_iid: dict[str, tuple[ParseNode, FieldInfo]] = {}
        self._tree_iids_in_display_order: list[str] = []
        self._field_range_by_iid: dict[str, tuple[int, int]] = {}
        self._frame_offset_by_iid: dict[str, tuple[int, int]] = {}
        self._preview_images: list[tk.PhotoImage] = []
        self._last_search: tuple[str, str, int] | None = None
        self._last_node_search: tuple[str, int] | None = None
        self.raw_options_by_path: dict[str, dict] = {}
        self.settings = AppSettings()
        self._theme_name = "dark"
        self._palette = PALETTES["dark"]
        self._drop_wndproc = None
        self._old_wndproc = None
        self._last_logged_status = ""
        self._binary_diff_indices: list[str] = []
        self._binary_diff_cursor = -1
        self._video_preview_position_seconds = 0.0
        self._yuv_preview_frame_index = 0
        self.log_panel_visible = tk.BooleanVar(value=True)
        self.hex_endian = tk.StringVar(value="little")
        self.issue_filter = tk.BooleanVar(value=False)
        self.timeline_anomaly_filter = tk.BooleanVar(value=False)
        self._build_ui()
        self._bind_shortcuts()
        self._apply_theme("dark")
        self._set_empty_state()
        self._enable_windows_file_drop()

    def _build_ui(self) -> None:
        self._build_menu()

        self.header = tk.Frame(self, height=58)
        self.header.pack(side=tk.TOP, fill=tk.X)
        self.header.pack_propagate(False)
        self.logo = tk.Canvas(self.header, width=34, height=34, highlightthickness=0, borderwidth=0)
        self.logo.pack(side=tk.LEFT, padx=(18, 8), pady=12)
        self.brand = tk.Label(self.header, text="AVScope", font=("Segoe UI Semibold", 18), anchor=tk.W)
        self.brand.pack(side=tk.LEFT, padx=(0, 10), fill=tk.Y)
        self.file_badge = tk.Label(self.header, text="未打开文件", font=("Microsoft YaHei UI", 9), anchor=tk.W)
        self.file_badge.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 18))

        toolbar = ttk.Frame(self, style="Toolbar.TFrame")
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 10))
        toolbar_groups = [
            ("文件", [("打开", self.open_file, "Primary.Toolbar.TButton"), ("重新解析", self.reload_file, "Toolbar.TButton")]),
            (
                "对比",
                [
                    ("二进制对比", self.compare_files, "Toolbar.TButton"),
                    ("协议对比", self.compare_protocol_files, "Toolbar.TButton"),
                    ("帧级对比", self.compare_frame_files, "Toolbar.TButton"),
                ],
            ),
            (
                "报告",
                [
                    ("导出 HTML", self.export_html_report, "Toolbar.TButton"),
                    ("导出 JSON", self.export_json_report, "Toolbar.TButton"),
                    ("导出 CSV", self.export_csv_report, "Toolbar.TButton"),
                ],
            ),
        ]
        for group_index, (group_label, buttons) in enumerate(toolbar_groups):
            if group_index:
                ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(2, 10), pady=10)
            ttk.Label(toolbar, text=group_label, style="ToolbarGroup.TLabel").pack(side=tk.LEFT, padx=(0, 8), pady=8)
            for text, command, style_name in buttons:
                ttk.Button(toolbar, text=text, command=command, style=style_name).pack(side=tk.LEFT, padx=(0, 8), pady=8)
        ttk.Label(toolbar, text="Offset", style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(16, 6))
        self.offset_entry = ttk.Entry(toolbar, width=14, style="Offset.TEntry")
        self.offset_entry.insert(0, "0x0")
        self.offset_entry.pack(side=tk.LEFT)
        ttk.Button(toolbar, text="跳转", command=self.jump_hex, style="Toolbar.TButton").pack(side=tk.LEFT, padx=8)
        ttk.Label(toolbar, text="搜索", style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(18, 6))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(toolbar, width=24, textvariable=self.search_var, style="Offset.TEntry")
        self.search_entry.pack(side=tk.LEFT)
        self.search_mode = tk.StringVar(value="hex")
        self.search_mode_box = ttk.Combobox(toolbar, width=7, textvariable=self.search_mode, values=("hex", "text", "node"), state="readonly")
        self.search_mode_box.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="查找下一个", command=self.find_next, style="Toolbar.TButton").pack(side=tk.LEFT, padx=8)
        ttk.Label(toolbar, text="Endian", style="Toolbar.TLabel").pack(side=tk.LEFT, padx=(10, 6))
        self.endian_box = ttk.Combobox(toolbar, width=7, textvariable=self.hex_endian, values=("little", "big"), state="readonly")
        self.endian_box.pack(side=tk.LEFT)

        self.summary_frame = tk.Frame(self)
        self.summary_frame.pack(side=tk.TOP, fill=tk.X, padx=12, pady=(0, 10))
        self.summary_cards: dict[str, tk.Frame] = {}
        self.summary_values: dict[str, tk.Label] = {}
        for label, key in [("格式", "format"), ("大小", "size"), ("节点", "nodes"), ("诊断", "issues"), ("耗时", "elapsed")]:
            card = tk.Frame(self.summary_frame, height=54)
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            card.pack_propagate(False)
            tk.Label(card, text=label, font=("Microsoft YaHei UI", 8), anchor=tk.W).pack(anchor=tk.W, padx=12, pady=(8, 0))
            value = tk.Label(card, text="--", font=("Microsoft YaHei UI", 11, "bold"), anchor=tk.W)
            value.pack(anchor=tk.W, padx=12)
            self.summary_cards[key] = card
            self.summary_values[key] = value

        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        left = ttk.Frame(main, style="Panel.TFrame")
        main.add(left, weight=1)
        self._panel_title(left, "协议树")
        self.issue_check = ttk.Checkbutton(left, text="只看异常", variable=self.issue_filter, command=self.toggle_issue_filter, style="Panel.TCheckbutton")
        self.issue_check.pack(anchor=tk.W, padx=10, pady=(0, 6))
        tree_frame = ttk.Frame(left, style="Panel.TFrame")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.tree = ttk.Treeview(tree_frame, columns=("type", "value", "offset", "size"), show="tree headings", style="Data.Treeview")
        self.tree.heading("#0", text="名称")
        self.tree.heading("type", text="类型")
        self.tree.heading("value", text="值")
        self.tree.heading("offset", text="Offset")
        self.tree.heading("size", text="Size")
        self.tree.column("#0", width=260, minwidth=180)
        self.tree.column("type", width=92, anchor=tk.CENTER)
        self.tree.column("value", width=220, minwidth=120)
        self.tree.column("offset", width=96, anchor=tk.E)
        self.tree.column("size", width=92, anchor=tk.E)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(xscrollcommand=tree_scroll_x.set)
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        center = ttk.PanedWindow(main, orient=tk.VERTICAL)
        main.add(center, weight=4)
        self.tabs = ttk.Notebook(center, style="Workbench.TNotebook")
        center.add(self.tabs, weight=4)

        self.hex_text = tk.Text(self.tabs, wrap=tk.NONE, font=("Consolas", 10), undo=False, padx=14, pady=12, borderwidth=0)
        self.tabs.add(self.hex_text, text="Hex")
        self._build_hex_context_menu()

        self.fields = ttk.Treeview(
            self.tabs,
            columns=("name", "value", "hex", "offset", "bits", "desc"),
            show="headings",
            style="Data.Treeview",
        )
        for col, title, width, anchor in [
            ("name", "字段", 180, tk.W),
            ("value", "值", 220, tk.W),
            ("hex", "Hex", 160, tk.W),
            ("offset", "Offset", 96, tk.E),
            ("bits", "Bit / Size", 92, tk.CENTER),
            ("desc", "说明", 340, tk.W),
        ]:
            self.fields.heading(col, text=title)
            self.fields.column(col, width=width, anchor=anchor)
        self.tabs.add(self.fields, text="字段")
        self.fields.bind("<<TreeviewSelect>>", self.on_field_select)

        self.frames = ttk.Treeview(
            self.tabs,
            columns=("index", "offset", "size", "pts", "dts", "duration", "type", "key"),
            show="headings",
            style="Data.Treeview",
        )
        for col, title, width, anchor in [
            ("index", "#", 64, tk.E),
            ("offset", "Offset", 104, tk.E),
            ("size", "Size", 92, tk.E),
            ("pts", "PTS", 98, tk.E),
            ("dts", "DTS", 98, tk.E),
            ("duration", "Duration", 96, tk.E),
            ("type", "类型", 150, tk.W),
            ("key", "Key", 64, tk.CENTER),
        ]:
            self.frames.heading(col, text=title)
            self.frames.column(col, width=width, anchor=anchor)
        self.tabs.add(self.frames, text="帧列表")
        self.frames.bind("<<TreeviewSelect>>", self.on_frame_select)

        self.timeline_page = ttk.Frame(self.tabs, style="Panel.TFrame")
        timeline_toolbar = ttk.Frame(self.timeline_page, style="Toolbar.TFrame")
        timeline_toolbar.pack(fill=tk.X, padx=8, pady=(8, 0))
        ttk.Checkbutton(
            timeline_toolbar,
            text="只看时间线异常",
            variable=self.timeline_anomaly_filter,
            command=self.toggle_timeline_anomaly_filter,
            style="Panel.TCheckbutton",
        ).pack(side=tk.LEFT)
        self.timeline_filter_label = ttk.Label(timeline_toolbar, text="", style="Toolbar.TLabel")
        self.timeline_filter_label.pack(side=tk.LEFT, padx=(10, 0))
        self.timeline_canvas = tk.Canvas(self.timeline_page, height=118, highlightthickness=0, borderwidth=0)
        self.timeline_canvas.pack(fill=tk.X, padx=8, pady=(6, 4))
        self.timeline_canvas.bind("<Configure>", lambda _event: self._render_timeline_chart())
        self.timeline = ttk.Treeview(
            self.timeline_page,
            columns=("index", "stream", "pts", "dts", "pos", "size", "type", "duration", "key", "issue"),
            show="headings",
            style="Data.Treeview",
        )
        for col, title, width, anchor in [
            ("index", "#", 64, tk.E),
            ("stream", "Stream", 74, tk.CENTER),
            ("pts", "PTS", 98, tk.E),
            ("dts", "DTS", 98, tk.E),
            ("pos", "Offset", 104, tk.E),
            ("size", "Size", 92, tk.E),
            ("type", "类型", 120, tk.W),
            ("duration", "Duration", 96, tk.E),
            ("key", "Key", 64, tk.CENTER),
            ("issue", "Issue", 170, tk.W),
        ]:
            self.timeline.heading(col, text=title)
            self.timeline.column(col, width=width, anchor=anchor)
        self.timeline.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.tabs.add(self.timeline_page, text="时间线")

        self.preview = tk.Text(self.tabs, wrap=tk.WORD, font=("Consolas", 10), padx=16, pady=14, borderwidth=0)
        self.tabs.add(self.preview, text="预览")

        right = ttk.Frame(main, style="Panel.TFrame")
        main.add(right, weight=1)
        self._panel_title(right, "诊断 / 属性")
        self.diagnostics = tk.Text(right, wrap=tk.WORD, font=("Microsoft YaHei UI", 9), width=34, padx=12, pady=10, borderwidth=0)
        self.diagnostics.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.status = tk.StringVar(value="就绪")
        self.log_frame = tk.Frame(self, height=92)
        self.log_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 6))
        self.log_frame.pack_propagate(False)
        self.log_header = tk.Label(self.log_frame, text="日志", font=("Microsoft YaHei UI", 9, "bold"), anchor=tk.W)
        self.log_header.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(6, 0))
        self.log_text = tk.Text(self.log_frame, height=3, wrap=tk.WORD, font=("Consolas", 9), padx=10, pady=6, borderwidth=0)
        self.log_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(4, 8))
        self.log_text.configure(state=tk.DISABLED)
        self.status.trace_add("write", self._on_status_change)
        self._append_log(self.status.get())
        self.status_bar = tk.Label(self, textvariable=self.status, anchor=tk.W, font=("Microsoft YaHei UI", 9))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _panel_title(self, parent: ttk.Frame, text: str) -> None:
        label = ttk.Label(parent, text=text, style="PanelTitle.TLabel")
        label.pack(anchor=tk.W, padx=10, pady=(10, 8))

    def _build_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="打开文件", command=self.open_file)
        file_menu.add_command(label="打开文件夹", command=self.open_folder)
        self.recent_menu = tk.Menu(file_menu, tearoff=False)
        file_menu.add_cascade(label="最近文件", menu=self.recent_menu)
        file_menu.add_command(label="保存工程", command=self.save_project_snapshot, accelerator="Ctrl+S")
        file_menu.add_command(label="导出 HTML 报告", command=self.export_html_report)
        file_menu.add_command(label="导出 JSON 报告", command=self.export_json_report)
        file_menu.add_command(label="导出 CSV 报告", command=self.export_csv_report)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.destroy)
        menu.add_cascade(label="文件", menu=file_menu)

        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_command(label="Hex 视图", command=lambda: self.select_workspace_tab(self.hex_text, "Hex"))
        view_menu.add_command(label="字段表", command=lambda: self.select_workspace_tab(self.fields, "字段"))
        view_menu.add_command(label="帧列表", command=lambda: self.select_workspace_tab(self.frames, "帧列表"))
        view_menu.add_command(label="时间线", command=lambda: self.select_workspace_tab(self.timeline_page, "时间线"))
        view_menu.add_command(label="预览", command=lambda: self.select_workspace_tab(self.preview, "预览"))
        view_menu.add_command(label="诊断面板", command=self.focus_diagnostics)
        view_menu.add_separator()
        view_menu.add_checkbutton(label="显示底部日志", variable=self.log_panel_visible, command=self.toggle_log_panel)
        view_menu.add_separator()
        view_menu.add_command(label="深色主题", command=lambda: self._apply_theme("dark"))
        view_menu.add_command(label="浅色主题", command=lambda: self._apply_theme("light"))
        menu.add_cascade(label="视图", menu=view_menu)

        analysis_menu = tk.Menu(menu, tearoff=False)
        analysis_menu.add_command(label="自动识别", command=self.reload_file)
        analysis_menu.add_command(label="提取音频", command=lambda: self.extract_current_media("audio"))
        analysis_menu.add_command(label="提取视频", command=lambda: self.extract_current_media("video"))
        analysis_menu.add_command(label="提取首个关键帧", command=lambda: self.extract_current_media("keyframe"))
        analysis_menu.add_separator()
        analysis_menu.add_command(label="播放音频片段", command=self.play_audio_preview)
        analysis_menu.add_command(label="播放指定音频片段", command=self.play_audio_preview_range)
        analysis_menu.add_command(label="停止音频播放", command=self.stop_audio_preview)
        analysis_menu.add_separator()
        analysis_menu.add_command(label="上一预览帧", command=lambda: self.step_video_preview(-VIDEO_PREVIEW_STEP_SECONDS))
        analysis_menu.add_command(label="下一预览帧", command=lambda: self.step_video_preview(VIDEO_PREVIEW_STEP_SECONDS))
        analysis_menu.add_command(label="跳转预览时间", command=self.jump_video_preview_time)
        analysis_menu.add_command(label="跳转预览帧号", command=self.jump_video_preview_frame_index)
        analysis_menu.add_command(label="上一关键帧预览", command=lambda: self.jump_video_preview_keyframe(-1))
        analysis_menu.add_command(label="下一关键帧预览", command=lambda: self.jump_video_preview_keyframe(1))
        analysis_menu.add_command(label="上一 YUV 帧", command=lambda: self.step_yuv_preview(-YUV_PREVIEW_STEP_FRAMES))
        analysis_menu.add_command(label="下一 YUV 帧", command=lambda: self.step_yuv_preview(YUV_PREVIEW_STEP_FRAMES))
        analysis_menu.add_separator()
        analysis_menu.add_command(label="二进制对比", command=self.compare_files)
        analysis_menu.add_command(label="下一个二进制差异", command=self.jump_next_binary_diff, accelerator="F4")
        analysis_menu.add_command(label="协议结构对比", command=self.compare_protocol_files)
        analysis_menu.add_command(label="帧级对比", command=self.compare_frame_files)
        menu.add_cascade(label="分析", menu=analysis_menu)

        plugin_menu = tk.Menu(menu, tearoff=False)
        plugin_menu.add_command(label="查看已加载模板", command=self.show_plugin_templates)
        plugin_menu.add_command(label="重新加载协议模板", command=self.reload_plugin_templates)
        plugin_menu.add_command(label="新建协议模板", command=self.create_plugin_template)
        menu.add_cascade(label="插件", menu=plugin_menu)

        tools_menu = tk.Menu(menu, tearoff=False)
        tools_menu.add_command(label="设置当前 Raw 参数", command=self.configure_current_raw_options)
        tools_menu.add_command(label="复制当前 Offset", command=self.copy_current_offset, accelerator="Ctrl+Shift+O")
        tools_menu.add_command(label="复制选中 Hex 字节", command=self.copy_selected_hex_bytes, accelerator="Ctrl+Shift+C")
        tools_menu.add_command(label="复制选中 ASCII", command=self.copy_selected_ascii)
        tools_menu.add_command(label="解释选中字节", command=self.show_selected_hex_interpretation, accelerator="Ctrl+Shift+I")
        tools_menu.add_separator()
        tools_menu.add_command(label="时间戳计算器", command=self.show_timestamp_calculator)
        tools_menu.add_command(label="码率计算器", command=self.show_bitrate_calculator)
        menu.add_cascade(label="工具", menu=tools_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="快捷键", command=self.show_shortcuts_help)
        help_menu.add_command(label="示例文件", command=self.show_sample_files_help)
        help_menu.add_separator()
        help_menu.add_command(label="关于 AVScope", command=self.show_about)
        menu.add_cascade(label="帮助", menu=help_menu)

        self.config(menu=menu)
        self._refresh_recent_menu()

    def show_plugin_templates(self) -> None:
        plugin_parsers = [parser for parser in self.analyzer.parsers if getattr(parser, "manifest_path", None)]
        messagebox.showinfo("插件模板", format_plugin_template_summary(plugin_parsers))

    def reload_plugin_templates(self) -> None:
        self.analyzer = Analyzer()
        self.show_plugin_templates()
        if self.current_file:
            self.reload_file()

    def create_plugin_template(self) -> None:
        name = simpledialog.askstring("新建协议模板", "模板名称", initialvalue="Custom Container", parent=self)
        if not name:
            return
        extension = simpledialog.askstring("新建协议模板", "文件扩展名，例如 .bin", initialvalue=".bin", parent=self)
        if not extension:
            return
        magic_hex = simpledialog.askstring("新建协议模板", "文件起始魔数，例如 41 56 53 43", initialvalue="41 56 53 43", parent=self)
        if not magic_hex:
            return
        try:
            path = write_plugin_template(name, extension, magic_hex, DEFAULT_PLUGIN_DIR)
        except FileExistsError as exc:
            messagebox.showerror("协议模板已存在", f"模板文件已存在：\n{exc}")
            return
        except ValueError as exc:
            messagebox.showerror("协议模板无效", str(exc))
            return
        except OSError as exc:
            messagebox.showerror("协议模板写入失败", str(exc))
            return
        self.analyzer = Analyzer()
        self._refresh_recent_menu()
        self.status.set(f"已新建协议模板: {path}")
        messagebox.showinfo("协议模板已创建", f"已写入：\n{path}\n\n可在 G:\\AVScope\\plugins 中编辑字段定义。")

    def show_shortcuts_help(self) -> None:
        messagebox.showinfo("快捷键", format_shortcuts_help())

    def show_sample_files_help(self) -> None:
        messagebox.showinfo("示例文件", format_sample_files_help())

    def show_about(self) -> None:
        messagebox.showinfo("关于 AVScope", ABOUT_TEXT)

    def select_workspace_tab(self, widget: tk.Widget, label: str) -> None:
        self.tabs.select(widget)
        widget.focus_set()
        self.status.set(f"已切换到{label}")

    def focus_diagnostics(self) -> None:
        self.diagnostics.focus_set()
        self.status.set("已聚焦诊断面板")

    def toggle_log_panel(self) -> None:
        if self.log_panel_visible.get():
            self.log_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 6), before=self.status_bar)
            self.status.set("已显示底部日志")
        else:
            self.log_frame.pack_forget()
            self.status.set("已隐藏底部日志")

    def _on_status_change(self, *_args) -> None:
        self._append_log(self.status.get())

    def _append_log(self, message: str) -> None:
        if not message or message == self._last_logged_status or not hasattr(self, "log_text"):
            return
        self._last_logged_status = message
        line = f"{datetime.now().strftime('%H:%M:%S')}  {message}\n"
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line)
        line_count = int(float(self.log_text.index("end-1c").split(".")[0]))
        if line_count > 80:
            self.log_text.delete("1.0", f"{line_count - 80}.0")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _build_hex_context_menu(self) -> None:
        self.hex_context_menu = tk.Menu(self.hex_text, tearoff=False)
        self.hex_context_menu.add_command(label="复制当前 Offset", command=self.copy_current_offset)
        self.hex_context_menu.add_command(label="复制选中 Hex 字节", command=self.copy_selected_hex_bytes)
        self.hex_context_menu.add_command(label="复制选中 ASCII", command=self.copy_selected_ascii)
        self.hex_context_menu.add_separator()
        self.hex_context_menu.add_command(label="解释选中字节", command=self.show_selected_hex_interpretation)
        self.hex_text.bind("<Button-3>", self._show_hex_context_menu)

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-o>", self._shortcut(self.open_file))
        self.bind_all("<Control-O>", self._shortcut(self.open_file))
        self.bind_all("<Control-r>", self._shortcut(self.reload_file))
        self.bind_all("<Control-R>", self._shortcut(self.reload_file))
        self.bind_all("<Control-f>", self._shortcut(self.focus_search))
        self.bind_all("<Control-F>", self._shortcut(self.focus_search))
        self.bind_all("<Control-s>", self._shortcut(self.save_project_snapshot))
        self.bind_all("<Control-S>", self._shortcut(self.save_project_snapshot))
        self.bind_all("<F3>", self._shortcut(self.find_next))
        self.bind_all("<F4>", self._shortcut(self.jump_next_binary_diff))
        self.bind_all("<Control-Key-1>", self._shortcut(lambda: self.select_workspace_tab(self.hex_text, "Hex")))
        self.bind_all("<Control-Key-2>", self._shortcut(lambda: self.select_workspace_tab(self.fields, "字段")))
        self.bind_all("<Control-Key-3>", self._shortcut(lambda: self.select_workspace_tab(self.frames, "帧列表")))
        self.bind_all("<Control-Key-4>", self._shortcut(lambda: self.select_workspace_tab(self.timeline_page, "时间线")))
        self.bind_all("<Control-Key-5>", self._shortcut(lambda: self.select_workspace_tab(self.preview, "预览")))
        self.bind_all("<Control-l>", self._shortcut(self.toggle_log_panel_from_shortcut))
        self.bind_all("<Control-L>", self._shortcut(self.toggle_log_panel_from_shortcut))
        self.bind_all("<Control-Shift-H>", self._shortcut(self.export_html_report))
        self.bind_all("<Control-Shift-J>", self._shortcut(self.export_json_report))
        self.bind_all("<Control-Shift-O>", self._shortcut(self.copy_current_offset))
        self.bind_all("<Control-Shift-C>", self._shortcut(self.copy_selected_hex_bytes))
        self.bind_all("<Control-Shift-I>", self._shortcut(self.show_selected_hex_interpretation))

    def toggle_log_panel_from_shortcut(self) -> None:
        self.log_panel_visible.set(not self.log_panel_visible.get())
        self.toggle_log_panel()

    def _shortcut(self, command):
        def handler(_event=None):
            command()
            return "break"

        return handler

    def _show_hex_context_menu(self, event) -> None:
        try:
            self.hex_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.hex_context_menu.grab_release()

    def _apply_theme(self, name: str) -> None:
        self._theme_name = name
        self._palette = PALETTES[name]
        p = self._palette
        style = ttk.Style(self)
        style.theme_use("clam")
        self.configure(bg=p["bg"])
        style.configure(".", background=p["bg"], foreground=p["fg"], font=("Microsoft YaHei UI", 9))
        style.configure("Toolbar.TFrame", background=p["panel2"])
        style.configure("Panel.TFrame", background=p["panel"])
        style.configure("PanelTitle.TLabel", background=p["panel"], foreground=p["muted"], font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Toolbar.TLabel", background=p["panel2"], foreground=p["muted"])
        style.configure("ToolbarGroup.TLabel", background=p["panel2"], foreground=p["muted"], font=("Microsoft YaHei UI", 8, "bold"))
        style.configure("Toolbar.TButton", padding=(12, 6), background=p["panel"], foreground=p["fg"], bordercolor=p["border"])
        style.map("Toolbar.TButton", background=[("active", p["select"])], foreground=[("active", p["fg"])])
        style.configure("Primary.Toolbar.TButton", padding=(14, 6), background=p["accent"], foreground="#FFFFFF", bordercolor=p["accent"])
        style.map("Primary.Toolbar.TButton", background=[("active", p["select"])], foreground=[("active", "#FFFFFF")])
        style.configure("Panel.TCheckbutton", background=p["panel"], foreground=p["fg"])
        style.map("Panel.TCheckbutton", background=[("active", p["panel"])], foreground=[("active", p["fg"])])
        style.configure("Offset.TEntry", fieldbackground=p["text_bg"], foreground=p["fg"], bordercolor=p["border"], insertcolor=p["fg"])
        style.configure("TCombobox", fieldbackground=p["text_bg"], foreground=p["fg"], background=p["panel"])
        style.configure("Workbench.TNotebook", background=p["bg"], borderwidth=0)
        style.configure("Workbench.TNotebook.Tab", padding=(16, 8), background=p["panel2"], foreground=p["muted"])
        style.map("Workbench.TNotebook.Tab", background=[("selected", p["panel"])], foreground=[("selected", p["fg"])])
        style.configure(
            "Data.Treeview",
            background=p["panel"],
            foreground=p["fg"],
            fieldbackground=p["panel"],
            borderwidth=0,
            rowheight=26,
        )
        style.configure("Data.Treeview.Heading", background=p["panel2"], foreground=p["muted"], relief=tk.FLAT, padding=(8, 7))
        style.map("Data.Treeview", background=[("selected", p["select"])], foreground=[("selected", p["select_fg"])])

        self.header.configure(bg=p["bg"])
        self.logo.configure(bg=p["bg"])
        self.brand.configure(bg=p["bg"], fg=p["fg"])
        self.file_badge.configure(bg=p["bg"], fg=p["muted"])
        self.log_frame.configure(bg=p["panel"])
        self.log_header.configure(bg=p["panel"], fg=p["muted"])
        self.log_text.configure(bg=p["text_bg"], fg=p["fg"], insertbackground=p["fg"], selectbackground=p["select"], selectforeground=p["select_fg"])
        self.status_bar.configure(bg=p["panel2"], fg=p["muted"], padx=12, pady=5)
        self.summary_frame.configure(bg=p["bg"])
        self.timeline_canvas.configure(bg=p["panel"])
        for key in self.summary_cards:
            self._paint_summary_card(key, "normal")
        self._draw_logo()
        for widget in (self.hex_text, self.preview, self.diagnostics):
            widget.configure(bg=p["text_bg"], fg=p["fg"], insertbackground=p["fg"], selectbackground=p["select"], selectforeground=p["select_fg"])
        self.hex_text.tag_configure("search_hit", background=p["accent"], foreground="#FFFFFF")
        self.preview.tag_configure("binary_diff_line", background=p["warning_bg"], foreground=p["fg"])
        self.preview.tag_configure("binary_diff_active", background=p["warning"], foreground=p["bg"])
        self.preview.tag_configure("empty_title", foreground=p["accent"], font=("Microsoft YaHei UI", 14, "bold"))
        self.preview.tag_configure("empty_heading", foreground=p["accent2"], font=("Microsoft YaHei UI", 10, "bold"))
        self.preview.tag_configure("empty_muted", foreground=p["muted"], font=("Microsoft YaHei UI", 9))
        self.diagnostics.tag_configure("info", foreground=p["accent2"])
        self.diagnostics.tag_configure("warning", foreground=p["warning"])
        self.diagnostics.tag_configure("error", foreground=p["error"])
        self.diagnostics.tag_configure("heading", foreground=p["accent"], font=("Microsoft YaHei UI", 9, "bold"))
        for tree in (self.tree, self.fields, self.frames, self.timeline):
            tree.tag_configure("warning", foreground=p["warning"], background=p["warning_bg"])
            tree.tag_configure("error", foreground=p["error"], background=p["error_bg"])
            tree.tag_configure("normal", foreground=p["fg"])
            tree.tag_configure("field_number", foreground=p["field_number"])
            tree.tag_configure("field_text", foreground=p["field_text"])
            tree.tag_configure("field_hex", foreground=p["field_hex"])
            tree.tag_configure("field_bool", foreground=p["field_bool"])
        self._render_summary_cards()
        self._render_timeline_chart()

    def open_file(self) -> None:
        path = filedialog.askopenfilename(title="打开媒体文件")
        if path:
            self.load_file(Path(path))

    def open_folder(self) -> None:
        folder = filedialog.askdirectory(title="打开媒体文件夹")
        if not folder:
            return
        candidate = self._first_supported_file(Path(folder))
        if candidate is None:
            messagebox.showinfo("未找到媒体文件", "该文件夹下没有发现当前支持的媒体文件。")
            return
        self.load_file(candidate)

    def _first_supported_file(self, folder: Path) -> Path | None:
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                return path
        return None

    def _load_dropped_paths(self, paths: list[str | Path]) -> None:
        path = first_loadable_drop_path(paths)
        if path is None:
            self.status.set("拖拽内容中未找到可打开的文件")
            messagebox.showinfo("拖拽打开", "拖拽内容中没有发现可打开的文件。")
            return
        if path.is_dir():
            candidate = self._first_supported_file(path)
            if candidate is None:
                self.status.set("拖拽文件夹中未找到支持的媒体文件")
                messagebox.showinfo("拖拽打开", "拖拽文件夹中没有发现当前支持的媒体文件。")
                return
            path = candidate
        self.load_file(path)

    def _enable_windows_file_drop(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return

        self.update_idletasks()
        hwnd = self.winfo_id()
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        wm_dropfiles = 0x0233
        gwlp_wndproc = -4
        lresult = ctypes.c_ssize_t
        wndproc_type = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        set_window_long_ptr = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        set_window_long_ptr.restype = ctypes.c_void_p
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallWindowProcW.restype = lresult
        shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
        shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        shell32.DragQueryFileW.restype = wintypes.UINT
        shell32.DragFinish.argtypes = [wintypes.HANDLE]

        def dropped_files(drop_handle) -> list[str]:
            count = shell32.DragQueryFileW(drop_handle, 0xFFFFFFFF, None, 0)
            files = []
            for index in range(count):
                length = shell32.DragQueryFileW(drop_handle, index, None, 0)
                buffer = ctypes.create_unicode_buffer(length + 1)
                shell32.DragQueryFileW(drop_handle, index, buffer, length + 1)
                files.append(buffer.value)
            return files

        def wndproc(window, message, wparam, lparam):
            if message == wm_dropfiles:
                try:
                    paths = dropped_files(wparam)
                finally:
                    shell32.DragFinish(wparam)
                if paths:
                    self.after(0, lambda value=paths: self._load_dropped_paths(value))
                return 0
            return user32.CallWindowProcW(self._old_wndproc, window, message, wparam, lparam)

        self._drop_wndproc = wndproc_type(wndproc)
        self._old_wndproc = set_window_long_ptr(hwnd, gwlp_wndproc, ctypes.cast(self._drop_wndproc, ctypes.c_void_p))
        shell32.DragAcceptFiles(hwnd, True)

    def destroy(self) -> None:
        if sys.platform == "win32" and self._old_wndproc is not None and self._drop_wndproc is not None:
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                shell32 = ctypes.windll.shell32
                hwnd = self.winfo_id()
                shell32.DragAcceptFiles(wintypes.HWND(hwnd), False)
                set_window_long_ptr = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
                set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
                set_window_long_ptr.restype = ctypes.c_void_p
                set_window_long_ptr(wintypes.HWND(hwnd), -4, ctypes.c_void_p(self._old_wndproc))
            except Exception:
                pass
        super().destroy()

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.delete(0, tk.END)
        recent = [path for path in self.settings.recent_files() if Path(path).exists()]
        if not recent:
            self.recent_menu.add_command(label="暂无最近文件", state=tk.DISABLED)
            return
        for path in recent:
            label = Path(path).name
            self.recent_menu.add_command(label=label, command=lambda value=path: self.load_file(value))
        self.recent_menu.add_separator()
        self.recent_menu.add_command(label="清空最近文件", command=self.clear_recent_files)

    def clear_recent_files(self) -> None:
        self.settings.clear_recent_files()
        self._refresh_recent_menu()

    def reload_file(self) -> None:
        if self.current_file:
            self.load_file(self.current_file)

    def load_file(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            messagebox.showerror("文件不存在", str(path))
            return
        self.status.set(f"正在解析 {path}")
        self.update_idletasks()
        self.current_file = path
        self._last_search = None
        self._last_node_search = None
        self._video_preview_position_seconds = 0.0
        self._yuv_preview_frame_index = 0
        started_at = perf_counter()
        self.result = self.analyzer.analyze(path, self._raw_options_for_path(path))
        self.last_parse_elapsed_seconds = perf_counter() - started_at
        self.result.media.summary["analysis_elapsed_seconds"] = round(self.last_parse_elapsed_seconds, 6)
        self._attach_waveform_preview(path)
        self._attach_video_preview(path)
        self._attach_yuv_preview(path)
        self._render_result()
        self._load_hex(0)
        self.file_badge.configure(text=f"{path.name}  |  {self.result.media.format_name}")
        self.status.set(
            f"{path.name} | {self.result.media.format_name} | {self.result.media.size} bytes | 解析 {format_elapsed_seconds(self.last_parse_elapsed_seconds)}"
        )
        self._render_summary_cards()
        self.settings.add_recent_file(path)
        self._refresh_recent_menu()

    def configure_current_raw_options(self) -> None:
        if not self.current_file or self.current_file.suffix.lower() not in {".pcm", ".yuv"}:
            messagebox.showinfo("Raw 参数", "请先打开 .pcm 或 .yuv 文件。")
            return
        self.raw_options_by_path.pop(str(self.current_file), None)
        started_at = perf_counter()
        self.result = self.analyzer.analyze(self.current_file, self._raw_options_for_path(self.current_file, force=True))
        self.last_parse_elapsed_seconds = perf_counter() - started_at
        self.result.media.summary["analysis_elapsed_seconds"] = round(self.last_parse_elapsed_seconds, 6)
        self._yuv_preview_frame_index = 0
        self._attach_waveform_preview(self.current_file)
        self._attach_yuv_preview(self.current_file)
        self._render_result()
        self._load_hex(self.current_hex_offset)
        self._render_summary_cards()
        self.status.set(
            f"{self.current_file.name} | {self.result.media.format_name} | {self.result.media.size} bytes | 解析 {format_elapsed_seconds(self.last_parse_elapsed_seconds)}"
        )

    def _raw_options_for_path(self, path: Path, force: bool = False) -> dict:
        suffix = path.suffix.lower()
        if suffix not in {".pcm", ".yuv"}:
            return {}
        key = str(path)
        if not force and key in self.raw_options_by_path:
            return self.raw_options_by_path[key]
        if suffix == ".pcm":
            options = self._ask_pcm_options(self.raw_options_by_path.get(key, {}))
        else:
            options = self._ask_yuv_options(self.raw_options_by_path.get(key, {}))
        self.raw_options_by_path[key] = options
        return options

    def _ask_pcm_options(self, defaults: dict) -> dict:
        sample_rate = simpledialog.askinteger("Raw PCM 参数", "采样率", initialvalue=int(defaults.get("sample_rate", 48000)), minvalue=1, parent=self)
        channels = simpledialog.askinteger("Raw PCM 参数", "声道数", initialvalue=int(defaults.get("channels", 2)), minvalue=1, parent=self)
        bits = simpledialog.askinteger("Raw PCM 参数", "位深", initialvalue=int(defaults.get("bits_per_sample", 16)), minvalue=1, parent=self)
        endian_value = simpledialog.askstring("Raw PCM 参数", "大小端 little/big", initialvalue=str(defaults.get("endian", "little")), parent=self)
        endian = str(endian_value or defaults.get("endian", "little")).strip().lower()
        if endian not in {"little", "big"}:
            endian = "little"
        signed = messagebox.askyesno(
            "Raw PCM 参数",
            "样本是否为有符号整数？\n选择“否”表示无符号 PCM。",
            default="yes" if bool(defaults.get("signed", True)) else "no",
            parent=self,
        )
        return {
            "sample_rate": sample_rate or int(defaults.get("sample_rate", 48000)),
            "channels": channels or int(defaults.get("channels", 2)),
            "bits_per_sample": bits or int(defaults.get("bits_per_sample", 16)),
            "endian": endian,
            "signed": signed,
        }

    def _ask_yuv_options(self, defaults: dict) -> dict:
        width = simpledialog.askinteger("Raw YUV 参数", "宽度", initialvalue=int(defaults.get("width", 1920)), minvalue=1, parent=self)
        height = simpledialog.askinteger("Raw YUV 参数", "高度", initialvalue=int(defaults.get("height", 1080)), minvalue=1, parent=self)
        pixel_format = simpledialog.askstring("Raw YUV 参数", "像素格式", initialvalue=str(defaults.get("pixel_format", "yuv420p")), parent=self)
        fps = simpledialog.askfloat("Raw YUV 参数", "帧率", initialvalue=float(defaults.get("fps", 25)), minvalue=0.001, parent=self)
        return {
            "width": width or int(defaults.get("width", 1920)),
            "height": height or int(defaults.get("height", 1080)),
            "pixel_format": pixel_format or str(defaults.get("pixel_format", "yuv420p")),
            "fps": fps or float(defaults.get("fps", 25)),
        }

    def _render_result(self) -> None:
        if not self.result:
            return
        self._render_tree()
        self.fields.delete(*self.fields.get_children())
        self._field_range_by_iid.clear()
        self._render_frames()
        self._render_timeline()
        self._render_diagnostics()
        self._preview_images.clear()
        self._clear_binary_diff_navigation()
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, self._preview_text())
        self._render_waveform_preview()
        self._render_video_preview()
        self._render_yuv_preview()

    def _render_tree(self) -> None:
        if not self.result:
            return
        self.tree.delete(*self.tree.get_children())
        self._node_by_iid.clear()
        self._field_by_tree_iid.clear()
        self._tree_iids_in_display_order.clear()
        self._last_node_search = None
        self._insert_node("", self.result.root)

    def _render_timeline(self) -> None:
        if not self.result:
            return
        self.timeline.delete(*self.timeline.get_children())
        summary = self.result.media.summary.get("timeline_summary", {})
        issue_orders = timeline_issue_item_orders(summary)
        issue_labels = timeline_issue_labels(summary)
        filter_anomalies = self.timeline_anomaly_filter.get()
        row_order = 0
        rendered_rows = 0
        for frame in self.result.frames[:5000]:
            if filter_anomalies and row_order not in issue_orders:
                row_order += 1
                continue
            tag = timeline_item_row_tag(row_order, issue_orders)
            self.timeline.insert(
                "",
                tk.END,
                values=(
                    frame.index,
                    "",
                    self._fmt(frame.pts),
                    self._fmt(frame.dts),
                    f"0x{frame.offset:X}",
                    frame.size,
                    frame.frame_type,
                    self._fmt(frame.duration),
                    "yes" if frame.keyframe else "",
                    issue_labels.get(row_order, ""),
                ),
                tags=(tag,),
            )
            row_order += 1
            rendered_rows += 1
        row_order = len(self.result.frames)
        packet_timeline = self.result.media.summary.get("packet_timeline", {})
        for packet in packet_timeline.get("packets", [])[:1000]:
            if filter_anomalies and row_order not in issue_orders:
                row_order += 1
                continue
            tag = timeline_item_row_tag(row_order, issue_orders)
            self.timeline.insert(
                "",
                tk.END,
                values=(
                    packet.get("index", ""),
                    packet.get("stream_index", ""),
                    self._fmt(packet.get("pts")),
                    self._fmt(packet.get("dts")),
                    "" if packet.get("pos") is None else f"0x{packet.get('pos'):X}",
                    packet.get("size", ""),
                    packet.get("codec_type", "packet"),
                    self._fmt(packet.get("duration")),
                    "yes" if packet.get("keyframe") else "",
                    issue_labels.get(row_order, ""),
                ),
                tags=(tag,),
            )
            row_order += 1
            rendered_rows += 1
        if hasattr(self, "timeline_filter_label"):
            total_rows = min(len(self.result.frames), 5000) + min(len(packet_timeline.get("packets", [])), 1000)
            if filter_anomalies:
                self.timeline_filter_label.configure(text=f"显示 {rendered_rows}/{total_rows} 个时间线异常点")
            else:
                self.timeline_filter_label.configure(text=f"时间线异常 {len(issue_orders)} 处")
        self._render_timeline_chart()

    def _render_timeline_chart(self) -> None:
        canvas = getattr(self, "timeline_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        p = self._palette
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.create_rectangle(0, 0, width, height, fill=p["panel"], outline="")
        if not self.result:
            return
        packets = self.result.media.summary.get("packet_timeline", {}).get("packets", [])
        items = timeline_chart_items(self.result.frames, packets)
        if not items:
            canvas.create_text(width / 2, height / 2, text="暂无帧大小时间线", fill=p["muted"], font=("Microsoft YaHei UI", 10))
            return

        left = 18
        right = max(left + 1, width - 18)
        top = 28
        bottom = max(top + 1, height - 26)
        mid = (top + bottom) / 2
        for frac in (0.25, 0.5, 0.75):
            y = top + (bottom - top) * frac
            color = p["border"] if frac != 0.5 else p["muted"]
            canvas.create_line(left, y, right, y, fill=color)
        max_size = max(item["size"] for item in items)
        span = right - left
        slot = span / max(1, len(items))
        bar_width = max(2, min(9, slot * 0.72))
        for index, item in enumerate(items):
            x = left + index * slot + slot / 2
            bar_height = max(2, (item["size"] / max_size) * (bottom - top))
            y0 = bottom - bar_height
            color = p["accent2"] if item.get("keyframe") else p["accent"]
            canvas.create_rectangle(x - bar_width / 2, y0, x + bar_width / 2, bottom, fill=color, outline="")
            if item.get("keyframe"):
                canvas.create_line(x, top, x, min(bottom, y0), fill=p["accent2"], dash=(2, 3))
        label = f"{len(items)} 项 | max size {max_size} bytes"
        canvas.create_text(left, bottom + 13, text=label, fill=p["muted"], anchor=tk.W, font=("Microsoft YaHei UI", 9))
        self._render_timeline_legend(canvas, left, right)
        self._render_gop_structure(canvas, left, right, top, bottom)
        self._render_timestamp_curves(canvas, left, right, top, bottom)
        self._render_bitrate_curve(canvas, left, right, top, bottom)
        self._render_rtp_sequence_curve(canvas, left, right, top, bottom)
        self._render_pcr_curve(canvas, left, right, top, bottom)
        canvas.create_line(left, mid, right, mid, fill=p["border"])

    def _render_timeline_legend(self, canvas: tk.Canvas, left: int, right: int) -> None:
        if not self.result:
            return
        summary = self.result.media.summary.get("timeline_summary", {})
        p = self._palette
        items = []
        if summary.get("series"):
            if summary.get("pts", {}).get("available"):
                items.append(("PTS", p["accent2"], ()))
            if summary.get("dts", {}).get("available"):
                items.append(("DTS", p["error"], (4, 3)))
        if summary.get("bitrate", {}).get("available"):
            items.append(("Bitrate", p["warning"], ()))
        if summary.get("gop", {}).get("groups_available"):
            items.append(("GOP", p["accent2"], ()))
        if summary.get("rtp_sequence", {}).get("available"):
            items.append(("RTP", p["accent"], ()))
        if summary.get("pcr", {}).get("available"):
            items.append(("PCR", p["muted"], (5, 3)))
        if summary.get("timestamp_anomalies"):
            items.append(("Anomaly", p["error"], ()))
        if not items:
            return
        x = left
        y = 10
        font = ("Microsoft YaHei UI", 8)
        for label, color, dash in items:
            text_width = max(32, len(label) * 7)
            item_width = 28 + text_width + 10
            if x + item_width > right and x > left:
                break
            if label == "Anomaly":
                canvas.create_oval(x, y - 4, x + 8, y + 4, fill=color, outline="")
            else:
                canvas.create_line(x, y, x + 18, y, fill=color, width=2, dash=dash)
            canvas.create_text(x + 24, y, text=label, fill=p["muted"], anchor=tk.W, font=font)
            x += item_width

    def _render_gop_structure(self, canvas: tk.Canvas, left: int, right: int, top: int, bottom: int) -> None:
        if not self.result:
            return
        groups = self.result.media.summary.get("timeline_summary", {}).get("gop", {}).get("groups", [])
        if not groups:
            return
        p = self._palette
        span = right - left
        max_order = max(1, max(int(group.get("end_item_order", 0) or 0) for group in groups))
        y = bottom - 7
        for group in groups[:80]:
            start = int(group.get("start_item_order", 0) or 0)
            end = int(group.get("end_item_order", start) or start)
            x0 = left + span * max(0, start) / max_order
            x1 = left + span * min(max_order, max(start + 1, end)) / max_order
            fill = p["accent2"] if int(group.get("index", 0) or 0) % 2 == 0 else p["accent"]
            canvas.create_rectangle(x0, y, max(x0 + 2, x1), y + 4, fill=fill, outline="")
        gop = self.result.media.summary.get("timeline_summary", {}).get("gop", {})
        canvas.create_text(
            right,
            bottom + 13,
            text=f"GOP {gop.get('group_count', len(groups))} max {gop.get('max_group_frames', '')}f",
            fill=p["accent2"],
            anchor=tk.E,
            font=("Microsoft YaHei UI", 8),
        )

    def _render_timestamp_curves(self, canvas: tk.Canvas, left: int, right: int, top: int, bottom: int) -> None:
        if not self.result:
            return
        summary = self.result.media.summary.get("timeline_summary", {})
        series = summary.get("series", [])
        if not series:
            return
        values = [
            float(point[key])
            for point in series
            for key in ("pts", "dts")
            if point.get(key) is not None
        ]
        if len(values) < 2:
            return
        value_min = min(values)
        value_max = max(values)
        if value_max <= value_min:
            return
        p = self._palette
        span = right - left
        denom = max(1, len(series) - 1)
        y_span = bottom - top
        for key, color, dash in (("pts", p["accent2"], ()), ("dts", p["error"], (4, 3))):
            points = []
            for index, point in enumerate(series):
                value = point.get(key)
                if value is None:
                    continue
                x = left + span * index / denom
                y = bottom - (float(value) - value_min) / (value_max - value_min) * y_span
                points.extend([x, y])
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=1.7, dash=dash, smooth=True)
        anomalies = summary.get("timestamp_anomalies", [])
        if anomalies:
            for anomaly in anomalies[:16]:
                order = int(anomaly.get("item_order", 0) or 0)
                x = left + span * min(max(order, 0), len(series) - 1) / denom
                canvas.create_oval(x - 4, top + 3, x + 4, top + 11, fill=p["error"], outline="")
            canvas.create_text(left, top - 2, text=f"timestamp anomalies {len(anomalies)}", fill=p["error"], anchor=tk.NW, font=("Microsoft YaHei UI", 8))

    def _render_bitrate_curve(self, canvas: tk.Canvas, left: int, right: int, top: int, bottom: int) -> None:
        if not self.result:
            return
        bitrate = self.result.media.summary.get("timeline_summary", {}).get("bitrate", {})
        buckets = bitrate.get("buckets", [])
        if not bitrate.get("available") or not buckets:
            return
        p = self._palette
        max_kbps = max(float(bucket.get("kbps", 0) or 0) for bucket in buckets)
        if max_kbps <= 0:
            return
        span = right - left
        denom = max(1, len(buckets) - 1)
        points = []
        for index, bucket in enumerate(buckets):
            x = left + span * index / denom
            y = bottom - (float(bucket.get("kbps", 0) or 0) / max_kbps) * (bottom - top)
            points.extend([x, y])
        if len(points) >= 4:
            canvas.create_line(*points, fill=p["warning"], width=2, smooth=True)
        canvas.create_text(right, top - 2, text=f"peak {max_kbps:.1f} kbps", fill=p["warning"], anchor=tk.NE, font=("Microsoft YaHei UI", 8))

    def _render_rtp_sequence_curve(self, canvas: tk.Canvas, left: int, right: int, top: int, bottom: int) -> None:
        if not self.result:
            return
        rtp = self.result.media.summary.get("timeline_summary", {}).get("rtp_sequence", {})
        series = rtp.get("series", [])
        if not rtp.get("available") or len(series) < 2:
            return
        p = self._palette
        values = []
        for point in series:
            try:
                values.append(int(point.get("sequence", 0) or 0))
            except (TypeError, ValueError):
                continue
        if len(values) < 2:
            return
        value_min = min(values)
        value_max = max(values)
        if value_max <= value_min:
            value_max = value_min + 1
        span = right - left
        denom = max(1, len(series) - 1)
        y_span = bottom - top
        points = []
        marker_points = []
        for index, point in enumerate(series):
            try:
                sequence = int(point.get("sequence", 0) or 0)
            except (TypeError, ValueError):
                continue
            x = left + span * index / denom
            y = bottom - (sequence - value_min) / (value_max - value_min) * y_span
            points.extend([x, y])
            if point.get("marker"):
                marker_points.append((x, y))
        if len(points) >= 4:
            canvas.create_line(*points, fill=p["accent"], width=1.8, smooth=True)
        for x, y in marker_points[:48]:
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=p["accent2"], outline="")
        warning_orders = [int(item.get("item_order", 0) or 0) for item in rtp.get("warnings", [])[:24]]
        max_order = max(1, max((int(point.get("item_order", 0) or 0) for point in series), default=0))
        for order in warning_orders:
            x = left + span * min(max(order, 0), max_order) / max_order
            canvas.create_oval(x - 4, bottom - 11, x + 4, bottom - 3, fill=p["error"], outline="")
        canvas.create_text(
            left,
            bottom + 2,
            text=f"RTP seq warnings {rtp.get('sequence_warnings', 0)}",
            fill=p["accent"],
            anchor=tk.SW,
            font=("Microsoft YaHei UI", 8),
        )

    def _render_pcr_curve(self, canvas: tk.Canvas, left: int, right: int, top: int, bottom: int) -> None:
        if not self.result:
            return
        pcr = self.result.media.summary.get("timeline_summary", {}).get("pcr", {})
        series = pcr.get("series", [])
        if not pcr.get("available") or len(series) < 2:
            return
        values = []
        for point in series:
            try:
                values.append(float(point.get("seconds", 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
        if len(values) < 2:
            return
        value_min = min(values)
        value_max = max(values)
        if value_max <= value_min:
            value_max = value_min + 1
        p = self._palette
        span = right - left
        denom = max(1, len(series) - 1)
        y_span = bottom - top
        points = []
        for index, point in enumerate(series):
            try:
                seconds = float(point.get("seconds", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            x = left + span * index / denom
            y = bottom - (seconds - value_min) / (value_max - value_min) * y_span
            points.extend([x, y])
        if len(points) >= 4:
            canvas.create_line(*points, fill=p["muted"], width=1.6, dash=(5, 3), smooth=True)
        canvas.create_text(
            right,
            top + 10,
            text=f"PCR {pcr.get('points', 0)} pts",
            fill=p["muted"],
            anchor=tk.NE,
            font=("Microsoft YaHei UI", 8),
        )

    def _render_frames(self) -> None:
        if not self.result:
            return
        self.frames.delete(*self.frames.get_children())
        self._frame_offset_by_iid.clear()
        for frame in self.result.frames[:5000]:
            iid = self.frames.insert(
                "",
                tk.END,
                values=(
                    frame.index,
                    f"0x{frame.offset:X}",
                    frame.size,
                    self._fmt(frame.pts),
                    self._fmt(frame.dts),
                    self._fmt(frame.duration),
                    frame.frame_type,
                    "yes" if frame.keyframe else "",
                ),
                tags=("normal",),
            )
            self._frame_offset_by_iid[iid] = (frame.offset, frame.size)

    def _render_diagnostics(self) -> None:
        if not self.result:
            return
        self.diagnostics.delete("1.0", tk.END)
        self.diagnostics.insert(tk.END, "媒体摘要\n", ("heading",))
        summary = {
            key: value
            for key, value in self.result.media.summary.items()
            if key not in {"waveform", "packet_timeline"}
        }
        self.diagnostics.insert(tk.END, json.dumps(summary, ensure_ascii=False, indent=2))
        self.diagnostics.insert(tk.END, "\n\n诊断\n", ("heading",))
        if not self.result.diagnostics:
            self.diagnostics.insert(tk.END, "未发现 warning/error\n", ("info",))
            return
        for issue in self.result.diagnostics:
            offset = "" if issue.offset is None else f" offset=0x{issue.offset:X}"
            tag = "error" if issue.severity == Severity.ERROR else "warning" if issue.severity == Severity.WARNING else "info"
            self.diagnostics.insert(tk.END, f"[{issue.severity.value}] {issue.message}{offset}\n", (tag,))

    def _insert_node(self, parent: str, node: ParseNode) -> None:
        if self.issue_filter.get() and not node_has_issue(node):
            return
        tag = "error" if node.severity == Severity.ERROR else "warning" if node.severity == Severity.WARNING else "normal"
        visible_children = [
            child for child in node.children if not self.issue_filter.get() or node_has_issue(child)
        ]
        iid = self.tree.insert(
            parent,
            tk.END,
            text=node.name,
            values=(node.node_type, "", f"0x{node.offset:X}", node.size),
            open=self.issue_filter.get() or len(visible_children) < 64,
            tags=(tag,),
        )
        self._node_by_iid[iid] = node
        self._tree_iids_in_display_order.append(iid)
        for field in node.fields:
            if self.issue_filter.get() and field.severity not in {Severity.WARNING, Severity.ERROR}:
                continue
            field_tag = field_tree_tag(field)
            field_iid = self.tree.insert(
                iid,
                tk.END,
                text=f"[字段] {field.name}",
                values=("字段", format_field_value(field.value), f"0x{field.offset:X}", field_highlight_size(field)),
                tags=(field_tag,),
            )
            self._field_by_tree_iid[field_iid] = (node, field)
        for child in visible_children:
            self._insert_node(iid, child)

    def on_tree_select(self, _event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        node = self._node_by_iid.get(selection[0])
        if node:
            self._render_fields(node)
            self._load_hex(node.offset)
            return
        field_entry = self._field_by_tree_iid.get(selection[0])
        if field_entry:
            node, field = field_entry
            self._render_fields(node)
            self._load_hex(field.offset)
            self._highlight_hex_range(field.offset, min(field_highlight_size(field), 4096))
            self.status.set(f"字段 {field.name} offset=0x{field.offset:X}, size={field_highlight_size(field)}")

    def _render_fields(self, node: ParseNode) -> None:
        self.fields.delete(*self.fields.get_children())
        self._field_range_by_iid.clear()
        for field in node.fields:
            bit_info = f"{field.bit_offset or 0}/{field.bit_length or 0}" if field.bit_offset is not None or field.bit_length is not None else str(field.size)
            tag = "error" if field.severity == Severity.ERROR else "warning" if field.severity == Severity.WARNING else "normal"
            iid = self.fields.insert(
                "",
                tk.END,
                values=(field.name, field.value, field.hex_value, f"0x{field.offset:X}", bit_info, field.description),
                tags=(tag,),
            )
            self._field_range_by_iid[iid] = (field.offset, field_highlight_size(field))

    def on_field_select(self, _event) -> None:
        selection = self.fields.selection()
        if not selection:
            return
        field_range = self._field_range_by_iid.get(selection[0])
        if not field_range:
            return
        offset, size = field_range
        self._load_hex(offset)
        self._highlight_hex_range(offset, min(size, 4096))
        self.status.set(f"字段 offset=0x{offset:X}, size={size}")

    def on_frame_select(self, _event) -> None:
        selection = self.frames.selection()
        if not selection:
            return
        frame_range = self._frame_offset_by_iid.get(selection[0])
        if not frame_range:
            return
        offset, size = frame_range
        self._load_hex(offset)
        self._highlight_hex_range(offset, min(size, 4096))
        self.status.set(f"帧 offset=0x{offset:X}, size={size}")

    def _preview_text(self) -> str:
        if not self.result:
            return ""
        lines = [
            f"文件: {self.current_file}",
            f"格式: {self.result.media.format_name}",
            f"大小: {self.result.media.size} bytes",
            "",
        ]
        ffprobe = self.result.media.summary.get("ffprobe", {})
        if ffprobe.get("available"):
            lines.append("ffprobe 流信息")
            for stream in ffprobe.get("streams", []):
                parts = [
                    f"#{stream.get('index')}",
                    stream.get("codec_type", ""),
                    stream.get("codec_name", ""),
                    f"{stream.get('width')}x{stream.get('height')}" if stream.get("width") and stream.get("height") else "",
                    f"{stream.get('sample_rate')} Hz" if stream.get("sample_rate") else "",
                    f"{stream.get('channels')} ch" if stream.get("channels") else "",
                    f"duration={stream.get('duration')}" if stream.get("duration") else "",
                ]
                lines.append("  " + " ".join(str(part) for part in parts if part))
            lines.append("")
        waveform = self.result.media.summary.get("waveform", {})
        if waveform.get("available"):
            lines.append("音频波形摘要")
            lines.append(
                f"  sample_rate={waveform.get('sample_rate')} channels={waveform.get('channels')} "
                f"duration={self._fmt(waveform.get('duration_seconds'))}"
            )
            energy = waveform.get("energy", {})
            if energy:
                lines.append(
                    "  "
                    f"peak={_format_dbfs(energy.get('peak_dbfs'))} "
                    f"rms={_format_dbfs(energy.get('rms_dbfs'))} "
                    f"clipped={energy.get('clipped_samples', 0)} samples"
                )
            lines.append(waveform.get("ascii", ""))
            lines.append("")
        waveform_preview = self.result.media.summary.get("waveform_preview", {})
        if waveform_preview.get("available") and waveform_preview.get("path"):
            lines.append(
                f"音频波形预览: 已生成 {waveform_preview.get('width')}x{waveform_preview.get('height')}，见下方画面。"
            )
            lines.append("音频播放: 可使用“分析 / 播放音频片段”试听默认片段，或用“播放指定音频片段”选择起始时间和时长。")
            lines.append("")
        elif waveform_preview.get("error"):
            lines.append(f"音频波形预览: {waveform_preview.get('error')}")
            lines.append("")
        frame_preview = format_frame_preview_lines(self.result.frames, self.result.media.summary.get("frame_stats", {}))
        if frame_preview:
            lines.extend(frame_preview)
            lines.append("")
        timeline_preview = format_timeline_summary_lines(self.result.media.summary.get("timeline_summary", {}))
        if timeline_preview:
            lines.extend(timeline_preview)
            lines.append("")
        video_preview = self.result.media.summary.get("video_preview", {})
        if video_preview.get("available") and video_preview.get("path"):
            shape = ""
            if video_preview.get("width") and video_preview.get("height"):
                shape = f" ({video_preview.get('width')}x{video_preview.get('height')})"
            position = float(video_preview.get("position_seconds") or 0.0)
            lines.extend("  " + line for line in format_video_frame_info_lines(video_preview.get("frame_info", {})))
            lines.append(f"视频预览帧: {format_seconds_timecode(position)} 已生成{shape}，见下方画面。")
            lines.append("")
        elif video_preview.get("error"):
            lines.append(f"视频预览帧: {video_preview.get('error')}")
            lines.append("")
        yuv_preview = self.result.media.summary.get("yuv_preview", {})
        if yuv_preview.get("available") and yuv_preview.get("path"):
            frame_index = int(yuv_preview.get("frame_index", 0))
            total_frames = int(yuv_preview.get("total_frames", 0))
            lines.append(
                f"Raw YUV 预览帧: #{frame_index + 1}/{total_frames} 已生成 {yuv_preview.get('width')}x{yuv_preview.get('height')} "
                f"{yuv_preview.get('pixel_format')}，见下方画面。"
            )
            lines.append("")
        elif yuv_preview.get("error"):
            lines.append(f"Raw YUV 预览帧: {yuv_preview.get('error')}")
            lines.append("")
        packet_timeline = self.result.media.summary.get("packet_timeline", {})
        packets = packet_timeline.get("packets", [])
        if packets:
            lines.append(f"packet 时间线: 已提取前 {len(packets)} 个 packet，详见“时间线”页。")
            packet_stats = self.result.media.summary.get("packet_stats", {})
            if packet_stats.get("available"):
                lines.append(
                    f"packet 统计: streams={packet_stats.get('streams')} keyframes={packet_stats.get('keyframes')} "
                    f"average={packet_stats.get('average_size')} bytes max={packet_stats.get('max_size')} bytes"
                )
        if not packets and not waveform.get("available") and not self.result.frames:
            lines.append("当前文件暂无可预览波形或 packet 时间线；仍可查看协议树、字段和 Hex。")
        return "\n".join(lines)

    def _attach_video_preview(self, path: Path) -> None:
        if not self.result:
            return
        streams = self.result.media.summary.get("ffprobe", {}).get("streams", [])
        if not any(stream.get("codec_type") == "video" for stream in streams):
            return
        self.result.media.summary["video_preview"] = build_video_preview(
            path,
            position_seconds=self._video_preview_position_seconds,
        )

    def _attach_waveform_preview(self, path: Path) -> None:
        if not self.result or self.result.media.format_name not in {"WAV", "Raw PCM"}:
            return
        self.result.media.summary["waveform_preview"] = build_waveform_preview(
            path,
            self.result.media.format_name,
            self.result.media.summary,
        )

    def _attach_yuv_preview(self, path: Path) -> None:
        if not self.result or self.result.media.format_name != "Raw YUV":
            return
        summary = self.result.media.summary
        self.result.media.summary["yuv_preview"] = build_yuv_preview(
            path,
            int(summary.get("width", 0)),
            int(summary.get("height", 0)),
            str(summary.get("pixel_format", "")),
            frame_index=self._yuv_preview_frame_index,
        )

    def _render_video_preview(self) -> None:
        if not self.result:
            return
        video_preview = self.result.media.summary.get("video_preview", {})
        image_path = video_preview.get("path")
        if not image_path:
            return
        try:
            image = tk.PhotoImage(file=str(image_path))
        except tk.TclError as exc:
            self.preview.insert(tk.END, f"\n视频预览帧画面加载失败: {exc}")
            return
        self._preview_images.append(image)
        position = float(video_preview.get("position_seconds") or 0.0)
        self.preview.insert(tk.END, f"\n视频预览帧 {format_seconds_timecode(position)}\n")
        self.preview.image_create(tk.END, image=image)
        self.preview.insert(tk.END, "\n")
        frame_lines = format_video_frame_info_lines(video_preview.get("frame_info", {}))
        if frame_lines:
            self.preview.insert(tk.END, "\n".join(frame_lines) + "\n")

    def step_video_preview(self, delta_seconds: float) -> None:
        if not self.current_file or not self.result:
            messagebox.showinfo("视频预览", "请先打开含视频流的媒体文件。")
            return
        streams = self.result.media.summary.get("ffprobe", {}).get("streams", [])
        if not any(stream.get("codec_type") == "video" for stream in streams):
            messagebox.showinfo("视频预览", "当前文件未发现可预览的视频流。")
            return
        current = float(self.result.media.summary.get("video_preview", {}).get("position_seconds") or self._video_preview_position_seconds)
        duration = self._video_preview_duration_seconds()
        target = max(0.0, current + float(delta_seconds))
        if duration is not None:
            target = min(target, max(0.0, duration - 0.001))
        self._video_preview_position_seconds = target
        self.status.set(f"正在生成视频预览帧 {format_seconds_timecode(target)}...")
        self.update_idletasks()
        preview = build_video_preview(self.current_file, position_seconds=target)
        self.result.media.summary["video_preview"] = preview
        self._render_result()
        self.tabs.select(self.preview)
        if preview.get("error"):
            self.status.set(f"视频预览帧生成失败: {preview.get('error')}")
        else:
            self.status.set(f"已生成视频预览帧 {format_seconds_timecode(target)}")

    def jump_video_preview_time(self) -> None:
        if not self.current_file or not self.result:
            messagebox.showinfo("视频预览", "请先打开含视频流的媒体文件。")
            return
        streams = self.result.media.summary.get("ffprobe", {}).get("streams", [])
        if not any(stream.get("codec_type") == "video" for stream in streams):
            messagebox.showinfo("视频预览", "当前文件未发现可预览的视频流。")
            return
        current = float(self.result.media.summary.get("video_preview", {}).get("position_seconds") or self._video_preview_position_seconds)
        duration = self._video_preview_duration_seconds()
        prompt = "目标时间（秒）"
        if duration is not None:
            prompt += f"，范围 0 - {duration:.3f}"
        target = simpledialog.askfloat("跳转预览时间", prompt, initialvalue=current, minvalue=0.0, parent=self)
        if target is None:
            return
        if duration is not None:
            target = min(float(target), max(0.0, duration - 0.001))
        self._video_preview_position_seconds = max(0.0, float(target))
        self.status.set(f"正在生成视频预览帧 {format_seconds_timecode(self._video_preview_position_seconds)}...")
        self.update_idletasks()
        preview = build_video_preview(self.current_file, position_seconds=self._video_preview_position_seconds)
        self.result.media.summary["video_preview"] = preview
        self._render_result()
        self.tabs.select(self.preview)
        if preview.get("error"):
            self.status.set(f"视频预览帧生成失败: {preview.get('error')}")
        else:
            self.status.set(f"已跳转视频预览帧 {format_seconds_timecode(self._video_preview_position_seconds)}")

    def jump_video_preview_frame_index(self) -> None:
        if not self.current_file or not self.result:
            messagebox.showinfo("视频预览", "请先打开含视频流的媒体文件。")
            return
        streams = self.result.media.summary.get("ffprobe", {}).get("streams", [])
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        if not video_streams:
            messagebox.showinfo("视频预览", "当前文件未发现可预览的视频流。")
            return
        max_frame = None
        for stream in video_streams:
            try:
                frames = int(stream.get("nb_frames") or 0)
            except (TypeError, ValueError):
                continue
            if frames > 0:
                max_frame = frames - 1
                break
        prompt = "目标视频帧序号（从 0 开始）"
        if max_frame is not None:
            prompt += f"，范围 0 - {max_frame}"
        target_index = simpledialog.askinteger("跳转预览帧号", prompt, initialvalue=0, minvalue=0, maxvalue=max_frame, parent=self)
        if target_index is None:
            return
        self.status.set(f"正在定位视频帧 #{target_index}...")
        self.update_idletasks()
        match = find_video_frame_time(self.current_file, target_index)
        if not match.get("available"):
            messagebox.showinfo("视频预览", f"帧号定位不可用: {match.get('error')}")
            self.status.set(f"帧号定位不可用: {match.get('error')}")
            return
        if match.get("error"):
            messagebox.showinfo("视频预览", f"未找到视频帧 #{target_index}: {match.get('error')}")
            self.status.set(f"未找到视频帧 #{target_index}: {match.get('error')}")
            return
        target = max(0.0, float(match.get("position_seconds") or 0.0))
        self._video_preview_position_seconds = target
        self.status.set(f"正在生成视频帧 #{target_index} 预览 {format_seconds_timecode(target)}...")
        self.update_idletasks()
        preview = build_video_preview(self.current_file, position_seconds=target)
        if match.get("frame_info") and not preview.get("frame_info", {}).get("available"):
            preview["frame_info"] = match["frame_info"]
        self.result.media.summary["video_preview"] = preview
        self._render_result()
        self.tabs.select(self.preview)
        if preview.get("error"):
            self.status.set(f"视频帧 #{target_index} 预览生成失败: {preview.get('error')}")
        else:
            self.status.set(f"已跳转到视频帧 #{target_index} {format_seconds_timecode(target)}")

    def jump_video_preview_keyframe(self, direction: int) -> None:
        if not self.current_file or not self.result:
            messagebox.showinfo("视频预览", "请先打开含视频流的媒体文件。")
            return
        streams = self.result.media.summary.get("ffprobe", {}).get("streams", [])
        if not any(stream.get("codec_type") == "video" for stream in streams):
            messagebox.showinfo("视频预览", "当前文件未发现可预览的视频流。")
            return
        current = float(self.result.media.summary.get("video_preview", {}).get("position_seconds") or self._video_preview_position_seconds)
        label = "下一关键帧" if direction >= 0 else "上一关键帧"
        self.status.set(f"正在查找{label}...")
        self.update_idletasks()
        match = find_video_keyframe_time(
            self.current_file,
            start_seconds=current,
            direction=direction,
            packet_timeline=self.result.media.summary.get("packet_timeline", {}),
        )
        if not match.get("available"):
            messagebox.showinfo("视频预览", f"{label}定位不可用: {match.get('error')}")
            self.status.set(f"{label}定位不可用: {match.get('error')}")
            return
        if match.get("error"):
            messagebox.showinfo("视频预览", f"未找到{label}: {match.get('error')}")
            self.status.set(f"未找到{label}: {match.get('error')}")
            return
        target = max(0.0, float(match.get("position_seconds") or 0.0))
        duration = self._video_preview_duration_seconds()
        if duration is not None:
            target = min(target, max(0.0, duration - 0.001))
        self._video_preview_position_seconds = target
        self.status.set(f"正在生成{label}预览 {format_seconds_timecode(target)}...")
        self.update_idletasks()
        preview = build_video_preview(self.current_file, position_seconds=target)
        self.result.media.summary["video_preview"] = preview
        self._render_result()
        self.tabs.select(self.preview)
        if preview.get("error"):
            self.status.set(f"{label}预览生成失败: {preview.get('error')}")
        else:
            self.status.set(f"已跳转到{label} {format_seconds_timecode(target)}")

    def _video_preview_duration_seconds(self) -> float | None:
        if not self.result:
            return None
        ffprobe = self.result.media.summary.get("ffprobe", {})
        candidates = [stream.get("duration") for stream in ffprobe.get("streams", []) if stream.get("codec_type") == "video"]
        candidates.append(ffprobe.get("format", {}).get("duration"))
        values = []
        for value in candidates:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                values.append(parsed)
        return max(values) if values else None

    def _render_waveform_preview(self) -> None:
        if not self.result:
            return
        waveform_preview = self.result.media.summary.get("waveform_preview", {})
        image_path = waveform_preview.get("path")
        if not image_path:
            return
        try:
            image = tk.PhotoImage(file=str(image_path))
        except tk.TclError as exc:
            self.preview.insert(tk.END, f"\n音频波形图加载失败: {exc}")
            return
        self._preview_images.append(image)
        self.preview.insert(tk.END, "\n音频波形图\n")
        self.preview.image_create(tk.END, image=image)
        self.preview.insert(tk.END, "\n")

    def play_audio_preview(self) -> None:
        self._play_audio_preview_range(0.0, 3.0)

    def play_audio_preview_range(self) -> None:
        start = simpledialog.askfloat("播放指定音频片段", "起始时间（秒）", initialvalue=0.0, minvalue=0.0, parent=self)
        if start is None:
            return
        duration = simpledialog.askfloat("播放指定音频片段", "播放时长（秒）", initialvalue=3.0, minvalue=0.1, parent=self)
        if duration is None:
            return
        self._play_audio_preview_range(float(start), float(duration))

    def _play_audio_preview_range(self, start_seconds: float, duration_seconds: float) -> None:
        if not self.current_file or not self.result:
            messagebox.showinfo("音频预览", "请先打开包含音频的文件。")
            return
        if not self._current_file_can_preview_audio():
            messagebox.showinfo("音频预览", "当前文件未发现可播放的音频片段。")
            return
        self.status.set(f"正在生成音频预览片段 {format_seconds_timecode(start_seconds)}...")
        self.update_idletasks()
        clip = build_audio_preview_clip(
            self.current_file,
            self.result.media.format_name,
            self.result.media.summary,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
        )
        if not clip.get("available") or not clip.get("path"):
            self.status.set(f"音频预览片段生成失败: {clip.get('error', 'unknown error')}")
            return
        playback = play_audio_preview_clip(clip["path"])
        if playback.get("error"):
            self.status.set(f"音频播放失败: {playback.get('error')}")
            return
        duration = format_seconds_timecode(float(clip.get("duration_seconds") or 0.0))
        start = format_seconds_timecode(float(clip.get("start_seconds") or 0.0))
        self.status.set(f"正在播放音频片段 {start} + {duration}: {clip.get('path')}")

    def stop_audio_preview(self) -> None:
        result = stop_audio_preview()
        if result.get("error"):
            self.status.set(f"停止音频播放失败: {result.get('error')}")
        else:
            self.status.set("已停止音频播放")

    def _current_file_can_preview_audio(self) -> bool:
        if not self.result:
            return False
        if self.result.media.format_name in {"WAV", "Raw PCM"}:
            return True
        streams = self.result.media.summary.get("ffprobe", {}).get("streams", [])
        return any(stream.get("codec_type") == "audio" for stream in streams)

    def _render_yuv_preview(self) -> None:
        if not self.result:
            return
        yuv_preview = self.result.media.summary.get("yuv_preview", {})
        image_path = yuv_preview.get("path")
        if not image_path:
            return
        try:
            image = tk.PhotoImage(file=str(image_path))
        except tk.TclError as exc:
            self.preview.insert(tk.END, f"\nRaw YUV 预览帧画面加载失败: {exc}")
            return
        self._preview_images.append(image)
        frame_index = int(yuv_preview.get("frame_index", 0))
        total_frames = int(yuv_preview.get("total_frames", 0))
        self.preview.insert(tk.END, f"\nRaw YUV 预览帧 #{frame_index + 1}/{total_frames}\n")
        self.preview.image_create(tk.END, image=image)
        self.preview.insert(tk.END, "\n")

    def step_yuv_preview(self, delta_frames: int) -> None:
        if not self.current_file or not self.result or self.result.media.format_name != "Raw YUV":
            messagebox.showinfo("Raw YUV 预览", "请先打开 Raw YUV 文件。")
            return
        summary = self.result.media.summary
        current = int(summary.get("yuv_preview", {}).get("frame_index", self._yuv_preview_frame_index))
        total_frames = int(summary.get("yuv_preview", {}).get("total_frames", summary.get("frames", 0)) or 0)
        if total_frames <= 0:
            messagebox.showinfo("Raw YUV 预览", "当前 Raw YUV 参数下没有完整帧。")
            return
        target = min(max(0, current + int(delta_frames)), total_frames - 1)
        self._yuv_preview_frame_index = target
        self.status.set(f"正在生成 Raw YUV 预览帧 #{target + 1}/{total_frames}...")
        self.update_idletasks()
        preview = build_yuv_preview(
            self.current_file,
            int(summary.get("width", 0)),
            int(summary.get("height", 0)),
            str(summary.get("pixel_format", "")),
            frame_index=target,
        )
        self.result.media.summary["yuv_preview"] = preview
        self._render_result()
        self.tabs.select(self.preview)
        if preview.get("error"):
            self.status.set(f"Raw YUV 预览帧生成失败: {preview.get('error')}")
        else:
            self.status.set(f"已生成 Raw YUV 预览帧 #{target + 1}/{total_frames}")

    def _load_hex(self, offset: int) -> None:
        if not self.current_file:
            return
        self.current_hex_offset = max(0, offset)
        with ByteSource(self.current_file) as source:
            data = source.read_at(self.current_hex_offset, 4096)
        self.hex_text.delete("1.0", tk.END)
        self.hex_text.insert(tk.END, format_hex(data, self.current_hex_offset))
        self.offset_entry.delete(0, tk.END)
        self.offset_entry.insert(0, f"0x{self.current_hex_offset:X}")

    def find_next(self) -> None:
        if not self.current_file:
            messagebox.showinfo("未打开文件", "请先打开一个文件。")
            return
        if self.search_mode.get() == "node":
            self.find_next_protocol_node()
            return
        try:
            pattern = parse_search_pattern(self.search_var.get(), self.search_mode.get())
        except SearchPatternError as exc:
            messagebox.showerror("搜索内容无效", str(exc))
            return
        start = self.current_hex_offset
        current_key = (self.search_var.get(), self.search_mode.get())
        if self._last_search and self._last_search[:2] == current_key:
            start = self._last_search[2] + 1
        found = find_pattern(self.current_file, pattern, start)
        if found is None:
            self._last_search = None
            self.status.set("未找到匹配内容")
            messagebox.showinfo("搜索完成", "未找到更多匹配内容。")
            return
        self._last_search = (current_key[0], current_key[1], found)
        self._load_hex(max(0, found - 128))
        self._highlight_hex_range(found, len(pattern))
        self.status.set(f"找到匹配内容 offset=0x{found:X}, size={len(pattern)}")

    def find_next_protocol_node(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            self.status.set("请输入协议节点搜索内容")
            return
        matches = [
            (index, iid)
            for index, iid in enumerate(self._tree_iids_in_display_order)
            if node_matches_query(self._node_by_iid[iid], query)
        ]
        if not matches:
            self._last_node_search = None
            self.status.set(f"未找到协议节点: {query}")
            return
        start_index = -1
        if self._last_node_search and self._last_node_search[0] == query:
            start_index = self._last_node_search[1]
        elif self.tree.selection():
            selected = self.tree.selection()[0]
            if selected in self._tree_iids_in_display_order:
                start_index = self._tree_iids_in_display_order.index(selected)
        next_match = next(((index, iid) for index, iid in matches if index > start_index), matches[0])
        index, iid = next_match
        self._last_node_search = (query, index)
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self.on_tree_select(None)
        node = self._node_by_iid[iid]
        self.status.set(f"找到协议节点: {node.name} offset=0x{node.offset:X}")

    def toggle_issue_filter(self) -> None:
        self._render_tree()
        self.fields.delete(*self.fields.get_children())
        mode = "只看异常" if self.issue_filter.get() else "显示全部节点"
        self.status.set(f"协议树已切换为: {mode}")

    def toggle_timeline_anomaly_filter(self) -> None:
        self._render_timeline()
        mode = "只看时间异常" if self.timeline_anomaly_filter.get() else "显示全部时间线"
        self.status.set(f"时间线已切换为 {mode}")

    def _highlight_hex_range(self, offset: int, size: int) -> None:
        self.hex_text.tag_remove("search_hit", "1.0", tk.END)
        if size <= 0:
            return
        start = max(offset, self.current_hex_offset)
        end = min(offset + size, self.current_hex_offset + 4096)
        current = start
        while current < end:
            relative = current - self.current_hex_offset
            line = relative // 16
            byte_index = relative % 16
            count = min(16 - byte_index, end - current)
            start_col = 10 + byte_index * 3
            end_col = start_col + count * 3 - 1
            self.hex_text.tag_add("search_hit", f"{line + 1}.{start_col}", f"{line + 1}.{end_col}")
            current += count

    def focus_search(self) -> None:
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

    def copy_current_offset(self) -> None:
        self._copy_to_clipboard(f"0x{self.current_hex_offset:X}")
        self.status.set(f"已复制当前 Offset: 0x{self.current_hex_offset:X}")

    def copy_selected_hex_bytes(self) -> None:
        data = self._selected_hex_bytes()
        if not data:
            self.status.set("未选择可复制的 Hex 字节")
            return
        self._copy_to_clipboard(data.hex(" ").upper())
        self.status.set(f"已复制 {len(data)} 个 Hex 字节")

    def copy_selected_ascii(self) -> None:
        data = self._selected_hex_bytes()
        if not data:
            self.status.set("未选择可复制的 ASCII 内容")
            return
        self._copy_to_clipboard(hex_bytes_to_ascii(data))
        self.status.set(f"已复制 {len(data)} 个 ASCII 字符")

    def show_selected_hex_interpretation(self) -> None:
        data = self._selected_hex_bytes()
        if not data:
            self.status.set("未选择可解释的 Hex 字节")
            return
        text = format_hex_interpretation(data, self.hex_endian.get())
        self.diagnostics.delete("1.0", tk.END)
        self.diagnostics.insert(tk.END, text, ("info",))
        self.tabs.select(self.hex_text)
        self.status.set(f"已解释 {len(data)} 个字节 ({self.hex_endian.get()} endian)")

    def show_timestamp_calculator(self) -> None:
        timestamp = simpledialog.askinteger("时间戳计算器", "时间戳 / 帧序号", initialvalue=0, parent=self)
        if timestamp is None:
            return
        denominator = simpledialog.askinteger("时间戳计算器", "time_base 分母或 FPS", initialvalue=90000, minvalue=1, parent=self)
        if denominator is None:
            return
        numerator = simpledialog.askinteger("时间戳计算器", "time_base 分子", initialvalue=1, minvalue=1, parent=self)
        if numerator is None:
            return
        seconds = calculate_timestamp_seconds(timestamp, numerator, denominator)
        text = "\n".join(
            [
                "时间戳计算器",
                f"输入值: {timestamp}",
                f"time_base: {numerator}/{denominator}",
                f"秒数: {seconds:.6f}s",
                f"时间码: {format_seconds_timecode(seconds)}",
            ]
        )
        self.diagnostics.delete("1.0", tk.END)
        self.diagnostics.insert(tk.END, text, ("info",))
        self.status.set(f"时间戳换算完成: {seconds:.6f}s")

    def show_bitrate_calculator(self) -> None:
        default_size = self.result.media.size if self.result else 1_048_576
        default_duration = self._current_duration_seconds() or 1.0
        size = simpledialog.askinteger("码率计算器", "数据大小 bytes", initialvalue=int(default_size), minvalue=1, parent=self)
        if size is None:
            return
        duration = simpledialog.askfloat("码率计算器", "时长 seconds", initialvalue=float(default_duration), minvalue=0.000001, parent=self)
        if duration is None:
            return
        bitrate = calculate_bitrate_kbps(size, duration)
        text = "\n".join(
            [
                "码率计算器",
                f"数据大小: {size:,} bytes",
                f"时长: {duration:.6f}s",
                f"码率: {bitrate:.3f} kbps",
                f"约等于: {bitrate / 1000:.6f} Mbps",
            ]
        )
        self.diagnostics.delete("1.0", tk.END)
        self.diagnostics.insert(tk.END, text, ("info",))
        self.status.set(f"码率计算完成: {bitrate:.3f} kbps")

    def _current_duration_seconds(self) -> float | None:
        if not self.result:
            return None
        summary = self.result.media.summary
        for key in ("duration_seconds", "duration"):
            value = float_or_none(summary.get(key))
            if value:
                return value
        ffprobe_format = summary.get("ffprobe", {}).get("format", {})
        return float_or_none(ffprobe_format.get("duration"))

    def _selected_hex_bytes(self) -> bytes:
        try:
            text = self.hex_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return b""
        return extract_hex_bytes_from_dump_text(text)

    def _copy_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    def jump_hex(self) -> None:
        try:
            self._load_hex(parse_offset(self.offset_entry.get()))
        except ValueError as exc:
            messagebox.showerror("Offset 无效", str(exc))

    def export_html_report(self) -> None:
        if not self.result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML", "*.html")])
        if path:
            export_html(self.result, path, notes=self._ask_report_notes())

    def export_json_report(self) -> None:
        if not self.result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            export_json(self.result, path, notes=self._ask_report_notes())

    def export_csv_report(self) -> None:
        if not self.result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            export_csv(self.result, path, notes=self._ask_report_notes())

    def save_project_snapshot(self) -> None:
        if not self.result:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".avscope.json",
            filetypes=[("AVScope Project", "*.avscope.json"), ("JSON", "*.json")],
        )
        if path:
            raw_options = {}
            if self.current_file:
                raw_options = self.raw_options_by_path.get(str(self.current_file), {})
            export_project(self.result, path, raw_options, notes=self._ask_report_notes())
            self.status.set(f"工程已保存: {path}")

    def _ask_report_notes(self) -> str:
        note = simpledialog.askstring("报告备注", "用户备注（可留空）", parent=self)
        return "" if note is None else note.strip()

    def compare_files(self) -> None:
        left = filedialog.askopenfilename(title="选择左侧文件")
        if not left:
            return
        right = filedialog.askopenfilename(title="选择右侧文件")
        if not right:
            return
        result = compare_binary(left, right)
        self.preview.delete("1.0", tk.END)
        text = format_binary_compare(result)
        self.preview.insert(tk.END, text)
        self._mark_binary_compare_diffs(text, result)
        self.tabs.select(self.preview)
        self.status.set(f"二进制对比完成: 差异窗口 {len(result.chunks)}")

    def extract_current_media(self, kind: str) -> None:
        if not self.current_file:
            messagebox.showinfo("提取媒体", "请先打开一个媒体文件。")
            return
        labels = {
            "audio": ("提取音频", ".aac", [("AAC/Audio", "*.aac *.m4a *.mp3"), ("All files", "*.*")]),
            "video": ("提取视频", ".h264", [("Video", "*.h264 *.h265 *.mp4"), ("All files", "*.*")]),
            "keyframe": ("提取首个关键帧", ".png", [("PNG", "*.png"), ("All files", "*.*")]),
        }
        title, extension, filetypes = labels.get(kind, labels["audio"])
        path = filedialog.asksaveasfilename(title=title, defaultextension=extension, filetypes=filetypes)
        if not path:
            return
        self.status.set(f"正在{title}...")
        self.update_idletasks()
        result = extract_media_stream(self.current_file, path, kind)
        if result.get("error"):
            messagebox.showerror(title, str(result["error"]))
            self.status.set(f"{title}失败")
            return
        self.status.set(f"{title}完成: {result.get('output')} ({result.get('size', 0)} bytes)")

    def compare_protocol_files(self) -> None:
        left = filedialog.askopenfilename(title="选择左侧文件")
        if not left:
            return
        right = filedialog.askopenfilename(title="选择右侧文件")
        if not right:
            return
        self.status.set("正在执行协议结构对比...")
        self.update_idletasks()
        result = compare_protocol(left, right)
        self._clear_binary_diff_navigation()
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, format_protocol_compare(result))
        self.tabs.select(self.preview)
        self.status.set(
            f"协议对比完成: 新增 {len(result['added'])}, 删除 {len(result['removed'])}, 变化 {len(result['changed'])}"
        )
        save_path = filedialog.asksaveasfilename(
            title="保存协议对比 JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if save_path:
            Path(save_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def compare_frame_files(self) -> None:
        left = filedialog.askopenfilename(title="选择左侧文件")
        if not left:
            return
        right = filedialog.askopenfilename(title="选择右侧文件")
        if not right:
            return
        self.status.set("正在执行帧级对比...")
        self.update_idletasks()
        result = compare_frames(left, right)
        self._clear_binary_diff_navigation()
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, format_frame_compare(result))
        self.tabs.select(self.preview)
        self.status.set(
            f"帧级对比完成: 新增 {len(result['added'])}, 删除 {len(result['removed'])}, 变化 {len(result['changed'])}"
        )
        save_path = filedialog.asksaveasfilename(
            title="保存帧级对比 JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if save_path:
            Path(save_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def _mark_binary_compare_diffs(self, text: str, result: CompareResult) -> None:
        self._clear_binary_diff_navigation()
        self._binary_diff_indices = binary_compare_preview_indices(text, binary_compare_offsets(result))
        for index in self._binary_diff_indices:
            self.preview.tag_add("binary_diff_line", index, f"{index} lineend")

    def _clear_binary_diff_navigation(self) -> None:
        self._binary_diff_indices = []
        self._binary_diff_cursor = -1
        if hasattr(self, "preview"):
            self.preview.tag_remove("binary_diff_line", "1.0", tk.END)
            self.preview.tag_remove("binary_diff_active", "1.0", tk.END)

    def jump_next_binary_diff(self) -> None:
        if not self._binary_diff_indices:
            self.status.set("没有可跳转的二进制差异")
            return
        self._binary_diff_cursor = (self._binary_diff_cursor + 1) % len(self._binary_diff_indices)
        index = self._binary_diff_indices[self._binary_diff_cursor]
        self.preview.tag_remove("binary_diff_active", "1.0", tk.END)
        self.preview.tag_add("binary_diff_active", index, f"{index} lineend")
        self.preview.see(index)
        self.tabs.select(self.preview)
        self.status.set(f"二进制差异 {self._binary_diff_cursor + 1}/{len(self._binary_diff_indices)}")

    @staticmethod
    def _fmt(value) -> str:
        if value is None or value == "":
            return ""
        if isinstance(value, float):
            return f"{value:.6f}".rstrip("0").rstrip(".")
        return str(value)

    def _draw_logo(self) -> None:
        p = self._palette
        self.logo.delete("all")
        self.logo.create_rectangle(2, 2, 32, 32, outline=p["border"], fill=p["panel2"], width=1)
        self.logo.create_line(8, 22, 13, 12, 18, 22, 23, 12, 28, 22, fill=p["accent"], width=2)
        self.logo.create_text(17, 26, text="AV", fill=p["fg"], font=("Segoe UI Semibold", 8))

    def _set_empty_state(self) -> None:
        self._clear_binary_diff_navigation()
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, format_empty_state_text())
        self.preview.tag_add("empty_title", "1.0", "1.end")
        for line in (5, 8):
            self.preview.tag_add("empty_heading", f"{line}.0", f"{line}.end")
        for line in (3, 6, 9, 10, 11):
            self.preview.tag_add("empty_muted", f"{line}.0", f"{line}.end")
        self.diagnostics.delete("1.0", tk.END)
        self.diagnostics.insert(tk.END, "等待文件输入\n", ("heading",))
        self.diagnostics.insert(tk.END, "请选择“打开”，或通过菜单载入媒体文件。", ("info",))
        for value in self.summary_values.values():
            value.configure(text="--")
        for key in self.summary_cards:
            self._paint_summary_card(key, "normal")
        self.status_bar.configure(bg=self._palette["panel2"], fg=self._palette["muted"])

    def _render_summary_cards(self) -> None:
        if not self.result:
            return
        issues = self.result.diagnostics
        errors = sum(1 for issue in issues if issue.severity == Severity.ERROR)
        warnings = sum(1 for issue in issues if issue.severity == Severity.WARNING)
        issue_text, issue_state = issue_summary_state(errors, warnings)
        self.summary_values["format"].configure(text=self.result.media.format_name)
        self.summary_values["size"].configure(text=f"{self.result.media.size:,} bytes")
        self.summary_values["nodes"].configure(text=str(self._count_nodes(self.result.root)))
        self.summary_values["issues"].configure(text=issue_text)
        self.summary_values["elapsed"].configure(text=format_elapsed_seconds(self.last_parse_elapsed_seconds))
        for key in ("format", "size", "nodes"):
            self._paint_summary_card(key, "normal")
        self._paint_summary_card("issues", issue_state)
        self._paint_status_bar(issue_state)

    def _paint_summary_card(self, key: str, state: str) -> None:
        card = self.summary_cards.get(key)
        if not card:
            return
        p = self._palette
        bg = {
            "ok": p["ok_bg"],
            "warning": p["warning_bg"],
            "error": p["error_bg"],
        }.get(state, p["panel2"])
        border = {
            "ok": p["accent2"],
            "warning": p["warning"],
            "error": p["error"],
        }.get(state, p["border"])
        value_fg = {
            "ok": p["accent2"],
            "warning": p["warning"],
            "error": p["error"],
        }.get(state, p["fg"])
        card.configure(bg=bg, highlightbackground=border, highlightthickness=1)
        for child in card.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(bg=bg, fg=value_fg if child is self.summary_values.get(key) else p["muted"])

    def _paint_status_bar(self, state: str) -> None:
        p = self._palette
        if state == "error":
            self.status_bar.configure(bg=p["error_bg"], fg=p["error"])
        elif state == "warning":
            self.status_bar.configure(bg=p["warning_bg"], fg=p["warning"])
        else:
            self.status_bar.configure(bg=p["panel2"], fg=p["muted"])

    def _count_nodes(self, node: ParseNode) -> int:
        return 1 + sum(self._count_nodes(child) for child in node.children)


def extract_hex_bytes_from_dump_text(text: str) -> bytes:
    values: list[int] = []
    for line in text.splitlines():
        before_ascii = line.split("|", 1)[0]
        for token in HEX_BYTE_RE.findall(before_ascii):
            values.append(int(token, 16))
    return bytes(values)


def hex_bytes_to_ascii(data: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data)


def node_has_issue(node: ParseNode) -> bool:
    if node.severity in {Severity.WARNING, Severity.ERROR}:
        return True
    if any(field.severity in {Severity.WARNING, Severity.ERROR} for field in node.fields):
        return True
    return any(node_has_issue(child) for child in node.children)


def node_matches_query(node: ParseNode, query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return False
    haystack = [
        node.name,
        node.node_type,
        node.description,
        f"0x{node.offset:X}",
        str(node.offset),
        str(node.size),
    ]
    for field in node.fields:
        haystack.extend(
            [
                field.name,
                str(field.value),
                field.hex_value,
                f"0x{field.offset:X}",
                str(field.offset),
                field.description,
            ]
        )
    return any(needle in str(value).lower() for value in haystack if value is not None)


def first_loadable_drop_path(paths: list[str | Path]) -> Path | None:
    for item in paths:
        path = Path(item)
        if path.exists() and (path.is_file() or path.is_dir()):
            return path
    return None


def field_highlight_size(field: FieldInfo) -> int:
    if field.size > 0:
        return field.size
    if field.bit_length is not None and field.bit_length > 0:
        return max(1, (field.bit_length + 7) // 8)
    return 1


def format_field_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def field_tree_tag(field: FieldInfo) -> str:
    if field.severity == Severity.ERROR:
        return "error"
    if field.severity == Severity.WARNING:
        return "warning"
    if isinstance(field.value, bool):
        return "field_bool"
    if isinstance(field.value, (int, float)) and not isinstance(field.value, bool):
        return "field_number"
    if field.hex_value:
        return "field_hex"
    return "field_text"


def calculate_timestamp_seconds(timestamp: int | float, time_base_num: int | float, time_base_den: int | float) -> float:
    if time_base_den == 0:
        raise ValueError("time_base 分母不能为 0")
    return float(timestamp) * float(time_base_num) / float(time_base_den)


def calculate_bitrate_kbps(size_bytes: int | float, duration_seconds: int | float) -> float:
    duration = float(duration_seconds)
    if duration <= 0:
        raise ValueError("时长必须大于 0")
    return float(size_bytes) * 8 / duration / 1000


def format_seconds_timecode(seconds: int | float) -> str:
    total_ms = round(float(seconds) * 1000)
    sign = "-" if total_ms < 0 else ""
    total_ms = abs(total_ms)
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    second = total_seconds % 60
    total_minutes = total_seconds // 60
    minute = total_minutes % 60
    hour = total_minutes // 60
    return f"{sign}{hour:02d}:{minute:02d}:{second:02d}.{ms:03d}"


def _format_dbfs(value) -> str:
    if value is None:
        return "-inf dBFS"
    try:
        return f"{float(value):.2f} dBFS"
    except (TypeError, ValueError):
        return "-inf dBFS"


def issue_summary_state(errors: int, warnings: int) -> tuple[str, str]:
    if errors:
        return f"{errors} error / {warnings} warning", "error"
    if warnings:
        return f"0 error / {warnings} warning", "warning"
    return "0 error / 0 warning", "ok"


def format_video_frame_info_lines(frame_info: dict | None = None) -> list[str]:
    info = frame_info or {}
    if not info.get("available"):
        error = str(info.get("error") or "").strip()
        return [] if not error else [f"视频帧信息: {error}"]
    shape = ""
    if info.get("width") and info.get("height"):
        shape = f" {info.get('width')}x{info.get('height')}"
    pix_fmt = f" {info.get('pix_fmt')}" if info.get("pix_fmt") else ""
    parts = [
        f"PTS={_fmt_seconds(info.get('pts'))}" if info.get("pts") is not None else "",
        f"DTS={_fmt_seconds(info.get('dts'))}" if info.get("dts") is not None else "",
        f"duration={_fmt_seconds(info.get('duration'))}" if info.get("duration") is not None else "",
        f"type={info.get('frame_type')}" if info.get("frame_type") else "",
        "keyframe=yes" if info.get("keyframe") else "keyframe=no",
        f"size={info.get('size')} bytes" if info.get("size") is not None else "",
    ]
    return [f"视频帧信息:{shape}{pix_fmt} " + " ".join(part for part in parts if part)]


def format_frame_preview_lines(frames: list[FrameInfo], frame_stats: dict | None = None) -> list[str]:
    if not frames:
        return []
    frame_stats = frame_stats or {}
    first = frames[0]
    keyframes = int(frame_stats.get("keyframes", sum(1 for frame in frames if frame.keyframe)))
    average_size = frame_stats.get("average_size")
    largest_size = frame_stats.get("largest_size")
    largest_index = frame_stats.get("largest_index")
    pts_text = "" if first.pts is None else f"{first.pts:.6f}".rstrip("0").rstrip(".")
    pts = "" if not pts_text else f", PTS={pts_text}s"
    lines = [
        f"解析器帧列表: 已提取 {len(frames)} 帧，关键帧 {keyframes} 帧，详见“帧列表”页。",
        f"首帧: offset=0x{first.offset:X}, size={first.size}{pts}",
    ]
    if average_size is not None and largest_size is not None:
        lines.append(f"帧大小: average={average_size} bytes, max={largest_size} bytes (frame #{largest_index})")
    average_keyframe_interval = frame_stats.get("average_keyframe_interval")
    max_keyframe_interval = frame_stats.get("max_keyframe_interval")
    if average_keyframe_interval is not None and max_keyframe_interval is not None:
        lines.append(f"关键帧间隔: average={average_keyframe_interval} frames, max={max_keyframe_interval} frames")
    return lines


def format_timeline_summary_lines(timeline_summary: dict | None = None) -> list[str]:
    summary = timeline_summary or {}
    if not summary.get("available"):
        return []
    lines = [f"时间线曲线摘要: {summary.get('items', 0)} 个点，来源={summary.get('source', '')}"]
    pts = summary.get("pts", {})
    dts = summary.get("dts", {})
    if pts.get("available"):
        lines.append(
            "  "
            f"PTS span={_fmt_seconds(pts.get('span'))} "
            f"range={_fmt_seconds(pts.get('first'))}..{_fmt_seconds(pts.get('last'))} "
            f"non_monotonic={pts.get('non_monotonic', 0)}"
        )
    if dts.get("available"):
        lines.append(
            "  "
            f"DTS span={_fmt_seconds(dts.get('span'))} "
            f"range={_fmt_seconds(dts.get('first'))}..{_fmt_seconds(dts.get('last'))} "
            f"non_monotonic={dts.get('non_monotonic', 0)}"
        )
    issue_line = format_timeline_issue_summary_line(summary)
    if issue_line:
        lines.append(f"  {issue_line}")
    anomalies = summary.get("timestamp_anomalies", [])
    if anomalies:
        first = anomalies[0]
        lines.append(
            "  "
            f"时间戳异常: {len(anomalies)} 处，first={first.get('kind', '').upper()} "
            f"#{first.get('index')} {first.get('previous')}->{first.get('current')}"
        )
    bitrate = summary.get("bitrate", {})
    if bitrate.get("available"):
        lines.append(
            "  "
            f"码率曲线 bucket={_fmt_seconds(bitrate.get('bucket_seconds'))} "
            f"avg={bitrate.get('average_kbps')} kbps peak={bitrate.get('peak_kbps')} kbps"
        )
    gop = summary.get("gop", {})
    if gop.get("available"):
        interval = ""
        if "average_interval" in gop and "max_interval" in gop:
            interval = f" avg_interval={gop.get('average_interval')} max_interval={gop.get('max_interval')}"
        lines.append(
            "  "
            f"GOP/keyframes={gop.get('keyframes', 0)} "
            f"ratio={gop.get('keyframe_ratio', 0)}{interval}"
        )
        if gop.get("groups_available"):
            lines.append(
                "  "
                f"GOP 结构: groups={gop.get('group_count', 0)} "
                f"avg={gop.get('average_group_frames', 0)} frames "
                f"max={gop.get('max_group_frames', 0)} frames "
                f"bytes_peak={gop.get('max_group_bytes', 0)}"
            )
    rtp = summary.get("rtp_sequence", {})
    if rtp.get("available"):
        streams = rtp.get("streams", {})
        first_stream = next(iter(streams.values()), {})
        lines.append(
            "  "
            f"RTP sequence: packets={rtp.get('packets', 0)} streams={len(streams)} "
            f"warnings={rtp.get('sequence_warnings', 0)} "
            f"range={first_stream.get('first_sequence', '')}->{first_stream.get('last_sequence', '')}"
        )
        warnings = rtp.get("warnings", [])
        if warnings:
            first = warnings[0]
            lines.append(
                "  "
                f"RTP sequence 异常: first #{first.get('index')} "
                f"expected={first.get('expected')} current={first.get('current')}"
            )
    pcr = summary.get("pcr", {})
    if pcr.get("available"):
        by_pid = pcr.get("by_pid", {})
        first_pid = next(iter(by_pid.values()), {})
        lines.append(
            "  "
            f"PCR: points={pcr.get('points', 0)} pid_count={pcr.get('pid_count', 0)} "
            f"range={_fmt_seconds(first_pid.get('first'))}->{_fmt_seconds(first_pid.get('last'))} "
            f"max_interval={_fmt_seconds(first_pid.get('max_interval'))}"
        )
    return lines


def format_timeline_issue_summary_line(timeline_summary: dict | None = None) -> str:
    labels = timeline_issue_labels(timeline_summary)
    if not labels:
        return ""
    first_order = min(labels)
    return f"时间线异常: {len(labels)} 处，first item #{first_order} {labels[first_order]}"


def timeline_anomaly_item_orders(timeline_summary: dict | None = None) -> set[int]:
    orders = set()
    for anomaly in (timeline_summary or {}).get("timestamp_anomalies", []):
        try:
            orders.add(int(anomaly.get("item_order", 0) or 0))
        except (TypeError, ValueError):
            continue
    return orders


def timeline_issue_item_orders(timeline_summary: dict | None = None) -> set[int]:
    summary = timeline_summary or {}
    return set(timeline_issue_labels(summary))


def timeline_issue_labels(timeline_summary: dict | None = None) -> dict[int, str]:
    summary = timeline_summary or {}
    labels: dict[int, list[str]] = {}

    def add_label(value, label: str) -> None:
        if value in (None, ""):
            return
        try:
            order = int(value)
        except (TypeError, ValueError):
            return
        labels.setdefault(order, [])
        if label not in labels[order]:
            labels[order].append(label)

    for anomaly in summary.get("timestamp_anomalies", []):
        kind = str(anomaly.get("kind") or "timestamp").upper()
        add_label(anomaly.get("item_order"), f"{kind} 回退")
    for warning in summary.get("rtp_sequence", {}).get("warnings", []):
        add_label(warning.get("item_order"), "RTP seq 跳变")
    for warning in summary.get("pcr", {}).get("warnings", []):
        add_label(warning.get("item_order"), "PCR 回退")
    return {order: " / ".join(parts) for order, parts in labels.items()}


def timeline_item_row_tag(item_order: int, anomaly_orders: set[int]) -> str:
    return "warning" if item_order in anomaly_orders else "normal"


def _fmt_seconds(value) -> str:
    if value in (None, ""):
        return ""
    try:
        text = f"{float(value):.6f}".rstrip("0").rstrip(".")
        return f"{text}s"
    except (TypeError, ValueError):
        return str(value)


def float_or_none(value) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_hex_interpretation(data: bytes, endian: str = "little") -> str:
    byteorder = "big" if endian == "big" else "little"
    struct_prefix = ">" if byteorder == "big" else "<"
    u8_values = ", ".join(str(value) for value in data[:16])
    i8_values = ", ".join(str(value if value < 128 else value - 256) for value in data[:16])
    suffix = "" if len(data) <= 16 else f", ... ({len(data)} bytes)"
    lines = [
        "Hex 选区解释",
        f"Endian: {byteorder}",
        f"Length: {len(data)} bytes",
        f"Hex: {data.hex(' ').upper()}",
        f"ASCII: {hex_bytes_to_ascii(data)}",
        f"u8[]: {u8_values}{suffix}",
        f"i8[]: {i8_values}{suffix}",
    ]
    for size in (2, 4, 8):
        if len(data) < size:
            continue
        chunk = data[:size]
        bits = size * 8
        lines.append(f"u{bits}: {int.from_bytes(chunk, byteorder=byteorder, signed=False)}")
        lines.append(f"i{bits}: {int.from_bytes(chunk, byteorder=byteorder, signed=True)}")
    if len(data) >= 4:
        lines.append(f"float32: {struct.unpack(struct_prefix + 'f', data[:4])[0]:.9g}")
    if len(data) >= 8:
        lines.append(f"float64: {struct.unpack(struct_prefix + 'd', data[:8])[0]:.17g}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    app = AVScopeApp()
    initial_paths = sys.argv[1:] if argv is None else argv
    if initial_paths:
        app.after(100, lambda: app._load_dropped_paths(initial_paths))
    app.mainloop()


if __name__ == "__main__":
    main()
