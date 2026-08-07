#!/usr/bin/env python3
"""Z LADDER — six numbered cells, each welded to the plate at a different gap, each with a real
second layer on top built exactly the way the bucket's floor is built.

  Oleg, 2026-08-06: "You shall test it. Prit numbers with different first level height and print
  second level on. Them normally as we will have on bucket"

WHY. Three max-bucket starts were cancelled over a first layer that laid ROUND strands instead of
pressed ones, and the width was raised 2.0 -> 3.0 -> 5.0 mm chasing it. Width was never the
problem. Every one of those three prints was extruding into open air, which is why more material
only ever made a fatter round strand -- a bead cannot press against a plate it never reaches.

**Z zero homes 0.15 mm high. NOT 0.30.** This file used to say 0.30 and that number is RETRACTED,
left here rather than deleted because it is still quoted elsewhere and it nearly caused a correct
constant to be "fixed" on 2026-08-07.

  0.30 came from PAPER: nozzle hot at bed centre, Oleg sliding sheets, three slid free at a
       commanded Z0.100 and one sheet gripped at Z-0.20.
  0.15 came from a PRINTED LADDER, which is this tool's whole reason to exist: at offset -0.15 the
       first layer was clean, and at -0.20 the nozzle DRAGGED through material it had just laid.

The paper reading was wrong by 2x, and the mechanism is worth keeping because it will happen again:
**the spring-steel sheet FLEXES under the shim and absorbs the very quantity being measured.** A
feeler gauge on a flexible plate reads the plate, not the gap. `machine.ZERR['k2plus'] = 0.15` is
the authority; this docstring is not.

WHAT THIS SWEEPS, AND WHY IT IS THE OFFSET AND NOT THE COMMANDED Z. Each cell sets
SET_GCODE_OFFSET, which moves where Z ZERO IS, and then prints at exactly the commanded heights the
bucket uses: layer 1 at Z0.100, layer 2 at Z0.340. So the offset changes the gap to the PLATE while
leaving the gap between layer 1 and layer 2 at exactly one layer height in every cell -- which is
what the bucket does. Sweeping the commanded first-layer Z instead would have moved layer 1 without
moving layer 2, and every cell would have tested a different part-to-part relationship as well as a
different plate gap. Two variables in one axis is not a ladder, it is a confound.

It also keeps the file honest to its own gates: every commanded Z is the bucket's, so R1 reads a
pressed 0.100 first layer and R2 reads a 0.24 ladder, and both are telling the truth for once --
before this correction R1 was passing a file whose real first layer was 0.4 mm off the plate.

  cell 1   offset  0.00   the uncorrected machine — what the three cancelled prints did
  cell 2   offset -0.15   the PRINTED-LADDER answer, and what machine.ZERR carries
  cell 3   offset -0.20   the ladder saw the nozzle DRAG here, so this is the far edge
  cell 4   offset -0.25
  cell 5   offset -0.30   where the RETRACTED paper reading pointed. Kept as a cell because a
                          ladder should span past its answer on both sides, not stop at it.
  cell 6   offset -0.35

THE NUMBERS ARE PRINTED, not captioned. Each cell draws its own digit in seven-segment strokes at
that cell's first-layer settings, so a photograph of the plate is self-describing and the digit is
itself a sample: a number that comes off in one glossy piece did not weld, whatever the patch next
to it looks like.

THE SECOND LAYER IS THE BUCKET'S, NOT A DECORATION. Layer 1 is a 1.6 mm-pitch raster metered to
land 2.00 mm wide in the press gap; layer 2 is the same 1.6 mm pitch turned PERPENDICULAR and laid
at the bucket's own 0.82 x 0.24 bead at the 50 mm/s north star. That is bucket_latch's cross-latch
floor, cell for cell. The reason it has to be here: a first layer can weld beautifully and still be
the wrong HEIGHT for what lands on it, and nothing about a single-layer test can show that.

Those two are the same flow, which is the whole first-layer doctrine and is worth seeing in
numbers: 2.00 x 0.10 = 0.200 mm2/mm against 0.82 x 0.24 = 0.197. Layer 1 is not over-extruded here,
it is the SAME material squashed into a gap 2.4x thinner, so it lands 2.4x wider. The width is the
adhesion.

HOW TO READ THE PLATE
  1. Thumb-peel a corner of each cell. Welded = it fights back and leaves colour on the sheet.
     Not welded = the whole cell lifts with a glossy underside.
  2. Look at the cell's SURFACE. Too high: separate round strands with plate visible between them.
     Right: a flat sheet with the raster barely readable. Too low: ridges, a scraped translucent
     look, or material pushed into ripples ahead of the nozzle.
  3. Look at layer 2. It should sit as a clean grid ON the sheet. If it drags, tears or balls up,
     layer 1 came out too thick and the bucket's floor will do the same 1250 times.
  4. The best cell's number is the offset the bucket runs with.

Usage:  python3 zladder.py
        python3 tools/push.py out/zladder_*.gcode
"""
import argparse, math, os, shlex, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

A_FIL = machine.A_FIL       # 2.40528 mm2 of 1.75mm filament

# SEVEN SEGMENTS, in a unit box: (x0,y0)-(x1,y1) as fractions of the digit's width and height.
SEG = {
    'a': (0.0, 1.0, 1.0, 1.0),   # top
    'b': (1.0, 0.5, 1.0, 1.0),   # upper right
    'c': (1.0, 0.0, 1.0, 0.5),   # lower right
    'd': (0.0, 0.0, 1.0, 0.0),   # bottom
    'e': (0.0, 0.0, 0.0, 0.5),   # lower left
    'f': (0.0, 0.5, 0.0, 1.0),   # upper left
    'g': (0.0, 0.5, 1.0, 0.5),   # middle
}
DIGIT = {'0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc',
         '5': 'afgcd', '6': 'afgedc', '7': 'abc', '8': 'abcdefg', '9': 'abcdfg'}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--heights", default="0.05,0.10,0.15,0.20,0.25",
                    help="FIRST-LAYER HEIGHT per cell, mm, in print order. This is the thing being "
                         "swept and the material scales with it, so every cell lands the same "
                         "--w1 width and is equally solid — the height is then the ONLY variable "
                         "on the plate. Every commanded Z in the file stays at PRESS_HARD; "
                         "the height is reached by SET_GCODE_OFFSET, so R1 and R2 read the ladder "
                         "they were written for and the check that matters is not disabled.")
    ap.add_argument("--zerr", type=float, default=0.15,
                    help="how much HIGHER than it thinks this machine's Z zero sits, mm. Needed "
                         "because a height has to be turned into an offset: offset = height - "
                         "PRESS_HARD - zerr. MEASURED 2026-08-06 on the K2, off a printed plate "
                         "rather than by feel: at offset -0.15 the first layer was clean and at "
                         "-0.20 the nozzle was dragging through the material it had just laid, so "
                         "the error is about 0.15 and it is NOT the 0.30 the paper test suggested "
                         "— a spring-steel sheet flexes under a paper shim and absorbs exactly the "
                         "difference. If the whole plate scrapes, this is too big; if the whole "
                         "plate is round strands, too small.")
    ap.add_argument("--layer-h", type=float, default=None,
                    help="LAYER 2's height, mm. Default is machine.SLICER_LAYER_H. This exists "
                         "because layer 2's whole job here is to be THE BUCKET'S second layer, and "
                         "on 2026-08-07 the bucket's layer height became a choice. A ladder whose "
                         "second layer is 0.24 tells you nothing about a bucket whose second layer "
                         "is 0.48: it is the layer-1-to-layer-2 RELATIONSHIP being tested, not "
                         "layer 1 alone. Checked against machine.SLICER_LAYER_HEIGHTS, because a "
                         "height no profile offers has never been laid on this machine.")
    ap.add_argument("--cell", type=float, default=40.0, help="cell side, mm")
    ap.add_argument("--w1", type=float, default=2.0,
                    help="target LANDED width of a layer-1 line, mm. Oleg's number. Stated as a "
                         "width because a width is what callipers measure; a flow multiplier can "
                         "only be checked by rerunning the arithmetic that produced it.")
    ap.add_argument("--pitch", type=float, default=1.6,
                    help="raster pitch, both layers. 1.6 is the bucket floor's own pitch.")
    ap.add_argument("--speed", type=float, default=machine.DEFAULT_SPEED, help="layer 2, mm/s")
    ap.add_argument("--speed1", type=float, default=25.0,
                    help="layer 1, mm/s. Half the north star, which Oleg asked for on 2026-08-06 "
                         "(\"may he half the speed?\") — a slower bead has longer to wet the plate.")
    ap.add_argument("--fan", type=float, default=1.0,
                    help="part-cooling fraction 0..1 for LAYER 2, matching what the bucket runs "
                         "(--fan 1). Layer 1 always keeps machine.fan_first_layer(), so the plate "
                         "weld is never chilled. This exists because the first version of this "
                         "file ran M106 S0 end to end and layer 2 slumped for want of cooling, "
                         "which reads as over-extrusion and is not.")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    material = a.material or machine.LOADED[a.printer]
    temp = machine.MATERIAL_TEMP[material]
    bed = machine.bed_for(material, a.printer)
    bx, by = machine.BED[a.printer]
    press = machine.PRESS_HARD                      # 0.10 — R1's number and the bucket's
    lh = machine.SLICER_LAYER_H if a.layer_h is None else a.layer_h
    if not any(abs(lh - h) < 1e-9 for h in machine.SLICER_LAYER_HEIGHTS):
        sys.exit(f"REFUSING TO EMIT: --layer-h {lh:g} is not one of the heights this machine's "
                 f"profiles offer ({', '.join(f'{h:g}' for h in machine.SLICER_LAYER_HEIGHTS)}).")
    bw = machine.SLICER_LINE_W                      # 0.82
    # LAYER 1 MUST CARRY THE BODY'S FLOW, AND --w1 IS A WIDTH, SO IT GOES STALE WHEN --layer-h MOVES.
    # This is the defect that cost a print on 2026-08-07: `--w1 2` carried from a 0.24 command into a
    # 0.48 one lays 0.51x the body bead, and the PRIME is metered at layer 1's rate, so the plate
    # showed thin unwelded strands in the first eight seconds. A ladder built to MEASURE a first
    # layer must not itself be able to starve one. (Placed after `bw` deliberately: the first
    # version of this check sat beside the --layer-h resolution above and referenced `bw` two lines
    # before it existed.)
    # THE TOLERANCE IS NOT SLOPPINESS, IT IS THE DIFFERENCE BETWEEN A GUARD AND A NUISANCE.
    # The first version compared against an exact 1.0 and refused --w1 2.62 at --layer-h 0.32:
    # 2.62 x 0.10 = 0.2620 against a 0.82 x 0.32 = 0.2624 bead, which is 0.9985x -- full flow to any
    # precision that matters, and the operator would have to type 2.6244 to satisfy it. Worse, the
    # message printed "the width that carries full flow is 2.62mm, not 2.62", because both rounded
    # to the same two decimals. A guard that goes red on a correct value AND cannot state why is
    # how a gate earns a reputation for crying wolf and gets switched off.
    # 1% is well inside the real failure this catches, which was 0.51x -- half.
    _ratio = (a.w1 * press) / (bw * lh)
    if _ratio < 0.99:
        _need = bw * lh / press
        sys.exit(f"REFUSING TO EMIT: layer 1 would carry {a.w1*press:.4f}mm2/mm against the body's "
                 f"{bw*lh:.4f}mm2/mm bead = {_ratio:.3f}x. At --layer-h {lh:g} the width that "
                 f"carries full flow is {_need:.3f}mm, and --w1 is {a.w1:.3f}mm. This ladder exists "
                 f"to measure a first layer; it must not be able to starve one.")

    for nm, v in (("--speed", a.speed), ("--speed1", a.speed1)):
        if v > machine.MAX_SPEED + 1e-9:
            sys.exit(f"REFUSING TO EMIT: {nm} {v:g} is above the {machine.MAX_SPEED:g} mm/s north "
                     f"star, which is a ceiling. Slower is legitimate; faster is not.")

    hts = [float(s) for s in a.heights.split(",") if s.strip()]
    # A POSITIVE OFFSET IS THE DEFECT, NOT A CORRECTION FOR IT: it lifts the nozzle further from
    # the plate. Refused here because validate.py cannot see SET_GCODE_OFFSET at all — R1 goes on
    # reading the commanded Z and passing, which is exactly the blindness that let three bucket
    # starts print half a millimetre in the air.
    if any(h <= 0 for h in hts):
        sys.exit(f"REFUSING TO EMIT: --heights contains a non-positive value {hts}.")
    if len(hts) > len(DIGIT) - 1:
        sys.exit(f"REFUSING TO EMIT: {len(hts)} cells but only single digits are drawn.")
    # A HEIGHT BECOMES AN OFFSET. Commanded Z never moves off PRESS_HARD, so the only way to reach
    # a different real height is to move where Z zero is: offset = height - PRESS_HARD - zerr.
    offs = [round(h - press - a.zerr, 4) for h in hts]
    # A POSITIVE OFFSET LIFTS THE NOZZLE ABOVE THE MACHINE'S OWN ZERO. That is the state the three
    # cancelled bucket starts printed in, and validate.py is blind to it — R1 reads the commanded
    # Z0.100 and passes whatever the plate is actually doing. Refused at the source instead.
    # A POSITIVE OFFSET USED TO BE REFUSED HERE. IT IS NOW ALLOWED, IN THIS FILE ONLY, AND THE
    # REASON IS EVIDENCE RATHER THAN CONVENIENCE.
    #
    # The refusal's premise was that positive lifts the nozzle away from the plate, "which is the
    # defect, not a test of it" -- true of a PART, and it is still refused in machine.zoff_for()
    # where parts get their offset. But on 2026-08-07 Oleg read a ladder and said "5 is closest to
    # truth": cell 5 is the 0.250mm first layer at offset +0.000, the machine's own UNCORRECTED
    # zero, and he then asked to go higher still. That is a request this file existed to serve and
    # could not.
    #
    # A LADDER IS A TEST BY DEFINITION -- it already declares '; Z_LADDER=1' and validate.py's
    # layer1_excuse() lets it visit gaps nothing has proven. Gaps LARGER than the press are gaps
    # nothing has proven. Refusing them made this tool unable to explore the half of the axis the
    # plate had just pointed at.
    #
    # It is announced rather than silent, and only the cells that need it are named.
    hi = [(h, o) for h, o in zip(hts, offs) if o > 1e-9]

    # THE TWO FAN REGIMES, NAMED. fan1 protects the weld to the plate; fan2 is whatever the bucket's
    # body runs at, because a second layer laid without the bucket's cooling is not the bucket's
    # second layer however exactly its flow matches.
    fan1 = machine.fan_first_layer(material)
    fan2 = max(0.0, min(1.0, a.fan))
    # LAYER 1'S RATE IS PER CELL, AND THAT IS THE WHOLE CORRECTION. The first version of this file
    # metered every cell for a 0.10 gap and then printed cells at 0.15, 0.20, 0.25 — so the taller
    # cells were UNDER-FILLED, landing 1.33mm, 1.00mm and 0.80mm on a 1.6mm pitch instead of the
    # 2.00mm they were labelled with. Oleg, seeing it: "I dont know what you measuring with that 5
    # numbers but first layer was getting thinner as thiner, why?" — because the material stayed
    # still while the gap moved. Scaling e with the cell's own height makes every cell land the
    # SAME width and be equally solid, which leaves the height as the only variable on the plate.
    def e1_for(h):
        return machine.layer1_rate(a.w1, h)   # ONE implementation, machine.py
    e2 = bw * lh / A_FIL                            # layer 2: the bucket's own bead, unchanged
    mm2_2 = bw * lh
    f1, f2 = round(a.speed1 * 60), round(a.speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    n = len(hts)

    # LAYOUT. Cells left to right with the digit above each. Stride is derived from the plate so a
    # wider --cell cannot silently overlap its neighbour — the one class of bug a per-move
    # validator cannot see, and it crashed a sequential plate once already.
    stride = (bx - 40.0) / n
    if stride < a.cell + 8.0:
        sys.exit(f"REFUSING TO EMIT: {n} cells of {a.cell:g}mm need {n*(a.cell+8):.0f}mm and the "
                 f"plate has {bx-40:.0f}mm of usable width. Shorten --cell or drop a cell.")
    x0, y0 = 20.0, (by - a.cell) / 2.0 - 12.0
    dw, dh = 11.0, 18.0                             # digit box
    dy = y0 + a.cell + 10.0                         # digit sits clear above its cell

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.out,
                       f"zladder_{a.printer}_{material}_{n}cell_w{a.w1:g}_p{a.pitch:g}.gcode")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    L = []
    w = L.append

    w(f"; Z LADDER — {n} numbered cells, real first-layer heights {a.heights}mm, reached by "
      f"offset against a measured Z-zero error of {a.zerr:+.3f}mm")
    w(f"; PRINTER={a.printer}")
    # THE INVOCATION, VERBATIM, SO THE PLATE CAN REGENERATE ITSELF. Without it a file can
    # only be reproduced by GUESSING at its filename encoding, and any parameter not
    # consciously retyped on the next run silently reverts to its DEFAULT -- the mechanism
    # behind Oleg's "why we getting this bug back every second print" on 2026-08-07.
    # sys.argv and NOT a reconstruction from the parsed args: a reconstruction prints what
    # the parser DECIDED, which is the very layer that turns an omitted flag into a default
    # and hides the omission. This records what a human actually typed.
    w(f"; CMD={' '.join(shlex.quote(s) for s in [os.path.basename(sys.argv[0])] + sys.argv[1:])}")
    w(f"; MATERIAL={material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={a.speed:.4f}")
    w(f"; SPEED_LAYER1={a.speed1:.4f}")
    w(f"; FLOW={mm2_2 * a.speed:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    # THE WIDTH IS THE CONSTANT HERE AND THE GAP IS THE VARIABLE, so the stamp must not name a
    # single gap. It used to say "pressed into the 0.1 gap" on a file whose cells deliberately land
    # 0.05 to 0.25, and validate.py R9b caught it correctly: the stamp names the gap it was metered
    # for, and an offset saying otherwise means somebody changed one of the two and not the other.
    # That check is right and the LIE was ours -- this file has five gaps by construction. Stating
    # the RANGE means R9b finds no single-gap claim to cross-examine, which its own comment says is
    # not a failure, while R9's weld check stays governed by '; Z_LADDER=1' where it belongs.
    w(f"; LAYER1_WIDTH={a.w1:.2f}mm landed in EVERY cell ({_ratio:.2f}x the body's own "
      f"{bw*lh:.4f}mm2/mm bead). THE GAP IS THE VARIABLE, swept {min(hts):g}..{max(hts):g}mm by "
      f"offset; the material scales with it so the width stays constant and the gap is the only "
      f"difference between cells.")
    w(f"; PRINT_TEMP={temp}")
    _cap = machine.flow_cap(material, a.printer)
    w(f"; FLOW_DERATE=this file reproduces the BUCKET's operating point on purpose, so it carries "
      f"the bucket's derate: a {machine.NOZZLE:g} nozzle laying the slicer's "
      f"{bw:g}x{lh:g} bead at {a.speed:g} mm/s delivers {mm2_2*a.speed:.2f} mm3/s against the "
      f"{_cap:g} cap. Reaching the cap would mean WIDENING the bead, and the bucket's wall "
      f"thickness IS its bead. A test that ran at a different flow would not be testing the bucket.")
    w(";")
    w("; ---------------- WHAT THIS IS ----------------")
    w(f"; {n} cells of {a.cell:g}x{a.cell:g}mm, each printed TWICE. COMMANDED Z NEVER MOVES: every")
    w(f"; cell writes Z{press:.3f} for layer 1 and Z{press+lh:.3f} for layer 2. What changes is")
    w("; SET_GCODE_OFFSET, which moves where Z zero IS, so each cell's first layer lands at a")
    w(f"; different REAL height -- and the material scales with that height, so all {n} land the")
    w(f"; same {a.w1:.2f}mm wide and the height is the only thing that differs.")
    w(f";   layer 1  {a.pitch:g}mm pitch, {a.w1/a.pitch:.2f}x coverage in EVERY cell, "
      f"{a.speed1:g} mm/s, fan {fan1*100:.0f}%")
    w(f";   layer 2  the SAME pitch turned 90 deg, one layer height above its own cell's layer 1, "
      f"at the bucket's own {bw:g}x{lh:g} bead, {a.speed:g} mm/s, fan {fan2*100:.0f}%")
    w(";            — bucket_latch's cross-latch floor, cell for cell")
    w(";")
    for i, h in enumerate(hts):
        w(f";   cell {i+1}  first layer {h:.3f}mm REAL, offset {offs[i]:+.3f}, {a.w1*h:.3f} mm2/mm "
          f"({a.w1*h/mm2_2:.2f}x the body's bead)")
    w(";")
    w("; WHY THE MATERIAL SCALES AND THE FIRST VERSION OF THIS FILE WAS WRONG. It metered every")
    w("; cell for a 0.10 gap and then printed cells at 0.15, 0.20 and 0.25, so the taller cells were")
    w("; UNDER-FILLED — landing 1.33, 1.00 and 0.80mm on a 1.6mm pitch while being labelled 2.00.")
    w("; Only the two cells that never printed would have been solid. A ladder whose rungs are not")
    w("; comparable is not a measurement.")
    w(";")
    w("; Z ZERO HOMES 0.15mm HIGH, measured off a PRINTED LADDER: offset -0.15 laid a clean first")
    w(";   layer, offset -0.20 dragged the nozzle through material it had just laid.")
    w("; RETRACTED, and printed here so no plate carries the old number: this header used to say")
    w(";   ~0.30mm, from paper sheets slid under a hot nozzle. That was wrong by 2x. The")
    w(";   spring-steel sheet FLEXES under the shim and absorbs the very gap being measured, so a")
    w(";   feeler on a flexible plate reads the plate. machine.ZERR['k2plus'] is the authority.")
    w(";")
    w("; READ IT: peel a corner of each cell. Welded fights back and leaves colour on the sheet;")
    w("; not welded lifts in one piece with a glossy underside. Then look at layer 2 — it should")
    w("; sit as a clean grid, not drag or ball up. The best cell's NUMBER is the bucket's offset.")
    w("; MATERIAL_PLACEHOLDER")
    _mat_line = len(L) - 1
    # SEQUENTIAL, DECLARED. These really are separate parts printed one after another: each cell is
    # finished to its second layer before the next one starts, so Z legitimately drops from 0.34
    # back to 0.10 at a new XY. Without the stamp the Z-plough guard reads that as the nozzle diving
    # into finished material, which is the right default for one continuous part and the wrong one
    # here. The stamp does NOT relax the checks that matter: a travel still may not extrude, and
    # parts still may not share ground.
    # THIS FILE IS THE COUPON R9 POINTS AT, AND IT HAS TO SAY SO. Without this stamp R9 refuses the
    # ladder for printing an unproven first layer -- which is literally its purpose -- while its own
    # failure message reads "Print zladder.py, read the plate, then cite the cell it welded on".
    # The gate told the operator to print the tool it then refused. A bootstrap deadlock, found
    # 2026-08-07 by running the ladder at a new layer height.
    #
    # THE EXEMPTION ALREADY EXISTED IN validate.py (layer1_excuse, '; Z_LADDER=1') and this
    # generator never emitted it. It is DECLARED AND COUNTED, not a trust-me flag: validate measures
    # the file's own moves and requires at least THREE different first-layer heights at one width,
    # so a part that stamps this is refused and told why. FLOW_TEST=1 sets the same precedent for
    # the flow cap.
    w("; Z_LADDER=1")
    # POSITIVE OFFSETS ANNOUNCED, NEVER SILENT. A part is refused one by machine.zoff_for(); a
    # ladder may visit them because a gap larger than the press is still a gap nothing has proven,
    # and on 2026-08-07 the plate pointed at exactly that half of the axis.
    if hi:
        w(f"; ABOVE THE MACHINE'S OWN ZERO: {len(hi)} of {n} cells lift the nozzle rather than press "
          f"it, which a PART may never do.")
        for _h, _o in hi:
            w(f";   height {_h:.3f}mm -> offset {_o:+.3f}  ({_o:+.3f}mm ABOVE the uncorrected zero)")
        w(f";   Oleg 2026-08-07, having read the previous ladder: \"5 is closest to truth\" (cell 5 "
          f"was 0.250mm at offset +0.000, the")
        w(f";   uncorrected machine) and \"keep the nozel slighly height for first layer\". The "
          f"refusal that used to sit here")
        w(f";   assumed positive was always the defect. His plate falsified that, so this file "
          f"explores it and says so.")
    w(f"; SEQUENTIAL={n} numbered cells, lifted hops between, nothing stacked across cells")
    w(";")

    w("M82")
    w("G90")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    # R7: the nozzle probes at PRINT temperature. Cold it is SHORTER, so Z zero records high and the
    # hot tip then grows down into the gap — the direction was got backwards once and cost a layer.
    w("G28")
    # ALWAYS EMITTED, INCLUDING THE ZERO. SET_GCODE_OFFSET survives a job — the K2's own start_print
    # macro zeroes it for exactly this reason — so a file that only wrote it when non-zero would
    # inherit whatever the previous print or a hand command left behind, and cell 1 would silently
    # be testing someone else's number.
    # THE ONE CORRECTION, EMITTED ALWAYS INCLUDING A ZERO. SET_GCODE_OFFSET survives a job -- the
    # K2's own start_print macro zeroes it for exactly this reason -- so a file that only wrote it
    # when non-zero would inherit whatever the last print or a hand command left behind, and cell 1
    # would silently be testing someone else's number.
    w("SET_GCODE_OFFSET Z=0                 ; start from the machine's own zero, not last run's")
    w(f"M190 S{bed if a.printer == 'k2plus' else machine.bed_start(material, bed):.0f}")
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    # LAYER 1 GETS NO FAN, AND IT IS SET EXPLICITLY RATHER THAN LEFT ALONE. A previous print can
    # leave the part fan running, and chilling a bead while its weld to the plate is still forming
    # is the cheapest possible way to lose a first layer — the one thing this file exists to
    # measure. Layer 2 turns the fan up to the BUCKET's own body value, per cell; see below.
    w(f"M106 S{int(round(fan1 * 255))}"
      f"   ; layer 1: {fan1*100:.0f}% — the plate weld is the job")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")

    # ONE SHARED PRIME, machine.prime(). Was the Z2 lift + 20mm free-air stationary purge Oleg
    # photographed on 2026-08-06; validate.py R10 refuses that shape on the emitted file now.
    # THE RATE IS METERED FOR THE UNCORRECTED GAP ON PURPOSE. Every cell below sets its own
    # SET_GCODE_OFFSET, and the prime runs BEFORE the first of them, so the gap the prime is
    # actually laid into is the machine's own zero plus --zerr, not any cell's. Metering it for
    # PRESS_HARD would have it land narrow for the same reason the first version of this file made
    # the taller cells thin -- the material staying still while the gap moves. This is the one file
    # in the fleet where the prime cannot be the part's own first layer, because the whole point of
    # the part is that its first layer is six different things.
    machine.prime(w, printer=a.printer, z=press,
                  rate=machine.layer1_rate(a.w1, press + a.zerr), feed=f1, travel_feed=travel_f,
                  avoid=(("rect", x0, y0, x0 + (n - 1) * stride + a.cell, dy + dh),),
                  near=(x0, dy))
    w("; BODY_START")

    E = 0.0

    # HOP HEIGHT IS THE PART'S AGAIN. It used to be max(press + lh, 2.0) + 1.0, and the 2.0 floor
    # was not about the part -- the part tops out at 0.34. It was clearing the PRIME purge, which
    # stood at Z2 by design so it could not collar the tip, and validate.py caught the version
    # without the floor: 39 travels at Z1.34 against material standing at Z2.0. machine.prime()
    # leaves nothing standing above the press gap, so the floor goes with the thing it protected
    # against; keeping it would be guarding a wall that is not there.
    safe_z = press + lh + 1.0

    def hop(tx, ty, note):
        w(f"G0 Z{safe_z:.3f} F1800   ; HOP lift, clear of the part")
        w(f"G0 X{tx:.3f} Y{ty:.3f} F{travel_f}   ; HOP {note}")

    for i, h in enumerate(hts):
        cx = x0 + i * stride
        z1, z2 = press, press + lh          # COMMANDED Z, identical in every cell
        o = offs[i]
        e1 = e1_for(h)
        w(f"; ================ cell {i+1} of {n}: first layer {h:.3f}mm REAL "
          f"(commanded Z{z1:.3f}, offset {o:+.3f}), {a.w1*h:.3f} mm2/mm ================")
        # MOVE=1 applies the shift NOW rather than at the next Z word. The next word is a flat
        # travel, so without it the digit and part of the cell would print at the PREVIOUS cell's
        # offset — a ladder one rung out of step with its own printed labels, which is worse than
        # no labels at all.
        w(f"SET_GCODE_OFFSET Z={o:.3f} MOVE=1   ; real first layer {h:.3f}mm")
        # BACK TO THE LAYER-1 FAN FOR THIS CELL. The previous cell left it at the body value, and a
        # cell whose first layer was cooled while its neighbour's was not is not a ladder rung, it
        # is a second variable.
        w(f"M106 S{int(round(fan1 * 255))}   ; layer 1 of this cell: {fan1*100:.0f}%")

        # ---- the digit, at this cell's first-layer settings, so the number is itself a sample
        dx = cx + (a.cell - dw) / 2.0
        segs = DIGIT[str(i + 1)]
        w(f"; ---- cell {i+1} digit '{i+1}': {len(segs)} segments at Z{z1:.3f}, {a.speed1:g} mm/s")
        for k, s in enumerate(segs):
            u0, v0, u1, v1 = SEG[s]
            ax, ay = dx + u0 * dw, dy + v0 * dh
            bx_, by_ = dx + u1 * dw, dy + v1 * dh
            hop(ax, ay, f"to digit {i+1} segment '{s}'")
            w(f"G1 F600 Z{z1:.3f}")
            E += math.hypot(bx_ - ax, by_ - ay) * e1
            w(f"G1 F{f1} X{bx_:.3f} Y{by_:.3f} E{E:.5f} ; segment '{s}'")

        # ---- layer 1: raster along X, metered to land --w1 wide in the press gap
        n1 = int(a.cell / a.pitch) + 1
        hop(cx, y0, f"to cell {i+1} layer 1")
        w(f"G1 F600 Z{z1:.3f}")
        w(f"; ---- cell {i+1} layer 1: {n1} passes at Z{z1:.3f}, {a.pitch:g}mm pitch, "
          f"{a.w1*h:.3f} mm2/mm so it lands {a.w1:.2f}mm wide -- the SAME width as every other "
          f"cell, which is what makes the heights comparable, {a.speed1:g} mm/s")
        ex, ey = cx, y0
        for p in range(n1):
            y = y0 + p * a.pitch
            xs, xe = (cx, cx + a.cell) if p % 2 == 0 else (cx + a.cell, cx)
            if p:
                E += a.pitch * e1
                w(f"G1 F{f1} X{xs:.3f} Y{y:.3f} E{E:.5f}")
            E += a.cell * e1
            w(f"G1 F{f1} X{xe:.3f} Y{y:.3f} E{E:.5f}")
            ex, ey = xe, y

        # ---- layer 2: the same pitch turned 90 deg, at the BUCKET's bead and the north star.
        # NO HOP AND NO TRAVEL. Layer 2 starts at the exact XY where layer 1 finished — the raster
        # is walked from whichever corner the head is already standing on — so the only thing
        # between the two layers is one Z word. That is not tidiness: a travel here would run at
        # layer height directly over the cell whose adhesion this file exists to measure, and
        # dragging the nozzle across a first layer is one of the ways to lose one.
        n2 = int(a.cell / a.pitch) + 1
        w(f"G1 F600 Z{z2:.3f}")
        # THE FAN IS PART OF "THE BUCKET'S SETUP", AND LEAVING IT OFF WAS A REAL MISS.
        # Oleg, 2026-08-06, watching cell 2 come off: "Why second has so much extrusion on second
        # layer? I said to mimic bucket setup for second layer". The FLOW was already the bucket's
        # to three decimals — what was not was the cooling. bucket_towers turns the part fan up to
        # its body value on layer 2 (`if li == 1`), and this file was running M106 S0 end to end, so
        # every second layer here was laid hot with nothing freezing it. Same material, no cooling,
        # and it slumps — which looks exactly like over-extrusion and is not.
        # It is re-issued per cell because M106 is machine state and a reader should be able to open
        # any cell in this file and see the whole regime it printed under.
        w(f"M106 S{int(round(fan2 * 255))}   ; layer 2: {fan2*100:.0f}% — the bucket's own body fan")
        w(f"; ---- cell {i+1} layer 2: {n2} passes at Z{z2:.3f}, PERPENDICULAR, bucket bead "
          f"{bw:g}x{lh:g}, {a.speed:g} mm/s — continues from layer 1's last corner, no travel")
        xs2 = list(range(n2)) if abs(ex - cx) < abs(ex - (cx + a.cell)) else list(range(n2))[::-1]
        y_hi = abs(ey - (y0 + a.cell)) < abs(ey - y0)
        for q, p in enumerate(xs2):
            x = cx + p * a.pitch
            if q % 2 == 0:
                ys_, ye = (y0 + a.cell, y0) if y_hi else (y0, y0 + a.cell)
            else:
                ys_, ye = (y0, y0 + a.cell) if y_hi else (y0 + a.cell, y0)
            if q:
                E += a.pitch * e2
                w(f"G1 F{f2} X{x:.3f} Y{ys_:.3f} E{E:.5f}")
            E += a.cell * e2
            w(f"G1 F{f2} X{x:.3f} Y{ye:.3f} E{E:.5f}")

    w("; ---- done")
    w("SET_GCODE_OFFSET Z=0                 ; hand the machine back at its own zero")
    w("M107"); w("M104 S0"); w("M140 S0")
    w("G0 Z45 F900")
    w(f"G0 X10 Y{by-10:.0f} F{travel_f}")
    w("M84")

    seg_mm = sum(math.hypot(SEG[s][2] - SEG[s][0], SEG[s][3] - SEG[s][1]) for s in DIGIT['8'])
    l1_mm = n * ((int(a.cell / a.pitch) + 1) * a.cell + int(a.cell / a.pitch) * a.pitch)
    l2_mm = l1_mm
    mins = l1_mm / a.speed1 / 60.0 + l2_mm / a.speed / 60.0
    vol = E * A_FIL / 1000.0
    L[_mat_line] = (f"; MATERIAL {vol*1.24:.1f}g / {vol:.2f}cm3, ~{mins:.0f} min of extrusion — "
                    f"measured from this file's own final E, not from a nominal bead")

    open(out, "w").write("\n".join(L) + "\n")
    print(out)
    print(f"  {n} cells, first-layer heights {a.heights}")
    print(f"  Z-zero error assumed {a.zerr:+.3f}mm (MEASURED off the plate, not by feel)")
    print(f"  commanded Z is Z{press:.3f}/Z{press+lh:.3f} in EVERY cell; the offset does the work")
    for i, h in enumerate(hts):
        print(f"    cell {i+1}: first layer {h:.3f}mm REAL  offset {offs[i]:+.3f}  "
              f"{a.w1*h:.3f} mm2/mm -> lands {a.w1:g}mm ({a.w1/a.pitch:.2f}x coverage)")
    print(f"  layer 2 everywhere: bucket bead {bw:g}x{lh:g} PERPENDICULAR, {mm2_2:.3f} mm2/mm, "
          f"{a.speed:g} mm/s, fan {fan2*100:.0f}%")
    print(f"  ~{mins:.0f} min   {vol:.2f}cm3")


if __name__ == "__main__":
    main()
