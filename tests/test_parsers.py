from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from avscope.app import (
    calculate_bitrate_kbps,
    calculate_timestamp_seconds,
    extract_hex_bytes_from_dump_text,
    field_highlight_size,
    format_frame_preview_lines,
    format_hex_interpretation,
    format_seconds_timecode,
    first_loadable_drop_path,
    hex_bytes_to_ascii,
    issue_summary_state,
    node_has_issue,
    node_matches_query,
)
from avscope.analyzer import Analyzer, build_probe_diagnostics, build_timeline_diagnostics
from avscope.byte_source import ByteSource
from avscope.cli import main as cli_main
from avscope.compare import compare_binary, compare_protocol, format_binary_compare, format_protocol_compare
from avscope.models import FieldInfo, FrameInfo, ParseNode, Severity
from avscope.plugins import load_plugin_parsers
from avscope.report import export_csv, export_html, export_json, export_project
from avscope.samples import generate_samples, make_h264_baseline_sps, make_h264_pps
from avscope.search import find_pattern, parse_search_pattern
from avscope.settings import AppSettings, MAX_RECENT_FILES


ROOT = Path("G:/AVScope/tmp/testdata")
TS_PACKET_SIZE = 188


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def diagnostics_with(result, severity: str) -> list:
    return [issue for issue in result.diagnostics if issue.severity.value == severity]


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
        first_frame_bits = {field.name: (field.bit_offset, field.bit_length) for field in result.root.children[0].fields}
        self.assertEqual(first_frame_bits["syncword"], (0, 12))
        self.assertEqual(first_frame_bits["profile"], (16, 2))
        self.assertEqual(first_frame_bits["sampling_frequency_index"], (18, 4))
        self.assertEqual(first_frame_bits["channel_configuration"], (23, 3))
        self.assertEqual(first_frame_bits["frame_length"], (30, 13))
        second_frame_bits = {field.name: (field.bit_offset, field.bit_length) for field in result.root.children[1].fields}
        self.assertEqual(second_frame_bits["syncword"], (96, 12))
        html_path = ROOT / "aac_bit_report.html"
        csv_path = ROOT / "aac_bit_report.csv"
        export_html(result, html_path)
        export_csv(result, csv_path)
        html = html_path.read_text(encoding="utf-8")
        csv_text = csv_path.read_text(encoding="utf-8-sig")
        self.assertIn("Bit / Size", html)
        self.assertIn("帧列表", html)
        self.assertIn("AAC LC", html)
        self.assertIn("<td>0/12</td>", html)
        self.assertIn("section,path,name,type,index,offset,size,key,value,hex,severity,description", csv_text)
        self.assertIn("frame", csv_text)
        self.assertIn("syncword", csv_text)

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
        project_path = ROOT / "project.avscope.json"
        export_project(result, project_path, {"sample_rate": 8000})
        self.assertIn("AVScope", html_path.read_text(encoding="utf-8"))
        self.assertIn("媒体摘要", html_path.read_text(encoding="utf-8"))
        self.assertIn("MP4/MOV", json_path.read_text(encoding="utf-8"))
        project = json.loads(project_path.read_text(encoding="utf-8"))
        self.assertEqual(project["project_type"], "AVScope Project")
        self.assertEqual(project["schema_version"], 1)
        self.assertEqual(project["raw_options"]["sample_rate"], 8000)
        self.assertEqual(project["analysis"]["media"]["format_name"], "MP4/MOV")

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

    def test_mpegts_parser(self):
        sample_dir = ROOT / "ts_sample"
        generate_samples(sample_dir)
        result = self.analyzer.analyze(sample_dir / "sample.ts")
        self.assertEqual(result.media.format_name, "MPEG-TS")
        self.assertEqual(result.media.summary["packet_size"], 188)
        self.assertEqual(result.media.summary["packets"], 3)
        self.assertEqual(result.media.summary["pid_counts"]["0x0000"], 1)
        self.assertEqual(result.media.summary["pid_counts"]["0x0100"], 1)
        self.assertEqual(result.root.children[0].name, "Packet[0] PID=0x0000")
        fields = {field.name: field for field in result.root.children[0].fields}
        self.assertEqual(fields["sync_byte"].value, "0x47")
        self.assertEqual(fields["pid"].value, "0x0000")
        self.assertEqual((fields["pid"].bit_offset, fields["pid"].bit_length), (11, 13))

    def test_flv_parser(self):
        sample_dir = ROOT / "flv_sample"
        generate_samples(sample_dir)
        result = self.analyzer.analyze(sample_dir / "sample.flv")
        self.assertEqual(result.media.format_name, "FLV")
        self.assertTrue(result.media.summary["has_audio"])
        self.assertTrue(result.media.summary["has_video"])
        self.assertEqual(result.media.summary["tags"], 2)
        self.assertEqual(result.media.summary["tag_counts"]["script"], 1)
        self.assertEqual(result.media.summary["tag_counts"]["video"], 1)
        self.assertEqual(result.root.children[1].name, "Tag[1] video")
        fields = {field.name: field.value for field in result.root.children[1].fields}
        self.assertEqual(fields["tag_type"], "video")
        self.assertEqual(fields["timestamp"], 40)

    def test_matroska_parser(self):
        sample_dir = ROOT / "matroska_sample"
        generate_samples(sample_dir)
        result = self.analyzer.analyze(sample_dir / "sample.mkv")
        self.assertEqual(result.media.format_name, "Matroska/WebM")
        self.assertEqual(result.media.summary["doc_type"], "matroska")
        self.assertEqual(result.media.summary["timecode_scale"], 1_000_000)
        self.assertEqual(result.media.summary["duration_seconds"], 5.0)
        self.assertEqual(result.media.summary["tracks"][0]["type"], "video")
        self.assertEqual(result.media.summary["tracks"][0]["codec"], "V_MPEG4/ISO/AVC")
        self.assertEqual(result.media.summary["tracks"][0]["width"], 640)
        self.assertEqual(result.media.summary["tracks"][0]["height"], 360)
        self.assertEqual(result.frames[0].pts, 0.0)
        self.assertTrue(result.frames[0].keyframe)

    def test_mpegts_continuity_counter_diagnostic(self):
        def packet(pid: int, counter: int) -> bytes:
            header = bytes([0x47, (pid >> 8) & 0x1F, pid & 0xFF, 0x10 | counter])
            return header + b"\xFF" * (TS_PACKET_SIZE - 4)

        result = self.analyzer.analyze(write(ROOT / "cc_jump.ts", packet(0x0100, 0) + packet(0x0100, 2)))
        self.assertEqual(result.media.format_name, "MPEG-TS")
        self.assertEqual(result.media.summary["continuity_errors"], 1)
        self.assertTrue(any("continuity counter 跳变" in issue.message for issue in diagnostics_with(result, "warning")))
        self.assertEqual(result.root.children[1].severity, Severity.WARNING)

    def test_malformed_files_emit_diagnostics(self):
        broken_mp4 = write(ROOT / "broken_box.mp4", struct.pack(">I4s", 4, b"ftyp") + b"isom")
        result = self.analyzer.analyze(broken_mp4)
        self.assertEqual(result.media.format_name, "MP4/MOV")
        self.assertTrue(diagnostics_with(result, "error"))

        wav_without_data = (
            b"RIFF"
            + struct.pack("<I", 4 + 8 + 16)
            + b"WAVE"
            + b"fmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
        )
        result = self.analyzer.analyze(write(ROOT / "missing_data.wav", wav_without_data))
        self.assertEqual(result.media.format_name, "WAV")
        self.assertTrue(diagnostics_with(result, "error"))

        bad_aac = bytes([0xFF, 0xF1, 0x50, 0x80, 0x00, 0x00, 0xFC])
        result = self.analyzer.analyze(write(ROOT / "bad_length.aac", bad_aac))
        self.assertEqual(result.media.format_name, "AAC ADTS")
        self.assertTrue(diagnostics_with(result, "error"))

        missing_pps_h264 = b"\x00\x00\x00\x01\x67" + make_h264_baseline_sps(640, 480) + b"\x00\x00\x01\x65\x88"
        result = self.analyzer.analyze(write(ROOT / "missing_pps.h264", missing_pps_h264))
        self.assertEqual(result.media.format_name, "H.264 Annex-B")
        self.assertTrue(diagnostics_with(result, "warning"))

        truncated_avi = b"RIFF" + struct.pack("<I", 1024) + b"AVI "
        result = self.analyzer.analyze(write(ROOT / "truncated.avi", truncated_avi))
        self.assertEqual(result.media.format_name, "AVI")
        self.assertTrue(diagnostics_with(result, "warning"))

        truncated_ts = write(ROOT / "truncated.ts", b"\x47\x40\x00\x10" + b"\xFF" * 190)
        result = self.analyzer.analyze(truncated_ts)
        self.assertEqual(result.media.format_name, "MPEG-TS")
        self.assertTrue(diagnostics_with(result, "warning"))

        truncated_flv = write(ROOT / "truncated.flv", b"FLV\x01\x05\x00\x00\x00\x09\x00\x00\x00\x00\x09\x00\x00\x10\x00\x00\x00\x00\x00\x00\x00")
        result = self.analyzer.analyze(truncated_flv)
        self.assertEqual(result.media.format_name, "FLV")
        self.assertTrue(diagnostics_with(result, "error"))

        truncated_mkv = write(ROOT / "truncated.mkv", b"\x1A\x45\xDF\xA3\x84\x42\x82")
        result = self.analyzer.analyze(truncated_mkv)
        self.assertEqual(result.media.format_name, "Matroska/WebM")
        self.assertTrue(diagnostics_with(result, "error"))

    def test_timeline_diagnostics(self):
        summary = {
            "packet_timeline": {
                "packets": [
                    {"index": 0, "stream_index": 0, "pts": 1.0, "dts": 1.0, "pos": 100},
                    {"index": 1, "stream_index": 0, "pts": 0.5, "dts": 0.75, "pos": 120},
                    {"index": 2, "stream_index": 1, "pts": 0.25, "dts": 0.25, "pos": 200},
                ]
            },
            "ffprobe": {
                "available": True,
                "streams": [
                    {"codec_type": "video", "duration": "10.0"},
                    {"codec_type": "audio", "duration": "8.9"},
                ],
            },
        }
        issues = build_timeline_diagnostics(summary)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("PTS 非单调" in message for message in messages))
        self.assertTrue(any("DTS 非单调" in message for message in messages))
        self.assertTrue(any("音视频时长差异" in message for message in messages))
        self.assertEqual({issue.severity for issue in issues}, {Severity.WARNING})

    def test_ffprobe_errors_emit_diagnostics(self):
        summary = {
            "ffprobe": {"available": True, "error": "moov atom not found"},
            "packet_timeline": {"available": True, "error": "invalid data", "packets": []},
        }
        issues = build_probe_diagnostics(summary)
        messages = [issue.message for issue in issues]
        self.assertEqual(len(issues), 2)
        self.assertEqual({issue.severity for issue in issues}, {Severity.WARNING})
        self.assertTrue(any("ffprobe 媒体流探测失败" in message and "moov atom not found" in message for message in messages))
        self.assertTrue(any("packet 时间线探测失败" in message and "invalid data" in message for message in messages))

    def test_plugin_template_parser(self):
        plugin_dir = ROOT / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": 1,
            "name": "Unit Plugin",
            "extensions": [".utp"],
            "match": {"offset": 0, "hex": "55 54 50 31"},
            "fields": [
                {"name": "magic", "offset": 0, "size": 4, "type": "ascii"},
                {"name": "version", "offset": 4, "size": 1, "type": "uint"},
                {"name": "payload_size", "offset": 5, "size": 2, "type": "uint", "endian": "big"},
            ],
        }
        (plugin_dir / "unit.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        parsers = load_plugin_parsers(plugin_dir)
        self.assertEqual([parser.name for parser in parsers], ["Unit Plugin"])

        result = Analyzer(parsers=parsers).analyze(write(ROOT / "sample.utp", b"UTP1\x02\x00\x05hello"))
        self.assertEqual(result.media.format_name, "Unit Plugin")
        fields = {field.name: field for field in result.root.children[0].fields}
        self.assertEqual(fields["magic"].value, "UTP1")
        self.assertEqual(fields["version"].value, 2)
        self.assertEqual(fields["payload_size"].value, 5)
        self.assertEqual((fields["payload_size"].bit_offset, fields["payload_size"].bit_length), (40, 16))

    def test_binary_compare(self):
        left = write(ROOT / "left.bin", b"abc123" + b"\x00" * 40 + b"tail-A")
        right = write(ROOT / "right.bin", b"abc923" + b"\x00" * 40 + b"tail-B")
        result = compare_binary(left, right)
        self.assertFalse(result.equal)
        self.assertEqual(result.chunks[0].offset, 3)
        self.assertEqual(result.chunks[1].offset, 51)
        text = format_binary_compare(result)
        self.assertIn("二进制对比", text)
        self.assertIn("0x00000003", text)
        self.assertIn("0x00000033", text)
        self.assertIn("^^", text)
        self.assertIn("|123", text)

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
        csv_path = ROOT / "cli_report.csv"
        exit_code = cli_main(["analyze", str(sample_dir / "sample.wav"), "--html", str(html_path), "--json", str(json_path), "--csv", str(csv_path)])
        self.assertEqual(exit_code, 0)
        self.assertTrue(html_path.exists())
        self.assertTrue(json_path.exists())
        self.assertTrue(csv_path.exists())
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

    def test_hex_selection_copy_helpers(self):
        dump = "00000000  00 01 68 65 6C 6C 6F FF  |..hello.|\n00000008  F1 20 41                 |. A|"
        data = extract_hex_bytes_from_dump_text(dump)
        self.assertEqual(data, b"\x00\x01hello\xFF\xF1 A")
        self.assertEqual(hex_bytes_to_ascii(data), "..hello.. A")
        self.assertEqual(extract_hex_bytes_from_dump_text("FF F1"), b"\xFF\xF1")
        little = format_hex_interpretation(bytes.fromhex("01 00 00 00"), "little")
        big = format_hex_interpretation(bytes.fromhex("01 00 00 00"), "big")
        self.assertIn("u16: 1", little)
        self.assertIn("u32: 1", little)
        self.assertIn("u16: 256", big)
        self.assertIn("u32: 16777216", big)
        self.assertIn("ASCII: ....", little)

    def test_timestamp_and_bitrate_helpers(self):
        self.assertEqual(calculate_timestamp_seconds(90000, 1, 90000), 1.0)
        self.assertEqual(calculate_timestamp_seconds(150, 1, 30), 5.0)
        self.assertEqual(format_seconds_timecode(3661.2345), "01:01:01.234")
        self.assertAlmostEqual(calculate_bitrate_kbps(125000, 1), 1000.0)
        with self.assertRaises(ValueError):
            calculate_timestamp_seconds(1, 1, 0)
        with self.assertRaises(ValueError):
            calculate_bitrate_kbps(1000, 0)

    def test_issue_summary_state(self):
        self.assertEqual(issue_summary_state(0, 0), ("0 error / 0 warning", "ok"))
        self.assertEqual(issue_summary_state(0, 2), ("0 error / 2 warning", "warning"))
        self.assertEqual(issue_summary_state(1, 3), ("1 error / 3 warning", "error"))

    def test_frame_preview_lines(self):
        frames = [
            FrameInfo(index=0, offset=32, size=12, pts=1.25, keyframe=True),
            FrameInfo(index=1, offset=44, size=10, pts=1.29, keyframe=False),
        ]
        lines = format_frame_preview_lines(frames)
        self.assertEqual(lines[0], "解析器帧列表: 已提取 2 帧，关键帧 1 帧，详见“帧列表”页。")
        self.assertEqual(lines[1], "首帧: offset=0x20, size=12, PTS=1.25s")
        self.assertEqual(format_frame_preview_lines([]), [])

    def test_protocol_tree_search_and_issue_helpers(self):
        root = ParseNode("root", "file", 0, 16)
        trak = root.add_child(ParseNode("trak", "box", 8, 8, description="video track"))
        trak.fields.append(FieldInfo("handler_type", "vide", offset=12, hex_value="76 69 64 65"))
        stsz = trak.add_child(ParseNode("stsz", "box", 20, 12))
        stsz.fields.append(FieldInfo("sample_count", 1, offset=24, severity=Severity.WARNING))

        self.assertTrue(node_matches_query(trak, "video"))
        self.assertTrue(node_matches_query(trak, "vide"))
        self.assertTrue(node_matches_query(stsz, "0x14"))
        self.assertFalse(node_matches_query(trak, "aac"))
        self.assertTrue(node_has_issue(root))
        self.assertTrue(node_has_issue(trak))
        self.assertTrue(node_has_issue(stsz))
        self.assertFalse(node_has_issue(ParseNode("mdat", "box", 32, 128)))

    def test_field_highlight_size(self):
        self.assertEqual(field_highlight_size(FieldInfo("size", 1, size=4)), 4)
        self.assertEqual(field_highlight_size(FieldInfo("syncword", "0xFFF", bit_length=12)), 2)
        self.assertEqual(field_highlight_size(FieldInfo("derived", 1, size=0)), 1)

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

    def test_drop_path_selection(self):
        missing = ROOT / "missing-drop.wav"
        sample = write(ROOT / "drop.wav", b"RIFFxxxxWAVE")
        self.assertEqual(first_loadable_drop_path([missing, sample]), sample)
        self.assertEqual(first_loadable_drop_path([ROOT]), ROOT)
        self.assertIsNone(first_loadable_drop_path([missing]))

    def test_byte_source_large_file_random_access(self):
        path = ROOT / "large_random_access.bin"
        size = 128 * 1024 * 1024 + 17
        with path.open("wb") as fh:
            fh.write(b"HEAD")
            fh.seek(size - 4)
            fh.write(b"TAIL")

        with ByteSource(path) as source:
            self.assertEqual(source.size, size)
            self.assertEqual(source.head(4), b"HEAD")
            self.assertEqual(source.read_at(size - 4, 16), b"TAIL")
            self.assertEqual(source.read_at(size + 1, 16), b"")
            self.assertEqual(len(source.read_at(64 * 1024 * 1024, 4096)), 4096)


if __name__ == "__main__":
    unittest.main()
