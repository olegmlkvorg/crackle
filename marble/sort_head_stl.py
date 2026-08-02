#!/usr/bin/env python3
"""SORT HEAD STL -- the piece that makes the sorting chute actually sort.

MEASURED 2026-08-02: the chute's rail crest does separate marbles by size, but only for a marble
arriving on the axis, and the aim has to be good to about a millimetre. 2mm off centre and the
marble clips the crest and rides the spiral instead. stand/funnel_stl.py has a O55 spout, so it
scatters marbles across the whole opening and sorts nothing.

So the crest is the wrong place to do the sorting. A GUIDE TUBE sized BETWEEN the two marble sizes
is its own sieve, and it does the job where you can see it:
  the small marble ENTERS the tube, and the tube delivers it dead centre by construction,
  the large marble CANNOT enter, and stays in the catch bowl for you to pick out.
The aim problem disappears because the tube is the aim.

Bottom-up: BOND v2.1 male spigot, cone in to the guide tube, the tube itself, then a wide catch
bowl flaring out to the mouth. Single-valued r(z) and z-monotonic, so slicer VASE mode prints it
as one wall. Narrowing upward is always self-supporting; only the bowl flare is overhang-limited,
and it is held under the vase ceiling.

Usage: python3 sort_head_stl.py [--hold 16] [--drop 12] [--mouth 100]
"""
import argparse, math, os

import marble_common as mc

AIM_TOL = 1.0     # MEASURED: 2mm off centre loses the sort, so the tube may not let the marble
                  # wander more than about this from the axis. Tube ID = drop + 2*AIM_TOL.
TUBE_L_MIN = 2.0  # tube length as a multiple of the marble dia: shorter and it is a hole, not a
                  # guide, and a hole does not aim.
BOWL_LEAN = 50.0  # deg from vertical for the catch bowl flare, under the 55 vase ceiling


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hold", type=float, default=16.0, help="marble that must NOT pass, mm")
    ap.add_argument("--drop", type=float, default=12.0, help="marble that must pass, mm")
    ap.add_argument("--mouth", type=float, default=100.0, help="catch bowl mouth dia mm")
    ap.add_argument("--points", type=int, default=144)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    tube_d = a.drop + 2 * AIM_TOL + mc.HOLE_SHRINK        # model bigger: it prints smaller
    printed = tube_d - mc.HOLE_SHRINK
    assert printed > a.drop + 0.3, (
        f"tube prints O{printed:.2f}, only {printed - a.drop:.2f}mm over the O{a.drop:g} marble: "
        f"it would jam rather than pass")
    assert printed < a.hold - 0.5, (
        f"tube prints O{printed:.2f} but the O{a.hold:g} marble must NOT enter it "
        f"(needs {a.hold - printed:.2f}mm of block, want >= 0.5). Pick sizes further apart: with "
        f"AIM_TOL {AIM_TOL:g} the gap must exceed {2*AIM_TOL + mc.HOLE_SHRINK + 0.5:.2f}mm")

    tr = tube_d / 2
    tube_l = TUBE_L_MIN * a.drop
    rb = a.mouth / 2
    h_in = mc.cone_h(mc.SPIGOT_BASE_R, tr)                # spigot base up to the tube: narrows, safe
    flare = math.tan(math.radians(BOWL_LEAN))
    h_bowl = (rb - tr) / flare

    z = 0.0
    prof = mc.spigot_profile()                            # male end, tip at z=0
    z = mc.COUPLE_L
    prof += [(z + h_in, tr)]                              # cone in to the guide tube
    z += h_in
    prof += [(z + tube_l, tr)]                            # THE GUIDE TUBE: this is the sieve
    z += tube_l
    prof += [(z + h_bowl, rb)]                            # catch bowl out to the mouth
    z += h_bowl
    out = a.out or f"sort_head_{a.hold:g}_{a.drop:g}.stl"

    tris = mc.grid_tris(mc.rev_rings(prof, a.points), a.points)
    mc.write_stl(out, tris)
    v = mc.verify_stl(out)

    # measure the tube off the emitted mesh, not off the variable that made it
    import struct
    with open(out, "rb") as f:
        f.read(84)
        rmin = 1e9
        for _ in range(v["tris"]):
            f.read(12)
            for _ in range(3):
                x, y, zz = struct.unpack("<3f", f.read(12))
                rmin = min(rmin, math.hypot(x, y))
            f.read(2)
    meas_tube = 2 * rmin

    print(f"{out}: {v['tris']} tris | O{a.mouth:g} mouth, guide tube O{tube_d:.2f} modelled "
          f"(prints ~O{printed:.2f}) x {tube_l:.0f}mm, total height {v['hi'][2]:.0f}mm")
    print(f"  O{a.drop:g} ENTERS the tube and is delivered on the axis; O{a.hold:g} cannot enter "
          f"and stays in the bowl")
    checks = [
        ("tube measured", abs(meas_tube - tube_d) < 0.05,
         f"emitted narrowest O{meas_tube:.2f} vs modelled O{tube_d:.2f}"),
        ("passes the small one", printed - a.drop >= 2 * AIM_TOL - 0.05,
         f"{(printed - a.drop)/2:.2f}mm per side, which IS the aim it delivers "
         f"(measured tolerance ~{AIM_TOL:g}mm)"),
        ("blocks the big one", a.hold - printed >= 0.5,
         f"O{a.hold:g} marble is {a.hold - printed:.2f}mm too fat to enter"),
        ("tube guides, not just holes", tube_l >= TUBE_L_MIN * a.drop - 1e-6,
         f"{tube_l:.0f}mm of tube for a O{a.drop:g} marble = {tube_l/a.drop:.1f} diameters"),
        ("vase printable", v["max_lean"] <= 55.0, f"max wall lean {v['max_lean']:.0f} deg"),
        ("bed fit", a.mouth <= 340, f"O{a.mouth:g} mouth vs 340 bed"),
    ]
    ok = True
    for name, good, msg in checks:
        print("  %s %-24s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    if not ok:
        os.replace(out, out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined")
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS  (vase mode, prints spigot-down as modelled, no support)")


if __name__ == "__main__":
    main()
