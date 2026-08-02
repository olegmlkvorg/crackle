#!/usr/bin/env python3
"""SPIRAL CHUTE STL — the hero of the marble-run kit: marbles orbit down a helical gutter.

How it works (single wall, marble INSIDE — the couplings force the path inside):
the wall is a helical pocket wave, r(θ,z) between a RAIL crest (Ø15 — smaller than a Ø16
marble, so the centre channel refuses it: the marble is CAPTIVE) and a POCKET (Ø44). The
up-facing helical flank carries the marble like a wall-of-death: its inward push is the
centripetal force. Too slow -> the marble slips over the rail and drops ONE turn (the next
flank catches it); too fast -> it climbs the flank outward-UPWARD and brushes the pocket
ceiling — both self-correcting. Descent = one pitch per lap, a rolling grade (~19°), not
free-fall. The helix IS the vase spiral: single-valued r(θ,z), Z-monotonic.

Coupling: the kit BOND v2 (marble_common) — tapered female socket + groove (top), tapered
male spigot + snap bump (bottom); the wave blends into plain cones at each end (entry hands
the marble to the first full turn; exit lets the last turn pour into the spigot).

Usage: python3 spiral_chute_stl.py [--turns 4] [--pitch 28] [--rail 15] [--pocket 44]
                                   [--floor-frac 0.54] [--points 144] [--out spiral_chute.stl]
"""
import argparse, math, os

import marble_common as mc


def _sawtooth(rail_r, pocket_r, floor_frac, pitch, fillet, samples):
    """Linear flanks, corners C1-rounded by parabolas over +-fillet mm.
    A parabola blend's peak slope equals the flank slope, so rounding never
    steepens the wall (moving-average smoothing + rescale DID — measured 55deg)."""
    fp = floor_frac * pitch
    m1 = (pocket_r - rail_r) / fp                  # floor flank (up-facing)
    m2 = (pocket_r - rail_r) / (pitch - fp)        # ceiling flank (down-facing)

    def corner(s, sc, r_c, a, b, h):               # parabola joining slopes a->b at sc
        d = s - sc
        return r_c - (a - b) * h / 4 + (a + b) / 2 * d + (b - a) / (4 * h) * d * d

    tab = []
    for i in range(samples):
        s = i / samples * pitch
        if s <= fillet:                       tab.append(corner(s, 0, rail_r, -m2, m1, fillet))
        elif s < fp - fillet:                 tab.append(rail_r + m1 * s)
        elif s <= fp + fillet:                tab.append(corner(s, fp, pocket_r, m1, -m2, fillet))
        elif s < pitch - fillet:              tab.append(pocket_r - m2 * (s - fp))
        else:                                 tab.append(corner(s, pitch, rail_r, -m2, m1, fillet))
    return tab


def wave_table(rail_r, pocket_r, floor_frac, pitch, fillet=3.0, samples=720):
    """One pitch of the pocket wave r(u), u in [0,1): crest at u=0, pocket max at
    u=floor_frac. Only the CREST gauge is load-bearing (it keeps the marble captive),
    so fix it by pure translation — translation preserves flank slopes, where forcing
    the pocket exact as well measurably steepened the wall past 55°. One extra pass
    widens the pocket input to make up (most of) the fillet loss."""
    tab = _sawtooth(rail_r, pocket_r, floor_frac, pitch, fillet, samples)
    tab = _sawtooth(rail_r, pocket_r + (pocket_r - max(tab)), floor_frac, pitch,
                    fillet, samples)
    return [t - (min(tab) - rail_r) for t in tab]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--turns", type=int, default=4, help="full gutter turns")
    ap.add_argument("--pitch", type=float, default=32.0,
                    help="helix pitch mm/turn (>=30 so a Ø16 marble fits the gutter mouth)")
    ap.add_argument("--rail", type=float, default=None,
                    help="rail crest dia mm (default 15) — MUST be < marble Ø16 to keep it "
                         "captive. In sort mode, overrides the derived crest and gets checked.")
    ap.add_argument("--pocket", type=float, default=44.0, help="pocket (outer wave) dia mm")
    ap.add_argument("--floor-frac", type=float, default=0.50,
                    help="fraction of pitch used by the up-facing floor flank")
    ap.add_argument("--points", type=int, default=144, help="points per ring")
    ap.add_argument("--zstep", type=float, default=0.5, help="ring spacing mm in the wave zone")
    ap.add_argument("--hold", type=float, default=None,
                    help="SORT MODE: marble dia mm that must RIDE the spiral (with --drop)")
    ap.add_argument("--drop", type=float, default=None,
                    help="SORT MODE: marble dia mm that must FALL through the central shaft")
    ap.add_argument("--slim", action="store_true",
                    help="shrink the coupling to the smallest the gutter allows. O52/56 was "
                         "inherited from the funnel spout; a spigot only has to clear the pocket.")
    ap.add_argument("--lean", type=float, default=0.0,
                    help="tilt the helix axis off vertical, deg. Bond ends stay vertical and "
                         "circular, so the segment still couples; the stack steps sideways.")
    ap.add_argument("--out", default="spiral_chute.stl")
    a = ap.parse_args()

    # SORT MODE. The chute has always been a sieve and nobody had named it: the wall is
    # single-valued r(theta,z), so the minimum radius over theta is the rail crest at EVERY
    # height, and the central shaft is a clear tube of exactly the rail diameter running the
    # whole tower. Anything smaller than the crest free-falls the axis; anything bigger rides
    # the spiral. Setting the crest BETWEEN two marble sizes turns that into a sorter.
    sort_note = ""
    if (a.hold is None) != (a.drop is None):
        raise SystemExit("sort mode needs BOTH --hold and --drop (the two marble sizes to split)")
    if a.hold is not None:
        # An explicit --rail pins the crest and is CHECKED against both marbles below; without
        # one, sort_gate derives the midpoint (and raises when the sizes are too close to split).
        a.rail = a.rail if a.rail is not None else mc.sort_gate(a.hold, a.drop)
        printed = a.rail - mc.HOLE_SHRINK              # what the machine will actually make
        hold_m, drop_m = a.hold - printed, printed - a.drop
        assert hold_m >= mc.SORT_DRIFT, (
            f"crest Ø{printed:.2f} printed leaves only {hold_m:.2f}mm under the Ø{a.hold:g} "
            f"marble (need {mc.SORT_DRIFT:g}): it would drop the one meant to ride")
        assert drop_m >= mc.SORT_DRIFT, (
            f"crest Ø{printed:.2f} printed leaves only {drop_m:.2f}mm over the Ø{a.drop:g} "
            f"marble (need {mc.SORT_DRIFT:g}): it would hold the one meant to fall")
        sort_note = (f"; SORTS Ø{a.hold:g} (rides) from Ø{a.drop:g} (falls the shaft): crest "
                     f"modelled Ø{a.rail:.2f} prints ~Ø{printed:.2f}, margins {hold_m:.2f}mm "
                     f"under the rider / {drop_m:.2f}mm over the dropper")

    if a.rail is None:
        a.rail = 15.0
    rail_r, pocket_r = a.rail / 2, a.pocket / 2
    if a.hold is None:
        assert a.rail <= mc.MARBLE_D - 1.0, "--rail must undercut the marble by >=1 mm (captivity)"
    grade = math.degrees(math.atan(a.pitch / (2 * math.pi * 13.0)))

    tab = wave_table(rail_r, pocket_r, a.floor_frac, a.pitch)
    slim_note = ""
    if a.slim:
        # size the coupling off the MEASURED pocket, not the nominal --pocket: the fillet pass
        # pulls the emitted pocket in by a few mm, and using the nominal would leave the bond
        # bigger than it needs to be for no reason.
        stock_mouth = mc.SOCKET_MOUTH_D
        mc.configure_bond(mc.min_bond_tip_d(2 * max(tab)))
        slim_note = (f"; SLIM coupling Ø{mc.SPIGOT_TIP_D:.1f}/Ø{mc.SPIGOT_BASE_D:.1f}, mouth "
                     f"Ø{mc.SOCKET_MOUTH_D:.1f} (stock mouth Ø{stock_mouth:.1f})")
    # the EMITTED pocket is what has to pass through the spigot, not the --pocket you asked for:
    # the fillet pass pulls the wave in by a couple of mm and the mesh is the truth.
    assert max(tab) < mc.SPIGOT_TIP_R, (
        f"emitted pocket Ø{2*max(tab):.1f} does not fit through a Ø{mc.SPIGOT_TIP_D:.1f} spigot tip")
    mouth = a.pitch * (1 - (13.0 - rail_r) / (max(tab) - rail_r))  # measured gap at r=13

    def wave(u):
        s = (u % 1.0) * len(tab)
        i = int(s); f = s - i
        return tab[i % len(tab)] * (1 - f) + tab[(i + 1) % len(tab)] * f

    P, N = a.pitch, a.points
    h_cone_lo = mc.cone_h(mc.SPIGOT_BASE_R, pocket_r)
    h_cone_hi = mc.cone_h(mc.SOCKET_BOT_R, pocket_r)
    z_w0 = mc.COUPLE_L + h_cone_lo                 # wave zone: full-pitch blend each end
    wave_h = (a.turns + 2) * P                     # (a shorter blend makes the crest sides
    #                                                steeper than 60° — measured, not guessed)
    z_w1 = z_w0 + wave_h
    total = z_w1 + h_cone_hi + mc.COUPLE_L

    def blend(z):                                  # wave amplitude 0->1->0, cosine-eased
        if z <= z_w0 or z >= z_w1: return 0.0
        d = min(z - z_w0, z_w1 - z)
        return min(1.0, d / P)                     # linear: spreads the ramp derivative flat

    rows = []
    def add_ring(z):
        w = blend(z)
        if w == 0.0:                               # plain profile outside the wave zone
            if z <= mc.COUPLE_L:                    # BOND v2 male spigot: cone + snap bump
                r = mc.spigot_r(z)
            elif z < z_w0: r = mc.SPIGOT_BASE_R + (pocket_r - mc.SPIGOT_BASE_R) * (z - mc.COUPLE_L) / h_cone_lo
            elif z <= z_w1: r = pocket_r
            elif z < total - mc.COUPLE_L: r = pocket_r + (mc.SOCKET_BOT_R - pocket_r) * (z - z_w1) / h_cone_hi
            else:                                   # BOND v2 female socket: cone + groove
                r = mc.socket_r(z - (total - mc.COUPLE_L))
            rows.append((z, [r] * N))
        else:
            radii = [pocket_r - w * (pocket_r - wave(z / P - k / N)) for k in range(N)]
            rows.append((z, radii))

    n_b = int(round(mc.COUPLE_L / mc.BOND_DZ))     # spigot: sampled fine (the bump lives here)
    for i in range(n_b + 1): add_ring(mc.COUPLE_L * i / n_b)
    steps = int(h_cone_lo / 2) + 1
    for i in range(1, steps + 1): add_ring(mc.COUPLE_L + h_cone_lo * i / steps)
    n_wave = int(wave_h / a.zstep)
    for i in range(1, n_wave + 1): add_ring(z_w0 + wave_h * i / n_wave)
    steps = int(h_cone_hi / 2) + 1
    for i in range(1, steps + 1): add_ring(z_w1 + h_cone_hi * i / steps)
    for i in range(1, n_b + 1):                    # socket: sampled fine (the groove lives here)
        add_ring(total - mc.COUPLE_L + mc.COUPLE_L * i / n_b)

    free_ch = 2 * min(min(r) for _, r in rows)     # measured from the emitted rings
    pocket_m = 2 * max(tab)

    z_lean0, z_lean1 = mc.COUPLE_L, total - mc.COUPLE_L
    if a.lean:
        rows = mc.shear_rows(rows, a.lean, z_lean0, z_lean1)
    tris = mc.grid_tris(rows, N)
    mc.write_stl(a.out, tris)
    v = mc.verify_stl(a.out)

    lean_note = ""
    if a.lean:
        # MEASURED off the emitted mesh, both ways: the wall lean the shear cost us, and the
        # lateral step the segment actually delivers (bond-zone centres, not the design number).
        import struct as _s
        with open(a.out, "rb") as f:
            f.read(84)
            lo_x = [1e30, -1e30]; hi_x = [1e30, -1e30]
            for _ in range(v["tris"]):
                f.read(12)
                for _ in range(3):
                    x, y, z = _s.unpack("<3f", f.read(12))
                    tgt = lo_x if z <= mc.COUPLE_L else (hi_x if z >= z_lean1 else None)
                    if tgt is not None:
                        tgt[0] = min(tgt[0], x); tgt[1] = max(tgt[1], x)
                f.read(2)
        step = ((hi_x[0] + hi_x[1]) - (lo_x[0] + lo_x[1])) / 2      # centre-to-centre in x
        want = (z_lean1 - z_lean0) * math.tan(math.radians(a.lean))
        budget = mc.lean_budget(v["max_lean"])
        checks = [
            ("wall lean <= 55", v["max_lean"] <= 55.0,
             f"measured {v['max_lean']:.0f}° from vertical, {budget:+.0f}° of budget left"),
            ("step delivered", abs(step - want) < 0.5,
             f"measured bond-to-bond step {step:.2f}mm vs designed {want:.2f}mm"),
        ]
        ok = True
        for name, good, msg in checks:
            print("  %s %-18s %s" % ("PASS" if good else "FAIL", name, msg))
            ok = ok and good
        if not ok:
            os.replace(a.out, a.out + ".FAILED")
            raise SystemExit(
                f"\nLEAN {a.lean:g}° REFUSED: measured wall lean {v['max_lean']:.0f}° against the "
                f"55° vase ceiling.\nTilt does NOT cost a degree of wall lean per degree of lean: "
                f"the shear rotates the surface normal, and the steepest facet is not the one "
                f"facing the tilt, so the wall gains only ~0.25° per degree.\nMEASURED ceilings "
                f"(the sweep that found them is in the repo history, each one fails at +1°):\n"
                f"  --pitch 32 (default)  leans to 16°  (49mm sideways per segment)\n"
                f"  --pitch 38            leans to 22°  (81mm sideways per segment)\n"
                f"  --pitch 44            leans to 23°  (98mm sideways per segment)\n"
                f"A relaxed wave buys the tilt: pitch 38 measures 47° unsheared where the default "
                f"measures 51°.\nThe 45° floor underneath is marble_common.CONE_SLOPE (the end "
                f"transition cones), not the wave.\n{a.out} quarantined to .FAILED.")
        lean_note = (f", LEANING {a.lean:g}° (measured wall lean {v['max_lean']:.0f}°, "
                     f"{budget:.0f}° left; the segment steps {step:.1f}mm sideways bond to bond)")

    mc.report(a.out, v, note=(
        f"{a.turns} captive turns, pitch {P:g} (drop/lap), measured rail Ø{free_ch:.1f} "
        f"(< marble Ø{mc.MARBLE_D:g}, captive) / pocket Ø{pocket_m:.1f}, "
        f"gutter mouth ~{mouth:.1f} mm at the ride radius, rolling grade ~{grade:.0f}°"
        + lean_note + sort_note + slim_note))


if __name__ == "__main__":
    main()
