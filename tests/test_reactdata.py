"""reactdata crawl with a fake browser and a fake collection. No network, no Mongo."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import src.enrich.reactdata as react
from src.config import Settings


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def body(self) -> bytes:
        return self._body


class FakePage:
    """Plays a script of answers per URL; the last answer repeats."""

    def __init__(self, script: dict) -> None:
        self.script = script

    def goto(self, url: str, **kwargs) -> FakeResponse:
        queue = self.script.setdefault(url, [{"status": 404, "error": "Product not found"}])
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if answer["status"] == 0:
            raise RuntimeError(answer["error"])
        if "data" in answer:
            d = answer["data"]
            raw = {"name": d.get("name"), "sku": d.get("sku"), "product_type": d.get("product_type"),
                   "category_name": d.get("category_name"),
                   "product_price": {"price": d.get("price"), "currencyCode": d.get("currency")}}
            return FakeResponse(answer["status"], json.dumps(raw).encode())
        if answer.get("error") == "Product not found":
            return FakeResponse(answer["status"], b'{"error":"Product not found"}')
        return FakeResponse(answer["status"], b"<html>Service Unavailable</html>")

    def close(self) -> None:
        pass


class FakeBrowser:
    def __init__(self, script: dict) -> None:
        self.script = script
        self.connected = True

    def new_page(self) -> FakePage:
        if not self.connected:
            raise RuntimeError("Browser.new_page: Target page, context or browser has been closed")
        return FakePage(self.script)

    def is_connected(self) -> bool:
        return self.connected

    def close(self) -> None:
        self.connected = False


class FakeProducts:
    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs = {d["_id"]: dict(d) for d in docs or []}

    def find(self, query: dict, projection: dict) -> list[dict]:
        if not query:
            return list(self.docs.values())
        def named(d: dict) -> bool:
            return isinstance(d.get("name"), str) and d["name"] != ""

        out = []
        for d in self.docs.values():
            if "$or" in query:
                if named(d) or d.get("not_found") is True:
                    out.append(d)
            elif named(d):
                out.append(d)
        return out

    def bulk_write(self, ops, ordered: bool = False) -> None:
        for op in ops:
            doc = op._doc["$set"]
            self.docs.setdefault(op._filter["_id"], {"_id": op._filter["_id"]}).update(doc)

    def count_documents(self, query: dict) -> int:
        return len(self.docs)

    def aggregate(self, pipeline: list) -> list[dict]:
        counts: dict = {}
        for d in self.docs.values():
            if isinstance(d.get("name"), str) and d["name"]:
                counts[d.get("category")] = counts.get(d.get("category"), 0) + 1
        return [{"_id": k, "n": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


def payload(name: str, kind: str = "ring") -> dict:
    return {"status": 200, "data": {"name": name, "product_type": kind, "price": "720.000000",
                                    "currency": "GBP", "sku": "PALMIER", "category_name": ""}}


class ReactDataTest(unittest.TestCase):
    def run_crawl(self, script: dict, seed_ids: list[str], docs: list[dict] | None = None) -> tuple:
        products = FakeProducts(docs)
        client = {"glamira": {"products": products}}
        tmp = tempfile.mkdtemp()
        seed = Path(tmp) / "seed.csv"
        seed.write_text("product_id,canonical_url,source_event\n"
                        + "".join(f"{i},https://x/{i}.html,view_product_detail\n" for i in seed_ids))
        settings = Settings(None, None, "mongodb://fake", "glamira", "glamira_raw", "products",
                            10000, 1.0, "https://www.glamira.co.uk", "ua")
        with mock.patch.object(react, "get_client", return_value=client), \
                mock.patch.object(react.time, "sleep"):
            result = react.crawl_reactdata(settings, seed_path=str(seed), out_md=str(Path(tmp) / "r.md"),
                                           browser_factory=lambda: FakeBrowser(script))
        return result, products

    def test_fields_use_product_type_as_category(self) -> None:
        fields = react.react_fields(payload("Engagement Ring Palmier")["data"])
        self.assertEqual((fields["name"], fields["category"], fields["currency"]),
                         ("Engagement Ring Palmier", "ring", "GBP"))

    def test_parse_response_cases(self) -> None:
        ok = react.parse_response(200, json.dumps({"name": "Ring", "product_type": "ring",
                                                    "product_price": {"price": "851", "currencyCode": "GBP"},
                                                    "media_image": {"images": [{"large_image_url": "https://img"}]}}).encode())
        self.assertEqual((ok["data"]["name"], ok["data"]["currency"], ok["data"]["image_url"]), ("Ring", "GBP", "https://img"))
        self.assertEqual(react.parse_response(404, b'{"error":"Product not found"}')["error"], "Product not found")
        blocked = react.parse_response(403, b"<html>Access Denied</html>")
        self.assertTrue(react.is_transient(blocked["status"], blocked["error"]))

    def test_url_adds_currency_only_for_uk(self) -> None:
        self.assertTrue(react.react_url("www.glamira.co.uk", "1").endswith("/id/1/?currency=GBP"))
        self.assertTrue(react.react_url("www.glamira.com", "1").endswith("/id/1/"))

    def test_found_on_uk_then_missing_everywhere(self) -> None:
        uk = react.react_url("www.glamira.co.uk", "100002")
        result, products = self.run_crawl({uk: [payload("Engagement Ring Palmier")]}, ["100002", "102226"])
        self.assertEqual((result.named, result.not_found), (1, 1))
        self.assertEqual(products.docs["100002"]["category"], "ring")
        self.assertTrue(products.docs["102226"]["not_found"])

    def test_falls_back_to_com(self) -> None:
        com = react.react_url("www.glamira.com", "5")
        result, products = self.run_crawl({com: [payload("Ring Five")]}, ["5"])
        self.assertEqual(products.docs["5"]["host"], "www.glamira.com")
        self.assertEqual(result.named, 1)

    def test_transient_error_is_retried_not_skipped(self) -> None:
        uk = react.react_url("www.glamira.co.uk", "7")
        script = {uk: [{"status": 0, "error": "TypeError: Failed to fetch"},
                       {"status": 503, "error": "http 503"},
                       payload("Ring Seven")]}
        result, products = self.run_crawl(script, ["7"])
        self.assertEqual(products.docs["7"]["name"], "Ring Seven")
        self.assertEqual(result.not_found, 0)

    def test_startup_waits_when_mongo_is_unreachable(self) -> None:
        from pymongo.errors import ServerSelectionTimeoutError

        calls = {"n": 0}
        real_done_ids = react.done_ids

        def flaky(products, retry_missing=False, refresh_old=False):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ServerSelectionTimeoutError("firewall")
            return real_done_ids(products, retry_missing, refresh_old)

        uk = react.react_url("www.glamira.co.uk", "9")
        with mock.patch.object(react, "done_ids", side_effect=flaky):
            result, products = self.run_crawl({uk: [payload("Ring Nine")]}, ["9"])
        self.assertEqual(calls["n"], 2)
        self.assertEqual(products.docs["9"]["name"], "Ring Nine")

    def test_single_blip_retries_in_same_tab(self) -> None:
        uk = react.react_url("www.glamira.co.uk", "12")
        script = {uk: [{"status": 0, "error": "TypeError: Failed to fetch"}, payload("Ring Twelve")]}
        opened = {"pages": 0}
        real_new_page = FakeBrowser.new_page

        def counting_new_page(self):
            opened["pages"] += 1
            return real_new_page(self)

        with mock.patch.object(FakeBrowser, "new_page", counting_new_page):
            result, products = self.run_crawl(script, ["12"])
        self.assertEqual(products.docs["12"]["name"], "Ring Twelve")
        self.assertEqual(opened["pages"], 1)     # no tab was reopened for one blip

    def test_closed_browser_is_relaunched(self) -> None:
        uk = react.react_url("www.glamira.co.uk", "11")
        launched: list[FakeBrowser] = []
        script = {uk: [{"status": 0, "error": "TargetClosedError: Page.evaluate: Target page, context or browser has been closed"},
                       payload("Ring Eleven")]}

        def factory() -> FakeBrowser:
            browser = FakeBrowser(script)
            if not launched:
                browser.connected = False      # first Chrome dies: every new_page fails
            launched.append(browser)
            return browser

        products = FakeProducts()
        tmp = tempfile.mkdtemp()
        seed = Path(tmp) / "seed.csv"
        seed.write_text("product_id,canonical_url,source_event\n11,https://x/11.html,view_product_detail\n")
        settings = Settings(None, None, "mongodb://fake", "glamira", "glamira_raw", "products",
                            10000, 1.0, "https://www.glamira.co.uk", "ua")
        with mock.patch.object(react, "get_client", return_value={"glamira": {"products": products}}), \
                mock.patch.object(react.time, "sleep"):
            react.crawl_reactdata(settings, seed_path=str(seed), out_md=str(Path(tmp) / "r.md"),
                                  browser_factory=factory)
        self.assertGreaterEqual(len(launched), 2)
        self.assertEqual(products.docs["11"]["name"], "Ring Eleven")

    def test_placeholder_type_becomes_null(self) -> None:
        for bad in ("--_select_--", "-1"):
            self.assertIsNone(react.react_fields({"name": "Shipping Label Fee", "product_type": bad})["category"])

    def test_refresh_old_reasks_html_crawl_and_bad_category(self) -> None:
        docs = [{"_id": "1", "name": "From HTML", "category": "Jewellery / Rings"},          # old crawl
                {"_id": "2", "name": "Fee", "category": "--_select_--", "source": "reactdata"},
                {"_id": "3", "name": "Good", "category": "ring", "source": "reactdata"},
                {"_id": "4", "name": None, "not_found": True, "source": "reactdata"}]
        products = FakeProducts(docs)
        self.assertEqual(react.done_ids(products), {"1", "2", "3", "4"})
        self.assertEqual(react.done_ids(products, refresh_old=True), {"3", "4"})

    def test_restart_skips_named_and_not_found(self) -> None:
        docs = [{"_id": "1", "name": "Done"}, {"_id": "2", "name": None, "not_found": True}]
        result, _ = self.run_crawl({}, ["1", "2", "3"], docs)
        self.assertEqual((result.skipped, result.attempted), (2, 1))


if __name__ == "__main__":
    unittest.main()
