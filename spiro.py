"""
spirogen.py — ONE CONTINUOUS TROCHOID per layer. No pillars, no direction reversals,
no travel moves inside a layer.

    z(t) = A e^{it} + B e^{i m t}      m = M/N rational, closed on t in [0, 2*pi*N]
    A = rmax/(1+beta), B = beta*A

Two separate speed constraints, both derived, both enforced here:

  PHYSICS      the toolhead must produce v^2/rho of centripetal acceleration, so
               rho_min >= v^2 / a   is required for the curve to run at commanded speed.
               ( v=200 mm/s, a=8000 mm/s^2  ->  rho_min >= 5.00 mm )

  PLANNER      Klipper never models centripetal accel; it clamps at junctions via
               junction_deviation = scv^2 (sqrt2 - 1) / a.  On a curve of radius rho cut into
               segments of length Ls the junction limit is  v_j = sqrt(8*jd*a) * rho / Ls,
               so segments must satisfy  Ls <= sqrt(8*jd*a)*rho / v  or the PLANNER slows you
               down even though the physics allows full speed.
               K2 Plus: scv=10, a=8000 -> jd=5.178e-3 -> Ls <= 0.0910*rho at 200 mm/s.
               We emit Ls = seg_k*rho (seg_k=0.06, 34% margin), clamped to [0.20, 1.00] mm.

Extrusion is computed PER MM OF PATH from strand_w*layer_h, never from feedrate, so a
feedrate clamp changes only the time, never the deposited geometry.
"""
import math
import numpy as np

GOLDEN_CONJ = 2.0 / (1.0 + math.sqrt(5.0))          # 0.6180339887


# --------------------------------------------------------------------------- the curve
def trochoid_points(M, N, beta, rmax=29.0, centre=(30.0, 30.0), spin=0.0,
                    seg_k=0.06, seg_min=0.20, seg_max=1.00, n_dense=None, warp=None):
    """Curvature-adaptive polyline for one closed layer. Returns (x, y) with the loop closed
    (last point == first point). Segment length is tied to the local radius of curvature so
    Klipper's junction-deviation limit never binds below the physical centripetal limit.

    ORDER MATTERS (found by parsing the emitted file back, 2026-07-25): the warp must be
    applied to the DENSE curve and the curvature measured AFTER it. Warping a polyline that
    was already segmented for the unwarped curvature leaves segments too long where the warp
    tightens the curve and too short where it stretches it -- and segments shorter than the
    0.001mm gcode coordinate quantisation turn junction angles into pure noise, which makes
    Klipper clamp to near zero. That cost 4.9% of the path before it was caught."""
    g = math.gcd(abs(M), abs(N))
    M, N = M // g, N // g
    if N < 0:
        M, N = -M, -N
    m = M / N
    A = rmax / (1.0 + beta)
    B = beta * A
    if n_dense is None:
        n_dense = max(300_000, int(abs(M - N)) * 30_000)

    t = np.linspace(0.0, 2.0 * math.pi * N, n_dense, endpoint=False)
    z = A * np.exp(1j * t) + B * np.exp(1j * m * t)
    z = z * np.exp(1j * spin)
    if warp:
        # superellipse push toward the square's corners. A circular curve can only ever reach
        # pi/4 = 78.5% of a square; |x|^n+|y|^n=1 reaches 92.7% at n=4. Smooth, so it costs
        # curvature (rho_min 8.51 -> 4.32mm) but introduces no corners.
        th = np.angle(z)
        z = z * (np.abs(np.cos(th)) ** warp + np.abs(np.sin(th)) ** warp) ** (-1.0 / warp)

    zc = np.append(z, z[0])
    s = np.concatenate([[0.0], np.cumsum(np.abs(np.diff(zc)))])
    L = float(s[-1])

    # curvature of whatever curve we actually ended up with (warped or not), by finite
    # difference on the dense sampling -- no analytic form survives the warp.
    k = max(2, int(round(0.25 / (L / n_dense))))          # ~0.25mm stencil
    zm, zp = np.roll(z, k), np.roll(z, -k)
    a_ = np.abs(z - zm); b_ = np.abs(zp - z); c_ = np.abs(zp - zm)
    area2 = np.abs((z - zm).real * (zp - zm).imag - (z - zm).imag * (zp - zm).real)
    kappa = np.where(a_ * b_ * c_ > 1e-15, 2.0 * area2 / np.maximum(a_ * b_ * c_, 1e-15), 0.0)
    rho = 1.0 / np.maximum(kappa, 1e-12)

    # adaptive walk: step by seg_k * rho(local), clamped. seg_min must stay far above the
    # 0.001mm gcode quantisation or junction angles become noise.
    step = np.clip(seg_k * np.append(rho, rho[0]), seg_min, seg_max)
    out_s, cur = [0.0], 0.0
    while cur < L - seg_min:
        cur += float(np.interp(cur, s, step))
        out_s.append(min(cur, L))
    # Close the loop WITHOUT leaving a stub. A final segment shorter than the 0.001mm gcode
    # quantisation has a meaningless direction, so Klipper reads a near-reversal there and
    # clamps to ~2mm/s -- one stub per layer was 0.39% of the path stuck below 90%.
    while len(out_s) > 2 and L - out_s[-2] < 0.75 * seg_min:
        out_s.pop()
    out_s[-1] = L
    out_s = np.array(out_s)

    zr = np.interp(out_s, s, zc.real) + 1j * np.interp(out_s, s, zc.imag)
    return zr.real + centre[0], zr.imag + centre[1], L


def layer_spins(n_layers, petals):
    """Rotation per layer. The curve already has `petals`-fold rotational symmetry, so the
    whole distinct-orientation range is ONE symmetry cell of 2*pi/petals -- rotating further
    just reproduces an earlier layer. Distribute inside that cell by the golden ratio, which
    is the sequence with the most uniform gaps for every prefix length.

    Consequence worth having: the reposition between layers is at most one cell of rim arc
    (2*pi*rmax/petals, ~5-8 mm), not a 60 mm dash across the coupon."""
    cell = 2.0 * math.pi / max(1, petals)
    return [((i * GOLDEN_CONJ) % 1.0) * cell for i in range(n_layers)]


# --------------------------------------------------------------------------- gcode
def gen_spiro_coupon(M=32, N=1, beta=0.50, beta_dither=0.24, warp=4.0,
                     layers=15, rmax=29.0, size=60.0,
                     layer_h=0.40, strand_w=0.50, temp=230, bed=60, fan=0,
                     feed_mm_s=200.0, filament_d=1.75, origin=40.0,
                     seg_k=0.06, seg_min=0.20, seg_max=1.00,
                     base_layers=2, base_pitch=1.2, accel=8000,
                     start_gcode=None, end_gcode=None):
    """Emit the whole coupon. Returns (gcode_string, stats_dict).

    base_layers: dense Archimedean-spiral layers bonded to the plate before the web starts.
                 A spiral, not a raster: no reversals, so it is laid at constant speed too.
                 Set 0 to print the bare web (and read the honest warning in the notes).
    """
    petals = abs(M // math.gcd(abs(M), abs(N)) - N // math.gcd(abs(M), abs(N)))
    cx = cy = origin + size / 2.0
    fil_area = math.pi * (filament_d / 2.0) ** 2
    e_per_mm = (strand_w * layer_h) / fil_area          # per mm of PATH, speed-independent
    e_per_mm_base = (min(1.2, 0.9) * layer_h) / fil_area
    F = int(round(feed_mm_s * 60))

    G, E, z = [], 0.0, 0.0
    w = G.append
    w(f"; spiro coupon  M={M} N={N} beta={beta}  petals={petals} wraps={N}")
    w(f"; ONE continuous self-intersecting curve per layer. No pillars. No travel inside a layer.")
    w(f"; {size}mm coupon, {layers}x{layer_h}mm web + {base_layers} base, T{temp} fan{fan}")
    w(f"; strand {strand_w}x{layer_h}mm, feed {feed_mm_s}mm/s -> "
      f"{strand_w*layer_h*feed_mm_s:.1f} mm3/s (working ceiling 68.8)")
    if start_gcode:
        w(start_gcode.rstrip())
    else:
        w("G90"); w("M83")
        w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G28")
        w(f"M190 S{bed}"); w(f"M109 S{temp}")
    w(f"M106 S{fan}")
    w(f"M104 S{temp}")
    w(f"M204 S{accel}")
    w("M83")

    # ---- base: Archimedean spiral, plate-bonded, continuous, no reversals
    for bl in range(base_layers):
        z = round(z + layer_h, 3)
        w(f"; base layer {bl+1} — Archimedean spiral, {base_pitch}mm pitch")
        w(f"G0 Z{z:.3f} F1200")
        turns = (rmax + 1.0) / base_pitch
        th = np.linspace(0.0, 2 * math.pi * turns, int(turns * 720) + 2)
        r = base_pitch * th / (2 * math.pi)
        if bl % 2:
            th = th[::-1]; r = r[::-1]
        bx, by = cx + r * np.cos(th), cy + r * np.sin(th)
        w(f"G0 X{bx[0]:.3f} Y{by[0]:.3f} F9000")
        w(f"G1 E{0.6:.4f} F1800"); E += 0.6
        for i in range(1, len(bx)):
            d = math.hypot(bx[i] - bx[i-1], by[i] - by[i-1])
            if d < 1e-4:
                continue
            e = d * e_per_mm_base; E += e
            w(f"G1 X{bx[i]:.3f} Y{by[i]:.3f} E{e:.5f} F{min(F, 6000):d}")

    # ---- web: one continuous trochoid per layer
    spins = layer_spins(layers, petals)
    seg_count, path_len = 0, 0.0
    px, py = None, None
    for li in range(layers):
        z = round(z + layer_h, 3)
        # beta dither: rotation alone cannot de-stack crossings near the centre (its
        # displacement scales with radius), so beta is dithered to sweep the inner caustic
        # radially as well. Golden sequence again -> uniform for every prefix length.
        b_li = beta - beta_dither/2 + ((li*GOLDEN_CONJ) % 1.0)*beta_dither
        X, Y, L = trochoid_points(M, N, b_li, rmax=rmax, centre=(cx, cy), spin=spins[li],
                                  seg_k=seg_k, seg_min=seg_min, seg_max=seg_max, warp=warp)
        path_len += L; seg_count += len(X) - 1
        w(f"; web layer {li+1}/{layers}  spin={math.degrees(spins[li]):.3f}deg  "
          f"beta={b_li:.4f}  L={L:.1f}mm  segs={len(X)-1}")
        # A closed curve can be STARTED ANYWHERE on itself -- a phase shift in t is a free
        # re-parametrisation of the same point set. So begin each layer at whichever of its
        # own points is nearest to where the head already is. Consecutive layers differ only
        # by a fraction of a symmetry cell, so that point is a fraction of a millimetre away:
        # the inter-layer reposition collapses to ~0 and there is no travel move in the file
        # at all after the first. (The earlier rim-arc reposition assumed constant radius,
        # which the superellipse warp breaks -- it left a 5mm radial jump and a hard corner.)
        if px is not None:
            k0 = int(np.argmin((X - px) ** 2 + (Y - py) ** 2))
            X = np.concatenate([X[k0:], X[1:k0 + 1]])
            Y = np.concatenate([Y[k0:], Y[1:k0 + 1]])
        w(f"G0 Z{z:.3f} F1200")
        if px is None:
            w(f"G0 X{X[0]:.3f} Y{Y[0]:.3f} F9000")
        else:
            d = math.hypot(X[0] - px, Y[0] - py)
            if d > 1e-3:
                e = d * e_per_mm; E += e
                w(f"G1 X{X[0]:.3f} Y{Y[0]:.3f} E{e:.5f} F{F:d}   ; layer seam, {d:.3f}mm")
        for i in range(1, len(X)):
            d = math.hypot(X[i] - X[i-1], Y[i] - Y[i-1])
            if d < 1e-4:
                continue
            e = d * e_per_mm; E += e
            w(f"G1 X{X[i]:.3f} Y{Y[i]:.3f} E{e:.5f} F{F:d}")
        px, py = X[-1], Y[-1]

    if end_gcode:
        w(end_gcode.rstrip())
    else:
        w("M104 S0"); w("M140 S0"); w("M106 S0")
        w(f"G0 Z{z+20:.2f} F1200"); w(f"G0 X5 Y{origin+size+20:.0f} F6000")
    grams = E * fil_area * 1.24 / 1000.0
    stats = dict(M=M, N=N, beta=beta, beta_dither=beta_dither, warp=warp,
                 petals=petals, wraps=N, layers=layers,
                 web_len_mm=path_len, segments=seg_count, filament_mm=E, grams=grams,
                 est_min=path_len / feed_mm_s / 60.0,
                 flow_mm3_s=strand_w * layer_h * feed_mm_s,
                 lines=len(G))
    return "\n".join(G) + "\n", stats


if __name__ == "__main__":
    gc, st = gen_spiro_coupon()
    for k, v in st.items():
        print(f"  {k:14} {v}")
    open("spiro_demo.gcode", "w").write(gc)
    print("  wrote spiro_demo.gcode")
