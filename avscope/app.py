from __future__ import annotations

import json
import re
import struct
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from avscope.analyzer import Analyzer
from avscope.byte_source import ByteSource
from avscope.compare import compare_binary, compare_frames, compare_protocol, format_binary_compare, format_frame_compare, format_protocol_compare
from avscope.ffmpeg_preview import build_video_preview
from avscope.hexview import format_hex, parse_offset
from avscope.models import FieldInfo, FrameInfo, ParseNode, ParseResult, Severity
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
        "select": "#25445F",
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
        "select": "#CDE4F5",
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
            "5. sample.pcm / sample.yuv：检查 Raw 参数输入、波形和 YUV 首帧预览。",
            "",
            "完整验收清单：G:\\AVScope\\docs\\ACCEPTANCE.md",
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
        self._node_by_iid: dict[str, ParseNode] = {}
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
        self.hex_endian = tk.StringVar(value="little")
        self.issue_filter = tk.BooleanVar(value=False)
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
        for text, command in [
            ("打开", self.open_file),
            ("重新解析", self.reload_file),
            ("二进制对比", self.compare_files),
            ("协议对比", self.compare_protocol_files),
            ("帧级对比", self.compare_frame_files),
            ("导出 HTML", self.export_html_report),
            ("导出 JSON", self.export_json_report),
            ("导出 CSV", self.export_csv_report),
        ]:
            ttk.Button(toolbar, text=text, command=command, style="Toolbar.TButton").pack(side=tk.LEFT, padx=(0, 8), pady=8)
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
        for label, key in [("格式", "format"), ("大小", "size"), ("节点", "nodes"), ("诊断", "issues")]:
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
        self.tree = ttk.Treeview(left, columns=("type", "offset", "size"), show="tree headings", style="Data.Treeview")
        self.tree.heading("#0", text="名称")
        self.tree.heading("type", text="类型")
        self.tree.heading("offset", text="Offset")
        self.tree.heading("size", text="Size")
        self.tree.column("#0", width=260, minwidth=180)
        self.tree.column("type", width=92, anchor=tk.CENTER)
        self.tree.column("offset", width=96, anchor=tk.E)
        self.tree.column("size", width=92, anchor=tk.E)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
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
        self.timeline_canvas = tk.Canvas(self.timeline_page, height=118, highlightthickness=0, borderwidth=0)
        self.timeline_canvas.pack(fill=tk.X, padx=8, pady=(8, 4))
        self.timeline_canvas.bind("<Configure>", lambda _event: self._render_timeline_chart())
        self.timeline = ttk.Treeview(
            self.timeline_page,
            columns=("index", "stream", "pts", "dts", "pos", "size", "type", "duration", "key"),
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
        view_menu.add_command(label="深色主题", command=lambda: self._apply_theme("dark"))
        view_menu.add_command(label="浅色主题", command=lambda: self._apply_theme("light"))
        menu.add_cascade(label="视图", menu=view_menu)

        analysis_menu = tk.Menu(menu, tearoff=False)
        analysis_menu.add_command(label="自动识别", command=self.reload_file)
        analysis_menu.add_command(label="二进制对比", command=self.compare_files)
        analysis_menu.add_command(label="协议结构对比", command=self.compare_protocol_files)
        analysis_menu.add_command(label="帧级对比", command=self.compare_frame_files)
        menu.add_cascade(label="分析", menu=analysis_menu)

        plugin_menu = tk.Menu(menu, tearoff=False)
        plugin_menu.add_command(label="查看已加载模板", command=self.show_plugin_templates)
        plugin_menu.add_command(label="重新加载协议模板", command=self.reload_plugin_templates)
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

    def show_shortcuts_help(self) -> None:
        messagebox.showinfo("快捷键", format_shortcuts_help())

    def show_sample_files_help(self) -> None:
        messagebox.showinfo("示例文件", format_sample_files_help())

    def show_about(self) -> None:
        messagebox.showinfo("关于 AVScope", ABOUT_TEXT)

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
        self.bind_all("<Control-Shift-H>", self._shortcut(self.export_html_report))
        self.bind_all("<Control-Shift-J>", self._shortcut(self.export_json_report))
        self.bind_all("<Control-Shift-O>", self._shortcut(self.copy_current_offset))
        self.bind_all("<Control-Shift-C>", self._shortcut(self.copy_selected_hex_bytes))
        self.bind_all("<Control-Shift-I>", self._shortcut(self.show_selected_hex_interpretation))

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
        style.configure("Toolbar.TButton", padding=(12, 6), background=p["panel"], foreground=p["fg"], bordercolor=p["border"])
        style.map("Toolbar.TButton", background=[("active", p["select"])], foreground=[("active", p["fg"])])
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
        style.map("Data.Treeview", background=[("selected", p["select"])], foreground=[("selected", p["fg"])])

        self.header.configure(bg=p["bg"])
        self.logo.configure(bg=p["bg"])
        self.brand.configure(bg=p["bg"], fg=p["fg"])
        self.file_badge.configure(bg=p["bg"], fg=p["muted"])
        self.status_bar.configure(bg=p["panel2"], fg=p["muted"], padx=12, pady=5)
        self.summary_frame.configure(bg=p["bg"])
        self.timeline_canvas.configure(bg=p["panel"])
        for key in self.summary_cards:
            self._paint_summary_card(key, "normal")
        self._draw_logo()
        for widget in (self.hex_text, self.preview, self.diagnostics):
            widget.configure(bg=p["text_bg"], fg=p["fg"], insertbackground=p["fg"], selectbackground=p["select"])
        self.hex_text.tag_configure("search_hit", background=p["accent"], foreground="#FFFFFF")
        self.diagnostics.tag_configure("info", foreground=p["accent2"])
        self.diagnostics.tag_configure("warning", foreground=p["warning"])
        self.diagnostics.tag_configure("error", foreground=p["error"])
        self.diagnostics.tag_configure("heading", foreground=p["accent"], font=("Microsoft YaHei UI", 9, "bold"))
        for tree in (self.tree, self.fields, self.frames, self.timeline):
            tree.tag_configure("warning", foreground=p["warning"], background=p["warning_bg"])
            tree.tag_configure("error", foreground=p["error"], background=p["error_bg"])
            tree.tag_configure("normal", foreground=p["fg"])
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
        self.result = self.analyzer.analyze(path, self._raw_options_for_path(path))
        self._attach_waveform_preview(path)
        self._attach_video_preview(path)
        self._attach_yuv_preview(path)
        self._render_result()
        self._load_hex(0)
        self.file_badge.configure(text=f"{path.name}  |  {self.result.media.format_name}")
        self.status.set(f"{path.name} | {self.result.media.format_name} | {self.result.media.size} bytes")
        self._render_summary_cards()
        self.settings.add_recent_file(path)
        self._refresh_recent_menu()

    def configure_current_raw_options(self) -> None:
        if not self.current_file or self.current_file.suffix.lower() not in {".pcm", ".yuv"}:
            messagebox.showinfo("Raw 参数", "请先打开 .pcm 或 .yuv 文件。")
            return
        self.raw_options_by_path.pop(str(self.current_file), None)
        self.result = self.analyzer.analyze(self.current_file, self._raw_options_for_path(self.current_file, force=True))
        self._attach_waveform_preview(self.current_file)
        self._attach_yuv_preview(self.current_file)
        self._render_result()
        self._load_hex(self.current_hex_offset)
        self._render_summary_cards()

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
        self._tree_iids_in_display_order.clear()
        self._last_node_search = None
        self._insert_node("", self.result.root)

    def _render_timeline(self) -> None:
        if not self.result:
            return
        self.timeline.delete(*self.timeline.get_children())
        for frame in self.result.frames[:5000]:
            tag = "normal"
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
                ),
                tags=(tag,),
            )
        packet_timeline = self.result.media.summary.get("packet_timeline", {})
        for packet in packet_timeline.get("packets", [])[:1000]:
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
                ),
                tags=("normal",),
            )
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
        top = 16
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
        canvas.create_line(left, mid, right, mid, fill=p["border"])

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
            values=(node.node_type, f"0x{node.offset:X}", node.size),
            open=self.issue_filter.get() or len(visible_children) < 64,
            tags=(tag,),
        )
        self._node_by_iid[iid] = node
        self._tree_iids_in_display_order.append(iid)
        for child in visible_children:
            self._insert_node(iid, child)

    def on_tree_select(self, _event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        node = self._node_by_iid.get(selection[0])
        if not node:
            return
        self._render_fields(node)
        self._load_hex(node.offset)

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
            lines.append(waveform.get("ascii", ""))
            lines.append("")
        waveform_preview = self.result.media.summary.get("waveform_preview", {})
        if waveform_preview.get("available") and waveform_preview.get("path"):
            lines.append(
                f"音频波形预览: 已生成 {waveform_preview.get('width')}x{waveform_preview.get('height')}，见下方画面。"
            )
            lines.append("")
        elif waveform_preview.get("error"):
            lines.append(f"音频波形预览: {waveform_preview.get('error')}")
            lines.append("")
        frame_preview = format_frame_preview_lines(self.result.frames, self.result.media.summary.get("frame_stats", {}))
        if frame_preview:
            lines.extend(frame_preview)
            lines.append("")
        video_preview = self.result.media.summary.get("video_preview", {})
        if video_preview.get("available") and video_preview.get("path"):
            shape = ""
            if video_preview.get("width") and video_preview.get("height"):
                shape = f" ({video_preview.get('width')}x{video_preview.get('height')})"
            lines.append(f"视频首帧预览: 已生成{shape}，见下方画面。")
            lines.append("")
        elif video_preview.get("error"):
            lines.append(f"视频首帧预览: {video_preview.get('error')}")
            lines.append("")
        yuv_preview = self.result.media.summary.get("yuv_preview", {})
        if yuv_preview.get("available") and yuv_preview.get("path"):
            lines.append(
                f"Raw YUV 首帧预览: 已生成 {yuv_preview.get('width')}x{yuv_preview.get('height')} "
                f"{yuv_preview.get('pixel_format')}，见下方画面。"
            )
            lines.append("")
        elif yuv_preview.get("error"):
            lines.append(f"Raw YUV 首帧预览: {yuv_preview.get('error')}")
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
        self.result.media.summary["video_preview"] = build_video_preview(path)

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
            self.preview.insert(tk.END, f"\n视频首帧画面加载失败: {exc}")
            return
        self._preview_images.append(image)
        self.preview.insert(tk.END, "\n视频首帧画面\n")
        self.preview.image_create(tk.END, image=image)
        self.preview.insert(tk.END, "\n")

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
            self.preview.insert(tk.END, f"\nRaw YUV 首帧画面加载失败: {exc}")
            return
        self._preview_images.append(image)
        self.preview.insert(tk.END, "\nRaw YUV 首帧画面\n")
        self.preview.image_create(tk.END, image=image)
        self.preview.insert(tk.END, "\n")

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
        self.preview.insert(tk.END, format_binary_compare(result))
        self.tabs.select(self.preview)
        self.status.set(f"二进制对比完成: 差异窗口 {len(result.chunks)}")

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
        self.preview.delete("1.0", tk.END)
        self.preview.insert(
            tk.END,
            "打开一个音视频文件开始分析。\n\n"
            "支持 MP4/MOV、AVI、FLV、Matroska/WebM、MPEG-PS、MPEG-TS、PCAP/RTP、WAV、AAC ADTS、H.264/H.265 Annex-B、PCM、YUV。\n"
            "可以拖拽文件到窗口打开；解析后会显示协议树、Hex、字段、帧列表、时间线、波形和诊断报告。",
        )
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


def issue_summary_state(errors: int, warnings: int) -> tuple[str, str]:
    if errors:
        return f"{errors} error / {warnings} warning", "error"
    if warnings:
        return f"0 error / {warnings} warning", "warning"
    return "0 error / 0 warning", "ok"


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
