from __future__ import annotations

import csv
import html
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from avscope import __version__
from avscope.models import ParseNode, ParseResult
from avscope.timeline_viz import build_timeline_summary, timeline_chart_items


def export_json(result: ParseResult, path: str | Path, notes: str | None = None) -> None:
    document = _document(result, notes)
    Path(path).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def export_csv(result: ParseResult, path: str | Path, notes: str | None = None) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "section",
                "path",
                "name",
                "type",
                "index",
                "offset",
                "size",
                "key",
                "value",
                "hex",
                "severity",
                "description",
            ],
        )
        writer.writeheader()
        clean_notes = _clean_notes(notes)
        writer.writerow(
            {
                "section": "media",
                "path": result.media.path,
                "name": result.media.format_name,
                "type": "summary",
                "size": result.media.size,
                "value": json.dumps(result.media.summary, ensure_ascii=False, default=str),
            }
        )
        if clean_notes:
            writer.writerow(
                {
                    "section": "notes",
                    "name": "user_notes",
                    "type": "text",
                    "value": clean_notes,
                }
            )
        for issue in result.diagnostics:
            writer.writerow(
                {
                    "section": "diagnostic",
                    "name": issue.source,
                    "type": issue.severity.value,
                    "offset": "" if issue.offset is None else f"0x{issue.offset:X}",
                    "value": issue.message,
                    "severity": issue.severity.value,
                }
            )
        frame_stats = result.media.summary.get("frame_stats", {})
        if frame_stats.get("available"):
            writer.writerow(
                {
                    "section": "frame_stats",
                    "name": "frames",
                    "type": "summary",
                    "size": frame_stats.get("total_bytes", ""),
                    "value": json.dumps(frame_stats, ensure_ascii=False),
                }
            )
        packet_stats = result.media.summary.get("packet_stats", {})
        if packet_stats.get("available"):
            writer.writerow(
                {
                    "section": "packet_stats",
                    "name": "packets",
                    "type": "summary",
                    "size": packet_stats.get("total_bytes", ""),
                    "value": json.dumps(packet_stats, ensure_ascii=False),
                }
            )
        timeline_summary = result.media.summary.get("timeline_summary", {})
        if timeline_summary.get("available"):
            writer.writerow(
                {
                    "section": "timeline_summary",
                    "name": "timeline",
                    "type": "summary",
                    "size": timeline_summary.get("items", ""),
                    "value": json.dumps(timeline_summary, ensure_ascii=False),
                }
            )
        for frame in result.frames[:5000]:
            writer.writerow(
                {
                    "section": "frame",
                    "index": frame.index,
                    "offset": f"0x{frame.offset:X}",
                    "size": frame.size,
                    "type": frame.frame_type,
                    "key": "yes" if frame.keyframe else "",
                    "value": f"pts={frame.pts or ''} dts={frame.dts or ''} duration={frame.duration or ''} {_frame_metadata_summary(_plain(frame.metadata))}",
                }
            )
        packet_timeline = result.media.summary.get("packet_timeline", {})
        for packet in packet_timeline.get("packets", [])[:5000]:
            writer.writerow(
                {
                    "section": "packet",
                    "index": packet.get("index", ""),
                    "offset": "" if packet.get("pos") is None else f"0x{packet.get('pos'):X}",
                    "size": packet.get("size", ""),
                    "type": packet.get("codec_type", ""),
                    "key": "yes" if packet.get("keyframe") else "",
                    "value": f"stream={packet.get('stream_index', '')} pts={packet.get('pts', '')} dts={packet.get('dts', '')} duration={packet.get('duration', '')}",
                }
            )
        for row in _node_csv_rows(result.root):
            writer.writerow(row)


def export_project(result: ParseResult, path: str | Path, raw_options: dict | None = None, notes: str | None = None) -> None:
    clean_notes = _clean_notes(notes)
    document = {
        "project_type": "AVScope Project",
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tool_version": __version__,
        "source_path": result.media.path,
        "raw_options": raw_options or {},
        "analysis": _document(result, clean_notes),
    }
    if clean_notes:
        document["user_notes"] = clean_notes
    Path(path).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def export_html(result: ParseResult, path: str | Path, notes: str | None = None) -> None:
    doc = _document(result, notes)
    media = doc["media"]
    summary_json = html.escape(json.dumps(media.get("summary", {}), ensure_ascii=False, indent=2))
    issue_counts = _issue_counts(doc["diagnostics"])
    issue_items = "\n".join(_issue_item(issue) for issue in doc["diagnostics"])
    health_class, health_text = _health(issue_counts)
    nodes = _node_html(result.root)
    waveform = result.media.summary.get("waveform", {})
    waveform_html = _waveform_html(waveform)
    packets = result.media.summary.get("packet_timeline", {}).get("packets", [])
    frame_stats = result.media.summary.get("frame_stats", {})
    packet_stats = result.media.summary.get("packet_stats", {})
    timeline_summary = result.media.summary.get("timeline_summary", {})
    if not timeline_summary.get("available"):
        timeline_summary = build_timeline_summary(result.frames, packets)
    stats_summary_html = _stats_summary_html(frame_stats, packet_stats)
    timeline_summary_html = _timeline_summary_html(timeline_summary)
    timeline_chart_html = _timeline_chart_html(doc["frames"], packets)
    timeline_html = _timeline_html(packets[:100])
    frame_html = _frame_html(doc["frames"][:200])
    stream_html = _stream_html(result.media.summary.get("ffprobe", {}).get("streams", []))
    notes_html = _notes_html(doc.get("user_notes", ""))
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
      overflow-x: auto;
    }}
    h2 {{ margin: 0 0 14px; font-size: 17px; color: var(--head); }}
    h3 {{ margin: 16px 0 8px; font-size: 14px; color: var(--head); }}
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
    table {{ width: 100%; min-width: 620px; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); background: var(--panel-soft); font-weight: 600; }}
    tr:hover td {{ background: #f8fbfd; }}
    .timeline-issues {{ margin: 12px 0 14px; }}
    .timeline-issues tr.warning-row td {{ background: #fff8e5; }}
    .timeline-issues .source {{ font-weight: 700; color: var(--warn); }}
    details {{
      border-left: 2px solid var(--line);
      margin: 7px 0 7px 12px;
      padding-left: 12px;
    }}
    summary {{ cursor: pointer; padding: 3px 0; font-family: Consolas, monospace; }}
    .warning {{ color: var(--warn); }}
    .error {{ color: var(--err); }}
    .empty {{ color: var(--muted); margin: 0; }}
    .waveform-chart {{ width: 100%; height: 180px; display: block; margin: 2px 0 14px; }}
    .waveform-chart .bg {{ fill: var(--panel-soft); }}
    .waveform-chart .grid {{ stroke: #d9e3ec; stroke-width: 1; }}
    .waveform-chart .axis {{ stroke: #a5b4c3; stroke-width: 1.2; }}
    .waveform-chart .bar {{ stroke: var(--accent); stroke-width: 2.2; stroke-linecap: round; }}
    .waveform-chart .rms {{ stroke: var(--ok); stroke-width: 1.1; stroke-linecap: round; opacity: 0.72; }}
    .timeline-chart {{ width: 100%; height: 170px; display: block; margin: 2px 0 14px; }}
    .timeline-chart .bg {{ fill: var(--panel-soft); }}
    .timeline-chart .grid {{ stroke: #d9e3ec; stroke-width: 1; }}
    .timeline-chart .axis {{ stroke: #a5b4c3; stroke-width: 1.2; }}
    .timeline-chart .bar {{ fill: var(--accent); }}
    .timeline-chart .key {{ fill: var(--ok); }}
    .timeline-chart .bitrate {{ fill: none; stroke: var(--warn); stroke-width: 2.2; stroke-linecap: round; }}
    .timeline-chart .bitrate-dot {{ fill: var(--warn); }}
    .timeline-chart .pts {{ fill: none; stroke: var(--ok); stroke-width: 2; stroke-linecap: round; }}
    .timeline-chart .dts {{ fill: none; stroke: var(--err); stroke-width: 1.8; stroke-linecap: round; stroke-dasharray: 5 4; }}
    .timeline-chart .timestamp-anomaly {{ fill: var(--err); }}
    .chart-legend {{ display: flex; flex-wrap: wrap; gap: 8px 12px; margin: 10px 0 12px; color: var(--muted); font-size: 12px; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 6px; min-height: 20px; }}
    .legend-swatch {{ width: 22px; height: 0; border-top: 3px solid var(--accent); }}
    .legend-swatch.pts {{ border-color: var(--ok); }}
    .legend-swatch.dts {{ border-color: var(--err); border-top-style: dashed; }}
    .legend-swatch.bitrate {{ border-color: var(--warn); }}
    .legend-swatch.gop {{ border-color: var(--ok); border-top-width: 6px; }}
    .legend-swatch.rtp {{ border-color: var(--accent); }}
    .legend-swatch.pcr {{ border-color: var(--muted); border-top-style: dashed; }}
    .legend-swatch.anomaly {{ width: 10px; height: 10px; border: 0; border-radius: 50%; background: var(--err); }}
    .chart-caption {{ color: var(--muted); font-size: 12px; margin: -4px 0 8px; }}
    .waveform {{ white-space: pre; line-height: 1.1; margin-top: 10px; }}
    @media (max-width: 720px) {{
      header {{ padding: 24px 18px; }}
      .header-inner {{ align-items: flex-start; }}
      main {{ padding: 18px 14px 30px; }}
      section {{ padding: 16px; }}
      h1 {{ font-size: 22px; }}
      table {{ font-size: 12px; }}
      th, td {{ padding: 7px 8px; }}
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
        <div class="metric"><div class="label">帧统计</div><div class="value">{_frame_stat_metric(frame_stats)}</div></div>
        <div class="metric"><div class="label">Packet 统计</div><div class="value">{_packet_stat_metric(packet_stats)}</div></div>
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
    {notes_html}
    <section>
      <h2>统计摘要</h2>
      {stats_summary_html}
    </section>
    <section>
      <h2>音频波形</h2>
      {waveform_html}
    </section>
    <section>
      <h2>帧列表</h2>
      {timeline_summary_html}
      {timeline_chart_html}
      {frame_html}
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


def _document(result: ParseResult, notes: str | None = None) -> dict[str, Any]:
    document = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tool_version": __version__,
        "media": _plain(result.media),
        "diagnostics": [_plain(i) for i in result.diagnostics],
        "frames": [_plain(f) for f in result.frames[:5000]],
        "root": _plain(result.root),
    }
    clean_notes = _clean_notes(notes)
    if clean_notes:
        document["user_notes"] = clean_notes
    return document


def _clean_notes(notes: str | None) -> str:
    return "" if notes is None else str(notes).strip()


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


def _node_csv_rows(node: ParseNode, parent_path: str = ""):
    node_path = f"{parent_path}/{node.name}" if parent_path else node.name
    yield {
        "section": "node",
        "path": node_path,
        "name": node.name,
        "type": node.node_type,
        "offset": f"0x{node.offset:X}",
        "size": node.size,
        "severity": node.severity.value,
        "description": node.description,
    }
    for field in node.fields:
        yield {
            "section": "field",
            "path": node_path,
            "name": field.name,
            "type": "field",
            "offset": f"0x{field.offset:X}",
            "size": field.size,
            "value": field.value,
            "hex": field.hex_value,
            "severity": field.severity.value,
            "description": field.description,
        }
    for child in node.children:
        yield from _node_csv_rows(child, node_path)


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


def _notes_html(notes: str) -> str:
    if not notes:
        return ""
    escaped = html.escape(notes)
    return f"<section><h2>用户备注</h2><pre>{escaped}</pre></section>"


def _waveform_html(waveform: dict) -> str:
    if not waveform.get("available"):
        return "<p class=\"empty\">暂无可展示的音频波形摘要。</p>"
    peaks = waveform.get("peaks", [])
    if not peaks:
        return "<p class=\"empty\">音频波形摘要为空。</p>"

    width = 720
    height = 160
    left = 12
    right = width - 12
    top = 12
    bottom = height - 12
    mid = (top + bottom) / 2
    sampled = _sample_peaks(peaks, 260)
    plot_width = max(1, right - left)
    denom = max(1, len(sampled) - 1)
    peak_lines = []
    rms_lines = []
    for index, peak in enumerate(sampled):
        x = left + plot_width * index / denom
        lo = _waveform_y(float(peak.get("min", 0.0)), top, bottom)
        hi = _waveform_y(float(peak.get("max", 0.0)), top, bottom)
        rms = max(0.0, min(1.0, float(peak.get("rms", 0.0))))
        rms_y = rms * (bottom - top) / 2.0
        peak_lines.append(f'<line class="bar" x1="{x:.2f}" y1="{hi:.2f}" x2="{x:.2f}" y2="{lo:.2f}" />')
        rms_lines.append(f'<line class="rms" x1="{x:.2f}" y1="{mid - rms_y:.2f}" x2="{x:.2f}" y2="{mid + rms_y:.2f}" />')
    grid_lines = "\n".join(
        [
            f'<line class="grid" x1="{left}" y1="{top + (bottom - top) * 0.25:.2f}" x2="{right}" y2="{top + (bottom - top) * 0.25:.2f}" />',
            f'<line class="axis" x1="{left}" y1="{mid:.2f}" x2="{right}" y2="{mid:.2f}" />',
            f'<line class="grid" x1="{left}" y1="{top + (bottom - top) * 0.75:.2f}" x2="{right}" y2="{top + (bottom - top) * 0.75:.2f}" />',
        ]
    )
    ascii_block = html.escape(waveform.get("ascii", ""))
    energy_html = _waveform_energy_html(waveform.get("energy", {}))
    return (
        energy_html
        +
        f'<svg class="waveform-chart" viewBox="0 0 {width} {height}" role="img" aria-label="音频波形图">'
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}" rx="8" />'
        f"{grid_lines}"
        f"{''.join(peak_lines)}"
        f"{''.join(rms_lines)}"
        "</svg>"
        f'<pre class="waveform">{ascii_block}</pre>'
    )


def _waveform_energy_html(energy: dict) -> str:
    if not energy:
        return ""
    rows = [
        ("Peak", _format_dbfs(energy.get("peak_dbfs"))),
        ("RMS", _format_dbfs(energy.get("rms_dbfs"))),
        ("裁剪样本", str(energy.get("clipped_samples", 0))),
        ("扫描样本", str(energy.get("sample_count", 0))),
    ]
    body = "".join(f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>" for label, value in rows)
    return f"<h3>音频能量</h3><table>{body}</table>"


def _format_dbfs(value) -> str:
    if value is None:
        return "-inf dBFS"
    try:
        return f"{float(value):.2f} dBFS"
    except (TypeError, ValueError):
        return "-inf dBFS"


def _sample_peaks(peaks: list[dict], max_points: int) -> list[dict]:
    if len(peaks) <= max_points:
        return peaks
    sampled = []
    for index in range(max_points):
        start = index * len(peaks) // max_points
        end = max(start + 1, (index + 1) * len(peaks) // max_points)
        bucket = peaks[start:end]
        sampled.append(
            {
                "min": min(float(peak.get("min", 0.0)) for peak in bucket),
                "max": max(float(peak.get("max", 0.0)) for peak in bucket),
                "rms": max(float(peak.get("rms", 0.0)) for peak in bucket),
            }
        )
    return sampled


def _waveform_y(value: float, top: int, bottom: int) -> float:
    clamped = max(-1.0, min(1.0, value))
    return top + (1.0 - clamped) * (bottom - top) / 2.0


def _timeline_chart_html(frames: list[dict], packets: list[dict]) -> str:
    items = timeline_chart_items(frames, packets, limit=220)
    if not items:
        return "<p class=\"empty\">暂无可展示的帧/packet 大小图。</p>"
    width = 720
    height = 150
    left = 12
    right = width - 12
    top = 12
    bottom = height - 24
    max_size = max(item["size"] for item in items)
    plot_width = max(1, right - left)
    slot = plot_width / max(1, len(items))
    bar_width = max(1.5, min(8.0, slot * 0.72))
    bars = []
    for index, item in enumerate(items):
        x = left + index * slot + slot / 2
        bar_height = max(2.0, item["size"] / max_size * (bottom - top))
        y = bottom - bar_height
        cls = "key" if item.get("keyframe") else "bar"
        bars.append(
            f'<rect class="{cls}" x="{x - bar_width / 2:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" rx="1.2" />'
        )
    grid_lines = "\n".join(
        [
            f'<line class="grid" x1="{left}" y1="{top + (bottom - top) * 0.25:.2f}" x2="{right}" y2="{top + (bottom - top) * 0.25:.2f}" />',
            f'<line class="axis" x1="{left}" y1="{top + (bottom - top) * 0.5:.2f}" x2="{right}" y2="{top + (bottom - top) * 0.5:.2f}" />',
            f'<line class="grid" x1="{left}" y1="{top + (bottom - top) * 0.75:.2f}" x2="{right}" y2="{top + (bottom - top) * 0.75:.2f}" />',
        ]
    )
    caption = f"{len(items)} 项，最大 size={max_size} bytes；绿色表示关键帧。"
    return (
        f'<svg class="timeline-chart" viewBox="0 0 {width} {height}" role="img" aria-label="帧/Packet 大小图">'
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}" rx="8" />'
        f"{grid_lines}"
        f"{''.join(bars)}"
        "</svg>"
        f'<p class="chart-caption">{caption}</p>'
    )


def _timeline_summary_html(timeline_summary: dict) -> str:
    if not timeline_summary.get("available"):
        return "<p class=\"empty\">暂无可展示的时间线曲线摘要。</p>"
    pts = timeline_summary.get("pts", {})
    dts = timeline_summary.get("dts", {})
    bitrate = timeline_summary.get("bitrate", {})
    gop = timeline_summary.get("gop", {})
    rtp = timeline_summary.get("rtp_sequence", {})
    pcr = timeline_summary.get("pcr", {})
    rows = [
        ("采样点", f"{timeline_summary.get('items', 0)} ({timeline_summary.get('source', '')})"),
        ("PTS 范围", _timestamp_range(pts)),
        ("DTS 范围", _timestamp_range(dts)),
        ("码率曲线", _bitrate_range(bitrate)),
        ("GOP / 关键帧", _gop_range(gop)),
        ("RTP Sequence", _rtp_sequence_range(rtp)),
        ("PCR", _pcr_range(pcr)),
    ]
    body = "".join(f"<tr><td>{html.escape(label)}</td><td>{html.escape(value)}</td></tr>" for label, value in rows)
    return (
        "<h3>时间线曲线摘要</h3>"
        "<table><tr><th>指标</th><th>值</th></tr>"
        + body
        + "</table>"
        + _timeline_issue_table_html(timeline_summary)
        + _timeline_legend_html(timeline_summary)
        + _timestamp_svg_html(timeline_summary)
        + _bitrate_svg_html(bitrate)
        + _gop_svg_html(gop)
        + _rtp_sequence_svg_html(rtp)
        + _pcr_svg_html(pcr)
    )


def _timeline_issue_table_html(timeline_summary: dict) -> str:
    rows = timeline_issue_rows(timeline_summary)
    if not rows:
        return ""
    body = "".join(
        "<tr class=\"warning-row\">"
        f"<td class=\"source\">{html.escape(str(row.get('source', '')))}</td>"
        f"<td>{html.escape(str(row.get('position', '')))}</td>"
        f"<td>{html.escape(str(row.get('kind', '')))}</td>"
        f"<td>{html.escape(str(row.get('detail', '')))}</td>"
        "</tr>"
        for row in rows[:80]
    )
    return (
        "<h3>时间线异常清单</h3>"
        "<table class=\"timeline-issues\">"
        "<tr><th>来源</th><th>位置</th><th>类型</th><th>详情</th></tr>"
        + body
        + "</table>"
    )


def timeline_issue_rows(timeline_summary: dict | None = None) -> list[dict[str, str]]:
    summary = timeline_summary or {}
    rows: list[dict[str, str]] = []
    for anomaly in summary.get("timestamp_anomalies", [])[:100]:
        kind = str(anomaly.get("kind") or "timestamp").upper()
        stream = anomaly.get("stream", "")
        rows.append(
            {
                "source": "Timestamp",
                "position": f"item {anomaly.get('item_order', '')}, index {anomaly.get('index', '')}, stream {stream or '-'}",
                "kind": f"{kind} non-monotonic",
                "detail": (
                    f"previous={anomaly.get('previous', '')} at item {anomaly.get('previous_order', '')}; "
                    f"current={anomaly.get('current', '')}"
                ),
            }
        )
    rtp = summary.get("rtp_sequence", {})
    for warning in rtp.get("warnings", [])[:100]:
        rows.append(
            {
                "source": "RTP",
                "position": f"item {warning.get('item_order', '')}, packet #{warning.get('index', '')}, SSRC {warning.get('ssrc') or '-'}",
                "kind": "sequence jump",
                "detail": (
                    f"previous={warning.get('previous', '')}; expected={warning.get('expected', '')}; "
                    f"current={warning.get('current', '')}; delta={warning.get('delta', '')}"
                ),
            }
        )
    pcr = summary.get("pcr", {})
    for warning in pcr.get("warnings", [])[:100]:
        kind = str(warning.get("kind") or "warning")
        detail = f"count={warning.get('count', '')}" if "count" in warning else json.dumps(warning, ensure_ascii=False)
        rows.append(
            {
                "source": "PCR",
                "position": f"PID {warning.get('pid', '-')}",
                "kind": kind,
                "detail": detail,
            }
        )
    return rows[:200]


def _timeline_legend_html(timeline_summary: dict) -> str:
    items = []
    if timeline_summary.get("pts", {}).get("available"):
        items.append(("pts", "PTS"))
    if timeline_summary.get("dts", {}).get("available"):
        items.append(("dts", "DTS"))
    if timeline_summary.get("bitrate", {}).get("available"):
        items.append(("bitrate", "Bitrate"))
    if timeline_summary.get("gop", {}).get("groups_available"):
        items.append(("gop", "GOP"))
    if timeline_summary.get("rtp_sequence", {}).get("available"):
        items.append(("rtp", "RTP seq"))
    if timeline_summary.get("pcr", {}).get("available"):
        items.append(("pcr", "PCR"))
    if timeline_summary.get("timestamp_anomalies"):
        items.append(("anomaly", "Anomaly"))
    if not items:
        return ""
    body = "".join(
        f'<span class="legend-item"><span class="legend-swatch {html.escape(kind)}"></span>{html.escape(label)}</span>'
        for kind, label in items
    )
    return f'<div class="chart-legend" aria-label="Timeline chart legend">{body}</div>'


def _timestamp_svg_html(timeline_summary: dict) -> str:
    series = timeline_summary.get("series", [])
    values = [
        float(point[key])
        for point in series
        for key in ("pts", "dts")
        if point.get(key) is not None
    ]
    if len(values) < 2:
        return ""
    value_min = min(values)
    value_max = max(values)
    if value_max <= value_min:
        return ""
    width = 720
    height = 120
    left = 12
    right = width - 12
    top = 12
    bottom = height - 20
    plot_width = max(1, right - left)
    y_span = max(1, bottom - top)
    denom = max(1, len(series) - 1)
    polylines = []
    for key, cls in (("pts", "pts"), ("dts", "dts")):
        pairs = []
        for index, point in enumerate(series):
            value = point.get(key)
            if value is None:
                continue
            x = left + plot_width * index / denom
            y = bottom - (float(value) - value_min) / (value_max - value_min) * y_span
            pairs.append(f"{x:.2f},{y:.2f}")
        if len(pairs) >= 2:
            polylines.append(f'<polyline class="{cls}" points="{" ".join(pairs)}" />')
    if not polylines:
        return ""
    anomalies = []
    for anomaly in timeline_summary.get("timestamp_anomalies", [])[:48]:
        try:
            order = int(anomaly.get("item_order", 0) or 0)
        except (TypeError, ValueError):
            order = 0
        x = left + plot_width * min(max(order, 0), len(series) - 1) / denom
        anomalies.append(f'<circle class="timestamp-anomaly" cx="{x:.2f}" cy="{top + 7:.2f}" r="3.8" />')
    grid_lines = "\n".join(
        [
            f'<line class="grid" x1="{left}" y1="{top + y_span * 0.33:.2f}" x2="{right}" y2="{top + y_span * 0.33:.2f}" />',
            f'<line class="grid" x1="{left}" y1="{top + y_span * 0.66:.2f}" x2="{right}" y2="{top + y_span * 0.66:.2f}" />',
            f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" />',
        ]
    )
    caption = (
        f"PTS/DTS range={_format_seconds(value_min)}..{_format_seconds(value_max)}, "
        f"timestamp anomalies={len(timeline_summary.get('timestamp_anomalies', []))}"
    )
    return (
        f'<svg class="timeline-chart" viewBox="0 0 {width} {height}" role="img" aria-label="PTS/DTS 曲线">'
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}" rx="8" />'
        f"{grid_lines}"
        f"{''.join(polylines)}"
        f"{''.join(anomalies)}"
        "</svg>"
        f'<p class="chart-caption">{html.escape(caption)}</p>'
    )


def _bitrate_svg_html(bitrate: dict) -> str:
    buckets = bitrate.get("buckets", [])
    if not bitrate.get("available") or not buckets:
        return ""
    width = 720
    height = 120
    left = 12
    right = width - 12
    top = 12
    bottom = height - 20
    max_kbps = max(float(bucket.get("kbps", 0) or 0) for bucket in buckets)
    if max_kbps <= 0:
        return ""
    plot_width = max(1, right - left)
    denom = max(1, len(buckets) - 1)
    point_pairs = []
    dots = []
    for index, bucket in enumerate(buckets):
        x = left + plot_width * index / denom
        y = bottom - (float(bucket.get("kbps", 0) or 0) / max_kbps) * (bottom - top)
        point_pairs.append(f"{x:.2f},{y:.2f}")
        if len(buckets) <= 48:
            dots.append(f'<circle class="bitrate-dot" cx="{x:.2f}" cy="{y:.2f}" r="2.2" />')
    grid_lines = "\n".join(
        [
            f'<line class="grid" x1="{left}" y1="{top + (bottom - top) * 0.33:.2f}" x2="{right}" y2="{top + (bottom - top) * 0.33:.2f}" />',
            f'<line class="grid" x1="{left}" y1="{top + (bottom - top) * 0.66:.2f}" x2="{right}" y2="{top + (bottom - top) * 0.66:.2f}" />',
            f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" />',
        ]
    )
    caption = (
        f"bucket={_format_seconds(bitrate.get('bucket_seconds'))}, "
        f"avg={bitrate.get('average_kbps')} kbps, peak={bitrate.get('peak_kbps')} kbps @ {_format_seconds(bitrate.get('peak_start'))}"
    )
    return (
        f'<svg class="timeline-chart" viewBox="0 0 {width} {height}" role="img" aria-label="码率曲线">'
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}" rx="8" />'
        f"{grid_lines}"
        f'<polyline class="bitrate" points="{" ".join(point_pairs)}" />'
        f"{''.join(dots)}"
        "</svg>"
        f'<p class="chart-caption">{html.escape(caption)}</p>'
    )


def _rtp_sequence_svg_html(rtp: dict) -> str:
    series = rtp.get("series", [])
    if not rtp.get("available") or len(series) < 2:
        return ""
    values = [int(point.get("sequence", 0) or 0) for point in series]
    value_min = min(values)
    value_max = max(values)
    if value_max <= value_min:
        value_max = value_min + 1
    width = 720
    height = 120
    left = 12
    right = width - 12
    top = 12
    bottom = height - 20
    plot_width = max(1, right - left)
    y_span = max(1, bottom - top)
    denom = max(1, len(series) - 1)
    pairs = []
    markers = []
    for index, point in enumerate(series):
        sequence = int(point.get("sequence", 0) or 0)
        x = left + plot_width * index / denom
        y = bottom - (sequence - value_min) / (value_max - value_min) * y_span
        pairs.append(f"{x:.2f},{y:.2f}")
        if point.get("marker"):
            markers.append(f'<circle class="key" cx="{x:.2f}" cy="{y:.2f}" r="2.8" />')
    warnings = []
    warning_orders = [int(item.get("item_order", 0) or 0) for item in rtp.get("warnings", [])[:48]]
    max_order = max(1, max((int(point.get("item_order", 0) or 0) for point in series), default=0))
    for order in warning_orders:
        x = left + plot_width * min(max(order, 0), max_order) / max_order
        warnings.append(f'<circle class="timestamp-anomaly" cx="{x:.2f}" cy="{top + 7:.2f}" r="3.8" />')
    grid_lines = "\n".join(
        [
            f'<line class="grid" x1="{left}" y1="{top + y_span * 0.33:.2f}" x2="{right}" y2="{top + y_span * 0.33:.2f}" />',
            f'<line class="grid" x1="{left}" y1="{top + y_span * 0.66:.2f}" x2="{right}" y2="{top + y_span * 0.66:.2f}" />',
            f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" />',
        ]
    )
    caption = f"RTP packets={rtp.get('packets', 0)}, sequence warnings={rtp.get('sequence_warnings', 0)}"
    return (
        f'<svg class="timeline-chart" viewBox="0 0 {width} {height}" role="img" aria-label="RTP sequence 曲线">'
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}" rx="8" />'
        f"{grid_lines}"
        f'<polyline class="pts" points="{" ".join(pairs)}" />'
        f"{''.join(markers)}"
        f"{''.join(warnings)}"
        "</svg>"
        f'<p class="chart-caption">{html.escape(caption)}</p>'
    )


def _pcr_svg_html(pcr: dict) -> str:
    series = pcr.get("series", [])
    if not pcr.get("available") or len(series) < 2:
        return ""
    values = []
    for point in series:
        try:
            values.append(float(point.get("seconds", 0.0) or 0.0))
        except (TypeError, ValueError):
            continue
    if len(values) < 2:
        return ""
    value_min = min(values)
    value_max = max(values)
    if value_max <= value_min:
        value_max = value_min + 1
    width = 720
    height = 120
    left = 12
    right = width - 12
    top = 12
    bottom = height - 20
    plot_width = max(1, right - left)
    y_span = max(1, bottom - top)
    denom = max(1, len(series) - 1)
    pairs = []
    for index, point in enumerate(series):
        try:
            seconds = float(point.get("seconds", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        x = left + plot_width * index / denom
        y = bottom - (seconds - value_min) / (value_max - value_min) * y_span
        pairs.append(f"{x:.2f},{y:.2f}")
    if len(pairs) < 2:
        return ""
    warning_orders = []
    for item in pcr.get("warnings", [])[:48]:
        try:
            warning_orders.append(int(item.get("item_order", 0) or 0))
        except (TypeError, ValueError):
            continue
    warnings = []
    max_order = max(1, max((int(point.get("item_order", 0) or 0) for point in series), default=0))
    for order in warning_orders:
        x = left + plot_width * min(max(order, 0), max_order) / max_order
        warnings.append(f'<circle class="timestamp-anomaly" cx="{x:.2f}" cy="{top + 7:.2f}" r="3.8" />')
    grid_lines = "\n".join(
        [
            f'<line class="grid" x1="{left}" y1="{top + y_span * 0.33:.2f}" x2="{right}" y2="{top + y_span * 0.33:.2f}" />',
            f'<line class="grid" x1="{left}" y1="{top + y_span * 0.66:.2f}" x2="{right}" y2="{top + y_span * 0.66:.2f}" />',
            f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" />',
        ]
    )
    caption = (
        f"PCR points={pcr.get('points', 0)}, pid_count={pcr.get('pid_count', 0)}, "
        f"range={_format_seconds(value_min)}..{_format_seconds(value_max)}"
    )
    return (
        f'<svg class="timeline-chart" viewBox="0 0 {width} {height}" role="img" aria-label="PCR curve">'
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}" rx="8" />'
        f"{grid_lines}"
        f'<polyline class="pts" points="{" ".join(pairs)}" />'
        f"{''.join(warnings)}"
        "</svg>"
        f'<p class="chart-caption">{html.escape(caption)}</p>'
    )


def _gop_svg_html(gop: dict) -> str:
    groups = gop.get("groups", [])
    if not gop.get("groups_available") or not groups:
        return ""
    width = 720
    height = 95
    left = 12
    right = width - 12
    top = 18
    bottom = height - 26
    plot_width = max(1, right - left)
    max_frames = max(1, max(int(group.get("frames", 0) or 0) for group in groups))
    max_bytes = max(1, max(int(group.get("bytes", 0) or 0) for group in groups))
    slot = plot_width / max(1, len(groups))
    bars = []
    for index, group in enumerate(groups[:120]):
        x = left + index * slot
        width_px = max(2.0, slot * 0.75)
        frame_height = max(3.0, int(group.get("frames", 0) or 0) / max_frames * (bottom - top))
        byte_height = max(2.0, int(group.get("bytes", 0) or 0) / max_bytes * (bottom - top))
        bars.append(
            f'<rect class="key" x="{x:.2f}" y="{bottom - frame_height:.2f}" width="{width_px:.2f}" height="{frame_height:.2f}" rx="1.2" />'
        )
        bars.append(
            f'<rect class="bar" x="{x + width_px * 0.28:.2f}" y="{bottom - byte_height:.2f}" width="{max(1.4, width_px * 0.44):.2f}" height="{byte_height:.2f}" rx="1.2" />'
        )
    grid_lines = "\n".join(
        [
            f'<line class="grid" x1="{left}" y1="{top + (bottom - top) * 0.5:.2f}" x2="{right}" y2="{top + (bottom - top) * 0.5:.2f}" />',
            f'<line class="axis" x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" />',
        ]
    )
    caption = (
        f"GOP groups={gop.get('group_count', len(groups))}, "
        f"avg={gop.get('average_group_frames')} frames, max={gop.get('max_group_frames')} frames, "
        f"max bytes={gop.get('max_group_bytes')}"
    )
    return (
        f'<svg class="timeline-chart" viewBox="0 0 {width} {height}" role="img" aria-label="GOP 结构图">'
        f'<rect class="bg" x="0" y="0" width="{width}" height="{height}" rx="8" />'
        f"{grid_lines}"
        f"{''.join(bars)}"
        "</svg>"
        f'<p class="chart-caption">{html.escape(caption)}</p>'
    )


def _timestamp_range(data: dict) -> str:
    if not data.get("available"):
        return "无"
    return (
        f"{_format_seconds(data.get('first'))} - {_format_seconds(data.get('last'))}; "
        f"span={_format_seconds(data.get('span'))}; non_monotonic={data.get('non_monotonic', 0)}"
    )


def _bitrate_range(data: dict) -> str:
    if not data.get("available"):
        return "无"
    return (
        f"bucket={_format_seconds(data.get('bucket_seconds'))}; "
        f"avg={data.get('average_kbps')} kbps; peak={data.get('peak_kbps')} kbps"
    )


def _gop_range(data: dict) -> str:
    if not data.get("available"):
        return "无关键帧"
    interval = ""
    if "average_interval" in data and "max_interval" in data:
        interval = f"; avg_interval={data.get('average_interval')}; max_interval={data.get('max_interval')}"
    groups = ""
    if data.get("groups_available"):
        groups = f"; groups={data.get('group_count', 0)}; max_group={data.get('max_group_frames', 0)} frames"
    return f"keyframes={data.get('keyframes', 0)}; ratio={data.get('keyframe_ratio', 0)}{interval}{groups}"


def _rtp_sequence_range(data: dict) -> str:
    if not data.get("available"):
        return "无"
    streams = data.get("streams", {})
    first_stream = next(iter(streams.values()), {})
    return (
        f"packets={data.get('packets', 0)}; streams={len(streams)}; "
        f"warnings={data.get('sequence_warnings', 0)}; "
        f"range={first_stream.get('first_sequence', '')}->{first_stream.get('last_sequence', '')}"
    )


def _pcr_range(data: dict) -> str:
    if not data.get("available"):
        return "none"
    by_pid = data.get("by_pid", {})
    first_pid = next(iter(by_pid.values()), {})
    return (
        f"points={data.get('points', 0)}; pid_count={data.get('pid_count', 0)}; "
        f"range={_format_seconds(first_pid.get('first'))}->{_format_seconds(first_pid.get('last'))}; "
        f"max_interval={_format_seconds(first_pid.get('max_interval'))}"
    )


def _format_seconds(value) -> str:
    if value in (None, ""):
        return ""
    try:
        text = f"{float(value):.6f}".rstrip("0").rstrip(".")
        return f"{text}s"
    except (TypeError, ValueError):
        return str(value)


def _stats_summary_html(frame_stats: dict, packet_stats: dict) -> str:
    blocks = []
    blocks.append(_frame_stats_table(frame_stats))
    blocks.append(_packet_stats_table(packet_stats))
    return "\n".join(blocks)


def _frame_stats_table(frame_stats: dict) -> str:
    if not frame_stats.get("available"):
        return "<p class=\"empty\">暂无解析器帧统计。</p>"
    overview = [
        ("帧数", frame_stats.get("frames", 0)),
        ("关键帧", frame_stats.get("keyframes", 0)),
        ("首个关键帧", _optional_frame_index(frame_stats.get("first_keyframe_index"))),
        ("平均关键帧间隔", _optional_bytes(frame_stats.get("average_keyframe_interval"), "")),
        ("最大关键帧间隔", _optional_bytes(frame_stats.get("max_keyframe_interval"), "")),
        ("平均大小", f"{frame_stats.get('average_size', 0)} bytes"),
        ("最大大小", f"{frame_stats.get('max_size', 0)} bytes"),
        ("最大帧", f"#{frame_stats.get('largest_index', '')} @ 0x{int(frame_stats.get('largest_offset', 0)):X}"),
    ]
    overview_rows = "".join(f"<tr><td>{html.escape(str(name))}</td><td>{html.escape(str(value))}</td></tr>" for name, value in overview)
    type_rows = "".join(
        f"<tr><td>{html.escape(str(name))}</td><td>{count}</td></tr>"
        for name, count in frame_stats.get("frame_types", {}).items()
    )
    type_table = (
        "<table><tr><th>帧类型</th><th>数量</th></tr>" + type_rows + "</table>"
        if type_rows
        else "<p class=\"empty\">暂无帧类型分布。</p>"
    )
    return (
        "<h3>帧统计</h3>"
        "<table><tr><th>指标</th><th>值</th></tr>"
        + overview_rows
        + "</table>"
        + type_table
    )


def _packet_stats_table(packet_stats: dict) -> str:
    if not packet_stats.get("available"):
        return "<p class=\"empty\">暂无 packet 统计。</p>"
    rows = []
    for stream, item in packet_stats.get("by_stream", {}).items():
        codec_types = ", ".join(f"{name}:{count}" for name, count in item.get("codec_types", {}).items())
        pts_span = item.get("pts_span", "")
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(stream))}</td>"
            f"<td>{item.get('packets', 0)}</td>"
            f"<td>{item.get('keyframes', 0)}</td>"
            f"<td>{item.get('average_size', 0)}</td>"
            f"<td>{item.get('max_size', 0)}</td>"
            f"<td>#{html.escape(str(item.get('largest_index', '')))}</td>"
            f"<td>{html.escape(str(pts_span))}</td>"
            f"<td>{html.escape(codec_types)}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class=\"empty\">暂无 packet stream 分布。</p>"
    return (
        "<h3>Packet 统计</h3>"
        "<table><tr><th>Stream</th><th>Packets</th><th>Key</th><th>Avg Size</th><th>Max Size</th><th>Max Packet</th><th>PTS Span</th><th>类型</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _optional_frame_index(value) -> str:
    return "" if value in (None, "") else f"#{value}"


def _optional_bytes(value, suffix: str = " bytes") -> str:
    return "" if value in (None, "") else f"{value}{suffix}"


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


def _frame_html(frames: list[dict]) -> str:
    if not frames:
        return "<p class=\"empty\">暂无解析器帧列表。</p>"
    rows = []
    for frame in frames:
        rows.append(
            "<tr>"
            f"<td>{frame.get('index', '')}</td>"
            f"<td>0x{int(frame.get('offset', 0)):X}</td>"
            f"<td>{frame.get('size', '')}</td>"
            f"<td>{frame.get('pts', '') or ''}</td>"
            f"<td>{frame.get('dts', '') or ''}</td>"
            f"<td>{frame.get('duration', '') or ''}</td>"
            f"<td>{html.escape(str(frame.get('frame_type', '')))}</td>"
            f"<td>{'yes' if frame.get('keyframe') else ''}</td>"
            f"<td>{html.escape(_frame_metadata_summary(frame.get('metadata', {})))}</td>"
            "</tr>"
        )
    return "<table><tr><th>#</th><th>offset</th><th>size</th><th>PTS</th><th>DTS</th><th>duration</th><th>type</th><th>key</th><th>metadata</th></tr>" + "".join(rows) + "</table>"


def _frame_metadata_summary(metadata: dict) -> str:
    if not metadata:
        return ""
    if "rtp_sequence" in metadata:
        return (
            f"RTP seq={metadata.get('rtp_sequence')} "
            f"ts={metadata.get('rtp_timestamp')} "
            f"ssrc={metadata.get('rtp_ssrc')} "
            f"pt={metadata.get('rtp_payload_type')}"
        )
    return json.dumps(metadata, ensure_ascii=False, default=str)


def _node_html(node: ParseNode) -> str:
    title = f"{node.name} [{node.node_type}] offset=0x{node.offset:X} size={node.size}"
    field_rows = "".join(
        "<tr>"
        f"<td>{html.escape(field.name)}</td>"
        f"<td>{html.escape(str(field.value))}</td>"
        f"<td>{html.escape(field.hex_value)}</td>"
        f"<td>0x{field.offset:X}</td>"
        f"<td>{_field_bit_info(field)}</td>"
        f"<td>{html.escape(field.description)}</td>"
        "</tr>"
        for field in node.fields
    )
    table = (
        "<table><tr><th>字段</th><th>值</th><th>Hex</th><th>Offset</th><th>Bit / Size</th><th>说明</th></tr>"
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


def _field_bit_info(field) -> str:
    if field.bit_offset is not None or field.bit_length is not None:
        return f"{field.bit_offset or 0}/{field.bit_length or 0}"
    return str(field.size)


def _frame_stat_metric(frame_stats: dict) -> str:
    if not frame_stats.get("available"):
        return "无"
    frames = frame_stats.get("frames", 0)
    keyframes = frame_stats.get("keyframes", 0)
    average = frame_stats.get("average_size", 0)
    max_size = frame_stats.get("max_size", 0)
    return html.escape(f"{frames} 帧 / {keyframes} 关键帧 / avg {average} B / max {max_size} B")


def _packet_stat_metric(packet_stats: dict) -> str:
    if not packet_stats.get("available"):
        return "无"
    packets = packet_stats.get("packets", 0)
    streams = packet_stats.get("streams", 0)
    average = packet_stats.get("average_size", 0)
    max_size = packet_stats.get("max_size", 0)
    return html.escape(f"{packets} packets / {streams} streams / avg {average} B / max {max_size} B")


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
