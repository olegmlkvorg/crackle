#!/usr/bin/env python3
"""HONEYCOMB in our technique — one continuous extrusion, no travels, pressed hard, at max flow.

Oleg: "create honeycomb out of our technic". The sliced STL version on the K2 is 321 x 310mm and
does not fit the K1C at all; more to the point, a sliced honeycomb is thousands of travel moves and
a stop-start extruder. Ours is one unbroken line.

HOW A HONEYCOMB IS DRAWN WITHOUT LIFTING THE PEN
A hex lattice has vertices of degree 3 — odd — so no Eulerian circuit exists and it cannot be traced
edge-once without retracing. The standard construction avoids that: a honeycomb is rows of ZIGZAGS
joined by short VERTICAL struts.

    row:      /\  /\  /\        the slanted walls
    struts:   |   |   |         the vertical walls, drawn between rows

Walk a row left to right, drop a strut, walk the next row right to left, drop a strut, and so on.
Every edge is drawn exactly once, the pen never lifts, and the result is a true hexagonal lattice.
Boustrophedon — the way an ox ploughs a field.

Everything else follows the project's method: pressed to machine.PRESS_HARD, flow held at target by
deriving speed from the bead, no travel between first and last extrusion.
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine


def comb_path(cell, cols, rows, ox, oy):
    """Hex lattice as one continuous polyline. `cell` is the hexagon side length."""
    s = cell
    dx = s * math.sqrt(3) / 2.0          # half-width of a hexagon
    up = s / 2.0                          # vertical rise of a slanted wall
    strut = s                             # length of a vertical wall
    pts = []
    y = oy
    for r in range(rows):
        rightward = (r % 2 == 0)
        xs = range(cols * 2 + 1) if rightward else range(cols * 2, -1, -1)
        for i, k in enumerate(xs):
            x = ox + k * dx
            zig = y + (up if (k % 2 == 1) else 0.0)
            pts.append((x, zig))
        # strut down into the next row, at whichever end we finished on
        if r < rows - 1:
            xend = pts[-1][0]
            pts.append((xend, pts[-1][1] + strut))
            y = y + strut
    return pts


def emit(cell, cols, rows, bead_w, bead_h, flow, temp, bed, fil_d, bed_xy, home, press, fan):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (bead_w * bead_h) / area
    speed = flow / (bead_w * bead_h)
    f = round(speed * 60)
    s = cell
    w_total = cols * 2 * (s * math.sqrt(3) / 2.0)
    h_total = (rows - 1) * s + s / 2.0
    ox = (bed_xy[0] - w_total) / 2.0
    oy = (bed_xy[1] - h_total) / 2.0
    if ox < 8 or oy < 8:
        raise SystemExit(f"{cols}x{rows} cells of {cell}mm = {w_total:.0f} x {h_total:.0f}mm — "
                         f"too big for a {bed_xy[0]:.0f} x {bed_xy[1]:.0f} bed. Reduce --cols/--rows "
                         f"or --cell.")
    pts = comb_path(cell, cols, rows, ox, oy)
    _xs = [p[0] for p in pts]; _ys = [p[1] for p in pts]
    if min(_xs) < 4 or min(_ys) < 4 or max(_xs) > bed_xy[0] - 4 or max(_ys) > bed_xy[1] - 4:
        raise SystemExit(f"comb spans X {min(_xs):.0f}..{max(_xs):.0f} Y {min(_ys):.0f}.."
                         f"{max(_ys):.0f} on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} bed — off the plate.")

    L = []; w = L.append
    w(f"; HONEYCOMB — one continuous extrusion, {cols}x{rows} cells of {cell}mm")
    w(f"; bead {bead_w}x{bead_h} = {bead_w*bead_h:.2f}mm2 at {speed:.0f} mm/s -> flow={flow} mm3/s")
    w(f"; {w_total:.0f} x {h_total:.0f}mm on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} bed, pressed to {press}mm")
    w("; HEADER_BLOCK_START"); w("; total layer number: 1"); w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — direct to print (fails safely if the machine lost home)")
    w(f"M190 S{bed}"); w(f"M109 S{temp}")
    w("M204 S8000"); w("M107" if not fan else f"M106 S{fan}")
    w("M82"); w("G92 E0")
    x0, y0 = pts[0]
    w(f"G1 Z{press:.3f} F600")
    # Prime must start ON the bed. x0-55 put it at X-24 on a 229 bed — the guard below catches it
    # now, but the approach is clamped so it cannot happen at all.
    _apx = max(6.0, x0 - 55.0)
    _apy = max(6.0, y0 - 12.0)
    w(f"G0 F9000 X{_apx:.3f} Y{_apy:.3f}")
    w("G1 E25 F300                      ; stationary purge — pressure before motion")
    w(f"G1 F1200 X{x0:.3f} Y{y0:.3f} E37   ; prime ends where the comb begins")
    w("G92 E0"); w("; BODY_START")

    e = 0.0
    px, py = pts[0]
    for (x, y) in pts[1:]:
        d = math.dist((px, py), (x, y))
        if d < 1e-9:
            continue
        e += d * e_per_mm
        L.append(f"G1 {'F%d ' % f if (px, py) == pts[0] else ''}X{x:.3f} Y{y:.3f} "
                 f"Z{press:.3f} E{e:.5f}")
        px, py = x, y
    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{press+40:.1f} F900",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(pts=len(pts), grams=round(grams, 1), speed=round(speed),
                                     mins=round(e / e_per_mm / speed / 60, 1),
                                     size=(round(w_total), round(h_total)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", type=float, default=12.0, help="hexagon side length mm")
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--rows", type=int, default=12)
    ap.add_argument("--bead-w", type=float, default=machine.BEAD_W)
    ap.add_argument("--bead-h", type=float, default=machine.BEAD_H)
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--temp", type=int, default=machine.TEMP)
    ap.add_argument("--bed", type=int, default=95)
    ap.add_argument("--press", type=float, default=machine.PRESS_HARD)
    ap.add_argument("--fan", type=int, default=0)
    ap.add_argument("--bed-size", default="229,225")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    bxy = tuple(float(v) for v in a.bed_size.split(","))
    g, st = emit(a.cell, a.cols, a.rows, a.bead_w, a.bead_h, a.flow, a.temp, a.bed, 1.75,
                 bxy, not a.no_home, a.press, a.fan)
    os.makedirs(a.out, exist_ok=True)
    tag = "k1c" if abs(bxy[0] - 229) < 5 else "k2"
    fn = f"{a.out}/honeycomb_{tag}_{a.cols}x{a.rows}_c{a.cell:g}_T{a.temp}.gcode"
    open(fn, "w").write(g)
    print(f"{fn}\n  {a.cols}x{a.rows} cells of {a.cell}mm -> {st['size'][0]} x {st['size'][1]}mm, "
          f"{st['pts']} points, one continuous path")
    print(f"  {st['speed']} mm/s at flow {a.flow} mm3/s, ~{st['mins']} min, {st['grams']} g, "
          f"pressed to {a.press}mm")
