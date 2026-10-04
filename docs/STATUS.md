# Free Fly reverse-engineering — project status

Live status board for the project. Updated at every stage boundary.

**Sample:** `samples/FF_v_1_00.apk` — SHA-256 `a6dc898ddcec0e9e13ab9c270835faea8a6d7961e7012e534361cdec0b9894ee`
(**matches the operator baseline exactly**; size 10,719,960 bytes).

Legend: ✅ done · 🔄 in progress · ⬜ not started · ⚠️ blocked

---

## Stage status

| Stage | Subject | Status | Output |
|---|---|---|---|
| 1 | Baseline and provenance | ✅ done | `docs/PROVENANCE.md` |
| 2 | Architecture reconstruction | ✅ done | `docs/ARCHITECTURE.md` |
| 3 | DUML binary format | ✅ done | `flylib/crc.py`, `flylib/packet.py` + golden-vector tests |
| 4 | DroneCommands transaction map | ✅ done | `research/generated/freefly_commands.json` (14 builders) |
| 5 | DroneRepository | 🔄 partial | USB layer + selection structure pinned; `force` semantics open |
| 6 | Parameter catalogue | ⬜ | |
| 7 | Free Fly vs Drone-Hacks / FreeFCC | ⬜ | |
| 8 | Clean read-only implementation | 🔄 partial | codec, framer, commands, guard, 4 transports, 111 tests |
| W | Write/mutation path (guarded) | ✅ done | `flylib/guard.py`; disabled by default, dry-run default |
| H | Hardware test plan | ⬜ | |

## Comparative corpus status

All four comparative workers ran ~52 minutes and were then killed by an
infrastructure failure (`getaddrinfo ENOTFOUND openrouter.ai`) before writing
their report files. Their findings survive in transcripts, not on disk. They
are **not** counted as delivered; the primary Free Fly path was not blocked on
them.

| Workstream | Subject | Status | Note |
|---|---|---|---|
| C1 | NLD FCC APK baseline | ⚠️ partial | report never written; no files deposited |
| C2 | Drone-Hacks 1.48 EXE baseline | ⚠️ partial | identified as a PyInstaller/Cython Python 3.11 onefile; report never written. `tools/pe_baseline.py` was committed |
| C3 | Public open-source corpus | ⚠️ partial | five repos cloned and pinned; report never written. Findings corroborate the DUML work (see below) |
| C4 | redfly.app / djifcc.app | ⚠️ partial | artifacts downloaded; report never written |
| C5 | Normalized command database | ⬜ | |
| C6 | Transport matrix | ⬜ | |
| C7 | App/build lineage | ⬜ | |
| C8 | Network/backend map | ⬜ | |
| C9 | Ecosystem classification | ⬜ | |
| C10 | Comparative report | ⬜ | |

### Salvaged from the killed C3 worker — unverified by this project

These came from the worker's transcript, which died before writing a report.
They are recorded because several **independently corroborate** conclusions
reached independently from Free Fly's own bytecode. They are **not** treated as
verified evidence and must be re-derived before being published in any report.

- DJI CRC-16 characterised as **X-25 with init `0x3692`, xorout `0x0000`**, and
  the header as little-endian — matching `flylib/crc.py` and `flylib/packet.py`,
  which were derived from the APK's tables before this worker reported anything.
- `cmdSet 3 / cmdId 0xF9` identified as "Write Param By Hash", i.e. the 2015
  hashed write. Consistent with Free Fly's `CMD_FC_PARAM_WRITE_2015 = -7`
  (`0xF9`) on cmdSet `CMD_SET_FC`.
- The 2017 parameter protocol is **index-addressed, not name-hashed** — exactly
  what Free Fly's `readParamValue2017(tableNo, paramIndex)` does.
- A 21-frame FCC sequence reconstructed from a FreeFCC profile.
- `DJI-FCC-Unlock-iOS` is licensed **PolyForm Noncommercial 1.0.0**, i.e. source
  available but *not* OSI open source. Worth recording before quoting it.
- A repo impersonating `doesthings/FreeFCC` by name carries a 489 KB `.zip`
  inside `src/main/java/`. It was correctly **not** retrieved. Treat any
  "FreeFCC" fork of unknown provenance as suspect.
- Local port convention: FreeFCC uses `40009`; the `djiparam` project uses
  `40008` (inject) / `40007` (read).

## Sample register

Required table: `SAMPLE | SHA256 | ANALYZED | TRANSPORT | DUML | PARAMS | FCC | BACKEND | NOTES`

| SAMPLE | SHA256 (first 16) | ANALYZED | TRANSPORT | DUML | PARAMS | FCC | BACKEND | NOTES |
|---|---|---|---|---|---|---|---|---|
| `FF_v_1_00.apk` (Free Fly 1.0) | `a6dc898ddcec0e9e` | ✅ Stages 1–4 | **USB host bulk** (raw bulk, no CDC-ACM), VID `0x2CA3`, PID `0x10/0x18/0x20` | ✅ recovered, tested | 🔄 selection structure pinned | ❌ **none found** | **none** — no INTERNET perm, no HTTP lib, no endpoints | Debug-signed, debuggable, unobfuscated, 10 DEX, no native app code; FC Assistant parameter protocol only — no RCLink, no FCC/profile, no service-mode |
| `nldfcc.apk` (NLD FCC) | `4a6e07a2ee1fbd7f` | ⚠️ partial | 🔄 | 🔄 | ⬜ | 🔄 | 🔄 | 7,269,392 bytes, 2 DEX; worker killed before report |
| `dh_v1.48_signed.exe` (Drone-Hacks 1.48) | `236dd98439e503c6` | ⚠️ partial | 🔄 | 🔄 | 🔄 | 🔄 | 🔄 | 25,944,848 bytes, PE32+ x86-64, 7 sections; PyInstaller/Cython Python 3.11 onefile |

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