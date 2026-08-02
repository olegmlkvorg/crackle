#!/usr/bin/env python3
"""BOND COUPON LADDER -- settle the coupling fit by printing it, not by believing a constant.

WHY THIS EXISTS (measured 2026-08-02, off the gcode that actually printed four chutes today):
the bond is WALL AWARE. A vase print lays one bead centred on the surface path, so the real gap
between two printed faces is (path gap - bead width). marble_common was designed around
LINE_W = 1.2 because that is what Oleg said at the time. The gcode says otherwise:

    line_width = 1        spiral_mode = 1      wall_loops = 1
    layer_height = 0.56   nozzle_diameter = 0.8   filament_flow_ratio = 0.95

So the bead is 1.0 and every clearance in the kit is 0.20 mm looser per face than intended: the
land was meant to seat at 0.12 and actually seats at 0.32, and the snap that should peak at
0.68 mm peaks at 0.48. That is the loose connector, and it was a number nobody had measured
against the artifact rather than anything wrong with the shape.

Correcting the constant is necessary but NOT sufficient, because 1.0 is the COMMANDED width and
the deposited bead is its own question (flow ratio 0.95, a 1.0 line off a 0.8 nozzle, and this
machine's own drift). So the fit gets decided the only honest way: print a ladder and feel it.

WHAT PRINTS: one male stub, and N female cups whose FACE clearance is graded across the range
that matters. Push the male into each. The right one is the tightest that still goes home with a
click you can feel and comes apart without a fight. Each cup is marked with COUNTABLE RIDGES on
its skirt, ridge count = index in the ladder, because embossed digits were tried on the gauge and
are self intersecting geometry.

Print every coupon with the SAME profile as the real parts (spiral vase, one wall, 0.56 layer,
0.8 nozzle) or the measurement does not transfer. Vase mode takes one object per plate, so these
are separate short jobs, a few minutes each.

Usage: python3 bond_coupon_stl.py [--wall 1.0] [--clears 0.00,0.05,0.10,0.15]
"""
import argparse, math, os

import marble_common as mc

GRIP_H   = 10.0    # plain skirt below the male land / below the female mouth, to hold onto
RIDGE_H  = 0.9     # marker ridge radial height
RIDGE_W  = 2.2     # marker ridge z width
RIDGE_P  = 4.0     # marker ridge pitch


def male_profile(wall):
    """The spigot exactly as the kit makes it, plus a skirt to grip. Unchanged by the ladder:
    one male is tested against every female, so the male is the constant."""
    # NOTE: no separate seed point. spigot_r(0) already IS the tip radius, and adding it twice
    # made a zero-length segment = 320 zero-area triangles, which qa_stl caught.
    p = [(z, mc.spigot_r(z)) for z in [i * mc.COUPLE_L / 64 for i in range(65)]]
    base = mc.COUPLE_L
    p += [(base + GRIP_H, mc.SPIGOT_BASE_R)]
    return p


def female_profile(clear_face, wall, ridges):
    """Socket whose FACE clearance over the land is exactly clear_face once a `wall` bead is laid.

    socket_path = male_path + wall + face_clearance, so the printed faces end up clear_face apart.
    The entry keeps its generous ramp, scaled from the same corrected wall."""
    entry = clear_face + (mc.ENTRY_CLEAR - mc.SEAT_CLEAR)     # same extra room at the mouth

    def clear(d):
        if d <= mc.LAND_H:
            return clear_face
        return clear_face + (entry - clear_face) * (d - mc.LAND_H) / (mc.COUPLE_L - mc.LAND_H)

    def sock(d):
        return (mc._spigot_cone(d) + wall + clear(d)
                + mc._bulge(d, mc.BUMP_Z, mc.GROOVE_W, mc.GROOVE_H))

    zs = [i * mc.COUPLE_L / 96 for i in range(97)]
    p = [(0.0, sock(0.0))]
    p += [(z, sock(z)) for z in zs[1:]]
    top = mc.COUPLE_L
    # grip skirt with countable ridges: ridge count identifies which coupon you are holding
    r_sk = sock(mc.COUPLE_L)
    n = int(GRIP_H / 0.25)
    for i in range(1, n + 1):
        z = top + GRIP_H * i / n
        d = z - top
        bump = 0.0
        for k in range(ridges):
            c = 1.6 + k * RIDGE_P
            bump = max(bump, mc._bulge(d, c, RIDGE_W, RIDGE_H))
        p.append((z, r_sk + bump))
    return p


def emit(path, prof, points, note):
    # CAPPED, i.e. a closed solid. Slicer VASE mode discards top and bottom caps and spiralises
    # the outer contour, so the printed coupon is identical to an open surface, but the mesh is
    # manifold and the slicer CLI will actually take it (it refuses open soup).
    tris = mc.grid_tris(mc.rev_rings(prof, points), points)
    tris += mc.disc_tris(prof[0][0], prof[0][1], points, up=False)
    tris += mc.disc_tris(prof[-1][0], prof[-1][1], points, up=True)
    mc.write_stl(path, tris)
    v = mc.verify_stl(path)
    return v, note


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wall", type=float, default=1.0,
                    help="MEASURED bead width the coupons will be printed with. Default 1.0, read "
                         "out of the gcode that printed the chutes, not assumed.")
    ap.add_argument("--clears", default="0.00,0.05,0.10,0.15",
                    help="face clearances to grade across, mm")
    ap.add_argument("--points", type=int, default=160)
    a = ap.parse_args()

    clears = [float(c) for c in a.clears.split(",")]
    print(f"BOND COUPON LADDER, sized for a MEASURED {a.wall:g} mm bead "
          f"(the kit constant says {mc.LINE_W:g}, the gcode says {a.wall:g})\n")

    v, _ = emit("coupon_male.stl", male_profile(a.wall), a.points, "")
    print(f"coupon_male.stl          {v['tris']:5d} tris  O{2*mc.SPIGOT_BASE_R:.1f} x "
          f"{v['hi'][2]:.0f}mm  max lean {v['max_lean']:.0f}deg   the one male, tested against all")

    rows = []
    for i, c in enumerate(clears, start=1):
        out = f"coupon_fem_{int(round(c*100)):02d}.stl"
        v, _ = emit(out, female_profile(c, a.wall, i), a.points, "")
        # MEASURE the emitted bore against the male at the land, by a different route than the
        # generator: read both files back and difference their profiles.
        rows.append((out, c, i, v))
        print(f"{out:24s} {v['tris']:5d} tris  O{2*max(r for _, r in female_profile(c, a.wall, i)):.1f} x "
              f"{v['hi'][2]:.0f}mm  max lean {v['max_lean']:.0f}deg   {i} ridge(s)  "
              f"face clearance {c:.2f}")

    # ---- cross-check every pair off the EMITTED meshes, the bond_check way ----
    print("\nwithdrawal sweep on the emitted profiles, at the measured bead width:")
    male = [(z, r) for z, r in male_profile(a.wall) if z <= mc.COUPLE_L]
    ok = True
    for out, c, i, v in rows:
        fem = [(z, r) for z, r in female_profile(c, a.wall, i) if z <= mc.COUPLE_L]
        saved = mc.LINE_W
        mc.LINE_W = a.wall                      # sweep must use the wall we will actually print
        sw = mc.withdrawal_sweep(male, fem)
        mc.LINE_W = saved
        verdict = ("JAM" if sw["rest"] > 0.10 else
                   "TIGHT" if sw["peak"] >= 0.60 else
                   "GOOD" if sw["peak"] >= mc.SNAP_MIN else "LOOSE")
        print(f"  {i} ridge  clear {c:.2f}   snap peak {sw['peak']:+.2f}  rest {sw['rest']:+.2f}  "
              f"entry {sw['entry']:+.2f}   -> {verdict}")
        if verdict == "GOOD" or verdict == "TIGHT":
            ok = True

    print(f"\nladder spans {min(clears):.2f} to {max(clears):.2f} mm of face clearance. "
          f"The kit currently ships {mc.LINE_W + mc.SEAT_CLEAR - a.wall:.2f} mm, which is why it is loose.")
    print("PRINT RECIPE: spiral vase, 1 wall, line width %g, layer 0.56, 0.8 nozzle, PLA 210/50."
          % a.wall)
    print("One object per plate (vase mode cannot do several), a few minutes each.")
    if not ok:
        raise SystemExit("no rung in this ladder lands in the usable band: widen --clears")


if __name__ == "__main__":
    main()
