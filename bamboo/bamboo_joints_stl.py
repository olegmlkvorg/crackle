#!/usr/bin/env python3
"""bamboo_joints_stl.py -- THE LEGO-FOR-BENT-BAMBOO JOINT KIT (Oleg: "all kind of bent bamboo
joint to experiment with, lego style"). One parametric generator, one part per --part flag,
--part all emits the whole kit.

THE LEGO PRINCIPLE: ONE socket standard everywhere + quantized geometry, so any joint combines
with any other.

SOCKET STANDARD (v2, 2026-08-02 -- every constant imports from rod_constants.py; a magic
number here is a bug):
  rod    the sticks MEASURE O5.8-6.2 variable per stick (calipers 2026-08-02), NOT the nominal
         6.35 the v1 kit assumed
  bore   O7.0 FLAT, everywhere. Stick to the stick size: clears the fattest stick by 0.8; the
         graded TPU shim rings (shim_ring_stl.py) fill the per-stick difference and provide the
         grip the old +0.70 press constant used to buy. No fit variants any more.
  depth  DERIVED, not picked (rod_constants.derive_socket_depth): a 610 mm rod with 20 N on the
         end puts M = 12200 N.mm on the joint; the prying couple crushes PLA at the mouth and
         blind end at sigma = 2M/(w d^2). v1's 12 mm sat AT the ~28 MPa crush figure; the
         derived 24.10 mm sits at 7 MPa = crush/4. Every part got LONGER -- that is the point.
  wall   >= 2.4 mm of material around every bore (measured off the emitted mesh)
  pin    O3.0 vertical cross-pin hole through every socket at 6.0 from the mouth (the stave
         retainer trick: bamboo skewer locks the rod)
  roof   horizontal bores carry a 46deg teardrop roof (facet nz = -0.695 > the -0.707 gate;
         a round bore ceiling is a spanning overhang and fails qa_stl PRINTABLE)

NO DEAD FILLER (v2): every planar multi-socket part (sleeve L90 T X Y120 hub6) carries an OPEN
middle -- the hub interior is a through-void with 2.4 walls, so the plastic between the blind
ends is a hole, not filler. Self-verify shoots a vertical ray through the hub centre and FAILS
if it hits anything (--sabotage filler proves the gate fires). The tetra keeps its middle: its
three walked bores now converge to within ~2 mm of the axis at the floor -- that middle IS
bore, not filler (measured note printed).

QUANTIZED: port width W=13 everywhere, one planar part height H (~13.5), one boss length
DEPTH+1.4, angles from {45, 60, 90, 120} (angle15 = the 165deg bent-rod-end kink, the stave
~14deg number rounded to the 15 grid).

KIT: sleeve L90 T X Y120 hub6 tetra saddle angle15 foot
  tetra NOTE: a true tetrahedral node needs bores tilted 54.7deg from vertical -- past the ~40deg
  walked-bore ceiling stave_hub proved. Per spec it therefore falls back to a 3-LEG TRIPOD NODE:
  3 sockets splayed 30deg from vertical as walked oblique bores (1/cos30 pre-stretch, the
  stave_hub technique), pin = horizontal O3 teardrop channel through the outer wall into each
  bore (single-wall pin: a through-pin would need an unwalkable 60deg hole; said honestly here).
  saddle NOTE: grips a BOWED rod mid-arc. R>=1000 sagitta over the ~13.5mm clip is 0.02mm --
  locally straight, so the clip bore is a straight O7.0 channel with a 0.90 x rod mouth (add a
  shim ring under the clip for thin sticks, same as the sockets).

CONSTRUCTION: watertight-by-construction z-loft. Each part = hub prism + socket blocks glued on
exact shared port rectangles, all lofted on ONE shared z-layer list (no T-vertices). Where the
vertical pin tube meets the horizontal bore void the cross-section topology changes; those
transitions happen at PINCH planes (bore width exactly 0) where both structures coincide
vertex-for-vertex, so edge parity survives. Every part is checked by measuring the EMITTED STL
(re-read from disk), and a failing part is quarantine-renamed .FAILED.

Usage:
  python3 bamboo_joints_stl.py --part all [--out-dir DIR]
  python3 bamboo_joints_stl.py --part hub6
  python3 bamboo_joints_stl.py --part sleeve --sabotage bore --out-dir /tmp/x   # prove gates fire
  python3 bamboo_joints_stl.py --part hub6 --sabotage filler                    # prove void gate
"""
import argparse
import math
import os
import struct
import sys

import rod_constants as RC

# ---------------------------------------------------------------- constants
ROD_D = RC.ROD_NOM           # rods MEASURE 5.8-6.2; nominal mid used for ratios only
BORE = RC.BORE               # O7.0 FLAT socket bore, no fit variants (shims do the fitting)
DEPTH = RC.derive_socket_depth()      # 24.10 -- DERIVED (arithmetic in rod_constants docstring)
WALL_MIN = 2.4               # min wall around every bore
BOT_WALL = 2.5               # designed wall under the bore (>= WALL_MIN)
W = 13.0                     # port width = hub side length, everywhere (bore + 2 walls = 11.8)
LB = DEPTH + 1.4             # boss (block) length: derived depth + 1.4 blind wall (hub behind)
PIN_D = 3.0                  # cross-pin (bamboo skewer)
PIN_FROM_MOUTH = 6.0
ROOF_DEG = 46.0              # teardrop roof angle from horizontal (facet nz -0.695 > -0.707)
S45 = math.sin(math.radians(45.0))
C45 = math.cos(math.radians(45.0))
T_ROOF = math.tan(math.radians(ROOF_DEG))
APEXF = S45 + C45 * T_ROOF   # apex height above bore centre, in bore radii (= 1.4394)
PIN_N = 16                   # pin hole polygon
PINR = (PIN_D / 2.0) / math.cos(math.pi / PIN_N)   # outscribed: inscribed circle = O3.0 exactly
POCKET_M = 8                 # pocket chain segments (must divide PIN_N/2)
TRI_TILT = 30.0              # tripod socket tilt from vertical (printable walked bore)
PARTS = ("sleeve", "L90", "T", "X", "Y120", "hub6", "tetra", "saddle", "angle15", "foot")
VOID_PARTS = ("sleeve", "L90", "T", "X", "Y120", "hub6")   # hub middle = through-void, 2.4 walls
PLA_G_PER_MM3 = 1.24e-3      # PLA density, for the grams report


def geom(r):
    """Derived vertical structure for bore radius r."""
    zc = BOT_WALL + r
    z45 = zc + r * S45
    zapex = zc + r * APEXF
    H = zapex + BOT_WALL
    return zc, z45, zapex, H


# ---------------------------------------------------------------- mesh sink
class Sink:
    def __init__(self):
        self.tris = []

    def tri(self, a, b, c):
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        if nx * nx + ny * ny + nz * nz < 1e-16:      # exact pinch collapse -> drop
            return
        self.tris.append((a, b, c))

    def quad(self, a0, a1, b1, b0):
        """a = lower layer pts (i, i+1), b = upper. CCW loops -> outward normals."""
        self.tri(a0, a1, b1)
        self.tri(a0, b1, b0)


def loft(sink, layers, tf):
    """layers: list of (z, loops); loops: list of (pts2d, skipset). Consecutive layers must have
    identical structure (same loop count + vertex counts). tf: 2D->2D placement transform."""
    for (za, la), (zb, lb) in zip(layers, layers[1:]):
        for (pa, skip), (pb, _s) in zip(la, lb):
            n = len(pa)
            for i in range(n):
                if i in skip:
                    continue
                j = (i + 1) % n
                ax, ay = tf(*pa[i]); bx, by = tf(*pa[j])
                cx, cy = tf(*pb[j]); dx, dy = tf(*pb[i])
                sink.quad((ax, ay, za), (bx, by, za), (cx, cy, zb), (dx, dy, zb))


# ------------------------------------------------------------ triangulation
def _area2(pts):
    s = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        s += x0 * y1 - x1 * y0
    return s


def earclip(pts):
    """Simple polygon (CCW, no holes) -> list of index triples. Tolerates collinear verts."""
    n = len(pts)
    idx = list(range(n))
    out = []
    guard = 0
    while len(idx) > 3 and guard < 10 * n * n:
        guard += 1
        clipped = False
        m = len(idx)
        for k in range(m):
            i0, i1, i2 = idx[(k - 1) % m], idx[k], idx[(k + 1) % m]
            ax, ay = pts[i0]; bx, by = pts[i1]; cx, cy = pts[i2]
            cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            if cross < -1e-9:
                continue                      # reflex
            if cross < 1e-9:
                idx.pop(k)                    # collinear ear: remove, emit nothing
                clipped = True
                break
            ok = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                px, py = pts[j]
                d1 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
                d2 = (cx - bx) * (py - by) - (cy - by) * (px - bx)
                d3 = (ax - cx) * (py - cy) - (ay - cy) * (px - cx)
                if d1 > 1e-9 and d2 > 1e-9 and d3 > 1e-9:
                    ok = False
                    break
            if ok:
                out.append((i0, i1, i2))
                idx.pop(k)
                clipped = True
                break
        if not clipped:
            raise RuntimeError("earclip stuck (%d verts left)" % len(idx))
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


def ring_merge(outer, hole, center):
    """Triangulate the ring between a star-shaped outer loop (CCW) and a hole loop (CW), both
    star-shaped about `center`. Two-pointer angle merge with unwrapped angles."""
    cx, cy = center

    def ang(p):
        return math.atan2(p[1] - cy, p[0] - cx)

    def unwrap(loop, ref=None):
        """Rotate a CCW star-shaped loop to start at its min angle (or at the first vertex CCW
        of `ref`) and return (rotated loop, nondecreasing unwrapped angles from that start)."""
        raw = [ang(p) for p in loop]
        if ref is None:
            i0 = min(range(len(loop)), key=lambda i: raw[i])
            base = raw[i0]
        else:
            i0 = min(range(len(loop)), key=lambda i: (raw[i] - ref) % (2 * math.pi))
            base = ref + ((raw[i0] - ref) % (2 * math.pi))
        rot = loop[i0:] + loop[:i0]
        a = [base] + [base + ((ang(p) - base) % (2 * math.pi)) for p in rot[1:]]
        for k in range(1, len(a)):              # monotonic guard against jitter
            if a[k] < a[k - 1]:
                a[k] = a[k - 1]
        return rot, a

    O, Oa = unwrap(outer)
    H, Ha = unwrap(hole[::-1], ref=Oa[0])       # CW -> CCW, start aligned into O's window
    no, nh = len(O), len(H)
    tris = []
    i = j = 0
    end_o = Oa[0] + 2 * math.pi
    end_h = Ha[0] + 2 * math.pi
    while i < no or j < nh:
        na_o = Oa[i + 1] if i + 1 < no else end_o
        na_h = Ha[j + 1] if j + 1 < nh else end_h
        if i < no and (j >= nh or na_o <= na_h):
            tris.append((O[i % no], O[(i + 1) % no], H[j % nh]))
            i += 1
        else:
            tris.append((H[(j + 1) % nh], H[j % nh], O[i % no]))
            j += 1
    return tris


def emit_cap(sink, tri_pts, z, up, tf):
    for a, b, c in tri_pts:
        pa = tf(*a) + (z,)
        pb = tf(*b) + (z,)
        pc = tf(*c) + (z,)
        if up:
            sink.tri(pa, pb, pc)
        else:
            sink.tri(pa, pc, pb)


def cap_from_indices(pts, idx_tris):
    return [(pts[i], pts[j], pts[k]) for i, j, k in idx_tris]


# ------------------------------------------------------------- socket block
def pin_loop(pc):
    """Pin hole polygon, CW viewed from +z (hole loop). Vert 0 at angle 0."""
    pts = []
    for k in range(PIN_N):
        a = -2.0 * math.pi * k / PIN_N
        pts.append((pc + PINR * math.cos(a), PINR * math.sin(a)))
    return pts


def _pin_chain_full(pc, side):
    """Half of the pin polygon on side (-1 lower / +1 upper), ordered for the bore-wall walk.
    Lower: mouth->blind = u decreasing = angles 0..-pi (CW k=0..8).
    Upper: blind->mouth = u increasing = angles -pi..-2pi (CW k=8..16)."""
    pts = []
    ks = range(0, PIN_N // 2 + 1) if side < 0 else range(PIN_N // 2, PIN_N + 1)
    for k in ks:
        a = -2.0 * math.pi * k / PIN_N
        pts.append((pc + PINR * math.cos(a), PINR * math.sin(a)))
    return pts


PIN_SECT = 2.0 * math.pi / PIN_N
PIN_APO = PIN_D / 2.0                        # polygon apothem = inscribed O3.0 exactly


def _poly_pt(pc, theta):
    """Point on the pin polygon boundary at angle theta about the pin centre."""
    k = math.floor(theta / PIN_SECT)
    off = theta - (k + 0.5) * PIN_SECT
    r = PIN_APO / math.cos(off)
    return (pc + r * math.cos(theta), r * math.sin(theta))


def _poly_v_solve(pc, lo, hi, target):
    """Bisect theta in [lo,hi] to where the polygon boundary's v equals target."""
    flo = _poly_pt(pc, lo)[1] - target
    for _ in range(60):
        mid = (lo + hi) / 2.0
        fm = _poly_pt(pc, mid)[1] - target
        if (fm > 0) == (flo > 0):
            lo = mid
            flo = fm
        else:
            hi = mid
    return (lo + hi) / 2.0


def pocket_chain(pc, side, h):
    """POCKET_M+1 pts replacing the bore wall between u=pc+PINR and pc-PINR at |v|=h.
    h=0: exact pin polygon half (pinch coincidence). h>=PINR: pin fully inside the bore ->
    spread on the wall line. Else: the pin polygon clipped at v=side*h, sampled EVENLY IN
    ANGLE so every sample sits ON the vertical pin prism (an arclength resampling skewed the
    layer correspondence and wove >45deg overhang slivers at the bore-bottom pinch --
    measured on the emitted sleeve, 2026-08-02)."""
    if h <= 1e-9:
        return _pin_chain_full(pc, side)
    if h >= PINR - 1e-9:                     # pin fully inside the bore: spread on the wall line
        if side < 0:                         # lower wall walks u decreasing
            us = [pc + PINR - 2.0 * PINR * t / POCKET_M for t in range(POCKET_M + 1)]
        else:                                # upper wall walks u increasing
            us = [pc - PINR + 2.0 * PINR * t / POCKET_M for t in range(POCKET_M + 1)]
        return [(u, side * h) for u in us]
    th_ent = _poly_v_solve(pc, -math.pi / 2.0, 0.0, -h)
    th_exit = _poly_v_solve(pc, -math.pi, -math.pi / 2.0, -h)
    # sample at the polygon's OWN vertex angles clamped into the clip window: interior samples
    # then do not move between layers (vertical tube walls) and the entry retreat becomes a
    # small up-facing floor instead of a folded down-facing sliver
    lower = []
    for t in range(POCKET_M + 1):
        th = min(max(-t * PIN_SECT, th_exit), th_ent)
        u, v = _poly_pt(pc, th)
        if th in (th_ent, th_exit):
            v = -h                                       # entry/exit sit ON the wall line
        lower.append((u, v))
    if side < 0:
        return lower                                     # u decreasing: mouth -> blind
    return [(u, -v) for (u, v) in lower][::-1]           # upper: mirrored, u increasing


def bore_w(z, r):
    """Teardrop bore width at height z (0 outside)."""
    zc, z45, zapex, _H = geom(r)
    if z < zc - r - 1e-9 or z > zapex + 1e-9:
        return 0.0
    if z <= z45:
        dz = z - zc
        w = 2.0 * math.sqrt(max(r * r - dz * dz, 0.0))
    else:
        w = 2.0 * (r * C45 - (z - z45) / T_ROOF)
    return 0.0 if w < 1e-6 else w


NSEG = max(3, int(math.ceil(LB / 4.5)))   # long-edge subdivision: the derived-depth block is
                                          # ~2x longer, and a 2-vert top cap boundary starves
                                          # ring_merge of angular coverage around the pin
                                          # (flipped cap slivers measured on the emitted v2
                                          # sleeve, 2026-08-02); walls, region-B loops and caps
                                          # all share these verts so parity survives


def _long_edge(v, forward):
    """Interior subdivision verts of a block long edge at lateral v, walking +u or -u."""
    us = [LB * k / NSEG for k in range(1, NSEG)]
    return [(u, v) for u in (us if forward else us[::-1])]


def block_loop(z, r, wport):
    """Region-B cross-section loop of a socket block, local coords u in [0,LB] (0=glue,
    LB=mouth), v lateral. Single CCW loop, closing (glue) segment skipped. Long edges carry
    the same NSEG subdivision as block_outer5 so region seams stay vertex-matched."""
    h = bore_w(z, r) / 2.0
    hw = wport / 2.0
    ub = LB - DEPTH
    pc = LB - PIN_FROM_MOUTH
    pts = [(0.0, -hw)] + _long_edge(-hw, True) + [(LB, -hw), (LB, -h)]
    pts += pocket_chain(pc, -1, h)
    pts += [(ub, -h), (ub, h)]
    pts += pocket_chain(pc, +1, h)
    pts += [(LB, h), (LB, hw)] + _long_edge(hw, False) + [(0.0, hw)]
    return (pts, {len(pts) - 1})


def block_outer5(wport):
    hw = wport / 2.0
    pts = ([(0.0, -hw)] + _long_edge(-hw, True) + [(LB, -hw), (LB, 0.0), (LB, hw)]
           + _long_edge(hw, False) + [(0.0, hw)])
    return (pts, {len(pts) - 1})


def dedupe_zs(zs, eps=2e-3):
    """Merge layer heights closer than eps. Two analytically-different heights that ROUND to
    the same 3dp (e.g. a phi-step at 2.67129 vs a vertex-crossing at 2.67088 when r=3.5) weave
    a micro-band whose edges double-count in the parity check -- measured on the emitted v2
    sleeve, 2026-08-02."""
    out = []
    for z in sorted(zs):
        if not out or z - out[-1] > eps:
            out.append(z)
    return out


def bore_band_zs(r):
    """Region-B layer heights. Fine steps near both pinches: the pocket entry point must not
    sweep more than ~one pin-polygon edge per layer, or the swallow of a polygon vertex weaves
    a down-facing sliver (measured on the emitted sleeve, 2026-08-02)."""
    zc, z45, zapex, _H = geom(r)
    phis = list(range(-90, -63, 3)) + list(range(-63, 46, 9))
    zs = {zc + r * math.sin(math.radians(phi)) for phi in phis}
    nroof = max(4, int(math.ceil((zapex - z45) / 0.2)))
    zs.update(z45 + (zapex - z45) * k / nroof for k in range(1, nroof + 1))
    # exact vertex-crossing layers: heights where the clip line passes a pin-polygon vertex
    # (and the hidden<->clip boundary h=PINR), so each swallow degenerates vertically instead
    # of weaving a down-facing chord across the polygon corner
    for h in [PINR * math.sin(k * math.pi / PIN_N * 2) for k in (1, 2, 3)] + [PINR]:
        if h < r:
            zs.add(zc - math.sqrt(r * r - h * h))          # bottom (circle) side
        if h < r * C45:
            zs.add(z45 + (r * C45 - h) * T_ROOF)           # roof side
    # keep a clear window around the h=PINR crossings: the chain re-parameterizes there
    # (straight spread <-> clipped polygon), and a foreign layer a few microns away turns
    # that re-parameterization into down-facing slivers (measured at z=9.46 on the emitted
    # v2 sleeve, 2026-08-02 -- the derived-depth kit moved the phi grid onto the crossing)
    cross = set()
    if PINR < r:
        cross.add(zc - math.sqrt(r * r - PINR * PINR))
    if PINR < r * C45:
        cross.add(z45 + (r * C45 - PINR) * T_ROOF)
    zs = {z for z in zs
          if z in cross or all(abs(z - czz) > 0.06 for czz in cross)}
    return dedupe_zs(zs)


def emit_block(sink, tf, r, wport, z_extra=()):
    """Socket block glued at u=0. tf maps local (u,v)->world. Emits walls+caps, glue face open."""
    zc, z45, zapex, H = geom(r)
    zbot = zc - r
    pc = LB - PIN_FROM_MOUTH
    o5 = block_outer5(wport)
    pin = (pin_loop(pc), set())
    # region A (below bore): outer + pin tube
    zsA = sorted(set([0.0] + [z for z in z_extra if z < zbot - 1e-9] + [zbot]))
    layersA = [(z, [o5, pin]) for z in zsA]
    loft(sink, layersA, tf)
    # region B (bore band): single merged loop; pinch layers at both ends
    layersB = [(z, [block_loop(z, r, wport)]) for z in bore_band_zs(r)]
    loft(sink, layersB, tf)
    # region C (above bore): outer + pin tube
    layersC = [(z, [o5, pin]) for z in (zapex, H)]
    loft(sink, layersC, tf)
    # caps: ring between outer5 and pin hole
    ring = ring_merge(o5[0], pin[0], (pc, 0.0))
    emit_cap(sink, ring, 0.0, False, tf)
    emit_cap(sink, ring, H, True, tf)


# ------------------------------------------------------------- hub + parts
def make_tf(origin, ux, uy):
    ox, oy = origin
    return lambda u, v: (ox + u * ux[0] + v * uy[0], oy + u * ux[1] + v * uy[1])


IDENT = lambda x, y: (x, y)


def block_z_list(r, z_extra=()):
    """Every z where any block has a layer -- the hub must loft on the same list (no T-verts)."""
    _zc, _z45, zapex, H = geom(r)
    zs = [0.0] + bore_band_zs(r) + [zapex, H] + list(z_extra)
    return dedupe_zs(zs)


def hub_void(poly, inset):
    """Hole loop for an OPEN hub middle: the (regular, origin-centred) hub polygon scaled so
    every edge moves inward by `inset`. Returned CW = a hole for loft/ring_merge."""
    apo = min(poly[i][0] * n[0] + poly[i][1] * n[1]
              for i, n in enumerate(_edge_normals(poly)))
    s = (apo - inset) / apo
    assert s > 0.15, "hub too small to void"
    return [(x * s, y * s) for (x, y) in poly][::-1]


def _edge_normals(poly):
    """Unit outward normals of a CCW polygon's edges (edge i = poly[i]->poly[i+1])."""
    out = []
    n = len(poly)
    for i in range(n):
        p0, p1 = poly[i], poly[(i + 1) % n]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        out.append((dy / L, -dx / L))
    return out


def emit_hub(sink, poly, port_sides, r, z_extra=(), caps=(True, True), zs=None, void=None):
    """Convex hub prism on the shared z list; port sides skipped. poly CCW. void = optional CW
    hole loop -> the hub middle is a through-void (caps become rings)."""
    _zc, _z45, _zapex, H = geom(r)
    if zs is None:
        zs = block_z_list(r, z_extra)
    loops = [(poly, set(port_sides))]
    if void is not None:
        loops.append((void, set()))
    loft(sink, [(z, loops) for z in zs], IDENT)
    if void is None:
        tris = cap_from_indices(poly, earclip(poly))
    else:
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        tris = ring_merge(poly, void, (cx, cy))
    if caps[0]:
        emit_cap(sink, tris, zs[0], False, IDENT)
    if caps[1]:
        emit_cap(sink, tris, H, True, IDENT)


def hub_ports(poly, sides, r, wport=W):
    """For each port side return (tf, socket_meta). Side i = poly[i]->poly[i+1], length == wport."""
    out = []
    n = len(poly)
    for i in sides:
        p0, p1 = poly[i], poly[(i + 1) % n]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        assert abs(L - wport) < 1e-6, "port side %d length %.6f != %g" % (i, L, wport)
        t = (dx / L, dy / L)
        nrm = (t[1], -t[0])                     # outward for CCW polygon
        origin = (p0[0] + (wport / 2.0) * t[0], p0[1] + (wport / 2.0) * t[1])
        tf = make_tf(origin, nrm, t)
        out.append((tf, {"type": "planar", "origin": origin, "n": nrm, "t": t}))
    return out


def hub_poly(name, wport):
    """The hub polygon + port-side indices for a planar part. ONE code path: the builder lofts
    it, the verifier measures the emitted void against it."""
    if name in ("sleeve", "L90", "T", "X"):
        h = wport / 2.0
        poly = [(h, -h), (h, h), (-h, h), (-h, -h)]  # CCW: sides 0:+x 1:+y 2:-x 3:-y
        sides = {"sleeve": [0, 2], "L90": [0, 1], "T": [0, 2, 1], "X": [0, 1, 2, 3]}[name]
        return poly, sides
    if name in ("Y120", "hub6"):
        poly = [(wport * math.cos(math.radians(60 * k)),
                 wport * math.sin(math.radians(60 * k))) for k in range(6)]
        return poly, ([0, 2, 4] if name == "Y120" else [0, 1, 2, 3, 4, 5])
    raise ValueError(name)


def part_planar(name, r, sabotage=None):
    """All hub+blocks planar parts. Returns (tris, sockets, note)."""
    wport = 10.0 if sabotage == "wall" else W
    rb = r - 0.25 if sabotage == "bore" else r
    sink = Sink()
    if name in ("sleeve", "L90", "T", "X", "Y120", "hub6"):
        poly, sides = hub_poly(name, wport)
    elif name == "angle15":
        a = math.radians(7.5)
        t = 2.0
        d1 = (-math.cos(a), math.sin(a))
        d2 = (math.cos(a), math.sin(a))
        t1 = (-math.sin(a), -math.cos(a))
        t2 = (-math.sin(a), math.cos(a))
        hw = wport / 2.0
        p1a = (t * d1[0] + hw * t1[0], t * d1[1] + hw * t1[1])
        p1b = (t * d1[0] - hw * t1[0], t * d1[1] - hw * t1[1])
        p2a = (t * d2[0] + hw * t2[0], t * d2[1] + hw * t2[1])
        p2b = (t * d2[0] - hw * t2[0], t * d2[1] - hw * t2[1])
        # CCW: bottom-left, bottom-right, up right port, top-right->top-left, down left port
        poly = [p1a, p2b, p2a, p1b]
        assert _area2(poly) > 0
        sides = [1, 3]
    else:
        raise ValueError(name)
    assert _area2(poly) > 0, "hub polygon must be CCW"
    void = None
    note = ""
    if name in VOID_PARTS and sabotage != "filler":
        void = hub_void(poly, WALL_MIN)
        note = "OPEN middle: hub interior is a through-void, %.1f walls" % WALL_MIN
    ports = hub_ports(poly, sides, rb, wport)
    emit_hub(sink, poly, sides, rb, void=void)
    for tf, _m in ports:
        emit_block(sink, tf, rb, wport)
    sockets = [m for _tf, m in ports]
    return sink.tris, sockets, note


def part_foot(r, sabotage=None):
    wport = 10.0 if sabotage == "wall" else W
    rb = r - 0.25 if sabotage == "bore" else r
    sink = Sink()
    hw = wport / 2.0
    PAD_T = 2.4
    PAD_BACK = 19.5                             # pad: x in [-PAD_BACK, 0]
    py = hw + 6.5
    hub = [(0.0, -hw), (0.0, hw), (-wport, hw), (-wport, -hw)]
    assert _area2(hub) > 0                      # CCW: side 0 = (0,-hw)->(0,hw) = the +x port
    sides = [0]
    ports = hub_ports(hub, sides, rb, wport)
    zs = block_z_list(rb, z_extra=(PAD_T,))
    # pad band z 0..PAD_T
    pad = [(0.0, -py), (0.0, -hw), (0.0, hw), (0.0, py), (-PAD_BACK, py), (-PAD_BACK, -py)]
    if _area2(pad) < 0:
        pad = pad[::-1]
    skip_pad = None
    for i in range(len(pad)):
        j = (i + 1) % len(pad)
        if pad[i] == (0.0, -hw) and pad[j] == (0.0, hw):
            skip_pad = i
    assert skip_pad is not None
    zs_pad = [z for z in zs if z <= PAD_T + 1e-9]
    loft(sink, [(z, [(pad, {skip_pad})]) for z in zs_pad], IDENT)
    pad_tris = cap_from_indices(pad, earclip(pad))
    emit_cap(sink, pad_tris, 0.0, False, IDENT)
    # ring at PAD_T: pad minus hub (U shape around the hub square)
    ring_poly = [(0.0, -py), (0.0, -hw), (-wport, -hw), (-wport, hw), (0.0, hw), (0.0, py),
                 (-PAD_BACK, py), (-PAD_BACK, -py)]
    if _area2(ring_poly) < 0:
        ring_poly = ring_poly[::-1]
    emit_cap(sink, cap_from_indices(ring_poly, earclip(ring_poly)), PAD_T, True, IDENT)
    # hub band PAD_T..H, no bottom cap
    zs_hub = [z for z in zs if z >= PAD_T - 1e-9]
    emit_hub(sink, hub, sides, rb, caps=(False, True), zs=zs_hub)
    for tf, _m in ports:
        emit_block(sink, tf, rb, wport, z_extra=(PAD_T,))
    return sink.tris, [m for _tf, m in ports], "pad 19.5x26 underfoot; rod runs parallel to floor"


def part_saddle(r, sabotage=None):
    """Open C-clip that snaps onto a bowed rod mid-arc + one standard socket branch at 90.
    Printed with the rod axis vertical: every clip surface is a vertical wall."""
    wport = 10.0 if sabotage == "wall" else W
    rb = r - 0.25 if sabotage == "bore" else r
    sink = Sink()
    rc = BORE / 2.0                             # clip cradle = the same standard O7.0 bore
    ro = rc + 2.4                               # ring wall
    hw = wport / 2.0
    mouth = 0.90 * ROD_D                        # 5.715 opening, in the 0.8-0.92 spec band
    g1 = mouth / 2.0
    g2 = g1 + 0.9                               # flare lead-in at the outer lip
    xp = 6.0                                    # port plane at x=-xp
    a_o = math.degrees(math.asin(min(g2 / ro, 1.0)))
    a_i = math.degrees(math.asin(min(g1 / rc, 1.0)))
    pts = [(-xp, -hw), (0.0, -hw), (0.0, -ro)]
    for ad in range(-90 + 10, int(-a_o), 10):
        pts.append((ro * math.cos(math.radians(ad)), ro * math.sin(math.radians(ad))))
    pts.append((math.sqrt(ro * ro - g2 * g2), -g2))     # outer lip, then flare in to the cradle
    ai = -a_i
    steps = 30
    for k in range(steps + 1):                          # cradle arc, the long way round (CW)
        ad = ai - (360.0 - 2 * a_i) * k / steps
        pts.append((rc * math.cos(math.radians(ad)), rc * math.sin(math.radians(ad))))
    pts.append((math.sqrt(ro * ro - g2 * g2), g2))
    for ad in range(int(a_o) + (10 - int(a_o) % 10), 90, 10):
        pts.append((ro * math.cos(math.radians(ad)), ro * math.sin(math.radians(ad))))
    pts += [(0.0, ro), (0.0, hw), (-xp, hw)]
    if _area2(pts) < 0:
        pts = pts[::-1]
    # port = closing segment (-xp,hw)->(-xp,-hw)
    n = len(pts)
    skip = None
    for i in range(n):
        j = (i + 1) % n
        if abs(pts[i][0] + xp) < 1e-9 and abs(pts[j][0] + xp) < 1e-9:
            skip = i
    assert skip is not None
    p0, p1 = pts[skip], pts[(skip + 1) % n]
    ports = hub_ports_from_segment(p0, p1, wport)
    zs = block_z_list(rb)
    loft(sink, [(z, [(pts, {skip})]) for z in zs], IDENT)
    cap = cap_from_indices(pts, earclip(pts))
    _zc, _z45, _zapex, H = geom(rb)
    emit_cap(sink, cap, 0.0, False, IDENT)
    emit_cap(sink, cap, H, True, IDENT)
    tf, meta = ports
    emit_block(sink, tf, rb, wport)
    return sink.tris, [meta], "clip mouth %.2f = %.3fx rod" % (mouth, mouth / ROD_D)


def hub_ports_from_segment(p0, p1, wport):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    assert abs(L - wport) < 1e-6, "port length %.6f" % L
    t = (dx / L, dy / L)
    nrm = (t[1], -t[0])
    origin = (p0[0] + (wport / 2.0) * t[0], p0[1] + (wport / 2.0) * t[1])
    return make_tf(origin, nrm, t), {"type": "planar", "origin": origin, "n": nrm, "t": t}


# ---------------------------------------------------------------- tripod
def part_tetra(r, sabotage=None):
    """Tetra fallback: TRUE tetra bores would tilt 54.7deg (unwalkable, >40deg proven ceiling)
    -> 3-leg tripod node, sockets 30deg from vertical, walked oblique bores (stave technique).

    v2 KILLS THE FILLER two ways (feedback 2026-08-02):
      TAPER  the outer wall follows the walked bores down at the same 30deg instead of a
             cylinder sized for the mouths -- an outward-leaning wall (nz>0 inside, 30deg lean
             outside) prints clean; the old cylinder was mostly dead plastic at the bottom.
      CORE   the middle above the bore convergence is a blind CONE void (apex down, widening
             up, open at the top face). A hole that widens going up exposes only UP-facing
             wall, so it needs no support and no roof. Radius stops at RHO_M/2: the derived
             star-shape bound for the top-cap merge (tangency of the wedge-corner chord)."""
    rb = r - 0.25 if sabotage == "bore" else r
    sink = Sink()
    tilt = math.radians(TRI_TILT)
    FLOOR = BOT_WALL                            # wall under the blind ends
    H = FLOOR + DEPTH * math.cos(tilt)          # derived: full socket depth along the 30deg axis
    a_r = rb / math.cos(tilt)                   # radial semi-axis (pre-stretch)
    b_t = rb                                    # tangential semi-axis
    walk = DEPTH * math.sin(tilt)
    # mouth radius DERIVED from the blind-end separation: adjacent bores 120deg apart at floor
    # radius rho0 sit sqrt(3)*rho0 apart; keep >= 2 ellipse semi-axes + WALL_MIN between axes
    rho0 = (2.0 * a_r + WALL_MIN) / math.sqrt(3.0)
    RHO_M = rho0 + walk                         # mouth centre radius (top face)
    wall_add = (10.0 - BORE) / 2.0 if sabotage == "wall" else WALL_MIN
    NO = 36
    boss_ang = [0.0, 2 * math.pi / 3, 4 * math.pi / 3]
    E = 24
    zp = H - PIN_FROM_MOUTH * math.cos(tilt)    # pin channel centre height (mid-socket-ish)
    pr = PIN_D / 2.0
    zp45 = zp + pr * S45
    zp_apex = zp + pr * APEXF
    zp_bot = zp - pr

    def rho(z):
        return rho0 + (z - FLOOR) * math.tan(tilt)

    def r_apo(z):
        """Outer wall apothem at height z: bore ellipse + wall, tapering with the walk."""
        return rho(max(z, FLOOR)) + a_r + wall_add

    def outer_ring(z):
        rr = r_apo(z) / math.cos(math.pi / NO)
        return [(rr * math.cos(2 * math.pi * k / NO), rr * math.sin(2 * math.pi * k / NO))
                for k in range(NO)]

    R_AP = r_apo(H)                             # top-face apothem (mouth level)
    R_OUT = R_AP / math.cos(math.pi / NO)
    RV_MAX = RHO_M / 2.0                        # core-void ceiling: top-cap star-shape bound
    z_apex = FLOOR + max(a_r + WALL_MIN - rho0, 0.0) / math.tan(tilt)   # rv birth height
    z_kink = FLOOR + (RV_MAX + a_r + WALL_MIN - rho0) / math.tan(tilt)  # rv hits RV_MAX

    def rv(z):
        if sabotage == "filler":
            return 0.0
        return max(0.0, min(rho(z) - a_r - WALL_MIN, RV_MAX))

    def void_loop(z):
        rr = rv(z)
        return [(rr * math.cos(-2 * math.pi * k / NO), rr * math.sin(-2 * math.pi * k / NO))
                for k in range(NO)]             # CW = hole; angles align with outer_ring's

    def ell_center(z, ang):
        rr = rho(z)
        return (rr * math.cos(ang), rr * math.sin(ang))

    def ell_pt(z, ang, psi):
        cx, cy = ell_center(z, ang)
        ca, sa = math.cos(ang), math.sin(ang)
        er = a_r * math.cos(psi)
        et = b_t * math.sin(psi)
        return (cx + er * ca - et * sa, cy + er * sa + et * ca)

    def psi_j(j):
        return -2.0 * math.pi * j / E           # ONE shared expression: pinch chain == hole loop

    def hole_loop(z, ang):
        # CW viewed +z: psi decreasing
        return [ell_pt(z, ang, psi_j(j)) for j in range(E)]

    def chan_w(z):
        if z < zp_bot - 1e-9 or z > zp_apex + 1e-9:
            return 0.0
        if z <= zp45:
            dz = z - zp
            w = 2.0 * math.sqrt(max(pr * pr - dz * dz, 0.0))
        else:
            w = 2.0 * (pr * C45 - (z - zp45) / T_ROOF)
        return 0.0 if w < 1e-6 else w

    def merged_loop(z):
        """Outer 36-gon where each boss vertex is replaced by a channel notch into its bore
        ellipse. At channel pinch (width 0) every notch vertex collapses onto the plain
        outer-vertex + full-ellipse structure of the neighbouring regions, so edge parity
        survives the topology change."""
        c = chan_w(z)
        hc = c / 2.0
        ring = outer_ring(z)
        pts = []
        for k in range(NO):
            ang_k = 2 * math.pi * k / NO
            site = None
            for ang in boss_ang:
                if abs(((ang_k - ang + math.pi) % (2 * math.pi)) - math.pi) < 1e-9:
                    site = ang
            if site is None:
                pts.append(ring[k])
                continue
            ang = site
            va = ring[k]
            ca, sa = math.cos(ang), math.sin(ang)

            def on_edge(sgn):
                # point with tangential coord sgn*hc on the outer edge flanking v_k
                nb = ring[(k + (1 if sgn > 0 else -1)) % NO]
                tv = -va[0] * sa + va[1] * ca
                tn = -nb[0] * sa + nb[1] * ca
                f = 0.0 if abs(tn - tv) < 1e-12 else (sgn * hc - tv) / (tn - tv)
                return (va[0] + f * (nb[0] - va[0]), va[1] + f * (nb[1] - va[1]))

            eA = va if hc < 1e-12 else on_edge(-1)
            eB = va if hc < 1e-12 else on_edge(+1)
            gam = 0.0 if hc < 1e-12 else math.asin(min(hc / b_t, 1.0))
            iA = ell_pt(z, ang, -gam)
            iB = ell_pt(z, ang, +gam)

            def wall(p_out, p_in):
                return [(p_out[0] + t * (p_in[0] - p_out[0]),
                         p_out[1] + t * (p_in[1] - p_out[1])) for t in (0.25, 0.5, 0.75)]

            # ellipse chain the long way round, psi decreasing -gam .. gam-2pi. Sampled at the
            # ellipse polygon's OWN angles clamped into the gap window (same lesson as the pin
            # pocket: a re-spread sampling weaves down-facing slivers at the pinch); at gam==0
            # the angles are EXACTLY psi_j(j) so the chain coincides with hole_loop verts
            chain = []
            for j in range(1, E):
                psi = psi_j(j)
                if psi > -gam:
                    psi = -gam
                elif psi < gam - 2 * math.pi:
                    psi = gam - 2 * math.pi
                chain.append(ell_pt(z, ang, psi))
            pts.extend([eA] + wall(eA, iA) + [iA] + chain + [iB] + wall(eB, iB)[::-1] + [eB])
        return (pts, set())

    # region 1: solid below floor (tapered outer only -- void is born above FLOOR)
    zs1 = [0.0, FLOOR]
    loft(sink, [(z, [(outer_ring(z), set())]) for z in zs1], IDENT)
    # bore floor discs (blind floors), facing up
    for ang in boss_ang:
        hl = hole_loop(FLOOR, ang)
        c = ell_center(FLOOR, ang)
        fan = [(c, hl[(j + 1) % E], hl[j]) for j in range(E)]   # hl is CW -> reversed for +z
        emit_cap(sink, fan, FLOOR, True, IDENT)
    # region 2: outer + 3 walking holes + core void, FLOOR..zp_bot. The void loop is carried
    # degenerate (rv=0, all verts at the axis) below its apex: zero-area quads drop, and the
    # first real circle fans onto the apex point -- the same pinch trick as the pin pockets.
    def holes_layers(zs):
        return [(z, [(outer_ring(z), set())]
                 + [(hole_loop(z, ang), set()) for ang in boss_ang]
                 + [(void_loop(z), set())]) for z in zs]
    n2 = 4
    zs2 = dedupe_zs([FLOOR + (zp_bot - FLOOR) * k / n2 for k in range(n2 + 1)]
                    + [z_apex])
    loft(sink, holes_layers(zs2), IDENT)
    # channel band: merged loop, zp_bot..zp_apex (pinch at both ends). Fine steps near the
    # pinches + exact layers where the gap swallows an ellipse-polygon vertex.
    zsC = {zp + pr * math.sin(math.radians(phi))
           for phi in list(range(-90, -63, 3)) + list(range(-63, 46, 9))}
    nroof = max(4, int(math.ceil((zp_apex - zp45) / 0.2)))
    zsC.update(zp45 + (zp_apex - zp45) * k / nroof for k in range(1, nroof + 1))
    for k in range(1, E):
        hs = b_t * math.sin(2 * math.pi * k / E)
        if hs >= pr:
            break
        dz = math.sqrt(pr * pr - hs * hs)
        zsC.add(zp - dz)                                   # bottom (circle) side
        if zp + dz <= zp45:
            zsC.add(zp + dz)                               # upper circle side
        if hs < pr * C45:
            zsC.add(zp45 + (pr * C45 - hs) * T_ROOF)       # roof side
    zsC.add(z_kink)                                        # core void hits RV_MAX in this band
    loft(sink, [(z, [merged_loop(z), (void_loop(z), set())]) for z in dedupe_zs(zsC)], IDENT)
    # region 3: outer + holes + void, zp_apex..H
    n3 = 3
    zs3 = [zp_apex + (H - zp_apex) * k / n3 for k in range(n3 + 1)]
    loft(sink, holes_layers(zs3), IDENT)
    # bottom cap (solid: the void never reaches the bed)
    ring0 = outer_ring(0.0)
    fanb = [(ring0[0], ring0[j], ring0[j + 1]) for j in range(1, NO - 1)]
    emit_cap(sink, fanb, 0.0, False, IDENT)
    # top cap: 3 annular wedges between the outer ring and the open core void, each merged
    # with its mouth ellipse. Void verts share the outer ring's angles, so the wedge inner
    # arc reuses the void loop's verts index-for-index (parity with the void wall loft).
    per = NO // 3
    ring_h = outer_ring(H)
    void_h = void_loop(H)
    for s, ang in enumerate(boss_ang):
        k0 = (s * per - per // 2) % NO
        sector = [ring_h[(k0 + j) % NO] for j in range(per + 1)]
        if rv(H) > 1e-9:
            sector += [void_h[(NO - (k0 + j)) % NO] for j in range(per, -1, -1)]
        else:
            sector += [(0.0, 0.0)]
        hl = hole_loop(H, ang)
        emit_cap(sink, ring_merge(sector, hl, ell_center(H, ang)), H, True, IDENT)
    sockets = []
    for ang in boss_ang:
        mouth_c = ell_center(H, ang)
        axis = (-math.sin(tilt) * math.cos(ang), -math.sin(tilt) * math.sin(ang),
                -math.cos(tilt))                 # pointing down into the socket
        sockets.append({"type": "oblique", "mouth": (mouth_c[0], mouth_c[1], H),
                        "axis": axis, "ang": ang, "zp": zp, "R_out": R_OUT,
                        "rho_zp": rho(zp), "rho0": rho0, "floor": FLOOR, "a_r": a_r,
                        "H": H, "rv_top": rv(H), "wall_add": wall_add, "tilt": tilt})
    note = ("TETRA FALLBACK: true 109.5deg tetra needs 54.7deg bores > the 40deg walked-bore "
            "ceiling -> 3-leg tripod node, 30deg splay, single-wall pin channels; filler killed "
            "by the 30deg outer TAPER + a blind core cone void (O%.1f at the top face); what "
            "remains near the floor is bore convergence: blind ends %.1f mm off the axis"
            % (2 * rv(H), rho0 - a_r))
    return sink.tris, sockets, note


# ------------------------------------------------------------------ output
def write_stl(path, tris):
    hdr = b"crackle bamboo kit v2 - O7.0 flat bores, derived depth, open middles"
    assert len(hdr) <= 80
    with open(path, "wb") as fh:
        fh.write(hdr.ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            m = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            fh.write(struct.pack("<3f", nx / m, ny / m, nz / m))
            for v in (a, b, c):
                fh.write(struct.pack("<3f", *v))
            fh.write(struct.pack("<H", 0))


def read_stl(path):
    tris = []
    with open(path, "rb") as fh:
        fh.read(80)
        (n,) = struct.unpack("<I", fh.read(4))
        for _ in range(n):
            fh.read(12)
            vs = [struct.unpack("<3f", fh.read(12)) for _ in range(3)]
            fh.read(2)
            tris.append(vs)
    return tris


def parity(tris):
    from collections import Counter
    edges = Counter()
    for t in tris:
        vs = [tuple(round(c, 3) for c in v) for v in t]
        for i in range(3):
            a, b = vs[i], vs[(i + 1) % 3]
            edges[(a, b) if a <= b else (b, a)] += 1
    return [(e, c) for e, c in edges.items() if c != 2]


def ray_up_crossings(tris, x, y):
    n = 0
    for a, b, c in tris:
        d1 = (x - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (y - b[1])
        d2 = (x - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (y - c[1])
        d3 = (x - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (y - a[1])
        if (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0):
            n += 1
    return n


# -------------------------------------------------------------- self-verify
def mesh_volume(tris):
    """Signed volume by the divergence theorem (outward CCW winding -> positive)."""
    v = 0.0
    for a, b, c in tris:
        v += (a[0] * (b[1] * c[2] - b[2] * c[1])
              - a[1] * (b[0] * c[2] - b[2] * c[0])
              + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return abs(v) / 6.0


def verify(path, r_std, sockets, note, expect_bbox=120.0, part=None):
    """Measure the EMITTED file. Any FAIL -> quarantine rename + exit 1."""
    tris = read_stl(path)
    verts = set()
    for t in tris:
        for v in t:
            verts.add(v)
    verts = list(verts)
    zc, z45, zapex, H = geom(r_std)
    checks = []
    unpaired = parity(tris)
    checks.append(("watertight", len(unpaired) == 0, "%d unpaired edges" % len(unpaired)))
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]
    dx, dy, dz = max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)
    checks.append(("bbox <= %g" % expect_bbox, dx <= expect_bbox and dy <= expect_bbox,
                   "%.1f x %.1f x %.1f mm" % (dx, dy, dz)))
    if part in VOID_PARTS:
        # FEEDBACK 2026-08-02: "the joint space is wasted ... the middle part is pure filler".
        # A vertical ray through the hub centre must hit NOTHING (open through-void).
        ncross = ray_up_crossings(tris, 0.0, 0.0)
        checks.append(("middle OPEN (no filler)", ncross == 0,
                       "%d ray hits through the hub centre (0 = through-void)" % ncross))
        # void wall measured off the emitted mesh: interior verts vs the hub edge planes
        poly, _sides = hub_poly(part, W)
        nrms = _edge_normals(poly)
        apo = min(poly[i][0] * n[0] + poly[i][1] * n[1] for i, n in enumerate(nrms))
        inner = [max(v[0] * n[0] + v[1] * n[1] for n in nrms) for v in verts
                 if max(v[0] * n[0] + v[1] * n[1] for n in nrms) < apo - 0.5]
        if inner:
            vwall = apo - max(inner)
            checks.append(("void wall >= %.1f" % WALL_MIN, vwall >= WALL_MIN - 0.02,
                           "%.2f mm hub ring around the void (measured)" % vwall))
        else:
            checks.append(("void wall >= %.1f" % WALL_MIN, False, "no void verts found"))
    if part == "saddle":
        # clip mouth opening, measured at the inner lips of the emitted mesh
        lips = [v for v in verts if 1.9 < v[0] < 2.6 and 0.5 < abs(v[1]) < 4.0]
        gap = 2.0 * min(abs(v[1]) for v in lips)
        ratio = gap / ROD_D
        checks.append(("clip mouth 0.8-0.92x rod", 0.80 <= ratio <= 0.92,
                       "opening %.2f = %.3fx O%g rod (snaps on, does not fall off)"
                       % (gap, ratio, ROD_D)))
    for si, s in enumerate(sockets):
        tag = "S%d" % si
        if s["type"] == "planar":
            ox, oy = s["origin"]; nx, ny = s["n"]; tx, ty = s["t"]
            loc = [((v[0] - ox) * nx + (v[1] - oy) * ny,
                    (v[0] - ox) * tx + (v[1] - oy) * ty, v[2]) for v in verts]
            bore = [(u, v, z) for u, v, z in loc
                    if LB - DEPTH + 0.5 <= u <= LB - 0.5 and abs(v) <= r_std + 0.5
                    and abs(z - zc) <= 3.0]
            if not bore:
                checks.append((tag + " bore", False, "no bore verts found"))
                continue
            bins = {}
            for u, v, z in bore:
                d = math.hypot(v, z - zc)
                b = int(u)
                bins[b] = min(bins.get(b, 9e9), d)
            worst = max(abs(d - r_std) for d in bins.values())
            gmin = min(bins.values())
            checks.append((tag + " bore == standard O%.2f" % (2 * r_std),
                           worst <= 0.06 and gmin >= r_std - 0.06,
                           "min bin-radius %.3f..%.3f vs %.3f (%d bins, emitted mesh)"
                           % (gmin, max(bins.values()), r_std, len(bins))))
            void = [(u, v, z) for u, v, z in loc
                    if LB - DEPTH + 0.3 <= u <= LB - 0.5 and abs(v) <= r_std + 0.3
                    and 2.0 <= z <= H - 2.0]     # bore + adjoining pin-tube mouth rings
            wall_bot = min(z for _u, _v, z in void)
            wall_top = H - max(z for _u, _v, z in void)
            # lateral wall: this block's own outer width (|v|<8 excludes sibling bosses)
            wloc = max(abs(v) for u, v, z in loc
                       if -0.1 <= u <= LB + 0.1 and 4.0 < abs(v) < 8.0)
            wall_lat = wloc - max(abs(v) for _u, v, _z in void)
            wmin = min(wall_bot, wall_top, wall_lat)
            checks.append((tag + " wall >= %.1f" % WALL_MIN, wmin >= WALL_MIN - 0.02,
                           "bot %.2f top %.2f lat %.2f (measured)" % (wall_bot, wall_top, wall_lat)))
            deep = [(u, v, z) for u, v, z in loc
                    if 0.3 <= u <= LB - 0.5 and abs(v) <= r_std - 0.2 and 2.7 <= z <= H - 2.7]
            depth = LB - min(u for u, _v, _z in deep)
            checks.append((tag + " depth >= DERIVED %.2f" % DEPTH, depth >= DEPTH - 0.05,
                           "%.2f mm blind (depth is sqrt(2M/(w*sigma)), not a picked number)"
                           % depth))
            # pin: vertical ray through the pin axis must cross NOTHING (clear through-channel)
            pc = LB - PIN_FROM_MOUTH
            px = ox + pc * nx
            py = oy + pc * ny
            ncross = ray_up_crossings(tris, px, py)
            tube = [1 for u, v, z in loc
                    if math.hypot(u - pc, v) <= PINR + 0.15 and z < zc - r_std + 0.05]
            checks.append((tag + " pin O%.1f present+clear" % PIN_D,
                           ncross == 0 and len(tube) >= 8,
                           "%d ray hits (0=clear), %d tube verts" % (ncross, len(tube))))
        else:   # oblique (tripod)
            mx, my, mz = s["mouth"]
            ax, ay, az = s["axis"]
            tilt = math.radians(TRI_TILT)
            # normal-section frame: e1 = horizontal tangential, e2 = in-plane perp
            ang = s["ang"]
            e1 = (-math.sin(ang), math.cos(ang), 0.0)
            e2 = (ay * e1[2] - az * e1[1], az * e1[0] - ax * e1[2], ax * e1[1] - ay * e1[0])
            bore = []
            for v in verts:
                d = (v[0] - mx, v[1] - my, v[2] - mz)
                sax = d[0] * ax + d[1] * ay + d[2] * az
                if not (1.0 <= sax <= DEPTH - 0.5):
                    continue
                c1 = d[0] * e1[0] + d[1] * e1[1] + d[2] * e1[2]
                c2 = d[0] * e2[0] + d[1] * e2[1] + d[2] * e2[2]
                rr = math.hypot(c1, c2)
                if rr <= r_std + 0.6:
                    bore.append((sax, rr, v))
            if not bore:
                checks.append((tag + " bore", False, "no bore verts"))
                continue
            bins = {}
            for sax, rr, _v in bore:
                b = int(sax)
                bins[b] = min(bins.get(b, 9e9), rr)
            worst = max(abs(d - r_std) for d in bins.values())
            checks.append((tag + " bore == standard O%.2f (normal section)" % (2 * r_std),
                           worst <= 0.08,
                           "min bin-radius %.3f..%.3f vs %.3f (%d bins)"
                           % (min(bins.values()), max(bins.values()), r_std, len(bins))))
            depth = max(sax for sax, _rr, _v in bore) + 1.0
            checks.append((tag + " depth >= DERIVED %.2f" % DEPTH, depth >= DEPTH - 0.6,
                           "%.1f mm along the 30deg axis" % depth))
            floor_z = min(v[2] for _s, _r2, v in bore)

            def apo_built(z):
                # the tapered outer wall apothem the part was built with
                return (s["rho0"] + (max(z, s["floor"]) - s["floor"]) * math.tan(s["tilt"])
                        + s["a_r"] + s["wall_add"])
            # wall measured from verts ON the bore surface only (rr ~ r): the channel-notch
            # wall interpolants live INSIDE the wall thickness and are not bore surface
            wall_out = min(apo_built(v[2]) - math.hypot(v[0], v[1])
                           for _s2, rr2, v in bore if rr2 <= r_std + 0.15)
            wmin = min(floor_z, wall_out)
            checks.append((tag + " wall >= %.1f" % WALL_MIN, wmin >= WALL_MIN - 0.05,
                           "floor %.2f outer %.2f (measured vs tapered wall)"
                           % (floor_z, wall_out)))
            if si == 0:
                # THE FILLER GATE: the core cone void must be open from the top face down --
                # a probe dropped at r=2 into the mouth must cross NO surface (solid middle
                # would put the top cap in its way; --sabotage filler proves this fires)
                p0 = (2.0, 0.0, s["H"] + 5.0)
                p1 = (2.0, 0.0, s["H"] * 0.55)
                hits = seg_crossings(tris, p0, p1)
                checks.append(("core void OPEN (no filler)", hits == 0,
                               "%d hits on a probe into the core mouth (0 = open), "
                               "void O%.1f at the top face" % (hits, 2 * s["rv_top"])))
            # pin channel: horizontal ray from outside toward the bore centre at zp
            zp = s["zp"]
            ca, sa = math.cos(ang), math.sin(ang)
            p0 = ((s["R_out"] + 2.0) * ca, (s["R_out"] + 2.0) * sa, zp)
            p1 = (s["rho_zp"] * ca, s["rho_zp"] * sa, zp)
            hits = seg_crossings(tris, p0, p1)
            checks.append((tag + " pin O%.1f channel clear" % PIN_D, hits == 0,
                           "%d hits outer->bore-axis at z=%.1f (0=clear, single-wall)" % (hits, zp)))
    ok = all(c[1] for c in checks)
    ntris = len(tris)
    vol = mesh_volume(tris)
    print("%s: %d tris, %.0f mm3 = %.1f g PLA (measured)" % (path, ntris, vol,
                                                             vol * PLA_G_PER_MM3))
    if note:
        print("  NOTE %s" % note)
    for name, good, msg in checks:
        print("  %s %-34s %s" % ("PASS" if good else "FAIL", name, msg))
    if not ok:
        failed = path + ".FAILED"
        os.replace(path, failed)
        print("  SELF-VERIFY: FAIL -> quarantined %s" % failed)
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS")


def seg_crossings(tris, p0, p1):
    d = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    n = 0
    for a, b, c in tris:
        e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        px = d[1] * e2[2] - d[2] * e2[1]
        py = d[2] * e2[0] - d[0] * e2[2]
        pz = d[0] * e2[1] - d[1] * e2[0]
        det = e1[0] * px + e1[1] * py + e1[2] * pz
        if abs(det) < 1e-12:
            continue
        inv = 1.0 / det
        tv = (p0[0] - a[0], p0[1] - a[1], p0[2] - a[2])
        u = (tv[0] * px + tv[1] * py + tv[2] * pz) * inv
        if u < 0 or u > 1:
            continue
        qx = tv[1] * e1[2] - tv[2] * e1[1]
        qy = tv[2] * e1[0] - tv[0] * e1[2]
        qz = tv[0] * e1[1] - tv[1] * e1[0]
        v = (d[0] * qx + d[1] * qy + d[2] * qz) * inv
        if v < 0 or u + v > 1:
            continue
        t = (e2[0] * qx + e2[1] * qy + e2[2] * qz) * inv
        if 0.0 < t < 1.0:
            n += 1
    return n


# --------------------------------------------------------------------- main
BUILDERS = {
    "sleeve": lambda r, s: part_planar("sleeve", r, s),
    "L90": lambda r, s: part_planar("L90", r, s),
    "T": lambda r, s: part_planar("T", r, s),
    "X": lambda r, s: part_planar("X", r, s),
    "Y120": lambda r, s: part_planar("Y120", r, s),
    "hub6": lambda r, s: part_planar("hub6", r, s),
    "angle15": lambda r, s: part_planar("angle15", r, s),
    "foot": part_foot,
    "saddle": part_saddle,
    "tetra": part_tetra,
}


def build_one(name, r, out_dir, sabotage=None):
    tris, sockets, note = BUILDERS[name](r, sabotage)
    out = os.path.join(out_dir, "%s.stl" % name.lower())
    write_stl(out, tris)
    verify(out, r, sockets, note, part=name)
    return out


def family_viz(out_dir, files):
    """Lay every kit part out in a grid in one viz STL (render aid, not a print file)."""
    cols = 4
    pitch = 92.0             # parts grew with the derived socket depth (widest ~74 mm)
    tris = []
    for i, f in enumerate(files):
        part = read_stl(f)
        xs = [v[0] for t in part for v in t]; ys = [v[1] for t in part for v in t]
        cx = (max(xs) + min(xs)) / 2.0
        cy = (max(ys) + min(ys)) / 2.0
        gx = (i % cols) * pitch - (cols - 1) * pitch / 2.0
        gy = (i // cols) * pitch - pitch
        for a, b, c in part:
            tris.append(tuple((v[0] - cx + gx, v[1] - cy + gy, v[2]) for v in (a, b, c)))
    out = os.path.join(out_dir, "family_viz.stl")
    write_stl(out, tris)
    print("%s: %d tris (grid render aid)" % (out, len(tris)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", required=True, choices=PARTS + ("all",))
    ap.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--sabotage", choices=("bore", "wall", "filler"), default=None,
                    help="deliberately wrong build to PROVE the function gates fire")
    a = ap.parse_args()
    r = BORE / 2.0
    _zc, _z45, _zapex, H = geom(r)
    M = RC.DESIGN_LOAD_N * RC.ROD_LEN
    print("SOCKET STANDARD v2: bore O%.2f FLAT (rods MEASURE %g-%g; TPU shims fill the gap), "
          "wall >= %g, pin O%g at %g from mouth, H=%.1f, port W=%g"
          % (BORE, RC.ROD_MIN, RC.ROD_MAX, WALL_MIN, PIN_D, PIN_FROM_MOUTH, H, W))
    print("DEPTH %.2f mm DERIVED: M = %g N x %g mm = %g N.mm; sigma = 2M/(w d^2); "
          "d = sqrt(2*%g/(%g*%g)) at %g MPa = crush/%g  (v1's 12 mm sat AT the %g MPa crush)"
          % (DEPTH, RC.DESIGN_LOAD_N, RC.ROD_LEN, M, M, RC.ROD_NOM,
             RC.PLA_CRUSH_MPA / RC.SAFETY, RC.PLA_CRUSH_MPA / RC.SAFETY, RC.SAFETY,
             RC.PLA_CRUSH_MPA))
    names = list(PARTS) if a.part == "all" else [a.part]
    files = [build_one(n, r, a.out_dir, a.sabotage) for n in names]
    if a.part == "all" and not a.sabotage:
        family_viz(a.out_dir, files)


if __name__ == "__main__":
    main()
