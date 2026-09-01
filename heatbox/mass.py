#!/usr/bin/env python3
"""Solid volume and PC mass of each exported heatbox part, straight from the STL.

Mesh volume is the signed-tetrahedron sum over every facet — it needs no slicer and no
guess about perimeters, so it is the honest floor: what a 100%-dense part would weigh.
A slicer reports MORE than this when walls are thin enough to be all-perimeter, and less
only where infill hollows a solid region. Density 1.19 g/cm3 is Creality's figure for
Hyper PC (their listing, quoted in README.md).
"""
from pathlib import Path
import re
import sys

DENSITY = 1.19e-3          # g/mm3
OUT = Path(__file__).resolve().parent / "out"


def read_facets(path):
    """Yield each ASCII-STL facet as three (x, y, z) tuples."""
    nums = re.compile(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)")
    verts = []
    with path.open() as handle:
        for line in handle:
            hit = nums.search(line)
            if hit:
                verts.append(tuple(float(v) for v in hit.groups()))
                if len(verts) == 3:
                    yield verts
                    verts = []
    if verts:
        raise ValueError(f"{path.name}: trailing {len(verts)} vertices, file truncated")


def signed_volume(path):
    """Signed tetrahedron sum, facet count, and bounding-box extent.

    The sign is kept rather than folded away here so a test can see it: an outward-wound
    solid must come out POSITIVE, and a reversed winding is a real defect that abs()
    would silently paper over.
    """
    volume = 0.0
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    count = 0
    for a, b, c in read_facets(path):
        volume += (a[0] * (b[1] * c[2] - c[1] * b[2])
                   - a[1] * (b[0] * c[2] - c[0] * b[2])
                   + a[2] * (b[0] * c[1] - c[0] * b[1])) / 6.0
        for point in (a, b, c):
            for i in range(3):
                lo[i] = min(lo[i], point[i])
                hi[i] = max(hi[i], point[i])
        count += 1
    if not count:
        raise ValueError(f"{path.name}: no facets parsed")
    return volume, count, [hi[i] - lo[i] for i in range(3)]


def measure(path):
    volume, count, box = signed_volume(path)
    return abs(volume), count, box


def main(argv):
    paths = [Path(a) for a in argv[1:]] or sorted(OUT.glob("heatbox_*.stl"))
    if not paths:
        print("no STLs found", file=sys.stderr)
        return 2
    total = 0.0
    print(f"{'part':<10}{'facets':>8}{'volume cm3':>12}{'mass g':>9}   bounding box mm")
    for path in paths:
        volume, facets, box = measure(path)
        grams = volume * DENSITY
        # cap prints twice; every other part once
        copies = 2 if "_cap_" in path.name else 1
        total += grams * copies
        name = path.name.split("_")[1]
        dims = " x ".join(f"{d:.1f}" for d in box)
        star = " x2" if copies == 2 else ""
        print(f"{name:<10}{facets:>8}{volume/1000:>12.1f}{grams:>9.0f}{star:<3} {dims}")
    print(f"{'TOTAL':<10}{'':>8}{'':>12}{total:>9.0f} g solid  "
          f"(spool cost at 1 kg: {total/10:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
