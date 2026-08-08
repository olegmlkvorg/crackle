#!/usr/bin/env python3
"""ART BUCKET — a bucket whose wall follows a traced silhouette, with a second silhouette cut
into the floor and walled at its own height.

Oleg, 2026-08-08: "lets now make outer shape as pikachu and inner hole in the bottom as other
shape of pikachu ... we want abound 20% of floor only as solid brim and rest used for the art",
then "since we are having the middle cut, lets have walls there as well but only 2 inch, while
outer wall is 6 inch". Plan D approved off tools/art_bucket_plan.py's render the same day.

WHAT THIS FILE IS. bucket_towers.py's system on an arbitrary outline: single-wall C-channel
posts placed by tools/art_bucket_plan.py (ONE implementation of trace/placement/mouth-solve --
imported, never copied), fabric crossings tip to tip, merge laps, the v16 bridge schedule, and
a floor that is brim lap-rings + an open hatch net + the art hole with its own walled ring.
Every law here is the accepted v16 bucket's, cited from machine.PROVEN_* -- nothing new is
asserted, and the two genuinely new quantities (the layer-1 net pitch, the transit strands)
are DECLARED as unproven in the header rather than smuggled.

THE TOOL IS GENERIC: any two silhouette PNGs. Character art used as input is third-party IP --
inputs and outputs stay in gitignored out/, and a part built from one is for the household,
never a shop page. The header carries sha256 of both PNGs because the CMD's paths point into
a gitignored directory: without the hash a regenerated part cannot prove it used the same art.

Usage:
  python3 art_bucket.py --outer out/A.png --hole out/B.png --size 330 --pitch 32 \
          --smooth 8 --dilate 7 --hole-frac 0.7 --cite-coupon out/zladder_... --coupon-read ...
  python3 validate.py out/art_bucket_*.gcode        # must pass
  python3 tools/qa_weld.py out/art_bucket_*.gcode   # must pass (art-geometry branch)
"""
import argparse, hashlib, math, os, shlex, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
import machine
import bucket_latch as latch
import art_bucket_plan as plan

from shapely.geometry import Polygon, LineString, Point, MultiPolygon
from shapely.ops import unary_union

A_FIL = machine.A_FIL
SEG = 1.0
FLOOR1_OVERLAP = 0.80          # the lap law -- the only floor ratio that has ever welded
PROVEN_AIR_MM = machine.PROVEN_AIR_MM


# ------------------------------------------------------------------------- ring geometry
def tips_of(c, mu, r_t, toff):
    """(leading, trailing) tips of a post: mouth centred at absolute angle mu, tips flank it."""
    lead = (c[0] + r_t * math.cos(mu + toff), c[1] + r_t * math.sin(mu + toff))
    trail = (c[0] + r_t * math.cos(mu - toff), c[1] + r_t * math.sin(mu - toff))
    return lead, trail


def arc_pts(c, r_t, a0, sweep, seg):
    """Arc from angle a0 through `sweep` (signed), EXCLUDING the start point."""
    n = max(2, int(math.ceil(abs(sweep) * r_t / seg)))
    return [(c[0] + r_t * math.cos(a0 + sweep * i / n),
             c[1] + r_t * math.sin(a0 + sweep * i / n)) for i in range(1, n + 1)]


def post_arc(c, mu, r_t, wrap_rad, toff, seg, frm=None, to=None):
    """The post's material arc walked trailing -> leading THROUGH the material (CW sweep of
    -wrap), optionally only a sub-span [frm..to] given as absolute angles ON that walk.
    Excludes the start point, ends exactly on the tip (or `to`)."""
    a_start = mu - toff if frm is None else frm
    a_end = mu + toff - 2 * math.pi if to is None else to
    # walk CW (decreasing angle) from a_start to a_end
    sweep = a_end - a_start
    while sweep > 1e-12:
        sweep -= 2 * math.pi
    pts = arc_pts(c, r_t, a_start, sweep, seg)
    end = (c[0] + r_t * math.cos(a_end), c[1] + r_t * math.sin(a_end))
    pts[-1] = end
    return pts


# THE GRAZE LAW, with its provenance. A crossing may touch the post it DEPARTS FROM or LANDS
# ON by up to GRAZE_MM, within GRAZE_NEAR_MM of that tip: the strand hugging the bead corner
# it is welded to is a micro merge-lap, not a plough -- the merge feature deliberately runs
# material along that exact zone. 0.05 is tools/qa_weld.py's own weld MARGIN, the depth below
# which this project already treats bead contact as sub-physical (beads land narrower than
# commanded by more than this). Everything else -- a third post anywhere, an own post beyond
# the tip zone -- is refused at 1e-9, exactly bucket_towers' standard. Measured before this
# law existed: every solver residual (0.002-0.004mm) sat in the own-tip zone, and no mouth
# rotation, pairwise sweep, phase or slide could clear the last of them, because a chord
# leaving a concave stretch ALWAYS leans on its own tip.
GRAZE_MM = 0.05
GRAZE_NEAR_MM = 3.0


def seg_dip(p, q, cs, mus, r_t, half_rad, n=512, skip=(), own_p=None, own_q=None):
    """Worst EXCESS penetration of segment p->q into any post's MATERIAL sector, under the
    graze law above: own-tip grazes are allowed GRAZE_MM, everything else 1e-9. 0.0 = clears.
    `own_p`/`own_q` are indices (into cs) of the posts the segment departs from / lands on."""
    worst, at = 0.0, None
    for j, (c, mu) in enumerate(zip(cs, mus)):
        if j in skip:
            continue
        # cheap reject: segment bbox vs post circle
        if (max(p[0], q[0]) < c[0] - r_t - 1 or min(p[0], q[0]) > c[0] + r_t + 1
                or max(p[1], q[1]) < c[1] - r_t - 1 or min(p[1], q[1]) > c[1] + r_t + 1):
            continue
        for i in range(n + 1):
            t = i / n
            x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
            r = math.hypot(x - c[0], y - c[1])
            if r >= r_t - 1e-9:
                continue
            off = (math.atan2(y - c[1], x - c[0]) - (mu + math.pi)) % (2 * math.pi)
            off = off - 2 * math.pi if off > math.pi else off
            if abs(off) <= half_rad + 1e-12:
                allow = 0.0
                if j == own_p and math.hypot(x - p[0], y - p[1]) <= GRAZE_NEAR_MM:
                    allow = GRAZE_MM
                if j == own_q and math.hypot(x - q[0], y - q[1]) <= GRAZE_NEAR_MM:
                    allow = GRAZE_MM
                ex = (r_t - r) - allow
                if ex > worst:
                    worst, at = ex, j
    return worst, at


def ring_chords(cs, mus, r_t, toff):
    """Crossing chords: leading tip of k -> trailing tip of k+1."""
    n = len(cs)
    out = []
    for k in range(n):
        lead, _ = tips_of(cs[k], mus[k], r_t, toff)
        _, trail = tips_of(cs[(k + 1) % n], mus[(k + 1) % n], r_t, toff)
        out.append((lead, trail))
    return out


def place_and_solve(poly, pitch, r_t, half_rad, toff, label, flip=False):
    """Placement PHASE first, mouths second, refinement last. Where post 0 lands is an
    accident of where the trace started, and that accident parked a post astride a sharp
    corner that NO mouth rotation could clear (three-post full-range sweep bottomed at
    0.0875mm). Eight phases of the same count are tried; the least-violated greedy seed wins
    and is then refined to zero."""
    dd = np.hypot(*np.diff(poly, axis=0).T)
    total = float(dd.sum())
    n = max(6, int(round(total / pitch)))
    step = total / n
    best = None
    for ip in range(8):
        phase = step * ip / 8.0
        cs, ph = plan.ring_posts(poly, pitch, phase=phase)
        if flip:
            ph = np.array([p2 + math.pi for p2 in ph])
        stag, _, _ = plan.solve_ring(cs, ph)
        mus = [ph[i] + stag[i] for i in range(len(cs))]
        chs = ring_chords(cs, mus, r_t, toff)
        worst = tot = 0.0
        for kq, (p, q) in enumerate(chs):
            d, _ = seg_dip(p, q, list(map(tuple, cs)), mus, r_t, half_rad, n=128,
                           own_p=kq, own_q=(kq + 1) % len(cs))
            worst = max(worst, d)
            tot += d
        if best is None or (worst, tot) < best[0]:
            best = ((worst, tot), phase, cs, ph, stag)
        if worst <= 1e-12:
            break
    (_w, _), phase, cs, ph, stag = best
    print(f"  ~ {label} ring: phase {phase:.1f}mm of {step:.1f} seed worst dip {_w:.4f}")
    return refine_to_zero(poly, cs, ph, stag, r_t, half_rad, toff, pitch, label, phase=phase)


def refine_to_zero(poly, cs, ph, stag, r_t, half_rad, toff, pitch, label, phase=0.0):
    """Drive every crossing's material dip to ZERO, or refuse.

    The planner's greedy (+-40 deg, 5 deg steps) is the seed; the emitter's standard is
    bucket_towers' own: a chord that dips 1e-9 into a wall is refused, not reported. Three
    escalations, each measured: (1) finer/wider mouth sweep on offending neighbourhoods
    (+-62 deg, 1 deg); (2) sliding offending posts ALONG the outline (pitch is a maximum,
    not a promise -- the count is fixed, the spacing may breathe); (3) refuse with the
    offender named. Returns (cs, ph, stag) with zero dips."""
    cs = cs.copy()
    ph = ph.copy()
    stag = stag.copy()
    n = len(cs)
    # OPEN arc length, exactly as plan.ring_posts parameterises it, so a slide of zero is the
    # seed position bit for bit -- a closed-loop ss here would shift every post ~1mm.
    dd = np.hypot(*np.diff(poly, axis=0).T)
    ss = np.concatenate([[0], np.cumsum(dd)])
    onn = plan.normals(poly)

    def at_arc(s):
        s = s % ss[-1]
        j = min(np.searchsorted(ss, s), len(onn) - 1)
        c = np.array([np.interp(s, ss, poly[:, 0]), np.interp(s, ss, poly[:, 1])])
        return c, math.atan2(onn[j, 1], onn[j, 0])

    # arc position of each post (as placed by ring_posts: equal arc steps + phase)
    pos = (np.linspace(0, ss[-1], n, endpoint=False) + phase) % ss[-1]

    def mus():
        return [ph[i] + stag[i] for i in range(n)]

    def worst_all():
        ch = ring_chords(cs, mus(), r_t, toff)
        w = []
        for k, (p, q) in enumerate(ch):
            d, j = seg_dip(p, q, cs, mus(), r_t, half_rad, n=512,
                           own_p=k, own_q=(k + 1) % n)
            if d > 1e-9:
                w.append((d, k, j))
        return sorted(w, reverse=True)

    def local_cost(i):
        ch = ring_chords(cs, mus(), r_t, toff)
        tot = 0.0
        for k in (i - 2, i - 1, i, (i + 1) % n):
            d, _ = seg_dip(ch[k % n][0], ch[k % n][1], cs, mus(), r_t, half_rad, n=256,
                           own_p=k % n, own_q=(k + 1) % n)
            tot += d
        return tot

    for rnd in range(24):
        bad = worst_all()
        if not bad:
            return cs, ph, stag
        _, k, j = bad[0]
        # posts implicated: the chord's two ends and the post it dips into
        cand = sorted({k % n, (k + 1) % n, (j if j is not None else k) % n})
        improved = False
        for i in cand:
            best, bestc = stag[i], local_cost(i)
            for cnd in np.radians(np.arange(-62, 63, 1.0)):
                stag[i] = cnd
                c2 = local_cost(i)
                if c2 < bestc - 1e-12:
                    bestc, best = c2, cnd
            # sub-degree polish: a chord grazing a tip converges through minima the 1-degree
            # grid steps straight over (measured: 0.003mm residual on the first run)
            for cnd in best + np.radians(np.arange(-1.5, 1.55, 0.05)):
                stag[i] = cnd
                c2 = local_cost(i)
                if c2 < bestc - 1e-12:
                    bestc, best = c2, cnd
            if abs(best - stag[i]) > 1e-12:
                improved = True
            stag[i] = best
        if worst_all() and rnd >= 1:
            # PAIRWISE, FULL RANGE, MAX OBJECTIVE. The chord couples its two posts, and the
            # sum objective happily trades one chord's dip against another's -- feasibility
            # needs the WORST dip driven to zero. Measured before this existed: the joint
            # zero for chords 33-35 sat at (-30, -8) degrees while single sweeps parked at a
            # 0.004mm equilibrium and a +-6 window never saw it.
            i1, i2 = k % n, (k + 1) % n

            def pair_cost(nn=128):
                ch2 = ring_chords(cs, mus(), r_t, toff)
                worst2 = tot2 = 0.0
                for kk in (k - 2, k - 1, k, (k + 1) % n, (k + 2) % n):
                    d2, _ = seg_dip(ch2[kk % n][0], ch2[kk % n][1], cs, mus(), r_t,
                                    half_rad, n=nn, own_p=kk % n, own_q=(kk + 1) % n)
                    worst2 = max(worst2, d2)
                    tot2 += d2
                return worst2 + 0.01 * tot2

            for span, step in ((62.0, 2.0), (1.5, 0.1)):
                c1, c2v = stag[i1], stag[i2]
                bp = (c1, c2v, pair_cost(512 if span < 10 else 128))
                for d1 in np.radians(np.arange(-span, span + step / 2, step)):
                    for d2 in np.radians(np.arange(-span, span + step / 2, step)):
                        s1 = (c1 + d1) if span < 10 else d1
                        s2 = (c2v + d2) if span < 10 else d2
                        stag[i1], stag[i2] = s1, s2
                        cc = pair_cost(512 if span < 10 else 128)
                        if cc < bp[2] - 1e-12:
                            bp = (s1, s2, cc)
                if abs(bp[0] - c1) > 1e-12 or abs(bp[1] - c2v) > 1e-12:
                    improved = True
                stag[i1], stag[i2] = bp[0], bp[1]
        if worst_all() and rnd >= 4:
            # escalate: slide the implicated posts along the outline
            for i in cand:
                bestc = local_cost(i)
                best_s = pos[i]
                for dsl in np.arange(-0.30, 0.31, 0.05) * pitch:
                    c2p, phi2 = at_arc(pos[i] + dsl)
                    oc, oph = cs[i].copy(), ph[i]
                    cs[i], ph[i] = c2p, phi2
                    c2 = local_cost(i)
                    if c2 < bestc - 1e-12:
                        bestc, best_s = c2, pos[i] + dsl
                    cs[i], ph[i] = oc, oph
                if abs(best_s - pos[i]) > 1e-12:
                    cs[i], ph[i] = at_arc(best_s)
                    pos[i] = best_s % ss[-1]
                    improved = True
                    # re-sweep the slid post's mouth
                    bestc, best = local_cost(i), stag[i]
                    for cnd in np.radians(np.arange(-62, 63, 1.0)):
                        stag[i] = cnd
                        c2 = local_cost(i)
                        if c2 < bestc - 1e-12:
                            bestc, best = c2, cnd
                    stag[i] = best
        if not improved and rnd >= 8:
            break
    bad = worst_all()
    if bad:
        d, k, j = bad[0]
        raise SystemExit(
            f"REFUSING TO EMIT: {label} ring crossing {k}->{k+1} still dips {d:.3f}mm into post "
            f"{j}'s material after mouth sweeps and arc slides. The outline is too concave for "
            f"this pitch here -- raise --smooth / --dilate, or change --pitch.")
    return cs, ph, stag


# ------------------------------------------------------------------------- floor geometry
# THE FLOOR REGION IS THE INTERIOR RING OF THE MATERIAL CHAIN, and the third construction
# is the one that cannot lie. History, measured each time off the emitted plate:
#   1  a polygon DETOURING around each material arc -- its arc-vs-chord slivers
#      self-intersected and buffer(0)'s heal rewrote the border (18.5mm unwelded).
#   2  the tip polygon minus grown disks -- BOWTIES under big mouth rotations (a trailing
#      tip rotated past -90 deg flips the vertex order), heal again, rails retreating from
#      whole chords and the net region overshooting 3-4 rails deep into the brim (the 1300
#      pile spots were net strands crossing rails).
#   3  THIS: union every post disk (r_t) with every chord strip -- a valid closed CHAIN by
#      construction (union of valid geometries; endpoints touch the circles). The chain's
#      largest INTERIOR ring is the floor border exactly: inner faces of the material
#      circles + inner edges of the chords, notches included. Rails are then plain inward
#      buffers of that region -- distance d from chords AND feet everywhere, no healing,
#      nothing to bowtie.
def floor_region_outer(cs, mus, r_t, toff):
    chords = ring_chords(cs, mus, r_t, toff)
    chain = unary_union([Point(tuple(c)).buffer(r_t, quad_segs=48) for c in cs]
                        + [LineString(ch).buffer(0.05, quad_segs=8) for ch in chords])
    best = None
    for part in (chain.geoms if isinstance(chain, MultiPolygon) else [chain]):
        for ring in part.interiors:
            pl = Polygon(ring)
            if best is None or pl.area > best.area:
                best = pl
    if best is None:
        raise SystemExit("REFUSING TO EMIT: the outer material chain encloses no interior -- "
                         "the ring is not closed.")
    return best


def hole_region_inner(cs, mus, r_t, toff):
    """The cut plus its rim band, filled: the largest part's EXTERIOR ring of the inner
    chain. Outward buffers of this are the hole-ring rails."""
    chords = ring_chords(cs, mus, r_t, toff)
    chain = unary_union([Point(tuple(c)).buffer(r_t, quad_segs=48) for c in cs]
                        + [LineString(ch).buffer(0.05, quad_segs=8) for ch in chords])
    part = max((chain.geoms if isinstance(chain, MultiPolygon) else [chain]),
               key=lambda p: p.area)
    return Polygon(part.exterior)


def poly_parts(g):
    if g.is_empty:
        return []
    if isinstance(g, MultiPolygon):
        return [p for p in g.geoms if p.area > 3.0]
    return [g] if g.area > 3.0 else []


def thin(pts, min_seg=0.30):
    """Drop vertices closer than min_seg to the last kept one, keeping the final point.
    shapely's round joins emit ~0.03mm vertices at tight post-foot corners; at the floor's
    21.4 mm/s that is ~676 moves/s against the ~300 where Klipper freezes (validate's own
    moves/s gate caught it on the first emission)."""
    if len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    for p in pts[1:-1]:
        if math.dist(p, out[-1]) >= min_seg:
            out.append(p)
    out.append(pts[-1])
    return out


def ring_loops_out(FR, depths):
    """[(depth_index, loop_pts)] -- brim rails: inward buffers of the floor region."""
    out = []
    for i, d in enumerate(depths):
        for part in poly_parts(FR.buffer(-d, quad_segs=24)):
            out.append((i, thin([(x, y) for x, y in part.exterior.coords])))
    return out


def ring_loops_in(HR, depths):
    """[(depth_index, loop_pts)] -- hole-ring rails: outward buffers, outermost first."""
    out = []
    for i, d in enumerate(sorted(depths, reverse=True)):
        for part in poly_parts(HR.buffer(d, quad_segs=24)):
            out.append((i, thin([(x, y) for x, y in part.exterior.coords])))
    return out


def hatch_runs(region, pitch, angle_deg, min_len=1.5):
    """Hatch line segments clipped to `region`, rows `pitch` apart at `angle_deg`."""
    ca, sa = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    minx, miny, maxx, maxy = region.bounds
    cxm, cym = (minx + maxx) / 2, (miny + maxy) / 2
    half = math.hypot(maxx - minx, maxy - miny) / 2 + pitch
    runs = []
    r = -half
    while r <= half:
        # row line: points at signed distance r from centre along the normal (-sa, ca)
        bx, by = cxm - sa * r, cym + ca * r
        line = LineString([(bx - ca * half, by - sa * half), (bx + ca * half, by + sa * half)])
        cut = line.intersection(region)
        geoms = getattr(cut, "geoms", [cut] if not cut.is_empty else [])
        for gsegm in geoms:
            if isinstance(gsegm, LineString) and gsegm.length >= min_len:
                cc = list(gsegm.coords)
                runs.append(((cc[0][0], cc[0][1]), (cc[-1][0], cc[-1][1])))
        r += pitch
    return runs


def walk_boundary(region, p, q, seg):
    """Points along region's boundary from (the projection of) p to q, the short way.
    Both p and q are expected to lie ON (or within a bead of) one boundary ring."""
    best = None
    parts = poly_parts(region)
    all_rings = [r for part in parts for r in [part.exterior] + list(part.interiors)]
    for ring in all_rings:
        dp, dq = ring.distance(Point(p)), ring.distance(Point(q))
        if best is None or dp + dq < best[0]:
            best = (dp + dq, ring)
    ring = best[1]
    L = ring.length
    sp, sq = ring.project(Point(p)), ring.project(Point(q))
    fwd = (sq - sp) % L
    back = (sp - sq) % L
    if fwd <= back:
        s0, s1, n = sp, fwd, max(1, int(fwd / seg))
        pts = [ring.interpolate((s0 + s1 * i / n) % L) for i in range(1, n + 1)]
    else:
        s0, s1, n = sp, back, max(1, int(back / seg))
        pts = [ring.interpolate((s0 - s1 * i / n) % L) for i in range(1, n + 1)]
    return thin([(pt.x, pt.y) for pt in pts])


def monotone_columns(runs, angle_deg):
    """Split hatch runs into serpentine-able COLUMNS: consecutive rows whose runs overlap
    one-to-one. A split (one run facing two in the next row: the art hole starting), a merge,
    or a gap closes the column. Inside a column every row-to-row hop is a short neighbour
    connector; only column-to-column transitions need a rail walk -- which is the entire
    point. The first chaining was greedy nearest-end, and its walks stacked on the popular
    rail stretches until qa_weld read 4-5 bead-heights of pile."""
    ca, sa = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    rows = {}
    for a, b in runs:
        r = round(-sa * a[0] + ca * a[1], 3)
        x0, x1 = ca * a[0] + sa * a[1], ca * b[0] + sa * b[1]
        if x0 > x1:
            x0, x1, a, b = x1, x0, b, a
        rows.setdefault(r, []).append((x0, x1, a, b))
    cols = []
    open_cols = []                                   # [(last_x0, last_x1, col_index)]
    for r in sorted(rows):
        row = sorted(rows[r])
        pairs = []
        for i, run in enumerate(row):
            for j, (lx0, lx1, _) in enumerate(open_cols):
                if run[0] <= lx1 and lx0 <= run[1]:
                    pairs.append((i, j))
        from collections import Counter
        ci = Counter(p[1] for p in pairs)
        ri = Counter(p[0] for p in pairs)
        used_r, used_c = set(), set()
        for i, j in pairs:
            if ci[j] == 1 and ri[i] == 1:
                cols[open_cols[j][2]].append(row[i])
                open_cols[j] = (row[i][0], row[i][1], open_cols[j][2])
                used_r.add(i)
                used_c.add(j)
        open_cols = [oc for j, oc in enumerate(open_cols) if j in used_c]
        for i, run in enumerate(row):
            if i not in used_r:
                cols.append([run])
                open_cols.append((run[0], run[1], len(cols) - 1))
    return cols


def chain_hatch(runs, region, hole_block, start, seg, angle_deg):
    """One-stroke chain: monotone-column serpentines, columns joined by rail walks (the rail
    beads repeat at the same XY every floor layer, so a walk is supported and welded; a
    straight cross-region link is neither -- it floated 42.8mm on the first emission and drew
    stray lines across the art). Returns points EXCLUDING `start`."""
    cols = monotone_columns(runs, angle_deg)
    out = []
    cur = np.array(start)
    todo = [c for c in cols if c]
    while todo:
        # nearest column by its nearest END row
        best = None
        for ci, col in enumerate(todo):
            for rev in (False, True):
                run = col[-1] if rev else col[0]
                for pt in (run[2], run[3]):
                    d = math.dist(cur, pt)
                    if best is None or d < best[0]:
                        best = (d, ci, rev, pt)
        _, ci, rev, _ = best
        col = todo.pop(ci)
        if rev:
            col = col[::-1]
        first = True
        for (x0, x1, a, b) in col:
            if math.dist(cur, b) < math.dist(cur, a):
                a, b = b, a
            link = LineString([tuple(cur), tuple(a)])
            if link.length > 1e-9:
                if first and (link.length > 6.0 or link.intersects(hole_block)):
                    out += walk_boundary(region, tuple(cur), tuple(a), seg)
                    if out and math.dist(out[-1], tuple(a)) > 1e-9:
                        out += latch.line_pts(out[-1], tuple(a), seg)
                elif link.length > 6.0 or link.intersects(hole_block):
                    # a long hop INSIDE a column means the rows shifted under the hatch --
                    # rail-walk it too rather than float it
                    out += walk_boundary(region, tuple(cur), tuple(a), seg)
                    if out and math.dist(out[-1], tuple(a)) > 1e-9:
                        out += latch.line_pts(out[-1], tuple(a), seg)
                else:
                    out += latch.line_pts(tuple(cur), tuple(a), seg)
            out += latch.line_pts(tuple(a), tuple(b), seg)
            cur = np.array(b)
            first = False
    return out


# --------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--outer", required=True, help="silhouette PNG for the WALL")
    ap.add_argument("--hole", required=True, help="silhouette PNG for the floor CUT")
    ap.add_argument("--size", type=float, default=330.0)
    ap.add_argument("--pitch", type=float, default=32.0)
    ap.add_argument("--smooth", type=float, default=8.0)
    ap.add_argument("--dilate", type=float, default=7.0)
    ap.add_argument("--hole-frac", type=float, default=0.7)
    ap.add_argument("--brim-frac", type=float, default=0.20,
                    help="Oleg: 'abound 20%% of floor only as solid brim'")
    ap.add_argument("--net-pitch", type=float, default=4.0,
                    help="the art net's hatch pitch on floor layers 2+; v16's --floor-pitch")
    ap.add_argument("--net-pitch-1", type=float, default=None,
                    help="LAYER 1's net pitch. Default DERIVES w1 / %.2f -- the accepted "
                         "open-grid coverage RATIO (2.00 on 2.5, 'accepted by Oleg 2026-08-06') "
                         "at this file's own w1. THE PAIR IS UNPROVEN: the ledger proves pairs, "
                         "not ratios, and (3.94, 4.925) has never been on a plate. Declared as "
                         "'; NET1_PAIR=' so send.py can refuse it into the --oleg-said cycle "
                         "instead of it slipping past inside a default." % FLOOR1_OVERLAP)
    ap.add_argument("--wall-h", type=float, default=152.4, help="outer wall height mm (6 in)")
    ap.add_argument("--inner-wall-h", type=float, default=50.8,
                    help="the cut's own wall height mm (2 in)")
    ap.add_argument("--inner-mouth", choices=("net", "cut"), default="net",
                    help="which way the cut wall's C-channels open. 'net' (default) is what the "
                         "approved plan-D render DRAWS: mouths toward the bucket interior, "
                         "continuous face tracing the cut, crossings buried against the floor. "
                         "The render's first caption wrongly said 'INTO the cut' -- retracted; "
                         "'cut' builds that instead (sticks visible through the hole).")
    ap.add_argument("--stick-d", type=float, default=3.175)
    ap.add_argument("--bore-allow", type=float, default=1.665,
                    help="machine.PROVEN_SEND fit_bore 4.84: 'The bores are perfect now'")
    ap.add_argument("--wrap-deg", type=float, default=287.5)
    ap.add_argument("--bridge-every", type=int, default=20)
    ap.add_argument("--bridge-w-mult", type=float, default=1.8)
    ap.add_argument("--accent-every", type=int, default=50)
    ap.add_argument("--accent-w-mult", type=float, default=3.6)
    ap.add_argument("--top-layers", type=int, default=2)
    ap.add_argument("--top-w-mult", type=float, default=7.2)
    ap.add_argument("--inner-top-layers", type=int, default=2)
    ap.add_argument("--inner-top-mult", type=float, default=3.6,
                    help="the cut wall's own rim band: its last N layers bridge at this mult "
                         "(single pass; 3.6 keeps the rod at v16's proven 0.95mm)")
    ap.add_argument("--bottom-brace-layers", type=int, default=5)
    ap.add_argument("--bottom-bridge-every", type=int, default=5)
    ap.add_argument("--floor-layers", type=int, default=3)
    ap.add_argument("--floor-layer-h", type=float, default=0.56)
    ap.add_argument("--layer-h", type=float, default=0.24)
    ap.add_argument("--speed", type=float, default=machine.DEFAULT_SPEED)
    ap.add_argument("--cross-speed", type=float, default=80.0,
                    help="PROVEN_SEND cross_mms: every THIN CROSS in the accepted bucket ran 80")
    ap.add_argument("--speed1", type=float, default=25.0)
    ap.add_argument("--h1", type=float, default=0.25)
    ap.add_argument("--zerr", type=float, default=0.15)
    ap.add_argument("--w1", type=float, default=3.94)
    ap.add_argument("--fan", type=float, default=1.0)
    ap.add_argument("--cross-flow", type=float, default=0.18)
    ap.add_argument("--fabric", choices=("fused", "open"), default="open")
    ap.add_argument("--merge-mm", type=float, default=2.0)
    ap.add_argument("--merge-flow", type=float, default=None)
    ap.add_argument("--cite-coupon", metavar="FILE")
    ap.add_argument("--coupon-read", metavar="YYYY-MM-DD")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    bw = machine.SLICER_LINE_W
    lh = a.layer_h
    lh_f = a.floor_layer_h
    for _h, _nm in ((lh, "--layer-h"), (lh_f, "--floor-layer-h")):
        if not any(abs(_h - hh) < 1e-9 for hh in machine.SLICER_LAYER_HEIGHTS):
            raise SystemExit(f"REFUSING TO EMIT: {_nm} {_h:g} is not a profile height "
                             f"({', '.join(f'{h:g}' for h in machine.SLICER_LAYER_HEIGHTS)}).")
    press = machine.PRESS_HARD
    for _nm, _v in (("--speed", a.speed), ("--speed1", a.speed1)):
        if _v > machine.MAX_SPEED + 1e-9:
            raise SystemExit(f"REFUSING TO EMIT: {_nm} {_v:g} is above the "
                             f"{machine.MAX_SPEED:g} mm/s north star.")
    if a.h1 <= 0:
        raise SystemExit("REFUSING TO EMIT: --h1 must be positive.")
    try:
        zoff = machine.zoff_for(a.h1, a.zerr)
    except ValueError as _e:
        raise SystemExit(f"REFUSING TO EMIT: {_e}")
    if zoff > 1e-9:
        raise SystemExit(f"REFUSING TO EMIT: derived --zoff {zoff:+g} is POSITIVE.")

    speed, speed1 = a.speed, a.speed1
    f, f_l1 = round(speed * 60), round(speed1 * 60)
    speed_x = a.cross_speed or speed
    f_x = round(speed_x * 60)
    temp = machine.MATERIAL_TEMP[a.material]
    bed = machine.bed_for(a.material, a.printer)
    fan = machine.FAN_MAX[a.material] if a.fan is None else max(0.0, min(1.0, a.fan))
    e_mm = bw * lh / A_FIL
    e_mm_f = bw * lh_f / A_FIL
    speed_floor = speed * lh / lh_f
    f_floor = round(speed_floor * 60)
    w1 = a.w1
    h1_real = a.h1
    e_mm_l1 = machine.layer1_rate(w1, h1_real)
    _l1_ratio = (w1 * h1_real) / (bw * lh)
    if _l1_ratio < 0.99:
        raise SystemExit(f"REFUSING TO EMIT: layer 1 carries {_l1_ratio:.3f}x the body bead -- "
                         f"the first layer must be full flow.")
    flow = bw * lh * speed
    r8cap = machine.flow_cap(a.material, a.printer)

    # ---- the C-channel, derived exactly as bucket_towers derives it
    bore_d = a.stick_d + a.bore_allow
    tower_d = bore_d + 2.0 * bw
    r_t = (tower_d - bw) / 2.0
    half_rad = math.radians(a.wrap_deg / 2.0)
    toff = math.radians((360.0 - a.wrap_deg) / 2.0)
    # the planner's dip/solve read module globals; pin them to THIS file's derivation so the
    # two tools cannot solve different channels (they are the same numbers today by default,
    # and this line is what keeps that true when a flag moves)
    plan.R_T, plan.HALF, plan.tip_off = r_t, half_rad, toff

    bedx, bedy = machine.BED[a.printer]
    cx0, cy0 = bedx / 2.0, bedy / 2.0

    # ---------------------------------------------------------------- trace + place + solve
    outer = plan.prep(a.outer, a.size - bw, a.smooth, dilate_mm=a.dilate)
    outer = outer + np.array([cx0, cy0])                     # planner traces about the origin
    per = float(np.hypot(*np.diff(np.vstack([outer, outer[:1]]), axis=0).T).sum())
    area = abs(plan.shoelace(outer))
    o_cs, o_ph, o_stag = place_and_solve(outer, a.pitch, r_t, half_rad, toff, "outer")
    o_mu = [o_ph[i] + o_stag[i] for i in range(len(o_cs))]
    n_out = len(o_cs)

    # the art hole, auto-fit exactly as the approved plan fitted it
    w_brim = a.brim_frac * area / per
    lp = FLOOR1_OVERLAP * bw
    n_rings = max(2, int(round(w_brim / lp)))
    from matplotlib.path import Path as MplPath
    inner_edge = plan.offset_inward(outer, r_t + bw / 2 + w_brim)
    P_fit = MplPath(plan.offset_inward(inner_edge, 8.0))
    frac = a.hole_frac
    hole = None
    ictr = inner_edge.mean(axis=0)
    for _ in range(16):
        cand0 = plan.prep(a.hole, (a.size - bw) * frac, max(3.0, a.smooth * frac))
        cand0 = cand0 - cand0.mean(axis=0)
        done = False
        for dx in (0, -10, 10, -20, 20):
            for dy in (0, -10, 10, -20, 20, -30, 30):
                cand = cand0 + ictr + (dx, dy)
                if P_fit.contains_points(cand).all():
                    hole, done = cand, True
                    break
            if done:
                break
        if done:
            break
        frac *= 0.94
    if hole is None:
        raise SystemExit("REFUSING TO EMIT: the hole never fit inside the net region.")
    hole_area = abs(plan.shoelace(hole))

    i_cs, i_ph, i_stag = place_and_solve(hole, a.pitch * 0.8, r_t, half_rad, toff, "inner",
                                         flip=(a.inner_mouth == "cut"))
    i_mu = [i_ph[i] + i_stag[i] for i in range(len(i_cs))]
    n_in = len(i_cs)

    all_cs = list(map(tuple, o_cs)) + list(map(tuple, i_cs))
    all_mu = list(o_mu) + list(i_mu)

    # cross-ring check: every crossing of each ring vs EVERY post of both rings
    o_ch = ring_chords(o_cs, o_mu, r_t, toff)
    i_ch = ring_chords(i_cs, i_mu, r_t, toff)
    for nm, ch, base in (("outer", o_ch, 0), ("inner", i_ch, n_out)):
        nn2 = n_out if base == 0 else n_in
        for k, (p, q) in enumerate(ch):
            d, j = seg_dip(p, q, all_cs, all_mu, r_t, half_rad, n=512,
                           own_p=base + k, own_q=base + (k + 1) % nn2)
            if d > 1e-9:
                raise SystemExit(f"REFUSING TO EMIT: {nm} crossing {k} dips {d:.3f}mm past the "
                                 f"graze law into post {j} (both rings checked).")
    max_chord = max(math.dist(p, q) for p, q in o_ch + i_ch)
    _spans = machine.PROVEN_SEND.get(a.printer, {}).get("span_mm", [])
    span_cap = max((t[0] for t in _spans), default=PROVEN_AIR_MM)
    if max_chord > span_cap + 1e-6:
        raise SystemExit(f"REFUSING TO EMIT: a {max_chord:.2f}mm crossing exceeds the "
                         f"{span_cap:.2f}mm the send ledger has ever accepted.")

    # ---------------------------------------------------------------- the transit (V panel)
    hole_poly = Polygon([(x, y) for x, y in hole]).buffer(0)
    hole_block = hole_poly.buffer(1.0)

    def leading(k):
        return tips_of(o_cs[k], o_mu[k], r_t, toff)[0]

    def trailing(k):
        return tips_of(o_cs[k], o_mu[k], r_t, toff)[1]

    best_tr = None
    hc = np.array(hole_poly.centroid.coords[0])
    order = sorted(range(n_out), key=lambda k: math.dist(o_cs[k], hc))
    for J in order[:10]:
        pJ = leading(J)
        qJ1 = trailing((J + 1) % n_out)
        for K in range(n_in):
            for azd in range(0, 360, 5):
                az = math.radians(azd)
                # landing azimuth must be on K's MATERIAL, >= 15 deg clear of the tips
                off = (az - (i_mu[K] + math.pi)) % (2 * math.pi)
                off = off - 2 * math.pi if off > math.pi else off
                if abs(off) > half_rad - math.radians(15):
                    continue
                M1 = (i_cs[K][0] + r_t * math.cos(az), i_cs[K][1] + r_t * math.sin(az))
                L1s, L2s = math.dist(pJ, M1), math.dist(M1, qJ1)
                if max(L1s, L2s) > span_cap:
                    continue
                if best_tr and L1s + L2s >= best_tr[0]:
                    continue
                if (LineString([pJ, M1]).intersects(hole_block)
                        or LineString([M1, qJ1]).intersects(hole_block)):
                    continue
                d1, _ = seg_dip(pJ, M1, all_cs, all_mu, r_t, half_rad, n=512,
                                own_p=J, own_q=n_out + K)
                d2, _ = seg_dip(M1, qJ1, all_cs, all_mu, r_t, half_rad, n=512,
                                own_p=n_out + K, own_q=(J + 1) % n_out)
                if max(d1, d2) > 1e-9:
                    continue
                best_tr = (L1s + L2s, J, K, az, M1, L1s, L2s)
    if best_tr is None:
        raise SystemExit("REFUSING TO EMIT: no transit pair (outer gap -> inner post) clears "
                         "both rings and the art hole. Move the hole (--hole-frac) or change "
                         "--pitch.")
    _, TJ, TK, t_az, M1, tr_len1, tr_len2 = best_tr

    # ---------------------------------------------------------------- floor construction
    FR = floor_region_outer(o_cs, o_mu, r_t, toff)
    HR = hole_region_inner(i_cs, i_mu, r_t, toff)
    lp1 = FLOOR1_OVERLAP * w1
    n_rings1 = max(2, int(round(w_brim / lp1)))
    nh, nh1 = 3, 2
    net1_pitch = a.net_pitch_1 if a.net_pitch_1 else round(w1 / FLOOR1_OVERLAP, 3)

    def floor_parts(lpx, nrx, nhx, netp, ang):
        rings = ring_loops_out(FR, [lpx * (1 + i) for i in range(nrx)])
        hrings = ring_loops_in(HR, [lpx * (1 + i) for i in range(nhx)])
        N = FR.buffer(-lpx * nrx, quad_segs=24).difference(
            HR.buffer(lpx * nhx, quad_segs=24))
        runs = hatch_runs(N, netp, ang)
        return rings, hrings, N, runs

    # exit rib: nearest inner tip to outer post 0's trailing tip, gated off the hole
    start0 = trailing(0)
    exK = min(range(n_in), key=lambda k2: math.dist(tips_of(i_cs[k2], i_mu[k2], r_t, toff)[1],
                                                    start0))
    ex_tip = tips_of(i_cs[exK], i_mu[exK], r_t, toff)[1]
    # the rib starts ON the inner rim, inside the hole's 1mm guard band by construction --
    # gate the rib PAST its first 2.5mm, or the guard fires on its own anchor point
    _rl = math.dist(ex_tip, start0)
    _t0 = min(1.0, 2.5 / _rl)
    _rib_body = LineString([(ex_tip[0] + (start0[0] - ex_tip[0]) * _t0,
                             ex_tip[1] + (start0[1] - ex_tip[1]) * _t0), start0])
    if _rib_body.intersects(hole_block):
        raise SystemExit("REFUSING TO EMIT: the floor exit rib crosses the art hole.")

    def inner_rim_circuit(entry_pt, start_k):
        """Inner posts + EXTRUDED chords starting at start_k's trailing tip, full circuit."""
        pts, kinds = [], []
        t0 = tips_of(i_cs[start_k], i_mu[start_k], r_t, toff)[1]
        pts += latch.line_pts(entry_pt, t0, SEG)
        kinds += ["E"] * len(pts)
        for kk in range(n_in):
            k2 = (start_k + kk) % n_in
            arc = post_arc(i_cs[k2], i_mu[k2], r_t, None, toff, SEG)
            pts += arc
            kinds += ["E"] * len(arc)
            nxt = tips_of(i_cs[(k2 + 1) % n_in], i_mu[(k2 + 1) % n_in], r_t, toff)[1]
            lnk = latch.line_pts(pts[-1], nxt, SEG)
            pts += lnk
            kinds += ["R"] * len(lnk)
        return pts, kinds

    def floor_layer(li, entry):
        """One whole floor layer from `entry` (== starts[0]) back to starts[0]."""
        lpx = lp1 if li == 0 else lp
        nrx = n_rings1 if li == 0 else n_rings
        nhx = nh1 if li == 0 else nh
        netp = net1_pitch if li == 0 else a.net_pitch
        ang = 90.0 * (li % 2)
        rings, hrings, N, runs = floor_parts(lpx, nrx, nhx, netp, ang)
        pts, kinds = [], []
        cur = entry

        def go(newpts, kind="E"):
            nonlocal cur
            pts.extend(newpts)
            kinds.extend([kind] * len(newpts))
            if newpts:
                cur = newpts[-1]

        for _, loop in rings:                                    # brim, outermost first
            j0 = min(range(len(loop)), key=lambda j2: math.dist(loop[j2], cur))
            lnk = latch.line_pts(cur, loop[j0], SEG)
            if LineString([cur, loop[j0]]).intersects(hole_block):
                raise SystemExit("REFUSING TO EMIT: a brim link crosses the art hole.")
            go(lnk)
            go(loop[j0 + 1:] + loop[:j0 + 1])
        net_start = cur
        go(chain_hatch(runs, N, hole_block, net_start, SEG, ang))
        for hi, (_, loop) in enumerate(hrings):                  # hole rings, outermost first
            j0 = min(range(len(loop)), key=lambda j2: math.dist(loop[j2], cur))
            if LineString([cur, loop[j0]]).intersects(hole_block):
                raise SystemExit("REFUSING TO EMIT: a hole-ring link crosses the art hole.")
            if hi == 0 and math.dist(cur, loop[j0]) > 6.0:
                # the approach from the net's last strand to the hole rings: a straight hop
                # here floats over sparse net and draws a line across the art -- walk N's
                # hole-side boundary, which IS the outermost hole rail
                go(walk_boundary(N, tuple(cur), loop[j0], SEG))
            go(latch.line_pts(cur, loop[j0], SEG))
            go(loop[j0 + 1:] + loop[:j0 + 1])
        rp, rk = inner_rim_circuit(cur, exK)
        pts += rp
        kinds += rk
        cur = pts[-1]
        go(latch.line_pts(cur, start0, SEG))                     # the exit rib
        # outer posts + extruded rim chords
        for k in range(n_out):
            arc = post_arc(o_cs[k], o_mu[k], r_t, None, toff, SEG)
            go(arc)
            nxt = trailing((k + 1) % n_out)
            go(latch.line_pts(cur, nxt, SEG), "R")
        return pts, kinds

    # ---------------------------------------------------------------- z ladder + schedule
    _floor_top = press + max(0, a.floor_layers - 1) * lh_f

    def z_of(li):
        if li <= 0:
            return press
        if li < a.floor_layers:
            return press + li * lh_f
        return _floor_top + (li - max(a.floor_layers - 1, 0)) * lh

    n_lay = a.floor_layers + int(round((a.wall_h - _floor_top) / lh))
    li_inner_top = a.floor_layers - 1
    for li in range(a.floor_layers, n_lay):
        if z_of(li) <= a.inner_wall_h + 1e-9:
            li_inner_top = li
    if li_inner_top < a.floor_layers:
        raise SystemExit("REFUSING TO EMIT: --inner-wall-h leaves no inner wall above the floor.")

    mult_cap = r8cap / flow if (r8cap and flow) else None
    m_ord, m_acc, m_top = a.bridge_w_mult, a.accent_w_mult, a.top_w_mult
    bridges = {}
    body = range(a.floor_layers, n_lay)
    if a.bridge_every > 0:
        for li in body:
            every = (a.bottom_bridge_every
                     if (a.bottom_brace_layers > 0 and li - a.floor_layers < a.bottom_brace_layers)
                     else a.bridge_every)
            if every > 0 and li % every == 0:
                bridges[li] = m_ord
    if a.accent_every > 0:
        for li in body:
            if li % a.accent_every == 0:
                bridges[li] = m_acc
    bridges[n_lay - 1] = m_ord if a.top_layers <= 0 else m_top
    for li in range(max(a.floor_layers, n_lay - max(0, a.top_layers)), n_lay):
        bridges[li] = m_top
    in_bridges = {li: m for li, m in bridges.items() if li <= li_inner_top}
    for li in range(max(a.floor_layers, li_inner_top - a.inner_top_layers + 1), li_inner_top + 1):
        in_bridges[li] = a.inner_top_mult

    # per-pass rod cap (v16's machinery): a mult past the cap splits into circuits
    _mcap = math.pi * machine.PROVEN_ROD_MM ** 2 / (4.0 * bw * lh)
    bpass = {}
    for _m9 in set(bridges.values()) | set(in_bridges.values()):
        _n9 = max(1, int(math.ceil(_m9 / _mcap)))
        bpass[_m9] = _n9
        if _m9 / _n9 > _mcap + 1e-9:
            raise SystemExit(f"REFUSING TO EMIT: bridge mult {_m9:g}x cannot get under the "
                             f"proven rod at any pass count.")
        if r8cap and (_m9 / _n9) * flow > r8cap + 1e-9:
            raise SystemExit(f"REFUSING TO EMIT: bridge mult {_m9:g}x per pass asks "
                             f"{(_m9/_n9)*flow:.1f} mm3/s of a {r8cap:g} extruder.")
    for li, m in in_bridges.items():
        if li <= li_inner_top and bpass.get(m, 1) > 1:
            raise SystemExit(f"REFUSING TO EMIT: inner-ring mult {m:g}x needs {bpass[m]} "
                             f"circuits and the inner ring does not do circuits. Use a mult "
                             f"under {_mcap:.2f}.")

    # fabric state, declared (same law as bucket_towers)
    fab_sub = lh
    cross_min = math.pi * lh / (4.0 * bw)
    fabric_rod = 2.0 * math.sqrt(a.cross_flow * bw * lh / math.pi)
    fabric_fused = fabric_rod >= fab_sub - 1e-9
    if a.fabric == "open" and fabric_fused:
        raise SystemExit("REFUSING TO EMIT: --fabric open but the rod reaches the pitch.")
    if a.fabric == "fused" and not fabric_fused:
        raise SystemExit("REFUSING TO EMIT: --fabric fused but the rod floats short.")

    merge_flow = a.cross_flow if a.merge_flow is None else a.merge_flow
    arc_len = r_t * 2.0 * half_rad
    if a.merge_mm > 0:
        if merge_flow <= 0:
            raise SystemExit("REFUSING TO EMIT: a zero-flow lap is a dry plough.")
        if a.merge_mm > arc_len / 2.0 + 1e-9:
            raise SystemExit(f"REFUSING TO EMIT: --merge-mm {a.merge_mm:g} exceeds half the "
                             f"{arc_len:.2f}mm post arc.")
        if r8cap and merge_flow * flow > r8cap + 1e-9:
            raise SystemExit("REFUSING TO EMIT: lap flow exceeds the material figure.")
    merge_mm2 = merge_flow * bw * lh
    lap_pack = 1.0 + 2.0 * merge_flow

    # lip budget -- both rings carry v16's regimes exactly (the transit lands mid-arc, not
    # on a lip, so it adds NOTHING here; the M1 zone is declared separately below)
    _lap_term = 2.0 * merge_flow if a.merge_mm > 0 else 0.0
    lip_regimes = [("body", bw * (1.0 + _lap_term + a.cross_flow + m_ord / a.bridge_every))]
    if a.bottom_brace_layers > 0:
        lip_regimes.append(("band", bw * (1.0 + _lap_term + a.cross_flow
                                          + m_ord / a.bottom_bridge_every)))
    if a.accent_every > 0:
        lip_regimes.append(("accent", bw * (1.0 + _lap_term + a.cross_flow
                                            + m_acc / a.accent_every)))
    # THE RIM BANDS ARE DECLARED, NOT GATED -- bucket_towers' own treatment of its 7.2x top
    # (which measures 7.0 on this same scale, exceeded PROVEN_LIP, and printed as the accepted
    # bucket): consecutive bridge layers at the very top are where the sticks ENTER, they are
    # Oleg's explicit hierarchy, and the header states them as UNPROVEN for insertion. The
    # gate below guards the RECURRING regimes, which is what PROVEN_LIP was measured on.
    lip_top_out = bw * (1.0 + _lap_term + m_top)
    lip_top_in = bw * (1.0 + _lap_term + a.inner_top_mult)
    lip_proven = machine.PROVEN_LIP.get(a.printer)
    if lip_proven:
        _wnm, _w = max(lip_regimes, key=lambda t: t[1])
        if _w > lip_proven * 1.01:
            raise SystemExit(f"REFUSING TO EMIT: the {_wnm} regime puts {_w:.3f} mm3/mm2 on the "
                             f"mouth lips, past the {lip_proven:.3f} ever inserted.")
    m1_zone = bw * (1.0 + 2.0 * a.cross_flow)      # the transit's landing, mid-arc, not a mouth

    # THE BRIM PITCH NEEDS NO GATE: lp1 = FLOOR1_OVERLAP x w1 is DERIVED, so it cannot exceed
    # the bead it is a fraction of -- a check here could never fire, and a gate that cannot
    # fire is a false comfort (the instrument-is-the-liar lesson). The net's layer-1 pitch is
    # the one that CAN be wrong and it is declared UNPROVEN in the header instead.

    # ---------------------------------------------------------------- build all layers
    layers = []
    entry = start0

    def weld_lap(tip, c, a_tip, sign):
        """merge lap: out along the post's own arc and back to EXACTLY tip."""
        if a.merge_mm <= 0:
            return [], []
        step_rad = SEG / r_t
        total = a.merge_mm / r_t
        outp, walked = [], 0.0
        while walked < total - 1e-12:
            walked = min(total, walked + step_rad)
            ang2 = a_tip + sign * walked
            outp.append((c[0] + r_t * math.cos(ang2), c[1] + r_t * math.sin(ang2)))
        path = outp + outp[-2::-1] + [tip]
        return path, ["M"] * len(path)

    for li in range(n_lay):
        is_floor = li < a.floor_layers
        _m = bridges.get(li)
        _mi = in_bridges.get(li)
        has_inner = (not is_floor) and li <= li_inner_top
        n_circ = bpass.get(_m, 1) if _m is not None else 1
        zfr = [(c2 + 1) / n_circ for c2 in range(n_circ)]
        for _ci, _zf in enumerate(zfr):
            pts, kinds = [], []
            if is_floor and n_circ == 1:
                fp, fk = floor_layer(li, entry)
                pts, kinds = [entry] + fp, fk
            else:
                pts = [entry]
                cross = ("B" if _m is not None else "T")
                for k in range(n_out):
                    arc = post_arc(o_cs[k], o_mu[k], r_t, None, toff, SEG)
                    pts += arc
                    kinds += ["E"] * len(arc)
                    lead_tip = arc[-1]
                    if has_inner and k == TJ:
                        # transit out -> inner circuit (M1-split) -> transit back
                        wp, wk = weld_lap(lead_tip, o_cs[k], o_mu[k] + toff, -1)
                        pts += wp; kinds += wk
                        pts.append(M1); kinds.append(cross)
                        # inner: M1 -> leading tip of TK (partial arc), around, back to M1.
                        # t_az is NORMALISED into the walk's frame (<= trailing angle) or the
                        # sweep silently becomes nearly a full turn THROUGH THE MOUTH.
                        _t_azn = _wrap_to(t_az, i_mu[TK] - toff)
                        arcp = post_arc(i_cs[TK], i_mu[TK], r_t, None, toff, SEG,
                                        frm=_t_azn, to=i_mu[TK] + toff - 2 * math.pi)
                        pts += arcp; kinds += ["E"] * len(arcp)
                        for kk in range(n_in):
                            k2 = (TK + kk) % n_in
                            nx2 = (k2 + 1) % n_in
                            icross = ("B" if _mi is not None else "T")
                            wp, wk = weld_lap(pts[-1], i_cs[k2], i_mu[k2] + toff, -1)
                            pts += wp; kinds += wk
                            t_nxt = tips_of(i_cs[nx2], i_mu[nx2], r_t, toff)[1]
                            pts.append(t_nxt); kinds.append(icross + "i")
                            wp, wk = weld_lap(t_nxt, i_cs[nx2], i_mu[nx2] - toff, +1)
                            pts += wp; kinds += wk
                            if nx2 == TK:
                                arcq = post_arc(i_cs[TK], i_mu[TK], r_t, None, toff, SEG,
                                                frm=i_mu[TK] - toff, to=_t_azn)
                                if arcq:
                                    arcq[-1] = M1      # close the split arc on the exact float
                                pts += arcq; kinds += ["E"] * len(arcq)
                                break
                            arcn = post_arc(i_cs[nx2], i_mu[nx2], r_t, None, toff, SEG)
                            pts += arcn; kinds += ["E"] * len(arcn)
                        nxt_trail = trailing((k + 1) % n_out)
                        pts.append(nxt_trail); kinds.append(cross)
                        wp, wk = weld_lap(nxt_trail, o_cs[(k + 1) % n_out],
                                          o_mu[(k + 1) % n_out] - toff, +1)
                        pts += wp; kinds += wk
                    else:
                        wp, wk = weld_lap(lead_tip, o_cs[k], o_mu[k] + toff, -1)
                        pts += wp; kinds += wk
                        nxt_trail = trailing((k + 1) % n_out)
                        pts.append(nxt_trail); kinds.append(cross)
                        wp, wk = weld_lap(nxt_trail, o_cs[(k + 1) % n_out],
                                          o_mu[(k + 1) % n_out] - toff, +1)
                        pts += wp; kinds += wk
            layers.append({"pts": pts, "kind": kinds, "mult": _m, "imult": _mi, "li": li,
                           "zf": _zf, "cdiv": n_circ,
                           "label": ("floor latch art" if is_floor else
                                     ("posts + BRIDGES %gx" % _m if _m else "posts")
                                     + (" + inner" if has_inner else ""))
                                    + (f" circuit {_ci+1}/{n_circ}" if n_circ > 1 else "")})
            entry = layers[-1]["pts"][-1]

    # ---------------------------------------------------------------- gates on built points
    for i in range(1, len(layers)):
        d = math.dist(layers[i]["pts"][0], layers[i - 1]["pts"][-1])
        if d > 1e-6:
            raise SystemExit(f"REFUSING TO EMIT: layer {i+1} starts {d:.6f}mm from where layer "
                             f"{i} ended -- a travel inside the object.")
    for i, L in enumerate(layers):
        halfb = (w1 if L["li"] == 0 else bw) / 2.0
        for (x, y) in L["pts"]:
            if not (halfb <= x <= bedx - halfb and halfb <= y <= bedy - halfb):
                raise SystemExit(f"REFUSING TO EMIT: layer {i+1} puts material at "
                                 f"({x:.1f},{y:.1f}) off the plate.")
    zs = [press if L["li"] == 0 else
          z_of(L["li"] - 1) + L["zf"] * (z_of(L["li"]) - z_of(L["li"] - 1)) for L in layers]
    if any(zs[k] < zs[k - 1] - 1e-9 for k in range(1, len(zs))):
        raise SystemExit("REFUSING TO EMIT: Z descends.")
    # every airborne move on WALL layers clears every post of both rings, under the graze
    # law: its own two anchor posts (detected off the endpoints, which sit ON their circles
    # by construction) may be grazed at the tip, nothing else may be touched at all
    def _own_of(pt):
        j = min(range(len(all_cs)), key=lambda jj: abs(math.dist(pt, all_cs[jj]) - r_t))
        return j if abs(math.dist(pt, all_cs[j]) - r_t) < 1e-5 else None

    n_air, worst_air = 0, 0.0
    _air_seen = set()
    for L in layers:
        if L["li"] < a.floor_layers:
            continue
        for j, k in enumerate(L["kind"]):
            if k in ("T", "B", "Ti", "Bi"):
                p, q = L["pts"][j], L["pts"][j + 1]
                n_air += 1
                key = (round(p[0], 3), round(p[1], 3), round(q[0], 3), round(q[1], 3))
                if key in _air_seen:
                    worst_air = max(worst_air, math.dist(p, q))
                    continue                     # identical chord repeats every layer
                _air_seen.add(key)
                d, jj = seg_dip(p, q, all_cs, all_mu, r_t, half_rad, n=256,
                                own_p=_own_of(p), own_q=_own_of(q))
                if d > 1e-9:
                    raise SystemExit(f"REFUSING TO EMIT: an airborne move on layer li="
                                     f"{L['li']} dips {d:.4f}mm past the graze law into post "
                                     f"{jj}.")
                worst_air = max(worst_air, math.dist(p, q))
    if worst_air > span_cap + 1e-6:
        raise SystemExit(f"REFUSING TO EMIT: airborne span {worst_air:.2f}mm past the ledger.")
    # merge laps: measured on points (ON a post circle, back to the exact tip)
    n_merge = 0
    for L in layers:
        K2, P2 = L["kind"], L["pts"]
        j = 0
        while j < len(K2):
            if K2[j] != "M":
                j += 1
                continue
            j0 = j
            while j < len(K2) and K2[j] == "M":
                j += 1
            tip = P2[j0]
            if math.dist(P2[j], tip) > 1e-9:
                raise SystemExit("REFUSING TO EMIT: a merge lap does not return to its tip.")
            c = min(all_cs, key=lambda cc: abs(math.dist(cc, tip) - r_t))
            for p2 in P2[j0:j + 1]:
                if abs(math.dist(p2, c) - r_t) > 1e-6:
                    raise SystemExit("REFUSING TO EMIT: a merge lap strays off its post circle.")
            n_merge += 1
    if a.merge_mm > 0 and not n_merge:
        raise SystemExit("REFUSING TO EMIT: --merge-mm asked for and no lap was built.")

    # ---------------------------------------------------------------- measures + header
    def layer_mm(L):
        ext = trav = 0.0
        for j, k in enumerate(L["kind"]):
            d = math.dist(L["pts"][j], L["pts"][j + 1])
            if k in ("T", "Ti"):
                trav += d
            else:
                ext += d
        return ext, trav

    path_mm = sum(layer_mm(L)[0] for L in layers)
    trav_mm = sum(layer_mm(L)[1] for L in layers)
    floor_mm = sum(layer_mm(L)[0] for L in layers[:a.floor_layers])
    floor_mins = sum(layer_mm(Lz)[0] / (speed1 if i == 0 else speed_floor)
                     for i, Lz in enumerate(layers[:a.floor_layers])) / 60.0
    mins = 0.0
    for Lz in layers:
        e2, t2 = layer_mm(Lz)
        li = Lz["li"]
        v_e = speed1 if li == 0 else (speed_floor if li < a.floor_layers else speed)
        mins += e2 / v_e / 60.0 + t2 / (speed1 if li == 0 else speed_x) / 60.0
    top_z = z_of(n_lay - 1)
    sha_o = hashlib.sha256(open(a.outer, "rb").read()).hexdigest()[:16]
    sha_h = hashlib.sha256(open(a.hole, "rb").read()).hexdigest()[:16]
    _bmoves = sorted({m / bpass[m] for m in bpass})
    _mm2s = sorted({round(m * bw * lh, 4) for m in _bmoves})
    brim_frac_real = (FR.area - sum(p.area for p in poly_parts(
        FR.buffer(-lp * n_rings, quad_segs=24)))) / area

    L = []
    w = L.append
    w(f"; ART BUCKET — {n_out}+{n_in} C-channel posts on two traced silhouettes, "
      f"{len(bridges)} bridged layers of {n_lay}")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; CMD={' '.join(shlex.quote(s) for s in [os.path.basename(sys.argv[0])] + sys.argv[1:])}")
    w(f"; ART_SHA outer={sha_o} hole={sha_h}  (inputs live in gitignored out/; the hash is how "
      f"a regeneration proves it used the same art)")
    w(f"; IP: character art -> household part only, never a shop page.")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={speed:.4f}")
    w(f"; SPEED_LAYER1={speed1:.4f}")
    if abs(lh_f - lh) > 1e-9 and a.floor_layers > 1:
        w(f"; SPEED_FLOOR={speed_floor:.4f}")
        w(f"; LAYER_H_FLOOR={lh_f:g}")
    w(f"; SPEED_CROSS={speed_x:.4f}")
    if speed_x > machine.MAX_SPEED + 1e-9:
        w(f"; SPEED_OVERRIDE={speed_x:.4f}")
        w(f";   raised for the gap crossings ONLY; ledgered at 80 off the accepted bucket.")
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; LAYER1_WIDTH={w1:.2f}mm landed into the {h1_real:g} gap = {w1*h1_real:.4f}mm2/mm "
      f"({w1*h1_real/(bw*lh):.2f}x the body's own {bw*lh:.4f}mm2 bead)")
    if a.cite_coupon:
        if not a.coupon_read:
            raise SystemExit("REFUSING TO EMIT: --cite-coupon needs --coupon-read.")
        if not os.path.isfile(a.cite_coupon):
            raise SystemExit(f"REFUSING TO EMIT: {a.cite_coupon} does not exist.")
        w(f"; COUPON={a.cite_coupon} h1={h1_real:g} w1={w1:.2f} verdict=welded "
          f"read={a.coupon_read}")
    w(f"; PRINT_TEMP={temp}")
    w(f"; bead {bw:g}x{lh:g}   nozzle {machine.NOZZLE:g}")
    w(f"; FLOW_DERATE=a {machine.NOZZLE:g} nozzle laying {bw:g}x{lh:g} at {speed:g} mm/s "
      f"delivers {flow:.2f} mm3/s; widening the bead would thicken a single-wall part's wall. "
      f"Declared, not silent.")
    w(f"; BRIDGE_FLOW={','.join(f'{m:g}' for m in _bmoves)}")
    w(f"; BRIDGE_MM2={','.join(f'{v:.4f}' for v in _mm2s)}")
    if any(bpass[m] > 1 for m in bpass):
        w(f"; BRIDGE_PASSES=" + ",".join(f"{m:g}x->{bpass[m]}" for m in sorted(bpass)))
    if a.merge_mm > 0:
        w(f"; MERGE_MM={a.merge_mm:.4f}")
        w(f"; MERGE_MM2={merge_mm2:.4f}")
        w(f"; MERGE_PASSES=2")
    w(f"; FABRIC={'fused' if fabric_fused else 'open'} rod={fabric_rod:.3f}mm "
      + (f"overlap={fabric_rod-fab_sub:.3f}mm" if fabric_fused
         else f"gap={fab_sub-fabric_rod:.3f}mm") + f" (strand pitch {fab_sub:g}, 1 pass)")
    w(f"; LIP_BUDGET=" + ", ".join(f"{nm} {v:.3f}" for nm, v in lip_regimes)
      + (f" vs {lip_proven:.3f} proven" if lip_proven else " UNGUARDED") + " mm3/mm2")
    w(f";   top rims DECLARED, not gated (bucket_towers' own law for consecutive bridge "
      f"bands): outer {lip_top_out:.3f} over {a.top_layers} layer(s), inner {lip_top_in:.3f} "
      f"over {a.inner_top_layers} -- PAST anything ever inserted, exactly where the sticks "
      f"enter. If a stick stops at the very top of either wall, this is the suspect.")
    w(f"; CHORD_GRAZE=own-post grazes <= {GRAZE_MM:g}mm within {GRAZE_NEAR_MM:g}mm of the tip "
      f"are WELDS (qa_weld's own weld margin -- the strand hugging the bead corner it lands "
      f"on is a micro merge-lap); every other material contact refused at 1e-9.")
    w(f"; NET1_PITCH={net1_pitch:g}")
    w(f"; NET1_PAIR=({w1:g}, {net1_pitch:g}) UNPROVEN -- the accepted open-grid RATIO "
      f"(2.00 on 2.5, Oleg 2026-08-06) at this file's w1; the ledger proves PAIRS and this "
      f"pair has never been on a plate. send.py should refuse it into the --oleg-said cycle.")
    w(f"; TRANSIT gap {TJ}->{TJ+1} routes through inner post {TK}: legs {tr_len1:.1f} + "
      f"{tr_len2:.1f}mm, landing MID-ARC (az {math.degrees(t_az):.0f} deg) on the post's "
      f"continuous face -- not a lip, so the mouth budget is untouched; the landing zone "
      f"carries {m1_zone:.3f} mm3/mm2. That gap's fabric panel is a V through the cut wall "
      f"for {li_inner_top - a.floor_layers + 1} layers -- a visibly different panel, declared.")
    w(f"; INNER_MOUTH={a.inner_mouth} (the approved render DRAWS mouths toward the net; its "
      f"first caption said 'INTO the cut' and was retracted -- the drawing was right)")
    w(f"; INNER_WALL h={a.inner_wall_h:g}mm, top at layer {li_inner_top+1} (z "
      f"{z_of(li_inner_top):.2f}), rim band {a.inner_top_layers} layers at "
      f"{a.inner_top_mult:g}x")
    w(f"; FLOOR_WELD=lap {1-FLOOR1_OVERLAP:.2f}xbead at every interface; brim {n_rings} rings "
      f"(L1 {n_rings1} at {lp1:g}), hole {nh} rings (L1 {nh1}), net {a.net_pitch:g}mm "
      f"(L1 {net1_pitch:g}mm, OPEN by design: '20% of floor only as solid brim'); "
      f"gate tools/qa_weld.py")
    w(f"; BRIM measured {brim_frac_real*100:.0f}% of floor area solid "
      f"(asked {a.brim_frac*100:g}%), band {w_brim:.1f}mm")
    w(f"; HOLE {hole_area/area*100:.0f}% of floor, area {hole_area/100:.0f} cm2")
    for k in range(n_out):
        w(f"; ART_POST outer {k} {o_cs[k][0]:.4f} {o_cs[k][1]:.4f} mu={math.degrees(o_mu[k]):.3f}")
    for k in range(n_in):
        w(f"; ART_POST inner {k} {i_cs[k][0]:.4f} {i_cs[k][1]:.4f} mu={math.degrees(i_mu[k]):.3f}")
    w(f"; ART_EXIT {ex_tip[0]:.3f} {ex_tip[1]:.3f} {start0[0]:.3f} {start0[1]:.3f}")
    w(f"; ART_WRAP={a.wrap_deg:g} TOWER_D={tower_d:.3f}")
    _hp = [hole[i] for i in range(0, len(hole), 3)]
    w("; ART_HOLE " + " ".join(f"{x:.2f},{y:.2f}" for x, y in _hp)
      + "  (the cut outline: qa_weld exempts inner-border steps inside it -- nothing can ever "
        "lap the side of a wall that faces a void, by design)")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {n_lay}")
    w("; HEADER_BLOCK_END")
    w("M82")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    _floorT = bed if a.printer == "k2plus" else machine.bed_start(a.material, bed)
    w(f"M190 S{_floorT:.0f}   ; BLOCKING: do not start below this")
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    machine.home(w, a.printer)
    w(f"SET_GCODE_OFFSET Z={zoff:.3f}"
      + ("                 ; the machine's own zero, uncorrected" if abs(zoff) < 1e-9 else
         f"            ; nozzle {abs(zoff):.3f}mm CLOSER than the machine's zero"))
    _fan_l1 = int(round(machine.fan_first_layer(a.material) * 255))
    w(f"M106 S{_fan_l1}                              ; layer 1 fan: the plate weld is the job")
    for _ln in machine.aux_fans(a.printer, 0.0):
        w(f"{_ln}                  ; no chamber draft on a wall of cantilevers")
    w("G92 E0")
    sx0, sy0 = layers[0]["pts"][0]
    machine.prime(w, printer=a.printer, z=press, rate=e_mm_l1, feed=f_l1,
                  travel_feed=round(machine.MACHINE_MAX_SPEED * 60),
                  avoid=(("circle", cx0, cy0, a.size / 2.0 + tower_d),), near=(sx0, sy0))
    w("; BODY_START")

    E = 0.0
    w(f"G0 F{f} X{sx0:.3f} Y{sy0:.3f} ; HOP prime -> first line, over bare plate")
    fan_on = False
    for _idx, Lay in enumerate(layers):
        li = Lay["li"]
        _zf, _cdiv = Lay["zf"], Lay["cdiv"]
        z = press if li == 0 else z_of(li - 1) + _zf * (z_of(li) - z_of(li - 1))
        w(f"; ---- layer {_idx+1} of {len(layers)}  z {z:.3f}  ({Lay['label']})")
        _is_floor_reg = 0 < li < a.floor_layers
        w(f"G1 F{f_l1 if li == 0 else (f_floor if _is_floor_reg else f)} Z{z:.3f}")
        if li == 1 and not fan_on:                       # from layer 2, exactly as v16 ran
            w(f"M106 S{int(round(fan*255))}     ; {fan*100:.0f}% body fan")
            fan_on = True
        ppx, ppy = Lay["pts"][0]
        for j, (x, y) in enumerate(Lay["pts"][1:]):
            kind = Lay["kind"][j]
            seg = math.hypot(x - ppx, y - ppy)
            if seg < 1e-9:
                continue
            if kind in ("T", "Ti"):
                if li == 0:
                    E += seg * e_mm_l1
                    w(f"G1 F{f_l1} X{x:.3f} Y{y:.3f} E{E:.5f} ; LINK plate-tie at layer 1's rate")
                else:
                    E += seg * e_mm * a.cross_flow
                    w(f"G1 F{f_x} X{x:.3f} Y{y:.3f} E{E:.5f} ; THIN CROSS "
                      f"{a.cross_flow*100:.1f}% -- deliberate strand (clears every post, "
                      f"both rings)")
            elif kind == "M":
                E += seg * (e_mm_l1 if li == 0 else e_mm * merge_flow)
                w(f"G1 F{f_l1 if li == 0 else f} X{x:.3f} Y{y:.3f} E{E:.5f} ; LINK MERGE "
                  f"{100 if li == 0 else merge_flow*100:.0f}% -- net lapped onto the post")
            elif kind in ("B", "Bi"):
                _bm = (Lay["mult"] if kind == "B" else Lay["imult"]) / _cdiv
                _a2 = _bm * bw * lh
                E += seg * e_mm * _bm
                if a.cross_flow > 0 and speed_x != speed and li != 0:
                    w(f"G1 F{f_floor if _is_floor_reg else f}")
                w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f} ; BRIDGE {_bm:g}x {_a2:.4f}mm2 rod "
                  f"{2*math.sqrt(_a2/math.pi):.3f}mm, {seg:.2f}mm tip to tip")
            else:
                _rate = (e_mm_l1 if li == 0 else
                         (e_mm_f if _is_floor_reg else e_mm / _cdiv))
                E += seg * _rate
                if a.cross_flow > 0 and speed_x != speed and li != 0:
                    w(f"G1 F{f_floor if _is_floor_reg else f}")
                if _cdiv > 1 and kind == "E":
                    w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f} ; LINK wall split over {_cdiv} circuits")
                else:
                    w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f}")
            ppx, ppy = x, y

    vol_cm3 = E * A_FIL / 1000.0
    w("M107")
    w("M104 S0")
    w("M140 S0")
    _zr2, _zcap = machine.z_retreat(a.printer, top_z)
    w(f"G0 F{f} Z{_zr2:.2f}")
    w("G0 F3000 X10 Y10")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"art_bucket_{a.printer}_{a.material}_s{a.size:g}_h{a.wall_h:g}_"
                             f"i{a.inner_wall_h:g}_n{n_out}+{n_in}_w{a.wrap_deg:g}_"
                             f"f{a.floor_layers}x{a.net_pitch:g}_b{a.bridge_every}_"
                             f"x{a.cross_flow*100:g}_j{a.merge_mm:g}_{sha_o[:6]}{sha_h[:6]}"
                             f".gcode")
    open(fn, "w").write("\n".join(L) + "\n")

    print(fn)
    print(f"  posts {n_out} outer + {n_in} inner, all crossings dip-free at 1e-9 over "
          f"{n_air} airborne moves; max span {worst_air:.2f}mm (ledger {span_cap:.2f})")
    print(f"  transit gap {TJ}->{TJ+1} via inner post {TK}, legs {tr_len1:.1f}/{tr_len2:.1f}mm "
          f"land mid-arc (no lip cost); exit rib from inner post {exK}")
    print(f"  {n_lay} layers ({a.floor_layers} floor + {n_lay-a.floor_layers} wall), top z "
          f"{top_z:.2f}, inner wall through layer {li_inner_top+1} (z {z_of(li_inner_top):.2f})")
    print(f"  brim {brim_frac_real*100:.0f}% solid ({n_rings} rings; L1 {n_rings1} at {lp1:g}), "
          f"hole {hole_area/area*100:.0f}%, net L1 {net1_pitch:g}mm UNPROVEN pair / upper "
          f"{a.net_pitch:g}mm")
    print(f"  lip budget worst {max(v for _, v in lip_regimes):.3f} vs {lip_proven:.3f} proven; "
          f"M1 landing zone {m1_zone:.3f} (mid-arc, not a mouth)")
    print(f"  {path_mm/1000:.1f}m extruded + {trav_mm/1000:.1f}m crossings, {vol_cm3:.1f} cm3, "
          f"est {mins:.0f} min motion (floor {floor_mins:.0f} min)")
    print(f"  gates: one-stroke, bounds, dip(all-vs-all), Z-monotone, laps, span, lip, rod "
          f"-- all passed on the built points; run validate.py + tools/qa_weld.py next")


def _wrap_to(target, frm):
    """angle `target` expressed <= `frm` (for a CW walk from `frm`)."""
    t = target
    while t > frm + 1e-12:
        t -= 2 * math.pi
    return t


if __name__ == "__main__":
    main()
