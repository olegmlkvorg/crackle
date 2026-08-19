#!/usr/bin/env python3
"""BORE + LOCK GAUGE — twelve numbered C-channel stubs on one plate, so the STICK decides the bore
and the CLICK decides the wrap, instead of me guessing a third time.

  Oleg, 2026-08-06, holding the printed bucket: "stick holes are too narrow and dos not have enough
  to click lock a stick"

WHY THIS EXISTS. The bucket's wall posts are open C-channels that must snap onto a 1/8 inch bamboo
skewer. The bore has now been guessed twice and been wrong twice, and both guesses rest on one
number: a shrink constant of 0.25 mm. That constant was calibrated on a 4 mm METAL-SHAFT hole and
then reused for bamboo bores. guides/fit-and-assembly-empirics.md records what happened the last
time it was reused across a size and a material like that -- it was 0.45 mm too tight and condemned
about 21 parts. The same guide records that Oleg's 6.35 mm NOMINAL bamboo actually measured 5.8 to
6.2 mm and varied stick to stick, and that the working answer there was a 7.0 mm bore: 0.8 to 1.2 mm
of clearance, not the 0.15 the failing design was cut for.

  THE 0.25 SHRINK IS THE CONSTANT UNDER SUSPICION. THIS PLATE EXISTS TO REPLACE IT WITH A
  MEASUREMENT. Every "expected printed" number in the table below is that suspect constant applied,
  and is printed so it can be FALSIFIED by callipers, not so it can be believed.

WHAT IS SWEPT, AND WHY THE WRAP HAD TO MOVE TOO. Two things decide a snap fit and they are not the
same thing:

  BORE   -- whether the stick goes in at all, and how loose it is once in.
  MOUTH  -- the clear opening between the two lips, which is what CAPTURES the stick. It is not an
            independent knob: mouth = (bore + bead) * sin((360 - wrap)/2) - bead. The wrap angle is
            the only way to move it once the bore is chosen.

The failing part ran --wrap-deg 220 at bore 3.575, which models a mouth of 3.310 mm against a
3.175 mm stick. THE MOUTH WAS ALREADY WIDER THAN THE STICK BEFORE ANY SHRINK. Nothing could have
clicked; the stick fell through the opening it was supposed to snap past. Apply the suspect 0.25
shrink and it is 3.06 -- 0.115 mm of interference, which is not a lock, it is a rattle.

That is also why this plate does NOT test wraps 210 and 240, which is what a straight-line reading
of the failure suggests. At bore 4.0 those model mouths of 3.836 and 3.354 mm -- BOTH still wider
than the stick. A ladder whose every rung is on the same side of the answer measures nothing. The
two wraps here are chosen so the twelve modelled mouths STRADDLE the stick with room on both sides:
2.02 mm at the tightest through 3.62 mm at the loosest, against a 3.175 mm stick. Gate 4 below
refuses to emit a plate whose mouths do not reach a full suspect-shrink past the stick in BOTH
directions, so this reasoning cannot be lost by editing a default. It refuses --wraps 220, which is
what the failing part ran, and it refuses --wraps 210,240, which is what the failure superficially
suggests -- that one crosses the stick by 0.167 mm on one cell of twelve, the same razor margin as
the part that did not click.

THE PLATE CARRIES ITS OWN NEGATIVE CONTROL. Cells 5 and 6 model mouths of 3.456 and 3.620 mm, both
WIDER than the stick, so they must NOT retain it. If they click, the gauge is lying and nothing else
on the plate can be trusted -- read those two first.

WHY 18 mm STUBS. The bucket's real posts are 359 mm; nothing that tall is needed to feel a lock,
but a very short stub answers the wrong question. At 18 mm the stick is engaged over about six of
its own diameters, which is long enough that it cannot pivot out sideways -- a 5 mm stub lets a
marginal grip pass because the stick simply levers free instead of unsnapping, and a rigid stub
also reads as tighter than the real wall, which flexes. 18 mm also keeps the whole plate at roughly
ten minutes, so the answer comes back today.

Usage:  python3 borelock.py
        python3 validate.py out/borelock_*.gcode
"""
import argparse, math, os, shlex, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

A_FIL = machine.A_FIL

# THE SUSPECT CONSTANT, NAMED ONCE. bucket_towers.py carries the same number as SHRINK_METAL with
# the same provenance note. It is imported into this file's arithmetic ONLY to print the prediction
# this plate is meant to test; no geometry here depends on it being right.
SHRINK_SUSPECT = 0.25     # guides/fit-and-assembly-empirics.md, ~6mm bore, METAL shaft

SEG_MM = 1.0              # target arc segment, bucket_towers.py's own number
MIN_SEGS = 24             # per FULL revolution, however small the post -- bucket_towers.py's floor

# SEVEN SEGMENTS in a unit box: (x0,y0)-(x1,y1) as fractions of the glyph's width and height.
# Lifted from zladder.py rather than reinvented -- the plate's numbers must look like the plate's
# numbers on every gauge in this project, or a photograph of one cannot be read against another.
SEG = {
    'a': (0.0, 1.0, 1.0, 1.0),   # top
    'b': (1.0, 0.5, 1.0, 1.0),   # upper right
    'c': (1.0, 0.0, 1.0, 0.5),   # lower right
    'd': (0.0, 0.0, 1.0, 0.0),   # bottom
    'e': (0.0, 0.0, 0.0, 0.5),   # lower left
    'f': (0.0, 0.5, 0.0, 1.0),   # upper left
    'g': (0.0, 0.5, 1.0, 0.5),   # middle
    'h': (0.5, 0.0, 0.5, 1.0),   # CENTRE bar — this file's '1', see below
}
# '1' IS A CENTRE BAR HERE, WHICH IS THE ONE PLACE THIS DIVERGES FROM zladder.py. A seven-segment
# '1' is segments b and c, both on the RIGHT edge of the glyph box, so it draws as a bar hanging
# half a glyph-width off the centre of the number. zladder only ever labels single digits and it
# does not matter there. This plate labels twelve cells, so five of its numbers contain a '1', and
# measured on the first emit the ink of cells 10 and 12 sat 1.38mm right of the post they name
# while 1 and 7 sat 2.75mm right. Nothing crossed into a neighbouring column, so it would have
# printed and been readable -- but the ENTIRE interface of this plate is Oleg reading a number off
# it and saying it back, and a numeral leaning toward the wrong post is the one defect that would
# cost the whole ten minutes. A centred bar is unmistakably a 1 and every label then centres exactly.
DIGIT = {'0': 'abcdef', '1': 'h', '2': 'abged', '3': 'abgcd', '4': 'fgbc',
         '5': 'afgcd', '6': 'afgedc', '7': 'abc', '8': 'abcdefg', '9': 'abcdfg'}


def mouth_of(bore_d, wrap_deg, bw):
    """Clear opening between the two lips, mm. NEGATIVE means the lips would overlap.

    The toolpath circle has diameter (bore + bead) -- single wall, so the path runs half a bead
    outside the bore. The tips sit +-wrap/2 from the outward radial, so the SHORT way between them
    is (360 - wrap) of arc; the clear gap is that chord minus one bead, because half a lip bead
    bulges in from each side. Same expression as bucket_towers.py, deliberately: a gauge that
    modelled the mouth differently from the part would measure a different object."""
    return (bore_d + bw) * math.sin(math.radians((360.0 - wrap_deg) / 2.0)) - bw


def glyph_segments(label, cx, y_bot, gw, gh, gap):
    """Every stroke of `label`, as ((ax,ay),(bx,by)), with its INK centred on `cx`.

    CENTRED BY INK, NOT BY BOX, and the difference is the whole point of the method. '1' is a bar
    in the middle of an otherwise empty box, so a label laid out on box advances puts its visible
    mark off to one side: measured on this plate, '10' and '12' had their ink sitting 1.38mm right
    of the post they name even after the box arithmetic was exactly right. Nobody reads a box. So
    the strokes are laid out at zero, their real extent is measured, and that is what gets centred
    -- which makes the emitted file agree with what a person standing over the plate sees."""
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
    """Visible width of `label`, measured off the same strokes that get emitted."""
    xs = [p[0] for seg in glyph_segments(label, 0.0, 0.0, gw, 1.0, gap) for p in seg]
    return max(xs) - min(xs)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--stick-d", type=float, default=3.175,
                    help="the bamboo skewer the C has to grip, mm. 3.175 = 1/8 inch NOMINAL, and "
                         "nominal is exactly what is not trusted here: the 6.35mm nominal bamboo in "
                         "guides/fit-and-assembly-empirics.md measured 5.8 to 6.2 and varied per "
                         "stick. This value is used ONLY to check that the sweep brackets it.")
    ap.add_argument("--bores", default="3.6,3.8,4.0,4.2,4.4,4.6",
                    help="MODELLED bore diameters, mm, one per column. Chosen to BRACKET rather "
                         "than centre on the failed guess of 3.575: the 6.35mm bamboo precedent "
                         "needed 0.8-1.2mm of clearance, which scales to about 3.5 PRINTED for a "
                         "3.175 stick, and a printed 3.325 was already too narrow. So the low end "
                         "sits just above the stick and the high end reaches 1.4mm of modelled "
                         "clearance, which covers a true shrink anywhere from 0 to 0.9mm.")
    ap.add_argument("--wraps", default="250,280",
                    help="wrap angles, degrees, one per ROW. NOT 210/240: at bore 4.0 those model "
                         "mouths of 3.84 and 3.35mm, both WIDER than a 3.175 stick, so neither "
                         "could ever click and the plate would answer nothing. 250 and 280 put the "
                         "twelve modelled mouths at 2.02-3.62mm, straddling the stick, with the "
                         "loosest two cells acting as the plate's own no-click control.")
    ap.add_argument("--post-h", type=float, default=18.0,
                    help="post height above the plate's zero, mm. See the header: ~6 stick "
                         "diameters of engagement, enough that a marginal grip cannot pass by the "
                         "stick levering out sideways.")
    ap.add_argument("--plate", default="100x60", help="plate WxH in mm")
    ap.add_argument("--h1", type=float, default=machine.PRESS_HARD,
                    help="REAL landed first-layer height, mm. PROVEN on the K2 today at 0.10 with "
                         "--w1 2.00; do not deviate, it cost two failures to establish.")
    ap.add_argument("--w1", type=float, default=2.00,
                    help="target LANDED width of a layer-1 line, mm. Stated as a width because a "
                         "width is what callipers measure.")
    ap.add_argument("--pitch", type=float, default=1.6,
                    help="raster pitch of the plate, both layers. The bucket floor's own pitch.")
    ap.add_argument("--speed", type=float, default=machine.DEFAULT_SPEED, help="body, mm/s")
    ap.add_argument("--speed1", type=float, default=25.0, help="layer 1, mm/s")
    ap.add_argument("--fan", type=float, default=1.0,
                    help="part-cooling fraction 0..1 for every layer above the plate weld. A "
                         "single-bead post 18mm tall is the geometry that most needs it; layer 1 "
                         "always keeps machine.fan_first_layer(), so the weld is never chilled.")
    ap.add_argument("--digit-layers", type=int, default=3,
                    help="how many layers the raised numbers stand. 3 = 0.72mm proud, which "
                         "photographs and reads at arm's length.")
    ap.add_argument("--glyph", default="5.5x9.0", help="digit box WxH in mm")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    material = a.material or machine.LOADED[a.printer]
    temp = machine.MATERIAL_TEMP[material]
    bed = machine.bed_for(material, a.printer)
    bedx, bedy = machine.BED[a.printer]
    press = machine.PRESS_HARD
    lh = machine.SLICER_LAYER_H
    bw = machine.SLICER_LINE_W

    bores = [float(s) for s in a.bores.split(",") if s.strip()]
    wraps = [float(s) for s in a.wraps.split(",") if s.strip()]
    pw, ph = (float(v) for v in a.plate.lower().split("x"))
    gw, gh = (float(v) for v in a.glyph.lower().split("x"))
    ggap = gw * 0.33

    # ------------------------------------------------------------------ GATES, ALL BEFORE EMIT
    # Every one of these refuses a plate that would print beautifully and answer nothing. That is
    # the failure mode this file exists to end, so the checks are not warnings.
    for nm, v in (("--speed", a.speed), ("--speed1", a.speed1)):
        if v > machine.MAX_SPEED + 1e-9:
            sys.exit(f"REFUSING TO EMIT: {nm} {v:g} is above the {machine.MAX_SPEED:g} mm/s north "
                     f"star, which is a ceiling. Slower is legitimate; faster is not.")
    # gate 1  THE MACHINE MUST HAVE BEEN MEASURED. A missing zerr is not a zero zerr.
    zerr = machine.ZERR.get(a.printer)
    if zerr is None:
        sys.exit(f"REFUSING TO EMIT: no measured Z-zero error for {a.printer!r} (machine.ZERR has "
                 f"{sorted(machine.ZERR)}), so nothing here can say where this file's first bead "
                 f"lands. Measure it with zladder.py first.")
    zoff = machine.zoff_for(a.h1, zerr)          # raises rather than lift the nozzle off the plate
    # gate 2  THE FIRST LAYER MUST BE ONE THAT HAS PRINTED AND HELD. R9 would catch this on the
    # emitted file, but a generator that can only be corrected by a validator is a generator that
    # wastes a run to learn what it already knew.
    if not any(abs(a.h1 - h) <= 0.005 and abs(a.w1 - w) <= 0.05
               for h, w in machine.PROVEN_LAYER1.get(a.printer, [])):
        sys.exit(f"REFUSING TO EMIT: first layer {a.h1:g}mm x {a.w1:g}mm is not in {a.printer}'s "
                 f"proven set {machine.PROVEN_LAYER1.get(a.printer, [])}. This plate is a "
                 f"measurement of a BORE; it must not also be an experiment in adhesion.")
    # gate 3  A POST MUST BE A POST. Below 2 x bead the toolpath circle is narrower than the bead
    # and what prints is a blob with a seam (towercoupon.py).
    for b in bores:
        if b + 2.0 * bw < 2.0 * bw - 1e-9 or b <= 0:
            sys.exit(f"REFUSING TO EMIT: bore {b:g} is not a positive diameter.")
    cells = []                                    # (n, bore, wrap, mouth, row, col)
    for r, wd in enumerate(wraps):
        if not (0.0 < wd <= 360.0):
            sys.exit(f"REFUSING TO EMIT: --wraps contains {wd:g}, which is not in (0, 360].")
        for c, b in enumerate(bores):
            cells.append((len(cells) + 1, b, wd, mouth_of(b, wd, bw), r, c))
    bad = [t for t in cells if t[3] <= 0.2]
    if bad:
        sys.exit("REFUSING TO EMIT: these cells model a mouth of 0.2mm or less, i.e. the two lips "
                 "close on each other and there is no opening to press a stick through:\n  " +
                 "\n  ".join(f"bore {t[1]:g} wrap {t[2]:g} -> mouth {t[3]:+.3f}" for t in bad))
    # gate 4  THE SWEEP MUST STRADDLE THE STICK, ON BOTH AXES. This is the gate that would have
    # stopped the failing part being designed at all: at --wrap-deg 220 every modelled mouth on
    # every bore was WIDER than the stick, so the C could not capture it before shrink was even
    # considered. A ladder entirely on one side of the answer is not a measurement, and the plate
    # costs ten minutes and a slot on a machine Oleg is standing at.
    # THE MARGIN IS DERIVED FROM THE UNKNOWN, NOT PICKED. Crossing the stick diameter once is not
    # enough: --wraps 210,240 does cross it, by 0.167mm on exactly one of twelve cells, which is
    # the same razor margin the failing part already had (0.115mm) and would send back the same
    # answer of "nothing clicked". What the sweep has to cover is the size of the thing being
    # measured -- the shrink is unknown by at least its own suspect value, so the mouths must reach
    # a full SHRINK_SUSPECT below the stick and a full SHRINK_SUSPECT above it. Then whichever way
    # the real shrink falls, some cell on this plate is on each side of the answer.
    mn, mx = min(t[3] for t in cells), max(t[3] for t in cells)
    lo_need, hi_need = a.stick_d - SHRINK_SUSPECT, a.stick_d + SHRINK_SUSPECT
    if mn > lo_need or mx < hi_need:
        sys.exit(f"REFUSING TO EMIT: the modelled mouths run {mn:.3f} to {mx:.3f}mm against a "
                 f"{a.stick_d:g}mm stick, and a gauge has to bracket by MORE than the quantity it "
                 f"is measuring. The shrink is unknown by at least its own suspect "
                 f"{SHRINK_SUSPECT:g}mm, so the sweep must reach {lo_need:.3f} at the tight end "
                 f"and {hi_need:.3f} at the loose end; this one "
                 f"{'never gets tight enough' if mn > lo_need else ''}"
                 f"{' and ' if mn > lo_need and mx < hi_need else ''}"
                 f"{'never gets loose enough' if mx < hi_need else ''}. Widen --wraps: mouth = "
                 f"(bore + {bw:g}) * sin((360 - wrap)/2) - {bw:g}, so a BIGGER wrap gives a "
                 f"SMALLER mouth. (--wraps 210,240 fails here on purpose: its tightest cell clears "
                 f"the stick by 0.167mm, the same razor margin as the part that did not click.)")
    if min(bores) <= a.stick_d:
        sys.exit(f"REFUSING TO EMIT: modelled bore {min(bores):g} is not above the {a.stick_d:g}mm "
                 f"stick, so it cannot accept it even at zero shrink -- that cell would measure "
                 f"nothing but the fact that it is too small.")
    if max(bores) - a.stick_d < 1.0:
        sys.exit(f"REFUSING TO EMIT: the widest bore leaves only "
                 f"{max(bores) - a.stick_d:.2f}mm of modelled clearance. The 6.35mm bamboo "
                 f"precedent needed 0.8-1.2mm on a stick TWICE this size, so a sweep that stops "
                 f"below 1.0mm can run out of range before it finds the fit.")

    od_max = max(bores) + 2.0 * bw
    stride = pw / len(bores)
    # MEASURED OFF THE STROKES THAT ACTUALLY GET EMITTED, not from an assumed two-glyph box. The
    # widest label is whichever one it is; asking the renderer is the only way that cannot drift.
    label_w = max(label_ink_w(str(t[0]), gw, ggap) for t in cells) + bw
    if stride < max(od_max, label_w) + 2.0:
        sys.exit(f"REFUSING TO EMIT: {len(bores)} columns on a {pw:g}mm plate give a {stride:.2f}mm "
                 f"stride, which does not clear a {od_max:.2f}mm post and a {label_w:.2f}mm label "
                 f"with 2mm to spare. Widen --plate or drop a bore.")
    if a.digit_layers < 1:
        ap.error("--digit-layers must be at least 1; an unnumbered cell cannot be reported back")

    # ------------------------------------------------------------------------------- GEOMETRY
    x0, y0 = (bedx - pw) / 2.0, (bedy - ph) / 2.0
    if x0 < 5 or y0 < 5:
        sys.exit(f"REFUSING TO EMIT: a {pw:g}x{ph:g} plate does not fit {a.printer}'s "
                 f"{bedx:g}x{bedy:g} bed with a margin.")
    nrow = len(wraps)
    band = ph / nrow                              # one row of posts + its labels
    # POST ABOVE, LABEL BELOW, in every band. The number sits between its own post and the plate
    # edge (or the next band's post), never between two posts, so there is no way to read a label
    # against the wrong cell -- which is the one failure that would make the whole plate worthless.
    post_y = [y0 + ph - (r * band) - band * 0.22 for r in range(nrow)]
    lab_y = [y0 + ph - (r * band) - band * 0.72 for r in range(nrow)]
    col_x = [x0 + (c + 0.5) * stride for c in range(len(bores))]

    z_plate = [press, press + lh]                 # the plate: layer 1 welds, layer 2 cross-latches
    z_post0 = press + 2 * lh
    n_post = int(round((a.post_h - z_post0) / lh)) + 1
    if n_post < 4:
        sys.exit(f"REFUSING TO EMIT: --post-h {a.post_h:g} leaves {n_post} post layers.")
    top_z = z_post0 + (n_post - 1) * lh

    e1 = machine.layer1_rate(a.w1, a.h1)          # ONE implementation, machine.py
    e2 = bw * lh / A_FIL
    mm2_body = bw * lh
    flow = mm2_body * a.speed
    f1, f2 = round(a.speed1 * 60), round(a.speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    fan1 = machine.fan_first_layer(material)
    fan2 = max(0.0, min(1.0, a.fan))

    # THE ARC, PER CELL. nseg is per FULL revolution so a 250 and a 280 post are cut at the same
    # angular step -- otherwise the two rows would differ in chord length as well as in wrap, and
    # a click that came from a coarser polygon would be read as a click that came from the angle.
    geo = {}
    for n, b, wd, mouth, r, c in cells:
        r_t = (b + bw) / 2.0
        nseg = max(MIN_SEGS, int(math.ceil(2 * math.pi * r_t / SEG_MM)))
        narc = max(1, int(math.ceil(nseg * wd / 360.0 - 1e-9)))
        # MOUTH FACES +Y ON EVERY CELL. The outward (solid) face points -Y, so the opening looks up
        # the plate and every stick is pressed in the same direction. A plate whose cells opened
        # different ways would have him changing grip between rungs of the same ladder.
        a_start = math.radians(270.0) - math.radians(wd) / 2.0
        geo[n] = (col_x[c], post_y[r], r_t, a_start, math.radians(wd), narc)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.out,
                       f"borelock_{a.printer}_{material}_b{min(bores):g}-{max(bores):g}"
                       f"x{len(bores)}_w{'-'.join(f'{w:g}' for w in wraps)}_h{a.post_h:g}.gcode")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    L = []
    w = L.append

    # ------------------------------------------------------------------------------- HEADER
    w(f"; BORE + LOCK GAUGE — {len(cells)} numbered C-channel stubs, {a.post_h:g}mm tall, on one "
      f"{pw:g}x{ph:g}mm plate")
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
    _cap = machine.flow_cap(material, a.printer)
    w(f"; FLOW_DERATE=this plate reproduces the BUCKET's operating point on purpose, so it carries "
      f"the bucket's derate: a {machine.NOZZLE:g} nozzle laying the slicer's {bw:g}x{lh:g} bead at "
      f"{a.speed:g} mm/s delivers {flow:.2f} mm3/s against the {_cap:g} cap. Reaching the cap would "
      f"mean WIDENING the bead, and a C-channel's wall thickness IS its bead — a wider bead moves "
      f"the bore and the mouth, which are the two things being measured. A gauge run at a different "
      f"flow would not be a gauge for this part.")
    w(";")
    w("; ---------------- WHAT THIS IS ----------------")
    w(f"; {len(cells)} open C-channel stubs standing on a {pw:g}x{ph:g}mm plate. Each is a single "
      f"{bw:g}mm")
    w(f"; wall, {a.post_h:g}mm tall, with its mouth facing +Y so every stick presses in the same")
    w(f"; direction. {len(bores)} BORES across x {len(wraps)} WRAP ANGLES down y. Every cell carries "
      f"its own")
    w(f"; NUMBER, printed {a.digit_layers * lh:.2f}mm proud on the plate, so a photograph is "
      f"self-describing.")
    w(";")
    w("; ---------------- THE CONSTANT UNDER SUSPICION ----------------")
    w(f"; THE {SHRINK_SUSPECT:g} mm SHRINK IS A GUESS AND THIS PLATE EXISTS TO REPLACE IT.")
    w(f"; It was calibrated on a 4 mm METAL-SHAFT hole and then reused for bamboo bores. The last")
    w(f"; time it was carried across a size and a material like that it was 0.45 mm too tight and")
    w(f"; condemned about 21 parts (guides/fit-and-assembly-empirics.md). The same guide records")
    w(f"; 6.35 mm NOMINAL bamboo measuring 5.8-6.2 mm and needing a 7.0 mm bore -- 0.8 to 1.2 mm of")
    w(f"; clearance. The failing bucket was cut for 0.15 mm. Every 'expected printed' number below")
    w(f"; is that suspect {SHRINK_SUSPECT:g} applied, and is printed here to be FALSIFIED, not believed.")
    w(";")
    w("; ---------------- THE CELLS ----------------")
    w(f";   mouth = (bore + {bw:g}) * sin((360 - wrap)/2) - {bw:g}     stick = {a.stick_d:g} mm NOMINAL")
    w(";   cell   modelled bore   expected printed   wrap    modelled mouth   vs stick")
    for n, b, wd, mouth, r, c in cells:
        d = mouth - a.stick_d
        verdict = ("DROPS IN, no capture" if d > 0.05 else
                   "marginal, on the line" if d > -0.15 else
                   "should CLICK past the lips")
        w(f";   {n:>4}   {b:>13.3f}   {b - SHRINK_SUSPECT:>16.3f}   {wd:>4.0f}   {mouth:>14.3f}   "
          f"{d:+.3f}  {verdict}")
    w(";")
    w(f"; THE PLATE CARRIES ITS OWN NEGATIVE CONTROL. The cells marked 'DROPS IN' model a mouth")
    w(f"; WIDER than the stick and must NOT retain it. If they click, the gauge is lying and")
    w(f"; nothing else here can be trusted — read those first.")
    w(";")
    w("; WHY NOT WRAP 210 / 240, which is what the failure suggests. At bore 4.0 those model mouths")
    w("; of 3.836 and 3.354 mm, BOTH wider than a 3.175 stick, so neither could ever capture it.")
    w("; The failing part ran wrap 220 at bore 3.575 -> mouth 3.310, already wider than the stick")
    w("; before any shrink. A ladder with every rung on one side of the answer measures nothing.")
    w(";")
    w("; ---------------- HOW TO READ THE PLATE ----------------")
    w("; 1. START WITH THE LOOSE CELLS. If a cell whose table row says DROPS IN holds a stick, stop")
    w(";    — the model is wrong somewhere else and the rest of the plate cannot be read.")
    w("; 2. BORE: press a skewer into each cell in turn. Report the LOWEST number that goes in")
    w(";    without forcing and does not rattle. Try a few different skewers — the last bamboo this")
    w(";    project measured varied 0.4mm stick to stick, and if the answer changes with the stick")
    w(";    that IS the finding.")
    w("; 3. LOCK: for each bore that fits, compare its two rows. The wrap that snaps past the lips")
    w(";    and holds the stick against a gentle pull, while still going in by thumb, is the wrap.")
    w("; 4. SHRINK, MEASURED AT LAST: put callipers across any post's OUTER diameter and across its")
    w(";    mouth, and compare with the modelled numbers in the table. That difference is the real")
    w(f";    shrink for a free single-bead loop of this size. It replaces the {SHRINK_SUSPECT:g} guess whether")
    w(";    or not any cell clicks, so this plate answers something even if every cell is wrong.")
    w("; 5. Report back as: 'bore N, wrap M' plus the two calliper numbers. Nothing else is needed.")
    w("; MATERIAL_PLACEHOLDER")
    _mat_line = len(L) - 1
    w(";")

    w("M82")
    w("G90")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    # R7: the nozzle probes at PRINT temperature. Cold it is SHORTER, so Z zero records high and the
    # hot tip then grows down into the gap.
    machine.home(w, a.printer)
    # ALWAYS EMITTED, INCLUDING A ZERO. SET_GCODE_OFFSET survives a job, so a file that only wrote
    # it when non-zero would inherit whatever the last print left behind.
    w("SET_GCODE_OFFSET Z=0                 ; start from the machine's own zero, not last run's")
    w(f"M190 S{bed if a.printer == 'k2plus' else machine.bed_start(material, bed):.0f}")
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    w(f"M106 S{int(round(fan1 * 255))}   ; layer 1: {fan1*100:.0f}% — the plate weld is the job")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")
    w(f"SET_GCODE_OFFSET Z={zoff:.3f} MOVE=1   ; commanded Z{press:.3f} lands {a.h1:.3f}mm on a "
      f"machine whose zero sits {zerr:.3f} high")

    # ONE SHARED PRIME, machine.prime(). What was here lifted to Z2.000, extruded 20mm of filament
    # (48.1 mm3) with the head STANDING STILL in free air, and then drove the nozzle 1.9mm DOWN into
    # the pile it had just made. That is the exact sequence in Oleg's 2026-08-06 photograph, and
    # validate.py R10 now refuses it on the emitted file. The line that followed was metered E20->30
    # over 40mm = 0.601 mm2/mm, asking a 0.8 orifice to spread a 6.01mm bead at the 0.10 gap, five
    # lines above this file's own comment stating layer 1 as 0.200 mm2/mm landing 2.00mm wide.
    # `e1` is that same 0.200, so the prime is now the part's own first layer.
    _px, _py, _ = machine.prime(
        w, printer=a.printer, z=press, rate=e1, feed=f1, travel_feed=travel_f,
        avoid=(("rect", x0, y0, x0 + pw, y0 + ph),), near=(x0, y0))
    w("; BODY_START")

    E = 0.0
    ext1 = ext2 = trav = zmm = 0.0
    cur = [_px, _py, press]

    # HOP HEIGHT IS THE PART'S, NOW THAT NOTHING ELSE STANDS ON THE PLATE. It used to be
    # max(z+1.0, 3.0), and the 3.0 floor was not about the posts at all: it was clearing the Z2
    # prime purge, which an obvious "one millimetre above the part" ploughed straight through for
    # the first six layers. machine.prime() lays its line at the press gap, so the tallest thing on
    # this plate is once again the part, and the floor that protected against the blob goes with the
    # blob. Keeping it would be guarding a wall that is not there.
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
        """One straight run, EMITTED IN ~SEG_MM STEPS rather than as a single long move.

        NOT cosmetic, and not a way around a check. The overhang guard indexes the layer BELOW by
        the ENDPOINTS of its moves, so a 60 mm plate stroke contributes exactly two points, both on
        the plate's edge, and every post standing on the middle of it reads as extruded onto
        nothing. Measured on the first emit of this file: "100% of layer Z0.58 has no material
        within one bead of it on layer Z0.34", about a plate the posts sit squarely on.

        The guard is not wrong to say that — it can only see what the file records. Subdividing
        makes the emitted path DESCRIBE THE MATERIAL IT LAYS, which makes the check stricter here,
        not weaker: it now actually measures whether each post has plate under it, and it does.
        SEG_MM is the same 1.0 mm target this project already cuts every curve and rib to."""
        n = max(1, int(math.ceil(math.hypot(tx - cur[0], ty - cur[1]) / SEG_MM)))
        sx, sy = cur[0], cur[1]
        for i in range(1, n + 1):
            draw(sx + (tx - sx) * i / n, sy + (ty - sy) * i / n, rate, feed)

    # ------------------------------------------------------------------------- THE PLATE, 2 LAYERS
    # LAYER 1 WELDS, LAYER 2 CROSS-LATCHES. Same pitch turned 90 degrees, which is bucket_latch's
    # floor. The plate is not decoration: an 18mm single-bead post standing on its own 9mm of
    # first-layer perimeter has almost nothing holding it down, and it is the one part of this
    # gauge that must not fail for a reason unrelated to the bore.
    w(f"; ---- plate layer 1: raster along X at Z{press:.3f}, {a.pitch:g}mm pitch, "
      f"{a.w1 * a.h1:.3f} mm2/mm so it lands {a.w1:.2f}mm wide, {a.speed1:g} mm/s")
    npass = int(math.ceil(ph / a.pitch)) + 1
    hop(x0, y0, press, "to the plate's first layer")
    for p in range(npass):
        y = min(y0 + p * a.pitch, y0 + ph)
        xs, xe = (x0, x0 + pw) if p % 2 == 0 else (x0 + pw, x0)
        if p:
            stroke(xs, y, e1, f1)
        stroke(xe, y, e1, f1)

    w(f"M106 S{int(round(fan2 * 255))}   ; every layer above the weld: {fan2*100:.0f}% — an 18mm "
      f"single-bead post is the geometry that most needs cooling")
    w(f"; ---- plate layer 2: the SAME pitch turned 90 deg at Z{press+lh:.3f}, body bead "
      f"{bw:g}x{lh:g}, {a.speed:g} mm/s — cross-latch, no travel from layer 1")
    w(f"G1 F1800 Z{press+lh:.3f}")
    zmm += lh
    cur[2] = press + lh
    npass2 = int(math.ceil(pw / a.pitch)) + 1
    # WALKED FROM WHICHEVER CORNER THE HEAD IS ALREADY ON, so the only thing between the two layers
    # is one Z word. A travel here would run at layer height across the weld this plate stands on.
    x_hi = abs(cur[0] - (x0 + pw)) < abs(cur[0] - x0)
    y_hi = abs(cur[1] - (y0 + ph)) < abs(cur[1] - y0)
    for q in range(npass2):
        x = (x0 + pw - min(q * a.pitch, pw)) if x_hi else min(x0 + q * a.pitch, x0 + pw)
        if q % 2 == 0:
            ys, ye = (y0 + ph, y0) if y_hi else (y0, y0 + ph)
        else:
            ys, ye = (y0, y0 + ph) if y_hi else (y0 + ph, y0)
        if q:
            stroke(x, ys, e2, f2)
        stroke(x, ye, e2, f2)

    # -------------------------------------------------------------------- THE POSTS AND THE NUMBERS
    # SNAKE ORDER, REVERSED EVERY LAYER. Consecutive cells are always neighbours, and the last post
    # of one layer is the first post of the next, so the head never crosses the plate to start a
    # layer. On 74 layers that is the difference between a gauge and an afternoon.
    order = []
    for r in range(nrow):
        cs = range(len(bores)) if r % 2 == 0 else reversed(range(len(bores)))
        order += [r * len(bores) + c + 1 for c in cs]

    for li in range(n_post):
        z = z_post0 + li * lh
        seq = order if li % 2 == 0 else order[::-1]
        w(f"; ================ post layer {li+1} of {n_post} at Z{z:.3f} ================")
        for n in seq:
            cxp, cyp, r_t, a_st, wrp, narc = geo[n]
            # THE WALK DIRECTION ALTERNATES BY LAYER, and that is not tidiness. Every layer of an
            # open C starts and stops ON A LIP — there is nowhere else for the ends to be — so the
            # start's pressure blob and the stop's under-run land on the two surfaces that do the
            # gripping. Always walking the same way piles 74 blobs on one lip and 74 shortfalls on
            # the other, which would narrow the mouth by an amount nobody modelled and hand back a
            # click that came from the seam rather than from the wrap.
            fwd = (li % 2 == 0)
            pts = [(cxp + r_t * math.cos(a_st + wrp * i / narc),
                    cyp + r_t * math.sin(a_st + wrp * i / narc)) for i in range(narc + 1)]
            if not fwd:
                pts = pts[::-1]
            hop(pts[0][0], pts[0][1], z, f"to cell {n}")
            for q in pts[1:]:
                draw(q[0], q[1], e2, f2)
        if li < a.digit_layers:
            for n, b, wd, mouth, r, c in cells:
                lab = str(n)
                w(f"; ---- cell {n} number '{lab}' at Z{z:.3f}, {a.digit_layers*lh:.2f}mm proud "
                  f"when done")
                for (ax, ay), (bx_, by_) in glyph_segments(lab, col_x[c], lab_y[r], gw, gh, ggap):
                    hop(ax, ay, z, f"to number {lab} stroke")
                    draw(bx_, by_, e2, f2)

    w("; ---- done")
    w("SET_GCODE_OFFSET Z=0                 ; hand the machine back at its own zero")
    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{max(top_z + 20.0, 45.0):.0f} F900")
    w(f"G0 X10 Y{bedy-10:.0f} F{travel_f}")
    w("M84")

    mins = (ext1 / a.speed1 + ext2 / a.speed) / 60.0 \
        + trav / machine.MACHINE_MAX_SPEED / 60.0 + zmm / 30.0 / 60.0
    vol = E * A_FIL / 1000.0
    L[_mat_line] = (f"; MATERIAL {vol*1.24:.1f}g / {vol:.2f}cm3, ~{mins:.0f} min of motion — "
                    f"measured from this file's own final E and its own emitted moves, not from a "
                    f"nominal bead")

    machine.emit_gcode(out, "\n".join(L) + "\n")

    print(out)
    print(f"  {len(cells)} cells: {len(bores)} bores x {len(wraps)} wraps, posts {a.post_h:g}mm "
          f"({n_post} layers, top Z{top_z:.2f})")
    print(f"  plate {pw:g}x{ph:g} at ({x0:.1f},{y0:.1f}), stride {stride:.2f}mm, "
          f"numbers {a.digit_layers*lh:.2f}mm proud")
    print(f"  first layer {a.h1:.3f}mm x {a.w1:.2f}mm landed via SET_GCODE_OFFSET Z={zoff:.3f} "
          f"(machine zero {zerr:+.3f} high) — {a.printer}'s PROVEN pair")
    print(f"  THE {SHRINK_SUSPECT:g}mm SHRINK IS THE SUSPECT; 'expected printed' below is that guess "
          f"applied, printed to be falsified")
    print(f"    cell  bore   exp.printed  wrap   mouth   vs stick {a.stick_d:g}")
    for n, b, wd, mouth, r, c in cells:
        d = mouth - a.stick_d
        print(f"    {n:>4}  {b:>5.2f}  {b-SHRINK_SUSPECT:>11.2f}  {wd:>4.0f}  {mouth:>6.3f}  "
              f"{d:+.3f}  {'DROPS IN' if d > 0.05 else 'marginal' if d > -0.15 else 'should CLICK'}")
    print(f"  modelled mouths {min(t[3] for t in cells):.3f}..{max(t[3] for t in cells):.3f}mm — "
          f"straddle the {a.stick_d:g}mm stick by more than the {SHRINK_SUSPECT:g}mm the shrink is "
          f"unknown by, in both directions")
    print(f"  ~{mins:.1f} min of motion, {vol:.2f}cm3")


if __name__ == "__main__":
    main()
