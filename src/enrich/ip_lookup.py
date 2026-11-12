"""Resolve public IPv4 addresses with the coach BIN and store one row per IP.

Events stay in `glamira_raw`. Country is joined later on `ip`. That avoids
writing the same city onto millions of copies of one address.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from IP2Location import IP2Location
from pymongo import UpdateOne

from src.config import Settings
from src.db import get_client
from src.explore.profile import classify_ip

_MISSING = {"", "-", "N/A", "n/a"}


@dataclass
class IpCoverage:
    events: int
    distinct_ips: int
    public_events: int
    resolved_events: int
    checkout_events: int
    checkout_resolved: int
    top_countries: list[tuple[str, int]]

    @property
    def resolved_pct(self) -> float:
        if self.public_events == 0:
            return 0.0
        return 100.0 * self.resolved_events / self.public_events

    @property
    def checkout_pct(self) -> float:
        if self.checkout_events == 0:
            return 0.0
        return 100.0 * self.checkout_resolved / self.checkout_events


def load_ip_geo(
    settings: Settings,
    *,
    counts_path: str = "data/staging/ip_event_counts.tsv",
    checkout_path: str = "data/staging/checkout_success_ips.tsv",
    bin_path: str | None = None,
    out_md: str = "docs/ip_coverage.md",
    batch_size: int = 5000,
) -> IpCoverage:
    database_path = bin_path or settings.ip_bin_path
    if not database_path:
        raise FileNotFoundError("IP_BIN_PATH is empty")
    counts = _read_counts(counts_path)
    checkout = _read_counts(checkout_path) if Path(checkout_path).is_file() else {}
    reader = IP2Location(database_path)
    client = get_client(settings)
    coll = client[settings.mongo_db]["ip_geo"]
    now = datetime.now(timezone.utc)
    countries: Counter[str] = Counter()
    public_events = 0
    resolved_events = 0
    ops: list[UpdateOne] = []

    resolved_ips: set[str] = set()
    for ip, events in counts.items():
        status, record = _lookup(reader, ip)
        if status == "public":
            public_events += events
            if record is not None:
                resolved_events += events
                resolved_ips.add(ip)
                code = record[0]
                countries[code] += events
                fields = {
                    "status": "ok",
                    "country_code": record[0],
                    "country_name": record[1],
                    "region": record[2],
                    "city": record[3],
                }
            else:
                fields = {"status": "not_found"}
        else:
            fields = {"status": status}
        fields["events"] = events
        fields["lookup_at"] = now
        ops.append(UpdateOne({"_id": ip}, {"$set": fields}, upsert=True))
        if len(ops) >= batch_size:
            coll.bulk_write(ops, ordered=False)
            ops.clear()
    if ops:
        coll.bulk_write(ops, ordered=False)

    checkout_events = sum(checkout.values())
    checkout_resolved = sum(events for ip, events in checkout.items() if ip in resolved_ips)
    coverage = IpCoverage(
        events=sum(counts.values()),
        distinct_ips=len(counts),
        public_events=public_events,
        resolved_events=resolved_events,
        checkout_events=checkout_events,
        checkout_resolved=checkout_resolved,
        top_countries=countries.most_common(10),
    )
    Path(out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(out_md).write_text(_render(coverage, database_path), encoding="utf-8")
    return coverage


def _lookup(reader: IP2Location, ip: str) -> tuple[str, tuple[str, str, str, str] | None]:
    kind = classify_ip(ip.encode("utf-8", "replace"))
    if kind != "public":
        return kind, None
    record = reader.get_all(ip)
    if record is None:
        return "public", None
    country = _clean(getattr(record, "country_short", None))
    if not country:
        return "public", None
    return "public", (
        country,
        _clean(getattr(record, "country_long", None)) or "",
        _clean(getattr(record, "region", None)) or "",
        _clean(getattr(record, "city", None)) or "",
    )


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in _MISSING:
        return None
    return text


def _read_counts(path: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            ip, _, raw_count = line.rstrip("\n").partition("\t")
            if ip:
                counts[ip] = int(raw_count)
    return counts


def _render(coverage: IpCoverage, bin_path: str) -> str:
    lines = [
        "# IP coverage",
        "",
        f"BIN: `{bin_path}`",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Events with an IP string | {coverage.events:,} |",
        f"| Distinct IP strings | {coverage.distinct_ips:,} |",
        f"| Events with public IPv4 | {coverage.public_events:,} |",
        f"| Events whose public IPv4 resolved | {coverage.resolved_events:,} |",
        f"| Resolve rate on public IPv4 | {coverage.resolved_pct:.2f}% |",
        f"| `checkout_success` events | {coverage.checkout_events:,} |",
        f"| `checkout_success` resolved | {coverage.checkout_resolved:,} |",
        f"| `checkout_success` resolve rate | {coverage.checkout_pct:.2f}% |",
        "",
        "Private, loopback, and IPv6 addresses are stored in `ip_geo` with a status and are not sent to the BIN.",
        "Join `glamira_raw.ip` to `ip_geo._id` for `country_code` and `city`.",
        "",
        "## Top 10 country by event count",
        "",
        "| Country | Events |",
        "|---|---:|",
    ]
    for code, events in coverage.top_countries:
        lines.append(f"| `{code}` | {events:,} |")
    lines.append("")
    return "\n".join(lines)
