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
