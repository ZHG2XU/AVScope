from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, FrameInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, warn


MAX_VISIBLE_ELEMENTS = 2000
DEFAULT_TIMECODE_SCALE = 1_000_000

ELEMENTS: dict[int, tuple[str, str]] = {
    0x1A45DFA3: ("EBML", "master"),
    0x4286: ("EBMLVersion", "uint"),
    0x42F7: ("EBMLReadVersion", "uint"),
    0x42F2: ("EBMLMaxIDLength", "uint"),
    0x42F3: ("EBMLMaxSizeLength", "uint"),
    0x4282: ("DocType", "string"),
    0x4287: ("DocTypeVersion", "uint"),
    0x4285: ("DocTypeReadVersion", "uint"),
    0x18538067: ("Segment", "master"),
    0x1549A966: ("Info", "master"),
    0x2AD7B1: ("TimecodeScale", "uint"),
    0x4489: ("Duration", "float"),
    0x4D80: ("MuxingApp", "utf8"),
    0x5741: ("WritingApp", "utf8"),
    0x1654AE6B: ("Tracks", "master"),
    0xAE: ("TrackEntry", "master"),
    0xD7: ("TrackNumber", "uint"),
    0x73C5: ("TrackUID", "uint"),
    0x83: ("TrackType", "uint"),
    0x86: ("CodecID", "string"),
    0x536E: ("Name", "utf8"),
    0x22B59C: ("Language", "string"),
    0xE0: ("Video", "master"),
    0xB0: ("PixelWidth", "uint"),
    0xBA: ("PixelHeight", "uint"),
    0xE1: ("Audio", "master"),
    0xB5: ("SamplingFrequency", "float"),
    0x9F: ("Channels", "uint"),
    0x6264: ("BitDepth", "uint"),
    0x1F43B675: ("Cluster", "master"),
    0xE7: ("Timecode", "uint"),
    0xA3: ("SimpleBlock", "binary"),
    0xA0: ("BlockGroup", "master"),
    0xA1: ("Block", "binary"),
    0x1C53BB6B: ("Cues", "master"),
    0x1254C367: ("Tags", "master"),
    0x1043A770: ("Chapters", "master"),
    0x1941A469: ("Attachments", "master"),
}

TRACK_TYPES = {
    1: "video",
    2: "audio",
    17: "subtitle",
}


@dataclass(slots=True)
class VInt:
    value: int
    length: int
    raw: bytes
    unknown: bool = False


class MatroskaParser(FormatParser):
    name = "Matroska/WebM"
    extensions = (".mkv", ".webm")

    def probe(self, source: ByteSource) -> bool:
        return source.head(4) == b"\x1A\x45\xDF\xA3"

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        diagnostics = []
        frames: list[FrameInfo] = []
        context: dict[str, Any] = {"timecode_scale": DEFAULT_TIMECODE_SCALE, "cluster_timecode": 0}
        stats = {"elements": 0}
        self._parse_elements(source, root, 0, source.size, diagnostics, frames, context, stats, 0)
        summary = self._summary(root, context, len(frames), stats["elements"])
        root.fields.extend(
            [
                FieldInfo("doc_type", summary.get("doc_type", ""), description="EBML DocType"),
                FieldInfo("timecode_scale", summary.get("timecode_scale", DEFAULT_TIMECODE_SCALE), description="nanoseconds per timecode unit"),
                FieldInfo("duration_seconds", summary.get("duration_seconds"), description="Duration * TimecodeScale / 1e9"),
                FieldInfo("tracks", len(summary.get("tracks", []))),
                FieldInfo("visible_elements", stats["elements"]),
            ]
        )
        return ParseResult(media_info(source, self.name, **summary), root, frames=frames, diagnostics=diagnostics)

    def _parse_elements(
        self,
        source: ByteSource,
        parent: ParseNode,
        start: int,
        end: int,
        diagnostics: list,
        frames: list[FrameInfo],
        context: dict[str, Any],
        stats: dict[str, int],
        depth: int,
    ) -> None:
        if depth > 12:
            diagnostics.append(warn("Matroska/WebM 元素层级过深，已停止递归解析", start, self.name))
            return
        offset = start
        while offset < end and stats["elements"] < MAX_VISIBLE_ELEMENTS:
            element_id = _read_vint(source, offset, keep_marker=True, max_len=4)
            if element_id is None:
                diagnostics.append(error("EBML element id 不完整", offset, self.name))
                break
            size_offset = offset + element_id.length
            size_vint = _read_vint(source, size_offset, keep_marker=False, max_len=8)
            if size_vint is None:
                diagnostics.append(error("EBML element size 不完整", size_offset, self.name))
                break

            payload_offset = size_offset + size_vint.length
            payload_size = max(0, end - payload_offset) if size_vint.unknown else size_vint.value
            payload_end = payload_offset + payload_size
            severity = Severity.NORMAL
            description = ""
            if payload_offset > end:
                diagnostics.append(error("EBML element header 超出父节点边界", offset, self.name))
                break
            if payload_end > end:
                diagnostics.append(error("EBML element payload 超出父节点边界", offset, self.name))
                payload_end = end
                payload_size = max(0, payload_end - payload_offset)
                severity = Severity.ERROR
                description = "payload 超出父节点边界"
            if size_vint.unknown:
                diagnostics.append(warn("EBML unknown-size element 已按父节点边界展开", size_offset, self.name))

            name, value_type = ELEMENTS.get(element_id.value, (f"Unknown 0x{element_id.value:X}", "binary"))
            node = parent.add_child(
                ParseNode(
                    name,
                    _node_type(name, value_type),
                    offset,
                    payload_end - offset,
                    severity=severity,
                    description=description,
                )
            )
            stats["elements"] += 1
            node.fields.extend(
                [
                    FieldInfo("element_id", f"0x{element_id.value:X}", offset, element_id.length, element_id.raw.hex(" ").upper()),
                    FieldInfo("header_size", element_id.length + size_vint.length, offset, element_id.length + size_vint.length),
                    FieldInfo("data_size", "unknown" if size_vint.unknown else payload_size, size_offset, size_vint.length, size_vint.raw.hex(" ").upper()),
                    FieldInfo("value_type", value_type),
                ]
            )

            if value_type == "master":
                child_context = dict(context) if name == "Cluster" else context
                self._parse_elements(source, node, payload_offset, payload_end, diagnostics, frames, child_context, stats, depth + 1)
            elif name in {"SimpleBlock", "Block"}:
                self._parse_block(source, node, payload_offset, payload_size, frames, context)
            else:
                value = _read_value(source, payload_offset, payload_size, value_type)
                node.fields.append(_value_field(name, value, payload_offset, payload_size, value_type))
                if name == "TimecodeScale" and isinstance(value, int):
                    context["timecode_scale"] = value
                elif name == "Timecode" and isinstance(value, int) and parent.name == "Cluster":
                    context["cluster_timecode"] = value

            offset = payload_end
        if offset < end and stats["elements"] >= MAX_VISIBLE_ELEMENTS:
            diagnostics.append(warn(f"Matroska/WebM 元素超过 {MAX_VISIBLE_ELEMENTS} 个，已停止展开后续元素", offset, self.name))

    def _parse_block(
        self,
        source: ByteSource,
        node: ParseNode,
        payload_offset: int,
        payload_size: int,
        frames: list[FrameInfo],
        context: dict[str, Any],
    ) -> None:
        payload = source.read_at(payload_offset, min(payload_size, 16))
        track = _parse_vint_bytes(payload, keep_marker=False, max_len=8)
        if track is None or len(payload) < track.length + 3:
            node.severity = Severity.WARNING
            node.description = "block header 不完整"
            return
        timecode_offset = payload_offset + track.length
        relative_timecode = int.from_bytes(payload[track.length : track.length + 2], "big", signed=True)
        flags = payload[track.length + 2]
        frame_payload_offset = payload_offset + track.length + 3
        frame_payload_size = max(0, payload_size - track.length - 3)
        cluster_timecode = int(context.get("cluster_timecode", 0))
        timecode_scale = int(context.get("timecode_scale", DEFAULT_TIMECODE_SCALE))
        absolute_timecode = cluster_timecode + relative_timecode
        pts = absolute_timecode * timecode_scale / 1_000_000_000
        lacing = (flags >> 1) & 0x03
        keyframe = bool(flags & 0x80)
        node.fields.extend(
            [
                FieldInfo("track_number", track.value, payload_offset, track.length, track.raw.hex(" ").upper()),
                FieldInfo("relative_timecode", relative_timecode, timecode_offset, 2, payload[track.length : track.length + 2].hex(" ").upper()),
                FieldInfo("absolute_timecode", absolute_timecode, timecode_offset, 0),
                FieldInfo("pts_seconds", pts, timecode_offset, 0),
                FieldInfo("keyframe", keyframe, payload_offset + track.length + 2, 1, hex(flags), bit_offset=(payload_offset + track.length + 2) * 8, bit_length=1),
                FieldInfo("invisible", bool(flags & 0x08), payload_offset + track.length + 2, 1, hex(flags), bit_offset=(payload_offset + track.length + 2) * 8 + 4, bit_length=1),
                FieldInfo("lacing", _lacing_name(lacing), payload_offset + track.length + 2, 1, hex(flags), bit_offset=(payload_offset + track.length + 2) * 8 + 5, bit_length=2),
                FieldInfo("discardable", bool(flags & 0x01), payload_offset + track.length + 2, 1, hex(flags), bit_offset=(payload_offset + track.length + 2) * 8 + 7, bit_length=1),
            ]
        )
        frames.append(
            FrameInfo(
                index=len(frames),
                offset=frame_payload_offset,
                size=frame_payload_size,
                pts=pts,
                dts=pts,
                frame_type=f"track {track.value} block",
                keyframe=keyframe,
            )
        )

    def _summary(self, root: ParseNode, context: dict[str, Any], frame_count: int, element_count: int) -> dict[str, Any]:
        doc_type = _first_value(root, "DocType")
        timecode_scale = _first_value(root, "TimecodeScale") or context.get("timecode_scale", DEFAULT_TIMECODE_SCALE)
        duration = _first_value(root, "Duration")
        duration_seconds = None
        if isinstance(duration, (int, float)) and isinstance(timecode_scale, int):
            duration_seconds = duration * timecode_scale / 1_000_000_000
        return {
            "doc_type": doc_type,
            "timecode_scale": timecode_scale,
            "duration": duration,
            "duration_seconds": duration_seconds,
            "tracks": _track_summaries(root),
            "frames": frame_count,
            "visible_elements": element_count,
        }


def _read_vint(source: ByteSource, offset: int, keep_marker: bool, max_len: int) -> VInt | None:
    head = source.read_at(offset, 1)
    if not head or head[0] == 0:
        return None
    first = head[0]
    mask = 0x80
    length = 1
    while length <= max_len and not (first & mask):
        mask >>= 1
        length += 1
    if length > max_len:
        return None
    raw = source.read_at(offset, length)
    if len(raw) < length:
        return None
    value = int.from_bytes(raw, "big")
    unknown = False
    if not keep_marker:
        value &= (1 << (7 * length)) - 1
        unknown = value == (1 << (7 * length)) - 1
    return VInt(value, length, raw, unknown)


def _parse_vint_bytes(data: bytes, keep_marker: bool, max_len: int) -> VInt | None:
    if not data or data[0] == 0:
        return None
    first = data[0]
    mask = 0x80
    length = 1
    while length <= max_len and not (first & mask):
        mask >>= 1
        length += 1
    if length > max_len or len(data) < length:
        return None
    raw = data[:length]
    value = int.from_bytes(raw, "big")
    if not keep_marker:
        value &= (1 << (7 * length)) - 1
    return VInt(value, length, raw)


def _read_value(source: ByteSource, offset: int, size: int, value_type: str) -> Any:
    payload = source.read_at(offset, min(size, 256))
    if value_type == "uint":
        return int.from_bytes(payload[: min(size, 8)], "big") if payload else 0
    if value_type == "string":
        return payload.decode("ascii", errors="replace").rstrip("\x00")
    if value_type == "utf8":
        return payload.decode("utf-8", errors="replace").rstrip("\x00")
    if value_type == "float":
        if size == 4 and len(payload) >= 4:
            return struct.unpack(">f", payload[:4])[0]
        if size == 8 and len(payload) >= 8:
            return struct.unpack(">d", payload[:8])[0]
    return payload[:32].hex(" ").upper()


def _value_field(name: str, value: Any, offset: int, size: int, value_type: str) -> FieldInfo:
    display = TRACK_TYPES.get(value, value) if name == "TrackType" and isinstance(value, int) else value
    return FieldInfo("value", display, offset, size, description=value_type)


def _node_type(name: str, value_type: str) -> str:
    if name == "Cluster":
        return "ebml_cluster"
    if name == "TrackEntry":
        return "ebml_track"
    if name in {"SimpleBlock", "Block"}:
        return "ebml_block"
    return "ebml_master" if value_type == "master" else "ebml_element"


def _lacing_name(value: int) -> str:
    return {0: "none", 1: "xiph", 2: "fixed-size", 3: "ebml"}.get(value, f"unknown({value})")


def _first_value(node: ParseNode, element_name: str) -> Any:
    if node.name == element_name:
        for field in node.fields:
            if field.name == "value":
                return field.value
    for child in node.children:
        value = _first_value(child, element_name)
        if value not in (None, ""):
            return value
    return None


def _track_summaries(root: ParseNode) -> list[dict[str, Any]]:
    tracks = []
    for track in _nodes_named(root, "TrackEntry"):
        summary = {
            "number": _first_value(track, "TrackNumber"),
            "type": _first_value(track, "TrackType"),
            "codec": _first_value(track, "CodecID"),
            "name": _first_value(track, "Name"),
            "language": _first_value(track, "Language"),
            "width": _first_value(track, "PixelWidth"),
            "height": _first_value(track, "PixelHeight"),
            "sample_rate": _first_value(track, "SamplingFrequency"),
            "channels": _first_value(track, "Channels"),
            "bit_depth": _first_value(track, "BitDepth"),
        }
        tracks.append({key: value for key, value in summary.items() if value not in (None, "")})
    return tracks


def _nodes_named(node: ParseNode, name: str):
    if node.name == name:
        yield node
    for child in node.children:
        yield from _nodes_named(child, name)
