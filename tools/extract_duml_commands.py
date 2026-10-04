#!/usr/bin/env python3
"""Extract the DUML command table from DroneCommands.smali.

Every DUML transaction Free Fly can send is one method on DroneCommands that
fills a payload array and calls DumlBuilder.buildPacket$default. Reading 1300
lines of smali by hand is exactly how sender/receiver/ack-type get mixed up, so
the constants are extracted mechanically:

  * `fill-array-data vN, :array_K` plus the `:array_K ... .end array-data` block
    gives the literal request payload;
  * the register constants immediately preceding the buildPacket$default call
    give the explicitly-passed arguments;
  * the trailing mask says which arguments were *omitted* at the call site.

The mask is the subtle part and is the reason this tool exists. Kotlin's
`buildPacket$default` dispatches on it with the sense inverted from what it
looks like: a **set** bit means "use the built-in default", a **clear** bit means
"use the value the caller passed". The built-in defaults live in
buildPacket$default itself (senderType=DEV_PC, senderIndex=1, receiverType=DEV_FC,
receiverIndex=0, ackType=0, packetType=0, seqNum=nextSeq()), and they are
re-derived here from that method rather than hardcoded, so a change in the APK
cannot silently invalidate the table.

Usage:
    python tools/extract_duml_commands.py <DroneCommands.smali> \
        --builder <DumlBuilder.smali> [--constants <DumlConstants.smali>] \
        [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re

# Names for readability; the values themselves come from the smali, not here.
DEVICES = {0: "DEV_ANY", 1: "DEV_CAMERA", 2: "DEV_APP", 3: "DEV_FC",
           4: "DEV_GIMBAL", 5: "DEV_CENTER", 6: "DEV_RC", 10: "DEV_PC"}
ACK = {0: "ACK_NO_ACK", 1: "ACK_BEFORE_EXEC", 2: "ACK_AFTER_EXEC"}
PKT = {0: "PKT_REQUEST", 1: "PKT_RESPONSE"}
CMD_SETS = {0: "CMD_SET_COMMON", 1: "CMD_SET_SPECIAL", 3: "CMD_SET_FC"}

# Parameter order of DumlBuilder.buildPacket.
BUILD_ARGS = ["cmdSet", "cmdId", "payload", "senderType", "senderIndex",
              "receiverType", "receiverIndex", "ackType", "packetType", "seqNum"]
# buildPacket$default mask: a SET bit means "use the built-in default". Keys are
# the mask's bit *positions*, which is what `(mask >> slot) & 1` needs; the
# bytecode tests them as bit values (`and-int/lit8 v1, v0, 0x8` for slot 3).
MASK_SLOT = {3: "senderType", 4: "senderIndex", 5: "receiverType",
             6: "receiverIndex", 7: "ackType", 8: "packetType", 9: "seqNum"}

METHOD_RE = re.compile(r"^\.method\s+.*?\s(?P<name>\w+)\((?P<args>[^)]*)\)")
ARRAY_LABEL_RE = re.compile(r"^\s*:(?P<label>array_\d+)\s*$")
CONST_RE = re.compile(r"^\s*const(?:/(?:4|16|)\s+)(?P<reg>v\d+),\s*(?P<val>-?0x[0-9a-fA-F]+|\d+)")
MOVE_OBJ_RE = re.compile(r"^\s*move-object(?:-from16)?\s+(?P<dst>v\d+),\s*(?P<src>v\d+)")
FILL_RE = re.compile(r"^\s*fill-array-data\s+(?P<reg>v\d+),\s*:(?P<label>array_\d+)")
FIELD_RE = re.compile(
    r"^\.field public static final (?P<name>[A-Z0-9_]+):B = (?P<val>-?0x[0-9a-fA-F]+|\d+)t\s*$",
    re.M)


def parse_int(text: str) -> int:
    """Parse a smali integer literal, honouring 8-bit sign extension.

    Smali suffixes bare hex literals with a type marker (`0x1t`, `-0x21t`), which
    must be stripped before conversion.
    """
    text = text.rstrip("t")
    short = re.fullmatch(r"-?0x[0-9a-fA-F]{1,2}", text) is not None
    value = int(text, 16) if text.startswith(("0x", "-0x")) else int(text)
    if short:
        value &= 0xFF
        if value >= 0x80:
            value -= 0x100
    return value


def parse_const_fields(path: str) -> dict[str, int]:
    """Read DumlConstants.smali so command ids are never hardcoded here."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}
    return {m.group("name"): parse_int(m.group("val"))
            for m in FIELD_RE.finditer(text)}


def parse_defaults(builder_path: str) -> dict[str, object]:
    """Recover buildPacket$default's built-in defaults from its own bytecode.

    Each default is guarded by `and-int/litN vA, v0, 0xNN` followed by
    `if-eqz vA, :cond_N`. `if-eqz` jumps when the mask bit is *clear*, i.e. to
    the caller-supplied value, so the instructions between the test and the
    label are the built-in default. Resolving the label rather than scanning for
    "the next constant" is what keeps this correct once `.line` directives are
    interleaved with the loads.
    """
    with open(builder_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    start = next((i for i, l in enumerate(lines)
                  if "buildPacket$default" in l and l.startswith(".method")), None)
    if start is None:
        raise SystemExit("buildPacket$default not found")
    stop = next((i for i in range(start + 1, len(lines))
                 if lines[i].startswith(".method")), len(lines))
    body = lines[start + 1:stop]

    labels: dict[str, int] = {}
    for i, line in enumerate(body):
        m = re.match(r"^\s*:(?P<label>\w+)\s*$", line)
        if m:
            labels[m.group("label")] = i

    # Registers are reused across the method (v1 carries a different default in
    # every branch), so a method-wide register->constant map silently resolves
    # every default to the last one. Blocks are therefore resolved on their own,
    # falling back to the method-wide map only for hoisted constants such as the
    # shared `const/4 v2, 0x0`.
    consts: dict[int, int] = {}
    for line in body:
        c = re.match(r"^\s*const(?:/4|/16|/)\s+v(?P<r>\d+),\s*"
                     r"(?P<num>-?0x[0-9a-fA-F]+|\d+)", line)
        if c:
            consts[int(c.group("r"))] = parse_int(c.group("num"))

    defaults: dict[str, object] = {}
    for i, line in enumerate(body):
        m = re.match(r"^\s*and-int/lit(?:8|16)\s+v\d+,\s*v0,\s*"
                     r"(?P<bit>0x[0-9a-fA-F]+)\s*$", line)
        if not m:
            continue
        position = int(m.group("bit"), 16).bit_length() - 1
        slot = MASK_SLOT.get(position)
        if slot is None:
            continue
        jump = next((l for l in body[i + 1:i + 6]
                     if re.match(r"^\s*if-eqz\s", l)), None)
        if jump is None:
            defaults[slot] = None
            continue
        label = re.match(r"^\s*if-eqz\s+v\d+,\s*:(?P<label>\w+)",
                         jump).group("label")
        defaults[slot] = _resolve_block(body[i + 1:labels.get(label, len(body))], consts)
    return defaults


def _resolve_block(block: list[str], consts: dict[int, int]) -> object:
    """The value a default-path block leaves in the outgoing register."""
    local: dict[int, int] = {}
    outgoing: object = None
    for line in block:
        if "nextSeq()I" in line:
            return "nextSeq()"
        c = re.match(r"^\s*const(?:/4|/16|/)\s+v(?P<r>\d+),\s*"
                     r"(?P<num>-?0x[0-9a-fA-F]+|\d+)", line)
        if c:
            local[int(c.group("r"))] = parse_int(c.group("num"))
            outgoing = local[int(c.group("r"))]
            continue
        m = re.match(r"^\s*move(?:/from16)?\s+v(?P<dst>\d+),\s*v(?P<src>\d+)\s*$", line)
        if m:
            src = int(m.group("src"))
            if src in local:
                local[int(m.group("dst"))] = local[src]
                outgoing = local[src]
            elif src in consts:
                local[int(m.group("dst"))] = consts[src]
                outgoing = consts[src]
    return outgoing


def parse_arrays(lines: list[str]) -> dict[str, bytes]:
    """Map :array_N labels to their literal bytes."""
    arrays: dict[str, bytes] = {}
    i = 0
    while i < len(lines):
        m = ARRAY_LABEL_RE.match(lines[i])
        if not m:
            i += 1
            continue
        label = m.group("label")
        i += 1
        if i >= len(lines) or ".array-data" not in lines[i]:
            continue
        width = int(lines[i].split()[-1])
        vals: list[int] = []
        i += 1
        while i < len(lines) and ".end array-data" not in lines[i]:
            stripped = lines[i].strip()
            if stripped and not stripped.startswith("."):
                for tok in stripped.split():
                    if re.fullmatch(r"-?0x[0-9a-fA-F]{1,2}t?", tok):
                        vals.append(parse_int(tok))
            i += 1
        arrays[label] = (bytes(v & 0xFF for v in vals) if width == 1
                         else b"".join((v & ((1 << (width * 8)) - 1)).to_bytes(width, "little")
                                       for v in vals))
    return arrays


def parse_methods(path: str) -> list[tuple[str, list[str], list[str]]]:
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    methods: list[tuple[str, list[str], list[str]]] = []
    name: str | None = None
    margs: list[str] = []
    body: list[str] = []
    for line in lines:
        if line.startswith(".method"):
            m = METHOD_RE.match(line)
            name = m.group("name") if m else None
            margs = m.group("args").split() if m else []
            body = []
            continue
        if line.startswith(".end method"):
            if name:
                methods.append((name, margs, body))
            name, margs, body = None, [], []
            continue
        if name:
            body.append(line)
    return methods


def analyse(body: list[str], arrays: dict[str, bytes]) -> dict | None:
    """Resolve one buildPacket$default call site into explicit arguments.

    The argument registers are not at fixed numbers: each method allocates its
    own locals, so `invoke-static/range {vA .. vB}` is what establishes the base
    register. Assuming v0 is always the builder silently attributes a payload
    index or a ByteBuffer length to cmdId.
    """
    call = next((i for i, l in enumerate(body) if "buildPacket$default" in l), None)
    if call is None:
        return None
    span = re.search(r"invoke-static/range\s*\{v(?P<a>\d+)\s*\.\.\s*v(?P<b>\d+)\}",
                     body[call])
    if span is None:
        return None
    base = int(span.group("a"))

    regs: dict[int, object] = {}
    for line in body[:call]:
        c = CONST_RE.match(line)
        if c:
            regs[int(c.group("reg")[1:])] = parse_int(c.group("val"))
            continue
        f = FILL_RE.match(line)
        if f:
            regs[int(f.group("reg")[1:])] = arrays.get(f.group("label"))
            continue
        m = MOVE_OBJ_RE.match(line)
        if m:
            dst, src = int(m.group("dst")[1:]), int(m.group("src")[1:])
            if isinstance(regs.get(src), bytes):
                regs[dst] = regs[src]

    # base+0 is the DumlBuilder receiver, then the declared buildPacket order.
    offset = {"cmdSet": 1, "cmdId": 2, "payload": 3, "senderType": 4,
              "senderIndex": 5, "receiverType": 6, "receiverIndex": 7,
              "ackType": 8, "packetType": 9, "seqNum": 10, "mask": 11}
    explicit = {k: regs.get(base + n) for k, n in offset.items()}
    if not isinstance(explicit["mask"], int):
        return None
    return {"base": base, "mask": explicit.pop("mask"), "explicit": explicit}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("smali", help="path to DroneCommands.smali")
    ap.add_argument("--builder", help="path to DumlBuilder.smali")
    ap.add_argument("--constants", help="path to DumlConstants.smali")
    ap.add_argument("--json", help="write machine-readable output here")
    args = ap.parse_args()

    defaults = parse_defaults(args.builder) if args.builder else {}
    constants = parse_const_fields(args.constants) if args.constants else {}

    with open(args.smali, encoding="utf-8") as fh:
        arrays = parse_arrays(fh.read().splitlines())

    rows = []
    for name, margs, body in parse_methods(args.smali):
        info = analyse(body, arrays)
        if info is None:
            continue
        mask = info["mask"]
        resolved: dict[str, object] = {}
        for key in BUILD_ARGS:
            if key in ("payload", "cmdSet", "cmdId"):
                # never defaulted: cmdSet/cmdId are required arguments and the
                # payload is taken verbatim from the call site
                resolved[key] = info["explicit"].get(key)
                continue
            slot = next(s for s, k in MASK_SLOT.items() if k == key)
            resolved[key] = defaults.get(key) if (mask >> slot) & 1 \
                else info["explicit"].get(key)
        payload = resolved["payload"] if isinstance(resolved["payload"], bytes) else b""
        rows.append({
            "method": name,
            "signature_args": margs,
            "mask": f"0x{mask:03x}",
            "cmdSet": resolved["cmdSet"],
            "cmdSet_name": CMD_SETS.get(resolved["cmdSet"], resolved["cmdSet"]),
            "cmdId": resolved["cmdId"],
            "cmdId_signed8": (resolved["cmdId"] - 0x100
                              if isinstance(resolved["cmdId"], int)
                              and resolved["cmdId"] > 0x7F else resolved["cmdId"]),
            "cmdId_constant": next((k for k, v in constants.items()
                                    if v == resolved["cmdId"]), None),
            "senderType": resolved["senderType"],
            "senderType_name": DEVICES.get(resolved["senderType"]),
            "senderIndex": resolved["senderIndex"],
            "receiverType": resolved["receiverType"],
            "receiverType_name": DEVICES.get(resolved["receiverType"]),
            "receiverIndex": resolved["receiverIndex"],
            "ackType": resolved["ackType"],
            "ackType_name": ACK.get(resolved["ackType"]),
            "packetType": resolved["packetType"],
            "packetType_name": PKT.get(resolved["packetType"]),
            "seqNum": resolved["seqNum"],
            "payload_hex": payload.hex(" ") if payload else None,
            "payload_len": len(payload),
        })

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"resolved_defaults": defaults, "commands": rows}, fh, indent=2)

    print(f"defaults recovered from buildPacket$default: {defaults}\n")
    header = (f"{'method':26} {'cmdSet':14} {'cmdId':>5} {'sender':>11} "
              f"{'receiver':>11} {'ack':16} {'pkt':10} {'seq':9} payload")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['method']:26} {str(r['cmdSet_name']):14} {str(r['cmdId']):>5} "
              f"{str(r['senderType_name']) + ':' + str(r['senderIndex']):>11} "
              f"{str(r['receiverType_name']) + ':' + str(r['receiverIndex']):>11} "
              f"{str(r['ackType_name']):16} {str(r['packetType_name']):10} "
              f"{str(r['seqNum']):9} {r['payload_hex'] or ''}")
    print(f"\n{len(rows)} command builders resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())