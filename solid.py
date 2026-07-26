#!/usr/bin/env python3
"""SOLID PARTS AS ONE CONTINUOUS PATH — concentric contours, no slicer.

The gap this closes: every generator here emits thin-wall geometry (a lattice, a ribbon, a belt, a
pulley whose fill is a spoke web). A bracket, a bearing block, a clamp -- anything that is genuinely
SOLID -- needed perimeters and infill, which meant going out to trimesh -> STL -> a slicer GUI, and
that is not autonomous. Oleg: "we dont do normal slicing, everhything we print is path based gen we
discovered today".

The method: take a 2D region (a shapely polygon, holes and all) and walk it INWARD in concentric
contours spaced one bead apart, until nothing is left. Concentric fill is not a compromise for small
mechanical parts -- it is stronger than rectilinear infill because every pass follows the load path
around holes instead of cutting across it.

    contour 0 = region.buffer(-bead/2)      the outer wall's centreline
    contour n = contour n-1 .buffer(-bead)  each one bead further in
    stop when the buffer comes back empty

Two things this has to get right, both learned the hard way today:
  · buffer() can return a MultiPolygon (a region pinches into separate islands) or drop holes.
    Handle both, or the part silently comes out with a missing wall.
  · Consecutive contours are separate closed loops, so linking them is the only place a jog can
    occur. Those jogs are INSIDE solid material -- they overprint, which this project accepts
    ("overprint or whatever but no sharp turning") -- and the start angle rotates per layer so the
    seam never stacks into a visible line.
"""
import argparse
import math
import os
import re

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.affinity import translate

import sys as _sys

import machine

# CONFIRMED 2026-07-25 at ~6mm: the pulley's D-bore was modelled 6.25 for a 6.0mm shaft and Oleg
# reports "the holes in puleys are perfect fit". So printed = model - 0.25 holds here, and a 1/4"
# stick (6.35) takes a 6.60 modelled bore. The spiral-vase README had flagged this figure as
# calibrated on a 4mm hole and unverified at larger sizes — it is now verified at 6.
SHRINK = 0.25


def contours(region, bead_w, max_rings=200):
    """Concentric centrelines, outermost first, spaced one bead apart."""
    rings = []
    cur = region.buffer(-bead_w / 2.0)
    n = 0
    while not cur.is_empty and n < max_rings:
        geoms = list(cur.geoms) if cur.geom_type == "MultiPolygon" else [cur]
        for g in geoms:
            if g.is_empty or g.area < (bead_w * bead_w):
                continue
            rings.append((n, list(g.exterior.coords)))
            # A HOLE IS A WALL TOO. Dropping interiors here would print a bracket whose bores have
            # no wall on the inside -- the part looks right in plan and is hollow where it matters.
            for ring in g.interiors:
                rings.append((n, list(ring.coords)))
        cur = cur.buffer(-bead_w)
        n += 1

    # DROP INFILL RINGS THAT COLLIDE WITH ONE ALREADY KEPT.
    # Walking inward from the outline and outward from a bore, the two ring families meet HEAD-ON
    # wherever the wall is not an integer number of beads. On the foot they landed 0.475mm apart
    # with a 1.2mm bead, overlapping over the ring's entire 47mm — and e_per_mm is a constant that
    # never notices. Measured: the foot deposited 0.4416mm per 0.400mm layer (+10.4%), the only
    # part in the batch over 1.0, and it climbed 0.042mm/layer until the nozzle ploughed it off the
    # plate. Both failures stopped at the SAME HEIGHT, which is the signature of accumulation, not
    # of adhesion.
    #
    # Generation 0 is never dropped — those are the part's outer wall and its bore walls. Only
    # interior fill rings can go, and a small medial void is exactly what every part that printed
    # correctly already had (bracket 7.5%, spacer 6.2%, coupler 16.5%).
    kept = []
    for gen, ring in rings:
        if gen == 0:
            kept.append(ring)
            continue
        line = LineString(ring)
        if line.length < 1e-9:
            continue
        clash = sum(1 for k in kept
                    if LineString(k).buffer(0.95 * bead_w).intersection(line).length
                    > 0.5 * line.length)
        if not clash:
            kept.append(ring)
    return kept


def decimate(loop, min_seg):
    """Drop points closer together than `min_seg`.

    Shapely renders a circle at 96 segments regardless of its radius, so a small inner contour
    arrives with segments of 0.009mm. At 30 mm/s that is 3354 moves per SECOND against a host that
    stalls around 300 -- Klipper simply freezes, which is what happened when a coupler was started.
    Curvature is unaffected: a 0.3mm chord on the smallest bore here is under 3 degrees of arc.
    """
    out = [loop[0]]
    for p in loop[1:-1]:
        if math.dist(p, out[-1]) >= min_seg:
            out.append(p)
    if math.dist(loop[-1], out[-1]) < min_seg and len(out) > 2:
        out.pop()
    out.append(loop[-1])
    return out


def densify(loop, step):
    """Split long straight edges into `step`-sized pieces.

    Shapely keeps a flat wall as two points, so a 30mm edge arrives as one segment. That breaks any
    rule expressed in terms of move length, and it also starves the motion planner of the points it
    needs to hold a constant speed through a corner.
    """
    out = [loop[0]]
    for a, b in zip(loop, loop[1:]):
        d = math.dist(a, b)
        n = max(1, int(math.ceil(d / step)))
        for i in range(1, n + 1):
            t = i / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def start_nearest(loop, here):
    """Rotate a closed loop to begin at the point nearest `here`."""
    core = loop[:-1] if loop[0] == loop[-1] else loop[:]
    if len(core) < 3:
        return loop
    k = min(range(len(core)), key=lambda i: math.dist(core[i], here))
    out = core[k:] + core[:k]
    return out + [out[0]]


def order_rings(rings, here):
    """Visit contours nearest-first, each entered at its closest point.

    Printing them in generation order drew a 43.9mm line straight across the part when the path
    stepped from one contour to the next -- and since every move extrudes, that line was laid down
    OVER the bores, bridging holes that are supposed to stay open. Greedy nearest-neighbour keeps
    every link down to roughly one bead, which stays inside solid material where an overprint is
    harmless.
    """
    todo = list(rings)
    out = []
    while todo:
        best_i, best_d, best_loop = 0, float('inf'), None
        for i, r in enumerate(todo):
            loop = start_nearest(r, here)
            d = math.dist(loop[0], here)
            if d < best_d:
                best_i, best_d, best_loop = i, d, loop
        out.append(best_loop)
        here = best_loop[-1]
        todo.pop(best_i)
    return out


def emit(region, height, bead_w, layer_h, flow, temp, bed, fil_d, bed_xy, home, press, fan,
         first_w, aux, printer, name, link_max=2.0, link_flow=0.3, min_seg=0.3, brim=4, brim_gap=0.18,
         material='pla', hop_min=8.0, centre=True):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (bead_w * layer_h) / area
    speed = machine.speed_for(flow, bead_w * layer_h, f" for {name}")
    flow = speed * bead_w * layer_h
    f = round(speed * 60)
    layers = max(1, int(round(height / layer_h)))
    e_first = (first_w * press) / area
    travel_f = int(machine.MACHINE_MAX_SPEED * 60)   # inter-object travel: machine max
    f_first = round(min(flow / (first_w * press), 20.0) * 60)

    # A region may be a fixed polygon OR a callable of layer fraction (see adapter()). Contours
    # are cached per distinct region so a 35-layer part does not re-buffer shapely 35 times.
    _is_fn = callable(region)
    _cache = {}

    def rings_at(kk):
        if not _is_fn:
            return rings
        t = kk / max(1, layers - 1)
        # CACHE ON THE REGION ITSELF, not on a guessed split point. This used to be
        # `key = round(t,3) < 0.5` — a BOOLEAN — so every per-layer part split at exactly half
        # height no matter what it asked for. Correct for the adapter by luck, wrong for a cavity
        # whose floor is 2.4mm of a 14mm part (t=0.17): the cavity started at layer 17 instead of 6.
        # The region's WKB is an exact identity, so distinct geometry gets computed once and
        # identical geometry is shared.
        reg = region(t)
        key = reg.wkb
        if key not in _cache:
            _cache[key] = contours(reg, bead_w)
        return _cache[key]

    # BRIM — Oleg: "k1 did not bind well to bed". These parts press their base layer to 0.1mm and
    # meter it as a wide thin ribbon, which is necessary but not sufficient: a 23mm foot standing
    # 14mm tall has almost no plate contact holding down a part the head keeps reversing around.
    # Extra contours OUTSIDE the region, layer 1 only, bought by buffering the region outward.
    rings = contours(region(0.0) if _is_fn else region, bead_w)

    # FILL RATIO GUARD — measure the emitted artifact, and FAIL rather than print a part that
    # climbs. fill = (total contour length x bead width) / region area. Above 1.0 the layer lays
    # more material than the Z step can hold; it has nowhere to go but up, and the nozzle
    # eventually ploughs the part off the plate. Below 1.0 is harmless porosity — every part that
    # printed correctly sat at 0.83-0.96. The foot as originally emitted was 1.082.
    _reg = region(0.0) if _is_fn else region
    _fill = sum(LineString(r).length for r in rings) * bead_w / max(_reg.area, 1e-9)
    if _fill > 1.02:
        # BEAD-MULTIPLE DIMENSIONS — Oleg's design rule from 2026-07-23, and this is the physics
        # behind it. A wall that is not an integer number of beads leaves the inward and outward
        # ring families colliding somewhere, and e_per_mm never notices. Measured on a 100mm
        # spacer: a 4.0mm flange (3.33 beads) fills 1.139 and would climb; 3.6 (3 beads) fills
        # 0.729 and 4.8 (4 beads) fills 0.981.
        _mult = [round(bead_w * k, 2) for k in range(2, 9)]
        raise SystemExit(
            f"{name}: contours cover {_fill:.3f}x the region — every layer deposits "
            f"{(_fill-1)*100:.1f}% more than the {layer_h}mm Z step can hold, so the part climbs "
            f"into the nozzle and gets ploughed off.\n"
            f"  Make wall thicknesses a MULTIPLE OF THE BEAD ({bead_w}mm): {_mult}\n"
            f"  A non-integer wall leaves the inward and outward contour families colliding.")
    base_extra = []
    if brim:
        src = region(0.0) if _is_fn else region
        for i in range(1, brim + 1):
            # HALF a bead, not a whole one: the part's outermost CENTRELINE sits half a
            # bead inside its boundary, so buffering by a full bead left the first brim
            # ring 1.8mm away with a 1.2mm bead — a 0.6mm void. The brim was never
            # touching the part, which is why adding one changed nothing.
            # A BRIM MUST DETACH. Oleg: "when you print brim it should be asily detachable,
            # no its not". Centrelines exactly one bead apart look like 'just touching' on paper,
            # but squish spreads each bead and they fuse. A small extra gap gives a light kiss:
            # enough to hold the part down while printing, weak enough to snap off by hand.
            g = src.buffer(bead_w * (i - 0.5) + brim_gap)
            for geo in (list(g.geoms) if g.geom_type == "MultiPolygon" else [g]):
                base_extra.append(list(geo.exterior.coords))
    if not rings:
        raise SystemExit(f"{name}: the region is smaller than one {bead_w}mm bead — nothing to print.")

    _allr = rings + base_extra + (contours(region(1.0), bead_w) if _is_fn else [])
    xs = [p[0] for r in _allr for p in r]
    ys = [p[1] for r in _allr for p in r]
    # CENTRING IS FOR A SINGLE PART ONLY.
    # A sequential plate hands emit() parts that are ALREADY positioned by the shelf packer.
    # Re-centring each one silently discarded that packing and stacked all 15 parts on the middle
    # of the bed — part 2 drove into finished part 1, which Oleg heard as a hit before the printer
    # reported abnormal resistance and shut down. Nothing in the file looked wrong: every move was
    # individually valid, and the coordinates were only obviously wrong when compared BETWEEN parts.
    if centre:
        ox = (bed_xy[0] - (max(xs) + min(xs))) / 2.0
        oy = (bed_xy[1] - (max(ys) + min(ys))) / 2.0
    else:
        ox = oy = 0.0
    if min(xs) + ox < 4 or min(ys) + oy < 4 or max(xs) + ox > bed_xy[0] - 4 \
            or max(ys) + oy > bed_xy[1] - 4:
        raise SystemExit(f"{name} spans {max(xs)-min(xs):.0f}x{max(ys)-min(ys):.0f}mm — "
                         f"off a {bed_xy[0]:.0f}x{bed_xy[1]:.0f} plate.")

    L = []
    w = L.append
    w(f"; {name} — solid part as concentric contours, one continuous path per layer")
    w(f"; {len(rings)} contours, bead {bead_w}x{layer_h}, {layers} layers = {height}mm tall")
    w(f"; {speed:.0f} mm/s at flow {flow:.1f} mm3/s (cap {machine.MAX_SPEED:.0f} mm/s)")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {layers}")
    w("; HEADER_BLOCK_END")
    w(f"M104 S{temp}")
    w("G90")
    w("G28" if home else "; NO HOME — assumes the machine is ALREADY homed; push.py verifies")
    w(f"M140 S{bed}")
    w(f"TEMPERATURE_WAIT SENSOR='heater_bed' MINIMUM={bed-3} MAXIMUM={bed+5}")
    w(f"M109 S{temp}")
    w("M204 S8000")
    w("M107" if not fan else f"M106 S{fan}")
    for ln in machine.aux_fans(printer, aux):
        w(ln)
    w("M82")
    w("G92 E0")

    x0, y0 = rings[0][0][0] + ox, rings[0][0][1] + oy
    w(f"G1 Z{press:.3f} F600")
    w(f"G0 F9000 X{max(6.0, x0 - 40):.3f} Y{max(6.0, y0):.3f}")
    w("G1 E20 F300                      ; stationary purge — pressure before motion")
    w(f"G1 F1200 X{x0:.3f} Y{y0:.3f} E30")
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
    for k in range(layers):
        z = press + k * layer_h
        if k:
            e += layer_h * e_per_mm
            L.append(f"G1 F{round(min(speed, 15)*60)} Z{z:.3f} E{e:.5f}")
            L.append(f"G1 F{f}")
        # THE BRIM MUST GO DOWN FIRST. Appending it to the ring list let order_rings reach it
        # LAST — measured at 75% through layer 1 — so the entire part was already printed before
        # any brim existed. A brim laid after the part cannot hold the part's first moments, which
        # is exactly why adding one did not stop the foot detaching.
        # Outermost brim ring first, working inward, then the part.
        if k == 0 and base_extra:
            brim_first = sorted(base_extra, key=lambda r: -max(
                (p[0] - ox) ** 2 + (p[1] - oy) ** 2 for p in r))
            ordered = ([start_nearest(r, (px - ox, py - oy) if px is not None else brim_first[0][0])
                        for r in brim_first]
                       + order_rings(rings_at(k), brim_first[-1][-1]))
        else:
            _rk = rings_at(k)
            ordered = order_rings(_rk, (px - ox, py - oy) if px is not None else _rk[0][0])
        for li, loop in enumerate(ordered):
            loop = decimate(densify(loop, 0.8), min_seg)
            for pi, (x, y) in enumerate(loop):
                X, Y = x + ox, y + oy
                if px is None:
                    px, py = X, Y
                    continue
                d = math.dist((px, py), (X, Y))
                if d < 1e-9:
                    continue
                # ONLY the step INTO a new loop may be a hop. A long move inside a loop is the
                # part's own straight wall -- shapely stores a flat edge as two points, so a naive
                # "long move = travel" rule turned this bracket's 30mm flat side into a travel and
                # produced 17 hops per layer. The link is pi == 0, and nothing else.
                if pi == 0 and d > hop_min:
                    # BETWEEN OBJECTS: TRAVEL. Oleg, 2026-07-26: "max out the speed when travel to
                    # next object and suspend the flow for a travel (dont retract)".
                    #
                    # The no-travel rule was written for a single continuous part, where a hop is a
                    # seam. Across a 15-part plate it is the opposite: a thin link between two parts
                    # 12mm apart is a string laid over open glass that welds the plate into one
                    # object and has to be cut off every part. So the rule holds INSIDE a part and
                    # inverts BETWEEN parts.
                    #
                    # No retract on purpose: retract/prime is the thing that leaves a blob at each
                    # end and needs pressure-advance tuning to hide. Simply not advancing E lets the
                    # melt relax on its own over a move that is over in a few hundredths of a second.
                    L.append(f"G0 X{X:.3f} Y{Y:.3f} Z{z:.3f} F{travel_f}")
                    # RESTORE THE PRINT FEEDRATE. F is STICKY in gcode: without this line the next
                    # extruding move inherits the travel's 120 mm/s and lays the bead at 106 mm3/s
                    # against a 36 target. Measured in the emitted file, not assumed.
                    L.append(f"G1 F{f_first if k == 0 else f}")
                    px, py = X, Y
                    continue
                if pi == 0 and d > link_max:
                    # LINK BETWEEN CONTOURS: extrude, but THIN. Two bad options were tried first.
                    # Extruding at full rate lays a second bead on top of one already at this Z --
                    # double height, and the nozzle drags through it next layer, which is how a
                    # tower came off the plate this morning. A G0 travel avoids that but breaks the
                    # project's no-travel rule and produced 133 travels in a 3-bore plate.
                    # A reduced-rate link is a thin connecting thread: it keeps the path continuous
                    # (the extruder never stops, so no ooze/restart artefact) and adds too little
                    # material to build a ridge.
                    e += d * (e_first if k == 0 else e_per_mm) * link_flow
                    L.append(f"G1 X{X:.3f} Y{Y:.3f} Z{z:.3f} E{e:.5f}")
                    px, py = X, Y
                    continue
                e += d * (e_first if k == 0 else e_per_mm)
                L.append(f"G1 {'F%d ' % (f_first if k == 0 else f) if (px, py) == (x0, y0) else ''}"
                         f"X{X:.3f} Y{Y:.3f} Z{z:.3f} E{e:.5f}")
                px, py = X, Y

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{press + height + 30:.1f} F900",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(rings=len(rings), layers=layers, grams=round(grams, 1),
                                     speed=round(speed), flow=round(flow, 1),
                                     mins=round(e / e_per_mm / speed / 60, 1),
                                     size=(round(max(xs)-min(xs)), round(max(ys)-min(ys))))


def d_profile(d, flat_depth, n=96):
    """A D-shaped shaft profile: a circle of diameter `d` with one side cut to a flat chord.

    Built as circle INTERSECT half-plane rather than by hand-ordering points. Walking the circle and
    dropping the points above the chord produced a self-intersecting ring (the coordinates wrap past
    the cut and rejoin across it), which shapely rejects with a side-location conflict. An
    intersection cannot produce an invalid ring.

    The flat is what transmits torque — a round bore on a D shaft simply spins.
    """
    r = d / 2.0
    y_flat = r - flat_depth
    return Point(0, 0).buffer(r, n).intersection(box(-r - 1, -r - 1, r + 1, y_flat))


def adapter(shaft_d, flat_depth, stick_d, wall, split=0.5):
    """Motor D-shaft -> bamboo stick. Returns a FUNCTION of layer fraction, not a fixed region.

    Oleg: "the shaft is D form. we will also need adapter". The two ends need different bores, so
    the cross-section changes partway up -- which a single extruded region cannot express. emit()
    therefore accepts a callable.

    The D end goes at the BOTTOM. Going up, the round stick bore is LARGER than the D bore, so the
    transition only ever REMOVES material — nothing is printed over air and no bridging is needed.
    Printed the other way up, the flat would have to bridge across the bore.
    """
    od = max(shaft_d, stick_d) + 2 * wall
    outer = Point(0, 0).buffer(od / 2.0, 96)

    def region_at(t):
        if t < split:
            return outer.difference(d_profile(shaft_d + SHRINK, flat_depth, 96))
        return outer.difference(Point(0, 0).buffer((stick_d + SHRINK) / 2.0, 96))

    return region_at


def shelled(region, shell, floor_h, height, layer_h):
    """Turn a solid region into a SHELL WITH A FLOOR, open at the top, to be filled with sand +
    gypsum after printing.

    Oleg: "for weight add a cavity, i will put sand + gipsum ... we have plan to use that in
    general for strugural prints".

    Why this beats both solid and hollow:
      · a shell is ~30% of the material, so it prints in ~a third of the time
      · filled it is HEAVIER than solid PLA (sand+gypsum ~1.8 g/cm3 against PLA's 1.24)
      · loose sand is an excellent damper — grains rub and eat energy — and the gypsum sets it so
        it stops migrating and becomes structural
      · mass lowers a structure's natural frequency, which is what you want in a base or a foot

    Open at the TOP on purpose: closing it would need the roof to bridge over the cavity, and this
    toolchain has no support and no bridging. Print it mouth-up, fill, let it set.

    Returns a CALLABLE of layer fraction, which emit() already understands (see adapter()).
    """
    floor_frac = min(0.9, max(0.0, floor_h / max(height, 1e-9)))

    def region_at(t):
        if t <= floor_frac:
            return region
        inner = region.buffer(-shell)
        if inner.is_empty:
            return region
        return region.difference(inner)

    return region_at


def plate(bores, wall, thickness=None, clearance=0.0, hollow=0.0):
    """A plate with N vertical bores — the general bamboo joint.

    Why vertical bores and not angled sockets: this generator extrudes a 2D region up the Z axis, so
    any feature whose axis is VERTICAL is a constant cross-section and prints with no bridging and
    no support. A socket lying horizontal is a bridged hole and this toolchain has no support to
    give it. So the whole joint family is built from vertical bores in flat plates:

      · foot plate      one bore, wide skirt      — stands a stick up
      · inline coupler  one bore, tall            — joins two sticks end to end (pulley.py --sleeve)
      · spacer          N bores in a row          — holds verticals parallel at intervals
      · bearing bracket axle bore + stick bore    — carries the pulley shaft off the frame

    `bores` is a list of (x, y, diameter). Each is modelled OVERSIZE by the measured printed-hole
    shrink so a real stick actually goes in.
    """
    parts = []
    for (x, y, d) in bores:
        parts.append(Point(x, y).buffer(d / 2.0 + wall, 96))
    body = unary_union(parts)
    if len(bores) > 1:
        # a spine joining the bores, so a near-collinear set does not depend on the circles touching
        xs = [b[0] for b in bores]
        ys = [b[1] for b in bores]
        h = max(b[2] / 2.0 + wall for b in bores) if thickness is None else thickness / 2.0
        body = unary_union([body, Polygon([(min(xs), min(ys) - h), (max(xs), min(ys) - h),
                                           (max(xs), max(ys) + h), (min(xs), max(ys) + h)])])
    if hollow > 0 and len(bores) > 1:
        # I-BEAM THE SPINE. The spacer's job is to hold two bores apart against the uprights
        # converging (compression — buckling load is 27 kN over 100mm, i.e. irrelevant) and against
        # the ladder racking in plane (bending). Material near the neutral axis contributes almost
        # nothing to bending: measured, removing the middle keeps 76% of the second moment for 38%
        # of the material. Flanges stay `hollow` mm thick top and bottom.
        xs = [b[0] for b in bores]
        ys = [b[1] for b in bores]
        h = max(b[2] / 2.0 + wall for b in bores)
        keep = max(b[2] / 2.0 + wall * 0.9 for b in bores)   # never cut into a boss
        void = Polygon([(min(xs) + keep, min(ys) - h + hollow),
                        (max(xs) - keep, min(ys) - h + hollow),
                        (max(xs) - keep, max(ys) + h - hollow),
                        (min(xs) + keep, max(ys) + h - hollow)])
        if void.is_valid and not void.is_empty and void.area > 4 * hollow ** 2:
            body = body.difference(void)
    for (x, y, d) in bores:
        body = body.difference(Point(x, y).buffer((d + SHRINK + clearance) / 2.0, 96))
    return body


def bracket(axle_d, stick_d, centres, wall, shrink=0.25, clearance=0.0):
    """Bearing block: an axle bore and a bamboo-stick bore, joined by a waisted body.

    Both bores are modelled OVERSIZE by the measured printed-hole shrink (printed = model - 0.25 on
    these machines), so the axle turns and the stick slides in rather than the part being scrap.
    """
    r_a = (axle_d + shrink) / 2.0
    r_s = (stick_d + shrink + clearance) / 2.0
    # CONSTANT-HEIGHT BODY, not a waisted one. A waist PINCHES as the region is buffered inward:
    # the contours split into two islands and the path has to cross the gap once per layer -- a
    # 12.8mm hop, measured. Making the connecting body as tall as the larger boss means the region
    # shrinks as a single blob and never splits, so every contour links to the next in about one
    # bead and the part needs no travel at all. It also puts more material around the stick bore,
    # which is the joint that carries the frame.
    h = r_s + wall
    body = unary_union([
        Point(0, 0).buffer(r_a + wall, 96),
        Point(centres, 0).buffer(r_s + wall, 96),
        Polygon([(0, -h), (centres, -h), (centres, h), (0, h)]),
    ])
    return body.difference(Point(0, 0).buffer(r_a, 96)) \
               .difference(Point(centres, 0).buffer(r_s, 96))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="bracket",
                    choices=["bracket", "foot", "coupler", "spacer2", "spacer3", "spacer4", "gauge", "adapter"])
    ap.add_argument("--axle", type=float, default=6.0)
    ap.add_argument("--stick", type=float, default=6.35, help="1/4 inch bamboo (6.35mm)")
    ap.add_argument("--centres", type=float, default=32.0)
    ap.add_argument("--wall", type=float, default=4.0)
    ap.add_argument("--flat", type=float, default=0.5, help="D-shaft flat depth mm")
    ap.add_argument("--height", type=float, default=12.0)
    ap.add_argument("--bead-w", type=float, default=1.2)
    ap.add_argument("--layer-h", type=float, default=0.4)
    ap.add_argument("--flow", type=float, default=machine.FLOW)
    ap.add_argument("--temp", type=int, default=machine.TEMP)
    ap.add_argument("--bed", type=int, default=0, help="0 = machine.BED_TEMP['pla']")
    ap.add_argument("--press", type=float, default=0.10)
    ap.add_argument("--first-w", type=float, default=3.0)
    ap.add_argument("--fan", type=int, default=80)
    ap.add_argument("--aux", type=float, default=0.2)
    ap.add_argument("--brim", type=int, default=4, help="brim rings on layer 1")
    ap.add_argument("--brim-gap", type=float, default=0.18,
                    help="mm of extra gap so the brim snaps off (0 = fused)")
    # BORE FIT. printed = model - 0.25 is CONFIRMED at ~6mm (the pulley bore is a perfect fit on a
    # 6.0mm shaft). So bore = stick + SHRINK gives ZERO clearance — a grip fit, which is what a
    # bracket wants: you slide it up the stick to tension the belt and friction holds it there.
    # A spacer wants the opposite: it should slide freely while you square the frame up.
    #   grip  0.00  -> prints at nominal, holds position   (bracket, foot)
    #   slip  0.25  -> slides by hand                      (spacer)
    #   loose 0.50  -> drops on                            (guides, sleeves over a taper)
    ap.add_argument("--cavity", type=float, default=0.0,
                    help="shell wall mm for a sand+gypsum cavity — MUST be a bead "
                         "multiple (1.2/2.4/3.6); 0 = solid")
    ap.add_argument("--floor", type=float, default=2.4,
                    help="solid floor under the cavity, mm")
    ap.add_argument("--hollow", type=float, default=0.0,
                    help="I-beam the spine: flange thickness mm (0 = solid)")
    ap.add_argument("--clearance", type=float, default=0.0,
                    help="extra bore clearance mm: 0 grip, 0.25 slip, 0.5 loose")
    ap.add_argument("--material", default="pla",
                    choices=["pla","petg","tpu","abs"],
                    help="stamped into the file; TPU is fan-guarded")
    ap.add_argument("--printer", default="k1c", choices=sorted(machine.BED))
    ap.add_argument("--parts", default="",
                    help="ONE PLATE, many parts: 'coupler*3,bracket*2,foot'. Overrides --part.")
    ap.add_argument("--sequential", action="store_true", default=True,
                    help="print each part to full height before the next (default)")
    ap.add_argument("--layerwise", dest="sequential", action="store_false",
                    help="all parts together, layer by layer")
    ap.add_argument("--part-gap", type=float, default=8.0,
                    help="mm between parts on a multi-part plate")
    ap.add_argument("--margin", type=float, default=12.0, help="mm kept clear at the bed edge")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    if a.parts:
        return run_plate(a)
    region = build_part(a.part, a)
    if a.cavity > 0:
        region = shelled(region, a.cavity, a.floor, a.height, a.layer_h)
    return finish(region, a, a.part,
                  f"{a.out}/{a.part}_{a.printer}_s{a.stick:g}_c{a.centres:g}"
                  f"_h{a.height:g}_T{a.temp}.gcode")


def build_part(part, a):
    """Construct one part's 2D region from the shared parameter set."""
    if part == "bracket":
        region = bracket(a.axle, a.stick, a.centres, a.wall, clearance=a.clearance)
    elif part == "foot":
        region = plate([(0, 0, a.stick)], a.wall * 3, clearance=a.clearance)
    elif part == "adapter":
        region = adapter(a.axle, a.flat, a.stick, a.wall)
    elif part == "gauge":
        # FIT GAUGE — three bores, one print. The shrink figure (printed = model - 0.25) was
        # calibrated on a 4mm hole and is unverified at 12.7mm, and a coupler bored for ZERO
        # clearance will not accept a stick at all. Measure once instead of printing a set wrong.
        region = plate([(i * (a.stick * 2.6 + 8), 0, a.stick + 0.2 + 0.25 * i)
                        for i in range(3)], 3.0)
    elif part == "coupler":
        region = plate([(0, 0, a.stick)], a.wall, clearance=a.clearance)
    else:
        n = int(part[-1])
        region = plate([(i * a.centres, 0, a.stick) for i in range(n)], a.wall,
                       clearance=a.clearance, hollow=a.hollow)
    return region


def finish(region, a, label, fn):
    g, st = emit(region, a.height, a.bead_w, a.layer_h, a.flow, a.temp,
                 a.bed or machine.BED_TEMP["pla"], 1.75, machine.BED[a.printer],
                 not a.no_home, a.press, a.fan, a.first_w, a.aux, a.printer,
                 f"{label.upper()} stick{a.stick:g} wall{a.wall:g}")
    os.makedirs(a.out, exist_ok=True)
    open(fn, "w").write(g)
    print(f"{fn}")
    print(f"  {st['size'][0]}x{st['size'][1]}mm, {st['rings']} concentric contours, "
          f"{st['layers']} layers = {a.height}mm tall")
    print(f"  {st['speed']} mm/s at flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g")
    return st


def run_plate(a):
    """ONE PLATE, EVERY PART THAT IS STILL NEEDED.

    Oleg: "use entire area to print everything needed not a tiny thing". A plate of 49 identical
    pads satisfies the letter of that and misses the point — the frame needs SIX DIFFERENT parts,
    and printing them one file at a time is six heat-ups, six homings, and six chances to collide
    with a plate that was not cleared.

    Parts are packed by bounding box into shelves and unioned into one region. They are disjoint,
    so contours() already treats each as its own ring family; nothing about the per-part geometry
    changes. The only real constraint is that every part on a plate shares ONE height, because the
    layer loop is shared — which is true of the whole joint family here (all 14mm).
    """
    spec = []
    for chunk in a.parts.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, n = chunk.partition("*")
        spec.append((name.strip(), int(n) if n else 1))

    built = []
    for name, n in spec:
        r = build_part(name, a)
        for _ in range(n):
            built.append((name, r))

    # THE BRIM DECIDES THE GAP, NOT TASTE.
    # Each part's brim reaches brim_gap + brim*bead_w beyond its outline. Two neighbours therefore
    # need TWICE that plus a bead of clear air between the outermost brim rings, or the brims merge
    # and the "parts" come off the plate as one welded lump — with the join hidden under a brim
    # that is supposed to snap away. Caught here rather than on the bed.
    reach = a.brim_gap + a.brim * a.bead_w
    need_gap = 2 * reach + a.bead_w
    if a.part_gap < need_gap:
        raise SystemExit(
            f"--part-gap {a.part_gap:g}mm is too tight: {a.brim} brim rings at {a.bead_w:g}mm reach "
            f"{reach:.2f}mm past each part, so neighbours need >= {need_gap:.2f}mm or their brims "
            f"fuse. Raise --part-gap to {math.ceil(need_gap)} or drop --brim.")

    # SHELF PACK. Sorted tallest-first so shelves stay tight; a plain grid on the largest part
    # would waste most of a 350mm bed on the small ones.
    gap = a.part_gap
    bed_x, bed_y = machine.BED[a.printer]
    usable_x = bed_x - 2 * a.margin
    built.sort(key=lambda it: -(it[1].bounds[3] - it[1].bounds[1]))
    placed, x, y, shelf_h = [], 0.0, 0.0, 0.0
    for name, r in built:
        minx, miny, maxx, maxy = r.bounds
        w, h = maxx - minx, maxy - miny
        if x > 0 and x + w > usable_x:
            x, y, shelf_h = 0.0, y + shelf_h + gap, 0.0
        placed.append((name, translate(r, x - minx, y - miny)))
        x += w + gap
        shelf_h = max(shelf_h, h)
    total_h = y + shelf_h
    if total_h > bed_y - 2 * a.margin:
        raise SystemExit(f"{len(built)} parts need {total_h:.0f}mm of Y on a "
                         f"{bed_y:.0f}mm plate — drop some or raise --margin.")

    # CENTRE THE ARRANGEMENT, NOT THE PARTS. The packer lays parts out from the origin, which is off
    # the plate; emit() used to rescue that by centring whatever it was handed, and in sequential
    # mode that rescue is what stacked every part on the middle of the bed. So the offset is applied
    # ONCE, here, to the whole layout — and emit() is told not to centre (centre=False).
    _ax = [c for _, r in placed for c in (r.bounds[0], r.bounds[2])]
    _ay = [c for _, r in placed for c in (r.bounds[1], r.bounds[3])]
    off_x = (bed_x - (max(_ax) + min(_ax))) / 2.0
    off_y = (bed_y - (max(_ay) + min(_ay))) / 2.0
    placed = [(n, translate(r, off_x, off_y)) for n, r in placed]

    counts = ", ".join(f"{n}x {name}" for name, n in spec)
    print(f"  plate: {counts} — {len(built)} parts, {x if y == 0 else usable_x:.0f}x{total_h:.0f}mm")
    fn = f"{a.out}/plate_{a.printer}_{len(built)}parts_h{a.height:g}_T{a.temp}.gcode"

    if a.sequential:
        return emit_sequential(placed, a, counts, fn)

    region = unary_union([r for _, r in placed])
    # A CAVITY WORKS ON A PLATE — shell the UNION, not each part. buffer(-shell) on a MultiPolygon
    # erodes every member independently, so each part gets its own floor and its own open mouth.
    # (Applied here rather than in build_part because shelled() returns a callable of layer
    # fraction, which cannot be translated or unioned.)
    if a.cavity > 0:
        region = shelled(region, a.cavity, a.floor, a.height, a.layer_h)
    return finish(region, a, "PLATE " + counts, fn)


def emit_sequential(placed, a, counts, fn):
    """PART BY PART, NOT LAYER BY LAYER. Oleg, 2026-07-26: "lets print part by part not layer by
    layer".

    Each part is taken to full height before the head moves to the next. Two things this buys that
    layer-by-layer cannot: a stop midway leaves N FINISHED parts instead of 15 ruined stumps — which
    is the difference between a wasted hour and a wasted afternoon on a machine that has been
    stopping all day — and no inter-part travel ever crosses a part at layer height.

    Built by generating each part through the normal emit() and splicing the bodies, so every
    per-part check still runs: the fill-ratio guard, the brim ordering, the ring ordering. A
    hand-rolled sequential loop would have quietly skipped all three.

    THE COLLISION RULE: between parts the head lifts CLEAR of everything already standing, travels,
    and only then descends. Without that lift the move to the next part happens at first-layer
    height and shears off every finished part in the way.
    """
    bodies = []
    head = None
    for i, (name, r) in enumerate(placed):
        reg = shelled(r, a.cavity, a.floor, a.height, a.layer_h) if a.cavity > 0 else r
        g, st = emit(reg, a.height, a.bead_w, a.layer_h, a.flow, a.temp,
                     a.bed or machine.BED_TEMP["pla"], 1.75, machine.BED[a.printer],
                     not a.no_home, a.press, a.fan, a.first_w, a.aux, a.printer,
                     f"{name.upper()} #{i+1}", centre=False)
        pre, _, post = g.partition("; BODY_START\n")
        if head is None:
            head = pre + "; BODY_START\n"
        body = post.split("; BODY_END")[0] if "; BODY_END" in post else post
        # drop the tail (M107/M104 S0/park) — it belongs once, at the end of the whole plate
        body = "\n".join(ln for ln in body.splitlines()
                         if not ln.startswith(("M107", "M104 S0", "M140 S0", "G0 X10 Y340"))
                         and not re.match(r"^G1 Z\d+\.\d+ F900$", ln))
        bodies.append((name, body, st))

    safe_z = a.height + 2.0
    travel_f = int(machine.MACHINE_MAX_SPEED * 60)
    print_f = round(machine.speed_for(a.flow, a.bead_w * a.layer_h) * 60)
    L = [head.rstrip("\n")]
    # STAMP IT. validate.py relaxes the no-travel rule ONLY for a file that declares itself
    # sequential, and replaces it with stricter checks (no extruding travel, every descent
    # preceded by a clearing lift). An unstamped file still gets the original rule.
    L.append(f"; SEQUENTIAL={len(bodies)} parts, hop clears Z{safe_z:.1f}")
    for i, (name, body, st) in enumerate(bodies):
        first = next((ln for ln in body.splitlines() if ln.startswith(("G1 ", "G0 ")) and "X" in ln),
                     None)
        if i:
            fx = re.search(r"X([-\d.]+)", first).group(1)
            fy = re.search(r"Y([-\d.]+)", first).group(1)
            L.append(f"; ---- part {i+1}/{len(bodies)}: {name} ----")
            L.append(f"G0 Z{safe_z:.3f} F900          ; clear everything already standing")
            L.append(f"G0 X{fx} Y{fy} F{travel_f}     ; travel at machine max, flow suspended")
            L.append(f"G0 Z{a.press:.3f} F900")
            L.append(f"G1 F{print_f}")   # sticky-F: never let the travel rate print
            L.append("G92 E0")
        L.append(body.rstrip("\n"))
    L.append("M107")
    L.append("M104 S0")
    L.append("M140 S0")
    L.append(f"G1 Z{safe_z + 20:.3f} F900")
    L.append("G0 X10 Y340 F9000")
    open(fn, "w").write("\n".join(L) + "\n")
    grams = sum(st["grams"] for _, _, st in bodies)
    mins = sum(st["mins"] for _, _, st in bodies)
    print(f"{fn}")
    print(f"  SEQUENTIAL — {len(bodies)} parts one at a time, {bodies[0][2]['layers']} layers each")
    print(f"  hop clears to Z{safe_z:.1f} at {machine.MACHINE_MAX_SPEED:g} mm/s, no retract")
    print(f"  ~{mins:.0f} min, {grams:.1f} g")
    return dict(grams=grams, mins=mins, size=(0, 0), rings=0,
                layers=bodies[0][2]["layers"], speed=bodies[0][2]["speed"],
                flow=bodies[0][2]["flow"])


if __name__ == "__main__":
    main()
