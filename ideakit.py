#!/usr/bin/env python3
"""IDEA KIT — a row of small alien-tech column samples to feel in the hand. Oleg 2026-07-30: "print
idea kit." Each sample is a short twisted fluted column with a DIFFERENT flute count / twist / depth,
so the form can be chosen by holding them side by side instead of from one render.

All samples rise TOGETHER, layer by layer, with lifted hops between them (the towers.py rotation: safe
from head collisions by construction, and each sample cools ~N laps before its next). Cold bed, pressed
first lap. Small (default 35mm tall, ~26mm across) so the whole kit prints in one short job.

Usage:  python3 ideakit.py [--height 35] [--dia 26]
"""
import argparse, math, os, sys
import machine

VARIANTS = [   # (label, lobes, twist_deg_over_height, flute_depth_mm)
    ("straight-6",  6,   0.0, 4.0),   # fluted, no twist — the classical column
    ("twist-6",     6, 180.0, 4.0),   # the current leg render
    ("twist-8",     8, 360.0, 3.0),   # finer flutes, full turn
    ("bold-4",      4, 120.0, 5.5),   # few bold flutes
    ("subtle-12",  12,  90.0, 1.8),   # many shallow flutes, near-round
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus")
    ap.add_argument("--material", default="pla-matte")
    ap.add_argument("--height", type=float, default=35.0)
    ap.add_argument("--dia", type=float, default=26.0, help="mean sample diameter")
    ap.add_argument("--gap", type=float, default=18.0, help="clear gap between samples")
    ap.add_argument("--bed", type=float, default=60, help="bed C; 0 = COLD (default, solar)")
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    flow = machine.flow_cap(a.material, a.printer)
    lh = a.layer_h
    bw = machine.bead_for_flow(flow, lh)
    speed = machine.speed_for_flow(flow, bw, lh)
    temp = 230
    f = round(speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    A_FIL = math.pi * (1.75 / 2) ** 2
    e_per_mm = bw * lh / A_FIL
    bed = min(a.bed, machine.BED_MAX.get(a.printer, machine.BED_MAX_DEFAULT)) if a.bed else 0

    bx, by = machine.BED[a.printer]
    Rm = a.dia / 2.0
    N = len(VARIANTS)
    pitch = a.dia + a.gap
    row_w = pitch * (N - 1)
    cy = by / 2.0
    centres = [(bx / 2.0 - row_w / 2.0 + k * pitch, cy) for k in range(N)]
    press_z = machine.PRESS_HARD
    laps = max(2, int(round((a.height - press_z) / lh)))
    n_lap = max(48, int(2 * math.pi * Rm / max(0.25, speed / 250.0)))
    twist_rate = [math.radians(v[2]) / a.height for v in VARIANTS]

    def profile_pts(k, z, start_angle):
        """A lobed, twisting ring for sample k at height z, starting near start_angle."""
        tx, ty = centres[k]
        _, lobes, _, flute = VARIANTS[k]
        pts = []
        for i in range(n_lap + 1):
            th = start_angle + 2 * math.pi * i / n_lap
            r = Rm + flute * 0.5 * math.cos(lobes * (th - twist_rate[k] * z))
            pts.append((tx + r * math.cos(th), ty + r * math.sin(th)))
        return pts

    L = []; w = L.append
    w("; IDEA KIT — alien-tech column samples, varied flutes/twist, rise together for hand comparison")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; FLOW={bw*lh*speed:.4f}")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={press_z:g}")
    w(f"; ARCH_LIFT={lh:.3f}")     # helical: Z varies within a lap by design
    w(f"; SEQUENTIAL={N} samples rising in rotation, lifted hops between")
    w("; kit: " + " | ".join(f"{v[0]}(L{v[1]},{v[2]:g}deg,f{v[3]:g})" for v in VARIANTS))
    w("; ARGV: " + " ".join(sys.argv))
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {laps}"); w("; HEADER_BLOCK_END")
    w("M82")
    if bed > 0:
        w(f"M140 S{bed:.0f}"); w(f"M104 S{temp}")
        _wait = bed if a.printer == "k2plus" else machine.bed_start(a.material, bed)
        w(f"M190 S{_wait:.0f}")
    else:
        w("M140 S0                          ; COLD BED — solar run, no bed heat, no M190 wait")
        w(f"M104 S{temp}")
    w(f"M109 S{temp}")
    w("G28")
    w("SET_GCODE_OFFSET Z=-0.05")
    w("M106 S0")
    w("G92 E0")
    px0, py0 = 20.0, 16.0
    w(f"G1 Z{press_z:.3f} F600")
    w(f"G0 F9000 X{px0:.3f} Y{py0:.3f}")
    w("G1 E18 F300                      ; PRIME stationary purge")
    w(f"G1 F1200 X{px0+40:.3f} Y{py0:.3f} E28   ; PRIME line")
    w(f"G0 F3000 X{px0+52:.3f} Y{py0+12:.3f}  ; PRIME break-off wipe")
    w("G92 E0")
    w("; BODY_START")

    e = 0.0
    qx = qy = qz = None
    clear_z = a.height + 5.0

    def emit_ring(pts, z0, z1):
        nonlocal e, qx, qy, qz
        total = sum(math.hypot(pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]) for i in range(len(pts)-1)) or 1.0
        run = 0.0
        for (X, Y) in pts:
            d = math.hypot(X - qx, Y - qy) if qx is not None else 0.0
            if qx is not None and d < 0.02:
                continue
            run += d
            Z = z0 + (z1 - z0) * min(run / total, 1.0)
            if qx is None:
                qx, qy, qz = X, Y, z0
                continue
            d3 = math.hypot(d, Z - qz)
            e += d3 * e_per_mm
            w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}")
            qx, qy, qz = X, Y, Z

    # first: travel to sample 0 start (the one licensed pre-extrusion move)
    p0 = profile_pts(0, 0.0, 0.0)
    w(f"G0 F9000 X{p0[0][0]:.3f} Y{p0[0][1]:.3f} ; PRIME-TRAVEL to kit start")
    w(f"G1 F600 Z{press_z:.3f}")
    w(f"G1 F{f}")
    qx, qy, qz = p0[0][0], p0[0][1], press_z

    start_ang = [0.0] * N
    for lap in range(laps):
        z0 = press_z + lap * lh
        z1 = press_z + (lap + 1) * lh if lap > 0 else press_z   # lap 0 flat pressed
        if lap == 0:
            z1 = press_z
        for k in range(N):
            pts = profile_pts(k, z0 - press_z, start_ang[k])
            if not (lap == 0 and k == 0):
                # lifted hop to this sample's ring start (flow suspended — sequential-plate rule)
                w(f"G0 Z{clear_z:.3f} F1800   ; HOP lift clear of all samples")
                w(f"G0 F{travel_f} X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; HOP to {VARIANTS[k][0]}")
                w(f"G1 F600 Z{z0:.3f}")
                w(f"G1 F{f}")
                qx, qy, qz = pts[0][0], pts[0][1], z0
            emit_ring(pts, z0, z1)
            start_ang[k] += 2 * math.pi / n_lap * 0.37   # drift the seam so it doesn't stack

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{clear_z+10:.0f} F900")
    w("G0 X10 Y10 F9000")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"ideakit_{a.printer}_h{a.height:g}_x{N}_T{temp:g}.gcode")
    open(fn, "w").write("\n".join(L) + "\n")
    print(fn)
    print(f"  idea kit: {N} samples ({', '.join(v[0] for v in VARIANTS)}), h{a.height:g}, cold bed")


if __name__ == "__main__":
    main()
