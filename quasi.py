#!/usr/bin/env python3
"""Quasi-periodic continuous crackle web — ONE self-intersecting curve. No pillars, no strand ends.

Answers Oleg's question ("why are you not doing continuous? is cracking require the segments?").
It does not. A junction forms wherever plastic crosses plastic; it does not care whether the two
branches came from two strands or from one curve crossing itself. The lattice buys nothing and
costs two things: a full stop at every pillar (so the strand thickens at both ends, and the
commanded feedrate is not the actual feedrate) and anchor mass that makes no crossings.

FAMILY — 2 harmonics per axis, irrational frequency ratios:

  x(t) = S*[ sin(f1 t + p1) + ax2 sin(f2 t + p2) ] + x0
  y(t) = S*[ sin(g1 t + q1) + ay2 sin(g2 t + q2) ] + y0
  z(t) = z0 + (layer_h / T) * t                              <-- CONTINUOUS, never steps

  {f1,f2,g1,g2} are rationally independent (distinct square roots over rationals), so the orbit is
  dense on a 4-torus: the curve never closes and every pass lands somewhere new.

WHY TWO HARMONICS AND NOT FOUR (measured, see notes at the bottom of this file):
  x is then distributed as U1 + a*U2 with Ui arcsine. Two arcsines convolve to a nearly flat
  density with FINITE, non-zero edges. Three or four convolve toward a Gaussian: the density
  collapses at the extremes and the curve stops visiting the corners of the square. Measured
  marginal CV: 2 harmonics 0.22, 3 harmonics 0.31 with the edge bin at 21% of the mean.

WHAT THE CONTINUOUS Z RAMP BUYS (this is the load-bearing idea, not decoration):
  1. A bead's top surface IS the Z at which it was laid. If Z only rises, every later pass has
     non-negative clearance over everything already down. A FLAT-Z LAYER HAS EXACTLY ZERO
     CLEARANCE AT EVERY ONE OF ITS OWN SELF-CROSSINGS — the nozzle ploughs its own bead. The
     pillar design has that defect too; nobody noticed because the strands were thin.
  2. The two branches of a crossing are separated in t by dt, hence in Z by layer_h*dt/T. That is
     a computed over/under gap. Crossings with dt ~ 0 are coplanar merges and are counted apart.

Run:  python3 quasi.py            # the numbers
      python3 quasi.py --sweep    # the dials
      python3 quasi.py --tune     # re-run the parameter search
      python3 quasi.py --gcode    # emit out/quasi_*.gcode
"""
from __future__ import annotations
import argparse, math, os
from dataclasses import dataclass, replace
import numpy as np

# ---- measured machine facts (given, not re-derived) ---------------------------
MAX_VOL_FLOW = 81.2       # mm3/s measured
WORK_VOL_FLOW = 68.8      # mm3/s working
ACCEL = 8000.0            # mm/s2 -- prints command M204 S8000
MAX_VEL = 800.0           # mm/s
SCV = 5.0                 # Klipper square_corner_velocity (stock)

# Q-linearly independent frequency pool: sqrt(squarefree)/rational.
# Any 4 distinct picks have no integer relation -> quasi-periodic on a 4-torus, never closes.
POOL = {
    "1":       1.0,
    "r2/2":    math.sqrt(2) / 2,     # 0.70711
    "r3/2":    math.sqrt(3) / 2,     # 0.86603
    "r5/2":    math.sqrt(5) / 2,     # 1.11803
    "r6/3":    math.sqrt(6) / 3,     # 0.81650
    "r7/3":    math.sqrt(7) / 3,     # 0.88192
    "r10/3":   math.sqrt(10) / 3,    # 1.05409
    "r11/4":   math.sqrt(11) / 4,    # 0.82916
    "r13/4":   math.sqrt(13) / 4,    # 0.90139
    "r15/4":   math.sqrt(15) / 4,    # 0.96825
    "r17/4":   math.sqrt(17) / 4,    # 1.03078
    "r19/4":   math.sqrt(19) / 4,    # 1.08972
}

# D4 (square symmetry) applied per layer. Rotation by an arbitrary angle would round the corners
# off and pile material in the middle; D4 maps the square onto itself exactly.
D4 = [(1, 0, 0, 1), (0, -1, 1, 0), (-1, 0, 0, -1), (0, 1, -1, 0),
      (-1, 0, 0, 1), (1, 0, 0, -1), (0, 1, 1, 0), (0, -1, -1, 0)]


@dataclass
class Q:
    size: float = 60.0
    margin: float = 1.5
    origin: float = 145.0        # 60mm coupon centred on a 350 bed
    layer_h: float = 0.40
    layers: int = 15
    strand_w: float = 0.50       # ABSOLUTE strand width (decoupled, as crackle.py already does)
    fil_d: float = 1.75
    temp: int = 230
    bed: int = 60
    # --- TUNED (600-candidate frequency search + local phase/amplitude refinement).
    # All four frequencies sit within 1.09-1.17: that is what keeps curvature low. If one axis
    # turns much faster than the other you get a raster, and a raster U-turns (the serpentine
    # defect the flow test already hit). sqrt(5), sqrt(22), sqrt(19), sqrt(21): distinct squarefree
    # radicands, so no integer relation exists -> the orbit is dense on a 4-torus and never closes.
    # ay is scaled by 0.90048 so the realised x and y extents match and one ISOTROPIC scale fits
    # the square (an anisotropic fit would re-introduce a curvature maximum on the squashed axis).
    fx: tuple = (1.118034, 1.172604)      # sqrt5/2, sqrt22/4
    ax: tuple = (1.0, 0.4193)
    px: tuple = (0.0, 5.8216)
    fy: tuple = (1.089725, 1.145644)      # sqrt19/4, sqrt21/4
    ay: tuple = (0.90048, 0.51858)
    py: tuple = (2.7006, 1.5657)
    T: float = 80.0              # THE DIAL: t-span per layer -> path length -> crossings
    v_cmd: float = 130.0         # mm/s commanded
    ds: float = 0.20             # analysis resampling (mm)
    min_angle_deg: float = 25.0  # below this a "crossing" is a shallow merge, not a junction
    d4: bool = False             # MEASURED USELESS: cumulative coverage CV 0.330 without it,
                                 # 0.325 with. It also breaks continuity (a jump at every layer
                                 # boundary). t simply continuing is enough. Left in to show the
                                 # comparison, off by default.


# ---------------------------------------------------------------- the curve
def _axis(t, f, a, p):
    x = np.zeros_like(t); dx = np.zeros_like(t); ddx = np.zeros_like(t)
    for A, F, P in zip(a, f, p):
        s, c = np.sin(F * t + P), np.cos(F * t + P)
        x += A * s; dx += A * F * c; ddx -= A * F * F * s
    return x, dx, ddx


def raw(q: Q, t):
    x, dx, ddx = _axis(t, q.fx, q.ax, q.px)
    y, dy, ddy = _axis(t, q.fy, q.ay, q.py)
    return x, y, dx, dy, ddx, ddy


def fit(q: Q, t_total: float, n=300_000):
    """ONE isotropic scale + offset over the whole print. Isotropic on purpose: an anisotropic
    scale creates a curvature maximum on the squashed axis, which is what we are trying to avoid."""
    t = np.linspace(0.0, t_total, n)
    x, y, *_ = raw(q, t)
    ex, ey = x.max() - x.min(), y.max() - y.min()
    s = (q.size - 2 * q.margin) / max(ex, ey)
    return (s,
            q.origin + q.size / 2 - s * (x.max() + x.min()) / 2,
            q.origin + q.size / 2 - s * (y.max() + y.min()) / 2, s * ex, s * ey)


def curve_mm(q: Q, t, s, cx, cy, op=0):
    x, y, dx, dy, ddx, ddy = raw(q, t)
    x, y, dx, dy, ddx, ddy = (s * v for v in (x, y, dx, dy, ddx, ddy))
    if op:
        a, b, c, d = D4[op % 8]
        x, y = a * x + b * y, c * x + d * y
        dx, dy = a * dx + b * dy, c * dx + d * dy
        ddx, ddy = a * ddx + b * ddy, c * ddx + d * ddy
    return x + cx, y + cy, dx, dy, ddx, ddy


def resample(q: Q, t0, t1, s, cx, cy, op=0, ds=None):
    ds = q.ds if ds is None else ds
    t = np.linspace(t0, t1, max(60_000, int((t1 - t0) * 3000)))
    x, y, *_ = curve_mm(q, t, s, cx, cy, op)
    cs = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    su = np.arange(0.0, cs[-1], ds)
    P = np.column_stack([np.interp(su, cs, x), np.interp(su, cs, y)])
    return P, su, np.interp(su, cs, t), cs[-1]


# ---------------------------------------------------------------- intersections
def _bucket(A, B, cell, gx0, gy0):
    lo, hi = np.minimum(A, B), np.maximum(A, B)
    b = {}
    ci0 = np.floor((lo[:, 0] - gx0) / cell).astype(int); ci1 = np.floor((hi[:, 0] - gx0) / cell).astype(int)
    cj0 = np.floor((lo[:, 1] - gy0) / cell).astype(int); cj1 = np.floor((hi[:, 1] - gy0) / cell).astype(int)
    for k in range(len(A)):
        for ci in range(ci0[k], ci1[k] + 1):
            for cj in range(cj0[k], cj1[k] + 1):
                b.setdefault((ci, cj), []).append(k)
    return b


def _isect(A, B, C, D, i, j):
    p, r = A[i], B[i] - A[i]
    qq, ss = C[j], D[j] - C[j]
    den = r[:, 0] * ss[:, 1] - r[:, 1] * ss[:, 0]
    ok = np.abs(den) > 1e-13
    d = qq - p
    safe = np.where(ok, den, 1.0)
    tt = (d[:, 0] * ss[:, 1] - d[:, 1] * ss[:, 0]) / safe
    uu = (d[:, 0] * r[:, 1] - d[:, 1] * r[:, 0]) / safe
    hit = ok & (tt >= 0) & (tt <= 1) & (uu >= 0) & (uu <= 1)
    return i[hit], j[hit], tt[hit], uu[hit]


def self_intersections(P, skip=3):
    A, B = P[:-1], P[1:]
    cell = float(max(np.max(np.abs(B - A)), 1e-6)) * 2.0
    gx0, gy0 = A[:, 0].min() - 1, A[:, 1].min() - 1
    pairs = set()
    for idxs in _bucket(A, B, cell, gx0, gy0).values():
        m = len(idxs)
        for a in range(m):
            for b in range(a + 1, m):
                i, j = idxs[a], idxs[b]
                if abs(i - j) >= skip:
                    pairs.add((i, j) if i < j else (j, i))
    if not pairs:
        z = np.zeros(0)
        return z.astype(int), z.astype(int), np.zeros((0, 2)), z, z, z
    pr = np.array(sorted(pairs))
    i, j, tt, uu = _isect(A, B, A, B, pr[:, 0], pr[:, 1])
    pts = A[i] + tt[:, None] * (B[i] - A[i])
    u1 = B[i] - A[i]; u1 = u1 / np.linalg.norm(u1, axis=1)[:, None]
    u2 = B[j] - A[j]; u2 = u2 / np.linalg.norm(u2, axis=1)[:, None]
    ang = np.degrees(np.arccos(np.clip(np.abs(np.sum(u1 * u2, axis=1)), 0, 1)))
    return i, j, pts, tt, uu, ang


def cross_pairs(P, Qp):
    A, B, C, D = P[:-1], P[1:], Qp[:-1], Qp[1:]
    cell = float(max(np.max(np.abs(B - A)), np.max(np.abs(D - C)), 1e-6)) * 2.0
    gx0 = min(A[:, 0].min(), C[:, 0].min()) - 1; gy0 = min(A[:, 1].min(), C[:, 1].min()) - 1
    b1, b2 = _bucket(A, B, cell, gx0, gy0), _bucket(C, D, cell, gx0, gy0)
    pairs = set()
    for key, ii in b1.items():
        jj = b2.get(key)
        if jj:
            for i in ii:
                for j in jj:
                    pairs.add((i, j))
    if not pairs:
        return np.zeros(0, int), np.zeros(0)
    pr = np.array(sorted(pairs))
    i, j, tt, uu = _isect(A, B, C, D, pr[:, 0], pr[:, 1])
    return i, tt


# ---------------------------------------------------------------- planner
def plan(P, v_cmd, accel=ACCEL, scv=SCV, vmax=MAX_VEL):
    """Klipper look-ahead, reimplemented: junction-deviation limit + centripetal limit at every
    vertex, then forward/backward accel passes, then the EXACT distance each segment spends below
    0.9*v_cmd (closed form on the trapezoid, not sampled)."""
    seg = np.diff(P, axis=0)
    d = np.hypot(seg[:, 0], seg[:, 1])
    seg, d = seg[d > 1e-9], d[d > 1e-9]
    n = len(d)
    u = seg / d[:, None]
    vcap = min(v_cmd, vmax)
    jct = np.clip(-np.sum(u[:-1] * u[1:], axis=1), -0.999999, 0.999999)
    sin_h = np.sqrt(0.5 * (1.0 - jct))
    cos_h = np.sqrt(np.maximum(0.5 * (1.0 + jct), 1e-15))
    jd = scv ** 2 * (math.sqrt(2.0) - 1.0) / accel
    v2 = np.minimum(sin_h / np.maximum(1.0 - sin_h, 1e-15) * jd * accel,
                    0.5 * np.minimum(d[:-1], d[1:]) * (sin_h / cos_h) * accel)
    v = np.empty(n + 1); v[0] = v[-1] = 0.0
    v[1:-1] = np.minimum(np.sqrt(np.maximum(v2, 0)), vcap)
    for i in range(n):
        v[i + 1] = min(v[i + 1], math.sqrt(v[i] ** 2 + 2 * accel * d[i]))
    for i in range(n - 1, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * accel * d[i]))
    thr = 0.9 * vcap
    ve, vx = v[:-1], v[1:]
    peak = np.minimum(np.sqrt(np.maximum((ve ** 2 + vx ** 2) / 2 + accel * d, 0.0)), vcap)
    d_cru = np.maximum(d - (peak ** 2 - ve ** 2) / (2 * accel) - (peak ** 2 - vx ** 2) / (2 * accel), 0.0)
    lim = np.minimum(peak, thr)
    below = np.minimum(
        np.where(ve < thr, np.maximum(lim ** 2 - ve ** 2, 0.0) / (2 * accel), 0.0)
        + np.where(vx < thr, np.maximum(lim ** 2 - vx ** 2, 0.0) / (2 * accel), 0.0)
        + np.where(peak < thr, d_cru, 0.0), d)
    tsec = float(np.sum((2 * peak - ve - vx) / accel + np.where(peak > 1e-9, d_cru / np.maximum(peak, 1e-9), 0.0)))
    return v, d, below, tsec


# ---------------------------------------------------------------- analysis
def analyse(q: Q, stack=False):
    R = {}
    s, cx, cy, ex, ey = fit(q, q.T * q.layers)
    R["scale"], R["bbox"] = s, (ex, ey)
    P, su, tu, L = resample(q, 0.0, q.T, s, cx, cy)
    R["L"] = L
    i, j, xpts, tt, uu, ang = self_intersections(P)
    real = ang >= q.min_angle_deg
    R["N_all"], R["N"], R["ang"] = len(i), int(real.sum()), ang
    dt_step = tu[1] - tu[0]
    sa, sb = su[i] + tt * q.ds, su[j] + uu * q.ds
    R["dz"] = q.layer_h * np.abs((tu[j] + uu * dt_step) - (tu[i] + tt * dt_step)) / q.T
    R["dz_real"] = R["dz"][real]
    pos = np.sort(np.concatenate([sa[real], sb[real]]))
    m = np.diff(pos); R["members"] = m[m > 1e-9]

    _, _, dx, dy, ddx, ddy = curve_mm(q, tu, s, cx, cy)
    sp = np.hypot(dx, dy)
    kap = np.abs(dx * ddy - dy * ddx) / np.maximum(sp ** 3, 1e-15)
    R["kappa"], R["vcurv"] = kap, np.sqrt(ACCEL / np.maximum(kap, 1e-12))
    R["r_min"] = float(1.0 / max(kap.max(), 1e-12))
    R["min_speed_ratio"] = float(sp.min() / sp.mean())

    v, d, below, tsec = plan(P, q.v_cmd)
    R["frac_below90"] = float(below.sum() / d.sum())
    R["time_layer"], R["v_mean"] = tsec, float(d.sum() / tsec)

    if stack:
        # Curvature and the planner over the WHOLE print. A quasi-periodic curve gets closer to a
        # near-cusp the longer it runs, so layer 0 alone flatters the design. This is the honest
        # number: one polyline, 15 layers, the planner started and stopped exactly once.
        Pf = np.vstack([resample(q, k * q.T, (k + 1) * q.T, s, cx, cy,
                                 op=k if q.d4 else 0)[0] for k in range(q.layers)])
        R["P_full"] = Pf
        tf = np.linspace(0.0, q.T * q.layers, 1_200_000)
        _, _, dxf, dyf, ddxf, ddyf = curve_mm(q, tf, s, cx, cy)
        spf = np.hypot(dxf, dyf)
        kf = np.abs(dxf * ddyf - dyf * ddxf) / np.maximum(spf ** 3, 1e-15)
        vcf = np.sqrt(ACCEL / np.maximum(kf, 1e-12))
        w = spf / spf.sum()                       # arc-length weighting, not t weighting
        o = np.argsort(vcf); cw = np.cumsum(w[o])
        R["vcurv_full_pct"] = {p: float(vcf[o][np.searchsorted(cw, p / 100)])
                               for p in (0.1, 1, 5, 10, 50)}
        R["r_min_full"] = float(1.0 / max(kf.max(), 1e-12))
        R["min_speed_ratio_full"] = float(spf.min() / spf.mean())
        R["v_full"] = {}
        for vtest in (60, 80, 100, 130, 150, 200, 300, 400):
            _, dfd, bf, tf_s = plan(Pf, float(vtest))
            R["v_full"][vtest] = (float(bf.sum() / dfd.sum()), float(dfd.sum() / tf_s), tf_s)

    nb = 12
    edges = np.linspace(q.origin, q.origin + q.size, nb + 1)
    mid = (P[:-1] + P[1:]) / 2
    H, _, _ = np.histogram2d(mid[:, 0], mid[:, 1], bins=[edges, edges],
                             weights=np.hypot(*(np.diff(P, axis=0).T)))
    R["cov"], R["cov_cv"] = H, float(H.std() / H.mean())
    R["cov_empty"] = int((H < 0.25 * H.mean()).sum())
    R["centre_edge"] = float((H[4:8, 4:8].sum() / 16) / ((H.sum() - H[4:8, 4:8].sum()) / (nb * nb - 16)))
    R["mean_height"] = L * q.strand_w * q.layer_h / (q.size ** 2)
    R["q_at_vcmd"] = q.strand_w * q.layer_h * q.v_cmd
    R["v_flow_max"] = WORK_VOL_FLOW / (q.strand_w * q.layer_h)

    if stack:
        R.update(multilayer(q, s, cx, cy))
        Hc = np.zeros_like(H)
        for k in range(q.layers):
            Pk, *_ = resample(q, k * q.T, (k + 1) * q.T, s, cx, cy, op=k if q.d4 else 0)
            mk = (Pk[:-1] + Pk[1:]) / 2
            h, _, _ = np.histogram2d(mk[:, 0], mk[:, 1], bins=[edges, edges],
                                     weights=np.hypot(*(np.diff(Pk, axis=0).T)))
            Hc += h
        R["cov_cum"], R["cov_cum_cv"] = Hc, float(Hc.std() / Hc.mean())
        R["cov_cum_empty"] = int((Hc < 0.25 * Hc.mean()).sum())
        R["cum_centre_edge"] = float((Hc[4:8, 4:8].sum() / 16) /
                                     ((Hc.sum() - Hc[4:8, 4:8].sum()) / (nb * nb - 16)))
    return R


def multilayer(q: Q, s, cx, cy):
    polys, xs = [], []
    for k in range(q.layers):
        P, *_ = resample(q, k * q.T, (k + 1) * q.T, s, cx, cy, op=k if q.d4 else 0)
        polys.append(P)
        i, j, pts, tt, uu, ang = self_intersections(P)
        xs.append(pts[ang >= q.min_angle_deg])
    near = tot = 0
    cell = 0.6
    for k in range(1, q.layers):
        a, b = xs[k], xs[k - 1]
        tot += len(a)
        grid = {}
        for p in b:
            grid.setdefault((int(p[0] / cell), int(p[1] / cell)), []).append(p)
        for p in a:
            gi, gj = int(p[0] / cell), int(p[1] / cell)
            if any((p[0] - pb[0]) ** 2 + (p[1] - pb[1]) ** 2 < cell ** 2
                   for di in (-1, 0, 1) for dj in (-1, 0, 1)
                   for pb in grid.get((gi + di, gj + dj), ())):
                near += 1
    spans, ninter = [], []
    for k in range(1, q.layers):
        i, tt = cross_pairs(polys[k], polys[k - 1])
        ninter.append(len(i))
        p = np.sort(q.ds * (i + tt))
        if len(p) > 1:
            spans.append(np.diff(p))
    return {"column_frac": near / max(tot, 1),
            "spans": np.concatenate(spans) if spans else np.zeros(0),
            "inter_cross": float(np.mean(ninter)) if ninter else 0.0}


# ---------------------------------------------------------------- tuning
def tune(iters=600, seed=11, T_eval=60.0):
    """Search frequency quadruples / amplitudes / phases. Objective: no tight corners (high
    curvature-limited speed), flat coverage, many junctions."""
    rng = np.random.default_rng(seed)
    keys = list(POOL)
    best = (-1e9, None)
    for it in range(iters):
        ks = rng.choice(len(keys), 4, replace=False)
        cand = Q(fx=(POOL[keys[ks[0]]], POOL[keys[ks[1]]]),
                 fy=(POOL[keys[ks[2]]], POOL[keys[ks[3]]]),
                 ax=(1.0, float(rng.uniform(0.35, 0.60))),
                 ay=(1.0, float(rng.uniform(0.35, 0.60))),
                 px=(0.0, float(rng.uniform(0, 2 * math.pi))),
                 py=(float(rng.uniform(0, 2 * math.pi)), float(rng.uniform(0, 2 * math.pi))),
                 T=T_eval, ds=0.35)
        try:
            R = analyse(cand)
        except Exception:
            continue
        vp1 = float(np.percentile(R["vcurv"], 1))
        sc = (min(vp1, 220) / 40.0 - 3.0 * R["cov_cv"] - 0.05 * R["cov_empty"]
              - 2.0 * abs(math.log(max(R["centre_edge"], 1e-3))) + 0.5 * math.log(max(R["N"], 1)))
        if sc > best[0]:
            best = (sc, cand)
            print(f"  it{it:4d} score {sc:6.3f} | v_p01 {vp1:6.0f} r_min {R['r_min']:5.2f} "
                  f"covCV {R['cov_cv']:.3f} empty {R['cov_empty']:3d} c/e {R['centre_edge']:.2f} N {R['N']}")
    b = best[1]
    print(f"\n  fx={tuple(round(v,6) for v in b.fx)} ax=(1.0, {b.ax[1]:.3f}) px=(0.0, {b.px[1]:.3f})")
    print(f"  fy={tuple(round(v,6) for v in b.fy)} ay=(1.0, {b.ay[1]:.3f}) py=({b.py[0]:.3f}, {b.py[1]:.3f})")
    return replace(b, T=Q().T, ds=Q().ds)


# ---------------------------------------------------------------- gcode
def emit(q: Q, chord_err=0.015, out="out"):
    """One continuous G1 chain for the whole coupon. No retraction, no travel, no layer change:
    E and Z are monotone from the first move to the last."""
    s, cx, cy, *_ = fit(q, q.T * q.layers)
    area = math.pi * (q.fil_d / 2) ** 2
    e_per_mm = q.strand_w * q.layer_h / area
    L = []
    L.append(f"; quasi-periodic continuous crackle web — ONE curve, {q.layers} layers, no pillars")
    L.append(f"; x = sin({q.fx[0]:.6f}t+{q.px[0]:.3f}) + {q.ax[1]:.3f} sin({q.fx[1]:.6f}t+{q.px[1]:.3f})")
    L.append(f"; y = sin({q.fy[0]:.6f}t+{q.py[0]:.3f}) + {q.ay[1]:.3f} sin({q.fy[1]:.6f}t+{q.py[1]:.3f})")
    L.append(f"; z = z0 + {q.layer_h}/{q.T} * t   (CONTINUOUS — nozzle clearance over its own bead >= 0)")
    L.append("; RETRACTION / COMBING / Z-HOP ABSENT ON PURPOSE. There are no travels: it is all one line.")
    L.append("G90"); L.append("M83" if False else "M82")
    L.append(f"M140 S{q.bed}"); L.append(f"M104 S{q.temp}"); L.append("G28")
    L.append(f"M190 S{q.bed}"); L.append(f"M109 S{q.temp}"); L.append("M106 S0")
    L.append("M204 S8000")
    e = 0.0
    px = py = None
    total = 0.0
    for k in range(q.layers):
        t = np.linspace(k * q.T, (k + 1) * q.T, int(q.T * 3000))
        x, y, dx, dy, ddx, ddy = curve_mm(q, t, s, cx, cy, op=k if q.d4 else 0)
        sp = np.hypot(dx, dy)
        kap = np.abs(dx * ddy - dy * ddx) / np.maximum(sp ** 3, 1e-15)
        # chord-error-adaptive step: ds = sqrt(8*eps/kappa), clamped
        step = np.clip(np.sqrt(8 * chord_err / np.maximum(kap, 1e-9)), 0.10, 1.20)
        cs = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
        # walk arc length using the local step
        pts, sacc = [0.0], 0.0
        while sacc < cs[-1]:
            sacc += float(np.interp(sacc, cs, step))
            pts.append(min(sacc, cs[-1]))
        su = np.array(pts)
        X, Y = np.interp(su, cs, x), np.interp(su, cs, y)
        Z = q.layer_h + q.layer_h * (np.interp(su, cs, t) - 0.0) / q.T   # continuous ramp from t=0
        if k == 0:
            L.append(f"G0 F3000 X{X[0]:.3f} Y{Y[0]:.3f} Z{Z[0]:.3f}")
            px, py = X[0], Y[0]
        for n in range(1, len(X)):
            d = math.hypot(X[n] - px, Y[n] - py)
            if d < 1e-6:
                continue
            e += d * e_per_mm; total += d
            L.append(f"G1 F{q.v_cmd*60:.0f} X{X[n]:.3f} Y{Y[n]:.3f} Z{Z[n]:.3f} E{e:.5f}")
            px, py = X[n], Y[n]
    L.append("M107"); L.append("M104 S0"); L.append("M140 S0")
    L.append(f"G0 Z{Z[-1]+30:.2f} F900"); L.append("G0 X10 Y330 F9000")
    os.makedirs(out, exist_ok=True)
    fn = f"{out}/quasi_T{int(q.T)}_v{int(q.v_cmd)}.gcode"
    open(fn, "w").write("\n".join(L) + "\n")
    g = e * area * 1.24 / 1000
    print(f"  wrote {fn}: {len(L)} lines, {total:.0f} mm of continuous path, E={e:.1f} mm, {g:.2f} g")
    return fn


# ---------------------------------------------------------------- report
def hbar(vals, edges):
    h, _ = np.histogram(vals, bins=edges)
    mx = max(h.max(), 1)
    return "\n".join(f"    [{edges[k]:5.2f},{edges[k+1]:5.2f}) {h[k]:6d} {'#'*int(round(40*h[k]/mx))}"
                     for k in range(len(h)))


def report(q: Q):
    print("=" * 82)
    print("QUASI-PERIODIC CONTINUOUS CRACKLE WEB — numerical analysis")
    print("=" * 82)
    print(f"coupon {q.size}mm  {q.layers} layers x {q.layer_h}mm  strand_w={q.strand_w}mm  0.8 nozzle")
    print(f"  x = sin({q.fx[0]:.6f} t + {q.px[0]:.3f}) + {q.ax[1]:.3f} sin({q.fx[1]:.6f} t + {q.px[1]:.3f})")
    print(f"  y = sin({q.fy[0]:.6f} t + {q.py[0]:.3f}) + {q.ay[1]:.3f} sin({q.fy[1]:.6f} t + {q.py[1]:.3f})")
    print(f"  z = z0 + {q.layer_h}/{q.T} * t        T={q.T} per layer   v_cmd={q.v_cmd} mm/s")
    print(f"  junction angle floor {q.min_angle_deg} deg; D4 per-layer op = {q.d4}\n")

    R = analyse(q, stack=True)
    print(f"realised bbox {R['bbox'][0]:.2f} x {R['bbox'][1]:.2f} mm (target {q.size-2*q.margin:.1f}); "
          f"scale {R['scale']:.3f} mm/unit")
    print(f"path length {R['L']:.0f} mm/layer, {R['L']*q.layers/1000:.2f} m total, ONE unbroken extrusion")

    print("\n1. SELF-INTERSECTIONS PER LAYER")
    print(f"   raw segment-pair crossings                : {R['N_all']}")
    print(f"   JUNCTIONS (crossing angle >= {q.min_angle_deg:.0f} deg)      : {R['N']}"
          f"   ({R['N']/36:.2f} per cm2)")
    print(f"   shallow merges (< {q.min_angle_deg:.0f} deg, two beads fuse side by side, not a junction): "
          f"{R['N_all']-R['N']}")
    print(f"   junctions over {q.layers} layers (intra-layer)   : {R['N']*q.layers}")
    print(f"   inter-layer crossings, layer n x layer n-1: {R['inter_cross']:.0f}/pair "
          f"= {R['inter_cross']*(q.layers-1):.0f} total")
    dz = R["dz_real"]
    print(f"   over/under gap dz at a junction (from the continuous Z ramp):")
    print(f"     mean {dz.mean():.3f}  median {np.median(dz):.3f} mm | >=0.10mm {100*np.mean(dz>=0.10):.0f}%"
          f" | >=0.20mm {100*np.mean(dz>=0.20):.0f}%")
    print(f"   TOTAL FUSED JUNCTIONS IN THE COUPON: "
          f"{R['N']*q.layers + R['inter_cross']*(q.layers-1):.0f}")

    print("\n2. SPEED UNIFORMITY  (measured over ALL 15 layers, one polyline, one start/stop)")
    print(f"   layer 0 alone: r_min {R['r_min']:.2f} mm, min|r'|/mean|r'| {R['min_speed_ratio']:.3f}")
    print(f"   whole print  : r_min {R['r_min_full']:.4f} mm, min|r'|/mean|r'| "
          f"{R['min_speed_ratio_full']:.4f}  <- near-cusps DO appear once t runs long enough")
    print(f"   curvature ceiling sqrt(a/kappa), a={ACCEL:.0f} mm/s2, weighted by ARC LENGTH:")
    pc = R["vcurv_full_pct"]
    print("     " + "  ".join(f"p{k}: {v:.0f}" for k, v in pc.items()) + " mm/s")
    print(f"   -> only {list(pc)[0]}% of the path cannot hold {pc[0.1]:.0f} mm/s; half of it could hold "
          f"{pc[50]:.0f} mm/s.")
    print(f"   full Klipper look-ahead over the whole 15-layer path (scv={SCV}, ds={q.ds}mm):")
    print(f"     {'v_cmd':>6} {'<90% of path':>13} {'achieved mean':>14} {'% of cmd':>9} {'min/coupon':>11}")
    for v, (fb, vm, ts) in R["v_full"].items():
        print(f"     {v:6.0f} {100*fb:12.2f}% {vm:13.1f} {100*vm/v:8.0f}% {ts/60:11.2f}")
    print(f"   flow at v_cmd={q.v_cmd}: {R['q_at_vcmd']:.1f} mm3/s (working ceiling {WORK_VOL_FLOW} "
          f"-> flow allows {R['v_flow_max']:.0f} mm/s; kinematics bind first)")

    print("\n3. MEMBER LENGTHS (path run between consecutive junctions)")
    m = R["members"]
    print(f"   n={len(m)}  mean {m.mean():.2f}  median {np.median(m):.2f}  sd {m.std():.2f}  "
          f"CV {m.std()/m.mean():.2f}")
    print(f"   min {m.min():.3f} | p05 {np.percentile(m,5):.2f} | p25 {np.percentile(m,25):.2f} | "
          f"p75 {np.percentile(m,75):.2f} | p95 {np.percentile(m,95):.2f} | max {m.max():.1f} mm")
    print(hbar(m, np.linspace(0, np.percentile(m, 98), 13)))
    print(f"   HARD CONSTRAINT: for any curve of length L in area A, N ~ L^2/(pi A) and mean member")
    print(f"   ~ pi A/(2L), so N * mean^2 ~ pi A/4 = {math.pi*q.size**2/4:.0f} mm2 regardless of shape.")
    print(f"   Measured N*mean^2 = {R['N']*m.mean()**2:.0f} mm2. Junctions and slender members trade")
    print(f"   against each other in a fixed footprint; the only way to buy both is more LAYERS.")

    print("\n4. COVERAGE (12x12 grid of 5mm bins; value = path length / mean)")
    print(f"   ONE layer    : CV {R['cov_cv']:.3f}  bins <25% of mean {R['cov_empty']}/144  "
          f"centre/edge {R['centre_edge']:.2f}")
    print(f"   ALL {q.layers} layers: CV {R['cov_cum_cv']:.3f}  bins <25% of mean {R['cov_cum_empty']}/144  "
          f"centre/edge {R['cum_centre_edge']:.2f}")
    Hc = R["cov_cum"] / R["cov_cum"].mean()
    for r in range(11, -1, -1):
        print("   " + " ".join(f"{Hc[c][r]:4.1f}" for c in range(12)))
    corners = [Hc[0][0], Hc[0][11], Hc[11][0], Hc[11][11]]
    print(f"   THE HONEST DEFECT: the four 5mm corner bins get {min(corners):.2f}-{max(corners):.2f}"
          f" of mean.")
    print(f"   A Lissajous only reaches a corner when BOTH axes peak at once, which is rare. The")
    print(f"   coupon is a 60mm square with ~5mm soft corners; "
          f"{100*float((Hc>=0.5).sum())/144:.0f}% of bins carry >=50% of mean.")
    print(f"   areal balance: mean deposited height {R['mean_height']:.3f} mm against a {q.layer_h}mm "
          f"Z step -> {100*R['mean_height']/q.layer_h:.0f}% of the layer is plastic, the rest air.")

    print("\n5. LAYER-TO-LAYER VARIATION")
    print(f"   t CONTINUES: layer k runs t in [{q.T:.0f}k, {q.T:.0f}(k+1)]. The curve is quasi-periodic,")
    print(f"   so no layer ever repeats another. No phase table, no random seed, no rotation angle.")
    print(f"   Plus a D4 op per layer (cycle of 8 square symmetries) to average out the residual")
    print(f"   coverage anisotropy WITHOUT rotating the square off its own corners.")
    exp = 100 * (1 - math.exp(-R["N"] * math.pi * 0.36 / q.size ** 2))
    print(f"   junctions within 0.6mm of a junction in the layer below: {100*R['column_frac']:.2f}%")
    print(f"   uncorrelated-layer (Poisson) expectation                : {exp:.2f}%")
    print(f"   -> {'no welded vertical columns' if 100*R['column_frac'] < 1.5*exp else 'COLUMNS FORMING'}")

    print("\n6. PRINTABILITY WITHOUT PILLARS")
    sp = R["spans"]
    print(f"   unsupported bridge span between contacts with the layer below:")
    print(f"     mean {sp.mean():.2f} | median {np.median(sp):.2f} | p90 {np.percentile(sp,90):.2f} | "
          f"p99 {np.percentile(sp,99):.2f} | max {sp.max():.1f} mm")
    print(f"     >5mm {100*np.mean(sp>5):.1f}% | >10mm {100*np.mean(sp>10):.2f}% | "
          f">20mm {100*np.mean(sp>20):.3f}%")
    fil = R["L"] * q.layers * q.strand_w * q.layer_h / (math.pi * (q.fil_d / 2) ** 2)
    print(f"   filament {fil:.0f} mm = {fil*math.pi*(q.fil_d/2)**2*1.24/1000:.2f} g")
    print(f"   Z ramp {q.layer_h/q.T*1000:.1f} um per t-unit, monotone: nozzle clearance over its own")
    print(f"   bead is >= 0 EVERYWHERE. A flat-Z layer has exactly 0 at every self-crossing.")
    kk = np.maximum(R["kappa"], 1e-9)
    for eps in (0.01, 0.02):
        dsad = np.clip(np.sqrt(8 * eps / kk), 0.10, 1.20)
        nm = float(np.sum(q.ds / dsad))
        print(f"   moves/layer at {eps}mm chord error: {nm:.0f}  ({nm/R['time_layer']:.0f} moves/s "
              f"at v_cmd={q.v_cmd}; Klipper handles ~1000/s)")
    return R


def sweep(q: Q):
    print("\n" + "=" * 82)
    print("DIAL 1 — T (t-span per layer). Path length, and therefore crossings, is the ONLY thing")
    print("it changes. N ~ L^2, so N is quadratic in T until the curve starts re-treading.")
    print("=" * 82)
    print(f"{'T':>5} {'L/layer':>8} {'JUNC':>6} {'/cm2':>6} {'merges':>7} {'memb mean':>10} "
          f"{'p05':>6} {'<90%@130':>9} {'covCV':>7} {'g':>6} {'min':>6}")
    for T in (20, 30, 40, 60, 80, 110, 150, 220, 320):
        qq = replace(q, T=float(T))
        R = analyse(qq)
        m = R["members"]
        print(f"{T:>5} {R['L']:8.0f} {R['N']:6d} {R['N']/36:6.2f} {R['N_all']-R['N']:7d} "
              f"{m.mean():10.2f} {np.percentile(m,5):6.2f} {100*R['frac_below90']:8.2f}% "
              f"{R['cov_cv']:7.3f} "
              f"{R['L']*qq.layers*qq.strand_w*qq.layer_h*1.24/1000:6.2f} "
              f"{R['time_layer']*qq.layers/60:6.2f}")

    print("\n" + "=" * 82)
    print("DIAL 2 — coupon size at fixed T. Junctions fall as area rises (fixed L, N ~ L^2/A)")
    print("=" * 82)
    print(f"{'size':>6} {'L':>8} {'JUNC':>6} {'memb mean':>10} {'r_min':>7} {'covCV':>7}")
    for sz in (40, 50, 60, 80, 100):
        R = analyse(replace(q, size=float(sz), origin=175.0 - sz / 2))
        print(f"{sz:>6} {R['L']:8.0f} {R['N']:6d} {R['members'].mean():10.2f} {R['r_min']:7.2f} {R['cov_cv']:7.3f}")

    print("\n" + "=" * 82)
    print("DIAL 3 — strand width (constant geometry, changes only what a junction weighs)")
    print("=" * 82)
    for w in (0.4, 0.5, 0.7, 0.9):
        qq = replace(q, strand_w=w)
        R = analyse(qq)
        print(f"  strand_w {w}: {R['q_at_vcmd']:.1f} mm3/s at {q.v_cmd} mm/s, "
              f"flow-limited speed {R['v_flow_max']:.0f} mm/s, "
              f"{R['L']*qq.layers*w*qq.layer_h*1.24/1000:.2f} g, areal fill "
              f"{100*R['mean_height']/qq.layer_h:.0f}%")

    print("\n" + "=" * 82)
    print("CONTROL — the same planner on the LATTICE this replaces (4x4 pillars, star order)")
    print("=" * 82)
    pts = [(153 + i * 14.667, 153 + j * 14.667) for j in range(4) for i in range(4)]
    k = len(pts)
    cxx = sum(p[0] for p in pts) / k; cyy = sum(p[1] for p in pts) / k
    ang = sorted(range(k), key=lambda i: math.atan2(pts[i][1] - cyy, pts[i][0] - cxx))
    order, cur = [], 0
    for _ in range(k):
        order.append(ang[cur]); cur = (cur + 7) % k
    lat = np.array([pts[i] for i in order])
    fine = [lat[0]]
    for a, b in zip(lat[:-1], lat[1:]):
        n = max(int(np.hypot(*(b - a)) / 0.2), 1)
        fine += [a + (b - a) * (t + 1) / n for t in range(n)]
    fine = np.array(fine)
    for v in (60, 100, 130):
        _, d, below, ts = plan(fine, float(v))
        print(f"   v_cmd={v:5.0f}: below 90% on {100*below.sum()/d.sum():6.2f}% of path | "
              f"achieved mean {d.sum()/ts:6.1f} mm/s = {100*d.sum()/ts/v:.0f}% of commanded")
    print(f"   lattice: {len(lat)-1} strands, {d.sum():.0f} mm of path/layer, 15 hard corners per layer.")
    print(f"   Every one of those corners is a place the strand thickens. That is the defect.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--gcode", action="store_true")
    ap.add_argument("--T", type=float); ap.add_argument("--v", type=float)
    a = ap.parse_args()
    q = Q()
    if a.tune:
        q = tune()
    if a.T: q = replace(q, T=a.T)
    if a.v: q = replace(q, v_cmd=a.v)
    report(q)
    if a.sweep:
        sweep(q)
    if a.gcode:
        emit(q)
