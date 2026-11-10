"""Stream BSON documents out of a gzipped ustar mongodump.

The Glamira archive is `dump/countly/summary.bson` (~31 GB uncompressed) inside
a ~5 GB `.tar.gz`. GNU tar base-256 sizes are required because the member is
larger than the classic 8 GB octal field.
"""

from __future__ import annotations

import gzip
from collections.abc import Iterator
from pathlib import Path

_CHUNK = 8 * 1024 * 1024
_MAX_DOC = 16 * 1024 * 1024


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


class SummaryDump:
    """Iterate BSON documents from the `summary.bson` member of a mongodump tar.gz."""

    def __init__(self, path: str | Path, member_suffix: str = "summary.bson") -> None:
        self.path = Path(path)
        self.member_suffix = member_suffix
        self.member_name = ""
        self.member_size = 0
        self.bytes_yielded = 0
        self.leftover_bytes = 0
        self.completed = False

    def __iter__(self) -> Iterator[bytes]:
        if not self.path.is_file():
            raise FileNotFoundError(f"archive not found: {self.path}")
        self.completed = False
        self.bytes_yielded = 0
        self.leftover_bytes = 0
        with gzip.open(self.path, "rb") as handle:
            while True:
                header = _read_exact(handle, 512)
                if header == b"\x00" * 512:
                    break
                name, size, typeflag = parse_tar_header(header)
                if typeflag == "L":
                    payload = _read_exact(handle, size)
                    _discard(handle, _padding(size))
                    long_name = payload.rstrip(b"\x00").decode("utf-8", "replace")
                    header = _read_exact(handle, 512)
                    _, size, typeflag = parse_tar_header(header)
                    name = long_name
                if typeflag in ("x", "g"):
                    raise RuntimeError(
                        f"pax tar header at {name!r} is not supported; "
                        "this reader expects ustar mongodump members"
                    )
                if typeflag in ("0", "\0") and name.endswith(self.member_suffix):
                    self.member_name = name
                    self.member_size = size
                    yield from self._iter_member(handle, size)
                    self.completed = True
                    return
                _discard(handle, size + _padding(size))
        raise FileNotFoundError(
            f"no tar member ending with {self.member_suffix!r} in {self.path}"
        )

    def _iter_member(self, handle: gzip.GzipFile, size: int) -> Iterator[bytes]:
        limited = _LimitedReader(handle, size)
        buffer = bytearray()
        while True:
            if len(buffer) < 4:
                chunk = limited.read(_CHUNK)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) < 4:
                    break
            length = int.from_bytes(buffer[:4], "little", signed=True)
            if length < 5 or length > _MAX_DOC:
                raise ValueError(f"invalid BSON document length {length}")
            while len(buffer) < length:
                chunk = limited.read(max(length - len(buffer), _CHUNK))
                if not chunk:
                    raise EOFError(
                        f"truncated BSON document: need {length} bytes, have {len(buffer)}"
                    )
                buffer += chunk
            document = bytes(buffer[:length])
            del buffer[:length]
            self.bytes_yielded += length
            yield document
        self.leftover_bytes = len(buffer) + limited.left


def _padding(size: int) -> int:
    remainder = size % 512
    return 0 if remainder == 0 else 512 - remainder


def _read_exact(handle: gzip.GzipFile, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        chunk = handle.read(remaining)
        if not chunk:
            raise EOFError(f"unexpected EOF in tar stream, still need {remaining} bytes")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks) if len(chunks) != 1 else chunks[0]


def _discard(handle: gzip.GzipFile, count: int) -> None:
    remaining = count
    while remaining:
        chunk = handle.read(min(remaining, _CHUNK))
        if not chunk:
            raise EOFError(f"unexpected EOF while skipping tar member, still need {remaining}")
        remaining -= len(chunk)


class _LimitedReader:
    def __init__(self, handle: gzip.GzipFile, limit: int) -> None:
        self._handle = handle
        self.left = limit

    def read(self, count: int) -> bytes:
        if self.left <= 0 or count <= 0:
            return b""
        chunk = self._handle.read(min(count, self.left))
        self.left -= len(chunk)
        return chunk
