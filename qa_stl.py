#!/usr/bin/env python3
"""qa_stl.py -- THE STL quality gate. stdlib only, no numpy.

Usage:
    python3 qa_stl.py part.stl [part2.stl ...] [--class closed|open] [--bed 340] [--allow-overhang 0]

Classes:
    closed (default)  formwork solids: LAW, HEADER, DEGENERATE, WATERTIGHT, PRINTABLE, BED
    open              vase surfaces:   LAW, HEADER, DEGENERATE, LEAN, BED

Exit 0 with a PASS summary if every check on every file passes; exit 1 on any FAIL.

Checks:
    1 LAW         filesize == 84 + 50*ntris (ntris read from the header)
    2 HEADER      binary STL must not start b"solid"
    3 DEGENERATE  0 zero-area triangles (|cross| < 1e-9)
    4 WATERTIGHT  (closed) every undirected edge shared by exactly 2 triangles, verts rounded 3dp
    5 LEAN        (open) max wall lean from vertical <= 55 deg, bed faces (z <= 0.5) excluded
    6 PRINTABLE   (closed) 0 REAL spanning overhangs: recomputed unit facet normal nz < -0.707
                  AND centroid z > 0.5 (not the bed) AND centroid r < wallR(5mm z-band) - 6.0
                  (spans inward = a floor/roof; a ~1mm raised bead at the wall bridges fine).
                  watertight != printable: a sealed cavity with a flat roof cannot print.
    7 BED         bbox X and Y extents <= --bed (default 340)

Facet normals are recomputed from vertex winding; stored normals are not trusted.
"""
import argparse
import math
import os
import struct
import sys
from collections import Counter

DOWN_NZ = -0.707        # unit-normal nz below this = downward-facing
BED_Z = 0.5             # mm; centroid at/below this sits on the bed
SPAN_MARGIN = 6.0       # mm inside the band wall radius = a real span, not a wall bead
BAND_H = 5.0            # mm z-band height for the wall-radius profile
LEAN_MAX_DEG = 55.0     # vase-printable ceiling for wall lean from vertical


def run_file(path, cls, bed, allow):
    """Run all checks for one file. Returns True if every check passed."""
    print("== %s [%s] ==" % (path, cls))
    fails = [0]

    def report(name, ok, msg):
        if not ok:
            fails[0] += 1
        print("%s %-10s %s" % ("PASS" if ok else "FAIL", name, msg))

    # -- 1 LAW ------------------------------------------------------------
    try:
        size = os.path.getsize(path)
    except OSError as e:
        report("LAW", False, "cannot stat file: %s" % e)
        return False
    if size < 84:
        report("LAW", False,
               "file is %d bytes, below the 84-byte binary STL minimum" % size)
        print("SKIP remaining checks: structure unreadable")
        return False
    with open(path, "rb") as f:
        hdr = f.read(80)
        (ntris,) = struct.unpack("<I", f.read(4))
        body = f.read()
    expect = 84 + 50 * ntris
    law_ok = size == expect
    report("LAW", law_ok, "filesize %d %s 84 + 50*%d (= %d)"
           % (size, "==" if law_ok else "!=", ntris, expect))
    if not law_ok:
        print("SKIP remaining checks: byte layout untrustworthy")
        return False

    # -- 2 HEADER ---------------------------------------------------------
    hdr_ok = not hdr.startswith(b"solid")
    report("HEADER", hdr_ok,
           "binary header ok" if hdr_ok
           else "header starts b'solid' (reads as ascii STL)")

    # -- single parse pass --------------------------------------------------
    degen = 0
    faces = []  # (nz, centroid_z, centroid_r) per non-degenerate triangle
    edges = Counter() if cls == "closed" else None
    minx = miny = minz = float("inf")
    maxx = maxy = maxz = float("-inf")
    for rec in struct.iter_unpack("<12fH", body):
        v0 = rec[3:6]
        v1 = rec[6:9]
        v2 = rec[9:12]
        for x, y, z in (v0, v1, v2):
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y
            if z < minz: minz = z
            if z > maxz: maxz = z
        if edges is not None:
            vs = (tuple(round(c, 3) for c in v0),
                  tuple(round(c, 3) for c in v1),
                  tuple(round(c, 3) for c in v2))
            for i in range(3):
                a, b = vs[i], vs[(i + 1) % 3]
                edges[(a, b) if a <= b else (b, a)] += 1
        e1x, e1y, e1z = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
        e2x, e2y, e2z = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
        cx = e1y * e2z - e1z * e2y
        cy = e1z * e2x - e1x * e2z
        cz = e1x * e2y - e1y * e2x
        m = math.sqrt(cx * cx + cy * cy + cz * cz)
        if m < 1e-9:
            degen += 1
            continue
        cenx = (v0[0] + v1[0] + v2[0]) / 3.0
        ceny = (v0[1] + v1[1] + v2[1]) / 3.0
        cenz = (v0[2] + v1[2] + v2[2]) / 3.0
        faces.append((cz / m, cenz, math.hypot(cenx, ceny)))

    # -- 3 DEGENERATE -------------------------------------------------------
    report("DEGENERATE", degen == 0, "%d zero-area triangles" % degen)

    # -- 4 WATERTIGHT (closed) ----------------------------------------------
    if cls == "closed":
        unpaired = sum(1 for c in edges.values() if c != 2)
        report("WATERTIGHT", unpaired == 0,
               "%d non-paired edges (%d edges, verts rounded 3dp)"
               % (unpaired, len(edges)))

    # -- 5 LEAN (open) ------------------------------------------------------
    if cls == "open":
        max_lean = 0.0
        for nz, z, _r in faces:
            if z <= BED_Z:
                continue
            lean = math.degrees(math.asin(min(1.0, abs(nz))))
            if lean > max_lean:
                max_lean = lean
        report("LEAN", max_lean <= LEAN_MAX_DEG,
               "max wall lean %.1f deg (limit %.0f, bed faces z<=%.1f excluded)"
               % (max_lean, LEAN_MAX_DEG, BED_Z))

    # -- 6 PRINTABLE (closed) -----------------------------------------------
    if cls == "closed":
        wall_r = {}
        for _nz, z, r in faces:
            band = int(z // BAND_H)
            if r > wall_r.get(band, 0.0):
                wall_r[band] = r
        offenders = [z for nz, z, r in faces
                     if nz < DOWN_NZ and z > BED_Z
                     and r < wall_r[int(z // BAND_H)] - SPAN_MARGIN]
        count = len(offenders)
        ok = count <= allow
        zspan = (", z %.1f..%.1f" % (min(offenders), max(offenders))
                 if offenders else "")
        report("PRINTABLE", ok,
               "%d spanning overhang faces (allow %d)%s%s"
               % (count, allow, zspan,
                  "" if ok else
                  " - inward floor/roof: unprintable inside a sealed shell"))

    # -- 7 BED ----------------------------------------------------------------
    if minx == float("inf"):
        report("BED", False, "no triangles, no bbox")
    else:
        dx, dy, dz = maxx - minx, maxy - miny, maxz - minz
        report("BED", dx <= bed and dy <= bed,
               "bbox %.1f x %.1f x %.1f mm (X,Y limit %g)" % (dx, dy, dz, bed))

    return fails[0] == 0


def main():
    ap = argparse.ArgumentParser(
        description="STL quality gate: LAW, HEADER, DEGENERATE, "
                    "WATERTIGHT/LEAN, PRINTABLE, BED. Exit 1 on any FAIL.")
    ap.add_argument("stl", nargs="+", help="binary STL file(s) to check")
    ap.add_argument("--class", dest="cls", choices=("closed", "open"),
                    default="closed",
                    help="closed = formwork solid (watertight + printable); "
                         "open = vase surface (lean). Default: closed")
    ap.add_argument("--bed", type=float, default=340.0,
                    help="max bbox X and Y in mm (default 340)")
    ap.add_argument("--allow-overhang", type=int, default=0,
                    help="spanning overhang faces tolerated (default 0)")
    args = ap.parse_args()

    failed = 0
    for path in args.stl:
        if not run_file(path, args.cls, args.bed, args.allow_overhang):
            failed += 1
    n = len(args.stl)
    if failed:
        print("FAIL qa_stl: %d of %d file(s) failed" % (failed, n))
        sys.exit(1)
    print("PASS qa_stl: %d file(s), all checks green" % n)
    sys.exit(0)


if __name__ == "__main__":
    main()
