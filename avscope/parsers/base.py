from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from avscope.byte_source import ByteSource
from avscope.models import ParseResult


class FormatParser(ABC):
    name = "Unknown"
    extensions: tuple[str, ...] = ()

    def extension_matches(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() in self.extensions

    @abstractmethod
    def probe(self, source: ByteSource) -> bool:
        raise NotImplementedError

    @abstractmethod
    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        raise NotImplementedError
