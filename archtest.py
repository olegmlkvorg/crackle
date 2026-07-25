#!/usr/bin/env python3
"""ARCH TEST — how big an arc can the plastic actually hold? Oleg, 2026-07-25:
"we first will have to find out empirically how big arcs we can produce".

The Z axis will happily move 2.5mm in a 3mm window. That says nothing about whether the STRAND
survives: it leaves the surface, spans a gap in mid-air, and lands. Too tall or too long and it
sags, thins, or snaps. That is a material limit, and only the plate can report it.

GEOMETRY: one continuous spiral (no travels, no corners — the same base the flow tests use), single
layer, with an ARC every `pitch` mm of path. Arc height ramps linearly outward, so the plate is a
ladder of arcs from barely-there to as tall as the axis allows.

    arc height  = ramp from a_lo at the centre to a_hi at the rim
    arc span    = 2 * win  (the horizontal distance the strand is airborne)

READ IT: run a fingernail outward along the spiral.
  · too small  -> a bump you can feel but not see
  · working    -> a clean raised loop, plastic continuous over the top
  · too big    -> the top thins, then breaks; the strand lands as two stubs with a gap
Note the radius where the tops first break. That is the empirical arc ceiling, and it will be
BELOW what the axis permits.

MAX COOLING throughout: an arc that does not freeze in flight sags into a droop and the test
measures the fan instead of the geometry.
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine


def win_for(amp, speed, aspect):
    """Half-span for a hoop of height `amp`, respecting the Z axis at both ends of the ladder.

    A hoop should scale as ONE thing — height and span together — so "hoop size" is a single
    variable and a failure is unambiguous. But pure proportional scaling breaks at the small end:
    acceleration goes as amp/win^2, so a short narrow hoop demands MORE acceleration than a tall
    wide one. The span is therefore the larger of the proportional span and the accel-safe minimum.
    """
    prop = aspect * amp
    a_min = math.sqrt((math.pi ** 2) * amp * speed ** 2 / (2 * machine.MAX_Z_A))
    v_min = math.pi * amp * speed / (2 * machine.MAX_Z_V)
    return max(prop, a_min, v_min)


def emit(a_lo, a_hi, aspect, pitch, flow, line_w, layer_h, temp, bed, fil_d, r0, margin,
         bed_xy, home, spacing, fan):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (line_w * layer_h) / area
    speed = flow / (line_w * layer_h)
    f_mm_min = round(speed * 60)
    cx, cy = bed_xy[0] / 2, bed_xy[1] / 2
    r_max = min(cx, cy) - margin
    b = spacing / (2 * math.pi)         # solid base: spacing under the landed width
    th_max = (r_max - r0) / b

    win_hi = win_for(a_hi, speed, aspect)
    if 2 * win_hi > pitch * 0.8:
        raise SystemExit(f"largest hoop spans {2*win_hi:.1f}mm against a {pitch}mm pitch — hoops "
                         f"would merge into a wave instead of standing separately.\n"
                         f"  Raise --pitch above {2*win_hi/0.8:.0f}.")

    L = []; w = L.append
    w(f"; ARCH TEST — arcs every {pitch}mm of path, height {a_lo} -> {a_hi}mm outward")
    w(f"; span scales with height (aspect {aspect}); largest hoop {2*win_hi:.1f}mm airborne")
    w(f"; flow={flow} at {speed:.0f} mm/s, line {line_w}x{layer_h}, base spacing {spacing}")
    w(f"; hoops every {pitch}mm of path, base spacing {spacing}mm (< 1.53 landed = solid)")
    w("; HEADER_BLOCK_START"); w("; total layer number: 1"); w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — direct to print (fails safely if the machine lost home)")
    w(f"M190 S{bed}"); w(f"M109 S{temp}")
    w("M204 S8000")
    # FANS OFF while the base bonds, then low. Max cooling froze the arcs beautifully and detached
    # the part at 46% (2026-07-25) — and adhesion is the PREREQUISITE for measuring anything, since
    # a part that lifts reports the fan rather than the hoop. Oleg: "also fans off. 20%".
    # Trade-off, stated: less cooling means the hoop tops droop more, so this reads as a
    # CONSERVATIVE height ceiling. Raise it once the height is known.
    w("M107                            ; fans off while the base bonds")
    w("M82"); w("G92 E0")
    _sx, _sy = cx + r0, cy
    w(f"G1 Z{layer_h:.2f} F600")
    w(f"G0 F9000 X{_sx - 60:.3f} Y{_sy:.3f}")
    w(f"G1 F1200 X{_sx:.3f} Y{_sy:.3f} E12"); w("G92 E0")
    w("; Z_MODULATED"); w("; BODY_START")

    # walk the spiral in small steps; arcs are placed by PATH DISTANCE so they stay evenly spaced
    seg = min(win_for(a_lo, speed, aspect) / 8.0, 0.6)
    e = 0.0; th = 0.0; s = 0.0
    px, py = _sx, _sy
    next_arc = pitch
    arcs = []
    fan_on = False
    fan_after = 2 * math.pi * r0   # one full turn of base before any cooling
    while th < th_max:
        r = r0 + b * th
        th += seg / max(r, 1.0)
        r = r0 + b * th
        x, y = cx + r * math.cos(th), cy + r * math.sin(th)
        d = math.dist((px, py), (x, y)); s += d
        amp = a_lo + (a_hi - a_lo) * (r - r0) / (r_max - r0)
        win = win_for(amp, speed, aspect)
        dz = 0.0
        if s > next_arc - win:
            off = s - next_arc
            if abs(off) < win:
                dz = amp * math.cos(math.pi * off / (2 * win)) ** 2
            elif off >= win:
                arcs.append((round(amp, 2), round(r)))
                next_arc += pitch
        if fan and not fan_on and s > fan_after:
            L.append(f"M106 S{fan}                        ; {round(fan/255*100)}% once the base has bonded")
            fan_on = True
        e += d * e_per_mm
        L.append(f"G1 {'F%d ' % f_mm_min if not arcs and s < 1 else ''}"
                 f"X{x:.3f} Y{y:.3f} Z{layer_h + dz:.4f} E{e:.5f}")
        px, py = x, y

    L += ["M107", "SET_PIN PIN=fan1 VALUE=0", "SET_PIN PIN=fan2 VALUE=0",
          "M104 S0", "M140 S0", f"G1 Z{layer_h + 40:.1f} F900",
          f"G0 X10 Y{bed_xy[1] - 10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(arcs=len(arcs), grams=round(grams, 1), speed=round(speed),
                                     mins=round(s / speed / 60, 1), path=round(s / 1000, 1),
                                     sample=arcs[::max(1, len(arcs)//8)] if arcs else [])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-lo", type=float, default=0.3)
    ap.add_argument("--a-hi", type=float, default=4.0)
    ap.add_argument("--aspect", type=float, default=1.6,
                    help="half-span / height. Hoop scales as ONE variable; the span is\n                          raised where the Z axis needs it at the small end.")
    ap.add_argument("--pitch", type=float, default=25.0, help="mm of path between arcs")
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--line_w", type=float, default=2.0)
    ap.add_argument("--spacing", type=float, default=1.4,
                    help="turn spacing — 1.4 < the 1.53mm landed width, so the base is a\n                          SOLID surface for hoops to launch from and land on")
    ap.add_argument("--layer_h", type=float, default=1.2)
    ap.add_argument("--temp", type=int, default=machine.TEMP)
    ap.add_argument("--bed", type=int, default=95)
    ap.add_argument("--fan", type=int, default=51, help="20%% — off entirely for the first turn")
    ap.add_argument("--r0", type=float, default=25.0)
    ap.add_argument("--margin", type=float, default=75.0)
    ap.add_argument("--bed-size", default="350,350")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    bed_xy = tuple(float(v) for v in a.bed_size.split(","))
    g, st = emit(a.a_lo, a.a_hi, a.aspect, a.pitch, a.flow, a.line_w, a.layer_h, a.temp,
                 a.bed, 1.75, a.r0, a.margin, bed_xy, not a.no_home, a.spacing, a.fan)
    os.makedirs(a.out, exist_ok=True)
    fn = f"{a.out}/hooptest_{a.a_lo:g}-{a.a_hi:g}mm_T{a.temp}.gcode"
    open(fn, "w").write(g)
    print(f"{fn}\n  {st['arcs']} hoops, {a.a_lo}->{a.a_hi}mm tall, span scales with height")
    print(f"  {st['speed']} mm/s, {st['path']} m path, ~{st['mins']} min, {st['grams']} g")
    print(f"  height at radius: {', '.join(f'{h}mm@r{r}' for h,r in st['sample'])}")
