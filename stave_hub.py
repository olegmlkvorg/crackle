#!/usr/bin/env python3
"""STAVE hub — the one new part family. A tray whose four tilted sockets carry the bowed rods.

2D REGION EXTRUDED UPWARD, region varies with height. Nothing bridges, nothing overhangs past 14 deg.

  z <= FLOOR ................. solid slab. This is what makes every bore BLIND, so neither the
                              gypsum pour nor the expanding foam can get into a socket.
  FLOOR < z <= RIM_H ......... rim ring (the pour dam) + 2 diagonal ribs + 4 bosses
  z > RIM_H .................. 2 diagonal ribs + 4 bosses ONLY

THE RIBS RUN FULL HEIGHT AND THAT IS A TRAVEL DECISION, NOT A STRUCTURAL ONE.
The bosses sit ON the diagonals and their bores walk radially outward ALONG those same diagonals,
so a corner-to-corner rib intersects every boss at every layer. Rim + 2 ribs + 4 bosses is
therefore ONE CONNECTED ISLAND on every single layer, and the head never hops inside the part.

  --style base   solid floor, 22mm-deep rim, no vents   -> gypsum+sand, used as printed
  --style crown  solid floor, 12mm-deep rim, vented     -> expanding foam, flipped in service

Both are printed bosses-UP with the bore walking OUTWARD. The crown is the base mirrored through
the waist plane, and a mirror through a horizontal plane IS a flip, so the walk direction is
identical in printing coordinates. There is no sign to get wrong.
"""
import math, sys, argparse
sys.path.insert(0, "/Users/olegmalkov/dev/crackle")
from shapely.geometry import box, Point
from shapely.ops import unary_union
from shapely.affinity import translate, rotate, scale
import solid, machine

ap = argparse.ArgumentParser()
ap.add_argument("--style", choices=("base", "crown"), default="base")
ap.add_argument("--side", type=float, default=170.0)
ap.add_argument("--theta", type=float, default=14.0)   # socket tilt from vertical, deg
ap.add_argument("--sock-h", type=float, default=40.0)  # socket VERTICAL extent
ap.add_argument("--floor", type=float, default=2.4)
ap.add_argument("--rim", type=float, default=2.4)      # rim wall thickness (2 beads)
ap.add_argument("--rib", type=float, default=2.4)      # rib thickness (2 beads)
ap.add_argument("--wall", type=float, default=3.6)     # boss wall (3 beads)
ap.add_argument("--r-mouth", type=float, default=98.0) # rod axis radius at the socket MOUTH
ap.add_argument("--contact", type=float, default=7.05) # MEASURED fit Oleg picked off the gauge
ap.add_argument("--bell", type=float, default=1.5)     # bore flare at the mouth
ap.add_argument("--bell-h", type=float, default=6.0)
ap.add_argument("--vent-w", type=float, default=4.8)
ap.add_argument("--vents", type=int, default=0)        # slots PER SIDE, crown only
ap.add_argument("--flow", type=float, default=27.0)    # SUSTAINED, not the 28.8 burst
ap.add_argument("--printer", default="k2plus")
ap.add_argument("--report", action="store_true")
ap.add_argument("--out", default="/private/tmp/claude-501/-Users-olegmalkov-dev-Assist/"
                                 "36659e1b-82c9-403f-979a-79971579343d/scratchpad/out")
A = ap.parse_args()

RIM_H  = 24.4 if A.style == "base" else 14.4
H      = A.floor + A.sock_h                      # part height = floor + socket vertical extent
TH     = math.radians(A.theta)
WALK   = A.sock_h * math.tan(TH)                 # radial travel of the bore over the socket
STRETCH = 1.0 / math.cos(TH)                     # oblique-bore correction, see below
R_FLOOR = A.r_mouth - WALK                       # rod axis radius at the socket FLOOR

# THE SOCKET, SIZED OFF THE MEASURED GAUGE — not off shaft_socket()'s defaults.
# shaft_socket(d) puts its three contact bumps on a circle of diameter (d - grip). Oleg printed the
# fit gauge on 2026-07-27 and chose the 7.05mm modelled bore on a real 6.35 rod, so 7.05 is the
# contact diameter we want and d = 7.05 + 0.25.
SOCK_D = A.contact + 0.25
sock0  = solid.shaft_socket(SOCK_D)              # contact circle 7.05, relief circle 8.30

# OBLIQUE BORE. Sweeping a round section along an axis tilted TH makes a bore whose section NORMAL
# to that axis is narrower by cos(TH) across the tilt. Pre-stretching the horizontal region by
# 1/cos(TH) in the tilt direction is what makes the normal section round again. At 14 deg this is a
# 3.1% correction (0.22mm on a 7.05 bore) and it distorts the 1.6mm bumps by 0.05mm.
sock0  = scale(sock0, xfact=STRETCH, yfact=1.0, origin=(0, 0))
BOSS_R = (SOCK_D + 2 * 0.5) / 2.0 + A.wall       # relief radius + wall

S  = A.side / 2.0
outer = box(-S, -S, S, S)
inner = box(-S + A.rim, -S + A.rim, S - A.rim, S - A.rim)
CORNERS = [(sx, sy) for sx in (-1, 1) for sy in (-1, 1)]


def region_at(t):
    z = t * H
    solid_floor = z <= A.floor

    if solid_floor:
        body = outer
    elif z <= RIM_H:
        body = outer.difference(inner)
        if A.vents:                              # VERTICAL slots — a gap in the 2D region, so the
            span = RIM_H - A.floor               # part still has no bridge and no overhang
            if z >= A.floor + 0.45 * span:
                cuts = []
                for i in range(A.vents):
                    off = (i - (A.vents - 1) / 2.0) * (A.side / (A.vents + 0.6))
                    cuts += [box(off - A.vent_w/2, S - A.rim*2, off + A.vent_w/2, S + A.rim*2),
                             box(off - A.vent_w/2, -S - A.rim*2, off + A.vent_w/2, -S + A.rim*2),
                             box(S - A.rim*2, off - A.vent_w/2, S + A.rim*2, off + A.vent_w/2),
                             box(-S - A.rim*2, off - A.vent_w/2, -S + A.rim*2, off + A.vent_w/2)]
                body = body.difference(unary_union(cuts))
    else:
        body = None

    # two diagonal ribs, corner to corner, FULL HEIGHT
    for ang in (45.0, -45.0):
        rib = rotate(box(-A.side, -A.rib/2, A.side, A.rib/2), ang, origin=(0, 0)).intersection(outer)
        body = rib if body is None else unary_union([body, rib])

    # four bosses, each walking radially outward along its own diagonal
    # BELL MOUTH: over the top BELL_H the bore widens, so the rod does not step from dead straight
    # (clamped in the socket) to R=1080 across one layer line.
    # THE BOSS OUTER FLARES BY THE SAME AMOUNT, and that is not cosmetic. Flaring only the bore
    # sweeps the wall from 3.6 down to 2.1mm, and 2.1 is not a multiple of the 1.2 bead — the fill
    # guard refused the part at 1.021x on exactly that layer. Growing both keeps the wall at 3.6
    # through the flare. This is the same taper-sweeps-every-thickness trap that makes collet()
    # unbuildable; here there is an escape because only ONE surface had to move.
    bell = A.bell * max(0.0, z - (H - A.bell_h)) / A.bell_h if A.bell_h > 0 else 0.0

    for sx, sy in CORNERS:
        # WALK OVER THE SOCKET, NOT OVER THE PART. Spreading the walk across the full part height
        # (t from 0 to 1) puts 2.4mm of it inside the solid floor where there is no bore, so the
        # BORE only leans atan(9.97*40/42.4 / 40) = 13.2 deg while the spec says 14.0. Caught by
        # measuring the emitted file, not by reading this code. The socket runs z=FLOOR..H, so the
        # walk must be parametrised on exactly that interval.
        r  = R_FLOOR + max(0.0, z - A.floor) / A.sock_h * WALK
        cx, cy = sx * r / math.sqrt(2), sy * r / math.sqrt(2)
        adeg = math.degrees(math.atan2(sy, sx))
        ring = scale(Point(0, 0).buffer(BOSS_R, 64), xfact=STRETCH, yfact=1.0, origin=(0, 0))
        if bell:
            ring = ring.buffer(bell)
        ring = translate(rotate(ring, adeg, origin=(0, 0)), cx, cy)
        body = unary_union([body, ring])
        if not solid_floor:
            s = sock0.buffer(bell) if bell else sock0
            s = translate(rotate(s, adeg, origin=(0, 0)), cx, cy)
            body = body.difference(s)
    return body


class Ns: pass
a = Ns()
a.height, a.bead_w, a.layer_h = H, 1.2, 0.4
a.material, a.printer = "pla", A.printer
a.temp = machine.temp_for(a.material)
a.flow = machine.flow_for(a.material, A.flow, f" for {A.style} hub")
a.bed, a.press, a.first_w, a.fan, a.aux = 0, 0.10, 3.0, 51, 0.2
a.no_home, a.stick, a.wall = False, 6.35, A.wall
a.out = A.out

print(f"STAVE {A.style.upper()} HUB  {A.side}x{A.side}x{H}mm   rim {RIM_H}mm  vents {A.vents}/side")
print(f"  socket: contact dia {A.contact} (MEASURED gauge fit), relief {SOCK_D+1.0:.2f}, "
      f"boss OD {2*BOSS_R:.2f}, wall {A.wall}")
print(f"  tilt {A.theta} deg -> walk {WALK:.2f}mm over {A.sock_h}mm, "
      f"step {WALK/(A.sock_h/0.4):.4f} mm/layer = {WALK/(A.sock_h/0.4)/1.2*100:.1f}% of a bead")
print(f"  oblique stretch 1/cos = {STRETCH:.4f}; rod axis r {R_FLOOR:.1f} (floor) -> "
      f"{A.r_mouth:.1f} (mouth); boss reaches x={A.r_mouth/math.sqrt(2)+BOSS_R*STRETCH:.1f} vs "
      f"half-side {S:.1f}")
if A.report:
    # CAVITY AND MATERIAL VOLUME, integrated off the SAME region_at that emits the file, and
    # cross-checked against the grams the emitter measured. If the PLA volume here and the emitted
    # grams disagree, the region model is lying and so is every fill number derived from it.
    n = int(round(H / 0.4))
    pla = cav = mz = 0.0
    for i in range(n):
        t = (i + 0.5) / n
        z = t * H
        r = region_at(t)
        pla += r.area * 0.4
        mz  += r.area * 0.4 * z
        if A.floor < z <= RIM_H:
            cav += (inner.area - r.intersection(inner).area) * 0.4
    print(f"\n  region-integrated PLA volume {pla/1000:.1f} cm3 -> {pla*1.24/1000:.1f} g at "
          f"1.24 g/cm3 (compare the emitted grams above)")
    print(f"  PLA centroid height above the part's own base: {mz/pla:.2f} mm")
    print(f"  CAVITY between the {A.floor}mm floor and the {RIM_H}mm rim: {cav/1000:.1f} cm3")
    if A.style == "base":
        for rho in (1.7, 1.85, 2.0):
            print(f"    gypsum15/sand85 at {rho} g/cm3 (ASSUMED, weigh it) -> {cav*rho/1000:.0f} g")
    else:
        print(f"    expanding PU at ~0.025 g/cm3 cured (ASSUMED) -> {cav*0.025/1000:.0f} g; "
              f"needs ~{cav/30/1000:.0f} cm3 of liquid at ~30x expansion")
    sys.exit(0)

import os; os.makedirs(A.out, exist_ok=True)
solid.finish(region_at, a, f"{A.style}hub", f"{A.out}/stave_{A.style}.gcode")
