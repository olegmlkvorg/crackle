# lamp — a table lamp whose shade is one continuous toolpath

**STAGE: PROPOSED. Nothing is generated, nothing is printed, and the send ledger holds nothing
for the nozzle this will print on.** Oleg, 2026-09-27: *"our gcode lamp design"*. The K2 Plus
carries a 0.4 nozzle since 2026-09-25 (his words). Every row of `machine.PROVEN_LAYER1` and
`machine.PROVEN_SEND` was measured on the 0.8, and so were `machine.NOZZLE` (still `0.8`),
`BEAD_W`/`BEAD_H`, `SLICER_LINE_W` and `SLICER_LAYER_HEIGHTS`. The last send in `send-log.jsonl`
is the hanger-tag night, 2026-08-31. **Only the temperatures transfer**, because they belong to
the filament and not to the nozzle (CLAUDE.md, "what is genuinely ABSOLUTE").

## What it is

Three pieces:

| piece | made by | what it does |
|---|---|---|
| **shade** | a new generator, `lamp.py`, native gcode | one helical stroke from the first bead to the last. The wall is a sine ripple whose phase flips every lap, so the wall carries **empty vertical cells inside its own thickness**. Open top, open bottom: the shade is a chimney. |
| **light core** | bought | an aluminium tube standing upright, a low-voltage LED strip bonded along it, USB-C power |
| **base** | native gcode, `solid.py` family | holds the tube upright on three contact ribs (`solid.shaft_socket`), sand-filled for weight (`solid.py --cavity`) |

The shade never touches the core. The light's heat is carried by metal and air, and plastic
meets the metal only at the base, at three lines of contact.

**Why the wall is toolpath-native.** A slicer's vase mode draws one line around a shape. It cannot
flip the ripple phase between laps, and the phase flip is the entire mechanism that makes the
cells. In the translucent PLA this repo was built on (`machine.py`, the TEMP note: *"Translucency
is what makes the object look like alien tech"*) the cells read as light, and the nodes where the
strands weld read as bright ribs.

## The wall: what a phase-flipped sine can and cannot do

Oleg asked what sine patterns can teach us about leaving empty vertical spaces during the print.
The mechanism is in FullControl's `models/ripple_texture.ipynb`: the radius follows
`cos((ripples_per_layer + 0.5) · θ)`. The extra half ripple per revolution puts every lap exactly
π out of phase with the lap below it. As FullControl ships it (`rip_depth 1` against `EW =
2.5 × 0.4 = 1.0`), the ripple depth equals the bead width, so neighbouring laps still overlap
everywhere and the result is a texture with no voids. **A void opens only when the peak-to-peak
ripple exceeds the bead width.** Past that point, the Z pitch decides which of two walls you get:

| | Z pitch | what forms | support | open problem |
|---|---|---|---|---|
| **O1 lace** | `lh` per lap | odd laps and even laps form two interleaved wavy sheets meeting at nodes. The vertical cells sit between them. | Each lap lands on the lap below only near the nodes. Between nodes it spans one layer height of air above its in-phase lap two below, and it sags onto that lap. | The sheets carry one-`lh` slits that sag closed or stay as lace. Which one is a plate question. |
| **O2 braid** | `lh` per **two** laps | two out-of-phase strands per logical layer, lens-shaped closed cells, stacked straight up as vertical tubes | Full. Every strand lands on its own in-phase copy one layer below. This is `bucket_towers.py:952`'s "C full ring circuits at lh/C height steps", with C = 2. | **Double deposit at every node.** The second strand crosses the first only `lh/2` above it. The in-house fix is `bucket.crossing_z` (only the later strand lifts, ramped). The in-house warning is Oleg on 2026-08-05 (`bucket_towers.py` docstring): *"you was not hitting adhesion with all this z up and down movements"*. |

**What no sine can do: a see-through window.** A lap that circles the light blocks every radial ray
at its height, so a wall built from planar laps around the axis is opaque in projection however
the laps ripple. Phase flips make voids *inside* the wall, never through it. A single stroke gets
a real opening in one of two ways:

- **a reversal.** The path turns back at an edge and returns one layer up, which is the
  C-channel. It yields exactly one slot, and the shade uses that slot as its **cable exit**: the
  bottom ~8 mm reverses, then the helix closes over the slot with an ~8 mm bridge.
- **posts and bridges.** `bucket_towers.py` is the only open wall this house has proven: the
  f3x4r1c bucket, "Perfect bucket", 2026-08-08, with 62.25 mm spans. That evidence was taken on
  the 0.8.

Q1 below asks which wall he wants.

### Constraints that choose the numbers

Illustrative operating point: a Ø150 × 200 mm shade, bead 0.60 × 0.28 (1.5× and 0.7× the 0.4
nozzle, inside the house stacking ceiling), wavelength 12 mm, peak-to-peak ripple 4 mm.

| constraint | source | consequence here |
|---|---|---|
| corner radius `R ≥ v²/a` | `smooth.py` docstring | at the 50 mm/s north star and the measured `machine.ACCEL` 5000, R ≥ 0.5 mm. A sine crest has `R = λ²/(4π²·a)` with `a` the half amplitude, so a 4 mm ripple needs λ ≥ 6.3 mm. The 12 mm default gives R 1.8 mm. FullControl's `RippleSegs = 2` zigzag has R = 0 and is refused. |
| move rate ≤ `MAX_MOVES_PER_SEC` 300 | `machine.py` | segments ≥ 0.17 mm at 50 mm/s. Plan 0.5 mm, about 100 moves/s. |
| ripples per lap | derived | `N + 0.5 = C/λ`. Ø150 gives C 471 mm, so N = 39 (39.5 ripples, λ 11.9 mm). |
| node crossing angle | derived | strand slope at the node is `2πa/λ` = 1.05, so the strands cross at 93° and the node overlap is about `w²` = 0.36 mm². That is what `crossing_z` would lift over in O2. |
| O1 unsupported run | derived | supported only where the lap offset `2a·sin φ` < w, about 10% of each half wave. Runs are about 6.7 mm over a 0.28 mm drop. `PROVEN_AIR_MM` 16.8 is a 0.8 figure and is not cited as evidence. |
| profile change per layer | `pulley.py` 40° bound | a bulge or taper may move the wall at most `lh·tan 40°` = 0.23 mm per layer |
| flow | CR-PLA 0.4 profile `filament_max_volumetric_speed` 18, Generic PLA 14 | 0.168 mm² × 50 mm/s = 8.4 mm³/s. The north star holds with no derate. |
| the ripple is geometry, never flow or speed | R3, R4 | constant bead and one speed throughout. Painted flow or speed (Nozzleboss, velocity painting) is refused. |

Path is about 585 mm per lap: the sine lengthens the 471 mm circle by about 24%. **O1** is 714
laps, 418 m, **about 2.3 h and 87 g**. **O2** is 1428 laps, 835 m, **about 4.6 h and 174 g**.
Both exceed `LONG_PRINT_MIN` 90, so a shade cannot go out on rule-6 grants. Coupons must be read
and `send.py accept`ed first.

## How it prints on the K2 Plus 0.4

**Step 1 is code, not a plate.** `machine.py` needs a per-nozzle table: bead ceiling, the 0.4
profiles' layer heights `(0.08, 0.12, 0.16, 0.20, 0.24, 0.28)`, line width 0.42 (all read
2026-09-27 from `Creality Print.app/.../process/*@Creality K2 Plus 0.4 nozzle.json`), and
`PROVEN_LAYER1`/`PROVEN_SEND` keyed by nozzle as well as machine. Today a 0.4 file is judged
against 0.8 evidence. `NOZZLE` is not edited in this commit, because every generator reads it.

Temperatures: 210 nozzle and bed 60, from `PROVEN_SEND temps`, if the translucent 210 PLA is
still the spool in `machine.LOADED`. Part fan follows the hanger-tag precedent for sub-millimetre
single-line walls (`machine.FAN_MAX` scope note, 2026-08-31): none on the pressed first lap, full
on the wall.

Plates, each sent only on Oleg's go:

| plate | what | time (motion) | reads off it |
|---|---|---|---|
| **P1** | 0.4 first-layer `Z_LADDER` plus an `L1_BENCH` rate sweep, reusing `zladder.py` and the hanger-tag benches | ~10 min | the first `PROVEN_LAYER1` row for the 0.4, and whether the thread leak from 2026-08-31 is still there |
| **P2** | wall coupon: Ø60 × 30 mm cylinders, O1 and O2 × three ripple amplitudes (1, 2, 4 mm peak-to-peak), each labelled by digit | ~40 min | which wall, which amplitude, whether O2's nodes plough |
| **P3** | the shade | 2.3 h (O1) to 4.6 h (O2) | the object |

The base prints separately. `solid.py`'s existing `foot` is a plate around one stick bore
(`wall × 3`), which is too small to keep a lamp upright. The base is a new part that reuses
`shaft_socket` and `--cavity`, and it shares P1's first-layer evidence.

## Light and heat

**Default light (Q3):** a 5 V warm-white COB LED strip bonded along an aluminium tube (Ø20 × 180
mm, 1 mm wall), powered from a USB-C adapter. Mains voltage never enters a printed part. **Rejected by
default: an E27 mains bulb in a printed socket holder.** It puts 230 V inside PLA and puts the
bulb's driver, its hottest part, at the socket where the plastic holds it. That rejection is a
design reason. No temperature figure was measured or sourced for it.

**The budget, as a relationship.** The strip's heat has to leave through the tube's surface:

    P_in,max = h · A · ΔT_allow / (1 − η_light)

- `A` = π · 0.020 · 0.180 = 0.0113 m² for the default tube
- `ΔT_allow` = 20 K: plastic contact at or below 45 C in a 25 C room. The ceiling is 15 K under
  the 60 C glass transition that `CR-PLA @Creality K2 Plus 0.4 nozzle.json` states
  (`temperature_vitrification`). The Generic PLA profile's 110 is an uncustomised default and is
  not used.
- `h` ≈ 6 W/m²K, **ASSUMED**: still-air convection on a small vertical cylinder plus little
  radiation from bare aluminium. Anodised aluminium radiates far better and roughly doubles it.
- `η_light` ≈ 0.3, **ASSUMED**: the fraction of input leaving as light
- result: **about 2 W of input** on the default tube. For more light, raise `A` (a longer or
  wider tube) or `h` (anodised), and never let the plastic run hotter.

**Why the shade stays cool, as an estimate.** The core radiates to the shade across a 65 mm air
gap. At 45 C against a 25 C shade, bare aluminium sends on the order of 0.1 W over the shade's
roughly 0.09 m², a rise well under 1 K. The warm plume leaves through the open top. The only
printed part near the heat is the base, which touches the tube on three rib lines and carries
about 29 g of aluminium (1 mm wall).

**The falsifier is a measurement, not this arithmetic.** First-light gate: a K-type probe on the
tube at the base contact, 60 minutes at full power, open room. PASS at 45 C or below. Above 45 C,
cut the LED power or enlarge the tube. The gate is also a guard, run before the lamp is left on
unattended.

## Guards `lamp.py` will carry, each forced red before it counts

| guard | refuses |
|---|---|
| L1 | a ripple crest tighter than `v²/machine.ACCEL` |
| L2 | peak-to-peak ripple at or below the bead width while declaring a void wall (it would be texture that claims cells) |
| L3 | a lap count that is not `N + 0.5` ripples when a phase-flipped wall is declared |
| L4 | O2 without the node lift (`crossing_z`), or a node lift that lifts the earlier strand |
| L5 | a profile moving more than `lh·tan 40°` per layer |
| L6 | the cable slot bridge wider than the span evidence the file cites |
| L7 | an undeclared wall mode: `; WALL={lace,braid}` in the header, contradicted by the geometry = refused (the same pattern as `--fabric`) |

Plus everything `validate.py` and `send.py` already enforce, and a readback of the emitted file
for the path length, lap count and ripple count the header claims.

## References examined

Each entry names what was opened, the mechanism, and the verdict.

- **`Claywoven/Nozzleboss-Claywoven`** (opened, commit `ca155c0`, 2026-08-03, all four source
  files and the README). **It contains no sine or wave code.** It is a Blender add-on that turns
  a mesh ribbon into gcode. The waves in Claywoven's work are built in Blender scenes (array and
  hook modifiers, sculpted paths) that this repo does not contain. Mechanisms read:
  - E = segment length × extruded-face height × `1.5 · nozzle`. The 1.5× width matches this
    house's stacking ceiling. **Adopted as corroboration**, nothing to import.
  - flow and speed multipliers painted as vertex colours. **Rejected**: R4 (constant flow) and
    R3 (one speed).
  - a Z hop to `max_z_so_far + 10` mm before any travel longer than 1 mm. **Rejected for the
    shade**, which has no travel. The idea behind it (clear everything already printed) is
    already `validate.py`'s lifted-travel rule.
  - relative E only, firmware retraction (G10/G11). Irrelevant here.
  - **No LICENSE file.** Nothing is copied from it.
- **`FullControlXYZ/fullcontrol`, `models/ripple_texture.ipynb`** (opened, GPL-3). The `N + 0.5`
  phase flip is **ADOPTED**: it is the whole wall mechanism. The zigzag `RippleSegs = 2` is
  **REJECTED** (a zero-radius corner, refused by `smooth.py`'s rule). `rip_depth = EW` is
  **REJECTED as a default** because it cannot open a cell. The first-lap E ramp
  (`first_layer_E_factor`) is **REJECTED** in favour of this house's pressed first lap and
  `machine.prime()`.
- **`fractional_design_engine_polar.ipynb` and `star_polygon_lattice.ipynb`**, same repo (opened).
  Nothing adopted. Both break the stroke with `Extruder(on=False)` travels, which the shade does
  not do.
- **claywoven.com** (opened). It lists products, including three lamps (Sea Blast, Parasol, Xeno
  Lumae), and no technique. The assets and workflows are Patreon-only and **were not opened**.
- **Creality Print K2 Plus 0.4 profiles** (opened, on disk): `0.20/0.24/0.28mm Standard`,
  `CR-PLA`, `Generic PLA`, `Hyper PETG`, `Generic PETG`, `Generic PC`. **ADOPTED** as the
  authority for line width, layer heights, the flow ceiling and Tg, per CLAUDE.md's rule that
  the vendor's slicer profile outranks the vendor's page.
- In this repo: `bucket_towers.py` (multi-circuit layers, posts and bridges), `bucket.crossing_z`
  (node lift), `spiraltower.py` (the closest existing single-wall helix: a pressed flat first lap
  and then a climb, but a hardcoded stationary purge that R10 now refuses, so it is not reused as
  it stands), `smooth.py`, `solid.shaft_socket`, `notes/Z-MODULATION.md`.

**Not opened, named so nobody mistakes them for evidence:** the Printables/Cults3D "Sine Wave
Woven Basket" (both returned HTTP 403). The FullControl lampshade video. Mark Wheadon's velocity
painting, rejected on the Nozzleboss README's one-line description of it (speed modulation,
which R3 refuses). No LED or luminaire thermal source was opened, which is why `h` and `η_light`
are marked ASSUMED.

## Questions for Oleg, each with the default work proceeds on

| | question | default |
|---|---|---|
| **Q1** | Cells inside the wall (O1 or O2), or real see-through windows (the `bucket_towers` post-and-bridge wall, re-proven on the 0.4)? | **Cells.** P2 prints both O1 and O2 and he picks off the plate. |
| **Q2** | Size | **Ø150 × 200 mm table lamp** |
| **Q3** | Light source, which is a purchase: 5 V COB strip + Ø20 × 180 aluminium tube + USB-C adapter (a few euro), or something he already owns | **The low-voltage kit, bought only on his yes.** Until then the design proceeds on its dimensions. |
| **Q4** | Material: is the translucent 210 PLA still on the K2? | **Translucent PLA** (`machine.LOADED`). If it is gone, P1 and P2 use whatever is loaded, and the shade waits for translucent. |
| **Q5** | Has the nozzle thread leak from 2026-08-31 been fixed on the new nozzle? | **Assume not.** P1 is read for it before anything taller prints. |
