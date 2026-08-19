#!/usr/bin/env python3
"""CLEAVAGE COUPON — how thin can a printed bamboo socket be before it splits?

The furniture review (guides/furniture-forms.md) found that EVERY design's retention is a socket
or a wedge on a bamboo rod, and that **nobody computed cleavage**. Sockets were checked against
compression perpendicular to grain (8-15 MPa). The mode that actually kills the joint is tension
perpendicular to grain -- 2-4 MPa, lower at a node -- and it kills the PRINTED wall too, in hoop.

This coupon is BUILT to answer it by experiment instead of by literature -- no coupon has been
printed or pushed yet, so as of 2026-07-27 it has answered nothing:

    a row of sockets, identical bore, wall thickness stepping 2 -> 6 beads by default
    (--from-beads / --walls; the first draft of this line claimed 2 -> 8, which the defaults
    never produced).

Push a real bamboo rod into each. The thin ones split (printed wall fails in hoop) or split the
bamboo (cleavage). The first one that survives is the minimum wall, measured on the real material
with the real fit -- a number four structural analyses currently have to assume. NOTE: until
2026-07-27 the coupons were silently WRONG for that job -- odd-bead walls printed with the middle
bead missing (see solid.py contours()), a hidden void in exactly the wall being measured.

BORE AND DEPTH COME FROM bamboo/rod_constants.py, NEVER FROM A LITERAL HERE. This coupon measures
the minimum wall FOR THE SOCKET KIT, so it has to be bored and sunk exactly like the kit or the
number it returns belongs to a socket nobody prints. Until 2026-08-04 it was not: it bored
`--stick 6.35 + solid.STICK_FIT 0.70` = 7.05 and sank 12 mm.

  · 6.35 is the nominal 1/4in the v1 kit ASSUMED. Oleg calipered the actual sticks on 2026-08-02
    and they measure O5.8-6.2 (rod_constants). The default rod diameter was a rod that does not
    exist in the batch.
  · 12 mm is the exact depth rod_constants condemns: the v1 socket that sat AT the PLA crush
    figure. The kit's depth is DERIVED (~24.10 mm, crush/4), not picked.

Now: bore = RC.BORE (7.0 FLAT), depth = RC.derive_socket_depth(). NOT RE-MEASURED, and nothing
downstream needs re-measuring, because no cleavage coupon has ever been printed or pushed -- this
file has answered nothing since it was written on 2026-07-27, so it had produced no number that
this change can invalidate.
"""
import argparse, math, os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "bamboo"))
from shapely.geometry import Point
from shapely.ops import unary_union
from shapely.affinity import translate

import machine
import solid as S
import rod_constants as RC          # THE rod/bore/depth truth. Never retyped.


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bore", type=float, default=RC.BORE,
                    help="socket bore, FLAT (rod_constants.BORE)")
    ap.add_argument("--walls", type=int, default=5, help="how many wall thicknesses to try")
    ap.add_argument("--from-beads", type=int, default=2, help="thinnest wall, in beads")
    ap.add_argument("--height", type=float, default=RC.derive_socket_depth(),
                    help="socket depth (DERIVED in rod_constants, not picked)")
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

    bore = a.bore                         # FLAT, from rod_constants. No fit adder, no rod nominal.
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

    print(f"  bore {bore:.2f} mm FLAT (rod_constants.BORE) x {a.height:.2f} mm deep "
          f"(DERIVED); push the real sticks in, they MEASURE "
          f"O{RC.ROD_MIN:g}-{RC.ROD_MAX:g} (calipers, 2026-08-02)")
    for nb, wall, od in labels:
        print(f"    {nb} beads = {wall:.2f} mm wall, OD {od:.2f}")
    print(f"  {a.bead_w:.2f} mm bead at {speed:.1f} mm/s -> {a.bead_w*a.layer_h*speed:.1f} mm3/s "
          f"on {a.material} ({a.printer})")

    g, st = S.emit(region, a.height, a.bead_w, a.layer_h, a.flow, temp,
                   machine.bed_for(a.material, a.printer), 1.75, (bx, by),
                   True, machine.PRESS_HARD, 100,
                   a.bead_w * a.layer_h / machine.PRESS_HARD,   # layer 1: full flow, wide line
                   # aux (side/chassis) fans at the PLA house norm 0.2, NOT True (== 1.0 = 100%),
                   # which chilled the first layer; emit()'s aux_for() still forces full for TPU.
                   0.2, a.printer, f"CLEAVAGE {a.walls} walls",
                   material=a.material, brim=a.brim, centre=False)
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"cleavage_{a.printer}_b{a.bore:g}_w{a.walls}_T{temp:g}.gcode")
    machine.emit_gcode(fn, g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
