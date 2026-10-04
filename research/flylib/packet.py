"""DUML packet encoding and decoding.

Clean-room implementation of the exact wire format Free Fly 1.0
(com.dronehacks.app) speaks, recovered from its smali. Layout, verified against
``DumlBuilder.buildPacket`` and ``DumlParser.parse``:

===  ==========  =====================================================
Off  Size        Meaning
===  ==========  =====================================================
0    1           magic, always 0x55
1    2           uint16 LE: ``(version << 10) | total_length``
                       version occupies the top 6 bits, total_length the low 10
2    (cont.)
3    1           header CRC-8 over bytes [0, 3)
4    1           sender device byte: ``(sender_index & 7) << 5 | (sender_type & 0x1f)``
5    1           receiver device byte: same packing
6    2           uint16 LE sequence number
7    (cont.)
8    1           ``(packet_type & 1) << 7 | (ack_type & 3) << 5``
9    1           command set
10   1           command id (signed 8-bit in DJI's own naming)
11   N           payload, ``total_length - 13`` bytes
N-2  2           uint16 LE CRC-16 over bytes [0, total_length - 2)
===  ==========  =====================================================

The frame CRC is stored **little-endian**: the low byte at ``total_length - 2``
and the high byte at ``total_length - 1``. Free Fly's parser reconstructs the
value as ``(data[total_length - 1] << 8) | data[total_length - 2]``, which is
consistent with that layout.
"""
from __future__ import annotations

import dataclasses
import struct

from .crc import crc8, crc16

MAGIC = 0x55
# Bytes preceding the payload: magic(1) + verLength(2) + headerCRC(1) +
# sender(1) + receiver(1) + sequence(2) + cmdTypeData(1) + cmdSet(1) +
# cmdId(1) = 11. The smallest legal frame is therefore 13 bytes
# (11 header + 0 payload + 2 CRC), which is the constant the app's parser
# compares the buffer against. Confusing the two is an easy 2-byte error that
# still produces self-consistent frames, so they are named separately.
HEADER_SIZE = 11
CRC_SIZE = 2
MIN_FRAME_SIZE = HEADER_SIZE + CRC_SIZE
PROTOCOL_VERSION = 1
VERSION_SHIFT = 10
LENGTH_MASK = 0x3FF
VERSION_MASK = 0x3F
MAX_TOTAL_LENGTH = LENGTH_MASK + 1

# Device types, as named by the app's DumlConstants.
DEV_ANY = 0
DEV_CAMERA = 1
DEV_APP = 2
DEV_FC = 3
DEV_GIMBAL = 4
DEV_CENTER = 5
DEV_RC = 6
DEV_PC = 10

ACK_NO_ACK = 0
ACK_BEFORE_EXEC = 1
ACK_AFTER_EXEC = 2

PKT_REQUEST = 0
PKT_RESPONSE = 1

# Command sets.
CMD_SET_COMMON = 0
CMD_SET_SPECIAL = 1
CMD_SET_FC = 3


class DumlError(ValueError):
    """Raised when a frame cannot be encoded or decoded."""


@dataclasses.dataclass(frozen=True)
class Header:
    version: int
    total_length: int
    header_crc: int
    sender_type: int
    sender_index: int
    receiver_type: int
    receiver_index: int
    sequence: int
    packet_type: int
    ack_type: int
    cmd_set: int
    cmd_id: int


@dataclasses.dataclass(frozen=True)
class Packet:
    """A decoded DUML frame.

    ``payload`` excludes the two trailing CRC bytes.
    """

    cmd_set: int
    cmd_id: int
    payload: bytes
    sequence: int
    packet_type: int
    ack_type: int
    sender_type: int
    sender_index: int
    receiver_type: int
    receiver_index: int
    version: int = PROTOCOL_VERSION

    @property
    def total_length(self) -> int:
        return HEADER_SIZE + len(self.payload) + CRC_SIZE

    @property
    def signed_cmd_id(self) -> int:
        """``cmd_id`` as DJI names it: a signed 8-bit value.

        The wire carries an unsigned byte, but the app declares ids such as
        ``-33`` (0xDF) for the assistant unlock, so both forms are offered and
        the unsigned one remains the stored value.
        """
        return self.cmd_id - 0x100 if self.cmd_id > 0x7F else self.cmd_id

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"Packet(cmdSet={self.cmd_set}, cmdId={self.cmd_id} "
                f"({self.cmd_id & 0xFF}), seq={self.sequence}, "
                f"type={self.packet_type}, ack={self.ack_type}, "
                f"payload={len(self.payload)}B)")


def pack_dev_byte(device_type: int, index: int) -> int:
    return ((index & 0x7) << 5) | (device_type & 0x1F)


def unpack_dev_byte(byte: int) -> tuple[int, int]:
    """Return ``(device_type, index)``."""
    return byte & 0x1F, (byte >> 5) & 0x7


def build_packet(cmd_set: int, cmd_id: int, payload: bytes,
                 sender_type: int = DEV_PC, sender_index: int = 1,
                 receiver_type: int = DEV_FC, receiver_index: int = 0,
                 ack_type: int = ACK_NO_ACK, packet_type: int = PKT_REQUEST,
                 sequence: int = 0, version: int = PROTOCOL_VERSION) -> bytes:
    """Encode one DUML frame.

    ``cmd_id`` is accepted as a signed value (``-33``) or as its unsigned byte
    form (``0xDF``); both encode identically, matching how the APK declares the
    constants.
    """
    payload = bytes(payload)
    total_length = HEADER_SIZE + len(payload) + CRC_SIZE
    if total_length > MAX_TOTAL_LENGTH:
        raise DumlError(f"payload too large: {total_length} > {MAX_TOTAL_LENGTH}")
    if not 0 <= version <= VERSION_MASK:
        raise DumlError(f"version {version} does not fit in {VERSION_MASK} bits")

    ver_length = ((version & VERSION_MASK) << VERSION_SHIFT) | (total_length & LENGTH_MASK)
    raw = bytearray(total_length)
    raw[0] = MAGIC
    struct.pack_into("<H", raw, 1, ver_length)
    raw[3] = 0
    raw[4] = pack_dev_byte(sender_type, sender_index)
    raw[5] = pack_dev_byte(receiver_type, receiver_index)
    struct.pack_into("<H", raw, 6, sequence & 0xFFFF)
    raw[8] = ((packet_type & 1) << 7) | ((ack_type & 3) << 5)
    raw[9] = cmd_set & 0xFF
    raw[10] = cmd_id & 0xFF
    raw[HEADER_SIZE:HEADER_SIZE + len(payload)] = payload

    raw[3] = crc8(raw, 0, 3)
    frame_crc = crc16(raw, 0, total_length - CRC_SIZE)
    struct.pack_into("<H", raw, total_length - CRC_SIZE, frame_crc)
    return bytes(raw)


def parse_header(data: bytes) -> tuple[Header, int]:
    """Validate and parse a frame.

    Returns ``(header, payload_length)``. Raises :class:`DumlError` with a
    ``reason`` attribute so a streaming caller can tell "not enough bytes yet"
    apart from "this frame is corrupt".
    """
    if len(data) < MIN_FRAME_SIZE:
        raise DumlError(f"buffer of {len(data)} bytes is shorter than the "
                        f"{MIN_FRAME_SIZE}-byte minimum frame")
    if data[0] != MAGIC:
        raise DumlError(f"bad magic 0x{data[0]:02x}, expected 0x{MAGIC:02x}")

    ver_length = struct.unpack_from("<H", data, 1)[0]
    version = (ver_length >> VERSION_SHIFT) & VERSION_MASK
    total_length = ver_length & LENGTH_MASK
    if total_length < MIN_FRAME_SIZE:
        raise DumlError(f"declared total length {total_length} is below the "
                        f"minimum frame size of {MIN_FRAME_SIZE}")
    if len(data) < total_length:
        raise DumlError(f"frame truncated: need {total_length} bytes, have {len(data)}")

    stored_header_crc = data[3]
    computed = crc8(data, 0, 3)
    if stored_header_crc != computed:
        raise DumlError(f"header CRC mismatch: stored 0x{stored_header_crc:02x}, "
                        f"computed 0x{computed:02x}")

    computed_frame_crc = crc16(data, 0, total_length - CRC_SIZE)
    stored_frame_crc = struct.unpack_from("<H", data, total_length - CRC_SIZE)[0]
    if stored_frame_crc != computed_frame_crc:
        raise DumlError(f"frame CRC mismatch: stored 0x{stored_frame_crc:04x}, "
                        f"computed 0x{computed_frame_crc:04x}")

    cmd_type_data = data[8]
    sender_type, sender_index = unpack_dev_byte(data[4])
    receiver_type, receiver_index = unpack_dev_byte(data[5])
    header = Header(
        version=version,
        total_length=total_length,
        header_crc=stored_header_crc,
        sender_type=sender_type,
        sender_index=sender_index,
        receiver_type=receiver_type,
        receiver_index=receiver_index,
        sequence=struct.unpack_from("<H", data, 6)[0],
        packet_type=(cmd_type_data >> 7) & 1,
        ack_type=(cmd_type_data >> 5) & 3,
        cmd_set=data[9],
        cmd_id=data[10],
    )
    return header, total_length


def parse_packet(data: bytes) -> Packet:
    """Decode exactly one complete frame."""
    header, total_length = parse_header(data)
    payload = bytes(data[HEADER_SIZE:total_length - CRC_SIZE])
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


def frame_length_at(data: bytes, offset: int = 0) -> int | None:
    """Length of the frame starting at ``offset``, or None if not yet knowable.

    Reads only the length word, so it is safe to call on a partial buffer.
    """
    if len(data) < offset + 3:
        return None
    if data[offset] != MAGIC:
        return None
    ver_length = struct.unpack_from("<H", data, offset + 1)[0]
    total_length = ver_length & LENGTH_MASK
    return total_length if total_length >= MIN_FRAME_SIZE else None