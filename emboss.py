#!/usr/bin/env python3
"""emboss.py — PERSONALIZED RAISED TEXT on a printed shell, WATERTIGHT and BOOLEAN-FREE.

The two gift/personalization generators import this to write a name / short message onto their
formwork: text stands proud as a RAISED BEAD (a "rib"). No CSG, no boolean subtraction — the same
trick the rest of crackle uses: build each rib as its OWN individually-watertight closed sub-solid
that INTERPENETRATES the shell, and let the SLICER union the soup.

HOW A RIB IS BUILT — the CAPSULE CHAIN. Each letter is a set of stroke polylines (a stick / single-
stroke vector font). Every stroke becomes a chain of watertight primitives that overlap each other
and dip into the shell:
  * a CYLINDER along each segment (both ends capped), and
  * a SPHERE at each vertex (lat-long, proper pole fans),
each closed on its own. Overlapping closed solids can only ADD volume, never subtract, so the union
is always a valid solid and the mesh is edge-parity clean with zero booleans. Rib radius ~0.8-1.2mm.

The rib centreline sits ~0.4mm BELOW the surface (rib_r - raise) so the bead is anchored INTO the
wall and crests ~raise_mm proud. The wall must be thick enough to swallow that (the importing
generator's job, not this module's).

STAGE / HONESTY: this is geometry only. Nothing here is cast or printed yet; the gypsum POUR that
these formworks are for is UNPROVEN (not physically poured). This module is verified watertight in
software (filesize law + edge parity), which is a mesh guarantee, NOT a proof that a print or a pour
succeeds. Do not phrase any of it as proven.

PUBLIC API (append triangles to a caller-provided list; nothing is returned but the list grows):
  text_strokes(s, height_mm, tracking=0.12) -> [ [ (x_mm, y_mm), ... ], ... ]   baseline y=0, x grows
  text_width(s, height_mm, tracking=0.12)   -> float   (mm, pen advance across the whole string)
  emboss_on_cylinder(tris, s, cyl_radius, z_center, angle_center_rad, height_mm, rib_r=1.0, raise_mm=0.6)
  emboss_on_plane(tris, s, center, x_dir, y_dir, normal, height_mm, rib_r=1.0, raise_mm=0.6)
Primitive builders (each proven watertight on its own in the self-test):
  add_sphere(tris, c, r, nlat, nlon)
  add_cylinder(tris, p0, p1, r, n, phase=0.0)
Heart glyph: the character emboss.HEART ('♥'). Include it in any string.

Self-test:  python3 emboss.py   -> writes emboss_test.stl ("GIFT<heart>" wrapped on a Ø80 cylinder +
"OLEG" on a plane), runs verify (MUST be 0 open edges), prints tri/edge counts, renders emboss_test.png.
"""
import argparse, math, os, struct

HEART = "♥"   # key into FONT for a filled-outline heart glyph


# ----------------------------------------------------------------------------- STL io + verify
def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris, header=b"crackle emboss - raised text ribs (capsule chain)"):
    with open(path, "wb") as fh:
        fh.write(header.ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            fh.write(struct.pack("<3f", *normal(a, b, c)))
            for v in (a, b, c):
                fh.write(struct.pack("<3f", *v))
            fh.write(struct.pack("<H", 0))


def verify(path, tris):
    """Assert the binary-STL laws and return (ntris, open_edge_count, bounds). open_edges MUST be 0."""
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
            fh.read(12)                                            # skip stored normal
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


# ----------------------------------------------------------------------------- vector helpers
def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v):
    m = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (0.0, 0.0, 0.0) if m < 1e-12 else (v[0] / m, v[1] / m, v[2] / m)


# ----------------------------------------------------------------------------- watertight primitives
# The sphere's pole axis is deliberately OBLIQUE (not a world axis). A capsule-chain sphere sits at
# the same point as the end caps of the cylinders meeting there; a cylinder cap ring is a radius-r
# circle centred on that point, and the ONLY sphere ring through the centre is the equator. If the
# sphere's equator were horizontal it would coincide edge-for-edge with the cap ring of any world-Z
# cylinder (a vertical stroke), and that edge would then be shared by 4 triangles -> a false open
# edge. An oblique pole axis keeps every latitude ring off every cap plane, so no ring ever matches.
_SPHERE_W = _unit((1.0, 2.0, 3.0))
_SPHERE_U = _unit(_cross((1.0, 0.0, 0.0), _SPHERE_W))
_SPHERE_V = _cross(_SPHERE_W, _SPHERE_U)


def add_sphere(tris, c, r, nlat, nlon):
    """A lat-long sphere: nlat latitude bands (pole to pole), nlon longitude slices, built on an
    OBLIQUE pole axis (_SPHERE_W). Two triangle FANS at the poles (a single shared pole vertex) +
    quad bands between interior rings. Closed + watertight: every ring vertex is computed by one
    formula so adjacent bands share it exactly, and the longitude seam reuses j=0 (k=(j+1)%nlon)."""
    cx, cy, cz = c
    nlat = max(2, int(nlat)); nlon = max(3, int(nlon))
    ux, uy, uz = _SPHERE_U
    vx, vy, vz = _SPHERE_V
    wx, wy, wz = _SPHERE_W

    def ring(i):
        phi = math.pi * i / nlat                                  # 0 at north pole, pi at south
        zr = math.cos(phi) * r                                    # along the oblique pole axis W
        rr = math.sin(phi) * r                                    # radius in the U,V plane
        out = []
        for j in range(nlon):
            a = 2 * math.pi * j / nlon
            ca, sa = rr * math.cos(a), rr * math.sin(a)
            out.append((cx + zr * wx + ca * ux + sa * vx,
                        cy + zr * wy + ca * uy + sa * vy,
                        cz + zr * wz + ca * uz + sa * vz))
        return out

    north = (cx + r * wx, cy + r * wy, cz + r * wz)
    south = (cx - r * wx, cy - r * wy, cz - r * wz)
    r1 = ring(1)
    for j in range(nlon):                                         # north pole fan
        k = (j + 1) % nlon
        tris.append((north, r1[j], r1[k]))
    for i in range(1, nlat - 1):                                  # quad bands
        a = ring(i); b = ring(i + 1)
        for j in range(nlon):
            k = (j + 1) % nlon
            tris.append((a[j], b[j], b[k]))
            tris.append((a[j], b[k], a[k]))
    rN = ring(nlat - 1)
    for j in range(nlon):                                         # south pole fan (reverse wind)
        k = (j + 1) % nlon
        tris.append((south, rN[k], rN[j]))


def add_cylinder(tris, p0, p1, r, n, phase=0.0):
    """A closed cylinder (both end caps) from p0 to p1, radius r, n sides. Zero-length segments are
    skipped (return without appending). A `phase` offset rotates the ring so two collinear cylinders
    meeting at a shared endpoint never produce an identical ring (which would break edge parity)."""
    axis = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    L = math.sqrt(axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2)
    if L < 1e-9:
        return
    az = (axis[0] / L, axis[1] / L, axis[2] / L)
    ref = (0.0, 0.0, 1.0) if abs(az[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = _unit(_cross(ref, az))
    v = _cross(az, u)                                             # unit; {az,u,v} orthonormal

    def ring(center):
        pts = []
        for j in range(n):
            t = phase + 2 * math.pi * j / n
            cs, sn = math.cos(t), math.sin(t)
            pts.append((center[0] + r * (cs * u[0] + sn * v[0]),
                        center[1] + r * (cs * u[1] + sn * v[1]),
                        center[2] + r * (cs * u[2] + sn * v[2])))
        return pts

    c0 = ring(p0); c1 = ring(p1)
    for j in range(n):                                           # side wall
        k = (j + 1) % n
        tris.append((c0[j], c0[k], c1[k]))
        tris.append((c0[j], c1[k], c1[j]))
    for j in range(n):                                           # cap at p0 (apex = p0)
        k = (j + 1) % n
        tris.append((p0, c0[k], c0[j]))
    for j in range(n):                                           # cap at p1 (apex = p1)
        k = (j + 1) % n
        tris.append((p1, c1[j], c1[k]))


# ----------------------------------------------------------------------------- capsule chain (a rib)
def add_capsule_chain(tris, pts, rib_r, placed_c=None, placed_s=None, nlat=6, nlon=8, cn=8):
    """Render a 3D centreline polyline as a rib: a cylinder per segment + a sphere per vertex, all
    interpenetrating (the slicer unions them). Two robustness rules keep the soup EDGE-PARITY clean:

    1. Cylinder ends are INSET (pulled ~0.4*rib_r toward the segment interior) so no two cylinders
       ever share an endpoint. Without this, at a vertex where two strokes meet (e.g. the branch of
       'Y'), both cap rings pass through centre ± rib_r*(common perpendicular) and that cap edge is
       shared by 4 triangles — a false open edge. The sphere at the full (un-inset) vertex, radius
       rib_r, always overlaps the inset caps, so the bead stays gap-free.
    2. `placed_c` / `placed_s` are optional dedup sets (rounded-key, shared across all strokes of one
       emboss call): they drop EXACT-duplicate primitives (two strokes sharing an identical segment
       or vertex), which would otherwise be miscounted."""
    if placed_c is None:
        placed_c = set()
    if placed_s is None:
        placed_s = set()

    def rk(p):
        return (round(p[0], 3), round(p[1], 3), round(p[2], 3))

    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        L = math.dist(p0, p1)
        if L < 1e-4:
            continue
        t = min(0.4 * rib_r, 0.4 * L) / L                        # inset fraction (never inverts)
        q0 = (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t, p0[2] + (p1[2] - p0[2]) * t)
        q1 = (p1[0] - (p1[0] - p0[0]) * t, p1[1] - (p1[1] - p0[1]) * t, p1[2] - (p1[2] - p0[2]) * t)
        ck = tuple(sorted((rk(q0), rk(q1))))
        if ck in placed_c:
            continue
        placed_c.add(ck)
        add_cylinder(tris, q0, q1, rib_r, cn, phase=0.31 * i)
    for p in pts:
        sk = rk(p)
        if sk in placed_s:
            continue
        placed_s.add(sk)
        add_sphere(tris, p, rib_r, nlat, nlon)


# ----------------------------------------------------------------------------- stick vector font
# A single-stroke ("stick") font on a 5x5 unit-em grid. y=0 is the baseline, y=1 the cap height;
# x grows rightward. Glyphs are lists of stroke polylines; each polyline is a list of grid indices
# (ix, iy) into _X / _Y. Closed glyphs (O, 0, ...) simply end where they began.
_X = (0.0, 0.14, 0.28, 0.42, 0.56)
_Y = (0.0, 0.25, 0.50, 0.75, 1.0)

_GLYPHS = {
    "A": [[(0, 0), (2, 4), (4, 0)], [(1, 2), (3, 2)]],
    "B": [[(0, 0), (0, 4), (3, 4), (4, 3), (3, 2), (0, 2)], [(3, 2), (4, 1), (3, 0), (0, 0)]],
    "C": [[(4, 3), (3, 4), (1, 4), (0, 3), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "D": [[(0, 0), (0, 4), (2, 4), (4, 3), (4, 1), (2, 0), (0, 0)]],
    "E": [[(4, 4), (0, 4), (0, 0), (4, 0)], [(0, 2), (3, 2)]],
    "F": [[(0, 0), (0, 4), (4, 4)], [(0, 2), (3, 2)]],
    "G": [[(4, 3), (3, 4), (1, 4), (0, 3), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (2, 2)]],
    "H": [[(0, 0), (0, 4)], [(4, 0), (4, 4)], [(0, 2), (4, 2)]],
    "I": [[(1, 4), (3, 4)], [(2, 4), (2, 0)], [(1, 0), (3, 0)]],
    "J": [[(0, 1), (1, 0), (2, 0), (3, 1), (3, 4)]],
    "K": [[(0, 0), (0, 4)], [(4, 4), (0, 2), (4, 0)]],
    "L": [[(0, 4), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 4), (2, 2), (4, 4), (4, 0)]],
    "N": [[(0, 0), (0, 4), (4, 0), (4, 4)]],
    "O": [[(1, 4), (3, 4), (4, 3), (4, 1), (3, 0), (1, 0), (0, 1), (0, 3), (1, 4)]],
    "P": [[(0, 0), (0, 4), (3, 4), (4, 3), (3, 2), (0, 2)]],
    "Q": [[(1, 4), (3, 4), (4, 3), (4, 1), (3, 0), (1, 0), (0, 1), (0, 3), (1, 4)], [(2, 1), (4, 0)]],
    "R": [[(0, 0), (0, 4), (3, 4), (4, 3), (3, 2), (0, 2)], [(2, 2), (4, 0)]],
    "S": [[(4, 3), (3, 4), (1, 4), (0, 3), (1, 2), (3, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "T": [[(0, 4), (4, 4)], [(2, 4), (2, 0)]],
    "U": [[(0, 4), (0, 1), (1, 0), (3, 0), (4, 1), (4, 4)]],
    "V": [[(0, 4), (2, 0), (4, 4)]],
    "W": [[(0, 4), (1, 0), (2, 2), (3, 0), (4, 4)]],
    "X": [[(0, 0), (4, 4)], [(0, 4), (4, 0)]],
    "Y": [[(0, 4), (2, 2), (4, 4)], [(2, 2), (2, 0)]],
    "Z": [[(0, 4), (4, 4), (0, 0), (4, 0)]],
    "0": [[(1, 4), (3, 4), (4, 3), (4, 1), (3, 0), (1, 0), (0, 1), (0, 3), (1, 4)], [(1, 1), (3, 3)]],
    "1": [[(1, 3), (2, 4), (2, 0)], [(1, 0), (3, 0)]],
    "2": [[(0, 3), (1, 4), (3, 4), (4, 3), (0, 0), (4, 0)]],
    "3": [[(0, 3), (1, 4), (3, 4), (4, 3), (2, 2)], [(4, 1), (3, 0), (1, 0), (0, 1)], [(2, 2), (4, 1)]],
    "4": [[(3, 0), (3, 4), (0, 1), (4, 1)]],
    "5": [[(4, 4), (0, 4), (0, 2), (3, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "6": [[(4, 3), (3, 4), (1, 4), (0, 3), (0, 1), (1, 0), (3, 0), (4, 1), (3, 2), (0, 2)]],
    "7": [[(0, 4), (4, 4), (1, 0)]],
    "8": [[(1, 4), (3, 4), (4, 3), (3, 2), (1, 2), (0, 3), (1, 4)],
          [(1, 2), (3, 2), (4, 1), (3, 0), (1, 0), (0, 1), (1, 2)]],
    "9": [[(0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (3, 4), (1, 4), (0, 3), (1, 2), (4, 2)]],
    "-": [[(1, 2), (3, 2)]],
    ".": [[(2, 0)]],
    "&": [[(4, 0), (0, 3), (1, 4), (2, 4), (2, 3), (0, 1), (1, 0), (2, 0), (4, 2)]],
    "'": [[(2, 4), (2, 3)]],
    " ": [],
}

# per-glyph advance in em units (glyph body spans 0..0.56); tracking adds the gap between glyphs.
_ADV = {"I": 0.42, "J": 0.50, "1": 0.50, "M": 0.66, "W": 0.66, "&": 0.68,
        "-": 0.56, ".": 0.30, "'": 0.28, " ": 0.42}
_ADV_DEFAULT = 0.62


def _heart_polyline(n=32):
    """A closed heart outline from the classic parametric curve, normalized into the em box
    (uniform scale, centred at x=0.28, base at y=0). Generated FROM the formula, not hand-placed."""
    raw = []
    for i in range(n):
        t = 2 * math.pi * i / n
        hx = 16 * math.sin(t) ** 3
        hy = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        raw.append((hx, hy))
    xs = [p[0] for p in raw]; ys = [p[1] for p in raw]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = min(0.56 / (x1 - x0), 1.0 / (y1 - y0))
    cx = (x0 + x1) / 2.0
    pts = [((hx - cx) * s + 0.28, (hy - y0) * s) for (hx, hy) in raw]
    pts.append(pts[0])                                            # close the loop
    return pts


def _build_font():
    font = {}
    for ch, strokes in _GLYPHS.items():
        polys = [[(_X[ix], _Y[iy]) for (ix, iy) in poly] for poly in strokes]
        font[ch] = (_ADV.get(ch, _ADV_DEFAULT), polys)
    font[HEART] = (0.66, [_heart_polyline()])
    return font


FONT = _build_font()


# ----------------------------------------------------------------------------- text layout (public)
def _glyph(ch):
    if ch in FONT:
        return FONT[ch]
    up = ch.upper()
    if up in FONT:
        return FONT[up]
    return FONT[" "]                                             # unknown -> blank space advance


def text_strokes(s, height_mm, tracking=0.12):
    """Lay the string out left-to-right at scale height_mm. Returns a list of stroke polylines in mm
    (baseline y=0, x grows). Each glyph's unit-em coords are scaled by height_mm and shifted by the
    running pen; tracking (em units) adds a gap between glyphs."""
    strokes = []
    pen = 0.0
    n = len(s)
    for i, ch in enumerate(s):
        adv, polys = _glyph(ch)
        for poly in polys:
            strokes.append([(pen + gx * height_mm, gy * height_mm) for (gx, gy) in poly])
        pen += adv * height_mm
        if i != n - 1:
            pen += tracking * height_mm
    return strokes


def text_width(s, height_mm, tracking=0.12):
    """Total pen advance (mm) of the laid-out string — used to centre it in emboss_*."""
    pen = 0.0
    n = len(s)
    for i, ch in enumerate(s):
        adv, _ = _glyph(ch)
        pen += adv * height_mm
        if i != n - 1:
            pen += tracking * height_mm
    return pen


def _subdivide(poly, max_step):
    """Insert intermediate points so no segment exceeds max_step (mm). Keeps a wrapped rib hugging a
    curved surface. A single-point polyline (e.g. '.') passes straight through."""
    if len(poly) < 2:
        return list(poly)
    out = [poly[0]]
    for i in range(1, len(poly)):
        x0, y0 = poly[i - 1]; x1, y1 = poly[i]
        d = math.hypot(x1 - x0, y1 - y0)
        k = max(1, int(math.ceil(d / max_step)))
        for t in range(1, k + 1):
            f = t / k
            out.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
    return out


# ----------------------------------------------------------------------------- emboss (public)
def emboss_on_cylinder(tris, s, cyl_radius, z_center, angle_center_rad, height_mm,
                       rib_r=1.0, raise_mm=0.6):
    """Wrap raised text around a cylinder of radius cyl_radius (axis = world +z). Per the spec:
        angle = angle_center + (x - width/2) / cyl_radius,   z = z_center + (y - height/2)
    where (x, y) are the mm coords of a stroke point. Ribs sit at cyl_radius and stand OUTWARD:
    the rib centreline is placed at (cyl_radius + raise_mm - rib_r) so the bead crests raise_mm proud
    and its base is buried below the surface for interpenetration. Text is centred on angle_center."""
    w = text_width(s, height_mm)
    cr = cyl_radius + raise_mm - rib_r                            # rib CENTRELINE radius
    placed_c, placed_s = set(), set()
    for stroke in text_strokes(s, height_mm):
        pts3d = []
        for (mx, my) in _subdivide(stroke, max_step=2.0):
            ang = angle_center_rad + (mx - w / 2.0) / cyl_radius
            z = z_center + (my - height_mm / 2.0)
            pts3d.append((cr * math.cos(ang), cr * math.sin(ang), z))
        add_capsule_chain(tris, pts3d, rib_r, placed_c, placed_s)


def emboss_on_plane(tris, s, center, x_dir, y_dir, normal, height_mm, rib_r=1.0, raise_mm=0.6):
    """Flat plaque of raised text on a plane (e.g. a dumbbell end cap). center / x_dir / y_dir /
    normal are 3D vectors (x_dir, y_dir span the plane; normal is the proud direction). A stroke
    point (x, y) in mm maps to:
        center + (x - width/2)*x_dir + (y - height/2)*y_dir + (raise_mm - rib_r)*normal
    so the bead crests raise_mm proud along +normal and its base is buried below the surface."""
    w = text_width(s, height_mm)
    xu = _unit(x_dir); yu = _unit(y_dir); nu = _unit(normal)
    off = raise_mm - rib_r
    placed_c, placed_s = set(), set()
    for stroke in text_strokes(s, height_mm):
        pts3d = []
        for (mx, my) in stroke:                                  # planar: no curvature to follow
            px = mx - w / 2.0
            py = my - height_mm / 2.0
            pts3d.append((center[0] + px * xu[0] + py * yu[0] + off * nu[0],
                          center[1] + px * xu[1] + py * yu[1] + off * nu[1],
                          center[2] + px * xu[2] + py * yu[2] + off * nu[2]))
        add_capsule_chain(tris, pts3d, rib_r, placed_c, placed_s)


# ----------------------------------------------------------------------------- self-test
def _selftest():
    here = os.path.dirname(os.path.abspath(__file__))
    out_stl = os.path.join(here, "emboss_test.stl")
    out_png = os.path.join(here, "emboss_test.png")

    # 1) each primitive is watertight ON ITS OWN
    for name, fn in (("sphere", lambda t: add_sphere(t, (0.0, 0.0, 0.0), 3.0, 6, 8)),
                     ("cylinder", lambda t: add_cylinder(t, (0.0, 0.0, 0.0), (10.0, 2.0, 1.0), 1.2, 8))):
        t = []
        fn(t)
        tmp = os.path.join(here, "_emboss_prim.stl")
        write_binary_stl(tmp, t)
        cnt, oe, _ = verify(tmp, t)
        os.remove(tmp)
        assert oe == 0, f"primitive {name} leaks {oe} open edges"
        print(f"  primitive {name:8s}: {cnt:4d} tris, {oe} open edges  [watertight]")

    # 2) the combined emboss: "GIFT<heart>" wrapped on a Ø80 cylinder + "OLEG" on a plane
    tris = []
    emboss_on_cylinder(tris, "GIFT" + HEART, cyl_radius=40.0, z_center=30.0,
                       angle_center_rad=0.0, height_mm=12.0)
    emboss_on_plane(tris, "OLEG", center=(60.0, 0.0, 15.0),
                    x_dir=(0.0, 1.0, 0.0), y_dir=(0.0, 0.0, 1.0), normal=(1.0, 0.0, 0.0),
                    height_mm=12.0)
    write_binary_stl(out_stl, tris)
    cnt, oe, b = verify(out_stl, tris)
    print(f"  emboss_test.stl : {cnt} tris, {oe} open edges  "
          f"[bounds X {b[0]:.1f}..{b[1]:.1f}  Y {b[2]:.1f}..{b[3]:.1f}  Z {b[4]:.1f}..{b[5]:.1f}]")
    assert oe == 0, f"emboss_test.stl leaks {oe} open edges — a primitive/pole-fan/cap bug"
    print(f"  wrote {out_stl}")

    # 3) render three orthographic panels for eyeball review
    try:
        import subprocess, sys
        r = subprocess.run([sys.executable, os.path.join(here, "render_stand_stl.py"),
                            out_stl, out_png, "--title", "EMBOSS  GIFT + heart (cyl) / OLEG (plane)"],
                           cwd=here, capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  {r.stdout.strip()}")
        else:
            print(f"  render skipped (rc={r.returncode}): {r.stderr.strip().splitlines()[-1:] }")
    except Exception as exc:                                      # render is a convenience, not the test
        print(f"  render skipped: {exc}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    _selftest()
