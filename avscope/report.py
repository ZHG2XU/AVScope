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


def export_html(result: ParseResult, path: str | Path) -> None:
    doc = _document(result)
    summary_json = html.escape(json.dumps(doc["media"].get("summary", {}), ensure_ascii=False, indent=2))
    issue_counts = _issue_counts(doc["diagnostics"])
    issue_items = "\n".join(_issue_item(issue) for issue in doc["diagnostics"])
    nodes = _node_html(result.root)
    waveform = result.media.summary.get("waveform", {})
    waveform_html = f"<pre class=\"waveform\">{html.escape(waveform.get('ascii', ''))}</pre>" if waveform.get("available") else "<p class=\"empty\">无波形摘要。</p>"
    timeline_html = _timeline_html(result.media.summary.get("packet_timeline", {}).get("packets", [])[:100])
    stream_html = _stream_html(result.media.summary.get("ffprobe", {}).get("streams", []))
    media = doc["media"]
    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AVScope Report</title>
  <style>
    :root {{
      --bg: #f5f7fa;
      --panel: #ffffff;
      --ink: #17212b;
      --muted: #5e6b78;
      --line: #dce3ea;
      --head: #101820;
      --accent: #176b9a;
      --ok: #287a5c;
      --warn: #9a6700;
      --err: #b42318;
      --code: #f0f4f7;
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
      padding: 28px 36px 24px;
      border-bottom: 4px solid var(--accent);
    }}
    header h1 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
    header .meta {{ margin-top: 8px; color: #a9b7c4; font-size: 13px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 26px 24px 40px; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
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
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}
    .metric {{
      border-left: 3px solid var(--accent);
      background: #f8fafc;
      padding: 10px 12px;
    }}
    .metric .label {{ color: var(--muted); font-size: 12px; }}
    .metric .value {{ margin-top: 3px; font-weight: 600; word-break: break-all; }}
    .badges {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid var(--line);
      background: #f8fafc;
    }}
    .badge.info {{ color: var(--ok); }}
    .badge.warning {{ color: var(--warn); }}
    .badge.error {{ color: var(--err); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); background: #f8fafc; font-weight: 600; }}
    tr:hover td {{ background: #f8fbfd; }}
    details {{ border-left: 2px solid var(--line); margin: 7px 0 7px 12px; padding-left: 12px; }}
    summary {{ cursor: pointer; padding: 3px 0; font-family: Consolas, monospace; }}
    .warning {{ color: var(--warn); }}
    .error {{ color: var(--err); }}
    .empty {{ color: var(--muted); }}
    .waveform {{ white-space: pre; line-height: 1.1; }}
  </style>
</head>
<body>
  <header>
    <h1>AVScope 分析报告</h1>
    <div class="meta">生成时间：{html.escape(doc["generated_at"])}，工具版本：{html.escape(doc["tool_version"])}</div>
  </header>
  <main>
    <section>
      <h2>文件概览</h2>
      <div class="overview">
        <div class="metric"><div class="label">文件路径</div><div class="value"><code>{html.escape(media["path"])}</code></div></div>
        <div class="metric"><div class="label">识别格式</div><div class="value">{html.escape(media["format_name"])}</div></div>
        <div class="metric"><div class="label">文件大小</div><div class="value">{media["size"]} bytes</div></div>
        <div class="metric"><div class="label">协议节点</div><div class="value">{len(result.root.children)}</div></div>
      </div>
    </section>
    <section>
      <h2>诊断摘要</h2>
      <div class="badges">
        <span class="badge info">info {issue_counts["info"]}</span>
        <span class="badge warning">warning {issue_counts["warning"]}</span>
        <span class="badge error">error {issue_counts["error"]}</span>
      </div>
      <ul>{issue_items or "<li class=\"empty\">未发现 warning/error</li>"}</ul>
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


def _issue_item(issue: dict) -> str:
    severity = html.escape(str(issue.get("severity", "info")))
    message = html.escape(str(issue.get("message", "")))
    offset = issue.get("offset")
    suffix = "" if offset is None else f" offset=0x{int(offset):X}"
    return f"<li class=\"{severity}\">[{severity}] {message}{suffix}</li>"


def _stream_html(streams: list[dict]) -> str:
    if not streams:
        return "<p class=\"empty\">无 ffprobe 流信息。</p>"
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
        return "<p class=\"empty\">无 packet 时间线。</p>"
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
