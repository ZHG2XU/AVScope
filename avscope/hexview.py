from __future__ import annotations


def format_hex(data: bytes, base_offset: int = 0, bytes_per_line: int = 16) -> str:
    lines: list[str] = []
    for start in range(0, len(data), bytes_per_line):
        chunk = data[start : start + bytes_per_line]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        hex_part = hex_part.ljust(bytes_per_line * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{base_offset + start:08X}  {hex_part}  |{ascii_part}|")
    return "\n".join(lines)


def parse_offset(text: str) -> int:
    value = text.strip().lower()
    if value.startswith("0x"):
        return int(value, 16)
    return int(value, 10)
