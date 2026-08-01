#!/usr/bin/env python3
"""DROP TUBE STL — the simplest marble-run link: a straight vertical fall.

Bottom-up: tapered male spigot -> cone in to the Ø24 marble bore -> straight bore -> cone out
to the tapered female socket at the top. Marbles fall from the part above straight through.
Ends use the shared kit standard (marble_common: tapered nest, female path +1.6mm over male so the
single walls clear). Open surface, single-valued r(z): slice VASE mode (one continuous wall, Z-monotonic).

Usage: python3 drop_tube_stl.py [--length 120] [--bore 24] [--points 120] [--out drop_tube.stl]
"""
import argparse

import marble_common as mc


def profile(length, bore, couple):
    rb = bore / 2
    h_lo = mc.cone_h(mc.SPIGOT_BASE_R, rb)              # spigot base -> bore
    h_hi = mc.cone_h(mc.SOCKET_BOT_R, rb)               # bore -> socket bottom
    straight = length - couple * 2 - h_lo - h_hi
    assert straight >= 5, f"--length too short: needs >= {couple*2 + h_lo + h_hi + 5:.0f} mm"
    p = mc.spigot_profile()                             # tapered male: (0,tip) -> (couple,base)
    p += [(couple + h_lo, rb)]                          # cone in to the bore
    p += [(length - couple - h_hi, rb)]                 # straight marble bore
    p += mc.socket_profile(length - couple)             # cone out + tapered female socket to the mouth
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--length", type=float, default=120.0, help="total part height mm")
    ap.add_argument("--bore", type=float, default=mc.BORE_D, help="marble path dia mm (marble Ø16)")
    ap.add_argument("--points", type=int, default=120, help="points per ring")
    ap.add_argument("--out", default="drop_tube.stl")
    a = ap.parse_args()

    prof = profile(a.length, a.bore, mc.COUPLE_L)
    tris = mc.grid_tris(mc.rev_rings(prof, a.points), a.points)
    mc.write_stl(a.out, tris)
    v = mc.verify_stl(a.out)
    mc.report(a.out, v, note=f"straight fall, bore Ø{a.bore:g} for Ø{mc.MARBLE_D:g} marbles")


if __name__ == "__main__":
    main()
