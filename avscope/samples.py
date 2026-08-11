from __future__ import annotations

import struct
from pathlib import Path


def generate_samples(directory: str | Path) -> list[Path]:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    files = [
        _write(target / "sample.wav", _wav_sample()),
        _write(target / "sample.aac", _aac_sample()),
        _write(target / "sample.h264", _h264_sample()),
        _write(target / "sample.mp4", _mp4_sample()),
        _write(target / "sample_changed.mp4", _mp4_sample(extra_free=True)),
        _write(target / "sample.pcm", b"\x00\x00\x10\x00\xf0\xff" * 64),
        _write(target / "sample.yuv", b"\x10" * (64 * 48) + b"\x80" * (64 * 48 // 2)),
    ]
    return files


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _wav_sample() -> bytes:
    pcm = b"\x00\x00\x10\x00\xf0\xff\x00\x00" * 128
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
    data = b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", 4 + len(fmt) + len(data)) + b"WAVE" + fmt + data


def _aac_sample() -> bytes:
    frame = bytes([0xFF, 0xF1, 0x50, 0x80, 0x01, 0x9F, 0xFC]) + b"\x00" * 5
    return frame * 12


def _h264_sample() -> bytes:
    return (
        b"\x00\x00\x00\x01\x67\x64\x00\x1f\xac\xd9\x40"
        b"\x00\x00\x01\x68\xee\x3c\x80"
        b"\x00\x00\x01\x65\x88\x84\x21\xa0"
        b"\x00\x00\x01\x41\x9a\x22\x11"
    )


def _mp4_sample(extra_free: bool = False) -> bytes:
    ftyp_payload = b"isom" + struct.pack(">I", 0) + b"isomiso2"
    ftyp = struct.pack(">I4s", len(ftyp_payload) + 8, b"ftyp") + ftyp_payload
    mvhd_payload = b"\x00" * 24
    mvhd = struct.pack(">I4s", len(mvhd_payload) + 8, b"mvhd") + mvhd_payload
    moov_payload = mvhd
    if extra_free:
        moov_payload += struct.pack(">I4s", 8, b"free")
    moov = struct.pack(">I4s", len(moov_payload) + 8, b"moov") + moov_payload
    mdat_payload = b"\x00\x01\x02\x03\x04\x05\x06\x07"
    mdat = struct.pack(">I4s", len(mdat_payload) + 8, b"mdat") + mdat_payload
    return ftyp + moov + mdat
