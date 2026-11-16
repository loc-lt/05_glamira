"""Product name and type from Glamira's product-customizer JSON.

Endpoint: https://<host>/productcustomizer/reactdata/index/id/<product_id>/
robots.txt explicitly allows /productcustomizer/reactdata/. Plain HTTP gets 403
from the CDN, so a real Chrome tab opens the JSON URL directly, exactly like typing
it in the address bar: about 0.5 s per product instead of 5-10 s for a product page.
(A fetch() issued from inside the home page was blocked by the CDN after the first
call in each tab; a top-level navigation is not.)

Progress lives in Mongo. Every product id ends with one document in `products`:
a name (done) or `not_found: true` (removed from the store). A restart skips
both, so stopping, losing the network or rebooting only costs the last batch.

Run:  uv run python -m src.enrich.reactdata --limit 0
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pymongo import UpdateOne
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from src.config import Settings
from src.db import get_client

HOSTS = ("www.glamira.co.uk", "www.glamira.com")
# Placeholder values the site uses when a product has no type (fees, test items).
BAD_TYPES = frozenset({"--_select_--", "-1", "0", ""})
CURRENCY = {"www.glamira.co.uk": "GBP"}
FLUSH_EVERY = 10
MAX_BACKOFF = 300

def extract_payload(payload: dict) -> dict:
    """Keep only the fields we store from the ~300-800 KB reactdata JSON."""
    price = payload.get("product_price") or {}
    images = (payload.get("media_image") or {}).get("images") or []
    first = images[0] if images and isinstance(images[0], dict) else {}
    return {
        "name": payload.get("name"),
        "sku": payload.get("sku"),
        "product_type": payload.get("product_type"),
        "category_name": payload.get("category_name"),
        "collection": payload.get("collection"),
        "gender": payload.get("gender"),
        "attribute_set": payload.get("attribute_set"),
        "price": price.get("price", payload.get("price")),
        "currency": price.get("currencyCode"),
        "min_price": payload.get("min_price"),
        "max_price": payload.get("max_price"),
        "image_url": first.get("large_image_url"),
        "store_code": payload.get("store_code"),
    }


def parse_response(status: int, body: bytes) -> dict:
    """Turn one HTTP answer into {status, data} or {status, error}."""
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {"status": status, "error": "not json"}
    if not isinstance(payload, dict):
        return {"status": status, "error": "not json"}
    if status != 200 or payload.get("error"):
        return {"status": status, "error": payload.get("error") or f"http {status}"}
    return {"status": status, "data": extract_payload(payload)}


@dataclass
class ReactResult:
    attempted: int = 0
    named: int = 0
    not_found: int = 0
    skipped: int = 0
    by_type: dict[str, int] = field(default_factory=dict)


def react_url(host: str, product_id: str) -> str:
    url = f"https://{host}/productcustomizer/reactdata/index/id/{product_id}/"
    currency = CURRENCY.get(host)
    return f"{url}?currency={currency}" if currency else url


def react_fields(data: dict) -> dict:
    """Normalise the JS payload. `category` is the product type (ring, necklace, ...)."""
    def text(value: object) -> str | None:
        if value is None or isinstance(value, bool):
            return None
        out = str(value).strip()
        return out or None

    product_type = text(data.get("product_type"))
    if product_type in BAD_TYPES:
        product_type = None
    return {
        "name": text(data.get("name")),
        "category": product_type or text(data.get("category_name")),
        "product_type": product_type,
        "collection": text(data.get("collection")),
        "gender": text(data.get("gender")),
        "attribute_set": text(data.get("attribute_set")),
        "sku": text(data.get("sku")),
        "price": text(data.get("price")),
        "currency": text(data.get("currency")),
        "min_price": text(data.get("min_price")),
        "max_price": text(data.get("max_price")),
        "image_url": text(data.get("image_url")),
        "store_code": text(data.get("store_code")),
    }


def is_transient(status: int, error: str | None) -> bool:
    """Retry later (network, CDN block, server error). 404 'Product not found' is final."""
    if status == 404:
        return False
    return status == 0 or status == 403 or status == 429 or status >= 500 or error == "not json"


def done_ids(products: Collection, retry_missing: bool = False, refresh_old: bool = False) -> set[str]:
    """Ids to skip. `refresh_old` re-asks products that came from the old HTML crawl
    (no `source`) or carry a placeholder category, so `category` ends up uniform."""
    done: set[str] = set()
    fields = {"_id": 1, "name": 1, "not_found": 1, "source": 1, "category": 1}
    for doc in products.find({}, fields):
        name = doc.get("name")
        if isinstance(name, str) and name.strip():
            stale = doc.get("source") != "reactdata" or doc.get("category") in BAD_TYPES
            if refresh_old and stale:
                continue
            done.add(str(doc["_id"]))
        elif doc.get("not_found") is True and not retry_missing:
            done.add(str(doc["_id"]))
    return done


def read_seed(path: str, limit: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            product_id = (record.get("product_id") or "").strip()
            if product_id:
                rows.append((product_id, (record.get("canonical_url") or "").strip()))
            if limit and len(rows) >= limit:
                break
    return rows


def found_op(product_id: str, host: str, seed_url: str, fields: dict) -> UpdateOne:
    doc = {
        "product_id": product_id,
        **fields,
        "url": react_url(host, product_id),
        "source_url": seed_url,
        "source": "reactdata",
        "host": host,
        "http_status": 200,
        "error": None,
        "not_found": False,
        "crawled_at": datetime.now(timezone.utc),
    }
    return UpdateOne({"_id": product_id}, {"$set": doc}, upsert=True)


def missing_op(product_id: str, seed_url: str, status: int, error: str | None) -> UpdateOne:
    # $set only these fields: a name found by an earlier crawl is never erased.
    doc = {
        "product_id": product_id,
        "source_url": seed_url,
        "source": "reactdata",
        "http_status": status,
        "error": error,
        "not_found": True,
        "crawled_at": datetime.now(timezone.utc),
    }
    return UpdateOne({"_id": product_id}, {"$set": doc}, upsert=True)


class _Tabs:
    """One Chrome tab per host. Each request is a top-level navigation to the JSON URL.

    `launch` starts a browser. If Chrome is closed or crashes, `reset(restart=True)`
    starts a new one; reopening tabs alone cannot work once the browser is gone.
    """

    def __init__(self, launch) -> None:
        self.launch = launch
        self.browser = launch()
        self.pages: dict[str, object] = {}

    def _alive(self) -> bool:
        try:
            return bool(self.browser.is_connected())
        except Exception:
            return False

    def get(self, host: str):
        if not self._alive():
            self.reset(restart=True)
        page = self.pages.get(host)
        if page is None:
            page = self.browser.new_page()
            self.pages[host] = page
        return page

    def reset(self, restart: bool = False) -> None:
        for page in self.pages.values():
            try:
                page.close()
            except Exception:
                pass
        self.pages.clear()
        if restart or not self._alive():
            self.close_browser()
            print("[react] restarting Chrome", flush=True)
            self.browser = self.launch()

    def close_browser(self) -> None:
        try:
            self.browser.close()
        except Exception:
            pass


def _fetch(tabs: _Tabs, host: str, product_id: str) -> dict:
    """Open the JSON URL in the host tab (like the address bar) and parse the answer."""
    try:
        page = tabs.get(host)
        response = page.goto(react_url(host, product_id), wait_until="commit", timeout=60_000)
        if response is None:
            return {"status": 0, "error": "no response"}
        return parse_response(response.status, response.body())
    except Exception as exc:  # tab or browser closed, network down
        return {"status": 0, "error": f"{type(exc).__name__}: {exc}"[:180]}


def _with_mongo_retry(label: str, action):
    """Run a Mongo read; if the VM is unreachable (firewall, tunnel down), wait and retry."""
    wait = 5
    while True:
        try:
            return action()
        except PyMongoError as exc:
            print(f"[react] mongo unreachable during {label} ({type(exc).__name__}); retry in {wait}s", flush=True)
            time.sleep(wait)
            wait = min(wait * 2, MAX_BACKOFF)


def _flush(products: Collection, ops: list[UpdateOne]) -> None:
    """Write the batch; if Mongo is unreachable, wait and retry instead of losing it."""
    wait = 5
    while ops:
        try:
            products.bulk_write(ops, ordered=False)
            ops.clear()
        except PyMongoError as exc:
            print(f"[react] mongo unreachable ({type(exc).__name__}); retry in {wait}s", flush=True)
            time.sleep(wait)
            wait = min(wait * 2, MAX_BACKOFF)


def crawl_reactdata(
    settings: Settings,
    *,
    seed_path: str = "data/exports/product_urls.csv",
    limit: int = 0,
    min_delay: float = 1.0,
    max_delay: float = 2.0,
    retry_missing: bool = False,
    refresh_old: bool = False,
    out_md: str = "docs/crawl_react.md",
    browser_factory=None,
) -> ReactResult:
    products = get_client(settings)[settings.mongo_db][settings.mongo_collection_products]
    rows = read_seed(seed_path, limit)
    finished = _with_mongo_retry("startup", lambda: done_ids(products, retry_missing, refresh_old))
    pending = [row for row in rows if row[0] not in finished]
    result = ReactResult(skipped=len(rows) - len(pending))
    print(f"[react] seed={len(rows)} already done={result.skipped} pending={len(pending)}", flush=True)
    ops: list[UpdateOne] = []
    started = time.perf_counter()

    # Adaptive politeness: slow down after CDN/network trouble, speed back up after a calm stretch.
    slow = {"factor": 1.0, "calm": 0}

    def pause() -> None:
        time.sleep(random.uniform(min_delay, max_delay) * slow["factor"])

    def calm() -> None:
        slow["calm"] += 1
        if slow["calm"] >= 50 and slow["factor"] > 1.0:
            slow["factor"] = max(1.0, slow["factor"] / 1.5)
            slow["calm"] = 0
            print(f"[react] calm again, delay x{slow['factor']:.1f}", flush=True)

    def trouble() -> None:
        slow["calm"] = 0
        if slow["factor"] < 4.0:
            slow["factor"] = min(4.0, slow["factor"] * 1.5)
            print(f"[react] slowing down, delay x{slow['factor']:.1f}", flush=True)

    playwright = None
    if browser_factory is None:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()

        def browser_factory():
            return playwright.chromium.launch(executable_path=_chrome_path(), headless=False)

    tabs = _Tabs(browser_factory)
    try:
        for index, (product_id, seed_url) in enumerate(pending, start=1):
            outcome = None
            backoff = 5
            failures = 0
            while outcome is None:
                last = {"status": 0, "error": None}
                transient = False
                for host in HOSTS:
                    pause()
                    reply = _fetch(tabs, host, product_id)
                    last = reply
                    if reply.get("data") and reply["data"].get("name"):
                        outcome = ("found", host, react_fields(reply["data"]))
                        break
                    if is_transient(int(reply.get("status") or 0), reply.get("error")):
                        transient = True
                        break
                if outcome is None and not transient:
                    outcome = ("missing", int(last.get("status") or 404), last.get("error"))
                if outcome is None:
                    print(
                        f"[react] {product_id} transient status={last.get('status')} "
                        f"err={last.get('error')}; retry {failures + 1} in {backoff}s",
                        flush=True,
                    )
                    failures += 1
                    closed = "closed" in str(last.get("error") or "").lower()
                    # Escalate step by step: a single blip is just retried in the same tab.
                    # Reloading the home page is heavy and draws more CDN attention, so only
                    # reopen tabs on the 2nd failure and restart Chrome from the 3rd (or if it died).
                    if failures >= 2:
                        trouble()
                    if closed or failures >= 2:
                        try:
                            tabs.reset(restart=closed or failures >= 3)
                        except Exception as exc:  # Chrome could not start; wait and try again
                            print(f"[react] could not restart Chrome: {type(exc).__name__}: {exc}"[:200], flush=True)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
            result.attempted += 1
            if failures == 0:
                calm()
            if outcome[0] == "found":
                _, host, fields = outcome
                ops.append(found_op(product_id, host, seed_url, fields))
                result.named += 1
                kind = fields.get("category") or "?"
                result.by_type[kind] = result.by_type.get(kind, 0) + 1
                print(f"[react] {index}/{len(pending)} {product_id} {kind} | {fields['name']}", flush=True)
            else:
                _, status, error = outcome
                ops.append(missing_op(product_id, seed_url, status, error))
                result.not_found += 1
                print(f"[react] {index}/{len(pending)} {product_id} not found ({status})", flush=True)
            if len(ops) >= FLUSH_EVERY:
                _flush(products, ops)
                rate = result.attempted / max(time.perf_counter() - started, 1e-9)
                left = (len(pending) - index) / rate if rate else 0
                print(
                    f"[react] saved: named={result.named} not_found={result.not_found} "
                    f"rate={rate * 3600:,.0f}/h eta={left / 3600:.1f}h",
                    flush=True,
                )
    except KeyboardInterrupt:
        print("[react] interrupted; saving what is already fetched", flush=True)
    finally:
        _flush(products, ops)
        for page in tabs.pages.values():
            try:
                page.close()
            except Exception:
                pass
        tabs.close_browser()
        if playwright is not None:
            playwright.stop()
        seconds = time.perf_counter() - started
        _with_mongo_retry("report", lambda: _write_report(out_md, products, result, seconds))
    return result


def _write_report(path: str, products: Collection, run: ReactResult, seconds: float) -> None:
    named = products.count_documents({"name": {"$type": "string", "$ne": ""}})
    missing = products.count_documents({"not_found": True, "name": {"$in": [None, ""]}})
    total = products.count_documents({})
    lines = [
        "# Product crawl — reactdata JSON",
        "",
        "Source: `https://www.glamira.co.uk/productcustomizer/reactdata/index/id/<id>/?currency=GBP`,",
        "then `www.glamira.com` for ids missing on co.uk. Allowed by robots.txt.",
        "",
        "| This run | Value |",
        "|---|---:|",
        f"| Attempted | {run.attempted:,} |",
        f"| Named | {run.named:,} |",
        f"| Not found on any store | {run.not_found:,} |",
        f"| Skipped (already done) | {run.skipped:,} |",
        f"| Minutes | {seconds / 60:,.1f} |",
        "",
        "| Collection `products` | Value |",
        "|---|---:|",
        f"| Documents | {total:,} |",
        f"| With a name | {named:,} |",
        f"| Not found (removed from the store) | {missing:,} |",
        "",
        "| Category (`product_type`), whole collection | Products |",
        "|---|---:|",
    ]
    by_category = products.aggregate([
        {"$match": {"name": {"$type": "string", "$ne": ""}}},
        {"$group": {"_id": "$category", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ])
    for row in by_category:
        lines.append(f"| `{row['_id'] or '?'}` | {row['n']:,} |")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _chrome_path() -> str:
    for candidate in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium"):
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("google-chrome not found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.enrich.reactdata")
    parser.add_argument("--seed", default="data/exports/product_urls.csv")
    parser.add_argument("--limit", type=int, default=0, help="First N seed rows. 0 reads the whole seed.")
    parser.add_argument("--min-delay", type=float, default=1.0, help="Seconds between requests (random).")
    parser.add_argument("--max-delay", type=float, default=2.0)
    parser.add_argument("--retry-missing", action="store_true", help="Ask again for ids marked not_found.")
    parser.add_argument("--refresh-old", action="store_true",
                        help="Re-ask products from the old HTML crawl or with a placeholder category.")
    parser.add_argument("--out", default="docs/crawl_react.md")
    parser.add_argument("--report-only", action="store_true",
                        help="Rewrite the report from Mongo only: no Chrome, no requests to the site.")
    args = parser.parse_args(argv)
    if args.report_only:
        settings = Settings.from_env()
        products = get_client(settings)[settings.mongo_db][settings.mongo_collection_products]
        _with_mongo_retry("report", lambda: _write_report(args.out, products, ReactResult(), 0.0))
        print(f"wrote {args.out}")
        return 0
    result = crawl_reactdata(
        Settings.from_env(),
        seed_path=args.seed,
        limit=args.limit,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        retry_missing=args.retry_missing,
        refresh_old=args.refresh_old,
        out_md=args.out,
    )
    print(
        f"attempted={result.attempted} named={result.named} not_found={result.not_found} "
        f"skipped={result.skipped} wrote {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
