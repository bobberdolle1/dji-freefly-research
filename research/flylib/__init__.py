"""flylib — clean-room, read-only-first DJI DUML diagnostics library.

Scope and safety
----------------
This package implements the DUML transport and the FC Assistant parameter
protocol as observed in Free Fly 1.0. It is built for *reading* aircraft state.
Nothing here can change aircraft state unless the caller explicitly opts in
through :mod:`flylib.guard`, which is disabled by default.

Read-only by default::

    from flylib import ReplayTransport, Session

    session = Session(ReplayTransport.from_hexfile("capture.hex"))
    info = session.query_device_info()      # sends reads only

To render frames without a device::

    dry = DryRunTransport()
    dry.send(commands.version_inquiry(1))

The read path
-------------
``device -> protocol selection -> parameter enumeration -> snapshot JSON ->
replay``. Each stage is usable on its own, and the whole chain runs with no
drone, no network and no Android runtime:

``crc``        the two checksums, reimplemented from the APK's own tables
``packet``     DUML header/payload encode and decode
``parser``     streaming framer with resynchronisation
``commands``   one builder per recovered DroneCommands method
``params``     FC parameter type table and value codecs
``selection``  protocol-selection policy (2017, with the 2015 dead code excluded)
``snapshot``   parameter snapshot serialisation, import and comparison
``replay``     capture from a source, and replay a snapshot without a device
``transport``  abstract, replay, scripted, dry-run and live transports
``guard``      the mutation gate, disabled by default
"""
from .crc import crc8, crc16
from .packet import (ACK_AFTER_EXEC, ACK_BEFORE_EXEC, ACK_NO_ACK, CMD_SET_COMMON,
                     CMD_SET_FC, DEV_CENTER, DEV_FC, DEV_PC, HEADER_SIZE, MAGIC,
                     MIN_FRAME_SIZE, PKT_REQUEST, PKT_RESPONSE, Packet,
                     build_packet, pack_dev_byte, parse_header, parse_packet,
                     unpack_dev_byte)
from .parser import StreamParser
from .commands import SequenceCounter, param_hash
from .params import ParamType, decode_value, encode_value
from .selection import IndexMapStore, select_parameters
from .snapshot import Snapshot, SnapshotError, SnapshotParameter, build_snapshot
from .replay import (ReplayParameterSource, SnapshotReplayTransport, capture,
                     snapshot_document, source_from_snapshot)
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
    "SnapshotParameter", "build_snapshot", "capture", "snapshot_document",
    "source_from_snapshot", "ReplayParameterSource", "SnapshotReplayTransport",
    "MutationGuard", "MutationNotAllowed", "is_state_changing", "Transport",
    "ReplayTransport", "ScriptedTransport", "DryRunTransport", "LiveTransport",
    "Session",
]
__version__ = "0.4.0"