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

Coupling: standard kit collars — Ø56 female socket (top), Ø55 male spigot (bottom); the
wave blends into plain cones over half a pitch at each end (entry hands the marble to the
first full turn; exit lets the last turn pour into the spigot).

Usage: python3 spiral_chute_stl.py [--turns 4] [--pitch 28] [--rail 15] [--pocket 44]
                                   [--floor-frac 0.54] [--points 144] [--out spiral_chute.stl]
"""
import argparse, math

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
    ap.add_argument("--rail", type=float, default=15.0,
                    help="rail crest dia mm — MUST be < marble Ø16 to keep it captive")
    ap.add_argument("--pocket", type=float, default=44.0, help="pocket (outer wave) dia mm")
    ap.add_argument("--floor-frac", type=float, default=0.50,
                    help="fraction of pitch used by the up-facing floor flank")
    ap.add_argument("--socket", type=float, default=mc.SOCKET_D, help="female socket dia (top)")
    ap.add_argument("--spigot", type=float, default=mc.SPIGOT_D, help="male spigot dia (bottom)")
    ap.add_argument("--points", type=int, default=144, help="points per ring")
    ap.add_argument("--zstep", type=float, default=0.5, help="ring spacing mm in the wave zone")
    ap.add_argument("--out", default="spiral_chute.stl")
    a = ap.parse_args()

    rail_r, pocket_r = a.rail / 2, a.pocket / 2
    rs, rg = a.socket / 2, a.spigot / 2
    assert a.rail <= mc.MARBLE_D - 1.0, "--rail must undercut the marble by >=1 mm (captivity)"
    assert pocket_r < rg, "--pocket must stay inside the spigot dia"
    grade = math.degrees(math.atan(a.pitch / (2 * math.pi * 13.0)))

    tab = wave_table(rail_r, pocket_r, a.floor_frac, a.pitch)
    mouth = a.pitch * (1 - (13.0 - rail_r) / (max(tab) - rail_r))  # measured gap at r=13

    def wave(u):
        s = (u % 1.0) * len(tab)
        i = int(s); f = s - i
        return tab[i % len(tab)] * (1 - f) + tab[(i + 1) % len(tab)] * f

    P, N = a.pitch, a.points
    h_cone_lo = mc.cone_h(rg, pocket_r)
    h_cone_hi = mc.cone_h(rs, pocket_r)
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
            if z <= mc.COUPLE_L: r = rg
            elif z < z_w0: r = rg + (pocket_r - rg) * (z - mc.COUPLE_L) / h_cone_lo
            elif z <= z_w1: r = pocket_r
            elif z < total - mc.COUPLE_L: r = pocket_r + (rs - pocket_r) * (z - z_w1) / h_cone_hi
            else: r = rs
            rows.append((z, [r] * N))
        else:
            radii = [pocket_r - w * (pocket_r - wave(z / P - k / N)) for k in range(N)]
            rows.append((z, radii))

    add_ring(0.0); add_ring(mc.COUPLE_L)           # spigot
    steps = int(h_cone_lo / 2) + 1
    for i in range(1, steps + 1): add_ring(mc.COUPLE_L + h_cone_lo * i / steps)
    n_wave = int(wave_h / a.zstep)
    for i in range(1, n_wave + 1): add_ring(z_w0 + wave_h * i / n_wave)
    steps = int(h_cone_hi / 2) + 1
    for i in range(1, steps + 1): add_ring(z_w1 + h_cone_hi * i / steps)
    add_ring(total)

    tris = mc.grid_tris(rows, N)
    mc.write_stl(a.out, tris)
    v = mc.verify_stl(a.out)
    free_ch = 2 * min(min(r) for _, r in rows)     # measured from the emitted rings
    pocket_m = 2 * max(tab)
    mc.report(a.out, v, note=(
        f"{a.turns} captive turns, pitch {P:g} (drop/lap), measured rail Ø{free_ch:.1f} "
        f"(< marble Ø{mc.MARBLE_D:g}, captive) / pocket Ø{pocket_m:.1f}, "
        f"gutter mouth ~{mouth:.1f} mm at the ride radius, rolling grade ~{grade:.0f}°"))


if __name__ == "__main__":
    main()
