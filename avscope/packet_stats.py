from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def build_packet_stats(packet_timeline: dict) -> dict:
    packets = packet_timeline.get("packets", []) if isinstance(packet_timeline, dict) else []
    if not packets:
        return {"available": False, "packets": 0}
    sizes = [_int_or_zero(packet.get("size")) for packet in packets]
    keyframes = sum(1 for packet in packets if packet.get("keyframe"))
    by_stream: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for packet in packets:
        grouped[str(packet.get("stream_index", ""))].append(packet)
    for stream, stream_packets in grouped.items():
        stream_sizes = [_int_or_zero(packet.get("size")) for packet in stream_packets]
        pts_values = [_float_or_none(packet.get("pts")) for packet in stream_packets]
        pts_values = [value for value in pts_values if value is not None]
        codec_counts = Counter(str(packet.get("codec_type") or "packet") for packet in stream_packets)
        item = {
            "packets": len(stream_packets),
            "keyframes": sum(1 for packet in stream_packets if packet.get("keyframe")),
            "total_bytes": sum(stream_sizes),
            "min_size": min(stream_sizes),
            "max_size": max(stream_sizes),
            "average_size": round(sum(stream_sizes) / len(stream_sizes), 2),
            "codec_types": dict(codec_counts.most_common(8)),
        }
        if pts_values:
            item["first_pts"] = pts_values[0]
            item["last_pts"] = pts_values[-1]
            item["pts_span"] = round(pts_values[-1] - pts_values[0], 6)
        by_stream[stream] = item
    return {
        "available": True,
        "packets": len(packets),
        "streams": len(grouped),
        "keyframes": keyframes,
        "total_bytes": sum(sizes),
        "min_size": min(sizes),
        "max_size": max(sizes),
        "average_size": round(sum(sizes) / len(sizes), 2),
        "by_stream": by_stream,
    }


def _int_or_zero(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
