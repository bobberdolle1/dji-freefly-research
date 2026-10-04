"""Streaming DUML framing.

**Difference from Free Fly, stated up front:** the app's ``DumlParser.parse`` is
single-shot and has no resynchronisation. On a short buffer, bad magic, an
impossible length or either CRC mismatch it simply returns a failed
``ParseResult`` and the caller is left to work out what happened. A real serial
link delivers arbitrary partial reads, so a byte-stream framer that resynchronises
on the magic byte is strictly more useful — and it is the reason this module
exists separately from :mod:`flylib.packet`.

Resynchronisation policy:

* a frame whose length word is still incomplete is left in the buffer (more bytes
  may arrive);
* a frame with a plausible length but a failed CRC is **discarded**, then framing
  resumes at the next occurrence of the magic byte;
* a byte that cannot start a frame is skipped one at a time.

The consequence to be aware of: a corrupted payload containing a second ``0x55``
can cause the framer to lock onto a false frame boundary. That is inherent to
length-anchored framing with no outer envelope, and it is reported through
``resyncs`` so a caller can notice it happening.
"""
from __future__ import annotations

import dataclasses
from typing import Iterator

from .packet import (CRC_SIZE, HEADER_SIZE, MAGIC, MIN_FRAME_SIZE, DumlError,
                     frame_length_at, parse_header, unpack_dev_byte)


@dataclasses.dataclass
class ParseEvent:
    """One framed message: either a decoded frame or a resynchronisation."""

    packet: object | None
    error: str | None = None
    offset: int = 0
    consumed: int = 0

    @property
    def ok(self) -> bool:
        return self.packet is not None


@dataclasses.dataclass
class FramerStats:
    frames: int = 0
    resyncs: int = 0
    discarded_bytes: int = 0


class StreamParser:
    """Incremental DUML framer over an arbitrary byte stream."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._offset = 0
        self.stats = FramerStats()

    def feed(self, data: bytes) -> list[ParseEvent]:
        """Add bytes and return every event that can now be resolved."""
        self._buf.extend(data)
        return list(self._drain())

    def _drain(self) -> Iterator[ParseEvent]:
        while True:
            start = self._buf.find(bytes([MAGIC]))
            if start < 0:
                # No frame start anywhere in the buffer. Everything is dropped;
                # a trailing 0x55 would have been found by the search above, so
                # nothing useful is lost.
                if self._buf:
                    yield self._resync(len(self._buf), reason="no frame start in buffer")
                return
            if start:
                yield self._resync(start, reason="skipped bytes before frame start")
            length = frame_length_at(bytes(self._buf), 0)
            if length is None:
                # Either no length word yet, or an implausible one. Requiring
                # HEADER_SIZE keeps a stray 0x55 from parking the framer forever.
                if len(self._buf) < 3:
                    return
                self._resync(1)
                continue
            if len(self._buf) < length:
                return
            frame = bytes(self._buf[:length])
            try:
                header, _ = parse_header(frame)
            except DumlError as exc:
                self._resync(1, reason=str(exc))
                continue
            payload = bytes(self._buf[HEADER_SIZE:length - CRC_SIZE])
            packet = _make_packet(header, payload)
            self.stats.frames += 1
            yield ParseEvent(packet=packet, offset=self._offset, consumed=length)
            self._discard(length)

    def _discard(self, count: int) -> None:
        del self._buf[:count]
        self._offset += count
        self.stats.discarded_bytes += count

    def _resync(self, count: int, reason: str | None = None) -> ParseEvent:
        offset = self._offset
        self.stats.resyncs += 1
        self._discard(count)
        return ParseEvent(packet=None, error=reason or "resynchronised", offset=offset)


def _make_packet(header, payload: bytes):
    from .packet import Packet
    return Packet(
        cmd_set=header.cmd_set,
        cmd_id=header.cmd_id,
        payload=payload,
        sequence=header.sequence,
        packet_type=header.packet_type,
        ack_type=header.ack_type,
        sender_type=header.sender_type,
        sender_index=header.sender_index,
        receiver_type=header.receiver_type,
        receiver_index=header.receiver_index,
        version=header.version,
    )


def resync_offset(data: bytes, max_scan: int = 4096) -> int:
    """Index of the next plausible frame start, or -1.

    Public helper so a caller can recover framing after discarding a buffer
    without instantiating a :class:`StreamParser`.
    """
    window = data[:max_scan]
    start = 0
    while True:
        idx = window.find(bytes([MAGIC]), start)
        if idx < 0:
            return -1
        length = frame_length_at(window, idx)
        if length is not None and length >= HEADER_SIZE:
            return idx
        start = idx + 1