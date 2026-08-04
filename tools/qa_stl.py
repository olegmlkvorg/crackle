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
                  AND centroid z > 0.5 (not the bed) AND centroid r inside wallR(5mm z-band)
                  by more than min(6.0 mm, 40% of wallR) -- spans inward = a floor/roof, while a
                  ~1mm raised bead at the wall bridges fine. Radii are measured from the part's
                  OWN xy bbox centre, so the verdict does not depend on where the file sits.
                  Faces whose just-outside point is INSIDE material are excluded (the slicer
                  union erases them), decided by the vertical winding walk, not by which
                  connected component they belong to.
    7 SEALED-VOID (closed) 0 ray columns with material above AND below a void. watertight !=
                  printable: a sealed cavity is a flawless manifold and cannot print.
    8 FOOT        (closed, fabric) the first layer can hold a bead. Cross-section at half the
                  first layer height, split into connected islands, and each island measured for
                  the widest bead it could hold -- twice its largest inscribed radius -- against
                  0.82 line + 2 x 0.15 elephant foot = 1.12 mm. AREA IS REPORTED, NOT GATED: the
                  part that motivated this had 630 mm2 in ONE island and could not be sliced,
                  because the island was a ring one bead wide. Skipped for open/vase-solid, which
                  are spiralize inputs where the modelled wall is not the extrusion width.
    9 BED         bbox X and Y extents <= --bed (default 340)

Facet normals are recomputed from vertex winding; stored normals are not trusted.
"""
import argparse
import math
import os
import struct
import sys
from collections import Counter

FABRIC_MIN_FACE = 47.0  # deg floor for fabric downward faces (45 + 2 margin, low-fan TPU)
DOWN_NZ = -0.707        # unit-normal nz below this = downward-facing
BED_Z = 0.5             # mm; centroid at/below this sits on the bed
BAND_H = 5.0            # mm z-band height for the wall-radius profile
LEAN_MAX_DEG = 55.0     # vase-printable ceiling for wall lean from vertical

# How far inside the band's wall radius a downward face has to sit before it counts as a real
# inward span rather than a raised bead at the wall. Two numbers because the physics has two
# scales: a bead is absolute (nozzle-sized) and a span is proportional (a fraction of the part).
SPAN_MARGIN_MAX = 6.0    # mm; past this much inward, no bead explains the face
SPAN_MARGIN_FRAC = 0.4   # ... but never more than 40% of the wall radius, so the test cannot
                         # become unsatisfiable on a small part. A flat 6.0 mm did exactly that:
                         # trashcan_sealed_base.stl scaled to 9 mm across passed ALL SIX checks
                         # green, because r < wall_r(4.5) - 6.0 is r < -1.5 (2026-08-03).

SEAL_DX_MAX = 1.0        # mm ray-cast column pitch for the sealed-void walk: resolves the >=2
                         # bead walls this project builds with, on a part big enough for them
SEAL_MIN_COLS = 40       # ... but at least this many columns across the part, so the pitch is
                         # never coarse RELATIVE to what it measures. A flat pitch has the same
                         # failure mode a flat margin had: it goes vacuous as the part shrinks.
# -- FOOT: can the first layer STICK? ------------------------------------------------------
# icecage_pointyhex.stl passed WATERTIGHT, PRINTABLE (zero spanning overhangs), SEALED-VOID and
# BED, and Creality Print 7.1.1 still refused it: "One object has empty initial layer and can't
# be printed. Please Cut the bottom or enable supports." (2026-08-04)
#
# THE FIRST LAYER WAS NOT MISSING AND IT WAS NOT SPECKS. Measured off that mesh, the plane at
# z = 0.2 held 630.32 mm2 in ONE connected island. An area test passes it. An island-count test
# passes it. What was wrong was WIDTH: the island was a continuous ring 787.9 mm long and 0.8 mm
# wide, one bead across with no margin. Every stock @Creality K2 Plus process shipped in
# /Applications/Creality Print.app/Contents/Resources/profiles/Creality/process sets
#     wall_generator            classic      (all 12 checked, 0.6 and 0.8 nozzle)
#     detect_thin_wall          0            so there is no fallback for a sub-line region
#     elefant_foot_compensation 0.15         on elefant_foot_compensation_layers = 1
#     initial_layer_line_width  0.82 (0.8 nozzle) / 0.62 (0.6 nozzle)
# 0.8 - 2 x 0.15 = 0.50 mm survives layer 1, under one line width either way, and the classic
# generator lays no bead into a region narrower than a line. Layer 1 comes out empty while every
# layer above it slices normally, which is exactly the error Oleg saw and no other.
#
# NOT PROVEN BY RUNNING THE SLICER. The Creality Print CLI segfaults headless (exit 139) on every
# STL including known-good ones, so the mechanism is read off the shipped profiles and the
# measured geometry. The THRESHOLD is arithmetic on those shipped numbers, not a guess.
FOOT_LINE_W = 0.82       # mm initial_layer_line_width, K2 Plus 0.8 nozzle processes (the wider
                         # of the two nozzles, so the demanding one)
FOOT_EFC = 0.15          # mm elefant_foot_compensation, eaten off EACH side of layer 1
FOOT_LAYER_H = 0.4       # mm initial_layer_print_height, same processes. A slicer takes layer 1's
                         # cross-section at half this, so that is where this check looks.
FOOT_MIN_W = FOOT_LINE_W + 2.0 * FOOT_EFC    # 1.12 mm to survive as one full first-layer bead
FOOT_PITCH = 0.05        # mm scanline pitch, 1/22 of FOOT_MIN_W: what matters is never decided
                         # by a single row
FOOT_CAP = 10.0          # mm. Inscribed width is reported capped here and the search stops. The
                         # gate only asks whether the widest island clears FOOT_MIN_W; measuring
                         # a 100 mm slab exactly costs time and answers nothing.
FOOT_CELL = 1.0          # mm bucket pitch for the nearest-boundary search

BIN_PITCH = 4.0          # mm xy bucket pitch, so a vertical ray only tests nearby facets
FUSE_GAP = 0.25          # mm. Two surfaces closer than this print as ONE: the measured
                         # vase-mode figure for this project's printer is that a modelled hole
                         # comes out 0.25 mm under nominal, i.e. extrudate spreads that far past
                         # where the model puts it. PROVENANCE: that hole-shrink measurement,
                         # applied to a vertical gap -- same spreading, different direction, so
                         # it is borrowed rather than measured in z. It exists because the walk
                         # otherwise calls a 0.036 mm sliver between two near-tangent rim
                         # surfaces a sealed cavity (gift/trashcan.stl, 2026-08-03), and a 0.4 mm
                         # nozzle cannot make a 0.036 mm void.


def _foot_section(tris, z):
    """Directed cross-section segments at height z, wound so that material is where the winding
    number is nonzero. NONZERO and not even-odd, because this project's meshes are unions of
    hundreds of INTERPENETRATING closed solids (5522 in the cage) and even-odd would punch the
    overlaps back out as holes. Facet normals are recomputed from the winding; stored ones are
    not trusted, same rule as everywhere else in this file."""
    segs = []
    for a, b, c in tris:
        pts = []
        for p, q in ((a, b), (b, c), (c, a)):
            if (p[2] - z) * (q[2] - z) < 0:
                t = (z - p[2]) / (q[2] - p[2])
                pts.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        if len(pts) != 2:
            continue
        e1x, e1y, e1z = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        e2x, e2y, e2z = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx = e1y * e2z - e1z * e2y
        ny = e1z * e2x - e1x * e2z
        p0, p1 = pts
        # orient the chord so the facet's outward xy normal lies to its RIGHT
        if nx * (p1[1] - p0[1]) - ny * (p1[0] - p0[0]) > 0:
            p0, p1 = p1, p0
        segs.append((p0, p1))
    return segs


def _foot_spans(segs, y):
    """x intervals of the cross-section on the scanline at y, by nonzero winding."""
    xs = []
    for p0, p1 in segs:
        y0, y1 = p0[1], p1[1]
        if (y0 - y) * (y1 - y) >= 0:
            continue
        t = (y - y0) / (y1 - y0)
        xs.append((p0[0] + t * (p1[0] - p0[0]), 1 if y1 > y0 else -1))
    if not xs:
        return []
    xs.sort()
    out = []
    w = 0
    start = 0.0
    for x, d in xs:
        was = w
        w += d
        if was == 0 and w != 0:
            start = x
        elif was != 0 and w == 0:
            out.append((start, x))
    return out


def _foot_clearance(grid, px, py):
    """Distance from (px, py) to the nearest boundary segment, searched outward a ring of buckets
    at a time and stopped as soon as no further ring can beat what has been found. Capped at
    FOOT_CAP / 2, because the gate asks a threshold question and an exact answer for a slab costs
    time and decides nothing."""
    best = FOOT_CAP / 2.0
    ci, cj = int(math.floor(px / FOOT_CELL)), int(math.floor(py / FOOT_CELL))
    for k in range(int(math.ceil(best / FOOT_CELL)) + 2):
        # (k-1), NOT k. The query point sits anywhere inside its own bucket, so a segment first
        # reachable at Chebyshev ring k can still pass within (k-1)*FOOT_CELL of it. Terminating
        # on `best <= k*FOOT_CELL` stopped after ring 0 and reported a 0.8 mm ring as 1.55 mm
        # wide -- it found the far wall, called it the answer, and PASSED the file this check
        # exists to fail (2026-08-04).
        if best <= (k - 1) * FOOT_CELL:
            break
        for i in range(ci - k, ci + k + 1):
            for j in range(cj - k, cj + k + 1):
                if k and max(abs(i - ci), abs(j - cj)) != k:
                    continue
                for p0, p1 in grid.get((i, j), ()):
                    vx, vy = p1[0] - p0[0], p1[1] - p0[1]
                    L2 = vx * vx + vy * vy
                    t = 0.0 if L2 < 1e-18 else \
                        max(0.0, min(1.0, ((px - p0[0]) * vx + (py - p0[1]) * vy) / L2))
                    dx, dy = px - (p0[0] + t * vx), py - (p0[1] + t * vy)
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < best:
                        best = d
    return best


def _foot_islands(tris, z):
    """The first layer as the slicer will see it: connected islands of the cross-section at z,
    each with its area and the widest first-layer bead it could hold.

    WIDTH, NOT AREA, IS THE MEASURE. The part that failed had one island of 630 mm2. Width is
    twice the largest inscribed radius, probed at scanline span midpoints -- for an annulus, a
    slab, a bar at any angle and a speck that midpoint IS the inscribed centre, so the probe is
    exact on every shape a first layer is made of, and it never overstates."""
    segs = _foot_section(tris, z)
    if not segs:
        return []
    grid = {}
    for s in segs:
        x0, x1 = sorted((s[0][0], s[1][0]))
        y0, y1 = sorted((s[0][1], s[1][1]))
        for i in range(int(math.floor(x0 / FOOT_CELL)), int(math.floor(x1 / FOOT_CELL)) + 1):
            for j in range(int(math.floor(y0 / FOOT_CELL)), int(math.floor(y1 / FOOT_CELL)) + 1):
                grid.setdefault((i, j), []).append(s)

    ys = [p[1] for s in segs for p in s]
    ylo, yhi = min(ys), max(ys)
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    area = {}
    width = {}
    prev = []
    for k in range(int(math.ceil((yhi - ylo) / FOOT_PITCH))):
        y = ylo + (k + 0.5) * FOOT_PITCH
        cur = []
        for j, (a, b) in enumerate(_foot_spans(segs, y)):
            key = (k, j)
            parent[key] = key
            area[key] = (b - a) * FOOT_PITCH
            # the midpoint always, plus a bounded stride so an L or a U is probed inside each arm
            probes = [(a + b) / 2.0]
            step = max(4.0 * FOOT_PITCH, (b - a) / 8.0)
            x = a + step / 2.0
            while x < b:
                probes.append(x)
                x += step
            width[key] = 2.0 * max(_foot_clearance(grid, px, y) for px in probes)
            for pk, pa, pb in prev:
                if pb > a and b > pa:
                    ra, rb = find(key), find(pk)
                    if ra != rb:
                        parent[ra] = rb
            cur.append((key, a, b))
        prev = cur

    isl = {}
    for key in parent:
        r = find(key)
        a, w = isl.get(r, (0.0, 0.0))
        isl[r] = (a + area[key], max(w, width[key]))
    return sorted(isl.values(), key=lambda t: -t[1])


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


def _xy_bins(tris3d, pitch=BIN_PITCH):
    """Bucket triangle indices by the xy cells their footprint covers, so a vertical ray only
    tests facets near its own column."""
    bins = {}
    for idx, t in enumerate(tris3d):
        v0, v1, v2 = t[0], t[1], t[2]
        ix0 = int(math.floor(min(v0[0], v1[0], v2[0]) / pitch))
        ix1 = int(math.floor(max(v0[0], v1[0], v2[0]) / pitch))
        iy0 = int(math.floor(min(v0[1], v1[1], v2[1]) / pitch))
        iy1 = int(math.floor(max(v0[1], v1[1], v2[1]) / pitch))
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                bins.setdefault((ix, iy), []).append(idx)
    return bins


def _solid_runs(x, y, tris3d, bins, pitch=BIN_PITCH, graze=1e-3):
    """Fire a vertical ray up the column at (x, y) and walk its crossings carrying a WINDING
    DEPTH: a downward-facing facet is the ray ENTERING material, an upward-facing one is it
    LEAVING. Material is wherever the depth is positive, so the runs are the UNION of whatever
    solids the column passes through -- interpenetration and cavities both come out right.

    Depth counting rather than bare parity pairing: a column that grazes a wall clips it twice
    at almost the same z, and every later pair is then inverted (the nfc puck read 54 phantom
    sealed voids that way). Zero-length grazes drop out at `graze`.

    Returns (runs, ok). ok is False when the walk did not close -- a ray through a vertex, or an
    open mesh. An undecidable column is never a passing one; callers must not read runs then."""
    hits = []
    key = (int(math.floor(x / pitch)), int(math.floor(y / pitch)))
    for idx in bins.get(key, ()):
        t = tris3d[idx]
        a, b, c = t[0], t[1], t[2]
        d1 = (x - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (y - b[1])
        d2 = (x - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (y - c[1])
        d3 = (x - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (y - a[1])
        if not ((d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0)):
            continue
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        if abs(nz) < 1e-12:
            continue                      # vertical facet: a vertical ray cannot cross it
        hits.append((a[2] - (nx * (x - a[0]) + ny * (y - a[1])) / nz, -1 if nz < 0 else 1))
    if len(hits) < 2:
        return [], len(hits) == 0         # empty column is fine; a single crossing is not
    hits.sort()
    runs = []
    depth = 0
    start = None
    for z_, s in hits:
        was = depth
        depth += 1 if s < 0 else -1
        if was <= 0 and depth > 0:
            start = z_
        elif was > 0 and depth <= 0 and start is not None:
            if z_ - start > graze:
                runs.append((start, z_))
            start = None
    merged = []                           # gaps under FUSE_GAP print as solid, so read them so
    for a, b in runs:                     # (see the constant: two near-tangent rim surfaces)
        if merged and a - merged[-1][1] < FUSE_GAP:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged, (depth == 0 and start is None)


def _sealed_voids(tris3d, bins, minx, maxx, miny, maxy):
    """Voids with NO PATH TO THE OUTSIDE -- the failure this project has shipped unprintable
    twice. Edge parity cannot see one: a solid with a sealed cavity is a flawless manifold.

    Reachability, not "is there material above and below". That column test is the one
    nfc_puck_stl.py uses and it is right for a puck, where any void is a chamber, but it does not
    generalise: a HORIZONTAL through-hole also has material above and below every column that
    crosses it, and it is wide open to the air. Measured on the 97 published parts it failed 26
    sound ones -- every bamboo socket bore, the marble ballast bases (2026-08-03).

    So: take each column's AIR intervals (the complement of its solid runs, running off to
    +/-inf at the ends), join an interval to the four neighbouring columns' intervals wherever
    their z ranges overlap, and flood from every interval that is unbounded or sits in a column
    outside the part. What the flood never reaches is enclosed.

    A wall thinner than the grid pitch is below this gate's resolution -- the pitch is reported
    with the verdict so that limit is visible rather than assumed away.

    Returns (sealed_cells, sealed_columns, odd, cols, tallest_mm, pitch_mm)."""
    seed = 0.0137                          # nudge the grid off every axis of symmetry
    dx = min(SEAL_DX_MAX, max(maxx - minx, maxy - miny) / SEAL_MIN_COLS)
    nx = int(math.ceil((maxx - minx) / dx))
    ny = int(math.ceil((maxy - miny) / dx))
    air = {}
    odd = cols = 0
    for ix in range(-1, nx + 2):           # one spare column of open air on each side
        x = minx + (ix + 0.5) * dx + seed
        for iy in range(-1, ny + 2):
            y = miny + (iy + 0.5) * dx + seed
            runs, ok = _solid_runs(x, y, tris3d, bins)
            if not ok:
                odd += 1                   # undecidable: contributes no air, so a neighbouring
                continue                   # void cannot escape THROUGH it. Reported, not hidden.
            if runs:
                cols += 1
            ivs = []
            lo = float("-inf")
            for a, b in runs:
                ivs.append((lo, a))
                lo = b
            ivs.append((lo, float("inf")))
            air[(ix, iy)] = ivs

    seen = set()
    stack = []
    for (ix, iy), ivs in air.items():
        edge = ix in (-1, nx + 1) or iy in (-1, ny + 1)
        for k, (a, b) in enumerate(ivs):
            if edge or a == float("-inf") or b == float("inf"):
                seen.add((ix, iy, k))
                stack.append((ix, iy, k))
    while stack:
        ix, iy, k = stack.pop()
        a, b = air[(ix, iy)][k]
        for jx, jy in ((ix - 1, iy), (ix + 1, iy), (ix, iy - 1), (ix, iy + 1)):
            nb = air.get((jx, jy))
            if nb is None:
                continue
            for kk, (c, d) in enumerate(nb):
                if (jx, jy, kk) in seen or not (c < b and a < d):
                    continue
                seen.add((jx, jy, kk))
                stack.append((jx, jy, kk))

    sealed = 0
    sealed_cols = set()
    tallest = 0.0
    for (ix, iy), ivs in air.items():
        for k, (a, b) in enumerate(ivs):
            if a == float("-inf") or b == float("inf") or (ix, iy, k) in seen:
                continue
            sealed += 1
            sealed_cols.add((ix, iy))
            if b - a > tallest:
                tallest = b - a
    return sealed, len(sealed_cols), odd, cols, tallest, dx


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



def _layer_continuity(body_tris, dz=0.4, walk=1.1, sample=0.6):
    """THE support-free ground truth: slice the mesh at dz planes; every bit of material in layer k
    must sit within `walk` (XY) of material in layer k-1, or be part of a BRIDGE RUN (an unsupported
    span whose ends are supported). Face-angle rules are necessary but NOT sufficient (a tilted
    ring's crest passes the face rule yet prints in mid-air -- Oleg caught it, 2026-08-02).
    Returns (bridge_runs, longest_run_mm, unsupported_orphans) where orphans = unsupported points
    NOT in a bridge (no supported ends) -- those are hard failures."""
    minz = min(v[2] for t in body_tris for v in t)
    maxz = max(v[2] for t in body_tris for v in t)
    layers = []
    zc = minz + dz
    while zc < maxz:
        pts = []
        for a, b, c in body_tris:
            zs = (a[2], b[2], c[2])
            if max(zs) < zc or min(zs) > zc:
                continue
            hits = []
            for p, q in ((a, b), (b, c), (c, a)):
                if (p[2] - zc) * (q[2] - zc) <= 0 and abs(q[2] - p[2]) > 1e-9:
                    t_ = (zc - p[2]) / (q[2] - p[2])
                    hits.append((p[0] + t_ * (q[0] - p[0]), p[1] + t_ * (q[1] - p[1])))
            if len(hits) >= 2:
                (x0, y0), (x1, y1) = hits[0], hits[1]
                L = math.hypot(x1 - x0, y1 - y0)
                n_ = max(1, int(L / sample))
                for k in range(n_ + 1):
                    f = k / n_
                    pts.append((x0 + f * (x1 - x0), y0 + f * (y1 - y0)))
        layers.append(pts)
        zc += dz

    def grid(pts):
        g = {}
        for (x, y) in pts:
            g.setdefault((int(x // 2), int(y // 2)), []).append((x, y))
        return g

    runs = []
    orphans = 0
    for k in range(1, len(layers)):
        below = grid(layers[k - 1])
        unsup = []
        for (x, y) in layers[k]:
            cx, cy = int(x // 2), int(y // 2)
            ok = False
            for gx in (cx - 1, cx, cx + 1):
                for gy in (cy - 1, cy, cy + 1):
                    for (bx, by) in below.get((gx, gy), ()):
                        if (x - bx) ** 2 + (y - by) ** 2 <= walk * walk:
                            ok = True
                            break
                    if ok: break
                if ok: break
            if not ok:
                unsup.append((x, y))
        if not unsup:
            continue
        # cluster unsupported points into runs (1.5mm neighbour joins)
        unused = list(unsup)
        while unused:
            seed = unused.pop()
            run = [seed]
            changed = True
            while changed:
                changed = False
                for p in unused[:]:
                    if any((p[0]-q[0])**2 + (p[1]-q[1])**2 <= 2.25 for q in run):
                        run.append(p); unused.remove(p); changed = True
            xs = [p[0] for p in run]; ys = [p[1] for p in run]
            span = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
            # a run is a BRIDGE if supported material sits within walk of BOTH extreme ends
            supported = [p for p in layers[k] if p not in unsup]
            def _near(pt):
                return any((pt[0]-sx)**2 + (pt[1]-sy)**2 <= (walk*1.5)**2 for (sx, sy) in supported)
            e1 = min(run, key=lambda p: p[0]*1000 + p[1]); e2 = max(run, key=lambda p: p[0]*1000 + p[1])
            if _near(e1) and _near(e2):
                runs.append(span)
            else:
                orphans += len(run)
    return runs, (max(runs) if runs else 0.0), orphans


def run_file(path, cls, bed, allow, clear_min, bridge_max=8.0, transit_dia=None):
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
    faces = []   # (nz, centroid_z, centroid_x, centroid_y) here; centroid_r replaces x,y below,
                 # once the bbox is known -- radius is measured from the PART, not the origin
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
        faces.append((cz / m, cenz, cenx, ceny))
        if cls in ("closed", "fabric"):
            tris3d.append((v0, v1, v2, cenx, ceny, cenz, cz / m))

    # Radii from the part's OWN xy bbox centre. Measured from the world origin, the same solid
    # moved to (+120, +120) turned 504 spanning faces into 5458 -- a verdict that depended on
    # where the file happened to sit (2026-08-03). The bbox centre and not the area centroid:
    # it is the axis for the bodies of revolution this heuristic reads, it sits inside the
    # footprint by construction, and it does not drift when a mesh is retessellated.
    if faces:
        ctr_x = (minx + maxx) / 2.0
        ctr_y = (miny + maxy) / 2.0
        faces = [(nz, z, math.hypot(fx - ctr_x, fy - ctr_y)) for (nz, z, fx, fy) in faces]

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
            out = []
            for i, (nz, z, r) in enumerate(fs):
                if nz >= DOWN_NZ or z <= BED_Z:
                    continue
                wr = wall_r[int(z // BAND_H)]
                if r < wr - min(SPAN_MARGIN_MAX, SPAN_MARGIN_FRAC * wr):
                    out.append(i)
            return out

        bins = _xy_bins(tris3d) if tris3d else {}

        def buried(idx):
            """A face is erased by the slicer union only if the point just outside it sits INSIDE
            material -- decided by the vertical winding walk over the WHOLE soup, which reads the
            union, so a solid's own body counts as material.

            The walk replaced a component-identity test that asked whether the point sat inside a
            DIFFERENT connected component. A solid with a sealed cavity is TWO components (outer
            shell and inverted cavity surface share no vertices), so the cavity's lid was 'buried'
            by the shell above the void it hangs in, and nfc_puck_stl.py --sealed -- a mesh whose
            own generator fails it on 3712 enclosed columns -- passed all six checks green.

            An undecidable column counts as NOT buried: uncertainty must not flatter the part."""
            _v0, _v1, _v2, px, py, pz, fnz = tris3d[idx]
            pz += (0.2 if fnz > 0 else -0.2)          # step just OUTSIDE the face along its normal z
            runs, ok = _solid_runs(px, py, tris3d, bins)
            return ok and any(a < pz < b for a, b in runs)

        up_idx = spanning_idx(faces)
        flipped = [(-nz, maxz - z, r) for nz, z, r in faces]
        fl_idx = spanning_idx(flipped)
        # burial is orientation-independent; test each candidate once
        cand = set(up_idx) | set(fl_idx)
        buried_set = set(i for i in cand if buried(i))
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
                   "z %.1f..%.1f%s - inward floor/roof: unprintable in EITHER orientation"
                   % (len(up), len(fl), allow, min(up), max(up), note))

        # -- 7 SEALED-VOID (closed) -----------------------------------------------
        # Edge parity cannot see this: a solid with a sealed cavity is a perfectly watertight
        # mesh, and one passed WATERTIGHT twice here while being unprintable twice.
        seal, seal_cols, odd, cols, tallest, pitch = \
            _sealed_voids(tris3d, bins, minx, maxx, miny, maxy) if tris3d \
            else (0, 0, 0, 0, 0.0, 0.0)
        report("SEALED-VOID", seal == 0 and cols > 0,
               "%d enclosed air pockets over %d of %d ray columns, tallest %.2f mm -- air with no "
               "path out through any of the 4 neighbouring columns. %.3f mm grid, so a wall "
               "thinner than that is below this gate's resolution; %d columns undecidable and "
               "counted as unmeasured"
               % (seal, seal_cols, cols, tallest, pitch, odd))

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
        n_margin = sum(1 for _nz, z, _r in faces
                       if z > BED_Z and _nz < 0
                       and math.degrees(math.acos(min(1.0, abs(_nz)))) < FABRIC_MIN_FACE)
        report("OVERHANG", n_over == 0 and n_margin == 0,
               "%d faces < 45deg, %d faces < %.0fdeg floor (45 + 2 margin for low-fan TPU); "
               "shallowest downward face = %.1f deg from horizontal"
               % (n_over, n_margin, FABRIC_MIN_FACE, shallow))

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

        body = [(t[0], t[1], t[2]) for t in tris3d] if tris3d else \
               [t for ct in comp_tris for t in ct]
        runs, longest, orphans = _layer_continuity(body)
        report("LAYERCONT", orphans == 0 and longest <= bridge_max,
               "%d bridge runs (longest %.1f mm, allowed %.1f), %d unsupported orphan points -- "
               "every layer must land on the layer below; bridges are a MEASURED allowance, not free"
               % (len(runs), longest, bridge_max, orphans))

    # -- FOOT ------------------------------------------------------------------
    # Only for parts printed layer by layer. `open` and `vase-solid` are spiralize inputs: the
    # slicer traces the modelled SURFACE and the extrusion width comes from the profile, not from
    # the modelled wall, so a one-line-thick vase wall is what vase mode is for and this test
    # would be measuring the wrong thing. That is the same reason vase-solid skips PRINTABLE.
    if cls in ("closed", "fabric") and tris3d:
        zc = minz + FOOT_LAYER_H / 2.0
        isl = _foot_islands([(t[0], t[1], t[2]) for t in tris3d], zc)
        flipped = ""
        if not (isl and isl[0][1] >= FOOT_MIN_W):
            up = _foot_islands([(t[0], t[1], t[2]) for t in tris3d],
                               maxz - FOOT_LAYER_H / 2.0)
            if up and up[0][1] >= FOOT_MIN_W:
                isl, flipped = up, "  (only as printed UPSIDE-DOWN -- the as-sits bottom fails)"
        if not isl:
            report("FOOT", False, "nothing crosses z = %.3f, %.2f mm above the mesh floor: there "
                                  "is no first layer at all" % (zc, FOOT_LAYER_H / 2.0))
        else:
            tot = sum(a for a, _w in isl)
            wide = [(a, w) for a, w in isl if w >= FOOT_MIN_W]
            best = isl[0][1]
            report("FOOT", bool(wide),
                   "first layer at z = %.3f: %d island(s), %.1f mm2 total; widest island holds a "
                   "%s mm bead (limit %.2f = %.2f line + 2 x %.2f elephant foot), %d island(s) "
                   "and %.1f mm2 survive it%s"
                   % (zc, len(isl), tot,
                      ">=%.2f" % best if best >= FOOT_CAP else "%.2f" % best,
                      FOOT_MIN_W, FOOT_LINE_W, FOOT_EFC,
                      len(wide), sum(a for a, _w in wide), flipped))

    # -- 7 BED ----------------------------------------------------------------
    if minx == float("inf"):
        report("BED", False, "no triangles, no bbox")
    else:
        dx, dy, dz = maxx - minx, maxy - miny, maxz - minz
        report("BED", dx <= bed and dy <= bed,
               "bbox %.1f x %.1f x %.1f mm (X,Y limit %g)" % (dx, dy, dz, bed))

    # TRANSIT. Opt-in, because most parts have no bore. Added 2026-08-03 after a bend guide
    # passed six checks including one NAMED "threadable" and could not admit a stick. A check
    # whose name claims a property must measure that property, so this one calls the measuring
    # code in transit.py rather than a proxy. See Assist/guides/retro-bore-transit.md.
    if transit_dia:
        try:
            import transit as _t
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import transit as _t
        try:
            r = _t.check(path, transit_dia)
            ok, msg = r["ok"], r["msg"]
        except Exception as e:
            # A probe that errors must FAIL, never pass quietly. A broken probe reporting
            # success is how several wrong conclusions got made in this project.
            ok, msg = False, "transit probe failed: %s" % e
        report("TRANSIT", ok, msg)

    return fails[0] == 0


def main():
    ap = argparse.ArgumentParser(
        description="STL quality gate: LAW, HEADER, DEGENERATE, "
                    "WATERTIGHT/LEAN, PRINTABLE, SEALED-VOID, BED. Exit 1 on any FAIL.")
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
    ap.add_argument("--bridge-max", type=float, default=8.0,
                    help="fabric: longest tolerated bridge run mm (crest of a tilted ring bridges)")
    ap.add_argument("--clear-min", type=float, default=0.45,
                    help="fabric: min pairwise surface clearance in mm (default 0.45)")
    ap.add_argument("--transit", type=float, default=None, metavar="DIA",
                    help="also prove a rigid DIA mm part can be THREADED through this part's bore, "
                         "measured off the mesh (tools/transit.py). Use it on anything a rod, "
                         "marble or shaft must pass through.")
    args = ap.parse_args()

    failed = 0
    for path in args.stl:
        if not run_file(path, args.cls, args.bed, args.allow_overhang, args.clear_min,
                        args.bridge_max, args.transit):
            failed += 1
    n = len(args.stl)
    if failed:
        print("FAIL qa_stl: %d of %d file(s) failed" % (failed, n))
        sys.exit(1)
    print("PASS qa_stl: %d file(s), all checks green" % n)
    sys.exit(0)


if __name__ == "__main__":
    main()
