from __future__ import annotations

import unittest
from collections import Counter

from src.enrich.urls import (
    canonical_product_url,
    catalog_product_url,
    crawl_url_chain,
    normalize_product_id,
    prefer_url,
)
class UrlRuleTest(unittest.TestCase):
    def test_canonical_keeps_store_host_and_drops_query(self) -> None:
        raw = "https://www.glamira.de/glamira-ring-griseus.html?alloy=yellow-585&gclid=abc"
        self.assertEqual(
            canonical_product_url(raw, "https://www.glamira.co.uk"),
            "https://www.glamira.de/glamira-ring-griseus.html",
        )

    def test_listing_url_is_not_a_product(self) -> None:
        self.assertIsNone(
            canonical_product_url("https://www.glamira.de/diamant-verlobungsringe/", "https://www.glamira.co.uk")
        )

    def test_cart_int_and_detail_string_match(self) -> None:
        self.assertEqual(normalize_product_id(95519), "95519")
        self.assertEqual(normalize_product_id("95519"), "95519")
        self.assertEqual(normalize_product_id(95519.0), "95519")

    def test_prefer_uk_host(self) -> None:
        de = "https://www.glamira.de/ring.html"
        uk = "https://www.glamira.co.uk/ring.html"
        self.assertEqual(prefer_url(de, uk), uk)
        self.assertEqual(prefer_url(uk, de), uk)

    def test_translated_slug_stays_on_its_store(self) -> None:
        raw = "https://www.glamira.fi/glamira-riipus-odila.html?stone2=diamond"
        self.assertEqual(
            canonical_product_url(raw, "https://www.glamira.co.uk"),
            "https://www.glamira.fi/glamira-riipus-odila.html",
        )

    def test_real_uk_page_beats_a_translated_slug(self) -> None:
        finnish = "https://www.glamira.fi/glamira-riipus-odila.html"
        uk = "https://www.glamira.co.uk/glamira-pendant-odila.html"
        self.assertEqual(prefer_url(finnish, uk), uk)
        self.assertEqual(prefer_url(uk, finnish), uk)
if __name__ == "__main__":
    unittest.main()
