from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from avscope.analyzer import Analyzer
from avscope.cli import main as cli_main
from avscope.compare import compare_binary, compare_protocol, format_protocol_compare
from avscope.report import export_html, export_json
from avscope.samples import generate_samples
from avscope.search import find_pattern, parse_search_pattern
from avscope.settings import AppSettings, MAX_RECENT_FILES


ROOT = Path("G:/AVScope/tmp/testdata")


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class ParserTests(unittest.TestCase):
    def setUp(self):
        ROOT.mkdir(parents=True, exist_ok=True)
        self.analyzer = Analyzer()

    def test_wav_parser(self):
        pcm = b"\x00\x00" * 16
        fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
        data = b"data" + struct.pack("<I", len(pcm)) + pcm
        wav = b"RIFF" + struct.pack("<I", 4 + len(fmt) + len(data)) + b"WAVE" + fmt + data
        result = self.analyzer.analyze(write(ROOT / "ok.wav", wav))
        self.assertEqual(result.media.format_name, "WAV")
        self.assertEqual(result.media.summary["sample_rate"], 8000)
        self.assertIn("ffprobe", result.media.summary)
        self.assertIn("packet_timeline", result.media.summary)
        self.assertTrue(result.media.summary["waveform"]["available"])
        self.assertFalse([i for i in result.diagnostics if i.severity.value == "error"])

    def test_aac_parser(self):
        frame = bytes([0xFF, 0xF1, 0x50, 0x80, 0x01, 0x9F, 0xFC]) + b"\x00" * 5
        result = self.analyzer.analyze(write(ROOT / "ok.aac", frame * 3))
        self.assertEqual(result.media.format_name, "AAC ADTS")
        self.assertEqual(result.media.summary["frames"], 3)

    def test_h264_parser(self):
        data = b"\x00\x00\x00\x01\x67\x64\x00\x1f" + b"\x00\x00\x01\x68\xee" + b"\x00\x00\x01\x65\x88"
        result = self.analyzer.analyze(write(ROOT / "ok.h264", data))
        self.assertEqual(result.media.format_name, "H.264 Annex-B")
        self.assertGreaterEqual(result.media.summary["nalu_count"], 3)

    def test_mp4_parser_and_reports(self):
        ftyp_payload = b"isom" + struct.pack(">I", 0) + b"isomiso2"
        ftyp = struct.pack(">I4s", len(ftyp_payload) + 8, b"ftyp") + ftyp_payload
        mdat = struct.pack(">I4s", 12, b"mdat") + b"\x00\x01\x02\x03"
        result = self.analyzer.analyze(write(ROOT / "ok.mp4", ftyp + mdat))
        self.assertEqual(result.media.format_name, "MP4/MOV")
        self.assertEqual(len(result.root.children), 2)
        html_path = ROOT / "report.html"
        json_path = ROOT / "report.json"
        export_html(result, html_path)
        export_json(result, json_path)
        self.assertIn("AVScope", html_path.read_text(encoding="utf-8"))
        self.assertIn("媒体摘要", html_path.read_text(encoding="utf-8"))
        self.assertIn("MP4/MOV", json_path.read_text(encoding="utf-8"))

    def test_binary_compare(self):
        left = write(ROOT / "left.bin", b"abc123")
        right = write(ROOT / "right.bin", b"abc923")
        result = compare_binary(left, right)
        self.assertFalse(result.equal)
        self.assertEqual(result.chunks[0].offset, 3)

    def test_protocol_compare(self):
        left = write(ROOT / "left_proto.mp4", b"\x00\x00\x00\x0Cftypisom")
        right = write(ROOT / "right_proto.mp4", b"\x00\x00\x00\x0Cftypisom\x00\x00\x00\x08free")
        result = compare_protocol(left, right)
        self.assertTrue(result["added"])
        text = format_protocol_compare(result)
        self.assertIn("协议结构对比", text)
        self.assertIn("新增节点", text)

    def test_protocol_compare_field_changes(self):
        def wav_bytes(sample_rate: int) -> bytes:
            pcm = b"\x00\x00" * 16
            fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
            data = b"data" + struct.pack("<I", len(pcm)) + pcm
            return b"RIFF" + struct.pack("<I", 4 + len(fmt) + len(data)) + b"WAVE" + fmt + data

        left = write(ROOT / "left_field.wav", wav_bytes(8000))
        right = write(ROOT / "right_field.wav", wav_bytes(16000))
        result = compare_protocol(left, right)
        changed_text = json.dumps(result["changed"], ensure_ascii=False)
        self.assertIn("sample_rate", changed_text)

    def test_samples_and_cli(self):
        sample_dir = ROOT / "samples"
        files = generate_samples(sample_dir)
        self.assertGreaterEqual(len(files), 6)
        html_path = ROOT / "cli_report.html"
        json_path = ROOT / "cli_report.json"
        exit_code = cli_main(["analyze", str(sample_dir / "sample.wav"), "--html", str(html_path), "--json", str(json_path)])
        self.assertEqual(exit_code, 0)
        self.assertTrue(html_path.exists())
        self.assertTrue(json_path.exists())
        protocol_path = ROOT / "protocol_compare.json"
        exit_code = cli_main(
            [
                "compare-protocol",
                str(sample_dir / "sample.mp4"),
                str(sample_dir / "sample_changed.mp4"),
                "--json",
                str(protocol_path),
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("changed", protocol_path.read_text(encoding="utf-8"))

    def test_ui_text_is_not_mojibake(self):
        bad_fragments = ["锛", "鎵", "鏃", "鍗", "璇", "濯", "鈥", "鈹", "�"]
        for source_path in [Path("G:/AVScope/avscope/app.py"), Path("G:/AVScope/avscope/report.py")]:
            text = source_path.read_text(encoding="utf-8")
            for fragment in bad_fragments:
                self.assertNotIn(fragment, text, f"{source_path} contains mojibake fragment {fragment}")

    def test_search_helpers(self):
        target = write(ROOT / "search.bin", b"\x00\x01hello\xFF\xF1world")
        self.assertEqual(parse_search_pattern("FF F1", "hex"), b"\xFF\xF1")
        self.assertEqual(parse_search_pattern("hello", "text"), b"hello")
        self.assertEqual(find_pattern(target, b"hello", 0, chunk_size=4), 2)
        self.assertEqual(find_pattern(target, b"\xFF\xF1", 0, chunk_size=8), 7)
        self.assertIsNone(find_pattern(target, b"missing", 0, chunk_size=4))

    def test_recent_file_settings(self):
        settings_path = ROOT / "settings.json"
        settings = AppSettings(settings_path)
        for index in range(MAX_RECENT_FILES + 3):
            settings.add_recent_file(ROOT / f"file_{index}.wav")
        settings.add_recent_file(ROOT / "file_3.wav")
        recent = settings.recent_files()
        self.assertEqual(recent[0], str(ROOT / "file_3.wav"))
        self.assertLessEqual(len(recent), MAX_RECENT_FILES)
        settings_reloaded = AppSettings(settings_path)
        self.assertEqual(settings_reloaded.recent_files()[0], str(ROOT / "file_3.wav"))


if __name__ == "__main__":
    unittest.main()
