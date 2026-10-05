# Drone-Hacks 1.48 — bounded fingerprint hunt

Before any broad decompilation: search the shipped CPython bytecode for specific
fingerprints, then use the hits to partition the executable. 25 modules,
11,735 string/name tokens scanned from the `.pyc` files inside the PyInstaller
bundle. No `.pyd` was decompiled and no claim here depends on one.

---

## 1. The headline: identical CRC and hash constants

**FACT.** Constants read out of `core/duml.pyc`:

| Function | Integer constants |
|---|---|
| `calc_pkt_checksum(packet, plength)` | `0x0`, `0x8`, `0xFF`, **`0x3692`** |
| `calc_hdr_checksum(seed, packet, plength)` | `0x0`, `0xFF` (seed supplied by caller) |
| `flyc_parameter_compute_hash(po, parname)` | `0x0`, `0x8`, **`0xFFFFFFFB`**, `0xFFFFFFFF` |

**FACT.** The CRC-8 seed is supplied at the call site: `createDUML_int` and
`createDUMLChunkStart_int` both pass **`119` = `0x77`**.

**FACT.** `do_packetise_byte` carries `85` (`0x55`, the DUML magic), `171`
(`0xAB`, the high byte of the 16-bit length mask) and `1023` (`0x3FF`, the
10-bit length mask).

**Cross-check against this project's Free Fly recovery:**

| Constant | Free Fly 1.0 (Kotlin) | Drone-Hacks 1.48 (Cython/Python) |
|---|---|---|
| crc8 init | `0x77` | `0x77` ✓ |
| crc8 polynomial | `0x8C` (reflected) | table-driven, same role |
| crc16 init | `0x3692` | `0x3692` ✓ |
| crc16 xorout | `0x0000` | implied by mask-only arithmetic |
| length mask | `0x3FF` | `1023` ✓ |
| param hash modulus | `0xFFFFFFFB` (2³²−5) | `0xFFFFFFFB` ✓ |

**These are DJI's protocol constants, and both projects agree on every one of
them.** That cuts two ways, and the two must not be collapsed:

1. **Strong validation of the Free Fly protocol recovery.** The `flylib.crc`
   derivation was obtained by brute-forcing the APK's own CRC tables against
   every polynomial. A codebase in a different language, written years apart
   against different hardware, independently lands on the same CRC-8 seed, the
   same CRC-16 initial value, the same length mask and the same parameter-hash
   modulus. The Free Fly constants are therefore very unlikely to be a
   misreading of the bytecode.
2. **LOW evidence for direct code lineage.** Identical protocol constants are
   what *both* independent implementations of a third-party format must
   produce. They demonstrate shared *protocol knowledge*, not shared source.
   The scale this project uses ranks identical constant **tables** as HIGH, but
   these are four scalar values that are fully determined by the wire format.

The honest description is therefore **separately implemented codebases** that
converge on the same protocol constants — not "unrelated" codebases, since that
would assert independence this evidence does not establish, and not "shared"
codebases either. The direct-lineage question is scored separately in
`docs/APP_LINEAGE.md`.

**One divergence, and it matters for reproduction.** Drone-Hacks encodes the
parameter name with **`'gbk'`**; Free Fly uses **US-ASCII**. For ASCII
parameter names the two produce identical hashes; for a name containing a
non-ASCII character they diverge, and Drone-Hacks will encode where Free Fly
raises. Recorded rather than reconciled.

## 2. Subsystem partition

Hits per needle, by module:

| Subsystem | Modules carrying it | Evidence |
|---|---|---|
| **Parameter / DUML** | `core/duml`, `core/duml_communication`, `core/drone_parameters`, `core/core` | `calc_pkt_checksum`×3, `calc_hdr_checksum`×4, `createDUML`×4, `DUMLHeader`×17, `store_packet`×4, `table_no`×28, `param_index`×25, `unknown1`×12, `param_hash`×17 |
| **Transport** | `serial/*`, `core/duml_communication`, `core/dji` | `port`×7, `baud`×3, `serial`×4, plus `serial/tools/list_ports_windows` |
| **Device / ADB** | `pyadb/adb`, `controller/*` | `bootloader` (adb), ADB helpers |
| **Licence / backend** | `controller/api_controller`, `view/dji_login`, `view/cert_view`, `controller/settings_controller`, `controller/view_controller`, `core/dji` | `login`×9, `license`×8, `token`×5 |
| **Firmware** | `controller/compatibility_controller`, `controller/drone_controller`, `core/core`, `view/*` | `firmware`×11, `version`×8 |
| **UI / wizard** | `view/view`, `view/wizard` | `fcc`×2, `firmware` |

**FACT — no FCC subsystem.** `RCLink`, `rclink`, `logiclink`, `duss`, `DUSS`:
**zero occurrences** in all 25 modules. `AUTOTEST` appears once as a bare
identifier in `core/duml` and `WIFI` seven times in `core/dji`; there is no
service-mode sequence, no radio command, no channel-map logic.

**INFERENCE.** Drone-Hacks 1.48 is a **parameter** tool, not an FCC tool — the
same conclusion reached independently for Free Fly. It speaks raw DUML over USB
serial and does not implement RCLink, which NLD FCC does.

## 3. The licence and backend subsystem

**FACT.** `controller/api_controller` embeds:

```
https://drone-hacks.com/api/v1
/account/login
/account/verify-token
/license
/license/
/license/update-short-sn-to-long-sn
```

with user-facing strings:

> "Device license is valid!"
> "No license found for this device!"
> "You do not have any license available to register for this device. Please,
> purchase a new license on www.drone-hacks.com."
> "Error! There was an error and the license could not be registered for this
> device! Contact Drone-Hacks support!"
> "This board cannot be used for extended unlocks or registering a license."
> "Could not download necessary files from drone-hacks.com, please check your
> internet connection…"
> "You got an older software version. Please download the latest version:
> https://drone-hacks.com/"

**FACT.** `view/dji_login` and `view/cert_view` embed DJI's account service:

```
https://account-api.dji.com/apis/apprest/
v1/email_login
token
```

plus "DJI Login E-Mail:", "DJI Login Password:", "Unlock Certificate", and:

> "Certificate name (displayed in the certificate view of the DJI App). This can
> only be 16chars long and cannot contain any special chars"

**INFERENCE.** The licence flow is: authenticate to **DJI's account API** by
email and password; create an "Unlock Certificate" surfaced inside the DJI app;
authenticate to **drone-hacks.com/api/v1** via `/account/login` then
`/account/verify-token`; register a licence bound to the device, with
`/license/update-short-sn-to-long-sn` converting a short to a long serial; and
download additional files from the backend. `PACKAGE_USAGE_STATS`-style device
identity and the "this board cannot be used for extended unlocks" message suggest
the licence is bound to specific hardware.

**INFERENCE.** Drone-Hacks is **licence-gated and online**. It is the opposite
of Free Fly, which holds no `INTERNET` permission and no HTTP library.

**Not done:** the API was not contacted. No request was made to either endpoint,
and no attempt was made to bypass or exercise the licence check.

## 4. No bundled parameter catalogue

**FACT.** `assets/advanced.json` is **not** a parameter database. It is a
human-verification payload:

```json
{"quiz": {"sport": {"q1": {"question": "...", "options": [...], "answer": "..."}},
          "maths": {...}}}
```

986 bytes, questions with four options and an answer key, containing deliberate
misspellings ("Golden State Warriros", "Huston Rocket") so the correct option is
unambiguous. **INFERENCE:** an anti-automation or proof-of-human check gating the
"advanced" feature set.

**Correction.** An earlier draft of `dronehacks_baseline.md` suggested
`advanced.json` was "the obvious thing to compare against Free Fly's
`params_catalog.json`". That was wrong and is retracted.

**FACT.** A search of all 11,735 tokens finds **no** DJI parameter names:
`gps_lon`, `ce_country_type`, `g_config`, `flyc`/`Flyc`/`FLYC` — **zero** hits.
The only related token is the identifier `param_name`.

**INFERENCE.** Drone-Hacks ships **no** parameter catalogue. It discovers the
parameter table at runtime from the aircraft, via
`getTblAttribute2017`/`getParamInfoByIndex2017`, exactly as Free Fly does. This
means there is **no catalogue-overlap question to answer** — the two apps have
nothing to compare, because neither bundles DJI's parameter names. Free Fly's
855-entry `params_catalog.json` is unique to Free Fly.

**FACT.** Drone-Hacks' `core/drone_parameters.py` exposes
`get_parameter_by_name`, `get_all_parameters`, `set_parameter`,
`write_default_values`, `set_default_value_by_name`, `write_parameter_to_drone`,
`export_parameters`, `import_parameters` — the same surface Free Fly's
`DroneRepository` offers, including `exportParameters`/`importParameters`/
`writeDefaultValues`. Drone-Hacks additionally exposes `do2015Params()`.

## 5. Summary against the hunt list

| Fingerprint sought | Result |
|---|---|
| DUML CRC tables | **matched** — init `0x77` (crc8), `0x3692` (crc16) |
| 2015/2017 parameter commands | **both present and live** (`do2015Params` + 2017 path) |
| Free Fly `paramHash` | **matched** — modulus `0xFFFFFFFB` (GBK vs US-ASCII naming) |
| NLD FCC sequence | **absent** — no service mode, no radio, no channel map |
| Ports 40009 / 40007 | **absent** — no RCLink, no DUSS, USB serial instead |
| AUTOTEST / radio commands | **absent** as a subsystem; one bare `AUTOTEST` identifier |
| Distinctive parameter strings | **absent** — no bundled catalogue |
| Bonus: backend/licence | **present** — drone-hacks.com API + DJI account API |

## 6. Not established

- The `.pyd` extension internals. Everything above is from `.pyc` bytecode.
- The CRC *polynomials* in Drone-Hacks: `calc_pkt_checksum` uses a table but
  the table is built at runtime, so only the initial value is observable from
  the bytecode. The shared init and shared behaviour are strong evidence for a
  shared polynomial; it is not directly observed.
- Whether `/license/update-short-sn-to-long-sn` is called at unlock time or only
  during registration.
- Any request to either backend.