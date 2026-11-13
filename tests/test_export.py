"""Load stamp and CSV export. No Mongo, no network."""

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.enrich.export_csv import COLUMNS, seed_ids, write_rows
from src.ingest.load_mongo import LoadResult, stamp


class LoadStampTest(unittest.TestCase):
    def test_stamp_adds_audit_fields_without_touching_source(self) -> None:
        when = datetime(2026, 11, 9, tzinfo=timezone.utc)
        doc = stamp({"_id": 1, "collection": "view_product_detail"}, when, "dump.tar.gz")
        self.assertEqual(doc["_loaded_at"], when)
        self.assertEqual(doc["_source_file"], "dump.tar.gz")
        self.assertEqual(doc["collection"], "view_product_detail")

    def test_stamp_keeps_an_existing_value(self) -> None:
        when = datetime(2026, 11, 9, tzinfo=timezone.utc)
        doc = stamp({"_source_file": "older.tar.gz"}, when, "new.tar.gz")
        self.assertEqual(doc["_source_file"], "older.tar.gz")

    def test_count_check(self) -> None:
        base = dict(inserted=0, duplicates=0, elapsed_seconds=0.0, stopped_for_disk=False,
                    ip_count_path="", distinct_ips=0)
        self.assertTrue(LoadResult(docs_scanned=5, completed_member=True, mongo_count=5, **base).count_matches)
        self.assertFalse(LoadResult(docs_scanned=5, completed_member=True, mongo_count=4, **base).count_matches)
        self.assertFalse(LoadResult(docs_scanned=5, completed_member=False, mongo_count=5, **base).count_matches)


class CsvExportTest(unittest.TestCase):
    def test_missing_fields_are_empty_cells(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "ip_geo.csv")
            rows = write_rows(path, COLUMNS["ip_geo"], [
                {"_id": "1.2.3.4", "status": "ok", "country_code": "DE", "city": "Berlin", "events": 3},
                {"_id": "10.0.0.1", "status": "private", "events": 1},
            ])
            self.assertEqual(rows, 2)
            with open(path, encoding="utf-8", newline="") as handle:
                records = list(csv.DictReader(handle))
            self.assertEqual(records[0]["country_code"], "DE")
            self.assertEqual(records[1]["country_code"], "")

    def test_datetime_is_iso(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "products.csv")
            when = datetime(2026, 11, 9, 1, 2, 3, tzinfo=timezone.utc)
            write_rows(path, ("_id", "crawled_at"), [{"_id": "100", "crawled_at": when}])
            self.assertIn("2026-11-09T01:02:03+00:00", Path(path).read_text(encoding="utf-8"))

    def test_seed_ids_skip_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seed.csv"
            path.write_text("product_id,canonical_url,source_event\n100,u,e\n,u,e\n101,u,e\n", encoding="utf-8")
            self.assertEqual(seed_ids(str(path)), {"100", "101"})


if __name__ == "__main__":
    unittest.main()
