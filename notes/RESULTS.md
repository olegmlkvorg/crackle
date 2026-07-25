# Phase 1 results — fill in while standing on them

Score barefoot, same floor. Identify coupons by the **raised tally bars on the base**.

## Round 1 — is there an effect at all? (9 minutes)
| tally | coupon | crossings/layer | loudness 1-5 | compressions_to_quiet | recovery | character 1-5 | notes |
|---|---|---|---|---|---|---|---|
| 1 | **B** perimeter | **0** | | | | | NEGATIVE CONTROL — should be silent |
| 2 | **A** star | **77** | | | | | the working coupon |

**Read it:** A crackles + B doesn't → effect is real and controllable → run the ladder.
Both crackle → crossings aren't the driver; the loose strands themselves are. Next test: strand
length/thinness, not crossings. Neither crackles → coupons may be too clean/small; try 2× size once.

## Round 2 — the dose-response ladder (only if round 1 is positive)
The number that proves the *mechanism*, not just the effect. Constant thickness across all four.

| tally | coupon | crossings/layer | loudness | compressions_to_quiet | recovery | character | notes |
|---|---|---|---|---|---|---|---|
| 1 | An4 | 77 | | | | | |
| 2 | An5 | 205 | | | | | |
| 3 | An6 | 524 | | | | | |
| 4 | An7 | 954 | | | | | |

**Read it:** monotonic rise then plateau → mechanism confirmed, and the plateau is your useful range.
Flat or random → crossings are not the driver even if A beat B.

## Round 3 — the other axes (as needed)
| coupon | what it isolates | result |
|---|---|---|
| C serpentine (0) | second negative control, different path | |
| D maxcross (66) | does the NUMBER predict it, or the pattern? | |
| F fan 255 (77) | does welding matter? fan should kill it | |
| E ×3 passes | density at constant order | |

## The verdict
**compressions_to_quiet is the number that decides this.** Under ~3 in PLA = novelty, and Phase 2
(TPU/PETG, elastic recovery) becomes the real project rather than a scaling exercise.

_(Write the honest answer here — including "chaotic and unrepeatable" if that's what it is.)_

---

# Round 0 — machine calibration (must land before any coupon score means anything)

Phase 1 coupons were generated with strand/pillar speeds I had *invented*. They are now derived from
measurement instead: `crackle.py --max-flow <n>` sets working flow to 0.85 × measured and computes
both speeds from it. So the flow number gates everything below it.

## 2026-07-25 — flow tower FAILED (design error, mine)
Not a material result. `flowtest.py` v1 stacked a single-wall tower with 3 mm commanded lines from a
0.8 mm nozzle. Commanded cross-section (3 × 0.4 = 1.2 mm²/mm) is conserved, but a round orifice
cannot spread that to 3 mm — the bead landed ~1.4 mm wide and therefore **~0.86 mm tall against a
0.4 mm Z step**. The part climbed ~0.46 mm/layer past the nozzle; by ~10 layers the nozzle was
several mm deep in the part, ploughing sideways, and it dragged the tower off the plate. Cancelled
at 56%. Oleg diagnosed it live from the camera before I did.

**Banked:** narrow bead means tall bead means collision. Anything that STACKS keeps commanded width
≤ 1.5 × nozzle — now enforced by a guard in `crackle.py` that refuses and prints the arithmetic.

## The replacement: single-layer full-plate ramp
`flowsheet_nohome_pla_T230_42-86.gcode` — one layer, 96 rows, 320 mm each, flow interpolated per
row (0.46 mm³/s per row). A single layer cannot collide with itself, so wide commanded lines are
safe, which is what makes the filament visible at low speed.

| decision | why |
|---|---|
| one layer | removes the collision failure mode entirely |
| straight 320 mm rows, not a space-filling curve | a Hilbert path is all corners; you never reach commanded speed, so you'd measure the motion planner instead of the hotend |
| fan 20%, not 100% | full fan chills the melt and would read as the flow ceiling — a confound in a melt-rate test, plus curl/lift on a 46 g single layer |
| per-row ramp, not repeated bands | a row is already ~11 s of continuous extrusion, well past steady state; repeating it spends 8× the plate to learn one number |
| row spacing = commanded width | the gaps *measure* true landed bead width for free — the number I was guessing when the tower died |
| notch every 5 mm³/s | the plate labels itself; count teeth on the right edge, no ruler |
| floor raised 34 → 42 | Oleg: still perfectly fine at 24% of the prior run |

### RESULT 2026-07-25 (refined) — **max flow = 81.2 mm³/s**
Zoom run 76→90 with a pimple per 1 mm³/s: first skip at 20% of path = **81.2 mm³/s**, r75 mm.
The two runs agree within 2.4% (83.1 → 81.2), so the hot-bed slumping I flagged was real but small.
It flattered the first reading; it did not invalidate it. **Working = 0.85 × 81 = 68.8.**

### ⚠️ The measurement does NOT bind the coupon — and my "no invented numbers" claim was wrong
Both derived speeds hit **hardcoded caps I wrote**: working flow wants 344 mm/s for strands and
191 mm/s for pillars, and `crackle.py` clamps to 200 (travel_f 12000) and 150 (print_f 9000). So
83 and 81 produce byte-identical coupons, and anything above ~55 mm³/s would too. The flow ceiling
binds the wide-line single-layer work (flow sheet, Z-spiral), not the coupon.

The caps are not indefensible — 200 mm/s sits well inside the machine's 800, and strand speed
*should* plausibly be bounded because **contact time at a crossing is what decides whether it
welds, and welding is the crackle mechanism**. But that is a physical claim to test, not a constant
to pick. **TODO: sweep it** — `--vary travel_f=6000,12000,24000` belongs beside the fan axis, since
both are testing the same thing: whether crossings fuse.

### Earlier reading (superseded, kept for the record) — 83.1 mm³/s
Oleg, watching live: *"72% we get first skips."* 72% of path on the 50→90 spiral = **83.1 mm³/s**,
radius 137 mm, 69 mm/s commanded. The bump spoke corroborates it independently: the 80 pimple sits
at r127 and the 85 pimple at r145, so the skips begin between the 6th and 7th pimple, nearer the 7th.

    max stable flow = 83.1 mm³/s  →  working = 0.85 × 83 = 70.5

Speeds now derived rather than invented: **strand travel 200 mm/s, pillar 150 mm/s**. Both are
within the machine (max_velocity 800, max_accel 30000) and both sit under the ceiling in their own
geometry — strand 0.5×0.4mm at 200 mm/s = 40 mm³/s, pillar 0.9×0.4 at 150 = 54 mm³/s. Note that
strand E is computed per mm of PATH, independent of speed, so if Klipper ever clamps a feedrate the
deposited geometry is unchanged — only the time is. That makes the coupon robust to speed clamping.

**Caveats worth holding, because 83 is very high for a 0.8 nozzle** (typical high-flow 0.8 is
40–60):
1. **Bed at 135 °C** keeps PLA far above its glass transition for the whole print, so beads stay
   soft and can slump together. Mild under-extrusion may have been masked, meaning the true onset
   could be below 83 — what we detected is where it became *undeniable*.
2. **Single layer on a hot plate is the most forgiving condition possible.** In a stacked print with
   cooling on, the usable ceiling will be lower.
   If coupons come out under-extruded, drop to 0.75 × 83 ≈ 62 rather than re-measuring.

**Zoom run staged:** `flowspiral_nohome_pla_T230_76-90.gcode` — 76→90 over the whole plate,
0.31 mm³/s per turn, **a pimple every 1 mm³/s** (77…89) so the onset can be read to the unit.

landed bead width = 3.0 − (gap) = ______ mm   _(measure between spiral turns once cool)_

## Next, gated on that number
1. `crackle.py --sweep all --fast --no-home --max-flow <n>` → regenerate B and A, run Phase 1.
2. `zwave.py --no-home --flow <working>` → Oleg's Z-during-extrusion sweep (`notes/Z-MODULATION.md`).

### Weld-time ladder (generated, gated behind B/A)
`crackle.py --preset A --fast --no-home --vary travel_f=6000,12000,24000` → strand speed
**100 / 200 / 400 mm/s** at identical geometry (all 4.63 g, 77 crossings/layer — verified, so it is
a genuine one-factor sweep). Tests the claim behind my hardcoded speed cap: that contact time at a
crossing decides whether it fuses, and fusing IS the crackle mechanism. Same question the fan axis
asks, approached from the other side — fan removes heat, speed removes time.

**Caveat:** over the shortest moves (20 mm pitch) at M204 S8000 the peak reachable speed is
sqrt(8000 × 20) = 400 mm/s, so the fastest variant is right at the accel limit on short moves and
fully reached only on long diagonals. The effective spread is therefore under the nominal 4×.
Read it as a ladder, not as calibrated speeds.

---

# ⭐ PHASE 1 ANSWERED — 2026-07-25, weave pair

**Oleg, on the two coupons: "second one is way better."** Second = `weld1` = **fused**.

The pair was the cleanest test built: identical geometry, identical 2.71 g, identical 10.9 m path,
identical 372 crossings, printed back-to-back on ONE plate in ONE session (so bed temp, ambient,
spool and nozzle state are shared, not drifting). The only difference in either file is whether Z
rose when the path crossed its own line.

| coupon | crossings | lifts | result |
|---|---|---|---|
| weld0 | 372 | 372 — fully woven, nothing fuses | worse |
| **weld1** | 372 | **0 — every crossing fused** | **way better** |

**Verdict: welding IS the mechanism.** The sound comes from fused junctions snapping, not from
mechanical interlock between woven strands. Crossings matter *because they weld* — so the dial is
weld state first, and crossing count second as the thing that sets how many welds exist.

**`--weld` is now the primary control**, ahead of fan and temperature. Those two were only ever
indirect proxies for the same variable; `--weld` sets it per crossing, deterministically.

## Defect found on the printed coupon (Oleg: "why the extrusion lines are not solid, are you retracting?")
Not retraction — 15,001 extruding moves, zero retracts (the one E decrease is the G92 reset).
**strand_w was 0.5 mm from a 0.8 mm nozzle: 0.62x the orifice.** A nozzle cannot deposit a bead
narrower than its own hole; the melt is drawn thin and breaks into discontinuous beads, which reads
exactly like retraction stringing. This is the MIRROR of the morning's tower failure — that one
commanded a width far too WIDE (bead landed tall, ploughed the part off the plate), this one far too
NARROW. Both silent, both syntactically valid, both invisible until something physical was examined.

v1 made this same mistake with `line_w` (0.6 from 0.8) and it was fixed; it returned when `strand_w`
was decoupled from `line_w` and set to 0.5 without re-checking against the orifice. **Guard added:
weave.py refuses strand_w < 0.8; defaults raised to 0.85.**

## Next
1. Re-run the pair at strand_w 0.85 to confirm the verdict holds with solid strands (a broken-up
   strand may have handicapped the WOVEN one more, since its lifted spans bridge in air).
2. `--weld 0.25 / 0.5 / 0.75` — is the response monotonic? If loudness tracks weld fraction, the
   mechanism is confirmed twice over and the dial is calibrated.
3. Only then return to crossing COUNT as a secondary axis.

---

# RETIRE THE PILLAR LATTICE — measured 2026-07-25

Oleg pushed twice: "why are you not doing continuous?" and "not sharp angles, use semi circlish
always". Both are the same insight, and the pillar-and-strand lattice violates both. Measured with
the corrected junction model (Klipper's own, validated: a 90-degree corner yields exactly its
square_corner_velocity of 5 mm/s):

| design | speed | junctions | member mean | path below 90% of commanded speed |
|---|---|---|---|---|
| pillar chords (coupon A) | 200 mm/s | 70 | 32.7mm | **93%** |
| lissajous 5:7 | 235 mm/s | 54 | 8.4mm | **7.8%** |
| lissajous 7:9 | 125 mm/s | 108 | 5.6mm | **2.0%** |
| lissajous 9:11 | 125 mm/s | 176 | 4.3mm | 3.5% |

**The coupon never ran at its commanded speed.** 93% of its path is corner-limited, so the carefully
derived "strand 200 mm/s" was fiction — the head crawled through the turns. Every coupon printed
before today shares this.

**Filleting cannot rescue it.** Star order makes near-reversals; rounding them at the minimum radius
that holds 200 mm/s (5.0mm) collapses the path from 894mm to 426mm and junctions from 70 to 46. The
corners ARE the design. You can keep them or keep the speed.

**The continuous curve wins on every axis simultaneously**: holds speed, MORE junctions, and much
shorter members between them (5.6mm vs 32.7mm) — short slender spans snap, long ones bend, and
bending is the quiet hex-grid feel that started this project.

## Design rule that falls out
At max flow the head moves fast, so curvature is the binding constraint on how many crossings fit:
9:11 costs 23.8% speed loss at 235 mm/s but only 3.5% at 125. To raise crossing density at max flow,
make the COUPON BIGGER (more path between crossings at the same curvature) rather than raising the
frequency pair.

## Consequence
`weave.py` (lissajous + per-crossing weld control) is now the coupon generator. `crackle.py` stays
for the historical pillar sweep and its measured comparison, but Phase 2 runs on weave.

---

# WELD LADDER — the monotonicity test (printing 2026-07-25)

The strongest available confirmation of Phase 1. Phase 1 compared the two extremes; this asks
whether the response is **monotonic across the middle**, which is much harder to explain any other
way.

**Five rungs, identical to the gram.** Same path, same crossings, same 8.027 g, same 70 mm³/s,
printed back-to-back in ONE session so bed temperature and nozzle state are shared. The only
difference in the five files is how many crossings the nozzle lifts over.

| plate x | `--weld` | lifts | meaning | loudness | compressions_to_quiet | character |
|---|---|---|---|---|---|---|
| 20 | 1.00 | 0 | every crossing FUSED (Phase 1 winner) | | | |
| 85 | 0.75 | 144 | | | | |
| 150 | 0.50 | 288 | half and half | | | |
| 215 | 0.25 | 432 | | | | |
| 280 | 0.00 | 592 | every crossing WOVEN, nothing fuses | | | |

**Score barefoot, same floor, ideally in a shuffled order** — position on the plate reveals which is
which, and expectation bias is real here.

## What each outcome means
- **Monotonic rise toward weld 1.0** → fusing confirmed a second, independent way, and the dial is
  calibrated in the same print. Build on it.
- **Flat or erratic** → the Phase 1 fused-vs-woven difference came from something other than weld
  state. Re-examine before building further.
- **PEAK IN THE MIDDLE** → the most interesting result: some fused junctions are needed to store
  elastic energy, but too many make the structure rigid enough to BEND rather than snap. The optimum
  would then be a mix, and `--weld` becomes a tuning parameter rather than a switch.

**compressions_to_quiet is the number that decides product vs novelty.** Under ~3 in PLA and the
honest answer is novelty, making Phase 2 (TPU/PETG, elastic recovery) the real project.

## Also being tested by this run
First sustained multi-print series at the corrected **70 mm³/s** (dropped from 80 after Oleg heard
the extruder cracking). If the cracking is gone across five back-to-back prints, the ear-based
ceiling holds.
