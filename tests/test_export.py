"""Load stamp and CSV export. No Mongo, no network."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

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




if __name__ == "__main__":
    unittest.main()
