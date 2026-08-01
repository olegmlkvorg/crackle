#!/usr/bin/env python3
"""qa_stl.py -- THE STL quality gate. stdlib only, no numpy.

Usage:
    python3 qa_stl.py part.stl [part2.stl ...] [--class closed|open] [--bed 340] [--allow-overhang 0]

Classes:
    closed (default)  formwork solids: LAW, HEADER, DEGENERATE, WATERTIGHT, PRINTABLE, BED
    open              vase surfaces:   LAW, HEADER, DEGENERATE, LEAN, BED
    vase-solid        closed solids fed to slicer VASE mode (e.g. leg.stl): as closed, but the
                      flat top/bottom caps never print (spiralize discards them), so instead of
                      PRINTABLE it checks SIDE-LEAN (lean of non-cap faces, |nz| < 0.95)

PRINTABLE tries the mesh AS-IS first; if that fails it retries FLIPPED (z -> maxz-z). A part that
only passes flipped PASSES with an explicit "print UPSIDE-DOWN" note (e.g. the platform wedges,
modeled in use orientation, print top-skin-down by design). A sealed cavity fails BOTH ways.

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
    faces = []   # (nz, centroid_z, centroid_r) per non-degenerate triangle
    tris3d = []  # (v0, v1, v2, cenx, ceny, cenz, nz) -- closed only, for the burial test
    edges = Counter() if cls in ("closed", "vase-solid") else None
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
        if cls == "closed":
            tris3d.append((v0, v1, v2, cenx, ceny, cenz, cz / m))

    # -- 3 DEGENERATE -------------------------------------------------------
    report("DEGENERATE", degen == 0, "%d zero-area triangles" % degen)

    # -- 4 WATERTIGHT (closed + vase-solid) -----------------------------------
    if cls in ("closed", "vase-solid"):
        unpaired = sum(1 for c in edges.values() if c != 2)
        report("WATERTIGHT", unpaired == 0,
               "%d non-paired edges (%d edges, verts rounded 3dp)"
               % (unpaired, len(edges)))

    # -- 5 LEAN (open) / SIDE-LEAN (vase-solid) --------------------------------
    if cls in ("open", "vase-solid"):
        cap_cut = 0.95 if cls == "vase-solid" else 1.1     # vase-solid: caps never print, exclude them
        max_lean = 0.0
        for nz, z, _r in faces:
            if z <= BED_Z or abs(nz) >= cap_cut:
                continue
            lean = math.degrees(math.asin(min(1.0, abs(nz))))
            if lean > max_lean:
                max_lean = lean
        name = "LEAN" if cls == "open" else "SIDE-LEAN"
        note = "" if cls == "open" else ", flat caps |nz|>=0.95 excluded (vase discards them)"
        report(name, max_lean <= LEAN_MAX_DEG,
               "max wall lean %.1f deg (limit %.0f, bed faces z<=%.1f excluded%s)"
               % (max_lean, LEAN_MAX_DEG, BED_Z, note))

    # -- 6 PRINTABLE (closed): as-is, then flipped; buried soup faces excluded --
    if cls == "closed":
        def spanning_idx(fs):
            wall_r = {}
            for _nz, z, r in fs:
                band = int(z // BAND_H)
                if r > wall_r.get(band, 0.0):
                    wall_r[band] = r
            return [i for i, (nz, z, r) in enumerate(fs)
                    if nz < DOWN_NZ and z > BED_Z
                    and r < wall_r[int(z // BAND_H)] - SPAN_MARGIN]

        def components():
            """Connected components of the soup (shared rounded verts join tris). Each sub-solid
            of an interpenetrating soup is its own component; interpenetration shares no verts."""
            parent = {}

            def find(a):
                while parent[a] != a:
                    parent[a] = parent[parent[a]]
                    a = parent[a]
                return a

            def union(a, b):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb

            keys = []
            for (v0, v1, v2, _cx, _cy, _cz, _nz) in tris3d:
                ks = [tuple(round(c, 3) for c in v) for v in (v0, v1, v2)]
                for k in ks:
                    if k not in parent:
                        parent[k] = k
                union(ks[0], ks[1]); union(ks[1], ks[2])
                keys.append(ks[0])
            return [find(k) for k in keys]            # component id per triangle

        comp = components() if tris3d else []

        def buried(idx):
            """Interpenetrating-soup semantics: a face is erased by the slicer union only if its
            just-outside point sits inside a DIFFERENT sub-solid's material (signed vertical-ray
            winding over OTHER components only; >=1 -> buried). Its own component is excluded, so
            a sealed enclosure cannot bury its own roof: that roof spans a hollow-intended void
            (a top skin over 0% infill = the failure) and stays an offender."""
            _v0, _v1, _v2, px, py, pz, fnz = tris3d[idx]
            pz += (0.2 if fnz > 0 else -0.2)          # step just OUTSIDE the face along its normal z
            mycomp = comp[idx]
            w = 0
            for j, (u0, u1, u2, _cx, _cy, _cz, unz) in enumerate(tris3d):
                if j == idx or comp[j] == mycomp or abs(unz) < 1e-9:
                    continue
                # cheap bbox reject in xy
                if px < min(u0[0], u1[0], u2[0]) or px > max(u0[0], u1[0], u2[0]):
                    continue
                if py < min(u0[1], u1[1], u2[1]) or py > max(u0[1], u1[1], u2[1]):
                    continue
                # 2D point-in-triangle (xy projection), then plane z above p?
                d1 = (px - u1[0]) * (u0[1] - u1[1]) - (u0[0] - u1[0]) * (py - u1[1])
                d2 = (px - u2[0]) * (u1[1] - u2[1]) - (u1[0] - u2[0]) * (py - u2[1])
                d3 = (px - u0[0]) * (u2[1] - u0[1]) - (u2[0] - u0[0]) * (py - u0[1])
                if not ((d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0)):
                    continue
                # plane z at (px, py)
                ax, ay, az = u0
                e1 = (u1[0] - ax, u1[1] - ay, u1[2] - az)
                e2 = (u2[0] - ax, u2[1] - ay, u2[2] - az)
                nx = e1[1] * e2[2] - e1[2] * e2[1]
                ny = e1[2] * e2[0] - e1[0] * e2[2]
                nzc = e1[0] * e2[1] - e1[1] * e2[0]
                if abs(nzc) < 1e-12:
                    continue
                zc = az - (nx * (px - ax) + ny * (py - ay)) / nzc
                if zc > pz:
                    w += 1 if unz > 0 else -1
            return w >= 1

        up_idx = spanning_idx(faces)
        flipped = [(-nz, maxz - z, r) for nz, z, r in faces]
        fl_idx = spanning_idx(flipped)
        # burial is orientation-independent; test each candidate once (skip if absurdly many)
        cand = set(up_idx) | set(fl_idx)
        buried_set = (set(i for i in cand if buried(i))
                      if len(cand) <= 3000 else set())
        up = [faces[i][1] for i in up_idx if i not in buried_set]
        fl = [i for i in fl_idx if i not in buried_set]
        nb = len(buried_set)
        note = (" (%d buried soup faces excluded: interpenetration, slicer erases them)" % nb
                if nb else "")
        if len(up) <= allow:
            report("PRINTABLE", True,
                   "%d spanning overhang faces (allow %d)%s" % (len(up), allow, note))
        elif len(fl) <= allow:
            report("PRINTABLE", True,
                   "%d spanning faces upright BUT %d flipped -> print UPSIDE-DOWN "
                   "(mesh is modeled in use orientation)%s" % (len(up), len(fl), note))
        else:
            report("PRINTABLE", False,
                   "%d spanning overhang faces upright, %d flipped (allow %d), "
                   "z %.1f..%.1f%s - inward floor/roof: unprintable in EITHER orientation "
                   "(sealed cavity)" % (len(up), len(fl), allow,
                                        min(up), max(up), note))

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
    ap.add_argument("--class", dest="cls", choices=("closed", "open", "vase-solid"),
                    default="closed",
                    help="closed = formwork solid (watertight + printable, tries flipped); "
                         "open = vase surface (lean); vase-solid = slicer-vase input solid "
                         "(watertight + side-lean, caps excluded). Default: closed")
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
