#!/usr/bin/env python3
"""TOWER COUPON — how tall can a thin vertical member stand before it stops standing?

Oleg, 2026-08-04: "lets start with a coupons how high can we build thin towers vertically, once we
have that primitive we can connect it with bridgest" and "i suggrst to play with generating gcode
directly". Then, the same evening, about the bucket: "0.8 nozel would not print it. and in general
sub milimeter extrusions - is it even workable?" and "We will be doing it on k2, tomorrow".

WHAT THIS PLATE IS
------------------
Six single-wall round towers in a row, every one a CONSTANT diameter, every one commanded to the
same height, all printed LAYER-SYNCHRONISED (every tower gets layer n before any tower gets layer
n+1). The only thing that differs between towers is the diameter.

ONE GENERATOR, TWO MACHINES, AND THE LADDER IS NOT THE SAME LADDER
------------------------------------------------------------------
The first version of this file was written for the SparkX and hard-coded its 0.42 x 0.08 bead, its
R5 diameter ladder and its nozzle diameter — including printing "nozzle 0.4" into the header of any
file it wrote, for any machine. Everything that differs between machines now lives in PROFILES and
nothing else in this file carries a machine name.

The K2 plate is NOT a port of the SparkX plate. It answers the harder question Oleg actually asked:
what is the thinnest tall vertical member a 0.8 nozzle can build? So its ladder starts at a floor
that is DERIVED, not chosen:

    A SINGLE-WALL ROUND TOWER OF OUTER DIAMETER D HAS A TOOLPATH CIRCLE OF RADIUS (D - bead)/2.
    Once that radius drops below bead/2 the nozzle is orbiting INSIDE its own bead width: the
    swept annulus folds through its own centre, every revolution lays material on ground it
    already covered, and the result is a blob with a seam, not a tower. So the floor is

        D_min = 2 x bead

    On the SparkX (bead 0.42) that floor is 0.84 mm, and the inherited R5 ladder starting at 1.0 mm
    clears it by 19%. The rule is not new physics invented for the K2 — it retroactively explains
    why the SparkX ladder was already sound. On the K2 (bead 0.82) the floor is 1.64 mm, which is
    why an R5 ladder starting at 1.0 or 1.6 mm CANNOT be printed on this machine and the ladder had
    to move. check_ladder() refuses any diameter under the floor rather than emitting it.

    THE FLOOR IS A FEATURE FLOOR, NOT A WIDTH FLOOR, AND THE TWO ARE DIFFERENT. A 0.80 orifice on
    this project has been driven to a 0.735 mm bead — 92% of the nozzle — so sub-millimetre WIDTH
    is real on this machine. Sub-millimetre FEATURES are not: at bead 0.82 nothing round narrower
    than 1.64 mm exists to print. Narrowing the bead would lower the floor to about 1.47 mm, and
    that is a WIDTH ladder. This is a HEIGHT ladder. It cannot answer it and does not pretend to.

K2 RUNGS ARE WHOLE BEAD COUNTS: 2, 3, 4, 6, 8, 12 beads = 1.64 / 2.46 / 3.28 / 4.92 / 6.56 / 9.84
mm. Rung 1 sits exactly ON the floor, because a plate that starts safely above the floor cannot say
where the floor is. Counting in beads rather than in millimetres is what makes the answer transfer:
"four beads wide survived 100 mm" is a statement about any nozzle, "3.28 mm survived" is a statement
about this one. The top rung lands within 2% of the SparkX plate's 10.0 mm rung — near enough to
compare, NOT the same rung, and it is not reported as one.

THE K2 IS THE BETTER MACHINE FOR THIS PLATE, and not as a consolation. A 100 mm slender tower is a
cantilever whose own frequency falls as it grows, and the only thing damping the head's excitation
of it is the input shaper. The SparkX's shaper numbers are admitted DEFAULTS (using_default_data =
True), never measured on it — the one unquantified term in its whole plate. The K2's are CALIBRATED
(X 36.4 / Y 42.6). On the K2 the shaper stops being the thing nobody can predict.

WHY CONSTANT SECTIONS AND NOT A TAPERED NEEDLE
----------------------------------------------
A tapering tower is a tempting design because its diameter reports its own height, so a fallen
fragment still says where it came from. It was rejected for two reasons.

  1. ON A TAPER, HEIGHT AND DIAMETER ARE THE SAME COORDINATE. A break at z is also a break at D(z),
     and nothing about a single tapered tower can separate "it ran out of section" from "it ran out
     of height". Recovering the separation costs several taper RATES on the same plate, which is a
     more expensive plate that answers a question nobody asked.

  2. OLEG ASKED FOR A PRIMITIVE TO BRIDGE BETWEEN. That primitive is a post of some section, not a
     needle. A number measured on a taper does not transfer to the constant-section member he would
     actually build with.

The taper's one real virtue — a wrecked plate still being evidence — is kept, by a different route:
see THE RULER below.

CONSTANT SECTIONS ALSO REMOVE THE COOLING CONFOUND FOR FREE. If towers had different heights, they
would drop out as the print rose, so the number still printing would fall with z, so layer time
would fall with z, so cooling would degrade in lockstep with the variable under test. Here every
tower runs every layer at a fixed circumference, so LAYER TIME IS CONSTANT BY CONSTRUCTION. No
padding shuttle, no metronome, nothing to declare. The measured spread is reported by
tools/measure_towers.py off the emitted file.

THE RULER — why a wrecked plate is still evidence
-------------------------------------------------
A tall thin tower usually destroys its own record: it falls, and neither machine has a webcam, so
"it reached somewhere between 0 and the top" is all that survives. Worse, a faller can take a
neighbour with it.

So every tower carries a COUNTING RULER. Every RULER_PERIOD layers the loop steps out RULER_BONUS mm
of radius for a few layers, leaving a raised collar; every RULER_MAJOR_EVERY collars the band is
twice as tall and reads as a major mark. Count collars from either end of any fragment, multiply by
the pitch, and the fragment reports the height it came from whatever orientation it landed in.

THE PITCH IS THE WHOLE MECHANISM, SO IT IS GATED, NOT ASSUMED. A ruler whose pitch is 3.9998 mm
while the header says 4 is worse than no ruler: it is a wrong number that reads as a measurement.
collar_pitch() computes RULER_PERIOD x LAYER_H in exact decimal and REFUSES to emit anything unless
the product is a whole number of millimetres. That is what forced the K2 period: a 0.24 layer needs
25 layers to make 6.000 mm, where the SparkX's 0.08 layer needs 50 to make 4.000 mm. Neither number
was chosen for looking round; both are the smallest period that makes the gate pass.

THE COLLAR IS A PERTURBATION AND IT IS DECLARED. It steps out RULER_BONUS of radius, so the collar
bead still overlaps the one below it — the actual percentage is computed per machine and printed in
the header rather than inherited as a sentence (0.15 on 0.42 = 64%, 0.30 on 0.82 = 63%). It is
deliberately an OUTWARD step, not a waist: a waist would be a stress concentration and would bias
where the tower breaks, which is the one thing this plate must not do. An outward step biases
stiffness the other way, very slightly.

    ONE HONEST EXCEPTION, ON THE THINNEST RUNG. A single-wall loop of path radius r leaves an
    internal bore of 2r - bead. Stepping the path out for a collar therefore ALWAYS bores more than
    the wall does, and on a rung whose wall is solid it opens a void the tower does not otherwise
    have. On the K2's 1.64 mm rung the wall is exactly solid (bore 0.00) and the collar's bore is
    0.60 mm, 2 layers tall. On the SparkX's 1.0 mm rung the wall already has a 0.16 mm bore and the
    collar widens it to 0.46 mm. Both numbers are computed from the emitted geometry and printed in
    the header, not asserted. It is a stress concentration on exactly the rung that matters most,
    and it is the SECOND thing to check on a wreck: a break at a collar on the thinnest rung but NOT
    on the thick ones is this defect, not the tower's limit. IF EVERY TOWER BREAKS AT A COLLAR, the
    collar is the cause outright and the plate must be re-run with --ruler-bonus 0 before its
    numbers mean anything. Both are falsifiable and both are the first things to look for.

THE FOOT — so the plate measures the tower and not the bed bond
---------------------------------------------------------------
The thinnest tower standing on its own footprint touches the plate along a ring one bead wide: a
fraction of a square millimetre of bond holding a lever a hundred times longer. It would peel, and
the plate would have measured ADHESION rather than height — the wrong quantity, arriving as a
confident number.

So each tower starts on a FOOT: an Archimedean spiral wound from the outside inward, ending exactly
on the tower's own seam so the foot and the tower are ONE CONTINUOUS STROKE with no link move. Two
foot layers, the second smaller, then the tower rises. The foot is what makes the base a clamp
instead of a hinge. Its spiral pitch is 0.78 of the width the bead ACTUALLY lands at in the press
gap, so it stays a fixed overlap on both machines instead of a number tuned to one.

WHAT EVERY MOVE IN THIS FILE RUNS AT
------------------------------------
50 mm/s. Extrusion, travel, hop, all of it — Oleg's north star taken literally ("50 mm/s constant
for ALL moves incl. first layer"). It also happens to keep every travel at F3000, which is not
above the ploughing guard's F3000 threshold, so the guard's arithmetic and the machine's physics
agree instead of being traded off against each other. The hops lift clear anyway.

Every constant below is either a machine.py constant with recorded provenance, or a value READ OFF
THE SPARKX ITSELF over Moonraker (marked MEASURED-OFF-MACHINE), or a value CHOSEN here with the
reasoning stated next to it. Nothing is captioned as measured that was not measured.

                            SparkX (f022)                K2 Plus (k2plus)
    bead width          0.42  its slicer line_width   0.82  machine.SLICER_LINE_W, read off
                                                            his Creality Print 0.8 profiles
    layer height        0.08  its slicer layer_height 0.24  machine.SLICER_LAYER_H (Oleg's pick
                                                            from the stock profile heights)
    nozzle              0.4   corroborated by its own 0.8   Oleg, 2026-08-04 / machine.NOZZLE
                              0.42 line width
    diameter floor      0.84  = 2 x bead, DERIVED     1.64  = 2 x bead, DERIVED
    ladder              1.0 1.6 2.5 4.0 6.3 10.0      1.64 2.46 3.28 4.92 6.56 9.84 (2-12 beads)
    collar pitch        50 x 0.08 = 4.000 mm EXACT    25 x 0.24 = 6.000 mm EXACT
    layer 1 gap         0.10  machine.PRESS_HARD  ("the nozel need to be 0,1 to board")
    speed               50 mm/s   machine.DEFAULT_SPEED
    nozzle temp         machine.MATERIAL_TEMP[material]
    bed                 machine.bed_for(material, printer)
    part fan            machine.FAN_MAX[material], 0 on layer 1

KLIPPER'S nozzle_diameter FIELD IS NOT AN INSTRUMENT AND IS NOT CITED HERE. Both machines report
0.4 with user_nozzle_diameter 0.0; it is a stock Creality default and it is demonstrably wrong on
the K2. The SparkX's 0.4 is carried because its own slicer profile draws a 0.42 line, which only
makes sense on a 0.4 orifice — an independent route to the same number, which is the only kind of
corroboration worth having.

WHY R8 IS DECLARED RATHER THAN BREACHED. Both plates deliver a small fraction of the machine's flow
figure. It is not a derate in the sense R8 guards against ("slow is allowed, silent slow is not"):
it is what a nozzle laying its own slicer's bead AT the north-star speed physically delivers. The
only way to reach the figure would be to widen the bead, and the width of a single-wall thin member
IS the variable under test. The file states the reason; no rule is changed or silenced.

THE PLATE IS READABLE AND CANCELLABLE AT ANY MOMENT. Failure accumulates from the bottom, so
whatever has already failed when Oleg stops it is already the answer for that tower, and whatever
is still standing is a lower bound for the rest. Stopping early costs nothing that was learned.

WHAT THIS PLATE CANNOT TELL US is printed at the end of every run and repeated in the report.

Usage:  python3 towercoupon.py                       (the K2 plate — machine.DEFAULT_PRINTER)
        python3 towercoupon.py --printer f022        (the SparkX plate, unchanged)
        python3 towercoupon.py --height 40           (shorter, if the row is to be re-run)
"""
import argparse, math, os
from decimal import Decimal
import machine

A_FIL = math.pi * (1.75 / 2) ** 2      # mm2 of 1.75mm filament; the one place it is computed here

# READ OFF THE SPARKX (192.168.3.138, hostname F022-EAE2) over Moonraker /printer/objects/query,
# 2026-08-04, read-only. Kept here rather than in machine.py because machine.py's 'f022' entries are
# admittedly copied from the k1c ("same hotend family as the k1c, untested -- assumed, not
# measured") and this is the first time the machine itself has been asked.
SPARKX = {
    "max_velocity": 500.0,         # printer.max_velocity
    "max_accel": 10000.0,          # printer.max_accel
    "square_corner_velocity": 12.0,
    "max_z_velocity": 20.0,        # printer.max_z_velocity  -- SLOW, and it prices every z-hop
    "max_z_accel": 100.0,          # printer.max_z_accel     -- SLOWER still
    "pressure_advance": 0.031,
    "position_max": (279.0, 280.0, 260.0),
    "bed_mesh": ((5.0, 5.0), (255.0, 255.0)),
    # extruder.nozzle_diameter reads 0.4 here, and it is NOT quoted as evidence: the same field
    # reads 0.4 on the K2, which has a 0.8 nozzle. It is a stock Creality default. The 0.4 below
    # is carried on the slicer's 0.42 line width instead — a different route to the same number.
    "input_shaper_is_default": True,
}

# --------------------------------------------------------------------------- PER-MACHINE PROFILES
# THE ONLY PLACE IN THIS FILE THAT KNOWS A MACHINE'S NAME. Everything below reads a profile.
K2_BEAD = machine.SLICER_LINE_W        # 0.82 — read off all six K2 Plus 0.8 process profiles
K2_LAYER = machine.SLICER_LAYER_H      # 0.24 — Oleg's pick from that profile family's own heights
K2_LADDER_BEADS = (2, 3, 4, 6, 8, 12)  # rungs in WHOLE BEADS; 2 is the derived floor (see docstring)

PROFILES = {
    # SparkX. Unchanged geometry: this plate exists, its numbers are on the record, and a silently
    # different SparkX plate would invalidate the comparison the K2 plate is here to make.
    "f022": {
        "bead_w": 0.42,            # its own slicer line_width
        "layer_h": 0.08,           # its own slicer layer_height
        "nozzle": 0.4,             # corroborated by that 0.42 line width, NOT by Klipper's field
        "nozzle_src": "its own slicer draws a 0.42 line, which needs a 0.4 orifice",
        "diameters": [1.0, 1.6, 2.5, 4.0, 6.3, 10.0],   # R5 preferred numbers, ratio ~1.585
        "ladder_src": "R5 preferred numbers; clears this machine's 0.84 floor by 19%",
        "ruler_period": 50,        # x 0.08 = 4.000 mm EXACTLY (gated in collar_pitch)
        "ruler_minor": 3,          # layers per ordinary collar
        "ruler_major_every": 5,    # every 5th collar is a major band
        "ruler_major": 6,          # layers per major band
        "ruler_bonus": 0.15,       # mm of extra RADIUS at a collar
        "height": 70.0,
        "shaper": ["; input_shaper on this machine is using_default_data=True — shaper freqs are "
                   "DEFAULTS, never",
                   "; measured on it. For a slender tower that is the one unquantified term. "
                   "UNMEASURED."],
        "buzz": [";   - a rising BUZZ or whine = the row is being driven near resonance. This "
                 "machine's input",
                 ";     shaper is on DEFAULT data, never measured on it, so that is the term "
                 "nobody can",
                 ";     predict. If you hear it, note the height and stop."],
    },
    # K2 Plus. NOTHING HERE WAS READ OFF THE MACHINE: it was off the network the day this was
    # written (a full /24 sweep found only the SparkX). Every value states where it did come from.
    "k2plus": {
        "bead_w": K2_BEAD,
        "layer_h": K2_LAYER,
        "nozzle": machine.NOZZLE,  # 0.8 — Oleg, 2026-08-04, and machine.py's own NOZZLE
        "nozzle_src": "Oleg, 2026-08-04; machine.NOZZLE. Klipper's field says 0.4 here and lies",
        "diameters": [round(k * K2_BEAD, 3) for k in K2_LADDER_BEADS],
        "ladder_src": f"whole bead counts {'/'.join(str(k) for k in K2_LADDER_BEADS)}; "
                      f"rung 1 sits ON the derived 2 x bead floor",
        # 25 x 0.24 = 6.000 mm EXACTLY. 50 x 0.24 would be 12 mm — also exact, but a 12 mm pitch
        # puts only 8 collars on a 100 mm tower, and a ruler with 8 graduations is a poor ruler.
        # 25 is the SMALLEST period that makes collar_pitch()'s whole-millimetre gate pass.
        "ruler_period": 25,
        # 2 and 4 rather than the SparkX's 3 and 6: at a 0.24 layer, 2 layers is already a 0.48 mm
        # step (a fingernail reads it), and it keeps the perturbed fraction at 2/25 = 8% against the
        # SparkX's 3/50 = 6% instead of doubling it to 12%.
        "ruler_minor": 2,
        "ruler_major_every": 5,    # major band every 5 collars = 30.000 mm
        "ruler_major": 4,
        # 0.30 on a 0.82 bead leaves 63% overlapping, matching the SparkX's 64%. CHOSEN to hold that
        # ratio, not carried over: 0.15 on a 0.82 bead would be an 18% step, too shallow to count.
        "ruler_bonus": 0.30,
        # 100 mm, not the SparkX's 70. CHOSEN: the point of the plate is to find a BOUNDARY, and a
        # plate where everything survives found none. The bottom rung at 70 mm would be 43:1, well
        # inside what a shaper-calibrated corexy should hold; at 100 mm it is 61:1, in the same
        # aspect-ratio band the SparkX plate probes at its own bottom rung (70:1). The towers are
        # tiny, so the extra 30 mm costs single-digit minutes.
        "height": 100.0,
        "shaper": ["; input shaper on this machine is CALIBRATED — X 36.4 / Y 42.6, read from "
                   "previously",
                   "; sliced K2 gcode headers, not from the machine today (it was off the network "
                   "on 08-05).",
                   "; That is the real reason this plate belongs here: on the SparkX the shaper is "
                   "default data",
                   "; and is the one term nobody can predict for a slender cantilever."],
        "buzz": [";   - a rising BUZZ or whine = the row is being driven near resonance. This "
                 "machine's shaper",
                 ";     IS calibrated (X 36.4 / Y 42.6), so a buzz here is the TOWER's own "
                 "frequency falling",
                 ";     into the excitation, not an untuned machine. Note the height and stop."],
    },
}

HOP_Z = 0.4            # mm lifted before every inter-tower travel (NO_TRAVEL_RULE: lift, tag, hop)
SEG_TARGET = 0.35      # mm, target segment length around a loop
SEG_MIN_N = 8          # never fewer than 8 segments, however small the loop
FOOT_LAYERS = 2        # foot layers before the tower rises
FOOT_MARGIN = 3.0      # mm of foot radius beyond the tower wall on layer 1
FOOT_MIN_D = 4.5       # mm, smallest foot diameter
FOOT_R_MIN = 1.0       # mm, radius below which the foot stops spiralling (see foot_spiral)


def collar_pitch(period, layer_h):
    """Exact collar pitch in mm, or a refusal. THE GATE THE WHOLE RULER RESTS ON.

    The ruler works because a human counts collars and MULTIPLIES. That multiplication is only
    valid if the printed pitch is the true pitch. 50 x 0.08 = 4.000 and 25 x 0.24 = 6.000 are exact;
    a period that lands on 3.9998 and gets formatted to "4.000" hands out a wrong number wearing a
    measurement's clothes, which is the worst failure mode this project has.

    So the product is computed in exact DECIMAL, not in float, and anything that is not a whole
    millimetre is refused at generation time rather than rounded into the header. Float would get
    this wrong in the direction that hurts most — it REFUSES VALID PITCHES. 25 x 0.28 is exactly 7
    mm, and in binary float it is 7.000000000000001, so a float gate would have thrown out the
    period this plate would have used had Oleg stayed on the 0.28 layer he first named. Checked:
    32 such false refusals across the layer heights these machines offer, and no false passes.
    """
    lh = Decimal(str(layer_h))
    pitch = Decimal(str(period)) * lh
    if pitch != pitch.to_integral_value():
        ok = [p for p in range(1, 401) if (Decimal(p) * lh) == (Decimal(p) * lh).to_integral_value()]
        raise SystemExit(
            f"REFUSING TO EMIT: collar pitch {period} layers x {layer_h} mm = {pitch} mm, which is "
            f"not a whole number of millimetres. The ruler is read by counting collars and "
            f"multiplying by the pitch, so a fractional pitch is a wrong number that reads as a "
            f"measurement. Periods that work at this layer height: "
            f"{', '.join(str(p) for p in ok[:8]) if ok else 'NONE under 400 — pick another layer height'}")
    return float(pitch)


def check_ladder(diams, bead_w):
    """Refuse any tower thinner than 2 x bead. THE FLOOR, DERIVED — see the docstring.

    Below 2 x bead the toolpath circle's radius is under half the bead width, so the swept annulus
    folds through its own centre: the nozzle re-covers ground it just laid, every revolution. That
    is not a thin tower, it is an over-extruded blob, and it would be measured as a tower.
    """
    floor = 2.0 * bead_w
    bad = [d for d in diams if d < floor - 1e-9]
    if bad:
        raise SystemExit(
            f"REFUSING TO EMIT: {len(bad)} tower diameter(s) {bad} are under the {floor:.2f} mm "
            f"floor for a {bead_w:g} mm bead (D_min = 2 x bead). At D={min(bad):g} the toolpath "
            f"circle is {max(0.0, min(bad) - bead_w):.2f} mm across — the nozzle would be extruding "
            f"essentially in place. Widen the ladder, or narrow the bead first (a WIDTH ladder, "
            f"which this plate is not).")
    return floor


def loop_pts(cx, cy, r, n, seam):
    """Closed loop of n segments about (cx,cy), starting at segment index `seam`.

    Returns n+1 points; the last equals the first, so the loop closes exactly. The NEXT layer asks
    for seam+1, whose first point is one segment along from where this layer ended — so the seam
    walks around the tower instead of stacking into a ridge, and the layer change costs one
    segment of travel rather than a reposition across the part.
    """
    return [(cx + r * math.cos(2 * math.pi * ((seam + i) % n) / n),
             cy + r * math.sin(2 * math.pi * ((seam + i) % n) / n))
            for i in range(n + 1)]


def foot_spiral(cx, cy, r_out, r_cl, step, seam, n):
    """Archimedean spiral from r_out inward, ENDING on the tower's seam point.

    Ending on the seam is the point: the foot runs straight into the tower's own loop with no link
    move and no travel, so foot+tower is one continuous stroke (the house rule) and the base has no
    seam to peel from.

    THE SPIRAL STOPS AT FOOT_R_MIN AND FINISHES WITH ONE RADIAL MOVE. Winding a spiral all the way
    down to a 0.29 mm inner radius (the D=1.0 tower's centreline) is what the first version did, and
    it was wrong twice over: the angular step SEG_TARGET/r blows up as r falls, so the innermost
    turns degenerate into a coarse 5-sided polygon whose corners cut inside the turn before them and
    lay a second bead on ground already covered. validate.py measured the result as a 1.72x fill at
    Z0.18 — a REAL over-extrusion, which the '; PRESSED_LAYER1=' stamp then excused because the
    worst layer happened to be sampled next to it. Below FOOT_R_MIN the annulus is crossed once, by
    a single radial bead at the seam angle, which covers no ground twice.
    """
    th_end = 2 * math.pi * (seam % n) / n
    r_in = max(r_cl, FOOT_R_MIN)
    pts = []
    revs = (r_out - r_in) / step
    if revs > 0:
        th_start = th_end - 2 * math.pi * revs
        th = th_start
        while th < th_end - 1e-9:
            r = r_in + (th_end - th) / (2 * math.pi) * step
            pts.append((cx + r * math.cos(th), cy + r * math.sin(th)))
            th += SEG_TARGET / max(r, FOOT_R_MIN)   # r floor keeps the arc step sane, see above
        pts.append((cx + r_in * math.cos(th_end), cy + r_in * math.sin(th_end)))
    if r_in > r_cl + 1e-9:
        # single radial bead inward to the tower wall, along the seam ray: crosses the uncovered
        # annulus exactly once
        pts.append((cx + r_cl * math.cos(th_end), cy + r_cl * math.sin(th_end)))
    return pts


def collar_bonus(li, bonus, period, minor, major_every, major):
    """Extra RADIUS at 0-based layer index li. See THE RULER in the module docstring."""
    if li < FOOT_LAYERS + 2:
        return 0.0
    k, off = divmod(li, period)
    if k == 0:
        return 0.0
    span = major if (k % major_every == 0) else minor
    return bonus if off < span else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(PROFILES))
    ap.add_argument("--material", default=None,
                    help="defaults to whatever machine.LOADED says is in this printer")
    ap.add_argument("--height", type=float, default=None,
                    help="commanded tower height mm (per-printer default, see PROFILES)")
    ap.add_argument("--pitch", type=float, default=25.0, help="mm between tower centres")
    ap.add_argument("--ruler-bonus", type=float, default=None,
                    help="collar radius step mm; 0 disables the ruler (re-run control if every "
                         "tower breaks at a collar)")
    ap.add_argument("--bridge-every", type=int, default=0,
                    help="lay an unsupported horizontal span between adjacent towers every N "
                         "layers; 0 disables. Oleg's spec was 10.")
    ap.add_argument("--fan", type=float, default=None,
                    help="part-cooling fan fraction 0..1 for the BODY, overriding "
                         "machine.FAN_MAX. Layer 1 is unaffected and stays at its material's "
                         "first-layer value, so the plate weld is never chilled.")
    ap.add_argument("--beads", default=None,
                    help="override the ladder with an explicit list of WHOLE-BEAD counts, e.g. "
                         "--beads 10 for a single tower, or --beads 6,8,10. Diameter is always "
                         "count x bead, so the derived floor and the ruler gates still apply.")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    P = PROFILES[a.printer]
    # WHY AN OVERRIDE EXISTS AT ALL. Oleg, 2026-08-05, after breaking the first plate by hand:
    # "6 is unbreakable 5 somewhat breakable 4 easy breakable". The strength threshold sits BETWEEN
    # two rungs of the fixed ladder, and a six-tower plate cannot answer where -- it can only
    # re-print the rungs it already has.
    #
    # It also fixes a defect the first plate revealed. Printing six towers layer-synchronised means
    # the head travels between them on EVERY layer, and each travel drags a molten string. The
    # result is a horizontal web that BRACES the towers to each other, so a thin tower that appears
    # to stand may be held up by its neighbours: "Because of this horizontal nets I think even
    # thinnest one was standing fine". One tower has no neighbour and no inter-tower travel, so the
    # result means what it claims.
    #
    # The counts stay WHOLE BEADS rather than millimetres on purpose. A single-wall tower's
    # diameter is only meaningful as a multiple of the bead it is drawn with, and the derived floor
    # (2 x bead) is expressed the same way -- so an override in mm could silently ask for a wall
    # the nozzle cannot draw. check_ladder() below still runs on whatever this produces.
    if a.beads:
        try:
            _counts = [int(s) for s in str(a.beads).replace("/", ",").split(",") if s.strip()]
        except ValueError:
            ap.error(f"--beads takes whole numbers, got {a.beads!r}")
        if not _counts:
            ap.error("--beads was given with no counts")
        P = dict(P)
        P["diameters"] = [round(k * P["bead_w"], 3) for k in _counts]
        P["ladder_src"] = ("EXPLICIT --beads " + "/".join(str(k) for k in _counts)
                           + "; the fixed ladder was overridden on the command line")
    # MATERIAL FOLLOWS THE PRINTER. A part generated for one machine with another machine's
    # filament is silently wrong: right geometry, wrong temperature, wrong flow ceiling.
    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    if a.height is None:
        a.height = P["height"]
    bonus_mm = P["ruler_bonus"] if a.ruler_bonus is None else a.ruler_bonus
    bridge_every = max(0, a.bridge_every)
    bw, lh = P["bead_w"], P["layer_h"]
    period = P["ruler_period"]
    minor, major_every, major = P["ruler_minor"], P["ruler_major_every"], P["ruler_major"]
    # BOTH GATES RUN BEFORE ANY GEOMETRY IS BUILT. Neither is advisory: they raise.
    pitch_mm = collar_pitch(period, lh)
    floor_d = check_ladder(P["diameters"], bw)

    speed = machine.DEFAULT_SPEED                 # 50, the north star, for EVERY move in the file
    f = round(speed * 60)                         # F3000
    temp = machine.MATERIAL_TEMP[a.material]
    bed = machine.bed_for(a.material, a.printer)
    # BODY FAN. machine.FAN_MAX is Oleg's own 20% ceiling for PLA (2026-07-26, "fans for printing
    # pla should be only on 20% at most"), written because high fan chills the bead as it lands and
    # costs ADHESION. A tall slender tower is the opposite regime: it failed on 2026-08-05 by never
    # freezing at all, coiling into a rope. So the override exists, and it is per-run rather than a
    # change to FAN_MAX, because that ceiling is right for every flat part and must not move.
    # Layer 1 is deliberately NOT affected -- fan_first_layer() still governs the plate weld, which
    # is the exact thing the 20% rule protects.
    fan = machine.FAN_MAX[a.material] if a.fan is None else max(0.0, min(1.0, a.fan))
    press = machine.PRESS_HARD                    # 0.10, R1
    e_mm = bw * lh / A_FIL                        # filament mm per mm of path — ONE value, all file
    flow = bw * lh * speed
    r8cap = machine.flow_cap(a.material, a.printer)
    overlap = (bw - bonus_mm) / bw if bw > 0 else 0.0   # what the collar bead keeps on the one below
    land_w1 = bw * lh / press                     # width the bead ACTUALLY lands at in the press gap
    # THE COLLAR'S OWN BORE, on the thinnest rung, measured off the geometry rather than asserted.
    # A single-wall loop of path radius r leaves an internal bore of 2r - bead (clamped at 0, where
    # the section is solid). The collar steps the path out, so it always bores MORE than the wall
    # does — and on a rung whose wall is solid it opens a void the tower does not otherwise have.
    _thin_r = min(t / 2.0 - bw / 2.0 for t in P["diameters"])
    thin_wall_bore = max(0.0, 2.0 * _thin_r - bw)
    thin_collar_bore = max(0.0, 2.0 * (_thin_r + bonus_mm) - bw)

    n_lay = int(round((a.height - press) / lh)) + 1
    top_z = press + (n_lay - 1) * lh

    bedx, bedy = machine.BED[a.printer]
    n_tow = len(P["diameters"])
    span = (n_tow - 1) * a.pitch
    x0 = bedx / 2.0 - span / 2.0
    cy = bedy / 2.0
    towers = []
    for i, d in enumerate(P["diameters"]):
        r_cl = d / 2.0 - bw / 2.0                 # CENTRELINE radius: the path, not the wall
        circ = 2 * math.pi * r_cl
        nseg = max(SEG_MIN_N, int(math.ceil(circ / SEG_TARGET)))
        towers.append({"d": d, "cx": x0 + i * a.pitch, "cy": cy, "r": r_cl,
                       "n": nseg, "circ": circ})

    L = []
    w = L.append
    w("; TOWER COUPON — how tall can a thin single-wall vertical member stand?")
    w(f"; six constant-section towers, layer-synchronised, collar ruler every {pitch_mm:.3f}mm")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={speed:.4f}")
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; PRINT_TEMP={temp}")
    w(f"; FLOW_DERATE=a {P['nozzle']:g} nozzle laying its own slicer's {bw:g}x{lh:g} bead at the "
      f"{speed:g} mm/s north star delivers {flow:.2f} mm3/s. Reaching {0.8*r8cap:g} would mean "
      f"WIDENING the bead, and the width of a thin single-wall member is the variable under test. "
      f"Declared, not silent.")
    w(f"; bead {bw:g} x {lh:g}   nozzle {P['nozzle']:g} ({P['nozzle_src']})")
    w(f"; towers D=" + "/".join(f"{t['d']:g}" for t in towers) + f" mm, pitch {a.pitch:g}mm")
    w(f"; ladder: {P['ladder_src']}")
    w(f"; single-wall floor D_min = 2 x bead = {floor_d:.2f}mm — below it the toolpath circle is "
      f"narrower than the bead and the loop folds through its own centre")
    w(f"; ruler: collar every {period} layers = {pitch_mm:.3f}mm, "
      f"major every {major_every} collars = {pitch_mm*major_every:.3f}mm, "
      f"radius step {bonus_mm:g}mm")
    w(f"; collar overlap: a {bonus_mm:g}mm step on a {bw:g}mm bead keeps {bw-bonus_mm:.2f}mm "
      f"({100*overlap:.0f}%) on the bead below; perturbed layers {minor}/{period} = "
      f"{100*minor/period:.0f}% of the tower")
    for _ln in P["shaper"]:
        w(_ln)
    w(";")
    w("; ---------------- PLATE PLAN ----------------")
    w("; WATCH THE FIRST 2 MINUTES. Six feet go down as flat spirals. If any of them is not stuck")
    if press < lh:
        w(f";   flat and glossy, stop: the {press:g} press gap is TIGHTER than the {lh:g} layer, so "
          f"this first")
        w(f";   layer lands SQUASHED WIDE ({land_w1:.2f}mm), and it is the only thing holding a "
          f"{a.height:g}mm lever.")
        w(";   A foot that lifts a corner has already decided the run.")
    else:
        w(f";   flat and glossy, stop: at this layer height the {press:.2f} press gap is LOOSER "
          f"than a {lh:g}")
        w(f";   layer, so this first layer is thin ({land_w1:.2f}mm wide), and it is the only thing "
          f"holding a")
        w(f";   {a.height:g}mm lever. A foot that lifts a corner has already decided the run.")
    w(f"; THEN LOOK EVERY ~10 MINUTES, at the THIN END of the row (left, X{x0:.0f}).")
    w(";   The answer arrives from the bottom up and the thinnest tower decides first.")
    w("; LISTEN. A tall thin tower announces failure before it looks failed:")
    w(";   - a light TICK once per layer = the nozzle is clipping a tower that has begun to lean.")
    for _ln in P["buzz"]:
        w(_ln)
    w(";   - a change to a papery RUSTLE = a tower is gone and the nozzle is drawing in the air.")
    w("; STOPPING EARLY COSTS NOTHING THAT WAS LEARNED. Whatever has already failed is the answer")
    w(";   for that tower; whatever still stands is a lower bound for the rest.")
    w(f"; READING THE WRECK: count collars from the base, x{pitch_mm:g}mm. Every {major_every}th "
      f"collar is a tall band")
    w(f";   (={pitch_mm*major_every:g}mm). A fallen fragment reports its own height the same way, "
      f"in any orientation.")
    w("; FIRST THING TO CHECK: if every tower broke exactly AT a collar, the ruler caused it —")
    w(";   re-run with --ruler-bonus 0 before believing any number from this plate.")
    w(f"; SECOND: a break at a collar on the THINNEST rung only is the collar's own bore, not the")
    w(f";   tower's limit — on D{towers[0]['d']:g} the wall's bore is {thin_wall_bore:.2f}mm and the "
      f"collar's is {thin_collar_bore:.2f}mm.")
    w("; -------------------------------------------")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {n_lay}")
    w("; HEADER_BLOCK_END")
    w("M82")
    # BED FIRST AND NON-BLOCKING, so the plate climbs while the nozzle heats and the machine homes.
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    # ON THE K2, WAIT FOR THE FULL BED TARGET — it provably reaches it. EVERY OTHER MACHINE gets
    # machine.bed_start(), because the K1C pins at ~87-91 with its heater at full power and a
    # blocking M190 at a target it cannot cross is an infinite stall, not a rule.
    # M190 BLOCKS AND CANNOT BE MISPARSED. A quoted TEMPERATURE_WAIT sensor name was silently
    # skipped once and a print started at 78C.
    _floor = bed if a.printer == "k2plus" else machine.bed_start(a.material, bed)
    w(f"M190 S{_floor:.0f}   ; BLOCKING: do not start below this")
    # RE-RAISE THE TARGET. M190 SETS the target as well as waiting on it, so without this line a
    # plate that started at bed-5 stays at bed-5 for the whole print. The first version of this
    # file had exactly that bug: it waited to 55 and then printed 70mm on a 55C plate.
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    # THE NOZZLE PROBES AT FULL PRINT TEMPERATURE, and that is REVERTED-ONCE history, not taste.
    # Probing at 150 was tried and cost a first layer: a cold nozzle is SHORTER, so Z zero records
    # high and the hot tip then grows down into the plate, turning a 0.10 gap into ~0.054. M109
    # above has already blocked, so G28 here touches at temperature and not on the way to it.
    w("G28")
    _fan_l1 = int(round(machine.fan_first_layer(a.material) * 255))
    w(f"M106 S{_fan_l1}                              ; layer 1 gets no fan — the weld to the plate "
      f"is the job" if _fan_l1 == 0 else
      f"M106 S{_fan_l1}                              ; {a.material} needs cooling from layer 1")
    # CHAMBER/SIDE FANS SET EXPLICITLY TO ZERO, not left unmentioned. On the K2 these are output
    # pins that HOLD their last value across jobs, so "never mentioned" means "whatever the previous
    # print left them at" — and a chamber draft is the worst possible thing to point at a row of
    # slender cantilevers. machine.aux_fans() emits the right syntax per machine (SET_PIN here,
    # SET_FAN_SPEED on the K1C) and returns nothing at all for the SparkX, which has none.
    for _ln in machine.aux_fans(a.printer, 0.0):
        w(f"{_ln}                  ; no chamber draft on a row of cantilevers")
    w("G92 E0")

    # prime, off the row, in the front-left corner
    px, py = 20.0, 16.0
    w(f"G1 F{f} Z{press:.3f}")
    w(f"G0 F{f} X{px:.3f} Y{py:.3f}")
    w("G1 E12 F300                          ; PRIME stationary purge")
    w(f"G1 F{f} X{px+40:.3f} Y{py:.3f} E20  ; PRIME line")
    w(f"G0 F{f} X{px+52:.3f} Y{py+12:.3f}   ; PRIME break-off wipe")
    w("G92 E0")
    w("; BODY_START")

    E = 0.0
    fan_on = False
    for li in range(n_lay):
        z = press + li * lh
        gap = press if li == 0 else lh          # layer 1 is laid into the 0.10 press gap
        order = list(range(n_tow)) if li % 2 == 0 else list(range(n_tow))[::-1]
        w(f"; ---- layer {li+1} of {n_lay}  z {z:.3f}")
        w(f"G1 F{f} Z{z:.3f}")                  # STANDALONE Z — this is R2's layer ladder
        if li == 1 and not fan_on:
            _fan_src = (f"machine.FAN_MAX['{a.material}']" if a.fan is None
                        else f"--fan {a.fan:g} on the command line, OVERRIDING "
                             f"machine.FAN_MAX['{a.material}']={machine.FAN_MAX[a.material]:g}")
            w(f"M106 S{int(round(fan*255))}     ; {fan*100:.0f}% — {_fan_src}")
            fan_on = True
        bonus = collar_bonus(li, bonus_mm, period, minor, major_every, major)
        ppx0 = ppy0 = None          # where the PREVIOUS tower's loop ended, for a bridge to start
        for j, ti in enumerate(order):
            t = towers[ti]
            seam = li % t["n"]
            r = t["r"] + bonus
            pts = loop_pts(t["cx"], t["cy"], r, t["n"], seam)
            # foot on the first FOOT_LAYERS layers, spiralling inward INTO the tower's own seam
            head = []
            if li < FOOT_LAYERS:
                r_out = max(t["d"] / 2.0 + FOOT_MARGIN - li * 1.2, FOOT_MIN_D / 2.0 - li * 1.2)
                step = 0.78 * (bw * lh / gap)   # 0.78 overlap on the width the bead ACTUALLY lands at
                head = foot_spiral(t["cx"], t["cy"], r_out, r, step, seam, t["n"])
            path = head + pts if head else pts
            sx, sy = path[0]
            # ON A BRIDGE LAYER THE MOVE BETWEEN TOWERS IS EXTRUDED, NOT TRAVELLED.
            # Oleg, 2026-08-05: "connect them with bridges. 10layers ... to next". The first
            # version of this laid bridges as a SEPARATE pass -- hop up, fly to the anchor, drop
            # back down, extrude across -- and validate.py refused the file twice over: "Z descends
            # to 36.1 below layer floor 36.5, nozzle would plough the part" and "96 TRAVEL move(s)
            # inside the object, prints must be one continuous extrusion". Both were right.
            #
            # The fix is not a smaller hop, it is deleting the visit. A bridge IS the inter-tower
            # move, so on a bridge layer the G0 becomes a G1 and the span leaves the wall it is
            # welded to rather than landing on top of it. No lift, no descent, no travel, and the
            # extrusion stays continuous exactly as the rule requires.
            _bridging = (bridge_every and j > 0 and li >= FOOT_LAYERS
                         and (li % bridge_every) == 0)
            if j == 0:
                # continuing on the tower this layer's predecessor ended on: one segment of travel
                w(f"G0 F{f} X{sx:.3f} Y{sy:.3f} ; HOP seam-walk")
            elif _bridging:
                _span = math.hypot(sx - ppx0, sy - ppy0)
                # TWO LENGTHS, AND ONLY ONE OF THEM IS THE ACHIEVEMENT. _span is seam to seam, so
                # its two ends land ON the towers. The UNSUPPORTED part is just the air between
                # the walls. The first version of this line reported _span as "unsupported", which
                # overstates it by a full tower diameter -- 25.00 against a real 16.80 here. Both
                # are printed now, because a gcode comment is where a number goes to be believed.
                _air = max(0.0, _span - (towers[order[j - 1]]["d"] + t["d"]) / 2.0)
                E += _span * e_mm
                w(f"G1 X{sx:.3f} Y{sy:.3f} E{E:.5f} ; BRIDGE seam-to-seam {_span:.2f}mm, "
                  f"unsupported air {_air:.2f}mm, to tower D{t['d']:g}")
            else:
                w(f"G0 F{f} Z{z+HOP_Z:.3f} ; HOP lift clear")
                w(f"G0 F{f} X{sx:.3f} Y{sy:.3f} ; HOP to tower D{t['d']:g}")
                w(f"G0 F{f} Z{z:.3f} ; HOP down")
            ppx, ppy = sx, sy
            for (x, y) in path[1:]:
                seg = math.hypot(x - ppx, y - ppy)
                if seg < 1e-9:
                    continue
                E += seg * e_mm
                w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f}")
                ppx, ppy = x, y
            ppx0, ppy0 = ppx, ppy   # this tower's end is the next bridge's start

    w("M107")
    w("M104 S0")
    w("M140 S0")
    w(f"G0 F{f} Z{top_z+20:.2f}")
    w("G0 F3000 X10 Y10")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out,
                      f"towercoupon_{a.printer}_{a.material}_h{a.height:g}_n{n_tow}_b{bw:g}.gcode")
    open(fn, "w").write("\n".join(L) + "\n")

    print(fn)
    _dlist = "/".join(f"{t['d']:g}" for t in towers)
    print(f"  {n_tow} towers D={_dlist}mm  "
          f"pitch {a.pitch:g}mm  {n_lay} layers  top z {top_z:.2f}mm")
    print(f"  bead {bw:g} x {lh:g} at {speed:g} mm/s -> {flow:.2f} mm3/s "
          f"({100*flow/r8cap:.1f}% of the {r8cap:g} figure, DECLARED)")
    print(f"  floor D_min = 2 x bead = {floor_d:.2f}mm; thinnest rung {min(P['diameters']):g}mm "
          f"= {min(P['diameters'])/bw:.2f} beads")
    print(f"  ruler pitch {period} x {lh:g} = {pitch_mm:.3f}mm EXACT, major every "
          f"{major_every} = {pitch_mm*major_every:.3f}mm; collar keeps {100*overlap:.0f}% overlap")
    print(f"  aspect ratios (h/D): " + "  ".join(f"{t['d']:g}:{top_z/t['d']:.0f}" for t in towers))
    print("  INTENT ONLY — every number that matters is measured off the file by "
          "tools/measure_towers.py")
    print("\n  WHAT THIS PLATE CANNOT TELL US")
    print(f"   - nothing about BEAD WIDTH. Every tower here is one {bw:g} bead wide. Whether a bead")
    print(f"     narrower than the {P['nozzle']:g} orifice still touches the nozzle land is a WIDTH "
          f"ladder, and")
    print("     this is a HEIGHT ladder. UNMEASURED.")
    print(f"   - so it cannot lower the {floor_d:.2f}mm feature floor. That floor is 2 x THIS bead;")
    print(f"     a narrower bead moves it, and only a width ladder can say how far.")
    print("   - nothing about bridging BETWEEN towers, which is the next primitive, not this one.")
    print(f"   - nothing about any other machine. {bw:g} x {lh:g} is the {a.printer}'s own slicer "
          f"geometry;")
    print("     the other machines are different regimes and this plate is silent about them.")
    print("   - it cannot separate SWAY from THERMAL failure on its own. Layer time is constant, so")
    print("     the comparison across diameters is clean, but a single failure height is a")
    print("     boundary, not a mechanism. What Oleg HEARS decides that (see the plate plan).")
    print("   - it cannot prove a survivor's limit. A tower still standing at the top gives a LOWER")
    print("     BOUND only: >= that height, not 'that height'.")


if __name__ == "__main__":
    main()
