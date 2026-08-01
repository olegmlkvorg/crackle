#!/usr/bin/env python3
"""DROP TUBE STL — the simplest marble-run link: a straight vertical fall.

Bottom-up: Ø55 male spigot -> cone in to the Ø24 marble bore -> straight bore -> cone out
to the Ø56 female socket at the top. Marbles fall from the part above straight through.
Open surface, single-valued r(z): slice in VASE mode (one continuous wall, Z-monotonic).

Usage: python3 drop_tube_stl.py [--length 120] [--bore 24] [--points 120] [--out drop_tube.stl]
"""
import argparse

import marble_common as mc


def profile(length, bore, socket_d, spigot_d, couple):
    rs, rg, rb = socket_d / 2, spigot_d / 2, bore / 2
    h_lo, h_hi = mc.cone_h(rg, rb), mc.cone_h(rs, rb)
    straight = length - couple * 2 - h_lo - h_hi
    assert straight >= 5, f"--length too short: needs >= {couple*2 + h_lo + h_hi + 5:.0f} mm"
    p = [(0.0, rg), (couple, rg)]                       # spigot (male, bottom)
    p += [(couple + h_lo, rb)]                          # cone in to the bore
    p += [(couple + h_lo + straight, rb)]               # straight marble bore
    p += [(length - couple, rs), (length, rs)]          # cone out + socket (female, top)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--length", type=float, default=120.0, help="total part height mm")
    ap.add_argument("--bore", type=float, default=mc.BORE_D, help="marble path dia mm (marble Ø16)")
    ap.add_argument("--socket", type=float, default=mc.SOCKET_D, help="female socket dia (top)")
    ap.add_argument("--spigot", type=float, default=mc.SPIGOT_D, help="male spigot dia (bottom)")
    ap.add_argument("--points", type=int, default=120, help="points per ring")
    ap.add_argument("--out", default="drop_tube.stl")
    a = ap.parse_args()

    prof = profile(a.length, a.bore, a.socket, a.spigot, mc.COUPLE_L)
    tris = mc.grid_tris(mc.rev_rings(prof, a.points), a.points)
    mc.write_stl(a.out, tris)
    v = mc.verify_stl(a.out)
    mc.report(a.out, v, note=f"straight fall, bore Ø{a.bore:g} for Ø{mc.MARBLE_D:g} marbles")


if __name__ == "__main__":
    main()
