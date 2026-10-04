# Final report — what Free Fly actually is

Stage 7. Answers the mission's questions from evidence, with every claim tagged
**FACT** (read directly out of a file), **INFERENCE** (concluded, with the
reasoning) or **HYPOTHESIS** (guess, with what would settle it).

Supporting documents: `PROVENANCE.md`, `ARCHITECTURE.md`, `DUML.md`,
`COMMAND_MAP.md`, `PARAMETERS.md`, and
`research/reports/djifcc_differential.md`.

---

## The short version

Free Fly 1.0 is a **standalone, offline, read-mostly FC parameter editor** that
opens a raw USB bulk endpoint to a DJI device, speaks DJI's DUML framing, and
addresses the flight controller's 2017-style parameter table by
`(table, index)`. It contains **no** FCC command sequence, **no** RCLink
envelope, **no** radio-region command, and **no** native code of its own.

It is *not* a patched DJI Fly, and it is *not* an FCC tool. But it is not
innocuous either: its bundled catalogue names `ce_country_type` and
`ce_regulatory_level`, and its parameter write path is live — so it can address
the same firmware state the FCC tools target, by an entirely different route.

That is the whole answer to "what is it": **mechanism-disjoint from the FCC
tooling, overlapping in effect.**

---

## 1. Is Free Fly a modified DJI Fly?

**No.**

**FACT.** Package `com.dronehacks.app`, `versionName` 1.0, `app_name` "Free Fly",
one asset (`assets/params_catalog.json`), 10 DEX files, 258 `com.dronehacks`
classes of which ~15 are hand-written. No DJI package, no DJI class namespace,
no DJI resource identifiers.

**FACT.** Compare the DJIFCC builds acquired for this project: they keep DJI's
own packages — `dji.go.v5` (Fly phone), `dji.go.v6` (Fly RC2), `dji.go.v4`
(GO 4) — and are re-signed with one vendor certificate `CN=DJIFCC.APP`
(`cad73496…`). That is what "modified DJI Fly" looks like. Free Fly is nothing
like it.

**INFERENCE.** The only "Drone-Hacks" traces in Free Fly are its own identifiers:
package `com.dronehacks.app`, application class `DroneHacksApp`, theme
`Theme.DroneHacks`, alongside the user-facing label "Free Fly".

**INFERENCE.** The most probable reading is a Drone-Hacks-family Android client
rebranded for distribution — but this remains a **HYPOTHESIS** about
authorship. Package naming is LOW-tier evidence on the scale this project uses
(identical uncommon code or constant tables would be HIGH; shared branding is
not). See §6 for what would settle it.

## 2. Is it a fixed-command FCC tool?

**No — and this is the finding that required the most work to establish.**

**FACT.** Free Fly has no FCC mechanism in the sense the comparative corpus
means. Among its fourteen named `DroneCommands` builders and the
`DumlConstants` set there is no radio-region, FCC-profile, service-mode or C0
command. No `com.dji.logiclink` / `com.dji.protocol` class, no RCLink envelope,
no local socket, no loopback TCP.

**FACT — and a correction.** I initially reported a live 2017→2015 protocol
fallback, inferred from the log string `"Table N empty or no response, falling
back to 2015"`. That was wrong. Verified across the whole decoded tree: the
only `invoke-direct` to `readAll2015` is inside its own synthetic accessor, and
`access$readAll2015` has exactly one reference in the entire APK — its own
coroutine continuation. **`readAll2015` is unreachable dead code**, and the
message is a leftover. Free Fly is 2017-only; `getParamInfo2015` and
`writeParamValue2015` have **zero** call sites.

**Scope limit, stated honestly.** That is an absence *within the search
performed*. A command sequence assembled inline from generic cmdSet/cmdId values
with no named constant would not have been caught. None was found, but the
claim is bounded by what was searched.

## 3. Is it principally a generic FC parameter editor?

**Yes.**

**FACT.** The live command set, by call-site count across the decoded tree:

| Command | cmdSet | cmdId | Callers |
|---|---|---|---|
| `readParamValue2017` | FC | `0xE2` | 3 |
| `getTableAttribs2017` | FC | `0xE0` | 1 |
| `getParamInfo2017` | FC | `0xE1` | 1 |
| `writeParamValue2017` | FC | `0xE3` | 1 |
| `assistantUnlock` | FC | `0xDF` | 2 |
| `versionInquiry`, `versionInquiryTo` | COMMON | `0x01` | 1 each |
| `getCfgFileChunk` | COMMON | `0x4F` | 1 |
| `replyRegAck`, `replyRegDev` | COMMON | `0x82`, `0x81` | 1 each |

Ten of the fourteen live builders are FC Assistant parameter operations. The
remaining four are device discovery, firmware retrieval and the registration
handshake that discovery depends on.

**FACT.** The transport is raw USB bulk, not a serial abstraction: no CDC-ACM
line-coding, no baud rate, no `setInterface` anywhere. The app claims the first
interface exposing a bulk IN and OUT endpoint, then writes the byte `0x30` five
times to wake the link (200 ms), reads 512 bytes with a 2000 ms timeout, and
writes with a 2000 ms timeout.

## 4. What overlaps Drone-Hacks' free parameter editor?

**FACT.** Substantially, at the level of protocol: the same DUML framing, the
same device addressing (`DEV_PC:1` → `DEV_FC:0`), the same FC Assistant command
set, the same name-hash algorithm `((h << 8) + b) % (2^32 − 5)` — though Free
Fly only reaches that hash from dead code — and the same 2017
`(table, index)` addressing that DJI's newer firmware uses.

**INFERENCE.** Functionally, a Free Fly user can enumerate the same flight
controller parameter table a Drone-Hacks parameter editor would, and write to
individual parameters. That is the overlap, and it is substantial.

**FACT.** Drone-Hacks 1.48 is a **different program entirely**: a PyInstaller
onefile bundling CPython 3.11 (`MEI\x0c\x0b\x0a\x0b\x0e` overlay magic at
`0x18bba6e`, `python311` tag; the string `Cython` occurs zero times, refuting
the earlier claim). Its protocol layer has not been recovered — that work was
lost when the worker was killed.

**INFERENCE.** The two are therefore **not demonstrably related in code**. The
shared protocol is DJI's, not theirs. Whether their implementations share code
is unresolved and I am not claiming it.

## 5. Which Drone-Hacks features require mechanisms absent here?

**FACT.** Absent from Free Fly: RCLink framing, service-mode entry, radio-region
commands, FCC profiles, firmware patching or flashing, NFZ/GEO modification,
DroneID logic, 4G modification.

**INFERENCE.** Anything requiring a change to the *radio module* rather than the
flight controller is out of reach for Free Fly as built: it opens a USB endpoint
to a DJI device and speaks to the FC. A region change effected through
`ce_country_type` is an FC-parameter change; a region change effected through an
FCC command sequence is not, and Free Fly contains no such sequence.

## 6. Is there any exact public source-code match?

**No exact match found.**

**FACT.** No distinctive code from Free Fly was located in `doesthings/FreeFCC`,
`FreeFCC-USB`, `M4TH1EU/DJI-FCC-HACK`, `andreapianidev/DJI-FCC-Unlock-iOS` or
`o-gs/dji-firmware-tools`. The five repos are cloned locally and pinned.

**FACT — a point of agreement, not of lineage.** The comparative worker reached
the same CRC-16 characterisation (X-25, init `0x3692`, xorout 0, little-endian
header) working from the public `o-gs` corpus that this project reached
independently from the APK's own tables. `cmdSet 3 / cmdId 0xF9` was likewise
independently identified there as "Write Param By Hash", matching Free Fly's
`CMD_FC_PARAM_WRITE_2015 = -7`.

**INFERENCE.** These are **convergences on DJI's own published and
reverse-engineered protocol**, which is exactly what the LOW tier of the
provenance scale is for. They are not evidence of shared code.

**HYPOTHESIS.** Free Fly's DUML layer may well be an independent implementation
of the same documented format. What would settle it: identical bugs or
identical unusual constant choices between Free Fly and any public project.
Not found.

## 7. Why can this APK apparently work without a licence or server?

**Because there is nothing to check a licence against — and nothing to
authorise one.**

**FACT.** No `android.permission.INTERNET`. No HTTP client library of any kind
in any of the ten DEX files (okhttp, retrofit, gson, Apache HttpClient, Picasso,
Glide, Firebase: **zero** classes each). No vendor URL, domain or IP — the eight
URLs in the APK are AndroidX and Compose build metadata.

**FACT, scoped.** The conclusion is *no direct Android Internet capability and
no embedded remote backend*. Binder, intent/broadcast IPC, and a cooperating
app's local provider or `LocalSocket` are **not** excluded. USB is a live egress
path, but it terminates in a DJI controller, not a server.

**FACT.** Signed with the standard AOSP **Android debug** keystore,
`debuggable="true"`, no obfuscation, no anti-analysis. This is an unreleased
developer build.

**INFERENCE.** "Free Fly works without a licence" is not a capability claim. It
is a property of a debug build with no network stack.

## 8. Does its DUML implementation derive from publicly documented DJI concepts?

**Yes, and specifically.**

**FACT.** The recovered format — 11-byte header, magic `0x55`, `(version << 10)
| length` in a little-endian uint16, device byte `(index << 5) | type`, reflected
CRC-8 poly `0x8C` init `0x77` over the first three bytes, CRC-16 poly `0x1021`
reflected with init `0x3692` and no final XOR — matches the DJI DUML conventions
described in the public research corpus.

**FACT.** The CRCs were not assumed. The APK embeds two 256-entry tables in
`DumlBuilder.<clinit>`; both were extracted and matched by brute force against
every reflected table for all 256 and all 65,536 polynomials respectively, giving
unique matches `0x8C` and `0x8408`. The generated tables are then compared
element-by-element against the extracted ones in the test suite.

**INFERENCE.** Free Fly implements the *publicly understood* DJI format. Note
one thing that is often mis-stated: its CRC-16 update is the **standard**
reflected CRC step with DJI-specific **parameters**. It is not a custom
algorithm, and an implementer comparing against another DJI tool should code the
same function.

---

## Where this leaves the ecosystem question

**INFERENCE.** Three distinct mechanisms are visible across the corpus, and they
are not variations on one theme:

| Mechanism | Representative | How the change is made |
|---|---|---|
| **Patched official app** | DJIFCC | Ships DJI's own package, re-signed, with modified app logic. Cannot upgrade stock — must side-load. |
| **Standalone DUML parameter tool** | Free Fly | Separate app, USB bulk, FC Assistant parameter read/write. No app patching. |
| **Local-socket / app-injection** | FreeFCC-style, `djiparam` (ports 40007/40008/40009) | Talks to a local DJI service on the controller or phone. |

**INFERENCE.** Persistence differs in all three and none of them is free:
a patched app survives until a real DJI update replaces it; a parameter write
survives only if the FC accepts and stores it; a socket tool survives only while
the service it depends on is running. Conflating these is the main analytical
error available here, and this project has tried not to commit it.

## Known limits of this report

1. The DJIFCC patch has **not** been located in DEX or native code, and there
   is no matching-version stock/patched pair (stock 1.21.8 vs patched
   1.21.10.43 / 1.21.12.19), so a naive diff would be confounded by version
   drift.
2. NLD FCC and Drone-Hacks 1.48 have had **no protocol analysis** — both
   workers died first.
3. `ce_country_type` being *present* in the catalogue proves it is
   **enumerable**. It does not prove Free Fly's UI exposes it, nor that a write
   succeeds. That needs hardware: see `docs/HARDWARE_TEST_PLAN.md`.
4. Whether the catalogue's flat index space maps 1:1 to
   `(tableNo, paramIndex)` is **unresolved**; the join has not been traced.
5. The `force` flag's interaction with the empty-result test in
   `readAllParameters` is unresolved, and `flylib` deliberately encodes no guess.