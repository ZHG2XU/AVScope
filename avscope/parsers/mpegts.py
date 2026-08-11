from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, FrameInfo, ParseNode, ParseResult, Severity
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
        last_counter_by_pid: dict[int, int] = {}
        sync_errors = 0
        continuity_errors = 0
        payload_start_packets = 0
        pcr_points = []
        frames = []
        visible_packets = min(packet_count, MAX_VISIBLE_PACKETS)
        for index in range(visible_packets):
            offset = index * TS_PACKET_SIZE
            packet = source.read_at(offset, TS_PACKET_SIZE)
            if len(packet) < TS_PACKET_SIZE:
                break
            fields = _packet_fields(packet, offset)
            pid = int(fields["pid"])
            pid_counts[pid] = pid_counts.get(pid, 0) + 1
            continuity_message = _continuity_error(last_counter_by_pid, pid, fields)
            if continuity_message:
                continuity_errors += 1
            if fields["sync_byte"] != 0x47:
                sync_errors += 1
            if fields["payload_unit_start_indicator"]:
                payload_start_packets += 1
            if fields.get("pcr_flag") and fields.get("pcr_seconds") is not None:
                pcr_seconds = float(fields["pcr_seconds"])
                pcr_point = {
                    "packet_index": index,
                    "offset": offset,
                    "pid": f"0x{pid:04X}",
                    "pcr_base": int(fields["pcr_base"]),
                    "pcr_extension": int(fields["pcr_extension"]),
                    "pcr_seconds": round(pcr_seconds, 9),
                }
                pcr_points.append(pcr_point)
                frames.append(
                    FrameInfo(
                        len(frames),
                        offset,
                        TS_PACKET_SIZE,
                        pts=pcr_seconds,
                        frame_type=f"PCR PID=0x{pid:04X}",
                        metadata={
                            "pcr_pid": f"0x{pid:04X}",
                            "pcr_base": int(fields["pcr_base"]),
                            "pcr_extension": int(fields["pcr_extension"]),
                            "pcr_seconds": round(pcr_seconds, 9),
                            "ts_packet_index": index,
                        },
                    )
                )
            severity = Severity.ERROR if fields["sync_byte"] != 0x47 else Severity.WARNING if continuity_message else Severity.NORMAL
            node = root.add_child(
                ParseNode(
                    f"Packet[{index}] PID=0x{pid:04X}",
                    "ts_packet",
                    offset,
                    TS_PACKET_SIZE,
                    severity=severity,
                    description=continuity_message,
                )
            )
            node.fields.extend(_field_infos(fields, offset))

        if sync_errors:
            diagnostics.append(warn(f"MPEG-TS 前 {visible_packets} 个 packet 中发现 {sync_errors} 个 sync byte 异常", 0, self.name))
        if continuity_errors:
            diagnostics.append(warn(f"MPEG-TS 前 {visible_packets} 个 packet 中发现 {continuity_errors} 个 continuity counter 跳变", 0, self.name))
        root.fields.extend(
            [
                FieldInfo("packet_size", TS_PACKET_SIZE),
                FieldInfo("packet_count", packet_count),
                FieldInfo("visible_packets", visible_packets),
                FieldInfo("trailing_bytes", trailing_bytes),
                FieldInfo("unique_pid_count", len(pid_counts)),
                FieldInfo("continuity_errors", continuity_errors),
                FieldInfo("pcr_points", len(pcr_points)),
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
            "continuity_errors": continuity_errors,
            "pcr": _pcr_summary(pcr_points),
        }
        return ParseResult(media_info(source, self.name, **summary), root, frames=frames, diagnostics=diagnostics)

    @staticmethod
    def _sync_score(data: bytes, packet_size: int) -> int:
        return sum(1 for offset in range(0, len(data), packet_size) if data[offset : offset + 1] == b"\x47")


def _packet_fields(packet: bytes, offset: int) -> dict[str, int | bool | float | None]:
    b0, b1, b2, b3 = packet[:4]
    adaptation_field_control = (b3 >> 4) & 0x03
    adaptation_field_length = packet[4] if adaptation_field_control in {2, 3} else 0
    adaptation_flags = packet[5] if adaptation_field_control in {2, 3} and adaptation_field_length >= 1 else 0
    pcr_flag = bool(adaptation_flags & 0x10)
    pcr_base = None
    pcr_extension = None
    pcr_seconds = None
    if pcr_flag and adaptation_field_length >= 7:
        pcr = packet[6:12]
        if len(pcr) == 6:
            pcr_base = (pcr[0] << 25) | (pcr[1] << 17) | (pcr[2] << 9) | (pcr[3] << 1) | (pcr[4] >> 7)
            pcr_extension = ((pcr[4] & 0x01) << 8) | pcr[5]
            pcr_seconds = pcr_base / 90000 + pcr_extension / 27000000
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
        "adaptation_flags": adaptation_flags,
        "pcr_flag": pcr_flag,
        "pcr_base": pcr_base,
        "pcr_extension": pcr_extension,
        "pcr_seconds": pcr_seconds,
        "payload_offset": min(payload_offset, TS_PACKET_SIZE),
    }


def _continuity_error(last_counter_by_pid: dict[int, int], pid: int, fields: dict[str, int | bool | float | None]) -> str:
    adaptation_field_control = int(fields["adaptation_field_control"])
    has_payload = adaptation_field_control in {1, 3}
    if not has_payload:
        return ""
    current = int(fields["continuity_counter"])
    previous = last_counter_by_pid.get(pid)
    last_counter_by_pid[pid] = current
    if previous is None:
        return ""
    expected = (previous + 1) & 0x0F
    if current == expected:
        return ""
    return f"continuity counter 跳变: PID=0x{pid:04X} previous={previous} expected={expected} current={current}"


def _field_infos(fields: dict[str, int | bool | float | None], offset: int) -> list[FieldInfo]:
    sync = int(fields["sync_byte"])
    severity = Severity.ERROR if sync != 0x47 else Severity.NORMAL
    adaptation_field_length = int(fields["adaptation_field_length"])
    has_adaptation_flags = adaptation_field_length >= 1
    infos = [
        FieldInfo("sync_byte", f"0x{sync:02X}", offset, 1, hex(sync), severity=severity),
        FieldInfo("transport_error_indicator", fields["transport_error_indicator"], offset + 1, 1, bit_offset=offset * 8 + 8, bit_length=1),
        FieldInfo("payload_unit_start_indicator", fields["payload_unit_start_indicator"], offset + 1, 1, bit_offset=offset * 8 + 9, bit_length=1),
        FieldInfo("transport_priority", fields["transport_priority"], offset + 1, 1, bit_offset=offset * 8 + 10, bit_length=1),
        FieldInfo("pid", f"0x{int(fields['pid']):04X}", offset + 1, 2, hex(int(fields["pid"])), bit_offset=offset * 8 + 11, bit_length=13),
        FieldInfo("transport_scrambling_control", fields["transport_scrambling_control"], offset + 3, 1, bit_offset=offset * 8 + 24, bit_length=2),
        FieldInfo("adaptation_field_control", fields["adaptation_field_control"], offset + 3, 1, bit_offset=offset * 8 + 26, bit_length=2),
        FieldInfo("continuity_counter", fields["continuity_counter"], offset + 3, 1, bit_offset=offset * 8 + 28, bit_length=4),
        FieldInfo("adaptation_field_length", fields["adaptation_field_length"], offset + 4, 1 if int(fields["adaptation_field_control"]) in {2, 3} else 0),
        FieldInfo("adaptation_flags", f"0x{int(fields['adaptation_flags']):02X}", offset + 5, 1 if has_adaptation_flags else 0),
        FieldInfo("pcr_flag", fields["pcr_flag"], offset + 5, 1 if has_adaptation_flags else 0, bit_offset=offset * 8 + 44, bit_length=1),
        FieldInfo("payload_offset", fields["payload_offset"], offset + int(fields["payload_offset"]), 0, description="packet payload offset"),
    ]
    if fields.get("pcr_flag") and fields.get("pcr_seconds") is not None:
        infos.extend(
            [
                FieldInfo("pcr_base", fields["pcr_base"], offset + 6, 6, hex(int(fields["pcr_base"]))),
                FieldInfo("pcr_extension", fields["pcr_extension"], offset + 10, 2, hex(int(fields["pcr_extension"]))),
                FieldInfo("pcr_seconds", round(float(fields["pcr_seconds"]), 9), offset + 6, 6),
            ]
        )
    return infos


def _pcr_summary(points: list[dict]) -> dict:
    if not points:
        return {"available": False, "points": 0}
    grouped: dict[str, list[dict]] = {}
    for point in points:
        grouped.setdefault(str(point["pid"]), []).append(point)
    by_pid = {}
    warnings = []
    for pid, pid_points in grouped.items():
        seconds = [float(point["pcr_seconds"]) for point in pid_points]
        intervals = [round(seconds[index] - seconds[index - 1], 9) for index in range(1, len(seconds))]
        non_monotonic = sum(1 for interval in intervals if interval < 0)
        if non_monotonic:
            warnings.append({"pid": pid, "kind": "non_monotonic", "count": non_monotonic})
        item = {
            "points": len(pid_points),
            "first": round(seconds[0], 9),
            "last": round(seconds[-1], 9),
            "span": round(seconds[-1] - seconds[0], 9),
            "min": round(min(seconds), 9),
            "max": round(max(seconds), 9),
            "non_monotonic": non_monotonic,
        }
        if intervals:
            average_interval = sum(intervals) / len(intervals)
            item.update(
                {
                    "average_interval": round(average_interval, 9),
                    "min_interval": round(min(intervals), 9),
                    "max_interval": round(max(intervals), 9),
                    "max_interval_jitter": round(max(abs(interval - average_interval) for interval in intervals), 9),
                }
            )
        by_pid[pid] = item
    return {
        "available": True,
        "points": len(points),
        "pid_count": len(grouped),
        "by_pid": by_pid,
        "warnings": warnings,
        "series": points[:160],
    }
