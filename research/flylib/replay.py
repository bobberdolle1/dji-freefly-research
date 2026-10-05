"""Capture a snapshot from a device, and replay one without a device.

This closes the loop the project exists to support:

    device -> protocol selection -> parameter enumeration -> snapshot JSON
           -> replay (no device, fully deterministic)

Two halves:

:class:`ReplayParameterSource`
    The aircraft-facing protocol operations the reader needs, expressed in terms
    of :mod:`flylib.selection`. It is a narrow Protocol so a real implementation
    can be bound to :class:`flylib.Session` and a test one to canned bytes.

:func:`capture`
    Runs protocol selection and enumeration and returns a
    :class:`~flylib.snapshot.Snapshot`. Read-only: it calls nothing but read
    commands, and any mutating frame is refused by the transport's guard.

:class:`SnapshotReplayTransport`
    Turns a snapshot back into replies. Replaying a capture against this
    transport exercises the whole reader path with no hardware and no network,
    which is what makes the read path testable at all.

The replay is deliberately a *fixture*, not a simulator: it answers what the
capture said, and nothing more. It cannot make an aircraft do anything, because
there is no aircraft behind it.

Index note
----------
``getTableAttribs2017(tableNo)`` returns a **count**, so the 2017 protocol
enumerates ``range(count)`` per table and its indices are dense per table. That
is why the tests here use 0,1 rather than the sparse indices in
``assets/params_catalog.json``; the join between that flat catalogue space and
per-table addressing is still untraced and is recorded as such in
``docs/PARAMETERS.md``.
"""
from __future__ import annotations

import dataclasses
from typing import Protocol

from .selection import ACTIVE_PROTOCOL, IndexMapStore, ParameterSource, ScanResult, select_parameters
from .snapshot import Snapshot, build_snapshot, utc_now
from .transport import Transport


class SnapshotSource(ParameterSource, Protocol):
    """Read-only protocol operations, on top of the 2017 selection surface."""

    def version(self) -> tuple[str, str]:
        """``(codename, firmware)`` from device info."""


@dataclasses.dataclass
class ReplayParameterSource:
    """A :class:`SnapshotSource` backed by an in-memory table.

    Used to replay a capture without a device, and by tests to drive selection
    branches deterministically. ``names`` is optional: without it, captured
    parameters are labelled by address.
    """

    codename: str = "unknown"
    firmware: str = "unknown"
    table_counts: dict[int, int] = dataclasses.field(default_factory=dict)
    values: dict[tuple[int, int], bytes] = dataclasses.field(default_factory=dict)
    types: dict[str, int] = dataclasses.field(default_factory=dict)
    silent_tables: set[int] = dataclasses.field(default_factory=set)
    reads: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    names: dict[tuple[int, int], str] = dataclasses.field(default_factory=dict)

    def version(self) -> tuple[str, str]:
        return self.codename, self.firmware

    def table_attribs_2017(self, table_no: int) -> int | None:
        if table_no in self.silent_tables:
            return None
        return self.table_counts.get(table_no, 0)

    def read_2017(self, table_no: int, param_index: int) -> bytes | None:
        self.reads.append((table_no, param_index))
        return self.values.get((table_no, param_index))


def source_from_snapshot(snapshot: Snapshot) -> ReplayParameterSource:
    """Rebuild a readable table from a snapshot, for replay and comparison.

    The address-to-name map is restored as well as the values and types.
    Without it a replayed capture falls back to ``tableN.indexM`` labels, which
    also loses the type lookup — and a size-based type guess decodes a 4-byte
    float as an integer. Restoring names is what makes capture a true fixed
    point, and there is a test that asserts exactly that.
    """
    counts: dict[int, int] = {}
    values: dict[tuple[int, int], bytes] = {}
    types: dict[str, int] = {}
    names: dict[tuple[int, int], str] = {}
    for p in snapshot.parameters:
        counts[p.table] = max(counts.get(p.table, 0), p.index + 1)
        values[(p.table, p.index)] = p.raw
        types[p.name] = p.type_id
        names[(p.table, p.index)] = p.name
    source = ReplayParameterSource(codename=snapshot.codename,
                                   firmware=snapshot.firmware or "unknown",
                                   table_counts=counts, values=values, types=types)
    source.names = names
    return source


def capture(source: SnapshotSource,
            index_maps: IndexMapStore | None = None,
            tables: tuple[int, ...] = (0,),
            force_full_scan: bool = False,
            captured_at: str | None = None,
            on_diagnostic=None) -> tuple[Snapshot, ScanResult]:
    """Enumerate an aircraft's parameters and package them as a snapshot.

    Returns the snapshot alongside the raw :class:`ScanResult`, because the
    diagnostics matter: a table that reported zero parameters and a table that
    never answered look identical in the snapshot and are only distinguishable
    in the scan record.
    """
    codename, firmware = source.version()
    result = select_parameters(source, codename, index_maps=index_maps,
                               force_full_scan=force_full_scan, tables=tables,
                               on_diagnostic=on_diagnostic)
    entries = []
    for table, index in result.index_map:
        raw = source.read_2017(table, index)
        if raw is None:
            continue
        entries.append((table, index, _name_for(source, table, index), raw))
    snapshot = build_snapshot(codename, entries, protocol=ACTIVE_PROTOCOL,
                              firmware=firmware,
                              captured_at=captured_at or utc_now(),
                              type_of=getattr(source, "types", None))
    return snapshot, result


def _name_for(source: SnapshotSource, table: int, index: int) -> str:
    names = getattr(source, "names", None)
    if isinstance(names, dict) and (table, index) in names:
        return names[(table, index)]
    return f"table{table}.index{index}"


class SnapshotReplayTransport(Transport):
    """Serve replies derived from a snapshot. Transmits nothing.

    Any frame sent to this transport is recorded and answered only if the
    snapshot contains a matching parameter. It is a fixture for exercising the
    read path, not a device model.
    """

    name = "snapshot-replay"

    def __init__(self, snapshot: Snapshot) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.index_map = {(p.table, p.index): p for p in snapshot.parameters}
        self.sent: list[bytes] = []
        self._pending: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.sent.append(bytes(data))
        return len(data)

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        return self._pending.pop(0) if self._pending else b""

    def reply_for(self, payload: bytes):
        """Look up a 2017 read payload ``<table><0><index>`` in the snapshot."""
        if len(payload) >= 6:
            table = int.from_bytes(payload[0:2], "little")
            index = int.from_bytes(payload[4:6], "little")
            return self.index_map.get((table, index))
        return None

    def table_count(self, table_no: int) -> int:
        """Declared parameter count for a table, or 0 if the aircraft has none."""
        members = [p for p in self.snapshot.parameters if p.table == table_no]
        return (max(p.index for p in members) + 1) if members else 0


def snapshot_document(snapshot: Snapshot) -> str:
    """Serialise a snapshot — the artefact the whole read path exists to produce."""
    return snapshot.to_json()