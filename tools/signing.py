#!/usr/bin/env python3
"""APK Signing Block (v2/v3) parser + signing-certificate identification.

The Free Fly APK ships no META-INF/*.RSA|*.SF entries, i.e. no JAR/v1 signature.
The only signature evidence is the APK Signing Block that sits between the last
local file entry and the ZIP central directory.

Verified layout (pinned by tests/test_signing.py against a synthetic archive and
against this APK):

    [ pairs ][ uint64 size ][ 16-byte magic "APK Sig Block 42" ][ central dir ]
              ^-- size = len(pairs) + 24, so the pairs start at central_dir - size
                   and end at central_dir - 24, immediately before the footer.

Each pair is:

    uint64 length          length of (id + value), i.e. 4 + len(value)
    uint32 id
    byte   value[length-4]

Certificate fields are read with openssl rather than a hand-rolled DER walk:
X.509 parsing is not the research subject here, and an off-by-one in a bespoke
parser silently produces wrong provenance evidence.

Usage: python tools/signing.py <apk> <outdir>
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import zipfile

BLOCK_MAGIC = b"APK Sig Block 42"
SCHEME_NAMES = {
    0x7109871A: "APK Signature Scheme v2",
    0xF05368C0: "APK Signature Scheme v3",
    0x1B93AD61: "APK Signature Scheme v3.1",
    0x42726577: "Verity padding block",
    0x6DFF800D: "Verity padding block / Source stamp v2",
    0x2146444E: "APK Signature Scheme v4 (idsig only)",
}
V1_EXTENSIONS = (".RSA", ".DSA", ".EC", ".SF")
OPENSSL_FIELDS = ["subject", "issuer", "serial", "dates", "fingerprint", "pubkey"]


class SigningBlockError(ValueError):
    pass


def central_directory_offset(data: bytes) -> int:
    eocd = data.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise SigningBlockError("no EOCD record: not a ZIP archive")
    (cd_off,) = struct.unpack_from("<I", data, eocd + 16)
    if data[cd_off:cd_off + 4] != b"PK\x01\x02":
        raise SigningBlockError(f"central directory offset mismatch at {cd_off}")
    return cd_off


def iter_pairs(data: bytes) -> list[dict]:
    """Walk the APK Signing Block pairs, verifying the closing size + magic."""
    cd_off = central_directory_offset(data)
    if data[cd_off - 16:cd_off] != BLOCK_MAGIC:
        raise SigningBlockError("no APK Signing Block before central directory")
    (size,) = struct.unpack_from("<Q", data, cd_off - 24)
    pos = cd_off - size
    if pos < 0:
        raise SigningBlockError("signing block size underflows the file")
    pairs: list[dict] = []
    while pos < cd_off - 24:
        (length,) = struct.unpack_from("<Q", data, pos)
        if length < 4 or pos + 8 + length > cd_off - 24:
            raise SigningBlockError(f"pair at {pos} has invalid length {length}")
        (block_id,) = struct.unpack_from("<I", data, pos + 8)
        pairs.append({
            "offset": pos,
            "id": "0x%08X" % block_id,
            "scheme": SCHEME_NAMES.get(block_id, "unknown"),
            "length": length,
            "value": data[pos + 12:pos + 8 + length],
        })
        pos += 8 + length
    if pos != cd_off - 24:
        raise SigningBlockError("pairs do not end exactly at the block footer")
    (size_copy,) = struct.unpack_from("<Q", data, pos)
    if size_copy != size:
        raise SigningBlockError("signing block size fields disagree")
    return pairs


def find_x509_certs(blob: bytes) -> list[bytes]:
    """Extract DER X.509 certificates from a signature block value.

    A candidate is any 0x30 0x82 long-form SEQUENCE whose declared length fits
    the blob. Every candidate is subsequently validated by openssl, so a nested
    SEQUENCE cannot be mistaken for a certificate.
    """
    certs: list[bytes] = []
    pos = 0
    while True:
        idx = blob.find(b"\x30\x82", pos)
        if idx < 0:
            return certs
        (total,) = struct.unpack_from(">H", blob, idx + 2)
        end = idx + 4 + total
        if end > len(blob):
            pos = idx + 1
            continue
        candidate = blob[idx:end]
        if openssl_cert_fields(candidate) is not None:
            certs.append(candidate)
            pos = end
        else:
            pos = idx + 1


def openssl_cert_fields(der: bytes) -> dict | None:
    """Read certificate metadata with openssl. Returns None if it is not a cert."""
    if not shutil.which("openssl"):
        return None
    try:
        proc = subprocess.run(
            ["openssl", "x509", "-inform", "DER", "-noout"]
            + [f"-{f}" for f in OPENSSL_FIELDS if f != "pubkey"],
            input=der, capture_output=True, check=True)
        spki = subprocess.run(
            ["openssl", "x509", "-inform", "DER", "-noout", "-pubkey"],
            input=der, capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    out: dict = {}
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition("=")
        out[key.strip().lower()] = value.strip()
    out["public_key_sha256"] = hashlib.sha256(spki).hexdigest()
    return out


def describe_cert(der: bytes) -> dict:
    b64 = base64.b64encode(der).decode()
    cert = {
        "der_len": len(der),
        "der_sha256": hashlib.sha256(der).hexdigest(),
        "der_sha1": hashlib.sha1(der).hexdigest(),
        "der_md5": hashlib.md5(der).hexdigest(),
        "der_b64": b64,
        "pem": "-----BEGIN CERTIFICATE-----\n"
               + "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
               + "\n-----END CERTIFICATE-----",
    }
    fields = openssl_cert_fields(der)
    if fields is None:
        cert["parse_error"] = "openssl could not parse this structure as X.509"
    else:
        cert.update(fields)
    return cert


def main() -> int:
    apk, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    data = open(apk, "rb").read()
    report: dict = {"apk": apk, "apk_sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                    "openssl": shutil.which("openssl")}

    with zipfile.ZipFile(apk) as zf:
        report["v1_signature_entries"] = [
            n for n in zf.namelist()
            if n.upper().startswith("META-INF/") and n.upper().endswith(V1_EXTENSIONS)]

    try:
        pairs = iter_pairs(data)
    except SigningBlockError as exc:
        report["signing_block_error"] = str(exc)
        with open(os.path.join(outdir, "signing.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"v1 entries      : {report['v1_signature_entries'] or 'none'}")
        print(f"signing block   : NONE ({exc})")
        return 0

    report["schemes"] = []
    written = 0
    for pair in pairs:
        rec = {"id": pair["id"], "scheme": pair["scheme"],
               "length": pair["length"], "offset": pair["offset"]}
        if pair["id"] in ("0x7109871A", "0xF05368C0"):
            rec["certificates"] = [describe_cert(c)
                                   for c in find_x509_certs(pair["value"])]
            for i, cert in enumerate(rec["certificates"]):
                with open(os.path.join(outdir, f"cert{i}.der"), "wb") as fh:
                    fh.write(base64.b64decode(cert["der_b64"]))
                written += 1
        elif pair["scheme"].startswith("Verity"):
            rec["value_prefix_hex"] = pair["value"][:16].hex()
            rec["value_len"] = len(pair["value"])
        report["schemes"].append(rec)

    with open(os.path.join(outdir, "signing.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"v1 entries      : {report['v1_signature_entries'] or 'none'}")
    for scheme in report["schemes"]:
        print(f"block           : {scheme['scheme']} ({scheme['id']}) len={scheme['length']}")
        for cert in scheme.get("certificates", []):
            print(f"  cert sha256   : {cert['der_sha256']}")
            print(f"  cert sha1     : {cert['der_sha1']}")
            print(f"  subject       : {cert.get('subject')}")
            print(f"  issuer        : {cert.get('issuer')}")
            print(f"  serial        : {cert.get('serial')}")
            print(f"  validity      : {cert.get('notbefore')} .. {cert.get('notafter')}")
            print(f"  pubkey sha256 : {cert.get('public_key_sha256')}")
            if "parse_error" in cert:
                print(f"  parse_error   : {cert['parse_error']}")
    print(f"certs written   : {written} -> {outdir}/cert*.der")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())