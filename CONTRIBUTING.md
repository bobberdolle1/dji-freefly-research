# Contributing

## Evidence requirements

Every protocol claim must be traceable to something a reader can check. A
proposed change adding or altering a protocol claim needs at least one of:

- **Bytecode / smali / native evidence** — the file, the method, and the
  constant or instruction it comes from.
- **A packet capture** — raw hex, both directions, committed as a fixture or
  summarised in a report. Never a proprietary capture file.
- **A reproducible test** — a test that fails before the change and passes after.
- **A public-source citation** — repository, commit SHA, file and line.

"Decompiling it showed" is not sufficient on its own. Point at the artefact.

## Label your claims

Use the project's existing labels, consistently:

- **FACT** — read directly out of a named artefact.
- **INFERENCE** — concluded from facts; state the reasoning.
- **HYPOTHESIS** — a guess; state what would confirm or refute it.

## Corrections go where the claim is

If you find that an existing claim is wrong, **correct it in the document where
it appears**, not only in a new changelog entry. This project keeps its
retractions visible at the point of the error on purpose — three corrections
are still readable in place, and they show more about the reliability of the
rest than a clean-looking document would.

When you correct something, say what was wrong and why the new reading is
better. "Updated" is not a correction.

## No proprietary binaries

- No APKs, EXEs, firmware images, decompiler bulk output, or proprietary
  databases in a pull request.
- Analysis output is **described and summarised**, not redistributed. If a
  finding depends on a bulk enumeration, commit the counts and the conclusion,
  and leave the listing to be regenerated locally.
- Small derived test vectors — checksums, normalised metadata, extracted
  constant tables — are fine, and are expected. Say where each came from.
- `samples/`, `work/` and `research/corpus/` are gitignored and must stay that
  way.

## Do not add capability casually

`flylib` is read-only-first by design. Before adding anything that can change
aircraft state:

1. Explain why a read cannot answer the question.
2. Route it through `flylib.guard` so it remains disabled by default.
3. Add a test that the new path is refused unless explicitly enabled.

## Scope

This project documents one application and compares it against others. It is not
a general DJI hacking toolkit. Additions that turn it into one — credential
material, licence bypass, bulk automation against vendor services, or new
capability not needed to document the protocol — will not be accepted.

## Before opening a pull request

```bash
python -m pytest tests/ -q      # must pass
git diff --check                # no whitespace errors
```

Add a line to the relevant document's "not established" list if your change
closes an unknown. If it opens one, add it there too.
