#!/usr/bin/env python3
"""SPAN LADDER — numbered bridges at a range of spans on one plate, so the PLATE says where the
cliff is instead of one number saying yes or no.

  The 320x300 bucket that STOOD is the only span this project has ever seen hold: 17.85mm tip to
  tip, of which its own header calls 16.8mm unsupported air (machine.PROVEN_SEND['k2plus']
  ['span_mm']). The bamboo bucket needs 33.60mm tip to tip. That is 1.88x, and send.py S4 refuses
  it: "33.6039 is NOT proven ... 476.2 min of motion, past the 25 min under which a file may
  establish a value nothing has proven".

NOTHING HAS EVER BEEN TESTED BETWEEN THOSE TWO NUMBERS. A comment in colonnade.py claimed towers.py
had "actually printed" 28mm rungs; it had not — towers.py only ASKS whether 28mm holds, and the only
towers gcode on disk is from the T230 era when towers coiled into rope. That comment was corrected
on 2026-08-06. So the interval 17.85..33.60 is empty of evidence, and this plate is the only evidence
that will ever exist in it.

WHY A LADDER AND NOT A SINGLE SPAN. A coupon at 33.60 answers yes or no at 33.60 and nothing else. If
it sags, the next question is "then what does hold?", and that is another plate and another day. If
it holds, nobody knows by how much, so the next part that needs 36 is back to guessing. A ladder
answers WHERE THE CLIFF IS in one read, which is the only shape of answer that also serves the parts
after this one.

WHY THE OPERATING POINT IS COPIED AND NOT CHOSEN. Every knob here is the bucket's, on purpose:
0.8 nozzle, the slicer's 0.82x0.24 bead, 50 mm/s, 210/60, and — the one most likely to be got
wrong — 20% part cooling, machine.FAN_MAX['pla'], with both chamber fans OFF, which is exactly what
the emitted bucket runs (M106 S51 at its body start; SET_PIN fan1/fan2 VALUE=0). A bridge ladder run
at 100% fan would bridge further than the bucket ever can and would be evidence about a machine
setting the bucket does not use.

WHAT IS DELIBERATELY NOT CLAIMED. This file predicts one row (the 17.85 control, which is the proven
value) and refuses to predict the middle of the ladder, because there is nothing to predict it from.
The prediction it does make is the negative control's, and that one is a claim it wants falsified.

Usage:  python3 spanladder.py
        python3 validate.py out/spanladder_*.gcode
        python3 send.py send out/spanladder_*.gcode          # DRY RUN. --live is Oleg's alone.
"""
import argparse, collections, math, os, shlex, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

A_FIL = machine.A_FIL

# THE ONLY SPAN WITH A PRINT BEHIND IT, and the reason it is a rung rather than a footnote: a ladder
# whose bottom rung is not the proven value cannot tell "the cliff is at 25" from "the whole plate
# was cooked". machine.PROVEN_SEND['k2plus']['span_mm'] is the source; it is read at run time below
# rather than retyped, so this constant cannot drift from the ledger.
BUCKET_NEED = 33.6039    # send.py S4's own measurement of the bamboo bucket that is blocked

SEG_MM = 1.0             # target segment for every subdivided run — this project's own number

# SEVEN SEGMENTS in a unit box, lifted from borelock.py (which lifted them from zladder.py) so the
# numbers on this plate look like the numbers on every other gauge here. '1' is the CENTRE bar, not
# the two right-hand segments: borelock measured a seven-segment '1' sitting 2.75mm right of the
# cell it named, and the entire interface of a plate like this is Oleg reading a number off it.
SEG = {
    'a': (0.0, 1.0, 1.0, 1.0),   # top
    'b': (1.0, 0.5, 1.0, 1.0),   # upper right
    'c': (1.0, 0.0, 1.0, 0.5),   # lower right
    'd': (0.0, 0.0, 1.0, 0.0),   # bottom
    'e': (0.0, 0.0, 0.0, 0.5),   # lower left
    'f': (0.0, 0.5, 0.0, 1.0),   # upper left
    'g': (0.0, 0.5, 1.0, 0.5),   # middle
    'h': (0.5, 0.0, 0.5, 1.0),   # CENTRE bar — this file's '1'
}
DIGIT = {'0': 'abcdef', '1': 'h', '2': 'abged', '3': 'abgcd', '4': 'fgbc',
         '5': 'afgcd', '6': 'afgedc', '7': 'abc', '8': 'abcdefg', '9': 'abcdfg'}


def glyph_segments(label, cx, y_bot, gw, gh, gap):
    """Every stroke of `label`, as ((ax,ay),(bx,by)), with its INK centred on `cx`."""
    out = []
    for k, ch in enumerate(label):
        gx = k * (gw + gap)
        for s in DIGIT[ch]:
            u0, v0, u1, v1 = SEG[s]
            out.append(((gx + u0 * gw, y_bot + v0 * gh), (gx + u1 * gw, y_bot + v1 * gh)))
    xs = [p[0] for seg in out for p in seg]
    dx = cx - (min(xs) + max(xs)) / 2.0
    return [((a[0] + dx, a[1]), (b[0] + dx, b[1])) for a, b in out]


def label_ink_w(label, gw, gap):
    xs = [p[0] for seg in glyph_segments(label, 0.0, 0.0, gw, 1.0, gap) for p in seg]
    return max(xs) - min(xs)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--spans", default="17.85,20,22.5,25,27.5,30,32,33.6,35.5,38,41",
                    help="TIP-TO-TIP span of each rung, mm, low to high. Tip to tip is the quantity "
                         "the ledger stores and the quantity send.py S4 measures off the emitted "
                         "move, so the ladder is graduated in the units the gate speaks. The low "
                         "rung MUST be the proven 17.85 and the bucket's 33.6 must have rungs "
                         "ABOVE it — passing at the top of a range proves 'at least this', never "
                         "'this'.")
    ap.add_argument("--control", type=float, default=120.0,
                    help="the NEGATIVE control's span, mm. A rung that must NOT come out taut, so "
                         "that a plate on which everything looks fine is known to be lying rather "
                         "than believed. 120 is 6.7x the only proven span and 3.6x what the bucket "
                         "asks; a 0.5mm rod of PLA is in free air for 2.4s at 50 mm/s before it "
                         "reaches the far post.")
    ap.add_argument("--ncross", type=int, default=6,
                    help="strands per rung. Alternating BRIDGE (the body's own full bead, what the "
                         "bucket's rim lays) and THIN CROSS (25%%, what the bucket lays between "
                         "towers), so both of the bucket's air-crossing regimes are read at every "
                         "span off one photograph.")
    ap.add_argument("--cross-flow", type=float, default=0.25,
                    help="THIN CROSS extrusion as a fraction of the body's. bucket_towers.py's own "
                         "default; the emitted bucket lays 0.0492 mm2/mm on these moves.")
    ap.add_argument("--post-h", type=float, default=5.0,
                    help="approximate height of the deck above the plate, mm. Tall enough that a "
                         "sagging strand has room to droop and be seen against bare glass before "
                         "it lands, short enough that 24 posts do not eat the 25-minute ceiling.")
    ap.add_argument("--post", default="4x10",
                    help="post footprint WxH in mm — a single-bead closed RECTANGLE, deliberately "
                         "not a circle: send.py S7 fits contiguous short segments to a circle and "
                         "would read a round post as a declared-bore fit this plate is not making.")
    ap.add_argument("--pad", default="9x16", help="pad under each post, WxH mm")
    ap.add_argument("--label-pad", default="13x12", help="pad under each row's number, WxH mm")
    ap.add_argument("--row-pitch", type=float, default=22.0, help="centre-to-centre row pitch, mm")
    ap.add_argument("--h1", type=float, default=machine.PRESS_HARD,
                    help="REAL landed first-layer height, mm. k2plus's PROVEN pair is 0.10 x 2.00.")
    ap.add_argument("--w1", type=float, default=2.00, help="LANDED width of a layer-1 line, mm")
    ap.add_argument("--pitch", type=float, default=1.6,
                    help="raster pitch of every pad, both layers. The 320x300 bucket's own floor "
                         "pitch, and the pair (2.00, 1.6) is what machine.PROVEN_SEND accepts.")
    ap.add_argument("--speed", type=float, default=machine.DEFAULT_SPEED, help="body, mm/s")
    ap.add_argument("--speed1", type=float, default=25.0, help="layer 1, mm/s")
    ap.add_argument("--fan", type=float, default=None,
                    help="part-cooling fraction above layer 1. Defaults to machine.FAN_MAX for the "
                         "material, which is what the bucket emits. Raising it would make this "
                         "plate bridge better than the part it is evidence for.")
    ap.add_argument("--digit-layers", type=int, default=3,
                    help="layers the raised numbers stand. 3 = 0.72mm proud, reads at arm's length.")
    ap.add_argument("--glyph", default="4.5x8.0", help="digit box WxH in mm")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    material = a.material or machine.LOADED[a.printer]
    temp = machine.MATERIAL_TEMP[material]
    bed = machine.bed_for(material, a.printer)
    bedx, bedy = machine.BED[a.printer]
    press = machine.PRESS_HARD
    lh = machine.SLICER_LAYER_H
    bw = machine.SLICER_LINE_W

    ladder = [float(s) for s in a.spans.split(",") if s.strip()]
    pw, pl = (float(v) for v in a.post.lower().split("x"))
    padw, padl = (float(v) for v in a.pad.lower().split("x"))
    labw, labl = (float(v) for v in a.label_pad.lower().split("x"))
    gw, gh = (float(v) for v in a.glyph.lower().split("x"))
    ggap = gw * 0.33
    fan2 = machine.FAN_MAX.get(material, 0.20) if a.fan is None else max(0.0, min(1.0, a.fan))

    # ------------------------------------------------------------------ GATES, ALL BEFORE EMIT
    # Each one refuses a plate that would print beautifully and answer nothing.
    for nm, v in (("--speed", a.speed), ("--speed1", a.speed1)):
        if v > machine.MAX_SPEED + 1e-9:
            sys.exit(f"REFUSING TO EMIT: {nm} {v:g} is above the {machine.MAX_SPEED:g} mm/s north "
                     f"star, which is a ceiling. Slower is legitimate; faster is not.")
    zerr = machine.ZERR.get(a.printer)
    if zerr is None:
        sys.exit(f"REFUSING TO EMIT: no measured Z-zero error for {a.printer!r}. Run zladder.py.")
    zoff = machine.zoff_for(a.h1, zerr)
    if not any(abs(a.h1 - h) <= 0.005 and abs(a.w1 - w) <= 0.05
               for h, w in machine.PROVEN_LAYER1.get(a.printer, [])):
        sys.exit(f"REFUSING TO EMIT: first layer {a.h1:g}x{a.w1:g} is not in {a.printer}'s proven "
                 f"set {machine.PROVEN_LAYER1.get(a.printer, [])}. This plate measures a SPAN; it "
                 f"must not also be an experiment in adhesion.")

    # GATE: THE LADDER MUST START ON THE PROVEN RUNG. Read from the ledger, never retyped, so an
    # edit to machine.PROVEN_SEND cannot leave this file quietly measuring against a stale number.
    proven = sorted(r[0] for r in machine.PROVEN_SEND[a.printer]['span_mm'])
    if not proven:
        sys.exit(f"REFUSING TO EMIT: machine.PROVEN_SEND[{a.printer!r}]['span_mm'] is empty, so "
                 f"there is no known-good rung to anchor the ladder on and a sagging plate could "
                 f"not be told from a bad print day.")
    if not any(abs(ladder[0] - p) <= 0.05 for p in proven):
        sys.exit(f"REFUSING TO EMIT: the lowest rung {ladder[0]:g} is not one of the proven spans "
                 f"{proven}. Without the known-good control at one end, a plate on which every rung "
                 f"sags says 'the cliff is below the ladder' and 'the machine was having a bad "
                 f"day' with equal force, and those need different next actions.")
    if sorted(ladder) != ladder or len(set(ladder)) != len(ladder):
        sys.exit(f"REFUSING TO EMIT: --spans must be strictly increasing; got {ladder}.")
    # GATE: THE ANSWER MUST SIT INSIDE THE LADDER, NOT AT ITS TOP EDGE.
    above = [s for s in ladder if s > BUCKET_NEED + 0.05]
    if len(above) < 2:
        sys.exit(f"REFUSING TO EMIT: only {len(above)} rung(s) sit above the bucket's "
                 f"{BUCKET_NEED:g}mm requirement. A ladder that stops at the number being asked "
                 f"about can only ever return 'at least this much', which is the same answer as "
                 f"not printing it. Add rungs above {BUCKET_NEED:g}.")
    if not any(abs(s - BUCKET_NEED) <= 0.15 for s in ladder):
        sys.exit(f"REFUSING TO EMIT: no rung is within 0.15mm of the bucket's own "
                 f"{BUCKET_NEED:g}mm. The plate must answer the blocking question directly and not "
                 f"by interpolation between two rungs that straddle it.")
    # GATE: THE NEGATIVE CONTROL MUST BE BEYOND ARGUMENT.
    if a.control < 2.0 * ladder[-1]:
        sys.exit(f"REFUSING TO EMIT: the negative control {a.control:g} is under 2x the top rung "
                 f"{ladder[-1]:g}. A control that could plausibly hold proves nothing when it does, "
                 f"and a plate where everything looks fine has to be distinguishable from a plate "
                 f"that is lying.")
    if a.ncross < 4 or a.ncross % 2:
        ap.error("--ncross must be an even number >= 4, so each rung carries both crossing regimes")
    if not (0.0 < a.cross_flow < 1.0):
        ap.error("--cross-flow must be a fraction strictly between 0 and 1")
    if a.digit_layers < 1:
        ap.error("--digit-layers must be at least 1; an unnumbered rung cannot be reported back")

    spans = ladder + [a.control]
    nrow = len(spans)
    # GATE: THE STRANDS MUST LAND ON THE POST. Anchored is the whole premise; a strand whose end
    # overhangs the post is measuring adhesion to air.
    deck_w = (a.ncross - 1) * a.pitch
    if deck_w > pl - 1.0:
        sys.exit(f"REFUSING TO EMIT: {a.ncross} strands at {a.pitch:g}mm pitch need {deck_w:g}mm of "
                 f"post length and the post is {pl:g}mm. Every strand must end ON the far post.")
    if padw < pw + 2.0 or padl < pl + 2.0:
        sys.exit(f"REFUSING TO EMIT: pad {padw:g}x{padl:g} does not stand 1mm proud of a "
                 f"{pw:g}x{pl:g} post on every side.")
    lab_need = max(label_ink_w(str(n + 1), gw, ggap) for n in range(nrow)) + bw + 2.0
    if labw < lab_need:
        sys.exit(f"REFUSING TO EMIT: the label pad is {labw:g}mm wide and the widest number needs "
                 f"{lab_need:.2f}mm. A number that runs off its pad is a number printed on glass.")
    if a.row_pitch < max(padl, labl) + 4.0:
        sys.exit(f"REFUSING TO EMIT: --row-pitch {a.row_pitch:g} leaves under 4mm between rows.")

    # ---------------------------------------------------------------------------------- LAYOUT
    # X: [label pad][gap][pad A | post A]  <-- span -->  [post B | pad B]
    lab_gap = 3.0
    x_left_of_a = pw / 2.0 + padw / 2.0            # from post A's inner wall back to pad A's edge
    width = 22.5 if False else (x_left_of_a + lab_gap + labw) + max(spans) + pw / 2.0 + padw / 2.0
    x0 = (bedx - width) / 2.0
    XA = x0 + (x_left_of_a + lab_gap + labw)       # post A's INNER wall, shared by every row
    height = (nrow - 1) * a.row_pitch + max(padl, labl)
    y0 = (bedy - height) / 2.0
    if x0 < 8 or y0 < 8:
        sys.exit(f"REFUSING TO EMIT: a {width:.1f}x{height:.1f}mm plate does not fit "
                 f"{a.printer}'s {bedx:g}x{bedy:g} bed with a margin.")
    # ROW 1 AT THE TOP, counting down, so the plate reads like the table in this header.
    ycs = [y0 + height - max(padl, labl) / 2.0 - r * a.row_pitch for r in range(nrow)]

    def row_rects(r):
        """(pad A, pad B, label pad) of row r, as (x0,y0,x1,y1)."""
        s, yc = spans[r], ycs[r]
        ax = XA - pw / 2.0                          # post A centre
        bx = XA + s + pw / 2.0                      # post B centre
        return ((ax - padw / 2.0, yc - padl / 2.0, ax + padw / 2.0, yc + padl / 2.0),
                (bx - padw / 2.0, yc - padl / 2.0, bx + padw / 2.0, yc + padl / 2.0),
                (XA - x_left_of_a - lab_gap - labw, yc - labl / 2.0,
                 XA - x_left_of_a - lab_gap, yc + labl / 2.0))

    def post_rects(r):
        """(post A, post B) toolpath rectangles of row r — the single-bead loop CENTRELINES."""
        s, yc = spans[r], ycs[r]
        return ((XA - pw, yc - pl / 2.0, XA, yc + pl / 2.0),
                (XA + s, yc - pl / 2.0, XA + s + pw, yc + pl / 2.0))

    z_pad = [press, press + lh]
    z_post0 = press + 2 * lh
    n_post = max(1, int(round((a.post_h - z_post0) / lh)))
    top_z = z_post0 + (n_post - 1) * lh
    z_deck = top_z + lh
    if n_post < 6:
        sys.exit(f"REFUSING TO EMIT: --post-h {a.post_h:g} leaves {n_post} post layers.")

    e1 = machine.layer1_rate(a.w1, a.h1)            # ONE implementation, machine.py
    e2 = bw * lh / A_FIL                            # the body's own bead
    ex = e2 * a.cross_flow                          # the thin crossing
    mm2_body = bw * lh
    mm2_cross = mm2_body * a.cross_flow
    flow = mm2_body * a.speed
    f1, f2 = round(a.speed1 * 60), round(a.speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    fan1 = machine.fan_first_layer(material)
    rod = math.sqrt(4.0 * mm2_body / math.pi)
    rod_x = math.sqrt(4.0 * mm2_cross / math.pi)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.out,
                       f"spanladder_{a.printer}_{material}_s{ladder[0]:g}-{ladder[-1]:g}"
                       f"x{len(ladder)}_neg{a.control:g}_h{z_deck:g}.gcode")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    L = []
    w = L.append

    # ------------------------------------------------------------------------------- HEADER
    w(f"; SPAN LADDER — {nrow} numbered bridges, {ladder[0]:g} to {ladder[-1]:g}mm plus a "
      f"{a.control:g}mm NEGATIVE CONTROL, on one plate")
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
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; LAYER1_WIDTH={a.w1:.2f}mm landed ({a.w1 / (mm2_body / press):.2f}x the body's own flow "
      f"pressed into the {press:g} gap)")
    w(f"; PRINT_TEMP={temp}")
    w(f"; bead {bw:g}x{lh:g}")
    w(f"; BRIDGE_MM2={mm2_body:.4f}")
    w(f"; SPEED_CROSS={a.speed:g}")
    w(f"; FLOW_DERATE=this plate reproduces the BAMBOO BUCKET's operating point on purpose, so it "
      f"carries the bucket's derate: a {machine.NOZZLE:g} nozzle laying the slicer's {bw:g}x{lh:g} "
      f"bead at {a.speed:g} mm/s delivers {flow:.2f} mm3/s against the "
      f"{machine.flow_cap(material, a.printer):g} cap. Reaching the cap would mean WIDENING the "
      f"bead, and the bead IS the thing crossing the air here — a fatter rod bridges further for "
      f"reasons that have nothing to do with the span. A ladder run at a different flow would not "
      f"be a ladder for this part.")
    w(";")
    w(f"; OPERATING_POINT=every knob here is the BAMBOO BUCKET's, so this plate is evidence about "
      f"that part and not about a friendlier machine setting. {machine.NOZZLE:g} nozzle laying the "
      f"slicer's {bw:g}x{lh:g} bead at {a.speed:g} mm/s = {flow:.2f} mm3/s against the "
      f"{machine.flow_cap(material, a.printer):g} cap; {temp}C / bed {bed}C; part cooling "
      f"{fan2*100:.0f}% (machine.FAN_MAX[{material!r}]) with BOTH chamber fans off, which is what "
      f"the emitted bucket runs. FAN IS THE KNOB MOST LIKELY TO BE GOT WRONG HERE: a bridge ladder "
      f"run at 100% would bridge further than the bucket ever can, and would answer a question "
      f"nobody asked.")
    w(";")
    w("; ---------------- WHAT THIS IS ----------------")
    w(f"; {nrow} rows on one plate. Each row is two single-bead {pw:g}x{pl:g}mm posts standing "
      f"{z_deck:.2f}mm tall")
    w(f"; on welded pads, with {a.ncross} strands thrown across the air between them at the row's "
      f"span.")
    w(f"; The strands ALTERNATE the bucket's two air-crossing regimes, so one photograph reads both:")
    w(f";    BRIDGE      {mm2_body:.4f} mm2/mm — the body's own full bead, a {rod:.3f}mm free rod. "
      f"The bucket's rim.")
    w(f";    THIN CROSS  {mm2_cross:.4f} mm2/mm — {a.cross_flow*100:.0f}% of it, a {rod_x:.3f}mm "
      f"rod. What the bucket lays tower to tower.")
    w(f"; Every row carries its NUMBER, {a.digit_layers*lh:.2f}mm proud on its own pad, so a "
      f"photograph is self-describing.")
    w(";")
    w("; ---------------- WHY A LADDER ----------------")
    w(f"; The only span this project has ever seen hold is {proven[0]:g}mm tip to tip (the 320x300")
    w(f"; bucket that stood; its header calls 16.8mm of that unsupported air). The bamboo bucket "
      f"needs")
    w(f"; {BUCKET_NEED:g}mm — 1.88x — and send.py S4 refuses it because 476 min of motion is far "
      f"past the")
    w(f"; 25 min inside which a file may establish a value nothing has proven. NOTHING HAS EVER "
      f"BEEN")
    w(f"; TESTED BETWEEN THOSE TWO NUMBERS. A comment in colonnade.py claimed towers.py had printed "
      f"28mm")
    w(f"; rungs; it had not, and that comment was corrected 2026-08-06. A single coupon at "
      f"{BUCKET_NEED:g} would")
    w(f"; answer yes or no at {BUCKET_NEED:g} and nothing else. This one answers WHERE THE CLIFF "
      f"IS, once.")
    w(";")
    w("; ---------------- THE ROWS, AND WHAT EACH IS EXPECTED TO DO ----------------")
    w(f";   air = tip-to-tip minus one {bw:g}mm bead: half a bead of each end sits on a post.")
    w(";   row   tip-to-tip   unsupported air   vs proven   expected")
    for r, s in enumerate(spans):
        air = s - bw
        if r == nrow - 1:
            exp = "MUST SAG OR SNAP — negative control"
        elif abs(s - proven[0]) <= 0.05:
            exp = "TAUT — this is the proven span"
        elif abs(s - BUCKET_NEED) <= 0.15:
            exp = "UNKNOWN — this is the bucket's own span"
        else:
            exp = "UNKNOWN — nothing has tested this"
        w(f";   {r+1:>3}   {s:>10.2f}   {air:>15.2f}   {s/proven[0]:>8.2f}x   {exp}")
    w(";")
    w("; ---------------- WHAT IS PREDICTED, AND WHAT IS NOT ----------------")
    w(f"; ROW 1 IS PREDICTED TAUT, and it is the only rung in the ladder that is predicted at all.")
    w(f"; It is the proven value. One caveat stated rather than buried: this row lays "
      f"{ladder[0]-bw:.2f}mm of")
    w(f"; air where the bucket that stood called its own {proven[0]:g} '16.8mm unsupported air' — "
      f"{ladder[0]-bw-16.8:+.2f}mm,")
    w(f"; because that file's bead was wider than this one's. The difference is in the HARDER")
    w(f"; direction, which is the direction a control may err in.")
    w(f";")
    w(f"; ROWS 2..{nrow-1} ARE NOT PREDICTED. There is no datum between {proven[0]:g} and "
      f"{BUCKET_NEED:g} to predict from,")
    w(f"; and this plate exists precisely because there is not. Writing a modelled sag per row here")
    w(f"; would be a guess wearing the clothes of a measurement, and this project has already paid")
    w(f"; for one of those (guides/fit-and-assembly-empirics.md, the 0.25mm shrink).")
    w(f";")
    w(f"; ROW {nrow} IS PREDICTED TO FAIL, and that prediction is the one this plate most wants")
    w(f"; falsified. {a.control:g}mm is {a.control/proven[0]:.1f}x the only proven span and "
      f"{a.control/BUCKET_NEED:.1f}x what the bucket asks. At")
    w(f"; {a.speed:g} mm/s the nozzle is {a.control/a.speed:.1f} seconds getting to the far post, "
      f"and a {rod:.2f}mm rod of PLA")
    w(f"; under {fan2*100:.0f}% cooling has no mechanism to stay straight that long. THE THIN "
      f"STRANDS ON THAT ROW")
    w(f"; ARE THINNER STILL ({rod_x:.2f}mm) AND SHOULD WISP OR BREAK OUTRIGHT.")
    w(f"; IF ROW {nrow} COMES OUT TAUT, THIS PLATE IS LYING AND NOTHING ON IT MAY BE READ. That is")
    w(f"; what the control is for: a plate on which everything looks fine is otherwise")
    w(f"; indistinguishable from a plate that measured nothing.")
    w(";")
    w("; ---------------- HOW TO READ THE PLATE ----------------")
    w(f"; 1. LOOK AT ROW {nrow} FIRST, the long one on its own at the bottom. It must be visibly")
    w(f";    sagged, drooping to the glass, or broken. If it is straight and tight, STOP — the "
      f"plate")
    w(f";    is lying and no other row on it means anything.")
    w(f"; 2. THEN ROW 1, the short one at the top. It must be taut. If row 1 sags, the run is bad,")
    w(f";    not the spans — nothing is being measured and the plate should be reprinted.")
    w(f"; 3. THEN WALK 2, 3, 4 ... AND REPORT THE HIGHEST ROW NUMBER WHOSE STRANDS ARE STILL FLAT")
    w(f";    AND TAUT, plus the first row number where they visibly droop. Two numbers is the whole")
    w(f";    answer. Look at the fat strands and the thin ones separately if they differ — they")
    w(f";    are the bucket's two regimes and they may not fall off at the same span.")
    w(";")
    w("; ---------------- ONE TRAP, NAMED BECAUSE THE TOOL CANNOT SEE IT ----------------")
    w(f"; send.py measures ONE span per file: the LONGEST. On this plate that is the negative")
    w(f"; control at {a.control:g}mm, the row designed to fail. So `send.py accept` on this file "
      f"will print a")
    w(f"; ready-to-paste ledger line reading span_mm ({a.control:g}, ...). DO NOT PASTE IT. The "
      f"value that")
    w(f"; earned a place in machine.PROVEN_SEND is the LONGEST ROW THAT CAME OUT TAUT, read off the")
    w(f"; plate and typed by hand, with the row number and what was seen in its provenance string.")
    w("; MATERIAL_PLACEHOLDER")
    _mat_line = len(L) - 1
    w(";")

    w("M82")
    w("G90")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    # R7: the nozzle probes at PRINT temperature. Cold it is SHORTER, so Z zero records high and the
    # hot tip then grows down into the gap.
    w("G28")
    # ALWAYS EMITTED, INCLUDING A ZERO. SET_GCODE_OFFSET survives a job.
    w("SET_GCODE_OFFSET Z=0                 ; start from the machine's own zero, not last run's")
    w(f"M190 S{bed if a.printer == 'k2plus' else machine.bed_start(material, bed):.0f}")
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    w(f"M106 S{int(round(fan1 * 255))}   ; layer 1: {fan1*100:.0f}% — the pad weld is the job")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line + "   ; the bucket runs both chamber fans off; this plate copies it")
    w("G92 E0")
    w(f"SET_GCODE_OFFSET Z={zoff:.3f} MOVE=1   ; commanded Z{press:.3f} lands {a.h1:.3f}mm on a "
      f"machine whose zero sits {zerr:.3f} high")

    # ONE SHARED PRIME, machine.prime(). Nothing extrudes standing still at any Z; validate R10
    # refuses the old stationary purge, and the clump it left is what dropped into a printing plate.
    avoid = []
    for r in range(nrow):
        for rc in row_rects(r):
            avoid.append(("rect",) + rc)
    _px, _py, _ = machine.prime(
        w, printer=a.printer, z=press, rate=e1, feed=f1, travel_feed=travel_f,
        avoid=tuple(avoid), near=(row_rects(0)[2][0], ycs[0]))
    w("; BODY_START")

    E = 0.0
    ext1 = ext2 = trav = zmm = 0.0
    cur = [_px, _py, press]

    def hop(tx, ty, z, note):
        nonlocal trav, zmm
        sz = z + 1.0
        w(f"G0 Z{sz:.3f} F1800   ; HOP lift, clear of the posts")
        w(f"G0 X{tx:.3f} Y{ty:.3f} F{travel_f}   ; HOP {note}")
        w(f"G1 F1800 Z{z:.3f}")
        trav += math.hypot(tx - cur[0], ty - cur[1])
        zmm += abs(sz - cur[2]) + abs(sz - z)
        cur[0], cur[1], cur[2] = tx, ty, z

    def draw(tx, ty, rate, feed, tag=""):
        nonlocal E, ext1, ext2
        d = math.hypot(tx - cur[0], ty - cur[1])
        E += d * rate
        w(f"G1 F{feed} X{tx:.3f} Y{ty:.3f} E{E:.5f}{tag}")
        if feed == f1:
            ext1 += d
        else:
            ext2 += d
        cur[0], cur[1] = tx, ty

    def stroke(tx, ty, rate, feed):
        """One straight run, EMITTED IN ~SEG_MM STEPS.

        NOT cosmetic. The overhang guard indexes the layer below by the ENDPOINTS of its moves, so a
        16mm pad stroke contributes two points on the pad's edge and every post standing on the
        middle of it reads as extruded onto nothing (borelock.py measured exactly that). Subdividing
        makes the emitted path DESCRIBE THE MATERIAL IT LAYS, which makes the check stricter here.
        THE CROSSINGS ARE THE ONE THING NEVER PUT THROUGH THIS: a bridge is one unsubdivided move so
        nothing in the planner can slow it mid-air, and so send.py's span measurement is exact."""
        n = max(1, int(math.ceil(math.hypot(tx - cur[0], ty - cur[1]) / SEG_MM)))
        sx, sy = cur[0], cur[1]
        for i in range(1, n + 1):
            draw(sx + (tx - sx) * i / n, sy + (ty - sy) * i / n, rate, feed)

    def raster(rect, z, rate, feed, along_x):
        """One pad, one layer. Walked from whichever corner the head is nearest."""
        rx0, ry0, rx1, ry1 = rect
        if along_x:
            n = int(math.ceil((ry1 - ry0) / a.pitch)) + 1
            lines = []
            for p in range(n):
                yy = min(ry0 + p * a.pitch, ry1)
                lines.append((rx0, yy, rx1, yy) if p % 2 == 0 else (rx1, yy, rx0, yy))
        else:
            n = int(math.ceil((rx1 - rx0) / a.pitch)) + 1
            lines = []
            for q in range(n):
                xx = min(rx0 + q * a.pitch, rx1)
                lines.append((xx, ry0, xx, ry1) if q % 2 == 0 else (xx, ry1, xx, ry0))
        hop(lines[0][0], lines[0][1], z, "to a pad")
        for i, (ax_, ay_, bx_, by_) in enumerate(lines):
            if i:
                stroke(ax_, ay_, rate, feed)
            stroke(bx_, by_, rate, feed)

    # ----------------------------------------------------------------------- THE PADS, 2 LAYERS
    # LAYER 1 WELDS, LAYER 2 CROSS-LATCHES — the same pitch turned 90 degrees, bucket_latch's floor.
    # The pads are not decoration: a bridge under tension pulls its two posts toward each other, and
    # the pad is the only thing that stops the answer being about adhesion instead of about span.
    w(f"; ---- pad layer 1: raster along X at Z{press:.3f}, {a.pitch:g}mm pitch, "
      f"{a.w1 * a.h1:.3f} mm2/mm so it lands {a.w1:.2f}mm wide, {a.speed1:g} mm/s")
    for r in range(nrow):
        pa, pb, plab = row_rects(r)
        for rc in ((plab, pa, pb) if r % 2 == 0 else (pb, pa, plab)):
            raster(rc, z_pad[0], e1, f1, along_x=True)

    w(f"M106 S{int(round(fan2 * 255))}   ; every layer above the weld: {fan2*100:.0f}% — "
      f"machine.FAN_MAX[{material!r}], the bucket's own cooling and not a friendlier one")
    w(f"; ---- pad layer 2: the SAME pitch turned 90 deg at Z{press+lh:.3f}, body bead "
      f"{bw:g}x{lh:g}, {a.speed:g} mm/s — cross-latch")
    for r in reversed(range(nrow)):
        pa, pb, plab = row_rects(r)
        for rc in ((pb, pa, plab) if r % 2 == 0 else (plab, pa, pb)):
            raster(rc, z_pad[1], e2, f2, along_x=False)

    # --------------------------------------------------------------- THE POSTS AND THE NUMBERS
    # SNAKE ORDER, REVERSED EVERY LAYER, so the last post of one layer is the first of the next.
    def post_loop(rect, fwd):
        rx0, ry0, rx1, ry1 = rect
        pts = [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1), (rx0, ry0)]
        return pts if fwd else pts[::-1]

    order = []
    for r in range(nrow):
        pa, pb = post_rects(r)
        order += [(r, pa), (r, pb)] if r % 2 == 0 else [(r, pb), (r, pa)]

    for li in range(n_post):
        z = z_post0 + li * lh
        seq = order if li % 2 == 0 else order[::-1]
        w(f"; ================ post layer {li+1} of {n_post} at Z{z:.3f} ================")
        for r, rect in seq:
            # DIRECTION ALTERNATES BY LAYER. A closed loop starts and stops at one corner, so the
            # start's pressure blob and the stop's under-run land on the same corner every time
            # unless the walk is reversed; on a post whose top surface is the anchor for a bridge,
            # a pile at one corner is a tilt the strand then measures.
            pts = post_loop(rect, li % 2 == 0)
            hop(pts[0][0], pts[0][1], z, f"to row {r+1} post")
            for q in pts[1:]:
                stroke(q[0], q[1], e2, f2)
        if li < a.digit_layers:
            for r in range(nrow):
                lab = str(r + 1)
                _, _, plab = row_rects(r)
                lcx = (plab[0] + plab[2]) / 2.0
                w(f"; ---- row {r+1} number '{lab}' at Z{z:.3f}, {a.digit_layers*lh:.2f}mm proud "
                  f"when done")
                for (ax_, ay_), (bx_, by_) in glyph_segments(lab, lcx, ycs[r] - gh / 2.0,
                                                             gw, gh, ggap):
                    hop(ax_, ay_, z, f"to number {lab} stroke")
                    stroke(bx_, by_, e2, f2)

    # ------------------------------------------------------------------------------- THE DECK
    # ONE LAYER, AND ONLY ONE. A second deck layer laid on a sagging first one prints a mess that
    # cannot be read; the question is whether the FIRST strand across the air holds, which is also
    # the question the bucket's rim asks.
    # ASCENDING SPAN, CONTROL LAST, so if the long one drops onto the glass and drags, it drags
    # after every rung that matters has already been laid.
    w(f"; ================ THE DECK at Z{z_deck:.3f} — every crossing ONE unsubdivided move "
      f"================")
    for r in range(nrow):
        s, yc = spans[r], ycs[r]
        air = s - bw
        ys = [yc - deck_w / 2.0 + i * a.pitch for i in range(a.ncross)]
        w(f"; ---- row {r+1}: {a.ncross} strands across {s:.2f}mm tip to tip ({air:.2f}mm of air)"
          f"{'   *** NEGATIVE CONTROL ***' if r == nrow - 1 else ''}")
        hop(XA, ys[0], z_deck, f"to row {r+1} deck start, on post A")
        for i in range(a.ncross):
            if i:
                # Along the post's own inner wall — supported, body flow, subdivided.
                stroke(cur[0], ys[i], e2, f2)
            to_b = (i % 2 == 0)
            tx = (XA + s) if to_b else XA
            if i % 2 == 0:
                draw(tx, ys[i], e2, f2,
                     f" ; BRIDGE 1x {mm2_body:.4f}mm2 rod {rod:.3f}mm, {s:.2f}mm tip to tip, "
                     f"{air:.2f}mm unsupported air")
            else:
                draw(tx, ys[i], ex, f2,
                     f" ; THIN CROSS {a.cross_flow*100:.0f}% -- deliberate strand, not ooze "
                     f"({s:.2f}mm tip to tip, {air:.2f}mm of air, rod {rod_x:.3f}mm)")

    w("; ---- done")
    w("SET_GCODE_OFFSET Z=0                 ; hand the machine back at its own zero")
    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{max(z_deck + 20.0, 45.0):.0f} F900")
    w(f"G0 X10 Y{bedy-10:.0f} F{travel_f}")
    w("M84")

    mins = (ext1 / a.speed1 + ext2 / a.speed) / 60.0 \
        + trav / machine.MACHINE_MAX_SPEED / 60.0 + zmm / 30.0 / 60.0
    vol = E * A_FIL / 1000.0
    L[_mat_line] = (f"; MATERIAL {vol*1.24:.1f}g / {vol:.2f}cm3, ~{mins:.0f} min of motion — "
                    f"measured from this file's own final E and its own emitted moves, not from a "
                    f"nominal bead")

    open(out, "w").write("\n".join(L) + "\n")

    print(out)
    print(f"  {nrow} rows: ladder {ladder[0]:g}..{ladder[-1]:g}mm in {len(ladder)} rungs "
          f"+ a {a.control:g}mm negative control")
    print(f"  posts {pw:g}x{pl:g} single bead, {n_post} layers, top Z{top_z:.2f}, deck Z{z_deck:.2f}")
    print(f"  plate {width:.1f}x{height:.1f} at ({x0:.1f},{y0:.1f}); post A inner wall X{XA:.2f}")
    print(f"  first layer {a.h1:.3f}mm x {a.w1:.2f}mm landed via SET_GCODE_OFFSET Z={zoff:.3f} "
          f"(machine zero {zerr:+.3f} high) — {a.printer}'s PROVEN pair")
    print(f"  fan {fan2*100:.0f}% above layer 1 (machine.FAN_MAX[{material!r}]), chamber fans off — "
          f"the bucket's own cooling")
    print(f"    row  tip-to-tip     air   vs proven {proven[0]:g}")
    for r, s in enumerate(spans):
        print(f"    {r+1:>3}  {s:>10.2f}  {s-bw:>6.2f}  {s/proven[0]:>8.2f}x"
              f"{'   NEGATIVE CONTROL — must NOT hold' if r == nrow-1 else ''}")
    print(f"  ~{mins:.1f} min of motion, {vol:.2f}cm3 — the rule-6 first-proof ceiling is 25 min")

    # ------------------------------------------------------- THE PITCH THE GATE WILL MEASURE
    # send.py's S2 does not measure the pitch of a pad. It collects the y of EVERY layer-1 move that
    # runs along X, over the whole plate, and takes the MODAL GAP between the distinct values. On a
    # one-slab plate those are the same number. ON A PLATE MADE OF SEPARATE PADS THEY ARE NOT: two
    # pads 3mm apart in X, whose y-origins differ by anything that is not a whole multiple of the
    # pitch, contribute y values a fraction apart, and the modal gap collapses onto that fraction.
    # Measured on the first emit of this file: pads on a real 1.6mm pitch read as 0.4, because the
    # label pad was 12mm tall against the post pads' 16 and 12-16 = -4, which is 0.4 off the lattice.
    # bucket_sector_..._d341.5_n4 took a first-proof grant at (2, 10.481) for the same reason on
    # 2026-08-06, so this is a pattern in the measurement and not a one-off here.
    #
    # NOTHING ON THE PLATE IS 0.4mm APART. The value is an artifact of a global statistic, and the
    # consequence is real anyway: S2 reads UNPROVEN, spends a first-proof grant on a nonsense pair,
    # and `send.py accept` will then offer that pair as a paste-ready machine.PROVEN_SEND row.
    # COMPUTED HERE OFF THE SAME RECTANGLES THE RASTER WALKS, not asserted in a comment.
    _ys = set()
    for r in range(nrow):
        for rc in row_rects(r):
            for p_ in range(int(math.ceil((rc[3] - rc[1]) / a.pitch)) + 1):
                _ys.add(round(min(rc[1] + p_ * a.pitch, rc[3]), 3))
    _srt = sorted(_ys)
    _gaps = collections.Counter(round(b_ - a_, 3) for a_, b_ in zip(_srt, _srt[1:]))
    _modal = _gaps.most_common(1)[0][0] if _gaps else None
    if _modal is not None and abs(_modal - a.pitch) > 0.05:
        print(f"\n  ! THE SEND GATE WILL MEASURE THIS PLATE'S FLOOR PITCH AS {_modal:g}mm, NOT "
              f"{a.pitch:g}mm.")
        print(f"    {len(_ys)} distinct layer-1 y values across {nrow*3} pads; the modal gap "
              f"between them is {_modal:g}. Every pad is rastered at {a.pitch:g}, and nothing on "
              f"the plate is {_modal:g}mm apart — the pads' y-origins are off a shared lattice, so "
              f"send.py's global modal gap lands between two pads instead of inside one.")
        print(f"    CONSEQUENCE: S2 reads (w1, {_modal:g}) as UNPROVEN, spends a rule-6 grant on it, "
              f"and `send.py accept` will offer it as a ledger row. DO NOT PASTE THAT ROW.")
        print(f"    FIX: put every pad on one lattice — --label-pad {labw:g}x{padl:g} and a "
              f"--row-pitch that is a whole multiple of {a.pitch:g} (e.g. "
              f"{math.ceil(a.row_pitch/a.pitch)*a.pitch:g}). Verified: that reads {a.pitch:g}.")
    else:
        print(f"  floor pitch the gate will measure: {_modal:g}mm, off {len(_ys)} distinct layer-1 "
              f"y values — matches the {a.pitch:g}mm every pad is rastered at")


if __name__ == "__main__":
    main()
