#!/usr/bin/env python3
"""BRACE STL -- the horizontal tie that turns separate towers into one frame.

WHY IT EXISTS. base_ballast_stl.py measured the other half of the problem: a bare tower is
hopeless against a sideways nudge (a 1 N push needs a half-metre plate at ANY height, because
mass grows with height so H/M is constant), and ballast is what buys it back. The brace is the
second half. A horizontal tie lets a nudged tower BORROW every other tower's restoring moment:

    unbraced  tower A tips when  F*H > M*g*b
    braced    the tie pushes B over too, so B's full M*g*b is added before anything moves:
              F*H > M*g*b + (n-1)*M*g*b   =>   n TIED TOWERS SURVIVE n x THE NUDGE OF ONE.

That result is independent of how high the tie sits (the tie force scales as 1/h, its lever as h)
and independent of the grid pitch. It assumes SEPARATE bases. On one shared base_ballast tray the
feet are already tied and the brace does a different job: it stops the towers hinging apart at
their snap couplings. That second job is NOT quantified here (see "unproven").

WHERE IT GRIPS, AND WHY THERE IS NO CLIP. The tower is stacked chutes; the only smooth surfaces
are the coupling zones. This part is a flat plate with holes, threaded onto a segment's SPIGOT
from the tip before that segment is dropped into the socket below. It then falls back down the
spigot and lands on the socket rim. No clip, no fastener, and a hole surrounds the tower so it
ties in push AND pull.

REST-ON-RIM IS THE ONLY OPTION, not a preference. Anything that can be threaded over the spigot
base can also pass everything above it, because the chute cones INWARD above the spigot (Ø56 base
down to the Ø44 pocket at 45 deg, stock). So no plate threaded from below can ever be caught from
above; the socket rim underneath is the only stop. A conical bore that seats on the chute's entry
cone would need its narrowest section BOTH wider than the spigot base (to thread) and narrower
(to catch): impossible. Proved before it was drawn, so the bore is a plain cylinder.

THE WINDOW, MEASURED OFF THE REAL PROFILES INCLUDING THE HALF-BEAD. A vase wall is laid CENTRED
on the surface path, so a printed FACE sits LINE_W/2 outside the path.

    spigot outer FACE = max(spigot_r) + LINE_W/2      the widest thing the hole must pass
    mouth  outer FACE = SOCKET_MOUTH_R + LINE_W/2     the rim the hole must land on
    window = mouth_face_d - spigot_face_d = 2*(LINE_W + ENTRY_CLEAR) = 2.90 mm diametral

The window is exactly one wall plus one entry clearance per side, because that is precisely how
much bigger BOND v2.1 makes the mouth than the spigot base it swallows. So it is 2.90 mm for the
STOCK coupling and 2.90 mm for the SLIM one: DIAMETER-INDEPENDENT. It is NOT too narrow. The hole
is placed FIT_CLR above the spigot face, which leaves 1.00 mm of radial ledge on the rim: the
plate covers the whole 0.95 mm rim bead and hangs 0.05 mm past its inner face.

SHAPE: a chain of overlapping CLOSED bodies, exactly like marble_gauge_stl.py -- one annular ring
solid per tower, joined by rectangular bar solids. Not one surface: a plate with holes is not a
surface of revolution and a triangulated slab-with-holes is not worth writing. Every body is
individually watertight, which is what the slicer and qa_stl both want. It is NOT a vase part.
Prints FLAT on the bed, no support: every face points up, sideways, or is ON the bed.

A COUNTERBORE WAS REJECTED BY THE GATE, correctly. A stepped bore (wide skirt below, narrow bore
above) would halve the play, but its step is a downward-facing flat annulus in mid air, which
qa_stl PRINTABLE flags as a spanning overhang. The plain bore keeps the play and prints.

Usage: python3 brace_stl.py [--towers 2] [--segments 2] [--slim] [--nudge 1.0] [--ballast 500]
                            [--joint N] [--fit-clr F] [--thickness T] [--bar-bite X]
"""
import argparse, math, os, struct

import marble_common as mc
import base_ballast_stl as bb

# ---- measured inputs, restated with provenance -------------------------------------------
CHUTE_G  = 46.9      # g per chute segment, MEASURED off the emitted mesh (base_ballast_stl.py)
CHUTE_H  = 235.3     # mm per chute segment, MEASURED off the emitted mesh
POCKET_D = 40.8      # slim gutter pocket Ø, MEASURED by the physics sim (Ø16 marble rides r=10.2)
STOCK_POCKET_D = 44.0  # stock chute --pocket default; the emitted wave comes in a shade under it

# ---- assumptions, labelled ---------------------------------------------------------------
SPIGOT_DRIFT = 0.20  # ASSUMED radial: vase-wall out-of-roundness on a printed spigot. Nobody has
                     # put callipers on one. Print a brace and a chute, then measure this.
RING_GAP     = 1.0   # ASSUMED mm of air between neighbouring rings, so their two surfaces never
                     # meet in a razor-thin lens the slicer has to reason about
BORE_KEEPOUT = 0.5   # ASSUMED mm: how far the tie bar's end plane stays clear of the bore wall
BITE         = 0.8   # ASSUMED mm, about one printed bead: minimum overlap of bar into ring wall
E_PLA        = 2000.0  # MPa, ASSUMED for printed PLA. Bulk PLA is ~3500; printed solid is less.
PLA_RHO      = 1.24e-3  # g/mm3
G            = 9.81
BED          = 340.0
MEAS_EPS     = 1e-3  # mm of slack on read-back comparisons. A binary STL stores float32, so a
                     # length measured off the FILE at these coordinates carries ~1e-5 mm of
                     # quantisation. 1e-3 is three orders below anything a printer can do, so it
                     # cannot hide a real error; it only stops the gate tripping on its own noise.


# ---------------------------------------------------------------- mesh bodies (all closed)
def ring_solid(cx, cy, r_in, r_out, z0, z1, n):
    """Closed annular prism. Winding copied from marble_gauge_stl.py (passes the gate).
    Bore vertices are CIRCUMSCRIBED (r/cos(pi/n)) so the polygon FLATS sit at r_in: an inscribed
    polygon would make the real hole 0.016 mm tight, in the one direction that matters."""
    rv = r_in / math.cos(math.pi / n)
    out = [(cx + r_out*math.cos(2*math.pi*k/n), cy + r_out*math.sin(2*math.pi*k/n)) for k in range(n)]
    inn = [(cx + rv*math.cos(2*math.pi*k/n), cy + rv*math.sin(2*math.pi*k/n)) for k in range(n)]
    tris = []
    for k in range(n):
        j = (k + 1) % n
        O0, O1 = (*out[k], z0), (*out[j], z0)
        O0h, O1h = (*out[k], z1), (*out[j], z1)
        I0, I1 = (*inn[k], z0), (*inn[j], z0)
        I0h, I1h = (*inn[k], z1), (*inn[j], z1)
        tris.append((O0, O1, O1h)); tris.append((O0, O1h, O0h))      # outer wall
        tris.append((I0, I1h, I1)); tris.append((I0, I0h, I1h))      # bore wall
        tris.append((O0, I0, I1)); tris.append((O0, I1, O1))         # bottom annulus (on the bed)
        tris.append((O0h, O1h, I1h)); tris.append((O0h, I1h, I0h))   # top annulus
    return tris


def box_solid(x0, x1, y0, y1, z0, z1):
    """Closed rectangular prism, outward winding on all six faces."""
    def quad(a, b, c, d):
        return [(a, b, c), (a, c, d)]
    t = []
    t += quad((x0,y0,z0), (x0,y1,z0), (x1,y1,z0), (x1,y0,z0))        # bottom, -z (on the bed)
    t += quad((x0,y0,z1), (x1,y0,z1), (x1,y1,z1), (x0,y1,z1))        # top, +z
    t += quad((x0,y0,z0), (x1,y0,z0), (x1,y0,z1), (x0,y0,z1))        # -y
    t += quad((x0,y1,z0), (x0,y1,z1), (x1,y1,z1), (x1,y1,z0))        # +y
    t += quad((x0,y0,z0), (x0,y0,z1), (x0,y1,z1), (x0,y1,z0))        # -x
    t += quad((x1,y0,z0), (x1,y1,z0), (x1,y1,z1), (x1,y0,z1))        # +x
    return t


def _normal(a, b, c):
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    m = math.sqrt(nx*nx + ny*ny + nz*nz)
    return (0.0, 0.0, 0.0) if m < 1e-12 else (nx/m, ny/m, nz/m)


def write_stl(path, tris):
    with open(path, "wb") as f:
        f.write(b"crackle brace - horizontal tie for a multi-tower marble structure".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<3f", *_normal(*t)))
            for v in t:
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))


# ---------------------------------------------------------------- measuring the emitted file
def read_stl(path):
    """Re-read the FILE, a different route than the writer: bytes back to triangles."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        tris = []
        for _ in range(n):
            f.read(12)
            tris.append(tuple(struct.unpack("<3f", f.read(12)) for _ in range(3)))
            f.read(2)
    return size, tris


def components(tris):
    """Union-find on rounded verts: one id per triangle. Overlapping closed bodies share no
    vertices, so each body comes out as its own component (same split qa_stl uses)."""
    parent = {}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    keys = []
    for t in tris:
        ks = [tuple(round(c, 3) for c in v) for v in t]
        for k in ks:
            parent.setdefault(k, k)
        union(ks[0], ks[1]); union(ks[1], ks[2])
        keys.append(ks[0])
    remap = {}
    return [remap.setdefault(find(k), len(remap)) for k in keys]


def inside(p, tris):
    """Point in a closed body: signed winding of a +z ray. Same construction qa_stl's burial
    test uses. Nonzero winding = the point is in material."""
    px, py, pz = p
    w = 0
    for u0, u1, u2 in tris:
        ax, ay, az = u0
        e1 = (u1[0]-ax, u1[1]-ay, u1[2]-az)
        e2 = (u2[0]-ax, u2[1]-ay, u2[2]-az)
        nzc = e1[0]*e2[1] - e1[1]*e2[0]
        if abs(nzc) < 1e-12:
            continue
        if px < min(u0[0], u1[0], u2[0]) or px > max(u0[0], u1[0], u2[0]):
            continue
        if py < min(u0[1], u1[1], u2[1]) or py > max(u0[1], u1[1], u2[1]):
            continue
        d1 = (px-u1[0])*(u0[1]-u1[1]) - (u0[0]-u1[0])*(py-u1[1])
        d2 = (px-u2[0])*(u1[1]-u2[1]) - (u1[0]-u2[0])*(py-u2[1])
        d3 = (px-u0[0])*(u2[1]-u0[1]) - (u2[0]-u0[0])*(py-u0[1])
        if not ((d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0)):
            continue
        nx = e1[1]*e2[2] - e1[2]*e2[1]
        ny = e1[2]*e2[0] - e1[0]*e2[2]
        zc = az - (nx*(px-ax) + ny*(py-ay)) / nzc
        if zc > pz:
            w += 1 if nzc > 0 else -1
    return w != 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--towers", type=int, default=2, choices=(2, 3),
                    help="towers tied, collinear on the kit structure grid (matches base_ballast)")
    ap.add_argument("--segments", type=int, default=2, help="chute segments per tower")
    ap.add_argument("--slim", action="store_true", help="SLIM coupling instead of stock O52/56")
    ap.add_argument("--nudge", type=float, default=1.0, help="sideways nudge at the top, N")
    ap.add_argument("--ballast", type=float, default=500.0, help="sand in each base tray, g")
    ap.add_argument("--joint", type=int, default=None,
                    help="which coupling joint carries the brace (1 = first joint above the base). "
                         "Default: the top one, which needs the least tie force.")
    ap.add_argument("--fit-clr", type=float, default=None,
                    help="radial clearance of the bore over the spigot face. Default DERIVED. Turn "
                         "it up to watch the window gate refuse the design.")
    ap.add_argument("--thickness", type=float, default=None,
                    help="plate thickness mm. Default DERIVED from the tie load; pin it thin and "
                         "the flex gate fails.")
    ap.add_argument("--bar-bite", type=float, default=None,
                    help="half-length of the tie bar in x. Default DERIVED to stop BORE_KEEPOUT "
                         "short of the bore; make it big and the bar plugs the holes.")
    ap.add_argument("--points", type=int, default=96, help="polygon points per ring")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    assert CHUTE_G == bb.CHUTE_G and CHUTE_H == bb.CHUTE_H, (
        f"chute mass/height disagree with base_ballast_stl.py ({bb.CHUTE_G} g, {bb.CHUTE_H} mm): "
        f"one of the two files is running on a stale measurement")

    coupling = "stock"
    pocket_d = STOCK_POCKET_D
    if a.slim:
        mc.configure_bond(mc.min_bond_tip_d(POCKET_D))
        coupling, pocket_d = "slim", POCKET_D

    # ---- the window, measured off the real BOND profiles, half-bead included ----
    half_bead = mc.LINE_W / 2.0
    spigot_face_d = 2 * (max(mc.spigot_r(z) for z, _ in mc.spigot_profile()) + half_bead)
    mouth_face_d = 2 * (mc.SOCKET_MOUTH_R + half_bead)
    pocket_face_d = pocket_d + mc.LINE_W
    window = mouth_face_d - spigot_face_d

    # ---- the bore. Placed AGAINST the spigot, not centred in the window: every millimetre not
    # spent on threading clearance becomes ledge on the rim, and ledge is what stops the plate
    # walking off its seat inside its own play. ----
    fit_clr = a.fit_clr if a.fit_clr is not None else mc.HOLE_SHRINK + SPIGOT_DRIFT
    bore_printed_r = spigot_face_d / 2 + fit_clr
    ledge = mouth_face_d / 2 - bore_printed_r
    bore_model_r = bore_printed_r + mc.HOLE_SHRINK / 2      # model oversize; the hole prints small

    # ---- ring wall: the most the structure grid allows, less a gap so neighbours stay apart ----
    wall = mc.GRID_PITCH / 2 - bore_model_r - RING_GAP / 2
    ring_out_r = bore_model_r + wall

    # ---- tie bar: as long as the bores allow, as wide as the ring wall it can still reach ----
    x_b = a.bar_bite if a.bar_bite is not None else mc.GRID_PITCH / 2 - bore_model_r - BORE_KEEPOUT
    # The bar's worst-buried point is the corner (reach, +-w) and the honest depth of burial is
    # its RADIAL distance inside the ring's outer surface, not its distance in x. Sizing w off the
    # x-overlap first gave a corner buried only 0.74mm where 0.80 was asked for, and the emitted
    # mesh said so: measuring by a different route than the one that produced the number.
    reach = mc.GRID_PITCH / 2 - x_b                  # ring centre to the bar's end plane
    inner = (ring_out_r - BITE) ** 2
    if inner <= reach ** 2:
        raise SystemExit(f"no tie bar fits: a bar ending {reach:.2f}mm from the ring centre cannot "
                         f"bite {BITE:g}mm into a ring only O{2*ring_out_r:.1f}. Knob: RING_GAP.")
    bar_half_w = math.sqrt(inner - reach ** 2)

    # ---- how hard the tie is pushed, from base_ballast's own tip-over solution ----
    if a.segments < 2:
        raise SystemExit(f"a {a.segments}-segment tower has no coupling joint to hang a brace on. "
                         f"Knob: --segments >= 2, or brace the base instead.")
    joint = a.joint if a.joint is not None else a.segments - 1
    if not 1 <= joint <= a.segments - 1:
        raise SystemExit(f"joint {joint} does not exist on a {a.segments}-segment tower "
                         f"(1..{a.segments - 1})")
    tower_h = a.segments * CHUTE_H
    tower_g = a.segments * CHUTE_G
    b_foot = bb.solve_radius(a.nudge, tower_h, tower_g, a.ballast)   # per-tower base half-footprint
    M = (tower_g + a.ballast) * 1e-3
    h_b = joint * CHUTE_H
    tie_P = M * G * (b_foot * 1e-3) / (h_b * 1e-3)   # the most one neighbour can be pushed with

    # ---- plate thickness: the brace's own flex must not add to the play already in the holes.
    # Out of plane is the weak axis and the honest worst case (a nudge square to the tie line):
    # one ring cantilevered a full grid pitch from the next. delta = P L^3 / (3 E I) <= fit_clr.
    L = mc.GRID_PITCH
    i_req = tie_P * L ** 3 / (3 * E_PLA * fit_clr)
    t_min = (i_req * 12 / (2 * bar_half_w)) ** (1 / 3)
    thick = a.thickness if a.thickness is not None else math.ceil(t_min / 0.5) * 0.5

    out = a.out or f"brace_t{a.towers}_{coupling}_{a.segments}seg.stl"
    centres = [((i - (a.towers - 1) / 2) * mc.GRID_PITCH, 0.0) for i in range(a.towers)]

    tris = []
    for cx, cy in centres:
        tris += ring_solid(cx, cy, bore_model_r, ring_out_r, 0.0, thick, a.points)
    for i in range(a.towers - 1):
        mid = (centres[i][0] + centres[i + 1][0]) / 2
        tris += box_solid(mid - x_b, mid + x_b, -bar_half_w, bar_half_w, 0.0, thick)
    write_stl(out, tris)

    # ================= self-verify: re-read the file and MEASURE it =================
    size, T = read_stl(out)
    n = len(T)
    comp = components(T)
    ncomp = max(comp) + 1 if comp else 0
    bodies = [[] for _ in range(ncomp)]
    for i, t in enumerate(T):
        bodies[comp[i]].append(t)

    edges = {}
    for t in T:
        k3 = [tuple(round(c, 3) for c in v) for v in t]
        for i in range(3):
            e = tuple(sorted((k3[i], k3[(i + 1) % 3])))
            edges[e] = edges.get(e, 0) + 1
    open_edges = sum(1 for c in edges.values() if c != 2)

    # classify by triangle count: a ring is 8*points tris, a bar is 12
    ring_ids = [k for k in range(ncomp) if len(bodies[k]) > 100]
    bar_ids = [k for k in range(ncomp) if len(bodies[k]) <= 100]

    meas = []            # (cx, bore_r, out_r, body_id) measured off the emitted mesh
    for k in ring_ids:
        V = [v for t in bodies[k] for v in t]
        cx = (min(v[0] for v in V) + max(v[0] for v in V)) / 2
        cy = (min(v[1] for v in V) + max(v[1] for v in V)) / 2
        rr = [math.hypot(v[0]-cx, v[1]-cy) for v in V]
        r_out_m, r_v = max(rr), min(rr)
        # the real hole is the polygon APOTHEM, not the vertex circle: measure it from the
        # bore edge midpoints, a different route than the r/cos(pi/n) that built them
        bore_v = sorted({(round(v[0], 4), round(v[1], 4)) for v in V
                         if abs(math.hypot(v[0]-cx, v[1]-cy) - r_v) < 1e-3},
                        key=lambda p: math.atan2(p[1]-cy, p[0]-cx))
        apo = min(math.hypot((bore_v[i][0]+bore_v[(i+1) % len(bore_v)][0])/2 - cx,
                             (bore_v[i][1]+bore_v[(i+1) % len(bore_v)][1])/2 - cy)
                  for i in range(len(bore_v)))
        meas.append((cx, apo, r_out_m, k))
    meas.sort()
    meas_bore_d = 2 * min(m[1] for m in meas)
    meas_out_r = max(m[2] for m in meas)
    meas_thick = max(v[2] for t in T for v in t)
    printed_bore_d = meas_bore_d - mc.HOLE_SHRINK
    pitches = [meas[i+1][0] - meas[i][0] for i in range(len(meas)-1)]
    meas_pitch = sum(pitches) / len(pitches) if pitches else float("nan")
    ring_gap_m = (min(pitches) - 2 * meas_out_r) if pitches else float("nan")
    xs = [v[0] for t in T for v in t]; ys = [v[1] for t in T for v in t]
    bbx, bby = max(xs) - min(xs), max(ys) - min(ys)

    # bar geometry off the mesh, then the BITE it actually takes out of each neighbour ring
    bite_m = float("inf")
    corners_in = 0
    corners_want = 0
    for k in bar_ids:
        V = [v for t in bodies[k] for v in t]
        bx0, bx1 = min(v[0] for v in V), max(v[0] for v in V)
        bw = max(v[1] for v in V)
        for cx, _bore, r_out_m, ring_k in meas:
            end = bx0 if cx < (bx0 + bx1) / 2 else bx1
            d = abs(cx - end)
            if d > r_out_m + 1e-6:
                continue                                     # not a neighbour of this bar
            corners_want += 2
            bite_m = min(bite_m, r_out_m - math.hypot(d, bw))
            for sy in (-bw, bw):                             # the two hardest points to reach
                if inside((end, sy, meas_thick / 2), bodies[ring_k]):
                    corners_in += 1

    # BORE EMPTY: sample the hole and require nothing in it. This is what a tower has to pass.
    plugged = 0
    for cx, bore, _ro, _k in meas:
        for fr in (0.0, 0.3, 0.6, 0.9):
            for j in range(24 if fr else 1):
                th = 2 * math.pi * j / 24
                p = (cx + fr*bore*math.cos(th), fr*bore*math.sin(th), meas_thick / 2)
                if any(inside(p, bd) for bd in bodies):
                    plugged += 1

    vol = 0.0
    for A, B, C in T:
        vol += (A[0]*(B[1]*C[2]-C[1]*B[2]) - A[1]*(B[0]*C[2]-C[0]*B[2])
                + A[2]*(B[0]*C[1]-C[0]*B[1])) / 6.0
    vol = abs(vol)

    i_m = (2 * (max(v[1] for t in T for v in t))) * meas_thick ** 3 / 12 if bar_ids else 0.0
    flex = tie_P * L ** 3 / (3 * E_PLA * i_m) if i_m else float("inf")
    unbraced_N = M * G * (b_foot * 1e-3) / (tower_h * 1e-3)
    sway = fit_clr * tower_h / h_b

    print(f"{out}: {n} tris, {size}B | {a.towers} holes O{printed_bore_d:.2f} printed at "
          f"{meas_pitch:.1f}mm pitch, plate {bbx:.0f} x {bby:.0f} x {meas_thick:.1f} mm, "
          f"{coupling} coupling, prints FLAT")
    print(f"  WINDOW measured off the BOND profiles: spigot outer face O{spigot_face_d:.2f} "
          f"(path O{mc.SPIGOT_BASE_D:g} + one half-bead {half_bead:.3f} per side), mouth outer "
          f"face O{mouth_face_d:.2f} => {window:.2f}mm diametral to land in, "
          f"= 2 x (LINE_W {mc.LINE_W:g} + ENTRY_CLEAR {mc.ENTRY_CLEAR:g}), the SAME for slim")
    print(f"  bore sits {fit_clr:.2f}mm radial clear of the spigot (HOLE_SHRINK {mc.HOLE_SHRINK:g} "
          f"+ SPIGOT_DRIFT {SPIGOT_DRIFT:g} ASSUMED) and leaves {ledge:.2f}mm of ledge on the "
          f"{mc.LINE_W:g}mm rim bead; modelled O{2*bore_model_r:.2f} so it PRINTS O{printed_bore_d:.2f}")
    print(f"  ring wall {wall:.2f}mm (all the grid allows less {RING_GAP:g}mm of air), tie bar "
          f"{2*x_b:.2f} x {2*bar_half_w:.2f} x {meas_thick:.1f}mm, thickness DERIVED "
          f"{t_min:.2f} -> {meas_thick:.1f} from a {tie_P:.2f} N tie load at {E_PLA:g} MPa")
    print(f"  FUNCTION: tower {a.segments} x chute = {tower_h:.0f}mm, {tower_g:.0f} g + "
          f"{a.ballast:.0f} g sand on a O{2*b_foot:.0f} base survives {unbraced_N:.2f} N alone. "
          f"Tied at joint {joint} ({h_b:.0f}mm up), {a.towers} towers each borrow the others' full "
          f"restoring moment: {a.towers * unbraced_N:.2f} N, {a.towers}x, and the brace weighs "
          f"{vol*PLA_RHO:.0f} g")
    print(f"  the play in the holes lets the top of a tower sway {sway:.1f}mm before the tie bites "
          f"(fit clearance {fit_clr:.2f} x H/h_b); the plate's own flex adds {flex:.3f}mm")

    checks = [
        ("watertight", open_edges == 0, f"{open_edges} non-paired edges over {ncomp} bodies"),
        ("window is wide enough", window >= 4 * fit_clr,
         f"{window:.2f}mm diametral vs the {4*fit_clr:.2f}mm this fit needs "
         f"({2*fit_clr:.2f} to thread + {2*fit_clr:.2f} of ledge). Under this, a clip is the "
         f"only honest answer"),
        ("threads over the spigot", printed_bore_d - spigot_face_d >= 2 * fit_clr - 0.02,
         f"printed bore O{printed_bore_d:.2f} vs spigot outer face O{spigot_face_d:.2f} = "
         f"{(printed_bore_d - spigot_face_d)/2:.2f}mm radial"),
        ("lands on the rim", (mouth_face_d - printed_bore_d) / 2 >= fit_clr,
         f"{(mouth_face_d - printed_bore_d)/2:.2f}mm of ledge vs {fit_clr:.2f}mm of play: it "
         f"cannot walk off its seat inside its own slop"),
        ("nothing above the spigot is wider", pocket_face_d < spigot_face_d,
         f"pocket outer face O{pocket_face_d:.2f} < spigot O{spigot_face_d:.2f}, so the plate "
         f"threads all the way on"),
        ("fits the base grid", abs(meas_pitch - mc.GRID_PITCH) < 0.05 and len(meas) == a.towers,
         f"{len(meas)} holes measured {meas_pitch:.2f}mm apart vs GRID_PITCH {mc.GRID_PITCH:.2f} "
         f"(base_ballast --sockets {a.towers} puts its bosses here)"),
        ("rings clear each other", ring_gap_m >= RING_GAP * 0.8,
         f"{ring_gap_m:.2f}mm of air between neighbouring rings (measured, want "
         f">= {RING_GAP*0.8:.2f})"),
        ("one object", corners_in == corners_want and bite_m >= BITE - MEAS_EPS,
         f"{corners_in}/{corners_want} bar corners measured INSIDE a ring, worst bite "
         f"{bite_m:.2f}mm (want >= {BITE:g})"),
        ("bores are empty", plugged == 0,
         f"{plugged} sample points inside material within a bore (the tower has to pass)"),
        ("brace flex under the tie", flex <= fit_clr,
         f"{flex:.3f}mm out-of-plane at {tie_P:.2f} N vs the {fit_clr:.2f}mm already in the holes"),
        ("bed fit", bbx <= BED and bby <= BED, f"{bbx:.0f} x {bby:.0f} vs {BED:.0f}"),
    ]
    ok = True
    for name, good, msg in checks:
        print("  %s %-30s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    if not ok:
        os.replace(out, out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined")
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS  (print FLAT, no support. Thread it onto a segment's spigot BEFORE "
          "you drop that segment into the socket below.)")


if __name__ == "__main__":
    main()
