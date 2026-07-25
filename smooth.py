#!/usr/bin/env python3
"""Round every corner in a toolpath. Oleg, 2026-07-25: "not sharp angles, make sure you use
semi circlish always".

WHY, in one line: a sharp corner forces the head to stop and re-accelerate, and since extrusion is
commanded per mm of PATH rather than per second, a slow corner deposits the same plastic over less
ground — a blob at every vertex, and thin strands everywhere else.

THE MINIMUM RADIUS IS COMPUTABLE, NOT A MATTER OF TASTE:
    a corner of radius R can be taken at v = sqrt(a * R)
    so holding speed v needs  R >= v^2 / a
At 235 mm/s with accel 8000 that is 6.9 mm. Below it the planner slows down whether or not the
gcode says so — and it does it silently, which is how a "constant speed" path stops being one.

Filleting also SHORTENS the path slightly (a chord cut across each corner), so extrusion per mm is
unchanged but total material drops a little. Reported, not hidden.
"""
import math


def min_radius(speed_mms, accel=8000.0):
    """Smallest corner radius that can be taken at speed without the planner intervening."""
    return speed_mms ** 2 / accel


def seg_for(speed_mms, r, accel=8000.0, scv=5.0):
    """Longest arc sample that still allows `speed` around radius `r`.

    Junction speed depends on the turn angle PER SAMPLE, so how finely an arc is sampled — not its
    radius — sets the ceiling at high feedrates. A 0.6mm sample on an 8mm arc caps the head at
    121 mm/s no matter how gentle the curve is. Measured 2026-07-25 while chasing why a 12mm fillet
    scored worse than an 8mm one."""
    jd = scv ** 2 * (math.sqrt(2.0) - 1.0) / accel
    k = speed_mms ** 2 / (jd * accel)
    h = math.acos(min(1.0, k / (1.0 + k)))
    return max(2.0 * r * h, 0.05)


def fillet(pts, r, arc_seg=None, closed=False, speed=None, accel=8000.0):
    """Replace each interior vertex with a circular arc of radius <= r.

    The radius is capped per-corner by the shorter adjacent segment: you cannot cut a 10mm arc into
    a 3mm segment. Corners that are already gentle are left alone."""
    if arc_seg is None:
        arc_seg = seg_for(speed, r, accel) if speed else 0.6
    if speed is not None:
        r_min = speed ** 2 / accel
        if r < r_min:
            raise SystemExit(f"fillet radius {r}mm cannot hold {speed:.0f} mm/s — centripetal "
                             f"limit needs r >= {r_min:.1f}mm. Raise the radius or drop the speed.")
    if len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    n = len(pts)
    rng = range(n) if closed else range(1, n - 1)
    for i in rng:
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        v1 = (a[0] - b[0], a[1] - b[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        l1 = math.hypot(*v1); l2 = math.hypot(*v2)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        u1 = (v1[0] / l1, v1[1] / l1)
        u2 = (v2[0] / l2, v2[1] / l2)
        cosang = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
        ang = math.acos(cosang)                 # interior angle at b
        if ang > math.radians(170):             # already effectively straight
            out.append(b); continue
        if ang < 1e-6:
            out.append(b); continue
        t = r / math.tan(ang / 2.0)
        t = min(t, l1 * 0.5, l2 * 0.5)          # never eat more than half a segment
        rr = t * math.tan(ang / 2.0)
        if rr < 1e-6:
            out.append(b); continue
        p1 = (b[0] + u1[0] * t, b[1] + u1[1] * t)
        p2 = (b[0] + u2[0] * t, b[1] + u2[1] * t)
        # arc centre along the angle bisector
        bis = (u1[0] + u2[0], u1[1] + u2[1])
        bl = math.hypot(*bis)
        if bl < 1e-9:
            out.append(b); continue
        bis = (bis[0] / bl, bis[1] / bl)
        d = rr / math.sin(ang / 2.0)
        ctr = (b[0] + bis[0] * d, b[1] + bis[1] * d)
        a1 = math.atan2(p1[1] - ctr[1], p1[0] - ctr[0])
        a2 = math.atan2(p2[1] - ctr[1], p2[0] - ctr[0])
        da = a2 - a1
        while da > math.pi: da -= 2 * math.pi
        while da < -math.pi: da += 2 * math.pi
        steps = max(2, int(abs(da) * rr / arc_seg))
        out.append(p1)
        for k in range(1, steps):
            th = a1 + da * k / steps
            out.append((ctr[0] + rr * math.cos(th), ctr[1] + rr * math.sin(th)))
        out.append(p2)
    if not closed:
        out.append(pts[-1])
    return out


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pathstats import analyse
    print(f"min radius at 235 mm/s, accel 8000: {min_radius(235):.1f} mm")
    print(f"min radius at 125 mm/s, accel 8000: {min_radius(125):.1f} mm\n")
    # a square: four 90-degree corners, the worst case
    sq = [(20, 20), (80, 20), (80, 80), (20, 80), (20, 20)]
    before = analyse(sq, feed_mms=235, quiet=True)
    for r in (8, 12, 20):
        f = fillet(sq, r, closed=False, speed=235)
        st = analyse(f, feed_mms=235, quiet=True)
        print(f"  r={r:>2}mm seg={seg_for(235,r):.2f}mm: path {st['path_mm']:>6.1f}mm "
              f"(was {before['path_mm']:.1f})  below-90%-speed "
              f"{st['frac_below_90pct']*100:>5.1f}%  (was {before['frac_below_90pct']*100:.1f}%)")
