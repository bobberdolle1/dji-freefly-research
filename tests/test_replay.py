"""Capture and replay: the APK-independent read path, end to end.

The property under test is that a capture survives a full round trip through
JSON and comes back byte-identical, with no device, no network and no drone
involved. That is what makes the read path testable at all.

Note on indices: ``getTableAttribs2017(tableNo)`` returns a *count*, so the
2017 protocol enumerates ``range(count)`` per table and its indices are dense.
That is why these fixtures use 0,1 rather than the sparse catalogue-style
indices in ``assets/params_catalog.json``; the join between that flat catalogue
space and the per-table addresses is still untraced and is documented as such
in ``docs/PARAMETERS.md``.

Also asserted: capture is read-only.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research"))

from flylib.commands import read_param_value_2017, write_param_value_2017  # noqa: E402
from flylib.guard import MutationNotAllowed, is_state_changing  # noqa: E402
from flylib.params import ParamType  # noqa: E402
from flylib.replay import (ReplayParameterSource, SnapshotReplayTransport,  # noqa: E402
                           capture, source_from_snapshot, snapshot_document)
from flylib.snapshot import Snapshot  # noqa: E402

# (table, index) -> (name, raw, type)
LAYOUT = [
    (0, 0, "ce_country_type", bytes.fromhex("05000000"), ParamType.UINT32),
    (0, 1, "g_config.flying_limit.max_radius", bytes.fromhex("5a00"), ParamType.UINT16),
    (1, 0, "total_distance", bytes.fromhex("0000c03f"), ParamType.FLOAT),
    (1, 1, "gps_lon", bytes.fromhex("0000000000000840"), ParamType.DOUBLE),
]
NAMES = {name: int(t) for _t, _i, name, _r, t in LAYOUT}


def populated() -> ReplayParameterSource:
    source = ReplayParameterSource(
        codename="M300RTK", firmware="03.00.0100",
        table_counts={0: 2, 1: 2},
        values={(t, i): raw for t, i, _n, raw, _ty in LAYOUT},
        types=dict(NAMES))
    source.names = {(t, i): n for t, i, n, _r, _ty in LAYOUT}
    return source


def test_capture_enumerates_every_declared_parameter():
    snap, scan = capture(populated(), tables=(0, 1))
    assert snap.codename == "M300RTK"
    assert snap.firmware == "03.00.0100"
    assert snap.protocol == "2017"
    assert len(snap) == 4
    assert scan.protocol == "2017"
    assert scan.skipped_tables == []


def test_capture_uses_supplied_names():
    snap, _ = capture(populated(), tables=(0, 1))
    assert set(snap.by_name()) == set(NAMES)


def test_capture_decodes_through_the_catalogue_types():
    snap, _ = capture(populated(), tables=(0, 1))
    decoded = snap.decode_all()
    assert decoded["ce_country_type"] == 5
    assert decoded["g_config.flying_limit.max_radius"] == 90
    assert decoded["total_distance"] == pytest.approx(1.5)
    assert decoded["gps_lon"] == pytest.approx(3.0)


def test_capture_is_read_only():
    """No frame the reader emits may be state-changing."""
    for frame in (read_param_value_2017(0, 1, 1), read_param_value_2017(1, 12, 2)):
        cmd_set, cmd_id = frame[9], frame[10]
        signed = cmd_id - 0x100 if cmd_id > 0x7F else cmd_id
        assert not is_state_changing(cmd_set, signed)


def test_aircraft_with_no_tables_yields_an_empty_snapshot():
    source = ReplayParameterSource(codename="UNKNOWN", table_counts={})
    snap, scan = capture(source, tables=(0,))
    assert len(snap) == 0
    assert scan.protocol == "2017"
    assert any("empty or no response" in d for d in scan.diagnostics)


def test_silent_table_is_reported_as_skipped():
    source = ReplayParameterSource(codename="X", table_counts={0: 1, 1: 1},
                                  values={(0, 0): b"\x01"}, silent_tables={1})
    snap, scan = capture(source, tables=(0, 1))
    assert len(snap) == 1
    assert [t.table_no for t in scan.skipped_tables] == [1]


# --------------------------------------------------------------------------
# Round trip through JSON
# --------------------------------------------------------------------------

def test_snapshot_survives_a_full_round_trip():
    original, _ = capture(populated(), tables=(0, 1),
                          captured_at="2026-10-05T12:00:00+00:00")
    text = snapshot_document(original)
    restored = Snapshot.from_json(text)
    assert restored.to_json() == text
    assert [p.raw for p in restored.parameters] == [p.raw for p in original.parameters]
    assert restored.codename == original.codename
    assert restored.firmware == original.firmware


def test_replayed_capture_reproduces_the_original():
    """capture -> JSON -> source -> capture must be a fixed point."""
    first, _ = capture(populated(), tables=(0, 1))
    second, _ = capture(source_from_snapshot(Snapshot.from_json(
        snapshot_document(first))), tables=(0, 1))
    assert second.decode_all() == first.decode_all()
    assert [(p.table, p.index, p.raw) for p in second.parameters] == \
           [(p.table, p.index, p.raw) for p in first.parameters]
    assert first.diff(second) == []


def test_snapshot_is_a_fixed_point_of_capture():
    once, _ = capture(populated(), tables=(0, 1))
    twice, _ = capture(source_from_snapshot(once), tables=(0, 1))
    thrice, _ = capture(source_from_snapshot(twice), tables=(0, 1))
    assert twice.to_json() == thrice.to_json()


# --------------------------------------------------------------------------
# Replay transport
# --------------------------------------------------------------------------

def test_replay_transport_answers_a_read_by_address():
    snap, _ = capture(populated(), tables=(0, 1))
    transport = SnapshotReplayTransport(snap)
    hit = transport.reply_for(bytes.fromhex("0000" "0000" "0000"))
    assert hit is not None
    assert hit.name == "ce_country_type"
    assert hit.raw == bytes.fromhex("05000000")


def test_replay_transport_returns_none_for_an_unknown_address():
    snap, _ = capture(populated(), tables=(0, 1))
    transport = SnapshotReplayTransport(snap)
    assert transport.reply_for(bytes.fromhex("0900" "0000" "0100")) is None
    assert transport.reply_for(b"\x00") is None


def test_replay_transport_reports_table_counts():
    snap, _ = capture(populated(), tables=(0, 1))
    transport = SnapshotReplayTransport(snap)
    assert transport.table_count(0) == 2
    assert transport.table_count(1) == 2
    assert transport.table_count(5) == 0


def test_replay_transport_transmits_nothing():
    snap, _ = capture(populated(), tables=(0, 1))
    transport = SnapshotReplayTransport(snap)
    transport.write(b"\x00" * 17)
    assert transport.read(512, 10) == b""       # nothing is ever produced
    assert len(transport.sent) == 1             # but the attempt was recorded


def test_replay_transport_refuses_a_mutating_frame():
    snap, _ = capture(populated(), tables=(0, 1))
    transport = SnapshotReplayTransport(snap)
    with pytest.raises(MutationNotAllowed):
        transport.send(write_param_value_2017(0, 0, b"\x00", 1))
    assert transport.sent == [], "a refused frame must not reach write()"
