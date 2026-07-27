#!/usr/bin/env python3
"""LAP-WELD COUPON — does a tall, barely-squished layer still weld?

The fast-walls ideation converged on one lever (guides/fast-walls.md): three of four winning
wall concepts get their speed from TALLER LAYERS (0.9-1.2mm), all at 100% flow — and all hang
on the same unproven weld. This plate answers it for the whole family at once.

Three vase-mode rings d40, printed ONE AT A TIME (lifted hops between), left to right:

    ring 1  lh 0.6  bead 2.00   the control — the proven house weld (37% squish)
    ring 2  lh 0.9  bead 1.33   23% squish
    ring 3  lh 1.2  bead 1.00   ZERO nozzle squish: the layer is taller than the 0.8 nozzle,
                                the strand lands as a free bead — nothing like it printed here

Every ring runs the SAME 60 mm3/s at the 50 north star (bead = flow/(speed*lh)) — R8 clean,
no derate anywhere. The knob is geometry, not rate.

THE TEST, by hand when cool: try to split each ring along a lap weld (thumbs inside, pry).
The control sets the feel; if 0.9 and/or 1.2 feel the same, the tall-lap wall (51% material,
0.54x time) is unlocked. If 1.2 delaminates and 0.9 holds, the plain 1.2x0.9 wall (60%/66%)
is the winner. If both split, walls stay at 0.6 and the openwork families carry the burden.
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia", type=float, default=40.0)
    ap.add_argument("--height", type=float, default=21.7)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    flow = machine.flow_cap(a.material, a.printer)
    speed = machine.DEFAULT_SPEED
    temp = machine.temp_for(a.material)
    bx, by = machine.BED[a.printer]
    r = a.dia / 2.0
    CONFIGS = [(0.6,), (0.9,), (1.2,)]
    xs = [bx/2 - 60, bx/2, bx/2 + 60]
    cy = by / 2.0

    A = math.pi * (1.75/2)**2
    f = round(speed * 60)
    seg = max(0.25, speed / 250.0)
    n_lap = max(64, int(2*math.pi*r / seg))
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)

    L = []; w = L.append
    w(f"; MATERIAL={a.material}")
    w("; LAYER_H=0.6")                     # the CONTROL's ladder; taller rings declare ARCH
    w(f"; FLOW={flow:.4f}")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w("; SEQUENTIAL=3 lap-weld coupons, lifted hops between")
    w("; ARGV: " + " ".join(sys.argv))
    w("; lap-weld coupons: lh/bead 0.6/2.00 | 0.9/1.33 | 1.2/1.00 — same 60 mm3/s everywhere")
    w("; ARCH_LIFT=1.200")                 # rings 2-3 step taller than the declared control lh
    w("; HEADER_BLOCK_START"); w("; total layer number: 36"); w("; HEADER_BLOCK_END")
    w("M82")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M104 S{temp}")
    w("G28")
    w(f"M190 S{machine.bed_start(a.material, machine.bed_for(a.material, a.printer)):.0f}")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M109 S{temp}")
    w("G92 E0")
    px0, py0 = 20.0, 20.0
    w(f"G1 Z{machine.PRESS_HARD:.3f} F600")
    w(f"G0 F9000 X{px0:.3f} Y{py0:.3f}")
    w("G1 E20 F300                      ; PRIME stationary purge")
    w(f"G1 F1200 X{px0+40:.3f} Y{py0:.3f} E30   ; PRIME line, in the clear")
    w(f"G0 F3000 X{px0+52:.3f} Y{py0+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    w("; BODY_START")

    e = 0.0
    qx = qy = None
    grams_note = []
    for idx, ((lh,), cx) in enumerate(zip(CONFIGS, xs)):
        bw = flow / (speed * lh)           # same volumetric rate for every ring
        e_mm = bw * lh / A
        pts = [(cx + r*math.cos(2*math.pi*i/n_lap), cy + r*math.sin(2*math.pi*i/n_lap))
               for i in range(n_lap + 1)]
        w(f"; ---- part coupon lh{lh:g}: bead {bw:.2f}x{lh:g} at {speed:g} = {bw*lh*speed:.0f} mm3/s")
        if idx == 0:
            w(f"G0 F9000 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; PRIME-TRAVEL")
        else:
            w("G0 Z25.0 F1800   ; HOP lift, clear of finished coupons")
            w(f"G0 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} F{travel_f}   ; HOP to next coupon")
        w(f"G1 Z{machine.PRESS_HARD:.3f} F600")
        w(f"G1 F{f}")
        qx, qy = pts[0]
        # layer 1: pressed ring — R1's weld; same mm2/mm as the body, spread by the press
        for X, Y in pts[1:]:
            d = math.hypot(X - qx, Y - qy)
            if d < 0.02:
                continue
            e += d * e_mm
            w(f"G1 X{X:.3f} Y{Y:.3f} Z{machine.PRESS_HARD:.3f} E{e:.5f}")
            qx, qy = X, Y
        # body: continuous helix at this ring's own lap height
        laps = int((a.height - machine.PRESS_HARD) / lh)
        t = 0.0
        C = 2*math.pi*r
        qz = machine.PRESS_HARD
        for lap in range(laps):
            for X, Y in pts[1:]:
                d = math.hypot(X - qx, Y - qy)
                if d < 0.02:
                    continue
                t += d
                Z = machine.PRESS_HARD + lh * t / C
                d3 = math.hypot(d, Z - qz)
                e += d3 * e_mm
                w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}")
                qx, qy, qz = X, Y, Z
        grams_note.append(f"lh{lh:g}: {laps} laps")

    w("M107"); w("M104 S0"); w("M140 S0")
    w("G0 Z45 F900")
    w(f"G0 X{min(10.0, bx-10):.0f} Y{by-10:.0f} F9000")
    g = "\n".join(L) + "\n"
    grams = e * A * 1.24 / 1000.0
    mins = e * A / flow / 60.0
    print(f"  3 coupons d{a.dia:g} h{a.height:g}: " + " | ".join(grams_note))
    print(f"  all at {flow:g} mm3/s, {speed:g} mm/s; ~{grams:.0f} g, ~{mins:.0f} min")
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"lapweld_{a.printer}_d{a.dia:g}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
