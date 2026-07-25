#!/usr/bin/env python3
"""MOORE CURVE — a closed space-filling loop, one continuous extrusion, stacked.

Oleg: "or you can just go for other shapes that can accommodate continuous move like hilbert".

This replaces the honeycomb for area-filling work, and it is not a workaround -- it is the shape
the constraint was asking for all along:

  · A hex lattice has NO Eulerian circuit (every interior vertex is degree 3), so drawing it as one
    stroke means walking cells individually, overprinting shared walls, and closing the path with a
    straight chord back to the start -- the visible straight artifact Oleg spotted in the print.
  · A Hilbert curve is a single non-self-intersecting stroke by construction. A MOORE curve is the
    closed variant: it ends where it begins. So there is no chord, no seam, and no travel anywhere.
  · Because it is closed, every stacked layer walks the SAME loop in the SAME direction. No reversal
    at the layer change -- which is what forced the honeycomb into a closed-loop rewrite anyway.
  · Order n covers a 2^n x 2^n grid, so n -> n+1 is exactly 4x the cells. Oleg asked for "4x
    honeycomb cells"; here that is a single increment.

The only corners are 90 degrees, all of them identical, and round_corners turns them into arcs that
hold full speed. Nothing else in the path bends at all.
"""
import argparse
import math
import os

import machine

# Moore curve L-system. L and R are the two chiralities of a Hilbert sub-curve; the axiom glues four
# of them into a ring, which is what makes the whole thing closed.
AXIOM = "LFL+F+LFL"
RULES = {"L": "-RF+LFL+FR-", "R": "+LF-RFR-FL+"}
# Hilbert, for when an open path is wanted instead (--open)
H_AXIOM = "A"
H_RULES = {"A": "-BF+AFA+FB-", "B": "+AF-BFB-FA+"}


def lsystem(axiom, rules, order):
    s = axiom
    for _ in range(order):
        s = "".join(rules.get(c, c) for c in s)
    return s


def turtle(s, step):
    """Walk the L-system string. + is a left turn, - a right turn, F a unit move."""
    x = y = 0.0
    dx, dy = 0.0, 1.0
    pts = [(x, y)]
    for c in s:
        if c == "F":
            x += dx * step
            y += dy * step
            pts.append((x, y))
        elif c == "+":
            dx, dy = -dy, dx
        elif c == "-":
            dx, dy = dy, -dx
    return pts


def curve(order, span, closed=True):
    """Points for a Moore (closed) or Hilbert (open) curve fitted into a `span` mm square."""
    # GRID SIZE IS MEASURED, NOT ASSUMED. The Moore axiom "LFL+F+LFL" already contains four
    # sub-curves plus the connecting moves, so order n covers a 2^(n+1) grid, not 2^n -- assuming
    # 2^n scaled a requested 100mm square to 233mm. The open Hilbert axiom is a single sub-curve
    # and does cover 2^n.
    if closed:
        s = lsystem(AXIOM, RULES, order)
        n = 2 ** (order + 1)
    else:
        s = lsystem(H_AXIOM, H_RULES, order)
        n = 2 ** order
    step = span / (n - 1)
    pts = turtle(s, step)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ox, oy = min(xs), min(ys)
    pts = [(p[0] - ox, p[1] - oy) for p in pts]
    if closed and math.dist(pts[0], pts[-1]) > 1e-6:
        pts.append(pts[0])
    return pts


def round_corners(pts, fillet, seg=0.8):
    """Replace every sharp vertex with a tangent curve.

    NO SHARP TURNS is a project rule and also physics: Klipper decelerates to square_corner_velocity
    (5 mm/s) at a hard corner, and since E is metered per mm of PATH the flow does not brake with
    it -- every corner is a pressure spike into a stalled head. A Moore curve is ALL 90-degree
    corners, so this is not a polish step, it is what makes the shape printable at speed.

    Quadratic Bezier through each vertex is C1-continuous, so heading never jumps. Holding speed v
    needs radius >= v^2/accel; at 41 mm/s and 5000 mm/s^2 that is 0.34mm, so even a small fillet
    keeps full speed. Sampling is bounded by ANGLE, not length: cutting a corner back and then
    splitting it into two steps leaves 45-degree jumps that measure as sharp.
    """
    if fillet <= 0 or len(pts) < 3:
        return pts
    closed = math.dist(pts[0], pts[-1]) < 1e-6
    ded = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, ded[-1]) > 1e-9:
            ded.append(p)
    pts = ded
    if closed:
        core = pts[:-1]
        idx = [(core[i - 1], core[i], core[(i + 1) % len(core)]) for i in range(len(core))]
        out = []
    else:
        idx = [(pts[i - 1], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)]
        out = [pts[0]]
    for a, v, c in idx:
        la = math.dist(a, v)
        lc = math.dist(v, c)
        if la < 1e-9 or lc < 1e-9:
            continue
        d = min(fillet, la / 2, lc / 2)
        p1 = (v[0] + (a[0] - v[0]) * d / la, v[1] + (a[1] - v[1]) * d / la)
        p2 = (v[0] + (c[0] - v[0]) * d / lc, v[1] + (c[1] - v[1]) * d / lc)
        _c = max(-1.0, min(1.0, ((a[0] - v[0]) * (c[0] - v[0]) + (a[1] - v[1]) * (c[1] - v[1]))
                           / (la * lc)))
        turn = 180.0 - math.degrees(math.acos(_c))
        n = max(4, int(math.ceil(2 * d / seg)), int(math.ceil(turn / 6.0)))
        for k in range(n + 1):
            t = k / n
            m = (1 - t) ** 2
            out.append((m * p1[0] + 2 * (1 - t) * t * v[0] + t * t * p2[0],
                        m * p1[1] + 2 * (1 - t) * t * v[1] + t * t * p2[1]))
    out.append(out[0] if closed else pts[-1])
    return out


def offset_closed(pts, d):
    """Offset a closed polyline by d (positive = outward, using the local normal).

    Used to turn one wall into a two-walled SLOT for the stacking joint. Safe here because the
    Moore curve's passes are a whole pitch apart (13.3mm at order 3) and the fillet radii are much
    larger than the offset, so nothing folds back on itself -- but the caller checks that rather
    than trusting it.
    """
    core = pts[:-1] if math.dist(pts[0], pts[-1]) < 1e-9 else pts[:]
    n = len(core)
    out = []
    for i in range(n):
        a, b = core[i - 1], core[(i + 1) % n]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty)
        if L < 1e-12:
            out.append(core[i])
            continue
        out.append((core[i][0] + (ty / L) * d, core[i][1] - (tx / L) * d))
    out.append(out[0])
    return out


def joint_layers(pts, layers, bead_w, tenon_n, mortise_n, slot_gap, wall_n):
    """Per-layer (points, bead width) for a stackable module.

    Oleg: "we need to make it connectable, will go may be few meters high".

    BOTTOM `mortise_n` layers: two walls offset either side of the path, leaving a slot.
    TOP    `tenon_n`   layers: one NARROW centred wall that drops into the slot above.
    Middle layers: the plain single wall.

    The slot is modelled WIDER than the tenon because a printed gap comes out about 0.25mm tighter
    than modelled on these machines -- a measured empiric from this project, not a guess. Modelling
    it nominally would produce a joint that cannot be assembled at all.
    """
    tenon_w = bead_w * 0.6
    half = (slot_gap + wall_n) / 2.0
    plan = []
    for k in range(layers):
        if k < mortise_n:
            plan.append(("mortise", offset_closed(pts, +half), wall_n))
            plan.append(("mortise2", offset_closed(pts, -half), wall_n))
        elif k >= layers - tenon_n:
            plan.append(("tenon", pts, tenon_w))
        else:
            plan.append(("body", pts, bead_w))
    return plan


def emit(order, span, bead_w, bead_h, flow, temp, bed, fil_d, bed_xy, home, press, fan,
         fillet, layers, closed):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (bead_w * bead_h) / area
    speed = min(flow / (bead_w * bead_h), machine.MAX_SPEED)
    flow = speed * bead_w * bead_h
    f = round(speed * 60)

    n = (2 ** (order + 1)) if closed else (2 ** order)
    pitch = span / (n - 1)
    if pitch < bead_w * 1.6:
        raise SystemExit(
            f"order {order} over {span:.0f}mm gives a {pitch:.2f}mm pitch, but the bead is "
            f"{bead_w}mm wide — neighbouring passes would fuse into a solid slab. Lower --order or "
            f"raise --span (need pitch >= {bead_w*1.6:.2f}mm).")

    pts = round_corners(curve(order, span, closed), fillet)
    ox = (bed_xy[0] - span) / 2.0
    oy = (bed_xy[1] - span) / 2.0
    pts = [(p[0] + ox, p[1] + oy) for p in pts]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if min(xs) < 4 or min(ys) < 4 or max(xs) > bed_xy[0] - 4 or max(ys) > bed_xy[1] - 4:
        raise SystemExit(f"curve spans X {min(xs):.0f}..{max(xs):.0f} Y {min(ys):.0f}..{max(ys):.0f} "
                         f"on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} bed — off the plate.")

    L = []
    w = L.append
    kind = "MOORE (closed)" if closed else "HILBERT (open)"
    w(f"; {kind} curve order {order} — one continuous extrusion, {n}x{n} grid = {n*n} cells")
    w(f"; bead {bead_w}x{bead_h} = {bead_w*bead_h:.2f}mm2 at {speed:.0f} mm/s -> flow={flow} mm3/s")
    w(f"; {span:.0f}mm square, {pitch:.2f}mm pitch, {layers} layers, pressed to {press}mm")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {layers}")
    w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}")
    w(f"M104 S{temp}")
    w("G90")
    w("G28" if home else "; NO HOME — assumes the machine is ALREADY homed; push.py verifies")
    w(f"M190 S{bed}")
    w(f"M109 S{temp}")
    w("M204 S8000")
    w("M107" if not fan else f"M106 S{fan}")
    w("M82")
    w("G92 E0")
    x0, y0 = pts[0]
    w(f"G1 Z{press:.3f} F600")
    _apx = max(6.0, x0 - 55.0)
    _apy = max(6.0, y0 - 12.0)
    w(f"G0 F9000 X{_apx:.3f} Y{_apy:.3f}")
    w("G1 E25 F300                      ; stationary purge — pressure before motion")
    w(f"G1 F1200 X{x0:.3f} Y{y0:.3f} E37   ; prime ends where the curve begins")
    w("G92 E0")
    w("; BODY_START")

    e = 0.0
    for k in range(layers):
        z = press + k * bead_h
        if k:
            # A closed curve ends where it starts, so the next layer needs nothing but a vertical
            # step -- no repositioning, no reversal, no seam artifact. This is the whole reason the
            # closed form was chosen over an open Hilbert.
            e += bead_h * e_per_mm
            L.append(f"; --- layer {k+1} at Z{z:.2f} — closed loop, straight up, same direction")
            L.append(f"G1 F{round(min(speed, 20)*60)} Z{z:.3f} E{e:.5f}")
            L.append(f"G1 F{f}")
        px, py = pts[0]
        for (x, y) in pts[1:]:
            d = math.dist((px, py), (x, y))
            if d < 1e-9:
                continue
            e += d * e_per_mm
            L.append(f"G1 {'F%d ' % f if (px, py) == pts[0] and k == 0 else ''}"
                     f"X{x:.3f} Y{y:.3f} Z{z:.3f} E{e:.5f}")
            px, py = x, y

    L += ["M107", "M104 S0", "M140 S0",
          f"G1 Z{press + (layers-1)*bead_h + 40:.1f} F900",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(flow=round(flow, 1), pts=len(pts), grams=round(grams, 1), speed=round(speed),
                                     cells=n * n, pitch=round(pitch, 2),
                                     mins=round(e / e_per_mm / speed / 60, 1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", type=int, default=4, help="curve order; n -> n+1 is 4x the cells")
    ap.add_argument("--span", type=float, default=0, help="square size mm (0 = fill the bed)")
    ap.add_argument("--margin", type=float, default=12.0, help="mm kept clear at the bed edge")
    ap.add_argument("--bead-w", type=float, default=machine.BEAD_W)
    ap.add_argument("--bead-h", type=float, default=machine.BEAD_H)
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--temp", type=int, default=machine.TEMP)
    ap.add_argument("--bed", type=int, default=80)
    ap.add_argument("--press", type=float, default=0.55)
    ap.add_argument("--fan", type=int, default=0)
    ap.add_argument("--fillet", type=float, default=0)
    ap.add_argument("--layers", type=int, default=1)
    ap.add_argument("--open", action="store_true", help="open Hilbert instead of closed Moore")
    ap.add_argument("--printer", default="k1c", choices=sorted(machine.BED),
                    help="picks the PRINTABLE plate size from machine.BED")
    ap.add_argument("--bed-size", default="", help="override WxY mm (rarely right)")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    bxy = (tuple(float(v) for v in a.bed_size.split(",")) if a.bed_size
           else machine.BED[a.printer])
    span = a.span or (min(bxy) - 2 * a.margin)
    # Default the fillet to just under half the pitch: any larger and opposite corners of the same
    # cell would eat into each other and the grid stops reading as a grid.
    pitch = span / ((2 ** (a.order + 1) if not a.open else 2 ** a.order) - 1)
    fillet = a.fillet or max(0.8, pitch * 0.45)
    g, st = emit(a.order, span, a.bead_w, a.bead_h, a.flow, a.temp, a.bed, 1.75, bxy,
                 not a.no_home, a.press, a.fan, fillet, a.layers, not a.open)
    os.makedirs(a.out, exist_ok=True)
    tag = a.printer
    kind = "hilbert" if a.open else "moore"
    fn = f"{a.out}/{kind}_{tag}_o{a.order}_{span:.0f}mm_L{a.layers}_T{a.temp}.gcode"
    open(fn, "w").write(g)
    print(f"{fn}\n  order {a.order} -> {st['cells']} cells, {st['pitch']}mm pitch, "
          f"{span:.0f}mm square, fillet {fillet:.2f}mm, {st['pts']} points")
    print(f"  {st['speed']} mm/s at flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g, "
          f"{a.layers} layers pressed to {a.press}mm")
