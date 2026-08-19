#!/usr/bin/env python3
"""STENCIL COUPON — one plate that answers stiffness, bleed and minimum feature size together.

  Oleg, 2026-08-06: "It is super nice that we can make thin sheets like this, add another vertical
  where we use this tech to create shapes that we print over with brush or spray so it becomes a
  pattern for the print on something. not sure thou how it will compete on cutting something with
  co2 laser, but at least you would not need original flat material to cut from"

`guides/stencils-vertical.md` lists five unknowns and says one plate settles most of them in under
an hour. This is that plate. NOTHING HAS BEEN PRINTED AS A STENCIL YET; this file is the experiment,
not a result.

WHAT IT PRINTS. Two sheets side by side, identical except for one thing:

    LEFT   a plain sheet, the naive stencil
    RIGHT  the same sheet with STANDOFF RIBS, which is the hypothesis under test

Each sheet carries a row of square cut-outs and a row of round ones, both stepping 12 / 9 / 6 / 4 /
3 / 2 mm. Squares and circles because a corner and a curve fail differently at a 0.82 mm bead: a
square's corner rounds off, a circle's edge goes polygonal, and which one you notice first depends
on what you are cutting out.

THE RIBS ARE ON TOP, AND THAT IS NOT A COMPROMISE. A printer cannot lay a feature under its own
first layer, so the ribs are printed above the sheet and the stencil is FLIPPED to use. What was up
becomes the standoff. It also means the face that touches the work is the face that was pressed
against the build plate, which is the flattest surface in the whole process.

WHY STANDOFF IS THE THING WORTH TESTING. Paint bleeds where the stencil touches the work. A
laser-cut sheet lies flat and bleeds along every edge; a printed one can hold itself a controlled
distance off. A laser cannot cut a feature that stands proud of the stock it is cutting, so this is
a difference in KIND rather than degree, and it is the strongest claim in the guide. It is also
completely untested, which is why the left sheet exists to disagree with it.

HOW TO READ THE PLATE
  1. Lift both sheets. If either needs a knife or tears, a one-layer stencil is not handleable and
     the answer is 2 layers or a frame. That is unknown 2 in the guide.
  2. Count down the holes until the shape stops being the shape. The last good one is the minimum
     feature this bead can hold. That is unknown 5, and it is the real ceiling on the whole idea.
  3. Spray both, once, from the same distance. Compare the edge under the plain sheet against the
     edge under the ribbed one. That is unknown 4, and it decides whether the output looks
     deliberate or amateur.

WHAT IT STILL CANNOT ANSWER: solvent resistance (unknown 3 -- PLA is the wrong material and PETG or
PP is the honest one), and how a curved stencil behaves, which needs a curved subject to test on.

Usage:  python3 stencil_coupon.py
        python3 stencil_coupon.py --layers 2 --h1 0.15
        python3 tools/push.py out/stencil_coupon_*.gcode
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

HOLES = [12.0, 9.0, 6.0, 4.0, 3.0, 2.0]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--sheet-x", type=float, default=110.0, help="one sheet's width, mm")
    ap.add_argument("--sheet-y", type=float, default=70.0, help="one sheet's depth, mm")
    ap.add_argument("--layers", type=int, default=1,
                    help="sheet layers. 1 is the interesting case: if a one-layer sheet cannot be "
                         "handled, that is the finding.")
    ap.add_argument("--h1", type=float, default=0.10,
                    help="REAL first-layer height, mm. All five heights 0.05-0.25 welded on the "
                         "2026-08-06 ladder, so this is not delicate; 0.10 is the standing press.")
    ap.add_argument("--zerr", type=float, default=0.15,
                    help="how much higher than it reports this machine's Z zero sits. Measured "
                         "2026-08-06 off a printed plate, not by feel.")
    ap.add_argument("--w1", type=float, default=2.0, help="target LANDED width of a sheet line, mm")
    ap.add_argument("--speed", type=float, default=25.0,
                    help="mm/s. Half the north star: a sheet is all first layer, and a slower bead "
                         "has longer to wet the plate.")
    ap.add_argument("--rib-h", type=float, default=0.6, help="standoff rib height, mm")
    ap.add_argument("--rib-pitch", type=float, default=18.0, help="mm between ribs")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    material = a.material or machine.LOADED[a.printer]
    temp = machine.MATERIAL_TEMP[material]
    bed = machine.bed_for(material, a.printer)
    bx, by = machine.BED[a.printer]
    press = machine.PRESS_HARD
    lh = machine.SLICER_LAYER_H
    bw = machine.SLICER_LINE_W

    if a.speed > machine.MAX_SPEED + 1e-9:
        sys.exit(f"REFUSING TO EMIT: --speed {a.speed:g} is above the {machine.MAX_SPEED:g} mm/s "
                 f"north star, which is a ceiling.")
    try:
        zoff = machine.zoff_for(a.h1, a.zerr)
    except ValueError as e:
        sys.exit(f"REFUSING TO EMIT: {e}")

    # ONE implementation of the first-layer arithmetic, machine.py. The rate is metered against the
    # height the bead ACTUALLY lands in, which is the bug that cost three bucket starts.
    e1 = machine.layer1_rate(a.w1, a.h1)
    e_body = machine.layer1_rate(bw, lh)
    pitch = a.w1                                  # coverage 1.00x: a sheet must be solid
    f = round(a.speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)

    gap = 16.0
    total_x = 2 * a.sheet_x + gap
    if total_x > bx - 40 or a.sheet_y > by - 60:
        sys.exit(f"REFUSING TO EMIT: two {a.sheet_x:g}x{a.sheet_y:g} sheets need "
                 f"{total_x:.0f}x{a.sheet_y:g}mm and the plate has {bx-40:.0f}x{by-60:.0f}.")
    x0 = (bx - total_x) / 2.0
    y0 = (by - a.sheet_y) / 2.0

    # HOLE CENTRES. Two rows per sheet: squares above, circles below, both stepping down in size.
    # Spaced by the LARGEST hole so the row reads left to right without the big ones crowding.
    def holes_for(sx):
        step = (a.sheet_x - 20.0) / len(HOLES)
        out = []
        for i, d in enumerate(HOLES):
            cx = sx + 10.0 + step * (i + 0.5)
            out.append(("sq", cx, y0 + a.sheet_y * 0.68, d))
            out.append(("ci", cx, y0 + a.sheet_y * 0.30, d))
        return out

    def inside(hs, x, y):
        for kind, cx, cy, d in hs:
            if kind == "sq":
                if abs(x - cx) <= d / 2 and abs(y - cy) <= d / 2:
                    return True
            elif (x - cx) ** 2 + (y - cy) ** 2 <= (d / 2) ** 2:
                return True
        return False

    def spans(hs, y, xa, xb):
        """The x intervals of this raster line that are SHEET rather than hole.

        Sampled rather than solved, at a fifth of a bead. Solving it exactly means intersecting a
        line with squares and circles and then merging the intervals, which is more code and more
        ways to be wrong; at 0.16 mm the sampling error is a fifth of the bead that will cover it.
        The step is stated here rather than buried so nobody reads this as exact."""
        step = bw / 5.0
        out, run = [], None
        x = xa
        while x <= xb + 1e-9:
            solid = not inside(hs, x, y)
            if solid and run is None:
                run = x
            elif not solid and run is not None:
                if x - run > bw:
                    out.append((run, x - step))
                run = None
            x += step
        if run is not None and xb - run > bw:
            out.append((run, xb))
        return out

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.out,
                            f"stencil_coupon_{a.printer}_{material}_"
                            f"{a.layers}L_h{a.h1:g}_w{a.w1:g}.gcode")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    L = []
    w = L.append

    w(f"; STENCIL COUPON — two sheets, one plain and one ribbed, {a.layers} layer(s)")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={a.speed:.4f}")
    w(f"; SPEED_LAYER1={a.speed:.4f}")
    w(f"; FLOW={a.w1 * a.h1 * a.speed:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; LAYER1_WIDTH={a.w1:.2f}mm landed ({a.w1/(bw*lh/press):.2f}x the body's own flow pressed "
      f"into the {press:g} gap)")
    w(f"; PRINT_TEMP={temp}")
    _cap = machine.flow_cap(material, a.printer)
    w(f"; FLOW_DERATE=a sheet is ALL first layer, so it is metered from a landed width rather than "
      f"from the body's bead: {a.w1:g}mm x {a.h1:g}mm at {a.speed:g} mm/s = "
      f"{a.w1*a.h1*a.speed:.2f} mm3/s against the {_cap:g} cap. Slower on purpose so the bead has "
      f"time to wet the plate; there is no body above it to fix a bad weld.")
    w(";")
    w("; ---------------- WHAT THIS IS ----------------")
    w(f"; LEFT sheet  {a.sheet_x:g}x{a.sheet_y:g}mm, plain. The naive stencil.")
    w(f"; RIGHT sheet the same, plus STANDOFF RIBS {a.rib_h:g}mm tall every {a.rib_pitch:g}mm.")
    w(f"; Both carry squares and circles at {'/'.join(f'{d:g}' for d in HOLES)}mm.")
    w("; Squares AND circles because a corner and a curve fail differently at this bead: a corner")
    w("; rounds off, a curve goes polygonal.")
    w(";")
    w("; THE RIBS ARE ON TOP AND THE STENCIL IS FLIPPED TO USE. A printer cannot lay a feature")
    w("; under its own first layer. Flipping also puts the plate-pressed face against the work,")
    w("; which is the flattest surface in the process.")
    w(";")
    w("; WHAT IT TESTS: 1) can a 1-layer sheet be handled at all  2) the smallest hole that is")
    w("; still its own shape  3) whether standoff ribs reduce bleed against a plain sheet.")
    w("; WHAT IT CANNOT: solvent resistance (PLA is the wrong material), and curved stencils.")
    w(f"; Z zero on this machine homes ~{a.zerr:g}mm high, so the first layer lands at {a.h1:g}mm")
    w(f"; via SET_GCODE_OFFSET Z={zoff:.3f} while every commanded Z stays at {press:g}.")
    w("; MATERIAL_PLACEHOLDER")
    _mat = len(L) - 1
    w(f"; SEQUENTIAL=2 sheets, lifted hops between, nothing stacked across them")
    w(";")

    w("M82")
    w("G90")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    w("G28")
    w(f"SET_GCODE_OFFSET Z={zoff:.3f}            ; first layer lands {a.h1:g}mm, not {press:g}")
    w(f"M190 S{bed if a.printer == 'k2plus' else machine.bed_start(material, bed):.0f}")
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    w(f"M106 S{int(round(machine.fan_first_layer(material) * 255))}   ; the weld to the plate is the job")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")

    # ONE SHARED PRIME, machine.prime(). This was the Z2 lift + 20mm stationary purge in free air
    # that Oleg photographed on 2026-08-06 as a clump on the nozzle and then as a lump dropped into
    # a printing plate. validate.py R10 refuses it on the emitted file now. `e1` is this file's own
    # layer-1 rate, so the prime lays the same bead the sheets do instead of the 3.01x line that
    # used to follow the purge.
    machine.prime(w, printer=a.printer, z=press, rate=e1, feed=f, travel_feed=travel_f,
                  avoid=(("rect", x0, y0, x0 + total_x, y0 + a.sheet_y),), near=(x0, y0))
    w("; BODY_START")

    E = 0.0
    # SAFE Z IS THE PART'S, NOW THAT THE PRIME NO LONGER STANDS ON THE PLATE. The old
    # max(press + rib_h, 2.0) + 1.0 carried a 2.0 floor that had nothing to do with the ribs: it was
    # clearing the Z2 prime blob, and this file's own comment below said so. The prime now lays at
    # the press gap, so the ribs are the tallest thing here and the floor goes with the blob.
    safe_z = press + a.rib_h + 1.0
    n_lines = int(a.sheet_y / pitch) + 1

    for si, (sx, ribbed) in enumerate(((x0, False), (x0 + a.sheet_x + gap, True))):
        hs = holes_for(sx)
        w(f"; ================ sheet {si+1}: {'RIBBED' if ribbed else 'PLAIN'} ================")
        for li in range(a.layers):
            z = press + li * lh
            w(f"G0 Z{safe_z:.3f} F1800   ; HOP lift, clear of the part")
            w(f"G0 X{sx:.3f} Y{y0:.3f} F{travel_f}   ; HOP to sheet {si+1} layer {li+1}")
            w(f"G1 F600 Z{z:.3f}")
            w(f"; ---- sheet {si+1} layer {li+1} of {a.layers} at Z{z:.3f}, {n_lines} passes")
            flip = False
            for p in range(n_lines):
                y = y0 + p * pitch
                segs = spans(hs, y, sx, sx + a.sheet_x)
                if flip:
                    segs = [(b, aa) for aa, b in reversed(segs)]
                for (xa, xb) in segs:
                    # LIFTED, and it cannot be the bucket's thin strand. The bucket meters a
                    # deliberate strand across its gaps because a web between towers is wanted; a
                    # strand across a stencil's cut-out would partially block the hole, which is the
                    # one thing a stencil must not do. So these cross lifted and dry.
                    # The lift now only has to clear the SHEET AND ITS RIBS. It used to have to
                    # clear a Z2 prime blob as well -- validate.py counts a travel at 0.1 as
                    # ploughing while anything stands at 2.0, and it was right to, because the blob
                    # was real material on the same plate. machine.prime() leaves nothing standing.
                    w(f"G0 F1800 Z{safe_z:.3f}")
                    w(f"G0 F{travel_f} X{xa:.3f} Y{y:.3f}   ; HOP over a cut-out, lifted")
                    w(f"G1 F600 Z{z:.3f}")
                    E += abs(xb - xa) * (e1 if li == 0 else e_body)
                    w(f"G1 F{f} X{xb:.3f} Y{y:.3f} E{E:.5f}")
                flip = not flip

        if ribbed:
            # ON TOP, because nothing can be laid under a first layer. Flipped in use.
            nrib = max(1, int(a.sheet_y / a.rib_pitch))
            w(f"; ---- {nrib} standoff rib(s), {a.rib_h:g}mm tall, printed ON TOP and flipped in use")
            for r in range(nrib):
                yr = y0 + a.rib_pitch * (r + 0.5)
                if yr > y0 + a.sheet_y - 2:
                    continue
                nz = max(1, int(round((a.rib_h - press) / lh)))
                for k in range(nz):
                    z = press + (a.layers - 1) * lh + (k + 1) * lh
                    w(f"G0 Z{safe_z:.3f} F1800   ; HOP")
                    w(f"G0 X{sx+4:.3f} Y{yr:.3f} F{travel_f}   ; HOP to rib {r+1}")
                    w(f"G1 F600 Z{z:.3f}")
                    E += (a.sheet_x - 8.0) * e_body
                    w(f"G1 F{f} X{sx + a.sheet_x - 4:.3f} Y{yr:.3f} E{E:.5f}")

    w("; ---- done")
    w("SET_GCODE_OFFSET Z=0                 ; hand the machine back at its own zero")
    w("M107"); w("M104 S0"); w("M140 S0")
    w("G0 Z45 F900")
    w(f"G0 X10 Y{by-10:.0f} F{travel_f}")
    w("M84")

    vol = E * machine.A_FIL / 1000.0
    L[_mat] = (f"; MATERIAL {vol*1.24:.1f}g / {vol:.2f}cm3 — measured from this file's own final E")
    machine.emit_gcode(out_path, "\n".join(L) + "\n")
    print(out_path)
    print(f"  2 sheets {a.sheet_x:g}x{a.sheet_y:g}mm, {a.layers} layer(s), holes "
          f"{'/'.join(f'{d:g}' for d in HOLES)}mm")
    print(f"  first layer {a.h1:g}mm REAL via SET_GCODE_OFFSET Z={zoff:.3f}, "
          f"{a.w1:g}mm landed, {a.speed:g} mm/s")
    print(f"  ribs {a.rib_h:g}mm every {a.rib_pitch:g}mm on the RIGHT sheet only, printed on top")
    print(f"  {vol:.2f}cm3 / {vol*1.24:.0f}g")


if __name__ == "__main__":
    main()
