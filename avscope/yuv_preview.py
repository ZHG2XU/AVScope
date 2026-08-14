from __future__ import annotations

import hashlib
from pathlib import Path
from avscope.runtime import temp_dir
from typing import Any


DEFAULT_YUV_PREVIEW_DIR = temp_dir("yuv-previews")
SUPPORTED_PIXEL_FORMATS = {"yuv420p", "nv12", "nv21", "yuyv422"}


def build_yuv_preview(
    path: str | Path,
    width: int,
    height: int,
    pixel_format: str,
    output_dir: str | Path = DEFAULT_YUV_PREVIEW_DIR,
    max_width: int = 640,
    frame_index: int = 0,
) -> dict[str, Any]:
    width = int(width)
    height = int(height)
    pixel_format = pixel_format.lower()
    frame_index = max(0, int(frame_index or 0))
    if width <= 0 or height <= 0:
        return {"available": False, "error": "Raw YUV width/height must be positive"}
    if pixel_format not in SUPPORTED_PIXEL_FORMATS:
        return {"available": False, "error": f"unsupported Raw YUV pixel format: {pixel_format}"}

    source = Path(path)
    frame_size = yuv_frame_size(width, height, pixel_format)
    try:
        file_size = source.stat().st_size
    except OSError as exc:
        return {"available": False, "error": str(exc)}
    total_frames = file_size // frame_size if frame_size > 0 else 0
    if file_size < frame_size and frame_index == 0:
        return {"available": False, "error": f"Raw YUV frame is incomplete: expected={frame_size} actual={file_size}"}
    if frame_index >= total_frames:
        return {
            "available": False,
            "error": f"Raw YUV frame index out of range: frame={frame_index} total={total_frames}",
            "frame_index": frame_index,
            "total_frames": total_frames,
        }
    with source.open("rb") as handle:
        handle.seek(frame_index * frame_size)
        data = handle.read(frame_size)
    if len(data) < frame_size:
        return {"available": False, "error": f"Raw YUV frame is incomplete: expected={frame_size} actual={len(data)}"}

    rgb = yuv_to_rgb(data, width, height, pixel_format)
    out_width = width
    out_height = height
    if max_width > 0 and width > max_width:
        out_width = max_width
        out_height = max(1, round(height * max_width / width))
        rgb = scale_rgb_nearest(rgb, width, height, out_width, out_height)

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = yuv_preview_output_path(source, target_dir, width, height, pixel_format, frame_index)
    write_ppm(target, out_width, out_height, rgb)
    return {
        "available": True,
        "path": str(target),
        "width": out_width,
        "height": out_height,
        "source_width": width,
        "source_height": height,
        "pixel_format": pixel_format,
        "frame_index": frame_index,
        "total_frames": total_frames,
        "size": target.stat().st_size,
    }


def yuv_frame_size(width: int, height: int, pixel_format: str) -> int:
    pixel_format = pixel_format.lower()
    if pixel_format in {"yuv420p", "nv12", "nv21"}:
        return width * height + 2 * ((width + 1) // 2) * ((height + 1) // 2)
    if pixel_format == "yuyv422":
        return width * height * 2
    raise ValueError(f"unsupported Raw YUV pixel format: {pixel_format}")


def yuv_to_rgb(data: bytes, width: int, height: int, pixel_format: str) -> bytes:
    pixel_format = pixel_format.lower()
    rgb = bytearray(width * height * 3)
    if pixel_format == "yuv420p":
        y_size = width * height
        uv_width = (width + 1) // 2
        uv_height = (height + 1) // 2
        u_offset = y_size
        v_offset = u_offset + uv_width * uv_height
        for y in range(height):
            for x in range(width):
                y_value = data[y * width + x]
                uv_index = (y // 2) * uv_width + (x // 2)
                _write_rgb(rgb, y * width + x, y_value, data[u_offset + uv_index], data[v_offset + uv_index])
        return bytes(rgb)
    if pixel_format in {"nv12", "nv21"}:
        y_size = width * height
        uv_width = (width + 1) // 2
        for y in range(height):
            for x in range(width):
                y_value = data[y * width + x]
                uv_index = y_size + ((y // 2) * uv_width + (x // 2)) * 2
                first = data[uv_index]
                second = data[uv_index + 1]
                u_value, v_value = (first, second) if pixel_format == "nv12" else (second, first)
                _write_rgb(rgb, y * width + x, y_value, u_value, v_value)
        return bytes(rgb)
    if pixel_format == "yuyv422":
        for y in range(height):
            row = y * width * 2
            for x in range(0, width, 2):
                pair = row + x * 2
                y0 = data[pair]
                u = data[pair + 1]
                y1 = data[pair + 2] if x + 1 < width else y0
                v = data[pair + 3] if x + 1 < width else 128
                _write_rgb(rgb, y * width + x, y0, u, v)
                if x + 1 < width:
                    _write_rgb(rgb, y * width + x + 1, y1, u, v)
        return bytes(rgb)
    raise ValueError(f"unsupported Raw YUV pixel format: {pixel_format}")


def scale_rgb_nearest(data: bytes, width: int, height: int, out_width: int, out_height: int) -> bytes:
    scaled = bytearray(out_width * out_height * 3)
    for y in range(out_height):
        src_y = min(height - 1, y * height // out_height)
        for x in range(out_width):
            src_x = min(width - 1, x * width // out_width)
            src = (src_y * width + src_x) * 3
            dst = (y * out_width + x) * 3
            scaled[dst : dst + 3] = data[src : src + 3]
    return bytes(scaled)


def write_ppm(path: str | Path, width: int, height: int, rgb: bytes) -> None:
    Path(path).write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + rgb)


def yuv_preview_output_path(source: Path, output_dir: Path, width: int, height: int, pixel_format: str, frame_index: int = 0) -> Path:
    try:
        stat = source.stat()
        marker = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{width}|{height}|{pixel_format}|{frame_index}"
    except OSError:
        marker = f"{source}|{width}|{height}|{pixel_format}|{frame_index}"
    digest = hashlib.sha1(marker.encode("utf-8", errors="replace")).hexdigest()[:12]
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in source.stem)[:40] or "yuv"
    suffix = "" if frame_index == 0 else f"-frame-{frame_index}"
    return output_dir / f"{stem}-{digest}{suffix}.ppm"


def _write_rgb(rgb: bytearray, pixel_index: int, y_value: int, u_value: int, v_value: int) -> None:
    c = y_value - 16
    d = u_value - 128
    e = v_value - 128
    offset = pixel_index * 3
    rgb[offset] = _clamp((298 * c + 409 * e + 128) >> 8)
    rgb[offset + 1] = _clamp((298 * c - 100 * d - 208 * e + 128) >> 8)
    rgb[offset + 2] = _clamp((298 * c + 516 * d + 128) >> 8)


def _clamp(value: int) -> int:
    return max(0, min(255, value))
