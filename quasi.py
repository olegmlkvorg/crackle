#!/usr/bin/env python3
"""Quasi-periodic continuous crackle web — ONE self-intersecting curve, no pillars, no strand ends.

Answers Oleg's question ("why are you not doing continuous? is cracking require the segments?").
No. A junction forms wherever plastic crosses plastic; it does not care whether the two branches
came from two strands or from one curve crossing itself. The lattice buys nothing and costs two
things: a full stop at every pillar (so the strand thickens at both ends) and anchor mass that
makes no crossings.

FAMILY — 3 harmonics per axis, irrational frequency ratios:

  x(t) = Sx*[ ax1 sin(f1 t + p1) + ax2 sin(f2 t + p2) + ax3 sin(f3 t + p3) ] + x0
  y(t) = Sy*[ ay1 sin(g1 t + q1) + ay2 sin(g2 t + q2) + ay3 sin(g3 t + q3) ] + y0
  z(t) = z0 + (layer_h/T) * t                                <-- CONTINUOUS, never steps

  {f} u {g} are rationally independent (distinct square roots), so the orbit is dense on a
  6-torus: the curve never closes and every pass through a region lands somewhere new.

TWO NON-OBVIOUS THINGS THIS BUYS

  1. Z RAMPS CONTINUOUSLY. A bead's top surface is the Z at which it was laid. If Z only ever
     rises, every later pass has NON-NEGATIVE clearance over everything already down. A flat-Z
     layer has EXACTLY ZERO clearance at its own self-crossings: the nozzle ploughs through its own
     bead at every one. The old pillar design has that defect too.
  2. The two branches of a crossing are separated in t by dt, hence in Z by layer_h*dt/T. That is
     a DIALLED over/under gap: the junction is a contact point between two strands at different
     heights, not a coplanar smear. Crossings with dt near 0 are merges and are counted separately.

Run:  python3 quasi.py             # full numerical report on the tuned design
      python3 quasi.py --sweep     # the dials
      python3 quasi.py --tune      # re-run the parameter search
"""
from __future__ import annotations
import argparse, math, random
from dataclasses import dataclass, replace, field
import numpy as np

# ---- measured machine facts (given, not re-derived) ---------------------------
MAX_VOL_FLOW = 81.2       # mm3/s measured
WORK_VOL_FLOW = 68.8      # mm3/s working
ACCEL = 8000.0            # mm/s2 -- prints command M204 S8000
MAX_VEL = 800.0           # mm/s
SCV = 5.0                 # Klipper square_corner_velocity (stock)

R2, R3, R5, R6, R7, R10, R11, R13 = (math.sqrt(k) for k in (2, 3, 5, 6, 7, 10, 11, 13))


@dataclass
class Q:
    size: float = 60.0
    margin: float = 1.5
    origin: float = 145.0        # 60mm coupon centred on a 350 bed
    layer_h: float = 0.40
    layers: int = 15
    strand_w: float = 0.50       # ABSOLUTE strand width (decoupled, as crackle.py already does)
    fil_d: float = 1.75
    fx: tuple = (1.0, R2 / 2, R3 / 2)          # 1.0000, 0.7071, 0.8660
    ax: tuple = (1.0, 0.78, 0.46)
    px: tuple = (0.00, 1.05, 2.60)
    fy: tuple = (R5 / 2, R7 / 2, R11 / 4)      # 1.1180, 1.3229, 0.8292
    ay: tuple = (1.0, 0.78, 0.46)
    py: tuple = (1.70, 3.10, 0.40)
    T: float = 80.0              # THE DIAL: t-span per layer -> path length -> crossings
    v_cmd: float = 110.0         # mm/s commanded
    rot_per_layer: float = math.radians(137.507764)   # golden angle
    ds: float = 0.20             # analysis resampling (mm)
    min_angle_deg: float = 25.0  # below this a "crossing" is a shallow merge, not a junction


# ---------------------------------------------------------------- the curve
def raw(q: Q, t):
    """Curve + 1st and 2nd derivatives, analytic (never finite-differenced)."""
    z = np.zeros_like(t)
    x, y, dx, dy, ddx, ddy = z.copy(), z.copy(), z.copy(), z.copy(), z.copy(), z.copy()
    for a, f, p in zip(q.ax, q.fx, q.px):
        s_, c_ = np.sin(f * t + p), np.cos(f * t + p)
        x += a * s_; dx += a * f * c_; ddx -= a * f * f * s_
    for a, f, p in zip(q.ay, q.fy, q.py):
        s_, c_ = np.sin(f * t + p), np.cos(f * t + p)
        y += a * s_; dy += a * f * c_; ddy -= a * f * f * s_
    return x, y, dx, dy, ddx, ddy


def fit(q: Q, t_total: float, n=300_000):
    """ONE isotropic scale + offset over the whole print, so the bbox fills the square.
    Isotropic on purpose — an anisotropic scale creates a curvature maximum on the squashed axis."""
    t = np.linspace(0.0, t_total, n)
    x, y, *_ = raw(q, t)
    ex, ey = x.max() - x.min(), y.max() - y.min()
    s = (q.size - 2 * q.margin) / max(ex, ey)
    cx = q.origin + q.size / 2 - s * (x.max() + x.min()) / 2
    cy = q.origin + q.size / 2 - s * (y.max() + y.min()) / 2
    return s, cx, cy, s * ex, s * ey


def curve_mm(q: Q, t, s, cx, cy, rot=0.0):
    x, y, dx, dy, ddx, ddy = raw(q, t)
    x, y, dx, dy, ddx, ddy = (s * v for v in (x, y, dx, dy, ddx, ddy))
    if rot:
        c, sn = math.cos(rot), math.sin(rot)
        x, y = c * x - sn * y, sn * x + c * y
        dx, dy = c * dx - sn * dy, sn * dx + c * dy
        ddx, ddy = c * ddx - sn * ddy, sn * ddx + c * ddy
    return x + cx, y + cy, dx, dy, ddx, ddy


def resample(q: Q, t0, t1, s, cx, cy, rot=0.0, dense=None, ds=None):
    ds = q.ds if ds is None else ds
    dense = dense or max(60_000, int((t1 - t0) * 4000))
    t = np.linspace(t0, t1, dense)
    x, y, *_ = curve_mm(q, t, s, cx, cy, rot)
    cs = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    L = cs[-1]
    su = np.arange(0.0, L, ds)
    P = np.column_stack([np.interp(su, cs, x), np.interp(su, cs, y)])
    return P, su, np.interp(su, cs, t), L


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
    """Exact segment-pair self-intersections of a polyline, grid-bucketed."""
    A, B = P[:-1], P[1:]
    cell = float(max(np.max(np.abs(B - A)), 1e-6)) * 2.0
    gx0, gy0 = A[:, 0].min() - 1, A[:, 1].min() - 1
    buckets = _bucket(A, B, cell, gx0, gy0)
    pairs = set()
    for idxs in buckets.values():
        m = len(idxs)
        for a in range(m):
            for b in range(a + 1, m):
                i, j = idxs[a], idxs[b]
                if abs(i - j) < skip:
                    continue
                pairs.add((i, j) if i < j else (j, i))
    if not pairs:
        z = np.zeros(0)
        return z.astype(int), z.astype(int), np.zeros((0, 2)), z, z, z
    pr = np.array(sorted(pairs))
    i, j, tt, uu = _isect(A, B, A, B, pr[:, 0], pr[:, 1])
    pts = A[i] + tt[:, None] * (B[i] - A[i])
    u1 = (B[i] - A[i]); u1 = u1 / np.linalg.norm(u1, axis=1)[:, None]
    u2 = (B[j] - A[j]); u2 = u2 / np.linalg.norm(u2, axis=1)[:, None]
    ang = np.degrees(np.arccos(np.clip(np.abs(np.sum(u1 * u2, axis=1)), 0, 1)))
    return i, j, pts, tt, uu, ang


def cross_pairs(P, Qp):
    """Intersections BETWEEN two polylines (layer n against layer n-1)."""
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
    """Klipper look-ahead reimplemented: junction-deviation + centripetal limit, forward/backward
    pass, then the exact distance each segment spends below 0.9*v_cmd."""
    seg = np.diff(P, axis=0)
    d = np.hypot(seg[:, 0], seg[:, 1])
    seg, d = seg[d > 1e-9], d[d > 1e-9]
    n = len(d)
    u = seg / d[:, None]
    vcap = min(v_cmd, vmax)
    jct = np.clip(-np.sum(u[:-1] * u[1:], axis=1), -0.999999, 0.999999)
    sin_h = np.sqrt(0.5 * (1.0 - jct))
    cos_h = np.sqrt(np.maximum(0.5 * (1.0 + jct), 1e-15))
    R_jd = sin_h / np.maximum(1.0 - sin_h, 1e-15)
    jd = scv ** 2 * (math.sqrt(2.0) - 1.0) / accel
    v2 = np.minimum(R_jd * jd * accel, 0.5 * np.minimum(d[:-1], d[1:]) * (sin_h / cos_h) * accel)
    v = np.empty(n + 1); v[0] = v[-1] = 0.0
    v[1:-1] = np.minimum(np.sqrt(np.maximum(v2, 0)), vcap)
    for i in range(n):
        v[i + 1] = min(v[i + 1], math.sqrt(v[i] ** 2 + 2 * accel * d[i]))
    for i in range(n - 1, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * accel * d[i]))
    thr = 0.9 * vcap
    ve, vx = v[:-1], v[1:]
    peak = np.minimum(np.sqrt(np.maximum((ve ** 2 + vx ** 2) / 2 + accel * d, 0.0)), vcap)
    d_acc = np.maximum((peak ** 2 - ve ** 2) / (2 * accel), 0.0)
    d_dec = np.maximum((peak ** 2 - vx ** 2) / (2 * accel), 0.0)
    d_cru = np.maximum(d - d_acc - d_dec, 0.0)
    lim = np.minimum(peak, thr)
    below = np.minimum(
        np.where(ve < thr, np.maximum(lim ** 2 - ve ** 2, 0.0) / (2 * accel), 0.0)
        + np.where(vx < thr, np.maximum(lim ** 2 - vx ** 2, 0.0) / (2 * accel), 0.0)
        + np.where(peak < thr, d_cru, 0.0), d)
    tsec = float(np.sum((peak - ve) / accel + (peak - vx) / accel
                        + np.where(peak > 1e-9, d_cru / np.maximum(peak, 1e-9), 0.0)))
    return v, d, below, tsec


# ---------------------------------------------------------------- analysis
def analyse(q: Q, stack=False):
    R = {}
    t_total = q.T * q.layers
    s, cx, cy, ex, ey = fit(q, t_total)
    R["scale"], R["bbox"] = s, (ex, ey)

    P, su, tu, L = resample(q, 0.0, q.T, s, cx, cy)
    R["L"] = L
    i, j, xpts, tt, uu, ang = self_intersections(P)
    real = ang >= q.min_angle_deg
    R["N_all"], R["N"] = len(i), int(real.sum())
    R["ang"] = ang
    R["xpts"] = xpts[real]

    dt_step = tu[1] - tu[0]
    sa = su[i] + tt * q.ds
    sb = su[j] + uu * q.ds
    dtc = np.abs((tu[j] + uu * dt_step) - (tu[i] + tt * dt_step))
    R["dz"] = q.layer_h * dtc / q.T
    R["dz_real"] = R["dz"][real]

    pos = np.sort(np.concatenate([sa[real], sb[real]]))
    m = np.diff(pos); R["members"] = m[m > 1e-9]

    # curvature -> kinematic speed ceiling, sampled ON the arc-length polyline
    _, _, dx, dy, ddx, ddy = curve_mm(q, tu, s, cx, cy)
    sp = np.hypot(dx, dy)
    kap = np.abs(dx * ddy - dy * ddx) / np.maximum(sp ** 3, 1e-15)
    R["kappa"] = kap
    R["vcurv"] = np.sqrt(ACCEL / np.maximum(kap, 1e-12))
    R["r_min"] = float(1.0 / max(kap.max(), 1e-12))
    R["min_speed_ratio"] = float(sp.min() / sp.mean())

    v, d, below, tsec = plan(P, q.v_cmd)
    R["frac_below90"] = float(below.sum() / d.sum())
    R["time_layer"], R["v_mean"] = tsec, float(d.sum() / tsec)

    # coverage, one layer and cumulative
    nb = 12
    edges = np.linspace(q.origin, q.origin + q.size, nb + 1)
    mid = (P[:-1] + P[1:]) / 2
    dseg = np.hypot(*(np.diff(P, axis=0).T))
    H, _, _ = np.histogram2d(mid[:, 0], mid[:, 1], bins=[edges, edges], weights=dseg)
    R["cov"] = H
    R["cov_cv"] = float(H.std() / H.mean())
    R["cov_empty"] = int((H < 0.25 * H.mean()).sum())
    inner = H[4:8, 4:8].sum() / 16
    outer = (H.sum() - H[4:8, 4:8].sum()) / (nb * nb - 16)
    R["centre_edge"] = float(inner / outer)
    R["mean_height"] = L * q.strand_w * q.layer_h / (q.size ** 2)
    R["q_at_vcmd"] = q.strand_w * q.layer_h * q.v_cmd
    R["v_flow_max"] = WORK_VOL_FLOW / (q.strand_w * q.layer_h)

    if stack:
        R.update(multilayer(q, s, cx, cy))
        Hc = np.zeros_like(H)
        for k in range(q.layers):
            Pk, _, _, _ = resample(q, k * q.T, (k + 1) * q.T, s, cx, cy, rot=k * q.rot_per_layer)
            mk = (Pk[:-1] + Pk[1:]) / 2
            dk = np.hypot(*(np.diff(Pk, axis=0).T))
            h, _, _ = np.histogram2d(mk[:, 0], mk[:, 1], bins=[edges, edges], weights=dk)
            Hc += h
        R["cov_cum"] = Hc
        R["cov_cum_cv"] = float(Hc.std() / Hc.mean())
        R["cov_cum_empty"] = int((Hc < 0.25 * Hc.mean()).sum())
        R["cum_centre_edge"] = float((Hc[4:8, 4:8].sum() / 16) /
                                     ((Hc.sum() - Hc[4:8, 4:8].sum()) / (nb * nb - 16)))
    return R


def multilayer(q: Q, s, cx, cy):
    polys, xs = [], []
    for k in range(q.layers):
        P, su, tu, L = resample(q, k * q.T, (k + 1) * q.T, s, cx, cy, rot=k * q.rot_per_layer)
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
def score(q: Q, T_eval=None):
    """Cheap objective for the parameter search: flat coverage, no tight corners, many crossings."""
    qq = replace(q, T=T_eval or q.T, ds=0.35)
    try:
        R = analyse(qq)
    except Exception:
        return -1e9, None
    pen = 0.0
    pen -= 3.0 * R["cov_cv"]                                # flat coverage
    pen -= 0.06 * R["cov_empty"]                            # no dead cells
    pen -= 2.0 * abs(math.log(max(R["centre_edge"], 1e-3))) # no centre pile
    pen += 1.2 * min(R["r_min"], 2.0)                       # corners not tighter than ~2mm
    pen += 0.6 * math.log(max(R["N"], 1))                   # crossings are the product
    return pen, R


def tune(iters=400, seed=7):
    rng = random.Random(seed)
    pool = [1.0, R2 / 2, R3 / 2, R5 / 2, R6 / 3, R7 / 3, R10 / 3, R11 / 4, R13 / 4, R7 / 2, R3 / 3]
    best = (-1e9, None)
    base = Q()
    for it in range(iters):
        fs = rng.sample(pool, 6)
        a2, a3 = rng.uniform(0.45, 1.0), rng.uniform(0.2, 0.8)
        cand = replace(base,
                       fx=tuple(fs[:3]), fy=tuple(fs[3:]),
                       ax=(1.0, a2, a3), ay=(1.0, rng.uniform(0.45, 1.0), rng.uniform(0.2, 0.8)),
                       px=tuple(rng.uniform(0, 2 * math.pi) for _ in range(3)),
                       py=tuple(rng.uniform(0, 2 * math.pi) for _ in range(3)))
        sc, R = score(cand, T_eval=60.0)
        if sc > best[0]:
            best = (sc, cand)
            print(f"  it{it:4d} score {sc:7.3f}  covCV {R['cov_cv']:.3f} empty {R['cov_empty']:3d} "
                  f"c/e {R['centre_edge']:.2f} r_min {R['r_min']:.2f} N {R['N']}")
    return best[1]


# ---------------------------------------------------------------- report
def hbar(vals, edges):
    h, _ = np.histogram(vals, bins=edges)
    mx = max(h.max(), 1)
    return "\n".join(f"    [{edges[k]:5.2f},{edges[k+1]:5.2f}) {h[k]:6d} {'#'*int(round(40*h[k]/mx))}"
                     for k in range(len(h)))


def report(q: Q):
    print("=" * 80)
    print("QUASI-PERIODIC CONTINUOUS CRACKLE WEB — numerical analysis")
    print("=" * 80)
    print(f"coupon {q.size}mm  layers={q.layers} x {q.layer_h}mm  strand_w={q.strand_w}mm")
    print(f"  x freqs {tuple(round(f,5) for f in q.fx)}  amps {q.ax}")
    print(f"  y freqs {tuple(round(f,5) for f in q.fy)}  amps {q.ay}")
    print(f"  T={q.T} per layer   v_cmd={q.v_cmd} mm/s   junction angle floor {q.min_angle_deg} deg\n")

    R = analyse(q, stack=True)
    print(f"realised bbox {R['bbox'][0]:.2f} x {R['bbox'][1]:.2f} mm (target {q.size-2*q.margin:.1f}), "
          f"scale {R['scale']:.3f} mm/unit")
    print(f"path length per layer {R['L']:.0f} mm; total {R['L']*q.layers/1000:.2f} m")

    print("\n1. SELF-INTERSECTIONS PER LAYER")
    print(f"   raw segment-pair crossings           : {R['N_all']}")
    print(f"   junctions (crossing angle >= {q.min_angle_deg:.0f} deg): {R['N']}   "
          f"({R['N']/(q.size**2)*100:.2f} per cm2)")
    print(f"   shallow merges (angle < {q.min_angle_deg:.0f} deg)     : {R['N_all']-R['N']}"
          f"  <- these fuse into one fat strand, they are not junctions")
    print(f"   junctions over {q.layers} layers (intra-layer): {R['N']*q.layers}")
    print(f"   inter-layer crossings, layer n x layer n-1  : {R['inter_cross']:.0f} per pair "
          f"({R['inter_cross']*(q.layers-1):.0f} total)")
    dz = R["dz_real"]
    print(f"   over/under gap dz at a junction (from the continuous Z ramp):")
    print(f"     mean {dz.mean():.3f} median {np.median(dz):.3f} mm | "
          f">=0.10mm {100*np.mean(dz>=0.10):.0f}% | >=0.20mm {100*np.mean(dz>=0.20):.0f}%")
    print(f"   TOTAL fused junctions in the coupon: "
          f"{R['N']*q.layers + R['inter_cross']*(q.layers-1):.0f}")

    print("\n2. SPEED UNIFORMITY")
    vc = R["vcurv"]
    print(f"   min radius of curvature {R['r_min']:.2f} mm; min|r'|/mean|r'| = {R['min_speed_ratio']:.3f}")
    print(f"   curvature-limited speed sqrt(a/kappa), a={ACCEL:.0f}:")
    print(f"     p00 {vc.min():6.0f}  p01 {np.percentile(vc,1):6.0f}  p05 {np.percentile(vc,5):6.0f}  "
          f"p50 {np.percentile(vc,50):6.0f}  p95 {np.percentile(vc,95):6.0f} mm/s")
    print(f"   planner (Klipper look-ahead, scv={SCV}, ds={q.ds}mm):")
    print(f"     {'v_cmd':>6} {'<90% of path':>14} {'achieved mean':>15} {'s/layer':>9} {'min/coupon':>11}")
    for v in (60, 80, 100, 110, 130, 150, 200, 300):
        P, _, _, _ = resample(q, 0, q.T, *fit(q, q.T * q.layers)[:3])
        _, d, below, ts = plan(P, float(v))
        print(f"     {v:6.0f} {100*below.sum()/d.sum():13.2f}% {d.sum()/ts:14.1f} "
              f"{ts:9.1f} {ts*q.layers/60:11.2f}")
    print(f"   flow at v_cmd={q.v_cmd}: {R['q_at_vcmd']:.1f} mm3/s "
          f"(working ceiling {WORK_VOL_FLOW}; flow allows up to {R['v_flow_max']:.0f} mm/s)")

    print("\n3. MEMBER LENGTHS (path between consecutive junctions)")
    m = R["members"]
    print(f"   n={len(m)}  mean {m.mean():.2f}  median {np.median(m):.2f}  sd {m.std():.2f}  "
          f"CV {m.std()/m.mean():.2f}")
    print(f"   min {m.min():.3f}  p05 {np.percentile(m,5):.2f}  p25 {np.percentile(m,25):.2f}  "
          f"p75 {np.percentile(m,75):.2f}  p95 {np.percentile(m,95):.2f}  max {m.max():.1f}")
    print(hbar(m, np.linspace(0, np.percentile(m, 98), 13)))
    print(f"   theory check: for ANY curve of length L in area A, N ~ L^2/(pi A) and mean member "
          f"~ pi A/(2L),\n   so N*mean^2 ~ pi A/4 = {math.pi*q.size**2/4:.0f} mm2. "
          f"Measured N*mean^2 = {R['N']*m.mean()**2:.0f} mm2.")

    print("\n4. COVERAGE (12x12 grid of 5mm bins; value = path length / mean)")
    print(f"   ONE layer   : CV {R['cov_cv']:.3f}  bins <25% of mean {R['cov_empty']}/144  "
          f"centre/edge {R['centre_edge']:.2f}")
    print(f"   ALL {q.layers} layers: CV {R['cov_cum_cv']:.3f}  bins <25% of mean {R['cov_cum_empty']}/144  "
          f"centre/edge {R['cum_centre_edge']:.2f}")
    Hc = R["cov_cum"] / R["cov_cum"].mean()
    for r in range(11, -1, -1):
        print("   " + " ".join(f"{Hc[c][r]:4.1f}" for c in range(12)))
    print(f"   areal material balance: mean deposited height {R['mean_height']:.3f} mm against a "
          f"{q.layer_h}mm Z step\n   -> the layer is {100*R['mean_height']/q.layer_h:.0f}% "
          f"covered; the web is mostly air, which is the point")

    print("\n5. LAYER-TO-LAYER VARIATION")
    print(f"   t simply CONTINUES: layer k uses t in [{q.T}k, {q.T}(k+1)]. The curve is quasi-periodic,")
    print(f"   so no layer repeats another — no phase table needed. Plus a golden-angle rotation")
    print(f"   ({math.degrees(q.rot_per_layer):.2f} deg/layer) so the coverage anisotropy also precesses.")
    print(f"   junctions landing within 0.6mm of a junction in the layer below: "
          f"{100*R['column_frac']:.2f}%")
    print(f"   Poisson expectation for uncorrelated layers: "
          f"{100*(1-math.exp(-R['N']*math.pi*0.36/q.size**2)):.2f}%  -> "
          f"{'no column stacking' if R['column_frac'] < 1.6*(1-math.exp(-R['N']*math.pi*0.36/q.size**2)) else 'STACKING'}")

    print("\n6. PRINTABILITY WITHOUT PILLARS")
    sp = R["spans"]
    print(f"   unsupported span between contacts with the layer below (the bridge length):")
    print(f"     mean {sp.mean():.2f}  median {np.median(sp):.2f}  p90 {np.percentile(sp,90):.2f}  "
          f"p99 {np.percentile(sp,99):.2f}  max {sp.max():.1f} mm")
    print(f"     >5mm {100*np.mean(sp>5):.1f}%  >10mm {100*np.mean(sp>10):.2f}%  "
          f">20mm {100*np.mean(sp>20):.3f}%")
    fil = R["L"] * q.layers * q.strand_w * q.layer_h / (math.pi * (q.fil_d / 2) ** 2)
    print(f"   filament {fil:.0f} mm = {fil*math.pi*(q.fil_d/2)**2*1.24/1000:.2f} g")
    print(f"   Z ramp {q.layer_h/q.T*1000:.1f} um per t-unit, monotone -> nozzle clearance over its")
    print(f"   own bead is >= 0 EVERYWHERE. A flat-Z layer has exactly 0 at every self-crossing.")
    kk = np.maximum(R["kappa"], 1e-9)
    for eps in (0.01, 0.02):
        dsad = np.clip(np.sqrt(8 * eps / kk), 0.08, 1.0)
        nm = float(np.sum(q.ds / dsad))
        print(f"   moves/layer at {eps}mm chord error: {nm:.0f}  "
              f"({nm/R['time_layer']:.0f} moves/s at v_cmd={q.v_cmd})")
    return R


def sweep(q: Q):
    print("\n" + "=" * 80)
    print("DIAL — T (t-span per layer). The ONLY thing that moves; sets path length.")
    print("=" * 80)
    print(f"{'T':>5} {'L/layer':>8} {'junc':>6} {'/cm2':>6} {'merges':>7} {'memb mean':>10} "
          f"{'memb p05':>9} {'<90%@110':>9} {'covCV':>7} {'g':>6} {'min':>6}")
    for T in (20, 30, 40, 60, 80, 110, 150, 200):
        qq = replace(q, T=float(T))
        R = analyse(qq)
        m = R["members"]
        g = R["L"] * qq.layers * qq.strand_w * qq.layer_h * 1.24 / 1000
        print(f"{T:>5} {R['L']:8.0f} {R['N']:6d} {R['N']/36:6.2f} {R['N_all']-R['N']:7d} "
              f"{m.mean():10.2f} {np.percentile(m,5):9.2f} {100*R['frac_below90']:8.2f}% "
              f"{R['cov_cv']:7.3f} {g:6.2f} {R['time_layer']*qq.layers/60:6.2f}")

    print("\n" + "=" * 80)
    print("SECONDARY DIAL — coupon size at fixed T (crossings scale, members do not)")
    print("=" * 80)
    print(f"{'size':>6} {'L':>8} {'junc':>6} {'memb mean':>10} {'r_min':>7}")
    for sz in (40, 50, 60, 80, 100):
        qq = replace(q, size=float(sz), origin=175.0 - sz / 2)
        R = analyse(qq)
        print(f"{sz:>6} {R['L']:8.0f} {R['N']:6d} {R['members'].mean():10.2f} {R['r_min']:7.2f}")

    print("\n" + "=" * 80)
    print("CONTROL — the same planner on the LATTICE we are replacing (4x4, star order)")
    print("=" * 80)
    pts = [(145 + 8 + i * 14.667, 145 + 8 + j * 14.667) for j in range(4) for i in range(4)]
    k = len(pts)
    cxx = sum(p[0] for p in pts) / k; cyy = sum(p[1] for p in pts) / k
    ang = sorted(range(k), key=lambda i: math.atan2(pts[i][1] - cyy, pts[i][0] - cxx))
    order, cur = [], 0
    for _ in range(k):
        order.append(ang[cur]); cur = (cur + 7) % k
    lat = np.array([pts[i] for i in order])
    fine = [lat[0]]
    for a, b in zip(lat[:-1], lat[1:]):                    # resample to the same ds for fairness
        n = max(int(np.hypot(*(b - a)) / 0.2), 1)
        fine += [a + (b - a) * (t + 1) / n for t in range(n)]
    fine = np.array(fine)
    for v in (60, 110, 150):
        _, d, below, ts = plan(fine, float(v))
        print(f"   v_cmd={v:5.0f}: below 90% on {100*below.sum()/d.sum():6.2f}% of path length | "
              f"achieved mean {d.sum()/ts:6.1f} mm/s ({100*d.sum()/ts/v:.0f}% of commanded)")
    print(f"   lattice: {len(lat)-1} strands, {d.sum():.0f} mm of path, 16 full stops per layer")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--T", type=float); ap.add_argument("--v", type=float)
    a = ap.parse_args()
    q = Q()
    if a.tune:
        q = tune()
        print("\nTUNED:", q.fx, q.ax, q.px, q.fy, q.ay, q.py)
    if a.T: q = replace(q, T=a.T)
    if a.v: q = replace(q, v_cmd=a.v)
    report(q)
    if a.sweep:
        sweep(q)
