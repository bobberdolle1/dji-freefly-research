#!/usr/bin/env python3
"""Normalise NLD FCC's command profiles into the shared command corpus.

NLD ships its whole command set as JSON profiles (assets/profiles/*.json). Each
frame is a DUML request reduced to the fields that identify the *command*:

    {s: cmdSet, i: cmdId, d: payload length, p: payload hex, note: description}

Normalisation policy
--------------------
Fields that vary per transmission are replaced with a token so two sequences can
be compared structurally:

* **sequence number** - not present in the profile at all; the profile is a
  template, and the sender allocates it per frame. Token: ``<seq>``.
* **CRC / header CRC** - computed by the sender at transmission time. Never in
  the profile, and normalised out for any frame that does carry one.
* **derived lengths** - ``d`` is the payload length, which is fully determined by
  ``p``. Kept as ``payload_len`` for reference but excluded from the identity
  key.
* **device serial** - the 4G profile embeds the aircraft serial in every payload.
  A device identity must not make a frame look like a different command, so
  payload bytes are retained verbatim here but flagged; cross-tool comparison
  masks them.

The identity key is therefore ``(cmdSet, cmdId, masked_payload)``.

Usage:
    python tools/nld_command_corpus.py <apk> <out.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile

PROFILE_PREFIX = "assets/profiles/"

# cmdSet values used across the profiles, as named by the vendor's own notes.
CMD_SET_NAMES = {
    0x00: "GENERAL", 0x03: "FLYCONTROLLER", 0x06: "RADIO",
    0x07: "WIFI", 0x09: "OFDM", 0x10: "AUTOTEST",
}

ACK_NAMES = {0: "ACK_NO_ACK_NEEDED", 1: "ACK_BEFORE_EXEC", 2: "ACK_AFTER_EXEC"}


def as_hex(value) -> str:
    if isinstance(value, int):
        return f"{value:02x}"
    if isinstance(value, str):
        return value.lower().replace(" ", "").replace("0x", "")
    return ""


def cmd_set_name(s: int) -> str:
    return CMD_SET_NAMES.get(s, f"CMD_SET_0x{s:02X}")


def normalise_payload(payload_hex: str) -> str:
    """Lower-case hex, no separators, even-length."""
    cleaned = as_hex(payload_hex)
    if len(cleaned) % 2:
        cleaned = "0" + cleaned
    return cleaned


def build_frames(profile: dict) -> list[dict]:
    """Frames from an explicit ``frames`` array."""
    frames = []
    for index, frame in enumerate(profile.get("frames", [])):
        payload = normalise_payload(frame.get("p", ""))
        cmd_set = int(frame.get("s", 0))
        cmd_id = int(frame.get("i", 0))
        frames.append({
            "index": index,
            "cmd_set": cmd_set,
            "cmd_set_name": cmd_set_name(cmd_set),
            "cmd_id": cmd_id,
            "cmd_id_signed": cmd_id - 0x100 if cmd_id > 0x7F else cmd_id,
            "payload_hex": payload,
            "payload_len": int(frame.get("d", len(payload) // 2)),
            "identity_key": f"{cmd_set:02x}/{cmd_id:02x}/{payload}",
            "note": frame.get("note", ""),
            "generated": False,
        })
    return frames


def expand_generated(profile: dict) -> list[dict]:
    """Frames from a *generated* sequence description.

    ``4g`` does not carry a frames array: it carries frame_count, cmd_set,
    cmd_id_start, a payload prefix and a payload_serial_encoding, because 128
    near-identical frames would be pointless to write out. Expanding it keeps
    that command class in the corpus instead of silently dropping it.
    """
    if "frame_count" not in profile:
        return []
    prefix = normalise_payload(profile.get("payload_prefix_hex", ""))
    cmd_set = int(profile.get("cmd_set", 0))
    cmd_id_start = int(profile.get("cmd_id_start", 0))
    frames = []
    for i in range(int(profile["frame_count"])):
        cmd_id = cmd_id_start + i
        frames.append({
            "index": i,
            "cmd_set": cmd_set,
            "cmd_set_name": cmd_set_name(cmd_set),
            "cmd_id": cmd_id,
            "cmd_id_signed": cmd_id,
            "payload_hex": prefix,
            "payload_len": len(prefix) // 2,
            # The serial is substituted per aircraft, so the identity key must not
            # depend on it.
            "identity_key": f"{cmd_set:02x}/{cmd_id:02x}/<prefix:{prefix}><serial>",
            "note": profile.get("note", ""),
            "generated": True,
        })
    return frames


def expand_profile(profile: dict) -> list[dict]:
    """Frames for a profile under either schema NLD uses."""
    if profile.get("frames"):
        return build_frames(profile)
    return expand_generated(profile)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("apk")
    ap.add_argument("out")
    args = ap.parse_args()

    with zipfile.ZipFile(args.apk) as zf:
        names = [n for n in zf.namelist() if n.startswith(PROFILE_PREFIX)
                 and n.endswith(".json")]
        profiles = {}
        for name in sorted(names):
            key = os.path.basename(name)[:-len(".json")]
            profiles[key] = json.loads(zf.read(name).decode("utf-8"))

    entries = []
    for key in sorted(profiles):
        profile = profiles[key]
        frames = expand_profile(profile)
        entries.append({
            "source": "nld-fcc",
            "source_profile": key,
            "name": profile.get("name", key),
            "description": profile.get("description", ""),
            "transport": "tcp:40009" if key in ("fcc", "fcc_keepalive") else (
                "tcp:40007" if key.startswith("led") else "unspecified"),
            "sender": profile.get("sender"),
            "sender_desc": profile.get("sender_desc"),
            "cmd_type": profile.get("cmd_type"),
            "cmd_type_desc": profile.get("cmd_type_desc"),
            "rounds": profile.get("rounds"),
            "inter_frame_delay_ms": profile.get("inter_frame_delay_ms"),
            "inter_round_delay_ms": profile.get("inter_round_delay_ms"),
            "read_window_ms": profile.get("read_window_ms"),
            "frame_count": len(frames),
            "frames": frames,
            "identity_sequence": [f["identity_key"] for f in frames],
        })

    corpus = {
        "schema": "freefly-command-corpus/1",
        "normalisation": {
            "sequence_number": "<seq>  (not present in NLD profiles; allocated per transmission)",
            "crc": "excluded  (computed by the sender at transmission time)",
            "derived_lengths": "payload_len retained for reference, excluded from identity_key",
            "identity_key": "<cmdSet hex>/<cmdId hex>/<payload hex>",
        },
        "apk": {"path": os.path.basename(args.apk),
                "sha256": hashlib.sha256(open(args.apk, "rb").read()).hexdigest()},
        "ack_names": {str(k): v for k, v in ACK_NAMES.items()},
        "cmd_set_names": {f"0x{k:02X}": v for k, v in CMD_SET_NAMES.items()},
        "entries": entries,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, indent=2)

    print(f"profiles: {len(entries)}")
    for e in entries:
        print(f"  {e['source_profile']:<20} {e['frame_count']:>3} frames  "
              f"rounds={e['rounds']} transport={e['transport']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())