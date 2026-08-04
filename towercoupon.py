#!/usr/bin/env python3
"""TOWER COUPON — how tall can a thin vertical member stand before it stops standing?

Oleg, 2026-08-04: "lets start with a coupons how high can we build thin towers vertically, once we
have that primitive we can connect it with bridgest" and "i suggrst to play with generating gcode
directly".

WHAT THIS PLATE IS
------------------
Six single-wall round towers in a row, every one a CONSTANT diameter, every one commanded to the
same height, all printed LAYER-SYNCHRONISED (every tower gets layer n before any tower gets layer
n+1). The only thing that differs between towers is the diameter. Diameters are the R5 preferred
numbers 1.0 / 1.6 / 2.5 / 4.0 / 6.3 / 10.0 mm — two full decades of section on one plate.

WHY CONSTANT SECTIONS AND NOT A TAPERED NEEDLE
----------------------------------------------
A tapering tower is a tempting design because its diameter reports its own height, so a fallen
fragment still says where it came from. It was rejected for two reasons.

  1. ON A TAPER, HEIGHT AND DIAMETER ARE THE SAME COORDINATE. A break at z is also a break at D(z),
     and nothing about a single tapered tower can separate "it ran out of section" from "it ran out
     of height". Recovering the separation costs several taper RATES on the same plate, which is a
     more expensive plate that answers a question nobody asked.

  2. OLEG ASKED FOR A PRIMITIVE TO BRIDGE BETWEEN. That primitive is a post of some section, not a
     needle. A number measured on a taper does not transfer to the constant-section member he would
     actually build with.

The taper's one real virtue — a wrecked plate still being evidence — is kept, by a different route:
see THE RULER below.

CONSTANT SECTIONS ALSO REMOVE THE COOLING CONFOUND FOR FREE. If towers had different heights, they
would drop out as the print rose, so the number still printing would fall with z, so layer time
would fall with z, so cooling would degrade in lockstep with the variable under test. Here every
tower runs every layer at a fixed circumference, so LAYER TIME IS CONSTANT BY CONSTRUCTION. No
padding shuttle, no metronome, nothing to declare. The measured spread is reported by
tools/measure_towers.py off the emitted file.

THE RULER — why a wrecked plate is still evidence
-------------------------------------------------
A tall thin tower usually destroys its own record: it falls, and this machine has no webcam, so
"it reached somewhere between 0 and 70 mm" is all that survives. Worse, a faller can take a
neighbour with it.

So every tower carries a COUNTING RULER. Every 50 layers — exactly 4.000 mm, because 50 x 0.08 is
exact — the loop steps out by RULER_BONUS mm of radius for a few layers, leaving a raised collar.
Every fifth collar (20.000 mm) is twice as tall, so it reads as a major band. Count collars from
either end of any fragment, multiply by 4 mm, and the fragment reports the height it came from
whatever orientation it landed in and whatever else fell on it.

THE COLLAR IS A PERTURBATION AND IT IS DECLARED. It steps out RULER_BONUS = 0.15 mm on a BEAD_W
0.42 bead, so the collar bead still overlaps the one below it by 0.27 mm (64%). It is deliberately
an OUTWARD step, not a waist: a waist would be a stress concentration and would bias where the
tower breaks, which is the one thing this plate must not do. An outward step biases stiffness the
other way, very slightly, at 1 layer in 17. IF EVERY TOWER BREAKS EXACTLY AT A COLLAR, THE COLLAR IS
THE CAUSE and this plate must be re-run with --ruler-bonus 0 before its numbers mean anything. That
is a falsifiable statement and it is the first thing to check on the wreck.

THE FOOT — so the plate measures the tower and not the bed bond
---------------------------------------------------------------
A 1.0 mm single-wall tower standing on its own footprint touches the plate along a ring 1.8 mm
around and (at the 0.10 press gap, carrying the body's own mm2/mm) 0.34 mm wide: about 0.6 mm2 of
bond holding a 70 mm lever. It would peel, and the plate would have measured ADHESION rather than
height — the wrong quantity, arriving as a confident number.

So each tower starts on a FOOT: an Archimedean spiral wound from the outside inward, ending exactly
on the tower's own seam so the foot and the tower are ONE CONTINUOUS STROKE with no link move. Two
foot layers, the second smaller, then the tower rises. The foot is what makes the base a clamp
instead of a hinge.

WHAT EVERY MOVE IN THIS FILE RUNS AT
------------------------------------
50 mm/s. Extrusion, travel, hop, all of it — Oleg's north star taken literally ("50 mm/s constant
for ALL moves incl. first layer"). It also happens to keep every travel at F3000, which is not
above the ploughing guard's F3000 threshold, so the guard's arithmetic and the machine's physics
agree instead of being traded off against each other. The hops lift clear anyway.

Every constant below is either a machine.py constant with recorded provenance, or a value READ OFF
THE SPARKX ITSELF over Moonraker (marked MEASURED-OFF-MACHINE). Nothing here is a new number.

    bead width      0.42 mm    SparkX slicer line_width
    layer height    0.08 mm    SparkX slicer layer_height
    layer 1 gap     0.10 mm    machine.PRESS_HARD  ("the nozel need to be 0,1 to board")
    speed           50 mm/s    machine.DEFAULT_SPEED
    nozzle          0.4 mm     MEASURED-OFF-MACHINE (extruder.nozzle_diameter)
    nozzle temp     210 C      machine.TEMP
    bed             60 C       machine.BED_TEMP['pla']
    part fan        20% max    machine.FAN_MAX['pla'], 0 on layer 1
    flow  0.42 * 0.08 * 50 = 1.68 mm3/s  -> REQUIRES '; FLOW_DERATE=' (see below)

WHY R8 IS DECLARED RATHER THAN BREACHED. 1.68 mm3/s is 3.7% of the 45 mm3/s figure carried for this
machine. It is not a derate in the sense R8 guards against ("slow is allowed, silent slow is not"):
it is what a 0.4 nozzle laying its own slicer's 0.42 x 0.08 bead AT the north-star speed physically
delivers. The only way to reach 36 mm3/s would be to widen the bead, and the width of a single-wall
thin member IS the variable under test. The file states the reason; no rule is changed or silenced.

THE PLATE IS READABLE AND CANCELLABLE AT ANY MOMENT. Failure accumulates from the bottom, so
whatever has already failed when Oleg stops it is already the answer for that tower, and whatever
is still standing is a lower bound for the rest. Stopping early costs nothing that was learned.

WHAT THIS PLATE CANNOT TELL US is printed at the end of every run and repeated in the report.

Usage:  python3 towercoupon.py                 (defaults are the plate as designed)
        python3 towercoupon.py --height 40     (shorter, if the row is to be re-run)
"""
import argparse, math, os
import machine

A_FIL = math.pi * (1.75 / 2) ** 2      # mm2 of 1.75mm filament; the one place it is computed here

# READ OFF THE SPARKX (192.168.3.138, hostname F022-EAE2) over Moonraker /printer/objects/query,
# 2026-08-04, read-only. Kept here rather than in machine.py because machine.py's 'f022' entries are
# admittedly copied from the k1c ("same hotend family as the k1c, untested -- assumed, not
# measured") and this is the first time the machine itself has been asked.
SPARKX = {
    "nozzle_diameter": 0.4,        # extruder.nozzle_diameter
    "max_velocity": 500.0,         # printer.max_velocity
    "max_accel": 10000.0,          # printer.max_accel
    "square_corner_velocity": 12.0,
    "max_z_velocity": 20.0,        # printer.max_z_velocity  -- SLOW, and it prices every z-hop
    "max_z_accel": 100.0,          # printer.max_z_accel     -- SLOWER still
    "pressure_advance": 0.031,
    "position_max": (279.0, 280.0, 260.0),
    "bed_mesh": ((5.0, 5.0), (255.0, 255.0)),
    # THE SHAPER NUMBERS ON THIS MACHINE ARE DEFAULTS, NEVER MEASURED ON IT:
    #   input_shaper.using_default_data = True, shaper_freq_x 63.4 (ei), shaper_freq_y 35.8 (mzv)
    # That matters more here than on any normal part: a 70 mm slender tower is a cantilever whose
    # own frequency falls as it grows, and the only thing damping the head's excitation of it is a
    # shaper tuned to a machine that is not this one. It is stated, not hidden. UNMEASURED.
    "input_shaper_is_default": True,
}

# The SparkX's own slicer profile geometry. This is the operating point Oleg's own slicer would use
# on this machine, which is the whole reason the answer transfers to what he would actually print.
BEAD_W = 0.42
LAYER_H = 0.08

# Preferred numbers (R5 series, ratio ~1.585). Two decades of section, six towers, five hops.
DIAMETERS = [1.0, 1.6, 2.5, 4.0, 6.3, 10.0]

RULER_PERIOD = 50      # layers between collars; 50 x 0.08 = 4.000 mm EXACTLY
RULER_MINOR = 3        # layers per ordinary collar
RULER_MAJOR_EVERY = 5  # every 5th collar (20.000 mm) is a major band
RULER_MAJOR = 6        # layers per major band
RULER_BONUS = 0.15     # mm of extra RADIUS at a collar; leaves 0.27mm of a 0.42 bead overlapping

HOP_Z = 0.4            # mm lifted before every inter-tower travel (NO_TRAVEL_RULE: lift, tag, hop)
SEG_TARGET = 0.35      # mm, target segment length around a loop
SEG_MIN_N = 8          # never fewer than 8 segments, however small the loop
FOOT_LAYERS = 2        # foot layers before the tower rises
FOOT_MARGIN = 3.0      # mm of foot radius beyond the tower wall on layer 1
FOOT_MIN_D = 4.5       # mm, smallest foot diameter
FOOT_R_MIN = 1.0       # mm, radius below which the foot stops spiralling (see foot_spiral)


def loop_pts(cx, cy, r, n, seam):
    """Closed loop of n segments about (cx,cy), starting at segment index `seam`.

    Returns n+1 points; the last equals the first, so the loop closes exactly. The NEXT layer asks
    for seam+1, whose first point is one segment along from where this layer ended — so the seam
    walks around the tower instead of stacking into a ridge, and the layer change costs one
    segment of travel rather than a reposition across the part.
    """
    return [(cx + r * math.cos(2 * math.pi * ((seam + i) % n) / n),
             cy + r * math.sin(2 * math.pi * ((seam + i) % n) / n))
            for i in range(n + 1)]


def foot_spiral(cx, cy, r_out, r_cl, step, seam, n):
    """Archimedean spiral from r_out inward, ENDING on the tower's seam point.

    Ending on the seam is the point: the foot runs straight into the tower's own loop with no link
    move and no travel, so foot+tower is one continuous stroke (the house rule) and the base has no
    seam to peel from.

    THE SPIRAL STOPS AT FOOT_R_MIN AND FINISHES WITH ONE RADIAL MOVE. Winding a spiral all the way
    down to a 0.29 mm inner radius (the D=1.0 tower's centreline) is what the first version did, and
    it was wrong twice over: the angular step SEG_TARGET/r blows up as r falls, so the innermost
    turns degenerate into a coarse 5-sided polygon whose corners cut inside the turn before them and
    lay a second bead on ground already covered. validate.py measured the result as a 1.72x fill at
    Z0.18 — a REAL over-extrusion, which the '; PRESSED_LAYER1=' stamp then excused because the
    worst layer happened to be sampled next to it. Below FOOT_R_MIN the annulus is crossed once, by
    a single radial bead at the seam angle, which covers no ground twice.
    """
    th_end = 2 * math.pi * (seam % n) / n
    r_in = max(r_cl, FOOT_R_MIN)
    pts = []
    revs = (r_out - r_in) / step
    if revs > 0:
        th_start = th_end - 2 * math.pi * revs
        th = th_start
        while th < th_end - 1e-9:
            r = r_in + (th_end - th) / (2 * math.pi) * step
            pts.append((cx + r * math.cos(th), cy + r * math.sin(th)))
            th += SEG_TARGET / max(r, FOOT_R_MIN)   # r floor keeps the arc step sane, see above
        pts.append((cx + r_in * math.cos(th_end), cy + r_in * math.sin(th_end)))
    if r_in > r_cl + 1e-9:
        # single radial bead inward to the tower wall, along the seam ray: crosses the uncovered
        # annulus exactly once
        pts.append((cx + r_cl * math.cos(th_end), cy + r_cl * math.sin(th_end)))
    return pts


def collar_bonus(li, bonus=RULER_BONUS):
    """Extra RADIUS at 0-based layer index li. See THE RULER in the module docstring."""
    if li < FOOT_LAYERS + 2:
        return 0.0
    k, off = divmod(li, RULER_PERIOD)
    if k == 0:
        return 0.0
    span = RULER_MAJOR if (k % RULER_MAJOR_EVERY == 0) else RULER_MINOR
    return bonus if off < span else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="f022")
    ap.add_argument("--material", default="pla")
    ap.add_argument("--height", type=float, default=70.0, help="commanded tower height mm")
    ap.add_argument("--pitch", type=float, default=25.0, help="mm between tower centres")
    ap.add_argument("--ruler-bonus", type=float, default=RULER_BONUS,
                    help="collar radius step mm; 0 disables the ruler (re-run control if every "
                         "tower breaks at a collar)")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    bonus_mm = a.ruler_bonus
    bw, lh = BEAD_W, LAYER_H
    speed = machine.DEFAULT_SPEED                 # 50, the north star, for EVERY move in the file
    f = round(speed * 60)                         # F3000
    temp = machine.MATERIAL_TEMP[a.material]      # 210
    bed = min(machine.BED_TEMP[a.material], machine.BED_MAX.get(a.printer, machine.BED_MAX_DEFAULT))
    fan = machine.FAN_MAX[a.material]             # 0.20
    press = machine.PRESS_HARD                    # 0.10, R1
    e_mm = bw * lh / A_FIL                        # filament mm per mm of path — ONE value, all file
    flow = bw * lh * speed                        # 1.68 mm3/s
    r8cap = machine.flow_cap(a.material, a.printer)

    n_lay = int(round((a.height - press) / lh)) + 1
    top_z = press + (n_lay - 1) * lh

    bedx, bedy = machine.BED[a.printer]
    n_tow = len(DIAMETERS)
    span = (n_tow - 1) * a.pitch
    x0 = bedx / 2.0 - span / 2.0
    cy = bedy / 2.0
    towers = []
    for i, d in enumerate(DIAMETERS):
        r_cl = d / 2.0 - bw / 2.0                 # CENTRELINE radius: the path, not the wall
        circ = 2 * math.pi * r_cl
        nseg = max(SEG_MIN_N, int(math.ceil(circ / SEG_TARGET)))
        towers.append({"d": d, "cx": x0 + i * a.pitch, "cy": cy, "r": r_cl,
                       "n": nseg, "circ": circ})

    L = []
    w = L.append
    w("; TOWER COUPON — how tall can a thin single-wall vertical member stand?")
    w("; six constant-section towers, layer-synchronised, collar ruler every 4.000mm")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={a.material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={speed:.4f}")
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; FLOW_DERATE=a 0.4 nozzle laying its own slicer's {bw:g}x{lh:g} bead at the {speed:g} mm/s "
      f"north star delivers {flow:.2f} mm3/s. Reaching {0.8*r8cap:g} would mean WIDENING the bead, "
      f"and the width of a thin single-wall member is the variable under test. Declared, not silent.")
    w(f"; bead {bw:g} x {lh:g}   nozzle {SPARKX['nozzle_diameter']:g} (read off the machine)")
    w(f"; towers D=" + "/".join(f"{t['d']:g}" for t in towers) + f" mm, pitch {a.pitch:g}mm")
    w(f"; ruler: collar every {RULER_PERIOD} layers = {RULER_PERIOD*lh:.3f}mm, "
      f"major every {RULER_MAJOR_EVERY} collars = {RULER_PERIOD*RULER_MAJOR_EVERY*lh:.3f}mm, "
      f"radius step {bonus_mm:g}mm")
    w("; input_shaper on this machine is using_default_data=True — shaper freqs are DEFAULTS, never")
    w("; measured on it. For a slender tower that is the one unquantified term. UNMEASURED.")
    w(";")
    w("; ---------------- PLATE PLAN ----------------")
    w("; WATCH THE FIRST 2 MINUTES. Six feet go down as flat spirals. If any of them is not stuck")
    w(";   flat and glossy, stop: at this layer height the 0.10 press gap is LOOSER than a 0.08")
    w(";   layer, so this first layer is thin (0.34mm wide), and it is the only thing holding a")
    w(";   70mm lever. A foot that lifts a corner has already decided the run.")
    w("; THEN LOOK EVERY ~10 MINUTES, at the THIN END of the row (left, X47).")
    w(";   The answer arrives from the bottom up and the thinnest tower decides first.")
    w("; LISTEN. A tall thin tower announces failure before it looks failed:")
    w(";   - a light TICK once per layer = the nozzle is clipping a tower that has begun to lean.")
    w(";   - a rising BUZZ or whine = the row is being driven near resonance. This machine's input")
    w(";     shaper is on DEFAULT data, never measured on it, so that is the term nobody can")
    w(";     predict. If you hear it, note the height and stop.")
    w(";   - a change to a papery RUSTLE = a tower is gone and the nozzle is drawing in the air.")
    w("; STOPPING EARLY COSTS NOTHING THAT WAS LEARNED. Whatever has already failed is the answer")
    w(";   for that tower; whatever still stands is a lower bound for the rest.")
    w("; READING THE WRECK: count collars from the base, x4mm. Every 5th collar is a tall band")
    w(";   (=20mm). A fallen fragment reports its own height the same way, in any orientation.")
    w("; FIRST THING TO CHECK: if every tower broke exactly AT a collar, the ruler caused it —")
    w(";   re-run with --ruler-bonus 0 before believing any number from this plate.")
    w("; -------------------------------------------")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {n_lay}")
    w("; HEADER_BLOCK_END")
    w("M82")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    w(f"M190 S{machine.bed_start(a.material, bed):.0f}")
    w(f"M109 S{temp}")
    w("G28")
    w("M106 S0                              ; layer 1 gets no fan — the weld to the plate is the job")
    w("G92 E0")

    # prime, off the row, in the front-left corner
    px, py = 20.0, 16.0
    w(f"G1 F{f} Z{press:.3f}")
    w(f"G0 F{f} X{px:.3f} Y{py:.3f}")
    w("G1 E12 F300                          ; PRIME stationary purge")
    w(f"G1 F{f} X{px+40:.3f} Y{py:.3f} E20  ; PRIME line")
    w(f"G0 F{f} X{px+52:.3f} Y{py+12:.3f}   ; PRIME break-off wipe")
    w("G92 E0")
    w("; BODY_START")

    E = 0.0
    fan_on = False
    for li in range(n_lay):
        z = press + li * lh
        gap = press if li == 0 else lh          # layer 1 is laid into the 0.10 press gap
        order = list(range(n_tow)) if li % 2 == 0 else list(range(n_tow))[::-1]
        w(f"; ---- layer {li+1} of {n_lay}  z {z:.3f}")
        w(f"G1 F{f} Z{z:.3f}")                  # STANDALONE Z — this is R2's layer ladder
        if li == 1 and not fan_on:
            w(f"M106 S{int(round(fan*255))}     ; {fan*100:.0f}% — machine.FAN_MAX['pla']")
            fan_on = True
        bonus = collar_bonus(li, bonus_mm)
        for j, ti in enumerate(order):
            t = towers[ti]
            seam = li % t["n"]
            r = t["r"] + bonus
            pts = loop_pts(t["cx"], t["cy"], r, t["n"], seam)
            # foot on the first FOOT_LAYERS layers, spiralling inward INTO the tower's own seam
            head = []
            if li < FOOT_LAYERS:
                r_out = max(t["d"] / 2.0 + FOOT_MARGIN - li * 1.2, FOOT_MIN_D / 2.0 - li * 1.2)
                step = 0.78 * (bw * lh / gap)   # 0.78 overlap on the width the bead ACTUALLY lands at
                head = foot_spiral(t["cx"], t["cy"], r_out, r, step, seam, t["n"])
            path = head + pts if head else pts
            sx, sy = path[0]
            if j == 0:
                # continuing on the tower this layer's predecessor ended on: one segment of travel
                w(f"G0 F{f} X{sx:.3f} Y{sy:.3f} ; HOP seam-walk")
            else:
                w(f"G0 F{f} Z{z+HOP_Z:.3f} ; HOP lift clear")
                w(f"G0 F{f} X{sx:.3f} Y{sy:.3f} ; HOP to tower D{t['d']:g}")
                w(f"G0 F{f} Z{z:.3f} ; HOP down")
            ppx, ppy = sx, sy
            for (x, y) in path[1:]:
                seg = math.hypot(x - ppx, y - ppy)
                if seg < 1e-9:
                    continue
                E += seg * e_mm
                w(f"G1 X{x:.3f} Y{y:.3f} E{E:.5f}")
                ppx, ppy = x, y

    w("M107")
    w("M104 S0")
    w("M140 S0")
    w(f"G0 F{f} Z{top_z+20:.2f}")
    w("G0 F3000 X10 Y10")

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out,
                      f"towercoupon_{a.printer}_{a.material}_h{a.height:g}_n{n_tow}_b{bw:g}.gcode")
    open(fn, "w").write("\n".join(L) + "\n")

    print(fn)
    _dlist = "/".join(f"{t['d']:g}" for t in towers)
    print(f"  {n_tow} towers D={_dlist}mm  "
          f"pitch {a.pitch:g}mm  {n_lay} layers  top z {top_z:.2f}mm")
    print(f"  bead {bw:g} x {lh:g} at {speed:g} mm/s -> {flow:.2f} mm3/s "
          f"({100*flow/r8cap:.1f}% of the {r8cap:g} figure, DECLARED)")
    print(f"  aspect ratios (h/D): " + "  ".join(f"{t['d']:g}:{top_z/t['d']:.0f}" for t in towers))
    print("  INTENT ONLY — every number that matters is measured off the file by "
          "tools/measure_towers.py")
    print("\n  WHAT THIS PLATE CANNOT TELL US")
    print("   - nothing about BEAD WIDTH. Every tower here is one 0.42 bead wide. Whether a bead")
    print("     narrower than the 0.4 orifice still touches the nozzle land is a WIDTH ladder, and")
    print("     this is a HEIGHT ladder. UNMEASURED.")
    print("   - nothing about bridging BETWEEN towers, which is the next primitive, not this one.")
    print("   - nothing about any other machine. 0.42 x 0.08 is the SparkX's own slicer geometry;")
    print("     the K1C (1.0 nozzle) and K2 Plus (0.8) are different regimes and were both silent.")
    print("   - it cannot separate SWAY from THERMAL failure on its own. Layer time is constant, so")
    print("     the comparison across diameters is clean, but a single failure height is a")
    print("     boundary, not a mechanism. What Oleg HEARS decides that (see the plate plan).")
    print("   - it cannot prove a survivor's limit. A tower still standing at the top gives a LOWER")
    print("     BOUND only: >= that height, not 'that height'.")


if __name__ == "__main__":
    main()
