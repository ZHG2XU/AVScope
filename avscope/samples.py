from __future__ import annotations

import math
import struct
from pathlib import Path


TS_PACKET_SIZE = 188


def generate_samples(directory: str | Path) -> list[Path]:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    files = [
        _write(target / "sample.wav", _wav_sample()),
        _write(target / "sample.aac", _aac_sample()),
        _write(target / "sample.h264", _h264_sample()),
        _write(target / "sample.h265", _h265_sample()),
        _write(target / "sample_h264_issues.h264", _h264_issue_sample()),
        _write(target / "sample_h265_issues.h265", _h265_issue_sample()),
        _write(target / "sample.mp4", _mp4_sample()),
        _write(target / "sample_changed.mp4", _mp4_sample(extra_free=True)),
        _write(target / "sample.avi", _avi_sample()),
        _write(target / "sample.flv", _flv_sample()),
        _write(target / "sample.mkv", _matroska_sample()),
        _write(target / "sample.ps", _mpegps_sample()),
        _write(target / "sample.pcap", _pcap_rtp_sample()),
        _write(target / "sample_rtp_anomalies.pcap", _pcap_rtp_anomaly_sample()),
        _write(target / "sample.ts", _mpegts_sample()),
        _write(target / "sample.pcm", _pcm_sample()),
        _write(target / "sample.yuv", _yuv420p_color_bars()),
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


def _pcm_sample(sample_rate: int = 8000, frequency: float = 440.0, duration: float = 0.25) -> bytes:
    frames = max(1, round(sample_rate * duration))
    amplitude = 0.72 * ((1 << 15) - 1)
    return b"".join(
        struct.pack("<h", round(amplitude * math.sin(2.0 * math.pi * frequency * index / sample_rate)))
        for index in range(frames)
    )


def _yuv420p_color_bars(width: int = 64, height: int = 48, frames: int = 3) -> bytes:
    bars = [
        (180, 128, 128),
        (162, 44, 142),
        (131, 156, 44),
        (112, 72, 58),
        (84, 184, 198),
        (65, 100, 212),
        (35, 212, 114),
        (16, 128, 128),
    ]
    output = bytearray()
    uv_width = (width + 1) // 2
    uv_height = (height + 1) // 2
    for frame in range(max(1, frames)):
        ordered = bars[frame % len(bars) :] + bars[: frame % len(bars)]
        y_plane = bytearray(width * height)
        u_plane = bytearray(uv_width * uv_height)
        v_plane = bytearray(uv_width * uv_height)
        for row in range(height):
            for column in range(width):
                bar = min(len(ordered) - 1, column * len(ordered) // width)
                y_plane[row * width + column] = ordered[bar][0]
        for row in range(uv_height):
            for column in range(uv_width):
                bar = min(len(ordered) - 1, column * 2 * len(ordered) // width)
                u_plane[row * uv_width + column] = ordered[bar][1]
                v_plane[row * uv_width + column] = ordered[bar][2]
        output.extend(y_plane + u_plane + v_plane)
    return bytes(output)


def _aac_sample() -> bytes:
    frame = bytes([0xFF, 0xF1, 0x50, 0x80, 0x01, 0x9F, 0xFC]) + b"\x00" * 5
    return frame * 12


def _h264_sample() -> bytes:
    return (
        b"\x00\x00\x00\x01\x67" + make_h264_baseline_sps(width=640, height=480)
        + b"\x00\x00\x01\x68" + make_h264_pps()
        + b"\x00\x00\x01\x65" + make_h264_slice_header(pps_id=0, slice_type=2)
        + b"\x00\x00\x01\x41" + make_h264_slice_header(pps_id=0, slice_type=0)
    )


def _h265_sample() -> bytes:
    return (
        _h265_nalu(32, make_h265_vps())
        + _h265_nalu(33, make_h265_sps(width=640, height=360))
        + _h265_nalu(34, make_h265_pps())
        + _h265_nalu(19, make_h265_slice_header(pps_id=0, irap=True))
    )


def _h264_issue_sample() -> bytes:
    return (
        b"\x00\x00\x00\x01\x65" + make_h264_slice_header(pps_id=7, slice_type=2)
        + b"\x00\x00\x01\x67" + make_h264_baseline_sps(width=640, height=480, seq_parameter_set_id=0)
        + b"\x00\x00\x01\x68" + make_h264_pps(pic_parameter_set_id=0, seq_parameter_set_id=0)
        + b"\x00\x00\x01\x65" + make_h264_slice_header(pps_id=0, slice_type=2)
        + b"\x00\x00\x01\x67" + make_h264_baseline_sps(width=320, height=240, seq_parameter_set_id=1)
        + b"\x00\x00\x01\x68" + make_h264_pps(pic_parameter_set_id=1, seq_parameter_set_id=9)
        + b"\x00\x00\x01\x41" + make_h264_slice_header(pps_id=1, slice_type=0)
    )


def _h265_issue_sample() -> bytes:
    return (
        _h265_nalu(19, make_h265_slice_header(pps_id=7, irap=True))
        + _h265_nalu(32, make_h265_vps(video_parameter_set_id=0))
        + _h265_nalu(33, make_h265_sps(width=640, height=360, video_parameter_set_id=0, seq_parameter_set_id=0))
        + _h265_nalu(34, make_h265_pps(pic_parameter_set_id=0, seq_parameter_set_id=0))
        + _h265_nalu(19, make_h265_slice_header(pps_id=0, irap=True))
        + _h265_nalu(33, make_h265_sps(width=1280, height=720, video_parameter_set_id=9, seq_parameter_set_id=1))
        + _h265_nalu(34, make_h265_pps(pic_parameter_set_id=1, seq_parameter_set_id=8))
        + _h265_nalu(1, make_h265_slice_header(pps_id=1, irap=False))
    )


def _mpegts_sample() -> bytes:
    return (
        _ts_packet(pid=0x0000, payload_unit_start=True, continuity_counter=0, payload=b"\x00\xb0\r\x00\x01\xc1\x00\x00\x00\x01\xe1\x00")
        + _ts_packet(pid=0x0100, payload_unit_start=True, continuity_counter=0, payload=b"\x00\x00\x01\xe0\x00\x00\x80\x80\x05", pcr_base=0)
        + _ts_packet(pid=0x0100, payload_unit_start=False, continuity_counter=1, payload=b"\x65\x88\x84\x21", pcr_base=90000)
    )


def _mpegps_sample() -> bytes:
    pack = b"\x00\x00\x01\xBA" + bytes.fromhex("44 00 04 00 04 01 00 01 89 C0")
    system_payload = b"\x80\x04\x04\xE0\x7F\xFF"
    system = b"\x00\x00\x01\xBB" + struct.pack(">H", len(system_payload)) + system_payload
    pes_payload = _pes_header(pts_90k=90000) + b"\x00\x00\x01\x65\x88\x84\x21"
    video_pes = b"\x00\x00\x01\xE0" + struct.pack(">H", len(pes_payload)) + pes_payload
    audio_payload = _pes_header(pts_90k=90000) + b"\x11\x22\x33\x44"
    audio_pes = b"\x00\x00\x01\xC0" + struct.pack(">H", len(audio_payload)) + audio_payload
    return pack + system + video_pes + audio_pes


def _pcap_rtp_sample() -> bytes:
    global_header = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    packets = [
        _pcap_packet(0, _ethernet_ipv4_udp_rtp(sequence=100, timestamp=90000, marker=False, payload=b"\x65\x88\x84")),
        _pcap_packet(1, _ethernet_ipv4_udp_rtp(sequence=101, timestamp=93000, marker=True, payload=b"\x41\x9A\x22")),
        _pcap_packet(2, _ethernet_ipv4_udp(_rtcp_compound_sample(), src_port=5005, dst_port=5005)),
    ]
    return global_header + b"".join(packets)


def _pcap_rtp_anomaly_sample() -> bytes:
    global_header = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    sequences = (100, 103, 102, 102)
    packets = [
        _pcap_packet(
            index,
            _ethernet_ipv4_udp_rtp(
                sequence=sequence,
                timestamp=90000 + index * 3000,
                marker=index == len(sequences) - 1,
                payload=bytes([0x60 + index, 0x88, 0x84]),
            ),
        )
        for index, sequence in enumerate(sequences)
    ]
    packets.extend(
        [
            _pcap_packet(
                10 + index,
                _ethernet_ipv4_udp_rtp(
                    sequence=sequence,
                    timestamp=180000 + index * 3000,
                    marker=index == 1,
                    payload=b"\x61\x22\x33",
                    ssrc=0xABCDEF01,
                    src_port=6004,
                    dst_port=6004,
                ),
            )
            for index, sequence in enumerate((200, 201))
        ]
    )
    return global_header + b"".join(packets)


def _pcap_packet(ts_sec: int, payload: bytes) -> bytes:
    return struct.pack("<IIII", ts_sec, 0, len(payload), len(payload)) + payload


def _ethernet_ipv4_udp_rtp(
    sequence: int,
    timestamp: int,
    marker: bool,
    payload: bytes,
    ssrc: int = 0x12345678,
    src_port: int = 5004,
    dst_port: int = 5004,
) -> bytes:
    rtp = bytes([0x80, (0x80 if marker else 0x00) | 96]) + struct.pack(">HII", sequence, timestamp, ssrc) + payload
    return _ethernet_ipv4_udp(rtp, src_port=src_port, dst_port=dst_port)


def _ethernet_ipv4_udp(payload: bytes, src_port: int, dst_port: int) -> bytes:
    ethernet = b"\xAA\xBB\xCC\xDD\xEE\xFF" + b"\x11\x22\x33\x44\x55\x66" + b"\x08\x00"
    udp_length = 8 + len(payload)
    udp = struct.pack(">HHHH", src_port, dst_port, udp_length, 0)
    ip_total_length = 20 + udp_length
    ip_header = bytearray(
        b"\x45\x00"
        + struct.pack(">H", ip_total_length)
        + b"\x00\x01\x00\x00\x40\x11\x00\x00"
        + bytes([192, 168, 1, 10])
        + bytes([239, 1, 1, 1])
    )
    checksum = _ipv4_checksum(bytes(ip_header))
    ip_header[10:12] = struct.pack(">H", checksum)
    return ethernet + bytes(ip_header) + udp + payload


def _rtcp_compound_sample() -> bytes:
    source_ssrc = 0x12345678
    report_block = (
        struct.pack(">I", source_ssrc)
        + bytes([0])
        + (0).to_bytes(3, "big")
        + struct.pack(">IIII", 101, 90, 0x00010000, 0x00008000)
    )
    sender_info = struct.pack(">IIIIII", source_ssrc, 2_208_988_802, 0x80000000, 93000, 2, 6)
    sender_report = bytes([0x81, 200]) + struct.pack(">H", 12) + sender_info + report_block
    receiver_report = bytes([0x81, 201]) + struct.pack(">H", 7) + struct.pack(">I", 0x87654321) + report_block
    return sender_report + receiver_report


def _ipv4_checksum(header: bytes) -> int:
    total = 0
    for offset in range(0, len(header), 2):
        total += int.from_bytes(header[offset : offset + 2], "big")
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _pes_header(pts_90k: int) -> bytes:
    return b"\x80\x80\x05" + _encode_pts(pts_90k, prefix=0x20)


def _encode_pts(value: int, prefix: int) -> bytes:
    return bytes(
        [
            prefix | (((value >> 30) & 0x07) << 1) | 1,
            (value >> 22) & 0xFF,
            (((value >> 15) & 0x7F) << 1) | 1,
            (value >> 7) & 0xFF,
            ((value & 0x7F) << 1) | 1,
        ]
    )


def _flv_sample() -> bytes:
    header = b"FLV" + bytes([1, 0x05]) + struct.pack(">I", 9) + struct.pack(">I", 0)
    script_payload = b"\x02\x00\x0AonMetaData\x08\x00\x00\x00\x00\x00\x00\x09"
    video_payload = b"\x17\x01\x00\x00\x00\x65\x88\x84"
    return header + _flv_tag(18, 0, script_payload) + _flv_tag(9, 40, video_payload)


def _flv_tag(tag_type: int, timestamp: int, payload: bytes) -> bytes:
    data_size = len(payload)
    header = (
        bytes([tag_type])
        + data_size.to_bytes(3, "big")
        + (timestamp & 0xFFFFFF).to_bytes(3, "big")
        + bytes([(timestamp >> 24) & 0xFF])
        + b"\x00\x00\x00"
    )
    previous_tag_size = len(header) + data_size
    return header + payload + struct.pack(">I", previous_tag_size)


def _matroska_sample() -> bytes:
    ebml_header = _ebml_element(
        b"\x1A\x45\xDF\xA3",
        _ebml_uint_element(b"\x42\x86", 1)
        + _ebml_uint_element(b"\x42\xF7", 1)
        + _ebml_uint_element(b"\x42\xF2", 4)
        + _ebml_uint_element(b"\x42\xF3", 8)
        + _ebml_text_element(b"\x42\x82", "matroska")
        + _ebml_uint_element(b"\x42\x87", 4)
        + _ebml_uint_element(b"\x42\x85", 2),
    )
    info = _ebml_element(
        b"\x15\x49\xA9\x66",
        _ebml_uint_element(b"\x2A\xD7\xB1", 1_000_000)
        + _ebml_element(b"\x44\x89", struct.pack(">d", 5000.0))
        + _ebml_text_element(b"\x4D\x80", "AVScope")
        + _ebml_text_element(b"\x57\x41", "AVScope Sample"),
    )
    video_track = _ebml_element(
        b"\xAE",
        _ebml_uint_element(b"\xD7", 1)
        + _ebml_uint_element(b"\x73\xC5", 1)
        + _ebml_uint_element(b"\x83", 1)
        + _ebml_text_element(b"\x86", "V_MPEG4/ISO/AVC")
        + _ebml_element(
            b"\xE0",
            _ebml_uint_element(b"\xB0", 640) + _ebml_uint_element(b"\xBA", 360),
        ),
    )
    tracks = _ebml_element(b"\x16\x54\xAE\x6B", video_track)
    block_payload = b"\x81\x00\x00\x80\x00\x00\x01\x65\x88\x84"
    cluster = _ebml_element(
        b"\x1F\x43\xB6\x75",
        _ebml_uint_element(b"\xE7", 0) + _ebml_element(b"\xA3", block_payload),
    )
    return ebml_header + _ebml_element(b"\x18\x53\x80\x67", info + tracks + cluster)


def _ebml_element(element_id: bytes, payload: bytes) -> bytes:
    return element_id + _ebml_size(len(payload)) + payload


def _ebml_uint_element(element_id: bytes, value: int) -> bytes:
    return _ebml_element(element_id, _ebml_uint(value))


def _ebml_text_element(element_id: bytes, value: str) -> bytes:
    return _ebml_element(element_id, value.encode("utf-8"))


def _ebml_uint(value: int) -> bytes:
    size = max(1, (value.bit_length() + 7) // 8)
    return value.to_bytes(size, "big")


def _ebml_size(size: int) -> bytes:
    if size < 0x7F:
        return bytes([0x80 | size])
    if size < 0x3FFF:
        return (0x4000 | size).to_bytes(2, "big")
    if size < 0x1F_FFFF:
        return (0x20_0000 | size).to_bytes(3, "big")
    if size < 0x0FFF_FFFF:
        return (0x1000_0000 | size).to_bytes(4, "big")
    raise ValueError("synthetic EBML sample is too large")


def _ts_packet(pid: int, payload_unit_start: bool, continuity_counter: int, payload: bytes, pcr_base: int | None = None) -> bytes:
    adaptation = b""
    adaptation_field_control = 0x10
    if pcr_base is not None:
        adaptation_field_control = 0x30
        adaptation = bytes([7, 0x10]) + _encode_pcr(pcr_base)
    header = bytes(
        [
            0x47,
            (0x40 if payload_unit_start else 0x00) | ((pid >> 8) & 0x1F),
            pid & 0xFF,
            adaptation_field_control | (continuity_counter & 0x0F),
        ]
    )
    capacity = TS_PACKET_SIZE - 4 - len(adaptation)
    return header + adaptation + payload[:capacity] + b"\xFF" * max(0, capacity - len(payload))


def _encode_pcr(pcr_base: int, pcr_extension: int = 0) -> bytes:
    base = max(0, int(pcr_base)) & ((1 << 33) - 1)
    extension = max(0, int(pcr_extension)) & 0x1FF
    return bytes(
        [
            (base >> 25) & 0xFF,
            (base >> 17) & 0xFF,
            (base >> 9) & 0xFF,
            (base >> 1) & 0xFF,
            ((base & 0x01) << 7) | 0x7E | ((extension >> 8) & 0x01),
            extension & 0xFF,
        ]
    )


def make_h264_baseline_sps(
    width: int = 640,
    height: int = 480,
    profile_idc: int = 66,
    level_idc: int = 30,
    seq_parameter_set_id: int = 0,
) -> bytes:
    if width % 16 or height % 16:
        raise ValueError("synthetic SPS helper expects dimensions divisible by 16")
    writer = _BitWriter()
    writer.write_bits(profile_idc, 8)
    writer.write_bits(0, 8)
    writer.write_bits(level_idc, 8)
    writer.write_ue(seq_parameter_set_id)
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


def make_h264_pps(pic_parameter_set_id: int = 0, seq_parameter_set_id: int = 0) -> bytes:
    writer = _BitWriter()
    writer.write_ue(pic_parameter_set_id)
    writer.write_ue(seq_parameter_set_id)
    writer.write_bit(0)
    writer.write_bit(0)
    writer.write_ue(0)
    return writer.finish()


def make_h264_slice_header(pps_id: int = 0, slice_type: int = 2, first_mb: int = 0) -> bytes:
    writer = _BitWriter()
    writer.write_ue(first_mb)
    writer.write_ue(slice_type)
    writer.write_ue(pps_id)
    return writer.finish()


def make_h265_vps(profile_idc: int = 1, level_idc: int = 120, video_parameter_set_id: int = 0) -> bytes:
    writer = _BitWriter()
    writer.write_bits(video_parameter_set_id, 4)
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


def make_h265_sps(
    width: int = 640,
    height: int = 360,
    profile_idc: int = 1,
    level_idc: int = 120,
    video_parameter_set_id: int = 0,
    seq_parameter_set_id: int = 0,
) -> bytes:
    writer = _BitWriter()
    writer.write_bits(video_parameter_set_id, 4)
    writer.write_bits(0, 3)
    writer.write_bit(1)
    _write_h265_profile_tier_level(writer, profile_idc, level_idc)
    writer.write_ue(seq_parameter_set_id)
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


def make_h265_pps(pic_parameter_set_id: int = 0, seq_parameter_set_id: int = 0) -> bytes:
    writer = _BitWriter()
    writer.write_ue(pic_parameter_set_id)
    writer.write_ue(seq_parameter_set_id)
    writer.write_bit(0)
    writer.write_bit(0)
    writer.write_bits(0, 3)
    writer.write_bit(0)
    writer.write_bit(0)
    return writer.finish()


def make_h265_slice_header(pps_id: int = 0, irap: bool = True) -> bytes:
    writer = _BitWriter()
    writer.write_bit(1)
    if irap:
        writer.write_bit(0)
    writer.write_ue(pps_id)
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
