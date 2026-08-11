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
from avscope.samples import generate_samples, make_h264_baseline_sps, make_h264_pps
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
        self.assertEqual(result.media.summary["wave_format_name"], "PCM")
        self.assertEqual(result.media.summary["data_bytes"], len(pcm))
        self.assertEqual(result.media.summary["expected_block_align"], 2)
        self.assertEqual(result.media.summary["expected_byte_rate"], 16000)
        self.assertEqual(result.media.summary["frame_count"], 16)
        self.assertEqual(result.media.summary["duration_seconds"], 0.002)
        self.assertIn("ffprobe", result.media.summary)
        self.assertIn("packet_timeline", result.media.summary)
        self.assertTrue(result.media.summary["waveform"]["available"])
        self.assertFalse([i for i in result.diagnostics if i.severity.value == "error"])

    def test_aac_parser(self):
        frame = bytes([0xFF, 0xF1, 0x50, 0x80, 0x01, 0x9F, 0xFC]) + b"\x00" * 5
        result = self.analyzer.analyze(write(ROOT / "ok.aac", frame * 3))
        self.assertEqual(result.media.format_name, "AAC ADTS")
        self.assertEqual(result.media.summary["frames"], 3)
        self.assertEqual(result.media.summary["profile"], "AAC LC")
        self.assertEqual(result.media.summary["sample_rate"], 44100)
        self.assertEqual(result.media.summary["channels"], 2)
        self.assertGreater(result.media.summary["average_bitrate"], 0)
        fields = {field.name: field.value for field in result.root.children[0].fields}
        self.assertEqual(fields["samples_per_frame"], 1024)
        self.assertIn("duration_seconds", fields)

    def test_h264_parser(self):
        data = b"\x00\x00\x00\x01\x67" + make_h264_baseline_sps(640, 480) + b"\x00\x00\x01\x68" + make_h264_pps() + b"\x00\x00\x01\x65\x88"
        result = self.analyzer.analyze(write(ROOT / "ok.h264", data))
        self.assertEqual(result.media.format_name, "H.264 Annex-B")
        self.assertGreaterEqual(result.media.summary["nalu_count"], 3)
        self.assertEqual(result.media.summary["width"], 640)
        self.assertEqual(result.media.summary["height"], 480)
        self.assertEqual(result.media.summary["pps_id"], 0)
        sps_fields = {field.name: field.value for field in result.root.children[0].fields}
        self.assertEqual(sps_fields["profile_idc"], 66)
        self.assertEqual(sps_fields["level_idc"], 30)
        pps_fields = {field.name: field.value for field in result.root.children[1].fields}
        self.assertEqual(pps_fields["pic_parameter_set_id"], 0)
        self.assertEqual(pps_fields["seq_parameter_set_id"], 0)

    def test_h265_parser(self):
        sample_dir = ROOT / "h265_sample"
        generate_samples(sample_dir)
        result = self.analyzer.analyze(sample_dir / "sample.h265")
        self.assertEqual(result.media.format_name, "H.265 Annex-B")
        self.assertGreaterEqual(result.media.summary["nalu_count"], 4)
        self.assertEqual(result.media.summary["width"], 640)
        self.assertEqual(result.media.summary["height"], 360)
        self.assertEqual(result.media.summary["profile_idc"], 1)
        self.assertEqual(result.media.summary["level_idc"], 120)
        vps_fields = {field.name: field.value for field in result.root.children[0].fields}
        self.assertEqual(vps_fields["vps_video_parameter_set_id"], 0)
        sps_fields = {field.name: field.value for field in result.root.children[1].fields}
        self.assertEqual(sps_fields["derived_width"], 640)
        self.assertEqual(sps_fields["bit_depth_luma"], 8)
        pps_fields = {field.name: field.value for field in result.root.children[2].fields}
        self.assertEqual(pps_fields["pps_pic_parameter_set_id"], 0)
        self.assertEqual(pps_fields["pps_seq_parameter_set_id"], 0)

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

    def test_mp4_mvhd_parser(self):
        sample_dir = ROOT / "mp4_sample"
        generate_samples(sample_dir)
        result = self.analyzer.analyze(sample_dir / "sample.mp4")
        moov = next(node for node in result.root.children if node.name == "moov")
        mvhd = next(node for node in moov.children if node.name == "mvhd")
        fields = {field.name: field.value for field in mvhd.fields}
        self.assertEqual(fields["timescale"], 1000)
        self.assertEqual(fields["duration"], 5000)
        self.assertEqual(fields["duration_seconds"], 5.0)
        trak = next(node for node in moov.children if node.name == "trak")
        tkhd = next(node for node in trak.children if node.name == "tkhd")
        tkhd_fields = {field.name: field.value for field in tkhd.fields}
        self.assertEqual(tkhd_fields["track_id"], 1)
        self.assertEqual(tkhd_fields["width"], 640)
        self.assertEqual(tkhd_fields["height"], 360)
        mdia = next(node for node in trak.children if node.name == "mdia")
        mdhd = next(node for node in mdia.children if node.name == "mdhd")
        mdhd_fields = {field.name: field.value for field in mdhd.fields}
        self.assertEqual(mdhd_fields["timescale"], 30000)
        self.assertEqual(mdhd_fields["duration"], 150000)
        self.assertEqual(mdhd_fields["duration_seconds"], 5.0)
        self.assertEqual(mdhd_fields["language"], "und")
        hdlr = next(node for node in mdia.children if node.name == "hdlr")
        hdlr_fields = {field.name: field.value for field in hdlr.fields}
        self.assertEqual(hdlr_fields["handler_type"], "vide")
        minf = next(node for node in mdia.children if node.name == "minf")
        stbl = next(node for node in minf.children if node.name == "stbl")
        stsd = next(node for node in stbl.children if node.name == "stsd")
        stsd_fields = {field.name: field.value for field in stsd.fields}
        self.assertEqual(stsd_fields["entry_count"], 1)
        sample_entry_fields = {field.name: field.value for field in stsd.children[0].fields}
        self.assertEqual(sample_entry_fields["type"], "avc1")
        self.assertEqual(sample_entry_fields["width"], 640)
        self.assertEqual(sample_entry_fields["height"], 360)
        stts = next(node for node in stbl.children if node.name == "stts")
        stts_fields = {field.name: field.value for field in stts.children[0].fields}
        self.assertEqual(stts_fields["sample_count"], 1)
        self.assertEqual(stts_fields["sample_delta"], 150)
        stsc = next(node for node in stbl.children if node.name == "stsc")
        stsc_fields = {field.name: field.value for field in stsc.children[0].fields}
        self.assertEqual(stsc_fields["samples_per_chunk"], 1)
        stsz = next(node for node in stbl.children if node.name == "stsz")
        stsz_fields = {field.name: field.value for field in stsz.fields}
        self.assertEqual(stsz_fields["sample_count"], 1)
        stco = next(node for node in stbl.children if node.name == "stco")
        stco_fields = {field.name: field.value for field in stco.children[0].fields}
        self.assertGreater(stco_fields["chunk_offset"], 0)

    def test_avi_parser(self):
        sample_dir = ROOT / "avi_sample"
        generate_samples(sample_dir)
        result = self.analyzer.analyze(sample_dir / "sample.avi")
        self.assertEqual(result.media.format_name, "AVI")
        self.assertEqual(result.media.summary["width"], 640)
        self.assertEqual(result.media.summary["height"], 480)
        self.assertEqual(result.media.summary["streams"], 1)
        self.assertEqual(result.media.summary["total_frames"], 150)
        self.assertAlmostEqual(result.media.summary["fps"], 30.0003, places=3)
        avih = result.root.children[0].children[0]
        fields = {field.name: field.value for field in avih.fields}
        self.assertEqual(fields["dwWidth"], 640)
        self.assertEqual(fields["dwHeight"], 480)

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
        pcm_json = ROOT / "cli_pcm_report.json"
        exit_code = cli_main(
            [
                "analyze",
                str(sample_dir / "sample.pcm"),
                "--sample-rate",
                "8000",
                "--channels",
                "1",
                "--bits-per-sample",
                "16",
                "--json",
                str(pcm_json),
            ]
        )
        self.assertEqual(exit_code, 0)
        pcm_summary = json.loads(pcm_json.read_text(encoding="utf-8"))["media"]["summary"]
        self.assertEqual(pcm_summary["sample_rate"], 8000)
        self.assertEqual(pcm_summary["channels"], 1)
        yuv_json = ROOT / "cli_yuv_report.json"
        exit_code = cli_main(
            [
                "analyze",
                str(sample_dir / "sample.yuv"),
                "--width",
                "64",
                "--height",
                "48",
                "--pixel-format",
                "yuv420p",
                "--fps",
                "30",
                "--json",
                str(yuv_json),
            ]
        )
        self.assertEqual(exit_code, 0)
        yuv_summary = json.loads(yuv_json.read_text(encoding="utf-8"))["media"]["summary"]
        self.assertEqual(yuv_summary["width"], 64)
        self.assertEqual(yuv_summary["height"], 48)
        self.assertEqual(yuv_summary["frames"], 1)
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
        for source_path in Path("G:/AVScope/avscope").rglob("*.py"):
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
