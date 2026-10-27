# Slope test vs step-test bridges (2026-10-27)

Brief: ~/dev/Assist/agents/briefs/crackle-slope-bridge-2026-10-27.md. Base: 57d6b81.

## Status
- [ ] fetch + verify hanging-row plate (sha256 8a2b230a4e13cb3f...)
- [ ] reproduce claim 1 (slope overhang inside step bridges) on plate + fixture
- [ ] reproduce claim 2 (end-gap ceilings counted by PRINTABLE) on plate + fixture
- [ ] fix confirmed, mutants, suite

## Decisions
(filled as made)

## Reproduction on the real plate (sha256 8a2b230a4e13cb3f..., 85484 B, verified), crackle 674041c
- qa_stl: PRINTABLE 28 up / 214 flipped z 2.4..2.6, 16 excused; LAYERSUP 12 overhang 13.3 mm2 worst 1.5 slope; 8 bridges. Matches print-kb.
- plane 8 z 2.21: 4 step bridges (x 26.24..33.76 y 34.56..35.46 etc.) + 4 slope overhang strips inside them (1.12, 0.72 mm2).
- plane 9 z 2.45: 4 step bridges (x 26.5..27.5 y 35.86..40.16 etc.) + 4 slope strips at x 27.35/32.65/10.35/13.65.
- plane 10 z 2.69: 4 slope strips (1.17/1.22 mm2) at x 28/32 y 36.06/39.96, no step region. They sit next to the
  plane-9 bridges, not inside them: skipping only same-plane bridge xy would not clear them.

## Decisions
- D1 (readiness Q1): bridge xy from every plane between the slope base and the current plane (inclusive) JOINS the
  slope base, grown by the same allowance. A bridge is a new floor; everything above it compares against it.
  Reason: plane-10 strips are beside, not inside, plane-9 bridges, so same-plane exclusion leaves them.
- D2 (readiness Q2): PRINTABLE excuses a downward face when its centroid xy, on the first plane above the centroid
  (within one layer), lies in material the step test found inside the grown layer below (every unsupported piece,
  noise included, removed; slope overhang removed). No xy tolerance. Applies upright and flipped. Reason: exact,
  and a real roof's centroid sits in an unsupported piece. Risk: a big fan triangle whose centroid lands on held
  material while part of it hangs is excused; the rest of that roof's faces still count.
- D3 (Q3): plate fetched and verified, no rebuild needed.
- D4 (Q4): fixture = 30x20x4 tiled boxes, 7x9 void from the bed, layer A z 2.4-2.64 two 7 mm bridges + 2 mm slot
  + 0.5 mm side gaps, layer B z 2.64-2.88 bridges across the slot, 2 mm hole, 0.5 mm end gaps. On 674041c code it
  reads 2 bridges + slope overhang 10.12 mm2 x2 at z 2.45 and 2.6 mm2 x2 at 2.69 (claim 1), and PRINTABLE counts 8
  upright faces, the end-gap ceilings (claim 2). Cells are merged into x runs: touching boxes split a bridge.
- D5 (Q5): rerun only the sweep's 15 FAIL files (either line FAIL) via reports/a1-sweep/slope-bridge-resweep.sh;
  both changes only lower counts, so only a FAIL can move.

## Verdicts
- Claim 1 CONFIRMED (plate: 8 slope strips at planes 8-9 inside the step bridges, 4 at plane 10 beside them).
- Claim 2 CONFIRMED (plate: 24 of the 28 upright faces are held within allowance; 4 remain, see below).

## After the fix (d1a3e88), plate
- LAYERSUP PASS: 0 overhang, 8 bridges. PRINTABLE FAIL: 4 upright, 124 flipped, z 2.6; 40 faces excused.
- The 4: fan triangles at z 2.641 by the big holes, centroids (28.19, 35.82) etc. At plane 2.69 x 27.74..28.69 is
  unsupported (the hole's corner past the plane-9 bridge, under the noise floor, so LAYERSUP drops it). Not
  excused by design: it is not held. Whether sub-bead pieces should excuse faces is a separate policy call.
