"""reactdata crawl with a fake browser and a fake collection. No network, no Mongo."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import src.enrich.reactdata as react
from src.config import Settings


class FakePage:
    def __init__(self, script: dict) -> None:
        self.script = script

    def goto(self, url: str, **kwargs) -> None:
        pass

    def evaluate(self, js: str, url: str) -> dict:
        queue = self.script.setdefault(url, [{"status": 404, "error": "Product not found"}])
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def close(self) -> None:
        pass


class FakeBrowser:
    def __init__(self, script: dict) -> None:
        self.script = script

    def new_page(self) -> FakePage:
        return FakePage(self.script)

    def close(self) -> None:
        pass


class FakeProducts:
    def __init__(self, docs: list[dict] | None = None) -> None:
        self.docs = {d["_id"]: dict(d) for d in docs or []}

    def find(self, query: dict, projection: dict) -> list[dict]:
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

    def test_restart_skips_named_and_not_found(self) -> None:
        docs = [{"_id": "1", "name": "Done"}, {"_id": "2", "name": None, "not_found": True}]
        result, _ = self.run_crawl({}, ["1", "2", "3"], docs)
        self.assertEqual((result.skipped, result.attempted), (2, 1))


if __name__ == "__main__":
    unittest.main()
