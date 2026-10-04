#!/usr/bin/env python3
"""Summarise assets/params_catalog.json without copying the proprietary asset.

The catalogue itself is proprietary and stays out of git. What is committed is
the *documentation* of it; this tool regenerates the machine-readable summary
into a gitignored directory so `docs/PARAMETERS.md` has something to cite.

Usage:
    python tools/analyze_params_catalog.py <catalog.json> <outdir>
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter

# Type ids as declared by the app's ParamType enum; the catalogue's `t` field is
# the enum ordinal, which is also the on-the-wire type id.
TYPES = {0: "UINT8", 1: "UINT16", 2: "UINT32", 3: "UINT64", 4: "INT8",
         5: "INT16", 6: "INT32", 7: "INT64", 8: "FLOAT", 9: "DOUBLE"}

ALIAS_SEPARATOR = "|"
REGION_PARAMS = ("ce_country_type", "ce_regulatory_level")
ABSENCE_KEYWORDS = ("region", "fcc", "c0", "geo", "nfz", "no_fly",
                    "droneid", "drone_id", "4g", "cefc")


def main() -> int:
    path, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    raw = open(path, "rb").read()
    entries = json.loads(raw.decode("utf-8"))

    indices = [e["i"] for e in entries]
    names = [e["n"] for e in entries]
    aliased = [e for e in entries if ALIAS_SEPARATOR in e["n"]]
    region = [e for e in entries if e["n"] in REGION_PARAMS]
    absent = {kw: [n for n in names if kw in n.lower()] for kw in ABSENCE_KEYWORDS}

    lo, hi = min(indices), max(indices)
    gaps = [(a, b) for a, b in zip(sorted(indices), sorted(indices)[1:]) if b != a + 1]

    summary = {
        "source": os.path.basename(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "entry_count": len(entries),
        "key_set": sorted({k for e in entries for k in e}),
        "index_min": lo,
        "index_max": hi,
        "unique_indices": len(set(indices)),
        "duplicate_indices": len(indices) - len(set(indices)),
        "range_occupancy": round(len(set(indices)) / (hi - lo + 1), 4),
        "gap_count": len(gaps),
        "type_histogram": {TYPES.get(t, f"UNKNOWN_{t}"): c
                           for t, c in sorted(Counter(e["t"] for e in entries).items())},
        "alias_count": len(aliased),
        "alias_examples": [e["n"] for e in aliased[:10]],
        "region_parameters": region,
        "absent_keyword_search": absent,
        "top_level_families": Counter(n.split(".")[0] for n in names).most_common(30),
    }

    with open(os.path.join(outdir, "params_catalog_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print(f"entries            : {summary['entry_count']}")
    print(f"sha256             : {summary['sha256']}")
    print(f"index range        : {lo}..{hi}  unique={summary['unique_indices']} "
          f"gaps={summary['gap_count']} occupancy={summary['range_occupancy']:.1%}")
    print(f"types              : {summary['type_histogram']}")
    print(f"aliased entries    : {summary['alias_count']}")
    print("region parameters  :")
    for entry in region:
        print(f"    index={entry['i']} type={TYPES.get(entry['t'], entry['t'])} "
              f"{entry['n']}")
    print("absent keywords    : " + ", ".join(
        f"{kw}={len(v)}" for kw, v in absent.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())