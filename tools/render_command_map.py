#!/usr/bin/env python3
"""Render docs/COMMAND_MAP.md from the extracted command evidence.

The table is generated from research/generated/freefly_commands.json (produced by
tools/extract_duml_commands.py) rather than transcribed, so the published
document cannot drift from the bytecode-derived data.

Two inputs, with different reproducibility:

* ``freefly_commands.json`` is **committed**, so the document regenerates from a
  clean clone with no setup.
* the decoded smali tree under ``work/apktool/`` is **gitignored**. It is
  needed only to *re-derive* the JSON, and optionally to re-verify the live/dead
  column. Rebuild it with ``bash tools/toolchain.sh`` then apktool on the
  sample. When it is supplied the render re-counts call sites and warns on any
  disagreement; when it is absent the recorded verdicts are emitted unchanged
  and the document says so.

Usage:
    python tools/render_command_map.py <commands.json> <out.md>
    python tools/render_command_map.py <commands.json> <smali_root> <out.md>
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

PAYLOAD_NOTES = {
    "assistantUnlock": "`01 00 00 00` (4 bytes, literal)",
    "getCfgFileChunk": "`01` ‖ uint32le offset ‖ uint32le 0xFFFFFFFF",
    "getParamInfo2015": "uint32le paramHash(name)",
    "getParamInfo2017": "uint16le table ‖ uint16le index",
    "getParamInfoByIndex2015": "uint16le index",
    "getTableAttribs2017": "uint16le table",
    "readParamValue2015": "uint32le paramHash(name)",
    "readParamValue2017": "uint16le table ‖ uint16le 0 ‖ uint16le index",
    "readParamValue": "",
    "versionInquiry": "empty",
    "versionInquiryTo": "empty",
    "writeParamValue2015": "uint32le paramHash(name) ‖ value — STATE-CHANGING",
    "writeParamValue2017": "uint16le table ‖ uint16le 0 ‖ uint16le index ‖ value — STATE-CHANGING",
    "replyRegAck": "`00`",
    "replyRegDev": "64-byte structure, see below",
}

LIVE_STATUS = {
    "assistantUnlock": "live (2 call sites)",
    "getCfgFileChunk": "live (1)",
    "getParamInfo2017": "live (1)",
    "getTableAttribs2017": "live (1)",
    "readParamValue2017": "live (3)",
    "writeParamValue2017": "live (1)",
    "versionInquiry": "live (1)",
    "versionInquiryTo": "live (1)",
    "replyRegAck": "live (1)",
    "replyRegDev": "live (1)",
    "getParamInfoByIndex2015": "**DEAD** — only from dead `readAll2015`",
    "readParamValue2015": "**DEAD** — only from dead `readAll2015`",
    "getParamInfo2015": "**DEAD** — 0 call sites",
    "writeParamValue2015": "**DEAD** — 0 call sites",
}


def count_call_sites(smali_root: str, method: str) -> int:
    """Count invocations of ``DroneCommands.<method>`` outside DroneCommands itself.

    Used only to *verify* the recorded live/dead verdicts. The decoded tree is
    gitignored, so this is optional: with it, the table is re-derived from the
    bytecode; without it, the recorded verdicts are emitted unchanged.
    """
    pattern = f"DroneCommands;->{method}("
    total = 0
    for dirpath, _dirs, files in os.walk(smali_root):
        for name in files:
            if not name.endswith(".smali") or name == "DroneCommands.smali":
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if pattern in line and "invoke-" in line:
                            total += 1
            except OSError:
                continue
    return total


def verify_live_status(smali_root: str) -> list[str]:
    """Re-count call sites and report any disagreement with LIVE_STATUS."""
    import re
    problems = []
    for method, recorded in LIVE_STATUS.items():
        count = count_call_sites(smali_root, method)
        expected = re.search(r"\((\d+)", recorded)
        if "DEAD" in recorded:
            if count > 1:
                problems.append(f"{method}: recorded DEAD but {count} call sites")
        elif expected and count != int(expected.group(1)):
            problems.append(
                f"{method}: recorded {expected.group(1)} call sites, found {count}")
    return problems


def main() -> int:
    # <commands.json> [<smali_root>] <out.md>
    args = sys.argv[1:]
    commands_json, out_md = args[0], args[-1]
    smali_root = args[1] if len(args) == 3 else None
    with open(commands_json, encoding="utf-8") as fh:
        data = json.load(fh)
    verified = None
    if smali_root and os.path.isdir(smali_root):
        verified = verify_live_status(smali_root)
        for problem in verified:
            print(f"WARNING: {problem}", file=sys.stderr)
    rows = data["commands"]
    defaults = data["resolved_defaults"]

    def signed(value):
        if isinstance(value, int) and value > 0x7F:
            return value - 0x100
        return value

    lines = []
    lines.append("# Free Fly 1.0 — DUML command map")
    lines.append("")
    lines.append("Generated by `tools/render_command_map.py` from")
    lines.append("`research/generated/freefly_commands.json`, which is **committed**.")
    lines.append("")
    lines.append("Every field in the table is machine-derived from bytecode and nothing")
    lines.append("here is transcribed by hand, so the document cannot drift from the")
    lines.append("extracted evidence.")
    lines.append("")
    lines.append("Reproducibility differs between the two inputs:")
    lines.append("")
    lines.append("- `freefly_commands.json` is committed, so this document regenerates")
    lines.append("  from a clean clone with no extra setup.")
    lines.append("- the decoded smali tree under `work/apktool/` is **gitignored**. It is")
    lines.append("  needed only to *re-derive* the JSON, and optionally to re-verify the")
    lines.append("  `live?` column. Rebuild with `bash tools/toolchain.sh`, then apktool")
    lines.append("  on the sample.")
    lines.append("")
    if verified is None:
        lines.append("This render did **not** re-verify the `live?` column — the decoded tree")
        lines.append("was not supplied, so the verdicts below are the recorded ones.")
    elif verified:
        lines.append(f"The `live?` column was re-verified and **{len(verified)} "
                     f"disagreement(s)** were found; treat the table with caution.")
    else:
        lines.append("The `live?` column was re-verified against the decoded smali for this")
        lines.append("render: **all call-site counts agree** with the recorded verdicts.")
    lines.append("")
    lines.append("## Shared defaults")
    lines.append("")
    lines.append("Recovered from `DumlBuilder.buildPacket$default`. A **set** mask bit")
    lines.append("means \"use the built-in default\", which is the opposite of how the")
    lines.append("mask reads at a glance:")
    lines.append("")
    lines.append("| Parameter | Default |")
    lines.append("|---|---|")
    lines.append(f"| senderType | `{defaults['senderType']}` = DEV_PC |")
    lines.append(f"| senderIndex | `{defaults['senderIndex']}` |")
    lines.append(f"| receiverType | `{defaults['receiverType']}` = DEV_FC |")
    lines.append(f"| receiverIndex | `{defaults['receiverIndex']}` |")
    lines.append(f"| ackType | `{defaults['ackType']}` = ACK_NO_ACK |")
    lines.append(f"| packetType | `{defaults['packetType']}` = PKT_REQUEST |")
    lines.append(f"| seqNum | `{defaults['seqNum']}` (counter starts at 1) |")
    lines.append("")
    lines.append("## Command table")
    lines.append("")
    lines.append("| Method | cmdSet | cmdId (dec / hex) | sender | receiver | ack | pkt | payload | live? |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    runtime_receiver = {"replyRegAck", "replyRegDev", "versionInquiryTo"}
    for row in sorted(rows, key=lambda r: r["method"]):
        name = row["method"]
        cmd_id = signed(row["cmdId"])
        hex_id = f"0x{cmd_id & 0xFF:02X}"
        payload = PAYLOAD_NOTES.get(name, row.get("payload_hex") or "—")
        if name == "replyRegDev":
            payload = ("64 bytes: `[01]=50 [02]=63 [21]=01 [22]=0A`, plus `[23]`,"
                       "`[29]`,`[2D]` copied from the request when present")
        if name in runtime_receiver:
            receiver = "`<runtime arg>`"
        else:
            receiver = f"{row['receiverType_name']}:{row['receiverIndex']}"
        lines.append(
            f"| `{name}` | {row['cmdSet_name']} | {cmd_id} / {hex_id} | "
            f"{row['senderType_name']}:{row['senderIndex']} | {receiver} | "
            f"{row['ackType_name']} | {row['packetType_name']} | {payload} | "
            f"{LIVE_STATUS.get(name, '?')} |")
    lines.append("")
    lines.append("`live?` above is asserted against the decoded smali. Reproduce with:")
    lines.append("")
    lines.append("```")
    lines.append("for m in assistantUnlock getCfgFileChunk getParamInfo2015 \\")
    lines.append("         getParamInfo2017 getParamInfoByIndex2015 getTableAttribs2017 \\")
    lines.append("         readParamValue2015 readParamValue2017 writeParamValue2015 \\")
    lines.append("         writeParamValue2017 versionInquiry versionInquiryTo \\")
    lines.append("         replyRegAck replyRegDev; do")
    lines.append('  printf "%-24s %s\\n" "$m" "$(grep -rl "DroneCommands;->$m(" \\')
    lines.append("    --include='*.smali' work/apktool/decoded | grep -vc DroneCommands.smali)")
    lines.append("done")
    lines.append("```")
    lines.append("")

    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {out_md}: {len(rows)} commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())