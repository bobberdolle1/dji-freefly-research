# Free Fly 1.0 — the DUML implementation, exactly

Recovered from `work/apktool/decoded/smali_classes8/com/dronehacks/app/data/protocol/`
— `DumlBuilder.smali`, `DumlParser.smali`, `DumlConstants.smali`,
`DumlPacket.smali`, `DumlHeader.smali`. All five share
`.source "DumlPacket.kt"`, so one Kotlin file produced the whole protocol layer.

Every constant here is checked by `tests/test_duml.py` against the APK's own
tables. The clean-room implementation is `research/flylib/`.

---

## 1. Frame layout

`DumlBuilder.buildPacket` computes `total = payload.size + 0x0b + 2`, i.e.
**11 header bytes + payload + 2 CRC bytes**.

| Offset | Size | Field | Encoding |
|---|---|---|---|
| 0 | 1 | magic | `0x55` |
| 1 | 2 | `verLength` | uint16 **LE** = `(version << 10) \| totalLength`, `totalLength` masked to `0x3FF` |
| 3 | 1 | header CRC-8 | over bytes `[0, 3)` |
| 4 | 1 | sender | `(senderIndex & 7) << 5 \| (senderType & 0x1F)` |
| 5 | 1 | receiver | `(receiverIndex & 7) << 5 \| (receiverType & 0x1F)` |
| 6 | 2 | sequence | uint16 **LE** |
| 8 | 1 | `cmdTypeData` | `(packetType & 1) << 7 \| (ackType & 3) << 5` |
| 9 | 1 | `cmdSet` | |
| 10 | 1 | `cmdId` | |
| 11 | N | payload | `total − 13` bytes |
| N−2 | 2 | frame CRC-16 | uint16 **LE**, over bytes `[0, total − 2)` |

**The header is 11 bytes, not 13.** 13 is the *minimum frame size* — 11 + 0
payload + 2 CRC — and is the constant the parser compares the buffer against.
Conflating the two is an easy 2-byte error that still round-trips cleanly
because encoder and decoder share the mistake; `HEADER_SIZE` (11) and
`MIN_FRAME_SIZE` (13) are therefore named separately in `flylib.packet`.

**FACT.** Version is emitted as `1`: `verLength = (total & 0x3FF) | 0x400`.
The parser reads only `verLength & 0x3FF` and never inspects the version field.

**FACT.** The frame CRC is stored **little-endian** — low byte at `total−2`,
high byte at `total−1`. The builder and parser agree: the parser reassembles
`(data[total−1] << 8) | data[total−2]`, which is `high<<8 | low`. There is no
byte-order asymmetry, contrary to what the two snippets look like in isolation.

## 2. Checksums

### crc8

| Property | Value |
|---|---|
| Algorithm | reflected (LSB-first) table CRC |
| Polynomial | `0x8C` |
| Initial value | `0x77` |
| Coverage | bytes `[0, 3)` — magic and the length word |

### crc16

| Property | Value |
|---|---|
| Algorithm | standard LSB-first reflected CRC-16 |
| Polynomial | `0x1021`, table reflected to `0x8408` |
| Initial value | `0x3692` |
| Final XOR | `0x0000` |
| Coverage | bytes `[0, total − 2)` |

**On "non-standard".** The APK's update reads

```
t = crc >> 8;  crc = table[(byte ^ crc) & 0xFF] ^ t
```

which is the ordinary reflected step `crc = (crc >> 8) ^ table[(crc ^ byte) &
0xFF]` with the operands reordered. The **algorithm** is standard; only the
**parameters** are DJI's. In catalogue terms: CRC-16/X-25 with a non-standard
initial value. `tests/test_duml.py` asserts the step equivalence over 20,000
random (register, byte) pairs rather than leaving it as prose.

**How the polynomials were established, not assumed.** `DumlBuilder.<clinit>`
embeds two 256-entry tables via `fill-array-data`. Those tables were extracted
from the smali and matched by brute force against every reflected table for all
256 (crc8) and all 65,536 (crc16) polynomials — a unique match for `0x8C` and
`0x8408` respectively. `test_crc8_table_matches_the_apk` and
`test_crc16_table_matches_the_apk` then compare the generated tables to the
extracted ones element by element, so the derivation is evidence rather than
assertion.

An independent line of agreement: a killed comparative worker, working from the
public `o-gs/dji-firmware-tools` corpus rather than from this APK, reached the
same characterisation (X-25, init `0x3692`, xorout 0) and reported
byte-identical tables.

## 3. Constants

From `DumlConstants.smali`:

**Device types** — `DEV_ANY` 0, `DEV_CAMERA` 1, `DEV_APP` 2, `DEV_FC` 3,
`DEV_GIMBAL` 4, `DEV_CENTER` 5, `DEV_RC` 6, `DEV_PC` 10.

**ACK** — `ACK_NO_ACK` 0, `ACK_BEFORE_EXEC` 1, `ACK_AFTER_EXEC` 2.

**Encryption** — `ENC_NO_ENC` 0, declared but never used by any builder.

**Packet type** — `PKT_REQUEST` 0, `PKT_RESPONSE` 1.

**Command sets** — `CMD_SET_COMMON` 0, `CMD_SET_SPECIAL` 1, `CMD_SET_FC` 3.
Only two are actually used: 9 builders on `CMD_SET_FC` and 5 on
`CMD_SET_COMMON`. **`CMD_SET_SPECIAL` is declared but used by no builder.**

**Command ids** — `CMD_FC_ASSISTANT_UNLOCK` −33 (`0xDF`),
`CMD_FC_PARAM_TABLE_ATTRS_2017` −32 (`0xE0`), `CMD_FC_PARAM_INFO_2017` −31
(`0xE1`), `CMD_FC_PARAM_READ_2017` −30 (`0xE2`), `CMD_FC_PARAM_WRITE_2017` −29
(`0xE3`), `CMD_FC_PARAM_INFO_2015` −16 (`0xF0`), `CMD_FC_PARAM_INFO_HASH_2015`
−9 (`0xF7`), `CMD_FC_PARAM_READ_2015` −8 (`0xF8`), `CMD_FC_PARAM_WRITE_2015` −7
(`0xF9`).

**Cross-check.** `0xF9` on cmdSet 3 was independently identified by the
comparative corpus worker as "Write Param By Hash" — Free Fly's
`CMD_FC_PARAM_WRITE_2015`. The two agree from opposite directions.

**Sequence numbers.** `nextSeq()` returns the pre-increment value of a static
counter initialised to `1`, so the first frame carries sequence 1. There is no
wrap handling.

## 4. Parser behaviour

`DumlParser.parse` is **single-shot with no resynchronisation**. It returns a
failed `ParseResult` — never an exception, never a resync — for:

| Condition | Threshold |
|---|---|
| buffer too short | `size < 0x0D` (13) |
| bad magic | `data[0] != 0x55` |
| declared length beyond buffer | `size < (verLength & 0x3FF)` |
| header CRC mismatch | `data[3] != crc8(data, 0, 3)` |
| frame CRC mismatch | recomputed ≠ stored |

On success it returns `(cmdSet, cmdId, seqNum, packetType, payload, srcByte)`.
**Note what is dropped:** the receiver device byte, the ack type, and the
version are read and discarded. A parser that needs them must extend the
`ParseResult`.

**The app's reader does its own framing.** `UsbSerialManager` accumulates into
an `incomingBuffer` and only assembles once at least 3 bytes are available
(enough for the magic and the length word). So the *absence* of resync is a
property of `DumlParser`, not of the app's read path as a whole.
`flylib.StreamParser` adds resynchronisation because a live serial link needs
it; the divergence is documented in `research/flylib/parser.py`.

**Resync caveat.** With length-anchored framing and no outer envelope, a
corrupted payload containing a second `0x55` can make a framer lock onto a
false boundary. That is inherent to the format, and `flylib` reports it through
`FramerStats.resyncs` rather than hiding it.

## 5. Parameter-name hashing

`DroneCommands.paramHash(name)`:

```
hash = 0
for byte in name.encode('US-ASCII'):
    hash = ((hash << 8) + byte) % 0xFFFFFFFB
return hash & 0xFFFFFFFF
```

Modulus `0xFFFFFFFB` = 2³² − 5. This is the classic DJI hash used by the
2015 name-addressed protocol; Free Fly implements it over US-ASCII bytes.

Golden vectors: `""` → 0, `"gps_lon"` → 1634836909, `"FlycCoe"` → 1688440258.

**FACT.** `paramHash` is only used by the 2015 builders, and every 2015 read
builder is dead code. See `docs/COMMAND_MAP.md` — the live protocol is
index-addressed and never hashes a name.

## 6. What is implemented and what is not

The protocol layer has **no encryption** — `ENC_NO_ENC` is declared and never
used, and no builder or parser path references it. There is no fragmentation,
reassembly, or flow control at this layer.

| Field | Encoded | Parsed back |
|---|---|---|
| magic | ✅ | ✅ |
| version | ✅ (always 1) | read, discarded |
| totalLength | ✅ | ✅ |
| header CRC-8 | ✅ | ✅ |
| sender | ✅ | type+index recovered by the caller |
| receiver | ✅ | ❌ discarded |
| sequence | ✅ | ✅ |
| packetType | ✅ | ✅ |
| ackType | ✅ | ❌ discarded |
| cmdSet | ✅ | ✅ |
| cmdId | ✅ | ✅ |
| payload | ✅ | ✅ |
| frame CRC-16 | ✅ | ✅ |

## 7. Golden vectors

`tests/test_duml.py` pins 13 frames, each checked field by field against the
smali rather than captured from the implementation. Two of them:

```
assistantUnlock  551104922a0301004003df01000000b2a0
  55 magic | 1104 verLength=0x411 (v1, total 17) | 92 hdrCRC
  2a DEV_PC:1 | 03 DEV_FC:0 | 0100 seq=1 | 40 ack=2,pkt=0
  03 cmdSet FC | df cmdId -33 | 01000000 payload | b2a0 CRC16

versionInquiry   550d04332a030100400001f05e
  55 magic | 0d04 verLength=0x40D (v1, total 13) | 33 hdrCRC
  2a DEV_PC:1 | 03 DEV_FC:0 | 0100 seq=1 | 40 ack=2,pkt=0
  00 cmdSet COMMON | 01 cmdId 1 | (no payload) | f05e CRC16
```

Reproduce with:

```
python -m pytest tests/test_duml.py -q
```