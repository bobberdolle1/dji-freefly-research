#!/usr/bin/env python3
"""Stage 1 baseline triage for the Free Fly APK.

Read-only. Emits JSON + a human summary so every claim in docs/PROVENANCE.md is
backed by a reproducible artifact under work/baseline/.

Usage:
    python tools/baseline.py <apk> <outdir>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
import zipfile
from collections import Counter


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def entry_listing(zf: zipfile.ZipFile) -> list[dict]:
    out = []
    for zi in zf.infolist():
        out.append({
            "name": zi.filename,
            "size": zi.file_size,
            "compressed": zi.compress_size,
            "crc": "%08x" % zi.CRC,
            "method": zi.compress_type,
        })
    return out


def dex_summary(zf: zipfile.ZipFile) -> list[dict]:
    out = []
    for name in sorted(n for n in zf.namelist() if re.fullmatch(r"classes\d*\.dex", n)):
        data = zf.read(name)
        rec = {"name": name, "size": len(data)}
        if data[:4] == b"dex\n":
            # header: magic(8) checksum(4) sha1(20) file_size(4) header_size(4)
            # endian(4) link_size link_off map_off string_ids_size string_ids_off
            (file_size, header_size, endian) = struct.unpack_from("<III", data, 32)
            rec.update({
                "magic": data[:8].decode("ascii", "replace"),
                "file_size": file_size,
                "header_size": header_size,
                "endian": hex(endian),
                "string_ids_size": struct.unpack_from("<I", data, 56)[0],
                "type_ids_size": struct.unpack_from("<I", data, 64)[0],
                "method_ids_size": struct.unpack_from("<I", data, 88)[0],
                "class_defs_size": struct.unpack_from("<I", data, 96)[0],
            })
        out.append(rec)
    return out


URL_RE = re.compile(rb"(?:https?://|ftp://)[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{4,240}")
EMAIL_RE = re.compile(rb"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,64}\.[A-Za-z]{2,24}")


def scan_strings(zf: zipfile.ZipFile) -> dict:
    """Scan DEX + native libs + assets for URLs/emails and crypto/licence hints."""
    urls: Counter = Counter()
    emails: Counter = Counter()
    keywords: Counter = Counter()
    KEYWORDS = [
        b"license", b"licence", b"licence_key", b"activation", b"serial_key",
        b"auth", b"token", b"api_key", b"apiKey", b"register", b"registration",
        b"update", b"upgrade", b"premium", b"pro", b"unlock", b"purchase",
        b"billing", b"firebase", b"play.google", b"device_id", b"android_id",
        b"TrustManager", b"X509", b"okhttp", b"Retrofit", b"Volley",
        b"loadClass", b"DexClassLoader", b"InMemoryDex", b"nativeLoad",
        b"System.loadLibrary", b"ptrace", b"frida", b"xposed", b"substrate",
        b"debugger", b"isDebuggerConnected",
    ]
    scanned = []
    for zi in zf.infolist():
        n = zi.filename
        is_dex = bool(re.fullmatch(r"classes\d*\.dex", n))
        is_lib = n.startswith("lib/") and n.endswith(".so")
        is_txt = n.endswith((".json", ".xml", ".txt", ".properties", ".cfg", ".ini"))
        if not (is_dex or is_lib or is_txt):
            continue
        if zi.file_size > 80_000_000:
            continue
        data = zf.read(n)
        scanned.append({"name": n, "size": len(data), "dex": is_dex, "lib": is_lib})
        for m in URL_RE.finditer(data):
            urls[m.group().decode("utf-8", "replace")] += 1
        for m in EMAIL_RE.finditer(data):
            emails[m.group().decode("utf-8", "replace")] += 1
        low = data
        for kw in KEYWORDS:
            c = low.count(kw)
            if c:
                keywords[kw.decode()] += c
    return {
        "scanned_entries": scanned,
        "urls": urls.most_common(),
        "emails": emails.most_common(),
        "keyword_counts": keywords.most_common(),
    }


def main() -> int:
    apk, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)

    report = {
        "apk_path": apk,
        "sha256": sha256_file(apk),
        "size": os.path.getsize(apk),
    }
    with zipfile.ZipFile(apk) as zf:
        report["entries"] = entry_listing(zf)
        report["entry_count"] = len(report["entries"])
        report["dex"] = dex_summary(zf)
        report["dex_count"] = len(report["dex"])
        report["abis"] = sorted({e["name"].split("/")[1] for e in report["entries"]
                                 if e["name"].startswith("lib/") and e["name"].count("/") >= 2})
        report["native_libs"] = [e for e in report["entries"] if e["name"].startswith("lib/")]
        report["assets"] = [e for e in report["entries"] if e["name"].startswith("assets/")]
        report["res_top"] = [e for e in report["entries"]
                             if e["name"].startswith("res/") and e["name"].count("/") == 1]
        report["has_meta_inf_v1"] = any(
            e["name"] in ("META-INF/CERT.RSA", "META-INF/CERT.SF") for e in report["entries"])
        report["has_meta_inf_v2"] = "META-INF/MANIFEST.MF" in [e["name"] for e in report["entries"]]
        report["strings"] = scan_strings(zf)

    with open(os.path.join(outdir, "baseline.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"sha256          : {report['sha256']}")
    print(f"size            : {report['size']}")
    print(f"entries         : {report['entry_count']}")
    print(f"dex files       : {report['dex_count']} -> "
          + ", ".join(f"{d['name']}({d['size']}B, {d.get('class_defs_size','?')} classes)"
                      for d in report["dex"]))
    print(f"abis            : {report['abis']}")
    print(f"native libs     : {len(report['native_libs'])}")
    print(f"assets          : {len(report['assets'])}")
    for a in report["assets"][:40]:
        print(f"   {a['name']} ({a['size']}B)")
    print(f"v1 signature    : {report['has_meta_inf_v1']}")
    print(f"urls found      : {len(report['strings']['urls'])}")
    for u, c in report["strings"]["urls"][:40]:
        print(f"   {c:>4}x {u}")
    print(f"emails          : {report['strings']['emails'][:10]}")
    print("keywords        :")
    for k, c in report["strings"]["keyword_counts"]:
        print(f"   {c:>6}x {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())