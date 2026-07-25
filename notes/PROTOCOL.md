# Phase 1 run protocol — is the crackle controllable?

## ⚠️ Before you print anything (2 minutes, saves hours)
1. **Turn OFF the AI / spaghetti detection on the K2 Plus.** This print is *deliberately* a spaghetti
   web. The failure-detection camera is designed to spot exactly this and pause or abort the job.
   (Being verified; do not skip it on my say-so — just check the toggle before the first run.)
2. **Bed:** clean PEI, 60 °C, slightly generous first-layer squish. The nozzle drags across the part
   all print; a lifted lattice ruins the coupon and is a rig problem, not a result.
3. **Have tweezers and a spare nozzle wipe handy.** Retraction is off for the whole print — ooze
   accumulates. If a run ends in a blob, add `wipe_every=5` and rerun.
4. **These are hand-emitted gcode files.** `validate.py` checks them structurally (no backwards E,
   no Z ploughing, nothing off the bed) but it cannot know your machine. Watch the first 30 s.

## The experiment
**Thesis:** the crackle is fused strand *crossings* breaking. If true, crossings-per-layer predicts
crackle, and it is computed for you — it's in every filename.

| Coupon | Order | crossings/layer | What it tests | ~time |
|---|---|---|---|---|
| **B** | perimeter | **0** | **Negative control.** If B crackles, the thesis is WRONG — stop and rethink. | 3.5 m |
| **C** | serpentine | **0** | Second negative control (different path, still no crossings). | 4.1 m |
| **A** | star | **77** | The working coupon. | 5.3 m |
| **D** | maxcross | **66** | Different high-crossing path — does the *number* predict it, or the pattern? | 5.2 m |
| **E** | star ×3 passes | 77/layer, **3× total** | Density at constant order. Travel-only cost. | 12.7 m |
| **F** | star, **fan 255** | 77 | Does welding matter? Fan should stop crossings fusing → should go quiet. | 5.3 m |
| **G** | star, 6×6 finer | **524** | Fine web — the high end of the dial. | 7.0 m |

**Run order: B → A first.** Those two alone answer the Phase 1 question. If B is silent and A
crackles, the effect is controllable and everything after is calibration. If they feel the same, the
thesis is dead and you've spent nine minutes learning it.

## Scoring (stand on it, barefoot, same floor each time)
Record for each coupon — 1–5 unless stated:

| Field | Meaning |
|---|---|
| **loudness** | crackle on FIRST compression |
| **compressions_to_quiet** | *count them.* **This is the number that decides product vs novelty** (PRD §2). |
| **recovery** | none / partial / full — does it spring back or stay crushed |
| **character** | good ↔ "standing on gravel". A 5 for loudness with a 1 for character is a failure. |
| **notes** | anything the numbers miss |

Write results into `notes/RESULTS.md` (template there). **Score blind if you can** — have someone
hand you coupons without saying which; expectation is a real bias here.

## What each result would mean
- **A crackles, B doesn't** → controllable. Then dial with G (more crossings) and E (more density).
- **A and B both crackle** → crossings aren't the mechanism; it's the loose strands themselves.
  Next hypothesis to test: strand *length* and *thinness*, not crossings.
- **Nothing crackles** → the effect needs the scale/tangle of a real failed print; coupons are too
  clean. Try a 2× larger coupon before abandoning.
- **Everything crackles once, then goes quiet** → it's a one-shot crush. That's a **novelty in PLA**,
  and the honest Phase 1 answer. Phase 2 (TPU/PETG, elastic recovery) becomes the whole question.
  The generator is already material-agnostic — only temp/fan/flow change.

## Deliberate deviations from the PRD (and why)
1. **Travel order promoted from last axis to first.** It's the only variable that moves
   crossings-per-layer by 10×; temp and fan only decide whether crossings *weld*.
2. **Crossings are computed, not swept blindly** — a segment-intersection count per layer, printed
   into the filename. You dial a number.
3. **Lattice base instead of a solid slab.** A solid base was 88% of print time and blew the 6-minute
   budget (the validator caught it). Frame + a rib through every pillar row/column anchors everything
   against nozzle drag and keeps the coupon peelable and standable, at ~1/8 the extrusion.
4. **Visit order rotates per layer** so crossings distribute through the volume instead of stacking
   into welded vertical columns — which would press like the hex grid rather than crackle.
