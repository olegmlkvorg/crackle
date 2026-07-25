# Crackle — Phase 1

Emits gcode directly for "crackle coupons": grids of pillars where **the travel moves are the
product**. Retraction, combing, z-hop and wipe are absent on purpose, so the nozzle drags a molten
strand between every pillar; strands cross, weld, and later snap underfoot.

**Why gcode and not CAD:** the web is defined by travel order and timing, which is exactly what
CAD-then-slice discards. A slicer's job is to hide travels; here they're the whole thing.

**The key idea:** crackle ≈ fused crossings breaking, so **crossings-per-layer is the control
variable — and it's computable from the visit order**, not an accident. This tool counts them
(segment intersection) and puts the number in the filename. Perimeter order → 0 crossings. Star
order → 77. A finer 6×6 grid → 524, for *less* filament.

```
python3 crackle.py --list          # presets
python3 crackle.py --sweep all     # emit the whole one-factor-at-a-time sweep
python3 validate.py out/*.gcode    # structural check before it touches the printer
```

`validate.py` catches what has no slicer to catch it: backwards E (an unintended retraction),
Z descending into the part, coordinates off the bed, missing home/heat, and the travel:extrude ratio
(if it's low, you aren't building a web). It already caught three real bugs in this generator.

Run protocol + scoring rubric: `notes/PROTOCOL.md`. Results table: `notes/RESULTS.md`.

## Use your printer's own start gcode (recommended)
Rather than trusting a generic start block, take the one your machine already uses:
1. Slice anything in Creality Print for the K2 Plus, save the `.gcode`.
2. Copy everything from the top down to just before the first real layer into `k2-start.txt`
   (and the tail after the last layer into `k2-end.txt`).
3. `python3 crackle.py --sweep all --start-gcode k2-start.txt --end-gcode k2-end.txt`

It's inserted verbatim, then **our** temperature and fan are re-asserted right after — because the
experiment depends on those two and a machine block will happily set its own.

**Read the protocol's first section before printing** — the K2's AI failure-detection is designed to
abort exactly this kind of print.

Phase 2 isn't built for, but isn't blocked either: every material-dependent value (temp, fan, flow,
speeds) is a parameter, so TPU/PETG coupons are a config change, not a rewrite.
