from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


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


def build_video_preview(path: str | Path, output_dir: str | Path = DEFAULT_PREVIEW_DIR, timeout: int = 12) -> dict[str, Any]:
    exe = find_ffmpeg()
    if not exe:
        return {"available": False, "error": "ffmpeg not found"}

    source = Path(path)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = preview_output_path(source, target_dir)
    command = [
        exe,
        "-hide_banner",
        "-v",
        "error",
        "-y",
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
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception as exc:
        return {"available": True, "error": str(exc)}
    if completed.returncode != 0 or not target.exists():
        return {"available": True, "error": completed.stderr.strip() or f"ffmpeg exited {completed.returncode}"}
    width, height = png_dimensions(target)
    return {
        "available": True,
        "path": str(target),
        "width": width,
        "height": height,
        "size": target.stat().st_size,
    }


def preview_output_path(source: Path, output_dir: Path) -> Path:
    try:
        stat = source.stat()
        marker = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        marker = str(source)
    digest = hashlib.sha1(marker.encode("utf-8", errors="replace")).hexdigest()[:12]
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in source.stem)[:40] or "preview"
    return output_dir / f"{stem}-{digest}.png"


def png_dimensions(path: str | Path) -> tuple[int | None, int | None]:
    data = Path(path).read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None, None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
