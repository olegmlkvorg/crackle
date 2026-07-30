#!/usr/bin/env python3
"""COLONNADE — a 3-leg cross-braced anti-vibration printer stand (alien-tech). RENDER-FIRST.

Oleg, 2026-07-30: the alien-tech stand. Three twisted-clover legs (the spiraltower.py profile,
Oleg's "why square? alien tech, feel it") stand on a wide ring as a tripod, rising TOGETHER in
rotation exactly like towers.py — the head lays a run of helical laps on a leg, HOPS (lifted, flow
suspended) to the next, and so on, so every leg gets a full rotation's worth of cooling before its
next pass. The frame is TRIANGULATED by diagonal cross-braces thrown across the leg gaps.

WHAT IS PROVEN vs PROVISIONAL (no overselling — read before trusting):
  * THE LEGS are the spiraltower.py mechanism, which prints: a continuous vase-mode clover helix,
    pressed 0.1 first lap, flow carried by a wide bead at the north-star speed. Three rising in
    rotation is the towers.py mechanism, which also prints. This is proven machinery.
  * THE TWIST is CLAMPED so the clover peak cannot "walk" faster than the walk limit per layer
    (Oleg's printed test: a fast twist makes the layers walk off themselves). At the default height
    a full 360deg turn would walk too fast, so the twist is reduced and the reduction is reported.
    Run it taller for a full turn.
  * THE CROSS-BRACES are geometry-valid and collision/dive-safe BY CONSTRUCTION: every strut is a
    continuous strand that launches from, and lands on, a leg's CURRENT build top and only crosses
    open air in between — it never lands on the lower part of a taller wall, which is the collision
    validate.py's dive check forbids. But each strut spans the full ~90mm leg gap, far longer than
    the 28mm rungs towers.py has actually printed. Printability of the braces is UNPROVEN; this
    generator renders them so the FORM can be judged. It does not claim they print.

WHY DIAGONAL BRACES, NOT LITERAL CROSSING "X"s. A vase-mode wall only ever rises, and validate.py
(correctly) refuses any strand that descends onto material already standing higher — that is a
head-into-wall collision. The two struts of a true X would need the two legs in OPPOSITE height
states at the same band (one high while the other is low, and vice-versa) — impossible when both
legs only rise. So the bracing is a set of diagonals thrown from a low "pivot" leg up to its two
risen neighbours (a doubled out-and-back strand each), with the pivot rotating band to band. Over
three bands every face is braced from two directions — a real triangulated cross-brace, the honest
shape the monotonic-rise constraint allows.

Bed 60 default (Oleg: cold spaghettied; PLA rated 50-70). Pressed 0.1 first lap. Hollow single-bead
legs (fill sand+gypsum + bamboo core later, like spiraltower).

Usage:  python3 colonnade.py [--height 200] [--dia 80] [--lobes 4] [--twist 360] [--ring-r 100]
                             [--bands 3] [--band-h 40] [--kpv 6] [--bed 60]
        python3 validate.py out/colonnade_*.gcode          # must pass
        python3 render.py  out/colonnade_*.gcode out.svg   # 3 legs + cross-braces
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

A_FIL = math.pi * (1.75 / 2) ** 2
TWIST_MAX_OFFSET = 0.6   # mm the clover peak may shift per layer before the wall "walks" (Oleg)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--height", type=float, default=200.0,
                    help="leg height mm (one segment; the full 600 stand stacks segments)")
    ap.add_argument("--dia", type=float, default=80.0, help="mean leg diameter mm (Oleg: bump for stability)")
    ap.add_argument("--lobes", type=int, default=4, help="flutes around (Oleg chose 4 — a clover)")
    ap.add_argument("--flute", type=float, default=13.5, help="flute depth mm (peak-to-valley radius swing)")
    ap.add_argument("--twist", type=float, default=360.0,
                    help="degrees the clover rotates over the height (clamped to the walk limit)")
    ap.add_argument("--ring-r", type=float, default=100.0, help="leg centres sit on this radius (stance width)")
    ap.add_argument("--legs", type=int, default=3)
    ap.add_argument("--bands", type=int, default=3, help="number of cross-brace height bands")
    ap.add_argument("--band-h", type=float, default=40.0, help="height mm each brace band spans")
    ap.add_argument("--kpv", type=int, default=6, help="laps per leg per rotation visit (cooling revisit)")
    ap.add_argument("--double-brace", type=int, default=1, choices=(1, 2),
                    help="1 = single strand, 2 = doubled out-and-back (rides the first pass)")
    ap.add_argument("--bed", type=float, default=60,
                    help="bed C, default 60 (PLA rated 50-70; 0 = cold, no M190 wait)")
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    flow = machine.flow_cap(a.material, a.printer)
    lh = a.layer_h
    bw = machine.bead_for_flow(flow, lh)
    speed = machine.speed_for_flow(flow, bw, lh)
    temp = machine.temp_for(a.material)
    f = round(speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    e_per_mm = bw * lh / A_FIL
    bx, by = machine.BED[a.printer]
    bed = min(a.bed, machine.BED_MAX.get(a.printer, machine.BED_MAX_DEFAULT)) if a.bed else 0

    N = a.legs
    Rm = a.dia / 2.0
    r_peak = Rm + a.flute * 0.5           # outermost radius (a clover peak)
    R = a.ring_r
    seg_len = max(1.2, speed / 30.0)      # target strand/lap segment length (move-rate safe)
    PPL = max(96, int(round(2 * math.pi * Rm / seg_len)))   # points per lap (smooth clover)

    # ---- TWIST CLAMP. The clover peak shifts r_peak * twist_rate * layer_h laterally per layer;
    # above the walk limit the wall walks off itself (Oleg's printed test). Clamp so the peak
    # offset stays <= TWIST_MAX_OFFSET, and SAY when it bit. ----
    req_twist = math.radians(a.twist)
    max_twist = TWIST_MAX_OFFSET * a.height / (r_peak * lh)     # rad, from offset = r_peak*(tw/H)*lh
    twist_rad = min(req_twist, max_twist)
    twist_rate = twist_rad / a.height                          # rad of clover phase per mm of height
    peak_offset = r_peak * twist_rate * lh                     # mm the peak walks per layer
    twist_clamped = req_twist > max_twist + 1e-9

    # ---- FOOTPRINT. Legs on a ring, then the cluster shifted so its peak-radius bounding box is
    # centred on the plate (max clearance). Refuse if it will not fit with 6mm to spare. ----
    angs = [math.radians(90 + 360.0 * k / N) for k in range(N)]  # one leg points +Y
    raw = [(R * math.cos(t), R * math.sin(t)) for t in angs]
    xs = [p[0] for p in raw]; ys = [p[1] for p in raw]
    cx = bx / 2.0 - (min(xs) + max(xs)) / 2.0
    cy = by / 2.0 - (min(ys) + max(ys)) / 2.0
    centres = [(cx + p[0], cy + p[1]) for p in raw]
    lo_x = min(c[0] for c in centres) - r_peak; hi_x = max(c[0] for c in centres) + r_peak
    lo_y = min(c[1] for c in centres) - r_peak; hi_y = max(c[1] for c in centres) + r_peak
    fp_x, fp_y = hi_x - lo_x, hi_y - lo_y
    if lo_x < 6 or lo_y < 6 or hi_x > bx - 6 or hi_y > by - 6:
        sys.exit(f"footprint {fp_x:.0f}x{fp_y:.0f}mm at ring-r {R:g} leaves < 6mm on the "
                 f"{bx:g}x{by:g} bed — reduce --ring-r or --dia")

    n_climb = int(round((a.height - machine.PRESS_HARD) / lh))   # climbing laps above the pressed foot
    top_z = machine.PRESS_HARD + n_climb * lh

    # ---- CROSS-BRACE BANDS: (lap_lo, lap_hi, pivot leg). Centred at even fractions of the height,
    # each band_laps tall; the pivot rotates band to band so every face is braced from two sides. ----
    faces_for = lambda p: [k for k in range(N) if k != p]
    band_laps = max(6, int(round(a.band_h / lh)))
    bands = []
    if a.bands > 0 and n_climb > band_laps + 6:
        for j in range(a.bands):
            centre = int(round((j + 1) / (a.bands + 1) * n_climb))
            b0 = max(1, centre - band_laps // 2)
            b1 = min(n_climb, b0 + band_laps)
            if b1 - b0 >= 6 and (not bands or b0 > bands[-1][1] + 4):
                bands.append((b0, b1, j % N))
    gap_dist = math.dist(centres[0], centres[1]) - 2 * Rm        # rim-to-rim air span (approx)

    # ---------------------------------------------------------------------------------------------
    def radius(theta, z):
        """Twisted clover radius at azimuth theta and absolute height z (from the plate)."""
        return Rm + a.flute * 0.5 * math.cos(a.lobes * (theta - twist_rate * (z - machine.PRESS_HARD)))

    def rim(k, toward_xy, z):
        """Point on leg k's wall on the side facing toward_xy, at height z. Returns (x,y,z)."""
        tx, ty = centres[k]
        th = math.atan2(toward_xy[1] - ty, toward_xy[0] - tx)
        r = radius(th, z)
        return (tx + r * math.cos(th), ty + r * math.sin(th), z)

    seam = [math.atan2(cy - centres[k][1], cx - centres[k][0]) for k in range(N)]  # inward, fixed

    def seam_pt(k, z):
        tx, ty = centres[k]; r = radius(seam[k], z)
        return (tx + r * math.cos(seam[k]), ty + r * math.sin(seam[k]), z)

    # ---------------------------------------------------------------------------------------------
    L = []; w = L.append
    e = 0.0
    qx = qy = qz = None
    zmax_seen = machine.PRESS_HARD
    done = [0] * N            # climbing laps completed per leg
    z = [machine.PRESS_HARD] * N

    def move_e(X, Y, Z):
        nonlocal e, qx, qy, qz, zmax_seen
        d3 = math.dist((qx, qy, qz), (X, Y, Z))
        if d3 < 0.02:
            return
        e += d3 * e_per_mm
        w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}")
        qx, qy, qz = X, Y, Z
        zmax_seen = max(zmax_seen, Z)

    def hop_to(X, Y, Z):
        """Lifted, flow-suspended travel: up clear of everything, across, down. Tagged HOP so R5
        excludes it and the plough check sees the XY move happen up high."""
        nonlocal qx, qy, qz
        if qx is not None and math.dist((qx, qy, qz), (X, Y, Z)) < 0.05:
            return
        clear = zmax_seen + 5.0
        w(f"G0 Z{clear:.3f} F1800   ; HOP lift clear")
        w(f"G0 X{X:.3f} Y{Y:.3f} F{travel_f}   ; HOP across")
        w(f"G0 Z{Z:.3f} F1800   ; HOP down")
        qx, qy, qz = X, Y, Z

    def foot(k, first=False):
        """Layer 1: one flat pressed clover lap at PRESS_HARD (wide bead welds to the plate)."""
        nonlocal qx, qy, qz
        tx, ty = centres[k]
        Z1 = machine.PRESS_HARD
        p0 = seam_pt(k, Z1)
        if first:
            w(f"G0 F9000 X{p0[0]:.3f} Y{p0[1]:.3f} ; PRIME-TRAVEL")
            w(f"G1 F1800 Z{Z1:.3f}")
            w(f"G1 F{f}")
            qx, qy, qz = p0
        else:
            hop_to(*p0)
            w(f"G1 F{f}")
        for i in range(1, PPL + 1):
            th = seam[k] + 2 * math.pi * i / PPL
            r = radius(th, Z1)
            move_e(tx + r * math.cos(th), ty + r * math.sin(th), Z1)

    def climb(k, target):
        """Continue leg k's clover helix from done[k] up to lap index `target`, in one stroke."""
        nonlocal qx, qy, qz
        if done[k] >= target:
            return
        m = target - done[k]
        z_start = z[k]
        tx, ty = centres[k]
        hop_to(*seam_pt(k, z_start))       # returns to the leg's own seam -> continuous helix
        w(f"G1 F{f}")
        steps = m * PPL
        for i in range(1, steps + 1):
            frac = i / PPL
            th = seam[k] + 2 * math.pi * frac
            zz = z_start + frac * lh
            r = radius(th, zz)
            move_e(tx + r * math.cos(th), ty + r * math.sin(th), zz)
        done[k] = target
        z[k] = z_start + m * lh

    def rotate(group, target):
        """Rise every leg in `group` together to lap index `target`, kpv laps per visit."""
        while any(done[k] < target for k in group):
            for k in group:
                if done[k] < target:
                    climb(k, min(target, done[k] + a.kpv))

    def strand(p_from, p_to):
        """One continuous brace strand from p_from to p_to (both (x,y,z)); climbs or descends
        through open air. Subdivided so it renders as a line and stays move-rate safe."""
        hop_to(*p_from)
        w(f"G1 F{f}")
        n = max(8, int(math.dist(p_from, p_to) / seg_len))
        for i in range(1, n + 1):
            t = i / n
            w_line(p_from[0] + (p_to[0] - p_from[0]) * t,
                   p_from[1] + (p_to[1] - p_from[1]) * t,
                   p_from[2] + (p_to[2] - p_from[2]) * t)

    def w_line(X, Y, Z):
        nonlocal e, qx, qy, qz, zmax_seen
        d3 = math.dist((qx, qy, qz), (X, Y, Z))
        e += d3 * e_per_mm
        w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}   ; BRACE")
        qx, qy, qz = X, Y, Z
        zmax_seen = max(zmax_seen, Z)

    n_brace = 0
    def brace_band(b0, b1, pivot):
        """Rise the two non-pivot legs to the band top, then throw a doubled diagonal from the
        pivot's current top up to each risen neighbour, then let the pivot catch up."""
        nonlocal n_brace
        others = faces_for(pivot)
        rotate(others, b1)                          # neighbours up; pivot stays low
        z_lo = z[pivot]                             # pivot's current top (band bottom-ish)
        for k in others:
            p_pt = rim(pivot, centres[k], z_lo)     # launch on the pivot's current top
            k_pt = rim(k, centres[pivot], z[k])     # land on the neighbour's current top
            strand(p_pt, k_pt)                      # climb across the gap (dive-safe)
            if a.double_brace == 2:
                strand(k_pt, p_pt)                  # ride back down the same line (doubles it)
            n_brace += 1
        climb(pivot, b1)                            # pivot rises to rejoin the others

    # ---- header + start (mirrors spiraltower/towers; probe hot for R7) ----
    w("; COLONNADE — 3-leg cross-braced alien-tech printer stand (twisted-clover legs)")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; FLOW={bw*lh*speed:.4f}")
    w(f"; PRINT_TEMP={temp}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w(f"; SEQUENTIAL={N} legs rising in rotation, lifted hops between")
    w(f"; ARCH_LIFT={lh:.3f}")     # Z varies within a lap (helix) and within a brace by design
    w(f"; legs x{N} dia{a.dia:g} lobes{a.lobes} flute{a.flute:g} on r{R:g}, h{a.height:g}, "
      f"bead {bw:.2f}x{lh:g}, twist {math.degrees(twist_rad):.0f}deg, {len(bands)} brace bands")
    w("; ARGV: " + " ".join(sys.argv))
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {n_climb + 1}"); w("; HEADER_BLOCK_END")
    w("M82")
    if bed > 0:
        w(f"M140 S{bed:.0f}")
        w(f"M104 S{temp}")
        _wait = bed if a.printer == "k2plus" else machine.bed_start(a.material, bed)
        w(f"M190 S{_wait:.0f}")
    else:
        w("M140 S0                          ; COLD BED — solar run, no bed heat, no M190 wait")
        w(f"M104 S{temp}")
    w(f"M109 S{temp}")
    w("G28")
    w("SET_GCODE_OFFSET Z=-0.05             ; first-lap press insurance (K2 datum ~0.1 high)")
    w("G92 E0")

    px, py = 20.0, 16.0
    w(f"G1 F600 Z{machine.PRESS_HARD:.3f}")
    w(f"G0 F9000 X{px:.3f} Y{py:.3f}")
    w("G1 E18 F300                          ; PRIME stationary purge")
    w(f"G1 F1200 X{px+40:.3f} Y{py:.3f} E28  ; PRIME line")
    w(f"G0 F3000 X{px+52:.3f} Y{py+12:.3f}   ; PRIME break-off wipe")
    w("G92 E0")
    w("; BODY_START")

    # ---- LAYER 1: pressed clover feet, all legs, hops between ----
    w("M107                              ; feet are layer 1: no cooling")
    for k in range(N):
        foot(k, first=(k == 0))
    w("M106 S51                          ; body fan 20% from layer 2")

    # ---- BODY: rise together in rotation; at each band, brace via the pivot leapfrog ----
    allk = list(range(N))
    for (b0, b1, pivot) in bands:
        rotate(allk, b0)
        brace_band(b0, b1, pivot)
    rotate(allk, n_climb)

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{zmax_seen + 30:.1f} F900")
    w(f"G0 X{min(10.0, bx-10):.0f} Y{by-10:.0f} F9000")
    g = "\n".join(L) + "\n"

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"colonnade_{a.printer}_x{N}_d{a.dia:g}_h{a.height:g}_T{temp:g}.gcode")
    open(fn, "w").write(g)

    grams = e * A_FIL * 1.24 / 1000.0
    mins = (e / e_per_mm) / speed / 60.0
    print(f"  {N} clover legs dia{a.dia:g} (lobes {a.lobes}, flute {a.flute:g}) on ring r{R:g}, "
          f"h{a.height:g}, {n_climb} climbing laps (+ pressed foot)")
    print(f"  footprint {fp_x:.0f}x{fp_y:.0f}mm on the {bx:g}x{by:g} bed "
          f"(X {lo_x:.0f}..{hi_x:.0f}, Y {lo_y:.0f}..{hi_y:.0f}); maxZ {top_z:.0f}mm")
    if twist_clamped:
        print(f"  TWIST CLAMPED {a.twist:g}deg -> {math.degrees(twist_rad):.0f}deg: a full turn over "
              f"{a.height:g}mm would walk the clover peak {r_peak*(req_twist/a.height)*lh:.2f}mm/layer "
              f"(> {TWIST_MAX_OFFSET:g}). Run taller (>= "
              f"{r_peak*req_twist*lh/TWIST_MAX_OFFSET:.0f}mm) for a full turn.")
    print(f"  twist {math.degrees(twist_rad):.0f}deg -> peak walk {peak_offset:.3f}mm/layer "
          f"(limit {TWIST_MAX_OFFSET:g}; half-bead {bw/2:.2f})")
    print(f"  {len(bands)} brace bands, pivots {[b[2] for b in bands]}, {n_brace} diagonal struts"
          + (" (doubled out-and-back)" if a.double_brace == 2 else "")
          + f" across a {gap_dist:.0f}mm gap  [BRACE PRINTABILITY UNPROVEN]")
    print(f"  flow {bw*lh*speed:.0f} mm3/s at {speed:g} mm/s, bead {bw:.2f}x{lh:g}, kpv {a.kpv}; "
          f"~{grams:.0f} g, ~{mins:.0f} min extruding + hops, bed {bed:g}"
          + ("C" if bed else " (cold)"))
    print(fn)


if __name__ == "__main__":
    main()
