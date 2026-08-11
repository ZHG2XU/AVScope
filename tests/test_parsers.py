from __future__ import annotations

import json
import os
import struct
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from avscope.app import (
    binary_compare_offsets,
    binary_compare_preview_indices,
    calculate_bitrate_kbps,
    calculate_timestamp_seconds,
    extract_hex_bytes_from_dump_text,
    format_empty_state_text,
    field_highlight_size,
    format_plugin_template_summary,
    format_elapsed_seconds,
    format_frame_preview_lines,
    format_video_frame_info_lines,
    format_timeline_summary_lines,
    format_hex_interpretation,
    format_sample_files_help,
    format_shortcuts_help,
    format_seconds_timecode,
    timeline_anomaly_item_orders,
    timeline_item_row_tag,
    first_loadable_drop_path,
    hex_bytes_to_ascii,
    issue_summary_state,
    node_has_issue,
    node_matches_query,
)
from avscope.analyzer import Analyzer, build_probe_diagnostics, build_timeline_diagnostics
from avscope.audio_preview import build_audio_preview_clip, play_audio_preview_clip
from avscope.byte_source import ByteSource
from avscope.cli import main as cli_main
from avscope.compare import compare_binary, compare_frames, compare_protocol, format_binary_compare, format_frame_compare, format_protocol_compare
from avscope.extract import build_extract_command, extract_media_stream
from avscope.ffmpeg_preview import build_video_preview, find_ffmpeg, find_video_frame_time, find_video_keyframe_time, png_dimensions, preview_output_path, probe_video_frame_info
from avscope.frame_stats import build_frame_stats
from avscope.models import FieldInfo, FrameInfo, MediaInfo, ParseNode, ParseResult, Severity
from avscope.packet_stats import build_packet_stats
from avscope.plugins import build_plugin_template_manifest, load_plugin_parsers, normalize_extension, normalize_magic_hex, write_plugin_template
from avscope.report import export_csv, export_html, export_json, export_project, timeline_issue_rows
from avscope.samples import generate_samples, make_h264_baseline_sps, make_h264_pps
from avscope.search import find_pattern, parse_search_pattern
from avscope.settings import AppSettings, MAX_RECENT_FILES
from scripts.release_manifest import build_release_manifest, write_release_manifest
from scripts.sample_reports import build_sample_reports
from scripts.validation_report import build_validation_report, write_validation_report
from avscope.timeline_viz import build_timeline_summary, timeline_chart_items
from avscope.waveform import build_waveform_preview
from avscope.yuv_preview import build_yuv_preview, yuv_frame_size, yuv_preview_output_path, yuv_to_rgb


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
        self.assertEqual(result.media.summary["waveform"]["energy"]["peak_level"], 0.0)
        self.assertIsNone(result.media.summary["waveform"]["energy"]["peak_dbfs"])
        preview = build_waveform_preview(ROOT / "ok.wav", "WAV", result.media.summary, output_dir=ROOT / "waveform-previews", width=320, height=120)
        self.assertTrue(preview["available"])
        self.assertEqual(preview["width"], 320)
        self.assertEqual(preview["height"], 120)
        self.assertTrue(Path(preview["path"]).read_bytes().startswith(b"P6\n320 120\n255\n"))
        self.assertFalse([i for i in result.diagnostics if i.severity.value == "error"])

    def test_raw_pcm_endian_and_signed_options(self):
        data = bytes([0x00, 0x00, 0x80, 0x00, 0xFF, 0xFF])
        result = self.analyzer.analyze(
            write(ROOT / "be_unsigned.pcm", data),
            {"sample_rate": 3, "channels": 1, "bits_per_sample": 16, "endian": "big", "signed": False},
        )
        self.assertEqual(result.media.summary["endian"], "big")
        self.assertFalse(result.media.summary["signed"])
        self.assertEqual(result.media.summary["bytes_per_sample"], 2)
        waveform = result.media.summary["waveform"]
        self.assertTrue(waveform["available"])
        self.assertEqual(waveform["endian"], "big")
        self.assertFalse(waveform["signed"])
        self.assertEqual(waveform["peaks"][0]["min"], -1.0)
        self.assertEqual(waveform["peaks"][1]["max"], 0.0)
        self.assertEqual(waveform["peaks"][2]["max"], 1.0)
        self.assertEqual(waveform["energy"]["peak_level"], 1.0)
        self.assertGreaterEqual(waveform["energy"]["clipped_samples"], 2)

    def test_audio_preview_clip_helpers(self):
        wav_path = ROOT / "preview_audio.wav"
        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"\x00\x00" * 800)
        clip = build_audio_preview_clip(wav_path, "WAV", {}, output_dir=ROOT / "audio-previews", duration_seconds=0.05)
        self.assertTrue(clip["available"])
        self.assertLessEqual(clip["frames"], 800)
        with wave.open(clip["path"], "rb") as clipped:
            self.assertEqual(clipped.getframerate(), 8000)
            self.assertEqual(clipped.getnchannels(), 1)
        ranged = build_audio_preview_clip(wav_path, "WAV", {}, output_dir=ROOT / "audio-previews", start_seconds=0.05, duration_seconds=0.05)
        self.assertTrue(ranged["available"])
        self.assertEqual(ranged["start_seconds"], 0.05)
        self.assertNotEqual(clip["path"], ranged["path"])

        pcm_path = write(ROOT / "preview_audio.pcm", b"\x00\x00\x01\x00" * 800)
        pcm_clip = build_audio_preview_clip(
            pcm_path,
            "Raw PCM",
            {"sample_rate": 8000, "channels": 1, "bits_per_sample": 16, "endian": "little", "signed": True},
            output_dir=ROOT / "audio-previews",
            duration_seconds=0.05,
        )
        self.assertTrue(pcm_clip["available"])
        with wave.open(pcm_clip["path"], "rb") as clipped:
            self.assertEqual(clipped.getsampwidth(), 2)
            self.assertEqual(clipped.getframerate(), 8000)
        pcm_ranged = build_audio_preview_clip(
            pcm_path,
            "Raw PCM",
            {"sample_rate": 8000, "channels": 1, "bits_per_sample": 16, "endian": "little", "signed": True},
            output_dir=ROOT / "audio-previews",
            start_seconds=0.05,
            duration_seconds=0.05,
        )
        self.assertTrue(pcm_ranged["available"])
        self.assertEqual(pcm_ranged["start_seconds"], 0.05)

        calls = []
        fake_winsound = types.SimpleNamespace(
            SND_FILENAME=1,
            SND_ASYNC=2,
            PlaySound=lambda path, flags: calls.append((path, flags)),
        )
        with patch.dict("sys.modules", {"winsound": fake_winsound}):
            playback = play_audio_preview_clip(clip["path"])
        self.assertTrue(playback["available"])
        self.assertEqual(calls[0][0], clip["path"])

    def test_audio_preview_clip_with_mocked_ffmpeg(self):
        source = write(ROOT / "preview_audio.aac", b"not real aac")
        commands = []

        def fake_run(command, capture_output, text, timeout, check):
            commands.append(command)
            output = Path(command[-1])
            with wave.open(str(output), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(b"\x00\x00" * 80)

            class Completed:
                returncode = 0
                stderr = ""

            return Completed()

        with patch("avscope.audio_preview.find_ffmpeg", return_value="ffmpeg"), patch("avscope.audio_preview.subprocess.run", side_effect=fake_run):
            clip = build_audio_preview_clip(source, "AAC ADTS", {}, output_dir=ROOT / "audio-previews", start_seconds=1.25, duration_seconds=0.1)
        self.assertTrue(clip["available"])
        self.assertEqual(clip["sample_rate"], 8000)
        self.assertEqual(clip["start_seconds"], 1.25)
        self.assertIn("-ss", commands[0])
        self.assertIn("1.250", commands[0])
        self.assertTrue(Path(clip["path"]).exists())

    def test_aac_parser(self):
        frame = bytes([0xFF, 0xF1, 0x50, 0x80, 0x01, 0x9F, 0xFC]) + b"\x00" * 5
        result = self.analyzer.analyze(write(ROOT / "ok.aac", frame * 3))
        self.assertEqual(result.media.format_name, "AAC ADTS")
        self.assertEqual(result.media.summary["frames"], 3)
        self.assertEqual(result.media.summary["frame_stats"]["frames"], 3)
        self.assertEqual(result.media.summary["frame_stats"]["average_size"], 12.0)
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
        self.assertIn("帧统计", html)
        self.assertIn("统计摘要", html)
        self.assertIn("AAC LC", html)
        self.assertIn("<td>0/12</td>", html)
        self.assertIn("section,path,name,type,index,offset,size,key,value,hex,severity,description", csv_text)
        self.assertIn("frame_stats", csv_text)
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
        report_notes = "现场备注：客户样例，关注 moov/mdat 结构。"
        export_html(result, html_path, notes=report_notes)
        export_json(result, json_path, notes=report_notes)
        project_path = ROOT / "project.avscope.json"
        csv_path = ROOT / "report.csv"
        export_csv(result, csv_path, notes=report_notes)
        export_project(result, project_path, {"sample_rate": 8000}, notes=report_notes)
        self.assertIn("AVScope", html_path.read_text(encoding="utf-8"))
        self.assertIn("媒体摘要", html_path.read_text(encoding="utf-8"))
        self.assertIn("用户备注", html_path.read_text(encoding="utf-8"))
        self.assertIn(report_notes, html_path.read_text(encoding="utf-8"))
        self.assertIn("MP4/MOV", json_path.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["user_notes"], report_notes)
        self.assertIn("notes", csv_path.read_text(encoding="utf-8-sig"))
        project = json.loads(project_path.read_text(encoding="utf-8"))
        self.assertEqual(project["project_type"], "AVScope Project")
        self.assertEqual(project["schema_version"], 1)
        self.assertEqual(project["raw_options"]["sample_rate"], 8000)
        self.assertEqual(project["user_notes"], report_notes)
        self.assertEqual(project["analysis"]["media"]["format_name"], "MP4/MOV")
        self.assertEqual(project["analysis"]["user_notes"], report_notes)

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
        self.assertEqual(result.media.summary["chunk_offsets"]["total"], 1)
        self.assertEqual(result.media.summary["chunk_offsets"]["outside_file"], 0)
        self.assertEqual(result.media.summary["chunk_offsets"]["outside_mdat"], 0)

    def test_mp4_chunk_offset_diagnostics(self):
        def find_node(node: ParseNode, name: str) -> ParseNode | None:
            if node.name == name:
                return node
            for child in node.children:
                found = find_node(child, name)
                if found is not None:
                    return found
            return None

        sample_dir = ROOT / "mp4_chunk_offset_sample"
        generate_samples(sample_dir)
        data = bytearray((sample_dir / "sample.mp4").read_bytes())
        stco_type_offset = data.index(b"stco")
        first_chunk_offset = stco_type_offset + 12

        outside_mdat = bytearray(data)
        outside_mdat[first_chunk_offset : first_chunk_offset + 4] = (8).to_bytes(4, "big")
        result = self.analyzer.analyze(write(ROOT / "chunk_outside_mdat.mp4", bytes(outside_mdat)))
        messages = [issue.message for issue in diagnostics_with(result, "warning")]
        self.assertEqual(result.media.summary["chunk_offsets"]["outside_mdat"], 1)
        self.assertTrue(any("MP4 chunk offset 未落在 mdat 数据区" in message for message in messages))
        stco = find_node(result.root, "stco")
        self.assertIsNotNone(stco)
        self.assertEqual(stco.children[0].severity, Severity.WARNING)

        outside_file = bytearray(data)
        outside_file[first_chunk_offset : first_chunk_offset + 4] = (len(data) + 128).to_bytes(4, "big")
        result = self.analyzer.analyze(write(ROOT / "chunk_outside_file.mp4", bytes(outside_file)))
        messages = [issue.message for issue in diagnostics_with(result, "error")]
        self.assertEqual(result.media.summary["chunk_offsets"]["outside_file"], 1)
        self.assertTrue(any("MP4 chunk offset 超出文件范围" in message for message in messages))

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
        self.assertEqual(result.media.summary["pid_counts"]["0x0100"], 2)
        self.assertTrue(result.media.summary["pcr"]["available"])
        self.assertEqual(result.media.summary["pcr"]["points"], 2)
        self.assertEqual(result.media.summary["pcr"]["by_pid"]["0x0100"]["span"], 1.0)
        self.assertEqual(len(result.frames), 2)
        self.assertEqual(result.frames[1].metadata["pcr_pid"], "0x0100")
        self.assertEqual(result.media.summary["timeline_summary"]["pcr"]["points"], 2)
        self.assertEqual(result.root.children[0].name, "Packet[0] PID=0x0000")
        fields = {field.name: field for field in result.root.children[0].fields}
        self.assertEqual(fields["sync_byte"].value, "0x47")
        self.assertEqual(fields["pid"].value, "0x0000")
        self.assertEqual((fields["pid"].bit_offset, fields["pid"].bit_length), (11, 13))
        pcr_fields = {field.name: field.value for field in result.root.children[1].fields}
        self.assertTrue(pcr_fields["pcr_flag"])
        self.assertEqual(pcr_fields["pcr_base"], 0)
        self.assertEqual(pcr_fields["pcr_seconds"], 0.0)
        html_path = ROOT / "mpegts_pcr_report.html"
        csv_path = ROOT / "mpegts_pcr_report.csv"
        json_path = ROOT / "mpegts_pcr_report.json"
        export_html(result, html_path)
        export_csv(result, csv_path)
        export_json(result, json_path)
        self.assertIn("PCR", html_path.read_text(encoding="utf-8"))
        self.assertIn("Timeline chart legend", html_path.read_text(encoding="utf-8"))
        self.assertIn("PCR curve", html_path.read_text(encoding="utf-8"))
        self.assertIn("pcr_seconds", csv_path.read_text(encoding="utf-8-sig"))
        self.assertIn('"pcr_seconds": 1.0', json_path.read_text(encoding="utf-8"))

    def test_mpegps_parser(self):
        sample_dir = ROOT / "ps_sample"
        generate_samples(sample_dir)
        result = self.analyzer.analyze(sample_dir / "sample.ps")
        self.assertEqual(result.media.format_name, "MPEG-PS")
        self.assertEqual(result.media.summary["stream_counts"]["pack_header"], 1)
        self.assertEqual(result.media.summary["stream_counts"]["system_header"], 1)
        self.assertEqual(result.media.summary["stream_counts"]["video_stream[0]"], 1)
        self.assertEqual(result.media.summary["stream_counts"]["audio_stream[0]"], 1)
        self.assertEqual(result.media.summary["frames"], 2)
        self.assertEqual(result.frames[0].pts, 1.0)
        self.assertEqual(result.frames[0].frame_type, "video_stream[0]")
        self.assertTrue(result.frames[0].keyframe)
        fields = {field.name: field.value for field in result.root.children[2].fields}
        self.assertEqual(fields["stream_id"], "0xE0")
        self.assertEqual(fields["pts_seconds"], 1.0)

    def test_pcap_rtp_parser(self):
        sample_dir = ROOT / "pcap_sample"
        generate_samples(sample_dir)
        result = self.analyzer.analyze(sample_dir / "sample.pcap")
        self.assertEqual(result.media.format_name, "PCAP/RTP")
        self.assertEqual(result.media.summary["packets"], 2)
        self.assertEqual(result.media.summary["rtp_packets"], 2)
        self.assertEqual(result.media.summary["payload_type_counts"]["96"], 2)
        self.assertEqual(result.frames[0].pts, 1.0)
        self.assertEqual(result.frames[0].frame_type, "RTP PT=96")
        self.assertFalse(result.frames[0].keyframe)
        self.assertTrue(result.frames[1].keyframe)
        self.assertEqual(result.frames[0].metadata["rtp_sequence"], 100)
        self.assertEqual(result.frames[0].metadata["rtp_ssrc"], "0x12345678")
        rtp_sequence = result.media.summary["timeline_summary"]["rtp_sequence"]
        self.assertTrue(rtp_sequence["available"])
        self.assertEqual(rtp_sequence["packets"], 2)
        self.assertEqual(rtp_sequence["sequence_warnings"], 0)
        self.assertEqual(rtp_sequence["streams"]["0x12345678"]["first_sequence"], 100)
        self.assertEqual(rtp_sequence["series"][0]["sequence"], 100)
        self.assertTrue(rtp_sequence["series"][1]["marker"])
        fields = {field.name: field.value for field in result.root.children[0].fields}
        self.assertEqual(fields["src_ip"], "192.168.1.10")
        self.assertEqual(fields["dst_ip"], "239.1.1.1")
        self.assertEqual(fields["rtp_sequence"], 100)
        self.assertEqual(fields["rtp_ssrc"], "0x12345678")
        html_path = ROOT / "pcap_rtp_report.html"
        csv_path = ROOT / "pcap_rtp_report.csv"
        json_path = ROOT / "pcap_rtp_report.json"
        export_html(result, html_path)
        export_csv(result, csv_path)
        export_json(result, json_path)
        self.assertIn("RTP Sequence", html_path.read_text(encoding="utf-8"))
        self.assertIn("Timeline chart legend", html_path.read_text(encoding="utf-8"))
        self.assertIn("RTP sequence 曲线", html_path.read_text(encoding="utf-8"))
        self.assertIn("RTP seq=100", csv_path.read_text(encoding="utf-8-sig"))
        self.assertIn('"rtp_sequence": 100', json_path.read_text(encoding="utf-8"))

    def test_pcap_rtp_sequence_diagnostic(self):
        sample_dir = ROOT / "pcap_jump_sample"
        generate_samples(sample_dir)
        data = (sample_dir / "sample.pcap").read_bytes()
        sequence_offset = 24 + 16 + 14 + 20 + 8 + 2
        changed = bytearray(data)
        second_sequence_offset = sequence_offset + 16 + int.from_bytes(data[24 + 8 : 24 + 12], "little")
        changed[second_sequence_offset : second_sequence_offset + 2] = (105).to_bytes(2, "big")
        result = self.analyzer.analyze(write(ROOT / "sequence_jump.pcap", bytes(changed)))
        self.assertEqual(result.media.format_name, "PCAP/RTP")
        self.assertEqual(result.media.summary["sequence_warnings"], 1)
        rtp_sequence = result.media.summary["timeline_summary"]["rtp_sequence"]
        self.assertEqual(rtp_sequence["sequence_warnings"], 1)
        self.assertEqual(rtp_sequence["warnings"][0]["expected"], 101)
        self.assertEqual(rtp_sequence["warnings"][0]["current"], 105)
        self.assertTrue(any("RTP sequence 跳变" in issue.message for issue in diagnostics_with(result, "warning")))

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

        truncated_ps = write(ROOT / "truncated.ps", b"\x00\x00\x01\xBA\x44\x00")
        result = self.analyzer.analyze(truncated_ps)
        self.assertEqual(result.media.format_name, "MPEG-PS")
        self.assertTrue(diagnostics_with(result, "error"))

        truncated_pcap = write(ROOT / "truncated.pcap", b"\xD4\xC3\xB2\xA1")
        result = self.analyzer.analyze(truncated_pcap)
        self.assertEqual(result.media.format_name, "PCAP/RTP")
        self.assertTrue(diagnostics_with(result, "error"))

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
            "frame_stats": {
                "available": True,
                "frames": 5,
                "average_size": 150,
                "max_size": 600,
                "largest_index": 2,
                "largest_offset": 512,
                "largest_size": 600,
            },
            "packet_stats": {
                "available": True,
                "packets": 6,
                "average_size": 90,
                "max_size": 500,
                "by_stream": {
                    "0": {
                        "packets": 5,
                        "average_size": 125,
                        "max_size": 500,
                        "largest_index": 3,
                        "largest_pos": 2048,
                        "largest_size": 500,
                    },
                    "1": {"packets": 2, "average_size": 50, "max_size": 60, "largest_index": 5, "largest_size": 60},
                },
            },
        }
        issues = build_timeline_diagnostics(summary)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("PTS 非单调" in message for message in messages))
        self.assertTrue(any("DTS 非单调" in message for message in messages))
        self.assertTrue(any("音视频时长差异" in message for message in messages))
        self.assertTrue(any("帧大小尖峰" in message and "frame=#2" in message for message in messages))
        self.assertTrue(any("Packet 大小尖峰" in message and "stream=0" in message for message in messages))
        self.assertEqual({issue.severity for issue in issues}, {Severity.WARNING})

    def test_packet_stats(self):
        stats = build_packet_stats(
            {
                "packets": [
                    {"stream_index": 0, "codec_type": "video", "pts": 1.0, "size": 100, "keyframe": True},
                    {"stream_index": 0, "codec_type": "video", "pts": 1.04, "size": 50, "keyframe": False},
                    {"stream_index": 1, "codec_type": "audio", "pts": 0.5, "size": 25, "keyframe": False},
                ]
            }
        )
        self.assertTrue(stats["available"])
        self.assertEqual(stats["packets"], 3)
        self.assertEqual(stats["streams"], 2)
        self.assertEqual(stats["keyframes"], 1)
        self.assertEqual(stats["average_size"], 58.33)
        self.assertEqual(stats["largest_index"], None)
        self.assertEqual(stats["largest_size"], 100)
        self.assertEqual(stats["by_stream"]["0"]["pts_span"], 0.04)
        self.assertEqual(stats["by_stream"]["0"]["largest_size"], 100)

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

    def test_write_plugin_template(self):
        plugin_dir = ROOT / "new_plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        for path in plugin_dir.glob("*.json"):
            path.unlink()
        path = write_plugin_template("Unit Template", "unitx", "55 4E 49 54", plugin_dir)
        self.assertEqual(path.parent, plugin_dir)
        self.assertTrue(path.exists())
        self.assertEqual(normalize_extension("unitx"), ".unitx")
        self.assertEqual(normalize_magic_hex("55-4e:49 54"), "55 4E 49 54")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["extensions"], [".unitx"])
        self.assertEqual(manifest["match"]["hex"], "55 4E 49 54")
        self.assertEqual(manifest["fields"][0]["size"], 4)
        parsers = load_plugin_parsers(plugin_dir)
        self.assertEqual(len(parsers), 1)
        self.assertEqual(parsers[0].name, "Unit Template")
        with self.assertRaises(FileExistsError):
            write_plugin_template("Unit Template", ".unitx", "55 4E 49 54", plugin_dir)
        with self.assertRaises(ValueError):
            build_plugin_template_manifest("Bad", "", "00")
        with self.assertRaises(ValueError):
            build_plugin_template_manifest("Bad", ".bad", "0")

    def test_ui_help_text(self):
        shortcuts = format_shortcuts_help()
        self.assertIn("Ctrl+O", shortcuts)
        self.assertIn("Ctrl+1", shortcuts)
        self.assertIn("Ctrl+L", shortcuts)
        self.assertIn("F4", shortcuts)
        self.assertIn("Ctrl+Shift+I", shortcuts)
        samples = format_sample_files_help()
        self.assertIn("G:\\AVScope\\samples", samples)
        self.assertIn("sample.mp4", samples)
        empty_state = format_empty_state_text()
        self.assertIn("工作区待命", empty_state)
        self.assertIn("H.264/H.265", empty_state)
        self.assertIn("媒体提取", empty_state)
        plugin_dir = ROOT / "help_plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": 1,
            "name": "Help Plugin",
            "extensions": [".help"],
            "match": {"offset": 0, "hex": "48 45 4C 50"},
            "fields": [],
        }
        (plugin_dir / "help.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = format_plugin_template_summary(load_plugin_parsers(plugin_dir))
        self.assertIn("Help Plugin", summary)
        self.assertIn(".help", summary)

    def test_elapsed_formatting(self):
        self.assertEqual(format_elapsed_seconds(None), "--")
        self.assertEqual(format_elapsed_seconds(0.0123), "12 ms")
        self.assertEqual(format_elapsed_seconds(1.23456), "1.235 s")

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
        self.assertEqual(binary_compare_offsets(result), [3, 51])
        indices = binary_compare_preview_indices(text, binary_compare_offsets(result))
        self.assertEqual(len(indices), 2)
        self.assertTrue(all(index.endswith(".0") for index in indices))

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

    def test_frame_compare(self):
        def aac_frame(frame_length: int) -> bytes:
            if frame_length < 7:
                raise ValueError("ADTS frame length must include the 7-byte header")
            header = bytearray([0xFF, 0xF1, 0x50, 0x80, 0x00, 0x1F, 0xFC])
            header[3] = (header[3] & 0xFC) | ((frame_length >> 11) & 0x03)
            header[4] = (frame_length >> 3) & 0xFF
            header[5] = ((frame_length & 0x07) << 5) | 0x1F
            return bytes(header) + b"\x00" * (frame_length - 7)

        left = write(ROOT / "frames_left.aac", aac_frame(12) + aac_frame(12))
        right = write(ROOT / "frames_right.aac", aac_frame(12) + aac_frame(14) + aac_frame(12))
        result = compare_frames(left, right)
        self.assertEqual(result["left_format"], "AAC ADTS")
        self.assertEqual(result["left_frames"], 2)
        self.assertEqual(result["right_frames"], 3)
        self.assertEqual(result["added"][0]["index"], 2)
        self.assertEqual(result["changed"][0]["index"], 1)
        self.assertEqual(result["changed"][0]["changes"]["size"], {"left": 12, "right": 14})
        text = format_frame_compare(result)
        self.assertIn("帧级对比", text)
        self.assertIn("size: 12 -> 14", text)

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
        html_text = html_path.read_text(encoding="utf-8")
        self.assertIn('class="waveform-chart"', html_text)
        self.assertIn("音频波形图", html_text)
        self.assertIn("音频能量", html_text)
        self.assertIn('class="timeline-chart"', html_text)
        self.assertIn("帧/Packet 大小图", html_text)
        self.assertIn("Packet 统计", html_text)
        self.assertIn("统计摘要", html_text)
        self.assertIn("<th>Stream</th>", html_text)
        self.assertIn("packet_stats", csv_path.read_text(encoding="utf-8-sig"))
        note_json = ROOT / "cli_note_report.json"
        exit_code = cli_main(["analyze", str(sample_dir / "sample.wav"), "--note", "CLI 备注", "--json", str(note_json)])
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(note_json.read_text(encoding="utf-8"))["user_notes"], "CLI 备注")
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
                "--endian",
                "big",
                "--unsigned-pcm",
                "--json",
                str(pcm_json),
            ]
        )
        self.assertEqual(exit_code, 0)
        pcm_summary = json.loads(pcm_json.read_text(encoding="utf-8"))["media"]["summary"]
        self.assertEqual(pcm_summary["sample_rate"], 8000)
        self.assertEqual(pcm_summary["channels"], 1)
        self.assertEqual(pcm_summary["endian"], "big")
        self.assertFalse(pcm_summary["signed"])
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
        frame_compare_path = ROOT / "frame_compare.json"
        exit_code = cli_main(
            [
                "compare-frames",
                str(sample_dir / "sample.aac"),
                str(sample_dir / "sample.aac"),
                "--json",
                str(frame_compare_path),
            ]
        )
        self.assertEqual(exit_code, 0)
        frame_compare = json.loads(frame_compare_path.read_text(encoding="utf-8"))
        self.assertEqual(frame_compare["left_frames"], frame_compare["right_frames"])
        self.assertEqual(frame_compare["changed"], [])

    def test_release_manifest(self):
        manifest_root = ROOT / "manifest_root"
        artifact = write(manifest_root / "dist" / "AVScope-Setup.exe", b"setup")
        manifest = build_release_manifest(manifest_root, ["dist/AVScope-Setup.exe"])
        self.assertEqual(manifest["manifest_type"], "AVScope Release Manifest")
        self.assertEqual(manifest["root"], str(manifest_root))
        self.assertEqual(manifest["artifacts"][0]["path"], str(artifact))
        self.assertEqual(manifest["artifacts"][0]["size"], 5)
        self.assertEqual(len(manifest["artifacts"][0]["sha256"]), 64)
        output = manifest_root / "dist" / "manifest.json"
        written = write_release_manifest(manifest_root, output, ["dist/AVScope-Setup.exe"])
        self.assertEqual(len(written["artifacts"]), 1)
        self.assertTrue(output.exists())

    def test_sample_reports(self):
        report_root = ROOT / "sample_report_root"
        generate_samples(report_root / "samples")
        outputs = build_sample_reports(report_root, report_root / "dist" / "sample-reports")
        names = {path.name for path in outputs}
        self.assertIn("sample_wav_report.html", names)
        self.assertIn("sample_wav_report.json", names)
        self.assertIn("sample_wav_report.csv", names)
        self.assertIn("sample_mp4_report.html", names)
        self.assertIn("sample_protocol_compare.json", names)
        for path in outputs:
            self.assertTrue(path.exists(), str(path))
            self.assertGreater(path.stat().st_size, 0)

    def test_validation_report(self):
        report_root = ROOT / "validation_report_root"
        artifact = write(report_root / "dist" / "AVScope-Setup.exe", b"setup")
        report = build_validation_report(report_root, ["dist/AVScope-Setup.exe"])
        self.assertIn("AVScope 发布验证报告", report)
        self.assertIn("验证结果：通过", report)
        self.assertIn(str(artifact.stat().st_size), report)
        output = report_root / "dist" / "validation.md"
        written = write_validation_report(report_root, output, ["dist/AVScope-Setup.exe"])
        self.assertIn("AVScope-Setup.exe", written)
        self.assertTrue(output.exists())

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
        stats = build_frame_stats(frames)
        lines = format_frame_preview_lines(frames, stats)
        self.assertEqual(lines[0], "解析器帧列表: 已提取 2 帧，关键帧 1 帧，详见“帧列表”页。")
        self.assertEqual(lines[1], "首帧: offset=0x20, size=12, PTS=1.25s")
        self.assertEqual(lines[2], "帧大小: average=11.0 bytes, max=12 bytes (frame #0)")
        self.assertEqual(format_frame_preview_lines([]), [])

    def test_frame_stats_keyframe_intervals(self):
        frames = [
            FrameInfo(index=0, offset=0, size=20, keyframe=True),
            FrameInfo(index=1, offset=20, size=10, keyframe=False),
            FrameInfo(index=2, offset=30, size=12, keyframe=False),
            FrameInfo(index=3, offset=42, size=18, keyframe=True),
            FrameInfo(index=4, offset=60, size=14, keyframe=False),
            FrameInfo(index=6, offset=74, size=22, keyframe=True),
        ]
        stats = build_frame_stats(frames)
        self.assertEqual(stats["keyframe_indices"], [0, 3, 6])
        self.assertEqual(stats["keyframe_intervals"], [3, 3])
        self.assertEqual(stats["first_keyframe_index"], 0)
        self.assertEqual(stats["last_keyframe_index"], 6)
        self.assertEqual(stats["average_keyframe_interval"], 3.0)
        self.assertEqual(stats["max_keyframe_interval"], 3)
        lines = format_frame_preview_lines(frames, stats)
        self.assertTrue(any("关键帧间隔" in line and "max=3" in line for line in lines))

    def test_timeline_chart_items(self):
        frames = [
            FrameInfo(index=0, offset=0x100, size=20, keyframe=True),
            FrameInfo(index=1, offset=0x200, size=10, keyframe=False),
        ]
        items = timeline_chart_items(frames, [], limit=8)
        self.assertEqual(items[0]["size"], 20)
        self.assertTrue(items[0]["keyframe"])
        packet_items = timeline_chart_items([], [{"index": 3, "size": "12", "keyframe": True}], limit=8)
        self.assertEqual(packet_items[0]["kind"], "packet")
        sampled = timeline_chart_items([FrameInfo(index=i, offset=i, size=i + 1, keyframe=(i == 8)) for i in range(10)], [], limit=4)
        self.assertEqual(len(sampled), 4)
        self.assertTrue(any(item["keyframe"] for item in sampled))

    def test_timeline_summary_from_frames(self):
        frames = [
            FrameInfo(index=0, offset=0x100, size=1000, pts=0.0, dts=0.0, duration=0.04, keyframe=True),
            FrameInfo(index=1, offset=0x200, size=500, pts=0.04, dts=0.04, duration=0.04),
            FrameInfo(index=2, offset=0x300, size=900, pts=0.08, dts=0.08, duration=0.04, keyframe=True),
        ]
        summary = build_timeline_summary(frames, [], bucket_seconds=0.04)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["source"], "frame")
        self.assertEqual(summary["pts"]["span"], 0.08)
        self.assertEqual(summary["gop"]["keyframes"], 2)
        self.assertEqual(summary["gop"]["average_interval"], 2.0)
        self.assertTrue(summary["gop"]["groups_available"])
        self.assertEqual(summary["gop"]["group_count"], 2)
        self.assertEqual(summary["gop"]["groups"][0]["frames"], 2)
        self.assertEqual(summary["gop"]["groups"][0]["bytes"], 1500)
        self.assertEqual(summary["gop"]["max_group_frames"], 2)
        self.assertTrue(summary["bitrate"]["available"])
        lines = format_timeline_summary_lines(summary)
        self.assertTrue(any("码率曲线" in line for line in lines))
        self.assertTrue(any("GOP 结构" in line and "groups=2" in line for line in lines))

    def test_timeline_summary_marks_timestamp_anomalies(self):
        frames = [
            FrameInfo(index=0, offset=0x100, size=1000, pts=0.0, dts=0.0, duration=0.04, keyframe=True),
            FrameInfo(index=1, offset=0x200, size=500, pts=0.08, dts=0.08, duration=0.04),
            FrameInfo(index=2, offset=0x300, size=900, pts=0.04, dts=0.12, duration=0.04),
        ]
        summary = build_timeline_summary(frames, [], bucket_seconds=0.04)
        self.assertEqual(summary["pts"]["non_monotonic"], 1)
        self.assertEqual(summary["timestamp_anomalies"][0]["kind"], "pts")
        self.assertEqual(summary["timestamp_anomalies"][0]["index"], 2)
        self.assertEqual(timeline_anomaly_item_orders(summary), {2})
        self.assertEqual(timeline_item_row_tag(1, {2}), "normal")
        self.assertEqual(timeline_item_row_tag(2, {2}), "warning")
        issue_rows = timeline_issue_rows(summary)
        self.assertEqual(issue_rows[0]["source"], "Timestamp")
        self.assertIn("PTS non-monotonic", issue_rows[0]["kind"])
        lines = format_timeline_summary_lines(summary)
        self.assertTrue(any("时间戳异常" in line for line in lines))

    def test_timeline_issue_rows_include_transport_warnings(self):
        rows = timeline_issue_rows(
            {
                "rtp_sequence": {
                    "warnings": [
                        {
                            "ssrc": "0x12345678",
                            "item_order": 4,
                            "index": 1,
                            "previous": 100,
                            "expected": 101,
                            "current": 105,
                            "delta": 4,
                        }
                    ]
                },
                "pcr": {"warnings": [{"pid": "0x0100", "kind": "non_monotonic", "count": 2}]},
            }
        )
        self.assertEqual([row["source"] for row in rows], ["RTP", "PCR"])
        self.assertIn("expected=101", rows[0]["detail"])
        self.assertIn("count=2", rows[1]["detail"])

    def test_timeline_summary_from_packets_and_reports(self):
        packets = [
            {"index": 0, "stream_index": 0, "codec_type": "video", "pts": 0.0, "dts": 0.0, "duration": 0.04, "size": 1000, "keyframe": True},
            {"index": 1, "stream_index": 0, "codec_type": "video", "pts": 0.04, "dts": 0.04, "duration": 0.04, "size": 500, "keyframe": False},
            {"index": 2, "stream_index": 0, "codec_type": "video", "pts": 0.08, "dts": 0.08, "duration": 0.04, "size": 1200, "keyframe": True},
        ]
        summary = build_timeline_summary([], packets, bucket_seconds=0.04)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["source"], "packet")
        self.assertIn("0", summary["by_stream"])
        self.assertEqual(summary["by_stream"]["0"]["gop"]["keyframes"], 2)

        sample_dir = ROOT / "timeline_report_sample"
        generate_samples(sample_dir)
        result = self.analyzer.analyze(sample_dir / "sample.aac")
        self.assertIn("timeline_summary", result.media.summary)
        html_path = ROOT / "timeline_summary_report.html"
        csv_path = ROOT / "timeline_summary_report.csv"
        json_path = ROOT / "timeline_summary_report.json"
        export_html(result, html_path)
        export_csv(result, csv_path)
        export_json(result, json_path)
        self.assertIn("时间线曲线摘要", html_path.read_text(encoding="utf-8"))
        self.assertIn("码率曲线", html_path.read_text(encoding="utf-8"))
        self.assertIn("timeline_summary", csv_path.read_text(encoding="utf-8-sig"))
        self.assertIn("timeline_summary", json_path.read_text(encoding="utf-8"))

        frames = [
            FrameInfo(index=0, offset=0, size=1000, pts=0.0, dts=0.0, duration=0.04, keyframe=True),
            FrameInfo(index=1, offset=1000, size=500, pts=0.08, dts=0.04, duration=0.04),
            FrameInfo(index=2, offset=1500, size=1200, pts=0.04, dts=0.08, duration=0.04, keyframe=True),
        ]
        synthetic = ParseResult(
            MediaInfo(str(ROOT / "synthetic_timeline.aac"), 2700, "Synthetic Timeline"),
            ParseNode("synthetic_timeline.aac", "Synthetic", 0, 2700),
            frames=frames,
        )
        synthetic.media.summary["timeline_summary"] = build_timeline_summary(frames, [], bucket_seconds=0.04)
        synthetic_html = ROOT / "timeline_curves_report.html"
        export_html(synthetic, synthetic_html)
        synthetic_text = synthetic_html.read_text(encoding="utf-8")
        self.assertIn('class="pts"', synthetic_text)
        self.assertIn('class="dts"', synthetic_text)
        self.assertIn("Timeline chart legend", synthetic_text)
        self.assertIn('class="timestamp-anomaly"', synthetic_text)
        self.assertIn('class="timeline-issues"', synthetic_text)
        self.assertIn("PTS non-monotonic", synthetic_text)
        self.assertIn("GOP 结构图", synthetic_text)

    def test_video_preview_helpers(self):
        source = write(ROOT / "preview input.mp4", b"not a real video")
        target = preview_output_path(source, ROOT / "previews")
        self.assertEqual(target.parent, ROOT / "previews")
        self.assertEqual(target.suffix, ".png")
        self.assertNotIn(" ", target.name)
        later_target = preview_output_path(source, ROOT / "previews", position_seconds=2.5)
        self.assertNotEqual(target.name, later_target.name)
        self.assertIn("2_500s", later_target.name)

        png_path = write(ROOT / "preview.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x02\x80\x00\x00\x01\xe0")
        self.assertEqual(png_dimensions(png_path), (640, 480))
        with patch.dict("os.environ", {"AVSCOPE_FFMPEG": str(source)}):
            self.assertEqual(find_ffmpeg(), str(source))

    def test_video_preview_build_without_ffmpeg(self):
        with patch("avscope.ffmpeg_preview.find_ffmpeg", return_value=None):
            result = build_video_preview(ROOT / "missing.mp4", output_dir=ROOT / "previews")
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "ffmpeg not found")

    def test_video_preview_build_with_mocked_ffmpeg(self):
        source = write(ROOT / "mock-video.mp4", b"mock")
        commands = []

        def fake_run(command, capture_output, text, timeout, check):
            commands.append(command)
            if "-show_frames" in command:
                class Completed:
                    returncode = 0
                    stderr = ""
                    stdout = json.dumps(
                        {
                            "frames": [
                                {
                                    "best_effort_timestamp_time": "1.250000",
                                    "pkt_dts_time": "1.200000",
                                    "pkt_duration_time": "0.040000",
                                    "pkt_size": "2048",
                                    "pict_type": "I",
                                    "key_frame": 1,
                                    "width": 320,
                                    "height": 180,
                                    "pix_fmt": "yuv420p",
                                }
                            ]
                        }
                    )

                return Completed()
            output = Path(command[-1])
            write(output, b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x40\x00\x00\x00\xb4")

            class Completed:
                returncode = 0
                stderr = ""
                stdout = ""

            return Completed()

        with patch("avscope.ffmpeg_preview.find_ffmpeg", return_value="ffmpeg"), patch("avscope.ffmpeg_preview.find_ffprobe", return_value="ffprobe"), patch("avscope.ffmpeg_preview.subprocess.run", side_effect=fake_run):
            result = build_video_preview(source, output_dir=ROOT / "previews", position_seconds=1.25)
        self.assertTrue(result["available"])
        self.assertEqual(result["width"], 320)
        self.assertEqual(result["height"], 180)
        self.assertEqual(result["position_seconds"], 1.25)
        self.assertEqual(result["frame_info"]["frame_type"], "I")
        self.assertTrue(result["frame_info"]["keyframe"])
        lines = format_video_frame_info_lines(result["frame_info"])
        self.assertIn("PTS=1.25s", lines[0])
        self.assertIn("-ss", commands[0])
        self.assertIn("1.250", commands[0])
        self.assertIn("-show_frames", commands[1])
        self.assertTrue(Path(result["path"]).exists())

    def test_video_frame_probe_helper(self):
        source = write(ROOT / "frame-probe.mp4", b"mock")

        def fake_run(command, capture_output, text, timeout, check):
            self.assertIn("-read_intervals", command)
            self.assertIn("2.500%+1", command)

            class Completed:
                returncode = 0
                stderr = ""
                stdout = json.dumps({"frames": [{"pts_time": "2.5", "pict_type": "P", "key_frame": 0}]})

            return Completed()

        with patch("avscope.ffmpeg_preview.find_ffprobe", return_value="ffprobe"), patch("avscope.ffmpeg_preview.subprocess.run", side_effect=fake_run):
            info = probe_video_frame_info(source, 2.5)
        self.assertTrue(info["available"])
        self.assertEqual(info["pts"], 2.5)
        self.assertEqual(info["frame_type"], "P")
        self.assertFalse(info["keyframe"])

    def test_video_keyframe_time_from_packet_timeline(self):
        timeline = {
            "packets": [
                {"index": 0, "codec_type": "video", "pts": 0.0, "keyframe": True},
                {"index": 1, "codec_type": "video", "pts": 1.0, "keyframe": False},
                {"index": 2, "codec_type": "video", "pts": 2.0, "keyframe": True},
                {"index": 3, "codec_type": "audio", "pts": 2.5, "keyframe": True},
                {"index": 4, "codec_type": "video", "pts": 4.0, "keyframe": True},
            ]
        }
        next_match = find_video_keyframe_time(ROOT / "unused.mp4", start_seconds=1.5, direction=1, packet_timeline=timeline)
        previous_match = find_video_keyframe_time(ROOT / "unused.mp4", start_seconds=3.0, direction=-1, packet_timeline=timeline)
        self.assertEqual(next_match["position_seconds"], 2.0)
        self.assertEqual(next_match["packet_index"], 2)
        self.assertEqual(next_match["source"], "packet_timeline")
        self.assertEqual(previous_match["position_seconds"], 2.0)

    def test_video_keyframe_time_falls_back_to_ffprobe(self):
        source = write(ROOT / "keyframe-probe.mp4", b"mock")

        def fake_run(command, capture_output, text, timeout, check):
            self.assertIn("-skip_frame", command)
            self.assertIn("nokey", command)
            self.assertIn("1.001%+30.000", command)

            class Completed:
                returncode = 0
                stderr = ""
                stdout = json.dumps(
                    {
                        "frames": [
                            {"best_effort_timestamp_time": "0.5", "pict_type": "I", "key_frame": 1},
                            {"best_effort_timestamp_time": "2.25", "pict_type": "I", "key_frame": 1},
                        ]
                    }
                )

            return Completed()

        with patch("avscope.ffmpeg_preview.find_ffprobe", return_value="ffprobe"), patch("avscope.ffmpeg_preview.subprocess.run", side_effect=fake_run):
            match = find_video_keyframe_time(source, start_seconds=1.0, direction=1)
        self.assertTrue(match["available"])
        self.assertEqual(match["position_seconds"], 2.25)
        self.assertEqual(match["source"], "ffprobe")

    def test_video_frame_time_by_index(self):
        source = write(ROOT / "frame-index-probe.mp4", b"mock")

        def fake_run(command, capture_output, text, timeout, check):
            self.assertIn("-read_intervals", command)
            self.assertIn("%+#3", command)

            class Completed:
                returncode = 0
                stderr = ""
                stdout = json.dumps(
                    {
                        "frames": [
                            {"best_effort_timestamp_time": "0.0", "pict_type": "I", "key_frame": 1},
                            {"best_effort_timestamp_time": "0.04", "pict_type": "P", "key_frame": 0},
                            {
                                "best_effort_timestamp_time": "0.08",
                                "pkt_dts_time": "0.04",
                                "pkt_duration_time": "0.04",
                                "pkt_size": "1200",
                                "pict_type": "B",
                                "key_frame": 0,
                                "width": 320,
                                "height": 180,
                                "pix_fmt": "yuv420p",
                            },
                        ]
                    }
                )

            return Completed()

        with patch("avscope.ffmpeg_preview.find_ffprobe", return_value="ffprobe"), patch("avscope.ffmpeg_preview.subprocess.run", side_effect=fake_run):
            match = find_video_frame_time(source, 2)
        self.assertTrue(match["available"])
        self.assertEqual(match["frame_index"], 2)
        self.assertEqual(match["position_seconds"], 0.08)
        self.assertEqual(match["frame_info"]["frame_type"], "B")
        self.assertEqual(match["frame_info"]["width"], 320)

    def test_extract_media_stream_helpers(self):
        source = write(ROOT / "extract_source.mp4", b"media")
        target = ROOT / "extract" / "audio.aac"
        audio_command = build_extract_command("ffmpeg", source, target, "audio")
        self.assertIn("0:a:0", audio_command)
        self.assertIn("-c", audio_command)
        keyframe_command = build_extract_command("ffmpeg", source, target.with_suffix(".png"), "keyframe")
        self.assertIn("-skip_frame", keyframe_command)
        self.assertIn("-frames:v", keyframe_command)

        def fake_run(command, capture_output, text, timeout, check):
            output = Path(command[-1])
            write(output, b"stream")

            class Completed:
                returncode = 0
                stderr = ""

            return Completed()

        with patch("avscope.extract.find_ffmpeg", return_value="ffmpeg"), patch("avscope.extract.subprocess.run", side_effect=fake_run):
            result = extract_media_stream(source, target, "audio")
        self.assertTrue(result["available"])
        self.assertEqual(result["size"], 6)
        self.assertTrue(target.exists())

        with patch("avscope.extract.find_ffmpeg", return_value=None):
            missing = extract_media_stream(source, target, "audio")
        self.assertFalse(missing["available"])
        self.assertEqual(missing["error"], "ffmpeg not found")

    def test_yuv_preview_helpers(self):
        self.assertEqual(yuv_frame_size(2, 2, "yuv420p"), 6)
        white = yuv_to_rgb(bytes([235, 235, 235, 235, 128, 128]), 2, 2, "yuv420p")
        self.assertEqual(white, b"\xFF\xFF\xFF" * 4)
        black = yuv_to_rgb(bytes([16, 16, 16, 16, 128, 128]), 2, 2, "nv12")
        self.assertEqual(black, b"\x00\x00\x00" * 4)

    def test_yuv_preview_build(self):
        sample_dir = ROOT / "yuv_preview_sample"
        generate_samples(sample_dir)
        result = build_yuv_preview(sample_dir / "sample.yuv", 64, 48, "yuv420p", output_dir=ROOT / "yuv-previews")
        self.assertTrue(result["available"])
        self.assertEqual(result["width"], 64)
        self.assertEqual(result["height"], 48)
        ppm = Path(result["path"]).read_bytes()
        self.assertTrue(ppm.startswith(b"P6\n64 48\n255\n"))
        self.assertEqual(result["frame_index"], 0)
        self.assertEqual(result["total_frames"], 1)

        two_frame = write(ROOT / "two_frame.yuv", bytes([235, 235, 235, 235, 128, 128]) + bytes([16, 16, 16, 16, 128, 128]))
        first = build_yuv_preview(two_frame, 2, 2, "yuv420p", output_dir=ROOT / "yuv-previews", frame_index=0)
        second = build_yuv_preview(two_frame, 2, 2, "yuv420p", output_dir=ROOT / "yuv-previews", frame_index=1)
        self.assertTrue(first["available"])
        self.assertTrue(second["available"])
        self.assertEqual(second["frame_index"], 1)
        self.assertEqual(second["total_frames"], 2)
        self.assertNotEqual(first["path"], second["path"])
        self.assertNotEqual(Path(first["path"]).read_bytes(), Path(second["path"]).read_bytes())
        self.assertIn("frame-1", yuv_preview_output_path(two_frame, ROOT / "yuv-previews", 2, 2, "yuv420p", 1).name)

    def test_yuv_preview_rejects_incomplete_frame(self):
        path = write(ROOT / "short.yuv", b"\x10" * 4)
        result = build_yuv_preview(path, 4, 4, "yuv420p", output_dir=ROOT / "yuv-previews")
        self.assertFalse(result["available"])
        self.assertIn("incomplete", result["error"])
        out_of_range = build_yuv_preview(path, 1, 1, "yuyv422", output_dir=ROOT / "yuv-previews", frame_index=2)
        self.assertFalse(out_of_range["available"])
        self.assertIn("out of range", out_of_range["error"])

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
