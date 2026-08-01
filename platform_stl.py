#!/usr/bin/env python3
"""platform_stl.py — the anti-vibration stand's TOP PLATFORM, as a watertight binary STL, NORMAL slice.

FIRST CUT for the owner to react to — geometry only, NOT a final design. See OPEN DECISIONS in report.

What the part IS (the printer sits on it):
  · a flat, rigid lobed PLATE, capped at ~340mm so it prints on the K2 bed (the printer footprint is
    ~355 and MAY slightly overhang — the K2 feet must land inside the plate; see caveats);
  · three LEG-TOP SOCKETS on the underside, in the SAME equilateral triangle as the base (v1 assumes
    VERTICAL legs, so the top triangle == the bottom triangle);
  · a BAMBOO pass-through hole through the plate at each socket centre — the rod runs up the leg and
    pins into/through the plate; the same hole is the gypsum fill/vent from the leg top to the top face;
  · the socket rings are SEGMENTED (gaps = fill ports) so slurry rising in a leg top oozes out around
    the leg and keys against the plate underside, setting monolithic.

v1 makes the plate a SOLID slab (slicer infill = mass + a flat rigid top). It is NOT a hollow gypsum
cavity like the base — the bamboo bores are the only gypsum path through it. Whether the platform
should instead be a fillable hollow shell for full gypsum continuity is an OPEN DECISION (see report).

MESH MODEL: same as base_stl.py — a soup of individually-WATERTIGHT closed sub-solids (the holey plate
slab + the segmented hanging socket-ring arcs) that INTERPENETRATE and are UNIONED BY THE SLICER.
verify() proves 0 non-paired edges (every sub-solid closed) and 0 degenerate triangles.

SLICE MODE: NORMAL. Print UPSIDE DOWN (flat top face on the bed = smooth finish + best adhesion,
socket rings pointing up) per the stand plan.

Usage: python3 platform_stl.py [--plat-dia 336] [--stance 110] [--socket-depth 18] ... --out platform.stl
"""
import argparse, math, os, struct


# ----------------------------------------------------------------------------- 2D profiles
def lobed(N, mean, amp, lobes, phase=0.0):
    pts = []
    for j in range(N):
        th = 2 * math.pi * j / N
        r = mean + amp * math.cos(lobes * (th - phase))
        pts.append((r * math.cos(th), r * math.sin(th)))
    return pts


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
    (px, py), (ax, ay), (bx, by), (cx, cy) = p, a, b, c
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    has_neg = (d1 < -eps) or (d2 < -eps) or (d3 < -eps)
    has_pos = (d1 > eps) or (d2 > eps) or (d3 > eps)
    return not (has_neg and has_pos)


def ear_clip(poly, test=None):
    """Ear-clip a simple/weakly-simple CCW polygon; predicates on `test` coords (indices into poly).
    Perturbed `test` coords de-coincide bridge duplicates so the clipper never stalls at the pinch,
    while emitted triangles use the real zero-width-slit coords (holes stay round)."""
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


def triangulate_with_holes(outer, holes):
    merged = list(outer)
    if not _ccw(merged):
        merged = merged[::-1]
    for hole in holes:
        h = list(hole)
        if _ccw(h):
            h = h[::-1]
        b = max(range(len(h)), key=lambda k: h[k][0] ** 2 + h[k][1] ** 2)
        M = h[b]
        rM = M[0] ** 2 + M[1] ** 2
        cand = [a for a in range(len(merged)) if merged[a][0] ** 2 + merged[a][1] ** 2 > rM]
        a = min(cand, key=lambda a: (merged[a][0] - M[0]) ** 2 + (merged[a][1] - M[1]) ** 2)
        hole_loop = [h[(b + t) % len(h)] for t in range(len(h))]
        merged = merged[:a + 1] + hole_loop + [hole_loop[0], merged[a]] + merged[a + 1:]
    test = [(x + 1e-6 * math.sin(i * 12.9898), y + 1e-6 * math.cos(i * 78.233))
            for i, (x, y) in enumerate(merged)]
    return merged, ear_clip(merged, test)


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


def add_arc_wall(tris, cx, cy, r_in, r_out, th0, th1, z0, z1, nseg):
    outer = []; inner = []
    for s in range(nseg + 1):
        th = th0 + (th1 - th0) * s / nseg
        outer.append((cx + r_out * math.cos(th), cy + r_out * math.sin(th)))
        inner.append((cx + r_in * math.cos(th), cy + r_in * math.sin(th)))
    for s in range(nseg):
        o0, o1 = outer[s], outer[s + 1]; i0, i1 = inner[s], inner[s + 1]
        oz0 = (o0[0], o0[1], z0); oz1 = (o0[0], o0[1], z1)
        pz0 = (o1[0], o1[1], z0); pz1 = (o1[0], o1[1], z1)
        tris.append((oz0, pz0, pz1)); tris.append((oz0, pz1, oz1))
        i0z0 = (i0[0], i0[1], z0); i0z1 = (i0[0], i0[1], z1)
        i1z0 = (i1[0], i1[1], z0); i1z1 = (i1[0], i1[1], z1)
        tris.append((i0z0, i1z1, i1z0)); tris.append((i0z0, i0z1, i1z1))
        tris.append((oz1, pz1, i1z1)); tris.append((oz1, i1z1, i0z1))
        tris.append((oz0, i1z0, pz0)); tris.append((oz0, i0z0, i1z0))
    o = outer[0]; i = inner[0]
    _quad(tris, (i[0], i[1], z0), (o[0], o[1], z0), (o[0], o[1], z1), (i[0], i[1], z1))
    o = outer[-1]; i = inner[-1]
    _quad(tris, (o[0], o[1], z0), (i[0], i[1], z0), (i[0], i[1], z1), (o[0], o[1], z1))


def _quad(tris, p0, p1, p2, p3):
    tris.append((p0, p1, p2)); tris.append((p0, p2, p3))


# ----------------------------------------------------------------------------- build the platform
def build(a):
    tris = []
    socket_od = a.socket_dia + 2 * a.socket_wall
    R = a.socket_dia / 2.0
    Ro = socket_od / 2.0
    peak_r = a.plat_dia / 2.0
    mean = peak_r - a.lobe_amp
    valley_r = mean - a.lobe_amp
    outer = lobed(a.points, mean, a.lobe_amp, a.lobes, math.radians(a.lobe_phase))

    z0 = a.socket_depth                          # underside of the plate
    z1 = a.socket_depth + a.plat_thick           # flat top face (printer sits here)

    centers = []
    for kk in range(3):
        th = math.radians(a.tri_phase + 120 * kk)
        centers.append((a.stance * math.cos(th), a.stance * math.sin(th)))
    socket_edge = a.stance + Ro                  # radial extent of a socket ring from plate centre
    holes = [circle(cx, cy, a.bamboo_dia / 2.0, a.hole_points, ccw=False) for (cx, cy) in centers]

    add_slab_with_holes(tris, outer, holes, z0, z1)      # solid plate + bamboo bores

    gap = a.port_frac * (2 * math.pi / a.ports)
    seg = (2 * math.pi / a.ports) - gap
    ring_z0 = 0.0
    ring_z1 = a.socket_depth + 2.0               # up INTO the plate (interpenetrate, no coincident face)
    arc_nseg = max(3, a.points // (2 * a.ports))
    for (cx, cy) in centers:
        for p in range(a.ports):
            th0 = 2 * math.pi * p / a.ports + gap / 2.0
            add_arc_wall(tris, cx, cy, R, Ro, th0, th0 + seg, ring_z0, ring_z1, arc_nseg)

    info = dict(peak_r=peak_r, valley_r=valley_r, socket_od=socket_od, socket_edge=socket_edge,
                centers=centers, z1=z1, socket_id=a.socket_dia)
    return tris, info


# ----------------------------------------------------------------------------- STL io + verify
def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris, header=b"crackle platform_stl top plate - normal-slice formwork"):
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plat-dia", type=float, default=336.0,
                    help="plate peak diameter mm; capped ~340 to fit the K2 bed (printer ~355 may overhang)")
    ap.add_argument("--stance", type=float, default=110.0,
                    help="foot-circle circumradius mm; MUST match the base. v1 = vertical legs so the "
                         "top triangle equals the bottom. Splayed legs (tighter top triangle) is a future "
                         "option — see report.")
    ap.add_argument("--tri-phase", type=float, default=90.0, help="angle of the first socket, deg")
    ap.add_argument("--leg-dia", type=float, default=64.0, help="leg mean diameter (reference)")
    ap.add_argument("--socket-clear", type=float, default=1.5, help="diametral clearance socket over leg")
    ap.add_argument("--socket-dia", type=float, default=None,
                    help="socket bore dia mm; default = leg-dia + socket-clear (=65.5)")
    ap.add_argument("--socket-wall", type=float, default=3.5, help="hanging ring wall thickness mm")
    ap.add_argument("--socket-depth", type=float, default=18.0, help="socket depth (leg-top insertion) mm")
    ap.add_argument("--plat-thick", type=float, default=12.0, help="plate thickness mm (solid; infill=mass)")
    ap.add_argument("--bamboo-dia", type=float, default=7.0, help="bamboo pass-through / fill-vent hole dia")
    ap.add_argument("--lobes", type=int, default=6, help="edge lobe count (alien-tech edge; top stays flat)")
    ap.add_argument("--lobe-amp", type=float, default=6.0, help="edge lobe amplitude mm")
    ap.add_argument("--lobe-phase", type=float, default=0.0, help="edge phase deg")
    ap.add_argument("--ports", type=int, default=3, help="fill ports (ring gaps) per socket")
    ap.add_argument("--port-frac", type=float, default=0.3, help="fraction of the ring that is gap")
    ap.add_argument("--points", type=int, default=120, help="edge samples")
    ap.add_argument("--hole-points", type=int, default=16, help="samples per bamboo bore")
    ap.add_argument("--out", default="platform.stl")
    a = ap.parse_args()
    if a.socket_dia is None:
        a.socket_dia = a.leg_dia + a.socket_clear

    tris, info = build(a)
    write_binary_stl(a.out, tris)
    n, open_edges, b = verify(a.out, tris)
    dx = b[1] - b[0]; dy = b[3] - b[2]; dz = b[5] - b[4]
    maxdim = max(dx, dy)
    fits = maxdim <= 340.0
    socket_inside = info['socket_edge'] <= info['valley_r']
    print(f"{a.out}: {n} triangles, {os.path.getsize(a.out)} bytes")
    print(f"  open (non-paired) edges: {open_edges}  [0 = every sub-solid closed/watertight]")
    print(f"  bounds  X {b[0]:.1f}..{b[1]:.1f}  Y {b[2]:.1f}..{b[3]:.1f}  Z {b[4]:.1f}..{b[5]:.1f}")
    print(f"  plate Ø peak {2*info['peak_r']:.1f} / valley {2*info['valley_r']:.1f}, thickness "
          f"{a.plat_thick:g}, total height {dz:.1f} mm")
    print(f"  socket bore Ø{info['socket_id']:.1f} (over Ø{a.leg_dia:g} leg), OD Ø{info['socket_od']:.1f}, "
          f"depth {a.socket_depth:g}, bamboo Ø{a.bamboo_dia:g}, {a.ports} ports x {int(a.port_frac*100)}% gap")
    print(f"  socket ring outer edge r={info['socket_edge']:.1f} <= plate valley r={info['valley_r']:.1f}: "
          f"{socket_inside}  [sockets fit inside the plate]")
    print("  socket centres: " + "  ".join(f"({cx:+.1f},{cy:+.1f})" for cx, cy in info['centers'])
          + f"  [r={a.stance:g}]")
    print(f"  FITS 340mm bed: {fits}  |  SLICE MODE: NORMAL, print UPSIDE DOWN (flat top on bed)")


if __name__ == "__main__":
    main()
