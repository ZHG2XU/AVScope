from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, FrameInfo, ParseNode, ParseResult
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

AAC_PROFILE_NAMES = {
    1: "AAC Main",
    2: "AAC LC",
    3: "AAC SSR",
    4: "AAC LTP",
}

CHANNEL_CONFIGS = {
    0: "defined in AOT Specific Config",
    1: "mono",
    2: "stereo",
    3: "3 channels",
    4: "4 channels",
    5: "5 channels",
    6: "5.1 channels",
    7: "7.1 channels",
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
        first_profile = None
        total_audio_units = 0
        total_payload_bytes = 0
        while offset + 7 <= source.size and index < 20000:
            header = source.read_at(offset, 9)
            if len(header) < 7:
                break
            if header[0] != 0xFF or (header[1] & 0xF0) != 0xF0:
                diagnostics.append(error("AAC syncword 错误", offset, self.name))
                break

            mpeg_version_id = (header[1] >> 3) & 0x01
            layer = (header[1] >> 1) & 0x03
            protection_absent = header[1] & 0x01
            profile_raw = (header[2] >> 6) & 0x03
            audio_object_type = profile_raw + 1
            sf_index = (header[2] >> 2) & 0x0F
            private_bit = (header[2] >> 1) & 0x01
            channels = ((header[2] & 0x01) << 2) | ((header[3] >> 6) & 0x03)
            original_copy = (header[3] >> 5) & 0x01
            home = (header[3] >> 4) & 0x01
            frame_length = ((header[3] & 0x03) << 11) | (header[4] << 3) | ((header[5] >> 5) & 0x07)
            fullness = ((header[5] & 0x1F) << 6) | ((header[6] >> 2) & 0x3F)
            blocks = header[6] & 0x03
            raw_blocks = blocks + 1
            samples_per_frame = raw_blocks * 1024
            header_size = 7 if protection_absent else 9

            if layer != 0:
                diagnostics.append(warn("AAC ADTS layer 字段应为 0", offset + 1, self.name))
            if frame_length < header_size:
                diagnostics.append(error("AAC frame_length 小于 header 长度", offset, self.name))
                break
            if offset + frame_length > source.size:
                diagnostics.append(warn("最后一个 AAC frame 被截断", offset, self.name))
                frame_length = source.size - offset

            sample_rate = SAMPLE_RATES.get(sf_index)
            if sample_rate is None:
                diagnostics.append(warn("AAC sampling_frequency_index 为保留值", offset + 2, self.name))
            if channels == 0:
                diagnostics.append(warn("AAC channel_configuration 为 0，需要额外配置描述声道布局", offset + 2, self.name))
            if first_sample_rate is None:
                first_sample_rate = sample_rate
                first_channels = channels
                first_profile = AAC_PROFILE_NAMES.get(audio_object_type, f"AOT {audio_object_type}")
            elif sample_rate != first_sample_rate:
                diagnostics.append(warn("AAC 采样率在文件中发生变化", offset + 2, self.name))

            duration = samples_per_frame / sample_rate if sample_rate else None
            payload_bytes = max(0, frame_length - header_size)
            total_audio_units += samples_per_frame
            total_payload_bytes += payload_bytes

            node = root.add_child(ParseNode(f"Frame[{index}]", "aac_frame", offset, frame_length))
            node.fields.extend(
                [
                    _adts_field(offset, "syncword", "0xFFF", 0, 12, 0, 2, "FF F?", "ADTS 同步字"),
                    _adts_field(offset, "mpeg_version_id", mpeg_version_id, 12, 1, 1, 1, description="0=MPEG-4, 1=MPEG-2"),
                    _adts_field(offset, "layer", layer, 13, 2, 1, 1, description="固定为 0"),
                    _adts_field(offset, "protection_absent", protection_absent, 15, 1, 1, 1, description="1=无 CRC"),
                    _adts_field(offset, "profile", audio_object_type, 16, 2, 2, 1, description=AAC_PROFILE_NAMES.get(audio_object_type, "reserved")),
                    _adts_field(offset, "sampling_frequency_index", sf_index, 18, 4, 2, 1, description=str(sample_rate or "reserved")),
                    _adts_field(offset, "sample_rate", sample_rate, 18, 4, 2, 1, description="由 sampling_frequency_index 推导"),
                    _adts_field(offset, "private_bit", private_bit, 22, 1, 2, 1),
                    _adts_field(offset, "channel_configuration", channels, 23, 3, 2, 2, description=CHANNEL_CONFIGS.get(channels, "reserved")),
                    _adts_field(offset, "original_copy", original_copy, 26, 1, 3, 1),
                    _adts_field(offset, "home", home, 27, 1, 3, 1),
                    _adts_field(offset, "frame_length", frame_length, 30, 13, 3, 3, description="ADTS header + raw data 长度"),
                    FieldInfo("payload_bytes", payload_bytes, offset + header_size, payload_bytes),
                    _adts_field(offset, "adts_buffer_fullness", fullness, 43, 11, 5, 2),
                    _adts_field(offset, "number_of_raw_data_blocks", blocks, 54, 2, 6, 1),
                    _adts_field(offset, "samples_per_frame", samples_per_frame, 54, 2, 6, 1),
                    FieldInfo("duration_seconds", duration, offset + 6, 0),
                ]
            )
            frames.append(
                FrameInfo(
                    index=index,
                    offset=offset,
                    size=frame_length,
                    duration=duration,
                    frame_type=AAC_PROFILE_NAMES.get(audio_object_type, "AAC"),
                )
            )
            offset += frame_length
            index += 1

        if not frames:
            diagnostics.append(error("未解析到 AAC ADTS frame", 0, self.name))
        if offset < source.size and frames:
            diagnostics.append(warn("AAC 文件尾部存在未解析字节", offset, self.name))
        duration_seconds = total_audio_units / first_sample_rate if first_sample_rate else None
        average_bitrate = int(source.size * 8 / duration_seconds) if duration_seconds else None
        summary = {
            "frames": len(frames),
            "sample_rate": first_sample_rate,
            "channels": first_channels,
            "channel_layout": CHANNEL_CONFIGS.get(first_channels, "unknown") if first_channels is not None else None,
            "profile": first_profile,
            "duration_seconds": duration_seconds,
            "average_bitrate": average_bitrate,
            "payload_bytes": total_payload_bytes,
        }
        return ParseResult(media_info(source, self.name, **summary), root, frames, diagnostics)


def _adts_field(
    frame_offset: int,
    name: str,
    value,
    bit_offset: int,
    bit_length: int,
    byte_offset: int,
    byte_size: int,
    hex_value: str = "",
    description: str = "",
) -> FieldInfo:
    return FieldInfo(
        name,
        value,
        frame_offset + byte_offset,
        byte_size,
        hex_value,
        bit_offset=frame_offset * 8 + bit_offset,
        bit_length=bit_length,
        description=description,
    )
