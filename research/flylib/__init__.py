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

To render frames without a device::

    dry = DryRunTransport()
    dry.send(commands.version_inquiry(next_seq()))

The read path
-------------
The end-to-end read path is ``device -> protocol selection -> parameter
enumeration -> snapshot JSON``:

* :mod:`flylib.crc`, :mod:`flylib.packet` — DUML wire format and checksums
* :mod:`flylib.parser` — streaming framer with resynchronisation
* :mod:`flylib.commands` — one builder per recovered DroneCommands method
* :mod:`flylib.transport` — abstract, replay, scripted, dry-run and live transports
* :mod:`flylib.selection` — 2015/2017 protocol selection policy
* :mod:`flylib.params` — FC parameter type table and value codecs
* :mod:`flylib.snapshot` — capture, export to JSON, import, and compare

Layout
------
``crc``       the two checksums, reimplemented from the APK's own tables
``packet``    DUML header/payload encode and decode
``parser``    streaming framer with resynchronisation
``commands``  one builder per recovered DroneCommands method
``transport`` abstract, replay and dry-run transports
``session``   request/response matching over a transport
``params``    parameter-name hashing and value codecs
``selection`` protocol-selection policy
``snapshot``  parameter snapshot serialisation
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
from .params import ParamType, decode_value, encode_value
from .selection import IndexMapStore, select_parameters
from .snapshot import Snapshot, SnapshotError, SnapshotParameter, build_snapshot
from .guard import MutationGuard, MutationNotAllowed, is_state_changing
from .transport import (DryRunTransport, LiveTransport, ReplayTransport,
                        ScriptedTransport, Session, Transport)

next_seq = SequenceCounter()

__all__ = [
    "crc8", "crc16", "MAGIC", "HEADER_SIZE", "MIN_FRAME_SIZE", "Packet",
    "build_packet", "parse_packet", "parse_header", "pack_dev_byte",
    "unpack_dev_byte", "DEV_PC", "DEV_FC", "DEV_CENTER", "CMD_SET_COMMON",
    "CMD_SET_FC", "PKT_REQUEST", "PKT_RESPONSE", "ACK_NO_ACK",
    "ACK_BEFORE_EXEC", "ACK_AFTER_EXEC", "StreamParser", "SequenceCounter",
    "next_seq", "param_hash", "ParamType", "decode_value", "encode_value",
    "select_parameters", "IndexMapStore", "Snapshot", "SnapshotError",
    "SnapshotParameter", "build_snapshot", "MutationGuard", "MutationNotAllowed",
    "is_state_changing", "Transport", "ReplayTransport", "ScriptedTransport",
    "DryRunTransport", "LiveTransport", "Session",
]
__version__ = "0.3.0"