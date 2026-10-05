# Transport matrix

How each project actually reaches the aircraft. Every row cites a file, a
manifest, or a binary observation — never a README.

---

## 1. The two paths, and the confusion between them

```mermaid
flowchart LR
    subgraph Phone["phone / laptop"]
        A1[Free Fly] --- A2[Drone-Hacks via USB]
        A3[FreeFCC] --- A4[djiparam]
        A5[NLD FCC]
    end
    subgraph RC["RC-N1/N2/N3 or smart controller"]
        B1["DJI app / local service"]
        B2[DUSS / RCLink]
    end
    subgraph Aircraft["aircraft"]
        C[flight controller]
        R[radio module]
    end
    A1 -->|raw USB bulk| C
    A2 -->|USB serial (CDC-ACM or pyserial)| C
    A3 -->|TCP 127.0.0.1:40009| B1
    A4 -->|TCP 40008 in / 40007 out| B1
    A5 -->|TCP 40009 / 40007| B1
    B1 --> B2 --> C
    B1 --> R
```

The distinction that matters: **DUML is the framing on both sides of the link.**
The 21-frame FCC sequence is spoken *through* the controller's local service, not
directly to the aircraft over USB. Free Fly skips the middle entirely.

## 2. Matrix

| Project | Class | Path | Evidence |
|---|---|---|---|
| **Free Fly 1.0** | Android | **USB bulk**, VID `0x2CA3`, pids `0x10`/`0x18`/`0x20`. Raw bulk, no CDC-ACM. | `res/xml/device_filter.xml`; `UsbSerialManager` walks interfaces for bulk IN+OUT and `claimInterface(iface, force=true)`; zero line-coding/baud setup |
| **Drone-Hacks 1.48** | Windows desktop | **USB serial**, pyserial | `serial/*` in the PyInstaller TOC; `baud` and `port` in `core/dji.pyc` |
| **DJI-FCC-HACK** | Android | **USB CDC-ACM serial**, `0x2CA3:0x1020` | `MainActivity.kt:143` `addProduct(11427, 4128, CdcAcmSerialDriver::class.java)` |
| **FreeFCC** | Android | **TCP 127.0.0.1:40009** (40007 for LED) | `DumlTransport.kt:15,203`; `FccViewModel.kt:596` |
| **FreeFCC-USB** | Android | **USB host** | `DumplTransport.kt:8-9` imports `UsbDevice`, `UsbDeviceConnection` |
| **djiparam** | Java | **TCP 40008 inject / 40007 read** | `Duml.java:16` |
| **DJI-FCC-Unlock-iOS** | iOS | **MFi ExternalAccessory** | `AboutPage.swift:149` `InfoRow(label: "Transport", value: "MFi ExternalAccessory")` |
| **NLD FCC** | Android | **TCP 40009 / 40007**, native | profile prose; `libnld-core.so` binds `/duss/mb/0x1e00`, connects `/duss/mb/0x205` |
| **DJIFCC** | Android | DJI's own stack, **native JNI** | patched app inherits `libsdk_jni.so` (81.7–88.3 MB), the sole carrier of `DUML`/`LogicLink` symbols |
| **RedFly** | ? | **unknown** | no artifact acquired; vendor-stated "DJI Fly mod", so presumably DJI's own stack |
| **dji-firmware-tools** | desktop | **none** — offline firmware tooling | — |

## 3. RCLink presence

| Project | RCLink |
|---|---|
| NLD FCC | **yes** — `NLD-RCLINK-RX` / `NLD-RCLINK-TX`, Kotlin `NativeRcLinkRxSink` |
| DJI-FCC-Unlock-iOS | **yes** — MFi ExternalAccessory session |
| DJIFCC | **inherited natively**, not as `com.dji.logiclink` Java classes |
| Free Fly | **no** — zero occurrences |
| Drone-Hacks | **no** — zero occurrences across all 25 modules |
| FreeFCC / djiparam / DJI-FCC-HACK | **no** (TCP/USB directly to the DUML endpoint) |

**FACT.** `com.dji.logiclink` and `com.dji.protocol` are **absent** from both
stock and patched DJI Fly's DEX. Those are legacy DJI MSDK v4 namespaces; modern
DJI Fly keeps the protocol layer in `libsdk_jni.so` instead. A search that only
looked for those Java namespaces would wrongly conclude modern DJI Fly has no
DUML layer at all.

## 4. Connection handshakes

| Project | Handshake |
|---|---|
| Free Fly | writes the single byte **`0x30`, five times**, to the OUT endpoint, 200 ms timeout. Reads 512 bytes / 2000 ms; writes 2000 ms |
| NLD FCC | **DUSS**: binds abstract socket `/duss/mb/0x1e00`, connects `/duss/mb/0x205`, persistent fd, one reopen on send failure. Plus a registration exchange (`replyRegAck` / `replyRegDev`) |
| Drone-Hacks | pyserial open; registration handled in-app |
| FreeFCC / djiparam | connect to the local TCP proxy; no USB involvement |

## 5. What the transport choice implies

**INFERENCE.**

- **USB-direct tools** (Free Fly, Drone-Hacks, DJI-FCC-HACK, FreeFCC-USB) need the
  aircraft or a controller exposed as a USB device. They work at the bench.
- **TCP-through-the-controller tools** (FreeFCC, djiparam, NLD) need the
  controller's own local service running — they are closer to the in-field
  experience of a patched DJI app.
- **Patched-app tools** (DJIFCC, RedFly) inherit DJI's entire transport, which is
  why their DUML behaviour is not independently observable as app code: it lives
  in an 88 MB proprietary `.so`.

**INFERENCE.** This is the mechanism-level reason Free Fly cannot use the FCC
command sequence even if it wanted to: that sequence addresses the **radio
module** through the controller's service, and Free Fly has no path to it. It
reaches only the flight controller, over a bulk endpoint, with the 2017 parameter
protocol.
