# Network and backend map

Passive inspection only. **No request was made to any endpoint in this
document**, no account was created, and no licence check was exercised.

Scope note: this maps what the artefacts *contain*. An `INTERNET` permission
establishes a capability, not an intention.

---

## 1. Backend summary

| Product | `INTERNET` | Backend present | Reachable without an account? |
|---|---|---|---|
| **Free Fly 1.0** | ❌ **absent** | ❌ **none** | n/a — no network capability at all |
| **NLD FCC** | ✅ | **yes** — vendor + DJI account + WireGuard | not determined |
| **DJIFCC** | ✅ (57 perms) | **yes** — patched app inherits DJI's | not determined |
| **RedFly** | ? | **yes** — paid subscription (boosty.to) | ❌ **purchase-walled** |
| **Drone-Hacks 1.48** | ✅ | **yes** — vendor API + DJI account API | ❌ login required |

## 2. Free Fly — the null case

**FACT.** Three independent lines of evidence:

1. **No `android.permission.INTERNET`.** On Android that permission gates the
   socket syscalls.
2. **No HTTP client library in any of ten DEX files.** okhttp, retrofit, gson,
   Apache HttpClient, Picasso, Glide, Firebase: **zero** classes each. Control:
   `kotlinx.coroutines` present at 877 files.
3. **No vendor URL, domain or IP.** The eight URLs in the APK are AndroidX and
   Compose build metadata.

**FACT.** No dynamic loading, no telemetry, no crash reporting, no update check.

**Scope, stated precisely.** The finding is *no direct Android Internet
capability and no embedded remote backend*. **Not** excluded: Binder, intent and
broadcast IPC to a cooperating process; a cooperating app's local provider or
`LocalSocket`; and USB, which is a live egress path — terminating in a DJI
controller, not a server.

**Conclusion.** "Free Fly works without a licence" is not a capability claim. It
is a property of a debug build with no network stack. There is nothing to
authorise because there is no channel to authorise over.

## 3. Drone-Hacks 1.48 — the most fully mapped

**FACT**, from `.pyc` bytecode in `controller/api_controller.pyc`:

```
https://drone-hacks.com/api/v1
/account/login
/account/verify-token
/license
/license/
/license/update-short-sn-to-long-sn
```

**FACT**, from `view/dji_login.pyc` and `view/cert_view.pyc`:

```
https://account-api.dji.com/apis/apprest/
v1/email_login
token
```

**INFERENCE — the flow:** authenticate to DJI's account API by email and
password → create an "Unlock Certificate" shown in the DJI app → authenticate to
the vendor API → register a licence bound to the device (with
`/license/update-short-sn-to-long-sn` converting a short to a long serial) →
download further files. Strings indicate the licence is hardware-bound
("This board cannot be used for extended unlocks or registering a license").

**FACT — remote configuration:** `CompatibilityController` fetches
`https://cloud.drone-hacks.com/drone-hacks/compatibility.json` (and a `_beta`
variant) and caches it locally **AES-CFB encrypted** with a module-level key and
IV, falling back to the local copy when offline and to a built-in "FailSafe"
release map when the map is unusable.

**FACT — version gate:** *"You got an older software version. Please download the
latest version: https://drone-hacks.com/"*

## 4. NLD FCC — vendor, DJI, and a VPN

**FACT.** `android.permission.INTERNET` plus `libwg.so`, `libwg-go.so` (3.3 MB),
`libwg-quick.so` and `com.wireguard.android.backend.GoBackend` in the DEX.

**FACT.** `SYSTEM_ALERT_WINDOW` and `PACKAGE_USAGE_STATS` alongside three
`FOREGROUND_SERVICE*` permissions.

**FACT.** No vendor host, endpoint or WireGuard configuration was found in either
the DEX or `libnld-core.so`, and no WireGuard configuration ships in the APK's
assets — which suggests provisioning at runtime or fetch, itself an open
question.

**Not determined:** what it tunnels to, and whether it is switched on.

## 5. DJIFCC and RedFly

**FACT.** DJIFCC holds `INTERNET` and 57 permissions because it is a patched
build of DJI Fly, a networked app. No DJIFCC-specific endpoint was identified.

**FACT.** RedFly's catalog points at `https://boosty.to/redfly` (paid
subscription) and `https://t.me/redflydjiapp` (Telegram). Downloads are served by
a **CSRF-gated, session-bound** `POST /api/download`; `/downloads/SHA256SUMS.txt`
returns 403. No endpoint was called.

## 6. What was deliberately not done

| Action | Status |
|---|---|
| Request to any listed endpoint | **not done** |
| Account creation or login | **not done** |
| Licence check exercise or bypass | **not done** |
| Downloading the RedFly artifact past its access control | **not done** |
| Brute force, credential attack, exploitation | **not attempted** |
| Decryption of any cached file | **not attempted** |

Every endpoint above is recorded so an authorised operator can reach it with
their own credentials, without this project having needed to.

## 7. Open question worth flagging

**INFERENCE.** Three commercial tools in this corpus ship a network backend and
one does not. That difference is architectural, not incidental: Free Fly's
absence of a licence gate is a direct consequence of having no network stack, so
it cannot later be added without changing the product's security posture. Any
comparison that treats "no licence" as a user benefit rather than as a missing
feature would be reading it backwards.
