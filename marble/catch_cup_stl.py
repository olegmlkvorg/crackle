#!/usr/bin/env python3
"""CATCH CUP STL: the end of the run, a belly bowl that collects the marbles.

Bottom-up: flat floor disc (prints as the solid vase bottom), 45 deg flare to a O100 belly, a
cosine shoulder curving back in over the marbles so bounces stay inside, then the standard BOND
v2.1 female socket to receive the last part's spigot. Terminus: no spigot. Single-valued r(z)
plus a flat floor, which is exactly what slicer VASE mode prints.

TWO COUPLING STANDARDS (--slim). Stock socket is mouth O58.90 over a O52 spigot; slim is mouth
O50.60 over a O43.7 spigot, the size the spiral chute derives from its own emitted pocket. They
do not mate, so a tower is all one or all the other, and until today a slim tower had no
terminus at all. The BELLY does not shrink with the coupling: it is sized by the marbles it
collects, not by how fat the neck is.

THE SHOULDER IS THE PART THAT CARES. It runs from the belly radius in to the socket-bottom
radius, so a smaller neck means a LONGER inward run, and the constant that shaped it (peak slope
1.08, about 47 deg) was tuned at the stock neck. That slope is nominally diameter-independent
because the shoulder height is scaled by the same drop it has to cover, but "nominally" is how
LINE_W stayed wrong for months: the emitted lean is MEASURED off the mesh here, per part, and it
is a gate, not a note. --shoulder is the knob if it ever runs out of budget.

Usage: python3 catch_cup_stl.py [--belly 100] [--floor 76] [--slim | --tip D] [--marble 16]
                                [--shoulder 1.08] [--points 120] [--out catch_cup.stl]
"""
import argparse, math, os

import marble_common as mc
# The marble gate and the slim-standard derivation live with the drop tube, the part that IS a
# free marble path. One copy, imported, so the two can never drift apart.
from drop_tube_stl import (marble_gate, slim_bond, read_rings, stl_verts, SLIM_REF_STL,
                           bond_polylines, bond_acceptance)

PACK = 0.60      # random loose sphere packing fraction. ASSUMED, handbook 0.55-0.64; nobody has
                 # poured marbles into a printed cup and counted. Capacity is REPORTED, not gated.


def profile(belly, floor, couple, shoulder=1.08):
    """Returns (polyline, top_z, shoulder_z0, shoulder_z1). shoulder = peak |dr/dz| of the
    incurving shoulder; the shoulder height is derived from it so the slope is the same whatever
    neck the coupling asks for."""
    rb, rf, rn = belly / 2, floor / 2, mc.SOCKET_BOT_R   # neck = socket bottom radius
    h_flare = mc.cone_h(rf, rb)                       # 45 deg flare from floor edge to belly
    p = [(0.0, rf), (h_flare, rb)]                    # floor edge -> belly
    z = h_flare + 12.0
    p.append((z, rb))                                 # straight belly band
    dr = rb - rn                                      # cosine shoulder in to the neck;
    dz = dr * math.pi / 2 / shoulder                  # height set so the peak slope IS `shoulder`
    for i in range(1, 17):
        t = i / 16
        p.append((z + dz * t, rb - dr * (1 - math.cos(math.pi * t)) / 2))
    p += mc.socket_profile(z + dz)[1:]                # BOND v2.1 female socket: neck -> mouth
    #                                    ([1:]: the shoulder already ends on the socket-bottom ring)
    return p, z + dz + couple, z, z + dz


def floor_seal(path, points):
    """Does the floor disc actually close the bottom of the wall? Measured off the emitted mesh:
    every edge lying in the z=0 plane must be shared by exactly two triangles. A floor disc whose
    rim radius disagrees with the wall's base ring leaves 2*points unpaired edges."""
    vs = list(stl_verts(path))
    edges = {}
    for i in range(0, len(vs), 3):
        t = [tuple(round(c, 4) for c in vs[i + k]) for k in range(3)]
        for k in range(3):
            a, b = t[k], t[(k + 1) % 3]
            if abs(a[2]) < 1e-6 and abs(b[2]) < 1e-6:
                e = (a, b) if a <= b else (b, a)
                edges[e] = edges.get(e, 0) + 1
    return sum(1 for c in edges.values() if c != 2), len(edges)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--belly", type=float, default=100.0, help="bowl belly dia mm")
    ap.add_argument("--floor", type=float, default=76.0, help="flat floor dia mm")
    ap.add_argument("--slim", action="store_true",
                    help="build the SLIM coupling standard (mouth O50.60 over a O43.7 spigot), the "
                         "one the spiral chute derives from its emitted pocket. Not an upgrade: "
                         "slim and stock do not mate.")
    ap.add_argument("--tip", type=float, default=None,
                    help="pin the mating spigot tip dia instead of stock/slim. This is what makes "
                         "the marble gate a real gate: ask for a coupling too narrow for the "
                         "marble and watch it fail.")
    ap.add_argument("--marble", type=float, default=mc.MARBLE_D,
                    help="marble dia this cup must swallow and hold, mm")
    ap.add_argument("--shoulder", type=float, default=1.08,
                    help="peak |dr/dz| of the incurving shoulder (1.08 = 47 deg from vertical). "
                         "The knob to reach for if the measured lean runs out of budget.")
    ap.add_argument("--points", type=int, default=120, help="points per ring")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.slim and a.tip is not None:
        raise SystemExit("--slim and --tip both set the coupling: pick one")
    bond_note, ref_check = "", None
    if a.slim:
        tip, ref, ref_ok = slim_bond()
        if ref != ref:                                  # NaN: no reference mesh to measure
            msg = ("cannot verify: %s not found, so the slim standard is unproven "
                   "(generate the slim chute first)" % SLIM_REF_STL)
        else:
            msg = ("derived tip O%.4f from the chute wave vs O%.4f measured off %s tip ring"
                   % (tip, ref, SLIM_REF_STL))
        ref_check = ("slim matches the chute", ref_ok, msg)
        bond_note = ("; SLIM socket O%.1f mouth over a O%.1f spigot (stock is O58.9 over O52 and "
                     "does NOT mate with it)" % (mc.SOCKET_MOUTH_D, mc.SPIGOT_TIP_D))
    elif a.tip is not None:
        mc.configure_bond(a.tip)
        bond_note = "; coupling PINNED to a O%g spigot (--tip)" % a.tip
    out = a.out or ("catch_cup_slim.stl" if a.slim else "catch_cup.stl")

    prof, top, z_sh0, z_sh1 = profile(a.belly, a.floor, mc.COUPLE_L, a.shoulder)
    tris = mc.disc_tris(0.0, a.floor / 2, a.points)               # closed floor
    tris += mc.grid_tris(mc.rev_rings(prof, a.points), a.points)  # wall
    mc.write_stl(out, tris)
    v = mc.verify_stl(out)

    # ---- self-verify: re-read the file and MEASURE what was claimed ----
    rings = read_rings(out)
    zs = sorted(rings)
    wall_zs = [z for z in zs if z > 1e-6]                     # z=0 holds the floor fan too
    r_of = {z: sum(rings[z]) / len(rings[z]) for z in wall_zs}
    round_err = max(max(rings[z]) - min(rings[z]) for z in wall_zs)
    height = zs[-1]
    mouth_d = 2 * r_of[zs[-1]]
    belly_d = 2 * max(r_of.values())
    # the neck is the narrowest ring above the belly band: socket bottom, measured not assumed
    neck_z = min((z for z in wall_zs if z >= z_sh0), key=lambda z: r_of[z])
    neck_d = 2 * r_of[neck_z]
    # the coupling THROAT is the mating spigot's tip, recovered from the measured socket bottom:
    # socket_r(0) = tip_r + LINE_W + SEAT_CLEAR (the groove bulge is zero at d=0)
    throat_d = neck_d - 2 * (mc.LINE_W + mc.SEAT_CLEAR)
    # lean measured off the emitted rings, and again isolated to the shoulder run
    def lean_over(band):
        pairs = [(za, zb) for za, zb in zip(band, band[1:]) if zb - za > 1e-9]
        return max(math.degrees(math.atan(abs(r_of[zb] - r_of[za]) / (zb - za)))
                   for za, zb in pairs) if pairs else 0.0
    sh_lean = lean_over([z for z in wall_zs if z_sh0 - 1e-6 <= z <= z_sh1 + 1e-6])
    # capacity: volume of revolution of the FREE bore (inner face = path minus half a bead) from
    # the floor up to where the shoulder starts closing in, integrated over the emitted rings
    below = [z for z in wall_zs if z <= z_sh0]
    vol = 0.0
    prev_z, prev_r = 0.0, a.floor / 2 - mc.LINE_W / 2
    for z in below:
        r = max(0.0, r_of[z] - mc.LINE_W / 2)
        vol += math.pi / 3 * (z - prev_z) * (prev_r**2 + prev_r * r + r**2)   # conical frustum
        prev_z, prev_r = z, r
    n_marbles = vol * PACK / (math.pi / 6 * a.marble**3)
    unpaired, n_edges = floor_seal(out, a.points)
    throat_ok, throat_msg = marble_gate(throat_d, a.marble, "coupling (from measured socket bottom)")
    neck_ok, neck_msg = marble_gate(neck_d, a.marble, "neck")
    # a terminus has no spigot of its own, so the male half is the kit standard's designed
    # profile; the female half is measured off this mesh. Weaker than measured x measured
    # (bond_check.py's pairing) but it is the only male a cup will ever see.
    snap_ok, snap_msg = bond_acceptance(mc.spigot_profile(), bond_polylines(out)[1],
                                        "kit-standard spigot into this socket, measured")

    mc.report(out, v, note=(
        "terminus bowl O%.1f measured, closed floor O%g, height %.1f mm, neck O%.2f; holds about "
        "%.0f O%g marbles (%.0f cm3 of free belly at %.2f packing, REPORTED not gated: nobody has "
        "poured marbles into a printed cup and counted)"
        % (belly_d, a.floor, height, neck_d, n_marbles, a.marble, vol / 1000, PACK) + bond_note))

    checks = [
        ("rings are round", round_err < 1e-3,
         "worst ring radius spread %.2e mm above the floor (surface of revolution)" % round_err),
        ("height as asked", abs(height - top) < 1e-3,
         "measured %.3f mm vs designed %.3f" % (height, top)),
        ("floor is sealed", unpaired == 0,
         "%d unpaired edges in the z=0 plane of %d (the disc rim must meet the wall's base ring); "
         "%d flat floor tris on the bed" % (unpaired, n_edges, v["flat"])),
        ("coupling passes the marble", throat_ok, throat_msg),
        ("neck passes the marble", neck_ok, neck_msg),
        ("holds what it swallows", belly_d / 2 - neck_d / 2 >= a.marble,
         "belly O%.1f over neck O%.2f = %.1f mm of shelf per side vs the %g mm a marble needs to "
         "sit clear of the neck shadow and stay put" % (belly_d, neck_d,
                                                        (belly_d - neck_d) / 2, a.marble)),
        ("socket is kit standard", abs(mouth_d - mc.SOCKET_MOUTH_D) < 0.02,
         "measured mouth O%.3f vs BOND v2.1 O%.3f" % (mouth_d, mc.SOCKET_MOUTH_D)),
        ("bond snaps", snap_ok, snap_msg),
        ("wall lean <= 55", v["max_lean"] <= 55.0,
         "MEASURED off the mesh: %.1f deg from vertical overall, %.1f deg on the shoulder run "
         "(z %.1f..%.1f, neck O%.2f), %.1f deg of budget left. Knobs: --shoulder for the incurve, "
         "marble_common.CONE_SLOPE for the 45 deg flare"
         % (v["max_lean"], sh_lean, z_sh0, z_sh1, neck_d, mc.lean_budget(v["max_lean"]))),
        ("bed fit", max(v["hi"][0] - v["lo"][0], v["hi"][1] - v["lo"][1]) <= 340,
         "widest bbox extent %.1f mm vs 340 bed"
         % max(v["hi"][0] - v["lo"][0], v["hi"][1] - v["lo"][1])),
    ]
    if ref_check is not None:
        checks.insert(0, ref_check)
    ok = True
    for name, good, msg in checks:
        print("  %s %-26s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    if not ok:
        os.replace(out, out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined to %s.FAILED" % out)
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS")


if __name__ == "__main__":
    main()
