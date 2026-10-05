# References

Public projects and sources used during this research, pinned so that any claim
can be re-checked.

## Scope of use — read this first

**Every project below was used for comparison, citation, or as a control. No
source code from any of them was incorporated into this repository.**

The distinction matters and is easy to blur:

| | Meaning |
|---|---|
| **"used for comparison/reference"** | Cloned, read, quoted minimally with attribution, and cited. **No code taken.** |
| **"source code incorporated"** | Copy-pasted, adapted, transliterated, or vendored. |

**Nothing in this repository falls into the second category.** `research/flylib`
was written from observed protocol behaviour in the analysed sample, and its
constants were verified by independent means — the CRC polynomials by brute force
against the sample's own embedded tables, the header layout by golden vectors
derived field-by-field. See [`docs/LICENSING.md`](docs/LICENSING.md) for the
full provenance audit.

---

## Public projects

### doesthings/FreeFCC
- **URL** — https://github.com/doesthings/FreeFCC
- **Pinned commit** — `597157bd5212`
- **Licence** — AGPL-3.0
- **Used for** — comparison. Its 21-frame `fcc.json` profile is byte-identical to
  NLD FCC's; its 4-frame `fcc_keepalive.json` matches NLD's keepalive 4/4.
- **Cited for** — TCP 127.0.0.1:40009 transport
  (`app/src/main/java/com/freefcc/app/DumlTransport.kt:15,203`); port 40007 for
  the LED path (`FccViewModel.kt:596`).

### doesthings/FreeFCC-USB
- **URL** — https://github.com/doesthings/FreeFCC-USB
- **Pinned commit** — `55da2d3bc6c5`
- **Licence** — AGPL-3.0
- **Used for** — comparison; second carrier of the identical 21-frame profile.
- **Cited for** — USB host transport (`app/src/main/java/com/freefcc/n1/DumplTransport.kt:8-9`);
  the AUTOTEST bracket assertion in
  `app/src/test/java/com/freefcc/n1/DumplBuilderTest.kt:201`.

### M4TH1EU/DJI-FCC-HACK
- **URL** — https://github.com/M4TH1EU/DJI-FCC-HACK
- **Pinned commit** — `84f149f58a20`
- **Licence** — GPL-3.0
- **Used for** — comparison. Shares **no** profile data with the above.
- **Cited for** — a different transport entirely: USB CDC-ACM serial at
  `0x2CA3:0x1020` (`app/src/main/java/ch/mathieubroillet/djiffchack/MainActivity.kt:143`,
  `addProduct(11427, 4128, CdcAcmSerialDriver::class.java)`).

### andreapianidev/DJI-FCC-Unlock-iOS
- **URL** — https://github.com/andreapianidev/DJI-FCC-Unlock-iOS
- **Pinned commit** — `5ef860adafd1`
- **Licence** — **PolyForm Noncommercial 1.0.0.** Source-available but **not OSI
  open source**. Treated accordingly throughout: read and compared, never
  described as "open source", and redistribution constraints noted.
- **Used for** — comparison; carries a **22-frame divergent fork** of the FCC
  profile (inserts `03/f9 9ad152ae01` at position 3; different channel
  payloads).
- **Cited for** — MFi ExternalAccessory transport
  (`FreeFCC/App/AboutPage.swift:149`).

### o-gs/dji-firmware-tools
- **URL** — https://github.com/o-gs/dji-firmware-tools
- **Pinned commit** — `195692263c26`
- **Licence** — GPL-3.0
- **Used for** — comparison and protocol reference. Also the most likely origin
  of shared protocol knowledge in this ecosystem.
- **Cited for** — authoritative `cmdSet` table (`comm_dissector/dji-dumlv1-proto.lua:83-110`);
  CRC-8/CRC-16 seed documentation; the device-type enumeration.

### djiparam (lmdegreeds)
- **URL** — https://github.com/lmdegreeds/djiparam
- **Pinned commit** — `1b396b1a0ade`
- **Licence** — MIT
- **Used for** — comparison, and specifically as the **control** in the lineage
  assessment.
- **Why it matters** — `src/com/djiparam/Duml.java` independently contains
  `crc8` init `0x77`, `crc16` init `0x3692`, the command ids `0xE0`/`0xE1`, and
  the literal field name `unknown1`. That is what demotes every "shared"
  marker between Free Fly and Drone-Hacks to public protocol knowledge, and holds
  `DIRECT_CODE_COPY_EVIDENCE` at **NONE**.
- **Cited for** — the 2017 metadata reply layout, which nothing else here
  documents: `status:u16, table:u16, index:u16, type_id:u16, size:u16,
  def[10:14], min[14:18], max[18:22], name\0`.

---

## Vendor sources

Recorded as research evidence. None of these artefacts is redistributed here,
and **no vendor endpoint was contacted**.

| Source | What was obtained | How |
|---|---|---|
| `dl.djifcc.app` | 18 APKs including **stock DJI Fly** baselines | Public download centre, no purchase, no login |
| DJI CDN (`service-adhoc.dji.com` → `terra-2-g.djicdn.com`) | `DJIFly-1.21.12.1030.apk`, versionCode **3131451** — a versionCode-exact stock match for the patched build | DJI's own published download page |
| `redfly.app` | Product catalogue and filenames only | Read from the site's own JS bundle |
| `drone-hacks.com`, `account-api.dji.com`, `cloud.drone-hacks.com` | **Endpoint names only**, extracted from static analysis | Not contacted |

**Stock DJI Fly** is DJI's own software and remains subject to its licence. It is
used here as a comparison baseline and is **not redistributed**, consistent with
`docs/LICENSING.md`.

---

## Analysed samples

Identity records — SHA-256, size, acquisition source and date, metadata
confidence — are held in the gitignored `research/corpus/registry.json`, produced
by `tools/corpus_registry.py`.

The primary sample is identified here by hash only:

```
FF_v_1_00.apk   a6dc898ddcec0e9e13ab9c270835faea8a6d7961e7012e534361cdec0b9894ee
com.dronehacks.app  version 1.0
```

See [`docs/README.md`](docs/README.md) for how to supply your own legally
obtained copy locally.

---

## A provenance caution

During GitHub discovery, a repository **impersonating `doesthings/FreeFCC` by
name** was found carrying a 489 KB `.zip` inside `src/main/java/`. It was not
cloned and its payload was not retrieved.

Treat any FreeFCC fork of unknown provenance as suspect. The pins above are the
ones this project actually analysed.
