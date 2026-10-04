# Free Fly reverse-engineering — project status

Live status board for the project. Updated at every stage boundary.

**Sample:** `samples/FF_v_1_00.apk` — SHA-256 `a6dc898ddcec0e9e13ab9c270835faea8a6d7961e7012e534361cdec0b9894ee`
(**matches the operator baseline exactly**; size 10,719,960 bytes).

Legend: ✅ done · 🔄 in progress · ⬜ not started · ⚠️ blocked

---

## Stage status

| Stage | Subject | Status | Output |
|---|---|---|---|
| 1 | Baseline and provenance | ✅ | `docs/PROVENANCE.md` |
| 2 | Architecture reconstruction | 🔄 | `docs/ARCHITECTURE.md` |
| 3 | DUML binary format | ⬜ | `docs/DUML.md` + golden-vector tests |
| 4 | DroneCommands transaction map | ⬜ | `docs/COMMAND_MAP.md` |
| 5 | DroneRepository | ⬜ | code + hardware-free unit tests |
| 6 | Parameter catalogue | ⬜ | `docs/PARAMETERS.md` |
| 7 | Free Fly vs Drone-Hacks / FreeFCC | ⬜ | `docs/FINAL_REPORT.md` |
| 8 | Clean read-only implementation | ⬜ | `research/` package + tests |
| W | Write/mutation path (guarded) | ⬜ | dry-run + disabled-by-default guard |
| H | Hardware test plan | ⬜ | `docs/HARDWARE_TEST_PLAN.md` |

## Comparative corpus status

| Workstream | Subject | Status | Output |
|---|---|---|---|
| C1 | NLD FCC APK baseline | 🔄 | `research/reports/nldfcc_baseline.md` |
| C2 | Drone-Hacks 1.48 EXE baseline | 🔄 | `research/reports/dronehacks_baseline.md` |
| C3 | Public open-source corpus (pinned) | 🔄 | `research/reports/public_corpus.md` |
| C4 | redfly.app / djifcc.app web research | 🔄 | `research/reports/web_sources.md` |
| C5 | Normalized command database | ⬜ | `docs/COMMAND_CORPUS.md` + `research/generated/command_corpus.json` |
| C6 | Transport matrix | ⬜ | `docs/TRANSPORT_MATRIX.md` |
| C7 | App/build lineage | ⬜ | `docs/APP_LINEAGE.md` |
| C8 | Network/backend map | ⬜ | `docs/BACKENDS.md` |
| C9 | Ecosystem classification | ⬜ | `docs/ECOSYSTEM_MAP.md` |
| C10 | Comparative report | ⬜ | `docs/COMPARATIVE_REPORT.md` |

## Sample register

Required table: `SAMPLE | SHA256 | ANALYZED | TRANSPORT | DUML | PARAMS | FCC | BACKEND | NOTES`

| SAMPLE | SHA256 (first 16) | ANALYZED | TRANSPORT | DUML | PARAMS | FCC | BACKEND | NOTES |
|---|---|---|---|---|---|---|---|---|
| `FF_v_1_00.apk` (Free Fly 1.0) | `a6dc898ddcec0e9e` | ✅ Stage 1 | USB host serial, VID `0x2CA3` | 🔄 | 🔄 (`assets/params_catalog.json`) | ⬜ | **none** — no INTERNET perm, no HTTP lib, no endpoints | Debug-signed, debuggable, unobfuscated, 10 DEX, no native app code |
| `nldfcc.apk` (NLD FCC) | `4a6e07a2ee1fbd7f` | 🔄 C1 | 🔄 | 🔄 | ⬜ | 🔄 | 🔄 | 7,269,392 bytes, 2 DEX |
| `dh_v1.48_signed.exe` (Drone-Hacks 1.48) | `236dd98439e503c6` | 🔄 C2 | 🔄 | 🔄 | 🔄 | 🔄 | 🔄 | 25,944,848 bytes, PE32+ x86-64, 7 sections |

Full identity records (sizes, SHA-1/MD5, sources, acquisition dates, metadata
confidence) live in the gitignored `research/corpus/registry.json`, produced by
`tools/corpus_registry.py`.

---

## Stage 1 headline findings

**FACT**

- SHA-256 matches the operator baseline exactly; analysis proceeded.
- Package `com.dronehacks.app`, versionName `1.0`, versionCode `1`,
  minSdk 26 / targetSdk 35, Compose 1.7.3 + Material3 1.3.0, coroutines 1.9.0,
  Hilt 2.52, Kotlin metadata 2.0.
- **No `android.permission.INTERNET`.** No HTTP client library anywhere in the
  DEX (okhttp/retrofit/gson/apache-http/picasso/glide/firebase: all zero
  classes). No vendor URL, domain or IP. **The app is incapable of network I/O.**
- `android:debuggable="true"`; APK Signature Scheme **v2 only**; certificate is
  the standard AOSP **Android debug** keystore (`CN=Android Debug`, self-signed,
  valid 2026-05-31 → 2056-05-23).
- App code is **completely unobfuscated** — 258 readable `com.dronehacks` classes.
- **No native app code** — the only `.so` is `libandroidx.graphics.path.so`.
- Exactly one asset: `assets/params_catalog.json` (42,041 bytes).
- USB host mode, vendor `0x2CA3` (DJI), product IDs `0x10`, `0x18`, `0x20`.
- No dynamic loading, no anti-debug, no anti-VM, no integrity checks, no packer.

**INFERENCE**

- There is no licensing, update, telemetry or authentication mechanism to
  analyse, because none can exist in this build.
- Transport is USB-host serial to a DJI controller/FC, not Android Open Accessory.
- "Free Fly" is very likely a Drone-Hacks-family Android client rebranded; the
  package, application class and theme all say Drone-Hacks while the label says
  Free Fly. No copied-code claim is made until Stages 4/7 produce byte-level
  evidence.

---

## Carried open questions

1. Which DJI devices do product IDs `0x10`, `0x18`, `0x20` correspond to, and
   what is the actual USB interface/endpoint layout? → Stage 5
2. Exact DUML framing and every CRC detail as implemented. → Stage 3
3. Whether the 2015 or 2017 parameter protocol is used, and how the choice is
   made. → Stage 5
4. Where the aircraft serial, model codename and firmware version are extracted
   from the AC response. → Stage 5
5. Whether the app contains **any** FCC / radio-region / RCLink / service-mode
   mechanism, or is purely FC Assistant parameter protocol. → Stages 4/7, and
   this is the central question of the comparative report.
6. Provenance of `assets/params_catalog.json`. → Stage 6
7. Relationship between Free Fly's DUML implementation and Drone-Hacks 1.48,
   NLD FCC and the public open-source corpus. → Stages 7 + C1–C3

## Engineering rules in force

- The original APK is never modified. All tools open it read-only.
- The APK and all bulk decompiler output stay out of git (`work/`, `samples/`,
  `research/corpus/` are gitignored); nothing binary is ever committed.
- Protocol constants are verified against **smali/DEX**, not accepted from
  decompiled Java alone.
- Every claim is tagged FACT / INFERENCE / HYPOTHESIS.
- Clean-room code defaults to read-only; any state-changing path is behind an
  explicit guard that is disabled by default and supports dry-run.
- No unknown command is ever sent to an aircraft.