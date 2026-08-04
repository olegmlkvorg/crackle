#!/usr/bin/env python3
"""icecage_pointyhex_force.py -- force every qa_stl check that judges icecage_pointyhex.stl.

A gate that has only ever seen a good file has not been shown to work. Each injection below is
ASSERTED to have landed -- the assertion prints, and the script aborts if a replace matched
nothing -- and only then is the gate run on the damaged copy. A no-op injection followed by a
clean PASS is a lie this project has already paid for twice today.

    python3 icecage_pointyhex_force.py <good.stl> <scratch dir>
"""
import math
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
QA = os.path.join(HERE, "tools", "qa_stl.py")
REC = 50


def load(p):
    with open(p, "rb") as f:
        hdr = f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        body = f.read()
    return hdr, n, [body[i * REC:(i + 1) * REC] for i in range(n)]


def save(p, hdr, recs):
    with open(p, "wb") as f:
        f.write(hdr)
        f.write(struct.pack("<I", len(recs)))
        for r in recs:
            f.write(r)


def rec_of(v0, v1, v2):
    ux, uy, uz = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
    vx, vy, vz = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return struct.pack("<12fH", nx / m, ny / m, nz / m,
                       v0[0], v0[1], v0[2], v1[0], v1[1], v1[2], v2[0], v2[1], v2[2], 0)


def box(x0, x1, y0, y1, z0, z1, inward=False):
    c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    q = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
         (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
         (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    if inward:
        q = [(a, c_, b) for (a, b, c_) in q]
    return [rec_of(c[a], c[b], c[d]) for (a, b, d) in q]


def gate(path, cls="closed"):
    r = subprocess.run([sys.executable, QA, path, "--class", cls, "--bed", "340"],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def assert_landed(label, ok, detail):
    print("  INJECTION %-14s %s  %s" % (label, "LANDED" if ok else "NO-OP", detail))
    if not ok:
        print("ABORT: injection %s matched nothing. A no-op forcing run reports a clean pass "
              "and proves nothing." % label)
        sys.exit(2)


def main():
    good, scratch = sys.argv[1], sys.argv[2]
    hdr, n, recs = load(good)
    gsize = os.path.getsize(good)
    print("baseline %s: %d bytes, %d triangles" % (os.path.basename(good), gsize, n))
    rc, out = gate(good)
    print("baseline gate rc=%d, last line: %s" % (rc, out.splitlines()[-1]))
    assert rc == 0, "baseline must pass before forcing means anything"
    results = []

    # 1 LAW -- one byte short of 84 + 50*ntris
    p = os.path.join(scratch, "force_law.stl")
    with open(good, "rb") as f:
        blob = f.read()
    with open(p, "wb") as f:
        f.write(blob[:-1])
    assert_landed("LAW", os.path.getsize(p) == gsize - 1,
                  "%d -> %d bytes, header still claims %d triangles" % (gsize, os.path.getsize(p), n))
    results.append(("LAW", gate(p)))

    # 2 HEADER -- make it read as an ascii STL
    p = os.path.join(scratch, "force_header.stl")
    save(p, b"solid" + hdr[5:], recs)
    h2 = open(p, "rb").read(80)
    assert_landed("HEADER", h2.startswith(b"solid") and not hdr.startswith(b"solid"),
                  "header %r -> %r" % (hdr[:12], h2[:12]))
    results.append(("HEADER", gate(p)))

    # 3 DEGENERATE -- collapse triangle 0 onto an edge
    p = os.path.join(scratch, "force_degen.stl")
    f0 = struct.unpack("<12fH", recs[0])
    bad = struct.pack("<12fH", *(list(f0[:9]) + list(f0[6:9]) + [0]))
    r2 = list(recs)
    r2[0] = bad
    save(p, hdr, r2)
    v1 = struct.unpack("<12fH", open(p, "rb").read(84 + REC)[84:])[6:9]
    v2 = struct.unpack("<12fH", open(p, "rb").read(84 + REC)[84:])[9:12]
    assert_landed("DEGENERATE", v1 == v2 and f0[6:9] != f0[9:12],
                  "tri 0 v1 %s now equals v2 (was %s)" % (str(v1)[:34], str(f0[9:12])[:34]))
    results.append(("DEGENERATE", gate(p)))

    # 4 WATERTIGHT -- delete one facet, leaving 3 unpaired edges
    p = os.path.join(scratch, "force_watertight.stl")
    save(p, hdr, recs[:-1])
    (n2,) = struct.unpack("<I", open(p, "rb").read(84)[80:])
    assert_landed("WATERTIGHT", n2 == n - 1 and os.path.getsize(p) == gsize - REC,
                  "%d -> %d triangles, %d -> %d bytes" % (n, n2, gsize, os.path.getsize(p)))
    results.append(("WATERTIGHT", gate(p)))

    # 5 PRINTABLE -- a 40x40x2 plate floating on the axis at z=150, far inboard of the wall
    p = os.path.join(scratch, "force_printable.stl")
    plate = box(-20.0, 20.0, -20.0, 20.0, 150.0, 152.0)
    save(p, hdr, recs + plate)
    (n3,) = struct.unpack("<I", open(p, "rb").read(84)[80:])
    zs = [struct.unpack("<12fH", r)[5] for r in plate]
    assert_landed("PRINTABLE", n3 == n + 12 and min(zs) == 150.0,
                  "+12 facets, plate at z=150..152, r<=28 against a 125.8 wall radius")
    results.append(("PRINTABLE", gate(p)))

    # 6 SEALED-VOID -- a hollow block ON THE BED: outer shell + inward-wound cavity surface.
    #   On the bed so its own floor is excluded and the cavity floor reads as buried, which
    #   leaves SEALED-VOID as the only check with anything to say.
    p = os.path.join(scratch, "force_sealed.stl")
    shell = box(-15.0, 15.0, -15.0, 15.0, 0.0, 30.0) + \
            box(-8.0, 8.0, -8.0, 8.0, 8.0, 22.0, inward=True)
    save(p, hdr, recs + shell)
    (n4,) = struct.unpack("<I", open(p, "rb").read(84)[80:])
    outn = struct.unpack("<12fH", shell[0])[:3]
    inn = struct.unpack("<12fH", shell[12])[:3]
    assert_landed("SEALED-VOID", n4 == n + 24 and outn[2] < 0 and inn[2] > 0,
                  "+24 facets; outer floor normal nz=%.1f, cavity floor normal nz=%.1f (inverted)"
                  % (outn[2], inn[2]))
    results.append(("SEALED-VOID", gate(p)))

    # 7 BED -- scale xy by 1.5 so the footprint clears the 340 limit
    p = os.path.join(scratch, "force_bed.stl")
    sc = []
    for r in recs:
        f = list(struct.unpack("<12fH", r))
        for k in (3, 6, 9):
            f[k] *= 1.5
            f[k + 1] *= 1.5
        sc.append(struct.pack("<12fH", *f))
    save(p, hdr, sc)
    xs = [struct.unpack("<12fH", r)[k] for r in sc for k in (3, 6, 9)]
    assert_landed("BED", max(xs) - min(xs) > 340.0,
                  "bbox X 251.6 -> %.1f mm against the 340 limit" % (max(xs) - min(xs)))
    results.append(("BED", gate(p)))

    print("\n-- did each forced check actually FAIL? --")
    bad = 0
    for name, (rc, out) in results:
        lines = [l for l in out.splitlines() if l.startswith("FAIL")]
        fired = any(l.split()[1] == name for l in lines)
        if not fired or rc == 0:
            bad += 1
        print("  %-12s rc=%d  %s" % (name, rc, "  |  ".join(lines) if lines else "NOTHING FAILED"))
    print("\n%s: %d of %d forced checks fired" % ("ALL GATES PROVEN ABLE TO FIRE" if bad == 0
                                                  else "NOT PROVEN", len(results) - bad, len(results)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
