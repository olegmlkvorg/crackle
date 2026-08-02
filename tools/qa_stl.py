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
    fabric            print-in-place lattices of DISJOINT interlocked solids (chainmail). Splits
                      the soup into connected components (rings) and checks, PER COMPONENT:
                      COMP-WATERTIGHT (edge parity within each ring), OVERHANG (no downward face
                      nz < -0.707 above z=0.5 -- the global wallR span heuristic breaks on a lattice,
                      so fabric uses a direct downward-face steepness gate = the >=45deg no-bridge
                      rule), BED-ALL (every ring touches the bed), and CLEARANCE (point-to-triangle
                      min surface distance between every ring pair >= --clear-min). Reports ring count.

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


def _components(tris3d):
    """Connected components of the soup (shared rounded verts join tris). Returns a component-id
    per triangle. Disjoint sub-solids (a chainmail lattice's rings share no verts) come out as
    separate components. Same union-find the closed PRINTABLE check uses."""
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
    ids = [find(k) for k in keys]
    remap = {}
    return [remap.setdefault(c, len(remap)) for c in ids]


def _pt_tri_d2(p, a, b, c):
    """Squared distance from point p to triangle abc (Ericson, Real-Time Collision Detection)."""
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    ap = (p[0] - a[0], p[1] - a[1], p[2] - a[2])
    d1 = ab[0]*ap[0] + ab[1]*ap[1] + ab[2]*ap[2]
    d2 = ac[0]*ap[0] + ac[1]*ap[1] + ac[2]*ap[2]
    if d1 <= 0 and d2 <= 0:
        return ap[0]**2 + ap[1]**2 + ap[2]**2
    bp = (p[0] - b[0], p[1] - b[1], p[2] - b[2])
    d3 = ab[0]*bp[0] + ab[1]*bp[1] + ab[2]*bp[2]
    d4 = ac[0]*bp[0] + ac[1]*bp[1] + ac[2]*bp[2]
    if d3 >= 0 and d4 <= d3:
        return bp[0]**2 + bp[1]**2 + bp[2]**2
    vc = d1*d4 - d3*d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        q = (a[0] + v*ab[0], a[1] + v*ab[1], a[2] + v*ab[2])
        return (p[0]-q[0])**2 + (p[1]-q[1])**2 + (p[2]-q[2])**2
    cp = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
    d5 = ab[0]*cp[0] + ab[1]*cp[1] + ab[2]*cp[2]
    d6 = ac[0]*cp[0] + ac[1]*cp[1] + ac[2]*cp[2]
    if d6 >= 0 and d5 <= d6:
        return cp[0]**2 + cp[1]**2 + cp[2]**2
    vb = d5*d2 - d1*d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        q = (a[0] + w*ac[0], a[1] + w*ac[1], a[2] + w*ac[2])
        return (p[0]-q[0])**2 + (p[1]-q[1])**2 + (p[2]-q[2])**2
    va = d3*d6 - d5*d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        q = (b[0] + w*(c[0]-b[0]), b[1] + w*(c[1]-b[1]), b[2] + w*(c[2]-b[2]))
        return (p[0]-q[0])**2 + (p[1]-q[1])**2 + (p[2]-q[2])**2
    denom = 1.0 / (va + vb + vc)
    v = vb * denom
    w = vc * denom
    q = (a[0] + ab[0]*v + ac[0]*w, a[1] + ab[1]*v + ac[1]*w, a[2] + ab[2]*v + ac[2]*w)
    return (p[0]-q[0])**2 + (p[1]-q[1])**2 + (p[2]-q[2])**2


def _seg_seg_d2(p1, p2, q1, q2):
    """Squared min distance between segments p1p2 and q1q2 (Eberly clamp method)."""
    dpx, dpy, dpz = p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]
    dqx, dqy, dqz = q2[0]-q1[0], q2[1]-q1[1], q2[2]-q1[2]
    rx, ry, rz = p1[0]-q1[0], p1[1]-q1[1], p1[2]-q1[2]
    a = dpx*dpx + dpy*dpy + dpz*dpz
    e = dqx*dqx + dqy*dqy + dqz*dqz
    f = dqx*rx + dqy*ry + dqz*rz
    if a <= 1e-12 and e <= 1e-12:
        return rx*rx + ry*ry + rz*rz
    if a <= 1e-12:
        s = 0.0; t = min(1.0, max(0.0, f / e))
    else:
        c = dpx*rx + dpy*ry + dpz*rz
        if e <= 1e-12:
            t = 0.0; s = min(1.0, max(0.0, -c / a))
        else:
            b = dpx*dqx + dpy*dqy + dpz*dqz
            den = a*e - b*b
            s = min(1.0, max(0.0, (b*f - c*e) / den)) if den > 1e-12 else 0.0
            t = (b*s + f) / e
            if t < 0.0:
                t = 0.0; s = min(1.0, max(0.0, -c / a))
            elif t > 1.0:
                t = 1.0; s = min(1.0, max(0.0, (b - c) / a))
    cx = p1[0] + dpx*s - (q1[0] + dqx*t)
    cy = p1[1] + dpy*s - (q1[1] + dqy*t)
    cz = p1[2] + dpz*s - (q1[2] + dqz*t)
    return cx*cx + cy*cy + cz*cz


def _min_clearance(comp_tris):
    """Min surface-to-surface distance over every component pair: point-to-triangle both ways PLUS
    edge-to-edge (two skew tube surfaces can pass closest between edge interiors; vertex-face alone
    overstated 0.016 where the true minimum was 0.000 -- found adversarially 2026-08-02).
    comp_tris[k] = list of (v0,v1,v2) for component k. Returns (min_dist, (kA, kB))."""
    bbs = []
    for ct in comp_tris:
        xs = [v[0] for t in ct for v in t]
        ys = [v[1] for t in ct for v in t]
        zs = [v[2] for t in ct for v in t]
        bbs.append((min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    best2 = float("inf")
    pair = (None, None)
    n = len(comp_tris)
    for i in range(n):
        for j in range(i + 1, n):
            bi, bj = bbs[i], bbs[j]
            gx = max(0.0, bi[0]-bj[1], bj[0]-bi[1])
            gy = max(0.0, bi[2]-bj[3], bj[2]-bi[3])
            gz = max(0.0, bi[4]-bj[5], bj[4]-bi[5])
            if gx*gx + gy*gy + gz*gz > best2:
                continue
            A, B = comp_tris[i], comp_tris[j]
            # centroid + bounding-radius per tri, so only near-contact tri pairs pay full price
            def _meta(tris_):
                out = []
                for t in tris_:
                    cx = (t[0][0]+t[1][0]+t[2][0])/3.0
                    cy = (t[0][1]+t[1][1]+t[2][1])/3.0
                    cz = (t[0][2]+t[1][2]+t[2][2])/3.0
                    r2 = max((v[0]-cx)**2 + (v[1]-cy)**2 + (v[2]-cz)**2 for v in t)
                    out.append((cx, cy, cz, math.sqrt(r2)))
                return out
            MA, MB = _meta(A), _meta(B)
            for ia, ta in enumerate(A):
                ca = MA[ia]
                for ib, tb in enumerate(B):
                    cb = MB[ib]
                    dc = math.sqrt((ca[0]-cb[0])**2 + (ca[1]-cb[1])**2 + (ca[2]-cb[2])**2)
                    if dc - ca[3] - cb[3] > math.sqrt(best2):
                        continue
                    for p in ta:                          # vertex -> face, both directions
                        d = _pt_tri_d2(p, tb[0], tb[1], tb[2])
                        if d < best2: best2 = d; pair = (i, j)
                    for p in tb:
                        d = _pt_tri_d2(p, ta[0], ta[1], ta[2])
                        if d < best2: best2 = d; pair = (i, j)
                    ea = ((ta[0], ta[1]), (ta[1], ta[2]), (ta[2], ta[0]))
                    eb = ((tb[0], tb[1]), (tb[1], tb[2]), (tb[2], tb[0]))
                    for p1, p2 in ea:                     # edge -> edge (the skew-tube case)
                        for q1, q2 in eb:
                            d = _seg_seg_d2(p1, p2, q1, q2)
                            if d < best2: best2 = d; pair = (i, j)
    return math.sqrt(best2), pair


def run_file(path, cls, bed, allow, clear_min):
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
        if cls in ("closed", "fabric"):
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

    # -- FABRIC: per-component watertight, overhang steepness, bed-all, clearance ----
    if cls == "fabric":
        comp = _components(tris3d) if tris3d else []
        ncomp = (max(comp) + 1) if comp else 0
        # gather per-component triangles + edges + min-z
        comp_tris = [[] for _ in range(ncomp)]
        comp_edges = [Counter() for _ in range(ncomp)]
        comp_minz = [float("inf")] * ncomp
        for idx, (v0, v1, v2, _cx, _cy, _cz, _nz) in enumerate(tris3d):
            k = comp[idx]
            comp_tris[k].append((v0, v1, v2))
            vs = (tuple(round(c, 3) for c in v0),
                  tuple(round(c, 3) for c in v1),
                  tuple(round(c, 3) for c in v2))
            for i in range(3):
                a, b = vs[i], vs[(i + 1) % 3]
                comp_edges[k][(a, b) if a <= b else (b, a)] += 1
            for v in (v0, v1, v2):
                if v[2] < comp_minz[k]:
                    comp_minz[k] = v[2]

        report("COMPONENTS", ncomp > 0, "%d disjoint components (rings)" % ncomp)

        unpaired = sum(1 for ce in comp_edges for c in ce.values() if c != 2)
        bad_comp = sum(1 for ce in comp_edges if any(c != 2 for c in ce.values()))
        report("COMP-WATERTIGHT", unpaired == 0,
               "%d non-paired edges across %d components (%d components not watertight)"
               % (unpaired, ncomp, bad_comp))

        # OVERHANG: direct downward-face steepness (no wallR span heuristic -- it breaks on lattices)
        worst_ang = 90.0
        n_over = 0
        for _nz, z, _r in faces:
            if z <= BED_Z or _nz >= DOWN_NZ:
                continue
            n_over += 1
            ang = math.degrees(math.acos(min(1.0, abs(_nz))))
            if ang < worst_ang:
                worst_ang = ang
        # also report the steepness of the shallowest downward face regardless of the -0.707 gate
        shallow = 90.0
        for _nz, z, _r in faces:
            if z <= BED_Z or _nz >= 0:
                continue
            ang = math.degrees(math.acos(min(1.0, abs(_nz))))
            if ang < shallow:
                shallow = ang
        report("OVERHANG", n_over == 0,
               "%d downward faces shallower than 45deg above z=%.1f; shallowest downward face "
               "overall = %.1f deg from horizontal" % (n_over, BED_Z, shallow))

        on_bed = sum(1 for mz in comp_minz if mz <= BED_Z)
        report("BED-ALL", on_bed == ncomp,
               "%d of %d components touch the bed (min-z <= %.1f)" % (on_bed, ncomp, BED_Z))

        if ncomp >= 2:
            clr, pr = _min_clearance(comp_tris)
            report("CLEARANCE", clr >= clear_min,
                   "min pairwise surface distance %.3f mm (limit %.2f)%s"
                   % (clr, clear_min,
                      "  worst pair components %s<->%s" % pr if pr[0] is not None else ""))
        else:
            report("CLEARANCE", False, "only %d component -- a fabric needs >=2 rings" % ncomp)

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
    ap.add_argument("--class", dest="cls",
                    choices=("closed", "open", "vase-solid", "fabric"),
                    default="closed",
                    help="closed = formwork solid (watertight + printable, tries flipped); "
                         "open = vase surface (lean); vase-solid = slicer-vase input solid "
                         "(watertight + side-lean, caps excluded); fabric = print-in-place lattice "
                         "of disjoint interlocked rings (per-component watertight, overhang, "
                         "bed-all, clearance). Default: closed")
    ap.add_argument("--bed", type=float, default=340.0,
                    help="max bbox X and Y in mm (default 340)")
    ap.add_argument("--allow-overhang", type=int, default=0,
                    help="spanning overhang faces tolerated (default 0)")
    ap.add_argument("--clear-min", type=float, default=0.45,
                    help="fabric: min pairwise surface clearance in mm (default 0.45)")
    args = ap.parse_args()

    failed = 0
    for path in args.stl:
        if not run_file(path, args.cls, args.bed, args.allow_overhang, args.clear_min):
            failed += 1
    n = len(args.stl)
    if failed:
        print("FAIL qa_stl: %d of %d file(s) failed" % (failed, n))
        sys.exit(1)
    print("PASS qa_stl: %d file(s), all checks green" % n)
    sys.exit(0)


if __name__ == "__main__":
    main()
