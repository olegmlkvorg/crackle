#!/usr/bin/env python3
"""ROTUNDA — the bucket: rosette floor + tower colonnade + woven bridge web. One stroke.

Oleg, 2026-07-27, after the towers probes printed well ("perfect"): "now transfer that to
bucket, and instead of middle line make a wawe between front and back lines. roseta base pluse
what we figured now. a tower in each in/out outer roseta shape turn + additional brim to keep
towers stable."

Assembly, bottom up:
  BRIM    layer 1 only, OUTSIDE the envelope — 2 outward offset rings. He asked for it
          ("additional brim to keep towers stable"), so the no-brim default does not apply.
  FLOOR   the proven rosette floor from bucket.py: rhodonea p13 q8 n3 with crossing lifts,
          inside a rim band of envelope insets — 5 layers (his strict spec).
  TOWERS  one d8 vase tower at EVERY radial turn of the lobed envelope — each lobe tip (out)
          and each cleft (in), found as local extrema of the wall line's radius. They rise in
          rotation, 5 laps per visit, flow never stopping (the v2/v3 probes).
  WEB     per gap per level, three connections (v3, amended): straight flight down the FRONT
          (outer) line, then the middle strand is a WAVE — it climbs back up while surfing
          laterally between the front and back lines (full sine period, touching each once,
          welding mid-air where it crosses the front chord) — then a straight flight down the
          BACK (inner) line. Ends on the lower tower, which takes its 5 laps.

Zero travels after the prime: the floor chains into tower 1 and every transit is extruded.
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import LineString
from shapely.ops import unary_union

import machine
from bucket import rose, crossing_z, ring_of


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia", type=float, default=200.0)
    ap.add_argument("--height", type=float, default=200.0)
    ap.add_argument("--floor-layers", type=int, default=5)
    ap.add_argument("--close", type=float, default=12.0)
    ap.add_argument("--tower-d", type=float, default=8.0)
    ap.add_argument("--laps-per-visit", type=int, default=5)
    ap.add_argument("--rim", type=float, default=None, help="floor rim band; default 3 beads")
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
    r_t = a.tower_d / 2.0
    kpv = a.laps_per_visit
    bx, by = machine.BED[a.printer]
    cx, cy = bx / 2.0, by / 2.0
    R = a.dia / 2.0
    rim_passes = max(2, round((a.rim or 3 * bw) / bw))

    # floor geometry — the proven bucket.py construction
    rose_pts = rose(cx, cy, R - bw / 2, (R - bw / 2) * 0.11)
    rose_pts = machine.decimate(rose_pts, machine.CONSTANT_SPEED / 300.0 * 1.2)
    rose_z, n_cross = crossing_z(rose_pts, bw, machine.PRESS_HARD, 0.5)
    rose_region = LineString(rose_pts).buffer(bw / 2.0, resolution=8)
    env = rose_region.buffer(a.close, resolution=64).buffer(-a.close, resolution=64)
    if env.geom_type == 'MultiPolygon':
        env = max(env.geoms, key=lambda g: g.area)
    seg = max(0.25, speed / 250.0)
    wall_line = env.buffer(-bw / 2.0)
    if wall_line.geom_type == 'MultiPolygon':
        raise SystemExit(f"envelope necks at --close {a.close:g}; raise it")
    rim_rings = []
    for j in range(rim_passes):
        rp = env.buffer(-(bw / 2.0 + j * bw))
        if rp.geom_type == 'MultiPolygon':
            rp = max(rp.geoms, key=lambda g: g.area)
        rim_rings.append(ring_of(rp.exterior, seg))
    brim_rings = []
    for j in (1, 2):                      # ASKED-FOR brim: outward, layer 1 only
        bp = env.buffer(j * bw)
        brim_rings.append(ring_of(bp.exterior, seg))

    # TOWERS AT EVERY RADIAL TURN of the tower line: local maxima (lobe tips) and minima
    # (clefts) of r(theta), found on the emitted path itself — never assumed from the rose
    # formula (the closing merges clefts; count what IS, not what the math suggests).
    # THE TOWER LINE IS THE WALL LINE INSET BY ONE TOWER RADIUS: centred on the wall line a
    # d8 ring would overhang the floor's outer edge by ~3mm — the feet must sit entirely ON
    # the floor, with each ring's outer arc kissing the wall line from inside.
    tower_line = env.buffer(-(bw / 2.0 + a.tower_d / 2.0))
    if tower_line.geom_type == 'MultiPolygon':
        tower_line = max(tower_line.geoms, key=lambda g: g.area)
    wl = ring_of(tower_line.exterior, 1.0)
    rr = [math.hypot(x - cx, y - cy) for x, y in wl]
    n = len(wl)
    WIN = 7
    centres = []
    for i in range(n):
        window = [rr[(i + d) % n] for d in range(-WIN, WIN + 1)]
        if rr[i] == max(window) or rr[i] == min(window):
            if centres and math.hypot(wl[i][0] - centres[-1][0], wl[i][1] - centres[-1][1]) < 6.0:
                continue
            centres.append(wl[i])
    if math.hypot(centres[0][0] - centres[-1][0], centres[0][1] - centres[-1][1]) < 6.0:
        centres.pop()
    N = len(centres)
    # order around the ring is inherited from the wall line — already sequential

    A = math.pi * (1.75 / 2) ** 2
    e_per_mm = bw * lh / A
    f = round(speed * 60)
    n_lap = max(24, int(2 * math.pi * r_t / seg))
    laps = max(kpv, int(round((a.height - a.floor_layers * lh) / lh)))

    L = []
    w = L.append
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh}")
    w(f"; FLOW={bw*lh*speed:.4f}")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w("; ARGV: " + " ".join(sys.argv))
    w(f"; ROTUNDA d{a.dia:g} h{a.height:g}: {N} towers d{a.tower_d:g} at envelope turns, "
      f"{kpv} laps/visit, front/wave/back web")
    w(f"; ARCH_LIFT={0.5 - machine.PRESS_HARD:.3f}")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {laps + a.floor_layers}")
    w("; HEADER_BLOCK_END")
    w("M82")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M104 S{temp}")
    w("G28")
    w(f"M190 S{machine.bed_start(a.material, machine.bed_for(a.material, a.printer)):.0f}")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M109 S{temp}")
    w("G92 E0")
    px0, py0 = 20.0, max(6.0, cy - R - 14.0)
    w(f"G1 Z{machine.PRESS_HARD:.3f} F600")
    w(f"G0 F9000 X{px0:.3f} Y{py0:.3f}")
    w("G1 E20 F300                      ; PRIME stationary purge")
    w(f"G1 F1200 X{px0+40:.3f} Y{py0:.3f} E30   ; PRIME line, in the clear")
    w(f"G0 F3000 X{px0+52:.3f} Y{py0+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    w("; BODY_START")

    e = 0.0
    pos = [None, None, None]              # x, y, z of the pen

    def stroke(pts, z, first=False, zs=None):
        """Continuous stroke at layer z (zs = per-point lift ladder), E on 3D length."""
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
                e_add = math.hypot(d0, z0 - pos[2]) * e_per_mm
                e2 = e + e_add
                w(f"G1 F{f} X{pts[0][0]:.3f} Y{pts[0][1]:.3f} Z{z0:.3f} E{e2:.5f}")
                e = e2
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
        i = min(range(len(ring)),
                key=lambda k: (ring[k][0]-pos[0])**2 + (ring[k][1]-pos[1])**2)
        out = ring[i:] + ring[:i]
        return out + [out[0]]

    # ---- FLOOR (5 layers) with layer-1 brim first, outermost first ----
    w("M107                              ; layer 1 bonds uncooled")
    for k in range(a.floor_layers):
        z = machine.PRESS_HARD + k * lh
        if k == 0:
            b1 = brim_rings[1] + [brim_rings[1][0]]
            stroke(b1, z, first=True)
            stroke(nearest_start(brim_rings[0]), z)
        stroke(rose_pts, z, first=False, zs=rose_z)
        prior = list(rose_pts)
        for ring in rim_rings:
            cpts = nearest_start(ring)
            cz, _ = crossing_z(cpts, bw, machine.PRESS_HARD, 0.5, prior=prior)
            stroke(cpts, z, zs=cz)
            prior += cpts
        if k == 0:
            w("M106 S51                        ; 20% fan from layer 2")

    # ---- COLONNADE: towers rise in rotation, web transits, flow never stops ----
    z_ft = machine.PRESS_HARD + (a.floor_layers - 1) * lh
    z = [z_ft] * N
    done = [0] * N
    start_at = [None] * N
    n_bridge = 0
    # START AT THE TOWER NEAREST THE FLOOR'S END. Starting at index 0 extruded the gap-close
    # as a 186mm chord straight across the finished floor (over every lifted rose crossing) —
    # the validator's worst finding on the first cut. The rotation order is a ring; where it
    # starts is free, so start where the pen already is.
    k = min(range(N), key=lambda i: (centres[i][0]-pos[0])**2 + (centres[i][1]-pos[1])**2)
    # THE FLOOR'S SURFACE IS NOT FLAT — crossing lifts stand 0.4 proud of the top layer where
    # the rose rides over itself. First-visit tower laps and first-level transits graze those
    # tips (the same problem bucket.py's rim rings solved with crossing_z prior=rose). Towers
    # clear it by starting their ladder above the lifted tops; the first lap's ring lands on
    # the rim band (flat, no rose crossings within a bead) so only TRANSIT strands cross rose
    # territory, and they inherit the raised base too.
    Z_CLEAR = 0.4 + 0.1                    # lift height + margin over the floor top
    z = [z_ft + Z_CLEAR] * N

    def tower_ring(kk, start_xy):
        tx, ty = centres[kk]
        if start_xy is None:
            start_xy = (tx + r_t, ty)
        a0 = math.atan2(start_xy[1] - ty, start_xy[0] - tx)
        return [(tx + r_t*math.cos(a0 + 2*math.pi*i/n_lap),
                 ty + r_t*math.sin(a0 + 2*math.pi*i/n_lap)) for i in range(n_lap + 1)]

    def helix(kk, nlaps):
        nonlocal e
        pts = tower_ring(kk, start_at[kk])
        # gap-close onto the tower start (extruded, 3D metered)
        d0 = math.hypot(pts[0][0] - pos[0], pts[0][1] - pos[1])
        if d0 > 0.02:
            e += math.hypot(d0, z[kk] - pos[2]) * e_per_mm
            w(f"G1 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} Z{z[kk]:.3f} E{e:.5f}")
            pos[0], pos[1], pos[2] = pts[0][0], pts[0][1], z[kk]
        C = 2 * math.pi * r_t
        t = 0.0
        qx, qy, qz = pos[0], pos[1], pos[2]
        for _ in range(nlaps):
            for X, Y in pts[1:]:
                d = math.hypot(X - qx, Y - qy)
                if d < 0.02:
                    continue
                t += d
                Z = z[kk] + lh * t / C
                e += math.hypot(d, Z - qz) * e_per_mm
                w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}")
                qx, qy, qz = X, Y, Z
        z[kk] += nlaps * lh
        start_at[kk] = (qx, qy)
        pos[0], pos[1], pos[2] = qx, qy, qz

    def rim_walk(kk, to):
        nonlocal e
        tx, ty = centres[kk]
        aw0 = math.atan2(pos[1] - ty, pos[0] - tx)
        aw1 = math.atan2(to[1] - ty, to[0] - tx)
        daw = (aw1 - aw0 + math.pi) % (2*math.pi) - math.pi
        steps = max(1, int(abs(daw) * r_t / seg))
        for i in range(1, steps + 1):
            aa = aw0 + daw * i / steps
            X, Y = tx + r_t*math.cos(aa), ty + r_t*math.sin(aa)
            d = math.hypot(X - pos[0], Y - pos[1])
            if d < 0.02:
                continue
            e += d * e_per_mm
            w(f"G1 X{X:.3f} Y{Y:.3f} Z{pos[2]:.3f} E{e:.5f}   ; rim walk")
            pos[0], pos[1] = X, Y

    def flight(to, zto, tag):
        nonlocal e, n_bridge
        d3 = math.hypot(to[0] - pos[0], to[1] - pos[1], zto - pos[2])
        e += d3 * e_per_mm
        w(f"G1 X{to[0]:.3f} Y{to[1]:.3f} Z{zto:.3f} E{e:.5f}   ; BRIDGE {tag}")
        n_bridge += 1
        pos[0], pos[1], pos[2] = to[0], to[1], zto

    def wave_up(frm_kk, to_kk, zto, amp):
        """The middle strand: descends while surfing between the front and back lines —
        a full sine period of lateral offset, touching each line once.

        AMPLITUDE IS CLEARANCE-CHECKED PER GAP. In tight clefts the ±r_t swing clips a
        NEIGHBOURING tower's standing wall — measured on the first emitted file: one gap, one
        XY spot, a 0.373mm plough repeating at every level. The swing shrinks (halving until
        clear, floor 0 = straight centre chord) for exactly the gaps that need it."""
        nonlocal e, n_bridge
        tx, ty = centres[to_kk]
        fx, fy = centres[frm_kk]
        du = math.hypot(tx - fx, ty - fy)
        ux, uy = (tx - fx) / du, (ty - fy) / du
        pxp, pyp = -uy, ux
        # outward perpendicular: pick the sign pointing away from the bucket centre
        mx, my = (fx + tx) / 2 - cx, (fy + ty) / 2 - cy
        if pxp * mx + pyp * my < 0:
            pxp, pyp = -pxp, -pyp
        p0 = (pos[0], pos[1], pos[2])
        p1 = (tx - ux * r_t, ty - uy * r_t)     # the target tower's near rim point
        steps = 10

        def path(amp_try):
            # Z FROM THE GAP'S SHARED HEIGHT FIELD, NOT FROM PATH FRACTION. The chords run
            # tangent-to-tangent (full centre distance du); the wave's centreline is truncated
            # by r_t at each end. Linear-in-t Z made the wave sit dz*r_t/du = 0.373mm BELOW
            # the climb strand at their crossing — measured on the emitted file, all 24 dives,
            # one number. Projecting every wave point onto the k->nxt axis and taking the
            # chords' own z(proj) makes every crossing weld at matched height BY CONSTRUCTION.
            z_hi, z_lo = p0[2], zto
            out = []
            for i in range(1, steps + 1):
                t = i / steps
                lat = amp_try * math.sin(2 * math.pi * t)
                X = p0[0] + (p1[0] - p0[0]) * t + pxp * lat
                Y = p0[1] + (p1[1] - p0[1]) * t + pyp * lat
                proj = ((X - fx) * ux + (Y - fy) * uy) / du
                out.append((X, Y, z_hi + (z_lo - z_hi) * min(1.0, max(0.0, proj))))
            return out

        while amp > 0.05:
            ok = True
            for X, Y, _ in path(amp):
                for j, (ox2, oy2) in enumerate(centres):
                    if j in (frm_kk, to_kk):
                        continue
                    if math.hypot(X - ox2, Y - oy2) < r_t + bw:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                break
            amp /= 2.0
        else:
            amp = 0.0
        for X, Y, Z in path(amp):
            d3 = math.hypot(X - pos[0], Y - pos[1], Z - pos[2])
            e += d3 * e_per_mm
            w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}   ; BRIDGE wave")
            pos[0], pos[1], pos[2] = X, Y, Z
        n_bridge += 1

    while min(done) < laps:
        take = min(kpv, laps - done[k])
        helix(k, take)
        done[k] += take
        nxt = (k + 1) % N
        if min(done) >= laps:
            break
        tx, ty = centres[k]; ox, oy = centres[nxt]
        du = math.hypot(ox - tx, oy - ty)
        ux, uy = (ox - tx) / du, (oy - ty) / du
        pxp, pyp = -uy, ux
        mx, my = (tx + ox) / 2 - cx, (ty + oy) / 2 - cy
        if pxp * mx + pyp * my < 0:
            pxp, pyp = -pxp, -pyp           # p points OUT of the bucket
        # ORDER IS THE COLLISION CONTROL. Both chords carry strands with the SAME height
        # profile (z[k] at this tower -> z[nxt] at the next), and the wave descends with that
        # same profile — so laid LAST, it crosses each chord at exactly the height of the
        # strand already there: a mid-air WELD at both crossings (an X-braced truss), zero
        # ploughing. The first cut laid the wave second and the back flight then passed 0.75mm
        # UNDER the hanging wave — 539 dives, validate caught it before the plate.
        a_out = (tx + r_t * pxp, ty + r_t * pyp)
        b_out = (ox + r_t * pxp, oy + r_t * pyp)
        a_in = (tx - r_t * pxp, ty - r_t * pyp)
        b_in = (ox - r_t * pxp, oy - r_t * pyp)
        a_ce = (tx + r_t * ux, ty + r_t * uy)     # this tower's rim point facing the next
        b_ce = (ox - r_t * ux, oy - r_t * uy)     # the next tower's rim point facing back
        rim_walk(k, a_out)
        flight(b_out, z[nxt], "front")       # straight, DOWN, outer line (v2 proven)
        rim_walk(nxt, b_in)
        flight(a_in, z[k], "climb")          # straight, UP, inner line (v3 printed well)
        rim_walk(k, a_ce)
        wave_up(k, nxt, z[nxt], r_t)         # the WAVE, laid last: down the centreline,
        start_at[nxt] = b_ce                 # surfing line-to-line, welding at both crossings
        k = nxt

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{max(z) + 30:.1f} F900")
    w(f"G0 X{min(10.0, bx-10):.0f} Y{by-10:.0f} F9000")
    g = "\n".join(L) + "\n"

    grams = e * A * 1.24 / 1000.0
    mins = (e / e_per_mm) / speed / 60.0
    print(f"  {N} towers d{a.tower_d:g} at envelope turns; floor {a.floor_layers} layers "
          f"(rose {n_cross} lifts + {rim_passes} rim passes + layer-1 brim x2, ASKED)")
    print(f"  {laps} laps/tower, {kpv}/visit; {n_bridge} bridges (front/wave/back per gap-level)")
    print(f"  full flow {bw*lh*speed:.0f} mm3/s at {speed:g} mm/s; ~{grams:.0f} g, ~{mins:.0f} min")
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"rotunda_{a.printer}_d{a.dia:g}_h{a.height:g}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
