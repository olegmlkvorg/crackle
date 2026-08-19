#!/usr/bin/env python3
"""BUCKET, 200 mm across, standing on a CROSS-LATCH floor instead of a solid one.

Oleg, 2026-08-05: "Now go for a real bucket , small one, 10cm radius with couple cross latch
layers of floor".

So: 200 mm outer diameter, a single-wall cylinder 40 mm tall, and a floor that is two layers of
straight parallel lines with the second layer's lines PERPENDICULAR to the first's. That crossing
is the "cross latch". It is a lattice, so it has holes in it on purpose -- about half the floor
area is open at the default pitch, and the number is computed and printed rather than asserted.

WHY THIS IS NOT bucket.py. bucket.py is the rosette/sinusoid-wave bucket from 2026-07-27 and is
still the thing validate.py's WAVE_SLOPE branch is written for. This is a different part with a
different floor and a plain cylindrical wall, so it gets its own file rather than overwriting one
that has printed.

THE THREE PIECES, and every one of them is one unbroken stroke welded to the next
--------------------------------------------------------------------------------

  FLOOR   --floor-layers (default 2) layers of parallel chords at --floor-pitch, each layer's
          lines at 90 degrees to the one under it. The lines are clipped to the 200 mm circle.

  RING    every floor layer ends with a FULL closed circle at exactly the wall's own centreline
          radius. THIS RING IS WHY THE WALL CAN EXIST. A lattice has gaps; a single-bead wall
          landing on a gap is extruding into air for that fraction of its circumference, layer
          after layer, and the whole 40 mm of it is carried by whatever the first lap grips. The
          ring gives the wall a continuous, solid, one-bead pad to stand on all the way round, and
          because it is the LAST thing drawn on the top floor layer, the wall starts from the
          ring's own end point with no move in between -- ring and wall are literally one stroke.

  WALL    a single-wall cylinder. The toolpath circle is (D - bead)/2, not D/2: a single-wall
          round feature is drawn on its CENTRELINE, so commanding D/2 would print a bucket one
          bead too wide. Same rule the tower coupon derives its diameter floor from.

WHY THE FLOOR PITCH DEFAULTS TO 5.0 mm, AND WHY NOT SOLID
----------------------------------------------------------
A solid disc would be a floor, not a latch, and it is not what was asked for. The pitch is picked
from the one thing that can actually fail: the SECOND latch layer has to bridge from one first-layer
line to the next, in air.

Layer 1 is pressed into the machine.PRESS_HARD gap carrying the body's full mm2 per mm, so it does
not land one bead wide -- it lands at bead*layer_h/press, which is 1.97 mm at 0.82 x 0.24 into 0.10.
So at pitch P the second layer's clear unsupported span is P - 1.97 mm, and at the 5.0 default that
is 3.03 mm of air between landings. A 3 mm bridge at a 0.82 bead is ordinary; the strand crosses it
in 60 ms at the north star and lands before it can sag. Widen the pitch and the span grows linearly
-- --floor-pitch 10 is a 8.03 mm bridge, which is a different and much less certain claim.

The open area is reported by the generator from the emitted geometry, not from a sentence here.

THE SEAM IS FIXED, AND THAT IS A REAL COST, STATED
---------------------------------------------------
Every wall layer draws exactly one revolution and therefore ends where it began, which is where the
next layer must begin if there is to be no travel move. That forces the start/stop point to the SAME
angle on every layer: a vertical scar line up the bucket. The two ways out both cost more than they
buy here:

  * walk the seam by extruding one segment PAST the closure. That is a doubled bead, once per
    layer, and the nozzle drives over its own 2x bump on the next lap.
  * spiral Z continuously (vase mode). There is then no layer ladder in the file at all, and
    validate.py's R2 -- the check that nothing floats above the layer below -- silently has nothing
    to measure. A guard that switches itself off is the failure mode this repo is built around
    refusing.

So: fixed seam, honestly named. If the bucket splits, look at the seam first.

WHAT RUNS AT WHAT
-----------------
    bead width      0.82   machine.SLICER_LINE_W, read off his Creality K2 Plus 0.8 profiles
    layer height    0.24   machine.SLICER_LAYER_H
    layer 1 gap     0.10   machine.PRESS_HARD
    speed           50     machine.DEFAULT_SPEED, every move in the file including layer 1
    nozzle temp     machine.MATERIAL_TEMP[material] -- READ, never typed here
    bed             machine.bed_for(material, printer)
    part fan        machine.FAN_MAX[material], overridable with --fan; layer 1 is NEVER overridden

Usage:  python3 bucket_latch.py                      (the part Oleg asked for)
        python3 bucket_latch.py --height 60          (taller)
        python3 bucket_latch.py --floor-pitch 8      (a coarser latch, a longer bridge)
        python3 bucket_latch.py --fan 0.5            (more cooling for the wall; layer 1 unaffected)
"""
import argparse, math, os
import machine

A_FIL = math.pi * (1.75 / 2) ** 2      # mm2 of 1.75mm filament; computed once, used once

# SEGMENT LENGTH FOR EVERY CURVE AND EVERY CLIPPED CHORD.
# On a 99.6 mm radius a 1.0 mm chord sits 1.0^2/(8*99.6) = 1.26 microns inside the true circle --
# the same order as the 1 micron grid the gcode is written on, so the polygon is round to the
# resolution the file can even express. It also fixes the move rate at 50/s against
# machine.MAX_MOVES_PER_SEC = 300, so the host cannot run out of lookahead.
# It matters for a second reason that is easy to miss: validate.py's overhang check indexes the
# layer BELOW by its emitted POINTS, so a 200 mm chord emitted as one G1 would leave that layer
# looking like two isolated dots and the layer above it like an unsupported bridge over nothing.
SEG = 1.0
MIN_HALF_CHORD = 2.0   # mm; a chord shorter than this near the rim is a stub, not a latch line


# --------------------------------------------------------------------------------- path helpers
def wrap(a):
    """Signed angle difference folded into (-pi, pi]."""
    while a <= -math.pi:
        a += 2 * math.pi
    while a > math.pi:
        a -= 2 * math.pi
    return a


def line_pts(p0, p1, seg):
    """Straight run p0 -> p1, subdivided at `seg`, EXCLUDING p0."""
    d = math.dist(p0, p1)
    n = max(1, int(math.ceil(d / seg)))
    return [(p0[0] + (p1[0] - p0[0]) * i / n, p0[1] + (p1[1] - p0[1]) * i / n)
            for i in range(1, n + 1)]


def arc_to(cx, cy, r, a0, a1, seg):
    """Shortest arc on radius r from angle a0 to a1, EXCLUDING the point at a0."""
    d = wrap(a1 - a0)
    n = max(1, int(math.ceil(abs(d) * r / seg)))
    return [(cx + r * math.cos(a0 + d * i / n), cy + r * math.sin(a0 + d * i / n))
            for i in range(1, n + 1)]


def ring_pts(cx, cy, r, a0, n):
    """One full closed revolution on radius r starting at a0, EXCLUDING the point at a0.

    The last point is the point at a0 again, so the caller's path closes exactly and the next
    layer can start from it with no move at all. That closure is the whole reason the wall needs
    no travel: see THE SEAM IS FIXED in the module docstring.
    """
    return [(cx + r * math.cos(a0 + 2 * math.pi * i / n), cy + r * math.sin(a0 + 2 * math.pi * i / n))
            for i in range(1, n + 1)]


def ang(cx, cy, p):
    return math.atan2(p[1] - cy, p[0] - cx)


def frame_pt(cx, cy, phi, t, s):
    """Point at cross-offset t and along-offset s in the frame rotated by phi.

    u = (cos phi, sin phi) runs ALONG the latch lines, n = (-sin phi, cos phi) runs ACROSS them,
    and both are unit and perpendicular -- so a point at (t, s) is exactly hypot(t, s) from the
    centre, which is what lets the line ends be placed ON the turnaround circle by construction
    rather than by intersecting anything.
    """
    c, s_ = math.cos(phi), math.sin(phi)
    return (cx + t * (-s_) + s * c, cy + t * c + s * s_)


def t_offsets(r, pitch):
    """Cross-offsets of the latch lines, centred so one line passes through the middle.

    Centring matters for the CROSS: with the same offsets in both directions the two layers meet
    on a square grid, so every crossing is a real landing and they are evenly spread. An arbitrary
    phase would put some crossings almost on top of each other and leave longer unsupported runs
    elsewhere, for no gain.
    """
    reach = math.sqrt(max(0.0, r * r - MIN_HALF_CHORD ** 2))
    j = int(math.floor(reach / pitch))
    return [k * pitch for k in range(-j, j + 1)]


def latch_pts(cx, cy, r, pitch, phi, order, side, seg):
    """One cross-latch layer as a serpentine: chord, arc on the rim, chord back, arc, ...

    The turnarounds ride the circle of radius r rather than cutting straight across, so the path
    never leaves the disc and never crosses its own lattice. `order` picks which end of the stack
    of lines to start from and `side` which end of the first line -- four variants of the same
    geometry, which is what lets the caller enter this layer from wherever the previous one left
    off without a travel move (see build_layers).
    """
    ts = t_offsets(r, pitch)
    if order < 0:
        ts = ts[::-1]
    cur = side
    s0 = math.sqrt(max(0.0, r * r - ts[0] * ts[0]))
    pts = [frame_pt(cx, cy, phi, ts[0], cur * s0)]
    for i, t in enumerate(ts):
        s = math.sqrt(max(0.0, r * r - t * t))
        b = frame_pt(cx, cy, phi, t, -cur * s)
        pts += line_pts(pts[-1], b, seg)
        if i < len(ts) - 1:
            t2 = ts[i + 1]
            s2 = math.sqrt(max(0.0, r * r - t2 * t2))
            c = frame_pt(cx, cy, phi, t2, -cur * s2)
            pts += arc_to(cx, cy, r, ang(cx, cy, b), ang(cx, cy, c), seg)
        cur = -cur
    return pts


# ------------------------------------------------------------------------------- the whole part
def build_layers(cx, cy, r_w, r_h, pitch, n_floor, n_wall_layers, n_ring, seg):
    """Every layer as a point list whose FIRST point is the previous layer's LAST point.

    That invariant is the whole no-travel design, and check_continuity() below refuses to emit if
    it is ever broken -- so "one continuous extrusion" is a property of the geometry here, not
    something validate.py is left to discover afterwards.
    """
    layers = []
    for i in range(n_floor):
        phi = (math.pi / 2.0) * (i % 2)     # PERPENDICULAR to the layer below: this is the latch
        if not layers:
            # First floor layer. Nothing has been printed, so the entry point is free and the
            # serpentine simply starts where it wants; the head reaches it once, off the part.
            layer = latch_pts(cx, cy, r_h, pitch, phi, +1, -1, seg)
        else:
            start = layers[-1][-1]           # sitting on the previous layer's ring, at r_w
            th_in = ang(cx, cy, start)
            # Step radially in by one bead onto the turnaround circle. One extruded move, 0.82 mm.
            layer = [start, (cx + r_h * math.cos(th_in), cy + r_h * math.sin(th_in))]
            # Of the four serpentine variants, take the one whose first point is angularly
            # NEAREST where we already are, so the lead-in arc along the rim is as short as the
            # geometry allows. It is still an extruded arc on the rim, not a travel.
            best = None
            for order in (+1, -1):
                for side in (+1, -1):
                    cand = latch_pts(cx, cy, r_h, pitch, phi, order, side, seg)
                    d = abs(wrap(ang(cx, cy, cand[0]) - th_in))
                    if best is None or d < best[0]:
                        best = (d, cand)
            cand = best[1]
            layer += arc_to(cx, cy, r_h, th_in, ang(cx, cy, cand[0]), seg)
            layer += cand[1:]
        # Radial step back out to the wall's radius, then the closed perimeter ring. The ring is
        # LAST on purpose: the wall above starts from its end point with nothing in between.
        th_out = ang(cx, cy, layer[-1])
        layer.append((cx + r_w * math.cos(th_out), cy + r_w * math.sin(th_out)))
        layer += ring_pts(cx, cy, r_w, th_out, n_ring)
        layers.append(layer)

    # THE WALL. Fixed seam at wherever the floor left the head; if there is no floor at all the
    # seam is simply angle 0 and the first wall lap is the pressed layer.
    th_seam = ang(cx, cy, layers[-1][-1]) if layers else 0.0
    seam = (cx + r_w * math.cos(th_seam), cy + r_w * math.sin(th_seam))
    for _ in range(n_wall_layers):
        layers.append([seam] + ring_pts(cx, cy, r_w, th_seam, n_ring))
    return layers


def check_continuity(layers, bed):
    """Refuse to emit anything that is not ONE stroke, and refuse anything off the plate.

    A gap between one layer's end and the next layer's start is a travel move by another name --
    the generator would simply not write the G0 and the printer would draw a line across the part.
    validate.py would catch the ploughing afterwards; this catches the cause, at the point where
    the fix is one line of geometry.
    """
    for i in range(1, len(layers)):
        d = math.dist(layers[i][0], layers[i - 1][-1])
        if d > 1e-6:
            raise SystemExit(
                f"REFUSING TO EMIT: layer {i+1} starts {d:.4f} mm from where layer {i} ended. "
                f"That gap is a travel move inside the object, which is exactly what this part is "
                f"built to avoid. Fix the handoff, do not add a hop.")
    for i, pts in enumerate(layers):
        for (x, y) in pts:
            if not (0.0 <= x <= bed[0] and 0.0 <= y <= bed[1]):
                raise SystemExit(
                    f"REFUSING TO EMIT: layer {i+1} reaches ({x:.1f},{y:.1f}), off a "
                    f"{bed[0]:g}x{bed[1]:g} plate. The part does not fit this machine.")


def open_area(r_w, r_h, pitch, w1, w2, n_floor):
    """Fraction of the 200 mm disc the latch leaves OPEN, from the emitted widths.

    Two crossing sets of strips of width w on pitch P leave (1 - w1/P)(1 - w2/P) of the area
    untouched, away from the rim. Reported because "a lattice means gaps" is a claim about a
    number, and the number should come out of the geometry rather than out of the docstring.
    """
    if n_floor < 1:
        return 1.0
    a = max(0.0, 1.0 - min(1.0, w1 / pitch))
    b = max(0.0, 1.0 - min(1.0, w2 / pitch)) if n_floor > 1 else 1.0
    return a * b


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED))
    ap.add_argument("--material", default=None,
                    help="defaults to whatever machine.LOADED says is in this printer")
    ap.add_argument("--diameter", type=float, default=200.0,
                    help="OUTER diameter mm. 200 = Oleg's 10 cm radius (2026-08-05).")
    ap.add_argument("--height", type=float, default=40.0, help="total height mm including floor")
    ap.add_argument("--floor-layers", type=int, default=2,
                    help="cross-latch layers; each is perpendicular to the one below. 2 = the "
                         "'couple' asked for. 0 stands the wall straight on the plate.")
    ap.add_argument("--floor-pitch", type=float, default=5.0,
                    help="mm between latch lines. NOT solid on purpose -- see the docstring: at "
                         "5.0 the second layer bridges 3.03 mm of clear air between landings.")
    ap.add_argument("--speed", type=float, default=machine.DEFAULT_SPEED,
                    help=f"mm/s for every move in the file. Default is the "
                         f"{machine.DEFAULT_SPEED:g} north star; lower is legitimate, higher is "
                         f"refused.")
    ap.add_argument("--fan", type=float, default=None,
                    help="part-cooling fan fraction 0..1 for the BODY, overriding "
                         "machine.FAN_MAX. Layer 1 is unaffected and stays at its material's "
                         "first-layer value, so the plate weld is never chilled.")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    # MATERIAL FOLLOWS THE PRINTER. A part generated for one machine with another machine's
    # filament is silently wrong: right geometry, wrong temperature, wrong flow ceiling.
    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    bw, lh = machine.SLICER_LINE_W, machine.SLICER_LAYER_H
    press = machine.PRESS_HARD                     # 0.10, R1
    # 50 IS A CEILING, NOT A TARGET TO BEAT. machine.MAX_SPEED is the north star and nothing in
    # this project may run above it; a slower run is a legitimate constraint and is allowed.
    if a.speed > machine.MAX_SPEED + 1e-9:
        raise SystemExit(f"REFUSING TO EMIT: --speed {a.speed:g} is above the "
                         f"{machine.MAX_SPEED:g} mm/s north star, which is a ceiling. "
                         f"Slower is allowed; faster is not.")
    speed = a.speed
    f = round(speed * 60)
    temp = machine.MATERIAL_TEMP[a.material]       # READ, never typed: 210 for pla as loaded today
    bed = machine.bed_for(a.material, a.printer)
    # BODY FAN. machine.FAN_MAX is Oleg's 20% PLA ceiling (2026-07-26) and it is right for a flat
    # part -- high fan chills the bead as it lands and costs adhesion. A 40 mm single-bead wall is
    # the other regime: it has to freeze before the next lap arrives 12.6 s later. So the override
    # is per-run rather than a change to FAN_MAX, which must not move. Layer 1 is deliberately NOT
    # affected: fan_first_layer() still governs the plate weld, which is what the 20% rule protects.
    fan = machine.FAN_MAX[a.material] if a.fan is None else max(0.0, min(1.0, a.fan))
    e_mm = bw * lh / A_FIL                         # filament mm per mm of path -- ONE value
    flow = bw * lh * speed
    r8cap = machine.flow_cap(a.material, a.printer)

    if a.floor_layers < 0:
        ap.error("--floor-layers cannot be negative")
    if a.floor_pitch <= bw:
        ap.error(f"--floor-pitch {a.floor_pitch:g} is not wider than the {bw:g} bead: that is a "
                 f"solid floor drawn as a lattice, with every line overlapping its neighbour")

    r_w = (a.diameter - bw) / 2.0                  # WALL CENTRELINE -- single-wall, see docstring
    r_h = r_w - bw                                 # turnaround circle: one bead inside the ring,
                                                   # so the latch's rim arcs abut the ring rather
                                                   # than laying a second bead on top of it
    if r_h <= a.floor_pitch:
        ap.error(f"--diameter {a.diameter:g} leaves a {r_h:.1f} mm latch disc, which does not fit "
                 f"a {a.floor_pitch:g} mm pitch")
    n_ring = max(16, int(round(2 * math.pi * r_w / SEG)))

    n_lay = int(round((a.height - press) / lh)) + 1
    n_wall = n_lay - a.floor_layers
    if n_wall < 1:
        ap.error(f"--height {a.height:g} gives {n_lay} layers, which is not more than the "
                 f"{a.floor_layers} floor layers asked for -- there would be no wall")
    top_z = press + (n_lay - 1) * lh

    bedx, bedy = machine.BED[a.printer]
    cx, cy = bedx / 2.0, bedy / 2.0
    layers = build_layers(cx, cy, r_w, r_h, a.floor_pitch, a.floor_layers, n_wall, n_ring, SEG)
    check_continuity(layers, (bedx, bedy))

    # measured off the built path, not predicted
    path_mm = sum(math.dist(p, q) for pts in layers for p, q in zip(pts, pts[1:]))
    floor_mm = sum(math.dist(p, q) for pts in layers[:a.floor_layers] for p, q in zip(pts, pts[1:]))
    n_moves = sum(len(pts) - 1 for pts in layers)
    land_w1 = bw * lh / press                      # what layer 1 ACTUALLY lands at in the press gap
    bridge = max(0.0, a.floor_pitch - land_w1)     # clear air the second latch layer crosses
    openf = open_area(r_w, r_h, a.floor_pitch, land_w1, bw, a.floor_layers)
    lay_s = (2 * math.pi * r_w) / speed            # seconds per wall lap
    mins = path_mm / speed / 60.0
    vol_cm3 = path_mm * bw * lh / 1000.0

    L = []
    w = L.append
    w(f"; BUCKET — {a.diameter:g}mm across, single-wall, on a cross-latch floor")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={speed:.4f}")
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; PRINT_TEMP={temp}")
    w(f"; bead {bw:g}x{lh:g}   nozzle {machine.NOZZLE:g}   (Oleg 2026-08-04; Klipper's "
      f"nozzle_diameter field reads 0.4 on this machine and lies)")
    w(f"; FLOW_DERATE=a {machine.NOZZLE:g} nozzle laying its own slicer's {bw:g}x{lh:g} bead at "
      f"the {speed:g} mm/s north star delivers {flow:.2f} mm3/s. Reaching {0.8*r8cap:g} would mean "
      f"WIDENING the bead, and a single-wall bucket's wall thickness IS the bead. Declared, not "
      f"silent.")
    w(";")
    w("; ---------------- WHAT THIS PART IS ----------------")
    w(f"; WALL   single bead, outer diameter {a.diameter:g}mm, toolpath radius {r_w:.2f}mm.")
    w(f";        A single-wall round feature is drawn on its CENTRELINE, so the path is")
    w(f";        (D - bead)/2 = {r_w:.2f}, not D/2 = {a.diameter/2:g}. {n_wall} laps of "
      f"{2*math.pi*r_w:.0f}mm each,")
    w(f";        {lay_s:.1f}s per lap at {speed:g} mm/s -- cooling is not the constraint at this")
    w(f";        diameter, unlike a thin tower where the same lap takes a fraction of a second.")
    w(f"; FLOOR  {a.floor_layers} cross-latch layer(s) at {a.floor_pitch:g}mm pitch, each "
      f"perpendicular to the one below.")
    if a.floor_layers >= 2:
        w(f";        Layer 1 is pressed into the {press:g} gap carrying the body's full "
          f"{bw*lh:.4f}mm2/mm, so it")
        w(f";        lands {land_w1:.2f}mm wide, not {bw:g}. The second layer therefore bridges "
          f"{bridge:.2f}mm of CLEAR AIR")
        w(f";        between landings -- an ordinary bridge at this bead. Widen --floor-pitch and "
          f"that span")
        w(f";        grows linearly; it is the number to watch, not the pitch.")
        w(f";        About {100*openf:.0f}% of the disc is left OPEN away from the rim. It is a "
          f"latch, not a floor.")
    elif a.floor_layers == 1:
        w(f";        ONE latch layer only, so nothing crosses anything: this is a set of parallel")
        w(f";        lines, not a latch. Pass --floor-layers 2 for the part Oleg asked for.")
    else:
        w(f";        NO FLOOR AT ALL -- the wall stands straight on the plate. This is the "
          f"floorless control,")
        w(f";        not the part Oleg asked for.")
    w(f"; RING   every floor layer ENDS with a closed circle at the wall's own {r_w:.2f}mm radius.")
    w(f";        A single-bead wall landing on a lattice gap would be extruding into air for that")
    w(f";        fraction of every lap, for {a.height:g}mm. The ring is the continuous pad it "
      f"stands on,")
    w(f";        and being last means the wall starts from its end point with NO move in between.")
    w("; ONE STROKE. There is exactly one non-extruding move in the body: reaching the part from")
    w(";        the prime corner, before any of it exists. Every layer starts where the last one")
    w(";        ended, and the generator REFUSES to emit if that is ever not true.")
    w(f"; SEAM   FIXED, at one angle, all {n_wall} wall layers. A full revolution ends where it")
    w(";        began, so a walked seam would mean either a doubled bead or a spiral with no layer")
    w(";        ladder for R2 to check. It is a real weak line: if the bucket splits, look there.")
    w("; ---------------- WATCH ----------------")
    w(f"; FIRST 90 SECONDS: the latch goes down as {a.floor_layers} passes of straight lines. If "
      f"they are not")
    w(f";   stuck flat and glossy, stop -- at a {press:g} press gap a line that does not weld is a "
      f"line the")
    w(f";   second layer has nothing to land on.")
    w(f"; THEN THE SECOND LATCH LAYER: it crosses {bridge:.2f}mm gaps in the air. Strands that SAG "
      f"rather than")
    w(";   land mean the pitch is too wide for this filament -- re-run with a smaller "
      "--floor-pitch.")
    w(f"; THEN THE WALL: {n_wall} laps, {lay_s:.1f}s each. A wall that leans is a cooling problem "
      f"before it is")
    w(f";   anything else -- --fan raises the body fan above the {100*machine.FAN_MAX[a.material]:.0f}%"
      f" PLA ceiling without")
    w(";   touching layer 1.")
    w("; ---------------------------------------")
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
    # print left them at" -- and a draft across a 200mm first layer is how a plate lets go.
    for _ln in machine.aux_fans(a.printer, 0.0):
        w(f"{_ln}                  ; no chamber draft across a 200mm first layer")
    w("G92 E0")

    sx0, sy0 = layers[0][0]
    # ONE SHARED PRIME, machine.prime(). Was a hand-rolled corner purge that extruded 12mm of
    # filament (28.9 mm3) with the head STANDING STILL at the 0.10 press gap and then laid a line
    # metered 2.43x layer 1's own rate -- two separate blob sources, in a corner asserted clear by
    # the comment rather than computed. `e_mm` is this file's ONE rate, so the prime is the same
    # bead the latch floor lays. The footprint is the wall's outermost material, as a CIRCLE: the
    # bounding box of this bucket covers the plate and would leave nowhere to prime.
    machine.prime(w, printer=a.printer, z=press, rate=e_mm, feed=f,
                  travel_feed=round(machine.MACHINE_MAX_SPEED * 60),
                  avoid=(("circle", cx, cy, r_w + bw / 2.0),), near=(sx0, sy0))
    w("; BODY_START")

    E = 0.0
    # THE ONE TRAVEL IN THE BODY, and it happens before any of the part exists: flat at the press
    # height, across bare plate, from the prime to the first latch line. No lift and no drop -- a
    # lift-then-drop between features is exactly the shape validate.py refuses, and there is
    # nothing here to lift over now that the prime stands 0.10 tall rather than 2.0.
    w(f"G0 F{f} X{sx0:.3f} Y{sy0:.3f} ; HOP prime -> first latch line, over bare plate")
    fan_on = False
    for li, pts in enumerate(layers):
        z = press + li * lh
        kind = "latch" if li < a.floor_layers else "wall"
        w(f"; ---- layer {li+1} of {n_lay}  z {z:.3f}  ({kind})")
        w(f"G1 F{f} Z{z:.3f}")                  # STANDALONE Z -- this is R2's layer ladder
        if li == 1 and not fan_on:
            _src = (f"machine.FAN_MAX['{a.material}']" if a.fan is None
                    else f"--fan {a.fan:g} on the command line, OVERRIDING "
                         f"machine.FAN_MAX['{a.material}']={machine.FAN_MAX[a.material]:g}")
            w(f"M106 S{int(round(fan*255))}     ; {fan*100:.0f}% — {_src}")
            fan_on = True
        ppx, ppy = pts[0]
        for (x, y) in pts[1:]:
            seg = math.hypot(x - ppx, y - ppy)
            if seg < 1e-9:
                continue
            E += seg * e_mm
            w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f}")
            ppx, ppy = x, y

    w("M107")
    w("M104 S0")
    w("M140 S0")
    w(f"G0 F{f} Z{top_z+20:.2f}")
    w("G0 F3000 X10 Y10")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"bucket_latch_{a.printer}_{a.material}_d{a.diameter:g}_"
                             f"h{a.height:g}_f{a.floor_layers}p{a.floor_pitch:g}.gcode")
    machine.emit_gcode(fn, "\n".join(L) + "\n")

    print(fn)
    print(f"  {a.diameter:g}mm outer / toolpath radius {r_w:.2f}mm, {a.height:g}mm tall, "
          f"{n_lay} layers ({a.floor_layers} latch + {n_wall} wall), top z {top_z:.2f}mm")
    print(f"  bead {bw:g} x {lh:g} at {speed:g} mm/s -> {flow:.2f} mm3/s "
          f"({100*flow/r8cap:.1f}% of the {r8cap:g} figure, DECLARED)")
    print(f"  latch pitch {a.floor_pitch:g}mm; layer 1 lands {land_w1:.2f}mm wide at the {press:g} "
          f"press, so the second layer bridges {bridge:.2f}mm of air")
    print(f"  ~{100*openf:.0f}% of the disc left open away from the rim (measured from the emitted "
          f"widths, not assumed)")
    print(f"  {n_moves} extruding moves, {path_mm/1000:.1f}m of path ({floor_mm/1000:.1f}m of it "
          f"floor), {vol_cm3:.1f} cm3 of PLA")
    print(f"  est. {mins:.0f} min of motion at {speed:g} mm/s (no accel, no heat-up)")
    print(f"  ONE continuous extrusion: {len(layers)} layers, every one starting where the last "
          f"ended (checked, not claimed)")
    print("\n  WHAT THIS FILE DOES NOT KNOW")
    print(f"   - whether a {bridge:.2f}mm bridge lands or sags on THIS spool. Nothing here has "
          f"been printed;")
    print("     the pitch is derived from the pressed first layer's width, not measured on a part.")
    print(f"   - whether a fixed seam holds for {a.height:g}mm. It is the one deliberate weak line "
          f"in the part.")
    print("   - anything about what the bucket can CARRY. A single-bead wall on a half-open floor")
    print("     is a container, and its load has not been calculated or tested.")
    print("   - anything about another machine. 0.82 x 0.24 is this printer's own slicer geometry.")


if __name__ == "__main__":
    main()
