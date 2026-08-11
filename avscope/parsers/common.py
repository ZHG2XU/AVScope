from __future__ import annotations

import struct
from pathlib import Path

from avscope.byte_source import ByteSource
from avscope.models import DiagnosticIssue, MediaInfo, ParseNode, Severity


def media_info(source: ByteSource, format_name: str, **summary) -> MediaInfo:
    return MediaInfo(str(source.path), source.size, format_name, summary)


def root_node(source: ByteSource, format_name: str) -> ParseNode:
    return ParseNode(Path(source.path).name, format_name, 0, source.size)


def u16be(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def u32be(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def u64be(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from(">Q", data, offset)[0]


def u16le(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32le(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def warn(message: str, offset: int | None = None, source: str = "") -> DiagnosticIssue:
    return DiagnosticIssue(Severity.WARNING, message, offset, source)


def error(message: str, offset: int | None = None, source: str = "") -> DiagnosticIssue:
    return DiagnosticIssue(Severity.ERROR, message, offset, source)
