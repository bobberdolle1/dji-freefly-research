# RedFly — research notes

Source: `https://redfly.app/`, read 2026-10-05. The site is a JavaScript-rendered
single-page app, so the catalog was recovered from the page's own bundle,
`/assets/app-f598545ff9.js` (456,101 bytes), which is what the mission
prescribes for such sites.

**No artifact was downloaded.** See §3 — the download endpoint is CSRF-gated and
session-bound, and no attempt was made to obtain the token or work around it.

---

## 1. What RedFly is

**FACT**, from the page's own metadata:

> "RedFly — мод DJI Fly для DJI RC 2. FCC, ATTI, офлайн-карты, калибровка
> подвеса и экспорт полётных записей. dev56 · build136."
>
> "DJI Fly mod: GPS / ATTI, FCC, offline maps and Wi-Fi video streaming. EN / RU."

**Classification: (A) patched official DJI Fly.** The vendor's own description
is "мод DJI Fly" / "DJI Fly mod". It is not a DUML utility, not a controller-local
tool, not a standalone parameter editor, and not a firmware patcher.

Feature set claimed: **FCC**, **ATTI**, offline maps, gimbal calibration, flight
log export, Wi-Fi video streaming.

## 2. The artifact catalog (from the bundle)

**FACT.** Filenames, versions and targets as published by the site:

| Artifact | Base DJI version | Target |
|---|---|---|
| `RedFly-1.21.10-dev-56-build-136-RC2-red-v5-final.apk` | 1.21.10 dev-56 build-136 | RC 2, `v5` |
| `RedFly-1.21.10-dev-56-build-136-RC2-red-v6-final.apk` | 1.21.10 dev-56 build-136 | RC 2, `v6` |
| `RedFly-1.21.12-build-156-Phone-RCPro-v5.apk` | 1.21.12 build-156 | Phone / RC Pro, `v5` |
| `RedFly-1.21.12-build-156-Phone-RCPro-v6.apk` | 1.21.12 build-156 | Phone / RC Pro, `v6` |

Adjacent products in the same catalog:

| Artifact | Notes |
|---|---|
| `Pilot-13.1.0.19-noAppGuard-coexist-r13.apk` | DJI **Pilot 2** 13.1.0.19, **`-noAppGuard`** |
| `RedPilot-17.3.1.4-noAppGuard-coexist-r4.apk` | **`-noAppGuard`** |
| `Pilot-Switch.apk` (Pilot Switch 2.4) | |
| `RC331-Root-ADB-Bundle.apk` / `RC331-ADB-Setup.exe` | root/ADB tooling for RC331 |
| `Fly-Network-ADB-Setup.exe` | ADB networking setup |
| `RC2_Unlock.zip` | controller unlock |
| `ADB-NOTICE.txt`, `SHA256SUMS.txt` | |

Distribution channels named on the site: `https://t.me/redflydjiapp` (Telegram),
`https://boosty.to/redfly` (paid subscription), and a YouTube link.

**Two observations that connect to the rest of this corpus:**

1. **The `v5` / `v6` split.** RedFly ships one APK per `dji.go.v5` / `dji.go.v6`
   package variant — **the same package split DJIFCC uses**. RedFly's
   `RedFly-1.21.12-build-156-Phone-RCPro-v5.apk` targets the same DJI Fly
   release (`1.21.12`) and the same package variant as the DJIFCC build analysed
   in `research/reports/djifcc_differential.md` (`dji.go.v5`, versionName 1.21.12,
   versionCode 3131451).

   **INFERENCE.** RedFly and DJIFCC converge on the same base release and the same
   package variants. That is consistent with a shared market and a shared target
   matrix. It is **not** evidence of shared tooling, a shared patch, or a shared
   author — it has not been tested.

2. **`-noAppGuard` is a named product variant.** This project's DJIFCC
   differential independently found that the patched DJIFCC build **omits**
   `libAppGuard.so`, `libAppGuard-x86.so` and `libdatajar.so` that stock DJI Fly
   ships. RedFly's own filenames advertise the same removal for its Pilot
   builds. **INFERENCE:** stripping DJI's integrity protection is a recognised
   technique in this product class, not a quirk of one vendor.

## 3. Why no artifact was acquired

**FACT.** The site's download flow, from the bundle:

```js
await t, e || await n();
const g = await fetch("/api/download", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-RF-CSRF": e },
  body: JSON.stringify({ file: l.dataset.file }),
  credentials: "same-origin"
});
```

Downloads are served by a **POST endpoint gated on an `X-RF-CSRF` token obtained
at runtime and bound to the session** (`credentials: "same-origin"`).

**FACT.** Direct paths are closed:

| URL | Result |
|---|---|
| `https://redfly.app/downloads/SHA256SUMS.txt` | **403 Forbidden** (nginx) |
| `https://app.lava.top/redfly/downloads/SHA256SUMS.txt` | anti-bot cloaking interstitial |
| `GET https://redfly.app/api/download` | **404** (endpoint is POST-only) |

**Decision.** The token exists to gate access. Fetching it, replaying the session,
or routing around the 403 would be circumventing an access control, and this
project does not do that. The mission also directs that a purchase-walled or
login-walled artifact be documented rather than obtained.

**Recorded for a future authorised pass:** the endpoint, the parameter name, the
header, the token-issuance call (`n()`), the artifact filenames, and the fact that
`SHA256SUMS.txt` is published alongside — so an operator with an account can
acquire and verify these without any reverse engineering at all.

## 4. Classification table

| Option | RedFly |
|---|---|
| A. Patched DJI Fly / GO4 | **YES** — vendor-stated "DJI Fly mod" |
| B. Standalone USB/DUML FCC utility | no |
| C. Controller-local utility | partially — `RC2_Unlock.zip`, `RC331-Root-ADB-Bundle`, `Pilot-Switch` are controller-side helpers shipped alongside |
| D. FC parameter editor | not claimed |
| E. Firmware modifier | not claimed |
| F. Hybrid | **plausible** — the Pilot/RedPilot/AppGuard-stripping and ADB components suggest more than a single patched Fly, but this is unverified without the artifact |

## 5. What is not known

- **Everything inside the APK.** No artifact was acquired, so no package name,
  signing certificate, DEX count, native libraries, or protocol layer has been
  observed. In particular whether RedFly talks DUML at all is **unknown** — a
  patched app would inherit DJI's transport, which for modern DJI Fly is native
  `libsdk_jni.so` rather than the `com.dji.logiclink` Java namespace.
- Whether RedFly's FCC implementation matches NLD's 21-frame profile. Given the
  v5/v6 split and the shared `1.21.12` base, that is the single most valuable
  comparison still outstanding.
- Whether `-noAppGuard` applies to the RedFly builds themselves or only to the
  separate Pilot/RedPilot products. The naming suggests the latter.
- RedFly's licence and backend model. `boosty.to/redfly` implies a paid
  subscription; no endpoint was identified from the bundle and none was contacted.