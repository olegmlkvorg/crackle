#!/usr/bin/env python3
"""
wander.py -- ONE continuous curve per crackle layer. No pillars, no endpoints,
no direction reversals.

FAMILY:  BLTW-C, a Band-Limited Tangent Walk with Coverage feedback.
The curve is defined in ARC LENGTH, so it is unit-speed by construction:

    dtheta/ds = kappa(s)                dx/ds = cos theta       dy/ds = sin theta
    kappa(s)  = clip( (1-w_wall)*[(1-w_cov)*kappa_rand(s) + w_cov*kappa_cov]
                      + w_wall*kappa_wall ,   +/- kappa_max )

    kappa_rand(s) = A * sum_{k=1..K} sin(2*pi*f_k*s + phi_k)
                    f_k log-spaced in [f_lo, f_hi], phi_k ~ U(0,2pi), A set by kappa_rms
    kappa_cov     = Kp * wrap(theta_free - theta), theta_free = least-visited heading
                    in a +/-75 deg cone (probes a visited-density grid at 3.5 and 8 mm)
    kappa_wall    = kappa_turn * sat(theta_inward - theta), authority near the edge

Because |kappa| <= kappa_max EVERYWHERE, the centripetal speed ceiling
sqrt(a/kappa_max) is a constant along the whole path: 200 mm/s at a = 8000 mm/s2
for kappa_max = 0.20 rad/mm (r_min = 5 mm). There is no point on the curve where
the planner must slow down. That is the entire reason to leave the lattice.

A rounded-rectangle PERIMETER LOOP (corner radius = r_min, so still no slowdown)
is prepended to each layer and joined tangentially: it fills the rim the
bounded-curvature wander physically cannot reach, and gives the coupon an edge.
"""
from __future__ import annotations
import math
import numpy as np
from dataclasses import dataclass, replace

GOLDEN = math.pi * (3 - math.sqrt(5))          # 137.508 deg


@dataclass
class W:
    # --- geometry -------------------------------------------------------
    size: float = 60.0
    L: float = 2400.0          # interior path length per layer  <-- THE CROSSING DIAL
    kappa_max: float = 0.20    # rad/mm. r_min = 5 mm. v_ceiling = sqrt(a/kappa_max)
    kappa_rms: float = 0.11    # rad/mm rms of the band-limited curvature noise
    f_lo: float = 1 / 40.0     # curvature band, cycles/mm  (40 mm .. 8 mm wavelength)
    f_hi: float = 1 / 8.0
    K: int = 12                # tones (incommensurate -> aperiodic)
    w_cov: float = 0.9         # coverage-feedback authority, 0 = pure noise
    cell: float = 2.5
    probe: tuple = (3.5, 8.0)
    cone: float = math.radians(75)
    nfan: int = 11
    ctrl_every: float = 0.4
    margin: float = 9.0        # wall band
    inset: float = 2.5         # walk square is [inset, size-inset]
    kappa_turn: float = 0.20
    kappa_bias: float = 0.0      # persistent-turn amplitude -> tight self-loops -> HOT welds
    bias_len: float = 120.0      # mm of path between bias sign flips
    ring: bool = True          # perimeter loop
    ring_inset: float = 2.0
    # --- per layer ------------------------------------------------------
    layers: int = 15
    layer_h: float = 0.40
    seed: int = 0
    h: float = 0.05            # integration step, mm


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# --------------------------------------------------------------- the walk
def wander(p: W, seed: int):
    rng = np.random.default_rng(seed)
    f = np.exp(np.linspace(math.log(p.f_lo), math.log(p.f_hi), p.K))
    f *= 1.0 + 0.07 * rng.standard_normal(p.K)
    phi = rng.uniform(0, 2 * math.pi, p.K)
    amp = np.full(p.K, 1.0)
    amp /= math.sqrt((amp ** 2).sum() / 2.0)
    amp *= p.kappa_rms
    w2 = 2 * math.pi * f

    S = p.size - 2 * p.inset
    c, m = p.cell, p.margin
    nb = int(math.ceil(S / c)); OFF = 6
    dens = np.zeros((nb + 2 * OFF, nb + 2 * OFF))
    for i in range(dens.shape[0]):
        for j in range(dens.shape[1]):
            d = max(max(OFF - i, i - (OFF + nb - 1), 0), max(OFF - j, j - (OFF + nb - 1), 0))
            if d:
                dens[i, j] = 200.0 * d
    shp0, shp1 = dens.shape
    fan = np.linspace(-p.cone, p.cone, p.nfan)
    D0, D1 = p.probe
    Kp = 1.5 * p.kappa_max

    n = int(p.L / p.h) + 1
    x = np.empty(n); y = np.empty(n); th = np.empty(n); kap = np.empty(n)
    xi, yi = S * 0.5, S * 0.5
    ti = rng.uniform(0, 2 * math.pi)
    every = max(1, int(round(p.ctrl_every / p.h)))
    kc = 0.0

    fb = 1.0 / max(1e-9, p.bias_len)
    pb = rng.uniform(0, 2 * math.pi)
    for i in range(n):
        s_ = i * p.h
        kr = float(np.dot(amp, np.sin(w2 * s_ + phi)))
        if p.kappa_bias:
            kr += p.kappa_bias * math.copysign(1.0, math.sin(2 * math.pi * fb * s_ + pb))
        if i % every == 0:
            best = 1e18; bang = ti
            for da in fan:
                a = ti + da; ca, sa = math.cos(a), math.sin(a); sc = 0.0
                for r in (D0, D1):
                    gi = int((xi + r * ca) / c) + OFF; gj = int((yi + r * sa) / c) + OFF
                    sc += dens[gi, gj] if (0 <= gi < shp0 and 0 <= gj < shp1) else 5000.0
                sc += abs(da) * 0.30
                if sc < best:
                    best, bang = sc, a
            kc = max(-p.kappa_max, min(p.kappa_max, Kp * _wrap(bang - ti)))

        vx = max(0.0, (m - xi) / m) - max(0.0, (m - (S - xi)) / m)
        vy = max(0.0, (m - yi) / m) - max(0.0, (m - (S - yi)) / m)
        mag = math.hypot(vx, vy)
        if mag > 1e-12:
            ww = min(1.0, mag) ** 0.5
            d = _wrap(math.atan2(vy, vx) - ti)
            kw = p.kappa_turn * (math.sin(d) if abs(d) <= math.pi / 2 else (1.0 if d >= 0 else -1.0))
        else:
            ww, kw = 0.0, 0.0

        k = (1.0 - ww) * ((1.0 - p.w_cov) * kr + p.w_cov * kc) + ww * kw
        k = max(-p.kappa_max, min(p.kappa_max, k))
        x[i] = xi; y[i] = yi; th[i] = ti; kap[i] = k
        gi = int(xi / c) + OFF; gj = int(yi / c) + OFF
        if 0 <= gi < shp0 and 0 <= gj < shp1 and dens[gi, gj] < 100.0:
            dens[gi, gj] += p.h
        tm = ti + 0.5 * p.h * k
        xi += p.h * math.cos(tm); yi += p.h * math.sin(tm); ti += p.h * k
    return x + p.inset, y + p.inset, th, kap


def ring_path(p: W):
    """Rounded rectangle, corner radius = 1/kappa_max: no slowdown at the corners.
    Sampled at p.h so it splices into the wander with uniform spacing."""
    r = 1.0 / p.kappa_max
    a, b = p.ring_inset, p.size - p.ring_inset
    C = [(b - r, a + r, -math.pi / 2),   # bottom-right
         (b - r, b - r, 0.0),            # top-right
         (a + r, b - r, math.pi / 2),    # top-left
         (a + r, a + r, math.pi)]        # bottom-left
    straight = (b - a) - 2 * r
    ns = max(2, int(round(straight / p.h)))
    na = max(2, int(round((math.pi / 2 * r) / p.h)))
    xs, ys, ks = [], [], []
    cur = np.array([a + r, a])
    for cx, cy, a0 in C:
        d = np.array([math.cos(a0 + math.pi / 2), math.sin(a0 + math.pi / 2)])
        for t in np.linspace(0, 1, ns, endpoint=False):
            q = cur + d * straight * t
            xs.append(q[0]); ys.append(q[1]); ks.append(0.0)
        for t in np.linspace(0, 1, na, endpoint=False):
            ang = a0 + t * math.pi / 2
            xs.append(cx + r * math.cos(ang)); ys.append(cy + r * math.sin(ang))
            ks.append(p.kappa_max)
        cur = np.array([cx + r * math.cos(a0 + math.pi / 2),
                        cy + r * math.sin(a0 + math.pi / 2)])
    return np.array(xs), np.array(ys), np.array(ks)


def layer(p: W, i: int):
    """Layer i: a fully re-phased wander (new phases f_k, phi_k, new start pose),
    optionally preceded by the ring. Returns x, y, kappa, and the index where the
    wander starts.

    NOTE: the pillar design rotated the visit order per layer. A square-filling
    continuous curve cannot be rotated inside its own square -- a 55 mm square
    turned 45 deg spans 78 mm. Re-phasing is the decorrelator here; Q5 below
    measures that it works as well as rotation did.
    """
    x, y, th, k = wander(p, p.seed + 7919 * i)
    if not p.ring:
        return x, y, k, 0
    rx, ry, rk = ring_path(p)
    # join tangentially: the ring ends at its start; walk from there to the
    # wander's first point along a bounded-curvature arc-ish lead-in
    j = _lead_in(np.array([rx[-1], ry[-1]]), np.array([rx[-1] - rx[-2], ry[-1] - ry[-2]]),
                 np.array([x[0], y[0]]), np.array([x[1] - x[0], y[1] - y[0]]), p)
    X = np.concatenate([rx, j[:, 0], x]); Y = np.concatenate([ry, j[:, 1], y])
    Kp = np.concatenate([rk, np.full(len(j), p.kappa_max), k])
    return X, Y, Kp, len(rx) + len(j)


def _lead_in(p0, t0, p1, t1, p: W, n=4000):
    """Cubic Hermite from p0 (heading t0) to p1 (heading t1), tangent-continuous
    at both ends, then resampled to uniform p.h spacing."""
    t0 = t0 / np.linalg.norm(t0); t1 = t1 / np.linalg.norm(t1)
    d = np.linalg.norm(p1 - p0)
    scale = max(d * 1.6, 3.0 / p.kappa_max)
    t = np.linspace(0, 1, n)[:, None]
    h00 = 2 * t**3 - 3 * t**2 + 1; h10 = t**3 - 2 * t**2 + t
    h01 = -2 * t**3 + 3 * t**2;    h11 = t**3 - t**2
    C = h00 * p0 + h10 * scale * t0 + h01 * p1 + h11 * scale * t1
    return uniform(C[:, 0], C[:, 1], p.h)[1:-1]


def uniform(x, y, h):
    """Resample a polyline to constant arc-length spacing h. Nx2 array out."""
    d = np.hypot(np.diff(x), np.diff(y))
    s = np.concatenate([[0.0], np.cumsum(d)])
    if s[-1] < h:
        return np.column_stack([x, y])
    t = np.arange(0.0, s[-1], h)
    return np.column_stack([np.interp(t, s, x), np.interp(t, s, y)])


# --------------------------------------------------------------- gcode
def resample(x, y, kap, h, dtheta_max=0.05, ds_min=0.20, ds_max=1.50):
    """Adaptive vertex spacing: hold the per-vertex turn angle under dtheta_max
    so Klipper's junction-deviation limit stays ABOVE the commanded feedrate."""
    n = len(x); idx = [0]; i = 0
    while i < n - 1:
        k = abs(kap[i]) + 1e-9
        step = min(ds_max, max(ds_min, dtheta_max / k))
        i = min(n - 1, i + max(1, int(round(step / h))))
        idx.append(i)
    idx = np.array(sorted(set(idx)))
    return x[idx], y[idx], idx


def emit(p: W, strand_d=0.5, ring_w=0.9, temp=230, bed=60, feed=200.0,
         ring_feed=150.0, fil_d=1.75, z0=0.4, scv=20.0, accel=8000.0,
         origin=(40.0, 40.0), home=True):
    """gcode for the whole coupon. Web extrusion is per mm of PATH, so a
    feedrate clamp changes the time, never the deposited geometry."""
    A_web = math.pi * strand_d ** 2 / 4
    A_ring = ring_w * p.layer_h
    fa = math.pi * fil_d ** 2 / 4
    g = ["; BLTW-C crackle coupon -- one continuous curve per layer, no pillars",
         "; kappa_max %.3f rad/mm -> r_min %.2f mm -> v_ceiling %.0f mm/s at a=%.0f"
         % (p.kappa_max, 1 / p.kappa_max, math.sqrt(accel / p.kappa_max), accel),
         "G21", "G90", "M83"] + (["G28"] if home else []) + [
         "M104 S%d" % temp, "M140 S%d" % bed,
         "M190 S%d" % bed, "M109 S%d" % temp, "M106 S0",
         "M204 S%d" % accel, "SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=%d" % scv]
    E = 0.0
    for i in range(p.layers):
        X, Y, K, j0 = layer(p, i)
        Xr, Yr, idx = resample(X, Y, K, p.h)
        z = z0 + i * p.layer_h
        g.append("; layer %d  z=%.2f  vertices=%d" % (i + 1, z, len(Xr)))
        g.append("G0 Z%.3f" % z)
        g.append("G0 X%.3f Y%.3f F%d" % (Xr[0] + origin[0], Yr[0] + origin[1], int(feed * 60)))
        # ring vertices get the wider STACKING bead; the web gets the thin free strand
        sr = np.hypot(np.diff(Xr), np.diff(Yr))
        is_ring = idx < j0
        for n in range(1, len(Xr)):
            ring_seg = bool(p.ring and is_ring[n])
            # LAYER 1 lands on the BED, so it must be a squished bead, not a free
            # strand: a 0.5 mm commanded width from a 0.8 nozzle lands 0.25 mm tall
            # against a 0.4 mm Z step and never touches. Layers 2+ print in air,
            # where cross-section is set by E/mm alone and 0.5 mm round is correct.
            A = A_ring if (ring_seg or i == 0) else A_web
            f = ring_feed if (ring_seg or i == 0) else feed
            e = sr[n - 1] * A / fa
            E += e
            g.append("G1 X%.3f Y%.3f E%.5f F%d"
                     % (Xr[n] + origin[0], Yr[n] + origin[1], e, int(f * 60)))
    g += ["M104 S0", "M140 S0", "G0 Z%.2f" % (z0 + p.layers * p.layer_h + 20)]
    return "\n".join(g), E
