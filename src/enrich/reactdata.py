"""Product name and type from Glamira's product-customizer JSON.

Endpoint: https://<host>/productcustomizer/reactdata/index/id/<product_id>/
robots.txt explicitly allows /productcustomizer/reactdata/. Plain HTTP gets 403
from the CDN, so each request is a fetch() inside one real Chrome tab per host:
no HTML rendering, about 0.5 s per product instead of 5-10 s for a product page.

Progress lives in Mongo. Every product id ends with one document in `products`:
a name (done) or `not_found: true` (removed from the store). A restart skips
both, so stopping, losing the network or rebooting only costs the last batch.

Run:  uv run python -m src.enrich.reactdata --limit 0
"""

from __future__ import annotations

import argparse
import csv
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
CURRENCY = {"www.glamira.co.uk": "GBP"}
FLUSH_EVERY = 10
MAX_BACKOFF = 300

# Runs inside the Chrome tab. Returns only the fields we keep, not the ~800 KB JSON.
_FETCH_JS = """async (url) => {
  let r;
  try { r = await fetch(url, {credentials: 'include', headers: {'Accept': 'application/json'}}); }
  catch (e) { return {status: 0, error: String(e).slice(0, 180)}; }
  const text = await r.text();
  let j = null;
  try { j = JSON.parse(text); } catch (e) { return {status: r.status, error: 'not json'}; }
  if (!r.ok || !j || j.error) return {status: r.status, error: (j && j.error) || ('http ' + r.status)};
  const pp = j.product_price || {};
  const images = (j.media_image || {}).images || [];
  return {status: r.status, data: {
    name: j.name, sku: j.sku, product_type: j.product_type, category_name: j.category_name,
    collection: j.collection, gender: j.gender, attribute_set: j.attribute_set,
    price: (pp.price !== undefined ? pp.price : j.price), currency: pp.currencyCode,
    min_price: j.min_price, max_price: j.max_price,
    image_url: images.length ? images[0].large_image_url : null, store_code: j.store_code}};
}"""


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


def done_ids(products: Collection, retry_missing: bool = False) -> set[str]:
    query: dict = {"name": {"$type": "string", "$ne": ""}}
    if not retry_missing:
        query = {"$or": [query, {"not_found": True}]}
    return {str(doc["_id"]) for doc in products.find(query, {"_id": 1})}


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
    """One Chrome tab per host, opened on the host home page so the CDN cookies exist."""

    def __init__(self, browser) -> None:
        self.browser = browser
        self.pages: dict[str, object] = {}

    def get(self, host: str):
        page = self.pages.get(host)
        if page is None:
            page = self.browser.new_page()
            page.goto(f"https://{host}/", wait_until="domcontentloaded", timeout=60_000)
            self.pages[host] = page
        return page

    def reset(self) -> None:
        for page in self.pages.values():
            try:
                page.close()
            except Exception:
                pass
        self.pages.clear()


def _fetch(tabs: _Tabs, host: str, product_id: str) -> dict:
    try:
        page = tabs.get(host)
        return page.evaluate(_FETCH_JS, react_url(host, product_id))
    except Exception as exc:  # tab crashed, navigation, network down while opening the home page
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
    out_md: str = "docs/crawl_react.md",
    browser_factory=None,
) -> ReactResult:
    products = get_client(settings)[settings.mongo_db][settings.mongo_collection_products]
    rows = read_seed(seed_path, limit)
    finished = _with_mongo_retry("startup", lambda: done_ids(products, retry_missing))
    pending = [row for row in rows if row[0] not in finished]
    result = ReactResult(skipped=len(rows) - len(pending))
    print(f"[react] seed={len(rows)} already done={result.skipped} pending={len(pending)}", flush=True)
    ops: list[UpdateOne] = []
    started = time.perf_counter()

    def pause() -> None:
        time.sleep(random.uniform(min_delay, max_delay))

    playwright = None
    browser = None
    if browser_factory is None:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(executable_path=_chrome_path(), headless=False)
    else:
        browser = browser_factory()
    tabs = _Tabs(browser)
    try:
        for index, (product_id, seed_url) in enumerate(pending, start=1):
            outcome = None
            backoff = 5
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
                        f"err={last.get('error')}; reopen tabs, retry in {backoff}s",
                        flush=True,
                    )
                    tabs.reset()
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
            result.attempted += 1
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
        tabs.reset()
        try:
            browser.close()
        except Exception:
            pass
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
        "| Category (`product_type`) this run | Products |",
        "|---|---:|",
    ]
    for kind, count in sorted(run.by_type.items(), key=lambda item: -item[1]):
        lines.append(f"| `{kind}` | {count:,} |")
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
    parser.add_argument("--out", default="docs/crawl_react.md")
    args = parser.parse_args(argv)
    result = crawl_reactdata(
        Settings.from_env(),
        seed_path=args.seed,
        limit=args.limit,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        retry_missing=args.retry_missing,
        out_md=args.out,
    )
    print(
        f"attempted={result.attempted} named={result.named} not_found={result.not_found} "
        f"skipped={result.skipped} wrote {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
