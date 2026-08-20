# R4: six stamped candidates, generator or history

Date: 2026-08-20. This report measures the six non-control files isolated by
`r4-violations-2026-08-20.md`. `FORCE_attach.gcode` and `FORCE_pile.gcode` remain known-bad
controls and are not defects.

## Result

Four files expose one live generator defect in `solid.py`; two are historical. R4 says only that
an unlabelled emitted move lies outside 0.80--1.20 times the file's own `FLOW` declaration. The band
has no recorded machine, nozzle, coupon, or scatter provenance. These results make no claim about
machine behaviour.

“Measured” below is the range over the exact R4 selection, with the median in parentheses. “Miss”
is the worst distance beyond the declared band in mm3/s. Low and high are shown where both occur.

| Historical artifact | Declared | Measured mm3/s (median) | Ratio | Miss | Generator | Verdict and mechanism |
|---|---:|---:|---:|---:|---|---|
| `bucket_towers_k2plus_pla_d339.5_h304.8_n16t6.48_w287.5os3.175_b20_bb5x5_m1.8-3.6-7.2_f3x4_x18p3_j2_z0.56.gcode` | 7.6533 | 4.5849--7.6639 (7.6525) | 0.5991--1.0014 | low 1.5377 | `bucket_towers.py:build/main` | **HISTORICAL.** Its five-way bridge circuits also split ordinary wall arcs five ways, but those arcs were unlabelled; 56,000 therefore looked like ordinary body moves at 3/5 of the three-pass declared flow. Commit `1588852` added the explicit `LINK wall split` regime 13 minutes after this file was written. Exact current arguments pass R4. |
| `cleavage_k1c_s6.35_w5_T210.gcode` | 45.0000 | 13.4996--45.1327 (44.9955) | 0.3000--1.0029 | low 22.5004 | `cleavage.py:main` -> `solid.emit` | **GENERATOR-DEFECT.** Twenty unlabelled layer-change moves extrude vertically at `F900`; `solid.emit` meters one layer height of material, so they carry 0.3000 times declared body flow. Current output repeats it (40 moves at the current derived height). |
| `hangerpole_k1c_x12_h5_T210.gcode` | 45.0000 | 13.4996--45.1237 (45.0005) | 0.3000--1.0027 | low 22.5004 | `hanger.py:main` -> `solid.emit_sequential` -> `solid.emit` | **GENERATOR-DEFECT.** The two plate-wide layer changes are the same unlabelled Z-only extrusion. Current output repeats it. |
| `hangerpole_k1c_x12_h5_T230.gcode` | 45.0000 | 13.4996--45.1335 (45.0005) | 0.3000--1.0030 | low 22.5004 | same | **GENERATOR-DEFECT.** Sequential emission makes two Z-only seam moves for each of 12 parts: 24 violations. |
| `hangerpole_k1c_x9_h5_T210.gcode` | 45.0000 | 13.4996--45.1529 (44.9987) | 0.3000--1.0034 | low 22.5004 | same | **GENERATOR-DEFECT.** Three plate-wide layer changes are the same unlabelled Z-only extrusion. |
| `zladder_k2plus_pla_6cell_w2_p1.6.gcode` | 9.8400 | 7.5000--17.5003 (9.8400) | 0.7622--1.7785 | low 0.3720; high 5.6923 | `zladder.py:main` | **HISTORICAL.** This calibration varied commanded first-layer Z and material per cell while declaring one body flow, leaving 224 variable-regime moves eligible for R4. Commit `a3723ff`, eight minutes after this file was written, moved the variation to `SET_GCODE_OFFSET` while keeping commanded Z at 0.100/0.340. Exact current heights pass R4. |

The hanger ratios are temperature-independent: x12 at 210 C and 230 C both have a minimum ratio
of 0.299992 and a median body ratio of 1.000010. x9 at 210 C has the same 0.299992 minimum. The
failure is geometric emission in `solid.py`, not the material-temperature lookup.

The six distributions do not support retuning the band. Almost all ordinary moves sit near 1.000;
the failures form discrete 0.300, 0.600, and calibration-regime clusters. The live solid defect's
regression gate must generate a multi-layer `solid.emit` and `solid.emit_sequential` part and require
every unlabelled, non-first-layer positive-E move, including Z-only layer changes, to remain inside
the declared R4 band. That gate must first reject the present 0.3000 case. This task does not fix it.

## Reproduction

The historical measurements use `gate_coverage.moves`, `AREA`, modal position/feed/extrusion state,
the `PRESSED_LAYER1` exclusion, and the same `LINK`, `THIN CROSS`, declared `BRIDGE`, `PRIME`, and
0.05 mm filters as `gate_coverage.analyze_text`. For each selected move compute
`delta_E * AREA * feed_mm_s / distance_mm` and compare it with `FLOW * [0.80, 1.20]`.

Regeneration used `/tmp/crackle-r4-six-20260820-a`, with each historical `ARGV`/`CMD` reproduced and
only `--out` changed; the coupon path was made absolute. One file per family was gated:

```text
bucket current:   PASS moves=6144, measured 7.6449..7.6569, declared 7.6533
cleavage current: FAIL moves=85480, 40 outside, minimum ratio=0.299992
hanger current:   FAIL moves=15408, 24 outside, minimum ratio=0.299992
zladder current:  PASS moves=306, measured 9.8399..9.8406, declared 9.8400
```

The current bucket filename gains `r1c` because current source emits the floor-border regime; its
geometry arguments are otherwise the historical command. The scratch files were purged after these
measurements. Future work must re-run this method against the bytes and source then present; do not
quote these classifications as current without re-deriving them.

## 2026-08-20 follow-up

The live `solid.py` defect is fixed: a layer change now advances Z without E because stationary XY
defines no bead path to meter. `tests/solid_layer_change.py` first rejected the old direct output at
ratio 0.299992, then passed direct and sequential output at 0.999258--1.000843. The historical
artifacts above remain unchanged; re-derive against current bytes before quoting this follow-up.
