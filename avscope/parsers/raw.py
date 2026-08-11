from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, ParseResult
from avscope.parsers.base import FormatParser
from avscope.parsers.common import media_info, root_node


class RawPcmParser(FormatParser):
    name = "Raw PCM"
    extensions = (".pcm",)

    def probe(self, source: ByteSource) -> bool:
        return self.extension_matches(source.path)

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        opts = options or {}
        sample_rate = int(opts.get("sample_rate", 48000))
        channels = int(opts.get("channels", 2))
        bits_per_sample = int(opts.get("bits_per_sample", 16))
        root = root_node(source, self.name)
        frame_bytes = max(1, channels * bits_per_sample // 8)
        samples = source.size // frame_bytes
        duration = samples / sample_rate if sample_rate else None
        root.fields.extend(
            [
                FieldInfo("sample_rate", sample_rate),
                FieldInfo("channels", channels),
                FieldInfo("bits_per_sample", bits_per_sample),
                FieldInfo("samples_per_channel", samples),
                FieldInfo("duration_seconds", duration),
            ]
        )
        return ParseResult(
            media_info(
                source,
                self.name,
                sample_rate=sample_rate,
                channels=channels,
                bits_per_sample=bits_per_sample,
                samples_per_channel=samples,
                duration=duration,
            ),
            root,
        )


class RawYuvParser(FormatParser):
    name = "Raw YUV"
    extensions = (".yuv",)

    def probe(self, source: ByteSource) -> bool:
        return self.extension_matches(source.path)

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        opts = options or {}
        width = int(opts.get("width", 1920))
        height = int(opts.get("height", 1080))
        pixel_format = str(opts.get("pixel_format", "yuv420p"))
        fps = float(opts.get("fps", 25))
        bytes_per_frame = int(width * height * 1.5) if pixel_format.lower() in {"yuv420p", "nv12", "nv21"} else width * height * 2
        frame_count = source.size // max(1, bytes_per_frame)
        root = root_node(source, self.name)
        root.fields.extend(
            [
                FieldInfo("width", width),
                FieldInfo("height", height),
                FieldInfo("pixel_format", pixel_format),
                FieldInfo("fps", fps),
                FieldInfo("bytes_per_frame", bytes_per_frame),
                FieldInfo("frame_count", frame_count),
            ]
        )
        duration = frame_count / fps if fps else None
        return ParseResult(
            media_info(
                source,
                self.name,
                width=width,
                height=height,
                pixel_format=pixel_format,
                fps=fps,
                bytes_per_frame=bytes_per_frame,
                frames=frame_count,
                duration=duration,
            ),
            root,
        )
