from __future__ import annotations

from pathlib import Path


class SearchPatternError(ValueError):
    pass


def parse_search_pattern(text: str, mode: str) -> bytes:
    value = text.strip()
    if not value:
        raise SearchPatternError("搜索内容不能为空")
    if mode == "hex":
        compact = value.replace(" ", "").replace("\t", "").replace("_", "")
        if compact.startswith("0x"):
            compact = compact[2:]
        if len(compact) % 2:
            raise SearchPatternError("十六进制搜索需要偶数字符")
        try:
            return bytes.fromhex(compact)
        except ValueError as exc:
            raise SearchPatternError("十六进制搜索包含无效字符") from exc
    if mode == "text":
        return value.encode("utf-8")
    raise SearchPatternError(f"未知搜索模式: {mode}")


def find_pattern(path: str | Path, pattern: bytes, start_offset: int = 0, chunk_size: int = 1024 * 1024) -> int | None:
    if not pattern:
        return None
    start_offset = max(0, start_offset)
    overlap_size = max(0, len(pattern) - 1)
    with Path(path).open("rb") as fh:
        fh.seek(start_offset)
        absolute = start_offset
        overlap = b""
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                return None
            data = overlap + chunk
            base = absolute - len(overlap)
            found = data.find(pattern)
            if found >= 0:
                return base + found
            keep = min(overlap_size, len(data))
            overlap = data[-keep:] if keep else b""
            absolute += len(chunk)
