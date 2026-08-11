from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, u32be, warn


MAX_VISIBLE_TAGS = 1000
TAG_TYPES = {
    8: "audio",
    9: "video",
    18: "script",
}


class FlvParser(FormatParser):
    name = "FLV"
    extensions = (".flv",)

    def probe(self, source: ByteSource) -> bool:
        return source.head(3) == b"FLV"

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        diagnostics = []
        header = source.head(9)
        if len(header) < 9:
            diagnostics.append(error("FLV header 长度不足 9 字节", 0, self.name))
            return ParseResult(media_info(source, self.name), root, diagnostics=diagnostics)

        version = header[3]
        flags = header[4]
        data_offset = u32be(header, 5)
        has_audio = bool(flags & 0x04)
        has_video = bool(flags & 0x01)
        root.fields.extend(
            [
                FieldInfo("signature", "FLV", 0, 3, "46 4C 56"),
                FieldInfo("version", version, 3, 1, hex(version)),
                FieldInfo("has_audio", has_audio, 4, 1, bit_offset=34, bit_length=1),
                FieldInfo("has_video", has_video, 4, 1, bit_offset=39, bit_length=1),
                FieldInfo("data_offset", data_offset, 5, 4, hex(data_offset)),
            ]
        )
        if data_offset < 9:
            diagnostics.append(error("FLV data_offset 小于 header 长度", 5, self.name))
            data_offset = 9
        if source.size < data_offset + 4:
            diagnostics.append(error("FLV 缺少 PreviousTagSize0", data_offset, self.name))
            return ParseResult(media_info(source, self.name, version=version, has_audio=has_audio, has_video=has_video), root, diagnostics=diagnostics)

        previous0 = u32be(source.read_at(data_offset, 4))
        root.fields.append(FieldInfo("previous_tag_size_0", previous0, data_offset, 4, hex(previous0)))
        if previous0 != 0:
            diagnostics.append(warn("FLV PreviousTagSize0 应为 0", data_offset, self.name))

        offset = data_offset + 4
        tag_counts: dict[str, int] = {}
        parsed_tags = 0
        last_timestamp = None
        while offset + 11 <= source.size and parsed_tags < MAX_VISIBLE_TAGS:
            header = source.read_at(offset, 11)
            fields = _tag_fields(header, offset)
            tag_type = TAG_TYPES.get(int(fields["tag_type"]), "unknown")
            tag_counts[tag_type] = tag_counts.get(tag_type, 0) + 1
            data_size = int(fields["data_size"])
            timestamp = int(fields["timestamp"])
            tag_total = 11 + data_size
            previous_size_offset = offset + tag_total
            severity = Severity.NORMAL
            description = ""
            if previous_size_offset + 4 > source.size:
                diagnostics.append(error("FLV tag 超出文件边界", offset, self.name))
                severity = Severity.ERROR
                description = "tag 超出文件边界"
                tag_total = max(0, source.size - offset)
            elif last_timestamp is not None and timestamp < last_timestamp:
                diagnostics.append(warn(f"FLV tag 时间戳回退: previous={last_timestamp} current={timestamp}", offset, self.name))
                severity = Severity.WARNING
                description = "tag 时间戳回退"

            node = root.add_child(
                ParseNode(
                    f"Tag[{parsed_tags}] {tag_type}",
                    "flv_tag",
                    offset,
                    min(tag_total + 4, source.size - offset),
                    severity=severity,
                    description=description,
                )
            )
            node.fields.extend(_field_infos(fields, offset))
            if previous_size_offset + 4 <= source.size:
                previous_size = u32be(source.read_at(previous_size_offset, 4))
                node.fields.append(FieldInfo("previous_tag_size", previous_size, previous_size_offset, 4, hex(previous_size)))
                if previous_size != tag_total:
                    diagnostics.append(warn(f"FLV PreviousTagSize 不匹配: expected={tag_total} actual={previous_size}", previous_size_offset, self.name))
                    node.severity = Severity.WARNING if node.severity == Severity.NORMAL else node.severity
                    node.description = node.description or "PreviousTagSize 不匹配"
            last_timestamp = timestamp
            parsed_tags += 1
            offset += tag_total + 4

        if offset < source.size and parsed_tags >= MAX_VISIBLE_TAGS:
            diagnostics.append(warn(f"FLV tag 超过 {MAX_VISIBLE_TAGS} 个，已停止展开后续 tag", offset, self.name))
        elif offset < source.size:
            diagnostics.append(warn("FLV 文件尾部存在未解析字节", offset, self.name))

        summary = {
            "version": version,
            "has_audio": has_audio,
            "has_video": has_video,
            "data_offset": data_offset,
            "tags": parsed_tags,
            "tag_counts": tag_counts,
        }
        return ParseResult(media_info(source, self.name, **summary), root, diagnostics=diagnostics)


def _tag_fields(header: bytes, offset: int) -> dict[str, int]:
    timestamp_lower = int.from_bytes(header[4:7], "big")
    timestamp_extended = header[7]
    return {
        "tag_type": header[0],
        "data_size": int.from_bytes(header[1:4], "big"),
        "timestamp": (timestamp_extended << 24) | timestamp_lower,
        "timestamp_extended": timestamp_extended,
        "stream_id": int.from_bytes(header[8:11], "big"),
    }


def _field_infos(fields: dict[str, int], offset: int) -> list[FieldInfo]:
    tag_type = int(fields["tag_type"])
    return [
        FieldInfo("tag_type", TAG_TYPES.get(tag_type, f"unknown({tag_type})"), offset, 1, hex(tag_type)),
        FieldInfo("data_size", fields["data_size"], offset + 1, 3, hex(int(fields["data_size"]))),
        FieldInfo("timestamp", fields["timestamp"], offset + 4, 4, hex(int(fields["timestamp"]))),
        FieldInfo("timestamp_extended", fields["timestamp_extended"], offset + 7, 1, hex(int(fields["timestamp_extended"]))),
        FieldInfo("stream_id", fields["stream_id"], offset + 8, 3, hex(int(fields["stream_id"]))),
    ]
