#!/usr/bin/env python3
"""foot_cup_stl.py — a STANCE-INDEPENDENT FOOT-CUP for the bamboo cross-brace stand base.

FIRST CUT for the owner to react to — geometry only. The base is no longer a disc: each leg stands on
one of these cups, and 3 identical cups are tied by horizontal bamboo rods into an equilateral triangle.
The stance = how long the owner cuts the rods, so exact dims do not matter — this is one good cup.

Prints PAD-DOWN, socket-UP, support-free. What it IS:
  1. a stable flat BASE PAD (Ø95) that sits on the floor;
  2. a LEG-SOCKET cup on top: a ROUND bore sized to the leg's PEAK diameter (Ø79.5 over the Ø77.5 leg
     peaks, ~1mm clearance, ~18mm deep, ~4mm walls). The leg twists, but its PEAK radius is constant, so
     it DROPS STRAIGHT IN at any rotation; the 4 lobe peaks locate it and the gypsum pour fills the valleys.
     (Not a clover bore: a keyed clover would have to be screwed in and would jam on print variance, and
     the socket is only a locator — the gypsum + bamboo + stance give the stability.)
  3. a VERTICAL Ø7 bamboo through-hole from the socket floor straight down through the pad (the rebar
     runs ground -> up the leg -> to the platform), plus gypsum PORTS around it so slurry poured down the
     leg reaches the pad/foot (the socket floor opens around the rod hole);
  4. TWO HORIZONTAL Ø7 bamboo sockets, ~30mm deep, 60deg apart (the interior angle of an equilateral
     triangle), symmetric about the piece's bisector — they take the two horizontal triangle rods to the
     neighbouring feet. Each enters on a FLAT facet and is a TEARDROP tunnel (apex up), so it bridges
     support-free when printed pad-down; a blind cap closes the inner end.

MESH MODEL: a soup of individually-WATERTIGHT closed sub-solids that INTERPENETRATE and are UNIONED BY
THE SLICER (same as base_stl.py). A horizontal blind bore is NOT a boolean subtraction (union can't
subtract) — it is built as an explicit connected tunnel: a flat facet with a teardrop hole, a teardrop
tube sweeping inward, and a blind teardrop cap. verify() proves 0 non-paired edges + 0 degenerate tris.

SLICE MODE: NORMAL, modest walls + light infill (a little gypsum fills the leg + cup for foot mass).
Fits any bed. Print pad-down.

Usage: python3 foot_cup_stl.py [--pad-dia 95] [--socket-depth 18] [--horiz-depth 30] ... --out foot_cup.stl
"""
import argparse, math, os, random, struct


# ----------------------------------------------------------------------------- 2D profiles
def circle(cx, cy, r, n, ccw=True):
    pts = [(cx + r * math.cos(2 * math.pi * j / n), cy + r * math.sin(2 * math.pi * j / n))
           for j in range(n)]
    return pts if ccw else pts[::-1]


def clover(cx, cy, mean_r, amp, lobes, n, phase=0.0, ccw=True):
    """A lobed 'clover' profile r(theta) = mean_r + amp*cos(lobes*(theta - phase)) — the SAME family
    the twisted-clover leg prints (leg_stl.py: radius = Rm + flute/2*cos(lobes*theta) at the foot,
    twist phase 0). Used for the leg-socket bore so it accepts the clover leg and keys its rotation."""
    pts = []
    for j in range(n):
        th = 2 * math.pi * j / n
        r = mean_r + amp * math.cos(lobes * (th - phase))
        pts.append((cx + r * math.cos(th), cy + r * math.sin(th)))
    return pts if ccw else pts[::-1]


def teardrop(cx, cy, r, n):
    """A teardrop for a horizontal bore: a circle whose top is two straight 50deg lines to an apex at
    +y (~1.556r). Printed with the bore axis horizontal and +y = world up, the roof stays STEEPER than
    the 45deg self-support limit at every facet (45deg flats put discretized facets exactly ON the
    limit; qa_stl caught 8 facets tipping past it). Returns a simple polygon of ~n points."""
    apex = (cx, cy + r / math.sin(math.radians(40.0)))
    a_lo, a_hi = math.radians(40.0), math.radians(140.0)         # tangent points of the 50deg flats
    pts = [apex]
    span = (a_lo + 2 * math.pi) - a_hi                           # bottom 270deg arc, a_hi -> a_lo+360
    m = max(3, n - 1)
    for i in range(m + 1):
        th = a_hi + span * i / m
        pts.append((cx + r * math.cos(th), cy + r * math.sin(th)))
    return pts


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
    (px, py), (ax, ay), (bx, by), (cx, cy) = p, a, b, c
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    return (d1 > eps and d2 > eps and d3 > eps) or (d1 < -eps and d2 < -eps and d3 < -eps)


def ear_clip(poly, test=None):
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
        best = None
        for mi, M in enumerate(h):
            for oi, O in enumerate(merged):
                d = (M[0] - O[0]) ** 2 + (M[1] - O[1]) ** 2
                if (best is None or d < best[0]) and _bridge_ok(M, O, merged, oi, h, mi):
                    best = (d, oi, mi)
        if best is None:
            mi = max(range(len(h)), key=lambda k: h[k][0] ** 2 + h[k][1] ** 2)
            M = h[mi]
            rM = M[0] ** 2 + M[1] ** 2
            cand = [a for a in range(len(merged)) if merged[a][0] ** 2 + merged[a][1] ** 2 > rM]
            oi = min(cand, key=lambda a: (merged[a][0] - M[0]) ** 2 + (merged[a][1] - M[1]) ** 2)
        else:
            _, oi, mi = best
        hole_loop = [h[(mi + t) % len(h)] for t in range(len(h))]
        merged = merged[:oi + 1] + hole_loop + [hole_loop[0], merged[oi]] + merged[oi + 1:]
    want = len(merged) - 2
    for seed in range(24):
        rng = random.Random(seed)
        test = [(x + rng.uniform(-1e-4, 1e-4), y + rng.uniform(-1e-4, 1e-4)) for (x, y) in merged]
        faces = ear_clip(merged, test)
        if len(faces) == want:
            return merged, faces
    return merged, faces


# ----------------------------------------------------------------------------- mesh builders
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


def add_tube(tris, outer2d, inner2d, z0, z1):
    n = len(outer2d)
    _add_side_wall(tris, outer2d, z0, z1, outward=True)
    _add_side_wall(tris, inner2d, z0, z1, outward=False)
    for j in range(n):
        k = (j + 1) % n
        o_j = outer2d[j]; o_k = outer2d[k]; i_j = inner2d[j]; i_k = inner2d[k]
        tris.append(((o_j[0], o_j[1], z1), (o_k[0], o_k[1], z1), (i_k[0], i_k[1], z1)))
        tris.append(((o_j[0], o_j[1], z1), (i_k[0], i_k[1], z1), (i_j[0], i_j[1], z1)))
        tris.append(((o_j[0], o_j[1], z0), (i_k[0], i_k[1], z0), (o_k[0], o_k[1], z0)))
        tris.append(((o_j[0], o_j[1], z0), (i_j[0], i_j[1], z0), (i_k[0], i_k[1], z0)))


def ngon(cx, cy, r, n, phase=0.0):
    return [(cx + r * math.cos(phase + 2 * math.pi * k / n),
             cy + r * math.sin(phase + 2 * math.pi * k / n)) for k in range(n)]


def cap_at(tris, outline, holes, z, up):
    """A single horizontal cap face (top or bottom) of an outline with holes, wound +z (up) or -z."""
    verts, faces = triangulate_with_holes(outline, holes)
    for (a, b, c) in faces:
        if up:
            tris.append(((verts[a][0], verts[a][1], z), (verts[b][0], verts[b][1], z),
                         (verts[c][0], verts[c][1], z)))
        else:
            tris.append(((verts[c][0], verts[c][1], z), (verts[b][0], verts[b][1], z),
                         (verts[a][0], verts[a][1], z)))


def add_wall_edge(tris, v0, v1, z0, z1):
    a = (v0[0], v0[1], z0); b = (v1[0], v1[1], z0); c = (v1[0], v1[1], z1); d = (v0[0], v0[1], z1)
    tris.append((a, b, c)); tris.append((a, c, d))


def add_horizontal_bore(tris, v0, v1, z0, z1, bore_r, depth, axis_z, tdrop_n):
    """Replace the flat wall on edge v0->v1 with: a face carrying a TEARDROP hole (the socket mouth),
    a teardrop TUNNEL swept `depth` inward, and a blind teardrop CAP. The tunnel mouth + tunnel end
    reuse the same teardrop points as the face hole + cap, so every edge pairs -> watertight."""
    dx, dy = v1[0] - v0[0], v1[1] - v0[1]
    W = math.hypot(dx, dy)
    ux, uy = dx / W, dy / W
    nx, ny = uy, -ux                                             # outward normal (right of v0->v1, CCW)

    def to3d(u, zz):
        return (v0[0] + ux * u, v0[1] + uy * u, zz)

    rect = [(0.0, z0), (W, z0), (W, z1), (0.0, z1)]
    td = teardrop(W / 2.0, axis_z, bore_r, tdrop_n)
    verts2, faces = triangulate_with_holes(rect, [td])           # the entry FACE with the mouth hole
    for (a, b, c) in faces:
        tris.append((to3d(*verts2[a]), to3d(*verts2[b]), to3d(*verts2[c])))
    inx, iny = -nx * depth, -ny * depth                          # sweep the mouth inward by depth
    for i in range(len(td)):
        t0 = td[i]; t1 = td[(i + 1) % len(td)]
        M0 = to3d(*t0); M1 = to3d(*t1)
        I0 = (M0[0] + inx, M0[1] + iny, M0[2]); I1 = (M1[0] + inx, M1[1] + iny, M1[2])
        tris.append((M0, M1, I1)); tris.append((M0, I1, I0))     # TUNNEL wall
    tv, tf = triangulate_with_holes(td, [])                      # blind CAP at the tunnel end
    for (a, b, c) in tf:
        A = to3d(*tv[a]); B = to3d(*tv[b]); C = to3d(*tv[c])
        A = (A[0] + inx, A[1] + iny, A[2]); B = (B[0] + inx, B[1] + iny, B[2]); C = (C[0] + inx, C[1] + iny, C[2])
        tris.append((A, C, B))


# ----------------------------------------------------------------------------- STL io + verify
def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris, header=b"crackle foot_cup_stl - bamboo cross-brace foot"):
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


# ----------------------------------------------------------------------------- build
def build(a):
    tris = []
    rod_r = a.bamboo_dia / 2.0
    bore_r = a.bamboo_dia / 2.0
    amp = a.flute / 2.0                                                  # leg clover lobe amplitude
    peak_r = a.socket_dia / 2.0 + amp                                    # leg OUTER (peak) radius = Rm + flute/2
    sock_in = peak_r + a.socket_clear                                    # ROUND bore over the leg PEAKS (drops in)
    sock_out = sock_in + a.socket_wall                                   # round cup outer wall
    pad_r = a.pad_dia / 2.0

    # HEXAGONAL pad: two ADJACENT hex faces are exactly 60deg apart (the equilateral-triangle interior
    # angle), which is where the two horizontal bamboo sockets go. Phase 0 -> vertices at 0,60,..300,
    # so edge0 (normal +30) and edge5 (normal -30) straddle the +x bisector symmetrically.
    verts = ngon(0.0, 0.0, pad_r, a.pad_sides, math.radians(a.pad_phase))
    bore_edges = {0, a.pad_sides - 1}                                    # the two edges sharing vertex 0

    # vertical holes: central rod hole + gypsum ports (placed between the bore azimuths)
    vhole = [circle(0.0, 0.0, rod_r, a.hole_points, ccw=False)]
    for kk in range(a.ports):
        pa = math.radians(a.port_phase + 360.0 * kk / a.ports)
        vhole.append(circle(a.port_r * math.cos(pa), a.port_r * math.sin(pa), a.port_dia / 2.0,
                            a.hole_points, ccw=False))

    cap_at(tris, verts, vhole, 0.0, up=False)                           # PAD bottom (-z)
    cap_at(tris, verts, vhole, a.pad_h, up=True)                        # PAD top  (+z, the socket floor)
    for i in range(a.pad_sides):                                        # PAD side walls
        v0 = verts[i]; v1 = verts[(i + 1) % a.pad_sides]
        if i in bore_edges:
            add_horizontal_bore(tris, v0, v1, 0.0, a.pad_h, bore_r, a.horiz_depth, a.horiz_z,
                                a.teardrop_points)
        else:
            add_wall_edge(tris, v0, v1, 0.0, a.pad_h)
    for h in vhole:                                                     # vertical hole walls
        _add_side_wall(tris, h, 0.0, a.pad_h, outward=False)

    cup_z0 = a.pad_h - 2.0                                              # interpenetrate the pad top
    cup_z1 = a.pad_h + a.socket_depth
    inner = circle(0.0, 0.0, sock_in, a.points)                        # ROUND bore over the leg peaks: the leg
    outer = circle(0.0, 0.0, sock_out, a.points)                       # twists but its PEAK radius is constant, so
    add_tube(tris, outer, inner, cup_z0, cup_z1)                       # it DROPS STRAIGHT IN at any rotation/depth

    info = dict(pad_r=pad_r, bore_r=sock_in, cup_outer_r=sock_out, peak_r=peak_r, height=cup_z1)
    return tris, info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pad-dia", type=float, default=105.0, help="base pad size (vertex circle) mm")
    ap.add_argument("--pad-sides", type=int, default=6,
                    help="pad polygon sides; 6 (hexagon) makes the two bore faces exactly 60deg apart")
    ap.add_argument("--pad-phase", type=float, default=0.0,
                    help="pad rotation deg; 0 -> the two bore faces straddle +x symmetrically")
    ap.add_argument("--pad-h", type=float, default=15.0,
                    help="pad thickness mm (thick enough to host the horizontal Ø7 bores + walls)")
    ap.add_argument("--socket-dia", type=float, default=64.0,
                    help="leg MEAN diameter mm (bore is sized to the PEAK = this/2 + flute/2)")
    ap.add_argument("--lobes", type=int, default=4, help="leg clover lobe count (for reference)")
    ap.add_argument("--flute", type=float, default=13.5, help="leg clover flute (peak-valley) depth mm")
    ap.add_argument("--socket-clear", type=float, default=1.0,
                    help="RADIAL clearance of the round bore over the leg PEAKS (generous = drops in easily)")
    ap.add_argument("--socket-wall", type=float, default=4.0, help="cup wall thickness mm")
    ap.add_argument("--socket-depth", type=float, default=18.0, help="cup depth mm")
    ap.add_argument("--bamboo-dia", type=float, default=7.0, help="bamboo rod hole dia mm (vert + horiz)")
    ap.add_argument("--ports", type=int, default=3, help="gypsum ports through the socket floor")
    ap.add_argument("--port-dia", type=float, default=7.0, help="gypsum port dia mm")
    ap.add_argument("--port-r", type=float, default=22.0, help="gypsum port radius from centre mm")
    ap.add_argument("--port-phase", type=float, default=90.0, help="first port angle deg")
    ap.add_argument("--horiz-depth", type=float, default=30.0, help="horizontal bamboo socket depth mm")
    ap.add_argument("--horiz-z", type=float, default=7.0, help="height of the horizontal bore axis mm")
    ap.add_argument("--points", type=int, default=96, help="samples around the pad/cup")
    ap.add_argument("--hole-points", type=int, default=16, help="samples per round hole")
    ap.add_argument("--teardrop-points", type=int, default=24, help="samples per teardrop bore")
    ap.add_argument("--out", default="foot_cup.stl")
    a = ap.parse_args()

    tris, info = build(a)
    write_binary_stl(a.out, tris)
    n, open_edges, b = verify(a.out, tris)
    dx = b[1] - b[0]; dy = b[3] - b[2]; dz = b[5] - b[4]
    print(f"{a.out}: {n} triangles, {os.path.getsize(a.out)} bytes")
    print(f"  open (non-paired) edges: {open_edges}  [0 = watertight]")
    print(f"  bounds  X {b[0]:.1f}..{b[1]:.1f}  Y {b[2]:.1f}..{b[3]:.1f}  Z {b[4]:.1f}..{b[5]:.1f}")
    print(f"  pad {a.pad_sides}-gon Ø{a.pad_dia:g} x {a.pad_h:g}, ROUND socket bore over the leg PEAKS "
          f"(leg peak r {info['peak_r']:.2f}), clearance {a.socket_clear:g} radial, depth {a.socket_depth:g}, height {dz:.1f}")
    print(f"  socket bore Ø{2*info['bore_r']:.2f} (r {info['bore_r']:.2f}); cup outer r {info['cup_outer_r']:.2f} "
          f"vs pad apothem {info['pad_r']*math.cos(math.pi/a.pad_sides):.2f} -- twisting leg drops straight in, "
          f"4 peaks locate it, gypsum fills the valleys")
    print(f"  vertical rod Ø{a.bamboo_dia:g} + {a.ports} gypsum ports Ø{a.port_dia:g} @ r{a.port_r:g}")
    print(f"  horizontal bores: 2 x Ø{a.bamboo_dia:g} TEARDROP (apex up, self-supporting), "
          f"{a.horiz_depth:g}mm deep, on 2 adjacent hex faces = {360.0/a.pad_sides:g}deg apart, axis z={a.horiz_z:g}")


if __name__ == "__main__":
    main()
