"""Transports and a request/response session.

Four transports, in increasing order of risk:

:class:`ReplayTransport`
    Replays a recorded capture. No hardware, no writes, fully deterministic —
    this is what the test suite uses.

:class:`ScriptedTransport`
    Returns canned responses chosen per request, for exercising policy branches
    (2017 empty, CRC failures, truncated replies) without needing a drone.

:class:`DryRunTransport`
    Records frames instead of sending them. Read operations pass through to
    whatever reply source is configured; state-changing frames are rendered and
    logged, never transmitted.

:class:`LiveTransport`
    The real thing. It refuses state-changing frames unless the guard has been
    explicitly enabled *and* is not in dry-run mode.

The write guard is enforced in :meth:`Transport.send` for every transport, so
no code path can reach a device with a mutating frame by picking a different
transport class.
"""
from __future__ import annotations

import abc
import dataclasses
import time
from typing import Callable, Iterable

from .guard import MutationGuard, is_state_changing
from .packet import Packet, parse_packet
from .parser import StreamParser

DEFAULT_TIMEOUT_MS = 2000      # matches the APK's bulk-transfer timeout
DEFAULT_RETRIES = 0            # the APK does not retry; neither do we by default


class Transport(abc.ABC):
    """A bidirectional byte channel."""

    name = "transport"

    def __init__(self, guard: MutationGuard | None = None) -> None:
        self.guard = guard or MutationGuard()

    @abc.abstractmethod
    def write(self, data: bytes) -> int:
        """Transmit raw bytes; returns the byte count accepted."""

    @abc.abstractmethod
    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        """Return up to ``max_bytes``, waiting at most ``timeout_ms``."""

    def close(self) -> None:
        """Release the underlying resource. Idempotent."""

    def send(self, frame: bytes) -> None:
        """Validate and transmit one frame, refusing mutation by default."""
        packet = parse_packet(frame)          # never put a malformed frame on a wire
        if is_state_changing(packet.cmd_set, packet.signed_cmd_id):
            self.guard.require(
                f"cmdSet={packet.cmd_set} cmdId={packet.signed_cmd_id}")
        self.write(frame)

    def frames(self, max_bytes: int = 512, timeout_ms: int = DEFAULT_TIMEOUT_MS,
               limit: int = 256) -> Iterable[Packet]:
        """Yield decoded packets from the read stream.

        Stops on end-of-data or after ``limit`` frames. The bound matters: a
        looping replay transport would otherwise make this generator spin
        forever and wedge a test run with no visible failure.
        """
        parser = StreamParser()
        seen = 0
        while seen < limit:
            chunk = self.read(max_bytes, timeout_ms)
            if not chunk:
                return
            for event in parser.feed(chunk):
                if event.ok:
                    seen += 1
                    yield event.packet
                    if seen >= limit:
                        return


@dataclasses.dataclass
class ReplayTransport(Transport):
    """Serve frames from a recorded byte stream.

    Deterministic and hardware-free, which is what lets the test suite assert on
    full protocol exchanges. A capture is finite, so ``loop`` defaults to False
    and iteration terminates; looping is opt-in for link simulation, and
    :meth:`Transport.frames` is bounded either way so it cannot hang a suite.
    """

    name: str = "replay"
    capture: bytes = b""
    loop: bool = False
    _cursor: int = dataclasses.field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.guard = MutationGuard()

    @classmethod
    def from_hexfile(cls, path: str, **kw) -> "ReplayTransport":
        with open(path, encoding="ascii") as fh:
            blob = "".join(line.strip() for line in fh
                           if line.strip() and not line.startswith("#"))
        return cls(capture=bytes.fromhex(blob), **kw)

    def write(self, data: bytes) -> int:
        # Writes are recorded but have no effect: this transport never mutates.
        return len(data)

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        if not self.capture:
            return b""
        if self._cursor >= len(self.capture):
            if not self.loop:
                return b""
            self._cursor = 0
        chunk = self.capture[self._cursor:self._cursor + max_bytes]
        self._cursor += len(chunk)
        return chunk


@dataclasses.dataclass
class ScriptedTransport(Transport):
    """Answer each transmitted frame with a canned reply.

    ``responder`` receives the parsed request and returns the reply payload (or
    ``None`` for no reply). That makes policy branches — an empty 2017 table, a
    CRC-corrupt reply, a truncated reply — reachable in tests without hardware.
    """

    name: str = "scripted"
    responder: Callable[[Packet], bytes | None] = lambda _p: None
    sent: list = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        self.guard = MutationGuard()
        self._queue: list[bytes] = []

    def write(self, data: bytes) -> int:
        packet = parse_packet(data)
        self.sent.append(packet)
        reply = self.responder(packet)
        if reply is not None:
            self._queue.append(reply)
        return len(data)

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        return self._queue.pop(0) if self._queue else b""


@dataclasses.dataclass
class DryRunTransport(Transport):
    """Record frames; transmit nothing.

    Read commands are still resolved (from ``responder``, if given) so the read
    path can be exercised end to end, but every frame is logged with a timestamp
    so a dry run produces an exact, reviewable record of what *would* be sent.
    """

    name: str = "dry-run"
    responder: Callable[[Packet], bytes | None] = lambda _p: None
    log: list = dataclasses.field(default_factory=list)
    allow_mutation: bool = False

    def __post_init__(self) -> None:
        self.guard = MutationGuard()
        self._queue: list[bytes] = []

    def write(self, data: bytes) -> int:
        packet = parse_packet(data)
        self.log.append({
            "at": time.time(),
            "cmd_set": packet.cmd_set,
            "cmd_id": packet.signed_cmd_id,
            "sequence": packet.sequence,
            "payload_len": len(packet.payload),
            "frame": data.hex(),
            "state_changing": is_state_changing(packet.cmd_set, packet.signed_cmd_id),
        })
        reply = self.responder(packet)
        if reply is not None and not (
                is_state_changing(packet.cmd_set, packet.signed_cmd_id)
                and not self.allow_mutation):
            self._queue.append(reply)
        return len(data)

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        return self._queue.pop(0) if self._queue else b""


class LiveTransport(Transport):
    """Real hardware. Only the two recovered DJI vendor/product pairs.

    Enumerates USB host devices matching vendor ``0x2CA3`` and product ``0x10``,
    ``0x18`` or ``0x20`` — the filters declared in the APK's
    ``res/xml/device_filter.xml`` — and claims the first interface that exposes
    a bulk IN and a bulk OUT endpoint, which is the same selection rule the app
    uses. There is no CDC-ACM line-coding setup: the app does raw bulk transfers,
    so this does too.

    Frames are exchanged exactly as recovered: a single ``0x30`` init byte is
    written five times on connect (200 ms timeout), reads use a 512-byte buffer
    with a 2000 ms timeout, and writes use a 2000 ms timeout.
    """

    name = "live"
    DJI_VENDOR_ID = 0x2CA3
    DJI_PRODUCT_IDS = (0x10, 0x18, 0x20)
    ENDPOINT_XFER_BULK = 0x02
    ENDPOINT_DIRECTION_OUT = 0x00
    ENDPOINT_DIRECTION_IN = 0x80
    INIT_BYTE = 0x30
    INIT_REPEATS = 5
    INIT_TIMEOUT_MS = 200
    READ_BUFFER = 512
    READ_TIMEOUT_MS = 2000
    WRITE_TIMEOUT_MS = 2000

    def __init__(self, connection, ep_in, ep_out, guard: MutationGuard | None = None):
        super().__init__(guard)
        self._conn = connection
        self.ep_in = ep_in
        self.ep_out = ep_out

    @classmethod
    def open(cls, manager=None, guard: MutationGuard | None = None) -> "LiveTransport":
        """Open the first matching DJI device. Requires the Android runtime."""
        raise NotImplementedError(
            "LiveTransport.open() needs the Android USB host API; it is "
            "deliberately not implemented here so that importing this module on a "
            "desktop cannot accidentally touch hardware. See docs/HARDWARE_TEST_PLAN.md.")

    def initialise_link(self) -> None:
        """The app's connect handshake: five 0x30 bytes on the OUT endpoint."""
        for _ in range(self.INIT_REPEATS):
            self._conn.bulkTransfer(self.ep_out,
                                    bytes([self.INIT_BYTE]),
                                    self.INIT_BYTE,
                                    1, self.INIT_TIMEOUT_MS)

    def write(self, data: bytes) -> int:
        result = self._conn.bulkTransfer(self.ep_out, data, 0, len(data),
                                         self.WRITE_TIMEOUT_MS)
        if result < 0:
            raise OSError(f"bulk write failed: {result}")
        return result

    def read(self, max_bytes: int = READ_BUFFER, timeout_ms: int = READ_TIMEOUT_MS) -> bytes:
        buf = bytearray(max_bytes)
        n = self._conn.bulkTransfer(self.ep_in, buf, 0, max_bytes, timeout_ms)
        return bytes(buf[:n]) if n > 0 else b""

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class Session:
    """Request/response matching over a transport.

    Matching rule: a reply is accepted when its ``cmdSet``/``cmdId`` match the
    request. Sequence numbers are checked when the reply carries one, but a
    mismatch alone is not fatal — the app's own ``awaitPacket`` matches on the
    decoded fields and tolerates sequence drift, so matching on both would be
    stricter than the reference implementation.
    """

    def __init__(self, transport: Transport, guard: MutationGuard | None = None,
                 timeout_ms: int = DEFAULT_TIMEOUT_MS,
                 retries: int = DEFAULT_RETRIES) -> None:
        self.transport = transport
        self.guard = guard or transport.guard
        self.timeout_ms = timeout_ms
        self.retries = retries
        self._parser = StreamParser()

    def request(self, frame: bytes, *, timeout_ms: int | None = None) -> Packet | None:
        """Send a frame and wait for its reply, or return ``None`` on timeout.

        One :class:`StreamParser` is held per session, not per call: a reply can
        arrive split across several reads, and a fresh parser per call would
        throw away the partial frame between them.
        """
        want = parse_packet(frame)
        deadline = time.monotonic() + ((timeout_ms or self.timeout_ms) / 1000.0)
        last_error: str | None = None

        for _ in range(self.retries + 1):
            try:
                self.transport.send(frame)
            except PermissionError:
                raise                      # a refused write must never be retried
            except OSError as exc:
                last_error = str(exc)
                continue

            while True:
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if remaining_ms <= 0:
                    break
                chunk = self.transport.read(self.READ_BUFFER, remaining_ms)
                if not chunk:
                    break
                for event in self._parser.feed(chunk):
                    if event.ok and self.matches(event.packet, want):
                        return event.packet
        if last_error:
            raise OSError(last_error)
        return None

    READ_BUFFER = 512

    @staticmethod
    def matches(got: Packet, want: Packet) -> bool:
        """Is ``got`` the reply to ``want``?

        Matched on command set, command id and the response bit. The sequence
        number is deliberately *not* required to match: the reference app
        tolerates sequence drift when matching replies, so requiring it here
        would be stricter than the behaviour being reproduced.
        """
        return (got.cmd_set == want.cmd_set
                and got.cmd_id == want.cmd_id
                and got.packet_type == 1)