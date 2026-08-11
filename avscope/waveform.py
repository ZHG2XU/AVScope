from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Iterable


MAX_FRAMES_TO_SCAN = 1_000_000


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


def _wav_summary(path: str | Path, points: int) -> dict:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        total_frames = wav.getnframes()
        scan_frames = min(total_frames, MAX_FRAMES_TO_SCAN)
        frames_per_bucket = max(1, math.ceil(scan_frames / points))
        peaks = []
        scanned = 0
        while scanned < scan_frames:
            want = min(frames_per_bucket, scan_frames - scanned)
            data = wav.readframes(want)
            samples = list(_decode_samples(data, sample_width, channels))
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
        "ascii": ascii_waveform(peaks),
    }


def _pcm_summary(path: str | Path, media_summary: dict, points: int) -> dict:
    sample_rate = int(media_summary.get("sample_rate", 48000))
    channels = int(media_summary.get("channels", 2))
    bits_per_sample = int(media_summary.get("bits_per_sample", 16))
    sample_width = max(1, bits_per_sample // 8)
    frame_size = max(1, channels * sample_width)
    size = Path(path).stat().st_size
    total_frames = size // frame_size
    scan_frames = min(total_frames, MAX_FRAMES_TO_SCAN)
    frames_per_bucket = max(1, math.ceil(scan_frames / points))
    peaks = []
    with Path(path).open("rb") as fh:
        for _ in range(points):
            if len(peaks) * frames_per_bucket >= scan_frames:
                break
            want = min(frames_per_bucket, scan_frames - len(peaks) * frames_per_bucket)
            data = fh.read(want * frame_size)
            samples = list(_decode_samples(data, sample_width, channels))
            peaks.append(_bucket(samples))
    return {
        "available": True,
        "source": "pcm",
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "total_frames": total_frames,
        "scanned_frames": scan_frames,
        "duration_seconds": total_frames / sample_rate if sample_rate else None,
        "peaks": peaks,
        "ascii": ascii_waveform(peaks),
    }


def _decode_samples(data: bytes, sample_width: int, channels: int) -> Iterable[float]:
    channels = max(1, channels)
    if sample_width == 1:
        for index in range(0, len(data), channels):
            values = [(data[index + c] - 128) / 128 for c in range(channels) if index + c < len(data)]
            if values:
                yield sum(values) / len(values)
        return
    frame_size = sample_width * channels
    for index in range(0, len(data) - frame_size + 1, frame_size):
        values = []
        for channel in range(channels):
            pos = index + channel * sample_width
            values.append(_decode_one(data[pos : pos + sample_width]))
        yield sum(values) / len(values)


def _decode_one(raw: bytes) -> float:
    if len(raw) == 2:
        return struct.unpack("<h", raw)[0] / 32768
    if len(raw) == 3:
        value = int.from_bytes(raw, "little", signed=False)
        if value & 0x800000:
            value -= 0x1000000
        return value / 8388608
    if len(raw) == 4:
        return struct.unpack("<i", raw)[0] / 2147483648
    value = int.from_bytes(raw, "little", signed=True)
    scale = float(1 << (8 * len(raw) - 1))
    return value / scale if scale else 0.0


def _bucket(samples: list[float]) -> dict:
    if not samples:
        return {"min": 0.0, "max": 0.0, "rms": 0.0}
    lo = min(samples)
    hi = max(samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    return {"min": round(lo, 4), "max": round(hi, 4), "rms": round(rms, 4)}


def _amp_to_row(value: float, height: int) -> int:
    clamped = max(-1.0, min(1.0, value))
    return int(round((1.0 - clamped) * (height - 1) / 2.0))
