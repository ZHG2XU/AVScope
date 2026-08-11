from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, FrameInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, u16be, warn


MAX_VISIBLE_PACKS = 1000
START_CODE_PREFIX = b"\x00\x00\x01"

PACK_START_CODE = 0xBA
SYSTEM_HEADER_START_CODE = 0xBB
PROGRAM_STREAM_MAP = 0xBC
PADDING_STREAM = 0xBE
PRIVATE_STREAM_2 = 0xBF


class MpegPsParser(FormatParser):
    name = "MPEG-PS"
    extensions = (".ps", ".mpg", ".mpeg", ".vob")

    def probe(self, source: ByteSource) -> bool:
        head = source.head(32)
        if head.startswith(START_CODE_PREFIX + bytes([PACK_START_CODE])):
            return True
        return self.extension_matches(source.path) and head.startswith(START_CODE_PREFIX)

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        diagnostics = []
        frames: list[FrameInfo] = []
        counts: dict[str, int] = {}
        parsed = 0
        offset = 0
        while offset + 4 <= source.size and parsed < MAX_VISIBLE_PACKS:
            start = _find_start_code(source, offset)
            if start is None:
                if offset < source.size:
                    diagnostics.append(warn("MPEG-PS 尾部存在未解析字节", offset, self.name))
                break
            if start > offset:
                diagnostics.append(warn("MPEG-PS start code 前存在填充或未识别字节", offset, self.name))
            code = source.read_at(start + 3, 1)[0]
            name = _stream_name(code)
            counts[name] = counts.get(name, 0) + 1
            next_start = _find_start_code(source, start + 4)
            packet_end = next_start if next_start is not None else source.size
            severity = Severity.NORMAL
            description = ""
            if code == PACK_START_CODE:
                node, packet_end = self._parse_pack_header(source, root, start, packet_end, diagnostics)
            elif _has_packet_length(code):
                node, packet_end = self._parse_length_prefixed_packet(source, root, start, packet_end, diagnostics, frames)
            else:
                severity = Severity.WARNING
                description = "未知或无长度 start code"
                diagnostics.append(warn(f"MPEG-PS 未识别 start code 0x{code:02X}", start, self.name))
                node = root.add_child(ParseNode(f"StartCode 0x{code:02X}", "ps_packet", start, max(4, packet_end - start), severity=severity, description=description))
                node.fields.extend(_start_code_fields(code, start))
            parsed += 1
            offset = max(packet_end, start + 4)

        if parsed >= MAX_VISIBLE_PACKS and offset < source.size:
            diagnostics.append(warn(f"MPEG-PS packet 超过 {MAX_VISIBLE_PACKS} 个，已停止展开后续 packet", offset, self.name))
        root.fields.extend(
            [
                FieldInfo("visible_packets", parsed),
                FieldInfo("stream_count", len(counts)),
                FieldInfo("frame_count", len(frames)),
            ]
        )
        summary = {
            "visible_packets": parsed,
            "stream_counts": counts,
            "frames": len(frames),
            "video_packets": sum(count for name, count in counts.items() if name.startswith("video")),
            "audio_packets": sum(count for name, count in counts.items() if name.startswith("audio")),
        }
        return ParseResult(media_info(source, self.name, **summary), root, frames=frames, diagnostics=diagnostics)

    def _parse_pack_header(self, source: ByteSource, root: ParseNode, start: int, scan_end: int, diagnostics: list) -> tuple[ParseNode, int]:
        header = source.read_at(start, min(14, source.size - start))
        if len(header) < 14:
            diagnostics.append(error("MPEG-PS pack header 长度不足", start, self.name))
            node = root.add_child(ParseNode("Pack header", "ps_pack", start, len(header), severity=Severity.ERROR, description="pack header 长度不足"))
            node.fields.extend(_start_code_fields(PACK_START_CODE, start))
            return node, source.size
        stuffing_length = header[13] & 0x07
        packet_size = 14 + stuffing_length
        if start + packet_size > source.size:
            diagnostics.append(error("MPEG-PS pack stuffing 超出文件边界", start + 13, self.name))
            packet_size = source.size - start
        node = root.add_child(ParseNode("Pack header", "ps_pack", start, packet_size))
        node.fields.extend(_start_code_fields(PACK_START_CODE, start))
        node.fields.extend(
            [
                FieldInfo("scr_base", _scr_base(header[4:10]), start + 4, 6, header[4:10].hex(" ").upper(), description="system clock reference base"),
                FieldInfo("program_mux_rate", _mux_rate(header[10:13]), start + 10, 3, header[10:13].hex(" ").upper()),
                FieldInfo("pack_stuffing_length", stuffing_length, start + 13, 1, hex(stuffing_length), bit_offset=start * 8 + 109, bit_length=3),
            ]
        )
        return node, max(start + packet_size, min(scan_end, source.size))

    def _parse_length_prefixed_packet(
        self,
        source: ByteSource,
        root: ParseNode,
        start: int,
        scan_end: int,
        diagnostics: list,
        frames: list[FrameInfo],
    ) -> tuple[ParseNode, int]:
        header = source.read_at(start, 6)
        code = header[3]
        if len(header) < 6:
            diagnostics.append(error("MPEG-PS packet header 长度不足", start, self.name))
            node = root.add_child(ParseNode(_stream_name(code), "ps_packet", start, len(header), severity=Severity.ERROR))
            node.fields.extend(_start_code_fields(code, start))
            return node, source.size
        packet_length = u16be(header, 4)
        packet_end = scan_end if packet_length == 0 else start + 6 + packet_length
        severity = Severity.NORMAL
        description = ""
        if packet_end > source.size:
            diagnostics.append(error("MPEG-PS packet length 超出文件边界", start + 4, self.name))
            packet_end = source.size
            severity = Severity.ERROR
            description = "packet length 超出文件边界"
        node = root.add_child(ParseNode(_stream_name(code), "ps_pes" if _is_pes_stream(code) else "ps_packet", start, packet_end - start, severity=severity, description=description))
        node.fields.extend(_start_code_fields(code, start))
        node.fields.append(FieldInfo("packet_length", packet_length, start + 4, 2, hex(packet_length), description="0 means until next start code for video PES"))
        if _is_pes_stream(code):
            payload_offset, pts, dts = _parse_pes_optional_header(source, node, start, packet_end)
            frame_payload_size = max(0, packet_end - payload_offset)
            frames.append(
                FrameInfo(
                    index=len(frames),
                    offset=payload_offset,
                    size=frame_payload_size,
                    pts=pts,
                    dts=dts,
                    frame_type=_stream_name(code),
                    keyframe=0xE0 <= code <= 0xEF,
                )
            )
        return node, packet_end


def _find_start_code(source: ByteSource, offset: int) -> int | None:
    chunk_size = 64 * 1024
    search_from = max(0, offset)
    overlap = b""
    while search_from < source.size:
        data = overlap + source.read_at(search_from, chunk_size)
        if not data:
            return None
        found = data.find(START_CODE_PREFIX)
        if found >= 0:
            return search_from - len(overlap) + found
        if len(data) < chunk_size + len(overlap):
            return None
        overlap = data[-2:]
        search_from += chunk_size
    return None


def _has_packet_length(code: int) -> bool:
    return code in {SYSTEM_HEADER_START_CODE, PROGRAM_STREAM_MAP, PADDING_STREAM, PRIVATE_STREAM_2} or _is_pes_stream(code)


def _is_pes_stream(code: int) -> bool:
    return code == 0xBD or 0xC0 <= code <= 0xDF or 0xE0 <= code <= 0xEF


def _stream_name(code: int) -> str:
    if code == PACK_START_CODE:
        return "pack_header"
    if code == SYSTEM_HEADER_START_CODE:
        return "system_header"
    if code == PROGRAM_STREAM_MAP:
        return "program_stream_map"
    if code == PADDING_STREAM:
        return "padding_stream"
    if code == 0xBD:
        return "private_stream_1"
    if code == PRIVATE_STREAM_2:
        return "private_stream_2"
    if 0xC0 <= code <= 0xDF:
        return f"audio_stream[{code - 0xC0}]"
    if 0xE0 <= code <= 0xEF:
        return f"video_stream[{code - 0xE0}]"
    return f"stream_id_0x{code:02X}"


def _start_code_fields(code: int, offset: int) -> list[FieldInfo]:
    return [
        FieldInfo("start_code_prefix", "0x000001", offset, 3, "00 00 01"),
        FieldInfo("stream_id", f"0x{code:02X}", offset + 3, 1, hex(code), description=_stream_name(code)),
    ]


def _parse_pes_optional_header(source: ByteSource, node: ParseNode, start: int, packet_end: int) -> tuple[int, float | None, float | None]:
    base = start + 6
    header = source.read_at(base, min(16, max(0, packet_end - base)))
    if len(header) < 3 or (header[0] & 0xC0) != 0x80:
        node.fields.append(FieldInfo("payload_offset", base, base, 0))
        return base, None, None
    flags = header[1]
    header_data_length = header[2]
    payload_offset = min(base + 3 + header_data_length, packet_end)
    pts = None
    dts = None
    node.fields.extend(
        [
            FieldInfo("pes_flags", flags, base + 1, 1, hex(flags)),
            FieldInfo("pts_dts_flags", (flags >> 6) & 0x03, base + 1, 1, bit_offset=(base + 1) * 8, bit_length=2),
            FieldInfo("pes_header_data_length", header_data_length, base + 2, 1, hex(header_data_length)),
            FieldInfo("payload_offset", payload_offset, payload_offset, 0),
        ]
    )
    pts_dts_flags = (flags >> 6) & 0x03
    if pts_dts_flags in {2, 3} and len(header) >= 8:
        pts_value = _decode_pts(header[3:8])
        pts = pts_value / 90000
        node.fields.append(FieldInfo("pts_90k", pts_value, base + 3, 5, header[3:8].hex(" ").upper()))
        node.fields.append(FieldInfo("pts_seconds", pts, base + 3, 0))
    if pts_dts_flags == 3 and len(header) >= 13:
        dts_value = _decode_pts(header[8:13])
        dts = dts_value / 90000
        node.fields.append(FieldInfo("dts_90k", dts_value, base + 8, 5, header[8:13].hex(" ").upper()))
        node.fields.append(FieldInfo("dts_seconds", dts, base + 8, 0))
    return payload_offset, pts, dts


def _decode_pts(data: bytes) -> int:
    if len(data) < 5:
        return 0
    return ((data[0] >> 1) & 0x07) << 30 | (data[1] << 22) | ((data[2] >> 1) << 15) | (data[3] << 7) | (data[4] >> 1)


def _scr_base(data: bytes) -> int | None:
    if len(data) < 6:
        return None
    return ((data[0] >> 3) & 0x07) << 30 | ((data[0] & 0x03) << 28) | (data[1] << 20) | ((data[2] >> 3) << 15) | ((data[2] & 0x03) << 13) | (data[3] << 5) | (data[4] >> 3)


def _mux_rate(data: bytes) -> int | None:
    if len(data) < 3:
        return None
    return ((data[0] & 0x7F) << 15) | (data[1] << 7) | (data[2] >> 1)
