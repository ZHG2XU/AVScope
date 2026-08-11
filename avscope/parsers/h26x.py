from __future__ import annotations

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
            if keyframe and not self._has_required_parameter_sets(seen_parameter_sets):
                node.severity = Severity.WARNING
                diagnostics.append(warn("关键帧前缺少参数集", start_offset, self.name))
            frames.append(FrameInfo(index, start_offset, code_len + nalu_size, frame_type=type_name, keyframe=keyframe))

        diagnostics.extend(self._parameter_set_warnings(seen_parameter_sets))
        summary = {"nalu_count": len(starts), "parsed_nalu": len(root.children)}
        return ParseResult(media_info(source, self.name, **summary), root, frames, diagnostics)

    def _find_start_codes(self, source: ByteSource) -> list[tuple[int, int]]:
        starts: list[tuple[int, int]] = []
        overlap = b""
        absolute = 0
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
            absolute = chunk_offset + len(chunk)
            if len(starts) > 20000:
                break
        return [(o, l) for o, l in starts if o >= 0 and o < source.size]

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
