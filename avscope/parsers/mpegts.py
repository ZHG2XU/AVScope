from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import media_info, root_node, warn


TS_PACKET_SIZE = 188
MAX_VISIBLE_PACKETS = 1000


class MpegTsParser(FormatParser):
    name = "MPEG-TS"
    extensions = (".ts",)

    def probe(self, source: ByteSource) -> bool:
        if source.size < TS_PACKET_SIZE:
            return False
        head = source.head(min(source.size, TS_PACKET_SIZE * 5))
        if self._sync_score(head, TS_PACKET_SIZE) >= 2:
            return True
        return self.extension_matches(source.path) and head[:1] == b"\x47"

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        diagnostics = []
        packet_count = source.size // TS_PACKET_SIZE
        trailing_bytes = source.size % TS_PACKET_SIZE
        if trailing_bytes:
            diagnostics.append(warn("MPEG-TS 文件尾部存在不足 188 字节的残留数据", packet_count * TS_PACKET_SIZE, self.name))

        pid_counts: dict[int, int] = {}
        sync_errors = 0
        payload_start_packets = 0
        visible_packets = min(packet_count, MAX_VISIBLE_PACKETS)
        for index in range(visible_packets):
            offset = index * TS_PACKET_SIZE
            packet = source.read_at(offset, TS_PACKET_SIZE)
            if len(packet) < TS_PACKET_SIZE:
                break
            fields = _packet_fields(packet, offset)
            pid = int(fields["pid"])
            pid_counts[pid] = pid_counts.get(pid, 0) + 1
            if fields["sync_byte"] != 0x47:
                sync_errors += 1
            if fields["payload_unit_start_indicator"]:
                payload_start_packets += 1
            node = root.add_child(
                ParseNode(
                    f"Packet[{index}] PID=0x{pid:04X}",
                    "ts_packet",
                    offset,
                    TS_PACKET_SIZE,
                    severity=Severity.ERROR if fields["sync_byte"] != 0x47 else Severity.NORMAL,
                )
            )
            node.fields.extend(_field_infos(fields, offset))

        if sync_errors:
            diagnostics.append(warn(f"MPEG-TS 前 {visible_packets} 个 packet 中发现 {sync_errors} 个 sync byte 异常", 0, self.name))
        root.fields.extend(
            [
                FieldInfo("packet_size", TS_PACKET_SIZE),
                FieldInfo("packet_count", packet_count),
                FieldInfo("visible_packets", visible_packets),
                FieldInfo("trailing_bytes", trailing_bytes),
                FieldInfo("unique_pid_count", len(pid_counts)),
            ]
        )
        summary = {
            "packet_size": TS_PACKET_SIZE,
            "packets": packet_count,
            "visible_packets": visible_packets,
            "trailing_bytes": trailing_bytes,
            "payload_start_packets": payload_start_packets,
            "pid_counts": {f"0x{pid:04X}": count for pid, count in sorted(pid_counts.items())},
            "sync_errors": sync_errors,
        }
        return ParseResult(media_info(source, self.name, **summary), root, diagnostics=diagnostics)

    @staticmethod
    def _sync_score(data: bytes, packet_size: int) -> int:
        return sum(1 for offset in range(0, len(data), packet_size) if data[offset : offset + 1] == b"\x47")


def _packet_fields(packet: bytes, offset: int) -> dict[str, int | bool]:
    b0, b1, b2, b3 = packet[:4]
    adaptation_field_control = (b3 >> 4) & 0x03
    adaptation_field_length = packet[4] if adaptation_field_control in {2, 3} else 0
    payload_offset = 4
    if adaptation_field_control in {2, 3}:
        payload_offset += 1 + min(adaptation_field_length, TS_PACKET_SIZE - 5)
    return {
        "sync_byte": b0,
        "transport_error_indicator": bool(b1 & 0x80),
        "payload_unit_start_indicator": bool(b1 & 0x40),
        "transport_priority": bool(b1 & 0x20),
        "pid": ((b1 & 0x1F) << 8) | b2,
        "transport_scrambling_control": (b3 >> 6) & 0x03,
        "adaptation_field_control": adaptation_field_control,
        "continuity_counter": b3 & 0x0F,
        "adaptation_field_length": adaptation_field_length,
        "payload_offset": min(payload_offset, TS_PACKET_SIZE),
    }


def _field_infos(fields: dict[str, int | bool], offset: int) -> list[FieldInfo]:
    sync = int(fields["sync_byte"])
    severity = Severity.ERROR if sync != 0x47 else Severity.NORMAL
    return [
        FieldInfo("sync_byte", f"0x{sync:02X}", offset, 1, hex(sync), severity=severity),
        FieldInfo("transport_error_indicator", fields["transport_error_indicator"], offset + 1, 1, bit_offset=offset * 8 + 8, bit_length=1),
        FieldInfo("payload_unit_start_indicator", fields["payload_unit_start_indicator"], offset + 1, 1, bit_offset=offset * 8 + 9, bit_length=1),
        FieldInfo("transport_priority", fields["transport_priority"], offset + 1, 1, bit_offset=offset * 8 + 10, bit_length=1),
        FieldInfo("pid", f"0x{int(fields['pid']):04X}", offset + 1, 2, hex(int(fields["pid"])), bit_offset=offset * 8 + 11, bit_length=13),
        FieldInfo("transport_scrambling_control", fields["transport_scrambling_control"], offset + 3, 1, bit_offset=offset * 8 + 24, bit_length=2),
        FieldInfo("adaptation_field_control", fields["adaptation_field_control"], offset + 3, 1, bit_offset=offset * 8 + 26, bit_length=2),
        FieldInfo("continuity_counter", fields["continuity_counter"], offset + 3, 1, bit_offset=offset * 8 + 28, bit_length=4),
        FieldInfo("adaptation_field_length", fields["adaptation_field_length"], offset + 4, 1 if int(fields["adaptation_field_control"]) in {2, 3} else 0),
        FieldInfo("payload_offset", fields["payload_offset"], offset + int(fields["payload_offset"]), 0, description="packet 内 payload 起始偏移"),
    ]
