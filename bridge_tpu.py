#!/usr/bin/env python3
"""BRIDGE-TPU-1: posts-and-bridges span coupon for TPU 72D on the K2 Plus 0.4 nozzle.

Spec: ~/dev/Assist/reports/toolpath-lattice-verdict-2026-10-18.md, section "Coupon spec: BRIDGE-TPU-1".
Path-based: every move is generated here, nothing is sliced, no STL exists.

WHAT IT IS. One bead row per FILE, five post pairs per row. Each post is a 4x4 mm closed loop
built lap by lap to ~20 mm; layer 1 is a filled pad. Every 10 laps one straight one-bead strand
runs from post B's facing wall to post A's facing wall at the lap's Z (posts first, the chord
after: verdict H5). Clear spans between facing faces: 4, 7, 10, 13, 16.8 mm.

TWO ROWS, TWO FILES, ONE PLATE. The verdict asks for two bead rows on one plate AND one speed per
file (50 mm/s for R1, 26 for R2). validate.py R3 has no seam for two body speeds, so each row is
its own file, placed at its own X on the same plate and printed one after the other. The rows sit
far enough apart (> machine.HEAD_R, which is UNVERIFIED) that printing the second row's 20 mm
posts does not sweep the head through the first.

  R1  0.6 x 0.3    the house ceilings, 1.5x / 0.75x a 0.4 orifice
  R2  0.82 x 0.42  his Orca hanger line and layer (2026-10-08). OVER both ceilings, so it is
                   refused unless --over-limit is passed, and the file then stamps BEAD_OVERRIDE.

SPEED = min(50, 9 mm3/s / (w*lh)). The 9 is the verdict's WV-78 figure, under Orca's 15 cap.

TEMPS AND FANS ARE READ FROM HIS ORCA PROFILE at generation time, following its inherits chain
("72D TPU 0.4" -> "Generic TPU @K2 Plus-all" -> "fdm_filament_tpu"), and each value's source is
stamped. Two places where the house disagrees with Orca, stamped rather than resolved:
  * machine.MATERIAL_TEMP/BED_TEMP say 245/50 for tpu-72d (2026-10-06); Orca says 270/70. Orca wins
    here because the brief says so.
  * Orca turns the part fan off for layer 1 and runs the aux fan at 70%; validate.py's TPU guard
    requires full fans everywhere, so machine.fan_first_layer/aux_for (1.0) win.

LAYER 1 lands at 0.24 x 0.93, the only k2plus 0.4-TPU pair in machine.PROVEN_LAYER1, which that
table itself marks ORDERED, NOT YET READ.

START: machine.home_clean (the K2's own order, the saved mesh loaded, no BED_MESH_CALIBRATE).

Usage:
  python3 bridge_tpu.py --row R1
  python3 bridge_tpu.py --row R2 --over-limit
  python3 bridge_tpu.py --check out/<file>.gcode     # re-derive every bridge's air from the moves
"""
import argparse, json, math, os, re, shlex, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine

A_FIL = machine.A_FIL
PRINTER = "k2plus"
MATERIAL = "tpu-72d"
NOZZLE = 0.4
W_CEIL, H_CEIL = 1.5 * NOZZLE, 0.75 * NOZZLE      # machine.py 36-44 ratios, applied to 0.4
ROWS = {"R1": (0.6, 0.3), "R2": (0.82, 0.42)}
ROW_CX = {"R1": 120.0, "R2": 230.0}               # both rows on one 350 plate, 85 mm edge to edge
FLOW_TARGET = 9.0                                 # mm3/s, verdict WV 78
POST = 4.0
POST_H = 20.0
SPANS = (4.0, 7.0, 10.0, 13.0, machine.PROVEN_AIR_MM)
PAIR_PITCH = 15.0
BRIDGE_EVERY = 10
BRIDGE_LEVELS = 5
H1, W1 = 0.24, 0.93                               # machine.PROVEN_LAYER1['k2plus'], unread entry
L1_PITCH = 0.80 * W1                              # bucket_towers.FLOOR1_OVERLAP, ratio to the bead
CLEAR = 0.8                                       # hop clearance over max printed Z

ORCA_USER = os.path.expanduser("~/Library/Application Support/OrcaSlicer/user/default/filament")
ORCA_SYS = "/Applications/OrcaSlicer.app/Contents/Resources/profiles/Creality/filament"
ORCA_PROFILE = "72D TPU 0.4"


def orca_filament(name=ORCA_PROFILE):
    """Resolve an Orca filament preset through its inherits chain. Returns {key: (value, file)}."""
    out, cur = {}, name
    while cur:
        path = next((os.path.join(d, cur + ".json") for d in (ORCA_USER, ORCA_SYS)
                     if os.path.isfile(os.path.join(d, cur + ".json"))), None)
        if path is None:
            sys.exit(f"REFUSING TO EMIT: Orca preset {cur!r} not found in {ORCA_USER} or {ORCA_SYS}")
        d = json.load(open(path))
        for k, v in d.items():
            out.setdefault(k, (v[0] if isinstance(v, list) and v else v, path))
        cur = d.get("inherits")
    return out


def speed_for(w, lh):
    return min(machine.DEFAULT_SPEED, FLOW_TARGET / (w * lh))


def layout(row):
    """Post footprints (x0,y0,x1,y1) as pairs [(A, B, span)], centred on the row's X."""
    cx, cy = ROW_CX[row], 175.0
    pairs = []
    for i, g in enumerate(SPANS):
        y0 = cy + (i - 2) * PAIR_PITCH - POST / 2
        xa0 = cx - (2 * POST + g) / 2
        A = (xa0, y0, xa0 + POST, y0 + POST)
        B = (xa0 + POST + g, y0, xa0 + 2 * POST + g, y0 + POST)
        pairs.append((A, B, g))
    return pairs


def air_span(p, q, rects, n=4000):
    """Length of chord p->q over no post footprint, walked, never assumed (bucket_towers.air_span)."""
    L = math.dist(p, q)
    air = 0.0
    for k in range(n):
        t = (k + 0.5) / n
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if not any(r[0] - 1e-9 <= x <= r[2] + 1e-9 and r[1] - 1e-9 <= y <= r[3] + 1e-9 for r in rects):
            air += L / n
    return air


def loop_pts(r, inset, start_side):
    """Closed square loop at `inset` inside rect r, starting and ending at the middle of a side."""
    x0, y0, x1, y1 = r[0] + inset, r[1] + inset, r[2] - inset, r[3] - inset
    ym = (y0 + y1) / 2
    if start_side == "right":
        return [(x1, ym), (x1, y1), (x0, y1), (x0, y0), (x1, y0), (x1, ym)]
    return [(x0, ym), (x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, ym)]


def emit(row, over_limit, out_dir):
    w_b, lh = ROWS[row]
    over = w_b > W_CEIL + 1e-9 or lh > H_CEIL + 1e-9
    if over and not over_limit:
        sys.exit(f"REFUSING TO EMIT: {row} bead {w_b:g}x{lh:g} exceeds the 0.4 ceilings "
                 f"{W_CEIL:g}x{H_CEIL:g}. Pass --over-limit to declare it (it is his Orca line).")
    orca = orca_filament()
    temp = int(float(orca["nozzle_temperature"][0]))
    bed = int(float(orca["hot_plate_temp"][0]))
    spd = speed_for(w_b, lh)
    f = round(spd * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    zerr = machine.ZERR[PRINTER]
    press = machine.PRESS_HARD
    zoff = machine.zoff_for(H1, zerr)
    laps = 1 + round((POST_H - H1) / lh)
    blaps = [k for k in range(BRIDGE_EVERY, laps + 1, BRIDGE_EVERY)][:BRIDGE_LEVELS]
    pairs = layout(row)
    rects = [r for A, B, _ in pairs for r in (A, B)]
    e1 = machine.layer1_rate(W1, H1)
    eb = w_b * lh / A_FIL

    L = []
    w = L.append
    w(f"; BRIDGE-TPU-1 row {row}: five post pairs, {w_b:g}x{lh:g} bead, spans "
      f"{','.join(f'{s:g}' for s in SPANS)} mm, a one-bead bridge every {BRIDGE_EVERY} laps")
    w(f"; PRINTER={PRINTER}")
    w(f"; CMD={' '.join(shlex.quote(s) for s in [os.path.basename(sys.argv[0])] + sys.argv[1:])}")
    w(f"; MATERIAL={MATERIAL}")
    w(f"; LAYER_H={lh:g}")
    q1, qb = e1 * A_FIL * spd, w_b * lh * spd
    w(f"; FLOW=VARIABLE:{round(min(q1, qb), 3):g}..{round(max(q1, qb), 3):g}")
    w(f"; SPEED={spd:.4f}")
    w(f";   min(50, {FLOW_TARGET:g} mm3/s / ({w_b:g}*{lh:g})) -- verdict WV 78; Orca cap "
      f"{orca['filament_max_volumetric_speed'][0]} mm3/s ({orca['filament_max_volumetric_speed'][1]})")
    w(f"; WALL=postbridge")
    w(f"; NOZZLE={NOZZLE:g}  (K2Plus-569A per memory printer-fleet-access; Orca's own K2Plus-569A "
      f"machine preset inherits the 0.6 base -- read the nozzle from Oleg before sending)")
    w(f"; bead {w_b:g}x{lh:g}")
    if over:
        w(f"; BEAD_OVERRIDE={w_b:g}x{lh:g} over the {W_CEIL:g}x{H_CEIL:g} ceilings, declared with "
          f"--over-limit: his Orca 'orca default' line/layer (memory hanger-family-is-tpu-72d)")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; LAYER1_WIDTH={W1:.2f}mm landed at {H1:g}: machine.PROVEN_LAYER1['k2plus'] (0.24, 0.93), "
      f"an entry that table marks ORDERED, NOT YET READ")
    w(f"; PRINT_TEMP={temp}  (Orca nozzle_temperature, {orca['nozzle_temperature'][1]}; "
      f"machine.MATERIAL_TEMP says {machine.MATERIAL_TEMP[MATERIAL]} -- disagreement stamped)")
    w(f"; BED_TEMP={bed}  (Orca hot_plate_temp, {orca['hot_plate_temp'][1]}; machine.BED_TEMP says "
      f"{machine.BED_TEMP[MATERIAL]})")
    w(f"; FAN: Orca fan_max_speed {orca['fan_max_speed'][0]}% ({orca['fan_max_speed'][1]}), "
      f"close_fan_the_first_x_layers {orca['close_fan_the_first_x_layers'][0]}, "
      f"additional_cooling_fan_speed {orca['additional_cooling_fan_speed'][0]}% -- emitted FULL on "
      f"every layer and both aux fans, because validate.py's TPU guard requires it")
    w("; PROBE_TEMP=140")
    w(f"; HEAD_R={machine.HEAD_R[PRINTER]:g} (UNVERIFIED) -- the other row sits 85 mm away edge to edge")
    for i, (A, B, g) in enumerate(pairs):
        w(f"; POST pair={i} A={A[0]:.3f},{A[1]:.3f},{A[2]:.3f},{A[3]:.3f} "
          f"B={B[0]:.3f},{B[1]:.3f},{B[2]:.3f},{B[3]:.3f} clear={g:g}")
    w(f"; {laps} laps, top at {H1 + (laps - 1) * lh:.2f} mm; bridges at laps "
      f"{','.join(map(str, blaps))} ({len(blaps)} levels"
      + (f", not {BRIDGE_LEVELS}: {POST_H:g} mm at {lh:g} holds only {len(blaps)}" if len(blaps) < BRIDGE_LEVELS else "")
      + ")")
    w("; READ IT: per span, mid-span sag vs 1 lh, hand-pull at the post, is the bridge above clean.")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {laps}"); w("; HEADER_BLOCK_END")

    w("M82")
    w("G90")
    w(f"M140 S{bed}")
    machine.home_clean(w, PRINTER, temp)
    w(f"M190 S{bed}")
    w("SET_GCODE_OFFSET Z=0")
    w(f"SET_GCODE_OFFSET Z={zoff:.3f} MOVE=0   ; commanded {press:g} + this + zerr {zerr:+.3f} = {H1:g}")
    w(f"M106 S{round(255 * machine.fan_first_layer(MATERIAL))}")
    for ln in machine.aux_fans(PRINTER, machine.aux_for(MATERIAL, 1.0)):
        w(ln)
    w("G92 E0")
    allx0 = min(r[0] for r in rects); ally0 = min(r[1] for r in rects)
    allx1 = max(r[2] for r in rects); ally1 = max(r[3] for r in rects)
    other = [r for A, B, _ in layout("R2" if row == "R1" else "R1") for r in (A, B)]
    avoid = (("rect", allx0 - 2, ally0 - 2, allx1 + 2, ally1 + 2),
             ("rect", min(r[0] for r in other) - 2, min(r[1] for r in other) - 2,
              max(r[2] for r in other) + 2, max(r[3] for r in other) + 2))
    machine.prime(w, printer=PRINTER, z=press, rate=e1, feed=f, travel_feed=travel_f,
                  avoid=avoid, near=(allx0, ally0))
    w("; BODY_START")

    E = 0.0
    top = [0.0]

    def hop(x, y, z, note):
        w(f"G0 Z{top[0] + CLEAR:.3f} F1800   ; HOP lift over max printed Z")
        w(f"G0 X{x:.3f} Y{y:.3f} F{travel_f}   ; HOP {note}")
        w(f"G1 Z{z:.3f} F600")

    def run(pts, rate, tag=""):
        nonlocal E
        for a, b in zip(pts, pts[1:]):
            E += math.dist(a, b) * rate
            w(f"G1 F{f} X{b[0]:.3f} Y{b[1]:.3f} E{E:.5f}{tag}")

    # layer 1: filled concentric pads, one per post
    z = press
    for i, (A, B, g) in enumerate(pairs):
        for r in (A, B):
            inset = W1 / 2
            while inset < POST / 2 - 1e-9:
                pts = loop_pts(r, inset, "right")
                hop(*pts[0], z, f"to pair {i} pad")
                run(pts, e1)
                inset += L1_PITCH
    top[0] = z
    stamps = []
    for k in range(2, laps + 1):
        z = round(press + (k - 1) * lh, 4)
        w(f"; ---- lap {k} of {laps}, commanded Z{z:.3f}")
        order = range(len(pairs)) if k % 2 else reversed(range(len(pairs)))
        for i in order:
            A, B, g = pairs[i]
            pa = loop_pts(A, w_b / 2, "right")
            pb = loop_pts(B, w_b / 2, "left")
            hop(*pa[0], z, f"to pair {i} post A")
            run(pa, eb)
            hop(*pb[0], z, f"to pair {i} post B")
            run(pb, eb)
            if k in blaps:
                p, q = pb[-1], pa[-1]
                air = air_span(p, q, rects)
                stamps.append((i, k, air))
                run([p, q], eb, f" ; BRIDGE span={air:.2f} pair={i} lap={k}")
        top[0] = z
    w("; ---- done")
    w("SET_GCODE_OFFSET Z=0")
    w("M107"); w("M104 S0"); w("M140 S0")
    zr, _ = machine.z_retreat(PRINTER, top[0], 20.0)
    w(f"G0 Z{zr:.3f} F900")
    os.makedirs(out_dir, exist_ok=True)
    tag = "_OVR" if over else ""
    out = os.path.join(out_dir, f"bridge_tpu1_{row}_{PRINTER}_{MATERIAL}_w{w_b:g}_lh{lh:g}"
                                f"_v{spd:.0f}_T{temp}{tag}.gcode")
    machine.emit_gcode(out, "\n".join(L) + "\n")
    print(out)
    print(f"  {laps} laps, {len(stamps)} bridges, {E * A_FIL / 1000:.2f} cm3, speed {spd:.2f} mm/s")
    return out


def check(path):
    """Re-derive each '; BRIDGE span=' from the emitted move against the stamped POST footprints."""
    rects, bad, n = [], [], 0
    x = y = None
    for ln in open(path):
        m = re.match(r"; POST pair=\d+ A=([\d.,]+) B=([\d.,]+)", ln)
        if m:
            for s in m.groups():
                rects.append(tuple(map(float, s.split(","))))
            continue
        c = ln.split(";")[0]
        g = dict(re.findall(r"\b([XY])(-?\d+(?:\.\d+)?)", c))
        nx, ny = float(g.get("X", x if x is not None else 0)), float(g.get("Y", y if y is not None else 0))
        ms = re.search(r"; BRIDGE span=([\d.]+)", ln)
        if ms and c.startswith("G1"):
            n += 1
            air = air_span((x, y), (nx, ny), rects)
            if abs(air - float(ms.group(1))) > 0.05:
                bad.append(f"stamp {ms.group(1)} vs measured {air:.2f}: {ln.strip()}")
        if c.startswith(("G0", "G1")):
            x = nx if "X" in g else x
            y = ny if "Y" in g else y
    if not rects or n == 0:
        bad.append("no POST footprints or no BRIDGE moves: nothing to check")
    return n, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--row", choices=sorted(ROWS))
    ap.add_argument("--over-limit", action="store_true",
                    help="declare a bead over the 1.5x/0.75x nozzle ceilings (R2 needs it)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    ap.add_argument("--check", metavar="GCODE")
    a = ap.parse_args()
    if a.check:
        n, bad = check(a.check)
        for b in bad:
            print("  FAIL", b)
        print(f"  {n} bridges checked, {len(bad)} mismatches")
        return 1 if bad else 0
    if not a.row:
        ap.error("--row or --check")
    emit(a.row, a.over_limit, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
