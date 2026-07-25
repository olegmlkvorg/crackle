#!/usr/bin/env python3
"""Quasi-periodic crackle web — ONE continuous self-intersecting curve, no pillars, no strand ends.

Answers Oleg's question ("why are you not doing continuous?"). A junction forms wherever plastic
crosses plastic; it does not care whether the two branches came from two strands or from one curve
crossing itself. So the lattice buys nothing and costs two things: a deceleration at every pillar
(the strand thickens at both ends) and anchor mass that makes no crossings.

FAMILY (2-3 harmonics per axis, irrational frequency ratios -> quasi-periodic, never repeats):

    x(t) = Sx * [ ax1 sin(t + p1) + ax2 sin(sqrt2 t + p2) + ca cos(wc t) ] + x0
    y(t) = Sy * [ ay1 sin(phi t + q1) + ay2 sin(sqrt5 t + q2) + ca sin(wc t) ] + y0
    z(t) = z0 + (layer_h / T) * t                      <-- CONTINUOUS, never steps

    {1, sqrt2} and {phi, sqrt5} are rationally independent, so the orbit is dense on the 4-torus:
    the curve never closes and every pass through a region lands somewhere new.

    The third term is a QUADRATURE CARRIER (cos on x, sin on y at the same frequency wc). It is a
    small circle riding the slow Lissajous. Its job is purely kinematic: |r'| >= ca*wc - |v_slow|,
    so the path speed can never reach zero and curvature can never blow up. ca is the dial between
    "pure Lissajous, cusp risk" and "tight coil, perfect speed but coplanar crossings".

    Z RAMPS CONTINUOUSLY with t. This is not decoration: it is what stops the nozzle ploughing.
    A bead's top surface is the Z at which it was laid. If Z only ever rises, every later pass has
    non-negative clearance over everything already down. A flat-Z layer has EXACTLY ZERO clearance
    at its own self-crossings -- the nozzle ploughs through its own bead 500 times per layer. The
    old pillar design has that defect too; nobody noticed because the strands were thin.

Run:  python3 quasi.py            # full numerical report
      python3 quasi.py --sweep    # the dials
"""
from __future__ import annotations
import argparse, math, sys
from dataclasses import dataclass, replace
import numpy as np

PHI = (1.0 + 5.0 ** 0.5) / 2.0
S2, S3, S5, S7 = 2 ** 0.5, 3 ** 0.5, 5 ** 0.5, 7 ** 0.5

# ---- measured machine facts (do not re-derive) --------------------------------
MAX_VOL_FLOW = 81.2       # mm3/s measured
WORK_VOL_FLOW = 68.8      # mm3/s working
ACCEL = 8000.0            # mm/s2  -- prints command M204 S8000
MAX_VEL = 800.0           # mm/s
SCV = 5.0                 # Klipper square_corner_velocity (stock)
NOZZLE = 0.8


@dataclass
class Q:
    size: float = 60.0
    margin: float = 1.5          # keep the curve off the coupon edge
    origin: float = 145.0        # 60mm coupon centred on a 350 bed
    layer_h: float = 0.40
    layers: int = 15
    strand_w: float = 0.50       # ABSOLUTE strand width (decoupled, as in crackle.py)
    fil_d: float = 1.75
    # slow harmonics -- these set the SHAPE and the coverage
    fx: tuple = (1.0, S2)
    ax: tuple = (1.0, 0.62)
    px: tuple = (0.00, 0.90)
    fy: tuple = (PHI, S5)
    ay: tuple = (1.0, 0.62)
    py: tuple = (1.70, 3.10)
    # quadrature carrier -- sets the SPEED FLOOR
    cf: float = 9.0 * S2         # ~12.728, irrational against every slow frequency
    ca: float = 0.10
    # THE DIAL
    T: float = 36.0              # t-span per layer -> path length -> crossings
    v_cmd: float = 150.0         # mm/s commanded
    # per-layer decorrelation
    rot_per_layer: float = math.radians(137.507764)   # golden angle
    ds: float = 0.20             # analysis resampling (mm)


# ---------------------------------------------------------------- the curve
def raw(q: Q, t):
    """Unscaled curve + first and second derivatives (analytic, not finite-differenced)."""
    x = np.zeros_like(t); y = np.zeros_like(t)
    dx = np.zeros_like(t); dy = np.zeros_like(t)
    ddx = np.zeros_like(t); ddy = np.zeros_like(t)
    for a, f, p in zip(q.ax, q.fx, q.px):
        x += a * np.sin(f * t + p); dx += a * f * np.cos(f * t + p); ddx -= a * f * f * np.sin(f * t + p)
    for a, f, p in zip(q.ay, q.fy, q.py):
        y += a * np.sin(f * t + p); dy += a * f * np.cos(f * t + p); ddy -= a * f * f * np.sin(f * t + p)
    w = q.cf; c = q.ca
    x += c * np.cos(w * t); dx -= c * w * np.sin(w * t); ddx -= c * w * w * np.cos(w * t)
    y += c * np.sin(w * t); dy += c * w * np.cos(w * t); ddy -= c * w * w * np.sin(w * t)
    return x, y, dx, dy, ddx, ddy


def fit(q: Q, t_total: float, n=400_000):
    """One isotropic scale + offset so the WHOLE print's bbox fills the square.
    Isotropic on purpose: an anisotropic scale turns the carrier circle into an ellipse and
    reintroduces a curvature maximum."""
    t = np.linspace(0.0, t_total, n)
    x, y, *_ = raw(q, t)
    ex, ey = x.max() - x.min(), y.max() - y.min()
    s = (q.size - 2 * q.margin) / max(ex, ey)
    cx = q.origin + q.size / 2 - s * (x.max() + x.min()) / 2
    cy = q.origin + q.size / 2 - s * (y.max() + y.min()) / 2
    return s, cx, cy, s * ex, s * ey


def curve_mm(q: Q, t, s, cx, cy, rot=0.0):
    x, y, dx, dy, ddx, ddy = raw(q, t)
    x = s * x; y = s * y; dx = s * dx; dy = s * dy; ddx = s * ddx; ddy = s * ddy
    if rot:
        c, sn = math.cos(rot), math.sin(rot)
        x, y = c * x - sn * y, sn * x + c * y
        dx, dy = c * dx - sn * dy, sn * dx + c * dy
        ddx, ddy = c * ddx - sn * ddy, sn * ddx + c * ddy
    return x + cx, y + cy, dx, dy, ddx, ddy


def resample(q: Q, t0, t1, s, cx, cy, rot=0.0, dense=300_000, ds=None):
    """Arc-length resample -> uniform-ds polyline + the t value at each point."""
    ds = ds if ds is not None else q.ds
    t = np.linspace(t0, t1, dense)
    x, y, *_ = curve_mm(q, t, s, cx, cy, rot)
    seg = np.hypot(np.diff(x), np.diff(y))
    cs = np.concatenate([[0.0], np.cumsum(seg)])
    L = cs[-1]
    su = np.arange(0.0, L, ds)
    P = np.column_stack([np.interp(su, cs, x), np.interp(su, cs, y)])
    tu = np.interp(su, cs, t)
    return P, su, tu, L


# ---------------------------------------------------------------- intersections
def self_intersections(P, skip=2):
    """Exact segment-pair intersections of a polyline, grid-bucketed.
    Returns arrays: ia, ib (segment indices), pts (xy), and the two arc parameters."""
    A = P[:-1]; B = P[1:]
    n = len(A)
    lo = np.minimum(A, B); hi = np.maximum(A, B)
    cell = float(max(np.max(hi - lo), 1e-6)) * 2.0
    gx0, gy0 = lo[:, 0].min(), lo[:, 1].min()
    buckets = {}
    ci0 = np.floor((lo[:, 0] - gx0) / cell).astype(int)
    ci1 = np.floor((hi[:, 0] - gx0) / cell).astype(int)
    cj0 = np.floor((lo[:, 1] - gy0) / cell).astype(int)
    cj1 = np.floor((hi[:, 1] - gy0) / cell).astype(int)
    for i in range(n):
        for ci in range(ci0[i], ci1[i] + 1):
            for cj in range(cj0[i], cj1[i] + 1):
                buckets.setdefault((ci, cj), []).append(i)
    pairs = set()
    for idxs in buckets.values():
        m = len(idxs)
        if m < 2:
            continue
        for a in range(m):
            for b in range(a + 1, m):
                i, j = idxs[a], idxs[b]
                if abs(i - j) < skip:
                    continue
                pairs.add((i, j) if i < j else (j, i))
    if not pairs:
        return (np.zeros(0, int), np.zeros(0, int), np.zeros((0, 2)), np.zeros(0), np.zeros(0))
    pr = np.array(sorted(pairs))
    i, j = pr[:, 0], pr[:, 1]
    p, r = A[i], B[i] - A[i]
    qq, ss = A[j], B[j] - A[j]
    den = r[:, 0] * ss[:, 1] - r[:, 1] * ss[:, 0]
    ok = np.abs(den) > 1e-12
    d = qq - p
    tt = np.where(ok, (d[:, 0] * ss[:, 1] - d[:, 1] * ss[:, 0]) / np.where(ok, den, 1), -1.0)
    uu = np.where(ok, (d[:, 0] * r[:, 1] - d[:, 1] * r[:, 0]) / np.where(ok, den, 1), -1.0)
    hit = ok & (tt >= 0) & (tt <= 1) & (uu >= 0) & (uu <= 1)
    i, j, tt, uu = i[hit], j[hit], tt[hit], uu[hit]
    pts = A[i] + tt[:, None] * (B[i] - A[i])
    return i, j, pts, tt, uu


def cross_pairs(P, Qp):
    """Intersections BETWEEN two polylines (layer n against layer n-1)."""
    A, B = P[:-1], P[1:]
    C, D = Qp[:-1], Qp[1:]
    cell = float(max(np.max(np.abs(B - A)), np.max(np.abs(D - C)), 1e-6)) * 2.0
    gx0 = min(A[:, 0].min(), C[:, 0].min()); gy0 = min(A[:, 1].min(), C[:, 1].min())

    def bucketize(U, V):
        lo = np.minimum(U, V); hi = np.maximum(U, V)
        b = {}
        ci0 = np.floor((lo[:, 0] - gx0) / cell).astype(int); ci1 = np.floor((hi[:, 0] - gx0) / cell).astype(int)
        cj0 = np.floor((lo[:, 1] - gy0) / cell).astype(int); cj1 = np.floor((hi[:, 1] - gy0) / cell).astype(int)
        for k in range(len(U)):
            for ci in range(ci0[k], ci1[k] + 1):
                for cj in range(cj0[k], cj1[k] + 1):
                    b.setdefault((ci, cj), []).append(k)
        return b
    b1, b2 = bucketize(A, B), bucketize(C, D)
    pairs = set()
    for key, ii in b1.items():
        jj = b2.get(key)
        if not jj:
            continue
        for i in ii:
            for j in jj:
                pairs.add((i, j))
    if not pairs:
        return np.zeros(0, int), np.zeros(0)
    pr = np.array(sorted(pairs)); i, j = pr[:, 0], pr[:, 1]
    p, r = A[i], B[i] - A[i]
    qq, ss = C[j], D[j] - C[j]
    den = r[:, 0] * ss[:, 1] - r[:, 1] * ss[:, 0]
    ok = np.abs(den) > 1e-12
    d = qq - p
    tt = np.where(ok, (d[:, 0] * ss[:, 1] - d[:, 1] * ss[:, 0]) / np.where(ok, den, 1), -1.0)
    uu = np.where(ok, (d[:, 0] * r[:, 1] - d[:, 1] * r[:, 0]) / np.where(ok, den, 1), -1.0)
    hit = ok & (tt >= 0) & (tt <= 1) & (uu >= 0) & (uu <= 1)
    return i[hit], tt[hit]


# ---------------------------------------------------------------- planner
def plan(P, v_cmd, accel=ACCEL, scv=SCV, vmax=MAX_VEL):
    """Klipper's look-ahead, reimplemented: junction-deviation + centripetal limit, then a
    forward/backward pass. Returns per-vertex velocity and per-segment distance run below 0.9*v_cmd."""
    seg = np.diff(P, axis=0)
    d = np.hypot(seg[:, 0], seg[:, 1])
    keep = d > 1e-9
    seg, d = seg[keep], d[keep]
    n = len(d)
    u = seg / d[:, None]
    vcap = min(v_cmd, vmax)
    dot = np.sum(u[:-1] * u[1:], axis=1)
    jct = np.clip(-dot, -0.999999, 0.999999)              # Klipper's junction_cos_theta
    sin_h = np.sqrt(0.5 * (1.0 - jct))
    cos_h = np.sqrt(np.maximum(0.5 * (1.0 + jct), 1e-15))
    R_jd = sin_h / np.maximum(1.0 - sin_h, 1e-15)
    tan_h = sin_h / cos_h
    jd = scv ** 2 * (math.sqrt(2.0) - 1.0) / accel
    v2_jd = R_jd * jd * accel
    v2_cp = 0.5 * np.minimum(d[:-1], d[1:]) * tan_h * accel
    vj = np.sqrt(np.minimum(np.minimum(v2_jd, v2_cp), vcap ** 2))
    v = np.empty(n + 1)
    v[0] = 0.0; v[-1] = 0.0
    v[1:-1] = np.minimum(vj, vcap)
    for i in range(n):                                     # forward (accel limit)
        v[i + 1] = min(v[i + 1], math.sqrt(v[i] ** 2 + 2 * accel * d[i]))
    for i in range(n - 1, -1, -1):                         # backward (decel limit)
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * accel * d[i]))
    # exact distance below threshold, per segment (trapezoid within the segment)
    thr = 0.9 * vcap
    ve, vx = v[:-1], v[1:]
    peak = np.minimum(np.sqrt(np.maximum((ve ** 2 + vx ** 2) / 2 + accel * d, 0.0)), vcap)
    d_acc = np.maximum((peak ** 2 - ve ** 2) / (2 * accel), 0.0)
    d_dec = np.maximum((peak ** 2 - vx ** 2) / (2 * accel), 0.0)
    d_cru = np.maximum(d - d_acc - d_dec, 0.0)
    lim = np.minimum(peak, thr)
    below_a = np.where(ve < thr, np.maximum(lim ** 2 - ve ** 2, 0.0) / (2 * accel), 0.0)
    below_d = np.where(vx < thr, np.maximum(lim ** 2 - vx ** 2, 0.0) / (2 * accel), 0.0)
    below_c = np.where(peak < thr, d_cru, 0.0)
    below = np.minimum(below_a + below_d + below_c, d)
    t_acc = (peak - ve) / accel; t_dec = (peak - vx) / accel
    t_cru = np.where(peak > 1e-9, d_cru / np.maximum(peak, 1e-9), 0.0)
    return v, d, below, float(np.sum(t_acc + t_dec + t_cru))


# ---------------------------------------------------------------- analysis
def hist_line(vals, edges):
    h, _ = np.histogram(vals, bins=edges)
    mx = max(h.max(), 1)
    out = []
    for k in range(len(h)):
        bar = "#" * int(round(40 * h[k] / mx))
        out.append(f"    [{edges[k]:5.2f},{edges[k+1]:5.2f})  {h[k]:6d} {bar}")
    return "\n".join(out)


def analyse(q: Q, verbose=True, layers_for_stack=None):
    R = {}
    t_total = q.T * q.layers
    s, cx, cy, ex, ey = fit(q, t_total)
    R["scale"] = s; R["bbox"] = (ex, ey)

    # ---- one layer -----------------------------------------------------------
    P, su, tu, L = resample(q, 0.0, q.T, s, cx, cy, rot=0.0)
    R["L"] = L
    i, j, xpts, tt, uu = self_intersections(P)
    N = len(i)
    R["N"] = N
    R["dens"] = N / (q.size ** 2)

    # arc positions of both branches of every crossing
    sa = su[i] + tt * q.ds
    sb = su[j] + uu * q.ds
    allpos = np.sort(np.concatenate([sa, sb]))
    members = np.diff(allpos)
    members = members[members > 1e-9]
    R["members"] = members

    # dt (and therefore dz) between the two branches of each crossing
    dt_cross = np.abs(tu[j] + uu * (tu[1] - tu[0]) - (tu[i] + tt * (tu[1] - tu[0])))
    dz_cross = q.layer_h * dt_cross / q.T
    R["dz_cross"] = dz_cross

    # ---- curvature / speed ---------------------------------------------------
    td = np.linspace(0.0, q.T, 200_000)
    x, y, dx, dy, ddx, ddy = curve_mm(q, td, s, cx, cy)
    sp = np.hypot(dx, dy)
    kap = np.abs(dx * ddy - dy * ddx) / np.maximum(sp ** 3, 1e-15)
    R["kappa"] = kap
    R["min_speed_ratio"] = float(sp.min() / sp.mean())
    R["v_curv"] = np.sqrt(ACCEL / np.maximum(kap, 1e-12))     # kinematic ceiling from curvature
    R["r_min"] = float(1.0 / kap.max())

    # ---- planner -------------------------------------------------------------
    v, d, below, tsec = plan(P, q.v_cmd)
    R["frac_below90"] = float(below.sum() / d.sum())
    R["time_layer"] = tsec
    R["v_mean"] = float(d.sum() / tsec)

    # ---- coverage ------------------------------------------------------------
    nb = 12
    edges = np.linspace(q.origin, q.origin + q.size, nb + 1)
    mid = (P[:-1] + P[1:]) / 2
    dseg = np.hypot(*(np.diff(P, axis=0).T))
    H, _, _ = np.histogram2d(mid[:, 0], mid[:, 1], bins=[edges, edges], weights=dseg)
    R["cov"] = H
    R["cov_cv"] = float(H.std() / H.mean())
    R["cov_empty"] = int((H < 0.25 * H.mean()).sum())
    # centre vs edge: inner 20x20 against the outer ring
    c0, c1 = 4, 8
    inner = H[c0:c1, c0:c1].sum() / ((c1 - c0) ** 2)
    outer = (H.sum() - H[c0:c1, c0:c1].sum()) / (nb * nb - (c1 - c0) ** 2)
    R["centre_edge_ratio"] = float(inner / outer)
    R["mean_height"] = L * q.strand_w * q.layer_h / (q.size ** 2)   # areal material balance

    # ---- flow ----------------------------------------------------------------
    R["q_at_vcmd"] = q.strand_w * q.layer_h * q.v_cmd
    R["v_flow_max"] = WORK_VOL_FLOW / (q.strand_w * q.layer_h)

    if layers_for_stack:
        R.update(multilayer(q, s, cx, cy, layers_for_stack))
    return R


def multilayer(q: Q, s, cx, cy, nlay):
    """Layer-to-layer: does the same XY crossing recur (welded vertical column), and how far does a
    strand fly unsupported over the layer below?"""
    polys, tuS = [], []
    for k in range(nlay):
        P, su, tu, L = resample(q, k * q.T, (k + 1) * q.T, s, cx, cy, rot=k * q.rot_per_layer)
        polys.append(P); tuS.append(su)
    allx = []
    for k, P in enumerate(polys):
        i, j, pts, tt, uu = self_intersections(P)
        allx.append(pts)
    # column risk: crossing in layer k with a crossing in layer k-1 within 0.6mm
    near = 0; tot = 0
    for k in range(1, nlay):
        a, b = allx[k], allx[k - 1]
        tot += len(a)
        if len(a) == 0 or len(b) == 0:
            continue
        cell = 0.6
        grid = {}
        for p in b:
            grid.setdefault((int(p[0] / cell), int(p[1] / cell)), []).append(p)
        for p in a:
            gi, gj = int(p[0] / cell), int(p[1] / cell)
            found = False
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for pb in grid.get((gi + di, gj + dj), ()):
                        if (p[0] - pb[0]) ** 2 + (p[1] - pb[1]) ** 2 < cell ** 2:
                            found = True; break
                    if found: break
                if found: break
            if found: near += 1
    # unsupported spans of layer k over layer k-1
    spans = []
    ncross_inter = []
    for k in range(1, nlay):
        i, tt = cross_pairs(polys[k], polys[k - 1])
        ncross_inter.append(len(i))
        pos = np.sort(q.ds * (i + tt))
        if len(pos) > 1:
            spans.append(np.diff(pos))
    spans = np.concatenate(spans) if spans else np.zeros(0)
    return {"column_frac": near / max(tot, 1), "spans": spans,
            "inter_cross": float(np.mean(ncross_inter)) if ncross_inter else 0.0}


# ---------------------------------------------------------------- report
def report(q: Q):
    print("=" * 78)
    print("QUASI-PERIODIC CONTINUOUS CRACKLE WEB — numerical analysis")
    print("=" * 78)
    print(f"coupon {q.size}mm  layers={q.layers}  layer_h={q.layer_h}  strand_w={q.strand_w}")
    print(f"x freqs {tuple(round(f,5) for f in q.fx)} amps {q.ax} | y freqs "
          f"{tuple(round(f,5) for f in q.fy)} amps {q.ay} | carrier {q.cf:.4f} amp {q.ca}")
    print(f"T (t-span per layer) = {q.T}   commanded feed = {q.v_cmd} mm/s\n")

    R = analyse(q, layers_for_stack=q.layers)
    print(f"realised bbox: {R['bbox'][0]:.2f} x {R['bbox'][1]:.2f} mm  (target {q.size-2*q.margin:.1f})")
    print(f"path length per layer: {R['L']:.1f} mm")

    print("\n1. SELF-INTERSECTIONS")
    print(f"   per layer: {R['N']}   ({R['dens']*100:.2f} per cm2)")
    print(f"   total over {q.layers} layers (intra-layer only): {R['N']*q.layers}")
    dz = R["dz_cross"]
    print(f"   dz between the two branches at a crossing (continuous-Z ramp):")
    print(f"     mean {dz.mean():.3f} mm  median {np.median(dz):.3f}  "
          f">=0.15mm: {100*np.mean(dz>=0.15):.1f}%  >=0.30mm: {100*np.mean(dz>=0.30):.1f}%")
    print(f"   -> genuine over/under junctions (dz>=0.15): {int(np.sum(dz>=0.15))}")
    print(f"   -> coplanar merges (dz<0.05): {int(np.sum(dz<0.05))}")
    print(f"   inter-layer crossings (layer n x layer n-1): {R.get('inter_cross',0):.0f} per layer pair")

    print("\n2. SPEED UNIFORMITY")
    kap = R["kappa"]
    print(f"   min radius of curvature {R['r_min']:.3f} mm; kappa max {kap.max():.2f} 1/mm")
    print(f"   min |r'| / mean |r'| = {R['min_speed_ratio']:.3f}  (0 = cusp)")
    for vc in (100.0, 150.0, 200.0, 300.0):
        qq = replace(q, v_cmd=vc)
        Pv, _, _, Lv = resample(qq, 0.0, qq.T, *fit(qq, qq.T * qq.layers)[:3])
        v, d, below, tsec = plan(Pv, vc)
        print(f"   v_cmd={vc:5.0f} mm/s : below 90% on {100*below.sum()/d.sum():5.2f}% of path length"
              f" | achieved mean {d.sum()/tsec:6.1f} mm/s | {tsec:5.1f} s/layer")
    print(f"   flow at v_cmd={q.v_cmd}: {R['q_at_vcmd']:.1f} mm3/s  "
          f"(working ceiling {WORK_VOL_FLOW} -> v_flow_max {R['v_flow_max']:.0f} mm/s)")

    print("\n3. MEMBER LENGTHS (between consecutive intersections along the path)")
    m = R["members"]
    print(f"   n={len(m)}  mean {m.mean():.3f}  median {np.median(m):.3f}  sd {m.std():.3f}  "
          f"min {m.min():.3f}  p05 {np.percentile(m,5):.3f}  p95 {np.percentile(m,95):.3f}  max {m.max():.2f}")
    print(f"   CV = {m.std()/m.mean():.2f}   (1.0 = exponential = Poisson crossings)")
    print(hist_line(m, np.linspace(0, np.percentile(m, 99), 13)))

    print("\n4. COVERAGE (12x12 = 5mm bins, path length per bin)")
    H = R["cov"]
    print(f"   CV across bins {R['cov_cv']:.3f}   bins under 25% of mean: {R['cov_empty']}/144")
    print(f"   centre(20x20) / edge density ratio: {R['centre_edge_ratio']:.3f}  (1.0 = flat)")
    print(f"   mean deposited height {R['mean_height']:.3f} mm vs {q.layer_h} layer step "
          f"-> areal coverage {100*R['mean_height']/q.layer_h:.0f}%")
    sc = H / H.mean()
    for r in range(11, -1, -1):
        print("   " + " ".join(f"{sc[c][r]:4.1f}" for c in range(12)))

    print("\n5. LAYER-TO-LAYER")
    print(f"   per layer: t advances by T (never repeats) + rotation {math.degrees(q.rot_per_layer):.2f} deg")
    print(f"   crossings landing within 0.6mm of a crossing in the layer below: "
          f"{100*R['column_frac']:.2f}%  (random expectation "
          f"{100*(1-math.exp(-R['N']*math.pi*0.36/q.size**2)):.2f}%)")

    print("\n6. PRINTABILITY WITHOUT PILLARS")
    sp = R["spans"]
    if len(sp):
        print(f"   unsupported span between contacts with the layer below:")
        print(f"     mean {sp.mean():.2f} mm  median {np.median(sp):.2f}  p95 {np.percentile(sp,95):.2f}  "
              f"p99 {np.percentile(sp,99):.2f}  max {sp.max():.2f}")
        print(f"     spans > 5mm: {100*np.mean(sp>5):.2f}%   > 10mm: {100*np.mean(sp>10):.3f}%")
    fil = R["L"] * q.layers * q.strand_w * q.layer_h / (math.pi * (q.fil_d / 2) ** 2)
    print(f"   filament {fil:.0f} mm = {fil*math.pi*(q.fil_d/2)**2*1.24/1000:.2f} g")
    print(f"   Z rise per layer {q.layer_h} mm, continuous -> clearance over own bead >= 0 everywhere")
    # move count with chord-error-adaptive segmentation
    for eps in (0.01, 0.02):
        kk = np.maximum(kap, 1e-9)
        dsad = np.clip(np.sqrt(8 * eps / kk), 0.08, 1.0)
        td = np.linspace(0, q.T, len(kk))
        x, y, dx, dy, *_ = curve_mm(q, td, R["scale"], q.origin, q.origin)
        spd = np.hypot(dx, dy)
        nmoves = np.trapezoid(spd / dsad, td)
        print(f"   moves/layer at chord error {eps}mm: {nmoves:.0f}  "
              f"({nmoves/max(R['time_layer'],1e-9):.0f} moves/s at v_cmd={q.v_cmd})")
    return R


def sweep(q: Q):
    print("\n" + "=" * 78)
    print("DIAL 1 — T (t-span per layer). Everything else fixed.")
    print("=" * 78)
    print(f"{'T':>6} {'L mm':>8} {'cross':>7} {'/cm2':>6} {'memb mean':>10} {'memb p05':>9} "
          f"{'<90% path':>10} {'cov CV':>7} {'g total':>8}")
    for T in (12, 18, 24, 30, 36, 45, 60, 80):
        qq = replace(q, T=float(T))
        R = analyse(qq)
        m = R["members"]
        g = R["L"] * qq.layers * qq.strand_w * qq.layer_h * 1.24 / 1000
        print(f"{T:>6} {R['L']:8.0f} {R['N']:7d} {R['dens']*100:6.2f} {m.mean():10.3f} "
              f"{np.percentile(m,5):9.3f} {100*R['frac_below90']:9.2f}% {R['cov_cv']:7.3f} {g:8.2f}")

    print("\n" + "=" * 78)
    print("DIAL 2 — carrier amplitude ca (speed floor vs crossing geometry). T fixed.")
    print("=" * 78)
    print(f"{'ca':>6} {'L mm':>8} {'cross':>7} {'minv/mean':>10} {'r_min mm':>9} "
          f"{'<90% path':>10} {'dz>=.15':>8} {'memb mean':>10}")
    for ca in (0.0, 0.02, 0.05, 0.10, 0.16, 0.25, 0.40):
        qq = replace(q, ca=float(ca))
        R = analyse(qq)
        print(f"{ca:>6.2f} {R['L']:8.0f} {R['N']:7d} {R['min_speed_ratio']:10.3f} {R['r_min']:9.3f} "
              f"{100*R['frac_below90']:9.2f}% {100*np.mean(R['dz_cross']>=0.15):7.1f}% {R['members'].mean():10.3f}")

    print("\n" + "=" * 78)
    print("DIAL 3 — carrier frequency cf at fixed carrier amplitude*frequency product")
    print("=" * 78)
    print(f"{'cf':>8} {'ca':>6} {'L mm':>8} {'cross':>7} {'r_min':>8} {'<90%':>8} {'memb mean':>10}")
    for cf in (4 * S2, 6 * S2, 9 * S2, 14 * S2, 20 * S2):
        ca = (0.10 * 9 * S2) / cf
        qq = replace(q, cf=cf, ca=ca)
        R = analyse(qq)
        print(f"{cf:8.3f} {ca:6.3f} {R['L']:8.0f} {R['N']:7d} {R['r_min']:8.3f} "
              f"{100*R['frac_below90']:7.2f}% {R['members'].mean():10.3f}")

    print("\n" + "=" * 78)
    print("CONTROL — the same analysis on a flat-Z LATTICE for comparison (4x4 star order)")
    print("=" * 78)
    pts = [(145 + 8 + i * 14.667, 145 + 8 + j * 14.667) for j in range(4) for i in range(4)]
    order = []
    k = len(pts); cxx = sum(p[0] for p in pts) / k; cyy = sum(p[1] for p in pts) / k
    ang = sorted(range(k), key=lambda i: math.atan2(pts[i][1] - cyy, pts[i][0] - cxx))
    step = 7
    cur = 0
    for _ in range(k):
        order.append(ang[cur]); cur = (cur + step) % k
    lat = np.array([pts[i] for i in order])
    v, d, below, tsec = plan(lat, q.v_cmd)
    print(f"   lattice path length {d.sum():.0f} mm, {len(lat)-1} strands")
    print(f"   below 90% of {q.v_cmd} mm/s on {100*below.sum()/d.sum():.1f}% of path length")
    print(f"   achieved mean speed {d.sum()/tsec:.1f} mm/s  ({100*d.sum()/tsec/q.v_cmd:.0f}% of commanded)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--T", type=float, default=None)
    ap.add_argument("--ca", type=float, default=None)
    ap.add_argument("--v", type=float, default=None)
    a = ap.parse_args()
    q = Q()
    if a.T: q = replace(q, T=a.T)
    if a.ca is not None: q = replace(q, ca=a.ca)
    if a.v: q = replace(q, v_cmd=a.v)
    report(q)
    if a.sweep:
        sweep(q)
