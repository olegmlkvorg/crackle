#!/usr/bin/env python3
"""MULTIWALL LEG — a twisted-clover printer-stand leg with 2-3 concentric perimeters.

THE FIX THIS IS. spiraltower.py draws the same fluted twisted column as ONE 1.2mm wall. Above
~5 layers a single unsupported 1.2mm wall, 40mm+ tall, has no lateral rigidity: it FLEXES away
from the nozzle, the bead lands short of the layer below, and the layers stop bonding. A slicer's
NORMAL mode beats vase mode here for exactly one reason — it lays 2-3 perimeters that touch and
fuse SIDEWAYS, so the wall becomes a rigid N x bead-wide box section that cannot flex. Everything
else about our single-wall settings (flow, bead, fan, temp, press) already matches or beats the
slicer; the missing ingredient is the walls.

GEOMETRY. Same profile as spiraltower — a lobed cross-section that rotates (twists) with height:
    r(wall, theta, z) = (Rm - wall*bw) + flute/2 * cos( lobes * (theta - twist_rate*z) )
The cos term is identical on every wall, so wall k and wall k+1 sit EXACTLY one bead apart at every
azimuth (the difference is a constant bw). Nested clovers, one bead apart, so adjacent beads fuse
into one thick clover tube wall.

PATH. Layer by layer (NOT a helix — concentric walls cannot be a single vase-mode spiral). Each
layer prints its N closed clover loops joined by short RADIAL EXTRUDING links (never travels), then
steps Z by one layer height at the seam. The wall order ALTERNATES — outer->inner on even layers,
inner->outer on odd — so every layer starts on the exact wall the previous one ended on: the whole
part is one continuous extrusion with a bare Z lift in place at the seam and no travel anywhere.
The links stack at the seam azimuth into a small radial rib that ties the walls together — extra
lateral bond, not a defect.

REUSES spiraltower's proven, validate-passing choices: bead 1.2 x layer 0.4 accurate on the 0.8
nozzle, squish 1.0 (hard squish just BENDS a thin wall — bond by heat + the touching neighbour,
not pressure), bed 60, pressed first layer at 0.1, FLOW / FLOW_DERATE stamps so R8 passes at low
flow. Default --speed 25 (a multi-wall box section bonds fine faster than single-wall's 12.5;
override freely). Render first, do not print.

Usage:  python3 multiwall_leg.py --walls 3 --dia 64 --lobes 4 --flute 13.5 --twist 48 \
                 --height 40 --bead 1.2 --layer-h 0.4 --bed 60
        (--walls 1 = a single-wall clover, laid layer-by-layer; 2-3 = the rigidity fix)
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus")
    ap.add_argument("--material", default="pla-matte")
    ap.add_argument("--height", type=float, default=40.0, help="leg height mm")
    ap.add_argument("--dia", type=float, default=64.0, help="mean column diameter mm (outer wall)")
    ap.add_argument("--lobes", type=int, default=4, help="number of flutes around")
    ap.add_argument("--flute", type=float, default=13.5, help="flute depth mm (peak-to-valley radius swing)")
    ap.add_argument("--twist", type=float, default=48.0, help="degrees the flutes rotate over full height")
    ap.add_argument("--walls", type=int, default=1,
                    help="concentric perimeters, one bead apart. 1 = single wall (flexes tall); "
                         "2-3 = the rigidity fix (walls bond laterally into a box section)")
    ap.add_argument("--bed", type=float, default=60,
                    help="bed C, default 60 (PLA rated 50-70). 0 = cold, no M190 wait.")
    ap.add_argument("--layer-h", type=float, default=0.4)
    ap.add_argument("--bead", type=float, default=1.2,
                    help="bead WIDTH mm. 1.2 = 1.5x the 0.8 nozzle, the width it places ACCURATELY. "
                         "Wall-to-wall spacing equals this, so adjacent walls touch and fuse.")
    ap.add_argument("--squish", type=float, default=1.0,
                    help="extrusion multiplier. Keep ~1.0: a multi-wall section is rigid, so it does "
                         "not need over-feed to fight flex, and hard squish still lands beads tall.")
    ap.add_argument("--speed", type=float, default=25.0,
                    help="mm/s override. A bonded multi-wall section carries heat and does not flex, "
                         "so it bonds fine at 25 where single-wall wanted 12.5. Never above the 50 north star.")
    ap.add_argument("--ppl", type=int, default=180, help="points per wall loop (lobe smoothness)")
    ap.add_argument("--link-flow", type=float, default=0.3,
                    help="wall-to-wall connectors run at this fraction of a bead. The connector "
                         "crosses ground the two touching walls already cover, so a full bead there "
                         "doubles the height and ploughs next layer (solid.py, 0.3). Thin keeps the "
                         "path continuous without building a seam ridge.")
    ap.add_argument("--seam-turns", type=float, default=2.0,
                    help="turns the SEAM azimuth rotates over the full height. A fixed seam (0) stacks "
                         "the loop-closure + reseat + wall-links at one azimuth into a visible scar "
                         "COLUMN (Oleg 2026-07-30, measured: every layer started at theta=0). Rotating "
                         "the seam spreads that scar into a gentle spiral so no misaligned column builds. "
                         "The inter-layer reseat stays on the same wall (alternation), so it is just a "
                         "short azimuthal arc; on a full-height leg the per-layer arc is < a bead.")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    lh = a.layer_h
    bw = a.bead
    speed = min(a.speed, machine.DEFAULT_SPEED)     # never above the north star
    flow = bw * lh * a.squish * speed               # actual volumetric flow, squish included
    temp = machine.temp_for(a.material)             # pla-matte -> 230
    f = round(speed * 60)
    A_FIL = math.pi * (1.75 / 2) ** 2
    e_mm = bw * lh * a.squish / A_FIL
    bed = min(a.bed, machine.BED_MAX.get(a.printer, machine.BED_MAX_DEFAULT)) if a.bed else 0

    cx, cy = 175.0, 175.0
    Rm = a.dia / 2.0
    N = max(1, a.walls)
    layers = int(round(a.height / lh))
    twist_rate = math.radians(a.twist) / a.height    # rad of profile phase per mm of height
    PPL = a.ppl

    # peak lateral shift per layer — consecutive layers must overlap (< one bead) to bond
    r_peak = Rm + a.flute * 0.5
    peak_shift = r_peak * twist_rate * lh

    def radius(wall, theta, zc):
        # lobed profile that rotates (twists) with height; identical cos term on every wall so
        # walls stay EXACTLY one bead apart (their radii differ by a constant wall*bw)
        return (Rm - wall * bw) + a.flute * 0.5 * math.cos(a.lobes * (theta - twist_rate * zc))

    L = []
    w = L.append
    w("; MULTIWALL LEG — twisted fluted clover, N concentric perimeters bonded laterally for rigidity")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w(f"; walls {N} dia {a.dia:g} lobes {a.lobes} flute {a.flute:g} twist {a.twist:g}deg "
      f"bead {bw:g}x{lh:g} — concentric clover perimeters one bead apart, alternating in/out per layer")
    w(f"; seam spirals {a.seam_turns:g} turn(s) over the height (rotating seam azimuth) so the "
      f"loop-closure + wall-links do not stack into a fixed scar column")
    w(f"; peak twist shift {peak_shift:.3f}mm/layer (must be < one bead {bw:g} to bond layer-to-layer)")
    w(f"; SPEED={speed:.4f}")
    w(f"; FLOW={flow:.4f}")
    _cap = machine.flow_cap(a.material, a.printer)
    if _cap and flow < 0.8 * _cap:
        w(f"; FLOW_DERATE=multiwall bead {bw:g}x{lh:g} x{a.squish:g} squish on the 0.8 nozzle; "
          f"{flow:g} of {_cap:g} mm3/s is a DELIBERATE accuracy+bonding choice at {speed:g} mm/s, "
          f"not a flow ceiling. {N} concentric walls bond LATERALLY into a rigid box section — the "
          f"rigidity a single {bw:g}mm wall lacks — so the layers fuse without over-fed squish.")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {layers}"); w("; HEADER_BLOCK_END")
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
    w("M106 S0                              ; no cooling — heat drives the layer weld")
    w("G92 E0")

    # prime off in the corner, then travel to the leg start ONCE (the one licensed pre-extrusion move)
    px, py = 20.0, 16.0
    w(f"G1 F600 Z{machine.PRESS_HARD:.3f}")
    w(f"G0 F9000 X{px:.3f} Y{py:.3f}")
    w("G1 E18 F300                          ; PRIME stationary purge")
    w(f"G1 F1200 X{px+40:.3f} Y{py:.3f} E28  ; PRIME line")
    w(f"G0 F3000 X{px+52:.3f} Y{py+12:.3f}   ; PRIME break-off wipe")
    w("G92 E0")
    w("; BODY_START")

    E = 0.0
    q = [None, None, None]     # current head position (x, y, z)

    def loop_points(wall, zc, theta0=0.0):
        """Closed clover loop for one wall at structural height zc; starts and ends at the seam
        azimuth theta0 (rotates per layer so the seam spirals instead of stacking a scar column)."""
        pts = []
        for i in range(PPL + 1):
            th = theta0 + 2 * math.pi * i / PPL
            r = radius(wall, th, zc)
            pts.append((cx + r * math.cos(th), cy + r * math.sin(th)))
        return pts

    def ext_to(x, y, z, tag="", flow_mul=1.0):
        nonlocal E
        d = math.hypot(x - q[0], y - q[1])
        d3 = math.hypot(d, z - q[2])
        if d3 < 1e-6:
            return
        E += d3 * e_mm * flow_mul
        line = f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} E{E:.5f}"
        if tag:
            line += f"   ; {tag}"
        w(line)
        q[0], q[1], q[2] = x, y, z

    # FIRST LAYER at the 0.10 press height (R1). Bare Z so validate reads it as layer 1, then the
    # ONE licensed travel to the leg's outer seam, then flow on.
    z0 = machine.PRESS_HARD
    start = loop_points(0, 0.0)[0]
    w(f"G1 F600 Z{z0:.3f}")
    w(f"G0 F9000 X{start[0]:.3f} Y{start[1]:.3f} ; PRIME-TRAVEL to leg start")
    w(f"G1 F{f}")
    q[0], q[1], q[2] = start[0], start[1], z0

    seam_step = a.seam_turns * 2 * math.pi / max(1, layers)   # seam azimuth advance per layer
    for Lidx in range(layers):
        zc = Lidx * lh                                 # structural height (for twist phase)
        z = machine.PRESS_HARD + Lidx * lh             # absolute Z
        theta0 = seam_step * Lidx                       # this layer's seam azimuth (spirals up)
        outward = (Lidx % 2 == 1)                      # even: outer->inner, odd: inner->outer
        order = range(N - 1, -1, -1) if outward else range(0, N)
        if Lidx > 0:
            # step to this layer's Z, lifting in place where the last layer ended. Bare Z (F
            # persists) so R2 reads the ladder; the first extrude then walks the seam arc to theta0.
            w(f"G1 Z{z:.3f}")
            q[2] = z
        first = True
        for wall in order:
            pts = loop_points(wall, zc, theta0)
            # first wall: the seam-reseat continues the same wall the previous layer ended on
            # (full flow). Subsequent walls: a THIN radial LINK across ground the touching walls
            # already cover — full flow there would build a seam ridge and plough next layer.
            if first:
                ext_to(pts[0][0], pts[0][1], z, tag="seam")
            else:
                ext_to(pts[0][0], pts[0][1], z, tag="LINK thin (wall-to-wall bond)", flow_mul=a.link_flow)
            for X, Y in pts[1:]:
                ext_to(X, Y, z)
            first = False

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{z + 15:.0f} F900")
    w("G0 X10 Y10 F9000")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"multiwall_{a.printer}_w{N}_h{a.height:g}_d{a.dia:g}_L{a.lobes}_T{temp:g}.gcode")
    open(fn, "w").write("\n".join(L) + "\n")
    print(fn)
    grams = E * A_FIL * 1.24 / 1000.0
    mins = (E / e_mm) / speed / 60.0
    print(f"  {N}-wall twisted clover h{a.height:g} dia {a.dia:g}, {a.lobes} flutes, {a.twist:g}deg twist, "
          f"{layers} layers, bed {bed:g}" + ("C" if bed else " (cold)"))
    print(f"  peak twist shift {peak_shift:.3f}mm/layer "
          + ("OK (< bead)" if peak_shift < bw else f"!! EXCEEDS bead {bw:g} — layers may not bond"))
    print(f"  flow {flow:.1f} mm3/s at {speed:g} mm/s; ~{grams:.0f} g, ~{mins:.0f} min extruding "
          f"(run validate.py for the checked print time)")
    if peak_shift >= bw:
        print("  WARNING: reduce --twist or --layer-h so the twist shift is under one bead.")


if __name__ == "__main__":
    main()
