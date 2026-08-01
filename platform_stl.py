#!/usr/bin/env python3
"""platform_stl.py — the stand's TOP PLATFORM as 3 PIE-WEDGE SEGMENTS, watertight binary STL, NORMAL slice.

FIRST CUT for the owner to react to — geometry only, NOT a final design. See OPEN DECISIONS in report.

WHY SEGMENTED: the K2 it holds has a ~355mm footprint, but we PRINT on the K2's ~340mm bed, so a
one-piece platform can't be big enough. The full platform is a ~Ø380 disc (the ~355 printer seats fully
with margin) SPLIT into 3 wedges of 120deg. A 120deg wedge of Ø380 is ~329mm across the chord, so each
piece fits the 340 bed (verified + reported per piece). Three legs, three wedges: one leg-top socket per
wedge, sitting on the leg triangle (r=110, same as the base).

Each wedge IS (thin-wall FORMWORK — the plaster is the mass, the PLA is the mould; installed top-up,
cavity mouth facing down):
  · a flat, closed TOP SKIN (thin — the slicer's solid top layers make it rigid; the printer sits here),
    a 120deg annular sector, lobed outer edge (alien-tech), with a central pour/vent hole when the 3
    assemble;
  · an OUTER RIM wall + an INNER HUB wall hanging down from the skin, enclosing a HOLLOW CAVITY (open on
    the underside) that fills with gypsum and becomes the platform's mass;
  · ONE leg-top SOCKET cup reaching down from the skin into the cavity, SEGMENTED (gaps = FILL PORTS) so
    gypsum poured up a leg exits the cup into the cavity — the socket OPENS INTO the interior;
  · a BAMBOO pass-through hole through the skin at the socket centre (rod pins through to the top face,
    and the hole vents air as the cavity fills);
  · SEAM REGISTRATION: each wedge carries a MALE puzzle tab on its low-angle radial edge and a matching
    FEMALE notch on its high-angle radial edge, both in the flat skin plane. The 3 identical wedges chain
    male->female at each seam so they self-align when assembled. The joints DO NOT bear load — gypsum +
    the bamboo cast tie the slab into one monolith across the open radial seams (the wedge cavities merge
    into one continuous cavity; only the outer rim is sealed at the seams). Registration is alignment only.

MESH MODEL: same as base_stl.py — a soup of individually-WATERTIGHT closed sub-solids (skin slab + outer
rim wall + inner hub wall + segmented socket-cup arcs) that INTERPENETRATE (never a coincident face) and
are UNIONED BY THE SLICER. verify() proves each WEDGE has 0 non-paired edges + 0 degenerate triangles.
No thick walls, no infill in the model — it is formwork.

SLICE MODE: NORMAL, ~2 walls, ~0% infill. Print each wedge UPSIDE DOWN (flat top skin flat on the bed:
smooth finish, best adhesion; the rim/hub/socket grow up, the cavity mouth is the open print-top, so no
wide roof needs bridging), then flip and assemble the 3.

Usage:
  python3 platform_stl.py                       # writes platform_seg1/2/3.stl + platform_assembled.stl
  python3 platform_stl.py --segment 2 --out w2.stl
"""
import argparse, math, os, random, struct


# ----------------------------------------------------------------------------- 2D helpers
def lobed_r(th, mean, amp, lobes, phase=0.0):
    return mean + amp * math.cos(lobes * (th - phase))


def circle(cx, cy, r, n, ccw=True):
    pts = [(cx + r * math.cos(2 * math.pi * j / n), cy + r * math.sin(2 * math.pi * j / n))
           for j in range(n)]
    return pts if ccw else pts[::-1]


# ----------------------------------------------------------------------------- polygon triangulation
def _area2(poly):
    s = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def _ccw(poly):
    return _area2(poly) > 0


def _in_tri(p, a, b, c, eps=1e-9):
    """STRICT interior: a point ON an edge/vertex counts as OUTSIDE, so a coincident bridge duplicate
    sitting at a triangle corner never blocks that ear (the inclusive version stalled the clipper)."""
    (px, py), (ax, ay), (bx, by), (cx, cy) = p, a, b, c
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    return (d1 > eps and d2 > eps and d3 > eps) or (d1 < -eps and d2 < -eps and d3 < -eps)


def ear_clip(poly, test=None):
    """Ear-clip a simple/weakly-simple CCW polygon (handles concave = the seam notch). Predicates on
    `test` coords (perturbed to de-coincide bridge duplicates); emitted triangles index `poly`."""
    P = test if test is not None else poly
    idx = list(range(len(poly)))
    tris = []

    def convex(a, b, c):
        ax, ay = P[a]; bx, by = P[b]; cx, cy = P[c]
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 1e-12

    guard = 0
    while len(idx) > 3 and guard < 100000:
        guard += 1
        m = len(idx)
        cut = False
        for i in range(m):
            a, b, c = idx[(i - 1) % m], idx[i], idx[(i + 1) % m]
            if not convex(a, b, c):
                continue
            if all(j in (a, b, c) or not _in_tri(P[j], P[a], P[b], P[c]) for j in idx):
                tris.append((a, b, c)); idx.pop(i); cut = True; break
        if not cut:
            break
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def _seg_cross(p1, p2, p3, p4):
    """Proper (interior) intersection of open segments p1p2 and p3p4."""
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = o(p3, p4, p1), o(p3, p4, p2), o(p1, p2, p3), o(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _pt_in_poly(p, poly):
    x, y = p
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _bridge_ok(M, O, merged, oi, hole, mi):
    """A bridge M(on hole)->O(on merged) is valid if its midpoint is inside `merged` and it crosses no
    edge of either loop (skipping the edges incident to O and M). Rotation-robust, unlike a radius test."""
    if not _pt_in_poly(((M[0] + O[0]) / 2.0, (M[1] + O[1]) / 2.0), merged):
        return False
    n = len(merged)
    for e in range(n):
        if e == oi or (e + 1) % n == oi:
            continue
        if _seg_cross(M, O, merged[e], merged[(e + 1) % n]):
            return False
    hn = len(hole)
    for e in range(hn):
        if e == mi or (e + 1) % hn == mi:
            continue
        if _seg_cross(M, O, hole[e], hole[(e + 1) % hn]):
            return False
    return True


def triangulate_with_holes(outer, holes):
    merged = list(outer)
    if not _ccw(merged):
        merged = merged[::-1]
    for hole in holes:
        h = list(hole)
        if _ccw(h):
            h = h[::-1]
        best = None                                    # shortest VALID bridge (visibility-checked)
        for mi, M in enumerate(h):
            for oi, O in enumerate(merged):
                d = (M[0] - O[0]) ** 2 + (M[1] - O[1]) ** 2
                if (best is None or d < best[0]) and _bridge_ok(M, O, merged, oi, h, mi):
                    best = (d, oi, mi)
        if best is None:                               # fallback: outermost-hole-vertex radial heuristic
            mi = max(range(len(h)), key=lambda k: h[k][0] ** 2 + h[k][1] ** 2)
            M = h[mi]
            rM = M[0] ** 2 + M[1] ** 2
            cand = [a for a in range(len(merged)) if merged[a][0] ** 2 + merged[a][1] ** 2 > rM]
            oi = min(cand, key=lambda a: (merged[a][0] - M[0]) ** 2 + (merged[a][1] - M[1]) ** 2)
        else:
            _, oi, mi = best
        hole_loop = [h[(mi + t) % len(h)] for t in range(len(h))]
        merged = merged[:oi + 1] + hole_loop + [hole_loop[0], merged[oi]] + merged[oi + 1:]
    # Ear-clip on a tiny RANDOM perturbation (de-coincides the doubled bridge vertices for the
    # predicates; emitted triangles use the real zero-width-slit coords). A fixed hash perturbation
    # aligned pathologically at some rotations and stalled; retry different seeds until the polygon
    # fully triangulates (faces == V-2), which the two-ears theorem guarantees for a simple polygon.
    want = len(merged) - 2
    for seed in range(24):
        rng = random.Random(seed)
        test = [(x + rng.uniform(-1e-4, 1e-4), y + rng.uniform(-1e-4, 1e-4)) for (x, y) in merged]
        faces = ear_clip(merged, test)
        if len(faces) == want:
            return merged, faces
    return merged, faces                                     # best effort; verify() will flag if short


# ----------------------------------------------------------------------------- mesh builders
def _quad(tris, p0, p1, p2, p3):
    tris.append((p0, p1, p2)); tris.append((p0, p2, p3))


def _add_side_wall(tris, loop2d, z0, z1, outward=True):
    n = len(loop2d)
    for j in range(n):
        k = (j + 1) % n
        aj = loop2d[j]; ak = loop2d[k]
        lo_j = (aj[0], aj[1], z0); lo_k = (ak[0], ak[1], z0)
        hi_j = (aj[0], aj[1], z1); hi_k = (ak[0], ak[1], z1)
        if outward:
            tris.append((lo_j, lo_k, hi_k)); tris.append((lo_j, hi_k, hi_j))
        else:
            tris.append((lo_j, hi_k, lo_k)); tris.append((lo_j, hi_j, hi_k))


def add_slab_with_holes(tris, outer2d, holes2d, z0, z1):
    verts, faces = triangulate_with_holes(outer2d, holes2d)
    for (a, b, c) in faces:
        tris.append(((verts[a][0], verts[a][1], z1), (verts[b][0], verts[b][1], z1),
                     (verts[c][0], verts[c][1], z1)))
    for (a, b, c) in faces:
        tris.append(((verts[c][0], verts[c][1], z0), (verts[b][0], verts[b][1], z0),
                     (verts[a][0], verts[a][1], z0)))
    _add_side_wall(tris, outer2d, z0, z1, outward=True)
    for hole in holes2d:
        _add_side_wall(tris, hole, z0, z1, outward=False)


def add_arc_wall(tris, cx, cy, r_in, r_out, th0, th1, z0, z1, nseg):
    """Constant-radius curved 'brick' (the socket cups); segments -> ports."""
    outer = []; inner = []
    for s in range(nseg + 1):
        th = th0 + (th1 - th0) * s / nseg
        outer.append((cx + r_out * math.cos(th), cy + r_out * math.sin(th)))
        inner.append((cx + r_in * math.cos(th), cy + r_in * math.sin(th)))
    add_curved_wall(tris, outer, inner, z0, z1)


def add_curved_wall(tris, outer_pts, inner_pts, z0, z1):
    """A closed thin curved wall between two matched arcs (outer/inner). Watertight open-loop 'tube':
    outer face, inner face, top & bottom strips, and an end cap at each end. Used for the rim + hub
    walls (per-theta lobed radius) and, via add_arc_wall, the socket cups."""
    n = len(outer_pts)
    for j in range(n - 1):
        o0, o1 = outer_pts[j], outer_pts[j + 1]
        a = (o0[0], o0[1], z0); b = (o1[0], o1[1], z0); c = (o1[0], o1[1], z1); d = (o0[0], o0[1], z1)
        tris.append((a, b, c)); tris.append((a, c, d))
        i0, i1 = inner_pts[j], inner_pts[j + 1]
        a2 = (i0[0], i0[1], z0); b2 = (i1[0], i1[1], z0); c2 = (i1[0], i1[1], z1); d2 = (i0[0], i0[1], z1)
        tris.append((a2, d2, c2)); tris.append((a2, c2, b2))
        # top strip (z1) and bottom strip (z0) across the wall thickness
        tris.append(((o0[0], o0[1], z1), (o1[0], o1[1], z1), (i1[0], i1[1], z1)))
        tris.append(((o0[0], o0[1], z1), (i1[0], i1[1], z1), (i0[0], i0[1], z1)))
        tris.append(((o0[0], o0[1], z0), (i1[0], i1[1], z0), (o1[0], o1[1], z0)))
        tris.append(((o0[0], o0[1], z0), (i0[0], i0[1], z0), (i1[0], i1[1], z0)))
    o, i = outer_pts[0], inner_pts[0]                              # end cap 0
    _quad(tris, (i[0], i[1], z0), (o[0], o[1], z0), (o[0], o[1], z1), (i[0], i[1], z1))
    o, i = outer_pts[-1], inner_pts[-1]                            # end cap n-1
    _quad(tris, (o[0], o[1], z0), (i[0], i[1], z0), (i[0], i[1], z1), (o[0], o[1], z1))


# ----------------------------------------------------------------------------- wedge geometry
def radial_edge(theta, r_from, r_to, tab_r0, tab_r1, tab_w, kind):
    """Points down one radial edge from r_from to r_to. kind='male' bumps OUT by tab_w over [tab_r0,
    tab_r1]; kind='female' notches IN by the same; kind='plain' is straight. The offset direction is
    (sin th, -cos th) (toward DECREASING angle) so a male at seam angle S mates a female at seam S."""
    ox, oy = math.sin(theta), -math.cos(theta)
    outward = 1 if r_to > r_from else -1
    rs = [r_from]
    if kind in ("male", "female"):
        rs += [tab_r0, tab_r1] if outward > 0 else [tab_r1, tab_r0]
    rs += [r_to]
    pts = []
    for r in rs:
        pts.append((r * math.cos(theta), r * math.sin(theta)))
    if kind == "plain":
        return [(r_from * math.cos(theta), r_from * math.sin(theta)),
                (r_to * math.cos(theta), r_to * math.sin(theta))]
    off = tab_w if kind == "male" else tab_w                       # male protrudes, female indents...
    sgn = +1 if kind == "male" else -1                             # ...female removes material (interior)
    a0 = (rs[1] * math.cos(theta) + sgn * off * ox, rs[1] * math.sin(theta) + sgn * off * oy)
    a1 = (rs[2] * math.cos(theta) + sgn * off * ox, rs[2] * math.sin(theta) + sgn * off * oy)
    return [pts[0], pts[1], a0, a1, pts[2], pts[3]]


def wedge_skin_polygon(center, half, r_inner, mean, amp, lobes, phase, arc_n, tab_r0, tab_r1, tab_w,
                       inset=0.0):
    # The skin is INSET half a wall thickness at both arcs so its outer edge is BURIED in the rim wall
    # and its inner edge in the hub wall (interpenetration, never a coincident face -> stays watertight).
    th0 = center - half                                            # low-angle radial edge  -> MALE
    th1 = center + half                                            # high-angle radial edge -> FEMALE
    ri = r_inner + inset
    r_out0 = lobed_r(th0, mean, amp, lobes, phase) - inset
    r_out1 = lobed_r(th1, mean, amp, lobes, phase) - inset
    poly = []
    poly += radial_edge(th0, ri, r_out0, tab_r0, tab_r1, tab_w, "male")          # out along th0 (male)
    for s in range(1, arc_n):                                                    # outer arc th0->th1
        th = th0 + (th1 - th0) * s / arc_n
        r = lobed_r(th, mean, amp, lobes, phase) - inset
        poly.append((r * math.cos(th), r * math.sin(th)))
    poly += radial_edge(th1, r_out1, ri, tab_r0, tab_r1, tab_w, "female")        # in along th1 (female)
    for s in range(1, arc_n):                                                    # inner arc th1->th0
        th = th1 - (th1 - th0) * s / arc_n
        poly.append((ri * math.cos(th), ri * math.sin(th)))
    # de-dupe consecutive coincident points
    out = []
    for p in poly:
        if not out or (abs(out[-1][0] - p[0]) > 1e-9 or abs(out[-1][1] - p[1]) > 1e-9):
            out.append(p)
    return out, th0, th1


def build_wedge(a, center_deg):
    tris = []
    # ROUND socket at the leg's PEAK radius (foot-cup lesson, 2026-08-01): the leg is a TWISTED clover,
    # so a keyed clover bore binds/jams; its PEAK radius is constant at every height, so a round bore at
    # peak + clearance accepts the leg top at any rotation. Peaks locate it; gypsum fills the valleys.
    s_bore = a.socket_dia / 2.0 + a.socket_flute / 2.0 + a.socket_clear   # bore r = leg peak + clearance
    s_out = s_bore + a.socket_wall                          # socket-ring outer radius
    socket_peak = s_out                                     # radial extent of the socket ring
    peak_r = a.dia / 2.0
    mean = peak_r - a.lobe_amp
    phase = math.radians(a.lobe_phase)
    center = math.radians(center_deg)
    half = math.radians(360.0 / a.segments / 2.0)          # wedge half-angle = 180/N

    z_mouth = 0.0
    z_skin0 = a.socket_depth
    z_skin1 = a.socket_depth + a.skin

    skin_poly, th0, th1 = wedge_skin_polygon(center, half, a.r_inner, mean, a.lobe_amp, a.lobes, phase,
                                             a.points, a.tab_r0, a.tab_r1, a.tab_w, inset=a.rim_wall / 2.0)
    sx, sy = a.stance * math.cos(center), a.stance * math.sin(center)             # this wedge's socket
    bamboo = circle(sx, sy, a.bamboo_dia / 2.0, a.hole_points, ccw=False)
    add_slab_with_holes(tris, skin_poly, [bamboo], z_skin0, z_skin1)              # top skin + bamboo bore

    # OUTER rim wall (lobed) + INNER hub wall (constant r_inner), both full height, thin
    arcN = a.points
    outer_o = []; outer_i = []; inner_o = []; inner_i = []
    for s in range(arcN + 1):
        th = th0 + (th1 - th0) * s / arcN
        ro = lobed_r(th, mean, a.lobe_amp, a.lobes, phase)
        outer_o.append((ro * math.cos(th), ro * math.sin(th)))
        outer_i.append(((ro - a.rim_wall) * math.cos(th), (ro - a.rim_wall) * math.sin(th)))
        inner_o.append(((a.r_inner + a.rim_wall) * math.cos(th), (a.r_inner + a.rim_wall) * math.sin(th)))
        inner_i.append((a.r_inner * math.cos(th), a.r_inner * math.sin(th)))
    add_curved_wall(tris, outer_o, outer_i, z_mouth, z_skin1)                     # outer rim
    add_curved_wall(tris, inner_o, inner_i, z_mouth, z_skin1)                     # inner hub

    # ROUND socket ring, segmented -> fill ports into the cavity. Round-at-peak: no phase, no keying;
    # the twisted leg top drops in at any rotation (see the foot-cup precedent).
    gap = a.port_frac * (2 * math.pi / a.ports)
    seg = (2 * math.pi / a.ports) - gap
    arc_nseg = max(4, a.points // (2 * a.ports))
    for p in range(a.ports):
        pth0 = 2 * math.pi * p / a.ports + gap / 2.0
        pth1 = pth0 + seg
        opts = []; ipts = []
        for t in range(arc_nseg + 1):
            th = pth0 + (pth1 - pth0) * t / arc_nseg
            ipts.append((sx + s_bore * math.cos(th), sy + s_bore * math.sin(th)))
            opts.append((sx + s_out * math.cos(th), sy + s_out * math.sin(th)))
        add_curved_wall(tris, opts, ipts, z_mouth, z_skin0 + 2.0)

    info = dict(peak_r=peak_r, socket_peak=socket_peak, socket=(sx, sy), z1=z_skin1,
                socket_id=a.socket_dia, th0=th0, th1=th1, r_inner=a.r_inner,
                sock_bore=s_bore)
    return tris, info


# ----------------------------------------------------------------------------- STL io + verify
def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris, header=b"crackle platform_stl wedge - normal-slice formwork"):
    with open(path, "wb") as fh:
        fh.write(header.ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            fh.write(struct.pack("<3f", *normal(a, b, c)))
            for v in (a, b, c):
                fh.write(struct.pack("<3f", *v))
            fh.write(struct.pack("<H", 0))


def verify(path, tris):
    size = os.path.getsize(path)
    expect = 84 + 50 * len(tris)
    assert size == expect, f"filesize {size} != 84+50*{len(tris)} = {expect}"
    with open(path, "rb") as fh:
        head = fh.read(80)
        assert not head[:5].lower().startswith(b"solid"), "binary STL header must not start 'solid'"
        (count,) = struct.unpack("<I", fh.read(4))
        assert count == len(tris), f"header count {count} != {len(tris)}"
        degen = 0
        edges = {}
        xs = []; ys = []; zs = []
        for _ in range(count):
            fh.read(12)
            vs = [struct.unpack("<3f", fh.read(12)) for _ in range(3)]
            fh.read(2)
            if normal(*vs) == (0.0, 0.0, 0.0):
                degen += 1
            for v in vs:
                xs.append(v[0]); ys.append(v[1]); zs.append(v[2])
            key = [(round(v[0], 3), round(v[1], 3), round(v[2], 3)) for v in vs]
            for i in range(3):
                e = tuple(sorted((key[i], key[(i + 1) % 3])))
                edges[e] = edges.get(e, 0) + 1
    assert degen == 0, f"{degen} degenerate (zero-area) triangles"
    open_edges = sum(1 for c in edges.values() if c != 2)
    bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
    return count, open_edges, bounds


def report(path, tris):
    n, oe, b = verify(path, tris)
    dx = b[1] - b[0]; dy = b[3] - b[2]; dz = b[5] - b[4]
    fits = max(dx, dy) <= 340.0
    print(f"{path}: {n} tris, {os.path.getsize(path)} bytes, open-edges {oe}, "
          f"bbox {dx:.1f} x {dy:.1f} x {dz:.1f} mm, FITS_340={fits}")
    return fits, (dx, dy, dz), oe


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia", type=float, default=380.0,
                    help="FULL platform PEAK diameter mm. Split into N wedges of 360/N deg; a wedge chord "
                         "is dia*sin(180/N) and MUST be < 340 to print (auto-checked below). e.g. Ø580 "
                         "needs N>=6 (chord ~290).")
    ap.add_argument("--segments", type=int, default=3, help="N: number of pie wedges to split into")
    ap.add_argument("--segment", default="all",
                    help="which wedge to emit: an int 1..N, or 'all' (writes N wedge STLs + a viz STL)")
    ap.add_argument("--stance", type=float, default=110.0,
                    help="leg-socket circumradius mm (one socket per wedge, at the wedge centre)")
    ap.add_argument("--tri-phase", type=float, default=90.0, help="angle of wedge-1's socket, deg")
    ap.add_argument("--r-inner", type=float, default=22.0,
                    help="inner (hub) radius mm; assembled -> a central Ø pour/vent hole")
    ap.add_argument("--socket-dia", type=float, default=64.0,
                    help="leg MEAN diameter mm (bore is ROUND at the PEAK = this/2 + flute/2)")
    ap.add_argument("--socket-flute", type=float, default=13.5,
                    help="leg clover flute (peak-valley) depth mm; sets the peak the round bore clears")
    ap.add_argument("--socket-clear", type=float, default=1.0,
                    help="RADIAL clearance of the round bore over the leg PEAKS (drops in at any rotation)")
    ap.add_argument("--socket-wall", type=float, default=3.5, help="socket-ring wall thickness mm")
    ap.add_argument("--socket-depth", type=float, default=18.0,
                    help="cavity depth = leg-top insertion depth mm")
    ap.add_argument("--skin", type=float, default=4.0, help="top-skin thickness mm (thin; solid at slice)")
    ap.add_argument("--rim-wall", type=float, default=4.0, help="outer-rim / inner-hub wall thickness mm")
    ap.add_argument("--bamboo-dia", type=float, default=7.0, help="bamboo pass-through / vent hole dia mm")
    ap.add_argument("--lobes", type=int, default=6, help="outer-edge lobe count (alien-tech; top flat)")
    ap.add_argument("--lobe-amp", type=float, default=6.0, help="outer-edge lobe amplitude mm")
    ap.add_argument("--lobe-phase", type=float, default=0.0, help="edge phase deg")
    ap.add_argument("--ports", type=int, default=3, help="fill ports (cup gaps) per socket")
    ap.add_argument("--port-frac", type=float, default=0.3, help="fraction of the cup ring that is gap")
    ap.add_argument("--tab-w", type=float, default=8.0, help="seam registration tab/notch depth mm")
    ap.add_argument("--tab-r0", type=float, default=70.0, help="registration tab inner radius mm")
    ap.add_argument("--tab-r1", type=float, default=120.0, help="registration tab outer radius mm")
    ap.add_argument("--points", type=int, default=60, help="arc samples per wedge")
    ap.add_argument("--hole-points", type=int, default=16, help="samples per bamboo bore")
    ap.add_argument("--out", default="platform.stl")
    a = ap.parse_args()

    N = a.segments
    base = a.out[:-4] if a.out.lower().endswith(".stl") else a.out
    wedge_deg = 360.0 / N
    chord = a.dia * math.sin(math.radians(180.0 / N))          # widest span of one wedge (outer chord)
    n_needed = math.ceil(math.pi / math.asin(min(0.999, 340.0 / a.dia)))
    print(f"# platform Ø{a.dia:g} (peak) split into N={N} wedges of {wedge_deg:g}deg; wedge outer chord "
          f"~{chord:.1f}mm {'<' if chord < 340 else '>='} 340 -> min N for this Ø = {n_needed}")
    bore_d = a.socket_dia + a.socket_flute + 2 * a.socket_clear
    print(f"# ROUND socket at leg PEAK: bore Ø{bore_d:g} (peak Ø{a.socket_dia + a.socket_flute:g} + "
          f"{a.socket_clear:g} radial), depth {a.socket_depth:g}; twisted leg drops in at any rotation; one per "
          f"wedge at stance r{a.stance:g}. r_inner {a.r_inner:g} (central Ø{2*a.r_inner:g} hole)")
    print(f"# thin-wall formwork: skin {a.skin:g}, rim/hub wall {a.rim_wall:g}, {a.ports} ports x "
          f"{int(a.port_frac*100)}% gap, bamboo Ø{a.bamboo_dia:g}, seam tab {a.tab_w:g}mm; slice NORMAL ~2 walls 0% infill")

    def emit(k, path):
        tris, info = build_wedge(a, a.tri_phase + wedge_deg * k)
        write_binary_stl(path, tris)
        fits, dims, oe = report(path, tris)
        sock_ok = info['socket_peak'] <= info['peak_r']       # socket inside the plate radius
        return (fits and oe == 0 and sock_ok), tris, info

    if a.segment == "all":
        all_tris = []
        oks = []
        for k in range(N):
            ok, tris, info = emit(k, f"{base}_seg{k+1}.stl")
            oks.append(ok)
            all_tris += tris
        apath = f"{base}_assembled.stl"                        # viz only: N pieces touching at seams
        write_binary_stl(apath, all_tris)
        xs = [v[0] for t in all_tris for v in t]
        ys = [v[1] for t in all_tris for v in t]
        print(f"{apath}: {len(all_tris)} tris, {os.path.getsize(apath)} bytes  [VIZ ONLY — {N} pieces, "
              f"not one manifold; full {max(xs)-min(xs):.1f} x {max(ys)-min(ys):.1f} mm, does NOT fit 340]")
        print(f"# all {N} wedges watertight + fit 340 + socket-inside: {all(oks)}")
    else:
        k = int(a.segment) - 1
        emit(k, a.out)


if __name__ == "__main__":
    main()
