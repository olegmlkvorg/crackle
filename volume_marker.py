#!/usr/bin/env python3
"""VOLUME MARKER — print the K2's 350x350x350 build volume as a physical object.

Not a wireframe cube (that is ~1.4 kg and most of a day). ONE CORNER of the cube: two floor rails
running the full span in X and Y from a corner, and one post standing the full height where they
meet. Three axes at full extent, three edges of material instead of twelve.

    Y
    ^
    |  rail Y (span mm)
    |  |
    |  |
    |  [post]---- rail X (span mm) ---->  X
       ^ post stands `height` mm

WHY THE POST IS NOT THE HARD PART, AND WHAT IS
----------------------------------------------
Tipping is the obvious worry and it is not the binding constraint. Layer 1 presses the body's full
mm2/mm into a 0.10 gap (machine.PRESS_HARD), so the rails land ~7x their nominal width and glue
~5000 mm2 of PLA to the plate with a `span`-long moment arm in both axes. The post is fused into
that at its base — one continuous stroke, not a separate object — so overturning it means peeling
a 350mm rail off the sheet. A 25mm single-wall square section has I = (2/3)*t*b^3 = 12500 mm4 and a
tip compliance of L^3/(3EI) = 0.46 mm per newton of nozzle drag; Euler self-buckling sits ~1200x
above its own weight. None of that is close.

What IS close is LAYER TIME. 350mm of height at a 0.6 layer is 584 layers, and a 100mm perimeter at
the 50 mm/s north star gives each layer 2.0 seconds to freeze. A 1.2x0.6 PLA bead cooling to Tg is
an order of magnitude slower than that at the 20% part-fan the house caps PLA to
(machine.FAN_MAX), so the tower gets built out of plastic that is still soft and leans before it
ever tips.

Three facts decide what can be done about it, and they are worth stating because they remove most
of the apparent options:

  * FILAMENT DEPENDS ON PERIMETER ALONE. volume = perimeter * height * bead_w. Layer height does
    not appear. Speed does not appear. A fatter post costs filament and buys nothing else.
  * TOTAL TIME = 584 * layer_time. The layer count is fixed by the height, so choosing a layer
    time chooses the print duration outright, whatever the cross-section.
  * THEREFORE THE ONLY LEVERS ON LAYER TIME ARE SPEED AND FAN. A bigger section raises layer time
    only by raising filament in exact proportion.

So speed is derived from a layer-time target rather than pinned at the north star. R3 permits one
constant speed below 50 when a constraint requires it; the constraint is stated in the file's
'; FLOW_DERATE=' stamp rather than left to be inferred.

THE FAN IS THE OTHER LEVER AND IT IS DELIBERATELY LEFT AT THE HOUSE CAP. machine.FAN_MAX puts PLA
at 20% on Oleg's rule ("fans for printing pla should be only on 20% at most"), which he set to stop
a landing bead being chilled on big flat plates. Layer 400 of a slender tower is not that case, and
raising --fan is the single highest-leverage change available here — but it is his rule, so the
default obeys it and the override is explicit.

PATH — ONE CONTINUOUS STROKE PER LAYER, NO TRAVEL
-------------------------------------------------
The rails attach at the post's FAR corner J (not at the plate corner), so no bead is ever laid over
ground another bead already covers:

    layer, direction A:   rail-X tip -> J -> full post loop -> J -> rail-Y tip
    layer, direction B:   rail-Y tip -> J -> full post loop -> J -> rail-X tip

Alternating A/B means each layer starts exactly where the last one ended: zero travel through the
rail section. When the rails top out, the head is at a rail tip and the post carries on alone, which
costs exactly ONE hop in the whole file (tagged, counted, and reported by validate.py).

Bed 60 (machine.BED_TEMP; a cold plate spaghettied on this machine). Nozzle 210 per the brief —
note machine.LOADED says pla-matte at 230 is what was last loaded, so check the spool.

Usage:  python3 volume_marker.py [--span 350] [--height 350] [--post 25] [--layer-secs 6]
"""
import argparse, math, os
import machine

# THE Z CEILING IS NOT IN machine.py, SO IT IS DERIVED HERE AND ITS PROVENANCE IS STATED.
# machine.BED carries the plate in XY only. The K2's product_param reads bed_size 350/350/350
# (quoted in machine.py's BED comment), so 350.0 is the nominal Z as well. It matters because the
# end-of-print park lift would otherwise command Z365 on a part that finishes at Z349.9 and drive
# the gantry into its own stop.
Z_CEILING = {"k2plus": 350.0, "k1c": 250.0, "f022": 250.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus")
    ap.add_argument("--material", default="pla",
                    help="pla (210C) per the brief. machine.LOADED says pla-matte/230 was last "
                         "loaded on the k2plus — check the spool before sending.")
    ap.add_argument("--span", type=float, default=350.0,
                    help="floor rail span mm — the X and Y extent being demonstrated")
    ap.add_argument("--height", type=float, default=350.0,
                    help="post height mm — the Z extent being demonstrated")
    ap.add_argument("--origin", type=float, default=0.0,
                    help="plate coordinate of the marker corner. 0 puts the post's outer wall on "
                         "the plate edge, so half the pressed layer-1 bead (~3.6mm) overhangs it. "
                         "The K2's bed mesh is only probed 5,5 -> 345,345, so the last 5mm at each "
                         "end sits on extrapolated mesh. --origin 5 --span 340 keeps everything "
                         "inside the probed area, and demonstrates 340 instead of 350.")
    ap.add_argument("--post", type=float, default=25.0,
                    help="post cross-section, mm square. Costs filament in direct proportion and "
                         "buys nothing but stiffness — see the note at the top of this file.")
    ap.add_argument("--rail-h", type=float, default=6.0,
                    help="floor rail height mm. Cheap: the rails are ~10%% of the post's filament "
                         "and they are what makes the marker impossible to tip.")
    ap.add_argument("--layer-secs", type=float, default=6.0,
                    help="target seconds per post layer; speed is derived from it. JUDGEMENT, NOT "
                         "A MEASUREMENT — a lumped-capacity estimate puts a 1.2x0.6 PLA bead at "
                         "~16s to Tg with a 20%% fan, and vase towers are commonly run at 4-6s. "
                         "Nothing here has been measured on a printed part.")
    ap.add_argument("--speed", type=float, default=None,
                    help="mm/s override; bypasses --layer-secs. Never above the 50 north star.")
    ap.add_argument("--layer-h", type=float, default=machine.BEAD_H)
    ap.add_argument("--bead", type=float, default=machine.BEAD_W,
                    help="bead WIDTH mm. 1.2 = 1.5x the 0.8 nozzle, the stacking ceiling and the "
                         "width that lines up accurately. This IS the post's wall thickness.")
    ap.add_argument("--seg", type=float, default=None,
                    help="emitted segment length mm; default = the bead width. See go() — this is "
                         "output resolution, not geometry, and it is what lets the repo's "
                         "sampling checks see a part whose layers are four corners long.")
    ap.add_argument("--temp", type=float, default=210.0)
    ap.add_argument("--bed", type=float, default=None, help="default: machine.BED_TEMP (PLA 60)")
    ap.add_argument("--fan", type=float, default=None,
                    help="part fan 0-1 from layer 2. Default machine.FAN_MAX (PLA 0.20).")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    lh, bw = a.layer_h, a.bead
    P = a.post
    seg = a.seg if a.seg else bw
    bed = a.bed if a.bed is not None else machine.BED_TEMP.get(a.material, 60)
    bed = min(bed, machine.BED_MAX.get(a.printer, machine.BED_MAX_DEFAULT))
    fan = a.fan if a.fan is not None else machine.FAN_MAX.get(a.material, 0.20)
    zmax = Z_CEILING.get(a.printer, 250.0)

    # SPEED FROM LAYER TIME. The post loop is the layer that has no time to cool; the rail layers
    # are 7x longer and take care of themselves.
    perim = 4.0 * P
    speed = a.speed if a.speed else min(perim / a.layer_secs, machine.MAX_SPEED)
    # The FILE is the artifact, so derive the stamps from what will actually be commanded: F is an
    # integer, and a stamp computed from the pre-rounding float is a stamp that disagrees with the
    # gcode underneath it.
    f = max(1, round(speed * 60))
    speed = f / 60.0
    flow = bw * lh * speed
    A_FIL = math.pi * (1.75 / 2) ** 2
    e_mm = bw * lh / A_FIL                       # mm of 1.75 filament per mm of path

    ox = oy = a.origin
    J = (ox + P, oy + P)                          # rails meet the post at its FAR corner
    x_tip = (ox + a.span, oy + P)                 # rail X runs +X at y = oy+P
    y_tip = (ox + P, oy + a.span)                 # rail Y runs +Y at x = ox+P
    # post loop, starting and ending at J, laid once per layer
    loop = [(ox, oy + P), (ox, oy), (ox + P, oy), J]

    nlay = int((a.height - machine.PRESS_HARD) // lh) + 1
    nrail = max(1, int(round(a.rail_h / lh)))
    top_z = machine.PRESS_HARD + (nlay - 1) * lh

    L = []
    w = L.append
    w("; VOLUME MARKER — one corner of the K2 build volume at full extent in X, Y and Z")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={speed:.4f}")
    w(f"; FLOW={flow:.4f}")
    w(f"; FLOW_DERATE=584-layer slender tower. Filament depends on perimeter alone and total time "
      f"is 584 x layer time, so SPEED is the only lever on how long each layer has to freeze "
      f"before the next lands. {speed:.1f} mm/s gives the {perim:g}mm post loop "
      f"{perim/speed:.1f}s per layer; the 50 north star would give {perim/50:.1f}s. Deposit per mm "
      f"of path is identical either way (E is metered per mm) — this costs clock, not material.")
    w(f"; span {a.span:g} height {a.height:g} post {P:g} square, bead {bw:g} x {lh:g}, "
      f"{nlay} layers, rails {nrail} layers")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {nlay}"); w("; HEADER_BLOCK_END")
    w("M82")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{a.temp:.0f}")
    w(f"M190 S{bed:.0f}")
    w(f"M109 S{a.temp:.0f}")
    w("G28")
    w("M106 S0                              ; layer 1 gets no fan — it is welding to the plate")
    w("G92 E0")

    # PRIME, laid well clear of the marker. The marker occupies an L along the low-X and low-Y
    # edges, so the far side of the plate is empty.
    #
    # THE E AXIS IS NOT RESET AFTER THE PRIME, AND THAT IS DELIBERATE. The obvious thing is a second
    # 'G92 E0' so the body starts from zero, and it is what the other generators here do. It breaks
    # R4 on this file: validate.py's rule loop skips every line that is not G0/G1, so it never sees
    # the G92, and it then reads the first body move's advance as (E_body - E_prime). Other
    # generators get away with it because their first body move is short enough that the difference
    # comes out negative and the move is dropped; this file's first move is 325mm, which lands the
    # error squarely inside the failing band and reported a 0.51mm2 bead that does not exist.
    # One continuous absolute E axis is both simpler and correct, so nothing has to be excused.
    PRIME_E = 28.0
    px, py = ox + 60.0, oy + a.span - 10.0
    w(f"G1 F600 Z{machine.PRESS_HARD:.3f}")
    w(f"G0 F9000 X{px:.3f} Y{py:.3f}")
    w("G1 E18 F300                          ; PRIME stationary purge")
    w(f"G1 F1200 X{px+40:.3f} Y{py:.3f} E{PRIME_E:g}  ; PRIME line")
    w(f"G0 F3000 X{px+52:.3f} Y{py+8:.3f}    ; PRIME break-off wipe")
    w("; BODY_START")

    E = PRIME_E
    cx = cy = None

    def go(pt):
        """One extruding move, subdivided to `seg`.

        SUBDIVISION CHANGES NO MOTION AND NO MATERIAL — same straight line, same total E. It exists
        because this part is four corners per layer and the repo's geometry checks sample MOVE
        ENDPOINTS: at full length a 325mm rail contributes two points, so the overhang check saw a
        fully-supported layer as 17% floating and the fill-ratio check had too few rows to run at
        all. Both assume points land about a bead apart, which is true of every curve generator
        here and was false of this one. Emitting at bead resolution puts the file in the
        representation the checks were built for, rather than leaving a part they structurally
        cannot see — RULES.md is explicit that an unchecked file passing is the worst outcome.

        THE FEEDRATE IS RESTATED ON EVERY MOVE. F persists in gcode, and the first version of this
        generator let four post moves inherit F6000 from the hop above them and run at 100 mm/s
        against a 50 ceiling. Restating it costs bytes and removes the whole class.
        """
        nonlocal E, cx, cy
        d = math.hypot(pt[0] - cx, pt[1] - cy)
        if d < 1e-9:
            return
        n = max(1, int(math.ceil(d / seg)))
        x0, y0 = cx, cy
        for i in range(1, n + 1):
            t = i / n
            E += (d / n) * e_mm
            w(f"G1 F{f} X{x0 + (pt[0]-x0)*t:.3f} Y{y0 + (pt[1]-y0)*t:.3f} E{E:.4f}")
        cx, cy = pt

    # Layer 1 starts at a rail tip, so the very first bead laid is a rail — the thing glued to the
    # plate — rather than the post it has to hold up.
    start = x_tip
    w(f"G1 F600 Z{machine.PRESS_HARD:.3f}")
    w(f"G0 F9000 X{start[0]:.3f} Y{start[1]:.3f} ; PRIME-TRAVEL to the rail tip")
    cx, cy = start
    w(f"G1 F{f}")

    for k in range(nlay):
        z = machine.PRESS_HARD + k * lh
        # R1/R2 read layers off a bare 'G1 [F] Z<z>' line, so the ladder is emitted in that exact
        # form. It also sets validate's layer floor, which is what keeps the plough check live.
        w(f"G1 F{f} Z{z:.3f}")
        if k == 1:
            w(f"M106 S{int(round(fan*255))}                            "
              f"; part fan {fan*100:.0f}% from layer 2 (machine.FAN_MAX for {a.material})")
        if k < nrail:
            # rails still running: rail-in -> post loop -> rail-out, alternating so the next layer
            # begins exactly where this one ended.
            a_tip, b_tip = (x_tip, y_tip) if k % 2 == 0 else (y_tip, x_tip)
            if (cx, cy) != a_tip:
                w(f"G0 F6000 X{a_tip[0]:.3f} Y{a_tip[1]:.3f} ; HOP over the rail to the far tip")
                cx, cy = a_tip
            go(J)
            for pt in loop:
                go(pt)
            go(b_tip)
        else:
            if k == nrail:
                # THE ONE TRAVEL IN THE FILE. The rails are finished and the head is standing at a
                # rail tip; the post carries on alone. It is a lift-and-cross over a 6mm rail at
                # the next layer's Z, flow suspended, no retract.
                w(f"G0 F6000 X{J[0]:.3f} Y{J[1]:.3f} ; HOP over the finished rail to the post")
                cx, cy = J
            for pt in loop:
                go(pt)

    w("M107")
    w("M104 S0")
    w("M140 S0")
    # PARK — LIFT, THEN XY, AND THE HEADROOM IS THE WHOLE PROBLEM AT FULL HEIGHT.
    #
    # A part that reaches the machine's Z ceiling cannot be escaped from vertically. That is not a
    # bug in this generator, it is what printing the whole volume means, and it has to be stated
    # rather than designed around. Two wrong answers were tried first:
    #   * the stock 'G0 Z+15' commands Z365 on a part that tops out at Z349.9 and drives the gantry
    #     into its own stop;
    #   * skipping the lift and parking in XY at the print height ploughs the nozzle along the top
    #     of the last bead — validate.py catches this, and it is right to: a travel AT the height
    #     of standing material is the damaging case, not merely below it.
    # So the lift is clamped to the ceiling and taken FIRST. At the default height that is 0.1mm of
    # real clearance, which is exactly one PRESS_HARD gap and is all the machine has to give.
    # --height 345 buys 5mm of it and demonstrates 345 instead of 350; that is Oleg's call, not
    # this file's, so the default demonstrates the full claim and the cost is printed out loud.
    _lift = min(top_z + 15.0, zmax)
    _clear = _lift - top_z
    w(f"G0 Z{_lift:.3f} F900                    ; lift {_clear:.2f}mm — ALL the headroom there is")
    w(f"G0 X{min(ox + a.span - 20, machine.BED[a.printer][0] - 5):.0f} "
      f"Y{min(oy + a.span - 5, machine.BED[a.printer][1] - 5):.0f} F9000")

    os.makedirs(a.out, exist_ok=True)
    # SPEED IS IN THE FILENAME. It is the parameter this part actually turns on — it sets the layer
    # time and therefore whether the tower stands up — so two runs that differ only in speed must
    # not land on the same path and silently overwrite each other.
    fn = os.path.join(a.out,
                      f"volume_marker_{a.printer}_{a.span:g}x{a.span:g}x{a.height:g}"
                      f"_p{P:g}_v{speed:.0f}_T{a.temp:.0f}.gcode")
    machine.emit_gcode(fn, "\n".join(L) + "\n")
    print(fn)
    print(f"  {nlay} layers, top of material at Z{top_z:g} (ceiling {zmax:g}), "
          f"post {P:g}mm square, rails {nrail} layers = {nrail*lh:g}mm tall")
    print(f"  one speed {speed:g} mm/s, flow {flow:.1f} mm3/s, post layer time "
          f"{perim/speed:.1f}s, fan {fan*100:.0f}%")
    if _clear < 1.0:
        print(f"  ! park clearance is only {_clear:.2f}mm: the part tops out at Z{top_z:g} against "
              f"a {zmax:g} ceiling, so the end-of-print lift has almost nowhere to go. The bed "
              f"mesh adds its own Z compensation on top of a commanded {_lift:g}, so the last line "
              f"of a 65-minute print is the one that can throw 'Move out of range'. "
              f"--height {zmax-5:g} buys 5mm of clearance and demonstrates {zmax-5:g}mm of Z.")
    print("  measure the FILE, not this line: python3 tools/measure_gcode.py " + fn)


if __name__ == "__main__":
    main()
