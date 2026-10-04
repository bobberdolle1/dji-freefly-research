"""DJI DUML checksums, reimplemented from observed Free Fly behaviour.

Free Fly (com.dronehacks.app 1.0) uses two checksums in its DUML framing:

``crc8``
    Reflected table CRC over the first three header bytes (magic and the
    length/version word). Initial value ``0x77``. The polynomial was not assumed:
    the APK embeds a 256-entry table in ``DumlBuilder.<clinit>`` and that table is
    reproduced exactly by the reflected generation loop with polynomial ``0x8C``.

``crc16``
    A reflected table for polynomial ``0x8408`` (the reflection of ``0x1021``)
    combined with a **non-standard** update step that XORs the previous high byte
    instead of shifting. Initial value ``0x3692``. This is why a textbook
    CRC-16/CCITT will not reproduce Free Fly's frames.

Both routines are pinned byte-for-byte against the tables lifted out of the
APK's own bytecode by ``tests/test_duml.py``.
"""
from __future__ import annotations

CRC8_POLY = 0x8C
CRC8_INIT = 0x77
CRC16_POLY = 0x8408
CRC16_INIT = 0x3692


def _reflected_table(poly: int, bits: int) -> tuple[int, ...]:
    mask = (1 << bits) - 1
    table = []
    for index in range(256):
        reg = index
        for _ in range(8):
            reg = ((reg >> 1) ^ poly) & mask if reg & 1 else reg >> 1
        table.append(reg)
    return tuple(table)


CRC8_TABLE = _reflected_table(CRC8_POLY, 8)
CRC16_TABLE = _reflected_table(CRC16_POLY, 16)


def crc8(data: bytes | bytearray | memoryview, offset: int = 0, length: int | None = None) -> int:
    """Reflected CRC-8, poly 0x8C, init 0x77. Result is masked to 8 bits."""
    end = len(data) if length is None else offset + length
    reg = CRC8_INIT
    for i in range(offset, end):
        reg = CRC8_TABLE[(data[i] ^ reg) & 0xFF]
    return reg & 0xFF


def crc16(data: bytes | bytearray | memoryview, offset: int = 0, length: int | None = None) -> int:
    """Free Fly's CRC-16: 0x8408 table with a high-byte XOR update, init 0x3692."""
    end = len(data) if length is None else offset + length
    reg = CRC16_INIT
    for i in range(offset, end):
        high = (reg >> 8) & 0xFF
        reg = (CRC16_TABLE[(data[i] ^ reg) & 0xFF] ^ high) & 0xFFFF
    return reg & 0xFFFF