# Free Fly's write path, end to end

Resolves the question raised by `CMD_FC_PARAM_WRITE_2015` having zero call
sites: **is Free Fly's write functionality reachable, does it use a different
path, or is it unfinished dead code?**

**Answer: write functionality is fully reachable and fully live — but only
through the 2017 protocol. `writeParamValue2015` is not an alternative path; it
is simply never referenced.**

---

## 1. The live path

Traced through the decoded smali, bottom-up and top-down.

```
EditParamDialog confirm            MainScreenKt.smali:7979
  └─ MainViewModel.setParameter(ID)V            MainViewModel.smali:1953
      └─ MainViewModel$setParameter$1:439
          └─ DroneRepository.writeParameter(DroneParameter)      DroneRepository.smali:12151
              ├─ unlock gate      ── false ⇒ RepoResult.Failure("Unlock failed before write")
              ├─ DroneParameter.getCurrentValue()   : Double
              ├─ DroneParameter.getTypeId()         : ParamType
              ├─ DroneRepository.encodeValue(ParamType, Double) : ByteArray
              ├─ DroneParameter.getTableNo()        : Int
              ├─ DroneParameter.getParamIndex()     : Int
              └─ DroneCommands.writeParamValue2017(tableNo, paramIndex, valueBytes)
                                                        DroneRepository.smali:12345
```

**FACT.** `DroneCommands.writeParamValue2017` is invoked from exactly **one**
place in the entire APK: `DroneRepository.writeParameter` at line 12345.

**FACT.** `DroneRepository.writeParameter` contains **zero** occurrences of the
string `2015` and zero references to `writeParamValue2015`. There is no protocol
flag, no version branch, no fallback — the 2017 builder is called
unconditionally.

**FACT.** The entry point is a real user gesture: `MainScreenKt:7979` is inside
the Compose `EditParamDialog` confirm action. It is not a background task or a
hidden developer affordance.

## 2. Two more entry points into the same write

**FACT.** Two other `DroneRepository` methods call `writeParameter`:

| Caller | Line |
|---|---|
| `writeChangedParameters` (method at 11129) | 11383 |
| `writeDefaultValues` (method at 11699) | 11908 |

So the three ways to reach the wire are: a single edited parameter, a batch of
changed parameters, and a batch of defaults restored. All three converge on
`writeParameter` and therefore on the 2017 builder.

## 3. The unlock gate

**FACT.** `writeParameter` begins by obtaining a `Boolean`. If it is false the
method returns:

```
RepoResult.Failure("Unlock failed before write")
```

and **no frame is transmitted**. The encoding step is only reached after the
gate passes.

**INFERENCE.** The gate is `doUnlockForWrite` (method at `DroneRepository:997`),
whose own body carries only the strings `"pkt"` and `"<unused var>"` — it is a
thin coroutine that assembles a request and collects a reply, with the actual
unlock command one level up.

**INFERENCE.** `unlock` (public, method at 10087) drives
`DroneCommands.assistantUnlock` — `cmdSet 3 / cmdId 0xDF`, payload
`01 00 00 00`, `ACK_AFTER_EXEC`. So the write precondition is a single
`assistantUnlock` exchange, and a failed unlock is reported as a typed
`RepoResult.Failure` rather than as an exception.

**INFERENCE.** The unlock is applied **per write**, not once per session: the
gate sits inside `writeParameter`, which every batch entry also passes through.
For a batch write that implies one unlock round-trip per parameter. Whether the
app caches the unlocked state across the batch was not established — `writeParameter`
does not read any unlocked flag, so on the evidence here it does not.

## 4. What is actually dead

| Builder | cmdSet / cmdId | Call sites | Status |
|---|---|---|---|
| `writeParamValue2017` | FC / `0xE3` | 1 (from `writeParameter`) | **live** |
| `writeParamValue2015` | FC / `0xF9` | **0** | dead |
| `readParamValue2017` | FC / `0xE2` | 3 | live |
| `readParamValue2015` | FC / `0xF8` | 1, from dead `readAll2015` | dead |
| `getParamInfo2017` | FC / `0xE1` | 1 | live |
| `getParamInfo2015` | FC / `0xF0` | **0** | dead |
| `getParamInfoByIndex2015` | FC / `0xF0` | 1, from dead `readAll2015` | dead |
| `getTableAttribs2017` | FC / `0xE0` | 1 | live |
| `assistantUnlock` | FC / `0xDF` | 2 | live |
| `versionInquiry`, `versionInquiryTo` | COMMON / `0x01` | 1 each | live |
| `getCfgFileChunk` | COMMON / `0x4F` | 1 | live |
| `replyRegAck`, `replyRegDev` | COMMON / `0x82`, `0x81` | 1 each | live |

**FACT.** Every value field in `DroneParameter` is a primitive Kotlin `Double`:
`currentValue:D`, `defaultValue:D`, `maxValue:D`, `minValue:D`
(`DroneParameter.smali:81-87`, getters at 601-628), while `paramIndex` and
`tableNo` are `I` and `typeId` is `ParamType`. Free Fly's parameter model is
double-precision throughout, on both the read and the write side. A 64-bit
integer parameter cannot round-trip exactly through this app, and
`flylib.params` deliberately diverges by returning the exact integer and
raising `lossy` instead.

**INFERENCE.** Every dead builder is 2015. The pattern is consistent with the
2015 protocol having been implemented and then abandoned during development,
with the call sites removed but the builders left in the source — which is why
they survive into a debug build with no obfuscation.

**INFERENCE.** This is not "unfinished write support". Writes work. What is
missing is the 2015 half of a dual-protocol implementation, and nothing in the
reachable code selects it.

## 5. Consequence for the comparative picture

`cmdSet 3 / cmdId 0xF9` — the command NLD's FCC sequence uses six times, and the
one the public corpus calls "Write Param By Hash" — is **present but unreachable**
in Free Fly. Free Fly's only reachable parameter write is `cmdSet 3 / cmdId 0xE3`
with a `(table, index, reserved, index, value)` payload.

**INFERENCE.** In the analysed build, Free Fly cannot apply the hashed parameter
writes that NLD's FCC sequence depends on, even though it contains the builder
for them. That is a capability difference between the two tools, not an
implementation difference — a statement about these two applications, not about
what the flight controller or any other client could do.

## 6. Not established

- Whether `writeParameter` succeeds against real firmware. The unlock gate is a
  precondition; what the flight controller does with a `0xE3` write, and whether
  it persists, needs hardware — see `docs/HARDWARE_TEST_PLAN.md`.
- Whether a batch write re-unlocks per parameter or reuses state across the
  batch (see the inference note in §3).