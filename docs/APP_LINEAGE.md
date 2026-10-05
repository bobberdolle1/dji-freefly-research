# App and code lineage

Closes the lineage question with **separate** scores, because "we implement the
same protocol" and "we share code" are different claims that the same evidence
can be made to support or not.

Method: every candidate marker was checked against the **pinned public corpus**
before being allowed to count. A marker that also appears in a public project
proves public protocol knowledge, not private lineage.

```
PROTOCOL_LINEAGE_CONFIDENCE      = HIGH
DIRECT_CODE_LINEAGE_CONFIDENCE   = LOW   (Free Fly 1.0 vs Drone-Hacks 1.48)
DIRECT_CODE_COPY_EVIDENCE        = NONE
```

---

## 1. What "lineage" means here

**Protocol lineage** — these projects were all derived from the same
*description of DJI's protocol*, whether obtained independently or from shared
public reverse-engineering. It is a statement about knowledge, not about code.

**Direct code lineage** — one project's source, or a close derivative of it,
was used to build another.

The two are scored separately because the evidence for the first is strong and
the evidence for the second is absent, and collapsing them would produce a
confident-sounding number that means nothing.

---

## 2. The public corpus, and why it is the control

Pinned at the time of this analysis:

| Project | Commit | Public? | Licence |
|---|---|---|---|
| `doesthings/FreeFCC` | `597157b` | yes | (per repo) |
| `doesthings/FreeFCC-USB` | `55da2d3` | yes | (per repo) |
| `M4TH1EU/DJI-FCC-HACK` | `84f149f` | yes | (per repo) |
| `andreapianidev/DJI-FCC-Unlock-iOS` | `5ef860a` | yes | **PolyForm Noncommercial 1.0.0 — not OSI open source** |
| `o-gs/dji-firmware-tools` | `1956922` | yes | (per repo) |
| `djiparam` | `1b396b1` | yes | (per repo) |

These exist because DJI's format is public knowledge, which makes them the
control group: **any marker that also appears here cannot be evidence of a
private relationship between two other projects.**

---

## 3. Candidate markers, tested

### 3.1 CRC-8 init `0x77` and CRC-16 init `0x3692`

**Appears in:** Free Fly, Drone-Hacks, **and** `djiparam/src/com/djiparam/Duml.java`:

```java
// 40009 inject path (fcc uses 0x0A there). CRC8 init 0x77 + CRC16 init 0x3692 (see tables below).
static int crc8(byte[] d, int off, int len) { int c = 0x77; ...
static int crc16(byte[] d, int off, int len) { int c = 0x3692; ...
```

**Verdict: NOT lineage evidence.** Public.

**What it *is* good for:** it is strong independent validation of this project's
Free Fly protocol recovery, which derived those values by brute-forcing the
APK's own CRC tables against every polynomial. Three codebases agreeing is
excellent evidence the reading is right.

### 3.2 The `unknown1` reserved field

**Appears in:** Drone-Hacks (`WriteParamVal*ByIndex2017Rq._fields_`), Free Fly
(writes a bare reserved zero in the same position), and **`djiparam`**, which
uses the literal identifier and even explains the variant:

```java
p[2] = 1; p[3] = 0;                       // unknown1 = 1 (u16)
...
* (NO unknown1 — the old getInfoName used a 6-byte payload, which this FC silently ignores).
* Request payload is just <table:u16> (no unknown1)
```

**Verdict: NOT lineage evidence.** This was the marker I had called "the
sharpest item", and checking it against the public corpus is exactly why that
check was worth doing — it fails.

### 3.3 Command ids `0xDF`, `0xF0`, `0xF8`, `0xF9`, `0xE0`, `0xE1`, `0xE2`, `0xE3`, `0x82`, `0x81`

**Appears in:** Free Fly and Drone-Hacks, and **`djiparam`** independently
(`get_table_attributes (0xE0)`, `get_info (0xE1)`).

**Verdict: NOT lineage evidence.** Command ids are the public interface of a
third-party protocol; they are *forced* to agree by anyone who implements it.

### 3.4 Parameter hash `((h << 8) + b) % (2**32 - 5)`

**Appears in:** Free Fly, Drone-Hacks (`0xFFFFFFFB`), and is documented in the
public corpus.

**Verdict: NOT lineage evidence.** One divergence is instructive: Drone-Hacks
encodes the name with `gbk`, Free Fly with US-ASCII. Two implementations that
shared source would more likely share the encoding choice.

### 3.5 Tolerant sequence matching

**FACT.** Drone-Hacks' `packet_header_is_reply_for_request(rplhdr, reqhdr,
responsebit_check, seqnum_check)` makes both checks optional.

**Verdict: inconclusive.** Not found in the searched public projects by that
name. But making a sequence check optional is the obvious behaviour of any
implementation that must tolerate an async link, and an absent string match in
four repositories is weak negative evidence. Not scored.

### 3.6 The 21-frame FCC profile — the one thing that *is* shared data

**FACT.** NLD FCC, FreeFCC and FreeFCC-USB ship a **byte-identical 21-frame
profile**, with identical timing metadata, identical sender, and an identical
4-frame keepalive (NLD vs FreeFCC). See `docs/COMMAND_CORPUS.md`.

**Verdict: HIGH-tier shared data.** This meets the project's HIGH criteria —
identical large constant data with identical ordering.

**It is not about Free Fly.** Free Fly contains no FCC sequence at all. This
finding is about the NLD/FreeFCC family, and it does not touch the Free Fly ↔
Drone-Hacks question.

**INFERENCE.** NLD is consuming or redistributing the FreeFCC profile corpus
rather than reimplementing it. Direction of derivation is **not established**.

---

## 4. What the evidence positively excludes

**DIRECT_CODE_COPY_EVIDENCE = NONE.** None of the project's HIGH criteria for
copied code is met between Free Fly and Drone-Hacks:

| Criterion | Result |
|---|---|
| Identical uncommon code | ✗ different languages, no shared routine |
| Identical large constant tables | ✗ no table shared; the 256-entry CRC tables are regenerated from polynomials in both |
| Identical bugs | ✗ none found |
| Identical unusual packet construction | ✗ both are *required* by DJI's format |
| Identical strings with the same typos | ✗ none found |
| Identical binary resources | ✗ no shared resource; different platforms |

What is positively *observed* to differ:

| | Drone-Hacks 1.48 | Free Fly 1.0 |
|---|---|---|
| Language / build | Cython + Python 3.11, PyInstaller | Kotlin, AGP, Compose |
| Platform | Windows desktop, Tkinter | Android, Compose |
| Transport | USB serial (pyserial) | raw USB bulk |
| 2015 protocol | live (`do2015Params`) | dead code |
| Framer | byte state machine, damage detection | single-shot, no resync |
| Encryption | full `Encrypt*` family | declared, never used |
| HW register / gimbal calib | present | absent |
| Type table | 12 entries | 10 entries |
| Name encoding | `gbk` | US-ASCII |
| Naming | `Rq`/`Re` suffixes | `get…`/`read…` |
| Licensing | vendor API + DJI account API | none; no INTERNET permission |
| Obfuscation | Cython-compiled | none (debug build) |

---

## 5. Scores

### PROTOCOL_LINEAGE_CONFIDENCE = **HIGH**

Free Fly 1.0, Drone-Hacks 1.48, NLD FCC, FreeFCC, FreeFCC-USB, DJI-FCC-HACK,
DJI-FCC-Unlock-iOS and `djiparam` all implement DJI's DUML protocol and the FC
Assistant parameter commands. The shared vocabulary is attested in three
independent directions: Free Fly's own bytecode, Drone-Hacks' bytecode, and
public source. Any two conforming implementations must agree on the command
ids, the reserved field, the CRC seeds and the hash modulus — and they do.

**Caveat, and it is a real one.** "Lineage" here is lineage of *public protocol
knowledge*. It does not distinguish "read the same wiki" from "read the same
other project". Distinguishing those would require contributor evidence this
project does not have.

### DIRECT_CODE_LINEAGE_CONFIDENCE (Free Fly vs Drone-Hacks) = **LOW**

Every candidate marker failed the public-corpus test in §3. The two differ in
language, platform, transport, architecture, naming convention, protocol coverage
(Drone-Hacks has encryption, HW registers, gimbal calibration and a live 2015
path; Free Fly has none of those), type-table width, name encoding and
obfuscation posture.

**LOW, not NONE**, because two Android/desktop tools from the same problem
domain by the same community remain a priori more likely to be inspired by each
other than by chance. That is an argument from the problem space, not from
code.

### DIRECT_CODE_COPY_EVIDENCE = **NONE**

No copy is demonstrated. The project's HIGH criteria are all unmet. If the
operator's question is "did one author copy the other", the answer on this
evidence is **no evidence of it**.

---

## 6. The separate, affirmative finding

One HIGH-tier result exists in this corpus and it should not be diluted by the
scores above:

**NLD FCC, FreeFCC and FreeFCC-USB ship a byte-identical 21-frame FCC profile.**

That is shared *data*, it is between a commercial product and two public ones,
and Free Fly is not party to it. It is recorded in `docs/COMMAND_CORPUS.md` and
scored separately from the Free Fly lineage question for exactly that reason.

---

## 7. What would change these scores

| Evidence | Effect |
|---|---|
| Contributor or authorship overlap between Free Fly and Drone-Hacks | raises DIRECT_CODE_LINEAGE above LOW |
| An identical constant *table* (not just a polynomial) in both | raises it toward MEDIUM |
| The same bug in both | raises it toward MEDIUM |
| Evidence Free Fly's author consumed FreeFCC data | none here — Free Fly has no FCC profile |
| Attribution evidence for the `PKDS` signing block | currently unclassified; would be separate |