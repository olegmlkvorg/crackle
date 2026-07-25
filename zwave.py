#!/usr/bin/env python3
"""Z modulation during extrusion — Oleg's idea, 2026-07-25. Single layer, spiral, whole plate.

Slicers treat Z as a staircase: constant inside a layer, stepping between layers. Nothing about the
machine requires that — Z is just another axis in the same G1. Moving it *while extruding* varies
how hard the bead is squished along a single line, changing its width, gloss and adhesion
continuously. There is no slicer setting for this.

    Z(s) = z0 + A * sin(2*pi*s / wavelength)      s = distance travelled along the path

SPIRAL, not rows. A serpentine reverses 180 degrees at each row end, so the head decelerates there —
and decelerating changes squish, which is the very thing being measured. Every row would carry a
false artifact at both ends. A spiral has no ends.

AMPLITUDE RAMPS OUTWARD, continuously, from 0 at the centre to the cap at the rim. So the plate is
one uninterrupted gradient from "flat" to "too much" and you find the transition by touch rather
than by comparing discrete bands. A pimple marks every 0.02mm step, all at the same polar angle, so
they line up into a radial spoke — count outward.

BED 60, deliberately NOT the 135 used for the flow test. Opposite requirement: the flow sheet wanted
maximum adhesion and did not care about shape, but this test IS shape. At 135 PLA stays far above
its glass transition and the ridges slump flat while still hot, erasing the signal. Ridges have to
freeze where they are laid.

SAFETY, and it is why this is cheap to try:
  - Amplitude capped at 0.6 * layer_h. Above it the nozzle lifts clear on the up-stroke, stops
    touching the bead, and drags a string instead of printing.
  - SINGLE LAYER. The 2026-07-25 tower failure was a stacking collision; nothing here stacks.

HOW TO READ IT: run a fingertip from the centre outward.
  - too low  -> smooth, indistinguishable from a normal surface
  - right    -> a regular ribbed texture you can feel; bead visibly widens and narrows
  - too high -> broken beads, strings, gaps where the nozzle lost contact
Note the radius where it starts to feel ribbed, and where it breaks up. Count pimples to convert.

Usage:
  python3 zwave.py --no-home --flow 70.5
  python3 zwave.py --no-home --flow 70.5 --wavelength 4 --amp-max 0.24
"""
import argparse, math, os

BED = (350.0, 350.0)


def emit(flow, layer_h, line_w, wavelength, amp_max, temp, bed, fan, fil_d, home, margin,
         r0, seg_len, bump_h, bump_arc, bump_every, spacing_mm):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (line_w * layer_h) / area
    speed = flow / (line_w * layer_h)
    f_mm_min = round(speed * 60)
    # Amplitude cap has TWO jobs and the old 0.6*layer_h only did one of them.
    #   UP-stroke:   above ~0.6*layer_h the nozzle leaves the bead and drags a string.
    #   DOWN-stroke: layer_h - amp is how close the nozzle gets to the PLATE. At layer_h 0.3 the
    #                old cap gave 0.12mm, and bed levelling alone varies +-0.05 — that scrapes.
    # So keep a hard 0.15mm floor under the down-stroke as well. Caught by validate.py once it
    # was actually checking these files (2026-07-25).
    Z_FLOOR = 0.15
    cap = min(0.6 * layer_h, layer_h - Z_FLOOR)
    if cap <= 0:
        raise SystemExit(f"layer_h {layer_h} leaves no room above the {Z_FLOOR}mm plate floor")
    amp_hi = min(amp_max, cap)
    cx, cy = BED[0] / 2, BED[1] / 2
    r_max = min(cx, cy) - margin
    b = (spacing_mm or line_w) / (2 * math.pi)
    th_max = (r_max - r0) / b

    def amp_at_r(r):
        return amp_hi * (r - r0) / (r_max - r0)

    marks = []
    a = bump_every
    while a < amp_hi - 1e-9:
        r_m = r0 + (a / amp_hi) * (r_max - r0)
        marks.append((a, math.ceil(((r_m - r0) / b) / (2 * math.pi)) * 2 * math.pi))
        a += bump_every

    L = []; w = L.append
    w(f"; Z MODULATION — single layer spiral, amplitude 0 -> {amp_hi:.3f}mm outward")
    w(f"; flow={flow} mm3/s -> {speed:.0f} mm/s, line_w={line_w} layer_h={layer_h} bed={bed} fan={fan}")
    w(f"; wavelength {wavelength}mm along the path; amplitude cap {cap:.3f}mm (0.6 x layer_h)")
    for ma, mth in marks:
        w(f";   pimple amp {ma:.2f}mm at r{r0 + b*mth:.0f}mm")
    w("; HEADER_BLOCK_START"); w("; total layer number: 1"); w("; HEADER_BLOCK_END")

    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — direct to print (fails safely if the machine lost home)")
    w(f"M190 S{bed}"); w(f"M109 S{temp}")
    w("M204 S8000"); w("M107" if not fan else f"M106 S{fan}")
    w("M82"); w("G92 E0")
    w(f"G1 Z{layer_h:.2f} F600")
    w(f"G0 F9000 X{margin:.1f} Y{margin:.1f}")
    w(f"G1 F1200 X{margin:.1f} Y{margin+80:.1f} E12"); w("G92 E0")

    L.append("; Z_MODULATED")
    L.append("; BODY_START")
    e = 0.0; th = 0.0; s = 0.0
    px, py = cx + r0, cy
    L.append(f"G0 F9000 X{px:.3f} Y{py:.3f}")
    first = True
    while th < th_max:
        r_base = r0 + b * th
        th += min(seg_len / max(r_base, 1.0), 0.25)
        r_base = r0 + b * th
        dr = 0.0
        for ma, mth in marks:
            d = th - mth
            if abs(d) < bump_arc:
                dr = bump_h * math.cos(math.pi * d / (2 * bump_arc)) ** 2
                break
        r = r_base + dr
        x, y = cx + r * math.cos(th), cy + r * math.sin(th)
        d_mm = math.dist((px, py), (x, y))
        s += d_mm
        e += d_mm * e_per_mm
        z = layer_h + amp_at_r(r_base) * math.sin(2 * math.pi * s / wavelength)
        L.append(f"G1 {'F%d ' % f_mm_min if first else ''}X{x:.3f} Y{y:.3f} Z{z:.4f} E{e:.5f}")
        first = False
        px, py = x, y

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{layer_h+40:.1f} F900", "G0 X10 Y340 F9000"]
    grams = e * area * 1.24 / 1000
    path = e / e_per_mm
    return "\n".join(L) + "\n", dict(turns=round(th_max / (2 * math.pi)), grams=round(grams, 1),
                                     mins=round(path / speed / 60, 1), path=round(path / 1000, 1),
                                     lines=len(L), amp_hi=amp_hi, r_max=r_max,
                                     marks=[m for m, _ in marks])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--flow", type=float, required=True, help="working flow mm3/s (0.85 x measured max)")
    ap.add_argument("--wavelength", type=float, default=10.0, help="mm of path per cycle")
    ap.add_argument("--amp-max", type=float, default=1.0, help="target rim amplitude (capped)")
    ap.add_argument("--layer_h", type=float, default=0.4)
    ap.add_argument("--line_w", type=float, default=3.0)
    ap.add_argument("--temp", type=int, default=230)
    ap.add_argument("--bed", type=int, default=60, help="LOW on purpose — ridges must freeze")
    ap.add_argument("--fan", type=int, default=128, help="50% — this test wants the shape to set")
    ap.add_argument("--margin", type=float, default=15.0)
    ap.add_argument("--r0", type=float, default=25.0)
    ap.add_argument("--seg", type=float, default=1.0, help="segment mm — must be << wavelength")
    ap.add_argument("--bump", type=float, default=1.0)
    ap.add_argument("--bump-arc", type=float, default=0.12)
    ap.add_argument("--bump-every", type=float, default=0.02, help="mm of amplitude between pimples")
    ap.add_argument("--spacing", type=float, default=None,
                    help="turn spacing mm; lines OVERLAP when < the landed bead width")
    ap.add_argument("--overlap", type=float, default=1.10,
                    help="material multiple vs spacing (1.10 = 10%% squeeze)")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    if a.spacing:
        # Conservation, not preference: material per unit AREA is line_w*layer_h/spacing. Move the
        # turns closer without narrowing the line and you deposit more height than the Z step,
        # the nozzle ploughs, and you repeat the 2026-07-25 tower failure. So --spacing DERIVES
        # line_w unless one was passed explicitly.
        if a.line_w in (3.0,):
            a.line_w = round(a.spacing * a.overlap, 3)
    # Z-AXIS FEASIBILITY. A sine of amplitude A at frequency f = speed/wavelength demands
    # v_peak = 2*pi*f*A and a_peak = (2*pi*f)^2*A from the Z gantry. Exceed it and Klipper does NOT
    # error — it slows the move to obey the Z limit, which changes XY speed, which changes extruded
    # width, which silently confounds the very thing being measured. K2 Plus: max_z_velocity 30,
    # max_z_accel 1000. Held to 40% of the accel limit so the planner never has to intervene.
    _speed = a.flow / (a.line_w * a.layer_h)
    _amp = min(a.amp_max, 0.6 * a.layer_h, a.layer_h - 0.15)
    _f = _speed / a.wavelength
    _vz = 2 * math.pi * _f * _amp
    _az = (2 * math.pi * _f) ** 2 * _amp
    if _vz > 30.0 or _az > 400.0:
        _wl = 2 * math.pi * math.sqrt(_amp / 400.0) * _speed
        raise SystemExit(
            f"Z cannot follow this sine: {_f:.1f} Hz demands v_peak {_vz:.1f} mm/s "
            f"(limit 30) and a_peak {_az:.0f} mm/s2 (budget 400 of 1000).\n"
            f"  At {_speed:.0f} mm/s the shortest safe wavelength is {_wl:.0f} mm — pass "
            f"--wavelength {math.ceil(_wl)} or slow the flow.\n"
            f"  Klipper would not error here; it would quietly slow the move and change the "
            f"extrusion width, confounding the measurement.")
    if a.seg > a.wavelength / 6:
        raise SystemExit(f"--seg {a.seg} is too coarse for wavelength {a.wavelength}: the sine would "
                         f"be sampled under 6x per cycle and come out as a jagged triangle, not a "
                         f"wave. Use --seg <= {a.wavelength/6:.2f}.")
    g, st = emit(a.flow, a.layer_h, a.line_w, a.wavelength, a.amp_max, a.temp, a.bed, a.fan, 1.75,
                 not a.no_home, a.margin, a.r0, a.seg, a.bump, a.bump_arc, a.bump_every, a.spacing)
    os.makedirs(a.out, exist_ok=True)
    fn = f"{a.out}/zspiral_{'nohome_' if a.no_home else ''}Q{a.flow:g}_w{a.wavelength:g}_T{a.temp}.gcode"
    open(fn, "w").write(g)
    print(f"{fn}\n  ONE layer spiral, {st['turns']} turns to r{st['r_max']:.0f}mm, {st['path']} m, "
          f"~{st['mins']} min, {st['grams']} g, {st['lines']} lines")
    print(f"  amplitude 0 -> {st['amp_hi']:.3f}mm outward, wavelength {a.wavelength}mm, "
          f"bed {a.bed}C fan {round(a.fan/255*100)}%")
    print(f"  pimple spoke every {a.bump_every}mm: {len(st['marks'])} marks")
