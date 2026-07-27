#!/usr/bin/env python3
"""STAVE TEST COUPON — the sub-10-minute print that has to happen before any 90-minute part.

It exists because three separate numbers in this build are inherited rather than measured ON THE
GEOMETRY THAT WILL BE PRINTED:

  1. STICK_FIT = 0.70 was measured on a VERTICAL bore in a flat plate. Every socket in this design
     is a bore leaning 14 deg whose section normal to the rod is corrected by 1/cos(14). The
     correction is verified in the gcode (probe_rod.py: +0.321mm/side modelled, +0.196 expected
     printed) but it has never touched bamboo.
  2. The 14 deg tilt is what sets the bow. If the emitted socket does not hold a real rod at 14 deg
     the bow is not 32mm and every downstream number moves.
  3. Bamboo E varies about 2x with species and moisture, so the 27 N socket couple is the middle of
     a band. The rod's own stiffness is measurable in the same ten minutes with a kitchen scale.

TWO BOSSES, BOTH LEANING THE SAME WAY, at two fits 0.25mm apart — the same sweep-and-let-Oleg-pick
pattern that settled STICK_FIT on 2026-07-27, which is the only fit number in this project that has
ever been right.
"""
import math, sys, argparse, os
sys.path.insert(0, "/Users/olegmalkov/dev/crackle")
from shapely.geometry import box, Point
from shapely.ops import unary_union
from shapely.affinity import translate, scale
import solid, machine

ap = argparse.ArgumentParser()
ap.add_argument("--theta", type=float, default=14.0)
ap.add_argument("--sock-h", type=float, default=40.0)
ap.add_argument("--floor", type=float, default=2.4)
ap.add_argument("--wall", type=float, default=3.6)
ap.add_argument("--fits", default="7.05,6.80")   # contact diameters to compare
ap.add_argument("--pitch", type=float, default=34.0)
ap.add_argument("--flow", type=float, default=machine.SUSTAINED_FLOW_BY_MATERIAL[machine.DEFAULT_MATERIAL])
ap.add_argument("--printer", default=machine.DEFAULT_PRINTER)
ap.add_argument("--out", default="/private/tmp/claude-501/-Users-olegmalkov-dev-Assist/"
                                 "36659e1b-82c9-403f-979a-79971579343d/scratchpad/out")
A = ap.parse_args()

TH   = math.radians(A.theta)
WALK = A.sock_h * math.tan(TH)
STR  = 1.0/math.cos(TH)
H    = A.floor + A.sock_h
FITS = [float(v) for v in A.fits.split(",")]
N    = len(FITS)

socks, BR = [], []
for f in FITS:
    d = f + 0.25
    s = scale(solid.shaft_socket(d), xfact=STR, yfact=1.0, origin=(0, 0))
    socks.append(s)
    BR.append((d + 1.0)/2.0 + A.wall)

PLATE_X = A.pitch*(N-1) + 2*max(BR)*STR + WALK + 24.0
PLATE_Y = 2*max(BR)*STR + 20.0
X0 = -(A.pitch*(N-1))/2.0 - WALK/2.0


def region_at(t):
    z = t*H
    body = box(-PLATE_X/2, -PLATE_Y/2, PLATE_X/2, PLATE_Y/2) if z <= A.floor else None
    for i in range(N):
        # the bore leans along +x only, so both rods lean the same way and can be compared
        cxx = X0 + i*A.pitch + max(0.0, z - A.floor)/A.sock_h*WALK
        ring = translate(scale(Point(0, 0).buffer(BR[i], 64), xfact=STR, yfact=1.0, origin=(0, 0)),
                         cxx, 0)
        body = ring if body is None else unary_union([body, ring])
        if z > A.floor:
            body = body.difference(translate(socks[i], cxx, 0))
    return body


class Ns: pass
a = Ns()
a.height, a.bead_w, a.layer_h = H, 1.2, 0.4
a.material, a.printer = "pla", A.printer
a.temp = machine.temp_for(a.material)
a.flow = machine.flow_for(a.material, A.flow, " for test coupon")
a.bed, a.press, a.first_w, a.fan, a.aux = 0, 0.10, 3.0, 51, 0.2
a.no_home, a.stick, a.wall = False, 6.35, A.wall
a.out = A.out
print(f"STAVE TEST COUPON {PLATE_X:.0f}x{PLATE_Y:.0f}x{H}mm, {N} sockets at {FITS} contact dia, "
      f"pitch {A.pitch}, tilt {A.theta} deg")
print(f"  rod tip offset check: at 400mm above the mouth a correctly-held rod is "
      f"{400*math.tan(TH):.1f} mm sideways")
os.makedirs(A.out, exist_ok=True)
solid.finish(region_at, a, "testcoupon", f"{A.out}/stave_test.gcode")
