from __future__ import annotations

import html
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from avscope import __version__
from avscope.models import ParseNode, ParseResult


def export_json(result: ParseResult, path: str | Path) -> None:
    document = _document(result)
    Path(path).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def export_project(result: ParseResult, path: str | Path, raw_options: dict | None = None) -> None:
    document = {
        "project_type": "AVScope Project",
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tool_version": __version__,
        "source_path": result.media.path,
        "raw_options": raw_options or {},
        "analysis": _document(result),
    }
    Path(path).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def export_html(result: ParseResult, path: str | Path) -> None:
    doc = _document(result)
    media = doc["media"]
    summary_json = html.escape(json.dumps(media.get("summary", {}), ensure_ascii=False, indent=2))
    issue_counts = _issue_counts(doc["diagnostics"])
    issue_items = "\n".join(_issue_item(issue) for issue in doc["diagnostics"])
    health_class, health_text = _health(issue_counts)
    nodes = _node_html(result.root)
    waveform = result.media.summary.get("waveform", {})
    waveform_html = (
        f"<pre class=\"waveform\">{html.escape(waveform.get('ascii', ''))}</pre>"
        if waveform.get("available")
        else "<p class=\"empty\">暂无可展示的音频波形摘要。</p>"
    )
    timeline_html = _timeline_html(result.media.summary.get("packet_timeline", {}).get("packets", [])[:100])
    stream_html = _stream_html(result.media.summary.get("ffprobe", {}).get("streams", []))
    generated_at = html.escape(doc["generated_at"])
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AVScope 分析报告</title>
  <style>
    :root {{
      --bg: #f4f7fa;
      --panel: #ffffff;
      --panel-soft: #f8fafc;
      --ink: #17212b;
      --muted: #5e6b78;
      --line: #dce3ea;
      --head: #101820;
      --accent: #176b9a;
      --accent-soft: #e4f2f9;
      --ok: #287a5c;
      --warn: #9a6700;
      --err: #b42318;
      --code: #eef3f7;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      line-height: 1.55;
    }}
    header {{
      background: var(--head);
      color: #e6edf3;
      padding: 30px 36px 28px;
      border-bottom: 4px solid var(--accent);
    }}
    .header-inner {{
      max-width: 1180px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 16px;
    }}
    .mark {{
      width: 42px;
      height: 42px;
      display: grid;
      place-items: center;
      border: 1px solid #355166;
      background: #142435;
      color: #e6edf3;
      font-weight: 700;
      letter-spacing: 0;
    }}
    h1 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
    .meta {{ margin-top: 6px; color: #a9b7c4; font-size: 13px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 26px 24px 42px; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 18px;
      padding: 20px 22px;
    }}
    h2 {{ margin: 0 0 14px; font-size: 17px; color: var(--head); }}
    code, pre {{
      background: var(--code);
      border: 1px solid var(--line);
      border-radius: 6px;
    }}
    code {{ padding: 2px 6px; }}
    pre {{ padding: 14px; overflow: auto; font-family: Consolas, monospace; font-size: 12px; }}
    .overview {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }}
    .metric {{
      border-left: 4px solid var(--accent);
      background: var(--panel-soft);
      border-radius: 8px;
      padding: 11px 13px;
      min-width: 0;
    }}
    .metric .label {{ color: var(--muted); font-size: 12px; }}
    .metric .value {{ margin-top: 3px; font-weight: 700; word-break: break-word; }}
    .status-line {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid var(--line);
      background: var(--panel-soft);
    }}
    .pill.ok {{ color: var(--ok); border-color: #b9dbc9; background: #edf8f1; }}
    .pill.warning {{ color: var(--warn); border-color: #ead59b; background: #fff8e5; }}
    .pill.error {{ color: var(--err); border-color: #efb8b0; background: #fff0ee; }}
    ul {{ margin: 0; padding-left: 20px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); background: var(--panel-soft); font-weight: 600; }}
    tr:hover td {{ background: #f8fbfd; }}
    details {{
      border-left: 2px solid var(--line);
      margin: 7px 0 7px 12px;
      padding-left: 12px;
    }}
    summary {{ cursor: pointer; padding: 3px 0; font-family: Consolas, monospace; }}
    .warning {{ color: var(--warn); }}
    .error {{ color: var(--err); }}
    .empty {{ color: var(--muted); margin: 0; }}
    .waveform {{ white-space: pre; line-height: 1.1; }}
    @media (max-width: 720px) {{
      header {{ padding: 24px 18px; }}
      .header-inner {{ align-items: flex-start; }}
      main {{ padding: 18px 14px 30px; }}
      section {{ padding: 16px; }}
      h1 {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div class="mark">AV</div>
      <div>
        <h1>AVScope 分析报告</h1>
        <div class="meta">生成时间：{generated_at}，工具版本：{html.escape(doc["tool_version"])}</div>
      </div>
    </div>
  </header>
  <main>
    <section>
      <h2>文件概览</h2>
      <div class="overview">
        <div class="metric"><div class="label">文件路径</div><div class="value"><code>{html.escape(media["path"])}</code></div></div>
        <div class="metric"><div class="label">识别格式</div><div class="value">{html.escape(media["format_name"])}</div></div>
        <div class="metric"><div class="label">文件大小</div><div class="value">{_format_size(media["size"])}</div></div>
        <div class="metric"><div class="label">协议节点</div><div class="value">{_count_nodes(result.root)}</div></div>
        <div class="metric"><div class="label">字段数量</div><div class="value">{_count_fields(result.root)}</div></div>
      </div>
    </section>
    <section>
      <h2>诊断摘要</h2>
      <div class="status-line">
        <span class="pill {health_class}">{health_text}</span>
        <span class="pill ok">info {issue_counts["info"]}</span>
        <span class="pill warning">warning {issue_counts["warning"]}</span>
        <span class="pill error">error {issue_counts["error"]}</span>
      </div>
      <ul>{issue_items or "<li class=\"empty\">未发现 warning/error。</li>"}</ul>
    </section>
    <section>
      <h2>媒体摘要</h2>
      {stream_html}
      <pre>{summary_json}</pre>
    </section>
    <section>
      <h2>音频波形</h2>
      {waveform_html}
    </section>
    <section>
      <h2>Packet 时间线</h2>
      {timeline_html}
    </section>
    <section>
      <h2>协议结构</h2>
      {nodes}
    </section>
  </main>
</body>
</html>
"""
    Path(path).write_text(body, encoding="utf-8")


def _document(result: ParseResult) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tool_version": __version__,
        "media": _plain(result.media),
        "diagnostics": [_plain(i) for i in result.diagnostics],
        "frames": [_plain(f) for f in result.frames[:5000]],
        "root": _plain(result.root),
    }


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        data = asdict(value)
        return _plain(data)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _issue_counts(diagnostics: list[dict]) -> dict[str, int]:
    counts = {"info": 0, "warning": 0, "error": 0}
    for issue in diagnostics:
        severity = str(issue.get("severity", "info"))
        if severity in counts:
            counts[severity] += 1
    return counts


def _health(counts: dict[str, int]) -> tuple[str, str]:
    if counts["error"]:
        return "error", "存在错误"
    if counts["warning"]:
        return "warning", "存在警告"
    return "ok", "未发现异常"


def _issue_item(issue: dict) -> str:
    severity = html.escape(str(issue.get("severity", "info")))
    message = html.escape(str(issue.get("message", "")))
    offset = issue.get("offset")
    suffix = "" if offset is None else f" offset=0x{int(offset):X}"
    return f"<li class=\"{severity}\">[{severity}] {message}{suffix}</li>"


def _stream_html(streams: list[dict]) -> str:
    if not streams:
        return "<p class=\"empty\">暂无 ffprobe 流信息。</p>"
    rows = []
    for stream in streams:
        shape = ""
        if stream.get("width") and stream.get("height"):
            shape = f"{stream.get('width')}x{stream.get('height')}"
        elif stream.get("sample_rate"):
            shape = f"{stream.get('sample_rate')} Hz / {stream.get('channels', '')} ch"
        rows.append(
            "<tr>"
            f"<td>{stream.get('index', '')}</td>"
            f"<td>{html.escape(str(stream.get('codec_type', '')))}</td>"
            f"<td>{html.escape(str(stream.get('codec_name', '')))}</td>"
            f"<td>{html.escape(shape)}</td>"
            f"<td>{html.escape(str(stream.get('duration', '')))}</td>"
            "</tr>"
        )
    return "<table><tr><th>#</th><th>类型</th><th>Codec</th><th>参数</th><th>时长</th></tr>" + "".join(rows) + "</table>"


def _timeline_html(packets: list[dict]) -> str:
    if not packets:
        return "<p class=\"empty\">暂无 packet 时间线。</p>"
    rows = []
    for packet in packets:
        rows.append(
            "<tr>"
            f"<td>{packet.get('index', '')}</td>"
            f"<td>{packet.get('stream_index', '')}</td>"
            f"<td>{packet.get('pts', '')}</td>"
            f"<td>{packet.get('dts', '')}</td>"
            f"<td>{packet.get('pos', '')}</td>"
            f"<td>{packet.get('size', '')}</td>"
            f"<td>{html.escape(str(packet.get('codec_type', '')))}</td>"
            f"<td>{'yes' if packet.get('keyframe') else ''}</td>"
            "</tr>"
        )
    return "<table><tr><th>#</th><th>stream</th><th>PTS</th><th>DTS</th><th>pos</th><th>size</th><th>type</th><th>key</th></tr>" + "".join(rows) + "</table>"


def _node_html(node: ParseNode) -> str:
    title = f"{node.name} [{node.node_type}] offset=0x{node.offset:X} size={node.size}"
    field_rows = "".join(
        "<tr>"
        f"<td>{html.escape(field.name)}</td>"
        f"<td>{html.escape(str(field.value))}</td>"
        f"<td>{html.escape(field.hex_value)}</td>"
        f"<td>0x{field.offset:X}</td>"
        f"<td>{field.size}</td>"
        f"<td>{html.escape(field.description)}</td>"
        "</tr>"
        for field in node.fields
    )
    table = (
        "<table><tr><th>字段</th><th>值</th><th>Hex</th><th>Offset</th><th>Size</th><th>说明</th></tr>"
        + field_rows
        + "</table>"
        if field_rows
        else ""
    )
    children = "\n".join(_node_html(child) for child in node.children)
    return f"<details open><summary>{html.escape(title)}</summary>{table}{children}</details>"


def _count_nodes(node: ParseNode) -> int:
    return 1 + sum(_count_nodes(child) for child in node.children)


def _count_fields(node: ParseNode) -> int:
    return len(node.fields) + sum(_count_fields(child) for child in node.children)


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
