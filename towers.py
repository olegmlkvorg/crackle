#!/usr/bin/env python3
"""TOWERS — spiral pillars rising in rotation, connected by bridge rungs. First probe.

Oleg, 2026-07-27: "lets explore spiral towers design with bridges over it" ... "k2 is waiting
for next test with spiral towers connected by bridges".

The mechanism under test, before any bucket-scale design:
  N small vase-mode towers rise TOGETHER — the head prints one helix lap on tower 1, hops
  (lifted, no extrusion) to tower 2, laps it, and so on around the ring. Rotation is the
  cooling strategy: a d14 tower alone gets its next lap after 0.9s (still molten -> slag);
  in a 4-rotation each tower gets ~4-5s. Every RUNG_EVERY laps the hop is replaced by a
  BRIDGE: the strand extrudes straight across the gap, anchored on both tower rims — the
  throw-and-land vocabulary at fixed height. Rungs are doubled (two consecutive laps) so the
  second pass rides the first.

What the plate answers (all UNKNOWN until printed):
  * do rotated towers stay crisp at ~4.5s revisit, 230C, 20% fan — or slump/slag?
  * do 28mm air rungs anchored on d14 rims hold — or sag/drop?
  * does a 4-tower arcade with doubled rungs every 6mm feel RIGID?

Full flow at the north star everywhere: bead 2.0x0.6 at 50 mm/s = 60 mm3/s (R8: no derate).
Hops are G0, lifted above everything standing, flow suspended — the sequential-plate rules.
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--towers", type=int, default=4)
    ap.add_argument("--tower-d", type=float, default=10.0,
                    help="tower diameter, mm — Oleg: 'towers does not need to be this thick'")
    ap.add_argument("--ring-r", type=float, default=30.0, help="tower centres sit on this radius")
    ap.add_argument("--height", type=float, default=35.0)
    ap.add_argument("--laps-per-visit", type=int, default=5,
                    help="helix laps per tower visit before the flowing transit to the next")
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
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
    cx, cy = bx / 2.0, by / 2.0
    R = a.ring_r
    r_t = a.tower_d / 2.0
    N = a.towers

    centres = [(cx + R * math.cos(2*math.pi*k/N), cy + R * math.sin(2*math.pi*k/N))
               for k in range(N)]
    # each tower's lap starts/ends at the point FACING THE NEXT tower, so a rung is a straight
    # chord from exit point to the next tower's entry point
    def rim_point(k, toward):
        tx, ty = centres[k]; ox, oy = centres[toward]
        d = math.hypot(ox-tx, oy-ty)
        return (tx + r_t*(ox-tx)/d, ty + r_t*(oy-ty)/d)

    A = math.pi * (1.75/2)**2
    e_per_mm = bw * lh / A
    f = round(speed * 60)
    seg = max(0.25, speed / 250.0)
    n_lap = max(24, int(2*math.pi*r_t / seg))
    laps = max(2, int(round((a.height - machine.PRESS_HARD) / lh)))
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)

    L = []; w = L.append
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh}")
    w(f"; FLOW={bw*lh*speed:.4f}")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w(f"; SEQUENTIAL={N} towers rising in rotation, lifted hops between")
    w("; ARGV: " + " ".join(sys.argv))
    w(f"; towers x{N} d{a.tower_d:g} on r{R:g}, h{a.height:g}, {a.laps_per_visit} laps/visit, bridges front/center/back")
    w(f"; ARCH_LIFT={lh:.3f}")   # helical: Z varies within a lap by design
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {laps}"); w("; HEADER_BLOCK_END")
    w("M82")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M104 S{temp}")
    w("G28")
    w(f"M190 S{machine.bed_start(a.material, machine.bed_for(a.material, a.printer)):.0f}")
    w(f"M140 S{machine.bed_for(a.material, a.printer):.0f}")
    w(f"M109 S{temp}")
    w("G92 E0")
    px0, py0 = 20.0, 20.0
    w(f"G1 Z{machine.PRESS_HARD:.3f} F600")
    w(f"G0 F9000 X{px0:.3f} Y{py0:.3f}")
    w("G1 E20 F300                      ; PRIME stationary purge")
    w(f"G1 F1200 X{px0+40:.3f} Y{py0:.3f} E30   ; PRIME line, in the clear")
    w(f"G0 F3000 X{px0+52:.3f} Y{py0+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    w("; BODY_START")

    e = 0.0
    qx = qy = qz = None

    def circle_pts(k, radius, start_xy=None):
        """Ring on tower k starting at the angle of start_xy (or facing the next tower)."""
        tx, ty = centres[k]
        if start_xy is None:
            start_xy = rim_point(k, (k+1) % N)
        a0 = math.atan2(start_xy[1] - ty, start_xy[0] - tx)
        return [(tx + radius*math.cos(a0 + 2*math.pi*i/n_lap),
                 ty + radius*math.sin(a0 + 2*math.pi*i/n_lap)) for i in range(n_lap + 1)]

    def emit_path(pts, z0, z1, first=False):
        """One stroke, Z sliding z0->z1 along it, E on 3D length."""
        nonlocal e, qx, qy, qz
        total = sum(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
                    for i in range(len(pts)-1)) or 1.0
        run = 0.0
        if first:
            w(f"G0 F9000 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; PRIME-TRAVEL")
            w(f"G1 F1800 Z{z0:.3f}")
            w(f"G1 F{f}")
            qx, qy, qz = pts[0][0], pts[0][1], z0
        for X, Y in pts[1:] if first else pts:
            d = math.hypot(X - qx, Y - qy)
            if d < 0.02:
                continue
            run += d
            Z = z0 + (z1 - z0) * min(run / total, 1.0)
            d3 = math.hypot(d, Z - qz)
            e += d3 * e_per_mm
            w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}")
            qx, qy, qz = X, Y, Z

    def hop(k, z_to, z_clear):
        """Lifted travel to tower k's rim entry, flow suspended — the sequential-plate rules."""
        nonlocal qx, qy, qz
        w(f"G0 Z{z_clear:.3f} F1800   ; HOP lift, clear of everything standing")
        hx, hy = rim_point(k, (k+1) % N)
        w(f"G0 X{hx:.3f} Y{hy:.3f} F{travel_f}   ; HOP over to tower {k+1}")
        w(f"G0 Z{z_to:.3f} F1800")
        w(f"G1 F{f}")
        qx, qy, qz = hx, hy, z_to

    # ---- LAYER 1: pressed feet — 3 concentric rings per tower, outer->inner, hop between ----
    w("M107                              ; feet are layer 1: no cooling")
    Z1 = machine.PRESS_HARD
    for k in range(N):
        for j, rad in enumerate((r_t + 2*bw, r_t + bw, r_t)):
            pts = circle_pts(k, rad)
            if k == 0 and j == 0:
                emit_path(pts, Z1, Z1, first=True)
            else:
                if j == 0:
                    hop(k, Z1, Z1 + 1.5)
                emit_path(pts, Z1, Z1)
    w("M106 S51                          ; body fan 20% from layer 2")

    # ---- CONTINUOUS-FLOW ROTATION. Oleg, 2026-07-27: "so you start with one tower, give it
    # 5 layers then without stoping the flow you get to other tower, 5 layers, and so on."
    # No hops after the feet: the transit to the next tower is EXTRUDED —
    #   flat chord ACROSS the finished tower's open bore (rim top to rim top, air over the
    #   tube void — descending here would plough the far rim, so it stays level), then a
    #   descending flight across the gap, landing on the next tower's rim exactly k*lh lower
    #   (that is the steady-state stagger: each tower is one visit behind its predecessor).
    # The landing gets buried under the next k laps — a mechanical lock, not just a weld —
    # which is the ROTUNDA construction the ideation review endorsed. Transit slats stack
    # k*lh apart between the same tower pair and become the bridges.
    # THREE BRIDGE POSITIONS — Oleg: "you can have 3 bridges on each tower level frond,
    # center and back". Under the never-stop-flow stagger they cannot share one exact level
    # (a level strand toward a taller tower flies into its standing wall), so the bridge
    # azimuth CYCLES per rotation: front tangent (+90°), center chord (0°), back tangent
    # (-90°). Every tower pair accumulates all three positions every three visits, k*lh
    # apart — a triple-laced colonnade. The helix starts wherever the incoming flight landed;
    # a short extruded rim walk at the top re-aims the launch when the azimuth changes.
    kpv = a.laps_per_visit
    OFFS = (math.pi / 2, 0.0, -math.pi / 2)   # front, center, back
    z = [Z1] * N
    done = [0] * N
    k = 0
    rot = 0                                # completed rotations -> azimuth index
    start_at = [None] * N                  # where each tower's next helix starts
    n_bridge = 0
    while min(done) < laps:
        take = min(kpv, laps - done[k])
        for _ in range(take):
            pts = circle_pts(k, r_t, start_at[k])
            emit_path(pts, z[k], z[k] + lh)
            z[k] += lh
            done[k] += 1
            start_at[k] = pts[0]
        nxt = (k + 1) % N
        if min(done) >= laps:
            break
        # THREE CONNECTIONS PER LEVEL — Oleg, after v2 printed well: "lets try 3 connections
        # per level. 5up other back other 5up continue so". The weave per gap: fly DOWN on the
        # front line, rim-walk the lower tower, climb BACK up the center line (the ascending
        # strand lands on the taller tower's exposed rim top — the nozzle tip grazes only the
        # rim corner on approach), rim-walk the top, fly DOWN again on the back line. Ends on
        # the lower tower, which then takes its 5 laps.
        tx, ty = centres[k]; ox, oy = centres[nxt]
        du = math.hypot(ox - tx, oy - ty)
        ux, uy = (ox - tx) / du, (oy - ty) / du
        px_, py_ = -uy, ux

        def a_pt(off):
            return (tx + r_t*(ux*math.cos(off) + px_*math.sin(off)),
                    ty + r_t*(uy*math.cos(off) + py_*math.sin(off)))

        def b_pt(off):
            return (ox + r_t*(-ux*math.cos(off) + px_*math.sin(off)),
                    oy + r_t*(-uy*math.cos(off) + py_*math.sin(off)))

        def rim_walk(cx_, cy_, to, zlvl):
            nonlocal e, qx, qy, qz
            aw0 = math.atan2(qy - cy_, qx - cx_)
            aw1 = math.atan2(to[1] - cy_, to[0] - cx_)
            daw = (aw1 - aw0 + math.pi) % (2*math.pi) - math.pi
            steps = max(1, int(abs(daw) * r_t / seg))
            for i in range(1, steps + 1):
                aa = aw0 + daw * i / steps
                X, Y = cx_ + r_t*math.cos(aa), cy_ + r_t*math.sin(aa)
                d = math.hypot(X - qx, Y - qy)
                if d < 0.02:
                    continue
                e += d * e_per_mm
                w(f"G1 X{X:.3f} Y{Y:.3f} Z{zlvl:.3f} E{e:.5f}   ; rim walk")
                qx, qy, qz = X, Y, zlvl

        def flight(to, zto, tag):
            nonlocal e, qx, qy, qz, n_bridge
            d3 = math.hypot(to[0] - qx, to[1] - qy, zto - qz)
            e += d3 * e_per_mm
            w(f"G1 X{to[0]:.3f} Y{to[1]:.3f} Z{zto:.3f} E{e:.5f}   ; BRIDGE {tag}, "
              f"{'drops' if zto < qz else 'CLIMBS'} {abs(qz - zto):.1f}")
            n_bridge += 1
            qx, qy, qz = to[0], to[1], zto

        FR, CE, BA = math.pi/2, 0.0, -math.pi/2
        rim_walk(tx, ty, a_pt(FR), z[k])          # to the front launch, on A's top
        flight(b_pt(FR), z[nxt], "front")          # down
        rim_walk(ox, oy, b_pt(CE), z[nxt])         # along B's top rim
        flight(a_pt(CE), z[k], "center")           # back UP to A's rim top
        rim_walk(tx, ty, a_pt(BA), z[k])           # along A's top rim
        flight(b_pt(BA), z[nxt], "back")           # down again — ends on B
        start_at[nxt] = b_pt(BA)
        if nxt == 0:
            rot += 1
        k = nxt

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{max(z) + 30:.1f} F900")
    w(f"G0 X{min(10.0, bx-10):.0f} Y{by-10:.0f} F9000")
    g = "\n".join(L) + "\n"

    grams = e * A * 1.24 / 1000.0
    mins = (e / e_per_mm) / speed / 60.0
    print(f"  {N} towers d{a.tower_d:g} on r{R:g}, {laps} laps to h{a.height:g}; "
          f"{n_bridge} flowing bridges cycling front/center/back "
          f"(~{2*R*math.sin(math.pi/N) - a.tower_d:.0f}mm air, dropping {a.laps_per_visit*lh:g})")
    print(f"  revisit cycle ~{N * (2*math.pi*r_t/speed + 0.7):.1f}s per tower "
          f"(lap {2*math.pi*r_t/speed:.1f}s + hop ~0.7s) — the cooling question the plate answers")
    print(f"  full flow {bw*lh*speed:.0f} mm3/s at {speed:g} mm/s; ~{grams:.0f} g, "
          f"~{mins:.0f} min extruding + hops")
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out,
                      f"towers_{a.printer}_x{N}_d{a.tower_d:g}_h{a.height:g}_T{temp:g}.gcode")
    machine.emit_gcode(fn, g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
