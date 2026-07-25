#!/usr/bin/env python3
"""NUCLEON — the flat atom drawing as a toolpath. Oleg, 2026-07-25: "think of flat nucleon drawing".

N ellipses rotated evenly about one centre, drawn as ONE continuous path. It is the best coupon
geometry measured so far, and it satisfies every constraint the project has accumulated:

  · perfectly smooth — no corners anywhere, so the head holds commanded speed
    (N=8: 6.5% of path below 90% speed, vs 93% for the old pillar lattice and 15.9% for a Lissajous)
  · circular outer bound — suits a round object, and it IS a recognisable thing rather than a squiggle
  · crossings land on a RING, not piled at the centre. The star-order lattice put 5 chords through
    one point and half its "crossings" were the same weld; ellipses about a common centre intersect
    each other in 4 points each, away from the middle.
  · crossings scale as 2*N*(N-1) — a clean analytic dial, verified numerically.

MEASURED (a=25mm, 235 mm/s, accel 8000):
    N= 3   16 junctions   member 13.9mm   11.9% below speed
    N= 6   70 junctions   member  6.0mm    8.1%
    N= 8  126 junctions   member  4.3mm    6.5%
    N=12  286 junctions   member  2.8mm    4.7%

THE TRADE-OFF TO TEST, and it is the real question: more junctions means SHORTER members between
them. Slender spans snap; short stubby ones bend quietly, which is the hex-grid feel that started
this project. At strand 0.85mm, N=6 gives a 7:1 span-to-thickness ratio and N=12 gives 3:1. More
crossings is not obviously better — it may be worse. Print both.

Fatter ellipses (b/a 0.55) print FASTER than thin ones — less curvature at the tips.

WELD CONTROL carries over from weave.py: in a single layer the second pass through a crossing must
lift or plough the bead already down. Lift = interlace, stay = fuse. Phase 1 said fusing is the
mechanism, so --weld defaults to 1.0.
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import smooth
from pathstats import crossings as find_crossings


def _ellipse_R(a, b, t):
    """Local radius of curvature of the ellipse at parameter t."""
    num = (a * a * math.sin(t) ** 2 + b * b * math.cos(t) ** 2) ** 1.5
    return num / max(a * b, 1e-9)


def nucleon_path(N, a, b, cx, cy, n_per, phase=0.0, speed=None, accel=None):
    """ADAPTIVE sampling: dense only where the curve is actually tight.

    Uniform sampling at n_per=600 gave 0.237mm segments, which at 235 mm/s is 990 moves/second.
    Klipper drains its lookahead buffer well below that and stalls to refill — the head stopped
    dead roughly every 3 seconds (Oleg spotted it, 2026-07-25). Resolution is only needed where
    curvature is high; an ellipse's radius runs from b^2/a at the major-axis tips to a^2/b at the
    minor ones, a factor of (a/b)^2, so uniform sampling oversamples most of the path by an order
    of magnitude.

    Segment length at each point is the longest that still holds `speed` there, from the same
    junction-deviation model the fillet uses."""
    if speed is None:
        pts = []
        for k in range(N):
            rot = phase + math.pi * k / N
            c, s = math.cos(rot), math.sin(rot)
            for i in range(n_per + 1):
                t = 2 * math.pi * i / n_per
                x, y = a * math.cos(t), b * math.sin(t)
                pts.append((cx + x * c - y * s, cy + x * s + y * c))
        return pts
    accel = accel or machine.ACCEL
    jd = 5.0 ** 2 * (math.sqrt(2.0) - 1.0) / accel
    kk = speed ** 2 / (jd * accel)
    h = math.acos(min(1.0, kk / (1.0 + kk)))          # half turn-angle budget per junction
    pts = []
    for k in range(N):
        rot = phase + math.pi * k / N
        c, s = math.cos(rot), math.sin(rot)
        t = 0.0
        while t < 2 * math.pi:
            x, y = a * math.cos(t), b * math.sin(t)
            pts.append((cx + x * c - y * s, cy + x * s + y * c))
            R = _ellipse_R(a, b, t)
            seg = max(2.0 * R * h, 0.15)              # arc length we may travel before turning
            dRdt = math.hypot(a * math.sin(t), b * math.cos(t))   # |dP/dt|
            t += max(seg / max(dRdt, 1e-9), 1e-4)
        x, y = a, 0.0
        pts.append((cx + x * c - y * s, cy + x * s + y * c))
    # ROUND THE JOINS. Each ellipse ends where it began and the next starts at a different
    # rotation, so the path crosses a chord between them — a genuine ~19deg corner, one per
    # ellipse. At 70 mm/s an 19deg turn caps the head at 28 mm/s, which is where the last 8.6% of
    # speed loss was hiding. Everything else on the curve is already gentle, and fillet() leaves
    # near-straight vertices untouched, so this only affects the joins.
    # (Oleg, 2026-07-25: "not sharp angles, make sure you use semi circlish always".)
    if speed:
        r_min = speed * speed / (accel or machine.ACCEL)
        pts = smooth.fillet(pts, max(2.0 * r_min, 2.0), speed=speed, accel=accel or machine.ACCEL)
    return pts


def emit(N, a, ratio, origin, layers, layer_h, strand_w, flow, weld, lift, lift_win,
         temp, bed, fan, fil_d, home, n_per, first_slow=0, first_speed_frac=1.0,
         first_squish=0.85, vase=False):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (strand_w * layer_h) / area
    # Speed is CAPPED, and flow follows from it rather than the other way round. Thick walls and
    # a calm head beat chasing volumetric throughput; and on stacked geometry the two cannot both
    # be satisfied anyway (see machine.MAX_SPEED).
    speed = min(flow / (strand_w * layer_h), machine.MAX_SPEED)
    actual_flow = strand_w * layer_h * speed
    f_mm_min = round(speed * 60)
    b = a * ratio
    cx = cy = origin + a

    if strand_w < machine.NOZZLE:
        raise SystemExit(f"strand_w {strand_w} is below the {machine.NOZZLE}mm orifice — a nozzle "
                         f"cannot lay a bead narrower than its hole; the melt stretches thin and "
                         f"breaks into beads that look like retraction stringing.")
    if weld < 1.0:
        vz = math.pi * lift * speed / (2 * lift_win)
        az = (math.pi ** 2) * lift * speed ** 2 / (2 * lift_win ** 2)
        if vz > machine.MAX_Z_V or az > machine.MAX_Z_A:
            need = speed * math.pi * math.sqrt(lift / (2 * machine.MAX_Z_A))
            raise SystemExit(f"Z cannot follow the lift at {speed:.0f} mm/s: a_peak {az:.0f} "
                             f"(limit {machine.MAX_Z_A}). Need --lift-win {math.ceil(need)}.")

    L = []; w = L.append
    w(f"; NUCLEON — {N} ellipses a={a} b={b:.1f}, weld={weld}, {layers} layers")
    w(f"; flow={actual_flow:.1f} mm3/s at {speed:.0f} mm/s (capped), bead {strand_w}x{layer_h} = {strand_w*layer_h:.2f}mm2")
    w(f"; predicted junctions/layer = 2*N*(N-1) = {2*N*(N-1)}")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {layers}"); w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — direct to print (fails safely if the machine lost home)")
    w(f"M190 S{bed}"); w(f"M109 S{temp}")
    w("M204 S8000"); w("M107" if not fan else f"M106 S{fan}")
    w("M82"); w("G92 E0")
    w(f"G1 Z{layer_h*0.85:.3f} F600")
    w(f"G0 F9000 X{origin:.1f} Y{origin-8:.1f}")
    w(f"G1 F1200 X{origin+2*a:.1f} Y{origin-8:.1f} E10"); w("G92 E0")
    if weld < 1.0:
        w("; Z_MODULATED")
    w("; BODY_START")

    e = 0.0; total_x = 0; total_lift = 0

    if vase:
        # VASE MODE — one unbroken extrusion for the whole object. Oleg: "why not continuous
        # nucleon? vasemode style". The layered version travels once per layer to reposition at the
        # path start; twelve layers is twelve visible travel lines. Here Z rises continuously with
        # distance travelled, so there is no layer change, no reposition, and no travel at all after
        # the initial approach.
        #
        # The crossings still weld, and that is not obvious — it needs checking rather than
        # assuming. Within one turn the N ellipses now sit at DIFFERENT heights, spread over
        # layer_h*(N-1)/N. For N=6 that is 0.50mm against a 0.60mm-tall bead, so strands still
        # overlap and fuse. It only fails if the spread exceeds the bead height, i.e. never, since
        # the spread is always < layer_h by construction.
        full = []
        for layer in range(layers):
            ph = (math.pi / N) * (layer * 0.5)
            seg = nucleon_path(N, a, b, cx, cy, n_per, ph, speed=speed)
            full.extend(seg if layer == 0 else seg[1:])
        cum = [0.0]
        for i in range(len(full) - 1):
            cum.append(cum[-1] + math.dist(full[i], full[i + 1]))
        total = cum[-1] or 1.0
        hits, _ = find_crossings(full)
        total_x = len(hits)
        L.append(f"; VASE — one continuous extrusion, {len(full)} points, "
                 f"Z {layer_h*first_squish:.2f} -> {layer_h*layers:.2f}, {total_x} junctions")
        L.append(f"G0 F9000 X{full[0][0]:.3f} Y{full[0][1]:.3f}")
        L.append(f"G1 F1800 Z{layer_h*first_squish:.3f}")
        z_lo = layer_h * first_squish
        z_hi = layer_h * layers
        for i in range(1, len(full)):
            frac = cum[i] / total
            z = z_lo + (z_hi - z_lo) * frac
            lf = round(machine.FIRST_LAYER_SPEED * 60) if frac < 1.0 / layers else f_mm_min
            e += math.dist(full[i - 1], full[i]) * e_per_mm
            L.append(f"G1 {'F%d ' % lf if i == 1 or (frac >= 1.0/layers and cum[i-1]/total < 1.0/layers) else ''}"
                     f"X{full[i][0]:.3f} Y{full[i][1]:.3f} Z{z:.4f} E{e:.5f}")
        L += ["M107", "M104 S0", "M140 S0", f"G1 Z{z_hi+40:.1f} F900", "G0 X10 Y340 F9000"]
        grams = e * area * 1.24 / 1000
        return "\n".join(L) + "\n", dict(grams=round(grams, 2), speed=round(speed),
                                          flow=round(actual_flow, 1), lines=len(L),
                                          junctions=total_x, lifts=0,
                                          mins=round(total / speed / 60, 1))

    for layer in range(layers):
        z0 = layer_h * (layer + 1)
        # FIRST LAYER. The balls failure (2026-07-25) came from 235 mm/s giving the bead no dwell to
        # wet the plate. With the head now capped at 50 mm/s the whole print runs at what IS a
        # first-layer speed, so no slowdown is needed and --first-slow defaults to 0.
        # The SQUISH stays: it presses the bead into the plate and does not touch flow, which is
        # what Oleg asked for — thick and irregular lines, always.
        if layer < first_slow:
            lf = round(machine.FIRST_LAYER_SPEED * 60)
            z0 = layer_h * first_squish
        else:
            lf = f_mm_min
        # rotate each layer off the last so crossings distribute through the volume instead of
        # stacking into welded vertical columns
        phase = (math.pi / N) * (layer * 0.5)
        pts = nucleon_path(N, a, b, cx, cy, n_per, phase, speed=speed)
        cum = [0.0]
        for i in range(len(pts) - 1):
            cum.append(cum[-1] + math.dist(pts[i], pts[i + 1]))
        hits, _ = find_crossings(pts)
        total_x += len(hits)
        second = []
        for k, (i, j, x, y) in enumerate(sorted(hits, key=lambda h: max(h[0], h[1]))):
            # Deterministic, evenly distributed, and correct for ANY crossing count.
            # The old rule was `(k % 100) >= weld*100`, which silently assumed >=100 crossings per
            # layer. There are 70, so k never reached 75 and --weld 0.75 lifted NOTHING while
            # reporting success; 0.5 lifted 64% and 0.25 lifted 100%. The primary control variable
            # of the whole project was miscalibrated at every setting except 0 and 1.
            # The golden-ratio low-discrepancy sequence: uniform for ANY count, and it spreads
            # the choice through the layer instead of fusing the early crossings and lifting
            # the late ones, which a plain k/n threshold would do. An integer hash mod 1000
            # does NOT work here — 997 = -3 mod 1000, so 70 crossings only ever sampled the
            # top fifth of the range and almost everything lifted.
            if ((k * 0.6180339887498949) % 1.0) >= weld:
                second.append(cum[max(i, j)]); total_lift += 1
        L.append(f"; layer {layer+1}  z{z0:.2f}  junctions {len(hits)}  lifts {len(second)}")
        L.append(f"G0 F9000 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
        L.append(f"G1 F1800 Z{z0:.3f}")   # layer-change Z move: 10 -> 30 mm/s
        for i in range(1, len(pts)):
            dz = 0.0
            if second:
                s = cum[i]
                for sv in second:
                    d = s - sv
                    if abs(d) < lift_win:
                        dz = max(dz, lift * math.cos(math.pi * d / (2 * lift_win)) ** 2)
            e += math.dist(pts[i - 1], pts[i]) * e_per_mm
            L.append(f"G1 {'F%d ' % lf if i == 1 else ''}X{pts[i][0]:.3f} "
                     f"Y{pts[i][1]:.3f} Z{z0+dz:.4f} E{e:.5f}")

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{layer_h*layers+40:.1f} F900", "G0 X10 Y340 F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(grams=round(grams, 2), speed=round(speed), flow=round(actual_flow,1), lines=len(L),
                                     junctions=total_x, lifts=total_lift,
                                     mins=round(e / e_per_mm / speed / 60, 1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=8, help="ellipse count; junctions = 2N(N-1)")
    ap.add_argument("--a", type=float, default=25.0, help="semi-major axis mm")
    ap.add_argument("--ratio", type=float, default=0.55, help="b/a — fatter prints faster")
    ap.add_argument("--origin", type=float, default=40.0)
    ap.add_argument("--layers", type=int, default=12)
    ap.add_argument("--layer_h", type=float, default=machine.BEAD_H)   # stacking ceiling
    ap.add_argument("--strand_w", type=float, default=machine.BEAD_W)  # stacking ceiling.
                    # Together these give the fattest bead a 0.8 nozzle can stack (0.72mm2),
                    # which is what lets max flow run at the SLOWEST possible speed: 111 mm/s
                    # instead of 235. Oleg wanted 5x slower at constant flow; 2.1x is the
                    # physical limit for stacked geometry, and going further would land the
                    # bead taller than the Z step and plough the part off the plate.
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--weld", type=float, default=1.0, help="1=fuse all (Phase 1 winner), 0=weave")
    ap.add_argument("--lift", type=float, default=0.5)
    ap.add_argument("--lift-win", type=float, default=12.0)
    ap.add_argument("--temp", type=int, default=230)
    ap.add_argument("--bed", type=int, default=60)
    ap.add_argument("--fan", type=int, default=0)
    ap.add_argument("--n-per", type=int, default=600, help="samples per ellipse")
    ap.add_argument("--first-slow", type=int, default=1,
                    help="layers slowed for adhesion — 0 by default: the whole print now runs\n                          at 50 mm/s, which IS a first-layer speed, so nothing needs slowing.\n                          Oleg: thick and irregular lines are good, always.")
    ap.add_argument("--first-frac", type=float, default=1.0, help="first-layer speed fraction")
    ap.add_argument("--first-squish", type=float, default=0.85, help="first-layer Z as a fraction")
    ap.add_argument("--vase", action="store_true",
                    help="one continuous extrusion, Z rising with path — no travels at all")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    g, st = emit(a.N, a.a, a.ratio, a.origin, a.layers, a.layer_h, a.strand_w, a.flow, a.weld,
                 a.lift, a.lift_win, a.temp, a.bed, a.fan, 1.75, not a.no_home, a.n_per,
                 a.first_slow, a.first_frac, a.first_squish, a.vase)
    os.makedirs(a.out, exist_ok=True)
    fn = (f"{a.out}/nucleon_{'nohome_' if a.no_home else ''}{'vase_' if a.vase else ''}"
          f"N{a.N}_weld{a.weld:g}_T{a.temp}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}\n  N={a.N} ({2*a.N*(a.N-1)} junctions/layer predicted, {st['junctions']} measured "
          f"over {a.layers} layers), {st['lifts']} lifts")
    print(f"  {st['speed']} mm/s (capped at {machine.MAX_SPEED:.0f}), flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g, {st['lines']} lines")
