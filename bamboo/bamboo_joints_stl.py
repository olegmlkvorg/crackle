#!/usr/bin/env python3
"""bamboo_joints_stl.py -- THE LEGO-FOR-BENT-BAMBOO JOINT KIT (Oleg: "all kind of bent bamboo
joint to experiment with, lego style"). One parametric generator, one part per --part flag,
--part all emits the whole kit.

THE LEGO PRINCIPLE: ONE socket standard everywhere + quantized geometry, so any joint combines
with any other.

SOCKET STANDARD (every part accepts the same 1/4in (O6.35) bamboo rod the same way):
  bore   SNUG O7.05 default (--fit slide -> O7.65) -- the MEASURED bamboo press constant
         (+0.70 on the rod, stave-shelf coupon 2026-07-27). Fit flagged UNPROVEN on this new
         geometry until a coupon prints: the constant was calibrated on walked vertical bores,
         these are horizontal teardrop bores.
  depth  12.0 mm blind
  wall   >= 2.4 mm of material around every bore (measured off the emitted mesh)
  pin    O3.0 vertical cross-pin hole through every socket at 6.0 from the mouth (the stave
         retainer trick: bamboo skewer locks the rod)
  roof   horizontal bores carry a 46deg teardrop roof (facet nz = -0.695 > the -0.707 gate;
         a round bore ceiling is a spanning overhang and fails qa_stl PRINTABLE)

QUANTIZED: port width W=13 everywhere, one part height H (13.6 at snug), one boss length 13.4,
angles from {45, 60, 90, 120} (angle15 = the 165deg bent-rod-end kink, the stave ~14deg number
rounded to the 15 grid).

KIT: sleeve L90 T X Y120 hub6 tetra saddle angle15 foot
  tetra NOTE: a true tetrahedral node needs bores tilted 54.7deg from vertical -- past the ~40deg
  walked-bore ceiling stave_hub proved. Per spec it therefore falls back to a 3-LEG TRIPOD NODE:
  3 sockets splayed 30deg from vertical as walked oblique bores (1/cos30 pre-stretch, the
  stave_hub technique), pin = horizontal O3 teardrop channel through the outer wall into each
  bore (single-wall pin: a through-pin would need an unwalkable 60deg hole; said honestly here).
  saddle NOTE: grips a BOWED rod mid-arc. R>=1000 sagitta over the 13.6mm clip is 0.02mm --
  locally straight, so the clip bore is a straight O7.05 channel with a 5.70 mouth (0.90 x rod).

CONSTRUCTION: watertight-by-construction z-loft. Each part = hub prism + socket blocks glued on
exact shared port rectangles, all lofted on ONE shared z-layer list (no T-vertices). Where the
vertical pin tube meets the horizontal bore void the cross-section topology changes; those
transitions happen at PINCH planes (bore width exactly 0) where both structures coincide
vertex-for-vertex, so edge parity survives. Every part is checked by measuring the EMITTED STL
(re-read from disk), and a failing part is quarantine-renamed .FAILED.

Usage:
  python3 bamboo_joints_stl.py --part all [--fit snug|slide] [--out-dir DIR]
  python3 bamboo_joints_stl.py --part hub6
  python3 bamboo_joints_stl.py --part sleeve --sabotage bore --out-dir /tmp/x   # prove gates fire
"""
import argparse
import math
import os
import struct
import sys

# ---------------------------------------------------------------- constants
ROD_D = 6.35                 # 1/4in bamboo rod
FIT = {"snug": 7.05, "slide": 7.65}   # measured bamboo constants (stave shelf)
DEPTH = 12.0                 # socket depth, blind
WALL_MIN = 2.4               # min wall around every bore
BOT_WALL = 2.5               # designed wall under the bore (>= WALL_MIN)
W = 13.0                     # port width = hub side length, everywhere
LB = 13.4                    # boss (block) length: DEPTH + 1.4 blind wall + hub behind it
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


def block_loop(z, r, wport):
    """Region-B cross-section loop of a socket block, local coords u in [0,LB] (0=glue,
    LB=mouth), v lateral. Single CCW loop, 4+2+2+2*(POCKET_M+1)+2 = 26 verts, closing (glue)
    segment skipped."""
    h = bore_w(z, r) / 2.0
    hw = wport / 2.0
    ub = LB - DEPTH
    pc = LB - PIN_FROM_MOUTH
    pts = [(0.0, -hw), (LB, -hw), (LB, -h)]
    pts += pocket_chain(pc, -1, h)
    pts += [(ub, -h), (ub, h)]
    pts += pocket_chain(pc, +1, h)
    pts += [(LB, h), (LB, hw), (0.0, hw)]
    return (pts, {len(pts) - 1})


def block_outer5(wport):
    hw = wport / 2.0
    return ([(0.0, -hw), (LB, -hw), (LB, 0.0), (LB, hw), (0.0, hw)], {4})


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
    return sorted(zs)


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
    return sorted(set(zs))


def emit_hub(sink, poly, port_sides, r, z_extra=(), caps=(True, True), zs=None):
    """Convex hub prism on the shared z list; port sides skipped. poly CCW."""
    _zc, _z45, _zapex, H = geom(r)
    if zs is None:
        zs = block_z_list(r, z_extra)
    loop = (poly, set(port_sides))
    loft(sink, [(z, [loop]) for z in zs], IDENT)
    tris = cap_from_indices(poly, earclip(poly))
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


def part_planar(name, r, sabotage=None):
    """All hub+blocks planar parts. Returns (tris, sockets, note)."""
    wport = 10.0 if sabotage == "wall" else W
    rb = r - 0.25 if sabotage == "bore" else r
    sink = Sink()
    if name in ("sleeve", "L90", "T", "X"):
        h = wport / 2.0
        poly = [(h, -h), (h, h), (-h, h), (-h, -h)]  # CCW: sides 0:+x 1:+y 2:-x 3:-y
        sides = {"sleeve": [0, 2], "L90": [0, 1], "T": [0, 2, 1], "X": [0, 1, 2, 3]}[name]
    elif name in ("Y120", "hub6"):
        poly = [(wport * math.cos(math.radians(60 * k)),
                 wport * math.sin(math.radians(60 * k))) for k in range(6)]
        sides = [0, 2, 4] if name == "Y120" else [0, 1, 2, 3, 4, 5]
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
    ports = hub_ports(poly, sides, rb, wport)
    emit_hub(sink, poly, sides, rb)
    for tf, _m in ports:
        emit_block(sink, tf, rb, wport)
    sockets = [m for _tf, m in ports]
    return sink.tris, sockets, ""


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
    rc = FIT["snug"] / 2.0                      # clip cradle = the same standard bore
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
    -> 3-leg tripod node, sockets 30deg from vertical, walked oblique bores (stave technique)."""
    rb = r - 0.25 if sabotage == "bore" else r
    sink = Sink()
    tilt = math.radians(TRI_TILT)
    zc_, z45_, zapex_, H = geom(rb)             # reuse H so the kit is one height
    FLOOR = H - DEPTH * math.cos(tilt)          # bore vertical extent below the top face
    a_r = rb / math.cos(tilt)                   # radial semi-axis (pre-stretch)
    b_t = rb                                    # tangential semi-axis
    RHO_M = 12.5                                # mouth centre radius (top face)
    walk = DEPTH * math.sin(tilt)
    rho0 = RHO_M - walk
    R_AP = RHO_M + a_r + (10.0 - 7.05) / 2.0 if sabotage == "wall" else RHO_M + a_r + 2.4
    NO = 36
    R_OUT = R_AP / math.cos(math.pi / NO)
    outer = [(R_OUT * math.cos(2 * math.pi * k / NO), R_OUT * math.sin(2 * math.pi * k / NO))
             for k in range(NO)]
    boss_ang = [0.0, 2 * math.pi / 3, 4 * math.pi / 3]
    E = 24
    zp = H - PIN_FROM_MOUTH * math.cos(tilt)    # pin channel centre height (mid-socket-ish)
    pr = PIN_D / 2.0
    zp45 = zp + pr * S45
    zp_apex = zp + pr * APEXF
    zp_bot = zp - pr

    def rho(z):
        return rho0 + (z - FLOOR) * math.tan(tilt)

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
        pts = []
        for k in range(NO):
            ang_k = 2 * math.pi * k / NO
            site = None
            for ang in boss_ang:
                if abs(((ang_k - ang + math.pi) % (2 * math.pi)) - math.pi) < 1e-9:
                    site = ang
            if site is None:
                pts.append(outer[k])
                continue
            ang = site
            va = outer[k]
            ca, sa = math.cos(ang), math.sin(ang)

            def on_edge(sgn):
                # point with tangential coord sgn*hc on the outer edge flanking v_k
                nb = outer[(k + (1 if sgn > 0 else -1)) % NO]
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

    # region 1: solid below floor
    zs1 = [0.0, FLOOR]
    loft(sink, [(z, [(outer, set())]) for z in zs1], IDENT)
    # bore floor discs (blind floors), facing up
    for ang in boss_ang:
        hl = hole_loop(FLOOR, ang)
        c = ell_center(FLOOR, ang)
        fan = [(c, hl[(j + 1) % E], hl[j]) for j in range(E)]   # hl is CW -> reversed for +z
        emit_cap(sink, fan, FLOOR, True, IDENT)
    # region 2: outer + 3 walking holes, FLOOR..zp_bot
    def holes_layers(zs):
        return [(z, [(outer, set())] + [(hole_loop(z, ang), set()) for ang in boss_ang])
                for z in zs]
    n2 = 4
    zs2 = [FLOOR + (zp_bot - FLOOR) * k / n2 for k in range(n2 + 1)]
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
    loft(sink, [(z, [merged_loop(z)]) for z in sorted(zsC)], IDENT)
    # region 3: outer + holes, zp_apex..H
    n3 = 3
    zs3 = [zp_apex + (H - zp_apex) * k / n3 for k in range(n3 + 1)]
    loft(sink, holes_layers(zs3), IDENT)
    # bottom cap
    fanb = [(outer[0], outer[j], outer[j + 1]) for j in range(1, NO - 1)]
    emit_cap(sink, fanb, 0.0, False, IDENT)
    # top cap: 3 sectors, each a ring between pie slice and its mouth ellipse
    per = NO // 3
    for s, ang in enumerate(boss_ang):
        k0 = (s * per - per // 2) % NO
        sector = [(0.0, 0.0)] + [outer[(k0 + j) % NO] for j in range(per + 1)]
        hl = hole_loop(H, ang)
        emit_cap(sink, ring_merge(sector, hl, ell_center(H, ang)), H, True, IDENT)
    sockets = []
    for ang in boss_ang:
        mouth_c = ell_center(H, ang)
        axis = (-math.sin(tilt) * math.cos(ang), -math.sin(tilt) * math.sin(ang),
                -math.cos(tilt))                 # pointing down into the socket
        sockets.append({"type": "oblique", "mouth": (mouth_c[0], mouth_c[1], H),
                        "axis": axis, "ang": ang, "zp": zp, "R_out": R_OUT})
    note = ("TETRA FALLBACK: true 109.5deg tetra needs 54.7deg bores > the 40deg walked-bore "
            "ceiling -> 3-leg tripod node, 30deg splay, single-wall pin channels")
    return sink.tris, sockets, note


# ------------------------------------------------------------------ output
def write_stl(path, tris):
    hdr = b"crackle bamboo joint kit - LEGO for bent bamboo, snug O7.05 sockets"
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
def verify(path, r_std, sockets, note, expect_bbox=60.0):
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
            checks.append((tag + " depth >= %g" % DEPTH, depth >= DEPTH - 0.05,
                           "%.2f mm blind" % depth))
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
            checks.append((tag + " depth >= %g" % DEPTH, depth >= DEPTH - 0.6,
                           "%.1f mm along the 30deg axis" % depth))
            floor_z = min(v[2] for _s, _r2, v in bore)
            wall_out = min(s["R_out"] * math.cos(math.pi / 36) - math.hypot(v[0], v[1])
                           for _s, _r2, v in bore)
            wmin = min(floor_z, wall_out)
            checks.append((tag + " wall >= %.1f" % WALL_MIN, wmin >= WALL_MIN - 0.05,
                           "floor %.2f outer %.2f (measured)" % (floor_z, wall_out)))
            # pin channel: horizontal ray from outside toward the bore centre at zp
            zp = s["zp"]
            ca, sa = math.cos(ang), math.sin(ang)
            p0 = ((s["R_out"] + 2.0) * ca, (s["R_out"] + 2.0) * sa, zp)
            walk_r = (12.5 - DEPTH * math.sin(tilt)) + (zp - (geom(r_std)[3] - DEPTH * math.cos(tilt))) * math.tan(tilt)
            p1 = (walk_r * ca, walk_r * sa, zp)
            hits = seg_crossings(tris, p0, p1)
            checks.append((tag + " pin O%.1f channel clear" % PIN_D, hits == 0,
                           "%d hits outer->bore-axis at z=%.1f (0=clear, single-wall)" % (hits, zp)))
    ok = all(c[1] for c in checks)
    ntris = len(tris)
    print("%s: %d tris" % (path, ntris))
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
    verify(out, r, sockets, note)
    return out


def family_viz(out_dir, files):
    """Lay every kit part out in a grid in one viz STL (render aid, not a print file)."""
    cols = 4
    pitch = 62.0
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
    ap.add_argument("--fit", choices=("snug", "slide"), default="snug")
    ap.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--sabotage", choices=("bore", "wall"), default=None,
                    help="deliberately wrong build to PROVE the function gates fire")
    a = ap.parse_args()
    r = FIT[a.fit] / 2.0
    _zc, _z45, _zapex, H = geom(r)
    print("SOCKET STANDARD: bore O%.2f %s x %g deep, wall >= %g, pin O%g at %g from mouth, "
          "H=%.1f, port W=%g  (fit constant from stave coupon; UNPROVEN on this horizontal "
          "teardrop geometry until a coupon prints)"
          % (FIT[a.fit], a.fit.upper(), DEPTH, WALL_MIN, PIN_D, PIN_FROM_MOUTH, H, W))
    names = list(PARTS) if a.part == "all" else [a.part]
    files = [build_one(n, r, a.out_dir, a.sabotage) for n in names]
    if a.part == "all" and not a.sabotage:
        family_viz(a.out_dir, files)


if __name__ == "__main__":
    main()
