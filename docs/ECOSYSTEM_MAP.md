# Ecosystem map

Every product in this corpus classified against the twelve categories the
mission defines. A product may occupy more than one.

---

## 1. Classification

| Product | 1 FC param editor | 2 raw DUML patcher | 3 patched DJI Fly/GO4 | 4 firmware patcher | 5 flasher/downgrader | 6 controller unlock/sideload | 7 radio-region/FCC | 8 NFZ/GEO | 9 C0/altitude | 10 ATTI | 11 DroneID | 12 4G |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Free Fly 1.0** | ✅ primary | — | — | — | — | — | — | — | ⚠️ *see §3* | — | — | — |
| **Drone-Hacks 1.48** | ✅ primary | ✅ | — | — | — | ⚠️ see §5 | ❌ | — | — | ❌ | — | — |
| **NLD FCC** | — | ✅ | — | — | — | — | ✅ primary | — | — | — | — | ✅ |
| **DJIFCC** | — | — | ✅ primary | — | — | ✅ | ✅ | — | — | — | — | — |
| **RedFly** | ? | ? | ✅ (stated) | ? | ? | ✅ | ✅ (stated) | ? | ? | ✅ (stated) | ? | ? |
| **FreeFCC / -USB** | — | ✅ | — | — | — | — | ✅ primary | — | — | — | — | — |
| **djiparam** | ✅ primary | ✅ | — | — | — | — | ❌ | — | — | — | — | — |
| **DJI-FCC-HACK** | — | ✅ | — | — | — | — | ✅ | — | — | — | — | — |
| **DJI-FCC-Unlock-iOS** | — | ✅ | — | — | — | — | ✅ | — | — | — | — | — |
| **dji-firmware-tools** | ✅ offline | — | — | ✅ tooling | ✅ tooling | — | — | — | — | — | — | — |

`?` = unknown, artefact not acquired. `—` = not evidenced. `⚠️` = qualified, see below.

## 2. The four mechanism families

**1. Standalone DUML parameter tools** — Free Fly, Drone-Hacks, djiparam.
Speak DUML directly, read and write the FC parameter table. Free Fly is the
only one in this corpus with no licensing and no network.

**2. TCP-through-the-controller FCC tools** — FreeFCC, djiparam (parameter side),
NLD FCC (FCC side).
Connect to the controller's local TCP proxy (40007/40008/40009) and reconfigure
the **radio module** through a service-mode sequence.

**3. USB-serial FCC tools** — DJI-FCC-HACK, DJI-FCC-Unlock-iOS (via MFi).
Reach the same radio commands over a different transport.

**4. Patched official apps** — DJIFCC, RedFly.
Ship DJI's own package, re-signed, with modified app logic. Inherit DJI's
transport wholesale; their protocol behaviour lives in an 88 MB `.so` rather
than in readable code.

## 3. The C0/altitude entry for Free Fly — qualified

Free Fly's catalogue contains `g_config.flying_limit.max_height`,
`user_set_max_height`, `max_radius`, `roof_limit_enable`. Those are **user-facing
flight-limit parameters**, which is category 9 by subject matter.

**But the distinction that keeps this honest:** writing `max_height` is not the
same act as defeating a C0 restriction. Free Fly sets the *operator's* limit; it
does not bypass a firmware-enforced one. Whether a C0 restriction can be lowered
through a parameter write at all is **not established** — it needs hardware, and
it is the first item in `HARDWARE_TEST_PLAN.md`.

Marked ⚠️ rather than ✅ for that reason.

## 4. The persistence problem

**No mechanism in this corpus persists automatically**, and the failure modes
differ in ways that matter:

| Family | Persistence | Why it can be lost |
|---|---|---|
| Parameter write | only if the FC stores it | firmware may reject, or accept and ignore |
| Radio + keepalive | **never** | NLD's own text: *"…to prevent DJI Fly from resetting to CE"* — re-applied every 2 s |
| Patched app | while installed | any real DJI update replaces it; signature mismatch forces uninstall-then-sideload |

**INFERENCE.** Because the FCC change is volatile, tools that advertise it as
"permanent" are describing the patched app's lifetime, not the aircraft's state.

## 5. The Drone-Hacks licensing entry — qualified

Drone-Hacks is a parameter editor with an **online licence gate**: a vendor API
at `drone-hacks.com/api/v1` with `/account/login`, `/account/verify-token` and
`/license`, plus a DJI account login and an "Unlock Certificate".

**Not** a sideload tool in the sense of category 6 — it does not place packages on
a controller. Marked ⚠️ because it *unlocks an aircraft feature* (FC Assistant)
and the product's own strings use "unlock".

## 6. Sideload tooling as a product class

**FACT.** DJIFCC's utility bundle is largely **third-party and AOSP software**,
not DJIFCC's code:

| Package | Signer |
|---|---|
| `io.github.muntashirakon.AppManager` 4.0.5 | `O=fdroid.org` (F-Droid) |
| `com.android.documentsui` | `O=DJI, C=CN` |
| `com.android.packageinstaller` | `O=DJI, C=CN` |
| `me.hisn.mygesture` | third-party |
| `ginlemon.flowerfree` 6.5 | third-party |

Only `com.djifcc.flyinstaller`, `appstore`, `gesture` and `launcher` are
DJIFCC's own.

**INFERENCE.** This closes the "controller unlock/sideload tool" class: DJIFCC's
installers exist *because* keeping DJI's package names while re-signing forces a
fresh install rather than an upgrade.

**FACT.** Two of those bundles are GPL-3.0 (App Manager) and Apache-2.0 (AOSP)
redistributed inside a commercial bundle. Flagged, not opined on.

## 7. Licensing map of the comparison set

| Product | Licence known to this project |
|---|---|
| FreeFCC, FreeFCC-USB | AGPL-3.0 |
| DJI-FCC-HACK, dji-firmware-tools | GPL-3.0 |
| djiparam | MIT |
| **DJI-FCC-Unlock-iOS** | **PolyForm Noncommercial 1.0.0 — not OSI open source** |
| Free Fly, NLD FCC, DJIFCC, RedFly, Drone-Hacks | proprietary; redistribution terms unknown |

## 8. Where a new entrant would sit

**INFERENCE.** A new Android parameter tool today would land in family 1: USB
bulk, DUML, 2017 parameter read/write. That is exactly Free Fly's position, and
it is the cheapest entry — no radio access, no patching, no licence server. The
trade is that it can only reach what the flight controller exposes as a
parameter, which is why Free Fly's catalogue includes `ce_country_type` while
containing no FCC sequence at all.