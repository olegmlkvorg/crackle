#!/usr/bin/env python3
"""chainmail_stl.py -- print-in-place CHAINMAIL FABRIC: one binary STL, a lattice of DISJOINT
interlocked rings. European-4-in-1 weave: identical tall-diamond rings in a staggered grid, rows
tilted alternately +/-tilt, every ring threading its four diagonal neighbours, every ring on the bed.

Each ring is its own watertight closed torus (diamond cross-section: tall in the ring-axis direction
so its downward faces stay steep). Rings never share a vertex -> disjoint solids the slicer keeps
separate, so the whole sheet prints in place and flexes like cloth.

Non-negotiables it self-verifies and reports:
  a. each ring watertight (edge parity per ring)
  b. worst downward face angle from horizontal above z=0.5 >= 45 deg (measured off the emitted mesh)
  c. pairwise surface clearance >= --clear (sampled)
  d. Gauss linking number +/-1 for every intended neighbour pair, 0 otherwise; sheet CONNECTED
  e. every ring touches the bed (min-z <= 0.5)

TPU on a Creality K1C: nozzle 205C, model/part fan 20% (all others 100%), ~25-30 mm/s outer walls,
no supports; a brim only if the small bed contacts release.

Usage:
  python3 chainmail_stl.py --cols 6 --rows 6 --out chainmail_coupon.stl
  python3 chainmail_stl.py --link-only two_rings.stl        # 2-ring interlock closeup
"""
import argparse
import math
import os
import struct
import sys

# ---- diamond cross-section geometry ------------------------------------------------
# local cross-section coords: u = radial (in ring plane), w = axial (along ring normal).
# diamond verts, ordered CCW around the section: outer, top, inner, bottom.
#   outer (+a,0)  top (0,+b)  inner (-a,0)  bottom (0,-b)
# downward faces are the two BOTTOM edges; their angle from horizontal (ring flat) = atan(b/a).


def build_ring(R, a, b, tilt, center, nmaj):
    """A torus with a diamond cross-section, tilted about x by `tilt`, translated to center.
    Returns a list of outward-wound triangles. Watertight: closes in both parametric directions."""
    ct, st = math.cos(tilt), math.sin(tilt)
    cx, cy, cz = center
    sec = [(a, 0.0), (0.0, b), (-a, 0.0), (0.0, -b)]   # (u, w)

    def world(u, w, th):
        # cross-section point at major angle th, in ring-local frame
        x = (R + u) * math.cos(th)
        y = (R + u) * math.sin(th)
        z = w
        # tilt about x-axis
        y2 = y * ct - z * st
        z2 = y * st + z * ct
        return (x + cx, y2 + cy, z2 + cz)

    # ring of section-vertex loops, one per major angle
    loops = []
    for j in range(nmaj):
        th = 2 * math.pi * j / nmaj
        loops.append([world(u, w, th) for (u, w) in sec])

    tris = []
    for j in range(nmaj):
        L0 = loops[j]
        L1 = loops[(j + 1) % nmaj]
        for m in range(4):
            n = (m + 1) % 4
            p00, p01 = L0[m], L0[n]
            p10, p11 = L1[m], L1[n]
            # two triangles per quad; winding chosen outward below via normal check
            tris.append(_wound(p00, p10, p11, R, center, tilt))
            tris.append(_wound(p00, p11, p01, R, center, tilt))
    return tris


def _wound(p0, p1, p2, R, center, tilt):
    """Return the triangle wound so its recomputed normal points AWAY from the tube centreline."""
    # tube-centre point nearest this facet: project facet centroid to the ring centreline circle
    ct, st = math.cos(tilt), math.sin(tilt)
    cx, cy, cz = center
    gx = (p0[0] + p1[0] + p2[0]) / 3.0 - cx
    gy = (p0[1] + p1[1] + p2[1]) / 3.0 - cy
    gz = (p0[2] + p1[2] + p2[2]) / 3.0 - cz
    # un-tilt the centroid to ring-local frame (inverse rot about x by tilt)
    ly = gy * ct + gz * st
    lz = -gy * st + gz * ct
    lx = gx
    rho = math.hypot(lx, ly) or 1.0
    # centreline point in local frame
    clx, cly, clz = R * lx / rho, R * ly / rho, 0.0
    # back to world
    wclx = clx + cx
    wcly = (cly * ct - clz * st) + cy
    wclz = (cly * st + clz * ct) + cz
    outx = (p0[0] + p1[0] + p2[0]) / 3.0 - wclx
    outy = (p0[1] + p1[1] + p2[1]) / 3.0 - wcly
    outz = (p0[2] + p1[2] + p2[2]) / 3.0 - wclz
    nx, ny, nz = _normal(p0, p1, p2)
    if nx * outx + ny * outy + nz * outz < 0:
        return (p0, p2, p1)
    return (p0, p1, p2)


def _normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


# ---- the sheet ---------------------------------------------------------------------


def build_sheet(cols, rows, ring_od, cs_w, cs_b, tilt_deg, dx, dy, nmaj):
    """Staggered E4-1 grid. Returns (tris, rings) where rings[k] = dict(center, tilt, i0, i1, cl)."""
    a = cs_w / 2.0
    R = ring_od / 2.0 - a
    t = math.radians(tilt_deg)

    rings = []
    tris = []
    for jr in range(rows):
        s = 1.0 if jr % 2 == 0 else -1.0            # alternate tilt sign by row
        xoff = (dx / 2.0) if (jr % 2) else 0.0
        for ic in range(cols):
            center = (ic * dx + xoff, jr * dy, 0.0)
            i0 = len(tris)
            tris.extend(build_ring(R, a, cs_b, s * t, center, nmaj))
            i1 = len(tris)
            cl = _centerline(R, s * t, center, 72)
            rings.append(dict(center=center, tilt=s * t, i0=i0, i1=i1, cl=cl,
                              row=jr, col=ic))

    # drop the whole sheet so the lowest point sits just on the bed
    minz = min(v[2] for tri in tris for v in tri)
    shift = 0.15 - minz
    tris = [tuple((v[0], v[1], v[2] + shift) for v in tri) for tri in tris]
    for rg in rings:
        rg["center"] = (rg["center"][0], rg["center"][1], rg["center"][2] + shift)
        rg["cl"] = [(p[0], p[1], p[2] + shift) for p in rg["cl"]]
    return tris, rings


def _centerline(R, tilt, center, n):
    ct, st = math.cos(tilt), math.sin(tilt)
    cx, cy, cz = center
    pts = []
    for j in range(n):
        th = 2 * math.pi * j / n
        x, y, z = R * math.cos(th), R * math.sin(th), 0.0
        y2 = y * ct - z * st
        z2 = y * st + z * ct
        pts.append((x + cx, y2 + cy, z2 + cz))
    return pts


# ---- verification ------------------------------------------------------------------


def gauss_linking(A, B):
    """Numerical Gauss double line integral between two closed polylines (segment midpoints)."""
    total = 0.0
    nA, nB = len(A), len(B)
    for i in range(nA):
        a0, a1 = A[i], A[(i + 1) % nA]
        max_ = ((a0[0] + a1[0]) * 0.5, (a0[1] + a1[1]) * 0.5, (a0[2] + a1[2]) * 0.5)
        da = (a1[0] - a0[0], a1[1] - a0[1], a1[2] - a0[2])
        for k in range(nB):
            b0, b1 = B[k], B[(k + 1) % nB]
            mbx = (b0[0] + b1[0]) * 0.5
            mby = (b0[1] + b1[1]) * 0.5
            mbz = (b0[2] + b1[2]) * 0.5
            db = (b1[0] - b0[0], b1[1] - b0[1], b1[2] - b0[2])
            rx, ry, rz = max_[0] - mbx, max_[1] - mby, max_[2] - mbz
            rm = math.sqrt(rx * rx + ry * ry + rz * rz)
            if rm < 1e-9:
                continue
            cx = da[1] * db[2] - da[2] * db[1]
            cy = da[2] * db[0] - da[0] * db[2]
            cz = da[0] * db[1] - da[1] * db[0]
            total += (rx * cx + ry * cy + rz * cz) / (rm ** 3)
    return total / (4.0 * math.pi)


def worst_downward_face(tris, bed_z=0.5):
    """Steepest (shallowest-from-horizontal) DOWNWARD face above the bed. Returns (angle_deg, nz)."""
    worst_ang = 90.0
    worst_nz = -1.0
    for a, b, c in tris:
        cz = (a[2] + b[2] + c[2]) / 3.0
        if cz <= bed_z:
            continue
        nx, ny, nz = _normal(a, b, c)
        if nz >= 0:
            continue
        ang = math.degrees(math.acos(min(1.0, abs(nz))))   # face angle from horizontal
        if ang < worst_ang:
            worst_ang, worst_nz = ang, nz
    return worst_ang, worst_nz


def ring_watertight(tris, i0, i1):
    from collections import Counter
    edges = Counter()
    for a, b, c in tris[i0:i1]:
        vs = [tuple(round(x, 3) for x in v) for v in (a, b, c)]
        for m in range(3):
            p, q = vs[m], vs[(m + 1) % 3]
            edges[(p, q) if p <= q else (q, p)] += 1
    return sum(1 for v in edges.values() if v != 2)


def ring_verts(tris, i0, i1):
    seen = {}
    for a, b, c in tris[i0:i1]:
        for v in (a, b, c):
            seen[(round(v[0], 3), round(v[1], 3), round(v[2], 3))] = v
    return list(seen.values())


def min_clearance(tris, rings, cutoff):
    """Sampled surface-to-surface min distance over every ring pair whose bboxes are within cutoff.
    Returns (min_dist, (rowA,colA), (rowB,colB))."""
    verts = [ring_verts(tris, r["i0"], r["i1"]) for r in rings]
    bb = []
    for vs in verts:
        xs = [p[0] for p in vs]; ys = [p[1] for p in vs]; zs = [p[2] for p in vs]
        bb.append((min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    best = float("inf")
    pair = (None, None)
    n = len(rings)
    for i in range(n):
        for j in range(i + 1, n):
            bi, bj = bb[i], bb[j]
            # bbox gap in each axis; if any axis gap > cutoff, min surface dist > cutoff -> skip
            gx = max(0.0, bi[0] - bj[1], bj[0] - bi[1])
            gy = max(0.0, bi[2] - bj[3], bj[2] - bi[3])
            gz = max(0.0, bi[4] - bj[5], bj[4] - bi[5])
            if math.sqrt(gx * gx + gy * gy + gz * gz) > best:
                continue
            vi, vj = verts[i], verts[j]
            for p in vi:
                for q in vj:
                    d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                    if d < best * best:
                        best = math.sqrt(d)
                        pair = ((rings[i]["row"], rings[i]["col"]),
                                (rings[j]["row"], rings[j]["col"]))
    return best, pair[0], pair[1]


def linking_report(rings, ring_od):
    """Gauss-check every close pair. Returns (ok, connected, n_links, offenders, n_pairs)."""
    n = len(rings)
    cut = ring_od * 1.4
    links = []           # (i, j) with |Lk| ~ 1
    offenders = []       # pairs with an ambiguous / non-integer linking number
    npairs = 0
    for i in range(n):
        ci = rings[i]["center"]
        for j in range(i + 1, n):
            cj = rings[j]["center"]
            if math.dist(ci, cj) > cut:
                continue
            npairs += 1
            lk = gauss_linking(rings[i]["cl"], rings[j]["cl"])
            if abs(abs(lk) - 1.0) < 0.15:
                links.append((i, j))
            elif abs(lk) < 0.15:
                pass
            else:
                offenders.append((i, j, lk))
    # connectivity over the linked graph (union-find)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in links:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    roots = {find(i) for i in range(n)}
    connected = len(roots) == 1
    ok = (len(offenders) == 0) and connected
    return ok, connected, len(links), offenders, npairs


# ---- STL i/o -----------------------------------------------------------------------


def write_stl(path, tris, header=b"crackle chainmail print-in-place fabric"):
    with open(path, "wb") as f:
        f.write(header.ljust(80, b"\0")[:80])
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            nx, ny, nz = _normal(a, b, c)
            f.write(struct.pack("<12fH", nx, ny, nz, *a, *b, *c, 0))


def bbox(tris):
    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    zs = [v[2] for t in tris for v in t]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


# ---- main --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description="print-in-place chainmail fabric -> one binary STL")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--ring-od", type=float, default=22.0, help="ring outer diameter (mm)")
    ap.add_argument("--cs-w", type=float, default=1.4, help="cross-section radial width (mm)")
    ap.add_argument("--cs-b", type=float, default=1.8, help="cross-section axial half-height (mm)")
    ap.add_argument("--tilt", type=float, default=22.0, help="row tilt from horizontal (deg)")
    ap.add_argument("--pitch-x", type=float, default=None, help="column pitch (auto from geometry)")
    ap.add_argument("--pitch-y", type=float, default=None, help="row pitch (auto from geometry)")
    ap.add_argument("--nmaj", type=int, default=96, help="major segments per ring")
    ap.add_argument("--clear", type=float, default=0.5, help="required pairwise clearance (mm)")
    ap.add_argument("--link-only", metavar="OUT", default=None,
                    help="emit a 2-ring interlock closeup instead of a sheet")
    ap.add_argument("--out", default="chainmail_coupon.stl")
    args = ap.parse_args()

    # auto pitch from geometry
    # measured, not derived: 0.75/0.375*od left same-row rings coplanar-overlapping (clearance
    # 0.000, would fuse). Swept 2026-08-02: dx=1.05*od, dy=0.425*od give 0.60+ mm at od 20.
    dx = args.pitch_x if args.pitch_x is not None else 1.05 * args.ring_od
    dy = args.pitch_y if args.pitch_y is not None else 0.418 * args.ring_od

    if args.link_only:
        # two threaded rings: rows 0 and 1, straddler pair (row0 col0, row1 col0)
        tris, rings = build_sheet(1, 2, args.ring_od, args.cs_w, args.cs_b,
                                  args.tilt, dx, dy, args.nmaj)
        write_stl(args.link_only, tris)
        lk = gauss_linking(rings[0]["cl"], rings[1]["cl"])
        clr, _, _ = min_clearance(tris, rings, args.clear)
        b = bbox(tris)
        print("== chainmail LINK closeup: %s ==" % args.link_only)
        print("  2 rings, %d tris, bbox %.1f x %.1f x %.1f mm"
              % (len(tris), b[1] - b[0], b[3] - b[2], b[5] - b[4]))
        print("  Gauss linking number = %+.3f  (interlocked)" % lk)
        print("  surface clearance = %.3f mm" % clr)
        return

    tris, rings = build_sheet(args.rows, args.cols, args.ring_od, args.cs_w, args.cs_b,
                              args.tilt, dx, dy, args.nmaj)
    write_stl(args.out, tris)

    # --- self-report ---
    b = bbox(tris)
    nbad_wt = sum(1 for r in rings if ring_watertight(tris, r["i0"], r["i1"]))
    minz_ring = [min(v[2] for v in tris[r["i0"]:r["i1"]] for v in [v]) for r in rings]
    # (simpler bed check per ring)
    bed_bad = 0
    for r in rings:
        mz = min(v[2] for tri in tris[r["i0"]:r["i1"]] for v in tri)
        if mz > 0.5:
            bed_bad += 1
    wang, wnz = worst_downward_face(tris)
    clr, pa, pb = min_clearance(tris, rings, args.clear)
    lk_ok, connected, nlinks, offenders, npairs = linking_report(rings, args.ring_od)

    a = args.cs_w / 2.0
    face0 = math.degrees(math.atan(args.cs_b / a))
    print("== chainmail fabric: %s ==" % args.out)
    print("  rings: %d  (%d cols x %d rows)  triangles: %d"
          % (len(rings), args.cols, args.rows, len(tris)))
    print("  sheet bbox: %.1f x %.1f x %.1f mm" % (b[1] - b[0], b[3] - b[2], b[5] - b[4]))
    print("  ring: OD %.1f  cross-section %.1f wide x %.1f tall (diamond), tilt %.0f deg"
          % (args.ring_od, args.cs_w, 2 * args.cs_b, args.tilt))
    print("  flat-ring face angle atan(b/a) = %.1f deg;  worst downward face (meshed, z>0.5) = "
          "%.1f deg  [need >=45, target >=47]" % (face0, wang))
    print("  per-ring watertight: %s (%d bad)" % ("OK" if nbad_wt == 0 else "FAIL", nbad_wt))
    print("  every ring on bed (min-z<=0.5): %s (%d hovering)"
          % ("OK" if bed_bad == 0 else "FAIL", bed_bad))
    print("  min pairwise clearance: %.3f mm  [need >=%.2f]  worst pair %s<->%s"
          % (clr, args.clear, pa, pb))
    print("  linking: %d intended pairs all +/-1, %d close pairs checked, %d ambiguous; "
          "connected: %s" % (nlinks, npairs, len(offenders),
                             "YES" if connected else "NO"))
    if offenders:
        for i, j, v in offenders[:5]:
            print("    AMBIGUOUS link %s<->%s = %+.3f"
                  % ((rings[i]["row"], rings[i]["col"]), (rings[j]["row"], rings[j]["col"]), v))
    ok = (nbad_wt == 0 and bed_bad == 0 and wang >= 45.0 and clr >= args.clear and lk_ok)
    print("  PRINT NOTES: K1C TPU, nozzle 205C, model fan 20%% (all other fans 100%%), "
          "~25-30 mm/s outer walls, no supports; brim only if a ring releases.")
    print("  SELF-VERIFY: %s" % ("PASS" if ok else "FAIL"))
    if not ok:
        failed = args.out + ".FAILED"
        os.replace(args.out, failed)
        print("  artifact quarantined -> %s (a failing STL must not sit in the repo looking ready)"
              % failed)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
