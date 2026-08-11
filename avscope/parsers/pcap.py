from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, FrameInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, warn


MAGICS = {
    b"\xD4\xC3\xB2\xA1": ("little", "microsecond"),
    b"\xA1\xB2\xC3\xD4": ("big", "microsecond"),
    b"\x4D\x3C\xB2\xA1": ("little", "nanosecond"),
    b"\xA1\xB2\x3C\x4D": ("big", "nanosecond"),
}
MAX_VISIBLE_PACKETS = 2000
ETHERNET_HEADER_SIZE = 14
IPV4_PROTOCOL_UDP = 17


class PcapRtpParser(FormatParser):
    name = "PCAP/RTP"
    extensions = (".pcap",)

    def probe(self, source: ByteSource) -> bool:
        return source.head(4) in MAGICS

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        root = root_node(source, self.name)
        diagnostics = []
        frames: list[FrameInfo] = []
        header = source.head(24)
        if len(header) < 24:
            diagnostics.append(error("PCAP global header 长度不足", 0, self.name))
            return ParseResult(media_info(source, self.name), root, diagnostics=diagnostics)

        endian, resolution = MAGICS[header[:4]]
        root.fields.extend(
            [
                FieldInfo("magic", header[:4].hex(" ").upper(), 0, 4),
                FieldInfo("byte_order", endian, 0, 4),
                FieldInfo("timestamp_resolution", resolution, 0, 4),
                FieldInfo("version_major", _u16(header, 4, endian), 4, 2),
                FieldInfo("version_minor", _u16(header, 6, endian), 6, 2),
                FieldInfo("snaplen", _u32(header, 16, endian), 16, 4),
                FieldInfo("network", _u32(header, 20, endian), 20, 4, description="1 means Ethernet"),
            ]
        )

        offset = 24
        packet_count = 0
        rtp_count = 0
        sequence_warnings = 0
        last_sequence_by_ssrc: dict[int, int] = {}
        payload_type_counts: dict[int, int] = {}
        while offset + 16 <= source.size and packet_count < MAX_VISIBLE_PACKETS:
            record_header = source.read_at(offset, 16)
            ts_sec = _u32(record_header, 0, endian)
            ts_frac = _u32(record_header, 4, endian)
            included_len = _u32(record_header, 8, endian)
            original_len = _u32(record_header, 12, endian)
            packet_offset = offset + 16
            packet_end = packet_offset + included_len
            severity = Severity.NORMAL
            description = ""
            if packet_end > source.size:
                diagnostics.append(error("PCAP packet included_len 超出文件边界", offset + 8, self.name))
                packet_end = source.size
                included_len = max(0, packet_end - packet_offset)
                severity = Severity.ERROR
                description = "included_len 超出文件边界"

            packet_node = root.add_child(
                ParseNode(f"Packet[{packet_count}]", "pcap_packet", offset, packet_end - offset, severity=severity, description=description)
            )
            packet_node.fields.extend(
                [
                    FieldInfo("ts_sec", ts_sec, offset, 4, hex(ts_sec)),
                    FieldInfo("ts_fraction", ts_frac, offset + 4, 4, hex(ts_frac)),
                    FieldInfo("included_len", included_len, offset + 8, 4, hex(included_len)),
                    FieldInfo("original_len", original_len, offset + 12, 4, hex(original_len)),
                ]
            )
            parsed_rtp = _parse_rtp_packet(source, packet_node, packet_offset, included_len)
            if parsed_rtp:
                rtp_count += 1
                payload_type_counts[parsed_rtp["payload_type"]] = payload_type_counts.get(parsed_rtp["payload_type"], 0) + 1
                ssrc = parsed_rtp["ssrc"]
                sequence = parsed_rtp["sequence"]
                previous = last_sequence_by_ssrc.get(ssrc)
                if previous is not None and sequence != ((previous + 1) & 0xFFFF):
                    sequence_warnings += 1
                    message = f"RTP sequence 跳变: ssrc=0x{ssrc:08X} previous={previous} current={sequence}"
                    diagnostics.append(warn(message, packet_offset, self.name))
                    packet_node.severity = Severity.WARNING if packet_node.severity == Severity.NORMAL else packet_node.severity
                    packet_node.description = packet_node.description or message
                last_sequence_by_ssrc[ssrc] = sequence
                frames.append(
                    FrameInfo(
                        index=len(frames),
                        offset=parsed_rtp["payload_offset"],
                        size=parsed_rtp["payload_size"],
                        pts=parsed_rtp["timestamp"] / 90000,
                        frame_type=f"RTP PT={parsed_rtp['payload_type']}",
                        keyframe=bool(parsed_rtp["marker"]),
                        metadata={
                            "rtp_sequence": sequence,
                            "rtp_timestamp": parsed_rtp["timestamp"],
                            "rtp_ssrc": f"0x{ssrc:08X}",
                            "rtp_payload_type": parsed_rtp["payload_type"],
                            "rtp_marker": bool(parsed_rtp["marker"]),
                        },
                    )
                )
            packet_count += 1
            offset = packet_end

        if offset < source.size and packet_count >= MAX_VISIBLE_PACKETS:
            diagnostics.append(warn(f"PCAP packet 超过 {MAX_VISIBLE_PACKETS} 个，已停止展开后续 packet", offset, self.name))
        elif offset < source.size:
            diagnostics.append(warn("PCAP 尾部存在未解析字节", offset, self.name))
        root.fields.extend(
            [
                FieldInfo("visible_packets", packet_count),
                FieldInfo("rtp_packets", rtp_count),
                FieldInfo("sequence_warnings", sequence_warnings),
            ]
        )
        summary = {
            "packets": packet_count,
            "rtp_packets": rtp_count,
            "sequence_warnings": sequence_warnings,
            "payload_type_counts": {str(key): value for key, value in sorted(payload_type_counts.items())},
        }
        return ParseResult(media_info(source, self.name, **summary), root, frames=frames, diagnostics=diagnostics)


def _parse_rtp_packet(source: ByteSource, packet_node: ParseNode, packet_offset: int, included_len: int) -> dict | None:
    if included_len < ETHERNET_HEADER_SIZE + 20 + 8 + 12:
        return None
    eth = source.read_at(packet_offset, ETHERNET_HEADER_SIZE)
    ether_type = int.from_bytes(eth[12:14], "big")
    packet_node.fields.append(FieldInfo("ether_type", f"0x{ether_type:04X}", packet_offset + 12, 2, hex(ether_type)))
    if ether_type != 0x0800:
        return None
    ip_offset = packet_offset + ETHERNET_HEADER_SIZE
    ip = source.read_at(ip_offset, 20)
    version = ip[0] >> 4
    ihl = (ip[0] & 0x0F) * 4
    protocol = ip[9]
    total_length = int.from_bytes(ip[2:4], "big")
    packet_node.fields.extend(
        [
            FieldInfo("ip_version", version, ip_offset, 1, bit_offset=ip_offset * 8, bit_length=4),
            FieldInfo("ip_header_length", ihl, ip_offset, 1, bit_offset=ip_offset * 8 + 4, bit_length=4),
            FieldInfo("ip_total_length", total_length, ip_offset + 2, 2, hex(total_length)),
            FieldInfo("ip_protocol", protocol, ip_offset + 9, 1, hex(protocol), description="17 means UDP"),
            FieldInfo("src_ip", ".".join(str(b) for b in ip[12:16]), ip_offset + 12, 4),
            FieldInfo("dst_ip", ".".join(str(b) for b in ip[16:20]), ip_offset + 16, 4),
        ]
    )
    if version != 4 or ihl < 20 or protocol != IPV4_PROTOCOL_UDP:
        return None
    udp_offset = ip_offset + ihl
    udp = source.read_at(udp_offset, 8)
    if len(udp) < 8:
        return None
    src_port = int.from_bytes(udp[0:2], "big")
    dst_port = int.from_bytes(udp[2:4], "big")
    udp_length = int.from_bytes(udp[4:6], "big")
    rtp_offset = udp_offset + 8
    rtp = source.read_at(rtp_offset, min(16, max(0, packet_offset + included_len - rtp_offset)))
    if len(rtp) < 12 or (rtp[0] >> 6) != 2:
        return None
    cc = rtp[0] & 0x0F
    rtp_header_size = 12 + cc * 4
    if len(rtp) < min(rtp_header_size, 16):
        return None
    marker = bool(rtp[1] & 0x80)
    payload_type = rtp[1] & 0x7F
    sequence = int.from_bytes(rtp[2:4], "big")
    timestamp = int.from_bytes(rtp[4:8], "big")
    ssrc = int.from_bytes(rtp[8:12], "big")
    payload_offset = rtp_offset + rtp_header_size
    payload_size = max(0, min(packet_offset + included_len, udp_offset + udp_length) - payload_offset)
    packet_node.fields.extend(
        [
            FieldInfo("udp_src_port", src_port, udp_offset, 2, hex(src_port)),
            FieldInfo("udp_dst_port", dst_port, udp_offset + 2, 2, hex(dst_port)),
            FieldInfo("udp_length", udp_length, udp_offset + 4, 2, hex(udp_length)),
            FieldInfo("rtp_version", 2, rtp_offset, 1, bit_offset=rtp_offset * 8, bit_length=2),
            FieldInfo("rtp_marker", marker, rtp_offset + 1, 1, bit_offset=(rtp_offset + 1) * 8, bit_length=1),
            FieldInfo("rtp_payload_type", payload_type, rtp_offset + 1, 1, hex(payload_type), bit_offset=(rtp_offset + 1) * 8 + 1, bit_length=7),
            FieldInfo("rtp_sequence", sequence, rtp_offset + 2, 2, hex(sequence)),
            FieldInfo("rtp_timestamp", timestamp, rtp_offset + 4, 4, hex(timestamp)),
            FieldInfo("rtp_ssrc", f"0x{ssrc:08X}", rtp_offset + 8, 4, hex(ssrc)),
            FieldInfo("rtp_payload_offset", payload_offset, payload_offset, 0),
            FieldInfo("rtp_payload_size", payload_size, payload_offset, 0),
        ]
    )
    return {
        "marker": marker,
        "payload_type": payload_type,
        "sequence": sequence,
        "timestamp": timestamp,
        "ssrc": ssrc,
        "payload_offset": payload_offset,
        "payload_size": payload_size,
    }


def _u16(data: bytes, offset: int, endian: str) -> int:
    return int.from_bytes(data[offset : offset + 2], endian)


def _u32(data: bytes, offset: int, endian: str) -> int:
    return int.from_bytes(data[offset : offset + 4], endian)
