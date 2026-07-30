#!/usr/bin/env python3
"""ANTI-VIBRATION STAND — tabletop FORMWORK TILE (v0 skeleton). Oleg 2026-07-29: "i need a strong
table for both of my printers. real heavy to let them manage vibration ... printouts that i will
fill with sand and gypsum, and bambo sticks if necessary".

WHAT THIS IS. One bed-sized, open-top rectangular TRAY: a pressed solid floor that holds the fill,
plus a single-bead perimeter wall rising to the fill depth. Several of these BUTT together on the
stand's top frame; bamboo rebar is laid in the bottom and ONE continuous sand+gypsum pour over all
the butted trays sets into a single monolithic damping slab (the trays stay as permanent skin).
See guides/printer-stand.md for the full stand.

WHY A TILE AND NOT ONE SLAB. The K2 plate is 350x350 max, so a 640mm K2 tabletop cannot print in
one piece. It TILES: 2x2 of 320mm trays -> 640x640 (K2 stand); 2x2 of 200mm trays -> 400x400
(K1C stand). Each tray prints on the K2; the 200mm K1C trays also print on the K1C itself.

v0 SCOPE — deliberately the atomic unit only: a plain filled tray (pressed floor + rising wall),
one continuous stroke per layer, validated by validate.py. NOT YET (v1, noted in the guide):
  - internal stiffening ribs (also divide the fill and hold the rebar off the floor)
  - vertical registration pegs/sockets on the butt edges so tiles align
  - LOW internal seam walls vs FULL perimeter walls (so one pour merges the tiles into a monolith)
  - rebar locator nibs on the floor
These change the FORMWORK, not the stand's structure, and several are PROVISIONAL pending the
concept cup (stand.py) proving the pressed floor holds + adheres and the fill actually damps.

Prints pla-matte, bed 80, press 0.1, 50 mm/s north star, single-bead wall — the house doctrine."""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import stand_common as sc          # corner_samples() — shared sharp-corner detection

A_FIL = math.pi * (1.75 / 2) ** 2


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size", type=float, default=320.0, help="tile outer edge (square); K2=320, K1C=200")
    ap.add_argument("--size-y", type=float, default=None, help="tile Y edge if not square")
    ap.add_argument("--depth", type=float, default=60.0, help="fill depth = wall height above the floor")
    ap.add_argument("--fillet", type=float, default=12.0,
                    help="height of the FUSED floor->wall haunch (a tapering solid perimeter band "
                         "welds floor into wall over real height, not a single-bead rim seam that "
                         "peels — concept cup delaminated there 2026-07-29)")
    ap.add_argument("--wall-beads", type=int, default=3,
                    help="beads wide at the base of the fused haunch, tapering to 1 (the wall)")
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--out", default="out")
    ap.add_argument("--bed", type=float, default=0,
                    help="bed target C; 0 = COLD (default, solar — Oleg 2026-07-30: no bed heat unless "
                         "asked). Heat only on explicit request, e.g. --bed 120 for a thick filled tile "
                         "(big-footprint grip + less warp) when mains power is available)")
    # v1 FORMWORK DETAILS — where they landed, and why (spec's "still to write" list).
    #
    # --rod-channel is the ONE detail that is clean single-part geometry: a shallow perimeter
    # CHANNEL in the floor, one bead inboard of the haunch, that locates the bottom bamboo RING ROD
    # (rule 2) laid along the floor-wall corner. It is the floor fill skipping one ring — still one
    # continuous stroke — so it validates. Default OFF; the proven tile output is unchanged.
    #
    # The corner-ring-rod SEAT itself needs NO new geometry: the fused haunch already forms the
    # concave floor-wall corner the ring rod beds into. The channel just gives it a defined inboard lip.
    #
    # The other three (shiplap tile edges, LOW interior seam walls, raised rebar-grid nibs) are NOT
    # emitted, deliberately. Each needs a feature that either descends back onto the floor after the
    # wall is up, or gives one edge a different height than the spiral is climbing — and BOTH break a
    # hard validate.py machine-safety rule (Z-plough / floating-line on a non-sequential part; a
    # capped edge that the climbing spiral re-traces and grinds). Declaring the file sequential does
    # not rescue them: those features STACK on the tray, and the sequential overlap guard (correctly)
    # refuses one part deposited within 1.5mm of another. So they are handled at ASSEMBLY — which is
    # exactly what the spec says (rule 3 + the note "laid at assembly (rods + pour), not printed into
    # a single tile"): tiles BUTT, every seam is crossed by rebar, and one continuous pour + the
    # bamboo ties merge them into a monolith. The PLA is skin; the set gypsum + bamboo is structure.
    ap.add_argument("--rod-channel", action="store_true",
                    help="cut a shallow perimeter channel one bead inboard of the haunch to locate "
                         "the bottom bamboo ring rod (spec rule 2). Single-stroke, validates.")
    ap.add_argument("--rod-dia", type=float, default=6.35, help="bamboo rod diameter (1/4in)")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    flow = machine.flow_cap(a.material, a.printer)
    lh = a.layer_h
    bw = machine.bead_for_flow(flow, lh)               # 2.0 k2 / 1.5 k1c at pla-matte
    speed = machine.speed_for_flow(flow, bw, lh)       # 50
    temp = machine.temp_for(a.material)
    bed = (min(a.bed, machine.BED_MAX.get(a.printer, machine.BED_MAX_DEFAULT))
           if a.bed is not None else machine.bed_for(a.material, a.printer))
    bx, by = machine.BED[a.printer]
    sx = a.size
    sy = a.size_y if a.size_y else a.size

    if sx > bx - 6 or sy > by - 6:
        sys.exit(f"tile {sx:g}x{sy:g} does not fit the {a.printer} plate {bx:g}x{by:g} "
                 f"(need >=3mm clearance each side). Pick a smaller --size or a bigger printer.")

    cx, cy = bx / 2.0, by / 2.0
    hx = sx / 2.0 - bw / 2.0        # wall-centreline half-extents
    hy = sy / 2.0 - bw / 2.0
    e_mm = bw * lh / A_FIL
    f = round(speed * 60)
    # CORNER SLOWDOWN — quarter speed through the inner concentric-square corners that peeled.
    # Oleg, 2026-07-30: "the inner square got detachment, on low radius sharp turns you have to slow
    # down." At 50 mm/s the head overshoots a 90deg corner (Klipper brakes but E meters per mm of
    # PATH, so the bead does not) and the flung cusp peels off the plate. Slow the ramp INTO/THROUGH
    # each corner; hold 50 on the straights. E per mm is unchanged, so deposit is identical — only
    # the feedrate falls (declared ; SPEED_CORNER, moves LINK-tagged, verified by validate R3c).
    corner_speed = speed / 4.0
    corner_f = round(corner_speed * 60)
    czone = max(4.0, 3.0 * bw)                         # mm of slow ramp each side of a corner
    land = bw * lh / machine.PRESS_HARD                # pressed layer-1 landed width (~12mm)
    z1 = machine.PRESS_HARD
    z2 = machine.PRESS_HARD + lh

    L = []; w = L.append
    e = 0.0
    qx = qy = qz = None

    def emit(X, Y, Z):
        nonlocal e, qx, qy, qz
        d3 = math.hypot(math.hypot(X - qx, Y - qy), Z - qz)
        if d3 < 0.2:                 # decimate micro-segments — else Klipper move-rate stalls
            return
        e += d3 * e_mm
        w(f"G1 X{X:.3f} Y{Y:.3f} Z{Z:.3f} E{e:.5f}")
        qx, qy, qz = X, Y, Z

    def emit_cornered(samples, z):
        """Emit (x,y,slow) samples at body speed, dropping to corner_f through the slow ramps.
        Mirrors the pocket regime: a bare 'G1 F' switches the regime, tagged moves inherit it (so
        R4 skips them via LINK and R3c verifies SPEED_CORNER). E per mm is unchanged — only feed."""
        nonlocal e, qx, qy, qz
        slow_state = False
        for X, Y, flag in samples:
            want_slow = flag           # DEST-only: decelerate into the cusp, keep the departure
            d3 = math.hypot(math.hypot(X - qx, Y - qy), z - qz)   # straight fast (see stand_common)
            if d3 < 0.2:
                continue
            if want_slow != slow_state:
                if want_slow:
                    w(f"G1 F{corner_f}   ; corner slowdown — sharp turn, {corner_speed:g} mm/s")
                else:
                    w(f"G1 F{f}   ; restore body speed — leaving corner")
                slow_state = want_slow
            e += d3 * e_mm
            tag = " ; LINK corner slow" if want_slow else ""
            w(f"G1 X{X:.3f} Y{Y:.3f} Z{z:.3f} E{e:.5f}{tag}")
            qx, qy, qz = X, Y, z
        if slow_state:
            w(f"G1 F{f}   ; restore body speed — corner ran to loop end")

    def ring_slow(ix, iy, z):
        """One rectangle ring inset (ix,iy) from the wall centreline, at height z, with the four
        90deg corners run at corner speed (the inner square that peeled). Starts/ends at +x,+y so
        rings chain into a continuous spiral."""
        x0, x1 = cx - ix, cx + ix
        y0, y1 = cy - iy, cy + iy
        corners = [(x1, y1), (x0, y1), (x0, y0), (x1, y0), (x1, y1)]
        emit_cornered(sc.corner_samples(corners, seg=1.5, zone=czone,
                                        sharp_deg=55.0, short_len=2.0 * bw), z)

    fillet = max(0.0, min(a.fillet, a.depth - lh))     # leave at least one single-bead lap above
    jlayers = int(round(fillet / lh))
    laps_wall = int((a.depth - fillet) / lh)
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh}")
    w(f"; FLOW={bw*lh*speed:.4f}")
    w(f"; PRINTER={a.printer}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w(f"; PRINT_TEMP={temp}")
    w(f"; SPEED_CORNER={corner_speed:.4f}")            # third regime — slow the square corners (R3c)
    w("; ARGV: " + " ".join(sys.argv))
    w(f"; STAND TILE {sx:g}x{sy:g} depth {a.depth:g}: pressed floor + single-bead wall, bead "
      f"{bw:.2f}x{lh:g}. Butt with siblings, lay bamboo rebar, pour sand+gypsum for a monolithic slab")
    _der = machine.flow_derate_stamp(a.material, a.printer, bw * lh * speed)
    if _der:
        w(_der)
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {laps_wall + jlayers + 2}"); w("; HEADER_BLOCK_END")
    w("M82")
    # COLD-BED RUN. Oleg, 2026-07-30, on limited solar power: the heated bed is the biggest draw, so
    # --bed 0 prints with NO bed heat. A cold bed must never emit M190 (wait-for-bed) — the bed will
    # never reach a positive target and the print would stall forever waiting. Adhesion then rests
    # ENTIRELY on the mechanical press doctrine (0.1 wide-bead squish keying into the textured plate)
    # plus this build's corner slowdown — which is exactly what the knock-test tile now proves out.
    if bed > 0:
        w(f"M140 S{bed:.0f}")
        w(f"M104 S{temp}")
        _wait = bed if a.printer == "k2plus" else machine.bed_start(a.material, bed)
        w(f"M190 S{_wait:.0f}")
    else:
        w("M140 S0                          ; COLD BED — solar run, no bed heat, no M190 wait")
        w(f"M104 S{temp}")
    w(f"M109 S{temp}")
    w("G28")
    w("SET_GCODE_OFFSET Z=-0.05             ; first-layer press insurance (measured ~0.1 high on K2)")
    w("M106 S0")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")
    px, py = 20.0, 16.0
    w(f"G1 F600 Z{machine.PRESS_HARD:.3f}")
    w(f"G0 F9000 X{px:.3f} Y{py:.3f}")
    w("G1 E20 F300                      ; PRIME stationary purge")
    w(f"G1 F1200 X{px+40:.3f} Y{py:.3f} E30   ; PRIME line")
    w(f"G0 F3000 X{px+52:.3f} Y{py+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    w("; BODY_START")

    # --- FLOOR layer 1: pressed at 0.1, concentric rings spiralling INWARD, pitch = landed width
    #     so the ~12mm pressed beads tile into a solid welded base (the wide-line press, R4b-exempt). ---
    x0c = cx + hx
    w(f"G0 F9000 X{x0c:.3f} Y{cy + hy:.3f} ; PRIME-TRAVEL to floor start")
    w(f"G1 F600 Z{z1:.3f}")
    w(f"G1 F{f}")
    qx, qy, qz = x0c, cy + hy, z1
    ix, iy = hx, hy
    while ix > land * 0.5 and iy > land * 0.5:
        ring_slow(ix, iy, z1)
        ix = max(0.0, ix - land)
        iy = max(0.0, iy - land)
    emit(cx, cy, z1)                 # close to centre

    # --- FLOOR layer 2: solid, rings spiralling OUTWARD at bead pitch, ending at the outer edge.
    #     With --rod-channel, ONE ring is skipped a bamboo-diameter inboard of the haunch, leaving a
    #     shallow perimeter channel that locates the bottom ring rod in the floor-wall corner (rule
    #     2). Skipping a ring is still one continuous stroke (the spiral steps 2 beads there). ---
    nbase = max(1, a.wall_beads)
    chan_r = hx - (nbase * bw + a.rod_dia) if a.rod_channel else None
    w(f"G1 F1800 Z{z2:.3f}")
    w(f"G1 F{f}")
    qz = z2
    rings = []
    ix, iy = 0.0, 0.0
    step = bw
    while ix < hx and iy < hy:
        if chan_r is None or abs(ix - chan_r) > bw * 0.5:
            rings.append((min(ix, hx), min(iy, hy)))
        ix += step; iy += step
    rings.append((hx, hy))
    emit(cx, cy, z2)
    for rix, riy in rings:
        ring_slow(rix, riy, z2)

    # --- FUSED CORNER (haunch): the concept cup (stand.py) FAILED here on 2026-07-29 — its solid
    #     floor disc peeled off the single-bead wall along the one-bead rim seam when pulled. A
    #     sand+gypsum fill pushes the floor down and out, so that seam is a peel joint under load.
    #     FIX: for the first `fillet` mm the perimeter is a solid band tapering from `wall_beads`
    #     wide to 1, laid face-to-face ONTO the floor's outer rings — floor and wall become one
    #     continuous welded mass over real height, not two parts touching along a line. (Mechanical
    #     interlock + bamboo rebar through this corner are the real load path — see the guide; they
    #     are laid at assembly, not printed into a single tile.) ---
    w("; bead 2.00x wall")            # so the overhang check sizes its support cell sensibly
    for j in range(1, jlayers + 1):
        zf = z2 + j * lh
        frac = (j * lh) / fillet if fillet > 1e-9 else 1.0
        k = max(1, int(round(nbase - (nbase - 1) * frac)))
        # innermost ring first, ending on the outer wall line, so the wall spiral continues cleanly
        for b in range(k - 1, -1, -1):
            ring_slow(hx - b * bw, hy - b * bw, zf)

    zstart = z2 + fillet

    # --- WALL: single-bead rectangle spiral rising from the top of the haunch to the fill depth ---
    perim = 2.0 * (2 * hx + 2 * hy)
    t = 0.0
    Z = zstart
    top = z2 + a.depth
    # ride the outer rectangle, climbing lh per full lap, until the fill depth is reached
    corners = [(cx + hx, cy + hy), (cx - hx, cy + hy),
               (cx - hx, cy - hy), (cx + hx, cy - hy)]
    ci = 0
    guard = 0
    while Z < top - 1e-6 and guard < laps_wall * 4 + 8:
        guard += 1
        for k in range(4):
            X, Y = corners[(ci + k + 1) % 4]
            seg = math.hypot(X - qx, Y - qy)
            t += seg
            # climb lh per lap: Z advances one layer height each full rectangle perimeter
            Z = min(top, zstart + lh * t / perim)
            emit(X, Y, Z)
        ci += 1

    w("M107"); w("M104 S0"); w("M140 S0")
    w(f"G0 Z{top + 10:.0f} F900")
    w(f"G0 X{min(10.0, bx-10):.0f} Y{by-10:.0f} F9000")
    g = "\n".join(L) + "\n"

    grams = e * A_FIL * 1.24 / 1000.0
    mins = e / e_mm / speed / 60.0
    fill_ml = sx * sy * a.depth / 1000.0 * 0.90        # ~90% net of walls; ribs (v1) take a little more
    kg = fill_ml * 1.9 / 1000.0
    print(f"  stand tile {sx:g}x{sy:g} depth {a.depth:g}: pressed floor, {fillet:g}mm fused "
          f"{nbase}->1 bead corner haunch, {laps_wall}-lap single-bead wall")
    print(f"  ~{grams:.0f} g shell, ~{mins:.0f} min; holds ~{fill_ml:.0f} mL fill "
          f"(~{kg:.1f} kg sand+gypsum at 1.9 g/cc)")
    print(f"  a 2x2 of these = one tabletop: {2*sx:g}x{2*sy:g} mm, ~{4*kg:.1f} kg of damping mass")
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"stand_tile_{a.printer}_{sx:g}x{sy:g}_d{a.depth:g}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(fn)


if __name__ == "__main__":
    main()
