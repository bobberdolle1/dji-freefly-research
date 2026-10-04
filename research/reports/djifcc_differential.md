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
   Installation must therefore be a fresh install — uninstall stock, then
   side-load.

**FACT.** Stock is v2-only; every patched build adds **v3**. The patching
toolchain is a different (newer) one from the one DJI used to sign.

**Caution — certificate fields are not attribution.** The subject includes
`C=PL`. In a self-signed certificate every DN field is whatever the creator
typed into keytool, so this records a keystore-creation artifact and nothing
more. It is not evidence about the operator's location, nationality or
residency, and this project does not treat it as such.

---

## 4. Where the DUML actually lives — a corrected assumption

An earlier draft of this report assumed DJI Fly "speaks DUML via
`com.dji.protocol`/logiclink". **That premise was wrong**, and checking it
changed the transport picture materially.

**FACT.** Scanning every DEX in both stock `dji.go.v5` 1.21.8 and the patched
`dji.go.v5` 1.21.12.19 build:

| Needle | Stock DEX | Patched DEX |
|---|---|---|
| `com/dji/logiclink` | 0 | 0 |
| `com/dji/protocol` | 0 | 0 |
| `logiclink` | 2 | 3 |
| `Duml` | 0 | 3 |

**No `com.dji.logiclink` or `com.dji.protocol` class exists in either build.**
Those are the legacy DJI MSDK v4 namespaces, and modern DJI Fly does not ship
them.

**FACT.** The DUML/logiclink symbols are in **one native library**,
`libsdk_jni.so`, which is also by far the largest component:

| Build | Library | Size | `DUML` | `LogicLink` | `logiclink` |
|---|---|---|---|---|---|
| Stock 1.21.8 (armeabi-v7a) | `lib/armeabi-v7a/libsdk_jni.so` | 81,761,572 | 7 | 2 | 1 |
| Patched 1.21.12.19 (arm64-v8a) | `lib/arm64-v8a/libsdk_jni.so` | 88,346,048 | 7 | 2 | 1 |

**FACT.** The two `libsdk_jni.so` builds are **not** byte-identical — different
ABIs, different sizes, different SHA-256 (`821ec8c9…` vs `de470818…`). This was
checked specifically because the identical symbol counts invite the conclusion,
and it would have been wrong to assert identical binaries.

**INFERENCE.** The patched build retains DJI's native transport library, built
for a different ABI from a later base version. Same lineage, not same binary.

**Corrected transport comparison:**

| | Free Fly | DJIFCC |
|---|---|---|
| DUML implemented in | **its own Kotlin, in its own DEX** | **DJI's native `libsdk_jni.so`**, inherited unchanged in lineage |
| Path to the aircraft | raw USB bulk, VID `0x2CA3`, claimed directly | DJI's own app transport stack |
| Own protocol code to audit | yes, ~300 lines | no — it inherits DJI's |

So the advisory's *direction* holds — DJIFCC reaches DUML through DJI's stack
rather than implementing its own — but the mechanism is **native JNI**, not
Java MSDK classes. That is a more interesting and more accurate finding, and it
changes what needs auditing: with Free Fly the protocol code is readable in the
APK, whereas DJIFCC's protocol behaviour lives in an 88 MB proprietary `.so`.

## 5. Which artifacts can actually be differenced

**FACT.** Only one pair is package-matched:

| | Package | Version |
|---|---|---|
| Stock DJI Fly RC2 1.21.8 | `dji.go.v5` | 1.21.8 |
| DJIFCC Fly Android 1.21.12.19 | `dji.go.v5` | 1.21.12 |

**FACT.** The patched **RC2** build is `dji.go.v6`. **No stock `v6` exists in
the corpus**, so that build has no matched operand and must not be diffed
against a `v5` baseline. Likewise the patched GO 4 builds are `dji.go.v4`, a
different app family from Fly entirely.

**FACT — first-order differential on the matched pair.** Stock 1.21.8 has
**22 DEX** files; the patched 1.21.12.19 build has **23**. Native libraries go
from 112 (armeabi-v7a only) to 206 (arm64-v8a). The DEX delta is the cleanest
available signal for locating the patch, but it is confounded by the version
gap and by the ABI change.

**FACT — packaging lineage.** `DJIFCC.APP-Android-arm64-signed-1.21.12.19.apk`
and `DJIFCC.APP-RCPro2-signed-1.21.12.3.apk` are **byte-length identical**
(716,586,363) with **different SHA-256** (`d65c3608…` vs `d5a76d3b…`) and the
same DEX count (23).

**INFERENCE.** Equal length with differing content and an equal DEX count is
the signature of **one APK repackaged per target SKU**, not two independent
builds. Phone and RC Pro 2 likely share a single patched payload differing only
in SKU-identifying content.

## 6. The `rc2_utility_*` bundle is not DJIFCC's code

**FACT.** Package and signing analysis of the nine "utility" APKs:

**DJIFCC's own apps** — all signed with the same `cad73496…` /
`CN=DJIFCC.APP` certificate, all holding `INTERNET`:

| Package | Version | Perms |
|---|---|---|
| `com.djifcc.flyinstaller` | 1.2.1 | 7 |
| `com.djifcc.appstore` | 1.8.3 | 12 |
| `com.djifcc.gesture` | 1.8.1 | 8 |
| `com.djifcc.launcher` | 1.8.7 | 4 |

**Third-party or AOSP apps carried under `rc2_utility_*` — different signers:**

| Package | Version | Signer | INTERNET |
|---|---|---|---|
| `io.github.muntashirakon.AppManager` | 4.0.5 | `O=fdroid.org` (F-Droid's App Manager) | ✅ |
| `com.android.documentsui` | 0.20.12.23 | `O=DJI, C=CN` | ❌ |
| `com.android.packageinstaller` | 11 | `O=DJI, C=CN` | ❌ |
| `me.hisn.mygesture` | 6.353 | `CN=hisn, L=shanghai` | ❌ |
| `ginlemon.flowerfree` | 6.5 | `CN=vincenzo coluc, ST=Italy` | ✅ |

**INFERENCE.** The `rc2_utility_*` files are a **curated bundle of existing
third-party and AOSP software**, not DJIFCC's own code. They provide exactly
what a controller without a Play Store needs to install and manage packages:
an app manager, a file manager, a package installer, a launcher and a gesture
tool. This closes the "controller unlock/sideload tool" category of the product
taxonomy on its own, without needing to decompile any of them.

**FACT.** Two of them are signed **by DJI** (`O=DJI, C=CN`) — the AOSP system
`packageinstaller` and `documentsui`, shipped with DJI's platform signature.

**HYPOTHESIS.** Those two were most likely extracted from the aircraft/RC
firmware's own system partition rather than obtained from DJI or AOSP.
Distinguishing that requires checking whether the copies match the controller's
system image; it is not settled here.

**Licensing note.** Redistributing F-Droid's App Manager (GPL-3.0) and AOSP
system apps (Apache-2.0) inside a commercial bundle is a question this project
flags but does not opine on.

**Backend contrast.** `com.djifcc.appstore` holds `INTERNET` with 12
permissions: the patch **distribution** channel does have network access. Free
Fly has no INTERNET permission and no HTTP library at all, so it structurally
cannot. That is a real architectural difference between the two businesses,
not a stylistic one.


---

## 7. Against Free Fly — the mechanism-level contrast

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

## 8. What is not yet known

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
- **There is no Java-level DUML in the stock build either.** Since
  `com.dji.logiclink` / `com.dji.protocol` are absent from stock DJI Fly, a
  DEX-only diff cannot locate the protocol path — it is in an 81–88 MB
  proprietary `.so` that has not been disassembled here.
- **`libsdk_jni.so` is not byte-identical** between stock and patched
  (`821ec8c9…` vs `de470818…`): different ABI, size and hash. Identical
  `DUML`/`LogicLink` symbol counts indicate lineage, not an unchanged binary.
  Whether that library itself was modified is **unknown**.
- **The origin of the DJI-signed AOSP utilities**
  (`com.android.packageinstaller`, `com.android.documentsui`) is unresolved —
  firmware extraction versus redistribution cannot be distinguished without
  comparing against a controller system image.
- The nine utility APKs have been identified by package and signature but **not
  decompiled**; no claim is made about what they do beyond their identity and
  permission sets.

## 9. Acquisition provenance

Downloaded 2026-10-04 from `dl.djifcc.app` by the comparative worker. Each
artifact has a sibling `.headers` file written by the downloader. Per-artifact
SHA-256 values are in `research/corpus/registry.json`. Nothing was purchased and
no login or purchase-gated artifact was accessed.