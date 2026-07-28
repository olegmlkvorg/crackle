#!/usr/bin/env python3
"""PETALWALL — the bucket as two prints: a floor with a wall stub, and flat lightweight
wall panels that wrap around it with temperature bending.

Oleg, 2026-07-28 ~03:30, redirecting from the rotunda: "i dont think we can rely on this. i am
more thinking now we print separately the floor with a bit of wall + we then print flat wall
which we will wrap around the floor with temperature bending. i want the wall to be
lightweight, it dors not carry much load anyway. so it is some kind of rosetish pattern
trapezoid foltable into roundish wall of the buckt."

Physics on our side for once: wrapping flat->cylinder is SINGLE curvature — the one thing a
flat sheet does perfectly (the cuff and the wave flower are the proven precedents; the failed
mask problem was double curvature, which this is not).

--part floor   the proven rosette floor (crossing lifts, rim band, layer-1 brim) plus a STUB:
               a short vase wall on the envelope, the register + weld target for the wrap.

--part wall    ONE flat trapezoid panel, 2 layers thick (pressed + one), lying on the plate:
                 * bottom + top rails and end rails: solid 3-bead bands — the top rail is the
                   bucket rim, the bottom welds to the stub, the ends are OVERLAP TABS (each
                   panel is perimeter/segments + tab wide) that weld onto the next panel
                 * interior: TWO INTERLEAVED BANKS OF PETAL LENSES — each bank a mirrored
                   strand pair y = mid +/- A*|sin|^m crossing into pointed fat-bellied petals
                   (the floor petals' character), the top bank staggered half a petal and both
                   banks oversized so they CROSS in a mid band; inside each petal an echo
                   loop, drawn as two tip-to-tip arcs whose chained connectors ride the node
                   knots lifted. Strand peaks half-overlap the rail rings: welds to the hoops.
               All 3 panels are identical — print the same file three times.
               The bucket is a shallow frustum, so the flat is a trapezoid: top edge longer by
               2*pi*h*tan(taper)/segments.

Numbers with provenance:
  panel thickness 2 layers = 0.7mm    CHOSEN — the wave-flower ribbons that hand-formed well
  taper 2 deg                          CHOSEN — reads as a bucket, keeps top edge on the bed
  segments 3 (d200)                    DERIVED — 630mm midplane wrap vs 334mm printable width
  tab 6mm                              CHOSEN — a 3-bead weld land; also the slack that
                                       absorbs stub-OD error (measure the stub, pass --dia)
  petals 6+5 per panel, overlap 0.2,   CHOSEN — by render iteration; 5+8 moire and aligned
  nest 0.55, profile |sin|^0.6         columns both tried and rejected as non-rosette
  forming window                       UNMEASURED — the standing gap; bed-warm forming (120C
                                       plate holds the sheet above Tg) is the fallback route
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import LineString
import machine
from bucket import rose, crossing_z, ring_of


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", choices=("floor", "wall"), required=True)
    ap.add_argument("--dia", type=float, default=200.0)
    ap.add_argument("--height", type=float, default=200.0, help="wall panel height")
    ap.add_argument("--stub", type=float, default=8.0, help="floor: stub wall height")
    ap.add_argument("--floor-layers", type=int, default=5)
    ap.add_argument("--close", type=float, default=12.0)
    ap.add_argument("--segments", type=int, default=2)
    ap.add_argument("--segment", type=int, default=1, help="which wall panel (1-based)")
    ap.add_argument("--taper", type=float, default=2.0, help="bucket flare, degrees")
    ap.add_argument("--rail", type=float, default=None, help="rail width; default 3 beads")
    ap.add_argument("--tab", type=float, default=6.0,
                    help="extra panel width so end rails OVERLAP the next panel (weld land)")
    ap.add_argument("--lenses", type=int, default=6,
                    help="petal lenses per bank per panel (two banks, stacked)")
    ap.add_argument("--nest", type=float, default=0.55,
                    help="inner echo loop inside each petal, as a fraction of it; 0 = none")
    ap.add_argument("--overlap", type=float, default=0.2,
                    help="how far the two petal banks interleave, as a fraction of the "
                         "interior height; 0 = banks only touch at mid height")
    ap.add_argument("--profile-pow", type=float, default=0.6,
                    help="|sin|^m strand profile: <1 fattens the lens belly, sharpens the tips")
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

    def header(name, layers):
        w(f"; MATERIAL={a.material}")
        w(f"; LAYER_H={lh}")
        w(f"; FLOW={bw*lh*speed:.4f}")
        w(f"; PRINTER={a.printer}")
        w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
        w("; ARGV: " + " ".join(sys.argv))
        w(f"; PETALWALL {name}")
        w(f"; ARCH_LIFT={0.5 - machine.PRESS_HARD:.3f}")
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
        # ---- WALL PANEL: flat trapezoid, 2 layers, rails + two banks of petal lenses ----
        # Each bank is a mirrored strand pair crossing into a chain of pointed petals
        # (|sin|^m profile: fat belly, cusp tips — the floor petals' character). The banks
        # stack: bottom bank peaks meet top bank valleys at mid height, welding belly to
        # belly, and the outer peaks half-overlap the rail rings — so the lattice is stitched
        # to both hoops and to itself, never slats. Inside each petal floats a nested echo
        # loop. Connectors ride the end-rail rings lifted, or chain petal tips.
        R = a.dia / 2.0
        peri = math.pi * (a.dia + 0.7)              # wrap length at the 0.7 sheet's midplane;
                                                    # pass the MEASURED stub OD as --dia
        Lb = peri / a.segments + a.tab               # + tab: end rails overlap the next panel
        Lt = Lb + 2 * math.pi * a.height * math.tan(math.radians(a.taper)) / a.segments
        H = a.height
        rail = (a.rail or 3 * bw)
        rail_n = max(2, round(rail / bw))
        rail_w = rail_n * bw
        if Lt > bx - 16 or H > by - 16:
            raise SystemExit(f"panel {Lt:.0f}x{H:.0f} exceeds the {bx:.0f}x{by:.0f} bed — "
                             f"more --segments or less --height")
        ox = (bx - Lt) / 2.0
        oy = (by - H) / 2.0
        ymid = oy + H / 2.0
        nl = a.lenses
        Hin = H - 2 * rail_w
        Ai = Hin * (1 + a.overlap) / 4.0   # oversized so the two banks interleave and CROSS
        ymid_b = oy + rail_w + Ai          # bottom bank centreline
        ymid_t = oy + H - rail_w - Ai      # top bank centreline (staggered half a petal)

        header(f"wall panel {a.segment}/{a.segments} {Lb:.0f}->{Lt:.0f} x {H:g}", 2)

        from shapely.geometry import Polygon
        BL = (ox + (Lt - Lb) / 2.0, oy)
        BR = (ox + (Lt + Lb) / 2.0, oy)
        TR = (ox + Lt, oy + H)
        TL = (ox, oy + H)
        trap = Polygon([BL, BR, TR, TL])

        def trap_ring(inset):
            g = trap.buffer(-inset, join_style=2)
            return ring_of(g.exterior, seg)

        def span_at(y):              # pattern x-range at height y, following the slanted sides
            sl = (Lt - Lb) / 2.0 * (1 - (y - oy) / H)
            return ox + sl + rail_w, ox + Lt - sl - rail_w

        def prof(u):                 # signed |sin|^m: fat petal belly, pointed tip
            s = math.sin(u)
            return math.copysign(abs(s) ** a.profile_pow, s)

        def bank_strand(rmid, sgn, phase, rtl=False, points=12000):
            """One strand of a bank: y = rmid + sgn*Ai*prof across the span. Its mirror
            crosses it at the nodes, closing the petals. The banks are oversized and the
            top one is phased half a petal, so their strands CROSS in the interleave band —
            the stitch that keeps the wall one net instead of two slats."""
            pts = []
            for i in range(points + 1):
                t = i / points
                y = rmid + sgn * Ai * prof(math.pi * nl * t + phase)
                x0, x1 = span_at(y)
                pts.append((x0 + t * (x1 - x0), y))
            if rtl:
                pts.reverse()
            return machine.decimate(pts, 0.25)

        def petal_centers(phase):
            k0 = phase / math.pi
            ts = [(k - k0) / nl for k in range(2 * nl + 2)]
            ts = [t for t in ts if -1e-9 <= t <= 1 + 1e-9]     # node positions
            return [(ts[i] + ts[i + 1]) / 2 for i in range(len(ts) - 1)]

        def petal_arc(rmid, tc, side, rtl=False, points=140):
            """Half the inner echo of one petal — the lens outline scaled by --nest, one
            side only. Drawn tip to tip so the chain connectors hop BETWEEN petals instead
            of slicing through them; the other side comes on the return pass."""
            pts = []
            for i in range(points + 1):
                f = i / points
                t = tc + (f - 0.5) * a.nest / nl
                y = rmid + side * a.nest * Ai * abs(math.sin(math.pi * f)) ** a.profile_pow
                x0, x1 = span_at(y)
                pts.append((x0 + t * (x1 - x0), y))
            if rtl:
                pts.reverse()
            return machine.decimate(pts, 0.25)

        def ride(p1):
            """Connector from the current position, sampled so crossing_z can lift it: it
            runs along the end-rail ring, and an unlifted straight G1 would plough it."""
            p0 = (pos[0], pos[1])
            n = max(2, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1])))
            return [(p0[0] + (p1[0] - p0[0]) * i / n, p0[1] + (p1[1] - p0[1]) * i / n)
                    for i in range(n + 1)]

        for kz in range(2):
            z = machine.PRESS_HARD + kz * lh
            first = (kz == 0)
            prior = []
            for j in range(rail_n):                 # frame loops, outer->inner
                ring = trap_ring(j * bw + bw / 2.0)
                i0 = min(range(len(ring)),
                         key=lambda k: (ring[k][0] - span_at(ymid)[0]) ** 2
                                     + (ring[k][1] - ymid) ** 2)
                ring = ring[i0:] + ring[:i0] + [ring[i0]]
                stroke(ring, z, first=first and j == 0)
                prior.extend(ring)

            def lay(pts):
                # bridge any real gap as a sampled stroke so crossing_z can lift it over
                # whatever it crosses — stroke()'s own gap-close is a single straight G1 at
                # base Z, which ploughs through the node knots (seen on the corner zoom)
                if pos[0] is not None:
                    d = math.hypot(pts[0][0] - pos[0], pts[0][1] - pos[1])
                    if d > 3.0:
                        br = ride(pts[0])
                        bz, _ = crossing_z(br, bw, machine.PRESS_HARD, 0.5, prior=prior)
                        stroke(br, z, zs=bz)
                        prior.extend(br)
                cz, _ = crossing_z(pts, bw, machine.PRESS_HARD, 0.5, prior=prior)
                stroke(pts, z, zs=cz)
                prior.extend(pts)

            PH = math.pi / 2.0                                  # top bank: half-petal stagger
            lay(ride((span_at(ymid_b)[0], ymid_b)))             # down the left rail, lifted
            lay(bank_strand(ymid_b, +1, 0.0))                   # bottom bank      L->R
            lay(bank_strand(ymid_b, -1, 0.0, rtl=True))         #                  R->L
            cbs = petal_centers(0.0)
            cts = petal_centers(PH)
            if a.nest > 0:                                      # echoes: tips chained, two passes
                for tc in cbs:
                    lay(petal_arc(ymid_b, tc, +1))
                for tc in reversed(cbs):
                    lay(petal_arc(ymid_b, tc, -1, rtl=True))
            lay(ride((span_at(ymid_b)[0], ymid_b)))             # back onto the left rail
            lay(ride((span_at(ymid_t - Ai)[0], ymid_t - Ai)))   # up to the top bank, lifted
            lay(bank_strand(ymid_t, -1, PH))                    # top bank         L->R
            lay(ride((span_at(ymid_t + Ai)[1], ymid_t + Ai)))   # up the right rail, lifted
            lay(bank_strand(ymid_t, +1, PH, rtl=True))          #                  R->L
            lay(ride((span_at(ymid_t)[0], ymid_t)))             # down to tip height, lifted
            if a.nest > 0:
                for tc in cts:
                    lay(petal_arc(ymid_t, tc, +1))
                for tc in reversed(cts):
                    lay(petal_arc(ymid_t, tc, -1, rtl=True))
            if kz == 0:
                # park where the next layer's ring begins — otherwise its gap-close is a
                # bare chord across the top-left petal
                lay(ride((span_at(ymid_t)[0], ymid_t)))
                lay(ride((span_at(ymid)[0], ymid)))
                w("M106 S51                        ; 20% fan from layer 2")
        grams = e * A * 1.24 / 1000.0
        mins = (e / e_per_mm) / speed / 60.0
        fn = os.path.join(a.out,
                          f"petalwall_{a.printer}_s{a.segment}of{a.segments}_h{H:g}_T{temp:g}.gcode")
        summary = (f"  panel {Lb:.0f}->{Lt:.0f} x {H:g} (tab {a.tab:g}), {rail_n}-bead rails, "
                   f"banks {nl}+{nl-1} petals interleaved (amp {Ai:.0f}, nest {a.nest:g}), "
                   f"2 layers; ~{grams:.1f} g, ~{mins:.0f} min")

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
