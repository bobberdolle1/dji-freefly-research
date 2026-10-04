"""Pins the APK Signing Block layout that tools/signing.py implements.

The layout was established empirically from the sample and is easy to get subtly
wrong: the block's leading ``size`` field covers the *pairs only*, not the size
fields themselves, and each pair stores a **uint32** id (not uint64). Both
mistakes still "work" until a pair boundary is misread, so they are pinned here
against a synthetic archive that is byte-exact and independent of the sample.

The real sample is additionally checked when it is present (it is gitignored, so
this part skips in a clean checkout).
"""
from __future__ import annotations

import os
import struct
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import signing  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(REPO, "samples", "FF_v_1_00.apk")

# Expected values for the operator-supplied sample. Asserted only when present.
SAMPLE_SHA256 = "a6dc898ddcec0e9e13ab9c270835faea8a6d7961e7012e534361cdec0b9894ee"
SAMPLE_CERT_DER_SHA256 = "a3239282c4a6068656e4f1f2474cb1c4ae162bc2ec7e57e97f5a8340b845893c"
SAMPLE_CERT_SUBJECT = "CN=Android Debug, O=Android, C=US"


def build_apk_with_block(pairs: list[tuple[int, bytes]], payload: bytes = b"payload") -> bytes:
    """Build a minimal ZIP whose APK Signing Block holds the given ID/value pairs."""
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("classes.dex", payload)

    raw = bytearray(buf.getvalue())
    eocd = raw.rfind(b"PK\x05\x06")
    (cd_off,) = struct.unpack_from("<I", raw, eocd + 16)

    block = b""
    for block_id, value in pairs:
        block += struct.pack("<QI", 4 + len(value), block_id) + value

    # Layout is [ pairs ][ uint64 size ][ magic ], where size counts the pairs
    # plus the trailing size field and magic (24 bytes), but not a leading one.
    block_size = len(block) + 24
    signing_block = block + struct.pack("<Q", block_size) + signing.BLOCK_MAGIC
    shift = len(signing_block)
    out = bytearray(raw[:cd_off]) + bytearray(signing_block) + bytearray(raw[cd_off:])

    # Everything at or after the central directory moved by `shift`.
    struct.pack_into("<I", out, eocd + shift + 16, cd_off + shift)
    (entries,) = struct.unpack_from("<H", out, eocd + shift + 10)
    entry = cd_off + shift
    for _ in range(entries):
        (local_off,) = struct.unpack_from("<I", out, entry + 42)
        struct.pack_into("<I", out, entry + 42, local_off + shift)
        (name_len, extra_len, comment_len) = struct.unpack_from("<HHH", out, entry + 28)
        entry += 46 + name_len + extra_len + comment_len
    return bytes(out)


def test_pairs_roundtrip_with_uint32_ids():
    pairs = [(0x7109871A, b"\x01\x02\x03\x04"), (0x42726577, b"\x00" * 32)]
    data = build_apk_with_block(pairs)
    got = signing.iter_pairs(data)
    assert [p["id"] for p in got] == ["0x7109871A", "0x42726577"]
    assert [p["value"] for p in got] == [b"\x01\x02\x03\x04", b"\x00" * 32]
    assert [p["scheme"] for p in got] == ["APK Signature Scheme v2", "Verity padding block"]


def test_uint32_id_layout_differs_from_a_uint64_read():
    """A uint64 id read would consume 4 bytes of value and shift every pair.

    This is the specific mistake the uint32-id layout invites, so the walk is
    asserted to survive a value whose first 4 bytes are non-zero.
    """
    value = b"\xde\xad\xbe\xef" + b"payload-bytes"
    data = build_apk_with_block([(0x7109871A, value)])
    got = signing.iter_pairs(data)
    assert len(got) == 1
    assert got[0]["value"] == value


def test_size_spans_pairs_plus_footer():
    """size spans the pairs plus the trailing size field and magic (24 bytes),
    so the pairs start at cd_offset - size and end at cd_offset - 24."""
    data = build_apk_with_block([(0x7109871A, b"abcd")])
    cd_off = signing.central_directory_offset(data)
    (size,) = struct.unpack_from("<Q", data, cd_off - 24)
    pair_len = 8 + (4 + 4)          # uint64 length + uint32 id + value
    assert size == pair_len + 24
    assert signing.iter_pairs(data)[0]["offset"] == cd_off - size


def test_rejects_block_without_magic():
    data = bytearray(build_apk_with_block([(0x7109871A, b"abcd")]))
    cd_off = signing.central_directory_offset(bytes(data))
    data[cd_off - 16:cd_off] = b"NOT A MAGIC___"
    with pytest.raises(signing.SigningBlockError):
        signing.iter_pairs(bytes(data))


def test_rejects_inconsistent_duplicate_size():
    data = bytearray(build_apk_with_block([(0x7109871A, b"abcd")]))
    cd_off = signing.central_directory_offset(bytes(data))
    struct.pack_into("<Q", data, cd_off - 24, 999)
    with pytest.raises(signing.SigningBlockError):
        signing.iter_pairs(bytes(data))


def test_rejects_pair_overrunning_the_footer():
    """A length that runs past the footer must be refused, not truncated."""
    data = bytearray(build_apk_with_block([(0x7109871A, b"abcd")]))
    cd_off = signing.central_directory_offset(bytes(data))
    (size,) = struct.unpack_from("<Q", data, cd_off - 24)
    start = cd_off - size
    struct.pack_into("<Q", data, start, 4096)
    with pytest.raises(signing.SigningBlockError):
        signing.iter_pairs(bytes(data))


@pytest.mark.skipif(not os.path.exists(SAMPLE), reason="proprietary sample not present")
def test_real_sample_signing_block():
    import hashlib

    data = open(SAMPLE, "rb").read()
    assert hashlib.sha256(data).hexdigest() == SAMPLE_SHA256

    with zipfile.ZipFile(SAMPLE) as zf:
        v1 = [n for n in zf.namelist()
              if n.upper().startswith("META-INF/") and n.upper().endswith(signing.V1_EXTENSIONS)]
    assert v1 == [], "sample is expected to carry no JAR/v1 signature"

    pairs = signing.iter_pairs(data)
    schemes = [p["id"] for p in pairs]
    assert "0x7109871A" in schemes, "v2 signature block expected"
    assert "0xF05368C0" not in schemes, "no v3 block expected"

    v2 = next(p for p in pairs if p["id"] == "0x7109871A")
    certs = signing.find_x509_certs(v2["value"])
    assert len(certs) == 1, "exactly one signer certificate expected"
    import hashlib as _h
    assert _h.sha256(certs[0]).hexdigest() == SAMPLE_CERT_DER_SHA256

    fields = signing.openssl_cert_fields(certs[0])
    assert fields is not None
    assert fields["subject"] == SAMPLE_CERT_SUBJECT