# Oleg's standing rules — enforced, not remembered

Every rule here was stated as an absolute, then broken by a generator that had its own idea,
because the rule lived in a constant, a comment, or my memory. None of those fail a build.

> *"why you keep annoying me with same errors again and again. why you dont have guards to
> enforce my requirements"* — Oleg, 2026-07-27

They are now checked in `validate.py`, on the emitted artifact, where a generator cannot route
around them. `push.py` refuses to upload a file that fails.

| | rule | his words | proven able to FAIL by |
|---|---|---|---|
| **R1** | first layer pressed to `PRESS_HARD` (0.1) | *"the nozel need to be 0,1 to board. we need adhesion"* | the file he cancelled — first layer at Z0.510 |
| **R2** | no Z step above one layer height | *"play Z smartly we dont want floaring lines"* | dropping the Z0.700 step → `Z steps [1.2] exceed 0.6` |
| **R3** | one constant head speed (50 mm/s) | *"50 is our north star for moving"* | synthesised corner slow-downs → 724 moves off-speed |
| **R4** | one constant flow, layer 1 included | *"flow must be constant"* | synthesised starved layer 1 → 103 moves under 80% |
| **R5** | dry travel must not exceed extrusion | *"travel dry is ok, but avoid it at all costs"* | injected dry hops → 278.8m travel vs 227.1m extruded |
| **R6** | file names a filament with a known flow figure | — | unknown material has no maintained figure |

## Why each guard had to be shown failing

A guard that has never failed is decoration. Two of these looked fine and were not:

- **R4 passed the exact starved file it was written to catch.** That file predates the
  `; FLOW=` stamp, so the check silently skipped. **A missing stamp is now itself a failure.**
- **R5 did not fire on my first attempt** to force it — other guards caught the malformed test
  file first, and I nearly recorded R5 as verified on that evidence. It needed a clean test with
  genuine `G0` travel.

## The licensed exception

The **prime line only** — laid off the part before printing starts. It is identified by its own
comment, never by being slow, otherwise "slow" becomes a way to opt out of R3.

## What is NOT guarded

- **Bore sizing.** `BORE_INSET_PER_BEAD = 1.373` is measured from ONE printed part, cancelled at
  ~14%, so it samples the most-squished bottom layers. It errs toward a looser hole, which is the
  safe direction. No guard can check this; only a printed part can.
- **Whether the object is any good.** Geometry that passes every rule can still be ugly or useless.

## Declared exceptions

An exception must be **declared by the generator in the file**, never inferred by the checker.
A checker that guesses "this one looks intentional" is a checker with a hole in it.

| exception | how it is declared | why it is legitimate |
|---|---|---|
| prime line | comment containing `PRIME` | laid off the part before printing starts |
| contour link | comment containing `LINK` | crosses ground the NEXT contour covers; a full bead there lays a second bead at the same Z, doubles the height, and the nozzle drags through it on the next layer |

**Declared LINK moves are exempt from R4 but COUNTED and printed on every run**, so an exemption
can never quietly grow. `solid.py` currently declares 45 of them on a bracket plate.

## False positives are how a guard gets switched off

The OVERHANG check measured support against a one-bead radius while layer 1 is laid into a
`PRESS_HARD` gap carrying the body's full mm² — so it spreads to `bead_w*layer_h/PRESS_HARD`,
about **13 mm** at 2.17×0.6. It reported a perfectly-covered layer 2 as 22% overhanging. The
support radius now uses the lower layer's real width when that layer is the pressed first one.

## Codebase-wide sweep, 2026-07-27

Building the guards revealed the rules were broken almost everywhere, not only where Oleg caught
them. This is the point: the file he catches is a sample, not the set.

| generator | what the guards found |
|---|---|
| `solid` | layer 1 metered at a **3.0 mm literal** width → a quarter of body flow. `--first-w` now derives from constant flow. **Passes.** |
| `nucleon` | own first-layer model at 0.51 mm; ladder not rebased; sub-resolution segments. **Passes.** |
| `belt`, `pulley` | 719 and 1046 moves at 25–30 mm/s instead of 50 |
| `hilbert` | layer 1 at flow 55 against a body of 36 |
| `waves`, `honeycomb` | no stamps at all — R4 could not see them |
| `stave_*` | flow not constant |
| `archtest` | extrudes below already-printed material; separate question, experimental file |

## The one bypass, stated plainly

`push.py --skip-validate` uploads a file that failed. It exists for genuine measurement files and
emergencies, and it prints *"fix it, or pass --skip-validate if you know better than the
validator"* rather than pretending the failure did not happen.

**It is a hole, and naming it is the point.** If it starts getting used routinely, the honest
response is to fix the generator or the rule — not to keep reaching for the flag. Legitimate
measurement files should not need it: `validate.py` already exempts files stamping `FLOW_TEST=1`
from the flow cap, because a flow ramp deliberately exceeds it.

Verified 2026-07-27: pushing a file with a starved first layer is **refused**.

## What an independent audit found wrong with THIS file's claims

An auditor re-ran every generator with its own parser and checked specifically whether anyone made
a file pass by bending the checker. It cleared the five generators — the fixes are real deltas, and
the baseline defects reproduce to the digit — and it caught two things about the guards themselves.

**1. `solid.py` passes BECAUSE of the LINK exemption, not on its own merit.** Strip only the
`; LINK thin` tag from its emitted gcode and it fails: *33 extruding moves under 80% of declared
flow*. The physical reason for thinning a contour connector is real, and the exemption is declared,
counted, printed and documented — but the honest statement is that this compliance was **granted by
a checker edit**, not earned by the generator. Anyone reading a green tick on `solid.py` should know
that.

**2. RULES.md claimed "a missing stamp is itself a failure" and that was only true of `; FLOW=`.**
The auditor proved it: delete `; LAYER_H=` and R2 died silently — a deliberately injected **1.9 mm
Z jump, 3× the layer height and a textbook floating line, PASSED**. Delete `; MATERIAL=` and R6 died
silently. Both now fail loudly, verified against stamp-stripped files.

A guard that switches itself off when its input goes missing is worse than no guard, because the
green tick is indistinguishable from a real pass. This file asserted the fix before it existed.
