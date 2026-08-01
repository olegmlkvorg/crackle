#!/usr/bin/env python3
"""dumbbell_stl.py — a PERSONALIZED GIFT DUMBBELL: two cast-mass ends on a rod core, printed as
thin PLA FORMWORK. Emits the two identical END shells + the GRIP sleeve as separate STLs.

WHAT IT IS (a gift / trophy, NOT a competition weight — 1..6 kg sweet spot):
  * Each END is a hollow thin-wall shell (sphere / hex / barrel silhouette) sized so its INNER cavity
    holds exactly the gypsum needed for the target weight (per-end fill volume = weight/density/2).
    You print the shell, pour a gypsum+sand mix (~1.9 g/cc) through the FILL PORT, and the mass is cast.
    The outer FACE carries the recipient's NAME as a raised bead (imported emboss.py, boolean-free).
  * The GRIP is a knurled/fluted tube sleeve with a central rod bore.

HARD RULE — THE ROD CORE IS MANDATORY (baked in, like the stand's rebar): a bamboo (Ø6.35) or steel
(Ø~12) ROD runs the whole length — through the grip's through-bore and into each cast end, where its
tip is embedded in the gypsum. The rod is the TENSILE / BENDING member; the gypsum is cheap mass; the
PLA is only the mould + grip sleeve. A solid gypsum handle with NO rod SNAPS in bending — never omit it.

BALANCE: the two ends are IDENTICAL by construction (same STL, printed twice). Do not scale one end
without the other or the dumbbell will be lopsided.

MESH MODEL (house style, BOOLEAN-FREE): each part is a soup of individually-watertight surfaces that
the SLICER unions. The END shell is two nested closed-except-at-holes surfaces (outer + inner cavity)
joined at the two ports by short collar tubes — the wall between them is the printed solid. The NAME
ribs are separate closed sub-solids that INTERPENETRATE the outer wall (emboss.py). No CSG, no boolean
subtraction anywhere. verify() ASSERTS the binary-STL laws and returns the open-edge count (MUST be 0).

STAGE / HONESTY — the gypsum POUR is UNPROVEN. Nothing here has been physically cast or even printed;
this is FIRST-CUT geometry for the owner to react to. A watertight mesh is a SOFTWARE guarantee (file-
size law + edge parity), NOT a proof that the shell prints, that it survives a pour, or that the cast
weight lands on target. Print orientation / supports for the closed hollow shell are NOT yet resolved
(a flat-roofed cavity may need support or a print-in-two-halves change). Do not phrase any of it as proven.

Usage:
  python3 dumbbell_stl.py --part all --name "OLEG"        # writes dumbbell_end.stl + dumbbell_grip.stl
  python3 dumbbell_stl.py --part end --weight 4 --end-shape barrel --name "MAX" --out max_end.stl
Flags: --weight --fill-density --end-shape {sphere,hex,barrel} --grip-dia --grip-len --name
       --core-dia --wall --points --part {end,grip,all} --out
"""
import argparse, math, os, random, struct

from emboss import emboss_on_plane, text_width          # raised NAME beads (boolean-free, watertight)

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


# ----------------------------------------------------------------------------- END geometry
SPHERE_TRUNC = 0.82        # sphere pole-flat cut at |z-zc| = TRUNC*Rs (medallion radius = Rs*sqrt(1-t^2))
BARREL_FILLET = 0.28       # barrel shoulder fillet radius as a fraction of Rb
BARREL_ASPECT = 1.7        # barrel height = ASPECT * Rb
HEX_ASPECT = 1.6           # hex prism height = ASPECT * vertex radius


def end_height(shape, size):
    if shape == "sphere":
        return 2.0 * size * SPHERE_TRUNC
    if shape == "barrel":
        return BARREL_ASPECT * size
    return HEX_ASPECT * size                          # hex


def outer_radius(shape, size, z, H):
    """Outer silhouette radius (for round shapes) at height z in [0,H]. hex is handled separately."""
    if shape == "sphere":
        zc = H / 2.0
        return math.sqrt(max(0.0, size * size - (z - zc) ** 2))
    if shape == "barrel":
        f = BARREL_FILLET * size
        r0 = size - f
        if z < f:
            return r0 + math.sqrt(max(0.0, f * f - (f - z) ** 2))
        if z > H - f:
            return r0 + math.sqrt(max(0.0, f * f - (f - (H - z)) ** 2))
        return size
    return size


def end_ring2d(shape, size, z, H, inset, side_n):
    """Outer (inset=0) or inner-cavity (inset=wall) cross-section polygon at height z."""
    if shape == "hex":
        r = size - (inset / COS30 if inset else 0.0)   # inward perpendicular offset of a regular hexagon
        return ngon(0.0, 0.0, r, 6, phase=0.0)
    r = outer_radius(shape, size, z, H) - inset
    return circle(0.0, 0.0, max(0.1, r), side_n)


def cavity_volume(shape, size, wall, side_n):
    """Modeled gypsum cavity volume (mm^3): integrate the INNER cross-sectional area over the cavity
    z-range [wall, H-wall]. Measures the actual meshed cavity, not an idealized sphere."""
    H = end_height(shape, size)
    nz = 96
    z0, z1 = wall, H - wall
    if z1 <= z0:
        return 0.0
    vol = 0.0
    dz = (z1 - z0) / nz
    for i in range(nz):
        z = z0 + (i + 0.5) * dz
        area = abs(_area2(end_ring2d(shape, size, z, H, wall, side_n)))
        vol += area * dz
    return vol


def size_for_weight(shape, weight_kg, density_gcc, wall, side_n):
    """Bisect the shape's size scalar so the modeled cavity holds the per-end fill volume."""
    vf = weight_kg / density_gcc / 2.0 * 1.0e6         # mm^3 per end (weight/density/2 in litres -> mm^3)
    lo, hi = 5.0, 250.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if cavity_volume(shape, mid, wall, side_n) < vf:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi), vf


def build_end(a):
    side_n = 6 if a.end_shape == "hex" else a.points
    size, vf = size_for_weight(a.end_shape, a.weight, a.fill_density, a.wall, side_n)
    H = end_height(a.end_shape, size)
    wall = a.wall

    RH = math.hypot(*end_ring2d(a.end_shape, size, H, H, 0.0, side_n)[0])   # top medallion "radius"
    rod_r = a.core_dia / 2.0 + 0.4                     # rod clearance bore (bottom / grip side)
    port_r = min(6.0, 0.30 * RH)                       # gypsum fill port radius (outer face)
    port_cy = 0.58 * RH                                # port sits near the top edge of the medallion
    port_c = (0.0, port_cy)

    tris = []

    # ---- OUTER surface: bottom medallion (rod hole) + side + top medallion (port hole) ----
    outer_rings = []
    nz = 1 if a.end_shape == "hex" else 48
    zs = [H * i / nz for i in range(nz + 1)]
    for z in zs:
        outer_rings.append(end_ring2d(a.end_shape, size, z, H, 0.0, side_n))
    rod_hole = circle(0.0, 0.0, rod_r, HOLE_N, ccw=False)
    port_hole = circle(port_c[0], port_c[1], port_r, HOLE_N, ccw=False)
    cap_at(tris, outer_rings[0], [rod_hole], 0.0, up=False)          # outer bottom (grip side), rod hole
    cap_at(tris, outer_rings[-1], [port_hole], H, up=True)          # outer top (face), fill port
    for i in range(nz):
        band(tris, lift(outer_rings[i], zs[i]), lift(outer_rings[i + 1], zs[i + 1]), outward=True)

    # ---- INNER cavity surface: bottom (z=wall) + side + top (z=H-wall), holes match the collars ----
    inner_rings = []
    zin = [wall + (H - 2 * wall) * i / nz for i in range(nz + 1)]
    for z in zin:
        inner_rings.append(end_ring2d(a.end_shape, size, z, H, wall, side_n))
    cap_at(tris, inner_rings[0], [rod_hole], wall, up=True)          # inner bottom faces cavity (+z)
    cap_at(tris, inner_rings[-1], [port_hole], H - wall, up=False)  # inner top faces cavity (-z)
    for i in range(nz):
        band(tris, lift(inner_rings[i], zin[i]), lift(inner_rings[i + 1], zin[i + 1]), outward=False)

    # ---- collars: join outer<->inner at each hole (the wall lining of the two ports) ----
    band(tris, lift(rod_hole, 0.0), lift(rod_hole, wall), outward=False)        # rod bore lining
    band(tris, lift(port_hole, H - wall), lift(port_hole, H), outward=False)    # fill port lining

    # ---- NAME on the outer face (raised beads, boolean-free interpenetration) ----
    name = a.name
    if name:
        name_top = port_cy - port_r - 2.0
        name_bot = -RH + 3.0
        name_cy = 0.5 * (name_top + name_bot)
        name_h = min(0.42 * RH, 0.9 * max(2.0, name_top - name_bot))
        w = text_width(name, name_h)
        if w > 1.72 * RH:
            name_h *= 1.72 * RH / w
        emboss_on_plane(tris, name, center=(0.0, name_cy, H), x_dir=(1.0, 0.0, 0.0),
                        y_dir=(0.0, 1.0, 0.0), normal=(0.0, 0.0, 1.0), height_mm=name_h)

    cav = cavity_volume(a.end_shape, size, wall, side_n)
    info = dict(size=size, H=H, RH=RH, rod_r=rod_r, port_r=port_r, vf=vf, cav=cav,
                mass=cav * a.fill_density / 1.0e6)              # kg (mm^3 * g/cc / 1e6)
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
    ap.add_argument("--end-shape", choices=("sphere", "hex", "barrel"), default="sphere")
    ap.add_argument("--grip-dia", type=float, default=32.0, help="grip outer diameter mm")
    ap.add_argument("--grip-len", type=float, default=130.0, help="grip length mm")
    ap.add_argument("--name", default="GIFT", help="name embossed on each end's outer face")
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
        print(f"  {a.end_shape} end sized to size={info['size']:.1f}mm, height {info['H']:.1f}mm, "
              f"medallion Ø{2*info['RH']:.1f}")
        print(f"  target per-end fill {info['vf']/1e3:.0f} cc -> modeled cavity {info['cav']/1e3:.0f} cc "
              f"= {info['mass']:.2f} kg gypsum/end ({2*info['mass']:.2f} kg total, target {a.weight:g})")
        print(f"  rod bore Ø{2*info['rod_r']:.2f} (grip side), fill port Ø{2*info['port_r']:.1f} (outer face), "
              f"name '{a.name}' — ROD CORE MANDATORY, ends identical for balance, POUR UNPROVEN")

    if a.part in ("grip", "all"):
        tris, info = build_grip(a)
        path = (base if a.part == "grip" and a.out else f"{stem}_grip{ext}")
        _emit(path, tris, "GRIP")
        print(f"  grip Ø{a.grip_dia:g} x {info['L']:g}mm, {info['ridges']} flutes, "
              f"through-bore Ø{2*info['bore_r']:.2f} for the rod core")


if __name__ == "__main__":
    main()
