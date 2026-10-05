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
| C1 | NLD FCC APK baseline | ✅ **done** | Bounded fingerprinting pass. `research/reports/nldfcc_baseline.md` — identity, signing (incl. an unknown `PKDS` block), TCP transport, and the app's own annotated 21-frame FCC sequence |
| C2 | Drone-Hacks 1.48 EXE baseline | ✅ **done** | PyInstaller onefile / CPython 3.11 / **Cython-compiled** (corrected — see report). Tkinter desktop + pyserial. `research/reports/dronehacks_baseline.md`. `tools/pyi_extract.py` added |
| C3 | Public open-source corpus | ✅ pinned, ✅ **used as control** | 6 repos pinned. Served as the control group for the lineage assessment: `djiparam/Duml.java` contains crc8 init 0x77, crc16 init 0x3692 and the literal `unknown1`, which demotes every 'sharpest' marker to public protocol knowledge. `docs/APP_LINEAGE.md` |
| C4 | redfly.app / djifcc.app | ✅ **recovered** | 18 APKs acquired and registered, including **stock DJI Fly** baselines. Differential written up in `research/reports/djifcc_differential.md`. redfly.app still outstanding |
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
| `FF_v_1_00.apk` (Free Fly 1.0) | `a6dc898ddcec0e9e` | ✅ Stages 1–4, 6 | **USB host bulk** (raw bulk, no CDC-ACM), VID `0x2CA3`, PID `0x10/0x18/0x20` | ✅ recovered, tested | ✅ 2017-only; `readAll2015` is dead code | ⚠️ **no FCC command sequence**, but **region params present and writable via the FC parameter path** (`ce_country_type` idx 687, `ce_regulatory_level` idx 858) | **none** — no INTERNET perm, no HTTP lib, no endpoints | Debug-signed, debuggable, unobfuscated, 10 DEX, no native app code. No RCLink/FCC-profile/service-mode constructs among the 14 named builders or `DumlConstants`; `writeParamValue2017` is the only live parameter write — full UI→builder trace and unlock gate in `docs/WRITE_PATH.md` |
| `nldfcc.apk` (NLD FCC 2.0.0.6) | `4a6e07a2ee1fbd7f` | ✅ fingerprint + profiles | **TCP 40007/40009** to controller, "outer wrapper", native impl | yes — ships its own **21-frame FCC sequence** as JSON profiles | ❌ `ce_country_type` absent; uses hashed FC writes `cmdSet 3 / cmdId 0xF9` | ✅ **enters AUTOTEST service mode**, sets radio region, WiFi channel map, OFDM power, country code, commits | ✅ `INTERNET` + bundled **WireGuard** (`libwg*.so`) | `com.nolimitdronez.nldfcc`; cert `CN=KK, O=NO LIMIT TECHNOLOGY LTD` `72e71df3…`; 2 s keepalive re-applies FCC |
| `dh_v1.48_signed.exe` (Drone-Hacks 1.48) | `236dd98439e503c6` | ✅ architecture + protocol layer | **USB serial (pyserial)**, Tkinter desktop, Windows | ✅ full DUML layer recovered from shipped `.pyc` (`core/duml.py`) | ✅ **both 2015 and 2017 live**; `DroneParameters` with export/import/defaults | 🔄 not located in the recovered layer | 🔄 `view/cert_view.py`, `view/dji_login.py` indicate licensing | 25,944,848 B, PyInstaller onefile, 1167 TOC entries, **Cython-compiled** — my earlier "not Cython" was wrong; `build\lib.win-amd64-cpython-311\*.pyd` is Cython's output tree. Encryption, hardware-register and gimbal-calib payloads absent from Free Fly |
| DJIFCC Fly Android `1.21.12.19` | `d65c3608cd09ca77` | ✅ baseline | DJI's own app transport, reached via **native JNI** | **inherits DJI's** `libsdk_jni.so` (81.7→88.3 MB, sole carrier of `DUML`/`LogicLink` symbols) | 🔄 | ✅ **patches the DJI app itself** | ✅ INTERNET, 57 perms | package `dji.go.v5` — DJI's own, so signature mismatch forces uninstall-then-sideload. **No `com.dji.logiclink`/`com.dji.protocol` classes** — that layer is native in modern DJI Fly |
| DJIFCC Fly RC2 V6 `1.21.10.43` | `e322fceead4b2543` | ✅ baseline | DJI's own app transport | **inherits DJI's** native stack | 🔄 | ✅ patches the DJI app | ✅ INTERNET, 57 perms | package `dji.go.v6` — **no stock v6 in the corpus**, so no matched differential operand |
| DJIFCC GO 4 `4.3.62` | `1d9fe6377f6f7224` | ✅ baseline | DJI's own GO 4 transport | **inherits DJI's** native stack | 🔄 | ✅ patches the DJI app | ✅ INTERNET, 41 perms | package `dji.go.v4` — a different app family from Fly |
| Stock DJI Fly RC2 `1.21.8` | `cfbf67368fa812c6` | ✅ baseline | — | `libsdk_jni.so`, DUML=7 LogicLink=2 | — | — | ✅ INTERNET, 57 perms | `dji.go.v5`, `CN=dji`, v2-only, 22 DEX / 112 `.so` (armeabi-v7a only). **The package-matched differential operand** |
| `FCCInstaller` `1.2.1` | `cc9dbe9afb407dc4` | ✅ baseline | — | n/a | — | sideload helper | ✅ INTERNET, 7 perms | `com.djifcc.flyinstaller` — load-bearing *because* DJI package names + re-signing force uninstall-then-sideload |
| `com.djifcc.appstore` `1.8.3` | `797458783689f280` | ✅ baseline | — | n/a | — | distribution channel | ✅ INTERNET, 12 perms | the patch *distribution* path does have network access — unlike Free Fly, which structurally cannot |

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