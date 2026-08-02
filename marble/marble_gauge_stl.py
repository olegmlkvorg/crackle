#!/usr/bin/env python3
"""MARBLE GAUGE STL -- the part to print FIRST, before any sorting chute is worth making.

The sorting chute works by setting the rail crest between two marble sizes. That is only useful if
you know what your marbles actually measure, and we do not: the kit assumes O16 because that is
the common size, but nobody has put callipers on Oleg's. Guessing here is not a small error, it is
the whole mechanism, so the gauge comes first.

A chain of graded rings. Drop a marble through from the top: it falls through every ring larger
than it and stops on the first one smaller. The last ring it passes is its size.

HOLE SHRINK IS BUILT IN. A printed hole comes out about 0.25 mm under the model on these machines
(the Creality vase-mode coin empiric), so every ring is MODELLED 0.25 mm oversize and the label is
the size it should measure once printed. That compensation is itself unproven on sliced round
holes, so the first thing to do with the printed gauge is put callipers on one ring and check the
label. If it is off, the offset is wrong and everything downstream of it moves.

Built as a chain of overlapping closed rings rather than a plate with holes bored in it. Each ring
is watertight on its own, which is what the slicer and the gate both want, and it needs no
triangulated face full of holes.

NO PRINTED NUMBERS ON IT, deliberately. Raised digits were tried and cut: the capsule ribs sit half
buried in the top face, which is self intersecting geometry, and qa_stl was right to reject it.
The chain grades monotonically instead, so the narrow end IS the small end and position is the
label. The size list is printed by this generator and belongs beside the part.

Prints FLAT on the bed with no support: every hole is a vertical through channel and the digits
stand proud of the top face.

Usage: python3 marble_gauge_stl.py [--min 12] [--max 20] [--step 1] [--out marble_gauge.stl]
"""
import argparse, math, os, struct

import marble_common as mc

WALL   = 4.0     # ring wall: thick enough that a marble resting on it does not splay it
THICK  = 5.0     # ring height. Deep enough to be a real gauge, shallow enough to stay flat
OVERLAP = 3.0    # how far neighbouring rings interpenetrate, so the chain is one rigid object
BED    = 340.0


def _normal(a, b, c):
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    m = math.sqrt(nx*nx+ny*ny+nz*nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx/m, ny/m, nz/m)


def ring_solid(cx, r_in, r_out, z0, z1, n=72):
    """Closed annular prism: outer wall, bore wall, top and bottom annuli."""
    tris = []
    out = [(cx + r_out*math.cos(2*math.pi*k/n), r_out*math.sin(2*math.pi*k/n)) for k in range(n)]
    inn = [(cx + r_in*math.cos(2*math.pi*k/n), r_in*math.sin(2*math.pi*k/n)) for k in range(n)]
    for k in range(n):
        j = (k + 1) % n
        O0, O1 = (*out[k], z0), (*out[j], z0)
        O0h, O1h = (*out[k], z1), (*out[j], z1)
        I0, I1 = (*inn[k], z0), (*inn[j], z0)
        I0h, I1h = (*inn[k], z1), (*inn[j], z1)
        tris.append((O0, O1, O1h)); tris.append((O0, O1h, O0h))     # outer wall
        tris.append((I0, I1h, I1)); tris.append((I0, I0h, I1h))     # bore wall
        tris.append((O0, I0, I1)); tris.append((O0, I1, O1))        # bottom annulus
        tris.append((O0h, O1h, I1h)); tris.append((O0h, I1h, I0h))  # top annulus
    return tris


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min", type=float, default=12.0, help="smallest labelled size mm")
    ap.add_argument("--max", type=float, default=20.0, help="largest labelled size mm")
    ap.add_argument("--step", type=float, default=1.0, help="grading step mm")
    ap.add_argument("--out", default="marble_gauge.stl")
    a = ap.parse_args()

    assert a.max > a.min and a.step > 0, "--max must exceed --min and --step must be positive"
    sizes = []
    d = a.min
    while d <= a.max + 1e-9:
        sizes.append(round(d, 2))
        d += a.step

    tris = []
    cx = 0.0
    centres = []
    for i, dia in enumerate(sizes):
        r_in = (dia + mc.HOLE_SHRINK) / 2.0        # model oversize so the PRINTED hole is `dia`
        r_out = r_in + WALL
        if i:
            prev_out = (sizes[i-1] + mc.HOLE_SHRINK) / 2.0 + WALL
            cx += prev_out + r_out - OVERLAP
        centres.append((cx, r_in, r_out))
        tris += ring_solid(cx, r_in, r_out, 0.0, THICK)

    with open(a.out, "wb") as f:
        f.write(b"crackle marble_gauge - graded ring chain, print this first".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<3f", *_normal(*t)))
            for v in t:
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))

    # ---- self-verify: re-read and MEASURE ----
    size = os.path.getsize(a.out)
    with open(a.out, "rb") as f:
        f.read(80); (n,) = struct.unpack("<I", f.read(4))
        V = []
        for _ in range(n):
            f.read(12)
            V += [struct.unpack("<3f", f.read(12)) for _ in range(3)]
            f.read(2)
    xs = [v[0] for v in V]; ys = [v[1] for v in V]; zs = [v[2] for v in V]
    length, width, height = max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)

    # measure each bore off the mesh: verts at mid height near that ring's centre
    meas = []
    for cxi, r_in, r_out in centres:
        near = [v for v in V if v[2] < 0.01 and abs(v[0]-cxi) < r_out + 0.5]
        rr = [math.hypot(v[0]-cxi, v[1]) for v in near]
        on = [r for r in rr if abs(r - r_in) < 0.2]
        meas.append(2*sum(on)/len(on) if on else float("nan"))
    worst = max(abs(m - (s + mc.HOLE_SHRINK)) for m, s in zip(meas, sizes))
    gaps = [centres[i+1][0] - centres[i][0] - centres[i][2] - centres[i+1][2]
            for i in range(len(centres)-1)]

    print(f"{a.out}: {n} tris, {size}B | {len(sizes)} rings O{a.min:g} to O{a.max:g} step {a.step:g}, "
          f"chain {length:.0f} x {width:.0f} x {height:.1f} mm, prints FLAT")
    print(f"  every bore modelled +{mc.HOLE_SHRINK:g} so the PRINTED hole matches its label")
    print("  narrow end first, ring by ring: " + "  ".join(f"O{s:g}" for s in sizes))

    checks = [
        ("bores measured", worst < 0.05,
         f"worst emitted bore is {worst:.3f}mm off its modelled size"),
        ("rings connect", all(g < 0 for g in gaps),
         f"largest neighbour gap {max(gaps):+.1f}mm (negative = they overlap into one object)"),
        ("bed fit", length <= BED and width <= BED, f"{length:.0f} x {width:.0f} vs {BED:.0f}"),
        ("covers the kit marble", a.min <= mc.MARBLE_D <= a.max,
         f"kit assumes O{mc.MARBLE_D:g}, gauge spans O{a.min:g} to O{a.max:g}"),
        ("step beats the sorter", a.step >= mc.sort_min_separation(),
         f"grading {a.step:g}mm vs the {mc.sort_min_separation():.2f}mm the sorter needs between "
         f"two sizes: a finer gauge than that would promise a sort we cannot print"),
    ]
    ok = True
    for name, good, msg in checks:
        print("  %s %-24s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    if not ok:
        os.replace(a.out, a.out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined")
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS  (print flat, then CALLIPER one ring against its label before "
          "trusting any sorting chute)")


if __name__ == "__main__":
    main()
