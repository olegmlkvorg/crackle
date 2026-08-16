#!/usr/bin/env python3
"""Emit the first signs proof as toolpath-native G-code.

The proof is a 240 mm rounded lightbox body printed back-down.  A solid three-layer back supports
an 18 mm double-bead perimeter wall.  A low inner rail leaves a 12 mm raceway for common 8-10 mm
LED strip while keeping the centre open for light diffusion.  The face/diffuser is deliberately a
separate, unproven assembly item: this artifact tests the printed body first.

Usage: python3 signs/desk_logo.py
"""
import argparse
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import machine


def rounded_rect(cx, cy, width, depth, radius, step=1.0):
    """Clockwise closed rounded rectangle, sampled at no more than ``step`` mm."""
    radius = min(radius, width / 2, depth / 2)
    points = []
    corners = (
        (cx + width / 2 - radius, cy - depth / 2 + radius, -90),
        (cx + width / 2 - radius, cy + depth / 2 - radius, 0),
        (cx - width / 2 + radius, cy + depth / 2 - radius, 90),
        (cx - width / 2 + radius, cy - depth / 2 + radius, 180),
    )
    n = max(6, math.ceil(math.pi * radius / (2 * step)))
    for x0, y0, start in corners:
        for i in range(n + 1):
            a = math.radians(start + 90 * i / n)
            points.append((x0 + radius * math.cos(a), y0 + radius * math.sin(a)))
    points.append(points[0])
    return points


def capsule_spans(cx, cy, width, depth, y):
    """Horizontal material span through the rounded rectangle at ``y``."""
    r = depth / 2
    dy = abs(y - cy)
    if dy > r:
        return None
    straight = width / 2 - r
    reach = straight + math.sqrt(max(0.0, r * r - dy * dy))
    return cx - reach, cx + reach


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default="pla", choices=sorted(machine.MATERIAL_TEMP))
    ap.add_argument("--width", type=float, default=240.0)
    ap.add_argument("--depth", type=float, default=96.0)
    ap.add_argument("--wall-h", type=float, default=18.0)
    ap.add_argument("--back-layers", type=int, default=4)
    ap.add_argument("--channel", type=float, default=12.0,
                    help="clear LED raceway from inner face of perimeter to retention rail")
    ap.add_argument("--rail-h", type=float, default=2.4)
    ap.add_argument("--bead-w", type=float, default=1.2)
    ap.add_argument("--layer-h", type=float, default=0.4)
    ap.add_argument("--speed", type=float, default=25.0)
    ap.add_argument("--h1", type=float, default=0.10)
    ap.add_argument("--w1", type=float, default=2.0)
    ap.add_argument("--zerr", type=float, default=0.15)
    ap.add_argument("--out", default="signs")
    a = ap.parse_args()

    if a.width > 300 or a.depth > 300:
        raise SystemExit("REFUSING TO EMIT: proof must fit a consumer 300 mm-class bed")
    if a.bead_w < 0.8 or a.bead_w > 1.2 or abs(a.layer_h - 0.4) > 1e-9:
        raise SystemExit("REFUSING TO EMIT: this proof is evidenced only at 0.8-1.2 x 0.4 mm")
    if a.channel < 10 or a.channel > 14:
        raise SystemExit("REFUSING TO EMIT: LED channel must remain 10-14 mm clear")
    if a.wall_h < 12 or a.wall_h > 24:
        raise SystemExit("REFUSING TO EMIT: proof wall height must remain 12-24 mm")
    if a.back_layers < 3:
        raise SystemExit("REFUSING TO EMIT: the flat back needs at least three body layers")
    if a.speed > machine.DEFAULT_SPEED:
        raise SystemExit("REFUSING TO EMIT: speed exceeds the 50 mm/s north star")

    bx, by = machine.BED[a.printer]
    if a.width > bx - 20 or a.depth > by - 20:
        raise SystemExit(f"REFUSING TO EMIT: {a.width:g}x{a.depth:g} does not fit {bx:g}x{by:g}")
    cx, cy = bx / 2, by / 2
    temp = machine.temp_for(a.material)
    bed = machine.bed_for(a.material, a.printer)
    press = machine.PRESS_HARD
    zoff = machine.zoff_for(a.h1, a.zerr)
    f = round(a.speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    e1_rate = machine.layer1_rate(a.w1, a.h1)
    body_rate = a.bead_w * a.layer_h / machine.A_FIL
    flow = a.bead_w * a.layer_h * a.speed
    wall_layers = 1 + math.ceil((a.wall_h - press) / a.layer_h)
    rail_layers = 1 + math.ceil((a.rail_h - press) / a.layer_h)
    back_top = press + (a.back_layers - 1) * a.layer_h

    # Two perimeter beads make a ~2.2 mm return. A conventional 0.4 nozzle can reproduce that as
    # five lines; this path-native K2 artifact uses the installed 0.8 nozzle's accurate 1.2 mm bead.
    outer = rounded_rect(cx, cy, a.width - a.bead_w, a.depth - a.bead_w,
                         a.depth / 2 - a.bead_w / 2)
    outer2 = rounded_rect(cx, cy, a.width - 3 * a.bead_w, a.depth - 3 * a.bead_w,
                          a.depth / 2 - 1.5 * a.bead_w)
    rail_inset = 2 * a.bead_w + a.channel
    rail = rounded_rect(cx, cy, a.width - 2 * rail_inset, a.depth - 2 * rail_inset,
                        a.depth / 2 - rail_inset)
    rail2 = rounded_rect(cx, cy, a.width - 2 * rail_inset - 2 * a.bead_w,
                         a.depth - 2 * rail_inset - 2 * a.bead_w,
                         a.depth / 2 - rail_inset - a.bead_w)

    out_dir = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    os.makedirs(out_dir, exist_ok=True)
    name = (f"desk_logo_{a.printer}_{a.material}_{a.width:.0f}x{a.depth:.0f}_"
            f"h{a.wall_h:.0f}_ch{a.channel:.0f}_bw{a.bead_w:g}_lh{a.layer_h:g}.gcode")
    out_path = os.path.join(out_dir, name)
    L = []
    w = L.append
    cmd = "python3 signs/desk_logo.py" + ((" " + " ".join(sys.argv[1:])) if sys.argv[1:] else "")

    w(f"; SIGNS DESK-LOGO PROOF — {a.width:g}x{a.depth:g}x{a.wall_h:g}mm indoor lightbox body")
    w("; STAGE=PHYSICAL PROOF FILE; design gate passed does not mean printed or tested")
    w(f"; CMD={cmd}")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={a.layer_h:g}")
    w(f"; SPEED={a.speed:.4f}")
    w(f"; SPEED_LAYER1={a.speed:.4f}")
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; LAYER1_WIDTH={a.w1:.2f}mm landed in the {a.h1:g} gap")
    w(f"; PRINT_TEMP={temp}")
    w(f"; PROOF_GEOMETRY=solid back {back_top:.1f}mm; double return ~{2*a.bead_w:.1f}mm; "
      f"LED raceway {a.channel:g}mm; retention rail {a.rail_h:g}mm")
    w(f"; FLOW_DERATE=accurate wall placement: {a.bead_w:g}x{a.layer_h:g}mm bead at "
      f"{a.speed:g}mm/s = {flow:g}mm3/s; this proof values straight, aligned light-sealing "
      f"returns over maximum throughput")
    w("; FACE=separate diffuser/removable face not included in this body proof")
    w("; USE=movable indoor low-voltage desk object only")
    w("; MATERIAL_PLACEHOLDER")
    mat_line = len(L) - 1
    w("M82")
    w("G90")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    w("G28")
    w(f"SET_GCODE_OFFSET Z={zoff:.3f} ; first layer lands at {a.h1:g}mm")
    w(f"M190 S{bed:.0f}")
    w(f"M109 S{temp}")
    w(f"M106 S{int(round(machine.fan_first_layer(a.material) * 255))}")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")
    machine.prime(w, printer=a.printer, z=press, rate=e1_rate, feed=f,
                  travel_feed=travel_f,
                  avoid=(("rect", cx-a.width/2, cy-a.depth/2,
                          cx+a.width/2, cy+a.depth/2),), near=(cx-a.width/2, cy-a.depth/2))
    w("; BODY_START")

    E = 0.0
    x = y = None

    def hop_to(px, py, z, label):
        nonlocal x, y
        safe = max(back_top, z) + a.layer_h + 0.4
        w(f"G0 Z{safe:.3f} F1800 ; HOP {label}")
        w(f"G0 X{px:.3f} Y{py:.3f} F{travel_f} ; HOP {label}")
        w(f"G1 Z{z:.3f} F600")
        x, y = px, py

    def draw(path, z, rate, label):
        nonlocal E, x, y
        hop_to(path[0][0], path[0][1], z, label)
        first = True
        for px, py in path[1:]:
            d = math.hypot(px - x, py - y)
            if d < 1e-8:
                continue
            E += d * rate
            w(f"G1 {'F%d ' % f if first else ''}X{px:.3f} Y{py:.3f} Z{z:.3f} E{E:.5f}")
            x, y, first = px, py, False

    # Flat back: horizontal boustrophedon rows. Pitch follows landed width on layer 1 and uses
    # 17% overlap above it, so adjacent beads merge instead of meeting at a zero-overlap butt joint.
    for k in range(a.back_layers):
        z = press + k * a.layer_h
        rate = e1_rate if k == 0 else body_rate
        pitch = a.w1 * 0.80 if k == 0 else a.bead_w * 0.83
        n = max(1, int(a.depth / pitch))
        ys = [cy - a.depth/2 + a.bead_w/2 + i * (a.depth - a.bead_w) / n
              for i in range(n + 1)]
        rows = []
        for i, yy in enumerate(ys):
            span = capsule_spans(cx, cy, a.width - a.bead_w, a.depth - a.bead_w, yy)
            if span:
                # Every row runs the same direction. Alternating made the validator correctly see
                # dozens of 180-degree reversals converging at the capsule ends, even though the
                # head hopped between them; the bead still arrived at every end from both sides.
                rows.append((span, yy))
        for i, (span, yy) in enumerate(rows):
            draw([(span[0], yy), (span[1], yy)], z, rate, f"back L{k+1} row {i+1}")
        # Raster endpoints sample the capsule's tight end radii sparsely near the tangent. Trace
        # the two future return centrelines on every back layer so the wall has exact bead-under-
        # bead support instead of asking the endpoint envelope to approximate a structural lap.
        draw(outer, z, rate, f"back outer support L{k+1}")
        draw(outer2, z, rate, f"back inner support L{k+1}")
        draw(rail, z, rate, f"back LED-rail support L{k+1}")
        draw(rail2, z, rate, f"back LED-rail inner support L{k+1}")

    # Raise the return and the LED retention rail from the already-solid back.
    for k in range(a.back_layers, wall_layers):
        z = press + k * a.layer_h
        if k == a.back_layers:
            fan = int(round(machine.fan_for(a.material, 1.0) * 255))
            w(f"M106 S{fan}")
        draw(outer, z, body_rate, f"outer return L{k+1}")
        draw(outer2, z, body_rate, f"inner return L{k+1}")
        if k < a.back_layers + rail_layers:
            draw(rail, z, body_rate, f"LED rail L{k+1}")
            draw(rail2, z, body_rate, f"LED rail inner L{k+1}")

    w("; ---- done")
    w("SET_GCODE_OFFSET Z=0")
    w("M107")
    w("M104 S0")
    w("M140 S0")
    w(f"G0 Z{a.wall_h + 40:.1f} F900")
    w(f"G0 X10 Y{by-10:.0f} F{travel_f}")
    w("M84")
    vol = E * machine.A_FIL / 1000
    L[mat_line] = f"; MATERIAL={vol*1.24:.1f}g / {vol:.2f}cm3 from final emitted E"
    with open(out_path, "w") as fh:
        fh.write("\n".join(L) + "\n")
    print(out_path)
    print(f"  {a.width:g}x{a.depth:g}mm body, {a.wall_h:g}mm return, {a.channel:g}mm LED raceway")
    print(f"  {a.back_layers} back layers to Z{back_top:.1f}; {vol:.2f}cm3 / {vol*1.24:.1f}g")


if __name__ == "__main__":
    main()
