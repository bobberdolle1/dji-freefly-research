"""Parameter snapshot: export, import, round-trip and diff.

The snapshot format is the end of the read path — device to protocol selection to
parameter enumeration to JSON — so its tests are about durability of evidence
rather than about the protocol.

Two properties matter most and are asserted explicitly:

* **Raw bytes are authoritative.** A snapshot stores both the little-endian
  payload and the decoded value; the value is derived. If a future decoder
  change breaks decoding, existing snapshots must still round-trip byte-exactly.
* **A snapshot cannot cause a write.** There is deliberately no apply/push API.
  The module exposes capture, serialise, deserialise and compare, and nothing
  that transmits.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research"))

from flylib.params import ParamType  # noqa: E402
from flylib.snapshot import (SNAPSHOT_VERSION, Snapshot, SnapshotError,  # noqa: E402
                             SnapshotParameter, build_snapshot, utc_now)

ENTRIES = [
    (0, 687, "ce_country_type", bytes.fromhex("05000000")),      # UINT32 -> 5
    (0, 654, "g_config.flying_limit.max_radius", bytes.fromhex("5a00")),  # UINT16
    (1, 12, "total_distance", bytes.fromhex("0000c03f")),        # FLOAT -> 1.5
    (2, 7, "fault_code", bytes.fromhex("ff")),                   # INT8 -> -1
]


def make() -> Snapshot:
    return build_snapshot("M300RTK", ENTRIES, firmware="03.00.0100",
                          captured_at="2026-10-05T00:00:00+00:00",
                          type_of={"ce_country_type": int(ParamType.UINT32),
                                   "g_config.flying_limit.max_radius": int(ParamType.UINT16),
                                   "total_distance": int(ParamType.FLOAT),
                                   "fault_code": int(ParamType.INT8)})


# --------------------------------------------------------------------------
# Round-trip
# --------------------------------------------------------------------------

def test_snapshot_round_trips_exactly():
    original = make()
    restored = Snapshot.from_json(original.to_json())
    assert restored.codename == original.codename
    assert restored.firmware == original.firmware
    assert restored.protocol == original.protocol
    assert restored.captured_at == original.captured_at
    assert len(restored) == len(original)
    for a, b in zip(original.parameters, restored.parameters):
        assert (a.table, a.index, a.type_id, a.name, a.raw) == \
               (b.table, b.index, b.type_id, b.name, b.raw)


def test_json_is_deterministic():
    """Same snapshot, same bytes - otherwise diffs over exports are noise."""
    assert make().to_json() == make().to_json()


def test_document_shape_is_self_describing():
    doc = json.loads(make().to_json())
    assert doc["snapshot_version"] == SNAPSHOT_VERSION
    assert doc["codename"] == "M300RTK"
    assert doc["parameter_count"] == len(ENTRIES)
    assert doc["parameters"][0]["raw"] == "05000000"
    assert set(doc["parameters"][0]) == {"table", "index", "type_id", "name", "raw"}


# --------------------------------------------------------------------------
# Decoding
# --------------------------------------------------------------------------

def test_values_decode_through_the_type_table():
    decoded = make().decode_all()
    assert decoded["ce_country_type"] == 5
    assert decoded["g_config.flying_limit.max_radius"] == 90
    assert decoded["total_distance"] == pytest.approx(1.5)
    assert decoded["fault_code"] == -1


def test_raw_bytes_survive_even_when_the_value_is_underivable():
    """A payload too short for its type must still round-trip byte-exactly."""
    short = SnapshotParameter(table=0, index=1, type_id=int(ParamType.UINT32),
                              name="truncated", raw=b"\x01\x02")
    snap = Snapshot(parameters=(short,))
    back = Snapshot.from_json(snap.to_json()).parameters[0]
    assert back.raw == b"\x01\x02"
    assert back.decoded.value is None


def test_unknown_type_id_is_rejected_on_decode():
    bad = SnapshotParameter(table=0, index=0, type_id=99, name="mystery", raw=b"\x01")
    with pytest.raises(SnapshotError, match="not a known FC type"):
        _ = bad.type


# --------------------------------------------------------------------------
# Diff
# --------------------------------------------------------------------------

def test_identical_snapshots_diff_to_nothing():
    assert make().diff(make()) == []


def test_diff_detects_a_changed_value():
    changed = build_snapshot(
        "M300RTK",
        [(0, 687, "ce_country_type", bytes.fromhex("0a000000"))] +
        [e for e in ENTRIES if e[2] != "ce_country_type"],
        type_of={e[2]: int(ParamType.UINT32 if e[2] == "ce_country_type" else 8)
                 for e in ENTRIES})
    deltas = make().diff(changed)
    assert [d["name"] for d in deltas] == ["ce_country_type"]
    assert deltas[0]["kind"] == "changed"
    assert deltas[0]["a"]["value"] == 5
    assert deltas[0]["b"]["value"] == 10


def test_diff_matches_by_name_not_by_address():
    """Index space is model-specific, so a moved parameter is not a change."""
    moved = build_snapshot(
        "OTHER",
        [(9, 400, name, raw) for _t, _i, name, raw in ENTRIES],
        type_of={e[2]: p.type_id for e, p in
                 zip(ENTRIES, make().parameters)})
    assert make().diff(moved) == []


def test_diff_reports_added_and_removed():
    fewer = build_snapshot("M300RTK", ENTRIES[:2],
                           type_of={"ce_country_type": int(ParamType.UINT32),
                                    "g_config.flying_limit.max_radius": int(ParamType.UINT16)})
    kinds = {d["name"]: d["kind"] for d in fewer.diff(make())}
    assert kinds == {"total_distance": "added", "fault_code": "added"}


# --------------------------------------------------------------------------
# Malformed input
# --------------------------------------------------------------------------

def test_invalid_json_is_reported_clearly():
    with pytest.raises(SnapshotError, match="not valid JSON"):
        Snapshot.from_json("{not json")


def test_non_object_document_is_rejected():
    with pytest.raises(SnapshotError, match="must be an object"):
        Snapshot.from_json("[]")


def test_unsupported_version_is_rejected():
    doc = make().to_dict()
    doc["snapshot_version"] = 99
    with pytest.raises(SnapshotError, match="not supported"):
        Snapshot.from_dict(doc)


def test_parameters_must_be_a_list():
    doc = make().to_dict()
    doc["parameters"] = {"a": 1}
    with pytest.raises(SnapshotError, match="must be a list"):
        Snapshot.from_dict(doc)


def test_parameter_missing_a_key_is_rejected():
    entry = make().parameters[0].to_dict()
    del entry["raw"]
    with pytest.raises(SnapshotError, match="missing"):
        SnapshotParameter.from_dict(entry)


def test_parameter_raw_must_be_hex():
    entry = make().parameters[0].to_dict()
    entry["raw"] = "zzzz"
    with pytest.raises(SnapshotError, match="not valid hex"):
        SnapshotParameter.from_dict(entry)


def test_unknown_top_level_keys_are_preserved_not_dropped():
    doc = make().to_dict()
    doc["airframe_serial"] = "1581F..."
    restored = Snapshot.from_dict(doc)
    assert restored.extra["airframe_serial"] == "1581F..."
    assert restored.codename == "M300RTK"


# --------------------------------------------------------------------------
# Safety
# --------------------------------------------------------------------------

def test_snapshot_module_exposes_no_transmitting_api():
    """A snapshot must not be able to change aircraft state.

    Guards against a future contributor adding an apply/push method to what is
    meant to be a pure data format.
    """
    import flylib.snapshot as mod
    forbidden = ("write", "apply", "push", "send", "commit", "upload", "flash")
    for name in dir(mod):
        if name.startswith("_"):
            continue
        assert not any(word in name.lower() for word in forbidden), \
            f"snapshot module exposes a transmitting-looking name: {name}"


def test_utc_now_is_iso_and_timezone_aware():
    stamp = utc_now()
    assert stamp.endswith("+00:00")
    assert "T" in stamp
