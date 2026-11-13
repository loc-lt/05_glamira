from __future__ import annotations

import unittest
from collections import Counter

from src.enrich.crawl import parse_product_html
from src.enrich.extract_products import _choose, pair_from_document
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

    def test_choose_keeps_the_observed_uk_page(self) -> None:
        product_id = "100045"
        pages = {
            "https://www.glamira.fi/glamira-riipus-odila.html": 3,
            "https://www.glamira.de/glamira-pendant-odila.html": 50,
            "https://www.glamira.co.uk/glamira-pendant-odila.html": 6,
        }
        seen = {(product_id, url): "view_product_detail" for url in pages}
        chosen, _event = _choose(product_id, Counter(pages), seen, "https://www.glamira.co.uk")
        self.assertEqual(chosen, "https://www.glamira.co.uk/glamira-pendant-odila.html")


class HtmlParserTest(unittest.TestCase):
    def test_json_ld_name_and_category(self) -> None:
        html = """
        <html><head>
          <script type="application/ld+json">
            {"@type": "Product", "name": "Griseus", "category": "Rings",
             "description": "A ring", "image": "https://cdn.example/ring.jpg",
             "offers": {"price": "120"}}
          </script>
        </head>
        <body><h1>ignored</h1></body></html>
        """
        page = parse_product_html(html)
        self.assertEqual((page.name, page.category, page.price), ("Griseus", "Rings", "120"))
        self.assertEqual(page.image_url, "https://cdn.example/ring.jpg")

    def test_json_ld_variant_fields(self) -> None:
        html = """
        <html><head>
          <script type="application/ld+json">
            {"@type": "Product", "name": "Odila", "sku": "100045_41",
             "material": "14K White Gold", "color": "H", "gtin": "123",
             "mpn": "ODILA", "weight": {"value": "2.4", "unitText": "g"},
             "brand": {"@type": "Brand", "name": "Glamira Diamonds"},
             "offers": {"price": "9818.35", "priceCurrency": "USD",
                        "availability": "https://schema.org/InStock"}}
          </script>
        </head></html>
        """
        page = parse_product_html(html)
        self.assertEqual(page.currency, "USD")
        self.assertEqual(page.brand, "Glamira Diamonds")
        self.assertEqual(page.sku, "100045_41")
        self.assertEqual(page.material, "14K White Gold")
        self.assertEqual(page.color, "H")
        self.assertEqual(page.availability, "InStock")
        self.assertEqual(page.weight, "2.4 g")
        self.assertEqual((page.gtin, page.mpn), ("123", "ODILA"))

    def test_catalog_fallback_uses_product_id(self) -> None:
        self.assertEqual(
            catalog_product_url("102002"),
            "https://www.glamira.com/catalog/product/view/id/102002",
        )
        self.assertEqual(
            catalog_product_url("102002", "www.glamira.co.uk"),
            "https://www.glamira.co.uk/catalog/product/view/id/102002",
        )

    def test_crawl_chain_is_seed_then_com_then_uk(self) -> None:
        seed, com, uk = crawl_url_chain(
            "102002", "https://www.glamira.de/glamira-ring-loronda.html"
        )
        self.assertEqual(seed, "https://www.glamira.de/glamira-ring-loronda.html")
        self.assertEqual(com, "https://www.glamira.com/catalog/product/view/id/102002")
        self.assertEqual(uk, "https://www.glamira.co.uk/catalog/product/view/id/102002")

    def test_product_nested_under_item_page(self) -> None:
        html = """
        <html><head>
          <script type="application/ld+json">
            {"@type": "ItemPage", "mainEntity": {
              "@type": "Product", "name": "Reyneke", "category": "Rings",
              "offers": {"price": 4373.25}
            }}
          </script>
        </head></html>
        """
        page = parse_product_html(html)
        self.assertEqual((page.name, page.category, page.price), ("Reyneke", "Rings", "4373.25"))

    def test_breadcrumb_fallback(self) -> None:
        html = """
        <html><body>
          <nav class="breadcrumbs"><a>Home</a><a>Rings</a><a>Griseus</a></nav>
          <h1>Griseus Ring</h1>
        </body></html>
        """
        page = parse_product_html(html)
        self.assertEqual((page.name, page.category), ("Griseus Ring", "Griseus"))


class PairRuleTest(unittest.TestCase):
    def test_detail_uses_current_url(self) -> None:
        document = {
            "product_id": "110474",
            "current_url": "https://www.glamira.fr/glamira-pendant-viktor.html?x=1",
        }
        self.assertEqual(
            pair_from_document("view_product_detail", document, "https://www.glamira.co.uk"),
            ("110474", "https://www.glamira.fr/glamira-pendant-viktor.html"),
        )

    def test_back_to_product_uses_referrer_page(self) -> None:
        document = {
            "product_id": "98267",
            "current_url": "https://www.glamira.pt/county/recommendation/list/id/98267/",
            "referrer_url": "https://www.glamira.pt/glamira-ring-linderoth.html",
        }
        self.assertEqual(
            pair_from_document("back_to_product_action", document, "https://www.glamira.co.uk"),
            ("98267", "https://www.glamira.pt/glamira-ring-linderoth.html"),
        )

    def test_recommendation_widget_is_not_paired(self) -> None:
        document = {
            "viewing_product_id": "89454",
            "current_url": "https://www.glamira.com.au/glamira-ring-pamela.html",
        }
        self.assertIsNone(
            pair_from_document(
                "product_detail_recommendation_visible",
                document,
                "https://www.glamira.co.uk",
            )
        )


if __name__ == "__main__":
    unittest.main()
