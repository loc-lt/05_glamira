"""Build one canonical product URL per product id from the coach's event list.

A pair is kept only when the URL is a product `.html` page for that same id.
Recommendation widgets store the recommended id beside the page the shopper
is already viewing, so those URLs are not attached to `viewing_product_id`.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pymongo.collection import Collection

from src.enrich.urls import canonical_product_url, normalize_product_id, page_rank, product_page_url

# These events carry product_id together with the product page in current_url.
_PAGE_EVENTS = (
    "view_product_detail",
    "select_product_option",
    "select_product_option_quality",
    "add_to_cart_action",
)
# current_url is a recommendation list. The product page is referrer_url.
_REFERRER_EVENTS = ("back_to_product_action",)
# Listed by the coach. The sample documents do not contain that product's page.
_UNPAIRED_EVENTS = (
    "product_detail_recommendation_visible",
    "product_detail_recommendation_noticed",
    "view_all_recommend",
    "product_view_all_recommend_clicked",
)
COACH_EVENTS = _PAGE_EVENTS + _REFERRER_EVENTS + _UNPAIRED_EVENTS

_FIELDS = {
    "collection": 1,
    "product_id": 1,
    "viewing_product_id": 1,
    "current_url": 1,
    "referrer_url": 1,
}


@dataclass
class ExtractResult:
    products: int
    scanned: int
    kept: int
    by_event: dict[str, tuple[int, int]] = field(default_factory=dict)
    path: str = ""


def extract_products(
    raw: Collection,
    *,
    base_url: str,
    per_event: int = 0,
    out_csv: str = "data/exports/product_urls.csv",
) -> ExtractResult:
    """One row per product id. `per_event` 0 reads every document of that event."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    seen_on: dict[tuple[str, str], str] = {}
    scanned: Counter[str] = Counter()
    kept: Counter[str] = Counter()
    for event in COACH_EVENTS:
        cursor = raw.find({"collection": event}, _FIELDS)
        if per_event > 0:
            cursor = cursor.limit(per_event)
        for document in cursor:
            scanned[event] += 1
            if scanned[event] % 1_000_000 == 0:
                print(f"[extract] {event} {scanned[event]}", flush=True)
            pair = _observed_page(event, document)
            if pair is None:
                continue
            product_id, url = pair
            kept[event] += 1
            counts[product_id][url] += 1
            seen_on.setdefault((product_id, url), event)
        print(f"[extract] {event} done scanned={scanned[event]} kept={kept[event]}", flush=True)
    chosen = {
        product_id: _choose(product_id, counter, seen_on, base_url)
        for product_id, counter in counts.items()
    }
    path = _write_csv(out_csv, chosen)
    return ExtractResult(
        products=len(chosen),
        scanned=sum(scanned.values()),
        kept=sum(kept.values()),
        by_event={event: (scanned[event], kept[event]) for event in COACH_EVENTS},
        path=path,
    )


def pair_from_document(event: str, document: dict, base_url: str) -> tuple[str, str] | None:
    """Return `(product_id, canonical_url)` when both describe the same page."""
    observed = _observed_page(event, document)
    if observed is None:
        return None
    product_id, page = observed
    url = canonical_product_url(page, base_url)
    if url is None:
        return None
    return product_id, url


def _observed_page(event: str, document: dict) -> tuple[str, str] | None:
    """Return `(product_id, page)` using the store host stored in the event."""
    if event in _UNPAIRED_EVENTS:
        return None
    product_id = normalize_product_id(document.get("product_id"))
    if not product_id:
        return None
    current = _page(document.get("current_url"))
    referrer = _page(document.get("referrer_url"))
    if event in _REFERRER_EVENTS:
        url = referrer or current
    else:
        url = current or referrer
    if url is None:
        return None
    return product_id, url


def _choose(
    product_id: str,
    counter: Counter[str],
    seen_on: dict[tuple[str, str], str],
    base_url: str,
) -> tuple[str, str]:
    """Keep the best real page. The view count breaks a tie between equal ranks."""
    best = max(counter, key=lambda url: (page_rank(url), counter[url]))
    chosen = canonical_product_url(best, base_url)
    if chosen is None:
        chosen = best
    return chosen, seen_on[(product_id, best)]


def _page(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return product_page_url(value)


def _write_csv(path: str, chosen: dict[str, tuple[str, str]]) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_id", "canonical_url", "source_event"])
        for product_id in sorted(chosen):
            url, event = chosen[product_id]
            writer.writerow([product_id, url, event])
    return str(destination)
