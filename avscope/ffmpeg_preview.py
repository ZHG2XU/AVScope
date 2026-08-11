from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from avscope.ffprobe import find_ffprobe


DEFAULT_FFMPEG = Path("E:/DevelopmentEnvironment/ffmpeg-8.1-essentials_build/bin/ffmpeg.exe")
DEFAULT_PREVIEW_DIR = Path("G:/AVScope/tmp/previews")


def find_ffmpeg() -> str | None:
    override = os.environ.get("AVSCOPE_FFMPEG")
    if override and Path(override).exists():
        return override
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [
        executable_dir / "ffmpeg.exe",
        executable_dir / "_internal" / "ffmpeg.exe",
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(getattr(sys, "_MEIPASS")) / "ffmpeg.exe")
    for bundled in candidates:
        if bundled.exists():
            return str(bundled)
    if DEFAULT_FFMPEG.exists():
        return str(DEFAULT_FFMPEG)
    return shutil.which("ffmpeg")


def build_video_preview(
    path: str | Path,
    output_dir: str | Path = DEFAULT_PREVIEW_DIR,
    timeout: int = 12,
    position_seconds: float = 0.0,
) -> dict[str, Any]:
    exe = find_ffmpeg()
    if not exe:
        return {"available": False, "error": "ffmpeg not found"}

    source = Path(path)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    position = max(0.0, float(position_seconds or 0.0))
    target = preview_output_path(source, target_dir, position)
    command = [
        exe,
        "-hide_banner",
        "-v",
        "error",
        "-y",
    ]
    if position > 0:
        command.extend(["-ss", _format_seek(position)])
    command.extend(
        [
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-vf",
            "scale='min(640,iw)':-2",
            str(target),
        ]
    )
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return {"available": True, "error": str(exc), "position_seconds": position}
    if completed.returncode != 0 or not target.exists():
        return {"available": True, "error": completed.stderr.strip() or f"ffmpeg exited {completed.returncode}", "position_seconds": position}
    width, height = png_dimensions(target)
    frame_info = probe_video_frame_info(source, position, timeout=timeout)
    return {
        "available": True,
        "path": str(target),
        "width": width,
        "height": height,
        "size": target.stat().st_size,
        "position_seconds": position,
        "frame_info": frame_info,
    }


def probe_video_frame_info(path: str | Path, position_seconds: float = 0.0, timeout: int = 8) -> dict[str, Any]:
    exe = find_ffprobe()
    position = max(0.0, float(position_seconds or 0.0))
    if not exe:
        return {"available": False, "error": "ffprobe not found", "position_seconds": position}
    command = [
        exe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-read_intervals",
        f"{_format_seek(position)}%+1",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time,pts_time,pkt_dts_time,pkt_duration_time,pkt_size,pict_type,key_frame,width,height,pix_fmt",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return {"available": True, "error": str(exc), "position_seconds": position}
    if completed.returncode != 0:
        return {"available": True, "error": completed.stderr.strip() or f"ffprobe exited {completed.returncode}", "position_seconds": position}
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"available": True, "error": f"invalid ffprobe json: {exc}", "position_seconds": position}
    frames = data.get("frames", [])
    if not frames:
        return {"available": True, "error": "no video frame metadata", "position_seconds": position}
    frame = frames[0]
    return {
        "available": True,
        "position_seconds": position,
        "pts": _float_or_none(frame.get("best_effort_timestamp_time") or frame.get("pts_time")),
        "dts": _float_or_none(frame.get("pkt_dts_time")),
        "duration": _float_or_none(frame.get("pkt_duration_time")),
        "size": _int_or_none(frame.get("pkt_size")),
        "frame_type": str(frame.get("pict_type") or ""),
        "keyframe": str(frame.get("key_frame", "")) == "1",
        "width": _int_or_none(frame.get("width")),
        "height": _int_or_none(frame.get("height")),
        "pix_fmt": str(frame.get("pix_fmt") or ""),
    }


def find_video_keyframe_time(
    path: str | Path,
    start_seconds: float = 0.0,
    direction: int = 1,
    packet_timeline: dict | None = None,
    window_seconds: float = 30.0,
    timeout: int = 8,
) -> dict[str, Any]:
    position = max(0.0, float(start_seconds or 0.0))
    step = 1 if direction >= 0 else -1
    packet_match = _keyframe_from_packet_timeline(packet_timeline or {}, position, step)
    if packet_match:
        return packet_match

    exe = find_ffprobe()
    if not exe:
        return {"available": False, "error": "ffprobe not found", "position_seconds": position}

    window = max(0.5, float(window_seconds or 30.0))
    if step > 0:
        interval_start = position + 0.001
        interval_duration = window
    else:
        interval_start = max(0.0, position - window)
        interval_duration = max(0.5, position - interval_start)
    command = [
        exe,
        "-v",
        "error",
        "-skip_frame",
        "nokey",
        "-select_streams",
        "v:0",
        "-read_intervals",
        f"{_format_seek(interval_start)}%+{_format_seek(interval_duration)}",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time,pts_time,pkt_dts_time,pict_type,key_frame",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return {"available": True, "error": str(exc), "position_seconds": position}
    if completed.returncode != 0:
        return {"available": True, "error": completed.stderr.strip() or f"ffprobe exited {completed.returncode}", "position_seconds": position}
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"available": True, "error": f"invalid ffprobe json: {exc}", "position_seconds": position}
    frames = [
        frame
        for frame in data.get("frames", [])
        if str(frame.get("key_frame", "1")) == "1" and _frame_time(frame) is not None
    ]
    if step > 0:
        candidates = [(float(_frame_time(frame)), frame) for frame in frames if float(_frame_time(frame)) > position + 0.0005]
        selected = min(candidates, default=None, key=lambda item: item[0])
    else:
        candidates = [(float(_frame_time(frame)), frame) for frame in frames if float(_frame_time(frame)) < max(0.0, position - 0.0005)]
        selected = max(candidates, default=None, key=lambda item: item[0])
    if not selected:
        label = "next" if step > 0 else "previous"
        return {"available": True, "error": f"no {label} keyframe in {window:.3f}s window", "position_seconds": position}
    target, frame = selected
    return {
        "available": True,
        "position_seconds": target,
        "source": "ffprobe",
        "frame_type": str(frame.get("pict_type") or ""),
        "keyframe": True,
    }


def find_video_frame_time(
    path: str | Path,
    frame_index: int,
    timeout: int = 12,
    max_scan_frames: int = 10000,
) -> dict[str, Any]:
    target_index = int(frame_index)
    if target_index < 0:
        return {"available": True, "error": "frame index must be >= 0", "frame_index": target_index}
    if target_index >= max_scan_frames:
        return {
            "available": True,
            "error": f"frame index exceeds scan limit {max_scan_frames - 1}",
            "frame_index": target_index,
        }
    exe = find_ffprobe()
    if not exe:
        return {"available": False, "error": "ffprobe not found", "frame_index": target_index}
    command = [
        exe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-read_intervals",
        f"%+#{target_index + 1}",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time,pts_time,pkt_dts_time,pkt_duration_time,pkt_size,pict_type,key_frame,width,height,pix_fmt",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return {"available": True, "error": str(exc), "frame_index": target_index}
    if completed.returncode != 0:
        return {"available": True, "error": completed.stderr.strip() or f"ffprobe exited {completed.returncode}", "frame_index": target_index}
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"available": True, "error": f"invalid ffprobe json: {exc}", "frame_index": target_index}
    frames = data.get("frames", [])
    if target_index >= len(frames):
        return {"available": True, "error": f"frame index {target_index} not found", "frame_index": target_index}
    frame = frames[target_index]
    position = _frame_time(frame)
    if position is None:
        return {"available": True, "error": f"frame index {target_index} has no timestamp", "frame_index": target_index}
    return {
        "available": True,
        "frame_index": target_index,
        "position_seconds": position,
        "frame_info": _video_frame_info(frame, position),
    }


def preview_output_path(source: Path, output_dir: Path, position_seconds: float = 0.0) -> Path:
    try:
        stat = source.stat()
        marker = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        marker = str(source)
    position = max(0.0, float(position_seconds or 0.0))
    marker = f"{marker}|{position:.3f}"
    digest = hashlib.sha1(marker.encode("utf-8", errors="replace")).hexdigest()[:12]
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in source.stem)[:40] or "preview"
    suffix = "" if position == 0 else f"-{_format_seek(position).replace('.', '_')}s"
    return output_dir / f"{stem}-{digest}{suffix}.png"


def _format_seek(seconds: float) -> str:
    return f"{max(0.0, seconds):.3f}"


def png_dimensions(path: str | Path) -> tuple[int | None, int | None]:
    data = Path(path).read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None, None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _frame_time(frame: dict[str, Any]) -> float | None:
    return _float_or_none(frame.get("best_effort_timestamp_time") or frame.get("pts_time") or frame.get("pkt_dts_time"))


def _packet_time(packet: dict[str, Any]) -> float | None:
    return _float_or_none(packet.get("pts") if packet.get("pts") is not None else packet.get("dts"))


def _keyframe_from_packet_timeline(packet_timeline: dict, position: float, direction: int) -> dict[str, Any] | None:
    packets = []
    for packet in packet_timeline.get("packets", []):
        if packet.get("codec_type") not in {"", "video"}:
            continue
        if not packet.get("keyframe"):
            continue
        packet_time = _packet_time(packet)
        if packet_time is None:
            continue
        if direction > 0 and packet_time > position + 0.0005:
            packets.append((packet_time, packet))
        elif direction < 0 and packet_time < max(0.0, position - 0.0005):
            packets.append((packet_time, packet))
    if not packets:
        return None
    target, packet = (min if direction > 0 else max)(packets, key=lambda item: item[0])
    return {
        "available": True,
        "position_seconds": target,
        "source": "packet_timeline",
        "packet_index": packet.get("index"),
        "keyframe": True,
    }


def _video_frame_info(frame: dict[str, Any], position: float) -> dict[str, Any]:
    return {
        "available": True,
        "position_seconds": position,
        "pts": _float_or_none(frame.get("best_effort_timestamp_time") or frame.get("pts_time")),
        "dts": _float_or_none(frame.get("pkt_dts_time")),
        "duration": _float_or_none(frame.get("pkt_duration_time")),
        "size": _int_or_none(frame.get("pkt_size")),
        "frame_type": str(frame.get("pict_type") or ""),
        "keyframe": str(frame.get("key_frame", "")) == "1",
        "width": _int_or_none(frame.get("width")),
        "height": _int_or_none(frame.get("height")),
        "pix_fmt": str(frame.get("pix_fmt") or ""),
    }
