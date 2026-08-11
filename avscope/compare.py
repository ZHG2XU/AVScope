from __future__ import annotations

from pathlib import Path

from avscope.analyzer import Analyzer
from avscope.byte_source import ByteSource
from avscope.models import CompareChunk, CompareResult, FrameInfo, ParseNode


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
                local_offset = 0
                block_limit = max(len(ldata), len(rdata))
                while local_offset < block_limit and len(chunks) < limit:
                    local = _first_diff(ldata[local_offset:], rdata[local_offset:])
                    if local is None:
                        break
                    diff_offset = offset + local_offset + local
                    chunks.append(CompareChunk(diff_offset, left.read_at(diff_offset, 32), right.read_at(diff_offset, 32)))
                    local_offset += local + 32
            offset += block_size
        return CompareResult(str(left_path), str(right_path), left.size, right.size, equal, chunks)


def _first_diff(left: bytes, right: bytes) -> int | None:
    common = min(len(left), len(right))
    for index in range(common):
        if left[index] != right[index]:
            return index
    if len(left) == len(right):
        return None
    return common


def format_binary_compare(result: CompareResult, max_chunks: int = 80) -> str:
    lines = [
        "二进制对比",
        f"左侧: {result.left_path}",
        f"右侧: {result.right_path}",
        f"结果: {'相同' if result.equal else '不同'}",
        f"大小: {result.left_size} -> {result.right_size} bytes",
        f"差异窗口: {len(result.chunks)}",
    ]
    if not result.chunks:
        return "\n".join(lines)
    lines.extend(
        [
            "",
            "差异列表",
            "Offset       Left Hex                                      Left ASCII        Right Hex                                     Right ASCII       Mark",
        ]
    )
    for chunk in result.chunks[:max_chunks]:
        left_hex = _hex_columns(chunk.left)
        right_hex = _hex_columns(chunk.right)
        left_ascii = _ascii_column(chunk.left)
        right_ascii = _ascii_column(chunk.right)
        marks = _diff_marks(chunk.left, chunk.right)
        lines.append(f"0x{chunk.offset:08X}  {left_hex}  {left_ascii}  {right_hex}  {right_ascii}  {marks}")
    if len(result.chunks) > max_chunks:
        lines.append(f"... 还有 {len(result.chunks) - max_chunks} 个差异窗口未显示")
    return "\n".join(lines)


def _hex_columns(data: bytes, width: int = 16) -> str:
    return " ".join(f"{byte:02X}" for byte in data[:width]).ljust(width * 3 - 1)


def _ascii_column(data: bytes, width: int = 16) -> str:
    text = "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data[:width])
    return f"|{text.ljust(width)}|"


def _diff_marks(left: bytes, right: bytes, width: int = 16) -> str:
    marks = []
    for index in range(width):
        lvalue = left[index] if index < len(left) else None
        rvalue = right[index] if index < len(right) else None
        marks.append("^^" if lvalue != rvalue else "  ")
    return " ".join(marks).rstrip()


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


def compare_frames(left_path: str | Path, right_path: str | Path, limit: int = 500) -> dict:
    analyzer = Analyzer()
    left = analyzer.analyze(left_path)
    right = analyzer.analyze(right_path)
    left_frames = {frame.index: frame for frame in left.frames}
    right_frames = {frame.index: frame for frame in right.frames}
    added = [_frame_row(right_frames[index]) for index in sorted(right_frames.keys() - left_frames.keys())[:limit]]
    removed = [_frame_row(left_frames[index]) for index in sorted(left_frames.keys() - right_frames.keys())[:limit]]
    changed = []
    for index in sorted(left_frames.keys() & right_frames.keys()):
        changes = _compare_frame_fields(left_frames[index], right_frames[index])
        if changes:
            changed.append({"index": index, "changes": changes})
        if len(changed) >= limit:
            break
    return {
        "left_path": str(left_path),
        "right_path": str(right_path),
        "left_format": left.media.format_name,
        "right_format": right.media.format_name,
        "left_frames": len(left.frames),
        "right_frames": len(right.frames),
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def _frame_row(frame: FrameInfo) -> dict:
    return {
        "index": frame.index,
        "offset": frame.offset,
        "size": frame.size,
        "pts": frame.pts,
        "dts": frame.dts,
        "duration": frame.duration,
        "frame_type": frame.frame_type,
        "keyframe": frame.keyframe,
    }


def _compare_frame_fields(left: FrameInfo, right: FrameInfo) -> dict:
    changes = {}
    for field in ("offset", "size", "pts", "dts", "duration", "frame_type", "keyframe"):
        left_value = getattr(left, field)
        right_value = getattr(right, field)
        if _same_frame_value(left_value, right_value):
            continue
        changes[field] = {"left": left_value, "right": right_value}
    return changes


def _same_frame_value(left, right) -> bool:
    if isinstance(left, float) or isinstance(right, float):
        if left is None or right is None:
            return left is right
        try:
            return abs(float(left) - float(right)) <= 0.000001
        except (TypeError, ValueError):
            return False
    return left == right


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


def format_frame_compare(result: dict, max_items: int = 80) -> str:
    lines = [
        "帧级对比",
        f"左侧: {result.get('left_path', '')}",
        f"右侧: {result.get('right_path', '')}",
        f"格式: {result.get('left_format', '')} -> {result.get('right_format', '')}",
        f"帧数: {result.get('left_frames', 0)} -> {result.get('right_frames', 0)}",
        "",
        f"新增帧: {len(result.get('added', []))}",
        f"删除帧: {len(result.get('removed', []))}",
        f"变化帧: {len(result.get('changed', []))}",
    ]
    for title, key in [("新增帧", "added"), ("删除帧", "removed")]:
        items = result.get(key, [])[:max_items]
        if not items:
            continue
        lines.extend(["", title])
        for item in items:
            lines.append(_format_frame_row(item))
    changed = result.get("changed", [])[:max_items]
    if changed:
        lines.extend(["", "变化帧"])
        for item in changed:
            lines.append(f"  frame #{item.get('index')}")
            for name, change in item.get("changes", {}).items():
                lines.append(f"    {name}: {change.get('left')} -> {change.get('right')}")
    return "\n".join(lines)


def _format_frame_row(frame: dict) -> str:
    return (
        f"  #{frame.get('index')} offset=0x{int(frame.get('offset', 0)):X} "
        f"size={frame.get('size')} pts={frame.get('pts')} "
        f"type={frame.get('frame_type', '')} key={frame.get('keyframe')}"
    )


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
