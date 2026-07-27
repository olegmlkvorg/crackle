#!/usr/bin/env python3
"""WAVES — long rippled ribbons, one continuous extrusion, to be shaped by hand while warm.

This began as a broken honeycomb: zigzag rows joined by a single strut per row pair, so it drew a
field of waves with 12 vertical walls for 96 cells -- no closed cells at all. As a honeycomb it was
simply wrong, and it was on its way to being deleted.

Oleg peeled the rows off the plate while they were still warm, splayed them radially and welded
them at the centre: a flower roughly 300mm across with a rippled edge, and the best thing either
machine made that day. 2026-07-25.

So the wave path is kept HERE as its own product instead of being fixed away. What makes it work
as hand-forming feedstock:
  · each ribbon is one uninterrupted strand -- no travels means nothing to snap at
  · the ripple gives the strand spring and grip, so a hand-formed curve HOLDS
  · rounded ends (the corner fillet) make a bent ribbon read as finished, not cut
  · translucent PLA pressed to 0.55mm is thin enough to bend warm, stiff enough to keep the shape

The honeycomb this failed to be now lives in honeycomb.py as a real hex lattice.
See guides/alien-tech-forming.md -- the FORMING vertical arriving on its own.
"""
import argparse
import math
import os

import sys as _sys

import machine

def comb_path(cell, cols, rows, ox, oy):
    """Hex lattice as one continuous polyline. `cell` is the hexagon side length."""
    s = cell
    dx = s * math.sqrt(3) / 2.0          # half-width of a hexagon
    up = s / 2.0                          # vertical rise of a slanted wall
    strut = s                             # length of a vertical wall
    pts = []
    y = oy
    for r in range(rows):
        rightward = (r % 2 == 0)
        xs = range(cols * 2 + 1) if rightward else range(cols * 2, -1, -1)
        for i, k in enumerate(xs):
            x = ox + k * dx
            zig = y + (up if (k % 2 == 1) else 0.0)
            pts.append((x, zig))
        # strut down into the next row, at whichever end we finished on
        if r < rows - 1:
            xend = pts[-1][0]
            pts.append((xend, pts[-1][1] + strut))
            y = y + strut
    # CLOSE THE CIRCUIT. Stacking by reversing the path makes each layer retrace the previous
    # layer's last segment backwards -- a 180-degree reversal, the sharpest turn there is, with the
    # extruder still running. Closing the comb into a loop instead lets every layer run the SAME
    # direction from the SAME point: no reversal, no travel, and the closing run down the left edge
    # is not waste, it is the left wall.
    if math.dist(pts[0], pts[-1]) > 1e-6:
        pts.append(pts[0])
    return pts


def round_corners(pts, fillet, seg=0.8):
    """Replace every sharp vertex with a tangent curve. NO SHARP TURNS is a project rule, and it is
    also physics: Klipper decelerates to square_corner_velocity (5 mm/s) at a hard corner, so a path
    of 60-degree hex vertices spends its life braking. Since E is metered per mm of PATH, the flow
    does not brake with it — every corner is a pressure spike into a stalled head, which is exactly
    what makes the extruder skip.

    A quadratic Bezier through each vertex is C1-continuous, so direction never jumps. Holding speed
    v through a curve needs radius >= v^2/accel; at 49 mm/s and 5000 mm/s^2 that is 0.5mm, so a
    few-mm fillet keeps FULL speed through every corner. Oleg: "overprint or whatever but no sharp
    turning" — the cut corners overlap slightly, and that is the accepted trade."""
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


def emit(cell, cols, rows, bead_w, bead_h, flow, temp, bed, fil_d, bed_xy, home, press, fan, fillet=3.0, layers=1, printer='k1c', material='pla'):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (bead_w * bead_h) / area
    # R4 — FLOW IS CONSTANT, AND LAYER 1 IS NOT AN EXCEPTION TO IT.
    # This file used to meter layer 1 at bead_w * press: 0.120mm2 against the body's 0.720mm2, one
    # SIXTH of the material, on the one layer whose only job is to bond. The reasoning was that a
    # bead laid into a 0.1mm gap can only hold 0.1mm of material. It is wrong, and Oleg said so
    # directly: "omg why you killed first layer flow!!!!!!! flow must be constant".
    # The bead does not stay 1.2mm wide at a 0.1mm gap. The same volume per mm SPREADS — roughly
    # 12x the nominal width here — and that enormous squished footprint IS the adhesion. Starving
    # it to keep a nominal width is the one thing that guarantees the ribbon lifts.
    # Same flow, same speed, pressed to the plate. Only Z changes on layer 1.
    e_first_mm = e_per_mm
    # R3 — SPEED IS AN INPUT HELD FIXED, NOT AN OUTPUT SOLVED FROM FLOW.
    # "50 is our north star for moving" (Oleg, 2026-07-27). The old line here was
    # min(flow / bead_area, MAX_SPEED), which lands on 50 only because the default flow happens to
    # ask for more than 50 — a lower --flow, or a narrower bead, silently produced an off-speed file
    # and nothing said so. Pinning it removes the accident.
    speed = machine.CONSTANT_SPEED
    # WITH SPEED AND BEAD BOTH FIXED, FLOW IS FULLY DETERMINED — so --flow is ADVISORY here, and it
    # has to say so in BOTH directions. A cap that silently rewrites your input is indistinguishable
    # from a bug (machine.speed_for says exactly this), and the old code rewrote it in silence: it
    # recomputed `flow` from the capped speed and printed the result as if it had been asked for.
    delivered = bead_w * bead_h * speed
    if abs(delivered - flow) > flow * 0.001:
        _dir = "under" if delivered < flow else "OVER"
        # The way to move flow is the BEAD, not the head. But widening past machine.BEAD_W
        # (1.5x nozzle) makes the bead land TALLER than the Z step and the part climbs into the
        # nozzle on a stacked run — so the width is printed as a suggestion, never applied.
        print(f"  ! flow is an OUTPUT here: {bead_w:g}x{bead_h:g} at a fixed {speed:g} mm/s "
              f"(machine.CONSTANT_SPEED) delivers {delivered:.1f} mm3/s, {_dir} the {flow:g} "
              f"requested ({delivered/flow*100:.0f}%). Speed may not move — R3. To hit {flow:g} "
              f"exactly, set --bead-w {machine.bead_for_flow(flow, bead_h):.2f} "
              f"(machine.BEAD_W is {machine.BEAD_W:g}; check it still stacks before going wider).")
    flow = delivered
    f = round(speed * 60)
    s = cell
    w_total = cols * 2 * (s * math.sqrt(3) / 2.0)      # wave-row geometry, not hex-cell
    h_total = (rows - 1) * s + s / 2.0
    ox = (bed_xy[0] - w_total) / 2.0
    oy = (bed_xy[1] - h_total) / 2.0
    if ox < 8 or oy < 8:
        raise SystemExit(f"{cols}x{rows} cells of {cell}mm = {w_total:.0f} x {h_total:.0f}mm — "
                         f"too big for a {bed_xy[0]:.0f} x {bed_xy[1]:.0f} bed. Reduce --cols/--rows "
                         f"or --cell.")
    pts = round_corners(comb_path(cell, cols, rows, ox, oy), fillet)
    # DECIMATE TO KEEP THE HOST ALIVE.
    # round_corners samples by angle, which produced ~0.15mm segments — fine at the old 30 mm/s cap,
    # but MAX_SPEED is now 70 and that is 466 moves/second against a host that stalls near 300.
    # Klipper does not error when it runs out of lookahead; it simply FREEZES mid-print. The limit
    # is a rate, so the minimum segment is derived from the speed actually commanded rather than
    # picked: at 250 moves/s of headroom, seg = speed / 250.
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

    L = []; w = L.append
    w(f"; WAVES — rippled ribbons to shape by hand, {cols}x{rows} of {cell}mm")
    # THE STAMPS COME FIRST, AND A MISSING ONE IS ITSELF A FAILURE (RULES.md). They used to sit
    # after the prime block; LAYER_H and FLOW were absent altogether, so validate.py could not
    # check R2 or R4 on this file at all and reported a green tick on a starved first layer.
    # An unchecked input passing quietly is the worst outcome this repo has.
    w(f"; PRINTER={printer}")
    w(f"; MATERIAL={material}")            # R6, and the TPU fan guard
    w(f"; LAYER_H={bead_h}")               # R2 — the Z ladder is checked against this
    w(f"; FLOW={flow:.1f}")                # R4 — every extruding move is checked against this
    # THE STAMP IS THE FLOW THAT IS ACTUALLY DELIVERED, not the one that was requested. Stamping
    # the request while the head runs at a fixed 50 mm/s declares a number no move in the file
    # meets, and R4 then reports every single move as starved — which is exactly what nucleon.py
    # does today (declares 55, delivers 36, 6851 moves flagged).
    w("; ARGV: " + " ".join(_sys.argv))
    w(f"; bead {bead_w}x{bead_h} = {bead_w*bead_h:.2f}mm2 at {speed:.0f} mm/s -> flow={flow:.1f} mm3/s")
    w(f"; {w_total:.0f} x {h_total:.0f}mm on a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} bed, pressed to {press}mm")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {layers}"); w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — assumes the machine is ALREADY homed; push.py verifies and homes if not")
    # M190 only waits for HEATING; a bed already hotter than target returns instantly, so a part
    # meant for a 45C plate can print on a 98C one left over from the previous job. TEMPERATURE_WAIT
    # blocks in BOTH directions.
    w(f"TEMPERATURE_WAIT SENSOR='heater_bed' MINIMUM={machine.bed_start(material, bed)} MAXIMUM={bed+5}")
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
    # The Z axis is slower than the head and cannot be commanded at the north star: machine.MAX_Z_V
    # is 30 mm/s. This is the feedrate for the vertical seam step only, which carries no XY.
    _zf = round(min(speed, machine.MAX_Z_V) * 60)
    for k in range(layers):
        seq = pts        # closed loop -- same direction every layer, so no seam reversal
        # R2 — THE LADDER IS REBASED ON THE PRESSED FIRST LAYER. Layer 1 sits at `press` (0.1) and
        # every layer above it is exactly one bead higher: press + bead_h*k, never bead_h*(k+1),
        # which would put layer 2 at 1.20 — a 1.10mm step over a 0.60mm bead, extruded into air.
        # "play Z smartly we dont want floaring lines" (Oleg, 2026-07-27).
        z = press + k * bead_h
        if k:
            L.append(f"; --- layer {k+1} at Z{z:.2f} -- closed loop, starts where layer "
                     f"{k} ended, same direction")
            # Keep extruding through the vertical step: the same material per mm of PATH as
            # everywhere else, so the seam is filled instead of travelled. Only the feedrate
            # differs, and it is the Z axis's limit rather than a head speed — this move has no XY
            # component, so there is no head velocity for R3 to be constant about. E is per mm, so
            # the deposit is identical whatever the clock says.
            e += bead_h * e_per_mm
            L.append(f"G1 F{_zf} Z{z:.3f} E{e:.5f}")
        px, py = seq[0]
        _first = True
        for (x, y) in seq[1:]:
            d = math.dist((px, py), (x, y))
            if d < 1e-9:
                continue
            e += d * (e_first_mm if k == 0 else e_per_mm)
            # F ON THE FIRST MOVE OF EVERY LAYER. Feedrates are STICKY in gcode: the prime line
            # (F1200) and the seam step (F1800) both leave one set. The old version restated F only
            # on layer 1, so on a stacked run every layer after the first inherited the seam step's
            # feedrate for its whole length — off the north star, and off it invisibly.
            L.append(f"G1 {'F%d ' % f if _first else ''}"
                     f"X{x:.3f} Y{y:.3f} Z{z:.3f} E{e:.5f}")
            px, py = x, y
            _first = False
    # THE PARK LIFT IS A RAPID, NOT A PRINT MOVE. Emitted as G1 it entered validate.py's Z ladder
    # as a 40mm "layer step" and failed R2 — the ladder reads printing layers, and this is the
    # end-of-print retreat with the heaters already off and nothing extruding. G0 says what it is.
    L += ["M107", "M104 S0", "M140 S0", f"G0 Z{press+(layers-1)*bead_h+40:.1f} F900",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(flow=round(flow, 1), pts=len(pts), grams=round(grams, 1), speed=round(speed),
                                     mins=round(e / e_per_mm / speed / 60, 1),
                                     size=(round(w_total), round(h_total)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", type=float, default=12.0, help="hexagon side length mm")
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--rows", type=int, default=12)
    ap.add_argument("--bead-w", type=float, default=machine.BEAD_W)
    ap.add_argument("--bead-h", type=float, default=machine.BEAD_H)
    ap.add_argument("--flow", type=float, default=0,
                    help="0 = the material's measured ceiling (PLA keeps the max-flow rule)")
    ap.add_argument("--temp", type=int, default=0,
                    help="0 = machine.temp_for(material). A PLA 210 default reached TPU in every generator.")
    ap.add_argument("--bed", type=int, default=0,
                    help="0 = machine.BED_TEMP[material] — PLA is maxed to the plate ceiling by standing rule")
    ap.add_argument("--press", type=float, default=machine.PRESS_HARD)
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
    # MATERIAL ROUTES THE NOZZLE AND THE FLOW TOO — see machine.MATERIAL_TEMP.
    a.temp = a.temp or machine.temp_for(a.material)
    a.flow = machine.flow_for(a.material, a.flow or machine.FLOW, ' for waves.py')
    machine.check_flow(a.flow, f' for waves.py')
    bxy = (tuple(float(v) for v in a.bed_size.split(",")) if a.bed_size
           else machine.BED[a.printer])
    g, st = emit(a.cell, a.cols, a.rows, a.bead_w, a.bead_h, a.flow, a.temp, a.bed or machine.bed_for(a.material, a.printer), 1.75,
                 bxy, not a.no_home, a.press, a.fan, a.fillet, a.layers, a.printer, a.material)
    os.makedirs(a.out, exist_ok=True)
    tag = a.printer
    fn = f"{a.out}/waves_{tag}_{a.cols}x{a.rows}_c{a.cell:g}_T{a.temp}.gcode"
    open(fn, "w").write(g)
    print(f"{fn}\n  {a.rows} ribbons of {a.cols} waves at {a.cell}mm -> "
          f"{st['size'][0]} x {st['size'][1]}mm, {st['pts']} points, one continuous path")
    print(f"  {st['speed']} mm/s at flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g, "
          f"pressed to {a.press}mm")
