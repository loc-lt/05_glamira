"""Small cardinality sketch. Error is about 1.04 / sqrt(2**p)."""

from __future__ import annotations

import math
import zlib


class HyperLogLog:
    def __init__(self, precision: int = 14) -> None:
        if not 4 <= precision <= 18:
            raise ValueError("precision must be between 4 and 18")
        self.precision = precision
        self._m = 1 << precision
        self._registers = bytearray(self._m)

    def add(self, data: bytes) -> None:
        if not data:
            return
        low = zlib.crc32(data) & 0xFFFFFFFF
        high = zlib.crc32(data, 0x9E3779B1) & 0xFFFFFFFF
        hashed = low | (high << 32)
        index = hashed & (self._m - 1)
        rest = hashed >> self.precision
        width = 64 - self.precision
        rank = width - rest.bit_length() + 1 if rest else width + 1
        if rank > self._registers[index]:
            self._registers[index] = rank

    def estimate(self) -> float:
        alpha = 0.7213 / (1.0 + 1.079 / self._m)
        inverse = 0.0
        zeros = 0
        for register in self._registers:
            inverse += 2.0 ** (-int(register))
            if register == 0:
                zeros += 1
        estimate = alpha * self._m * self._m / inverse
        if estimate <= 2.5 * self._m and zeros:
            estimate = self._m * math.log(self._m / zeros)
        return estimate
