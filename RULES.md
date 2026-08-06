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
| **R3** | **one** speed per print, ≤ the north star | *"speed is not fixed - 50 is north star default unless overruled by other constraints"* | mixed-speed file → *"runs at 2 different speeds"*; a uniform 21 mm/s crawl correctly **passes** |
| **R4** | one constant flow, layer 1 included | *"flow must be constant"* | synthesised starved layer 1 → 103 moves under 80% |
| **R5** | dry travel must not exceed extrusion | *"travel dry is ok, but avoid it at all costs"* | injected dry hops → 278.8m travel vs 227.1m extruded |
| **R6** | file names a filament with a known flow figure | — | unknown material has no maintained figure |
| **R9** | the first layer may not CHANGE without a coupon | *"why you keep messing up base layer every second print?"* | `tests/forced_layer1.py` — ten forced cases, every one of which the pre-R9 validator passed |
| **R10** | nothing may extrude before the first bead is pinned | *"The beginning of extrusion need to be improved generically"* / *"Also few unacceptable artifacts"* | `tests/forced_prime.py` — five forced cases: it refuses both purge shapes, DECLINES the pinned one, and passes the prime now emitted |

## R10, and why the answer was not a better Z

Every generator opened by extruding 12 to 25 mm of filament — 28.9 to 60.1 mm³ — with the head
**standing still**. Oleg photographed the result twice on 2026-08-06: a clump hanging off the
nozzle, and that clump dropped into the middle of a printing plate.

Only one thing had ever been varied, and this repo had already written down that **both ends of it
fail**:

- at the **press gap**, `presstest.py:168`: *"a 20mm stationary purge (~48mm³) at the 0.1 press gap
  cannot spread — it balloons up and COLLARS the nozzle"*.
- **lifted to Z2**, which was the fix for that, is the photograph. 4 seconds at F300 makes ~96 mm of
  0.8 mm strand falling 2.0 mm into open air. Its entire weight is 0.56 mN against wetted adhesion
  to hot brass over several mm². It cannot fall away, so it coils onto the tip.

So the rule is not about Z at all — keying on Z would pass the 132 files that purged at 0.10 and
catch only the 17 that purged at Z2. **The only force that separates melt from a 210 °C brass face
is tension at the far end of the strand, and the only thing that supplies it is a bead already
welded to the plate.** The plate is the tool. R10 refuses stationary extrusion at any Z before
anything is pinned, and `machine.prime()` is the third option nobody had tried: move from the first
millimetre.

### What R10 does NOT refuse

A stationary extrusion **after** material is down — about 20 `solid.py` files step Z while
extruding at the spiral seam. There the previous layer holds the far end of the strand, so the
mechanism does not apply. They are counted and printed, never hidden, but refusing them would be
refusing files for a reason that is not the defect in the photograph. `forced_prime.py` asserts
that decline, because a rule that fires on everything is not a measurement.

### The second blob source, which fixing only the purge would have left

The prime **line** was metered as a hardcoded `E`, over a path length that was computed — so its
bead width was an accident of part position. One source line in the `hilbert.py` family produced
**thirteen** different mm²/mm across the emitted files, a 4.05× spread. `borelock` ran its prime at
0.601 mm²/mm five lines above its own header stating layer 1 as 0.200: a 0.8 mm orifice asked to
spread a 6.01 mm bead at a 0.10 gap, which it cannot do, so the excess goes up and around the tip.
`machine.prime()` takes a `rate` and callers pass `machine.layer1_rate(...)` — the same call layer 1
makes — so the prime physically cannot be a different bead from the part's own first layer.

## R9, and why R1 was not enough

R1 checks the first layer is **commanded** to 0.1. On the K2 that is not where it goes: the Z zero
sits 0.15 mm high, so a commanded `Z0.100` with no correction lands at **0.250** — a gap the bead
never reaches. The correction is a `SET_GCODE_OFFSET` line, and until 2026-08-06
`grep -c SET_GCODE_OFFSET validate.py` returned **0**. Every first-layer parameter in this project
was being changed behind a gate that examined none of it. It cost two prints in one day: the 320 mm
bucket's five cancels, then a bamboo bucket whose base came off as separated lifted strands.

R9 measures where the bead **lands**, off the emitted moves:

    h1 = commanded Z of the body's first bead + the offset in force AT THAT BEAD + machine.ZERR
    w1 = (mm² per mm of the moves at that Z) / h1

and refuses any pair that is not in `machine.PROVEN_LAYER1` — pairs somebody watched come off the
plate, not arithmetic. Height and width are **one weld**: 2.00 mm at 0.10 and 2.00 mm at 0.15 are
different things, and checking them separately would have passed the bamboo base.

A machine with no `machine.ZERR` entry is **not judged and says so**. A missing measurement is not
a measurement of zero.

### The two ways past it, both declared AND counted

| exception | how it is declared | what is checked, on artifacts |
|---|---|---|
| coupon citation | `; COUPON=<file> h1=<mm> w1=<mm> verdict=welded read=<YYYY-MM-DD>` | the coupon file exists; the verdict is `welded`; the cited numbers are the ones this file **lands**; and those numbers appear among the heights **that coupon itself printed** |
| the coupon itself | `; Z_LADDER=1` | the file really presses ≥3 different heights at one width, measured off its own moves. A part presses exactly one, so a bucket declaring `Z_LADDER` is refused |

The last coupon clause is the one that matters. The ladder on the plate today sweeps 0.10 → 0.35
all at 2.00 mm wide, so it **cannot** excuse a 1.33 mm weld at any height, and R9 says exactly that
instead of accepting the citation. A flag that merely asserted "tested" would have waved the bamboo
base through.

### What R9 does NOT check

**Floor pitch.** It is part of the proven set on paper (1.6 mm solid, 2.5 mm open grid) and it is
deliberately left unguarded, because the instrument is not good enough to name it. The emitted
first layer is drawn as ~1 mm micro-segments with no straight-line primitive to measure, so pitch
has to be inferred as hull-area ÷ path-length. Measured that way it lands 1.586 against a declared
1.6 and 2.476 against 2.5 on the large buckets — but 4.05 against 5 on a 100 mm bucket, and it is
meaningless on any multi-cell plate, where the hull spans the gaps between cells. A check that
cannot measure its own name must decline rather than approve.

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

## R3 was implemented wrong first, and the wrongness became two false claims

I first implemented the north star as an **immovable** 50 mm/s. Oleg corrected it:
*"speed is not fixed - 50 is north star default unless overruled by other constraints."*

The over-strict version broke two legitimate things — and I reported both as findings about the
world rather than about my own code:

- **"Your two rules collide."** They do not. The wide-bead trick has always been *crawl with a fat
  bead*: speed comes DOWN so the flow lands. Pinning speed inverted it (10 mm × 0.6 × 50 = 300
  mm³/s) and made 7 archived commands unrunnable. **I manufactured the collision, then presented it
  as his problem to resolve.**
- **"TPU cannot be printed at the north star at all."** False. At a pinned 50 it needs a 0.51 mm
  bead, narrower than the nozzle — so I declared the material unprintable. At the normal 1.2 × 0.6
  bead it runs at **21 mm/s**.

**What R3 actually protects is constancy within a print** — one speed, so material per mm does not
change where the geometry is already tightest. The value is 50 unless a constraint pushes it lower;
never higher.

**The general failure:** an over-strict guard does not fail loudly like a missing one. It produces
*confident, well-evidenced claims that are artifacts of the guard*. Both claims above came with
arithmetic. Before reporting "X is impossible", check whether X is impossible **or merely forbidden
by something I wrote**.
