# NLD FCC — native transport, wrapper framing, PKDS, WireGuard

Bounded deep pass over `nldfcc.apk`. Strings and structure only; no
disassembly and no execution.

---

## 1. The native implementation is `libnld-core.so`

**FACT.** Native libraries per ABI:

| Library | arm64-v8a | armeabi-v7a |
|---|---|---|
| `libnld-core.so` | 713,664 | 441,492 |
| `libwg-go.so` | 3,365,264 | 3,174,788 |
| `libwg-quick.so` | 29,952 | 22,736 |
| `libwg.so` | 81,704 | 47,076 |
| `libandroidx.graphics.path.so` | 10,096 | 7,252 |

`libnld-core.so` is the vendor's own component (the other four are
`libandroidx.graphics.path.so` from AndroidX and the WireGuard set).

**FACT.** It exports **no `Java_*` JNI symbols**, yet the DEX contains
`com.nolimitdronez.nldfcc.MainActivity$NativeRcLinkRxSink` and four `RCLink`
string occurrences, with the library logging *"RCLink Kotlin RX sink callback
failed"* and *"RCLink Kotlin RX sink method not found"*.

**INFERENCE.** The Kotlin/native boundary is resolved at runtime rather than by
JNI name binding — a native-to-Kotlin callback sink looked up by name, not a
static `Java_*` export. The class and the log strings together establish that
`libnld-core.so` is the protocol engine and `MainActivity` is its callback host.

## 2. The "outer wrapper" is DUSS, over an RCLink layer

The profile prose said *"Uses port 40007 with outer wrapper"*. The native
library names both halves.

**FACT.** `libnld-core.so` string evidence:

```
DUSS socket() failed errno=%d (%s)
bind(/duss/mb/0x1e00) failed errno=%d (%s)
connect(/duss/mb/0x205) failed errno=%d (%s)
bound /duss/mb/0x1e00 and connected /duss/mb/0x205 fd=%d
DUSS TX persistent fd=%d sends=%llu bytes=%llu len=%zu opens=%llu reopens=%llu
DUSS TX send failed fd=%d attempt=%d len=%zu wrote=%zd errno=%d (%s); reopening once
NLD-RCLINK-RX      NLD-RCLINK-TX
RX len=%zu src=%02X%02X dst=%02X%02X seq=%u cmd=%02X/%02X
RX invalid DUML datagram len=%zu
main RX connected port=%d fd=%d epoch=%d
aux  RX connected port=%d fd=%d hijack=%d epoch=%d
```

**FACT.** The DUSS layer **binds the Android abstract socket
`/duss/mb/0x1e00`** and **connects to `/duss/mb/0x205`**, holding a persistent
file descriptor and reopening it once on send failure.

**INFERENCE — the transport stack, bottom-up:**

```
DUML frame            ← validated in native: "RX invalid DUML datagram len=%zu"
  └─ RCLink           ← NLD's own implementation; Kotlin sink callbacks
      └─ DUSS         ← DJI's abstract-socket service, /duss/mb/0x205
          └─ controller-local DJI service
```

with a **TCP route** beneath that ("main RX connected port=%d") and a second
**aux route** carrying a `hijack` flag. "Port 40007/40009" from the profile
prose is the TCP route's runtime port, logged rather than hard-coded — the ports
appear **zero** times in the DEX, which is consistent with them being parameters
rather than constants.

**FACT.** Two route names are tracked independently with their own state:
`mainConnected`/`auxConnected`, `mainRunning`/`auxRunning`, `mainPort`, and
`owns` in the disconnect logs.

**INFERENCE.** NLD runs two concurrent connections and can take ownership of a
route it did not open (`hijack`, `owns`). What triggers a hijack, and which
route wins, is not determinable from strings.

## 3. Signing-block id `0x504B4453` — unclassified

**FACT.**

| Property | Value |
|---|---|
| Id | `0x504B4453`, ASCII `PKDS` |
| Length | 4,277 bytes |
| SHA-256 | `cec2fb68d1a47ac157fd80e7a5c809cdab656032d466e65a783eb0536efd6ea2` |
| Shannon entropy | **7.9536 bits/byte** (maximum 8.0) |
| Distinct byte values | 256 / 256 |
| Byte counts | min 5, max 28 (uniform expectation 16 ± 4) |
| zlib / gzip / raw deflate | all invalid |

**FACT.** It is **not** a recognised AOSP APK Signing Block id. The AOSP set is
`0x7109871a` (v2), `0xF05368C0` (v3), `0x1B93AD61` (v3.1), `0x42726577` (verity
BR padding), `0x6DFF800D` (verity-v3 padding / source stamp). `0x504B4453` is
outside that set.

**FACT.** No container magic is present — not ZIP, not ELF, and the one `{` byte
at offset 23 is coincidental given a uniform byte distribution.

**Classification, deliberately minimal: UNCLASSIFIED.** The block is a
4,277-byte, near-maximal-entropy opaque blob under a non-AOSP identifier.

**INFERENCE (weak, and flagged as such).** Entropy this high with a uniform
distribution and no decompressor that accepts it is consistent with a
cryptographic artefact — a signature, a MAC, or an encrypted blob. It is *not*
consistent with ordinary compression of structured data.

**Explicitly not claimed.** "PKDS" is suggestive of `PK` (as in APK) plus `DS`,
but nothing in the artefact establishes what those letters stand for, who wrote
the block, or what verifies it. Naming a meaning here would be invention. The
only further step that would settle it is locating the producer — which means the
APK's own build chain or a writer with the corresponding key, neither of which
is available offline.

## 4. WireGuard is runtime-reachable, not dead baggage

**I was wrong earlier.** In `research/reports/nldfcc_baseline.md` I reported that
WireGuard appeared in the binary but did not assess reachability. When I then
checked, I grepped for `com.wireguard` — a **dotted** string — and got zero hits.

**FACT.** The DEX contains the descriptor:

```
Lcom/wireguard/android/backend/GoBackend;
```

**FACT.** `libwg-go.so` is 3.3 MB — by far the largest library in the APK, and a
Go-based WireGuard implementation is consistent with that size.

**INFERENCE.** `GoBackend` is WireGuard for Android's JNI backend. Its presence
in the DEX, together with the complete `libwg`/`libwg-go`/`libwg-quick` set,
means the VPN is **compiled into the app and reachable at runtime**. It is not
baggage left by a transitive dependency — the backend class is what loads
`libwg-go.so`.

**Correction to method.** The miss was a search bug, not a finding: DEX type
descriptors use `/`, not `.`. Any DEX string search in this project should be
run against both separators.

**INFERENCE.** Combined with the `INTERNET` permission and a bundled VPN, NLD
FCC plausibly tunnels its backend traffic. What it tunnels **to** is not
determinable offline: no host, endpoint or configuration string was found in
either the DEX or `libnld-core.so`. The absence of a WireGuard configuration in
the APK's assets suggests one is provisioned at runtime or fetched, which is
itself a finding worth recording as an open question.

## 5. Class layout — the app *is* obfuscated

**FACT.** 104 descriptors under `com.nolimitdronez`, including named classes
`MainActivity`, `MainActivity$NativeRcLinkRxSink`, `DumlForegroundService`,
`ParameterMacroOverlayService`, `ParameterMacroOverlaySnapshot`,
`RuntimeMaintenanceService`, alongside short names `a`, `a0`, `b`, `b0`, `c`,
`c0`, `d`, `d0`, …

**INFERENCE.** ProGuard/R8 renaming is applied to most of the app while a handful
of entry-point classes keep their names. This is the opposite of Free Fly, whose
`com.dronehacks` classes are entirely unobfuscated — one more reason the two
should not be assumed to share an implementation.

`ParameterMacroOverlayService` + `SYSTEM_ALERT_WINDOW` is a coherent pair: the
app draws an overlay, consistent with a live parameter readout while flying.

## 6. Summary

| Question | Answer | Confidence |
|---|---|---|
| Native implementation | `libnld-core.so`, runtime-bound to a Kotlin `NativeRcLinkRxSink` | FACT |
| Outer wrapper | **DUSS** — binds `/duss/mb/0x1e00`, connects `/duss/mb/0x205`; RCLink above it; DUML above that | FACT (strings) |
| TCP ports | logged at runtime (`main RX connected port=%d`), absent from DEX; aux route carries `hijack` | FACT |
| `0x504B4453` (PKDS) | 4,277 bytes, entropy 7.9536/8.0, not an AOSP id, not any container → **unclassified**, consistent with a cryptographic artefact | FACT + weak INFERENCE |
| WireGuard | **runtime-reachable** — `com.wireguard.android.backend.GoBackend` present | FACT (corrected) |
| Obfuscation | present (ProGuard/R8), unlike Free Fly | FACT |

## 7. Not established

- The DUSS message framing: no length prefix or envelope header is visible in
  the strings, only that RX validates DUML datagram lengths. Recovering the
  framing needs the disassembly.
- What triggers an `aux` route hijack and which route is preferred.
- Any WireGuard peer, endpoint or configuration.
- Whether `libnld-core.so` verifies the PKDS block, or whether some other
  component does.