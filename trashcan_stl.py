#!/usr/bin/env python3
"""trashcan_stl.py — a PERSONALIZED WEIGHTED GIFT BIN (formwork shell + base-only cast).

What it IS: a thin-wall tapered OPEN bin (a wastebasket) whose BODY stays hollow but whose BOTTOM is a
closed, double-wall RING cavity you pour a sand+gypsum slurry into. The cast mass lives ONLY in that
base ring — a low, heavy skirt around the perimeter — so the bin sits with a low centre of gravity and
will not tip or blow over. A name stands proud on the side. One printed PLA part, sliced NORMAL.

HOW IT IS MODELLED (the crackle boolean-free union trick, same as foot_cup_stl.py): the part is a SOUP
of individually-watertight closed sub-solids that INTERPENETRATE; the SLICER unions the soup. Nothing
is CSG-subtracted. The sub-solids:
  BODY   * body wall  — a thin (--wall) tapered tube, open at the top (its own closed thin shell);
         * body floor — a solid disc that closes the bin over the base ring so trash rests on it.
  BASE   * outer wall tube + inner wall tube — the two thin walls of the ring cavity (a "double wall");
  RING   * floor disc — seals the underside + is the ground-contact base;
         * top annulus — caps the ring and carries the FILL PORT + a smaller VENT (holes to pour/breathe);
         * port collars — short upstanding spouts around those two holes (each a watertight pipe).
The GYPSUM fills the annular void between the inner and outer wall tubes, floor disc up to top annulus.

NAME: raised text is wrapped on the side ~2/3 up via emboss.emboss_on_cylinder (import emboss.py). Each
letter is its own watertight capsule-chain rib that interpenetrates the wall — no booleans.

STYLE: --style round (a smooth cone frustum) or faceted (a low-count polygon, a flat facet facing the
name). The base ring is always round (it is hidden inside the base).

HONEST STAGE / CAVEATS — READ. This is GEOMETRY ONLY and verified watertight IN SOFTWARE (the binary-STL
filesize law + edge parity). That is a mesh guarantee, NOT a proof that the print or the pour works:
  * The gypsum POUR IS UNPROVEN — nothing here has been physically cast. Do not phrase it as proven.
  * Set gypsum is BRITTLE and WATER-SOLUBLE. This is an INDOOR bin. The PLA shell is the wet face; the
    cast never touches water if the shell stays intact — SEAL the cast (the open port/vent especially)
    before use. A cracked shell + a wet cast is a failure.
  * The cast is BASE-ONLY by design (mass low, walls light) — the body is not reinforced and is not a
    load member; it is a liner, not structure.

FITS: default footprint (Ø top) is under the K2 Plus bed; a FITS_340 line is printed. Default --height
350 puts the Z extent at the machine's ~350mm ceiling — drop --height for margin.

Usage: python3 trashcan_stl.py [--name OLEG] [--height 350] [--top-dia 300] [--bottom-dia 260]
                               [--wall 1.2] [--base-ring-h 70] [--style round|faceted] [--points 160]
                               [--out trashcan.stl]
"""
import argparse, math, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emboss                                                        # noqa: E402  (raised-text ribs)

FACETS = 16                                                          # facet count for --style faceted
CAVITY_WIDTH = 18.0                                                  # radial width of the cast ring (mm)
GYPSUM_DENSITY = 0.0019                                              # g/mm^3  (1.9 g/cc sand+gypsum)


# ----------------------------------------------------------------------------- 2D profiles
def circle(cx, cy, r, n, phase=0.0, ccw=True):
    pts = [(cx + r * math.cos(phase + 2 * math.pi * j / n),
            cy + r * math.sin(phase + 2 * math.pi * j / n)) for j in range(n)]
    return pts if ccw else pts[::-1]


# ----------------------------------------------------------------------------- polygon triangulation
# (copied verbatim in spirit from foot_cup_stl.py — used only for the holed top annulus)
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
    import random
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
    faces = []
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


def _taper_wall(tris, bot, top, z0, z1, outward=True):
    """A ruled side wall between a bottom loop (@z0) and a top loop (@z1) of equal point count."""
    n = len(bot)
    for j in range(n):
        k = (j + 1) % n
        bj = bot[j]; bk = bot[k]; tj = top[j]; tk = top[k]
        lo_j = (bj[0], bj[1], z0); lo_k = (bk[0], bk[1], z0)
        hi_j = (tj[0], tj[1], z1); hi_k = (tk[0], tk[1], z1)
        if outward:
            tris.append((lo_j, lo_k, hi_k)); tris.append((lo_j, hi_k, hi_j))
        else:
            tris.append((lo_j, hi_k, lo_k)); tris.append((lo_j, hi_j, hi_k))


def add_tube_taper(tris, ob, ot, ib, it, z0, z1):
    """A closed thin tube (its own watertight solid): outer wall (ob@z0 -> ot@z1), inner wall
    (ib -> it), plus a top rim annulus (@z1) and a bottom rim annulus (@z0). Straight tubes pass the
    same loop as bottom and top; tapered tubes pass different-radius loops."""
    n = len(ob)
    _taper_wall(tris, ob, ot, z0, z1, outward=True)
    _taper_wall(tris, ib, it, z0, z1, outward=False)
    for j in range(n):                                              # top rim annulus @z1: ot -> it
        k = (j + 1) % n
        oj = ot[j]; ok = ot[k]; ij = it[j]; ik = it[k]
        tris.append(((oj[0], oj[1], z1), (ok[0], ok[1], z1), (ik[0], ik[1], z1)))
        tris.append(((oj[0], oj[1], z1), (ik[0], ik[1], z1), (ij[0], ij[1], z1)))
    for j in range(n):                                             # bottom rim annulus @z0: ob -> ib
        k = (j + 1) % n
        oj = ob[j]; ok = ob[k]; ij = ib[j]; ik = ib[k]
        tris.append(((oj[0], oj[1], z0), (ik[0], ik[1], z0), (ok[0], ok[1], z0)))
        tris.append(((oj[0], oj[1], z0), (ij[0], ij[1], z0), (ik[0], ik[1], z0)))


def add_solid_cylinder(tris, r, z0, z1, n, phase=0.0):
    """A solid closed disc/cylinder (its own watertight solid): side wall + a top cap and a bottom cap,
    each a triangle fan from the centre point."""
    loop = circle(0.0, 0.0, r, n, phase)
    _add_side_wall(tris, loop, z0, z1, outward=True)
    ct = (0.0, 0.0, z1); cb = (0.0, 0.0, z0)
    for j in range(n):
        k = (j + 1) % n
        aj = loop[j]; ak = loop[k]
        tris.append((ct, (aj[0], aj[1], z1), (ak[0], ak[1], z1)))          # top cap (up)
        tris.append((cb, (ak[0], ak[1], z0), (aj[0], aj[1], z0)))          # bottom cap (down)


def add_slab_with_holes(tris, outer2d, holes2d, z0, z1):
    """A solid slab (its own watertight solid) of an outer loop with holes cut in it: top + bottom
    faces (triangulated with the holes) and side walls for the outer loop and every hole loop."""
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


# ----------------------------------------------------------------------------- STL io + verify
def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris, header=b"crackle trashcan_stl - weighted gift bin (base-ring cast)"):
    with open(path, "wb") as fh:
        fh.write(header.ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            fh.write(struct.pack("<3f", *normal(a, b, c)))
            for v in (a, b, c):
                fh.write(struct.pack("<3f", *v))
            fh.write(struct.pack("<H", 0))


def verify(path, tris):
    """Assert the binary-STL laws and return (ntris, open_edge_count, degenerate, bounds).
    Laws: filesize == 84 + 50*ntris; header not 'solid'; header count == ntris; 0 degenerate tris.
    open_edges (undirected edges NOT shared by exactly 2 tris) MUST be 0 for a watertight mesh."""
    size = os.path.getsize(path)
    expect = 84 + 50 * len(tris)
    assert size == expect, f"filesize {size} != 84 + 50*{len(tris)} = {expect}"
    with open(path, "rb") as fh:
        head = fh.read(80)
        assert not head[:5].lower().startswith(b"solid"), "binary STL header must not begin with 'solid'"
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
    return count, open_edges, degen, bounds


# ----------------------------------------------------------------------------- build
def build(a):
    tris = []
    H = a.height
    wall = a.wall
    R0 = a.bottom_dia / 2.0                                          # body OUTER radius at the floor
    R1 = a.top_dia / 2.0                                             # body OUTER radius at the rim

    def Rb(z):                                                       # body outer radius at height z
        return R0 + (R1 - R0) * (z / H)

    n_body = a.points if a.style == "round" else FACETS
    ph_body = 0.0 if a.style == "round" else math.pi / FACETS        # faceted: a flat facet faces +x
    n = a.points                                                     # smooth rings for the hidden ring

    # --- BODY: thin tapered tube, open top -------------------------------------------------------
    ob = circle(0.0, 0.0, R0, n_body, ph_body)
    ot = circle(0.0, 0.0, R1, n_body, ph_body)
    ib = circle(0.0, 0.0, R0 - wall, n_body, ph_body)
    it = circle(0.0, 0.0, R1 - wall, n_body, ph_body)
    add_tube_taper(tris, ob, ot, ib, it, 0.0, H)

    # --- BASE RING geometry (all radii kept distinct so no two sub-solids share an exact edge) ----
    brh = a.base_ring_h
    z_ring0 = wall                                                   # cavity floor (top of ring floor)
    z_ring1 = brh - wall                                             # cavity ceiling (under top annulus)

    def Roo(z):                                                      # ring OUTER wall, outer face
        return Rb(z) - 0.6                                           # 0.6 buried in the body wall -> welds
    def Roi(z):                                                      # ring OUTER wall, inner face = cavity outer bound
        return Roo(z) - wall
    def Rio(z):                                                      # ring INNER wall, outer face = cavity inner bound
        return Roi(z) - CAVITY_WIDTH
    def Rii(z):                                                      # ring INNER wall, inner face
        return Rio(z) - wall

    # ring floor disc: seals the underside + is the ground-contact base (full solid disc)
    add_solid_cylinder(tris, R0 - 0.3, 0.0, wall + 0.3, n)

    # outer + inner wall tubes of the cast cavity (tapered to follow the body)
    add_tube_taper(tris,
                   circle(0, 0, Roo(z_ring0), n), circle(0, 0, Roo(z_ring1), n),
                   circle(0, 0, Roi(z_ring0), n), circle(0, 0, Roi(z_ring1), n),
                   z_ring0, z_ring1)
    add_tube_taper(tris,
                   circle(0, 0, Rio(z_ring0), n), circle(0, 0, Rio(z_ring1), n),
                   circle(0, 0, Rii(z_ring0), n), circle(0, 0, Rii(z_ring1), n),
                   z_ring0, z_ring1)

    # top annulus (caps the ring) carrying the FILL PORT + VENT holes
    port_r = 5.0                                                    # fill port hole radius (Ø10)
    vent_r = 2.5                                                    # vent hole radius (Ø5)
    r_pc = (Rio(z_ring1) + Roi(z_ring1)) / 2.0                      # ports centred in the cast band
    fill_ang = math.radians(160.0); vent_ang = math.radians(200.0)  # on the back, away from the name
    fill_c = (r_pc * math.cos(fill_ang), r_pc * math.sin(fill_ang))
    vent_c = (r_pc * math.cos(vent_ang), r_pc * math.sin(vent_ang))
    outer_ann = circle(0, 0, Roo(z_ring1) + 0.3, n)
    holes = [circle(0, 0, Rii(z_ring1) - 0.3, n, ccw=False),
             circle(fill_c[0], fill_c[1], port_r, 24, ccw=False),
             circle(vent_c[0], vent_c[1], vent_r, 20, ccw=False)]
    add_slab_with_holes(tris, outer_ann, holes, z_ring1, brh)

    # body floor: solid disc closing the bin over the central well (welds to inner wall + annulus)
    add_solid_cylinder(tris, Rio(z_ring1) + 1.5, brh - wall - 0.3, brh + 0.3, n)

    # port collars: short upstanding pour spouts around each hole (each a watertight pipe, bore
    # offset +0.4 from the hole so it never shares an edge with the annulus hole wall)
    for (cx, cy), br in ((fill_c, port_r), (vent_c, vent_r)):
        bore = br + 0.4
        zc0 = brh - wall - 0.1; zc1 = brh + 8.0
        add_tube_taper(tris,
                       circle(cx, cy, bore + wall, 24), circle(cx, cy, bore + wall, 24),
                       circle(cx, cy, bore, 24), circle(cx, cy, bore, 24),
                       zc0, zc1)

    # --- NAME: raised text wrapped on the side, ~2/3 up ------------------------------------------
    name_h = min(60.0, 0.16 * H)
    z_name = 0.66 * H
    if a.style == "round":
        cyl_r = Rb(z_name)
    else:
        cyl_r = Rb(z_name) * math.cos(math.pi / FACETS)             # facet inradius (text on the flat)
    if a.name:
        emboss.emboss_on_cylinder(tris, a.name, cyl_radius=cyl_r, z_center=z_name,
                                  angle_center_rad=0.0, height_mm=name_h)

    # --- cast mass (annular cavity, exact integral of a linear taper via the mid-height radius) ---
    zc_mid = (z_ring0 + z_ring1) / 2.0
    roi_mid = Roi(zc_mid)                                           # cavity outer bound at mid-height
    cav_h = z_ring1 - z_ring0
    cast_vol = math.pi * CAVITY_WIDTH * (2 * roi_mid - CAVITY_WIDTH) * cav_h   # pi*(Roi^2 - Rio^2)*h
    cast_mass = cast_vol * GYPSUM_DENSITY

    info = dict(name_h=name_h, z_name=z_name, cyl_r=cyl_r, r_pc=r_pc, port_r=port_r, vent_r=vent_r,
                cav_w=CAVITY_WIDTH, cav_h=cav_h, cast_vol=cast_vol, cast_mass=cast_mass,
                roi_mid=roi_mid, rio_mid=roi_mid - CAVITY_WIDTH)
    return tris, info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--height", type=float, default=350.0, help="bin height mm")
    ap.add_argument("--top-dia", type=float, default=300.0, help="top (rim) OUTER diameter mm")
    ap.add_argument("--bottom-dia", type=float, default=260.0, help="bottom OUTER diameter mm")
    ap.add_argument("--wall", type=float, default=1.2, help="shell wall thickness mm")
    ap.add_argument("--base-ring-h", type=float, default=70.0, help="height of the cast base ring mm")
    ap.add_argument("--style", choices=("round", "faceted"), default="round", help="body cross-section")
    ap.add_argument("--name", default="OLEG", help="raised name on the side ('' for none)")
    ap.add_argument("--points", type=int, default=160, help="samples per round ring")
    ap.add_argument("--out", default="trashcan.stl")
    a = ap.parse_args()

    tris, info = build(a)
    write_binary_stl(a.out, tris)
    ntris, open_edges, degen, b = verify(a.out, tris)
    dx = b[1] - b[0]; dy = b[3] - b[2]; dz = b[5] - b[4]
    fits = "PASS" if (dx <= 340.0 and dy <= 340.0) else "FAIL"

    print(f"{a.out}: {ntris} triangles, {os.path.getsize(a.out)} bytes")
    print(f"  open (non-paired) edges: {open_edges}  [0 = watertight]    degenerate: {degen}  [0 = ok]")
    print(f"  bounds  X {b[0]:.1f}..{b[1]:.1f}  Y {b[2]:.1f}..{b[3]:.1f}  Z {b[4]:.1f}..{b[5]:.1f}")
    print(f"  FITS_340: X {dx:.1f} Y {dy:.1f} <= 340 -> {fits}   (Z {dz:.1f}mm; default height sits at "
          f"the ~350mm machine ceiling — lower --height for margin)")
    print(f"  body: {a.style} tapered tube, bottom Ø{a.bottom_dia:g} -> rim Ø{a.top_dia:g}, "
          f"wall {a.wall:g}mm, open top, height {a.height:g}mm")
    print(f"  base ring: cast band width {info['cav_w']:g}mm x height {info['cav_h']:.1f}mm "
          f"(r {info['rio_mid']:.1f}..{info['roi_mid']:.1f}), fill port Ø{2*info['port_r']:g} + vent "
          f"Ø{2*info['vent_r']:g} @ r{info['r_pc']:.0f}")
    print(f"  CAST MASS (base only): {info['cast_vol']/1000.0:.0f} cc x 1.9 g/cc = "
          f"{info['cast_mass']:.0f} g  (~{info['cast_mass']/1000.0:.2f} kg) — POUR UNPROVEN, not yet cast")
    print(f"  name '{a.name}' raised {info['name_h']:.0f}mm tall, wrapped @ z{info['z_name']:.0f} "
          f"(~2/3 up) on r{info['cyl_r']:.1f}")


if __name__ == "__main__":
    main()
