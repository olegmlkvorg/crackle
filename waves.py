#!/usr/bin/env python3
"""WAVES — long rippled ribbons, one continuous extrusion, to be shaped by hand while warm.

This began as a broken honeycomb: zigzag rows joined by a single strut per row pair, so it drew a
field of waves with 12 vertical walls for 96 cells -- no closed cells at all. As a honeycomb it was
simply wrong, and it was on its way to being deleted.

Oleg peeled the rows off the plate while they were still warm, splayed them radially and welded
them at the centre: a flower roughly 300mm across with a rippled edge, and the best thing either
machine made that day. 2026-07-25.

So the wave path is kept HERE as its own product instead of being fixed away. What makes it work
as hand-forming feedstock:
  · each ribbon is one uninterrupted strand -- no travels means nothing to snap at
  · the ripple gives the strand spring and grip, so a hand-formed curve HOLDS
  · rounded ends (the corner fillet) make a bent ribbon read as finished, not cut
  · translucent PLA pressed to 0.55mm is thin enough to bend warm, stiff enough to keep the shape

The honeycomb this failed to be now lives in honeycomb.py as a real hex lattice.
See guides/alien-tech-forming.md -- the FORMING vertical arriving on its own.
"""
import argparse
import math
import os

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
    # CLOSE THE CIRCUIT. Stacking by reversing the path makes each layer retrace the previous
    # layer's last segment backwards -- a 180-degree reversal, the sharpest turn there is, with the
    # extruder still running. Closing the comb into a loop instead lets every layer run the SAME
    # direction from the SAME point: no reversal, no travel, and the closing run down the left edge
    # is not waste, it is the left wall.
    if math.dist(pts[0], pts[-1]) > 1e-6:
        pts.append(pts[0])
    return pts


def round_corners(pts, fillet, seg=0.8):
    """Replace every sharp vertex with a tangent curve. NO SHARP TURNS is a project rule, and it is
    also physics: Klipper decelerates to square_corner_velocity (5 mm/s) at a hard corner, so a path
    of 60-degree hex vertices spends its life braking. Since E is metered per mm of PATH, the flow
    does not brake with it — every corner is a pressure spike into a stalled head, which is exactly
    what makes the extruder skip.

    A quadratic Bezier through each vertex is C1-continuous, so direction never jumps. Holding speed
    v through a curve needs radius >= v^2/accel; at 49 mm/s and 5000 mm/s^2 that is 0.5mm, so a
    few-mm fillet keeps FULL speed through every corner. Oleg: "overprint or whatever but no sharp
    turning" — the cut corners overlap slightly, and that is the accepted trade."""
    if fillet <= 0 or len(pts) < 3:
        return pts
    # Near-coincident points clamp the fillet to nothing (d = min(fillet, la/2, lc/2)), leaving a
    # hard corner that no amount of sampling can smooth. Drop them first.
    ded = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, ded[-1]) > 0.5:
            ded.append(p)
    pts = ded
    # A CLOSED LOOP HAS NO FIRST VERTEX. Filleting only the interior points leaves the junction
    # where the path rejoins its own start un-rounded -- and since every stacked layer passes
    # through it, that one hard corner repeats on every layer. Walk closed paths cyclically so the
    # junction is just another vertex.
    closed = math.dist(pts[0], pts[-1]) < 1e-6
    if closed:
        core = pts[:-1]
        idx = [(core[i - 1], core[i], core[(i + 1) % len(core)]) for i in range(len(core))]
    else:
        idx = [(pts[i - 1], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)]
    out = [] if closed else [pts[0]]
    for a, v, c in idx:
        la = math.dist(a, v); lc = math.dist(v, c)
        if la < 1e-9 or lc < 1e-9:
            continue
        d = min(fillet, la / 2, lc / 2)
        p1 = (v[0] + (a[0] - v[0]) * d / la, v[1] + (a[1] - v[1]) * d / la)
        p2 = (v[0] + (c[0] - v[0]) * d / lc, v[1] + (c[1] - v[1]) * d / lc)
        # Sample by ANGLE, not by length. A 90-degree corner cut back only 0.3mm still turns 90
        # degrees; splitting it into 2 steps leaves 45-degree jumps. Bounding the angular step is
        # what actually removes the sharp turn.
        _c = max(-1.0, min(1.0, ((a[0]-v[0])*(c[0]-v[0]) + (a[1]-v[1])*(c[1]-v[1]))
                           / (la * lc)))
        turn = 180.0 - math.degrees(math.acos(_c))
        n = max(4, int(math.ceil(2 * d / seg)), int(math.ceil(turn / 6.0)))
        for k in range(n + 1):
            t = k / n
            m = (1 - t) ** 2
            out.append((m * p1[0] + 2 * (1 - t) * t * v[0] + t * t * p2[0],
                        m * p1[1] + 2 * (1 - t) * t * v[1] + t * t * p2[1]))
    if closed:
        out.append(out[0])
    else:
        out.append(pts[-1])
    return out


def emit(cell, cols, rows, bead_w, bead_h, flow, temp, bed, fil_d, bed_xy, home, press, fan, fillet=3.0, layers=1):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (bead_w * bead_h) / area
    speed = flow / (bead_w * bead_h)
    f = round(speed * 60)
    s = cell
    w_total = cols * 2 * (s * math.sqrt(3) / 2.0)      # wave-row geometry, not hex-cell
    h_total = (rows - 1) * s + s / 2.0
    ox = (bed_xy[0] - w_total) / 2.0
    oy = (bed_xy[1] - h_total) / 2.0
    if ox < 8 or oy < 8:
        raise SystemExit(f"{cols}x{rows} cells of {cell}mm = {w_total:.0f} x {h_total:.0f}mm — "
                         f"too big for a {bed_xy[0]:.0f} x {bed_xy[1]:.0f} bed. Reduce --cols/--rows "
                         f"or --cell.")
    pts = round_corners(comb_path(cell, cols, rows, ox, oy), fillet)
    _xs = [p[0] for p in pts]; _ys = [p[1] for p in pts]
    if min(_xs) < 4 or min(_ys) < 4 or max(_xs) > bed_xy[0] - 4 or max(_ys) > bed_xy[1] - 4:
        raise SystemExit(f"comb spans X {min(_xs):.0f}..{max(_xs):.0f} Y {min(_ys):.0f}.."
                         f"{max(_ys):.0f} on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} bed — off the plate.")

    L = []; w = L.append
    w(f"; WAVES — rippled ribbons to shape by hand, {cols}x{rows} of {cell}mm")
    w(f"; bead {bead_w}x{bead_h} = {bead_w*bead_h:.2f}mm2 at {speed:.0f} mm/s -> flow={flow} mm3/s")
    w(f"; {w_total:.0f} x {h_total:.0f}mm on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} bed, pressed to {press}mm")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {layers}"); w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — assumes the machine is ALREADY homed; push.py verifies and homes if not")
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
    # STACK THE COMB. A single pass is a drawing of a honeycomb; stacked passes are a honeycomb --
    # walls with height. Each layer REVERSES the path so it starts exactly where the previous one
    # finished: no travel across the part, and the seam is a single vertical step extruded in place.
    #
    # Layer 1 sits at `press` (squashed into the plate so it BONDS). Every layer above steps by the
    # full bead height, because it is landing on plastic rather than glass and does not need to be
    # crushed -- pressing an upper layer just ploughs the one beneath it.
    for k in range(layers):
        seq = pts        # closed loop -- same direction every layer, so no seam reversal
        z = press + k * bead_h
        if k:
            L.append(f"; --- layer {k+1} at Z{z:.2f} -- closed loop, starts where layer "
                     f"{k} ended, same direction")
            e += bead_h * e_per_mm          # keep extruding through the vertical step
            L.append(f"G1 F{round(min(speed, 20)*60)} Z{z:.3f} E{e:.5f}")
            L.append(f"G1 F{f}")
        px, py = seq[0]
        for (x, y) in seq[1:]:
            d = math.dist((px, py), (x, y))
            if d < 1e-9:
                continue
            e += d * e_per_mm
            L.append(f"G1 {'F%d ' % f if (px, py) == seq[0] and k == 0 else ''}"
                     f"X{x:.3f} Y{y:.3f} Z{z:.3f} E{e:.5f}")
            px, py = x, y
    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{press+(layers-1)*bead_h+40:.1f} F900",
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
    ap.add_argument("--layers", type=int, default=1, help="stacked layers of comb")
    ap.add_argument("--fillet", type=float, default=3.0,
                    help="corner rounding radius mm — 0 gives sharp corners (banned)")
    ap.add_argument("--bed-size", default="229,225")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    bxy = tuple(float(v) for v in a.bed_size.split(","))
    g, st = emit(a.cell, a.cols, a.rows, a.bead_w, a.bead_h, a.flow, a.temp, a.bed, 1.75,
                 bxy, not a.no_home, a.press, a.fan, a.fillet, a.layers)
    os.makedirs(a.out, exist_ok=True)
    tag = "k1c" if abs(bxy[0] - 229) < 5 else "k2"
    fn = f"{a.out}/waves_{tag}_{a.cols}x{a.rows}_c{a.cell:g}_T{a.temp}.gcode"
    open(fn, "w").write(g)
    print(f"{fn}\n  {a.rows} ribbons of {a.cols} waves at {a.cell}mm -> "
          f"{st['size'][0]} x {st['size'][1]}mm, {st['pts']} points, one continuous path")
    print(f"  {st['speed']} mm/s at flow {a.flow} mm3/s, ~{st['mins']} min, {st['grams']} g, "
          f"pressed to {a.press}mm")
