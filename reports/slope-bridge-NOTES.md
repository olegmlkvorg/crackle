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
