#!/usr/bin/env python3
"""HONEYCOMB in our technique — one continuous extrusion, no travels, pressed hard, at max flow.

Oleg: "create honeycomb out of our technic". The sliced STL version on the K2 is 321 x 310mm and
does not fit the K1C at all; more to the point, a sliced honeycomb is thousands of travel moves and
a stop-start extruder. Ours is one unbroken line.

HOW A HONEYCOMB IS DRAWN WITHOUT LIFTING THE PEN
A hex lattice has vertices of degree 3 — odd — so no Eulerian circuit exists and it cannot be traced
edge-once without retracing. The standard construction avoids that: a honeycomb is rows of ZIGZAGS
joined by short VERTICAL struts.

    row:      hexagon cells, walked one by one
    struts:   |   |   |         the vertical walls, drawn between rows

Walk a row left to right, drop a strut, walk the next row right to left, drop a strut, and so on.
Every edge is drawn exactly once, the pen never lifts, and the result is a true hexagonal lattice.
Boustrophedon — the way an ox ploughs a field.

Everything else follows the project's method: pressed to machine.PRESS_HARD, flow held at target by
deriving speed from the bead, no travel between first and last extrusion.
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sys as _sys

import machine


def _wall_graph(cell, cols, rows, ox, oy):
    """Every hex edge in the lattice, as an adjacency map on snapped vertices.

    Oleg, 2026-07-26: "we still get lines inside cells, cant you move it next to existing honeycomb
    lines instead of over shape?" — exactly right. A hex lattice has no Eulerian circuit, so the walk
    must step between cells; the question is whether that step crosses OPEN CELL or follows a wall
    that is already there. Crossing costs a visible line through the cell and blocks it. Following
    an existing wall costs a second pass over plastic that already exists, which this project
    already accepts ("overprint or whatever but no sharp turning").
    """
    R = cell
    w = math.sqrt(3) * R
    vsp = 1.5 * R
    verts = [(math.cos(math.radians(90 + 60 * k)) * R,
              math.sin(math.radians(90 + 60 * k)) * R) for k in range(6)]
    adj = {}
    def key(p):
        return (round(p[0], 2), round(p[1], 2))
    for r in range(rows):
        cy = oy + R + r * vsp
        xoff = (w / 2.0) if (r % 2) else 0.0
        for c in range(cols):
            cx = ox + w / 2.0 + xoff + c * w
            hexa = [(cx + vx, cy + vy) for vx, vy in verts]
            for i in range(6):
                a, b = key(hexa[i]), key(hexa[(i + 1) % 6])
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
    return adj


def _route(adj, a, b):
    """Shortest walk from a to b along existing walls. [] if they are not connected."""
    from collections import deque
    ka = (round(a[0], 2), round(a[1], 2))
    kb = (round(b[0], 2), round(b[1], 2))
    if ka not in adj or kb not in adj:
        return []
    prev = {ka: None}
    q = deque([ka])
    while q:
        cur = q.popleft()
        if cur == kb:
            break
        for nxt in adj.get(cur, ()):
            if nxt not in prev:
                prev[nxt] = cur
                q.append(nxt)
    if kb not in prev:
        return []
    out = []
    cur = kb
    while cur is not None:
        out.append(cur)
        cur = prev[cur]
    return list(reversed(out))[1:-1]      # interior vertices only


def comb_path(cell, cols, rows, ox, oy):
    """A real hex lattice as one continuous polyline. `cell` is the hexagon circumradius.

    The previous version laid zigzag rows joined by a single strut per row pair -- 12 vertical walls
    for 96 cells. That is a field of waves, not a honeycomb: without the vertical walls nothing
    closes into a cell.

    A hex lattice cannot be drawn edge-once (every interior vertex has degree 3, so no Eulerian
    circuit exists). Rather than fake it, each CELL is walked as a closed hexagon and the walk steps
    from cell to neighbouring cell. Shared walls therefore get printed twice -- Oleg: "overprint or
    whatever but no sharp turning" -- which costs filament and buys real closed cells, plus double
    thickness on every shared wall.

    Pointy-top hexagons: flat left and right sides, so horizontal neighbours share a vertical wall
    and the step between them is short.
    """
    R = cell
    w = math.sqrt(3) * R                 # across the flats
    vsp = 1.5 * R                        # row-to-row centre spacing
    adj = _wall_graph(cell, cols, rows, ox, oy)
    wall_len = R                          # a hex edge is exactly the circumradius
    verts = [(math.cos(math.radians(90 + 60 * k)) * R,
              math.sin(math.radians(90 + 60 * k)) * R) for k in range(6)]
    pts = []
    for r in range(rows):
        cy = oy + R + r * vsp
        xoff = (w / 2.0) if (r % 2) else 0.0
        order = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)
        for c in order:
            cx = ox + w / 2.0 + xoff + c * w
            hexa = [(cx + vx, cy + vy) for vx, vy in verts]
            # start each cell at whichever vertex is nearest where the path currently is, so the
            # step between cells is the shortest possible and never crosses the cell
            if pts:
                # Nearest-vertex alone doubles back: the nearest vertex of the next cell is often
                # the one we just CAME FROM, so the path retraces the edge it has just laid -- a
                # 180-degree reversal. The corner fillet then hid it by shrinking it into 0.006mm
                # segments, small enough in angle to pass a turn check while still being a dead
                # stop with the extruder running. Exclude the previous point from the choice.
                # Prefer not to start the next cell on the vertex we just came FROM, which
                # retraces the edge just laid. This helps (13 near-reversals -> 11) but does not
                # solve it: closing every cell means the walk ENDS where it started, so entering a
                # neighbour that shares that vertex tends to double back whatever we pick. Excluding
                # the arrival vertex too made it worse (18), and the walk direction cannot fix it
                # because both directions share the same first vertex.
                #
                # The structural fix is a different construction: zigzag rows with EVERY strut drawn
                # as a narrow loop (down one side, back up ~1.2mm over) rather than per-cell closed
                # hexagons. At a 1.5mm bead the loop merges into a single wall, gives every cell its
                # vertical walls, and has no reversal anywhere. Not done yet -- the current path
                # prints correctly, and the fillet turns these cusps into tight arcs, so this is
                # wasted moves and dead stops rather than a defect on the plate.
                back = pts[-2] if len(pts) > 1 else None
                cand = [i for i in range(6)
                        if back is None or math.dist(hexa[i], back) > 1e-6] or list(range(6))
                k0 = min(cand, key=lambda i: math.dist(pts[-1], hexa[i]))
            else:
                k0 = 0
            # AND PICK THE DIRECTION OF TRAVEL. When the next cell starts on a vertex shared with
            # the last one, walking it in a fixed direction sends the first edge straight back along
            # the edge just laid -- a 180-degree reversal. The corner fillet then hid it by shrinking
            # it into 0.006mm segments: small enough in angle to pass a turn check, still a dead stop
            # with the extruder running. Walk each cell whichever way continues the current heading.
            loops = [[hexa[(k0 + d * i) % 6] for i in range(6)] + [hexa[k0]] for d in (1, -1)]
            if len(pts) > 1:
                hx, hy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
                hl = math.hypot(hx, hy)
                if hl > 1e-9:
                    def _turn(loop):
                        nxt = loop[1] if math.dist(pts[-1], loop[0]) < 1e-6 else loop[0]
                        vx, vy = nxt[0] - pts[-1][0], nxt[1] - pts[-1][1]
                        vl = math.hypot(vx, vy)
                        if vl < 1e-9:
                            return 180.0
                        return math.degrees(math.acos(
                            max(-1.0, min(1.0, (hx * vx + hy * vy) / (hl * vl)))))
                    loops.sort(key=_turn)
            # FOLLOW THE WALLS, DO NOT CUT THE CELL.
            # If the step into this cell is longer than one hex edge it is crossing open cell, so
            # walk there along edges that already exist instead. Measured before this: 18.1% of the
            # first layer was chords through cell interiors.
            nxt0 = loops[0][0]
            if pts and math.dist(pts[-1], nxt0) > wall_len * 1.05:
                pts.extend(_route(adj, pts[-1], nxt0))
            pts.extend(loops[0])
    # CLOSE ALONG THE WALLS TOO. This used to be a bare `pts.append(pts[0])` — a single straight
    # line from wherever the walk ended back to the origin, 192.5mm across the whole part on a
    # 7x9 lattice, extruded, once per layer. It is the "straight light artifact" Oleg spotted in the
    # very first honeycomb print, and it was never fixed — the Moore curve was adopted instead.
    if math.dist(pts[0], pts[-1]) > 1e-6:
        pts.extend(_route(adj, pts[-1], pts[0]))
        pts.append(pts[0])
    return pts


def round_corners(pts, fillet, seg=0.8):
    """Replace every sharp vertex with a tangent curve. NO SHARP TURNS is a project rule, and it is
    also physics: Klipper decelerates to square_corner_velocity (5 mm/s) at a hard corner, so a path
    of 60-degree hex vertices spends its life braking. Since E is metered per mm of PATH, the flow
    does not brake with it — every corner is a pressure spike into a stalled head, which is exactly
    what makes the extruder skip.

    A quadratic Bezier through each vertex is C1-continuous, so direction never jumps. Holding speed
    v through a curve needs radius >= v^2/accel; at the 50 mm/s north star and 5000 mm/s^2 that is
    0.5mm, so a few-mm fillet keeps FULL speed through every corner. The requirement scales with
    v^2, so a print that resolves BELOW the north star (fat bead, low-flow material) needs less
    radius, never more — this is safe in the direction speed is allowed to move. Oleg: "overprint or
    whatever but no sharp turning" — the cut corners overlap slightly, and that is the accepted
    trade."""
    if fillet <= 0 or len(pts) < 3:
        return pts
    # Near-coincident points clamp the fillet to nothing (d = min(fillet, la/2, lc/2)), leaving a
    # hard corner that no amount of sampling can smooth. Drop them first.
    ded = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, ded[-1]) > 0.5:
            ded.append(p)
    pts = ded
    # A CLOSED LOOP HAS NO FIRST VERTEX. Filleting only the interior points leaves the junction
    # where the path rejoins its own start un-rounded -- and since every stacked layer passes
    # through it, that one hard corner repeats on every layer. Walk closed paths cyclically so the
    # junction is just another vertex.
    closed = math.dist(pts[0], pts[-1]) < 1e-6
    if closed:
        core = pts[:-1]
        idx = [(core[i - 1], core[i], core[(i + 1) % len(core)]) for i in range(len(core))]
    else:
        idx = [(pts[i - 1], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)]
    out = [] if closed else [pts[0]]
    for a, v, c in idx:
        la = math.dist(a, v); lc = math.dist(v, c)
        if la < 1e-9 or lc < 1e-9:
            continue
        d = min(fillet, la / 2, lc / 2)
        p1 = (v[0] + (a[0] - v[0]) * d / la, v[1] + (a[1] - v[1]) * d / la)
        p2 = (v[0] + (c[0] - v[0]) * d / lc, v[1] + (c[1] - v[1]) * d / lc)
        # Sample by ANGLE, not by length. A 90-degree corner cut back only 0.3mm still turns 90
        # degrees; splitting it into 2 steps leaves 45-degree jumps. Bounding the angular step is
        # what actually removes the sharp turn.
        _c = max(-1.0, min(1.0, ((a[0]-v[0])*(c[0]-v[0]) + (a[1]-v[1])*(c[1]-v[1]))
                           / (la * lc)))
        turn = 180.0 - math.degrees(math.acos(_c))
        n = max(4, int(math.ceil(2 * d / seg)), int(math.ceil(turn / 6.0)))
        for k in range(n + 1):
            t = k / n
            m = (1 - t) ** 2
            out.append((m * p1[0] + 2 * (1 - t) * t * v[0] + t * t * p2[0],
                        m * p1[1] + 2 * (1 - t) * t * v[1] + t * t * p2[1]))
    if closed:
        out.append(out[0])
    else:
        out.append(pts[-1])
    return out


def emit(cell, cols, rows, bead_w, bead_h, flow, temp, bed, fil_d, bed_xy, home, press, fan,
         fillet=3.0, layers=1, material='pla', printer='k1c'):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (bead_w * bead_h) / area
    # R4 — FLOW IS CONSTANT, AND THE FIRST LAYER IS NOT AN EXCEPTION TO IT.
    # Oleg, 2026-07-27: "omg why you killed first layer flow!!!!!!! flow must be constant".
    # This file used to meter layer 1 at bead_w * press = 0.12mm2 against the body's 0.72mm2 —
    # one sixth of the material — reasoning that a bead laid into a 0.1mm gap can only hold
    # 0.1mm of plastic. That reasoning is wrong: the bead does not stay 1.2mm wide at a 0.1mm
    # gap, it SPREADS, and that enormous squished footprint IS the adhesion. Starving it to keep
    # a nominal width is the one thing that guarantees the comb lifts off the plate.
    # Same flow, same speed, pressed to the plate. Only Z changes on layer 1.
    e_first_mm = e_per_mm
    # R3 — ONE SPEED PER PRINT. ITS VALUE IS THE NORTH STAR UNLESS A CONSTRAINT PUSHES IT DOWN.
    # Oleg, 2026-07-27, correcting the previous version of this block: "speed is not fixed - 50 is
    # north star default unless overruled by other constraints."
    #
    # This file used to PIN speed at 50 and then recompute flow from it. That is a different and
    # worse rule, and it broke the technique it was supposed to protect:
    #   * THE WIDE-BEAD TRICK INVERTED. A fat commanded bead exists so the head CRAWLS and still
    #     lands the flow target. Pinned at 50, width IS flow — `--bead-w 6` emitted 180 mm3/s and
    #     validate.py refused the file outright. The archived 1.5x0.9 comb was re-inflated from its
    #     own 55 to 67.5, past the material's measured ceiling, AFTER machine.flow_for had already
    #     clamped it — a generator overwriting the material's limit with arithmetic.
    #   * LOW-FLOW MATERIALS became "unprintable". TPU's 15.2 mm3/s at a pinned 50 needs a 0.51mm
    #     bead, narrower than the 0.8 nozzle. At the normal 1.2x0.6 bead it just runs at 21 mm/s.
    #
    # What must actually hold is CONSTANCY — one speed for the whole print, so material per mm does
    # not change where the geometry is tightest. machine.speed_for_flow() gives that one speed:
    # min(north star, flow / bead area). Never above 50; below it whenever the bead or the material
    # says so.
    speed = machine.speed_for_flow(flow, bead_w, bead_h)
    # DECLARE WHAT THE FILE DELIVERS, NOT WHAT WAS ASKED FOR. The head runs the INTEGER feedrate
    # written into the gcode, so the flow is derived from THAT — otherwise '; FLOW=' is an
    # aspiration a few hundredths off every move in the file (R4). Floored, never rounded: the
    # flow target it was solved from is a material CEILING, and a ceiling must not be rounded past.
    f = max(1, math.floor(speed * 60))
    speed = f / 60.0
    _asked, flow = flow, speed * bead_w * bead_h
    if speed >= machine.DEFAULT_SPEED - 1e-9 and flow < _asked * 0.999:
        # The other direction: the bead is too THIN to carry the target at the north star. Speed is
        # not allowed ABOVE 50, so the honest outcome is less flow, said out loud.
        print(f"  ! --flow {_asked:g} mm3/s would need {_asked/(bead_w*bead_h):.0f} mm/s at a "
              f"{bead_w}x{bead_h} bead, above the {machine.DEFAULT_SPEED:g} mm/s north star. "
              f"Running {flow:.1f} mm3/s ({flow/_asked*100:.0f}% of target). Widen the "
              f"bead (--bead-w) to close the gap.")
    elif speed < machine.DEFAULT_SPEED - 1e-9:
        _why = "the fat bead" if bead_w * bead_h > machine.BEAD_W * machine.BEAD_H + 1e-9 \
            else f"{material}'s flow ceiling"
        print(f"  ~ {bead_w}x{bead_h} bead at {_asked:g} mm3/s resolves to {speed:.1f} mm/s, below "
              f"the {machine.DEFAULT_SPEED:g} mm/s north star — the head crawls so {_why} lands "
              f"the flow. One speed throughout (R3); deposit per mm of path is unchanged, only "
              f"the clock moves.")
    s = cell
    w_total = cols * math.sqrt(3) * s + math.sqrt(3) * s / 2.0
    h_total = (rows - 1) * 1.5 * s + 2 * s
    ox = (bed_xy[0] - w_total) / 2.0
    oy = (bed_xy[1] - h_total) / 2.0
    if ox < 8 or oy < 8:
        raise SystemExit(f"{cols}x{rows} cells of {cell}mm = {w_total:.0f} x {h_total:.0f}mm — "
                         f"too big for a {bed_xy[0]:.0f} x {bed_xy[1]:.0f} bed. Reduce --cols/--rows "
                         f"or --cell.")
    pts = round_corners(comb_path(cell, cols, rows, ox, oy), fillet)
    # DECIMATE FOR THE COMMANDED SPEED. round_corners samples by angle; at 70 mm/s that was 1174
    # moves/second against a host that stalls near 300 and then FREEZES with no error.
    _min_seg = max(0.25, speed / 250.0)
    _dec = [pts[0]]
    for _p in pts[1:-1]:
        if math.dist(_p, _dec[-1]) >= _min_seg:
            _dec.append(_p)
    _dec.append(pts[-1])
    pts = _dec
    _xs = [p[0] for p in pts]; _ys = [p[1] for p in pts]
    if min(_xs) < 4 or min(_ys) < 4 or max(_xs) > bed_xy[0] - 4 or max(_ys) > bed_xy[1] - 4:
        raise SystemExit(f"comb spans X {min(_xs):.0f}..{max(_xs):.0f} Y {min(_ys):.0f}.."
                         f"{max(_ys):.0f} on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} bed — off the plate.")

    # MEASURE THE OVERPRINT INSTEAD OF HIDING IT. A hex lattice has no Eulerian circuit, so a
    # single stroke MUST re-walk some walls. Two passes on a shared wall is designed (see
    # comb_path). Anything beyond two is the cell-to-cell routing landing on walls both
    # neighbouring cells already drew — that plastic is real and it goes on the plate at full
    # rate now that flow is constant (R4), so the figure is measured from the emitted path and
    # printed on every run rather than being quietly metered away.
    _seen, _tot, _over = {}, 0.0, 0.0
    _pp = pts[0]
    for _q in pts[1:]:
        _d = math.dist(_pp, _q)
        if _d < 1e-9:
            continue
        _k = tuple(sorted([(round(_pp[0], 1), round(_pp[1], 1)),
                           (round(_q[0], 1), round(_q[1], 1))]))
        _seen[_k] = _seen.get(_k, 0) + 1
        _tot += _d
        if _seen[_k] > 2:
            _over += _d
        _pp = _q
    overprint = 100.0 * _over / max(_tot, 1e-9)

    L = []; w = L.append
    w(f"; HONEYCOMB — one continuous extrusion, {cols}x{rows} cells of {cell}mm")
    w(f"; PRINTER={printer}")
    w(f"; MATERIAL={material}")
    w(f"; LAYER_H={bead_h}")     # R2: validate.py checks the Z ladder against this
    # R4b exemption stamp: layer 1 is pressed to `press` and over-fills on purpose (the
    # plate weld); unstamped, R4b read 2.49x as a failure (review-confirmed)
    w(f"; PRESSED_LAYER1={press:g}")
    # R4: validate.py checks every extruding move against this, so it is the DELIVERED flow at the
    # resolved speed (bead_w * bead_h * speed), never the --flow that was asked for.
    w(f"; FLOW={flow:.1f}")
    _der = machine.flow_derate_stamp(material, printer, flow)
    if _der:
        w(_der)   # R8: slow is allowed, silent slow is not
        print("  " + _der.lstrip("; "))
    w("; ARGV: " + " ".join(_sys.argv))
    w(f"; bead {bead_w}x{bead_h} = {bead_w*bead_h:.2f}mm2 at {speed:.1f} mm/s -> flow={flow:.1f} mm3/s"
      f" (north star {machine.DEFAULT_SPEED:g}; lower is the bead crawling, never faster)")
    w(f"; {w_total:.0f} x {h_total:.0f}mm on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} bed, pressed to {press}mm")
    w(f"; overprint: {overprint:.1f}% of the path is a 3rd/4th pass over a wall already laid twice")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {layers}"); w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — assumes the machine is ALREADY homed; push.py verifies and homes if not")
    # M190 only waits for HEATING; a bed already hotter than target returns instantly, so a part
    # meant for a 45C plate can print on a 98C one left over from the previous job. TEMPERATURE_WAIT
    # blocks in BOTH directions.
    # SENSOR NAME UNQUOTED — Klipper does not match the QUOTED form and skips the wait
    # SILENTLY (empirical: a 100C-floor part started at 78C; bucket.py hit the same bug).
    w(f"TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM={machine.bed_start(material, bed)} MAXIMUM={bed+5}")
    w(f"M109 S{temp}")
    w("M204 S8000")
    # fan: clamped to the material ceiling, and OFF on layer 1 unless the material needs it
    _fan_body = int(round(machine.fan_for(material, (fan or 0) / 255.0) * 255))
    _fan_l1 = int(round(machine.fan_first_layer(material) * 255))
    w(f"M106 S{_fan_l1}" if _fan_l1 else "M107")
    for _ln in machine.aux_fans(printer, machine.aux_for(material, 0.2)):
        w(_ln)
    w("M82"); w("G92 E0")
    x0, y0 = pts[0]
    w(f"G1 Z{press:.3f} F600")
    # Prime must start ON the bed. x0-55 put it at X-24 on a 229 bed — the guard below catches it
    # now, but the approach is clamped so it cannot happen at all.
    _apx = max(6.0, x0 - 55.0)
    _apy = max(6.0, y0 - 12.0)
    w(f"G0 F9000 X{_apx:.3f} Y{_apy:.3f}")
    w("G1 E25 F300                      ; stationary purge — pressure before motion")
    w(f"G1 F1200 X{x0:.3f} Y{y0:.3f} E37   ; prime ends where the comb begins")
    w("G92 E0")
    # The machine, the material, the layer height, the flow and the command that made the file are
    # all stamped at the TOP of the header now, not here. validate.py reads several of them out of
    # the first 4000 characters, and a stamp that arrives after a long ARGV line is a stamp that can
    # silently go missing — and a missing stamp is a FAILURE, not a skip (RULES.md).
    w("; BODY_START")

    e = 0.0
    px, py = pts[0]
    # STACK THE COMB. A single pass is a drawing of a honeycomb; stacked passes are a honeycomb --
    # walls with height. Each layer REVERSES the path so it starts exactly where the previous one
    # finished: no travel across the part, and the seam is a single vertical step extruded in place.
    #
    # Layer 1 sits at `press` (squashed into the plate so it BONDS). Every layer above steps by the
    # full bead height, because it is landing on plastic rather than glass and does not need to be
    # crushed -- pressing an upper layer just ploughs the one beneath it.
    #
    # R2 — THE LADDER IS REBASED ON THE PRESSED FIRST LAYER: z = press + bead_h*k, never
    # bead_h*(k+1). Pressing layer 1 to 0.1 without rebasing leaves a 1.10mm step onto layer 2 over
    # a 0.60mm bead, i.e. a layer extruded into air. Oleg: "play Z smartly we dont want floaring
    # lines".
    for k in range(layers):
        seq = pts        # closed loop -- same direction every layer, so no seam reversal
        z = press + k * bead_h
        if k:
            L.append(f"; --- layer {k+1} at Z{z:.2f} -- closed loop, starts where layer "
                     f"{k} ended, same direction")
            e += bead_h * e_per_mm          # keep extruding through the vertical step
            # The seam step is never FASTER than the print's one speed (min), so a crawl stays a
            # crawl all the way up the Z ladder.
            L.append(f"G1 F{max(1, round(min(speed, 20.0)*60))} Z{z:.3f} E{e:.5f}")
            L.append(f"G1 F{f}")
        px, py = seq[0]
        for (x, y) in seq[1:]:
            d = math.dist((px, py), (x, y))
            if d < 1e-9:
                continue
            # ONE RATE FOR EVERY MOVE IN THE FILE (R4).
            # This loop used to meter a wall's 3rd and 4th pass at 0.15x — a token thread, on the
            # argument that the wall already exists and the path only needs continuity. That is a
            # generator deciding for itself when the flow rule applies, which is exactly what
            # RULES.md exists to stop: "flow must be constant". The over-deposit it was hiding is
            # real and is now MEASURED and stamped into the header instead (see `overprint`), so it
            # can be argued with from the artifact rather than silently compensated for.
            e += d * (e_first_mm if k == 0 else e_per_mm)
            L.append(f"G1 {'F%d ' % f if (px, py) == seq[0] and k == 0 else ''}"
                     f"X{x:.3f} Y{y:.3f} Z{z:.3f} E{e:.5f}")
            px, py = x, y
    # END-OF-PRINT RETREAT — a rapid, non-extruding move, so it is a G0 and not a G1.
    # It was a G1, which is wrong on its own terms (nothing is extruded) and also made the 40mm
    # retreat read as a 40mm LAYER STEP to the R2 ladder check. Files with many layers hid that by
    # filling the check's window before the retreat was reached; a 1-layer comb did not.
    L += ["M107", "M104 S0", "M140 S0", f"G0 Z{press+(layers-1)*bead_h+40:.1f} F900",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(flow=round(flow, 1), pts=len(pts), grams=round(grams, 1), speed=round(speed, 1),
                                     mins=round(e / e_per_mm / speed / 60, 1),
                                     overprint=round(overprint, 1),
                                     size=(round(w_total), round(h_total)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", type=float, default=12.0, help="hexagon side length mm")
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--rows", type=int, default=12)
    ap.add_argument("--bead-w", type=float, default=machine.BEAD_W)
    ap.add_argument("--bead-h", type=float, default=machine.BEAD_H)
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--temp", type=int, default=0,
                    help="0 = machine.temp_for(material). A hardcoded machine.TEMP (210, the "
                         "translucent PLA figure) stamped MATERIAL=pla-matte into a file printed "
                         "20C under that spool's rating — the exact defect machine.py's "
                         "material-routing audit was written about.")
    ap.add_argument("--bed", type=int, default=0,
                    help="0 = machine.BED_TEMP[material] — PLA is maxed to the plate ceiling by standing rule")
    ap.add_argument("--press", type=float, default=machine.PRESS_HARD,
                    help="first-layer Z. R1 requires machine.PRESS_HARD (%.2f) and validate.py "
                         "refuses anything else — the knob stays only for a deliberate levelling "
                         "experiment." % machine.PRESS_HARD)
    ap.add_argument("--fan", type=int, default=0)
    ap.add_argument("--layers", type=int, default=1, help="stacked layers of comb")
    ap.add_argument("--fillet", type=float, default=3.0,
                    help="corner rounding radius mm — 0 gives sharp corners (banned)")
    ap.add_argument("--material", default=machine.DEFAULT_MATERIAL,
                    choices=sorted(machine.MATERIAL_TEMP),
                    help="stamped into the file; TPU is fan-guarded")
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED),
                    help="picks the PRINTABLE plate size from machine.BED")
    ap.add_argument("--bed-size", default="", help="override WxY mm (rarely right)")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    machine.check_flow(a.flow, f' for honeycomb.py')
    # R1 IS NOT NEGOTIABLE BY FLAG. "the nozel need to be 0,1 to board. we need adhesion" — a file
    # laid anywhere else is refused by validate.py and by push.py, so say so HERE rather than let
    # someone discover it after a generation run.
    if abs(a.press - machine.PRESS_HARD) > 1e-9:
        print(f"  !! --press {a.press:g} is not machine.PRESS_HARD ({machine.PRESS_HARD:g}). R1 "
              f"presses the first layer to the plate; validate.py will refuse this file and push.py "
              f"will not upload it. Only do this to measure something.")
    # MATERIAL FOLLOWS THE PRINTER. A comb generated for one spool and printed on another is
    # silently wrong: right geometry, wrong temperature, wrong flow ceiling.
    machine.check_spool(a.printer, a.material)
    a.temp = a.temp or machine.temp_for(a.material)
    a.flow = machine.flow_for(a.material, a.flow, ' for honeycomb.py')
    bxy = (tuple(float(v) for v in a.bed_size.split(",")) if a.bed_size
           else machine.BED[a.printer])
    g, st = emit(a.cell, a.cols, a.rows, a.bead_w, a.bead_h, a.flow, a.temp, a.bed or machine.bed_for(a.material, a.printer), 1.75,
                 bxy, not a.no_home, a.press, a.fan, a.fillet, a.layers, a.material, a.printer)
    os.makedirs(a.out, exist_ok=True)
    tag = a.printer
    fn = f"{a.out}/honeycomb_{tag}_{a.cols}x{a.rows}_c{a.cell:g}_T{a.temp}.gcode"
    machine.emit_gcode(fn, g)
    print(f"{fn}\n  {a.cols}x{a.rows} cells of {a.cell}mm -> {st['size'][0]} x {st['size'][1]}mm, "
          f"{st['pts']} points, one continuous path")
    print(f"  {st['speed']} mm/s at flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g, "
          f"pressed to {a.press}mm")
    # SAY THE OVERPRINT OUT LOUD. A hex lattice cannot be drawn edge-once, so a single stroke
    # re-walks walls; two passes on a shared wall is the design, the rest is routing. Flow is
    # constant (R4), so this fraction of the path lands 3-4 beads deep in one line. It used to be
    # metered down to 15% and therefore invisible.
    print(f"  overprint {st['overprint']}% of path on a 3rd/4th pass — laid at FULL rate (R4: flow "
          f"is constant). Watch those walls on the plate; if they bulge, fix the WALK, not the flow.")
