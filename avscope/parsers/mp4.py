from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import DiagnosticIssue, FieldInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, u16be, u32be, u64be, warn


CONTAINER_BOXES = {
    "moov",
    "trak",
    "mdia",
    "minf",
    "stbl",
    "edts",
    "dinf",
    "moof",
    "traf",
    "mfra",
    "udta",
    "meta",
    "ilst",
}


class Mp4Parser(FormatParser):
    name = "MP4/MOV"
    extensions = (".mp4", ".mov", ".m4v", ".m4a")

    def probe(self, source: ByteSource) -> bool:
        head = source.head(16)
        if len(head) < 12:
            return False
        box_type = head[4:8]
        return box_type in {b"ftyp", b"moov", b"mdat", b"free", b"wide"}

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        diagnostics: list[DiagnosticIssue] = []
        self._parse_boxes(source, root, 0, source.size, diagnostics, 0)
        summary = {
            "boxes": len(root.children),
            "has_moov": any(c.name == "moov" for c in root.children),
            "has_mdat": any(c.name == "mdat" for c in root.children),
        }
        if not summary["has_moov"]:
            diagnostics.append(warn("未发现 moov box，文件可能缺少索引或不是完整 MP4/MOV", 0, self.name))
        if root.children and root.children[-1].name == "moov":
            diagnostics.append(warn("moov 位于文件尾部，网络渐进播放体验可能较差", root.children[-1].offset, self.name))
        return ParseResult(media_info(source, self.name, **summary), root, diagnostics=diagnostics)

    def _parse_boxes(
        self,
        source: ByteSource,
        parent: ParseNode,
        start: int,
        end: int,
        diagnostics: list[DiagnosticIssue],
        depth: int,
    ) -> None:
        if depth > 12:
            diagnostics.append(warn("MP4 box 层级过深，已停止递归解析", start, self.name))
            return
        offset = start
        while offset + 8 <= end:
            header = source.read_at(offset, 16)
            if len(header) < 8:
                break
            size32 = u32be(header, 0)
            raw_type = header[4:8]
            try:
                box_type = raw_type.decode("ascii")
            except UnicodeDecodeError:
                diagnostics.append(error("box type 不是 ASCII，结构可能损坏", offset + 4, self.name))
                break

            header_size = 8
            if size32 == 1:
                if len(header) < 16:
                    diagnostics.append(error("extended size box 头不完整", offset, self.name))
                    break
                box_size = u64be(header, 8)
                header_size = 16
            elif size32 == 0:
                box_size = end - offset
            else:
                box_size = size32

            if box_size < header_size:
                diagnostics.append(error(f"{box_type} box size 小于头部长度", offset, self.name))
                break
            if offset + box_size > end:
                diagnostics.append(error(f"{box_type} box size 超出父节点边界", offset, self.name))
                box_size = end - offset

            node = parent.add_child(ParseNode(box_type, "box", offset, box_size))
            node.fields.extend(
                [
                    FieldInfo("size", box_size, offset, header_size if header_size == 8 else 16, hex(box_size), description="box 总长度"),
                    FieldInfo("type", box_type, offset + 4, 4, raw_type.hex(" ").upper(), description="box 类型"),
                ]
            )
            if box_type == "ftyp":
                self._parse_ftyp(source, node)
            elif box_type == "mvhd":
                self._parse_mvhd(source, node)
            elif box_type == "tkhd":
                self._parse_tkhd(source, node)
            elif box_type == "mdhd":
                self._parse_mdhd(source, node)
            elif box_type == "hdlr":
                self._parse_hdlr(source, node)
            elif box_type == "stsd":
                self._parse_stsd(source, node, diagnostics)
            elif box_type == "stts":
                self._parse_table_entries(source, node, ("sample_count", "sample_delta"))
            elif box_type == "stsc":
                self._parse_table_entries(source, node, ("first_chunk", "samples_per_chunk", "sample_description_index"))
            elif box_type == "stsz":
                self._parse_stsz(source, node)
            elif box_type == "stco":
                self._parse_chunk_offsets(source, node, offset_size=4)
            elif box_type == "co64":
                self._parse_chunk_offsets(source, node, offset_size=8)
            elif box_type in CONTAINER_BOXES:
                child_start = offset + header_size
                if box_type == "meta":
                    child_start += 4
                self._parse_boxes(source, node, child_start, offset + box_size, diagnostics, depth + 1)

            offset += box_size
            if box_size == 0:
                break

    def _parse_ftyp(self, source: ByteSource, node: ParseNode) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 64))
        if len(payload) < 8:
            node.severity = Severity.WARNING
            return
        major = payload[:4].decode("ascii", errors="replace")
        minor = u32be(payload, 4)
        brands = [
            payload[i : i + 4].decode("ascii", errors="replace")
            for i in range(8, len(payload) - 3, 4)
        ]
        node.fields.extend(
            [
                FieldInfo("major_brand", major, node.offset + 8, 4, payload[:4].hex(" ").upper()),
                FieldInfo("minor_version", minor, node.offset + 12, 4, hex(minor)),
                FieldInfo("compatible_brands", ", ".join(brands), node.offset + 16, max(0, len(payload) - 8)),
            ]
        )

    def _parse_mvhd(self, source: ByteSource, node: ParseNode) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 120))
        if len(payload) < 20:
            node.severity = Severity.WARNING
            return
        version = payload[0]
        flags = int.from_bytes(payload[1:4], "big")
        node.fields.extend(
            [
                FieldInfo("version", version, node.offset + 8, 1, hex(version)),
                FieldInfo("flags", flags, node.offset + 9, 3, hex(flags)),
            ]
        )
        if version == 1:
            if len(payload) < 32:
                node.severity = Severity.WARNING
                return
            creation_time = u64be(payload, 4)
            modification_time = u64be(payload, 12)
            timescale = u32be(payload, 20)
            duration = u64be(payload, 24)
            timescale_offset = node.offset + 28
            duration_offset = node.offset + 32
        else:
            creation_time = u32be(payload, 4)
            modification_time = u32be(payload, 8)
            timescale = u32be(payload, 12)
            duration = u32be(payload, 16)
            timescale_offset = node.offset + 20
            duration_offset = node.offset + 24
        duration_seconds = duration / timescale if timescale else None
        node.fields.extend(
            [
                FieldInfo("creation_time", creation_time, node.offset + 12, 4 if version == 0 else 8, hex(creation_time)),
                FieldInfo("modification_time", modification_time, node.offset + (16 if version == 0 else 20), 4 if version == 0 else 8, hex(modification_time)),
                FieldInfo("timescale", timescale, timescale_offset, 4, hex(timescale), description="movie time units per second"),
                FieldInfo("duration", duration, duration_offset, 4 if version == 0 else 8, hex(duration), description="movie duration in timescale units"),
                FieldInfo("duration_seconds", duration_seconds, duration_offset, 0, description="duration / timescale"),
            ]
        )

    def _parse_tkhd(self, source: ByteSource, node: ParseNode) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 120))
        if len(payload) < 84:
            node.severity = Severity.WARNING
            return
        version = payload[0]
        flags = int.from_bytes(payload[1:4], "big")
        if version == 1:
            if len(payload) < 96:
                node.severity = Severity.WARNING
                return
            creation_time = u64be(payload, 4)
            modification_time = u64be(payload, 12)
            track_id = u32be(payload, 20)
            duration = u64be(payload, 28)
            width_offset = 88
            height_offset = 92
        else:
            creation_time = u32be(payload, 4)
            modification_time = u32be(payload, 8)
            track_id = u32be(payload, 12)
            duration = u32be(payload, 20)
            width_offset = 76
            height_offset = 80
        width_raw = u32be(payload, width_offset)
        height_raw = u32be(payload, height_offset)
        width = width_raw / 65536
        height = height_raw / 65536
        node.fields.extend(
            [
                FieldInfo("version", version, node.offset + 8, 1, hex(version)),
                FieldInfo("flags", flags, node.offset + 9, 3, hex(flags)),
                FieldInfo("creation_time", creation_time, node.offset + 12, 4 if version == 0 else 8, hex(creation_time)),
                FieldInfo("modification_time", modification_time, node.offset + (16 if version == 0 else 20), 4 if version == 0 else 8, hex(modification_time)),
                FieldInfo("track_id", track_id, node.offset + (20 if version == 0 else 28), 4, hex(track_id)),
                FieldInfo("duration", duration, node.offset + (28 if version == 0 else 36), 4 if version == 0 else 8, hex(duration)),
                FieldInfo("width", width, node.offset + 8 + width_offset, 4, hex(width_raw), description="16.16 fixed point"),
                FieldInfo("height", height, node.offset + 8 + height_offset, 4, hex(height_raw), description="16.16 fixed point"),
            ]
        )

    def _parse_mdhd(self, source: ByteSource, node: ParseNode) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 48))
        if len(payload) < 24:
            node.severity = Severity.WARNING
            return
        version = payload[0]
        flags = int.from_bytes(payload[1:4], "big")
        if version == 1:
            if len(payload) < 36:
                node.severity = Severity.WARNING
                return
            creation_time = u64be(payload, 4)
            modification_time = u64be(payload, 12)
            timescale = u32be(payload, 20)
            duration = u64be(payload, 24)
            language_raw = int.from_bytes(payload[32:34], "big")
            language_offset = 32
        else:
            creation_time = u32be(payload, 4)
            modification_time = u32be(payload, 8)
            timescale = u32be(payload, 12)
            duration = u32be(payload, 16)
            language_raw = int.from_bytes(payload[20:22], "big")
            language_offset = 20
        duration_seconds = duration / timescale if timescale else None
        node.fields.extend(
            [
                FieldInfo("version", version, node.offset + 8, 1, hex(version)),
                FieldInfo("flags", flags, node.offset + 9, 3, hex(flags)),
                FieldInfo("creation_time", creation_time, node.offset + 12, 4 if version == 0 else 8, hex(creation_time)),
                FieldInfo("modification_time", modification_time, node.offset + (16 if version == 0 else 20), 4 if version == 0 else 8, hex(modification_time)),
                FieldInfo("timescale", timescale, node.offset + (20 if version == 0 else 28), 4, hex(timescale), description="media time units per second"),
                FieldInfo("duration", duration, node.offset + (24 if version == 0 else 32), 4 if version == 0 else 8, hex(duration), description="media duration in timescale units"),
                FieldInfo("duration_seconds", duration_seconds, node.offset + (24 if version == 0 else 32), 0, description="duration / timescale"),
                FieldInfo("language", _decode_mp4_language(language_raw), node.offset + 8 + language_offset, 2, hex(language_raw)),
            ]
        )

    def _parse_hdlr(self, source: ByteSource, node: ParseNode) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 256))
        if len(payload) < 24:
            node.severity = Severity.WARNING
            return
        version = payload[0]
        flags = int.from_bytes(payload[1:4], "big")
        handler_type = payload[8:12].decode("ascii", errors="replace")
        name = payload[24:].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        node.fields.extend(
            [
                FieldInfo("version", version, node.offset + 8, 1, hex(version)),
                FieldInfo("flags", flags, node.offset + 9, 3, hex(flags)),
                FieldInfo("handler_type", handler_type, node.offset + 16, 4, payload[8:12].hex(" ").upper()),
                FieldInfo("name", name, node.offset + 32, len(name)),
            ]
        )

    def _parse_stsd(self, source: ByteSource, node: ParseNode, diagnostics: list[DiagnosticIssue]) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 4096))
        if len(payload) < 8:
            node.severity = Severity.WARNING
            return
        version = payload[0]
        flags = int.from_bytes(payload[1:4], "big")
        entry_count = u32be(payload, 4)
        node.fields.extend(
            [
                FieldInfo("version", version, node.offset + 8, 1, hex(version)),
                FieldInfo("flags", flags, node.offset + 9, 3, hex(flags)),
                FieldInfo("entry_count", entry_count, node.offset + 12, 4, hex(entry_count)),
            ]
        )
        offset = node.offset + 16
        end = node.offset + node.size
        for index in range(min(entry_count, 16)):
            if offset + 8 > end:
                diagnostics.append(warn(f"stsd entry[{index}] header is incomplete", offset, self.name))
                break
            header = source.read_at(offset, 16)
            entry_size = u32be(header, 0)
            entry_type = header[4:8].decode("ascii", errors="replace")
            if entry_size < 8 or offset + entry_size > end:
                diagnostics.append(warn(f"stsd entry[{index}] size is invalid", offset, self.name))
                break
            child = node.add_child(ParseNode(f"entry[{index}] {entry_type}", "sample_entry", offset, entry_size))
            child.fields.extend(
                [
                    FieldInfo("size", entry_size, offset, 4, hex(entry_size)),
                    FieldInfo("type", entry_type, offset + 4, 4, header[4:8].hex(" ").upper()),
                ]
            )
            if entry_type in {"avc1", "hvc1", "hev1", "mp4v"}:
                self._parse_video_sample_entry(source, child)
            elif entry_type in {"mp4a", "enca"}:
                self._parse_audio_sample_entry(source, child)
            offset += entry_size

    def _parse_video_sample_entry(self, source: ByteSource, node: ParseNode) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 86))
        if len(payload) < 78:
            node.severity = Severity.WARNING
            return
        width = u16be(payload, 24)
        height = u16be(payload, 26)
        frame_count = u16be(payload, 40)
        depth = u16be(payload, 74)
        compressor_name_length = min(payload[42], 31)
        compressor_name = payload[43 : 43 + compressor_name_length].decode("utf-8", errors="replace")
        node.fields.extend(
            [
                FieldInfo("data_reference_index", u16be(payload, 6), node.offset + 14, 2),
                FieldInfo("width", width, node.offset + 32, 2, hex(width)),
                FieldInfo("height", height, node.offset + 34, 2, hex(height)),
                FieldInfo("horizresolution", u32be(payload, 28) / 65536, node.offset + 36, 4),
                FieldInfo("vertresolution", u32be(payload, 32) / 65536, node.offset + 40, 4),
                FieldInfo("frame_count", frame_count, node.offset + 48, 2, hex(frame_count)),
                FieldInfo("compressor_name", compressor_name, node.offset + 51, compressor_name_length),
                FieldInfo("depth", depth, node.offset + 82, 2, hex(depth)),
            ]
        )

    def _parse_audio_sample_entry(self, source: ByteSource, node: ParseNode) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 28))
        if len(payload) < 28:
            node.severity = Severity.WARNING
            return
        channel_count = u16be(payload, 16)
        sample_size = u16be(payload, 18)
        sample_rate_raw = u32be(payload, 24)
        node.fields.extend(
            [
                FieldInfo("data_reference_index", u16be(payload, 6), node.offset + 14, 2),
                FieldInfo("channel_count", channel_count, node.offset + 24, 2, hex(channel_count)),
                FieldInfo("sample_size", sample_size, node.offset + 26, 2, hex(sample_size)),
                FieldInfo("sample_rate", sample_rate_raw / 65536, node.offset + 32, 4, hex(sample_rate_raw)),
            ]
        )

    def _parse_table_entries(self, source: ByteSource, node: ParseNode, names: tuple[str, ...]) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 4096))
        if len(payload) < 8:
            node.severity = Severity.WARNING
            return
        version = payload[0]
        flags = int.from_bytes(payload[1:4], "big")
        entry_count = u32be(payload, 4)
        node.fields.extend(
            [
                FieldInfo("version", version, node.offset + 8, 1, hex(version)),
                FieldInfo("flags", flags, node.offset + 9, 3, hex(flags)),
                FieldInfo("entry_count", entry_count, node.offset + 12, 4, hex(entry_count)),
            ]
        )
        entry_size = len(names) * 4
        for index in range(min(entry_count, 32)):
            entry_offset = 8 + index * entry_size
            if entry_offset + entry_size > len(payload):
                break
            child = node.add_child(ParseNode(f"entry[{index}]", "table_entry", node.offset + 8 + entry_offset, entry_size))
            for field_index, name in enumerate(names):
                value_offset = entry_offset + field_index * 4
                value = u32be(payload, value_offset)
                child.fields.append(FieldInfo(name, value, node.offset + 8 + value_offset, 4, hex(value)))

    def _parse_stsz(self, source: ByteSource, node: ParseNode) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 4096))
        if len(payload) < 12:
            node.severity = Severity.WARNING
            return
        version = payload[0]
        flags = int.from_bytes(payload[1:4], "big")
        sample_size = u32be(payload, 4)
        sample_count = u32be(payload, 8)
        node.fields.extend(
            [
                FieldInfo("version", version, node.offset + 8, 1, hex(version)),
                FieldInfo("flags", flags, node.offset + 9, 3, hex(flags)),
                FieldInfo("sample_size", sample_size, node.offset + 12, 4, hex(sample_size)),
                FieldInfo("sample_count", sample_count, node.offset + 16, 4, hex(sample_count)),
            ]
        )
        if sample_size:
            return
        for index in range(min(sample_count, 64)):
            value_offset = 12 + index * 4
            if value_offset + 4 > len(payload):
                break
            value = u32be(payload, value_offset)
            child = node.add_child(ParseNode(f"sample_size[{index}]", "table_entry", node.offset + 8 + value_offset, 4))
            child.fields.append(FieldInfo("entry_size", value, node.offset + 8 + value_offset, 4, hex(value)))

    def _parse_chunk_offsets(self, source: ByteSource, node: ParseNode, offset_size: int) -> None:
        payload = source.read_at(node.offset + 8, min(node.size - 8, 4096))
        if len(payload) < 8:
            node.severity = Severity.WARNING
            return
        version = payload[0]
        flags = int.from_bytes(payload[1:4], "big")
        entry_count = u32be(payload, 4)
        node.fields.extend(
            [
                FieldInfo("version", version, node.offset + 8, 1, hex(version)),
                FieldInfo("flags", flags, node.offset + 9, 3, hex(flags)),
                FieldInfo("entry_count", entry_count, node.offset + 12, 4, hex(entry_count)),
            ]
        )
        for index in range(min(entry_count, 64)):
            value_offset = 8 + index * offset_size
            if value_offset + offset_size > len(payload):
                break
            value = u64be(payload, value_offset) if offset_size == 8 else u32be(payload, value_offset)
            child = node.add_child(ParseNode(f"chunk_offset[{index}]", "table_entry", node.offset + 8 + value_offset, offset_size))
            child.fields.append(FieldInfo("chunk_offset", value, node.offset + 8 + value_offset, offset_size, hex(value)))


def _decode_mp4_language(value: int) -> str:
    if value == 0:
        return ""
    chars = [
        chr(((value >> 10) & 0x1F) + 0x60),
        chr(((value >> 5) & 0x1F) + 0x60),
        chr((value & 0x1F) + 0x60),
    ]
    return "".join(chars)
