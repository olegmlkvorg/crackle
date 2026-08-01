#!/usr/bin/env python3
"""dumbbell_stl.py — a PERSONALIZED GIFT DUMBBELL in the canonical form Oleg named (2026-08-02):
"dumbbell is 2 sides plus tube in the middle". Two identical DRUM-CUP ends + a fluted GRIP tube,
printed as thin PLA formwork, mass cast in with gypsum. First unit is Oleg's own home equipment.

WHAT AN END IS — an open DRUM CUP that reads as a classic weight plate:
  * Outer silhouette: a STRAIGHT CYLINDER (a drum). Diameter and depth are derived from --weight:
    the inner cavity holds exactly the per-end fill (weight/fill_density/2), with proportions that
    read like a dumbbell plate: depth = --aspect * dia (default 0.55). 3 kg at 1.9 g/cc -> ~789 cc
    per end -> about Ø125 x 69.
  * CLOSED flat outer FACE — prints ON THE BED, face-down. It stays CLEAN: raised text printed
    face-down would squish into the bed, so the NAME wraps the drum SIDE instead
    (emboss_on_cylinder — plate-style rim lettering, printed mid-wall, a self-supporting bead).
  * Straight vertical wall (--wall), OPEN inner side: the pour mouth is the WHOLE open face (vase
    doctrine — fill from one side). A small inner LIP flange at the open rim (LIP_IN mm inward)
    locks the set gypsum axially; its underside is a chamfer (rise LIP_RISE) so it self-supports.
  * ROD BORE: a collar tube stands COLLAR_H mm from the closed face centre into the cavity
    (bore r = --core-dia/2 + 0.4, blind socket, closed by the face plate). The rod tip embeds in
    the cast gypsum while the bore itself stays gypsum-free for assembly.

HARD RULE — THE ROD CORE IS MANDATORY: a bamboo (Ø6.35) or steel (Ø~12) rod runs the whole length,
through the grip's bore and into each end's collar socket. The rod is the TENSILE / BENDING member;
the gypsum is cheap mass; the PLA is only the mould + grip sleeve. Never omit it.

ASSEMBLY reads: [drum][grip tube][drum] — open faces INWARD against the grip ends, rod through all
three. --viz ALSO writes dumbbell_assembled.stl: 2 ends + grip on a shared axis, correctly spaced
(grip length between the two open rims), lying HORIZONTAL (axis along X) like a real dumbbell on a
table. VIZ ONLY — never print that file.

BALANCE: the two ends are IDENTICAL by construction (same STL, printed twice). Do not scale one end
without the other.

WHY IT PRINTS WITHOUT SUPPORT (mesh frame = print frame): the closed face is at z=0 on the bed,
every wall is vertical, every internal flat annulus (cavity floor, collar top, rim top) faces UP,
and the only downward-tilted skin — the lip chamfer underside — is held to |nz| ~0.62 (< 0.707) by
LIP_IN/LIP_RISE. Zero spanning downward overhangs BY CONSTRUCTION; build_end measures it anyway.

MESH MODEL (house style, BOOLEAN-FREE): the drum is ONE closed solid of revolution — bottom disc
fan, outer wall, rim-top annulus, lip chamfer, inner cavity wall, cavity floor annulus, collar wall,
collar top, bore wall, bore floor disc — every ring shared by exactly two surfaces. The NAME ribs
are separate closed capsule-chain sub-solids that INTERPENETRATE the outer wall (emboss.py; the
wall must swallow rib_r - raise_mm = 0.4 mm, which --wall 1.6 does). No CSG anywhere. verify()
asserts the binary-STL laws and 0 open edges.

STAGE / HONESTY — the gypsum POUR is UNPROVEN. Nothing has been cast; this is geometry for Oleg to
react to. Watertight + zero-overhang are SOFTWARE guarantees measured off the emitted mesh, not a
proof the shell survives a pour or that the cast mass lands on target. Do not phrase the POUR as
proven.

Usage:
  python3 dumbbell_stl.py --name "OLEG" --viz     # end + grip + assembled viz
  python3 dumbbell_stl.py --part end --weight 4 --name "MAX" --out max_end.stl
Flags: --weight --fill-density --grip-dia --grip-len --name
       --core-dia --wall --aspect --points --part {end,grip,all} --out --viz
"""
import argparse, math, os, random, struct

from emboss import emboss_on_cylinder, text_width       # raised NAME beads (boolean-free, watertight)

BORE_N = 48                                             # samples per grip rod bore


# ----------------------------------------------------------------------------- 2D profiles
def circle(cx, cy, r, n, ccw=True):
    pts = [(cx + r * math.cos(2 * math.pi * j / n), cy + r * math.sin(2 * math.pi * j / n))
           for j in range(n)]
    return pts if ccw else pts[::-1]


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


def disc_fan(tris, ring2d, z, up):
    """A full horizontal disc at height z: a triangle fan from the (0,0) centre to a ccw ring.
    up=True winds the face +z, up=False winds it -z. The ring is shared vertex-for-vertex with
    whatever band it closes, so edge parity holds."""
    c = (0.0, 0.0, z)
    n = len(ring2d)
    for j in range(n):
        k = (j + 1) % n
        pj = (ring2d[j][0], ring2d[j][1], z)
        pk = (ring2d[k][0], ring2d[k][1], z)
        if up:
            tris.append((c, pj, pk))
        else:
            tris.append((c, pk, pj))


def band(tris, A, B, outward=True):
    """Connect two equal-length rings of 3D points (A lower, B upper) with a quad strip. `outward`
    winds the normals away from the axis (True) or toward it (False). For two concentric rings at
    the SAME z (a flat annulus), band(inner, outer, outward=True) faces -z and outward=False +z."""
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


def write_binary_stl(path, tris, header=b"crackle dumbbell_stl - drum-cup dumbbell formwork (POUR UNPROVEN)"):
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


# ----------------------------------------------------------------------------- END geometry (drum cup)
# The end is a straight open cylinder cup, printed CLOSED-FACE-DOWN. In the mesh (= print) frame the
# closed face plate sits at z=0 on the bed, the walls rise vertically, and the open rim is the top.
# Every flat internal surface faces UP; the one downward-tilted skin is the lip-flange chamfer,
# whose slope is fixed by LIP_IN/LIP_RISE at |nz| ~0.62 — under the 0.707 support threshold. So the
# cup has ZERO spanning downward overhangs by construction (measured anyway, see build_end).
LIP_IN = 2.5     # rim lip flange, mm radially inward at the open rim — axial lock for the set gypsum
LIP_RISE = 3.2   # chamfer rise under the lip, mm; slope atan(LIP_IN/LIP_RISE) ~38deg off vertical
COLLAR_H = 25.0  # rod-bore collar height into the cavity, mm (blind socket depth for the rod tip)


def collar_height(D, wall):
    """Collar height, clamped so the collar always stays clear of the lip chamfer zone."""
    return min(COLLAR_H, max(5.0, D - wall - LIP_RISE - 2.0))


def cavity_volume(R, aspect, wall, side_n, rc_out):
    """Modeled gypsum volume (mm^3) of one drum cup, filled to the open brim: integrate the meshed
    side_n-gon cross-section from the cavity floor (z=wall) to the rim (z=D), narrowing across the
    lip chamfer, MINUS the collar keep-out disc (collar tube + blind bore, r<=rc_out, gypsum-free)."""
    D = 2.0 * R * aspect
    ch = collar_height(D, wall)
    k = abs(_area2(circle(0.0, 0.0, 1.0, side_n)))       # n-gon area factor: A(r) = k * r^2
    z0, z1 = wall, D
    if z1 <= z0:
        return 0.0
    nz = 200
    dz = (z1 - z0) / nz
    vol = 0.0
    for i in range(nz):
        z = z0 + (i + 0.5) * dz
        if z <= D - LIP_RISE:
            r_in = R - wall
        else:
            r_in = R - wall - LIP_IN * (z - (D - LIP_RISE)) / LIP_RISE
        a = k * max(0.1, r_in) ** 2
        if z <= wall + ch:
            a -= k * rc_out ** 2                          # collar + bore keep-out
        vol += max(0.0, a) * dz
    return vol


def size_for_weight(weight_kg, density_gcc, aspect, wall, side_n, rc_out):
    """Bisect the drum outer radius R (depth D = 2*R*aspect follows) so the modeled cavity holds the
    per-end fill volume (weight/density/2 in litres -> mm^3). Volume rises with R, so it converges."""
    vf = weight_kg / density_gcc / 2.0 * 1.0e6
    lo, hi = max(12.0, rc_out + wall + LIP_IN + 2.0), 250.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if cavity_volume(mid, aspect, wall, side_n, rc_out) < vf:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi), vf


def overhang_count(tris, thresh=0.707, z_floor=0.5):
    """Count SUPPORT-NEEDING facets in a triangle soup: downward-facing (nz<0) steeper than 45deg off
    vertical (nz < -thresh), EXCLUDING anything on the base layer (zmin < z_floor, which sits ON the
    bed). Returns (bad, total). For the drum cup this MUST be 0 (walls vertical, annuli face up, lip
    chamfer capped at |nz| ~0.62)."""
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
    """One drum-cup end as a single closed solid of revolution + the NAME ribs on the drum side.
    Mesh frame = print frame: closed face at z=0 (bed), open rim at z=D."""
    side_n = a.points
    wall = a.wall
    rod_r = a.core_dia / 2.0 + 0.4                       # rod clearance bore (blind socket)
    rc_out = rod_r + wall                                # collar outer radius
    R, vf = size_for_weight(a.weight, a.fill_density, a.aspect, wall, side_n, rc_out)
    D = 2.0 * R * a.aspect
    ch = collar_height(D, wall)

    # one ring object per radius, reused at every z — exact shared vertices = clean edge parity
    ring_R = circle(0.0, 0.0, R, side_n)                 # outer drum
    ring_Rw = circle(0.0, 0.0, R - wall, side_n)         # inner cavity wall
    ring_lip = circle(0.0, 0.0, R - wall - LIP_IN, side_n)  # rim opening inside the lip
    ring_rc = circle(0.0, 0.0, rc_out, side_n)           # collar outer
    ring_rod = circle(0.0, 0.0, rod_r, side_n)           # bore

    tris = []
    # closed outer FACE: full disc ON THE BED at z=0, facing -z — stays clean flat (no text here)
    disc_fan(tris, ring_R, 0.0, up=False)
    # outer drum wall: straight vertical cylinder z=0..D
    band(tris, lift(ring_R, 0.0), lift(ring_R, D), outward=True)
    # rim top annulus at z=D: lip opening -> outer edge, faces up
    band(tris, lift(ring_lip, D), lift(ring_R, D), outward=False)
    # lip chamfer underside: cavity wall (R-wall @ D-LIP_RISE) -> lip edge (@ D); |nz| ~0.62
    band(tris, lift(ring_Rw, D - LIP_RISE), lift(ring_lip, D), outward=False)
    # inner cavity wall: vertical, cavity floor -> chamfer start
    band(tris, lift(ring_Rw, wall), lift(ring_Rw, D - LIP_RISE), outward=False)
    # cavity floor annulus at z=wall: collar outer -> cavity wall, faces up
    band(tris, lift(ring_rc, wall), lift(ring_Rw, wall), outward=False)
    # rod-bore collar: outer wall, top annulus (faces up), bore wall, blind-bore floor disc
    band(tris, lift(ring_rc, wall), lift(ring_rc, wall + ch), outward=True)
    band(tris, lift(ring_rod, wall + ch), lift(ring_rc, wall + ch), outward=False)
    band(tris, lift(ring_rod, wall), lift(ring_rod, wall + ch), outward=False)
    disc_fan(tris, ring_rod, wall, up=True)

    shell_bad, shell_tot = overhang_count(tris)          # the drum shell alone MUST be 0

    # NAME on the drum SIDE — plate-style rim lettering, wrapped mid-wall (self-supporting bead).
    # NOT on the bed face: raised text printed face-down would squish into the bed.
    name = a.name
    if name:
        name_h = 0.40 * D
        arc_budget = 1.9 * R                             # ~109deg of the forward-facing arc
        w = text_width(name, name_h)
        if w > arc_budget:
            name_h *= arc_budget / w
        emboss_on_cylinder(tris, name, cyl_radius=R, z_center=D / 2.0,
                           angle_center_rad=0.0, height_mm=name_h)

    cav = cavity_volume(R, a.aspect, wall, side_n, rc_out)
    info = dict(R=R, D=D, rod_r=rod_r, rc_out=rc_out, ch=ch, vf=vf, cav=cav,
                mass=cav * a.fill_density / 1.0e6,       # kg (mm^3 * g/cc / 1e6)
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


# ----------------------------------------------------------------------------- assembled viz
def build_assembled(a):
    """VIZ ONLY — never print this file. The dumbbell as assembled: [drum][grip tube][drum] on a
    shared axis along X, open faces inward against the grip ends, grip length between the two open
    rims, lying horizontal on the table (lowest drum point at z=0). Proper rotations only, so the
    soup stays watertight (three disjoint closed solids)."""
    end_tris, einfo = build_end(a)
    grip_tris, ginfo = build_grip(a)
    D, R = einfo["D"], einfo["R"]
    hg = a.grip_len / 2.0

    tris = []
    for (p0, p1, p2) in end_tris:                        # LEFT drum: mesh +z -> +x (open rim at -hg)
        tris.append(tuple((v[2] - hg - D, -v[1], v[0] + R) for v in (p0, p1, p2)))
    for (p0, p1, p2) in end_tris:                        # RIGHT drum: mesh +z -> -x (open rim at +hg)
        tris.append(tuple((-v[2] + hg + D, v[1], v[0] + R) for v in (p0, p1, p2)))
    for (p0, p1, p2) in grip_tris:                       # grip: mesh z 0..L -> x -hg..+hg
        tris.append(tuple((v[2] - hg, v[1], -v[0] + R) for v in (p0, p1, p2)))
    return tris, dict(total_len=2.0 * D + a.grip_len, R=R, D=D, grip_R=ginfo["grip_R"])


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
    ap.add_argument("--name", default="OLEG", help="name wrapped on each end's drum side")
    ap.add_argument("--core-dia", type=float, default=6.35, help="rod core diameter mm (bamboo 6.35 / steel ~12)")
    ap.add_argument("--wall", type=float, default=1.6, help="shell / sleeve wall thickness mm")
    ap.add_argument("--aspect", type=float, default=0.55, help="end drum depth/dia ratio (plate look ~0.55)")
    ap.add_argument("--points", type=int, default=96, help="samples around round ends")
    ap.add_argument("--part", choices=("end", "grip", "all"), default="all")
    ap.add_argument("--out", default=None, help="output STL path (base name; 'all' derives _end/_grip)")
    ap.add_argument("--viz", action="store_true",
                    help="ALSO write <stem>_assembled.stl — the full dumbbell lying on its side (VIZ ONLY)")
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
              f"(target 0)  [drum shell; {info['shell_tot']} facets]")
        if text_bad > 0:
            print(f"  (+{text_bad} downfacing micro-facets = the raised-NAME bead on the drum side; "
                  f"raised text on a vertical wall is self-supporting, no support)")
        print(f"  drum Ø{2*info['R']:.1f} x {info['D']:.1f}mm deep (aspect {a.aspect:g}), wall {a.wall:g}, "
              f"prints closed-face-down")
        print(f"  rim lip {LIP_IN:g}mm inward (gypsum axial lock, chamfered underside), "
              f"collar socket Ø{2*info['rod_r']:.2f} x {info['ch']:.0f}mm deep at the face centre")
        print(f"  target per-end fill {info['vf']/1e3:.0f} cc -> modeled cavity {info['cav']/1e3:.0f} cc "
              f"= {info['mass']:.2f} kg gypsum/end ({2*info['mass']:.2f} kg total, target {a.weight:g})")
        print(f"  name '{a.name}' wrapped on the drum side — ROD CORE MANDATORY, "
              f"ends identical for balance, POUR UNPROVEN")

    if a.part in ("grip", "all"):
        tris, info = build_grip(a)
        path = (base if a.part == "grip" and a.out else f"{stem}_grip{ext}")
        _emit(path, tris, "GRIP")
        print(f"  grip Ø{a.grip_dia:g} x {info['L']:g}mm, {info['ridges']} flutes, "
              f"through-bore Ø{2*info['bore_r']:.2f} for the rod core")

    if a.viz:
        tris, info = build_assembled(a)
        path = f"{stem}_assembled{ext}"
        _emit(path, tris, "ASSEMBLED")
        print(f"  VIZ ONLY (do not print): [drum][grip][drum] on one axis, open faces inward, "
              f"{info['total_len']:.0f}mm end to end, lying horizontal")


if __name__ == "__main__":
    main()
