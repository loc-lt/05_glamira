"""Single-pass aggregates for the Phase 0 null profile and quality report.

Nullish means the field is absent, BSON null, or an empty string.
`false`, `0`, and empty objects/arrays are present values and are counted
separately. Email and user-agent bytes are never copied.
"""

from __future__ import annotations

import re
import struct
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.explore.sketch import HyperLogLog
from src.stream.bson_lite import Val, iter_fields
from src.stream.tar_bson import SummaryDump

CRITICAL_FIELDS: tuple[str, ...] = (
    "ip",
    "product_id",
    "viewing_product_id",
    "current_url",
    "cat_id",
    "cart_products",
    "device_id",
    "local_time",
    "email_address",
)
EXTRA_FIELDS: tuple[str, ...] = (
    "referrer_url",
    "user_id_db",
    "store_id",
    "time_stamp",
    "option",
    "order_id",
    "collect_id",
    "show_recommendation",
    "user_agent",
    "resolution",
)
TRACKED_FIELDS: tuple[str, ...] = CRITICAL_FIELDS + EXTRA_FIELDS
VARIANT_FIELDS: tuple[str, ...] = (
    "product_id",
    "viewing_product_id",
    "show_recommendation",
    "recommendation",
    "utm_source",
    "utm_medium",
    "option",
    "cart_products",
)
VALUE_FIELDS: tuple[str, ...] = ("show_recommendation", "api_version")

_LOCAL_TIME = re.compile(br"^(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{1,2}):(\d{1,2})$")
_EXACT_DUP_PREFIX = 500_000
_MAX_TRACKED_KEYS = 300
_MAX_HOSTS = 500
_MAX_STORES = 400


@dataclass
class Profile:
    source: str
    member_name: str
    member_size: int
    compressed_bytes: int
    sample_size_requested: int
    docs_scanned: int
    bson_bytes: int
    completed_member: bool
    elapsed_seconds: float
    parse_errors: int
    error_samples: list[str]
    event_counts: dict[str, int]
    nullish: dict[str, dict[str, int]]
    key_docs: dict[str, int]
    extra_untracked_keys: int
    variants: dict[str, dict[str, int]]
    product_kind_by_event: dict[str, dict[str, int]]
    ip_class: dict[str, int]
    hosts: dict[str, int]
    store_counts: dict[str, int]
    html_by_event: dict[str, int]
    url_nonempty_by_event: dict[str, int]
    product_query_by_event: dict[str, int]
    product_link_by_event: dict[str, int]
    pid_without_html: dict[str, int]
    cart_present: int
    cart_with_product_id: int
    ts_min: int | None
    ts_max: int | None
    local_unparsed: int
    local_compared: int
    offset_hours: dict[int, int]
    offset_out_of_range: int
    store_offset_mode: dict[str, dict[str, int | float | str]]
    hll: dict[str, int]
    exact_dup_prefix_n: int
    exact_dup_prefix_dups: int
    oid_compared: int
    oid_skew_over_1d: int
    leftover_bytes: int
    scanned_at: str
    value_counts: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "member_name": self.member_name,
            "member_size": self.member_size,
            "compressed_bytes": self.compressed_bytes,
            "sample_size_requested": self.sample_size_requested,
            "docs_scanned": self.docs_scanned,
            "bson_bytes": self.bson_bytes,
            "completed_member": self.completed_member,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "parse_errors": self.parse_errors,
            "error_samples": self.error_samples,
            "event_counts": self.event_counts,
            "nullish": self.nullish,
            "key_docs": self.key_docs,
            "extra_untracked_keys": self.extra_untracked_keys,
            "variants": self.variants,
            "product_kind_by_event": self.product_kind_by_event,
            "ip_class": self.ip_class,
            "hosts": self.hosts,
            "store_counts": self.store_counts,
            "html_by_event": self.html_by_event,
            "url_nonempty_by_event": self.url_nonempty_by_event,
            "product_query_by_event": self.product_query_by_event,
            "product_link_by_event": self.product_link_by_event,
            "pid_without_html": self.pid_without_html,
            "cart_present": self.cart_present,
            "cart_with_product_id": self.cart_with_product_id,
            "ts_min": self.ts_min,
            "ts_max": self.ts_max,
            "local_unparsed": self.local_unparsed,
            "local_compared": self.local_compared,
            "offset_hours": {str(k): v for k, v in sorted(self.offset_hours.items())},
            "offset_out_of_range": self.offset_out_of_range,
            "store_offset_mode": self.store_offset_mode,
            "hll": self.hll,
            "exact_dup_prefix_n": self.exact_dup_prefix_n,
            "exact_dup_prefix_dups": self.exact_dup_prefix_dups,
            "oid_compared": self.oid_compared,
            "oid_skew_over_1d": self.oid_skew_over_1d,
            "leftover_bytes": self.leftover_bytes,
            "scanned_at": self.scanned_at,
            "value_counts": self.value_counts,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> Profile:
        data = dict(payload)
        hours = data.get("offset_hours", {})
        if isinstance(hours, dict):
            data["offset_hours"] = {int(key): value for key, value in hours.items()}
        return cls(**data)


@dataclass
class _Acc:
    event_counts: Counter[str] = field(default_factory=Counter)
    nullish: dict[str, dict[str, int]] = field(default_factory=dict)
    key_docs: Counter[str] = field(default_factory=Counter)
    extra_untracked_keys: int = 0
    variants: dict[str, Counter[str]] = field(
        default_factory=lambda: {name: Counter() for name in VARIANT_FIELDS}
    )
    product_kind_by_event: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    ip_class: Counter[str] = field(default_factory=Counter)
    hosts: Counter[str] = field(default_factory=Counter)
    store_counts: Counter[str] = field(default_factory=Counter)
    html_by_event: Counter[str] = field(default_factory=Counter)
    url_nonempty_by_event: Counter[str] = field(default_factory=Counter)
    product_query_by_event: Counter[str] = field(default_factory=Counter)
    product_link_by_event: Counter[str] = field(default_factory=Counter)
    pid_without_html: Counter[str] = field(default_factory=Counter)
    cart_present: int = 0
    cart_with_product_id: int = 0
    ts_min: int | None = None
    ts_max: int | None = None
    local_unparsed: int = 0
    local_compared: int = 0
    offset_hours: Counter[int] = field(default_factory=Counter)
    offset_out_of_range: int = 0
    store_offsets: dict[str, Counter[int]] = field(default_factory=lambda: defaultdict(Counter))
    hll_ip: HyperLogLog = field(default_factory=HyperLogLog)
    hll_device: HyperLogLog = field(default_factory=HyperLogLog)
    hll_product: HyperLogLog = field(default_factory=HyperLogLog)
    hll_viewing: HyperLogLog = field(default_factory=HyperLogLog)
    hll_user: HyperLogLog = field(default_factory=HyperLogLog)
    seen_ids: set[bytes] = field(default_factory=set)
    exact_dup_prefix_n: int = 0
    exact_dup_prefix_dups: int = 0
    oid_compared: int = 0
    oid_skew_over_1d: int = 0
    value_counts: dict[str, Counter[str]] = field(
        default_factory=lambda: {name: Counter() for name in VALUE_FIELDS}
    )
    parse_errors: int = 0
    error_samples: list[str] = field(default_factory=list)
    docs: int = 0
    bson_bytes: int = 0


def profile_documents(
    documents: Iterable[bytes],
    *,
    source: str = "memory",
    sample_size: int = 0,
    progress_every: int = 0,
) -> Profile:
    """Aggregate `documents`. `sample_size=0` reads the whole iterator."""
    started = time.perf_counter()
    acc = _Acc()
    stopped_early = False
    for document in documents:
        acc.bson_bytes += len(document)
        try:
            _accumulate(document, acc)
        except (ValueError, UnicodeError, IndexError, struct.error) as exc:
            acc.parse_errors += 1
            if len(acc.error_samples) < 5:
                acc.error_samples.append(f"{type(exc).__name__}: {exc}"[:240])
            if acc.parse_errors >= 100:
                raise RuntimeError("stopped after 100 BSON parse errors") from exc
        acc.docs += 1
        if progress_every and acc.docs % progress_every == 0:
            elapsed = time.perf_counter() - started
            rate = acc.docs / elapsed if elapsed else 0
            print(
                f"[profile] docs={acc.docs:,} events={len(acc.event_counts)} "
                f"rate={rate:,.0f}/s elapsed={elapsed:,.0f}s",
                flush=True,
            )
        if sample_size and acc.docs >= sample_size:
            stopped_early = True
            break
    elapsed = time.perf_counter() - started
    return _finish(acc, source=source, sample_size=sample_size, elapsed=elapsed, early=stopped_early)


def profile_tar(
    path: str,
    *,
    sample_size: int = 0,
    progress_every: int = 1_000_000,
    member_suffix: str = "summary.bson",
) -> Profile:
    dump = SummaryDump(path, member_suffix=member_suffix)
    profile = profile_documents(
        _iter_dump(dump),
        source=str(path),
        sample_size=sample_size,
        progress_every=progress_every,
    )
    compressed = dump.path.stat().st_size if dump.path.is_file() else 0
    profile.compressed_bytes = compressed
    profile.member_name = dump.member_name
    profile.member_size = dump.member_size
    profile.completed_member = dump.completed and sample_size == 0
    profile.leftover_bytes = dump.leftover_bytes if profile.completed_member else -1
    return profile


def _iter_dump(dump: SummaryDump) -> Iterator[bytes]:
    yield from dump


def classify_ip(raw: bytes) -> str:
    if not raw:
        return "empty"
    if b":" in raw:
        return "ipv6"
    parts = raw.split(b".")
    if len(parts) != 4:
        return "invalid"
    numbers: list[int] = []
    for part in parts:
        if not part or not part.isdigit():
            return "invalid"
        number = int(part)
        if number > 255:
            return "invalid"
        numbers.append(number)
    first, second = numbers[0], numbers[1]
    if first == 10 or (first == 172 and 16 <= second <= 31) or (first == 192 and second == 168):
        return "private"
    if first == 127:
        return "loopback"
    if first == 0 or first >= 224 or (first == 169 and second == 254):
        return "non_public"
    return "public"


def local_time_to_epoch(raw: bytes) -> int | None:
    match = _LOCAL_TIME.match(raw)
    if match is None:
        return None
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 60):
        return None
    try:
        parsed = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(parsed.timestamp())


def _accumulate(document: bytes, acc: _Acc) -> None:
    seen: dict[str, Val] = {}
    seen_keys: set[str] = set()
    for key, value in iter_fields(document):
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key in acc.key_docs or len(acc.key_docs) < _MAX_TRACKED_KEYS:
            acc.key_docs[key] += 1
        else:
            acc.extra_untracked_keys += 1
        seen[key] = value

    event_val = seen.get("collection")
    if event_val is None or event_val.kind == "null" or event_val.nullish:
        event = "(missing)"
    else:
        event = (event_val.raw or b"").decode("utf-8", "replace") or "(empty)"
    acc.event_counts[event] += 1

    bucket = acc.nullish.get(event)
    if bucket is None:
        bucket = {name: 0 for name in TRACKED_FIELDS}
        acc.nullish[event] = bucket

    for name in TRACKED_FIELDS:
        value = seen.get(name)
        if value is None or value.nullish or value.kind == "null":
            bucket[name] += 1

    for name in VARIANT_FIELDS:
        acc.variants[name][_variant_kind(seen.get(name))] += 1
    acc.product_kind_by_event[event][_variant_kind(seen.get("product_id"))] += 1

    ip_value = seen.get("ip")
    if ip_value is None:
        acc.ip_class["missing"] += 1
    elif ip_value.kind == "null":
        acc.ip_class["null"] += 1
    elif ip_value.kind == "str":
        label = "empty" if ip_value.nullish else classify_ip(ip_value.raw or b"")
        acc.ip_class[label] += 1
        if label == "public" and ip_value.raw:
            acc.hll_ip.add(ip_value.raw)
    else:
        acc.ip_class["other"] += 1

    _add_hll(acc.hll_device, seen.get("device_id"))
    _add_hll(acc.hll_product, seen.get("product_id"))
    _add_hll(acc.hll_viewing, seen.get("viewing_product_id"))
    _add_hll(acc.hll_user, seen.get("user_id_db"))

    url = seen.get("current_url")
    has_html = False
    url_present = url is not None and not url.nullish and url.kind == "str" and bool(url.raw)
    if url_present and url is not None and url.raw is not None:
        acc.url_nonempty_by_event[event] += 1
        has_html = b".html" in url.raw
        if has_html:
            acc.html_by_event[event] += 1
        if b"product_id=" in url.raw or b"itm_" in url.raw:
            acc.product_query_by_event[event] += 1
        host = _host(url.raw)
        if host:
            if host in acc.hosts or len(acc.hosts) < _MAX_HOSTS:
                acc.hosts[host] += 1
            else:
                acc.hosts["(other)"] += 1

    product_present = _is_present(seen.get("product_id"))
    viewing_present = _is_present(seen.get("viewing_product_id"))
    if product_present and not has_html:
        acc.pid_without_html[event] += 1

    cart = seen.get("cart_products")
    cart_has_pid = False
    if cart is not None and cart.kind == "arr" and not cart.empty_container and cart.payload is not None:
        acc.cart_present += 1
        cart_has_pid = _array_has_product_id(cart.payload)
        if cart_has_pid:
            acc.cart_with_product_id += 1
    elif cart is not None and not cart.nullish and cart.kind != "null":
        acc.cart_present += 1

    if product_present or viewing_present or cart_has_pid:
        acc.product_link_by_event[event] += 1

    store_raw = _present_text(seen.get("store_id"))
    store_id = store_raw or "(missing)"
    if store_id in acc.store_counts or len(acc.store_counts) < _MAX_STORES:
        acc.store_counts[store_id] += 1

    timestamp = _as_int(seen.get("time_stamp"))
    if timestamp is not None:
        acc.ts_min = timestamp if acc.ts_min is None else min(acc.ts_min, timestamp)
        acc.ts_max = timestamp if acc.ts_max is None else max(acc.ts_max, timestamp)

    local_raw = seen.get("local_time")
    local_epoch = None
    if local_raw is not None and local_raw.kind == "str" and not local_raw.nullish and local_raw.raw:
        local_epoch = local_time_to_epoch(local_raw.raw)
        if local_epoch is None:
            acc.local_unparsed += 1
    if timestamp is not None and local_epoch is not None:
        acc.local_compared += 1
        delta_hours = int(round((local_epoch - timestamp) / 3600))
        if -14 <= delta_hours <= 14:
            acc.offset_hours[delta_hours] += 1
            if store_id in acc.store_offsets or len(acc.store_offsets) < _MAX_STORES:
                acc.store_offsets[store_id][delta_hours] += 1
        else:
            acc.offset_out_of_range += 1

    oid = seen.get("_id")
    if oid is not None and oid.oid and timestamp is not None:
        oid_ts = int.from_bytes(oid.oid[:4], "big")
        acc.oid_compared += 1
        if abs(oid_ts - timestamp) > 86_400:
            acc.oid_skew_over_1d += 1
    if oid is not None and oid.oid and acc.exact_dup_prefix_n < _EXACT_DUP_PREFIX:
        acc.exact_dup_prefix_n += 1
        if oid.oid in acc.seen_ids:
            acc.exact_dup_prefix_dups += 1
        else:
            acc.seen_ids.add(oid.oid)
        if acc.exact_dup_prefix_n >= _EXACT_DUP_PREFIX:
            acc.seen_ids.clear()
    for name in VALUE_FIELDS:
        _count_low_card_value(acc, name, seen.get(name))


def _top_counts(counter: Counter[str], limit: int = 20) -> dict[str, int]:
    """Keep the largest labels and fold the tail into `(other)` so counts still sum."""
    head: list[tuple[str, int]] = []
    rest = 0
    for key, count in counter.most_common():
        if key == "(other)":
            rest += count
            continue
        if len(head) < limit - 1:
            head.append((key, count))
        else:
            rest += count
    result = dict(head)
    if rest:
        result["(other)"] = rest
    return result


def _count_low_card_value(acc: _Acc, name: str, value: Val | None) -> None:
    counter = acc.value_counts[name]
    if value is None:
        label = "(missing)"
    elif value.kind == "null" or (value.nullish and value.kind != "str"):
        label = "(null)"
    elif value.kind == "str":
        if value.nullish or not value.raw:
            label = "(empty)"
        elif name == "show_recommendation" and value.raw not in (b"true", b"false"):
            # Corrupted values include cookie and ad-click fragments. Do not keep them.
            label = "(other)"
        elif name == "api_version" and not re.fullmatch(br"[0-9.]{1,8}", value.raw):
            label = "(other)"
        else:
            label = value.raw.decode("utf-8", "replace")[:80]
    elif value.kind == "bool":
        label = "true" if value.flag else "false"
    else:
        label = f"({value.kind})"
    if label not in counter and len(counter) >= 30:
        counter["(other)"] += 1
    else:
        counter[label] += 1


def _variant_kind(value: Val | None) -> str:
    if value is None:
        return "missing"
    if value.kind == "null" or value.nullish and value.kind != "str":
        return "null"
    if value.kind == "str":
        return "empty_str" if value.nullish else "str"
    if value.kind == "doc":
        return "empty_doc" if value.empty_container else "doc"
    if value.kind == "arr":
        return "empty_arr" if value.empty_container else "arr"
    if value.kind in {"int", "float", "bool", "bin", "oid"}:
        return value.kind
    return "other"


def _is_present(value: Val | None) -> bool:
    return value is not None and not value.nullish and value.kind != "null"


def _present_text(value: Val | None) -> str:
    if value is None or value.nullish or value.kind == "null":
        return ""
    if value.kind == "str" and value.raw is not None:
        return value.raw.decode("utf-8", "replace")
    if value.kind == "int" and isinstance(value.number, int):
        return str(value.number)
    return ""


def _as_int(value: Val | None) -> int | None:
    if value is None or value.number is None:
        return None
    if isinstance(value.number, float):
        return int(round(value.number))
    return int(value.number)


def _add_hll(sketch: HyperLogLog, value: Val | None) -> None:
    if value is None or value.nullish or value.kind == "null":
        return
    if value.kind == "str" and value.raw:
        sketch.add(value.raw)
    elif value.kind == "int" and value.number is not None:
        sketch.add(str(int(value.number)).encode("ascii"))


def _host(url: bytes) -> str | None:
    scheme = url.find(b"://")
    if scheme < 0:
        return None
    rest = url[scheme + 3 :]
    cut = len(rest)
    for separator in (b"/", b"?", b"#"):
        found = rest.find(separator)
        if found != -1:
            cut = min(cut, found)
    host = rest[:cut]
    if b"@" in host:
        host = host.split(b"@", 1)[1]
    if not host:
        return None
    text = host.decode("utf-8", "replace").lower()
    if "@" in text:
        return None
    return text[:200]


def _array_has_product_id(payload: memoryview) -> bool:
    for _key, value in iter_fields(payload, material_keys=frozenset({b"product_id"})):
        if value.kind == "doc" and value.payload is not None:
            for nested_key, nested in iter_fields(value.payload, material_keys=frozenset({b"product_id"})):
                if nested_key == "product_id" and _is_present(nested):
                    return True
        elif _key == "product_id" and _is_present(value):
            return True
    return False


def _finish(
    acc: _Acc,
    *,
    source: str,
    sample_size: int,
    elapsed: float,
    early: bool,
) -> Profile:
    # Release the prefix id set before building the result.
    acc.seen_ids.clear()
    store_modes: dict[str, dict[str, int | float | str]] = {}
    for store_id, hours in acc.store_offsets.items():
        total = sum(hours.values())
        mode_hour, mode_count = hours.most_common(1)[0]
        store_modes[store_id] = {
            "mode_hour": mode_hour,
            "mode_count": mode_count,
            "compared": total,
            "mode_share": round(mode_count / total, 4) if total else 0.0,
        }
    return Profile(
        source=source,
        member_name="",
        member_size=0,
        compressed_bytes=0,
        sample_size_requested=sample_size,
        docs_scanned=acc.docs,
        bson_bytes=acc.bson_bytes,
        completed_member=not early and sample_size == 0,
        elapsed_seconds=elapsed,
        parse_errors=acc.parse_errors,
        error_samples=acc.error_samples,
        event_counts=dict(acc.event_counts.most_common()),
        nullish=acc.nullish,
        key_docs=dict(acc.key_docs.most_common()),
        extra_untracked_keys=acc.extra_untracked_keys,
        variants={name: dict(counter) for name, counter in acc.variants.items()},
        product_kind_by_event={
            event: dict(counter) for event, counter in acc.product_kind_by_event.items()
        },
        ip_class=dict(acc.ip_class),
        hosts=dict(acc.hosts.most_common()),
        store_counts=dict(acc.store_counts.most_common()),
        html_by_event=dict(acc.html_by_event),
        url_nonempty_by_event=dict(acc.url_nonempty_by_event),
        product_query_by_event=dict(acc.product_query_by_event),
        product_link_by_event=dict(acc.product_link_by_event),
        pid_without_html=dict(acc.pid_without_html),
        cart_present=acc.cart_present,
        cart_with_product_id=acc.cart_with_product_id,
        ts_min=acc.ts_min,
        ts_max=acc.ts_max,
        local_unparsed=acc.local_unparsed,
        local_compared=acc.local_compared,
        offset_hours=dict(acc.offset_hours),
        offset_out_of_range=acc.offset_out_of_range,
        store_offset_mode=store_modes,
        hll={
            "ip_public": int(round(acc.hll_ip.estimate())),
            "device_id": int(round(acc.hll_device.estimate())),
            "product_id": int(round(acc.hll_product.estimate())),
            "viewing_product_id": int(round(acc.hll_viewing.estimate())),
            "user_id_db": int(round(acc.hll_user.estimate())),
        },
        exact_dup_prefix_n=acc.exact_dup_prefix_n,
        exact_dup_prefix_dups=acc.exact_dup_prefix_dups,
        oid_compared=acc.oid_compared,
        oid_skew_over_1d=acc.oid_skew_over_1d,
        leftover_bytes=-1,
        scanned_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        value_counts={name: _top_counts(counter) for name, counter in acc.value_counts.items()},
    )
