# Pinned public-repository inventory

Six repositories, cloned locally under `research/public/` (gitignored) and pinned
by commit. This corpus serves two purposes: it is the **control group** for the
lineage assessment in `docs/APP_LINEAGE.md`, and it is the reference against
which the proprietary artefacts are compared.

Machine-readable pins: `work/generated/public_repos.json`.

---

## 1. Pins

| Project | Commit | Date | Primary language | Licence |
|---|---|---|---|---|
| `doesthings/FreeFCC` | `597157bd5212` | 2026-08-10 | Kotlin | **AGPL-3.0** |
| `doesthings/FreeFCC-USB` | `55da2d3bc6c5` | 2026-08-12 | Kotlin | **AGPL-3.0** |
| `M4TH1EU/DJI-FCC-HACK` | `84f149f58a20` | 2026-01-20 | Kotlin | **GPL-3.0** |
| `andreapianidev/DJI-FCC-Unlock-iOS` | `5ef860adafd1` | 2026-09-20 | Swift | **PolyForm Noncommercial 1.0.0** |
| `o-gs/dji-firmware-tools` | `195692263c26` | 2026-07-21 | Python, Lua | **GPL-3.0** |
| `djiparam` (`lmdegreeds`) | `1b396b1a0ade` | 2026-07-13 | Java, Python | **MIT** |

Head-of-pin subjects:

- FreeFCC — "v1.5.5: robust aircraft serial detection + manual entry (#45)"
- FreeFCC-USB — "v2.2: sweep every known-working command path, tighten the burst"
- DJI-FCC-HACK — "Add DJI Mini 2 SE to the list of drones"
- DJI-FCC-Unlock-iOS — "v1.8.1 build 12: make the log ask for the census"
- dji-firmware-tools — "amba_sys_hardcoder: Fix typo, 'definiton' -> 'definition'"
- djiparam — "Все параметры: сверка имени параметра с бортом при чтении/записи (v0.16)"

**Licensing note that matters for citation.** `DJI-FCC-Unlock-iOS` is
**PolyForm Noncommercial 1.0.0** — source-available but **not OSI open source**.
It may be read and compared, but it should not be described as "open source",
and redistribution has commercial constraints the OSI licences do not. The other
five are OSI-licensed.

## 2. Transport — every project, cited

| Project | Transport | Evidence |
|---|---|---|
| **FreeFCC** | local **TCP 127.0.0.1:40009** | `DumlTransport.kt:15` "*(127.0.0.1:40009) on their controllers*"; `:203` "Sends DUML frames to the controller's local TCP proxy at 127.0.0.1:40009" |
| **FreeFCC** (LED path) | **TCP 40007** | `FccViewModel.kt:596` "Uses port 40007 (different from the standard 40009 DUML port)" |
| **FreeFCC-USB** | **USB host** | `DumplTransport.kt:8-9` imports `UsbDevice`, `UsbDeviceConnection` |
| **DJI-FCC-HACK** | **USB CDC-ACM serial**, `0x2CA3:0x1020` | `MainActivity.kt:143` `addProduct(11427, 4128, CdcAcmSerialDriver::class.java)` |
| **DJI-FCC-Unlock-iOS** | **MFi ExternalAccessory** | `AboutPage.swift:149` `InfoRow(label: "Transport", value: "MFi ExternalAccessory")` |
| **djiparam** | local **TCP 40008 inject / 40007 read** | `Duml.java:16` "inject request on 127.0.0.1:40008, read replies on 127.0.0.1:40007 (busy downstream)" |
| **dji-firmware-tools** | none (offline firmware tooling) | — |
| *Free Fly (this project)* | raw USB bulk, `0x2CA3`, pids `0x10`/`0x18`/`0x20` | `res/xml/device_filter.xml` |
| *NLD FCC (proprietary)* | TCP 40009 / 40007, native `libnld-core.so` | profile prose + `DUSS` strings |

**INFERENCE.** The three controller-side projects (FreeFCC, djiparam, NLD) all use
the **same local TCP proxy on the controller** — 40009 for injection, 40007 where
a second path is needed. FreeFCC-USB, DJI-FCC-HACK, Free Fly and Drone-Hacks all
reach the aircraft over **USB** instead, but by three different mechanisms:
host serial (`DJI-FCC-HACK`), raw bulk (`Free Fly`), and pyserial on desktop
(`Drone-Hacks`).

## 3. Shared command data

**FACT.** NLD FCC, FreeFCC and FreeFCC-USB ship a **byte-identical 21-frame FCC
profile**, with identical timing metadata and sender, and NLD's 4-frame keepalive
matches FreeFCC's 4/4. See `docs/COMMAND_CORPUS.md`.

**FACT.** FreeFCC's own test asserts the shared profile's invariants:

```kotlin
// DumplBuilderTest.kt
assertEquals("frame count", 21, frames.size)
// AUTOTEST cmdSet 16 / cmdId 88 brackets the sequence.
assertEquals("first frame cmdSet", 16, first.s)
assertEquals("first frame cmdId", 88, first.i)
```

`FreeFCC-USB` has no keepalive asset; `FreeFCC` and NLD do.

**FACT.** `DJI-FCC-Unlock-iOS` carries a **22-frame divergent fork**: it inserts
`03/f9 9ad152ae01` at position 3 and uses `5553…` channel payloads where the
others use `4155…`.

## 4. The control group — `djiparam`

`djiparam/src/com/djiparam/Duml.java` is the single most useful artefact in this
corpus for the lineage question, because it is an **independent implementation
that contains the same markers** this project first read out of Free Fly's
bytecode:

```java
// 40009 inject path (fcc uses 0x0A there). CRC8 init 0x77 + CRC16 init 0x3692 (see tables below).
static int crc8(byte[] d, int off, int len) { int c = 0x77; ...
static int crc16(byte[] d, int off, int len) { int c = 0x3692; ...
p[2] = 1; p[3] = 0;                       // unknown1 = 1 (u16)
```

plus `get_table_attributes (0xE0)` and `get_info (0xE1)`.

**Consequence.** The CRC seeds, the parameter-hash modulus, the command ids and
the reserved field that Drone-Hacks names `unknown1` are **public protocol
knowledge**. Any of them appearing in two proprietary projects is therefore
evidence of shared *protocol* lineage and not of shared *code*. This is the basis
for `DIRECT_CODE_COPY_EVIDENCE = NONE` in `docs/APP_LINEAGE.md`.

`djiparam` also documents something the others do not: the 2017 metadata reply
layout — `status:u16, table:u16, index:u16, type_id:u16, size:u16, def[10:14],
min[14:18], max[18:22], name\0`, with 4-byte `def`/`min`/`max` decoded by type.

## 5. Other findings

**FACT.** `dji-firmware-tools` contains an authoritative `cmdSet` table
(`dji-dumlv1-proto.lua:83-110`) and a per-module command-name table, plus
Wireshark dissectors. Its `dji_flyc_param_ed.py` and related tools operate on
**firmware images**, not on a live aircraft.

**FACT.** `DJI-FCC-Unlock-iOS` ships a `FreeFCC/Resources/profiles/` directory
containing the same `fcc.json` / `ce_restore.json` schema as the Android
projects, in its **22-frame** variant.

**FACT.** `FreeFCC-USB` `DumplBuilderTest.kt:201` names the AUTOTEST bracket in a
comment: *"AUTOTEST cmdSet 16 / cmdId 88 brackets the sequence."*

## 6. Provenance cautions

**INTEGRITY NOTE.** During GitHub discovery a repository impersonating
`doesthings/FreeFCC` **by name** was found carrying a 489 KB `.zip` inside
`src/main/java/`. It was **not** cloned and its payload was **not** retrieved.
Any fork of FreeFCC of unknown provenance should be treated as suspect; the
pins in §1 are the ones this project actually analysed.

**INFERENCE.** `dji-firmware-tools` is the most likely origin of the shared
protocol knowledge in this ecosystem: it is GPL, it publishes dissectors and
tables, and its own header documents the crc8/crc16 seeds. Several other
projects credit it. That makes it the plausible upstream reference — which is
precisely why it is the right control: knowledge that flows from a public
repository cannot establish private lineage between two of its consumers.

## 7. Not done

- No repository was modified; all six are read-only clones.
- Individual project READMEs were not used as evidence for any claim — every
  statement above cites a file and line, or the commit pin.
- RedFly and the proprietary artefacts were not compared against
  `DJI-FCC-Unlock-iOS`'s divergent 22-frame profile beyond the divergence point
  already recorded in `docs/COMMAND_CORPUS.md`.