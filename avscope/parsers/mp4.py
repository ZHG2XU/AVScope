from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import DiagnosticIssue, FieldInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, u32be, u64be, warn


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
