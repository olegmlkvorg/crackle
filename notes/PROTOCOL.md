# Phase 1 run protocol — is the crackle controllable?

## ⚠️ Before you print anything (2 minutes, saves hours)
1. **Turn OFF AI detection: Settings → Camera → AI function → uncheck "fault pause" / disable AI
   detection.** (Creality's own wiki, code AC0101, applies to K2 Plus.) This print is *deliberately*
   a spaghetti web — the camera is built to spot exactly this and pause the job.
   **Also: clear and wipe the plate between coupons.** A plate still webbed from the previous run
   trips **AC0104 "foreign object detected"** at Z-homing, *before* the print starts.
2. **`push.py` uploads AND starts** (changed 2026-07-25 — Oleg: *"i have way higher risk tolerance
   then you"*). `--no-start` opts out. The reported remote-start head-crash bug is real but is an
   unhomed-axis failure, and it fails safely on this toolchain: no-home files error with "Must home
   axis first" rather than crashing. The one non-overridable guard remains: never overwrite the file
   Klipper is currently streaming, which is corruption rather than caution.
3. **Bed:** clean PEI, 60 °C, slightly generous first-layer squish. The nozzle drags across the part
   all print; a lifted lattice ruins the coupon and is a rig problem, not a result.
4. **Have tweezers and a spare nozzle wipe handy.** Retraction is off for the whole print — ooze
   accumulates. If a run ends in a blob, add `wipe_every=5` and rerun.
5. **These are hand-emitted gcode files.** `validate.py` checks them structurally (no backwards E,
   no Z ploughing, nothing off the bed) but it cannot know your machine. Watch the first 30 s.
6. **THE FAILURE MODE VALIDATE.PY CANNOT SEE — physics, not syntax.** On 2026-07-25 a flow tower
   printed 3 mm-wide lines from a 0.8 mm nozzle. The file was perfect; the physics was not. A round
   orifice cannot spread 1.2 mm2/mm to 3 mm, so the bead landed ~1.4 mm wide and therefore ~0.86 mm
   TALL against a 0.4 mm Z step — the part climbed ~0.46 mm per layer past the nozzle, which
   ploughed into it and dragged it off the plate at 56%.
   **Narrow bead means TALL bead means collision.** Two rules came out of it:
   - Anything that STACKS keeps commanded line width <= 1.5x nozzle. `crackle.py` now refuses
     otherwise and prints the arithmetic.
   - Anything wanting fat, visible beads is a **single layer**, where nothing can collide with
     itself and any commanded width is safe. That is why `flowtest.py` is one layer.

## Already on the printer
`crackle_B_…` and `crackle_A_…` are **uploaded to the K2 Plus** (192.168.3.140) and waiting in the
file list. The start block is taken **verbatim from this laptop's own Creality Print K2 Plus 0.4
profile** — `START_PRINT`/`END_PRINT` macros, adaptive-probe bounds, `T0` for the CFS — so homing and
the strain-gauge Z-probe behave exactly as they do for a normal sliced job.
Push more with `python3 push.py out/crackle_G_*.gcode` (it refuses a busy printer unless `--force`).

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

### ⚠️ B vs A is CONFOUNDED — use Bpas2 as the real control (found 2026-07-25)
B is 2.60 g and A is 4.63 g: **A has 78% more plastic.** Star order produces longer strands AND more
crossings at the same time, so "A crackles, B doesn't" is equally explained by *more material*. The
thesis is about crossings, so material has to be held constant or the verdict means nothing.

**`crackle_iter_Bpas2_…` = perimeter order, 2 passes, 4.35 g, 0 crossings** — within 6% of A's mass.
That is the negative control the thesis needs: same plastic, no crossings.

| coupon | crossings | mass | role |
|---|---|---|---|
| B (1 pass) | 0 | 2.60 g | low-material end; keep, but not the control |
| **Bpas2** | **0** | **4.35 g** | **mass-matched negative control — run this against A** |
| A | 77 | 4.63 g | the working coupon |

If A crackles and **Bpas2** is silent, crossings are the mechanism and material is ruled out.
If Bpas2 crackles like A, it was never crossings — it is strand length/thinness, and the dial to
build is `strand_w` and pass count, not visit order.

**Run order: Bpas2 → A first.** Those two alone answer the Phase 1 question. If B is silent and A
crackles, the effect is controllable and everything after is calibration. If they feel the same, the
thesis is dead and you've spent nine minutes learning it.

## If A crackles: the dose-response ladder (already on the printer)
The single strongest confirmation of the thesis isn't "A crackles" — it's **more crossings → more
crackle, monotonically**. That ladder is generated and uploaded:
`crackle_fast_An4/An5/An6/An7` = **77 → 205 → 524 → 954 crossings per layer**, constant thickness
(12 layers, so none has more material to crush than another), 0.54–0.93 g each.
If loudness climbs with the number and then plateaus, you've found the useful range and the mechanism
is confirmed. If it's flat or random, crossings aren't the driver even if A beat B.
Times rise with density (3.9 / 6.1 / 9.4 / 13.8 min) — that's inherent: more crossings means more
travel moves. Sweep anything else the same way: `--vary passes=1,2,4`, `--vary temp=210,230,250`.

## Machine calibration comes first (`flowtest.py`)
Every coupon speed used to be a number I invented. They are now derived: `crackle.py --max-flow <n>`
sets working flow to 0.85 x measured and computes strand and pillar speeds from it. So measure first.

`flowtest.py` prints a **single-layer Archimedean spiral**, flow ramping outward, ~7 min:
- **Spiral, not rows** — serpentine reverses 180 degrees at every row end, so the head decelerates
  and never reaches commanded speed. A flow test that does not reach commanded speed measures the
  motion planner, not the hotend. A spiral never turns.
- **Outward ramp** — highest flow lands at the largest radius, the gentlest curvature on the plate.
- **Fan 20%** — full fan chills the melt and would read as the flow ceiling. A melt-rate test must
  not have a second cooling variable fighting the hotend.
- **Bump spoke** — at every 5 mm3/s the spiral makes a 1 mm outward pimple, all at the same polar
  angle, so they line up into one radial spoke. Count outward from the centre. It is a shape change,
  never a gap, so it cannot be mistaken for the extrusion failure being hunted.
- **Turn spacing = commanded width**, so the gaps between turns measure true landed bead width free.
- `python3 where.py` prints the live mm3/s being extruded at this instant.

Read it: find where the bead stops being continuous plastic. That is the ceiling; use 85% of it.

## Why it still "calibrates" — and the file set that doesn't
**The expensive ceremony is inside `G28` on this machine, not only in `START_PRINT`.** The K2 probes
with a strain gauge *through the nozzle*, so its homing routine heats to 140 °C and probes. Dropping
`START_PRINT` didn't remove that, because `G28` triggers it too.

Three tiers, pick by situation:
| prefix | homes? | when |
|---|---|---|
| `crackle_X_…` | full `START_PRINT` | first print of a session, or after any doubt about Z |
| `crackle_fast_X_…` | plain `G28` | fresh session, skip the macro ceremony |
| **`crackle_iter_X_…`** | **no homing at all** | **back-to-back coupons — the actually-fast one** |

The `iter_` files also **leave the steppers energised at the end**, because `M84` would drop the
homed position and force the next coupon to re-calibrate. So: print one `fast_` coupon to establish
home, then run `iter_` files all afternoon.
**If the machine was powered off or the steppers disabled in between**, an `iter_` file fails safely
with "Must home axis first" — it errors, it does not crash.

## Fast iteration (`crackle_fast_*` files)
The normal files call Creality's `START_PRINT`, which heats to 140 °C, homes, cleans the nozzle,
re-homes Z, reheats and cleans **again** — often longer than the 4-minute coupon itself. The
`crackle_fast_*` variants skip all of that: heat, one `G28`, a short prime, go. They also park the
head high and to the front at the end so you can grab the coupon immediately.

**What is deliberately NOT removed: `G28`.** Homing isn't ceremony — Klipper refuses to move an
unhomed axis, and a wrong Z gouges the plate.

**The honest trade-off:** without a nozzle clean before probing, an oozy nozzle can bias Z slightly.
This print doesn't need a pretty first layer, it needs the lattice to *stick*. Eyeball the first
layer on your first fast run. If adhesion goes bad, run one normal (non-fast) coupon to re-establish
a clean Z, then go back to fast.

## Telling them apart afterwards
Six identical black squares are unscoreable in a pile, so each coupon has **raised tally bars on its
base** — count them by eye or by fingertip:
**1=B · 2=A · 3=C · 4=D · 5=F · 6=G** (7=E). That's also why blind scoring works: someone can hand
you a coupon face-up and you can identify it afterwards without having seen the filename.

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
