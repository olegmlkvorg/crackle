#!/usr/bin/env python3
"""Max volumetric flow test — find the real melt-rate ceiling of THIS nozzle + THIS filament.

Volumetric flow Q (mm3/s) = line_width x layer_height x speed. To push Q you push speed. The hotend
can only melt so fast; past that it under-extrudes no matter what the slicer claims.

This prints a single-wall square tower in bands. Each band is a fixed number of layers at ONE
volumetric rate, stepping up as it climbs. You read it with your eyes and fingers:

    bottom band = lowest flow ... top band = highest
    The band where walls go THIN, GAPPY, MATTE or start missing = you have passed the ceiling.
    Your max STABLE flow is the last good band below it. Use ~85-90% of it as a working number.

Why a tower and not a slicer test: same reason as the crackle work — the thing being controlled is
motion, so emit motion. It also means the number comes out in the same units the crackle generator
consumes.

Usage:
  python3 flowtest.py                          # PLA default ladder 5..26 mm3/s
  python3 flowtest.py --flows 8,12,16,20,24,28 --temp 240
  python3 flowtest.py --material petg          # sensible temp/flow defaults
"""
import argparse, math, os

MATERIALS = {   # sane starting ladders; the point is to find the truth, not trust these
    "pla":  dict(temp=230, bed=60,  flows=[10, 16, 22, 28, 34, 40, 46, 52]),  # 0.8 nozzle range
    "petg": dict(temp=245, bed=80,  flows=[5, 8, 11, 14, 17, 20, 23, 26]),
    "tpu":  dict(temp=230, bed=50,  flows=[2, 3, 4, 5, 6, 8, 10, 12]),
    "abs":  dict(temp=255, bed=100, flows=[6, 9, 12, 15, 18, 21, 24, 27]),
}

def emit(size, layer_h, line_w, flows, band_layers, temp, bed, fan, origin, fil_d, fast, home=True):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (line_w * layer_h) / area
    L = []
    w = L.append
    w(f"; MAX VOLUMETRIC FLOW TEST — {len(flows)} bands x {band_layers} layers")
    w(f"; line_w={line_w} layer_h={layer_h} temp={temp} fan={fan}")
    w("; READ IT: bottom band = lowest flow. First band that goes thin/gappy/matte = past the ceiling.")
    for i, q in enumerate(flows, 1):
        v = q / (line_w * layer_h)               # mm/s needed for this volumetric rate
        z0 = round(i * band_layers * layer_h, 2)
        w(f"; band {i}: {q} mm3/s  -> {v:.0f} mm/s  (top of band at Z{z0})")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {len(flows)*band_layers}"); w("; HEADER_BLOCK_END")
    if fast:
        w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
        if home: w("G28")
        else: w("; NO HOME — direct to print (errors safely if the machine lost its homed position)")
        w(f"M190 S{bed}"); w(f"M109 S{temp}")
        w("M204 S8000")                          # high accel: short sides otherwise never reach speed
        w("M83"); w("G1 Z0.3 F600")
        w("G1 X10 Y10 F9000"); w("G1 X90 Y10 E9 F1200"); w("G92 E0"); w("G1 Z1 F600")
    else:
        w(f"M140 S{bed}"); w(f"M104 S{temp}")
        w(f"START_PRINT EXTRUDER_TEMP={temp} BED_TEMP={bed}"); w("T0"); w(f"M109 S{temp}")
        w("M204 S8000"); w("M83"); w("G92 E0")
    w("M107" if not fan else f"M106 S{fan}")
    w("M82"); w("G92 E0")

    x0, y0 = origin, origin
    pts = [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]
    e = 0.0; z = 0.0; layer = 0
    # a couple of slow adhesion layers first — a tower that detaches teaches nothing
    for _ in range(2):
        z = round(z + layer_h, 3); layer += 1
        L.append(f"G0 Z{z:.3f}")
        L.append(f"G0 F6000 X{pts[0][0]:.2f} Y{pts[0][1]:.2f}")
        for k in range(4):
            a, b = pts[k], pts[(k + 1) % 4]
            d = math.dist(a, b); e += d * e_per_mm
            L.append(f"G1 F900 X{b[0]:.2f} Y{b[1]:.2f} E{e:.5f}")
    for i, q in enumerate(flows, 1):
        v = q / (line_w * layer_h)
        f_mm_min = round(v * 60)
        L.append(f"; ---- band {i}: {q} mm3/s @ {v:.0f} mm/s ----")
        for _ in range(band_layers):
            z = round(z + layer_h, 3); layer += 1
            L.append(f"G0 Z{z:.3f}")
            for k in range(4):
                a, b = pts[k], pts[(k + 1) % 4]
                d = math.dist(a, b); e += d * e_per_mm
                L.append(f"G1 F{f_mm_min} X{b[0]:.2f} Y{b[1]:.2f} E{e:.5f}")
    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{z+30:.1f} F900", "G1 X10 Y330 F9000"]  # steppers stay on
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", {"layers": layer, "grams": round(grams, 2), "z": z}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--material", default="pla", choices=list(MATERIALS))
    ap.add_argument("--flows", default=None, help="comma list of mm3/s, e.g. 8,12,16,20,24")
    ap.add_argument("--temp", type=int, default=None)
    ap.add_argument("--size", type=float, default=60.0)
    ap.add_argument("--layer_h", type=float, default=0.4)   # 0.8 nozzle: ~50% of orifice
    ap.add_argument("--line_w", type=float, default=0.9)   # 0.8 nozzle: never narrower than the orifice
    ap.add_argument("--band_layers", type=int, default=6)
    ap.add_argument("--fan", type=int, default=255)   # flow test WANTS cooling (unlike crackle)
    ap.add_argument("--origin", type=float, default=100.0)
    ap.add_argument("--fast", action="store_true", default=True)
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    m = MATERIALS[a.material]
    flows = [float(x) for x in a.flows.split(",")] if a.flows else m["flows"]
    temp = a.temp or m["temp"]
    g, st = emit(a.size, a.layer_h, a.line_w, flows, a.band_layers, temp, m["bed"], a.fan,
                 a.origin, 1.75, a.fast, not a.no_home)
    os.makedirs(a.out, exist_ok=True)
    fn = f"{a.out}/flowtest_{'nohome_' if a.no_home else ''}{a.material}_T{temp}_{int(min(flows))}-{int(max(flows))}.gcode"
    open(fn, "w").write(g)
    speeds = [f"{q:g}→{q/(a.line_w*a.layer_h):.0f}mm/s" for q in flows]
    print(f"{fn}\n  {len(flows)} bands x {a.band_layers} layers, {st['layers']} layers, {st['z']}mm tall, {st['grams']} g")
    print("  " + "  ".join(speeds))
