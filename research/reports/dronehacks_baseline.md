# Drone-Hacks 1.48 — architecture and protocol layer

Recovered from `dh_v1.48_signed.exe`
(sha256 `236dd98439e503c6748abe28ba5c954a3ec712663fb8280b8e48344c158ee568`,
25,944,848 bytes) using PyInstaller's own `CArchiveReader`
(`PyInstaller.archive.readers`). **No decompilation of the Cython extensions was
performed** —
the conclusions below come from the original CPython `.pyc` bytecode that the
bundle ships alongside them, plus the archive's own metadata.

---

## 0. Correction: it *is* Cython-compiled

*(Method note: a hand-rolled TOC parser was written and abandoned. It read the
trailer cookie correctly - `python311.dll`, version tag 311 - but assumed the
packed `!iIIIBc` TOC entry format, which is wrong for this PyInstaller build, and
was deleted rather than shipped. PyInstaller's tested reader was used instead.)*

Earlier in this project I recorded "**Not** Cython-compiled", on the grounds
that the string `Cython` occurs zero times in the executable. That inference was
wrong, and I should not have drawn it from a string search.

**FACT.** The archive contains, for every application module, both a compiled
extension and its build output under a literal Cython build tree:

```
controller\api_controller.cp311-win_amd64.pyd
controller\build\lib.win-amd64-cpython-311\api_controller.cp311-win_amd64.pyd
core\build\lib.win-amd64-cpython-311\duml.cp311-win-amd64.pyd
```

`build\lib.win-amd64-cpython-311\` is Cython's output directory, and
`.cp311-win_amd64.pyd` is an extension-module suffix. The absence of the literal
string "Cython" in the binary is not evidence of its absence — the word simply is
not embedded.

**INFERENCE.** The app was Cython-compiled and frozen with PyInstaller; the
`__pycache__/*.pyc` files present next to each `.pyd` are the intermediate
CPython bytecode from that build, which is why the original logic is readable
without touching the extensions.

**Still true and separately established:** `MEI\x0c\x0b\x0a\x0b\x0e` overlay
magic at offset `0x18bba6e`, `python311.dll`, version tag `311`.

## 1. Archive shape

**FACT.** PyInstaller onefile, `python311.dll`, **1167** TOC entries.

| Group | Entries | What it is |
|---|---|---|
| `tcl`, `tk`, `tcl8` | 922 | **Tkinter** GUI toolkit |
| `serial` | 35 | **pyserial** — USB serial transport |
| `Crypto`, `Cryptodome` | 83 | PyCryptodome |
| `controller` | 21 | app controllers |
| `core` | 15 | **protocol and parameter core** |
| `lxml` | 16 | XML — CFG parsing |
| `view` | 12 | GUI |
| `assets` | 10 | JSON data, icons, i18n |
| `pyadb` | 4 | ADB |
| `PIL` | 4 | images |

**INFERENCE.** A **Tkinter desktop application** speaking **USB serial** through
pyserial — not a mobile app, and not a controller-socket app. That places it in
the same transport family as Free Fly and a different family from NLD FCC.

## 2. Module layout

```
core/duml.py                  DUML framing, header, payloads, CRC, framer
core/duml_communication.py    send/receive, request matching, param operations
core/dji.py                   DJI device layer
core/drone_parameters.py      parameter model, export/import, defaults
core/core.py
controller/{main,api,drone,settings,tools,view,compatibility}_controller.py
view/{view,wizard,cert_view,dji_login}.py
assets/advanced.json          human-verification quiz payload (NOT a parameter DB)
assets/lang/{de_DE,en_US}.json
```

**INFERENCE.** `cert_view` and `dji_login` indicate **licence/login
functionality**, which Free Fly has none of. `compatibility_controller`
suggests model/region compatibility handling.

**CORRECTED.** `advanced.json` was first described here as bundled
parameter/config data. It is not: it is a quiz payload used as a
proof-of-human check. See `dronehacks_fingerprint_hunt.md`, which also finds
**no** DJI parameter names anywhere in the bytecode — Drone-Hacks discovers the
parameter table from the aircraft and bundles no catalogue.

## 3. The DUML implementation — and the convergence with Free Fly

**FACT.** `core/duml.py` defines enums `ACK_TYPE`, `DEV_TYPE`, `ENCRYPT_TYPE`,
`PACKET_TYPE`, `CMD_SET_TYPE`; a `DUMLHeader` with `whole_length`, `version`,
`sender_type`, `sender_index`, `receiver_type`, `receiver_index`, `packet_type`,
`ack_type`, `encrypt_type`; and `calc_hdr_checksum` / `calc_pkt_checksum`.

That header field set is **exactly Free Fly's**, field for field.

### 3.1 Payload classes

**FACT.** Both projects define a payload class per transaction, and the two sets
correspond command for command:

| Drone-Hacks 1.48 | Free Fly 1.0 |
|---|---|
| `FlyController_AssistantUnlockRq/Re` | `assistantUnlock` |
| `FlyController_GetParamInfoByIndex2015Rq` | `getParamInfoByIndex2015` |
| `FlyController_GetParamInfoByHash2015Rq` | `getParamInfo2015` |
| `FlyController_ReadParamValByHash2015Rq/Re` | `readParamValue2015` |
| `FlyController_ReadParamValByIndex2017Rq/Re` | `readParamValue2017` |
| `FlyController_WriteParamVal{1,2,4,8,16,Any}ByHash2015Rq` | `writeParamValue2015` |
| `FlyController_WriteParamVal{1,2,4,8,16,Any}ByIndex2017Rq` | `writeParamValue2017` |
| `FlyController_GetTblAttribute2017Rq/Re/EOL2017Re` | `getTableAttribs2017` |
| `reply_reg_ack` / `reply_reg_dev` | `replyRegAck` / `replyRegDev` |
| `flyc_parameter_compute_hash(po, parname)` | `paramHash(name)` |
| `flyc_parameter_is_signed` / `is_float` | `ParamType` signedness |

**FACT.** Drone-Hacks additionally implements an **encryption** family —
`EncryptCmd`, `EncryptOperType`, `EncryptGetStateRq`, `EncryptConfigRq`,
`EncryptConfig3Rq`, `EncryptDoEncryptRq`, `EncryptGetChipStateRe`,
`EncryptGetModuleStateRe`, `EncryptConfigRe` — plus `HDLink_WriteHardwareRegister`
and `Gimbal_Calib`.

**FACT.** Free Fly has **no** encryption payload, no hardware-register write and
no gimbal calibration. `ENC_NO_ENC` is declared there and never used.

### 3.2 Payload field names

**FACT.** Drone-Hacks' 2017 request payloads carry fields named:

- `ReadParamValByIndex2017Rq`: `table_no`, **`unknown1`**
- `WriteParamVal*ByIndex2017Rq`: `table_no`, **`unknown1`**
- `GetParamInfoByIndex2017Rq`: `table_no`, `param_index`
- `GetTblAttribute2017Rq`: `table_no`

Free Fly's corresponding payloads are
`uint16le table ‖ uint16le 0 ‖ uint16le index` for reads/writes and
`uint16le table ‖ uint16le index` for get-param-info. The reserved zero that
Free Fly writes is named `unknown1` by Drone-Hacks — **the same undocumented
reserved field, independently observed in both projects**.

### 3.3 The parameter type table differs

**FACT.** `DUMLPayload_FlyController_ParamType` carries constants `[0..7]` —
**eight** types. Free Fly's `ParamType` has **ten** (`UINT8`…`DOUBLE`, ids 0–9).

**INFERENCE.** Drone-Hacks' enum appears truncated relative to Free Fly's, or
Free Fly added `FLOAT`/`DOUBLE` handling Drone-Hacks lacks. The numeric values
that overlap are identical. **This is a genuine difference, not an error.**

### 3.4 The framer is more robust

**FACT.** `duml.py` has `do_packetise_byte(byte, state, info)` — a byte-at-a-time
state machine — with `is_packet_ready`, **`is_packet_damaged`**,
`is_packet_at_finish`, `store_packet`, `drop_packet`.

**FACT.** Free Fly's `DumlParser.parse` is single-shot with **no** resync and no
damage detection.

**INFERENCE.** Drone-Hacks' framer detects a damaged frame and drops it;
Free Fly's does not. That is a real robustness difference between the two, and
it is why `flylib.StreamParser` resynchronises.

### 3.5 Reply matching

**FACT.** `duml_communication.py` has
`packet_header_is_reply_for_request(rplhdr, reqhdr, responsebit_check, seqnum_check)`
and `find_reply_for_request(po, pktlist, pktreq, seqnum_check)`.

**INFERENCE.** Both the response bit and the sequence number are **optional**
checks. That is the same tolerance this project had to infer for Free Fly's
`awaitPacket` and encode in `flylib.Session.matches` — sequence drift is
tolerated rather than required to match. Two implementations, same policy.

### 3.6 Both 2015 and 2017 are live here

**FACT.** `drone_parameters.py` has `do2015Params()`, and `duml_communication.py`
exposes `flyc_param_request_2015_get_param_info_by_index`,
`…_read_param_value_by_hash`, `…_write_param_value_by_hash` alongside the 2017
equivalents.

**FACT.** In Free Fly the 2015 builders have **zero call sites** — dead code.

**INFERENCE.** Drone-Hacks uses both protocols; Free Fly shipped with the 2015
path compiled in but unreachable. That is the single most concrete behavioural
difference between the two found so far.

## 4. Parameter subsystem

**FACT.** `drone_parameters.DroneParameters` provides `get_parameter_by_name`,
`get_all_parameters`, `set_parameter(name, value, exact_name)`,
`write_default_values`, `set_default_value_by_name`,
`write_parameter_to_drone`, `export_parameters`, `import_parameters`,
`_string_to_value`, `_value_to_string`.

**INFERENCE.** This mirrors Free Fly's `DroneRepository` surface almost
name-for-name — including `exportParameters` / `importParameters` /
`writeDefaultValues` / `clearCache`. Drone-Hacks additionally exposes
`get_default`, which Free Fly does not.

## 5. What this establishes

**INFERENCE, MEDIUM tier.** Drone-Hacks 1.48 and Free Fly 1.0 implement the same
DUML protocol with the same header layout, the same command set, the same
registration handshake, the same parameter-name hash, the same 2017 payload
shape *including the undocumented reserved field*, and the same
tolerant reply-matching policy.

That is far above the "both use DUML" tier. It is consistent with both being
implementations of DJI's protocol using the same public reverse-engineering
literature — which the mission's provenance scale treats as **convergence on a
third party's format**, not as copying.

**It is not HIGH tier.** There is no evidence of shared code: the languages
differ (Cython/Python vs Kotlin), the naming conventions differ
(`Rq`/`Re` suffixes vs `get…`/`read…`), and no identical constant table, bug, or
typo has been shown.

**Differences that keep this from being "the same code twice":**

| | Drone-Hacks 1.48 | Free Fly 1.0 |
|---|---|---|
| Platform | Tkinter desktop, pyserial | Android, raw USB bulk |
| 2015 protocol | **live** | **dead code** |
| Framer | byte state machine, damage detection | single-shot, no resync |
| Encryption | full family implemented | declared, never used |
| Hardware register writes | yes | no |
| Gimbal calibration | yes | no |
| Type table | 8 types | 10 types |
| Licensing | `cert_view`, `dji_login` | **none** |

## 6. Not done

- The `.pyd` extensions were **not** decompiled. Conclusions rest on the shipped
  `.pyc` bytecode and archive metadata.
- The numeric `cmdSet`/`cmdId` values per payload class were **not** recovered;
  they are class-body attributes, not literals in the function code objects
  dumped so far. That is the next concrete step and it would allow a true
  byte-level frame comparison with Free Fly's table.
- ~~`assets/advanced.json` ... compare against Free Fly's catalogue.~~
  **RETRACTED** in `dronehacks_fingerprint_hunt.md`: it is a human-verification
  quiz payload (986 B, `{"quiz": {...}}` with deliberate misspellings), not a
  parameter database. A token scan also found **no** DJI parameter names
  anywhere in the bytecode, so Drone-Hacks ships no catalogue at all and
  discovers the table from the aircraft at runtime. There is no
  catalogue-overlap question to answer.
- `core/dji.py`, `controller/api_controller.py` and `view/dji_login.py` have
  since been read: `api_controller` and the two login views contain the full
  licence/backend subsystem, documented in `dronehacks_fingerprint_hunt.md`.
- No Authenticode signature analysis of the EXE beyond the PyInstaller payload.