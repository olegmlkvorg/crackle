#!/usr/bin/env python3
"""Generate the tiny synthetic fixtures that prove qa_stl.py's checks can fire.

box.stl             good closed 20x20x20 box (control: must PASS --class closed)
bad_law.stl         box truncated by 10 bytes            -> LAW fires
bad_header.stl      box with a header starting b"solid"  -> HEADER fires
bad_degenerate.stl  box plus one zero-area triangle      -> DEGENERATE fires
bad_watertight.stl  box with one triangle removed        -> WATERTIGHT fires
bad_bed.stl         400mm-wide box                       -> BED fires
bad_lean.stl        open pyramid shell, walls ~76 deg    -> LEAN fires (--class open)
"""
import math
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))


def normal(a, b, c):
    e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    n = (e1[1] * e2[2] - e1[2] * e2[1],
         e1[2] * e2[0] - e1[0] * e2[2],
         e1[0] * e2[1] - e1[1] * e2[0])
    m = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (n[0] / m, n[1] / m, n[2] / m)


def write_stl(path, tris, header=b"qa_stl synthetic fixture"):
    with open(path, "wb") as f:
        f.write(header.ljust(80, b"\0")[:80])
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            nx, ny, nz = normal(a, b, c)
            f.write(struct.pack("<12fH", nx, ny, nz, *a, *b, *c, 0))
    return path


def box(x0, x1, y0, y1, z0, z1):
    """Closed box, 12 triangles, outward winding enforced by construction."""
    def quad(a, b, c, d, out):
        t1, t2 = (a, b, c), (a, c, d)
        n = normal(*t1)
        if n[0] * out[0] + n[1] * out[1] + n[2] * out[2] < 0:
            t1, t2 = (a, c, b), (a, d, c)
        return [t1, t2]

    c000, c100 = (x0, y0, z0), (x1, y0, z0)
    c110, c010 = (x1, y1, z0), (x0, y1, z0)
    c001, c101 = (x0, y0, z1), (x1, y0, z1)
    c111, c011 = (x1, y1, z1), (x0, y1, z1)
    tris = []
    tris += quad(c000, c100, c110, c010, (0, 0, -1))
    tris += quad(c001, c101, c111, c011, (0, 0, 1))
    tris += quad(c000, c100, c101, c001, (0, -1, 0))
    tris += quad(c010, c110, c111, c011, (0, 1, 0))
    tris += quad(c000, c010, c011, c001, (-1, 0, 0))
    tris += quad(c100, c110, c111, c101, (1, 0, 0))
    return tris


def main():
    good = box(-10, 10, -10, 10, 0, 20)

    # control: must PASS --class closed
    write_stl(os.path.join(HERE, "box.stl"), good)

    # (a) LAW: truncate 10 bytes off the good box
    with open(os.path.join(HERE, "box.stl"), "rb") as f:
        data = f.read()
    with open(os.path.join(HERE, "bad_law.stl"), "wb") as f:
        f.write(data[:-10])

    # (d) HEADER: ascii-style header
    write_stl(os.path.join(HERE, "bad_header.stl"), good,
              header=b"solid qa_stl fixture, bad on purpose")

    # (c) DEGENERATE: one zero-area triangle appended
    corner = (-10.0, -10.0, 0.0)
    write_stl(os.path.join(HERE, "bad_degenerate.stl"),
              good + [(corner, corner, corner)])

    # (b) WATERTIGHT: drop one triangle (header count matches, LAW still holds)
    write_stl(os.path.join(HERE, "bad_watertight.stl"), good[:-1])

    # (e) BED: 400mm wide
    write_stl(os.path.join(HERE, "bad_bed.stl"), box(-200, 200, -10, 10, 0, 20))

    # (f) LEAN: open pyramid shell, 40mm base rising only 5mm -> ~76 deg walls
    apex = (0.0, 0.0, 5.0)
    b = [(-20.0, -20.0, 0.0), (20.0, -20.0, 0.0),
         (20.0, 20.0, 0.0), (-20.0, 20.0, 0.0)]
    write_stl(os.path.join(HERE, "bad_lean.stl"),
              [(b[i], b[(i + 1) % 4], apex) for i in range(4)])

    print("fixtures written to", HERE)


if __name__ == "__main__":
    main()
