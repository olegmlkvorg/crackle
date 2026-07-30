#!/usr/bin/env python3
"""SPIRAL TOWER — an alien-tech printer-stand leg. Oleg 2026-07-30: "why square? alien tech, feel it."

A twisted fluted column: a lobed cross-section (like a fluted classical column) that ROTATES as it
rises, so the flutes spiral up the tower. One continuous vase-mode helix, no travels. Hollow, so it
fills with sand+gypsum for the damping mass (the print is the permanent mould). A bamboo rod drops
through the core as rebar and a visible spine.

Form, not a box: the spiral is the structure and the ornament at once. Same family as towers.py (the
spiral pillars Oleg called "perfect") and the rotunda, scaled to a load-bearing leg.

Cold bed (solar). Pressed first lap for adhesion. Single-bead wall (the mass, not the shell, bears load).

Usage:  python3 spiraltower.py [--height 180] [--dia 64] [--lobes 6] [--flute 4] [--twist 180]
        (--twist = degrees the profile rotates over the full height)
"""
import argparse, math, os
import machine


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus")
    ap.add_argument("--material", default="pla-matte")
    ap.add_argument("--height", type=float, default=180.0, help="tower height mm (one segment; stack for 600)")
    ap.add_argument("--dia", type=float, default=64.0, help="mean column diameter mm (bamboo + fill inside)")
    ap.add_argument("--lobes", type=int, default=6, help="number of flutes around")
    ap.add_argument("--flute", type=float, default=4.0, help="flute depth mm (peak-to-valley radius swing)")
    ap.add_argument("--twist", type=float, default=180.0, help="degrees the flutes rotate over full height")
    ap.add_argument("--bed", type=float, default=0, help="bed C; 0 = COLD (default, solar)")
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    flow = machine.flow_cap(a.material, a.printer)
    lh = a.layer_h
    bw = machine.bead_for_flow(flow, lh)
    speed = machine.speed_for_flow(flow, bw, lh)
    temp = 230
    f = round(speed * 60)
    A_FIL = math.pi * (1.75 / 2) ** 2
    e_mm = bw * lh / A_FIL
    bed = min(a.bed, machine.BED_MAX.get(a.printer, machine.BED_MAX_DEFAULT)) if a.bed else 0

    cx, cy = 175.0, 175.0
    Rm = a.dia / 2.0
    laps = int(round(a.height / lh))                 # one lap raises Z by lh
    twist_rate = math.radians(a.twist) / a.height    # rad of profile phase per mm of height
    PPL = 160                                         # points per lap (smooth lobes)

    def radius(theta, z):
        # lobed profile that rotates (twists) with height
        return Rm + a.flute * 0.5 * math.cos(a.lobes * (theta - twist_rate * z * 1.0))

    L = []
    w = L.append
    w("; SPIRAL TOWER — alien-tech stand leg: twisted fluted hollow column, one continuous helix")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w("; PRESSED_LAYER1=1                    ; first lap pressed low to key into the cold plate")
    w(f"; height {a.height:g} dia {a.dia:g} lobes {a.lobes} flute {a.flute:g} twist {a.twist:g}deg — fill sand+gypsum, bamboo core")
    w(f"; SPEED={speed:.4f}")
    w(f"; FLOW={bw*lh*speed:.4f}")
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
    w("SET_GCODE_OFFSET Z=-0.05             ; first-lap press insurance (K2 datum ~0.1 high)")
    w("M106 S0")
    w("G92 E0")

    # prime off in the corner, then travel to the tower start ONCE (the one licensed pre-extrusion move)
    px, py = 20.0, 16.0
    w(f"G1 F600 Z{machine.PRESS_HARD:.3f}")
    w(f"G0 F9000 X{px:.3f} Y{py:.3f}")
    w("G1 E18 F300                          ; PRIME stationary purge")
    w(f"G1 F1200 X{px+40:.3f} Y{py:.3f} E28  ; PRIME line")
    w(f"G0 F3000 X{px+52:.3f} Y{py+12:.3f}   ; PRIME break-off wipe")
    w("G92 E0")
    w("; BODY_START")

    # first point — first FULL lap is FLAT at the 0.10 press height (wide-bead key to the cold plate),
    # then the helix climbs lh per lap. R1 wants layer 1 pressed to 0.10.
    press_z = machine.PRESS_HARD                      # 0.10
    th = 0.0
    r0 = radius(th, 0.0)
    x0, y0 = cx + r0 * math.cos(th), cy + r0 * math.sin(th)
    w(f"G1 F600 Z{press_z:.3f}")
    w(f"G0 F9000 X{x0:.3f} Y{y0:.3f} ; PRIME-TRAVEL to tower start")
    w(f"G1 F{f}")

    E = 0.0
    pxx, pyy = x0, y0
    total_pts = laps * PPL
    for i in range(1, total_pts + 1):
        frac = i / PPL                                # laps completed (float)
        th = 2 * math.pi * frac
        # lap 1 flat at the press height; after that, climb lh per lap
        if frac <= 1.0:
            z = press_z
        else:
            z = press_z + (frac - 1.0) * lh
        r = radius(th, z - press_z)
        x, y = cx + r * math.cos(th), cy + r * math.sin(th)
        seg = math.hypot(x - pxx, y - pyy)
        if seg < 1e-6:
            continue
        E += seg * e_mm
        w(f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} E{E:.4f}")
        pxx, pyy = x, y

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{z+15:.0f} F900")
    w("G0 X10 Y10 F9000")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"spiraltower_{a.printer}_h{a.height:g}_d{a.dia:g}_L{a.lobes}_T{temp:g}.gcode")
    open(fn, "w").write("\n".join(L) + "\n")
    print(fn)
    print(f"  twisted fluted column h{a.height:g} dia {a.dia:g}, {a.lobes} flutes, {a.twist:g}deg twist, "
          f"{laps} laps, cold bed, ~{laps*PPL*bw*lh/ (speed*60) /60:.0f}? min")


if __name__ == "__main__":
    main()
