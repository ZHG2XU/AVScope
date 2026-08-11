from __future__ import annotations

from dataclasses import dataclass

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, FrameInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import media_info, root_node, warn


H264_TYPES = {
    1: "Non-IDR Slice",
    5: "IDR Slice",
    6: "SEI",
    7: "SPS",
    8: "PPS",
    9: "AUD",
}

H265_TYPES = {
    32: "VPS",
    33: "SPS",
    34: "PPS",
    35: "AUD",
    39: "SEI Prefix",
    40: "SEI Suffix",
}

H264_EXTENDED_PROFILES = {100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135}


@dataclass(slots=True)
class H264SpsInfo:
    profile_idc: int
    level_idc: int
    seq_parameter_set_id: int
    chroma_format_idc: int
    pic_width_in_mbs_minus1: int
    pic_height_in_map_units_minus1: int
    frame_mbs_only_flag: int
    frame_crop_left_offset: int
    frame_crop_right_offset: int
    frame_crop_top_offset: int
    frame_crop_bottom_offset: int
    width: int
    height: int


class BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.bit_pos = 0

    def read_bit(self) -> int:
        if self.bit_pos >= len(self.data) * 8:
            raise ValueError("bitstream ended unexpectedly")
        byte = self.data[self.bit_pos // 8]
        shift = 7 - (self.bit_pos % 8)
        self.bit_pos += 1
        return (byte >> shift) & 1

    def read_bits(self, count: int) -> int:
        value = 0
        for _ in range(count):
            value = (value << 1) | self.read_bit()
        return value

    def read_ue(self) -> int:
        zeros = 0
        while self.read_bit() == 0:
            zeros += 1
            if zeros > 31:
                raise ValueError("Exp-Golomb code is too large")
        if zeros == 0:
            return 0
        return (1 << zeros) - 1 + self.read_bits(zeros)

    def read_se(self) -> int:
        code_num = self.read_ue()
        value = (code_num + 1) // 2
        return -value if code_num % 2 == 0 else value


class _AnnexBParser(FormatParser):
    codec_name = "H.26x Annex-B"
    nal_types: dict[int, str] = {}

    def probe(self, source: ByteSource) -> bool:
        head = source.head(1024 * 1024)
        return b"\x00\x00\x01" in head or b"\x00\x00\x00\x01" in head

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        diagnostics = []
        frames: list[FrameInfo] = []
        starts = self._find_start_codes(source)
        if not starts:
            diagnostics.append(warn("未发现 Annex-B 起始码", 0, self.name))
            return ParseResult(media_info(source, self.name, nalu_count=0), root, diagnostics=diagnostics)

        seen_parameter_sets: set[int] = set()
        summary: dict = {"nalu_count": len(starts)}
        for index, (start_offset, code_len) in enumerate(starts[:20000]):
            payload_offset = start_offset + code_len
            next_start = starts[index + 1][0] if index + 1 < len(starts) else source.size
            nalu_size = max(0, next_start - payload_offset)
            header = source.read_at(payload_offset, 2)
            if not header:
                continue
            nal_type = self._nal_type(header)
            type_name = self.nal_types.get(nal_type, f"NAL type {nal_type}")
            if type_name in {"SPS", "PPS", "VPS"}:
                seen_parameter_sets.add(nal_type)
            keyframe = type_name == "IDR Slice" or nal_type in {19, 20}
            node = root.add_child(ParseNode(f"NALU[{index}] {type_name}", "nalu", start_offset, code_len + nalu_size))
            node.fields.extend(
                [
                    FieldInfo("start_code", "00 00 01" if code_len == 3 else "00 00 00 01", start_offset, code_len),
                    FieldInfo("nal_unit_type", nal_type, payload_offset, 1),
                    FieldInfo("payload_size", nalu_size, payload_offset, nalu_size),
                ]
            )
            self._parse_nalu_payload(source, node, nal_type, payload_offset, nalu_size, summary, diagnostics)
            if keyframe and not self._has_required_parameter_sets(seen_parameter_sets):
                node.severity = Severity.WARNING
                diagnostics.append(warn("关键帧前缺少参数集", start_offset, self.name))
            frames.append(FrameInfo(index, start_offset, code_len + nalu_size, frame_type=type_name, keyframe=keyframe))

        diagnostics.extend(self._parameter_set_warnings(seen_parameter_sets))
        summary["parsed_nalu"] = len(root.children)
        return ParseResult(media_info(source, self.name, **summary), root, frames, diagnostics)

    def _find_start_codes(self, source: ByteSource) -> list[tuple[int, int]]:
        starts: list[tuple[int, int]] = []
        overlap = b""
        for chunk_offset, chunk in source.iter_chunks(1024 * 1024):
            data = overlap + chunk
            base = chunk_offset - len(overlap)
            i = 0
            limit = len(data) - 3
            while i < limit:
                if data[i : i + 4] == b"\x00\x00\x00\x01":
                    starts.append((base + i, 4))
                    i += 4
                elif data[i : i + 3] == b"\x00\x00\x01":
                    starts.append((base + i, 3))
                    i += 3
                else:
                    i += 1
            overlap = data[-4:]
            if len(starts) > 20000:
                break
        return [(offset, length) for offset, length in starts if 0 <= offset < source.size]

    def _parse_nalu_payload(self, source: ByteSource, node: ParseNode, nal_type: int, payload_offset: int, nalu_size: int, summary: dict, diagnostics: list) -> None:
        return None

    def _nal_type(self, header: bytes) -> int:
        raise NotImplementedError

    def _has_required_parameter_sets(self, seen: set[int]) -> bool:
        raise NotImplementedError

    def _parameter_set_warnings(self, seen: set[int]):
        raise NotImplementedError


class H264AnnexBParser(_AnnexBParser):
    name = "H.264 Annex-B"
    extensions = (".h264", ".264")
    nal_types = H264_TYPES

    def _nal_type(self, header: bytes) -> int:
        return header[0] & 0x1F

    def _parse_nalu_payload(self, source: ByteSource, node: ParseNode, nal_type: int, payload_offset: int, nalu_size: int, summary: dict, diagnostics: list) -> None:
        if nal_type != 7 or nalu_size <= 1:
            return
        payload = source.read_at(payload_offset + 1, min(nalu_size - 1, 4096))
        try:
            sps = parse_h264_sps(payload)
        except ValueError as exc:
            node.severity = Severity.WARNING
            diagnostics.append(warn(f"H.264 SPS 解析失败: {exc}", payload_offset, self.name))
            return
        node.fields.extend(
            [
                FieldInfo("profile_idc", sps.profile_idc, payload_offset + 1, 1, hex(sps.profile_idc), description="H.264 profile"),
                FieldInfo("level_idc", sps.level_idc, payload_offset + 3, 1, hex(sps.level_idc), description="H.264 level"),
                FieldInfo("seq_parameter_set_id", sps.seq_parameter_set_id, payload_offset + 4, 0),
                FieldInfo("chroma_format_idc", sps.chroma_format_idc, payload_offset + 4, 0),
                FieldInfo("pic_width_in_mbs_minus1", sps.pic_width_in_mbs_minus1, payload_offset + 4, 0),
                FieldInfo("pic_height_in_map_units_minus1", sps.pic_height_in_map_units_minus1, payload_offset + 4, 0),
                FieldInfo("frame_mbs_only_flag", sps.frame_mbs_only_flag, payload_offset + 4, 0),
                FieldInfo("derived_width", sps.width, payload_offset + 4, 0, description="由 SPS 推导的亮度宽度"),
                FieldInfo("derived_height", sps.height, payload_offset + 4, 0, description="由 SPS 推导的亮度高度"),
            ]
        )
        summary["width"] = sps.width
        summary["height"] = sps.height
        summary["profile_idc"] = sps.profile_idc
        summary["level_idc"] = sps.level_idc

    def _has_required_parameter_sets(self, seen: set[int]) -> bool:
        return 7 in seen and 8 in seen

    def _parameter_set_warnings(self, seen: set[int]):
        issues = []
        if 7 not in seen:
            issues.append(warn("未发现 H.264 SPS", 0, self.name))
        if 8 not in seen:
            issues.append(warn("未发现 H.264 PPS", 0, self.name))
        return issues


class H265AnnexBParser(_AnnexBParser):
    name = "H.265 Annex-B"
    extensions = (".h265", ".265", ".hevc")
    nal_types = H265_TYPES

    def _nal_type(self, header: bytes) -> int:
        return (header[0] >> 1) & 0x3F

    def _has_required_parameter_sets(self, seen: set[int]) -> bool:
        return 32 in seen and 33 in seen and 34 in seen

    def _parameter_set_warnings(self, seen: set[int]):
        issues = []
        if 32 not in seen:
            issues.append(warn("未发现 H.265 VPS", 0, self.name))
        if 33 not in seen:
            issues.append(warn("未发现 H.265 SPS", 0, self.name))
        if 34 not in seen:
            issues.append(warn("未发现 H.265 PPS", 0, self.name))
        return issues


def parse_h264_sps(payload: bytes) -> H264SpsInfo:
    rbsp = remove_emulation_prevention_bytes(payload)
    reader = BitReader(rbsp)
    profile_idc = reader.read_bits(8)
    reader.read_bits(8)
    level_idc = reader.read_bits(8)
    seq_parameter_set_id = reader.read_ue()
    chroma_format_idc = 1
    separate_colour_plane_flag = 0
    if profile_idc in H264_EXTENDED_PROFILES:
        chroma_format_idc = reader.read_ue()
        if chroma_format_idc == 3:
            separate_colour_plane_flag = reader.read_bit()
        reader.read_ue()
        reader.read_ue()
        reader.read_bit()
        seq_scaling_matrix_present_flag = reader.read_bit()
        if seq_scaling_matrix_present_flag:
            count = 8 if chroma_format_idc != 3 else 12
            for index in range(count):
                if reader.read_bit():
                    _skip_scaling_list(reader, 16 if index < 6 else 64)
    reader.read_ue()
    pic_order_cnt_type = reader.read_ue()
    if pic_order_cnt_type == 0:
        reader.read_ue()
    elif pic_order_cnt_type == 1:
        reader.read_bit()
        reader.read_se()
        reader.read_se()
        for _ in range(reader.read_ue()):
            reader.read_se()
    reader.read_ue()
    reader.read_bit()
    pic_width_in_mbs_minus1 = reader.read_ue()
    pic_height_in_map_units_minus1 = reader.read_ue()
    frame_mbs_only_flag = reader.read_bit()
    if not frame_mbs_only_flag:
        reader.read_bit()
    reader.read_bit()
    frame_crop_left_offset = 0
    frame_crop_right_offset = 0
    frame_crop_top_offset = 0
    frame_crop_bottom_offset = 0
    if reader.read_bit():
        frame_crop_left_offset = reader.read_ue()
        frame_crop_right_offset = reader.read_ue()
        frame_crop_top_offset = reader.read_ue()
        frame_crop_bottom_offset = reader.read_ue()

    width, height = _derive_h264_dimensions(
        chroma_format_idc,
        separate_colour_plane_flag,
        pic_width_in_mbs_minus1,
        pic_height_in_map_units_minus1,
        frame_mbs_only_flag,
        frame_crop_left_offset,
        frame_crop_right_offset,
        frame_crop_top_offset,
        frame_crop_bottom_offset,
    )
    return H264SpsInfo(
        profile_idc=profile_idc,
        level_idc=level_idc,
        seq_parameter_set_id=seq_parameter_set_id,
        chroma_format_idc=chroma_format_idc,
        pic_width_in_mbs_minus1=pic_width_in_mbs_minus1,
        pic_height_in_map_units_minus1=pic_height_in_map_units_minus1,
        frame_mbs_only_flag=frame_mbs_only_flag,
        frame_crop_left_offset=frame_crop_left_offset,
        frame_crop_right_offset=frame_crop_right_offset,
        frame_crop_top_offset=frame_crop_top_offset,
        frame_crop_bottom_offset=frame_crop_bottom_offset,
        width=width,
        height=height,
    )


def remove_emulation_prevention_bytes(payload: bytes) -> bytes:
    output = bytearray()
    zeros = 0
    for byte in payload:
        if zeros >= 2 and byte == 0x03:
            zeros = 0
            continue
        output.append(byte)
        zeros = zeros + 1 if byte == 0 else 0
    return bytes(output)


def _derive_h264_dimensions(
    chroma_format_idc: int,
    separate_colour_plane_flag: int,
    pic_width_in_mbs_minus1: int,
    pic_height_in_map_units_minus1: int,
    frame_mbs_only_flag: int,
    frame_crop_left_offset: int,
    frame_crop_right_offset: int,
    frame_crop_top_offset: int,
    frame_crop_bottom_offset: int,
) -> tuple[int, int]:
    width = (pic_width_in_mbs_minus1 + 1) * 16
    height = (2 - frame_mbs_only_flag) * (pic_height_in_map_units_minus1 + 1) * 16
    if chroma_format_idc == 0 or separate_colour_plane_flag:
        crop_unit_x = 1
        crop_unit_y = 2 - frame_mbs_only_flag
    elif chroma_format_idc == 1:
        crop_unit_x = 2
        crop_unit_y = 2 * (2 - frame_mbs_only_flag)
    elif chroma_format_idc == 2:
        crop_unit_x = 2
        crop_unit_y = 2 - frame_mbs_only_flag
    else:
        crop_unit_x = 1
        crop_unit_y = 2 - frame_mbs_only_flag
    width -= (frame_crop_left_offset + frame_crop_right_offset) * crop_unit_x
    height -= (frame_crop_top_offset + frame_crop_bottom_offset) * crop_unit_y
    return width, height


def _skip_scaling_list(reader: BitReader, size: int) -> None:
    last_scale = 8
    next_scale = 8
    for _ in range(size):
        if next_scale != 0:
            delta_scale = reader.read_se()
            next_scale = (last_scale + delta_scale + 256) % 256
        last_scale = last_scale if next_scale == 0 else next_scale
