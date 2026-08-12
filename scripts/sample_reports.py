from __future__ import annotations

import argparse
import json
from pathlib import Path

from avscope.analyzer import Analyzer
from avscope.compare import compare_frames, compare_protocol
from avscope.report import export_csv, export_html, export_json


DEFAULT_OUTPUTS = [
    "sample_wav_report.html",
    "sample_wav_report.json",
    "sample_wav_report.csv",
    "sample_mp4_report.html",
    "sample_mp4_report.json",
    "sample_rtp_video_report.html",
    "sample_rtp_video_report.json",
    "sample_rtp_video_report.csv",
    "sample_sip_sdp_report.html",
    "sample_sip_sdp_report.json",
    "sample_sip_sdp_report.csv",
    "sample_rtcp_feedback_report.html",
    "sample_rtcp_feedback_report.json",
    "sample_rtcp_feedback_report.csv",
    "sample_rtp_timing_report.html",
    "sample_rtp_timing_report.json",
    "sample_rtp_timing_report.csv",
    "sample_rtcp_twcc_report.html",
    "sample_rtcp_twcc_report.json",
    "sample_rtcp_twcc_report.csv",
    "sample_protocol_compare.json",
    "sample_frame_compare.json",
]


def build_sample_reports(root: str | Path, output_dir: str | Path) -> list[Path]:
    root_path = Path(root)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    analyzer = Analyzer()

    wav = root_path / "samples" / "sample.wav"
    wav_result = analyzer.analyze(wav)
    export_html(wav_result, output_path / "sample_wav_report.html", notes="AVScope 交付示例报告：WAV 音频结构与波形。")
    export_json(wav_result, output_path / "sample_wav_report.json", notes="AVScope 交付示例报告：WAV 音频结构与波形。")
    export_csv(wav_result, output_path / "sample_wav_report.csv", notes="AVScope 交付示例报告：WAV 音频结构与波形。")

    mp4 = root_path / "samples" / "sample.mp4"
    mp4_result = analyzer.analyze(mp4)
    export_html(mp4_result, output_path / "sample_mp4_report.html", notes="AVScope 交付示例报告：MP4 box 与 sample table。")
    export_json(mp4_result, output_path / "sample_mp4_report.json", notes="AVScope 交付示例报告：MP4 box 与 sample table。")

    rtp_video = root_path / "samples" / "sample_rtp_video.pcap"
    rtp_video_result = analyzer.analyze(rtp_video)
    rtp_note = "AVScope 交付示例报告：RTP H.264/H.265 聚合、分片重组与负载诊断。"
    export_html(rtp_video_result, output_path / "sample_rtp_video_report.html", notes=rtp_note)
    export_json(rtp_video_result, output_path / "sample_rtp_video_report.json", notes=rtp_note)
    export_csv(rtp_video_result, output_path / "sample_rtp_video_report.csv", notes=rtp_note)

    sip_sdp = root_path / "samples" / "sample_sip_sdp.pcap"
    sip_sdp_result = analyzer.analyze(sip_sdp)
    sip_note = "AVScope 交付示例报告：SIP/SDP Call-ID、媒体协商与动态 PT 映射。"
    export_html(sip_sdp_result, output_path / "sample_sip_sdp_report.html", notes=sip_note)
    export_json(sip_sdp_result, output_path / "sample_sip_sdp_report.json", notes=sip_note)
    export_csv(sip_sdp_result, output_path / "sample_sip_sdp_report.csv", notes=sip_note)

    rtcp_feedback = root_path / "samples" / "sample_rtcp_feedback.pcap"
    rtcp_feedback_result = analyzer.analyze(rtcp_feedback)
    rtcp_note = "AVScope 交付示例报告：RTCP NACK/PLI/FIR 控制反馈、SDES 与 BYE 会话事件。"
    export_html(rtcp_feedback_result, output_path / "sample_rtcp_feedback_report.html", notes=rtcp_note)
    export_json(rtcp_feedback_result, output_path / "sample_rtcp_feedback_report.json", notes=rtcp_note)
    export_csv(rtcp_feedback_result, output_path / "sample_rtcp_feedback_report.csv", notes=rtcp_note)

    rtp_timing = root_path / "samples" / "sample_rtp_timing.pcap"
    rtp_timing_result = analyzer.analyze(rtp_timing)
    timing_note = "AVScope 交付示例报告：RTP RFC 3550 Jitter、到达间隔、媒体间隔与突发延迟。"
    export_html(rtp_timing_result, output_path / "sample_rtp_timing_report.html", notes=timing_note)
    export_json(rtp_timing_result, output_path / "sample_rtp_timing_report.json", notes=timing_note)
    export_csv(rtp_timing_result, output_path / "sample_rtp_timing_report.csv", notes=timing_note)

    rtcp_twcc = root_path / "samples" / "sample_rtcp_twcc.pcap"
    rtcp_twcc_result = analyzer.analyze(rtcp_twcc)
    twcc_note = "AVScope 交付示例报告：WebRTC RTCP TWCC 包状态、接收 Delta、丢包与 REMB 带宽估计。"
    export_html(rtcp_twcc_result, output_path / "sample_rtcp_twcc_report.html", notes=twcc_note)
    export_json(rtcp_twcc_result, output_path / "sample_rtcp_twcc_report.json", notes=twcc_note)
    export_csv(rtcp_twcc_result, output_path / "sample_rtcp_twcc_report.csv", notes=twcc_note)

    changed_mp4 = root_path / "samples" / "sample_changed.mp4"
    protocol_compare = compare_protocol(mp4, changed_mp4)
    (output_path / "sample_protocol_compare.json").write_text(json.dumps(protocol_compare, ensure_ascii=False, indent=2), encoding="utf-8")

    aac = root_path / "samples" / "sample.aac"
    frame_compare = compare_frames(aac, aac)
    (output_path / "sample_frame_compare.json").write_text(json.dumps(frame_compare, ensure_ascii=False, indent=2), encoding="utf-8")

    return [output_path / name for name in DEFAULT_OUTPUTS]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write AVScope sample analysis reports")
    parser.add_argument("--root", default="G:/AVScope")
    parser.add_argument("--output-dir", default="G:/AVScope/dist/sample-reports")
    args = parser.parse_args(argv)
    outputs = build_sample_reports(args.root, args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir), "reports": [str(path) for path in outputs]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
