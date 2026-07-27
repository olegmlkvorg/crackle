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
from shapely.affinity import translate, rotate

import sys as _sys

import machine

# CONFIRMED 2026-07-25 at ~6mm: the pulley's D-bore was modelled 6.25 for a 6.0mm shaft and Oleg
# reports "the holes in puleys are perfect fit". So printed = model - 0.25 holds here, and a 1/4"
# stick (6.35) takes a 6.60 modelled bore. The spiral-vase README had flagged this figure as
# calibrated on a 4mm hole and unverified at larger sizes — it is now verified at 6.
SHRINK = 0.25          # METAL SHAFTS ONLY — a 6mm motor shaft, round or D. Validated by the sleeve
                       # Oleg pressed on hot and called a perfect fit; do not widen it on their
                       # account. See STICK_FIT below for why bamboo needed its own number.

# BAMBOO STICK FIT — MEASURED 2026-07-27, not inherited.
# The fit gauge (three bores, 0.25mm apart, printed on the K1C) went onto a real 6.35mm rod and
# Oleg picked the middle one: "use middle". Measured from the emitted gauge file, the three holes
# are 6.80 / 7.05 / 7.30mm in geometry, so the fit he chose is 7.05 — rod + 0.70.
# (plate() was already adding SHRINK on top of the diameters the gauge passes in, which is easy
#  to miss and which I got wrong once here: the first version of this constant said 0.45, from
#  reading the gauge's argument instead of the hole it actually emits. Measure the artifact.)
#
# Every bamboo bore in this file was using `stick_d + SHRINK` = 6.60mm, which is 0.45mm TIGHTER
# than the fit that works and sits nearer the gauge's press-fit bore than its sliding one. That is
# ~21 already-printed parts — shelf bores, couplers, spacers — bored too tight. The gauge existed
# precisely to settle this and had been sitting unprinted on the list.
#
# It gets its OWN constant because SHRINK was calibrated on a 4mm hole for a METAL shaft, and a
# number that belongs to one material and one diameter must not be spent on another: bamboo rods
# are not round, not consistent, and are gripped rather than pressed. Sharing one constant between
# them is the same defect that made the bowl lid unable to close.
STICK_FIT = 0.70
# ...AND 0.70 IS STILL TIGHT WHEN HOT. Oleg, 2026-07-27, holding the shell that printed with it:
# "it barely fitted stick ... on hot. you need to take into account that we print and hich temps
# around for high adhesiv so wals will bulge and it is expected. so give room for it to bulge and
# yet fit our expected sizes. this is super amplified on round things you create."
#
# The number is not the whole problem, and raising it does not fix this: a bigger ROUND bore is
# loose when cold AND still pinched when hot, because a circle has no relief anywhere — every
# degree of it sits at the fit diameter, so a bulge in any direction is immediate interference.
#
# The fix is SHAPE, not size. A polygon bore whose INSCRIBED circle is the fit touches at its edge
# midpoints and stands its corners off by 1/cos(pi/n), and that gap is the room the bulge grows
# into. Measured against a 6.35mm rod at the same 7.05 fit:
#       3 points -> 3.52mm corner relief      4 -> 1.46mm      6 -> 0.55mm      circle -> 0.00mm
# Three also locates a rod the way a three-legged stool cannot rock, and a 0.2mm error squeezes
# three short flats instead of seizing a whole circumference.
#
# NOT IMPLEMENTED YET, deliberately. A first attempt at ribbing the shell to carry this shipped
# three separate geometry defects in a row (ribs through the bore, ribs clipping the very relief
# they were meant to protect, region left disconnected) and was reverted. The shell builds its wall
# by eroding its own outline, and that interacts with a polygon hole in ways I did not predict
# correctly three times running. It wants path-level construction like pulley.py's
# rim -> spoke -> bore -> spoke circuit, not another buffer patch.


def circle(r, seg=0.5):
    """A circle whose SEGMENT LENGTH is fixed, not its segment count.

    shapely renders every buffer at 96 segments whatever the radius, so a 6.25mm bore comes out with
    0.205mm segments while a 60mm rim gets 2mm ones. The short end is the dangerous one: at 60 mm/s
    a 0.2mm segment is 300 moves/second, which is exactly where Klipper drains its lookahead and
    FREEZES with no error. Resolution is per quarter-circle, hence the /4.
    """
    res = max(4, int(math.ceil(2 * math.pi * max(r, 1e-6) / seg / 4)))
    return Point(0, 0).buffer(r, res)


def shaft_socket(shaft_d, points=3, grip=0.25, clearance=0.5, bump_r=1.6):
    """A shaft slot made of a few PRESSURE POINTS, not a round hole.

    Oleg, 2026-07-26: "when you designing, do not try to make a round shaft in the middle, instead
    just plan the lines that will create that shaft slot with few pressure points".

    THREE REASONS THIS BEATS SUBTRACTING A CIRCLE.

    1. A printed hole is never round. Subtracting a circle assumes the plastic lands where the model
       says, and it does not — so a "6.60mm" bore grips wherever it happens to be tightest and rocks
       everywhere else. Three deliberate contact points grip in three known places instead.
    2. It self-centres. Three points at 120 degrees locate a shaft exactly, the way a three-legged
       stool cannot rock. More points are worse, not better: four fight each other.
    3. It survives shrink error. The contact points are the only tight geometry, so being 0.2mm out
       squeezes three small bumps rather than seizing or rattling a whole circumference. The
       clearance circle around them can be coarse — it never touches anything, so it needs no fine
       segments, which is also what keeps the move rate down.

    Returns the region to SUBTRACT from a part: a generous clearance bore with `points` bumps
    protruding back inward to just under the shaft radius, so they must deform slightly to admit it.
    """
    r_shaft = shaft_d / 2.0
    r_clear = r_shaft + clearance
    r_contact = r_shaft - grip / 2.0          # bumps stand proud INTO the shaft by grip/2
    hole = circle(r_clear, seg=0.8)           # coarse on purpose: it touches nothing
    for i in range(points):
        a = 2 * math.pi * i / points
        d = r_contact + bump_r                # bump centre, so its inner edge sits at r_contact
        c = Point(d * math.cos(a), d * math.sin(a)).buffer(bump_r, 8)
        hole = hole.difference(c)
    # CLEAN THE JUNCTIONS. Where each bump meets the clearance circle the boolean leaves vertices a
    # few hundredths apart — measured 0.031mm, which is SHORTER than the round bore this was meant
    # to improve on. simplify() collapses them without moving the contact points, which sit far from
    # any junction. Checked after, not assumed: the contact radius must survive this.
    cleaned = hole.simplify(0.04, preserve_topology=True)
    return cleaned if not cleaned.is_empty else hole


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
         material=None, hop_min=8.0, centre=True, hop_clear=1.5):
    # NO DEFAULT MATERIAL HERE. A literal 'pla' default stamped "; MATERIAL=pla" into a file
    # printing matte at 230C, and validate.py then checked it against the wrong flow cap. An
    # unpassed material is a bug in the caller, so it fails here instead of being guessed.
    if material is None:
        raise ValueError("plate(): material must be passed explicitly — it is stamped into the "
                         "file header and every downstream check reads it")
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (bead_w * layer_h) / area
    # ONE SPEED PER PRINT, AND ITS VALUE IS NOT PINNED.
    # Oleg, 2026-07-27, correcting me: "speed is not fixed - 50 is north star default unless
    # overruled by other constraints." What must hold is CONSTANCY within a print, so material per
    # mm does not change where the geometry is already tightest. The VALUE is the north star unless
    # a real constraint pushes it lower — a fat bead or a low-flow material — and it is never
    # higher. Pinning it would have broken the two things this work most depends on:
    #   · THE WIDE-BEAD TRICK — a fat commanded bead so the head CRAWLS and the flow still lands.
    #     At a pinned speed the width multiplies straight into impossible flow (6 x 0.4 x 50 =
    #     120 mm3/s); the bead is supposed to push the SPEED down, not the flow up.
    #   · LOW-FLOW MATERIALS — TPU's 15.2 mm3/s at a pinned 50 needs a 0.51mm bead, narrower than
    #     the 0.8 nozzle, so the material reads as unprintable. At the normal bead it just crawls.
    #
    # STATED PLAINLY, because a comment that overclaims a fix is the same defect as a page that
    # oversells: this file was NOT one of the ones that pinned speed. It already went through a
    # helper that took min(flow/area, cap), so the arithmetic here is unchanged and no archived
    # command was ever refused by it. What changes is that the resolution now names the ONE
    # function the corrected rule defines (machine.speed_for_flow), so this file cannot drift from
    # the rest of the repo, and that a legitimate crawl is reported as a crawl rather than as a
    # failure to reach 50.
    _flow_req = flow
    _want = flow / max(bead_w * layer_h, 1e-9)
    speed = machine.speed_for_flow(flow, bead_w, layer_h)
    # THE FEEDRATE IS AN INTEGER, so the speed the file DELIVERS is f/60 and not the float above.
    # Everything downstream — the '; FLOW=' stamp R4 is checked against, the header, the reported
    # time — is derived from the feedrate actually emitted, so the declared number is the commanded
    # one rather than an aspiration that happens to sit beside it.
    f = round(speed * 60)
    speed = f / 60.0
    flow = speed * bead_w * layer_h
    if _want > machine.DEFAULT_SPEED + 1e-9:
        print(f"  ~ a {bead_w:g}x{layer_h:g} bead at the {machine.DEFAULT_SPEED:g} mm/s north star "
              f"delivers {flow:.1f} mm3/s, not the {_flow_req:g} asked for, for {name}. The bead is "
              f"too THIN to carry that flow under the ceiling — widen it to "
              f"{machine.bead_for_flow(_flow_req, layer_h):.2f}mm rather than raise the speed.")
    elif speed < machine.DEFAULT_SPEED - 0.05:
        print(f"  ~ {speed:.1f} mm/s, below the {machine.DEFAULT_SPEED:g} mm/s north star, for "
              f"{name}: a {bead_w:g}x{layer_h:g} bead delivers the full {flow:.1f} mm3/s only if "
              f"the head crawls. That is the constraint overruling the default, not a fault.")
    # LAYERS COUNTED FOR THE ACTUAL Z LADDER, which further down is `z = press + k*layer_h` for
    # k in range(layers) -- so N layers span from press to press+(N-1)*layer_h, i.e. N-1 steps.
    # The old `round(height/layer_h)` was a STALE inversion of an earlier ladder that started at
    # z=0; against the press-offset ladder it dropped a layer (hanger --layers 3 printed 2).
    # Callers pass height = press + (N-1)*layer_h, so this returns N exactly.
    layers = max(1, int(round((height - press) / layer_h)) + 1)
    e_first = (bead_w * layer_h) / area   # full flow: the body's mm2 per mm
    travel_f = int(machine.MACHINE_MAX_SPEED * 60)   # inter-object travel: machine max
    # LAYER 1 RUNS AT THE SAME ONE SPEED, and carries the flow by WIDTH instead. Laid into a
    # PRESS_HARD gap its cross-section is first_w * press, and --first-w defaults to
    # bead_w * layer_h / PRESS_HARD precisely so that equals the body's mm2.
    # A separate FIRST_LAYER_SPEED clamp here was a second speed knob in a print allowed exactly
    # one. With the derived width it resolved to the body speed anyway, so it bought nothing; with
    # an overridden --first-w it silently emitted TWO speeds (R3) instead of showing the actual
    # defect, which is a first layer not carrying the body's flow (R4). Say that instead.
    f_first = f
    _first_area = first_w * press
    if abs(_first_area - bead_w * layer_h) > 0.01 * bead_w * layer_h:
        print(f"  ! --first-w {first_w:g} into a {press:g}mm gap is {_first_area:.3f} mm2 against "
              f"the body's {bead_w * layer_h:.3f} — layer 1 would run at "
              f"{_first_area / (bead_w * layer_h) * 100:.0f}% of the declared flow. "
              f"{bead_w * layer_h / press:.2f}mm is the width that matches it.")

    # A region may be a fixed polygon OR a callable of layer fraction (see adapter()). Contours
    # are cached per distinct region so a 35-layer part does not re-buffer shapely 35 times.
    _is_fn = callable(region)
    _cache = {}

    def _widen_holes(reg, d):
        """Enlarge every HOLE by d, leaving the outline alone.

        LAYER 1 IS A WIDE RIBBON LAID ON THE BODY'S PATHS, and that closes every bore.
        The first layer is metered as a `first_w` ribbon (3.0mm) for adhesion while walking the
        SAME contours as the 1.2mm body, so its bead reaches 0.9mm further in every direction.
        Outward that is free — more plate contact, which is the point. INWARD it eats the holes:
            gauge middle bore  7.05 -> 5.25mm at layer 1
            lid shaft hole     8.00 -> 6.20mm   (the audit's raycast measured 6.18 independently)
        A 6.35mm stick cannot pass a 5.25mm restriction, so every plate the posts thread through
        was unusable at its first layer — and nothing reported it, because every layer above was
        the right size and the part looks correct.

        Widening the holes on layer 1 only puts the ribbon's inner edge back where the body's is.
        The outline is deliberately NOT shrunk: outward spread is what makes the first layer stick.
        """
        from shapely.geometry import Polygon, MultiPolygon
        def one(poly):
            if not poly.interiors:
                return poly
            keep = []
            for ring in poly.interiors:
                # AN INTERIOR RING *IS* THE HOLE, so growing the hole means buffering that
                # polygon OUTWARD. The first version used -d and made every bore 1.8mm SMALLER
                # than the defect it was fixing: measured 5.0/5.2/5.49 -> 3.2/3.45/3.69 where the
                # body is 6.80/7.05/7.30. Sign errors in offsets do not announce themselves; only
                # sweeping the real ribbon and measuring the hole it leaves does.
                grown = Polygon(ring).buffer(+d)
                if grown.is_empty:
                    continue
                for g in (grown.geoms if grown.geom_type == 'MultiPolygon' else [grown]):
                    keep.append(g.exterior.coords)
            return Polygon(poly.exterior.coords, keep)
        if reg.geom_type == 'MultiPolygon':
            return MultiPolygon([one(g) for g in reg.geoms])
        return one(reg)

    # LAYER 1 WALKS THE SAME PATHS AS THE BODY. WIDTH IS AN EXTRUSION RATE, NOT A PLAN.
    # Widening the layer-1 CONTOURS by (first_w - bead_w)/2 means any feature narrower than
    # first_w cannot hold a contour and is DROPPED. Measured on a pole hook: first_w 9mm against
    # a 4mm ring wall, and layer 1 came out with the bar and hook but NO RING AT ALL -- the ring
    # started in mid-air on layer 2. The overhang guard caught it (30% unsupported) and I nearly
    # dismissed that as a false positive.
    # The physical truth is the other way round: the paths are the same, and the extra material
    # spreads sideways on its own because a 0.1mm gap gives it nowhere else to go. Oleg has said
    # exactly this: "first layer is 55 as well just line width is crazy high" -- the WIDTH SETTING
    # is high, meaning more material per mm, not a different toolpath.
    _first_widen = 0.0

    def rings_at(kk):
        if kk == 0 and _first_widen > 1e-9:
            base = region(0.0) if _is_fn else region
            return contours(_widen_holes(base, _first_widen), bead_w)
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
    # ...AND IT MUST LOOK AT EVERY LAYER, not just the first. Where `region` is a FUNCTION of
    # height — vented shells, tapered collets, anything whose cross-section changes as it climbs —
    # layer 0 cannot speak for the part. Measured on `--part shell --vents 3 --height 60 --od 34`:
    # layer 0 fills 0.966 and sails through while 68 of the 150 layers exceed 1.02, worst 1.091.
    # That is the foot failure (+10.4%, ploughed off the plate) shipping clean — and sustained over
    # half the part rather than confined to one layer.
    _n_layers = max(1, int(round(height / max(layer_h, 1e-9))))
    if _is_fn:
        _step = max(1, _n_layers // 40)          # contours() per sample is not free
        _ts = sorted({min(1.0, i / max(1, _n_layers - 1)) for i in range(0, _n_layers, _step)} | {1.0})
    else:
        _ts = [0.0]
    # Computed ONCE and reused: the fill guard, the off-plate bounds check, and the size/contour
    # report all need the same per-layer contours, and contours() is the expensive call here.
    _layer_rings = {}
    _fills = []
    for _t in _ts:
        _r = region(_t) if _is_fn else region
        _rr = contours(_r, bead_w) if _is_fn else rings
        _layer_rings[_t] = _rr
        _fills.append((sum(LineString(r).length for r in _rr) * bead_w / max(_r.area, 1e-9), _t))
    _fill, _fill_t = max(_fills)
    _over = sum(1 for _f, _ in _fills if _f > 1.02)
    _reg = region(_fill_t) if _is_fn else region
    if _fill > 1.02:
        # BEAD-MULTIPLE DIMENSIONS — Oleg's design rule from 2026-07-23, and this is the physics
        # behind it. A wall that is not an integer number of beads leaves the inward and outward
        # ring families colliding somewhere, and e_per_mm never notices. Measured on a 100mm
        # spacer: a 4.0mm flange (3.33 beads) fills 1.139 and would climb; 3.6 (3 beads) fills
        # 0.729 and 4.8 (4 beads) fills 0.981.
        _mult = [round(bead_w * k, 2) for k in range(2, 9)]
        raise SystemExit(
            f"{name}: contours cover {_fill:.3f}x the region at {_fill_t*100:.0f}% of the part's "
            f"height ({_over} of {len(_fills)} sampled layers exceed 1.02) — that layer deposits "
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

    # THE EXTENT MUST COME FROM EVERY LAYER, for the same reason the fill ratio does. This sampled
    # the two ENDPOINT layers, t=0 and t=1 — and a 120-degree twist maps t=1 straight back onto
    # t=0, so the two samples agree with each other and both miss the widest part of the object.
    # Measured: 14274 extruding moves off the plate, the first at layer 16, on a file that emitted
    # clean. validate.py caught it afterwards; solid.py never calls validate.py, so the only thing
    # between that file and the machine was this line. Re-uses the per-layer samples built for the
    # fill guard above, so it costs nothing extra.
    _allr = rings + base_extra
    if _is_fn:
        for _t in _ts:
            _allr = _allr + _layer_rings[_t]
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

    # THE CORRIDOR — a Y line with no part on it, used as the through-route for every inter-object
    # travel. Placed clear of the lowest part and its brim; if that would fall off the front of the
    # plate, it goes behind the highest part instead.
    _lo = min(ys) + oy
    _hi = max(ys) + oy
    _clear = brim * bead_w + brim_gap + 4.0
    corridor = _lo - _clear
    if corridor < 4.0:
        corridor = _hi + _clear
    if corridor > bed_xy[1] - 4.0:
        corridor = _lo - _clear          # nowhere clear; validate will catch any crossing
    L = []
    w = L.append
    w(f"; {name} — solid part as concentric contours, one continuous path per layer")
    # CONTOUR COUNT VARIES WITH HEIGHT on any part whose region does. A vented shell announced
    # "11 contours" while its layers actually run 6 / 9 / 11 — a header describing 4% of the
    # file. State the RANGE when it varies, one number only when it genuinely is one number.
    _rc = sorted({len(_rr) for _rr in _layer_rings.values()})
    _rcs = f"{_rc[0]}" if len(_rc) == 1 else f"{_rc[0]}-{_rc[-1]}"
    w(f"; {_rcs} contours, bead {bead_w}x{layer_h}, {layers} layers = {height}mm tall")
    # SPEED IS REPORTED TO A DECIMAL BECAUSE IT IS NO LONGER ALWAYS 50. Rounding 22.9 to "23" in
    # the one line a human reads hides the whole point of the correction: the value moved.
    w(f"; {speed:.1f} mm/s at flow {flow:.1f} mm3/s "
      f"(north star {machine.DEFAULT_SPEED:g} mm/s — lower is a constraint, never faster)")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {layers}")
    w("; HEADER_BLOCK_END")
    # ASK FOR THE BED BEFORE HOMING, so it heats WHILE the machine homes instead of afterwards.
    # M140 is non-blocking (M190/TEMPERATURE_WAIT is what waits), so there is no reason to sit at
    # room temperature through a 30-60s homing cycle and then start heating a cold plate. Every
    # other generator in this repo already ordered it this way; solid.py was the only one that did
    # not, which is why a K1C job showed `bed 22/0` while the nozzle was already at 169.
    # Nothing about safety changes: TEMPERATURE_WAIT below still blocks until the plate is at
    # temperature, so layer 1 cannot start on a cold bed either way. This only reclaims the overlap.
    w(f"M140 S{bed}")
    # Target the PROBE temperature first when homing. Setting the print temperature here and then
    # asking M109 to wait for 150 is a no-op: the tip sails past 150 on its way to 210 and probes
    # hot anyway. The full temperature is commanded after the probe, below.
    w(f"M104 S{temp}")
    w("G90")
    # CLEAN NOZZLE BEFORE THE CALIBRATION TOUCH. Oleg, 2026-07-27: "also clean nozel before
    # touching the middle fo calibration". G28 probes by touching the plate WITH THE NOZZLE, and
    # this ran while the hotend was already climbing to print temperature -- soft tip, oozing, and
    # whatever blob was on it went straight into the Z zero. Every layer height in the file
    # inherits that error, including the 0.1 press the whole first-layer technique depends on.
    # Probe at a temperature where PLA is firm and does not ooze; full heat comes after.
    # PROBING AT A LOWER TEMPERATURE IS REVERTED. It was added today to answer "clean nozel
    # before touching the middle fo calibration", and the very next print had ZERO adhesion.
    # The mechanism is real and I got the direction wrong: a nozzle probed at 150 is SHORTER than
    # at 230 by ~0.046 mm over the hotend's length, so Z zero is recorded high and the tip then
    # grows down into the plate -- a 0.1 gap becomes ~0.054. Too tight to push 1.2 mm2/mm through,
    # so the first layer lays little or nothing and nothing sticks. 46% of the gap is not a detail.
    # The request stands and needs a MECHANICAL wipe, not a temperature change. Not guessed again
    # until it can be tested against a part that is known to stick.
    w("G28" if home else "; NO HOME — assumes the machine is ALREADY homed; push.py verifies")
    # THE FLOOR MUST BE SATISFIABLE ON THIS MACHINE. machine.bed_start() clamps under the held
    # target; the raw BED_START_MIN (Oleg's 100) was emitted here directly, and on the K1C -- bed
    # pinned at ~87-91 at full power -- M190 S100 never completes: fifteen minutes of heating,
    # then forever. The floor-vs-K1C-ceiling conflict itself is Oleg's call (QUESTIONS.md); what
    # is not his call is a file that stalls silently instead of surfacing it.
    w(f"M190 S{machine.bed_start(material, bed):.0f}                     ; BLOCKING bed floor")
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    w("M204 S8000")
    # FAN OFF FOR LAYER 1, CLAMPED BY MATERIAL AFTER. Oleg: "fans for printing pla should be only
    # on 20% at most". This defaulted to 80/255 = 31% and ran from the first millimetre, chilling
    # the bond while it formed — the cheapest possible way to lose a first layer.
    _fan_body = int(round(machine.fan_for(material, (fan or 0) / 255.0) * 255))
    w("M107                              ; layer 1: no part cooling, let it bond")
    for ln in machine.aux_fans(printer, machine.aux_for(material, aux)):
        w(ln)
    w("M82")
    w("G92 E0")

    # WHERE THE PATH ACTUALLY STARTS — not where the outer contour happens to be indexed.
    # The prime used to target rings[0][0], but layer 0 prints the BRIM first, so the head began
    # 4.99mm away on a coupler and 18.12mm away on a bracket, and that gap was extruded at 4-8% of
    # the metered rate — a starved thread dragged across the part's own footprint and over an open
    # bore. Compute the real first point the same way the layer loop will.
    if base_extra:
        _bfirst = sorted(base_extra, key=lambda r: -max(
            (q[0] - ox) ** 2 + (q[1] - oy) ** 2 for q in r))
        _start = _bfirst[0][0]
    else:
        _r0 = rings_at(0)
        _start = _r0[0][0]
    x0, y0 = _start[0] + ox, _start[1] + oy

    # PURGE AND PRIME IN THE CORRIDOR, NOT ON THE PART.
    # The old approach was a blind `x0 - 40`, which on a packed plate lies INSIDE layer-1 material;
    # the stationary purge landed 0.09mm from deposited material and the prime laid a ridge at
    # 2.00x the layer-1 ribbon, which the brim then printed on top of. The corridor is a Y line
    # already computed to have no part on it.
    _py = min(max(corridor, 6.0), bed_xy[1] - 6.0)
    _px = min(max(x0, 30.0), bed_xy[0] - 6.0)
    w(f"G1 Z{press:.3f} F600")
    w(f"G0 F9000 X{_px - 24:.3f} Y{_py:.3f}")
    w("G1 E20 F300                      ; stationary purge — pressure before motion")
    w(f"G1 F1200 X{_px:.3f} Y{_py:.3f} E30      ; prime line, laid in the clear corridor")
    # ANGLED BREAK-OFF, so the prime does not drag a thread into the part.
    # Oleg, 2026-07-27: "make the first sstripe of extrudement disconnected from main model, you
    # know how the creality print draws an angle disconnect and start dwawing, this will make our
    # prints cleaner". The lifted travel below already avoided extruding across the part, but the
    # bead was still ATTACHED when the head left: molten PLA stretches rather than snaps, so a
    # tail rode along and landed on layer 1.
    # A short un-extruded run at an angle off the end of the prime wipes the nozzle against the
    # plate and breaks the tail there, in the corridor, where it belongs. No retraction -- this
    # project keeps flow continuous, and the wipe achieves the separation mechanically.
    w(f"G0 F3000 X{_px + 12:.3f} Y{_py + 12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    # ONE lifted travel from the prime to the real start. Kept explicit and tagged: it is cheaper
    # than the alternative, which was extruding a starved thread across the part to reach it.
    w(f"G0 Z{press + hop_clear:.3f} F900 ; PRIME-TRAVEL up")
    w(f"G0 X{x0:.3f} Y{y0:.3f} F{travel_f} ; PRIME-TRAVEL to first point")
    w(f"G0 Z{press:.3f} F900 ; PRIME-TRAVEL down")
    # STAMP THE MACHINE INTO THE FILE. validate.py cannot check bounds without
    # knowing which plate, and a filename is not a contract.
    # THE FILE MUST RECORD THE COMMAND THAT MADE IT. The belt that fixed the cleats
    # recorded neither --dish nor --rail, so which fix version was on the plate could
    # not be established from the artifact — in a project whose doctrine is measuring
    # the emitted file, that is a provenance hole. Now every file is reproducible from
    # its own header.
    w(f"; MATERIAL={material}")
    w(f"; LAYER_H={layer_h}")   # validate.py checks the Z ladder against this
    # THE STAMP IS WHAT THE FILE DELIVERS, NOT WHAT WAS ASKED FOR. `flow` was re-derived above from
    # the emitted feedrate and the emitted bead (f/60 * bead_w * layer_h), so R4 checks the moves
    # against the flow those same moves actually carry. A stamp copied from the --flow request would
    # declare an aspiration and quietly fail every move in a wide-bead or low-flow-material print.
    w(f"; FLOW={flow:.4f}")   # R4 checks every move against this
    # Layer 1 is laid at PRESS_HARD and metered to that gap, so its cross-section differs from the
    # body BY CONSTRUCTION. Declared so R4 exempts it and R4b (fill ratio) polices it instead --
    # an exception the checker has to guess at is a hole.
    w(f"; PRESSED_LAYER1={press:g}")
    w("; ARGV: " + " ".join(_sys.argv))
    w(f"; PRINTER={printer}")
    w("; BODY_START")

    e = 0.0
    # THE HEAD IS AT THE FIRST POINT — say so, instead of leaving it None.
    # With px None the layer loop's first step hits `if px is None: continue`, which SWALLOWED the
    # move onto the start rather than emitting or checking it. That swallow is what hid a 4.99mm
    # (coupler) and 18.12mm (bracket) starved thread for as long as the prime targeted the wrong
    # ring. Now the position is known, the first step measures zero, and any future mismatch shows
    # up as a real move instead of silence.
    px, py = x0, y0
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
                # SKIP MOVES TOO SHORT TO BE MOTION. A rotating region (the mixer's helix) starts
                # each layer a fraction off where the last one ended — measured 0.001mm. At 1e-9
                # those survive as real commands and the planner is asked for 60,000 moves/second
                # against a host that stalls near 300 and then FREEZES with no error. The material
                # skipped is 0.0005mm of filament, i.e. nothing; the command is the whole cost.
                if d < 0.02:
                    px, py = X, Y
                    continue
                # ONLY the step INTO a new loop may be a hop. A long move inside a loop is the
                # part's own straight wall -- shapely stores a flat edge as two points, so a naive
                # "long move = travel" rule turned this bracket's 30mm flat side into a travel and
                # produced 17 hops per layer. The link is pi == 0, and nothing else.
                if pi == 0 and d > hop_min:
                    # DISABLED BY DEFAULT (hop_min=inf) — AND THIS IS WHY.
                    # Oleg said "max out the speed when travel to next OBJECT". I applied it to
                    # links INSIDE a part too, which put 161 non-extruding moves at 120 mm/s at the
                    # CURRENT LAYER HEIGHT — the nozzle sweeping across material it had just laid,
                    # at exactly that material's height. It ploughed through the fresh layer and
                    # knocked every model off the plate. Between-object travel is emitted by
                    # emit_sequential instead, which lifts Z clear FIRST.
                    # A travel is only safe if it is ABOVE what is already printed.
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
                    # LIFT ONE LAYER, TRAVEL, DROP BACK. Oleg: "max out the speed when travel to
                    # next object and suspend the flow for a travel (dont retract)" — plus the
                    # correction that cost two plates: a FLAT travel at layer height drags the
                    # nozzle through the material just laid. One layer of lift clears it, and in
                    # layer-by-layer printing nothing on the plate is ever taller than the current
                    # layer, so one layer is provably enough.
                    # ROUTE AROUND THE PARTS, DO NOT FLY OVER THEM.
                    # Oleg: "another thing about moving from part to part - lines should [not] be
                    # crossing the parts". A straight hop clears a part it crosses by exactly one
                    # layer (0.6mm) — enough on paper, nothing at all against a curled edge or a
                    # blob, and every part on the plate is the same height in layer-by-layer mode.
                    # So the travel leaves the part band entirely, runs along a clear corridor, and
                    # comes back in. Non-extruding moves at machine max are nearly free, so the
                    # longer route costs almost no time and removes the whole failure mode.
                    # CLEARANCE IS PROVABLE, ROUTING IS NOT. Corridor routing cut crossings but
                    # could not eliminate them: leaving a part means crossing its own footprint, and
                    # with shelf-packed rows the run out to the corridor can cross the row in front.
                    # In layer-by-layer printing EVERY part is at the current layer height, so a
                    # fixed lift clears all of them whatever route is taken. 1.5mm against a 0.6mm
                    # layer is real margin for a curled edge or a blob, where one layer (0.6mm) was
                    # only clearance on paper.
                    L.append(f"G0 Z{z + hop_clear:.3f} F900 ; HOP up")
                    L.append(f"G0 Y{corridor:.3f} F{travel_f} ; HOP out to corridor")
                    L.append(f"G0 X{X:.3f} F{travel_f} ; HOP along corridor")
                    L.append(f"G0 Y{Y:.3f} F{travel_f} ; HOP over")
                    L.append(f"G0 Z{z:.3f} F900 ; HOP down")
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
                    L.append(f"G1 X{X:.3f} Y{Y:.3f} Z{z:.3f} E{e:.5f} ; LINK thin")
                    px, py = X, Y
                    continue
                e += d * (e_first if k == 0 else e_per_mm)
                L.append(f"G1 {'F%d ' % (f_first if k == 0 else f) if (px, py) == (x0, y0) else ''}"
                         f"X{X:.3f} Y{Y:.3f} Z{z:.3f} E{e:.5f}")
                px, py = X, Y

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{press + height + 30:.1f} F900",
          f"G0 X10 Y{bed_xy[1]-10:.0f} F9000"]
    # SIZE IS THE WHOLE PART, NOT ITS FIRST LAYER. Taken from `rings` alone this described layer 0
    # and nothing else, so any part whose region changes with height mis-reported itself: the mixer
    # printed 59.5x59.5mm while announcing 49x57. Same root as the fill and off-plate guards — a
    # part that changes shape as it climbs cannot be summarised by its base. The brim is still
    # excluded (base_extra is scaffolding, not the object); this is every sampled LAYER of the part.
    _prx = [p[0] for _rr in _layer_rings.values() for r in _rr for p in r]
    _pry = [p[1] for _rr in _layer_rings.values() for r in _rr for p in r]
    _pxs = (max(_prx) - min(_prx) + bead_w) if _prx else 0.0
    _pys = (max(_pry) - min(_pry) + bead_w) if _pry else 0.0
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(rings=len(rings), layers=layers, grams=round(grams, 1),
                                     # ONE DECIMAL, and the FEEDRATE ITSELF. Speed is no longer
                                     # always 50, so an integer report turns 22.9 into "23"; and
                                     # `feed` is handed out so the sequential splicer restores the
                                     # exact F this body was written with instead of recomputing it
                                     # from the request and risking a second speed in one print.
                                     speed=round(speed, 1), feed=f, flow=round(flow, 1),
                                     mins=round(e / e_per_mm / speed / 60, 1),
                                     # SIZE MUST BE THE PART, NOT THE PART PLUS ITS BRIM.
                                     # xs/ys are taken from rings + base_extra, and base_extra IS
                                     # the brim — so a 36.35mm foot reported as "45x45mm" and that
                                     # number went onto a public page as the part's diameter. The
                                     # brim is scaffolding; it snaps off and is not the object.
                                     size=(round(_pxs), round(_pys)),
                                     footprint=(round(max(xs)-min(xs)), round(max(ys)-min(ys))))


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
        return outer.difference(Point(0, 0).buffer((stick_d + STICK_FIT) / 2.0, 96))

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


def plate(bores, wall, thickness=None, clearance=0.0, hollow=0.0, fit=None):
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
        # `fit` is the BAMBOO allowance (STICK_FIT, measured), not the metal-shaft SHRINK.
        # The gauge passes fit=0 and sweeps raw diameters, so its reading stays valid.
        _fit = STICK_FIT if fit is None else fit
        body = body.difference(Point(x, y).buffer((d + _fit + clearance) / 2.0, 96))
    return body


def spacer_shell(bore_d, od, wall, height, floor_h, layer_h, vents=0, vent_w=4.0,
                 vent_from=0.55, clearance=0.0):
    """A fillable tube that threads onto a post: two concentric walls with a void between them.

    Oleg, 2026-07-26: a 24-inch bamboo shelf, "wise distribution of empty internals to be filled
    with gipsum mix and some with expanding foam (upper parts)", and "make sure the shells for foam
    has holes for vent and over growth".

    WHY THIS SHAPE. The frame is four 610mm sticks standing as posts, with shelves threaded on and
    these tubes stacked between them as the spacers that set shelf height. The posts are pulled into
    TENSION by tightening at the top; every tube is therefore a COMPRESSION member, which is the one
    load a hollow tube is best at and the one filling helps most.

    The cavity is not modelled — it falls out of the geometry. Shelling a disc-with-a-bore erodes
    the outer edge inward AND the bore outward, leaving two concentric walls with a void between.
    Nothing bridges: every surface is a constant cross-section extruded straight up.

    FILL, BY POSITION IN THE STACK:
      · low tubes  → gypsum + sand. ~1.8 g/cm3 against PLA's 1.24, so a filled tube outweighs a
        solid printed one while using a third of the plastic. Mass low down is what stops a tall
        shelf walking.
      · high tubes → expanding foam. Stiffens the wall against buckling for almost no weight, which
        is the opposite of what you want at the bottom.

    VENTS ARE NOT OPTIONAL ON THE FOAM ONES. Expanding foam in a sealed tube has nowhere to go: it
    either splits the wall or cures compressed and never sets properly. The slots run VERTICALLY
    through the wall — a gap in the 2D region, so still no bridging — and they do two jobs at once:
    air leaves as foam rises, and surplus foam is allowed to escape and be trimmed rather than
    building pressure. They start above `vent_from` of the height so the lower wall stays closed and
    the tube can still be stood up and filled from the top.
    """
    r_out = od / 2.0
    r_bore = (bore_d + STICK_FIT + clearance) / 2.0   # a bamboo post passes through
    base = Point(0, 0).buffer(r_out, 96).difference(Point(0, 0).buffer(r_bore, 96))

    floor_frac = min(0.9, max(0.0, floor_h / max(height, 1e-9)))
    slots = []
    if vents:
        for i in range(vents):
            a = 2 * math.pi * i / vents
            # a radial slot cut clean through the outer wall
            slot = box(r_out - wall * 1.6, -vent_w / 2.0, r_out + wall, vent_w / 2.0)
            slots.append(rotate(slot, math.degrees(a), origin=(0, 0)))

    def region_at(t):
        if t <= floor_frac:
            return base                      # solid floor: the fill cannot fall out
        inner = base.buffer(-wall)
        r = base if inner.is_empty else base.difference(inner)
        if slots and t >= vent_from:
            for sl in slots:
                r = r.difference(sl)
        return r

    return region_at


def mixer(shaft_d, od, blades, blade_w, hub_w, twist_deg, height, layer_h, clearance=0.0):
    """A helical mixing paddle for a 6mm motor shaft.

    Oleg, 2026-07-26: "you will need to print a mizer for me. i have cnc motor with contorlable
    speed 6mm shaft" — for the gypsum+sand fill, which at 15% binder is stiff and sand-heavy rather
    than pourable.

    WHY IT TWISTS. A flat paddle spun in a stiff mix just carves a channel and the material rides
    around with it; nothing folds. Rotating the blade profile as it rises makes a helix, so the
    blades drive material DOWNWARD or upward along the axis depending on rotation direction — the
    mix is turned over, not merely swept. That costs nothing here: this generator already varies its
    region per layer, so a twist is a rotation of the same profile rather than new geometry.

    Printable because every layer is still a flat cross-section: the helix exists only in how those
    cross-sections are indexed, never as an overhang. Twist per layer is bounded so consecutive
    layers overlap by more than half a bead — beyond that the blade edge steps into thin air.

    THE BORE IS ROUND AND UNDERSIZED ON PURPOSE. Press it onto the shaft while the part is still hot
    off the plate and the shaft moulds its own seat, including any flat — Oleg's own discovery, and
    it beats modelling a D because it cannot be misaligned and one part fits any shaft of that size.
    """
    r_hub = shaft_d / 2 + hub_w
    r_out = od / 2
    r_bore = (shaft_d + SHRINK + clearance) / 2.0

    # bound the twist so consecutive layers still overlap along the blade tip
    layers = max(1, int(round(height / layer_h)))
    tip_step = math.radians(twist_deg / max(layers - 1, 1)) * r_out
    if tip_step > blade_w * 0.5:
        safe = math.degrees((blade_w * 0.5) / r_out) * max(layers - 1, 1)
        raise SystemExit(
            f"a {twist_deg:.0f} deg twist over {height:g}mm moves the blade tip {tip_step:.2f}mm "
            f"per layer, more than half the {blade_w:g}mm blade — consecutive layers would not "
            f"overlap and the tip prints onto air. Max here is about {safe:.0f} deg.")

    base = circle(r_hub)
    for i in range(blades):
        a = 2 * math.pi * i / blades
        blade = box(0, -blade_w / 2.0, r_out, blade_w / 2.0)
        base = unary_union([base, rotate(blade, math.degrees(a), origin=(0, 0))])
    # PRESSURE POINTS, NOT A BORE. Three contact points locate the shaft exactly and grip in known
    # places; a subtracted circle grips wherever the print happened to land tightest and rocks
    # everywhere else. The clearance around them is coarse on purpose — it touches nothing.
    base = base.difference(shaft_socket(shaft_d))

    def region_at(t):
        return rotate(base, twist_deg * t, origin=(0, 0))

    return region_at


def collet(stick_d, od_small, od_large, slots, slot_w, height, wall, clearance=0.0):
    """A split tapered sleeve that grips a stick harder the more you pull on it.

    This is the part the shelf is missing. Everything else — shelves, spacers, feet — is a
    compression member and works by simply sitting on the one below. Putting the POSTS in tension
    needs something that grips a smooth bamboo rod hard enough to pull against, and friction from a
    plain collar is not it.

    HOW IT WORKS. The sleeve is a cone, wide at the bottom, split by vertical slots into fingers. It
    sits inside a matching conical seat in the cap above. Pulling the post upward drags the cone
    into the narrowing seat, which squeezes the fingers onto the stick. The harder it is pulled, the
    harder it grips — the load does the clamping, so nothing needs tightening by feel and it cannot
    shake loose.

    WHY IT IS PRINTABLE. The taper is a radius that varies with layer, which this generator already
    supports (a region that is a function of height). The splits are VERTICAL slots — a gap in the
    2D region, not an overhang. Nothing bridges anywhere.

    THE FINGERS MUST BE ABLE TO CLOSE. The bore is modelled at the stick's own size plus shrink,
    with no clearance: the fingers only need to travel the shrink allowance to bite. Slots run the
    full height so each finger is a cantilever from the top rather than a hoop that must stretch.
    """
    r_bore = (stick_d + STICK_FIT + clearance) / 2.0   # bamboo, not a metal shaft
    if od_small <= 2 * r_bore + 2 * wall:
        raise SystemExit(
            f"collet: a {od_small:g}mm narrow end cannot hold a {stick_d:g}mm stick with {wall:g}mm "
            f"walls — needs at least {2*r_bore + 2*wall:.1f}mm.")

    def region_at(t):
        # t=0 at the plate (WIDE end down, so the cone is self-supporting as it prints)
        r_out = (od_large + (od_small - od_large) * t) / 2.0
        body = circle(r_out).difference(circle(r_bore))
        for i in range(slots):
            a = 2 * math.pi * i / slots
            sl = box(0, -slot_w / 2.0, r_out + wall, slot_w / 2.0)
            body = body.difference(rotate(sl, math.degrees(a), origin=(0, 0)))
        return body

    return region_at


def collet_seat(od_small, od_large, od, height, wall, seat_gap=0.30):
    """The conical seat the collet is pulled into — the other half of the tension pair.

    Alone, a collet does nothing: it needs a hole that narrows in the direction of pull. This is
    that hole. It sits at the top of the post stack; the post passes through it, the collet rides on
    the post inside it, and tightening drags the cone up into the narrowing bore.

    THE BORE NARROWS GOING UP, which means material grows inward as it prints. That is an overhang,
    and it is only printable because the taper is shallow: 22->14mm over 30mm is 7.6 degrees from
    vertical, far inside the ~45 degrees this toolchain can hold unsupported. A steeper collet would
    grip harder and be unprintable without support, which is the trade if this one slips.

    seat_gap widens the bore over the collet's own profile so the two are not an interference fit
    before any load is applied — the collet must be able to enter the seat and THEN be drawn in.
    """
    # ...AND THE ANGLE ABOVE IS NOW CHECKED RATHER THAN ASSERTED. The paragraph above states the
    # bound — "far inside the ~45 degrees this toolchain can hold unsupported" — and nothing
    # enforced it, so the one part in this file that prints an overhang BY DESIGN was the only one
    # with no angle check. Its structural twin post_foot() has refused above 40 degrees all along.
    # Measured: `--part seat --height 6 --od 60 --od-small 14 --od-large 34` is 59 degrees from
    # vertical and emitted clean, and validate.py cannot catch it either — its overhang check is
    # blind below 71.6 degrees. A number recorded in a docstring is not a guard.
    _ang = math.degrees(math.atan2(abs(od_large - od_small) / 2.0, max(height, 1e-9)))
    if _ang > 40:
        raise SystemExit(
            f"collet_seat: the bore tapers {od_large:g}->{od_small:g}mm over {height:g}mm, which is "
            f"{_ang:.0f} degrees from vertical. Over ~40 the bore wall grows inward onto air.\n"
            f"  Raise --height (to {abs(od_large-od_small)/2.0/math.tan(math.radians(40)):.1f}mm or "
            f"more), or narrow the taper.")

    def region_at(t):
        r_bore = (od_large + (od_small - od_large) * t) / 2.0 + seat_gap
        r_out = od / 2.0
        if r_bore >= r_out - wall:
            raise SystemExit(
                f"collet_seat: bore {r_bore*2:.1f}mm leaves under {wall:g}mm of wall inside a "
                f"{od:g}mm body — widen --od.")
        return circle(r_out).difference(circle(r_bore))
    return region_at


def post_foot(stick_d, od_base, od_top, height, wall, floor_h, layer_h, points=3):
    """What a post stands in: a flared, fillable base with a three-point socket.

    The bottom of the stack has three jobs at once and this does all three with one shape.
      · SPREAD the load, so a 610mm post does not punch into a soft floor — hence the flare.
      · CARRY MASS as low as physically possible. Weight at the base is what stops a tall shelf
        walking, and the same gypsum+sand that fills the spacers fills this, only lower.
      · LOCATE the post, on three pressure points rather than a round bore
        (Oleg: "just plan the lines that will create that shaft slot with few pressure points").

    The flare tapers OUTWARD going down, which prints as an overhang-free constant cross-section
    stack — wide first, narrowing upward, so every layer lands on the one below.

    Filled, this is by far the heaviest part of the shelf, which is exactly where the weight belongs.
    """
    ang = math.degrees(math.atan2((od_base - od_top) / 2.0, height))
    if ang > 40:
        raise SystemExit(
            f"post_foot: a {od_base:g}->{od_top:g}mm flare over {height:g}mm leans {ang:.0f} deg "
            f"from vertical. Over ~40 the wall prints onto air — raise --height or narrow the base.")

    floor_frac = min(0.9, max(0.0, floor_h / max(height, 1e-9)))
    socket = shaft_socket(stick_d, points=points)

    def region_at(t):
        r_out = (od_base + (od_top - od_base) * t) / 2.0
        body = circle(r_out)
        if t <= floor_frac:
            return body.difference(socket)      # solid plinth, fill sits on it
        inner = body.buffer(-wall)
        shell = body if inner.is_empty else body.difference(inner)
        # the socket wall must persist up the whole height or the post has nothing to grip
        boss = circle((stick_d / 2.0) + wall).difference(socket)
        return unary_union([shell, boss])

    return region_at


def mixer_bowl(id_dia, height, wall, floor_h, layer_h, baffles=4, baffle_d=8.0, foot=6.0):
    """A mixing vessel with internal baffles, sized to the paddle that stirs it.

    BAFFLES ARE THE WHOLE POINT. A smooth round bowl and a rotating paddle spin the entire mass as
    one plug — the mix travels with the blade instead of across it and almost nothing shears. Ribs
    standing proud of the wall stop the rotation, so material forced round by the blade has to break
    over them. Industrial mixers do this; a bucket does not, which is why a bucket mixes badly.

    They cost nothing to print here: a rib is a vertical feature, so it is a constant cross-section
    extruded straight up — no overhang, no support, no extra time beyond the material.

    THE GAP IS THE SHEAR ZONE. Bowl radius minus paddle radius is where the mix is actually worked;
    too wide and the blade stirs a hole through the middle, too tight and it wedges. This sizes from
    the paddle rather than from a round number, and the caller is told what the gap came out as.

    The floor is solid and slightly wider than the wall — a mixing vessel gets pushed sideways, and a
    flat-bottomed tube tips.
    """
    r_i = id_dia / 2.0
    r_o = r_i + wall
    floor_frac = min(0.9, max(0.0, floor_h / max(height, 1e-9)))

    def region_at(t):
        if t <= floor_frac:
            return circle(r_o + foot)                 # solid, wider base
        body = circle(r_o).difference(circle(r_i))
        for i in range(baffles):
            a = 2 * math.pi * i / baffles
            rib = box(r_i - baffle_d, -baffle_d / 2.0, r_i + 1.0, baffle_d / 2.0)
            body = unary_union([body, rotate(rib, math.degrees(a), origin=(0, 0))])
        return body

    return region_at


def bowl_lid(bowl_id, shaft_d, height, spigot_h, wall, shaft_clear=2.0, fill_port=0.0,
             baffles=0, baffle_d=8.0, baffle_clear=0.6):
    """A lid that locates itself in the bowl, with a taper so the step is printable.

    Spinning a stiff paste at CNC speeds throws it. This closes the bowl and keeps the shaft
    centred; the shaft hole is deliberately LOOSE — this is a cover, not a bearing, and a lid that
    grips the shaft turns with it.

    THE STEP IS THE PROBLEM. A lid is a spigot that drops inside the bowl plus a skirt that covers
    the rim, and that is a 4.2mm horizontal ledge. Printed spigot-down it has nothing beneath it —
    a bridge, which this toolchain cannot do. Tapering the step over the same 4.2mm of height makes
    it 45 degrees, which prints unsupported. The taper is not decoration; without it the lid needs
    support and this generator has none to give.

    fill_port, if set, cuts a second opening so the mix can be topped up without stopping.
    """
    r_spig = (bowl_id - 0.6) / 2.0            # drops inside with a little slack
    r_skirt = r_spig + wall + 2.0
    step = r_skirt - r_spig
    r_hole = (shaft_d + shaft_clear) / 2.0

    # PRINTED UPSIDE DOWN, AND THAT IS THE WHOLE TRICK.
    # A lid is a thin face plus a spigot that drops into the bowl. Printed face-up, the face is a
    # roof over the spigot's void — a bridge, which this toolchain cannot do, and my first version
    # dodged that by making the lid a SOLID 14mm puck: 87g and 27 minutes for a cover.
    # Inverted, the face lands flat on the plate and the spigot grows upward off it. The taper then
    # runs inward as it rises, which is self-supporting. Flip it after printing.
    # --spigot-h WAS A DEAD PARAMETER. bowl_lid() took it and never read it: --spigot-h 6 and
    # --spigot-h 12 emitted BYTE-IDENTICAL files. The bands were derived from `wall` and `step`
    # alone, so the one number that decides HOW DEEP THE LID LOCATES IN THE BOWL could not be set —
    # and the audit measured the resulting lid seating only 5.40mm into a 91.8mm-deep vessel.
    #
    # The taper is NOT free: it must be at least `step` tall or its 45-degree wall becomes an
    # overhang this toolchain cannot print. So the spigot takes what it asks for, the taper takes
    # what physics demands, and the FACE gets the remainder — which is checked rather than assumed.
    taper_frac = min(0.3, step / max(height, 1e-9))
    if spigot_h and spigot_h > 0:
        spig_frac = spigot_h / max(height, 1e-9)
        face_frac = 1.0 - spig_frac - taper_frac
        _min_face = wall / max(height, 1e-9)      # a face thinner than one wall is not a lid
        if face_frac < _min_face:
            raise SystemExit(
                f"bowl_lid: --spigot-h {spigot_h:g}mm plus a {step:.1f}mm taper leaves "
                f"{face_frac*height:.1f}mm of face on a {height:g}mm lid — under the "
                f"{wall:g}mm (one wall) needed to be a lid rather than a ring.\n"
                f"  Raise --height to {math.ceil(spigot_h + step + wall)}, "
                f"or lower --spigot-h.")
    else:
        face_frac = min(0.6, max(0.15, (wall * 2) / max(height, 1e-9)))

    def region_at(t):
        _in_bowl = False
        if t <= face_frac:
            body = circle(r_skirt)                       # the lid face: solid, on the plate
        elif t <= face_frac + taper_frac:
            k = (t - face_frac) / max(taper_frac, 1e-9)
            r = r_skirt - step * k                       # 45 deg inward — self-supporting
            body = circle(r).difference(circle(max(r - wall, r_hole + 0.6)))
            _in_bowl = False
        else:
            body = circle(r_spig).difference(circle(r_spig - wall))   # spigot ring
            _in_bowl = True
        # THE BOWL HAS RIBS AND THE SPIGOT HAS TO GET PAST THEM. (Oleg, 2026-07-26: "it does not
        # close, remember the ribs".) mixer_bowl() grows `baffles` ribs INWARD from the inner wall
        # by baffle_d — 8mm by default — and this function used to size its spigot from bowl_id
        # alone, i.e. from the SMOOTH wall, as if the ribs did not exist. Measured on the pair that
        # was actually printed: bowl baffle tips at r=32.59, smallest lid radius r=39.74. The lid
        # was 7.15mm per side too big to enter and simply sat on top of the ribs.
        #
        # The fix is NOT to shrink the spigot to clear the tips — that abandons 8mm of location and
        # turns the rim step into a 12mm ledge that has to be tapered over most of the lid's height.
        # Instead the spigot is CASTELLATED: notches cut where the ribs are, so it drops between
        # them onto the full bore. Measured from the bowl's own gcode, the channels between ribs are
        # clear to r=40.60 while the tips reach r=32.60 — so the lobes keep the original radius and
        # only the four rib positions are cut away.
        #
        # It is strictly better than a plain spigot: the ribs now key the lid against rotation, and
        # a lid on a bowl of spinning paste WANTS that — otherwise the mix drags the cover round
        # with the paddle. And it costs nothing to print, because a notch is a vertical feature.
        #
        # The notch is built from the SAME box mixer_bowl() uses for the rib, dilated by clearance,
        # so the two parts cannot drift apart: the shared constraint is now shared in code rather
        # than duplicated as a number in two places, which is what broke it the first time.
        # ...AND ONLY THE SPIGOT. The first version of this notched EVERY band, because the cut sat
        # after the if/elif instead of inside it — so the lid FACE came out with four 12.5-degree
        # slots straight through it and the lid no longer sealed. Measured on the printed part:
        # 527 of 720 angle bins had face material, with four real gaps at 0/90/180/270. A cover with
        # holes in it is a worse failure than a cover that does not fit, because it looks fine.
        # The face and the rim taper sit ON or ABOVE the bowl rim and never pass a rib; only the
        # spigot descends into the bore, so only the spigot is cut.
        if baffles > 0 and _in_bowl:
            r_i = bowl_id / 2.0
            c = baffle_clear
            for i in range(baffles):
                a = 2 * math.pi * i / baffles
                notch = box(r_i - baffle_d - c, -(baffle_d / 2.0 + c), r_i + wall + 4.0, baffle_d / 2.0 + c)
                body = body.difference(rotate(notch, math.degrees(a), origin=(0, 0)))
        body = body.difference(circle(r_hole))
        if fill_port > 0 and t <= face_frac:
            body = body.difference(translate(circle(fill_port / 2.0),
                                             (r_spig + r_hole) / 2.0, 0))
        return body

    return region_at


def shelf_plate(width, depth, thickness, post_d, post_inset, layer_h, style="solid",
                rib=6.0, cell=26.0, clearance=0.30):
    """A shelf that threads onto the four posts. Two styles, because the choice is a real trade.

    SOLID  — every layer a full rectangle. Holds anything, including small objects and dust.
             Heavy and slow: a 300x200 plate is the biggest single part in the shelf.
    RIBBED — a border plus a grid of ribs, so it is mostly holes. Far less material and time,
             stiffer per gram (material at the edges resists bending, material at the neutral
             axis does almost nothing), but small things fall through.

    Both are flat plates of constant cross-section, so both print with no support. The bores are
    plain clearance holes, NOT pressure points: a shelf must SLIDE down the posts to its spacer and
    then rest there. Gripping is the collet's job at the top; a shelf that grips cannot be adjusted.
    That distinction is the reason these are different parts and not one part with a flag.
    """
    w, d = width / 2.0, depth / 2.0
    body = box(-w, -d, w, d)

    if style == "ribbed":
        inner = box(-w + rib, -d + rib, w - rib, d - rib)
        holes = []
        nx = max(1, int((width - 2 * rib) // cell))
        ny = max(1, int((depth - 2 * rib) // cell))
        cx = (width - 2 * rib) / nx
        cy = (depth - 2 * rib) / ny
        for i in range(nx):
            for j in range(ny):
                x0 = -w + rib + i * cx + rib / 2.0
                y0 = -d + rib + j * cy + rib / 2.0
                h = box(x0, y0, x0 + cx - rib, y0 + cy - rib)
                if inner.contains(h):
                    holes.append(h)
        if holes:
            body = body.difference(unary_union(holes))

    # post holes: clearance, so the shelf slides and rests rather than grips.
    # STICK_FIT, NOT SHRINK — these are BAMBOO posts. Missed when the two constants were split
    # apart, in the one function whose docstring says the plate must SLIDE down the posts: at
    # SHRINK it modelled 6.60mm, which prints to roughly the rod's own 6.35 and grips instead.
    r = (post_d + STICK_FIT + clearance) / 2.0
    for sx in (-1, 1):
        for sy in (-1, 1):
            body = body.difference(translate(circle(r),
                                             sx * (w - post_inset), sy * (d - post_inset)))
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
                    choices=["bracket", "foot", "coupler", "spacer2", "spacer3", "spacer4",
                             "gauge", "adapter", "shell", "mixer", "collet", "seat",
                             "postfoot", "bowl", "lid", "shelf"])
    ap.add_argument("--axle", type=float, default=6.0)
    ap.add_argument("--stick", type=float, default=6.35, help="1/4 inch bamboo (6.35mm)")
    ap.add_argument("--centres", type=float, default=32.0)
    ap.add_argument("--wall", type=float, default=4.0)
    ap.add_argument("--od", type=float, default=34.0, help="shell/mixer outer diameter")
    ap.add_argument("--od-small", type=float, default=14.0, help="collet narrow end")
    ap.add_argument("--od-large", type=float, default=22.0, help="collet wide end")
    ap.add_argument("--slots", type=int, default=3, help="collet splits")
    ap.add_argument("--slot-w", type=float, default=2.0)
    ap.add_argument("--width", type=float, default=300.0)
    ap.add_argument("--depth", type=float, default=200.0)
    ap.add_argument("--inset", type=float, default=14.0, help="post centre from the shelf edge")
    ap.add_argument("--style", default="solid", choices=["solid", "ribbed"])
    ap.add_argument("--rib", type=float, default=6.0)
    ap.add_argument("--cellsize", type=float, default=26.0)
    ap.add_argument("--spigot-h", type=float, default=6.0, help="lid spigot depth")
    ap.add_argument("--fill-port", type=float, default=0.0, help="lid top-up hole diameter")
    ap.add_argument("--baffles", type=int, default=4)
    ap.add_argument("--baffle-d", type=float, default=8.0)
    ap.add_argument("--blades", type=int, default=3)
    ap.add_argument("--blade-w", type=float, default=10.0)
    ap.add_argument("--hub-w", type=float, default=4.0)
    ap.add_argument("--twist", type=float, default=180.0, help="total blade twist over the height")
    ap.add_argument("--vents", type=int, default=0,
                    help="vertical vent slots — REQUIRED for expanding foam, 0 for gypsum+sand")
    ap.add_argument("--vent-w", type=float, default=4.0, help="vent slot width mm")
    ap.add_argument("--vent-from", type=float, default=0.55,
                    help="fraction of height above which vents open (lower wall stays closed)")
    ap.add_argument("--flat", type=float, default=0.5, help="D-shaft flat depth mm")
    ap.add_argument("--height", type=float, default=12.0)
    ap.add_argument("--bead-w", type=float, default=1.2)
    ap.add_argument("--layer-h", type=float, default=0.4)
    ap.add_argument("--flow", type=float, default=0,
                    help="0 = the material's measured ceiling (PLA keeps the max-flow rule)")
    ap.add_argument("--temp", type=int, default=0,
                    help="0 = machine.temp_for(material). A PLA 210 default reached TPU in every generator.")
    ap.add_argument("--bed", type=int, default=0, help="0 = machine.BED_TEMP['pla']")
    ap.add_argument("--press", type=float, default=0.10)
    # FIRST-LAYER WIDTH IS DERIVED, NOT A CONSTANT. Flow must be constant (Oleg: "flow must be
    # constant"), and speed is fixed, so layer 1 must carry the SAME mm2 as the body. Laid into a
    # PRESS_HARD gap that forces its width:  first_w = bead_w * layer_h / PRESS_HARD.
    # At 2.17 x 0.6 into a 0.1 gap that is ~13mm -- which is exactly the technique he described,
    # "you have to go 15mm wide in settings do not worry of massive over extrusion, this is what
    # we do". The old 3.0mm literal starved layer 1 to a quarter of the body's flow.
    ap.add_argument("--first-w", type=float, default=None)
    ap.add_argument("--fan", type=int, default=51,
                    help="0-255. 51 = 20%%, the PLA ceiling (machine.FAN_MAX). "
                         "Layer 1 always prints with the fan OFF regardless.")
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
    ap.add_argument("--material", default=None,
                    choices=sorted(machine.MATERIAL_TEMP),
                    help="stamped into the file; TPU is fan-guarded")
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED))
    ap.add_argument("--parts", default="",
                    help="ONE PLATE, many parts: 'coupler*3,bracket*2,foot'. Overrides --part.")
    ap.add_argument("--sequential", action="store_true", default=False,
                    help="print each part to full height before the next. REQUIRES a part gap "
                         "larger than the head radius (machine.HEAD_R) — see the guard.")
    ap.add_argument("--layerwise", dest="sequential", action="store_false",
                    help="all parts together, layer by layer (default, and the only safe mode "
                         "at small part gaps)")
    ap.add_argument("--part-gap", type=float, default=8.0,
                    help="mm between parts on a multi-part plate")
    ap.add_argument("--margin", type=float, default=12.0, help="mm kept clear at the bed edge")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    if a.first_w is None:
        a.first_w = a.bead_w * a.layer_h / machine.PRESS_HARD
    # MATERIAL ROUTES THE NOZZLE AND THE FLOW TOO — see machine.MATERIAL_TEMP.
    a.temp = a.temp or machine.temp_for(a.material)
    a.flow = machine.flow_for(a.material, a.flow or machine.FLOW, ' for solid.py')
    # THE MACHINE CAP COMPOSES WITH THE MATERIAL CAP. flow_for() clamps to what the FILAMENT holds
    # and never knew which MACHINE. The k1c/f022 hotend holds machine.PRINTER_FLOW_CAP (45) where
    # the k2plus holds 55, so a pla part built for the k1c through this path ran at the material's
    # 55 and overran the machine by 10 mm3/s. Compose them the way machine.flow_cap() does: the
    # lower of the two.
    _pcap = machine.PRINTER_FLOW_CAP.get(a.printer)
    if _pcap is not None and a.flow > _pcap + 1e-9:
        print(f"  ! flow {a.flow:g} mm3/s is above the {a.printer} machine cap {_pcap:g} mm3/s — "
              f"clamped to {_pcap:g}.")
        a.flow = _pcap
    machine.check_flow(a.flow, f' for solid.py')
    if a.parts:
        return run_plate(a)
    region = build_part(a.part, a)
    if a.cavity > 0:
        if callable(region):
            raise SystemExit(
                '--cavity cannot be combined with a part whose cross-section varies with\n'
                '  height (bowl, lid, mixer, shell, collet, seat, postfoot). shelled() erodes a\n'
                '  STATIC region; those parts are already a function of layer fraction.\n'
                '  Print them without --cavity, or put only static parts on a cavity plate.')
        region = shelled(region, a.cavity, a.floor, a.height, a.layer_h)
    # THE FILENAME MUST DISTINGUISH THE PARTS. A vented foam shell and a sealed gypsum shell differ
    # only in --vents, and both wrote to the same name — so the second silently replaced the first
    # and either could be printed believing it was the other.
    # ANY ARGUMENT THAT CHANGES THE PART MUST CHANGE THE FILENAME.
    # Fixed once tonight for --vents, then immediately repeated for --style: a solid and a ribbed
    # shelf differ by 193g and an hour and were writing to the same name, so the second silently
    # replaced the first. Encoding the discriminating argument is not optional.
    _tag = (f"_v{a.vents}" if a.part == "shell"
            else f"_{a.style}" if a.part == "shelf"
            else "")
    return finish(region, a, a.part,
                  f"{a.out}/{a.part}_{a.printer}_s{a.stick:g}_c{a.centres:g}"
                  f"_h{a.height:g}{_tag}_T{a.temp}.gcode")


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
        # Sweeps RAW diameters (fit=0) so the emitted holes are exactly what is measured:
        # 6.80 / 7.05 / 7.30 on a 6.35 stick. Oleg picked the middle 2026-07-27, which is
        # what STICK_FIT=0.70 now encodes. Re-run this on any new stick or filament batch.
        # (This comment carried 6.55/6.80/7.05 and 0.45 — the numbers from my FIRST, WRONG reading,
        #  which had been corrected in the constant and left standing here. A stale comment beside
        #  a corrected constant is how a wrong number gets adopted twice.)
        region = plate([(i * (a.stick * 2.6 + 8), 0, a.stick + 0.45 + 0.25 * i)
                        for i in range(3)], 3.0, fit=0.0)
    elif part == "shelf":
        # --clearance never reached this part: it kept its own default 0.30 whatever was passed,
        # so the ONE part that must slide freely was the one you could not loosen. The 0.30 stays
        # as the default (a shelf slides; it does not grip), but it is now overridable.
        return shelf_plate(a.width, a.depth, a.height, a.stick, a.inset, a.layer_h,
                           style=a.style, rib=a.rib, cell=a.cellsize,
                           clearance=0.30 if a.clearance == 0.0 else a.clearance)
    elif part == "lid":
        # THE LID TAKES THE BOWL'S OWN BAFFLE ARGUMENTS. Same --baffles/--baffle-d the bowl was
        # built with, so the notches are derived from the ribs rather than guessed alongside them.
        return bowl_lid(a.od, a.axle, a.height, a.spigot_h, a.wall, fill_port=a.fill_port,
                        baffles=a.baffles, baffle_d=a.baffle_d)
    elif part == "bowl":
        _paddle = a.od_small
        print(f"  bowl ID {a.od:g} vs paddle {_paddle:g} -> shear gap "
              f"{(a.od - _paddle)/2:.1f} mm per side")
        return mixer_bowl(a.od, a.height, a.wall, a.floor, a.layer_h,
                          baffles=a.baffles, baffle_d=a.baffle_d)
    elif part == "postfoot":
        return post_foot(a.stick, a.od, a.od_small, a.height, a.wall, a.floor, a.layer_h)
    elif part == "seat":
        return collet_seat(a.od_small, a.od_large, a.od, a.height, a.wall)
    elif part == "collet":
        return collet(a.stick, a.od_small, a.od, a.slots, a.slot_w, a.height, a.wall,
                      clearance=a.clearance)
    elif part == "mixer":
        return mixer(a.axle, a.od, a.blades, a.blade_w, a.hub_w, a.twist,
                     a.height, a.layer_h, clearance=a.clearance)
    elif part == "shell":
        return spacer_shell(a.stick, a.od, a.wall, a.height, a.floor, a.layer_h,
                            vents=a.vents, vent_w=a.vent_w, vent_from=a.vent_from,
                            clearance=a.clearance)
    elif part == "coupler":
        region = plate([(0, 0, a.stick)], a.wall, clearance=a.clearance)
    else:
        n = int(part[-1])
        region = plate([(i * a.centres, 0, a.stick) for i in range(n)], a.wall,
                       clearance=a.clearance, hollow=a.hollow)
    return region


def finish(region, a, label, fn):
    g, st = emit(region, a.height, a.bead_w, a.layer_h, a.flow, a.temp,
                 a.bed or machine.bed_for(a.material, a.printer), 1.75, machine.BED[a.printer],
                 not a.no_home, a.press, a.fan, a.first_w, a.aux, a.printer,
                 f"{label.upper()} stick{a.stick:g} wall{a.wall:g}", material=a.material)
    os.makedirs(a.out, exist_ok=True)
    open(fn, "w").write(g)
    print(f"{fn}")
    # THE SUMMARY MUST DESCRIBE THE FILE. This line printed "(with brim NNxNN)" unconditionally,
    # including on files generated with --brim 0 that contain no brim at all. A summary that
    # disagrees with its own artifact is how a wrong number gets believed.
    _brimtxt = f"(with brim {st['size'][0]+9}x{st['size'][1]+9})" if a.brim else "(no brim)"
    print(f"  part {st['size'][0]}x{st['size'][1]}mm "
          f"{_brimtxt}, "
          f"{st['rings']} concentric contours, "
          f"{st['layers']} layers = {a.height}mm tall")
    print(f"  {st['speed']} mm/s at flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g")
    return st


# A REGION MAY BE A FUNCTION OF HEIGHT, AND THE PLATE PACKER ASSUMED IT NEVER WAS.
# build_part() returns either a static shapely geometry or a callable of layer fraction — every
# interesting part (bowl, lid, mixer, shell, collet, seat, postfoot) is the latter, because its
# cross-section changes as it climbs. run_plate() called .bounds and translate() on whatever it got,
# so `--parts "bowl,lid"` died with `AttributeError: 'function' object has no attribute 'bounds'`.
# That is why the ONE mechanism that could build two mating parts from a single argument set — and
# so make it impossible for them to disagree — was unusable on exactly the parts that keep
# disagreeing. The lid was built --od 81.2 against an --od 80 bowl precisely because they were
# generated by two separate commands.
def _rbounds(r, samples=(0.0, 0.25, 0.5, 0.75, 1.0)):
    """Bounds over the WHOLE part, not one layer of it."""
    if not callable(r):
        return r.bounds
    bs = [r(t).bounds for t in samples]
    return (min(b[0] for b in bs), min(b[1] for b in bs),
            max(b[2] for b in bs), max(b[3] for b in bs))


def _rtranslate(r, dx, dy):
    if not callable(r):
        return translate(r, dx, dy)
    return lambda t, _r=r, _dx=dx, _dy=dy: translate(_r(t), _dx, _dy)


def _runion(rs):
    rs = list(rs)
    if not any(callable(r) for r in rs):
        return unary_union(rs)
    return lambda t, _rs=rs: unary_union([(_r(t) if callable(_r) else _r) for _r in _rs])


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
    built.sort(key=lambda it: -(_rbounds(it[1])[3] - _rbounds(it[1])[1]))
    placed, x, y, shelf_h = [], 0.0, 0.0, 0.0
    for name, r in built:
        minx, miny, maxx, maxy = _rbounds(r)
        w, h = maxx - minx, maxy - miny
        if x > 0 and x + w > usable_x:
            x, y, shelf_h = 0.0, y + shelf_h + gap, 0.0
        placed.append((name, _rtranslate(r, x - minx, y - miny)))
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
    _ax = [c for _, r in placed for c in (_rbounds(r)[0], _rbounds(r)[2])]
    _ay = [c for _, r in placed for c in (_rbounds(r)[1], _rbounds(r)[3])]
    off_x = (bed_x - (max(_ax) + min(_ax))) / 2.0
    off_y = (bed_y - (max(_ay) + min(_ay))) / 2.0
    placed = [(n, _rtranslate(r, off_x, off_y)) for n, r in placed]

    counts = ", ".join(f"{n}x {name}" for name, n in spec)
    print(f"  plate: {counts} — {len(built)} parts, {x if y == 0 else usable_x:.0f}x{total_h:.0f}mm")
    fn = f"{a.out}/plate_{a.printer}_{len(built)}parts_h{a.height:g}_T{a.temp}.gcode"

    if a.sequential:
        # THE HEAD SWEEPS A CYLINDER, NOT A POINT.
        # While part N prints at first-layer height, everything within HEAD_R of the nozzle that is
        # taller than the current layer is in the head's path. Lifting between parts does not help:
        # the collision happens DURING printing. Oleg lost two plates to this before it was modelled.
        need = machine.HEAD_R[a.printer] + a.bead_w
        if a.part_gap < need:
            raise SystemExit(
                f"--sequential needs a part gap of at least {need:.0f}mm on the {a.printer} "
                f"(HEAD_R {machine.HEAD_R[a.printer]:.0f}mm"
                f"{'' if machine.HEAD_R_MEASURED else ', UNVERIFIED — measure yours'}"
                f"), but --part-gap is {a.part_gap:g}mm.\n"
                f"  While the head prints one part, its heater block and fan shroud sweep a "
                f"{machine.HEAD_R[a.printer]:.0f}mm radius through anything already standing "
                f"nearby — a Z-hop between parts does not prevent it.\n"
                f"  Either raise --part-gap to {math.ceil(need)} (which fits far fewer parts), or "
                f"drop --sequential and print layer-by-layer, where every part grows together and "
                f"nothing finished is ever taller than the head's current height.")
        return emit_sequential(placed, a, counts, fn)

    region = _runion([r for _, r in placed])
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
                     a.bed or machine.bed_for(a.material, a.printer), 1.75, machine.BED[a.printer],
                     not a.no_home, a.press, a.fan, a.first_w, a.aux, a.printer,
                     f"{name.upper()} #{i+1}", material=a.material, centre=False)
        pre, _, post = g.partition("; BODY_START\n")
        if head is None:
            head = pre + "; BODY_START\n"
        body = post.split("; BODY_END")[0] if "; BODY_END" in post else post
        # drop the tail (M107/M104 S0/park) — it belongs once, at the end of the whole plate
        body = "\n".join(ln for ln in body.splitlines()
                         if not ln.startswith(("M107", "M104 S0", "M140 S0", "G0 X10 Y"))
                         and not re.match(r"^G1 Z\d+\.\d+ F900$", ln))
        bodies.append((name, body, st))

    safe_z = a.height + 2.0
    travel_f = int(machine.MACHINE_MAX_SPEED * 60)
    # TAKE THE FEEDRATE FROM THE BODY THAT WAS ACTUALLY EMITTED, do not recompute it. This line
    # re-derived speed from the REQUEST, so any difference between the request and what emit()
    # resolved (the north star cap, or a fat bead crawling under it) would have restored a feedrate
    # the bodies never used — a second speed in a print allowed exactly one, appearing only after
    # the first inter-part travel.
    print_f = bodies[0][2]["feed"]
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
    # PARK WHERE THE PLATE ACTUALLY IS. This was hardcoded to Y340 — a K2 coordinate — and on the
    # K1C's 220mm bed that is 120mm off the plate. validate.py caught it as "XY off bed"; it would
    # otherwise have driven the head into the frame at the end of every sequential print.
    _bx, _by = machine.BED[a.printer]
    L.append(f"G0 X{min(10.0, _bx - 10):.0f} Y{_by - 10:.0f} F9000")
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
