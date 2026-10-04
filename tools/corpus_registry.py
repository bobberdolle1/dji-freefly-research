#!/usr/bin/env python3
"""Corpus sample registry: identity + provenance metadata for every sample.

Every proprietary binary handled by this project gets one record so that claims
in docs/ are traceable back to a specific artifact. Metadata is split into:

  observed_*   values read directly out of the file (FACT)
  claimed_*    values taken from filenames, manifests or vendor pages
               (a vendor claim, not necessarily true)

Registry file: research/corpus/registry.json  (gitignored - it records local
paths and hashes of proprietary binaries; the committed, publishable summary
lives in research/reports/ and docs/).

Usage:
    python tools/corpus_registry.py list
    python tools/corpus_registry.py add <path> --name <id> --source <url> [--note ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "research", "corpus", "registry.json")


def digests(path: str) -> dict:
    h = {k: hashlib.new(k) for k in ("sha256", "sha1", "md5")}
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            size += len(chunk)
            for hasher in h.values():
                hasher.update(chunk)
    out = {f"observed_{k}": v.hexdigest() for k, v in h.items()}
    out["observed_size"] = size
    return out


def apk_metadata(path: str) -> dict:
    """Read what can be read without a full decompile."""
    meta: dict = {}
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        meta["observed_entry_count"] = len(names)
        meta["observed_dex"] = sorted(n for n in names
                                      if n.startswith("classes") and n.endswith(".dex"))
        meta["observed_native_libs"] = sorted(n for n in names if n.endswith(".so"))
        meta["observed_abis"] = sorted({n.split("/")[1] for n in names
                                        if n.startswith("lib/") and n.count("/") >= 2})
        meta["observed_assets"] = sorted(n for n in names if n.startswith("assets/"))
        for prop in ("META-INF/com/android/build/gradle/app-metadata.properties",):
            if prop in names:
                meta["observed_gradle_metadata"] = zf.read(prop).decode(
                    "utf-8", "replace").strip()
    return meta


def load() -> dict:
    if os.path.exists(REGISTRY):
        with open(REGISTRY, encoding="utf-8") as fh:
            return json.load(fh)
    return {"samples": []}


def save(registry: dict) -> None:
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    with open(REGISTRY, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=2)


def cmd_add(args: argparse.Namespace) -> int:
    registry = load()
    if not os.path.exists(args.path):
        print(f"error: {args.path} not found", file=sys.stderr)
        return 1
    record = {
        "id": args.name,
        "original_filename": os.path.basename(args.path),
        "local_path": os.path.abspath(args.path),
        "acquisition_source": args.source,
        "acquisition_date": args.date,
        "claimed_product_name": args.product,
        "claimed_version": args.version,
        "metadata_confidence": args.confidence,
        "notes": args.note or "",
        "committed": False,
        **digests(args.path),
    }
    if zipfile.is_zipfile(args.path) and args.path.lower().endswith((".apk", ".xapk", ".apks")):
        record.update(apk_metadata(args.path))
    registry["samples"] = [s for s in registry["samples"] if s["id"] != args.name]
    registry["samples"].append(record)
    save(registry)
    print(f"registered {args.name}")
    for k in ("observed_sha256", "observed_size", "observed_dex"):
        if k in record:
            print(f"  {k}: {record[k]}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    registry = load()
    if not registry["samples"]:
        print("no samples registered")
        return 0
    for s in registry["samples"]:
        print(f"{s['id']}")
        print(f"  file    : {s['original_filename']} ({s['observed_size']} bytes)")
        print(f"  sha256  : {s['observed_sha256']}")
        print(f"  product : {s.get('claimed_product_name')} v{s.get('claimed_version')}")
        print(f"  source  : {s.get('acquisition_source')} ({s.get('acquisition_date')})")
        print(f"  dex     : {len(s.get('observed_dex', []))} "
              f"abis={s.get('observed_abis', [])}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list")
    p_list.set_defaults(func=cmd_list)
    p_add = sub.add_parser("add")
    p_add.add_argument("path")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--source", default="operator-supplied")
    p_add.add_argument("--date", default="")
    p_add.add_argument("--product", default="")
    p_add.add_argument("--version", default="")
    p_add.add_argument("--confidence", default="unknown",
                       choices=["unknown", "low", "medium", "high"])
    p_add.add_argument("--note", default="")
    p_add.set_defaults(func=cmd_add)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())