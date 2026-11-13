"""Fetch a small number of canonical product pages and store name plus category.

Opens the installed Google Chrome through Playwright, one page at a time.
The pilot stops at `--limit` (100 for the acceptance run).
"""

from __future__ import annotations

import csv
import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, Page, Playwright, sync_playwright
from pymongo import UpdateOne
from pymongo.collection import Collection

from src.config import Settings
from src.db import get_client
from src.enrich.urls import crawl_url_chain

_CHROME_CANDIDATES = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)
_BLOCKED_NAMES = frozenset({"access denied", "forbidden", "just a moment", "oops", "oops!"})
_FLUSH_EVERY = 10
_COM_ATTEMPTS = 3
_UK_ATTEMPTS = 2


@dataclass
class CrawlResult:
    attempted: int
    http_200: int
    parsed: int
    elapsed_seconds: float
    failed_com: int = 0
    failed_uk: int = 0

    @property
    def parse_rate(self) -> float:
        if self.attempted == 0:
            return 0.0
        return 100.0 * self.parsed / self.attempted


@dataclass(frozen=True)
class ProductPage:
    name: str | None = None
    category: str | None = None
    price: str | None = None
    currency: str | None = None
    description: str | None = None
    image_url: str | None = None
    brand: str | None = None
    sku: str | None = None
    material: str | None = None
    color: str | None = None
    availability: str | None = None
    gtin: str | None = None
    mpn: str | None = None
    weight: str | None = None


def parse_product_html(html: str) -> ProductPage:
    """Read the product fields from JSON-LD, then h1 and breadcrumbs."""
    soup = BeautifulSoup(html, "html.parser")
    page = _from_json_ld(soup)
    name = page.name
    category = page.category
    if not name:
        heading = soup.select_one("h1")
        if heading is not None:
            name = heading.get_text(" ", strip=True) or None
    if not category:
        crumbs = [
            node.get_text(" ", strip=True)
            for node in soup.select(".breadcrumbs a, nav[aria-label='Breadcrumb'] a, .breadcrumb a")
        ]
        crumbs = [item for item in crumbs if item and item.lower() not in {"home", "glamira"}]
        category = crumbs[-1] if crumbs else None
    return ProductPage(
        name=name,
        category=category,
        price=page.price,
        currency=page.currency,
        description=page.description,
        image_url=page.image_url,
        brand=page.brand,
        sku=page.sku,
        material=page.material,
        color=page.color,
        availability=page.availability,
        gtin=page.gtin,
        mpn=page.mpn,
        weight=page.weight,
    )


def crawl_seed(
    settings: Settings,
    *,
    seed_path: str = "data/exports/product_urls.csv",
    limit: int = 100,
    out_md: str = "docs/crawl_pilot.md",
    failed_com_path: str = "data/exports/product_failed_com.csv",
    failed_uk_path: str = "data/exports/product_failed_couk.csv",
) -> CrawlResult:
    """One Chrome tab. Seed URL, then .com catalog (2–3 tries), then .co.uk for leftovers."""
    rows = _read_seed(seed_path, limit)
    client = get_client(settings)
    catalog = client[settings.mongo_db][settings.mongo_collection_products]
    named = _named_ids(catalog)
    pending = [row for row in rows if row[0] not in named]
    delay = 1.0 / settings.crawl_rate_limit_per_sec if settings.crawl_rate_limit_per_sec else 0.0
    started = time.perf_counter()
    http_200 = 0
    parsed = 0
    failed_com: list[tuple[str, str]] = []
    failed_uk: list[tuple[str, str]] = []
    lines = [
        "# Crawl pilot",
        "",
        f"Limit: {limit}. Rate: {settings.crawl_rate_limit_per_sec} request/s.",
        f"Skipped {len(rows) - len(pending)} products that already have a name.",
        "Order: current_url, then www.glamira.com/catalog/product/view/id/<id> "
        f"({_COM_ATTEMPTS} tries), then www.glamira.co.uk for leftovers.",
        "",
        "| product_id | status | name | category | price | url |",
        "|---|---:|---|---|---|---|",
    ]
    probe = _probe_http(pending[0][1], settings.crawl_user_agent) if pending else None
    lines.insert(3, f"HTTP GET probe: {probe if probe is not None else 'not run'}.")
    ops: list[UpdateOne] = []
    playwright = sync_playwright().start()
    browser: Browser | None = None

    def pause() -> None:
        time.sleep(random.uniform(1.5, 4.2) if delay else 0.0)

    def record(
        product_id: str,
        source_url: str,
        fetched_url: str,
        status: int,
        parsed_page: ProductPage,
        error: str | None,
        *,
        count_http: bool,
    ) -> None:
        nonlocal http_200, parsed
        if count_http and status == 200:
            http_200 += 1
        if parsed_page.name:
            parsed += 1
        lines.append(
            f"| `{product_id}` | {status} | {_cell(parsed_page.name)} | "
            f"{_cell(parsed_page.category)} | {_cell(parsed_page.price)} | `{fetched_url}` |"
        )
        ops.append(_catalog_op(product_id, fetched_url, source_url, parsed_page, status, error))
        if len(ops) >= _FLUSH_EVERY:
            _flush_catalog(catalog, ops)
            ops.clear()
            _write_report(out_md, lines, len(pending), http_200, parsed, finished=False)
            print(f"[crawl] saved parsed={parsed} failed_com={len(failed_com)}", flush=True)

    try:
        browser = _launch_chrome(playwright)
        page = browser.new_page()
        print(f"[crawl] pending {len(pending)}", flush=True)
        for index, (product_id, seed_url) in enumerate(pending):
            _seed, com_url, uk_url = crawl_url_chain(product_id, seed_url)
            if index:
                pause()
            page, status, parsed_page, error = _fetch_attempts(browser, page, seed_url, attempts=1)
            fetched_url = seed_url
            if not _usable(parsed_page):
                page, status, parsed_page, error = _fetch_attempts(
                    browser, page, com_url, attempts=_COM_ATTEMPTS, pause=pause
                )
                fetched_url = com_url
            if _usable(parsed_page):
                record(product_id, seed_url, fetched_url, status, parsed_page, error, count_http=True)
            else:
                failed_com.append((product_id, seed_url))
                record(
                    product_id,
                    seed_url,
                    fetched_url,
                    status,
                    parsed_page,
                    error or "failed_com",
                    count_http=True,
                )
            print(
                f"[crawl] {index + 1}/{len(pending)} {product_id} "
                f"status={status} name={parsed_page.name or ''} url={fetched_url} err={error or ''}",
                flush=True,
            )
        print(f"[crawl] .com leftovers {len(failed_com)} → .co.uk", flush=True)
        for index, (product_id, seed_url) in enumerate(failed_com):
            _seed, _com, uk_url = crawl_url_chain(product_id, seed_url)
            pause()
            page, status, parsed_page, error = _fetch_attempts(
                browser, page, uk_url, attempts=_UK_ATTEMPTS, pause=pause
            )
            if _usable(parsed_page):
                record(product_id, seed_url, uk_url, status, parsed_page, error, count_http=True)
            else:
                failed_uk.append((product_id, uk_url))
                record(
                    product_id,
                    seed_url,
                    uk_url,
                    status,
                    parsed_page,
                    error or "failed_uk",
                    count_http=True,
                )
            print(
                f"[crawl] uk {index + 1}/{len(failed_com)} {product_id} "
                f"status={status} name={parsed_page.name or ''} url={uk_url} err={error or ''}",
                flush=True,
            )
    except KeyboardInterrupt:
        print("[crawl] interrupted; saving pages already fetched", flush=True)
    finally:
        _flush_catalog(catalog, ops)
        ops.clear()
        if browser is not None:
            browser.close()
        playwright.stop()
        _write_id_list(failed_com_path, failed_com)
        _write_id_list(failed_uk_path, failed_uk)
        _write_report(out_md, lines, len(pending), http_200, parsed, finished=True)
    elapsed = time.perf_counter() - started
    return CrawlResult(
        attempted=len(pending),
        http_200=http_200,
        parsed=parsed,
        elapsed_seconds=elapsed,
        failed_com=len(failed_com),
        failed_uk=len(failed_uk),
    )


def _named_ids(catalog: Collection) -> set[str]:
    found: set[str] = set()
    for doc in catalog.find({"name": {"$type": "string"}}, {"_id": 1, "name": 1}):
        name = doc.get("name")
        if isinstance(name, str) and name.strip():
            found.add(str(doc["_id"]))
    return found


def _usable(parsed_page: ProductPage) -> bool:
    return bool(parsed_page.name)


def _fetch_attempts(
    browser: Browser,
    page: Page,
    url: str,
    *,
    attempts: int,
    pause: object = None,
) -> tuple[Page, int, ProductPage, str | None]:
    status, parsed_page, error = 0, ProductPage(), None
    for try_no in range(attempts):
        if try_no and callable(pause):
            pause()
        status, parsed_page, error = _fetch_one(page, url)
        if status == 0:
            page = _replace_page(browser, page)
            time.sleep(2)
            status, parsed_page, error = _fetch_one(page, url)
        if _usable(parsed_page):
            return page, status, parsed_page, error
    return page, status, parsed_page, error


def _write_id_list(path: str, rows: list[tuple[str, str]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_id", "url"])
        writer.writerows(rows)


def _catalog_op(
    product_id: str,
    url: str,
    source_url: str,
    parsed_page: ProductPage,
    status: int,
    error: str | None,
) -> UpdateOne:
    return UpdateOne(
        {"_id": product_id},
        {
            "$set": {
                "product_id": product_id,
                "url": url,
                "source_url": source_url,
                "name": parsed_page.name,
                "category": parsed_page.category,
                "price": parsed_page.price,
                "currency": parsed_page.currency,
                "description": parsed_page.description,
                "image_url": parsed_page.image_url,
                "brand": parsed_page.brand,
                "sku": parsed_page.sku,
                "material": parsed_page.material,
                "color": parsed_page.color,
                "availability": parsed_page.availability,
                "gtin": parsed_page.gtin,
                "mpn": parsed_page.mpn,
                "weight": parsed_page.weight,
                "http_status": status,
                "error": error,
                "crawled_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


def _flush_catalog(catalog: Collection, ops: list[UpdateOne]) -> None:
    if ops:
        catalog.bulk_write(ops, ordered=False)


def _write_report(
    path: str,
    lines: list[str],
    attempted: int,
    http_200: int,
    parsed: int,
    *,
    finished: bool,
) -> None:
    rate = 100.0 * parsed / attempted if attempted else 0.0
    body = list(lines)
    body.extend(
        [
            "",
            f"Attempted {attempted}. HTTP 200: {http_200}. Name parsed: {parsed} ({rate:.2f}%).",
            "",
            "Client: installed Google Chrome via Playwright, one page at a time.",
            "Mongo writes every 10 pages, including when the run stops early.",
            "",
        ]
    )
    if not finished:
        body.append("Run still in progress.")
        body.append("")
    Path(path).write_text("\n".join(body), encoding="utf-8")


def _chrome_path() -> str:
    override = os.environ.get("CHROME_PATH", "").strip()
    candidates = (override, *_CHROME_CANDIDATES) if override else _CHROME_CANDIDATES
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("google-chrome not found. Set CHROME_PATH to the Chrome binary.")


def _launch_chrome(playwright: Playwright) -> Browser:
    return playwright.chromium.launch(
        executable_path=_chrome_path(),
        headless=False,
    )


def _replace_page(browser: Browser, page: Page) -> Page:
    """Open a new tab after a dropped connection so the next try is not stuck on it."""
    try:
        page.close()
    except Exception:
        pass
    return browser.new_page()


def _cell(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("|", "/")


_CATALOG_READY = """() => {
  const title = document.title || '';
  return title.includes('GLAMIRA') && !title.startsWith('404');
}"""
_CATALOG_PRODUCT = """() => [...document.querySelectorAll("script[type='application/ld+json']")]
  .some(node => (node.textContent || '').includes('Product'));"""


def _fetch_one(page: Page, url: str) -> tuple[int, ProductPage, str | None]:
    empty = ProductPage()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:
        return 0, empty, f"{type(exc).__name__}: {exc}"[:180]
    if "/catalog/product/view/" in url:
        try:
            page.wait_for_function(_CATALOG_READY, timeout=20_000)
            page.wait_for_function(_CATALOG_PRODUCT, timeout=10_000)
        except Exception:
            pass
    status = response.status if response is not None else 0
    if status != 200:
        return status, empty, None
    parsed_page = parse_product_html(page.content())
    if parsed_page.name is not None and parsed_page.name.casefold() in _BLOCKED_NAMES:
        return status, empty, "blocked"
    return status, parsed_page, None


def _probe_http(url: str, user_agent: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except urllib.error.URLError:
        return 0


def _from_json_ld(soup: BeautifulSoup) -> ProductPage:
    for node in soup.select("script[type='application/ld+json']"):
        try:
            payload = json.loads(node.get_text())
        except json.JSONDecodeError:
            continue
        for item in _walk_ld(payload):
            kind = item.get("@type")
            types = kind if isinstance(kind, list) else [kind]
            if "Product" not in types:
                continue
            category = item.get("category")
            if isinstance(category, list):
                category = category[-1] if category else None
            if isinstance(category, dict):
                category = category.get("name")
            offers = item.get("offers")
            return ProductPage(
                name=_text(item.get("name")),
                category=_text(category),
                price=_price(offers),
                currency=_offer_text(offers, "priceCurrency"),
                description=_text(item.get("description")),
                image_url=_image(item.get("image")),
                brand=_brand(item.get("brand")),
                sku=_text(item.get("sku")),
                material=_text(item.get("material")),
                color=_text(item.get("color")),
                availability=_availability(offers),
                gtin=_text(item.get("gtin")),
                mpn=_text(item.get("mpn")),
                weight=_weight(item.get("weight")),
            )
    return ProductPage()


def _walk_ld(payload: object) -> list[dict]:
    if isinstance(payload, list):
        found: list[dict] = []
        for item in payload:
            found.extend(_walk_ld(item))
        return found
    if isinstance(payload, dict):
        nested = payload.get("@graph")
        if isinstance(nested, list):
            return _walk_ld(nested)
        found = [payload]
        main = payload.get("mainEntity")
        if main is not None:
            found.extend(_walk_ld(main))
        return found
    return []


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _offer(offers: object) -> dict | None:
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if isinstance(offers, dict):
        return offers
    return None


def _price(offers: object) -> str | None:
    offer = _offer(offers)
    if offer is None:
        return None
    return _text(offer.get("price"))


def _offer_text(offers: object, key: str) -> str | None:
    offer = _offer(offers)
    if offer is None:
        return None
    return _text(offer.get(key))


def _availability(offers: object) -> str | None:
    raw = _offer_text(offers, "availability")
    if raw is None:
        return None
    return raw.rsplit("/", 1)[-1]


def _brand(value: object) -> str | None:
    if isinstance(value, dict):
        return _text(value.get("name"))
    return _text(value)


def _weight(value: object) -> str | None:
    if isinstance(value, dict):
        amount = _text(value.get("value"))
        unit = _text(value.get("unitText") or value.get("unitCode"))
        if amount and unit:
            return f"{amount} {unit}"
        return amount
    return _text(value)


def _image(value: object) -> str | None:
    if isinstance(value, list):
        return _image(value[0]) if value else None
    if isinstance(value, dict):
        return _text(value.get("url") or value.get("contentUrl"))
    return _text(value)


def _read_seed(path: str, limit: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            url = (record.get("canonical_url") or "").strip()
            product_id = (record.get("product_id") or "").strip()
            if not url or not product_id:
                continue
            rows.append((product_id, url))
            if limit and len(rows) >= limit:
                break
    return rows
