#!/usr/bin/env python3
"""leg_stl.py — export the SPIRAL TOWER leg as a SOLID binary STL, for slicer comparison ONLY.

Sweeps the same twisted-clover profile spiraltower.py prints:
    r(theta, z) = Rm + flute/2 * cos(lobes * (theta - twist_rate * z))
Rings up z (one per ~layer_h), each ring N points, side quads -> 2 tris, plus bottom + top caps.
The mesh is a closed SOLID column (not the hollow single-wall print) so a real slicer can decide
its own walls/infill/vase from the same geometry. Diagnostic artifact — never printed.

Usage: python3 leg_stl.py [--dia 64] [--lobes 4] [--flute 13.5] [--twist 48] [--height 40] --out leg.stl
"""
import argparse, math, struct


def radius(theta, z, Rm, lobes, flute, twist_rate):
    return Rm + flute * 0.5 * math.cos(lobes * (theta - twist_rate * z))


def build(dia, lobes, flute, twist, height, layer_h, N):
    Rm = dia / 2.0
    twist_rate = math.radians(twist) / height     # rad of profile phase per mm of height (matches generator)
    nrings = max(2, int(round(height / layer_h)) + 1)
    zs = [height * k / (nrings - 1) for k in range(nrings)]

    rings = []                                     # rings[i][j] = (x, y, z)
    for z in zs:
        ring = []
        for j in range(N):
            th = 2 * math.pi * j / N
            r = radius(th, z, Rm, lobes, flute, twist_rate)
            ring.append((r * math.cos(th), r * math.sin(th), z))
        rings.append(ring)

    tris = []
    # side surface: quad between ring i and i+1, points j and j+1 -> 2 triangles, wound outward (CCW from outside)
    for i in range(nrings - 1):
        lo, hi = rings[i], rings[i + 1]
        for j in range(N):
            k = (j + 1) % N
            tris.append((lo[j], lo[k], hi[k]))
            tris.append((lo[j], hi[k], hi[j]))
    # bottom cap: fan from centre, wound so normal points -z (outward = down)
    cb = (0.0, 0.0, zs[0])
    bot = rings[0]
    for j in range(N):
        k = (j + 1) % N
        tris.append((cb, bot[k], bot[j]))
    # top cap: fan from centre, wound so normal points +z (outward = up)
    ct = (0.0, 0.0, zs[-1])
    top = rings[-1]
    for j in range(N):
        k = (j + 1) % N
        tris.append((ct, top[j], top[k]))
    return tris


def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris):
    with open(path, "wb") as fh:
        fh.write(b"crackle leg_stl solid column - slicer comparison only".ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            nx, ny, nz = normal(a, b, c)
            fh.write(struct.pack("<3f", nx, ny, nz))
            for v in (a, b, c):
                fh.write(struct.pack("<3f", *v))
            fh.write(struct.pack("<H", 0))


def verify(path, tris):
    import os
    size = os.path.getsize(path)
    expect = 84 + 50 * len(tris)
    assert size == expect, f"filesize {size} != 84 + 50*{len(tris)} = {expect}"
    with open(path, "rb") as fh:
        head = fh.read(80)
        assert not head[:5].lower().startswith(b"solid"), "binary STL header must not begin with 'solid'"
        (count,) = struct.unpack("<I", fh.read(4))
        assert count == len(tris), f"header count {count} != {len(tris)}"
        degen = 0
        for _ in range(count):
            fh.read(12)                            # skip stored normal
            vs = [struct.unpack("<3f", fh.read(12)) for _ in range(3)]
            fh.read(2)
            n = normal(*vs)
            if n == (0.0, 0.0, 0.0):
                degen += 1
        assert degen == 0, f"{degen} degenerate (zero-area) triangles"
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dia", type=float, default=64.0)
    ap.add_argument("--lobes", type=int, default=4)
    ap.add_argument("--flute", type=float, default=13.5)
    ap.add_argument("--twist", type=float, default=48.0)
    ap.add_argument("--height", type=float, default=40.0)
    ap.add_argument("--layer-h", type=float, default=0.4)
    ap.add_argument("--points", type=int, default=160, help="points per ring (PPL in the generator)")
    ap.add_argument("--out", default="leg.stl")
    a = ap.parse_args()

    tris = build(a.dia, a.lobes, a.flute, a.twist, a.height, a.layer_h, a.points)
    write_binary_stl(a.out, tris)
    n = verify(a.out, tris)
    Rm = a.dia / 2.0
    print(f"{a.out}: {n} triangles, dia {a.dia:g} (r {Rm - a.flute/2:g}..{Rm + a.flute/2:g}) "
          f"lobes {a.lobes} flute {a.flute:g} twist {a.twist:g}deg height {a.height:g} — VERIFIED")


if __name__ == "__main__":
    main()
