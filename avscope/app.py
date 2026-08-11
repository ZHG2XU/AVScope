from __future__ import annotations

import json
import re
import struct
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from avscope.analyzer import Analyzer
from avscope.byte_source import ByteSource
from avscope.compare import compare_binary, compare_protocol, format_binary_compare, format_protocol_compare
from avscope.hexview import format_hex, parse_offset
from avscope.models import ParseNode, ParseResult, Severity
from avscope.report import export_html, export_json
from avscope.search import SearchPatternError, find_pattern, parse_search_pattern
from avscope.settings import AppSettings


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
        "text_bg": "#FFFFFF",
    },
}

SUPPORTED_EXTENSIONS = {
    ".aac",
    ".avi",
    ".h264",
    ".h265",
    ".264",
    ".265",
    ".mp4",
    ".mov",
    ".pcm",
    ".wav",
    ".yuv",
}


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
        self._last_search: tuple[str, str, int] | None = None
        self._last_node_search: tuple[str, int] | None = None
        self.raw_options_by_path: dict[str, dict] = {}
        self.settings = AppSettings()
        self._theme_name = "dark"
        self._palette = PALETTES["dark"]
        self.hex_endian = tk.StringVar(value="little")
        self.issue_filter = tk.BooleanVar(value=False)
        self._build_ui()
        self._bind_shortcuts()
        self._apply_theme("dark")
        self._set_empty_state()

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
            ("导出 HTML", self.export_html_report),
            ("导出 JSON", self.export_json_report),
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
        self.summary_values: dict[str, tk.Label] = {}
        for label, key in [("格式", "format"), ("大小", "size"), ("节点", "nodes"), ("诊断", "issues")]:
            card = tk.Frame(self.summary_frame, height=54)
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            card.pack_propagate(False)
            tk.Label(card, text=label, font=("Microsoft YaHei UI", 8), anchor=tk.W).pack(anchor=tk.W, padx=12, pady=(8, 0))
            value = tk.Label(card, text="--", font=("Microsoft YaHei UI", 11, "bold"), anchor=tk.W)
            value.pack(anchor=tk.W, padx=12)
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

        self.timeline = ttk.Treeview(
            self.tabs,
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
        self.tabs.add(self.timeline, text="时间线")

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
        file_menu.add_command(label="导出 HTML 报告", command=self.export_html_report)
        file_menu.add_command(label="导出 JSON 报告", command=self.export_json_report)
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
        menu.add_cascade(label="分析", menu=analysis_menu)
        tools_menu = tk.Menu(menu, tearoff=False)
        tools_menu.add_command(label="设置当前 Raw 参数", command=self.configure_current_raw_options)
        tools_menu.add_command(label="复制当前 Offset", command=self.copy_current_offset, accelerator="Ctrl+Shift+O")
        tools_menu.add_command(label="复制选中 Hex 字节", command=self.copy_selected_hex_bytes, accelerator="Ctrl+Shift+C")
        tools_menu.add_command(label="复制选中 ASCII", command=self.copy_selected_ascii)
        tools_menu.add_command(label="解释选中字节", command=self.show_selected_hex_interpretation, accelerator="Ctrl+Shift+I")
        menu.add_cascade(label="工具", menu=tools_menu)
        self.config(menu=menu)
        self._refresh_recent_menu()

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
        for card in self.summary_frame.winfo_children():
            card.configure(bg=p["panel2"], highlightbackground=p["border"], highlightthickness=1)
            for child in card.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=p["panel2"], fg=p["muted"])
        for value in self.summary_values.values():
            value.configure(bg=p["panel2"], fg=p["fg"])
        self._draw_logo()
        for widget in (self.hex_text, self.preview, self.diagnostics):
            widget.configure(bg=p["text_bg"], fg=p["fg"], insertbackground=p["fg"], selectbackground=p["select"])
        self.hex_text.tag_configure("search_hit", background=p["accent"], foreground="#FFFFFF")
        self.diagnostics.tag_configure("info", foreground=p["accent2"])
        self.diagnostics.tag_configure("warning", foreground=p["warning"])
        self.diagnostics.tag_configure("error", foreground=p["error"])
        self.diagnostics.tag_configure("heading", foreground=p["accent"], font=("Microsoft YaHei UI", 9, "bold"))
        for tree in (self.tree, self.fields, self.timeline):
            tree.tag_configure("warning", foreground=p["warning"])
            tree.tag_configure("error", foreground=p["error"])
            tree.tag_configure("normal", foreground=p["fg"])

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
        return {
            "sample_rate": sample_rate or int(defaults.get("sample_rate", 48000)),
            "channels": channels or int(defaults.get("channels", 2)),
            "bits_per_sample": bits or int(defaults.get("bits_per_sample", 16)),
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
        self._render_timeline()
        self._render_diagnostics()
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, self._preview_text())

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
        for field in node.fields:
            bit_info = f"{field.bit_offset or 0}/{field.bit_length or 0}" if field.bit_offset is not None or field.bit_length is not None else str(field.size)
            tag = "error" if field.severity == Severity.ERROR else "warning" if field.severity == Severity.WARNING else "normal"
            self.fields.insert(
                "",
                tk.END,
                values=(field.name, field.value, field.hex_value, f"0x{field.offset:X}", bit_info, field.description),
                tags=(tag,),
            )

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
        packet_timeline = self.result.media.summary.get("packet_timeline", {})
        packets = packet_timeline.get("packets", [])
        if packets:
            lines.append(f"packet 时间线: 已提取前 {len(packets)} 个 packet，详见“时间线”页。")
        if not packets and not waveform.get("available"):
            lines.append("当前文件暂无可预览波形或 packet 时间线；仍可查看协议树、字段和 Hex。")
        return "\n".join(lines)

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
            export_html(self.result, path)

    def export_json_report(self) -> None:
        if not self.result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            export_json(self.result, path)

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
            "支持 MP4/MOV、WAV、AAC ADTS、H.264/H.265 Annex-B、PCM、YUV。\n"
            "解析后会显示协议树、Hex、字段、时间线、波形和诊断报告。",
        )
        self.diagnostics.delete("1.0", tk.END)
        self.diagnostics.insert(tk.END, "等待文件输入\n", ("heading",))
        self.diagnostics.insert(tk.END, "请选择“打开”，或通过菜单载入媒体文件。", ("info",))
        for value in self.summary_values.values():
            value.configure(text="--")

    def _render_summary_cards(self) -> None:
        if not self.result:
            return
        issues = self.result.diagnostics
        errors = sum(1 for issue in issues if issue.severity == Severity.ERROR)
        warnings = sum(1 for issue in issues if issue.severity == Severity.WARNING)
        self.summary_values["format"].configure(text=self.result.media.format_name)
        self.summary_values["size"].configure(text=f"{self.result.media.size:,} bytes")
        self.summary_values["nodes"].configure(text=str(self._count_nodes(self.result.root)))
        self.summary_values["issues"].configure(text=f"{errors} error / {warnings} warning")

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


def main() -> None:
    app = AVScopeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
