"""Stream summary.bson into `glamira_raw`.

The source ObjectId is the Mongo `_id`, so a second run does not duplicate rows.
Each inserted event also gets `_loaded_at` and `_source_file` (coach step 1.3).
The same pass records IP frequencies. Product URLs are a later step
(`enrich extract-products`), not part of the load.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from bson import decode as decode_bson
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError

from src.config import Settings
from src.db import get_client
from src.stream.tar_bson import SummaryDump

_MIN_FREE_BYTES = 8 * 1024 * 1024 * 1024


@dataclass
class LoadResult:
    docs_scanned: int
    inserted: int
    duplicates: int
    completed_member: bool
    mongo_count: int
    elapsed_seconds: float
    stopped_for_disk: bool
    ip_count_path: str
    distinct_ips: int

    @property
    def count_matches(self) -> bool:
        """True when the whole member was read and Mongo holds every scanned event."""
        return self.completed_member and self.mongo_count == self.docs_scanned


@dataclass
class _Sidecar:
    ip_counts: dict[str, int] = field(default_factory=dict)
    checkout_ips: dict[str, int] = field(default_factory=dict)


def load_tar(
    path: str,
    settings: Settings,
    *,
    batch_size: int | None = None,
    limit: int = 0,
    progress_every: int = 100_000,
    database: str | None = None,
    collection: str | None = None,
    write_sidecars: bool = True,
    ip_count_path: str = "data/staging/ip_event_counts.tsv",
) -> LoadResult:
    client = get_client(settings)
    client.admin.command("ping")
    db_name = database or settings.mongo_db
    coll_name = collection or settings.mongo_collection_raw
    coll = client[db_name][coll_name]
    batch_size = batch_size or settings.ingest_batch_size
    started = time.perf_counter()
    sidecar = _Sidecar()
    batch: list[dict] = []
    scanned = 0
    inserted = 0
    duplicates = 0
    stopped_for_disk = False
    dump = SummaryDump(path)
    loaded_at = datetime.now(timezone.utc)
    source_file = Path(path).name

    for raw in dump:
        document = stamp(decode_bson(raw), loaded_at, source_file)
        _observe(document, sidecar)
        batch.append(document)
        scanned += 1
        if len(batch) >= batch_size:
            added, dup = _flush(coll, batch)
            inserted += added
            duplicates += dup
            batch.clear()
            if progress_every and scanned % progress_every == 0:
                _log(scanned, inserted, duplicates, started)
            if _disk_is_low(ip_count_path):
                stopped_for_disk = True
                break
        if limit and scanned >= limit:
            break
    if batch and not stopped_for_disk:
        added, dup = _flush(coll, batch)
        inserted += added
        duplicates += dup

    completed = dump.completed and not stopped_for_disk and limit == 0
    if write_sidecars and completed:
        _write_ip_counts(ip_count_path, sidecar.ip_counts)
        checkout_path = str(Path(ip_count_path).with_name("checkout_success_ips.tsv"))
        _write_ip_counts(checkout_path, sidecar.checkout_ips)
        _ensure_indexes(coll)
    mongo_count = coll.count_documents({}) if (completed or limit or stopped_for_disk) else coll.estimated_document_count()
    return LoadResult(
        docs_scanned=scanned,
        inserted=inserted,
        duplicates=duplicates,
        completed_member=completed,
        mongo_count=mongo_count,
        elapsed_seconds=time.perf_counter() - started,
        stopped_for_disk=stopped_for_disk,
        ip_count_path=ip_count_path if completed else "",
        distinct_ips=len(sidecar.ip_counts),
    )


def stamp(document: dict, loaded_at: datetime, source_file: str) -> dict:
    """Add the two load-audit fields. Source fields are never overwritten."""
    document.setdefault("_loaded_at", loaded_at)
    document.setdefault("_source_file", source_file)
    return document


def _observe(document: dict, sidecar: _Sidecar) -> None:
    ip = document.get("ip")
    if isinstance(ip, str) and ip:
        sidecar.ip_counts[ip] = sidecar.ip_counts.get(ip, 0) + 1
        if document.get("collection") == "checkout_success":
            sidecar.checkout_ips[ip] = sidecar.checkout_ips.get(ip, 0) + 1


def _flush(collection: Collection, batch: list[dict]) -> tuple[int, int]:
    try:
        result = collection.insert_many(batch, ordered=False)
    except BulkWriteError as exc:
        details = exc.details or {}
        errors = details.get("writeErrors") or []
        other = [item for item in errors if item.get("code") != 11000]
        if other:
            sample = other[0]
            raise RuntimeError(
                f"mongo write failed code={sample.get('code')} message={sample.get('errmsg')}"
            ) from exc
        inserted = int(details.get("nInserted") or 0)
        return inserted, len(errors)
    return len(result.inserted_ids), 0


def _ensure_indexes(collection: Collection) -> None:
    collection.create_index("collection")
    collection.create_index("time_stamp")
    collection.create_index("ip")
    collection.create_index("product_id", sparse=True)
    collection.create_index("viewing_product_id", sparse=True)


def _disk_is_low(anchor: str) -> bool:
    path = Path(anchor).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path.parent).free
    if free < _MIN_FREE_BYTES:
        print(f"[load] stop: only {free / 1024**3:.1f} GiB free", flush=True)
        return True
    return False


def _write_ip_counts(path: str, counts: dict[str, int]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for ip, count in counts.items():
            handle.write(f"{ip}\t{count}\n")


def _log(scanned: int, inserted: int, duplicates: int, started: float) -> None:
    elapsed = time.perf_counter() - started
    rate = scanned / elapsed if elapsed else 0
    print(
        f"[load] scanned={scanned:,} inserted={inserted:,} dup={duplicates:,} "
        f"rate={rate:,.0f}/s elapsed={elapsed:,.0f}s",
        flush=True,
    )


def iter_decoded(path: str, limit: int = 0) -> Iterable[dict]:
    seen = 0
    for raw in SummaryDump(path):
        yield decode_bson(raw)
        seen += 1
        if limit and seen >= limit:
            break
