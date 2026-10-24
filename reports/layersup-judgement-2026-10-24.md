# LAYERSUP judgement, 2026-10-24

Three parts pass PRINTABLE and fail `tools/qa_stl.py --layer-support`. Each was run, its flagged
regions listed, rendered from the check's own scanline data and looked at, and its generator read
for the intended print orientation.

Verdicts in one line each:

- **stand/foot_cup.stl: measurement artefact caused by INVERTED WINDING, which is a real mesh defect.**
  It is not an overhang. When the defect is fixed, LAYERSUP passes.
- **marble/sort_head_gate_v1.stl and _seat0.stl (byte-identical): a real lean past the house 45° rule,
  printed deliberately past it.** The bowl flare leans 50° from vertical, which is 40° from horizontal.
  The generator allows vase-mode walls up to 55° from vertical. The flag is a true reading of the
  geometry. Both files already fail WATERTIGHT (a vase-path surface with 288 open edges), so the
  LAYERSUP fail changes no overall verdict.
- **Recommendation: switch LAYERSUP on by default after one named fix.** LAYERSUP must decline
  (could-not-measure) on a layer whose scanline winding does not return to zero, and report it as a
  mesh-orientation fault. Today it reports such a layer as overhang.

Renders are in `reports/layersup-2026-10-24/`. In the top views, grey is material in this layer and
in the baseline layer below. Blue is material in this layer only. Light grey is baseline only. Red is
the region LAYERSUP flagged. White is empty.

## stand/foot_cup.stl

Run: `FAIL LAYERSUP 3 overhang region(s), 4.6 mm2`. PRINTABLE and WATERTIGHT pass.

| z mm | area mm² | kind | test | x, y |
|---|---|---|---|---|
| 9.65 | 0.92 | overhang | slope | 22.8, 10.1 |
| 10.61 | 1.84 | overhang | slope | 20.4, 9.5 |
| 11.57 | 1.84 | overhang | slope | 17.6, 8.8 |

Intended orientation: the generator says "Prints PAD-DOWN, socket-UP, support-free", which is the
STL's own orientation. The two horizontal Ø7 teardrop bores (axis z 7, flats at 50° from horizontal)
are designed to self-support.

What the renders show (`foot_cup_full_z9.65.png`, `foot_cup_zoom_z9.65.png`, `foot_cup_zoom_z11.57.png`):
the flagged red sliver sits at the inner blind end of the +y teardrop bore. In the same layer, a band
about 4 mm wide in y reads EMPTY across the whole pad, from the bore's end through to both outer
faces. The same band appears at -y. The pad there is solid.

Mechanism, measured: on the scanline y 8.01 at z 9.66 the section's crossings are
`-47.87 (+1), 13.23 (+1), 18.55 (+1), 47.87 (-1)`. They sum to +2, so nonzero winding never returns to
zero and `_ls_rows` drops the row. The +1 at 13.23 comes from triangle 231, part of the bore's blind
CAP. Its normal points into the solid. `add_horizontal_bore` in `stand/foot_cup_stl.py` appends the
cap as `(A, C, B)`, and that reversal is wrong. WATERTIGHT cannot see it, because it pairs undirected
edges. The file has 178 directed edges that appear twice in the same direction.

Proof: a scratch copy of the generator with the cap written as `(A, B, C)` (the regenerated original
is byte-identical to the committed STL) gives `PASS LAYERSUP 0 overhang region(s)`, with PRINTABLE and
WATERTIGHT still passing. 128 duplicated directed edges remain after that change, in the
pad cap triangulation (`cap_at`). That is a second orientation fault, not judged here, and it does not
affect the sections because caps are horizontal.

Verdict: artefact (inverted winding). LAYERSUP caught a real defect that no other gate catches but
labelled it as overhang. The part itself prints as designed. The generator needs a one-line fix,
which belongs to the stand work and is not made here.

## marble/sort_head_gate_v1.stl (and _seat0, identical bytes)

Run: `FAIL LAYERSUP 149 overhang region(s), 4656.7 mm2, worst 54.6 mm2 at z 88.37, slope test`. Every
one of the 149 regions is from the slope test, centred on the axis (x 0, y 0), at z 52.85 to 88.37,
about one per layer. The area per layer grows from 7.8 mm² to 54.6 mm² as the radius grows. Totals by
5 mm band:

| z band | regions | mm² |
|---|---|---|
| 55 | 20 | 213.8 |
| 60 | 21 | 355.0 |
| 65 | 21 | 501.5 |
| 70 | 20 | 613.3 |
| 75 | 21 | 779.7 |
| 80 | 21 | 918.6 |
| 85 | 21 | 1057.6 |
| 90 | 4 | 217.2 |

Geometry measured off the file (max radius per vertex ring): z 0-16 is the spigot ring at r 26-28. The
wall then leans inward at 55° from vertical to z 30, runs as a tube to z 52, and from z 52.03 to
88.59 flares outward at a constant 50.1° from vertical (r 6.4 to 50.0). `sort_head_profile.png` shows
this r-z silhouette with the flagged band shaded. The band covers exactly the bowl flare.
`sort_head_zoom_z88.37.png` shows the flagged strip as a thin red ring outside the layer below.

Check of the arithmetic: at 40° from horizontal the wall steps out 0.19 mm per 1.2 mm baseline past the 45°
allowance. Around a 50 mm radius that is about 55 mm², which matches the worst region. The slope test is
reading the geometry correctly. The step test passes because each 0.24 mm layer is only 0.05 mm past.

Intended orientation: the generator's self-verify reads "vase mode, prints lower-tube-down as
modelled, no support". `BOWL_LEAN = 50.0` is commented as "under the 55 vase ceiling", and the
`vase printable` check allows up to 55°. PRINTABLE says "print UPSIDE-DOWN (mesh is modeled in use
orientation)", which disagrees with the generator. LAYERSUP tried the flip itself and the flip fails
too, because the 55° inward taper becomes the overhang. The generator's orientation is the better of
the two.

The section is FILLED as a disc (`sort_head_zoom_*.png`, grey interior) because the mesh is one
vase-path surface of revolution, not a solid. The outer edge of that disc is still the wall's outer
face, so the lean is measured correctly. The file also fails WATERTIGHT, 288 open edges, today, with
or without LAYERSUP.

Verdict: real, and deliberate. It is a 40°-from-horizontal single-bead vase flare, past the house 45° rule,
inside the generator's own 55° vase ceiling. The generator's docstring says nothing in this part has
been printed. Whether 0.67 mm of offset per layer on a 0.82 bead holds up is a coupon question,
untested. No support or other orientation fixes it. The design choice belongs to the marble work.

## Recommendation

Switch LAYERSUP on by default after one fix, F1. Then the default-on run fails exactly the parts it
should, for the right reason.

- **F1 (before default-on):** `_ls_rows` drops a row whose winding does not return to zero. Count those
  rows per layer. When a layer has any, LAYERSUP reports a could-not-measure fault naming the z and the
  unbalanced row count, and stops calling the region overhang. It is proven on stand/foot_cup.stl, which
  must turn from "3 overhangs" into "winding unbalanced at z 9.66 ...". A cheaper companion is a
  directed-edge pairing check beside WATERTIGHT, which would fail foot_cup on its own (178 duplicated
  directed edges). Not implemented here.
- No LAYERSUP fix is needed for sort_head. Its reading is correct, and the part fails qa_stl on WATERTIGHT
  already. If vase-path surfaces should be judged by their own lean ceiling, that is a separate vase
  rule (the house 45° vs the generator's 55°), and the decision belongs with the marble work.
- Follow-ups outside qa_stl: fix the cap winding in `stand/foot_cup_stl.py` (`(A, C, B)` to `(A, B, C)`)
  and regenerate. Then look at the remaining 128 duplicated directed edges in `cap_at`.

Not run: the full crackle test suite. No code changed. The commands that produced every number
above are `python3 tools/qa_stl.py <part> --layer-support` and direct calls to `qa_stl._layer_support`
and `_foot_section` on the same files.
