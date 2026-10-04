"""Read-only guarantees: the mutation gate and the transports.

The central claim of this project is that the library cannot change aircraft
state unless someone explicitly says so. These tests are what make that a
checked property rather than a claim in a README.

Every transport is exercised, because a guard enforced in only one of them is a
guard that a future refactor can route around.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research"))

from flylib import commands as C  # noqa: E402
from flylib.guard import (MutationGuard, MutationNotAllowed,  # noqa: E402
                          STATE_CHANGING_COMMANDS, is_state_changing)
from flylib.packet import CMD_SET_FC, PKT_RESPONSE, build_packet, parse_packet  # noqa: E402
from flylib.transport import (DryRunTransport, ReplayTransport,  # noqa: E402
                              ScriptedTransport, Session, Transport)

WRITE_2015 = C.write_param_value_2015("gps_lon", b"\x01\x00", 1)
WRITE_2017 = C.write_param_value_2017(0, 1, b"\x01\x00", 1)
UNLOCK = C.assistant_unlock(1)
READ_2017 = C.read_param_value_2017(0, 1, 1)
VERSION = C.version_inquiry(1)

ALL_MUTATING = [WRITE_2015, WRITE_2017, UNLOCK]


def _transports():
    return [
        ReplayTransport(capture=b""),
        ScriptedTransport(),
        DryRunTransport(),
    ]


# --------------------------------------------------------------------------
# The gate itself
# --------------------------------------------------------------------------

def test_guard_is_disabled_on_construction():
    assert MutationGuard().allowed is False
    assert MutationGuard().dry_run is True


@pytest.mark.parametrize("frame", ALL_MUTATING, ids=["w2015", "w2017", "unlock"])
def test_guard_refuses_every_state_changing_command_by_default(frame):
    packet = parse_packet(frame)
    assert is_state_changing(packet.cmd_set, packet.signed_cmd_id)
    with pytest.raises(MutationNotAllowed):
        MutationGuard().require("test")


@pytest.mark.parametrize("frame", ALL_MUTATING, ids=["w2015", "w2017", "unlock"])
def test_every_transport_refuses_mutation_by_default(frame):
    for transport in _transports():
        with pytest.raises(MutationNotAllowed):
            transport.send(frame)


@pytest.mark.parametrize("frame", [READ_2017, VERSION], ids=["read2017", "version"])
def test_read_commands_are_allowed_by_default(frame):
    for transport in _transports():
        transport.send(frame)          # must not raise


def test_read_commands_are_not_classified_as_state_changing():
    for frame in (READ_2017, VERSION, C.get_table_attribs_2017(0, 1),
                  C.get_param_info_2017(0, 1, 1),
                  C.get_param_info_2015("gps_lon", 1)):
        packet = parse_packet(frame)
        assert not is_state_changing(packet.cmd_set, packet.signed_cmd_id)


def test_enable_requires_a_reason():
    for blank in ("", "   ", "\n\t"):
        with pytest.raises(ValueError):
            MutationGuard().enable(blank)


def test_enabled_but_dry_run_still_refuses_transmission():
    """Opting in with dry_run keeps development safe."""
    guard = MutationGuard()
    guard.enable("testing the write path against a simulator", actor="pytest")
    assert guard.allowed is True
    with pytest.raises(MutationNotAllowed, match="dry_run"):
        guard.require("writeParamValue2017")



def test_disable_returns_to_default_and_forgets_the_reason():
    guard = MutationGuard()
    guard.enable("temporary")
    guard.disable()
    assert guard.allowed is False
    assert guard.describe()["reason"] == ""
    with pytest.raises(MutationNotAllowed):
        guard.require("writeParamValue2017")


def test_transport_uses_the_guard_it_was_given():
    transport = ScriptedTransport()
    transport.guard = MutationGuard()
    with pytest.raises(MutationNotAllowed):
        transport.send(WRITE_2017)


def test_enable_lands_in_dry_run_unless_told_otherwise():
    """The safe mode is the default outcome of opting in."""
    guard = MutationGuard()
    guard.enable("testing the write path against a simulator", actor="pytest")
    assert guard.allowed is True and guard.dry_run is True
    with pytest.raises(MutationNotAllowed, match="dry_run"):
        guard.require("writeParamValue2017")


def test_live_writes_require_explicitly_disabling_dry_run():
    guard = MutationGuard()
    guard.enable("bench test on a disarmed aircraft", actor="operator",
                 dry_run=False)
    guard.require("writeParamValue2017")        # must not raise
    described = guard.describe()
    assert described["reason"] == "bench test on a disarmed aircraft"
    assert described["enabled_by"] == "operator"
    assert described["dry_run"] is False
    assert described["enabled_at"] is not None
def test_state_changing_set_matches_the_command_table():
    """The documented set must not drift from the classifier."""
    for frame in ALL_MUTATING:
        packet = parse_packet(frame)
        assert packet.signed_cmd_id in {
            -7, -29, -33}, f"{packet.signed_cmd_id} missing from STATE_CHANGING_COMMANDS"
    assert STATE_CHANGING_COMMANDS == {
        "writeParamValue2015", "writeParamValue2017", "assistantUnlock"}


def test_a_wrong_command_set_is_not_treated_as_state_changing():
    """Classifier keys on cmdSet as well as cmdId — an id alone is not enough."""
    frame = build_packet(CMD_SET_FC, C.CMD_FC_PARAM_WRITE_2017, b"\x01",
                         packet_type=0)
    assert is_state_changing(CMD_SET_FC, -29)
    assert not is_state_changing(0, -29)


# --------------------------------------------------------------------------
# Transports
# --------------------------------------------------------------------------

def test_dry_run_transport_logs_but_does_not_transmit():
    transport = DryRunTransport()
    transport.send(READ_2017)
    assert len(transport.log) == 1
    assert transport.log[0]["cmd_id"] == C.CMD_FC_PARAM_READ_2017
    assert transport.log[0]["state_changing"] is False


def test_dry_run_transport_records_the_exact_frame_that_would_be_sent():
    transport = DryRunTransport()
    transport.send(READ_2017)
    assert transport.log[0]["frame"] == READ_2017.hex()


def test_replay_transport_is_deterministic():
    capture = READ_2017 + VERSION
    a = ReplayTransport(capture=capture)
    b = ReplayTransport(capture=capture)
    first = [p.signed_cmd_id for p in a.frames()]
    second = [p.signed_cmd_id for p in b.frames()]
    assert first == second
    assert first == [C.CMD_FC_PARAM_READ_2017, C.CMD_COMMON_VERSION_INQUIRY]


def test_replay_transport_accepts_a_capture_on_disk(tmp_path):
    capture = VERSION
    path = tmp_path / "capture.hex"
    path.write_text("# a comment\n" + capture.hex() + "\n", encoding="ascii")
    transport = ReplayTransport.from_hexfile(str(path))
    packets = list(transport.frames())
    assert len(packets) == 1
    assert packets[0].cmd_id == C.CMD_COMMON_VERSION_INQUIRY


def test_scripted_transport_returns_the_configured_reply():
    reply = build_packet(CMD_SET_FC, C.CMD_FC_PARAM_READ_2017, b"\xaa\xbb",
                         packet_type=PKT_RESPONSE, sequence=1)
    transport = ScriptedTransport(responder=lambda p: reply)
    transport.send(READ_2017)
    assert transport.read(512, 10) == reply


# --------------------------------------------------------------------------
# Session matching
# --------------------------------------------------------------------------

def _response_for(request: bytes, payload: bytes) -> bytes:
    want = parse_packet(request)
    return build_packet(want.cmd_set, want.cmd_id, payload,
                        packet_type=PKT_RESPONSE, sequence=want.sequence)


def test_session_returns_the_matching_reply():
    reply = _response_for(READ_2017, b"\x01\x02")
    transport = ScriptedTransport(responder=lambda p: reply)
    session = Session(transport)
    got = session.request(READ_2017)
    assert got is not None and got.payload == b"\x01\x02"


def test_session_tolerates_sequence_drift_but_still_matches():
    """The reference app does not require the reply sequence to match."""
    want = parse_packet(READ_2017)
    reply = build_packet(want.cmd_set, want.cmd_id, b"\x01",
                         packet_type=PKT_RESPONSE, sequence=(want.sequence + 7) & 0xFFFF)
    transport = ScriptedTransport(responder=lambda p: reply)
    assert Session(transport).request(READ_2017) is not None


def test_session_reassembles_a_reply_split_across_reads():
    reply = _response_for(READ_2017, b"\xde\xad\xbe\xef")
    chunks = [reply[i:i + 3] for i in range(0, len(reply), 3)]

    class TrickleTransport(Transport):
        name = "trickle"

        def __init__(self):
            super().__init__()
            self._pending = list(chunks)

        def write(self, data):
            return len(data)

        def read(self, max_bytes, timeout_ms):
            return self._pending.pop(0) if self._pending else b""

    session = Session(TrickleTransport())
    got = session.request(READ_2017)
    assert got is not None and got.payload == b"\xde\xad\xbe\xef"


def test_session_returns_none_on_timeout():
    transport = ScriptedTransport(responder=lambda p: None)
    assert Session(transport, timeout_ms=50).request(READ_2017) is None


def test_session_ignores_a_reply_to_a_different_command():
    other = build_packet(CMD_SET_FC, C.CMD_FC_PARAM_INFO_2017, b"\x00",
                         packet_type=PKT_RESPONSE, sequence=1)
    transport = ScriptedTransport(responder=lambda p: other)
    assert Session(transport, timeout_ms=50).request(READ_2017) is None


def test_session_refuses_a_mutating_request():
    transport = ScriptedTransport()
    with pytest.raises(MutationNotAllowed):
        Session(transport).request(WRITE_2017)


def test_session_survives_a_corrupt_reply_and_finds_the_next_good_one():
    good = _response_for(READ_2017, b"\x11\x22")
    bad = bytearray(good)
    bad[-1] ^= 0xFF                    # break the frame CRC

    class TwoReplyTransport(Transport):
        name = "two"

        def __init__(self):
            super().__init__()
            self._queue = [bytes(bad), good]

        def write(self, data):
            return len(data)

        def read(self, max_bytes, timeout_ms):
            return self._queue.pop(0) if self._queue else b""

    got = Session(TwoReplyTransport(), timeout_ms=200).request(READ_2017)
    assert got is not None and got.payload == b"\x11\x22"


def test_malformed_bytes_on_the_read_stream_are_survivable():
    good = _response_for(READ_2017, b"\x33\x44")

    class GarbageTransport(Transport):
        name = "garbage"

        def __init__(self):
            super().__init__()
            self._queue = [b"\x00\x01\x02garbage!", good]

        def write(self, data):
            return len(data)

        def read(self, max_bytes, timeout_ms):
            return self._queue.pop(0) if self._queue else b""

    got = Session(GarbageTransport(), timeout_ms=200).request(READ_2017)
    assert got is not None and got.payload == b"\x33\x44"