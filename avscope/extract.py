from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from avscope.ffmpeg_preview import find_ffmpeg


EXTRACT_KINDS = {"audio", "video", "keyframe"}


def build_extract_command(ffmpeg: str, source: str | Path, target: str | Path, kind: str) -> list[str]:
    if kind not in EXTRACT_KINDS:
        raise ValueError(f"Unsupported extract kind: {kind}")
    command = [ffmpeg, "-hide_banner", "-v", "error", "-y"]
    if kind == "keyframe":
        command.extend(["-skip_frame", "nokey"])
    command.extend(["-i", str(source)])
    if kind == "audio":
        command.extend(["-map", "0:a:0", "-c", "copy"])
    elif kind == "video":
        command.extend(["-map", "0:v:0", "-c", "copy"])
    else:
        command.extend(["-map", "0:v:0", "-frames:v", "1"])
    command.append(str(target))
    return command


def extract_media_stream(source: str | Path, target: str | Path, kind: str, timeout: int = 60) -> dict[str, Any]:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return {"available": False, "error": "ffmpeg not found"}
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_extract_command(ffmpeg, source, target_path, kind)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return {"available": True, "error": str(exc), "output": str(target_path), "kind": kind}
    if completed.returncode != 0 or not target_path.exists() or target_path.stat().st_size <= 0:
        return {
            "available": True,
            "error": completed.stderr.strip() or f"ffmpeg exited {completed.returncode}",
            "output": str(target_path),
            "kind": kind,
        }
    return {
        "available": True,
        "output": str(target_path),
        "kind": kind,
        "size": target_path.stat().st_size,
    }
