"""Flight-controller parameter types and value codecs.

The type table is DJI's canonical FC parameter set. It was read from the APK's
``ParamType`` enum and cross-checked against the ``packed-switch`` in
``DroneRepository.parseRawValue``; the Kotlin ``WhenMappings`` constructor
assigns switch keys in declaration order, so the switch key is
``ordinal + 1`` and the **enum ordinal is the on-the-wire type id**.

===========  ====  ==============  ===========================
Type id      Ord  Width (bytes)    Java reader
===========  ====  ==============  ===========================
``UINT8``    0    1                ``ByteBuffer.get()``
``UINT16``   1    2                ``getShort()``
``UINT32``   2    4                ``getInt()``
``UINT64``   3    8                ``getLong()``
``INT8``     4    1                ``get()``
``INT16``    5    2                ``getShort()``
``INT32``    6    4                ``getInt()``
``INT64``    7    8                ``getLong()``
``FLOAT``    8    4                ``getFloat()``
``DOUBLE``   9    8                ``getDouble()``
===========  ====  ==============  ===========================

All values are **little-endian**. Every decode is length-guarded: a payload
shorter than the type requires yields ``None`` rather than raising or reading
past the end. That is the app's behaviour and it is worth preserving, because a
truncated parameter reply is a normal condition on a noisy USB link and should
degrade to "no value" rather than an exception.


**Where this deliberately diverges from Free Fly.** The app's
``DroneRepository.parseRawValue`` returns a Kotlin ``Double``, so every value —
including 64-bit integers — passes through double precision and anything above
2**53 is silently rounded by the app. ``flylib`` returns the **exact Python
int** for the integer types and raises :attr:`DecodedValue.lossy` instead. That
is an improvement, not a reproduction: when describing what Free Fly does, its
parameter values are double-precision and 64-bit integers are not exact.
"""
from __future__ import annotations

import dataclasses
import enum
import struct

class ParamType(enum.IntEnum):
    """Type id as carried on the wire and declared by the app's enum."""

    UINT8 = 0
    UINT16 = 1
    UINT32 = 2
    UINT64 = 3
    INT8 = 4
    INT16 = 5
    INT32 = 6
    INT64 = 7
    FLOAT = 8
    DOUBLE = 9


#: Wire width in bytes for each type.
WIDTH: dict[ParamType, int] = {
    ParamType.UINT8: 1, ParamType.UINT16: 2, ParamType.UINT32: 4,
    ParamType.UINT64: 8, ParamType.INT8: 1, ParamType.INT16: 2,
    ParamType.INT32: 4, ParamType.INT64: 8, ParamType.FLOAT: 4,
    ParamType.DOUBLE: 8,
}

#: Struct format characters, little-endian, for each type.
_FORMAT: dict[ParamType, str] = {
    ParamType.UINT8: "<B", ParamType.UINT16: "<H", ParamType.UINT32: "<I",
    ParamType.UINT64: "<Q", ParamType.INT8: "<b", ParamType.INT16: "<h",
    ParamType.INT32: "<i", ParamType.INT64: "<q", ParamType.FLOAT: "<f",
    ParamType.DOUBLE: "<d",
}

SIGNED = frozenset({ParamType.INT8, ParamType.INT16, ParamType.INT32,
                    ParamType.INT64, ParamType.FLOAT, ParamType.DOUBLE})

#: Values at or above this magnitude are not exactly representable as a double.
EXACT_INTEGER_LIMIT = 2 ** 53


class MalformedParameter(ValueError):
    """Raised when a payload cannot be interpreted at all."""


@dataclasses.dataclass(frozen=True)
class DecodedValue:
    """A decoded parameter value plus the precision caveat, if any."""

    value: float | int | None
    type: ParamType
    lossy: bool = False

    def __float__(self) -> float:
        if self.value is None:
            raise ValueError("no value: the payload was too short for its type")
        return float(self.value)


def decode_value(data: bytes, type_: ParamType) -> DecodedValue:
    """Decode one little-endian parameter value.

    Returns ``DecodedValue(value=None)`` when ``data`` is shorter than the
    type's width — the app's behaviour, and the right one on a link that can
    deliver truncated frames.
    """
    width = WIDTH[type_]
    if len(data) < width:
        return DecodedValue(value=None, type=type_)

    (raw,) = struct.unpack_from(_FORMAT[type_], data, 0)
    if type_ in (ParamType.FLOAT, ParamType.DOUBLE):
        return DecodedValue(value=float(raw), type=type_)

    lossy = abs(int(raw)) >= EXACT_INTEGER_LIMIT
    return DecodedValue(value=raw, type=type_, lossy=lossy)


def encode_value(value, type_: ParamType) -> bytes:
    """Encode a parameter value to its little-endian wire form.

    This is the *write* direction. Callers must obtain explicit permission via
    :mod:`flylib.guard` before putting the result on a device; this function
    only formats bytes and performs no I/O.
    """
    width = WIDTH[type_]
    fmt = _FORMAT[type_]
    try:
        if type_ in (ParamType.FLOAT, ParamType.DOUBLE):
            return struct.pack(fmt, float(value))
        if type_ in SIGNED:
            return struct.pack(fmt, int(value))
        ivalue = int(value)
        if not 0 <= ivalue < (1 << (width * 8)):
            raise ValueError(f"{ivalue} does not fit in {type_.name}")
        return struct.pack(fmt, ivalue)
    except (struct.error, OverflowError) as exc:
        raise MalformedParameter(f"cannot encode {value!r} as {type_.name}: {exc}") from exc


def index_addressed(protocol: str) -> bool:
    """2017 parameters are addressed by ``(table, index)``; 2015 by name hash.

    **FACT** from the request builders: ``readParamValue2017(tableNo, paramIndex)``
    takes two integers, while ``readParamValue2015(name)`` takes a name and
    hashes it. There is no 2017 name field on the wire.
    """
    return protocol == "2017"