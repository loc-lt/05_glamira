"""Stream BSON documents out of a gzipped ustar mongodump.

The Glamira archive is `dump/countly/summary.bson` (~31 GB uncompressed) inside
a ~5 GB `.tar.gz`. GNU tar base-256 sizes are required because the member is
larger than the classic 8 GB octal field.
"""

from __future__ import annotations

def parse_tar_size(field: bytes) -> int:
    """Decode a 12-byte ustar size, including the GNU base-256 extension."""
    if len(field) != 12:
        raise ValueError(f"tar size field must be 12 bytes, got {len(field)}")
    if field[0] in (0x80, 0xFF):
        magnitude = int.from_bytes(field[1:], "big", signed=False)
        if field[0] == 0xFF:
            magnitude -= 1 << (8 * (len(field) - 1))
        return magnitude
    text = field.split(b"\x00", 1)[0].strip()
    if not text:
        return 0
    return int(text, 8)


def parse_tar_header(header: bytes) -> tuple[str, int, str]:
    if len(header) != 512:
        raise ValueError(f"tar header must be 512 bytes, got {len(header)}")
    name = header[0:100].split(b"\x00", 1)[0].decode("utf-8", "replace")
    prefix = header[345:500].split(b"\x00", 1)[0].decode("utf-8", "replace")
    size = parse_tar_size(header[124:136])
    typeflag = "0" if header[156] == 0 else chr(header[156])
    full_name = f"{prefix}/{name}" if prefix else name
    return full_name, size, typeflag
