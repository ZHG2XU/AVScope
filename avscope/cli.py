from __future__ import annotations

import argparse
import json
from pathlib import Path

from avscope.analyzer import Analyzer
from avscope.compare import compare_binary, compare_protocol, format_binary_compare
from avscope.report import export_csv, export_html, export_json
from avscope.samples import generate_samples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="avscope", description="AVScope command line tools")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Analyze one media file")
    analyze.add_argument("file")
    analyze.add_argument("--html")
    analyze.add_argument("--json")
    analyze.add_argument("--csv")
    analyze.add_argument("--sample-rate", type=int, help="Raw PCM sample rate")
    analyze.add_argument("--channels", type=int, help="Raw PCM channel count")
    analyze.add_argument("--bits-per-sample", type=int, help="Raw PCM bits per sample")
    analyze.add_argument("--endian", choices=("little", "big"), help="Raw PCM sample byte order")
    analyze.add_argument("--unsigned-pcm", action="store_true", help="Treat Raw PCM samples as unsigned integers")
    analyze.add_argument("--width", type=int, help="Raw YUV frame width")
    analyze.add_argument("--height", type=int, help="Raw YUV frame height")
    analyze.add_argument("--pixel-format", help="Raw YUV pixel format, such as yuv420p/nv12/yuyv422")
    analyze.add_argument("--fps", type=float, help="Raw YUV frame rate")

    binary = sub.add_parser("compare-binary", help="Compare two files byte by byte")
    binary.add_argument("left")
    binary.add_argument("right")
    binary.add_argument("--json")

    protocol = sub.add_parser("compare-protocol", help="Compare parsed protocol trees")
    protocol.add_argument("left")
    protocol.add_argument("right")
    protocol.add_argument("--json")

    samples = sub.add_parser("make-samples", help="Generate small validation samples")
    samples.add_argument("--out", default="G:/AVScope/samples")

    args = parser.parse_args(argv)
    if args.command == "analyze":
        result = Analyzer().analyze(args.file, _analyze_options(args))
        if args.html:
            export_html(result, args.html)
        if args.json:
            export_json(result, args.json)
        if args.csv:
            export_csv(result, args.csv)
        print(json.dumps({"format": result.media.format_name, "size": result.media.size, "diagnostics": len(result.diagnostics)}, ensure_ascii=False))
        return 0
    if args.command == "compare-binary":
        result = compare_binary(args.left, args.right)
        document = {
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


if __name__ == "__main__":
    raise SystemExit(main())
