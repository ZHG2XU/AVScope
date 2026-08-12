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
RTCP_PACKET_TYPES = {
    192: "FIR",
    193: "NACK",
    195: "IJ",
    200: "Sender Report",
    201: "Receiver Report",
    202: "Source Description",
    203: "Goodbye",
    204: "Application Defined",
    205: "Transport Feedback",
    206: "Payload Feedback",
    207: "Extended Report",
}


class PcapRtpParser(FormatParser):
    name = "PCAP/RTP/RTCP"
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
                FieldInfo("magic", header[:4].hex(" ").upper(), 0, 4, header[:4].hex(" ").upper()),
                FieldInfo("byte_order", endian, 0, 4),
                FieldInfo("timestamp_resolution", resolution, 0, 4),
                FieldInfo("version_major", _u16(header, 4, endian), 4, 2, _hex_bytes(header[4:6])),
                FieldInfo("version_minor", _u16(header, 6, endian), 6, 2, _hex_bytes(header[6:8])),
                FieldInfo("thiszone", _signed(header[8:12], endian), 8, 4, _hex_bytes(header[8:12])),
                FieldInfo("sigfigs", _u32(header, 12, endian), 12, 4, _hex_bytes(header[12:16])),
                FieldInfo("snaplen", _u32(header, 16, endian), 16, 4, _hex_bytes(header[16:20])),
                FieldInfo("network", _u32(header, 20, endian), 20, 4, _hex_bytes(header[20:24]), description="1 means Ethernet"),
            ]
        )

        offset = 24
        packet_count = 0
        rtp_count = 0
        sequence_warnings = 0
        last_sequence_by_ssrc: dict[int, int] = {}
        payload_type_counts: dict[int, int] = {}
        rtcp_stats = _new_rtcp_stats()
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
                    FieldInfo("ts_sec", ts_sec, offset, 4, _hex_bytes(record_header[0:4])),
                    FieldInfo("ts_fraction", ts_frac, offset + 4, 4, _hex_bytes(record_header[4:8])),
                    FieldInfo("timestamp_seconds", _packet_timestamp(ts_sec, ts_frac, resolution), offset, 8),
                    FieldInfo("included_len", included_len, offset + 8, 4, _hex_bytes(record_header[8:12])),
                    FieldInfo("original_len", original_len, offset + 12, 4, _hex_bytes(record_header[12:16])),
                ]
            )
            parsed = _parse_network_packet(
                source,
                packet_node,
                packet_offset,
                included_len,
                diagnostics,
                rtcp_stats,
            )
            parsed_rtp = parsed.get("rtp") if parsed else None
            if parsed_rtp:
                rtp_count += 1
                payload_type = parsed_rtp["payload_type"]
                payload_type_counts[payload_type] = payload_type_counts.get(payload_type, 0) + 1
                ssrc = parsed_rtp["ssrc"]
                sequence = parsed_rtp["sequence"]
                previous = last_sequence_by_ssrc.get(ssrc)
                if previous is not None and sequence != ((previous + 1) & 0xFFFF):
                    sequence_warnings += 1
                    message = f"RTP sequence 跳变: ssrc=0x{ssrc:08X} previous={previous} current={sequence}"
                    diagnostics.append(warn(message, parsed_rtp["header_offset"] + 2, self.name))
                    packet_node.severity = Severity.WARNING if packet_node.severity == Severity.NORMAL else packet_node.severity
                    packet_node.description = packet_node.description or message
                last_sequence_by_ssrc[ssrc] = sequence
                frames.append(
                    FrameInfo(
                        index=len(frames),
                        offset=parsed_rtp["payload_offset"],
                        size=parsed_rtp["payload_size"],
                        pts=parsed_rtp["timestamp"] / 90000,
                        frame_type=f"RTP PT={payload_type}",
                        keyframe=bool(parsed_rtp["marker"]),
                        metadata={
                            "rtp_sequence": sequence,
                            "rtp_timestamp": parsed_rtp["timestamp"],
                            "rtp_ssrc": f"0x{ssrc:08X}",
                            "rtp_payload_type": payload_type,
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

        rtcp_summary = _finalize_rtcp_stats(rtcp_stats)
        root.fields.extend(
            [
                FieldInfo("visible_packets", packet_count),
                FieldInfo("rtp_packets", rtp_count),
                FieldInfo("rtcp_datagrams", rtcp_summary["datagrams"]),
                FieldInfo("rtcp_packets", rtcp_summary["packets"]),
                FieldInfo("sequence_warnings", sequence_warnings),
            ]
        )
        summary = {
            "packets": packet_count,
            "rtp_packets": rtp_count,
            "rtcp_datagrams": rtcp_summary["datagrams"],
            "rtcp_packets": rtcp_summary["packets"],
            "sequence_warnings": sequence_warnings,
            "payload_type_counts": {str(key): value for key, value in sorted(payload_type_counts.items())},
            "rtcp": rtcp_summary,
        }
        return ParseResult(media_info(source, self.name, **summary), root, frames=frames, diagnostics=diagnostics)


def _parse_network_packet(
    source: ByteSource,
    packet_node: ParseNode,
    packet_offset: int,
    included_len: int,
    diagnostics: list,
    rtcp_stats: dict,
) -> dict | None:
    packet_end = packet_offset + included_len
    if included_len < ETHERNET_HEADER_SIZE:
        return None

    eth = source.read_at(packet_offset, ETHERNET_HEADER_SIZE)
    ether_type = int.from_bytes(eth[12:14], "big")
    ethernet_node = packet_node.add_child(ParseNode("Ethernet II", "ethernet", packet_offset, ETHERNET_HEADER_SIZE))
    ethernet_node.fields.extend(
        [
            FieldInfo("destination", _mac(eth[0:6]), packet_offset, 6, _hex_bytes(eth[0:6])),
            FieldInfo("source", _mac(eth[6:12]), packet_offset + 6, 6, _hex_bytes(eth[6:12])),
            FieldInfo("ether_type", f"0x{ether_type:04X}", packet_offset + 12, 2, _hex_bytes(eth[12:14]), description="0x0800 means IPv4"),
        ]
    )
    if ether_type != 0x0800 or packet_end - (packet_offset + ETHERNET_HEADER_SIZE) < 20:
        return None

    ip_offset = packet_offset + ETHERNET_HEADER_SIZE
    ip = source.read_at(ip_offset, min(60, packet_end - ip_offset))
    version = ip[0] >> 4
    ihl_words = ip[0] & 0x0F
    ihl = ihl_words * 4
    if version != 4 or ihl < 20 or len(ip) < ihl:
        return None
    total_length = int.from_bytes(ip[2:4], "big")
    ip_size = min(total_length, packet_end - ip_offset)
    flags_fragment = int.from_bytes(ip[6:8], "big")
    protocol = ip[9]
    ipv4_node = ethernet_node.add_child(ParseNode("Internet Protocol Version 4", "ipv4", ip_offset, ip_size))
    ipv4_node.fields.extend(
        [
            FieldInfo("version", version, ip_offset, 1, _hex_bytes(ip[0:1]), bit_offset=ip_offset * 8, bit_length=4),
            FieldInfo("header_length_words", ihl_words, ip_offset, 1, _hex_bytes(ip[0:1]), bit_offset=ip_offset * 8 + 4, bit_length=4),
            FieldInfo("header_length_bytes", ihl, ip_offset, 1),
            FieldInfo("dscp", ip[1] >> 2, ip_offset + 1, 1, _hex_bytes(ip[1:2]), bit_offset=(ip_offset + 1) * 8, bit_length=6),
            FieldInfo("ecn", ip[1] & 0x03, ip_offset + 1, 1, _hex_bytes(ip[1:2]), bit_offset=(ip_offset + 1) * 8 + 6, bit_length=2),
            FieldInfo("total_length", total_length, ip_offset + 2, 2, _hex_bytes(ip[2:4])),
            FieldInfo("identification", int.from_bytes(ip[4:6], "big"), ip_offset + 4, 2, _hex_bytes(ip[4:6])),
            FieldInfo("flags", flags_fragment >> 13, ip_offset + 6, 2, _hex_bytes(ip[6:8]), bit_offset=(ip_offset + 6) * 8, bit_length=3),
            FieldInfo("fragment_offset", flags_fragment & 0x1FFF, ip_offset + 6, 2, _hex_bytes(ip[6:8]), bit_offset=(ip_offset + 6) * 8 + 3, bit_length=13),
            FieldInfo("ttl", ip[8], ip_offset + 8, 1, _hex_bytes(ip[8:9])),
            FieldInfo("protocol", protocol, ip_offset + 9, 1, _hex_bytes(ip[9:10]), description="17 means UDP"),
            FieldInfo("header_checksum", f"0x{int.from_bytes(ip[10:12], 'big'):04X}", ip_offset + 10, 2, _hex_bytes(ip[10:12])),
            FieldInfo("source", _ip(ip[12:16]), ip_offset + 12, 4, _hex_bytes(ip[12:16])),
            FieldInfo("destination", _ip(ip[16:20]), ip_offset + 16, 4, _hex_bytes(ip[16:20])),
        ]
    )
    if ihl > 20:
        ipv4_node.fields.append(FieldInfo("options", _hex_bytes(ip[20:ihl]), ip_offset + 20, ihl - 20, _hex_bytes(ip[20:ihl])))
    if protocol != IPV4_PROTOCOL_UDP or ip_size < ihl + 8:
        return None

    udp_offset = ip_offset + ihl
    udp = source.read_at(udp_offset, 8)
    if len(udp) < 8:
        return None
    src_port = int.from_bytes(udp[0:2], "big")
    dst_port = int.from_bytes(udp[2:4], "big")
    udp_length = int.from_bytes(udp[4:6], "big")
    available_udp_size = min(max(0, ip_size - ihl), packet_end - udp_offset)
    udp_size = min(max(8, udp_length), available_udp_size)
    udp_node = ipv4_node.add_child(ParseNode("User Datagram Protocol", "udp", udp_offset, udp_size))
    udp_node.fields.extend(
        [
            FieldInfo("source_port", src_port, udp_offset, 2, _hex_bytes(udp[0:2])),
            FieldInfo("destination_port", dst_port, udp_offset + 2, 2, _hex_bytes(udp[2:4])),
            FieldInfo("length", udp_length, udp_offset + 4, 2, _hex_bytes(udp[4:6])),
            FieldInfo("checksum", f"0x{int.from_bytes(udp[6:8], 'big'):04X}", udp_offset + 6, 2, _hex_bytes(udp[6:8])),
        ]
    )
    payload_offset = udp_offset + 8
    payload_size = max(0, udp_size - 8)
    if payload_size < 2:
        return None
    payload = source.read_at(payload_offset, payload_size)
    if _looks_like_rtcp(payload) or (_rtcp_header_candidate(payload) and src_port % 2 == 1 and dst_port % 2 == 1):
        rtcp_stats["datagrams"] += 1
        _parse_rtcp_compound(source, udp_node, payload_offset, payload_size, diagnostics, rtcp_stats)
        return {"kind": "rtcp"}
    rtp = _parse_rtp(source, udp_node, payload_offset, payload_size)
    return {"kind": "rtp", "rtp": rtp} if rtp else None


def _looks_like_rtcp(payload: bytes) -> bool:
    cursor = 0
    packets = 0
    while cursor < len(payload):
        if len(payload) - cursor < 4:
            return False
        version = payload[cursor] >> 6
        packet_type = payload[cursor + 1]
        packet_size = (int.from_bytes(payload[cursor + 2 : cursor + 4], "big") + 1) * 4
        if version != 2 or packet_type not in RTCP_PACKET_TYPES or packet_size < 4 or cursor + packet_size > len(payload):
            return False
        if packet_type == 200 and packet_size < 28:
            return False
        if packet_type == 201 and packet_size < 8:
            return False
        cursor += packet_size
        packets += 1
    return packets > 0 and cursor == len(payload)


def _rtcp_header_candidate(payload: bytes) -> bool:
    return len(payload) >= 4 and payload[1] in RTCP_PACKET_TYPES


def _parse_rtp(source: ByteSource, udp_node: ParseNode, rtp_offset: int, available: int) -> dict | None:
    if available < 12:
        return None
    rtp = source.read_at(rtp_offset, available)
    version = rtp[0] >> 6
    if version != 2:
        return None
    padding = bool(rtp[0] & 0x20)
    extension = bool(rtp[0] & 0x10)
    cc = rtp[0] & 0x0F
    header_size = 12 + cc * 4
    if available < header_size:
        return None
    marker = bool(rtp[1] & 0x80)
    payload_type = rtp[1] & 0x7F
    sequence = int.from_bytes(rtp[2:4], "big")
    timestamp = int.from_bytes(rtp[4:8], "big")
    ssrc = int.from_bytes(rtp[8:12], "big")
    node = udp_node.add_child(ParseNode("Real-time Transport Protocol", "rtp", rtp_offset, available))
    node.fields.extend(
        [
            FieldInfo("version", version, rtp_offset, 1, _hex_bytes(rtp[0:1]), bit_offset=rtp_offset * 8, bit_length=2),
            FieldInfo("padding", padding, rtp_offset, 1, _hex_bytes(rtp[0:1]), bit_offset=rtp_offset * 8 + 2, bit_length=1),
            FieldInfo("extension", extension, rtp_offset, 1, _hex_bytes(rtp[0:1]), bit_offset=rtp_offset * 8 + 3, bit_length=1),
            FieldInfo("csrc_count", cc, rtp_offset, 1, _hex_bytes(rtp[0:1]), bit_offset=rtp_offset * 8 + 4, bit_length=4),
            FieldInfo("marker", marker, rtp_offset + 1, 1, _hex_bytes(rtp[1:2]), bit_offset=(rtp_offset + 1) * 8, bit_length=1),
            FieldInfo("payload_type", payload_type, rtp_offset + 1, 1, _hex_bytes(rtp[1:2]), bit_offset=(rtp_offset + 1) * 8 + 1, bit_length=7),
            FieldInfo("sequence_number", sequence, rtp_offset + 2, 2, _hex_bytes(rtp[2:4])),
            FieldInfo("timestamp", timestamp, rtp_offset + 4, 4, _hex_bytes(rtp[4:8])),
            FieldInfo("ssrc", f"0x{ssrc:08X}", rtp_offset + 8, 4, _hex_bytes(rtp[8:12])),
        ]
    )
    for index in range(cc):
        csrc_offset = 12 + index * 4
        csrc = int.from_bytes(rtp[csrc_offset : csrc_offset + 4], "big")
        node.fields.append(FieldInfo(f"csrc[{index}]", f"0x{csrc:08X}", rtp_offset + csrc_offset, 4, _hex_bytes(rtp[csrc_offset : csrc_offset + 4])))

    if extension:
        if available < header_size + 4:
            return None
        extension_words = int.from_bytes(rtp[header_size + 2 : header_size + 4], "big")
        extension_size = 4 + extension_words * 4
        if available < header_size + extension_size:
            return None
        ext = rtp[header_size : header_size + extension_size]
        extension_node = node.add_child(ParseNode("RTP Header Extension", "rtp_extension", rtp_offset + header_size, extension_size))
        extension_node.fields.extend(
            [
                FieldInfo("profile", f"0x{int.from_bytes(ext[0:2], 'big'):04X}", rtp_offset + header_size, 2, _hex_bytes(ext[0:2])),
                FieldInfo("length_words", extension_words, rtp_offset + header_size + 2, 2, _hex_bytes(ext[2:4])),
                FieldInfo("data", _hex_bytes(ext[4:]), rtp_offset + header_size + 4, len(ext) - 4, _hex_bytes(ext[4:])),
            ]
        )
        header_size += extension_size

    padding_size = rtp[-1] if padding and rtp else 0
    if padding_size > available - header_size:
        padding_size = 0
    payload_size = max(0, available - header_size - padding_size)
    payload_offset = rtp_offset + header_size
    node.fields.extend(
        [
            FieldInfo("header_size", header_size, rtp_offset, 0),
            FieldInfo("payload_offset", payload_offset, payload_offset, 0),
            FieldInfo("payload_size", payload_size, payload_offset, 0),
            FieldInfo("padding_size", padding_size, rtp_offset + available - padding_size, padding_size),
        ]
    )
    return {
        "header_offset": rtp_offset,
        "marker": marker,
        "payload_type": payload_type,
        "sequence": sequence,
        "timestamp": timestamp,
        "ssrc": ssrc,
        "payload_offset": payload_offset,
        "payload_size": payload_size,
    }


def _parse_rtcp_compound(
    source: ByteSource,
    udp_node: ParseNode,
    offset: int,
    size: int,
    diagnostics: list,
    stats: dict,
) -> None:
    compound = udp_node.add_child(ParseNode("RTCP Compound Packet", "rtcp_compound", offset, size))
    cursor = offset
    end = offset + size
    index = 0
    while cursor < end:
        remaining = end - cursor
        if remaining < 4:
            message = f"RTCP common header 截断: remaining={remaining}"
            diagnostics.append(error(message, cursor, "RTCP"))
            compound.severity = Severity.ERROR
            compound.description = message
            break
        header = source.read_at(cursor, 4)
        version = header[0] >> 6
        padding = bool(header[0] & 0x20)
        report_count = header[0] & 0x1F
        packet_type = header[1]
        length_words_minus_one = int.from_bytes(header[2:4], "big")
        declared_size = (length_words_minus_one + 1) * 4
        packet_size = min(declared_size, remaining)
        type_name = RTCP_PACKET_TYPES.get(packet_type, f"Unknown {packet_type}")
        node = compound.add_child(ParseNode(f"RTCP[{index}] {type_name}", "rtcp_packet", cursor, packet_size))
        node.fields.extend(
            [
                FieldInfo("version", version, cursor, 1, _hex_bytes(header[0:1]), bit_offset=cursor * 8, bit_length=2),
                FieldInfo("padding", padding, cursor, 1, _hex_bytes(header[0:1]), bit_offset=cursor * 8 + 2, bit_length=1),
                FieldInfo("report_count", report_count, cursor, 1, _hex_bytes(header[0:1]), bit_offset=cursor * 8 + 3, bit_length=5),
                FieldInfo("packet_type", packet_type, cursor + 1, 1, _hex_bytes(header[1:2]), description=type_name),
                FieldInfo("length_words_minus_one", length_words_minus_one, cursor + 2, 2, _hex_bytes(header[2:4])),
                FieldInfo("packet_length_bytes", declared_size, cursor + 2, 2),
            ]
        )
        stats["packets"] += 1
        stats["packet_type_counts"][packet_type] = stats["packet_type_counts"].get(packet_type, 0) + 1
        if version != 2:
            message = f"RTCP version 应为 2，实际为 {version}"
            diagnostics.append(warn(message, cursor, "RTCP"))
            node.severity = Severity.WARNING
            node.description = message
        if declared_size < 4 or declared_size > remaining:
            message = f"RTCP packet length 越界: declared={declared_size} remaining={remaining}"
            diagnostics.append(error(message, cursor + 2, "RTCP"))
            node.severity = Severity.ERROR
            node.description = message
        if packet_type == 200:
            _parse_sender_report(source, node, cursor, packet_size, report_count, diagnostics, stats)
        elif packet_type == 201:
            _parse_receiver_report(source, node, cursor, packet_size, report_count, diagnostics, stats)
        elif packet_size > 4:
            payload = source.read_at(cursor + 4, packet_size - 4)
            node.fields.append(FieldInfo("payload", _hex_bytes(payload), cursor + 4, len(payload), _hex_bytes(payload)))
        if declared_size <= 0 or declared_size > remaining:
            break
        cursor += declared_size
        index += 1
    compound.fields.extend(
        [
            FieldInfo("compound_packet_count", len(compound.children), offset, 0),
            FieldInfo("compound_size_bytes", size, offset, 0),
        ]
    )


def _parse_sender_report(source: ByteSource, node: ParseNode, offset: int, size: int, report_count: int, diagnostics: list, stats: dict) -> None:
    stats["sender_reports"] += 1
    if size < 28:
        _mark_truncated_report(node, diagnostics, offset, "Sender Report", 28, size)
        return
    data = source.read_at(offset, 28)
    sender_ssrc = int.from_bytes(data[4:8], "big")
    ntp_msw = int.from_bytes(data[8:12], "big")
    ntp_lsw = int.from_bytes(data[12:16], "big")
    rtp_timestamp = int.from_bytes(data[16:20], "big")
    packet_count = int.from_bytes(data[20:24], "big")
    octet_count = int.from_bytes(data[24:28], "big")
    stats["ssrcs"].add(sender_ssrc)
    node.fields.extend(
        [
            FieldInfo("sender_ssrc", f"0x{sender_ssrc:08X}", offset + 4, 4, _hex_bytes(data[4:8])),
            FieldInfo("ntp_timestamp_msw", ntp_msw, offset + 8, 4, _hex_bytes(data[8:12])),
            FieldInfo("ntp_timestamp_lsw", ntp_lsw, offset + 12, 4, _hex_bytes(data[12:16])),
            FieldInfo("ntp_timestamp_seconds", round(ntp_msw + ntp_lsw / 2**32, 9), offset + 8, 8),
            FieldInfo("ntp_unix_seconds", round(ntp_msw + ntp_lsw / 2**32 - 2_208_988_800, 9), offset + 8, 8),
            FieldInfo("rtp_timestamp", rtp_timestamp, offset + 16, 4, _hex_bytes(data[16:20])),
            FieldInfo("sender_packet_count", packet_count, offset + 20, 4, _hex_bytes(data[20:24])),
            FieldInfo("sender_octet_count", octet_count, offset + 24, 4, _hex_bytes(data[24:28])),
        ]
    )
    _parse_report_blocks(source, node, offset + 28, offset + size, report_count, diagnostics, stats)


def _parse_receiver_report(source: ByteSource, node: ParseNode, offset: int, size: int, report_count: int, diagnostics: list, stats: dict) -> None:
    stats["receiver_reports"] += 1
    if size < 8:
        _mark_truncated_report(node, diagnostics, offset, "Receiver Report", 8, size)
        return
    data = source.read_at(offset + 4, 4)
    reporter_ssrc = int.from_bytes(data, "big")
    stats["ssrcs"].add(reporter_ssrc)
    node.fields.append(FieldInfo("reporter_ssrc", f"0x{reporter_ssrc:08X}", offset + 4, 4, _hex_bytes(data)))
    _parse_report_blocks(source, node, offset + 8, offset + size, report_count, diagnostics, stats)


def _parse_report_blocks(source: ByteSource, parent: ParseNode, offset: int, packet_end: int, count: int, diagnostics: list, stats: dict) -> None:
    for index in range(count):
        block_offset = offset + index * 24
        available = packet_end - block_offset
        if available < 24:
            message = f"RTCP report block[{index}] 截断: expected=24 available={max(0, available)}"
            diagnostics.append(error(message, max(0, block_offset), "RTCP"))
            parent.severity = Severity.ERROR
            parent.description = parent.description or message
            break
        data = source.read_at(block_offset, 24)
        source_ssrc = int.from_bytes(data[0:4], "big")
        fraction_lost = data[4]
        cumulative_lost = _signed_24(data[5:8])
        highest_sequence = int.from_bytes(data[8:12], "big")
        jitter = int.from_bytes(data[12:16], "big")
        last_sr = int.from_bytes(data[16:20], "big")
        delay_since_last_sr = int.from_bytes(data[20:24], "big")
        delay_seconds = delay_since_last_sr / 65536
        block = parent.add_child(ParseNode(f"Report Block[{index}]", "rtcp_report_block", block_offset, 24))
        block.fields.extend(
            [
                FieldInfo("source_ssrc", f"0x{source_ssrc:08X}", block_offset, 4, _hex_bytes(data[0:4])),
                FieldInfo("fraction_lost", fraction_lost, block_offset + 4, 1, _hex_bytes(data[4:5]), description=f"{fraction_lost / 256:.3%}"),
                FieldInfo("fraction_lost_percent", round(fraction_lost * 100 / 256, 6), block_offset + 4, 1),
                FieldInfo("cumulative_packets_lost", cumulative_lost, block_offset + 5, 3, _hex_bytes(data[5:8])),
                FieldInfo("extended_highest_sequence", highest_sequence, block_offset + 8, 4, _hex_bytes(data[8:12])),
                FieldInfo("sequence_cycles", highest_sequence >> 16, block_offset + 8, 2, _hex_bytes(data[8:10])),
                FieldInfo("highest_sequence", highest_sequence & 0xFFFF, block_offset + 10, 2, _hex_bytes(data[10:12])),
                FieldInfo("interarrival_jitter", jitter, block_offset + 12, 4, _hex_bytes(data[12:16])),
                FieldInfo("last_sr", f"0x{last_sr:08X}", block_offset + 16, 4, _hex_bytes(data[16:20])),
                FieldInfo("delay_since_last_sr", delay_since_last_sr, block_offset + 20, 4, _hex_bytes(data[20:24])),
                FieldInfo("delay_since_last_sr_seconds", round(delay_seconds, 6), block_offset + 20, 4),
            ]
        )
        stats["report_blocks"] += 1
        stats["ssrcs"].add(source_ssrc)
        stats["max_fraction_lost"] = max(stats["max_fraction_lost"], fraction_lost)
        stats["max_cumulative_packets_lost"] = max(stats["max_cumulative_packets_lost"], cumulative_lost)
        stats["max_interarrival_jitter"] = max(stats["max_interarrival_jitter"], jitter)
        stats["max_delay_since_last_sr_seconds"] = max(stats["max_delay_since_last_sr_seconds"], delay_seconds)
        if fraction_lost > 0 or cumulative_lost > 0:
            message = (
                f"RTCP 接收报告存在丢包: ssrc=0x{source_ssrc:08X} "
                f"fraction={fraction_lost}/256 ({fraction_lost * 100 / 256:.2f}%) cumulative={cumulative_lost}"
            )
            diagnostics.append(warn(message, block_offset + 4, "RTCP"))
            block.severity = Severity.WARNING
            block.description = message


def _mark_truncated_report(node: ParseNode, diagnostics: list, offset: int, name: str, expected: int, actual: int) -> None:
    message = f"RTCP {name} 截断: expected>={expected} actual={actual}"
    diagnostics.append(error(message, offset, "RTCP"))
    node.severity = Severity.ERROR
    node.description = message


def _new_rtcp_stats() -> dict:
    return {
        "datagrams": 0,
        "packets": 0,
        "sender_reports": 0,
        "receiver_reports": 0,
        "report_blocks": 0,
        "ssrcs": set(),
        "packet_type_counts": {},
        "max_fraction_lost": 0,
        "max_cumulative_packets_lost": 0,
        "max_interarrival_jitter": 0,
        "max_delay_since_last_sr_seconds": 0.0,
    }


def _finalize_rtcp_stats(stats: dict) -> dict:
    fraction = stats["max_fraction_lost"]
    return {
        "available": stats["packets"] > 0,
        "datagrams": stats["datagrams"],
        "packets": stats["packets"],
        "sender_reports": stats["sender_reports"],
        "receiver_reports": stats["receiver_reports"],
        "report_blocks": stats["report_blocks"],
        "ssrcs": [f"0x{value:08X}" for value in sorted(stats["ssrcs"])],
        "packet_type_counts": {str(key): value for key, value in sorted(stats["packet_type_counts"].items())},
        "max_fraction_lost": fraction,
        "max_fraction_lost_percent": round(fraction * 100 / 256, 6),
        "max_cumulative_packets_lost": stats["max_cumulative_packets_lost"],
        "max_interarrival_jitter": stats["max_interarrival_jitter"],
        "max_delay_since_last_sr_seconds": round(stats["max_delay_since_last_sr_seconds"], 6),
    }


def _packet_timestamp(seconds: int, fraction: int, resolution: str) -> float:
    divisor = 1_000_000_000 if resolution == "nanosecond" else 1_000_000
    return round(seconds + fraction / divisor, 9)


def _signed_24(data: bytes) -> int:
    value = int.from_bytes(data, "big")
    return value - (1 << 24) if value & 0x800000 else value


def _signed(data: bytes, endian: str) -> int:
    return int.from_bytes(data, endian, signed=True)


def _hex_bytes(data: bytes) -> str:
    return data.hex(" ").upper()


def _mac(data: bytes) -> str:
    return ":".join(f"{value:02X}" for value in data)


def _ip(data: bytes) -> str:
    return ".".join(str(value) for value in data)


def _u16(data: bytes, offset: int, endian: str) -> int:
    return int.from_bytes(data[offset : offset + 2], endian)


def _u32(data: bytes, offset: int, endian: str) -> int:
    return int.from_bytes(data[offset : offset + 4], endian)
