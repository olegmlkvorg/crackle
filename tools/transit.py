#!/usr/bin/env python3
"""transit.py -- can the thing a bore serves actually PASS THROUGH IT. stdlib only, no numpy.

WHY THIS EXISTS. Oleg printed a bamboo bend guide whose generator had just printed six PASS lines,
one of them named "threadable". That check computed the channel SLOPE, (offset/spacing) < 0.12, and
printed the sentence "the rod slides in without snagging". It never measured whether a rod fits.
The middle bore sat 1.54mm off the axis with 0.55mm of room around a fat rod. The same failure with
different nouns -- balls provably captive in a slew ring, a 5.97mm fill corridor for an 8mm ball --
was written down as a lesson on 2026-07-21 and did not prevent this one. Notes did not work, so
this is a gate that FAILS. Full anatomy: Assist/guides/retro-bore-transit.md.

WHAT IT MEASURES, off the emitted mesh, using none of the generator's variables: slice the STL at a
ladder of z heights, find the ENCLOSED VOID at each height, and take the largest circle that fits
inside it. That is a measured channel, centre c(z) and radius r(z), derived from triangles alone.

WHAT THIS DOES NOT ANSWER, learned by misusing it twice in one night. It measures a THROUGH
CHANNEL ALONG Z: it slices horizontally and asks whether one straight line stays inside the
enclosed void at every height. So it is the wrong tool for:
  - a BLIND socket, which has no void above its floor. branch_sleeve reports "no enclosed void at
    3 of 60 heights" and that is correct and meaningless: its sockets are blind holes entered from
    the X faces, and the right questions there are depth and entry, not transit.
  - a bore that runs along X or Y. Reorient the mesh first or the answer is about the wrong axis.
  - a part measured against the wrong mating diameter. Feeding a stock O52 spigot to a SLIM brace
    built for O43.7 produced a confident FAIL that was entirely the operator's error.
Both mistakes were mine, both looked like real defects, and neither was. Check the axis and check
the pair before believing a verdict from this file.

THE CRITERION. A rigid straight part has a straight axis, so it threads the channel if and only if
SOME straight line stays inside the channel over the whole height:

    exists p, d  with  |(p + z*d) - c(z)|  <=  r(z) - shrink/2 - part_d/2   at every z

End state and transit are the same question here: once such a line exists, sliding the part along
that very line works, because at every partial insertion it occupies a sub-interval of constraints
it already satisfies. A straight bore with a fat part is the easy case. The case that shipped is a
channel whose CENTRELINE MOVES SIDEWAYS. No straight line follows a bent path, so the sideways move
is paid for out of clearance, and 1.54mm of move cannot be paid out of 0.55mm of room.

TWO VERDICT ROUTES, which are not the same strength and are labelled as such:

  BLOCKED     some z has no enclosed void at all, or a void smaller than the part. Nothing to argue.
  IMPOSSIBLE  a proof. For any three heights, an affine axis forces
                  |c_j - chord(c_i, c_k)|  <=  (1-t)*clear_i + clear_j + t*clear_k,  t = the z ratio
              so a triple that breaks it proves NO line exists, at any spacing, at any bore size.
  THREADS     a witness. A line is constructed, then verified against every measured slab.

The gate refuses anything that is not a verified THREADS, and prints which route it took. "All
triples pass but no witness was found" is reported as a FAIL and explicitly NOT called a proof.

CONSERVATIVE BY CONSTRUCTION. The void is modelled as its largest inscribed circle, so a non-round
channel is credited with less room than it really has, and the shrink and the fattest part in the
batch are both charged against it. It fails safe rather than loose. The z ladder IS a sampling: a
pinch thinner than --step can hide between slabs, so step is an argument and it is printed.

Usage:
    python3 transit.py part.stl [--part-dia 6.2] [--shrink 0.25] [--step 2] [--at X,Y] [-v]
    python3 transit.py --self-test          # proves the measurement on geometry with known answers
"""
import argparse
import math
import os
import struct
import sys

# Printed holes come out UNDER the model. PROVENANCE: solid.py:44 SHRINK = 0.25, "printed = model
# - 0.25", confirmed by Oleg at 6mm on a metal shaft 2026-07-25; the same 0.25 is the figure the
# bore retrospective uses for the 7.0 bamboo bore. It is NOT measured on a printed 7mm bamboo bore,
# and rod_constants.py carries no shrink figure to import. Override with --shrink when you have one.
HOLE_SHRINK = 0.25

CELL = 0.3        # mm, section grid pitch. Only has to FIND the void; the radius is then refined.
SLABS = 60        # default z samples across the part height
STEP_MIN = 0.4    # mm, floor on the z ladder pitch


def rod_constants():
    """The rod truth lives in bamboo/rod_constants.py and is never retyped here. Imported lazily so
    a part that is not a bamboo part can still be checked with an explicit --part-dia."""
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "bamboo")
    if d not in sys.path:
        sys.path.insert(0, d)
    import rod_constants
    return rod_constants


# ---------------------------------------------------------------- mesh -> sections

def load_tris(path):
    """Binary STL -> [(v0, v1, v2)]. Stored normals ignored; only vertices are trusted."""
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        body = f.read()
    tris = [(r[3:6], r[6:9], r[9:12]) for r in struct.iter_unpack("<12fH", body)]
    if len(tris) != n:
        raise ValueError("%s: header says %d triangles, body holds %d" % (path, n, len(tris)))
    return tris


def _buckets(tris, z0, step):
    """Triangles indexed by the z band they span, so a section only tests its own candidates."""
    b = {}
    for t in tris:
        lo = min(v[2] for v in t)
        hi = max(v[2] for v in t)
        for k in range(int(math.floor((lo - z0) / step)), int(math.floor((hi - z0) / step)) + 1):
            b.setdefault(k, []).append(t)
    return b


def section(cands, z):
    """Cross-section segments at plane z. Half-open vertex rule (vertex z >= z counts ABOVE), so a
    vertex sitting exactly on the plane cannot produce an odd crossing count."""
    segs = []
    for tri in cands:
        pts = []
        for i in range(3):
            p, q = tri[i], tri[(i + 1) % 3]
            if (p[2] >= z) == (q[2] >= z):
                continue
            f = (z - p[2]) / (q[2] - p[2])
            pts.append((p[0] + f * (q[0] - p[0]), p[1] + f * (q[1] - p[1])))
        if len(pts) == 2:
            (x0, y0), (x1, y1) = pts
            if (x0 - x1) ** 2 + (y0 - y1) ** 2 > 1e-18:
                segs.append((x0, y0, x1, y1))
    return segs


def _d_seg(px, py, s):
    x0, y0, x1, y1 = s
    dx, dy = x1 - x0, y1 - y0
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 <= 0.0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / l2))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def _d_all(px, py, segs, cutoff=None):
    """Distance from (px, py) to the nearest segment.

    With a `cutoff`, the scan stops as soon as it can prove the answer is at or below it. The caller
    then knows one thing for certain: a value ABOVE the cutoff never exited early, so it IS the true
    distance. _inscribe only ever asks "is this point further out than the one I have", so that is
    the whole question, and answering it lets most probes quit after a segment or two. Called with
    no cutoff it scans every segment, exactly as before."""
    best = float("inf")
    for s in segs:
        d = _d_seg(px, py, s)
        if d < best:
            best = d
            if cutoff is not None and best <= cutoff:
                return best
    return best


def _voids(segs, cell):
    """Enclosed voids of one section: grid the bbox, classify material by even-odd scanline, flood
    the air in from the border, and keep the air that the flood never reached. Returns a list of
    cell lists, largest first. A hole is enclosed by definition of not touching the border."""
    xs = [v for s in segs for v in (s[0], s[2])]
    ys = [v for s in segs for v in (s[1], s[3])]
    x0, x1 = min(xs) - 2 * cell, max(xs) + 2 * cell
    y0, y1 = min(ys) - 2 * cell, max(ys) + 2 * cell
    nx = int((x1 - x0) / cell) + 1
    ny = int((y1 - y0) / cell) + 1
    if nx * ny > 4_000_000:
        raise ValueError("section grid %dx%d too fine for this bbox; raise --cell" % (nx, ny))

    air = [[True] * nx for _ in range(ny)]
    for iy in range(ny):
        yv = y0 + (iy + 0.5) * cell
        xc = []
        for (sx0, sy0, sx1, sy1) in segs:
            if (sy0 > yv) != (sy1 > yv):
                xc.append(sx0 + (yv - sy0) * (sx1 - sx0) / (sy1 - sy0))
        if not xc:
            continue
        xc.sort()
        row = air[iy]
        for ix in range(nx):
            xv = x0 + (ix + 0.5) * cell
            lo, hi = 0, len(xc)
            while lo < hi:                       # crossings strictly right of xv, parity = inside
                mid = (lo + hi) // 2
                if xc[mid] <= xv:
                    lo = mid + 1
                else:
                    hi = mid
            if (len(xc) - lo) & 1:
                row[ix] = False

    seen = [[False] * nx for _ in range(ny)]
    stack = []
    for ix in range(nx):
        for iy in (0, ny - 1):
            if air[iy][ix] and not seen[iy][ix]:
                seen[iy][ix] = True
                stack.append((ix, iy))
    for iy in range(ny):
        for ix in (0, nx - 1):
            if air[iy][ix] and not seen[iy][ix]:
                seen[iy][ix] = True
                stack.append((ix, iy))
    while stack:
        ix, iy = stack.pop()
        for jx, jy in ((ix + 1, iy), (ix - 1, iy), (ix, iy + 1), (ix, iy - 1)):
            if 0 <= jx < nx and 0 <= jy < ny and air[jy][jx] and not seen[jy][jx]:
                seen[jy][jx] = True
                stack.append((jx, jy))

    holes = []
    for iy in range(ny):
        for ix in range(nx):
            if not air[iy][ix] or seen[iy][ix]:
                continue
            comp = []
            seen[iy][ix] = True
            stack = [(ix, iy)]
            while stack:
                ax, ay = stack.pop()
                comp.append((x0 + (ax + 0.5) * cell, y0 + (ay + 0.5) * cell))
                for jx, jy in ((ax + 1, ay), (ax - 1, ay), (ax, ay + 1), (ax, ay - 1)):
                    if 0 <= jx < nx and 0 <= jy < ny and air[jy][jx] and not seen[jy][jx]:
                        seen[jy][jx] = True
                        stack.append((jx, jy))
            holes.append(comp)
    holes.sort(key=len, reverse=True)
    return holes


# 16 directions, 22.5 deg apart. Four (+-x, +-y) is what stalled; see _inscribe. Same table
# bore_probe._inscribe_hard has searched with since 2026-08-03.
DIRS16 = [(math.cos(2 * math.pi * i / 16), math.sin(2 * math.pi * i / 16)) for i in range(16)]

# A move must GAIN something real to count as one. Accepting a 1e-16 gain keeps `moved` true
# forever, the step never halves, and the search walks a ridge until it is killed -- what this same
# 16-direction loop did for 12 minutes on a near-degenerate section in bore_probe (2026-08-03).
# 1e-9 mm sits three orders below the 1e-6 mm step the loop stops at, so it cannot cost accuracy.
INSCRIBE_GAIN = 1e-9


def _inscribe(comp, segs, cell):
    """Largest circle inside one void: best of a subsampled coarse scan, then a shrinking pattern
    search over 16 directions. Every step is capped at the current radius, so the search cannot hop
    a thin wall into a neighbouring void and report its room instead.

    Sixteen directions, not four. With two walls binding at once the directions that improve on both
    form a wedge, and stepping only +-x and +-y puts every step exactly ON that wedge's edge when the
    two walls are orthogonal AND square to the search axes: each move gains on one wall and loses on
    the other, the minimum never improves, and the search calls itself converged. Inside an
    axis-aligned 7.00 mm square bore it stops at (-0.250, -0.250) r=3.250 against a true 3.500 --
    0.5 mm lost on diameter (bore_probe selftest case 28, which now fails if that comes back). A
    45 deg step is strictly inside the wedge and gains on both walls at once.

    Measured 2026-08-03, so the size of the thing is on the record rather than assumed: it is the
    ALIGNMENT that stalls, not the flat. The same square rotated 1 deg came out 0.00005 mm short,
    and a 12x7 slot 0.00005 mm, because only one pair of walls binds there. Axis-aligned is how
    parts are modelled, which is why a narrow trigger was still worth 0.5 mm. Sixteen directions
    leave a stall possible only where the wedge is under 22.5 deg wide, i.e. two walls within
    22.5 deg of opposite -- the middle of a slot, where the radius is right anyway.

    Round bores are unaffected: across 120 voids of transit's own round fixtures this returns the
    64-gon's true apothem to within 0.6 nm, against 71.6 nm for the four-direction search."""
    stride = max(1, len(comp) // 120)
    px, py, d = comp[0][0], comp[0][1], -1.0
    for k in range(0, len(comp), stride):
        cx, cy = comp[k]
        if _d_all(cx, cy, segs, cutoff=d) <= d:
            continue
        px, py, d = cx, cy, _d_all(cx, cy, segs)
    # The centre of a circle inscribed in this void lies inside the void, so inside the bbox of the
    # void's own cells. comp holds cell CENTRES, so the void itself reaches at most half a cell past
    # them and this +-cell margin is looser than that bound: it cannot exclude a real answer. What
    # it stops is a gaining direction marching a one-cell void's centre away from the section for
    # good, which is how the 16-direction loop first ran away in bore_probe.
    xs = [c[0] for c in comp]
    ys = [c[1] for c in comp]
    x0, x1 = min(xs) - cell, max(xs) + cell
    y0, y1 = min(ys) - cell, max(ys) + cell
    # Where the search STOPS is part of what it measures. At the old 1e-4 mm floor the returned
    # radius sat up to 1e-4 short of the true one and where it landed inside that window depended on
    # the path: on the 64-gon fixtures the 4-direction search scattered 3..65 nm under the apothem
    # and the 16-direction one 50..74 nm, so a floor change would have looked like a regression that
    # was only ever the floor. 1e-6 mm puts both a thousand times under the 1e-3 mm last printed
    # digit, and the two searches then agree on round bores to every digit a verdict shows.
    step = cell
    rounds = 0
    while step > 1e-6:
        rounds += 1
        if rounds > 2000:
            raise ValueError("_inscribe did not converge in 2000 rounds at a void of bbox "
                             "%.3f x %.3f. The circle it has is real but may not be the largest, "
                             "and a bore that quietly under-reports is how a part that cannot be "
                             "threaded passes." % (x1 - x0 - 2 * cell, y1 - y0 - 2 * cell))
        step = min(step, max(d, 1e-6))
        moved = False
        for ux, uy in DIRS16:
            nx_, ny_ = px + ux * step, py + uy * step
            if not (x0 <= nx_ <= x1 and y0 <= ny_ <= y1):
                continue
            nd = _d_all(nx_, ny_, segs, cutoff=d + INSCRIBE_GAIN)
            if nd <= d + INSCRIBE_GAIN:
                continue
            px, py, d = nx_, ny_, nd
            moved = True
        if not moved:
            step *= 0.5
    return px, py, d


def channel(tris, step, cell=CELL, seed=None):
    """Measure the channel: [(z, cx, cy, r)] plus the z heights where no enclosed void exists.

    The channel is followed by continuity: the void nearest the previous slab's centre, seeded by
    the largest void at the bottom slab (or by the void nearest `seed` if one is given). A part with
    two separate bores therefore reports on ONE of them; pass --at to pick the other."""
    zlo = min(v[2] for t in tris for v in t)
    zhi = max(v[2] for t in tris for v in t)
    buck = _buckets(tris, zlo, step)
    slabs, blocked, multi = [], [], 0
    prev = seed
    z = zlo + 0.5 * step
    while z < zhi:
        segs = section(buck.get(int(math.floor((z - zlo) / step)), ()), z)
        holes = _voids(segs, cell) if segs else []
        if not holes:
            blocked.append(z)
            z += step
            continue
        if len(holes) > 1:
            multi += 1
        cand = [_inscribe(h, segs, cell) for h in holes]
        if prev is None:
            cx, cy, r = max(cand, key=lambda c: c[2])
        else:
            cx, cy, r = min(cand, key=lambda c: math.hypot(c[0] - prev[0], c[1] - prev[1]))
        slabs.append((z, cx, cy, r))
        prev = (cx, cy)
        z += step
    return slabs, blocked, multi


# ---------------------------------------------------------------- the transit question

def worst_triple(slabs, clears):
    """The strongest 3-slab infeasibility proof. For an affine axis a(z) and errors e = a - c,
        e_j = (1-t) e_i + t e_k - v,  v = c_j - chord(c_i, c_k),  t = (z_j-z_i)/(z_k-z_i)
    so |v| <= (1-t)|e_i| + |e_j| + t|e_k| <= (1-t)clear_i + clear_j + t*clear_k. A triple breaking
    that has NO straight-line solution, and no other triple can rescue it.
    Returns (excess, i, j, k, dev, budget); excess > 0 means proven impossible."""
    n = len(slabs)
    best = (float("-inf"), 0, 0, 0, 0.0, 0.0)
    for i in range(n):
        zi, xi, yi, _ = slabs[i]
        for k in range(i + 2, n):
            zk, xk, yk, _ = slabs[k]
            dz = zk - zi
            if dz <= 1e-9:
                continue
            for j in range(i + 1, k):
                zj, xj, yj, _ = slabs[j]
                t = (zj - zi) / dz
                dev = math.hypot(xj - (xi + t * (xk - xi)), yj - (yi + t * (yk - yi)))
                budget = (1.0 - t) * clears[i] + clears[j] + t * clears[k]
                if dev - budget > best[0]:
                    best = (dev - budget, i, j, k, dev, budget)
    return best


def fit_axis(slabs, clears, sweeps=6000):
    """Find an axis line that stays inside every slab's clearance disc, by cyclic projection onto
    the constraint discs (POCS: each set is convex, so the sweep converges into their intersection
    when one exists). Least-squares seed. Returns (px, py, dx, dy, margin) where the margin is
    RE-MEASURED against every slab afterwards; the fit is never trusted on its own report."""
    n = len(slabs)
    zm = sum(s[0] for s in slabs) / n
    zc = [s[0] - zm for s in slabs]
    szz = sum(z * z for z in zc)
    px = sum(s[1] for s in slabs) / n
    py = sum(s[2] for s in slabs) / n
    dx = sum(zc[i] * slabs[i][1] for i in range(n)) / szz if szz > 1e-12 else 0.0
    dy = sum(zc[i] * slabs[i][2] for i in range(n)) / szz if szz > 1e-12 else 0.0

    def margin():
        m = float("inf")
        for i in range(n):
            e = math.hypot(px + zc[i] * dx - slabs[i][1], py + zc[i] * dy - slabs[i][2])
            m = min(m, clears[i] - e)
        return m

    for _ in range(sweeps):
        if margin() >= 0.0:
            break
        for i in range(n):
            ex = px + zc[i] * dx - slabs[i][1]
            ey = py + zc[i] * dy - slabs[i][2]
            e = math.hypot(ex, ey)
            if e <= clears[i] or e < 1e-15:
                continue
            f = (1.0 - clears[i] / e) / (1.0 + zc[i] * zc[i])
            px -= f * ex
            py -= f * ey
            dx -= f * zc[i] * ex
            dy -= f * zc[i] * ey
    return px, py, dx, dy, margin()


def check(path, part_dia, shrink=HOLE_SHRINK, step=None, cell=CELL, seed=None):
    """THE gate call. Can a rigid straight part of diameter `part_dia` pass through this mesh?

    Returns a dict: ok, route (BLOCKED/IMPOSSIBLE/NO-WITNESS/THREADS), msg (one line for qa_stl),
    detail (report lines), and the measured numbers."""
    tris = load_tris(path)
    if not tris:
        return {"ok": False, "route": "BLOCKED", "msg": "no triangles, nothing to pass through",
                "detail": [], "slabs": []}
    zlo = min(v[2] for t in tris for v in t)
    zhi = max(v[2] for t in tris for v in t)
    if step is None:
        step = max(STEP_MIN, (zhi - zlo) / SLABS)

    slabs, blocked, multi = channel(tris, step, cell, seed)
    part_r = part_dia / 2.0
    detail = ["measured off %s: %d triangles, z %.2f..%.2f, %d slabs at %.2fmm pitch"
              % (os.path.basename(path), len(tris), zlo, zhi, len(slabs), step),
              "part O%.2f (worst case), printed hole = model - %.2f, so room = "
              "2*(r_slab - %.3f) - %.2f" % (part_dia, shrink, shrink / 2.0, part_dia)]
    if multi:
        detail.append("%d slab(s) held more than one enclosed void; followed the one continuous "
                      "with the bottom slab (use --at to pick another)" % multi)

    out = {"ok": False, "route": "BLOCKED", "slabs": slabs, "step": step,
           "part_dia": part_dia, "shrink": shrink, "detail": detail}

    if not slabs:
        out["msg"] = ("no enclosed void at any of the %d sampled heights: this mesh has no channel "
                      "to pass through" % (len(blocked)))
        detail.append(out["msg"])
        return out
    if blocked:
        out["msg"] = ("channel BLOCKED: no enclosed void at %d of %d heights, first at z=%.2f"
                      % (len(blocked), len(blocked) + len(slabs), blocked[0]))
        detail.append(out["msg"])
        return out

    clears = [(r - shrink / 2.0) - part_r for (_z, _x, _y, r) in slabs]
    tight = min(range(len(clears)), key=lambda i: clears[i])
    zt, _xt, _yt, rt = slabs[tight]
    detail.append("tightest slab z=%.2f: void O%.3f measured, O%.3f printed, room %.3f mm around "
                  "a O%.2f part" % (zt, 2 * rt, 2 * rt - shrink, 2 * clears[tight], part_dia))
    if clears[tight] < 0.0:
        out["route"] = "BLOCKED"
        out["msg"] = ("BLOCKED at z=%.2f: the channel prints O%.3f and the part is O%.2f, short by "
                      "%.3f mm before any centreline question" % (zt, 2 * rt - shrink, part_dia,
                                                                 -2 * clears[tight]))
        detail.append(out["msg"])
        return out

    exc, i, j, k, dev, budget = worst_triple(slabs, clears)
    zi, xi, yi, _ = slabs[i]
    zj, xj, yj, _ = slabs[j]
    zk, xk, yk, _ = slabs[k]
    detail.append("worst triple z=%.2f / %.2f / %.2f: the centreline sits %.3f mm off the straight "
                  "chord, and the three slabs together can only pay %.3f mm"
                  % (zi, zj, zk, dev, budget))
    if exc > 0.0:
        out["route"] = "IMPOSSIBLE"
        out["msg"] = ("IMPOSSIBLE: no straight line threads this channel. At z=%.2f the centreline "
                      "is %.3f mm off the chord through z=%.2f and z=%.2f, which have only %.3f mm "
                      "of room to pay it. Short by %.3f mm. Proof, not a margin: a rigid O%.2f part "
                      "cannot bend to follow the bore."
                      % (zj, dev, zi, zk, budget, exc, part_dia))
        detail.append(out["msg"])
        return out

    px, py, dx, dy, margin = fit_axis(slabs, clears)
    zm = sum(s[0] for s in slabs) / len(slabs)
    if margin < 0.0:
        out["route"] = "NO-WITNESS"
        out["msg"] = ("NO WITNESS: no triple proves it impossible, but no axis line was found that "
                      "clears every slab (best line still %.3f mm short). Refused, and this is NOT "
                      "a proof of impossibility." % (-margin))
        detail.append(out["msg"])
        return out

    tiltx, tilty = dx * 1000.0, dy * 1000.0
    out["ok"] = True
    out["route"] = "THREADS"
    out["margin"] = margin
    out["msg"] = ("THREADS: a O%.2f part passes on a verified axis (x=%.3f%+.3f, y=%.3f%+.3f per "
                  "mm about z=%.2f), tightest point %.3f mm of side room to spare at z=%.2f"
                  % (part_dia, px, dx, py, dy, zm, margin, zt))
    detail.append("witness axis tilts %.2f / %.2f mm per 1000mm of z; verified against all %d slabs"
                  % (tiltx, tilty, len(slabs)))
    detail.append(out["msg"])
    return out


# ---------------------------------------------------------------- probe self-test

def _tube_stl(path, r_bore, r_out, height, offset=0.0, n=64, steps=40):
    """A straight or laterally kinked tube with EXACTLY known bore. The bore centre runs
    0 -> offset -> 0 over the height, which is the bend guide's own construction."""
    def cen(z):
        h = height / 2.0
        return offset * (z / h) if z <= h else offset * ((height - z) / h)

    def ring(cx, r):
        return [(cx + r * math.cos(2 * math.pi * q / n), r * math.sin(2 * math.pi * q / n))
                for q in range(n)]

    zs = [height * s / steps for s in range(steps + 1)]
    lv = [(z, ring(cen(z), r_bore), ring(0.0, r_out)) for z in zs]
    tris = []
    for a in range(len(lv) - 1):
        z0, i0, o0 = lv[a]
        z1, i1, o1 = lv[a + 1]
        for q in range(n):
            w = (q + 1) % n
            tris += [((*o0[q], z0), (*o0[w], z0), (*o1[w], z1)),
                     ((*o0[q], z0), (*o1[w], z1), (*o1[q], z1)),
                     ((*i0[q], z0), (*i0[w], z0), (*i1[w], z1)),
                     ((*i0[q], z0), (*i1[w], z1), (*i1[q], z1))]
    for (zc, ii, oo), up in ((lv[0], False), (lv[-1], True)):
        for q in range(n):
            w = (q + 1) % n
            A, B, C, D = (*oo[q], zc), (*oo[w], zc), (*ii[q], zc), (*ii[w], zc)
            tris += [(A, B, D), (A, D, C)] if up else [(A, D, B), (A, C, D)]
    with open(path, "wb") as f:
        f.write(b"transit self-test tube".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            for v in (a, b, c):
                f.write(struct.pack("<3f", *v))
            f.write(struct.pack("<H", 0))
    return path


def self_test(tmp=None):
    """Prove the MEASUREMENT before trusting any verdict it feeds. Every case declares the answer
    from the construction, and the probe has to recover it off the emitted bytes. Returns the
    number of failures; a probe that reports success and never errors is exactly the trap here."""
    import tempfile
    tmp = tmp or tempfile.mkdtemp(prefix="transit-selftest-")
    bad = 0

    def ck(name, ok, msg):
        nonlocal bad
        if not ok:
            bad += 1
        print("  %s %-26s %s" % ("PASS" if ok else "FAIL", name, msg))

    # 1 straight tube: the measured bore must BE the modelled bore, everywhere
    p = _tube_stl(os.path.join(tmp, "straight.stl"), 3.5, 7.45, 60.0)
    slabs, blocked, _ = channel(load_tris(p), step=2.0)
    rs = [s[3] for s in slabs]
    offs = [math.hypot(s[1], s[2]) for s in slabs]
    ck("straight radius", abs(max(rs) - 3.5) < 0.02 and abs(min(rs) - 3.5) < 0.02,
       "measured r %.4f..%.4f vs modelled 3.5000 (%d slabs, %d blocked)"
       % (min(rs), max(rs), len(slabs), len(blocked)))
    ck("straight centreline", max(offs) < 0.02,
       "centre wanders %.4f mm off the axis, modelled 0" % max(offs))

    # 2 kinked tube: the measured centreline must recover the modelled offset
    p = _tube_stl(os.path.join(tmp, "kink.stl"), 3.5, 9.0, 60.0, offset=1.55)
    slabs, _b, _m = channel(load_tris(p), step=1.0)
    peak = max(slabs, key=lambda s: abs(s[1]))
    ck("kink offset recovered", abs(abs(peak[1]) - 1.55) < 0.03,
       "measured peak offset %.4f mm at z=%.2f vs modelled 1.5500" % (abs(peak[1]), peak[0]))

    # 3 verdicts, both directions, on geometry whose answer is arithmetic
    v = check(_tube_stl(os.path.join(tmp, "good.stl"), 3.5, 7.45, 60.0), 6.2)
    ck("straight tube THREADS", v["ok"] and v["route"] == "THREADS", v["msg"])
    v = check(_tube_stl(os.path.join(tmp, "kinked.stl"), 3.5, 9.0, 60.0, offset=1.55), 6.2)
    ck("kinked tube IMPOSSIBLE", (not v["ok"]) and v["route"] == "IMPOSSIBLE", v["msg"])

    # 4 a bore narrower than the part is caught before any centreline argument
    v = check(_tube_stl(os.path.join(tmp, "narrow.stl"), 2.9, 7.0, 40.0), 6.2)
    ck("narrow bore BLOCKED", (not v["ok"]) and v["route"] == "BLOCKED", v["msg"])

    # 5 a solid bar has no channel at all
    v = check(_tube_stl(os.path.join(tmp, "solidish.stl"), 0.35, 7.0, 40.0), 6.2)
    ck("no channel BLOCKED", (not v["ok"]) and v["route"] == "BLOCKED", v["msg"])

    # 6 the boundary: offset exactly at, and just over, the room the arithmetic allows.
    #   room = 2*(3.5 - 0.125) - 6.2 = 0.55, so 0.50 must thread and 0.60 must not.
    v = check(_tube_stl(os.path.join(tmp, "edge_lo.stl"), 3.5, 9.0, 60.0, offset=0.50), 6.2)
    ck("offset 0.50 < room 0.55", v["ok"], v["msg"])
    v = check(_tube_stl(os.path.join(tmp, "edge_hi.stl"), 3.5, 9.0, 60.0, offset=0.60), 6.2)
    ck("offset 0.60 > room 0.55", not v["ok"], v["msg"])

    print("  self-test: %d failure(s), fixtures in %s" % (bad, tmp))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stl", nargs="*", help="binary STL(s) with a channel something must pass")
    ap.add_argument("--part-dia", type=float, default=None,
                    help="diameter of the rigid part that must pass. Default: ROD_MAX from "
                         "bamboo/rod_constants.py, the FATTEST stick in the batch")
    ap.add_argument("--shrink", type=float, default=HOLE_SHRINK,
                    help="printed hole undersize vs model, mm on diameter (default %g)" % HOLE_SHRINK)
    ap.add_argument("--step", type=float, default=None,
                    help="z ladder pitch in mm (default: height/%d, floor %g)" % (SLABS, STEP_MIN))
    ap.add_argument("--cell", type=float, default=CELL,
                    help="section grid pitch in mm (default %g)" % CELL)
    ap.add_argument("--at", default=None, metavar="X,Y",
                    help="seed the channel at this xy instead of the largest void at the bottom")
    ap.add_argument("-v", "--verbose", action="store_true", help="print the measured slab ladder")
    ap.add_argument("--self-test", action="store_true",
                    help="measure geometry with known answers and check the probe recovers them")
    a = ap.parse_args()

    if a.self_test:
        print("== transit.py probe self-test ==")
        sys.exit(1 if self_test() else 0)
    if not a.stl:
        ap.error("give at least one STL, or --self-test")

    dia = a.part_dia
    src = "--part-dia"
    if dia is None:
        dia = rod_constants().ROD_MAX
        src = "rod_constants.ROD_MAX"
    seed = tuple(float(v) for v in a.at.split(",")) if a.at else None

    failed = 0
    for path in a.stl:
        print("== %s [transit O%.2f from %s] ==" % (path, dia, src))
        v = check(path, dia, shrink=a.shrink, step=a.step, cell=a.cell, seed=seed)
        for line in v["detail"][:-1]:
            print("   " + line)
        if a.verbose:
            for (z, cx, cy, r) in v["slabs"]:
                print("   z=%8.3f  centre (%7.3f, %7.3f)  void O%.3f  room %+.3f"
                      % (z, cx, cy, 2 * r, 2 * ((r - a.shrink / 2.0) - dia / 2.0)))
        print("%s TRANSIT   %s" % ("PASS" if v["ok"] else "FAIL", v["msg"]))
        if not v["ok"]:
            failed += 1
    if failed:
        print("FAIL transit: %d of %d file(s) cannot be threaded" % (failed, len(a.stl)))
        sys.exit(1)
    print("PASS transit: %d file(s) threadable" % len(a.stl))
    sys.exit(0)


if __name__ == "__main__":
    main()
