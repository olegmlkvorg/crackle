#!/usr/bin/env python3
"""bore_probe.py -- THE bore/socket measuring instrument. stdlib only, no numpy.

WHY THIS EXISTS. Three separate agents were asked to judge the bamboo joints kit. All three spent
their whole context not on judging parts but on discovering their own measuring apparatus was wrong,
and died before reaching a verdict. Their own words:

    "The z-probe picked 4.06, off the bore axis, so those numbers are chord artefacts."
    "Depth reads 15.80 -- but my depth formula measures to the far face, not the mouth."
    "My depth formula was wrong, not the part."

The same shape of failure sank the marble transfer trough: the transit check was wrong three times
in a row and every failure was in the MEASURING, not the part. So the measurement is a tool, once,
cross-checked and selftested. A verdict then costs one command.

WHAT IT MEASURES, off the emitted mesh, using none of the generator's variables:

  1 TRUE BORE DIAMETER ABOUT THE BORE'S OWN AXIS. The axis is FOUND from the geometry (largest
    circle inscribed in the enclosed void of each cross-section), never assumed to be x=0,y=0.
    A probe that samples off-axis measures a CHORD, which always reads small and looks like a
    too-tight part. That mistake is not available here: the void is located first, the centre is
    where the inscribed circle sits, and a supplied --axis that disagrees is REJECTED, not used.
  2 DIAMETER AS A FUNCTION OF HEIGHT, so a pinch or a flare is visible instead of averaged away.
  3 SOCKET DEPTH MEASURED FROM THE MOUTH. The mouth is an opening: there is no surface there to
    hit, which is exactly what defeated the earlier attempts. It is defined explicitly as the end
    of the bore column that is OPEN (no material on the axis beyond it) and located at the plane
    where the void stops being enclosed. The report prints the mouth z, the floor z, the part's
    own extreme z, AND the wrong answer a far-face probe would have given, so the two cannot be
    confused again.
  4 MINIMUM FREE DIAMETER OVER THE FULL DEPTH -- the number a rod actually cares about.

TWO INDEPENDENT ROUTES PER QUANTITY, and they must AGREE or the tool FAILS loudly:

  DIAMETER
  A  2D: slice the mesh at z, classify material by even-odd scanline on a 0.3mm grid, flood the
     outside air in from the border, keep the air it never reached (= the enclosed void), and grow
     the largest inscribed circle in it. Sectioning, flood fill and distance field are transit.py's.
  B  3D: from route A's centre, cast a fan of horizontal rays and intersect them against the raw
     TRIANGLES (Moller-Trumbore). Nearest hit per direction gives r(theta), and a circle fit to the
     hit points gives route B its OWN centre. Shares no code with A -- no grid, no flood fill, no
     parity, no 2D sectioning.
  C  vertex cloud: the radial distance of the mesh's own vertices about the measured axis, over the
     constant-radius region of the bore. Applicable only when such a region exists; when it does
     not, the check is SKIPPED WITH THE REASON PRINTED, never silently dropped.

  FLOOR
  A  2D even-odd parity of the section at the axis point, bisected to the plane where the axis
     first becomes material.
  B  3D Moller-Trumbore ray fired along the axis; its first hit. 2D segments against 3D triangles.

  MOUTH
  A  bisection on void ENCLOSURE: the plane past which the section's air is no longer surrounded.
  B  the extreme z of the mesh vertices lying on the bore wall. A chamfer legitimately puts A past
     B; that case is named MOUTH FLARE, the conservative B value is reported, and B past A -- which
     would mean bore wall past the opening -- is a hard failure.

Agreement tolerances are arguments and are printed with every run (defaults: 0.05mm on diameter,
0.10mm on centre position, 0.15mm on the floor plane, 0.50mm on the mouth plane).

WHAT THIS PROBE CANNOT MEASURE. Read this before believing a number.
  - A BORE THAT IS NOT ALONG THE PROBE AXIS. Pass --dir DX,DY,DZ pointing along the bore; the mesh
    is rotated so that direction becomes local +Z and every number is reported in that frame plus
    world coordinates. Without --dir it measures along Z, and it does NOT search for the direction.
    It does detect the mistake: a fitted tilt over 0.02/mm is a note, over 0.20/mm a hard failure,
    and where the fit is trustworthy it prints the --dir to rerun with. MEASURED 2026-08-03: that
    fit is exact to about 5 deg of tilt and useless by 10 deg, because slicing a tilted bore
    perpendicular to z clips its ends into D shapes. Past that the tool says so and offers nothing,
    because advice from a fit it does not trust is worse than no advice.
  - A NON-ROUND BORE. It reports the largest inscribed circle, which is the largest round rod that
    fits, and flags NON-ROUND with the measured out-of-roundness. "Diameter" is not a single number
    for a square or slotted bore and this tool does not pretend otherwise.
  - A DEPTH AGAINST A DESIGN THAT MEASURES FROM A DIFFERENT PLANE. This probe's mouth is where
    enclosure is LOST, which on a mouth face cut oblique to the bore axis is the SHALLOWEST point
    of the rim. A design quoting depth at the axis crossing of that face reads deeper, by the rim
    spread 2 r tan(face angle). SETTLED 2026-08-03 on bamboo/tetra.stl: flat top face at z=23.3738
    with the bore at 30 deg, rim spread 2*3.5*tan30 = 4.041 mm, so measured 20.037 + 4.041 = 24.078
    against a design 24.10 -- agreement to 0.02 mm. Ruled MET: the shortfall was the measuring
    convention, not missing material, and the generator's own normal-section bore gate independently
    passes that socket at radius 3.500. Check the mouth face angle before re-litigating a shortfall.
  - A SURFACE (vase-path) MESH. It needs a closed solid: even-odd parity calls the inside of a
    single-wall loop material, so there is no enclosed void to find. Non-watertight input is
    detected and refused with that diagnosis. If you must reason about a vase path, the printed wall
    is CENTRED on the path, so free bore = path gap - one bead width; measure the path elsewhere.
  - A BORE THAT OPENS SIDEWAYS, over its whole length (a C-clamp slot, a side-entry channel). Its
    air reaches the section border, so it is never an enclosed void: reported as no bore, not as a
    small one. Where a bore is open sideways over PART of its length -- a sleeve with the wall cut
    away, which sleeve.stl and angle15.stl both do -- the depth is still measured (material on the
    axis bounds it) and the unmeasurable stretch is reported in millimetres, never passed over.
  - A VOID SMALLER THAN MIN_VOID_CELLS grid cells, about 0.45 mm2 at the default 0.3 mm grid. That
    is below anything a 0.4 nozzle prints and is usually a speck left by slicing exactly along a
    flat face, so it is discarded rather than measured.
  - WHETHER A STRAIGHT ROD ACTUALLY PASSES. This tool measures the bore's SIZE and DEPTH about the
    bore's own moving centreline. A channel whose centreline wanders can be everywhere wide enough
    and still admit no straight rod. That is transit.py's question, and it is a different one.
  - THE PRINTED PART. Everything here is MODEL geometry. Printed holes come out under the model
    (transit.HOLE_SHRINK = 0.25 on diameter); pass --shrink to have the printed figures reported
    alongside. Nothing here has touched a printer.
  - A PINCH BETWEEN SLABS. The profile is a ladder, so a constriction thinner than --step can hide
    between samples. Both ends of the depth ARE sampled explicitly; the interior is not exhaustive.
  - A LOCAL MAXIMUM. The inscribed circle is grown by a 16-direction pattern search from the best of
    a coarse scan, so a peanut-shaped void can in principle report a lobe rather than the global
    best. The search cannot leave the void's own bbox and its result is re-verified against every
    segment of the section, so what it returns is always a real inscribed circle.

Usage:
    python3 bore_probe.py part.stl [--dir 1,0,0] [--from lo|hi] [--at U,V] [--step 0.5]
                                   [--shrink 0.25] [--rays 120] [-v]
    python3 bore_probe.py part.stl --require-dia 7.0 --require-depth 24.0    # optional gate
    python3 bore_probe.py --selftest                # synthetic meshes with KNOWN answers

As a library:
    import bore_probe
    rep = bore_probe.probe("sleeve.stl", direction=(1, 0, 0), entry="lo")
    rep["ok"]            measurement is trustworthy (every cross-check agreed). NOT a part verdict.
    rep["dia"]           representative bore diameter about the axis (median over the column)
    rep["min_free_dia"]  smallest free diameter anywhere over the depth  <- what a rod cares about
    rep["depth"]         mouth -> floor, or None when the bore is a through hole
    rep["mouth_z"] / rep["floor_z"] / rep["through"] / rep["part_z"]
    rep["profile"]       [(z, dia_A, dia_B_min, dia_B_max, cx, cy)] the diameter/height curve
    rep["axis"]          (px, py, dx, dy) the fitted axis in the probe frame
    rep["tilt"] / rep["straight"] / rep["bore_dir_world"]   is the probe axis the bore's axis, and
                         if the fit is trustworthy, the direction to rerun --dir with (else None)
    rep["enclosure_gaps"] / rep["gap_mm"]   how much of the depth could NOT be measured
    rep["columns"]       every distinct bore column found, so "which bore?" is never ambiguous
    rep["notes"] / rep["fails"]   the cross-check ledger; print rep["lines"] for the human report

Every return carries every key in REPORT_KEYS, unmeasured ones as None, including refusals -- so
rep["depth"] after a NO-BORE is None and never a KeyError. Exit code is 0 only when ok is True.
"""
import argparse
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Mesh loading and 2D section machinery are NOT rewritten here -- a fourth STL parser in this repo
# is how measurements drift apart. Route A is transit.py's sectioning, flood fill and distance
# field. The one thing it does NOT reuse is transit._inscribe; see _inscribe_hard for why.
from transit import load_tris, section, _voids, _inscribe, _buckets, _d_seg, _d_all, \
    HOLE_SHRINK  # noqa: E402

CELL = 0.3            # mm, section grid pitch for route A (transit.py's default)
SLABS = 40            # z samples across the measured column
STEP_MIN = 0.30       # mm, floor on the z ladder pitch
RAYS = 120            # route B ray fan, 3 deg apart
B_SLABS = 10          # heights at which the full route-B fan is cast (tightest/widest always in)

TOL_DIA = 0.05        # mm, route A vs route B on diameter
TOL_CENTRE = 0.10     # mm, route A centre vs route B circle-fit centre (round bores only)
TOL_FLOOR = 0.15      # mm, void-column floor vs axis-ray floor
TOL_MOUTH = 0.50      # mm, void-column mouth vs bore-surface vertex mouth
ROUND_TOL = 0.15      # mm, out-of-roundness above which a single "diameter" is not meaningful
MIN_VOID_CELLS = 5    # grid cells; below this a void is sectioning noise (0.45 mm2 at cell 0.3,
                      # about a O0.76 hole -- far under anything a 0.4 nozzle can print)

# Deliberate-breakage hook. It exists ONLY so the selftest can prove each cross-check is able to
# FIRE, in the same spirit as board-compile.js's meta case. Never set outside the selftest.
_BREAK = None


# ---------------------------------------------------------------- frame

def rot_to_z(direction):
    """Rotation R (rows) taking `direction` to +Z, plus its transpose. Rodrigues; the 180 deg case
    is handled explicitly because the cross product vanishes there."""
    dx, dy, dz = direction
    m = math.sqrt(dx * dx + dy * dy + dz * dz)
    if m < 1e-12:
        raise ValueError("--dir is the zero vector")
    dx, dy, dz = dx / m, dy / m, dz / m
    kx, ky, kz = dy * 1.0 - dz * 0.0, dz * 0.0 - dx * 1.0, dx * 0.0 - dy * 0.0  # d x zhat
    s = math.sqrt(kx * kx + ky * ky + kz * kz)
    c = dz
    if s < 1e-12:
        R = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)) if c > 0 else \
            ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0))
    else:
        kx, ky, kz = kx / s, ky / s, kz / s
        th = math.atan2(s, c)
        ct, st = math.cos(th), math.sin(th)
        vt = 1.0 - ct
        R = ((ct + kx * kx * vt,      kx * ky * vt - kz * st, kx * kz * vt + ky * st),
             (ky * kx * vt + kz * st, ct + ky * ky * vt,      ky * kz * vt - kx * st),
             (kz * kx * vt - ky * st, kz * ky * vt + kx * st, ct + kz * kz * vt))
    Rt = tuple(tuple(R[j][i] for j in range(3)) for i in range(3))
    return R, Rt


def apply_rot(R, v):
    return (R[0][0] * v[0] + R[0][1] * v[1] + R[0][2] * v[2],
            R[1][0] * v[0] + R[1][1] * v[1] + R[1][2] * v[2],
            R[2][0] * v[0] + R[2][1] * v[1] + R[2][2] * v[2])


# ---------------------------------------------------------------- route B: 3D ray casting

def _mt(ox, oy, oz, dx, dy, dz, v0, v1, v2):
    """Moller-Trumbore. Returns the positive ray parameter t of the hit, or None."""
    e1x, e1y, e1z = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
    e2x, e2y, e2z = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
    px = dy * e2z - dz * e2y
    py = dz * e2x - dx * e2z
    pz = dx * e2y - dy * e2x
    det = e1x * px + e1y * py + e1z * pz
    if -1e-14 < det < 1e-14:
        return None
    inv = 1.0 / det
    tx, ty, tz = ox - v0[0], oy - v0[1], oz - v0[2]
    u = (tx * px + ty * py + tz * pz) * inv
    if u < -1e-9 or u > 1.0 + 1e-9:
        return None
    qx = ty * e1z - tz * e1y
    qy = tz * e1x - tx * e1z
    qz = tx * e1y - ty * e1x
    v = (dx * qx + dy * qy + dz * qz) * inv
    if v < -1e-9 or u + v > 1.0 + 1e-9:
        return None
    t = (e2x * qx + e2y * qy + e2z * qz) * inv
    return t if t > 1e-7 else None


def ray_fan(cands, cx, cy, z, rays=RAYS):
    """Route B. Cast `rays` horizontal rays from (cx, cy, z) and return the nearest triangle hit
    distance per direction, plus the hit points. A direction that hits nothing yields None, which
    means the bore is not closed in that direction."""
    ds, pts = [], []
    for i in range(rays):
        a = 2.0 * math.pi * i / rays
        dx, dy = math.cos(a), math.sin(a)
        best = None
        for (v0, v1, v2) in cands:
            t = _mt(cx, cy, z, dx, dy, 0.0, v0, v1, v2)
            if t is not None and (best is None or t < best):
                best = t
        ds.append(best)
        pts.append(None if best is None else (cx + dx * best, cy + dy * best))
    return ds, pts


def axis_ray(tris, o, d):
    """Route B's floor probe. Every material crossing along the ray from point `o` in direction `d`,
    returned as z values ordered by distance. Zero hits means the axis leaves the part without ever
    meeting material -- that end of the bore is an OPENING, not a floor."""
    out = []
    for (v0, v1, v2) in tris:
        t = _mt(o[0], o[1], o[2], d[0], d[1], d[2], v0, v1, v2)
        if t is not None:
            out.append((t, o[2] + t * d[2]))
    out.sort()
    return [z for (_t, z) in out]


def inside_material(tris, z, x, y):
    """Route A's floor probe: is (x, y) inside material at height z? Even-odd parity of the 2D
    section along +x, the same rule _voids uses to classify its grid. Shares no code with the ray
    caster above -- 2D segments against 3D triangles -- which is what makes the floor cross-check
    worth running."""
    cnt = 0
    for (x0, y0, x1, y1) in section(_cands_at(tris, z), z):
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xc > x:
                cnt += 1
    return bool(cnt & 1)


def circle_fit(pts):
    """Kasa algebraic circle fit -> (cx, cy, r, rms residual). Route B's own centre estimate, owing
    nothing to route A. For a non-round bore the residual is large and the caller must say so."""
    p = [q for q in pts if q is not None]
    n = len(p)
    if n < 3:
        return None
    sx = sy = sxx = syy = sxy = sz = sxz = syz = 0.0
    for (x, y) in p:
        zz = x * x + y * y
        sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y
        sz += zz; sxz += x * zz; syz += y * zz
    a11, a12, a13 = 2 * sxx, 2 * sxy, sx
    a21, a22, a23 = 2 * sxy, 2 * syy, sy
    a31, a32, a33 = 2 * sx, 2 * sy, float(n)
    b1, b2, b3 = sxz, syz, sz
    det = (a11 * (a22 * a33 - a23 * a32) - a12 * (a21 * a33 - a23 * a31)
           + a13 * (a21 * a32 - a22 * a31))
    if abs(det) < 1e-12:
        return None
    cx = (b1 * (a22 * a33 - a23 * a32) - a12 * (b2 * a33 - a23 * b3)
          + a13 * (b2 * a32 - a22 * b3)) / det
    cy = (a11 * (b2 * a33 - a23 * b3) - b1 * (a21 * a33 - a23 * a31)
          + a13 * (a21 * b3 - b2 * a31)) / det
    cc = (a11 * (a22 * b3 - b2 * a32) - a12 * (a21 * b3 - b2 * a31)
          + b1 * (a21 * a32 - a22 * a31)) / det
    rr = cc + cx * cx + cy * cy
    if rr <= 0:
        return None
    r = math.sqrt(rr)
    res = math.sqrt(sum((math.hypot(x - cx, y - cy) - r) ** 2 for (x, y) in p) / n)
    return cx, cy, r, res


# ---------------------------------------------------------------- route A: void columns

DIRS16 = [(math.cos(2 * math.pi * i / 16), math.sin(2 * math.pi * i / 16)) for i in range(16)]


def _seg_meta(segs):
    return [(min(s[0], s[2]), max(s[0], s[2]), min(s[1], s[3]), max(s[1], s[3])) for s in segs]


def _dmin(px, py, segs, meta, cutoff=None):
    """Distance from (px, py) to the nearest section segment. The same quantity as transit._d_all,
    with a bounding-box reject and an optional early exit once the answer is known to be at or
    below `cutoff` (the pattern search only ever asks "is this point better than d?"). The selftest
    checks it against _d_all on a real section rather than assuming the optimisation is harmless."""
    best = float("inf")
    for i, s in enumerate(segs):
        bx0, bx1, by0, by1 = meta[i]
        dx = 0.0 if bx0 <= px <= bx1 else min(abs(px - bx0), abs(px - bx1))
        dy = 0.0 if by0 <= py <= by1 else min(abs(py - by0), abs(py - by1))
        if dx * dx + dy * dy >= best * best:
            continue
        d = _d_seg(px, py, s)
        if d < best:
            best = d
            if cutoff is not None and best <= cutoff:
                return best
    return best


def _inscribe_hard(comp, segs, cell):
    """Largest circle inside one void. Kept as an independent implementation of what
    transit._inscribe now also does, so cases 28/29 can cross-check the two.

    HISTORY, so the next reader knows why this exists: until 2026-08-03 transit._inscribe stepped
    only +-x and +-y, and stalled where two orthogonal walls bind AND sit square to the search
    axes -- measured then: an axis-aligned 7.00 mm square returned centre (-0.250, -0.250)
    r=3.250 against a true 3.500, a 0.5 mm error on diameter, while the same square rotated 1 deg
    erred only 50 nm and a 12x7 slot 49 nm (one binding axis never stalls). The trigger was the
    ALIGNMENT, not the flat -- but axis-aligned is exactly how parts get modelled, so it was worth
    0.5 mm in practice. transit._inscribe has since been fixed with this same 16-direction table
    plus an acceptance epsilon, and selftest case 28 now FAILS if that stall ever returns.

    16 directions: the improving cone is missed only when two binding walls sit within 22.5 deg
    of opposite, the middle of a slot where the error is negligible (worst measured: 0.6 nm on a
    20x5 slot). Every step stays capped at the current radius, exactly as transit does, so the
    search cannot hop a thin wall into a neighbouring void and report its room."""
    xs = [c[0] for c in comp]
    ys = [c[1] for c in comp]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    # No point inside the void can be further from the boundary than half its own bbox diagonal, so
    # segments beyond that of the void's bbox can never be the nearest one. On a part with a second
    # solid beside the bore this drops most of the section. The bound is verified below, not assumed.
    rmax = 0.5 * math.hypot(x1 - x0, y1 - y0) + 2 * cell
    mx, my = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    sub, meta = [], []
    for s in segs:
        bx0, bx1 = min(s[0], s[2]), max(s[0], s[2])
        by0, by1 = min(s[1], s[3]), max(s[1], s[3])
        dx = 0.0 if bx1 >= x0 and bx0 <= x1 else min(abs(x0 - bx1), abs(bx0 - x1))
        dy = 0.0 if by1 >= y0 and by0 <= y1 else min(abs(y0 - by1), abs(by0 - y1))
        if dx * dx + dy * dy <= rmax * rmax:
            sub.append(s)
            meta.append((bx0, bx1, by0, by1))
    # nearest-first, so the running bound drops on the first segments and the bbox reject bites
    ordr = sorted(range(len(sub)),
                  key=lambda i: (max(0.0, meta[i][0] - mx, mx - meta[i][1]) ** 2
                                 + max(0.0, meta[i][2] - my, my - meta[i][3]) ** 2))
    sub = [sub[i] for i in ordr]
    meta = [meta[i] for i in ordr]

    stride = max(1, len(comp) // 120)
    px, py, d = comp[0][0], comp[0][1], -1.0
    for k in range(0, len(comp), stride):
        cx, cy = comp[k]
        if _dmin(cx, cy, sub, meta, cutoff=d) <= d:
            continue
        px, py, d = cx, cy, _dmin(cx, cy, sub, meta)
    # A move must GAIN something to count as one. Accepting a 1e-16 gain kept `moved` true forever,
    # the step never halved, and the search walked a ridge until the process was killed: the tilted
    # fixture hung here for 12 minutes at a near-degenerate section (2026-08-03). The cutoff is
    # d + GAIN, so a call that returns above it did not exit early and IS the true distance.
    GAIN = 1e-9
    step = cell
    rounds = 0
    while step > 1e-4:
        rounds += 1
        if rounds > 2000:
            raise ValueError("_inscribe_hard did not converge in 2000 rounds at a void of bbox "
                             "%.3f x %.3f. The circle it has is real but may not be the largest, "
                             "and quietly under-reporting a bore is the whole failure this file "
                             "exists to stop." % (x1 - x0, y1 - y0))
        step = min(step, max(d, 1e-6))
        moved = False
        for (ux, uy) in DIRS16:
            nx_, ny_ = px + ux * step, py + uy * step
            # The centre of a circle inscribed in this void lies INSIDE this void, so it lies in
            # its bbox. Without that clamp the search walked out of a one-cell void and marched
            # away from the segments the prefilter had kept, gaining ground every round forever.
            if not (x0 - cell <= nx_ <= x1 + cell and y0 - cell <= ny_ <= y1 + cell):
                continue
            nd = _dmin(nx_, ny_, sub, meta, cutoff=d + GAIN)
            if nd <= d + GAIN:
                continue
            px, py, d = nx_, ny_, nd
            moved = True
        if not moved:
            step *= 0.5
    # the prefilter's bound, checked against every segment rather than trusted
    full = _d_all(px, py, segs)
    if full < d - 1e-9:
        raise ValueError("_inscribe_hard prefilter dropped a segment that mattered: r=%.6f but the "
                         "full section says %.6f at (%.4f, %.4f). The bbox bound is wrong."
                         % (d, full, px, py))
    return px, py, d


def _cands_at(tris, z):
    return [t for t in tris if min(v[2] for v in t) <= z <= max(v[2] for v in t)]


def _circles_at(tris_or_cands, z, cell, buck=None, zlo=None, step=None):
    """Every enclosed void at height z with its largest inscribed circle: [(cx, cy, r, cells)]."""
    if buck is not None:
        cands = buck.get(int(math.floor((z - zlo) / step)), ())
    else:
        cands = _cands_at(tris_or_cands, z)
    segs = section(cands, z)
    if not segs:
        return [], segs
    # A void of a few grid cells is sectioning noise, not a bore. Slicing a rotated mesh exactly at
    # a flat face leaves specks of "enclosed air" one cell across; treating one as a bore is how a
    # bisection ended up asking for the largest circle inside 0.30 x 0.00 mm.
    holes = [h for h in _voids(segs, cell) if len(h) >= MIN_VOID_CELLS]
    out = []
    for h in holes:
        cx, cy, r = _inscribe_hard(h, segs, cell)
        out.append((cx, cy, r, h))
    return out, segs


def _void_here(tris, z, cell, near, radius):
    """Is there still an enclosed void at z whose inscribed circle centre is within `radius` of
    `near`? The bisection predicate for both the mouth and the floor."""
    cs, _ = _circles_at(tris, z, cell)
    for (cx, cy, r, _h) in cs:
        if math.hypot(cx - near[0], cy - near[1]) <= radius:
            return True
    return False


def _bisect_edge(tris, z_in, z_out, cell, near, radius, iters=22):
    """The plane between a height where the bore void exists and one where it does not."""
    lo, hi = z_in, z_out
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if _void_here(tris, mid, cell, near, radius):
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def scan_columns(tris, zlo, zhi, step, cell):
    """Ladder scan -> distinct bore COLUMNS. A column is a run of consecutive heights whose voids
    are continuous (each centre lies inside the previous circle or vice versa). Two sockets in one
    sleeve come out as two columns, so "which bore did it measure" is never a guess."""
    buck = _buckets(tris, zlo, step)
    open_cols, done = [], []
    z = zlo + 0.5 * step
    while z < zhi:
        cs, segs = _circles_at(None, z, cell, buck, zlo, step)
        used = set()
        still = []
        for col in open_cols:
            lz, lx, ly, lr = col[-1]
            best, bd = None, None
            for i, (cx, cy, r, _h) in enumerate(cs):
                if i in used:
                    continue
                d = math.hypot(cx - lx, cy - ly)
                if d <= max(lr, r) and (bd is None or d < bd):
                    best, bd = i, d
            if best is None:
                done.append(col)
            else:
                used.add(best)
                cx, cy, r, _h = cs[best]
                col.append((z, cx, cy, r))
                still.append(col)
        for i, (cx, cy, r, _h) in enumerate(cs):
            if i not in used:
                still.append([(z, cx, cy, r)])
        open_cols = still
        z += step
    done.extend(open_cols)
    done = [c for c in done if len(c) >= 2]
    done.sort(key=lambda c: c[0][0])
    return done


# ---------------------------------------------------------------- the probe

REPORT_KEYS = ("ok", "route", "dia", "min_free_dia", "min_free_z", "max_dia", "nonround",
               "round_ok", "depth", "mouth_z", "floor_z", "mouth_side", "through", "length",
               "part_z", "far_face_depth", "profile", "axis", "axis_z", "wander", "columns",
               "picked", "step", "rays", "span", "enclosure_gaps", "gap_mm", "tilt", "straight",
               "bore_dir_world", "notes", "fails", "lines")


def _report(**kw):
    """Every return from probe() carries the SAME keys, unmeasured ones as None. A caller reading
    rep["depth"] after a refusal got a KeyError before, and a selftest case that raises instead of
    failing stops the whole run: the broken-probe demonstration died at case 20 with the remaining
    26 cases never executed, 2026-08-03. A harness must report FAIL, not disappear."""
    out = dict.fromkeys(REPORT_KEYS)
    out["notes"] = []
    out["fails"] = []
    out["lines"] = []
    out["columns"] = []
    out["profile"] = []
    out.update(kw)
    return out


def probe(path, direction=(0.0, 0.0, 1.0), entry="auto", at=None, step=None, cell=CELL,
          rays=RAYS, b_slabs=B_SLABS, shrink=0.0, axis_hint=None,
          tol_dia=TOL_DIA, tol_centre=TOL_CENTRE, tol_floor=TOL_FLOOR, tol_mouth=TOL_MOUTH):
    """Measure one bore. Returns the report dict documented at the top of this file.

    `rep["ok"]` means THE MEASUREMENT IS TRUSTWORTHY -- every cross-check agreed and a bore was
    found. It is not a verdict on the part; this file never issues one."""
    R, Rt = rot_to_z(direction)
    raw = load_tris(path)
    if not raw:
        return _report(**{"ok": False, "route": "NO-MESH", "fails": ["no triangles in %s" % path],
                "notes": [], "lines": ["FAIL no triangles in %s" % path], "columns": []})
    tris = [tuple(apply_rot(R, v) for v in t) for t in raw]

    fails, notes, lines = [], [], []
    zs = [v[2] for t in tris for v in t]
    zlo, zhi = min(zs), max(zs)

    # A mesh that is not a closed solid cannot be sectioned by parity. Say so before measuring.
    edges = {}
    for t in tris:
        vs = [tuple(round(c, 3) for c in v) for v in t]
        for i in range(3):
            a, b = vs[i], vs[(i + 1) % 3]
            k = (a, b) if a <= b else (b, a)
            edges[k] = edges.get(k, 0) + 1
    unpaired = sum(1 for c in edges.values() if c != 2)
    if unpaired:
        msg = ("mesh is NOT watertight: %d of %d edges are unpaired. Even-odd parity cannot tell "
               "material from air here, so no void measurement is attempted. If this is a "
               "single-wall vase PATH rather than a solid, the printed wall is centred on the path "
               "and the free bore = path gap - one bead width; this probe cannot do that for you."
               % (unpaired, len(edges)))
        return _report(**{"ok": False, "route": "NOT-SOLID", "fails": [msg], "notes": [], "columns": [],
                "lines": ["FAIL NOT-SOLID  " + msg]})

    if step is None:
        step = max(STEP_MIN, (zhi - zlo) / SLABS)

    cols = scan_columns(tris, zlo, zhi, step, cell)
    lines.append("%s  |  %d triangles  |  probe axis %s -> local +Z  |  local z %.3f..%.3f  |  "
                 "ladder %.3f mm, section grid %.2f mm"
                 % (os.path.basename(path), len(tris),
                    "%g,%g,%g" % tuple(direction), zlo, zhi, step, cell))
    if not cols:
        msg = ("no enclosed void at any of the sampled heights: this mesh has no bore along the "
               "probe axis. A bore along X or Y needs --dir; a bore that opens sideways is not "
               "enclosed and is invisible to this method by construction.")
        return _report(**{"ok": False, "route": "NO-BORE", "fails": [msg], "notes": notes, "columns": [],
                "lines": lines + ["FAIL NO-BORE  " + msg]})

    summ = []
    for c in cols:
        med = sorted(s[3] for s in c)[len(c) // 2]
        summ.append({"z0": c[0][0], "z1": c[-1][0], "dia": 2 * med,
                     "cx": sum(s[1] for s in c) / len(c), "cy": sum(s[2] for s in c) / len(c),
                     "n": len(c)})
    lines.append("bore columns found: %d" % len(cols))
    for i, s in enumerate(summ):
        lines.append("   [%d] local z %.3f..%.3f  centre (%.3f, %.3f)  median void O%.3f"
                     % (i, s["z0"], s["z1"], s["cx"], s["cy"], s["dia"]))

    # -- pick the column -------------------------------------------------------
    if at is not None:
        pick = min(range(len(cols)),
                   key=lambda i: math.hypot(summ[i]["cx"] - at[0], summ[i]["cy"] - at[1]))
        why = "nearest --at (%.3f, %.3f)" % at
    elif entry == "lo":
        pick = min(range(len(cols)), key=lambda i: summ[i]["z0"])
        why = "--from lo: the column reaching the low end of the probe axis"
    elif entry == "hi":
        pick = max(range(len(cols)), key=lambda i: summ[i]["z1"])
        why = "--from hi: the column reaching the high end of the probe axis"
    else:
        pick = max(range(len(cols)),
                   key=lambda i: (summ[i]["z1"] - summ[i]["z0"]) * summ[i]["dia"])
        why = "auto: the largest column by extent x diameter (use --at or --from to pick another)"
    col = cols[pick]
    if len(cols) > 1:
        notes.append("%d bore columns exist; measuring [%d] -- %s" % (len(cols), pick, why))
    lines.append("measuring column [%d]  (%s)" % (pick, why))

    # -- the axis, and any hint checked against it -----------------------------
    n = len(col)
    zm = sum(s[0] for s in col) / n
    zc = [s[0] - zm for s in col]
    szz = sum(z * z for z in zc)
    px = sum(s[1] for s in col) / n
    py = sum(s[2] for s in col) / n
    adx = sum(zc[i] * col[i][1] for i in range(n)) / szz if szz > 1e-12 else 0.0
    ady = sum(zc[i] * col[i][2] for i in range(n)) / szz if szz > 1e-12 else 0.0
    wander = max(math.hypot(col[i][1] - (px + zc[i] * adx),
                            col[i][2] - (py + zc[i] * ady)) for i in range(n))
    lines.append("axis FOUND from the geometry: (%.4f, %.4f) at local z=%.3f, tilt %+.4f/%+.4f per "
                 "mm; the measured centres wander %.4f mm off that line"
                 % (px, py, zm, adx, ady, wander))

    # IS THE PROBE AXIS EVEN THE BORE'S AXIS. Slicing a tilted bore perpendicular to z still gives
    # the right inscribed DIAMETER -- the inscribed circle of the oblique ellipse is the cylinder's
    # own radius -- but the z-extent is NOT the bore's depth, and the profile is a series of oblique
    # cuts. hub6's radial sockets probed along X fitted a 0.40/mm tilt and were refused for an
    # obscure vertex-cloud reason; a refusal has to name the actual problem (2026-08-03).
    tilt = math.hypot(adx, ady)
    rad_c = max(s[3] for s in col)
    # A direction is only worth offering if the centres actually lie ON the fitted line. hub6's do
    # not -- they wander 1.74 mm -- and the direction fitted through them sent a rerun into a O2.5
    # sliver (2026-08-03). Advice taken from a fit the tool does not trust is worse than no advice.
    straight = wander <= tol_centre
    wdir = None
    if straight:
        mm_ = math.sqrt(1 + tilt ** 2)
        wdir = apply_rot(Rt, (adx / mm_, ady / mm_, 1.0 / mm_))
    if tilt > 0.02:
        adv = ("the bore is NOT parallel to the probe axis: its own axis tilts %.4f mm per mm "
               "(%.1f deg), so the z-extent below is not the bore's own length (it is %.4f times "
               "shorter) and the profile is a series of oblique cuts. "
               % (tilt, math.degrees(math.atan(tilt)), 1.0 / math.sqrt(1 + tilt ** 2)))
        adv += (("Rerun with --dir %.4f,%.4f,%.4f to measure along the bore itself." % wdir)
                if straight else
                ("No direction can be offered: the centres wander %.3f mm off the fitted line "
                 "(tolerance %.3f), so that line is not the bore's axis either."
                 % (wander, tol_centre)))
        if tilt > 0.20:
            fails.append("WRONG AXIS. " + adv)
        else:
            notes.append(adv)
    if not straight:
        notes.append("the void centres do not lie on a LINE: they wander %.3f mm off the best fit "
                     "(tolerance %.3f). Diameters below are still measured about each height's OWN "
                     "centre and stand, but a single axis is the wrong description of this channel, "
                     "and whether a straight rod passes is transit.py's question, not this one."
                     % (wander, tol_centre))
    if wander > 0.5 * rad_c:
        fails.append("the measured void centres do not lie on a LINE: they wander %.3f mm off the "
                     "best fit, more than half the bore radius %.3f. This column is not one "
                     "straight bore, so a single axis and a single depth are both the wrong "
                     "description of it." % (wander, rad_c))
    if axis_hint is not None:
        d = math.hypot(axis_hint[0] - px, axis_hint[1] - py)
        # An axis hint is an ASSERTION, not a selector -- use --at to choose a column. Anything
        # further off than tol_centre would move the measured diameter by more than tol_dia, which
        # is the whole error being guarded against, so it is refused rather than quietly used.
        if d > tol_centre:
            msg = ("supplied axis (%.3f, %.3f) is %.3f mm off the axis MEASURED from the geometry "
                   "(%.3f, %.3f), tolerance %.3f. Probing there would return a CHORD, which always "
                   "reads smaller than the diameter. Rejected: the numbers you asked for would "
                   "have been wrong. To SELECT a bore rather than assert its position, use --at."
                   % (axis_hint[0], axis_hint[1], d, px, py, tol_centre))
            fails.append(msg)
            return _report(**{"ok": False, "route": "AXIS-REJECTED", "fails": fails, "notes": notes,
                    "columns": summ, "lines": lines + ["FAIL AXIS-REJECTED  " + msg]})
        notes.append("supplied axis agrees with the measured axis to %.3f mm" % d)

    # -- how far the bore RUNS, taken from the axis and not from the void column --
    # An enclosed-void column is not the bore. A sleeve whose wall is cut away over part of its
    # length has a bore that is perfectly continuous while its void stops being ENCLOSED, and
    # sleeve.stl does exactly that: four void columns for two sockets, 2026-08-03. Treating a
    # column end as a floor there put the floor 19.6 mm out. What bounds the bore is MATERIAL ON
    # THE AXIS, so that is what is measured, and the enclosure gaps are reported separately.
    zlo_s, zhi_s = col[0][0], col[-1][0]
    rad = max(s[3] for s in col)

    def ax_at(z):
        return (px + (z - zm) * adx, py + (z - zm) * ady)

    def air(z):
        x, y = ax_at(z)
        return not inside_material(tris, z, x, y)

    ladder = [zlo + (k + 0.5) * step for k in range(max(1, int((zhi - zlo) / step)))]
    inside = [i for i in range(len(ladder)) if zlo_s - 1e-9 <= ladder[i] <= zhi_s + 1e-9]
    seed = None
    for i in sorted(inside, key=lambda i: abs(ladder[i] - 0.5 * (zlo_s + zhi_s))):
        if air(ladder[i]):
            seed = i
            break
    if seed is None:
        msg = ("the axis is inside MATERIAL at every sampled height of this void: the void is an "
               "annulus around a core (a conical or pin floor, or a bore around a post), so there "
               "is no axial channel and an insertion depth does not exist. Measure it as a shape, "
               "not as a socket.")
        return _report(**{"ok": False, "route": "ANNULAR", "fails": [msg], "notes": notes, "columns": summ,
                "lines": lines + ["FAIL ANNULAR  " + msg]})

    i_lo = seed
    while i_lo - 1 >= 0 and air(ladder[i_lo - 1]):
        i_lo -= 1
    i_hi = seed
    while i_hi + 1 < len(ladder) and air(ladder[i_hi + 1]):
        i_hi += 1
    open_lo, open_hi = (i_lo == 0), (i_hi == len(ladder) - 1)

    def bisect_air(z_air, z_mat):
        lo, hi = z_air, z_mat
        for _ in range(24):
            mid = 0.5 * (lo + hi)
            if air(mid):
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    floor_lo_a = None if open_lo else bisect_air(ladder[i_lo], ladder[i_lo - 1])
    floor_hi_a = None if open_hi else bisect_air(ladder[i_hi], ladder[i_hi + 1])
    lines.append("axis material scan: air over local z %.3f..%.3f -> %s at the low end, %s at the "
                 "high end" % (ladder[i_lo], ladder[i_hi],
                               "OPEN" if open_lo else "FLOOR z=%.3f" % floor_lo_a,
                               "OPEN" if open_hi else "FLOOR z=%.3f" % floor_hi_a))

    if open_lo and open_hi:
        route = "THROUGH"
    elif open_lo or open_hi:
        route = "SOCKET"
    else:
        route = "SEALED"

    # THE MOUTH. It is an opening, so nothing is there to hit: it is the OUTERMOST plane along the
    # bore at which the void is still enclosed. Taking instead the end of whichever void column was
    # picked put l90's mouth at z=24.5 when the bore opens at z=32.0, because --from lo had selected
    # the inner of the two columns that one cut-away wall splits a single socket into (2026-08-03).
    # The part's own extreme z is printed beside the mouth and is a different number again.
    def enclosed(z):
        cs, _ = _circles_at(tris, z, cell)
        x, y = ax_at(z)
        return any(math.hypot(c[0] - x, c[1] - y) <= rad for c in cs)

    def bisect_enc(z_in, z_out):
        lo, hi = z_in, z_out
        for _ in range(22):
            mid = 0.5 * (lo + hi)
            if enclosed(mid):
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def outer_enclosure(i_end, sign, i_stop, zlim):
        """Walk inward from the open end of the axis air-run to the outermost height that still has
        an enclosed void around the axis, then bisect to the plane where enclosure is lost."""
        k = i_end
        while k != i_stop and not enclosed(ladder[k]):
            k -= sign
        if not enclosed(ladder[k]):
            return None
        nxt = k + sign
        z_out = ladder[nxt] if i_lo <= nxt <= i_hi else zlim
        return bisect_enc(ladder[k], z_out)

    mouth_z = floor_z = None
    mouth_side = None
    if route == "SEALED":
        notes.append("both ends of this void are closed by material on the axis: it is a SEALED "
                     "internal cavity, not a socket. Nothing can be inserted, so there is no "
                     "mouth and no depth.")
    else:
        mouth_side = "lo" if open_lo else "hi"
        if open_lo:
            mouth_z = outer_enclosure(i_lo, -1, i_hi, zlo - 1e-6)
        else:
            mouth_z = outer_enclosure(i_hi, +1, i_lo, zhi + 1e-6)
        if mouth_z is None:
            msg = ("the bore is never enclosed anywhere along the axis air-run: its wall is open "
                   "sideways over the whole length, so there is no mouth plane to measure from.")
            return _report(**{"ok": False, "route": "OPEN-SIDE", "fails": [msg], "notes": notes,
                              "columns": summ, "lines": lines + ["FAIL OPEN-SIDE  " + msg]})
        if route == "SOCKET":
            floor_a = floor_hi_a if open_lo else floor_lo_a
            d = (adx, ady, 1.0) if open_lo else (-adx, -ady, -1.0)
            m = math.sqrt(d[0] ** 2 + d[1] ** 2 + 1.0)
            hits = axis_ray(tris, ax_at(ladder[seed]) + (ladder[seed],),
                            (d[0] / m, d[1] / m, d[2] / m))
            floor_b = hits[0] if hits else None
            if _BREAK == "far_face":
                floor_b = zlo if open_hi else zhi        # the historical bug, on purpose
            if floor_b is None:
                fails.append("FLOOR routes disagree: the 2D parity scan says material closes the "
                             "axis at z=%.3f but the 3D axis ray hit nothing at all." % floor_a)
                floor_z = floor_a
            else:
                dfloor = abs(floor_a - floor_b)
                if dfloor > tol_floor:
                    fails.append("FLOOR routes disagree by %.3f mm (tolerance %.2f): 2D section "
                                 "parity puts the first material on the axis at z=%.3f, the 3D "
                                 "axis ray at z=%.3f. One of them is not the socket floor."
                                 % (dfloor, tol_floor, floor_a, floor_b))
                else:
                    notes.append("floor cross-check: 2D section parity says z=%.3f, the 3D axis "
                                 "ray says z=%.3f, agree to %.3f mm"
                                 % (floor_a, floor_b, dfloor))
                floor_z = floor_b

    # -- the measured span, its ladder, its END PLANES, and any enclosure gaps ----
    # "minimum free diameter over the full DEPTH" has to include the depth's ends. A ladder of slab
    # centres stops half a step short of each, and on a tapered bore the tightest point is exactly
    # there: it read O6.018 for a modelled O5.997 until these two samples were added.
    if route == "SEALED":
        span = (min(zlo_s, ladder[i_lo]), max(zhi_s, ladder[i_hi]))
    elif route == "THROUGH":
        other = outer_enclosure(i_hi, +1, i_lo, zhi + 1e-6) if mouth_side == "lo" \
            else outer_enclosure(i_lo, -1, i_hi, zlo - 1e-6)
        other = mouth_z if other is None else other
        span = (min(mouth_z, other), max(mouth_z, other))
    else:
        span = (min(mouth_z, floor_z), max(mouth_z, floor_z))

    eps = min(0.02, step / 10.0)
    want_z = [z for z in ladder if span[0] + 1e-9 < z < span[1] - 1e-9]
    want_z = [span[0] + eps] + want_z + [span[1] - eps]
    slabs, gaps = [], []
    for zq in sorted(set(want_z)):
        cs, _ = _circles_at(tris, zq, cell)
        x, y = ax_at(zq)
        cand = [c for c in cs if math.hypot(c[0] - x, c[1] - y) <= rad]
        if cand:
            cx, cy, r, _h = min(cand, key=lambda c: math.hypot(c[0] - x, c[1] - y))
            slabs.append((zq, cx, cy, r))
        else:
            gaps.append(zq)
    if gaps:
        notes.append("NOT ENCLOSED at %d of %d sampled heights (z %.3f..%.3f, about %.2f mm of the "
                     "span): the wall is cut away there, so the bore is open sideways and its free "
                     "diameter CANNOT be measured by this method over that stretch. The figures "
                     "below cover the enclosed heights only."
                     % (len(gaps), len(gaps) + len(slabs), min(gaps), max(gaps),
                        len(gaps) * step))
    if not slabs:
        msg = ("no enclosed void anywhere between the mouth and the floor: the bore is open "
               "sideways over its whole length, so this method cannot measure its diameter.")
        return _report(**{"ok": False, "route": "OPEN-SIDE", "fails": [msg], "notes": notes, "columns": summ,
                "lines": lines + ["FAIL OPEN-SIDE  " + msg]})
    ns = len(slabs)

    # -- diameter profile: route A everywhere, route B at b_slabs heights -------
    prof = []
    order = sorted(range(ns), key=lambda i: slabs[i][3])
    want = set(order[:1] + order[-1:])                      # tightest and widest always measured
    stride = max(1, ns // max(1, b_slabs))
    want |= set(range(0, ns, stride))
    want |= {0, ns - 1}                                     # and both ends of the depth
    b_at = {}
    for i in sorted(want):
        z, cx, cy, r = slabs[i]
        ds, pts = ray_fan(_cands_at(tris, z),
                          cx + (1.5 if _BREAK == "off_axis" else 0.0), cy, z, rays)
        good = [d for d in ds if d is not None]
        if len(good) < rays:
            notes.append("z=%.3f: %d of %d ray directions left the part without hitting material "
                         "-- the void is not closed all the way round at that height"
                         % (z, rays - len(good), rays))
        if not good:
            continue
        fit = circle_fit(pts)
        b_at[i] = (min(good), max(good), fit)
    for i in range(ns):
        z, cx, cy, r = slabs[i]
        b = b_at.get(i)
        prof.append((z, 2 * r, (2 * b[0] if b else None), (2 * b[1] if b else None), cx, cy))

    # -- HARD cross-check A vs B ------------------------------------------------
    if not b_at:
        fails.append("route B measured NOTHING: every ray fan left the part without hitting "
                     "material. Route A's numbers stand uncorroborated, so they are refused. "
                     "An unchecked measurement is the failure mode this file exists to stop.")
    worst_d, worst_z = 0.0, None
    worst_c, worst_cz = 0.0, None
    nonround = 0.0
    for i, (bmin, bmax, fit) in b_at.items():
        z, cx, cy, r = slabs[i]
        if _BREAK == "scale_a":
            r *= 1.03
        d = abs(2 * bmin - 2 * r)
        if d > worst_d:
            worst_d, worst_z = d, z
        nonround = max(nonround, bmax - bmin)
        if fit is not None and fit[3] < tol_dia:
            c = math.hypot(fit[0] - cx, fit[1] - cy)
            if c > worst_c:
                worst_c, worst_cz = c, z
    if worst_d > tol_dia:
        fails.append("DIAMETER routes disagree by %.4f mm at z=%.3f (tolerance %.3f). Route A is "
                     "the inscribed circle of the flood-filled void; route B is the nearest "
                     "triangle hit of a %d-ray fan cast from that same centre. They measure the "
                     "same distance by different code, so a gap means one of them is broken."
                     % (worst_d, worst_z, tol_dia, rays))
    else:
        notes.append("diameter cross-check: route A (2D flood + inscribed circle) and route B (3D "
                     "%d-ray triangle casting) agree to %.4f mm everywhere (tolerance %.3f)"
                     % (rays, worst_d, tol_dia))
    if worst_cz is not None and worst_c > tol_centre:
        fails.append("CENTRE routes disagree by %.4f mm at z=%.3f (tolerance %.3f): route B's "
                     "circle fit to its own hit points does not land on route A's inscribed centre."
                     % (worst_c, worst_cz, tol_centre))
    elif worst_cz is not None:
        notes.append("centre cross-check: route B's circle fit lands within %.4f mm of route A's "
                     "inscribed centre (tolerance %.3f)" % (worst_c, tol_centre))
    round_flag = nonround > ROUND_TOL
    if round_flag:
        notes.append("NON-ROUND: the bore's radius varies %.3f mm around the axis. A single "
                     "\"diameter\" is not meaningful here; the figures below are the largest "
                     "INSCRIBED circle, i.e. the largest round rod that fits." % nonround)

    # -- route C: vertex cloud over the constant-radius region -------------------
    rmed = sorted(s[3] for s in slabs)[ns // 2]
    band = [i for i in range(ns) if abs(slabs[i][3] - rmed) <= 0.01 * rmed]
    if not straight:
        notes.append("route C SKIPPED and not silently: it measures vertex radii ABOUT THE FITTED "
                     "AXIS, and the centres wander %.3f mm off that line, which is more than the "
                     "%.3f mm the check itself allows. It would report the wander, not the bore."
                     % (wander, tol_dia / 2.0))
        band = []
    if len(band) >= 3 and (slabs[band[-1]][0] - slabs[band[0]][0]) > 2 * step:
        z0 = slabs[band[0]][0] + step
        z1 = slabs[band[-1]][0] - step
        best = None
        for t in tris:
            for v in t:
                if not (z0 <= v[2] <= z1):
                    continue
                rv = math.hypot(v[0] - px - (v[2] - zm) * adx, v[1] - py - (v[2] - zm) * ady)
                if rv < 0.3 * rmed or rv > 1.6 * rmed:
                    continue
                if best is None or rv < best:
                    best = rv
        if best is None:
            notes.append("route C SKIPPED: no mesh vertices lie on the bore wall between z=%.3f "
                         "and z=%.3f (the surface is tessellated only at its ends)" % (z0, z1))
        else:
            allow = tol_dia / 2.0
            hi_allow = nonround + allow
            if best < rmed - allow or best > rmed + hi_allow:
                fails.append("VERTEX-CLOUD route disagrees: the closest mesh vertex on the bore "
                             "wall sits %.4f mm from the measured axis, but the measured bore "
                             "radius there is %.4f mm (allowed %.4f below, %.4f above -- above "
                             "covers tessellation, a facet's corners sit outside its inscribed "
                             "circle). A vertex INSIDE the inscribed circle means the circle is "
                             "wrong or the axis is." % (best, rmed, allow, hi_allow))
            else:
                notes.append("vertex-cloud cross-check: closest bore-wall vertex is %.4f mm from "
                             "the axis vs the measured radius %.4f mm (within -%.3f/+%.3f)"
                             % (best, rmed, allow, hi_allow))
    elif straight:
        notes.append("route C SKIPPED and not silently: the bore has no constant-radius region "
                     "longer than %.2f mm (radius varies over the column), so a single vertex "
                     "radius has nothing to be compared against." % (2 * step))

    # -- mouth cross-check: bore-surface vertices --------------------------------
    if mouth_z is not None:
        def r_at(z):
            if z <= slabs[0][0]:
                return slabs[0][3]
            if z >= slabs[-1][0]:
                return slabs[-1][3]
            for i in range(ns - 1):
                if slabs[i][0] <= z <= slabs[i + 1][0]:
                    f = (z - slabs[i][0]) / max(1e-12, slabs[i + 1][0] - slabs[i][0])
                    return slabs[i][3] + f * (slabs[i + 1][3] - slabs[i][3])
            return rmed
        lo_b, hi_b = min(slabs[0][0], mouth_z) - 1.0, max(slabs[-1][0], mouth_z) + 1.0
        cand_z = []
        for t in tris:
            for v in t:
                if not (lo_b <= v[2] <= hi_b):
                    continue
                rv = math.hypot(v[0] - px - (v[2] - zm) * adx, v[1] - py - (v[2] - zm) * ady)
                if abs(rv - r_at(v[2])) <= 0.20:
                    cand_z.append(v[2])
        if cand_z:
            mouth_b = min(cand_z) if mouth_side == "lo" else max(cand_z)
            dm = abs(mouth_b - mouth_z)
            flare = (mouth_z < mouth_b) if mouth_side == "lo" else (mouth_z > mouth_b)
            # A mouth rim that is not perpendicular to the probe axis SPREADS in z. Route A finds
            # the near edge (enclosure is lost as soon as any part of the wall ends), route B the
            # far edge, and the gap between them is 2 r sin(tilt) of ordinary geometry, not error.
            # The allowance is computed from the tilt this run measured, so at tilt 0 it is nothing.
            rim = 2.0 * rmed * tilt / math.sqrt(1.0 + tilt ** 2)
            tolm = tol_mouth + rim
            if dm <= tolm:
                notes.append("mouth cross-check: void enclosure ends at z=%.3f, the bore-wall "
                             "vertices end at z=%.3f, agree to %.3f mm (tolerance %.3f%s)"
                             % (mouth_z, mouth_b, dm, tolm,
                                " = %.2f + %.3f for a rim tilted %.1f deg"
                                % (tol_mouth, rim, math.degrees(math.atan(tilt))) if rim else ""))
            elif flare:
                notes.append("MOUTH FLARE: the void stays enclosed for %.3f mm past the end of the "
                             "constant-radius bore surface (a chamfer or a flare at the mouth). "
                             "Reporting the conservative mouth at z=%.3f, the end of the bore "
                             "wall itself." % (dm, mouth_b))
                mouth_z = mouth_b
            else:
                fails.append("MOUTH routes disagree by %.3f mm (tolerance %.3f, already widened by "
                             "%.3f for the measured tilt): the void stops being enclosed at z=%.3f "
                             "but bore-wall vertices continue to z=%.3f, which is past the opening. "
                             "Either one of them is not the mouth, or the mouth FACE is cut oblique "
                             "to the probe axis and its rim spans those two planes -- this probe "
                             "cannot tell those apart, so it reports both and refuses to choose."
                             % (dm, tolm, rim, mouth_z, mouth_b))
        else:
            notes.append("mouth cross-check SKIPPED: no mesh vertices sit on the bore wall near "
                         "the mouth to confirm it independently")

    # -- the numbers -------------------------------------------------------------
    dias = [p[1] for p in prof]
    dia = sorted(dias)[len(dias) // 2]
    min_free = min(dias)
    min_free_z = prof[dias.index(min_free)][0]
    depth = None
    if route == "SOCKET" and mouth_z is not None and floor_z is not None:
        depth = abs(mouth_z - floor_z)
    length = abs(span[1] - span[0]) if route != "SOCKET" else None
    part_end = zlo if mouth_side == "lo" else zhi
    far_face = zhi if mouth_side == "lo" else zlo

    lines.append("")
    lines.append("BORE  %s" % route)
    lines.append("   diameter about the bore's OWN axis: median O%.3f, min O%.3f at z=%.3f, "
                 "max O%.3f%s"
                 % (dia, min_free, min_free_z, max(dias),
                    "   NON-ROUND by %.3f mm" % nonround if round_flag else ""))
    lines.append("   MIN FREE DIAMETER over the full depth: O%.3f   <- the number a rod cares about"
                 % min_free)
    if route == "SOCKET":
        lines.append("   MOUTH  local z=%.3f  (the %s end, where the bore stops being enclosed)"
                     % (mouth_z, "low" if mouth_side == "lo" else "high"))
        lines.append("   FLOOR  local z=%.3f  (first material on the axis beyond the bore)" % floor_z)
        lines.append("   DEPTH  %.3f mm   = |mouth - floor|, measured FROM THE MOUTH" % depth)
        lines.append("   for contrast, and these are NOT the depth: mouth to the part's far face "
                     "= %.3f mm; the part's own %s extreme is z=%.3f while the mouth is z=%.3f "
                     "(they differ by %.3f mm)"
                     % (abs(mouth_z - far_face), "low" if mouth_side == "lo" else "high",
                        part_end, mouth_z, abs(part_end - mouth_z)))
    elif route == "THROUGH":
        lines.append("   THROUGH hole: open at both ends, so there is no socket depth. Measured "
                     "length %.3f mm over local z %.3f..%.3f" % (length, span[0], span[1]))
        lines.append("   a through hole is transit.py's question, not this one: being wide enough "
                     "everywhere does not mean a straight rod passes.")
    else:
        lines.append("   SEALED cavity: material closes the axis at BOTH ends. No mouth, no depth.")
    if shrink:
        lines.append("   printed (model - %.2f on diameter): median O%.3f, min free O%.3f%s"
                     % (shrink, dia - shrink, min_free - shrink,
                        ", depth unchanged %.3f mm" % depth if depth is not None else ""))
    else:
        lines.append("   these are MODEL dimensions. A printed hole comes out about %.2f mm "
                     "smaller on diameter (transit.HOLE_SHRINK); pass --shrink to apply it."
                     % HOLE_SHRINK)

    wx = apply_rot(Rt, (px, py, zm))
    lines.append("   axis in WORLD coordinates: passes (%.3f, %.3f, %.3f) along (%g, %g, %g)"
                 % (wx[0], wx[1], wx[2], direction[0], direction[1], direction[2]))

    for m in notes:
        lines.append("   note: " + m)
    for m in fails:
        lines.append("   FAIL: " + m)
    ok = not fails
    lines.append("%s bore_probe  %s  O%.3f min-free, %s"
                 % ("PASS" if ok else "FAIL", route, min_free,
                    "depth %.3f mm from the mouth" % depth if depth is not None
                    else "no socket depth (%s)" % route.lower()))

    return _report(**{"ok": ok, "route": route, "dia": dia, "min_free_dia": min_free,
            "min_free_z": min_free_z, "max_dia": max(dias), "nonround": nonround,
            "round_ok": not round_flag, "depth": depth, "mouth_z": mouth_z, "floor_z": floor_z,
            "mouth_side": mouth_side, "through": route == "THROUGH", "length": length,
            "part_z": (zlo, zhi), "far_face_depth": (abs(mouth_z - far_face)
                                                     if mouth_z is not None else None),
            "profile": prof, "axis": (px, py, adx, ady), "axis_z": zm, "wander": wander,
            "columns": summ, "picked": pick, "step": step, "rays": rays, "span": span,
            "tilt": tilt, "straight": straight, "bore_dir_world": wdir,
            "enclosure_gaps": len(gaps), "gap_mm": len(gaps) * step,
            "notes": notes, "fails": fails, "lines": lines})


# ---------------------------------------------------------------- fixtures (known answers)

def _loop(kind, r, cx, cy, n):
    if kind == "square":
        per = []
        side = 2.0 * r
        m = max(1, n // 4)
        for e in range(4):
            for k in range(m):
                f = k / m
                if e == 0:
                    x, y = -r + side * f, -r
                elif e == 1:
                    x, y = r, -r + side * f
                elif e == 2:
                    x, y = r - side * f, r
                else:
                    x, y = -r, r - side * f
                per.append((cx + x, cy + y))
        return per
    return [(cx + r * math.cos(2 * math.pi * q / n), cy + r * math.sin(2 * math.pi * q / n))
            for q in range(n)]


def _prism(stations, n=96, inner="circle"):
    """stations = [(z, r_out, r_in, cx, cy)] bottom to top. Duplicate z = a horizontal transition
    face (a socket floor, a counterbore step). Emits a watertight solid."""
    tris = []

    def ring(st):
        z, ro, ri, cx, cy = st
        return ([(x, y, z) for (x, y) in _loop("circle", ro, cx, cy, n)],
                [(x, y, z) for (x, y) in _loop(inner, ri, cx, cy, n)] if ri > 0 else None)

    def band(a, b, out):
        za, ra = a
        zb, rb = b
        for q in range(n):
            w = (q + 1) % n
            A, B, C, D = ra[q], ra[w], rb[w], rb[q]
            tris.extend([(A, B, C), (A, C, D)] if out else [(A, C, B), (A, D, C)])

    def cap(inner_ring, outer_ring, up):
        for q in range(n):
            w = (q + 1) % n
            A, B = outer_ring[q], outer_ring[w]
            C, D = inner_ring[q], inner_ring[w]
            tris.extend([(A, B, D), (A, D, C)] if up else [(A, D, B), (A, C, D)])

    def disc(ring_, z, cx, cy, up):
        c = (cx, cy, z)
        for q in range(n):
            w = (q + 1) % n
            tris.append((c, ring_[q], ring_[w]) if up else (c, ring_[w], ring_[q]))

    R = [ring(s) for s in stations]
    for k in range(len(stations) - 1):
        a, b = stations[k], stations[k + 1]
        (ao, ai), (bo, bi) = R[k], R[k + 1]
        if abs(a[0] - b[0]) > 1e-9:
            band((a[0], ao), (b[0], bo), True)
            if ai and bi:
                band((a[0], ai), (b[0], bi), False)
            elif ai or bi:
                raise ValueError("bore starts/stops between stations at z=%g and %g: give two "
                                 "stations at the same z for the transition face" % (a[0], b[0]))
        else:
            if ai and bi:
                # a counterbore step. The void widening upward means material sits BELOW the face.
                if b[2] > a[2]:
                    cap(ai, bi, True)
                else:
                    cap(bi, ai, False)
            elif bi:
                disc(bi, b[0], b[3], b[4], True)
            elif ai:
                disc(ai, a[0], a[3], a[4], False)
    (bo, bi) = R[0]
    if bi:
        cap(bi, bo, False)
    else:
        disc(bo, stations[0][0], stations[0][3], stations[0][4], False)
    (to, ti) = R[-1]
    if ti:
        cap(ti, to, True)
    else:
        disc(to, stations[-1][0], stations[-1][3], stations[-1][4], True)
    return tris


def _subdiv(stations, k=4):
    """Insert k-1 interpolated stations into every non-degenerate band, so the fixture carries
    mesh vertices along the bore wall and not only at its ends. Route C (the vertex-cloud check)
    has nothing to look at otherwise, and a check that always skips is not a check."""
    out = []
    for i in range(len(stations) - 1):
        a, b = stations[i], stations[i + 1]
        out.append(a)
        if abs(a[0] - b[0]) < 1e-9 or (a[2] > 0) != (b[2] > 0):
            continue
        for j in range(1, k):
            f = j / k
            out.append(tuple(a[c] + f * (b[c] - a[c]) for c in range(5)))
    out.append(stations[-1])
    return out


def _box(x0, x1, y0, y1, z0, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return [(v[a], v[b], v[c]) for (a, b, c) in f]


def _write_stl(path, tris):
    with open(path, "wb") as f:
        f.write(b"bore_probe selftest fixture".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            for v in (a, b, c):
                f.write(struct.pack("<3f", *[float(x) for x in v]))
            f.write(struct.pack("<H", 0))
    return path


def _watertight(tris):
    e = {}
    for t in tris:
        vs = [tuple(round(c, 3) for c in v) for v in t]
        for i in range(3):
            a, b = vs[i], vs[(i + 1) % 3]
            k = (a, b) if a <= b else (b, a)
            e[k] = e.get(k, 0) + 1
    return sum(1 for c in e.values() if c != 2)


def _rot_tris(tris, R):
    return [tuple(apply_rot(R, v) for v in t) for t in tris]


def apothem(r, n):
    """The inscribed radius of the n-gon a fixture actually emits. The ground truth of a tessellated
    'O7.00 bore' is NOT 3.5: the largest circle inside a 96-gon of circumradius 3.5 is 3.5*cos(pi/96).
    Stating the fixture's real answer is the difference between a selftest and a ritual."""
    return r * math.cos(math.pi / n)


# ---------------------------------------------------------------- selftest

def selftest(tmp=None, keep=False):
    """Synthetic meshes with answers known from their construction, plus meta cases that PROVE each
    cross-check can fire. Returns the failure count."""
    import tempfile
    tmp = tmp or tempfile.mkdtemp(prefix="bore-probe-selftest-")
    N = 96
    bad = [0]
    idx = [0]

    def ck(name, fn):
        """Each case is a thunk so that a case which RAISES is reported FAIL and the run carries
        on. The deliberately-broken demonstration died at case 20 on a KeyError and the remaining
        26 cases never executed, 2026-08-03: a harness that disappears is not a harness."""
        idx[0] += 1
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, ("case RAISED %s: %s -- a case that dies is a case that did not run"
                              % (type(e).__name__, e))
        if not ok:
            bad[0] += 1
        print("  %-4s %2d %-34s %s" % ("PASS" if ok else "FAIL", idx[0], name, msg))

    def mk(name, tris):
        p = _write_stl(os.path.join(tmp, name), tris)
        return p, _watertight(tris)

    # ---- 0 the frame ------------------------------------------------------
    worst = 0.0
    for d in ((0, 0, 1), (1, 0, 0), (0, 1, 0), (0, 0, -1), (1, 1, 1), (-2, 0.5, 0.3)):
        R, Rt = rot_to_z(d)
        m = math.sqrt(sum(c * c for c in d))
        v = apply_rot(R, tuple(c / m for c in d))
        worst = max(worst, math.hypot(v[0], v[1]), abs(v[2] - 1.0))
        b = apply_rot(Rt, apply_rot(R, (0.3, -0.7, 2.1)))
        worst = max(worst, max(abs(b[i] - (0.3, -0.7, 2.1)[i]) for i in range(3)))
    ck("frame: dir -> +Z, R'R = I", lambda: (worst < 1e-9,
       "worst deviation %.2e over 6 directions" % worst))

    # ---- 1 a perfect through tube: O7.00 --------------------------------
    exp_r = apothem(3.5, N)
    tris = _prism(_subdiv([(0.0, 7.0, 3.5, 0.0, 0.0), (40.0, 7.0, 3.5, 0.0, 0.0)]), N)
    p, unp = mk("tube.stl", tris)
    ck("fixture tube is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r1 = probe(p)
    ck("perfect tube diameter", lambda: (r1["ok"] and abs(r1["dia"] - 2 * exp_r) < 0.01,
       "measured O%.4f vs the 96-gon's true inscribed O%.4f (model circumradius 3.5)"
       % (r1["dia"], 2 * exp_r)))
    ck("perfect tube is flat", lambda: (abs(r1["max_dia"] - r1["min_free_dia"]) < 0.01,
       "profile spans O%.4f..O%.4f over %d heights"
       % (r1["min_free_dia"], r1["max_dia"], len(r1["profile"]))))
    ck("through hole has NO depth", lambda: (r1["route"] == "THROUGH" and r1["depth"] is None,
       "route %s, depth %s -- open at both ends, so a socket depth would be an invention"
       % (r1["route"], r1["depth"])))
    ck("centre found at the origin", lambda: (math.hypot(r1["axis"][0], r1["axis"][1]) < 0.01,
       "axis (%.4f, %.4f)" % (r1["axis"][0], r1["axis"][1])))

    # ---- 2 a blind socket: floor 16, mouth 40, DEPTH 24 -------------------
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 0.0, 0.0), (16.0, 10.0, 0.0, 0.0, 0.0),
                   (16.0, 10.0, 3.5, 0.0, 0.0), (40.0, 10.0, 3.5, 0.0, 0.0)]), N)
    p, unp = mk("socket.stl", tris)
    ck("fixture socket is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r2 = probe(p)
    ck("socket depth from the MOUTH", lambda: (r2["ok"] and abs(r2["depth"] - 24.0) < 0.02,
       "measured %.4f mm, modelled 24.000 (mouth z=%.3f, floor z=%.3f)"
       % (r2["depth"], r2["mouth_z"], r2["floor_z"])))
    ck("depth is NOT to the far face", lambda: (abs(r2["far_face_depth"] - 40.0) < 0.02
       and abs(r2["far_face_depth"] - r2["depth"]) > 15.0,
       "a far-face probe would have said %.3f mm; the case discriminates by %.3f mm"
       % (r2["far_face_depth"], abs(r2["far_face_depth"] - r2["depth"]))))
    ck("socket diameter", lambda: (abs(r2["dia"] - 2 * exp_r) < 0.01,
       "measured O%.4f vs %.4f" % (r2["dia"], 2 * exp_r)))
    ck("socket mouth side identified", lambda: (r2["mouth_side"] == "hi" and r2["route"] == "SOCKET",
       "open end = %s, route %s" % (r2["mouth_side"], r2["route"])))

    # ---- 3 a taper: O7.0 at the floor, O6.0 at the mouth -------------------
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 0.0, 0.0), (16.0, 10.0, 0.0, 0.0, 0.0),
                   (16.0, 10.0, 3.5, 0.0, 0.0), (40.0, 10.0, 3.0, 0.0, 0.0)]), N)
    p, unp = mk("taper.stl", tris)
    ck("fixture taper is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r3 = probe(p)
    exp_lo = 2 * apothem(3.0, N)
    ck("taper min free diameter", lambda: (r3["ok"] and abs(r3["min_free_dia"] - exp_lo) < 0.02,
       "min O%.4f (modelled O%.4f at the mouth), max O%.4f -- a probe that averaged would have "
       "said O%.4f" % (r3["min_free_dia"], exp_lo, r3["max_dia"],
                       (r3["min_free_dia"] + r3["max_dia"]) / 2)))
    mono = all(r3["profile"][i][1] >= r3["profile"][i + 1][1] - 0.02
               for i in range(len(r3["profile"]) - 1))
    ck("taper is visible in the profile", lambda: (mono and r3["max_dia"] - r3["min_free_dia"] > 0.9,
       "diameter falls monotonically over %.3f mm of z, total narrowing %.3f mm"
       % (r3["profile"][-1][0] - r3["profile"][0][0], r3["max_dia"] - r3["min_free_dia"])))

    # ---- 4 THE CHORD CASE: bore centred at (1.5, 0) ------------------------
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 1.5, 0.0), (16.0, 10.0, 0.0, 1.5, 0.0),
                   (16.0, 10.0, 3.5, 1.5, 0.0), (40.0, 10.0, 3.5, 1.5, 0.0)]), N)
    p, unp = mk("offaxis.stl", tris)
    ck("fixture off-axis is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r4 = probe(p)
    ck("off-centre bore: TRUE diameter", lambda: (r4["ok"] and abs(r4["dia"] - 2 * exp_r) < 0.02,
       "measured O%.4f vs modelled O%.4f, with the bore 1.5 mm off the part centre"
       % (r4["dia"], 2 * exp_r)))
    ck("off-centre bore: centre recovered", lambda: (math.hypot(r4["axis"][0] - 1.5, r4["axis"][1]) < 0.02,
       "axis found at (%.4f, %.4f), modelled (1.500, 0.000)" % (r4["axis"][0], r4["axis"][1])))
    # what a naive x=0,y=0 probe would have got -- if it matched, this case would test nothing
    cands = _cands_at([tuple(apply_rot(rot_to_z((0, 0, 1))[0], v) for v in t)
                       for t in load_tris(p)], 28.0)
    nd, _np = ray_fan(cands, 0.0, 0.0, 28.0, 120)
    naive = 2 * min(d for d in nd if d is not None)
    ck("naive on-axis probe reads SMALL", lambda: (naive < r4["dia"] - 1.0,
       "a probe assuming x=0,y=0 measures O%.4f -- %.4f mm under the true O%.4f. That is the "
       "chord artefact the earlier attempts reported." % (naive, r4["dia"] - naive, r4["dia"])))
    r4b = probe(p, axis_hint=(0.0, 0.0))
    ck("a wrong supplied axis is REJECTED", lambda: ((not r4b["ok"]) and r4b["route"] == "AXIS-REJECTED",
       r4b["fails"][0][:150] if r4b["fails"] else "no failure raised"))

    # ---- 5 far off-centre: the void must still be FOUND ---------------------
    tris = _prism(_subdiv([(0.0, 12.0, 0.0, 4.0, -2.5), (16.0, 12.0, 0.0, 4.0, -2.5),
                   (16.0, 12.0, 3.5, 4.0, -2.5), (40.0, 12.0, 3.5, 4.0, -2.5)]), N)
    p, unp = mk("faroff.stl", tris)
    r5 = probe(p)
    ck("far off-centre bore located", lambda: (r5["ok"]
       and math.hypot(r5["axis"][0] - 4.0, r5["axis"][1] + 2.5) < 0.02
       and abs(r5["dia"] - 2 * exp_r) < 0.02,
       "axis (%.4f, %.4f) modelled (4.000, -2.500), O%.4f, depth %.3f"
       % (r5["axis"][0], r5["axis"][1], r5["dia"], r5["depth"])))

    # ---- 6 THE MOUTH IS NOT THE PART TOP -----------------------------------
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 0.0, 0.0), (16.0, 10.0, 0.0, 0.0, 0.0),
                   (16.0, 10.0, 3.5, 0.0, 0.0), (40.0, 10.0, 3.5, 0.0, 0.0)]), N)
    tris = tris + _box(16.0, 24.0, -4.0, 4.0, 0.0, 55.0)
    p, unp = mk("recessed.stl", tris)
    ck("fixture recessed is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r6 = probe(p)
    ck("mouth is the bore's rim, not the part top", lambda: (r6["ok"] and abs(r6["mouth_z"] - 40.0) < 0.05 and abs(r6["part_z"][1] - 55.0) < 0.01,
       "mouth z=%.3f while the part reaches z=%.3f -- a probe that started from the part's top "
       "would have been %.1f mm out" % (r6["mouth_z"], r6["part_z"][1], r6["part_z"][1] - 40.0)))
    ck("recessed-mouth depth still 24", lambda: (abs(r6["depth"] - 24.0) < 0.05,
       "depth %.4f mm, modelled 24.000 (part-top-to-floor would say %.1f)"
       % (r6["depth"], r6["part_z"][1] - 16.0)))

    # ---- 7 a counterbore step -----------------------------------------------
    tris = _prism(_subdiv([(0.0, 12.0, 0.0, 0.0, 0.0), (16.0, 12.0, 0.0, 0.0, 0.0),
                   (16.0, 12.0, 3.5, 0.0, 0.0), (30.0, 12.0, 3.5, 0.0, 0.0),
                   (30.0, 12.0, 7.0, 0.0, 0.0), (40.0, 12.0, 7.0, 0.0, 0.0)]), N)
    p, unp = mk("counterbore.stl", tris)
    ck("fixture counterbore is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r7 = probe(p)
    below = [d for (z, d, _b1, _b2, _x, _y) in r7["profile"] if z < 29.5]
    above = [d for (z, d, _b1, _b2, _x, _y) in r7["profile"] if z > 30.5]
    ck("step visible, min free = the small bore", lambda: (r7["ok"] and abs(r7["min_free_dia"] - 2 * exp_r) < 0.02
       and max(below) - min(below) < 0.02 and min(above) > 13.0,
       "O%.3f below z=30, O%.3f above; min free O%.4f, depth %.3f from the mouth"
       % (max(below), min(above), r7["min_free_dia"], r7["depth"])))

    # ---- 8 a square bore: NON-ROUND, inscribed circle reported ---------------
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 0.0, 0.0), (16.0, 10.0, 0.0, 0.0, 0.0),
                   (16.0, 10.0, 3.5, 0.0, 0.0), (40.0, 10.0, 3.5, 0.0, 0.0)]), N,
                  inner="square")
    p, unp = mk("square.stl", tris)
    ck("fixture square bore is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r8 = probe(p)
    ck("square bore flagged NON-ROUND", lambda: (r8["ok"] and (not r8["round_ok"])
       and abs(r8["dia"] - 7.0) < 0.05,
       "inscribed O%.3f (a 7.00 square's inscribed circle is 7.00), out-of-roundness %.3f mm "
       "(corner-to-flat of a 7.00 square = %.3f)"
       % (r8["dia"], r8["nonround"], 3.5 * math.sqrt(2) - 3.5)))

    # The square bore is the fixture that caught transit._inscribe stalling: stepping only +-x and
    # +-y, every move from (-0.250, -0.250) left the nearer of two orthogonal walls untouched, so it
    # called itself converged at r=3.250 against a true 3.500 -- 0.5 mm of diameter, quietly. It was
    # given 16 directions on 2026-08-03 and now lands the true answer. Both searches are asserted
    # against the same square, so a regression in EITHER is a red case here rather than a bore that
    # under-reports its room and passes a part that cannot be threaded.
    sq_tris = load_tris(p)
    cs, segs = _circles_at(sq_tris, 28.0, CELL)
    hole = _voids(segs, CELL)[0]
    tr = _inscribe(hole, segs, CELL)
    hard = _inscribe_hard(hole, segs, CELL)
    ck("transit._inscribe holds the square", lambda: (abs(tr[2] - 3.5) < 0.005
       and math.hypot(tr[0], tr[1]) < 0.005,
       "transit._inscribe returns centre (%.4f, %.4f) r=%.4f against a true inscribed radius of "
       "3.500. The axis-only stall it replaced returned 3.250, so a radius back near there means "
       "the stall is back" % tr))
    ck("16-direction search recovers it", lambda: (abs(hard[2] - 3.5) < 0.005
       and math.hypot(hard[0], hard[1]) < 0.005,
       "_inscribe_hard returns centre (%.4f, %.4f) r=%.4f, the true answer" % hard))
    worstd = max(abs(_dmin(x * 0.7, y * 0.7, segs, _seg_meta(segs)) - _d_all(x * 0.7, y * 0.7, segs))
                 for x in range(-6, 7) for y in range(-6, 7))
    ck("bbox-pruned distance == _d_all", lambda: (worstd < 1e-12,
       "worst difference %.2e over 169 probe points of a real section" % worstd))

    # ---- 9 no bore at all ----------------------------------------------------
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 0.0, 0.0), (40.0, 10.0, 0.0, 0.0, 0.0)]), N)
    p, unp = mk("solid.stl", tris)
    r9 = probe(p)
    ck("solid bar: NO-BORE, no number", lambda: ((not r9["ok"]) and r9["route"] == "NO-BORE",
       "route %s -- refused rather than reporting a diameter" % r9["route"]))

    # ---- 10 a sealed cavity --------------------------------------------------
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 0.0, 0.0), (16.0, 10.0, 0.0, 0.0, 0.0),
                   (16.0, 10.0, 3.5, 0.0, 0.0), (30.0, 10.0, 3.5, 0.0, 0.0),
                   (30.0, 10.0, 0.0, 0.0, 0.0), (40.0, 10.0, 0.0, 0.0, 0.0)]), N)
    p, unp = mk("sealed.stl", tris)
    ck("fixture sealed is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r10 = probe(p)
    ck("sealed cavity: no mouth, no depth", lambda: (r10["route"] == "SEALED" and r10["depth"] is None and r10["mouth_z"] is None,
       "route %s -- material closes the axis at both ends, so an insertion depth does not exist"
       % r10["route"]))

    # ---- 11 two sockets in one sleeve ---------------------------------------
    tris = _prism(_subdiv([(0.0, 10.0, 3.5, 0.0, 0.0), (24.0, 10.0, 3.5, 0.0, 0.0),
                   (24.0, 10.0, 0.0, 0.0, 0.0), (36.0, 10.0, 0.0, 0.0, 0.0),
                   (36.0, 10.0, 3.0, 0.0, 0.0), (60.0, 10.0, 3.0, 0.0, 0.0)]), N)
    p, unp = mk("twin.stl", tris)
    ck("fixture twin is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r11a = probe(p, entry="lo")
    r11b = probe(p, entry="hi")
    ck("two columns, --from picks the right one", lambda: (len(r11a["columns"]) == 2 and abs(r11a["depth"] - 24.0) < 0.05
       and abs(r11b["depth"] - 24.0) < 0.05
       and abs(r11a["dia"] - 2 * exp_r) < 0.02
       and abs(r11b["dia"] - 2 * apothem(3.0, N)) < 0.02,
       "lo: O%.3f deep %.3f  |  hi: O%.3f deep %.3f  |  %d columns reported"
       % (r11a["dia"], r11a["depth"], r11b["dia"], r11b["depth"], len(r11a["columns"]))))

    # ---- 12 the same socket lying along +X, probed with --dir ---------------
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 0.0, 0.0), (16.0, 10.0, 0.0, 0.0, 0.0),
                   (16.0, 10.0, 3.5, 0.0, 0.0), (40.0, 10.0, 3.5, 0.0, 0.0)]), N)
    _Rx, Rxt = rot_to_z((1.0, 0.0, 0.0))
    laid = _rot_tris(tris, Rxt)                     # local +Z of the socket -> world +X
    p, unp = mk("alongx.stl", laid)
    ck("fixture along-X is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r12 = probe(p, direction=(1.0, 0.0, 0.0))
    ck("bore along +X measured via --dir", lambda: (r12["ok"] and abs(r12["depth"] - 24.0) < 0.02 and abs(r12["dia"] - 2 * exp_r) < 0.01,
       "O%.4f deep %.4f, same socket as case 7 rotated onto X" % (r12["dia"], r12["depth"])))
    r12z = probe(p)
    ck("the same file along Z finds nothing", lambda: ((not r12z["ok"]) and r12z["route"] == "NO-BORE",
       "route %s without --dir -- it does not guess the bore direction, it says so" % r12z["route"]))

    # ---- 13 a surface (vase path) mesh is refused ----------------------------
    surf = []
    ring0 = _loop("circle", 3.5, 0, 0, N)
    for q in range(N):
        w = (q + 1) % N
        a, b = ring0[q], ring0[w]
        surf.append(((a[0], a[1], 0.0), (b[0], b[1], 0.0), (b[0], b[1], 40.0)))
        surf.append(((a[0], a[1], 0.0), (b[0], b[1], 40.0), (a[0], a[1], 40.0)))
    p = _write_stl(os.path.join(tmp, "surface.stl"), surf)
    r13 = probe(p)
    ck("surface (vase path) mesh refused", lambda: ((not r13["ok"]) and r13["route"] == "NOT-SOLID",
       r13["fails"][0][:130]))

    # ---- 14 the bore continues where its void stops being ENCLOSED -----------
    # sleeve.stl does this for real: its wall is cut away over part of the length, so one socket
    # reads as two void columns and a column end is 19.6 mm away from the actual floor. Here the
    # same situation is built with a known answer -- a cup and a collar with 3 mm of clear air
    # between them -- so the depth must still come out 24.000 and the unmeasurable stretch must be
    # declared rather than passed over.
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 0.0, 0.0), (16.0, 10.0, 0.0, 0.0, 0.0),
                           (16.0, 10.0, 3.5, 0.0, 0.0), (24.0, 10.0, 3.5, 0.0, 0.0)]), N)
    tris = tris + _prism(_subdiv([(27.0, 10.0, 3.5, 0.0, 0.0), (40.0, 10.0, 3.5, 0.0, 0.0)]), N)
    p, unp = mk("gapped.stl", tris)
    ck("fixture gapped is watertight", lambda: (unp == 0,
       "%d unpaired edges" % unp))
    r14 = probe(p)
    ck("enclosure gap does not become a floor", lambda: (r14["ok"] and abs(r14["depth"] - 24.0) < 0.05 and len(r14["columns"]) == 2,
       "depth %.4f mm from the mouth z=%.3f to the floor z=%.3f across %d void columns -- taking "
       "the first column's end for the floor would have said %.1f mm"
       % (r14["depth"], r14["mouth_z"], r14["floor_z"], len(r14["columns"]),
          abs(r14["mouth_z"] - 27.0))))
    ck("the unmeasurable stretch is declared", lambda: (r14["enclosure_gaps"] > 0
       and any("NOT ENCLOSED" in nn for nn in r14["notes"]),
       "%.2f mm of the depth is not enclosed and the free diameter there is reported as "
       "unmeasured, not as fine" % r14["gap_mm"]))

    # ---- 15 a bore that is not along the probe axis says so, with the fix ----
    # hub6 and tetra do this for real: radial sockets probed along X. The refusal used to come out
    # as an obscure vertex-cloud complaint. Here the same socket is tilted 20 deg by construction.
    ang = math.radians(20.0)
    dtilt = (math.sin(ang), 0.0, math.cos(ang))
    tris = _prism(_subdiv([(0.0, 10.0, 0.0, 0.0, 0.0), (16.0, 10.0, 0.0, 0.0, 0.0),
                           (16.0, 10.0, 3.5, 0.0, 0.0), (40.0, 10.0, 3.5, 0.0, 0.0)]), N)
    _R20, Rt20 = rot_to_z(dtilt)
    p, unp = mk("tilted.stl", _rot_tris(tris, Rt20))
    ck("fixture tilted is watertight", lambda: (unp == 0, "%d unpaired edges" % unp))
    r15 = probe(p)
    ck("tilted bore probed along Z is REFUSED", lambda: ((not r15["ok"])
       and any("WRONG AXIS" in f for f in r15["fails"]),
       (r15["fails"][0][:150] if r15["fails"] else "NO FAILURE RAISED -- an oblique slice was "
        "reported as if it were the bore")))
    r15b = probe(p, direction=dtilt)
    ck("and measures right along its own axis", lambda: (r15b["ok"]
       and abs(r15b["depth"] - 24.0) < 0.05 and abs(r15b["dia"] - 2 * exp_r) < 0.02,
       "with --dir %.4f,%.4f,%.4f it is O%.4f deep %.4f, the same socket as case 7 tilted 20 deg"
       % (dtilt + (r15b["dia"], r15b["depth"]))))
    ck("and offers NO direction from a bad fit", lambda: (r15["bore_dir_world"] is None,
       "at 20 deg the oblique sections put the fitted centres %.3f mm off a straight line, so the "
       "fitted tilt %.4f is not the true %.4f either and no --dir is offered. hub6 offered one "
       "from a fit this bad and the rerun landed in a O2.5 sliver."
       % (r15["wander"], r15["tilt"], math.tan(ang))))

    # FOLLOW THE TOOL'S OWN ADVICE, where it gives any. Measured 2026-08-03: the fit is exact to
    # about 5 deg (wander 0.0000) and breaks by 10 deg (wander 1.03), which is why the gate exists.
    ang2 = math.radians(5.0)
    d2 = (math.sin(ang2), 0.0, math.cos(ang2))
    _R5, Rt5 = rot_to_z(d2)
    p2, unp2 = mk("tilted5.stl", _rot_tris(tris, Rt5))
    r16 = probe(p2)
    # The expected value is DERIVED from the tilted geometry, not guessed. The floor disc is tilted
    # too and the axis ray meets it at the axis crossing, so that end costs nothing; but the mouth
    # is a tilted RIM, and enclosure is lost at its LOWEST point, one bore radius x sin(tilt) below
    # the axis crossing. z-extent = 24 cos5 - 3.5 sin5. Asserting the naive 24 cos5 failed by
    # 0.31 mm and the tool was right both times.
    exp16 = 24.0 * math.cos(ang2) - 3.5 * math.sin(ang2)
    ck("a 5 deg tilt is a NOTE, and z-extent is short", lambda: (
        r16["ok"] and abs(r16["depth"] - exp16) < 0.05
        and any("NOT parallel" in nn for nn in r16["notes"]),
        "measured along Z the depth is %.4f vs the derived 24cos5 - 3.5sin5 = %.4f: a z-extent "
        "shortened by the tilt AND by the tilted rim, not the bore's length"
        % (r16["depth"], exp16)))
    r16b = probe(p2, direction=r16["bore_dir_world"]) if r16["bore_dir_world"] else None
    ck("its suggested --dir round-trips", lambda: (
        r16b is not None and r16b["ok"] and abs(r16b["depth"] - 24.0) < 0.10
        and abs(r16b["dia"] - 2 * exp_r) < 0.05,
        "it suggested %s and that direction measures O%.4f deep %.4f, recovering the modelled "
        "O%.4f deep 24.000"
        % (("%.4f,%.4f,%.4f" % r16["bore_dir_world"]) if r16["bore_dir_world"] else "NOTHING",
           r16b["dia"] if r16b else 0.0, r16b["depth"] if r16b else 0.0, 2 * exp_r)))

    # ---- 16 every refusal still answers the documented key contract ----------
    missing = {}
    for nm, rep in (("NO-BORE", r9), ("NOT-SOLID", r13), ("AXIS-REJECTED", r4b),
                    ("SOCKET", r2), ("THROUGH", r1), ("SEALED", r10)):
        gap = [k for k in REPORT_KEYS if k not in rep]
        if gap:
            missing[nm] = gap
    ck("every route returns every key", lambda: (not missing,
       "6 routes against the %d documented keys, missing: %s"
       % (len(REPORT_KEYS), missing or "none, so rep[\"depth\"] after a refusal is None rather "
          "than a KeyError that kills the caller")))

    # ---- META: every cross-check must be able to FIRE ------------------------
    global _BREAK
    p = os.path.join(tmp, "socket.stl")
    try:
        _BREAK = "off_axis"
        m1 = probe(p)
        ck("META route B cast off-axis FIRES", lambda: ((not m1["ok"])
           and any("DIAMETER routes disagree" in f for f in m1["fails"]),
       m1["fails"][0][:130] if m1["fails"] else "NO FAILURE RAISED -- the guard is asleep"))
        _BREAK = "scale_a"
        m2 = probe(p)
        ck("META route A radius scaled FIRES", lambda: ((not m2["ok"])
           and any("DIAMETER routes disagree" in f for f in m2["fails"]),
       m2["fails"][0][:130] if m2["fails"] else "NO FAILURE RAISED -- the guard is asleep"))
        _BREAK = "far_face"
        m3 = probe(p)
        ck("META floor at the far face FIRES", lambda: ((not m3["ok"])
           and any("FLOOR routes disagree" in f for f in m3["fails"]),
       m3["fails"][0][:130] if m3["fails"] else "NO FAILURE RAISED -- the guard is asleep"))
    finally:
        _BREAK = None
    m4 = probe(p)
    ck("META breakage restored", lambda: (m4["ok"] and abs(m4["depth"] - 24.0) < 0.02,
       "the same file measures O%.4f deep %.4f again once the break is removed"
       % (m4["dia"], m4["depth"])))

    print("  selftest: %d case(s), %d failure(s). fixtures in %s"
          % (idx[0], bad[0], tmp if keep else tmp))
    return bad[0]


# ---------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stl", nargs="*", help="binary STL(s) holding a bore or socket")
    ap.add_argument("--dir", default="0,0,1", metavar="DX,DY,DZ",
                    help="the bore direction. The mesh is rotated so this becomes local +Z. "
                         "Default 0,0,1. This probe does NOT search for the direction.")
    ap.add_argument("--from", dest="entry", choices=("auto", "lo", "hi"), default="auto",
                    help="which end of the probe axis the socket is entered from, when a part has "
                         "more than one bore column (a sleeve has two)")
    ap.add_argument("--at", default=None, metavar="U,V",
                    help="pick the bore column nearest this point, in the PROBE frame (the report "
                         "lists every column's centre in that frame)")
    ap.add_argument("--axis", default=None, metavar="U,V",
                    help="assert the bore axis is here. If the geometry says otherwise the run is "
                         "REJECTED rather than returning a chord.")
    ap.add_argument("--step", type=float, default=None,
                    help="z ladder pitch in mm (default: height/%d, floor %g)" % (SLABS, STEP_MIN))
    ap.add_argument("--cell", type=float, default=CELL, help="section grid pitch (default %g)" % CELL)
    ap.add_argument("--rays", type=int, default=RAYS, help="route B ray fan size (default %d)" % RAYS)
    ap.add_argument("--shrink", type=float, default=0.0,
                    help="printed hole undersize vs model, mm on diameter, reported alongside the "
                         "model figures (transit.HOLE_SHRINK = %g)" % HOLE_SHRINK)
    ap.add_argument("--tol-dia", type=float, default=TOL_DIA)
    ap.add_argument("--tol-centre", type=float, default=TOL_CENTRE)
    ap.add_argument("--tol-floor", type=float, default=TOL_FLOOR)
    ap.add_argument("--tol-mouth", type=float, default=TOL_MOUTH)
    ap.add_argument("--require-dia", type=float, default=None, metavar="MM",
                    help="optional gate: exit 1 unless the MIN FREE diameter is at least this")
    ap.add_argument("--require-depth", type=float, default=None, metavar="MM",
                    help="optional gate: exit 1 unless the socket depth is at least this")
    ap.add_argument("-v", "--verbose", action="store_true", help="print the diameter/height table")
    ap.add_argument("--selftest", "--self-test", dest="selftest", action="store_true",
                    help="measure synthetic meshes with KNOWN answers and check the probe "
                         "recovers them, including meta cases that prove each guard can fire")
    a = ap.parse_args()

    if a.selftest:
        print("== bore_probe.py selftest ==")
        sys.exit(1 if selftest() else 0)
    if not a.stl:
        ap.error("give at least one STL, or --selftest")

    direction = tuple(float(v) for v in a.dir.split(","))
    at = tuple(float(v) for v in a.at.split(",")) if a.at else None
    axis = tuple(float(v) for v in a.axis.split(",")) if a.axis else None

    failed = 0
    for path in a.stl:
        print("== %s ==" % path)
        rep = probe(path, direction=direction, entry=a.entry, at=at, step=a.step, cell=a.cell,
                    rays=a.rays, shrink=a.shrink, axis_hint=axis, tol_dia=a.tol_dia,
                    tol_centre=a.tol_centre, tol_floor=a.tol_floor, tol_mouth=a.tol_mouth)
        for ln in rep["lines"]:
            print(ln if ln[:4] in ("PASS", "FAIL") else "   " + ln)
        if a.verbose and rep.get("profile"):
            print("   %8s  %10s  %10s  %10s   %s" % ("z", "route A", "route B min", "B max",
                                                     "centre"))
            for (z, da, bmin, bmax, cx, cy) in rep["profile"]:
                print("   %8.3f  O%9.4f  %11s  %10s   (%7.3f, %7.3f)"
                      % (z, da, "O%.4f" % bmin if bmin else "-",
                         "O%.4f" % bmax if bmax else "-", cx, cy))
        bad = not rep["ok"]
        if a.require_dia is not None:
            got = rep.get("min_free_dia")
            hit = got is not None and got >= a.require_dia
            print("%s REQUIRE-DIA min free O%s vs required O%.3f"
                  % ("PASS" if hit else "FAIL", "%.3f" % got if got else "n/a", a.require_dia))
            bad = bad or not hit
        if a.require_depth is not None:
            got = rep.get("depth")
            hit = got is not None and got >= a.require_depth
            print("%s REQUIRE-DEPTH %s vs required %.3f mm"
                  % ("PASS" if hit else "FAIL", "%.3f mm" % got if got else "no depth",
                     a.require_depth))
            bad = bad or not hit
        failed += 1 if bad else 0
    if failed:
        print("FAIL bore_probe: %d of %d file(s)" % (failed, len(a.stl)))
        sys.exit(1)
    print("PASS bore_probe: %d file(s) measured, every cross-check agreed" % len(a.stl))
    sys.exit(0)


if __name__ == "__main__":
    main()
