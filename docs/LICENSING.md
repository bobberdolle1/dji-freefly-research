# Licensing provenance audit

**No LICENSE file is present, and none has been added.** This document records
why, so the decision belongs to the operator rather than to an assumption.

```
LICENCE_STATUS=UNSET — deferred to operator choice
THIRD_PARTY_CODE_INCLUDED=NO
THIRD_PARTY_LICENSE_OBLIGATIONS=NONE INCURRED
```

---

## 1. Provenance, separated into four classes

### A. Code written clean-room in this repository

`research/flylib/` (10 modules), `tools/` (10 scripts), `tests/` (6 files).

Written from **observed protocol behaviour** and public documentation of DJI's
format. No third-party source was copied, adapted, transliterated, or pasted.

The derivation path for the protocol layer was: extract constants from the
analysed sample's own bytecode, then **verify by independent means** — the CRC
polynomials were brute-forced against every candidate by comparing generated
tables to the APK's embedded tables element by element, and the header layout
was confirmed by the fact that encoder and decoder agree on golden vectors
derived field-by-field from the smali.

### B. Research facts and protocol observations

Command identifiers, frame layout, CRC parameters, device-type encodings, the
parameter-hash algorithm, the catalogue contents, and every observation tagged
FACT in `docs/`.

These are **facts about a third party's protocol**, not code. They are what the
project exists to publish.

### C. Public projects referenced, quoted, or compared against

| Project | Licence | Relationship to this repository |
|---|---|---|
| `doesthings/FreeFCC` | AGPL-3.0 | **Compared against only.** No code incorporated |
| `doesthings/FreeFCC-USB` | AGPL-3.0 | **Compared against only.** No code incorporated |
| `M4TH1EU/DJI-FCC-HACK` | GPL-3.0 | **Compared against only.** No code incorporated |
| `o-gs/dji-firmware-tools` | GPL-3.0 | **Compared against only.** No code incorporated |
| `andreapianidev/DJI-FCC-Unlock-iOS` | **PolyForm Noncommercial 1.0.0** — *not* OSI open source | **Compared against only.** No code incorporated |
| `djiparam` | MIT | **Compared against only.** Used as a control in the lineage assessment |

Short quotations appear in the analysis documents — a format-string, a
diagnostic message, a comment line — to identify and cite a specific artefact.
These are cited, attributed, and minimal.

### D. Code copied or adapted from third parties

**None.**

---

## 2. The one artefact that needed judgement

`tests/fixtures/crc_tables_from_sample.json` contains two 256-entry CRC lookup
tables. They were:

1. extracted from the analysed sample's own bytecode;
2. verified byte-for-byte equal to the tables `flylib` generates from the
   polynomials `0x8C` and `0x8408`.

They are **mechanically generated mathematical constants**, not expressive
code: each is the deterministic output of a published algorithm given a
polynomial. The same tables are independently published in the public
`o-gs/dji-firmware-tools` corpus under GPL-3.0.

**INFERENCE.** A CRC lookup table is the kind of factual, non-creative datum
copyright does not protect, in the same category as a protocol constant. It is
committed because it is this project's **strongest verification**: it lets the
test suite assert that `flylib`'s polynomial-derived tables match the ones the
application ships, on any machine, with no sample present.

Had the tables come from a GPL source rather than from the sample, the analysis
would differ and the file would not have been committed on this basis.

---

## 3. Why no licence was chosen

The provenance is clean in the sense that matters most — **no third-party code
is present**, so no copyleft obligation has been incurred. But one question is
genuinely open, and it is not mine to settle silently:

> Several AGPL-3.0 and GPL-3.0 projects in this space implement the **same
> protocol**, and one of them (FreeFCC) ships a profile that a commercial product
> redistributes byte-for-byte. Could a clean-room implementation of a protocol
> that AGPL projects also implement be treated as a derivative work?

**INFERENCE.** Probably not: implementation of a protocol from observation is
generally not derivative of another implementation of the same protocol, and
nothing here was copied from those sources. But the question is close enough to
plausible that declaring a permissive licence without addressing it would be
overconfident, and declaring a copyleft one without cause would over-restrict.

The safest and most accurate position is to leave it to the repository owner,
with the analysis recorded.

### Options, with what each would imply

| Option | Effect | Note |
|---|---|---|
| **MIT / BSD-3** | Permissive; allows reuse including commercially | Defensible on this provenance. Would need the AGPL question settled to the owner's satisfaction first |
| **GPL-3.0 / AGPL-3.0** | Copyleft; would satisfy any residual doubt at the cost of restrictiveness | Over-restrictive if no obligation exists |
| **No licence (current state)** | All rights reserved by default; others may read but not reuse | Accurate and non-committal. **Currently in effect** |
| **Research/non-commercial** | Restricts commercial use | Would align with the commercial products this work describes |

---

## 4. What would resolve it

- A provenance review confirming that no AGPL/GPL expression was consulted
  while writing `flylib`.
- An owner decision on whether to accept the residual risk of a permissive
  licence.

Until then the repository carries **no licence**, which is a deliberate,
documented state rather than an oversight.

## 5. Third-party attributions regardless of licence

Whatever licence is eventually chosen, attribution belongs in the repository
regardless. See [`../REFERENCES.md`](../REFERENCES.md) for the pinned URLs, commit
SHAs and licences of every public project used for comparison.
