from __future__ import annotations

from pathlib import Path


class ByteSource:
    """Read-only, random-access byte source for large media files."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._fh = self.path.open("rb")
        self.size = self.path.stat().st_size

    def close(self) -> None:
        self._fh.close()

    def read_at(self, offset: int, size: int) -> bytes:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if size <= 0 or offset >= self.size:
            return b""
        safe_size = min(size, self.size - offset)
        self._fh.seek(offset)
        return self._fh.read(safe_size)

    def head(self, size: int = 4096) -> bytes:
        return self.read_at(0, size)

    def iter_chunks(self, chunk_size: int = 1024 * 1024):
        offset = 0
        while offset < self.size:
            data = self.read_at(offset, chunk_size)
            if not data:
                break
            yield offset, data
            offset += len(data)

    def __enter__(self) -> "ByteSource":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
