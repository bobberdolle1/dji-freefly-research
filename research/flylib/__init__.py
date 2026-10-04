"""flylib — clean-room, read-only-first DJI DUML diagnostics library.

Scope and safety
----------------
This package implements the DUML transport and the FC Assistant parameter
protocol as observed in Free Fly 1.0. It is built for *reading* aircraft state.
Nothing here can change aircraft state unless the caller explicitly opts in
through :mod:`flylib.guard`, which is disabled by default.

Read-only by default::

    from flylib import ReplayTransport, Session, next_seq

    session = Session(ReplayTransport.from_hexfile("capture.hex"))
    info = session.query_device_info()      # sends reads only

To emit frames without a device::

    dry = DryRunTransport()
    dry.send(commands.version_inquiry(next_seq()))

Layout
------
``crc``       the two checksums, reimplemented from the APK's own tables
``packet``    DUML header/payload encode and decode
``parser``    streaming framer with resynchronisation
``commands``  one builder per recovered DroneCommands method
``transport`` abstract, replay and dry-run transports
``session``   request/response matching over a transport
``params``    parameter-name hashing and value codecs
``guard``     the mutation gate, disabled by default
"""
from .crc import crc8, crc16
from .packet import (ACK_AFTER_EXEC, ACK_BEFORE_EXEC, ACK_NO_ACK, CMD_SET_COMMON,
                     CMD_SET_FC, DEV_CENTER, DEV_FC, DEV_PC, HEADER_SIZE, MAGIC,
                     MIN_FRAME_SIZE, PKT_REQUEST, PKT_RESPONSE, Packet,
                     build_packet, parse_header, parse_packet, pack_dev_byte,
                     unpack_dev_byte)
from .parser import StreamParser
from .commands import SequenceCounter, param_hash
from .guard import MutationGuard, MutationNotAllowed, is_state_changing
from .transport import (DryRunTransport, LiveTransport, ReplayTransport,
                        ScriptedTransport, Session, Transport)

__all__ = [
    "crc8", "crc16", "MAGIC", "HEADER_SIZE", "MIN_FRAME_SIZE", "Packet",
    "build_packet", "parse_packet", "parse_header", "pack_dev_byte",
    "unpack_dev_byte", "DEV_PC", "DEV_FC", "DEV_CENTER", "CMD_SET_COMMON",
    "CMD_SET_FC", "PKT_REQUEST", "PKT_RESPONSE", "ACK_NO_ACK",
    "ACK_BEFORE_EXEC", "ACK_AFTER_EXEC", "StreamParser", "SequenceCounter",
    "param_hash", "MutationGuard", "MutationNotAllowed", "is_state_changing",
    "Transport", "ReplayTransport", "ScriptedTransport", "DryRunTransport",
    "LiveTransport", "Session",
]
__version__ = "0.2.0"