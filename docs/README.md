# Documentation index

Seventeen documents. This page says what each is for and which to read first.

## Read these three first

| # | Document | What it answers |
|---|---|---|
| 1 | [`FINAL_REPORT.md`](FINAL_REPORT.md) | **What is Free Fly?** Verdict, evidence, and the comparative conclusion |
| 2 | [`ARCHITECTURE.md`](ARCHITECTURE.md) | How is it built? Classes, call graph, USB layer, protocol selection |
| 3 | [`COMPARATIVE_REPORT.md`](COMPARATIVE_REPORT.md) | How does it compare? The cross-corpus questions, answered |

---

## The subject

| Document | Contents |
|---|---|
| [`PROVENANCE.md`](PROVENANCE.md) | Sample identity, permissions, signing, obfuscation, network capability. How the analysis was scoped |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Module map, call graph, USB interface/endpoints/handshake, coroutines, protocol selection, live-vs-dead code |
| [`DUML.md`](DUML.md) | The wire format, field by field, with the CRC derivations |
| [`COMMAND_MAP.md`](COMMAND_MAP.md) | Every recovered command: cmdSet, cmdId, sender, receiver, ack, payload, live/dead |
| [`PARAMETERS.md`](PARAMETERS.md) | The 855-entry bundled catalogue, aliases, and the region parameters |
| [`WRITE_PATH.md`](WRITE_PATH.md) | UI → ViewModel → Repository → builder, the unlock gate, and what is dead |

## The comparison

| Document | Contents |
|---|---|
| [`COMPARATIVE_REPORT.md`](COMPARATIVE_REPORT.md) | The fifteen cross-corpus questions |
| [`COMMAND_CORPUS.md`](COMMAND_CORPUS.md) | Normalised command sequences and the FCC profile lineage |
| [`WIRE_COMPARISON.md`](WIRE_COMPARISON.md) | Drone-Hacks vs Free Fly, command id by command id |
| [`APP_LINEAGE.md`](APP_LINEAGE.md) | Protocol lineage vs direct code lineage, scored separately |
| [`PUBLIC_REPO_INVENTORY.md`](PUBLIC_REPO_INVENTORY.md) | The pinned public corpus, with licences and transports |
| [`ECOSYSTEM_MAP.md`](ECOSYSTEM_MAP.md) | Every product classified across twelve capability categories |
| [`TRANSPORT_MATRIX.md`](TRANSPORT_MATRIX.md) | How each project actually reaches the aircraft |
| [`BACKENDS.md`](BACKENDS.md) | Network backends, and what was deliberately not contacted |

## Doing this yourself

| Document | Contents |
|---|---|
| [`REPRODUCING.md`](REPRODUCING.md) | How to re-derive the analysis yourself, and the expected sample hash |
| [`HARDWARE_TEST_PLAN.md`](HARDWARE_TEST_PLAN.md) | Phased plan, risk levels, and what must not be attempted |
| [`LICENSING.md`](LICENSING.md) | Provenance audit and why no licence was chosen |
| [`STATUS.md`](STATUS.md) | Running status and the full sample register |

## Per-sample reports

`research/reports/` holds the long-form work:

| Report | Sample |
|---|---|
| `nldfcc_baseline.md` | NLD FCC — identity, transport, the shipped command profiles |
| `nld_native_transport.md` | NLD FCC — the DUSS/RCLink stack, PKDS block, WireGuard |
| `dronehacks_baseline.md` | Drone-Hacks 1.48 — architecture and DUML layer |
| `dronehacks_fingerprint_hunt.md` | Drone-Hacks 1.48 — constant hunt, licence subsystem, cache and export |
| `djifcc_differential.md` | DJIFCC vs stock DJI Fly — the matching differential |
| `djifcc_patch_localisation.md` | DJIFCC — what the patch actually is |
| `redfly.md` | RedFly — catalogue and classification, no artifact acquired |

---

## Conventions used throughout

**Evidence labels.** Every claim is **FACT** (read from a named artefact),
**INFERENCE** (concluded, with reasoning) or **HYPOTHESIS** (a guess, with what
would settle it).

**Corrections are made in place.** Where an earlier claim was wrong, the
correction appears where the original claim is, not only in a later document.

**No proprietary binaries.** Analysis outputs are described, not redistributed.
Bulk enumerations of a proprietary APK's internals are summarised rather than
committed; the tools regenerate them locally.
