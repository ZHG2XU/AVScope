from __future__ import annotations

import argparse
import json
from pathlib import Path

from avscope.analyzer import Analyzer
from avscope.compare import compare_binary, compare_frames, compare_protocol, format_binary_compare, format_frame_compare
from avscope.ffmpeg_preview import build_video_preview
from avscope.report import export_csv, export_html, export_json
from avscope.samples import generate_samples
from avscope.yuv_preview import build_yuv_preview


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="avscope", description="AVScope command line tools")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Analyze one media file")
    analyze.add_argument("file")
    analyze.add_argument("--html")
    analyze.add_argument("--json")
    analyze.add_argument("--csv")
    analyze.add_argument("--note", action="append", default=[], help="User note to include in exported reports")
    analyze.add_argument("--notes-file", help="UTF-8 text file with user notes to include in exported reports")
    analyze.add_argument("--sample-rate", type=int, help="Raw PCM sample rate")
    analyze.add_argument("--channels", type=int, help="Raw PCM channel count")
    analyze.add_argument("--bits-per-sample", type=int, help="Raw PCM bits per sample")
    analyze.add_argument("--endian", choices=("little", "big"), help="Raw PCM sample byte order")
    analyze.add_argument("--unsigned-pcm", action="store_true", help="Treat Raw PCM samples as unsigned integers")
    analyze.add_argument("--width", type=int, help="Raw YUV frame width")
    analyze.add_argument("--height", type=int, help="Raw YUV frame height")
    analyze.add_argument("--pixel-format", help="Raw YUV pixel format, such as yuv420p/nv12/yuyv422")
    analyze.add_argument("--fps", type=float, help="Raw YUV frame rate")
    analyze.add_argument("--preview-dir", help="Generate GUI preview assets in this directory")
    analyze.add_argument("--preview-position", type=float, default=0.0, help="Video preview position in seconds")
    analyze.add_argument("--preview-frame", type=int, default=0, help="Raw YUV preview frame index")

    binary = sub.add_parser("compare-binary", help="Compare two files byte by byte")
    binary.add_argument("left")
    binary.add_argument("right")
    binary.add_argument("--json")

    protocol = sub.add_parser("compare-protocol", help="Compare parsed protocol trees")
    protocol.add_argument("left")
    protocol.add_argument("right")
    protocol.add_argument("--json")

    frames = sub.add_parser("compare-frames", help="Compare parsed frame lists")
    frames.add_argument("left")
    frames.add_argument("right")
    frames.add_argument("--json")

    samples = sub.add_parser("make-samples", help="Generate small validation samples")
    samples.add_argument("--out", default="G:/AVScope/samples")

    args = parser.parse_args(argv)
    if args.command == "analyze":
        result = Analyzer().analyze(args.file, _analyze_options(args))
        if args.preview_dir:
            _attach_previews(result, args.preview_dir, args.preview_position, args.preview_frame)
        notes = _report_notes(args)
        if args.html:
            export_html(result, args.html, notes=notes)
        if args.json:
            export_json(result, args.json, notes=notes)
        if args.csv:
            export_csv(result, args.csv, notes=notes)
        print(json.dumps({"format": result.media.format_name, "size": result.media.size, "diagnostics": len(result.diagnostics)}, ensure_ascii=False))
        return 0
    if args.command == "compare-binary":
        result = compare_binary(args.left, args.right)
        document = {
            "compare_type": "binary",
            "left_path": str(args.left),
            "right_path": str(args.right),
            "equal": result.equal,
            "left_size": result.left_size,
            "right_size": result.right_size,
            "chunks": [
                {"offset": c.offset, "left": c.left.hex(" ").upper(), "right": c.right.hex(" ").upper()}
                for c in result.chunks
            ],
        }
        if args.json:
            _emit(document, args.json)
        else:
            print(format_binary_compare(result))
        return 0
    if args.command == "compare-protocol":
        document = compare_protocol(args.left, args.right)
        _emit(document, args.json)
        return 0
    if args.command == "compare-frames":
        document = compare_frames(args.left, args.right)
        if args.json:
            _emit(document, args.json)
        else:
            print(format_frame_compare(document))
        return 0
    if args.command == "make-samples":
        files = generate_samples(args.out)
        print(json.dumps({"samples": [str(p) for p in files]}, ensure_ascii=False, indent=2))
        return 0
    return 2


def _emit(document: dict, path: str | None) -> None:
    text = json.dumps(document, ensure_ascii=False, indent=2)
    if path:
        Path(path).write_text(text, encoding="utf-8")
    print(text)


def _analyze_options(args: argparse.Namespace) -> dict:
    mapping = {
        "sample_rate": args.sample_rate,
        "channels": args.channels,
        "bits_per_sample": args.bits_per_sample,
        "endian": args.endian,
        "signed": False if args.unsigned_pcm else None,
        "width": args.width,
        "height": args.height,
        "pixel_format": args.pixel_format,
        "fps": args.fps,
    }
    return {key: value for key, value in mapping.items() if value is not None}


def _report_notes(args: argparse.Namespace) -> str:
    notes = [str(note).strip() for note in getattr(args, "note", []) if str(note).strip()]
    notes_file = getattr(args, "notes_file", None)
    if notes_file:
        notes.append(Path(notes_file).read_text(encoding="utf-8").strip())
    return "\n".join(note for note in notes if note)


def _attach_previews(result, output_dir: str, position_seconds: float = 0.0, frame_index: int = 0) -> None:
    summary = result.media.summary
    if result.media.format_name == "Raw YUV":
        summary["yuv_preview"] = build_yuv_preview(
            result.media.path,
            summary.get("width", 0),
            summary.get("height", 0),
            summary.get("pixel_format", "yuv420p"),
            output_dir=output_dir,
            frame_index=max(0, frame_index),
        )
        return
    streams = summary.get("ffprobe", {}).get("streams", [])
    if any(stream.get("codec_type") == "video" for stream in streams):
        summary["video_preview"] = build_video_preview(
            result.media.path,
            output_dir=output_dir,
            position_seconds=max(0.0, position_seconds),
        )


if __name__ == "__main__":
    raise SystemExit(main())
