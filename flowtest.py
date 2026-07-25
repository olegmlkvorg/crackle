#!/usr/bin/env python3
"""Max volumetric flow test — ONE LAYER, whole plate, flow ramping as it climbs in Y.

Q (mm3/s) = line_width x layer_height x speed. The hotend can only melt so fast; past that it
under-extrudes no matter what you command. This finds that ceiling.

WHY THIS IS A SINGLE LAYER AND NOT A TOWER (learned the hard way, 2026-07-25)
  v1 was a stacked tower. It printed 3 mm-wide lines from a 0.8 mm nozzle, which is 1.2 mm2 of
  plastic per mm of path. The nozzle cannot spread that to 3 mm, so the bead landed ~1.4 mm wide
  and therefore ~0.86 mm TALL — while Z stepped 0.4 mm per layer. The part grew twice as fast as
  the nozzle climbed, the nozzle ploughed into it, and it dragged the tower off the plate at 56%.
  Narrow bead means tall bead. Tall bead means collision.
  A single layer has nothing to stack into, so wide commanded lines are safe — which is the whole
  reason we can keep 3 mm lines and actually SEE the filament.

WHY LONG STRAIGHT ROWS AND NOT A HILBERT / SPACE-FILLING CURVE
  A flow test is only valid if the head actually reaches the commanded speed. A Hilbert curve is
  nothing but 90-degree corners; acceleration limits mean you decelerate into every one and never
  hit the speed you asked for, so you would be measuring the motion planner, not the hotend.
  320 mm straight runs reach commanded speed with room to spare. (Hilbert is the right path for
  the crackle/ORBE work, where corners and crossings ARE the point — just not for measurement.)

HOW TO READ IT
  Bottom of the plate (low Y) = lowest flow. Each band up = more flow.
  The first band that goes THIN, GAPPY, MATTE or starts skipping = past the ceiling.
  Max stable flow = the last good band below it. Use ~85% of it as the working number.

BONUS MEASUREMENT: row spacing equals the COMMANDED line width. Where the sheet seals with no gap,
  the bead really is that wide. Where you see a gap, measure it — landed width = spacing - gap.
  That number is what a hermetic single-layer sheet needs for its spacing, and it feeds the
  crackle strand model too.

Usage:
  python3 flowtest.py --no-home                       # full plate, 34..78 mm3/s
  python3 flowtest.py --no-home --flows 40,50,60,70
"""
import argparse, math, os

MATERIALS = {
    # start where the last run was still visibly fine and climb from there
    "pla":  dict(temp=230, bed=60,  flows=[34, 38, 42, 46, 50, 54, 58, 62, 66, 70, 74, 78]),
    "petg": dict(temp=245, bed=80,  flows=[10, 14, 18, 22, 26, 30, 34, 38]),
    "tpu":  dict(temp=230, bed=50,  flows=[2, 3, 4, 5, 6, 8, 10, 12]),
    "abs":  dict(temp=255, bed=100, flows=[8, 12, 16, 20, 24, 28, 32, 36]),
}
BED = (350.0, 350.0)   # K2 Plus


def emit(flows, rows_per_band, layer_h, line_w, temp, bed, fan, fil_d, home, margin):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (line_w * layer_h) / area          # constant: volume per mm of path
    x0, x1 = margin, BED[0] - margin
    row_len = x1 - x0
    n_rows = len(flows) * rows_per_band
    spacing = line_w                              # textbook sealed-sheet spacing; gaps = measurement
    span = (n_rows - 1) * spacing
    y0 = (BED[1] - span) / 2.0
    if y0 < margin:
        raise SystemExit(f"{n_rows} rows x {spacing}mm = {span:.0f}mm exceeds the plate. "
                         f"Reduce --rows or --flows.")

    L = []; w = L.append
    w(f"; MAX VOLUMETRIC FLOW — single layer, full plate, {len(flows)} bands x {rows_per_band} rows")
    w(f"; line_w={line_w} layer_h={layer_h} temp={temp} fan={fan} spacing={spacing}")
    w("; READ IT: low Y (front) = lowest flow. First band that goes thin/gappy/matte = past the ceiling.")
    for i, q in enumerate(flows, 1):
        v = q / (line_w * layer_h)
        ya = y0 + (i - 1) * rows_per_band * spacing
        yb = ya + (rows_per_band - 1) * spacing
        w(f"; band {i}: {q:g} mm3/s -> {v:.0f} mm/s   Y {ya:.0f}..{yb:.0f}")
    w("; HEADER_BLOCK_START"); w("; total layer number: 1"); w("; HEADER_BLOCK_END")

    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    if home:
        w("G28")
    else:
        w("; NO HOME — direct to print (errors safely if the machine lost its homed position)")
    w(f"M190 S{bed}"); w(f"M109 S{temp}")
    w("M204 S8000")                 # 320mm rows: high accel so commanded speed is actually reached
    w("M107" if not fan else f"M106 S{fan}")
    w("M82"); w("G92 E0")
    # prime bead down the far left, clear of the test area
    w(f"G1 Z{layer_h:.2f} F600")
    w(f"G0 F9000 X{margin:.1f} Y{margin:.1f}")
    w(f"G1 F1200 X{margin:.1f} Y{margin+80:.1f} E12")
    w("G92 E0")

    e = 0.0; row = 0
    for i, q in enumerate(flows, 1):
        v = q / (line_w * layer_h)
        f_mm_min = round(v * 60)
        L.append(f"; ---- band {i}: {q:g} mm3/s @ {v:.0f} mm/s ----")
        for r in range(rows_per_band):
            y = y0 + row * spacing
            left_to_right = (row % 2 == 0)
            sx, ex = (x0, x1) if left_to_right else (x1, x0)
            if row == 0:
                L.append(f"G0 F9000 X{sx:.2f} Y{y:.2f}")
            else:
                # y-shift is part of the sheet, drawn not travelled — no ooze gap between rows
                e += spacing * e_per_mm
                L.append(f"G1 F{f_mm_min} X{sx:.2f} Y{y:.2f} E{e:.5f}")
            e += row_len * e_per_mm
            L.append(f"G1 F{f_mm_min} X{ex:.2f} Y{y:.2f} E{e:.5f}")
            row += 1

    L += ["M107", "M104 S0", "M140 S0",
          f"G1 Z{layer_h+40:.1f} F900", "G0 X10 Y340 F9000"]   # steppers stay on for the next run
    grams = e * area * 1.24 / 1000
    path_mm = n_rows * row_len + (n_rows - 1) * spacing
    secs = sum((rows_per_band * row_len + rows_per_band * spacing) / (q / (line_w * layer_h))
               for q in flows)
    return "\n".join(L) + "\n", dict(rows=n_rows, grams=round(grams, 1), mins=round(secs / 60, 1),
                                     path=round(path_mm / 1000, 1), y0=round(y0), span=round(span))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--material", default="pla", choices=list(MATERIALS))
    ap.add_argument("--flows", default=None, help="comma list of mm3/s")
    ap.add_argument("--temp", type=int, default=None)
    ap.add_argument("--rows", type=int, default=8, help="rows per flow band")
    ap.add_argument("--layer_h", type=float, default=0.4)
    ap.add_argument("--line_w", type=float, default=3.0)   # safe: single layer, nothing stacks
    ap.add_argument("--fan", type=int, default=255)
    ap.add_argument("--margin", type=float, default=15.0)
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    m = MATERIALS[a.material]
    flows = [float(x) for x in a.flows.split(",")] if a.flows else m["flows"]
    temp = a.temp or m["temp"]
    g, st = emit(flows, a.rows, a.layer_h, a.line_w, temp, m["bed"], a.fan, 1.75,
                 not a.no_home, a.margin)
    os.makedirs(a.out, exist_ok=True)
    fn = (f"{a.out}/flowsheet_{'nohome_' if a.no_home else ''}{a.material}"
          f"_T{temp}_{int(min(flows))}-{int(max(flows))}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}\n  ONE layer, {st['rows']} rows, Y {st['y0']}..{st['y0']+st['span']}, "
          f"{st['path']} m of path, ~{st['mins']} min, {st['grams']} g")
    print("  " + "  ".join(f"{q:g}→{q/(a.line_w*a.layer_h):.0f}mm/s" for q in flows))
