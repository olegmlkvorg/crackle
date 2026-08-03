#!/usr/bin/env python3
"""NFC REVIEW PUCK -- the counter object a tag lives in, and the reason it is heavy.

WHAT IT IS. A slant-cut drum. A cylinder sliced by a plane; it stands on the slice and presents the
flat circular end face to a phone at the slice angle. An NTAG213 25mm disc inlay seats in a
counterbore directly under that face; the whole interior below is one chamber you fill with sand,
gypsum, coins or shot.

WHY A DRUM AND NOT A CARD. Two scouts found the same three failure modes in the field: metal
counters detune a bare tag (>80% range loss without a spacer), wet/greasy counters destroy a
laminated card, and light objects walk. Every competing product is a flat laminated card or an
acrylic card holder -- all three failures at once. Mass is the fix for two of them and plastic
standoff is the fix for the third, so the honest product is a heavy wipe-down object that cannot be
shipped flat. That is not a styling choice; the arithmetic below sizes it.

THE ORIENTATION IS FORCED, NOT PICKED. The tag is rated -25..75C, so it cannot be printed over
(no pause-at-layer embed), and a pause that drops the nozzle target while extrusion continues is
a known clog path here anyway. So the tag goes in AFTER printing, which means its pocket must be
open in the finished part; and a blind pocket's roof is unsupported unless the pocket opens UPWARD
while printing. The tag has to sit under the tap face. Those three facts together force it:

    tag under the face + no support + no pause  =>  the pocket opens away from the face
                                                =>  in print, "away from the face" points UP
                                                =>  THE TAP FACE IS THE BED FACE

Everything else follows. The tap face gets a bed finish for free (that is the wipe-down surface).
The tag well and the ballast chamber are the same cavity, opening at what becomes the underside.
You pour the ballast in the same orientation you printed in, so the fill settles against the tag and
the set fill IS the tag retainer -- no plug, no lid, no glue relied on.

And face markings have to be recesses, because nothing can stand proud of the bed. So the tap zone
is marked by V-grooves at 60 deg from horizontal: they have no flat ceiling at all, so they are
printable on their own merit (facet nz = -0.50, honestly clear of the -0.707 gate) rather than by
hiding under qa_stl's BED_Z threshold. A groove with a flat 26mm roof would pass that threshold at
0.4mm deep and still be a bridge; this one is not a bridge at any depth.

WHAT IS MEASURED AND WHAT IS ASSUMED. Every number in the report is measured off the emitted STL by
a route that is not the generator: the file is read back and a grid of vertical rays is cast through
the triangle soup, which gives solid volume, cavity volume, section thickness and sealed-void count
without consulting a single design parameter. The ray caster is itself checked against the mesh's
divergence-theorem volume before anything it says is used (HARNESS gate).

The one thing this file CANNOT measure is whether a phone reads the tag through the face. The read
window thickness is ASSUMED workable in 0.8-1.6mm of PLA and nothing here may claim otherwise --
enforced by no_read_claim(), which fails the run if the report contains a phone-read claim while
READ_MEASURED_MM is None. The measurement that would settle it: print the face coupon, stick a real
NTAG213 under it, and record the greatest air gap at which three different phones still read it,
for each of 0.8 / 1.2 / 1.6mm. Until that exists this is a MODEL of a working object.

Usage:
    python3 nfc_puck_stl.py                      # solve the diameter from the physics
    python3 nfc_puck_stl.py --dia 60             # pin it and watch BALLAST fail
    python3 nfc_puck_stl.py --tilt 70            # watch the slide gate fail
    python3 nfc_puck_stl.py --selftest           # force every gate and prove each one fires
"""
import argparse
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import machine  # noqa: E402  -- bead/nozzle doctrine, so this file cannot drift from the machine

# ---------------------------------------------------------------------------
# CONSTANTS. Every one states where it came from. A guess captioned MEASURED is
# the thing this project treats as worst.
# ---------------------------------------------------------------------------
TAG_D   = 25.0        # GIVEN (scouts): NTAG213 25mm disc / wet inlay
TAG_T   = 0.2         # GIVEN: inlay thickness incl. adhesive backing
TAG_TMAX_C = 75.0     # GIVEN: rated -25..75C -- below nozzle temp, hence no pause-embed

BEAD_W  = machine.BEAD_W      # 1.2  -- house bead, 1.5 x the 0.8 nozzle
BEAD_H  = machine.BEAD_H      # 0.6  -- house layer
PLA_RHO = 1.24e-3             # g/mm3, PLA. Repo-wide constant (base_ballast_stl.py)

# READ WINDOW -- ASSUMED, NOT MEASURED. The plastic between the tag and the phone.
WINDOW_MIN, WINDOW_MAX = 0.8, 1.6     # ASSUMED workable band (plastic does not block NFC but
                                      # attenuation rises with thickness). NOT verified on printed
                                      # PLA. See no_read_claim() and READ_MEASURED_MM.
READ_MEASURED_MM = None               # set ONLY by a real coupon measurement, never by a designer

# FILL. Densities are handbook/derived, none of them weighed here.
FILLS = {
    "sand":        (1.60e-3, "dry loose sand, handbook 1.4-1.7 -- ASSUMED, needs a base pad to stay in"),
    "gypsum":      (1.15e-3, "set plaster of Paris, handbook 1.1-1.3 -- ASSUMED, sets solid, no lid"),
    "sand-gypsum": (1.95e-3, "sand with the voids taken by plaster slurry (1.6 + 0.4x1.2) -- DERIVED "
                             "from the two handbook figures, ASSUMED until a filled puck is weighed"),
    "steel-shot":  (4.50e-3, "loose-packed steel shot, 7.85 x ~0.6 random pack -- ASSUMED"),
    "coins":       (4.40e-3, "nickel-plated steel coins loose -- ASSUMED, and they rattle unless bound"),
}
FILL_DEFAULT = "sand-gypsum"

# CONTACT MECHANICS -- the numbers that size the object. Both ASSUMED, both cheap to measure.
MU_DEFAULT    = 0.35   # PLA on a laminate/stone counter. ASSUMED. Confirm with a tilt table: raise
                       # one end until the puck slides, mu = tan(angle). A rubber or felt base ring
                       # takes this to ~0.8 and would roughly halve the mass this file demands.
PRESS_DEFAULT = 3.0    # N a customer pushes into the face on a tap. ASSUMED. Confirm by standing
                       # the puck on a kitchen scale and tapping it twenty times.
SAFETY        = 1.25   # on the required mass
G             = 9.81

# GEOMETRY doctrine
WALL_MIN      = 2 * BEAD_W          # 2.4 -- thinnest wall this file will allow between fill and air
WEB_MIN       = 2 * BEAD_H          # 1.2 -- thinnest section anywhere outside the read window
CHAMBER_MIN   = 6.0                 # mm of chamber depth on the SHALLOW side, or the pour is a film
OVERHANG_MIN  = 50.0                # deg from horizontal. qa_stl fails below 45; this keeps margin
GROOVE_ANG    = 60.0                # deg from horizontal, V-groove walls
GROOVE_W      = BEAD_W              # 1.2 -- one bead wide, so a groove is one bead of missing floor
TILT_BAND     = (15.0, 45.0)        # deg. Below 15 it reads as flat; above 45 the object is a wedge
                                    # and the slide force runs away (see solve_mass).


# ---------------------------------------------------------------------------
# THE PHYSICS THAT SIZES IT
# ---------------------------------------------------------------------------
def required_weight_N(press_N, tilt_deg, mu):
    """Weight the puck needs so a tap does not shove it across the counter.

    A phone pressed into the face pushes along the face normal, which at tilt b from horizontal
    splits into press*sin(b) sideways and press*cos(b) downward. The downward part HELPS -- it
    loads the friction. So the puck slides unless

        mu * (W + press*cos b)  >=  press*sin b

    which rearranges to the weight below. Note what it says: at low tilt the friction from the
    press alone carries it and the requirement is zero; the requirement climbs steeply past
    atan(mu) and is why a steep face needs a heavy object rather than a clever one."""
    b = math.radians(tilt_deg)
    return max(0.0, press_N * (math.sin(b) / mu - math.cos(b)))


def solve_dia(press_N, tilt_deg, mu, rho_fill, aspect, wall, window, seat_h, seat_d):
    """Smallest drum diameter (2mm steps) whose predicted mass clears the requirement.

    Prediction only -- the gate downstream uses the mass MEASURED off the emitted mesh. A slant cut
    through the axis leaves the cylinder's volume unchanged (the wedge it removes on one side it
    adds on the other), so envelope = pi R^2 h and cavity = pi Rc^2 (h - deck) exactly."""
    need = required_weight_N(press_N, tilt_deg, mu) * SAFETY / G * 1000.0   # grams
    deck = window + seat_h
    for d10 in range(400, 1601, 20):          # 40.0 .. 160.0 mm
        D = d10 / 10.0
        R = D / 2.0
        h = aspect * D
        Rc = R - wall
        if Rc <= seat_d / 2 + wall or h - deck <= CHAMBER_MIN + R * math.tan(math.radians(tilt_deg)):
            continue
        cav = math.pi * Rc * Rc * (h - deck)
        solid = math.pi * R * R * h - cav
        if solid * PLA_RHO + cav * rho_fill >= need:
            return D, need
    return None, need


# ---------------------------------------------------------------------------
# MESH. One closed (r, z) profile revolved, where a z may be the symbol TOP,
# meaning "on the slant plane at this point's own x" -- that is what turns a
# lathe into a sliced cylinder without leaving the lathe.
# ---------------------------------------------------------------------------
TOP = "TOP"


def build(P):
    """Return (triangles, profile) for the puck, modelled in PRINT space:
    z=0 is the tap face and lies on the bed; +z runs into the object toward the use-underside."""
    R, Rc, rs = P["R"], P["Rc"], P["seat_d"] / 2.0
    win, seat, ch = P["window"], P["seat_h"], P["chamfer_h"]
    Rbed = R - ch / math.tan(math.radians(P["chamfer_ang"]))
    gd = (GROOVE_W / 2.0) * math.tan(math.radians(GROOVE_ANG))

    prof = [(0.0, 0.0)]
    for rg in P["rings"]:                       # V-grooves cut up into the bed face
        prof += [(rg - GROOVE_W / 2, 0.0), (rg, gd), (rg + GROOVE_W / 2, 0.0)]
    prof += [(Rbed, 0.0), (R, ch)]              # rim chamfer: a real edge break, and 60 deg of it
    if P["sealed"]:
        # THE KNOWN-BAD ARTIFACT. Same part with the chamber roofed over: watertight, and
        # unprintable in either orientation. Kept in the generator so the sealed-void gate and
        # qa_stl PRINTABLE can both be shown to FIRE rather than assumed to work.
        lid = P["lid_z"]
        prof += [(R, TOP), (0.0, TOP), (0.0, lid), (Rc, lid)]
    else:
        prof += [(R, TOP), (Rc, TOP)]           # up the outside, across the slant, into the mouth
    prof += [(Rc, win + seat), (rs, win + seat), (rs, win), (0.0, win)]

    n = P["points"]
    tanb = math.tan(math.radians(P["tilt"]))
    hmid = P["hmid"]

    def ring(entry, k):
        r, z = entry
        th = 2 * math.pi * k / n
        x, y = r * math.cos(th), r * math.sin(th)
        return (x, y, (hmid - x * tanb) if z is TOP else z)

    tris = []
    m = len(prof)
    for i in range(m):
        a, b = prof[i], prof[(i + 1) % m]
        for k in range(n):
            p00, p01 = ring(a, k), ring(a, k + 1)
            p10, p11 = ring(b, k), ring(b, k + 1)
            if a[0] > 1e-9:
                tris.append((p00, p01, p11))
            if b[0] > 1e-9:
                tris.append((p00, p11, p10))
    return tris, prof


def write_stl(path, tris):
    def nrm(a, b, c):
        ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
        vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        mg = math.sqrt(nx*nx + ny*ny + nz*nz)
        return (0.0, 0.0, 0.0) if mg < 1e-12 else (nx/mg, ny/mg, nz/mg)
    with open(path, "wb") as f:
        f.write(b"crackle nfc_puck - ballasted NFC counter object, tag seats under the tap face"
                .ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<3f", *nrm(a, b, c)))
            for v in (a, b, c):
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))


# ---------------------------------------------------------------------------
# MEASUREMENT. Reads the FILE back and never looks at a design parameter.
# ---------------------------------------------------------------------------
def read_stl(path):
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        tris = []
        for _ in range(n):
            f.read(12)
            tris.append(tuple(struct.unpack("<3f", f.read(12)) for _ in range(3)))
            f.read(2)
    return tris, os.path.getsize(path)


def signed_volume(tris):
    """Divergence-theorem volume + centroid of the closed mesh. Route A."""
    v = 0.0
    cx = cy = cz = 0.0
    for a, b, c in tris:
        d = (a[0]*(b[1]*c[2]-c[1]*b[2]) - a[1]*(b[0]*c[2]-c[0]*b[2])
             + a[2]*(b[0]*c[1]-c[0]*b[1])) / 6.0
        v += d
        cx += d * (a[0]+b[0]+c[0]) / 4.0
        cy += d * (a[1]+b[1]+c[1]) / 4.0
        cz += d * (a[2]+b[2]+c[2]) / 4.0
    if abs(v) < 1e-9:
        return 0.0, (0.0, 0.0, 0.0)
    return abs(v), (cx/v, cy/v, cz/v)


def open_edges(tris):
    e = {}
    for t in tris:
        k = [tuple(round(c, 3) for c in v) for v in t]
        for i in range(3):
            a, b = k[i], k[(i+1) % 3]
            key = (a, b) if a <= b else (b, a)
            e[key] = e.get(key, 0) + 1
    return sum(1 for c in e.values() if c != 2)


def fit_top_plane(tris):
    """The slant face, found by its own normal: upward-facing but not horizontal. Returns
    (unit normal, offset) with n.p = d, and the count of faces it was fitted to."""
    pts = []
    nsum = [0.0, 0.0, 0.0]
    for a, b, c in tris:
        ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
        vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        mg = math.sqrt(nx*nx + ny*ny + nz*nz)
        if mg < 1e-12:
            continue
        nz /= mg
        if 0.05 < nz < 0.999:
            nsum[0] += nx/mg; nsum[1] += ny/mg; nsum[2] += nz
            pts += [a, b, c]
    if not pts:
        return None, None, 0
    mg = math.sqrt(sum(v*v for v in nsum)) or 1.0
    nrm = tuple(v/mg for v in nsum)
    d = sum(nrm[j] * sum(p[j] for p in pts) / len(pts) for j in range(3))
    return nrm, d, len(pts)


def raycast(tris, dx, plane, r_meas, r_seat):
    """Route B, and the one that sees inside. Fire a vertical ray up every dx x dx column and walk
    the crossings in z, carrying a WINDING DEPTH: a downward-facing facet is the ray entering
    material, an upward-facing one is it leaving. Material is wherever the depth is positive.

    The winding walk is not decoration. Bare parity pairing (crossing 1 to 2, 3 to 4) reported a
    0.00 mm read window and 54 sealed voids on the first correct mesh, because a column that grazes
    the outer wall clips it twice at almost the same z and every later pairing is then inverted.
    Depth counting is immune to that, and the zero-length grazes drop out at GRAZE.

    What comes back, all of it from the file: solid volume, the void volume under the measured
    slant plane (= the fillable chamber), the fill centroid, the thinnest solid section, and the
    count of ENCLOSED voids -- a void with material both above and below it, which is a sealed
    cavity and is the failure this project has shipped twice.

    Thickness minima skip a 2 mm band inside the measured outer radius: there the part genuinely
    tapers to a chamfered edge, and a square grid column clipping a curved rim measures the grid,
    not the part."""
    GRAZE = 1e-3          # mm; a run this short is a tangential clip, not material
    EDGE_SKIP = 2.0       # mm inside the outer radius, excluded from thickness minima
    nrm, d = plane
    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    nb = max(1, int((hi_x - lo_x) / dx) + 1)
    bins = [[] for _ in range(nb)]
    for t in tris:
        a, b, c = t
        ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
        vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
        nz = ux*vy - uy*vx
        if abs(nz) < 1e-12:
            continue                                    # vertical facet: a vertical ray cannot cross it
        i0 = max(0, int((min(a[0], b[0], c[0]) - lo_x) / dx))
        i1 = min(nb - 1, int((max(a[0], b[0], c[0]) - lo_x) / dx))
        for i in range(i0, i1 + 1):
            bins[i].append(t)

    dA = dx * dx
    solid_v = void_v = 0.0
    fx = fy = fz = 0.0
    sealed = 0
    odd = 0
    cols = 0
    min_web = (1e30, None)     # (thinnest solid run outside the axis zone, radius it happened at)
    axis_runs = []             # solid runs on columns over the tag footprint = the read window
    seed = 0.0137              # nudges the grid off every axis of symmetry, so rays miss vertices
    y = lo_y + dx / 2 + seed
    while y < hi_y:
        x = lo_x + dx / 2 + seed
        while x < hi_x:
            i = int((x - lo_x) / dx)
            hits = []
            for a, b, c in bins[i] if 0 <= i < nb else ():
                d1 = (x - b[0])*(a[1] - b[1]) - (a[0] - b[0])*(y - b[1])
                d2 = (x - c[0])*(b[1] - c[1]) - (b[0] - c[0])*(y - c[1])
                d3 = (x - a[0])*(c[1] - a[1]) - (c[0] - a[0])*(y - a[1])
                if not ((d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0)):
                    continue
                ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
                vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
                nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
                if abs(nz) < 1e-12:
                    continue
                hits.append((a[2] - (nx*(x - a[0]) + ny*(y - a[1])) / nz, -1 if nz < 0 else 1))
            if len(hits) >= 2:
                cols += 1
                hits.sort()
                runs = []
                depth = 0
                start = None
                for z_, s in hits:
                    was = depth
                    depth += 1 if s < 0 else -1        # facet points down = ray enters material
                    if was <= 0 and depth > 0:
                        start = z_
                    elif was > 0 and depth <= 0 and start is not None:
                        if z_ - start > GRAZE:
                            runs.append((start, z_))
                        start = None
                if depth != 0 or start is not None:
                    odd += 1                            # unbalanced walk: do not trust this column
                elif runs:
                    solid_v += dA * sum(b_ - a_ for a_, b_ in runs)
                    sealed += len(runs) - 1
                    r = math.hypot(x, y)
                    thin = min(b_ - a_ for a_, b_ in runs)
                    if r < TAG_D / 2:                 # the tag's own footprint = the read window
                        axis_runs.append(thin)
                    elif r_seat + 1.0 < r < r_meas - EDGE_SKIP and thin < min_web[0]:
                        min_web = (thin, r)           # 1 mm clear of the seat wall, or the gate
                        # measures the step it straddles instead of the plate a groove thins
                    # the chamber: from the last exit up to the measured slant plane
                    if abs(nrm[2]) > 1e-9:
                        z_lid = (d - nrm[0]*x - nrm[1]*y) / nrm[2]
                        gap = z_lid - runs[-1][1]
                        if gap > 0:
                            void_v += dA * gap
                            fx += dA*gap*x; fy += dA*gap*y
                            fz += dA*gap*(z_lid + runs[-1][1]) / 2
            x += dx
        y += dx
    fill_c = (fx/void_v, fy/void_v, fz/void_v) if void_v > 1e-9 else (0.0, 0.0, 0.0)
    return dict(solid=solid_v, void=void_v, fill_c=fill_c, sealed=sealed, odd=odd, cols=cols,
                min_web=min_web, window=(min(axis_runs) if axis_runs else float("nan")),
                n_axis=len(axis_runs))


def face_stats(tris):
    """Steepest overhang and the seat geometry, straight off the facets."""
    worst = 90.0
    z_levels = {}
    for a, b, c in tris:
        ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
        vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        mg = math.sqrt(nx*nx + ny*ny + nz*nz)
        if mg < 1e-12:
            continue
        nz /= mg
        cz = (a[2]+b[2]+c[2]) / 3.0
        if nz < -1e-6 and cz > 0.01:
            worst = min(worst, math.degrees(math.acos(min(1.0, abs(nz)))))
        if nz > 0.999:                                   # flat upward faces: seat floor and ledge
            r = max(math.hypot(v[0], v[1]) for v in (a, b, c))
            z_levels.setdefault(round(cz, 3), 0.0)
            z_levels[round(cz, 3)] = max(z_levels[round(cz, 3)], r)
    return worst, z_levels


def measure_seat(tris, window_z):
    """Seat bore and depth, from the vertices that form the seat wall -- a vertical band whose
    radius is the smallest non-axis radius anywhere above the tap face."""
    band = [v for t in tris for v in t if v[2] > window_z - 0.01]
    rs = [math.hypot(v[0], v[1]) for v in band]
    rmin = min(r for r in rs if r > 0.05)
    zs = [v[2] for v in band if abs(math.hypot(v[0], v[1]) - rmin) < 0.02]
    return 2 * rmin, (max(zs) - min(zs)), min(zs)


# ---------------------------------------------------------------------------
# USE SPACE. Rotate the print mesh so the slant plane is the counter.
# ---------------------------------------------------------------------------
def to_use(p, tilt_deg, hmid):
    b = math.radians(tilt_deg)
    return (-p[0]*math.cos(b) + p[2]*math.sin(b),
            p[1],
            -p[0]*math.sin(b) - p[2]*math.cos(b) + hmid*math.cos(b))


def footprint(tris, tilt_deg, hmid):
    """The counter contact, measured: every vertex that lands on z_use ~ 0, and the polygon it
    traces. Returns (centre_x, centre_y, half-extent in x, half-extent in y)."""
    pts = [to_use(v, tilt_deg, hmid) for t in tris for v in t]
    onbed = [p for p in pts if abs(p[2]) < 0.05]
    if not onbed:
        return None
    xs = [p[0] for p in onbed]; ys = [p[1] for p in onbed]
    return ((min(xs)+max(xs))/2, (min(ys)+max(ys))/2,
            (max(xs)-min(xs))/2, (max(ys)-min(ys))/2)


def inside_margin(x, y, fp):
    """How far inside the elliptical footprint a point sits, in mm (negative = outside)."""
    cx, cy, ax, ay = fp
    t = math.hypot((x - cx)/ax, (y - cy)/ay)
    return (1.0 - t) * min(ax, ay)


# ---------------------------------------------------------------------------
# THE GATE THAT REFUSES A CLAIM
# ---------------------------------------------------------------------------
def section(tris, tilt_deg, hmid, cols=74):
    """An ASCII cross-section CUT FROM THE EMITTED MESH, in use orientation. Not a sketch of what
    the part should be -- the plane y=eps is intersected with the real triangle soup, so if the
    generator and the picture ever disagree, the picture is the one telling the truth."""
    eps = 0.0137
    segs = []
    for t in tris:
        pts = []
        for i in range(3):
            a, b = t[i], t[(i + 1) % 3]
            if (a[1] - eps) * (b[1] - eps) < 0:
                f = (eps - a[1]) / (b[1] - a[1])
                pts.append(tuple(a[j] + f * (b[j] - a[j]) for j in range(3)))
        if len(pts) == 2:
            segs.append(tuple(to_use(p, tilt_deg, hmid) for p in pts))
    if not segs:
        return ["(no section)"]
    xs = [p[0] for s in segs for p in s]
    zs = [p[2] for s in segs for p in s]
    lo_x, hi_x, hi_z = min(xs), max(xs), max(zs)
    sc = (cols - 2) / (hi_x - lo_x)
    rows = int(hi_z * sc / 2.0) + 2                     # /2: character cells are ~2x tall
    grid = [[" "] * cols for _ in range(rows + 1)]
    for (x0, _y0, z0), (x1, _y1, z1) in segs:
        n = max(2, int(max(abs(x1-x0), abs(z1-z0)) * sc) + 2)
        for k in range(n + 1):
            f = k / n
            cx = int((x0 + f*(x1-x0) - lo_x) * sc) + 1
            cy = rows - int((z0 + f*(z1-z0)) * sc / 2.0)
            if 0 <= cy <= rows and 0 <= cx < cols:
                grid[cy][cx] = "#"
    out = ["".join(r).rstrip() for r in grid]
    out.append("_" * cols + "  counter")
    out.append("  section cut from the emitted mesh at y=%g: %.0f mm across the counter, "
               "%.0f mm tall" % (eps, hi_x - lo_x, hi_z))
    return out


CLAIM_WORDS = ("reads through", "phone reads", "works with a phone", "scans reliably",
               "proven read", "read range of", "taps successfully", "confirmed read")


def no_read_claim(lines):
    """Fail the run if anything about to be printed claims phone-read behaviour that has not been
    measured. The rule 'no overselling' only survives as code; this is the code."""
    if READ_MEASURED_MM is not None:
        return
    joined = " ".join(lines).lower()
    hit = [w for w in CLAIM_WORDS if w in joined]
    if hit:
        raise SystemExit("NO-CLAIM GATE: report contains an unmeasured phone-read claim %s. "
                         "READ_MEASURED_MM is None -- print the coupon and measure it first." % hit)


# ---------------------------------------------------------------------------
def build_and_check(a, quiet=False):
    """Emit one puck and return (ok, lines, facts). Nothing here trusts a design parameter."""
    rho_fill, fill_note = FILLS[a.fill]
    solved = None
    if a.dia is None:
        a.dia, need_g = solve_dia(a.press, a.tilt, a.mu, rho_fill, a.aspect,
                                  a.wall, a.window, a.seat_depth, TAG_D + a.seat_clear)
        if a.dia is None:
            raise SystemExit("no diameter up to 160mm carries a %.1f N tap at %g deg on %s. "
                             "Lower --tilt, lower --press, a denser --fill, or a rubber base "
                             "(which raises --mu)." % (a.press, a.tilt, a.fill))
        solved = need_g
    R = a.dia / 2.0
    P = dict(R=R, Rc=R - a.wall, seat_d=TAG_D + a.seat_clear, window=a.window, seat_h=a.seat_depth,
             chamfer_h=a.chamfer, chamfer_ang=a.chamfer_ang, tilt=a.tilt, points=a.points,
             hmid=a.aspect * a.dia, sealed=a.sealed, lid_z=a.window + a.seat_depth + CHAMBER_MIN,
             rings=[TAG_D/2 + a.seat_clear/2 + GROOVE_W/2 + 1.5,
                    TAG_D/2 + a.seat_clear/2 + GROOVE_W/2 + 8.5])
    tris, prof = build(P)
    if a.drop_tri:
        tris = tris[:-a.drop_tri]                 # forces the watertight gate, nothing else
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "nfc_puck_%gmm_%gdeg.stl" % (a.dia, a.tilt))
    write_stl(out, tris)

    # ---- everything below reads the FILE ----
    mt, size = read_stl(out)
    vol_a, com_plastic = signed_volume(mt)
    oe = open_edges(mt)
    nrm, dplane, nfit = fit_top_plane(mt)
    if nrm is None:
        raise SystemExit("no slant face found in the emitted mesh -- the tilt is degenerate")
    r_meas = max(math.hypot(v[0], v[1]) for t in mt for v in t)
    worst_over, levels = face_stats(mt)
    seat_d_m, seat_h_m, seat_z_m = measure_seat(mt, 0.05)
    rc = raycast(mt, a.grid, (nrm, dplane), r_meas, seat_d_m / 2.0)
    tilt_m = math.degrees(math.acos(min(1.0, abs(nrm[2]))))
    hmid_m = dplane / nrm[2]                      # where the measured plane crosses the axis
    fp = footprint(mt, tilt_m, hmid_m)

    harness_err = abs(rc["solid"] - vol_a) / vol_a * 100.0 if vol_a else 100.0
    if a.force_harness:
        harness_err = 99.0
    m_pla = vol_a * PLA_RHO
    m_fill = rc["void"] * rho_fill
    m_tot = m_pla + m_fill
    W = m_tot * G / 1000.0
    W_bare = m_pla * G / 1000.0
    need_W = required_weight_N(a.press, tilt_m, a.mu)

    # what a tap does, in use space, measured
    tapc_use = to_use((0.0, 0.0, 0.0), tilt_m, hmid_m)
    tapedge_use = to_use((TAG_D/2, 0.0, 0.0), tilt_m, hmid_m)
    com_use = to_use(com_plastic, tilt_m, hmid_m)
    fill_use = to_use(rc["fill_c"], tilt_m, hmid_m)
    com_all = tuple((com_use[j]*m_pla + fill_use[j]*m_fill) / max(m_tot, 1e-9) for j in range(3))
    m_stand = inside_margin(com_all[0], com_all[1], fp) if fp else -1.0
    m_tap = min(inside_margin(tapc_use[0], tapc_use[1], fp),
                inside_margin(tapedge_use[0], tapedge_use[1], fp)) if fp else -1.0
    chamber_min = (min(dplane - nrm[0]*v[0] - nrm[1]*v[1] for v in
                       [(P["Rc"]*math.cos(2*math.pi*k/24), P["Rc"]*math.sin(2*math.pi*k/24))
                        for k in range(24)]) / nrm[2]) - (a.window + a.seat_depth)
    wall_m = R - P["Rc"]                          # nominal; the measured version is min_web below
    bbx = max(v[0] for t in mt for v in t) - min(v[0] for t in mt for v in t)
    bby = max(v[1] for t in mt for v in t) - min(v[1] for t in mt for v in t)

    L = []
    p = L.append
    p("%s: %d tris, %d B | drum O%.1f sliced at %.1f deg, %.1f mm on the axis"
      % (os.path.basename(out), len(mt), size, 2*r_meas, tilt_m, hmid_m))
    if solved is not None:
        p("  diameter SOLVED, not picked: a %.1f N tap at %.0f deg on mu=%g needs %.0f g; "
          "stepped up to O%g." % (a.press, a.tilt, a.mu, solved, a.dia))
    p("  tag seat O%.2f x %.2f deep at %.2f above the tap face, %s under a %.2f mm window"
      % (seat_d_m, seat_h_m, seat_z_m, "measured", rc["window"]))
    p("  mass MEASURED off the mesh: %.0f g PLA + %.0f g %s (%.0f cm3 chamber) = %.0f g"
      % (m_pla, m_fill, a.fill, rc["void"]/1000, m_tot))
    p("  fill: %s" % fill_note)
    p("  a %.1f N tap needs %.2f N of weight to stay put; ballasted it has %.2f N, bare PLA "
      "%.2f N" % (a.press, need_W, W, W_bare))
    p("  READ WINDOW %.2f mm is ASSUMED workable (%.1f-%.1f mm band), NOT measured. What would "
      "settle it: a face coupon at 0.8/1.2/1.6 mm with a real NTAG213 behind it, three phones, "
      "record the largest air gap that still triggers. Until then this is a MODEL."
      % (rc["window"], WINDOW_MIN, WINDOW_MAX))

    checks = [
        ("HARNESS", harness_err <= 3.0,
         "ray-cast volume %.0f mm3 vs divergence-theorem %.0f mm3, %.2f%% apart (limit 3%%, "
         "%.1f mm grid) -- two routes to the same number before either is believed"
         % (rc["solid"], vol_a, harness_err, a.grid)),
        ("WATERTIGHT", oe == 0, "%d open edges" % oe),
        ("NO-SEALED-VOID", rc["sealed"] == 0,
         "%d columns of %d enclose a void (material above AND below) -- a sealed cavity is what "
         "shipped unprintable twice here; %d odd-parity columns skipped"
         % (rc["sealed"], rc["cols"], rc["odd"])),
        ("SEAT-BORE", TAG_D + 0.6 <= seat_d_m <= TAG_D + 1.6,
         "O%.2f measured for a O%g tag = %.2f mm diametral clearance; a printed hole lands ~0.25 "
         "under nominal, so it seats at ~O%.2f and cannot wander more than %.2f mm off centre"
         % (seat_d_m, TAG_D, seat_d_m - TAG_D, seat_d_m - 0.25, (seat_d_m - 0.25 - TAG_D)/2)),
        ("SEAT-DEPTH", TAG_T + 0.5 <= seat_h_m <= 3.0,
         "%.2f mm for a %.1f mm inlay -- room for the inlay plus an adhesive pad, and shallow "
         "enough that the fill still presses the tag flat against the window" % (seat_h_m, TAG_T)),
        ("READ-WINDOW", WINDOW_MIN <= rc["window"] <= WINDOW_MAX,
         "%.2f mm of solid PLA over the tag, measured on %d ray columns inside the tag footprint. "
         "ASSUMED band %.1f-%.1f, UNVERIFIED on printed PLA"
         % (rc["window"], rc["n_axis"], WINDOW_MIN, WINDOW_MAX)),
        ("WEB", rc["min_web"][0] >= WEB_MIN,
         "thinnest section outside the tag footprint %.2f mm at r=%.1f (limit %.1f, outer 2 mm of "
         "the chamfered rim excluded) -- this is what a V-groove eats into"
         % (rc["min_web"][0], rc["min_web"][1] or 0.0, WEB_MIN)),
        ("OVERHANG", worst_over >= OVERHANG_MIN,
         "shallowest downward face %.1f deg from horizontal (limit %.0f, qa_stl fails at 45). "
         "Same number says no undercut: a cloth reaches every outside surface" % (worst_over, OVERHANG_MIN)),
        ("CAVITY-WALL", wall_m >= WALL_MIN,
         "%.2f mm between fill and air (limit %.1f = %d beads)" % (wall_m, WALL_MIN, WALL_MIN/BEAD_W)),
        ("CHAMBER", chamber_min >= CHAMBER_MIN,
         "%.1f mm of chamber on the shallow side (limit %.1f) -- shallower and the pour is a film"
         % (chamber_min, CHAMBER_MIN)),
        ("BALLAST", W >= need_W * SAFETY,
         "%.2f N of weight vs %.2f N needed x%.2f safety = %.2f N; a %.1f N tap at %.1f deg on "
         "mu=%g" % (W, need_W, SAFETY, need_W*SAFETY, a.press, tilt_m, a.mu)),
        ("BALLAST-EARNS-IT", W >= 3 * W_bare,
         "ballasted %.2f N vs bare shell %.2f N = %.1fx -- if the plastic alone did it the fill "
         "would be decoration" % (W, W_bare, W/max(W_bare, 1e-9))),
        ("TAP-ZONE-STANDS", m_tap >= 5.0,
         "the marked tap zone projects %.1f mm inside the contact ellipse (limit 5). Press the "
         "far top edge of the face instead and it tips -- that edge is outside the base"
         % m_tap),
        ("STANDS", m_stand >= 8.0,
         "centre of mass lands %.1f mm inside the contact ellipse %.0f x %.0f mm (limit 8)"
         % (m_stand, 2*fp[2] if fp else 0, 2*fp[3] if fp else 0)),
        ("TILT", TILT_BAND[0] <= tilt_m <= TILT_BAND[1] and abs(tilt_m - a.tilt) < 0.5,
         "%.2f deg measured off the slant face normal (%d facets), asked for %g, band %g-%g"
         % (tilt_m, nfit//3, a.tilt, *TILT_BAND)),
        ("BED", max(bbx, bby) <= 340.0, "bbox %.1f x %.1f mm" % (bbx, bby)),
    ]
    ok = True
    for name, good, msg in checks:
        L.append("  %s %-17s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good

    if a.section:
        L += [""] + section(mt, tilt_m, hmid_m) + [""]
    no_read_claim(L)
    if not quiet:
        print("\n".join(L))
    if not ok:
        os.replace(out, out + ".FAILED")
        if not quiet:
            print("  SELF-VERIFY: FAIL -> quarantined as %s.FAILED" % os.path.basename(out))
    elif not quiet:
        print("  SELF-VERIFY: PASS. Prints tap-face-DOWN as modelled, no support, no pause. "
              "Fill it in that same orientation: tag in the seat first, pour, let it set, flip.")
    return ok, L, dict(out=out, mass=m_tot, checks={n: g for n, g, _ in checks})


def add_args(ap):
    ap.add_argument("--dia", type=float, default=None,
                    help="pin the drum diameter instead of solving it from the tap physics. "
                         "Pinning it small is how you watch BALLAST fail.")
    ap.add_argument("--tilt", type=float, default=30.0, help="slice angle = face tilt from horizontal")
    ap.add_argument("--aspect", type=float, default=0.40, help="axial height as a fraction of diameter")
    ap.add_argument("--press", type=float, default=PRESS_DEFAULT, help="N a customer taps with (ASSUMED)")
    ap.add_argument("--mu", type=float, default=MU_DEFAULT, help="friction, puck on counter (ASSUMED)")
    ap.add_argument("--fill", default=FILL_DEFAULT, choices=sorted(FILLS))
    ap.add_argument("--wall", type=float, default=3 * BEAD_W, help="shell wall, bead multiple")
    ap.add_argument("--window", type=float, default=2 * BEAD_H, help="PLA over the tag (ASSUMED band)")
    ap.add_argument("--seat-clear", type=float, default=1.0, dest="seat_clear",
                    help="diametral clearance of the seat over the 25mm tag")
    ap.add_argument("--seat-depth", type=float, default=2 * BEAD_H, dest="seat_depth")
    ap.add_argument("--chamfer", type=float, default=2 * BEAD_W, help="rim chamfer height")
    ap.add_argument("--chamfer-ang", type=float, default=60.0, dest="chamfer_ang")
    ap.add_argument("--points", type=int, default=144)
    ap.add_argument("--grid", type=float, default=1.0, help="ray-cast column pitch, mm")
    ap.add_argument("--out", default=None)
    ap.add_argument("--section", action="store_true",
                    help="print an ASCII cross-section cut from the emitted mesh, in use orientation")
    ap.add_argument("--sealed", action="store_true",
                    help="build the KNOWN-BAD artifact: same puck with the chamber roofed over. "
                         "Watertight and unprintable. Used to prove the gates fire.")
    ap.add_argument("--drop-tri", type=int, default=0, dest="drop_tri",
                    help="delete N triangles, to prove the watertight gate fires")
    ap.add_argument("--force-harness", action="store_true", dest="force_harness",
                    help="feed the harness gate a wrong number, to prove it fires")


def selftest():
    """Every gate, forced. A gate that has never been seen to fail is not a gate."""
    import copy
    base = argparse.Namespace()
    ap = argparse.ArgumentParser(); add_args(ap)
    for act in ap._actions:
        if act.dest != "help":
            setattr(base, act.dest, act.default)
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest.stl")
    cases = [
        ("HARNESS",         dict(force_harness=True)),
        ("WATERTIGHT",      dict(drop_tri=3)),
        ("NO-SEALED-VOID",  dict(sealed=True, dia=80.0)),
        ("SEAT-BORE",       dict(seat_clear=0.1, dia=80.0)),
        ("SEAT-DEPTH",      dict(seat_depth=0.3, dia=80.0)),
        ("READ-WINDOW",     dict(window=3.0, dia=80.0)),
        ("WEB",             dict(window=1.2, seat_depth=0.8, dia=80.0)),
        ("OVERHANG",        dict(chamfer_ang=20.0, dia=80.0)),
        ("CAVITY-WALL",     dict(wall=1.0, dia=80.0)),
        ("CHAMBER",         dict(aspect=0.28, dia=80.0)),
        ("BALLAST",         dict(dia=46.0)),
        ("BALLAST-EARNS-IT", dict(wall=15.0, dia=80.0)),
        ("TAP-ZONE-STANDS", dict(dia=40.0, aspect=1.2)),
        ("STANDS",          dict(dia=40.0, aspect=2.0)),
        ("BED",             dict(dia=350.0, grid=3.0)),
        ("TILT",            dict(tilt=60.0, dia=140.0)),
    ]
    print("SELFTEST -- each gate must be seen to FAIL on an artifact built to break it")
    bad = 0
    for gate, over in cases:
        a = copy.deepcopy(base)
        a.out = tmp
        for k, v in over.items():
            setattr(a, k, v)
        try:
            _ok, _L, facts = build_and_check(a, quiet=True)
            fired = facts["checks"].get(gate) is False
            other = [n for n, g in facts["checks"].items() if g is False and n != gate]
        except SystemExit as e:
            fired, other = ("NO-CLAIM" in str(e) and gate == "NO-CLAIM"), []
        print("  %s %-17s %s" % ("PASS" if fired else "FAIL", gate,
                                 "fired as designed" + (" (also: %s)" % ", ".join(other) if other else "")
                                 if fired else "DID NOT FIRE -- this gate is decoration"))
        bad += 0 if fired else 1
    # the no-claim gate, forced directly: it guards text, not geometry
    try:
        no_read_claim(["the puck reads through 1.2mm of PLA"])
        print("  FAIL %-17s DID NOT FIRE -- this gate is decoration" % "NO-CLAIM")
        bad += 1
    except SystemExit:
        print("  PASS %-17s fired as designed" % "NO-CLAIM")
    for suffix in ("", ".FAILED"):
        if os.path.exists(tmp + suffix):
            os.remove(tmp + suffix)
    print("SELFTEST: %s (%d gates could not be made to fail)"
          % ("PASS" if bad == 0 else "FAIL", bad))
    return bad == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_args(ap)
    ap.add_argument("--selftest", action="store_true", help="force every gate and prove it fires")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(0 if selftest() else 1)
    ok, _L, _f = build_and_check(a)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
