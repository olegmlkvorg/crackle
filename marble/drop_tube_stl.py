#!/usr/bin/env python3
"""DROP TUBE STL: the simplest marble-run link, a straight vertical fall.

Bottom-up: BOND v2.1 male spigot (land + snap bump) -> cone in to the O24 marble bore -> straight
bore -> cone out to the BOND v2.1 female socket (land + groove) at the top. Marbles fall from the
part above straight through. Open surface, single-valued r(z): slice VASE mode.

TWO COUPLING STANDARDS, and they do not mix. Stock is tip O52 / mouth O58.90. SLIM (--slim) is
tip O43.7 / mouth O50.60, the size the spiral chute derives from its own emitted pocket. A slim
spigot dropped into a stock socket has 5.22mm of gap per side and falls straight through, so a
tower is built entirely from one standard or the other. The BORE does not change with the
coupling: it is sized by the marble, not by how fat the ends are.

The slim tip is RECOMPUTED here from the chute's wave, not copied as a number, and then
cross-checked against the tip ring measured off the emitted spiral_chute_slim.stl. If the hero
part ever moves, this FAILS instead of quietly shipping a tube that will not mate.

This file also hosts the shared MARBLE GATE (marble_gate), the DYNAMIC BOND GATE (bond_acceptance)
and the slim-standard derivation, which catch_cup_stl.py imports: the drop tube is the part that IS
a free marble path and the only part carrying both bond ends, so the rules about what a coupling
must let through and what it must grip live with it, in exactly one copy.

Usage: python3 drop_tube_stl.py [--length 120] [--bore 24] [--slim | --tip D] [--marble 16]
                                [--points 120] [--out drop_tube.stl]
"""
import argparse, math, os, struct

import marble_common as mc
import spiral_chute_stl as sc

# The chute's argparse defaults, restated so the slim tip can be derived without running the
# chute's main(). They are a PREDICTION, not the truth: slim_bond() checks them against the tip
# ring measured off the emitted spiral_chute_slim.stl and fails on any disagreement.
CHUTE_RAIL_D, CHUTE_POCKET_D = 15.0, 44.0
CHUTE_FLOOR_FRAC, CHUTE_PITCH = 0.50, 32.0
SLIM_REF_STL = "spiral_chute_slim.stl"
SLIM_REF_TOL = 0.01      # mm; both routes are arithmetic on the same wave, so they must agree


def stl_verts(path):
    """Vertices straight off a binary STL. Reading the FILE back is the point: it is a different
    route to the geometry than the profile arithmetic that wrote it."""
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        body = f.read()
    for rec in struct.iter_unpack("<12fH", body):
        yield rec[3:6]
        yield rec[6:9]
        yield rec[9:12]


def read_rings(path):
    """{z: [radius, ...]} measured off the emitted mesh, one entry per modelled ring."""
    rings = {}
    for x, y, z in stl_verts(path):
        rings.setdefault(round(z, 5), []).append(math.hypot(x, y))
    return rings


def measured_tip_d(path):
    """Spigot tip diameter measured off a part's lowest ring. The land is cylindrical and the bump
    starts 1.5mm up, so the bottom ring IS the tip."""
    rings = read_rings(path)
    z0 = min(rings)
    rs = rings[z0]
    assert max(rs) - min(rs) < 1e-3, f"{path}: bottom ring z={z0} is not round"
    return 2 * sum(rs) / len(rs)


def slim_bond():
    """Adopt the SLIM coupling standard: exactly the tip the chute gives itself.

    The chute sizes its slim bond off its own EMITTED pocket, because the fillet pass pulls the
    wave in a couple of mm and the mesh is the truth:
        tip = pocket + 2 * LINE_W + 1.0   (marble_common.min_bond_tip_d: a wall each side plus a
                                           hair of daylight, so the pocket passes through the tip)
    Returns (tip_d, ref_tip_d, ref_ok). ref_* is the same number measured a second way, off the
    tip ring of the emitted spiral_chute_slim.stl; ref_ok False means the two disagree or the
    reference mesh is missing, and the caller must FAIL."""
    tab = sc.wave_table(CHUTE_RAIL_D / 2, CHUTE_POCKET_D / 2, CHUTE_FLOOR_FRAC, CHUTE_PITCH)
    tip = mc.min_bond_tip_d(2 * max(tab))
    mc.configure_bond(tip)
    if not os.path.exists(SLIM_REF_STL):
        return tip, float("nan"), False
    ref = measured_tip_d(SLIM_REF_STL)
    return tip, ref, abs(ref - tip) <= SLIM_REF_TOL


def marble_gate(throat_d, marble_d, source):
    """THE GATE THIS KIT WAS MISSING: fail a part whose COUPLING cannot pass the marble the part
    exists to carry. Slim shrank the bond 14 percent in one step and nothing anywhere related the
    bond diameter to the marble, so nothing would have stopped the next shrink.

    Every term is a constant from marble_common, and the half-bead bookkeeping is the same one
    that made every socket 0.25mm loose when LINE_W was wrong:
        the vase wall is laid CENTRED on the surface path, so the printed inner FACE sits half a
        bead inside it        -> free bore = path diameter - one whole LINE_W
        a printed hole comes out under the model (Creality vase empirics)
                              -> as printed, another HOLE_SHRINK off
        the marble is not perfectly round and neither is the print
                              -> it needs SORT_DRIFT of daylight per side

    Returns (ok, message). throat_d is the coupling's narrowest PATH diameter, which is the male
    spigot tip: the socket is always one wall and one clearance wider, so a marble that clears the
    tip clears the whole joint."""
    free = throat_d - mc.LINE_W - mc.HOLE_SHRINK
    need = marble_d + 2 * mc.SORT_DRIFT
    return (free >= need,
            "%s throat path O%.2f -> prints free O%.2f (less one %.2f bead, less %.2f hole shrink) "
            "vs O%g marble + 2 x %.2f drift = O%.2f needed; margin %+.2f mm"
            % (source, throat_d, free, mc.LINE_W, mc.HOLE_SHRINK, marble_d, mc.SORT_DRIFT,
               need, free - need))


def bond_polylines(path, couple=mc.COUPLE_L):
    """(male, female) bond polylines MEASURED off an emitted mesh: male tip at z=0, socket bottom
    at d=0. A terminus has no real male end and its caller ignores that half."""
    rings = read_rings(path)
    top = max(rings)
    mean = lambda z: sum(rings[z]) / len(rings[z])
    male = [(z, mean(z)) for z in sorted(z for z in rings if z <= couple + 1e-6)]
    fem = [(z - (top - couple), mean(z))
           for z in sorted(z for z in rings if z >= top - couple - 1e-6)]
    return male, fem


def bond_acceptance(male, fem, what):
    """DYNAMIC bond acceptance, the thing every static check here is blind to: diameters and the
    mouth are geometry, the SNAP is not. Nothing in a part's self-verify sees SEAT_CLEAR, BUMP_H,
    GROOVE_H, BUMP_Z or LAND_H, because socket_r(COUPLE_L) does not depend on any of them, so a
    part with zero pull-out force measured green (verified 2026-08-03: seat 0.45, bump 0, groove
    6mm off, land 2mm all emitted PASS). bond_check.py catches exactly that, but its MALES/FEMALES
    are hardcoded stock filenames and it answers a slim trio with "0 x 0 pairings, all checks
    green", so the slim parts had no dynamic gate at all. This is that gate, per part, at emit
    time, on the standard's own acceptance numbers."""
    sw = mc.withdrawal_sweep(male, fem)
    ok = (sw["peak"] >= mc.SNAP_MIN and sw["rest"] <= mc.REST_MAX
          and abs(sw["entry"] - mc.ENTRY_CLEAR) <= 0.10)
    return ok, ("%s: snap %+.3f mm at %.2f mm out (need >= %.2f), rest %+.3f (need <= %.2f), "
                "entry %.3f (need %.2f +-0.10)"
                % (what, sw["peak"], sw["peak_at"], mc.SNAP_MIN, sw["rest"], mc.REST_MAX,
                   sw["entry"], mc.ENTRY_CLEAR))


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
    ap.add_argument("--bore", type=float, default=mc.BORE_D, help="marble path dia mm (marble O16)")
    ap.add_argument("--slim", action="store_true",
                    help="build the SLIM coupling standard (tip O43.7 / mouth O50.60), the one the "
                         "spiral chute derives from its emitted pocket. Not an upgrade: slim and "
                         "stock do not mate, so a tower is all one or all the other.")
    ap.add_argument("--tip", type=float, default=None,
                    help="pin the spigot tip dia instead of stock/slim. This is what makes the "
                         "marble gate a real gate: ask for a coupling too narrow for the marble "
                         "and watch it fail.")
    ap.add_argument("--marble", type=float, default=mc.MARBLE_D,
                    help="marble dia this tube must pass, mm")
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
        bond_note = ("; SLIM coupling O%.1f tip / O%.1f mouth, grid %.1f (stock is O52 / O58.9 / "
                     "66.9 and does NOT mate with it)"
                     % (mc.SPIGOT_TIP_D, mc.SOCKET_MOUTH_D, mc.GRID_PITCH))
    elif a.tip is not None:
        mc.configure_bond(a.tip)
        bond_note = "; coupling PINNED to tip O%g (--tip)" % a.tip
    out = a.out or ("drop_tube_slim.stl" if a.slim else "drop_tube.stl")

    prof = profile(a.length, a.bore, mc.COUPLE_L)
    tris = mc.grid_tris(mc.rev_rings(prof, a.points), a.points)
    mc.write_stl(out, tris)
    v = mc.verify_stl(out)

    # ---- self-verify: re-read the file and MEASURE what was claimed ----
    rings = read_rings(out)
    zs = sorted(rings)
    round_err = max(max(rs) - min(rs) for rs in rings.values())
    r_of = {z: sum(rings[z]) / len(rings[z]) for z in zs}
    tip_d = 2 * r_of[zs[0]]
    mouth_d = 2 * r_of[zs[-1]]
    bore_path_d = 2 * min(r_of.values())                # narrowest ring anywhere in the part
    height = zs[-1] - zs[0]
    # the straight bore: consecutive rings within half a hole-shrink of the narrowest
    bore_zs = [z for z in zs if 2 * r_of[z] <= bore_path_d + 0.01]
    bore_len = max(bore_zs) - min(bore_zs)
    # a marble descends a surface of revolution through its narrowest ring, so the emitted
    # minimum radius IS the descent test; put it through the same printed-bore arithmetic
    bore_ok, bore_msg = marble_gate(bore_path_d, a.marble, "narrowest ring in the part")
    throat_ok, throat_msg = marble_gate(tip_d, a.marble, "coupling (measured spigot tip)")
    # this part has BOTH bond ends, so the pairing is real: a drop tube stacks on a drop tube
    snap_ok, snap_msg = bond_acceptance(*bond_polylines(out),
                                        "own spigot into own socket, both measured off the mesh")

    mc.report(out, v, note=(
        "straight fall %.0fmm, bore path O%.1f measured (%.0fmm of it straight) for O%g marbles"
        % (height, bore_path_d, bore_len, a.marble) + bond_note))

    checks = [
        ("rings are round", round_err < 1e-3,
         "worst ring radius spread %.2e mm (surface of revolution)" % round_err),
        ("height as asked", abs(height - a.length) < 1e-3,
         "measured %.3f mm vs --length %g" % (height, a.length)),
        ("coupling passes the marble", throat_ok, throat_msg),
        ("free path passes marble", bore_ok, bore_msg),
        ("spigot is kit standard", abs(tip_d - mc.SPIGOT_TIP_D) < 0.02,
         "measured tip O%.3f vs BOND v2.1 O%.3f" % (tip_d, mc.SPIGOT_TIP_D)),
        ("socket is kit standard", abs(mouth_d - mc.SOCKET_MOUTH_D) < 0.02,
         "measured mouth O%.3f vs BOND v2.1 O%.3f" % (mouth_d, mc.SOCKET_MOUTH_D)),
        ("bond snaps", snap_ok, snap_msg),
        ("wall lean <= 55", v["max_lean"] <= 55.0,
         "measured %.1f deg from vertical, %.1f deg of budget left (the steep face is a transition "
         "cone: marble_common.CONE_SLOPE is the knob, --length only moves where it sits)"
         % (v["max_lean"], mc.lean_budget(v["max_lean"]))),
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
