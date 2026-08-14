from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, ParseNode, ParseResult
from avscope.parsers.base import FormatParser
from avscope.parsers.common import media_info, root_node, warn
from avscope.runtime import user_data_dir


PLUGIN_SCHEMA_VERSION = 1
DEFAULT_PLUGIN_DIR = user_data_dir() / "plugins"


class PluginTemplateParser(FormatParser):
    def __init__(self, manifest: dict[str, Any], manifest_path: Path):
        self.manifest = manifest
        self.manifest_path = manifest_path
        self.name = str(manifest.get("name") or manifest_path.stem)
        self.extensions = tuple(str(item).lower() for item in manifest.get("extensions", []))

    def probe(self, source: ByteSource) -> bool:
        match = self.manifest.get("match", {})
        offset = int(match.get("offset", 0))
        expected = _hex_to_bytes(str(match.get("hex", "")))
        if not expected:
            return False
        return source.read_at(offset, len(expected)) == expected

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        header = root.add_child(ParseNode("template_fields", "plugin_template", 0, min(source.size, 256)))
        diagnostics = []
        for item in self.manifest.get("fields", []):
            try:
                header.fields.append(_field_from_template(source, item))
            except (OSError, ValueError, TypeError) as exc:
                diagnostics.append(warn(f"插件字段解析失败 {item.get('name', '<unnamed>')}: {exc}", item.get("offset"), self.name))
        summary = {
            "plugin": True,
            "plugin_manifest": str(self.manifest_path),
            "schema_version": self.manifest.get("schema_version"),
        }
        return ParseResult(media_info(source, self.name, **summary), root, diagnostics=diagnostics)


def load_plugin_parsers(plugin_dir: str | Path | None = None) -> list[PluginTemplateParser]:
    parsers: list[PluginTemplateParser] = []
    for folder in _candidate_plugin_dirs(plugin_dir):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                if int(manifest.get("schema_version", 0)) != PLUGIN_SCHEMA_VERSION:
                    continue
                parsers.append(PluginTemplateParser(manifest, path))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
    return parsers


def build_plugin_template_manifest(name: str, extension: str, magic_hex: str) -> dict[str, Any]:
    clean_name = str(name).strip() or "Custom Template"
    clean_extension = normalize_extension(extension)
    clean_magic = normalize_magic_hex(magic_hex)
    magic_size = len(_hex_to_bytes(clean_magic))
    return {
        "schema_version": PLUGIN_SCHEMA_VERSION,
        "name": clean_name,
        "extensions": [clean_extension],
        "match": {
            "offset": 0,
            "hex": clean_magic,
        },
        "fields": [
            {
                "name": "magic",
                "offset": 0,
                "size": magic_size,
                "type": "hex",
                "description": "模板匹配魔数",
            },
            {
                "name": "version",
                "offset": magic_size,
                "size": 1,
                "type": "uint",
                "description": "示例版本字段，可按实际协议修改",
            },
            {
                "name": "payload",
                "offset": magic_size + 1,
                "size": 4,
                "type": "hex",
                "description": "示例载荷字段，可按实际协议修改",
            },
        ],
    }


def write_plugin_template(
    name: str,
    extension: str,
    magic_hex: str,
    plugin_dir: str | Path = DEFAULT_PLUGIN_DIR,
    overwrite: bool = False,
) -> Path:
    manifest = build_plugin_template_manifest(name, extension, magic_hex)
    directory = Path(plugin_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{plugin_template_filename(str(manifest['name']))}.json"
    if path.exists() and not overwrite:
        raise FileExistsError(str(path))
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def plugin_template_filename(name: str) -> str:
    clean = "".join(char.lower() if char.isalnum() else "_" for char in str(name).strip())
    clean = "_".join(part for part in clean.split("_") if part)
    return clean[:48] or "custom_template"


def normalize_extension(extension: str) -> str:
    clean = str(extension).strip().lower()
    if not clean:
        raise ValueError("扩展名不能为空")
    if not clean.startswith("."):
        clean = f".{clean}"
    if any(char in clean for char in "\\/:*?\"<>|"):
        raise ValueError(f"扩展名包含非法字符: {extension}")
    return clean


def normalize_magic_hex(magic_hex: str) -> str:
    data = _hex_to_bytes(str(magic_hex))
    if not data:
        raise ValueError("魔数必须是偶数长度的十六进制字节")
    return data.hex(" ").upper()


def _candidate_plugin_dirs(plugin_dir: str | Path | None) -> list[Path]:
    if plugin_dir is not None:
        return [Path(plugin_dir)]
    executable_dir = Path(sys.executable).resolve().parent
    source_root = Path(__file__).resolve().parent.parent
    candidates = [
        executable_dir / "plugins",
        executable_dir / "_internal" / "plugins",
        source_root / "plugins",
        user_data_dir() / "plugins",
    ]
    seen = set()
    unique = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            unique.append(path)
            seen.add(resolved)
    return unique


def _field_from_template(source: ByteSource, item: dict[str, Any]) -> FieldInfo:
    name = str(item["name"])
    offset = int(item.get("offset", 0))
    size = int(item.get("size", 0))
    if offset < 0 or size < 0 or offset + size > source.size:
        raise ValueError("字段范围超出文件边界")
    data = source.read_at(offset, size)
    field_type = str(item.get("type", "hex")).lower()
    endian = str(item.get("endian", "big")).lower()
    if field_type == "ascii":
        value = data.decode("ascii", errors="replace")
    elif field_type == "uint":
        value = int.from_bytes(data, "little" if endian == "little" else "big", signed=False)
    elif field_type == "int":
        value = int.from_bytes(data, "little" if endian == "little" else "big", signed=True)
    else:
        value = data.hex(" ").upper()
    return FieldInfo(
        name,
        value,
        offset,
        size,
        data.hex(" ").upper(),
        bit_offset=offset * 8,
        bit_length=size * 8,
        description=str(item.get("description", "")),
    )


def _hex_to_bytes(text: str) -> bytes:
    cleaned = "".join(ch for ch in text if ch not in " \t\r\n_-:")
    if not cleaned or len(cleaned) % 2:
        return b""
    return bytes.fromhex(cleaned)
