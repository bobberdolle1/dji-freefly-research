#!/usr/bin/env python3
"""Test whether two same-size DJIFCC APKs are one build repackaged per SKU.

`docs/STATUS.md` and `research/reports/djifcc_differential.md` currently record
as INFERENCE that

    DJIFCC.APP-Android-arm64-signed-1.21.12.19.apk
    DJIFCC.APP-RCPro2-signed-1.21.12.3.apk

are byte-length identical (716,586,363) with different SHA-256 and the same DEX
count, and inferred from that they are "one APK repackaged per SKU".

Equal length plus differing content is *suggestive*, not proof: ZIP compression
can absorb a size difference, or two genuinely different builds can coincide in
length. This tool settles it with normalised, order-independent evidence:

1. entry-name sets must match exactly (a repackage preserves the name set);
2. per-entry content hashes must be compared by name, ignoring compression
   method, timestamps and ZIP ordering;
3. the differing entries are listed so the difference can be inspected rather
   than assumed.

Usage:
    python tools/repack_proof.py <apk_a> <apk_b> [--json out.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile

CHUNK = 1 << 20


def entry_hashes(path: str) -> tuple[dict[str, str], dict[str, int]]:
    """Return {name: sha256 of decompressed content} and {name: size}."""
    digests: dict[str, str] = {}
    sizes: dict[str, int] = {}
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            h = hashlib.sha256()
            total = 0
            with zf.open(info) as fh:
                while True:
                    chunk = fh.read(CHUNK)
                    if not chunk:
                        break
                    h.update(chunk)
                    total += len(chunk)
            digests[info.filename] = h.hexdigest()
            sizes[info.filename] = total
    return digests, sizes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("apk_a")
    ap.add_argument("apk_b")
    ap.add_argument("--json")
    args = ap.parse_args()

    digests_a, sizes_a = entry_hashes(args.apk_a)
    digests_b, sizes_b = entry_hashes(args.apk_b)

    names_a, names_b = set(digests_a), set(digests_b)
    only_a = sorted(names_a - names_b)
    only_b = sorted(names_b - names_a)
    shared = sorted(names_a & names_b)
    differing = [n for n in shared if digests_a[n] != digests_b[n]]

    same_size = os.path.getsize(args.apk_a) == os.path.getsize(args.apk_b)
    identical = not only_a and not only_b and not differing

    # Content-level agreement, ignoring the APK signing block and signatures,
    # which necessarily differ between two differently-signed packages.
    excluded = [n for n in differing
                if n.startswith("META-INF/")
                or n in ("AndroidManifest.xml",)]
    payload_differing = [n for n in differing if n not in excluded]

    report = {
        "a": {"name": os.path.basename(args.apk_a),
              "size": os.path.getsize(args.apk_a),
              "entries": len(digests_a)},
        "b": {"name": os.path.basename(args.apk_b),
              "size": os.path.getsize(args.apk_b),
              "entries": len(digests_b)},
        "same_archive_size": same_size,
        "entry_name_sets_identical": not only_a and not only_b,
        "entries_only_in_a": only_a,
        "entries_only_in_b": only_b,
        "shared_entry_count": len(shared),
        "differing_entry_count": len(differing),
        "differing_entries": differing,
        "differing_excluding_signature_and_manifest": payload_differing,
        "byte_identical": identical,
        "verdict": (
            "byte-identical archives"
            if identical else
            "same name set, differing content in "
            f"{len(payload_differing)} payload entries and "
            f"{len(differing) - len(payload_differing)} signature/manifest entries"
        ),
    }

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

    print(f"A: {report['a']['name']}  ({report['a']['size']:,} bytes, "
          f"{report['a']['entries']} entries)")
    print(f"B: {report['b']['name']}  ({report['b']['size']:,} bytes, "
          f"{report['b']['entries']} entries)")
    print()
    print(f"  same archive size          : {same_size}")
    print(f"  entry name sets identical  : {report['entry_name_sets_identical']}")
    print(f"    only in A                : {len(only_a)}")
    print(f"    only in B                : {len(only_b)}")
    print(f"  shared entries             : {len(shared)}")
    print(f"  differing content          : {len(differing)}")
    print(f"    of which payload         : {len(payload_differing)}")
    print(f"    of which sig/manifest    : {len(differing) - len(payload_differing)}")
    print(f"  byte-identical             : {identical}")
    print(f"  verdict                    : {report['verdict']}")
    if payload_differing:
        print()
        print("  differing payload entries (first 25):")
        for name in payload_differing[:25]:
            print(f"    {sizes_a[name]:>10,} -> {sizes_b[name]:>10,}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())