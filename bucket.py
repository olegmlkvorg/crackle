#!/usr/bin/env python3
"""BUCKET — single-bead wall, two-layer rosette floor, reinforced where they meet.

Oleg, 2026-07-27: "on k2 print a single layer bucket (but add addtiional adhesion when floor
connects to walls. floor is 2 layrs. use roseta as you base for thesign of the bucket i guess.
the floor can have holes its fine" ... "i need like 20x20x20 cm bucket".

Three parts, one continuous stroke per layer:

  FLOOR   two layers of the rhodonea rosette (the p13 q8 n3 curve that printed well) inside a
          solid rim. The rose leaves daylight between its lobes -- that is the "holes are fine"
          part, and it is why the floor uses a fraction of the material a solid disc would.

  FILLET  the wall does not start as a single bead. For the first `fillet` layers it is several
          beads thick and steps inward one bead at a time, so the wall grows out of the floor
          instead of balancing on it. A single bead landing on a two-layer floor is a butt joint
          between two beads -- the weakest thing in the part, and exactly where a bucket fails.

  WALL    one bead thick the rest of the way up. Vertical, so it needs no support.

Everything is a 2D region extruded straight up; the cross-section CHANGES with height, which
emit() handles through a callable region.
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

import machine
import solid as S


def rose(cx, cy, R_out, R_in, p=13, q=8, n=3, steps=4000):
    """The rhodonea used for the rosetta: one closed self-crossing stroke, q laps to close."""
    D = R_out - R_in
    pts = []
    for i in range(steps + 1):
        t = 2.0 * math.pi * q * i / steps
        r = R_in + D * abs(math.cos(p * t / (2.0 * q))) ** n
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def crossing_z(pts, bead_w, base, lift, skip=40, ramp=2.0, prior=None):
    """Per-point Z: `base` normally, `lift` where the path crosses something already laid.

    Oleg, 2026-07-27: "lets play z on intresections. 0.1 when no intersection and 0.5 while
    crossin intersection (approximate)".

    The rose crosses itself ~90 times a layer. At a crossing the nozzle is being asked to lay a
    bead ON TOP of one already there, at the same Z -- so it ploughs through it, drags it, and
    piles material exactly where the part is already tallest. Lifting over the crossing lets the
    strand ride the one beneath it instead, which is what the nucleon's weld lift does.

    A point counts as a crossing if a point laid EARLIER lies within one bead: earlier in this
    stroke (more than `skip` indices back IN BOTH DIRECTIONS AROUND THE LOOP -- the rose is a
    closed curve, so its last points sit on its first points by construction; that is the seam
    every closed loop has, not a crossing, and lifting it built a 0.4mm mound exactly where the
    rim circles start), or anywhere in `prior` -- strokes already laid in this layer, so the rim
    rides over the rose tips it crosses instead of ploughing 13 of them per pass.

    ONLY THE LATER STRAND LIFTS. The first version lifted both sides of each crossing, but at
    the moment the earlier strand is laid there is nothing under it -- a lifted bead there is a
    line floating over air, which is exactly what Oleg banned ("we dont want floaring lines").

    Ramped over `ramp` mm so the Z move is not a step the machine has to absorb in one segment.
    """
    n = len(pts)
    cell = max(bead_w, 0.5)
    pgrid = {}
    for px, py in (prior or ()):
        pgrid.setdefault((int(px // cell), int(py // cell)), []).append((px, py))
    grid = {}
    hit = [False] * n
    for i, (x, y) in enumerate(pts):
        gx, gy = int(x // cell), int(y // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py in pgrid.get((gx + dx, gy + dy), ()):
                    # prior-stroke material: any proximity counts, no seam to excuse
                    if (x - px) ** 2 + (y - py) ** 2 < bead_w ** 2:
                        hit[i] = True
                        break
                if not hit[i]:
                    for j in grid.get((gx + dx, gy + dy), ()):
                        if min(i - j, n - 1 - (i - j)) > skip \
                                and (x - pts[j][0]) ** 2 + (y - pts[j][1]) ** 2 < bead_w ** 2:
                            hit[i] = True
                            break
                if hit[i]:
                    break
            if hit[i]:
                break
        grid.setdefault((gx, gy), []).append(i)
    # ramp: distance along the path to the nearest crossing
    d = [0.0] * n
    for i in range(1, n):
        d[i] = d[i - 1] + math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1])
    near = [1e9] * n
    for i in range(n):
        if hit[i]:
            near[i] = 0.0
    for i in range(1, n):
        near[i] = min(near[i], near[i-1] + (d[i] - d[i-1]))
    for i in range(n - 2, -1, -1):
        near[i] = min(near[i], near[i+1] + (d[i+1] - d[i]))
    return [base + (lift - base) * max(0.0, 1.0 - near[i] / ramp) for i in range(n)], sum(hit)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia", type=float, default=200.0, help="outside diameter, mm")
    ap.add_argument("--height", type=float, default=200.0, help="overall height, mm")
    ap.add_argument("--rim", type=float, default=None, help="rim width; default 3 beads")
    ap.add_argument("--fillet", type=int, default=14, help="layers of thickened wall at the base")
    ap.add_argument("--floor-layers", type=int, default=2)
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--bead-w", type=float, default=None)
    ap.add_argument("--flow", type=float, default=None)
    ap.add_argument("--brim", type=int, default=0)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    a.flow = a.flow or machine.flow_cap(a.material, a.printer)
    a.bead_w = a.bead_w or machine.bead_for_flow(a.flow, a.layer_h)
    speed = machine.speed_for_flow(a.flow, a.bead_w, a.layer_h)
    temp = machine.temp_for(a.material)
    bw = a.bead_w

    # THE RIM IS A WHOLE NUMBER OF BEADS. A fractional wall leaves the inward and outward contour
    # families with a void between them -- the defect Oleg spotted in the pole hook's ring.
    rim = a.rim or 3 * bw
    rim = max(2, round(rim / bw)) * bw

    bx, by = machine.BED[a.printer]
    cx, cy = bx / 2.0, by / 2.0
    R = a.dia / 2.0

    outer = Point(cx, cy).buffer(R, resolution=256)
    rim_ring = outer.difference(Point(cx, cy).buffer(R - rim, resolution=256))

    # floor: the rose, fattened to a bead, unioned with the rim so the two are one body
    rose_pts = rose(cx, cy, R - rim + bw / 2, (R - rim) * 0.11)
    # DECIMATE THE ROSE. Its points are evenly spaced in the PARAMETER, not in distance, so they
    # bunch where the curve dives toward the centre: measured 380 moves/s against the ~300 where
    # Klipper drains its lookahead and freezes with no error at all. The floor is the only place
    # this bites, and it is the same fix the nucleon needed.
    rose_pts = machine.decimate(rose_pts, machine.CONSTANT_SPEED / 300.0 * 1.2)
    rose_z, n_cross = crossing_z(rose_pts, bw, machine.PRESS_HARD, 0.5)
    floor = unary_union([rim_ring, LineString(rose_pts).buffer(bw / 2.0, resolution=8)])

    n_layers = int(round((a.height - machine.PRESS_HARD) / a.layer_h)) + 1
    f_frac = a.floor_layers / n_layers
    fil_frac = (a.floor_layers + a.fillet) / n_layers

    # WHY THIS DOES NOT GO THROUGH solid.emit(). That emitter builds a layer from contours() of a
    # 2D region, and contours() is written for SOLID regions: measured, a ring exactly one bead
    # wide yields ZERO contours, and anything wider yields TWO -- which would lay two beads inside
    # a 2mm wall. A single-bead wall is a different geometry class (the path IS the wall), so the
    # layers are written directly here, one continuous stroke each.
    import time as _t
    A = math.pi * (1.75 / 2) ** 2
    e_per_mm = bw * a.layer_h / A
    f = round(speed * 60)
    L = []
    w = L.append
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={a.layer_h}")
    w(f"; FLOW={bw*a.layer_h*speed:.4f}")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w("; ARGV: " + " ".join(sys.argv))
    w(f"; bucket {a.dia:.0f}x{a.height:.0f}, bead {bw:.2f}x{a.layer_h} at {speed:.1f} mm/s")
    w("M82")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M104 S{temp}")
    w("G28")
    # BED THRESHOLD SCALES WITH FOOTPRINT. Oleg's "you dont need to wait for 120 plate" was about
    # a small part; this one is 200mm across -- 5.7x the rosetta's area and 5.7x the shrinkage
    # force pulling its edges up. Starting a part this size on a 60C plate that is still climbing
    # to 120 is asking the first layer to hold while the plate moves under it.
    # Oleg, 2026-07-27: "for the bucket it was good start, lets try bed 120 there." So the
    # bucket waits for the FULL bed target, not a floor under it.
    _bmin = machine.bed_for(a.material, a.printer)
    # M190 BLOCKS, AND CANNOT BE MISPARSED. The previous line was
    #     TEMPERATURE_WAIT SENSOR='heater_bed' MINIMUM=100
    # and the print started at 78 C anyway: Klipper does not match the QUOTED sensor name, so the
    # wait was silently skipped. A guard that is silently skipped is worse than none, and this one
    # was invisible because the line was right there in the file.
    # M190 waits, then the target is raised again so the plate keeps climbing to its real setpoint.
    w(f"M190 S{_bmin:.0f}                          ; BLOCKING: do not start below this")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}   ; keep climbing to the real target")
    w(f"M109 S{temp}")
    w("M106 S51")
    w("G92 E0")
    # prime in the clear, then break the bead off at an angle so no tail rides onto the part
    px0, py0 = 20.0, cy - R - 14.0
    w(f"G1 Z{machine.PRESS_HARD:.3f} F600")
    w(f"G0 F9000 X{px0:.3f} Y{py0:.3f}")
    w("G1 E20 F300                      ; PRIME stationary purge")
    w(f"G1 F1200 X{px0+40:.3f} Y{py0:.3f} E30   ; PRIME line, in the clear")
    w(f"G0 F3000 X{px0+52:.3f} Y{py0+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    # WITHOUT THIS MARKER several checks silently do not run. validate.py said so outright:
    # "BODY NEVER STARTED ... the Z-plough, backwards-extrusion and off-bed checks NEVER RAN.
    # This file is unchecked, not clean." An unrun check reported as a pass is the worse failure.
    w(f"; ARCH_LIFT={0.5 - machine.PRESS_HARD:.3f}")   # Z varies WITHIN the floor layers, by design
    w("; BODY_START")

    e = 0.0
    pos = [None]

    def stroke(pts, z, first, zs=None):
        """Emit one continuous stroke, metering E from the REAL distance travelled.

        The first version set the pen position to pts[0] without accounting for where the head
        actually was. At every stroke boundary -- rose to rim, rim to rim, floor to wall -- the
        head then crossed a real gap while E advanced by the next segment's tiny amount: a
        starved thread at 8.9 mm3/s against a declared 60. R4 caught it before it printed.
        """
        nonlocal e
        if first or pos[0] is None:
            w(f"G0 F9000 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; PRIME-TRAVEL to first point")
            pos[0] = pts[0]
        w(f"G1 F1800 Z{z:.3f}")
        qx, qy = pos[0]
        d0 = math.hypot(pts[0][0] - qx, pts[0][1] - qy)
        # zs is layer-relative (PRESS_HARD..lift); the layer offset must be applied here exactly
        # as it is in the loop below, or a layer-2 gap-close would extrude down at layer-1 Z
        z0 = (z - machine.PRESS_HARD + zs[0]) if zs else z
        if d0 > 0.02:                      # close the gap AS EXTRUSION, properly metered
            e += d0 * e_per_mm
            w(f"G1 F{f} X{pts[0][0]:.3f} Y{pts[0][1]:.3f} Z{z0:.3f} E{e:.5f}")
        else:
            w(f"G1 F{f}")
        qx, qy = pts[0]
        for i, (X, Y) in enumerate(pts[1:], 1):
            d = math.hypot(X - qx, Y - qy)
            if d < 0.02:
                continue
            e += d * e_per_mm
            zz = (z - machine.PRESS_HARD + zs[i]) if zs else z
            w(f"G1 X{X:.3f} Y{Y:.3f} Z{zz:.3f} E{e:.5f}")
            qx, qy = X, Y
        last[0] = (qx, qy)
        pos[0] = (qx, qy)

    last = [None]

    def circle(r, n=None):
        """Start each ring where the previous stroke ENDED.

        Without this the head finishes the rose at one angle and starts the rim at angle 0, and
        because every move extrudes, that lays a stray bead straight across the floor. Aligning
        the start angle keeps the whole layer one continuous stroke with no crossing -- which is
        the project's no-dry-travel rule and, here, also just a cleaner floor.
        """
        n = n or max(64, int(2 * math.pi * r / 0.6))
        a0 = 0.0
        if last[0] is not None:
            a0 = math.atan2(last[0][1] - cy, last[0][0] - cx)
        return [(cx + r * math.cos(a0 + 2 * math.pi * i / n),
                 cy + r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n + 1)]

    n_layers = int(round((a.height - machine.PRESS_HARD) / a.layer_h)) + 1
    rim_passes = int(round(rim / bw))
    first = True
    for k in range(n_layers):
        z = machine.PRESS_HARD + k * a.layer_h
        if k < a.floor_layers:
            # floor: the rose, then the rim ring passes, all at full flow.
            # EVERY stroke lifts over material laid EARLIER IN THIS LAYER: the rose over its own
            # crossings, each rim pass over the rose tips it crosses (the innermost rim runs
            # exactly through all 13 of them) and over any earlier pass it grazes.
            stroke(rose_pts, z, first, zs=rose_z); first = False
            prior = list(rose_pts)
            for j in range(rim_passes):
                cpts = circle(R - bw / 2 - j * bw)
                cz, _ = crossing_z(cpts, bw, machine.PRESS_HARD, 0.5, prior=prior)
                stroke(cpts, z, False, zs=cz)
                prior += cpts
        elif k < a.floor_layers + a.fillet:
            # fillet: step from the full rim down to one bead so the wall grows out of the floor
            kk = (k - a.floor_layers) / max(a.fillet - 1, 1)
            npass = max(1, int(round(rim_passes * (1.0 - kk) + 1 * kk)))
            for j in range(npass):
                stroke(circle(R - bw / 2 - j * bw), z, first and j == 0); first = False
        else:
            stroke(circle(R - bw / 2), z, False)

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G1 Z{a.height + 30:.1f} F900")
    g = "\n".join(x for x in L if x) + "\n"

    print(f"  {n_cross} of {len(rose_pts)} rose points ride over a crossing "
          f"(Z {machine.PRESS_HARD} -> 0.5)")
    print(f"  {n_layers} layers; floor {a.floor_layers}, fillet {a.fillet} "
          f"({rim_passes} -> 1 bead), then a single-bead wall")
    grams = e * A * 1.24 / 1000.0
    print(f"  ~{grams:.0f} g")
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"bucket_{a.printer}_d{a.dia:.0f}_h{a.height:.0f}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
