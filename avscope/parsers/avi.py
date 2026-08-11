from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, ParseNode, ParseResult
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, u32le, warn


class AviParser(FormatParser):
    name = "AVI"
    extensions = (".avi",)

    def probe(self, source: ByteSource) -> bool:
        head = source.head(12)
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"AVI "

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        diagnostics = []
        head = source.head(12)
        riff_size = u32le(head, 4) + 8
        root.fields.extend(
            [
                FieldInfo("riff_id", "RIFF", 0, 4, "52 49 46 46"),
                FieldInfo("riff_size", riff_size, 4, 4, hex(riff_size)),
                FieldInfo("avi_id", "AVI ", 8, 4, "41 56 49 20"),
            ]
        )
        if riff_size > source.size:
            diagnostics.append(warn("AVI RIFF 声明长度超过文件实际长度", 4, self.name))
        summary: dict = {}
        self._parse_chunks(source, root, 12, min(source.size, riff_size), diagnostics, summary, depth=0)
        return ParseResult(media_info(source, self.name, **summary), root, diagnostics=diagnostics)

    def _parse_chunks(
        self,
        source: ByteSource,
        parent: ParseNode,
        start: int,
        end: int,
        diagnostics: list,
        summary: dict,
        depth: int,
    ) -> None:
        if depth > 12:
            diagnostics.append(warn("AVI RIFF 层级过深，已停止递归解析", start, self.name))
            return
        offset = start
        while offset + 8 <= end:
            header = source.read_at(offset, 12)
            chunk_id = header[:4].decode("ascii", errors="replace")
            chunk_size = u32le(header, 4)
            total_size = 8 + chunk_size + (chunk_size & 1)
            if offset + total_size > end:
                diagnostics.append(error(f"{chunk_id} chunk 超出父节点边界", offset, self.name))
                total_size = end - offset
            node = parent.add_child(ParseNode(chunk_id, "riff_list" if chunk_id == "LIST" else "riff_chunk", offset, total_size))
            node.fields.extend(
                [
                    FieldInfo("chunk_id", chunk_id, offset, 4, header[:4].hex(" ").upper()),
                    FieldInfo("chunk_size", chunk_size, offset + 4, 4, hex(chunk_size)),
                ]
            )
            if chunk_id == "LIST" and chunk_size >= 4:
                list_type = header[8:12].decode("ascii", errors="replace")
                node.name = f"LIST {list_type}"
                node.fields.append(FieldInfo("list_type", list_type, offset + 8, 4, header[8:12].hex(" ").upper()))
                self._parse_chunks(source, node, offset + 12, offset + 8 + chunk_size, diagnostics, summary, depth + 1)
            elif chunk_id == "avih":
                self._parse_avih(source, node, offset, chunk_size, summary, diagnostics)
            elif chunk_id == "strh":
                self._parse_strh(source, node, offset, chunk_size, summary)
            offset += total_size

    def _parse_avih(self, source: ByteSource, node: ParseNode, offset: int, chunk_size: int, summary: dict, diagnostics: list) -> None:
        payload = source.read_at(offset + 8, min(chunk_size, 64))
        if len(payload) < 40:
            diagnostics.append(error("AVI avih chunk 长度不足", offset, self.name))
            return
        micro_sec_per_frame = u32le(payload, 0)
        max_bytes_per_sec = u32le(payload, 4)
        padding_granularity = u32le(payload, 8)
        flags = u32le(payload, 12)
        total_frames = u32le(payload, 16)
        initial_frames = u32le(payload, 20)
        streams = u32le(payload, 24)
        suggested_buffer_size = u32le(payload, 28)
        width = u32le(payload, 32)
        height = u32le(payload, 36)
        fps = 1_000_000 / micro_sec_per_frame if micro_sec_per_frame else None
        duration_seconds = total_frames * micro_sec_per_frame / 1_000_000 if micro_sec_per_frame else None
        node.fields.extend(
            [
                FieldInfo("dwMicroSecPerFrame", micro_sec_per_frame, offset + 8, 4, hex(micro_sec_per_frame), description="每帧微秒数"),
                FieldInfo("dwMaxBytesPerSec", max_bytes_per_sec, offset + 12, 4, hex(max_bytes_per_sec)),
                FieldInfo("dwPaddingGranularity", padding_granularity, offset + 16, 4, hex(padding_granularity)),
                FieldInfo("dwFlags", flags, offset + 20, 4, hex(flags)),
                FieldInfo("dwTotalFrames", total_frames, offset + 24, 4, hex(total_frames)),
                FieldInfo("dwInitialFrames", initial_frames, offset + 28, 4, hex(initial_frames)),
                FieldInfo("dwStreams", streams, offset + 32, 4, hex(streams)),
                FieldInfo("dwSuggestedBufferSize", suggested_buffer_size, offset + 36, 4, hex(suggested_buffer_size)),
                FieldInfo("dwWidth", width, offset + 40, 4, hex(width)),
                FieldInfo("dwHeight", height, offset + 44, 4, hex(height)),
                FieldInfo("fps", fps, offset + 8, 0, description="1_000_000 / dwMicroSecPerFrame"),
                FieldInfo("duration_seconds", duration_seconds, offset + 24, 0, description="dwTotalFrames * dwMicroSecPerFrame / 1_000_000"),
            ]
        )
        summary.update(
            {
                "width": width,
                "height": height,
                "streams": streams,
                "total_frames": total_frames,
                "micro_sec_per_frame": micro_sec_per_frame,
                "fps": fps,
                "duration_seconds": duration_seconds,
            }
        )

    def _parse_strh(self, source: ByteSource, node: ParseNode, offset: int, chunk_size: int, summary: dict) -> None:
        payload = source.read_at(offset + 8, min(chunk_size, 64))
        if len(payload) < 32:
            return
        stream_type = payload[0:4].decode("ascii", errors="replace")
        handler = payload[4:8].decode("ascii", errors="replace")
        scale = u32le(payload, 20)
        rate = u32le(payload, 24)
        length = u32le(payload, 32) if len(payload) >= 36 else None
        fps = rate / scale if scale else None
        node.fields.extend(
            [
                FieldInfo("fccType", stream_type, offset + 8, 4, payload[0:4].hex(" ").upper()),
                FieldInfo("fccHandler", handler, offset + 12, 4, payload[4:8].hex(" ").upper()),
                FieldInfo("dwScale", scale, offset + 28, 4, hex(scale)),
                FieldInfo("dwRate", rate, offset + 32, 4, hex(rate)),
                FieldInfo("dwLength", length, offset + 40, 4 if length is not None else 0, "" if length is None else hex(length)),
                FieldInfo("stream_rate", fps, offset + 28, 0),
            ]
        )
        summary.setdefault("stream_headers", []).append({"type": stream_type, "handler": handler, "scale": scale, "rate": rate, "length": length})
