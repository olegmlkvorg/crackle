#!/usr/bin/env python3
"""CROWNED PULLEY — for the cleated belt lift, emitted as one continuous extrusion.

Oleg: "you can use k1 to print gears and holder stuff meanwhile".

A pulley is normally a SOLID part: perimeters plus infill, which nothing in this toolchain emits,
and which would mean going out to trimesh -> STL -> a slicer GUI. So it is built here the way
everything else is -- as one continuous path -- by making the solid parts rings and the fill a web:

    per layer:  outer rim  ->  spoke inward  ->  bore ring  ->  spoke outward  ->  next layer

The spoke angles ADVANCE every layer, so the web is a spiral staircase of struts rather than three
tall unsupported blades stacked on themselves. That both braces the rim and means no spoke is ever
printed in mid-air over the gap.

CROWN. The rim radius bulges by `crown` at mid-height, following a circular arc. This is not
decoration: a flat pulley lets a flat belt wander off the end, while a crowned one self-centres --
the belt always climbs toward the largest diameter, which is the middle. It is why every flat-belt
machine has crowned pulleys.

BORE. A 6mm D-profile socket to match a standard motor shaft, cut as a flat chord. Printed bores
come out about 0.25mm undersize on these machines (measured, see connector_family.py in
~/Desktop/spiral-vase), so the modelled bore is oversized to compensate rather than hoping.
"""
import argparse
import math
import os

import sys as _sys

import machine

SHRINK = 0.25       # measured: printed bore = modelled - 0.25 on the Creality machines


def d_bore(r, flat_depth, n=180, a_start=0.0, sweep=None):
    """A D-profile: a circle of radius r with one side cut back to a flat chord.

    `a_start`/`sweep` let each spoke walk its OWN arc of the bore. Taking the first N points three
    times instead drew the same arc three times over and left a 60-degree hole in the bore wall --
    caught by measuring the largest angular gap between emitted bore points, not by looking at it.
    """
    if sweep is None:
        sweep = 2 * math.pi
    y_flat = r - flat_depth
    pts = []
    steps = max(4, int(n * sweep / (2 * math.pi)))
    for i in range(steps + 1):
        a = a_start + sweep * i / steps
        x, y = r * math.cos(a), r * math.sin(a)
        if y > y_flat:                       # inside the cut-off cap -> project onto the flat
            if abs(math.cos(a)) < 1e-9:
                continue
            x = y_flat / math.tan(a) if abs(math.tan(a)) > 1e-9 else x
            x = max(-r, min(r, x))
            y = y_flat
        pts.append((x, y))
    pts.append(pts[0])
    return pts


def decimate(pts, min_seg=0.25):
    """Drop points closer together than `min_seg`.

    d_bore projects every circle point that falls beyond the chord ONTO the flat, so a whole arc of
    angles collapses onto a few millimetres of straight line — segments down to 0.006mm, which is
    5145 moves/s at 30 mm/s against a ~300/s host limit. Klipper freezes with no error. Same failure
    as shapely's fixed-96-segment circles in solid.py, different source; both are "points generated
    by angle, consumed by distance"."""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for p in pts[1:-1]:
        if math.dist(p, out[-1]) >= min_seg:
            out.append(p)
    out.append(pts[-1])
    return out


def ring(r, n=240, phase=0.0):
    return [(r * math.cos(2 * math.pi * i / n + phase),
             r * math.sin(2 * math.pi * i / n + phase)) for i in range(n + 1)]


def spiral_between(r0, r1, a0, turns_frac, n=60):
    """A gentle spiral from radius r0 to r1 — the spoke. Not a straight radial line: a radial jump
    is a 90-degree corner at each end, and a corner is where Klipper drops to square_corner_velocity
    while E keeps metering per mm of path."""
    out = []
    for i in range(n + 1):
        t = i / n
        r = r0 + (r1 - r0) * t
        a = a0 + turns_frac * 2 * math.pi * t
        out.append((r * math.cos(a), r * math.sin(a)))
    return out


def emit(od, width, bore_d, flat_depth, crown, flange, spokes, bead_w, layer_h, flow, temp, bed,
         fil_d, bed_xy, home, press, fan, spoke_adv, sleeve=0, first_w=3.0, aux=0.2,
         brim=0, printer='k1c', material='pla'):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (bead_w * layer_h) / area
    # HARD CAP the head speed, then re-derive the flow that speed actually delivers.
    # Capping speed without lowering flow would over-extrude by the same ratio.
    speed = min(flow / (bead_w * layer_h), machine.MAX_SPEED)
    flow = speed * bead_w * layer_h
    f = round(speed * 60)
    layers = max(2, int(round(width / layer_h)))
    # BASE LAYER PRESSED TO THE PLATE. Oleg, after a pulley turned into spaghetti: "make sure you
    # are at 0.1 close to bed when you extrude base layer". A 0.25mm first layer is not pressed, it
    # is merely near — and a part that lets go becomes a ball of filament.
    #
    # But the base layer CANNOT carry a full 0.9mm bead's worth of material through a 0.1mm gap:
    # that is 9x too much, it packs against the plate and the extruder skips (measured earlier today
    # when the honeycomb ran a 0.72mm2 bead at Z0.1 and skipped). So the base layer is metered as
    # what it physically is — a thin WIDE ribbon: 0.1mm tall, spread to first_w.
    first_h = press
    e_first = (first_w * first_h) / area
    speed_first = min(flow / (first_w * first_h), 30.0)   # slow: adhesion, not throughput
    f_first = round(speed_first * 60)

    r_bore = bore_d / 2 + SHRINK / 2
    if sleeve:
        # SLEEVE MODE: a plain tube of `sleeve` concentric walls -- a bamboo stick coupler, not a
        # pulley. No web, because there is no annulus to fill: the wall IS the part. The pulley's
        # guard below reserves room for spokes and would reject a perfectly good 3mm-walled sleeve.
        if od / 2 <= r_bore + sleeve * bead_w:
            raise SystemExit(f"OD {od} is too small for a {bore_d}mm bore with {sleeve} walls of "
                             f"{bead_w}mm — need at least {2*(r_bore + sleeve*bead_w):.1f}mm.")
    elif r_bore + 2.5 * bead_w >= od / 2 - 2 * bead_w:
        raise SystemExit(f"a {bore_d}mm bore leaves no material inside a {od}mm pulley.")

    # SPOKE ADVANCE IS BOUNDED BY OVERHANG, not chosen. A rotating web is only self-supporting if
    # each layer's spoke still lands on the one below: the lateral shift at the OUTER radius is
    # adv * r_out, against a layer height of layer_h, so the overhang from horizontal is
    # atan(layer_h / (adv * r_out)).
    #
    # 0.09 rad/layer was fine on a 40mm pulley (r20 -> 1.8mm shift, 12.5deg) and SNAPPED THE MODEL
    # on a 60mm one (r30 -> 2.7mm, 8deg — printing in mid-air). The constant was tuned on one
    # radius and silently became wrong on another; derive it instead.
    _r_out = od / 2.0 + crown + flange
    _adv_max = layer_h / (math.tan(math.radians(40.0)) * max(_r_out, 1e-6))
    if spoke_adv > _adv_max:
        print(f"  spoke advance {spoke_adv:.3f} would overhang at "
              f"{math.degrees(math.atan(layer_h / (spoke_adv * _r_out))):.0f}deg — "
              f"capped to {_adv_max:.4f} rad/layer (40deg)")
        spoke_adv = _adv_max

    cx, cy = bed_xy[0] / 2.0, bed_xy[1] / 2.0
    L = []
    w = L.append
    w(f"; CROWNED PULLEY — OD {od}mm, {width}mm wide, {bore_d}mm D-bore, {spokes} spokes")
    w(f"; crown +{crown}mm at mid-height (self-centres a flat belt), flange +{flange}mm at the ends")
    w(f"; bead {bead_w}x{layer_h} at {speed:.0f} mm/s -> flow={flow} mm3/s, {layers} layers")
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
    # FAN OFF FOR LAYER 1, CLAMPED BY MATERIAL AFTER. Oleg: "fans for printing pla should be only
    # on 20% at most". This defaulted to 80/255 = 31% and ran from the first millimetre, chilling
    # the bond while it formed — the cheapest possible way to lose a first layer.
    _fan_body = int(round(machine.fan_for(material, (fan or 0) / 255.0) * 255))
    w("M107                              ; layer 1: no part cooling, let it bond")
    # Oleg: "other fans to 20%". side/chassis fans move air through the chamber without blasting
    # the bead the way the part fan does.
    # PER-MACHINE fan syntax. Hardcoding the K1C form here put SET_FAN_SPEED
    # FAN=side_fan into a K2 file — a command that machine does not have, which
    # would have errored out a 76-minute print. Ask machine.aux_fans().
    for _ln in machine.aux_fans(printer, aux):
        w(_ln)
    w("M82")
    w("G92 E0")

    path_layers = []
    cur_ang = 0.0
    for k in range(layers):
        t = k / max(1, layers - 1)
        # crown: circular bulge, maximum at mid-height
        r_rim = od / 2 + crown * math.sin(math.pi * t)
        # flanges: the outer few layers step out to keep the belt on
        edge = min(k, layers - 1 - k) * layer_h
        if edge < 2.0:
            # ramp, not a step: a sudden +2.5mm between two layers is a 2.5mm jump in the path
            r_rim += flange * (1.0 - edge / 2.0)
        a0 = spoke_adv * k
        # START THE RIM WHERE THE LAST SPOKE LEFT OFF. Restarting it at a fixed angle left a chord
        # across the pulley face -- a 31mm straight extruded move, the same class of artifact as the
        # honeycomb's closing chord. The rim is a circle, so it can start anywhere.
        if sleeve:
            # concentric walls, joined by a short spiral so the layer stays one path
            pts = []
            for wi in range(sleeve):
                r_w = r_bore + bead_w / 2 + wi * bead_w
                pts += [(r_w * math.cos(cur_ang + 2 * math.pi * t / 240),
                         r_w * math.sin(cur_ang + 2 * math.pi * t / 240)) for t in range(241)]
                if wi < sleeve - 1:
                    pts += spiral_between(r_w, r_bore + bead_w / 2 + (wi + 1) * bead_w,
                                          cur_ang, 0.06, n=20)
                    cur_ang += 0.06 * 2 * math.pi
            cur_ang += spoke_adv
            path_layers.append(decimate(pts))
            continue
        # ONE UNBROKEN CIRCUIT PER LAYER, with every join at the same point/radius:
        #   full rim circle (ends where it began)
        #   -> spiral inward
        #   -> full bore circle (ends where it began)
        #   -> spiral outward, landing on the rim
        # and the NEXT layer's rim starts exactly there. Two spokes per layer, rotating with
        # spoke_adv. My earlier attempts advanced the angle by hand at each stage and left a 36mm
        # chord and a 170-degree hole in the bore -- the fix is to make every segment start where
        # the previous one ended, by construction, rather than to keep correcting the arithmetic.
        # THE WALL'S PATH SITS HALF A BEAD OUT FROM THE HOLE, NOT A WHOLE ONE.
        # This was `r_bore + bead_w`, which puts the bead's INNER FACE a full bead from centre and
        # opens the hole to 7.45mm while the header keeps reporting 6.25 — 1.2mm of slop on a 6mm
        # axle, and with --flat the D never touches the shaft's flat so no torque is transmitted.
        # The sleeve path in this same file has always used bead_w/2 and is the part Oleg pressed
        # onto the motor and called a perfect fit; the two disagreed and only one was ever tested.
        r_b = r_bore + bead_w / 2
        pts = [(r_rim * math.cos(cur_ang + 2 * math.pi * t / 240),
                r_rim * math.sin(cur_ang + 2 * math.pi * t / 240)) for t in range(241)]
        a_in = cur_ang + 0.12 * 2 * math.pi
        pts += spiral_between(r_rim, r_b, cur_ang, 0.12)
        pts += d_bore(r_b, flat_depth, a_start=a_in, sweep=2 * math.pi)
        # UNWIND ON THE WAY OUT. The inward spiral advances 0.12 turn and the outward one used to
        # advance another 0.12, so every layer rotated 1.51 rad no matter what spoke_adv said — the
        # web's rotation was a side effect of the spokes' own angular travel, and capping spoke_adv
        # changed nothing. That is why the 60mm wheel snapped: 1.51 rad at r30 is a 45mm lateral
        # shift on a 0.4mm layer, i.e. the spoke printed in mid-air.
        # Spiralling BACK the other way cancels it, so the layer advances by exactly spoke_adv.
        pts += spiral_between(r_b, r_rim, a_in, -0.12)
        cur_ang = a_in - 0.12 * 2 * math.pi + spoke_adv
        path_layers.append(decimate(pts))

    # BRIM. Oleg: "for puley first layer adhesion was not perfect, double check (start with brim
    # layer)". A 40mm pulley standing 29mm tall has a tiny footprint holding down a tall part that
    # the head keeps reversing around — the base layer being pressed is necessary but not
    # sufficient, it also needs AREA.
    #
    # Built as an Archimedean spiral running INWARD, which is the shape that needs no joins at all:
    # r falls linearly while theta advances, so consecutive brim rings are one unbroken curve with
    # no corner anywhere, and it arrives exactly at the point where layer 1 starts. No travel, no
    # seam, and the last ring touches the part so it actually holds it.
    if brim:
        r_first = math.dist((0, 0), path_layers[0][0])
        gap = first_w * 0.9                      # slight overlap so rings fuse into one sheet
        r_out = r_first + brim * gap
        if 2 * (r_out + 4) > min(bed_xy):
            raise SystemExit(f"a {brim}-ring brim reaches r{r_out:.0f}mm — off a "
                             f"{bed_xy[0]:.0f}mm plate. Lower --brim.")
        a_start = math.atan2(path_layers[0][0][1], path_layers[0][0][0])
        n_b = max(60, int(brim * 120))
        brim_pts = []
        for i in range(n_b + 1):
            t = i / n_b
            th = a_start + (t - 1.0) * 2 * math.pi * brim
            r = r_out + (r_first - r_out) * t
            brim_pts.append((r * math.cos(th), r * math.sin(th)))
        path_layers[0] = brim_pts + path_layers[0]

    x0, y0 = path_layers[0][0]
    w(f"G1 Z{press:.3f} F600")
    w(f"G0 F9000 X{cx + x0 - 45:.3f} Y{cy + y0:.3f}")
    w("G1 E25 F300                      ; stationary purge — pressure before motion")
    w(f"G1 F1200 X{cx + x0:.3f} Y{cy + y0:.3f} E37   ; prime ends where the rim begins")
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
    px = py = None
    for k, pts in enumerate(path_layers):
        z = press + k * layer_h
        if k:
            e += layer_h * e_per_mm
            L.append(f"G1 F{round(min(speed, 20)*60)} Z{z:.3f} E{e:.5f}")
            L.append(f"G1 F{f}")
        for (x, y) in pts:
            X, Y = cx + x, cy + y
            if px is None:
                px, py = X, Y
                continue
            d = math.dist((px, py), (X, Y))
            if d < 1e-9:
                continue
            e += d * (e_first if k == 0 else e_per_mm)
            L.append(f"G1 {'F%d ' % (f_first if k == 0 else f) if e < 1 or k == 1 else ''}"
                     f"X{X:.3f} Y{Y:.3f} Z{z:.3f} E{e:.5f}")
            px, py = X, Y

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{press + width + 40:.1f} F900",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(adv=spoke_adv, flow=round(flow, 1), layers=layers, grams=round(grams, 1), speed=round(speed),
                                     mins=round(e / e_per_mm / speed / 60, 1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--od", type=float, default=40.0)
    ap.add_argument("--width", type=float, default=29.0, help="belt width + flange room")
    ap.add_argument("--bore", type=float, default=6.0, help="D-shaft diameter")
    ap.add_argument("--flat", type=float, default=0.5, help="depth of the D flat")
    ap.add_argument("--crown", type=float, default=0.6)
    ap.add_argument("--flange", type=float, default=2.5)
    ap.add_argument("--spokes", type=int, default=3)
    ap.add_argument("--sleeve", type=int, default=0,
                    help="plain tube of N concentric walls (a stick coupler), no web")
    ap.add_argument("--spoke-adv", type=float, default=0.09, help="radians the web advances/layer")
    ap.add_argument("--bead-w", type=float, default=1.2)
    ap.add_argument("--layer-h", type=float, default=0.4)
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--temp", type=int, default=machine.TEMP)
    ap.add_argument("--bed", type=int, default=0,
                    help="0 = machine.BED_TEMP for the material; 120 WELDS TPU")
    ap.add_argument("--press", type=float, default=0.10, help="base-layer gap — pressed")
    ap.add_argument("--first-w", type=float, default=3.0, help="base-layer ribbon width")
    ap.add_argument("--aux", type=float, default=0.2, help="side/chassis fan speed 0-1")
    ap.add_argument("--brim", type=int, default=5, help="brim rings on layer 1 (0 = none)")
    ap.add_argument("--fan", type=int, default=51,
                    help="0-255. 51 = 20%%, the PLA ceiling (machine.FAN_MAX). "
                         "Layer 1 always prints with the fan OFF regardless.")
    ap.add_argument("--material", default="pla",
                    choices=["pla","petg","tpu","abs"],
                    help="stamped into the file; TPU is fan-guarded")
    ap.add_argument("--printer", default="k1c", choices=sorted(machine.BED))
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    bxy = machine.BED[a.printer]
    g, st = emit(a.od, a.width, a.bore, a.flat, a.crown, a.flange, a.spokes, a.bead_w, a.layer_h,
                 a.flow, a.temp, a.bed or machine.BED_TEMP[a.material], 1.75, bxy, not a.no_home, a.press, a.fan, a.spoke_adv,
                 a.sleeve, a.first_w, a.aux, a.brim, a.printer,
                 a.material)
    os.makedirs(a.out, exist_ok=True)
    fn = f"{a.out}/pulley_{a.printer}_od{a.od:.0f}_w{a.width:.0f}_b{a.bore:.0f}D_T{a.temp}.gcode"
    open(fn, "w").write(g)
    print(f"{fn}")
    print(f"  OD {a.od}mm (+{a.crown} crown, +{a.flange} flange), {a.width}mm wide, "
          f"{a.bore}mm D-bore modelled {a.bore + SHRINK:.2f} for shrink")
    print(f"  {st['layers']} layers, {a.spokes} spokes advancing {st['adv']:.4f} rad/layer")
    print(f"  {st['speed']} mm/s at flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g")
