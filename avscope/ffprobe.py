from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from avscope.runtime import bundled_file


def find_ffprobe() -> str | None:
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [
        executable_dir / "ffprobe.exe",
        executable_dir / "_internal" / "ffprobe.exe",
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(getattr(sys, "_MEIPASS")) / "ffprobe.exe")
    for bundled in candidates:
        if bundled.exists():
            return str(bundled)
    bundled = bundled_file("ffprobe.exe")
    if bundled:
        return str(bundled)
    return shutil.which("ffprobe")


def probe_media(path: str | Path, timeout: int = 8) -> dict[str, Any]:
    exe = find_ffprobe()
    if not exe:
        return {"available": False, "error": "ffprobe not found"}
    command = [
        exe,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return {"available": True, "error": str(exc)}
    if completed.returncode != 0:
        return {"available": True, "error": completed.stderr.strip() or f"ffprobe exited {completed.returncode}"}
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"available": True, "error": f"invalid ffprobe json: {exc}"}
    return {
        "available": True,
        "format": _format_summary(data.get("format", {})),
        "streams": [_stream_summary(stream) for stream in data.get("streams", [])],
    }


def probe_packet_timeline(path: str | Path, max_packets: int = 200, timeout: int = 8) -> dict[str, Any]:
    exe = find_ffprobe()
    if not exe:
        return {"available": False, "error": "ffprobe not found", "packets": []}
    command = [
        exe,
        "-v",
        "error",
        "-read_intervals",
        f"%+#{max_packets}",
        "-show_packets",
        "-show_entries",
        "packet=stream_index,codec_type,pts_time,dts_time,duration_time,size,pos,flags",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return {"available": True, "error": str(exc), "packets": []}
    if completed.returncode != 0:
        return {"available": True, "error": completed.stderr.strip() or f"ffprobe exited {completed.returncode}", "packets": []}
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"available": True, "error": f"invalid ffprobe json: {exc}", "packets": []}
    packets = []
    for index, packet in enumerate(data.get("packets", [])[:max_packets]):
        packets.append(
            {
                "index": index,
                "stream_index": packet.get("stream_index"),
                "codec_type": packet.get("codec_type", ""),
                "pts": _float_or_none(packet.get("pts_time")),
                "dts": _float_or_none(packet.get("dts_time")),
                "duration": _float_or_none(packet.get("duration_time")),
                "size": _int_or_none(packet.get("size")),
                "pos": _int_or_none(packet.get("pos")),
                "flags": packet.get("flags", ""),
                "keyframe": "K" in str(packet.get("flags", "")),
            }
        )
    return {"available": True, "packets": packets}


def _format_summary(format_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "format_name": format_info.get("format_name", ""),
        "duration": format_info.get("duration", ""),
        "bit_rate": format_info.get("bit_rate", ""),
        "probe_score": format_info.get("probe_score", ""),
    }


def _stream_summary(stream: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": stream.get("index"),
        "codec_type": stream.get("codec_type", ""),
        "codec_name": stream.get("codec_name", ""),
        "profile": stream.get("profile", ""),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "sample_rate": stream.get("sample_rate"),
        "channels": stream.get("channels"),
        "pix_fmt": stream.get("pix_fmt", ""),
        "sample_fmt": stream.get("sample_fmt", ""),
        "duration": stream.get("duration", ""),
        "bit_rate": stream.get("bit_rate", ""),
        "nb_frames": stream.get("nb_frames", ""),
        "r_frame_rate": stream.get("r_frame_rate", ""),
        "avg_frame_rate": stream.get("avg_frame_rate", ""),
        "time_base": stream.get("time_base", ""),
    }


def _float_or_none(value: Any) -> float | None:
    if value in (None, "N/A", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, "N/A", ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
