#!/usr/bin/env python3
"""FUNNEL STL — a pour funnel for floating the sand+gypsum slurry into the Ø64 vase legs.

An open truncated cone: a wide MOUTH to catch the pour, flaring down to a narrow SPOUT that drops
INTO the leg's top opening. Open at both ends (it is a funnel), so it is a SURFACE, not a solid —
exactly what a slicer's vase/spiralize mode wants (print the single-wall cone, no infill). Print it
mouth-down (wide, stable base) then use it the other way up.

Usage: python3 funnel_stl.py [--mouth 160] [--spout 55] [--spout-drop 40] [--flare 90] [--points 120]
       --spout should be a few mm UNDER the leg bore (Ø64 -> ~55) so it seats inside the leg top.
"""
import argparse, math, os, struct


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mouth", type=float, default=160.0, help="mouth (wide top) diameter mm")
    ap.add_argument("--spout", type=float, default=55.0, help="spout (narrow bottom) dia mm; sits inside the Ø64 leg")
    ap.add_argument("--spout-drop", type=float, default=40.0, help="straight spout length that drops into the leg")
    ap.add_argument("--flare", type=float, default=90.0, help="flare (cone) height mm from spout to mouth")
    ap.add_argument("--points", type=int, default=120, help="points per ring")
    ap.add_argument("--out", default="funnel.stl")
    a = ap.parse_args()

    r_mouth, r_spout = a.mouth / 2.0, a.spout / 2.0
    N = a.points
    # rings bottom(z=0, spout tip) -> up: straight spout, then flared cone to the mouth
    rings = []                                    # (z, radius)
    SPOUT_RINGS, FLARE_RINGS = 8, 60
    for i in range(SPOUT_RINGS + 1):              # straight spout
        rings.append((a.spout_drop * i / SPOUT_RINGS, r_spout))
    for i in range(1, FLARE_RINGS + 1):           # flare out to the mouth
        t = i / FLARE_RINGS
        rings.append((a.spout_drop + a.flare * t, r_spout + (r_mouth - r_spout) * t))

    def pt(z, r, k):
        th = 2 * math.pi * k / N
        return (r * math.cos(th), r * math.sin(th), z)

    tris = []                                     # open surface: quads between consecutive rings, no caps
    for a0 in range(len(rings) - 1):
        z0, r0 = rings[a0]; z1, r1 = rings[a0 + 1]
        for k in range(N):
            p00 = pt(z0, r0, k);   p01 = pt(z0, r0, (k + 1) % N)
            p10 = pt(z1, r1, k);   p11 = pt(z1, r1, (k + 1) % N)
            tris.append((p00, p10, p11)); tris.append((p00, p11, p01))

    with open(a.out, "wb") as f:
        f.write(b"\0" * 80); f.write(struct.pack("<I", len(tris)))
        for t in tris:
            ux, uy, uz = (t[1][0]-t[0][0], t[1][1]-t[0][1], t[1][2]-t[0][2])
            vx, vy, vz = (t[2][0]-t[0][0], t[2][1]-t[0][1], t[2][2]-t[0][2])
            nx, ny, nz = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
            m = math.hypot(nx, ny, nz) or 1.0
            f.write(struct.pack("<3f", nx/m, ny/m, nz/m))
            for p in t: f.write(struct.pack("<3f", *p))
            f.write(b"\0\0")
    print(f"{a.out}: {len(tris)} triangles, mouth Ø{a.mouth:g} -> spout Ø{a.spout:g} "
          f"(seats in Ø64 leg), spout-drop {a.spout_drop:g}, flare {a.flare:g}, total h "
          f"{a.spout_drop + a.flare:g}mm — OPEN cone, slice in VASE mode")


if __name__ == "__main__":
    main()
