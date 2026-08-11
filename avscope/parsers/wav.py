from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, ParseNode, ParseResult
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, u16le, u32le, warn


class WavParser(FormatParser):
    name = "WAV"
    extensions = (".wav",)

    def probe(self, source: ByteSource) -> bool:
        head = source.head(12)
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        diagnostics = []
        head = source.head(12)
        riff_size = u32le(head, 4) + 8 if len(head) >= 8 else 0
        root.fields.append(FieldInfo("riff_size", riff_size, 4, 4, hex(riff_size)))
        if riff_size > source.size:
            diagnostics.append(warn("RIFF 声明长度超过文件实际长度", 4, self.name))
        offset = 12
        fmt_seen = False
        data_seen = False
        audio_summary = {}
        while offset + 8 <= source.size:
            header = source.read_at(offset, 8)
            chunk_id = header[:4].decode("ascii", errors="replace")
            chunk_size = u32le(header, 4)
            total_size = 8 + chunk_size + (chunk_size & 1)
            node = root.add_child(ParseNode(chunk_id, "riff_chunk", offset, total_size))
            node.fields.extend(
                [
                    FieldInfo("chunk_id", chunk_id, offset, 4, header[:4].hex(" ").upper()),
                    FieldInfo("chunk_size", chunk_size, offset + 4, 4, hex(chunk_size)),
                ]
            )
            if offset + total_size > source.size:
                diagnostics.append(error(f"{chunk_id} chunk 超出文件边界", offset, self.name))
                break
            if chunk_id == "fmt ":
                fmt_seen = True
                payload = source.read_at(offset + 8, min(chunk_size, 40))
                if len(payload) >= 16:
                    audio_format = u16le(payload, 0)
                    channels = u16le(payload, 2)
                    sample_rate = u32le(payload, 4)
                    byte_rate = u32le(payload, 8)
                    block_align = u16le(payload, 12)
                    bits_per_sample = u16le(payload, 14)
                    audio_summary.update(
                        {
                            "audio_format": audio_format,
                            "channels": channels,
                            "sample_rate": sample_rate,
                            "bits_per_sample": bits_per_sample,
                        }
                    )
                    node.fields.extend(
                        [
                            FieldInfo("audio_format", audio_format, offset + 8, 2, hex(audio_format)),
                            FieldInfo("channels", channels, offset + 10, 2),
                            FieldInfo("sample_rate", sample_rate, offset + 12, 4),
                            FieldInfo("byte_rate", byte_rate, offset + 16, 4),
                            FieldInfo("block_align", block_align, offset + 20, 2),
                            FieldInfo("bits_per_sample", bits_per_sample, offset + 22, 2),
                        ]
                    )
            elif chunk_id == "data":
                data_seen = True
            offset += total_size

        if not fmt_seen:
            diagnostics.append(error("未发现 fmt chunk", 0, self.name))
        if not data_seen:
            diagnostics.append(error("未发现 data chunk", 0, self.name))
        return ParseResult(media_info(source, self.name, chunks=len(root.children), **audio_summary), root, diagnostics=diagnostics)
