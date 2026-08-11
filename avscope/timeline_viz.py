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


def build_timeline_summary(frames: Iterable[Any], packets: Iterable[dict], max_points: int = 240, bucket_seconds: float | None = None) -> dict:
    items = _timeline_items(frames, packets)
    if not items:
        return {"available": False, "items": 0}
    pts_values = [item["pts"] for item in items if item["pts"] is not None]
    dts_values = [item["dts"] for item in items if item["dts"] is not None]
    key_indices = [item["index"] for item in items if item["keyframe"]]
    summary = {
        "available": True,
        "items": len(items),
        "source": _summary_source(items),
        "series": _sample_series(items, max_points),
        "pts": _timestamp_summary(pts_values),
        "dts": _timestamp_summary(dts_values),
        "timestamp_anomalies": _timestamp_anomalies(items),
        "gop": _gop_summary(key_indices, len(items)),
        "bitrate": _bitrate_summary(items, bucket_seconds),
    }
    by_stream = _stream_summaries(items)
    if by_stream:
        summary["by_stream"] = by_stream
    return summary


def _timeline_items(frames: Iterable[Any], packets: Iterable[dict]) -> list[dict]:
    items = []
    for frame in frames:
        items.append(
            {
                "index": _value(frame, "index", len(items)),
                "stream": "",
                "size": _int_or_zero(_value(frame, "size", 0)),
                "pts": _float_or_none(_value(frame, "pts", None)),
                "dts": _float_or_none(_value(frame, "dts", None)),
                "duration": _float_or_none(_value(frame, "duration", None)),
                "keyframe": bool(_value(frame, "keyframe", False)),
                "kind": str(_value(frame, "frame_type", "") or "frame"),
                "source": "frame",
            }
        )
    for packet in packets:
        items.append(
            {
                "index": packet.get("index", len(items)),
                "stream": packet.get("stream_index", ""),
                "size": _int_or_zero(packet.get("size")),
                "pts": _float_or_none(packet.get("pts")),
                "dts": _float_or_none(packet.get("dts")),
                "duration": _float_or_none(packet.get("duration")),
                "keyframe": bool(packet.get("keyframe")),
                "kind": str(packet.get("codec_type") or "packet"),
                "source": "packet",
            }
        )
    return items


def _summary_source(items: list[dict]) -> str:
    sources = {item["source"] for item in items}
    if len(sources) == 1:
        return next(iter(sources))
    return "mixed"


def _timestamp_summary(values: list[float]) -> dict:
    if not values:
        return {"available": False, "points": 0}
    non_monotonic = sum(1 for index in range(1, len(values)) if values[index] < values[index - 1])
    return {
        "available": True,
        "points": len(values),
        "first": round(values[0], 6),
        "last": round(values[-1], 6),
        "span": round(values[-1] - values[0], 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "non_monotonic": non_monotonic,
    }


def _timestamp_anomalies(items: list[dict], tolerance: float = 0.000001) -> list[dict]:
    anomalies = []
    last_by_stream: dict[tuple[str, str], tuple[int, Any, float]] = {}
    for item_order, item in enumerate(items):
        stream = str(item.get("stream", ""))
        for key in ("pts", "dts"):
            current = item.get(key)
            if current is None:
                continue
            marker = (stream, key)
            previous = last_by_stream.get(marker)
            if previous is not None:
                previous_order, previous_index, previous_value = previous
                if current + tolerance < previous_value:
                    anomalies.append(
                        {
                            "kind": key,
                            "stream": stream,
                            "item_order": item_order,
                            "index": item.get("index"),
                            "previous_order": previous_order,
                            "previous_index": previous_index,
                            "previous": round(previous_value, 6),
                            "current": round(current, 6),
                        }
                    )
            last_by_stream[marker] = (item_order, item.get("index"), current)
    return anomalies[:100]


def _gop_summary(key_indices: list[Any], item_count: int) -> dict:
    if not key_indices:
        return {"available": False, "keyframes": 0, "keyframe_ratio": 0.0}
    intervals = []
    for index in range(1, len(key_indices)):
        try:
            intervals.append(int(key_indices[index]) - int(key_indices[index - 1]))
        except (TypeError, ValueError):
            intervals.append(index)
    summary = {
        "available": True,
        "keyframes": len(key_indices),
        "keyframe_ratio": round(len(key_indices) / max(1, item_count), 6),
        "first_keyframe_index": key_indices[0],
        "last_keyframe_index": key_indices[-1],
        "keyframe_indices": key_indices[:100],
        "intervals": intervals[:100],
    }
    if intervals:
        summary["average_interval"] = round(sum(intervals) / len(intervals), 2)
        summary["min_interval"] = min(intervals)
        summary["max_interval"] = max(intervals)
    return summary


def _bitrate_summary(items: list[dict], bucket_seconds: float | None) -> dict:
    timed = []
    for item in items:
        timestamp = item["pts"] if item["pts"] is not None else item["dts"]
        if timestamp is None or item["size"] <= 0:
            continue
        timed.append((timestamp, item["size"]))
    if len(timed) < 2:
        return {"available": False, "buckets": 0}
    timed.sort(key=lambda item: item[0])
    start = timed[0][0]
    end = timed[-1][0]
    span = end - start
    if span <= 0:
        return {"available": False, "buckets": 0}
    bucket = _choose_bucket_seconds(span, bucket_seconds)
    buckets: dict[int, int] = {}
    for timestamp, size in timed:
        index = int((timestamp - start) / bucket)
        buckets[index] = buckets.get(index, 0) + size
    rows = []
    for index in sorted(buckets):
        bucket_start = start + index * bucket
        bucket_end = bucket_start + bucket
        byte_count = buckets[index]
        rows.append(
            {
                "start": round(bucket_start, 6),
                "end": round(bucket_end, 6),
                "bytes": byte_count,
                "kbps": round(byte_count * 8 / bucket / 1000, 3),
            }
        )
    peak = max(rows, key=lambda row: row["kbps"])
    return {
        "available": True,
        "bucket_seconds": round(bucket, 6),
        "buckets": rows[:120],
        "bucket_count": len(rows),
        "average_kbps": round(sum(size for _, size in timed) * 8 / span / 1000, 3),
        "peak_kbps": peak["kbps"],
        "peak_start": peak["start"],
    }


def _stream_summaries(items: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        stream = str(item.get("stream", ""))
        if not stream:
            continue
        grouped.setdefault(stream, []).append(item)
    summaries = {}
    for stream, stream_items in grouped.items():
        pts_values = [item["pts"] for item in stream_items if item["pts"] is not None]
        dts_values = [item["dts"] for item in stream_items if item["dts"] is not None]
        key_indices = [item["index"] for item in stream_items if item["keyframe"]]
        summaries[stream] = {
            "items": len(stream_items),
            "bytes": sum(item["size"] for item in stream_items),
            "pts": _timestamp_summary(pts_values),
            "dts": _timestamp_summary(dts_values),
            "gop": _gop_summary(key_indices, len(stream_items)),
        }
    return summaries


def _sample_series(items: list[dict], max_points: int) -> list[dict]:
    max_points = max(1, int(max_points))
    if len(items) <= max_points:
        return [_series_point(item) for item in items]
    sampled = []
    for index in range(max_points):
        start = index * len(items) // max_points
        end = max(start + 1, (index + 1) * len(items) // max_points)
        bucket = items[start:end]
        largest = max(bucket, key=lambda item: item["size"])
        point = _series_point(largest)
        point["keyframe"] = any(item.get("keyframe") for item in bucket)
        sampled.append(point)
    return sampled


def _series_point(item: dict) -> dict:
    return {
        "index": item["index"],
        "stream": item["stream"],
        "pts": item["pts"],
        "dts": item["dts"],
        "duration": item["duration"],
        "size": item["size"],
        "keyframe": item["keyframe"],
        "kind": item["kind"],
    }


def _choose_bucket_seconds(span: float, bucket_seconds: float | None) -> float:
    if bucket_seconds is not None and bucket_seconds > 0:
        return float(bucket_seconds)
    return max(0.1, min(10.0, span / 12.0))


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


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)
