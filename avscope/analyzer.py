from __future__ import annotations

from pathlib import Path

from avscope.byte_source import ByteSource
from avscope.ffprobe import probe_media, probe_packet_timeline
from avscope.models import DiagnosticIssue, MediaInfo, ParseNode, ParseResult, Severity
from avscope.waveform import build_waveform_summary
from avscope.parsers import DEFAULT_PARSERS
from avscope.parsers.base import FormatParser


class Analyzer:
    def __init__(self, parsers: list[FormatParser] | None = None):
        self.parsers = parsers or DEFAULT_PARSERS

    def analyze(self, path: str | Path, options: dict | None = None) -> ParseResult:
        with ByteSource(path) as source:
            parser = self._select_parser(source)
            if parser is None:
                return self._unknown_result(source)
            try:
                result = parser.parse(source, options or {})
                self._attach_ffprobe(result)
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
        return result

    def _attach_ffprobe(self, result: ParseResult) -> None:
        suffix = Path(result.media.path).suffix.lower()
        if suffix not in {".pcm", ".yuv"}:
            result.media.summary["ffprobe"] = probe_media(result.media.path)
            result.media.summary["packet_timeline"] = probe_packet_timeline(result.media.path)
        if suffix in {".wav", ".pcm"} or result.media.format_name in {"WAV", "Raw PCM"}:
            result.media.summary["waveform"] = build_waveform_summary(
                result.media.path,
                result.media.format_name,
                result.media.summary,
            )
