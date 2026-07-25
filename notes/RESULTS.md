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

**Result:** _(record the flow where the surface stops being continuous plastic, and the landed bead
width measured from the row gaps)_

max stable flow = ______ mm³/s → working = 0.85 × ____ = ______
landed bead width = 3.0 − (gap) = ______ mm

## Next, gated on that number
1. `crackle.py --sweep all --fast --no-home --max-flow <n>` → regenerate B and A, run Phase 1.
2. `zwave.py --no-home --flow <working>` → Oleg's Z-during-extrusion sweep (`notes/Z-MODULATION.md`).
