from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def timeline_chart_items(frames: Iterable[Any], packets: Iterable[dict], limit: int = 360) -> list[dict]:
    limit = max(1, int(limit))
    items = [
        {"index": _value(frame, "index", 0), "size": int(_value(frame, "size", 0)), "keyframe": bool(_value(frame, "keyframe", False)), "kind": "frame"}
        for frame in frames
        if int(_value(frame, "size", 0)) > 0
    ]
    if not items:
        for packet in packets:
            try:
                size = int(packet.get("size", 0) or 0)
            except (TypeError, ValueError):
                size = 0
            if size <= 0:
                continue
            items.append(
                {
                    "index": packet.get("index", len(items)),
                    "size": size,
                    "keyframe": bool(packet.get("keyframe")),
                    "kind": str(packet.get("codec_type") or "packet"),
                }
            )
    if len(items) <= limit:
        return items
    sampled = []
    for index in range(limit):
        start = index * len(items) // limit
        end = max(start + 1, (index + 1) * len(items) // limit)
        bucket = items[start:end]
        largest = max(bucket, key=lambda item: item["size"])
        sampled.append(
            {
                "index": largest["index"],
                "size": largest["size"],
                "keyframe": any(item.get("keyframe") for item in bucket),
                "kind": largest["kind"],
            }
        )
    return sampled


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)
