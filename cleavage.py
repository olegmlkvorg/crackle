#!/usr/bin/env python3
"""CLEAVAGE COUPON — how thin can a printed bamboo socket be before it splits?

The furniture review (guides/furniture-forms.md) found that EVERY design's retention is a socket
or a wedge on a bamboo rod, and that **nobody computed cleavage**. Sockets were checked against
compression perpendicular to grain (8-15 MPa). The mode that actually kills the joint is tension
perpendicular to grain -- 2-4 MPa, lower at a node -- and it kills the PRINTED wall too, in hoop.

This coupon answers it by experiment instead of by literature:

    a row of sockets, identical bore, wall thickness stepping 2 -> 8 beads.

Push a real bamboo rod into each. The thin ones split (printed wall fails in hoop) or split the
bamboo (cleavage). The first one that survives is the minimum wall, measured on the real material
with the real fit -- a number four structural analyses currently have to assume.

Bore uses the MEASURED bamboo fit, not the metal shrink figure: STICK_FIT 0.70 on a 6.35 rod.
That distinction already condemned ~21 parts once (see machine.py / solid.py notes).
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import Point
from shapely.ops import unary_union
from shapely.affinity import translate

import machine
import solid as S


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stick", type=float, default=6.35, help="bamboo rod diameter")
    ap.add_argument("--walls", type=int, default=5, help="how many wall thicknesses to try")
    ap.add_argument("--from-beads", type=int, default=2, help="thinnest wall, in beads")
    ap.add_argument("--height", type=float, default=12.0, help="socket depth")
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--bead-w", type=float, default=None)
    ap.add_argument("--flow", type=float, default=None)
    ap.add_argument("--brim", type=int, default=0)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    a.flow = a.flow or machine.flow_cap(a.material, a.printer)
    a.bead_w = a.bead_w or machine.bead_for_flow(a.flow, a.layer_h)
    speed = machine.speed_for_flow(a.flow, a.bead_w, a.layer_h)
    temp = machine.temp_for(a.material)

    bore = a.stick + S.STICK_FIT          # MEASURED bamboo fit, not the metal SHRINK
    parts, labels, x = [], [], 0.0
    for i in range(a.walls):
        nb = a.from_beads + i
        wall = nb * a.bead_w              # whole beads: a fractional wall collides its contours
        od = bore + 2 * wall
        ring = Point(x + od / 2, 0.0).buffer(od / 2, resolution=64) \
            .difference(Point(x + od / 2, 0.0).buffer(bore / 2, resolution=64))
        parts.append(ring)
        labels.append((nb, wall, od))
        x += od + 6.0

    region = unary_union(parts)
    bx, by = machine.BED[a.printer]
    minx, miny, maxx, maxy = region.bounds
    region = translate(region, bx / 2 - (minx + maxx) / 2, by / 2 - (miny + maxy) / 2)

    print(f"  bore {bore:.2f} mm for a {a.stick:g} mm rod (STICK_FIT {S.STICK_FIT}, measured)")
    for nb, wall, od in labels:
        print(f"    {nb} beads = {wall:.2f} mm wall, OD {od:.2f}")
    print(f"  {a.bead_w:.2f} mm bead at {speed:.1f} mm/s -> {a.bead_w*a.layer_h*speed:.1f} mm3/s "
          f"on {a.material} ({a.printer})")

    g, st = S.emit(region, a.height, a.bead_w, a.layer_h, a.flow, temp,
                   machine.bed_for(a.material, a.printer), 1.75, (bx, by),
                   True, machine.PRESS_HARD, 100,
                   a.bead_w * a.layer_h / machine.PRESS_HARD,   # layer 1: full flow, wide line
                   True, a.printer, f"CLEAVAGE {a.walls} walls",
                   material=a.material, brim=a.brim, centre=False)
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"cleavage_{a.printer}_s{a.stick:g}_w{a.walls}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
