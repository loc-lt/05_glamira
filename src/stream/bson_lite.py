"""Minimal BSON walker for schema-on-read scans.

Only top-level fields are decoded. Long strings (user agent, email, referrer)
are skipped in place so a multi-gigabyte dump is never materialized.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass

# Strings whose contents Phase 0 actually aggregates. Everything else is
# measured as empty vs non-empty without copying the bytes.
MATERIAL_KEYS = frozenset(
    {
        b"collection",
        b"local_time",
        b"ip",
        b"store_id",
        b"product_id",
        b"viewing_product_id",
        b"current_url",
        b"device_id",
        b"user_id_db",
        b"show_recommendation",
        b"api_version",
    }
)


@dataclass(slots=True)
class Val:
    kind: str
    nullish: bool = False
    raw: bytes | None = None
    number: int | float | None = None
    flag: bool | None = None
    oid: bytes | None = None
    empty_container: bool = False
    payload: memoryview | None = None


def iter_fields(
    doc: bytes | memoryview,
    material_keys: frozenset[bytes] = MATERIAL_KEYS,
) -> Iterator[tuple[str, Val]]:
    """Yield top-level `(key, value)` pairs from one BSON document."""
    mv = doc if isinstance(doc, memoryview) else memoryview(doc)
    if len(mv) < 5:
        raise ValueError(f"bson document shorter than 5 bytes ({len(mv)})")
    declared = int.from_bytes(mv[0:4], "little", signed=True)
    if declared != len(mv):
        raise ValueError(f"bson length prefix {declared} does not match buffer {len(mv)}")
    index = 4
    end = declared - 1
    while index < end:
        type_code = mv[index]
        index += 1
        key_bytes, index = _cstring_bytes(mv, index)
        materialize = key_bytes in material_keys
        value, index = _read_value(type_code, mv, index, materialize)
        yield key_bytes.decode("utf-8", "replace"), value
    if index != end:
        raise ValueError(f"bson parser stopped at {index}, expected {end}")


def _cstring_bytes(mv: memoryview, index: int) -> tuple[bytes, int]:
    cursor = index
    limit = len(mv)
    while cursor < limit and mv[cursor] != 0:
        cursor += 1
    if cursor >= limit:
        raise ValueError("unterminated BSON cstring")
    return mv[index:cursor].tobytes(), cursor + 1


def _read_value(type_code: int, mv: memoryview, index: int, materialize: bool) -> tuple[Val, int]:
    if type_code == 0x01:
        number = struct.unpack_from("<d", mv, index)[0]
        return Val("float", number=number), index + 8
    if type_code == 0x02:
        return _read_string(mv, index, materialize)
    if type_code in (0x03, 0x04):
        length = int.from_bytes(mv[index : index + 4], "little", signed=True)
        if length < 5 or index + length > len(mv):
            raise ValueError(f"bad embedded document length {length}")
        payload = mv[index : index + length]
        kind = "doc" if type_code == 0x03 else "arr"
        return Val(kind, empty_container=length <= 5, payload=payload), index + length
    if type_code == 0x05:
        length = int.from_bytes(mv[index : index + 4], "little", signed=True)
        if length < 0 or index + 5 + length > len(mv):
            raise ValueError(f"bad binary length {length}")
        return Val("bin"), index + 5 + length
    if type_code == 0x06:
        return Val("null", nullish=True), index
    if type_code == 0x07:
        oid = mv[index : index + 12].tobytes()
        return Val("oid", oid=oid), index + 12
    if type_code == 0x08:
        return Val("bool", flag=bool(mv[index])), index + 1
    if type_code == 0x09:
        millis = int.from_bytes(mv[index : index + 8], "little", signed=True)
        return Val("int", number=millis), index + 8
    if type_code == 0x0A:
        return Val("null", nullish=True), index
    if type_code == 0x0B:
        _, index = _cstring_bytes(mv, index)
        _, index = _cstring_bytes(mv, index)
        return Val("other"), index
    if type_code == 0x0C:
        _, index = _read_string(mv, index, materialize=False)
        return Val("other"), index + 12
    if type_code in (0x0D, 0x0E):
        _, index = _read_string(mv, index, materialize=False)
        return Val("other"), index
    if type_code == 0x0F:
        length = int.from_bytes(mv[index : index + 4], "little", signed=True)
        if length < 4 or index + length > len(mv):
            raise ValueError(f"bad code_w_scope length {length}")
        return Val("other"), index + length
    if type_code == 0x10:
        number = int.from_bytes(mv[index : index + 4], "little", signed=True)
        return Val("int", number=number), index + 4
    if type_code == 0x11:
        return Val("int"), index + 8
    if type_code == 0x12:
        number = int.from_bytes(mv[index : index + 8], "little", signed=True)
        return Val("int", number=number), index + 8
    if type_code == 0x13:
        return Val("other"), index + 16
    if type_code in (0x7F, 0xFF):
        return Val("other"), index
    raise ValueError(f"unsupported BSON type 0x{type_code:02x}")


def _read_string(mv: memoryview, index: int, materialize: bool) -> tuple[Val, int]:
    length = int.from_bytes(mv[index : index + 4], "little", signed=True)
    if length < 1 or index + 4 + length > len(mv):
        raise ValueError(f"bad BSON string length {length}")
    start = index + 4
    end = start + length - 1
    if mv[end] != 0:
        raise ValueError("BSON string is missing its NUL terminator")
    empty = length <= 1
    raw = mv[start:end].tobytes() if materialize else None
    return Val("str", nullish=empty, raw=raw), end + 1
