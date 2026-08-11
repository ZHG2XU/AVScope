from __future__ import annotations

import math
import hashlib
import wave
from pathlib import Path
from typing import Iterable


MAX_FRAMES_TO_SCAN = 1_000_000
DEFAULT_WAVEFORM_PREVIEW_DIR = Path("G:/AVScope/tmp/waveform-previews")


def build_waveform_summary(path: str | Path, format_name: str, media_summary: dict, points: int = 96) -> dict:
    suffix = Path(path).suffix.lower()
    try:
        if format_name == "WAV" or suffix == ".wav":
            return _wav_summary(path, points)
        if format_name == "Raw PCM" or suffix == ".pcm":
            return _pcm_summary(path, media_summary, points)
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    return {"available": False, "error": "waveform is only available for WAV and PCM"}


def ascii_waveform(peaks: list[dict], height: int = 9) -> str:
    if not peaks:
        return ""
    height = max(5, height | 1)
    mid = height // 2
    grid = [[" " for _ in peaks] for _ in range(height)]
    for x, peak in enumerate(peaks):
        lo = float(peak.get("min", 0.0))
        hi = float(peak.get("max", 0.0))
        top = _amp_to_row(hi, height)
        bottom = _amp_to_row(lo, height)
        if top > bottom:
            top, bottom = bottom, top
        for y in range(top, bottom + 1):
            grid[y][x] = "|"
        grid[mid][x] = "-" if grid[mid][x] == " " else "+"
    return "\n".join("".join(row).rstrip() for row in grid)


def build_waveform_preview(
    path: str | Path,
    format_name: str,
    media_summary: dict,
    output_dir: str | Path = DEFAULT_WAVEFORM_PREVIEW_DIR,
    width: int = 720,
    height: int = 180,
) -> dict:
    width = int(width)
    height = int(height)
    if width < 160 or height < 80:
        return {"available": False, "error": "waveform preview size is too small"}

    waveform = media_summary.get("waveform", {}) if isinstance(media_summary, dict) else {}
    if not waveform.get("available"):
        waveform = build_waveform_summary(path, format_name, media_summary, points=min(width, 512))
    peaks = waveform.get("peaks", [])
    if not peaks:
        return {"available": False, "error": "waveform peaks are empty"}

    source = Path(path)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = waveform_preview_output_path(source, target_dir, width, height, len(peaks))
    write_waveform_ppm(target, width, height, peaks)
    return {
        "available": True,
        "path": str(target),
        "width": width,
        "height": height,
        "points": len(peaks),
        "size": target.stat().st_size,
    }


def write_waveform_ppm(path: str | Path, width: int, height: int, peaks: list[dict]) -> None:
    bg = (248, 250, 252)
    grid = (219, 228, 237)
    axis = (162, 174, 188)
    fill = (28, 113, 160)
    rms_fill = (46, 125, 92)
    pixels = bytearray(bg * (width * height))
    plot_left = 14
    plot_right = width - 14
    plot_top = 12
    plot_bottom = height - 14
    mid = (plot_top + plot_bottom) // 2

    for frac in (0.25, 0.5, 0.75):
        y = int(round(plot_top + (plot_bottom - plot_top) * frac))
        _draw_hline(pixels, width, height, plot_left, plot_right, y, axis if frac == 0.5 else grid)
    for step in range(1, 8):
        x = plot_left + (plot_right - plot_left) * step // 8
        _draw_vline(pixels, width, height, x, plot_top, plot_bottom, grid)

    plot_width = max(1, plot_right - plot_left)
    for x in range(plot_left, plot_right):
        peak = peaks[(x - plot_left) * len(peaks) // plot_width]
        lo = _preview_value_to_y(float(peak.get("min", 0.0)), plot_top, plot_bottom)
        hi = _preview_value_to_y(float(peak.get("max", 0.0)), plot_top, plot_bottom)
        if hi > lo:
            hi, lo = lo, hi
        _draw_vline(pixels, width, height, x, hi, lo, fill)
        rms = max(0.0, min(1.0, float(peak.get("rms", 0.0))))
        rms_y = int(round(rms * (plot_bottom - plot_top) / 2.0))
        _draw_vline(pixels, width, height, x, mid - rms_y, mid + rms_y, rms_fill)

    Path(path).write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(pixels))


def waveform_preview_output_path(source: Path, output_dir: Path, width: int, height: int, points: int) -> Path:
    try:
        stat = source.stat()
        marker = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{width}|{height}|{points}"
    except OSError:
        marker = f"{source}|{width}|{height}|{points}"
    digest = hashlib.sha1(marker.encode("utf-8", errors="replace")).hexdigest()[:12]
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in source.stem)[:40] or "audio"
    return output_dir / f"{stem}-{digest}.ppm"


def _wav_summary(path: str | Path, points: int) -> dict:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        total_frames = wav.getnframes()
        scan_frames = min(total_frames, MAX_FRAMES_TO_SCAN)
        frames_per_bucket = max(1, math.ceil(scan_frames / points))
        peaks = []
        energy = _energy_state()
        scanned = 0
        while scanned < scan_frames:
            want = min(frames_per_bucket, scan_frames - scanned)
            data = wav.readframes(want)
            samples = list(_decode_samples(data, sample_width, channels))
            _update_energy(energy, samples)
            peaks.append(_bucket(samples))
            scanned += want
    return {
        "available": True,
        "source": "wav",
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "total_frames": total_frames,
        "scanned_frames": scan_frames,
        "duration_seconds": total_frames / sample_rate if sample_rate else None,
        "peaks": peaks,
        "energy": _finish_energy(energy),
        "ascii": ascii_waveform(peaks),
    }


def _pcm_summary(path: str | Path, media_summary: dict, points: int) -> dict:
    sample_rate = int(media_summary.get("sample_rate", 48000))
    channels = int(media_summary.get("channels", 2))
    bits_per_sample = int(media_summary.get("bits_per_sample", 16))
    endian = str(media_summary.get("endian", "little")).lower()
    if endian not in {"little", "big"}:
        endian = "little"
    signed = _bool_option(media_summary.get("signed", True))
    sample_width = max(1, (bits_per_sample + 7) // 8)
    frame_size = max(1, channels * sample_width)
    size = Path(path).stat().st_size
    total_frames = size // frame_size
    scan_frames = min(total_frames, MAX_FRAMES_TO_SCAN)
    frames_per_bucket = max(1, math.ceil(scan_frames / points))
    peaks = []
    energy = _energy_state()
    with Path(path).open("rb") as fh:
        for _ in range(points):
            if len(peaks) * frames_per_bucket >= scan_frames:
                break
            want = min(frames_per_bucket, scan_frames - len(peaks) * frames_per_bucket)
            data = fh.read(want * frame_size)
            samples = list(_decode_samples(data, sample_width, channels, endian=endian, signed=signed))
            _update_energy(energy, samples)
            peaks.append(_bucket(samples))
    return {
        "available": True,
        "source": "pcm",
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "endian": endian,
        "signed": signed,
        "total_frames": total_frames,
        "scanned_frames": scan_frames,
        "duration_seconds": total_frames / sample_rate if sample_rate else None,
        "peaks": peaks,
        "energy": _finish_energy(energy),
        "ascii": ascii_waveform(peaks),
    }


def _decode_samples(data: bytes, sample_width: int, channels: int, endian: str = "little", signed: bool = True) -> Iterable[float]:
    channels = max(1, channels)
    if sample_width == 1:
        for index in range(0, len(data), channels):
            values = [_decode_one(data[index + c : index + c + 1], endian, signed) for c in range(channels) if index + c < len(data)]
            if values:
                yield sum(values) / len(values)
        return
    frame_size = sample_width * channels
    for index in range(0, len(data) - frame_size + 1, frame_size):
        values = []
        for channel in range(channels):
            pos = index + channel * sample_width
            values.append(_decode_one(data[pos : pos + sample_width], endian, signed))
        yield sum(values) / len(values)


def _decode_one(raw: bytes, endian: str = "little", signed: bool = True) -> float:
    bits = max(1, len(raw) * 8)
    scale = float(1 << (bits - 1))
    if signed:
        return int.from_bytes(raw, endian, signed=True) / scale
    return (int.from_bytes(raw, endian, signed=False) - scale) / scale


def _bucket(samples: list[float]) -> dict:
    if not samples:
        return {"min": 0.0, "max": 0.0, "rms": 0.0}
    lo = min(samples)
    hi = max(samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    return {"min": round(lo, 4), "max": round(hi, 4), "rms": round(rms, 4)}


def _energy_state() -> dict:
    return {"samples": 0, "sum_squares": 0.0, "peak": 0.0, "clipped_samples": 0}


def _update_energy(state: dict, samples: list[float]) -> None:
    for sample in samples:
        value = max(-1.0, min(1.0, float(sample)))
        absolute = abs(value)
        state["samples"] += 1
        state["sum_squares"] += value * value
        state["peak"] = max(state["peak"], absolute)
        if absolute >= 0.999:
            state["clipped_samples"] += 1


def _finish_energy(state: dict) -> dict:
    samples = int(state.get("samples", 0))
    peak = float(state.get("peak", 0.0))
    rms = math.sqrt(float(state.get("sum_squares", 0.0)) / samples) if samples else 0.0
    return {
        "sample_count": samples,
        "peak_level": round(peak, 6),
        "rms_level": round(rms, 6),
        "peak_dbfs": _dbfs(peak),
        "rms_dbfs": _dbfs(rms),
        "clipped_samples": int(state.get("clipped_samples", 0)),
    }


def _dbfs(value: float) -> float | None:
    if value <= 0:
        return None
    return round(20 * math.log10(value), 2)


def _amp_to_row(value: float, height: int) -> int:
    clamped = max(-1.0, min(1.0, value))
    return int(round((1.0 - clamped) * (height - 1) / 2.0))


def _bool_option(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "unsigned", "无符号"}
    return bool(value)


def _preview_value_to_y(value: float, top: int, bottom: int) -> int:
    clamped = max(-1.0, min(1.0, value))
    return int(round(top + (1.0 - clamped) * (bottom - top) / 2.0))


def _draw_hline(pixels: bytearray, width: int, height: int, x0: int, x1: int, y: int, color: tuple[int, int, int]) -> None:
    if y < 0 or y >= height:
        return
    for x in range(max(0, x0), min(width, x1 + 1)):
        _set_pixel(pixels, width, height, x, y, color)


def _draw_vline(pixels: bytearray, width: int, height: int, x: int, y0: int, y1: int, color: tuple[int, int, int]) -> None:
    if x < 0 or x >= width:
        return
    lo = max(0, min(y0, y1))
    hi = min(height - 1, max(y0, y1))
    for y in range(lo, hi + 1):
        _set_pixel(pixels, width, height, x, y, color)


def _set_pixel(pixels: bytearray, width: int, height: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    offset = (y * width + x) * 3
    pixels[offset : offset + 3] = bytes(color)
