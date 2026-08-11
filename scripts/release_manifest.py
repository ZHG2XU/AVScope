from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path


DEFAULT_ARTIFACTS = [
    "dist/AVScope/AVScope.exe",
    "dist/AVScope/_internal/ffprobe.exe",
    "dist/AVScope/_internal/ffmpeg.exe",
    "dist/AVScope/_internal/plugins/demo_magic.json",
    "dist/AVScope-Setup.exe",
    "dist/AVScope-portable-win-x64.zip",
    "dist/AVScope-portable-source.zip",
]


def build_release_manifest(root: str | Path, artifacts: list[str] | None = None) -> dict:
    root_path = Path(root)
    rows = []
    for relative in artifacts or DEFAULT_ARTIFACTS:
        path = root_path / relative
        if not path.exists():
            raise FileNotFoundError(f"Missing artifact: {path}")
        if not path.is_file():
            raise ValueError(f"Artifact is not a file: {path}")
        rows.append(
            {
                "path": str(path),
                "relative_path": relative.replace("/", "\\"),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return {
        "manifest_type": "AVScope Release Manifest",
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root_path),
        "artifacts": rows,
    }


def write_release_manifest(root: str | Path, output: str | Path, artifacts: list[str] | None = None) -> dict:
    manifest = build_release_manifest(root, artifacts)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write AVScope release artifact manifest")
    parser.add_argument("--root", default="G:/AVScope")
    parser.add_argument("--output", default="G:/AVScope/dist/AVScope-release-manifest.json")
    args = parser.parse_args(argv)
    manifest = write_release_manifest(args.root, args.output)
    print(json.dumps({"output": str(args.output), "artifacts": len(manifest["artifacts"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
