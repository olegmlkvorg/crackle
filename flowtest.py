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

CONTINUOUS RAMP, NOT BANDS (Oleg, 2026-07-25: "you could have easily done the progressions much
smoother"). Every row gets its own flow, interpolated linearly across the plate. v1 repeated each
flow for 8 rows — a habit carried over from the stacked tower, where a band genuinely needed several
LAYERS to be readable. A single-layer row is already a 320mm constant-speed run, ~11 s of continuous
extrusion, long past thermal steady state. So repeating it spent 8x the plate to learn one number.
96 rows = 96 flow values = ~0.5 mm3/s resolution instead of 4, for the same time and material.

HOW TO READ IT
  Front of the plate (low Y) = lowest flow, back = highest. It degrades gradually, not in steps.
  Find where the surface first goes THIN, GAPPY, MATTE or starts skipping.
  SELF-LABELLING: rows at each multiple of 5 mm3/s are cut 15mm short, so the right-hand edge is a
  comb. Count teeth from the front — the first tooth is the first multiple of 5 above the start
  flow, and each tooth after it is +5. No ruler needed. Tell me the tooth and I have the number.

FAN: 20%, not 100% (Oleg, 2026-07-25). Two reasons, and the second is the important one:
  1. It is a single layer with nothing above it, so cooling buys nothing — but a 46 g sheet of fat
     beads WILL curl and lift off the plate with full fan behind it.
  2. Worse, full fan chills the melt and can make extrusion fail on its own. That would read as the
     flow ceiling when it is really the fan, and we would set every downstream parameter too low.
     A melt-rate test must not have a second cooling variable fighting the hotend.

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


def emit(flows, n_rows, layer_h, line_w, temp, bed, fan, fil_d, home, margin):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (line_w * layer_h) / area          # constant: volume per mm of path
    x0, x1 = margin, BED[0] - margin
    row_len = x1 - x0
    q_lo, q_hi = min(flows), max(flows)
    def q_at(r):                      # linear ramp: one flow per row
        return q_lo + (q_hi - q_lo) * (r / max(n_rows - 1, 1))
    NOTCH = 15.0                      # rows crossing a multiple of 5 mm3/s are cut short -> a comb
    spacing = line_w                              # textbook sealed-sheet spacing; gaps = measurement
    span = (n_rows - 1) * spacing
    y0 = (BED[1] - span) / 2.0
    if y0 < margin:
        raise SystemExit(f"{n_rows} rows x {spacing}mm = {span:.0f}mm exceeds the plate. "
                         f"Reduce --rows or --flows.")

    L = []; w = L.append
    w(f"; MAX VOLUMETRIC FLOW — single layer, full plate, {n_rows} rows, continuous ramp")
    w(f"; line_w={line_w} layer_h={layer_h} temp={temp} fan={fan} spacing={spacing}")
    w("; READ IT: low Y (front) = lowest flow, ramping continuously to the back.")
    w("; Rows at each multiple of 5 mm3/s are 15mm short -> comb on the right edge. Count teeth.")
    w(f"; RAMP {q_lo:g} -> {q_hi:g} mm3/s over {n_rows} rows "
      f"({(q_hi-q_lo)/max(n_rows-1,1):.2f} mm3/s per row)")
    for r in range(n_rows):
        q = q_at(r)
        if math.floor(q / 5) != math.floor(q_at(r - 1) / 5) if r else False:
            w(f"; NOTCH row {r}: {q:.1f} mm3/s at Y{y0 + r*spacing:.0f}")
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

    e = 0.0
    for row in range(n_rows):
        q = q_at(row)
        v = q / (line_w * layer_h)
        f_mm_min = round(v * 60)
        y = y0 + row * spacing
        # notch this row if the ramp crosses a multiple of 5 here — makes the plate self-labelling
        notch = row > 0 and math.floor(q / 5) != math.floor(q_at(row - 1) / 5)
        left_to_right = (row % 2 == 0)
        sx, ex = (x0, x1) if left_to_right else (x1, x0)
        if notch:
            ex = ex - NOTCH if left_to_right else ex + NOTCH
        if row == 0:
            L.append(f"; ramp starts {q:.1f} mm3/s")
            L.append(f"G0 F9000 X{sx:.2f} Y{y:.2f}")
        else:
            if notch:
                L.append(f"; --- notch: {q:.1f} mm3/s @ {v:.0f} mm/s, Y{y:.0f} ---")
            # y-shift is part of the sheet, drawn not travelled — no ooze gap between rows
            e += spacing * e_per_mm
            L.append(f"G1 F{f_mm_min} X{sx:.2f} Y{y:.2f} E{e:.5f}")
        d = abs(ex - sx)
        e += d * e_per_mm
        L.append(f"G1 F{f_mm_min} X{ex:.2f} Y{y:.2f} E{e:.5f}")

    L += ["M107", "M104 S0", "M140 S0",
          f"G1 Z{layer_h+40:.1f} F900", "G0 X10 Y340 F9000"]   # steppers stay on for the next run
    grams = e * area * 1.24 / 1000
    path_mm = n_rows * row_len + (n_rows - 1) * spacing
    secs = sum((row_len + spacing) / (q_at(r) / (line_w * layer_h)) for r in range(n_rows))
    return "\n".join(L) + "\n", dict(rows=n_rows, grams=round(grams, 1), mins=round(secs / 60, 1),
                                     path=round(path_mm / 1000, 1), y0=round(y0), span=round(span))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--material", default="pla", choices=list(MATERIALS))
    ap.add_argument("--flows", default=None, help="comma list of mm3/s")
    ap.add_argument("--temp", type=int, default=None)
    ap.add_argument("--rows", type=int, default=96, help="total rows = flow resolution")
    ap.add_argument("--layer_h", type=float, default=0.4)
    ap.add_argument("--line_w", type=float, default=3.0)   # safe: single layer, nothing stacks
    ap.add_argument("--fan", type=int, default=51)   # 20% — see FAN note in the docstring
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
    lo, hi = min(flows), max(flows)
    print(f"  ramp {lo:g}→{hi:g} mm3/s, {(hi-lo)/max(a.rows-1,1):.2f} per row "
          f"({lo/(a.line_w*a.layer_h):.0f}→{hi/(a.line_w*a.layer_h):.0f} mm/s)")
    print(f"  notches (15mm short rows) at every 5 mm3/s — count teeth from the front")
