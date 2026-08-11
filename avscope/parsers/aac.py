from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, FrameInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, warn


SAMPLE_RATES = {
    0: 96000,
    1: 88200,
    2: 64000,
    3: 48000,
    4: 44100,
    5: 32000,
    6: 24000,
    7: 22050,
    8: 16000,
    9: 12000,
    10: 11025,
    11: 8000,
    12: 7350,
}


class AacAdtsParser(FormatParser):
    name = "AAC ADTS"
    extensions = (".aac",)

    def probe(self, source: ByteSource) -> bool:
        head = source.head(2)
        return len(head) == 2 and head[0] == 0xFF and (head[1] & 0xF0) == 0xF0

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        frames: list[FrameInfo] = []
        diagnostics = []
        offset = 0
        index = 0
        first_sample_rate = None
        first_channels = None
        while offset + 7 <= source.size and index < 20000:
            header = source.read_at(offset, 9)
            if len(header) < 7:
                break
            if header[0] != 0xFF or (header[1] & 0xF0) != 0xF0:
                diagnostics.append(error("AAC syncword 错误", offset, self.name))
                break

            protection_absent = header[1] & 0x01
            profile = (header[2] >> 6) & 0x03
            sf_index = (header[2] >> 2) & 0x0F
            channels = ((header[2] & 0x01) << 2) | ((header[3] >> 6) & 0x03)
            frame_length = ((header[3] & 0x03) << 11) | (header[4] << 3) | ((header[5] >> 5) & 0x07)
            fullness = ((header[5] & 0x1F) << 6) | ((header[6] >> 2) & 0x3F)
            blocks = header[6] & 0x03
            header_size = 7 if protection_absent else 9

            if frame_length < header_size:
                diagnostics.append(error("AAC frame_length 小于 header 长度", offset, self.name))
                break
            if offset + frame_length > source.size:
                diagnostics.append(warn("最后一个 AAC frame 被截断", offset, self.name))
                frame_length = source.size - offset

            sample_rate = SAMPLE_RATES.get(sf_index)
            if sample_rate is None:
                diagnostics.append(warn("AAC sampling_frequency_index 为保留值", offset + 2, self.name))
            if first_sample_rate is None:
                first_sample_rate = sample_rate
                first_channels = channels

            node = root.add_child(ParseNode(f"Frame[{index}]", "aac_frame", offset, frame_length))
            node.fields.extend(
                [
                    FieldInfo("syncword", "0xFFF", offset, 2, "FF F?"),
                    FieldInfo("profile", profile + 1, offset + 2, 1, description="Audio Object Type = profile + 1"),
                    FieldInfo("sampling_frequency_index", sf_index, offset + 2, 1, description=str(sample_rate or "reserved")),
                    FieldInfo("channel_configuration", channels, offset + 2, 2),
                    FieldInfo("frame_length", frame_length, offset + 3, 3),
                    FieldInfo("adts_buffer_fullness", fullness, offset + 5, 2),
                    FieldInfo("number_of_raw_data_blocks", blocks, offset + 6, 1),
                ]
            )
            frames.append(
                FrameInfo(
                    index=index,
                    offset=offset,
                    size=frame_length,
                    duration=(1024 * (blocks + 1) / sample_rate) if sample_rate else None,
                    frame_type="AAC",
                )
            )
            offset += frame_length
            index += 1

        if not frames:
            diagnostics.append(error("未解析到 AAC ADTS frame", 0, self.name))
        if offset < source.size and frames:
            diagnostics.append(warn("AAC 文件尾部存在未解析字节", offset, self.name))
        summary = {"frames": len(frames), "sample_rate": first_sample_rate, "channels": first_channels}
        return ParseResult(media_info(source, self.name, **summary), root, frames, diagnostics)
