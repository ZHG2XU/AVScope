from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from avscope.models import DiagnosticIssue, FieldInfo, ParseNode, Severity


H264_NAL_TYPES = {
    1: "Non-IDR Slice", 5: "IDR Slice", 6: "SEI", 7: "SPS", 8: "PPS", 9: "AUD",
    24: "STAP-A", 28: "FU-A",
}
H265_NAL_TYPES = {
    0: "TRAIL_N", 1: "TRAIL_R", 19: "IDR_W_RADL", 20: "IDR_N_LP", 21: "CRA_NUT",
    32: "VPS", 33: "SPS", 34: "PPS", 35: "AUD", 39: "PREFIX_SEI", 40: "SUFFIX_SEI",
    48: "AP", 49: "FU", 50: "PACI",
}


@dataclass(slots=True)
class _Fragment:
    codec: str
    nal_type: int
    timestamp: int
    start_sequence: int
    last_sequence: int
    offset: int
    bytes: int
    packets: int = 1


@dataclass(slots=True)
class _Stream:
    key: tuple[str, int, str, int, int]
    codec: str = ""
    packets: int = 0
    payload_bytes: int = 0
    nal_units: int = 0
    single_packets: int = 0
    aggregation_packets: int = 0
    fragmentation_packets: int = 0
    completed_fragments: int = 0
    incomplete_fragments: int = 0
    issue_count: int = 0
    first_offset: int | None = None
    nal_type_counts: dict[str, int] = field(default_factory=dict)
    packetization_counts: dict[str, int] = field(default_factory=dict)
    fragment: _Fragment | None = None

    def count_type(self, name: str) -> None:
        self.nal_type_counts[name] = self.nal_type_counts.get(name, 0) + 1


class RtpVideoPayloadAnalyzer:
    """Inspect RFC 6184/7798 payloads without retaining payload bodies."""

    def __init__(self, payload_map: dict[int, str] | None = None) -> None:
        self._streams: dict[tuple[str, int, str, int, int], _Stream] = {}
        self._payload_map = {int(key): str(value).lower() for key, value in (payload_map or {}).items()}
        self._diagnostics: list[DiagnosticIssue] = []
        self._issues: list[dict[str, Any]] = []

    def add_packet(self, packet: dict[str, Any], payload: bytes, rtp_node: ParseNode) -> dict[str, Any]:
        key = _stream_key(packet)
        stream = self._streams.get(key) or _Stream(key)
        codec = self._detect_codec(stream, int(packet.get("payload_type", 0)), payload)
        if not codec:
            return {"available": False}
        self._streams.setdefault(key, stream)
        if stream.codec and stream.codec != codec:
            self._issue(stream, f"RTP 视频负载编码从 {stream.codec} 切换为 {codec}", int(packet["payload_offset"]))
        stream.codec = codec
        stream.packets += 1
        stream.payload_bytes += len(payload)
        stream.first_offset = int(packet["payload_offset"]) if stream.first_offset is None else stream.first_offset
        issues_before = stream.issue_count

        if stream.fragment and int(packet["timestamp"]) != stream.fragment.timestamp:
            self._close_incomplete(stream, "RTP timestamp 已切换但上一分片未结束", stream.fragment.offset)

        if codec == "H.264":
            result = self._parse_h264(stream, packet, payload, rtp_node)
        else:
            result = self._parse_h265(stream, packet, payload, rtp_node)
        if stream.issue_count > issues_before:
            result["status"] = "warning"
            rtp_node.severity = Severity.WARNING
            rtp_node.description = self._issues[-1]["message"]
        stream.packetization_counts[result["packetization"]] = stream.packetization_counts.get(result["packetization"], 0) + 1
        return {"available": True, "codec": codec, **result}

    def finalize(self) -> tuple[dict[str, Any], list[DiagnosticIssue]]:
        for stream in self._streams.values():
            if stream.fragment:
                self._close_incomplete(stream, "PCAP 结束时 RTP 视频分片仍未完成", stream.fragment.offset)
        rows = []
        for index, stream in enumerate(self._streams.values()):
            source_ip, source_port, destination_ip, destination_port, ssrc = stream.key
            endpoint = f"{source_ip}:{source_port} -> {destination_ip}:{destination_port}"
            rows.append(
                {
                    "index": index,
                    "endpoint": endpoint,
                    "ssrc": f"0x{ssrc:08X}",
                    "codec": stream.codec,
                    "packets": stream.packets,
                    "payload_bytes": stream.payload_bytes,
                    "nal_units": stream.nal_units,
                    "single_packets": stream.single_packets,
                    "aggregation_packets": stream.aggregation_packets,
                    "fragmentation_packets": stream.fragmentation_packets,
                    "completed_fragments": stream.completed_fragments,
                    "incomplete_fragments": stream.incomplete_fragments,
                    "issue_count": stream.issue_count,
                    "first_offset": int(stream.first_offset or 0),
                    "nal_type_counts": dict(sorted(stream.nal_type_counts.items())),
                    "packetization_counts": dict(sorted(stream.packetization_counts.items())),
                    "status": "warning" if stream.issue_count else "normal",
                }
            )
        summary = {
            "available": bool(rows),
            "streams": rows,
            "stream_count": len(rows),
            "warning_streams": sum(row["status"] == "warning" for row in rows),
            "packets": sum(row["packets"] for row in rows),
            "payload_bytes": sum(row["payload_bytes"] for row in rows),
            "nal_units": sum(row["nal_units"] for row in rows),
            "completed_fragments": sum(row["completed_fragments"] for row in rows),
            "incomplete_fragments": sum(row["incomplete_fragments"] for row in rows),
            "issue_count": len(self._issues),
            "issues": list(self._issues),
            "codecs": sorted({row["codec"] for row in rows if row["codec"]}),
        }
        return summary, list(self._diagnostics)

    def _detect_codec(self, stream: _Stream, payload_type: int, payload: bytes) -> str:
        mapped = self._payload_map.get(payload_type, "")
        if mapped in {"h264", "avc"}:
            return "H.264"
        if mapped in {"h265", "hevc"}:
            return "H.265"
        if stream.codec:
            return stream.codec
        if not payload:
            return ""
        h264_type = payload[0] & 0x1F
        if h264_type in {24, 28}:
            return "H.264"
        if len(payload) >= 2:
            h265_type = (payload[0] >> 1) & 0x3F
            temporal_id_plus1 = payload[1] & 0x07
            if h265_type == 48 and temporal_id_plus1 and _valid_h265_ap(payload):
                return "H.265"
            if h265_type in {49, 50} and temporal_id_plus1 and len(payload) >= 3:
                return "H.265"
            h265_valid = h265_type <= 47 and temporal_id_plus1 != 0
        else:
            h265_valid = False
        h264_valid = 1 <= h264_type <= 23
        if h264_valid and not h265_valid:
            return "H.264"
        if h265_valid and not h264_valid:
            return "H.265"
        if h264_type in {5, 7, 8, 9}:
            return "H.264"
        return ""

    def _parse_h264(self, stream: _Stream, packet: dict[str, Any], payload: bytes, parent: ParseNode) -> dict[str, Any]:
        offset = int(packet["payload_offset"])
        nal_type = payload[0] & 0x1F
        if 1 <= nal_type <= 23:
            name = H264_NAL_TYPES.get(nal_type, f"NAL type {nal_type}")
            self._add_nal_node(parent, "H.264", name, nal_type, offset, len(payload), payload[0])
            stream.single_packets += 1
            stream.nal_units += 1
            stream.count_type(name)
            return {"packetization": "Single NALU", "nal_types": [name], "nal_units": 1, "status": "normal"}
        if nal_type == 24:
            names, count, malformed = self._parse_h264_stap(stream, payload, parent, offset)
            stream.aggregation_packets += 1
            return {"packetization": "STAP-A", "nal_types": names, "nal_units": count, "status": "warning" if malformed else "normal"}
        if nal_type == 28:
            return self._parse_h264_fu(stream, packet, payload, parent, offset)
        self._issue(stream, f"不支持的 H.264 RTP packetization NAL type={nal_type}", offset)
        return {"packetization": f"NAL type {nal_type}", "nal_types": [], "nal_units": 0, "status": "warning"}

    def _parse_h264_stap(self, stream: _Stream, payload: bytes, parent: ParseNode, offset: int) -> tuple[list[str], int, bool]:
        node = parent.add_child(ParseNode("H.264 STAP-A", "rtp_h264_stap", offset, len(payload)))
        node.fields.append(FieldInfo("packetization_type", 24, offset, 1, _hex(payload[:1])))
        cursor = 1
        names: list[str] = []
        malformed = False
        while cursor < len(payload):
            if cursor + 2 > len(payload):
                malformed = True
                self._issue(stream, "H.264 STAP-A NALU 长度字段截断", offset + cursor)
                break
            size = int.from_bytes(payload[cursor:cursor + 2], "big")
            size_offset = offset + cursor
            cursor += 2
            if size <= 0 or cursor + size > len(payload):
                malformed = True
                self._issue(stream, f"H.264 STAP-A NALU 长度越界: size={size}", size_offset)
                break
            nal_type = payload[cursor] & 0x1F
            name = H264_NAL_TYPES.get(nal_type, f"NAL type {nal_type}")
            child = node.add_child(ParseNode(name, "rtp_h264_nalu", offset + cursor, size))
            child.fields.extend([FieldInfo("nal_unit_size", size, size_offset, 2, _hex(payload[cursor - 2:cursor])), FieldInfo("nal_unit_type", nal_type, offset + cursor, 1, _hex(payload[cursor:cursor + 1]))])
            names.append(name)
            stream.nal_units += 1
            stream.count_type(name)
            cursor += size
        if malformed:
            node.severity = Severity.WARNING
        return names, len(names), malformed

    def _parse_h264_fu(self, stream: _Stream, packet: dict[str, Any], payload: bytes, parent: ParseNode, offset: int) -> dict[str, Any]:
        stream.fragmentation_packets += 1
        if len(payload) < 2:
            self._issue(stream, "H.264 FU-A header 截断", offset)
            return {"packetization": "FU-A", "nal_types": [], "nal_units": 0, "status": "warning"}
        header = payload[1]
        start, end, reserved, nal_type = bool(header & 0x80), bool(header & 0x40), bool(header & 0x20), header & 0x1F
        name = H264_NAL_TYPES.get(nal_type, f"NAL type {nal_type}")
        node = parent.add_child(ParseNode(f"H.264 FU-A {name}", "rtp_h264_fu", offset, len(payload)))
        node.fields.extend([
            FieldInfo("fu_start", start, offset + 1, 1, _hex(payload[1:2]), bit_offset=(offset + 1) * 8, bit_length=1),
            FieldInfo("fu_end", end, offset + 1, 1, _hex(payload[1:2]), bit_offset=(offset + 1) * 8 + 1, bit_length=1),
            FieldInfo("fu_reserved", reserved, offset + 1, 1, _hex(payload[1:2]), bit_offset=(offset + 1) * 8 + 2, bit_length=1),
            FieldInfo("nal_unit_type", nal_type, offset + 1, 1, _hex(payload[1:2]), bit_offset=(offset + 1) * 8 + 3, bit_length=5),
        ])
        warning = reserved or (start and end)
        if reserved:
            self._issue(stream, "H.264 FU-A reserved bit 不为 0", offset + 1)
        completed = self._consume_fragment(stream, packet, "H.264", nal_type, name, start, end, offset, len(payload) - 2)
        if stream.issue_count and node.severity == Severity.NORMAL and warning:
            node.severity = Severity.WARNING
        return {"packetization": "FU-A", "nal_types": [name], "nal_units": int(completed), "fragment_start": start, "fragment_end": end, "status": "warning" if warning else "normal"}

    def _parse_h265(self, stream: _Stream, packet: dict[str, Any], payload: bytes, parent: ParseNode) -> dict[str, Any]:
        offset = int(packet["payload_offset"])
        if len(payload) < 2:
            self._issue(stream, "H.265 RTP payload header 截断", offset)
            return {"packetization": "truncated", "nal_types": [], "nal_units": 0, "status": "warning"}
        nal_type = (payload[0] >> 1) & 0x3F
        if nal_type <= 47:
            name = H265_NAL_TYPES.get(nal_type, f"NAL type {nal_type}")
            self._add_nal_node(parent, "H.265", name, nal_type, offset, len(payload), int.from_bytes(payload[:2], "big"))
            stream.single_packets += 1
            stream.nal_units += 1
            stream.count_type(name)
            return {"packetization": "Single NALU", "nal_types": [name], "nal_units": 1, "status": "normal"}
        if nal_type == 48:
            names, count, malformed = self._parse_h265_ap(stream, payload, parent, offset)
            stream.aggregation_packets += 1
            return {"packetization": "AP", "nal_types": names, "nal_units": count, "status": "warning" if malformed else "normal"}
        if nal_type == 49:
            return self._parse_h265_fu(stream, packet, payload, parent, offset)
        self._issue(stream, f"不支持的 H.265 RTP packetization NAL type={nal_type}", offset)
        return {"packetization": H265_NAL_TYPES.get(nal_type, str(nal_type)), "nal_types": [], "nal_units": 0, "status": "warning"}

    def _parse_h265_ap(self, stream: _Stream, payload: bytes, parent: ParseNode, offset: int) -> tuple[list[str], int, bool]:
        node = parent.add_child(ParseNode("H.265 AP", "rtp_h265_ap", offset, len(payload)))
        node.fields.append(FieldInfo("packetization_type", 48, offset, 2, _hex(payload[:2])))
        cursor = 2
        names: list[str] = []
        malformed = False
        while cursor < len(payload):
            if cursor + 2 > len(payload):
                malformed = True
                self._issue(stream, "H.265 AP NALU 长度字段截断", offset + cursor)
                break
            size = int.from_bytes(payload[cursor:cursor + 2], "big")
            size_offset = offset + cursor
            cursor += 2
            if size < 2 or cursor + size > len(payload):
                malformed = True
                self._issue(stream, f"H.265 AP NALU 长度越界: size={size}", size_offset)
                break
            nal_type = (payload[cursor] >> 1) & 0x3F
            name = H265_NAL_TYPES.get(nal_type, f"NAL type {nal_type}")
            child = node.add_child(ParseNode(name, "rtp_h265_nalu", offset + cursor, size))
            child.fields.extend([FieldInfo("nal_unit_size", size, size_offset, 2, _hex(payload[cursor - 2:cursor])), FieldInfo("nal_unit_type", nal_type, offset + cursor, 2, _hex(payload[cursor:cursor + 2]))])
            names.append(name)
            stream.nal_units += 1
            stream.count_type(name)
            cursor += size
        if malformed:
            node.severity = Severity.WARNING
        return names, len(names), malformed

    def _parse_h265_fu(self, stream: _Stream, packet: dict[str, Any], payload: bytes, parent: ParseNode, offset: int) -> dict[str, Any]:
        stream.fragmentation_packets += 1
        if len(payload) < 3:
            self._issue(stream, "H.265 FU header 截断", offset)
            return {"packetization": "FU", "nal_types": [], "nal_units": 0, "status": "warning"}
        header = payload[2]
        start, end, nal_type = bool(header & 0x80), bool(header & 0x40), header & 0x3F
        name = H265_NAL_TYPES.get(nal_type, f"NAL type {nal_type}")
        node = parent.add_child(ParseNode(f"H.265 FU {name}", "rtp_h265_fu", offset, len(payload)))
        node.fields.extend([
            FieldInfo("fu_start", start, offset + 2, 1, _hex(payload[2:3]), bit_offset=(offset + 2) * 8, bit_length=1),
            FieldInfo("fu_end", end, offset + 2, 1, _hex(payload[2:3]), bit_offset=(offset + 2) * 8 + 1, bit_length=1),
            FieldInfo("fu_type", nal_type, offset + 2, 1, _hex(payload[2:3]), bit_offset=(offset + 2) * 8 + 2, bit_length=6),
        ])
        warning = start and end
        if warning:
            self._issue(stream, "H.265 FU 同时设置 Start/End", offset + 2)
        completed = self._consume_fragment(stream, packet, "H.265", nal_type, name, start, end, offset, len(payload) - 3)
        return {"packetization": "FU", "nal_types": [name], "nal_units": int(completed), "fragment_start": start, "fragment_end": end, "status": "warning" if warning else "normal"}

    def _consume_fragment(self, stream: _Stream, packet: dict[str, Any], codec: str, nal_type: int, name: str, start: bool, end: bool, offset: int, body_size: int) -> bool:
        sequence = int(packet["sequence"])
        timestamp = int(packet["timestamp"])
        if start:
            if stream.fragment:
                self._close_incomplete(stream, f"收到新的 {codec} 分片起始包，上一 NALU 未结束", stream.fragment.offset)
            stream.fragment = _Fragment(codec, nal_type, timestamp, sequence, sequence, offset, body_size)
            if end:
                self._close_incomplete(stream, f"{codec} 分片不能同时为起始和结束", offset)
            return False
        fragment = stream.fragment
        if fragment is None:
            self._issue(stream, f"{codec} {name} 分片缺少起始包", offset)
            stream.incomplete_fragments += 1
            return False
        expected = (fragment.last_sequence + 1) & 0xFFFF
        if sequence != expected:
            self._close_incomplete(stream, f"{codec} {name} 分片序号不连续: expected={expected} current={sequence}", offset)
            return False
        if fragment.nal_type != nal_type or fragment.timestamp != timestamp:
            self._close_incomplete(stream, f"{codec} 分片 NAL type 或 timestamp 不一致", offset)
            return False
        fragment.last_sequence = sequence
        fragment.bytes += body_size
        fragment.packets += 1
        if end:
            stream.completed_fragments += 1
            stream.nal_units += 1
            stream.count_type(name)
            stream.fragment = None
            return True
        return False

    def _close_incomplete(self, stream: _Stream, message: str, offset: int) -> None:
        self._issue(stream, message, offset)
        stream.incomplete_fragments += 1
        stream.fragment = None

    def _add_nal_node(self, parent: ParseNode, codec: str, name: str, nal_type: int, offset: int, size: int, header: int) -> None:
        node_type = "rtp_h264_nalu" if codec == "H.264" else "rtp_h265_nalu"
        node = parent.add_child(ParseNode(f"{codec} {name}", node_type, offset, size))
        node.fields.extend([FieldInfo("codec", codec, offset, 0), FieldInfo("nal_unit_type", nal_type, offset, 1 if codec == "H.264" else 2, f"0x{header:X}"), FieldInfo("nal_unit_name", name, offset, 0), FieldInfo("payload_size", size, offset, size)])

    def _issue(self, stream: _Stream, message: str, offset: int) -> None:
        stream.issue_count += 1
        issue = {"severity": "warning", "source": "rtp_video", "message": message, "offset": offset}
        self._issues.append(issue)
        self._diagnostics.append(DiagnosticIssue(Severity.WARNING, message, offset, "rtp_video"))


def _stream_key(packet: dict[str, Any]) -> tuple[str, int, str, int, int]:
    return (
        str(packet.get("source_ip", "")), int(packet.get("source_port", 0)),
        str(packet.get("destination_ip", "")), int(packet.get("destination_port", 0)),
        int(packet.get("ssrc", 0)),
    )


def _hex(data: bytes) -> str:
    return data.hex(" ").upper()


def _valid_h265_ap(payload: bytes) -> bool:
    cursor = 2
    units = 0
    while cursor < len(payload):
        if cursor + 2 > len(payload):
            return False
        size = int.from_bytes(payload[cursor:cursor + 2], "big")
        cursor += 2
        if size < 2 or cursor + size > len(payload):
            return False
        cursor += size
        units += 1
    return units > 0 and cursor == len(payload)
