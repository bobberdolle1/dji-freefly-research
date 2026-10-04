# Free Fly 1.0 — Architecture

How the app moves from a tap to a DUML frame, reconstructed from smali in
`work/apktool/decoded/smali_classes{4,5,6,7,8,9}/com/dronehacks/app/`.

Evidence labels are used throughout and mean what they mean in
`docs/PROVENANCE.md`: **FACT** (read from the bytecode, with the method named),
**INFERENCE** (concluded from facts, reasoning given), **HYPOTHESIS** (guess,
with what would settle it).

Method note: a full `jadx -d out <apk>` run loaded all 14,580 classes and
2,947,927 instructions and then spent 30+ minutes in codegen without emitting a
file. The app's own classes were then read directly from apktool smali, which is
both faster and the evidence level the project requires — decompiled Java is
explicitly not accepted for protocol constants.

---

## 1. The app is small, and that is the main finding

**FACT.** Of the 258 `com.dronehacks.app` classes, only about 15 are
hand-written. Everything else is Hilt/Dagger-generated
(`DaggerDroneHacksApp_HiltComponents_*`, `DroneHacksApp_HiltComponents$*`,
`Hilt_*`), Compose-generated (`ComposableSingletons*`), or Kotlin lambda
scaffolding (`$$ExternalSyntheticLambda*`, `$WhenMappings`, `$awaitPacket$1`).

The hand-written surface:

| Class | Role |
|---|---|
| `DroneHacksApp` | `@HiltAndroidApp`; sets up DI |
| `MainActivity` | `@AndroidEntryPoint`, Compose host; also the USB-attach target |
| `di.AppModule` | Hilt providers (`provideUsbSerialManager`, context) |
| `ui.screens.MainViewModel` | UI state holder; owns scan/read/write coroutines |
| `ui.screens.UiState` | immutable UI snapshot |
| `data.usb.UsbSerialManager` | USB enumeration, claim, read loop, diagnostics |
| `data.usb.UsbState` | `Connected` / `Disconnected` / `Error` / `WaitingPermission` |
| `data.repository.DroneRepository` | all protocol orchestration and caching |
| `data.repository.RepoResult` | `Success` / `Failure` result wrapper |
| `data.protocol.DumlBuilder` | frame construction + CRCs + sequence counter |
| `data.protocol.DumlParser` | single-shot frame validation |
| `data.protocol.DumlPacket` | data classes |
| `data.protocol.DumlHeader` | header model |
| `data.protocol.DumlConstants` | device/ack/cmdset/cmdid constants |
| `data.protocol.DroneCommands` | one method per request |
| `data.model.*` | `DroneInfo`, `DroneParameter`, `ParamDef`, `ParamType`, `ParamValueType`, `ParamCategory`, `ParamCatalog`, `ConnectionState` |

**INFERENCE.** This is a single-purpose tool, not a product with a feature set.
There is no settings screen, no account, no telemetry, no update path, no
plugin system — consistent with Stage 1's finding that the app has no network
capability at all.

---

## 2. Call graph

```
MainActivity (Compose)
  └─ MainViewModel                     StateFlow<UiState>
       ├─ DroneRepository              StateFlow<DroneInfo>, <parameters>, <progress>
       │    ├─ UsbSerialManager        StateFlow<UsbState>, SharedFlow<packets>, SharedFlow<diagLog>
       │    ├─ DroneCommands           builds request frames
       │    └─ DumlBuilder             encodes frames, crc8/crc16, nextSeq()
       └─ ParamCatalog                 reads assets/params_catalog.json
```

**FACT.** `MainViewModel` coroutine entry points recovered from the
`$$ExternalSyntheticLambda`/`$1` classes: `initDrone`, `readAllParameters`,
`readAllParametersInternal`, `refreshParameters`, `fetchParamValue`,
`setParameter`.

**FACT.** `DroneRepository` private suspend functions (the full protocol
surface): `awaitPacket`, `doUnlockForWrite`, `e2ReadValue`, `fetchDeviceInfo`,
`fetchFirmwareFromCfgFile`, `readAll2015`, `readAll2017`, `readByIndexMap`,
`unlock`, plus public `readAllParameters`, `writeParameter`,
`writeChangedParameters`, `writeDefaultValues`, `exportParameters`,
`importParameters`, `clearCache`.

```mermaid
flowchart TD
    UI[MainViewModel] --> RP[readAllParameters]
    RP --> LM[loadIndexMap codename]
    LM -->|hit| RBM[readByIndexMap]
    LM -->|miss| S17[readAll2017]
    S17 -->|table empty| SKIP[skip table, log diagnostic]
    S17 --> SIM[saveIndexMap]
    RP --> U[unlock / assistantUnlock]
    U --> FD[fetchDeviceInfo]
    FD --> SN[parseSnFromResponse / parseSnFromUsbProductName]
    FD --> FW[fetchFirmwareFromCfgFile -> getCfgFileChunk]
    FW --> PF[parseFirmwareAndCodenameFromAcResponse]
```

---

## 3. USB layer — exact behaviour

**FACT**, from `UsbSerialManager.findAndConnect` and `startReadLoop$1`:

### Device and interface selection

1. Iterate `device.getInterfaceCount()`.
2. For each interface, iterate `getEndpointCount()`. Keep an endpoint when
   `getType() == 0x02` (`ENDPOINT_XFER_BULK`); `getDirection() == 0x80` selects
   the IN endpoint, anything else the OUT endpoint. **Later endpoints overwrite
   earlier ones**, so the *last* bulk IN/OUT pair on an interface wins.
3. If both an IN and an OUT endpoint were found:
   `claimInterface(iface, /* force = */ true)`.
   On failure the app logs `  claimInterface <n> FAILED, trying next` and
   continues to the next interface.
4. On success the two endpoint addresses are rendered as hex strings for the
   diagnostic log.

**FACT.** There is **no** CDC-ACM handling anywhere: no `UsbSerialManager` from
a serial library, no control transfer, no line-coding / baud-rate setup, no
`setInterface`. The app performs **raw USB bulk transfers**. This is a
notable and slightly surprising result — the app does not talk to a serial port
abstraction, it talks to bulk endpoints directly.

### Connection handshake

**FACT.** On entering the read loop the app writes a one-byte buffer
`byteArrayOf(0x30)` to the OUT endpoint **five times**, each with a **200 ms**
timeout:

```
bulkTransfer(epOut, [0x30], 0, 1, 200)   × 5
```

**INFERENCE.** `0x30` is ASCII `'0'`. A repeated single-character nudge is a
common way to make a device-side parser emit or flush state at link-up. What
the aircraft does with it is not determinable from this APK.

### Read path

**FACT.**

| Setting | Value |
|---|---|
| Read buffer | `0x200` = **512 bytes** |
| Read timeout | `0x7d0` = **2000 ms** |
| Write timeout | `0x7d0` = **2000 ms** |
| `_packets` SharedFlow | replay `0`, extra buffer capacity `0x100` = 256 |
| `_diagLog` SharedFlow | replay `0`, extra buffer capacity `0x200` = 512 |

**FACT.** Received bytes are appended to an `incomingBuffer: List<Byte>`.
Framing waits until the buffer holds at least **3** bytes before attempting a
parse, then coalesces into a new array.

**FACT.** `DumlParser.parse` is single-shot with **no resynchronisation**. It
returns a failed `ParseResult` on: buffer shorter than `0x0d` (13), first byte
not `0x55`, declared length exceeding the buffer, header-CRC mismatch, or
frame-CRC mismatch. There is no scan-forward for the next magic byte.

**INFERENCE.** The 3-byte threshold is the minimum needed to read the magic and
the length word. That the parser cannot resynchronise means a single corrupt
byte in the stream costs the app whatever it was waiting for; the clean-room
`flylib.StreamParser` adds resynchronisation precisely because it is the
practical thing to do on a real link, and that difference is documented in
`research/flylib/parser.py`.

### USB identifiers

**FACT.** From `res/xml/device_filter.xml` and `DroneRepository`:
vendor `0x2CA3` (11427, DJI), product IDs `0x10` (16), `0x18` (24), `0x20` (32).
`MainActivity` registers `USB_DEVICE_ATTACHED`, so the app auto-launches when a
matching device is attached.

---

## 4. Protocol selection — what is confirmed and what is not

**FACT.** `DroneRepository.readAllParameters(force: Boolean)` — decoded from
`DroneRepository.smali:9668-10086`:

```
codename = droneInfo.type                      // the AC's model codename
if (!force):
    map = loadIndexMap(codename)
    if map != null:
        diag("Cache hit for <codename>: N known indices — fast read")
        return readByIndexMap(map)             // log "Fast read done: N"
diag("Full scan for <codename> (first time)")
list = readAll2017()
diag("Scan done: N")
if (list.isEmpty() XOR force):                 // see caveat below
    saveIndexMap(codename, list)
return Success(list)
```

**FACT.** `readAll2017` iterates parameter tables, calling
`getTableAttribs2017(tableNo)` to learn each table's declared parameter count,
and contains the literal diagnostic string:

```
"Table " + tableNo + " empty or no response, falling back to 2015"
```


**FACT.** `readAll2015` — which turns out to be dead code, see below — contains
the literal string `"2015 EOL at index "`, so the 2015 walk terminates on an
explicit end-of-list marker rather than a known count.


**FACT.** Index maps are cached under the filename suffix `_index_map.json`,
keyed by the aircraft codename (`DroneRepository.cacheFile`), with
`loadIndexMap` / `saveIndexMap` / `clearCache` as the accessors.

### Confirmed structure, and one correction

**FACT.** `DroneRepository.readAllParameters` — decoded from
`DroneRepository.smali:9668-10086`:

```
codename = droneInfo.type                      // the AC's model codename
if (!force):
    map = loadIndexMap(codename)
    if map != null:
        diag("Cache hit for <codename>: N known indices — fast read")
        return readByIndexMap(map)             // log "Fast read done: N"
diag("Full scan for <codename> (first time)")
list = readAll2017()
diag("Scan done: N")
... saveIndexMap(codename, list)
return Success(list)
```

**FACT — the app is 2017-only, and the "fallback to 2015" is a dead end.**
`readAll2017` contains the literal string `"Table N empty or no response,
falling back to 2015"`, which reads like a per-table protocol fallback. It is
not one. Verified across the whole decoded tree:

| Check | Result |
|---|---|
| `invoke-direct` to `readAll2017` | line **10001**, inside `readAllParameters` — the only live bulk-read path |
| `invoke-direct` to `readAll2015` | line **751** only, which is *inside* `access$readAll2015` (745-755) itself |
| `access$readAll2015` references in the entire tree | exactly **one**: `DroneRepository$readAll2015$1.smali:145`, its own coroutine continuation — the normal Kotlin self-resume pattern, not a caller |
| commands used by `readByIndexMap` | `readParamValue2017` only |
| commands used by `readAll2017` | `getTableAttribs2017`, `getParamInfo2017`, `readParamValue2017` |
| commands used by `readAll2015` | `getParamInfoByIndex2015`, `readParamValue2015` |

**Conclusion — FACT.** `readAll2015` is unreachable dead code. An aircraft
whose tables all report zero parameters gets an **empty result and a log
line**, not a 2015 scan. The message is misleading; it is a leftover.

**FACT — live vs dead commands.** Call-site counts across the decoded tree:

| Command | Callers | Live? |
|---|---|---|
| `assistantUnlock` | 2 | ✅ |
| `readParamValue2017` | 3 | ✅ |
| `getCfgFileChunk`, `getParamInfo2017`, `getTableAttribs2017`, `writeParamValue2017`, `versionInquiry`, `versionInquiryTo`, `replyRegAck`, `replyRegDev` | 1 each | ✅ |
| `getParamInfoByIndex2015`, `readParamValue2015` | 1 each | ❌ only from dead `readAll2015` |
| `getParamInfo2015`, `writeParamValue2015` | **0** | ❌ never called |

**INFERENCE.** Free Fly **writes parameters exclusively through the 2017
protocol** (`writeParamValue2017`). Its 2015 read/write builders exist in the
binary but nothing invokes them. This materially changes the comparative
picture: an FC parameter write is always `cmdSet 3 / cmdId 0xE3` with a
`(table, index, reserved, index, value)` payload.

**Not pinned — stated rather than guessed.** The exact interaction between
`force` and the empty-result test at the end of `readAllParameters` is not
resolved: the operand `isEmpty()` is XORed with is a register that the
coroutine state object moves ambiguously, and it may be the `force` flag or a
size. The *structure* is confirmed; the `force` semantics are **HYPOTHESIS**
pending a cleaner read, and `flylib.selection` does not encode a guess.

**Connection** (`UsbState`): `Disconnected → WaitingPermission → Connected`,
with `Error` reachable from any step (permission refused, `openDevice` null, no
interface claims).

**Protocol selection** (`DroneRepository.readAllParameters`): index map hit →
fast read → return; otherwise full 2017 scan → per-table fallback → save map →
return.

**Parameter value lifecycle** (`UiState`): `DisconnectedPlaceholder` /
`LoadingScreen` / `MainScreen` with `DeviceInfoCard`, `DiagPanel`, `ParamCard`,
`EditParamDialog`, `TopBar`.

---

## 7. What the app does *not* contain

Stated explicitly because several are easy to assume from the "DJI hacking"
framing, and their absence is itself a finding:

- **FACT.** No RCLink framing, no `com.dji.logiclink` / `com.dji.protocol`
  classes, no local socket or loopback TCP transport anywhere in the DEX.
- **FACT (scoped).** No radio-region, FCC-profile, service-mode or C0 command
  appears among the **fourteen named `DroneCommands` builders** or in
  `DumlConstants`. This is an absence *within that search*, not a proof of
  absence: a sequence could in principle be assembled inline from generic
  cmdSet/cmdId values with no named constant and no builder method. No such
  inline construction was found, but the claim is bounded by what was searched.
- **FACT.** No firmware container, patcher or flasher.
- **FACT.** The live read and write paths are **FC Assistant parameter
  protocol** over direct USB bulk, 2017 protocol only.

**Correction made during analysis.** An earlier draft of this section stated
"Everything is FC Assistant parameter protocol only — no FCC, no region tool"
flatly, and modelled a live 2017→2015 fallback. Both were wrong: `readAll2015`
is unreachable, and the catalogue does contain the region parameters
`ce_country_type` and `ce_regulatory_level`. See
`docs/PARAMETERS.md` §5 — the accurate claim is *mechanism-disjoint from the
FCC tools but overlapping in effect*.

**INFERENCE.** Free Fly is a parameter reader/editor for the flight controller
reached over USB, and reaches region state by writing FC parameters rather
than by issuing FCC command sequences. That makes it **mechanism-disjoint from
the FCC tools while overlapping in effect**: neither "it is an FCC tool" nor
"it is a harmless parameter browser" survives the evidence. The precise
remaining question — whether a `ce_country_type` write actually takes — is
unanswerable without hardware and is carried into Stage 7 and
`docs/HARDWARE_TEST_PLAN.md`.