from __future__ import annotations

from pathlib import Path

from avscope.analyzer import Analyzer
from avscope.byte_source import ByteSource
from avscope.models import CompareChunk, CompareResult, ParseNode


def compare_binary(left_path: str | Path, right_path: str | Path, limit: int = 256) -> CompareResult:
    chunks: list[CompareChunk] = []
    with ByteSource(left_path) as left, ByteSource(right_path) as right:
        max_size = max(left.size, right.size)
        offset = 0
        block_size = 64 * 1024
        equal = left.size == right.size
        while offset < max_size and len(chunks) < limit:
            ldata = left.read_at(offset, block_size)
            rdata = right.read_at(offset, block_size)
            if ldata != rdata:
                equal = False
                local = _first_diff(ldata, rdata)
                diff_offset = offset + local
                chunks.append(CompareChunk(diff_offset, left.read_at(diff_offset, 32), right.read_at(diff_offset, 32)))
            offset += block_size
        return CompareResult(str(left_path), str(right_path), left.size, right.size, equal, chunks)


def _first_diff(left: bytes, right: bytes) -> int:
    common = min(len(left), len(right))
    for index in range(common):
        if left[index] != right[index]:
            return index
    return common


def compare_protocol(left_path: str | Path, right_path: str | Path, limit: int = 500) -> dict:
    analyzer = Analyzer()
    left = analyzer.analyze(left_path)
    right = analyzer.analyze(right_path)
    left_nodes = _flatten_nodes(left.root)
    right_nodes = _flatten_nodes(right.root)
    left_keys = {item["path"]: item for item in left_nodes}
    right_keys = {item["path"]: item for item in right_nodes}
    added = [right_keys[key] for key in sorted(right_keys.keys() - left_keys.keys())[:limit]]
    removed = [left_keys[key] for key in sorted(left_keys.keys() - right_keys.keys())[:limit]]
    changed = []
    for key in sorted(left_keys.keys() & right_keys.keys()):
        lnode = left_keys[key]
        rnode = right_keys[key]
        changes = {}
        for field in ("node_type", "offset", "size", "severity"):
            if lnode[field] != rnode[field]:
                changes[field] = {"left": lnode[field], "right": rnode[field]}
        field_changes = _compare_fields(lnode.get("fields", {}), rnode.get("fields", {}))
        if field_changes:
            changes["fields"] = field_changes
        if changes:
            changed.append({"path": key, "changes": changes})
        if len(changed) >= limit:
            break
    return {
        "left_path": str(left_path),
        "right_path": str(right_path),
        "left_format": left.media.format_name,
        "right_format": right.media.format_name,
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def _flatten_nodes(root: ParseNode) -> list[dict]:
    rows: list[dict] = []

    def walk(node: ParseNode, prefix: str, is_root: bool = False) -> None:
        path_name = "<root>" if is_root else node.name
        path = f"{prefix}/{path_name}" if prefix else path_name
        rows.append(
            {
                "path": path,
                "name": node.name,
                "node_type": node.node_type,
                "offset": node.offset,
                "size": node.size,
                "severity": node.severity.value,
                "field_count": len(node.fields),
                "child_count": len(node.children),
                "fields": {
                    field.name: {
                        "value": str(field.value),
                        "hex": field.hex_value,
                        "severity": field.severity.value,
                    }
                    for field in node.fields
                },
            }
        )
        for child in node.children:
            walk(child, path)

    walk(root, "", True)
    return rows


def format_protocol_compare(result: dict, max_items: int = 80) -> str:
    lines = [
        "协议结构对比",
        f"左侧: {result.get('left_path', '')}",
        f"右侧: {result.get('right_path', '')}",
        f"格式: {result.get('left_format', '')} -> {result.get('right_format', '')}",
        "",
        f"新增节点: {len(result.get('added', []))}",
        f"删除节点: {len(result.get('removed', []))}",
        f"变化节点: {len(result.get('changed', []))}",
    ]
    for title, key in [("新增节点", "added"), ("删除节点", "removed")]:
        items = result.get(key, [])[:max_items]
        if not items:
            continue
        lines.extend(["", title])
        for item in items:
            lines.append(f"  {item['path']} offset=0x{item['offset']:X} size={item['size']} type={item['node_type']}")
    changed = result.get("changed", [])[:max_items]
    if changed:
        lines.extend(["", "变化节点"])
        for item in changed:
            lines.append(f"  {item['path']}")
            for name, change in item.get("changes", {}).items():
                lines.append(f"    {name}: {change.get('left')} -> {change.get('right')}")
    return "\n".join(lines)


def _compare_fields(left: dict, right: dict) -> dict:
    changes = {}
    for name in sorted(set(left) | set(right)):
        if name not in left:
            changes[name] = {"left": None, "right": right[name]}
        elif name not in right:
            changes[name] = {"left": left[name], "right": None}
        elif left[name] != right[name]:
            changes[name] = {"left": left[name], "right": right[name]}
    return changes
