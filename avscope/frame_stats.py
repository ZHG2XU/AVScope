from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any


def build_frame_stats(frames: Iterable[Any]) -> dict:
    normalized = []
    for frame in frames:
        size = int(_value(frame, "size", 0) or 0)
        normalized.append(
            {
                "index": _value(frame, "index", len(normalized)),
                "offset": int(_value(frame, "offset", 0) or 0),
                "size": size,
                "pts": _float_or_none(_value(frame, "pts", None)),
                "dts": _float_or_none(_value(frame, "dts", None)),
                "duration": _float_or_none(_value(frame, "duration", None)),
                "frame_type": str(_value(frame, "frame_type", "") or ""),
                "keyframe": bool(_value(frame, "keyframe", False)),
            }
        )
    if not normalized:
        return {"available": False, "frames": 0}

    sizes = [frame["size"] for frame in normalized]
    keyframes = sum(1 for frame in normalized if frame["keyframe"])
    pts_values = [frame["pts"] for frame in normalized if frame["pts"] is not None]
    duration_values = [frame["duration"] for frame in normalized if frame["duration"] is not None]
    type_counts = Counter(frame["frame_type"] or "unknown" for frame in normalized)
    first = normalized[0]
    largest = max(normalized, key=lambda frame: frame["size"])
    stats = {
        "available": True,
        "frames": len(normalized),
        "keyframes": keyframes,
        "keyframe_ratio": round(keyframes / len(normalized), 6),
        "total_bytes": sum(sizes),
        "min_size": min(sizes),
        "max_size": max(sizes),
        "average_size": round(sum(sizes) / len(sizes), 2),
        "first_offset": first["offset"],
        "first_size": first["size"],
        "first_pts": first["pts"],
        "largest_index": largest["index"],
        "largest_offset": largest["offset"],
        "largest_size": largest["size"],
        "frame_types": dict(type_counts.most_common(12)),
    }
    if pts_values:
        stats["first_pts"] = pts_values[0]
        stats["last_pts"] = pts_values[-1]
        stats["pts_span"] = round(pts_values[-1] - pts_values[0], 6)
    if duration_values:
        stats["total_duration"] = round(sum(duration_values), 6)
        stats["average_duration"] = round(sum(duration_values) / len(duration_values), 6)
    return stats


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
