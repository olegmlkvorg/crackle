# Z modulation during extrusion — Oleg's idea, 2026-07-25

**The idea:** at the max stable flow, move Z up and down *while extruding* instead of holding it flat.

**Why it is interesting and not just a gimmick.** Every slicer treats Z as a staircase: constant
within a layer, stepping between layers. Nothing about the machine requires that — Z is just
another axis in the same `G1`. Modulating it during a move makes the bead's squish vary
continuously, which changes bead width, gloss and adhesion along a single line. That is a texture
you cannot ask a slicer for at all, and it costs no extra material or time.

**Why it pairs specifically with max flow.** Squish modulation only has range if there is enough
plastic to squash. At low flow, lifting Z just breaks the bead into a broken thread. At the melt
ceiling the bead is fat, so Z becomes a real amplitude knob: press it flat, let it stand proud.

**Directly relevant to crackle.** The current crackle model builds fragile crossings by controlling
*where* strands cross. Z modulation controls *how hard* they weld at each crossing — press down at a
crossing to fuse it, lift between crossings to leave the strand thin and free. That is a second,
independent axis of control over exactly the mechanism we are testing, and it needs no new geometry.

**Experiments, in order (all single layer, so no collision risk):**
1. Fixed-amplitude sine along a straight row: `Z = z0 + A*sin(2*pi*x/wavelength)`, sweep A =
   0.05/0.10/0.20/0.30 mm at constant wavelength. Find where the bead breaks up.
2. Sweep wavelength at the best amplitude — this is the "feel" frequency.
3. Phase-lock Z to crossings: press (low Z) at every crossing, lift between. Compare against the
   same path at flat Z. If crackle changes, welding is confirmed as a controllable variable.

**Safety note that makes this cheap to try:** amplitude must stay below the layer height or the
nozzle lifts clear of the bed on the up-stroke and drags a loose string. Cap A at ~0.6 * layer_h
until measured. Single layer throughout — the 2026-07-25 tower failure was a stacking collision,
and none of this stacks.

**Status:** waiting on the max-flow number from `flowsheet_*`. That number sets the flow this runs at.
