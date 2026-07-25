#!/usr/bin/env python3
"""WEAVE — lift the head over already-printed lines, then come back down. Oleg's idea, 2026-07-25.

    "i was more thinking of you will use z axis to move head up to cross over the print lines
     and then back down to the plate"

THE PHYSICAL FACT THIS IS BUILT ON. In a single layer, when a path crosses itself, the SECOND pass
has no choice: the first pass is already lying on the plate, so the second either lifts over it or
ploughs straight through it. There is no "under". The existing crackle coupon does the ploughing
version at ~35 crossings per layer, and I had been calling that "welding" without ever checking.

So lifting is not decoration, it is the missing CONTROL:
    stay down at a crossing -> the two strands fuse into one weld
    lift over the crossing  -> they interlace mechanically, over-under, like basketry
That is a direct dial on whether crossings weld — the exact mechanism the crackle thesis rests on,
and previously only reachable indirectly through fan and temperature.

    --weld 1.0  every crossing fused      (what the coupon does today)
    --weld 0.0  every crossing woven      (nothing fuses; pure mechanical interlock)
    --weld 0.5  half and half

WHY THIS NEEDS THE CROSSING DETECTOR. You cannot lift reactively — the head must already be rising
before it reaches the bead. So every self-intersection has to be found and located along the path
BEFORE emitting a line of gcode. That is what pathstats.py is for.

WHY A SMOOTH CURVE. A Lissajous figure crosses itself many times, has no corners to decelerate into,
and its crossing count is dialled by the frequency pair. Straight chords between pillars would put a
sharp direction change at every anchor, which varies the bead exactly where we are trying to control
it.

Z FEASIBILITY is checked, not assumed: each lift is a raised-cosine bump of height `lift` over a
window of `lift_win` mm of path, so peak Z velocity is ~pi*lift*speed/(2*lift_win) and peak Z accel
scales as speed^2. The K2 Plus allows 30 mm/s and 1000 mm/s2. Exceed it and Klipper does not error —
it slows the move, which changes extruded width and silently confounds the result.

Usage:
  python3 weave.py --no-home --flow 40 --weld 0.0     # fully woven
  python3 weave.py --no-home --flow 40 --weld 1.0     # fully fused (today's behaviour)
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathstats import crossings as find_crossings

MAX_Z_V, MAX_Z_A = 30.0, 1000.0


def lissajous(a, b, size, cx, cy, n, phase):
    R = size / 2.0
    return [(cx + R * math.sin(a * 2 * math.pi * i / n + phase),
             cy + R * math.sin(b * 2 * math.pi * i / n)) for i in range(n + 1)]


def emit(a_f, b_f, size, origin, layers, layer_h, line_w, strand_w, flow, weld, lift, lift_win,
         temp, bed, fan, fil_d, home, samples):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (strand_w * layer_h) / area
    speed = flow / (strand_w * layer_h)
    f_mm_min = round(speed * 60)

    # Z demand of one raised-cosine lift, as a function of path speed
    vz = math.pi * lift * speed / (2 * lift_win)
    az = (math.pi ** 2) * lift * speed ** 2 / (2 * lift_win ** 2)
    if vz > MAX_Z_V or az > MAX_Z_A:
        need = speed * math.pi * math.sqrt(lift / (2 * MAX_Z_A))
        raise SystemExit(
            f"Z cannot follow the lift: v_peak {vz:.1f} mm/s (limit {MAX_Z_V}), "
            f"a_peak {az:.0f} mm/s2 (limit {MAX_Z_A}).\n"
            f"  At {speed:.0f} mm/s a {lift}mm lift needs a window of at least {need:.1f}mm "
            f"(--lift-win {math.ceil(need)}), or drop --flow.\n"
            f"  Klipper would not error; it would slow the move and change the bead width.")

    cx = cy = origin + size / 2.0
    L = []; w = L.append
    w(f"; WEAVE — lift over printed lines. lissajous {a_f}:{b_f}, weld fraction {weld}")
    w(f"; flow={flow} -> {speed:.0f} mm/s, strand_w={strand_w} layer_h={layer_h} lift={lift}")
    w(f"; Z demand per lift: v {vz:.1f} mm/s, a {az:.0f} mm/s2 (limits {MAX_Z_V}/{MAX_Z_A})")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {layers}"); w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — direct to print (fails safely if the machine lost home)")
    w(f"M190 S{bed}"); w(f"M109 S{temp}")
    w("M204 S8000"); w("M107" if not fan else f"M106 S{fan}")
    w("M82"); w("G92 E0")
    w(f"G1 Z{layer_h:.2f} F600")
    w(f"G0 F9000 X{origin:.1f} Y{origin-8:.1f}")
    w(f"G1 F1200 X{origin+60:.1f} Y{origin-8:.1f} E10"); w("G92 E0")

    L.append("; BODY_START")
    e = 0.0
    stats = dict(cross=0, lifts=0)
    for layer in range(layers):
        z0 = layer_h * (layer + 1)
        phase = (math.pi / 3.0) * layer          # rotate the figure so crossings do not stack
        pts = lissajous(a_f, b_f, size, cx, cy, samples, phase)

        hits, _ = find_crossings(pts)
        # path distance to each sample
        cum = [0.0]
        for i in range(len(pts) - 1):
            cum.append(cum[-1] + math.dist(pts[i], pts[i + 1]))

        # Each crossing is visited TWICE. The first visit lies on the plate; the SECOND must lift,
        # because there is no "under" once plastic is down. weld<1 means we let some second visits
        # stay down and fuse instead — that is the dial.
        second_visits = []
        for k, (i, j, x, y) in enumerate(sorted(hits, key=lambda h: max(h[0], h[1]))):
            stats['cross'] += 1
            if (k % 100) >= weld * 100:          # deterministic: no RNG, reproducible coupons
                second_visits.append(cum[max(i, j)])
                stats['lifts'] += 1

        L.append(f"; layer {layer+1}  z{z0:.2f}  crossings {len(hits)}  lifts {len(second_visits)}")
        L.append(f"G0 F9000 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
        L.append(f"G1 F600 Z{z0:.3f}")
        for i in range(1, len(pts)):
            s = cum[i]
            dz = 0.0
            for sv in second_visits:
                d = s - sv
                if abs(d) < lift_win:
                    dz = max(dz, lift * math.cos(math.pi * d / (2 * lift_win)) ** 2)
            seg = math.dist(pts[i - 1], pts[i])
            e += seg * e_per_mm
            L.append(f"G1 {'F%d ' % f_mm_min if i == 1 else ''}X{pts[i][0]:.3f} "
                     f"Y{pts[i][1]:.3f} Z{z0+dz:.4f} E{e:.5f}")

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{layer_h*layers+40:.1f} F900", "G0 X10 Y340 F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(grams=round(grams, 2), lines=len(L), speed=round(speed),
                                     path=round(e / e_per_mm / 1000, 1), **stats)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--flow", type=float, default=40.0, help="mm3/s (keep well under the 81 ceiling)")
    ap.add_argument("--weld", type=float, default=0.0, help="0=all woven, 1=all fused")
    ap.add_argument("--a", type=int, default=5)
    ap.add_argument("--b", type=int, default=7)
    ap.add_argument("--size", type=float, default=60.0)
    ap.add_argument("--origin", type=float, default=40.0)
    ap.add_argument("--layers", type=int, default=10)
    ap.add_argument("--layer_h", type=float, default=0.4)
    ap.add_argument("--line_w", type=float, default=0.9)
    ap.add_argument("--strand_w", type=float, default=0.5)
    ap.add_argument("--lift", type=float, default=0.5, help="mm to clear the bead below")
    ap.add_argument("--lift-win", type=float, default=6.0, help="mm of path to rise and fall over")
    ap.add_argument("--temp", type=int, default=230)
    ap.add_argument("--bed", type=int, default=60)
    ap.add_argument("--fan", type=int, default=0)
    ap.add_argument("--samples", type=int, default=1500)
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    g, st = emit(a.a, a.b, a.size, a.origin, a.layers, a.layer_h, a.line_w, a.strand_w, a.flow,
                 a.weld, a.lift, a.lift_win, a.temp, a.bed, a.fan, 1.75, not a.no_home, a.samples)
    os.makedirs(a.out, exist_ok=True)
    fn = (f"{a.out}/weave_{'nohome_' if a.no_home else ''}{a.a}x{a.b}_weld{a.weld:g}"
          f"_T{a.temp}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}\n  {a.layers} layers, {st['cross']} crossings total, {st['lifts']} lifts "
          f"({100*st['lifts']/max(st['cross'],1):.0f}% woven), {st['speed']} mm/s")
    print(f"  {st['path']} m path, {st['grams']} g, {st['lines']} lines")
