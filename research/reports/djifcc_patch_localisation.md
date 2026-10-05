# DJIFCC patch localisation — what the patch actually is

Follow-on from `djifcc_differential.md`, made possible by acquiring a
**versionCode-exact, ABI-matched** stock operand.

## The operand

**FACT.** The stock build was obtained from DJI's own distribution service
(`service-adhoc.dji.com/download/app/android/…`), whose page links a DJI CDN
artifact named `DJIFly-1.21.12.1030(3131451)-android-release-260921-sec.apk`.

| | Package | versionName | versionCode | ABI | DEX | Entries |
|---|---|---|---|---|---|---|
| Stock `DJIFly-1.21.12.1030.apk` | `dji.go.v5` | 1.21.12 | **3131451** | arm64-v8a | **1** | 16,160 |
| DJIFCC `…-Android-arm64-signed-1.21.12.19.apk` | `dji.go.v5` | 1.21.12 | **3131451** | arm64-v8a | **23** | 16,180 |

- SHA-256 `1da8d5b2ee5cdcb6002131b8f6535605e7445080d1ca6f8411067a0d1524ce0b`
- Size 719,710,792 bytes
- Acquired 2026-10-05 from DJI's CDN, via the official page. Not a third-party
  mirror.

**INFERENCE.** This is the ideal operand: same package, same versionName, **same
versionCode**, same ABI. Any difference between the two is attributable to the
patch rather than to version drift.

*(Method note: DJI's CDN returns 403 when a browser `User-Agent` is supplied and
200 for a default client. `curl` also rejects the unencoded parentheses in the
filename. Both are client quirks, not access controls.)*

## What the patch changes

Entry-level comparison, normalised and order-independent
(`tools/repack_proof.py`, output in `research/generated/djifcc_stock_diff.json`):

### Added

**FACT.** `lib/arm64-v8a/libdjifccnative.so` — 403,872 bytes, SHA-256
`3699b5d83f7ad49a7bc60129b407bab7…`, **absent from stock**. This is the patch's
own native component.

**FACT.** `classes2.dex` … `classes23.dex` — stock ships a **single** 13 MB
`classes.dex`; the patched build splits into 23. `classes23.dex` (305,256 bytes)
has no stock counterpart.

**FACT.** The patched build's `META-INF/KEY0.SF` / `KEY0.RSA` replace stock's
`META-INF/DJI.SF` / `DJI.RSA`.

### Removed

**FACT.** Three native libraries present in stock and **absent from the patched
build**:

- `lib/arm64-v8a/libAppGuard.so`
- `lib/arm64-v8a/libAppGuard-x86.so`
- `lib/arm64-v8a/libdatajar.so`

**INFERENCE.** DJI's `AppGuard` is a tamper/integrity component. DJIFCC
**removes DJI's integrity protection** and substitutes its own. That is a
security-relevant change to the shipped artefact and is stated here as an
observed delta, without endorsing or condemning it.

### Re-encoded

**FACT.** Stock resource paths are obfuscated (`res/-02.png`, `res/-0N.webp`);
the patched build's are plain (`res/anim/abc_fade_in.xml`). 231 payload entries
differ in content at identical size — binary XML whose string pools were
reordered by a rebuild.

**INFERENCE.** The patcher decoded and re-encoded the resource table rather than
patching in place, which is why a targeted binary diff of stock vs patched is
not the cheapest route to understanding the change.

## `libdjifccnative.so` — the patch's native core

**FACT.** It is an **arm64-v8a ELF shared object** carrying Rust runtime strings
(`RUST_BACKTRACE`, `note: run with ...`), Android NDK `r30-beta3`.

**FACT.** It exports JNI symbols for a single Java class,
`com.djifcc.mod.NativeBridge`:

| Symbol | Purpose |
|---|---|
| `Java_com_djifcc_mod_NativeBridge_codeIntegrity` | integrity check |
| `Java_com_djifcc_mod_NativeBridge_grantSelfTest` | self-test grant |
| `Java_com_djifcc_mod_NativeBridge_lcDecode` | opaque ("lc" — purpose unverified) |
| `Java_com_djifcc_mod_NativeBridge_lcEncode` | opaque ("lc" — purpose unverified) |
| `Java_com_djifcc_mod_NativeBridge_securityStatus` | security status |
| `Java_com_djifcc_mod_NativeBridge_signerOk` | signer check |

**FACT.** It embeds the literal

```
DJIFCC-SELFTEST-OK-v1cad73496edd54f0453708617454f494b96b9cb5bb9e1b52ff5d448d13f93d19c
```

where `cad73496…` is the **SHA-256 of DJIFCC's own signing certificate**, and the
adjacent literals `DJ_CODE_EXPECT` and `DJCRC01`.

**INFERENCE.** The native module binds its own execution to DJIFCC's signing
certificate. Combined with `codeIntegrity`, `signerOk` and `securityStatus`,
this is an integrity-and-licensing gate over the patch itself. It is **not**
attributing anything beyond that: no unpacked code has been read, and `lcDecode`
/ `lcEncode` are symbol names only — their meaning is **unverified** and they
could be licence-code, link-code, or something else.

## `classes23.dex` — the patch's Java layer

**FACT.** 305,256 bytes, containing **232 `com.djifcc.mod.*` classes**, with an
**identical class set** in both the phone and RC Pro 2 builds (consistent with
the earlier finding that only 27 % of its bytes differ between SKUs — the code is
the same, the embedded constants and strings are not).

**FACT.** Representative classes:

`AdbLockdown`, **`AreaCodeFcc`**, **`AuthClient`** (with `Callback`, `Result`),
`Branding`.

**FACT.** Notable embedded strings:

```
User-Agent: djifcc
forcedRegion=
region=
switches (excl. 500m + FCC)
verify:
.djifcc.fileprovider/
```

and, in Italian, a user-facing warning:

> 4G (auto-HYBRID) e FCC non possono essere attivi insieme. Ha effetto solo dopo
> un riavvio completo: con 4G ATTIVO l'FCC resta DISATTIVO; disattiva il 4G e
> riavvia per usare di nuovo l'FCC…

("4G (auto-HYBRID) and FCC cannot be active at the same time. It takes effect
only after a full reboot: with 4G ACTIVE the FCC stays DISABLED; disable 4G and
reboot to use FCC again.")

**INFERENCE**, each from the evidence named:

- `AreaCodeFcc` plus `forcedRegion=`/`region=` indicate region forcing **inside
  the patched app**, consistent with modifying DJI Fly rather than writing
  aircraft parameters.
- `AuthClient` + `User-Agent: djifcc` + the INTERNET permission indicate a
  **network authentication/licensing backend**. This is the opposite of Free
  Fly, which has no INTERNET permission and no HTTP library.
- `AdbLockdown` indicates the patch **restricts ADB access** — plausibly to stop
  the user from removing it. Purpose inferred from the class name only.
- The Italian warning is a **product-level constraint**: DJIFCC treats 4G and FCC
  as mutually exclusive states requiring a reboot to change, which is a claim
  about the aircraft's behaviour, not about the app.

## How this compares with Free Fly

| | **DJIFCC** | **Free Fly** |
|---|---|---|
| Where the change lives | inside a **re-signed DJI app** | a **separate app**; DJI's app is untouched |
| Patch carrier | `classes23.dex` (232 classes) + `libdjifccnative.so` (Rust) | its own ~15 Kotlin classes |
| Licensing | **yes** — `AuthClient`, `User-Agent: djifcc`, INTERNET | **no** — no INTERNET permission, no HTTP library |
| Integrity gate | `codeIntegrity`, `signerOk`, `securityStatus`, cert-bound self-test | none |
| DJI's tamper protection | **removed** (`libAppGuard*.so`, `libdatajar.so`) | n/a — DJI's app is not repackaged |
| Region mechanism | app-side (`AreaCodeFcc`, `forcedRegion=`) | FC parameter write (`ce_country_type`) |
| Obfuscation | Rust native core + integrity binding | none — fully readable Kotlin |

**INFERENCE.** This settles the §10 question with far more specificity than the
mechanism-level contrast alone. DJIFCC does not merely "patch the app": it ships
a licensed, integrity-bound native module, removes DJI's own tamper protection,
and forces region from inside the patched application. Free Fly does none of
those things and takes an entirely different route — writing flight-controller
parameters over USB bulk from a separate program.

## What is still unknown

1. **No disassembly.** `libdjifccnative.so` has been identified by exports and
   strings only; `lcDecode`/`lcEncode` remain unidentified, and nothing is known
   about what `codeIntegrity` actually checks.
2. **The 27 % per-SKU delta in `classes23.dex` is unexplained.** Same class set,
   same size, different constants — likely per-SKU region or branding data, but
   not confirmed.
3. **No `AuthClient` endpoint identified.** The `User-Agent: djifcc` string is
   confirmed; the host is not. Resolving it needs the code, not the strings.
4. **Whether the patch changes aircraft behaviour** or only the app's UI and
   region reporting. Nothing here addresses what is sent to the aircraft.
5. **Stock 1.21.12's resource obfuscation** is itself unexplained; understanding
   the packer is a prerequisite for a minimal-diff approach.