#!/usr/bin/env python3
"""CLEATED BELT — a closed loop with scoop cleats, printed flat as one continuous extrusion.

Oleg: "or lets just do some kind of belt assembly", after the screw analysis showed a vertical
Archimedes screw cannot lift a rolling sphere without either a 40-degree tilt or ~2990 rpm.

This is already the documented design in Assist/guides/balls-vertical.md -- "Belt-Lift = cleated TPU
friction loop over two crowned PETG pulleys ... flights scoop balls up, dump at the top port".

WHY IT SUITS THIS TOOLCHAIN, where the screw did not:
  · A screw is a SOLID part. It needs perimeters and infill, and nothing in crackle emits those --
    every generator here produces single-wall continuous paths. A screw would have to go through
    trimesh -> STL -> Creality Print.
  · A belt is a closed loop of thin wall. Printed lying flat, its cross-section IS a single wall,
    its width is the Z height, and the whole part is one unbroken extrusion with no travel. That is
    exactly what this toolchain is for.
  · And it is light. A 426mm loop, 25mm wide, 1.2mm thick is ~16g. The lattice tower Oleg rejected
    was 1353g.

GEOMETRY. The belt is printed as a RACETRACK ring lying on the plate:
  · in XY: a stadium (two straights joined by semicircles) whose CENTRELINE PERIMETER equals the
    belt's required loop length, so it wraps the pulleys without stretching
  · in Z:  the belt's width -- printed standing, so belt width is print height
  · cleats: bumps pushed outward from the ring, evenly spaced by arc length along the centreline

The cleats have to be on the OUTSIDE of the flat ring. When the loop is lifted onto the pulleys the
ring's outer face becomes the belt's outer face, which is the side that carries the balls.
"""
import argparse
import math
import os

import sys as _sys

import machine
import hilbert


def stadium(length, width, n=720):
    """Centreline of a stadium: two straights of `length`, two semicircles of radius width/2."""
    r = width / 2.0
    per = 2 * length + 2 * math.pi * r
    pts = []
    for i in range(n):
        s = per * i / n
        if s < length:                                   # bottom straight, left -> right
            pts.append((s, -r))
        elif s < length + math.pi * r:                   # right semicircle
            a = (s - length) / r - math.pi / 2
            pts.append((length + r * math.cos(a), r * math.sin(a)))
        elif s < 2 * length + math.pi * r:               # top straight, right -> left
            pts.append((length - (s - length - math.pi * r), r))
        else:                                            # left semicircle
            a = (s - 2 * length - math.pi * r) / r + math.pi / 2
            pts.append((r * math.cos(a), r * math.sin(a)))
    pts.append(pts[0])
    return pts, per


def add_cleats(pts, per, n_cleats, height, width, ease=0.35, centres=None,
               return_centres=False):
    """Push `n_cleats` bumps outward from the ring, spaced evenly by ARC LENGTH.

    Spacing by arc length and not by point index matters: the semicircle ends are sampled at the
    same angular rate as the straights but cover less distance, so index spacing would bunch the
    cleats at the ends -- and cleat spacing is what sets how many balls the belt carries.

    The bump is a raised-cosine, not a rectangle. A rectangular cleat is two 90-degree corners, and
    a corner is where Klipper drops to square_corner_velocity while E keeps metering per mm of path.
    A raised cosine has no corner at all and eases in and out of the belt line.
    """
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.dist(a, b))
    total = s[-1]
    # PUT CLEATS ONLY ON STRAIGHT RUNS. Spacing them evenly by arc length drops some of them onto
    # the fold's U-turn fillets, and a bump pushed along the normal of an already-curving path
    # distorts into a spike -- measured 58 degrees at fold 2, and a full 178-degree reversal at
    # fold 3 where the fillets are tighter. The belt does not care where its cleats sit once it is
    # unfolded, so put them where the path is straight.
    turn = [0.0] * len(pts)
    for i in range(1, len(pts) - 1):
        ax, ay = pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]
        bx, by = pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1]
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la < 1e-12 or lb < 1e-12:
            continue
        turn[i] = abs(math.degrees(math.acos(
            max(-1.0, min(1.0, (ax*bx + ay*by) / (la*lb))))))
    half0 = width / 2.0
    ok = []
    for i in range(len(pts)):
        lo = hi = i
        while lo > 0 and s[i] - s[lo] < half0:
            lo -= 1
        while hi < len(pts) - 1 and s[hi] - s[i] < half0:
            hi += 1
        # CURVATURE, not straightness. Requiring a dead-straight run allowed only 14 cleats on a
        # 2.5m belt: at fold 2 the fillet radius is 21mm on a 46mm channel, so barely 4mm of each
        # run is truly straight. But the fold's curves BECOME STRAIGHT BELT once it is unfolded --
        # the curvature is an artefact of packing it onto the plate, not a property of the belt.
        # What actually matters is that pushing a bump out along the normal must not fold back on
        # itself, which needs the local radius to comfortably exceed the cleat height.
        # Swept 2.0/2.5/3.0/3.5x, measuring the worst emitted turn each time:
        #   2.0x -> 40 cleats, worst 45.8deg, 4 over 30
        #   2.5x -> 25 cleats, worst 47.2deg, 12 over 30   (WORSE — different positions
        #   3.0x -> 25 cleats, worst 47.2deg, 12 over 30    get selected, so this is not
        #   3.5x -> 25 cleats, worst 23.4deg,  0 over 30    monotonic; measure, do not guess)
        seg_len = max(1e-6, (s[hi] - s[lo]) / max(1, hi - lo))
        worst = max(turn[lo:hi + 1] or [180.0])
        r_local = seg_len / max(math.radians(worst), 1e-6)
        if r_local > 3.5 * height:
            ok.append(i)
    if len(ok) < n_cleats:
        raise SystemExit(f"only {len(ok)} straight positions for {n_cleats} cleats of {width}mm — "
                         f"the fold's straights are too short. Reduce --cleats or --cleat-w.")
    # Greedy placement in arc-length order: take a valid position whenever it is far enough from
    # the last cleat placed. Distributing evenly across the LIST of valid indices does not work --
    # they come in contiguous runs, so even spacing in index put cleats 6.3mm apart on a 22mm cleat.
    need = width * 1.15
    # CENTRES ARE CHOSEN ONCE, AT FULL CLEAT HEIGHT, AND REUSED FOR EVERY LAYER.
    # The acceptance test is `r_local > 3.5 * height`, so when height ramps per layer a DIFFERENT
    # set of positions qualifies and every cleat centre slides — measured 0.787mm between adjacent
    # layers on a 1.2mm wall. Amplitude may vary per layer; position may not.
    if centres is not None:
        centres = list(centres)
    else:
      centres = []
      for i in ok:
        if not centres or s[i] - centres[-1] >= need:
            centres.append(s[i])
      if len(centres) > n_cleats:
        keep = [centres[round(k * (len(centres) - 1) / (n_cleats - 1))] for k in range(n_cleats)] \
            if n_cleats > 1 else centres[:1]
        # re-check: thinning by index can still land two of them adjacent
        centres = [keep[0]] + [c for j, c in enumerate(keep[1:], 1) if c - keep[j-1] >= need]
    if len(centres) < 2:
        raise SystemExit("no room for cleats on the straight runs — reduce --cleat-w.")
    if return_centres:
        return centres
    if len(centres) < n_cleats:
        print(f"  note: straight runs hold {len(centres)} cleats of {width}mm, not {n_cleats} "
              f"— using {len(centres)}")
    half = width / 2.0
    out = []
    for i, p in enumerate(pts):
        # outward normal from the local tangent
        a = pts[i - 1] if i else pts[-2]
        b = pts[(i + 1) % len(pts)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = ty / L, -tx / L
        bump = 0.0
        for c in centres:
            d = abs(s[i] - c)
            d = min(d, total - d)                        # the ring wraps
            if d < half:
                bump = max(bump, height * 0.5 * (1 + math.cos(math.pi * d / half)))
        out.append((p[0] + nx * bump, p[1] + ny * bump))
    return out


def emit(length, width, belt_w, n_cleats, cleat_h, cleat_w, bead_w, layer_h, flow, temp, bed,
         fil_d, bed_xy, home, press, fan, walls, fold=0, span=0.0, first_w=3.0, aux=0.2,
         printer='k2plus', dish=2.0, rail=3.0, material='pla'):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (bead_w * layer_h) / area
    # HARD CAP the head speed, then re-derive the flow that speed actually delivers.
    # Capping speed without lowering flow would over-extrude by the same ratio.
    speed = min(flow / (bead_w * layer_h), machine.MAX_SPEED)
    flow = speed * bead_w * layer_h
    f = round(speed * 60)
    layers = max(1, int(round(belt_w / layer_h)))
    # BASE LAYER PRESSED TO THE PLATE — a 2.5m single-wall loop has enormous peel length and very
    # little weight holding it down. Metered as the thin wide ribbon it physically is at a 0.1mm
    # gap, NOT as a full bead: a full bead through 0.1mm packs and skips.
    e_first = (first_w * press) / area
    f_first = round(min(flow / (first_w * press), 25.0) * 60)

    if fold:
        # FOLD THE BELT INTO THE PLATE. Oleg: "use hilpert trick to print really long belt".
        # A stadium ring is limited by the bed: 350mm of plate buys about a 700mm loop. A closed
        # space-filling curve folds metres of belt into the same square.
        #
        # This works because of WHICH WAY the belt has to bend. Printed as a wall, the belt's
        # thickness (1.2mm) lies in XY and its width (25mm) is Z. Both unfolding the serpentine and
        # wrapping a pulley bend it about a Z-parallel axis -- through the 1.2mm dimension, the
        # compliant one. The stiff 25mm direction is never asked to bend. So the folded print
        # straightens into a long loop without fighting the material.
        #
        # A MOORE curve is used rather than a plain serpentine because it is already CLOSED: a belt
        # must be an endless loop, and this way there is no join to bond.
        ring = hilbert.round_corners(hilbert.curve(fold, span, True), span / (2 ** (fold + 1) - 1) * 0.45)
        per = sum(math.dist(a, b) for a, b in zip(ring, ring[1:]))
    else:
        ring, per = stadium(length, width)
    # CRADLE THE BALL. Oleg: "did you added a bit of cavity into belt so ball gravitates to the
    # middle of it?" — no, and a flat cleat lets a 14mm ball roll off the side of a 20mm belt.
    #
    # The fix comes free from how this is printed: BELT WIDTH IS THE Z AXIS, so varying the cleat
    # height per layer shapes the cleat's profile ACROSS the belt. A parabola that protrudes more
    # at the edges and less in the middle turns every cleat into a valley, and the ball rolls to
    # the bottom of it. `dish` is that depth.
    #
    # The ball (r7) is wider than half the belt (10), so it rides ON the valley walls rather than
    # sinking to the bottom — the dish only has to TILT it, not enclose it. 2mm gives a ~9 degree
    # wall and a restoring force of 0.16x weight at 2mm off-centre, which is ample.
    base_ring = ring

    if fold:
        cx = cy = 0.0
        _xs = [p[0] for p in ring]; _ys = [p[1] for p in ring]
        cx = (bed_xy[0] - (max(_xs) - min(_xs))) / 2.0 - min(_xs)
        cy = (bed_xy[1] - (max(_ys) - min(_ys))) / 2.0 - min(_ys)
    else:
        cx = (bed_xy[0] - (length + width + 2 * cleat_h)) / 2.0 + cleat_h
        cy = bed_xy[1] / 2.0
    base_ring = [(p[0], p[1]) for p in base_ring]
    _fixed_centres = add_cleats(base_ring, per, n_cleats, cleat_h, cleat_w, return_centres=True)
    _probe = add_cleats(base_ring, per, n_cleats, cleat_h, cleat_w, centres=_fixed_centres)
    ring = [(p[0] + cx, p[1] + cy) for p in _probe]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    if min(xs) < 4 or min(ys) < 4 or max(xs) > bed_xy[0] - 4 or max(ys) > bed_xy[1] - 4:
        raise SystemExit(f"belt spans X {min(xs):.0f}..{max(xs):.0f} Y {min(ys):.0f}..{max(ys):.0f} "
                         f"on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} plate — off the edge. "
                         f"Shorten --length or use the larger printer.")

    L = []
    w = L.append
    w(f"; CLEATED BELT — closed loop, {per:.0f}mm centreline, {belt_w}mm wide, {n_cleats} cleats")
    w(f"; bead {bead_w}x{layer_h} at {speed:.0f} mm/s -> flow={flow} mm3/s, {layers} layers")
    w(f"; printed FLAT: belt width is the Z height, belt thickness is the wall")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {layers}")
    w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}")
    w(f"M104 S{temp}")
    w("G90")
    w("G28" if home else "; NO HOME — assumes the machine is ALREADY homed; push.py verifies")
    # M190 only waits for HEATING; if the bed is hotter than target it returns instantly and
    # the part prints on a plate left hot by the previous job. TEMPERATURE_WAIT blocks both ways.
    w(f"TEMPERATURE_WAIT SENSOR='heater_bed' MINIMUM={bed-3} MAXIMUM={bed+5}")
    w(f"M109 S{temp}")
    w("M204 S8000")
    w("M107" if not fan else f"M106 S{fan}")
    # PER-MACHINE fan syntax. Hardcoding the K1C form here put SET_FAN_SPEED
    # FAN=side_fan into a K2 file — a command that machine does not have, which
    # would have errored out a 76-minute print. Ask machine.aux_fans().
    for _ln in machine.aux_fans(printer, aux):
        w(_ln)
    w("M82")
    w("G92 E0")
    x0, y0 = ring[0]
    w(f"G1 Z{press:.3f} F600")
    w(f"G0 F9000 X{max(6.0, x0 - 45.0):.3f} Y{max(6.0, y0 - 10.0):.3f}")
    w("G1 E25 F300                      ; stationary purge — pressure before motion")
    w(f"G1 F1200 X{x0:.3f} Y{y0:.3f} E37   ; prime ends where the loop begins")
    w("G92 E0")
    # STAMP THE MACHINE INTO THE FILE. validate.py cannot check bounds without
    # knowing which plate, and a filename is not a contract.
    # THE FILE MUST RECORD THE COMMAND THAT MADE IT. The belt that fixed the cleats
    # recorded neither --dish nor --rail, so which fix version was on the plate could
    # not be established from the artifact — in a project whose doctrine is measuring
    # the emitted file, that is a provenance hole. Now every file is reproducible from
    # its own header.
    w(f"; MATERIAL={material}")
    w("; ARGV: " + " ".join(_sys.argv))
    w(f"; PRINTER={printer}")
    w("; BODY_START")

    e = 0.0
    for k in range(layers):
        z = press + k * layer_h
        if k:
            # The loop is closed, so a new layer is a vertical step in place: no repositioning, no
            # seam, no reversal. Same reason the Moore curve stacks cleanly.
            e += layer_h * e_per_mm
            L.append(f"; --- layer {k+1} at Z{z:.2f}")
            L.append(f"G1 F{round(min(speed, 20)*60)} Z{z:.3f} E{e:.5f}")
            L.append(f"G1 F{f}")
        # cleat height for THIS layer: full at the belt edges, reduced by `dish` in the middle
        u = (k / max(1, layers - 1)) * 2.0 - 1.0          # -1 at one edge, +1 at the other
        # TENSION RAILS AT THE EDGES. Oleg: "the V parts of belt that suppose to catch ball, they
        # stretch to almost straight".
        #
        # The cause is structural, not cosmetic: a cleat is built by displacing the BELT LINE
        # outward, so the cleat's strands ARE the belt. Pull the belt taut and you are pulling on
        # the cleat itself — it straightens because nothing else is carrying the load.
        #
        # Since belt width is the Z axis, the outermost layers can be left cleat-free. They run dead
        # straight for the whole loop and take ALL the tension, so the cleated layers between them
        # are never loaded and cannot be pulled flat. The rails also give the ball two edges to sit
        # between, which is the same job the dish does.
        # RAMP THE CLEAT IN, DO NOT SWITCH IT ON.
        # This was a hard boolean, so h_k jumped 0 -> full cleat height between two adjacent layers:
        # measured 9.26mm of lateral displacement across one 0.6mm layer step on the shipped belt,
        # against a 1.2mm bead. 23% of that layer was extruded onto nothing, in TPU, and 22 further
        # layers stacked on the single bridged bead. pulley.py already ramps a 2.5mm step for
        # exactly this reason; the belt did not.
        _edge = 1.0 - 2.0 * rail / max(belt_w, 1e-6)
        if abs(u) >= _edge:
            h_k = 0.0
        else:
            # smoothstep from the rail boundary inward, so the cleat grows over many layers
            _t = (_edge - abs(u)) / max(_edge, 1e-6)
            _ramp = _t * _t * (3.0 - 2.0 * _t)
            h_k = _ramp * max(0.0, cleat_h - dish * (1.0 - u * u))
        ring = add_cleats(base_ring, per, n_cleats, h_k, cleat_w,
                          centres=_fixed_centres)
        ring = [(p[0] + cx, p[1] + cy) for p in ring]
        px, py = ring[0]
        for (x, y) in ring[1:]:
            d = math.dist((px, py), (x, y))
            if d < 1e-9:
                continue
            e += d * (e_first if k == 0 else e_per_mm)
            L.append(f"G1 {'F%d ' % (f_first if k == 0 else f) if (px, py) == ring[0] else ''}"
                     f"X{x:.3f} Y{y:.3f} Z{z:.3f} E{e:.5f}")
            px, py = x, y

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{press + belt_w + 40:.1f} F900",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(flow=round(flow, 1), per=round(per), layers=layers, grams=round(grams, 1),
                                     speed=round(speed),
                                     mins=round(e / e_per_mm / speed / 60, 1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--centres", type=float, default=150.0, help="pulley centre distance mm")
    ap.add_argument("--pulley-d", type=float, default=40.0)
    ap.add_argument("--belt-w", type=float, default=25.0, help="belt width mm (= print height)")
    ap.add_argument("--cleats", type=int, default=12)
    ap.add_argument("--cleat-h", type=float, default=10.0, help="how far a cleat stands proud mm")
    ap.add_argument("--cleat-w", type=float, default=14.0, help="cleat footprint along the belt mm")
    ap.add_argument("--rail", type=float, default=3.0,
                    help="cleat-free tension rail at each belt edge, mm")
    ap.add_argument("--dish", type=float, default=2.0,
                    help="cradle depth across the belt width — 0 = flat cleats")
    ap.add_argument("--ring-w", type=float, default=20.0, help="width of the flat ring on the plate")
    ap.add_argument("--bead-w", type=float, default=1.2)
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--temp", type=int, default=machine.TEMP)
    ap.add_argument("--bed", type=int, default=0,
                    help="0 = machine.BED_TEMP for the material; 120 WELDS TPU")
    ap.add_argument("--press", type=float, default=0.10, help="base-layer gap — pressed")
    ap.add_argument("--first-w", type=float, default=3.0)
    ap.add_argument("--aux", type=float, default=0.2)
    ap.add_argument("--fan", type=int, default=0)
    ap.add_argument("--walls", type=int, default=1)
    ap.add_argument("--fold", type=int, default=0,
                    help="Moore-curve order to fold the belt into the plate (0 = plain ring)")
    ap.add_argument("--margin", type=float, default=12.0)
    ap.add_argument("--material", default="pla",
                    choices=["pla","petg","tpu","abs"],
                    help="stamped into the file; TPU is fan-guarded")
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    bxy = machine.BED[a.printer]

    # The loop must wrap two pulleys: two straights plus one full pulley circumference.
    loop = 2 * a.centres + math.pi * a.pulley_d
    # Solve the flat stadium's straight length so its centreline perimeter equals that loop.
    length = (loop - math.pi * a.ring_w) / 2.0
    if length <= 0:
        raise SystemExit(f"loop {loop:.0f}mm is too short for a {a.ring_w}mm ring — "
                         f"reduce --ring-w below {loop/math.pi:.0f}mm.")

    # The cleats stand proud of the curve, so the FOLD has to be inset by the cleat
    # height as well as the margin — otherwise the guard rejects a belt whose curve fits
    # fine and whose cleats do not, and the error blames the length.
    span = min(bxy) - 2 * (a.margin + (a.cleat_h if a.fold else 0.0))
    if a.fold:
        pitch = span / (2 ** (a.fold + 1) - 1)
        if pitch < 2 * a.cleat_h + a.bead_w + 2:
            raise SystemExit(
                f"fold order {a.fold} gives a {pitch:.1f}mm channel, but a {a.cleat_h}mm cleat needs "
                f"{2*a.cleat_h + a.bead_w + 2:.1f}mm — the cleats would print into the neighbouring "
                f"run. Lower --fold or --cleat-h.")
    g, st = emit(length, a.ring_w, a.belt_w, a.cleats, a.cleat_h, a.cleat_w, a.bead_w, a.layer_h,
                 a.flow, a.temp, a.bed or machine.BED_TEMP[a.material], 1.75, bxy, not a.no_home, a.press, a.fan, a.walls,
                 a.fold, span, a.first_w, a.aux, a.printer, a.dish, a.rail,
                 a.material)
    os.makedirs(a.out, exist_ok=True)
    fn = (f"{a.out}/belt_{a.printer}_c{a.centres:.0f}_p{a.pulley_d:.0f}_"
          f"w{a.belt_w:.0f}_{a.cleats}cleat_T{a.temp}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")
    print(f"  loop {loop:.0f}mm (centres {a.centres:.0f} + pulley {a.pulley_d:.0f}) -> "
          f"flat stadium {length:.0f} x {a.ring_w:.0f}mm, measured perimeter {st['per']}mm")
    print(f"  {a.cleats} cleats {a.cleat_h}mm proud, one every {loop/a.cleats:.0f}mm of belt")
    print(f"  {st['layers']} layers x {a.layer_h} = {a.belt_w}mm belt width")
    print(f"  {st['speed']} mm/s at flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g")
