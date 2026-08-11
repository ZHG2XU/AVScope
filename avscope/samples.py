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
        _write(target / "sample.h265", _h265_sample()),
        _write(target / "sample.mp4", _mp4_sample()),
        _write(target / "sample_changed.mp4", _mp4_sample(extra_free=True)),
        _write(target / "sample.avi", _avi_sample()),
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
        b"\x00\x00\x00\x01\x67" + make_h264_baseline_sps(width=640, height=480)
        + b"\x00\x00\x01\x68\xee\x3c\x80"
        b"\x00\x00\x01\x65\x88\x84\x21\xa0"
        b"\x00\x00\x01\x41\x9a\x22\x11"
    )


def _h265_sample() -> bytes:
    return (
        _h265_nalu(32, make_h265_vps())
        + _h265_nalu(33, make_h265_sps(width=640, height=360))
        + _h265_nalu(34, b"\x80")
        + _h265_nalu(19, b"\x80")
    )


def make_h264_baseline_sps(width: int = 640, height: int = 480, profile_idc: int = 66, level_idc: int = 30) -> bytes:
    if width % 16 or height % 16:
        raise ValueError("synthetic SPS helper expects dimensions divisible by 16")
    writer = _BitWriter()
    writer.write_bits(profile_idc, 8)
    writer.write_bits(0, 8)
    writer.write_bits(level_idc, 8)
    writer.write_ue(0)
    writer.write_ue(0)
    writer.write_ue(0)
    writer.write_ue(0)
    writer.write_ue(1)
    writer.write_bit(0)
    writer.write_ue(width // 16 - 1)
    writer.write_ue(height // 16 - 1)
    writer.write_bit(1)
    writer.write_bit(1)
    writer.write_bit(0)
    writer.write_bit(0)
    return writer.finish()


def make_h265_vps(profile_idc: int = 1, level_idc: int = 120) -> bytes:
    writer = _BitWriter()
    writer.write_bits(0, 4)
    writer.write_bit(1)
    writer.write_bit(1)
    writer.write_bits(0, 6)
    writer.write_bits(0, 3)
    writer.write_bit(1)
    writer.write_bits(0xFFFF, 16)
    _write_h265_profile_tier_level(writer, profile_idc, level_idc)
    writer.write_bit(1)
    writer.write_ue(0)
    writer.write_ue(0)
    writer.write_ue(0)
    writer.write_bits(0, 6)
    writer.write_ue(0)
    return writer.finish()


def make_h265_sps(width: int = 640, height: int = 360, profile_idc: int = 1, level_idc: int = 120) -> bytes:
    writer = _BitWriter()
    writer.write_bits(0, 4)
    writer.write_bits(0, 3)
    writer.write_bit(1)
    _write_h265_profile_tier_level(writer, profile_idc, level_idc)
    writer.write_ue(0)
    writer.write_ue(1)
    writer.write_ue(width)
    writer.write_ue(height)
    writer.write_bit(0)
    writer.write_ue(0)
    writer.write_ue(0)
    writer.write_ue(4)
    writer.write_bit(1)
    writer.write_ue(0)
    writer.write_ue(0)
    writer.write_ue(0)
    return writer.finish()


def _write_h265_profile_tier_level(writer: "_BitWriter", profile_idc: int, level_idc: int) -> None:
    writer.write_bits(0, 2)
    writer.write_bit(0)
    writer.write_bits(profile_idc, 5)
    writer.write_bits(0, 32)
    writer.write_bit(1)
    writer.write_bit(0)
    writer.write_bit(0)
    writer.write_bit(1)
    writer.write_bits(0, 44)
    writer.write_bits(level_idc, 8)


def _h265_nalu(nal_type: int, rbsp: bytes) -> bytes:
    header = bytes([((nal_type & 0x3F) << 1) & 0x7E, 0x01])
    return b"\x00\x00\x00\x01" + header + rbsp


class _BitWriter:
    def __init__(self):
        self.bits: list[int] = []

    def write_bit(self, value: int) -> None:
        self.bits.append(1 if value else 0)

    def write_bits(self, value: int, count: int) -> None:
        for shift in range(count - 1, -1, -1):
            self.write_bit((value >> shift) & 1)

    def write_ue(self, value: int) -> None:
        code_num = value + 1
        bits = code_num.bit_length()
        for _ in range(bits - 1):
            self.write_bit(0)
        self.write_bits(code_num, bits)

    def finish(self) -> bytes:
        self.write_bit(1)
        while len(self.bits) % 8:
            self.write_bit(0)
        data = bytearray()
        for offset in range(0, len(self.bits), 8):
            byte = 0
            for bit in self.bits[offset : offset + 8]:
                byte = (byte << 1) | bit
            data.append(byte)
        return bytes(data)


def _mp4_sample(extra_free: bool = False) -> bytes:
    ftyp_payload = b"isom" + struct.pack(">I", 0) + b"isomiso2"
    ftyp = _mp4_box(b"ftyp", ftyp_payload)
    mvhd_payload = _mvhd_payload(timescale=1000, duration=5000)
    mvhd = _mp4_box(b"mvhd", mvhd_payload)
    mdat_payload = b"\x00\x01\x02\x03\x04\x05\x06\x07"
    moov_payload = mvhd + _mp4_track_sample(chunk_offset=0)
    if extra_free:
        moov_payload += _mp4_box(b"free", b"")
    moov = _mp4_box(b"moov", moov_payload)
    mdat_payload_offset = len(ftyp) + len(moov) + 8
    moov_payload = mvhd + _mp4_track_sample(chunk_offset=mdat_payload_offset)
    if extra_free:
        moov_payload += _mp4_box(b"free", b"")
    moov = _mp4_box(b"moov", moov_payload)
    mdat = _mp4_box(b"mdat", mdat_payload)
    return ftyp + moov + mdat


def _mvhd_payload(timescale: int, duration: int) -> bytes:
    return (
        b"\x00\x00\x00\x00"
        + struct.pack(">IIII", 0, 0, timescale, duration)
        + struct.pack(">I", 0x00010000)
        + struct.pack(">H", 0x0100)
        + b"\x00\x00"
        + b"\x00" * 8
        + struct.pack(">9I", 0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000)
        + b"\x00" * 24
        + struct.pack(">I", 2)
    )


def _mp4_track_sample(chunk_offset: int) -> bytes:
    tkhd = _mp4_box(b"tkhd", _tkhd_payload(track_id=1, duration=5000, width=640, height=360))
    mdhd = _mp4_box(b"mdhd", _mdhd_payload(timescale=30000, duration=150000, language="und"))
    hdlr = _mp4_box(b"hdlr", _hdlr_payload(handler_type=b"vide", name="VideoHandler"))
    stbl = _mp4_box(
        b"stbl",
        _mp4_stsd_payload()
        + _mp4_full_box(b"stts", 0, struct.pack(">III", 1, 1, 150))
        + _mp4_full_box(b"stsc", 0, struct.pack(">IIII", 1, 1, 1, 1))
        + _mp4_full_box(b"stsz", 0, struct.pack(">III", 0, 1, 8))
        + _mp4_full_box(b"stco", 0, struct.pack(">II", 1, chunk_offset)),
    )
    minf = _mp4_box(b"minf", stbl)
    mdia = _mp4_box(b"mdia", mdhd + hdlr + minf)
    return _mp4_box(b"trak", tkhd + mdia)


def _tkhd_payload(track_id: int, duration: int, width: int, height: int) -> bytes:
    return (
        b"\x00\x00\x00\x07"
        + struct.pack(">IIII", 0, 0, track_id, 0)
        + struct.pack(">I", duration)
        + b"\x00" * 8
        + struct.pack(">hhHh", 0, 0, 0, 0)
        + struct.pack(">9I", 0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000)
        + struct.pack(">II", width << 16, height << 16)
    )


def _mdhd_payload(timescale: int, duration: int, language: str) -> bytes:
    return (
        b"\x00\x00\x00\x00"
        + struct.pack(">IIII", 0, 0, timescale, duration)
        + struct.pack(">H", _encode_mp4_language(language))
        + b"\x00\x00"
    )


def _hdlr_payload(handler_type: bytes, name: str) -> bytes:
    return b"\x00\x00\x00\x00" + b"\x00" * 4 + handler_type + b"\x00" * 12 + name.encode("utf-8") + b"\x00"


def _mp4_stsd_payload() -> bytes:
    avc1_entry = _mp4_box(b"avc1", _video_sample_entry_payload(width=640, height=360, compressor_name="AVScope AVC"))
    return _mp4_full_box(b"stsd", 0, struct.pack(">I", 1) + avc1_entry)


def _video_sample_entry_payload(width: int, height: int, compressor_name: str) -> bytes:
    name = compressor_name.encode("utf-8")[:31]
    compressor = bytes([len(name)]) + name + b"\x00" * (31 - len(name))
    return (
        b"\x00" * 6
        + struct.pack(">H", 1)
        + b"\x00" * 16
        + struct.pack(">HH", width, height)
        + struct.pack(">II", 0x00480000, 0x00480000)
        + b"\x00" * 4
        + struct.pack(">H", 1)
        + compressor
        + struct.pack(">HH", 0x0018, 0xFFFF)
    )


def _mp4_full_box(box_type: bytes, flags: int, payload: bytes, version: int = 0) -> bytes:
    return _mp4_box(box_type, bytes([version]) + flags.to_bytes(3, "big") + payload)


def _mp4_box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, box_type) + payload


def _encode_mp4_language(language: str) -> int:
    text = (language or "und")[:3].lower()
    if len(text) != 3:
        text = "und"
    value = 0
    for char in text:
        value = (value << 5) | max(0, min(31, ord(char) - 0x60))
    return value


def _avi_sample() -> bytes:
    avih_payload = struct.pack(
        "<IIIIIIIIII4I",
        33333,
        1_000_000,
        0,
        0x10,
        150,
        0,
        1,
        4096,
        640,
        480,
        0,
        0,
        0,
        0,
    )
    avih = _riff_chunk(b"avih", avih_payload)
    strh_payload = (
        b"vids"
        + b"DIB "
        + struct.pack("<IIIIIIII", 0, 0, 0, 1, 30, 0, 150, 4096)
        + struct.pack("<Ihhhh", 0xFFFFFFFF, 0, 0, 640, 480)
    )
    strh = _riff_chunk(b"strh", strh_payload)
    strl = _riff_list(b"strl", strh)
    hdrl = _riff_list(b"hdrl", avih + strl)
    movi = _riff_list(b"movi", b"")
    payload = b"AVI " + hdrl + movi
    return b"RIFF" + struct.pack("<I", len(payload)) + payload


def _riff_chunk(chunk_id: bytes, payload: bytes) -> bytes:
    padding = b"\x00" if len(payload) & 1 else b""
    return chunk_id + struct.pack("<I", len(payload)) + payload + padding


def _riff_list(list_type: bytes, payload: bytes) -> bytes:
    body = list_type + payload
    padding = b"\x00" if len(body) & 1 else b""
    return b"LIST" + struct.pack("<I", len(body)) + body + padding
