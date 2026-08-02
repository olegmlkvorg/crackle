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
    ap.add_argument("--amp", type=float, default=6.0, help="wave amplitude mm (bigger = softer spring)")
    ap.add_argument("--wall", type=float, default=1.8, help="band thickness mm (thinner = softer)")
    ap.add_argument("--height", type=float, default=8.0, help="band height mm")
    ap.add_argument("--sharp", type=float, default=0.6, help="peak sharpening exponent (<1 = pointier star)")
    ap.add_argument("--points", type=int, default=48, help="samples per lobe period")
    ap.add_argument("--out", default="star_ring.stl")
    a = ap.parse_args()

    grip_d = a.grip_dia or (GRIP_MOUTH_D if a.mode == "mouth" else GRIP_OVER_D)
    r_grip = grip_d / 2.0                      # innermost radius = lobe tips (they grip)
    base = r_grip + a.amp                      # wave centreline: r(theta) = base + amp*star -> min = r_grip
    N = a.lobes * a.points

    inner, outer = [], []
    for k in range(N):
        th = 2 * math.pi * k / N
        # inner surface radius in [r_grip, r_grip + 2A]: wave MINIMA are the lobe tips that grip
        w = star(a.lobes * th, a.sharp)                     # [-1, 1], sharpened
        ri = r_grip + a.amp * (1.0 + w)
        ro = ri + a.wall
        inner.append((ri * math.cos(th), ri * math.sin(th)))
        outer.append((ro * math.cos(th), ro * math.sin(th)))

    h = a.height
    tris = []
    for k in range(N):
        j = (k + 1) % N
        i0, i1 = inner[k], inner[j]
        o0, o1 = outer[k], outer[j]
        I0, I1 = (i0[0], i0[1], 0.0), (i1[0], i1[1], 0.0)
        O0, O1 = (o0[0], o0[1], 0.0), (o1[0], o1[1], 0.0)
        I0h, I1h = (i0[0], i0[1], h), (i1[0], i1[1], h)
        O0h, O1h = (o0[0], o0[1], h), (o1[0], o1[1], h)
        tris.append((O0, O1, O1h)); tris.append((O0, O1h, O0h))       # outer wall (outward)
        tris.append((I0, I1h, I1)); tris.append((I0, I0h, I1h))       # inner wall (inward)
        tris.append((O0, I0, I1)); tris.append((O0, I1, O1))          # bottom cap (normal -z)
        tris.append((O0h, O1h, I1h)); tris.append((O0h, I1h, I0h))    # top cap (normal +z)

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

    target = MOUTH_FACE_D
    stretch = (target - grip_d) / grip_d
    eps = a.wall / (2 * a.amp) * stretch
    od = 2 * (r_grip + 2 * a.amp + a.wall)
    print(f"{a.out}: {len(tris)} tris, {size} bytes, open edges {oe} [0=watertight]")
    print(f"  mode {a.mode}: {a.lobes}-point star, grip Ø{grip_d:g} lobe tips, outer peaks Ø{od:.1f}, "
          f"band {a.wall:g} x {h:g}mm, sharp {a.sharp:g}")
    print(f"  must open +{100*stretch:.1f}% to pass the Ø{target:g} mouth -> peak PLA strain "
          f"~{100*eps:.2f}% (t/2A={a.wall/(2*a.amp):.2f}; <1.5% = safe; beam estimate, print = proof)")
    print(f"  seats on: {'female mouth rim (crowns the joint)' if a.mode=='mouth' else 'male body below the joint (retainer)'}; "
          f"prints FLAT, no support, PLA")


if __name__ == "__main__":
    main()
