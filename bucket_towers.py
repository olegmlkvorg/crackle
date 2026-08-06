#!/usr/bin/env python3
"""BUCKET ON TOWERS — the wall is a RING OF VERTICAL POSTS joined by horizontal bridges.

Oleg, 2026-08-05: "We want a bucket using towers on the sides. The way you printed bucket now did
not work, the layers of wall math is very complex and you was not hitting adhesion with all this z
up and down movements".

So the wall stops being a continuous wavy cylinder. It becomes N single-wall posts standing on a
circle, each one drawn as a plain loop that only ever goes UP, with the gaps between them
crossed by horizontal bridges on a layer schedule. Nothing climbs, dips and re-welds to a
surface it left. The two things that were hard are simply gone: there is no wall profile to
compute per layer, and there is no descending Z anywhere in the file.

WHAT CHANGED ON 2026-08-06, after Oleg held the finished v1 bucket
------------------------------------------------------------------
"It came out majestic, true pleasure to have it in my hands. Few adjustments - half the tower
number, double the number of layers between solid lines. Double the thickness of solid lines, add
4x line width of new line types every 100 lines plus x8 for the final 4 layers on top of the
bucket. Also max out the usable printer area (fail is ok)". Then: "compute a version where The
columns are half... a bit more than half circles, which hold one eight of inch. Bamboo sticks so we
reenforxw the most fragile part off bucket and also add some extras printed support lines so bottom
of bucket is sturdier. And let's press on base plate a half less, I don't want to have solid base".

Three features, and every one of them is a flag with a stated default, not a rewrite:

1  THE POST IS AN OPEN C-CHANNEL THAT SNAPS ONTO A BAMBOO STICK (--wrap-deg, --stick-d,
   --bore-allow). The opening faces INWARD so the outer face stays continuous for the fabric and
   the bridges. --wrap-deg 360 reproduces the closed loop POINT FOR POINT -- proven, not claimed,
   by generating the same part with the pre-change file and diffing every G0/G1.
   A closed post has one seam; a C has TWO FREE ENDS, and those ends ARE the attachment points.
   The crossing runs leading tip of post k -> trailing tip of post k+1. That is the line the old
   seam_window() could not express: it used ONE offset for both ends of a chord.

2  THE LINE FEATURES ARE A BRIDGE FLOW SCHEDULE (--bridge-w-mult, --accent-every/-w-mult,
   --top-layers/--top-w-mult). Oleg, asked what the features were: "yes you understand correctly
   the features are all bridges" / "Just different extrusion volume". So a solid line, an accent
   band and the top rim are ONE move across the gap at more flow, which in air makes a thicker
   ROD -- never a second pass, never a fatter post. Declared as '; BRIDGE_MM2=' and MEASURED
   against the emitted moves by validate.py R4e.
   THE FABRIC IS UNTOUCHED: --cross-flow 0.25 on every non-bridge layer. "Don't remove the fabric
   that has to stay." Its 0.250mm rod exceeds the 0.24mm layer pitch, which is why the strands
   fuse into a continuous membrane instead of sitting as separate threads.

3  A BRACED BOTTOM AND AN OPEN BASE (--bottom-brace-layers, --bottom-bridge-every, and --h1/--w1).
   "press on base plate a half less, I don't want to have solid base" is NOT --h1 alone: the rate
   is derived from w1 x h1, so raising the gap at the same width just extrudes more and the base
   stays solid. The flow is HELD and --w1 comes down with it, which is what opens the base into a
   grid. Verify it in the emitted floor, not here.

WHAT CHANGED ON 2026-08-06 (second pass), after Oleg looked at the printed bucket
---------------------------------------------------------------------------------
"you need to merge the net and outer wall print in many places, it cant be separate closly aligned
pieces". That is a real defect and it was visible in the emitted file: the crossing left post k's
LEADING TIP tangentially, at a single point, and arrived at post k+1's TRAILING TIP the same way.
So the WALL was a vertical stack of arcs fusing to each other, the NET was a vertical stack of
strands fusing to each other, and the two structures met along ONE BEAD-WIDE SEAM LINE running the
full height. Two soundly built things touching, not interpenetrating.

4  --merge-mm (default 2.0) LAPS THE NET ONTO THE WALL AT BOTH ENDS OF EVERY CROSSING. Before it
   departs, the head runs BACK along the post's own arc for --merge-mm of ARC LENGTH and returns
   to the tip; after it lands, it runs FORWARD along the next post's arc the same distance and
   returns. The strand is then welded to the wall over a LENGTH at each end rather than at a point,
   and the joint is a lap rather than a butt. Both ends, because a weld on one side only MOVES the
   seam instead of removing it.
   THE CROSSING ITSELF IS UNTOUCHED. Each excursion returns EXACTLY to the tip it started from, so
   the chord that spans the air is the same chord: the fabric Oleg told us to keep is not in the
   blast radius, gate 3 tests the same geometry it always did, and --merge-mm 0 reproduces the
   pre-change file's motion BYTE FOR BYTE (proven by generating both and diffing every G0/G1, not
   claimed).
   WHAT IT COSTS, STATED: the excursion is out AND back, so each lap region receives 2 x
   --merge-flow of bead ON TOP OF the wall's own 1.0 -- 1.50x at the default. That lands on the
   two LIPS of the C-channel, which are also the bamboo mouth, so the modelled mouth NARROWS. Both
   numbers are printed in the header. Neither is measured.

WHAT THIS FILE REFUSES TO CLAIM: whether the C actually grips. The modelled mouth is WIDER than
the stick, so capture depends wholly on a print shrink that has never been measured for a free
single-bead loop of this size -- and the house record has that exact constant condemning ~21 parts
when it was carried from metal to bamboo. The header states both numbers and DECLINES. A graded
coupon answers it in minutes; a constant does not.

WHAT IS PROVEN AND WHAT IS NOT — read this before trusting the part
-------------------------------------------------------------------
PROVEN ON THE PLATE, tonight, by towercoupon.py:
  * 8.2 mm (10 beads) towers print and stand. 4.92 breaks easily by hand, 6.56 takes effort, 9.84
    does not break. 8.2 sits in that gap and is this file's default.
  * bridges every 10 layers between towers at 25 mm pitch held as TAUT STRANDS across 16.8 mm of
    unsupported air, at full flow and 50 mm/s.
  * cooling is structural, and it is a COUNT problem: six towers in rotation gave 4.50 s per layer
    and stood; ONE tower gave 0.57 s and coiled into a rope.
NOT PROVEN, and this file cannot claim it:
  * THE DEFAULT PART'S BRIDGE SPAN IS LONGER THAN THE ONE THAT HELD, and that is the single number
    to distrust. --pitch 25 was carried over from the coupon, but the coupon's seams sat ON its
    towers so a whole diameter of each strand was over solid material; this file's chord clears
    both towers by design, so nearly all of it is air. The generator MEASURES its own span
    (air_span), prints it against the 16.80 mm that held, and hands over the --pitch that would
    bring it inside. It does not quietly re-derive the default to make the number look good.
  * that a ring of towers holds together as a BUCKET. Nothing here has been printed.
  * that the part holds anything. It is a lattice with 16 mm gaps in the wall and a half-open
    lattice floor: it is a bucket in SHAPE. It is not a vessel and it does not hold liquid.
  * the strings. Every non-bridge layer crosses each gap as a non-extruding move, and there is no
    retraction anywhere in this project, so the nozzle oozes across the air. The coupon printed a
    web of exactly these ("Because of this horizontal nets I think even thinnest one was standing
    fine"). Expect them here too, x13 gaps x 148 layers. They brace the towers; they also look
    like a mess. Nothing about that is measured.

WHY A RING FIXES COOLING BY CONSTRUCTION
-----------------------------------------
Layer time is what killed the single tower, and a ring cannot have a short layer: the head must
walk the whole circle before it returns to any one tower. The number is computed from the emitted
path, not asserted here, and printed in the header and in the run report — both the extruding time
and the wall-clock including the gap crossings, because the tower is cooling during both.

THE SEAM IS DERIVED, NOT CHOSEN, AND IT IS THE WHOLE REASON NOTHING LIFTS
-------------------------------------------------------------------------
The head has to get from one tower to the next thirteen times a layer. towercoupon.py does it by
lifting 0.4 mm, flying across and dropping back — safe, but it is 2000 Z reversals in a 40 mm part
and Z reversals are the thing Oleg just said did not work.

They are only necessary if the straight line between two towers would drag the nozzle through
material. It does not have to. Put every tower's seam at the SAME angular offset from its own
outward radial, and the chord between two neighbouring seams is congruent for every pair — so
there is one geometry question, asked once: for which offsets does that chord leave the first
tower's toolpath circle immediately and arrive at the second's from outside?

seam_window() answers it by MEASURING the real chords at 0.25 degree steps rather than by algebra,
and reports the window it found. On the default 100 mm / 13-tower / 8.2 mm geometry the window is
a band around 180 degrees — the seam pointing INWARD, at the bucket's inside. Outward fails: the
chord to the next tower doubles back and dips 0.12 mm inside the wall it just laid.

So the seam faces the inside of the bucket, the crossing is FLAT at the layer's own Z over open
air, and Z in the whole body is monotonic: one step up per layer and nothing else. That is checked
on the emitted list, not assumed (check_paths, gate 4).

THE COST OF A FIXED SEAM, NAMED. Every layer of a tower starts and stops at the same angle, so
each tower carries a vertical scar line up its inside face. bucket_latch.py already documents why
the alternatives are worse (walking the seam doubles a bead once per layer; spiralling Z removes
the layer ladder R2 measures). If a tower splits, look at the inside seam first.

THE FLOOR IS bucket_latch.py's, IMPORTED, NOT RE-WRITTEN
---------------------------------------------------------
--floor-layers (default 5) cross-latch layers: parallel chords at --floor-pitch, each layer's
lines perpendicular to the one below. That code is imported from bucket_latch.py and called, so
there is exactly one cross-latch implementation in this repo and a fix to it fixes both parts.

WHY THE FLOOR IS 5 LAYERS AT 2.5 mm AND NOT 5 LAYERS AT 5 mm — MEASURED, 2026-08-05
------------------------------------------------------------------------------------
Oleg, holding the first printed ring: "Base need to be way stronger, otherwise look like perfect
piece." His own earlier instruction (2026-07-27) was "for the bucket. floor 5 layers. walls single
layer. strict", and the 2 here was a later "couple cross latch layers" that he has now questioned.

Raising the count alone WAS TRIED FIRST AND validate.py REFUSED IT:
    FAIL  OVERHANG: 23% of layer Z0.58 has no material within one bead (0.82mm) of it on
                    layer Z0.34 -- that fraction of the layer is being extruded onto nothing.
The reason is the latch's own geometry and it is not cosmetic. Consecutive layers are
PERPENDICULAR, so layer 3 touches layer 2 only where the two rasters cross -- once every
--floor-pitch -- and flies over the (pitch - bead) between crossings. At 5.0 mm pitch that is
4.18 mm of air under 84% of every rib. Stacking a sparse lattice higher does not build a floor; it
builds ribs joined at points, and three more layers of it is three more layers of that.

So the pitch comes down WITH the count, and the criterion is the support fraction bead/pitch:
    pitch 5.0 -> 16% of each rib over material, 4.18 mm bridged   -> gate says 23% unsupported
    pitch 2.5 -> 33% of each rib over material, 1.68 mm bridged   -> gate says  2%, passes
    pitch 1.6 -> 51%, 0.78 mm bridged (under one bead: they touch) -> gate says 0%, passes
2.5 is taken. 1.6 buys 2 percentage points of a gate reading for +7.1 m of extrusion and +3 min,
and it also forces --w1 down to about the pitch or layer 1 over-extrudes ~1.9x -- which would undo
"first layer needs full flow, a lot of filament glued to base max width" to chase a number that is
already inside its threshold.

WHAT THE SAME ONE CHANGE BUYS, all of it from the floor block being taller and denser:
  * FLOOR THICKNESS 0.34 -> 1.06 mm. Plate bending stiffness goes as thickness CUBED, so that term
    alone is ~30x. DERIVED from the layer ladder, not measured on a part -- and it is a lattice, so
    the absolute figure is well under a solid plate of the same thickness.
  * THE RIM RING, FREE. The gap crossings are extruded on every floor layer, so the 16-gon tying
    the tower feet together grows from 0.34 mm tall to 1.06 mm: 0.28 -> 0.87 mm2 of hoop section,
    3.1x, and hoop section is what resists a tower splaying outward at its foot.
  * LAYER 1 BECOMES SOLID. At --w1 3.0 landed on a 2.5 mm pitch the first layer's own lines overlap
    1.2x instead of covering 60% of the disc, so the thing welded to the plate is a disc and not a
    grid -- and every layer above it lands on material.

WHAT WAS CONSIDERED AND REJECTED, with the reason rather than a shrug:
  * A SOLID PAD UNDER EACH TOWER FOOT. The tower is a hollow single-wall tube for all 40 mm of it,
    so a 1 mm plug moves the hollow-to-solid transition up by 1 mm rather than removing it, and the
    annulus the tube actually stands on is already solid (latch + rim + its own loop, every floor
    layer). It also needs new path code threading in and out of 16 loops without breaking the
    one-stroke invariant or the seam window. Cost and risk for no load path.
  * A WIDER RIM BAND. Hoop section is width x height and both are linear, so the layer count already
    bought the same 3.1x without a second knob or a second thing to keep true.

Two things are different here, and both are about what the towers stand on:
  * the latch disc stops one bead inside the RIM POLYGON (the 13-gon joining the tower seams),
    and that radius is measured off the emitted chords rather than derived from a formula.
  * on a FLOOR layer the tower loops are drawn too, and the gap crossings are EXTRUDED. So the
    floor ends in a solid rim tying all thirteen towers together, and every tower's first airborne
    layer lands on its own footprint from the layer below. Without this the towers would be
    standing on a lattice with 5 mm holes in it.

WHAT RUNS AT WHAT — every number READ, none typed here
-------------------------------------------------------
    bead width      machine.SLICER_LINE_W    0.82   (his own Creality K2 Plus 0.8 profiles)
    layer height    machine.SLICER_LAYER_H   0.24
    layer 1 gap     machine.PRESS_HARD       0.10
    speed           machine.DEFAULT_SPEED    50     every move in the file, layer 1 included
    nozzle temp     machine.MATERIAL_TEMP[machine.LOADED[printer]]  — 210 for the pla loaded today
    bed             machine.bed_for(...)
    part fan        machine.FAN_MAX[...], raisable with --fan; layer 1 keeps
                    machine.fan_first_layer() so the plate weld is never chilled

Usage:  python3 bucket_towers.py                  (the 100 mm bucket Oleg asked for first)
        python3 bucket_towers.py --dia 200        (the big one, once the small one has printed)
        python3 bucket_towers.py --fan 0.6        (more cooling for the towers; layer 1 unaffected)
        python3 validate.py out/bucket_towers_*.gcode      # must pass
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import bucket_latch as latch          # the cross-latch floor — imported, not copied

A_FIL = machine.A_FIL     # mm2 of 1.75mm filament; computed once
SEG = 1.0                             # mm target segment on every curve and every rib
MIN_TOWER_SEGS = 24                   # never fewer than this per tower loop, however small it is
SEAM_SCAN_DEG = 0.25                  # resolution of the seam-window measurement
# THE ONLY BRIDGE SPAN THAT HAS ACTUALLY HELD. towercoupon.py, printed 2026-08-05: strands across
# 16.80 mm of unsupported air between 25 mm-pitch towers pulled TAUT at this flow and speed. It is
# a lower bound (16.8 held; nothing says 17 does not), and it is the yardstick this file reports
# its own span against rather than quietly assuming the span is fine.
PROVEN_AIR_MM = 16.80


# ------------------------------------------------------------------------------ small geometry
def seam_point(c, phi, r_t, off):
    """The point on tower `c`'s toolpath circle at `off` radians from its OUTWARD radial."""
    a = phi + off
    return (c[0] + r_t * math.cos(a), c[1] + r_t * math.sin(a))


def arc_segs(nseg_full, wrap_deg):
    """How many segments to walk `wrap_deg` of arc, given `nseg_full` per FULL revolution.

    nseg IS PER FULL REVOLUTION AND ALWAYS HAS BEEN, so a C-channel and a closed loop are cut at
    the same angular step and --wrap-deg 360 lands on exactly the number the closed loop used.
    ceil, never round: rounding DOWN would make the arc's chord coarser than the full-turn chord
    the SEG target was sized for. The 1e-9 is the float slack -- 24 * 210/360 evaluates to
    14.000000000000002, and a bare ceil would cut 15 segments where 14 divides the arc exactly.
    """
    return max(1, int(math.ceil(nseg_full * wrap_deg / 360.0 - 1e-9)))


def tower_arc(c, r, a_start, wrap_rad, n, end_pt):
    """One post, EXCLUDING the start point, ending EXACTLY on `end_pt`.

    `a_start` is the angle of the TRAILING tip; the head walks CCW through the post's outward face
    to the LEADING tip. At wrap_rad = 2*pi this is one closed revolution and reproduces the closed
    loop point for point (a_start = phi + seam - pi, so the first computed point is the old
    a0 + 2*pi/n): --wrap-deg 360 is the degenerate case of this parameterisation, not a branch.

    The exact closure matters at BOTH ends: the next thing drawn starts from the last point with no
    move at all, and the layer above starts on the trailing tip, so a float-drifted end would open a
    sub-micron gap the emitter would turn into a silent travel. check_paths() gate 1 measures it at
    1e-6; forcing the point here means it never happens.
    """
    pts = [(c[0] + r * math.cos(a_start + wrap_rad * i / n),
            c[1] + r * math.sin(a_start + wrap_rad * i / n)) for i in range(1, n)]
    pts.append(end_pt)
    return pts


def merge_arc(c, r, a_tip, sign, merge_mm, step_rad):
    """Points walking `merge_mm` of ARC LENGTH away from a post's tip, ALONG THE POST'S OWN PATH.

    Excludes the tip itself, so it appends straight onto a path that is already sitting there.
    `sign` is -1 to walk BACK from the leading tip (the departure lap) and +1 to walk FORWARD from
    the trailing tip (the arrival lap).

    IT FOLLOWS THE ARC, IT DOES NOT CHORD ACROSS IT. The whole point is that this material lands ON
    the wall bead; a straight shortcut between the same two ends would sit up to r(1-cos) INSIDE the
    post and weld to nothing. Same angular step as tower_arc(), so the lap lands on the same points
    the wall itself was drawn through and the two beads share a centreline rather than crossing it.

    The last step is TRUNCATED to land exactly at merge_mm rather than overshooting to the next
    whole segment: the overlap length is a declared number that gate 6 measures off the emitted
    points, so it has to be the number, not the number rounded up to the arc's segmentation.
    """
    if merge_mm <= 0 or r <= 1e-12:
        return []
    total = merge_mm / r                          # radians of arc = length / radius
    step = max(step_rad, 1e-9)
    out, walked = [], 0.0
    while walked < total - 1e-12:
        walked = min(total, walked + step)
        a = a_tip + sign * walked
        out.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
    return out


def dip(p, q, c, r):
    """How far (mm) segment p->q passes INSIDE the circle (c, r). 0.0 means it clears it.

    This is the whole basis for crossing between towers WITHOUT lifting: if the chord never enters
    either tower's toolpath circle, there is nothing under the nozzle to plough and nothing to
    lift over. Both endpoints sit exactly ON a circle, so a clean chord measures exactly 0.0 here
    and anything that doubles back reads positive.
    """
    dx, dy = q[0] - p[0], q[1] - p[1]
    l2 = dx * dx + dy * dy
    if l2 < 1e-18:
        return 0.0
    t = max(0.0, min(1.0, ((c[0] - p[0]) * dx + (c[1] - p[1]) * dy) / l2))
    return max(0.0, r - math.hypot(p[0] + dx * t - c[0], p[1] + dy * t - c[1]))


def air_span(p, q, cA, cB, r_t, bw, n=2000, arc=None):
    """Length of p->q that is over NOTHING, measured on the chord rather than assumed.

    `arc` = (phiA, phiB, half_rad) makes this ARC-AWARE. A C-channel post is not a disc: the 150
    degrees facing the bucket axis are EMPTY, and a sample landing in that sector is over air, not
    over material. Ignoring it can only ever UNDER-report the span, which is the direction that
    flatters the part, so the sector test is done rather than argued. (Measured at --wrap-deg 210:
    every in-disc sample lies at |offset| 103.6..105.0 deg, inside the material, so the two answers
    agree here -- but they agree by MEASUREMENT, not by assumption, and a narrower wrap parts them.)

    THE OBVIOUS FORMULA IS WRONG HERE AND IT FLATTERS US. towercoupon.py computes its span's air as
    (seam distance - one tower diameter), which is right for ITS geometry: its seams sit at the same
    absolute angle on towers in a row, so each end of the strand lands ACROSS a tower and a whole
    diameter of the chord is over solid material. This file's chord deliberately CLEARS both towers
    -- that is the entire reason it may cross flat without lifting -- so almost none of it is over
    material, and borrowing that formula understated the span by 6 mm on the default part.

    So it is measured: walk the chord and count the length whose distance from BOTH tower centres
    exceeds r_t + bw/2, i.e. is outside the material the wall bead actually occupies.
    """
    edge = r_t + bw / 2.0
    L = math.dist(p, q)

    def solid(x, y, c, phi):
        if math.dist((x, y), c) > edge:
            return False
        if arc is None:
            return True
        off = math.atan2(y - c[1], x - c[0]) - phi
        off = (off + math.pi) % (2 * math.pi) - math.pi      # to (-pi, pi]
        return abs(off) <= arc[2] + 1e-12

    phiA, phiB = (arc[0], arc[1]) if arc else (0.0, 0.0)
    over = 0
    for i in range(n):
        t = (i + 0.5) / n
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if not solid(x, y, cA, phiA) and not solid(x, y, cB, phiB):
            over += 1
    return L * over / n


def seam_window(centres, phis, r_t, half_deg=180.0, step_deg=SEAM_SCAN_DEG):
    """STAGGER offsets (deg) whose gap crossings clear every post. MEASURED, not argued.

    A CLOSED LOOP HAS ONE SEAM; AN OPEN ARC HAS TWO FREE ENDS, and that is the line that had to
    change. The crossing runs from post k's LEADING tip (stagger + half) to post k+1's TRAILING tip
    (stagger - half) -- two DIFFERENT offsets. The old version used one `off` for both ends, which
    is the closed-loop special case and cannot express an arc at all.

    `half_deg` is half the wrap. At 180 the two tips merge, this reduces exactly to the closed-loop
    scan, and the window it returns is the old 180-degree seam window shifted by 180 (stagger 0 IS
    seam 180). So --wrap-deg 360 stays a superset here too.

    Returns the sorted list of passing stagger offsets, so the caller takes the widest run's centre
    and REPORTS the window instead of asserting a number.
    """
    n = len(centres)
    ok = []
    steps = int(round(360.0 / step_deg))
    hr = math.radians(half_deg)
    for i in range(steps):
        st = math.radians(i * step_deg)
        good = True
        for k in range(n):
            j = (k + 1) % n
            p = seam_point(centres[k], phis[k], r_t, st + hr)
            q = seam_point(centres[j], phis[j], r_t, st - hr)
            if dip(p, q, centres[k], r_t) > 1e-9 or dip(p, q, centres[j], r_t) > 1e-9:
                good = False
                break
        if good:
            ok.append(i * step_deg)
    return ok


def widest_run(offs, step_deg=SEAM_SCAN_DEG):
    """(centre, width) of the widest circular run of passing offsets, in degrees."""
    if not offs:
        return None, 0.0
    runs, cur = [], [offs[0]]
    for a, b in zip(offs, offs[1:]):
        if abs(b - a - step_deg) < 1e-9:
            cur.append(b)
        else:
            runs.append(cur)
            cur = [b]
    runs.append(cur)
    # join across the 0/360 wrap so a window straddling zero is not reported as two
    if len(runs) > 1 and abs(runs[0][0]) < 1e-9 and abs(runs[-1][-1] + step_deg - 360.0) < 1e-9:
        runs[0] = [x - 360.0 for x in runs[-1]] + runs[0]
        runs.pop()
    best = max(runs, key=len)
    return (best[0] + best[-1]) / 2.0, best[-1] - best[0] + step_deg


# ------------------------------------------------------------------------------------- the gates
def air_for_count(cx, cy, r_ring, r_t, bw, n, half_deg=180.0):
    """The unsupported bridge span this file WOULD build with `n` posts, run through the same
    window and air-span code the real part uses. Used only to hand the operator the --pitch
    that lands on the proven span -- at the SAME scan resolution and the SAME sample count, so the
    span it advertises is the span the suggested run actually builds. (A coarser scan here first
    advertised 15.63 where the run produced 15.65: small, and the same species of error as the
    rounded pitch that did not reproduce.)

    IT TAKES THE WRAP, and that is not cosmetic. Built from ONE offset it returned the closed-loop
    chord 35.42 while the arc run builds 33.22 -- a 2.2 mm error in the number this function exists
    to make trustworthy, in exactly the way its own docstring already warns about."""
    phis = [2 * math.pi * k / n for k in range(n)]
    cs = [(cx + r_ring * math.cos(p), cy + r_ring * math.sin(p)) for p in phis]
    c, _ = widest_run(seam_window(cs, phis, r_t, half_deg))
    if c is None:
        return None
    hr = math.radians(half_deg)
    o = math.radians(c)
    return air_span(seam_point(cs[0], phis[0], r_t, o + hr), seam_point(cs[1], phis[1], r_t, o - hr),
                    cs[0], cs[1], r_t, bw, arc=(phis[0], phis[1], hr))


def check_paths(layers, centres, r_t, bed, press, lh, seam_off_deg, bw, w1, merge_mm=0.0):
    """Refuse to emit anything that breaks one of the properties this part is built on.

    Every one of these was a real failure, and none of them is checkable by reading the source:
    they are properties of the emitted point list, so that is what is measured.
      1  ONE STROKE. Layer n+1 starts exactly where layer n ended. A gap is a travel by another
         name -- the emitter would simply not write a G0 and the printer would draw across the part.
      2  NOTHING OFF THE PLATE -- MATERIAL, not toolpath. See below.
      3  EVERY GAP CROSSING CLEARS BOTH POSTS. If it fails, the answer is a different angle, not a
         hop. READ THE CAVEAT ON THIS ONE: for a C-channel it no longer discriminates (below).
      4  Z NEVER DESCENDS. Trivially true of a per-layer Z ladder -- and asserted anyway, because
         "the first bridge attempt" was also obviously fine until validate.py read the file.
      6  EVERY MERGE LAP LIES ON A POST AND IS AS LONG AS DECLARED. Gate 3 exempts these moves
         because they run ON a post BY DESIGN, and an exemption granted by a tag is worth nothing;
         this earns it back by MEASURING that they do, off the emitted points.
    Gate 5 (the latch floor vs the bamboo channel) needs r_h and lives in main().
    Returns (n_crossings, n_laps, measured_lap_mm).
    """
    for i in range(1, len(layers)):
        d = math.dist(layers[i]["pts"][0], layers[i - 1]["pts"][-1])
        if d > 1e-6:
            raise SystemExit(
                f"REFUSING TO EMIT: layer {i+1} starts {d:.6f} mm from where layer {i} ended. That "
                f"gap is a travel move inside the object. Fix the handoff, do not add a hop.")
    # GATE 2 MEASURES THE BEAD, NOT THE TOOLPATH, and on this part that is the difference between
    # a real check and a comfortable one. The toolpath is a centreline; what has to fit on the plate
    # is the material, which extends half a bead further -- half of --w1 on the pressed first layer,
    # where the bead is widest. On the 341.5 mm part the toolpath clears by 2.13 mm and the layer-1
    # bead clears by 1.46 mm, so the old gate carried 0.67 mm of blindness on a part whose whole
    # stated margin is about one millimetre.
    for i, L in enumerate(layers):
        half = (w1 if i == 0 else bw) / 2.0     # only layer 1 is metered to --w1
        for (x, y) in L["pts"]:
            if not (half <= x <= bed[0] - half and half <= y <= bed[1] - half):
                raise SystemExit(
                    f"REFUSING TO EMIT: layer {i+1} puts material at ({x:.1f},{y:.1f}) +-"
                    f"{half:.2f} mm of bead, off a {bed[0]:g}x{bed[1]:g} plate. The part does not "
                    f"fit this machine.")
    # GATE 3, AND AN HONEST CAVEAT ABOUT WHAT IT IS WORTH NOW.
    # For a CLOSED loop it bound hard: only 12.75 of 360 degrees of seam offset passed, so it was
    # genuinely what licensed a flat crossing. For a C-CHANNEL the crossing runs tip to tip, near
    # the tangent points, and MEASURED on this geometry it refuses only below --wrap-deg 12.854
    # (= the 360/n ring step): about 347 of 360 degrees pass. It still measures a true property of
    # the emitted points and it still runs on every crossing -- but it no longer DISCRIMINATES, so
    # it must not be quoted as the reason the arc form is safe. A guard is worth only what it has
    # been seen to reject.
    worst = (0.0, None)
    n_cross = 0
    for i, L in enumerate(layers):
        for j, kind in enumerate(L["kind"]):
            if kind not in ("T", "B", "R"):
                continue
            p, q = L["pts"][j], L["pts"][j + 1]
            n_cross += 1
            for c in centres:
                d = dip(p, q, c, r_t)
                if d > worst[0]:
                    worst = (d, (i + 1, p, q, c))
    if worst[0] > 1e-9:
        i, p, q, c = worst[1]
        raise SystemExit(
            f"REFUSING TO EMIT: a gap crossing on layer {i} passes {worst[0]:.3f} mm INSIDE a "
            f"tower's toolpath circle -- ({p[0]:.2f},{p[1]:.2f}) -> ({q[0]:.2f},{q[1]:.2f}) against "
            f"the post at ({c[0]:.2f},{c[1]:.2f}). At --stagger-deg {seam_off_deg:g} the head would "
            f"drag across a wall it just laid, and the ONLY reason this file may cross flat with no "
            f"lift is that it does not. Move the seam into the measured window, do not add a hop.")
    zs = [press + i * lh for i in range(len(layers))]
    bad = [k for k in range(1, len(zs)) if zs[k] < zs[k - 1] - 1e-9]
    if bad:
        raise SystemExit(f"REFUSING TO EMIT: Z descends at layer(s) {bad[:5]}. Towers only go up.")
    # GATE 6 — THE MERGE LAP. Gate 3 above skips kind "M" because a lap runs ON a post deliberately:
    # feeding it to a check whose whole job is to refuse anything touching a post would refuse the
    # feature for doing what it exists to do. That is stated rather than special-cased quietly, and
    # the exemption is EARNED BACK HERE by measuring the property gate 3 can no longer see:
    #   * every point of a lap sits on a post's toolpath circle to 1e-6 -- it is ON the wall, not
    #     beside it, which is the entire difference between a weld and the seam it replaces;
    #   * the lap returns EXACTLY to the tip it left, so the crossing chord is untouched;
    #   * the arc length it reaches is --merge-mm. Declared-and-not-applied is the failure this
    #     project has been bitten by five times, so the number is measured off the points, never
    #     re-derived from the argument that produced them.
    # And a merge asked for but ABSENT is refused too: a silently empty feature is the same defect
    # wearing a pass.
    n_merge, lap_lo, lap_hi = 0, None, None
    for i, L in enumerate(layers):
        K, P = L["kind"], L["pts"]
        j = 0
        while j < len(K):
            if K[j] != "M":
                j += 1
                continue
            j0 = j
            while j < len(K) and K[j] == "M":
                j += 1
            tip = P[j0]
            if math.dist(P[j], tip) > 1e-9:
                raise SystemExit(
                    f"REFUSING TO EMIT: a merge lap on layer {i+1} ends {math.dist(P[j], tip):.9f} "
                    f"mm from the tip it started at. The lap must return to the tip exactly or the "
                    f"crossing departs from somewhere the seam window was never measured for.")
            c = min(centres, key=lambda cc: abs(math.dist(cc, tip) - r_t))
            a_tip = math.atan2(tip[1] - c[1], tip[0] - c[0])
            worst_r, reach = 0.0, 0.0
            for p in P[j0:j + 1]:
                worst_r = max(worst_r, abs(math.dist(p, c) - r_t))
                da = math.atan2(p[1] - c[1], p[0] - c[0]) - a_tip
                da = (da + math.pi) % (2 * math.pi) - math.pi
                reach = max(reach, abs(da) * r_t)
            if worst_r > 1e-6:
                raise SystemExit(
                    f"REFUSING TO EMIT: a merge lap on layer {i+1} strays {worst_r:.6f} mm off the "
                    f"post's toolpath circle at ({c[0]:.2f},{c[1]:.2f}). A lap that is not ON the "
                    f"wall welds nothing -- it lays a second bead beside the first, which is the "
                    f"defect this feature exists to remove.")
            n_merge += 1
            lap_lo = reach if lap_lo is None else min(lap_lo, reach)
            lap_hi = reach if lap_hi is None else max(lap_hi, reach)
    if merge_mm > 0 and not n_merge:
        raise SystemExit(
            f"REFUSING TO EMIT: --merge-mm {merge_mm:g} was asked for and NOT ONE lap was built. "
            f"Declared and never applied.")
    if n_merge and max(abs(lap_lo - merge_mm), abs(lap_hi - merge_mm)) > 1e-6:
        raise SystemExit(
            f"REFUSING TO EMIT: the merge laps reach {lap_lo:.6f}..{lap_hi:.6f} mm of arc against "
            f"the {merge_mm:g} mm declared. The header would state an overlap the file does not "
            f"lay.")
    return n_cross, n_merge, (lap_hi or 0.0)


# ------------------------------------------------------------------------------------- the part
def floor_check(r_h, bw, r_ring, bore_r, wrap_deg):
    """GATE 5 — THE LATCH FLOOR MUST NOT BE EXTRUDED INTO THE VOLUME THE BAMBOO STICK OCCUPIES.

    Nothing in this toolchain looked at this and it is the constraint that actually binds the wrap.
    r_poly is measured off the CROSSING chords, and opening the post moves those chords OUTWARD
    (the tips at +-wrap/2 sit further from the axis than the old inward seam did), so the floor disc
    GROWS as the wrap narrows. Measured on the target geometry: +0.087 mm of clearance at
    --wrap-deg 210, +0.269 at 220, and NEGATIVE at 205.24 and below. gate 3 tests crossings against
    post circles only; the floor lattice is not a crossing, so it would print, validate, and then
    refuse the stick.
    """
    edge = r_h + bw / 2.0                 # outer edge of the floor disc's own bead
    inner = r_ring - bore_r               # where the bamboo channel's empty volume starts
    if edge > inner + 1e-9:
        raise SystemExit(
            f"REFUSING TO EMIT: the cross-latch floor's outer bead reaches radius {edge:.3f} mm, "
            f"{edge-inner:.3f} mm INSIDE the {inner:.3f} mm where the bamboo channel's bore begins. "
            f"At --wrap-deg {wrap_deg:g} the post tips sit far enough out that the rim polygon -- "
            f"and with it the latch disc -- has grown into the volume the stick has to occupy. The "
            f"part would print and validate and then refuse the bamboo. Widen --wrap-deg (220 gives "
            f"+0.27 mm here) or cut --bore-allow.")
    return edge, inner


def floor_path(cx, cy, r_h, pitch, phi, seam0, entry, seg):
    """One cross-latch floor layer: [entry] -> lattice -> back out to tower 0's seam.

    The lattice itself is bucket_latch.latch_pts, imported. What is added here is the handoff at
    both ends, because this floor has to hand the head to a ring of towers rather than to a wall.
    Returns (first_point, points_after_it, kinds).
    """
    th = latch.ang(cx, cy, seam0)
    rim = (cx + r_h * math.cos(th), cy + r_h * math.sin(th))
    out = []
    if entry is None:
        cand = latch.latch_pts(cx, cy, r_h, pitch, phi, +1, -1, seg)
        first = cand[0]
        out += cand[1:]
    else:
        first = entry
        out += latch.line_pts(entry, rim, seg)          # radial rib in off the rim polygon
        best = None
        for order in (+1, -1):
            for side in (+1, -1):
                cand = latch.latch_pts(cx, cy, r_h, pitch, phi, order, side, seg)
                d = abs(latch.wrap(latch.ang(cx, cy, cand[0]) - th))
                if best is None or d < best[0]:
                    best = (d, cand)
        cand = best[1]
        out += latch.arc_to(cx, cy, r_h, th, latch.ang(cx, cy, cand[0]), seg)
        out += cand[1:]
    out += latch.arc_to(cx, cy, r_h, latch.ang(cx, cy, out[-1]), th, seg)
    out += latch.line_pts(out[-1], rim, seg)
    out += latch.line_pts(rim, seam0, seg)              # radial rib back out to the tower ring
    return first, out, ["E"] * len(out)


def build(cx, cy, centres, phis, r_t, stagger, half_rad, nseg, narc, n_lay, n_floor,
          floor_pitch, r_h, bridges, merge_mm=0.0):
    """Every layer as {pts, kind, label}. pts[0] is where the layer starts; kind[j] says how the
    head reaches pts[j+1] -- E extrude, T flat metered crossing, B bridge, R floor rim,
    M the lap that welds a crossing ONTO the post it leaves and the post it lands on.

    THE ORDERING IS FORCED, there is no design freedom in it: the head arrives at post k's TRAILING
    tip (stagger - wrap/2), walks CCW through the post's OUTWARD face, and departs from the LEADING
    tip (stagger + wrap/2). So the crossing is leading tip of k -> trailing tip of k+1, and the
    layer closes on post 0's trailing tip, which is exactly where the next layer starts."""
    n = len(centres)
    starts = [seam_point(centres[k], phis[k], r_t, stagger - half_rad) for k in range(n)]
    ends = [seam_point(centres[k], phis[k], r_t, stagger + half_rad) for k in range(n)]
    a0 = [phis[k] + stagger - half_rad for k in range(n)]
    step_rad = 2.0 * half_rad / narc          # the arc's OWN angular step; the lap reuses it

    def weld(tip, c, a_tip, sign):
        """The lap: out along the post from `tip`, and back to EXACTLY `tip`.

        RETURNING TO THE TIP IS THE WHOLE DESIGN. It leaves the crossing chord, the seam window and
        the one-stroke handoff untouched -- the lap is inserted BESIDE the crossing, never in place
        of part of it -- which is what makes --merge-mm 0 a byte-identical superset instead of a
        claim about one. It also costs a second pass over the lap, and that is where the 1.5x of
        bead in the lip comes from; it is declared in the header rather than absorbed quietly.
        `tip` is passed back by IDENTITY, not recomputed, so the chord's start point is the same
        float it always was and gate 1's 1e-6 handoff can never open on a rounding difference.
        """
        out = merge_arc(c, r_t, a_tip, sign, merge_mm, step_rad)
        if not out:
            return [], []
        path = out + out[-2::-1] + [tip]
        return path, ["M"] * len(path)

    layers = []
    for li in range(n_lay):
        is_floor = li < n_floor
        pts, kind = [], []
        if is_floor:
            entry = layers[-1]["pts"][-1] if layers else None
            first, fp, fk = floor_path(cx, cy, r_h, floor_pitch, (math.pi / 2.0) * (li % 2),
                                       starts[0], entry, SEG)
            pts = [first] + fp
            kind = fk
        else:
            pts = [starts[0]]
        cross = "B" if li in bridges else ("R" if is_floor else "T")
        for k in range(n):
            loop = tower_arc(centres[k], r_t, a0[k], 2 * half_rad, narc, ends[k])
            pts += loop
            kind += ["E"] * len(loop)
            nxt = (k + 1) % n
            if cross == "R":
                # ON A FLOOR LAYER THE CROSSING IS THE RIM, so it is subdivided and drawn as a
                # line: the towers' feet are meant to be tied into one solid ring, and a rim that
                # is one long move leaves the layer above nothing to be measured against.
                seg_pts = latch.line_pts(pts[-1], starts[nxt], SEG)
                pts += seg_pts
                kind += ["R"] * len(seg_pts)
            else:
                # THE LAP GOES ON BOTH SIDES OF THE CROSSING AND ONLY AROUND AN AIRBORNE ONE.
                # A floor-layer rim ("R") is already a full-flow extruded line landing on a solid
                # latch disc: there is no net there and nothing to weld, so lapping it would only
                # double material on the feet. The T and B crossings are the net.
                wp, wk = weld(ends[k], centres[k], a0[k] + 2.0 * half_rad, -1)
                pts += wp
                kind += wk
                # ONE MOVE, NOT A SUBDIVIDED LINE, and that is not a shortcut. A bridge is a strand
                # pulled taut across air; every intermediate point is a place the planner can slow
                # down and let it sag. towercoupon.py laid its proven 16.8 mm spans as single moves.
                # Oleg 2026-08-06: "the features are all bridges", "Just different extrusion
                # volume" -- so a solid line, an accent band and the top rim are all THIS move at a
                # different flow, never a second pass and never a wider post.
                pts.append(starts[nxt])
                kind.append(cross)
                wp, wk = weld(starts[nxt], centres[nxt], a0[nxt], +1)
                pts += wp
                kind += wk
        _m = bridges.get(li)
        layers.append({"pts": pts, "kind": kind, "mult": _m,
                       "label": ("floor latch" if is_floor else
                                 (f"posts + BRIDGES {_m:g}x" if _m else "posts"))})
    return layers


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED))
    ap.add_argument("--material", default=None,
                    help="defaults to whatever machine.LOADED says is in this printer")
    ap.add_argument("--dia", type=float, default=100.0,
                    help="diameter mm of the circle the tower CENTRES stand on. 100 = the small "
                         "one Oleg asked to test first (2026-08-05).")
    ap.add_argument("--tower-d", type=float, default=None,
                    help="post outer diameter mm. DERIVED by default from --stick-d + --bore-allow "
                         "+ two beads, because the C-channel's size IS the bamboo's size and two "
                         "authoritative sources for one quantity is a footgun. Pass it to override, "
                         "and the bore is then derived BACKWARDS from it (bore = tower_d - 2 beads) "
                         "so the two can never disagree. --tower-d 2.46 --wrap-deg 360 is the v1 "
                         "post that printed on 2026-08-06.")
    ap.add_argument("--stick-d", type=float, default=3.175,
                    help="the bamboo stick the C-channel has to grip, mm. 3.175 = 1/8 inch, and it "
                         "is a NOMINAL: Oleg's 1/4in bamboo measures 5.8-6.2 against a nominal 6.35 "
                         "(guides/fit-and-assembly-empirics.md), so callipers on the actual sticks "
                         "beat this default.")
    ap.add_argument("--bore-allow", type=float, default=0.25,
                    help="mm added to --stick-d to get the MODELLED bore. THIS IS THE ONE NUMBER "
                         "THAT DECIDES WHETHER THE CHANNEL GRIPS, and the house record says the 0.25 "
                         "in the brief was measured on a 4mm METAL shaft and then condemned ~21 "
                         "parts when it was reused for 6.35mm BAMBOO (the answer there was rod+0.70). "
                         "Three K2 coupon rounds on this exact 1/8in stick landed on ~0.6mm/side for "
                         "a socket in mass; a free single-bead loop bulges less and depth loosens, so "
                         "the true value for THIS geometry is bracketed 0.25..1.725 and NOT measured. "
                         "The file declares that rather than asserting a fit.")
    ap.add_argument("--wrap-deg", type=float, default=210.0,
                    help="how much of the circle each post covers. Oleg 2026-08-06: 'a bit more than "
                         "half circles, which hold one eight of inch bamboo sticks'. The opening "
                         "faces INWARD (toward the bucket axis), so the outer face stays continuous "
                         "and the sticks are hidden from outside. 360 reproduces the closed loop "
                         "point for point -- it is the degenerate case of the same parameterisation, "
                         "not a special branch.")
    ap.add_argument("--pitch", type=float, default=25.0,
                    help="MAXIMUM arc spacing mm between tower centres; the count is derived from "
                         "it and stated in the header.")
    ap.add_argument("--bridge-every", type=int, default=10,
                    help="lay bridges across every gap every N layers. 0 disables the periodic "
                         "bridges; the top layer is bridged either way (it is the rim).")
    ap.add_argument("--bridge-w-mult", type=float, default=1.0,
                    help="flow multiple on an ORDINARY bridge, against the body's own bead. Oleg "
                         "2026-08-06: 'Double the thickness of solid lines'. One move at more flow "
                         "makes a thicker ROD in air; it is never a second pass and never a wider "
                         "post. 1.0 is the old behaviour exactly.")
    ap.add_argument("--accent-every", type=int, default=0,
                    help="lay an ACCENT band every N layers ('4x line width of new line types every "
                         "100 lines'). 0 disables. The bridge layer set is the UNION of the ordinary, "
                         "accent and top schedules, so a band appears on schedule even where the "
                         "layer is not a multiple of --bridge-every.")
    ap.add_argument("--accent-w-mult", type=float, default=4.0,
                    help="flow multiple on an accent band.")
    ap.add_argument("--top-layers", type=int, default=0,
                    help="how many layers at the very top get the top-rim flow ('x8 for the final 4 "
                         "layers on top of the bucket'). 0 leaves the old single bridged top layer.")
    ap.add_argument("--top-w-mult", type=float, default=8.0,
                    help="flow multiple on the top rim. PRECEDENCE: top beats accent beats ordinary. "
                         "CAPPED at the material's own sustained flow at --speed -- see the header, "
                         "which states requested and delivered.")
    ap.add_argument("--bottom-brace-layers", type=int, default=0,
                    help="brace the bottom: for this many layers ABOVE THE FLOOR, bridge every "
                         "--bottom-bridge-every layers instead of every --bridge-every. Oleg "
                         "2026-08-06: 'add some extras printed support lines so bottom of bucket is "
                         "sturdier'. 0 disables.")
    ap.add_argument("--bottom-bridge-every", type=int, default=5,
                    help="the denser bridge interval inside --bottom-brace-layers.")
    ap.add_argument("--floor-layers", type=int, default=5,
                    help="cross-latch floor layers (bucket_latch.py's lattice), each perpendicular "
                         "to the one below. 5 is Oleg's own 2026-07-27 'floor 5 layers ... strict', "
                         "restored 2026-08-05 after he held the 2-layer part: 'Base need to be way "
                         "stronger'. 0 stands the towers straight on the plate.")
    ap.add_argument("--floor-pitch", type=float, default=2.5,
                    help="mm between latch lines. MUST come down with --floor-layers and this is "
                         "measured, not taste: layers are perpendicular, so a layer lands on the "
                         "one below only where the rasters cross. At the old 5.0 a 5-layer floor "
                         "was REFUSED by validate.py at 23%% unsupported; 2.5 reads 2%%.")
    ap.add_argument("--height", type=float, default=40.0, help="total height mm including floor")
    ap.add_argument("--stagger-deg", type=float, default=None,
                    help="rotation of the whole C, in degrees, from the opening pointing dead "
                         "INWARD. The two free ends sit at stagger +- wrap/2 and the crossings run "
                         "tip to tip. Default is the centre of the window seam_window() MEASURES; "
                         "values outside it are REFUSED by check_paths, which is how that gate is "
                         "proven able to fire. DO NOT stagger PER LAYER: the mouth is a snap fit "
                         "with 0.105mm of modelled slack and a +-1 deg per-layer stagger smears the "
                         "slot by 0.074mm of it, which is a taper, not a seam.")
    ap.add_argument("--seam-deg", type=float, default=None,
                    help="COMPAT ONLY, and only at --wrap-deg 360, where the two tips merge into one "
                         "seam: it is the old flag, and --seam-deg X there means --stagger-deg "
                         "X-180. Refused at any other wrap, because an arc has two ends and one "
                         "number cannot place them.")
    ap.add_argument("--speed", type=float, default=machine.DEFAULT_SPEED,
                    help=f"mm/s for every move. Default is the {machine.DEFAULT_SPEED:g} north "
                         f"star, which is a ceiling: slower is allowed, faster is refused.")
    ap.add_argument("--cross-speed", type=float, default=None,
                    help="mm/s for the gap crossings ONLY, which are in-air strands rather than "
                         "structure. Default is --speed, i.e. no second regime. THIS IS THE BIG "
                         "TIME LEVER: measured on the 320mm bucket, the crossings are 1121m of the "
                         "1861m of motion, so 59%% of the wall clock is the head going between "
                         "towers. Raising it treats an in-air strand as a DIFFERENT regime from a "
                         "wall, which is what it is: the 50 north star exists for deposition onto "
                         "structure, and nothing is being deposited onto here. Declared in the "
                         "header as SPEED_CROSS so the gate checks it rather than ignoring it.")
    ap.add_argument("--speed1", type=float, default=25.0,
                    help="mm/s for LAYER 1 only. Half the north star by default, because that is "
                         "the speed zladder.py measured the winning offset at and a bucket run at "
                         "a different first-layer speed would not inherit that result. Oleg "
                         "2026-08-06: \"may he half the speed?\" — a slower bead has longer to wet "
                         "the plate before it freezes.")
    ap.add_argument("--h1", type=float, default=None,
                    help="the REAL first-layer height in mm, measured off zladder.py's plate. This "
                         "is the one number to carry over from that coupon, and it sets TWO things "
                         "that were previously hand-converted: the machine offset needed to reach "
                         "that height (--zoff, derived), and layer 1's extrusion rate, which must "
                         "scale WITH the height or the layer lands narrower than --w1 claims. "
                         "Getting that conversion wrong by hand is exactly how a ladder's answer "
                         "stops transferring to the part it was measured for.")
    ap.add_argument("--zerr", type=float, default=0.15,
                    help="how much HIGHER than it reports this machine's Z zero sits, mm. Only used "
                         "to turn --h1 into an offset. MEASURED 2026-08-06 off a printed plate: at "
                         "offset -0.15 the first layer was clean, at -0.20 the nozzle dragged "
                         "through its own material.")
    ap.add_argument("--zoff", type=float, default=0.0,
                    help="SET_GCODE_OFFSET Z applied right after G28, mm. NEGATIVE brings the "
                         "nozzle CLOSER to the plate. NOT a tuning knob — a correction for a Z "
                         "reference that homes HIGH. Measured 2026-08-06: a commanded Z0.100 on "
                         "this K2 left a gap four sheets of paper thick, and it took one sheet "
                         "only at a commanded Z-0.200. Every commanded Z in the file is unchanged, "
                         "so R1 still reads a pressed 0.1 first layer; the difference is that with "
                         "this set it finally IS one. Take the value from the best-numbered cell "
                         "on zladder.py's plate. Positive is refused.")
    ap.add_argument("--w1", type=float, default=None,
                    help="target LANDED WIDTH of layer 1 in mm. Default reproduces the body's "
                         "own flow pressed into the gap. Oleg 2026-08-05: layer 1 needs full "
                         "flow, a lot of filament glued to the base at max width.")
    ap.add_argument("--fan", type=float, default=None,
                    help="part-cooling fan fraction 0..1 for the BODY, overriding machine.FAN_MAX. "
                         "Layer 1 is unaffected and keeps its material's first-layer value, so the "
                         "plate weld is never chilled.")
    ap.add_argument("--cross-flow", type=float, default=0.25,
                    help="fraction of the body's own extrusion rate to lay while crossing a gap on "
                         "a NON-bridge layer. Oleg 2026-08-05: 'why we ever want to fly without "
                         "anything coming out? Are not we releasing tiny all the time at least'. "
                         "There is NO RETRACTION in this project, so a 'dry' crossing oozes anyway "
                         "and the web in the printed part IS that ooze — the travel was never dry, "
                         "it was UNCONTROLLED extrusion. This meters it. 0 restores the old G0 "
                         "travel exactly. NOT 1.0: at full flow the crossings cost more than the "
                         "posts and the part lands at 1.24x a solid single-bead wall; at 0.25 the "
                         "same part is 0.51x. Thin is the point.")
    ap.add_argument("--merge-mm", type=float, default=2.0,
                    help="mm of ARC LENGTH that each gap crossing laps ONTO the post, at BOTH ends. "
                         "Oleg 2026-08-06, holding the printed bucket: 'you need to merge the net "
                         "and outer wall print in many places, it cant be separate closly aligned "
                         "pieces'. Before departing, the head runs back along the post's own arc "
                         "this far and returns to the tip; after landing, it runs forward along the "
                         "next post's arc the same distance and returns. The strand is then welded "
                         "over a LENGTH at each end instead of at a point. 0 reproduces the old "
                         "output byte for byte -- the crossing chord itself never changes.")
    ap.add_argument("--merge-flow", type=float, default=None,
                    help="fraction of the body's own extrusion rate laid on EACH PASS of the lap. "
                         "Default follows --cross-flow, because the weld IS the strand pressed onto "
                         "the wall rather than a new feature with its own volume. IT IS A SEPARATE "
                         "KNOB ON PURPOSE: an in-air strand and a lap onto solid material are "
                         "different physics, so a future change to the fabric must not silently "
                         "change the weld. The lap is out AND back, so the region receives 2x this "
                         "on top of the wall's own 1.0 -- see the header, which prints the packing "
                         "and what it does to the modelled bamboo mouth.")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    # MATERIAL FOLLOWS THE PRINTER. A part generated for one machine with another machine's
    # filament is silently wrong: right geometry, wrong temperature, wrong flow ceiling.
    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    bw, lh = machine.SLICER_LINE_W, machine.SLICER_LAYER_H
    press = machine.PRESS_HARD                      # 0.10, R1
    for _nm, _v in (("--speed", a.speed), ("--speed1", a.speed1)):
        if _v > machine.MAX_SPEED + 1e-9:
            raise SystemExit(f"REFUSING TO EMIT: {_nm} {_v:g} is above the "
                             f"{machine.MAX_SPEED:g} mm/s north star, which is a ceiling. Slower "
                             f"is allowed; faster is not.")
    # A POSITIVE OFFSET IS THE DEFECT, NOT A CORRECTION FOR IT: it lifts the nozzle further from
    # the plate. Refused here because validate.py cannot see SET_GCODE_OFFSET at all — R1 would go
    # on reading the commanded Z0.100 and passing a file printing half a millimetre in the air,
    # which is exactly the blindness that let three max-bucket starts through on 2026-08-05/06.
    # --h1 DERIVES --zoff RATHER THAN SITTING BESIDE IT. Two knobs that set the same physical
    # quantity is a footgun: whichever the caller forgets silently wins. Given together, refuse.
    if a.h1 is not None:
        if abs(a.zoff) > 1e-9:
            raise SystemExit(f"REFUSING TO EMIT: --h1 {a.h1:g} and --zoff {a.zoff:+g} both set. "
                             f"--h1 DERIVES the offset (h1 - {press:g} - zerr); passing both means "
                             f"one of them is silently ignored. Pass --h1 alone.")
        if a.h1 <= 0:
            raise SystemExit(f"REFUSING TO EMIT: --h1 {a.h1:g} is not a positive height.")
        try:
            a.zoff = machine.zoff_for(a.h1, a.zerr)
        except ValueError as _e:
            raise SystemExit(f"REFUSING TO EMIT: {_e}")
    if a.zoff > 1e-9:
        _why = (f" With --zerr {a.zerr:g} the tallest first layer reachable without lifting the "
                f"nozzle above the machine's own zero is {press + a.zerr:.3f}mm."
                if a.h1 is not None else "")
        raise SystemExit(f"REFUSING TO EMIT: --zoff {a.zoff:+g} is POSITIVE, which lifts the "
                         f"nozzle AWAY from the plate.{_why} Use a negative value to press harder, "
                         f"or 0 for the machine's own zero.")
    speed = a.speed
    f = round(speed * 60)
    # LAYER 1 CARRIES ITS OWN FEEDRATE. F is sticky in gcode, so it is enough to set it on each
    # layer's standalone Z word — except in the gap-crossing branch, which writes its own F and
    # would otherwise snap layer 1 back to the body speed halfway through the floor.
    speed1 = a.speed1
    f_l1 = round(speed1 * 60)
    # THE CROSSING REGIME. Same sticky-F rule as layer 1: the crossing branch writes its own F, and
    # the next body move writes F back, so the two never bleed into each other.
    speed_x = a.cross_speed if a.cross_speed else speed
    f_x = round(speed_x * 60)
    temp = machine.MATERIAL_TEMP[a.material]        # READ, never typed: 210 for the pla loaded now
    bed = machine.bed_for(a.material, a.printer)
    # BODY FAN. machine.FAN_MAX is Oleg's 20% PLA ceiling (2026-07-26), right for a flat part where
    # high fan chills the bead as it lands and costs adhesion. A ring of 40 mm towers is the other
    # regime -- the single tower that failed on 2026-08-05 failed by never freezing at all. So the
    # override is per-run rather than a change to FAN_MAX, which must not move; and layer 1 keeps
    # fan_first_layer(), which is the exact thing the 20% rule protects.
    fan = machine.FAN_MAX[a.material] if a.fan is None else max(0.0, min(1.0, a.fan))
    e_mm = bw * lh / A_FIL                          # filament mm per mm of path -- ONE value
    # LAYER 1 GETS ITS OWN RATE, from a target LANDED WIDTH. See the emitter for his instruction.
    # A bead pressed into a `press` gap occupies w1 x press of cross-section, so the filament it
    # needs is w1 * press / A_FIL. Stating it as a width rather than a flow multiplier means the
    # number in the header is the thing you can measure on the plate with callipers.
    w1 = a.w1 if a.w1 else bw * lh / press          # default reproduces the old behaviour exactly
    # LAYER 1'S RATE IS METERED AGAINST THE HEIGHT IT ACTUALLY LANDS AT, not against PRESS_HARD.
    # Those are the same number only when the machine's Z zero is honest, and on this K2 it is not:
    # it homes ~0.15mm high, so a file commanding Z0.100 lays its first layer into whatever gap
    # --zoff leaves. Metering w1 * press / A_FIL into a 0.20 gap lands HALF the width the header
    # claims, which is precisely the mismatch that made three ladders unreadable -- the material
    # stayed still while the gap moved. h1_real is the gap the bead is actually laid into.
    h1_real = a.h1 if a.h1 is not None else press
    e_mm_l1 = machine.layer1_rate(w1, h1_real)   # ONE implementation, machine.py
    flow = bw * lh * speed
    r8cap = machine.flow_cap(a.material, a.printer)

    # ---------------------------------------------------------------- THE C-CHANNEL, DERIVED
    # ONE AUTHORITATIVE SOURCE FOR THE POST'S SIZE. The channel exists to hold a stick, so the
    # stick's diameter sets it; --tower-d overrides and then the bore is derived BACKWARDS from it,
    # so the two numbers can never state different things about the same wall.
    if a.wrap_deg <= 0 or a.wrap_deg > 360.0 + 1e-9:
        ap.error(f"--wrap-deg {a.wrap_deg:g} is not in (0, 360]")
    if a.tower_d is None:
        bore_d = a.stick_d + a.bore_allow
        a.tower_d = bore_d + 2.0 * bw
        td_src = f"DERIVED from --stick-d {a.stick_d:g} + --bore-allow {a.bore_allow:g} + 2 beads"
    else:
        bore_d = a.tower_d - 2.0 * bw
        td_src = f"GIVEN; the bore is derived backwards from it as {bore_d:.3f}"
    bore_r = bore_d / 2.0
    if a.seam_deg is not None:
        if abs(a.wrap_deg - 360.0) > 1e-9:
            ap.error(f"--seam-deg is the CLOSED-LOOP flag and there is no single seam at "
                     f"--wrap-deg {a.wrap_deg:g}: an open arc has two free ends. Use --stagger-deg.")
        if a.stagger_deg is not None:
            ap.error("--seam-deg and --stagger-deg both set; they are the same quantity offset by "
                     "180 degrees, so one of them would be silently ignored.")
        a.stagger_deg = a.seam_deg - 180.0
    # THE POST FLOOR IS DERIVED, NOT CHOSEN (towercoupon.py): below 2 x bead the toolpath circle
    # is narrower than the bead, the loop folds through its own centre, and what prints is a blob
    # with a seam rather than a tower.
    if a.tower_d < 2.0 * bw - 1e-9:
        raise SystemExit(f"REFUSING TO EMIT: --tower-d {a.tower_d:g} is under the {2*bw:.2f} mm "
                         f"floor for a {bw:g} mm bead (D_min = 2 x bead). Below it the nozzle "
                         f"orbits inside its own bead width and extrudes essentially in place.")
    if a.floor_layers < 0:
        ap.error("--floor-layers cannot be negative")
    if a.floor_pitch <= bw:
        ap.error(f"--floor-pitch {a.floor_pitch:g} is not wider than the {bw:g} bead: that is a "
                 f"solid floor drawn as a lattice, with every line overlapping its neighbour")

    r_ring = a.dia / 2.0
    r_t = (a.tower_d - bw) / 2.0                    # CENTRELINE radius: single-wall, the path
    circ_ring = 2 * math.pi * r_ring
    # CEIL, NOT ROUND. --pitch is a MAXIMUM spacing here, so the count goes UP when the circle does
    # not divide evenly. On the 100 mm default that is 13 towers rather than the 12 an even
    # division suggests, and the reason is the only bridge number that has actually printed: at 12
    # the unsupported air is 17.9 mm, PAST the 16.8 mm proven tonight; at 13 it is 15.9 mm, inside
    # it. Rounding down would have put the part outside its own evidence to save one tower.
    n_tow = max(3, int(math.ceil(circ_ring / a.pitch)))
    phis = [2 * math.pi * k / n_tow for k in range(n_tow)]

    bedx, bedy = machine.BED[a.printer]
    cx, cy = bedx / 2.0, bedy / 2.0
    centres = [(cx + r_ring * math.cos(p), cy + r_ring * math.sin(p)) for p in phis]

    # THE WINDOW IS MEASURED BEFORE ANY GEOMETRY IS BUILT, and the default sits at its centre.
    half_deg = a.wrap_deg / 2.0
    half_rad = math.radians(half_deg)
    offs = seam_window(centres, phis, r_t, half_deg)
    win_c, win_w = widest_run(offs)
    if win_c is None:
        raise SystemExit(
            f"REFUSING TO EMIT: NO stagger lets the head cross between {n_tow} posts of "
            f"{a.tower_d:g} mm on a {a.dia:g} mm circle without passing inside a post wall. The "
            f"posts are too close together for a flat crossing; widen --dia or raise --pitch.")
    stag_deg = win_c if a.stagger_deg is None else a.stagger_deg
    stagger = math.radians(stag_deg)
    starts = [seam_point(centres[k], phis[k], r_t, stagger - half_rad) for k in range(n_tow)]
    ends = [seam_point(centres[k], phis[k], r_t, stagger + half_rad) for k in range(n_tow)]

    # ------------------------------------------------------------------ THE MERGE LAP, VALIDATED
    # Three ways --merge-mm can be wrong, and each is refused with the number that refused it
    # rather than clamped silently -- a clamp would print a header describing a lap the operator
    # did not ask for.
    arc_len = r_t * 2.0 * half_rad                  # the whole post, tip to tip, in mm of path
    merge_flow = a.cross_flow if a.merge_flow is None else a.merge_flow
    if a.merge_mm < 0:
        ap.error(f"--merge-mm {a.merge_mm:g} is negative")
    if a.merge_flow is not None and a.merge_flow < 0:
        ap.error(f"--merge-flow {a.merge_flow:g} is negative")
    if a.merge_mm > 0:
        # A ZERO-FLOW LAP IS A DRY DRAG ACROSS THE WALL, which is strictly worse than the point
        # contact it was meant to fix: the nozzle ploughs the bead it just laid and welds nothing.
        if merge_flow <= 0:
            raise SystemExit(
                f"REFUSING TO EMIT: --merge-mm {a.merge_mm:g} with a lap flow of 0 "
                f"({'--merge-flow 0' if a.merge_flow is not None else '--cross-flow 0, which the lap follows'}). "
                f"That drags the nozzle {a.merge_mm:g} mm back across the wall it just laid with "
                f"nothing coming out -- a plough, not a weld. Pass --merge-flow, or --merge-mm 0.")
        # THE TWO LAPS ARE AT OPPOSITE ENDS OF THE SAME ARC, so they collide at half the arc, not
        # at the whole of it. Past that the post's middle takes both laps and the lip flow doubles
        # again; at --wrap-deg 30 the whole arc is 1.11 mm and a 2 mm lap would wrap past the far
        # tip into the mouth. Refused with the arc it measured, so the message states the ceiling.
        if a.merge_mm > arc_len / 2.0 + 1e-9:
            raise SystemExit(
                f"REFUSING TO EMIT: --merge-mm {a.merge_mm:g} is more than half the "
                f"{arc_len:.2f} mm arc of a {a.wrap_deg:g}-degree post ({a.tower_d:.3f} mm OD). The "
                f"lap at each end would run past the middle and overlap the other one, so the post "
                f"would carry {1.0 + 4.0*merge_flow:.2f}x of bead along its whole length instead of "
                f"{1.0 + 2.0*merge_flow:.2f}x at its lips. Cap is {arc_len/2.0:.2f} mm here.")
        if r8cap and merge_flow * flow > r8cap + 1e-9:
            raise SystemExit(
                f"REFUSING TO EMIT: a lap at --merge-flow {merge_flow:g} runs at "
                f"{merge_flow*flow:.2f} mm3/s against the {r8cap:g} mm3/s maintained figure for "
                f"{a.material} on this machine. The lap runs at the BODY speed ({speed:g} mm/s), "
                f"not the crossing speed, so its flow is merge_flow x bead x body speed.")
    merge_mm2 = merge_flow * bw * lh                # cross-section of ONE pass of the lap
    lap_pack = 1.0 + 2.0 * merge_flow               # the wall's own bead + both passes of the lap

    # THE LATCH DISC STOPS ONE BEAD INSIDE THE RIM POLYGON, and that radius is MEASURED off the
    # emitted chords rather than computed from a cos(pi/n) that would silently be wrong the moment
    # the ends move off the radial. THE CHORD IS TIP TO TIP now, so it sits FURTHER OUT than the
    # closed loop's inward seam did and this disc GREW -- which is what gate 5 below exists for.
    r_poly = min(math.hypot(ends[k][0] + (starts[(k+1) % n_tow][0]-ends[k][0])*t/64.0 - cx,
                            ends[k][1] + (starts[(k+1) % n_tow][1]-ends[k][1])*t/64.0 - cy)
                 for k in range(n_tow) for t in range(65))
    r_h = r_poly - bw
    if a.floor_layers and r_h <= a.floor_pitch:
        ap.error(f"--dia {a.dia:g} leaves a {r_h:.1f} mm latch disc, which does not fit a "
                 f"{a.floor_pitch:g} mm pitch")
    floor_edge, bore_inner = (floor_check(r_h, bw, r_ring, bore_r, a.wrap_deg)
                              if a.floor_layers else (r_h + bw / 2.0, r_ring - bore_r))

    # THE MOUTH. The two tips are +-wrap/2 from the outward radial, so the SHORT way between them
    # is (360 - wrap) of arc and the clear opening is that chord minus one bead (half a lip bead
    # bulges in from each side). This is the number that decides whether the C captures the stick
    # at all, and it is MODELLED: the printed value depends on a shrink this project has not
    # measured for a free single-bead loop of this size. Both are reported; neither is asserted.
    tip_gap = 2.0 * r_t * math.sin(math.radians((360.0 - a.wrap_deg) / 2.0))
    mouth = tip_gap - bw
    SHRINK_METAL = 0.25          # guides/fit-and-assembly-empirics.md, ~6mm bore, METAL shaft
    mouth_shrunk = mouth - SHRINK_METAL
    # THE LAP LANDS ON THE LIPS AND THE LIPS ARE THE MOUTH, so --merge-mm moves a number this file
    # already declines to claim. MODELLED, and the model is stated: the nozzle sets the layer
    # height, so extra material at a fixed Z spreads SIDEWAYS rather than stacking, and a lip
    # carrying lap_pack of a bead lands lap_pack x {bw} wide. Half of each lip's width bulges into
    # the opening, so the clear mouth is the tip chord minus one whole lip bead -- the same
    # arithmetic as the line above it, with the lap's bead in place of the plain one.
    # NOTHING HERE IS MEASURED. It is printed so the tradeoff is visible and tunable (--merge-flow),
    # not so it can be claimed: this file already DECLINES to claim a fit, and narrowing the mouth
    # toward the stick is exactly the direction that would flatter us into claiming one.
    lip_w = lap_pack * bw if a.merge_mm > 0 else bw
    mouth_lap = tip_gap - lip_w

    circ_t = 2 * math.pi * r_t
    nseg = max(MIN_TOWER_SEGS, int(math.ceil(circ_t / SEG)))     # PER FULL REVOLUTION
    narc = arc_segs(nseg, a.wrap_deg)
    n_lay = int(round((a.height - press) / lh)) + 1
    if n_lay <= a.floor_layers:
        ap.error(f"--height {a.height:g} gives {n_lay} layers, not more than the {a.floor_layers} "
                 f"floor layers asked for -- there would be no towers")
    top_z = press + (n_lay - 1) * lh

    # ------------------------------------------------------------- THE BRIDGE FLOW SCHEDULE
    # THE LAYER SET IS THE UNION OF THREE SCHEDULES, and the multiplier is decided by PRECEDENCE:
    # top beats accent beats ordinary. Union rather than intersection is the whole point -- an
    # accent band must appear on ITS schedule even where that layer is not a multiple of
    # --bridge-every, or "every 100 lines" quietly becomes "every 100 that happen to divide by 20".
    #
    # THE TOP MULTIPLIER IS CAPPED BY PHYSICS, NOT BY TASTE. A bridge runs at the body speed, so
    # its flow is mult x bead x speed. Asking for 8x here is asking the extruder for 78.7 mm3/s
    # against a maintained figure of 55: it does not make a fatter rod, it makes a skipping
    # extruder. Slowing the move instead was considered and REJECTED -- a bridge is a strand pulled
    # taut across 33mm of air and time is the thing that makes it sag, so cutting speed to buy
    # volume trades the risk we can least afford. Requested and delivered are both declared below.
    mult_cap = r8cap / flow if (r8cap and flow) else None
    def _cap(m):
        return m if (mult_cap is None or m <= mult_cap) else math.floor(mult_cap * 100) / 100.0
    m_ord, m_acc = _cap(a.bridge_w_mult), _cap(a.accent_w_mult)
    m_top = _cap(a.top_w_mult)
    _cap_all = (("--bridge-w-mult", a.bridge_w_mult, m_ord),
                ("--accent-w-mult", a.accent_w_mult, m_acc),
                ("--top-w-mult", a.top_w_mult, m_top))
    bridges = {}
    body = range(a.floor_layers, n_lay)
    if a.bridge_every > 0:
        for li in body:
            every = (a.bottom_bridge_every
                     if (a.bottom_brace_layers > 0 and a.bottom_bridge_every > 0
                         and li - a.floor_layers < a.bottom_brace_layers)
                     else a.bridge_every)
            if every > 0 and li % every == 0:
                bridges[li] = m_ord
    if a.accent_every > 0:
        for li in body:
            if li % a.accent_every == 0:
                bridges[li] = m_acc
    bridges[n_lay - 1] = m_ord if a.top_layers <= 0 else m_top
    for li in range(max(a.floor_layers, n_lay - max(0, a.top_layers)), n_lay):
        bridges[li] = m_top
    n_brace = sum(1 for li in bridges
                  if a.bottom_brace_layers > 0 and li - a.floor_layers < a.bottom_brace_layers)
    # ONLY REPORT A CAP THAT ACTUALLY BIT. --top-w-mult is capped arithmetically even when
    # --top-layers is 0 and no layer ever carries it; announcing that would be a warning about a
    # move the file does not contain.
    _used = set(bridges.values())
    capped = [t for t in _cap_all if t[2] < t[1] - 1e-9 and t[2] in _used]

    layers = build(cx, cy, centres, phis, r_t, stagger, half_rad, nseg, narc, n_lay,
                   a.floor_layers, a.floor_pitch, r_h, bridges, a.merge_mm)
    n_cross, n_merge, lap_measured = check_paths(layers, centres, r_t, (bedx, bedy), press, lh,
                                                 stag_deg, bw, w1, a.merge_mm)

    # ------------------------------------------------------------------ measured off the built path
    def layer_mm(L):
        ext = trav = 0.0
        for j, k in enumerate(L["kind"]):
            d = math.dist(L["pts"][j], L["pts"][j + 1])
            if k == "T":
                trav += d
            else:
                ext += d
        return ext, trav
    _tow = [layer_mm(L) for i, L in enumerate(layers)
            if i >= a.floor_layers and i not in bridges]
    tow_ext, tow_trav = (_tow[0] if _tow else layer_mm(layers[-1]))
    # THE CROSSINGS ARE DIVIDED BY THE CROSSING SPEED. Both of these used to divide everything by
    # `speed`, so at --cross-speed 200 the file printed a 23.42 s layer clock beside the sentence
    # "six towers at 4.50s STOOD, one at 0.57s roped" -- 2.6x the real 9.13 s, on the one number
    # the part's cooling is judged against. The C-channel is what made it load-bearing: an open arc
    # extrudes a third of what a closed 8.2 post did.
    lay_s_ext = tow_ext / speed                      # post cooling: extruding time per layer
    lay_s_all = tow_ext / speed + tow_trav / speed_x  # wall clock per layer, crossings included
    path_mm = sum(layer_mm(L)[0] for L in layers)
    trav_mm = sum(layer_mm(L)[1] for L in layers)
    floor_mm = sum(layer_mm(L)[0] for L in layers[:a.floor_layers])
    # THE FLOOR'S OWN CLOCK, at the speeds the floor actually runs: layer 1 at --speed1, the rest
    # at --speed. Dividing it all by --speed under-reported the watch window by the whole
    # first-layer slowdown, which is the one layer the instruction tells the operator to watch.
    floor_mins = sum(layer_mm(Lz)[0] / (speed1 if i == 0 else speed)
                     for i, Lz in enumerate(layers[:a.floor_layers])) / 60.0
    # A METERED CROSSING IS EXTRUSION, NOT TRAVEL. layer_mm() classifies by kind, and kind "T" is
    # travel only while --cross-flow is 0; above 0 the emitter writes those same moves as G1 with E
    # ("; THIN CROSS"). Left as travel, the summary described a file it had just written as having
    # 44.5m of dry crossings when validate.py reads the emitted file as travel=0.4m extrude=80.4m.
    cross_mm = trav_mm if a.cross_flow > 0 else 0.0
    ext_mm = path_mm + cross_mm                      # path with material coming out of the nozzle
    dry_mm = trav_mm - cross_mm                      # path flown dry
    n_moves = sum(len(L["kind"]) for L in layers)
    # THE LAP'S OWN LENGTH AND CLOCK, measured off the built points. It is inside path_mm already
    # (a lap extrudes), but it is the price of the feature and a price nobody states is a price
    # nobody can decide about: it runs at the BODY speed, so it is minutes, not seconds.
    lap_mm = sum(math.dist(Lz["pts"][j], Lz["pts"][j + 1])
                 for Lz in layers for j, k in enumerate(Lz["kind"]) if k == "M")
    lap_mins = lap_mm / speed / 60.0
    # WHAT LAYER 1 ACTUALLY LANDS AT — which is w1, by construction, because e_mm_l1 was DERIVED
    # from it (e = w1 * press / A_FIL). This used to be re-typed as bw*lh/press, the DEFAULT w1,
    # so every run with --w1 printed a floor description of a first layer it was not laying: the
    # part that printed tonight declares LAYER1_WIDTH=3.00 in one header line and "lands 1.97mm
    # wide" in another. Same file, two widths, and the wrong one was the one the floor's coverage
    # claim was computed from.
    land_w1 = w1
    # FLOOR THICKNESS OFF THE LAYER LADDER, not off the argument: layer 1 occupies the press gap
    # and every layer after it one lh, which is the same z ladder the emitter writes.
    floor_h = press + max(0, a.floor_layers - 1) * lh
    # ends[0] -> starts[1], NOT seams[0] -> seams[1]. The crossing is tip to tip; reading the old
    # single-seam pair reported 35.42mm while every bridge in the file spans 33.22, and that number
    # is quoted four times in this header and onto the comment of every bridge move in the file.
    gap_chord = math.dist(ends[0], starts[1])
    bridge_air = air_span(ends[0], starts[1], centres[0], centres[1], r_t, bw,
                          arc=(phis[0], phis[1], half_rad))
    # WHEN THE SPAN IS PAST THE ONE THAT HAS HELD, SAY SO AND HAND OVER THE FIX. Searched by
    # running the real geometry at each candidate count rather than by inverting a formula, so the
    # suggested --pitch is one the generator provably reproduces.
    # THE SUGGESTED VALUE IS RUN THROUGH ceil() BEFORE IT IS PRINTED. The first version handed over
    # circ/nc rounded to 2dp, and --pitch 19.63 built SEVENTEEN towers rather than the sixteen it
    # advertised: circ/16 is 19.6350, so rounding DOWN crosses the ceil boundary. A suggestion that
    # does not reproduce is a wrong number wearing a measurement's clothes. --pitch p yields count
    # nc for p in [circ/nc, circ/(nc-1)), so the midpoint of that interval is taken and then
    # VERIFIED against the generator's own arithmetic; a hint that fails to reproduce is dropped.
    pitch_hint = None
    if bridge_air > PROVEN_AIR_MM:
        for nc in range(n_tow + 1, n_tow + 40):
            _air = air_for_count(cx, cy, r_ring, r_t, bw, nc, half_deg)
            if _air is not None and _air <= PROVEN_AIR_MM:
                _p = round(0.5 * (circ_ring / nc + circ_ring / (nc - 1)), 2)
                if max(3, int(math.ceil(circ_ring / _p))) == nc:
                    pitch_hint = (_p, nc, _air)
                break
    # SAME DEFECT, SAME FIX: layer 1 runs at --speed1 and the crossings at --cross-speed, so a
    # single division by `speed` was a wall-clock estimate for a file that does not exist.
    mins = sum(layer_mm(Lz)[0] / (speed1 if i == 0 else speed)
               + layer_mm(Lz)[1] / (speed1 if i == 0 else speed_x)
               for i, Lz in enumerate(layers)) / 60.0
    # vol_cm3 IS NOT MODELLED HERE. It is read off the E the emitter actually writes, below the
    # emission loop, because three different rates now leave this nozzle: the body's e_mm, layer 1's
    # e_mm_l1 (--w1), and a crossing's e_mm x --cross-flow. path_mm x bw x lh knew only the first
    # and called the part 7.0 cm3 when its own E said 9.59.

    L = []
    w = L.append
    # THE FIRST LINE NAMES THE WHOLE SCHEDULE, not just --bridge-every. With three schedules in
    # union, "bridged every 20 layers" is true of one of them and false of the file.
    w(f"; BUCKET ON TOWERS — {n_tow} "
      + ("towers" if abs(a.wrap_deg - 360.0) < 1e-9 else f"{a.wrap_deg:g}-deg C-channel columns")
      + f" on a {a.dia:g}mm circle, {len(bridges)} bridged layers of {n_lay}")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={speed:.4f}")
    # R3 EXEMPTS A DECLARED LAYER-1 REGIME, AND ONLY A DECLARED ONE. Without this stamp a file
    # running two feedrates fails constant-speed, which is correct: layer 1 is a different
    # regime (pressed to the plate), not a wobble inside the body's one.
    w(f"; SPEED_LAYER1={speed1:.4f}")
    w(f"; SPEED_CROSS={speed_x:.4f}")
    if speed_x > machine.MAX_SPEED + 1e-9:
        # THE CEILING IS RAISED OUT LOUD OR NOT AT ALL. validate.py honours '; SPEED_OVERRIDE=' and
        # PRINTS that the north star was raised, so this can never be a quiet change. It applies to
        # the CROSSINGS only in practice, because the body's own --speed is separately refused above
        # if it exceeds the north star -- the override cannot be used to smuggle a faster wall.
        #
        # Why an in-air strand is a different regime from a wall: the 50 north star exists for
        # DEPOSITION -- bead width, cooling, the weld to what is underneath. A strand flung between
        # two towers is laid onto nothing. It has no adhesion to get wrong and no width to hold, and
        # crossing faster gives it LESS time to sag, not more.
        w(f"; SPEED_OVERRIDE={speed_x:.4f}")
        w(f";   raised from the {machine.MAX_SPEED:g} mm/s north star for the gap crossings ONLY. "
          f"Oleg 2026-08-06: \"I asked you to speed it up not slow it down\". The crossings are "
          f"{speed_x/speed:.1f}x the body speed and they are 59% of this print's motion.")
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    # THE GAP NAMED HERE IS THE GAP THE BEAD IS LAID INTO, which is --h1 and is NOT PRESS_HARD
    # once --zoff is in play. The old wording said "pressed into the 0.1 gap" on a file laying its
    # first layer into 0.15, so the one line an operator would check with callipers described a
    # different layer from the one being printed.
    w(f"; LAYER1_WIDTH={w1:.2f}mm landed into the {h1_real:g} gap = {w1*h1_real:.4f}mm2/mm "
      f"({w1*h1_real/(bw*lh):.2f}x the body's own {bw*lh:.4f}mm2 bead)")
    w(f"; PRINT_TEMP={temp}")
    w(f"; bead {bw:g}x{lh:g}   nozzle {machine.NOZZLE:g}   (Oleg 2026-08-04; Klipper's "
      f"nozzle_diameter field reads 0.4 on this machine and lies)")
    w(f"; FLOW_DERATE=a {machine.NOZZLE:g} nozzle laying its own slicer's {bw:g}x{lh:g} bead at the "
      f"{speed:g} mm/s north star delivers {flow:.2f} mm3/s. Reaching {0.8*r8cap:g} would mean "
      f"WIDENING the bead, and a single-wall tower's wall thickness IS the bead. Declared, not "
      f"silent.")
    # THE BRIDGE FLOW SCHEDULE IS DECLARED AS CROSS-SECTIONS, not as multipliers alone. A
    # multiplier can only be checked by rerunning the arithmetic that produced it, which is not an
    # independent check; mm2 per mm of path is measurable straight off the emitted E and distance,
    # which is exactly what validate.py's R4e does with this line.
    _mm2s = sorted({round(m * bw * lh, 4) for m in bridges.values()})
    w(f"; BRIDGE_FLOW={','.join(f'{m:.2f}' for m in sorted(set(bridges.values())))}")
    w(f"; BRIDGE_MM2={','.join(f'{v:.4f}' for v in _mm2s)}")
    # THE LAP IS DECLARED AS A LENGTH AND A CROSS-SECTION, both measurable off the emitted moves.
    # MERGE_MM is the arc length gate 6 measured on the built points, NOT the argument that asked
    # for it, so a lap that silently came out short would contradict its own stamp.
    if a.merge_mm > 0:
        w(f"; MERGE_MM={lap_measured:.4f}")
        w(f"; MERGE_MM2={merge_mm2:.4f}")
        w(f"; MERGE_PASSES=2")
    w(";")
    w("; ---------------- WHAT THIS PART IS ----------------")
    if abs(a.wrap_deg - 360.0) < 1e-9:
        w(f"; POSTS  {n_tow} single-wall CLOSED posts, {a.tower_d:g}mm outer "
          f"({a.tower_d/bw:.0f} beads), toolpath radius {r_t:.2f}mm.")
    else:
        w(f"; POSTS  {n_tow} single-wall C-CHANNELS that snap onto a bamboo stick. Oleg 2026-08-06: "
          f"\"columns are")
        w(f";        half... a bit more than half circles, which hold one eight of inch. Bamboo "
          f"sticks so we")
        w(f";        reenforxw the most fragile part off bucket\".")
        w(f";          stick        {a.stick_d:.3f}mm  (--stick-d; 1/8 inch NOMINAL, not callipered)")
        w(f";          bore         {2*bore_r:.3f}mm  MODELLED (--bore-allow {a.bore_allow:g})")
        w(f";          channel OD   {a.tower_d:.3f}mm  ({td_src})")
        w(f";          wrap         {a.wrap_deg:g} deg, opening {360-a.wrap_deg:g} deg facing INWARD "
          f"at the bucket axis,")
        w(f";                       so the OUTER face stays continuous and the sticks do not show.")
        w(f";          mouth        {mouth:.3f}mm modelled clear between the two lip beads, against "
          f"a {a.stick_d:.3f}mm stick")
        w(f";                       = {mouth-a.stick_d:+.3f}mm. THE MODELLED PART DOES NOT GRIP if "
          f"that is positive;")
        w(f";                       grip then depends WHOLLY on print shrink, which is NOT measured "
          f"for this")
        w(f";                       geometry class. See UNMEASURED below -- this file DECLINES to "
          f"claim a fit.")
        w(f";        A closed post has one seam; a C has TWO FREE ENDS, and they are the attachment "
          f"points:")
        w(f";        the head arrives at a post's trailing tip, walks CCW across its outward face, "
          f"and leaves")
        w(f";        from the leading tip. Bridges and fabric strands land ON the tips, never into "
          f"the opening.")
        w(f";        {narc} segments of {a.wrap_deg/narc:.2f} deg per arc ({nseg} per full "
          f"revolution, so --wrap-deg 360")
        w(f";        reproduces the closed loop point for point rather than by a special case).")
    w(f";        Centres on a {a.dia:g}mm circle at {circ_ring/n_tow:.2f}mm arc spacing (--pitch "
      f"{a.pitch:g} is a MAXIMUM,")
    w(f";        so the count is ceil({circ_ring:.1f}/{a.pitch:g})={n_tow}). Each post only ever "
      f"goes UP.")
    if abs(a.wrap_deg - 360.0) > 1e-9:
        w(f";        THE 8.2mm BREAKAGE DATA DOES NOT APPLY HERE and is deliberately not repeated: "
          f"4.92/6.56/9.84")
        w(f";        was measured by hand on CLOSED posts. Nothing has been broken, or printed, as "
          f"a {a.tower_d:.2f}mm C.")
    w(f"; BRIDGE every gap is spanned on a schedule, and always on the top layer (the rim).")
    w(f";        {gap_chord:.2f}mm tip to tip, of which {bridge_air:.2f}mm is UNSUPPORTED AIR — "
      f"measured on the")
    w(f";        chord, not the (span - one diameter) the coupon uses, because THIS chord clears "
      f"both posts")
    w(f";        instead of landing across them, so almost none of it is over material.")
    w(f";        Each bridge is ONE move, so nothing in the planner can slow it and let it sag.")
    w(f";        FLOW SCHEDULE — Oleg: \"the features are all bridges\", \"Just different extrusion "
      f"volume\".")
    w(f";        One move at more flow makes a thicker ROD in air. Body bead {bw*lh:.4f}mm2.")
    for _nm, _n, _m in (("ordinary", len([1 for li, m in bridges.items() if m == m_ord]), m_ord),
                        ("accent", len([1 for li, m in bridges.items() if m == m_acc]), m_acc),
                        ("top rim", len([1 for li, m in bridges.items() if m == m_top]), m_top)):
        if _n:
            _a2 = _m * bw * lh
            w(f";          {_nm:<9}{_m:>5.2f}x  {_a2:.4f}mm2  rod {2*math.sqrt(_a2/math.pi):.3f}mm  "
              f"{_m*flow:5.2f}mm3/s   on {_n} layer(s)")
    w(f";          fabric   {a.cross_flow:>5.2f}x  {a.cross_flow*bw*lh:.4f}mm2  "
      f"rod {2*math.sqrt(a.cross_flow*bw*lh/math.pi):.3f}mm  "
      f"{a.cross_flow*bw*lh*speed_x:5.2f}mm3/s   on every non-bridge layer")
    w(f";        THE FABRIC IS THE PART'S CHARACTER AND IT IS UNCHANGED. Its "
      f"{2*math.sqrt(a.cross_flow*bw*lh/math.pi):.3f}mm rod exceeds the")
    w(f";        {lh:g}mm layer pitch, so consecutive strands touch and FUSE into a continuous "
      f"membrane. Oleg,")
    w(f";        2026-08-06: \"Don't remove the fabric that has to stay\".")
    if a.merge_mm > 0:
        w(f"; MERGE  every crossing is LAPPED ONTO THE POST AT BOTH ENDS. Oleg 2026-08-06, holding "
          f"the printed")
        w(f";        bucket: \"you need to merge the net and outer wall print in many places, it "
          f"cant be separate")
        w(f";        closly aligned pieces\". Before departing, the head runs {a.merge_mm:g}mm BACK "
          f"along the post's own")
        w(f";        arc and returns to the tip; after landing, it runs {a.merge_mm:g}mm FORWARD "
          f"along the next post's")
        w(f";        arc and returns. The net is welded to the wall over a LENGTH at each end "
          f"instead of at a")
        w(f";        point -- a lap joint, not a butt joint against a bead-wide seam running the "
          f"whole height.")
        w(f";        MEASURED, not asserted: gate 6 read {n_merge} laps off the emitted points, "
          f"every one reaching")
        w(f";        {lap_measured:.4f}mm of arc and landing on a post's toolpath circle to within "
          f"1e-6mm.")
        w(f";        THE CROSSING CHORD IS UNCHANGED. Each lap returns EXACTLY to the tip it left, "
          f"so the strand")
        w(f";        across the air is the same move it always was and the fabric is untouched.")
        w(f";          lap      {merge_flow:>5.2f}x  {merge_mm2:.4f}mm2  per pass, at the body's "
          f"{speed:g}mm/s ({merge_flow*flow:.2f}mm3/s)")
        w(f";                       NOT at --cross-speed: that regime is licensed for AIR, and a "
          f"lap is deposition.")
        w(f";        PACKING, NAMED: the lap is out AND back, so the lip carries 1.0 + 2 x "
          f"{merge_flow:g} = {lap_pack:.2f}x of a bead.")
        w(f";        The nozzle sets the height, so the excess spreads SIDEWAYS: the lip lands "
          f"~{lip_w:.2f}mm wide")
        w(f";        against {bw:g}mm elsewhere. MODELLED. Nothing here has been printed or "
          f"measured.")
        w(f";        AND THAT NARROWS THE BAMBOO MOUTH, which is the cost worth seeing rather than "
          f"absorbing:")
        w(f";        {mouth:.3f} -> {mouth_lap:.3f}mm against a {a.stick_d:.3f}mm stick "
          f"({mouth-a.stick_d:+.3f} -> {mouth_lap-a.stick_d:+.3f}). This file")
        w(f";        DECLINES to claim a fit either way -- see UNMEASURED below. Narrowing toward "
          f"the stick is")
        w(f";        exactly the direction that would flatter us into claiming one. --merge-flow "
          f"tunes it,")
        w(f";        --merge-mm 0 removes the feature and reproduces the old file's motion byte for "
          f"byte.")
        w(f";        COST: {lap_mm/1000:.1f}m of extra path at {speed:g}mm/s = {lap_mins:.0f} min "
          f"of the {mins:.0f} min total.")
    if capped:
        for _nm, _req, _got in capped:
            w(f";        !! CAPPED: {_nm} requested {_req:g}x = {_req*flow:.2f}mm3/s, DELIVERED "
              f"{_got:g}x = {_got*flow:.2f}mm3/s.")
            w(f";           WHY: a bridge runs at the body's {speed:g}mm/s, so flow is mult x bead x "
              f"speed, and {r8cap:g}mm3/s is")
            w(f";           the maintained figure for {a.material} on this machine. {_req:g}x does "
              f"not make a fatter rod, it")
            w(f";           makes a skipping extruder. Slowing the move to buy the volume was "
              f"REJECTED: time in air is")
            w(f";           what makes a {bridge_air:.1f}mm strand sag, and that is the risk this "
              f"part can least afford.")
            w(f";           Rod {2*math.sqrt(_req*bw*lh/math.pi):.3f}mm requested -> "
              f"{2*math.sqrt(_got*bw*lh/math.pi):.3f}mm delivered.")
    if a.bottom_brace_layers > 0:
        w(f";        BRACED BOTTOM — \"add some extras printed support lines so bottom of bucket is "
          f"sturdier\":")
        w(f";           the first {a.bottom_brace_layers} layers above the floor bridge every "
          f"{a.bottom_bridge_every} instead of every {a.bridge_every},")
        w(f";           which is {n_brace} braced layers up to z "
          f"{press + (a.floor_layers + a.bottom_brace_layers - 1)*lh:.2f}mm.")
    if bridge_air > PROVEN_AIR_MM:
        w(f";        !! {bridge_air:.2f}mm is {100*bridge_air/PROVEN_AIR_MM-100:.0f}% LONGER than "
          f"the {PROVEN_AIR_MM:g}mm that has actually held.")
        w(f";        This span is UNPROVEN. It is not a small extrapolation and it is the first "
          f"thing to watch.")
        if pitch_hint:
            w(f";        --pitch {pitch_hint[0]:.2f} gives {pitch_hint[1]} towers and a "
              f"{pitch_hint[2]:.2f}mm span, inside what has held.")
    else:
        w(f";        Inside the {PROVEN_AIR_MM:g}mm that held tonight — which is a LOWER BOUND, "
          f"not a limit.")
    w(f"; FLOOR  {a.floor_layers} cross-latch layer(s) at {a.floor_pitch:g}mm pitch on a "
      f"{r_h:.1f}mm disc — bucket_latch.py's")
    w(f";        lattice, imported and called, so there is one implementation of it in this repo.")
    if a.floor_layers >= 2:
        w(f";        {a.floor_layers} x {lh:g} on the {press:g} press = {floor_h:.2f}mm of floor. "
          f"Plate bending goes as thickness")
        w(f";        CUBED, so against the 2-layer {press+lh:.2f}mm that Oleg called too weak that "
          f"term is ~{(floor_h/(press+lh))**3:.0f}x — DERIVED")
        w(f";        from the layer ladder, not measured on a part, and it is a lattice so the real "
          f"figure is under")
        w(f";        a solid plate of the same thickness.")
        w(f";        Layer 1 lands {land_w1:.2f}mm wide on a {a.floor_pitch:g}mm pitch = "
          f"{land_w1/a.floor_pitch:.2f}x coverage, so what welds to the plate is")
        w(f";        {'a SOLID disc' if land_w1 >= a.floor_pitch else 'a GRID'}"
          f"{'' if land_w1 >= a.floor_pitch else f' leaving {a.floor_pitch-land_w1:.2f}mm of clear air between landings'}.")
        w(f";        SUPPORT, the number that decides the pitch: layers are PERPENDICULAR, so a "
          f"latch rib touches the")
        w(f";        one below only where the rasters cross, every {a.floor_pitch:g}mm, and flies "
          f"{max(0.0, a.floor_pitch-bw):.2f}mm between crossings")
        w(f";        ({100*min(1.0, bw/a.floor_pitch):.0f}% of each rib over material). At 5.0mm "
          f"pitch that was 4.18mm and validate.py REFUSED a")
        w(f";        5-layer floor at 23% unsupported. Stacking a sparse lattice higher does not "
          f"build a floor.")
    w(f"; RIM    on a FLOOR layer the gap crossings are EXTRUDED, so the floor ends as a solid "
      f"{n_tow}-gon tying")
    w(f";        every tower foot together. Each tower's first airborne layer lands on its own "
      f"footprint,")
    w(f";        not on a lattice with {a.floor_pitch:g}mm holes in it.")
    w(f";        IT IS DRAWN ON EVERY FLOOR LAYER, so raising the floor to {a.floor_layers} raised "
      f"the ring to {floor_h:.2f}mm tall:")
    w(f";        {bw*floor_h:.2f}mm2 of hoop section against {bw*(press+lh):.2f}mm2 at 2 layers, "
      f"{floor_h/(press+lh):.1f}x, and hoop section is")
    w(f";        what resists a tower splaying outward at its foot. That is why the rim needed no "
      f"second knob.")
    if a.floor_layers:
        w(f"; GATE 5 the latch disc's outer bead reaches radius {floor_edge:.3f}mm and the bamboo "
          f"channel's bore")
        w(f";        starts at {bore_inner:.3f}mm: {bore_inner-floor_edge:+.3f}mm of clearance. "
          f"NOTHING ELSE CHECKS THIS —")
        w(f";        gate 3 tests crossings against post circles and the floor lattice is not a "
          f"crossing, so a")
        w(f";        part that prints, validates, and then REFUSES THE STICK was a live possibility. "
          f"The disc grows")
        w(f";        as the wrap narrows (the tips move outward); it goes negative below "
          f"--wrap-deg 205.24 here.")
        if bore_inner - floor_edge < 0.15:
            w(f";        !! {bore_inner-floor_edge:.3f}mm is a razor margin. --wrap-deg 220 measures "
              f"+0.269mm AND closes the")
            w(f";        mouth to capture the stick without relying on shrink. 210 is what was "
              f"asked for and what ran.")
    w("; ---------------- WHY NOTHING LIFTS ----------------")
    w(f"; Every post is rotated {stag_deg:.2f} deg from the opening pointing dead inward — inside "
      f"the {win_w:.2f} deg")
    w(f"; window MEASURED by seam_window() (scanned at {SEAM_SCAN_DEG:g} deg, centre {win_c:.2f}), "
      f"which builds the real")
    w(f"; tip-to-tip chords and tests each against both of its posts. All {n_cross} crossings were "
      f"re-checked")
    w(f"; against every post on the emitted points, so there is nothing under the nozzle to plough "
      f"and NOTHING")
    w(f"; TO LIFT OVER; the file is refused if one dips inside a wall.")
    if abs(a.wrap_deg - 360.0) > 1e-9:
        w(f"; HONEST CAVEAT ON THAT GATE: for a CLOSED post it bound hard — 12.75 of 360 deg passed. "
          f"For a C the")
        w(f"; chord starts near the tangent points and the same gate refuses only below --wrap-deg "
          f"{360.0/n_tow:.3f}")
        w(f"; (the ring step), so ~347 of 360 deg pass. It still measures a true property and it "
          f"still runs on")
        w(f"; every crossing, but it no longer DISCRIMINATES and must not be quoted as what makes "
          f"the arc safe.")
    w(f"; CONSEQUENCE: Z in this body only ever goes UP, one {lh:g}mm step per layer. There is no "
      f"lift, no")
    w(f"; drop and no descent anywhere. That is the thing that did not work last time.")
    if abs(a.wrap_deg - 360.0) < 1e-9:
        w(f"; COST, NAMED: the seam is FIXED, so each post carries a vertical scar up its INSIDE "
          f"face. If a post")
        w(f"; splits, look there first.")
    else:
        w(f"; COST, NAMED — AND IT IS TWO SCARS NOW, NOT ONE. The ends do not move, so each post "
          f"carries a")
        w(f"; vertical scar up EACH LIP of its mouth, and a lip is a free end with no material on "
          f"the far side to")
        w(f"; carry load past it. They are not staggered ON PURPOSE: a +-1 deg per-layer stagger "
          f"smears the slot")
        w(f"; by 0.074mm against {mouth-a.stick_d:.3f}mm of modelled slack (a taper, not a seam), "
          f"and changing the")
        w(f"; stagger between layers breaks the one-stroke handoff gate 1 measures at 1e-6. The "
          f"defensible answer")
        w(f"; is Oleg's own: the stick IS the reinforcement of that exact weakness.")
        w(f"; AND A NEW ONE, UNMEASURED: the membrane attaches to BOTH lips, pulling post k's "
          f"leading lip toward")
        w(f"; k+1 and its trailing lip toward k-1 — away from each other. {n_lay} layers of it is a "
          f"continuous")
        w(f"; PRYING-OPEN moment on the feature that has to grip the bamboo, and a stick resists "
          f"closing, not")
        w(f"; opening. Nothing here measures that.")
    w("; ---------------- COOLING ----------------")
    w(f"; {tow_ext:.0f}mm of extrusion per post layer = {lay_s_ext:.2f}s, {lay_s_all:.2f}s wall "
      f"clock with the crossings")
    w(f"; at their own {speed_x:g}mm/s. (Both numbers used to divide EVERYTHING by {speed:g}: at "
      f"--cross-speed {speed_x:g}")
    w(f"; that printed {(tow_ext+tow_trav)/speed:.2f}s here, {(tow_ext+tow_trav)/speed/lay_s_all:.1f}x "
      f"the truth, right beside the figure below.)")
    w(f"; MEASURED: six towers in rotation at 4.50s per layer STOOD; one tower at 0.57s coiled into "
      f"a rope.")
    if lay_s_ext < 4.50:
        w(f"; !! {lay_s_ext:.2f}s IS UNDER THE 4.50s THAT STOOD, and the C-channel is why: an open "
          f"{a.wrap_deg:g}-degree arc")
        w(f"; extrudes {tow_ext:.0f}mm a layer where a closed 8.2mm post extruded 649. A ring "
          f"cannot have a SHORT layer")
        w(f"; — the head still walks the whole circle — but it can have a THIN one, and this is the "
          f"thinnest yet.")
    w("; ---------------- ACCEPTED RISKS. He was told, and said fail is ok. ----------------")
    w(f"; THIS IS THE RISKIEST FIRST LAYER THIS PROJECT HAS ATTEMPTED, and it is three things at "
      f"once:")
    w(f";  1 LESS PRESS. Oleg 2026-08-06: \"let's press on base plate a half less, I don't want to "
      f"have solid base\".")
    w(f";    --h1 {h1_real:g} against the old {press:g}. RAISING h1 ALONE WOULD NOT HAVE DONE IT — "
      f"the rate is derived")
    w(f";    from w1 x h1, so a taller gap at the same width just extrudes more and the base stays "
      f"solid. The")
    w(f";    flow is HELD instead and --w1 comes down with it: "
      f"{w1:g} x {h1_real:g} = {w1*h1_real:.4f}mm2, against")
    w(f";    2.00 x {press:g} = {2.0*press:.4f}. Same material, {w1:g}mm of landed width on a "
      f"{a.floor_pitch:g}mm pitch, so the base")
    w(f";    opens by {a.floor_pitch-w1:.2f}mm per line instead of overlapping into a sheet. "
      f"Weaker plate weld, on purpose.")
    _outer = r_ring + r_t + w1 / 2.0
    w(f";  2 OFF THE BED MESH. Layer 1's outer bead edge reaches radius {_outer:.2f}mm = X "
      f"{cx+_outer:.2f}, and this")
    w(f";    machine's bed_mesh covers only 5..345. That edge has NO mesh compensation, on a bed "
      f"measured to")
    w(f";    vary 0.652mm. Plate margin is {min(bedx, bedy) - (cx+_outer):.2f}mm per side.")
    w(f";  3 A BRIDGE SPAN ~{bridge_air/PROVEN_AIR_MM:.1f}x ANYTHING THAT HAS HELD "
      f"({bridge_air:.2f}mm against {PROVEN_AIR_MM:g}mm).")
    w(f";  All three are combined in one part. Oleg: \"test it on maximum, absolute maximum size. No "
      f"no safety")
    w(f";  gaps. Maybe, like, super small, like, one millimetre safety gap\", and \"fail is ok\".")
    if abs(a.wrap_deg - 360.0) > 1e-9:
        w("; ---------------- UNMEASURED: WHETHER THE C ACTUALLY GRIPS ----------------")
        w(f"; THIS FILE DECLINES TO CLAIM A FIT, because the check cannot measure its own name from "
          f"house data.")
        w(f";   modelled mouth {mouth:.3f}mm vs a {a.stick_d:.3f}mm stick = "
          f"{mouth-a.stick_d:+.3f}mm — "
          f"{'SLIDES IN FREE, no capture' if mouth > a.stick_d else 'captures'}")
        w(f";   at the house 'printed = model - {SHRINK_METAL:g}' the mouth becomes "
          f"{mouth_shrunk:.3f}mm = {mouth_shrunk-a.stick_d:+.3f}mm")
        if a.merge_mm > 0:
            w(f";   AND THE MERGE LAP MOVES IT AGAIN: a {lap_pack:.2f}x lip bead spreading sideways "
              f"reads {mouth_lap:.3f}mm = {mouth_lap-a.stick_d:+.3f}mm.")
            w(f";   THAT IS THE DIRECTION THAT FLATTERS US -- a mouth that was too wide to capture "
              f"is now modelled")
            w(f";   narrower than the stick -- so it is the one to distrust hardest. It rests on a "
              f"bead-spreading")
            w(f";   model with NO measurement behind it, stacked on the shrink constant above that "
              f"is already cited")
            w(f";   outside its conditions. Two unmeasured models pointing the same way is not "
              f"evidence.")
        w(f"; SO CAPTURE DEPENDS WHOLLY ON A SHRINK CONSTANT THAT IS CITED OUTSIDE ITS CONDITIONS. "
          f"That {SHRINK_METAL:g} was")
        w(f"; calibrated on a ~6mm bore around a METAL shaft. Reused for 6.35mm BAMBOO it was "
          f"0.45mm too tight and")
        w(f"; condemned about 21 printed parts (guides/fit-and-assembly-empirics.md). Three K2 "
          f"coupon rounds on THIS")
        w(f"; 1/8in stick landed near 0.6mm/side for a socket in mass — at which this bore prints "
          f"~2.2mm and the")
        w(f"; stick does not enter at all. The counter is in the same guide: free single-bead loops "
          f"bulge LESS than")
        w(f"; bores-in-mass and depth LOOSENS, and this is a free single-bead loop {a.height:g}mm "
          f"deep. The true value")
        w(f"; is bracketed 0.25..1.725 and NO house measurement exists in this geometry class. The "
          f"answer is a")
        w(f"; graded coupon (4-6 posts, ~30mm tall, minutes), not a constant. Also: Oleg's bamboo "
          f"measures UNDER")
        w(f"; nominal — his 1/4in rods are 5.8-6.2 against 6.35 — so {a.stick_d:g} is a catalogue "
          f"number, not a calliper.")
    w("; ---------------- WATCH ----------------")
    # THE FLOOR'S DURATION IS MEASURED OFF THE EMITTED PATH, not the "2 minutes" that was typed when
    # the floor was 2 layers at 5mm. A watch instruction with a stale clock tells the operator to
    # stop looking before the thing it names has finished printing.
    w(f"; FIRST {floor_mins:.0f} MINUTES ({a.floor_layers} floor layers, z up to "
      f"{floor_h:.2f}): the latch and the rim. If the rim {n_tow}-gon is not stuck flat and "
      f"glossy, stop —")
    w(f";   it is the only thing holding {n_tow} x {a.height:g}mm of lever.")
    w(f"; THEN THE FIRST BRIDGE LAYER (z {press + (min(bridges) if bridges else 0)*lh:.2f}mm): "
      f"strands that SAG instead of pulling taut mean")
    w(f";   the {bridge_air:.2f}mm span is past this filament — re-run with a smaller --pitch"
      + (f" (try {pitch_hint[0]:.2f})." if pitch_hint else "."))
    w(f";   STOP AND LOOK AT THAT LAYER. It is the one number in this part that is outside its own "
      f"evidence."
      if bridge_air > PROVEN_AIR_MM else
      f";   The span is inside what has held, so a sag here would be new information.")
    w(f"; THROUGHOUT: strings across the gaps are EXPECTED. There is no retraction in this project "
      f"and the")
    w(f";   head crosses open air {n_tow} times a layer. The coupon printed the same web and stood.")
    w(f"; A LEANING TOWER IS A COOLING PROBLEM FIRST — --fan raises the body fan above the "
      f"{100*machine.FAN_MAX[a.material]:.0f}% PLA")
    w(f";   ceiling without touching layer 1.")
    w("; ------------------------------------------")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {n_lay}")
    w("; HEADER_BLOCK_END")
    w("M82")
    # BED FIRST AND NON-BLOCKING, so the plate climbs while the nozzle heats and the machine homes.
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    # ON THE K2, WAIT FOR THE FULL BED TARGET -- it provably reaches it. Every other machine gets
    # machine.bed_start(), because the K1C pins at ~87-91 with its heater at full power and a
    # blocking M190 at a target it cannot cross is an infinite stall, not a rule.
    _floor = bed if a.printer == "k2plus" else machine.bed_start(a.material, bed)
    w(f"M190 S{_floor:.0f}   ; BLOCKING: do not start below this")
    # RE-RAISE THE TARGET: M190 SETS the target as well as waiting on it.
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    # THE NOZZLE PROBES AT FULL PRINT TEMPERATURE (R7). A cold nozzle is SHORTER, so Z zero records
    # high and the hot tip then grows down into the plate, turning a 0.10 gap into ~0.054.
    w("G28")
    # ALWAYS EMITTED, INCLUDING THE ZERO. SET_GCODE_OFFSET is machine state that survives a job
    # -- the K2's own start_print macro zeroes it for exactly this reason -- so a file that only
    # wrote it when non-zero would inherit whatever the previous print or a hand command left
    # behind. On a 10-hour part that is not a variable worth carrying.
    w(f"SET_GCODE_OFFSET Z={a.zoff:.3f}"
      + ("                 ; the machine's own zero, uncorrected" if abs(a.zoff) < 1e-9 else
         f"            ; nozzle {abs(a.zoff):.3f}mm CLOSER than the machine's zero -- Z zero\n"
         f";                                       homes HIGH on this machine, MEASURED 2026-08-06"))
    _fan_l1 = int(round(machine.fan_first_layer(a.material) * 255))
    w(f"M106 S{_fan_l1}                              ; layer 1 gets no fan — the weld to the plate "
      f"is the job" if _fan_l1 == 0 else
      f"M106 S{_fan_l1}                              ; {a.material} needs cooling from layer 1")
    # CHAMBER/SIDE FANS SET EXPLICITLY TO ZERO, not left unmentioned. On the K2 these are output
    # pins that HOLD their last value across jobs, so "never mentioned" means "whatever the previous
    # print left them at" -- and a chamber draft is the worst possible thing to point at a ring of
    # slender cantilevers.
    for _ln in machine.aux_fans(a.printer, 0.0):
        w(f"{_ln}                  ; no chamber draft on a ring of cantilevers")
    w("G92 E0")

    sx0, sy0 = layers[0]["pts"][0]
    # ONE SHARED PRIME, machine.prime(). This was six hand-written lines whose second one extruded
    # 12mm of filament (28.9 mm3) with the head STANDING STILL at the 0.10 press gap, in a corner
    # the comment above them ASSERTED was clear rather than computing it. That is the clump Oleg
    # photographed on 2026-08-06, and validate.py R10 now refuses the shape on the emitted file.
    # THE FOOTPRINT HANDED OVER IS THE RING'S OUTERMOST MATERIAL, NOT A BOUNDING BOX: the bbox of a
    # 341.5mm circle covers this entire plate and would leave nowhere to prime, while the circle's
    # own corners are wide open. Metering comes from e_mm_l1, layer 1's own rate, so the prime
    # physically cannot be a different bead from the part's first layer -- the old E12/E20 pair ran
    # 2.43x it.
    machine.prime(w, printer=a.printer, z=press, rate=e_mm_l1, feed=f_l1,
                  travel_feed=round(machine.MACHINE_MAX_SPEED * 60),
                  avoid=(("circle", cx, cy, r_ring + a.tower_d / 2.0),), near=(sx0, sy0))
    w("; BODY_START")

    E = 0.0
    # THE ONE TRAVEL IN THE BODY, and it happens before any of the part exists: flat at the press
    # height, across bare plate, from the prime to the first line. No lift and no drop -- there is
    # nothing here to lift over. It is safe flat BECAUSE the prime now stands 0.10 tall instead of
    # the 2.0 a lifted purge left; it also starts on the runway prime() reserved beyond the last
    # row, so it does not begin by dragging along the prime itself.
    w(f"G0 F{f} X{sx0:.3f} Y{sy0:.3f} ; HOP prime -> first line, over bare plate")
    fan_on = False
    for li, Lay in enumerate(layers):
        z = press + li * lh
        w(f"; ---- layer {li+1} of {n_lay}  z {z:.3f}  ({Lay['label']})")
        w(f"G1 F{f_l1 if li == 0 else f} Z{z:.3f}")   # STANDALONE Z -- this is R2's layer ladder,
        # and it is also where layer 1's slower feedrate is set: F is sticky, so one word here
        # carries the whole layer.
        if li == 1 and not fan_on:
            _src = (f"machine.FAN_MAX['{a.material}']" if a.fan is None
                    else f"--fan {a.fan:g} on the command line, OVERRIDING "
                         f"machine.FAN_MAX['{a.material}']={machine.FAN_MAX[a.material]:g}")
            w(f"M106 S{int(round(fan*255))}     ; {fan*100:.0f}% — {_src}")
            fan_on = True
        ppx, ppy = Lay["pts"][0]
        for j, (x, y) in enumerate(Lay["pts"][1:]):
            kind = Lay["kind"][j]
            seg = math.hypot(x - ppx, y - ppy)
            if seg < 1e-9:
                continue
            if kind == "T":
                # FLAT, AT THE LAYER'S OWN Z, NO LIFT. Licensed by geometry, not by a tag: the
                # chord provably clears both tower walls (check_paths gate 3), so there is no
                # material under it. F is at the north star, which is also what keeps this move
                # under validate.py's ploughing threshold rather than at it.
                if a.cross_flow > 0:
                    # THERE IS NO RETRACTION IN THIS PROJECT, so this move was never dry. It oozed,
                    # and the web in the printed part IS that ooze. Metering it at a stated fraction
                    # of the body's own rate turns an uncontrolled leak into a strand we chose.
                    E += seg * e_mm * a.cross_flow
                    w(f"G1 F{f_l1 if li == 0 else f_x} X{x:.3f} Y{y:.3f} E{E:.5f} ; THIN CROSS "
                      f"{a.cross_flow*100:.0f}% "
                      f"-- deliberate strand, not ooze (clears both tower walls)")
                else:
                    w(f"G0 F{f} X{x:.3f} Y{y:.3f} ; HOP flat across open air, no lift (clears both "
                      f"tower walls)")
            elif kind == "M":
                # THE LAP RUNS AT THE BODY SPEED, NOT THE CROSSING SPEED, and that is the north
                # star doing its job rather than being worked around. --cross-speed is licensed for
                # AIR: "nothing is being deposited onto" a strand flung between two towers, so it
                # has no adhesion to get wrong. This move IS deposition, onto the wall bead, so it
                # belongs to the 50 mm/s regime that exists for exactly that. F is written on every
                # lap move because F is sticky and a lap follows a crossing at f_x on one side and
                # a body move at f on the other.
                #
                # TAGGED '; LINK', WHICH IS A DECLARATION AND NOT A LOOPHOLE. validate.py exempts
                # LINK moves from R4 constant flow because they deliberately meter DOWN, and it
                # counts and reports every one so an exemption cannot hide a growing problem. The
                # tag deliberately avoids the words BRIDGE/POCKET/CORNER/THIN CROSS: each of those
                # names a different declared regime with its own gate, and borrowing one would put
                # these moves in front of a check built for something else.
                E += seg * e_mm * merge_flow
                w(f"G1 F{f_l1 if li == 0 else f} X{x:.3f} Y{y:.3f} E{E:.5f} ; LINK MERGE "
                  f"{merge_flow*100:.0f}% -- net lapped onto the post, {a.merge_mm:g}mm of arc")
            else:
                # LAYER 1 IS METERED SEPARATELY AND ON PURPOSE.
                # Oleg, 2026-08-05, after the first ring printed: "first layer need to be full flow
                # ( a lot of fillament glued to base max width". The body's e_mm carries the SAME
                # volume into the 0.10 press gap, which lands about 1.97mm wide -- wide, but it is
                # the body's flow flattened, not more of it. He is asking for more of it. So layer 1
                # gets its own rate, derived from a TARGET LANDED WIDTH rather than from a
                # multiplier nobody can check: e = w1 * press / A_FIL. The width is the adhesion.
                # A BRIDGE CARRIES ITS OWN FLOW, and that is the whole of Oleg's line-feature ask:
                # "the features are all bridges", "Just different extrusion volume". Solid line,
                # accent band and top rim are THIS one move at 2x / 4x / 8x-capped, never a second
                # pass over the same air and never a fatter post.
                _bm = Lay["mult"] if kind == "B" else 1.0
                E += seg * (e_mm_l1 if li == 0 else e_mm * _bm)
                # F IS STICKY, so a body move following a crossing must restore the body feedrate or
                # the whole tower would silently print at the crossing speed.
                if a.cross_flow > 0 and speed_x != speed and li != 0:
                    w(f"G1 F{f}")
                if kind == "B":
                    _a2 = _bm * bw * lh
                    w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f} ; BRIDGE {_bm:g}x {_a2:.4f}mm2 rod "
                      f"{2*math.sqrt(_a2/math.pi):.3f}mm, {seg:.2f}mm tip to tip, "
                      f"{bridge_air:.2f}mm unsupported air")
                else:
                    w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f}")
            ppx, ppy = x, y

    # THE MATERIAL FIGURE IS THE ACCUMULATOR, NOT A SECOND MODEL OF IT. E is the body total, after
    # the G92 E0 that follows the prime; the prime line itself is 20mm of filament on top.
    vol_cm3 = E * A_FIL / 1000.0

    w("M107")
    w("M104 S0")
    w("M140 S0")
    # THE END-OF-PRINT RETREAT IS BOUNDED BY THE MACHINE, not by a constant. At --height 359 the
    # old `top_z + 20` emitted G0 Z378.90 against an axis_maximum of 360: Klipper refuses a move
    # out of range, so a six-hour print would have aborted on its own last line. See machine.Z_MAX.
    _zr2, _zcap = machine.z_retreat(a.printer, top_z)
    w(f"G0 F{f} Z{_zr2:.2f}"
      + (f"   ; retreat SHORTENED from {top_z+20:.2f} to the {machine.Z_MAX[a.printer]:g} "
         f"axis_maximum -- {_zr2-top_z:.2f}mm of clearance over the part" if _zcap else ""))
    w("G0 F3000 X10 Y10")

    os.makedirs(a.out, exist_ok=True)
    # THE FLOOR IS IN THE FILENAME, and it is here because leaving it out cost the printed record.
    # Regenerating with a stronger base on 2026-08-05 silently OVERWROTE the gcode of the part that
    # had already printed: same dia, same height, same tower count, same bridge interval, entirely
    # different floor. Two different parts cannot share a name.
    # --cross-flow IS IN THE NAME FOR THE SAME REASON THE FLOOR IS. A run at 0.25 and a run at 0
    # are the same geometry carrying different material: 9.59 cm3 against 7.40, and 44.5m of the
    # path is a strand in one and open air in the other. Suffix only when it is on, so every
    # filename written before --cross-flow existed still names the same file.
    # THE WRAP AND THE FLOW SCHEDULE ARE IN THE NAME FOR EXACTLY THAT REASON. A closed post and a
    # C-channel at the same diameter and count are different parts, and so are two runs whose
    # bridges carry 1x and 8x. Suffixes appear only when the feature is on, so every filename
    # written before these flags existed still names the same file.
    xf = f"_x{a.cross_flow*100:g}" if a.cross_flow > 0 else ""
    wf = "" if abs(a.wrap_deg - 360.0) < 1e-9 else f"_w{a.wrap_deg:g}s{a.stick_d:g}"
    mf = ("" if set(bridges.values()) == {1.0} else
          "_m" + "-".join(f"{m:g}" for m in sorted(set(bridges.values()))))
    bb = f"_bb{a.bottom_brace_layers}x{a.bottom_bridge_every}" if a.bottom_brace_layers > 0 else ""
    # THE LAP IS IN THE NAME FOR THE SAME REASON THE FLOOR AND THE CROSS FLOW ARE: a run with the
    # net welded into the wall and a run with it touching are the same geometry carrying different
    # material, and two different parts cannot share a name. Suffix only when it is on, so every
    # filename written before --merge-mm existed still names the same file.
    jf = f"_j{a.merge_mm:g}" if a.merge_mm > 0 else ""
    fn = os.path.join(a.out, f"bucket_towers_{a.printer}_{a.material}_d{a.dia:g}_h{a.height:g}_"
                             f"n{n_tow}t{a.tower_d:g}{wf}_b{a.bridge_every}{bb}{mf}_"
                             f"f{a.floor_layers}x{a.floor_pitch:g}{xf}{jf}.gcode")
    open(fn, "w").write("\n".join(L) + "\n")

    print(fn)
    print(f"  {n_tow} towers of {a.tower_d:g}mm on a {a.dia:g}mm circle "
          f"({circ_ring/n_tow:.2f}mm arc spacing from --pitch {a.pitch:g} as a MAXIMUM), "
          f"{a.height:g}mm tall")
    print(f"  {n_lay} layers ({a.floor_layers} latch + {n_lay-a.floor_layers} tower), top z "
          f"{top_z:.2f}mm, {len(bridges)} bridge layers at z "
          f"{', '.join(f'{press+li*lh:.1f}' for li in sorted(bridges)[:4])}"
          f"{' ...' if len(bridges) > 4 else ''}")
    print(f"  floor {a.floor_layers} latch layers at {a.floor_pitch:g}mm pitch = {floor_h:.2f}mm "
          f"thick; layer 1 lands {land_w1:.2f}mm on {a.floor_pitch:g}mm "
          f"({land_w1/a.floor_pitch:.2f}x, {'SOLID' if land_w1 >= a.floor_pitch else 'grid'}); "
          f"ribs cross every {a.floor_pitch:g}mm and bridge {max(0.0, a.floor_pitch-bw):.2f}mm")
    print(f"  bead {bw:g} x {lh:g} at {speed:g} mm/s -> {flow:.2f} mm3/s "
          f"({100*flow/r8cap:.1f}% of the {r8cap:g} figure, DECLARED)")
    if abs(a.wrap_deg - 360.0) > 1e-9:
        print(f"  C-CHANNEL: bore {2*bore_r:.3f}mm modelled (stick {a.stick_d:g} + allow "
              f"{a.bore_allow:g}), OD {a.tower_d:.3f}mm, wrap {a.wrap_deg:g} deg, "
              f"{narc} segs of {a.wrap_deg/narc:.2f} deg")
        print(f"     mouth {mouth:.3f}mm modelled ({mouth-a.stick_d:+.3f} vs the stick), "
              f"{mouth_shrunk:.3f}mm at the house model-{SHRINK_METAL:g} shrink "
              f"({mouth_shrunk-a.stick_d:+.3f}) — DECLINED, not claimed: no house measurement "
              f"exists in this geometry class")
        if a.floor_layers:
            print(f"     gate 5 latch floor vs bamboo channel: bead edge {floor_edge:.3f} vs bore "
                  f"at {bore_inner:.3f} = {bore_inner-floor_edge:+.3f}mm clear")
    print(f"  bridge flow: " + ", ".join(
        f"{m:g}x {m*bw*lh:.4f}mm2 rod {2*math.sqrt(m*bw*lh/math.pi):.3f}mm on "
        f"{sum(1 for v in bridges.values() if v == m)} layers"
        for m in sorted(set(bridges.values()))))
    print(f"     fabric UNCHANGED at {a.cross_flow:g}x = {a.cross_flow*bw*lh:.4f}mm2, rod "
          f"{2*math.sqrt(a.cross_flow*bw*lh/math.pi):.3f}mm > the {lh:g} layer pitch, so it fuses "
          f"into a membrane")
    for _nm, _req, _got in capped:
        print(f"  !! CAPPED {_nm}: requested {_req:g}x = {_req*flow:.2f}mm3/s, delivered {_got:g}x "
              f"= {_got*flow:.2f}mm3/s — {r8cap:g}mm3/s is the maintained figure for {a.material}")
    print(f"  stagger {stag_deg:.2f} deg, inside a {win_w:.2f} deg window measured at "
          f"{SEAM_SCAN_DEG:g} deg steps (centre {win_c:.2f})")
    print(f"  {n_cross} gap crossings, every one re-checked against every post: none passes "
          f"inside a wall, so none lifts")
    if a.merge_mm > 0:
        # AGAINST THE AIRBORNE CROSSINGS, NOT n_cross. n_cross counts every T/B/R move and a floor
        # rim is SUBDIVIDED, so dividing by it read "0 laps per crossing" on a file with two laps
        # on every one of them -- a report about the artifact quoting the wrong denominator.
        _n_air = sum(1 for Lz in layers for k in Lz["kind"] if k in ("T", "B"))
        print(f"  MERGE: {n_merge} laps on {_n_air} airborne crossings "
              f"({n_merge/max(1,_n_air):.1f} each — both ends), every one measured at "
              f"{lap_measured:.4f}mm of arc ON the post's own circle to 1e-6")
        print(f"     {merge_flow:g}x = {merge_mm2:.4f}mm2 per pass at the body {speed:g}mm/s, out "
              f"and back, so the lip carries {lap_pack:.2f}x of a bead -> ~{lip_w:.2f}mm wide "
              f"(MODELLED)")
        print(f"     modelled mouth {mouth:.3f} -> {mouth_lap:.3f}mm vs the {a.stick_d:.3f}mm stick "
              f"({mouth-a.stick_d:+.3f} -> {mouth_lap-a.stick_d:+.3f}) — DECLINED, not claimed")
        print(f"     costs {lap_mm/1000:.1f}m and {lap_mins:.0f} min; the crossing chord itself is "
              f"unchanged, so the fabric is untouched")
    else:
        print(f"  MERGE: OFF (--merge-mm 0) — the net meets the wall at a single tangent point at "
              f"each end, which is what Oleg objected to on 2026-08-06")
    print(f"  bridge span {gap_chord:.2f}mm tip to tip, {bridge_air:.2f}mm of UNSUPPORTED AIR "
          f"measured on the chord")
    if bridge_air > PROVEN_AIR_MM:
        print(f"  !! that span is {100*bridge_air/PROVEN_AIR_MM-100:.0f}% LONGER than the "
              f"{PROVEN_AIR_MM:g}mm that has actually held tonight — UNPROVEN, and the first thing "
              f"to watch")
        if pitch_hint:
            print(f"     --pitch {pitch_hint[0]:.2f} -> {pitch_hint[1]} towers, {pitch_hint[2]:.2f}"
                  f"mm span, inside what has held")
    else:
        print(f"     inside the {PROVEN_AIR_MM:g}mm that held tonight (a lower bound, not a limit)")
    print(f"  cooling: {tow_ext:.0f}mm extruded per tower layer = {lay_s_ext:.2f}s, "
          f"{lay_s_all:.2f}s wall clock with the crossings (one tower gave 0.57s and roped)")
    print(f"  {n_moves} moves, {ext_mm/1000:.1f}m extruded ({floor_mm/1000:.1f}m of it floor"
          + (f", {cross_mm/1000:.1f}m of it flat crossings at {a.cross_flow*100:g}% flow"
             if cross_mm else "")
          + f") + {dry_mm/1000:.1f}m of "
          + ("flat crossings" if a.cross_flow <= 0 else "dry travel inside the body")
          + f", {vol_cm3:.2f} cm3 of PLA (the file's own E, +0.05 for the prime line)")
    print(f"  est. {mins:.0f} min of motion at {speed:g} mm/s (no accel, no heat-up)")
    print(f"  ONE stroke: {len(layers)} layers, each starting exactly where the last ended, and Z "
          f"never descends (both checked, not claimed)")
    print("\n  WHAT THIS FILE DOES NOT KNOW")
    print("   - whether a ring of towers holds together as a BUCKET. Nothing here has printed.")
    print(f"   - whether a {bridge_air:.2f}mm bridge lands or sags. {PROVEN_AIR_MM:g}mm did, on a "
          f"row of six towers, which is a")
    print("     different part with different air around it, and that figure is a lower bound "
          "rather than a limit.")
    # n_tow, NOT 13. This line was typed when --pitch 25 gave 13 towers and it kept saying 13 while
    # the part on the plate had 16 gaps in its wall — a constant in a report about the artifact.
    print(f"   - anything about what it can CARRY. The wall has {n_tow} gaps in it and the floor is "
          f"a")
    print(f"     {floor_h:.2f}mm lattice: this is a bucket in SHAPE. It is not a vessel and it will "
          f"not hold liquid.")
    print(f"   - whether {floor_h:.2f}mm of floor is what he means by 'way stronger'. The thickness "
          f"and the rim's hoop")
    print("     section are derived from the layer ladder; nothing about the new base has been "
          "printed or handled.")
    if a.merge_mm > 0:
        print(f"   - whether the lap actually WELDS. It puts {lap_pack:.2f}x of bead on the lips "
              f"and the geometry is")
        print(f"     measured, but fusion is a thermal question and nothing here has printed. It "
              f"also loads the two")
        print(f"     lips -- already the weakest feature, already being pried apart by the "
              f"membrane -- with more")
        print(f"     material and a second nozzle pass per layer.")
    print("   - how much it strings. There is no retraction in this project and the head crosses "
          "open air")
    print(f"     {n_tow} times on {n_lay-a.floor_layers-len(bridges)} layers. The coupon's web was "
          f"real and unmeasured.")
    print("   - anything about another machine. 0.82 x 0.24 is this printer's own slicer geometry.")


if __name__ == "__main__":
    main()
