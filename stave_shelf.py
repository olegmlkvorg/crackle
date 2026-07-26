#!/usr/bin/env python3
"""STAVE shelf — a flat ribbed plate with four PLAIN clearance bores. No boss, no tilt.

WHY NO TILTED BOSS. STAVE's own shelf carried a 24mm boss bored at the rod's local tangent. The
two stations straddle midspan, so their tangents are +5.5 and -5.5 deg — equal in size, OPPOSITE in
sign — and a 24mm boss with 1.4mm of slop has only atan(1.4/24)=3.3 deg of angular play. Threading
that boss down from a rod tip (18+ deg of mismatch) is geometrically impossible. Deleting the boss
deletes the problem: a 4.8mm plate with a 7.65mm modelled bore has atan(1.05/4.8)=12.3 deg of play
against a 5.5 deg requirement, and the bamboo cross-pin does the locating and the carrying, which
it was always going to do anyway.

TWO BUGS IN solid.shelf_plate() ARE WORKED AROUND HERE, NOT INHERITED:

1. IT BORES BAMBOO WITH THE METAL CONSTANT. Line 1120 is `r = (post_d + SHRINK + clearance)/2`.
   SHRINK is 0.25 and is documented in that same file as "METAL SHAFTS ONLY". The measured bamboo
   fit is STICK_FIT = 0.70, picked by Oleg off a printed gauge on 2026-07-27. The commit that
   introduced STICK_FIT converted plate(), spacer_shell(), collet() and adapter() and MISSED
   shelf_plate — even though the file header names "shelf bores" as one of the things that were
   too tight. Stock, this emits a 6.60mm bore for a 6.35 rod: printed ~6.35, i.e. zero clearance,
   on a part whose own docstring says "a shelf must SLIDE down the posts".

2. THE RIB GRID DOES NOT KNOW WHERE THE BORES ARE. The cells are laid out from the plate edges, so
   a bore can land in a hole and come off the bed as a bore with no material around it. Fixed with
   a solid pad unioned in under each bore before the bore is cut.
"""
import math, sys, argparse
sys.path.insert(0, "/Users/olegmalkov/dev/crackle")
from shapely.geometry import box, Point
from shapely.ops import unary_union
from shapely.affinity import translate
import solid, machine

ap = argparse.ArgumentParser()
ap.add_argument("--side", type=float, default=200.0)
ap.add_argument("--thick", type=float, default=4.8)     # 12 layers
ap.add_argument("--bore-at", type=float, default=88.5)  # rod axis x=y at the shelf station
ap.add_argument("--bore", type=float, default=7.65)     # MODELLED dia = 6.35 + STICK_FIT + 0.60
ap.add_argument("--pad", type=float, default=11.0)      # solid pad radius under each bore
ap.add_argument("--rib", type=float, default=6.0)
ap.add_argument("--cell", type=float, default=30.0)
ap.add_argument("--style", default="ribbed")
ap.add_argument("--flow", type=float, default=27.0)
ap.add_argument("--printer", default="k2plus")
ap.add_argument("--out", default="/private/tmp/claude-501/-Users-olegmalkov-dev-Assist/"
                                 "36659e1b-82c9-403f-979a-79971579343d/scratchpad/out")
A = ap.parse_args()

S = A.side / 2.0
body = box(-S, -S, S, S)

if A.style == "ribbed":
    inner = box(-S + A.rib, -S + A.rib, S - A.rib, S - A.rib)
    holes = []
    n = max(1, int((A.side - 2*A.rib) // A.cell))
    c = (A.side - 2*A.rib) / n
    for i in range(n):
        for j in range(n):
            x0 = -S + A.rib + i*c + A.rib/2.0
            y0 = -S + A.rib + j*c + A.rib/2.0
            h = box(x0, y0, x0 + c - A.rib, y0 + c - A.rib)
            if inner.contains(h):
                holes.append(h)
    if holes:
        body = body.difference(unary_union(holes))

pads, bores = [], []
for sx in (-1, 1):
    for sy in (-1, 1):
        cx, cy = sx*A.bore_at, sy*A.bore_at
        pads.append(Point(cx, cy).buffer(A.pad, 64))
        bores.append(Point(cx, cy).buffer(A.bore/2.0, 64))
body = unary_union([body] + pads).difference(unary_union(bores))

class Ns: pass
a = Ns()
a.height, a.bead_w, a.layer_h = A.thick, 1.2, 0.4
a.material, a.printer = "pla", A.printer
a.temp = machine.temp_for(a.material)
a.flow = machine.flow_for(a.material, A.flow, " for shelf")
a.bed, a.press, a.first_w, a.fan, a.aux = 0, 0.10, 3.0, 51, 0.2
a.no_home, a.stick, a.wall = False, 6.35, A.rib
a.out = A.out

play = math.degrees(math.atan2(A.bore - 0.25 - 6.35, A.thick))
print(f"STAVE SHELF {A.side}x{A.side}x{A.thick}mm, bores at +-{A.bore_at} "
      f"(square {2*A.bore_at:.1f}mm), modelled bore {A.bore} -> ~{A.bore-0.25:.2f} printed")
print(f"  angular play on the rod: {play:.1f} deg (needs 5.5); pad r{A.pad} = "
      f"{A.pad - A.bore/2:.2f}mm of material round each bore = {(A.pad-A.bore/2)/1.2:.1f} beads")
import os; os.makedirs(A.out, exist_ok=True)
solid.finish(body, a, "shelf", f"{A.out}/stave_shelf.gcode")
