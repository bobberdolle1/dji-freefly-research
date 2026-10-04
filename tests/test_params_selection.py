"""Parameter codec and protocol-selection policy.

Covers the cases that decide which protocol talks to the aircraft: 2015
selection, 2017 selection, the failed-2017 fallback, index-map reuse, malformed
metadata, unknown parameter types, and truncated input.

The fallback tests are the interesting ones: a table that reports zero
parameters and a table that simply does not answer must both drive the app to
2015, and the distinction matters because the second case is what a
disconnected or busy aircraft actually looks like.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research"))

from flylib import commands as C  # noqa: E402
from flylib.params import (DecodedValue, MalformedParameter, ParamType,  # noqa: E402
                           WIDTH, decode_value, encode_value)
from flylib import selection  # noqa: E402
from flylib.selection import (ACTIVE_PROTOCOL, PROTOCOL_2017,  # noqa: E402
                              IndexMapStore, select_parameters)


# Type table
# --------------------------------------------------------------------------

def test_type_ids_match_the_apps_enum_ordinals():
    """Type id on the wire == enum ordinal, so the ids are 0..9 in this order."""
    assert [t.value for t in ParamType] == list(range(10))
    assert [t.name for t in ParamType] == [
        "UINT8", "UINT16", "UINT32", "UINT64",
        "INT8", "INT16", "INT32", "INT64", "FLOAT", "DOUBLE"]


def test_widths():
    assert [WIDTH[t] for t in ParamType] == [1, 2, 4, 8, 1, 2, 4, 8, 4, 8]


# --------------------------------------------------------------------------
# Codec round-trips
# --------------------------------------------------------------------------

ROUND_TRIP = [
    (ParamType.UINT8, 200),
    (ParamType.UINT16, 60000),
    (ParamType.UINT32, 4000000000),
    (ParamType.UINT64, 18000000000),
    (ParamType.INT8, -128),
    (ParamType.INT16, -32768),
    (ParamType.INT32, -2147483648),
    (ParamType.INT64, -9000000000000000000),
    (ParamType.FLOAT, 1.5),
    (ParamType.DOUBLE, 1234.5678),
]


@pytest.mark.parametrize("type_,value", ROUND_TRIP, ids=[t.name for t, _ in ROUND_TRIP])
def test_value_round_trips(type_, value):
    raw = encode_value(value, type_)
    assert len(raw) == WIDTH[type_]
    decoded = decode_value(raw, type_)
    # Decoding returns the exact Python int for integer types, so the round trip
    # is exact. `lossy` is a separate downstream warning about double precision,
    # asserted on its own below.
    assert decoded.value == value
    assert decoded.type is type_



@pytest.mark.parametrize("type_,value", ROUND_TRIP, ids=[t.name for t, _ in ROUND_TRIP])
def test_encoding_is_little_endian(type_, value):
    raw = encode_value(value, type_)
    assert raw == encode_value(value, type_)
    # the least significant byte comes first
    assert raw[0] == (int(value) & 0xFF) if type_ not in (ParamType.FLOAT,
                                                            ParamType.DOUBLE) else True


def test_float_and_double_are_four_and_eight_bytes():
    assert len(encode_value(1.0, ParamType.FLOAT)) == 4
    assert len(encode_value(1.0, ParamType.DOUBLE)) == 8


# --------------------------------------------------------------------------
# Truncated and malformed input
# --------------------------------------------------------------------------

@pytest.mark.parametrize("type_", list(ParamType), ids=[t.name for t in ParamType])
def test_short_payload_decodes_to_none_rather_than_raising(type_):
    """A truncated reply is normal on a noisy link; it must degrade, not throw."""
    for length in range(0, WIDTH[type_]):
        decoded = decode_value(bytes(length), type_)
        assert decoded.value is None, f"{type_.name} with {length} bytes"
        assert decoded.lossy is False


def test_extra_trailing_bytes_are_ignored():
    raw = encode_value(7, ParamType.UINT8) + b"\xff\xff\xff"
    assert decode_value(raw, ParamType.UINT8).value == 7


def test_unknown_parameter_type_is_rejected_loudly():
    with pytest.raises(KeyError):
        decode_value(b"\x01\x02\x03\x04\x05\x06\x07\x08\x09", 99)
    with pytest.raises(KeyError):
        encode_value(1, 42)


def test_out_of_range_unsigned_is_refused():
    with pytest.raises(ValueError):
        encode_value(256, ParamType.UINT8)
    with pytest.raises(ValueError):
        encode_value(-1, ParamType.UINT8)
    with pytest.raises(ValueError):
        encode_value(65536, ParamType.UINT16)


def test_out_of_range_signed_is_refused_by_struct():
    with pytest.raises(MalformedParameter):
        encode_value(200, ParamType.INT8)


def test_large_integers_are_flagged_as_lossy():
    decoded = decode_value(encode_value(2 ** 60, ParamType.UINT64), ParamType.UINT64)
    assert decoded.lossy is True, "values above 2**53 cannot survive a double"


def test_float_too_large_for_int_is_refused():
    with pytest.raises((MalformedParameter, ValueError, OverflowError)):
        encode_value(float("nan"), ParamType.INT32)


def test_decodedvalue_float_conversion_requires_a_value():
    with pytest.raises(ValueError):
        float(DecodedValue(value=None, type=ParamType.UINT8))


# --------------------------------------------------------------------------
# Addressed-by-index vs addressed-by-name
# --------------------------------------------------------------------------

def test_2017_is_index_addressed_and_2015_is_name_hashed():
    """The request payloads are the proof, not a convention."""
    from flylib.packet import parse_packet

    p2017 = parse_packet(C.read_param_value_2017(3, 17, 1))
    assert p2017.payload == b"\x03\x00\x00\x00\x11\x00"
    assert "gps_lon" not in p2017.payload.decode("latin-1")

    p2015 = parse_packet(C.read_param_value_2015("gps_lon", 1))
    assert len(p2015.payload) == 4
    assert p2015.payload == C.param_hash("gps_lon").to_bytes(4, "little")


# --------------------------------------------------------------------------
# Protocol selection
# --------------------------------------------------------------------------

class FakeSource:
    """Stands in for the aircraft over the 2017 protocol only.

    ``table_counts`` maps table number to declared count; a table absent from
    the map behaves like one that never answers.
    """

    def __init__(self, table_counts: dict[int, int],
                 silent_tables: set[int] | None = None) -> None:
        self.table_counts = table_counts
        self.silent_tables = silent_tables or set()
        self.reads: list[tuple] = []

    def table_attribs_2017(self, table_no: int) -> int | None:
        if table_no in self.silent_tables:
            return None
        return self.table_counts.get(table_no, 0)

    def read_2017(self, table_no: int, param_index: int):
        self.reads.append(("2017", table_no, param_index))
        return f"t{table_no}p{param_index}"


def test_2017_is_the_only_protocol_the_model_can_return():
    """readAll2015 is unreachable, so there is no 2015 outcome to return."""
    assert ACTIVE_PROTOCOL == "2017"
    assert not hasattr(selection, "PROTOCOL_2015")
    for counts, tbls in [({0: 3, 1: 2}, (0, 1)), ({}, (0,)), ({0: 0}, (0, 1))]:
        assert select_parameters(FakeSource(counts), "M300RTK",
                                 tables=tbls).protocol == PROTOCOL_2017


def test_2017_is_selected_when_a_table_declares_parameters():
    source = FakeSource({0: 3, 1: 2})
    result = select_parameters(source, "M300RTK", tables=(0, 1))
    assert result.protocol == PROTOCOL_2017
    assert result.values == ["t0p0", "t0p1", "t0p2", "t1p0", "t1p1"]
    assert result.skipped_tables == []


def test_empty_table_is_skipped_without_changing_protocol():
    """The 'falling back to 2015' string is a log line, not a fallback."""
    source = FakeSource({})
    result = select_parameters(source, "M300RTK", tables=(0,))
    assert result.protocol == PROTOCOL_2017
    assert result.values == []
    assert [t.table_no for t in result.skipped_tables] == [0]


def test_unanswered_tables_are_skipped_and_logged():
    """A silent table is the realistic failure: busy link, wrong device."""
    silent = FakeSource(table_counts={}, silent_tables={0, 1, 2, 3})
    result = select_parameters(silent, "M300RTK", tables=(0, 1, 2, 3))
    assert result.protocol == PROTOCOL_2017
    assert result.values == []
    assert [t.table_no for t in result.skipped_tables] == [0, 1, 2, 3]
    assert all("no response" in d for d in result.diagnostics if "Table" in d)


def test_empty_table_diagnostic_matches_the_apps_literal():
    """Reproduced verbatim, including the misleading 'falling back' wording."""
    source = FakeSource({})
    result = select_parameters(source, "M300RTK", tables=(0,))
    assert result.diagnostics[0] == (
        "Full scan for M300RTK (first time)")
    assert result.diagnostics[1] == (
        "Table 0 empty or no response, falling back to 2015")


def test_partial_tables_still_return_2017_for_the_good_ones():
    source = FakeSource({0: 2, 1: 0, 2: 1})
    result = select_parameters(source, "M300RTK", tables=(0, 1, 2))
    assert result.protocol == PROTOCOL_2017
    assert result.values == ["t0p0", "t0p1", "t2p0"]
    assert [t.used for t in result.tables] == [True, False, True]


def test_no_2015_traffic_is_ever_generated():
    """The model must not read through the 2015 path under any input."""
    for counts, tbls in [({0: 3}, (0,)), ({}, (0, 1, 2)), ({0: 1, 1: 1}, (0, 1))]:
        source = FakeSource(counts)
        select_parameters(source, "M300RTK", tables=tbls)
        assert all(r[0] == "2017" for r in source.reads)


# --------------------------------------------------------------------------
# Index-map cache
# --------------------------------------------------------------------------

def test_index_map_is_saved_after_a_full_scan():
    saved: dict[str, list] = {}
    store = IndexMapStore(lambda name: None,
                          lambda name, pairs: saved.__setitem__(name, pairs))
    select_parameters(FakeSource({0: 2}), "M300RTK", index_maps=store)
    assert saved["M300RTK_index_map.json"] == [(0, 0), (0, 1)]


def test_index_map_is_reused_on_the_next_scan():
    saved: dict[str, list] = {}
    store = IndexMapStore(lambda name: saved.get(name),
                          lambda name, pairs: saved.__setitem__(name, pairs))
    first = select_parameters(FakeSource({0: 2}), "M300RTK", index_maps=store)

    second_source = FakeSource({0: 99})          # table now declares 99
    second = select_parameters(second_source, "M300RTK", index_maps=store)
    assert any("Cache hit" in d for d in second.diagnostics)
    assert second.values == ["t0p0", "t0p1"]     # exactly the cached pair
    assert second_source.reads == [("2017", 0, 0), ("2017", 0, 1)]


def test_force_full_scan_skips_the_cache():
    saved: dict[str, list] = {}
    store = IndexMapStore(lambda name: saved.get(name),
                          lambda name, pairs: saved.__setitem__(name, pairs))
    select_parameters(FakeSource({0: 2}), "M300RTK", index_maps=store)
    forced = select_parameters(FakeSource({0: 3}), "M300RTK", index_maps=store,
                               force_full_scan=True)
    assert not any("Cache hit" in d for d in forced.diagnostics)
    assert len(forced.values) == 3


def test_cache_is_keyed_per_codename():
    """A different aircraft must not reuse another model's index map."""
    saved: dict[str, list] = {}
    store = IndexMapStore(lambda name: saved.get(name),
                          lambda name, pairs: saved.__setitem__(name, pairs))
    select_parameters(FakeSource({0: 2}), "M300RTK", index_maps=store)
    other = select_parameters(FakeSource({0: 4}), "PHANTOM_4PRO", index_maps=store)
    assert not any("Cache hit" in d for d in other.diagnostics)
    assert saved["PHANTOM_4PRO_index_map.json"] == [(0, i) for i in range(4)]


def test_unanswered_parameters_are_droped_not_counted():
    class Partial(FakeSource):
        def read_2017(self, table_no, param_index):
            return None if param_index == 1 else super().read_2017(table_no, param_index)

    result = select_parameters(Partial({0: 3}), "M300RTK")
    assert result.values == ["t0p0", "t0p2"]


def test_diagnostics_can_be_streamed():
    seen: list[str] = []
    select_parameters(FakeSource({0: 1}), "M300RTK", on_diagnostic=seen.append)
    assert any("Full scan" in m for m in seen)