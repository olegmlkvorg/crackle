#!/usr/bin/env python3
"""PETALWALL — the bucket as two prints: a floor with a wall stub, and flat wall panels that
wrap warm around it (single curvature — the proven cuff / wave-flower regime).

--part floor   unchanged: the rosette floor (crossing lifts, rim band) + an 8mm 2-bead stub,
               the register and weld target for the wrap.

--part wall    v2, after the first printed panel was judged in hand. Oleg, 2026-07-28:
               "adhesion between lines is bad. structurally very weak wall, make double
               strenth and this patterna is ugly. get something pretty like anime characters
               shapes ... at lease lets do 2 [panels]. you can reduce the dia of base."
               v1 was an open lattice of single strands welding at POINTS — the point-weld
               that has failed this project before. v2 changes CONSTRUCTION CLASS: a solid
               3-layer sheet filled with concentric contours (solid.py's proven method), so
               every bead welds to its neighbour along its FULL length; the pattern is a
               frieze of original chibi silhouettes cut through as WINDOWS — light draws the
               characters, and the fill ripples outward around each one until it merges.
               Every window edge is a closed multi-bead contour by construction.
               Two panels, mirrored casts (--segment 1 / 2), weld at 6mm end tabs.

Numbers with provenance:
  dia 200                       PINNED — the d200 floor+stub is PRINTED and the client called
                                it perfect; a smaller dia means reprinting an approved 64g
                                part. Two panels of pi*201.3/2 + 6mm tab = 322mm fit the
                                334mm printable width only while the taper stays under ~1.1deg
  taper 0 (was 2deg)            CHOSEN — the flare budget d200 leaves (<1.1deg) is invisible
                                on a 200mm wall, so the bucket is a straight cylinder and the
                                panel a plain rectangle; pass --taper if dia ever shrinks
  3 layers = 1.3mm sheet        CHOSEN — "double strength": vs the v1 lattice this is a
                                class jump, and 1.3mm at r~101 is 0.65% bend strain (t/2r),
                                far under what warm PLA takes (cold PLA yields ~2%)
  window min feature 14mm       DERIVED — layer 1 presses 0.1 at full flow, a ~12mm ribbon;
                                the measured hole inset is ~3mm/side (machine.BORE_INSET_MM),
                                so details under 14mm close. Chibi proportions are the
                                printable regime here, not only a style.
  webs between windows >= 8mm   CHOSEN — 4 beads; enforced below, with a tear guard: no
                                vertical line may lose more than 55% of the panel height
  tab 6mm                       CHOSEN — carried from v1 (a 3-bead weld land; also the slack
                                that absorbs stub-OD error — measure the stub, pass --dia)
  forming window                UNMEASURED — the standing gap; bed-warm forming (120C plate
                                holds the sheet above Tg) is the fallback route
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely import affinity
import machine
from bucket import rose, crossing_z, ring_of
from solid import contours as sheet_contours, densify as sheet_densify, \
    decimate as sheet_decimate


# ---------------- ANIME FRIEZE — original chibi silhouettes, coded as geometry ----------------
# Builders return cutout polygons in mm: feet on y=0, centred on x=0, about `s` tall. All of
# them are unions of fat primitives on purpose: layer 1's pressed ribbon blurs ~5mm into every
# window edge, so whiskers, wands and thin ears were never going to survive — fat heads and
# stub limbs are what prints, and happily that IS the chibi look.

def _c(x, y, r):
    return Point(x, y).buffer(r, 40)


def _ell(x, y, rx, ry, deg=0.0):
    g = affinity.scale(_c(0, 0, 1.0), rx, ry)
    if deg:
        g = affinity.rotate(g, deg)
    return affinity.translate(g, x, y)


def _chunky(g, name, r=1.5):
    """Open-then-close: trims any spike thinner than 2r, rounds every corner. The style guard —
    a detail this pass removes was never going to survive the layer-1 ribbon anyway."""
    g = g.buffer(-r, 8).buffer(2 * r, 8).buffer(-r, 8)
    if g.geom_type == "MultiPolygon":
        parts = sorted(g.geoms, key=lambda p: -p.area)
        if parts[1].area > 0.01 * parts[0].area:
            raise SystemExit(f"frieze: {name} falls apart under the {2*r:g}mm chunky pass — "
                             f"fatten the joint")
        g = parts[0]
    return g.simplify(0.25)


def _cat(s):
    head = _c(0, 0.66 * s, 0.26 * s)
    ears = [Polygon([(m * 0.24 * s, 0.76 * s), (m * 0.36 * s, 1.02 * s),
                     (m * 0.04 * s, 0.90 * s)]) for m in (-1, 1)]
    body = _ell(0, 0.30 * s, 0.30 * s, 0.31 * s)
    # tail: a HALF arc, free end clear of the body — a full curl would enclose a solid island
    # inside the window, and an island in a cutout is an orphan part on layers 2+
    tail = LineString([(0.30 * s + 0.13 * s * math.cos(math.radians(t)),
                        0.30 * s + 0.20 * s * math.sin(math.radians(t)))
                       for t in range(-85, 31, 12)]).buffer(0.075 * s, 8)
    return unary_union([head, body, tail] + ears)


def _ghost(s):
    g = _c(0, 0.66 * s, 0.31 * s).union(box(-0.31 * s, 0.16 * s, 0.31 * s, 0.66 * s))
    for gx in (-0.2325, -0.0775, 0.0775, 0.2325):       # the wavy hem
        g = g.difference(_c(gx * s, 0.16 * s, 0.0775 * s))
    for m in (-1, 1):                                   # stub arms, raised in a boo
        g = g.union(_c(m * 0.385 * s, 0.66 * s, 0.11 * s))
    return g


def _bunny(s):
    head = _c(0, 0.36 * s, 0.295 * s)
    ears = [_ell(m * 0.15 * s, 0.74 * s, 0.10 * s, 0.30 * s, -m * 14) for m in (-1, 1)]
    return unary_union([head] + ears)


def _girl(s):
    head = _c(0, 0.76 * s, 0.22 * s)
    buns = [_c(m * 0.285 * s, 0.86 * s, 0.11 * s) for m in (-1, 1)]    # twin hair buns
    dress = Polygon([(-0.085 * s, 0.58 * s), (0.085 * s, 0.58 * s),    # A-line flare
                     (0.34 * s, 0.06 * s), (-0.34 * s, 0.06 * s)])
    arms = [_c(m * 0.185 * s, 0.46 * s, 0.08 * s) for m in (-1, 1)]
    ahoge = Polygon([(-0.02 * s, 0.95 * s), (0.06 * s, 1.10 * s), (0.11 * s, 0.97 * s)])
    return unary_union([head, dress, ahoge] + buns + arms)


def _star(s):
    pts = []
    for i in range(10):
        r = (0.50 if i % 2 == 0 else 0.235) * s
        a = math.pi / 2 + i * math.pi / 5
        pts.append((r * math.cos(a), 0.5 * s + r * math.sin(a)))
    return Polygon(pts)


def _heart(s):
    lobes = [_c(m * 0.165 * s, 0.60 * s, 0.235 * s) for m in (-1, 1)]
    v = Polygon([(-0.375 * s, 0.52 * s), (0.375 * s, 0.52 * s), (0.0, 0.02 * s)])
    return unary_union(lobes + [v])


def _sakura(s):
    """Five petal WINDOWS around a solid hub — the flower reads from the webs between them,
    each petal carrying the classic sakura tip notch. Geometry note: 14mm petals + 8mm webs
    only coexist above s ~ 85, so the sakura is a statement bloom, never a small accent."""
    petals = []
    for i in range(5):
        p = _ell(0, 0.37 * s, 0.085 * s, 0.145 * s)
        p = p.difference(_c(0, 0.515 * s, 0.035 * s))
        petals.append(affinity.rotate(p, 72 * i, origin=(0, 0)))
    return [affinity.translate(p, 0, 0.5 * s) for p in petals]


FRIEZE = {"cat": _cat, "ghost": _ghost, "bunny": _bunny, "girl": _girl,
          "star": _star, "heart": _heart, "sakura": _sakura}

# The parade, per panel: (name, height mm, u across the panel, base y, tilt deg, mirror).
# Ground register (walkers) + sky register (floaters), staggered so no vertical line carries
# two big windows — sizes and tilts vary so it reads alive, not tiled. The two panels carry
# DIFFERENT casts: same trapezoid, different party.
CAST = {
    1: [("bunny", 76, 0.115, 18, 5, False),
        ("star", 38, 0.215, 148, -12, False),
        ("cat", 82, 0.30, 16, -3, False),
        ("heart", 33, 0.44, 150, 10, False),
        ("ghost", 68, 0.567, 36, -8, False),
        ("star", 32, 0.60, 154, 8, False),
        ("star", 34, 0.75, 142, 15, False),
        ("girl", 88, 0.822, 22, 2, False)],
    2: [("heart", 33, 0.10, 148, 10, False),
        ("cat", 84, 0.16, 18, 4, False),
        ("ghost", 56, 0.33, 128, 6, True),
        ("sakura", 86, 0.46, 22, 0, False),
        ("star", 36, 0.50, 150, -10, False),
        ("star", 38, 0.645, 146, -14, False),
        ("girl", 88, 0.80, 20, -2, True),
        ("star", 34, 0.90, 116, 18, False)],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", choices=("floor", "wall"), required=True)
    ap.add_argument("--dia", type=float, default=200.0,
                    help="bucket diameter — 200 is PINNED by the already-printed floor; two "
                         "panels fit the bed at taper 0. Pass the MEASURED stub OD here.")
    ap.add_argument("--height", type=float, default=200.0, help="wall panel height")
    ap.add_argument("--stub", type=float, default=8.0, help="floor: stub wall height")
    ap.add_argument("--floor-layers", type=int, default=5)
    ap.add_argument("--close", type=float, default=12.0)
    ap.add_argument("--segments", type=int, default=2,
                help="2 fits the 334mm printable width at d190 (client: 'at least lets do 2')")
    ap.add_argument("--segment", type=int, default=1,
                    help="which wall panel (1-based) — each carries a different cast")
    ap.add_argument("--taper", type=float, default=0.0,
                    help="bucket flare, degrees; d200 x 2 panels leaves <1.1deg of room, "
                         "which is invisible — straight cylinder by default")
    ap.add_argument("--rail", type=float, default=None, help="floor rim width; default 3 beads")
    ap.add_argument("--tab", type=float, default=6.0,
                    help="extra panel width so the ends OVERLAP the next panel (weld land)")
    ap.add_argument("--wall-layers", type=int, default=3,
                    help="sheet layers (pressed + n-1); 3 = 1.3mm, 0.65% bend strain at r~101")
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    flow = machine.flow_cap(a.material, a.printer)
    bw = machine.bead_for_flow(flow, a.layer_h)
    speed = machine.speed_for_flow(flow, bw, a.layer_h)
    temp = machine.temp_for(a.material)
    lh = a.layer_h
    bx, by = machine.BED[a.printer]
    A = math.pi * (1.75 / 2) ** 2
    e_per_mm = bw * lh / A
    f = round(speed * 60)
    seg = max(0.25, speed / 250.0)

    L = []
    w = L.append

    def header(name, layers, arch=True):
        w(f"; MATERIAL={a.material}")
        w(f"; LAYER_H={lh}")
        w(f"; FLOW={bw*lh*speed:.4f}")
        w(f"; PRINTER={a.printer}")
        w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
        w("; ARGV: " + " ".join(sys.argv))
        w(f"; PETALWALL {name}")
        if arch:   # the floor lifts over crossings; the wall sheet is flat — its overhang
            w(f"; ARCH_LIFT={0.5 - machine.PRESS_HARD:.3f}")   # check must RUN, so no stamp
        w("; HEADER_BLOCK_START"); w(f"; total layer number: {layers}"); w("; HEADER_BLOCK_END")
        w("M82")
        w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
        w(f"M104 S{temp}")
        w("G28")
        # THE FOOTPRINT RULE, INHERITED FROM THE FLOOR THAT STUCK: a 200mm part waits for the
        # FULL held target, not the start-early floor — petalfloor started at 115 on a climbing
        # cold plate and PEELED at ~7min (Oleg: "baking to plate failed"); the emitted layer-1
        # numbers were correct (0.1 press, 12mm spread), the wait was the deviation.
        _bed = machine.bed_for(a.material, a.printer)
        _floor_wait = _bed if a.printer == "k2plus" else machine.bed_start(a.material, _bed)
        w(f"M190 S{_floor_wait:.0f}")
        w(f"M140 S{_bed:.0f}")
        w(f"M109 S{temp}")
        w("G92 E0")
        w(f"G1 Z{machine.PRESS_HARD:.3f} F600")
        w(f"G0 F9000 X20.000 Y20.000")
        w("G1 E20 F300                      ; PRIME stationary purge")
        w(f"G1 F1200 X60.000 Y20.000 E30   ; PRIME line, in the clear")
        w(f"G0 F3000 X72.000 Y32.000  ; PRIME break-off — angled wipe, no extrusion")
        w("G92 E0")
        w("; BODY_START")

    e = 0.0
    pos = [None, None, None]

    def stroke(pts, z, first=False, zs=None):
        nonlocal e
        base = z - machine.PRESS_HARD
        z0 = (base + zs[0]) if zs else z
        if first:
            w(f"G0 F9000 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; PRIME-TRAVEL")
            w(f"G1 F1800 Z{z0:.3f}")
            w(f"G1 F{f}")
            pos[0], pos[1], pos[2] = pts[0][0], pts[0][1], z0
        else:
            if pos[2] <= z + 1e-9:
                w(f"G1 F1800 Z{z:.3f}")
                pos[2] = max(pos[2], z)
            d0 = math.hypot(pts[0][0] - pos[0], pts[0][1] - pos[1])
            if d0 > 0.02:
                e += math.hypot(d0, z0 - pos[2]) * e_per_mm
                w(f"G1 F{f} X{pts[0][0]:.3f} Y{pts[0][1]:.3f} Z{z0:.3f} E{e:.5f}")
                pos[0], pos[1], pos[2] = pts[0][0], pts[0][1], z0
            else:
                w(f"G1 F{f}")
        qx, qy, qz = pos[0], pos[1], pos[2]
        for i, (X, Y) in enumerate(pts[1:], 1):
            d = math.hypot(X - qx, Y - qy)
            if d < 0.02:
                continue
            zz = (base + zs[i]) if zs else z
            e += math.hypot(d, zz - qz) * e_per_mm
            w(f"G1 X{X:.3f} Y{Y:.3f} Z{zz:.3f} E{e:.5f}")
            qx, qy, qz = X, Y, zz
        pos[0], pos[1], pos[2] = qx, qy, qz

    def nearest_start(ring):
        if pos[0] is None:
            return ring + [ring[0]]
        i = min(range(len(ring)),
                key=lambda k: (ring[k][0]-pos[0])**2 + (ring[k][1]-pos[1])**2)
        out = ring[i:] + ring[:i]
        return out + [out[0]]

    if a.part == "floor":
        cx, cy = bx / 2.0, by / 2.0
        R = a.dia / 2.0
        rim_passes = max(2, round((a.rail or 3 * bw) / bw))
        rose_pts = rose(cx, cy, R - bw / 2, (R - bw / 2) * 0.11)
        rose_pts = machine.decimate(rose_pts, machine.CONSTANT_SPEED / 300.0 * 1.2)
        rose_region = LineString(rose_pts).buffer(bw / 2.0, resolution=8)
        env = rose_region.buffer(a.close, resolution=64).buffer(-a.close, resolution=64)
        if env.geom_type == 'MultiPolygon':
            env = max(env.geoms, key=lambda g: g.area)
        rim_rings = []
        for j in range(rim_passes):
            rp = env.buffer(-(bw / 2.0 + j * bw))
            if rp.geom_type == 'MultiPolygon':
                rp = max(rp.geoms, key=lambda g: g.area)
            rim_rings.append(ring_of(rp.exterior, seg))
        stub_laps = max(1, int(round(a.stub / lh)))
        n_layers = a.floor_layers + stub_laps
        header(f"floor d{a.dia:g} + stub {a.stub:g}", n_layers)
        w("M107                              ; layer 1 bonds uncooled")
        for k in range(a.floor_layers):
            z = machine.PRESS_HARD + k * lh
            j = min(range(len(rose_pts) - 1),
                    key=lambda i: (rose_pts[i][0]-(pos[0] or cx+R))**2
                                + (rose_pts[i][1]-(pos[1] or cy))**2)
            rpts = rose_pts[j:-1] + rose_pts[:j] + [rose_pts[j]]
            rz, _ = crossing_z(rpts, bw, machine.PRESS_HARD, 0.5)
            stroke(rpts, z, first=(k == 0), zs=rz)
            prior = list(rpts)
            for ring in rim_rings:
                cpts = nearest_start(ring)
                cz, _ = crossing_z(cpts, bw, machine.PRESS_HARD, 0.5, prior=prior)
                stroke(cpts, z, zs=cz)
                prior += cpts
            if k == 0:
                w("M106 S51                        ; 20% fan from layer 2")
        # STUB: a 2-bead vase wall on the envelope — the wrap's register and weld target
        stub_rings = [ring_of(env.buffer(-(bw / 2.0 + j * bw)).exterior
                              if env.buffer(-(bw / 2.0 + j * bw)).geom_type == 'Polygon'
                              else max(env.buffer(-(bw / 2.0 + j * bw)).geoms,
                                       key=lambda g: g.area).exterior, seg)
                      for j in (0, 1)]
        z_ft = machine.PRESS_HARD + (a.floor_layers - 1) * lh
        for s_ in range(stub_laps):
            z = z_ft + (s_ + 1) * lh
            for ring in stub_rings:
                stroke(nearest_start(ring), z)
        grams = e * A * 1.24 / 1000.0
        mins = (e / e_per_mm) / speed / 60.0
        fn = os.path.join(a.out, f"petalfloor_{a.printer}_d{a.dia:g}_T{temp:g}.gcode")
        summary = (f"  floor {a.floor_layers} layers + {stub_laps}-lap 2-bead stub; "
                   f"~{grams:.0f} g, ~{mins:.0f} min")

    else:
        # ---- WALL PANEL v2: solid 3-layer sheet, chibi-silhouette windows, contour fill ----
        # The sheet is a shapely region (trapezoid minus the cast's cutouts) walked in
        # concentric contours one bead apart — solid.py's method, where every window edge is
        # a closed ring welded full-length to its neighbours. One continuous stroke per
        # layer; ring-to-ring jogs are thin tagged LINKs that never cross a window.
        t_sheet = machine.PRESS_HARD + (a.wall_layers - 1) * lh
        peri = math.pi * (a.dia + t_sheet)          # wrap length at the sheet's midplane;
                                                    # pass the MEASURED stub OD as --dia
        Lb = peri / a.segments + a.tab               # + tab: ends overlap the next panel
        Lt = Lb + 2 * math.pi * a.height * math.tan(math.radians(a.taper)) / a.segments
        H = a.height
        if Lt > bx - 16 or H > by - 16:
            raise SystemExit(f"panel {Lt:.0f}x{H:.0f} exceeds the {bx:.0f}x{by:.0f} bed — "
                             f"more --segments or less --height")
        ox = (bx - Lt) / 2.0
        oy = (by - H) / 2.0
        BL = (ox + (Lt - Lb) / 2.0, oy)
        BR = (ox + (Lt + Lb) / 2.0, oy)
        TR = (ox + Lt, oy + H)
        TL = (ox, oy + H)
        trap = Polygon([BL, BR, TR, TL])

        # 12mm solid frame: bottom band welds to the 8mm stub, top band is the rim hoop,
        # end bands are the 6mm overlap tabs plus margin
        MARGIN = 12.0
        safe = trap.buffer(-MARGIN, join_style=2)

        def edge_x(y):               # panel x-range at height y, following the slanted sides
            fr = (y - oy) / H
            half = Lb / 2.0 + (Lt - Lb) / 2.0 * fr
            return ox + Lt / 2.0 - half, ox + Lt / 2.0 + half

        if a.segment not in CAST:
            raise SystemExit(f"--segment {a.segment}: no cast defined (have {sorted(CAST)})")
        cutouts = []                                  # (label, polygon)
        for name, s, u, base, tilt, mirror in CAST[a.segment]:
            polys = FRIEZE[name](s)
            for j, p in enumerate(polys if isinstance(polys, list) else [polys]):
                p = _chunky(p, name)
                if mirror:
                    p = affinity.scale(p, -1.0, 1.0, origin=(0, 0))
                if tilt:
                    p = affinity.rotate(p, tilt, origin=(0, 0.5 * s))
                x0, x1 = edge_x(min(max(oy + base + 0.5 * s, oy), oy + H))
                p = affinity.translate(p, x0 + u * (x1 - x0), oy + base)
                cutouts.append((f"{name}{s:g}@u{u:g}" + (f".{j}" if isinstance(polys, list)
                                                         else ""), p))

        # THE GUARDS FAIL, THEY DO NOT ADVISE (rules-enforced-not-remembered). Each one is a
        # print-loss mode seen or derived, not taste.
        fails = []
        holes = unary_union([p for _, p in cutouts])
        for lab, p in cutouts:
            if list(p.interiors):
                fails.append(f"{lab}: encloses a solid ISLAND — an orphan part inside a window")
            if not p.within(safe):
                fails.append(f"{lab}: breaks into the {MARGIN:g}mm solid frame "
                             f"(weld bands / tabs)")
            if p.buffer(-7.0).is_empty:
                fails.append(f"{lab}: no 14mm-wide core — the layer-1 ribbon closes it")
        labs = [c[0] for c in cutouts]
        for i in range(len(cutouts)):
            for j in range(i + 1, len(cutouts)):
                d = cutouts[i][1].distance(cutouts[j][1])
                if d < 8.0:
                    fails.append(f"{labs[i]} and {labs[j]} only {d:.1f}mm apart — the web "
                                 f"between windows must be >= 8mm (4 beads)")
        for xq in range(int(ox) + 2, int(ox + Lt), 2):   # no weak vertical tear line
            cut = LineString([(xq, oy - 1), (xq, oy + H + 1)]).intersection(holes).length
            if cut > 0.55 * H:
                fails.append(f"vertical tear line at x={xq}: {cut:.0f}mm of {H:g}mm cut away")
        if fails:
            raise SystemExit("frieze guards:\n  " + "\n  ".join(fails))

        region = trap.difference(holes)
        if region.geom_type != "Polygon":
            raise SystemExit("the cutouts slice the panel into pieces")
        rings = sheet_contours(region, bw)
        fill = sum(LineString(r).length for r in rings) * bw / region.area
        if fill > 1.02:
            raise SystemExit(f"contours cover {fill:.3f}x the region — the layer would climb "
                             f"into the nozzle (see solid.py's fill guard)")

        header(f"wall panel {a.segment}/{a.segments} {Lb:.0f}->{Lt:.0f} x {H:g}, "
               f"{len(cutouts)} windows", a.wall_layers, arch=False)
        w("M107                              ; layer 1 bonds uncooled")

        holes_t = holes.buffer(-0.8)   # a link may kiss a window's spread zone, never cross it
        from shapely.prepared import prep
        _ph = prep(holes_t)

        def clean(p0, p1):
            if (p0[0] - p1[0]) ** 2 + (p0[1] - p1[1]) ** 2 < 4.0:
                return True
            return not _ph.intersects(LineString([p0, p1]))

        WPS = [p for r in rings for p in r[::25]]   # waypoint bank: points on solid material
        n_drop = 0

        def order_loops(here):
            """Rings in nearest-first order, each entered where the approach stays out of the
            windows — a jog across a window would draw a thread across the character, the one
            place a link is not harmless overprint. A walled-in ring (a hub behind petals)
            takes one waypoint over solid material (two thin legs); a ring no route reaches —
            a recovered sliver inside a notch, e.g. between the bunny's ears — is DROPPED,
            the same small-void trade the clash filter already makes, unless it is a window
            wall, which must never be dropped."""
            nonlocal n_drop
            todo = [r[:-1] if r[0] == r[-1] else list(r) for r in rings]
            out = []          # (via_or_None, loop)
            while todo:
                near = sorted(range(len(todo)),
                              key=lambda i: min((p[0] - here[0]) ** 2 + (p[1] - here[1]) ** 2
                                                for p in todo[i][::4]))
                chosen = None
                for i in near:
                    r = todo[i]
                    order = sorted(range(len(r)), key=lambda q: (r[q][0] - here[0]) ** 2
                                                              + (r[q][1] - here[1]) ** 2)
                    for q in order[:80]:
                        if clean(here, r[q]):
                            chosen = (i, q, None)
                            break
                    if chosen:
                        break
                if chosen is None:
                    wps = sorted(WPS, key=lambda p: (p[0] - here[0]) ** 2
                                                  + (p[1] - here[1]) ** 2)[:400]
                    for wp in wps:
                        if not clean(here, wp):
                            continue
                        for i in near[:4]:
                            r = todo[i]
                            ent = sorted(range(len(r)), key=lambda q: (r[q][0] - wp[0]) ** 2
                                                                    + (r[q][1] - wp[1]) ** 2)
                            for q in ent[:40]:
                                if clean(wp, r[q]):
                                    chosen = (i, q, wp)
                                    break
                            if chosen:
                                break
                        if chosen:
                            break
                if chosen is None:
                    r = todo[near[0]]
                    if LineString(r + [r[0]]).distance(holes) < 0.75 * bw:
                        raise SystemExit("link routing: a WINDOW WALL is unreachable without "
                                         "crossing a window — respace the cast")
                    todo.pop(near[0])
                    n_drop += 1
                    continue
                i, q, via = chosen
                r = todo.pop(i)
                loop = r[q:] + r[:q] + [r[q]]
                out.append((via, loop))
                here = loop[-1]
            return out

        n_link = 0
        for k in range(a.wall_layers):
            z = machine.PRESS_HARD + k * lh
            here = (pos[0], pos[1]) if pos[0] is not None else (72.0, 32.0)  # prime break-off
            for i, (via, loop) in enumerate(order_loops(here)):
                loop = sheet_decimate(sheet_densify(loop, 0.8), 0.3)
                first = (k == 0 and i == 0)
                if not first:
                    if pos[2] < z - 1e-9:
                        w(f"G1 F1800 Z{z:.3f}")
                        pos[2] = z
                    for tgt in ([via] if via else []) + [loop[0]]:
                        d0 = math.hypot(tgt[0] - pos[0], tgt[1] - pos[1])
                        if d0 <= 0.4:
                            continue
                        if not clean((pos[0], pos[1]), tgt):
                            raise SystemExit(f"layer {k+1}: a {d0:.1f}mm link crosses a "
                                             f"window — routing failed")
                        e += d0 * e_per_mm * 0.3
                        w(f"G1 F{f} X{tgt[0]:.3f} Y{tgt[1]:.3f} Z{z:.3f} E{e:.5f} ; LINK thin")
                        pos[0], pos[1], pos[2] = tgt[0], tgt[1], z
                        n_link += 1
                stroke(loop, z, first=first)
            if k == 0:
                w("M106 S51                        ; 20% fan from layer 2")
        grams = e * A * 1.24 / 1000.0
        mins = (e / e_per_mm) / speed / 60.0
        fn = os.path.join(a.out,
                          f"petalwall_{a.printer}_s{a.segment}of{a.segments}_h{H:g}_T{temp:g}.gcode")
        summary = (f"  panel {Lb:.0f}->{Lt:.0f} x {H:g} (tab {a.tab:g}), {a.wall_layers} layers "
                   f"= {t_sheet:g}mm sheet (bend strain {t_sheet / (a.dia + t_sheet) * 100:.2f}% "
                   f"at r{(a.dia + t_sheet) / 2:.0f}), {len(cutouts)} windows "
                   f"({holes.area / trap.area * 100:.0f}% open), fill {fill:.2f}, "
                   f"{n_link} links, {n_drop // a.wall_layers} slivers dropped/layer; "
                   f"~{grams:.0f} g, ~{mins:.0f} min")

    # KEEP THE BED AT TARGET after the part — Oleg: "keep printer bed 120 so you dont need
    # to wait when you start". Multi-part builds (floor + 3 panels) chain with zero re-heat;
    # the bed only goes cold when he turns it off.
    w("M107"); w("M104 S0")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}   ; bed STAYS hot between parts (Oleg)")
    w("G0 Z40 F900")
    w(f"G0 X{min(10.0, bx-10):.0f} Y{by-10:.0f} F9000")
    os.makedirs(a.out, exist_ok=True)
    open(fn, "w").write("\n".join(L) + "\n")
    print(summary)
    print(fn)


if __name__ == "__main__":
    main()
