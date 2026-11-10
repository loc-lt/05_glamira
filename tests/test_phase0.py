"""Synthetic fixtures only. Do not put real Glamira events in git."""

from __future__ import annotations

import tarfile
import unittest

from src.stream.tar_bson import parse_tar_header, parse_tar_size


class TarSizeTest(unittest.TestCase):
    def test_octal_and_gnu_base256(self) -> None:
        # 12-byte ustar field. 363 octal == 243 decimal (metadata.json size).
        self.assertEqual(parse_tar_size(b"00000000363\x00"), 243)
        self.assertEqual(parse_tar_size(b"00000000243\x00"), 0o243)
        encoded = bytes([0x80]) + (33_530_129_089).to_bytes(11, "big")
        self.assertEqual(parse_tar_size(encoded), 33_530_129_089)

    def test_header_name_size_type(self) -> None:
        # tarfile dựng một header ustar thật 512 byte để kiểm hàm đọc của bạn.
        info = tarfile.TarInfo(name="dump/countly/summary.bson")
        info.size = 1234
        header = info.tobuf(format=tarfile.USTAR_FORMAT)[:512]
        self.assertEqual(parse_tar_header(header), ("dump/countly/summary.bson", 1234, "0"))


if __name__ == "__main__":
    unittest.main()