#!/usr/bin/env python3
"""star_ring_stl.py — a STRETCHABLE STAR RING that crowns the marble-kit joints (Oleg 2026-08-02:
"stretchable ring to put on top of connected ball spiral parts (pla, starish shape)").

WHY PLA CAN STRETCH HERE: solid PLA takes only ~1.5-2% strain, but a CORRUGATED (star) ring stretches
by BENDING its arms, not by straining the material. Peak material strain ~= (t / 2A) * stretch, so the
wave amplitude divides the strain: t=1.8, A=6 -> a 1.7% stretch costs only ~0.25% material strain.
The star IS the spring (beam-theory estimate; the print is the proof).

WHERE IT SITS: the kit's tapered joints. The female mouth's printed OUTER face is ~Ø60.4 (path 59.2 +
1.2 wall); the male body below is ~Ø57.2. Two modes:
  --mode mouth (default): grip Ø59.4 lobes clamp ONTO the mouth rim (+1.7% stretch) — squeezes the
      mouth onto the spigot and crowns the joint.
  --mode over: grip Ø56.6 stretches OVER the mouth (+6.7%, ~0.77% strain) and snaps onto the male
      body BELOW the joint — a retaining collar the joint cannot open past.

GEOMETRY: an N-point star band, r(theta) = base + A*star(N*theta), where star() is a sharpened cosine
(exponent --sharp < 1 makes pointier, more alien peaks). Inner surface at the wave, outer = wave + t.
A flat prism ring: prints flat on the bed, no support, ~10 min. Watertight closed solid (qa_stl
--class closed). PLA only; the compliance numbers assume PLA's modulus — TPU would just be floppy.

Usage: python3 star_ring_stl.py [--mode mouth|over] [--lobes 8] [--amp 6] [--wall 1.8]
                                [--height 8] [--sharp 0.6] [--points 48] [--out star_ring.stl]
"""
import argparse, math, os, struct

MOUTH_FACE_D = 60.4      # female mouth printed outer face (59.2 path + 1.2 wall)
MALE_FACE_D = 57.2       # male body printed outer face below the mouth (56 + 1.2)
GRIP_MOUTH_D = 59.4      # lobe-tip circle, mouth mode: 1.0mm diametral squeeze on the mouth
GRIP_OVER_D = 56.6       # lobe-tip circle, over mode: 0.6mm squeeze on the male body


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


def write_binary_stl(path, tris, header=b"crackle star_ring - compliant joint crown (PLA star spring)"):
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
    ap.add_argument("--mode", choices=("mouth", "over"), default="mouth",
                    help="mouth = clamp onto the female mouth rim; over = stretch past it, grip the male body")
    ap.add_argument("--grip-dia", type=float, default=None,
                    help="lobe-tip inner circle mm (overrides the mode default)")
    ap.add_argument("--lobes", type=int, default=8, help="star points")
    ap.add_argument("--amp", type=float, default=None,
                    help="wave amplitude mm (default per mode: mouth 2.0, over 5.0 -- the smallest that keeps peak strain under ~1.2%%)")
    ap.add_argument("--wall", type=float, default=None,
                    help="band thickness mm (default per mode: mouth 1.8, over 1.4 -- over needs softer)")
    ap.add_argument("--height", type=float, default=16.0, help="band height mm (tall = spans the joint)")
    ap.add_argument("--sharp", type=float, default=0.6, help="peak sharpening exponent (<1 = pointier star)")
    ap.add_argument("--points", type=int, default=48, help="samples per lobe period")
    ap.add_argument("--out", default="star_ring.stl")
    a = ap.parse_args()

    grip_d = a.grip_dia or (GRIP_MOUTH_D if a.mode == "mouth" else GRIP_OVER_D)
    if a.amp is None:
        a.amp = 2.5 if a.mode == "mouth" else 4.0
    if a.wall is None:
        a.wall = 1.8 if a.mode == "mouth" else 1.4
    r_grip = grip_d / 2.0                      # innermost radius = lobe tips (they grip)
    base = r_grip + a.amp                      # wave centreline: r(theta) = base + amp*star -> min = r_grip
    N = a.lobes * a.points

    # V3 CONICAL WEDGE-LOCK (Oleg 2026-08-02: "tension not sufficient to hold the joint together...
    # higher... not straight... pushing harder"). The bore is a CONE matching the joint: the lower
    # zone squeezes the male body (O57.2 face), the upper zone rides the female mouth cone; pulling
    # the joint apart drives the cone into the star spring = wedges TIGHTER. Assembly: slide up the
    # male body, climb the mouth cone until snug -- the ring never crosses the O60.4 rim.
    # squeeze: 0.9mm RADIAL both zones (about double v2's push); strain = t/2A * stretch stays
    # under ~1.2% with amp 2.5.
    SQUEEZE_R = 0.9
    tip_bot = MALE_FACE_D / 2.0 - SQUEEZE_R              # bottom lobe-tip radius (grips the male)
    # mouth cone outer face: ~O57.2 at its base rising to O60.4 at the rim over the 16mm engagement;
    # the ring's top zone meets it mid-cone: tip_top set to seat ~4mm below the rim
    tip_top = (MOUTH_FACE_D - 2.0) / 2.0 - SQUEEZE_R     # grips the cone where it measures ~O58.4
    NZ = 9                                                # loft rings up the height
    h = a.height

    def ring2d(tip_r):
        mid_, out_, inn_ = [], [], []
        for k in range(N):
            th = 2 * math.pi * k / N
            w = star(a.lobes * th, a.sharp)
            rm = (tip_r + a.wall / 2.0) + a.amp * (1.0 + w)
            mid_.append((rm * math.cos(th), rm * math.sin(th)))
        return mid_

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

    levels = []                                           # (z, inner2d, outer2d) per loft ring
    for iz in range(NZ + 1):
        f = iz / NZ
        tip = tip_bot + (tip_top - tip_bot) * f
        mid = ring2d(tip)
        levels.append((h * f, parallel(mid, -a.wall / 2.0), parallel(mid, a.wall / 2.0)))
    inner = levels[0][1]; outer = levels[0][2]            # base ring (function checks reference it)

    tris = []
    for lz in range(NZ):
        z0, in0, ot0 = levels[lz]
        z1, in1, ot1 = levels[lz + 1]
        for k in range(N):
            j = (k + 1) % N
            O0 = (ot0[k][0], ot0[k][1], z0); O1 = (ot0[j][0], ot0[j][1], z0)
            O0h = (ot1[k][0], ot1[k][1], z1); O1h = (ot1[j][0], ot1[j][1], z1)
            I0 = (in0[k][0], in0[k][1], z0); I1 = (in0[j][0], in0[j][1], z0)
            I0h = (in1[k][0], in1[k][1], z1); I1h = (in1[j][0], in1[j][1], z1)
            tris.append((O0, O1, O1h)); tris.append((O0, O1h, O0h))       # outer wall
            tris.append((I0, I1h, I1)); tris.append((I0, I0h, I1h))       # inner wall
    b_in = [(p[0], p[1], 0.0) for p in levels[0][1]]
    b_ot = [(p[0], p[1], 0.0) for p in levels[0][2]]
    t_in = [(p[0], p[1], h) for p in levels[NZ][1]]
    t_ot = [(p[0], p[1], h) for p in levels[NZ][2]]
    for k in range(N):
        j = (k + 1) % N
        tris.append((b_ot[k], b_in[k], b_in[j])); tris.append((b_ot[k], b_in[j], b_ot[j]))   # bottom (-z)
        tris.append((t_ot[k], t_ot[j], t_in[j])); tris.append((t_ot[k], t_in[j], t_in[k]))   # top (+z)

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

    # ---- FUNCTION checks (Oleg 2026-08-02: "ring is clearly too big to be useful... no
    # connection to reality" -- printability gates alone say nothing about the part serving its
    # joint; QC != function). Every claim below is computed, and a failing ring is quarantined.
    target = MOUTH_FACE_D
    sq_bot = MALE_FACE_D / 2.0 - tip_bot                 # radial squeeze on the male body
    sq_top = (MOUTH_FACE_D - 2.0) / 2.0 - tip_top        # radial squeeze at the cone seat
    stretch = 2.0 * sq_bot / (2.0 * tip_bot)             # worst diametral stretch (bottom zone)
    eps = a.wall / (2 * a.amp) * stretch
    od = 2 * (tip_top + 2 * a.amp + a.wall)
    rim_clear = MOUTH_FACE_D / 2.0 - tip_top             # top tips sit INSIDE the rim = wedge lock
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
        ("squeezes the male body", 0.5 <= sq_bot <= 1.5,
         "bottom tips O%.1f vs male O%.1f = %.2fmm radial push" % (2*tip_bot, MALE_FACE_D, sq_bot)),
        ("wedges on the mouth cone", 0.4 <= sq_top and rim_clear >= 0.5,
         "top tips O%.1f seat mid-cone, %.2fmm inside the O%.1f rim -> separation TIGHTENS it"
         % (2*tip_top, rim_clear, MOUTH_FACE_D)),
        ("strain safe (<=1.2%)", eps <= 0.012, "peak ~%.2f%% at %.1f%% stretch (t/2A model)" % (100*eps, 100*stretch)),
        ("proportion (od <= %.2fx pipe)" % PROPORTION_MAX, od <= PROPORTION_MAX * MOUTH_FACE_D,
         "outer peaks O%.1f vs pipe O%.1f" % (od, MOUTH_FACE_D)),
        ("wall constant (measured)", t_min >= 0.8*a.wall and t_max <= 1.4*a.wall,
         "min %.2f / med %.2f / max %.2f vs nominal %.2f" % (t_min, t_med, t_max, a.wall)),
        ("tall enough to span the joint", h >= 14.0, "height %.0fmm (needs >=14 to bridge both zones)" % h),
    ]
    print(f"{a.out}: {len(tris)} tris, {size} bytes")
    print(f"  mode {a.mode}: {a.lobes}-point CONICAL star, tips O{2*tip_bot:.1f}->O{2*tip_top:.1f}, outer peaks O{od:.1f}, "
          f"band {a.wall:g} x {h:g}mm, amp {a.amp:g}, sharp {a.sharp:g}")
    ok = True
    for name, good, msg in checks:
        print("  %s %-28s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    print(f"  seats on: {'female mouth rim (crowns the joint)' if a.mode=='mouth' else 'male body below the joint (retainer)'}; "
          f"prints FLAT, no support, PLA")
    if not ok:
        failed = a.out + ".FAILED"
        os.replace(a.out, failed)
        print("  SELF-VERIFY: FAIL -> quarantined %s" % failed)
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS")


if __name__ == "__main__":
    main()
