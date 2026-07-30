#!/usr/bin/env python3
"""SPIRAL DISC — a round merge coupon. Oleg 2026-07-30: "why square again wtf? also lines still not
overlapping always" + "extrude at max flow, put lines closer".

WHY ROUND, not a square tile: a square forces corner slowdowns, and a varying speed makes a varying
bead width, so overlap is inconsistent ("not always"). A continuous Archimedean spiral has NO corners:
one constant speed, one constant bead width, so adjacent passes overlap CONSISTENTLY. Round is both the
alien-tech look and the technical fix for the merge.

The merge levers, both applied:
  1. LINES CLOSER: spiral pitch = bead_width * OVERLAP (default 0.70 = 30% overlap).
  2. MAX FLOW: each mm of path lays a full bead of material into a lane 30% narrower, so the bead is
     over-fed and squishes sideways into its neighbour. No gap can survive.

Cold bed (solar). Press first layer (0.1) for adhesion, then body layers show the merged top surface.

Usage:  python3 spiraldisc.py [--dia 70] [--layers 3] [--overlap 0.70] [--printer k2plus]
"""
import argparse, math, os
import machine

A_FIL = math.pi * (1.75 / 2) ** 2      # 1.75mm filament cross-section, mm^2


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus")
    ap.add_argument("--material", default="pla-matte")
    ap.add_argument("--dia", type=float, default=70.0, help="disc diameter mm")
    ap.add_argument("--layers", type=int, default=3, help="total layers (1 press + rest body)")
    ap.add_argument("--overlap", type=float, default=0.78,
                    help="spiral pitch as fraction of bead width. 0.78 = 22%% overlap (fill 1.28x, under "
                         "the R4b 1.35 shear limit, merges reliably on a constant-speed round spiral). "
                         "1.0 = butt joint (gaps). Lower = more overlap but risks over-fill/shear.")
    ap.add_argument("--bed", type=float, default=0, help="bed C; 0 = COLD (default, solar)")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    flow = machine.flow_cap(a.material, a.printer)          # 60
    lh = 0.6
    bw = machine.bead_for_flow(flow, lh)                    # 2.0
    speed = machine.speed_for_flow(flow, bw, lh)            # 50
    temp = machine.nozzle_temp(a.material) if hasattr(machine, "nozzle_temp") else 230
    f = round(speed * 60)
    bed = min(a.bed, machine.BED_MAX.get(a.printer, machine.BED_MAX_DEFAULT)) if a.bed else 0

    R = a.dia / 2.0
    cx, cy = 175.0, 175.0                                   # bed centre (K2 350)
    pitch = bw * a.overlap                                  # lines closer than a bead -> merge (uniform, all layers)
    e_mm = bw * lh / A_FIL                                  # full-bead material into a tight lane = over-fed -> squish/merge

    L = []
    w = L.append
    w("; SPIRAL DISC merge coupon — round, continuous BOUSTROPHEDON spiral (out/in/out, no travels),")
    w("; constant speed = constant bead width = CONSISTENT overlap. Oleg 07-30: round fixes the merge.")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w("; PRESSED_LAYER1=1                    ; layer 1 sits low (0.45) and over-extrudes to key into the cold plate")
    w(f"; dia {a.dia:g} layers {a.layers} overlap {a.overlap:g} (pitch {pitch:.2f} of bead {bw:.2f}) cold-bed")
    w(f"; SPEED={speed:.4f}")
    w(f"; FLOW={bw*lh*speed:.4f}")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {a.layers}"); w("; HEADER_BLOCK_END")
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
    w("SET_GCODE_OFFSET Z=-0.05             ; first-layer press insurance (K2 datum ~0.1 high)")
    w("M106 S0")
    w("G92 E0")

    # prime (stationary purge + wipe, off to the corner), then travel to centre
    px, py = 20.0, 16.0
    w(f"G1 F600 Z{machine.PRESS_HARD:.3f}")
    w(f"G0 F9000 X{px:.3f} Y{py:.3f}")
    w("G1 E18 F300                          ; PRIME stationary purge")
    w(f"G1 F1200 X{px+40:.3f} Y{py:.3f} E28  ; PRIME line")
    w(f"G0 F3000 X{px+52:.3f} Y{py+12:.3f}   ; PRIME break-off wipe")
    w("G92 E0")
    w("; BODY_START")

    # Build the spiral point list once (centre -> edge), then walk it OUT on even layers and
    # IN (reversed) on odd layers. The end of each layer is the start of the next, so there is
    # NO travel between layers: just a Z step at the turnaround. One continuous extrusion (R5).
    b = pitch / (2 * math.pi)                                # Archimedean r = b*theta
    theta_max = R / b
    pts = []
    theta = 0.0
    while theta < theta_max:
        r = b * theta
        pts.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
        theta += 0.8 / max(r, 0.5)                           # ~0.8mm arc segments
    pts.append((cx + R * math.cos(theta_max), cy + R * math.sin(theta_max)))

    # first layer sits slightly low for a cold-plate press (over-fed bead squishes wider + keys in)
    z0 = 0.45
    E = 0.0
    start = pts[0] if True else None
    # travel to the very first point ONCE (the one licensed pre-extrusion move)
    w(f"G1 F600 Z{z0:.3f}")
    w(f"G0 F9000 X{pts[0][0]:.3f} Y{pts[0][1]:.3f} ; PRIME-TRAVEL to spiral start")
    w(f"G1 F{f}")
    pxx, pyy = pts[0]
    for li in range(a.layers):
        z = z0 + li * lh
        seq = pts if li % 2 == 0 else list(reversed(pts))
        # step Z at the turnaround (no XY move — we're already at seq[0] from the previous layer's end)
        if li > 0:
            w(f"G1 F600 Z{z:.3f}")
            w(f"G1 F{f}")
        for (x, y) in seq:
            seg = math.hypot(x - pxx, y - pyy)
            if seg < 1e-6:
                continue
            E += seg * e_mm
            w(f"G1 X{x:.3f} Y{y:.3f} E{E:.4f}")
            pxx, pyy = x, y
    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{z+10:.0f} F900")
    w("G0 X10 Y10 F9000")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"spiraldisc_{a.printer}_d{a.dia:g}_ov{a.overlap:g}_T{temp:g}.gcode")
    open(fn, "w").write("\n".join(L) + "\n")
    print(fn)
    print(f"  round spiral disc dia {a.dia:g}, {a.layers} layers, pitch {pitch:.2f}mm "
          f"({int((1-a.overlap)*100)}% overlap), cold bed, constant {speed:g} mm/s")


if __name__ == "__main__":
    main()
