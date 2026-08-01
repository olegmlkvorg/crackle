#!/usr/bin/env python3
"""trashcan_stl.py -- a PERSONALIZED WEIGHTED GIFT BIN (open-top pour, vase doctrine).

What it IS: a thin-wall tapered OPEN bin (a wastebasket) with a SOLID thin floor sitting on the bed
at z=0 and nothing sealed anywhere. The ballast (sand+gypsum slurry) is poured INTO the bin through
the open top, straight onto the floor, and sets as an exposed slab in the base -- a low centre of
gravity so the bin will not tip or blow over. A name stands proud on the side. One printed PLA part,
sliced NORMAL.

WHY THIS SHAPE (the redesign): the previous version cast the mass inside a sealed double-wall ring
cavity in the base. That mesh was watertight -- and UNPRINTABLE: the cavity's roof and floor were
spanning overhangs inside a sealed shell where support can never be removed (830 offending faces
measured by qa_stl.py; the broken part is preserved as fixtures/trashcan_sealed_base.stl). Watertight
is not printable. The fix is the vase doctrine: keep the vessel open so the ballast goes in from one
side, no internal cavity, no fill port, no roof.

HOW IT IS MODELLED (the crackle boolean-free union trick): a soup of individually-watertight closed
sub-solids that INTERPENETRATE; the SLICER unions the soup. Nothing is CSG-subtracted. The sub-solids:
  * body wall  -- a thin (--wall) tapered tube, open at the top (its own closed thin shell);
  * floor      -- a solid thin disc at z=0, rim buried 0.9mm into the body wall so it welds;
  * name       -- raised text wrapped on the side via emboss.emboss_on_cylinder (each letter a
                  watertight capsule-chain rib that interpenetrates the wall, no booleans).

--cover: also emit a drop-in COVER DISC (out root + "_cover.stl"): a flat washer with a Ø20 finger
hole, sized to the bin's inner cross-section at the default pour depth (40mm) minus 1.5mm diametral
clearance. After the slab sets, it drops in through the open top and sits on the gypsum as a clean
floor. It prints flat.

BALLAST TABLE -- measured, not recomputed: after the STL is written, this script reads the FILE back,
slices the inner cavity at successive z planes, and integrates the measured cross-section areas
(Simpson) to get litres and kg at 1.9 g/cc for depths 20/40/70mm. An independent analytic figure is
computed from the input dimensions and the two routes MUST agree within 0.5% or the run FAILS
(crosscheck() -- proven able to fire).

HONEST STAGE -- READ. This is GEOMETRY ONLY. The mesh passes qa_stl.py --class closed (watertight AND
0 spanning overhangs, i.e. printable geometry as measured), but:
  * The gypsum POUR IS UNPROVEN -- nothing here has been physically cast. Do not phrase it as proven.
  * NOTHING HAS BEEN PRINTED. Wall adhesion, emboss legibility, warp: untested on the K2 Plus.
  * Set gypsum is BRITTLE and WATER-SOLUBLE. Indoor bin. The exposed slab top is why the cover disc
    exists; seal the slab (e.g. PVA/varnish) before wet use. The body is a liner, not structure.

FITS: default footprint (Ø top 300) clears the 340 bed; a FITS_340 line is printed. Default --height
350 puts the Z extent at the machine's ~350mm ceiling -- drop --height for margin.

Usage: python3 trashcan_stl.py [--name OLEG] [--height 350] [--top-dia 300] [--bottom-dia 260]
                               [--wall 1.2] [--style round|faceted] [--points 160] [--cover]
                               [--out trashcan.stl]
"""
import argparse, math, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emboss                                                        # noqa: E402  (raised-text ribs)

FACETS = 16                # facet count for --style faceted
GYPSUM_DENSITY = 0.0019    # g/mm^3 (1.9 g/cc sand+gypsum) -- mix-recipe target, not a measured slab
BALLAST_DEPTHS = (20.0, 40.0, 70.0)   # mm, the printed table rows
DEFAULT_POUR_DEPTH = 40.0  # mm, the depth the cover disc is sized for (middle table row)
COVER_CLEAR = 1.5          # mm diametral clearance of the cover disc in the bin
COVER_T = 2.4              # mm cover disc thickness
FINGER_R = 10.0            # mm finger-hole radius in the cover (Ø20)


# ----------------------------------------------------------------------------- 2D profiles
def circle(cx, cy, r, n, phase=0.0, ccw=True):
    pts = [(cx + r * math.cos(phase + 2 * math.pi * j / n),
            cy + r * math.sin(phase + 2 * math.pi * j / n)) for j in range(n)]
    return pts if ccw else pts[::-1]


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


# ----------------------------------------------------------------------------- STL io + verify
def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    m = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx / m, ny / m, nz / m)


def write_binary_stl(path, tris, header=b"crackle trashcan_stl - open weighted bin (top-pour ballast)"):
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


# ------------------------------------------------------------------ MEASURE the emitted artifact
# The ballast table and the cover size come from slicing the WRITTEN FILE, not from the loop math
# that built it (lesson: measure the emitted artifact; verify by a different route).
def read_stl_tris(path):
    tris = []
    with open(path, "rb") as fh:
        fh.read(80)
        (count,) = struct.unpack("<I", fh.read(4))
        for _ in range(count):
            fh.read(12)
            vs = tuple(struct.unpack("<3f", fh.read(12)) for _ in range(3))
            fh.read(2)
            tris.append(vs)
    return tris


def _slice_segments(tris, z):
    """Cut the triangle soup with the plane at height z. Returns oriented 2D segments (p1, p2):
    each segment is directed along n x k (facet normal x +z) so every loop is traversed with one
    consistent orientation and a plain cross-sum gives its enclosed area."""
    segs = []
    for v0, v1, v2 in tris:
        zs = (v0[2], v1[2], v2[2])
        if min(zs) >= z or max(zs) <= z:                      # strictly crossing triangles only
            continue
        pts = []
        for a, b in ((v0, v1), (v1, v2), (v2, v0)):
            if (a[2] - z) * (b[2] - z) < 0.0:
                t = (z - a[2]) / (b[2] - a[2])
                pts.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        if len(pts) != 2:
            continue                                          # vertex exactly on plane: skip sliver
        n = normal(v0, v1, v2)
        d = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
        if d[0] * n[1] - d[1] * n[0] < 0.0:                   # want dir . (ny, -nx) >= 0
            pts.reverse()
        segs.append((pts[0], pts[1]))
    return segs


def _pt_seg_dist(px, py, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def cavity_section(tris, z):
    """Measured inner cross-section of the bin at height z: (area mm^2, inradius mm).
    Expects exactly the bin's two concentric wall loops (outer face, inner face) at that height --
    i.e. z must sit between the floor top and the bottom of the name band. Both loops enclose the
    axis, so under the n x k orientation rule every segment of one loop subtends the origin with
    the same cross sign: the INNER face (surface normal toward the axis) winds counter to the
    outer, so its segments are exactly the positive-cross ones. Radius clustering is NOT used --
    on a faceted bin the facet chord sag exceeds the wall gap and the radii of the two loops
    overlap (found live by crosscheck(); see the guide). The inradius is the closest approach of
    any inner segment to the axis: what a drop-in disc must clear."""
    segs = _slice_segments(tris, z)
    pos = []; n_neg = 0
    for a, b in segs:
        cr = a[0] * b[1] - b[0] * a[1]
        if cr > 0.0:
            pos.append((a, b, cr))
        else:
            n_neg += 1
    if len(pos) < 6 or n_neg < 6:
        raise SystemExit(f"MEASURE FAIL: z={z:.1f} slice has {len(pos)} inner + {n_neg} outer "
                         "segments; expected the bin's two wall faces")
    area = 0.5 * sum(cr for _, _, cr in pos)
    inr = min(_pt_seg_dist(0.0, 0.0, a, b) for a, b, _ in pos)
    if area <= 0.0 or not math.isfinite(inr):
        raise SystemExit(f"MEASURE FAIL: degenerate inner loop at z={z:.1f}")
    return area, inr


def cavity_volume(tris, z0, z1, m=8):
    """Composite Simpson over measured sections. The section area of a linearly tapered polygon
    tube is quadratic in z, so Simpson is exact up to the 0.01mm plane-epsilon."""
    if m % 2:
        m += 1
    h = (z1 - z0) / m
    total = 0.0
    for i in range(m + 1):
        a, _ = cavity_section(tris, z0 + i * h)
        w = 1 if i in (0, m) else (4 if i % 2 else 2)
        total += w * a
    return total * h / 3.0


def crosscheck(measured, analytic, what, tol=0.005):
    """The two routes (slice the emitted file vs analytic from the input dims) MUST agree.
    Fails the run on divergence -- proven able to fire (see guide)."""
    if analytic == 0 or abs(measured - analytic) / abs(analytic) > tol:
        raise SystemExit(f"CROSSCHECK FAIL [{what}]: measured {measured:.1f} vs analytic "
                         f"{analytic:.1f} (tol {tol*100:.1f}%) -- the emitted file disagrees "
                         "with the math that claims to describe it")
    return measured


# ----------------------------------------------------------------------------- build
def build(a):
    tris = []
    H = a.height
    wall = a.wall
    R0 = a.bottom_dia / 2.0                                          # body OUTER radius at the floor
    R1 = a.top_dia / 2.0                                             # body OUTER radius at the rim
    floor_t = wall + 0.3                                             # solid floor thickness

    def Rb(z):                                                       # body outer radius at height z
        return R0 + (R1 - R0) * (z / H)

    n_body = a.points if a.style == "round" else FACETS
    ph_body = 0.0 if a.style == "round" else math.pi / FACETS        # faceted: a flat facet faces +x

    # --- BODY: thin tapered tube, open top, nothing above it ---------------------------------
    ob = circle(0.0, 0.0, R0, n_body, ph_body)
    ot = circle(0.0, 0.0, R1, n_body, ph_body)
    ib = circle(0.0, 0.0, R0 - wall, n_body, ph_body)
    it = circle(0.0, 0.0, R1 - wall, n_body, ph_body)
    add_tube_taper(tris, ob, ot, ib, it, 0.0, H)

    # --- FLOOR: solid thin disc ON THE BED, rim buried 0.9mm into the body wall so it welds.
    # Same point count and phase as the body so a faceted bin gets a faceted floor that stays
    # inside the flats (radius offset only -> no shared/coincident edges).
    add_solid_cylinder(tris, R0 - 0.3, 0.0, floor_t, n_body, ph_body)

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

    info = dict(name_h=name_h, z_name=z_name, cyl_r=cyl_r, floor_t=floor_t,
                n_body=n_body, R0=R0, R1=R1,
                name_band_lo=z_name - name_h / 2.0 - 2.0)           # ribs poke ~1.6 below the glyph box
    return tris, info


def build_cover(cover_r, n):
    """The drop-in cover: a flat washer, cover_r outer, Ø20 finger hole, COVER_T thick. Sits on the
    set slab as a clean floor. Prints flat on the bed, trivially."""
    tris = []
    # a washer IS a straight tube: outer wall + finger-hole wall + top and bottom annuli
    oc = circle(0.0, 0.0, cover_r, n)
    ic = circle(0.0, 0.0, FINGER_R, n)
    add_tube_taper(tris, oc, oc, ic, ic, 0.0, COVER_T)
    return tris


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--height", type=float, default=350.0, help="bin height mm")
    ap.add_argument("--top-dia", type=float, default=300.0, help="top (rim) OUTER diameter mm")
    ap.add_argument("--bottom-dia", type=float, default=260.0, help="bottom OUTER diameter mm")
    ap.add_argument("--wall", type=float, default=1.2, help="shell wall thickness mm")
    ap.add_argument("--style", choices=("round", "faceted"), default="round", help="body cross-section")
    ap.add_argument("--name", default="OLEG", help="raised name on the side ('' for none)")
    ap.add_argument("--points", type=int, default=160, help="samples per round ring")
    ap.add_argument("--cover", action="store_true",
                    help=f"also emit the drop-in cover disc (sized for the {DEFAULT_POUR_DEPTH:g}mm "
                         "default pour depth) as <out-root>_cover.stl")
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
          f"the ~350mm machine ceiling -- lower --height for margin)")
    print(f"  body: {a.style} tapered tube, bottom Ø{a.bottom_dia:g} -> rim Ø{a.top_dia:g}, "
          f"wall {a.wall:g}mm, OPEN top, solid {info['floor_t']:g}mm floor at z=0, height {a.height:g}mm")
    print(f"  no cavity, no port, no roof: the ballast pours in from the open top onto the floor "
          f"and sets as an exposed slab")

    # ---- BALLAST TABLE: measured from the emitted file, cross-checked analytically -------------
    file_tris = read_stl_tris(a.out)
    eps = 0.01
    z_floor = info["floor_t"] + eps
    max_depth = max(list(BALLAST_DEPTHS) + [DEFAULT_POUR_DEPTH])
    if info["floor_t"] + max_depth >= info["name_band_lo"]:
        raise SystemExit("MEASURE FAIL: ballast depth reaches the name band; the two-loop slice "
                         "assumption breaks there. Raise the name (taller --height) or lower depth.")
    c_poly = 0.5 * info["n_body"] * math.sin(2 * math.pi / info["n_body"])   # polygon area coeff

    def ri(z):                                                       # analytic inner circumradius
        return (info["R0"] - a.wall) + (info["R1"] - info["R0"]) * z / a.height

    def analytic_vol(z0, z1):                                        # exact integral of c*ri(z)^2
        s = (info["R1"] - info["R0"]) / a.height
        r0 = ri(z0)
        d = z1 - z0
        return c_poly * (r0 * r0 * d + r0 * s * d * d + s * s * d * d * d / 3.0)

    print(f"  BALLAST (measured by slicing {a.out}; density {GYPSUM_DENSITY*1000:g} g/cc sand+gypsum "
          f"mix target):")
    for depth in BALLAST_DEPTHS:
        v = cavity_volume(file_tris, z_floor, info["floor_t"] + depth)
        crosscheck(v, analytic_vol(z_floor, info["floor_t"] + depth), f"volume@{depth:g}mm")
        print(f"    depth {depth:5.0f} mm -> {v/1e6:.2f} L -> {v*GYPSUM_DENSITY/1000.0:.1f} kg")
    a10, _ = cavity_section(file_tris, info["floor_t"] + 10.0)
    print(f"    pour to taste: ~{a10*10.0*GYPSUM_DENSITY/1000.0:.2f} kg per 10 mm of depth near the "
          f"floor (grows slightly with depth; the bin tapers outward)")
    print(f"  POUR UNPROVEN: nothing has been cast; the masses above are geometry, not a weighed part")

    if a.name:
        print(f"  name '{a.name}' raised {info['name_h']:.0f}mm tall, wrapped @ z{info['z_name']:.0f} "
              f"(~2/3 up) on r{info['cyl_r']:.1f}")

    # ---- COVER: sized off the MEASURED inner section at the default pour depth -----------------
    if a.cover:
        z_cover = info["floor_t"] + DEFAULT_POUR_DEPTH
        _, inr = cavity_section(file_tris, z_cover)
        crosscheck(inr, ri(z_cover) * math.cos(math.pi / info["n_body"]), "cover inradius")
        cover_r = inr - COVER_CLEAR / 2.0
        cov_path = os.path.splitext(a.out)[0] + "_cover.stl"
        cov = build_cover(cover_r, a.points)
        write_binary_stl(cov_path, cov, header=b"crackle trashcan_stl cover - drop-in slab floor disc")
        cn, co, cd, cb = verify(cov_path, cov)
        print(f"  cover: {cov_path}  Ø{2*cover_r:.1f} x {COVER_T:g}mm washer, Ø{2*FINGER_R:g} finger "
              f"hole, {cn} tris, open edges {co}, degenerate {cd}")
        print(f"    sits on the slab at the {DEFAULT_POUR_DEPTH:g}mm default depth "
              f"({COVER_CLEAR:g}mm diametral clearance, measured inradius {inr:.2f}); the bin only "
              f"widens upward, so the drop-in transit from the rim is free by geometry")


if __name__ == "__main__":
    main()
