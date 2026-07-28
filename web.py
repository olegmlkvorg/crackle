#!/usr/bin/env python3
"""WEB BUCKET — the client's v3 architecture, verbatim (2026-07-28): "it has to be a web.
plus the base and the web need to have side connectors for 1/8 inch bambo sticks to hold
the structure. so you go base. 2x walls, topper coil"

Four parts, one skeleton: 12 vertical bamboo sticks (1/8" = 3.175mm) stand in sockets on
the proven rosette floor, two flat-printed WEB panels wrap around and SNAP onto the sticks,
and a printed coil ring caps the drum and swallows the stick tops.

  --part coupon   THE FIT GATE (k1c). Six socket/clip variants for a 3.175 stick, indexed
                  by edge notches (1 notch = V1 ... 6 = V6). Every fit number in the other
                  three parts keys off which variant Oleg reports snug. Print this FIRST.
  --part base     rosette floor (petalwall machinery, unchanged) + 12 socket bosses merged
                  into the 2-bead stub band. Sockets are blind — the floor is their bottom.
  --part web      one wall panel (print two, --segment 1/2 varies the net organically).
                  2 layers of web + snap-clip channels at every stick line it owns.
  --part topper   the coil: printed show-face-down; 3 cap layers laid as ONE continuous
                  multi-lap spiral, then socket bosses. Flipped at assembly, the sockets
                  open downward onto the stick tops and the boss ring seats on the panels.

Numbers with provenance:
  STICK_D 3.175            MEASURED — 1/8" bamboo stock
  BORE_MOD 9.9             DERIVED, UNMEASURED AT THIS SIZE — 3.175 + STICK_FIT 0.70
                           (measured on 6.35 bamboo) + 2 x BORE_INSET 3.02 (measured on
                           ~6.35+ vertical bores; solid.py: below ~6mm modelled no hole
                           survives). A 3.175 stick is DEEP in unmeasured territory,
                           which is exactly what the coupon exists to measure.
  N_STICKS 12              CHOSEN — 47mm stick pitch: web cells read open, bosses fit
  R_STICK 90.5             CHOSEN — boss ring (bore+4 beads) stays inside the d200 floor
  CLIP_CAVITY 4.3          CHOSEN -> coupon V5/V6 — stick + 1.1 room for the hot bulge
  CLIP_MOUTH 2.9           CHOSEN -> coupon V5 (V6 tries 2.5) — stick - 0.28 snap
  wall bead 2.0 x 0.6      DERIVED — flow_cap(pla-matte,k2plus)=60 at the 50 north star
  coupon bead 1.5 x 0.6    DERIVED — flow_cap(pla-matte,k1c)=45 at the 50 north star
  layer-1 ribbon ~12mm     DERIVED — full flow pressed to 0.1 spreads bw*lh/0.1; the web
                           ground layer is drawn AT this width: cells must clear it
  panel H 177.6            DERIVED — 200 total - base band 13.9 - topper 8.5
  stick cut 195mm          DERIVED — base floor z2.5 to topper bore ceiling z198.7, minus
                           1.2 float so the topper seats on the panel rim, not the sticks

Honest unknowns (the coupon closes the first two; the rest only a print can):
  * bore inset below 6mm modelled hole — extrapolated, never measured
  * channel-mouth bulge on 1-bead rails — same unknown, open geometry
  * coupon prints on the K1C (bead 1.5) but base/topper/panels print on the K2 (bead 2.0);
    the inset is measured ABSOLUTE (2.98 vs 3.06 across beads 1.5/2.17), so it should
    transfer — "should" is the word
  * L2 net strands bridge up to ~36mm between pressed ribbons at z0.7 — they will sag and
    kiss the 120C plate; expected to release on cooldown, UNTESTED
  * clip grip per 12mm channel — 3 channels per stick; if loose, the fix is more/longer
    channels, parametric below
"""
import argparse, math, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
import machine
from bucket import rose, crossing_z, ring_of
from solid import circle, contours, densify, decimate as loop_decimate, start_nearest

STICK_D = 3.175          # MEASURED: 1/8 inch bamboo stock
N_STICKS = 12            # CHOSEN
R_STICK = 90.5           # CHOSEN: stick-circle radius on the d200 floor
FLOOR_LAYERS = 5         # the printed, approved rosette floor
BAND_LAYERS = 19         # base socket band: 19 x 0.6 = 11.4mm of stick grip
CAP_LAYERS = 3           # topper cap sheet (1.3mm), the show face
TOP_SOCKET_LAYERS = 12   # topper sockets: 7.2mm deep
WALL_LAYERS = 2          # the web sheet: pressed ground + net
CLIP_LAYERS = 8          # snap channels rise layers 3..10 (4.8mm)
EDGE_L, EDGE_R = 10.0, 5.0   # panel margins past its first / before its last stick line
BAND_Y_FRAC = (0.085, 0.5, 0.915)   # clip bands: near bottom, middle, near top


def sheet_t():
    return machine.PRESS_HARD + (WALL_LAYERS - 1) * 0.6


def wrap_radius():
    """Panel mid-plane radius: panels lie on the stick faces."""
    return R_STICK + STICK_D / 2.0 + sheet_t() / 2.0


def stick_pitch():
    return 2 * math.pi * wrap_radius() / N_STICKS


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", choices=("coupon", "base", "web", "topper"), required=True)
    ap.add_argument("--dia", type=float, default=200.0, help="floor diameter (pinned)")
    ap.add_argument("--height", type=float, default=200.0, help="assembled bucket height")
    ap.add_argument("--bore-mod", type=float, default=9.9,
                    help="MODELLED socket bore diameter — set from the winning coupon "
                         "variant: V1=9.0 V2=9.9 V3=10.8 (interpolate between two)")
    ap.add_argument("--socket", choices=("round", "lobed"), default="round",
                    help="lobed if coupon V4 wins: clearance bore + 3 contact bumps")
    ap.add_argument("--lobe-inscribed", type=float, default=5.6,
                    help="lobed socket: modelled circle the 3 bumps inscribe (coupon V4)")
    ap.add_argument("--span", action="store_true",
                    help="coupon: six round bores 3.9-9.9 (zero-inset..full-inset), no clips")
    ap.add_argument("--clip-cavity", type=float, default=4.3,
                    help="snap channel width at the stick (coupon V5/V6 test this bulged)")
    ap.add_argument("--clip-mouth", type=float, default=2.9,
                    help="snap channel opening: V5=2.9, V6=2.5 — pick what held")
    ap.add_argument("--segment", type=int, default=1, help="web panel 1 or 2 (net varies)")
    ap.add_argument("--printer", default=None, choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.printer = a.printer or ("k1c" if a.part == "coupon" else machine.DEFAULT_PRINTER)
    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    flow = machine.flow_cap(a.material, a.printer)
    lh = a.layer_h
    bw = machine.bead_for_flow(flow, lh)
    speed = machine.speed_for_flow(flow, bw, lh)
    temp = machine.temp_for(a.material)
    bx, by = machine.BED[a.printer]
    A = math.pi * (1.75 / 2) ** 2
    e_per_mm = bw * lh / A
    f = round(speed * 60)
    seg = max(0.25, speed / 250.0)

    L = []
    w = L.append

    def header(name, layers, arch):
        w(f"; MATERIAL={a.material}")
        w(f"; LAYER_H={lh}")
        w(f"; FLOW={bw*lh*speed:.4f}")
        w(f"; PRINTER={a.printer}")
        w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
        w("; ARGV: " + " ".join(sys.argv))
        w(f"; WEB {name}")
        if arch:
            w(f"; ARCH_LIFT={0.5 - machine.PRESS_HARD:.3f}")
        w("; HEADER_BLOCK_START"); w(f"; total layer number: {layers}"); w("; HEADER_BLOCK_END")
        w("M82")
        w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
        w(f"M104 S{temp}")
        w("G28")
        # the footprint rule inherited from the floor that stuck: the K2 waits for the FULL
        # held 120 (petalfloor peeled when it started on a climbing plate); the K1C cannot
        # hold its target, so it waits to bed_start (5 under) like every k1c part
        _bed = machine.bed_for(a.material, a.printer)
        _wait = _bed if a.printer == "k2plus" else machine.bed_start(a.material, _bed)
        w(f"M190 S{_wait:.0f}")
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

    def stroke(pts, z, first=False, zs=None, meter=1.0):
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
                e += math.hypot(d0, z0 - pos[2]) * e_per_mm * meter
                tag = " ; LINK thin" if meter < 1.0 else ""
                w(f"G1 F{f} X{pts[0][0]:.3f} Y{pts[0][1]:.3f} Z{z0:.3f} E{e:.5f}{tag}")
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

    def hop(x, y, z, clear):
        """Between disjoint standing features only (lapweld precedent): lifted clear of
        everything standing, flow suspended, no retract, tagged."""
        w(f"G0 Z{clear:.3f} F900 ; HOP up")
        w(f"G0 X{x:.3f} Y{y:.3f} F9000 ; HOP over standing clips")
        w(f"G0 Z{z:.3f} F900 ; HOP down")
        pos[0], pos[1], pos[2] = x, y, z

    def link_to(p, z):
        """Thin metered connector to the next ring."""
        if pos[0] is None:
            return
        d0 = math.hypot(p[0] - pos[0], p[1] - pos[1])
        if d0 <= 0.4:
            return
        nonlocal e
        e += d0 * e_per_mm * 0.3
        w(f"G1 F{f} X{p[0]:.3f} Y{p[1]:.3f} Z{z:.3f} E{e:.5f} ; LINK thin")
        pos[0], pos[1], pos[2] = p[0], p[1], z

    def emit_region_layer(region, z, first=False, holes=None):
        """One layer of a solid region as concentric contours, nearest-first, entered
        wherever the thin link stays out of the bores (a link across a void would draw a
        thread across the very hole the part exists to keep open)."""
        from shapely.prepared import prep
        _ph = prep(holes) if holes is not None and not holes.is_empty else None

        def clean(p0, p1):
            if (p0[0] - p1[0]) ** 2 + (p0[1] - p1[1]) ** 2 < 0.25:
                return True
            return _ph is None or not _ph.intersects(LineString([p0, p1]))

        rings = contours(region, bw)
        todo = [r[:-1] if r[0] == r[-1] else list(r) for r in rings]
        here = (pos[0], pos[1]) if pos[0] is not None else (bx / 2 + a.dia / 2, by / 2)
        wps = []          # waypoint bank: points on rings already laid this layer
        while todo:
            order = sorted(range(len(todo)),
                           key=lambda i: min((p[0] - here[0]) ** 2 + (p[1] - here[1]) ** 2
                                             for p in todo[i][::8]))
            chosen = None
            for i in order:
                r = todo[i]
                ents = sorted(range(len(r)), key=lambda q: (r[q][0] - here[0]) ** 2
                                                         + (r[q][1] - here[1]) ** 2)
                for q in ents[:120]:
                    if first or clean(here, r[q]):
                        chosen = (i, q, None)
                        break
                if chosen:
                    break
            if chosen is None:
                # a walled-in transition: route via a point on material already laid
                for wp in sorted(wps, key=lambda p: (p[0] - here[0]) ** 2
                                                  + (p[1] - here[1]) ** 2)[:400]:
                    if not clean(here, wp):
                        continue
                    for i in order[:4]:
                        r = todo[i]
                        ents = sorted(range(len(r)), key=lambda q: (r[q][0] - wp[0]) ** 2
                                                                 + (r[q][1] - wp[1]) ** 2)
                        for q in ents[:60]:
                            if clean(wp, r[q]):
                                chosen = (i, q, wp)
                                break
                        if chosen:
                            break
                    if chosen:
                        break
            if chosen is None:
                raise SystemExit(f"z{z:g}: no bore-clean entry to any remaining ring")
            i, q, via = chosen
            r = todo.pop(i)
            loop = r[q:] + r[:q] + [r[q]]
            loop = loop_decimate(densify(loop, 0.8), 0.3)
            if pos[2] is not None and pos[2] < z - 1e-9:
                w(f"G1 F1800 Z{z:.3f}")
                pos[2] = z
            if not first:
                if via is not None:
                    link_to(via, z)
                link_to(loop[0], z)
            stroke(loop, z, first=first)
            first = False
            wps += loop[::20]
            here = (pos[0], pos[1])

    def sockets_at(centers, bore_mod):
        """The void to subtract per socket. Round is the default; lobed is coupon V4's
        geometry: a generous clearance bore with 3 bumps standing back in — the bulge
        grows into the relief between bumps instead of seizing a whole circumference."""
        holes = []
        for cx_, cy_ in centers:
            if a.socket == "round":
                h = circle(bore_mod / 2.0, seg=0.4)
            else:
                r_ins = a.lobe_inscribed / 2.0
                h = circle(bore_mod / 2.0, seg=0.4)
                for k in range(3):
                    ang = 2 * math.pi * k / 3
                    d = r_ins + 1.6
                    b = Point(d * math.cos(ang), d * math.sin(ang)).buffer(1.6, 8)
                    h = h.difference(b)
                h = h.simplify(0.04, preserve_topology=True)
            from shapely import affinity
            holes.append(affinity.translate(h, cx_, cy_))
        return holes

    # ------------------------------------------------------------------ COUPON (k1c)
    if a.part == "coupon":
        # Six fit variants for the 3.175 stick, one plate. Read it by the notches on the
        # front edge: 1 notch = V1 ... 6 = V6. Oleg pushes a stick into each and reports.
        #   V1 bore 9.0   V2 bore 9.9   V3 bore 10.8      (round, push straight down)
        #   V4 lobed: clearance 10.8, 3 bumps inscribing 5.6
        #   V5 channel mouth 2.9   V6 channel mouth 2.5   (lay stick in, press down)
        PL, PH = 130.0, 20.0
        ox, oy = (bx - PL) / 2.0, (by - PH) / 2.0
        # ROUND 2 (Oleg's photo: K1C coupon bores printed ~3x the stick — the 3.02 inset
        # measured on big hot K2 parts did NOT appear on a small K1C coupon; a fit constant
        # does not cross printers/beads/part sizes). --span widens the sweep to SIX round
        # bores from zero-inset snug to full-inset prediction, to be printed ON THE K2.
        bores = ([(16.0, 9.0), (36.0, 9.9), (56.0, 10.8)] if not a.span else
                 [(14.0, 3.9), (34.0, 5.1), (54.0, 6.3), (74.0, 7.5), (94.0, 8.7), (114.0, 9.9)])
        LOBE_X = None if a.span else 76.0
        CH = [] if a.span else [(96.0, 2.9), (118.0, 2.5)]     # (centre x, mouth)
        CAV = a.clip_cavity
        yc = PH / 2.0

        def plate_region():
            r = box(ox, oy, ox + PL, oy + PH)
            n = 0
            sites = ([(16, 1), (36, 2), (56, 3), (76, 4), (96, 5), (118, 6)] if not a.span
                     else [(14, 1), (34, 2), (54, 3), (74, 4), (94, 5), (114, 6)])
            for site_x, count in sites:
                for k in range(count):
                    nx = ox + site_x + (k - (count - 1) / 2.0) * 3.2
                    r = r.difference(Point(nx, oy).buffer(1.2, 8))
                n += 1
            return r

        def upper_region(mouth_shift):
            """Bosses + lobed boss + channel rails + the ridge that keeps it ONE stroke.
            mouth_shift moves the rail faces toward the channel on the top two layers."""
            parts, holes = [], []
            # every bar here is TWO beads wide: a 1-bead-wide region collapses to nothing
            # under contours' half-bead erosion — the rails would silently vanish (same
            # species as the sub-6mm hole loss). 2 beads = the erosion leaves exactly the
            # two face passes.
            ridge_y0 = oy + PH - 0.8 - 2 * bw
            parts.append(box(ox + 6, ridge_y0, ox + PL - 4, oy + PH - 0.8))
            for sx, bm in bores:
                parts.append(circle((bm + 4 * bw) / 2.0, seg=0.4).buffer(0))
                from shapely import affinity
                parts[-1] = affinity.translate(parts[-1], ox + sx, oy + yc)
                holes.append(Point(ox + sx, oy + yc).buffer(bm / 2.0, 24))
            # V4 lobed (skipped in --span mode: round-bore sweep only)
            from shapely import affinity
            if LOBE_X is None:
                reg = unary_union(parts)
                for h in holes:
                    reg = reg.difference(h)
                if reg.geom_type != "Polygon":
                    raise SystemExit("span coupon region is not one connected piece")
                return reg, unary_union(holes)
            # +1.2 pad: the bump bites thin the wall to ~1.6 beads; padding restores a
            # full 2-bead wall at the bumps (an under-filled strip elsewhere is the safe
            # direction, a doubled bead is not)
            boss = affinity.translate(circle((10.8 + 4 * bw + 1.2) / 2.0, seg=0.4), ox + LOBE_X, oy + yc)
            lob = circle(10.8 / 2.0, seg=0.3)
            for k in range(3):
                ang = 2 * math.pi * k / 3 + math.pi / 2
                d = a.lobe_inscribed / 2.0 + 1.6
                lob = lob.difference(Point(d * math.cos(ang), d * math.sin(ang)).buffer(1.6, 8))
            lob = lob.simplify(0.04, preserve_topology=True)
            holes.append(affinity.translate(lob, ox + LOBE_X, oy + yc))
            parts.append(boss)
            # V5/V6 snap channels: two 1-bead rails flanking the stick corridor, joined to
            # the ridge by a closed end so every layer stays one connected region
            for chx, mouth in CH:
                x0, x1 = ox + chx - 8, ox + chx + 8
                shift = mouth_shift * (CAV - mouth) / 2.0
                yin = oy + yc - CAV / 2.0 + shift      # inner rail face
                yout = oy + yc + CAV / 2.0 - shift     # outer rail face
                parts.append(box(x0 + 2 * bw, yin - 2 * bw, x1, yin))       # front rail
                parts.append(box(x0 + 2 * bw, yout, x1, yout + 2 * bw))     # back rail
                parts.append(box(x0, oy + yc - CAV / 2.0 - 2 * bw, x0 + 2 * bw, oy + PH - 0.8))
            reg = unary_union(parts)
            for h in holes:
                reg = reg.difference(h)
            if reg.geom_type != "Polygon":
                raise SystemExit("coupon upper region is not one connected piece")
            return reg, unary_union(holes)

        n_layers = 2 + CLIP_LAYERS
        header("fit coupon V1-V6 for 3.175 stick", n_layers, arch=False)
        w("M107                              ; layer 1 bonds uncooled")
        plate = plate_region()
        for k in range(2):
            z = machine.PRESS_HARD + k * lh
            emit_region_layer(plate, z, first=(k == 0))
            if k == 0:
                w("M106 S51                        ; 20% fan from layer 2")
        reg_body, holes_body = upper_region(0.0)
        reg_m1, _ = upper_region(0.5)
        reg_m2, _ = upper_region(1.0)
        for k in range(CLIP_LAYERS):
            z = machine.PRESS_HARD + (2 + k) * lh
            reg = reg_body if k < CLIP_LAYERS - 2 else (reg_m1 if k == CLIP_LAYERS - 2 else reg_m2)
            # layer 3 sits on the solid plate — a link over a bore mouth there lands on
            # ground; from layer 4 up the void below is real and links must stay clear
            emit_region_layer(reg, z, holes=None if k == 0 else holes_body.buffer(-0.4))
        grams = e * A * 1.24 / 1000.0
        mins = (e / e_per_mm) / speed / 60.0
        if grams > 14.0 or mins > 8.0:
            # cap raised 10->14g for --span: six bores at the K2's 2.0 bead legitimately
            # weigh more than three at the K1C's 1.5 (the budget is a scope guard, not physics)
            raise SystemExit(f"coupon budget blown: {grams:.1f}g / {mins:.1f}min "
                             f"(caps 14g / 8min) — shrink it")
        fn = os.path.join(a.out, f"web_coupon_{a.printer}_T{temp:g}.gcode")
        summary = (f"  coupon: V1-3 bores 9.0/9.9/10.8, V4 lobed 10.8/{a.lobe_inscribed:g}, "
                   f"V5-6 channels cav {CAV:g} mouth 2.9/2.5; ~{grams:.1f} g, ~{mins:.1f} min")

    # ------------------------------------------------------------------ BASE (k2plus)
    elif a.part == "base":
        cx, cy = bx / 2.0, by / 2.0
        R = a.dia / 2.0
        rim_passes = max(2, round(3 * bw / bw))
        rose_pts = rose(cx, cy, R - bw / 2, (R - bw / 2) * 0.11)
        rose_pts = machine.decimate(rose_pts, machine.CONSTANT_SPEED / 300.0 * 1.2)
        rose_region = LineString(rose_pts).buffer(bw / 2.0, resolution=8)
        env = rose_region.buffer(12.0, resolution=64).buffer(-12.0, resolution=64)
        if env.geom_type == 'MultiPolygon':
            env = max(env.geoms, key=lambda g: g.area)
        rim_rings = []
        for j in range(rim_passes):
            rp = env.buffer(-(bw / 2.0 + j * bw))
            if rp.geom_type == 'MultiPolygon':
                rp = max(rp.geoms, key=lambda g: g.area)
            rim_rings.append(ring_of(rp.exterior, seg))
        centers = [(cx + R_STICK * math.cos(2 * math.pi * k / N_STICKS),
                    cy + R_STICK * math.sin(2 * math.pi * k / N_STICKS))
                   for k in range(N_STICKS)]
        boss_r = (a.bore_mod + 4 * bw + (1.2 if a.socket == "lobed" else 0)) / 2.0
        from shapely import affinity
        boss_discs = [affinity.translate(circle(boss_r, seg=0.4), px, py)
                      for px, py in centers]
        boss_rings = [contours(d, bw) for d in boss_discs]
        # socket band: the two stub rings the panels register on, with the bosses merged in
        band = env.difference(env.buffer(-2 * bw))
        band_reg = unary_union([band] + boss_discs)
        holes = unary_union(sockets_at(centers, a.bore_mod))
        band_reg = band_reg.difference(holes)
        if band_reg.geom_type != "Polygon":
            raise SystemExit("base socket band is not one connected region")

        n_layers = FLOOR_LAYERS + BAND_LAYERS
        header(f"base d{a.dia:g} + {N_STICKS} sockets bore {a.bore_mod:g}", n_layers, arch=True)
        w("M107                              ; layer 1 bonds uncooled")
        for k in range(FLOOR_LAYERS):
            z = machine.PRESS_HARD + k * lh
            j = min(range(len(rose_pts) - 1),
                    key=lambda i: (rose_pts[i][0] - (pos[0] or cx + R)) ** 2
                                + (rose_pts[i][1] - (pos[1] or cy)) ** 2)
            rpts = rose_pts[j:-1] + rose_pts[:j] + [rose_pts[j]]
            rz, _ = crossing_z(rpts, bw, machine.PRESS_HARD, 0.5)
            stroke(rpts, z, first=(k == 0), zs=rz)
            prior = list(rpts)
            for ring in rim_rings:
                cpts = start_nearest(ring + [ring[0]], (pos[0], pos[1]))
                cz, _ = crossing_z(cpts, bw, machine.PRESS_HARD, 0.5, prior=prior)
                stroke(cpts, z, zs=cz)
                prior += cpts
            # socket bosses, walked around the stick circle; the chords between them lie
            # over the rose lace and ride its strands exactly as the rim rings do
            order = sorted(range(N_STICKS),
                           key=lambda i: (centers[i][0] - pos[0]) ** 2 + (centers[i][1] - pos[1]) ** 2)
            first_b = order[0]
            seq = [(first_b + s) % N_STICKS for s in range(N_STICKS)]
            for bi in seq:
                entry = min(boss_rings[bi][0], key=lambda p: (p[0] - pos[0]) ** 2 + (p[1] - pos[1]) ** 2)
                chord = densify([(pos[0], pos[1]), entry], 0.8)
                czs, _ = crossing_z(chord, bw, machine.PRESS_HARD, 0.5, prior=prior, skip=4)
                stroke(chord, z, zs=czs)
                prior += chord
                for ring in boss_rings[bi]:
                    cpts = start_nearest(ring, (pos[0], pos[1]))
                    cpts = loop_decimate(densify(cpts, 0.8), 0.3)
                    czs, _ = crossing_z(cpts, bw, machine.PRESS_HARD, 0.5, prior=prior)
                    stroke(cpts, z, zs=czs)
                    prior += cpts
            if k == 0:
                w("M106 S51                        ; 20% fan from layer 2")
        z_ft = machine.PRESS_HARD + (FLOOR_LAYERS - 1) * lh
        for s_ in range(BAND_LAYERS):
            # band layer 1 lies on the solid boss tops; the bores only become voids above it
            emit_region_layer(band_reg, z_ft + (s_ + 1) * lh,
                              holes=None if s_ == 0 else holes.buffer(-0.4))
        grams = e * A * 1.24 / 1000.0
        mins = (e / e_per_mm) / speed / 60.0
        fn = os.path.join(a.out, f"web_base_{a.printer}_d{a.dia:g}_T{temp:g}.gcode")
        summary = (f"  base: rosette floor {FLOOR_LAYERS} layers + {BAND_LAYERS}-layer socket band "
                   f"({BAND_LAYERS * lh:.1f}mm grip, {N_STICKS} sockets bore {a.bore_mod:g} "
                   f"{a.socket}); ~{grams:.0f} g, ~{mins:.0f} min")

    # ------------------------------------------------------------------ WEB PANEL (k2plus)
    elif a.part == "web":
        pitch = stick_pitch()
        W = EDGE_L + 6 * pitch - EDGE_R
        band_top = machine.PRESS_HARD + (FLOOR_LAYERS + BAND_LAYERS - 1) * lh   # 13.9
        topper_t = machine.PRESS_HARD + (CAP_LAYERS + TOP_SOCKET_LAYERS - 1) * lh
        H = a.height - band_top - topper_t
        if W > bx - 16 or H > by - 16:
            raise SystemExit(f"panel {W:.0f}x{H:.0f} exceeds the {bx:.0f}x{by:.0f} bed")
        ox, oy = (bx - W) / 2.0, (by - H) / 2.0
        lines = [EDGE_L + i * pitch for i in range(7)]        # line 6 is OFF this panel
        bands = [oy + fr * H for fr in BAND_Y_FRAC]
        rng = random.Random(20260728 + a.segment)

        CAV, MOUTH = a.clip_cavity, a.clip_mouth
        off = CAV / 2.0 + bw / 2.0        # rail centreline offset from a stick line
        RL2 = 6.0                          # rail half-length within a clip band

        n_layers = WALL_LAYERS + CLIP_LAYERS
        header(f"web panel {a.segment}/2, {W:.0f}x{H:.0f}, {N_STICKS} sticks", n_layers, arch=True)
        w("M107                              ; layer 1 bonds uncooled")

        def frame_loop():
            i2 = bw / 2.0
            fr = [(ox + i2, oy + i2), (ox + W - i2, oy + i2),
                  (ox + W - i2, oy + H - i2), (ox + i2, oy + H - i2), (ox + i2, oy + i2)]
            return densify(fr, 0.8)

        # ---- layer 1, pressed: the web's GROUND — fat ribbons ~12mm landed.
        # frame + a vertical ribbon per stick line + a hoop ribbon per clip band.
        z1 = machine.PRESS_HARD
        fr = frame_loop()
        stroke(fr, z1, first=True)
        prior = list(fr)
        # hoop bands first (bottom-up, entered at the corner the frame just closed on),
        # THEN the verticals, ROUTED along the frame between strokes: an unrouted approach
        # here drew a 165mm pressed ribbon straight across the web — caught in the render,
        # not by any rule (publish-as-we-go doing its job)
        hx0, hx1 = ox + 8.0, ox + W - 8.0
        hpts = [(hx0, bands[0]), (hx1, bands[0]), (hx1, bands[1]), (hx0, bands[1]),
                (hx0, bands[2]), (hx1, bands[2])]
        hpath = densify(hpts, 0.8)
        hz, _ = crossing_z(hpath, bw, machine.PRESS_HARD, 0.5, prior=prior)
        stroke(hpath, z1, zs=hz)
        prior += hpath
        vy0, vy1 = oy + 8.0, oy + H - 8.0
        vpts = [(hx1, vy1)]
        for j, i in enumerate(range(5, -1, -1)):
            x = ox + lines[i]
            vpts += [(x, vy1), (x, vy0)] if j % 2 == 0 else [(x, vy0), (x, vy1)]
        vpath = densify(vpts, 0.8)
        vz, _ = crossing_z(vpath, bw, machine.PRESS_HARD, 0.5, prior=prior)
        stroke(vpath, z1, zs=vz)
        w("M106 S51                        ; 20% fan from layer 2")

        # ---- layer 2: frame, the clip footprint comb, then the NET.
        z2 = machine.PRESS_HARD + lh
        fr2 = frame_loop()
        stroke(start_nearest(fr2, (pos[0], pos[1])), z2)
        prior2 = list(fr2)
        rails = []          # (x_rail, sign toward stick) per band handled below
        rail_x = []
        for i in range(6):
            rail_x += [ox + lines[i] - off, ox + lines[i] + off]
        rail_x = sorted(rail_x)
        comb_all = []
        for yb in bands:
            # the comb ends in the frame MARGIN: still on the pressed 12mm frame ribbon
            # (so the jog to the next band rides ground, not open cells) but 2.5mm clear
            # of BOTH the frame bead and the net's turnarounds — any closer and crossing_z
            # reads the parallel runs as one long crossing and floats the whole jog
            cpts = [(ox + 3.5, yb - RL2)]
            for x in rail_x:
                cpts += [(x - 0.7, yb - RL2), (x - 0.7, yb + RL2),
                         (x + 0.7, yb + RL2), (x + 0.7, yb - RL2)]
            cpts += [(ox + W - 3.5, yb - RL2)]
            comb_all.append(densify(cpts, 0.8))
        for ci, cpath in enumerate(comb_all if pos[1] < by / 2 else comb_all[::-1]):
            cp = cpath if (pos[0] - cpath[0][0]) ** 2 < (pos[0] - cpath[-1][0]) ** 2 else cpath[::-1]
            czs, _ = crossing_z(cp, bw, machine.PRESS_HARD, 0.5, prior=prior2)
            stroke(cp, z2, zs=czs)
            prior2 += cp

        # THE NET: one serpentine of sine rows; adjacent rows carry opposite phase and an
        # amplitude larger than half the row pitch, so each pair CROSSES twice per cell —
        # long shallow lens overlaps, ridden via crossing_z. Junctions are lens welds and
        # ribbon-riding welds, never point kisses (the v1 failure).
        NROWS = 8
        row_pitch = (H - 52.0) / (NROWS - 1)
        AMP = 0.72 * row_pitch
        nx0, nx1 = ox + 6.0, ox + W - 6.0
        rows = [oy + 26.0 + r_ * row_pitch for r_ in range(NROWS)]
        if pos[1] > by / 2.0:            # start on the row nearest where the comb ended
            rows = rows[::-1]
        going = 1 if abs(pos[0] - nx0) < abs(pos[0] - nx1) else -1
        net = []
        for r_, yr in enumerate(rows):
            amp = AMP * rng.uniform(0.85, 1.15)
            ph = rng.uniform(-0.5, 0.5)
            sgn = 1 if r_ % 2 == 0 else -1
            xs = [nx0 + t * (nx1 - nx0) / 240 for t in range(241)]
            if going < 0:
                xs = xs[::-1]
            for x in xs:
                net.append((x, yr + sgn * amp * math.sin(2 * math.pi * (x - ox - EDGE_L) / pitch + ph)))
            going = -going
        # densify BEFORE the crossing scan: the row-to-row connectors arrive as single
        # 30mm segments, and a one-segment span turns crossing_z's 2mm ramp into a 30mm
        # shallow float (caught by measuring the emitted file, not by any guard)
        net = machine.decimate(densify(net, 0.8), 0.3)
        nzs, ncross = crossing_z(net, bw, machine.PRESS_HARD, 0.5, prior=prior2, skip=60)
        stroke(net, z2, zs=nzs)

        # ---- layers 3..10: the SIDE CONNECTORS. Snap channels at the six stick lines this
        # panel owns (the 7th is gripped by the other panel's first line). Disjoint towers,
        # so: strict layer-by-layer with lifted tagged HOPs between (lapweld precedent) —
        # the nozzle never extrudes below the file's standing layer floor, safe by
        # construction against both the plough check and the head assembly.
        pieces = []                      # each: list of (x, y) waypoints, one pass per layer
        for yb in bands:
            pieces.append([(ox + lines[0] - off, yb + RL2), (ox + lines[0] - off, yb - RL2)])
            for i in range(5):
                xr = ox + lines[i] + off
                xl = ox + lines[i + 1] - off
                pieces.append([(xr, yb + RL2), (xr, yb - RL2),
                               (xl, yb - RL2), (xl, yb + RL2)])
            pieces.append([(ox + lines[5] + off, yb + RL2), (ox + lines[5] + off, yb - RL2)])

        def mouth_shift(k):
            """Rail x-shift toward its stick on the top two clip layers — the snap lip."""
            if k == CLIP_LAYERS - 2:
                return 0.5 * (CAV - MOUTH) / 2.0
            if k == CLIP_LAYERS - 1:
                return (CAV - MOUTH) / 2.0
            return 0.0

        def shifted(piece, s):
            if s == 0.0:
                return piece
            out = []
            for (x, y) in piece:
                near = min(lines, key=lambda lx: abs(ox + lx - x))
                out.append((x + s * (1 if ox + near > x else -1), y))
            return out

        for k in range(CLIP_LAYERS):
            z = machine.PRESS_HARD + (WALL_LAYERS + k) * lh
            clear = z + 1.0
            seq = pieces if k % 2 == 0 else pieces[::-1]
            for piece in seq:
                p = shifted(piece, mouth_shift(k))
                if k % 2 == 1:
                    p = p[::-1]      # alternate direction so the wall stacks straight
                p = densify(p, 0.8)
                if math.hypot(p[0][0] - pos[0], p[0][1] - pos[1]) > 0.75:
                    hop(p[0][0], p[0][1], z, clear)
                stroke(p, z)
        grams = e * A * 1.24 / 1000.0
        mins = (e / e_per_mm) / speed / 60.0
        fn = os.path.join(a.out,
                          f"web_panel{a.segment}_{a.printer}_w{W:.0f}_h{H:.0f}_T{temp:g}.gcode")
        summary = (f"  panel {a.segment}: {W:.0f}x{H:.0f}, ground grid + {NROWS}-row net "
                   f"({ncross} path points in ride-over zones), {len(pieces)} clip pieces x{CLIP_LAYERS} layers "
                   f"(cavity {CAV:g}, mouth {MOUTH:g}); ~{grams:.0f} g, ~{mins:.0f} min")

    # ------------------------------------------------------------------ TOPPER (k2plus)
    else:
        cx, cy = bx / 2.0, by / 2.0
        r_in, r_out = R_STICK - (a.bore_mod + 4 * bw) / 2.0 - 0.5, R_STICK + (a.bore_mod + 4 * bw) / 2.0 + 1.5
        # SAME angles as the base sockets, k/N — the flip mirrors angle to -angle, and only
        # the k/N set maps onto itself in a way that still meets the base's k/N set. A
        # half-pitch offset here would land every socket 15 degrees off its stick.
        centers = [(cx + R_STICK * math.cos(2 * math.pi * k / N_STICKS),
                    cy + R_STICK * math.sin(2 * math.pi * k / N_STICKS))
                   for k in range(N_STICKS)]
        # PRINTED SHOW-FACE-DOWN: cap first (it is the top after flipping), sockets above
        # (they open downward at assembly). 12-fold symmetric, so the flip mirrors it onto
        # itself and no chirality is lost.
        n_layers = CAP_LAYERS + TOP_SOCKET_LAYERS
        header(f"topper coil r{r_in:.0f}-{r_out:.0f}, {N_STICKS} sockets", n_layers, arch=False)
        w("M107                              ; layer 1 bonds uncooled")
        for k in range(CAP_LAYERS):
            z = machine.PRESS_HARD + k * lh
            # THE COIL, literally: one unbroken Archimedean spiral per layer, pitch = one
            # bead, alternating in/out so consecutive layers chain without travel.
            lap = r_out - r_in
            n_t = int(lap / bw * 360)
            pts = []
            for t in range(n_t + 1):
                frac = t / n_t
                r = r_in + lap * (frac if k % 2 == 0 else 1 - frac)
                ang = 2 * math.pi * (lap / bw) * frac
                pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
            # close with one full ring at the resting radius so the rim is a clean circle
            r_end = r_out if k % 2 == 0 else r_in
            ang0 = 2 * math.pi * (lap / bw)
            for t in range(1, 121):
                ang = ang0 + 2 * math.pi * t / 120
                pts.append((cx + r_end * math.cos(ang), cy + r_end * math.sin(ang)))
            pts = machine.decimate(pts, 0.3)
            stroke(pts, z, first=(k == 0))
            if k == 0:
                w("M106 S51                        ; 20% fan from layer 2")
        band = circle(r_out, seg=0.4).difference(circle(r_out - 2 * bw, seg=0.4))
        from shapely import affinity
        band = affinity.translate(band, cx, cy)
        boss_r = (a.bore_mod + 4 * bw + (1.2 if a.socket == "lobed" else 0)) / 2.0
        boss_discs = [affinity.translate(circle(boss_r, seg=0.4), px, py)
                      for px, py in centers]
        holes = unary_union(sockets_at(centers, a.bore_mod))
        reg = unary_union([band] + boss_discs).difference(holes)
        if reg.geom_type != "Polygon":
            raise SystemExit("topper socket ring is not one connected region")
        z_cap = machine.PRESS_HARD + (CAP_LAYERS - 1) * lh
        for s_ in range(TOP_SOCKET_LAYERS):
            # first socket layer lies on the solid cap — the bore voids start above it
            emit_region_layer(reg, z_cap + (s_ + 1) * lh,
                              holes=None if s_ == 0 else holes.buffer(-0.4))
        grams = e * A * 1.24 / 1000.0
        mins = (e / e_per_mm) / speed / 60.0
        fn = os.path.join(a.out, f"web_topper_{a.printer}_T{temp:g}.gcode")
        summary = (f"  topper: {CAP_LAYERS}-layer spiral cap r{r_in:.0f}-{r_out:.0f} + "
                   f"{TOP_SOCKET_LAYERS}-layer socket ring ({N_STICKS} sockets bore "
                   f"{a.bore_mod:g}); ~{grams:.0f} g, ~{mins:.0f} min")

    w("M107"); w("M104 S0")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}   ; bed STAYS hot between parts (Oleg)")
    w("G0 Z40 F900")
    w(f"G0 X{min(10.0, bx - 10):.0f} Y{by - 10:.0f} F9000")
    os.makedirs(a.out, exist_ok=True)
    open(fn, "w").write("\n".join(L) + "\n")
    print(summary)
    print(fn)


if __name__ == "__main__":
    main()
