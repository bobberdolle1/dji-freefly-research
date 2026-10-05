# Normalized command corpus

Answers the FCC-sequence lineage question with byte-level evidence rather than
by resemblance.

Generated evidence:
- `research/generated/command_corpus.json` — NLD's profiles, normalised
  (`tools/nld_command_corpus.py`)
- `research/generated/fcc_sequence_comparison.json` — the cross-project
  comparison below

Pinned public commits used as inputs:

| Project | Commit |
|---|---|
| `doesthings/FreeFCC` | `597157b` |
| `doesthings/FreeFCC-USB` | `55da2d3` |
| `M4TH1EU/DJI-FCC-HACK` | `84f149f` |
| `andreapianidev/DJI-FCC-Unlock-iOS` | `5ef860a` |

---

## 1. Normalisation

Fields that vary per transmission are excluded from frame identity:

| Field | Treatment | Why |
|---|---|---|
| sequence number | excluded | allocated by the sender at send time; absent from every profile |
| header CRC / frame CRC | excluded | computed at transmission time |
| payload length (`d`) | retained for reference, excluded from identity | fully determined by the payload |
| aircraft serial | masked (`<serial>`) | substituted per airframe; must not change command identity |

**Identity** = the ordered triple `(cmdSet, cmdId, payload hex)`. Ordering is
part of the identity, because an FCC sequence is not a set.

## 2. The FCC Universal sequence — byte-level equivalence

All four projects that ship a profile use the same schema: a JSON object with
`{s, i, d, p, note}` per frame, plus `rounds`, `inter_frame_delay_ms`,
`inter_round_delay_ms`, `read_window_ms`, `sender`, `cmd_type`.

**FACT.** Frame counts and pairwise identity:

| Comparison | Frames | Identical | Fraction |
|---|---|---|---|
| **NLD FCC vs FreeFCC** | 21 vs 21 | **21** | **1.00** |
| **NLD FCC vs FreeFCC-USB** | 21 vs 21 | **21** | **1.00** |
| **FreeFCC vs FreeFCC-USB** | 21 vs 21 | **21** | **1.00** |
| NLD/FreeFCC/FreeFCC-USB vs **DJI-FCC-Unlock-iOS** | 21 vs **22** | 3 | 0.14 |

**FACT.** Timing metadata is also identical across NLD, FreeFCC and
FreeFCC-USB: `rounds` 2, `inter_frame_delay_ms` 30, `inter_round_delay_ms` 100,
`read_window_ms` 50. Sender is `130` (`MOBILE_APP, index 4` = `(4<<5)|2`, the
same device-byte packing Free Fly implements), `cmd_type` 32
(`Request, ACK_BEFORE_EXEC, no encryption`).

**FACT.** The keepalive matches too: **NLD's `fcc_keepalive.json` and FreeFCC's
are 4/4 frames identical**.

**FACT.** `FreeFCC-USB` ships `fcc.json` and `ce_restore.json` but no keepalive;
`FreeFCC` and NLD ship all seven profiles with identical names.

### The sequence itself

| # | cmdSet | cmdId | Target | Action |
|---|---|---|---|---|
| 0 | `0x10` | `0x58` | AUTOTEST | enter service mode |
| 1 | `0x06` | `0x72` | REMOTE_RADIO | set region to FCC (01) |
| 2 | `0x03` | `0xF9` | FLYCONTROLLER | write param `8a237103f401` |
| 3 | `0x00` | `0x00` | WM330/WM220 | activate change |
| 4 | `0x00` | `0x32` | LB_68013_SKY | country code `11` |
| 5 | `0x03` | `0xAF` | FLYCONTROLLER | write param |
| 6–7 | `0x07` | `0x30` | WIFI | channel group 2.4G / 5.8G |
| 8–9 | `0x09` | `0x27` | OFDM | 2.4G / 5.8G power limit |
| 10 | `0x07` | `0x18` | WIFI | write channel map |
| 11 | `0x07` | `0x19` | WIFI | set channel flag |
| 12–13 | `0x03` | `0xF9` | SVO | write param ON / OFF |
| 14 | `0x00` | `0xE5` | LB_68013_SKY | country code `22` |
| 15–16 | `0x03` | `0xF9` | FLYCONTROLLER | write param |
| 17–18 | `0x06` | `0x8C` | LB_MCU_SKY | radio parameters 03, 01 |
| 19 | `0x06` | `0x72` | REMOTE_RADIO | **commit region change** |
| 20 | `0x10` | `0x58` | AUTOTEST | exit service mode |

**Ordering, timing and keepalive are therefore equivalent** between NLD FCC,
FreeFCC and FreeFCC-USB, frame for frame.

## 3. DJI-FCC-Unlock-iOS is a divergent fork

**FACT.** Its `fcc.json` has **22** frames, not 21. It matches the others at only
positions 0–2, and then diverges in two ways:

1. **It inserts an extra frame at position 3**: `03/f9 9ad152ae01` — another
   hashed FC parameter write (hash `0xAE52D19A`, value `01`).
2. **It uses different channel payloads**: frames 7/8 are `55530000555300000100`
   where the others use `41550000415500000100`, and frame 11 is `ff555300`
   against `ff415500`.

**INFERENCE.** `0x4155` = 16725 and `0x5553` = 21843 differ by exactly `0x1400`.
That is not a channel selection difference; it looks like a **structurally
different payload layout** rather than a different value. Reading the iOS
variant's intent requires its own decoder and is not attempted here.

**INFERENCE.** The iOS port is a *fork with edits*, not a direct copy: it grew a
frame and changed payload encoding. The other three share one profile lineage.

## 4. DJI-FCC-HACK is a different mechanism

**FACT.** It ships no profile JSON. Its `MainActivity.kt:143` reads:

```kotlin
addProduct(11427, 4128, CdcAcmSerialDriver::class.java)
```

11427 = `0x2CA3` (DJI), 4128 = `0x1020`, and the driver is
**`CdcAcmSerialDriver`** from `usb-serial-for-android`.

**INFERENCE.** DJI-FCC-HACK reaches a *different* USB product and speaks
**CDC-ACM serial** rather than raw bulk. It is therefore a different transport
path to the aircraft from Free Fly (`0x10`/`0x18`/`0x20`, raw bulk), and it
assembles its frames in code rather than from a shared profile asset. It cannot
be compared frame-for-frame with the others and is not counted as part of this
lineage.

## 5. Transport matrix for the FCC sequence

| Project | Transport | Evidence |
|---|---|---|
| **NLD FCC** | TCP **40009** (fcc, keepalive), **40007** (led), native impl, "outer wrapper" | profile prose; ports absent from DEX, present in `libnld-core.so` context |
| **FreeFCC** | not determined from assets | ships identical profiles to NLD |
| **FreeFCC-USB** | USB host | project name and `usb` package |
| **DJI-FCC-Unlock-iOS** | MFi ExternalAccessory | `com.dji.logiclink` / RCLink stack in project |
| **DJI-FCC-HACK** | USB **CDC-ACM serial**, `0x2CA3:0x1020` | `MainActivity.kt:143` |
| **Free Fly** | USB **raw bulk**, `0x2CA3`, pids `0x10`/`0x18`/`0x20`, **no CDC-ACM** | `device_filter.xml`, `UsbSerialManager` |

## 6. The link to Free Fly

**FACT.** Six of the 21 frames use `cmdSet 0x03 / cmdId 0xF9` with payloads of
`uint32le(hash) ‖ value` — for example `d04aeffb01` / `d04aeffb00`, sharing the
leading `d0 4a ef fb` and differing only in the value byte.

**FACT.** `0xF9` on cmdSet 3 is exactly Free Fly's `CMD_FC_PARAM_WRITE_2015`
(−7 = `0xF9`) on `CMD_SET_FC`, whose payload Free Fly builds as
`uint32le(paramHash(name)) ‖ value`.

**FACT.** Free Fly's `versionInquiry` is `cmdSet 0 / cmdId 1`; NLD's
`device_info.json` is the same command with an empty payload.

**INFERENCE.** The hashed-parameter-write convention is shared, but it is a DJI
firmware convention — Drone-Hacks names the same class
(`WriteParamVal*ByHash2015Rq`) and the public corpus documents it — so it is
**protocol convergence, not evidence of a shared implementation with NLD or
FreeFCC**. It is a different matter from the 21-frame profile data, which is
identical byte-for-byte between NLD and the public projects and is direct
shared *data*.

## 7. Conclusions

**FACT.** NLD FCC, FreeFCC and FreeFCC-USB ship a **byte-identical 21-frame FCC
profile** with identical ordering, identical timing metadata, identical sender,
and an identical 4-frame keepalive.

**INFERENCE.** This is **shared data**, not independent implementation: it
matches the project's HIGH-tier criteria (identical large constant data,
identical sequence and ordering). NLD is consuming or redistributing the
FreeFCC profile corpus rather than reimplementing it.

**INFERENCE.** Direction of derivation is **not established** by this evidence.
FreeFCC is public and pinned; NLD is commercial. File sizes differ (NLD 2,906 B
vs FreeFCC-USB 3,815 B) because of differing prose, so content lineage is
established while chronology is not.

**FACT.** DJI-FCC-Unlock-iOS is a **22-frame divergent fork** with an inserted
frame and different channel payload encoding.

**FACT.** DJI-FCC-HACK uses a **different USB product and a different transport**
(CDC-ACM serial) and shares no profile data.

**FACT.** Free Fly shares **no** part of this sequence. It contains no service
mode, no radio, WiFi or OFDM commands, and no FCC profile — only FC Assistant
parameter commands over raw USB bulk.

## 8. Not established here

- Whether NLD's APK embeds FreeFCC's assets verbatim at build time, or the two
  share an upstream repository. Both produce the same frames; the mechanism is
  not visible from the artefacts.
- What `0x4155`/`0x5553` mean in the channel-map payloads, in either variant.
- FreeFCC's own transport (its assets carry no transport metadata; only NLD's
  prose names ports).
- The five payload bytes at position 2 are described only as "write param"; the
  parameter names they hash to are not recoverable without the hash inverted.