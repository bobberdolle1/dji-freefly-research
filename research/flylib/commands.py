"""DUML command builders recovered from Free Fly 1.0.

Every function here corresponds one-to-one with a method on the app's
``DroneCommands`` object, and every constant was read out of its smali (or,
where noted, re-derived by ``tools/extract_duml_commands.py``) rather than taken
from a public write-up.

Shared defaults, taken from ``DumlBuilder.buildPacket$default``:

* sender ``DEV_PC`` (10) index 1
* receiver ``DEV_FC`` (3) index 0
* ``ACK_NO_ACK``, ``PKT_REQUEST``
* sequence number from a monotonic counter starting at 1

Note the asymmetry the app actually uses: the 2015 parameter commands leave the
ack type at ``ACK_NO_ACK``, while the 2017 parameter commands and the version
inquiry explicitly request ``ACK_AFTER_EXEC``. That is a property of the APK, not
a choice made here.
"""
from __future__ import annotations

import struct

from .packet import (ACK_AFTER_EXEC, ACK_NO_ACK, CMD_SET_COMMON, CMD_SET_FC,
                     DEV_CENTER, DEV_FC, DEV_PC, PKT_REQUEST, PKT_RESPONSE,
                     build_packet)

DEFAULT_SENDER_TYPE = DEV_PC
DEFAULT_SENDER_INDEX = 1
DEFAULT_RECEIVER_TYPE = DEV_FC
DEFAULT_RECEIVER_INDEX = 0

# Command ids, as declared in the app's DumlConstants.
CMD_FC_ASSISTANT_UNLOCK = -33
CMD_FC_PARAM_TABLE_ATTRS_2017 = -32
CMD_FC_PARAM_INFO_2017 = -31
CMD_FC_PARAM_READ_2017 = -30
CMD_FC_PARAM_WRITE_2017 = -29
CMD_FC_PARAM_INFO_2015 = -16
CMD_FC_PARAM_INFO_HASH_2015 = -9
CMD_FC_PARAM_READ_2015 = -8
CMD_FC_PARAM_WRITE_2015 = -7
CMD_COMMON_VERSION_INQUIRY = 1
CMD_COMMON_REG_ACK = -126
CMD_COMMON_REG_DEV = -127
CMD_COMMON_CFG_FILE_CHUNK = 79

HASH_MODULUS = 0xFFFFFFFB  # 2**32 - 5


class SequenceCounter:
    """Monotonic sequence counter.

    The app's ``nextSeq()`` starts its static counter at 1 and returns the
    pre-increment value, so the first frame it builds carries sequence 1.
    """

    def __init__(self, start: int = 1) -> None:
        self._next = start

    def __call__(self) -> int:
        value = self._next
        self._next += 1
        return value

    def peek(self) -> int:
        return self._next


def param_hash(name: str) -> int:
    """DJI parameter-name hash.

    Reproduces the app's ``DroneCommands.paramHash``:

        hash = 0
        for byte in name.encode('US-ASCII'):
            hash = ((hash << 8) + byte) % (2**32 - 5)

    The name is encoded as US-ASCII and each byte is masked to 0..255, so a
    non-ASCII name raises rather than silently hashing something else.
    """
    digest = 0
    for byte in name.encode("ascii"):
        digest = ((digest << 8) + (byte & 0xFF)) % HASH_MODULUS
    return digest & 0xFFFFFFFF


def assistant_unlock(seq: int, **kw) -> bytes:
    """``assistantUnlock()`` — cmdSet FC, cmdId -33, payload ``01 00 00 00``."""
    return build_packet(CMD_SET_FC, CMD_FC_ASSISTANT_UNLOCK, b"\x01\x00\x00\x00",
                        ack_type=ACK_AFTER_EXEC, sequence=seq, **kw)


def version_inquiry(seq: int, **kw) -> bytes:
    """``versionInquiry()`` — cmdSet COMMON, cmdId 1, empty payload."""
    return build_packet(CMD_SET_COMMON, CMD_COMMON_VERSION_INQUIRY, b"",
                        ack_type=ACK_AFTER_EXEC, sequence=seq, **kw)


def version_inquiry_to(dst_dev_byte: int, seq: int, **kw) -> bytes:
    """``versionInquiryTo(dst)`` — same as above but to an explicit device byte.

    ``dst_dev_byte`` is the packed ``(index << 5) | type`` value.
    """
    receiver_type = dst_dev_byte & 0x1F
    receiver_index = (dst_dev_byte >> 5) & 0x7
    return build_packet(CMD_SET_COMMON, CMD_COMMON_VERSION_INQUIRY, b"",
                        receiver_type=receiver_type, receiver_index=receiver_index,
                        ack_type=ACK_AFTER_EXEC, sequence=seq, **kw)


def get_cfg_file_chunk(offset: int, seq: int, **kw) -> bytes:
    """``getCfgFileChunk(offset)`` — cmdSet COMMON, cmdId 79, to DEV_CENTER:2.

    Payload is ``01 | uint32le(offset) | uint32le(0xFFFFFFFF)``: a one-byte
    selector, the chunk offset, and a length of -1 meaning "to the end".
    """
    payload = b"\x01" + struct.pack("<iI", offset, -1 & 0xFFFFFFFF)
    return build_packet(CMD_SET_COMMON, CMD_COMMON_CFG_FILE_CHUNK, payload,
                        receiver_type=DEV_CENTER, receiver_index=2,
                        ack_type=ACK_AFTER_EXEC, sequence=seq, **kw)


def get_param_info_2015(name: str, seq: int, **kw) -> bytes:
    """cmdSet FC, cmdId -16, payload ``uint32le(paramHash(name))``."""
    return build_packet(CMD_SET_FC, CMD_FC_PARAM_INFO_2015,
                        struct.pack("<I", param_hash(name)),
                        ack_type=ACK_NO_ACK, sequence=seq, **kw)


def get_param_info_by_index_2015(param_index: int, seq: int, **kw) -> bytes:
    """cmdSet FC, cmdId -16, payload ``uint16le(param_index)``."""
    return build_packet(CMD_SET_FC, CMD_FC_PARAM_INFO_2015,
                        struct.pack("<h", param_index),
                        ack_type=ACK_NO_ACK, sequence=seq, **kw)


def read_param_value_2015(name: str, seq: int, **kw) -> bytes:
    """cmdSet FC, cmdId -8, payload ``uint32le(paramHash(name))``."""
    return build_packet(CMD_SET_FC, CMD_FC_PARAM_READ_2015,
                        struct.pack("<I", param_hash(name)),
                        ack_type=ACK_NO_ACK, sequence=seq, **kw)


def write_param_value_2015(name: str, value_bytes: bytes, seq: int, **kw) -> bytes:
    """cmdSet FC, cmdId -7, payload ``uint32le(hash) || value`` — STATE-CHANGING."""
    payload = struct.pack("<I", param_hash(name)) + bytes(value_bytes)
    return build_packet(CMD_SET_FC, CMD_FC_PARAM_WRITE_2015, payload,
                        ack_type=ACK_NO_ACK, sequence=seq, **kw)


def get_table_attribs_2017(table_no: int, seq: int, **kw) -> bytes:
    """cmdSet FC, cmdId -32, payload ``uint16le(table_no)``."""
    return build_packet(CMD_SET_FC, CMD_FC_PARAM_TABLE_ATTRS_2017,
                        struct.pack("<h", table_no),
                        ack_type=ACK_AFTER_EXEC, sequence=seq, **kw)


def get_param_info_2017(table_no: int, param_index: int, seq: int, **kw) -> bytes:
    """cmdSet FC, cmdId -31, payload ``uint16le(table) || uint16le(index)``."""
    payload = struct.pack("<hH", table_no, param_index)
    return build_packet(CMD_SET_FC, CMD_FC_PARAM_INFO_2017, payload,
                        ack_type=ACK_AFTER_EXEC, sequence=seq, **kw)


def read_param_value_2017(table_no: int, param_index: int, seq: int, **kw) -> bytes:
    """cmdSet FC, cmdId -30, payload ``uint16le(table) || uint16le(0) || uint16le(index)``.

    The middle uint16 is a reserved/zero field in the app's implementation.
    """
    payload = struct.pack("<hHH", table_no, 0, param_index)
    return build_packet(CMD_SET_FC, CMD_FC_PARAM_READ_2017, payload,
                        ack_type=ACK_AFTER_EXEC, sequence=seq, **kw)


def write_param_value_2017(table_no: int, param_index: int, value_bytes: bytes,
                           seq: int, **kw) -> bytes:
    """cmdSet FC, cmdId -29 — STATE-CHANGING."""
    payload = struct.pack("<hHH", table_no, 0, param_index) + bytes(value_bytes)
    return build_packet(CMD_SET_FC, CMD_FC_PARAM_WRITE_2017, payload,
                        ack_type=ACK_AFTER_EXEC, sequence=seq, **kw)


REG_DEV_PAYLOAD_SIZE = 64


def reply_reg_ack(seq: int, peer_dev_byte: int, **kw) -> bytes:
    """``replyRegAck(...)`` — cmdSet COMMON, cmdId -126, payload ``00``.

    Answers a registration request: the reply is sent back to the device byte
    that the request came from, as a ``PKT_RESPONSE`` echoing the same sequence.
    """
    return build_packet(CMD_SET_COMMON, CMD_COMMON_REG_ACK, b"\x00",
                        receiver_type=peer_dev_byte & 0x1F,
                        receiver_index=(peer_dev_byte >> 5) & 0x7,
                        ack_type=ACK_NO_ACK, packet_type=PKT_RESPONSE,
                        sequence=seq, **kw)


def reply_reg_dev(seq: int, peer_dev_byte: int, request_packet: bytes, **kw) -> bytes:
    """``replyRegDev(...)`` — cmdSet COMMON, cmdId -127, 64-byte payload.

    The payload is a fixed 64-byte structure, zero-filled except for a fixed
    prefix and three bytes copied out of the registration request:

    ======  ==========================================================
    Offset  Value
    ======  ==========================================================
    0x01    ``0x50``
    0x02    ``0x63``
    0x21    ``0x01``
    0x22    ``0x0A``
    0x23    ``request[0x2b]`` when the request is longer than 0x2b
    0x29    ``request[0x29]`` when the request is longer than 0x29
    0x2d    ``request[0x2d]`` when the request is longer than 0x2d
    ======  ==========================================================

    The guards are strict ``>`` comparisons, so a byte at exactly the bound is
    not copied; that off-by-one is reproduced rather than "fixed".
    """
    payload = bytearray(REG_DEV_PAYLOAD_SIZE)
    payload[0x01] = 0x50
    payload[0x02] = 0x63
    payload[0x21] = 0x01
    payload[0x22] = 0x0A
    for src, dst in ((0x2B, 0x23), (0x29, 0x29), (0x2D, 0x2D)):
        if len(request_packet) > src:
            payload[dst] = request_packet[src]
    return build_packet(CMD_SET_COMMON, CMD_COMMON_REG_DEV, bytes(payload),
                        receiver_type=peer_dev_byte & 0x1F,
                        receiver_index=(peer_dev_byte >> 5) & 0x7,
                        ack_type=ACK_NO_ACK, packet_type=PKT_RESPONSE,
                        sequence=seq, **kw)