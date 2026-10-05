# NLD FCC — bounded fingerprinting pass

Static pass over `research/corpus/nldfcc/nldfcc.apk`
(sha256 `4a6e07a2ee1fbd7f2dacd4bb500ed3a2747490be1d8adb4d6f212d99a4a15126`,
7,269,392 bytes). Deliberately bounded: identity, signing, transport, and the
command profiles the app ships. No decompilation of app logic.

Reproduce: `python tools/signing.py research/corpus/nldfcc/nldfcc.apk work/nldfcc`.

---

## 1. Identity

| Field | Value |
|---|---|
| Package | `com.nolimitdronez.nldfcc` |
| versionName / versionCode | `2.0.0.6` / `46` |
| Label | **NLD FCC** |
| DEX | 2 (`classes.dex`, `classes2.dex`) |
| Native libs | 5 per ABI × arm64-v8a + armeabi-v7a |
| Signing scheme | v2 only, **no v1** |
| Cert subject | `CN=KK, OU=App, O=NO LIMIT TECHNOLOGY LTD, L=Nicosia, C=CY` |
| Cert SHA-256 | `72e71df3f2cc7db67a5ec62c1acb513e03ddbcd43f828d365b51e67ff2199a89` |
| Serial / validity | `01`, 2026-03-12 → 2051-03-06 |

**FACT.** The APK Signing Block carries a **third, unknown pair** with id
`0x504B4453` (ASCII `PKDS`), length 4281, alongside the v2 block and a verity
padding block. Not a recognised AOSP scheme id — proprietary or repurposed.

**Caution.** As with DJIFCC's `C=PL`, the DN fields of a self-signed certificate
record what the creator typed into keytool. They are not attribution.

## 2. Permissions — eight, and they matter

```
android.permission.INTERNET
android.permission.SYSTEM_ALERT_WINDOW
android.permission.PACKAGE_USAGE_STATS
android.permission.POST_NOTIFICATIONS
android.permission.FOREGROUND_SERVICE
android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE
android.permission.FOREGROUND_SERVICE_SPECIAL_USE
com.nolimitdronez.nldfcc.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION
```

**INFERENCE.** `INTERNET` plus `libwg*.so` (WireGuard) means NLD FCC ships a VPN
stack and can reach the network. `SYSTEM_ALERT_WINDOW` + `PACKAGE_USAGE_STATS`
is the overlay/usage-stats pair typical of a persistent background utility. The
three `FOREGROUND_SERVICE*` permissions mean a long-lived service — consistent
with the keepalive described below.

**This is the opposite of Free Fly**, which holds no `INTERNET` permission and no
HTTP library at all.

## 3. Transport — TCP to the controller, not raw USB

**FACT.** The bundled profiles state their own transport:

- `fcc_keepalive.json`: *"Re-applies FCC radio mode every **2s over TCP 40009**
  to prevent DJI Fly from resetting to CE."*
- `led_on.json` / `led_off.json`: *"Uses **port 40007** with outer wrapper."*

**FACT.** The LED profiles also reference `FccViewModel.setLed()` and a
`HardwareLock` — *"Does NOT hold HardwareLock so the FCC keepalive continues
during the LED command."*

**INFERENCE.** NLD FCC reaches the aircraft through a **local TCP service on the
controller** (ports 40007 / 40009), wrapped in an "outer wrapper", rather than
opening a raw USB endpoint as Free Fly does. The port numbers line up with what
the public corpus reports for this family of tools (`djiparam` 40007/40008,
FreeFCC 40009).

## 4. The command profiles — a documented FCC sequence

**FACT.** The app ships seven JSON profiles under `assets/profiles/`:
`fcc.json`, `fcc_keepalive.json`, `ce_restore.json`, `device_info.json`,
`4g.json`, `led_on.json`, `led_off.json`.

**FACT.** Each is fully self-describing: `name`, `description`, `sender`,
`sender_desc`, `cmd_type`, `cmd_type_desc`, `rounds`, `inter_frame_delay_ms`,
`inter_round_delay_ms`, `read_window_ms`, and `frames`, where each frame is
`{s: cmdSet, i: cmdId, d: data length, p: payload hex, note: description}`.

**This is the single most complete FCC sequence available in this corpus.** It
is the vendor's own annotated description of what it sends.

### 4.1 The 21-frame "FCC Universal" sequence

Sender `130` = `MOBILE_APP, index 4`; `cmd_type` 32 = *"Request,
ACK_BEFORE_EXEC, no encryption"*; 2 rounds, 30 ms between frames, 100 ms
between rounds, 50 ms read window.

| # | cmdSet | cmdId | Target | Action |
|---|---|---|---|---|
| 0 | `0x10` | `0x58` | AUTOTEST | **enter service mode** |
| 1 | `0x06` | `0x72` | REMOTE_RADIO | set region param to FCC (01) |
| 2 | `0x03` | **`0xF9`** | FLYCONTROLLER | **write param** |
| 3 | `0x00` | `0x00` | WM330/WM220 | activate change |
| 4 | `0x00` | `0x32` | LB_68013_SKY | set **country code '11'** |
| 5 | `0x03` | `0xAF` | FLYCONTROLLER | write param |
| 6 | `0x07` | `0x30` | WIFI | channel group AU 2.4G |
| 7 | `0x07` | `0x30` | WIFI | channel group AU 5.8G |
| 8 | `0x09` | `0x27` | OFDM | **2.4G power limit** |
| 9 | `0x09` | `0x27` | OFDM | **5.8G power limit** |
| 10 | `0x07` | `0x18` | WIFI | write channel map |
| 11 | `0x07` | `0x19` | WIFI | set channel flag |
| 12 | `0x03` | **`0xF9`** | SVO | write param **ON** |
| 13 | `0x03` | **`0xF9`** | SVO | write param **OFF** |
| 14 | `0x00` | `0xE5` | LB_68013_SKY | set **country code '22'** |
| 15 | `0x03` | **`0xF9`** | FLYCONTROLLER | write param |
| 16 | `0x03` | **`0xF9`** | FLYCONTROLLER | write param |
| 17 | `0x06` | `0x8C` | LB_MCU_SKY | radio parameter 03 |
| 18 | `0x06` | `0x8C` | LB_MCU_SKY | radio parameter 01 |
| 19 | `0x06` | `0x72` | REMOTE_RADIO | **commit region change** |
| 20 | `0x10` | `0x58` | AUTOTEST | **exit service mode** |

**INFERENCE.** The sequence is a genuine *radio* reconfiguration, not a parameter
edit: it enters **service mode**, sets the radio region, rewrites the **WIFI
channel map**, sets **OFDM power limits**, sets **country codes**, and commits
to the remote radio before leaving service mode. Only frames 2, 5, 12, 13, 15,
16 touch the flight controller.

### 4.2 The hashed FC parameter writes

**FACT.** Frames 12 and 13 both carry `cmdSet 0x03 / cmdId 0xF9` with payloads
`d04aeffb01` and `d04aeffb00`. They share the leading four bytes `d0 4a ef fb`
and differ only in the final value byte.

**FACT.** Five-byte `cmdSet 3 / cmdId 0xF9` payloads elsewhere in the sequence are
`8a237103f401`, `236b820101`, `8773e68a01`.

**INFERENCE.** Reading the four leading bytes as a little-endian uint32 gives a
parameter hash and the trailing byte the value — i.e. `0xFBEF4AD0 = 1` and
`0xFBEF4AD0 = 0`. That is the signature of a **name-hashed FC parameter write**.

**This is the same command Free Fly implements.** Free Fly declares
`CMD_FC_PARAM_WRITE_2015 = -7` = `0xF9` on `CMD_SET_FC = 3`, and builds exactly
`uint32le(paramHash(name)) ‖ value`. Two independent projects, one on each side
of the ecosystem, arrived at the same command id from the same DJI firmware
convention.

**FACT — and the asymmetry that matters.** In Free Fly that builder has **zero
call sites**: it is dead code. In NLD FCC's documented sequence it appears six
times and is load-bearing.

### 4.3 Two more shared commands

**FACT.** `device_info.json` is `cmdSet 0x00 / cmdId 0x01`, noted *"GENERAL
VersionInquiry to ANY — returns HW version, LDR version…"*. That is **exactly**
Free Fly's `versionInquiry` (cmdSet COMMON 0, cmdId 1), including the empty
payload.

**FACT.** NLD's `sender` value 130 is decoded by the vendor as
`MOBILE_APP, index 4`. `130 = (4 << 5) | 2`. That is precisely Free Fly's
`packDevByte(type, index) = (index & 7) << 5 | (type & 0x1F)` with type 2
(`DEV_APP`). **The device-byte encoding is independently confirmed** by a
project that documents it in prose.

### 4.4 Other profiles

- **`fcc_keepalive`** (4 frames): service-mode in → set region FCC → **commit** →
  service-mode out, re-applied every 2 s. **INFERENCE:** this is why the change
  does not survive — DJI Fly resets the radio to CE, so the tool must keep
  re-applying. Persistence is *borrowed time*, not a stored setting.
- **`ce_restore`** (1 frame): *"Resets the radio to its factory-flashed default
  region (CE for CE units, FCC for FCC units)."* cmd_type 6 =
  *"Request, NO_ACK_NEEDED"*.
- **`led_on` / `led_off`**: *"2 bursts of 5 writes (10 total) with 100ms between
  each"*, sender 2 = `CAMERA, index 0`, cmd_type 64.
- **`4g`**: *"Enables 4G transmission on the aircraft. 128 frames with the
  aircraft serial embedded in each payload."*

**INFERENCE.** `ce_restore`'s wording is notable: the default is per-unit and
factory-flashed. That is the strongest statement in this corpus about where
FCC/CE actually lives — in the **radio module's flash**, not in a phone-side
flag and (on this evidence) not primarily in an FC parameter.

## 5. Free Fly vs NLD FCC, side by side

| | **Free Fly** | **NLD FCC** |
|---|---|---|
| Transport | raw USB bulk, VID `0x2CA3` | **TCP 40007/40009** to the controller, "outer wrapper" |
| Internet | none — no permission, no HTTP lib | `INTERNET` + bundled **WireGuard** |
| Scope | FC parameter table only | **radio, service mode, WiFi, OFDM, country code** |
| Service mode | none | **enter/exit** (`0x10`/`0x58`) |
| `cmdSet 3 / cmdId 0xF9` param write | implemented, **dead code** | **used six times**, load-bearing |
| `cmdSet 0 / cmdId 1` version inquiry | implemented, live | implemented |
| Device-byte packing `(i<<5)\|t` | implemented | documented in prose, same encoding |
| Persistence | FC accepts the parameter, or not | **2 s keepalive** re-applied over TCP |

**INFERENCE — the lineage answer.** The two tools agree on DUML's *framing
conventions* (device-byte packing, ack semantics, the version-inquiry command)
and share one *command id* for hashed parameter writes, which is what you would
expect of two independent implementations of the same DJI firmware protocol
using the same public reverse-engineering literature. They diverge completely in
**what they use it for**: Free Fly reads and edits the flight controller's
parameter table; NLD FCC reconfigures the **radio** through service mode.

Neither is derived from the other on the evidence available. This is **MEDIUM**
tier at most — shared protocol and one shared command id — and **LOW** for any
claim of shared *code*.

## 6. The region parameter check — a clean negative

**FACT.** Searched across all 2,587,172 bytes of NLD's DEX **and** its profile
assets:

| Needle | DEX | Profiles |
|---|---|---|
| `ce_country_type` | **0** | **0** |
| `country` | 0 | 2 |
| `region` | 6 | 6 |
| `fcc` / `FCC` | 121 / 5 | — |
| `logiclink` | **0** | — |
| `WriteParamByHash`, `getParamInfo`, `flyc_param` | **0** | — |
| `40007`, `40008`, `40009` | **0** | named in profile prose |
| `0x2ca3` (USB VID) | **0** | — |

**FACT.** `ce_country_type` — the parameter Free Fly's catalogue exposes and
whose 2017 write path is live in Free Fly — **does not appear anywhere in NLD
FCC**. Neither does `com.dji.logiclink`.

**INFERENCE.** This separates the two approaches cleanly. Free Fly addresses
region through a **flight-controller parameter**; NLD FCC addresses region
through the **radio module in service mode**, and shows no sign of touching the
FC parameter table for that purpose. The six `cmdSet 3 / cmdId 0xF9` writes in
NLD's sequence belong to the radio procedure, not to a substitute for the
country parameter.

**FACT.** The TCP ports appear in profile *prose* but not as string literals in
the DEX, placing the transport implementation in native code — consistent with
`libnld-core.so` and the "outer wrapper" wording.

**FACT.** The DEX contains no named FC-parameter-protocol symbols
(`WriteParamByHash`, `getParamInfo`, `flyc_param`), so its parameter writes are
driven by profile data through the native layer rather than by a Java
implementation of the 2015/2017 protocols.

## 7. Not done, and why

- No decompilation of app logic; the profile JSONs were read directly.
- `libnld-core.so` and `libwg*.so` not analysed.
- The `0x504B4453` (`PKDS`) signing block not decoded.
- ~~Whether the WireGuard configuration is active.~~ **RESOLVED** in
  `nld_native_transport.md`: `com.wireguard.android.backend.GoBackend` is
  present in the DEX, so WireGuard is runtime-reachable. (My first check grepped
  for `com.wireguard` with a dot and found nothing; DEX type descriptors use
  `/`.) What it tunnels **to** remains unknown.