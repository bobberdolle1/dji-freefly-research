# Hardware test plan

**Nothing in this project has been executed against an aircraft.** Every result
so far is static analysis. This document defines what a hardware pass would
require, what it would observe, and how risky each step is.

**Read-only probes come first and need no approval beyond physical safety.
State-changing commands require explicit operator approval before anything is
sent.**

Safety rules that apply to every step below:

1. **Props removed, battery disconnected** for any state-changing step, or an
   airframe that cannot arm.
2. Read-only steps may proceed once the operator confirms a safe bench.
3. **No step may be run from an unfinished build of this library.** Use a
   released, tested build; `flylib` is research code.
4. Anything that can persist is treated as **persistent** until a power cycle
   proves otherwise.
5. Record every frame transmitted and every reply received, both sides.

---

## 1. Phase A — read-only, no state change

**Risk: none.** Every command below is a read. Nothing is transmitted that the
FC is asked to modify.

| # | Probe | Frame | Expected observation | Resolves |
|---|---|---|---|---|
| A1 | Link bring-up | the 5× `0x30` init burst, then read 2000 ms | whether the bulk IN endpoint emits anything | confirms the USB path end-to-end |
| A2 | Version inquiry | `versionInquiry` — `cmdSet 0`, `cmdId 1`, empty payload | HW/LDR/app version strings | is `awaitPacket` matching correctly |
| A3 | Registration | `replyRegAck`, `replyRegDev` | whether the FC expects the handshake | is Free Fly's registration path required? |
| A4 | AC response | whatever `fetchDeviceInfo` issues | aircraft serial and codename | where the serial/codename really come from |
| A5 | Table discovery | `getTableAttribs2017(table)` for tables 0..N | per-table declared counts | **the table bound this project could not pin** |
| A6 | Parameter read | `readParamValue2017(table, index)` on a known index | raw value bytes | the (table, index) ↔ catalogue-`i` join |
| A7 | Full enumeration | the whole table | complete snapshot | baseline for every later diff |
| A8 | Region parameters | `readParamValue2017` for `ce_country_type` (687) and `ce_regulatory_level` (858) | current values | whether they are readable through this path |

**A8 is the highest-value read-only step in the whole plan.** It converts
"present in a catalogue" into "actually enumerable on hardware".

Capture: a full hex dump of the USB stream for A2–A8, plus the resulting
snapshot JSON.

## 2. Phase B — unlock, state-changing

**Risk: LOW.** Changes FC Assistant state only; no flight behaviour.

| # | Action | Frame | Precondition |
|---|---|---|---|
| B1 | Assistant unlock | `assistantUnlock` — `cmdSet 3`, `cmdId 0xDF`, payload `01 00 00 00`, `ACK_AFTER_EXEC` | props removed |
| B2 | Verify unlock | repeat A6; compare to A6 | — |

**FACT to confirm:** Free Fly applies the unlock **per write**, and
`writeParameter` transmits nothing if the unlock fails. B1/B2 confirms whether the
FC actually honours it, or whether writes proceed regardless.

**Risk note:** unlocking is what makes writes possible at all. It is the gate
the app places in front of every parameter write, and it is the first thing to
characterise.

## 3. Phase C — the region write

**Risk: MEDIUM.** This is the capability the whole comparison turns on.

| # | Action | Frame | Precondition |
|---|---|---|---|
| C1 | Read-before | A8 | unlocked |
| C2 | Write a **non-critical** parameter first | `writeParamValue2017(table, index, value)` on a benign parameter | props removed, battery disconnected |
| C3 | Read-back | A6 on the same index | — |
| C4 | Power cycle | disconnect/reconnect the aircraft | — |
| C5 | Re-read | A6 after reboot | — |

**C2–C5 answer the single largest open question in this project:** does a
`0xE3` parameter write persist?

| C3 result | C5 result | Conclusion |
|---|---|---|
| new value | new value | **persists** — Free Fly can make durable FC-level changes |
| new value | old value | **does not persist** — runtime-only |
| old value | — | **rejected or ignored** — the FC declined |

**DO NOT** attempt the `ce_country_type` write as a first experiment. It is a
regulatory parameter; altering it may affect geofencing and compliance behaviour
on a real aircraft. Establish the mechanism on a benign parameter first, and only
proceed to region parameters with **explicit written operator approval**, on a
non-flyable test airframe.

## 4. What must NOT be attempted

| Action | Why |
|---|---|
| Writing `ce_country_type` / `ce_regulatory_level` without written approval | regulatory parameter; possible geofencing/compliance effect |
| Any `writeParamValue2015` (`0xF9`) | **unreachable in the app and deliberately so**; the guard in `flylib` blocks it |
| The NLD/FreeFCC 21-frame FCC sequence | These commands address the **radio module** through the controller's TCP service. **The current Free Fly implementation does not implement this sequence**, because it has neither the controller-side transport nor the radio/service-mode command path that the sequence uses. Replaying those frames over Free Fly's bulk endpoint is therefore not a supported operation, and this plan does not attempt it |
| Service-mode entry (`0x10`/`0x58`) | Free Fly has no such command in the analysed build; adding one would be new capability work, not verification |
| Any frame built from a decompiled `.pyd` | unverified constants |
| Running this against a flight-ready airframe | — |

## 5. Instruments needed

| Need | Why |
|---|---|
| USB capture between host and device | the FC replies may arrive faster than the app polls; a bulk-transfer trace settles framing questions |
| Props removed / airframe non-armable | every state-changing step |
| Bench supply with current logging | to observe FC reaction to a rejected write |
| A second DJI-supported airframe | `ce_country_type` indices are model-specific and must not be assumed portable |

**FACT — index portability.** Free Fly's catalogue is a flat index space with no
table field, and the join to `(tableNo, paramIndex)` was never traced. **Any
index used on hardware must come from an A5/A6 enumeration on that same
airframe**, never from the catalogue.

## 6. Recording standard

For every step, capture and commit:

- the exact frame bytes transmitted and received (hex, both directions);
- the frame's `cmdSet`/`cmdId`/sender/receiver/sequence;
- the app's interpretation and the raw bytes;
- timestamps and elapsed times;
- the resulting snapshot JSON diff against the A7 baseline.

The `flylib` `ReplayTransport` accepts a hex capture in exactly this format, so a
recorded pass becomes a permanent regression fixture.

## 7. Sequencing

```
A1..A8  read-only, no approval beyond bench safety
   ↓
B1..B2  unlock, LOW risk, props removed
   ↓
C2..C5  benign parameter write, MEDIUM risk, battery disconnected
   ↓
   [ STOP — region parameters require written operator approval ]
```

Do not compress these phases. A is free of risk and resolves the most; C is the
only phase that can leave a change on an aircraft.
