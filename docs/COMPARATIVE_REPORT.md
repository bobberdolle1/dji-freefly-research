# Comparative report

The 15 questions, answered from the evidence assembled across this project.
Every claim is tagged **FACT**, **INFERENCE** or **HYPOTHESIS** as in
`PROVENANCE.md`.

Supporting documents: `PROVENANCE.md`, `ARCHITECTURE.md`, `DUML.md`,
`COMMAND_MAP.md`, `PARAMETERS.md`, `WRITE_PATH.md`, `WIRE_COMPARISON.md`,
`APP_LINEAGE.md`, `COMMAND_CORPUS.md`, `TRANSPORT_MATRIX.md`,
`ECOSYSTEM_MAP.md`, `BACKENDS.md`, `PUBLIC_REPO_INVENTORY.md`, `FINAL_REPORT.md`,
and the per-sample reports in `research/reports/`.

**Samples**

| Sample | SHA-256 (first 16) | Note |
|---|---|---|
| `FF_v_1_00.apk` | `a6dc898ddcec0e9e` | Free Fly 1.0, operator-supplied |
| `nldfcc.apk` | `4a6e07a2ee1fbd7f` | NLD FCC 2.0.0.6, operator-supplied |
| `dh_v1.48_signed.exe` | `236dd98439e503c6` | Drone-Hacks 1.48, operator-supplied |
| `DJIFCC.APP-Android-1.21.12.19.apk` | `d65c3608cd09ca77` | vendor |
| `DJIFCC.APP-RC2-V6-1.21.10.43.apk` | `e322fceead4b2543` | vendor |
| `fcc_dji_go_android_v4.3.62.apk` | `1d9fe6377f6f7224` | vendor |
| `DJIFly-1.21.12.1030.apk` | `1da8d5b2ee5cdcb6` | **stock DJI Fly**, DJI CDN |
| `fly_1.21.8.apk` | `cfbf67368fa812c6` | stock DJI Fly |

---

## 1. What exactly is Free Fly?

**A standalone, offline, read-mostly flight-controller parameter editor.**
Android/Compose app; opens a raw USB bulk endpoint to a DJI device; speaks
DUML; addresses the FC's 2017 parameter table by `(table, index)`; ships one
855-entry parameter catalogue as an asset.

**FACT.** No `INTERNET` permission, no HTTP client library in any of ten DEX
files, no vendor endpoint. Debug-signed, `debuggable=true`, unobfuscated, no
native app code.

**FACT.** 10 of 14 command builders are FC Assistant parameter operations. All
2015 builders are unreachable dead code; the live protocol is 2017 only.

## 2. How much functionality overlaps Drone-Hacks?

**Substantially — and byte-for-byte on the wire.**

**FACT.** 10 of 10 command ids identical (`0xDF`, `0xF0`, `0xF8`, `0xF9`, `0xE0`,
`0xE1`, `0xE2`, `0xE3`, `0x82`, `0x81`) and 6 of 6 payload layouts identical.

**FACT.** Identical CRC seeds (`0x77`, `0x3692`), identical length mask
(`0x3FF`), identical parameter-hash modulus (`0xFFFFFFFB`).

**FACT.** Real behavioural differences: Drone-Hacks has a **live** 2015 path, a
full `Encrypt*` payload family, hardware-register writes, gimbal calibration, a
12-entry type table against Free Fly's 10, and a `gbk` name encoding against
US-ASCII. Free Fly has none of those and is 2017-only with no resync.

## 3. Is there evidence of shared code?

**No. `DIRECT_CODE_COPY_EVIDENCE = NONE`.**

Every candidate marker fails against the public-corpus control:
`djiparam/Duml.java` independently contains crc8 init `0x77`, crc16 init `0x3692`,
the literal `unknown1`, and the `0xE0`/`0xE1` ids. No HIGH criterion is met —
no identical uncommon code, no identical constant *table* (both regenerate from
polynomials), no identical bug, no shared typo, no shared binary resource.

`DIRECT_CODE_LINEAGE_CONFIDENCE = LOW` — two tools from one problem domain
remain more likely to be mutually inspired than chance, but that is an argument
from the problem space, not from code.

## 4. Where does its parameter catalogue come from?

**Not from any source in this corpus, as far as can be determined.**

**FACT.** Drone-Hacks contains **zero** occurrences of `gps_lon`,
`ce_country_type` or `g_config` across 11,735 bytecode tokens. It ships no
catalogue and rediscovers the table from the aircraft each session.

**FACT.** Free Fly's `assets/params_catalog.json` is unique to Free Fly among
every artefact examined.

**INFERENCE.** The catalogue was compiled by Free Fly's author from DJI
firmware or from public research. Which, is not established. `ce_country_type`
and `ce_regulatory_level` are present at indices 687 and 858, so region
parameters are enumerable — but *enumerable is not writable*, and see §5.

**HYPOTHESIS.** A compiled-from-firmware catalogue would explain the flat index
space and the 58% occupancy. Untested.

## 5. Which DJI protocols are common to all tools?

**Only DUML and the FC Assistant parameter commands.**

**FACT.** RCLink appears **only** in NLD FCC (`libnld-core.so` + `NativeRcLinkRxSink`)
and DJI-FCC-Unlock-iOS (MFi). Zero occurrences in Free Fly and Drone-Hacks.

**FACT.** Service mode, radio, WiFi and OFDM commands appear **only** in the
NLD/FreeFCC FCC sequence.

**FACT.** USB, TCP-on-controller and ExternalAccessory are mutually exclusive
transports — see `TRANSPORT_MATRIX.md`.

## 6. Which FCC implementations are actually identical?

**NLD FCC, FreeFCC and FreeFCC-USB. Byte-for-byte.**

**FACT.** 21/21 frames identical, identical ordering, identical timing
(`rounds` 2, 30 ms inter-frame, 100 ms inter-round, 50 ms read window),
identical sender `130`, and a 4/4 identical keepalive between NLD and FreeFCC.

**FACT.** `DJI-FCC-Unlock-iOS` is a **22-frame divergent fork** — inserts
`03/f9 9ad152ae01` at position 3, and uses `5553…` channel payloads where the
others use `4155…` (differing by exactly `0x1400`).

**FACT.** `DJI-FCC-HACK` shares **no** profile data and uses a different
transport (USB CDC-ACM serial at `0x2CA3:0x1020`).

**FACT.** Free Fly contains **no** FCC sequence at all.

**INFERENCE.** NLD consumes or redistributes the FreeFCC profile corpus rather
than reimplementing it. Direction of derivation is **not established**.

## 7. Which tools patch DJI Fly instead of talking DUML directly?

**DJIFCC and RedFly. Both keep DJI's own package names and re-sign.**

**FACT.** DJIFCC: `dji.go.v5` / `v6` / `v4`, one vendor certificate
`CN=DJIFCC.APP` (`cad73496…`), v1+v2+v3.

**FACT.** RedFly's catalog: `RedFly-1.21.12-build-156-Phone-RCPro-v5.apk` and
`-v6.apk` — the same package split, and the **same DJI 1.21.12 release** as the
DJIFCC build analysed here.

**INFERENCE.** Converging on the same base release and package matrix is
consistent with a shared market. It is **not** evidence of shared tooling, patch
or author.

**FACT.** Both vendor classes remove DJI's integrity protection: DJIFCC omits
`libAppGuard.so`/`libAppGuard-x86.so`/`libdatajar.so`; RedFly advertises
`-noAppGuard` product variants.

## 8. How do RC-N1/N2/N3 and smart-controller transport differ?

Summarised in `TRANSPORT_MATRIX.md`. The essential finding: **five distinct
mechanisms** are in use, and no two projects that reach the aircraft do so the
same way.

## 9. Which hacks persist across reboot, and which must be re-applied?

**None of the mechanisms studied persist automatically, and each fails
differently.**

| Tool | Mechanism | Persistence |
|---|---|---|
| Free Fly | FC parameter write | **if the FC accepts and stores it** — unverified |
| NLD FCC | radio reconfiguration + 2 s keepalive | **explicitly not** — the keepalive exists because DJI Fly resets the radio to CE |
| DJIFCC / RedFly | patched app | **while installed**; lost on a real DJI update |
| Drone-Hacks | parameter write, licence-gated | **if the FC accepts it**, and gated by an online licence |

**FACT.** NLD's own profile text: *"Re-applies FCC radio mode every 2s over TCP
40009 to prevent DJI Fly from resetting to CE."* That is an explicit, vendor-
stated answer to this question, and it is why the mechanism is described as
borrowed time rather than a stored setting.

## 10. Which capabilities require firmware modification rather than parameter writes?

**Region/regulatory state is the clearest case.**

**FACT.** Free Fly's catalogue names `ce_country_type` and
`ce_regulatory_level` — firmware-level parameters. **FACT.** NLD's sequence uses
`cmdSet 3 / cmdId 0xF9` hashed parameter writes. **FACT.** Neither is a
firmware patch; both are parameter-level.

**INFERENCE.** The line between "parameter write" and "firmware modification"
is not established by static analysis for region settings. What is established:
no tool in this corpus patches firmware. Tools that claim to do more are either
patching the *application* (DJIFCC, RedFly) or writing parameters.

**FACT — an asymmetry worth stating.** `cmdSet 3 / cmdId 0xF9`, the hashed
parameter write NLD uses six times, is **present but unreachable** in Free Fly.
Free Fly's only live write is `0xE3`.

## 11. Which public project has the most complete documentation?

**`DJI-FCC-Unlock-iOS`, with a licensing caveat.**

**FACT.** It carries extensive technical documentation of the ExternalAccessory
transport, `com.dji.logiclink`/`com.dji.protocol`, the RCLink envelope, DUML
parsing, bootstrap, keepalive, FCC profiles and service-mode timing.

**FACT — and the caveat is not cosmetic.** It is licensed **PolyForm Noncommercial
1.0.0**: source-available but **not OSI open source**, with commercial
redistribution constraints. It is the best documentation here and the one that
must not be described as "open source".

**FACT.** For *protocol constants*, `o-gs/dji-firmware-tools` is the most
authoritative (Wireshark dissectors, `cmdSet` tables) and is GPL-3.0.

## 12. What is sufficient to build a clean read-only DJI diagnostic library?

**Sufficient today, and built:** `research/flylib` — DUML codec, streaming
framer with resync, 14 command builders, parameter type table and value codec,
2017 selection policy, snapshot JSON capture/import/diff, a replay path with no
device, and a mutation gate disabled by default. 198 tests, zero skips, no
hardware.

**Verified**, not assumed: CRC tables compared element-by-element against the
APK's own; golden vectors checked field by field against smali rather than
captured from the implementation.

## 13. What remains unknown after static analysis?

1. Whether any `0xE3` parameter write actually persists on real firmware.
2. Whether `ce_country_type` is writable at all through the FC Assistant path.
3. The DUSS message framing (no length prefix visible in strings).
4. What `PKDS` (`0x504B4453`) is — 4,277 bytes at 7.95 bits/byte, unclassified.
5. Where Drone-Hacks' AES key and IV for its cached compatibility map live.
6. Everything inside RedFly — no artifact acquired.
7. The CRC *polynomials* in Drone-Hacks (tables are built at runtime).

## 14. What specific hardware captures would resolve those unknowns?

Enumerated with expected traffic and risk levels in `HARDWARE_TEST_PLAN.md`. The
highest-value capture is a **region-relevant `0xE3` write with a subsequent
power cycle and re-read**, because it converts the single largest unknown into a
yes/no answer.

## 15. Confidence summary

```
PROTOCOL_LINEAGE_CONFIDENCE     = HIGH    DJI's protocol is public knowledge;
                                           three independent codebases agree.
DIRECT_CODE_LINEAGE_CONFIDENCE  = LOW     Separately implemented codebases.
DIRECT_CODE_COPY_EVIDENCE       = NONE    No HIGH criterion met.
SHARED_DATA_EVIDENCE            = HIGH    NLD / FreeFCC / FreeFCC-USB ship a
                                           byte-identical 21-frame profile.
```