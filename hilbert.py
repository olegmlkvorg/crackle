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
    z_step = layer_z or bead_h
    # LAYER 1 IS NOT AS TALL AS THE OTHERS, SO IT MUST NOT BE FED LIKE THEM.
    # This metered every layer with the BODY cross-section (bead_w * bead_h) while printing layer 1
    # at Z=press. With press 0.30 and bead_h 0.60 that is exactly 2x over-extrusion on the one layer
    # that has to bond: 0.72mm2 of plastic commanded into a 0.30mm gap. The surplus has nowhere to
    # go but under the nozzle, which ploughs the print off the plate — reported as "bonding failed",
    # and the same mechanism that detached the foot on 2026-07-25.
    flow_target = flow
    speed = min(flow / (bead_w * bead_h), machine.MAX_SPEED)
    flow = speed * bead_w * bead_h
    f = round(speed * 60)

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
    # LAYER 1: 0.1mm OFF THE PLATE, FULL FLOW, WIDTH TAKES THE STRAIN.
    # Oleg, 2026-07-26: "first layer maintain same 55 flow but put nozzle 0.1 to the plate,
    # compensate with line width, set it to 10 if needed".
    #
    # I got this wrong once already by capping the width to keep the lattice cells open — which
    # silently cut the flow, which was the whole thing being protected. The flow target is the
    # constraint; the width is the free variable; the cells are not the priority on layer 1.
    #
    #   width 10.0 x height 0.1 = 1.00 mm2  ->  at 55 mm/s that is exactly 55 mm3/s
    #
    # The consequence is deliberate and worth stating: at a lattice pitch below the first-layer
    # width the base fuses into a SOLID SHEET. That is a raft the object grows out of, and it is
    # the strongest bed contact available.
    first_h = first_h or press
    # HOLD THE FLOW, LET THE WIDTH ABSORB IT. Oleg: "why you did not force max flow for the first
    # layer?!" — because I applied the speed cap as a FLOW cut, which is backwards. The first layer
    # wants BOTH: a crawling head (dwell, so it wets the plate) AND the full flow target (material,
    # so there is something to bond). Those are only compatible if the cross-section grows:
    #
    #     area = flow_target / first_speed      e.g. 55 / 20 = 2.75 mm2
    #     width = area / first_h                     2.75 / 0.1 = 27.5 mm commanded
    #
    # It will not land 27.5mm wide. It does not need to — the point is the material, and on a
    # lattice pitch far below that the first layer simply fuses into a solid raft, which is the
    # strongest bed contact available and exactly what "its fine to break the shape" permits.
    first_speed = min(machine.FIRST_LAYER_SPEED, machine.MAX_SPEED)
    if first_w > 0:
        first_area = first_w * first_h
        first_speed = min(flow_target / first_area, first_speed)
    else:
        first_area = flow_target / first_speed
        first_w = first_area / first_h
    e_first_mm = first_area / area

    shapes = [round_corners(curve(o, span, closed), fillet) for o in orders]
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

    L = []
    w = L.append
    kind = "MOORE (closed)" if closed else "HILBERT (open)"
    w(f"; {kind} curve order {order} — one continuous extrusion, {n}x{n} grid = {n*n} cells")
    # STATE BOTH FLOWS. Layer 1 is a different bead at a different speed, and a header that
    # declares one number makes the validator flag the other as an overrun.
    w(f"; bead {bead_w}x{bead_h} = {bead_w*bead_h:.2f}mm2 at {speed:.0f} mm/s -> flow={flow} mm3/s")
    w(f"; layer 1: {first_w:.1f}x{first_h} = {first_area:.2f}mm2 at {first_speed:.0f} mm/s "
      f"-> flow={first_area*first_speed:.1f} mm3/s, fan OFF")
    w(f"; {span:.0f}mm square, {pitch:.2f}mm pitch, {layers} layers, layer1 {first_h}mm x {first_w:.2f}mm wide, body bead {bead_w}x{bead_h}")
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
    # LAYER 1 PRINTS WITH THE FAN OFF, whatever was asked for. Its job is to weld to the plate.
    # The requested fan is clamped to what the material tolerates and switched on at layer 2.
    _fan_frac = machine.fan_for(material, (fan or 0) / 255.0)
    _fan_body = int(round(_fan_frac * 255))
    w("M107                              ; layer 1: no part cooling, let it bond")
    # AUX FANS — hilbert/honeycomb/waves never set these at all, so every pad and lattice
    # printed with the chamber fans OFF while belt/pulley/solid/flowtest set them. Oleg
    # spotted it on the machine: "i noticed fans on 0, what the heck!?"
    for _ln in machine.aux_fans(printer, aux):
        w(_ln)
    w("M82")
    w("G92 E0")
    x0, y0 = pts[0][0]
    w(f"G1 Z{first_h:.3f} F600")   # prime at the first-layer height, not the body press
    _apx = max(6.0, x0 - 55.0)
    _apy = max(6.0, y0 - 12.0)
    w(f"G0 F9000 X{_apx:.3f} Y{_apy:.3f}")
    w("G1 E25 F300                      ; stationary purge — pressure before motion")
    w(f"G1 F1200 X{x0:.3f} Y{y0:.3f} E37   ; prime ends where the curve begins")
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
    w(f"G1 F{round(first_speed*60)}                 ; layer 1 speed holds the flow target")

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
                # the hop between tiles extrudes THIN — continuous, but it snaps off
                thin = 0.3 if (pi == 0 and li > 0) else 1.0
                e += d * (e_first_mm if k == 0 else e_per_mm) * thin
                L.append(f"G1 {'F%d ' % (round(first_speed*60) if k == 0 else f) if (px, py) == pts[0][0] else ''}"
                         f"X{x:.3f} Y{y:.3f} Z{z:.3f} E{e:.5f}")
                px, py = x, y

    L += ["M107", "M104 S0", "M140 S0",
          f"G1 Z{first_h + (layers-1)*bead_h + 40:.1f} F900",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(flow=round(flow, 1), pts=len(pts), grams=round(grams, 1), speed=round(speed),
                                     cells=n * n, pitch=round(pitch, 2),
                                     mins=round(e / e_per_mm / speed / 60, 1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", type=int, default=4, help="curve order; n -> n+1 is 4x the cells")
    ap.add_argument("--span", type=float, default=0, help="square size mm (0 = fill the bed)")
    ap.add_argument("--margin", type=float, default=12.0, help="mm kept clear at the bed edge")
    ap.add_argument("--bead-w", type=float, default=machine.BEAD_W)
    ap.add_argument("--bead-h", type=float, default=machine.BEAD_H)
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--temp", type=int, default=machine.TEMP)
    ap.add_argument("--bed", type=int, default=0,
                    help="0 = machine.BED_TEMP[material] — PLA is maxed to the plate ceiling by standing rule")
    ap.add_argument("--press", type=float, default=0.55)
    ap.add_argument("--first-h", type=float, default=0.10,
                    help="layer-1 height — thin squashes it into the plate (default 0.10)")
    ap.add_argument("--fuse-ok", action="store_true",
                    help="allow a bead wide enough to merge neighbouring cells")
    ap.add_argument("--layer-z", type=float, default=0.0,
                    help="Z step per layer. 0 = same as --bead-h. Set it to what the bead ACTUALLY "
                         "lands at when commanding a width far past the nozzle.")
    ap.add_argument("--first-w", type=float, default=0.0,
                    help="layer-1 bead WIDTH; 0 = auto, wide enough to hold the body flow at "
                         "--first-h, capped at 0.62x the lattice pitch so cells stay open")
    ap.add_argument("--fan", type=int, default=0)
    ap.add_argument("--aux", type=float, default=0.2,
                    help="chamber/side fans 0-1")
    ap.add_argument("--fillet", type=float, default=0)
    ap.add_argument("--layers", type=int, default=1)
    ap.add_argument("--open", action="store_true", help="open Hilbert instead of closed Moore")
    ap.add_argument("--tile", type=int, default=1, help="NxN copies across the plate")
    ap.add_argument("--gap", type=float, default=6.0, help="mm between tiles")
    ap.add_argument("--material", default="pla",
                    choices=["pla","petg","tpu","abs"],
                    help="stamped into the file; TPU is fan-guarded")
    ap.add_argument("--printer", default="k1c", choices=sorted(machine.BED),
                    help="picks the PRINTABLE plate size from machine.BED")
    ap.add_argument("--bed-size", default="", help="override WxY mm (rarely right)")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
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
          f"{a.layers} layers, layer 1 {a.first_h}mm tall")
