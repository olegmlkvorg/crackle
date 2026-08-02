#!/usr/bin/env python3
"""star_ring_stl.py — a STRETCHABLE STAR RING that crowns the marble-kit joints (Oleg 2026-08-02:
"stretchable ring to put on top of connected ball spiral parts (pla, starish shape)").

STATUS: OPTIONAL DECORATION (v4, bond v2.1). The joint no longer needs a retainer: BOND v2.1's
deep detent measures a +0.68 mm peak radial interference over the withdrawal sweep (gate
bond_check.py, required >= 0.45) — the snap holds the joint by itself. Earlier ring versions
(v3/v3.1) "gripped the Ø57.2 male body below the joint": on an ASSEMBLED joint that body is
FICTION — the male is inside the socket, and the only outer surfaces are the female mouth cone
(rim face Ø60.6) with the groove bulge ~9.5-15 mm below the rim. The adversarial sweep showed a
rigid v3.1 ring stalls on that bulge and never reaches its imagined seat. v4 therefore reverts
to the honest mouth-crown: it clamps the FEMALE MOUTH OUTER only.

HOW IT SITS: drop it over the rim from above (before or after stacking — the spigot passes
inside the socket wall, never through the ring). The star arms stretch ~2% diametrally to cross
the Ø60.6 rim face (bend-dominated: peak material strain ~ t/2A * stretch ~ 0.7%, safe for PLA),
then relax onto the narrowing mouth cone and wedge where the outer face measures GRIP_D — about
2 mm below the rim, far above the groove bulge. Pressing it down only tightens it (wedge).

WHY PLA CAN STRETCH HERE: solid PLA takes only ~1.5-2% strain, but a CORRUGATED (star) ring
stretches by BENDING its arms, not by straining the material. Peak material strain ~= (t / 2A) *
stretch, so the wave amplitude divides the strain. The star IS the spring.

GEOMETRY: an N-point star band, r(theta) = base + A*star(N*theta), star() a sharpened cosine
(--sharp < 1 = pointier, more alien peaks). Straight prism, prints flat, no support, ~10 min.
Watertight closed solid (qa_stl --class closed). PLA only. All joint dimensions are DERIVED
from marble_common (never restated): rim face, mouth-cone slope, groove-bulge zone.

Usage: python3 star_ring_stl.py [--lobes 8] [--amp 2.5] [--wall 1.8] [--height 8]
                                [--sharp 0.6] [--points 48] [--out star_ring.stl]
"""
import argparse, math, os, struct

import marble_common as mc

# every joint dimension DERIVED from the bond standard (v3.1's restated constants drifted into fiction)
MOUTH_FACE_D = 2 * (mc.SOCKET_MOUTH_R + mc.LINE_W / 2)          # rim printed outer face (Ø60.6)
FACE_SLOPE = (mc.SOCKET_MOUTH_R - mc.socket_r(mc.LAND_H)) / (mc.COUPLE_L - mc.LAND_H)
GRIP_D = 59.4            # lobe-tip circle: 1.2 mm under the rim face -> ~2% stretch to cross,
#                          then wedges on the mouth cone ~2 mm below the rim
RING_REACH = (MOUTH_FACE_D - GRIP_D) / 2 / FACE_SLOPE            # mm below the rim it reaches
# groove-bulge no-go zone, from the bond profile: top edge of the outward bulge (dev > 0.05)
def _bulge_top_below_rim():
    d = mc.BUMP_Z + mc.GROOVE_W / 2
    while d > mc.BUMP_Z and mc._bulge(d, mc.BUMP_Z, mc.GROOVE_W, mc.GROOVE_H) < 0.05:
        d -= 0.01
    return mc.COUPLE_L - d
BULGE_TOP_BELOW_RIM = _bulge_top_below_rim()


def star(u, sharp):
    """Sharpened cosine in [-1, 1]: cos sign kept, magnitude^sharp -> pointy star peaks for sharp<1."""
    c = math.cos(u)
    return math.copysign(abs(c) ** sharp, c)


def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris, header=b"crackle star_ring v4 - optional mouth-crown (PLA star spring)"):
    with open(path, "wb") as fh:
        fh.write(header.ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            fh.write(struct.pack("<3f", *normal(a, b, c)))
            for v in (a, b, c):
                fh.write(struct.pack("<3f", *v))
            fh.write(struct.pack("<H", 0))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grip-dia", type=float, default=GRIP_D,
                    help="lobe-tip inner circle mm (default wedges ~2 mm below the rim)")
    ap.add_argument("--lobes", type=int, default=8, help="star points")
    ap.add_argument("--amp", type=float, default=2.5, help="wave amplitude mm (divides the strain)")
    ap.add_argument("--wall", type=float, default=1.8, help="band thickness mm")
    ap.add_argument("--height", type=float, default=8.0, help="band height mm (a crown, not a collar)")
    ap.add_argument("--sharp", type=float, default=0.6, help="peak sharpening exponent (<1 = pointier)")
    ap.add_argument("--points", type=int, default=48, help="samples per lobe period")
    ap.add_argument("--out", default="star_ring.stl")
    a = ap.parse_args()

    r_grip = a.grip_dia / 2.0                  # innermost radius = lobe tips (they grip)
    N = a.lobes * a.points
    h = a.height

    mid = []
    for k in range(N):
        th = 2 * math.pi * k / N
        w = star(a.lobes * th, a.sharp)
        rm = (r_grip + a.wall / 2.0) + a.amp * (1.0 + w)
        mid.append((rm * math.cos(th), rm * math.sin(th)))

    def parallel(pts, dist):
        out = []
        n_ = len(pts)
        for k in range(n_):
            p_prev, p, p_next = pts[k - 1], pts[k], pts[(k + 1) % n_]
            e1 = (p[0] - p_prev[0], p[1] - p_prev[1])
            e2 = (p_next[0] - p[0], p_next[1] - p[1])
            n1 = (e1[1], -e1[0]); m1 = math.hypot(*n1) or 1e-12
            n2 = (e2[1], -e2[0]); m2 = math.hypot(*n2) or 1e-12
            bx, by = n1[0] / m1 + n2[0] / m2, n1[1] / m1 + n2[1] / m2
            bm = math.hypot(bx, by) or 1e-9
            d = min(2.0 * abs(dist) / bm, 2.0 * abs(dist)) * (1 if dist >= 0 else -1)
            out.append((p[0] + bx / bm * d, p[1] + by / bm * d))
        return out

    inner = parallel(mid, -a.wall / 2.0)
    outer = parallel(mid, a.wall / 2.0)

    tris = []
    for k in range(N):
        j = (k + 1) % N
        O0 = (outer[k][0], outer[k][1], 0.0); O1 = (outer[j][0], outer[j][1], 0.0)
        O0h = (outer[k][0], outer[k][1], h);  O1h = (outer[j][0], outer[j][1], h)
        I0 = (inner[k][0], inner[k][1], 0.0); I1 = (inner[j][0], inner[j][1], 0.0)
        I0h = (inner[k][0], inner[k][1], h);  I1h = (inner[j][0], inner[j][1], h)
        tris.append((O0, O1, O1h)); tris.append((O0, O1h, O0h))       # outer wall
        tris.append((I0, I1h, I1)); tris.append((I0, I0h, I1h))       # inner wall
        tris.append((O0, I0, I1)); tris.append((O0, I1, O1))          # bottom (-z)
        tris.append((O0h, O1h, I1h)); tris.append((O0h, I1h, I0h))    # top (+z)

    write_binary_stl(a.out, tris)

    # self-verify: laws + edge parity
    size = os.path.getsize(a.out)
    assert size == 84 + 50 * len(tris), "filesize law"
    edges = {}
    for t in tris:
        key = [(round(v[0], 3), round(v[1], 3), round(v[2], 3)) for v in t]
        for i in range(3):
            e = tuple(sorted((key[i], key[(i + 1) % 3])))
            edges[e] = edges.get(e, 0) + 1
    oe = sum(1 for c in edges.values() if c != 2)

    # ---- FUNCTION checks (QC != function). The ring is OPTIONAL: check 1 proves the BOND holds
    # the joint without it (design withdrawal sweep, marble_common); the rest prove the crown
    # actually sits where it claims. A failing ring is quarantined.
    sw = mc.withdrawal_sweep(mc.spigot_profile(),
                             [(d, mc.socket_r(d)) for d in mc._bond_zs()])
    stretch = (MOUTH_FACE_D - a.grip_dia) / a.grip_dia   # diametral stretch to cross the rim
    eps = a.wall / (2 * a.amp) * stretch
    squeeze_at_rim = (MOUTH_FACE_D - a.grip_dia) / 2.0   # radial pinch while crossing
    reach = (MOUTH_FACE_D - a.grip_dia) / 2 / FACE_SLOPE if a.grip_dia < MOUTH_FACE_D else 99.0
    od = 2 * (r_grip + 2 * a.amp + a.wall)
    PROPORTION_MAX = 1.25
    def _seg_d(p, q1, q2):
        dx, dy = q2[0]-q1[0], q2[1]-q1[1]
        L2 = dx*dx + dy*dy or 1e-12
        t_ = max(0.0, min(1.0, ((p[0]-q1[0])*dx + (p[1]-q1[1])*dy) / L2))
        return math.hypot(p[0]-(q1[0]+t_*dx), p[1]-(q1[1]+t_*dy))
    ths = []
    for k in range(N):
        d = min(_seg_d(inner[k], outer[(k+m) % N], outer[(k+m+1) % N]) for m in range(-3, 3))
        ths.append(d)
    ths.sort()
    t_min, t_med, t_max = ths[0], ths[N//2], ths[-1]

    checks = [
        ("watertight", oe == 0, "%d open edges" % oe),
        ("OPTIONAL: bond holds alone", sw["peak"] >= mc.SNAP_MIN,
         "BOND v2.1 withdrawal-sweep peak %+.2f mm (>= %.2f) -> the ring is decoration, not a retainer"
         % (sw["peak"], mc.SNAP_MIN)),
        ("crowns the female mouth", 0.3 <= squeeze_at_rim <= 0.9 and 1.0 <= reach <= 4.0,
         "tips O%.1f cross the O%.1f rim (%.2f mm radial pinch), wedge %.1f mm below the rim"
         % (a.grip_dia, MOUTH_FACE_D, squeeze_at_rim, reach)),
        ("clear of the groove bulge", reach + 1.0 <= BULGE_TOP_BELOW_RIM,
         "reaches %.1f mm below the rim; bulge starts %.1f mm below (margin %.1f, need >= 1)"
         % (reach, BULGE_TOP_BELOW_RIM, BULGE_TOP_BELOW_RIM - reach)),
        ("strain safe (<=1.2%)", eps <= 0.012,
         "peak ~%.2f%% at %.1f%% stretch over the rim (t/2A model)" % (100*eps, 100*stretch)),
        ("proportion (od <= %.2fx pipe)" % PROPORTION_MAX, od <= PROPORTION_MAX * MOUTH_FACE_D,
         "outer peaks O%.1f vs pipe O%.1f" % (od, MOUTH_FACE_D)),
        ("wall constant (measured)", t_min >= 0.8*a.wall and t_max <= 1.4*a.wall,
         "min %.2f / med %.2f / max %.2f vs nominal %.2f" % (t_min, t_med, t_max, a.wall)),
    ]
    print(f"{a.out}: {len(tris)} tris, {size} bytes")
    print(f"  v4 OPTIONAL mouth-crown: {a.lobes}-point star, tips O{a.grip_dia:g}, outer peaks O{od:.1f}, "
          f"band {a.wall:g} x {h:g}mm, amp {a.amp:g}, sharp {a.sharp:g}")
    ok = True
    for name, good, msg in checks:
        print("  %s %-28s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    print("  seats on: female mouth outer cone only (the O57.2 'male body' of v3 does not exist "
          "on an assembled joint); prints FLAT, no support, PLA")
    if not ok:
        failed = a.out + ".FAILED"
        os.replace(a.out, failed)
        print("  SELF-VERIFY: FAIL -> quarantined %s" % failed)
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS")


if __name__ == "__main__":
    main()
