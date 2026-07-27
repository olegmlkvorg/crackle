#!/usr/bin/env python3
"""BUCKET — five-layer rosette floor, one-bead lobed wall, sinusoid Z-wave to save material.

Oleg, 2026-07-27, three instructions, latest wins where they touch:
  · "use roseta as you base for thesign of the bucket i guess. the floor can have holes its fine"
  · "improve shape of bucket so we follow more of boudary area fo rosetta instead of plain circle"
  · "for the bucket. floor 5 layers. walls single layer. strict"
  · "also try Z axis manilulation during wall print so we can use less material for walls.
     sinusoid pagttern"

Three parts, one continuous stroke per layer (floor) and ONE stroke for the whole wall:

  FLOOR   five layers: the rhodonea rosette (p13 q8 n3) inside a rim band. The rim is no longer
          circles — it is inward offsets of the WALL's lobed path, so the floor's outer band sits
          exactly under the wall it has to carry. The rose leaves daylight between its lobes.

  WALL    one bead thick, STRICT — no fillet, no thickened base; the five-layer floor is the
          adhesion now. Its XY path is the rose's own boundary: the closing of the buffered rose
          (holes bridged at --close radius) instead of a plain circle, so the wall scallops in
          and out with the lobes.

  WAVE    the wall is a single continuous helix of THROW-AND-LAND waves.

          v1 was a pure sinusoid welded at crest/trough TANGENCIES — points. IT FAILED ON THE
          PLATE (2026-07-27, K2, cancelled ~21 min in): the point welds did not adhere. Oleg,
          from the machine: "bucket failed on adhesion of sin pattern. so you need to thow into
          the air then land and adheeeeeese then thro again. and next layer should be on the
          tops of prev layer sinus."

          So the wave is flat-topped now, per wavelength (fractions of lambda):
              LAND  [0.0-0.2)  flat, welded one layer height above the strand below
              RISE  [0.2-0.5)  cosine ramp up by H, airborne
              TOP   [0.5-0.7)  flat, in the air — it becomes the NEXT lap's landing pad
              FALL  [0.7-1.0)  cosine ramp back down, ending exactly at the next landing
          The extra HALF wave per lap staggers the phase, and LAND+RISE = exactly half a
          wavelength is load-bearing: it maps every landing of lap k+1 onto a TOP of lap k for
          its FULL length, at exactly one layer height of gap (z(t+L) - z(t) = (H+lh) +
          H*(prof(x+1/2) - prof(x)), which is lh wherever the later lap lands). One lap climbs
          H + layer_h instead of layer_h — at H=2.4 that is 5x less wall material. The wall
          ends after an EVEN number of laps, i.e. ON a landing, welded — and the rim is wavy,
          which is the construction showing honestly.

Numbers and their provenance:
  H=2.4mm                 CHOSEN — 4 beads of climb per wave; wall openings ~lambda x H. Not measured.
  waves/lap               DERIVED from the Z axis's speed budget: the steepest cosine-ramp slope
                          is H*pi/(0.6*lambda); lambda is chosen so Z speed stays under 80% of
                          machine.MAX_Z_V at the north-star head speed.
  weld gap = layer_h      DERIVED — the normal layer step, held across the WHOLE landing.
  E per mm                metered on TRUE 3D path length (F is a 3D feedrate in Klipper), so
                          delivered flow is constant on the ramps too. validate.py reads flow
                          per XY mm and sees more on the steepest ramp — real geometry, inside
                          its 20% window, not an error.
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
    rim strokes start), or anywhere in `prior` -- strokes already laid in this layer, so the rim
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


def ring_of(poly_boundary, seg):
    """A closed shapely ring as an evenly-spaced point list (endpoint NOT repeated).

    Even spacing matters twice: the wave phase is parameterised by arc length, so uneven
    sampling would warp the sinusoid; and the move rate the host sees is speed/seg, which
    stalls Klipper near 300/s -- seg comes in derived from the commanded speed.
    """
    n = max(16, int(math.ceil(poly_boundary.length / seg)))
    return [(p.x, p.y) for p in
            (poly_boundary.interpolate(i / n, normalized=True) for i in range(n))]


def rotate_to(pts, near):
    """Rotate a closed ring so it starts at the point nearest `near` — every stroke starts
    where the previous one ended (no-dry-travel rule)."""
    if near is None:
        return pts
    i = min(range(len(pts)), key=lambda k: (pts[k][0]-near[0])**2 + (pts[k][1]-near[1])**2)
    return pts[i:] + pts[:i]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia", type=float, default=200.0, help="outside diameter at the lobes, mm")
    ap.add_argument("--height", type=float, default=200.0, help="overall height, mm")
    ap.add_argument("--rim", type=float, default=None, help="floor rim band width; default 3 beads")
    ap.add_argument("--floor-layers", type=int, default=5)
    ap.add_argument("--close", type=float, default=12.0,
                    help="closing radius for the rose envelope, mm — smallest that leaves one "
                         "clean ring; below ~10 the envelope grows necks and holes")
    ap.add_argument("--wave-amp", type=float, default=2.4,
                    help="wave height H, mm — each lap climbs H + layer_h")
    ap.add_argument("--waves", type=int, default=0,
                    help="whole waves per lap (a half wave is added for the landing stagger); "
                         "0 = derive the most waves the Z axis's speed budget allows")
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--bead-w", type=float, default=None)
    ap.add_argument("--flow", type=float, default=None)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    a.flow = a.flow or machine.flow_cap(a.material, a.printer)
    a.bead_w = a.bead_w or machine.bead_for_flow(a.flow, a.layer_h)
    speed = machine.speed_for_flow(a.flow, a.bead_w, a.layer_h)
    temp = machine.temp_for(a.material)
    bw = a.bead_w
    lh = a.layer_h

    # Z SPEED IS A HARD LIMIT, SO IT IS CHECKED, NOT HOPED. The steepest slope of the sinusoid is
    # A * 2pi * (waves+0.5) / L; at the print speed that is the Z feed the machine must deliver.
    # Refusing here beats a stalled or layer-shifted wall 150mm up.

    # THE RIM IS A WHOLE NUMBER OF BEADS. A fractional band leaves a void between passes -- the
    # defect Oleg spotted in the pole hook's ring.
    rim = a.rim or 3 * bw
    rim_passes = max(2, round(rim / bw))

    bx, by = machine.BED[a.printer]
    cx, cy = bx / 2.0, by / 2.0
    R = a.dia / 2.0

    # floor: the rose, fattened to a bead; its own closing is the wall's path
    rose_pts = rose(cx, cy, R - bw / 2, (R - bw / 2) * 0.11)
    # DECIMATE THE ROSE. Its points are evenly spaced in the PARAMETER, not in distance, so they
    # bunch where the curve dives toward the centre: measured 380 moves/s against the ~300 where
    # Klipper drains its lookahead and freezes with no error at all.
    rose_pts = machine.decimate(rose_pts, machine.CONSTANT_SPEED / 300.0 * 1.2)
    rose_z, n_cross = crossing_z(rose_pts, bw, machine.PRESS_HARD, 0.5)
    rose_region = LineString(rose_pts).buffer(bw / 2.0, resolution=8)

    # THE WALL FOLLOWS THE ROSE'S OWN BOUNDARY, NOT A CIRCLE (Oleg: "follow more of boudary area
    # fo rosetta instead of plain circle"). The closing of the rose region -- buffer out, buffer
    # back in -- bridges the clefts between lobes at --close radius and hugs the tips, giving one
    # smooth lobed ring. Measured on the d200 rose: r runs 95.8..100 around the lap, 13 scallops.
    env = rose_region.buffer(a.close, resolution=64).buffer(-a.close, resolution=64)
    if env.geom_type == 'MultiPolygon':
        env = max(env.geoms, key=lambda g: g.area)
    seg = max(0.25, speed / 250.0)
    # wall centre line: half a bead inside the envelope, so the bead's outer edge IS the boundary
    wall_poly = env.buffer(-bw / 2.0)
    if wall_poly.geom_type == 'MultiPolygon':
        raise SystemExit(f"envelope necks at --close {a.close:g}: the wall ring splits when "
                         f"inset half a bead. Raise --close.")
    wall_ring = ring_of(wall_poly.exterior, seg)
    Lw = wall_poly.exterior.length
    H = a.wave_amp
    # WAVELENGTH FROM THE Z AXIS'S SPEED BUDGET, derived not picked. The steepest point of the
    # cosine ramp is H*pi/(2*ramp_len) with ramp_len = 0.3*lambda; F is a 3D feedrate, so the
    # Z component is speed*slope/sqrt(1+slope^2), held under 80% of machine.MAX_Z_V.
    if a.waves:
        m_waves = a.waves
    else:
        zv_bud = 0.8 * machine.MAX_Z_V
        slope_star = zv_bud / math.sqrt(max(speed * speed - zv_bud * zv_bud, 1e-9))
        m_waves = max(3, int(Lw / (H * math.pi / (0.6 * slope_star)) - 0.5))
    lam = Lw / (m_waves + 0.5)
    slope = H * math.pi / (0.6 * lam)
    zv = slope * speed / math.sqrt(1 + slope * slope)
    if zv > machine.MAX_Z_V * 0.85:
        raise SystemExit(f"wave ramp slope {slope:.2f} needs {zv:.1f} mm/s of Z at {speed:g} mm/s "
                         f"— over 85% of machine.MAX_Z_V={machine.MAX_Z_V:g}. Fewer --waves or "
                         f"less --wave-amp.")

    # floor rim: inward offsets of the SAME envelope, so the band sits exactly under the wall
    rim_rings = []
    for j in range(rim_passes):
        rp = env.buffer(-(bw / 2.0 + j * bw))
        if rp.geom_type == 'MultiPolygon':
            rp = max(rp.geoms, key=lambda g: g.area)
        rim_rings.append(ring_of(rp.exterior, seg))

    A = math.pi * (1.75 / 2) ** 2
    e_per_mm = bw * lh / A
    f = round(speed * 60)
    L = []
    w = L.append
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh}")
    w(f"; FLOW={bw*lh*speed:.4f}")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w("; ARGV: " + " ".join(sys.argv))
    w(f"; bucket d{a.dia:.0f}xh{a.height:.0f}, bead {bw:.2f}x{lh} at {speed:.1f} mm/s")
    w(f"; wall = rose envelope (close {a.close:g}), throw-and-land wave H={H:g} x {m_waves}.5/lap")
    w("M82")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M104 S{temp}")
    w("G28")
    # BED THRESHOLD SCALES WITH FOOTPRINT. Oleg's "you dont need to wait for 120 plate" was about
    # a small part; this one is 200mm across. Oleg, 2026-07-27: "for the bucket it was good
    # start, lets try bed 120 there." So ON THE K2 the bucket waits for the FULL 120 target —
    # the K2 provably reaches it (printed today). Any other machine gets machine.bed_start():
    # the K1C pins at ~87-91, and a blocking M190 at an unreachable target is an infinite stall,
    # not a rule (review-confirmed).
    # M190 BLOCKS, AND CANNOT BE MISPARSED (a quoted TEMPERATURE_WAIT sensor name was silently
    # skipped once — the print started at 78C). Target is re-raised after so the plate keeps
    # climbing while the part starts.
    _bed = machine.bed_for(a.material, a.printer)
    _floor = _bed if a.printer == "k2plus" else machine.bed_start(a.material, _bed)
    w(f"M190 S{_floor:.0f}   ; BLOCKING: do not start below this")
    w(f"M140 S{_bed:.0f}")
    w(f"M109 S{temp}")
    # fan LOW/OFF for layer 1 (it only has to weld to the plate); body fan from layer 2
    _fan_l1 = int(round(machine.fan_first_layer(a.material) * 255))
    w(f"M106 S{_fan_l1}" if _fan_l1 else "M107")
    w("G92 E0")
    # prime in the clear, then break the bead off at an angle so no tail rides onto the part;
    # py0 clamped on-bed — cy-R-14 lands at Y-4 on the K1C's 220 bed (review-confirmed)
    px0, py0 = 20.0, max(6.0, cy - R - 14.0)
    w(f"G1 Z{machine.PRESS_HARD:.3f} F600")
    w(f"G0 F9000 X{px0:.3f} Y{py0:.3f}")
    w("G1 E20 F300                      ; PRIME stationary purge")
    w(f"G1 F1200 X{px0+40:.3f} Y{py0:.3f} E30   ; PRIME line, in the clear")
    w(f"G0 F3000 X{px0+52:.3f} Y{py0+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    # WITHOUT THIS MARKER several checks silently do not run (validate.py: "BODY NEVER STARTED
    # ... This file is unchecked, not clean."). ARCH_LIFT declares that Z varies inside layers
    # BY DESIGN — the floor's crossing lifts and the wall's wave both live under it.
    w(f"; ARCH_LIFT={max(0.5 - machine.PRESS_HARD, H):.3f}")
    # The wave wall descends on purpose at up to this dz/dxy. validate.py's per-cell dive check
    # uses it to raise its in-cell threshold PAST self-descent (slope * cell diagonal) while
    # staying UNDER one layer height — so a real collision with the lap below still fails.
    w(f"; WAVE_SLOPE={slope:.3f}")
    w("; BODY_START")

    e = 0.0
    pos = [None]
    last = [None]

    def stroke(pts, z, first, zs=None):
        """Emit one continuous stroke, metering E from the REAL distance travelled.

        The first version set the pen position to pts[0] without accounting for where the head
        actually was. At every stroke boundary the head then crossed a real gap while E advanced
        by the next segment's tiny amount: a starved thread at 8.9 mm3/s against a declared 60.
        R4 caught it before it printed.
        """
        nonlocal e
        base = z - machine.PRESS_HARD
        # zs is layer-relative (PRESS_HARD..lift); the layer offset must be applied everywhere
        # alike, or a layer-2 gap-close would extrude down at layer-1 Z
        z0 = (base + zs[0]) if zs else z
        if first or pos[0] is None:
            w(f"G0 F9000 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; PRIME-TRAVEL to first point")
            pos[0] = (pts[0][0], pts[0][1], z0)
        qx, qy, qz = pos[0]
        d0 = math.hypot(pts[0][0] - qx, pts[0][1] - qy)
        ceil = None
        if z0 >= qz - 1e-9:
            # net ascent (every layer start) or level. THE BARE Z LINE IS A MARKER, NOT A MOVE
            # TO THE STROKE'S FIRST POINT: validate.py reads bare-Z lines as the layer floor,
            # so it must be emitted at the LAYER'S BASE Z, never at a lifted start — a marker
            # at 2.9 made every later in-stroke descent to the true 2.5 floor read as a plough.
            # If the head parked lifted above the base (envelope rims end ON the rose tips),
            # there is no honest marker to write; the gap-close carries the whole transition.
            if qz <= z + 1e-9:
                w(f"G1 F1800 Z{z:.3f}")
            if d0 > 0.02:                  # close the gap AS EXTRUSION, properly metered
                e += d0 * e_per_mm
                w(f"G1 F{f} X{pts[0][0]:.3f} Y{pts[0][1]:.3f} Z{z0:.3f} E{e:.5f}")
            else:
                if z0 > max(qz, z) + 1e-9:
                    w(f"G1 F1800 Z{z0:.3f}   ; rise in place onto a lifted start")
                w(f"G1 F{f}")
        elif d0 > 0.02:
            # DESCENDING INTO A NEW STROKE: the previous stroke ended lifted (the envelope rim
            # rides the rose tips for whole arcs). A bare Z drop here plunges the nozzle 0.4mm
            # into the strand it just laid — validate.py caught 69 of those. Carry the descent
            # INSIDE the extruding gap-close instead: off the lifted strand, down across the
            # gap, landing on the new stroke's virgin start.
            e += d0 * e_per_mm
            w(f"G1 F{f} X{pts[0][0]:.3f} Y{pts[0][1]:.3f} Z{z0:.3f} E{e:.5f}")
        else:
            # descending with no gap to carry it: ramp down along the new path at the same
            # 0.2mm/mm the crossing lifts use, never below each point's own target
            w(f"G1 F{f}")
            ceil = qz
        qx, qy = pts[0]
        zz = z0
        cum = 0.0
        for i, (X, Y) in enumerate(pts[1:], 1):
            d = math.hypot(X - qx, Y - qy)
            if d < 0.02:
                continue
            cum += d
            e += d * e_per_mm
            zz = (base + zs[i]) if zs else z
            if ceil is not None:
                zz = max(zz, ceil - 0.2 * cum)
            w(f"G1 X{X:.3f} Y{Y:.3f} Z{zz:.3f} E{e:.5f}")
            qx, qy = X, Y
        last[0] = (qx, qy)
        pos[0] = (qx, qy, zz)

    # ---- FLOOR: five layers of rose + rim band, every stroke lifting over earlier material ----
    first = True
    for k in range(a.floor_layers):
        z = machine.PRESS_HARD + k * lh
        stroke(rose_pts, z, first, zs=rose_z); first = False
        prior = list(rose_pts)
        for ring in rim_rings:
            cpts = rotate_to(ring, last[0]) + []
            cpts = cpts + [cpts[0]]        # close the lap
            cz, _ = crossing_z(cpts, bw, machine.PRESS_HARD, 0.5, prior=prior)
            stroke(cpts, z, False, zs=cz)
            prior += cpts
        if k == 0:
            w("M106 S51                        ; body fan from layer 2 — layer 1 welds unchilled")

    # ---- WALL: throw-and-land wave helix, single bead, strict ----
    # Landings weld along a SEGMENT (0.2*lambda), not at a point — the point-tangency sinusoid
    # failed on the plate (see the module docstring for Oleg's field correction). LAND+RISE =
    # exactly half a wavelength is load-bearing: the half-wave stagger then maps every landing
    # of lap k+1 onto a TOP of lap k for its full length,
    #     z(t+L) - z(t) = (H + lh) + H*(prof(x+1/2) - prof(x))  =  lh on every landing,
    # and never less anywhere (prof differences are bounded by [-1, 0] there). The climb
    # (H+lh)*t/L is a continuous helix — a per-lap step materializes the whole climb in one
    # 0.25mm segment at the seam (v1's 67 near-vertical moves).
    z_ft = machine.PRESS_HARD + (a.floor_layers - 1) * lh    # top floor layer's Z
    wall = rotate_to(wall_ring, last[0])
    n_ring = len(wall)
    ds = Lw / n_ring

    def prof(x):
        """z fraction within one wave, x in [0,1): LAND flat (welded), RISE cosine, TOP flat
        (airborne — the next lap's landing pad), FALL cosine into the next landing."""
        if x < 0.2:
            return 0.0
        if x < 0.5:
            return 0.5 * (1.0 - math.cos(math.pi * (x - 0.2) / 0.3))
        if x < 0.7:
            return 1.0
        return 0.5 * (1.0 + math.cos(math.pi * (x - 0.7) / 0.3))

    # END ON A LANDING: an even lap count finishes the strand welded onto a top, not mid-air.
    # No hem, no taper — the rim is wavy, which is the construction showing honestly. (A taper
    # is where v1 grew its plough regime; the landing map above only holds at constant H.)
    K = int((a.height - z_ft - lh - H) // (H + lh))
    if K % 2:
        K -= 1
    if K < 2:
        raise SystemExit(f"height {a.height:g} leaves no room for a wave wall over a "
                         f"{z_ft:g}mm floor at H={H:g}")
    w(f"; WALL_START — throw-and-land helix: land {0.2*lam:.1f}mm welded, throw "
      f"{0.8*lam:.1f}mm airborne, climb {H+lh:g}/lap, {K} laps")
    qx, qy, qz = pos[0]
    t = 0.0
    started = False
    for lap in range(K):
        for i in range(n_ring):
            X, Y = wall[i]
            x = ((m_waves + 0.5) * t / Lw) % 1.0
            Z = z_ft + lh + (H + lh) * t / Lw + H * prof(x)
            dxy = math.hypot(X - qx, Y - qy)
            if dxy > 0.02:
                d3 = math.hypot(dxy, Z - qz)   # E on TRUE 3D length: constant flow on ramps
                e += d3 * e_per_mm
                w(f"G1 {'F%d ' % f if not started else ''}X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}")
                started = True
                qx, qy, qz = X, Y, Z
            t += ds
    revs = K
    mid = z_ft + lh + (H + lh) * K         # final landing level = top of the wall's welds

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{mid + 30:.1f} F900")
    g = "\n".join(x for x in L if x) + "\n"

    grams = e * A * 1.24 / 1000.0
    mins = (e / e_per_mm) / speed / 60.0
    print(f"  {n_cross} of {len(rose_pts)} rose points ride over a crossing "
          f"(Z {machine.PRESS_HARD} -> 0.5)")
    print(f"  floor {a.floor_layers} layers (rose + {rim_passes} envelope passes); wall "
          f"{revs} laps of {Lw:.0f}mm, climbing {H + lh:g}/lap vs {lh:g} solid "
          f"= {(H + lh)/lh:.1f}x less wall material")
    print(f"  wave: H={H:g}, {m_waves}.5 waves/lap — land {0.2*lam:.1f}mm welded / throw "
          f"{0.8*lam:.1f}mm airborne; max Z speed {zv:.1f} mm/s (limit {machine.MAX_Z_V:g})")
    print(f"  top of wall at Z{mid:.1f} (asked {a.height:g}); ~{grams:.0f} g, ~{mins:.0f} min")
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out,
                      f"bucket_wave_{a.printer}_d{a.dia:.0f}_h{a.height:.0f}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
