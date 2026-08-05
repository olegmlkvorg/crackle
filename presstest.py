#!/usr/bin/env python3
"""PRESS TEST — 0.1mm line height, 20mm line width. Oleg, 2026-07-28: "print test 0.1 line
heght 20mm line width", after the third report of "we still do not have pressed into the board".

WHAT IT IS. Nine straight ribbons, ONE layer, nothing stacked, ~2 minutes. Every ribbon carries
the same 2.00 mm2/mm (20mm x 0.1mm) at the same 30 mm/s, which is 60 mm3/s -- the machine's
measured pla-matte figure, so this is a full-flow test, not a gentle one.

WHY A WIDTH IS A MICROMETER. A pressed bead has nowhere to go but sideways, so

        landed width  =  (mm2 per mm)  /  (actual nozzle-to-plate gap)

At 2.00 mm2/mm a 0.05mm error in the gap moves the landed ribbon by 3-7 MILLIMETRES. The thing we
cannot measure directly (the gap) is amplified ~200x into the thing we can measure with a ruler,
or eyeball against the known pitch between ribbons. That is the whole design.

THE LADDER (5 ribbons... no, 4 rungs, 200mm long, left to right across the middle of the plate).
All four are commanded the SAME material and speed; only the commanded Z changes:

    rung 1   Z 0.10   <- exactly what Oleg asked for. Predicted landed width 20.0mm
    rung 2   Z 0.15                                                        13.3mm
    rung 3   Z 0.20                                                        10.0mm
    rung 4   Z 0.30                                                         6.7mm

Two unknowns, and four measurements is enough to separate them -- which matters, because they
would otherwise be confused with each other:

    w(Z) = k * 2.00 / (Z + off)

    off = the CONSTANT error in the Z reference. Positive means the real gap is bigger than
          commanded -- the nozzle never got down to the plate. That is the "not pressed" symptom,
          and a nozzle-touch home through a blob of molten PLA is one way to get it.
    k   = the fraction of commanded material actually delivered. If the extruder is slipping at
          60 mm3/s, every ribbon comes out narrow TOGETHER, which would look exactly like a
          positive off if only one ribbon were printed.

A single ribbon cannot tell those apart. Four can: off shifts the CURVE, k scales it.

THE POSITION TRIAD (4 short ribbons, 55mm, in the corners of the print zone, all at Z 0.10).
The plate's loaded 9x9 mesh measures 0.65mm of variation (-0.137 .. +0.515, a near-linear ramp
in Y). If the mesh is doing its job, all four corner ribbons land the same width as rung 1. If
the front ones are fat and the back ones are thin, the mesh is not being applied and the fix is
mechanical, not a Z offset.

HOW TO READ THE PLATE
  1. Thumb-peel each ribbon. Welded = it fights back and leaves colour on the sheet. Not welded =
     it lifts as a whole strip with a glossy underside.
  2. Measure each ribbon's WIDTH. No caliper needed for the ladder: the clean plate between rungs
     is ~20mm everywhere by construction, so compare a ribbon to its own gap.
  3. Feed the four widths back and the fit prints the actual gap and the actual delivery.

WHAT IT CANNOT ANSWER: whether the failure is the plate surface itself (grease, PEI wear) --
that shows up as "welded here, not there" with no pattern. And it says nothing about layer 2+.
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

A_FIL = machine.A_FIL      # 2.40528 mm2 of filament


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--width", type=float, default=20.0, help="commanded line width (Oleg: 20)")
    ap.add_argument("--layer", type=float, default=machine.PRESS_HARD, help="the press gap: 0.1")
    ap.add_argument("--rungs", default="0.10,0.15,0.20,0.30",
                    help="commanded Z of each ladder rung. Steps must stay within one layer "
                         "height or the Z-ladder guard (correctly) refuses the file.")
    ap.add_argument("--length", type=float, default=200.0, help="ladder ribbon length")
    ap.add_argument("--probe-length", type=float, default=55.0, help="corner ribbon length")
    ap.add_argument("--zoff", type=float, default=0.0,
                    help="SET_GCODE_OFFSET Z applied immediately after G28, mm. NEGATIVE brings "
                         "the nozzle CLOSER to the plate. Every commanded Z in the file stays "
                         "exactly what it was, so R1 still reads a pressed 0.1 first layer — the "
                         "difference is that it now IS one. MEASURED 2026-08-06: under a commanded "
                         "Z0.100, three sheets of paper slid free and four touched, so the real "
                         "gap read ~0.35mm. That paper figure was WRONG BY 2x -- a printed ladder later put the error at ~0.15mm, because the spring-steel sheet flexes under the shim. Positive is refused.")
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    # A POSITIVE OFFSET IS THE BUG, NOT A TEST OF IT. It lifts the nozzle further from the plate,
    # which is precisely the failure this file exists to measure, and it would also print ABOVE the
    # press R1 guarantees while R1 kept reading Z0.100 and passing. Refused at the source rather
    # than left to a validator that cannot see SET_GCODE_OFFSET at all.
    if a.zoff > 1e-9:
        sys.exit(f"REFUSING TO EMIT: --zoff {a.zoff:+g} is POSITIVE, which lifts the nozzle AWAY "
                 f"from the plate. That is the defect being measured. Use a negative value to "
                 f"press harder, or 0 to test the machine's own zero.")

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    flow = machine.flow_cap(a.material, a.printer)
    temp = machine.temp_for(a.material)
    bed = machine.bed_for(a.material, a.printer)
    bx, by = machine.BED[a.printer]

    mm2 = a.width * a.layer                       # 2.00 mm2 per mm of path
    speed = machine.speed_for_flow(flow, a.width, a.layer)   # the wide-bead crawl: 30 mm/s
    e_mm = machine.layer1_rate(a.width, a.layer)   # ONE implementation, machine.py
    rungs = [float(s) for s in a.rungs.split(",") if s.strip()]

    # PITCH MATCHED TO EXPECTED SPREAD, so every ribbon keeps ~20mm of clean plate beside it and
    # the gap itself is the ruler. A fixed pitch either wastes the plate or lets rung 1 merge into
    # rung 2 -- and two merged ribbons destroy the only measurement this plate exists to make.
    ys, y = [], 100.0
    for i, z in enumerate(rungs):
        ys.append(y)
        if i + 1 < len(rungs):
            w_here, w_next = mm2 / z, mm2 / rungs[i + 1]
            y += (w_here + w_next) / 2.0 + 20.0
    x0 = (bx - a.length) / 2.0

    if ys[-1] + mm2 / rungs[-1] / 2.0 > by - 25.0:
        sys.exit(f"ladder needs {ys[-1]:.0f}mm of Y and the plate has {by:.0f} — shorten it")

    # corners of the PRINT ZONE (where real parts live), not of the plate
    pl = a.probe_length
    probes = [("front-left",  25.0,        48.0),
              ("front-right", bx - 25 - pl, 48.0),
              ("back-left",   25.0,        by - 50.0),
              ("back-right",  bx - 25 - pl, by - 50.0)]

    L = []; w = L.append
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={a.layer:g}")
    w(f"; FLOW={mm2 * speed:.4f}")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={a.layer:g}")
    w(f"; PRINT_TEMP={temp}")
    w(f"; SEQUENTIAL={len(probes) + len(rungs)} straight ribbons, lifted hops between, nothing stacked")
    w("; ARGV: " + " ".join(sys.argv))
    w(f"; PRESS TEST: {a.width:g}mm commanded width x {a.layer:g}mm = {mm2:.2f} mm2/mm at "
      f"{speed:g} mm/s = {mm2*speed:.0f} mm3/s")
    w(f"; the LANDED WIDTH of each ribbon is the instrument: w = k * {mm2:.2f} / (Z + off)")
    w(f"; ladder rungs Z={','.join(f'{z:g}' for z in rungs)} at Y={','.join(f'{v:.0f}' for v in ys)}")
    w(f"; predicted widths if the gap is exactly commanded: "
      f"{', '.join(f'{mm2/z:.1f}mm' for z in rungs)}")
    w("; HEADER_BLOCK_START"); w("; total layer number: 1"); w("; HEADER_BLOCK_END")
    w("M82")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    # Probe at PRINT temperature: the nozzle is shorter cold and then grows DOWN into the plate
    # (validate.py R7). This is also the leading suspect for the press failure -- a tip carrying
    # oozed PLA measures the plate as HIGHER than it is -- so the ladder is what settles it.
    w("G28")
    # THE OFFSET IS ALWAYS EMITTED, INCLUDING THE ZERO. SET_GCODE_OFFSET is machine state that
    # survives a job — the K2's own start_print macro sets it to 0 for this reason — so a file that
    # only writes it when non-zero would silently inherit whatever the previous print, or a hand
    # command, left behind. That is a variable this test cannot afford to carry: the whole plate
    # would shift by an unknown amount and every width on it would fit a wrong gap.
    w(f"SET_GCODE_OFFSET Z={a.zoff:.3f}"
      + ("                 ; the machine's own zero, uncorrected" if abs(a.zoff) < 1e-9 else
         f"            ; nozzle {abs(a.zoff):.3f}mm CLOSER than the machine's zero"))
    w(f"M190 S{machine.bed_start(a.material, bed):.0f}")
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    # FANS OFF, EXPLICITLY. A previous print can leave the part fan running, and chilling a bead
    # while its weld to the plate is still forming is the cheapest possible way to lose adhesion.
    # Inheriting fan state is exactly the kind of invisible variable this test must not carry.
    w("M106 S0")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")
    px, py = 20.0, 16.0
    # PRIME PURGE LIFTED CLEAR OF THE PLATE. A 20mm stationary purge (~48mm3) at the 0.1 press gap
    # cannot spread -- it balloons up and COLLARS the nozzle, and that collar then rides onto the
    # first printed ribbon and reads as "not pressed". This is a surviving hypothesis of the
    # 2026-07-28 root-cause hunt, and this test exists to isolate the gap -- so the one confound it
    # must not carry is a contaminated tip. Purged at Z2 the blob oozes as a free string; the
    # moving prime line then lays flat at the actual press gap, and the break-off snaps the string.
    w("G1 F600 Z2.000")
    w(f"G0 F9000 X{px:.3f} Y{py:.3f}")
    w("G1 E20 F300                      ; PRIME purge, LIFTED to Z2 so it cannot collar the tip")
    w(f"G1 F600 Z{a.layer:.3f}")
    w(f"G1 F1200 X{px+40:.3f} Y{py:.3f} E30   ; PRIME line, in the clear at the press gap")
    w(f"G0 F3000 X{px+52:.3f} Y{py+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    w("; BODY_START")

    ribbons = [(f"probe {name}", x, y_, a.layer, pl) for name, x, y_ in probes]
    ribbons += [(f"rung Z{z:g}", x0, ys[i], z, a.length) for i, z in enumerate(rungs)]

    f = round(speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    seg = 2.0            # subdivided so the per-move guards have something to measure
    e = 0.0
    for i, (label, sx, sy, z, ln) in enumerate(ribbons):
        pred = mm2 / z
        w(f"; ---- part ribbon {i+1}: {label} — {ln:g}mm at Z{z:.3f}, predicts {pred:.1f}mm wide")
        if i == 0:
            w(f"G0 F9000 X{sx:.3f} Y{sy:.3f} ; PRIME-TRAVEL")
        else:
            w("G0 Z1.000 F1800   ; HOP lift, clear of the finished ribbons")
            w(f"G0 X{sx:.3f} Y{sy:.3f} F{travel_f}   ; HOP over to ribbon {i+1}")
        w(f"G1 F600 Z{z:.3f}")
        w(f"G1 F{f}")
        n = max(2, int(round(ln / seg)))
        qx = sx
        for k in range(1, n + 1):
            X = sx + ln * k / n
            d = X - qx
            e += d * e_mm
            w(f"G1 X{X:.3f} Y{sy:.3f} Z{z:.3f} E{e:.5f}")
            qx = X

    w("M107"); w("M104 S0"); w("M140 S0")
    w("G0 Z45 F900")
    w(f"G0 X{min(10.0, bx-10):.0f} Y{by-10:.0f} F9000")
    g = "\n".join(L) + "\n"

    path_mm = sum(r[4] for r in ribbons)
    grams = e * A_FIL * 1.24 / 1000.0
    print(f"  {len(ribbons)} ribbons, {path_mm:.0f}mm of path, {a.width:g}mm x {a.layer:g}mm "
          f"= {mm2:.2f} mm2/mm at {speed:g} mm/s = {mm2*speed:.0f} mm3/s (cap {flow:g})")
    print(f"  bed {bed:.0f} (waits to {machine.bed_start(a.material, bed):.0f}), nozzle {temp}, "
          f"fans off, ~{grams:.1f} g, ~{path_mm/speed/60 + 0.5:.0f} min of motion")
    print(f"  READ THE LADDER — landed width against the actual gap:")
    hdr = "    off  " + "".join(f"  Z{z:<5g}" for z in rungs)
    print(hdr)
    for off in (-0.02, 0.0, 0.05, 0.10, 0.15, 0.20, 0.30):
        row = "".join(f"  {mm2/(z+off):5.1f} " if z + off > 0.02 else "   scrape"
                      for z in rungs)
        tag = "  <- gap is exactly as commanded" if off == 0.0 else ""
        print(f"   {off:+.2f} {row}{tag}")
    print(f"  a ribbon that peels off in one glossy strip did NOT weld, whatever its width")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"presstest_{a.printer}_w{a.width:g}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
