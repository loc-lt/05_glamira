"""CSV copies of the enrichment collections, and the crawl completeness check.

The coach asks for a CSV beside every Mongo collection, and for `products` to hold
exactly one document per id in the seed.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.config import Settings
from src.db import get_client

COLUMNS: dict[str, tuple[str, ...]] = {
    "ip_geo": ("_id", "status", "country_code", "country_name", "region", "city", "events"),
    "products": (
        "_id",
        "name",
        "category",
        "price",
        "currency",
        "material",
        "image_url",
        "url",
        "source_url",
        "http_status",
        "error",
        "crawled_at",
    ),
}


@dataclass
class ProductStatus:
    seed: int
    documents: int
    named: int
    missing: int

    @property
    def named_pct(self) -> float:
        return 100.0 * self.named / self.seed if self.seed else 0.0


def write_rows(path: str, columns: tuple[str, ...], documents: Iterable[dict]) -> int:
    """Write one CSV row per document. Missing fields become empty cells."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for document in documents:
            writer.writerow([_cell(document.get(column)) for column in columns])
            rows += 1
    return rows


def export_collection(settings: Settings, name: str, out_csv: str) -> int:
    columns = COLUMNS[name]
    collection = get_client(settings)[settings.mongo_db][name]
    cursor = collection.find({}, {column: 1 for column in columns}).sort("_id", 1)
    return write_rows(out_csv, columns, cursor)


def seed_ids(path: str) -> set[str]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return {
            (row.get("product_id") or "").strip()
            for row in csv.DictReader(handle)
            if (row.get("product_id") or "").strip()
        }


def product_status(settings: Settings, seed_path: str) -> ProductStatus:
    wanted = seed_ids(seed_path)
    collection = get_client(settings)[settings.mongo_db][settings.mongo_collection_products]
    present: set[str] = set()
    named = 0
    for document in collection.find({}, {"_id": 1, "name": 1}):
        product_id = str(document["_id"])
        if product_id not in wanted:
            continue
        present.add(product_id)
        name = document.get("name")
        if isinstance(name, str) and name.strip():
            named += 1
    return ProductStatus(
        seed=len(wanted),
        documents=len(present),
        named=named,
        missing=len(wanted - present),
    )


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
