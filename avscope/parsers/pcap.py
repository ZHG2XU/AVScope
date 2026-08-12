from __future__ import annotations

from avscope.byte_source import ByteSource
from avscope.models import FieldInfo, FrameInfo, ParseNode, ParseResult, Severity
from avscope.parsers.base import FormatParser
from avscope.parsers.common import error, media_info, root_node, warn
from avscope.rtp_video import RtpVideoPayloadAnalyzer
from avscope.sip_sdp import SipSdpAnalyzer
from avscope.transport_sessions import TransportSessionTracker


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
RTP_STATIC_CLOCK_RATES = {
    0: 8000, 3: 8000, 4: 8000, 5: 8000, 6: 16000, 7: 8000, 8: 8000, 9: 8000,
    10: 44100, 11: 44100, 12: 8000, 13: 8000, 14: 90000, 15: 8000, 16: 11025,
    17: 22050, 18: 8000, 25: 90000, 26: 90000, 28: 90000, 31: 90000, 32: 90000,
    33: 90000, 34: 90000,
}


class PcapRtpParser(FormatParser):
    name = "PCAP/RTP/RTCP"
    extensions = (".pcap",)

    def probe(self, source: ByteSource) -> bool:
        return source.head(4) in MAGICS

    def parse(self, source: ByteSource, options: dict | None = None) -> ParseResult:
        options = options or {}
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
        payload_type_counts: dict[int, int] = {}
        rtcp_stats = _new_rtcp_stats()
        session_tracker = TransportSessionTracker()
        sip_analyzer = SipSdpAnalyzer()
        rtp_descriptors: list[tuple[dict, int]] = []
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
                sip_analyzer,
            )
            parsed_rtp = parsed.get("rtp") if parsed else None
            if parsed_rtp:
                parsed_rtp["capture_time"] = _packet_timestamp(ts_sec, ts_frac, resolution)
                rtp_count += 1
                payload_type = parsed_rtp["payload_type"]
                payload_type_counts[payload_type] = payload_type_counts.get(payload_type, 0) + 1
                ssrc = parsed_rtp["ssrc"]
                sequence = parsed_rtp["sequence"]
                sequence_event = session_tracker.add_rtp(parsed_rtp)
                if sequence_event:
                    sequence_warnings += 1
                    message = _sequence_event_message(ssrc, sequence_event)
                    diagnostics.append(warn(message, parsed_rtp["header_offset"] + 2, self.name))
                    packet_node.severity = Severity.WARNING if packet_node.severity == Severity.NORMAL else packet_node.severity
                    packet_node.description = packet_node.description or message
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
                            "rtp_sequence_event": sequence_event.get("kind") if sequence_event else "",
                        },
                    )
                )
                rtp_descriptors.append((parsed_rtp, len(frames) - 1))
            packet_count += 1
            offset = packet_end

        if offset < source.size and packet_count >= MAX_VISIBLE_PACKETS:
            diagnostics.append(warn(f"PCAP packet 超过 {MAX_VISIBLE_PACKETS} 个，已停止展开后续 packet", offset, self.name))
        elif offset < source.size:
            diagnostics.append(warn("PCAP 尾部存在未解析字节", offset, self.name))

        sip_sdp, sip_diagnostics = sip_analyzer.finalize()
        diagnostics.extend(sip_diagnostics)
        video_analyzer = RtpVideoPayloadAnalyzer(options.get("rtp_payload_map"))
        negotiated_packets: list[tuple[dict, dict[str, object]]] = []
        for parsed_rtp, frame_index in rtp_descriptors:
            negotiated = sip_analyzer.resolve_payload(parsed_rtp)
            if negotiated:
                negotiated_packets.append((parsed_rtp, negotiated))
            payload = source.read_at(parsed_rtp["payload_offset"], parsed_rtp["payload_size"])
            video_payload = video_analyzer.add_packet(parsed_rtp, payload, parsed_rtp["node"], negotiated)
            metadata = frames[frame_index].metadata
            metadata.update(
                {
                    "rtp_video_codec": video_payload.get("codec", ""),
                    "rtp_packetization": video_payload.get("packetization", ""),
                    "rtp_nal_types": video_payload.get("nal_types", []),
                    "rtp_nal_units": video_payload.get("nal_units", 0),
                    "rtp_video_status": video_payload.get("status", ""),
                    "rtp_negotiated_encoding": video_payload.get("negotiated_encoding", ""),
                    "rtp_clock_rate": video_payload.get("clock_rate", 0),
                    "sip_call_id": video_payload.get("call_id", ""),
                    "rtp_mapping_source": video_payload.get("mapping_source", ""),
                }
            )
            clock_rate = int(video_payload.get("clock_rate", 0) or 0)
            if clock_rate > 0:
                frames[frame_index].pts = parsed_rtp["timestamp"] / clock_rate

        session_tracker.attach_rtcp(rtcp_stats)
        transport_sessions = session_tracker.summary()
        _merge_sdp_transport_sessions(transport_sessions, negotiated_packets)
        _merge_rtp_timing_quality(transport_sessions)
        for session in transport_sessions.get("sessions", []):
            for event in session.get("rtp_timing", {}).get("events", []):
                diagnostics.append(warn(
                    f"RTP 到达时序突发: ssrc={session.get('ssrc')} sequence={event.get('sequence')} "
                    f"arrival={event.get('arrival_interval_ms'):.3f}ms media={event.get('media_interval_ms'):.3f}ms "
                    f"deviation={event.get('deviation_ms'):.3f}ms",
                    int(event.get("offset", 0)), "RTP Timing",
                ))
        rtp_video, video_diagnostics = video_analyzer.finalize()
        _merge_rtp_video_sessions(transport_sessions, rtp_video)
        transport_sessions["warning_sessions"] = sum(
            item.get("status") == "warning" for item in transport_sessions.get("sessions", [])
        )
        diagnostics.extend(video_diagnostics)
        rtcp_summary = _finalize_rtcp_stats(rtcp_stats)
        root.fields.extend(
            [
                FieldInfo("visible_packets", packet_count),
                FieldInfo("rtp_packets", rtp_count),
                FieldInfo("rtcp_datagrams", rtcp_summary["datagrams"]),
                FieldInfo("rtcp_packets", rtcp_summary["packets"]),
                FieldInfo("transport_sessions", transport_sessions["session_count"]),
                FieldInfo("warning_sessions", transport_sessions["warning_sessions"]),
                FieldInfo("sequence_warnings", sequence_warnings),
                FieldInfo("rtp_video_streams", rtp_video["stream_count"]),
                FieldInfo("rtp_video_issues", rtp_video["issue_count"]),
                FieldInfo("sip_messages", sip_sdp["message_count"]),
                FieldInfo("sdp_media", sip_sdp["media_count"]),
                FieldInfo("sdp_payload_mappings", sip_sdp["mapping_count"]),
                FieldInfo("rtp_timing_bursts", transport_sessions["rtp_timing"]["burst_events"]),
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
            "transport_sessions": transport_sessions,
            "rtp_video": rtp_video,
            "sip_sdp": sip_sdp,
        }
        return ParseResult(media_info(source, self.name, **summary), root, frames=frames, diagnostics=diagnostics)


def _parse_network_packet(
    source: ByteSource,
    packet_node: ParseNode,
    packet_offset: int,
    included_len: int,
    diagnostics: list,
    rtcp_stats: dict,
    sip_analyzer: SipSdpAnalyzer,
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
    source_ip = _ip(ip[12:16])
    destination_ip = _ip(ip[16:20])
    if sip_analyzer.add_datagram(
        payload, payload_offset, udp_node, source_ip, src_port, destination_ip, dst_port,
    ):
        return {"kind": "sip"}
    if _looks_like_rtcp(payload) or (_rtcp_header_candidate(payload) and src_port % 2 == 1 and dst_port % 2 == 1):
        rtcp_stats["datagrams"] += 1
        _parse_rtcp_compound(source, udp_node, payload_offset, payload_size, diagnostics, rtcp_stats)
        return {"kind": "rtcp"}
    rtp = _parse_rtp(source, udp_node, payload_offset, payload_size)
    if rtp:
        rtp.update(
            {
                "source_ip": source_ip,
                "destination_ip": destination_ip,
                "source_port": src_port,
                "destination_port": dst_port,
            }
        )
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
        "node": node,
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
        elif packet_type == 202:
            _parse_rtcp_sdes(source, node, cursor, packet_size, report_count, diagnostics, stats)
        elif packet_type == 203:
            _parse_rtcp_bye(source, node, cursor, packet_size, report_count, diagnostics, stats)
        elif packet_type == 205:
            _parse_rtcp_rtpfb(source, node, cursor, packet_size, report_count, diagnostics, stats)
        elif packet_type == 206:
            _parse_rtcp_psfb(source, node, cursor, packet_size, report_count, diagnostics, stats)
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
    stats["sender_report_records"].append(
        {
            "sender_ssrc": sender_ssrc,
            "offset": offset,
            "rtp_timestamp": rtp_timestamp,
            "sender_packet_count": packet_count,
            "sender_octet_count": octet_count,
        }
    )
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
    _parse_report_blocks(source, node, offset + 28, offset + size, report_count, diagnostics, stats, sender_ssrc)


def _parse_receiver_report(source: ByteSource, node: ParseNode, offset: int, size: int, report_count: int, diagnostics: list, stats: dict) -> None:
    stats["receiver_reports"] += 1
    if size < 8:
        _mark_truncated_report(node, diagnostics, offset, "Receiver Report", 8, size)
        return
    data = source.read_at(offset + 4, 4)
    reporter_ssrc = int.from_bytes(data, "big")
    stats["ssrcs"].add(reporter_ssrc)
    node.fields.append(FieldInfo("reporter_ssrc", f"0x{reporter_ssrc:08X}", offset + 4, 4, _hex_bytes(data)))
    _parse_report_blocks(source, node, offset + 8, offset + size, report_count, diagnostics, stats, reporter_ssrc)


def _parse_report_blocks(
    source: ByteSource,
    parent: ParseNode,
    offset: int,
    packet_end: int,
    count: int,
    diagnostics: list,
    stats: dict,
    reporter_ssrc: int,
) -> None:
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
        stats["report_records"].append(
            {
                "reporter_ssrc": f"0x{reporter_ssrc:08X}",
                "source_ssrc": source_ssrc,
                "offset": block_offset,
                "fraction_lost": fraction_lost,
                "cumulative_packets_lost": cumulative_lost,
                "extended_highest_sequence": highest_sequence,
                "interarrival_jitter": jitter,
                "last_sr": last_sr,
                "delay_since_last_sr_seconds": round(delay_seconds, 6),
            }
        )
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


def _parse_rtcp_sdes(source: ByteSource, node: ParseNode, offset: int, size: int, chunk_count: int, diagnostics: list, stats: dict) -> None:
    item_names = {1: "cname", 2: "name", 3: "email", 4: "phone", 5: "location", 6: "tool", 7: "note", 8: "private"}
    cursor = offset + 4
    packet_end = offset + size
    for chunk_index in range(chunk_count):
        if cursor + 4 > packet_end:
            _mark_truncated_report(node, diagnostics, cursor, f"SDES chunk[{chunk_index}]", 4, max(0, packet_end - cursor))
            break
        chunk_offset = cursor
        ssrc_data = source.read_at(cursor, 4)
        ssrc = int.from_bytes(ssrc_data, "big")
        stats["ssrcs"].add(ssrc)
        cursor += 4
        chunk = node.add_child(ParseNode(f"SDES Chunk[{chunk_index}]", "rtcp_sdes_chunk", chunk_offset, 4))
        chunk.fields.append(FieldInfo("ssrc", f"0x{ssrc:08X}", chunk_offset, 4, _hex_bytes(ssrc_data)))
        record = {"ssrc": ssrc, "offset": chunk_offset}
        item_index = 0
        while cursor < packet_end:
            item_type = source.read_at(cursor, 1)[0]
            if item_type == 0:
                chunk.fields.append(FieldInfo("end", 0, cursor, 1, "00", description="END"))
                cursor += 1
                break
            if cursor + 2 > packet_end:
                _mark_truncated_report(chunk, diagnostics, cursor, "SDES item header", 2, packet_end - cursor)
                cursor = packet_end
                break
            item_length = source.read_at(cursor + 1, 1)[0]
            available = packet_end - cursor - 2
            if item_length > available:
                _mark_truncated_report(chunk, diagnostics, cursor, "SDES item", item_length, available)
                cursor = packet_end
                break
            raw = source.read_at(cursor + 2, item_length)
            value = raw.decode("utf-8", errors="replace")
            name = item_names.get(item_type, f"item_{item_type}")
            item = chunk.add_child(ParseNode(f"SDES {name.upper()}[{item_index}]", "rtcp_sdes_item", cursor, item_length + 2))
            item.fields.extend([
                FieldInfo("item_type", item_type, cursor, 1, _hex_bytes(bytes([item_type])), description=name),
                FieldInfo("item_length", item_length, cursor + 1, 1, _hex_bytes(bytes([item_length]))),
                FieldInfo("item_value", value, cursor + 2, item_length, _hex_bytes(raw)),
            ])
            record[name] = value
            cursor += item_length + 2
            item_index += 1
        chunk_size = cursor - chunk_offset
        cursor = min(packet_end, chunk_offset + ((chunk_size + 3) & ~3))
        chunk.size = max(4, cursor - chunk_offset)
        stats["sdes_chunks"].append(record)


def _parse_rtcp_bye(source: ByteSource, node: ParseNode, offset: int, size: int, source_count: int, diagnostics: list, stats: dict) -> None:
    cursor = offset + 4
    packet_end = offset + size
    required = source_count * 4
    if cursor + required > packet_end:
        _mark_truncated_report(node, diagnostics, cursor, "BYE SSRC list", required, packet_end - cursor)
        return
    ssrcs = []
    for index in range(source_count):
        raw = source.read_at(cursor, 4)
        ssrc = int.from_bytes(raw, "big")
        ssrcs.append(ssrc)
        stats["ssrcs"].add(ssrc)
        node.fields.append(FieldInfo(f"source_ssrc[{index}]", f"0x{ssrc:08X}", cursor, 4, _hex_bytes(raw)))
        cursor += 4
    reason = ""
    if cursor < packet_end:
        reason_length = source.read_at(cursor, 1)[0]
        node.fields.append(FieldInfo("reason_length", reason_length, cursor, 1, _hex_bytes(bytes([reason_length]))))
        cursor += 1
        available = packet_end - cursor
        if reason_length > available:
            _mark_truncated_report(node, diagnostics, cursor, "BYE reason", reason_length, available)
            reason_length = max(0, available)
        raw = source.read_at(cursor, reason_length)
        reason = raw.decode("utf-8", errors="replace")
        node.fields.append(FieldInfo("reason", reason, cursor, reason_length, _hex_bytes(raw)))
    stats["bye_events"].append({"ssrcs": ssrcs, "reason": reason, "offset": offset, "size": size})


def _feedback_header(source: ByteSource, node: ParseNode, offset: int, size: int, diagnostics: list, name: str) -> tuple[int, int, int] | None:
    if size < 12:
        _mark_truncated_report(node, diagnostics, offset, name, 12, size)
        return None
    raw = source.read_at(offset + 4, 8)
    sender_ssrc = int.from_bytes(raw[0:4], "big")
    media_ssrc = int.from_bytes(raw[4:8], "big")
    node.fields.extend([
        FieldInfo("sender_ssrc", f"0x{sender_ssrc:08X}", offset + 4, 4, _hex_bytes(raw[0:4])),
        FieldInfo("media_ssrc", f"0x{media_ssrc:08X}", offset + 8, 4, _hex_bytes(raw[4:8])),
    ])
    return sender_ssrc, media_ssrc, offset + 12


def _parse_rtcp_rtpfb(source: ByteSource, node: ParseNode, offset: int, size: int, fmt: int, diagnostics: list, stats: dict) -> None:
    header = _feedback_header(source, node, offset, size, diagnostics, "RTPFB")
    if not header:
        return
    sender_ssrc, media_ssrc, cursor = header
    stats["ssrcs"].update((sender_ssrc, media_ssrc))
    first_byte = source.read_at(offset, 1)
    node.fields.append(FieldInfo(
        "feedback_message_type", fmt, offset, 1, _hex_bytes(first_byte),
        description="Generic NACK" if fmt == 1 else "Unsupported RTPFB",
        bit_offset=offset * 8 + 3, bit_length=5,
    ))
    if fmt != 1:
        return
    lost_sequences: list[int] = []
    block_index = 0
    packet_end = offset + size
    while cursor + 4 <= packet_end:
        raw = source.read_at(cursor, 4)
        pid = int.from_bytes(raw[0:2], "big")
        blp = int.from_bytes(raw[2:4], "big")
        expanded = [pid] + [((pid + bit + 1) & 0xFFFF) for bit in range(16) if blp & (1 << bit)]
        lost_sequences.extend(expanded)
        block = node.add_child(ParseNode(f"Generic NACK[{block_index}]", "rtcp_nack", cursor, 4, severity=Severity.WARNING))
        block.fields.extend([
            FieldInfo("packet_id", pid, cursor, 2, _hex_bytes(raw[0:2])),
            FieldInfo("bitmask_lost_packets", f"0x{blp:04X}", cursor + 2, 2, _hex_bytes(raw[2:4])),
            FieldInfo("lost_sequences", expanded, cursor, 4),
        ])
        cursor += 4
        block_index += 1
    event = {"kind": "NACK", "packet_type": 205, "fmt": fmt, "sender_ssrc": sender_ssrc,
             "media_ssrc": media_ssrc, "lost_sequences": lost_sequences, "offset": offset, "size": size}
    stats["feedback_events"].append(event)
    stats["nack_lost_sequences"] += len(lost_sequences)
    message = f"RTCP Generic NACK 请求重传: media_ssrc=0x{media_ssrc:08X} lost={lost_sequences}"
    diagnostics.append(warn(message, offset, "RTCP"))
    node.severity = Severity.WARNING
    node.description = message


def _parse_rtcp_psfb(source: ByteSource, node: ParseNode, offset: int, size: int, fmt: int, diagnostics: list, stats: dict) -> None:
    header = _feedback_header(source, node, offset, size, diagnostics, "PSFB")
    if not header:
        return
    sender_ssrc, media_ssrc, cursor = header
    stats["ssrcs"].update((sender_ssrc, media_ssrc))
    kind = "PLI" if fmt == 1 else "FIR" if fmt == 4 else f"PSFB-{fmt}"
    first_byte = source.read_at(offset, 1)
    node.fields.append(FieldInfo(
        "feedback_message_type", fmt, offset, 1, _hex_bytes(first_byte), description=kind,
        bit_offset=offset * 8 + 3, bit_length=5,
    ))
    event = {"kind": kind, "packet_type": 206, "fmt": fmt, "sender_ssrc": sender_ssrc,
             "media_ssrc": media_ssrc, "offset": offset, "size": size}
    if fmt == 4:
        entries = []
        packet_end = offset + size
        while cursor + 8 <= packet_end:
            raw = source.read_at(cursor, 8)
            target_ssrc = int.from_bytes(raw[0:4], "big")
            sequence = raw[4]
            entry = node.add_child(ParseNode(f"FIR Entry[{len(entries)}]", "rtcp_fir", cursor, 8, severity=Severity.WARNING))
            entry.fields.extend([
                FieldInfo("target_ssrc", f"0x{target_ssrc:08X}", cursor, 4, _hex_bytes(raw[0:4])),
                FieldInfo("fir_sequence", sequence, cursor + 4, 1, _hex_bytes(raw[4:5])),
                FieldInfo("reserved", _hex_bytes(raw[5:8]), cursor + 5, 3, _hex_bytes(raw[5:8])),
            ])
            stats["ssrcs"].add(target_ssrc)
            entries.append({"target_ssrc": target_ssrc, "fir_sequence": sequence})
            cursor += 8
        event["fir_entries"] = entries
        event["fir_sequence"] = entries[0]["fir_sequence"] if entries else None
    if fmt in (1, 4):
        stats["feedback_events"].append(event)
        message = f"RTCP {kind} 视频刷新请求: media_ssrc=0x{media_ssrc:08X}"
        diagnostics.append(warn(message, offset, "RTCP"))
        node.severity = Severity.WARNING
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
        "report_records": [],
        "sender_report_records": [],
        "feedback_events": [],
        "sdes_chunks": [],
        "bye_events": [],
        "nack_lost_sequences": 0,
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
        "feedback_events": stats["feedback_events"],
        "feedback_event_count": len(stats["feedback_events"]),
        "nack_events": sum(item["kind"] == "NACK" for item in stats["feedback_events"]),
        "nack_lost_sequences": stats["nack_lost_sequences"],
        "pli_events": sum(item["kind"] == "PLI" for item in stats["feedback_events"]),
        "fir_events": sum(item["kind"] == "FIR" for item in stats["feedback_events"]),
        "sdes_chunks": stats["sdes_chunks"],
        "sdes_count": len(stats["sdes_chunks"]),
        "bye_events": stats["bye_events"],
        "bye_count": len(stats["bye_events"]),
    }


def _packet_timestamp(seconds: int, fraction: int, resolution: str) -> float:
    divisor = 1_000_000_000 if resolution == "nanosecond" else 1_000_000
    return round(seconds + fraction / divisor, 9)


def _sequence_event_message(ssrc: int, event: dict) -> str:
    kind = event.get("kind")
    if kind == "duplicate":
        return f"RTP sequence 重复: ssrc=0x{ssrc:08X} sequence={event.get('sequence')}"
    if kind == "reordered":
        return (
            f"RTP sequence 乱序: ssrc=0x{ssrc:08X} sequence={event.get('sequence')} "
            f"behind={event.get('behind')}"
        )
    return (
        f"RTP sequence 跳变（缺口）: ssrc=0x{ssrc:08X} expected={event.get('expected')} "
        f"current={event.get('sequence')} missing={event.get('missing')}"
    )


def _merge_rtp_video_sessions(transport: dict, video: dict) -> None:
    by_key = {(item.get("endpoint"), item.get("ssrc")): item for item in video.get("streams", [])}
    for session in transport.get("sessions", []):
        stream = by_key.get((session.get("endpoint"), session.get("ssrc")))
        if not stream:
            continue
        session["video_codec"] = stream.get("codec", "")
        session["video_nal_units"] = int(stream.get("nal_units", 0))
        session["video_completed_fragments"] = int(stream.get("completed_fragments", 0))
        session["video_incomplete_fragments"] = int(stream.get("incomplete_fragments", 0))
        session["video_issue_count"] = int(stream.get("issue_count", 0))
        session["video_status"] = stream.get("status", "normal")
        if stream.get("status") == "warning":
            session["status"] = "warning"
    transport["warning_sessions"] = sum(item.get("status") == "warning" for item in transport.get("sessions", []))
    transport["video_streams"] = int(video.get("stream_count", 0))
    transport["video_warning_streams"] = int(video.get("warning_streams", 0))


def _merge_sdp_transport_sessions(transport: dict, negotiated_packets: list[tuple[dict, dict]]) -> None:
    sessions = {
        (
            item.get("source_ip"), item.get("source_port"), item.get("destination_ip"),
            item.get("destination_port"), item.get("ssrc"),
        ): item
        for item in transport.get("sessions", [])
    }
    linked: set[int] = set()
    for packet, mapping in negotiated_packets:
        key = (
            packet.get("source_ip"), packet.get("source_port"), packet.get("destination_ip"),
            packet.get("destination_port"), f"0x{int(packet.get('ssrc', 0)):08X}",
        )
        session = sessions.get(key)
        if not session:
            continue
        session["negotiated_media"] = mapping.get("media", "")
        session["negotiated_encoding"] = mapping.get("encoding", "")
        session["negotiated_clock_rate"] = int(mapping.get("clock_rate", 0) or 0)
        session["sip_call_id"] = mapping.get("call_id", "")
        session["sdp_media_port"] = int(mapping.get("media_port", 0) or 0)
        session["mapping_source"] = mapping.get("mapping_source", "SDP")
        linked.add(int(session.get("index", 0)))
    transport["sdp_linked_sessions"] = len(linked)


def _merge_rtp_timing_quality(transport: dict) -> None:
    warning_sessions = 0
    available_sessions = 0
    max_jitter_ms = 0.0
    max_deviation_ms = 0.0
    total_burst_events = 0
    for session in transport.get("sessions", []):
        samples = session.pop("rtp_timing_samples", [])
        clock_rate = int(session.get("negotiated_clock_rate", 0) or 0)
        clock_source = "SDP" if clock_rate > 0 else ""
        payload_types = session.get("payload_types", [])
        if clock_rate <= 0 and len(payload_types) == 1:
            clock_rate = RTP_STATIC_CLOCK_RATES.get(int(payload_types[0]), 0)
            clock_source = "RTP static PT" if clock_rate > 0 else ""
        quality = _rtp_timing_metrics(samples, clock_rate, clock_source)
        session["rtp_timing"] = quality
        if quality["available"]:
            available_sessions += 1
            max_jitter_ms = max(max_jitter_ms, float(quality["rfc3550_jitter_ms"]))
            max_deviation_ms = max(max_deviation_ms, float(quality["max_abs_deviation_ms"]))
            total_burst_events += int(quality["burst_events"])
        if quality["status"] == "warning":
            warning_sessions += 1
            session["status"] = "warning"
    transport["rtp_timing"] = {
        "available": available_sessions > 0,
        "session_count": available_sessions,
        "warning_sessions": warning_sessions,
        "max_rfc3550_jitter_ms": round(max_jitter_ms, 3),
        "max_abs_deviation_ms": round(max_deviation_ms, 3),
        "burst_events": total_burst_events,
    }
    transport["warning_sessions"] = sum(item.get("status") == "warning" for item in transport.get("sessions", []))


def _rtp_timing_metrics(samples: list[dict], clock_rate: int, clock_source: str) -> dict:
    base = {
        "available": False, "status": "unavailable", "clock_rate": clock_rate, "clock_source": clock_source,
        "packet_count": len(samples), "interval_count": max(0, len(samples) - 1), "rfc3550_jitter_ms": 0.0,
        "average_arrival_interval_ms": 0.0, "min_arrival_interval_ms": 0.0, "max_arrival_interval_ms": 0.0,
        "max_abs_deviation_ms": 0.0, "burst_events": 0, "burst_threshold_ms": 20.0, "events": [],
    }
    if clock_rate <= 0 or len(samples) < 2:
        return base
    jitter = 0.0
    arrival_intervals: list[float] = []
    deviations: list[float] = []
    events: list[dict] = []
    previous = samples[0]
    for sample in samples[1:]:
        sequence_delta = (int(sample["sequence"]) - int(previous["sequence"])) & 0xFFFF
        if sequence_delta == 0 or sequence_delta & 0x8000:
            continue
        arrival_ms = (float(sample["capture_time"]) - float(previous["capture_time"])) * 1000
        timestamp_delta = (int(sample["rtp_timestamp"]) - int(previous["rtp_timestamp"])) & 0xFFFFFFFF
        if timestamp_delta & 0x80000000:
            timestamp_delta -= 0x100000000
        media_ms = timestamp_delta * 1000 / clock_rate
        deviation_ms = arrival_ms - media_ms
        jitter += (abs(deviation_ms) - jitter) / 16
        arrival_intervals.append(arrival_ms)
        deviations.append(deviation_ms)
        if abs(deviation_ms) > base["burst_threshold_ms"]:
            events.append({
                "sequence": int(sample["sequence"]), "offset": int(sample["offset"]),
                "arrival_interval_ms": round(arrival_ms, 3), "media_interval_ms": round(media_ms, 3),
                "deviation_ms": round(deviation_ms, 3),
            })
        previous = sample
    if not arrival_intervals:
        return base
    max_deviation = max((abs(value) for value in deviations), default=0.0)
    base.update({
        "available": True, "status": "warning" if events else "normal", "interval_count": len(arrival_intervals),
        "rfc3550_jitter_ms": round(jitter, 3),
        "rfc3550_jitter_timestamp_units": round(jitter * clock_rate / 1000, 3),
        "average_arrival_interval_ms": round(sum(arrival_intervals) / len(arrival_intervals), 3),
        "min_arrival_interval_ms": round(min(arrival_intervals), 3),
        "max_arrival_interval_ms": round(max(arrival_intervals), 3),
        "max_abs_deviation_ms": round(max_deviation, 3), "burst_events": len(events), "events": events,
    })
    return base


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
