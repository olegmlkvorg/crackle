#!/usr/bin/env python3
"""SPIRA-1 — crackle coupon as ONE continuous self-crossing curve per layer. No pillars.

FAMILY (per layer)
    r(t) = r0 + b t + A sin(m t + phi0)          b = s / 2pi   (s = turn spacing, mm)
    x(t) = cx + rho(th) r(t) cos(th)             th = t + alpha
    y(t) = cy + rho(th) r(t) sin(th)
    rho(th) = (|cos th|^q + |sin th|^q)^(-1/q)   superellipse warp; q=2 circle, q=4 fills the square

CROSSINGS ARE CLOSED FORM.  Turn k and turn k+j meet at polar angle th where
    r(th + 2pi(k+j)) - r(th + 2pi k) = 2 pi b j + 2A cos(...) sin(pi m j)
so that pair crosses iff   2A |sin(pi m j)| > 2 pi b j , giving 2m(N-j) crossings.
    X = sum over j of  [ A |sin(pi m j)| > pi b j ] * 2m(N-j)
  * m INTEGER  -> sin(pi m j) = 0 for all j -> ZERO crossings, for any A. (Verified.)
  * m HALF-INTEGER -> |sin| = 1 for odd j, 0 for even j: the cleanest dial.
        pi b < A < 3 pi b  ->  X = 2m(N-1) exactly.  m is the dial, A is the on/off threshold.

Run:  python3 spiralcoupon.py            # numbers + out/spira1_*.gcode
"""
from __future__ import annotations
import math, os, sys
import numpy as np

TAU = 2 * math.pi

# ------------------------------------------------------------------ defaults
DEF = dict(
    size=60.0, origin=40.0,          # coupon footprint / offset onto a 350x350 bed
    r0=7.0, r_max=28.0, s=2.0,       # inner radius, outer radius, turn spacing (mm)
    A=2.2, m=8.5, q=4.0,             # modulation amplitude, angular frequency, square-fill warp
    layers=15, layer_h=0.40,
    strand_w=0.5, nozzle_d=0.8, filament_d=1.75,
    feed=60.0,                       # mm/s commanded  (see speed-uniformity table)
    temp=230, bed=60, fan=0,
    tol=0.008, seg_max=0.6, seg_min=0.08,
)

def rho(th, q):
    if q == 2.0:
        return np.ones_like(th)
    return (np.abs(np.cos(th)) ** q + np.abs(np.sin(th)) ** q) ** (-1.0 / q)

def crossings_closed_form(P):
    """Exact count, no sampling."""
    b = P['s'] / TAU
    N = (P['r_max'] - P['r0']) / P['s']
    tot, terms = 0.0, []
    for j in range(1, int(N) + 1):
        if P['A'] * abs(math.sin(math.pi * P['m'] * j)) > math.pi * b * j and N - j > 0:
            c = 2 * P['m'] * (N - j)
            tot += c; terms.append((j, round(c)))
    return round(tot), terms

def spiral_layer(P, phi0=0.0, alpha=0.0, r0=None, reverse=False, r_max=None):
    """THE GENERATOR.  Returns (x, y) of one layer's continuous path, adaptively segmented so the
    chord sagitta stays under P['tol'] (fine where the modulation turns, coarse on the straights)."""
    r0 = P['r0'] if r0 is None else r0
    r_max = P['r_max'] if r_max is None else r_max
    b = P['s'] / TAU
    turns = (r_max - r0) / P['s']
    T = TAU * turns
    n = max(4000, int(1400 * turns))
    t = np.linspace(0.0, T, n)
    r = r0 + b * t + P['A'] * np.sin(P['m'] * t + phi0)
    th = t + alpha
    R = rho(th, P['q'])
    cx = cy = P['origin'] + P['size'] / 2.0
    x = cx + R * r * np.cos(th)
    y = cy + R * r * np.sin(th)
    # curvature -> adaptive step
    dx, dy = np.gradient(x), np.gradient(y)
    ddx, ddy = np.gradient(dx), np.gradient(dy)
    kap = np.abs(dx * ddy - dy * ddx) / np.maximum((dx * dx + dy * dy) ** 1.5, 1e-12)
    step = np.clip(np.sqrt(8.0 * P['tol'] / np.maximum(kap, 1e-9)), P['seg_min'], P['seg_max'])
    seg = np.hypot(np.diff(x), np.diff(y))
    keep, acc, budget = [0], 0.0, step[0]
    for i in range(1, n):
        acc += seg[i - 1]; budget = min(budget, step[i])
        if acc >= budget:
            keep.append(i); acc = 0.0; budget = step[i]
    if keep[-1] != n - 1:
        keep.append(n - 1)
    k = np.array(keep)
    x, y = x[k], y[k]
    return (x[::-1], y[::-1]) if reverse else (x, y)

def layer_plan(P, i):
    """Per-layer variation.
      phi0  walks by the golden angle  -> crossing ANGLES never repeat, so no welded columns.
      r0    alternates by half a turn spacing (r_max shifts with it, keeping turns constant at
            N+0.5 so every layer's outer end lands at the same polar angle) -> odd layers' turns
            sit in even layers' gaps, which is what creates inter-layer contacts.
      direction alternates -> layer i ends at the rim, layer i+1 starts at the rim: the whole
            15-layer web is ONE extrusion with ~1mm handovers instead of 15 travel moves.
      NOTE: do NOT also rotate by alpha=pi. For an Archimedean spiral a rotation by alpha IS a
      radial shift of -alpha*s/2pi, so alpha=pi exactly cancels the +s/2 offset and the layers
      re-align into columns (measured: stacking 0.000 -> 0.237)."""
    GOLD = math.pi * (3 - math.sqrt(5))
    odd = i % 2
    d = P['s'] / 2 if odd else 0.0
    return dict(phi0=i * GOLD, alpha=0.0, r0=P['r0'] + d, r_max=P['r_max'] + d, reverse=bool(odd))

def count_crossings_numeric(x, y, cell=1.5, skip=3):
    """Independent check on the closed form: brute-force segment-pair intersection."""
    from collections import defaultdict
    n = len(x) - 1
    grid = defaultdict(list)
    for i in range(n):
        a, bq = sorted((x[i], x[i + 1])); c, d = sorted((y[i], y[i + 1]))
        for gx in range(int(a // cell), int(bq // cell) + 1):
            for gy in range(int(c // cell), int(d // cell) + 1):
                grid[(gx, gy)].append(i)
    seen, cnt = set(), 0
    for bucket in grid.values():
        for ai in range(len(bucket)):
            for bi in range(ai + 1, len(bucket)):
                i, j = sorted((bucket[ai], bucket[bi]))
                if j - i < skip or (i, j) in seen:
                    continue
                seen.add((i, j))
                p1, p2, p3, p4 = (x[i], y[i]), (x[i+1], y[i+1]), (x[j], y[j]), (x[j+1], y[j+1])
                d1 = (p2[0]-p1[0], p2[1]-p1[1]); d2 = (p4[0]-p3[0], p4[1]-p3[1])
                den = d1[0]*d2[1] - d1[1]*d2[0]
                if abs(den) < 1e-14:
                    continue
                ex, ey = p3[0]-p1[0], p3[1]-p1[1]
                u = (ex*d2[1] - ey*d2[0]) / den; v = (ex*d1[1] - ey*d1[0]) / den
                if 0 <= u <= 1 and 0 <= v <= 1:
                    cnt += 1
    return cnt

# ------------------------------------------------------------------- gcode
def emit(P):
    max_w = 1.5 * P['nozzle_d']
    if P['strand_w'] > max_w:
        raise SystemExit(f"strand_w {P['strand_w']} > 1.5*nozzle ({max_w}) — bead lands TALL and "
                         f"the nozzle ploughs the part off (2026-07-25).")
    area = math.pi * (P['filament_d'] / 2) ** 2
    e_per_mm = (P['strand_w'] * P['layer_h']) / area
    f = round(P['feed'] * 60)
    X, terms = crossings_closed_form(P)
    L, e = [], 0.0
    w = L.append
    w(f"; SPIRA-1 continuous modulated-spiral crackle coupon — NO PILLARS, NO TRAVELS in the web")
    w(f"; r = {P['r0']} + {P['s']/TAU:.5f} t + {P['A']} sin({P['m']} t + phi)   q={P['q']}")
    w(f"; crossings/layer = {X}  (closed form, terms j->count: {terms})")
    w(f"; {P['layers']} layers x {P['layer_h']}mm, strand {P['strand_w']}mm, F{P['feed']}mm/s, "
      f"T{P['temp']} fan{P['fan']}")
    w("; RETRACTION / COMBING / Z-HOP ABSENT ON PURPOSE.")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {2 + P['layers']}"); w("; HEADER_BLOCK_END")
    w(f"M140 S{P['bed']}"); w(f"M104 S{P['temp']}"); w("G90"); w("G28")
    w(f"M190 S{P['bed']}"); w(f"M109 S{P['temp']}"); w("M204 S8000")
    w("M107" if not P['fan'] else f"M106 S{P['fan']}")
    w("M83"); w("G1 Z0.3 F600")
    w("G1 X10 Y10 F9000"); w("G1 X90 Y10 E9 F1200")
    w("G92 E0"); w("M82"); w("G92 E0")

    z = 0.0
    o, S = P['origin'], P['size']
    # --- anchor base: frame + ribs (adhesion + a coupon you can peel off and stand on) ---
    for bl in range(2):
        z = round(z + P['layer_h'], 3)
        w(f"; base layer {bl+1}")
        w(f"G0 Z{z:.3f}")
        x0, y0, x1, y1 = o + 3, o + 3, o + S - 3, o + S - 3
        pts = [(x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        w(f"G0 F9000 X{x0:.3f} Y{y0:.3f}")
        px, py = x0, y0
        for tx, ty in pts:
            e += math.dist((px, py), (tx, ty)) * (0.9 * P['layer_h']) / area
            w(f"G1 F3000 X{tx:.3f} Y{ty:.3f} E{e:.5f}"); px, py = tx, ty
        for gy in np.linspace(y0 + 4, y1 - 4, 7):
            w(f"G0 F9000 X{x0:.3f} Y{gy:.3f}")
            e += (x1 - x0) * (0.9 * P['layer_h']) / area
            w(f"G1 F3000 X{x1:.3f} Y{gy:.3f} E{e:.5f}")
        for gx in np.linspace(x0 + 4, x1 - 4, 7):
            w(f"G0 F9000 X{gx:.3f} Y{y0:.3f}")
            e += (y1 - y0) * (0.9 * P['layer_h']) / area
            w(f"G1 F3000 X{gx:.3f} Y{y1:.3f} E{e:.5f}")

    # --- web: one continuous curve per layer ---
    path_mm = 0.0
    lx = ly = None
    for i in range(P['layers']):
        z = round(z + P['layer_h'], 3)
        lp = layer_plan(P, i)
        xs, ys = spiral_layer(P, lp['phi0'], lp['alpha'], lp['r0'], lp['reverse'], lp['r_max'])
        w(f"; web layer {i+1} — ONE curve, {len(xs)-1} segments, {X} self-crossings")
        w(f"G0 Z{z:.3f}")
        if lx is None:
            w(f"G0 F9000 X{xs[0]:.3f} Y{ys[0]:.3f}")
        else:
            d = math.hypot(xs[0] - lx, ys[0] - ly)
            if d > 0.05:                      # handover: EXTRUDE it (a known chord, not an ooze)
                e += d * e_per_mm
                w(f"G1 F{f} X{xs[0]:.3f} Y{ys[0]:.3f} E{e:.5f}")
                path_mm += d
        px, py = xs[0], ys[0]
        for j in range(1, len(xs)):
            d = math.hypot(xs[j] - px, ys[j] - py)
            e += d * e_per_mm; path_mm += d
            w(f"G1 F{f} X{xs[j]:.3f} Y{ys[j]:.3f} E{e:.5f}")
            px, py = xs[j], ys[j]
        lx, ly = px, py
    w("M107"); w("M104 S0"); w("M140 S0"); w(f"G1 Z{z+40:.1f} F900"); w("G0 X10 Y340 F9000")
    return "\n".join(L) + "\n", dict(crossings=X, terms=terms, path_mm=path_mm,
                                     grams=e * area * 1.24 / 1000, lines=len(L))


if __name__ == "__main__":
    P = dict(DEF)
    X, terms = crossings_closed_form(P)
    xs, ys = spiral_layer(P)
    num = count_crossings_numeric(xs, ys)
    print(f"SPIRA-1  r0={P['r0']} r_max={P['r_max']} s={P['s']} A={P['A']} m={P['m']} q={P['q']}")
    print(f"  turns {(P['r_max']-P['r0'])/P['s']:.1f}   segments/layer {len(xs)-1}")
    print(f"  crossings/layer: closed form {X}  (terms {terms})   numeric check {num}")
    print(f"  A/(pi b) = {P['A']/(math.pi*P['s']/TAU):.2f}   "
          f"(>1 => crossings, <3 => only the j=1 family)")
    g, st = emit(P)
    os.makedirs("out", exist_ok=True)
    fn = f"out/spira1_x{st['crossings']}_m{P['m']}_A{P['A']}_T{P['temp']}.gcode"
    open(fn, "w").write(g)
    print(f"  path {st['path_mm']:.0f} mm total web, {st['grams']:.1f} g, {st['lines']} lines")
    print(f"  wrote {fn}")
