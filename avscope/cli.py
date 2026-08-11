from __future__ import annotations

import argparse
import json
from pathlib import Path

from avscope.analyzer import Analyzer
from avscope.compare import compare_binary, compare_protocol
from avscope.report import export_html, export_json
from avscope.samples import generate_samples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="avscope", description="AVScope command line tools")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Analyze one media file")
    analyze.add_argument("file")
    analyze.add_argument("--html")
    analyze.add_argument("--json")

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
        result = Analyzer().analyze(args.file)
        if args.html:
            export_html(result, args.html)
        if args.json:
            export_json(result, args.json)
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
        _emit(document, args.json)
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


if __name__ == "__main__":
    raise SystemExit(main())
