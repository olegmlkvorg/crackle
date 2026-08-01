#!/usr/bin/env python3
"""base_stl.py — the anti-vibration stand's BASE PLINTH, as a watertight binary STL for a NORMAL slice.

FIRST CUT for the owner to react to — geometry only, NOT a final design. See the OPEN DECISIONS block
in the report; the fill-port flow in particular is unproven (see docstring end).

What the part IS (bottom-to-top, printed upright):
  · a wide, low ROSETTE tray — lobed (clover) outer rim wall + a floor — the beautiful-from-above face;
  · three LEG-FOOT SOCKETS (cups) standing on the floor in an equilateral triangle, each sized a hair
    over the Ø64 leg so a leg foot drops in and is located;
  · a BAMBOO pass-through hole through the floor at each socket centre (the 1/4" rod runs down the leg,
    through the base floor);
  · the cup walls are SEGMENTED (angular gaps = fill ports) so slurry poured down a leg exits the cup
    into the surrounding tray and sets monolithic; the tray's open top is where you pour the base itself;
  · a low containing rim so the base pour does not run off.

Why it is a hollow tray, not a solid disc: the stand is a MONOLITHIC gypsum+bamboo casting and the PLA
is only formwork. The tray holds the base pour; the ports tie base-gypsum to leg-gypsum; the rim
contains it. Mass (the fill) does the damping, not the plastic.

MESH MODEL: a soup of individually-WATERTIGHT closed sub-solids (rim tube, floor slab with holes, and
the segmented cup arcs) that INTERPENETRATE (never share a coincident face) and are UNIONED BY THE
SLICER. This is standard for a normal-mode slice; it is NOT one manifold. verify() proves every sub-
solid is closed (undirected edge parity == 2 everywhere) and has no degenerate triangles. Self-
intersections at the interpenetrations are resolved by the slicer's union, as intended.

SLICE MODE: NORMAL (multi-perimeter walls + your chosen infill / solid floor). NOT vase mode — it has
sockets, holes and a cavity. Print upright, floor on the bed.

UNPROVEN: whether the port count/size actually lets the sand+gypsum slurry flow well between leg and
tray is geometry-only here — it is the thing a first pour tests. Ports, socket clearance and rim are
all flags so the owner can tune before committing filament.

Usage: python3 base_stl.py [--stance 105] [--socket-depth 18] [--lobes 6] ... --out base.stl
"""
import argparse, math, os, struct


# ----------------------------------------------------------------------------- 2D profiles
def lobed(N, mean, amp, lobes, phase=0.0):
    """Rosette outline: r(theta) = mean + amp*cos(lobes*theta). Star-convex (single-valued r>0)."""
    pts = []
    for j in range(N):
        th = 2 * math.pi * j / N
        r = mean + amp * math.cos(lobes * (th - phase))
        pts.append((r * math.cos(th), r * math.sin(th)))
    return pts


def circle(cx, cy, r, n, ccw=True):
    pts = []
    for j in range(n):
        th = 2 * math.pi * j / n
        pts.append((cx + r * math.cos(th), cy + r * math.sin(th)))
    return pts if ccw else pts[::-1]


# ----------------------------------------------------------------------------- polygon triangulation
def _area2(poly):
    s = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def _ccw(poly):
    return _area2(poly) > 0


def _in_tri(p, a, b, c, eps=1e-9):
    """Strict interior test (on an edge/vertex counts as OUTSIDE, so bridge duplicates never block)."""
    (px, py), (ax, ay), (bx, by), (cx, cy) = p, a, b, c
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    has_neg = (d1 < -eps) or (d2 < -eps) or (d3 < -eps)
    has_pos = (d1 > eps) or (d2 > eps) or (d3 > eps)
    return not (has_neg and has_pos)


def ear_clip(poly, test=None):
    """Ear-clip a simple (or weakly-simple/bridged) CCW polygon. Returns index triples.

    Predicates run on `test` coords when given (indices still address `poly`). A bridged polygon
    is only WEAKLY simple — its doubled bridge vertices are coincident, which stalls a naive clipper
    at the pinch. Passing tiny-perturbed `test` coords (symbolic-perturbation lite) makes the loop
    STRICTLY simple for the predicates, so the two-ears theorem holds and it never stalls, while the
    emitted triangles use the real zero-width-slit coords (holes stay round, no material removed)."""
    P = test if test is not None else poly
    n = len(poly)
    idx = list(range(n))
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
            ok = True
            for j in idx:
                if j in (a, b, c):
                    continue
                if _in_tri(P[j], P[a], P[b], P[c]):
                    ok = False
                    break
            if ok:
                tris.append((a, b, c))
                idx.pop(i)
                cut = True
                break
        if not cut:                       # no ear found — leave the rest (verify will flag if wrong)
            break
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def triangulate_with_holes(outer, holes):
    """Cut each hole into the outer loop with a doubled radial bridge, then ear-clip. Returns
    (verts, faces): verts a list of (x,y), faces a list of index triples (CCW = +z up)."""
    merged = list(outer)
    if not _ccw(merged):
        merged = merged[::-1]
    for hole in holes:
        h = list(hole)
        if _ccw(h):                        # holes must run CW so the bridged polygon stays simple
            h = h[::-1]
        b = max(range(len(h)), key=lambda k: h[k][0] ** 2 + h[k][1] ** 2)   # outermost hole vertex
        M = h[b]
        rM = M[0] ** 2 + M[1] ** 2
        cand = [a for a in range(len(merged)) if merged[a][0] ** 2 + merged[a][1] ** 2 > rM]
        a = min(cand, key=lambda a: (merged[a][0] - M[0]) ** 2 + (merged[a][1] - M[1]) ** 2)
        hole_loop = [h[(b + t) % len(h)] for t in range(len(h))]
        merged = merged[:a + 1] + hole_loop + [hole_loop[0], merged[a]] + merged[a + 1:]
    # de-coincide the doubled bridge vertices for the PREDICATES only (see ear_clip docstring)
    test = [(x + 1e-6 * math.sin(i * 12.9898), y + 1e-6 * math.cos(i * 78.233))
            for i, (x, y) in enumerate(merged)]
    faces = ear_clip(merged, test)
    return merged, faces


# ----------------------------------------------------------------------------- mesh builders (append tris)
def add_slab_with_holes(tris, outer2d, holes2d, z0, z1):
    verts, faces = triangulate_with_holes(outer2d, holes2d)
    for (a, b, c) in faces:                                    # top (+z)
        tris.append(((verts[a][0], verts[a][1], z1), (verts[b][0], verts[b][1], z1),
                     (verts[c][0], verts[c][1], z1)))
    for (a, b, c) in faces:                                    # bottom (-z)
        tris.append(((verts[c][0], verts[c][1], z0), (verts[b][0], verts[b][1], z0),
                     (verts[a][0], verts[a][1], z0)))
    _add_side_wall(tris, outer2d, z0, z1, outward=True)        # outer rim of the slab
    for hole in holes2d:                                       # each bamboo bore
        _add_side_wall(tris, hole, z0, z1, outward=False)


def _add_side_wall(tris, loop2d, z0, z1, outward=True):
    n = len(loop2d)
    for j in range(n):
        k = (j + 1) % n
        aj = (loop2d[j][0], loop2d[j][1])
        ak = (loop2d[k][0], loop2d[k][1])
        lo_j = (aj[0], aj[1], z0); lo_k = (ak[0], ak[1], z0)
        hi_j = (aj[0], aj[1], z1); hi_k = (ak[0], ak[1], z1)
        if outward:
            tris.append((lo_j, lo_k, hi_k)); tris.append((lo_j, hi_k, hi_j))
        else:
            tris.append((lo_j, hi_k, lo_k)); tris.append((lo_j, hi_j, hi_k))


def add_tube(tris, outer2d, inner2d, z0, z1):
    """Closed annular tube: outer + inner side walls + top and bottom annular caps."""
    n = len(outer2d)
    _add_side_wall(tris, outer2d, z0, z1, outward=True)
    _add_side_wall(tris, inner2d, z0, z1, outward=False)
    for j in range(n):                                         # caps: annulus quads outer<->inner
        k = (j + 1) % n
        o_j = outer2d[j]; o_k = outer2d[k]; i_j = inner2d[j]; i_k = inner2d[k]
        # top (+z)
        tris.append(((o_j[0], o_j[1], z1), (o_k[0], o_k[1], z1), (i_k[0], i_k[1], z1)))
        tris.append(((o_j[0], o_j[1], z1), (i_k[0], i_k[1], z1), (i_j[0], i_j[1], z1)))
        # bottom (-z)
        tris.append(((o_j[0], o_j[1], z0), (i_k[0], i_k[1], z0), (o_k[0], o_k[1], z0)))
        tris.append(((o_j[0], o_j[1], z0), (i_j[0], i_j[1], z0), (i_k[0], i_k[1], z0)))


def add_arc_wall(tris, cx, cy, r_in, r_out, th0, th1, z0, z1, nseg):
    """A curved wall 'brick': outer & inner arc faces, two radial end caps, top & bottom. Watertight.
    Segmenting a cup into arcs (with gaps between) is how the fill PORTS are formed."""
    outer = []; inner = []
    for s in range(nseg + 1):
        th = th0 + (th1 - th0) * s / nseg
        outer.append((cx + r_out * math.cos(th), cy + r_out * math.sin(th)))
        inner.append((cx + r_in * math.cos(th), cy + r_in * math.sin(th)))
    for s in range(nseg):                                      # outer arc (out) & inner arc (in)
        o0, o1 = outer[s], outer[s + 1]; i0, i1 = inner[s], inner[s + 1]
        oz0 = (o0[0], o0[1], z0); oz1 = (o0[0], o0[1], z1)
        pz0 = (o1[0], o1[1], z0); pz1 = (o1[0], o1[1], z1)
        tris.append((oz0, pz0, pz1)); tris.append((oz0, pz1, oz1))
        i0z0 = (i0[0], i0[1], z0); i0z1 = (i0[0], i0[1], z1)
        i1z0 = (i1[0], i1[1], z0); i1z1 = (i1[0], i1[1], z1)
        tris.append((i0z0, i1z1, i1z0)); tris.append((i0z0, i0z1, i1z1))
        # top & bottom quads across the wall thickness
        tris.append((oz1, pz1, i1z1)); tris.append((oz1, i1z1, i0z1))          # top
        tris.append((oz0, i1z0, pz0)); tris.append((oz0, i0z0, i1z0))          # bottom
    for (a, b) in ((0, -1),):                                  # two radial END CAPS (close the brick)
        pass
    # end cap at th0
    o = outer[0]; i = inner[0]
    _quad(tris, (i[0], i[1], z0), (o[0], o[1], z0), (o[0], o[1], z1), (i[0], i[1], z1))
    # end cap at th1
    o = outer[-1]; i = inner[-1]
    _quad(tris, (o[0], o[1], z0), (i[0], i[1], z0), (i[0], i[1], z1), (o[0], o[1], z1))


def _quad(tris, p0, p1, p2, p3):
    tris.append((p0, p1, p2)); tris.append((p0, p2, p3))


# ----------------------------------------------------------------------------- build the base
def build(a):
    tris = []
    R = a.socket_dia / 2.0                       # socket inner radius (over the leg)
    socket_od = a.socket_dia + 2 * a.socket_wall
    Ro = socket_od / 2.0

    # rosette wall: inner valley must clear the cup outer edge by base_margin
    valley_in = a.stance + Ro + a.base_margin    # required MIN inner radius of the rim wall
    mean_in = valley_in + a.lobe_amp
    mean_out = mean_in + a.rim_wall
    peak_out = mean_out + a.lobe_amp
    outer = lobed(a.points, mean_out, a.lobe_amp, a.lobes, math.radians(a.lobe_phase))
    inner = lobed(a.points, mean_in, a.lobe_amp, a.lobes, math.radians(a.lobe_phase))

    top = a.floor + a.rim_height                 # total height
    add_tube(tris, outer, inner, 0.0, top)       # the containing rosette rim/wall (full height)

    # floor slab, edge buried inside the wall (interpenetrates -> no coincident face), with bamboo bores
    floor_outer = lobed(a.points, mean_out - a.rim_wall / 2.0, a.lobe_amp, a.lobes,
                        math.radians(a.lobe_phase))
    centers = []
    for kk in range(3):
        th = math.radians(a.tri_phase + 120 * kk)
        centers.append((a.stance * math.cos(th), a.stance * math.sin(th)))
    holes = [circle(cx, cy, a.bamboo_dia / 2.0, a.hole_points, ccw=False) for (cx, cy) in centers]
    add_slab_with_holes(tris, floor_outer, holes, 0.0, a.floor)

    # three segmented socket cups standing on the floor (start below it -> interpenetrate, no coincidence)
    gap = a.port_frac * (2 * math.pi / a.ports)  # angular size of each gap (a port)
    seg = (2 * math.pi / a.ports) - gap          # angular size of each wall arc
    cup_z0 = a.floor - 2.0
    cup_z1 = a.floor + a.socket_depth
    arc_nseg = max(3, a.points // (2 * a.ports))
    for (cx, cy) in centers:
        for p in range(a.ports):
            th0 = 2 * math.pi * p / a.ports + gap / 2.0
            add_arc_wall(tris, cx, cy, R, Ro, th0, th0 + seg, cup_z0, cup_z1, arc_nseg)

    info = dict(mean_out=mean_out, peak_out=peak_out, mean_in=mean_in, valley_in=mean_in - a.lobe_amp,
                socket_od=socket_od, centers=centers, top=top, socket_id=a.socket_dia)
    return tris, info


# ----------------------------------------------------------------------------- STL io + verify
def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris, header=b"crackle base_stl plinth - normal-slice formwork"):
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
    ap.add_argument("--stance", type=float, default=110.0,
                    help="foot-circle circumradius mm (leg-foot centres on a circle of this radius). "
                         "Default 110 (Ø220 feet). The owner asked for ~150 (Ø300): IMPOSSIBLE on a 340 "
                         "bed — the socket edge alone would sit at Ø372.5, and the whole plinth at ~Ø425. "
                         "The absolute max single-piece stance on a 340 bed is ~123. Tip-over stability is "
                         "the plinth-disc footprint (~Ø335 here), not this circle; a wider circle only "
                         "improves anti-racking of the upper mass and needs a segmented base to exceed 123.")
    ap.add_argument("--tri-phase", type=float, default=90.0, help="angle of the first foot, deg")
    ap.add_argument("--leg-dia", type=float, default=64.0, help="leg mean diameter (for reference)")
    ap.add_argument("--socket-clear", type=float, default=1.5, help="diametral clearance socket over leg")
    ap.add_argument("--socket-dia", type=float, default=None,
                    help="socket bore dia mm; default = leg-dia + socket-clear (=65.5)")
    ap.add_argument("--socket-wall", type=float, default=3.5, help="cup wall thickness mm")
    ap.add_argument("--socket-depth", type=float, default=18.0, help="cup depth (leg foot insertion) mm")
    ap.add_argument("--bamboo-dia", type=float, default=7.0, help="bamboo pass-through hole dia mm")
    ap.add_argument("--lobes", type=int, default=6, help="rosette lobe count (0-ish look: raise amp)")
    ap.add_argument("--lobe-amp", type=float, default=6.0, help="rosette lobe amplitude mm")
    ap.add_argument("--lobe-phase", type=float, default=0.0, help="rosette phase deg")
    ap.add_argument("--base-margin", type=float, default=4.0, help="radial gap cup-edge -> rim inner valley")
    ap.add_argument("--floor", type=float, default=4.0, help="floor slab thickness mm")
    ap.add_argument("--rim-height", type=float, default=30.0, help="rim height above the floor mm")
    ap.add_argument("--rim-wall", type=float, default=5.0, help="rim wall thickness mm")
    ap.add_argument("--ports", type=int, default=3, help="fill ports (wall gaps) per socket cup")
    ap.add_argument("--port-frac", type=float, default=0.3, help="fraction of the cup ring that is gap")
    ap.add_argument("--points", type=int, default=120, help="rosette samples around the rim")
    ap.add_argument("--hole-points", type=int, default=16, help="samples per bamboo bore")
    ap.add_argument("--out", default="base.stl")
    a = ap.parse_args()
    if a.socket_dia is None:
        a.socket_dia = a.leg_dia + a.socket_clear

    tris, info = build(a)
    write_binary_stl(a.out, tris)
    n, open_edges, b = verify(a.out, tris)
    dx = b[1] - b[0]; dy = b[3] - b[2]; dz = b[5] - b[4]
    maxdim = max(dx, dy)
    fits = maxdim <= 340.0
    print(f"{a.out}: {n} triangles, {os.path.getsize(a.out)} bytes")
    print(f"  open (non-paired) edges: {open_edges}  [0 = every sub-solid closed/watertight]")
    print(f"  bounds  X {b[0]:.1f}..{b[1]:.1f}  Y {b[2]:.1f}..{b[3]:.1f}  Z {b[4]:.1f}..{b[5]:.1f}")
    print(f"  footprint {dx:.1f} x {dy:.1f} mm (rosette Ø peak {2*info['peak_out']:.1f}, valley "
          f"{2*info['valley_in']:.1f}), height {dz:.1f} mm")
    print(f"  socket bore Ø{info['socket_id']:.1f} (over Ø{a.leg_dia:g} leg), OD Ø{info['socket_od']:.1f}, "
          f"depth {a.socket_depth:g}, bamboo Ø{a.bamboo_dia:g}, {a.ports} ports x {int(a.port_frac*100)}% gap")
    print("  foot centres: " + "  ".join(f"({cx:+.1f},{cy:+.1f})" for cx, cy in info['centers'])
          + f"  [r={a.stance:g}]")
    print(f"  FITS 340mm bed: {fits}  |  SLICE MODE: NORMAL (walls + infill), print floor-down")


if __name__ == "__main__":
    main()
