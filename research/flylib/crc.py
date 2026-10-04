"""DJI DUML checksums, reimplemented from observed Free Fly behaviour.

Free Fly (com.dronehacks.app 1.0) uses two checksums in its DUML framing.

``crc8``
    A reflected (LSB-first) CRC-8 with polynomial ``0x8C`` and initial value
    ``0x77``, taken over the first three header bytes (the magic and the
    length/version word).

    The polynomial was not assumed. The APK embeds a 256-entry table in
    ``DumlBuilder.<clinit>``; that table is reproduced exactly by the reflected
    generation loop with polynomial ``0x8C``, and
    ``tests/test_duml.py`` compares the two element by element.

``crc16``
    The **standard LSB-first (reflected) CRC-16 step**

        crc = (crc >> 8) ^ table[(crc ^ byte) & 0xFF]

    over the reflected table for polynomial ``0x8408``, which is the reflection
    of ``0x1021``.

    The algorithm itself is ordinary. What is DJI-specific is the *parameters*:
    initial value ``0x3692``, no final XOR, no reflection of the result. In
    catalogue terms this is CRC-16/X-25 with a non-standard initial value, so an
    implementer who "simplifies" the unusual-looking update expression is still
    computing the same function — what has to be reproduced exactly is the
    reflected table, the init, and xorout 0. The APK's spelling reads
    ``t = crc >> 8; crc = table[(byte ^ crc) & 0xFF] ^ t``, which is the same
    step reordered; the equality is asserted in ``tests/test_duml.py`` rather
    than left as prose.

Both routines are pinned byte-for-byte against the tables lifted out of the
APK's own bytecode, so the polynomial derivation is evidence and not assertion.
"""
from __future__ import annotations

CRC8_POLY = 0x8C
CRC8_INIT = 0x77
CRC16_POLY = 0x8408          # reflection of 0x1021
CRC16_INIT = 0x3692
CRC16_XOROUT = 0x0000


def _reflected_table(poly: int, bits: int) -> tuple[int, ...]:
    """Standard LSB-first table generation for one polynomial."""
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


def crc8(data, offset: int = 0, length: int | None = None) -> int:
    """Reflected CRC-8, poly 0x8C, init 0x77. Result is masked to 8 bits."""
    end = len(data) if length is None else offset + length
    reg = CRC8_INIT
    for i in range(offset, end):
        reg = CRC8_TABLE[(data[i] ^ reg) & 0xFF]
    return reg & 0xFF


def crc16(data, offset: int = 0, length: int | None = None) -> int:
    """CRC-16/X-25 step with DJI's parameters: poly 0x1021 reflected, init 0x3692.

    ``init`` and ``xorout`` are exposed because they are the parts that differ
    from a textbook X-25, and getting them wrong yields plausible-looking frames
    that no aircraft will accept.
    """
    end = len(data) if length is None else offset + length
    reg = CRC16_INIT
    for i in range(offset, end):
        reg = (reg >> 8) ^ CRC16_TABLE[(reg ^ data[i]) & 0xFF]
    return (reg ^ CRC16_XOROUT) & 0xFFFF