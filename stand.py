#!/usr/bin/env python3
"""ANTI-VIBRATION PRINTER STAND — concept test tile. Oleg 2026-07-29: "i need a strong table for
both of my printers. real heavy to let them manage vibration... printouts that i will fill with
sand and gypsum, and bambo sticks if necessary". Two same-height stands (K2+K1) side by side,
usable storage underneath, anti-vibration the PRIMARY factor.

The design: a heavy DAMPING TABLETOP — printed thin-wall FORMWORK (the permanent mould) that Oleg
fills with a sand+gypsum mix that sets into a dense (~1.9 g/cc) block. Mass raises the printer's
effective inertia (same toolhead jerk -> far less motion); the grain/gypsum internal friction damps
the energy (the classic filled machine-tool base). Bamboo rods thread moulded channels as rebar +
tie tiles. The tabletop rides a rigid frame with open storage below.

THIS FILE = concept test tile #1: a floored cup (solid pressed floor that HOLDS the fill + a
single-bead spiral wall). Purpose: prove the primary factor before committing to full slabs — fill
it with sand+gypsum, let it set, KNOCK it. A dead THUD (not a ring) = the damping works, and the
printed shell holds the mix. Tiling edges, bamboo channels, and the leg/storage frame come next,
once this is confirmed. Prints on the K2 (bed 80, pla-matte)."""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

A_FIL = math.pi * (1.75 / 2) ** 2


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia", type=float, default=120.0, help="cup outer diameter")
    ap.add_argument("--height", type=float, default=40.0, help="cup height (fill depth)")
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    flow = machine.flow_cap(a.material, a.printer)
    lh = a.layer_h
    bw = machine.bead_for_flow(flow, lh)               # 2.0 for k2 pla-matte
    speed = machine.speed_for_flow(flow, bw, lh)       # 50
    temp = machine.temp_for(a.material)
    bed = machine.bed_for(a.material, a.printer)
    bx, by = machine.BED[a.printer]
    cx, cy = bx / 2.0, by / 2.0
    e_mm = bw * lh / A_FIL
    f = round(speed * 60)
    R = a.dia / 2.0 - bw / 2.0
    land = bw * lh / machine.PRESS_HARD                # pressed layer-1 landed width (~12mm)
    seg = max(0.5, speed / 150.0)

    L = []; w = L.append
    e = 0.0
    qx = qy = qz = None

    def emit(X, Y, Z):
        nonlocal e, qx, qy, qz
        d = math.hypot(X - qx, Y - qy)
        d3 = math.hypot(d, Z - qz)
        if d3 < 0.2:            # decimate micro-segments (spiral centre) — else Klipper move-rate stalls
            return
        e += d3 * e_mm
        w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}")
        qx, qy, qz = X, Y, Z

    laps_wall = int((a.height - (machine.PRESS_HARD + lh)) / lh)
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh}")
    w(f"; FLOW={bw*lh*speed:.4f}")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w(f"; PRINT_TEMP={temp}")
    w("; ARGV: " + " ".join(sys.argv))
    w(f"; STAND concept cup d{a.dia:g} h{a.height:g}: solid pressed floor + single-bead spiral wall, "
      f"fill with sand+gypsum then knock-test for damping")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {laps_wall + 2}"); w("; HEADER_BLOCK_END")
    w("M82")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    _wait = bed if a.printer == "k2plus" else machine.bed_start(a.material, bed)
    w(f"M190 S{_wait:.0f}")                 # bed hot BEFORE homing — plate expanded to print height
    w(f"M109 S{temp}")                      # NOZZLE HOT BEFORE G28: a cold tip carries residue from the
    #   previous print, and the blob touches first -> Z0 set high -> nothing presses (the recurring
    #   "nothing glued"). A hot tip sheds it and the datum is taken at true print-temp length.
    w("G28")
    w("SET_GCODE_OFFSET Z=-0.05             ; first-layer press insurance: the K2 nozzle-touch datum"
      " scatters ~0.1mm high (measured); bias down 0.05 so the 0.1 gap actually presses")
    w("M106 S0")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")
    px, py = 20.0, 16.0
    w(f"G1 F600 Z{machine.PRESS_HARD:.3f}")
    w(f"G0 F9000 X{px:.3f} Y{py:.3f}")
    w("G1 E20 F300                      ; PRIME stationary purge")
    w(f"G1 F1200 X{px+40:.3f} Y{py:.3f} E30   ; PRIME line")
    w(f"G0 F3000 X{px+52:.3f} Y{py+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    w("; BODY_START")

    # --- FLOOR layer 1: pressed at 0.1, Archimedean spiral INWARD, pitch = landed width so the
    #     ~12mm pressed beads tile into a solid welded base (the wide-line press, R4b-exempt). ---
    z1 = machine.PRESS_HARD
    th = 0.0
    r = R
    x0 = cx + R
    w(f"G0 F9000 X{x0:.3f} Y{cy:.3f} ; PRIME-TRAVEL to floor start")
    w(f"G1 F600 Z{z1:.3f}")
    w(f"G1 F{f}")
    qx, qy, qz = x0, cy, z1
    dth = seg / max(R, 1.0)
    while r > land * 0.5:
        th += dth
        r = R - land * th / (2.0 * math.pi)
        if r < 0:
            r = 0.0
        emit(cx + r * math.cos(th), cy + r * math.sin(th), z1)
        if r <= land * 0.5:
            break

    # --- FLOOR layer 2: normal solid infill, spiral OUTWARD at bead pitch, Z = 0.1 + lh ---
    z2 = machine.PRESS_HARD + lh
    w(f"G1 F1800 Z{z2:.3f}")
    w(f"G1 F{f}")            # re-assert body speed — the Z move left F at 1800 (30mm/s)
    qz = z2
    th = 0.0
    r = 0.0
    while r < R:
        th += seg / max(r, bw)
        r = bw * th / (2.0 * math.pi)
        if r > R:
            r = R
        emit(cx + r * math.cos(th), cy + r * math.sin(th), z2)

    # --- WALL: single-bead circle spiral rising from z2 to height, continuous from the floor edge ---
    n = max(96, int(2 * math.pi * R / seg))
    C = 2 * math.pi * R
    t = 0.0
    ang0 = math.atan2(qy - cy, qx - cx)
    laps = int((a.height - z2) / lh)
    for lap in range(laps):
        for i in range(1, n + 1):
            ang = ang0 + 2 * math.pi * i / n
            X, Y = cx + R * math.cos(ang), cy + R * math.sin(ang)
            d = math.hypot(X - qx, Y - qy)
            if d < 0.02:
                continue
            t += d
            Z = z2 + lh * t / C
            emit(X, Y, Z)

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{a.height + 10:.0f} F900")
    w(f"G0 X{min(10.0, bx-10):.0f} Y{by-10:.0f} F9000")
    g = "\n".join(L) + "\n"

    grams = e * A_FIL * 1.24 / 1000.0
    mins = e / e_mm / speed / 60.0
    fill_ml = math.pi * (R ** 2) * (a.height - z2) / 1000.0
    print(f"  stand concept cup d{a.dia:g} h{a.height:g}: solid pressed floor + {laps}-lap wall")
    print(f"  ~{grams:.0f} g shell, ~{mins:.0f} min; holds ~{fill_ml:.0f} mL fill "
          f"(~{fill_ml*1.9/1000:.1f} kg sand+gypsum)")
    print(f"  KNOCK TEST after it sets: dead THUD = damping works; ringing = not enough mass/contact")
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"stand_concept_{a.printer}_d{a.dia:g}_h{a.height:g}_T{temp:g}.gcode")
    machine.emit_gcode(fn, g)
    print(fn)


if __name__ == "__main__":
    main()
