#!/usr/bin/env python3
"""Z modulation during extrusion — Oleg's idea, 2026-07-25. Single layer, whole plate.

Slicers treat Z as a staircase: constant inside a layer, stepping between layers. Nothing about
the machine requires that — Z is just another axis in the same G1. Moving it *while extruding*
varies how hard the bead is squished along a single line, which changes its width, gloss and
adhesion continuously. There is no slicer setting for it.

    Z(x) = z0 + A * sin(2*pi*x / wavelength)

Each band up the plate is one AMPLITUDE (or one wavelength with --vary wavelength). Flow is held
constant throughout, so the only thing changing is squish. Run it at the working flow found by
flowtest.py — squish only has range when there is enough plastic to squash.

SAFETY, and it is the whole reason this is cheap to try:
  - Amplitude is capped at 0.6 * layer_h. Above that the nozzle lifts clear of the bed on the
    up-stroke, stops touching the bead, and drags a loose string instead of printing.
  - SINGLE LAYER. The 2026-07-25 tower failure was a stacking collision; nothing here stacks, so
    it cannot repeat.

HOW TO READ IT: run a fingertip across the rows, front to back.
  - Amplitude too low  -> feels flat, indistinguishable from a normal row.
  - Amplitude right    -> a regular ribbed texture you can feel; bead visibly widens and narrows.
  - Amplitude too high -> broken beads, strings, gaps where the nozzle lost contact.
Note the LAST band that still gives continuous plastic. That is the usable ceiling.

Usage:
  python3 zwave.py --no-home --flow 29            # sweep amplitude at 10mm wavelength
  python3 zwave.py --no-home --flow 29 --vary wavelength
"""
import argparse, math, os

BED = (350.0, 350.0)
# Amplitudes are DERIVED from the safety cap (0.6*layer_h), evenly spaced up to it. A fixed list
# got silently clipped — 0.25 and 0.30 both clamped to 0.24 and printed two identical bands, which
# is a wasted sixth of the plate. Deriving them guarantees a real spread whatever the layer height.
def amps_for(layer_h, n=6):
    cap = 0.6 * layer_h
    return [round(cap * (i + 1) / n, 3) for i in range(n)]
WAVES = [2.0, 4.0, 8.0, 16.0, 32.0, 64.0]       # mm per cycle


def emit(bands, vary, flow, layer_h, line_w, amp_fixed, wave_fixed, rows_per_band,
         temp, bed, fan, fil_d, home, margin, seg_per_wave):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (line_w * layer_h) / area
    speed = flow / (line_w * layer_h)
    f_mm_min = round(speed * 60)
    cap = 0.6 * layer_h
    x0, x1 = margin, BED[0] - margin
    n_rows = len(bands) * rows_per_band
    spacing = line_w
    span = (n_rows - 1) * spacing
    y0 = (BED[1] - span) / 2.0
    if y0 < margin:
        raise SystemExit(f"{n_rows} rows exceeds the plate — reduce --rows.")

    L = []; w = L.append
    w(f"; Z MODULATION — single layer, {len(bands)} bands x {rows_per_band} rows, vary={vary}")
    w(f"; flow={flow} mm3/s -> {speed:.0f} mm/s, line_w={line_w} layer_h={layer_h} fan={fan}")
    w(f"; amplitude cap {cap:.2f}mm (0.6 x layer_h) — above it the nozzle leaves the bead")
    for i, b in enumerate(bands, 1):
        a = min(b, cap) if vary == "amplitude" else min(amp_fixed, cap)
        wl = b if vary == "wavelength" else wave_fixed
        ya = y0 + (i - 1) * rows_per_band * spacing
        w(f"; band {i}: amp {a:.2f}mm  wavelength {wl:.0f}mm   Y {ya:.0f}.."
          f"{ya + (rows_per_band-1)*spacing:.0f}")
    w("; HEADER_BLOCK_START"); w("; total layer number: 1"); w("; HEADER_BLOCK_END")

    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — direct to print (fails safely if the machine lost home)")
    w(f"M190 S{bed}"); w(f"M109 S{temp}")
    w("M204 S8000"); w("M107" if not fan else f"M106 S{fan}")
    w("M82"); w("G92 E0")
    w(f"G1 Z{layer_h:.2f} F600")
    w(f"G0 F9000 X{margin:.1f} Y{margin:.1f}")
    w(f"G1 F1200 X{margin:.1f} Y{margin+80:.1f} E12"); w("G92 E0")

    e = 0.0; row = 0
    for i, b in enumerate(bands, 1):
        amp = min(b, cap) if vary == "amplitude" else min(amp_fixed, cap)
        wl = b if vary == "wavelength" else wave_fixed
        seg = wl / seg_per_wave
        L.append(f"; ---- band {i}: amp {amp:.2f}mm, wavelength {wl:.0f}mm ----")
        for _ in range(rows_per_band):
            y = y0 + row * spacing
            fwd = (row % 2 == 0)
            sx, ex = (x0, x1) if fwd else (x1, x0)
            if row == 0:
                L.append(f"G0 F9000 X{sx:.2f} Y{y:.2f}")
            else:
                e += spacing * e_per_mm
                L.append(f"G1 F{f_mm_min} X{sx:.2f} Y{y:.2f} E{e:.5f}")
            n_seg = max(2, int(round((x1 - x0) / seg)))
            for k in range(1, n_seg + 1):
                t = k / n_seg
                x = sx + (ex - sx) * t
                # phase on absolute X so the ridges line up across rows into a readable field
                z = layer_h + amp * math.sin(2 * math.pi * x / wl)
                d = abs(ex - sx) / n_seg
                e += d * e_per_mm
                L.append(f"G1 X{x:.3f} Z{z:.3f} E{e:.5f}")
            row += 1

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{layer_h+40:.1f} F900", "G0 X10 Y340 F9000"]
    grams = e * area * 1.24 / 1000
    secs = (n_rows * (x1 - x0) + n_rows * spacing) / speed
    return "\n".join(L) + "\n", dict(rows=n_rows, grams=round(grams, 1), mins=round(secs / 60, 1),
                                     lines=len(L), speed=round(speed))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--flow", type=float, required=True, help="working flow mm3/s (0.85 x measured max)")
    ap.add_argument("--vary", default="amplitude", choices=["amplitude", "wavelength"])
    ap.add_argument("--amp", type=float, default=0.20, help="fixed amplitude when varying wavelength")
    ap.add_argument("--wavelength", type=float, default=10.0, help="fixed wavelength when varying amplitude")
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--layer_h", type=float, default=0.4)
    ap.add_argument("--line_w", type=float, default=3.0)   # single layer: wide is safe
    ap.add_argument("--temp", type=int, default=230)
    ap.add_argument("--bed", type=int, default=60)
    ap.add_argument("--fan", type=int, default=51)
    ap.add_argument("--margin", type=float, default=15.0)
    ap.add_argument("--seg", type=int, default=12, help="segments per wave cycle")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    bands = amps_for(a.layer_h) if a.vary == "amplitude" else WAVES
    g, st = emit(bands, a.vary, a.flow, a.layer_h, a.line_w, a.amp, a.wavelength, a.rows,
                 a.temp, a.bed, a.fan, 1.75, not a.no_home, a.margin, a.seg)
    os.makedirs(a.out, exist_ok=True)
    fn = f"{a.out}/zwave_{'nohome_' if a.no_home else ''}{a.vary}_Q{a.flow:g}_T{a.temp}.gcode"
    open(fn, "w").write(g)
    cap = 0.6 * a.layer_h
    print(f"{fn}\n  ONE layer, {st['rows']} rows @ {st['speed']}mm/s, ~{st['mins']} min, "
          f"{st['grams']} g, {st['lines']} lines")
    print(f"  varying {a.vary}: " + ", ".join(
        f"{min(b,cap):.2f}mm" if a.vary == "amplitude" else f"{b:g}mm" for b in bands)
        + (f"   (capped at {cap:.2f})" if a.vary == "amplitude" and max(bands) > cap else ""))
