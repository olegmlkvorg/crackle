#!/usr/bin/env python3
"""HANGER — a hook and a hole, a couple of layers thick.

Oleg, 2026-07-27: "and on k1 lets print hangers, hist a hook and a hole coule layers width".

The whole part is ONE flat 2D region extruded a few layers up, which is the only thing this
toolchain makes natively: vertical walls, no bridges, no supports. A hook lying flat on the plate
is the ideal case for it — the shape IS the cross-section.

WHY THE HOOK OPENS SIDEWAYS, not upward. Printed flat, the layers stack through the hook's
THICKNESS, so a load pulling the hook open peels along layer lines only if the opening faces the
build direction. Lying flat, the load runs across the beads in-plane, which is the strong axis of
an FDM part by a wide margin. This orientation is chosen for strength, not convenience.

The hole is a real hole: the region is a difference, so the toolpath walks around it and the
bore is a printed wall rather than a gap in an infill pattern.
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

import machine
import solid as S


def hook_region(shank, hook_r, thick, hole_d, gap_deg, tip):
    """A J: straight shank, a hook curled off the bottom, an eye at the top.

    Everything is built as a fattened CENTRELINE (LineString.buffer), so the wall thickness is one
    number and there are no thin slivers where parts meet -- the union of round-capped strokes is
    always at least `thick` wide.
    """
    r = thick / 2.0
    eye_r = hole_d / 2.0 + thick / 2.0          # material ring around the hole
    top = shank                                  # eye centre sits at the top of the shank

    # shank: straight up the middle
    parts = [LineString([(0.0, 0.0), (0.0, top)]).buffer(r, resolution=16)]

    # eye: an annulus at the top
    parts.append(Point(0.0, top).buffer(eye_r, resolution=48))

    # hook: an arc curling from the shank foot, opening to one side
    #   sweeps from -90deg (straight down off the shank) round to the gap
    a0, a1 = -90.0, -90.0 - (360.0 - gap_deg)
    cx, cy = 0.0, -hook_r
    pts = []
    n = max(24, int(abs(a1 - a0) / 3))
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((cx + hook_r * math.cos(a), cy + hook_r * math.sin(a)))
    parts.append(LineString(pts).buffer(r, resolution=16))

    # tip: a short straight run off the hook end so it does not simply stop mid-air
    if tip > 0:
        ax, ay = pts[-1]
        bx, by = pts[-2]
        dx, dy = ax - bx, ay - by
        m = math.hypot(dx, dy) or 1.0
        parts.append(LineString([(ax, ay), (ax + dx / m * tip, ay + dy / m * tip)])
                     .buffer(r, resolution=16))

    body = unary_union(parts)
    return body.difference(Point(0.0, top).buffer(eye_r - thick / 2.0, resolution=48))


def lip_region(wall, grip, shank, hook_r, thick, hole_d, tip):
    """An over-the-edge hook: hangs on a vertical wall by hooking OVER its top.

    Different animal from the J. The J hangs FROM something by its eye. This one grips a lip:
      * a short back leg drops down the far side of the wall
      * a 180-degree arc passes over the top, its inner clearance sized to the WALL THICKNESS
      * the front leg (shank) descends on the near side
      * the load hook curls forward off the bottom

    The mouth is `wall` wide at the inside of the arc, so the part sits on the lip rather than
    being sprung onto it -- a printed part sprung over an edge is a part loaded in cleavage
    along its layer lines, which is the weak direction.
    """
    r = thick / 2.0
    inner = wall / 2.0                       # arc centreline radius: half the wall + half a wall
    cr = inner + r                           # centreline of the stroke going over the lip
    parts = []

    # back leg: down the far side
    bx = -cr
    parts.append(LineString([(bx, 0.0), (bx, -grip)]).buffer(r, resolution=16))

    # the arc over the top of the wall
    pts = []
    n = 48
    for i in range(n + 1):
        a = math.pi - math.pi * i / n        # 180deg -> 0deg
        pts.append((cr * math.cos(a), cr * math.sin(a)))
    parts.append(LineString(pts).buffer(r, resolution=16))

    # front leg / shank: down the near side
    fx = cr
    parts.append(LineString([(fx, 0.0), (fx, -shank)]).buffer(r, resolution=16))

    # load hook: curls FORWARD off the bottom of the shank
    cx, cy = fx + hook_r, -shank
    arc = []
    for i in range(37):
        a = math.radians(180.0 - 150.0 * i / 36.0)
        arc.append((cx + hook_r * math.cos(a), cy + hook_r * math.sin(a)))
    parts.append(LineString(arc).buffer(r, resolution=16))
    if tip > 0:
        ax, ay = arc[-1]; bx2, by2 = arc[-2]
        dx, dy = ax - bx2, ay - by2
        m = math.hypot(dx, dy) or 1.0
        parts.append(LineString([(ax, ay), (ax + dx / m * tip, ay + dy / m * tip)])
                     .buffer(r, resolution=16))

    body = unary_union(parts)
    if hole_d > 0:                            # optional eye through the back leg
        body = body.difference(Point(bx, -grip + hole_d).buffer(hole_d / 2.0, resolution=32))
    return body


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--style", choices=("j", "lip"), default="j",
                    help="j = hangs from its eye; lip = hooks OVER a vertical wall")
    ap.add_argument("--wall", type=float, default=25.0, help="lip style: wall thickness to grip")
    ap.add_argument("--grip", type=float, default=20.0, help="lip style: how far down the far side")
    ap.add_argument("--shank", type=float, default=45.0, help="straight length above the hook")
    ap.add_argument("--hook-r", type=float, default=13.0, help="hook inner curl radius")
    ap.add_argument("--thick", type=float, default=6.0, help="wall thickness of the stroke")
    ap.add_argument("--hole", type=float, default=5.0, help="hole diameter")
    ap.add_argument("--gap", type=float, default=95.0, help="hook mouth opening, degrees")
    ap.add_argument("--tip", type=float, default=6.0, help="straight run at the hook tip")
    ap.add_argument("--layers", type=int, default=4, help="'couple layers width'")
    ap.add_argument("--n", type=int, default=1, help="how many hangers on the plate")
    ap.add_argument("--spacing", type=float, default=0.0, help="0 = auto from part width")
    ap.add_argument("--printer", default="k1c", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--bead-w", type=float, default=None)
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--flow", type=float, default=None)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    a.flow = a.flow or machine.SUSTAINED_FLOW_BY_MATERIAL[a.material]
    # bead first, then the speed the bead allows -- 50 is the north star, a fat bead pulls it down
    a.bead_w = a.bead_w or machine.bead_for_flow(a.flow, a.layer_h)
    speed = machine.speed_for_flow(a.flow, a.bead_w, a.layer_h)
    temp = machine.temp_for(a.material)

    # THICKNESS SNAPS TO A WHOLE NUMBER OF BEADS. A non-integer wall leaves the inward and
    # outward contour families colliding in the middle, which over-fills the layer and ploughs
    # the part off the plate -- solid.py's own guard refuses it, and it refused 6.0mm here.
    # This is the same bead-multiple rule the thick-profile parts already follow.
    n_beads = max(2, round(a.thick / a.bead_w))
    snapped = n_beads * a.bead_w
    if abs(snapped - a.thick) > 1e-6:
        print(f"  thickness {a.thick:g} -> {snapped:.2f} mm ({n_beads} x {a.bead_w:.2f} bead)")
        a.thick = snapped

    if a.style == "lip":
        one = lip_region(a.wall, a.grip, a.shank, a.hook_r, a.thick, a.hole, a.tip)
    else:
        one = hook_region(a.shank, a.hook_r, a.thick, a.hole, a.gap, a.tip)
    minx, miny, maxx, maxy = one.bounds
    w = maxx - minx
    pitch = a.spacing or (w + 12.0)
    parts = [S._rtranslate(one, i * pitch, 0.0) if hasattr(S, "_rtranslate")
             else __import__("shapely.affinity", fromlist=["translate"]).translate(one, i * pitch, 0)
             for i in range(a.n)]
    region = unary_union(parts)

    height = machine.PRESS_HARD + a.layer_h * (a.layers - 1)
    bx, by = machine.BED[a.printer]
    rminx, rminy, rmaxx, rmaxy = region.bounds
    print(f"  hanger: {rmaxx-rminx:.0f} x {rmaxy-rminy:.0f} mm, {a.layers} layers = "
          f"{height:.2f} mm thick, hole {a.hole:.1f} mm")
    print(f"  {a.bead_w:.2f}mm bead at {speed:.1f} mm/s -> {a.bead_w*a.layer_h*speed:.1f} mm3/s "
          f"on {a.material} ({a.printer})")

    g, st = S.emit(region, height, a.bead_w, a.layer_h, a.flow, temp,
                   machine.bed_for(a.material, a.printer), 1.75, (bx, by),
                   # first_w = the BEAD, not the spread width. Feeding layer 1 the body's
                   # cross-section at a 0.1 press over-fills a solid region 3.3x: the paths are
                   # bead-spaced, so a 11mm ribbon overlaps its neighbours six times. Same
                   # failure that sheared the rosetta off the plate.
                   True, machine.PRESS_HARD, 100, a.bead_w,
                   True, a.printer, f"HANGER x{a.n}", material=a.material)
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"hanger{a.style}_{a.printer}_x{a.n}_h{a.hole:g}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
