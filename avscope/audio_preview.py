from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any
from avscope.runtime import bundled_file, temp_dir


DEFAULT_AUDIO_PREVIEW_DIR = temp_dir("audio-previews")


def build_audio_preview_clip(
    path: str | Path,
    format_name: str,
    media_summary: dict[str, Any],
    output_dir: str | Path = DEFAULT_AUDIO_PREVIEW_DIR,
    start_seconds: float = 0.0,
    duration_seconds: float = 3.0,
) -> dict[str, Any]:
    source = Path(path)
    start = max(0.0, float(start_seconds or 0.0))
    duration = max(0.1, float(duration_seconds or 3.0))
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = audio_preview_output_path(source, target_dir, start, duration)
    try:
        if format_name == "WAV" or source.suffix.lower() == ".wav":
            return _wav_clip(source, target, start, duration)
        if format_name == "Raw PCM" or source.suffix.lower() == ".pcm":
            return _pcm_clip(source, target, media_summary, start, duration)
        return _ffmpeg_audio_clip(source, target, start, duration)
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def play_audio_preview_clip(clip_path: str | Path) -> dict[str, Any]:
    try:
        import winsound
    except ImportError:
        return {"available": False, "error": "winsound is only available on Windows"}
    try:
        winsound.PlaySound(str(clip_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except RuntimeError as exc:
        return {"available": True, "error": str(exc)}
    return {"available": True, "path": str(clip_path)}


def stop_audio_preview() -> dict[str, Any]:
    try:
        import winsound
    except ImportError:
        return {"available": False, "error": "winsound is only available on Windows"}
    winsound.PlaySound(None, 0)
    return {"available": True}


def audio_preview_output_path(source: Path, output_dir: Path, start_seconds: float, duration_seconds: float) -> Path:
    try:
        stat = source.stat()
        marker = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{start_seconds:.3f}|{duration_seconds:.3f}"
    except OSError:
        marker = f"{source}|{start_seconds:.3f}|{duration_seconds:.3f}"
    digest = hashlib.sha1(marker.encode("utf-8", errors="replace")).hexdigest()[:12]
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in source.stem)[:40] or "audio"
    return output_dir / f"{stem}-{_format_seconds(start_seconds)}s-{digest}.wav"


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
    bundled = bundled_file("ffmpeg.exe")
    if bundled:
        return str(bundled)
    return shutil.which("ffmpeg")


def _wav_clip(source: Path, target: Path, start_seconds: float, duration_seconds: float) -> dict[str, Any]:
    with wave.open(str(source), "rb") as src:
        params = src.getparams()
        start_frame = min(src.getnframes(), int(src.getframerate() * start_seconds))
        src.setpos(start_frame)
        frames = min(src.getnframes() - start_frame, max(1, int(src.getframerate() * duration_seconds)))
        if frames <= 0:
            raise ValueError("audio preview range is outside the source duration")
        data = src.readframes(frames)
    with wave.open(str(target), "wb") as dst:
        dst.setparams(params)
        dst.writeframes(data)
    return _clip_result(target, frames, params.framerate, params.nchannels, start_seconds)


def _pcm_clip(source: Path, target: Path, media_summary: dict[str, Any], start_seconds: float, duration_seconds: float) -> dict[str, Any]:
    sample_rate = int(media_summary.get("sample_rate", 48000))
    channels = int(media_summary.get("channels", 2))
    bits_per_sample = int(media_summary.get("bits_per_sample", 16))
    endian = str(media_summary.get("endian", "little")).lower()
    signed = _bool_option(media_summary.get("signed", True))
    sample_width = max(1, (bits_per_sample + 7) // 8)
    if sample_width not in {1, 2, 3, 4}:
        raise ValueError(f"unsupported PCM sample width: {sample_width}")
    frame_size = max(1, channels * sample_width)
    total_frames = source.stat().st_size // frame_size
    start_frame = min(total_frames, int(sample_rate * start_seconds))
    frames = min(total_frames - start_frame, max(1, int(sample_rate * duration_seconds)))
    if frames <= 0:
        raise ValueError("audio preview range is outside the source duration")
    with source.open("rb") as handle:
        handle.seek(start_frame * frame_size)
        data = handle.read(frames * frame_size)
    data = _pcm_to_wave_bytes(data, sample_width, endian, signed)
    with wave.open(str(target), "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(sample_width)
        dst.setframerate(sample_rate)
        dst.writeframes(data)
    return _clip_result(target, frames, sample_rate, channels, start_seconds)


def _ffmpeg_audio_clip(source: Path, target: Path, start_seconds: float, duration_seconds: float) -> dict[str, Any]:
    exe = find_ffmpeg()
    if not exe:
        return {"available": False, "error": "ffmpeg not found"}
    command = [
        exe,
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-t",
        f"{duration_seconds:.3f}",
        "-vn",
        "-acodec",
        "pcm_s16le",
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    if completed.returncode != 0 or not target.exists():
        return {"available": True, "error": completed.stderr.strip() or f"ffmpeg exited {completed.returncode}"}
    with wave.open(str(target), "rb") as wav:
        return _clip_result(target, wav.getnframes(), wav.getframerate(), wav.getnchannels(), start_seconds)


def _pcm_to_wave_bytes(data: bytes, sample_width: int, endian: str, signed: bool) -> bytes:
    if sample_width == 1:
        if signed:
            return bytes((int.from_bytes(bytes([value]), "little", signed=True) + 128) & 0xFF for value in data)
        return data
    endian = "big" if endian == "big" else "little"
    out = bytearray()
    bias = 1 << (sample_width * 8 - 1)
    for offset in range(0, len(data) - sample_width + 1, sample_width):
        value = int.from_bytes(data[offset : offset + sample_width], endian, signed=signed)
        if not signed:
            value -= bias
        out.extend(int(value).to_bytes(sample_width, "little", signed=True))
    return bytes(out)


def _clip_result(target: Path, frames: int, sample_rate: int, channels: int, start_seconds: float) -> dict[str, Any]:
    return {
        "available": True,
        "path": str(target),
        "start_seconds": start_seconds,
        "frames": frames,
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": frames / sample_rate if sample_rate else None,
        "size": target.stat().st_size,
    }


def _bool_option(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "unsigned", "无符号"}
    return bool(value)


def _format_seconds(seconds: float) -> str:
    return f"{max(0.0, seconds):.3f}".replace(".", "_")
