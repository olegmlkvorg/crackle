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
    ap.add_argument("--tower-d", type=float, default=14.0, help="tower diameter, mm")
    ap.add_argument("--ring-r", type=float, default=30.0, help="tower centres sit on this radius")
    ap.add_argument("--height", type=float, default=35.0)
    ap.add_argument("--rung-every", type=int, default=10, help="bridge rung every N laps")
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
    w(f"; towers x{N} d{a.tower_d:g} on r{R:g}, h{a.height:g}, rung every {a.rung_every} laps")
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

    def circle_pts(k, radius, start_toward):
        tx, ty = centres[k]
        sx, sy = rim_point(k, start_toward) if radius == r_t else (tx + radius, ty)
        a0 = math.atan2(sy - ty, sx - tx)
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
            pts = circle_pts(k, rad, (k+1) % N)
            if k == 0 and j == 0:
                emit_path(pts, Z1, Z1, first=True)
            else:
                if j == 0:
                    hop(k, Z1, Z1 + 1.5)
                emit_path(pts, Z1, Z1)
    w("M106 S51                          ; body fan 20% from layer 2")

    # ---- TOWERS RISE IN ROTATION: one helix lap each, lifted hop on ----
    # RUNGS ARE A SAME-HEIGHT CIRCUIT after the whole rotation tops out (all towers equal):
    # gap bridge -> chord ACROSS the next tower's open bore -> gap bridge -> ... Every anchor
    # is a rim TOP at the circuit's own height, so the circuit never extrudes under material
    # (the first cut walked each rim one layer up and then printed the lap underneath it —
    # 922 dives, validate caught it). Bore chords are <= tower_d of air anchored on both rim
    # sides; the tube is hollow, there is nothing beneath to plough.
    z = [Z1] * N                          # current top of each tower
    for lap in range(1, laps):
        for k in range(N):
            pts = circle_pts(k, r_t, (k+1) % N)
            emit_path(pts, z[k], z[k] + lh)
            z[k] += lh
            nxt = (k + 1) % N
            if k < N - 1:
                hop(nxt, z[nxt], max(z) + 2.0)
        if lap % a.rung_every == 0 and 2 < lap < laps - 1:
            zt = z[0]                     # all towers top out equal after a full rotation
            w(f"; RUNG circuit at Z{zt:.1f} — gaps + bore chords, all anchors are rim tops")
            for k in range(N - 1, 2 * N - 1):
                cur = k % N
                nxt = (k + 1) % N
                # gap bridge: exit rim of cur -> near rim of nxt (air)
                gx, gy = rim_point(nxt, cur)
                d3 = math.hypot(gx - qx, gy - qy)
                e += d3 * e_per_mm
                w(f"G1 X{gx:.3f} Y{gy:.3f} Z{zt:.3f} E{e:.5f}   ; RUNG gap bridge")
                qx, qy, qz = gx, gy, zt
                # bore chord: straight across the open tube to its exit rim point (air)
                ex, ey = rim_point(nxt, (nxt + 1) % N)
                d3 = math.hypot(ex - qx, ey - qy)
                e += d3 * e_per_mm
                w(f"G1 X{ex:.3f} Y{ey:.3f} Z{zt:.3f} E{e:.5f}   ; RUNG bore chord")
                qx, qy = ex, ey
            # circuit ends at tower N-1's exit; hop to tower 0 for the next rotation
            if lap < laps - 1:
                hop(0, z[0], max(z) + 2.0)
        elif lap < laps - 1:
            hop(0, z[0], max(z) + 2.0)

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{max(z) + 30:.1f} F900")
    w(f"G0 X{min(10.0, bx-10):.0f} Y{by-10:.0f} F9000")
    g = "\n".join(L) + "\n"

    grams = e * A * 1.24 / 1000.0
    mins = (e / e_per_mm) / speed / 60.0
    n_rungs = sum(1 for lap in range(1, laps) if (lap % a.rung_every in (0, 1)) and lap > 2) * N
    print(f"  {N} towers d{a.tower_d:g} on r{R:g}, {laps} laps to h{a.height:g}; "
          f"{n_rungs} rung bridges (~{2*R*math.sin(math.pi/N) - a.tower_d:.0f}mm air each)")
    print(f"  revisit cycle ~{N * (2*math.pi*r_t/speed + 0.7):.1f}s per tower "
          f"(lap {2*math.pi*r_t/speed:.1f}s + hop ~0.7s) — the cooling question the plate answers")
    print(f"  full flow {bw*lh*speed:.0f} mm3/s at {speed:g} mm/s; ~{grams:.0f} g, "
          f"~{mins:.0f} min extruding + hops")
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out,
                      f"towers_{a.printer}_x{N}_d{a.tower_d:g}_h{a.height:g}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
