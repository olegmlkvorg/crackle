# Hanger tags in native gcode — one night, eleven plates, 2026-08-31

Oleg's reads on real plates, in order, with the generator state that produced each. The design
source is `~/Downloads/hanger-tags-handoff.zip` (26.4x11 tag, one 0.24 layer, clip for a 4.6
shaft); the generator is `hangertag.py`; every send is in `send-log.jsonl`.

## What the plates settled

| question | answer | evidence |
|---|---|---|
| nozzle | 0.4 (corroborated: 0.6mm lines welded; an 0.8 orifice cannot lay them) | first ladder, printed complete |
| floor pattern | SPIRAL to centre. Billiard net retired: "nucleon pointless" | spiral plate vs net plates |
| floor extrusion | **fill 0.75** of the 0.864 pitch x 0.64 gap cavity was best ("best base layer was 9") — the sweep's bottom rung, so the true optimum may sit lower | 9-tag grid, row 7-9 |
| floor speed | 15 mm/s cruise + 5 mm/s touchdown ("first layer should be slow", "first second of touching... x3 slowdown") | v15 ladders vs v50 failures |
| holder | best of the sweep = **single 0.8mm line** ("best triangle was 1") — but "messy... no luck": NOT production-ready in native gcode | 9-tag grid, column 1,4,7 |
| bed/temps | 210 / bed 80, glue stick on the smooth plate | all accepted starts |
| retraction | needed on this leaking 0.4 ("we crerating a lot of nets during move"): 0.8mm before every hop | grid plate, strings gone from file |
| start flow | probe at 140, heat to 210 at the chute, wipe, then print — a hot G28 re-zeroes Z through the leak's drool | the frame stopped drifting after this |

## The decision that ends the night

"no time now. will print with normal slicer." The native-gcode floor is SOLVED to a recipe; the
native holder is not. The slicer path resumes from the handoff's own next actions (LENGTHTEST /
FITTEST STLs, `make_plate.py` for the 336 grid).

**What transfers to Creality Print, from tonight's plates, in its own vocabulary:**
- 0.4 nozzle profile, 0.24 layers (the handoff's own cut).
- Initial layer: ~75-80% flow (his fill-0.75 read), 15 mm/s, bed 80, glue on the smooth plate.
- Retraction ON (~0.8mm) — this nozzle strings badly while it leaks.
- The nozzle LEAKS at 210 when idle over the plate: if seepage shows at the threads, hot
  re-tighten before trusting any calibration.
- The machine injects its own ~6-min calibrate before every API-started job (service layer, above
  Klipper — measured; homing state disproven as the trigger). Screen-started jobs may expose the
  toggle.

## What stays proven in the toolchain (all forced red before being trusted, suite 11/11)

- `; Z_LADDER=1` height coupons, `; L1_BENCH=1` extrusion-level coupons (one height, 3+ counted
  rates), `; RETRACT=` (E-only, no deeper than declared), `; PROBE_TEMP=` (declared cool probe),
  BED_MESH_CALIBRATE must be a bare line (Creality parses the whole line as args — key514),
  Moonraker port defaults to :7125, no M84 in tails (bed sinks, machine unhomes).
- The floor-sweep spread cap (one layer height) for layer-major multi-part plates.
- S2 can MEASURE a spiral floor (axis-aligned modal pitch) — the first hangertag send that needed
  no override went on a rule-6 grant: (1.08, 0.864).

## Open, honestly

- The native holder: single-line 45° tents are buildable but messy at 10mm tunnel depth. Untried:
  slicer-style multi-perimeter holders in native gcode, and the leak repair (hardware) which may
  be most of the "messy".
- Both winning reads were sweep EDGES (fill 0.75 = bottom rung, as cell 6 and 0.40 were top
  rungs earlier). Every read tonight was censored at a boundary; the next sweep, if any, centers
  on the winner.
- Nobody has run `send.py accept` on any plate, so machine.PROVEN_LAYER1/PROVEN_SEND still carry
  none of tonight's operating points. If the native path resumes, accept the best plate first —
  the 336-size plate (~6h motion) cannot go on grants (LONG_PRINT_MIN 90).
