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
