"""Golden-vector and property tests for the DUML implementation.

The checksum layer is verified against the **APK's own tables**: they are lifted
straight out of ``DumlBuilder.<clinit>`` and compared element by element with the
tables this library generates from a polynomial. That is the only check that
proves the polynomial derivation is right rather than merely self-consistent, so
it is not optional — when the proprietary sample is absent the checksum tests
skip, and the remaining tests still run.

The frame layer is checked two ways: against hardcoded golden vectors, and
against a second, deliberately literal transcription of the smali in
``_reference_build`` below. Two independent implementations agreeing on the same
bytes catches transcription errors that a single implementation cannot.
"""
from __future__ import annotations

import os
import re
import struct
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research"))

from flylib import commands as C  # noqa: E402
from flylib.crc import CRC8_TABLE, CRC16_TABLE, crc8, crc16  # noqa: E402
from flylib.packet import (ACK_AFTER_EXEC, ACK_NO_ACK, CMD_SET_COMMON,  # noqa: E402
                           CMD_SET_FC, DEV_CENTER, DEV_FC, DEV_PC, HEADER_SIZE,
                           MAGIC, PKT_RESPONSE, build_packet, parse_header,
                           parse_packet)
from flylib.parser import StreamParser  # noqa: E402

SMALI = os.path.join(
    REPO, "work", "apktool", "decoded", "smali_classes8", "com", "dronehacks",
    "app", "data", "protocol", "DumlBuilder.smali")
HAVE_SMALI = os.path.exists(SMALI)


# --------------------------------------------------------------------------
# Checksum verification against the APK's own tables
# --------------------------------------------------------------------------

def _apk_array(label: str) -> list[int]:
    with open(SMALI, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f":{label}":
            i += 2  # skip the label and the .array-data width line
            vals: list[int] = []
            while ".end array-data" not in lines[i]:
                stripped = lines[i].strip()
                if stripped and not stripped.startswith("."):
                    vals.extend(int(tok, 16) for tok in stripped.split()
                                if re.fullmatch(r"0x[0-9a-fA-F]+", tok))
                i += 1
            return vals
    raise AssertionError(f"{label} not found in {SMALI}")


@pytest.mark.skipif(not HAVE_SMALI, reason="apktool smali not available")
def test_crc8_table_matches_the_apk():
    assert list(CRC8_TABLE) == _apk_array("array_0")


@pytest.mark.skipif(not HAVE_SMALI, reason="apktool smali not available")
def test_crc16_table_matches_the_apk():
    assert list(CRC16_TABLE) == _apk_array("array_1")


@pytest.mark.skipif(not HAVE_SMALI, reason="apktool smali not available")
def test_crc_over_the_apk_first_frame_prefix_is_stable():
    """Spot-check the routines against hand-applied CRC definitions.

    crc8 is a plain reflected CRC-8 (poly 0x8C, init 0x77) so its value for a
    one-byte message equals the table entry XORed with the init in the standard
    way; asserting the fixed value pins the initial condition, which is the part
    a polynomial alone does not determine.
    """
    assert crc8(b"", 0, 0) == 0x77
    assert crc8(b"\x00") == CRC8_TABLE[0x00 ^ 0x77]
    assert crc16(b"", 0, 0) == 0x3692


def test_crc16_step_is_the_standard_reflected_step():
    """The APK's `t = crc>>8; crc = table[(byte^crc)&0xff] ^ t` is the ordinary
    LSB-first CRC-16 update, merely reordered.

    Worth pinning because the APK's spelling reads like a bespoke algorithm and
    invites an implementer to "fix" it. What is DJI-specific is the initial
    value and the absent final XOR, not the update.
    """
    import random

    def apk_step(reg: int, byte: int) -> int:
        t = (reg >> 8) & 0xFF
        return (CRC16_TABLE[(byte ^ reg) & 0xFF] ^ t) & 0xFFFF

    def standard_step(reg: int, byte: int) -> int:
        return ((reg >> 8) ^ CRC16_TABLE[(reg ^ byte) & 0xFF]) & 0xFFFF

    rng = random.Random(4242)
    for _ in range(20000):
        reg, byte = rng.randrange(65536), rng.randrange(256)
        assert apk_step(reg, byte) == standard_step(reg, byte)


def test_crc16_parameters_are_x25_with_a_dji_init():
    """Poly 0x1021 reflected, init 0x3692, xorout 0 — X-25 otherwise."""
    from flylib.crc import CRC16_INIT, CRC16_POLY, CRC16_XOROUT
    assert CRC16_POLY == 0x8408      # reflection of 0x1021
    assert CRC16_INIT == 0x3692
    assert CRC16_XOROUT == 0x0000
    assert crc16(b"123456789") == 0x7109


# --------------------------------------------------------------------------
# Parameter-name hashing
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("", 0),
    ("gps_lon", 1634836909),
    ("FlycCoe", 1688440258),
])
def test_param_hash_golden(name, expected):
    assert C.param_hash(name) == expected


def test_param_hash_matches_the_smali_modulus():
    """The APK computes `((hash << 8) + byte) % 0xfffffffb` in 64-bit Kotlin."""
    for name in ("gps_lon", "FlycCoe", "a", "zzzzzzzzzz"):
        value = 0
        for byte in name.encode("ascii"):
            value = ((value << 8) + byte) % 0xFFFFFFFB
        assert C.param_hash(name) == value


def test_param_hash_rejects_non_ascii():
    with pytest.raises(UnicodeEncodeError):
        C.param_hash("gé")


# --------------------------------------------------------------------------
# Golden frames
# --------------------------------------------------------------------------

# Every vector below is a frame of length `11 + len(payload) + 2`, with the
# payload starting at offset 11. They were checked field by field against the
# smali rather than merely captured from the implementation: the 13 that a
# naive `HEADER_SIZE = 13` produces are self-consistent, parse cleanly, and are
# wrong on the wire, which is exactly the failure mode golden vectors exist to
# catch.
GOLDEN = [
    ("assistantUnlock",
     "551104922a0301004003df01000000b2a0"),
    ("versionInquiry",
     "550d04332a030100400001f05e"),
    ("getCfgFileChunk(0)",
     "551604fc2a45010040004f0100000000ffffffff3086"),
    ("getParamInfo2015('gps_lon')",
     "551104922a0301000003f0ada171614896"),
    ("getParamInfoByIndex2015(7)",
     "550f04a22a0301000003f00700c4e6"),
    ("readParamValue2015('gps_lon')",
     "551104922a0301000003f8ada1716168cc"),
    ("getTableAttribs2017(0)",
     "550f04a22a0301004003e000007bef"),
    ("getParamInfo2017(0,1)",
     "551104922a0301004003e100000100b810"),
    ("readParamValue2017(0,1)",
     "551304032a0301004003e2000000000100f073"),
    ("writeParamValue2015('gps_lon',[1,0])",
     "551304032a0301000003f9ada1716101002a1b"),
    ("writeParamValue2017(0,1,[1,0])",
     "551504a92a0301004003e30000000001000100a040"),
    ("replyRegAck(1,0x03)",
     "550e04662a03010080008200f0ff"),
    ("replyRegDev(1,0x03,zeros64)",
     "554d04a82a0301008000810050630000000000000000000000000000000000000000"
     "00000000000000000000010a00000000000000000000000000000000000000000000"
     "0000000000000022b9"),
]

FRAMES = {
    "assistantUnlock": lambda: C.assistant_unlock(1),
    "versionInquiry": lambda: C.version_inquiry(1),
    "getCfgFileChunk(0)": lambda: C.get_cfg_file_chunk(0, 1),
    "getParamInfo2015('gps_lon')": lambda: C.get_param_info_2015("gps_lon", 1),
    "getParamInfoByIndex2015(7)": lambda: C.get_param_info_by_index_2015(7, 1),
    "readParamValue2015('gps_lon')": lambda: C.read_param_value_2015("gps_lon", 1),
    "getTableAttribs2017(0)": lambda: C.get_table_attribs_2017(0, 1),
    "getParamInfo2017(0,1)": lambda: C.get_param_info_2017(0, 1, 1),
    "readParamValue2017(0,1)": lambda: C.read_param_value_2017(0, 1, 1),
    "writeParamValue2015('gps_lon',[1,0])":
        lambda: C.write_param_value_2015("gps_lon", b"\x01\x00", 1),
    "writeParamValue2017(0,1,[1,0])":
        lambda: C.write_param_value_2017(0, 1, b"\x01\x00", 1),
    "replyRegAck(1,0x03)": lambda: C.reply_reg_ack(1, 0x03),
    "replyRegDev(1,0x03,zeros64)": lambda: C.reply_reg_dev(1, 0x03, bytes(64)),
}


@pytest.mark.parametrize("name,hexframe", GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden_frames(name, hexframe):
    assert FRAMES[name]().hex() == hexframe


@pytest.mark.parametrize("name,hexframe", GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden_frames_decode_back(name, hexframe):
    frame = bytes.fromhex(hexframe)
    packet = parse_packet(frame)
    # every golden frame is a well-formed, fully validated frame
    assert packet.total_length == len(frame)
    header, _ = parse_header(frame)
    assert header.version == 1
    assert header.sender_type == DEV_PC and header.sender_index == 1


# --------------------------------------------------------------------------
# Differential check against a literal transcription of the smali
# --------------------------------------------------------------------------

def _reference_build(cmd_set, cmd_id, payload, sender_type, sender_index,
                     receiver_type, receiver_index, ack_type, packet_type,
                     seq, version=1):
    """A second, deliberately naive transcription of DumlBuilder.buildPacket.

    Written to follow the bytecode instruction for instruction rather than to be
    elegant, so that a shared misreading of the smali is unlikely.
    """
    payload = bytes(payload)
    total = len(payload) + 11 + 2
    raw = bytearray(total)
    raw[0] = 0x55
    ver_length = (total & 0x3FF) | 0x400          # version 1
    raw[1] = ver_length & 0xFF
    raw[2] = (ver_length >> 8) & 0xFF
    raw[3] = 0
    raw[4] = (sender_type & 0x1F) | ((sender_index & 0x7) << 5)
    raw[5] = (receiver_type & 0x1F) | ((receiver_index & 0x7) << 5)
    raw[6] = seq & 0xFF
    raw[7] = (seq >> 8) & 0xFF
    raw[8] = ((packet_type & 1) << 7) | ((ack_type & 3) << 5)
    raw[9] = cmd_set & 0xFF
    raw[10] = cmd_id & 0xFF
    for i, byte in enumerate(payload):
        raw[11 + i] = byte
    reg = 0x77
    for i in range(3):
        reg = CRC8_TABLE[(raw[i] ^ reg) & 0xFF]
    raw[3] = reg & 0xFF
    reg = 0x3692
    for i in range(total - 2):
        high = (reg >> 8) & 0xFF
        reg = (CRC16_TABLE[(raw[i] ^ reg) & 0xFF] ^ high) & 0xFFFF
    raw[total - 2] = reg & 0xFF
    raw[total - 1] = (reg >> 8) & 0xFF
    return bytes(raw)


@pytest.mark.parametrize("payload", [b"", b"\x01", bytes(range(16)), bytes(200)])
@pytest.mark.parametrize("seq", [0, 1, 255, 4096, 65535])
def test_encoder_matches_literal_transcription(payload, seq):
    mine = build_packet(3, -29, payload, sender_type=DEV_PC, sender_index=1,
                        receiver_type=DEV_FC, receiver_index=0,
                        ack_type=ACK_AFTER_EXEC, packet_type=0, sequence=seq)
    theirs = _reference_build(3, -29, payload, DEV_PC, 1, DEV_FC, 0,
                              ACK_AFTER_EXEC, 0, seq)
    assert mine == theirs


def test_roundtrip_over_random_payloads():
    import random
    rng = random.Random(20261004)          # fixed seed: failures are reproducible
    for _ in range(500):
        payload = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 300)))
        seq = rng.randrange(65536)
        frame = build_packet(CMD_SET_FC, -30, payload, sequence=seq)
        packet = parse_packet(frame)
        assert packet.payload == payload
        assert packet.sequence == seq


# --------------------------------------------------------------------------
# Header field semantics
# --------------------------------------------------------------------------

def test_device_byte_packing():
    frame = C.version_inquiry(1)
    # sender DEV_PC index 1 -> 0b001_01010 = 0x2a
    assert frame[4] == ((1 << 5) | DEV_PC) == 0x2A
    # receiver DEV_FC index 0
    assert frame[5] == DEV_FC


def test_length_word_carries_version_one_and_total_length():
    frame = C.version_inquiry(1)
    ver_length = struct.unpack_from("<H", frame, 1)[0]
    assert (ver_length >> 10) & 0x3F == 1
    assert ver_length & 0x3FF == len(frame)


def test_frame_crc_is_stored_little_endian():
    frame = C.get_param_info_2017(0, 1, 1)
    total = len(frame)
    low, high = frame[total - 2], frame[total - 1]
    assert low | (high << 8) == crc16(frame, 0, total - 2)


def test_response_packet_type_bit():
    frame = C.reply_reg_ack(1, 0x03)
    assert frame[8] & 0x80, "PKT_RESPONSE must set bit 7 of the type byte"
    assert parse_packet(frame).packet_type == PKT_RESPONSE


def test_2015_commands_use_no_ack_and_2017_use_after_exec():
    """A real asymmetry in the APK, asserted so a 'cleanup' cannot hide it."""
    assert parse_packet(C.read_param_value_2015("gps_lon", 1)).ack_type == ACK_NO_ACK
    assert parse_packet(C.read_param_value_2017(0, 1, 1)).ack_type == ACK_AFTER_EXEC


def test_cfg_chunk_targets_dev_center_index_two():
    packet = parse_packet(C.get_cfg_file_chunk(0, 1))
    assert packet.receiver_type == DEV_CENTER and packet.receiver_index == 2


# --------------------------------------------------------------------------
# Malformed input
# --------------------------------------------------------------------------

def test_bad_magic_is_rejected():
    frame = bytearray(C.version_inquiry(1))
    frame[0] = 0x56
    with pytest.raises(Exception, match="magic"):
        parse_packet(bytes(frame))


def test_header_crc_mismatch_is_rejected():
    frame = bytearray(C.version_inquiry(1))
    frame[3] ^= 0xFF
    with pytest.raises(Exception, match="header CRC"):
        parse_packet(bytes(frame))


def test_frame_crc_mismatch_is_rejected():
    frame = bytearray(C.version_inquiry(1))
    frame[-1] ^= 0xFF
    with pytest.raises(Exception, match="frame CRC"):
        parse_packet(bytes(frame))


def test_truncated_frame_is_rejected():
    frame = C.read_param_value_2017(0, 1, 1)
    with pytest.raises(Exception, match="truncated"):
        parse_packet(frame[:-1])


def test_buffer_shorter_than_a_minimal_frame_is_rejected():
    with pytest.raises(Exception, match="minimum frame"):
        parse_packet(C.version_inquiry(1)[:-1])


def test_declared_length_below_header_is_rejected():
    frame = bytearray(C.version_inquiry(1))
    struct.pack_into("<H", frame, 1, 5)     # version 0, total length 5
    with pytest.raises(Exception):
        parse_packet(bytes(frame))


# --------------------------------------------------------------------------
# Streaming framer
# --------------------------------------------------------------------------

def test_framer_handles_arbitrary_chunking():
    stream = b"".join([
        C.version_inquiry(1),
        C.read_param_value_2017(0, 3, 2),
        C.assistant_unlock(3),
    ])
    for chunk_size in (1, 2, 3, 5, 7, 13, 64, len(stream)):
        parser = StreamParser()
        seen = []
        for i in range(0, len(stream), chunk_size):
            seen.extend(parser.feed(stream[i:i + chunk_size]))
        assert len([e for e in seen if e.ok]) == 3, f"chunk size {chunk_size}"
        assert parser.stats.resyncs == 0


def test_framer_resynchronises_after_garbage():
    good = C.version_inquiry(1)
    parser = StreamParser()
    events = parser.feed(b"\x00\x11\x22garbage" + good)
    frames = [e for e in events if e.ok]
    assert len(frames) == 1
    assert parser.stats.resyncs >= 1
    assert frames[0].packet.sequence == 1


def test_framer_skips_a_corrupt_frame_and_keeps_going():
    bad = bytearray(C.version_inquiry(1))
    bad[-1] ^= 0xFF                        # break the frame CRC
    good = C.assistant_unlock(9)
    parser = StreamParser()
    events = parser.feed(bytes(bad) + good)
    ok = [e for e in events if e.ok]
    assert len(ok) == 1
    assert ok[0].packet.signed_cmd_id == C.CMD_FC_ASSISTANT_UNLOCK


def test_framer_ignores_a_split_magic_across_reads():
    frame = C.version_inquiry(1)
    parser = StreamParser()
    assert parser.feed(frame[:1]) == []   # lone 0x55 held back, not discarded
    events = parser.feed(frame[1:])
    assert len([e for e in events if e.ok]) == 1