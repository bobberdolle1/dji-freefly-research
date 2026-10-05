# Security and safety

## This is research software

`flylib` is an independent, clean-room implementation written to **document and
test** a protocol. It is not a flight tool, not a product, and not suitable for
operating an aircraft.

## Defaults

- **Read-only.** Every read path works without configuration.
- **Mutation is disabled by default.** `MutationGuard` starts refused. Enabling
  it requires an explicit written reason, and it stays in dry-run unless the
  caller *also* passes `dry_run=False`. Every transport enforces this, so no code
  path can put a mutating frame on a wire by choosing a different transport.
- **No network code.** The library opens no sockets. `LiveTransport` is a thin
  wrapper over a caller-supplied connection and does not implement one itself.

## Do not send unknown commands to live aircraft

Sending unverified frames to a real aircraft risks unintended state changes on
flight-critical systems. This repository exists partly because that risk is
real: the commands documented here address a **flight controller** and a
**radio module**.

Work on hardware must follow [`docs/HARDWARE_TEST_PLAN.md`](docs/HARDWARE_TEST_PLAN.md):
read-only probes first, then unlock, then a parameter write on a non-flyable
airframe, with an explicit stop before anything touching regulatory parameters.

## Caution on specific parameter classes

- **Flight limits.** `max_height`, `max_radius`, `roof_limit_enable` and similar
  are *operator limits*. Lowering or disabling them does not bypass a
  firmware-enforced restriction, and removing them can remove a safety margin
  the pilot relies on.
- **Regulatory / region parameters.** `ce_country_type` and
  `ce_regulatory_level` appear in the analysed application's catalogue. The
  static analysis here establishes that they are **enumerable**; it does not
  establish that they are writable, nor that changing them is lawful in the
  jurisdiction of operation.
- **Radio configuration.** The FCC mechanism in the comparative corpus
  reconfigures a radio module. **Radio operation is regulated in most
  jurisdictions.** Changing transmitted power, channel plans or region codes can
  breach local radio regulations and, in some places, is a criminal offence
  independent of any aircraft safety consideration. Nothing in this repository
  should be read as advice on the legality of any such change, and none of it has
  been tested here.

## Vendor licensing

This project documents observed architecture and protocol behaviour. It contains
**no credentials, no authentication bypasses, and no means of defeating a
vendor licence gate**. Where a commercial product's licence mechanism is
described, it is described as an observation, in the same register as any other
finding.

No vendor authentication endpoint was contacted at any point during this work.

## Reporting a problem

Open an issue describing the concern. Do **not** include proprietary samples,
credentials, or captured traffic containing personal data.
