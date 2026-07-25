#!/usr/bin/env python3
"""SPIRA-2 — the crackle web as ONE continuous curve per layer, running at the melt ceiling.

Successor to spiralcoupon.py (SPIRA-1). Same family, three things fixed, all of them measured:

  1. SPIRA-1 CANNOT RUN AT MAX FLOW AND NOBODY CHECKED. Its min turn radius is 0.179 mm, so its
     centripetal ceiling is sqrt(8000*0.179) = 38 mm/s. The max-flow speed for an 0.85 x 0.40 bead
     at 80 mm3/s is 235 mm/s. It was shipped at F60 and the gap never appeared in any number,
     because "% of path below 90% of COMMANDED" flatters any design you command slowly enough.
  2. IT WAS COSTED AT A 0.5 mm STRAND FROM AN 0.8 mm NOZZLE — the defect Oleg found on the printed
     coupon. Everything here is derived at 0.85.
  3. ITS AMPLITUDE WAS CONSTANT, so the inner turns carried the same radial swing as the outer ones
     over a fraction of the arc. Curvature ~ A*m^2/r^2: the inner turns were the whole problem.

THE FAMILY
    r(t)  = rb(t) + A(rb)*sin(m t + phi)          rb(t) = r0 + (s/2pi) t      (Archimedean base)
    W     = 1 + (rho(th,q) - 1) * (rb/r_max)^2    rho = superellipse, squares the RIM only
    x, y  = W * r * cos(th), W * r * sin(th)      th = t

    A(rb) = (s/2) * (rb/r_x)^2       <- THE FIX. Amplitude grows as r^2.

WHY r^2, DERIVED NOT TUNED. Max curvature sits at the outward peak of the modulation:
    kappa(r) = 1/r + A(r) m^2 / r^2
With A proportional to r^2 the second term is CONSTANT at every radius:
    kappa(r) = 1/r + s m^2 / (2 r_x^2)
so the modulation spends the same curvature everywhere instead of blowing up at the centre, and
the whole design collapses to one inequality:

    1/R_req  >=  1/r0 + s*m^2/(2*r_x^2)          R_req = v_cmd^2 / accel

r_x is exactly the crossing-onset radius: A(r_x) = s/2 is the condition for adjacent turns to
interleave, so crossings exist for r > r_x and

    crossings/layer ~ 2*m*(r_max - r_x)/s        <- m is the dial, LINEAR and exact in the limit

THE DIAL IS m, AND ITS ZERO IS FREE. |sin(pi*m)| gates the crossing condition, so INTEGER m gives
exactly zero crossings at the same path length, same amplitude, same speed profile, same mass —
the mass-matched negative control PROTOCOL.md says the project still lacks (Bpas2 was 6% off).
m is otherwise run at half-integer + 0.07: the +0.07 detune breaks the 2m radial spokes that a
clean half-integer locks crossings onto (spira-1 weakness 3).

THE FINDING THAT MATTERS MOST HERE: M204 S8000 GIVES ZERO CROSSINGS AT MAX FLOW.
At 235 mm/s, accel 8000 needs R >= 6.92 mm everywhere. That eats the entire curvature budget on
the base spiral alone (r0 >= 6.92) and leaves nothing for the modulation — and the modulation IS
the crossings. The project's S8000 convention is not a detail, it is the enabling parameter.
S20000 (2/3 of the machine's 30000) gives R_req 2.77 mm and ~95 crossings/layer.

Run:
    python3 spira2.py --analyse          # every number in this docstring, recomputed
    python3 spira2.py --ladder           # the constant-mass dose-response ladder
    python3 spira2.py --emit --no-home   # gcode + parse-it-back verification
"""
from __future__ import annotations
import argparse, math, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

TAU = 2 * math.pi
GOLD = math.pi * (3 - math.sqrt(5))          # 2.39996 rad

DEF = dict(
    size=60.0, origin=40.0,                  # coupon footprint, offset onto the 350x350 bed
    r0=8.0, r_max=28.5, s=2.0, r_x=14.25,    # base spiral: hole, rim, turn spacing, crossing onset
    m=6.57, q=4.0, warp_p=2.0,               # dial, superellipse exponent, warp blend-in power
    layers=15, layer_h=0.40,
    strand_w=0.85, filament_d=1.75,          # 0.85 >= the 0.8 orifice. Not negotiable, see RESULTS.
    flow=machine.FLOW,                       # 80 mm3/s measured-max-known-good -> speed follows
    accel=20000, scv=5.0,                    # M204 S20000; scv 5 is Klipper's default (K2 may be 10)
    seg_margin=1.25, seg_min=0.08, seg_max=1.20,
    temp=230, bed=60, fan=0,
    weld=1.0, lift=0.5, lift_win=8.0,        # Phase 1: fused beat woven. weld<1 only for the sweep.
)


def speed_of(P):
    """Oleg's rule: extrude at the max flow the nozzle is known to pass, 100% of the time."""
    return P['flow'] / (P['strand_w'] * P['layer_h'])


# --------------------------------------------------------------------------- geometry
def _rho(th, q):
    if q == 2.0:
        return np.ones_like(th)
    return (np.abs(np.cos(th)) ** q + np.abs(np.sin(th)) ** q) ** (-1.0 / q)


def curve_dense(P, m=None, phi0=0.0, r0=None, r_max=None, n=None):
    """Dense uniform-t sample of one layer's curve, centred on (0,0). No segmentation yet."""
    m = P['m'] if m is None else m
    r0 = P['r0'] if r0 is None else r0
    r_max = P['r_max'] if r_max is None else r_max
    turns = (r_max - r0) / P['s']
    t = np.linspace(0.0, TAU * turns, n or int(max(60000, 5000 * turns)))
    rb = r0 + (P['s'] / TAU) * t
    A = (P['s'] / 2.0) * (rb / P['r_x']) ** 2
    r = rb + A * np.sin(m * t + phi0)
    W = 1.0 + (_rho(t, P['q']) - 1.0) * np.clip(rb / r_max, 0, 1) ** P['warp_p']
    return t, W * r * np.cos(t), W * r * np.sin(t), rb, A


def curvature(t, x, y):
    dt = t[1] - t[0]
    dx, dy = np.gradient(x, dt), np.gradient(y, dt)
    ddx, ddy = np.gradient(dx, dt), np.gradient(dy, dt)
    k = np.abs(dx * ddy - dy * ddx) / np.maximum((dx * dx + dy * dy) ** 1.5, 1e-15)
    k[:30] = k[30]; k[-30:] = k[-31]        # gradient end effects, not geometry
    return k


def fit_to_coupon(P, x, y):
    """Uniform scale so the modulated, warped path fits the coupon with half a bead of margin.
    Uniform scaling multiplies every radius of curvature by the same factor and cannot create or
    destroy an intersection, so nothing measured downstream is disturbed except favourably."""
    half = P['size'] / 2.0 - P['strand_w'] / 2.0 - 0.15
    got = max(np.abs(x).max(), np.abs(y).max())
    k = min(1.0, half / got)
    return k * x, k * y, k


def segment(P, t, x, y, kap, v_cmd):
    """Adaptive segmentation — the Lissajous graft, generalised so it is affordable at 235 mm/s.

    The Lissajous brief's rule was chord error <= junction_deviation, which guarantees Klipper's
    junction term NEVER binds at ANY speed. Solve Klipper's junction formula in the small-angle
    limit and the condition for it not to bind BELOW WHAT PHYSICS ALREADY ALLOWS is

        h <= 1.8205 * scv * R / v_allowed ,   v_allowed = min(v_cmd, sqrt(accel*R))

    (1.8205 = sqrt(8*(sqrt2-1)); the accel cancels.) Where R < v_cmd^2/accel this reduces EXACTLY
    to h = sqrt(8*jd*R), i.e. the eps<=jd rule; where R is larger it is looser, because physics is
    not asking for full speed there anyway. At 235 mm/s the strict form costs ~19,000 moves/layer
    (3,300 moves/s, far past the MCU); this form costs ~4,000 and is provably no worse."""
    R = 1.0 / np.maximum(kap, 1e-9)
    v_allowed = np.minimum(v_cmd, np.sqrt(P['accel'] * R))
    h = 1.8205 * P['scv'] * R / (P['seg_margin'] * np.maximum(v_allowed, 1e-6))
    h = np.clip(h, P['seg_min'], P['seg_max'])
    seg = np.hypot(np.diff(x), np.diff(y))
    keep, acc, budget = [0], 0.0, h[0]
    for i in range(1, len(x)):
        acc += seg[i - 1]
        budget = min(budget, h[i])
        if acc >= budget:
            keep.append(i); acc = 0.0; budget = h[i]
    if keep[-1] != len(x) - 1:
        keep.append(len(x) - 1)
    k = np.array(keep)
    return x[k], y[k]


def handover(P, p0, t0, p1, t1, v):
    """Tangent-continuous blend between the end of one layer and the start of the next.

    PARSE-BACK CAUGHT THIS TOO. v1 joined layers with a straight chord. The chord is 4-6 mm (the
    two layers' rim ends sit at the same polar angle but different radius, because of the golden
    phase walk and the half-pitch offset), and it met the next layer's 0.07 mm chords at a sharp
    angle: Klipper's junction limit put the head at 4 mm/s, 15 times per print, at the rim where
    material already piles. My single-layer model could not see it because a handover is not part
    of a layer. A cubic Hermite with the arm length grown until the blend's own min radius clears
    v^2/accel fixes it by construction rather than by hoping."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    t0 = np.asarray(t0, float); t0 = t0 / max(np.hypot(*t0), 1e-12)
    t1 = np.asarray(t1, float); t1 = t1 / max(np.hypot(*t1), 1e-12)
    gap = float(np.hypot(*(p1 - p0)))
    R_req = v * v / P['accel']
    arm = max(gap * 0.5, 2.0)
    for _ in range(14):
        u = np.linspace(0, 1, 400)[:, None]
        h00 = 2*u**3 - 3*u**2 + 1; h10 = u**3 - 2*u**2 + u
        h01 = -2*u**3 + 3*u**2;    h11 = u**3 - u**2
        pts = h00*p0 + h10*(arm*t0) + h01*p1 + h11*(arm*t1)
        x, y = pts[:, 0], pts[:, 1]
        kap = curvature(np.linspace(0, 1, len(x)), x, y)
        if 1.0 / max(kap.max(), 1e-9) >= R_req:
            break
        arm *= 1.35
    return segment(P, np.linspace(0, 1, len(x)), x, y, kap, v)


def layer_plan(P, i):
    """Per-layer variation. Three things, and the third is the one that is easy to get wrong.

      phi0   golden-angle walk -> the modulation's phase never repeats, so crossings rotate.
      r0/r_max  both shift by s/2 on odd layers -> odd layers' turns land in even layers' gaps.
             Shifting BOTH keeps the turn count fixed so every layer ends at the same polar angle.
      reverse alternates -> layer i ends at the rim where layer i+1 starts: the whole 15-layer web
             is one extrusion with millimetre handovers instead of 15 travels.

      DO NOT add a rigid rotation alpha. For an Archimedean spiral a rotation by alpha IS a radial
      shift of -alpha*s/2pi, so alpha=pi exactly cancels the +s/2 offset and every layer re-aligns
      into welded columns. SPIRA-1 shipped that bug for one revision; stacking went 0.000 -> 0.237
      with no other symptom."""
    odd = i % 2
    d = P['s'] / 2 if odd else 0.0
    return dict(phi0=(i * GOLD) % TAU, r0=P['r0'] + d, r_max=P['r_max'] + d, reverse=bool(odd))


def layer_polyline(i, m=None, P=None):
    """>>> THE DELIVERABLE <<<  (x, y) polyline for layer i of the 60 mm coupon, bed coordinates.

    i : layer index, 0-based. Applies the per-layer variation schedule.
    m : the dial. crossings/layer ~ 2*m*(r_max - r_x)/s, and INTEGER m gives exactly 0.
    """
    P = dict(DEF, **(P or {}))
    m = P['m'] if m is None else m
    lp = layer_plan(P, i)
    t, x, y, rb, A = curve_dense(P, m=m, phi0=lp['phi0'], r0=lp['r0'], r_max=lp['r_max'])
    kap = curvature(t, x, y)
    x, y, k = fit_to_coupon(P, x, y)
    kap = kap / k                                   # scaling by k divides curvature by k
    xs, ys = segment(P, t, x, y, kap, speed_of(P))
    if lp['reverse']:
        xs, ys = xs[::-1], ys[::-1]
    c = P['origin'] + P['size'] / 2.0
    return xs + c, ys + c


# --------------------------------------------------------------------------- measurement
def crossings(x, y, skip=3, tol=0.15):
    """Segment-pair intersection. Returns (i, j, px, py) with i<j, geometrically de-duplicated."""
    from scipy.spatial import cKDTree
    p0 = np.column_stack([x[:-1], y[:-1]]); p1 = np.column_stack([x[1:], y[1:]])
    ln = np.hypot(*(p1 - p0).T)
    pr = np.array(list(cKDTree(0.5 * (p0 + p1)).query_pairs(max(ln.max(), 1e-9) * 1.001)))
    if len(pr) == 0:
        return []
    i, j = np.minimum(pr[:, 0], pr[:, 1]), np.maximum(pr[:, 0], pr[:, 1])
    k = (j - i) >= skip
    i, j = i[k], j[k]
    a, r = p0[i], p1[i] - p0[i]
    c, sv = p0[j], p1[j] - p0[j]
    den = r[:, 0] * sv[:, 1] - r[:, 1] * sv[:, 0]
    ok = np.abs(den) > 1e-12
    i, j, a, r, c, sv, den = i[ok], j[ok], a[ok], r[ok], c[ok], sv[ok], den[ok]
    e = c - a
    tt = (e[:, 0] * sv[:, 1] - e[:, 1] * sv[:, 0]) / den
    uu = (e[:, 0] * r[:, 1] - e[:, 1] * r[:, 0]) / den
    h = (tt >= 0) & (tt <= 1) & (uu >= 0) & (uu <= 1)
    i, j, tt = i[h], j[h], tt[h]
    px, py = x[i] + tt * (x[i + 1] - x[i]), y[i] + tt * (y[i + 1] - y[i])
    _, u = np.unique(np.round(np.column_stack([px, py]) / tol).astype(np.int64),
                     axis=0, return_index=True)
    return list(zip(i[u], j[u], px[u], py[u]))


def crossing_angles(x, y, hits):
    out = []
    for i, j, _, _ in hits:
        d1 = np.array([x[i + 1] - x[i], y[i + 1] - y[i]])
        d2 = np.array([x[j + 1] - x[j], y[j + 1] - y[j]])
        c = abs(float(d1 @ d2)) / (np.linalg.norm(d1) * np.linalg.norm(d2) + 1e-15)
        out.append(math.degrees(math.acos(min(1.0, c))))
    return np.array(out) if out else np.array([0.0])


def arc(x, y):
    return np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])


def members(x, y, hits):
    """Path run between consecutive crossings. Each crossing marks BOTH branches."""
    cum = arc(x, y)
    pos = np.sort(np.array([cum[i] for i, j, _, _ in hits] + [cum[j] for i, j, _, _ in hits]))
    return np.diff(pos) if len(pos) > 1 else np.array([0.0])


def weld_dt(x, y, hits, v):
    """BLTW-C's metric, taken while rejecting its design: seconds between the two passes through a
    crossing. A junction only fuses if the second pass lands while the first is still hot, and
    fusing is the confirmed mechanism (RESULTS.md, weld1 beat weld0)."""
    cum = arc(x, y)
    return np.array([(cum[j] - cum[i]) / v for i, j, _, _ in hits]) if hits else np.array([0.0])


def fused_fraction(x, y, bead, ds=0.25):
    """Share of path lying within one bead width of a non-adjacent part of the path — material
    that is junction, not member. Above ~40% the web is a perforated plate, not a web."""
    from scipy.spatial import cKDTree
    cum = arc(x, y)
    u = np.arange(0.0, cum[-1], ds)
    px, py = np.interp(u, cum, x), np.interp(u, cum, y)
    pts = np.column_stack([px, py])
    gap = int(math.ceil(3.0 * bead / ds))
    fus = np.zeros(len(pts), bool)
    for a, b in cKDTree(pts).query_pairs(bead, output_type='ndarray'):
        if abs(a - b) > gap:
            fus[a] = fus[b] = True
    return float(fus.mean())


# --------------------------------------------------------------------------- Klipper planner
def plan(x, y, v_cmd, accel, scv, cyclic=False):
    """Klipper look-ahead, transcribed from toolhead.Move.calc_junction, then forward/backward
    passes and the trapezoid integrated inside every move. Self-tested against three analytic
    cases in --analyse; a planner nobody has checked is not a measurement."""
    d = np.hypot(np.diff(x), np.diff(y))
    k = d > 1e-9
    d = d[k]
    ux = np.diff(x)[k] / d; uy = np.diff(y)[k] / d
    if cyclic:                       # tile 3x and read the middle: a closed loop never starts/stops
        n1 = len(d)
        d = np.tile(d, 3); ux = np.tile(ux, 3); uy = np.tile(uy, 3)
    n = len(d)
    jd = scv * scv * (math.sqrt(2.0) - 1.0) / accel
    v2 = np.full(n + 1, v_cmd * v_cmd)
    v2[0] = v2[-1] = 0.0
    ct = -(ux[:-1] * ux[1:] + uy[:-1] * uy[1:])           # Klipper's junction_cos_theta
    ct = np.clip(ct, -0.999999, 1.0)
    sh = np.sqrt(np.maximum(0.5 * (1.0 - ct), 0.0))
    with np.errstate(divide='ignore', invalid='ignore'):
        R_jd = np.where(sh < 1.0 - 1e-12, sh / np.maximum(1.0 - sh, 1e-12), np.inf)
        th = np.sqrt(np.maximum(0.5 * (1.0 + ct), 1e-18))
        tan_h = sh / th
    cap = np.minimum(R_jd * jd * accel,
                     np.minimum(0.5 * d[:-1] * tan_h * accel, 0.5 * d[1:] * tan_h * accel))
    cap = np.where(ct > 0.999999, 0.0, cap)
    v2[1:-1] = np.minimum(v2[1:-1], cap)
    for i in range(n - 1, -1, -1):                        # backward
        v2[i] = min(v2[i], v2[i + 1] + 2.0 * accel * d[i])
    for i in range(n):                                    # forward
        v2[i + 1] = min(v2[i + 1], v2[i] + 2.0 * accel * d[i])
    if cyclic:
        d = d[n1:2 * n1]; v2 = v2[n1:2 * n1 + 1]
        n = n1
    ve, vx = np.sqrt(v2[:-1]), np.sqrt(v2[1:])
    vt = 0.9 * v_cmd
    lo = np.clip((vt * vt - ve * ve) / (2 * accel), 0, None) + \
         np.clip((vt * vt - vx * vx) / (2 * accel), 0, None)
    below = float(np.minimum(lo, d).sum())
    # time: accel-up + decel-down + cruise remainder, per move
    peak2 = np.minimum(v_cmd ** 2, (ve ** 2 + vx ** 2) / 2 + accel * d)
    peak = np.sqrt(peak2)
    d_a = (peak2 - ve ** 2) / (2 * accel); d_d = (peak2 - vx ** 2) / (2 * accel)
    d_c = np.clip(d - d_a - d_d, 0, None)
    T = ((peak - ve) / accel + (peak - vx) / accel + d_c / np.maximum(peak, 1e-9)).sum()
    L = float(d.sum())
    inner = v2[1:-1] if len(v2) > 2 else v2      # the first/last vertices are at rest BY DESIGN;
    cum = np.concatenate([[0.0], np.cumsum(d)])   # reporting them as "v_min" measures nothing
    mid = (cum > 5.0) & (cum < L - 5.0)           # v_min in the BODY, past the start/stop ramps
    vmid = float(np.sqrt(v2[mid]).min()) if mid.any() else float(np.sqrt(inner).min())
    return dict(frac_below_90=below / L, v_min_body=vmid,
                v_min=float(np.sqrt(inner).min()),
                v_mean=L / T if T else 0.0, secs=T, L=L,
                moves_per_s=n / T if T else 0.0, moves=n)


def _planner_selftest(accel=8000.0, scv=5.0):
    out = []
    a = np.array([0., 50., 50.]); b = np.array([0., 0., 50.])      # exact 90 degree corner
    out.append(("90deg corner -> scv", plan(a, b, 400.0, accel, scv)['v_min'], scv))
    for R, v in ((5.0, 400.0), (50.0, 400.0), (50.0, 150.0)):
        th = np.linspace(0, TAU, int(TAU * R / 0.05), endpoint=False)
        p = plan(R * np.cos(th), R * np.sin(th), v, accel, scv, cyclic=True)
        exp = min(v, math.sqrt(accel * R))
        out.append((f"R={R:g} circle at F{v:.0f} -> min(F, sqrt(aR))", p['v_mean'], exp))
    return out


# --------------------------------------------------------------------------- gcode
def emit(P):
    v = speed_of(P)
    if P['strand_w'] < machine.NOZZLE:
        raise SystemExit(f"strand_w {P['strand_w']} < the {machine.NOZZLE} orifice — a nozzle "
                         f"cannot lay a bead narrower than its hole (RESULTS.md 2026-07-25).")
    if P['strand_w'] > 1.5 * machine.NOZZLE:
        raise SystemExit(f"strand_w {P['strand_w']} > 1.5x nozzle — the bead lands TALL and the "
                         f"nozzle ploughs the part off the plate (2026-07-25).")
    if v > machine.MAX_VELOCITY:
        raise SystemExit(f"{v:.0f} mm/s exceeds max_velocity {machine.MAX_VELOCITY}")
    if P['accel'] > machine.MAX_ACCEL:
        raise SystemExit(f"accel {P['accel']} exceeds max_accel {machine.MAX_ACCEL}")
    area = math.pi * (P['filament_d'] / 2) ** 2
    e_mm = (P['strand_w'] * P['layer_h']) / area
    base_w = 0.9
    f = round(v * 60)
    L, e, z = [], 0.0, 0.0
    w = L.append
    o, S = P['origin'], P['size']
    c = o + S / 2.0

    w(f"; SPIRA-2  m={P['m']}  r0={P['r0']} r_max={P['r_max']} s={P['s']} r_x={P['r_x']} q={P['q']}")
    w(f"; A(r) = (s/2)(r/r_x)^2 -> kappa = 1/r + s*m^2/(2 r_x^2), constant modulation curvature")
    w(f"; strand {P['strand_w']}x{P['layer_h']} at flow {P['flow']} mm3/s -> F{v:.0f} mm/s")
    w(f"; M204 S{P['accel']}: R_req = v^2/a = {v*v/P['accel']:.2f} mm. S8000 would need "
      f"{v*v/8000:.2f} mm and yields ZERO crossings — see the module docstring.")
    w("; NO RETRACTION, NO COMBING, NO Z-HOP — the web is the extrusion.")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {2 + P['layers']}"); w("; HEADER_BLOCK_END")
    w(f"M140 S{P['bed']}"); w(f"M104 S{P['temp']}"); w("G90")
    w("G28" if P.get('home', True) else "; NO HOME — machine must still be homed from a prior run")
    w(f"M190 S{P['bed']}"); w(f"M109 S{P['temp']}")
    w(f"M204 S{P['accel']}"); w("M107" if not P['fan'] else f"M106 S{P['fan']}")
    w("M82"); w("G92 E0")
    w(f"G1 Z{P['layer_h']:.2f} F600")
    w(f"G0 F9000 X{o:.1f} Y{o-8:.1f}"); w(f"G1 F1200 X{o+S:.1f} Y{o-8:.1f} E10"); w("G92 E0")
    if P['weld'] < 1.0:
        w("; Z_MODULATED")
    w("; BODY_START")

    # ---- anchor base: 2 layers of a dense Archimedean spiral. Continuous (no reversals, the
    #      flowtest lesson), sticks, and peels off as one coupon you can stand on.
    # PARSE-BACK CAUGHT THIS: v1 started the base at r=0 (curvature -> infinity, planner floor
    # 3 mm/s) and sampled it at a fixed 900 points/turn (2097 moves/s, 27k moves for 2.9 m).
    # Start at a finite radius and segment it by the same adaptive rule as the web.
    v_base = P['flow'] / (base_w * P['layer_h'])
    r0b, rmb = 1.2, S / 2 - 1.5
    turns = (rmb - r0b) / base_w
    tb = np.linspace(0.0, TAU * turns, int(max(40000, 2000 * turns)))
    rbb = r0b + (base_w / TAU) * tb
    Wb = 1.0 + (_rho(tb, 4.0) - 1.0) * np.clip(rbb / rmb, 0, 1) ** 2
    bx, by = Wb * rbb * np.cos(tb), Wb * rbb * np.sin(tb)
    bx, by = segment(P, tb, bx, by, curvature(tb, bx, by), v_base)
    bx, by = bx + c, by + c
    for bl in range(2):
        z = round(z + P['layer_h'], 3)
        w(f"; base layer {bl+1}")
        w(f"G0 F9000 X{bx[0]:.3f} Y{by[0]:.3f}"); w(f"G1 F600 Z{z:.3f}")
        seq = zip(bx, by) if bl == 0 else zip(bx[::-1], by[::-1])
        px = py = None
        for X, Y in seq:
            if px is not None:
                e += math.hypot(X - px, Y - py) * (base_w * P['layer_h']) / area
                w(f"G1 F{round(P['flow']/(base_w*P['layer_h'])*60)} X{X:.3f} Y{Y:.3f} E{e:.5f}")
            px, py = X, Y
        for k in range(P.get('tally', 0)):               # blind-ID bars, PROTOCOL.md
            yb = o + 4 + 3.0 * k
            w(f"G0 F9000 X{o-2.5:.2f} Y{yb:.2f}")
            e += 6.0 * (base_w * P['layer_h']) / area
            w(f"G1 F2400 X{o+3.5:.2f} Y{yb:.2f} E{e:.5f}")

    # ---- web
    stats = dict(cross=0, lifts=0, moves=0, path=0.0)
    lx = ly = None
    for i in range(P['layers']):
        z = round(z + P['layer_h'], 3)
        xs, ys = layer_polyline(i, P['m'], P)
        hits = crossings(xs, ys)
        cum = arc(xs, ys)
        second = [cum[max(a, b)] for k, (a, b, _, _) in
                  enumerate(sorted(hits, key=lambda h: max(h[0], h[1])))
                  if (k % 100) >= P['weld'] * 100]
        stats['cross'] += len(hits); stats['lifts'] += len(second)
        w(f"; web layer {i+1}  z{z:.2f}  ONE curve, {len(xs)-1} moves, {len(hits)} crossings, "
          f"{len(second)} lifts")
        if lx is None:
            w(f"G0 F9000 X{xs[0]:.3f} Y{ys[0]:.3f}")
        w(f"G1 F600 Z{z:.3f}")
        if lx is not None and math.hypot(xs[0] - lx, ys[0] - ly) > 0.05:
            hx, hy = handover(P, (lx, ly), (ltx, lty), (xs[0], ys[0]),
                              (xs[1] - xs[0], ys[1] - ys[0]), v)
            hpx, hpy = lx, ly
            for X, Y in list(zip(hx, hy))[1:]:
                d = math.hypot(X - hpx, Y - hpy)
                e += d * e_mm; stats['path'] += d; stats['moves'] += 1
                w(f"G1 F{f} X{X:.3f} Y{Y:.3f} E{e:.5f}")
                hpx, hpy = X, Y
        px, py = xs[0], ys[0]
        for jj in range(1, len(xs)):
            dz = 0.0
            for sv in second:
                dd = cum[jj] - sv
                if abs(dd) < P['lift_win']:
                    dz = max(dz, P['lift'] * math.cos(math.pi * dd / (2 * P['lift_win'])) ** 2)
            d = math.hypot(xs[jj] - px, ys[jj] - py)
            e += d * e_mm; stats['path'] += d; stats['moves'] += 1
            zt = f" Z{z+dz:.4f}" if second else ""
            w(f"G1 F{f} X{xs[jj]:.3f} Y{ys[jj]:.3f}{zt} E{e:.5f}")
            px, py = xs[jj], ys[jj]
        lx, ly = px, py
        ltx, lty = xs[-1] - xs[-2], ys[-1] - ys[-2]
    w("M107"); w("M104 S0"); w("M140 S0"); w(f"G1 Z{z+40:.1f} F900"); w("G0 X10 Y340 F9000")
    stats['grams'] = e * area * 1.24 / 1000
    stats['lines'] = len(L)
    stats['speed'] = v
    return "\n".join(L) + "\n", stats


def parse_gcode(path):
    """Read the EMITTED file back as {tag: [polyline, ...]}. The epicycle brief's discipline:
    verify the ARTIFACT, not the model — their first file ran 4.9% below speed while the model
    said 0.00%. It earned its keep here too: v1's base spiral started at r=0 and the parse-back
    read v_min 3 mm/s and 2097 moves/s off the emitted file, which no model of mine was watching."""
    runs, cur, tag, x, y, body = {}, [], None, 0.0, 0.0, False
    def flush():
        if cur and len(cur) > 2:
            runs.setdefault(tag, []).append(np.array(cur))
    for raw in open(path):
        if '; BODY_START' in raw:
            body = True
        if raw.startswith('; base layer'):
            flush(); cur = []; tag = 'base'
        elif raw.startswith('; web layer'):
            flush(); cur = []; tag = 'web'
        s = raw.split(';')[0].strip()
        if not body or not s.startswith(('G0', 'G1')):
            continue
        mx = re.search(r'X([-\d.]+)', s); my = re.search(r'Y([-\d.]+)', s)
        nx = float(mx.group(1)) if mx else x; ny = float(my.group(1)) if my else y
        if 'E' in s and ('X' in s or 'Y' in s):
            if not cur:
                cur.append([x, y])
            cur.append([nx, ny])
        elif 'X' in s or 'Y' in s:
            flush(); cur = []                     # a travel breaks the polyline
        x, y = nx, ny
    flush()
    return runs


# --------------------------------------------------------------------------- analysis
def layer_report(P, m, i=0, label=""):
    v = speed_of(P)
    xs, ys = layer_polyline(i, m, P)
    hits = crossings(xs, ys)
    ang = crossing_angles(xs, ys, hits)
    mem = members(xs, ys, hits)
    dt = weld_dt(xs, ys, hits, v)
    pl = plan(xs, ys, v, P['accel'], P['scv'])
    t, dx, dy, rb, A = curve_dense(P, m=m)
    dx, dy, k = fit_to_coupon(P, dx, dy)
    Rmin = float(1.0 / curvature(t, dx, dy).max() / k)
    cr = np.hypot([h[2] - (P['origin'] + P['size'] / 2) for h in hits],
                  [h[3] - (P['origin'] + P['size'] / 2) for h in hits]) if hits else np.array([0.])
    return dict(label=label or f"m={m}", m=m, X=len(hits), L=pl['L'], Rmin=Rmin,
                vcap=math.sqrt(P['accel'] * Rmin), ang50=float(np.median(ang)),
                ang_lt20=float((ang < 20).mean()), mem_mean=float(mem.mean()),
                mem_cv=float(mem.std() / max(mem.mean(), 1e-9)),
                dt50=float(np.median(dt)), dt_lt1=float((dt < 1.0).mean()),
                fused=fused_fraction(xs, ys, P['strand_w']),
                core=float(cr.min()) if hits else float('nan'),
                slow=pl['frac_below_90'], vmin=pl['v_min'], vmean=pl['v_mean'],
                moves=pl['moves'], mps=pl['moves_per_s'], secs=pl['secs'],
                grams=pl['L'] * P['strand_w'] * P['layer_h'] * 1.24 / 1000)


def match_mass(P, m, L_target, lo=3.0, hi=22.0):
    """Hold path length (=mass) constant across the ladder by trimming r0. Judge correction to
    SPIRA-1: its m-ladder was NOT constant mass (+24.9% from m=4.5 to 10.5) and said it was."""
    for _ in range(22):
        mid = 0.5 * (lo + hi)
        Q = dict(P, r0=mid)
        xs, ys = layer_polyline(0, m, Q)
        if arc(xs, ys)[-1] > L_target:
            lo = mid                       # too long -> bigger hole
        else:
            hi = mid
    return 0.5 * (lo + hi)


def stack_report(P, m, cell=0.6, near=0.5):
    """Do crossings pile into welded vertical columns? That is re-inventing the pillar."""
    from scipy.spatial import cKDTree
    per, cells = [], {}
    prev = None
    adj = 0; tot = 0
    for i in range(P['layers']):
        xs, ys = layer_polyline(i, m, P)
        h = crossings(xs, ys)
        pts = np.array([[a, b] for _, _, a, b in h])
        per.append(pts)
        for p in pts:
            cells.setdefault((round(p[0] / cell), round(p[1] / cell)), []).append(i)
        if prev is not None and len(pts) and len(prev):
            d, _ = cKDTree(prev).query(pts)
            adj += int((d < near).sum()); tot += len(pts)
        prev = pts
    depths = [len(set(v)) for v in cells.values()]
    return dict(adjacent=adj / max(tot, 1), occupied=len(cells), maxcol=max(depths),
                meancol=float(np.mean(depths)), total=sum(len(p) for p in per))


# --------------------------------------------------------------------------- CLI
def _hdr():
    return (f"{'design':>12}{'X':>6}{'L mm':>8}{'Rmin':>7}{'vcap':>7}{'ang50':>7}{'<20d':>6}"
            f"{'mem':>7}{'CV':>6}{'fused':>7}{'core':>6}{'slow':>7}{'vmin':>7}{'mv/s':>7}")


def _row(r):
    return (f"{r['label']:>12}{r['X']:>6}{r['L']:>8.0f}{r['Rmin']:>7.2f}{r['vcap']:>7.0f}"
            f"{r['ang50']:>7.0f}{r['ang_lt20']*100:>5.0f}%{r['mem_mean']:>7.2f}{r['mem_cv']:>6.2f}"
            f"{r['fused']*100:>6.1f}%{r['core']:>6.1f}{r['slow']*100:>6.2f}%{r['vmin']:>7.0f}"
            f"{r['mps']:>7.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--ladder", action="store_true")
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--m", type=float, default=DEF['m'])
    ap.add_argument("--accel", type=int, default=DEF['accel'])
    ap.add_argument("--flow", type=float, default=DEF['flow'])
    ap.add_argument("--strand_w", type=float, default=DEF['strand_w'])
    ap.add_argument("--layers", type=int, default=DEF['layers'])
    ap.add_argument("--weld", type=float, default=1.0)
    ap.add_argument("--tally", type=int, default=0)
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    P = dict(DEF, m=a.m, accel=a.accel, flow=a.flow, strand_w=a.strand_w, layers=a.layers,
             weld=a.weld, tally=a.tally, home=not a.no_home)
    v = speed_of(P)

    if a.analyse:
        print(f"SPIRA-2   flow {P['flow']} mm3/s / ({P['strand_w']} x {P['layer_h']}) "
              f"= F{v:.1f} mm/s     M204 S{P['accel']}  ->  R_req = {v*v/P['accel']:.2f} mm")
        print("\nPLANNER SELF-TEST (a planner nobody has checked is not a measurement)")
        for name, got, exp in _planner_selftest():
            print(f"  {name:<28} got {got:8.3f}   expect {exp:8.3f}   "
                  f"{'OK' if abs(got-exp) < max(0.02*exp, 0.05) else 'FAIL'}")
        print("\nWHY THE ACCEL COMMAND IS THE ENABLING PARAMETER, not a detail")
        print(f"  {'M204':>8}{'R_req':>8}{'m_max':>8}{'X at m_max':>12}")
        for ac in (8000, 12000, 20000, 30000):
            Rr = v * v / ac
            budget = 1.0 / Rr - 1.0 / P['r0']
            mmax = P['r_x'] * math.sqrt(2 * budget / P['s']) if budget > 0 else 0.0
            print(f"  {ac:>8}{Rr:>8.2f}{mmax:>8.2f}"
                  f"{2*mmax*(P['r_max']-P['r_x'])/P['s']:>12.0f}")
        print("\nTHE DIAL — measured by segment intersection on the EMITTED polyline")
        print(_hdr())
        for m in (2.57, 4.57, 6.57, 5.0):
            r = layer_report(P, m, 0, label=("m=%g" % m) + (" (INT)" if m == int(m) else ""))
            print(_row(r))
        print("  (m=5.0 is an integer: sin(pi m)=0, so zero crossings at the same path length —"
              "\n   the mass-matched negative control, free from the closed form.)")
        print("\nSPEED — same curve, the feedrate you command")
        xs, ys = layer_polyline(0, P['m'], P)
        print(f"  {'F mm/s':>8}{'flow':>8}{'slow':>9}{'v_min':>8}{'v_mean':>8}{'s/layer':>9}"
              f"{'moves/s':>9}")
        for vv in (60, 120, 180, v, 300):
            p = plan(xs, ys, vv, P['accel'], P['scv'])
            print(f"  {vv:>8.0f}{vv*P['strand_w']*P['layer_h']:>8.1f}"
                  f"{p['frac_below_90']*100:>8.2f}%{p['v_min']:>8.0f}{p['v_mean']:>8.0f}"
                  f"{p['secs']:>9.1f}{p['moves_per_s']:>9.0f}")
        print("  the ENTIRE below-90% figure is the start/stop ramp: v_min in the body of the "
              f"layer is {plan(xs, ys, v, P['accel'], P['scv'])['v_min_body']:.0f} mm/s = "
              f"{plan(xs, ys, v, P['accel'], P['scv'])['v_min_body']/v*100:.0f}% of commanded.")
        print("\nMOVE RATE is the real cost of accel. At the tightest turn of ANY curve held at "
              "its\n  centripetal limit the rate is accel/(1.82*scv) — independent of speed and "
              "shape.")
        print(f"  {'M204':>8}{'scv':>6}{'peak mv/s':>11}{'actual mv/s':>13}{'slow':>8}")
        for ac in (12000, 20000, 30000):
            for sc in (5.0, 10.0):
                Q = dict(P, accel=ac, scv=sc)
                x2, y2 = layer_polyline(0, P['m'], Q)
                pp = plan(x2, y2, v, ac, sc)
                print(f"  {ac:>8}{sc:>6.0f}{ac/(1.8205*sc):>11.0f}{pp['moves_per_s']:>13.0f}"
                      f"{pp['frac_below_90']*100:>7.2f}%")
        print("\nSEGMENTATION IS PART OF THE DESIGN (Lissajous graft), at F%.0f" % v)
        t, dx, dy, rb, A = curve_dense(P)
        kap0 = curvature(t, dx, dy)
        dx, dy, kk = fit_to_coupon(P, dx, dy)
        kap0 = kap0 / kk
        print(f"  {'rule':>26}{'moves':>8}{'chord':>8}{'slow':>9}{'v_min':>8}{'mv/s':>7}")
        for lbl, mg in (("eps<=jd (strict)", None), ("this design", P['seg_margin']),
                        ("margin 1.0", 1.0), ("fixed 0.6mm", 'f6'), ("fixed 1.2mm", 'f12')):
            if mg is None:
                jd = P['scv'] ** 2 * (math.sqrt(2) - 1) / P['accel']
                h = np.clip(np.sqrt(8 * jd / np.maximum(kap0, 1e-9)), P['seg_min'], P['seg_max'])
                Q = dict(P); xs2, ys2 = _seg_with(P, dx, dy, h)
            elif mg == 'f6':
                xs2, ys2 = _seg_with(P, dx, dy, np.full_like(kap0, 0.6))
            elif mg == 'f12':
                xs2, ys2 = _seg_with(P, dx, dy, np.full_like(kap0, 1.2))
            else:
                xs2, ys2 = segment(dict(P, seg_margin=mg), t, dx, dy, kap0, v)
            p = plan(xs2, ys2, v, P['accel'], P['scv'])
            print(f"  {lbl:>26}{p['moves']:>8}{p['L']/p['moves']:>8.3f}"
                  f"{p['frac_below_90']*100:>8.2f}%{p['v_min']:>8.0f}{p['moves_per_s']:>7.0f}")
        print("\nWELD TIME (BLTW-C's metric; fusing is the confirmed mechanism)")
        r = layer_report(P, P['m'])
        print(f"  median dt {r['dt50']:.2f} s   under 1 s: {r['dt_lt1']*100:.0f}%   "
              f"layer {r['secs']:.1f} s   dt/layer {r['dt50']/max(r['secs'],1e-9):.3f} "
              f"(uniform-random floor 0.293)")
        print("\nPER-LAYER VARIATION — do crossings weld into columns?")
        for lbl, Q in (("none", dict(P, _flat=True)), ("full schedule", P)):
            if lbl == "none":
                import types
                g = globals(); old = g['layer_plan']
                g['layer_plan'] = lambda PP, i: dict(phi0=0.0, r0=PP['r0'], r_max=PP['r_max'],
                                                     reverse=False)
                st = stack_report(P, P['m']); g['layer_plan'] = old
            else:
                st = stack_report(P, P['m'])
            print(f"  {lbl:>14}: adjacent-layer stacking {st['adjacent']*100:5.1f}%   "
                  f"occupied cells {st['occupied']:>5}   max column {st['maxcol']:>2}/{P['layers']}"
                  f"   mean {st['meancol']:.2f}")

    if a.ladder:
        base = layer_report(P, 6.57)
        print(f"CONSTANT-MASS LADDER — path length held at {base['L']:.0f} mm/layer by trimming r0")
        print(f"{'m':>8}{'r0':>7}{'X':>6}{'L mm':>8}{'g/layer':>9}{'vcap':>7}{'slow':>8}"
              f"{'mem':>7}{'core':>6}")
        for m in (5.0, 2.57, 3.57, 4.57, 5.57, 6.57):
            r0 = match_mass(P, m, base['L'])
            Q = dict(P, r0=r0)
            r = layer_report(Q, m)
            print(f"{m:>8.2f}{r0:>7.2f}{r['X']:>6}{r['L']:>8.0f}{r['grams']:>9.3f}"
                  f"{r['vcap']:>7.0f}{r['slow']*100:>7.2f}%{r['mem_mean']:>7.2f}{r['core']:>6.1f}")
        print("  m=5.00 is the integer rung: same mass, same speed profile, ZERO crossings.")

    if a.emit:
        g, st = emit(P)
        os.makedirs(a.out, exist_ok=True)
        fn = (f"{a.out}/spira2_{'nohome_' if a.no_home else ''}m{P['m']:g}"
              f"_x{st['cross']//P['layers']}_w{P['weld']:g}_T{P['temp']}.gcode")
        open(fn, "w").write(g)
        print(f"wrote {fn}")
        print(f"  {P['layers']} layers, {st['cross']} crossings total "
              f"({st['cross']//P['layers']}/layer), {st['lifts']} lifts, {st['moves']} web moves")
        print(f"  {st['path']/1000:.1f} m web path, {st['grams']:.2f} g, {st['lines']} lines, "
              f"F{st['speed']:.0f} mm/s")
        runs = parse_gcode(fn)
        print("  PARSE-BACK — the emitted file re-planned, not the model:")
        print(f"    {'part':>6}{'runs':>6}{'pts':>8}{'m':>7}{'F':>6}{'slow':>8}{'v_min_body':>12}"
              f"{'v_mean':>8}{'mv/s':>7}{'xings':>7}")
        for tag, F in (('base', P['flow'] / (0.9 * P['layer_h'])), ('web', st['speed'])):
            rr = runs.get(tag, [])
            if not rr:
                continue
            big = max(rr, key=len)
            p = plan(big[:, 0], big[:, 1], F, P['accel'], P['scv'])
            h = crossings(big[:, 0], big[:, 1])
            print(f"    {tag:>6}{len(rr):>6}{len(big):>8}{p['L']/1000:>7.2f}{F:>6.0f}"
                  f"{p['frac_below_90']*100:>7.2f}%{p['v_min_body']:>12.0f}{p['v_mean']:>8.0f}"
                  f"{p['moves_per_s']:>7.0f}{len(h):>7}")
        allw = [plan(r[:, 0], r[:, 1], st['speed'], P['accel'], P['scv']) for r in runs['web']]
        print(f"    all 15 web layers: worst slow {max(q['frac_below_90'] for q in allw)*100:.2f}%,"
              f" worst v_min_body {min(q['v_min_body'] for q in allw):.0f} mm/s,"
              f" peak {max(q['moves_per_s'] for q in allw):.0f} moves/s")


def _seg_with(P, x, y, h):
    seg = np.hypot(np.diff(x), np.diff(y))
    keep, acc, budget = [0], 0.0, h[0]
    for i in range(1, len(x)):
        acc += seg[i - 1]; budget = min(budget, h[i])
        if acc >= budget:
            keep.append(i); acc = 0.0; budget = h[i]
    if keep[-1] != len(x) - 1:
        keep.append(len(x) - 1)
    k = np.array(keep)
    return x[k], y[k]


if __name__ == "__main__":
    main()
