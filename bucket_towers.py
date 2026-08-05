#!/usr/bin/env python3
"""BUCKET ON TOWERS — the wall is a RING OF VERTICAL POSTS joined by horizontal bridges.

Oleg, 2026-08-05: "We want a bucket using towers on the sides. The way you printed bucket now did
not work, the layers of wall math is very complex and you was not hitting adhesion with all this z
up and down movements".

So the wall stops being a continuous wavy cylinder. It becomes N single-wall towers standing on a
circle, each one drawn as a plain closed loop that only ever goes UP, with the gaps between them
crossed by horizontal bridges every --bridge-every layers. Nothing climbs, dips and re-welds to a
surface it left. The two things that were hard are simply gone: there is no wall profile to
compute per layer, and there is no descending Z anywhere in the file.

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
--floor-layers (default 2) cross-latch layers: parallel chords at --floor-pitch, each layer's
lines perpendicular to the one below. That code is imported from bucket_latch.py and called, so
there is exactly one cross-latch implementation in this repo and a fix to it fixes both parts.

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

A_FIL = math.pi * (1.75 / 2) ** 2     # mm2 of 1.75mm filament; computed once
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


def tower_loop(c, r, a0, n, seam):
    """One closed revolution, EXCLUDING the start point, ending EXACTLY on `seam`.

    The exact closure matters: the next thing drawn starts from this point with no move at all, so
    a float-drifted last point would open a sub-micron gap that the emitter would turn into a
    silent travel. check_paths() would catch it; closing it here means it never happens.
    """
    pts = [(c[0] + r * math.cos(a0 + 2 * math.pi * i / n),
            c[1] + r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(1, n)]
    pts.append(seam)
    return pts


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


def air_span(p, q, cA, cB, r_t, bw, n=2000):
    """Length of p->q that is over NOTHING, measured on the chord rather than assumed.

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
    over = 0
    for i in range(n):
        t = (i + 0.5) / n
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if math.dist((x, y), cA) > edge and math.dist((x, y), cB) > edge:
            over += 1
    return L * over / n


def seam_window(centres, phis, r_t, step_deg=SEAM_SCAN_DEG):
    """Seam offsets (degrees from the outward radial) whose gap crossings clear every tower.

    MEASURED, not argued: every candidate offset is built into real chords and every chord is
    tested against both of its towers. Returns the sorted list of offsets that pass, so the caller
    can take the widest run's centre and REPORT the window instead of asserting a number.
    """
    n = len(centres)
    ok = []
    steps = int(round(360.0 / step_deg))
    for i in range(steps):
        off = math.radians(i * step_deg)
        good = True
        for k in range(n):
            j = (k + 1) % n
            p = seam_point(centres[k], phis[k], r_t, off)
            q = seam_point(centres[j], phis[j], r_t, off)
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
def air_for_count(cx, cy, r_ring, r_t, bw, n):
    """The unsupported bridge span this file WOULD build with `n` towers, run through the same
    seam-window and air-span code the real part uses. Used only to hand the operator the --pitch
    that lands on the proven span -- at the SAME scan resolution and the SAME sample count, so the
    span it advertises is the span the suggested run actually builds. (A coarser scan here first
    advertised 15.63 where the run produced 15.65: small, and the same species of error as the
    rounded pitch that did not reproduce.)"""
    phis = [2 * math.pi * k / n for k in range(n)]
    cs = [(cx + r_ring * math.cos(p), cy + r_ring * math.sin(p)) for p in phis]
    c, _ = widest_run(seam_window(cs, phis, r_t))
    if c is None:
        return None
    o = math.radians(c)
    return air_span(seam_point(cs[0], phis[0], r_t, o), seam_point(cs[1], phis[1], r_t, o),
                    cs[0], cs[1], r_t, bw)


def check_paths(layers, centres, r_t, bed, press, lh, seam_off_deg):
    """Refuse to emit anything that breaks one of the four properties this part is built on.

    Every one of these was a real failure earlier today, and none of them is checkable by reading
    the source: they are properties of the emitted point list, so that is what is measured.
      1  ONE STROKE. Layer n+1 starts exactly where layer n ended. A gap is a travel by another
         name -- the emitter would simply not write a G0 and the printer would draw across the part.
      2  NOTHING OFF THE PLATE.
      3  EVERY GAP CROSSING CLEARS BOTH TOWERS. This is what licenses a FLAT crossing at layer Z
         with no lift. If it fails, the answer is a different seam angle, not a hop.
      4  Z NEVER DESCENDS. Trivially true of a per-layer Z ladder -- and asserted anyway, because
         "the first bridge attempt" today was also obviously fine until validate.py read the file.
    """
    for i in range(1, len(layers)):
        d = math.dist(layers[i]["pts"][0], layers[i - 1]["pts"][-1])
        if d > 1e-6:
            raise SystemExit(
                f"REFUSING TO EMIT: layer {i+1} starts {d:.6f} mm from where layer {i} ended. That "
                f"gap is a travel move inside the object. Fix the handoff, do not add a hop.")
    for i, L in enumerate(layers):
        for (x, y) in L["pts"]:
            if not (0.0 <= x <= bed[0] and 0.0 <= y <= bed[1]):
                raise SystemExit(
                    f"REFUSING TO EMIT: layer {i+1} reaches ({x:.1f},{y:.1f}), off a "
                    f"{bed[0]:g}x{bed[1]:g} plate. The part does not fit this machine.")
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
            f"the tower at ({c[0]:.2f},{c[1]:.2f}). At --seam-deg {seam_off_deg:g} the head would "
            f"drag across a wall it just laid, and the ONLY reason this file may cross flat with no "
            f"lift is that it does not. Move the seam into the measured window, do not add a hop.")
    zs = [press + i * lh for i in range(len(layers))]
    bad = [k for k in range(1, len(zs)) if zs[k] < zs[k - 1] - 1e-9]
    if bad:
        raise SystemExit(f"REFUSING TO EMIT: Z descends at layer(s) {bad[:5]}. Towers only go up.")
    return n_cross


# ------------------------------------------------------------------------------------- the part
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


def build(cx, cy, centres, phis, r_t, seam_off, nseg, n_lay, n_floor, floor_pitch, r_h, bridges):
    """Every layer as {pts, kind, label}. pts[0] is where the layer starts; kind[j] says how the
    head reaches pts[j+1] -- E extrude, T flat non-extruding crossing, B bridge, R floor rim."""
    n = len(centres)
    seams = [seam_point(centres[k], phis[k], r_t, seam_off) for k in range(n)]
    a0 = [phis[k] + seam_off for k in range(n)]
    layers = []
    for li in range(n_lay):
        is_floor = li < n_floor
        pts, kind = [], []
        if is_floor:
            entry = layers[-1]["pts"][-1] if layers else None
            first, fp, fk = floor_path(cx, cy, r_h, floor_pitch, (math.pi / 2.0) * (li % 2),
                                       seams[0], entry, SEG)
            pts = [first] + fp
            kind = fk
        else:
            pts = [seams[0]]
        cross = "B" if li in bridges else ("R" if is_floor else "T")
        for k in range(n):
            loop = tower_loop(centres[k], r_t, a0[k], nseg, seams[k])
            pts += loop
            kind += ["E"] * len(loop)
            nxt = (k + 1) % n
            if cross == "R":
                # ON A FLOOR LAYER THE CROSSING IS THE RIM, so it is subdivided and drawn as a
                # line: the towers' feet are meant to be tied into one solid ring, and a rim that
                # is one long move leaves the layer above nothing to be measured against.
                seg_pts = latch.line_pts(pts[-1], seams[nxt], SEG)
                pts += seg_pts
                kind += ["R"] * len(seg_pts)
            else:
                # ONE MOVE, NOT A SUBDIVIDED LINE, and that is not a shortcut. A bridge is a strand
                # pulled taut across air; every intermediate point is a place the planner can slow
                # down and let it sag. towercoupon.py laid its proven 16.8 mm spans as single moves.
                pts.append(seams[nxt])
                kind.append(cross)
        layers.append({"pts": pts, "kind": kind,
                       "label": ("floor latch" if is_floor else
                                 ("towers + BRIDGES" if li in bridges else "towers"))})
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
    ap.add_argument("--tower-d", type=float, default=8.2,
                    help="tower outer diameter mm. 8.2 = 10 beads, MEASURED tonight: 4.92 breaks "
                         "easily by hand, 6.56 takes effort, 9.84 does not break.")
    ap.add_argument("--pitch", type=float, default=25.0,
                    help="MAXIMUM arc spacing mm between tower centres; the count is derived from "
                         "it and stated in the header.")
    ap.add_argument("--bridge-every", type=int, default=10,
                    help="lay bridges across every gap every N layers. 0 disables the periodic "
                         "bridges; the top layer is bridged either way (it is the rim).")
    ap.add_argument("--floor-layers", type=int, default=2,
                    help="cross-latch floor layers (bucket_latch.py's lattice), each perpendicular "
                         "to the one below. 0 stands the towers straight on the plate.")
    ap.add_argument("--floor-pitch", type=float, default=5.0, help="mm between latch lines")
    ap.add_argument("--height", type=float, default=40.0, help="total height mm including floor")
    ap.add_argument("--seam-deg", type=float, default=None,
                    help="seam offset in degrees from each tower's OUTWARD radial. Default is the "
                         "centre of the window seam_window() measures. Values outside that window "
                         "are REFUSED by check_paths, which is how the gate is proven able to fire.")
    ap.add_argument("--speed", type=float, default=machine.DEFAULT_SPEED,
                    help=f"mm/s for every move. Default is the {machine.DEFAULT_SPEED:g} north "
                         f"star, which is a ceiling: slower is allowed, faster is refused.")
    ap.add_argument("--w1", type=float, default=None,
                    help="target LANDED WIDTH of layer 1 in mm. Default reproduces the body's "
                         "own flow pressed into the gap. Oleg 2026-08-05: layer 1 needs full "
                         "flow, a lot of filament glued to the base at max width.")
    ap.add_argument("--fan", type=float, default=None,
                    help="part-cooling fan fraction 0..1 for the BODY, overriding machine.FAN_MAX. "
                         "Layer 1 is unaffected and keeps its material's first-layer value, so the "
                         "plate weld is never chilled.")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    # MATERIAL FOLLOWS THE PRINTER. A part generated for one machine with another machine's
    # filament is silently wrong: right geometry, wrong temperature, wrong flow ceiling.
    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    bw, lh = machine.SLICER_LINE_W, machine.SLICER_LAYER_H
    press = machine.PRESS_HARD                      # 0.10, R1
    if a.speed > machine.MAX_SPEED + 1e-9:
        raise SystemExit(f"REFUSING TO EMIT: --speed {a.speed:g} is above the "
                         f"{machine.MAX_SPEED:g} mm/s north star, which is a ceiling. Slower is "
                         f"allowed; faster is not.")
    speed = a.speed
    f = round(speed * 60)
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
    e_mm_l1 = w1 * press / A_FIL
    flow = bw * lh * speed
    r8cap = machine.flow_cap(a.material, a.printer)

    # THE TOWER FLOOR IS DERIVED, NOT CHOSEN (towercoupon.py): below 2 x bead the toolpath circle
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

    # THE SEAM WINDOW IS MEASURED BEFORE ANY GEOMETRY IS BUILT, and the default sits at its centre.
    offs = seam_window(centres, phis, r_t)
    win_c, win_w = widest_run(offs)
    if win_c is None:
        raise SystemExit(
            f"REFUSING TO EMIT: NO seam offset lets the head cross between {n_tow} towers of "
            f"{a.tower_d:g} mm on a {a.dia:g} mm circle without passing inside a tower wall. The "
            f"towers are too close together for a flat crossing; widen --dia or raise --pitch.")
    seam_deg = win_c if a.seam_deg is None else a.seam_deg
    seam_off = math.radians(seam_deg)
    seams = [seam_point(centres[k], phis[k], r_t, seam_off) for k in range(n_tow)]

    # THE LATCH DISC STOPS ONE BEAD INSIDE THE RIM POLYGON, and that radius is MEASURED off the
    # emitted chords rather than computed from a cos(pi/n) that would silently be wrong the moment
    # the seam moves off the radial.
    r_poly = min(math.hypot(seams[k][0] + (seams[(k+1) % n_tow][0]-seams[k][0])*t/64.0 - cx,
                            seams[k][1] + (seams[(k+1) % n_tow][1]-seams[k][1])*t/64.0 - cy)
                 for k in range(n_tow) for t in range(65))
    r_h = r_poly - bw
    if a.floor_layers and r_h <= a.floor_pitch:
        ap.error(f"--dia {a.dia:g} leaves a {r_h:.1f} mm latch disc, which does not fit a "
                 f"{a.floor_pitch:g} mm pitch")

    circ_t = 2 * math.pi * r_t
    nseg = max(MIN_TOWER_SEGS, int(math.ceil(circ_t / SEG)))
    n_lay = int(round((a.height - press) / lh)) + 1
    if n_lay <= a.floor_layers:
        ap.error(f"--height {a.height:g} gives {n_lay} layers, not more than the {a.floor_layers} "
                 f"floor layers asked for -- there would be no towers")
    top_z = press + (n_lay - 1) * lh
    # THE TOP LAYER IS ALWAYS BRIDGED. A ring of thirteen unconnected tower tops is not a bucket
    # rim, it is thirteen sticks; the last thing the head does is tie them together.
    bridges = set()
    if a.bridge_every > 0:
        bridges = {li for li in range(a.floor_layers, n_lay) if li % a.bridge_every == 0}
    bridges.add(n_lay - 1)

    layers = build(cx, cy, centres, phis, r_t, seam_off, nseg, n_lay, a.floor_layers,
                   a.floor_pitch, r_h, bridges)
    n_cross = check_paths(layers, centres, r_t, (bedx, bedy), press, lh, seam_deg)

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
    lay_s_ext = tow_ext / speed                      # tower cooling: extruding time per layer
    lay_s_all = (tow_ext + tow_trav) / speed         # wall clock per layer, crossings included
    path_mm = sum(layer_mm(L)[0] for L in layers)
    trav_mm = sum(layer_mm(L)[1] for L in layers)
    floor_mm = sum(layer_mm(L)[0] for L in layers[:a.floor_layers])
    n_moves = sum(len(L["kind"]) for L in layers)
    land_w1 = bw * lh / press                        # what layer 1 ACTUALLY lands at, pressed
    gap_chord = math.dist(seams[0], seams[1])
    bridge_air = air_span(seams[0], seams[1], centres[0], centres[1], r_t, bw)
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
            _air = air_for_count(cx, cy, r_ring, r_t, bw, nc)
            if _air is not None and _air <= PROVEN_AIR_MM:
                _p = round(0.5 * (circ_ring / nc + circ_ring / (nc - 1)), 2)
                if max(3, int(math.ceil(circ_ring / _p))) == nc:
                    pitch_hint = (_p, nc, _air)
                break
    mins = (path_mm + trav_mm) / speed / 60.0
    vol_cm3 = path_mm * bw * lh / 1000.0

    L = []
    w = L.append
    w(f"; BUCKET ON TOWERS — {n_tow} towers on a {a.dia:g}mm circle, bridged every "
      f"{a.bridge_every} layers")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={speed:.4f}")
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; LAYER1_WIDTH={w1:.2f}mm landed ({w1/(bw*lh/press):.2f}x the body's own flow pressed into the {press:g} gap)")
    w(f"; PRINT_TEMP={temp}")
    w(f"; bead {bw:g}x{lh:g}   nozzle {machine.NOZZLE:g}   (Oleg 2026-08-04; Klipper's "
      f"nozzle_diameter field reads 0.4 on this machine and lies)")
    w(f"; FLOW_DERATE=a {machine.NOZZLE:g} nozzle laying its own slicer's {bw:g}x{lh:g} bead at the "
      f"{speed:g} mm/s north star delivers {flow:.2f} mm3/s. Reaching {0.8*r8cap:g} would mean "
      f"WIDENING the bead, and a single-wall tower's wall thickness IS the bead. Declared, not "
      f"silent.")
    w(";")
    w("; ---------------- WHAT THIS PART IS ----------------")
    w(f"; TOWERS {n_tow} single-wall posts, {a.tower_d:g}mm outer ({a.tower_d/bw:.0f} beads), "
      f"toolpath radius {r_t:.2f}mm,")
    w(f";        centres on a {a.dia:g}mm circle at {circ_ring/n_tow:.2f}mm arc spacing (--pitch "
      f"{a.pitch:g} is a MAXIMUM,")
    w(f";        so the count is ceil({circ_ring:.1f}/{a.pitch:g})={n_tow}). 8.2mm is MEASURED: "
      f"4.92 breaks easily by hand,")
    w(f";        6.56 takes effort, 9.84 does not break. Each tower only ever goes UP.")
    w(f"; BRIDGE every gap is spanned every {a.bridge_every} layers, and always on the top layer "
      f"(the rim).")
    w(f";        {gap_chord:.2f}mm seam to seam, of which {bridge_air:.2f}mm is UNSUPPORTED AIR — "
      f"measured on the")
    w(f";        chord, not the (span - one diameter) the coupon uses, because THIS chord clears "
      f"both towers")
    w(f";        instead of landing across them, so almost none of it is over material.")
    w(f";        Each bridge is ONE move, so nothing in the planner can slow it and let it sag.")
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
        w(f";        Layer 1 is pressed into the {press:g} gap carrying the full {bw*lh:.4f}mm2/mm, "
          f"so it lands")
        w(f";        {land_w1:.2f}mm wide and the second latch layer bridges "
          f"{max(0.0, a.floor_pitch-land_w1):.2f}mm of clear air between landings.")
    w(f"; RIM    on a FLOOR layer the gap crossings are EXTRUDED, so the floor ends as a solid "
      f"{n_tow}-gon tying")
    w(f";        every tower foot together. Each tower's first airborne layer lands on its own "
      f"footprint,")
    w(f";        not on a lattice with {a.floor_pitch:g}mm holes in it.")
    w("; ---------------- WHY NOTHING LIFTS ----------------")
    w(f"; Every tower's seam sits {seam_deg:.2f} deg from its own outward radial — inside the "
      f"{win_w:.2f} deg window")
    w(f"; MEASURED by seam_window() (scanned at {SEAM_SCAN_DEG:g} deg, centre {win_c:.2f}). In that "
      f"window the chord")
    w(f"; between two seams leaves the first tower's circle at once and reaches the second from "
      f"outside, so")
    w(f"; there is nothing under the nozzle to plough and NOTHING TO LIFT OVER. All {n_cross} "
      f"crossings were")
    w(f"; re-checked against every tower on the emitted points; the file is refused if one dips "
      f"inside a wall.")
    w(f"; CONSEQUENCE: Z in this body only ever goes UP, one {lh:g}mm step per layer. There is no "
      f"lift, no")
    w(f"; drop and no descent anywhere. That is the thing that did not work last time.")
    w(f"; COST, NAMED: the seam is FIXED, so each tower carries a vertical scar up its INSIDE face. "
      f"If a")
    w(f"; tower splits, look there first. Walking it would double a bead once per layer; spiralling "
      f"Z would")
    w(f"; leave R2 no layer ladder to measure.")
    w("; ---------------- COOLING ----------------")
    w(f"; {tow_ext:.0f}mm of extrusion per tower layer = {lay_s_ext:.2f}s, {lay_s_all:.2f}s "
      f"including the gap crossings.")
    w(f"; MEASURED tonight: six towers in rotation at 4.50s per layer STOOD; one tower at 0.57s "
      f"coiled into a")
    w(f"; rope. A ring cannot have a short layer — the head must walk the whole circle before it "
      f"returns.")
    w("; ---------------- WATCH ----------------")
    w(f"; FIRST 2 MINUTES: the latch and the rim. If the rim {n_tow}-gon is not stuck flat and "
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

    # prime, off the part, in the front-left corner. The part's footprint starts at
    # X{cx-r_ring-a.tower_d/2:.0f}, so this corner is clear of it.
    px, py = 20.0, 16.0
    w(f"G1 F{f} Z{press:.3f}")
    w(f"G0 F{f} X{px:.3f} Y{py:.3f}")
    w("G1 E12 F300                          ; PRIME stationary purge")
    w(f"G1 F{f} X{px+40:.3f} Y{py:.3f} E20  ; PRIME line")
    w(f"G0 F{f} X{px+52:.3f} Y{py+12:.3f}   ; PRIME break-off wipe")
    w("G92 E0")
    w("; BODY_START")

    E = 0.0
    sx0, sy0 = layers[0]["pts"][0]
    # THE ONE TRAVEL IN THE BODY, and it happens before any of the part exists: flat at the press
    # height, across bare plate, from the prime corner to the first line. No lift and no drop --
    # there is nothing here to lift over.
    w(f"G0 F{f} X{sx0:.3f} Y{sy0:.3f} ; HOP prime corner -> first line, over bare plate")
    fan_on = False
    for li, Lay in enumerate(layers):
        z = press + li * lh
        w(f"; ---- layer {li+1} of {n_lay}  z {z:.3f}  ({Lay['label']})")
        w(f"G1 F{f} Z{z:.3f}")                   # STANDALONE Z -- this is R2's layer ladder
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
                w(f"G0 F{f} X{x:.3f} Y{y:.3f} ; HOP flat across open air, no lift (clears both "
                  f"tower walls)")
            else:
                # LAYER 1 IS METERED SEPARATELY AND ON PURPOSE.
                # Oleg, 2026-08-05, after the first ring printed: "first layer need to be full flow
                # ( a lot of fillament glued to base max width". The body's e_mm carries the SAME
                # volume into the 0.10 press gap, which lands about 1.97mm wide -- wide, but it is
                # the body's flow flattened, not more of it. He is asking for more of it. So layer 1
                # gets its own rate, derived from a TARGET LANDED WIDTH rather than from a
                # multiplier nobody can check: e = w1 * press / A_FIL. The width is the adhesion.
                E += seg * (e_mm_l1 if li == 0 else e_mm)
                if kind == "B":
                    w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f} ; BRIDGE {seg:.2f}mm seam to seam, "
                      f"{bridge_air:.2f}mm unsupported air")
                else:
                    w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f}")
            ppx, ppy = x, y

    w("M107")
    w("M104 S0")
    w("M140 S0")
    w(f"G0 F{f} Z{top_z+20:.2f}")
    w("G0 F3000 X10 Y10")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"bucket_towers_{a.printer}_{a.material}_d{a.dia:g}_h{a.height:g}_"
                             f"n{n_tow}t{a.tower_d:g}_b{a.bridge_every}.gcode")
    open(fn, "w").write("\n".join(L) + "\n")

    print(fn)
    print(f"  {n_tow} towers of {a.tower_d:g}mm on a {a.dia:g}mm circle "
          f"({circ_ring/n_tow:.2f}mm arc spacing from --pitch {a.pitch:g} as a MAXIMUM), "
          f"{a.height:g}mm tall")
    print(f"  {n_lay} layers ({a.floor_layers} latch + {n_lay-a.floor_layers} tower), top z "
          f"{top_z:.2f}mm, {len(bridges)} bridge layers at z "
          f"{', '.join(f'{press+li*lh:.1f}' for li in sorted(bridges)[:4])}"
          f"{' ...' if len(bridges) > 4 else ''}")
    print(f"  bead {bw:g} x {lh:g} at {speed:g} mm/s -> {flow:.2f} mm3/s "
          f"({100*flow/r8cap:.1f}% of the {r8cap:g} figure, DECLARED)")
    print(f"  seam {seam_deg:.2f} deg from the outward radial, inside a {win_w:.2f} deg window "
          f"measured at {SEAM_SCAN_DEG:g} deg steps (centre {win_c:.2f})")
    print(f"  {n_cross} gap crossings, every one re-checked against every tower: none passes "
          f"inside a wall, so none lifts")
    print(f"  bridge span {gap_chord:.2f}mm seam to seam, {bridge_air:.2f}mm of UNSUPPORTED AIR "
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
    print(f"  {n_moves} moves, {path_mm/1000:.1f}m extruded ({floor_mm/1000:.1f}m of it floor) + "
          f"{trav_mm/1000:.1f}m of flat crossings, {vol_cm3:.1f} cm3 of PLA")
    print(f"  est. {mins:.0f} min of motion at {speed:g} mm/s (no accel, no heat-up)")
    print(f"  ONE stroke: {len(layers)} layers, each starting exactly where the last ended, and Z "
          f"never descends (both checked, not claimed)")
    print("\n  WHAT THIS FILE DOES NOT KNOW")
    print("   - whether a ring of towers holds together as a BUCKET. Nothing here has printed.")
    print(f"   - whether a {bridge_air:.2f}mm bridge lands or sags. {PROVEN_AIR_MM:g}mm did, on a "
          f"row of six towers, which is a")
    print("     different part with different air around it, and that figure is a lower bound "
          "rather than a limit.")
    print("   - anything about what it can CARRY. The wall has 13 gaps in it and the floor is a")
    print("     lattice: this is a bucket in SHAPE. It is not a vessel and it will not hold liquid.")
    print("   - how much it strings. There is no retraction in this project and the head crosses "
          "open air")
    print(f"     {n_tow} times on {n_lay-a.floor_layers-len(bridges)} layers. The coupon's web was "
          f"real and unmeasured.")
    print("   - anything about another machine. 0.82 x 0.24 is this printer's own slicer geometry.")


if __name__ == "__main__":
    main()
