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
    gop_summary = _gop_summary(key_indices, len(items))
    gop_groups = _gop_groups(items)
    if gop_groups.get("groups_available"):
        gop_summary.update(gop_groups)
    summary = {
        "available": True,
        "items": len(items),
        "source": _summary_source(items),
        "series": _sample_series(items, max_points),
        "pts": _timestamp_summary(pts_values),
        "dts": _timestamp_summary(dts_values),
        "timestamp_anomalies": _timestamp_anomalies(items),
        "gop": gop_summary,
        "bitrate": _bitrate_summary(items, bucket_seconds),
    }
    rtp_sequence = _rtp_sequence_summary(items)
    if rtp_sequence.get("available"):
        summary["rtp_sequence"] = rtp_sequence
    pcr = _pcr_summary(items)
    if pcr.get("available"):
        summary["pcr"] = pcr
    by_stream = _stream_summaries(items)
    if by_stream:
        summary["by_stream"] = by_stream
    return summary


def _timeline_items(frames: Iterable[Any], packets: Iterable[dict]) -> list[dict]:
    items = []
    for frame in frames:
        metadata = _value(frame, "metadata", {}) or {}
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
                "rtp_sequence": _int_or_none(metadata.get("rtp_sequence")),
                "rtp_timestamp": _int_or_none(metadata.get("rtp_timestamp")),
                "rtp_ssrc": str(metadata.get("rtp_ssrc") or ""),
                "rtp_payload_type": _int_or_none(metadata.get("rtp_payload_type")),
                "rtp_marker": bool(metadata.get("rtp_marker")),
                "pcr_pid": str(metadata.get("pcr_pid") or ""),
                "pcr_base": _int_or_none(metadata.get("pcr_base")),
                "pcr_extension": _int_or_none(metadata.get("pcr_extension")),
                "pcr_seconds": _float_or_none(metadata.get("pcr_seconds")),
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


def _gop_groups(items: list[dict]) -> dict:
    key_positions = [position for position, item in enumerate(items) if item.get("keyframe")]
    if not key_positions:
        return {"available": False, "groups": []}
    groups = []
    for group_index, start_position in enumerate(key_positions):
        end_position = key_positions[group_index + 1] if group_index + 1 < len(key_positions) else len(items)
        group_items = items[start_position:end_position]
        if not group_items:
            continue
        pts_values = [item["pts"] for item in group_items if item.get("pts") is not None]
        bytes_total = sum(_int_or_zero(item.get("size")) for item in group_items)
        type_counts: dict[str, int] = {}
        for item in group_items:
            kind = str(item.get("kind") or "frame")
            type_counts[kind] = type_counts.get(kind, 0) + 1
        duration = None
        if len(pts_values) >= 2:
            duration = round(max(pts_values) - min(pts_values), 6)
        groups.append(
            {
                "index": group_index,
                "start_item_order": start_position,
                "end_item_order": end_position - 1,
                "start_index": group_items[0].get("index"),
                "end_index": group_items[-1].get("index"),
                "frames": len(group_items),
                "bytes": bytes_total,
                "duration": duration,
                "type_counts": type_counts,
                "start_pts": None if not pts_values else round(min(pts_values), 6),
                "end_pts": None if not pts_values else round(max(pts_values), 6),
            }
        )
    if not groups:
        return {"available": False, "groups": []}
    largest_frames = max(groups, key=lambda group: int(group.get("frames", 0) or 0))
    largest_bytes = max(groups, key=lambda group: int(group.get("bytes", 0) or 0))
    durations = [float(group["duration"]) for group in groups if group.get("duration") is not None]
    result = {
        "groups_available": True,
        "groups": groups[:120],
        "group_count": len(groups),
        "average_group_frames": round(sum(group["frames"] for group in groups) / len(groups), 2),
        "max_group_frames": largest_frames.get("frames", 0),
        "max_group_index": largest_frames.get("index", 0),
        "max_group_bytes": largest_bytes.get("bytes", 0),
        "max_group_bytes_index": largest_bytes.get("index", 0),
    }
    if durations:
        result["average_group_duration"] = round(sum(durations) / len(durations), 6)
        result["max_group_duration"] = round(max(durations), 6)
    return result


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


def _rtp_sequence_summary(items: list[dict]) -> dict:
    indexed = [(order, item) for order, item in enumerate(items) if item.get("rtp_sequence") is not None]
    if not indexed:
        return {"available": False, "packets": 0}
    grouped: dict[str, list[tuple[int, dict]]] = {}
    for order, item in indexed:
        grouped.setdefault(str(item.get("rtp_ssrc") or ""), []).append((order, item))
    streams = {}
    warnings = []
    for ssrc, stream_items in grouped.items():
        sequences = [int(item.get("rtp_sequence", 0)) for _, item in stream_items]
        marker_count = sum(1 for _, item in stream_items if item.get("rtp_marker"))
        stream_warnings = []
        previous = sequences[0]
        for position, (order, item) in enumerate(stream_items[1:], start=1):
            current = int(item.get("rtp_sequence", 0))
            expected = (previous + 1) & 0xFFFF
            if current != expected:
                warning = {
                    "ssrc": ssrc,
                    "item_order": order,
                    "index": item.get("index"),
                    "position": position,
                    "previous": previous,
                    "expected": expected,
                    "current": current,
                    "delta": (current - expected) & 0xFFFF,
                }
                stream_warnings.append(warning)
                warnings.append(warning)
            previous = current
        streams[ssrc or "unknown"] = {
            "packets": len(stream_items),
            "first_sequence": sequences[0],
            "last_sequence": sequences[-1],
            "min_sequence": min(sequences),
            "max_sequence": max(sequences),
            "marker_packets": marker_count,
            "sequence_warnings": len(stream_warnings),
        }
    return {
        "available": True,
        "packets": len(indexed),
        "streams": streams,
        "sequence_warnings": len(warnings),
        "warnings": warnings[:100],
        "series": _sample_rtp_series(indexed, 160),
    }


def _pcr_summary(items: list[dict]) -> dict:
    indexed = [(order, item) for order, item in enumerate(items) if item.get("pcr_seconds") is not None]
    if not indexed:
        return {"available": False, "points": 0}
    grouped: dict[str, list[tuple[int, dict]]] = {}
    for order, item in indexed:
        grouped.setdefault(str(item.get("pcr_pid") or "unknown"), []).append((order, item))
    by_pid = {}
    warnings = []
    for pid, pid_items in grouped.items():
        seconds = [float(item.get("pcr_seconds", 0.0) or 0.0) for _, item in pid_items]
        intervals = [round(seconds[index] - seconds[index - 1], 9) for index in range(1, len(seconds))]
        non_monotonic = sum(1 for interval in intervals if interval < 0)
        if non_monotonic:
            warnings.append({"pid": pid, "kind": "non_monotonic", "count": non_monotonic})
        summary = {
            "points": len(pid_items),
            "first": round(seconds[0], 9),
            "last": round(seconds[-1], 9),
            "span": round(seconds[-1] - seconds[0], 9),
            "min": round(min(seconds), 9),
            "max": round(max(seconds), 9),
            "non_monotonic": non_monotonic,
        }
        if intervals:
            average_interval = sum(intervals) / len(intervals)
            summary.update(
                {
                    "average_interval": round(average_interval, 9),
                    "min_interval": round(min(intervals), 9),
                    "max_interval": round(max(intervals), 9),
                    "max_interval_jitter": round(max(abs(interval - average_interval) for interval in intervals), 9),
                }
            )
        by_pid[pid] = summary
    return {
        "available": True,
        "points": len(indexed),
        "pid_count": len(grouped),
        "by_pid": by_pid,
        "warnings": warnings[:100],
        "series": _sample_pcr_series(indexed, 160),
    }


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
    point = {
        "index": item["index"],
        "stream": item["stream"],
        "pts": item["pts"],
        "dts": item["dts"],
        "duration": item["duration"],
        "size": item["size"],
        "keyframe": item["keyframe"],
        "kind": item["kind"],
    }
    if item.get("rtp_sequence") is not None:
        point["rtp_sequence"] = item.get("rtp_sequence")
        point["rtp_timestamp"] = item.get("rtp_timestamp")
        point["rtp_ssrc"] = item.get("rtp_ssrc")
        point["rtp_payload_type"] = item.get("rtp_payload_type")
        point["rtp_marker"] = item.get("rtp_marker")
    if item.get("pcr_seconds") is not None:
        point["pcr_pid"] = item.get("pcr_pid")
        point["pcr_base"] = item.get("pcr_base")
        point["pcr_extension"] = item.get("pcr_extension")
        point["pcr_seconds"] = item.get("pcr_seconds")
    return point


def _sample_rtp_series(indexed: list[tuple[int, dict]], max_points: int) -> list[dict]:
    max_points = max(1, int(max_points))
    if len(indexed) <= max_points:
        selected = indexed
    else:
        selected = []
        for index in range(max_points):
            source_index = index * len(indexed) // max_points
            selected.append(indexed[source_index])
    return [
        {
            "item_order": order,
            "index": item.get("index"),
            "sequence": item.get("rtp_sequence"),
            "timestamp": item.get("rtp_timestamp"),
            "ssrc": item.get("rtp_ssrc"),
            "payload_type": item.get("rtp_payload_type"),
            "marker": bool(item.get("rtp_marker")),
        }
        for order, item in selected
    ]


def _sample_pcr_series(indexed: list[tuple[int, dict]], max_points: int) -> list[dict]:
    max_points = max(1, int(max_points))
    if len(indexed) <= max_points:
        selected = indexed
    else:
        selected = []
        for index in range(max_points):
            source_index = index * len(indexed) // max_points
            selected.append(indexed[source_index])
    return [
        {
            "item_order": order,
            "index": item.get("index"),
            "pid": item.get("pcr_pid"),
            "pcr_base": item.get("pcr_base"),
            "pcr_extension": item.get("pcr_extension"),
            "seconds": item.get("pcr_seconds"),
        }
        for order, item in selected
    ]


def _choose_bucket_seconds(span: float, bucket_seconds: float | None) -> float:
    if bucket_seconds is not None and bucket_seconds > 0:
        return float(bucket_seconds)
    return max(0.1, min(10.0, span / 12.0))


def _int_or_zero(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
