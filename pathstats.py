#!/usr/bin/env python3
"""Measure a toolpath: self-intersections, member lengths, speed uniformity.

This is the harness that turns any candidate curve into a DIAL. The crackle thesis is that fused
crossings snapping make the sound, so a path is only useful if we can count its crossings and see
how they respond to a parameter. Everything here is numeric — no design is accepted on the strength
of an argument about what it "should" do.

Three numbers, and each one exists because a specific mistake was made without it:

  crossings        — the control variable. Counted by actual segment intersection, never assumed
                     from the formula, because a formula's predicted count and a sampled path's
                     real count diverge whenever the sampling is coarse.

  member lengths   — distance along the path between consecutive crossings. This is the crackle-
                     relevant one: short stiff spans BEND (the quiet hex-grid feel Oleg rejected),
                     slender spans SNAP. A design can have excellent crossing counts and still be
                     silent if every member is 3mm long.

  speed uniformity — fraction of path length where curvature forces the planner below 90% of the
                     commanded feedrate. The whole reason for leaving the pillar lattice was that
                     the head decelerated into every pillar, so strand cross-section varied along
                     its length. A "continuous" curve that is secretly corner-limited fixes nothing.

Usage:
    from pathstats import analyse
    analyse(points, feed_mms=200, accel=8000, label="lissajous a=5 b=7")
"""
import math
from collections import defaultdict


def _orient(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _seg_intersect(p1, p2, p3, p4):
    """PROPER (transversal) crossing only — segments that merely TOUCH do not count.

    History, because this cost a false alarm: the first version required the intersection to be
    strictly interior to both segments, which silently dropped crossings landing exactly on a
    sampled vertex (symmetric curves put them there systematically — the figure-8's single crossing
    vanished). Loosening to a closed interval fixed that and immediately created a worse bug: every
    place three or more segments MEET at a shared point became a 'crossing'. In this project every
    pillar is a hub where a strand arrives and a diamond opens and closes, so coupon B measured 45
    crossings when it has none by construction, and the negative control looked broken when it was
    fine.

    Orientation signs are the right test: a proper crossing requires each segment's endpoints to
    lie on OPPOSITE sides of the other segment. Touching yields a zero orientation and is excluded.
    Vertex-coincident crossings are then a SAMPLING problem, solved by sampling off-vertex, not by
    weakening the geometry test."""
    d1 = _orient(p3, p4, p1)
    d2 = _orient(p3, p4, p2)
    d3 = _orient(p1, p2, p3)
    d4 = _orient(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and \
       min(abs(d1), abs(d2), abs(d3), abs(d4)) > 1e-9:
        x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
        den = (x2-x1)*(y4-y3) - (y2-y1)*(x4-x3)
        if abs(den) < 1e-12:
            return None
        t = ((x3-x1)*(y4-y3) - (y3-y1)*(x4-x3)) / den
        return (x1 + t*(x2-x1), y1 + t*(y2-y1), t)
    return None


def crossings(pts, cell=None):
    """Self-intersections via a uniform grid. Naive O(n^2) is unusable past a few thousand points
    (a 10k-point path is 50M pair tests in Python); bucketing by cell makes it near-linear."""
    n = len(pts) - 1
    if n < 3:
        return [], []
    # A CLOSED path's first and last segments meet at the closing vertex — they are adjacent in
    # reality but maximally distant in index, so the |i-j|<2 rule misses them and every closed curve
    # reports one phantom crossing. (A circle should have zero.)
    closed = math.dist(pts[0], pts[-1]) < 1e-6
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    if cell is None:
        cell = max(span / 64.0, 1e-6)
    grid = defaultdict(list)
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        for gx in range(int(min(ax, bx) // cell), int(max(ax, bx) // cell) + 1):
            for gy in range(int(min(ay, by) // cell), int(max(ay, by) // cell) + 1):
                grid[(gx, gy)].append(i)
    seen = set(); hits = []
    for bucket in grid.values():
        for ii in range(len(bucket)):
            for jj in range(ii + 1, len(bucket)):
                i, j = bucket[ii], bucket[jj]
                gap = abs(i - j)
                if gap < 2 or (closed and gap >= n - 1):   # adjacent, or adjacent across the seam
                    continue
                key = (i, j) if i < j else (j, i)
                if key in seen:
                    continue
                seen.add(key)
                r = _seg_intersect(pts[i], pts[i + 1], pts[j], pts[j + 1])
                if r:
                    hits.append((min(i, j), max(i, j), r[0], r[1]))
    # dedupe geometrically: one physical crossing can be reported by several segment pairs when it
    # sits on or near a vertex
    uniq = {}
    for h in hits:
        key = (round(h[2] / 0.05), round(h[3] / 0.05))
        if key not in uniq:
            uniq[key] = h
    hits = list(uniq.values())
    return hits, sorted(set(h[0] for h in hits) | set(h[1] for h in hits))


def analyse(pts, feed_mms=200.0, accel=8000.0, label="", quiet=False):
    seglen = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seglen)
    hits, cross_segs = crossings(pts)

    # member lengths: path distance between consecutive crossings
    cum = [0.0]
    for s in seglen:
        cum.append(cum[-1] + s)
    cpos = sorted(cum[i] for i in cross_segs)
    members = [b - a for a, b in zip(cpos, cpos[1:])] if len(cpos) > 1 else []

    # SPEED UNIFORMITY — Klipper's own junction model, not a circle fitted through three points.
    # The fitted-circle version was wrong in the way that matters: for a square with 60mm sides it
    # returned a 42mm radius (geometrically true, physically meaningless) and declared a 90-degree
    # corner fast. A polyline vertex is a DIRECTION DISCONTINUITY — its speed limit does not depend
    # on how long the neighbouring segments are.
    #
    # Klipper: junction_deviation = scv^2 * (sqrt(2)-1) / accel
    #          sin_half = sin(turn/2);  R = jd * sin_half / (1 - sin_half);  v = sqrt(R * accel)
    # which yields exactly square_corner_velocity at a 90-degree corner, as it should.
    # Arcs are additionally limited by centripetal accel, v = sqrt(accel * R_arc); take the lower.
    SCV = 5.0
    jd = SCV ** 2 * (math.sqrt(2.0) - 1.0) / accel
    slow = 0.0
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        d1 = math.dist(a, b); d2 = math.dist(b, c)
        if d1 < 1e-9 or d2 < 1e-9:
            continue
        cosang = ((b[0]-a[0])*(c[0]-b[0]) + (b[1]-a[1])*(c[1]-b[1])) / (d1*d2)
        cosang = max(-1.0, min(1.0, cosang))
        turn = math.acos(cosang)                     # 0 = straight ahead
        # Klipper's term is cos(turn/2), NOT sin(turn/2): straight ahead must give an INFINITE
        # junction radius and a 180-degree reversal must give zero. Getting this backwards made
        # filleting look worse than sharp corners, which is how the error surfaced.
        sin_half = math.cos(turn / 2.0)
        if sin_half >= 1.0 - 1e-9:
            v_corner = float('inf')          # straight
        elif sin_half < 1e-9:
            v_corner = 0.0                   # full reversal
        else:
            v_corner = math.sqrt(jd * sin_half / (1.0 - sin_half) * accel)
        # centripetal limit of the local arc (only meaningful once sampling is fine)
        if turn > 1e-9 and max(d1, d2) < 5.0:
            R_arc = ((d1 + d2) / 2.0) / (2.0 * math.sin(turn / 2.0))
            v_corner = min(v_corner, math.sqrt(accel * R_arc))
        if v_corner < 0.9 * feed_mms:
            slow += d2
    frac_slow = slow / total if total else 0.0

    st = dict(points=len(pts), path_mm=round(total, 1), crossings=len(hits),
              members=len(members),
              member_mean=round(sum(members)/len(members), 2) if members else 0.0,
              member_min=round(min(members), 2) if members else 0.0,
              member_max=round(max(members), 2) if members else 0.0,
              frac_below_90pct=round(frac_slow, 3))
    if not quiet:
        print(f"{label or 'path'}: {st['points']} pts, {st['path_mm']}mm")
        print(f"  crossings {st['crossings']}   members {st['members']} "
              f"(mean {st['member_mean']}mm, min {st['member_min']}, max {st['member_max']})")
        print(f"  path below 90% of {feed_mms:.0f}mm/s: {st['frac_below_90pct']*100:.1f}%")
    return st


if __name__ == "__main__":
    import sys
    # self-test on shapes with a KNOWN answer — a harness nobody has checked is not a harness
    def circle(n=400, r=25, cx=30, cy=30):
        return [(cx + r*math.cos(2*math.pi*i/n), cy + r*math.sin(2*math.pi*i/n)) for i in range(n+1)]
    def fig8(n=801, A=25, cx=30, cy=30):     # Lissajous 1:2 — exactly ONE self-crossing.
        # odd n + half-step offset so the crossing does NOT land on a sampled vertex; a proper
        # crossing test cannot see a touch, so the sampling must not manufacture one.
        # 0.37 (not 0.5): with an offset of exactly half a step and n odd, s=0.5 STILL lands on a
        # sample and the crossing sits on a vertex again. An irrational-ish offset avoids it.
        return [(cx + A*math.sin(2*math.pi*(i+0.37)/n), cy + A*math.sin(4*math.pi*(i+0.37)/n))
                for i in range(n+1)]
    def liss(a, b, n=4000, A=28, cx=30, cy=30, d=math.pi/2):
        return [(cx + A*math.sin(a*2*math.pi*i/n + d), cy + A*math.sin(b*2*math.pi*i/n))
                for i in range(n+1)]
    print("SELF-TEST (expected values in brackets)")
    c = analyse(circle(), label="circle [0 crossings]", quiet=True)
    print(f"  circle          crossings={c['crossings']}  expect 0   "
          f"{'OK' if c['crossings']==0 else 'FAIL'}")
    f = analyse(fig8(), label="figure-8", quiet=True)
    print(f"  figure-8        crossings={f['crossings']}  expect 1   "
          f"{'OK' if f['crossings']==1 else 'FAIL'}")
    for a, b in ((3,4),(5,7),(7,9),(9,11)):
        s = analyse(liss(a,b), quiet=True)
        print(f"  lissajous {a}:{b}   crossings={s['crossings']:>4}  members mean "
              f"{s['member_mean']:>5}mm  slow {s['frac_below_90pct']*100:>4.1f}%")
