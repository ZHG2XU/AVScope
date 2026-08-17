from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, ParseNode, ParseResult
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, u16le, u32le, warn


MAX_INDEX_ENTRY_NODES = 10_000


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
        summary: dict = {
            "riff_segments": [{"type": "AVI ", "offset": 0, "size": min(source.size, riff_size)}],
            "avix_segments": 0,
        }
        self._parse_chunks(source, root, 12, min(source.size, riff_size), diagnostics, summary, depth=0)
        self._parse_avix_segments(source, root, riff_size + (riff_size & 1), diagnostics, summary)
        if "open_dml_total_frames" in summary:
            summary["total_frames"] = summary["open_dml_total_frames"]
            micro_sec_per_frame = summary.get("micro_sec_per_frame")
            if micro_sec_per_frame:
                summary["duration_seconds"] = summary["total_frames"] * micro_sec_per_frame / 1_000_000
        open_dml = bool(summary.get("open_dml") or summary["avix_segments"])
        summary["open_dml"] = open_dml
        summary["avi_version"] = "2.0 (OpenDML)" if open_dml else "1.0"
        root.fields.append(FieldInfo("avi_version", summary["avi_version"], description="根据 OpenDML 头、索引或 AVIX 分段判断"))
        return ParseResult(media_info(source, self.name, **summary), root, diagnostics=diagnostics)

    def _parse_avix_segments(
        self,
        source: ByteSource,
        root: ParseNode,
        start: int,
        diagnostics: list,
        summary: dict,
    ) -> None:
        offset = start
        while offset + 12 <= source.size:
            header = source.read_at(offset, 12)
            if header[:4] != b"RIFF":
                diagnostics.append(warn("首个 AVI RIFF 段后存在无法识别的附加数据", offset, self.name))
                return
            segment_size = u32le(header, 4) + 8
            form_type = header[8:12].decode("ascii", errors="replace")
            if segment_size < 12:
                diagnostics.append(error("AVI 扩展 RIFF 段长度无效", offset, self.name))
                return
            segment_end = offset + segment_size
            if segment_end > source.size:
                diagnostics.append(warn("AVI 扩展 RIFF 段声明长度超过文件实际长度", offset + 4, self.name))
                segment_end = source.size
            node = root.add_child(ParseNode(f"RIFF {form_type}", "riff_segment", offset, segment_end - offset))
            node.fields.extend(
                [
                    FieldInfo("riff_id", "RIFF", offset, 4, "52 49 46 46"),
                    FieldInfo("riff_size", segment_size, offset + 4, 4, hex(segment_size)),
                    FieldInfo("form_type", form_type, offset + 8, 4, header[8:12].hex(" ").upper()),
                ]
            )
            summary["riff_segments"].append({"type": form_type, "offset": offset, "size": segment_end - offset})
            if form_type != "AVIX":
                diagnostics.append(warn(f"AVI 后续 RIFF 段类型不是 AVIX：{form_type}", offset + 8, self.name))
            else:
                summary["avix_segments"] += 1
                summary["open_dml"] = True
            self._parse_chunks(source, node, offset + 12, segment_end, diagnostics, summary, depth=0)
            next_offset = offset + segment_size + (segment_size & 1)
            if next_offset <= offset:
                return
            offset = next_offset
        if offset < source.size:
            diagnostics.append(warn("AVI 文件尾部存在不足 12 字节的附加数据", offset, self.name))

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
                if list_type == "odml":
                    summary["open_dml"] = True
                list_end = min(end, offset + 8 + chunk_size)
                self._parse_chunks(source, node, offset + 12, list_end, diagnostics, summary, depth + 1)
            elif chunk_id == "avih":
                self._parse_avih(source, node, offset, chunk_size, summary, diagnostics)
            elif chunk_id == "strh":
                self._parse_strh(source, node, offset, chunk_size, summary)
            elif chunk_id == "dmlh":
                self._parse_dmlh(source, node, offset, chunk_size, summary, diagnostics)
            elif chunk_id == "indx" or chunk_id.startswith("ix"):
                self._parse_open_dml_index(source, node, offset, chunk_size, summary, diagnostics)
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
                "avi_header_total_frames": total_frames,
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

    def _parse_dmlh(self, source: ByteSource, node: ParseNode, offset: int, chunk_size: int, summary: dict, diagnostics: list) -> None:
        payload = source.read_at(offset + 8, min(chunk_size, 4))
        if len(payload) < 4:
            diagnostics.append(error("AVI OpenDML dmlh chunk 长度不足", offset, self.name))
            return
        total_frames = u32le(payload)
        node.fields.append(FieldInfo("dwTotalFrames", total_frames, offset + 8, 4, hex(total_frames), description="OpenDML 文件总帧数"))
        summary["open_dml"] = True
        summary["open_dml_total_frames"] = total_frames
        summary["total_frames"] = total_frames
        micro_sec_per_frame = summary.get("micro_sec_per_frame")
        if micro_sec_per_frame:
            summary["duration_seconds"] = total_frames * micro_sec_per_frame / 1_000_000

    def _parse_open_dml_index(
        self,
        source: ByteSource,
        node: ParseNode,
        offset: int,
        chunk_size: int,
        summary: dict,
        diagnostics: list,
    ) -> None:
        payload = source.read_at(offset + 8, min(chunk_size, 24))
        if len(payload) < 24:
            diagnostics.append(error(f"AVI OpenDML {node.name} index 长度不足", offset, self.name))
            return
        longs_per_entry = u16le(payload, 0)
        index_subtype = payload[2]
        index_type = payload[3]
        entries_in_use = u32le(payload, 4)
        chunk_id_bytes = payload[8:12]
        indexed_chunk_id = chunk_id_bytes.decode("ascii", errors="replace")
        index_type_name = {0: "AVI_INDEX_OF_INDEXES", 1: "AVI_INDEX_OF_CHUNKS"}.get(index_type, f"unknown({index_type})")
        node.node_type = "avi_super_index" if index_type == 0 else "avi_standard_index"
        node.fields.extend(
            [
                FieldInfo("wLongsPerEntry", longs_per_entry, offset + 8, 2, hex(longs_per_entry)),
                FieldInfo("bIndexSubType", index_subtype, offset + 10, 1, hex(index_subtype)),
                FieldInfo("bIndexType", index_type, offset + 11, 1, hex(index_type), description=index_type_name),
                FieldInfo("nEntriesInUse", entries_in_use, offset + 12, 4, hex(entries_in_use)),
                FieldInfo("dwChunkId", indexed_chunk_id, offset + 16, 4, chunk_id_bytes.hex(" ").upper()),
            ]
        )
        summary["open_dml"] = True
        if index_type == 0:
            summary["super_indexes"] = summary.get("super_indexes", 0) + 1
            self._parse_super_index_entries(source, node, offset, chunk_size, longs_per_entry, entries_in_use, diagnostics, summary)
        elif index_type == 1:
            summary["standard_indexes"] = summary.get("standard_indexes", 0) + 1
            self._parse_standard_index_entries(
                source, node, offset, chunk_size, longs_per_entry, index_subtype, entries_in_use, payload, diagnostics, summary
            )
        else:
            diagnostics.append(warn(f"AVI OpenDML index 类型不受支持：{index_type}", offset + 11, self.name))

    def _parse_super_index_entries(
        self,
        source: ByteSource,
        node: ParseNode,
        offset: int,
        chunk_size: int,
        longs_per_entry: int,
        entries_in_use: int,
        diagnostics: list,
        summary: dict,
    ) -> None:
        entry_size = longs_per_entry * 4
        if entry_size < 16:
            diagnostics.append(error("AVI OpenDML 超级索引 entry 长度无效", offset + 8, self.name))
            return
        count = self._available_index_entries(chunk_size, entry_size, entries_in_use, offset, diagnostics)
        summary["super_index_entries"] = summary.get("super_index_entries", 0) + count
        self._warn_if_index_nodes_limited(count, offset, diagnostics)
        for index in range(min(count, MAX_INDEX_ENTRY_NODES)):
            entry_offset = offset + 8 + 24 + index * entry_size
            data = source.read_at(entry_offset, entry_size)
            absolute_offset = int.from_bytes(data[0:8], "little")
            size = u32le(data, 8)
            duration = u32le(data, 12)
            child = node.add_child(ParseNode(f"SuperIndexEntry[{index}]", "avi_index_entry", entry_offset, entry_size))
            child.fields.extend(
                [
                    FieldInfo("qwOffset", absolute_offset, entry_offset, 8, hex(absolute_offset), description="标准索引绝对文件偏移"),
                    FieldInfo("dwSize", size, entry_offset + 8, 4, hex(size)),
                    FieldInfo("dwDuration", duration, entry_offset + 12, 4, hex(duration)),
                ]
            )

    def _parse_standard_index_entries(
        self,
        source: ByteSource,
        node: ParseNode,
        offset: int,
        chunk_size: int,
        longs_per_entry: int,
        index_subtype: int,
        entries_in_use: int,
        header: bytes,
        diagnostics: list,
        summary: dict,
    ) -> None:
        entry_size = longs_per_entry * 4
        minimum_size = 12 if index_subtype == 1 else 8
        if entry_size < minimum_size:
            diagnostics.append(error("AVI OpenDML 标准索引 entry 长度无效", offset + 8, self.name))
            return
        base_offset = int.from_bytes(header[12:20], "little")
        node.fields.extend(
            [
                FieldInfo("qwBaseOffset", base_offset, offset + 20, 8, hex(base_offset)),
                FieldInfo("dwReserved3", u32le(header, 20), offset + 28, 4, hex(u32le(header, 20))),
            ]
        )
        count = self._available_index_entries(chunk_size, entry_size, entries_in_use, offset, diagnostics)
        summary["standard_index_entries"] = summary.get("standard_index_entries", 0) + count
        self._warn_if_index_nodes_limited(count, offset, diagnostics)
        for index in range(min(count, MAX_INDEX_ENTRY_NODES)):
            entry_offset = offset + 8 + 24 + index * entry_size
            data = source.read_at(entry_offset, entry_size)
            relative_offset = u32le(data, 0)
            raw_size = u32le(data, 4)
            size = raw_size & 0x7FFFFFFF
            keyframe = not bool(raw_size & 0x80000000)
            absolute_offset = base_offset + relative_offset
            child = node.add_child(ParseNode(f"StandardIndexEntry[{index}]", "avi_index_entry", entry_offset, entry_size))
            child.fields.extend(
                [
                    FieldInfo("dwOffset", relative_offset, entry_offset, 4, hex(relative_offset)),
                    FieldInfo("absolute_offset", absolute_offset, entry_offset, 0, hex(absolute_offset)),
                    FieldInfo("dwSize", size, entry_offset + 4, 4, hex(raw_size)),
                    FieldInfo("keyframe", keyframe, entry_offset + 4, 0, description="dwSize 最高位为 0 时是关键帧"),
                ]
            )
            if index_subtype == 1 and entry_size >= 12:
                second_field_offset = u32le(data, 8)
                child.fields.append(
                    FieldInfo("dwOffsetField2", second_field_offset, entry_offset + 8, 4, hex(second_field_offset), description="第二场相对偏移")
                )

    def _available_index_entries(
        self,
        chunk_size: int,
        entry_size: int,
        entries_in_use: int,
        offset: int,
        diagnostics: list,
    ) -> int:
        available = max(0, chunk_size - 24) // entry_size
        if entries_in_use > available:
            diagnostics.append(error("AVI OpenDML index 条目数超过 chunk 边界", offset + 12, self.name))
        return min(entries_in_use, available)

    def _warn_if_index_nodes_limited(self, count: int, offset: int, diagnostics: list) -> None:
        if count > MAX_INDEX_ENTRY_NODES:
            diagnostics.append(
                warn(f"AVI OpenDML index 含 {count} 个条目，仅展开前 {MAX_INDEX_ENTRY_NODES} 个节点", offset, self.name)
            )
