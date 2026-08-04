#!/usr/bin/env python3
"""icecage_pointyhex.py -- OPEN pointy-top hexagonal lattice cage, layer-by-layer printable.

WHAT THIS IS
    A cylindrical cage: no closed wall anywhere. The wall is a honeycomb of pointy-top hexagons
    whose members are all vertical or inclined at atan(a/b) from vertical. There is not one
    horizontal member in the lattice, so nothing bridges: every layer lands on the layer below.

    This is NOT a vase-mode part. The last two builds in this series (icecage.py,
    icecage_corrugated.py) emitted closed single-wall solids for the slicer's spiralize mode.
    This one is an ordinary solid printed layer by layer with ~120 separate islands per layer.
    Slicing it in vase mode would destroy it.

WHY THE FIRST BUILD COULD NOT BE SLICED, and it was not the foot
    Creality Print 7.1.1 refused it: "One object has empty initial layer and can't be printed."
    The first layer was NOT missing and it was NOT specks. Measured off that mesh, the plane at
    z = 0.2 held 630.32 mm2 in ONE connected island, a continuous 787.9 mm ring, and all 5522
    solids were outward-oriented. It was too NARROW. The members were built 0.80 wide and his
    slicer's line is 0.82, so NOT ONE FEATURE IN THE PART could hold a single extrusion. Every
    stock @Creality K2 Plus process sets wall_generator = classic with detect_thin_wall = 0, so a
    region narrower than a line gets no bead and no fallback. The first layer is simply where the
    slicer says so, because an empty first layer is its one FATAL emptiness.
    NOT PROVEN BY RUNNING THE SLICER: the Creality Print CLI segfaults headless (exit 139) on
    every STL including known-good ones. Read off the shipped profiles and the measured geometry.

THE STACKING LAW, re-derived at the machine's own numbers
    At layer height h a member inclined T from VERTICAL shifts h*tan(T) sideways per layer. For
    the bead to land on the bead below, that shift must stay under half the extrusion width.
        h = SLICER_LAYER_H = 0.24, w = SLICER_LINE_W = 0.82
        0.24 * tan(T) < 0.41  ->  T < 59.66 deg
    That is LOOSER than the 55 deg this design was judged against (0.28 layer, 0.80 bead), so the
    lattice clears with more room than before, not less. --lean-max stays at the stricter 55.0,
    which is also tools/qa_stl.py LEAN_MAX_DEG: a change that buys slack is no reason to spend it.
    This generator REFUSES to keep a file whose worst measured MEMBER AXIS or sloped underside
    exceeds --lean-max, and deletes it. Proven able to fire twice: --apex-rise 3.0 (65.5 deg) and
    --cells 12 (80.5 deg).

THE FOOT, which is a SECOND defect and survives the width fix
    Layer 1 is eroded by elefant_foot_compensation = 0.15 PER SIDE (elefant_foot_compensation_
    layers = 1, so layer 1 only). A member at exactly one line width would be left 0.52 mm there,
    still under a line -- so a part standing on its own 0.82 wall has an empty first layer even
    after the width fix. The bottom is therefore a band --foot-width wide held for --foot-flat,
    splayed back to the wall by --rim.
        foot width = 3 x 0.82 = 2.46, taken as 2.4. After 2 x 0.15 that is 2.10 mm of printed
        width = 2.56 lines, so two full loops survive with margin. 2 x 0.82 + 2 x 0.15 = 1.94 is
        the bare minimum, and the part before this failed by 2%, which is why the minimum is not
        what was used.
    The TOP gets no foot: see the note at the top_ring call.
    tools/qa_stl.py gates both -- MINWIDTH for the line-width rule, FOOT for layer 1.

CONSTANT PROVENANCE -- every dimension below now comes off HIS machine, none are hand-set
    member width 0.82       machine.py SLICER_LINE_W, read from all six K2 Plus 0.8 profiles.
                            Oleg asked for "single line 0.8 line width everywhere"; 0.82 is that
                            same intent at his profile's own number, and 0.80 is what failed.
    layer height 0.24       machine.py SLICER_LAYER_H. Oleg 2026-08-04 "yea i meant 0.24 update
                            it" -- he first said 0.28, which is not among the stock heights.
    first layer 0.40        machine.py SLICER_FIRST_H. Note it is 1.67 x the layer height; that
                            is the profile's own design, and nothing here assumes uniform layers.
    nozzle 0.8              machine.py NOZZLE
    bed 350 x 350 x 350     memory printer-k2plus (K2 Plus real ceiling)
    PLA density 1.24 g/cm3  handbook figure carried in from the ranking brief -- NOT measured here
    MISMATCH, unresolved on purpose:
      machine.py BEAD_W = 1.2 and BEAD_H = 0.6 are the crackle stacking doctrine for hand-rolled
      toolpaths. This part is sliced, so the SLICER_ constants govern it, and they disagree.

EVERY NUMBER THIS SCRIPT PRINTS IS MEASURED OFF THE EMITTED FILE, by reading it back. Nothing
is reported from the design arithmetic that produced it.
"""
import argparse
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# IMPORTED, never retyped. A literal copy of a machine constant is the bug class this repo keeps
# paying for, and it is what put an 0.80 wall under an 0.82 line in the first place.
from machine import SLICER_LINE_W, SLICER_LAYER_H, SLICER_FIRST_H


# ---------------------------------------------------------------- mesh primitives

def hexa(b0, b1, b2, b3, t0, t1, t2, t3):
    """12 outward-wound triangles of a hexahedron. b0..b3 must run CCW seen from the t side."""
    return [(b0, b2, b1), (b0, b3, b2),
            (t0, t1, t2), (t0, t2, t3),
            (b0, b1, t1), (b0, t1, t0),
            (b1, b2, t2), (b1, t2, t1),
            (b2, b3, t3), (b2, t3, t2),
            (b3, b0, t0), (b3, t0, t3)]


def member(p0, p1, w, ext):
    """A w x w square-section beam from p0 to p1, extended `ext` past each end so beams
    INTERPENETRATE at every node instead of leaving a notch. One radial face, one tangential."""
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    L = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / L, uy / L, uz / L
    q0 = (p0[0] - ux * ext, p0[1] - uy * ext, p0[2] - uz * ext)
    q1 = (p1[0] + ux * ext, p1[1] + uy * ext, p1[2] + uz * ext)
    mx, my = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    rm = math.hypot(mx, my)
    rx, ry = mx / rm, my / rm            # radial at the midpoint; exactly perpendicular to u
    tx = uy * 0.0 - uz * ry
    ty = uz * rx - ux * 0.0
    tz = ux * ry - uy * rx
    tl = math.sqrt(tx * tx + ty * ty + tz * tz)
    tx, ty, tz = tx / tl, ty / tl, tz / tl
    hw = w / 2.0

    def c(p, sr, st):
        return (p[0] + sr * hw * rx + st * hw * tx,
                p[1] + sr * hw * ry + st * hw * ty,
                p[2] + st * hw * tz)

    return hexa(c(q0, -1, -1), c(q0, 1, -1), c(q0, 1, 1), c(q0, -1, 1),
                c(q1, -1, -1), c(q1, 1, -1), c(q1, 1, 1), c(q1, -1, 1))


def revolve(facets, sec_fn):
    """A solid of revolution WELDED all the way round: one manifold, not a chain of separate
    slices. Slices that merely share vertices put 4 triangles on every interface edge and edge
    parity fails -- that is exactly what 5760 non-paired edges looked like the first time this was
    built. sec_fn(theta) returns the section as (r, z) pairs, wound CCW in the r-z plane; it takes
    theta so a section can vary around the turn (the top ring's scalloped underside does)."""
    secs = []
    for k in range(facets):
        th = 2.0 * math.pi * k / facets
        c, s = math.cos(th), math.sin(th)
        secs.append([(r * c, r * s, z) for r, z in sec_fn(th)])
    m = len(secs[0])
    tris = []
    for k in range(facets):
        p, q = secs[k], secs[(k + 1) % facets]
        for i in range(m):
            j = (i + 1) % m
            tris.append((p[i], p[j], q[j]))
            tris.append((p[i], q[j], q[i]))
    return orient(tris)


def orient(tris):
    """Flip a closed set so its facet normals point OUT (signed volume positive)."""
    vol = 0.0
    for a, b, c in tris:
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return tris if vol > 0 else [(a, c, b) for a, b, c in tris]


def write_stl(path, tris):
    hdr = b"icecage_pointyhex open lattice - binary STL - not vase mode"
    with open(path, "wb") as f:
        f.write(hdr.ljust(80, b" ")[:80])
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            m = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            f.write(struct.pack("<12fH", nx / m, ny / m, nz / m,
                                a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2], 0))


# ---------------------------------------------------------------- the part

def build(A):
    w = A.member
    r_in = A.inner_dia / 2.0
    r_out = r_in + w
    r_mid = r_in + w / 2.0
    C = 2.0 * math.pi * r_mid
    n = A.cells
    a = C / (2.0 * n)                     # half cell width, arc on the mid surface
    b, v = A.apex_rise, A.side
    hh = v / 2.0 + b                      # hexagon half height
    pitch = v + b
    T = math.degrees(math.atan2(a, b))    # member inclination from VERTICAL
    ext = w / 2.0

    def P(m, z):
        th = m * math.pi / n
        return (r_mid * math.cos(th), r_mid * math.sin(th), z)

    tris = []
    # THE FOOT. A plain w-wide rim on the bed is what a slicer rejects: see the FOOT WIDTH note in
    # the module docstring. So the bottom is a band A.foot_width wide held for A.foot_flat, then
    # splayed back to the w-wide wall by A.rim. Splay per side, and the lean it costs:
    splay = (A.foot_width - w) / 2.0
    foot_lean = math.degrees(math.atan2(splay, A.rim - A.foot_flat))
    tris += revolve(A.ring_facets, lambda th: [
        (r_in - splay, 0.0), (r_out + splay, 0.0), (r_out + splay, A.foot_flat),
        (r_out, A.rim), (r_in, A.rim), (r_in - splay, A.foot_flat)])

    # lattice. Rows 0..rows-1 own {right vertical, bottom-right slant, bottom-left slant};
    # row `rows` contributes only its two bottom slants, which ARE the top row's apex pair.
    for j in range(A.rows + 1):
        zc = A.rim + hh + j * pitch
        for i in range(n):
            m = (j % 2) + 2 * i
            B = P(m, zc - hh)
            LR = P(m + 1, zc - v / 2.0)
            LL = P(m - 1, zc - v / 2.0)
            tris += member(B, LR, w, ext)
            tris += member(B, LL, w, ext)
            if j < A.rows:
                tris += member(LR, P(m + 1, zc + v / 2.0), w, ext)

    z_apex = A.rim + b + A.rows * pitch
    corbel = a / math.tan(math.radians(T))       # = b exactly; rise to close the ring
    z_top = z_apex + corbel + A.rim
    apex_par = (A.rows + 1) % 2                  # apex stations have this parity

    def zbot(th):
        st = th * n / math.pi                    # station coordinate, 2n per turn
        k = math.floor(st)
        best = a
        for cand in (k - 1, k, k + 1, k + 2):
            if cand % 2 == apex_par:
                d = abs(st - cand) * a           # |station delta| * half cell = arc distance
                if d < best:
                    best = d
        return z_apex + best * (b / a)

    # top ring: corbel + rim as ONE solid. Its underside is a scalloped V that starts at the 60
    # apexes and widens at exactly T until neighbours meet, so the ring closes with ZERO bridging.
    # THE TOP GETS NO FOOT, and the reason is not symmetry. A foot does one job -- hold the part
    # to the plate through the first layer -- and the top touches no plate. The compensation that
    # eats the first layer is applied for elefant_foot_compensation_layers = 1, so nothing erodes
    # the top ring either. Widening it would add mass at the full 313.8 mm lever arm of a part
    # 251.6 mm across, which makes tipping worse, and it is the one place on this part where extra
    # material buys nothing at all.
    if A.top_ring:
        tris += revolve(A.ring_facets, lambda th: [(r_in, zbot(th)), (r_out, zbot(th)),
                                                   (r_out, z_top), (r_in, z_top)])

    return tris, dict(a=a, b=b, v=v, T=T, C=C, r_in=r_in, r_out=r_out, r_mid=r_mid,
                      z_apex=z_apex, z_top=z_top, corbel=corbel, w=w, pitch=pitch,
                      splay=splay, foot_lean=foot_lean)


# ---------------------------------------------------------------- measurement (off the file)

def read_stl(path):
    with open(path, "rb") as f:
        hdr = f.read(80)
        (ntris,) = struct.unpack("<I", f.read(4))
        body = f.read()
    tris = [(r[3:6], r[6:9], r[9:12]) for r in struct.iter_unpack("<12fH", body)]
    return hdr, ntris, tris


def components(tris):
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    keys = []
    for a, b, c in tris:
        ks = [tuple(round(q, 3) for q in p) for p in (a, b, c)]
        for k in ks:
            parent.setdefault(k, k)
        union(ks[0], ks[1])
        union(ks[1], ks[2])
        keys.append(ks[0])
    remap = {}
    return [remap.setdefault(find(k), len(remap)) for k in keys], len(remap)


def poly_span_at(poly, z):
    """s-interval of a convex polygon (s,z) at height z, or None."""
    lo, hi = None, None
    n = len(poly)
    for i in range(n):
        s1, z1 = poly[i]
        s2, z2 = poly[(i + 1) % n]
        if (z1 - z) * (z2 - z) > 0 or z1 == z2:
            continue
        t = (z - z1) / (z2 - z1)
        s = s1 + t * (s2 - s1)
        lo = s if lo is None or s < lo else lo
        hi = s if hi is None or s > hi else hi
    if lo is None or hi is None or hi <= lo:
        return None
    return (lo, hi)


def axis_from_vertices(vs):
    """Dominant principal axis of a solid's vertex cloud. For a w x w x L box this IS the beam
    axis, exactly. Used instead of a face-normal threshold because the normal route CANNOT see a
    steep member: a face at T from vertical has |nz| = sin(T), so any cap filter at |nz| >= c
    blinds the metric above asin(c). At c = 0.95 that hid an 80.5 deg member and reported 9.5
    (--cells 12, caught 2026-08-04). Geometry cannot be blinded that way."""
    n = float(len(vs))
    cx = sum(p[0] for p in vs) / n
    cy = sum(p[1] for p in vs) / n
    cz = sum(p[2] for p in vs) / n
    m = [[0.0] * 3 for _ in range(3)]
    for p in vs:
        d = (p[0] - cx, p[1] - cy, p[2] - cz)
        for i in range(3):
            for j in range(3):
                m[i][j] += d[i] * d[j]
    v = [0.3, 0.5, 0.81]
    for _ in range(60):
        w = [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]
        nrm = math.sqrt(sum(q * q for q in w))
        if nrm < 1e-18:
            return 0.0
        v = [q / nrm for q in w]
    return math.degrees(math.acos(min(1.0, abs(v[2]))))


def radial_wall(tris, A, nsample=3000, seed=20260804):
    """Probe the wall thickness DIRECTLY: fire rays outward from the axis at random (theta, z),
    walk the crossings carrying a winding depth (same rule tools/qa_stl.py:_solid_runs uses), and
    measure the solid run in r. Independent of any footprint or vertex-radius arithmetic."""
    import random
    rng = random.Random(seed)
    zs = [p[2] for t in tris for p in t]
    zlo, zhi = min(zs), max(zs)
    bins = {}
    for i, (a, b, c) in enumerate(tris):
        th0 = math.atan2(a[1], a[0])
        ths = []
        for p in (a, b, c):
            th = math.atan2(p[1], p[0])
            while th - th0 > math.pi:
                th -= 2 * math.pi
            while th0 - th > math.pi:
                th += 2 * math.pi
            ths.append(math.degrees(th))
        z0 = min(p[2] for p in (a, b, c))
        z1 = max(p[2] for p in (a, b, c))
        for d in range(int(math.floor(min(ths))), int(math.floor(max(ths))) + 1):
            for kz in range(int(z0 // 2.0), int(z1 // 2.0) + 1):
                bins.setdefault((d % 360, kz), []).append(i)

    runs = []
    tries = 0
    while len(runs) < nsample and tries < nsample * 60:
        tries += 1
        thd = rng.uniform(0.0, 360.0)
        z = rng.uniform(zlo + 0.05, zhi - 0.05)
        dx, dy = math.cos(math.radians(thd)), math.sin(math.radians(thd))
        hits = []
        for i in bins.get((int(thd) % 360, int(z // 2.0)), ()):
            a, b, c = tris[i]
            e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            px, py, pz = dy * e2[2] - 0.0 * e2[1], 0.0 * e2[0] - dx * e2[2], dx * e2[1] - dy * e2[0]
            det = e1[0] * px + e1[1] * py + e1[2] * pz
            if abs(det) < 1e-12:
                continue
            inv = 1.0 / det
            sx, sy, sz = -a[0], -a[1], z - a[2]
            u = (sx * px + sy * py + sz * pz) * inv
            if u < 0.0 or u > 1.0:
                continue
            qx = sy * e1[2] - sz * e1[1]
            qy = sz * e1[0] - sx * e1[2]
            qz = sx * e1[1] - sy * e1[0]
            vv = (dx * qx + dy * qy) * inv
            if vv < 0.0 or u + vv > 1.0:
                continue
            t = (e2[0] * qx + e2[1] * qy + e2[2] * qz) * inv
            if t <= 0.0:
                continue
            hits.append((t, -1 if det > 0 else 1))   # det>0 <=> ray meets the face front-on
        if len(hits) < 2:
            continue
        hits.sort()
        depth = 0
        start = None
        tot = 0.0
        for t, s in hits:
            was = depth
            depth += 1 if s < 0 else -1
            if was <= 0 and depth > 0:
                start = t
            elif was > 0 and depth <= 0 and start is not None:
                tot += t - start
                start = None
        if depth == 0 and start is None and tot > 1e-6:
            runs.append(tot)
    runs.sort()
    if not runs:
        return 0.0, 0.0, 0.0, 0
    return (runs[len(runs) // 2], runs[int(0.02 * len(runs))],
            runs[int(0.98 * len(runs))], len(runs))


def measure(path, A, meta):
    hdr, ntris, tris = read_stl(path)
    size = os.path.getsize(path)
    out = {"ntris": ntris, "size": size, "law": size == 84 + 50 * ntris,
           "hdr_ok": not hdr.startswith(b"solid")}

    # bbox + radial band
    xs = [p[0] for t in tris for p in t]
    ys = [p[1] for t in tris for p in t]
    zs = [p[2] for t in tris for p in t]
    out["bbox"] = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    rr = [math.hypot(p[0], p[1]) for t in tris for p in t]
    out["r_min"], out["r_max"] = min(rr), max(rr)

    # gross volume by the divergence theorem: exact per closed solid, so it DOUBLE COUNTS the
    # node overlaps. It is the independent upper bound the footprint measure has to sit under.
    gross = 0.0
    for a, b, c in tris:
        gross += (a[0] * (b[1] * c[2] - b[2] * c[1])
                  - a[1] * (b[0] * c[2] - b[2] * c[0])
                  + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    out["gross_volume"] = abs(gross)

    # face leans, recomputed normals (stored normals not trusted)
    worst_over = 0.0          # steepest SLOPED underside: the overhang angle from vertical
    n_flat_under = 0          # exactly-flat undersides, counted and reported, never hidden
    area_flat_under = 0.0
    degen = 0
    for a, b, c in tris:
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        m = math.sqrt(nx * nx + ny * ny + nz * nz)
        if m < 1e-9:
            degen += 1
            continue
        nzu = nz / m
        cz = (a[2] + b[2] + c[2]) / 3.0
        if cz <= 0.5 or nzu >= 0.0:
            continue
        if nzu <= -0.999:
            n_flat_under += 1
            area_flat_under += m / 2.0
        else:
            worst_over = max(worst_over, math.degrees(math.asin(min(1.0, -nzu))))
    out["degenerate"] = degen
    out["worst_overhang"] = worst_over
    out["n_flat_under"] = n_flat_under
    out["area_flat_under"] = area_flat_under

    # components -> per-solid vertex sets
    cid, ncomp = components(tris)
    verts = [set() for _ in range(ncomp)]
    cvol = [0.0] * ncomp                      # signed volume PER closed solid, divergence theorem
    for k, (a, b, c) in enumerate(tris):
        verts[cid[k]].update((a, b, c))
        cvol[cid[k]] += (a[0] * (b[1] * c[2] - b[2] * c[1])
                         - a[1] * (b[0] * c[2] - b[2] * c[0])
                         + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    out["ncomp"] = ncomp

    # The foot is the one solid that reaches the bed, so it is identified by measurement and not
    # by remembering which call emitted it. Its volume is exact: it overlaps nothing.
    bed_ids = [i for i in range(ncomp) if min(p[2] for p in verts[i]) <= 1e-6]
    out["n_bed_solids"] = len(bed_ids)
    out["foot_volume"] = sum(abs(cvol[i]) for i in bed_ids)

    r_mid = meta["r_mid"]
    C = meta["C"]
    rim, z_top = A.rim, meta["z_top"]
    polys = []
    lat_len = 0.0
    n_lat = 0
    n_bot = n_top = 0
    thicks = []
    worst_member = 0.0
    for vs in verts:
        vs = list(vs)
        zmin = min(p[2] for p in vs)
        zmax = max(p[2] for p in vs)
        cr = [math.hypot(p[0], p[1]) for p in vs]
        thicks.append(max(cr) - min(cr))     # radial extent WITHIN one solid: the wall
        if zmax <= rim + 1e-3:
            n_bot += 1
        elif zmax >= z_top - 1e-3:
            n_top += 1
        else:
            n_lat += 1
            d2 = [(p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                  for i, p in enumerate(vs) for q in vs[i + 1:]]
            dmax = math.sqrt(max(d2))
            dmin = math.sqrt(min(d2))                 # = the square section side, measured
            lat_len += math.sqrt(max(0.0, dmax * dmax - 2.0 * dmin * dmin))
            ang = axis_from_vertices(vs)
            if ang > worst_member:
                worst_member = ang
    out["n_bot_rim"] = n_bot
    out["n_top_ring"] = n_top
    out["n_lattice"] = n_lat
    out["thick_solid_med"] = thicks[len(thicks) // 2]
    out["worst_member"] = worst_member
    out["worst_angle"] = max(worst_member, out["worst_overhang"])
    out["lattice_box_len"] = lat_len
    out["lattice_node_len"] = lat_len - n_lat * meta["w"]   # boxes are extended w/2 per end

    # -- union footprint on the mid surface ---------------------------------------------
    # PER TRIANGLE, not per solid: the silhouette of a closed solid is exactly the union of the
    # silhouettes of its faces, and that needs no convexity. Hulling whole components was wrong --
    # the top ring is one component and is NOT convex, and its hull swallowed the whole scallop.
    dz = A.scan_dz
    tri2d = []
    for a, b, c in tris:
        th0 = math.atan2(a[1], a[0])
        pp = []
        for p in (a, b, c):
            th = math.atan2(p[1], p[0])
            while th - th0 > math.pi:
                th -= 2 * math.pi
            while th0 - th > math.pi:
                th += 2 * math.pi
            pp.append((r_mid * th, p[2]))
        zs3 = (pp[0][1], pp[1][1], pp[2][1])
        tri2d.append((min(zs3), max(zs3), pp))
    tri2d.sort(key=lambda t: t[0])
    zlo = tri2d[0][0]
    zhi = max(t[1] for t in tri2d)
    nrow = int(math.ceil((zhi - zlo) / dz))
    area = 0.0
    active = []
    idx = 0
    n = len(tri2d)
    for k in range(nrow):
        z = zlo + (k + 0.5) * dz
        while idx < n and tri2d[idx][0] <= z:
            active.append(tri2d[idx])
            idx += 1
        active = [t for t in active if t[1] >= z]
        iv = []
        for (_a0, _a1, pol) in active:
            sp = poly_span_at(pol, z)
            if sp is None:
                continue
            lo, hi = sp
            L = hi - lo
            lo %= C
            if lo + L <= C:
                iv.append((lo, lo + L))
            else:
                iv.append((lo, C))
                iv.append((0.0, lo + L - C))
        if not iv:
            continue
        iv.sort()
        tot = 0.0
        cs, ce = iv[0]
        for s, e in iv[1:]:
            if s > ce:
                tot += ce - cs
                cs, ce = s, e
            else:
                ce = max(ce, e)
        tot += ce - cs
        area += tot * dz
    out["solid_area"] = area
    out["shell_area"] = C * (zhi - zlo)
    out["open_frac"] = 1.0 - area / (C * (zhi - zlo))

    # -- wall thickness, probed directly: radial rays through the mesh ------------------
    out["wall"], out["wall_lo"], out["wall_hi"], out["wall_n"] = radial_wall(tris, A)

    # The union formula prices every millimetre of shell at `wall` thick. That is true of the
    # lattice and FALSE of the foot, which is deliberately wider. So the foot's z band is taken
    # out at the union rate and put back at the foot's own measured volume.
    band = C * A.rim * out["wall"]
    out["lattice_volume"] = area * out["wall"] - band
    out["volume"] = out["lattice_volume"] + out["foot_volume"]
    out["grams"] = out["volume"] * A.density / 1000.0
    out["foot_grams"] = out["foot_volume"] * A.density / 1000.0
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inner-dia", type=float, default=250.0)
    ap.add_argument("--height-rows", dest="rows", type=int, default=30)
    ap.add_argument("--cells", type=int, default=60, help="hex cells around")
    ap.add_argument("--member", type=float, default=SLICER_LINE_W,
                    help="member width AND wall thickness. Defaults to machine.py SLICER_LINE_W "
                         "so exactly one line fills a member with nothing left over -- the "
                         "cheapest printable wall that exists. 0.80 under an 0.82 line is what "
                         "made the slicer discard the whole part")
    ap.add_argument("--layer", type=float, default=SLICER_LAYER_H,
                    help="layer height (stacking budget). machine.py SLICER_LAYER_H")
    ap.add_argument("--apex-rise", type=float, default=5.5, help="hex apex rise b")
    ap.add_argument("--side", type=float, default=4.5, help="hex vertical side v")
    ap.add_argument("--rim", type=float, default=1.4)
    ap.add_argument("--foot-width", dest="foot_width", type=float, default=3.0 * SLICER_LINE_W,
                    help="radial width of the band ON THE BED. THREE line widths, so after the "
                         "0.15 mm of elephant foot eaten off each side of layer 1 there are still "
                         "two full first-layer lines with margin")
    ap.add_argument("--foot-flat", dest="foot_flat", type=float,
                    default=SLICER_FIRST_H + SLICER_LAYER_H,
                    help="height the full foot width is held before splaying back to --member. "
                         "One first layer plus one ordinary layer, so layer 1 is full width "
                         "throughout and layer 2 still lands on a band wider than a line")
    ap.add_argument("--ring-facets", type=int, default=720)
    ap.add_argument("--top-ring", dest="top_ring", action="store_true", default=True)
    ap.add_argument("--no-top-ring", dest="top_ring", action="store_false")
    ap.add_argument("--lean-max", type=float, default=55.0, help="qa_stl.py:58 LEAN_MAX_DEG")
    ap.add_argument("--density", type=float, default=1.24, help="g/cm3, handbook PLA")
    ap.add_argument("--scan-dz", type=float, default=0.1, help="z pitch of the area scanline")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "icecage_pointyhex.stl"))
    A = ap.parse_args()

    tris, meta = build(A)
    write_stl(A.out, tris)
    m = measure(A.out, A, meta)

    budget = A.member / 2.0
    shift = A.layer * math.tan(math.radians(m["worst_angle"]))
    print("== icecage_pointyhex -> %s ==" % A.out)
    print("DESIGN  ID %.1f  mid-D %.2f  C %.2f  cells %d  a %.4f  b %.2f  v %.2f  pitch %.2f"
          % (A.inner_dia, 2 * meta["r_mid"], meta["C"], A.cells, meta["a"], meta["b"],
             meta["v"], meta["pitch"]))
    print("DESIGN  rows %d (%d cells)  apex z %.2f  corbel %.2f  top z %.2f  rim %.2f"
          % (A.rows, A.rows * A.cells, meta["z_apex"], meta["corbel"], meta["z_top"], A.rim))
    print("DESIGN  foot %.2f wide on the bed for %.2f, splay %.2f/side back to %.2f by z %.2f "
          "-- taper leans %.2f deg from vertical"
          % (A.foot_width, A.foot_flat, meta["splay"], A.member, A.rim, meta["foot_lean"]))
    print("-- MEASURED OFF %s --" % os.path.basename(A.out))
    print("  triangles          %d" % m["ntris"])
    print("  filesize           %d bytes, 84+50*n = %d  %s"
          % (m["size"], 84 + 50 * m["ntris"], "OK" if m["law"] else "MISMATCH"))
    print("  binary header      %s" % ("ok" if m["hdr_ok"] else "STARTS b'solid' -- BAD"))
    print("  degenerate tris    %d" % m["degenerate"])
    print("  solids (comps)     %d  = %d foot + %d lattice members + %d top ring"
          % (m["ncomp"], m["n_bot_rim"], m["n_lattice"], m["n_top_ring"]))
    print("  solids on the bed  %d (min-z <= 0)" % m["n_bed_solids"])
    print("  bbox               %.2f x %.2f x %.2f mm" % m["bbox"])
    print("  radial band        r %.3f .. %.3f mm over the whole mesh" % (m["r_min"], m["r_max"]))
    print("  WALL probed        %.4f mm median, %.4f..%.4f at 2nd/98th pct of %d radial rays"
          % (m["wall"], m["wall_lo"], m["wall_hi"], m["wall_n"]))
    print("  member length      %.1f mm boxes, %.1f mm node-to-node centreline"
          % (m["lattice_box_len"], m["lattice_node_len"]))
    print("  solid footprint    %.1f mm2 of %.1f mm2 mid-surface" % (m["solid_area"], m["shell_area"]))
    print("  OPEN AREA          %.2f %%" % (100.0 * m["open_frac"]))
    print("  volume  UNION      %.1f mm3  (footprint x measured wall; +0.3%% angular-measure bias)"
          % m["volume"])
    print("  volume  gross      %.1f mm3  (divergence theorem, node overlaps double counted --"
          " the independent upper bound; union is %.1f%% of it)"
          % (m["gross_volume"], 100.0 * m["volume"] / m["gross_volume"]))
    print("  FOOT volume        %.1f mm3 = %.3f g  (divergence theorem on the solid that reaches"
          " the bed -- it overlaps nothing, so this is exact, not a union estimate)"
          % (m["foot_volume"], m["foot_grams"]))
    print("  MASS               %.2f g at %.2f g/cm3  = %.2f g lattice + %.2f g foot"
          % (m["grams"], A.density, m["lattice_volume"] * A.density / 1000.0, m["foot_grams"]))
    print("  WORST MEMBER       %.2f deg from vertical (principal axis of each lattice solid)"
          % m["worst_member"])
    print("  worst underside    %.2f deg from vertical (sloped downward faces)" % m["worst_overhang"])
    print("  flat undersides    %d faces, %.1f mm2 -- the vertical members' bottom caps, each"
          " landing on the pair of slants converging under it" % (m["n_flat_under"], m["area_flat_under"]))
    print("  STACKING at %.2f mm layers: shift %.4f mm/layer vs %.2f mm budget (half bead)  %s"
          % (A.layer, shift, budget, "OK" if shift < budget else "OVER"))

    if m["degenerate"]:
        print("GATE FAIL: %d degenerate triangles" % m["degenerate"])
        os.remove(A.out)
        sys.exit(1)
    if m["worst_angle"] > A.lean_max:
        print("GATE FAIL: worst measured angle %.2f deg > --lean-max %.2f (member %.2f, underside "
              "%.2f). At %.2f mm layers that is %.3f mm of sideways shift per layer against a "
              "%.2f mm half-bead budget: the bead hangs over air and droops. File removed."
              % (m["worst_angle"], A.lean_max, m["worst_member"], m["worst_overhang"],
                 A.layer, shift, budget))
        os.remove(A.out)
        sys.exit(1)
    print("GATE OK: worst angle %.2f <= %.2f" % (m["worst_angle"], A.lean_max))


if __name__ == "__main__":
    main()
