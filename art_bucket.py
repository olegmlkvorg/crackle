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
from shapely.ops import unary_union, nearest_points

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
#   3  union every post DISK with every chord strip -- valid chain, but a disk covers the
#      open mouth too: near shallow grazes the boundary followed a phantom bulge and the
#      rails ran just past weld reach of the chord for 17.5mm stretches.
#   4  THIS: union every post MATERIAL SECTOR (arc + tip chord, material_sector) with every
#      chord strip. The chain's largest INTERIOR ring is the floor border exactly, notches
#      included; rails are plain inward buffers -- distance d from chords and feet
#      everywhere, no healing, nothing to bowtie, no phantom material.
def material_sector(c, mu, r_t, toff, seg=0.4):
    """The post's MATERIAL silhouette as a polygon: the toolpath arc trailing->leading
    through the material, auto-closed by the tip chord across the mouth.

    SECTORS, NOT DISKS -- the emitter's own instance of the arc-aware lesson dip() and
    seam_window learned on 2026-08-07: near a shallow graze the crossing chord passes
    legally OVER the open mouth, a full disk bulges past it, the region boundary followed
    the phantom bulge, and the first rail (an offset of that boundary) ran 0.70-0.94mm off
    the chord -- just past the 0.77 weld reach, for exactly the 17.5mm unwelded runs
    qa_weld kept reporting through three wedge models."""
    trail = (c[0] + r_t * math.cos(mu - toff), c[1] + r_t * math.sin(mu - toff))
    return Polygon([trail] + post_arc(c, mu, r_t, None, toff, seg)).buffer(0)


def floor_region_outer(cs, mus, r_t, toff):
    # the chord strips are TOPOLOGICAL GLUE, 0.01mm: a 0.05 strip pushed every rail 0.05
    # further from the border, and 0.656+0.05+join noise landed the whole brim ring ON the
    # weld test's 0.77 threshold -- qa_weld read 36% of the border unwelded by microns.
    chords = ring_chords(cs, mus, r_t, toff)
    chain = unary_union([material_sector(tuple(c), mu, r_t, toff)
                         for c, mu in zip(cs, mus)]
                        + [LineString(ch).buffer(0.01, quad_segs=8) for ch in chords])
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
    chain. Outward buffers of this are the hole-ring rails. Sectors, not disks -- see
    material_sector."""
    chords = ring_chords(cs, mus, r_t, toff)
    chain = unary_union([material_sector(tuple(c), mu, r_t, toff)
                         for c, mu in zip(cs, mus)]
                        + [LineString(ch).buffer(0.01, quad_segs=8) for ch in chords])
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


def wedge_loops(rail_boundary, cs, mus, r_t, toff, d_lo=0.70, d_hi=16.0, seg=1.0):
    """One elongated LOOP per stretch of a crossing chord that the FIRST RAIL pulls away
    from, hung off the chord itself.

    THIRD MODEL, and this one measures the failing quantity directly. The first modelled
    the gap as radial to the post: zero wedges found. The second measured distance to the
    REGION boundary: zero again, because the chord IS that boundary. What actually strands
    the chord is offset corner-cutting: at a shallow chord-arc junction the inward offset
    stays 0.656 from BOTH sides, so near the vertex the rail runs up the bisector and its
    distance from the chord grows to 0.656/sin(theta/2) -- the chord's last 5-15mm has no
    rail within weld reach (qa_weld: 17.5mm unwelded, every run the landing stretch of one
    chord). Where distance(chord, FIRST RAIL) > d_lo a single PASS is laid (midline of the
    gap, or a rib 0.65 off the chord for deep retreats -- regimes and the arithmetic that
    picked them are at the emit site below), spliced into the chord walk so no stub ever
    crosses a bead.

    d_hi is the BRIDGE LEDGER's territory, not a taste ceiling: the loop's open end closes
    with one strand across the full gap, so the widest gap a wedge may span is bounded by
    what this machine bridges (16.0 < PROVEN_AIR_MM). The first value was 8.0 with no stated
    reason, and near a post tip the corner retreat runs PAST 8 -- that chord's last stretch
    got no wedge, its rail sat 0.85mm off (just past the 0.77 weld reach), and qa_weld read
    exactly that as run 15's 7.5mm ATTACH failure beside post 0.

    L2+ floors only: layer 1's w1-wide beads reach its border already (measured 100%).
    Returns {chord_index: [(attach_pt, loop_pts)]}."""
    n = len(cs)
    ch = ring_chords(cs, mus, r_t, toff)
    out = {}
    for k, (p, q) in enumerate(ch):
        L = math.dist(p, q)
        if L < 2 * seg:
            continue
        ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
        m = int(L / seg)
        ds = []
        for i in range(m + 1):
            s = i * seg
            pt = (p[0] + ux * s, p[1] + uy * s)
            np_ = nearest_points(rail_boundary, Point(pt))[0]
            ds.append((pt, (np_.x, np_.y), math.dist(pt, (np_.x, np_.y))))
        i = 0
        while i <= m:
            if ds[i][2] <= d_lo or ds[i][2] > d_hi:
                i += 1
                continue
            j = i
            while j <= m and d_lo < ds[j][2] <= d_hi:
                j += 1
            if j - i >= 2:
                # SINGLE PASSES, NEVER LOOPS. Three two-sided constructions in a row read
                # 2.9-3.6 on qa_weld's depth model, each a different face of one fact: in
                # a corridor 0.8-1.8mm wide bounded by the chord and the rail, ANY second
                # wedge line is within half a bead of something. The model's own arithmetic
                # picks the shape (a bead at distance x contributes sqrt(1-(2x/w)^2), zero
                # past w/2 = 0.41):
                #   gap (0.70,0.77]  NOTHING -- the rail itself is inside the 0.77 reach
                #   gap (0.77,1.54]  MIDLINE -- welds chord AND rail at once (d/2 <= 0.77);
                #                    reads 1.44-1.75 alone, worst at the narrow end
                #   gap (1.54,16]    RIB 0.65 off the CHORD -- the border weld is what
                #                    ATTACH demands and the rib sits on L1's 3.94 rim bead;
                #                    pair with the chord reads 1.22. The rail side of a
                #                    deep retreat stays unstitched, on purpose: a return
                #                    side is the pinch-crossing disease again.
                W_WELD, W_SPLIT, W_RIB = 0.77, 1.54, 0.65
                i2 = i
                while i2 < j:
                    reg = (0 if ds[i2][2] <= W_WELD else
                           1 if ds[i2][2] <= W_SPLIT else 2)
                    j2 = i2
                    while j2 < j and (0 if ds[j2][2] <= W_WELD else
                                      1 if ds[j2][2] <= W_SPLIT else 2) == reg:
                        j2 += 1
                    sub = ds[i2:j2]
                    if reg > 0 and len(sub) >= 2:
                        if reg == 1:
                            rib = [((pt[0] + bp[0]) / 2, (pt[1] + bp[1]) / 2)
                                   for pt, bp, d in sub]
                        else:
                            rib = []
                            for pt, bp, d in sub:
                                vx, vy = (bp[0] - pt[0]) / d, (bp[1] - pt[1]) / d
                                rib.append((pt[0] + W_RIB * vx, pt[1] + W_RIB * vy))
                        out.setdefault(k, []).append((sub[0][0], rib))
                    i2 = j2
            i = j
    return out


def chord_with_wedges(cur, nxt, wedges, seg):
    """The rim chord cur->nxt with each wedge loop spliced in at its attach point: hop off
    the chord 0.4mm, run the loop, hop back to the same chord point, continue. Returns
    (pts, kinds) -- chord body 'R', wedge detours 'E' (full floor flow: they are welds)."""
    body = latch.line_pts(cur, nxt, seg)
    if not wedges:
        return body, ["R"] * len(body)
    pts, kinds = [], []
    assign = {}
    for attach, loop in wedges:
        j = min(range(len(body)), key=lambda i: math.dist(body[i], attach))
        assign.setdefault(j, []).append(loop)
    for i, bp in enumerate(body):
        pts.append(bp)
        kinds.append("R")
        loops = assign.get(i, [])
        for j, loop in enumerate(loops):
            hop = latch.line_pts(pts[-1], loop[0], seg)
            pts += hop
            kinds += ["E"] * len(hop)
            pts += loop[1:]
            kinds += ["E"] * (len(loop) - 1)
            # LAND ON THE NEXT CHORD POINT, never back on the departure point: returning
            # to bp stacked chord + hop-out + hop-back on one spot, and qa_weld read the
            # 67 wedge attach points as run 15's pile zones at 2.9-3.6 bead-heights.
            # Entering and leaving ~1mm apart caps the spot at ~2.0; the skipped 1mm of
            # chord is covered by the loop's near-chord side 0.4 away (welded, one body).
            ret = body[i + 1] if (j == len(loops) - 1 and i + 1 < len(body)) else bp
            back = latch.line_pts(pts[-1], ret, seg)
            pts += back
            kinds += ["E"] * len(back)
    return pts, kinds


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


STITCH_TRIGGER = 8.0
STITCH_REACH = 3.6
STITCH_TOUCH = 0.45          # riding this close to support already counts as held
STITCH_RIDE = 0.8            # the tooth tip RIDES the support bead this far and returns
                             # from the far end -- a tooth that retraced its own leg read
                             # 2.0 deep on itself and was run 17's worst pile (3.5)


def _seg_hash(segs2, cell=4.0):
    """Spatial hash of support segments, sampled every `cell` along each segment so a
    100mm rail straight is findable from every cell it passes through."""
    grid = {}
    for s in segs2:
        (ax, ay), (bx, by) = s
        n2 = max(1, int(math.hypot(bx - ax, by - ay) / cell))
        for k2 in range(n2 + 1):
            t = k2 / n2
            key = (int((ax + (bx - ax) * t) // cell), int((ay + (by - ay) * t) // cell))
            grid.setdefault(key, []).append(s)
    return grid, cell


def _near_seg(grid, cell, p2, r):
    """(dist, seg) of the nearest support segment within r of p2, else (None, None)."""
    gx, gy = int(p2[0] // cell), int(p2[1] // cell)
    best, bseg = None, None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for s in grid.get((gx + dx, gy + dy), ()):
                (ax, ay), (bx, by) = s
                ux, uy = bx - ax, by - ay
                L2 = ux * ux + uy * uy
                t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p2[0] - ax) * ux
                                                           + (p2[1] - ay) * uy) / L2))
                d = math.hypot(p2[0] - (ax + t * ux), p2[1] - (ay + t * uy))
                if d <= r and (best is None or d < best):
                    best, bseg = d, s
    return best, bseg


def dense_path(path, seg):
    """Resample a path so no step exceeds ~1.5*seg. thin() legitimately leaves 10mm+
    straight segments in walk outputs, and every point-based consumer -- the laid grid,
    overlap, repulsion, rib yield -- is blind to a segment's interior: run 21's immune
    3.0 zones were 11mm collinear hops whose interiors no grid ever saw."""
    if len(path) < 2:
        return [tuple(p) for p in path]
    out2 = [tuple(path[0])]
    for p2 in path[1:]:
        p2 = tuple(p2)
        if math.dist(out2[-1], p2) > seg * 1.5:
            out2 += latch.line_pts(out2[-1], p2, seg)
        else:
            out2.append(p2)
    return out2


def stitch_to_grid(pts, sup, seg):
    """Teeth: no stretch of a net-region walk runs past STITCH_TRIGGER mm without touching
    what the layer BELOW actually laid. validate's overhang frame is run length along the
    path, so a walk riding PARALLEL to the support below hangs (metrically) for its whole
    length even though the physical gap under it is one strand pitch -- measured on run 15:
    an 18.0mm lane-walk stretch beside the art hole, 1.9mm of y-drift over 17mm of x.

    `sup` is a _seg_hash of the layer below's hatch RUNS AND RAIL LOOPS, from the same
    cached floor_parts that laid them. The first version knew only the hatch rows, so
    walks near the hole -- fully supported by the layer below's own hole rings, which
    validate sees -- grew teeth anyway, and each tooth retraced its own leg: run 17's
    worst pile (3.5) was one tooth's two legs plus the two walks it stitched. Now a tooth
    lands on the support, rides it STITCH_RIDE, and returns from the far end to the walk's
    NEXT point -- no cell ever carries two of its legs. Worst metric hang between touches:
    a return leg + trigger + an out leg = 3.6 + 8 + 3.6 = 15.2mm < machine.PROVEN_AIR_MM."""
    if not sup or len(pts) < 2:
        return list(pts)
    grid, cell = sup
    out = [tuple(pts[0])]
    run = 0.0
    pend = None                      # tooth tip still to be joined to the walk's next point
    for p2 in pts[1:]:
        p2 = tuple(p2)
        if pend is not None:
            out += latch.line_pts(pend, p2, seg)
            run = math.dist(pend, p2)
            pend = None
            continue
        q2 = out[-1]
        mx, my = (q2[0] + p2[0]) / 2, (q2[1] + p2[1]) / 2
        held = (_near_seg(grid, cell, p2, STITCH_TOUCH)[0] is not None
                or _near_seg(grid, cell, (mx, my), STITCH_TOUCH)[0] is not None)
        run = 0.0 if held else run + math.dist(q2, p2)
        out.append(p2)
        if run > STITCH_TRIGGER:
            d3, s3 = _near_seg(grid, cell, p2, STITCH_REACH)
            if s3 is not None:
                (ax, ay), (bx, by) = s3
                ux, uy = bx - ax, by - ay
                L3 = math.hypot(ux, uy)
                ux, uy = ((ux / L3, uy / L3) if L3 > 1e-12 else (1.0, 0.0))
                s4 = max(0.0, min(L3, (p2[0] - ax) * ux + (p2[1] - ay) * uy))
                np1 = (ax + ux * s4, ay + uy * s4)
                s5 = s4 + STITCH_RIDE if s4 + STITCH_RIDE <= L3 else max(0.0, s4 - STITCH_RIDE)
                np2 = (ax + ux * s5, ay + uy * s5)
                out += latch.line_pts(p2, np1, seg)
                if math.dist(np1, np2) > 1e-9:
                    out += latch.line_pts(np1, np2, seg)
                pend = np2
                run = 0.0
    return out


def lane_walk(lanes, lane_ctr, cur, target, seg, hole_block=None, stitch=None, avoid=None,
              repel=None):
    """A LONG transition rides a LANE -- a closed track buffered INSIDE the net region, so
    its stubs cross only strand rows (point crossings, 2.0 deep, pass). Walking the rails
    themselves stacked every transition onto the same neck stretches beside the art hole:
    qa_weld read 4 passes deep. Lanes at several depths rotate so consecutive walks land on
    different tracks -- but rotation alone still reuses a lane every len(lanes) transitions,
    and two same-lane walks (sampled from different phases, so 0.1mm apart, never welded as
    one) plus one stitch tooth read 3.0 on run 19. So `avoid` measures each candidate walk's
    overlap with material this layer ALREADY laid, and the first lane under 3mm of overlap
    wins; if none qualifies, the least-overlapping. Returns pts."""
    best_fb = None
    for tries in range(len(lanes)):
        lane = lanes[(lane_ctr[0] + tries) % len(lanes)]
        if not poly_parts(lane):
            continue
        out = list(walk_boundary(lane, tuple(cur), tuple(target), seg))
        if out and math.dist(out[-1], tuple(target)) > 1e-9:
            out += latch.line_pts(out[-1], tuple(target), seg)
        out = dense_path(out, seg)
        ov = avoid(out) if avoid else 0.0
        if ov < 3.0:
            lane_ctr[0] += 1 + tries
            out = repel(out) if repel else out
            return stitch(out) if stitch else out
        if best_fb is None or ov < best_fb[0]:
            best_fb = (ov, tries, out)
    if best_fb is not None:
        lane_ctr[0] += 1 + best_fb[1]
        out = best_fb[2]
        out = repel(out) if repel else out
        return stitch(out) if stitch else out
    if hole_block is not None and LineString(
            [tuple(cur), tuple(target)]).intersects(hole_block):
        raise SystemExit("REFUSING TO EMIT: no lane exists and the straight fallback for a "
                         "net transition crosses the art hole.")
    out = latch.line_pts(tuple(cur), tuple(target), seg)
    out = repel(out) if repel else out
    return stitch(out) if stitch else out


def chain_hatch(runs, lanes, lane_ctr, hole_block, start, seg, angle_deg, stitch=None,
                mark=None, avoid=None, repel=None, fat_region=None):
    """One-stroke chain: monotone-column serpentines; short neighbour links straight, long
    transitions as rotated lane walks (a straight cross-region link floated 42.8mm on the
    first emission; a rail walk piled 4 deep on the second). `mark` records each piece into
    the layer's laid-material grid AS IT IS BUILT, so `avoid` sees this net's own strands
    and earlier walks, not just what preceded the net. Returns pts EXCLUDING start."""
    cols = monotone_columns(runs, angle_deg)
    out = []

    def emit(newpts):
        out.extend(newpts)
        if mark and newpts:
            mark(newpts)

    cur = np.array(start)
    # TWO-PHASE ORDER: columns in PINCHED throats go LAST, as one cluster. The global
    # greedy bounced in and out of the throat between the outer border and the cut, and
    # every re-entry laid another transit through cells already carrying the serpentine's
    # own out-and-back -- run 22's stubborn 3.0 cells were exactly one early transit plus
    # that pair, where the hole guard leaves repulsion nowhere to push. Fat first, then
    # each pinched cluster in a single visit: the removable pass never gets laid.
    if fat_region is not None:
        fat, pinched = [], []
        for c in cols:
            if not c:
                continue
            ends = [p for r in c for p in (r[2], r[3])]
            cx2 = sum(p[0] for p in ends) / len(ends)
            cy2 = sum(p[1] for p in ends) / len(ends)
            (fat if fat_region.contains(Point((cx2, cy2))) else pinched).append(c)
        phases = [ph for ph in (fat, pinched) if ph]
    else:
        phases = [[c for c in cols if c]]
    for todo in phases:
      while todo:
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
        for (x0, x1, a, b) in col:
            if math.dist(cur, b) < math.dist(cur, a):
                a, b = b, a
            link = LineString([tuple(cur), tuple(a)])
            if link.length > 1e-9:
                if link.length > 6.0 or link.intersects(hole_block):
                    emit(lane_walk(lanes, lane_ctr, cur, a, seg,
                                   hole_block=hole_block, stitch=stitch, avoid=avoid,
                                   repel=repel))
                    if out and math.dist(out[-1], tuple(a)) > 1e-9:
                        emit(latch.line_pts(out[-1], tuple(a), seg))
                else:
                    lk = latch.line_pts(tuple(cur), tuple(a), seg)
                    emit(repel(lk) if repel else lk)
            emit(latch.line_pts(tuple(a), tuple(b), seg))
            cur = np.array(b)
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

    # the finder measures against the rails AS EMITTED (poly_parts-filtered ring loops):
    # `.boundary` of the raw buffer still sees sliver parts that poly_parts drops before
    # emission, so it reported a rail at 0.666 that no plate would ever carry.
    from shapely.geometry import MultiLineString
    _rails_out = MultiLineString([r9 for _, r9 in ring_loops_out(FR, [lp])])
    _rails_in = MultiLineString([r9 for _, r9 in ring_loops_in(HR, [lp])])
    o_wedges = wedge_loops(_rails_out, o_cs, o_mu, r_t, toff)
    i_wedges = wedge_loops(_rails_in, i_cs, i_mu, r_t, toff)

    def floor_parts(lpx, nrx, nhx, netp, ang):
        rings = ring_loops_out(FR, [lpx * (1 + i) for i in range(nrx)])
        hrings = ring_loops_in(HR, [lpx * (1 + i) for i in range(nhx)])
        N = FR.buffer(-lpx * nrx, quad_segs=24).difference(
            HR.buffer(lpx * nhx, quad_segs=24))
        runs = hatch_runs(N, netp, ang)
        # five depths, not three: rotation reuses a lane every len(lanes) transitions, and
        # the avoid() check needs somewhere else to go when it refuses a collision
        lanes = [N.buffer(-1.2 * (i + 1), quad_segs=16) for i in range(5)]
        return rings, hrings, N, runs, lanes

    _fp_cache = {}

    def _fp(li):
        """floor_parts for layer li, computed once. Layer li+1's stitching reads layer li's
        ACTUAL hatch runs from here -- support is what was laid, by the same code path,
        never re-derived by a second one."""
        if li not in _fp_cache:
            _fp_cache[li] = floor_parts(lp1 if li == 0 else lp,
                                        n_rings1 if li == 0 else n_rings,
                                        nh1 if li == 0 else nh,
                                        net1_pitch if li == 0 else a.net_pitch,
                                        90.0 * (li % 2))
        return _fp_cache[li]

    # THE RIM-CIRCUIT ENTRY WALKS THE RIM TRACK; it never cuts the chord. Found on run 15's
    # emitted bytes: the straight entry from wherever the hole-ring walk ended to exK's
    # trailing tip laid a ~155mm full-flow bar with 143.5mm of it ACROSS THE CUT, on every
    # floor layer on a different track. validate flagged only L2's (a 114.3mm float over
    # L1's air); the L1 bar welded to the plate and NO gate looked at it -- three link gates
    # each guarded their own construct and this entry was nobody's. The track sits 0.3 bead
    # inside the innermost hole ring: inside the L1 rim bead's cover (layers 2+ supported),
    # off the ring and off the border chords (stacks on neither).
    rim_walk = HR.buffer(0.3 * bw, quad_segs=24)

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

    def inner_rim_circuit(entry_pt, start_k, wedges_fn, mark=None):
        """Inner posts + EXTRUDED chords starting at start_k's trailing tip, full circuit.
        Each chord carries its wedge ribs (chord_with_wedges); `wedges_fn(k2)` is asked at
        splice time so a rib can yield to material laid earlier in this same circuit, and
        `mark` records each chord's output so the NEXT chord's ribs see it."""
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
            cp, ck = chord_with_wedges(pts[-1], nxt, wedges_fn(k2), SEG)
            pts += cp
            kinds += ck
            if mark:
                mark(cp)
        return pts, kinds

    def floor_layer(li, entry):
        """One whole floor layer from `entry` (== starts[0]) back to starts[0]."""
        ang = 90.0 * (li % 2)
        rings, hrings, N, runs, lanes = _fp(li)
        # stitch teeth target what the layer BELOW actually laid -- its hatch runs AND its
        # rail loops (rows alone grew teeth over ring-supported ground); layer 1 sits on
        # the plate and needs none
        if li > 0:
            prin, phrin, _, pruns, _ = _fp(li - 1)
            ssegs = [(tuple(a2), tuple(b2)) for a2, b2 in pruns]
            for _, lp2 in prin + phrin:
                ssegs += list(zip([tuple(v) for v in lp2[:-1]],
                                  [tuple(v) for v in lp2[1:]]))
            _sup = _seg_hash(ssegs)
            st = lambda pp: stitch_to_grid(pp, _sup, SEG)
        else:
            st = None
        lane_ctr = [li]                              # rotate lane choice per layer too
        pts, kinds = [], []
        cur = entry

        # THE LAYER'S LAID-MATERIAL GRID -- separate from go_rail's dedup grid on purpose
        # (that one holds rail points only; feeding it links would re-open the seam gap the
        # closure fix just closed). Two consumers: ribs YIELD to fill that already welds
        # their border stretch, and lane walks AVOID stretches another transition laid.
        _laid_all = {}

        def _mark_all(newpts):
            # marks interpolate ALONG each segment: thin() leaves 10mm+ straights whose
            # interiors a vertex-only grid never records (run 21's immune zones)
            prev = None
            for p2 in newpts:
                if prev is not None:
                    n2 = int(math.dist(prev, p2))
                    for k2 in range(1, n2 + 1):
                        t2 = k2 / (n2 + 1)
                        q2 = (prev[0] + (p2[0] - prev[0]) * t2,
                              prev[1] + (p2[1] - prev[1]) * t2)
                        _laid_all.setdefault((int(q2[0] // 2.0), int(q2[1] // 2.0)),
                                             []).append(q2)
                _laid_all.setdefault((int(p2[0] // 2.0), int(p2[1] // 2.0)), []).append(p2)
                prev = p2

        def _overlap_mm(walk_pts):
            tot = 0.0
            for p2 in walk_pts:
                gx, gy = int(p2[0] // 2.0), int(p2[1] // 2.0)
                if any(math.dist(p2, q2) < 0.5
                       for dx2 in (-1, 0, 1) for dy2 in (-1, 0, 1)
                       for q2 in _laid_all.get((gx + dx2, gy + dy2), ())):
                    tot += 1.0                       # walk points are ~1mm apart
            return tot

        def rib_yield(entries, ch_pq):
            """Drop rib stretches whose border is ALREADY welded by laid fill. Run 19's
            two worst zones were transition hops welding the border themselves with the
            rib doubled over them. The qualifying annulus honours the classifier:
            material within 0.68 of the border sample welds it (reach 0.77), but only if
            it sits farther than 0.45 off the chord LINE -- closer classifies RIM, and a
            RIM bead holds no chord sample (the entry-link lesson). Two qualifying
            vertices required, so one stray point cannot delete a rib the border then
            misses; a kept rib is the status quo, never a regression."""
            if not entries:
                return []
            (cpx, cpy), (cqx, cqy) = ch_pq
            ux, uy = cqx - cpx, cqy - cpy
            LL = math.hypot(ux, uy)
            if LL < 1e-9:
                return entries
            ux, uy = ux / LL, uy / LL
            out2 = []
            for _attach, rib in entries:
                keep = []
                for r2 in rib:
                    t2 = (r2[0] - cpx) * ux + (r2[1] - cpy) * uy
                    fx, fy = cpx + ux * t2, cpy + uy * t2
                    nq = 0
                    gx, gy = int(fx // 2.0), int(fy // 2.0)
                    for dx2 in (-1, 0, 1):
                        for dy2 in (-1, 0, 1):
                            for q2 in _laid_all.get((gx + dx2, gy + dy2), ()):
                                if math.dist(q2, (fx, fy)) <= 0.68:
                                    dperp = abs(-(q2[0] - cpx) * uy + (q2[1] - cpy) * ux)
                                    if dperp > 0.45:
                                        nq += 1
                    keep.append(nq < 2)
                i3 = 0
                while i3 < len(rib):
                    if not keep[i3]:
                        i3 += 1
                        continue
                    j3 = i3
                    while j3 < len(rib) and keep[j3]:
                        j3 += 1
                    if j3 - i3 >= 2:
                        r0 = rib[i3]
                        t2 = (r0[0] - cpx) * ux + (r0[1] - cpy) * uy
                        out2.append(((cpx + ux * t2, cpy + uy * t2), rib[i3:j3]))
                    i3 = j3
            return out2

        def _repel(path):
            """Nudge a transition's mid-course off material this layer already laid, to
            0.85mm clearance (past capsule half-width, so neither bead reads on the
            other's depth). Run 20's stubborn 3.0 zones were four near-parallel transition
            passes 0.1-0.7 apart beside the hole band -- avoidance can pick another lane,
            but every hop CONVERGES on its target, so spacing has to be enforced on the
            path itself. First/last ~2 points stay put (they weld to their anchors, and
            endpoint contact is path-adjacent, which the depth model merges anyway); a
            nudge that would enter the hole guard is dropped."""
            if len(path) < 5:
                return path
            out2 = [path[0]]
            for i2 in range(1, len(path)):
                p2 = tuple(path[i2])
                if 2 <= i2 <= len(path) - 3:
                    gx, gy = int(p2[0] // 2.0), int(p2[1] // 2.0)
                    best = None
                    for dx2 in (-1, 0, 1):
                        for dy2 in (-1, 0, 1):
                            for q2 in _laid_all.get((gx + dx2, gy + dy2), ()):
                                d2 = math.dist(p2, q2)
                                if d2 < 0.85 and (best is None or d2 < best[0]):
                                    best = (d2, q2)
                    if best and best[0] > 1e-9:
                        d2, q2 = best
                        ux2, uy2 = (p2[0] - q2[0]) / d2, (p2[1] - q2[1]) / d2
                        cands = [(q2[0] + ux2 * 0.85, q2[1] + uy2 * 0.85)]
                        # VETO-AWARE: in the throat the natural push lands in the hole
                        # guard and was silently dropped -- run 22's 3.0 cells sat 0.01
                        # off their neighbour with repel formally 'on'. Second try pushes
                        # AWAY FROM THE HOLE (one consistent direction, no zigzag). Any
                        # candidate must keep >= 0.6 clearance from all OTHER laid
                        # material: landing 0.3 off the next rail just moves the pile.
                        rr2 = math.hypot(p2[0] - hc[0], p2[1] - hc[1])
                        if rr2 > 1e-9:
                            cands.append((q2[0] + (p2[0] - hc[0]) / rr2 * 0.85,
                                          q2[1] + (p2[1] - hc[1]) / rr2 * 0.85))
                        for cand in cands:
                            if hole_block.contains(Point(cand)):
                                continue
                            gx2, gy2 = int(cand[0] // 2.0), int(cand[1] // 2.0)
                            dmin = min((math.dist(cand, q3)
                                        for dx3 in (-1, 0, 1) for dy3 in (-1, 0, 1)
                                        for q3 in _laid_all.get((gx2 + dx3, gy2 + dy3), ())),
                                       default=9.9)
                            if dmin >= 0.6:
                                p2 = cand
                                break
                out2.append(p2)
            return out2

        def go(newpts, kind="E"):
            nonlocal cur
            pts.extend(newpts)
            kinds.extend([kind] * len(newpts))
            if newpts:
                cur = newpts[-1]
                _mark_all(newpts)

        # NECK DEDUP. At a tapering neck (the ear junctions) a rail's two sides sweep through
        # coincidence with the next rail's -- 2-3 rail beads inside a third of a millimetre,
        # by offset geometry, and qa_weld reads 3.0 bead-heights there. A deeper rail SKIPS
        # stretches within 0.5mm of already-laid rail material (0.5 < the 0.656 pitch, so a
        # normal neighbour is never dropped) and bridges along the laid path instead:
        # deliberate coincidence at 2.0 in place of jittered triples at 3.0.
        _laid = {}

        def _mark(p2):
            _laid.setdefault((int(p2[0] // 2.0), int(p2[1] // 2.0)), []).append(p2)

        def _near_laid(p2, r=0.5):
            gx, gy = int(p2[0] // 2.0), int(p2[1] // 2.0)
            for dx2 in (-1, 0, 1):
                for dy2 in (-1, 0, 1):
                    for q2 in _laid.get((gx + dx2, gy + dy2), ()):
                        if math.dist(p2, q2) < r:
                            return True
            return False

        def go_rail(loop_r):
            keep = [not _near_laid(p2) for p2 in loop_r]
            segs2 = []
            for j2, p2 in enumerate(loop_r):
                if keep[j2]:
                    if segs2 and segs2[-1][-1] == j2 - 1:
                        segs2[-1].append(j2)
                    else:
                        segs2.append([j2])
            if not segs2:
                return
            for sub in segs2:
                block = [loop_r[j2] for j2 in sub]
                # a dedup split can put consecutive kept stretches far apart; a straight
                # link that would cross the cut instead FOLLOWS THE RING's own points to
                # the next block (the deliberate-coincidence idiom, 2.0 deep and
                # gate-visible -- run 23's reordered net shifted a hole-ring walk until
                # its dedup link cut the guard, and the refusal fired as designed).
                # Sub-2.5mm links are exempt: two ring points legitimately inside the
                # 1mm guard band joined by a 0.74mm step tripped this three times (the
                # exit rib documented the same anchor-point trap); a bar across the cut
                # is many mm, never a vertex step.
                if (math.dist(cur, block[0]) > 2.5 and
                        LineString([tuple(cur), tuple(block[0])]).intersects(hole_block)):
                    # nearest vertex BEFORE the block, not globally nearest: at a neck the
                    # loop passes close to itself and the global nearest snaps to the far
                    # side, past the block (run 23b's refusal). Consecutive ring vertices
                    # never cross the guard, so reaching loop_r[sub[0]-1] settles it.
                    if sub[0] > 0:
                        j9 = min(range(sub[0]), key=lambda j2: math.dist(loop_r[j2], cur))
                        if not LineString([tuple(cur),
                                           tuple(loop_r[j9])]).intersects(hole_block):
                            go(latch.line_pts(cur, loop_r[j9], SEG))
                            go(loop_r[j9 + 1:sub[0]])
                    if LineString([tuple(cur), tuple(block[0])]).intersects(hole_block):
                        raise SystemExit(
                            f"REFUSING TO EMIT: a rail dedup link crosses the art hole "
                            f"even along the ring. cur=({cur[0]:.2f},{cur[1]:.2f}) -> "
                            f"block0=({block[0][0]:.2f},{block[0][1]:.2f}), sub[0]={sub[0]}"
                            f"/{len(loop_r)}, kept_runs={len(segs2)}, "
                            f"first_kept={segs2[0][0]}, li={li}")
                lnk = latch.line_pts(cur, block[0], SEG)
                go(lnk)
                go(block)
                for p2 in block:
                    _mark(p2)

        # A ROTATED LOOP WALK MUST BE RE-CLOSED. loop[j0+1:] + loop[:j0+1] starts at vertex
        # j0+1 and ends at vertex j0 -- the seam segment j0 -> j0+1 is never laid. Usually
        # that is a sub-mm vertex gap; on run 16 the rotation landed where ring0's next
        # segment was a 13.6mm STRAIGHT rail stretch, so 13.6mm of rail was silently absent:
        # qa_weld read the border unwelded there (the 7.5mm ATTACH) while the wedge finder,
        # measuring the GEOMETRIC loop seam included, saw 0.669mm and laid nothing. Both
        # instruments were honest; the walk dropped a segment.
        def rot_closed(loop_r, j0):
            rot = loop_r[j0 + 1:] + loop_r[:j0 + 1]
            rot.append(rot[0])
            return rot

        for _, loop in rings:                                    # brim, outermost first
            j0 = min(range(len(loop)), key=lambda j2: math.dist(loop[j2], cur))
            if LineString([cur, loop[j0]]).intersects(hole_block):
                raise SystemExit("REFUSING TO EMIT: a brim link crosses the art hole.")
            go_rail(rot_closed(loop, j0))
        net_start = cur
        # two-phase order only where the strands run PERPENDICULAR to the throat's long
        # axis: run 23 measured it on both -- ang=90 (L2) cleared the throat 66->33 worst
        # 3.0->2.9, ang=0 (L3) regressed 38->105 worst 2.9->3.7, because for parallel
        # strands the pinched columns ARE the throat rows and clustering them last stacks
        # their own transitions
        go(chain_hatch(runs, lanes, lane_ctr, hole_block, net_start, SEG, ang, stitch=st,
                       mark=_mark_all, avoid=_overlap_mm, repel=_repel,
                       fat_region=N.buffer(-2.0, quad_segs=8) if ang == 90.0 else None))
        for hi, (_, loop) in enumerate(hrings):                  # hole rings, outermost first
            j0 = min(range(len(loop)), key=lambda j2: math.dist(loop[j2], cur))
            if hi == 0 and math.dist(cur, loop[j0]) > 6.0:
                # the approach from the net's last strand to the hole rings: a straight hop
                # here floats over sparse net and draws a line across the art -- walk N's
                # hole-side boundary, which IS the outermost hole rail. Densified and
                # repelled like every other transition: it was the third pass at several
                # of run 20's boundary-crowding zones.
                go(_repel(dense_path(walk_boundary(N, tuple(cur), loop[j0], SEG), SEG)))
                if math.dist(cur, loop[j0]) > 1e-9:
                    go(latch.line_pts(cur, loop[j0], SEG))
            # gate the REMAINING link, after the approach walk that replaces the long
            # straight -- gating before the routing decision refused the route it would
            # never take (the reordered net ends inside the throat now). Sub-2.5mm steps
            # between band-adjacent points are the anchor-point trap, exempt.
            if (math.dist(cur, loop[j0]) > 2.5
                    and LineString([cur, loop[j0]]).intersects(hole_block)):
                raise SystemExit("REFUSING TO EMIT: a hole-ring link crosses the art hole.")
            go_rail(rot_closed(loop, j0))
        t0e = tips_of(i_cs[exK], i_mu[exK], r_t, toff)[1]
        if math.dist(cur, t0e) > 6.0:
            go(walk_boundary(rim_walk, tuple(cur), t0e, SEG))
        # gate the entry PAST its last 2.5mm: the tip sits inside the hole's 1mm guard band
        # by construction -- the exit rib documented this same anchor-point trap, and the
        # untrimmed form of this check re-walked into it (refused a clean walk at its own
        # landing). The question is whether the APPROACH crosses the cut, never whether it
        # lands on its own post. PROVEN ABLE TO FIRE 2026-08-09: a mutant with the walk
        # disabled was refused here at the straight 155mm entry, exit 1.
        _d0 = math.dist(cur, t0e)
        if _d0 > 2.5:
            _t1 = 1.0 - 2.5 / _d0
            _stop = (cur[0] + (t0e[0] - cur[0]) * _t1, cur[1] + (t0e[1] - cur[1]) * _t1)
            if LineString([tuple(cur), _stop]).intersects(hole_block):
                raise SystemExit("REFUSING TO EMIT: the rim-circuit entry crosses the art "
                                 "hole.")
        rp, rk = inner_rim_circuit(cur, exK,
                                   (lambda k2: rib_yield(i_wedges.get(k2, []), i_ch[k2]))
                                   if li > 0 else (lambda k2: []),
                                   mark=_mark_all)
        pts += rp
        kinds += rk
        cur = pts[-1]
        go(latch.line_pts(cur, start0, SEG))                     # the exit rib
        # outer posts + extruded rim chords, each chord carrying its wedge loops
        for k in range(n_out):
            arc = post_arc(o_cs[k], o_mu[k], r_t, None, toff, SEG)
            go(arc)
            nxt = trailing((k + 1) % n_out)
            ow = rib_yield(o_wedges.get(k, []), o_ch[k]) if li > 0 else []
            cp, ck = chord_with_wedges(cur, nxt, ow, SEG)
            pts += cp
            kinds += ck
            _mark_all(cp)
            cur = pts[-1]
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
    w(f"; RIM_ENTRY=walked on the rim track ({0.3*bw:.2f}mm inside the innermost hole ring), "
      f"never a chord across the cut (run 15's straight entry laid 143.5mm of full-flow bar "
      f"THROUGH the cut, ungated -- three link gates each guarded their own construct and "
      f"this entry was nobody's)")
    w(f"; NET_STITCH=teeth every {STITCH_TRIGGER:g}mm on net-region walks, reach "
      f"{STITCH_REACH:g}mm, to the layer below's own strands AND rails; each tooth rides "
      f"the support {STITCH_RIDE:g}mm and returns from the far end (a retraced leg reads "
      f"2.0 deep on itself); worst metric hang {STITCH_TRIGGER + 2*STITCH_REACH:g}mm "
      f"< {PROVEN_AIR_MM:g} proven air")
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
      f"{sum(len(v) for v in o_wedges.values())}+{sum(len(v) for v in i_wedges.values())} "
      f"tip-wedge RIBS welding shallow-graze chords (single pass: gap midline to 1.54mm, "
      f"a rib 0.65 off the chord beyond -- every two-sided loop read 2.9+ on the depth "
      f"model somewhere along its pinch); gate tools/qa_weld.py")
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
