from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class _SequenceState:
    first_sequence: int | None = None
    last_sequence: int | None = None
    min_extended: int | None = None
    max_extended: int | None = None
    seen: set[int] = field(default_factory=set)
    duplicate_packets: int = 0
    reordered_packets: int = 0
    forward_gap_events: int = 0

    def add(self, sequence: int) -> dict[str, int | str] | None:
        if self.max_extended is None:
            extended = sequence
            self.first_sequence = sequence
            self.last_sequence = sequence
            self.min_extended = extended
            self.max_extended = extended
            self.seen.add(extended)
            return None

        extended = _nearest_extended_sequence(sequence, self.max_extended)
        event: dict[str, int | str] | None = None
        if extended in self.seen:
            self.duplicate_packets += 1
            event = {"kind": "duplicate", "sequence": sequence}
        elif extended < self.max_extended:
            self.reordered_packets += 1
            event = {
                "kind": "reordered",
                "sequence": sequence,
                "behind": self.max_extended - extended,
            }
        elif extended > self.max_extended + 1:
            self.forward_gap_events += 1
            event = {
                "kind": "gap",
                "sequence": sequence,
                "expected": (self.max_extended + 1) & 0xFFFF,
                "missing": extended - self.max_extended - 1,
            }

        self.seen.add(extended)
        self.last_sequence = sequence
        self.min_extended = extended if self.min_extended is None else min(self.min_extended, extended)
        self.max_extended = max(self.max_extended, extended)
        return event

    def summary(self) -> dict[str, int]:
        if self.min_extended is None or self.max_extended is None:
            return {
                "first_sequence": 0,
                "last_sequence": 0,
                "expected_packets": 0,
                "unique_packets": 0,
                "estimated_lost_packets": 0,
                "duplicate_packets": self.duplicate_packets,
                "reordered_packets": self.reordered_packets,
                "forward_gap_events": self.forward_gap_events,
                "sequence_cycles": 0,
            }
        expected = self.max_extended - self.min_extended + 1
        unique = len(self.seen)
        return {
            "first_sequence": int(self.first_sequence or 0),
            "last_sequence": int(self.last_sequence or 0),
            "lowest_extended_sequence": self.min_extended,
            "highest_extended_sequence": self.max_extended,
            "expected_packets": expected,
            "unique_packets": unique,
            "estimated_lost_packets": max(0, expected - unique),
            "duplicate_packets": self.duplicate_packets,
            "reordered_packets": self.reordered_packets,
            "forward_gap_events": self.forward_gap_events,
            "sequence_cycles": max(0, self.max_extended // 65536 - self.min_extended // 65536),
        }


@dataclass(slots=True)
class _Session:
    key: tuple[str, int, str, int, int]
    sequence: _SequenceState = field(default_factory=_SequenceState)
    packets: int = 0
    payload_bytes: int = 0
    marker_packets: int = 0
    payload_types: set[int] = field(default_factory=set)
    first_offset: int | None = None
    last_offset: int | None = None
    first_capture_time: float | None = None
    last_capture_time: float | None = None
    rtcp_reports: list[dict[str, Any]] = field(default_factory=list)
    rtcp_sender_reports: list[dict[str, Any]] = field(default_factory=list)

    def add_rtp(self, packet: dict[str, Any]) -> dict[str, int | str] | None:
        self.packets += 1
        self.payload_bytes += int(packet.get("payload_size", 0))
        self.marker_packets += int(bool(packet.get("marker")))
        self.payload_types.add(int(packet.get("payload_type", 0)))
        offset = int(packet.get("header_offset", 0))
        capture_time = float(packet.get("capture_time", 0.0))
        if self.first_offset is None:
            self.first_offset = offset
            self.first_capture_time = capture_time
        self.last_offset = offset
        self.last_capture_time = capture_time
        return self.sequence.add(int(packet.get("sequence", 0)))

    def to_dict(self, index: int) -> dict[str, Any]:
        source_ip, source_port, destination_ip, destination_port, ssrc = self.key
        sequence = self.sequence.summary()
        duration = max(0.0, float(self.last_capture_time or 0.0) - float(self.first_capture_time or 0.0))
        bitrate = self.payload_bytes * 8 / duration / 1000 if duration > 0 else None
        reports = self.rtcp_reports
        sender_reports = self.rtcp_sender_reports
        max_fraction = max((int(item.get("fraction_lost", 0)) for item in reports), default=0)
        max_cumulative = max((int(item.get("cumulative_packets_lost", 0)) for item in reports), default=0)
        max_jitter = max((int(item.get("interarrival_jitter", 0)) for item in reports), default=0)
        max_dlsr = max((float(item.get("delay_since_last_sr_seconds", 0.0)) for item in reports), default=0.0)
        anomalies = (
            sequence["estimated_lost_packets"]
            + sequence["duplicate_packets"]
            + sequence["reordered_packets"]
        )
        rtcp_loss = max_fraction > 0 or max_cumulative > 0
        status = "warning" if anomalies or rtcp_loss else "normal"
        endpoint = f"{source_ip}:{source_port} -> {destination_ip}:{destination_port}"
        return {
            "index": index,
            "session_id": f"{endpoint} / 0x{ssrc:08X}",
            "source_ip": source_ip,
            "source_port": source_port,
            "destination_ip": destination_ip,
            "destination_port": destination_port,
            "endpoint": endpoint,
            "ssrc": f"0x{ssrc:08X}",
            "payload_types": sorted(self.payload_types),
            "packets": self.packets,
            "payload_bytes": self.payload_bytes,
            "marker_packets": self.marker_packets,
            "first_offset": int(self.first_offset or 0),
            "last_offset": int(self.last_offset or 0),
            "first_capture_time": round(float(self.first_capture_time or 0.0), 9),
            "last_capture_time": round(float(self.last_capture_time or 0.0), 9),
            "duration_seconds": round(duration, 9),
            "payload_bitrate_kbps": None if bitrate is None else round(bitrate, 3),
            **sequence,
            "rtcp_report_blocks": len(reports),
            "rtcp_sender_reports": len(sender_reports),
            "rtcp_reporter_ssrcs": sorted({str(item.get("reporter_ssrc", "")) for item in reports if item.get("reporter_ssrc")}),
            "rtcp_max_fraction_lost": max_fraction,
            "rtcp_max_fraction_lost_percent": round(max_fraction * 100 / 256, 6),
            "rtcp_max_cumulative_packets_lost": max_cumulative,
            "rtcp_max_interarrival_jitter": max_jitter,
            "rtcp_max_delay_since_last_sr_seconds": round(max_dlsr, 6),
            "status": status,
        }


class TransportSessionTracker:
    def __init__(self) -> None:
        self._sessions: dict[tuple[str, int, str, int, int], _Session] = {}

    def add_rtp(self, packet: dict[str, Any]) -> dict[str, int | str] | None:
        key = (
            str(packet.get("source_ip", "")),
            int(packet.get("source_port", 0)),
            str(packet.get("destination_ip", "")),
            int(packet.get("destination_port", 0)),
            int(packet.get("ssrc", 0)),
        )
        session = self._sessions.setdefault(key, _Session(key))
        return session.add_rtp(packet)

    def attach_rtcp(self, rtcp_stats: dict[str, Any]) -> None:
        by_ssrc: dict[int, list[_Session]] = {}
        for key, session in self._sessions.items():
            by_ssrc.setdefault(key[-1], []).append(session)
        for report in rtcp_stats.get("report_records", []):
            for session in by_ssrc.get(int(report.get("source_ssrc", -1)), []):
                session.rtcp_reports.append(report)
        for report in rtcp_stats.get("sender_report_records", []):
            for session in by_ssrc.get(int(report.get("sender_ssrc", -1)), []):
                session.rtcp_sender_reports.append(report)

    def summary(self) -> dict[str, Any]:
        sessions = [session.to_dict(index) for index, session in enumerate(self._sessions.values())]
        warning_sessions = sum(item["status"] == "warning" for item in sessions)
        return {
            "available": bool(sessions),
            "sessions": sessions,
            "session_count": len(sessions),
            "warning_sessions": warning_sessions,
            "total_rtp_packets": sum(int(item["packets"]) for item in sessions),
            "total_payload_bytes": sum(int(item["payload_bytes"]) for item in sessions),
            "estimated_lost_packets": sum(int(item["estimated_lost_packets"]) for item in sessions),
            "duplicate_packets": sum(int(item["duplicate_packets"]) for item in sessions),
            "reordered_packets": sum(int(item["reordered_packets"]) for item in sessions),
            "rtcp_linked_sessions": sum(int(item["rtcp_report_blocks"]) > 0 or int(item["rtcp_sender_reports"]) > 0 for item in sessions),
        }


def _nearest_extended_sequence(sequence: int, reference: int) -> int:
    candidate = (reference & ~0xFFFF) | (sequence & 0xFFFF)
    if candidate < reference - 0x8000:
        candidate += 0x10000
    elif candidate > reference + 0x8000:
        candidate -= 0x10000
    return candidate
