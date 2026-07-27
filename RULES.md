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
