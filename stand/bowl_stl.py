#!/usr/bin/env python3
"""BOWL STL — a flexible TPU mixing bowl for the sand+gypsum slurry.

Print in TPU, slicer VASE mode: a single flexible wall + solid bottom. TPU flexes like silicone, so the
set plaster pops out when you bend the bowl (no buying expensive silicone, no bag liner). Wide + shallow-ish
so you can stir fast before it goes off. Open at the top (a bowl), so it is a single revolved SURFACE with
a closed bottom, exactly what vase mode wants.

Usage: python3 bowl_stl.py [--bottom 100] [--rim 220] [--depth 110] [--points 140]
       (dims are DIAMETERS mm; ~2.2L at the defaults = a manageable ~4kg batch)
"""
import argparse, math, os, struct


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bottom", type=float, default=100.0, help="flat bottom diameter mm (stable + stir the base)")
    ap.add_argument("--rim", type=float, default=220.0, help="rim (mouth) diameter mm, wide = mix fast")
    ap.add_argument("--depth", type=float, default=110.0, help="bowl depth mm")
    ap.add_argument("--points", type=int, default=140, help="points per ring")
    ap.add_argument("--rings", type=int, default=80, help="rings up the wall")
    ap.add_argument("--curve", type=float, default=0.85,
                    help="wall profile exponent t**curve; 0.85 keeps the base lean under the 55deg "
                         "vase ceiling (0.7 flared too low: qa_stl measured 63.8deg at the base)")
    ap.add_argument("--out", default="bowl.stl")
    a = ap.parse_args()

    rb, rr, N = a.bottom / 2.0, a.rim / 2.0, a.points
    # profile (r,z): flat bottom out to rb, then a flared wall to the rim (t**curve = bowl-ish)
    prof = [(0.0, 0.0), (rb, 0.0)]
    for i in range(1, a.rings + 1):
        t = i / a.rings
        prof.append((rb + (rr - rb) * (t ** a.curve), a.depth * t))

    def pt(r, z, k):
        th = 2 * math.pi * k / N
        return (r * math.cos(th), r * math.sin(th), z)

    tris = []
    # bottom fan: centre (0,0,0) to the first real ring (r=rb)
    r0, z0 = prof[1]
    for k in range(N):
        tris.append(((0.0, 0.0, 0.0), pt(r0, z0, k), pt(r0, z0, (k + 1) % N)))
    # wall: quads between rings prof[1..end]
    for i in range(1, len(prof) - 1):
        ra, za = prof[i]; rc, zc = prof[i + 1]
        for k in range(N):
            p00 = pt(ra, za, k); p01 = pt(ra, za, (k + 1) % N)
            p10 = pt(rc, zc, k); p11 = pt(rc, zc, (k + 1) % N)
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
    # rough volume (disc integration)
    vol = 0.0
    for i in range(len(prof) - 1):
        ra, za = prof[i]; rc, zc = prof[i + 1]
        vol += math.pi * ((ra + rc) / 2) ** 2 * (zc - za)
    print(f"{a.out}: {len(tris)} triangles, bottom Ø{a.bottom:g} rim Ø{a.rim:g} depth {a.depth:g}mm, "
          f"~{vol/1e6:.2f} L capacity — TPU, slice VASE mode (flexible wall + solid bottom)")


if __name__ == "__main__":
    main()
