from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, u16le, u32le, warn


WAVE_FORMATS = {
    0x0001: "PCM",
    0x0003: "IEEE float",
    0x0006: "A-law",
    0x0007: "mu-law",
    0xFFFE: "Extensible",
}


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
        root.fields.extend(
            [
                FieldInfo("riff_id", "RIFF", 0, 4, "52 49 46 46"),
                FieldInfo("riff_size", riff_size, 4, 4, hex(riff_size), description="RIFF 声明的总长度"),
                FieldInfo("wave_id", "WAVE", 8, 4, "57 41 56 45"),
            ]
        )
        if riff_size > source.size:
            diagnostics.append(warn("RIFF 声明长度超过文件实际长度", 4, self.name))
        elif riff_size < source.size:
            diagnostics.append(warn("RIFF 声明长度小于文件实际长度，尾部可能存在附加数据", riff_size, self.name))

        offset = 12
        fmt_seen = False
        data_seen = False
        audio_summary: dict = {}
        fmt_values: dict = {}
        data_bytes = 0
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
                fmt_values = self._parse_fmt_chunk(source, node, offset, chunk_size, diagnostics)
                audio_summary.update(fmt_values)
            elif chunk_id == "data":
                data_seen = True
                data_bytes += chunk_size
                node.fields.append(FieldInfo("data_bytes", chunk_size, offset + 8, chunk_size, description="音频数据字节数"))
            offset += total_size

        if fmt_values and data_bytes:
            derived = _derive_audio_metrics(fmt_values, data_bytes)
            audio_summary.update(derived)
            if fmt_values.get("byte_rate") and derived.get("expected_byte_rate") != fmt_values.get("byte_rate"):
                diagnostics.append(warn("WAV byte_rate 与格式字段推导值不一致", 0, self.name))
            if fmt_values.get("block_align") and derived.get("expected_block_align") != fmt_values.get("block_align"):
                diagnostics.append(warn("WAV block_align 与格式字段推导值不一致", 0, self.name))
        if not fmt_seen:
            diagnostics.append(error("未发现 fmt chunk", 0, self.name))
        if not data_seen:
            diagnostics.append(error("未发现 data chunk", 0, self.name))
        return ParseResult(media_info(source, self.name, chunks=len(root.children), **audio_summary), root, diagnostics=diagnostics)

    def _parse_fmt_chunk(self, source: ByteSource, node: ParseNode, offset: int, chunk_size: int, diagnostics: list) -> dict:
        payload = source.read_at(offset + 8, min(chunk_size, 64))
        if len(payload) < 16:
            node.severity = Severity.WARNING
            diagnostics.append(error("fmt chunk 长度不足 16 字节", offset, self.name))
            return {}
        audio_format = u16le(payload, 0)
        channels = u16le(payload, 2)
        sample_rate = u32le(payload, 4)
        byte_rate = u32le(payload, 8)
        block_align = u16le(payload, 12)
        bits_per_sample = u16le(payload, 14)
        fmt_name = WAVE_FORMATS.get(audio_format, f"0x{audio_format:04X}")
        node.fields.extend(
            [
                FieldInfo("audio_format", audio_format, offset + 8, 2, hex(audio_format), description=fmt_name),
                FieldInfo("format_name", fmt_name, offset + 8, 2),
                FieldInfo("channels", channels, offset + 10, 2),
                FieldInfo("sample_rate", sample_rate, offset + 12, 4),
                FieldInfo("byte_rate", byte_rate, offset + 16, 4),
                FieldInfo("block_align", block_align, offset + 20, 2),
                FieldInfo("bits_per_sample", bits_per_sample, offset + 22, 2),
            ]
        )
        if audio_format != 1:
            diagnostics.append(warn(f"WAV format 为 {fmt_name}，当前仅对 PCM 做完整派生校验", offset + 8, self.name))
        return {
            "audio_format": audio_format,
            "wave_format_name": fmt_name,
            "channels": channels,
            "sample_rate": sample_rate,
            "byte_rate": byte_rate,
            "block_align": block_align,
            "bits_per_sample": bits_per_sample,
        }


def _derive_audio_metrics(fmt: dict, data_bytes: int) -> dict:
    channels = int(fmt.get("channels") or 0)
    sample_rate = int(fmt.get("sample_rate") or 0)
    bits_per_sample = int(fmt.get("bits_per_sample") or 0)
    bytes_per_sample = bits_per_sample // 8 if bits_per_sample else 0
    expected_block_align = channels * bytes_per_sample if channels and bytes_per_sample else None
    expected_byte_rate = sample_rate * expected_block_align if sample_rate and expected_block_align else None
    frame_count = data_bytes // expected_block_align if expected_block_align else None
    duration_seconds = frame_count / sample_rate if frame_count is not None and sample_rate else None
    return {
        "data_bytes": data_bytes,
        "expected_block_align": expected_block_align,
        "expected_byte_rate": expected_byte_rate,
        "frame_count": frame_count,
        "duration_seconds": duration_seconds,
    }
