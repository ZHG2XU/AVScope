from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    NORMAL = "normal"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class FieldInfo:
    name: str
    value: Any
    offset: int = 0
    size: int = 0
    hex_value: str = ""
    bit_offset: int | None = None
    bit_length: int | None = None
    description: str = ""
    severity: Severity = Severity.NORMAL


@dataclass(slots=True)
class ParseNode:
    name: str
    node_type: str
    offset: int
    size: int
    fields: list[FieldInfo] = field(default_factory=list)
    children: list["ParseNode"] = field(default_factory=list)
    severity: Severity = Severity.NORMAL
    description: str = ""

    def add_child(self, child: "ParseNode") -> "ParseNode":
        self.children.append(child)
        return child


@dataclass(slots=True)
class FrameInfo:
    index: int
    offset: int
    size: int
    pts: float | None = None
    dts: float | None = None
    duration: float | None = None
    frame_type: str = ""
    keyframe: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DiagnosticIssue:
    severity: Severity
    message: str
    offset: int | None = None
    source: str = ""


@dataclass(slots=True)
class MediaInfo:
    path: str
    size: int
    format_name: str
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParseResult:
    media: MediaInfo
    root: ParseNode
    frames: list[FrameInfo] = field(default_factory=list)
    diagnostics: list[DiagnosticIssue] = field(default_factory=list)


@dataclass(slots=True)
class CompareChunk:
    offset: int
    left: bytes
    right: bytes


@dataclass(slots=True)
class CompareResult:
    left_path: str
    right_path: str
    left_size: int
    right_size: int
    equal: bool
    chunks: list[CompareChunk] = field(default_factory=list)
