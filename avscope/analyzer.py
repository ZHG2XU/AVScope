from __future__ import annotations

from pathlib import Path

from avscope.byte_source import ByteSource
from avscope.ffprobe import probe_media, probe_packet_timeline
from avscope.frame_stats import build_frame_stats
from avscope.models import DiagnosticIssue, MediaInfo, ParseNode, ParseResult, Severity
from avscope.packet_stats import build_packet_stats
from avscope.plugins import load_plugin_parsers
from avscope.timeline_viz import build_timeline_summary
from avscope.waveform import build_waveform_summary
from avscope.parsers import DEFAULT_PARSERS
from avscope.parsers.base import FormatParser


class Analyzer:
    def __init__(self, parsers: list[FormatParser] | None = None):
        self.parsers = parsers if parsers is not None else [*DEFAULT_PARSERS, *load_plugin_parsers()]

    def analyze(self, path: str | Path, options: dict | None = None) -> ParseResult:
        with ByteSource(path) as source:
            parser = self._select_parser(source)
            if parser is None:
                return self._unknown_result(source)
            try:
                result = parser.parse(source, options or {})
                self._attach_frame_stats(result)
                self._attach_ffprobe(result)
                self._attach_timeline_summary(result)
                return result
            except Exception as exc:
                root = ParseNode(Path(path).name, "Parse Error", 0, source.size, severity=Severity.ERROR)
                issue = DiagnosticIssue(Severity.ERROR, f"解析失败：{exc}", 0, parser.name)
                return ParseResult(MediaInfo(str(path), source.size, parser.name), root, diagnostics=[issue])

    def _select_parser(self, source: ByteSource) -> FormatParser | None:
        extension_matches = [p for p in self.parsers if p.extension_matches(source.path)]
        ordered = extension_matches + [p for p in self.parsers if p not in extension_matches]
        for parser in ordered:
            try:
                if parser.probe(source):
                    return parser
            except Exception:
                continue
        return None

    def _unknown_result(self, source: ByteSource) -> ParseResult:
        root = ParseNode(source.path.name, "Unknown", 0, source.size, severity=Severity.WARNING)
        issue = DiagnosticIssue(Severity.WARNING, "无法识别文件格式，可作为只读 Hex 文件查看", 0, "probe")
        result = ParseResult(MediaInfo(str(source.path), source.size, "Unknown"), root, diagnostics=[issue])
        self._attach_ffprobe(result)
        self._attach_timeline_summary(result)
        return result

    def _attach_frame_stats(self, result: ParseResult) -> None:
        stats = build_frame_stats(result.frames)
        if stats.get("available"):
            result.media.summary["frame_stats"] = stats

    def _attach_ffprobe(self, result: ParseResult) -> None:
        suffix = Path(result.media.path).suffix.lower()
        if suffix not in {".pcm", ".yuv"}:
            result.media.summary["ffprobe"] = probe_media(result.media.path)
            result.media.summary["packet_timeline"] = probe_packet_timeline(result.media.path)
            packet_stats = build_packet_stats(result.media.summary["packet_timeline"])
            if packet_stats.get("available"):
                result.media.summary["packet_stats"] = packet_stats
            result.diagnostics.extend(build_timeline_diagnostics(result.media.summary))
        if suffix in {".wav", ".pcm"} or result.media.format_name in {"WAV", "Raw PCM"}:
            result.media.summary["waveform"] = build_waveform_summary(
                result.media.path,
                result.media.format_name,
                result.media.summary,
            )

    def _attach_timeline_summary(self, result: ParseResult) -> None:
        packets = result.media.summary.get("packet_timeline", {}).get("packets", [])
        summary = build_timeline_summary(result.frames, packets)
        if summary.get("available"):
            result.media.summary["timeline_summary"] = summary


def build_timeline_diagnostics(summary: dict, tolerance: float = 0.000001) -> list[DiagnosticIssue]:
    diagnostics: list[DiagnosticIssue] = []
    diagnostics.extend(build_probe_diagnostics(summary))
    diagnostics.extend(_packet_monotonic_diagnostics(summary.get("packet_timeline", {}), tolerance))
    diagnostics.extend(_stream_duration_diagnostics(summary.get("ffprobe", {})))
    diagnostics.extend(_size_spike_diagnostics(summary))
    return diagnostics


def build_probe_diagnostics(summary: dict) -> list[DiagnosticIssue]:
    diagnostics: list[DiagnosticIssue] = []
    seen: set[tuple[str, str]] = set()
    for key, label in (("ffprobe", "ffprobe 媒体流探测"), ("packet_timeline", "ffprobe packet 时间线探测")):
        section = summary.get(key, {})
        message = str(section.get("error") or "").strip()
        if not message:
            continue
        marker = (key, message)
        if marker in seen:
            continue
        diagnostics.append(DiagnosticIssue(Severity.WARNING, f"{label}失败：{message}", None, "ffprobe"))
        seen.add(marker)
    return diagnostics


def _packet_monotonic_diagnostics(packet_timeline: dict, tolerance: float) -> list[DiagnosticIssue]:
    diagnostics: list[DiagnosticIssue] = []
    last_by_stream: dict[object, dict[str, float]] = {}
    reported: set[tuple[object, str]] = set()
    for packet in packet_timeline.get("packets", []):
        stream = packet.get("stream_index")
        values = last_by_stream.setdefault(stream, {})
        for key in ("pts", "dts"):
            current = packet.get(key)
            previous = values.get(key)
            if current is None:
                continue
            if previous is not None and current + tolerance < previous and (stream, key) not in reported:
                label = key.upper()
                diagnostics.append(
                    DiagnosticIssue(
                        Severity.WARNING,
                        f"{label} 非单调: stream={stream} packet={packet.get('index')} previous={previous} current={current}",
                        packet.get("pos"),
                        "timeline",
                    )
                )
                reported.add((stream, key))
            values[key] = current
    return diagnostics


def _stream_duration_diagnostics(ffprobe: dict, tolerance: float = 0.5) -> list[DiagnosticIssue]:
    if not ffprobe.get("available"):
        return []
    audio = []
    video = []
    for stream in ffprobe.get("streams", []):
        duration = _float_or_none(stream.get("duration"))
        if duration is None:
            continue
        if stream.get("codec_type") == "audio":
            audio.append(duration)
        elif stream.get("codec_type") == "video":
            video.append(duration)
    if not audio or not video:
        return []
    audio_duration = max(audio)
    video_duration = max(video)
    delta = abs(audio_duration - video_duration)
    if delta <= tolerance:
        return []
    return [
        DiagnosticIssue(
            Severity.WARNING,
            f"音视频时长差异: audio={audio_duration:.3f}s video={video_duration:.3f}s delta={delta:.3f}s",
            None,
            "timeline",
        )
    ]


def _size_spike_diagnostics(summary: dict, ratio: float = 4.0, minimum_items: int = 3) -> list[DiagnosticIssue]:
    diagnostics: list[DiagnosticIssue] = []
    frame_stats = summary.get("frame_stats", {})
    if _has_size_spike(frame_stats, "frames", ratio, minimum_items):
        diagnostics.append(
            DiagnosticIssue(
                Severity.WARNING,
                (
                    "帧大小尖峰 "
                    f"frame=#{frame_stats.get('largest_index')} "
                    f"max={frame_stats.get('largest_size', frame_stats.get('max_size'))} bytes "
                    f"average={frame_stats.get('average_size')} bytes"
                ),
                frame_stats.get("largest_offset"),
                "timeline",
            )
        )

    packet_stats = summary.get("packet_stats", {})
    if not packet_stats.get("available"):
        return diagnostics
    for stream, item in packet_stats.get("by_stream", {}).items():
        if not _has_size_spike(item, "packets", ratio, minimum_items):
            continue
        diagnostics.append(
            DiagnosticIssue(
                Severity.WARNING,
                (
                    "Packet 大小尖峰 "
                    f"stream={stream} "
                    f"packet={item.get('largest_index')} "
                    f"max={item.get('largest_size', item.get('max_size'))} bytes "
                    f"average={item.get('average_size')} bytes"
                ),
                item.get("largest_pos"),
                "timeline",
            )
        )
    return diagnostics


def _has_size_spike(stats: dict, count_key: str, ratio: float, minimum_items: int) -> bool:
    if not stats.get("available", True):
        return False
    try:
        count = int(stats.get(count_key, 0) or 0)
        average_size = float(stats.get("average_size", 0) or 0)
        max_size = float(stats.get("max_size", stats.get("largest_size", 0)) or 0)
    except (TypeError, ValueError):
        return False
    return count >= minimum_items and average_size > 0 and max_size >= average_size * ratio


def _float_or_none(value) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
