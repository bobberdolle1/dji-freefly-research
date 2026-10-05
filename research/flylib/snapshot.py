"""Parameter snapshots: capture, export to JSON, import, and replay.

This is the end of the read path the project exists to support:

    device -> protocol selection -> parameter enumeration -> snapshot JSON

A snapshot is a portable, self-describing record of one aircraft's FC parameter
table. It is **read-only by construction**: it records values, and applying one
would be a state-changing operation, so no apply/diff-to-device path exists here.
:meth:`Snapshot.diff` exists to compare two snapshots, not to write one back.

Design notes
------------
* Values are stored **twice** - the exact little-endian ``raw`` bytes and the
  decoded number. The raw bytes are the source of truth; the decoded value is
  derived and may be ``None`` when the payload is short for its type. Keeping
  both means a future decoder change cannot corrupt an existing snapshot.
* Every entry records its ``type_id`` as the *wire* value, not the enum name,
  so a snapshot does not depend on this library's enum ordering staying stable.
* Unknown keys on import are preserved under ``extra`` rather than dropped, so a
  snapshot written by a newer tool round-trips through an older one.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
from typing import Any, Iterable, Sequence

from .params import ParamType, decode_value

SNAPSHOT_VERSION = 1


class SnapshotError(ValueError):
    """Raised when a snapshot document cannot be understood."""


@dataclasses.dataclass(frozen=True)
class SnapshotParameter:
    table: int
    index: int
    type_id: int
    name: str
    raw: bytes

    @property
    def type(self) -> ParamType:
        try:
            return ParamType(self.type_id)
        except ValueError as exc:
            raise SnapshotError(
                f"{self.name!r}: type id {self.type_id} is not a known FC type") from exc

    @property
    def decoded(self):
        """The decoded value, or ``None`` if the payload is too short."""
        return decode_value(self.raw, self.type)

    def to_dict(self) -> dict[str, Any]:
        return {"table": self.table, "index": self.index, "type_id": self.type_id,
                "name": self.name, "raw": self.raw.hex()}

    @classmethod
    def from_dict(cls, data: Any) -> "SnapshotParameter":
        if not isinstance(data, dict):
            raise SnapshotError(f"parameter entry must be an object, got {type(data).__name__}")
        missing = [k for k in ("table", "index", "type_id", "name", "raw") if k not in data]
        if missing:
            raise SnapshotError(f"parameter entry missing {missing}")
        try:
            raw = bytes.fromhex(str(data["raw"]))
        except ValueError as exc:
            raise SnapshotError(f"raw is not valid hex: {data['raw']!r}") from exc
        return cls(table=int(data["table"]), index=int(data["index"]),
                   type_id=int(data["type_id"]), name=str(data["name"]), raw=raw)


@dataclasses.dataclass(frozen=True)
class Snapshot:
    """One aircraft's parameter table at one moment."""

    codename: str = "unknown"
    firmware: str | None = None
    protocol: str = "2017"
    captured_at: str | None = None
    parameters: tuple[SnapshotParameter, ...] = ()
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "snapshot_version": SNAPSHOT_VERSION,
            "codename": self.codename,
            "firmware": self.firmware,
            "protocol": self.protocol,
            "captured_at": self.captured_at,
            "parameter_count": len(self.parameters),
            "parameters": [p.to_dict() for p in self.parameters],
        }
        if self.extra:
            doc["extra"] = self.extra
        return doc

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def from_dict(cls, doc: Any) -> "Snapshot":
        if not isinstance(doc, dict):
            raise SnapshotError(f"snapshot must be an object, got {type(doc).__name__}")
        version = doc.get("snapshot_version", SNAPSHOT_VERSION)
        if version != SNAPSHOT_VERSION:
            raise SnapshotError(
                f"snapshot_version {version} is not supported by this build "
                f"(expected {SNAPSHOT_VERSION})")
        params = doc.get("parameters", [])
        if not isinstance(params, list):
            raise SnapshotError("'parameters' must be a list")
        known = {"snapshot_version", "codename", "firmware", "protocol",
                 "captured_at", "parameter_count", "parameters", "extra"}
        return cls(
            codename=str(doc.get("codename", "unknown")),
            firmware=doc.get("firmware"),
            protocol=str(doc.get("protocol", "2017")),
            captured_at=doc.get("captured_at"),
            parameters=tuple(SnapshotParameter.from_dict(p) for p in params),
            extra=dict(doc.get("extra") or {}),
            **{},  # keep unknown top-level keys out of the dataclass
        ) if set(doc) <= known else cls(
            codename=str(doc.get("codename", "unknown")),
            firmware=doc.get("firmware"),
            protocol=str(doc.get("protocol", "2017")),
            captured_at=doc.get("captured_at"),
            parameters=tuple(SnapshotParameter.from_dict(p) for p in params),
            extra={**dict(doc.get("extra") or {}),
                   **{k: v for k, v in doc.items() if k not in known}},
        )

    @classmethod
    def from_json(cls, text: str) -> "Snapshot":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SnapshotError(f"snapshot is not valid JSON: {exc}") from exc
        return cls.from_dict(doc)

    # -- convenience ----------------------------------------------------

    def __len__(self) -> int:
        return len(self.parameters)

    def by_name(self) -> dict[str, SnapshotParameter]:
        return {p.name: p for p in self.parameters}

    def addresses(self) -> set[tuple[int, int]]:
        return {(p.table, p.index) for p in self.parameters}

    def decode_all(self) -> dict[str, Any]:
        """Name -> decoded value, for human-facing comparison."""
        out: dict[str, Any] = {}
        for p in self.parameters:
            decoded = p.decoded
            out[p.name] = None if decoded.value is None else decoded.value
        return out

    def diff(self, other: "Snapshot") -> list[dict[str, Any]]:
        """Compare by parameter **name**; returns only entries that differ.

        Matching is by name, not by ``(table, index)``, because the index space
        is model-specific and may be laid out differently on another airframe.
        """
        mine, theirs = self.by_name(), other.by_name()
        changes: list[dict[str, Any]] = []
        for name in sorted(set(mine) | set(theirs)):
            a, b = mine.get(name), theirs.get(name)
            if a is None:
                changes.append({"name": name, "kind": "added"})
            elif b is None:
                changes.append({"name": name, "kind": "removed"})
            elif a.raw != b.raw:
                changes.append({
                    "name": name, "kind": "changed",
                    "a": {"table": a.table, "index": a.index,
                          "raw": a.raw.hex(), "value": a.decoded.value},
                    "b": {"table": b.table, "index": b.index,
                          "raw": b.raw.hex(), "value": b.decoded.value},
                })
        return changes


def build_snapshot(codename: str, entries: Iterable[tuple[int, int, str, bytes]],
                   *, protocol: str = "2017", firmware: str | None = None,
                   captured_at: str | None = None,
                   type_of: dict[str, int] | None = None) -> Snapshot:
    """Assemble a snapshot from ``(table, index, name, raw)`` tuples.

    ``type_of`` maps parameter name to wire type id; names absent from it get
    type ``UINT32`` only if the payload is 4 bytes, otherwise the snapshot
    records the size-derived guess and the caller is expected to supply the
    mapping. Prefer passing the real catalogue types.
    """
    params = []
    for table, index, name, raw in entries:
        if type_of and name in type_of:
            type_id = type_of[name]
        else:
            type_id = {1: ParamType.UINT8, 2: ParamType.UINT16,
                       4: ParamType.UINT32, 8: ParamType.DOUBLE}.get(len(raw), 0)
        params.append(SnapshotParameter(table=table, index=index,
                                        type_id=int(type_id), name=name, raw=raw))
    return Snapshot(codename=codename, firmware=firmware, protocol=protocol,
                    captured_at=captured_at, parameters=tuple(params))


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()