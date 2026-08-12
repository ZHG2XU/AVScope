from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from avscope.models import DiagnosticIssue, FieldInfo, ParseNode, Severity


SIP_METHODS = {
    "INVITE", "ACK", "BYE", "CANCEL", "OPTIONS", "REGISTER", "INFO", "MESSAGE",
    "SUBSCRIBE", "NOTIFY", "PRACK", "UPDATE", "REFER", "PUBLISH",
}


@dataclass(slots=True)
class _Media:
    call_id: str
    message_index: int
    media_index: int
    media: str
    port: int
    protocol: str
    payload_types: list[int]
    connection_address: str
    direction: str
    offset: int
    source_ip: str
    source_port: int
    destination_ip: str
    destination_port: int
    mappings: dict[int, dict[str, Any]] = field(default_factory=dict)
    node: ParseNode | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "message_index": self.message_index,
            "media_index": self.media_index,
            "media": self.media,
            "port": self.port,
            "protocol": self.protocol,
            "payload_types": self.payload_types,
            "connection_address": self.connection_address,
            "direction": self.direction,
            "offset": self.offset,
            "source_endpoint": f"{self.source_ip}:{self.source_port}",
            "destination_endpoint": f"{self.destination_ip}:{self.destination_port}",
            "mappings": [self.mappings[key] for key in sorted(self.mappings)],
        }


class SipSdpAnalyzer:
    def __init__(self) -> None:
        self._messages: list[dict[str, Any]] = []
        self._media: list[_Media] = []
        self._diagnostics: list[DiagnosticIssue] = []
        self._issues: list[dict[str, Any]] = []

    def add_datagram(
        self,
        payload: bytes,
        offset: int,
        parent: ParseNode,
        source_ip: str,
        source_port: int,
        destination_ip: str,
        destination_port: int,
    ) -> bool:
        if not _looks_like_sip(payload):
            return False
        text = payload.decode("utf-8", errors="replace")
        head_text, body_text, body_byte_offset = _split_message(text, payload)
        lines = head_text.replace("\r\n", "\n").split("\n")
        start_line = lines[0].strip() if lines else ""
        headers = _parse_headers(lines[1:])
        kind = "response" if start_line.upper().startswith("SIP/2.0") else "request"
        method = "" if kind == "response" else start_line.split(" ", 1)[0].upper()
        status_code = _status_code(start_line) if kind == "response" else None
        call_id = headers.get("call-id", "")
        cseq = headers.get("cseq", "")
        content_type = headers.get("content-type", "")
        declared_content_length = _int_or_zero(headers.get("content-length"))
        message_index = len(self._messages)
        node = parent.add_child(ParseNode(f"SIP {start_line}", "sip", offset, len(payload)))
        node.fields.extend(
            [
                FieldInfo("start_line", start_line, offset, len(start_line.encode("utf-8"))),
                FieldInfo("message_kind", kind, offset, 0),
                FieldInfo("method", method, offset, 0),
                FieldInfo("status_code", status_code if status_code is not None else "", offset, 0),
                FieldInfo("call_id", call_id, offset, 0),
                FieldInfo("cseq", cseq, offset, 0),
                FieldInfo("content_type", content_type, offset, 0),
                FieldInfo("content_length", declared_content_length, offset, 0),
            ]
        )
        _append_sip_header_fields(node, payload, offset, body_byte_offset)
        has_sdp = "application/sdp" in content_type.lower() or _looks_like_sdp(body_text)
        actual_body_length = len(payload) - body_byte_offset
        if declared_content_length and declared_content_length != actual_body_length:
            self._issue(
                f"SIP Content-Length 不一致: declared={declared_content_length} actual={actual_body_length}",
                offset + body_byte_offset,
            )
            node.severity = Severity.WARNING
        media_before = len(self._media)
        if has_sdp:
            self._parse_sdp(
                body_text,
                offset + body_byte_offset,
                node,
                call_id,
                message_index,
                source_ip,
                source_port,
                destination_ip,
                destination_port,
            )
        message = {
            "index": message_index,
            "kind": kind,
            "method": method,
            "status_code": status_code,
            "start_line": start_line,
            "call_id": call_id,
            "cseq": cseq,
            "content_type": content_type,
            "has_sdp": has_sdp,
            "media_count": len(self._media) - media_before,
            "source_endpoint": f"{source_ip}:{source_port}",
            "destination_endpoint": f"{destination_ip}:{destination_port}",
            "offset": offset,
            "size": len(payload),
        }
        self._messages.append(message)
        return True

    def resolve_payload(self, packet: dict[str, Any]) -> dict[str, Any] | None:
        payload_type = int(packet.get("payload_type", -1))
        source_port = int(packet.get("source_port", 0))
        destination_port = int(packet.get("destination_port", 0))
        source_ip = str(packet.get("source_ip", ""))
        destination_ip = str(packet.get("destination_ip", ""))
        candidates: list[tuple[int, _Media, dict[str, Any]]] = []
        for media in self._media:
            mapping = media.mappings.get(payload_type)
            if not mapping:
                continue
            score = 0
            if destination_port == media.port:
                score += 8
            if source_port == media.port:
                score += 6
            if not score:
                continue
            if media.connection_address and destination_ip == media.connection_address:
                score += 4
            if media.connection_address and source_ip == media.connection_address:
                score += 3
            if destination_ip in {media.source_ip, media.destination_ip}:
                score += 1
            candidates.append((score, media, mapping))
        if not candidates:
            return None
        _, media, mapping = max(candidates, key=lambda item: (item[0], item[1].message_index))
        return {
            **mapping,
            "media": media.media,
            "media_port": media.port,
            "call_id": media.call_id,
            "connection_address": media.connection_address,
            "mapping_source": "SDP",
        }

    def finalize(self) -> tuple[dict[str, Any], list[DiagnosticIssue]]:
        call_ids = sorted({item["call_id"] for item in self._messages if item.get("call_id")})
        calls = []
        for call_id in call_ids:
            messages = [item for item in self._messages if item.get("call_id") == call_id]
            media = [item.to_dict() for item in self._media if item.call_id == call_id]
            calls.append(
                {
                    "call_id": call_id,
                    "messages": len(messages),
                    "requests": sum(item["kind"] == "request" for item in messages),
                    "responses": sum(item["kind"] == "response" for item in messages),
                    "methods": sorted({item["method"] for item in messages if item.get("method")}),
                    "status_codes": sorted({item["status_code"] for item in messages if item.get("status_code") is not None}),
                    "media_count": len(media),
                    "media": media,
                    "first_offset": min((item["offset"] for item in messages), default=0),
                }
            )
        mappings = []
        for media in self._media:
            for mapping in media.mappings.values():
                mappings.append(
                    {
                        "call_id": media.call_id,
                        "media": media.media,
                        "port": media.port,
                        "connection_address": media.connection_address,
                        "direction": media.direction,
                        **mapping,
                        "offset": media.offset,
                    }
                )
        unique_mappings = []
        seen_mappings: set[tuple[Any, ...]] = set()
        for mapping in mappings:
            key = (
                mapping.get("call_id"), mapping.get("media"), mapping.get("port"),
                mapping.get("payload_type"), mapping.get("encoding"), mapping.get("clock_rate"),
            )
            if key in seen_mappings:
                continue
            seen_mappings.add(key)
            unique_mappings.append(mapping)
        summary = {
            "available": bool(self._messages),
            "messages": list(self._messages),
            "message_count": len(self._messages),
            "requests": sum(item["kind"] == "request" for item in self._messages),
            "responses": sum(item["kind"] == "response" for item in self._messages),
            "calls": calls,
            "call_count": len(calls),
            "media": [item.to_dict() for item in self._media],
            "media_count": len(self._media),
            "payload_mappings": mappings,
            "mapping_count": len(mappings),
            "unique_payload_mappings": unique_mappings,
            "unique_mapping_count": len(unique_mappings),
            "issue_count": len(self._issues),
            "issues": list(self._issues),
        }
        return summary, list(self._diagnostics)

    def _parse_sdp(
        self,
        body: str,
        body_offset: int,
        parent: ParseNode,
        call_id: str,
        message_index: int,
        source_ip: str,
        source_port: int,
        destination_ip: str,
        destination_port: int,
    ) -> None:
        sdp_node = parent.add_child(ParseNode("Session Description Protocol", "sdp", body_offset, len(body.encode("utf-8"))))
        session_connection = ""
        session_direction = "sendrecv"
        current: _Media | None = None
        cursor = 0
        for raw_segment in body.splitlines(keepends=True):
            raw_line = raw_segment.rstrip("\r\n")
            line = raw_line.strip()
            if not line:
                cursor += len(raw_segment.encode("utf-8"))
                continue
            line_offset = body_offset + cursor
            cursor += len(raw_segment.encode("utf-8"))
            if len(line) >= 2 and line[1] == "=":
                sdp_node.fields.append(
                    FieldInfo(
                        f"sdp.{line[0]}", line[2:], line_offset, len(raw_line.encode("utf-8")),
                        raw_line.encode("utf-8").hex(" ").upper(), description=raw_line,
                    )
                )
            if line.startswith("c="):
                connection = line[2:].split()
                address = connection[-1].split("/")[0] if connection else ""
                if current:
                    current.connection_address = address
                else:
                    session_connection = address
                sdp_node.fields.append(FieldInfo("connection", address, line_offset, len(raw_line.encode("utf-8"))))
                continue
            if line in {"a=sendrecv", "a=sendonly", "a=recvonly", "a=inactive"}:
                direction = line[2:]
                if current:
                    current.direction = direction
                else:
                    session_direction = direction
                continue
            if line.startswith("m="):
                parts = line[2:].split()
                if len(parts) < 4:
                    self._issue("SDP m= 行字段不足", line_offset)
                    current = None
                    continue
                try:
                    port = int(parts[1].split("/")[0])
                    payload_types = [int(value) for value in parts[3:] if value.isdigit()]
                except ValueError:
                    self._issue("SDP m= 端口或 PT 无效", line_offset)
                    current = None
                    continue
                current = _Media(
                    call_id, message_index, len([item for item in self._media if item.message_index == message_index]),
                    parts[0], port, parts[2], payload_types, session_connection, session_direction, line_offset,
                    source_ip, source_port, destination_ip, destination_port,
                )
                self._media.append(current)
                media_node = sdp_node.add_child(ParseNode(f"Media {current.media}:{port}", "sdp_media", line_offset, len(raw_line.encode("utf-8"))))
                media_node.fields.extend(
                    [
                        FieldInfo("media", current.media, line_offset, 0),
                        FieldInfo("port", port, line_offset, 0),
                        FieldInfo("protocol", current.protocol, line_offset, 0),
                        FieldInfo("payload_types", payload_types, line_offset, 0),
                    ]
                )
                current.node = media_node
                continue
            if line.startswith("a=rtpmap:") and current:
                value = line[len("a=rtpmap:"):]
                pieces = value.split(None, 1)
                if len(pieces) != 2 or not pieces[0].isdigit():
                    self._issue("SDP rtpmap 格式无效", line_offset)
                    continue
                payload_type = int(pieces[0])
                encoding_parts = pieces[1].split("/")
                encoding = encoding_parts[0].upper()
                clock_rate = _int_or_zero(encoding_parts[1] if len(encoding_parts) > 1 else 0)
                channels = _int_or_zero(encoding_parts[2] if len(encoding_parts) > 2 else 0)
                existing = current.mappings.get(payload_type)
                if existing and existing.get("encoding") and existing.get("encoding") != encoding:
                    self._issue(
                        f"SDP PT={payload_type} 存在冲突编码: {existing.get('encoding')} / {encoding}",
                        line_offset,
                    )
                mapping = {
                    "payload_type": payload_type,
                    "encoding": encoding,
                    "clock_rate": clock_rate,
                    "channels": channels or None,
                    "fmtp": "",
                    "rtpmap": pieces[1],
                }
                current.mappings[payload_type] = mapping
                media_node = current.node or sdp_node
                child = media_node.add_child(ParseNode(f"rtpmap PT={payload_type} {encoding}", "sdp_rtpmap", line_offset, len(raw_line.encode("utf-8"))))
                child.fields.extend(
                    [
                        FieldInfo("payload_type", payload_type, line_offset, 0),
                        FieldInfo("encoding", encoding, line_offset, 0),
                        FieldInfo("clock_rate", clock_rate, line_offset, 0),
                        FieldInfo("channels", channels or "", line_offset, 0),
                    ]
                )
                continue
            if line.startswith("a=fmtp:") and current:
                value = line[len("a=fmtp:"):]
                pieces = value.split(None, 1)
                if pieces and pieces[0].isdigit():
                    payload_type = int(pieces[0])
                    fmtp = pieces[1] if len(pieces) > 1 else ""
                    mapping = current.mappings.setdefault(
                        payload_type,
                        {"payload_type": payload_type, "encoding": "", "clock_rate": 0, "channels": None, "fmtp": "", "rtpmap": ""},
                    )
                    mapping["fmtp"] = fmtp

        for media in self._media:
            if media.message_index != message_index:
                continue
            for payload_type in media.payload_types:
                if payload_type in media.mappings:
                    continue
                static = _static_payload(payload_type)
                if static:
                    media.mappings[payload_type] = static
                elif payload_type >= 96:
                    self._issue(
                        f"SDP 动态 PT={payload_type} 缺少 a=rtpmap",
                        media.offset,
                    )

    def _issue(self, message: str, offset: int) -> None:
        issue = {"severity": "warning", "source": "sip_sdp", "message": message, "offset": offset}
        self._issues.append(issue)
        self._diagnostics.append(DiagnosticIssue(Severity.WARNING, message, offset, "sip_sdp"))


def _looks_like_sip(payload: bytes) -> bool:
    head = payload[:32].decode("ascii", errors="ignore").strip().upper()
    if head.startswith("SIP/2.0 "):
        return True
    method = head.split(" ", 1)[0]
    return method in SIP_METHODS and "SIP/2.0" in payload[:512].decode("ascii", errors="ignore").upper()


def _looks_like_sdp(body: str) -> bool:
    lines = body.replace("\r\n", "\n").split("\n")
    return any(line.startswith("v=0") for line in lines) and any(line.startswith("m=") for line in lines)


def _split_message(text: str, payload: bytes) -> tuple[str, str, int]:
    marker = payload.find(b"\r\n\r\n")
    marker_size = 4
    if marker < 0:
        marker = payload.find(b"\n\n")
        marker_size = 2
    if marker < 0:
        return text, "", len(payload)
    head = payload[:marker].decode("utf-8", errors="replace")
    body = payload[marker + marker_size:].decode("utf-8", errors="replace")
    return head, body, marker + marker_size


def _parse_headers(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    current = ""
    for line in lines:
        if line[:1] in {" ", "\t"} and current:
            result[current] = f"{result[current]} {line.strip()}"
            continue
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        current = name.strip().lower()
        result[current] = value.strip()
    compact = {"i": "call-id", "l": "content-length", "c": "content-type"}
    for short, full in compact.items():
        if short in result and full not in result:
            result[full] = result[short]
    return result


def _append_sip_header_fields(node: ParseNode, payload: bytes, offset: int, body_byte_offset: int) -> None:
    header_bytes = payload[:body_byte_offset]
    cursor = 0
    line_index = 0
    for segment in header_bytes.splitlines(keepends=True):
        raw = segment.rstrip(b"\r\n")
        line_offset = offset + cursor
        cursor += len(segment)
        if line_index == 0:
            line_index += 1
            continue
        line_index += 1
        if not raw or b":" not in raw:
            continue
        name_bytes, value_bytes = raw.split(b":", 1)
        name = name_bytes.decode("ascii", errors="replace").strip()
        value = value_bytes.decode("utf-8", errors="replace").strip()
        value_start = len(name_bytes) + 1
        while value_start < len(raw) and raw[value_start:value_start + 1] in {b" ", b"\t"}:
            value_start += 1
        node.fields.append(
            FieldInfo(
                f"header.{name}", value, line_offset + value_start, max(0, len(raw) - value_start),
                raw[value_start:].hex(" ").upper(), description=f"SIP {name} header",
            )
        )


def _status_code(start_line: str) -> int | None:
    parts = start_line.split()
    if len(parts) > 1 and parts[1].isdigit():
        return int(parts[1])
    return None


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _static_payload(payload_type: int) -> dict[str, Any] | None:
    static = {
        0: ("PCMU", 8000, 1), 3: ("GSM", 8000, 1), 8: ("PCMA", 8000, 1),
        9: ("G722", 8000, 1), 10: ("L16", 44100, 2), 11: ("L16", 44100, 1),
        18: ("G729", 8000, 1), 26: ("JPEG", 90000, 0), 31: ("H261", 90000, 0),
        32: ("MPV", 90000, 0), 33: ("MP2T", 90000, 0), 34: ("H263", 90000, 0),
    }
    value = static.get(payload_type)
    if not value:
        return None
    encoding, clock_rate, channels = value
    return {
        "payload_type": payload_type,
        "encoding": encoding,
        "clock_rate": clock_rate,
        "channels": channels or None,
        "fmtp": "",
        "rtpmap": f"{encoding}/{clock_rate}" + (f"/{channels}" if channels else ""),
    }
