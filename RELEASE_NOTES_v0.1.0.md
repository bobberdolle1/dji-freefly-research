# Free Fly 1.0 Protocol Research — Initial Public Release

Clean-room reverse engineering and documentation of the DUML flight-controller
parameter protocol used by the **Free Fly 1.0** Android application
(`com.dronehacks.app`).

**NO PROPRIETARY APK, EXE OR FIRMWARE IS DISTRIBUTED IN THIS RELEASE.** All
analysis was performed locally on samples obtained outside the repository.

---

## What this release contains

### Free Fly DUML recovery

The complete wire format, recovered from the application's bytecode and verified
against its own embedded constants:

- **Frame layout** — magic `0x55`; uint16 LE `verLength = (version << 10) |
  totalLength`; an **11-byte** header before the payload, followed by 2 CRC bytes.
- **Device byte** — `(index & 7) << 5 | (type & 0x1F)`.
- **Type byte** — `(packetType & 1) << 7 | (ackType & 3) << 5`.
- **CRC-8** — reflected, polynomial `0x8C`, initial value `0x77`, over bytes
  `[0, 3)`.
- **CRC-16** — the standard LSB-first reflected CRC-16 step over the table for
  polynomial `0x8408` (reflection of `0x1021`), initial value `0x3692`, no final
  XOR.
- **Command table** — 14 request builders with sender, receiver, ack type,
  payload and live/dead status.

The CRC polynomials were **derived, not assumed**: the application ships its own
256-entry tables, and both were matched by brute force against every candidate
polynomial, giving a unique match.

### 2017 parameter protocol

Free Fly's live protocol is the **2017 table/index** scheme. The **2015**
implementation is present in the binary but **unreachable** — verified by
call-site analysis across the whole DEX tree, where `readAll2015` has no caller
outside its own coroutine continuation and `getParamInfo2015` /
`writeParamValue2015` have zero callers.

The **write path is live**, traced end to end from the parameter edit dialog
through the ViewModel and repository to the 2017 builder, including the
per-write unlock gate.

### `flylib` — an independent, read-only-first implementation

DUML encode/decode, both checksums, a streaming framer with resynchronisation,
the recovered command builders, the parameter type table and value codecs, the
protocol-selection policy, replay/scripted/dry-run/live transports, a snapshot
capture-and-compare path, and a mutation gate that is **disabled by default**.

### Drone-Hacks wire comparison

Command identifiers and payload layouts recovered from the Drone-Hacks 1.48
executable's embedded bytecode and compared against Free Fly:

- **10 / 10** command identifiers match
- **6 / 6** payload layouts match

### FCC corpus finding

NLD FCC, FreeFCC and FreeFCC-USB were found to ship a **byte-identical 21-frame
FCC profile**, with identical timing metadata, and a 4/4 identical keepalive
between NLD and FreeFCC. DJI-FCC-Unlock-iOS carries a 22-frame divergent fork.

Separately, a pinned public project (`djiparam`) was shown to independently
contain the same CRC seeds, command ids and the same `unknown1` field name —
which is what separates **protocol lineage (HIGH)** from **direct code lineage
(LOW)** and holds **direct copying evidence at NONE**.

---

## Hardware-validation status

**STATIC RESEARCH COMPLETE.**
**HARDWARE VALIDATION NOT YET PERFORMED.**

Nothing in this release has been sent to an aircraft. The protocol described
here is recovered from bytecode and verified against the application's own
constants — **not** from observed traffic. In particular it remains unknown
whether a parameter write persists across a power cycle.

A phased plan with explicit risk levels is in `docs/HARDWARE_TEST_PLAN.md`.

---

## Verification

| | |
|---|---|
| Tests | 200 passing, 0 skipped with a sample present |
| Tests, repository contents only | 198 passing, 2 skipped |
| Proprietary binaries in tree | **0** |
| Proprietary binaries in full history | **0** |
| Tests requiring a proprietary sample | **none** — the suite runs from the public repository alone |

## Licence

No licence is declared yet. `docs/LICENSING.md` records the provenance audit
and why the choice was left to the repository owner.
