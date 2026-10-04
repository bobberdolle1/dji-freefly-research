#!/usr/bin/env python3
"""Deterministic, dependency-free PE (Portable Executable) baseline analyser.

Usage:
    python tools/pe_baseline.py <exe> [--json <out.json>] [--no-strings]
                               [--max-strings N]

Prints a structured report to stdout; with ``--json`` the same data is also
written to disk as JSON.  Only the Python standard library is used, and the
sample is never executed - everything below is static inspection of bytes.

Endpoint classification is driven by an explicit keyword table over the
lowercased ``scheme://host/path`` string:

    update          firmware/software updater hosts and paths
                    ("update", "upgrade", "firmware", "/fw", "version",
                    "release", "changelog", "cdn.", "download")
    firmware-cdn    explicit firmware/image blobs ("firmware", ".bin", ".img",
                    "fw_download", "ota")
    telemetry       device/flight telemetry sinks ("telemetry", "collect",
                    "track", "stats", "report")
    analytics       page/traffic analytics ("analytics", "google-analytics",
                    "googletagmanager", "matomo", "piwik", "hotjar")
    crash-reporting exception/crash sinks ("crash", "sentry", "bugsnag",
                    "raygun", "appcenter", "firebase")
    login           account/authentication endpoints ("login", "signin",
                    "sign-in", "oauth", "auth", "account", "session",
                    "token", "sso", "passport")
    license         licence/activation/subscription endpoints ("licence",
                    "license", "activate", "activation", "serial",
                    "subscription", "entitlement", "unlock", "certificate")
    product-catalog product/model/firmware catalogues ("catalog", "catalogue",
                    "products", "models", "shop", "store", "market",
                    "compatibility", "price")
    websocket       ws:// and wss:// endpoints

A host or path matching none of the above is classified as ``other``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
from datetime import datetime, timezone

MACHINE = {
    0x0: "UNKNOWN", 0x14C: "I386", 0x166: "R4000", 0x1A2: "SH3", 0x1A6: "SH4",
    0x1C0: "ARM", 0x1C2: "THUMB", 0x1C4: "ARMNT", 0x1D3: "AM33", 0x200: "IA64",
    0x266: "MIPSFPU", 0x5032: "RISCV32", 0x5064: "RISCV64", 0x8664: "AMD64",
    0xAA64: "ARM64",
}

SUBSYSTEM = {
    0: "UNKNOWN", 1: "NATIVE", 2: "WINDOWS_GUI", 3: "WINDOWS_CUI", 5: "OS2_CUI",
    7: "POSIX_CUI", 8: "NATIVE_WINDOWS", 9: "WINDOWS_CE_GUI",
    10: "EFI_APPLICATION", 11: "EFI_BOOT_SERVICE_DRIVER",
    12: "EFI_RUNTIME_DRIVER", 13: "EFI_ROM", 14: "XBOX",
    16: "WINDOWS_BOOT_APPLICATION",
}

CHARACTERISTICS = {
    0x0001: "RELOCS_STRIPPED", 0x0002: "EXECUTABLE_IMAGE",
    0x0004: "LINE_NUMS_STRIPPED", 0x0008: "LOCAL_SYMS_STRIPPED",
    0x0010: "AGGRESSIVE_WS_TRIM", 0x0020: "LARGE_ADDRESS_AWARE",
    0x0080: "BYTES_REVERSED_LO", 0x0100: "32BIT_MACHINE", 0x0200: "DEBUG_STRIPPED",
    0x0400: "REMOVABLE_RUN_FROM_SWAP", 0x0800: "NET_RUN_FROM_SWAP",
    0x1000: "SYSTEM", 0x2000: "DLL", 0x4000: "UP_SYSTEM_ONLY",
    0x8000: "BYTES_REVERSED_HI",
}

DLL_CHARACTERISTICS = {
    0x0020: "HIGH_ENTROPY_VA", 0x0040: "DYNAMIC_BASE", 0x0080: "FORCE_INTEGRITY",
    0x0100: "NX_COMPAT", 0x0200: "NO_ISOLATION", 0x0400: "NO_SEH",
    0x0800: "NO_BIND", 0x1000: "APPCONTAINER", 0x2000: "WDM_DRIVER",
    0x4000: "GUARD_CF", 0x8000: "TERMINAL_SERVER_AWARE",
}

DATA_DIRECTORY = [
    "EXPORT", "IMPORT", "RESOURCE", "EXCEPTION", "SECURITY", "BASERELOC",
    "DEBUG", "ARCHITECTURE", "GLOBALPTR", "TLS", "LOAD_CONFIG", "BOUND_IMPORT",
    "IAT", "DELAY_IMPORT", "COM_DESCRIPTOR (CLR)", "RESERVED",
]

SECTION_CHARACTERISTICS = {
    0x00000020: "CNT_CODE", 0x00000040: "CNT_INITIALIZED_DATA",
    0x00000080: "CNT_UNINITIALIZED_DATA", 0x02000000: "MEM_DISCARDABLE",
    0x04000000: "MEM_NOT_CACHED", 0x08000000: "MEM_NOT_PAGED",
    0x10000000: "MEM_SHARED", 0x20000000: "MEM_EXECUTE", 0x40000000: "MEM_READ",
    0x80000000: "MEM_WRITE",
}

RESOURCE_TYPE = {
    1: "RT_CURSOR", 2: "RT_BITMAP", 3: "RT_ICON", 4: "RT_MENU", 5: "RT_DIALOG",
    6: "RT_STRING", 7: "RT_FONTDIR", 8: "RT_FONT", 9: "RT_ACCELERATOR",
    10: "RT_RCDATA", 11: "RT_MESSAGETABLE", 12: "RT_GROUP_CURSOR",
    14: "RT_GROUP_ICON", 16: "RT_VERSION", 24: "RT_MANIFEST",
}

DEBUG_TYPE = {
    0: "UNKNOWN", 1: "COFF", 2: "CODEVIEW", 3: "FPO", 4: "MISC",
    5: "EXCEPTION", 6: "FIXUP", 7: "OMAP_TO_SRC", 8: "OMAP_FROM_SRC",
    9: "BORLAND", 10: "RESERVED10", 11: "CLSID", 12: "VC_FEATURE", 13: "POGO",
    14: "ILTCG", 15: "MPX", 16: "REPRO", 19: "EMBEDDED_PORTABLE_PDB",
    20: "PDB_CHECKSUM",
}

WIN_CERT_REVISION = {0x0100: "WIN_CERT_REVISION_1_0", 0x0200: "WIN_CERT_REVISION_2_0"}
WIN_CERT_TYPE = {1: "WIN_CERT_TYPE_X509", 2: "WIN_CERT_TYPE_PKCS_SIGNED_DATA",
                 3: "WIN_CERT_TYPE_RESERVED_1", 4: "WIN_CERT_TYPE_TS_STACK_SIGNED"}

# Rich-header compid -> product label.  Only entries we can state with
# confidence are listed; everything else is reported raw as "unmapped".
RICH_PRODUCTS = {
    0x00: "imported object (any)", 0x01: "imported C runtime",
    0x02: "linker-generated import stub", 0x04: "C compiler",
    0x06: "resource compiler (cvtres)", 0x07: "C compiler",
    0x09: "C compiler", 0x0A: "assembler (MASM)", 0x0B: "C++ compiler",
    0x0D: "linker", 0x0E: "exported C runtime", 0x0F: "linker",
    0x19: "C++ compiler", 0x1C: "C++ compiler", 0x40: "assembler",
    0x5D: "linker", 0x5E: "C++ compiler", 0x60: "C compiler",
    0x6D: "linker", 0x78: "C++ compiler", 0x83: "C compiler",
    0x84: "linker", 0x93: "C compiler", 0x94: "C++ compiler",
    0x9D: "C++ compiler", 0xAA: "C++ compiler", 0xAB: "C++ compiler",
    0xC7: "MASM (ML)", 0xC9: "linker", 0xFF: "imported object (any)",
    0x103: "MSVC v140 toolset (VS2015+ era)", 0x104: "MSVC v140 toolset (VS2015+ era)",
    0x105: "MSVC v140 toolset (VS2015+ era)", 0xFD: "MSVC v140 toolset (VS2015+ era)",
}

EMBEDDED_MAGIC = {
    b"PK\x03\x04": "zip", b"PK\x05\x06": "zip-eocd", b"7z\xbc\xaf\x27\x1c": "7z",
    b"\x1f\x8b\x08": "gzip", b"Rar!\x1a\x07": "rar", b"MZ": "pe",
    b"MEI\x0c\x0b\x0a\x0b\x0e": "pyinstaller-cookie", b"!\x7fELF": "elf",
    b"MSCF": "cab", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": "ole-cfb",
    b"\xfd7zXZ\x00": "xz", b"\x04\x22\x4d\x18": "lz4",
}

NOTABLE_IMPORT_KEYWORDS = {
    "usb": ("setupdi", "winusb", "libusb", "hidd", "hidp", "setupapi", "cm_get",
            "cm_open", "cm_devnode", "devguid"),
    "crypto": ("crypt", "bcrypt", "ncrypt", "cert", "aes", "rsa", "sha", "md5"),
    "net": ("winhttp", "wininet", "internet", "wsa", "socket", "http", "url",
            "ssl", "tls", "gethost", "getaddr"),
    "anti-debug": ("isdebuggerpresent", "checkremotedebuggerpresent",
                   "ntqueryinformationprocess", "ntsetinformationthread",
                   "outputdebugstring", "unhandledexceptionfilter"),
    "version": ("getfileversioninfo", "verqueryvalue", "getversion"),
    "process": ("createfile", "deviceiocontrol", "writefile", "readfile",
                "virtualalloc", "virtualprotect", "loadlibrary", "getprocaddress",
                "createprocess", "shellexecute", "createthread"),
    "registry": ("regopen", "regquery", "regset", "regcreate", "regenum", "shget"),
    "file": ("findfirstfile", "findnextfile", "gettemppath", "createdirectory",
             "setcurrentdirectory", "getcurrentdirectory"),
}

URL_RE = re.compile(r"(?:https?|ftp|wss?)://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
TLD = ("com|net|org|io|de|co|uk|us|info|biz|dev|app|xyz|cn|ru|me|gg|tv|ly|air|"
       "online|site|tech|store|pro|edu|gov|mil|int|eu|nl|pl|se|fi|no|dk|es|it|"
       "pt|cz|sk|at|ch|be|fr|ca|au|jp|kr|in|br|za|mx|ar|cl")
HOST_RE = re.compile(r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?\.)+(?:%s)\b" % TLD)

CLASSIFY_RULES = {
    "crash-reporting": ("crash", "sentry", "bugsnag", "raygun", "appcenter",
                        "firebase", "crashlytics", "bugly"),
    "analytics": ("analytics", "google-analytics", "googletagmanager", "matomo",
                  "piwik", "hotjar", "clarity", "segment", "mixpanel"),
    "login": ("login", "signin", "sign-in", "oauth", "/auth", "account",
              "session", "/token", "sso", "passport"),
    "license": ("licence", "license", "licenc", "activate", "activation",
                "subscription", "entitlement", "unlock", "certificate", "cert"),
    "telemetry": ("telemetry", "collect", "tracking", "stats", "report"),
    "firmware-cdn": ("firmware", ".bin", ".img", "fw_download", "ota", "/fw/"),
    "product-catalog": ("catalog", "catalogue", "products", "models", "shop",
                        "store", "market", "compatibility", "price"),
    "update": ("update", "upgrade", "version", "release", "changelog", "cdn",
               "download", "platform-tools"),
}

ANTI_DEBUG_NAMES = [
    "IsDebuggerPresent", "CheckRemoteDebuggerPresent", "NtQueryInformationProcess",
    "NtSetInformationThread", "OutputDebugString", "NtQuerySystemInformation",
    "QueryPerformanceCounter", "GetTickCount",
]
ANTI_VM_STRINGS = ["VMware", "VirtualBox", "QEMU", "Xen", "Sandboxie", "VBox",
                   "vmtoolsd", "vboxservice"]
KEYWORD_HITS = [
    "duml", "DJI", "Firmware", "P3", "Mavic", "Phantom", "Inspire", "Ronin",
    "Osmo", "Aerial", "Agriculture", "WinUSB", "libusb", "SetupAPI", "hid",
    "serial", "USB", "license", "activate", "login", "password", "token",
    "api_key", "telemetry", "crash", "sentry", "bugsnag", "firebase", "google",
    "update", "version", "ssl", "certificate", "PyInstaller", "python311",
]


def entropy(buf: bytes) -> float:
    if not buf:
        return 0.0
    counts = [0] * 256
    for b in buf:
        counts[b] += 1
    n = len(buf)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def flags(value: int, table: dict) -> list:
    out = [name for bit, name in sorted(table.items()) if value & bit]
    return out or ["<none>"]


def extract_strings(data: bytes, minimum: int = 5):
    ascii_re = re.compile(rb"[\x20-\x7e]{%d,}" % minimum)
    wide_re = re.compile(rb"(?:[\x20-\x7e]\x00){%d,}" % minimum)
    out = []
    for m in ascii_re.finditer(data):
        out.append(("ascii", m.start(), m.group().decode("ascii", "replace")))
    for m in wide_re.finditer(data):
        out.append(("utf16le", m.start(), m.group().decode("utf-16le", "replace")))
    out.sort(key=lambda t: t[1])
    return out


def classify_endpoint(text: str) -> list:
    low = text.lower()
    tags = [tag for tag in CLASSIFY_RULES if any(k in low for k in CLASSIFY_RULES[tag])]
    if low.startswith("ws://") or low.startswith("wss://"):
        tags.append("websocket")
    return tags or ["other"]


class PE:
    def __init__(self, data: bytes):
        self.d = data
        self.errors = []
        if data[:2] != b"MZ":
            raise ValueError("not an MZ executable")
        self.e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[self.e_lfanew:self.e_lfanew + 4] != b"PE\0\0":
            raise ValueError("PE signature not found at e_lfanew")
        coff = self.e_lfanew + 4
        (self.machine, self.n_sections, self.timestamp, self.symtab,
         self.n_symbols, self.size_opt, self.characteristics) = struct.unpack_from(
            "<HHIIIHH", data, coff)
        self.coff_off = coff
        self.opt_off = coff + 20
        self.magic = struct.unpack_from("<H", data, self.opt_off)[0]
        self.pe32plus = self.magic == 0x20B
        if self.magic not in (0x10B, 0x20B):
            raise ValueError("unknown optional header magic 0x%X" % self.magic)
        self.sec_off = self.opt_off + self.size_opt
        self.linker = (data[self.opt_off + 2], data[self.opt_off + 3])
        self.size_of_code = struct.unpack_from("<I", data, self.opt_off + 4)[0]
        self.size_of_init = struct.unpack_from("<I", data, self.opt_off + 8)[0]
        self.size_of_uninit = struct.unpack_from("<I", data, self.opt_off + 12)[0]
        self.entry_point = struct.unpack_from("<I", data, self.opt_off + 16)[0]
        self.base_of_code = struct.unpack_from("<I", data, self.opt_off + 20)[0]
        if self.pe32plus:
            self.image_base = struct.unpack_from("<Q", data, self.opt_off + 24)[0]
            self.dd_off = self.opt_off + 112
        else:
            self.image_base = struct.unpack_from("<I", data, self.opt_off + 28)[0]
            self.dd_off = self.opt_off + 96
        o = self.opt_off
        self.section_align = struct.unpack_from("<I", data, o + 32)[0]
        self.file_align = struct.unpack_from("<I", data, o + 36)[0]
        self.size_of_image = struct.unpack_from("<I", data, o + 56)[0]
        self.size_of_headers = struct.unpack_from("<I", data, o + 60)[0]
        self.checksum = struct.unpack_from("<I", data, o + 64)[0]
        self.subsystem = struct.unpack_from("<H", data, o + 68)[0]
        self.dll_characteristics = struct.unpack_from("<H", data, o + 70)[0]
        q = "<Q" if self.pe32plus else "<I"
        self.size_of_stack_reserve = struct.unpack_from(q, data, o + 72)[0]
        self.size_of_stack_commit = struct.unpack_from(q, data, o + 80)[0]
        self.size_of_heap_reserve = struct.unpack_from(q, data, o + 88)[0]
        self.size_of_heap_commit = struct.unpack_from(q, data, o + 96)[0]
        self.num_dirs = struct.unpack_from("<I", data, o + 108 if self.pe32plus
                                           else o + 92)[0]
        self.dirs = [struct.unpack_from("<II", data, self.dd_off + 8 * i)
                     for i in range(min(self.num_dirs, 16))]
        self.sections = []
        for i in range(self.n_sections):
            so = self.sec_off + 40 * i
            name = data[so:so + 8].rstrip(b"\0").decode("latin-1")
            vs, va, rs, rp = struct.unpack_from("<IIII", data, so + 8)
            sc = struct.unpack_from("<I", data, so + 36)[0]
            self.sections.append(dict(name=name, virtual_size=vs, virtual_address=va,
                                      raw_size=rs, raw_pointer=rp, characteristics=sc))

    def rva_to_offset(self, rva):
        for s in self.sections:
            span = max(s["virtual_size"], s["raw_size"])
            if s["virtual_address"] <= rva < s["virtual_address"] + span:
                return s["raw_pointer"] + (rva - s["virtual_address"])
        return None

    def dir(self, index):
        return self.dirs[index] if index < len(self.dirs) else (0, 0)

    def parse_imports(self):
        rva = self.dir(1)[0]
        out = []
        if not rva:
            return out
        base = self.rva_to_offset(rva)
        if base is None:
            return out
        i = 0
        while base + i * 20 + 20 <= len(self.d):
            ilt, _ts, _fwd, name_rva, iat = struct.unpack_from(
                "<IIIII", self.d, base + i * 20)
            if name_rva == 0:
                break
            no = self.rva_to_offset(name_rva)
            dll = self.d[no:self.d.index(b"\0", no)].decode("latin-1") if no else "?"
            funcs = []
            to = self.rva_to_offset(ilt or iat)
            step = 8 if self.pe32plus else 4
            while to is not None and to + step <= len(self.d):
                if self.pe32plus:
                    v = struct.unpack_from("<Q", self.d, to)[0]
                    ob = 1 << 63
                else:
                    v = struct.unpack_from("<I", self.d, to)[0]
                    ob = 1 << 31
                if v == 0:
                    break
                if v & ob:
                    funcs.append("#%d" % (v & 0xFFFF))
                else:
                    ho = self.rva_to_offset(v & (ob - 1))
                    funcs.append(self.d[ho + 2:self.d.index(b"\0", ho + 2)]
                                 .decode("latin-1", "replace") if ho else "<unresolvable>")
                to += step
            out.append(dict(dll=dll, functions=funcs))
            i += 1
        return out

    def parse_exports(self):
        rva = self.dir(0)[0]
        if not rva:
            return None
        o = self.rva_to_offset(rva)
        if o is None:
            return None
        (_ch, _ts, _mj, _mn, name_rva, obase, nf, nn, _ar, npr, _or) = \
            struct.unpack_from("<IIHHIIIIIII", self.d, o)
        no = self.rva_to_offset(name_rva)
        names = []
        npo = self.rva_to_offset(npr)
        if npo:
            for i in range(nn):
                p = struct.unpack_from("<I", self.d, npo + 4 * i)[0]
                eo = self.rva_to_offset(p)
                if eo:
                    names.append(self.d[eo:self.d.index(b"\0", eo)].decode("latin-1"))
        return dict(module=self.d[no:self.d.index(b"\0", no)].decode("latin-1")
                    if no else "?", ordinal_base=obase,
                    number_of_functions=nf, names=names)

    def parse_delay_imports(self):
        rva = self.dir(13)[0]
        out = []
        if not rva:
            return out
        i = 0
        while True:
            base = self.rva_to_offset(rva + i * 32)
            if base is None or base + 32 > len(self.d):
                break
            attrs, name_rva = struct.unpack_from("<II", self.d, base)
            if name_rva == 0:
                break
            no = self.rva_to_offset(name_rva)
            out.append(dict(dll=self.d[no:self.d.index(b"\0", no)].decode("latin-1")
                            if no else "?", attributes=attrs))
            i += 1
        return out

    def parse_resources(self):
        rva = self.dir(2)[0]
        if not rva:
            return []
        base = self.rva_to_offset(rva)
        if base is None:
            return []

        def name_at(v):
            if not v >> 31:
                return str(v & 0x7FFFFFFF)
            p = base + v
            ln = struct.unpack_from("<H", self.d, p)[0]
            return self.d[p + 2:p + 2 + 2 * ln].decode("utf-16le", "replace")

        def walk(off, path):
            _ch, _ts, named, ids = struct.unpack_from("<IIHH", self.d, off)
            for i in range(named + ids):
                nm, dv = struct.unpack_from("<II", self.d, off + 16 + 8 * i)
                label = name_at(nm) if nm >> 31 else str(nm & 0x7FFFFFFF)
                if dv >> 31:
                    for x in walk(base + (dv & 0x7FFFFFFF), path + [label]):
                        yield x
                else:
                    de = base + (dv & 0x7FFFFFFF)
                    drva, dsz, cp, _res = struct.unpack_from("<IIII", self.d, de)
                    yield path + [label], drva, dsz, cp

        out = []
        try:
            for path, drva, dsz, cp in walk(base, []):
                fo = self.rva_to_offset(drva)
                t = path[0]
                out.append(dict(path=path,
                                type=RESOURCE_TYPE.get(int(t), t) if t.isdigit() else t,
                                id=int(t) if t.isdigit() else None,
                                size=dsz, codepage=cp, file_offset=fo,
                                blob=self.d[fo:fo + dsz] if fo is not None else b""))
        except (struct.error, IndexError, ValueError) as exc:
            self.errors.append("resource walk aborted: %s" % exc)
        return out

    @staticmethod
    def parse_version_info(blob):
        info = {}
        sig_pos = blob.find(b"\xbd\x04\xef\xfe")
        if sig_pos < 0:
            return info
        ffi = struct.unpack_from("<IIIIIIIIIIIIII", blob, sig_pos)
        info["fixed"] = dict(
            signature="0x%08X" % ffi[0],
            file_version="%d.%d.%d.%d" % (ffi[1] >> 16, ffi[1] & 0xFFFF,
                                          ffi[2] >> 16, ffi[2] & 0xFFFF),
            product_version="%d.%d.%d.%d" % (ffi[3] >> 16, ffi[3] & 0xFFFF,
                                             ffi[4] >> 16, ffi[4] & 0xFFFF),
            file_flags_mask="0x%08X" % ffi[5], file_flags="0x%08X" % ffi[6],
            file_os="0x%08X" % ffi[7], file_type="0x%08X" % ffi[8],
            file_subtype="0x%08X" % ffi[9])
        strings = {}
        for key in ("CompanyName", "FileDescription", "FileVersion", "InternalName",
                    "LegalCopyright", "OriginalFilename", "ProductName",
                    "ProductVersion", "Comments"):
            enc = key.encode("utf-16le")
            p = blob.find(enc)
            if p < 0:
                continue
            v = p + len(enc)
            end = blob.find(b"\x00\x00", v)
            if end > v:
                val = blob[v:end + 1].decode("utf-16le", "replace").strip("\x00")
                if val:
                    strings[key] = val
        info["strings"] = strings
        return info

    def parse_debug(self):
        rva, size = self.dir(6)
        out = []
        if not rva:
            return out
        base = self.rva_to_offset(rva)
        if base is None:
            return out
        for i in range(size // 28):
            o = base + i * 28
            chars, ts, maj, mn, typ, sod, addr, ptr = struct.unpack_from(
                "<IIIIIIII", self.d, o)
            e = dict(characteristics="0x%08X" % chars, timestamp=ts,
                     major_version=maj, minor_version=mn,
                     type=DEBUG_TYPE.get(typ, "UNKNOWN(%d)" % typ), type_id=typ,
                     size_of_data=sod, address_of_raw_data="0x%X" % addr,
                     pointer_to_raw_data="0x%X" % ptr)
            if typ == 2 and ptr and sod:
                blob = self.d[ptr:ptr + sod]
                if blob[:4] == b"RSDS":
                    guid = blob[4:20]
                    e["codeview"] = dict(
                        signature="RSDS",
                        guid="%08X-%04X-%04X-%s-%s" % (
                            struct.unpack_from("<I", guid, 0)[0],
                            struct.unpack_from("<H", guid, 4)[0],
                            struct.unpack_from("<H", guid, 6)[0],
                            guid[8:10].hex().upper(), guid[10:16].hex().upper()),
                        age=struct.unpack_from("<I", blob, 20)[0],
                        pdb_path=blob[24:].split(b"\0")[0].decode("latin-1", "replace"))
                elif blob[:4] == b"NB10":
                    e["codeview"] = dict(
                        signature="NB10", age=struct.unpack_from("<I", blob, 16)[0],
                        pdb_path=blob[20:].split(b"\0")[0].decode("latin-1", "replace"))
            out.append(e)
        return out

    def parse_tls(self):
        rva = self.dir(9)[0]
        if not rva:
            return None
        o = self.rva_to_offset(rva)
        if o is None:
            return None
        fmt = "<QQQQII" if self.pe32plus else "<IIIIII"
        start, end, idx, cb, zf, ch = struct.unpack_from(fmt, self.d, o)
        cbs = []
        if cb:
            co = self.rva_to_offset(cb - self.image_base)
            step = 8 if self.pe32plus else 4
            while co is not None and co + step <= len(self.d) and len(cbs) < 64:
                v = (struct.unpack_from("<Q", self.d, co)[0] if self.pe32plus
                     else struct.unpack_from("<I", self.d, co)[0])
                if v == 0:
                    break
                cbs.append(v)
                co += step
        return dict(start_address_of_raw_data="0x%X" % start,
                    end_address_of_raw_data="0x%X" % end,
                    address_of_index="0x%X" % idx, address_of_callbacks="0x%X" % cb,
                    size_of_zero_fill=zf, characteristics="0x%08X" % ch,
                    callbacks=["0x%X" % c for c in cbs], callback_count=len(cbs))

    def parse_rich(self):
        pos = self.d.find(b"Rich", 0x40, self.e_lfanew)
        if pos < 0:
            return None
        key = struct.unpack_from("<I", self.d, pos + 4)[0]
        region = self.d[0x80:pos]
        plain = [struct.unpack_from("<I", region, i)[0] ^ key
                 for i in range(0, len(region) - 3, 4)]
        strategy = "constant-xor"
        if not plain or plain[0] != 0x536E6144:
            strategy = "rolling-xor-backwards"
            k, dec = key, []
            for i in range(len(region) - 4, -1, -4):
                v = struct.unpack_from("<I", region, i)[0] ^ k
                dec.append(v)
                k = (((k + v) << 13) | ((k + v) >> 19)) & 0xFFFFFFFF
            dec.reverse()
            plain = dec
        verified = bool(plain) and plain[0] == 0x536E6144
        entries = []
        if verified:
            for i in range(4, len(plain) - 1, 2):
                compid, count = plain[i], plain[i + 1]
                prodid = (compid >> 16) & 0xFFFF
                entries.append(dict(compid="0x%08X" % compid, prodid=prodid,
                                    build=compid & 0xFFFF, count=count,
                                    product=RICH_PRODUCTS.get(prodid, "unmapped")))
        return dict(region="0x%X..0x%X" % (0x80, pos), region_hex=region.hex(),
                    marker_offset=pos, key="0x%08X" % key, strategy=strategy,
                    danS_verified=verified,
                    plaintext_dwords=["0x%08X" % x for x in plain], entries=entries)

    def scan_embedded(self, limit_per_kind=40):
        found = {}
        for magic, kind in EMBEDDED_MAGIC.items():
            hits, start, total = [], 0, 0
            while True:
                i = self.d.find(magic, start)
                if i < 0:
                    break
                total += 1
                if kind == "pe":
                    if i + 0x40 < len(self.d):
                        lf = struct.unpack_from("<I", self.d, i + 0x3C)[0]
                        if 0 < lf < 0x1000 and \
                                self.d[i + lf:i + lf + 4] == b"PE\0\0":
                            if len(hits) < limit_per_kind:
                                hits.append(i)
                elif len(hits) < limit_per_kind:
                    hits.append(i)
                start = i + 1
            found[kind] = dict(magic=magic.hex(), count=total,
                               offsets=[hex(x) for x in hits])
        return found

    def pyinstaller_cookies(self):
        out, start = [], 0
        while True:
            i = self.d.find(b"MEI\x0c\x0b\x0a\x0b\x0e", start)
            if i < 0:
                break
            try:
                _m, plen, toc, toclen, pyvers, pylib = struct.unpack_from(
                    "!8sIIII64s", self.d, i)
                out.append(dict(cookie_offset=hex(i), package_length=plen,
                                toc_offset=toc, toc_length=toclen,
                                archive_start=hex(i + 88 - plen),
                                python_version=pyvers,
                                python_library=pylib.split(b"\0")[0]
                                .decode("ascii", "replace")))
            except struct.error:
                pass
            start = i + 1
        return out


def identify_technology(pe, imports, strings):
    verdicts = []

    def add(name, evidence):
        verdicts.append(dict(technology=name, evidence=evidence))

    dll_lower = [d["dll"].lower() for d in imports]
    names_lower = [f.lower() for d in imports for f in d["functions"]]
    s_all = "\n".join(s for _, _, s in strings).lower()
    sec_names = [s["name"] for s in pe.sections]
    clr_rva = pe.dir(14)[0]

    if clr_rva or "mscoree.dll" in dll_lower or "_corexemain" in names_lower:
        add(".NET", ["CLR data directory RVA=0x%X" % clr_rva,
                     "mscoree.dll imported: %s" % ("mscoree.dll" in dll_lower),
                     "_CorExeMain imported: %s" % ("_corexemain" in names_lower)])

    native = pe.machine in (0x14C, 0x8664, 0x1C0, 0x1C4, 0xAA64, 0x200)
    if native and not clr_rva:
        ev = ["Machine=0x%04X (%s)" % (pe.machine, MACHINE.get(pe.machine, "?")),
              "CLR data directory (index 14) is empty",
              "sections: %s" % ", ".join(sec_names),
              "Characteristics=0x%04X %s" % (pe.characteristics,
                                             ",".join(flags(pe.characteristics,
                                                            CHARACTERISTICS)))]
        if ".pdata" in sec_names:
            ev.append(".pdata present -> native x64 exception directory")
        rich = pe.parse_rich()
        if rich and rich["entries"]:
            ev.append("Rich header toolset prodids: %s"
                      % sorted({e["product"] for e in rich["entries"]}))
        add("Native C/C++ (MSVC)", ev)

    qt = [d for d in dll_lower if re.match(r"qt[56]", d)]
    if qt or "qtcore" in s_all or "qapplication" in s_all or ".rcc" in sec_names:
        add("Qt", ["Qt DLLs imported: %s" % (qt or "none"),
                   "Qt runtime strings present", "sections: %s" % ", ".join(sec_names)])
    cef = [d for d in dll_lower if d in ("libcef.dll", "icudt.dll", "libffmpeg.dll",
                                        "chrome_elf.dll", "minicore.dll")]
    if cef or "resources.pak" in s_all or "icudtl.dat" in s_all:
        add("Electron/CEF", ["CEF DLLs imported: %s" % (cef or "none"),
                             "resources.pak / icudtl.dat strings present"])

    pyi = []
    if "pyinstaller" in s_all:
        pyi.append("string 'PyInstaller' present")
    if b"MEI\x0c\x0b\x0a\x0b\x0e" in pe.d:
        pyi.append("CArchive cookie magic MEI\\014\\013\\012\\013\\016 present")
    if "_meipass" in s_all:
        pyi.append("string '_MEIPASS' present")
    if "pyz-00.pyz" in s_all:
        pyi.append("string 'PYZ-00.pyz' present")
    py_dll = [d for d in dll_lower if re.match(r"python3\d+\.dll", d)]
    if py_dll:
        pyi.append("imports %s" % py_dll)
    for c in pe.pyinstaller_cookies():
        pyi.append("cookie at %s: pkg_len=%d toc=%d/%d pyver=%d lib=%s start=%s"
                   % (c["cookie_offset"], c["package_length"], c["toc_offset"],
                      c["toc_length"], c["python_version"], c["python_library"],
                      c["archive_start"]))
    if pyi:
        add("Python-frozen (PyInstaller)", pyi)

    if any(s in s_all for s in ("borland", "embarcadero")) or "tapplication" in s_all:
        add("Delphi", ["Borland/Embarcadero or TApplication strings present"])
    if "go build id" in s_all or ".gopclntab" in sec_names or "runtime.main" in s_all:
        add("Go", ["Go runtime markers present"])
    if any(s.startswith("UPX") or s in (".aspack", ".themida", ".vmp0", ".vmp1")
           for s in sec_names):
        add("Packed (UPX/VMProtect)", ["packer section names: %s" % sec_names])
    return verdicts


def analyse(path, want_strings, max_strings):
    data = open(path, "rb").read()
    pe = PE(data)
    rep = {"file": dict(path=path, size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                        md5=hashlib.md5(data).hexdigest(),
                        sha1=hashlib.sha1(data).hexdigest())}
    imports = pe.parse_imports()
    digest = ",".join("%s.%s" % (d["dll"].lower(), f.lower())
                      for d in imports for f in d["functions"])
    rep["file"]["import_digest_sha256"] = hashlib.sha256(digest.encode()).hexdigest()

    strings = extract_strings(data)[:max_strings] if want_strings else []
    rep["technology"] = identify_technology(pe, imports, strings)

    rep["headers"] = dict(
        e_magic=pe.d[:2].decode("latin-1"), e_lfanew=hex(pe.e_lfanew),
        pe_signature=pe.d[pe.e_lfanew:pe.e_lfanew + 4].hex(),
        machine="0x%04X (%s)" % (pe.machine, MACHINE.get(pe.machine, "unknown")),
        number_of_sections=pe.n_sections, timestamp=pe.timestamp,
        timestamp_utc=(datetime.fromtimestamp(pe.timestamp, timezone.utc).isoformat()
                       if 0 < pe.timestamp < 4e9 else "invalid"),
        timestamp_note="UNRELIABLE: reproducible-build and signing pipelines commonly "
                       "rewrite this field; it is not proof of a build date.",
        pointer_to_symbol_table=hex(pe.symtab), number_of_symbols=pe.n_symbols,
        size_of_optional_header=pe.size_opt,
        characteristics="0x%04X %s" % (pe.characteristics,
                                       ",".join(flags(pe.characteristics,
                                                      CHARACTERISTICS))),
        optional_magic="0x%04X (%s)" % (pe.magic, "PE32+" if pe.pe32plus else "PE32"),
        linker_version="%d.%d" % pe.linker, size_of_code=pe.size_of_code,
        size_of_initialized_data=pe.size_of_init,
        size_of_uninitialized_data=pe.size_of_uninit,
        entry_point_rva=hex(pe.entry_point),
        entry_point_va="0x%X" % (pe.image_base + pe.entry_point),
        base_of_code=hex(pe.base_of_code), image_base="0x%X" % pe.image_base,
        section_alignment=hex(pe.section_align), file_alignment=hex(pe.file_align),
        size_of_image=hex(pe.size_of_image), size_of_headers=hex(pe.size_of_headers),
        checksum="0x%08X" % pe.checksum,
        subsystem="%d (%s)" % (pe.subsystem, SUBSYSTEM.get(pe.subsystem, "unknown")),
        dll_characteristics="0x%04X %s" % (
            pe.dll_characteristics,
            ",".join(flags(pe.dll_characteristics, DLL_CHARACTERISTICS))),
        size_of_stack_reserve=pe.size_of_stack_reserve,
        size_of_stack_commit=pe.size_of_stack_commit,
        size_of_heap_reserve=pe.size_of_heap_reserve,
        size_of_heap_commit=pe.size_of_heap_commit,
        number_of_rva_and_sizes=pe.num_dirs,
        data_directories=[dict(index=i, name=DATA_DIRECTORY[i], rva="0x%X" % r, size=s)
                          for i, (r, s) in enumerate(pe.dirs) if r or s])

    rep["sections"] = []
    for s in pe.sections:
        blob = data[s["raw_pointer"]:s["raw_pointer"] + s["raw_size"]]
        ent = entropy(blob)
        rep["sections"].append(dict(
            name=s["name"], virtual_address="0x%X" % s["virtual_address"],
            virtual_size=s["virtual_size"], raw_size=s["raw_size"],
            raw_pointer="0x%X" % s["raw_pointer"],
            file_range="0x%X..0x%X" % (s["raw_pointer"],
                                       s["raw_pointer"] + s["raw_size"]),
            characteristics="0x%08X %s" % (
                s["characteristics"],
                ",".join(flags(s["characteristics"], SECTION_CHARACTERISTICS))),
            entropy=round(ent, 4), high_entropy=ent > 7.2))

    notable = [dict(category=cat, dll=d["dll"], function=f)
               for d in imports for f in d["functions"]
               for cat, keys in NOTABLE_IMPORT_KEYWORDS.items()
               if any(k in f.lower() for k in keys)]
    rep["imports"] = dict(
        dlls=[dict(dll=d["dll"], count=len(d["functions"]), functions=d["functions"])
              for d in imports], notable=notable)
    rep["exports"] = pe.parse_exports() or "none"
    rep["delay_imports"] = pe.parse_delay_imports() or "none"
    rep["rich_header"] = pe.parse_rich() or "absent"

    res_out, by_type = [], {}
    for r in pe.parse_resources():
        blob = r.pop("blob")
        e = dict(r)
        e["first_bytes_hex"] = blob[:32].hex()
        e["entropy"] = round(entropy(blob), 4)
        e["embedded_magic"] = next((k for m, k in EMBEDDED_MAGIC.items()
                                    if blob.startswith(m)), None)
        if r["type"] == "RT_VERSION":
            e["version_info"] = pe.parse_version_info(blob)
        elif r["type"] == "RT_MANIFEST":
            e["text"] = blob.decode("utf-8", "replace")
        elif r["type"] == "RT_STRING":
            out, i, base_id = [], 0, (int(r["path"][1]) - 1) * 16
            while i + 2 <= len(blob):
                ln = struct.unpack_from("<H", blob, i)[0]
                i += 2
                if ln:
                    out.append((base_id + (i - 2) // 2,
                                blob[i:i + 2 * ln].decode("utf-16le", "replace")))
                    i += 2 * ln
            e["strings"] = out
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
        res_out.append(e)
    rep["resources"] = dict(summary=by_type, entries=res_out)

    rep["debug_directory"] = pe.parse_debug() or "none"
    pdbs = [d["codeview"]["pdb_path"] for d in rep["debug_directory"]
            if isinstance(d, dict) and d.get("codeview")]
    rep["pdb_path"] = pdbs or "none (no IMAGE_DEBUG_TYPE_CODEVIEW entry)"
    rep["tls"] = pe.parse_tls() or "none (no TLS data directory)"

    sec_off, sec_size = pe.dir(4)
    sig = dict(certificate_table_offset=hex(sec_off), certificate_table_size=sec_size)
    if sec_off and sec_off + 8 <= len(data):
        clen, crev, ctype = struct.unpack_from("<IHH", data, sec_off)
        pkcs7 = data[sec_off + 8:sec_off + clen]
        sig.update(dw_length=clen,
                   wRevision="0x%04X (%s)" % (crev,
                                               WIN_CERT_REVISION.get(crev, "unknown")),
                   wCertificateType="%d (%s)" % (
                       ctype, WIN_CERT_TYPE.get(ctype, "unknown")),
                   asn1_starts_with_sequence=pkcs7[:1] == b"\x30",
                   pkcs7_size=len(pkcs7))
    rep["authenticode"] = sig

    end_secs = max((s["raw_pointer"] + s["raw_size"] for s in pe.sections), default=0)
    overlay = data[end_secs:]
    rep["overlay"] = dict(end_of_last_section=hex(end_secs), size=len(overlay),
                          entropy=round(entropy(overlay), 4),
                          first_bytes_hex=overlay[:64].hex(),
                          last_bytes_hex=overlay[-64:].hex() if overlay else "")
    rep["embedded_magics"] = pe.scan_embedded()
    rep["pyinstaller_cookies"] = pe.pyinstaller_cookies() or "none"

    text_sec = next((s for s in pe.sections if s["name"] == ".text"), None)
    int3 = rdtsc = 0
    if text_sec:
        tb = data[text_sec["raw_pointer"]:text_sec["raw_pointer"] + text_sec["raw_size"]]
        int3 = tb.count(b"\xCC")
        rdtsc = sum(1 for i in range(len(tb) - 1) if tb[i] == 0x0F and tb[i + 1] == 0x31)
    text_all = "\n".join(s for _, _, s in strings)
    anti = [dict(indicator=n, present=bool([1 for _, _, s in strings if s == n]),
                 offsets=[hex(i) for _, i, s in strings if s == n][:20])
            for n in ANTI_DEBUG_NAMES]
    anti += [dict(indicator="VM string '%s'" % v,
                  present=bool([1 for _, _, s in strings if v.lower() in s.lower()]),
                  offsets=[hex(i) for _, i, s in strings
                           if v.lower() in s.lower()][:10])
             for v in ANTI_VM_STRINGS]
    anti.append(dict(indicator="int3 (0xCC) bytes in .text", present=int3 > 0, value=int3))
    anti.append(dict(indicator="RDTSC (0F 31) opcodes in .text", present=rdtsc > 0,
                     value=rdtsc))
    rep["anti_analysis"] = dict(
        indicators=anti,
        note="the outer stub is a stock PyInstaller bootloader; these counts are "
             "background noise unless a specific indicator is present.")

    if want_strings:
        urls = sorted({m.group().rstrip(".,);'\"") for m in URL_RE.finditer(text_all)})
        hosts = sorted(set(HOST_RE.findall(text_all)))
        endpoints = [dict(url=u, category=classify_endpoint(u)) for u in urls]
        keywords = {}
        for word in KEYWORD_HITS:
            hits = [hex(i) for _, i, s in strings if word.lower() in s.lower()]
            if hits:
                keywords[word] = dict(count=len(hits), first_offsets=hits[:20])
        rep["strings"] = dict(
            total=len(strings),
            urls=endpoints,
            endpoint_classification={e["url"]: e["category"] for e in endpoints},
            hosts=hosts,
            emails=sorted(set(EMAIL_RE.findall(text_all))),
            ipv4=sorted(set(IPV4_RE.findall(text_all))),
            keyword_hits=keywords,
            sample=[dict(kind=k, offset=hex(i), text=s[:160])
                    for k, i, s in strings[:200]])
    rep["parse_errors"] = pe.errors
    return rep


def emit(rep):
    def hdr(t):
        print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)

    hdr("1. FILE")
    for k, v in rep["file"].items():
        print("  %-24s %s" % (k, v))

    hdr("2. TECHNOLOGY IDENTIFICATION")
    for v in rep["technology"]:
        print("  * %s" % v["technology"])
        for e in v["evidence"]:
            print("      - %s" % e)
    if not rep["technology"]:
        print("  (no verdict matched)")

    hdr("3. HEADERS")
    for k, v in rep["headers"].items():
        if k != "data_directories":
            print("  %-28s %s" % (k, v))
    print("  data directories:")
    for d in rep["headers"]["data_directories"]:
        print("      [%2d] %-22s rva=%12s size=%d"
              % (d["index"], d["name"], d["rva"], d["size"]))

    hdr("4. SECTIONS")
    for s in rep["sections"]:
        print("  %-9s vaddr=%10s vsize=%8d raw=%8d @%10s entropy=%.4f%s"
              % (s["name"], s["virtual_address"], s["virtual_size"], s["raw_size"],
                 s["raw_pointer"], s["entropy"], "  HIGH" if s["high_entropy"] else ""))
        print("            %s" % s["characteristics"])

    hdr("5. IMPORTS")
    for d in rep["imports"]["dlls"]:
        print("  %s  (%d functions)" % (d["dll"], d["count"]))
        print("      " + ", ".join(d["functions"]))
    print("  notable:")
    for n in rep["imports"]["notable"]:
        print("      [%-10s] %s!%s" % (n["category"], n["dll"], n["function"]))

    hdr("6. EXPORTS")
    print("  " + json.dumps(rep["exports"])[:2000])

    hdr("7. DELAY IMPORTS")
    print("  " + json.dumps(rep["delay_imports"])[:1000])

    hdr("8. RICH HEADER")
    r = rep["rich_header"]
    if r == "absent":
        print("  absent")
    else:
        print("  region %s  marker@%d  key=%s" % (r["region"], r["marker_offset"], r["key"]))
        print("  strategy=%s  DanS_verified=%s" % (r["strategy"], r["danS_verified"]))
        print("  region_hex=%s..." % r["region_hex"][:160])
        print("  %10s %7s %7s %7s  product" % ("compid", "prodid", "build", "count"))
        for e in r["entries"]:
            print("  %10s %7d %7d %7d  %s" % (e["compid"], e["prodid"], e["build"],
                                              e["count"], e["product"]))

    hdr("9. RESOURCES")
    print("  summary: " + json.dumps(rep["resources"]["summary"]))
    for e in rep["resources"]["entries"]:
        print("  %s %s size=%d codepage=%d entropy=%s magic=%s"
              % (e["type"], "/".join(e["path"]), e["size"], e["codepage"],
                 e["entropy"], e["embedded_magic"]))
        print("      first bytes: %s" % e["first_bytes_hex"])
        if "version_info" in e:
            print("      " + json.dumps(e["version_info"])[:1500])
        if "strings" in e:
            for sid, s in e["strings"][:60]:
                print("      [%s] %r" % (sid, s))
        if "text" in e:
            for line in e["text"].splitlines():
                print("      | " + line)

    hdr("10. DEBUG DIRECTORY")
    print("  " + json.dumps(rep["debug_directory"])[:1500])
    print("  PDB path: " + json.dumps(rep["pdb_path"]))

    hdr("11. TLS")
    print("  " + json.dumps(rep["tls"]))

    hdr("12. AUTHENTICODE")
    for k, v in rep["authenticode"].items():
        print("  %-32s %s" % (k, v))

    hdr("13. OVERLAY AND EMBEDDED ARCHIVES")
    for k, v in rep["overlay"].items():
        print("  %-26s %s" % (k, v))
    for kind, info in rep["embedded_magics"].items():
        print("  magic %-18s count=%-8d %s" % (kind, info["count"], info["offsets"][:8]))
    print("  PyInstaller cookies: " + json.dumps(rep["pyinstaller_cookies"])[:800])

    hdr("14. STRINGS AND ENDPOINTS")
    if "strings" not in rep:
        print("  (skipped with --no-strings)")
    else:
        s = rep["strings"]
        print("  total strings: %d" % s["total"])
        print("  URLs:")
        for u in s["urls"]:
            print("      %-78s %s" % (u["url"], u["category"]))
        print("  hosts: " + ", ".join(s["hosts"][:150]))
        print("  emails: " + ", ".join(s["emails"][:60]))
        print("  ipv4: " + ", ".join(s["ipv4"][:60]))
        print("  keyword hits:")
        for k, v in s["keyword_hits"].items():
            print("      %-14s count=%-6d first=%s" % (k, v["count"],
                                                       v["first_offsets"][:5]))

    hdr("15. ANTI-ANALYSIS")
    for i in rep["anti_analysis"]["indicators"]:
        print("  " + json.dumps(i))
    if rep["parse_errors"]:
        hdr("PARSE ERRORS")
        for e in rep["parse_errors"]:
            print("  " + e)


def main() -> int:
    ap = argparse.ArgumentParser(description="Static PE baseline report.")
    ap.add_argument("exe")
    ap.add_argument("--json", help="also write the machine-readable report here")
    ap.add_argument("--no-strings", action="store_true")
    ap.add_argument("--max-strings", type=int, default=20000)
    a = ap.parse_args()
    try:
        rep = analyse(a.exe, not a.no_strings, a.max_strings)
    except Exception as exc:                                     # noqa: BLE001
        print("error: %s" % exc, file=sys.stderr)
        return 1
    emit(rep)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=1, default=str)
        print("\nwrote " + a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())