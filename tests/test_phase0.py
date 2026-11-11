"""Synthetic fixtures only. Do not put real Glamira events in git."""

from __future__ import annotations

import gzip
import io
import json
import struct
import tarfile
import unittest
from pathlib import Path

from src.explore.profile import Profile, classify_ip, local_time_to_epoch, profile_documents
from src.explore.render import render_null_profile, render_quality_report
from src.explore.sketch import HyperLogLog
from src.stream.bson_lite import iter_fields
from src.stream.tar_bson import SummaryDump, parse_tar_size


def bdoc(items: list[tuple[str, object]]) -> bytes:
    body = bytearray()
    for key, value in items:
        key_bytes = key.encode() + b"\x00"
        if value is None:
            body.append(0x0A)
            body += key_bytes
        elif isinstance(value, bool):
            body.append(0x08)
            body += key_bytes
            body.append(1 if value else 0)
        elif isinstance(value, int):
            body.append(0x10)
            body += key_bytes
            body += struct.pack("<i", value)
        elif isinstance(value, str):
            body.append(0x02)
            body += key_bytes
            raw = value.encode() + b"\x00"
            body += struct.pack("<i", len(raw))
            body += raw
        elif isinstance(value, dict):
            body.append(0x03)
            body += key_bytes
            body += bdoc(list(value.items()))
        elif isinstance(value, list):
            body.append(0x04)
            body += key_bytes
            body += bdoc([(str(index), item) for index, item in enumerate(value)])
        elif isinstance(value, bytes):
            body.append(0x07)
            body += key_bytes
            if len(value) != 12:
                raise ValueError("object id must be 12 bytes")
            body += value
        else:
            raise TypeError(type(value))
    body.append(0)
    return struct.pack("<i", len(body) + 4) + bytes(body)


class BsonLiteTest(unittest.TestCase):
    def test_reads_field_after_nested_document(self) -> None:
        document = bdoc(
            [
                ("collection", "view_listing_page"),
                ("option", {"alloy": ""}),
                ("device_id", "device-ok"),
                ("after", "skipped-text"),
                ("cat_id", None),
                ("flag", False),
            ]
        )
        fields = dict(iter_fields(document))
        self.assertEqual(fields["device_id"].raw, b"device-ok")
        self.assertEqual(fields["after"].kind, "str")
        self.assertIsNone(fields["after"].raw)
        self.assertFalse(fields["after"].nullish)
        self.assertTrue(fields["cat_id"].nullish)
        self.assertFalse(fields["flag"].nullish)
        self.assertFalse(fields["flag"].flag)
        self.assertTrue(fields["option"].kind == "doc")

    def test_empty_string_is_nullish_without_copying_unneeded_text(self) -> None:
        document = bdoc(
            [
                ("collection", "view_home_page"),
                ("email_address", "secret@example.com"),
                ("user_agent", "VeryLongAgent/1.0"),
                ("ip", ""),
            ]
        )
        fields = dict(iter_fields(document))
        self.assertIsNone(fields["email_address"].raw)
        self.assertFalse(fields["email_address"].nullish)
        self.assertIsNone(fields["user_agent"].raw)
        self.assertTrue(fields["ip"].nullish)

    def test_int64_and_object_id_do_not_desync_parser(self) -> None:
        body = bytearray()
        body.append(0x12)
        body += b"time_stamp\x00"
        body += struct.pack("<q", 1_591_266_092)
        body.append(0x07)
        body += b"_id\x00"
        body += b"\x5e\xd8\xcb\x2a" + b"\x00" * 8
        body.append(0x02)
        body += b"collection\x00"
        raw = b"checkout\x00"
        body += struct.pack("<i", len(raw))
        body += raw
        body.append(0)
        document = struct.pack("<i", len(body) + 4) + bytes(body)
        fields = dict(iter_fields(document))
        self.assertEqual(fields["time_stamp"].number, 1_591_266_092)
        self.assertEqual(fields["collection"].raw, b"checkout")


class TarSizeTest(unittest.TestCase):
    def test_octal_and_gnu_base256(self) -> None:
        # 12-byte ustar field. 363 octal == 243 decimal (metadata.json size).
        self.assertEqual(parse_tar_size(b"00000000363\x00"), 243)
        self.assertEqual(parse_tar_size(b"00000000243\x00"), 0o243)
        encoded = bytes([0x80]) + (33_530_129_089).to_bytes(11, "big")
        self.assertEqual(parse_tar_size(encoded), 33_530_129_089)

    def test_roundtrip_tiny_dump(self) -> None:
        first = bdoc(
            [
                ("_id", b"\x01" * 12),
                ("collection", "view_home_page"),
                ("ip", "8.8.8.8"),
                ("time_stamp", 1_600_000_000),
                ("local_time", "2020-09-13 12:26:40"),
            ]
        )
        second = bdoc(
            [
                ("_id", b"\x02" * 12),
                ("collection", "checkout"),
                ("ip", "10.0.0.8"),
                ("cart_products", [{"product_id": 42, "amount": 1}]),
            ]
        )
        blob = io.BytesIO()
        with tarfile.open(fileobj=blob, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            payload = first + second
            info = tarfile.TarInfo(name="dump/countly/summary.bson")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        gz_path = Path(self._tmpdir()) / "mini.tar.gz"
        with gzip.open(gz_path, "wb") as handle:
            handle.write(blob.getvalue())

        docs = list(SummaryDump(gz_path))
        self.assertEqual(docs, [first, second])
        dump = SummaryDump(gz_path)
        list(dump)
        self.assertTrue(dump.completed)
        self.assertEqual(dump.leftover_bytes, 0)
        self.assertEqual(dump.member_size, len(first) + len(second))

    def _tmpdir(self) -> str:
        import tempfile

        path = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(path))
        return path


class ProfileTest(unittest.TestCase):
    def test_nullish_ip_and_cart_product_without_leaking_email(self) -> None:
        secret = "secret@example.com"
        docs = [
            bdoc(
                [
                    ("_id", b"\x11" * 12),
                    ("collection", "view_product_detail"),
                    ("ip", "8.8.8.8"),
                    ("product_id", "110474"),
                    ("current_url", f"https://www.glamira.co.uk/ring.html?email={secret}"),
                    ("email_address", secret),
                    ("user_agent", "Agent/Secret"),
                    ("show_recommendation", "false"),
                    ("time_stamp", 1_591_266_092),
                    ("local_time", "2020-06-04 12:21:32"),
                    ("store_id", "12"),
                    ("device_id", "device-a"),
                ]
            ),
            bdoc(
                [
                    ("_id", b"\x22" * 12),
                    ("collection", "view_home_page"),
                    ("ip", ""),
                    ("show_recommendation", False),
                    ("store_id", "12"),
                ]
            ),
            bdoc(
                [
                    ("_id", b"\x33" * 12),
                    ("collection", "checkout"),
                    ("ip", "10.1.2.3"),
                    ("cart_products", [{"product_id": 7}]),
                    ("current_url", "https://www.glamira.de/checkout/"),
                ]
            ),
        ]
        profile = profile_documents(docs, source="memory", sample_size=0)
        home = profile.nullish["view_home_page"]
        self.assertEqual(home["ip"], 1)
        self.assertEqual(home["product_id"], 1)
        detail = profile.nullish["view_product_detail"]
        self.assertEqual(detail["product_id"], 0)
        self.assertEqual(detail["ip"], 0)
        self.assertEqual(profile.product_link_by_event["checkout"], 1)
        self.assertEqual(profile.cart_with_product_id, 1)
        self.assertEqual(profile.html_by_event["view_product_detail"], 1)
        self.assertEqual(profile.ip_class["public"], 1)
        self.assertEqual(profile.ip_class["empty"], 1)
        self.assertEqual(profile.ip_class["private"], 1)
        self.assertEqual(profile.hosts["www.glamira.co.uk"], 1)
        self.assertEqual(profile.exact_dup_prefix_dups, 0)
        rendered = render_quality_report(profile) + render_null_profile(profile)
        blob = json.dumps(profile.to_dict())
        self.assertNotIn(secret, rendered)
        self.assertNotIn(secret, blob)
        self.assertNotIn("Agent/Secret", blob)
        self.assertIn("www.glamira.co.uk", blob)
        leaked = bdoc(
            [
                ("collection", "view_home_page"),
                ("show_recommendation", "erToken=SECRETVALUE123"),
                ("api_version", "1.0"),
            ]
        )
        leaked_profile = profile_documents([leaked], source="memory")
        leaked_blob = json.dumps(leaked_profile.to_dict())
        self.assertNotIn("SECRETVALUE123", leaked_blob)
        self.assertEqual(leaked_profile.value_counts["show_recommendation"]["(other)"], 1)
        roundtrip = profile.to_dict()
        restored = Profile.from_dict(roundtrip)
        self.assertEqual(restored.docs_scanned, profile.docs_scanned)
        self.assertEqual(restored.offset_hours, profile.offset_hours)

    def test_duplicate_prefix_id(self) -> None:
        document = bdoc([("_id", b"\x44" * 12), ("collection", "x")])
        profile = profile_documents([document, document], source="memory")
        self.assertEqual(profile.exact_dup_prefix_dups, 1)


class HelperTest(unittest.TestCase):
    def test_ip_and_local_time(self) -> None:
        self.assertEqual(classify_ip(b"8.8.8.8"), "public")
        self.assertEqual(classify_ip(b"192.168.0.1"), "private")
        self.assertEqual(classify_ip(b"127.0.0.1"), "loopback")
        self.assertEqual(classify_ip(b"not-an-ip"), "invalid")
        from datetime import datetime, timezone

        expected = int(datetime(2020, 6, 4, 8, 20, 4, tzinfo=timezone.utc).timestamp())
        self.assertEqual(local_time_to_epoch(b"2020-06-04 8:20:4"), expected)
        self.assertIsNone(local_time_to_epoch(b"04/06/2020 08:20:04"))

    def test_hll_orders_of_magnitude(self) -> None:
        sketch = HyperLogLog()
        for index in range(3000):
            sketch.add(f"id-{index}".encode())
        estimate = sketch.estimate()
        self.assertGreater(estimate, 2400)
        self.assertLess(estimate, 3600)
        repeated = HyperLogLog()
        for _ in range(1000):
            repeated.add(b"same")
        self.assertLess(repeated.estimate(), 5)


if __name__ == "__main__":
    unittest.main()
