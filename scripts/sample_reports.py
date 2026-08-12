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
