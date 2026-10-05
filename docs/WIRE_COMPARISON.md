# Drone-Hacks 1.48 vs Free Fly 1.0 — normalized wire comparison

Command constants and payload layouts recovered from the `.pyc` bytecode in the
PyInstaller bundle. No `.pyd` introspection was needed, and none was attempted.

---

## 1. Method

`DroneCommands` and `DumlBuilder` are Kotlin, so its command ids live in a
`DumlConstants` object. Drone-Hacks' ids are literals at the call sites in
`core/duml_communication.pyc`, so each `flyc_param_*` function's `co_consts`
gives its `cmdId` directly.

**Normalization.** Sequence number and CRCs are excluded (assigned/computed at
transmission). Payload bytes are compared on structure. Signing and transport
are out of scope for the frame itself.

---

## 2. Command ids — 10 of 10 identical

| Drone-Hacks function (`duml_communication.pyc`) | cmdId | Free Fly constant | |
|---|---|---|---|
| `flyc_request_assistant_unlock` | `0xDF` | `CMD_FC_ASSISTANT_UNLOCK = -33` | ✓ |
| `flyc_param_request_2015_get_param_info_by_index` | `0xF0` | `CMD_FC_PARAM_INFO_2015 = -16` | ✓ |
| `flyc_param_request_2015_read_param_value_by_hash` | `0xF8` | `CMD_FC_PARAM_READ_2015 = -8` | ✓ |
| `flyc_param_request_2015_write_param_value_by_hash` | `0xF9` | `CMD_FC_PARAM_WRITE_2015 = -7` | ✓ |
| `flyc_param_request_2017_get_table_attribs` | `0xE0` | `CMD_FC_PARAM_TABLE_ATTRS_2017 = -32` | ✓ |
| `flyc_param_request_2017_get_param_info_by_index` | `0xE1` | `CMD_FC_PARAM_INFO_2017 = -31` | ✓ |
| `flyc_param_request_2017_read_param_value_by_index` | `0xE2` | `CMD_FC_PARAM_READ_2017 = -30` | ✓ |
| `flyc_param_request_2017_write_param_value_by_index` | `0xE3` | `CMD_FC_PARAM_WRITE_2017 = -29` | ✓ |
| `reply_reg_ack` | `0x82` | `-126` | ✓ |
| `reply_reg_dev` | `0x81` | `-127` | ✓ |

**Version inquiry**: Drone-Hacks' module-level constants are cmdSet `0x00` and
cmdId `0x01`; Free Fly's `versionInquiry` is `CMD_SET_COMMON = 0`, cmdId `1`. ✓

**Absences are as informative as matches.** Searching every constant in
`duml_communication.pyc` for the FCC sequence finds **none** of `0x58`
(AUTOTEST service mode), `0x72` (radio region), `0x8C` (radio parameter),
`0xAF`, `0xE5` (country 22), `0x30` (WIFI), `0x27` (OFDM), `0x18`/`0x19` (WIFI
map/flag), or `0x4F` (CFG chunk).

**One residue.** `find_reply_for_request` carries `0x32` — `GENERAL` cmdSet,
cmdId 50, which NLD's profile calls *"set country code '11'"*. It appears in the
**reply matcher**, not in any request builder. Whether that is a country-code
comparison or a coincidence is not established.

## 3. Payload layouts are identical

**FACT.** Drone-Hacks' payload classes are `ctypes` structures declared in
`core/duml.pyc`, not Python enums:

| Drone-Hacks class | ctypes members | `_fields_` |
|---|---|---|
| `..._WriteParamVal{N}ByIndex2017Rq` | `c_ushort`, `c_ubyte` | `table_no`, **`unknown1`**, `param_index`, (+ value) |
| `..._WriteParamVal{N}ByHash2015Rq` | `c_uint`, `c_ubyte` | `param_hash`, `param_value` |
| `..._ReadParamValByIndex2017Rq` | `c_ushort` | `table_no`, `unknown1`, `param_index` |
| `..._ReadParamValByHash2015Rq` | `c_uint` | `param_hash` |
| `..._GetTblAttribute2017Rq` | `c_ushort` | `table_no` |
| `..._GetParamInfoByIndex2017Rq` | `c_ushort`, `c_ushort` | `table_no`, `param_index` |

**FACT.** Free Fly builds the same payloads by hand:

| Transaction | Drone-Hacks (ctypes) | Free Fly (builder) |
|---|---|---|
| 2017 read | `u16 table_no, u16 unknown1, u16 param_index` | `uint16le table ‖ uint16le 0 ‖ uint16le index` |
| 2017 write | same + `c_ubyte[N] param_value` | same ‖ `value` |
| 2015 read | `u32 param_hash` | `uint32le paramHash(name)` |
| 2015 write | `u32 param_hash, c_ubyte[N] param_value` | `uint32le paramHash(name) ‖ value` |
| 2017 table attribs | `u16 table_no` | `uint16le table` |
| 2017 get param info | `u16 table_no, u16 param_index` | `uint16le table ‖ uint16le index` |

**The `unknown1` field is the sharpest item.** Drone-Hacks names the reserved
zero `unknown1`; Free Fly writes it as a bare reserved zero. Both put it in the
same position, between the table number and the parameter index.

**INFERENCE.** An undocumented reserved field in a proprietary binary format is
a natural thing for two implementers to observe independently and both to leave
unnamed. It is a good marker of shared *protocol knowledge* and weak evidence of
shared *code*.

## 4. Correction: `ParamType` is 12 entries, not 8

An earlier draft of `dronehacks_baseline.md` stated Drone-Hacks' `ParamType` has
**8** entries against Free Fly's 10. That was an artefact of truncating the
constant list to its first eight entries.

**FACT.** `DUMLPayload_FlyController_ParamType` in `core/duml.pyc` carries
constants `0x0` through `0xb` — **12** — with ctype member names beginning
`ubyte, ushort, ulong, ulonglong, byte, …`.

**INFERENCE.** The two type tables are of **different width**: 12 in
Drone-Hacks, 10 in Free Fly. They overlap over the shared ids. Whether one is a
superset, or they diverge in the middle, is not established from the truncated
name list.

## 5. Framing constants

**FACT.** `do_packetise_byte` carries `85` (`0x55`), `171` (`0xAB`) and `1023`
(`0x3FF`); `createDUML_int` passes `119` (`0x77`) as the CRC seed;
`calc_pkt_checksum` carries `0x3692`; `flyc_parameter_compute_hash` carries
`0xFFFFFFFB` and `0xFFFFFFFF`.

All five match Free Fly. See `dronehacks_fingerprint_hunt.md` §1 for why that is
**strong validation of the Free Fly protocol recovery** and only **LOW** evidence
of direct code lineage.

**One divergence.** Drone-Hacks encodes parameter names with `gbk`; Free Fly with
US-ASCII. Identical for ASCII names; divergent — and Free Fly raises — for
non-ASCII.

## 6. Result

| Family | Command ids | Payload layout |
|---|---|---|
| AssistantUnlock | `0xDF` ✓ | `01 00 00 00` — not recovered from `.pyc`; see caveat |
| 2015 metadata by index | `0xF0` ✓ | `u16 index` |
| 2015 read by hash | `0xF8` ✓ | `u32 hash` |
| 2015 write by hash | `0xF9` ✓ | `u32 hash ‖ value[N]`, N ∈ {1,2,4,8,16} |
| 2017 table attributes | `0xE0` ✓ | `u16 table` |
| 2017 metadata by index | `0xE1` ✓ | `u16 table ‖ u16 index` |
| 2017 read by index | `0xE2` ✓ | `u16 table ‖ u16 reserved ‖ u16 index` |
| 2017 write by index | `0xE3` ✓ | same ‖ `value[N]`, N ∈ {1,2,4,8,16} |
| Registration replies | `0x82`, `0x81` ✓ | not recovered |

**All ten command ids and all six payload layouts agree.** The two projects
implement DJI's FC Assistant parameter protocol identically on the wire.

## 7. Not established

- **`assistantUnlock`'s payload** `01 00 00 00` is Free Fly's. Drone-Hacks'
  `flyc_request_assistant_unlock(po, ser, val)` takes the value as an
  *argument*, so its literal is at the call site in `do_assistant_unlock`, which
  was not traced. The command id matches; the payload is unconfirmed.
- The `reply_reg_ack` / `reply_reg_dev` payload bytes.
- The CRC *polynomials* in Drone-Hacks — the table is built at runtime, so only
  the initial value is observable from the bytecode.
- Whether the `0x32` constant in `find_reply_for_request` is a country-code
  comparison.
- No `.pyd` was introspected; everything above is `.pyc`.