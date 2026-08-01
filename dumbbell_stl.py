#!/usr/bin/env python3
"""dumbbell_stl.py — a PERSONALIZED GIFT DUMBBELL: two cast-mass ends on a rod core, printed as
thin PLA FORMWORK. Emits the two identical END shells + the GRIP sleeve as separate STLs.

WHAT IT IS (a gift / trophy, NOT a competition weight — 1..6 kg sweet spot):
  * Each END is a SELF-SUPPORTING HOLLOW DOME vessel — a gumdrop/bell whose outer radius is WIDEST at
    the base and only ever narrows going up to a small OPEN pour hole at the top. It is sized so its
    inner cavity holds exactly the gypsum needed for the target weight (per-end fill = weight/density/2).
    You print the dome BASE-DOWN (no support), stand the rod up through the base hole, pour a gypsum+sand
    mix (~1.9 g/cc) in through the OPEN TOP, and the mass casts around the rod tip. The recipient's NAME
    is a raised bead wrapped on the near-vertical SIDE band (imported emboss.py, boolean-free).
  * The GRIP is a knurled/fluted tube sleeve with a central rod bore.

HARD RULE — THE ROD CORE IS MANDATORY (baked in, like the stand's rebar): a bamboo (Ø6.35) or steel
(Ø~12) ROD runs the whole length — through the grip's through-bore and into each cast end, where its
tip is embedded in the gypsum. The rod is the TENSILE / BENDING member; the gypsum is cheap mass; the
PLA is only the mould + grip sleeve. A solid gypsum handle with NO rod SNAPS in bending — never omit it.

BALANCE: the two ends are IDENTICAL by construction (same STL, printed twice). Do not scale one end
without the other or the dumbbell will be lopsided.

WHY THE DOME PRINTS WITHOUT SUPPORT: the outer silhouette r(z) = r_top + (R_base-r_top)*(1-(z/H)^p)^q
is MONOTONICALLY NON-INCREASING, so every layer is <= the one below (no outer overhang anywhere). The
height H is auto-scaled so the steepest wall slope |dr/dz| stays at MAX_WALL_SLOPE (0.70 = 35deg off
vertical, well under 45), which bounds the inner cavity skin's downward tilt to nz > -0.58 — under the
support threshold. There is NO flat internal ceiling and NO sealed cavity: the top is an OPEN pour hole,
so the interior is reachable from outside and needs no support to remove. build_end runs an overhang
check on the emitted STL (see overhang_report) that MEASURES this: ~0 support-needing facets above the bed.

MESH MODEL (house style, BOOLEAN-FREE): each part is a soup of individually-watertight surfaces that
the SLICER unions. The END is an outer dome skin + an inner dome skin (offset inward by --wall) closed
by three flat annuli built with band(): the wide BASE annulus at z=0 (rod-hole floor, underside on the
bed) with its bore collar, and the TOP RIM annulus at z=H that steps the outer rim down to the open pour
hole. The NAME ribs are separate closed sub-solids that INTERPENETRATE the outer wall (emboss.py). No
CSG, no boolean subtraction anywhere. verify() ASSERTS the binary-STL laws and returns the open-edge
count (MUST be 0).

STAGE / HONESTY — the gypsum POUR is UNPROVEN. Nothing here has been physically cast or even printed;
this is FIRST-CUT geometry for the owner to react to. A watertight mesh is a SOFTWARE guarantee (file-
size law + edge parity), NOT a proof that the shell survives a pour or that the cast weight lands on
target. The print-orientation / support caveat, however, IS resolved for the shell: printed base-down
the dome is measured self-supporting (overhang_report ~0). Do not phrase the POUR as proven.

Usage:
  python3 dumbbell_stl.py --part all --name "OLEG"        # writes dumbbell_end.stl + dumbbell_grip.stl
  python3 dumbbell_stl.py --part end --weight 4 --name "MAX" --out max_end.stl
Flags: --weight --fill-density --grip-dia --grip-len --name
       --core-dia --wall --points --part {end,grip,all} --out
"""
import argparse, math, os, random, struct

from emboss import emboss_on_cylinder, text_width       # raised NAME beads (boolean-free, watertight)

COS30 = math.cos(math.radians(30.0))
HOLE_N = 24                                              # samples per round port / rod hole
BORE_N = 48                                             # samples per grip rod bore


# ----------------------------------------------------------------------------- 2D profiles
def circle(cx, cy, r, n, ccw=True):
    pts = [(cx + r * math.cos(2 * math.pi * j / n), cy + r * math.sin(2 * math.pi * j / n))
           for j in range(n)]
    return pts if ccw else pts[::-1]


def ngon(cx, cy, r, n, phase=0.0):
    return [(cx + r * math.cos(phase + 2 * math.pi * k / n),
             cy + r * math.sin(phase + 2 * math.pi * k / n)) for k in range(n)]


def fluted(cx, cy, mean_r, depth, ridges, n, phase=0.0):
    """A knurled/fluted grip profile: r(theta) = mean_r - depth/2*(1 - cos(ridges*theta)), sampled at
    n points. Peaks (r = mean_r) are the ridges you grip; valleys sit `depth` in. Rounded, so it
    prints and feels clean, and revolves like any polygon (n points) for the band/cap builders."""
    pts = []
    for j in range(n):
        th = phase + 2 * math.pi * j / n
        r = mean_r - 0.5 * depth * (1.0 - math.cos(ridges * th))
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
    faces = []
    for seed in range(24):
        rng = random.Random(seed)
        test = [(x + rng.uniform(-1e-4, 1e-4), y + rng.uniform(-1e-4, 1e-4)) for (x, y) in merged]
        faces = ear_clip(merged, test)
        if len(faces) == want:
            return merged, faces
    return merged, faces


# ----------------------------------------------------------------------------- mesh builders
def cap_at(tris, outline, holes, z, up):
    """A single horizontal cap face (an outline with holes) at height z, wound +z (up=True) or -z."""
    verts, faces = triangulate_with_holes(outline, holes)
    for (a, b, c) in faces:
        if up:
            tris.append(((verts[a][0], verts[a][1], z), (verts[b][0], verts[b][1], z),
                         (verts[c][0], verts[c][1], z)))
        else:
            tris.append(((verts[c][0], verts[c][1], z), (verts[b][0], verts[b][1], z),
                         (verts[a][0], verts[a][1], z)))


def band(tris, A, B, outward=True):
    """Connect two equal-length rings of 3D points (A lower, B upper) with a quad strip. `outward`
    winds the normals away from the axis (True) or toward it (False)."""
    n = len(A)
    for j in range(n):
        k = (j + 1) % n
        if outward:
            tris.append((A[j], A[k], B[k])); tris.append((A[j], B[k], B[j]))
        else:
            tris.append((A[j], B[k], A[k])); tris.append((A[j], B[j], B[k]))


def lift(poly2d, z):
    return [(x, y, z) for (x, y) in poly2d]


# ----------------------------------------------------------------------------- STL io + verify
def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris, header=b"crackle dumbbell_stl - gift dumbbell formwork (POUR UNPROVEN)"):
    with open(path, "wb") as fh:
        fh.write(header.ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            fh.write(struct.pack("<3f", *normal(a, b, c)))
            for v in (a, b, c):
                fh.write(struct.pack("<3f", *v))
            fh.write(struct.pack("<H", 0))


def verify(path, tris):
    """Assert the binary-STL laws and return (ntris, open_edge_count, bounds, degenerate). Laws:
    filesize == 84 + 50*ntris, header not starting b'solid', 0 degenerate tris, every undirected
    edge shared by exactly 2 triangles (open_edges MUST be 0)."""
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
    return count, open_edges, bounds, degen


# ----------------------------------------------------------------------------- END geometry (dome)
# Self-supporting capped-cylinder vessel, printed BASE-DOWN, poured from the OPEN TOP. Outer silhouette:
#     z in [0, z_knee]:  r(z) = R_base                                   (a straight vertical body)
#     z in [z_knee, H ]: r(z) = r_top + (R_base-r_top)*(1-w**P)**Q       w = (z-z_knee)/(H-z_knee)
# It is MAX at the base and MONOTONICALLY NON-INCREASING to r_top at the top (constant, then narrowing),
# so no outer overhang exists at any z. The straight lower body gives a near-vertical CONSTANT-RADIUS
# band for the wrapped NAME; the domed top narrows to the open pour hole. The dome height (H-z_knee) is
# auto-scaled (end_geom) so the steepest wall slope equals MAX_WALL_SLOPE, which also bounds the inner
# cavity skin's downward tilt below the support threshold => self-supporting at any weight.
DOME_P = 1.4               # cap shape (1-w^P)^Q: rounded at both the knee (w=0) and the pour hole (w=1)
DOME_Q = 1.6
MAX_WALL_SLOPE = 0.75      # cap on |dr/dz| = tan(wall angle off vertical); 0.75 -> 37deg (< 45 = 1.0)
CYL_FRAC = 0.45            # lower fraction of H that is the straight vertical body (the name band lives here)


def _dome_shape(w):
    """Dome-cap shape factor: 1 at the knee (w=0), 0 at the top (w=1); w clamped to [0,1]."""
    w = 0.0 if w < 0.0 else (1.0 if w > 1.0 else w)
    return (1.0 - w ** DOME_P) ** DOME_Q


def _dome_shape_max_slope(samples=4000):
    """max_w |d(shape)/dw| — a pure number for (P,Q). The dome height is scaled by this (end_geom) so
    the wall never exceeds MAX_WALL_SLOPE at ANY size => the vessel is self-supporting at any weight."""
    m = 0.0
    for i in range(1, samples):
        w = i / samples
        d = DOME_P * DOME_Q * (w ** (DOME_P - 1.0)) * ((1.0 - w ** DOME_P) ** (DOME_Q - 1.0))
        if d > m:
            m = d
    return m


_SHAPE_MAX_SLOPE = _dome_shape_max_slope()


def end_geom(size, wall):
    """Vessel dimensions for base radius `size`: (H, r_top, port_r, z_knee).
      port_r = OPEN pour-hole radius at the top (the inner opening, min(6, 0.30*R_base)),
      r_top  = outer silhouette radius at z=H = port_r + wall (so the top rim annulus is `wall` wide),
      z_knee = top of the straight body; the dome caps z in [z_knee, H],
      H      = z_knee + dome height, dome height set so the steepest wall slope == MAX_WALL_SLOPE."""
    port_r = min(6.0, 0.30 * size)
    r_top = port_r + wall
    span = max(1.0, size - r_top)
    dome_h = span * _SHAPE_MAX_SLOPE / MAX_WALL_SLOPE
    H = dome_h / (1.0 - CYL_FRAC)
    z_knee = CYL_FRAC * H
    return H, r_top, port_r, z_knee


def dome_r(size, z, H, r_top, z_knee):
    """Outer silhouette radius at height z: R_base (=size) up to z_knee, then monotonically
    non-increasing to r_top at z=H. Every layer <= the one below, so the outer skin never overhangs."""
    if z <= z_knee:
        return size
    return r_top + (size - r_top) * _dome_shape((z - z_knee) / (H - z_knee))


def cavity_volume(size, wall, side_n):
    """Modeled gypsum volume (mm^3): integrate the INNER cross-sectional area (the meshed side_n-gon of
    radius r_out(z)-wall) from the floor (z=wall) to the OPEN brim (z=H). Open-topped: no top wall."""
    H, r_top, _, z_knee = end_geom(size, wall)
    z0, z1 = wall, H
    if z1 <= z0:
        return 0.0
    nz = 160
    dz = (z1 - z0) / nz
    vol = 0.0
    for i in range(nz):
        z = z0 + (i + 0.5) * dz
        r_in = max(0.1, dome_r(size, z, H, r_top, z_knee) - wall)
        vol += abs(_area2(circle(0.0, 0.0, r_in, side_n))) * dz
    return vol


def size_for_weight(weight_kg, density_gcc, wall, side_n):
    """Bisect the dome base radius so the modeled cavity holds the per-end fill volume
    (weight/density/2 in litres -> mm^3). cavity_volume rises with size, so bisection converges."""
    vf = weight_kg / density_gcc / 2.0 * 1.0e6
    lo, hi = 5.0, 250.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if cavity_volume(mid, wall, side_n) < vf:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi), vf


def overhang_count(tris, thresh=0.707, z_floor=0.5):
    """Count SUPPORT-NEEDING facets in a triangle soup: downward-facing (nz<0) steeper than 45deg off
    vertical (nz < -thresh), EXCLUDING anything on the base layer (zmin < z_floor, which sits ON the
    bed). Returns (bad, total). For the self-supporting shell this MUST be ~0 (the outer skin faces
    up-and-out; the inner skin's downward tilt is capped below thresh by MAX_WALL_SLOPE)."""
    bad = 0
    for vs in tris:
        _, _, nz = normal(*vs)
        if nz < -thresh and min(v[2] for v in vs) >= z_floor:
            bad += 1
    return bad, len(tris)


def overhang_report(path, thresh=0.707, z_floor=0.5):
    """Read the EMITTED STL back off disk and run overhang_count on it (measure the artifact, not the
    in-memory list). Returns (bad, total)."""
    tris = []
    with open(path, "rb") as fh:
        fh.read(80)
        (count,) = struct.unpack("<I", fh.read(4))
        for _ in range(count):
            fh.read(12)
            tris.append([struct.unpack("<3f", fh.read(12)) for _ in range(3)])
            fh.read(2)
    return overhang_count(tris, thresh, z_floor)


def build_end(a):
    side_n = a.points
    wall = a.wall
    size, vf = size_for_weight(a.weight, a.fill_density, wall, side_n)
    H, r_top, port_r, z_knee = end_geom(size, wall)
    rod_r = a.core_dia / 2.0 + 0.4                      # rod clearance bore through the base floor

    def rout(z):
        return dome_r(size, z, H, r_top, z_knee)

    # z-levels: a ring exactly AT the knee (a crisp body->dome crease) + dense sampling over the dome.
    ncyl, ndome = 6, 64
    zs = [z_knee * i / ncyl for i in range(ncyl)] + \
         [z_knee + (H - z_knee) * i / ndome for i in range(ndome + 1)]
    zin = [wall + (z_knee - wall) * i / ncyl for i in range(ncyl)] + \
          [z_knee + (H - z_knee) * i / ndome for i in range(ndome + 1)]

    tris = []
    outer_rings = [circle(0.0, 0.0, rout(z), side_n) for z in zs]
    inner_rings = [circle(0.0, 0.0, max(0.5, rout(z) - wall), side_n) for z in zin]
    rod_ring = circle(0.0, 0.0, rod_r, side_n)

    # ---- outer skin: vertical body then narrowing cap, every facet faces up-and-out (nz >= 0) ----
    for i in range(len(zs) - 1):
        band(tris, lift(outer_rings[i], zs[i]), lift(outer_rings[i + 1], zs[i + 1]), outward=True)
    # ---- inner cavity skin: faces in-and-down, |nz| < 0.58 by the slope cap (below support thresh) ----
    for i in range(len(zin) - 1):
        band(tris, lift(inner_rings[i], zin[i]), lift(inner_rings[i + 1], zin[i + 1]), outward=False)
    # ---- base: widest flat annulus at z=0 (underside on the bed) + cavity floor + rod-bore collar ----
    band(tris, lift(rod_ring, 0.0), lift(outer_rings[0], 0.0), outward=True)      # base underside, -z
    band(tris, lift(rod_ring, wall), lift(inner_rings[0], wall), outward=False)   # cavity floor, +z
    band(tris, lift(rod_ring, 0.0), lift(rod_ring, wall), outward=False)          # rod bore lining, -r
    # ---- top rim annulus at z=H: outer rim stepped down to the OPEN pour hole (faces up) ----
    band(tris, lift(inner_rings[-1], H), lift(outer_rings[-1], H), outward=False)  # pour rim, +z

    shell_bad, shell_tot = overhang_count(tris)         # the SHELL FORM alone must be ~0

    # ---- NAME wrapped on the vertical body band (~37% H, constant radius = size, raised ribs) ----
    name = a.name
    if name:
        band_cy = 0.37 * H                              # inside the straight body (below z_knee = 0.45*H)
        name_h = 0.10 * H
        arc_budget = 1.7 * size                         # ~97deg of the forward-facing arc
        w = text_width(name, name_h)
        if w > arc_budget:
            name_h *= arc_budget / w
        emboss_on_cylinder(tris, name, cyl_radius=size, z_center=band_cy,
                           angle_center_rad=0.0, height_mm=name_h)

    cav = cavity_volume(size, wall, side_n)
    info = dict(size=size, H=H, r_top=r_top, port_r=port_r, rod_r=rod_r, z_knee=z_knee, vf=vf, cav=cav,
                mass=cav * a.fill_density / 1.0e6,              # kg (mm^3 * g/cc / 1e6)
                shell_bad=shell_bad, shell_tot=shell_tot)
    return tris, info


# ----------------------------------------------------------------------------- GRIP geometry
def build_grip(a):
    grip_R = a.grip_dia / 2.0
    L = a.grip_len
    bore_r = a.core_dia / 2.0 + 0.4
    ridges = max(8, int(round(math.pi * a.grip_dia / 5.0)))     # ~one flute per 5mm of circumference
    depth = 1.2
    n = max(48, ridges * 6)

    outer2d = fluted(0.0, 0.0, grip_R, depth, ridges, n)
    bore2d = circle(0.0, 0.0, bore_r, BORE_N, ccw=False)

    tris = []
    cap_at(tris, outer2d, [bore2d], 0.0, up=False)              # bottom cap (annulus, bore hole)
    cap_at(tris, outer2d, [bore2d], L, up=True)                 # top cap
    band(tris, lift(outer2d, 0.0), lift(outer2d, L), outward=True)      # fluted outer wall
    band(tris, lift(bore2d, 0.0), lift(bore2d, L), outward=False)       # rod bore wall

    info = dict(grip_R=grip_R, L=L, bore_r=bore_r, ridges=ridges)
    return tris, info


# ----------------------------------------------------------------------------- io helpers
def _emit(path, tris, label):
    write_binary_stl(path, tris)
    n, oe, b, dg = verify(path, tris)
    assert oe == 0, f"{label}: {oe} open (non-paired) edges — not watertight"
    dx, dy, dz = b[1] - b[0], b[3] - b[2], b[5] - b[4]
    print(f"{path}: {n} triangles, {os.path.getsize(path)} bytes")
    print(f"  open edges {oe} [0=watertight]   degenerate {dg}   "
          f"bounds {dx:.1f} x {dy:.1f} x {dz:.1f} mm")
    return n, oe, b


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weight", type=float, default=3.0, help="target TOTAL dumbbell weight kg (1..6 gift range)")
    ap.add_argument("--fill-density", type=float, default=1.9, help="cast fill density g/cc (gypsum+sand ~1.9)")
    ap.add_argument("--grip-dia", type=float, default=32.0, help="grip outer diameter mm")
    ap.add_argument("--grip-len", type=float, default=130.0, help="grip length mm")
    ap.add_argument("--name", default="GIFT", help="name embossed on each end's side band")
    ap.add_argument("--core-dia", type=float, default=6.35, help="rod core diameter mm (bamboo 6.35 / steel ~12)")
    ap.add_argument("--wall", type=float, default=1.6, help="shell / sleeve wall thickness mm")
    ap.add_argument("--points", type=int, default=96, help="samples around round ends")
    ap.add_argument("--part", choices=("end", "grip", "all"), default="all")
    ap.add_argument("--out", default=None, help="output STL path (base name; 'all' derives _end/_grip)")
    a = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    base = a.out or os.path.join(here, "dumbbell.stl")
    stem, ext = os.path.splitext(base)
    ext = ext or ".stl"

    if a.part in ("end", "all"):
        tris, info = build_end(a)
        path = (base if a.part == "end" and a.out else f"{stem}_end{ext}")
        _emit(path, tris, "END")
        bad, tot = overhang_report(path)                # measured from the emitted STL (whole part)
        text_bad = bad - info['shell_bad']              # residual = raised-text beads (self-supporting)
        print(f"  PRINTABLE: {info['shell_bad']} downward faces >45deg off vertical above the base "
              f"(target ~0)  [dome shell; {info['shell_tot']} facets]")
        if text_bad > 0:
            print(f"  (+{text_bad} downfacing micro-facets = the raised-NAME beads on the vertical body "
                  f"band; raised text on a vertical wall is self-supporting, no support)")
        print(f"  dome base Ø{2*info['size']:.1f}mm, height {info['H']:.1f}mm (base-down, self-supporting)")
        print(f"  target per-end fill {info['vf']/1e3:.0f} cc -> modeled cavity {info['cav']/1e3:.0f} cc "
              f"= {info['mass']:.2f} kg gypsum/end ({2*info['mass']:.2f} kg total, target {a.weight:g})")
        print(f"  rod bore Ø{2*info['rod_r']:.2f} (base/grip side), OPEN pour hole Ø{2*info['port_r']:.1f} (top), "
              f"name '{a.name}' on the side — ROD CORE MANDATORY, ends identical for balance, POUR UNPROVEN")

    if a.part in ("grip", "all"):
        tris, info = build_grip(a)
        path = (base if a.part == "grip" and a.out else f"{stem}_grip{ext}")
        _emit(path, tris, "GRIP")
        print(f"  grip Ø{a.grip_dia:g} x {info['L']:g}mm, {info['ridges']} flutes, "
              f"through-bore Ø{2*info['bore_r']:.2f} for the rod core")


if __name__ == "__main__":
    main()
