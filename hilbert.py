#!/usr/bin/env python3
"""MOORE CURVE — a closed space-filling loop, one continuous extrusion, stacked.

Oleg: "or you can just go for other shapes that can accommodate continuous move like hilbert".

This replaces the honeycomb for area-filling work, and it is not a workaround -- it is the shape
the constraint was asking for all along:

  · A hex lattice has NO Eulerian circuit (every interior vertex is degree 3), so drawing it as one
    stroke means walking cells individually, overprinting shared walls, and closing the path with a
    straight chord back to the start -- the visible straight artifact Oleg spotted in the print.
  · A Hilbert curve is a single non-self-intersecting stroke by construction. A MOORE curve is the
    closed variant: it ends where it begins. So there is no chord, no seam, and no travel anywhere.
  · Because it is closed, every stacked layer walks the SAME loop in the SAME direction. No reversal
    at the layer change -- which is what forced the honeycomb into a closed-loop rewrite anyway.
  · Order n covers a 2^n x 2^n grid, so n -> n+1 is exactly 4x the cells. Oleg asked for "4x
    honeycomb cells"; here that is a single increment.

The only corners are 90 degrees, all of them identical, and round_corners turns them into arcs that
hold full speed. Nothing else in the path bends at all.
"""
import argparse
import math
import os

import sys as _sys

import machine

# Moore curve L-system. L and R are the two chiralities of a Hilbert sub-curve; the axiom glues four
# of them into a ring, which is what makes the whole thing closed.
AXIOM = "LFL+F+LFL"
RULES = {"L": "-RF+LFL+FR-", "R": "+LF-RFR-FL+"}
# Hilbert, for when an open path is wanted instead (--open)
H_AXIOM = "A"
H_RULES = {"A": "-BF+AFA+FB-", "B": "+AF-BFB-FA+"}


def lsystem(axiom, rules, order):
    s = axiom
    for _ in range(order):
        s = "".join(rules.get(c, c) for c in s)
    return s


def turtle(s, step):
    """Walk the L-system string. + is a left turn, - a right turn, F a unit move."""
    x = y = 0.0
    dx, dy = 0.0, 1.0
    pts = [(x, y)]
    for c in s:
        if c == "F":
            x += dx * step
            y += dy * step
            pts.append((x, y))
        elif c == "+":
            dx, dy = -dy, dx
        elif c == "-":
            dx, dy = dy, -dx
    return pts


def curve(order, span, closed=True):
    """Points for a Moore (closed) or Hilbert (open) curve fitted into a `span` mm square."""
    # GRID SIZE IS MEASURED, NOT ASSUMED. The Moore axiom "LFL+F+LFL" already contains four
    # sub-curves plus the connecting moves, so order n covers a 2^(n+1) grid, not 2^n -- assuming
    # 2^n scaled a requested 100mm square to 233mm. The open Hilbert axiom is a single sub-curve
    # and does cover 2^n.
    if closed:
        s = lsystem(AXIOM, RULES, order)
        n = 2 ** (order + 1)
    else:
        s = lsystem(H_AXIOM, H_RULES, order)
        n = 2 ** order
    step = span / (n - 1)
    pts = turtle(s, step)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ox, oy = min(xs), min(ys)
    pts = [(p[0] - ox, p[1] - oy) for p in pts]
    if closed and math.dist(pts[0], pts[-1]) > 1e-6:
        pts.append(pts[0])
    return pts


def round_corners(pts, fillet, seg=0.8):
    """Replace every sharp vertex with a tangent curve.

    NO SHARP TURNS is a project rule and also physics: Klipper decelerates to square_corner_velocity
    (5 mm/s) at a hard corner, and since E is metered per mm of PATH the flow does not brake with
    it -- every corner is a pressure spike into a stalled head. A Moore curve is ALL 90-degree
    corners, so this is not a polish step, it is what makes the shape printable at speed.

    Quadratic Bezier through each vertex is C1-continuous, so heading never jumps. Holding speed v
    needs radius >= v^2/accel; at 41 mm/s and 5000 mm/s^2 that is 0.34mm, so even a small fillet
    keeps full speed. Sampling is bounded by ANGLE, not length: cutting a corner back and then
    splitting it into two steps leaves 45-degree jumps that measure as sharp.
    """
    if fillet <= 0 or len(pts) < 3:
        return pts
    closed = math.dist(pts[0], pts[-1]) < 1e-6
    ded = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, ded[-1]) > 1e-9:
            ded.append(p)
    pts = ded
    if closed:
        core = pts[:-1]
        idx = [(core[i - 1], core[i], core[(i + 1) % len(core)]) for i in range(len(core))]
        out = []
    else:
        idx = [(pts[i - 1], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)]
        out = [pts[0]]
    for a, v, c in idx:
        la = math.dist(a, v)
        lc = math.dist(v, c)
        if la < 1e-9 or lc < 1e-9:
            continue
        d = min(fillet, la / 2, lc / 2)
        p1 = (v[0] + (a[0] - v[0]) * d / la, v[1] + (a[1] - v[1]) * d / la)
        p2 = (v[0] + (c[0] - v[0]) * d / lc, v[1] + (c[1] - v[1]) * d / lc)
        _c = max(-1.0, min(1.0, ((a[0] - v[0]) * (c[0] - v[0]) + (a[1] - v[1]) * (c[1] - v[1]))
                           / (la * lc)))
        turn = 180.0 - math.degrees(math.acos(_c))
        n = max(4, int(math.ceil(2 * d / seg)), int(math.ceil(turn / 6.0)))
        for k in range(n + 1):
            t = k / n
            m = (1 - t) ** 2
            out.append((m * p1[0] + 2 * (1 - t) * t * v[0] + t * t * p2[0],
                        m * p1[1] + 2 * (1 - t) * t * v[1] + t * t * p2[1]))
    out.append(out[0] if closed else pts[-1])
    return out


def offset_closed(pts, d):
    """Offset a closed polyline by d (positive = outward, using the local normal).

    Used to turn one wall into a two-walled SLOT for the stacking joint. Safe here because the
    Moore curve's passes are a whole pitch apart (13.3mm at order 3) and the fillet radii are much
    larger than the offset, so nothing folds back on itself -- but the caller checks that rather
    than trusting it.
    """
    core = pts[:-1] if math.dist(pts[0], pts[-1]) < 1e-9 else pts[:]
    n = len(core)
    out = []
    for i in range(n):
        a, b = core[i - 1], core[(i + 1) % n]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty)
        if L < 1e-12:
            out.append(core[i])
            continue
        out.append((core[i][0] + (ty / L) * d, core[i][1] - (tx / L) * d))
    out.append(out[0])
    return out


def joint_layers(pts, layers, bead_w, tenon_n, mortise_n, slot_gap, wall_n):
    """Per-layer (points, bead width) for a stackable module.

    Oleg: "we need to make it connectable, will go may be few meters high".

    BOTTOM `mortise_n` layers: two walls offset either side of the path, leaving a slot.
    TOP    `tenon_n`   layers: one NARROW centred wall that drops into the slot above.
    Middle layers: the plain single wall.

    The slot is modelled WIDER than the tenon because a printed gap comes out about 0.25mm tighter
    than modelled on these machines -- a measured empiric from this project, not a guess. Modelling
    it nominally would produce a joint that cannot be assembled at all.
    """
    tenon_w = bead_w * 0.6
    half = (slot_gap + wall_n) / 2.0
    plan = []
    for k in range(layers):
        if k < mortise_n:
            plan.append(("mortise", offset_closed(pts, +half), wall_n))
            plan.append(("mortise2", offset_closed(pts, -half), wall_n))
        elif k >= layers - tenon_n:
            plan.append(("tenon", pts, tenon_w))
        else:
            plan.append(("body", pts, bead_w))
    return plan


def emit(order, span, bead_w, bead_h, flow, temp, bed, fil_d, bed_xy, home, press, fan,
         fillet, layers, closed, printer='k1c', aux=0.2, material='pla',
         tile=1, gap=6.0, mix=(), first_h=0.0, first_w=0.0, layer_z=0.0, fuse_ok=False):
    area = math.pi * (fil_d / 2) ** 2
    # COMMANDED CROSS-SECTION vs Z STEP — deliberately decoupled.
    # Oleg: "you can do line width 10mm to compensate for the flow... we know it is not going to
    # make 10mm, but it will extrude enough" and "its fine to violate max nozzle recommended
    # settings". Commanding a very wide bead buys material per mm, which lets the head crawl while
    # the flow target is still met. What it does NOT buy is a 10mm-wide line: the plastic lands
    # somewhere narrower and correspondingly TALLER (measured on this machine: a commanded 2.0mm
    # landed 1.53 wide and 1.573 tall — cross-section conserved, shape not).
    # So the Z step must be set to what LANDS, not what was commanded, or the nozzle ploughs the
    # layer it just laid. --layer-z sets it independently; bead_h alone still meters E.
    e_per_mm = (bead_w * bead_h) / area
    # QUANTISED TO THE 3 DECIMALS Z IS ACTUALLY WRITTEN AT. The ladder is emitted as Z{z:.3f}, so a
    # z_step carrying more precision than that produces printed steps that differ from the declared
    # LAYER_H by a rounding crumb — and R2 compares the two. Round once, here, and the file agrees
    # with its own stamp by construction.
    z_step = round(layer_z or bead_h, 3)
    # SPEED IS THE FREE VARIABLE. 50 IS WHERE IT STARTS, NOT WHERE IT IS STUCK.
    # Oleg, 2026-07-27, correcting the previous version of this block: "speed is not fixed - 50 is
    # north star default unless overruled by other constraints."
    #
    # It had been written as `speed = machine.CONSTANT_SPEED`, an immovable 50, with flow solved
    # from it. That is a different and worse rule, and it broke the two things this generator exists
    # to do:
    #   · THE WIDE-BEAD TRICK. Oleg: "you can do line width 10mm to compensate for the flow ... we
    #     know it is not going to make 10mm, but it will extrude enough". The whole point is that a
    #     fat commanded bead buys material per MILLIMETRE so the head CRAWLS and still lands the flow
    #     target. Pinned at 50 the same command means 10 x 0.6 x 50 = 300 mm3/s, so it was REFUSED —
    #     the trick inverted into an error message. 7 of the archived commands in out/ stopped
    #     running.
    #   · TPU. Working flow 15.2 mm3/s. At a pinned 50 that needs a 0.51mm bead, narrower than the
    #     0.8 nozzle, so the generator announced that TPU "cannot be run ... at all on this hotend".
    #     It runs fine: at the normal 1.2x0.6 bead it simply moves at 21 mm/s. An over-strict rule of
    #     mine had been promoted into a claim about the material.
    #
    # What R3 actually requires is ONE speed WITHIN a print, so material per mm does not change where
    # the geometry is tightest. machine.speed_for_flow gives that one speed: the north star unless
    # the bead or the material pulls it down, never above.
    flow_target = flow
    speed = machine.speed_for_flow(flow_target, bead_w, bead_h)
    flow = speed * bead_w * bead_h          # what this file will actually DELIVER, per move
    f = round(speed * 60)
    _want_speed = flow_target / (bead_w * bead_h)
    if flow < flow_target - 0.05:
        # The bead is too THIN to carry the target at the north star. Speed cannot go up to fix it
        # (50 is the ceiling), so the honest report is the reduced flow plus the bead that closes it.
        print(f"  ! --flow {flow_target:g} mm3/s would need {_want_speed:.0f} mm/s at a "
              f"{bead_w:g}x{bead_h:g} bead, above the {machine.DEFAULT_SPEED:g} mm/s north star — "
              f"delivering {flow:.1f} at {speed:g} mm/s. Widen the bead to close it: --bead-w "
              f"{machine.bead_for_flow(flow_target, bead_h):.2f}.")
    elif speed < machine.DEFAULT_SPEED - 0.05:
        print(f"  ~ {bead_w:g}x{bead_h:g} = {bead_w*bead_h:.2f}mm2 at {flow_target:g} mm3/s runs at "
              f"{speed:.1f} mm/s, under the {machine.DEFAULT_SPEED:g} north star — the bead asks for "
              f"it. That is the wide-bead crawl working, not a violation: one speed, just a lower one.")
    # THE MATERIAL CEILING LANDS ON THE SPEED, NOT ON THE BEAD. __main__ already routes --flow
    # through machine.flow_for, so this only bites when emit() is called directly; keep it anyway,
    # because a delivered flow past the material's measured ceiling is a physical fact, not a policy.
    # Narrowing the bead would return a lattice instead of the fused sheet that was asked for —
    # the bead IS the part. Speed is only the clock, so the clock is what moves.
    _mcap = machine.MATERIAL_FLOW.get(material, machine.FLOW)
    if flow > _mcap + 1e-9:
        _over = flow
        speed = machine.speed_for_flow(_mcap, bead_w, bead_h)
        flow = speed * bead_w * bead_h
        f = round(speed * 60)
        print(f"  ! a {bead_w:g}x{bead_h:g} bead was about to deliver {_over:.0f} mm3/s; "
              f"{material}'s measured ceiling is {_mcap:g} — running {speed:.1f} mm/s for "
              f"{flow:.1f} mm3/s. Bead unchanged; deposit per mm is unchanged.")

    # Every order that will appear on the plate must clear the fuse check, not just the default.
    orders = list(mix) if mix else [order]
    for o in orders:
        n_o = (2 ** (o + 1)) if closed else (2 ** o)
        p_o = span / (n_o - 1)
        # LANDED width, not commanded. Oleg deliberately commands a bead far past the nozzle to buy
        # material per mm at a crawling head speed — "we know it is not going to make 10mm, but it
        # will extrude enough". What lands is the cross-section divided by the Z step.
        _landed = (bead_w * bead_h) / (layer_z or bead_h)
        if p_o < _landed * 1.6:
            _msg = (f"order {o} over {span:.0f}mm gives a {p_o:.2f}mm pitch. Commanding "
                    f"{bead_w}mm wide at a {(layer_z or bead_h):.2f}mm Z step lands about "
                    f"{_landed:.2f}mm wide, so neighbouring passes will FUSE "
                    f"(pitch >= {_landed*1.6:.2f}mm keeps them open).")
            if not fuse_ok:
                raise SystemExit(_msg + "\n  Pass --fuse-ok if merging the cells is the intent.")
            print(f"  ! {_msg}\n    --fuse-ok: printing anyway, cells will merge — deliberate.")
    n = (2 ** (order + 1)) if closed else (2 ** order)
    pitch = span / (n - 1)
    # LAYER 1: PRESSED TO THE PLATE. SAME BEAD, SAME FLOW, SAME SPEED — ONLY Z CHANGES.
    # Oleg, 2026-07-27: "omg why you killed first layer flow!!!!!!! flow must be constant", and
    # "the nozel need to be 0,1 to board. we need adhesion".
    #
    # What stood here modelled layer 1 as its OWN bead: a width solved from flow_target/first_speed
    # (13.0mm at the defaults) laid at 0.1mm, i.e. 1.10mm2 against the body's 0.72. Measured on the
    # emitted file that is +53% on every move of the layer, and R4 fails it from one side or the
    # other whichever of the two numbers the header declares. Two rates in a file IS the violation.
    #
    # The width compensation was not wrong when it was written — it existed because layer 1 CRAWLED
    # while the body ran fast, so the cross-section had to grow to keep the flow up. There is only
    # ONE speed in the file now (it may be a crawl, but the body crawls with it), so there is nothing
    # left to compensate for and the compensation is pure over-extrusion.
    #
    # The body's 0.72mm2 forced through a 0.1mm gap does not vanish, it SPREADS — about
    # bead_w*bead_h/PRESS_HARD wide — and that squished footprint IS the adhesion. The lattice cells
    # still fuse into a solid raft on layer 1, which is what was wanted; it now happens at the same
    # flow as everything else rather than at a second, higher one.
    #
    # R1 IS NOT AN ARGUMENT. --press and --first-h are kept so archived commands still run, but the
    # first layer is laid at machine.PRESS_HARD whatever they say, and the file says so out loud.
    if press and abs(press - machine.PRESS_HARD) > 1e-9:
        print(f"  ~ --press {press:g} ignored: layer 1 is laid at machine.PRESS_HARD "
              f"({machine.PRESS_HARD:g}) — R1, adhesion comes from the press.")
    if first_h and abs(first_h - machine.PRESS_HARD) > 1e-9:
        print(f"  ~ --first-h {first_h:g} ignored: layer 1 is laid at machine.PRESS_HARD "
              f"({machine.PRESS_HARD:g}) — R1.")
    first_h = machine.PRESS_HARD
    first_speed = speed
    first_area = bead_w * bead_h
    if first_w and abs(first_w - first_area / first_h) > 1e-9:
        print(f"  ~ --first-w {first_w:g} ignored: flow is constant (R4), so layer 1 commands the "
              f"body's {first_area:.2f}mm2 and spreads to ~{first_area/first_h:.1f}mm at "
              f"{machine.PRESS_HARD:g}mm.")
    first_w = first_area / first_h      # what it SPREADS to, not a second commanded bead
    e_first_mm = e_per_mm

    # THE MOVE-RATE CEILING IS A FUNCTION OF THE SPEED ACTUALLY RESOLVED, NOT OF THE NORTH STAR.
    # round_corners samples every 90-degree corner by ANGLE (6 deg per point), so a small-span, high
    # -order lattice emits sub-0.2mm segments. At 50 mm/s that is a real hazard — replaying the
    # archived commands caught moore_k2plus_o3_40mm_L17 asking for 380 moves/s against
    # machine.MAX_MOVES_PER_SEC=300, the rate at which Klipper drains its lookahead and the head
    # FREEZES with no error to read. At a wide-bead crawl of 9 mm/s the same geometry asks for a
    # sixth of that, so deriving the floor from a hardcoded 50 would throw away detail the machine
    # can execute perfectly well.
    # The threshold is derived, not chosen — a segment shorter than speed/MAX_MOVES_PER_SEC cannot
    # be executed at this speed, so it is not geometry, it is a request the host cannot serve.
    # machine.decimate exists for exactly this and keeps endpoints, so closed loops stay closed.
    # 1.2x margin because the rate is measured over a 24-move window, not per segment.
    # If the duration clamp below lowers the speed further, this floor was merely CONSERVATIVE —
    # it dropped points the machine could have run, which costs detail, never safety.
    _min_seg = speed / machine.MAX_MOVES_PER_SEC * 1.2
    shapes = [machine.decimate(round_corners(curve(o, span, closed), fillet), _min_seg)
              for o in orders]
    pts = shapes[0]

    # TILE THE WHOLE PLATE. Oleg: "use entire area to print everything needed not a tiny thing".
    # Copies are joined by a THIN LINK at reduced flow rather than a travel — the same trick
    # solid.py uses between contours. It keeps the no-travel rule, and the link snaps off.
    if tile > 1:
        step = span + gap
        need = tile * step - gap
        if need + 2 * 6 > min(bed_xy):
            raise SystemExit(f"{tile}x{tile} tiles of {span:.0f}mm need {need:.0f}mm — "
                             f"a {min(bed_xy):.0f}mm plate holds "
                             f"{int((min(bed_xy)-12+gap)//step)}.")
        grid = []
        for r in range(tile):
            cols = range(tile) if r % 2 == 0 else range(tile - 1, -1, -1)
            for c in cols:
                grid.append([(p[0] + c * step, p[1] + r * step) for p in pts])
        pts = grid          # a LIST OF LOOPS from here on
    else:
        pts = [pts]
    _allx = [p[0] for lp in pts for p in lp]; _ally = [p[1] for lp in pts for p in lp]
    ox = (bed_xy[0] - (max(_allx) + min(_allx))) / 2.0
    oy = (bed_xy[1] - (max(_ally) + min(_ally))) / 2.0
    pts = [[(p[0] + ox, p[1] + oy) for p in lp] for lp in pts]
    xs = [p[0] for lp in pts for p in lp]
    ys = [p[1] for lp in pts for p in lp]
    if min(xs) < 4 or min(ys) < 4 or max(xs) > bed_xy[0] - 4 or max(ys) > bed_xy[1] - 4:
        raise SystemExit(f"curve spans X {min(xs):.0f}..{max(xs):.0f} Y {min(ys):.0f}..{max(ys):.0f} "
                         f"on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} bed — off the plate.")

    # A FLOW CEILING BELONGS TO A DURATION — and this generator is the one that proved it.
    # The order-5 Moore lattice stalled the K2's extruder driver 16 minutes into layer 1 on
    # 2026-07-26 (machine.SUSTAINED_FLOW carries the firmware log). Path length is known EXACTLY
    # here, so the duration comes off the real geometry rather than being back-solved from
    # filament the way the `mins` estimate does it. Lowering speed at a FIXED cross-section lowers
    # the rate and nothing else: E is per mm, so the part is unchanged to the microgram.
    _len1 = sum(math.dist(lp[i - 1], lp[i]) for lp in pts for i in range(1, len(lp)))
    # ONE FLOW, ONE DURATION. This asked twice — once for layer 1, once for the body — because the
    # two used to run at different rates. They do not any more, and asking twice about one number is
    # how a file ends up with two.
    # IT ALSO NEVER PASSED `material`, so flow_for_duration defaulted to "pla" and measured a
    # pla-matte part against PLA's 55 mm3/s figure — a number that does not belong to it.
    # THE CLAMP LANDS ON THE SPEED, WHICH IS EXACTLY WHERE IT BELONGS. flow_for_duration's own
    # advice is "deposit per mm is unchanged; only the clock moves", and that is true precisely
    # because E is metered per MILLIMETRE: slowing the head lowers the extruder's duty cycle and
    # changes not one microgram of the part. The previous version refused instead, on the grounds
    # that speed was fixed — so it protected a rule Oleg had not made at the cost of the part.
    # It stays ONE speed for the whole file; it is simply a lower one, which R3 allows.
    _mins_all = _len1 * layers / speed / 60.0
    _fc = machine.flow_for_duration(flow, _mins_all, " for this part", material)
    if _fc < flow - 1e-9:
        speed = machine.speed_for_flow(_fc, bead_w, bead_h)
        flow = speed * bead_w * bead_h
        f = round(speed * 60)
        first_speed = speed
        _mins_all = _len1 * layers / speed / 60.0
        print(f"  ~ holding {_fc:g} mm3/s with a {bead_w:g}x{bead_h:g} bead means {speed:.1f} mm/s "
              f"for the whole file (~{_mins_all:.0f} min). Bead, path and grams are identical; only "
              f"the clock moves.")

    L = []
    w = L.append
    kind = "MOORE (closed)" if closed else "HILBERT (open)"
    w(f"; {kind} curve order {order} — one continuous extrusion, {n}x{n} grid = {n*n} cells")
    # THE STAMPS validate.py READS, AND A MISSING ONE IS ITSELF A FAILURE (RULES.md).
    # They sit at the very top because the validator only reads the first 4000 characters for
    # LAYER_H, and stops at BODY_START for MATERIAL — a stamp further down is a stamp that is not
    # there. This file carried MATERIAL and PRINTER but neither LAYER_H nor FLOW, so R2 and R4
    # SILENTLY SKIPPED on every hilbert file ever produced: they reported nothing, which reads
    # exactly like passing.
    w(f"; PRINTER={printer}")
    w(f"; MATERIAL={material}")
    # LAYER_H IS THE Z STEP, NOT bead_h. R2 checks the emitted Z ladder against this, and the ladder
    # rises by z_step. bead_h only meters E; --layer-z is what the bead actually LANDS at and is
    # what the part grows by, so it is the layer height in every sense R2 cares about.
    w(f"; LAYER_H={z_step:.3f}")
    # ONE FLOW FOR THE WHOLE FILE. There used to be two lines here declaring two numbers, with a
    # comment explaining that layer 1 is "a different bead at a different speed" — which is the
    # violation, not a caveat about it. R4 checks every extruding move against this single figure.
    #
    # AND IT IS THE DELIVERED FLOW, NOT THE REQUESTED ONE. `flow` here is bead_w * bead_h * speed
    # at the speed this file actually resolved to — the same arithmetic validate.py re-derives from
    # the emitted G1 lines. Declaring the --flow that was ASKED for would be an aspiration stamped
    # as a measurement, which is the defect this project keeps catching in itself.
    w(f"; FLOW={flow:.2f}")
    _der = machine.flow_derate_stamp(material, printer, flow)
    if _der:
        w(_der)   # R8: slow is allowed, silent slow is not
        print("  " + _der.lstrip("; "))
    w(f"; SPEED={speed:.2f}   ; one speed, the north star ({machine.DEFAULT_SPEED:g}) unless the "
      f"bead or the material pulled it down")
    w(f"; bead {bead_w:.2f}x{bead_h:g} = {bead_w*bead_h:.2f}mm2 at {speed:.1f} mm/s "
      f"-> flow={flow:.1f} mm3/s, layer 1 included")
    w(f"; layer 1: same {first_area:.2f}mm2 laid at Z{first_h:.2f} (machine.PRESS_HARD) — spreads to "
      f"~{first_w:.1f}mm wide, fan OFF")
    w(f"; {span:.0f}mm square, {pitch:.2f}mm pitch, {layers} layers, Z step {z_step:.3f}mm, "
      f"body bead {bead_w:.2f}x{bead_h:g}")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {layers}")
    w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}")
    w(f"M104 S{temp}")
    w("G90")
    w("G28" if home else "; NO HOME — assumes the machine is ALREADY homed; push.py verifies")
    # M190 only waits for HEATING; if the bed is hotter than target it returns instantly and
    # the part prints on a plate left hot by the previous job. TEMPERATURE_WAIT blocks both ways.
    # SENSOR NAME UNQUOTED — Klipper does not match the QUOTED form and skips the wait
    # SILENTLY (empirical: a 100C-floor part started at 78C; bucket.py hit the same bug).
    w(f"TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM={machine.bed_start(material, bed)} MAXIMUM={bed+5}")
    w(f"M109 S{temp}")
    w("M204 S8000")
    # LAYER 1 PRINTS WITH THE FAN OFF, whatever was asked for. Its job is to weld to the plate.
    # The requested fan is clamped to what the material tolerates and switched on at layer 2.
    _fan_frac = machine.fan_for(material, (fan or 0) / 255.0)
    _fan_body = int(round(_fan_frac * 255))
    _fan_l1 = int(round(machine.fan_first_layer(material) * 255))
    w(f"M106 S{_fan_l1}" if _fan_l1 else
      "M107                              ; layer 1: no part cooling, let it bond")
    # AUX FANS — hilbert/honeycomb/waves never set these at all, so every pad and lattice
    # printed with the chamber fans OFF while belt/pulley/solid/flowtest set them. Oleg
    # spotted it on the machine: "i noticed fans on 0, what the heck!?"
    for _ln in machine.aux_fans(printer, machine.aux_for(material, aux)):
        w(_ln)
    w("M82")
    w("G92 E0")
    x0, y0 = pts[0][0]
    w(f"G1 Z{first_h:.3f} F600")   # prime at the first-layer height, not the body press
    _apx = max(6.0, x0 - 55.0)
    _apy = max(6.0, y0 - 12.0)
    w(f"G0 F9000 X{_apx:.3f} Y{_apy:.3f}")
    w("G1 E25 F300                      ; PRIME purge, stationary — pressure before motion")
    # THE ONE LICENSED EXCEPTION TO R3, AND IT IS IDENTIFIED BY ITS NAME, NOT BY BEING SLOW
    # (RULES.md). This line is laid off the part before the object starts; "PRIME" in the comment is
    # what exempts it. Nothing else in this file may carry that word.
    w(f"G1 F1200 X{x0:.3f} Y{y0:.3f} E37   ; PRIME line — ends where the curve begins")
    w("G92 E0")
    # THE FILE MUST RECORD THE COMMAND THAT MADE IT. The belt that fixed the cleats
    # recorded neither --dish nor --rail, so which fix version was on the plate could
    # not be established from the artifact — in a project whose doctrine is measuring
    # the emitted file, that is a provenance hole. Now every file is reproducible from
    # its own header. (PRINTER/MATERIAL/LAYER_H/FLOW are stamped at the top, where the
    # validator actually looks for them.)
    w("; ARGV: " + " ".join(_sys.argv))
    w("; BODY_START")
    w(f"G1 F{round(first_speed*60)}                 ; ONE speed — every move, layer 1 included")

    e = 0.0
    for k in range(layers):
        z = first_h + k * z_step
        if k:
            # A closed curve ends where it starts, so the next layer needs nothing but a vertical
            # step -- no repositioning, no reversal, no seam artifact. This is the whole reason the
            # closed form was chosen over an open Hilbert.
            e += z_step * e_per_mm
            L.append(f"; --- layer {k+1} at Z{z:.2f} — closed loop, straight up, same direction")
            if k == 1:
                L.append("M107" if not _fan_body else f"M106 S{_fan_body}   ; part cooling from layer 2")
            L.append(f"G1 F{round(min(speed, 20)*60)} Z{z:.3f} E{e:.5f}")
            L.append(f"G1 F{f}")   # body rate from layer 2 onward
        # DO NOT PRETEND THE HEAD WENT BACK TO THE START.
        # This reset px,py to the FIRST tile's first point at every layer, but with --tile the head
        # physically finished at the LAST tile's end. The zero-length first move was then skipped
        # and the next move became a 389.8mm diagonal ACROSS THE WHOLE PLATE, metered as if it were
        # 0.8mm — an extruding move dragged over every finished tile, once per layer. Measured on
        # moore_k2plus_o1_40mm_L5: head at (313.7, 293.0), next commanded point (38.5, 17.0).
        # The position now carries across the layer change, so that move is metered for what it is.
        if k == 0:
            px, py = pts[0][0]
        # SERPENTINE THE TILES BETWEEN LAYERS, not just within one.
        # The tile grid already snakes left-right-left within a layer, so a layer ENDS at the far
        # corner while the next one began at the near corner — a real 389.8mm move across every
        # finished tile, once per layer. Walking the tiles in the opposite order on alternate
        # layers means each layer starts in the tile the previous one just finished.
        _order = pts if (k % 2 == 0) else pts[::-1]
        for li, loop in enumerate(_order):
            for pi, (x, y) in enumerate(loop):
                d = math.dist((px, py), (x, y))
                if d < 1e-9:
                    continue
                # THE LINK BETWEEN TILES RUNS AT FULL FLOW. It used to extrude at 0.3x so it would
                # snap off — 48 moves per layer at --tile 7, every one of them 70% under the
                # declared rate, which is R4 broken for the same reason a starved layer 1 breaks it.
                # validate.py already records the project's ruling on this exact trick, for
                # between-part moves: "a travel must suspend flow, not thin it". Thinning is not a
                # middle ground; a link either carries the bead or it is a dry, tagged hop.
                # CONSEQUENCE, stated because it changes the object: at --tile > 1 the copies are
                # now joined by a full-width bead and must be CUT apart, not snapped. If separate
                # parts matter more than the continuous stroke, the sanctioned alternative is a
                # lifted, unmetered '; HOP' (machine.NO_TRAVEL_RULE) — that is a design decision,
                # not a validator workaround, so it is left to the owner.
                e += d * (e_first_mm if k == 0 else e_per_mm)
                L.append(f"G1 {'F%d ' % (round(first_speed*60) if k == 0 else f) if (px, py) == pts[0][0] else ''}"
                         f"X{x:.3f} Y{y:.3f} Z{z:.3f} E{e:.5f}")
                px, py = x, y

    # THE PART'S HEIGHT IS THE Z STEP, NOT THE BEAD HEIGHT. These are deliberately decoupled here
    # (--layer-z sets what LANDS; bead_h only meters E), and the end-of-print lift used the wrong
    # one. With --bead-h 0.6 --layer-z 1.5 --layers 60 the part tops out at 88.6mm and the head
    # lifted to 75.5 — then travelled to park, driven 13.1mm THROUGH the finished object. Shipped
    # files escaped only because the +40mm of slack absorbs the error below about 45 layers, so it
    # would have surfaced first on the tallest print anyone ever ran.
    # THE PARK LIFT IS A DRY MOVE AND MUST BE WRITTEN AS ONE. Emitted as `G1 Z...` it looked like a
    # layer change to R2's ladder scan: on a 1-layer file the ladder read [0.100, 40.100] and the
    # 40mm park was reported as a Z step 66x the layer height. G0 is what a non-extruding rapid is,
    # the machine treats the two identically, and R2 then only ever sees real layer changes.
    L += ["M107", "M104 S0", "M140 S0",
          f"G0 Z{first_h + (layers-1)*z_step + 40:.1f} F900   ; park lift — dry, not a layer",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    # `pts` was rebound from a point list to a LIST OF LOOPS 150 lines above, so len() had been
    # reporting the tile count: "1 points" for a 14,957-point curve.
    # And `mins` used to back-solve path length out of filament (e / e_per_mm), which is blind to
    # travels and to a differently-metered layer 1 — it reported the whole print at the body speed.
    # Both quantities are now summed from the geometry that was actually emitted.
    _npts = sum(len(lp) for lp in pts)
    _mins = _len1 * layers / speed / 60.0     # one speed for the whole file now
    # SPEED IS REPORTED TO A DECIMAL. round() to the integer turned a 9.17 mm/s wide-bead crawl into
    # "9 mm/s", and 9 x 6.0 = 54 does not reconstruct the 55 mm3/s stamped two words later — a
    # summary line that disagrees with its own file is how a wrong number survives a read-through.
    return "\n".join(L) + "\n", dict(flow=round(flow, 1), pts=_npts, grams=round(grams, 1), speed=round(speed, 1),
                                     cells=n * n, pitch=round(pitch, 2),
                                     mins=round(_mins, 1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", type=int, default=4, help="curve order; n -> n+1 is 4x the cells")
    ap.add_argument("--span", type=float, default=0, help="square size mm (0 = fill the bed)")
    ap.add_argument("--margin", type=float, default=12.0, help="mm kept clear at the bed edge")
    ap.add_argument("--bead-w", type=float, default=machine.BEAD_W)
    ap.add_argument("--bead-h", type=float, default=machine.BEAD_H)
    ap.add_argument("--flow", type=float, default=0,
                    help="0 = the material's measured ceiling (PLA keeps the max-flow rule)")
    ap.add_argument("--temp", type=int, default=0,
                    help="0 = machine.temp_for(material). A PLA 210 default reached TPU in every generator.")
    ap.add_argument("--bed", type=int, default=0,
                    help="0 = machine.BED_TEMP[material] — PLA is maxed to the plate ceiling by standing rule")
    # --press AND --first-h ARE NO LONGER INPUTS, they are kept so archived commands still run.
    # Layer 1 is laid at machine.PRESS_HARD by rule (R1) and the generator says so when a command
    # asks for something else. The old default was 0.55 — a first layer half a millimetre off the
    # plate — which is exactly the file Oleg cancelled.
    ap.add_argument("--press", type=float, default=machine.PRESS_HARD,
                    help="IGNORED: layer 1 is machine.PRESS_HARD (R1). Kept for old commands.")
    ap.add_argument("--first-h", type=float, default=machine.PRESS_HARD,
                    help="IGNORED: layer 1 is machine.PRESS_HARD (R1). Kept for old commands.")
    ap.add_argument("--fuse-ok", action="store_true",
                    help="allow a bead wide enough to merge neighbouring cells")
    ap.add_argument("--layer-z", type=float, default=0.0,
                    help="Z step per layer. 0 = same as --bead-h. Set it to what the bead ACTUALLY "
                         "lands at when commanding a width far past the nozzle.")
    ap.add_argument("--first-w", type=float, default=0.0,
                    help="IGNORED: flow is constant (R4), so layer 1 commands the body bead and "
                         "lets it spread at the 0.1mm press. Kept for old commands.")
    ap.add_argument("--fan", type=int, default=0)
    ap.add_argument("--aux", type=float, default=0.2,
                    help="chamber/side fans 0-1")
    ap.add_argument("--fillet", type=float, default=0)
    ap.add_argument("--layers", type=int, default=1)
    ap.add_argument("--open", action="store_true", help="open Hilbert instead of closed Moore")
    ap.add_argument("--tile", type=int, default=1, help="NxN copies across the plate")
    ap.add_argument("--gap", type=float, default=6.0, help="mm between tiles")
    ap.add_argument("--material", default=machine.DEFAULT_MATERIAL,
                    choices=sorted(machine.MATERIAL_TEMP),
                    help="stamped into the file; TPU is fan-guarded")
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED),
                    help="picks the PRINTABLE plate size from machine.BED")
    ap.add_argument("--bed-size", default="", help="override WxY mm (rarely right)")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    # MATERIAL ROUTES THE NOZZLE AND THE FLOW TOO — see machine.MATERIAL_TEMP.
    a.temp = a.temp or machine.temp_for(a.material)
    a.flow = machine.flow_for(a.material, a.flow or machine.FLOW, ' for hilbert.py')
    machine.check_flow(a.flow, f' for hilbert.py')
    bxy = (tuple(float(v) for v in a.bed_size.split(",")) if a.bed_size
           else machine.BED[a.printer])
    span = a.span or (min(bxy) - 2 * a.margin)
    # Default the fillet to just under half the pitch: any larger and opposite corners of the same
    # cell would eat into each other and the grid stops reading as a grid.
    pitch = span / ((2 ** (a.order + 1) if not a.open else 2 ** a.order) - 1)
    fillet = a.fillet or max(0.8, pitch * 0.45)
    g, st = emit(a.order, span, a.bead_w, a.bead_h, a.flow, a.temp, a.bed or machine.bed_for(a.material, a.printer), 1.75, bxy,
                 not a.no_home, a.press, a.fan, fillet, a.layers, not a.open, a.printer, a.aux, a.material,
                 a.tile, a.gap, (), a.first_h, a.first_w, a.layer_z, a.fuse_ok)
    os.makedirs(a.out, exist_ok=True)
    tag = a.printer
    kind = "hilbert" if a.open else "moore"
    fn = f"{a.out}/{kind}_{tag}_o{a.order}_{span:.0f}mm_L{a.layers}_T{a.temp}.gcode"
    open(fn, "w").write(g)
    print(f"{fn}\n  order {a.order} -> {st['cells']} cells, {st['pitch']}mm pitch, "
          f"{span:.0f}mm square, fillet {fillet:.2f}mm, {st['pts']} points")
    print(f"  {st['speed']} mm/s at flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g, "
          f"{a.layers} layers, layer 1 pressed to {machine.PRESS_HARD}mm at the same flow")
