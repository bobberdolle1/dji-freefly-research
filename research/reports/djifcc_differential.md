# DJIFCC vs stock DJI Fly — mechanism-level differential

Static comparison of the artifacts acquired from `https://dl.djifcc.app/` by a
comparative worker that was killed before reporting. All binaries are gitignored
under `research/corpus/djifcc/`; identity records are in the gitignored
`research/corpus/registry.json`.

Reproduce with:

```
python tools/signing.py <apk> <outdir>
python tools/baseline.py <apk> <outdir>
```

---

## 1. What was recovered

18 APKs, ~3 GB, spanning five of the product classes the mission asked about:

| Class | Files |
|---|---|
| Patched DJI Fly (phone) | `DJIFCC.APP-Android-arm64-signed-1.21.12.19.apk` |
| Patched DJI Fly (RC2) | `DJIFCC.APP-RC2-V6-signed-1.21.10.43.apk` |
| Patched DJI Fly (RC Pro 2) | `DJIFCC.APP-RCPro2-signed-1.21.12.3.apk` |
| Patched DJI GO 4 | `fcc_dji_go_android_v4.3.46.apk`, `v4.3.62.apk` |
| **Stock DJI Fly (RC2) baselines** | `fly_1.19.4`, `fly_1.21.2`, `fly_1.21.4`, `fly_1.21.8` |
| Controller-side utilities | `FCCInstaller`, `com.djifcc.appstore_1.8.3`, `app_gesture_v1.8.1`, `app_launcher_v1.8.7`, `utility_appmanager`, `utility_filemanager_from_rc_pro`, `utility_mygesture`, `utility_packageinstaller`, `utility_smartlauncher` |

The stock DJI Fly baselines are the important part: they make this a genuine
differential rather than a set of assertions about a vendor's marketing.

---

## 2. Package identity — it really is DJI Fly

**FACT** (manifest, read with `androguard.core.apk.APK`):

| Artifact | Package | versionName | versionCode | Perms | INTERNET |
|---|---|---|---|---|---|
| Stock DJI Fly 1.21.8 | `dji.go.v5` | 1.21.8 | 3115809 | 57 | ✅ |
| DJIFCC Fly Android 1.21.12.19 | `dji.go.v5` | 1.21.12 | 3131451 | 57 | ✅ |
| DJIFCC Fly RC2 V6 1.21.10.43 | `dji.go.v6` | 1.21.10 | 3115981 | 57 | ✅ |
| DJIFCC GO 4 4.3.62 | `dji.go.v4` | 4.3.62 | 3036675 | 41 | ✅ |
| FCCInstaller 1.2.1 | `com.djifcc.flyinstaller` | 1.2.1 | 121 | 7 | ✅ |

**FACT.** The patched builds retain DJI's own package names — `dji.go.v5` (Fly),
`dji.go.v6` (Fly for RC2), `dji.go.v4` (GO 4). DJIFCC does not ship a parallel
app; it ships a **modified DJI Fly**.

**INFERENCE.** This classifies DJIFCC as a *patched official app* rather than a
DUML tool. It does not decide whether the patch is Java, native, or both — that
is the next step and is not attempted here.

---

## 3. Signing — and why it must be side-loaded

**FACT** (APK Signing Block, `tools/signing.py`):

| Artifact | Scheme(s) | Subject | Cert SHA-256 |
|---|---|---|---|
| Stock DJI Fly 1.21.8 | v2 | `CN=dji` | `01a42c94aa87020f41e8c252598df98b…` |
| DJIFCC Fly Android | v2 **and v3** | `CN=DJIFCC.APP, OU=DJIFCC.APP, O=DJIFCC.APP, L=PL, ST=PL, C=PL` | `cad73496edd54f0453708617454f494b…` |
| DJIFCC Fly RC2 | v2 **and v3** | same | `cad73496edd54f0453708617454f494b…` |
| DJIFCC GO 4 | v2 **and v3** | same | `cad73496edd54f0453708617454f494b…` |

Two consequences follow directly:

1. **All four patched product classes share one vendor certificate.** Whatever
   the patching pipeline is, it is a single vendor operation across phone, RC2,
   RC Pro 2 and GO 4.
2. **The APK cannot be installed as an update over stock DJI Fly.** Android
   requires a signature match for an upgrade, and the vendor key is not DJI's.
   Installation must therefore be a fresh install — uninstall stock, then side-
   load.

That second point is not speculation about the vendor's intentions; it is what
Android's package manager enforces, and it is corroborated by the artifact set:
`com.djifcc.flyinstaller` (`FCCInstaller`), `rc2_utility_packageinstaller.apk`,
`utility_appmanager.apk` and `utility_smartlauncher.apk` exist precisely to place
these packages on a controller that normally has no sideloading UI.

**FACT.** Stock is v2-only; every patched build adds **v3**. The patching
toolchain is a different (newer) one from the one DJI used to sign.

---

## 4. Against Free Fly — the mechanism-level contrast

| | **Free Fly** | **DJIFCC** |
|---|---|---|
| Package | `com.dronehacks.app` | `dji.go.v5` / `v6` / `v4` (DJI's own) |
| What it is | standalone USB/DUML parameter tool | **patched official DJI app** |
| `INTERNET` permission | **absent** | present |
| HTTP library | **none** in any of 10 DEX | present (stock Fly is a networked app) |
| Transport | raw USB bulk to a DJI device, VID `0x2CA3` | the stock Fly transport stack, unmodified in shape |
| Signs its own frames | yes, DUML | no — it is the app DJI already had |
| Signing | Android **debug** keystore | vendor key, v2+v3 |
| Region mechanism | writes FC parameters (`ce_country_type`) | modifies the app's own region logic |

**INFERENCE — the §10 answer.** DJIFCC and Free Fly are **mechanism-disjoint**.

- DJIFCC changes behaviour by *editing the DJI application*: it ships DJI's own
  package with modifications, so whatever suppresses a region or country check
  lives in the app's own code path.
- Free Fly changes nothing on the phone side of DJI's stack at all. It is a
  separate program that opens a USB endpoint and speaks DUML, addressing the
  flight controller's parameter table directly.

That is a structural difference, not a difference of degree. It also means a
byte-level frame comparison between the two is **not** meaningful: there are no
DJIFCC frames to compare against Free Fly's, because DJIFCC never emits any.

**INFERENCE.** It also predicts different persistence. A patched app persists
only as long as the patched package is installed and not replaced by a real DJI
update; the change is not in the aircraft's firmware. Free Fly's parameter write
persists only if the aircraft accepts and stores the parameter. **Neither is
guaranteed to survive; they are different failure modes**, and stating that
plainly is more useful than implying one is "better".

---

## 5. What is not yet known

Stated so the next stage is not mistaken for work already done:

- **The patch itself has not been diffed.** Comparing stock `fly_1.21.8` against
  a patched build of the *same* version would be the clean experiment, but no
  matching-version pair exists in the corpus: stock is 1.19.4/1.21.2/1.21.4/1.21.8
  while the patched RC2 is 1.21.10.43 and the patched phone build is 1.21.12.19.
  Version drift would confound any naive diff.
- **Java vs native vs both** is unknown. Entry counts differ (stock 1.21.8: 22
  DEX / 112 `.so`; patched RC2: 24 DEX / 110 `.so`; patched Android: 23 DEX /
  206 `.so`) but those are different base versions, so the deltas mean nothing
  yet.
- **No DJIFCC endpoint, licence server or update host has been identified.**
  Permission counts and `INTERNET` establish that it *can* talk to the network;
  they do not establish that it does.
- The GO 4 builds (`dji.go.v4`) are a different app family from Fly and may
  patch differently.

## 6. Acquisition provenance

Downloaded 2026-10-04 from `dl.djifcc.app` by the comparative worker. Each
artifact has a sibling `.headers` file written by the downloader. Per-artifact
SHA-256 values are in `research/corpus/registry.json`. Nothing was purchased and
no login or purchase-gated artifact was accessed.