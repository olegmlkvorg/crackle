#!/usr/bin/env python3
"""CATCH CUP STL — the end of the run: a belly bowl that collects the marbles.

Bottom-up: flat floor disc (prints as the solid vase bottom), 45° flare to a Ø100 belly,
a cosine shoulder curving back in over the marbles (so bounces stay inside), then the standard
tapered female socket (marble_common) to receive the last part's spigot. Terminus: no spigot.
Single-valued r(z) + a flat floor: exactly what slicer VASE mode prints (solid bottom
layers, then one continuous wall).

Usage: python3 catch_cup_stl.py [--belly 100] [--floor 76] [--points 120] [--out catch_cup.stl]
"""
import argparse, math

import marble_common as mc


def profile(belly, floor, couple):
    rb, rf, rn = belly / 2, floor / 2, mc.SOCKET_BOT_R   # neck = socket bottom radius
    h_flare = mc.cone_h(rf, rb)                       # 45° flare from floor edge to belly
    p = [(0.0, rf), (h_flare, rb)]                    # floor edge -> belly
    z = h_flare + 12.0
    p.append((z, rb))                                 # straight belly band
    dr = rb - rn                                      # cosine shoulder in to the neck;
    dz = dr * math.pi / 2 / 1.08                      # height keeps peak slope ~47deg at any belly
    for i in range(1, 17):
        t = i / 16
        p.append((z + dz * t, rb - dr * (1 - math.cos(math.pi * t)) / 2))
    p.append((z + dz + couple, mc.SOCKET_MOUTH_R))    # tapered female socket: neck -> mouth
    top = z + dz + couple
    return p, top


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--belly", type=float, default=100.0, help="bowl belly dia mm")
    ap.add_argument("--floor", type=float, default=76.0, help="flat floor dia mm")
    ap.add_argument("--points", type=int, default=120, help="points per ring")
    ap.add_argument("--out", default="catch_cup.stl")
    a = ap.parse_args()

    prof, top = profile(a.belly, a.floor, mc.COUPLE_L)
    tris = mc.disc_tris(0.0, a.floor / 2, a.points)               # closed floor
    tris += mc.grid_tris(mc.rev_rings(prof, a.points), a.points)  # wall
    mc.write_stl(a.out, tris)
    v = mc.verify_stl(a.out)
    mc.report(a.out, v, note=f"terminus bowl Ø{a.belly:g}, closed floor, height {top:.1f} mm")


if __name__ == "__main__":
    main()
