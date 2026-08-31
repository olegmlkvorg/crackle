#!/usr/bin/env python3
"""HANGERTAG FLOOR — the hanger-tag plate (26.4 x 11, hanger-tags-handoff.zip) as a single-pass
diamond-net first layer, laid as a Z LADDER of real first-layer heights so every plate is its own
first-layer coupon.

Oleg, 2026-08-31: "the first layer does not need to be solid. design a single pass grild like
shape, may be something even cooler like nucleon. also use 0.6 line width and 0.24 line height for
first layer, because this plate adhesion is real low (smooth plate), i applied thin layer of glue
to help. lets first test how fast we can print the first layer in different configurations of
speed" — and "tghe shape has to be of the zip archive, not square nucleon".

WHAT ONE CELL IS. The tag's own outline (26.4 x 11 rounded rect, hanger-tag.scad: one Avery
L4731REV label 25.4 x 10 plus a 0.5 border) drawn as ONE continuous stroke: the perimeter, a short
link inward, then a closed BILLIARD path — a p:q reflection net whose legs run at ~45 degrees, so
every bounce is a ~90 degree turn (filleted; no hairpins, which is what lets the head hold speed —
a serpentine's 180 degree row-ends are the "93% of path below 90% speed" failure the nucleon
docstring records). The net's bounces land one strand-overlap inside the perimeter, so the lattice
is welded into the frame on all four sides. Crossings weld (single layer; the bumps face UP — the
sticker face is the plate side and stays flat).

WHY A LADDER OF HEIGHTS AND NOT ONE HEIGHT. Three reasons, each structural:
  * R9 refuses an unproven (h1, w1) pair, and (0.24, 0.60) has never been on a plate here. The
    Z_LADDER declaration is the ONE counted seam for a coupon visiting unproven gaps — 3+ real
    heights at one width, measured off the file's own moves (validate.py layer1_excuse).
  * machine.ZERR['k2plus'] = 0.15 was measured 2026-08-06, before the nozzle swap this design
    assumes. A swapped nozzle can move Z zero; the ladder READS the new truth off the plate (which
    cell looks like a true flat sheet tells you the real error).
  * the weldable-height window is expected to move with speed, so each speed test carries its own
    bracket instead of citing one plate read at 50 mm/s.

THE LADDER LIVES IN COMMANDED Z, NOT IN PER-CELL OFFSETS — the opposite of zladder.py, and the
reason is measured, not taste. zladder sweeps the offset because each of its cells carries the
bucket's layer 2, and the layer-1-to-layer-2 relationship must stay identical while the plate gap
moves. This file is a SINGLE layer, and the offset sweep then breaks R9's own instrument: with
every cell at commanded Z0.100, first_layer_emitted() accumulates ALL cells into one w1 (nothing
at a second commanded Z ever ends layer 1), so a 6-height ladder metered 0.6mm wide everywhere
"measures" w1 = 0.6 x mean(h)/h1 = 0.90mm and the Z_LADDER count finds 0 cells at that width.
Proven by running it — the first emission of this file failed R9 exactly that way. So: commanded
Z steps cell by cell from PRESS_HARD (cell 1 IS the pressed press, R1's number), and ONE
SET_GCODE_OFFSET, emitted before the prime, corrects the machine's measured Z-zero error for the
whole file. Landed height = commanded + offset + zerr = the cell's label. R1 reads a pressed
first bead, R2 reads a real ladder, and w1 is measured off cell 1 alone.

SPEED IS ONE PER FILE (R3). The ladder sweeps height at one speed; the speed series is one file
per speed, each a 3-height mini-ladder bracketing the height Oleg's read of the first plate picks.
Above the 50 mm/s north star the file stamps '; SPEED_OVERRIDE=' — the declared seam validate.py
already checks — because Oleg asked for exactly this measurement.

NOZZLE 0.4 IS AN ASSUMPTION, STAMPED, NOT A MEASURED FACT. The handoff's tag is cut for 0.30mm
lines (a 0.4-nozzle profile: the scad says 0.24 plate "needs a 0.4 nozzle profile") and Oleg asked
for 0.6mm lines = 1.5x a 0.4 orifice. machine.NOZZLE still says 0.8 and is deliberately NOT edited
on an assumption — towercoupon.py records that Klipper's own config field lies about this exact
fact, so only Oleg at the machine can settle it. If the 0.8 nozzle is still mounted, a 0.6mm bead
is UNDER the orifice (unprintable — it strings into beads) and the coupon must be cancelled.

S2 AND THE MISSING PITCH — measured, so the next session does not re-walk it. send.py's S2
abstains on this file because its pitch instrument reads axis-aligned rasters only, and the
obvious fix — teach it rotated rasters — was probed on the emitted bytes and REJECTED: the
billiard's strand offsets project NON-uniformly (cell 1 measures gaps 2.12..2.36mm, modal
dominance 0.22-0.25 against the 0.70 the ledger's own evidence demands), so an honest rotated
instrument declines exactly like today's. The net genuinely has no single pitch. The standing
options, all Oleg's to pick: keep the billiard and clear S2 with a recorded --oleg-said per send;
redesign the fill as an exactly-uniform diamond crosshatch (measurable, slightly worse corners);
or give S2 a max-inscribed-void measure, which is the quantity that physically decides whether a
sticker face has backing — but that changes what the ledger stores, which is not a generator's
call.

FLOW AT SPEED, the ceiling this ladder will eventually hit: 0.6 x 0.24 = 0.144 mm2, so 50 mm/s is
7.2 mm3/s, 100 is 14.4, 200 is 28.8. Every 0.4-nozzle hotend runs out somewhere in the 20s-30s,
and machine.py's flow figures are all 0.8-nozzle numbers — so past ~150 mm/s the failure to watch
for is matte, thin, or gappy extrusion (a FLOW ceiling), not adhesion.
"""
import argparse, math, os, shlex, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import smooth

A_FIL = machine.A_FIL

# THE TAG'S OWN NUMBERS, from hanger-tags-handoff.zip / hanger-tag.scad — sticker 25.4 x 10
# (measured off the Avery PDF at 600 dpi), 0.5mm border per side. Not free parameters: change the
# scad and regenerate, never retype one side of the pair.
TAG_W = 26.4
TAG_H = 11.0

# SEVEN SEGMENTS, zladder.py's own table (copied with it: the digit is a LABEL, and the two files
# labelling plates differently would be worse than the copy).
SEG = {
    'a': (0.0, 1.0, 1.0, 1.0), 'b': (1.0, 0.5, 1.0, 1.0), 'c': (1.0, 0.0, 1.0, 0.5),
    'd': (0.0, 0.0, 1.0, 0.0), 'e': (0.0, 0.0, 0.0, 0.5), 'f': (0.0, 0.5, 0.0, 1.0),
    'g': (0.0, 0.5, 1.0, 0.5),
}
DIGIT = {'1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc', '5': 'afgcd', '6': 'afgedc',
         '7': 'abc', '8': 'abcdefg', '9': 'abcdfg'}


def tri(u):
    """Triangle wave 0 -> 1 -> 0 over one unit of u."""
    u = u % 1.0
    return 2.0 * u if u <= 0.5 else 2.0 * (1.0 - u)


def billiard(w, h, p, q, phase):
    """Closed p:q billiard (reflection) path in a w x h box, vertices only.

    x = w*tri(p*t + phase), y = h*tri(q*t) over t in [0,1]. Both coordinates are piecewise linear,
    so the path is exactly the straight legs between fold times. p, q coprime closes it.

    THE PHASE IS WHAT KEEPS IT A NET AND NOT A LINE DRAWN TWICE. With phase 0 the path launches
    from the box corner, and a billiard from a corner runs to a corner and RETRACES — every leg
    covered twice, 2x material on one track. A phase that keeps the x-folds and y-folds from ever
    coinciding means no corner is ever hit and each leg is laid once. Asserted, not assumed."""
    if math.gcd(p, q) != 1:
        raise SystemExit(f"billiard p={p}, q={q} share a factor — the path closes early and "
                         f"covers only 1/{math.gcd(p, q)} of the box.")
    tx = [(0.5 * m - phase) / p for m in range(0, 2 * p + 1)]
    tx = [t for t in tx if 1e-9 < t < 1.0 - 1e-9]
    ty = [m / (2.0 * q) for m in range(0, 2 * q + 1)]
    ty = [t for t in ty if 1e-9 < t < 1.0 - 1e-9]
    gap = min(abs(a - b) for a in tx for b in ty)
    if gap < 1e-4:
        raise SystemExit(f"billiard phase {phase} lets an x-fold and a y-fold coincide "
                         f"(gap {gap:.6f}) — that is a box corner, and a corner hit makes the "
                         f"path retrace itself. Nudge --phase.")
    ts = sorted([0.0] + tx + ty + [1.0])
    return [(w * tri(p * t + phase), h * tri(q * t)) for t in ts]


def rounded_rect(x0, y0, x1, y1, r):
    """Rounded-rect loop, CCW from (sx, y0) on the bottom edge, back to (sx, y0). Corner arcs are
    emitted as real arcs (fine enough that fillet() leaves them alone); sx is where the caller
    wants to enter and leave, so the loop's one open joint sits exactly at the lattice link."""
    def arc(cx, cy, a0, a1, n=12):
        return [(cx + r * math.cos(a0 + (a1 - a0) * k / n),
                 cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]
    sx = x0 + (x1 - x0) * 0.12
    pts = [(sx, y0), (x1 - r, y0)]
    pts += arc(x1 - r, y0 + r, -math.pi / 2, 0.0)
    pts += [(x1, y1 - r)]
    pts += arc(x1 - r, y1 - r, 0.0, math.pi / 2)
    pts += [(x0 + r, y1)]
    pts += arc(x0 + r, y1 - r, math.pi / 2, math.pi)
    pts += [(x0, y0 + r)]
    pts += arc(x0 + r, y0 + r, math.pi, 1.5 * math.pi)
    pts += [(sx, y0)]
    return pts, sx


def cell_path(ox, oy, w_line, p, q, phase, fillet_r, arc_seg):
    """ONE tag cell as one continuous polyline: perimeter loop, link inward, billiard net.

    Perimeter centerline sits half a line inside the outline; the net's box sits 0.75 lines
    inside the perimeter centerline, so every bounce overlaps the frame bead by ~25% — welded,
    not blobbed. Returns (pts, stats)."""
    px0, py0 = ox + w_line / 2.0, oy + w_line / 2.0
    px1, py1 = ox + TAG_W - w_line / 2.0, oy + TAG_H - w_line / 2.0
    rc = max(1.1 * w_line - w_line / 2.0, 0.2)          # scad's face_r = 1.1*line_w, centerline
    lat_in = 0.75 * w_line                              # bounce apex -> 25% bead overlap
    lx0, ly0 = px0 + lat_in, py0 + lat_in
    lw, lh = (px1 - px0) - 2 * lat_in, (py1 - py0) - 2 * lat_in

    net = billiard(lw, lh, p, q, phase)
    entry = (lx0 + net[0][0], ly0 + net[0][1])

    peri, sx = rounded_rect(px0, py0, px1, py1, rc)
    # The loop's joint is at (sx, py0); the link runs from there to the net's entry. Both are near
    # the bottom-left, so the link is about one line width long — drawn at full rate, a weld.
    pts = peri + [entry] + [(lx0 + x, ly0 + y) for x, y in net[1:]]
    pts = smooth.fillet(pts, fillet_r, arc_seg=arc_seg)
    pts = machine.decimate(pts)
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    return pts, {'len': length, 'verts': len(net), 'entry': entry}


def clip_walls(zmid, shaft_d, fit_clear, wall):
    """Wall CENTERLINE x-offsets (from tag centre) of the clip at height `zmid` above the plate's
    top, straight from hanger-tag.scad's tunnel(): vertical legs to leg_h, then a 45-degree gable
    closing to a point. The tunnel INNER profile is untouched (the fit is the fit); the wall sits
    half a line outside it, so a fatter wall only grows the clip outward.

    Returns [] above the apex, [x] when the two roof lines have merged into one, else [-x, +x]."""
    rho = shaft_d / 2.0
    half_w = rho + fit_clear
    leg_h = rho + (math.sqrt(2.0) - 1.0) * half_w
    xw = half_w + wall / 2.0
    if zmid > leg_h:
        xw -= (zmid - leg_h)            # the 45-degree roof: in by one mm per mm up
    if xw < -wall / 4.0:
        return []
    if xw < wall / 2.0:
        return [0.0]                    # the two lines are one weld now — draw it once
    return [-xw, xw]


def measured_speeds(path):
    """Speeds and peak implied flow read back OFF THE EMITTED FILE (nucleon's discipline: the
    summary describes the artifact, never the intention)."""
    import re as _re
    f, seen, body = 0.0, {}, False
    px = py = None
    pe = 0.0
    wflow = 0.0
    for ln in open(path):
        if 'BODY_START' in ln:
            body = True
            continue
        c = ln.split(';')[0].strip()
        if not c.startswith(('G0', 'G1')):
            continue
        mf = _re.search(r'\bF(\d+(?:\.\d+)?)', c)
        if mf:
            f = float(mf.group(1)) / 60.0
        mx = _re.search(r'\bX(-?[\d.]+)', c)
        my = _re.search(r'\bY(-?[\d.]+)', c)
        me = _re.search(r'\bE(-?[\d.]+)', c)
        nx = float(mx.group(1)) if mx else px
        ny = float(my.group(1)) if my else py
        if body and me and mx and px is not None:
            d = math.hypot(nx - px, ny - py)
            de = float(me.group(1)) - pe
            if d > 1e-6 and de > 0 and f:
                seen[round(f, 1)] = seen.get(round(f, 1), 0) + 1
                wflow = max(wflow, de * A_FIL / d * f)
        if me:
            pe = float(me.group(1))
        px, py = nx, ny
    return sorted(seen), sum(seen.values()), wflow


def emit_full(a, material, temp, bed, bx, by, press, zerr):
    """The LENGTHTEST as full native pieces: N tags, every floor the SAME proven gap, the clip
    walls stacked above, layer-major across the row.

    LAYER-MAJOR, NOT SEQUENTIAL, and the reason is the head, not the gates: machine.HEAD_R says
    everything within ~50mm of the nozzle sweeps at head height, so finishing tag 1 to its 6.6mm
    apex and then descending to tag 2's floor 32mm away would drive the heater block through the
    finished part. Z here only ever climbs; between strokes the head hops LIFTED and '; HOP'
    tagged, so the no-travel rule's licensed exception is the only travel in the file."""
    lens = [float(s) for s in a.clip_lens.split(",") if s.strip()]
    n = len(lens)
    if not 1 <= n <= 9:
        sys.exit(f"REFUSING TO EMIT: {n} clip lengths; 1..9 tags fit the digit labels.")
    if any(l <= 0 or l > TAG_H - 1.0 for l in lens):
        sys.exit(f"REFUSING TO EMIT: a clip length in {lens} is outside (0, {TAG_H - 1.0:g}] — "
                 f"the tunnel lies along the tag's {TAG_H:g}mm height.")
    if a.h1 is None:
        sys.exit("REFUSING TO EMIT: full pieces need --h1, the ladder cell Oleg read as welded. "
                 "The whole point of the ladder was to make this number a citation, not a guess.")
    h1s = [float(s) for s in str(a.h1).split(",") if s.strip()]
    if len(h1s) == 1:
        h1s = h1s * n
    if len(h1s) != n:
        sys.exit(f"REFUSING TO EMIT: {len(h1s)} floor heights for {n} tags — one each, or one "
                 f"for all.")
    if h1s != sorted(h1s):
        sys.exit("REFUSING TO EMIT: floor heights must ascend with the tags, so commanded Z only "
                 "ever climbs across the row.")
    ladder = len(set(h1s)) >= 3
    if a.speed > machine.MAX_SPEED + 1e-9:
        sys.exit(f"REFUSING TO EMIT: {a.speed:g} mm/s on a full PIECE. The SPEED_OVERRIDE seam is "
                 f"for measurement coupons; a part never carries it (machine.MAX_SPEED).")
    proven = any(abs(h1s[0] - p[0]) <= 0.005 and abs(a.w1 - p[1]) <= 0.05
                 for p in machine.PROVEN_LAYER1.get(a.printer, []))
    coupon = None
    if a.coupon:
        cf, _, cdate = a.coupon.partition(":")
        coupon = (cf, cdate)
        cpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.out, cf)
        if not os.path.isfile(cpath) and not os.path.isfile(cf):
            sys.exit(f"REFUSING TO EMIT: cited coupon '{cf}' is not in {a.out}/ — a citation to a "
                     f"file nobody can open proves nothing (R9's own clause).")
    if not proven and coupon is None and not ladder:
        sys.exit(f"REFUSING TO EMIT: ({h1s[0]:g}, {a.w1:g}) is not in PROVEN_LAYER1[{a.printer!r}] "
                 f"and no --coupon cites the ladder cell that welded. R9 would refuse the file; "
                 f"refusing here says why sooner. (A comma list of 3+ floors is its own ladder.)")

    zoff = round(h1s[0] - press - zerr, 4)
    speed1 = a.speed1 if a.speed1 else a.speed
    if speed1 > machine.MAX_SPEED + 1e-9:
        sys.exit(f"REFUSING TO EMIT: --speed1 {speed1:g} is above the north star.")
    f1 = round(speed1 * 60)
    e_wall = a.wall * a.layer_h / A_FIL
    flow_wall = a.wall * a.layer_h * a.speed
    flows = [a.w1 * h * speed1 for h in h1s] + [flow_wall]
    f_body = round(a.speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)

    stride = TAG_W + a.gap
    row_w = n * TAG_W + (n - 1) * a.gap
    if row_w > bx - 60:
        sys.exit(f"REFUSING TO EMIT: {n} tags need {row_w:.0f}mm and the plate has {bx - 60:.0f}.")
    x0 = (bx - row_w) / 2.0
    oy = by / 2.0 - TAG_H / 2.0
    yc = oy + TAG_H / 2.0
    dw, dh = 6.0, 10.0
    dy = oy + TAG_H + 3.0

    v_eff = min(a.speed, math.sqrt(machine.ACCEL * a.fillet))
    arc_seg = max(0.25, v_eff / 220.0)
    e1s = [machine.layer1_rate(a.w1, h) for h in h1s]
    zbase = [round(press + (h - h1s[0]), 3) for h in h1s]   # each floor's commanded Z
    cells = [cell_path(x0 + i * stride, oy, a.w1, a.p, a.q, a.phase, a.fillet, arc_seg)
             for i in range(n)]

    # the wall layer schedule, shared by every tag (same shaft, same profile — only length varies)
    K = 0
    sched = []
    while True:
        zmid = (K + 0.5) * a.layer_h
        xs = clip_walls(zmid, a.shaft, a.fit_clear, a.wall)
        if not xs:
            break
        K += 1
        sched.append(xs)
    rho = a.shaft / 2.0
    leg_h = rho + (math.sqrt(2.0) - 1.0) * (rho + a.fit_clear)

    L = []
    w = L.append
    w(f"; HANGERTAG FULL x{n} — the LENGTHTEST as native pieces: tunnel lengths "
      f"{a.clip_lens}mm left to right, {a.p}:{a.q} net floors {a.w1:g}mm wide at "
      f"{','.join(f'{h:g}' for h in h1s)}mm"
      + (" — the floors ARE the next ladder rung set" if ladder else ""))
    w(f"; PRINTER={a.printer}")
    w(f"; CMD={' '.join(shlex.quote(s) for s in [os.path.basename(sys.argv[0])] + sys.argv[1:])}")
    w(f"; MATERIAL={material}")
    w(f"; LAYER_H={a.layer_h:g}")
    _qlo, _qhi = min(flows), max(flows)
    if abs(_qlo - _qhi) < 1e-9:
        w(f"; FLOW={_qlo:g}")
    else:
        w(f"; FLOW=VARIABLE:{round(_qlo, 3):g}..{round(_qhi, 3):g}")
    w(f"; SPEED={a.speed:.4f}")
    if abs(speed1 - a.speed) > 1e-9:
        w(f"; SPEED_LAYER1={speed1:.4f}")
        w(f";   way slower than the {a.speed:g} body BY INSTRUCTION — Oleg 2026-08-31: 'make "
          f"first layer way slower, adhestion is bad on this suface'. The floor dwells; the "
          f"walls do not need to.")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; PRINT_TEMP={temp}")
    w(f"; bead {a.wall:g}x{a.layer_h:g}")
    w(f"; FLOW_DERATE=the clip wall IS one {a.wall:g}x{a.layer_h:g} line — the tag's whole design "
      f"(hanger-tags-handoff.zip) — so {flow_wall:g} mm3/s at the {a.speed:g} mm/s north star is "
      f"the operating point. Widening the bead would thicken a wall whose thickness is the part.")
    w(f"; NOZZLE={a.nozzle:g} — corroborated by the plate 2026-08-31: the ladder's 0.6mm lines "
      f"welded (cell 6 read by Oleg), and an 0.8 orifice cannot lay a 0.6 bead at all. "
      f"machine.NOZZLE still carries the pre-swap 0.8 until he says the word at the machine.")
    if coupon:
        w(f"; COUPON={coupon[0]} h1={h1s[0]:.3f} w1={a.w1:.2f} verdict=welded read={coupon[1]}")
    if ladder:
        w("; Z_LADDER=1")
    w(f"; LAYER1_WIDTH={a.w1:.2f}mm landed in EVERY floor, cell 1 metered for the {h1s[0]:g} gap"
      + (f"; THE FLOOR GAP IS ALSO SWEPT {min(h1s):g}..{max(h1s):g} by commanded Z, one height "
         f"per tag, so the plate that delivers the pieces also answers which floor grips"
         if ladder else "."))
    if zoff > 0:
        w(f"; OFFSET +{zoff:.3f} SITS ABOVE THE MACHINE'S OWN ZERO, and that is the PLATE's word, "
          f"not a guess: machine.zoff_for refuses positive for parts because an uncorrected "
          f"machine was the standing defect — but every 2026-08-31 read pointed above the zero "
          f"(the clean-nozzle strip's best cell was its TOP rung), so the floors explore up. "
          f"{'A counted ladder may visit gaps nothing has proven; that is what it is for.' if ladder else 'The citation above is the license.'}")
    w(";")
    w("; ---------------- WHAT THIS IS ----------------")
    w(f"; {n} complete hanger tags: one {a.layer_h:g} net floor (sticker face down, ~57% net) and")
    w(f"; the clip above it — vertical legs to {leg_h:.2f}mm, then the 45deg gable, ONE "
      f"{a.wall:g}mm line per layer,")
    w(f"; {K} wall layers, apex ~{(K * a.layer_h):.1f}mm over the floor. Layer overlap on the "
      f"roof: {100 * (1 - a.layer_h / a.wall):.0f}%")
    w(f"; (the handoff's 0.30 wall gave 20% — that open question is what this plate answers, "
      f"per length).")
    w(";")
    for i, l in enumerate(lens):
        tilt = math.degrees(math.atan2(2 * a.fit_clear, l))
        w(f";   tag {i + 1}  tunnel {l:g}mm  (rocks ~{tilt:.0f}deg on the shaft — the trade the "
          f"LENGTHTEST measures)")
    w(";")
    w("; READ IT: does each roof BOND (the 45deg single-line gable), and how short a tunnel still")
    w("; threads a hanger hook without wobbling loose. Tag 5's 0.6mm tunnel is 2-3 lines long —")
    w("; the handoff predicted slicers drop it; native gcode draws it, so the plate decides.")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {K + 1}"); w("; HEADER_BLOCK_END")

    w("M82")
    w("G90")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    machine.home(w, a.printer, calibrate=a.calibrate)
    w("SET_GCODE_OFFSET Z=0                 ; clear whatever the last job left")
    w(f"SET_GCODE_OFFSET Z={zoff:.3f} MOVE=0   ; commanded Z + this + the {zerr:+.3f} machine "
      f"error = tag 1's floor at {h1s[0]:g} (taller floors climb by commanded Z)")
    w(f"M190 S{bed:.0f}")
    w(f"M109 S{temp}")
    w("M107                                 ; fans OFF for layer 1 — the plate weld is the job")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")
    machine.prime(w, printer=a.printer, z=press,
                  rate=e1s[0], feed=f1, travel_feed=travel_f,
                  avoid=(("rect", x0 - 2, oy - 2, x0 + row_w + 2, dy + dh + 2),),
                  near=(x0, oy))
    w("; BODY_START")

    E = 0.0

    def hop(tx, ty, note, lift):
        w(f"G0 Z{lift:.3f} F1800   ; HOP lift, clear of everything laid")
        w(f"G0 X{tx:.3f} Y{ty:.3f} F{travel_f}   ; HOP {note}")

    # ---- layer 1: every tag's digit and net, all at the one proven gap
    for i in range(n):
        pts, st = cells[i]
        e1 = e1s[i]
        zb = zbase[i]
        dx = x0 + i * stride + (TAG_W - dw) / 2.0
        w(f"; ---- layer 1, tag {i + 1}: digit + net at commanded Z{zb:.3f}, floor "
          f"{h1s[i]:.3f}mm real ({a.w1 * h1s[i]:.4f} mm2/mm)")
        for s in DIGIT[str(i + 1)]:
            u0, v0, u1, v1 = SEG[s]
            ax, ay = dx + u0 * dw, dy + v0 * dh
            bx_, by_ = dx + u1 * dw, dy + v1 * dh
            hop(ax, ay, f"to digit {i + 1} segment '{s}'", zbase[-1] + 1.0)
            w(f"G1 F600 Z{zb:.3f}")
            E += math.hypot(bx_ - ax, by_ - ay) * e1
            w(f"G1 F{f1} X{bx_:.3f} Y{by_:.3f} E{E:.5f} ; digit segment '{s}'")
        hop(pts[0][0], pts[0][1], f"to tag {i + 1} net", zbase[-1] + 1.0)
        w(f"G1 F600 Z{zb:.3f}")
        w(f"G1 F{f1} X{pts[1][0]:.3f} Y{pts[1][1]:.3f} "
          f"E{(E := E + math.dist(pts[0], pts[1]) * e1):.5f}")
        for j in range(2, len(pts)):
            E += math.dist(pts[j - 1], pts[j]) * e1
            w(f"G1 X{pts[j][0]:.3f} Y{pts[j][1]:.3f} E{E:.5f}")

    _fan = int(round(machine.fan_for(material, machine.FAN_MAX.get(material, 0.2)) * 255))
    w(f"M106 S{_fan}      ; floors have bonded — {material}'s capped cooling for the walls")

    # ---- the clip, layer-major across the row
    for k in range(1, K + 1):
        xs = sched[k - 1]
        w(f"; ---- wall layer {k} of {K}: "
          f"{'legs' if (k - 0.5) * a.layer_h <= leg_h else 'roof'} at x "
          f"{','.join(f'{x:+.2f}' for x in xs)} (commanded Z per tag: its floor + {k}*{a.layer_h:g})")
        lift = zbase[-1] + k * a.layer_h + 0.8
        for i in range(n):
            ck = round(zbase[i] + k * a.layer_h, 3)
            cx = x0 + i * stride + TAG_W / 2.0
            half = lens[i] / 2.0
            for m, x in enumerate(xs):
                ya, yb = (yc - half, yc + half) if (k + m) % 2 == 0 else (yc + half, yc - half)
                hop(cx + x, ya, f"to tag {i + 1} wall x{x:+.2f}", lift)
                w(f"G1 F600 Z{ck:.3f}")
                E += lens[i] * e_wall
                w(f"G1 F{f_body} X{cx + x:.3f} Y{yb:.3f} E{E:.5f} ; wall")

    w("; ---- done")
    w("SET_GCODE_OFFSET Z=0                 ; hand the machine back at its own zero")
    w("M107"); w("M104 S0"); w("M140 S0")
    w("G0 Z45 F900")
    w(f"G0 X10 Y{by - 10:.0f} F{travel_f}")
    w("M84")

    _htag = f"{h1s[0]:g}" if len(set(h1s)) == 1 else f"{min(h1s):g}-{max(h1s):g}"
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.out,
                       f"hangertag_full{n}_{a.printer}_{material}_w{a.w1:g}_wall{a.wall:g}"
                       f"_h1-{_htag}_len{max(lens):g}-{min(lens):g}_v{a.speed:g}.gcode")
    machine.emit_gcode(out, "\n".join(L) + "\n")
    vol = E * A_FIL / 1000.0
    print(out)
    print(f"  {n} FULL tags, tunnels {a.clip_lens}mm, floors "
          f"{','.join(f'{h:g}' for h in h1s)}x{a.w1:g} at {speed1:g} mm/s "
          f"(offset {zoff:+.3f} vs zerr {zerr:+.3f}), wall {a.wall:g}x{a.layer_h:g} at "
          f"{a.speed:g}, {K + 1} layers")
    print(f"  {vol:.2f}cm3 / {vol * 1.24:.1f}g  roof overlap "
          f"{100 * (1 - a.layer_h / a.wall):.0f}% (handoff's 0.30 wall gave 20%)")
    spds, moves, wflow = measured_speeds(out)
    print(f"  MEASURED in the file: {'/'.join(f'{s:g}' for s in spds)} mm/s over {moves} "
          f"extruding moves" + ("   !! MORE THAN ONE SPEED — R3 violation" if len(spds) > 1 else ""))
    print(f"  peak implied flow {wflow:.1f} mm3/s")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--speed", type=float, default=50.0,
                    help="the ONE speed of this file, mm/s (R3). Above the 50 north star the file "
                         "stamps '; SPEED_OVERRIDE=' — validate.py's declared seam — because this "
                         "series exists to measure speed (Oleg, 2026-08-31). One file per speed.")
    ap.add_argument("--heights", default="0.10,0.16,0.20,0.24,0.28,0.32",
                    help="REAL first-layer heights, ascending, one tag cell each. Commanded Z "
                         "steps with the cells from PRESS_HARD (cell 1 must be a height the "
                         "machine can press: first height <= PRESS_HARD + zerr, since the ONE "
                         "global offset may not be positive). 3+ distinct heights is what makes "
                         "the file its own R9 coupon ('; Z_LADDER=1', counted). Material scales "
                         "with each cell's gap so every cell lands the same --w1 width.")
    ap.add_argument("--w1", type=float, default=0.6,
                    help="landed line width, mm. Oleg's number for the tag floor: 0.6 = 1.5x the "
                         "0.4 nozzle this design assumes.")
    ap.add_argument("--nozzle", type=float, default=0.4,
                    help="orifice this file ASSUMES is mounted. Not machine.NOZZLE (0.8, "
                         "pre-swap): only Oleg at the machine can confirm the swap, and the stamp "
                         "makes the assumption cancellable rather than silent.")
    ap.add_argument("--layer-h", type=float, default=0.24,
                    help="the tag design's layer height (the plate IS one 0.24 layer).")
    ap.add_argument("--p", type=int, default=3, help="billiard x-cycles; with q sets the net")
    ap.add_argument("--q", type=int, default=8,
                    help="billiard y-cycles. 3:8 in the tag's box runs the legs at ~45 deg, so "
                         "every bounce is ~90 deg — no hairpins, the head holds speed.")
    ap.add_argument("--phase", type=float, default=0.031,
                    help="billiard phase; keeps fold families apart (asserted in billiard()).")
    ap.add_argument("--fillet", type=float, default=0.8,
                    help="bounce fillet radius, mm. sqrt(accel*r) is the speed a corner holds "
                         "(63 mm/s at 0.8/5000); past that the planner brakes locally, commanded "
                         "F stays constant, deposit per mm is unchanged — E is per mm.")
    ap.add_argument("--gap", type=float, default=6.0, help="clear plate between tag cells, mm")
    ap.add_argument("--zerr", type=float, default=None,
                    help="Z-zero error, mm. Default machine.ZERR[printer]; refused if unmeasured.")
    ap.add_argument("--clip-lens", default=None,
                    help="FULL-PIECE MODE: comma list of tunnel lengths mm, one tag each — the "
                         "handoff's LENGTHTEST (8.2,4.1,2.4,1.2,0.6 answers 'how short can the "
                         "holder go'). Every floor prints at ONE --h1, the clip walls stack above, "
                         "layer-major across the row so the head never returns down past a "
                         "standing part.")
    ap.add_argument("--h1", default=None,
                    help="full-piece floor gap, mm — one value (the ladder cell Oleg read as "
                         "welded, cited via --coupon), or a comma list ONE PER TAG, ascending: "
                         "the floors then form their own counted Z ladder ('; Z_LADDER=1'), for "
                         "the state where the frame moved again and Oleg wants pieces, not "
                         "another bare measuring strip (2026-08-31: 'i asked to print whole "
                         "pieces').")
    ap.add_argument("--coupon", default=None,
                    help="R9 citation '<coupon-file>:<YYYY-MM-DD>' — the ladder plate and the day "
                         "Oleg read it. Required when (--h1, --w1) is not in PROVEN_LAYER1.")
    ap.add_argument("--shaft", type=float, default=4.6,
                    help="shaft diameter the tunnel swallows (std bore, hanger-tag.scad clip_id)")
    ap.add_argument("--fit-clear", type=float, default=0.3, help="radial clearance, scad's number")
    ap.add_argument("--wall", type=float, default=0.4,
                    help="clip wall, ONE line per layer. DEVIATES from the handoff's 0.30 with the "
                         "reason recorded: 0.30 is under this 0.4 orifice (the house floor — melt "
                         "necks below the hole), and 0.4 lifts the 45deg roof's layer-to-layer "
                         "overlap from 20%% to 40%% — the handoff's own #1 open risk. The tunnel "
                         "INNER profile is untouched; the wall grows outward only.")
    ap.add_argument("--speed1", type=float, default=None,
                    help="FIRST-LAYER speed for full-piece mode, mm/s (default: --speed). "
                         "Oleg, 2026-08-31, after the full plate\'s floor failed to grip the "
                         "smooth glued plate at 50: \'make first layer way slower, adhestion "
                         "is bad on this suface\'. His word overrules the speed-is-not-a-lever "
                         "doctrine FOR THIS SURFACE; a declared \'; SPEED_LAYER1=\' regime, the "
                         "same seam zladder\'s half-speed layer 1 uses.")
    ap.add_argument("--calibrate", action="store_true",
                    help="run a FULL bed-mesh probe before printing instead of loading the "
                         "saved mesh — the first print after a restart or nozzle change "
                         "(Oleg, 2026-08-31). Costs ~6 measured minutes, buys a bed the "
                         "machine has actually seen since it changed.")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    material = a.material or machine.LOADED[a.printer]
    temp = machine.MATERIAL_TEMP[material]
    bed = machine.bed_for(material, a.printer)
    bx, by = machine.BED[a.printer]
    press = machine.PRESS_HARD
    zerr = a.zerr if a.zerr is not None else machine.ZERR.get(a.printer)
    if zerr is None:
        sys.exit(f"REFUSING TO EMIT: no measured Z-zero error for {a.printer!r} "
                 f"(machine.ZERR has {sorted(machine.ZERR)}) and none was passed. A ladder built "
                 f"on a guessed zero labels every cell wrong.")
    if a.w1 < a.nozzle:
        sys.exit(f"REFUSING TO EMIT: --w1 {a.w1:g} is under the {a.nozzle:g}mm orifice this file "
                 f"assumes — a nozzle cannot lay a bead narrower than its hole; the melt stretches "
                 f"thin and breaks into beads.")

    if a.clip_lens:
        if a.wall < a.nozzle:
            sys.exit(f"REFUSING TO EMIT: --wall {a.wall:g} is under the {a.nozzle:g}mm orifice — "
                     f"same floor as --w1. The handoff's 0.30 needs a slicer's under-orifice "
                     f"tricks; this toolchain does not lay beads narrower than the hole.")
        return emit_full(a, material, temp, bed, bx, by, press, zerr)

    hts = [float(s) for s in a.heights.split(",") if s.strip()]
    if len(set(hts)) < 3:
        sys.exit(f"REFUSING TO EMIT: {len(set(hts))} distinct height(s). Three or more is what "
                 f"lets the file declare '; Z_LADDER=1' and be its own R9 coupon; fewer is a part "
                 f"printing an unproven first layer, which R9 exists to refuse.")
    if any(h <= 0 for h in hts):
        sys.exit(f"REFUSING TO EMIT: non-positive height in {hts}.")
    if hts != sorted(hts) or len(hts) != len(set(hts)):
        sys.exit(f"REFUSING TO EMIT: heights must be strictly ascending — the commanded-Z ladder "
                 f"climbs with the cells, so a descent would read as the nozzle diving back into "
                 f"finished work. Got {hts}.")
    # ONE offset for the whole file, before the prime. zoff_for refuses a positive result — a
    # positive offset lifts the nozzle above the machine's own zero, which is the defect the three
    # cancelled bucket starts printed in. Heights ABOVE press+zerr are reached by commanded Z.
    try:
        zoff = machine.zoff_for(hts[0], zerr)
    except ValueError as exc:
        sys.exit(f"REFUSING TO EMIT: {exc}\n  Start the ladder at or below "
                 f"{press + zerr:g}mm; taller cells climb by commanded Z instead.")
    zc = [round(press + (h - hts[0]), 3) for h in hts]      # commanded Z per cell; cell 1 = press

    over = a.speed > machine.MAX_SPEED + 1e-9
    if over:
        print(f"  !! {a.speed:g} mm/s is ABOVE the {machine.MAX_SPEED:g} north star. Stamping "
              f"'; SPEED_OVERRIDE={a.speed:g}' — the declared seam validate.py checks — because "
              f"this file IS the speed measurement Oleg asked for. A part never carries this.")
    flow_per_h = [round(a.w1 * h * a.speed, 4) for h in hts]
    q_lo, q_hi = min(flow_per_h), max(flow_per_h)

    n = len(hts)
    stride = TAG_W + a.gap
    row_w = n * TAG_W + (n - 1) * a.gap
    if row_w > bx - 60:
        sys.exit(f"REFUSING TO EMIT: {n} tags need {row_w:.0f}mm and the plate has {bx - 60:.0f} "
                 f"usable. Fewer cells or a smaller --gap.")
    x0 = (bx - row_w) / 2.0
    oy = by / 2.0 - TAG_H / 2.0
    dw, dh = 6.0, 10.0
    dy = oy + TAG_H + 3.0

    # Corner speed the fillet actually holds; arc sampling follows it so the move rate stays under
    # the host's measured stall (machine.MAX_MOVES_PER_SEC) even inside a fillet.
    v_eff = min(a.speed, math.sqrt(machine.ACCEL * a.fillet))
    arc_seg = max(0.25, v_eff / 220.0)

    f_body = round(a.speed * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    safe_z = zc[-1] + 1.2       # commanded frame; physically 1.2mm above the tallest cell

    cells = []
    for i, h in enumerate(hts):
        pts, st = cell_path(x0 + i * stride, oy, a.w1, a.p, a.q, a.phase, a.fillet, arc_seg)
        cells.append((pts, st))

    L = []
    w = L.append
    w(f"; HANGERTAG FLOOR — {n} tag cells ({TAG_W:g}x{TAG_H:g} outline from "
      f"hanger-tags-handoff.zip), single-pass {a.p}:{a.q} billiard net at ONE speed "
      f"{a.speed:g} mm/s, first-layer heights {a.heights} by offset")
    w(f"; PRINTER={a.printer}")
    w(f"; CMD={' '.join(shlex.quote(s) for s in [os.path.basename(sys.argv[0])] + sys.argv[1:])}")
    w(f"; MATERIAL={material}")
    w(f"; LAYER_H={a.layer_h:g}")
    if abs(q_lo - q_hi) < 1e-9:
        w(f"; FLOW={q_lo:g}")
    else:
        w(f"; FLOW=VARIABLE:{q_lo:g}..{q_hi:g}")
    w(f"; SPEED={a.speed:.4f}")
    if over:
        w(f"; SPEED_OVERRIDE={a.speed:g}")
        w(f";   above the {machine.MAX_SPEED:g} north star BY INSTRUCTION — Oleg, 2026-08-31: "
          f"\"lets first test how fast we can print the first layer in different configurations "
          f"of speed\". A coupon measuring speed, never a part.")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; PRINT_TEMP={temp}")
    w(f"; bead {a.w1:g}x{a.layer_h:g}")
    w(f"; NOZZLE={a.nozzle:g} ASSUMED, not measured: the handoff tag is cut for 0.30mm lines (a "
      f"0.4-nozzle profile) and 0.6 = 1.5x a 0.4 orifice. machine.NOZZLE still records the 0.8 "
      f"and is not edited on an assumption. IF THE 0.8 IS STILL MOUNTED, a {a.w1:g}mm bead is "
      f"UNDER the orifice and this coupon strings — cancel it at the screen.")
    w(f"; LAYER1_WIDTH={a.w1:.2f}mm landed in EVERY cell, cell 1 metered for the {hts[0]:g} gap. "
      f"THE GAP IS THE VARIABLE, swept {min(hts):g}..{max(hts):g}mm by COMMANDED Z; the material "
      f"scales with each cell's gap so the width stays constant and the gap is the only "
      f"difference between cells.")
    w("; Z_LADDER=1")
    w(f"; SEQUENTIAL={n} tag cells, lifted hops between, nothing stacked across cells")
    w(";")
    w("; ---------------- WHAT THIS IS ----------------")
    w(f"; The hanger-tag PLATE (one {a.layer_h:g} layer, sticker face DOWN on the plate) as a")
    w(f"; non-solid single-stroke net: perimeter + link + {a.p}:{a.q} billiard, ~45 deg legs,")
    w(f"; ~90 deg filleted bounces (r={a.fillet:g}). Net path {cells[0][1]['len']:.0f}mm/cell, ")
    w(f"; coverage ~{cells[0][1]['len'] * a.w1 / (TAG_W * TAG_H) * 100:.0f}% of the tag footprint.")
    w(f"; COMMANDED Z climbs with the cells from Z{press:.3f} (cell 1 IS the pressed press, R1's")
    w(f"; number); ONE SET_GCODE_OFFSET Z={zoff:.3f}, emitted before the prime, corrects the")
    w(f"; MEASURED (2026-08-06, pre-swap) Z-zero error {zerr:+.3f} for the whole file. If the")
    w("; nozzle swap moved the zero, the ladder shows it: the cell that reads as a flat welded")
    w("; sheet is the true gap, whatever its label says.")
    w(";")
    for i, h in enumerate(hts):
        w(f";   cell {i + 1}  first layer {h:.3f}mm REAL (commanded Z{zc[i]:.3f}), "
          f"{a.w1 * h:.4f} mm2/mm, {flow_per_h[i]:g} mm3/s at {a.speed:g} mm/s")
    w(";")
    w("; READ IT: thumb-peel a corner of each cell. Welded fights back and leaves colour;")
    w("; not welded lifts whole with a glossy underside. Too high reads as round separate")
    w("; strands; too low as ridges/scrape. Past ~150 mm/s watch for matte/thin/gappy lines —")
    w("; that is the 0.4 nozzle's FLOW ceiling, not adhesion. The best cell's NUMBER is the")
    w("; height the speed series brackets.")
    w("; HEADER_BLOCK_START"); w("; total layer number: 1"); w("; HEADER_BLOCK_END")

    w("M82")
    w("G90")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")                      # R7: nozzle commanded hot BEFORE the probe
    machine.home(w, a.printer, calibrate=a.calibrate)
    w("SET_GCODE_OFFSET Z=0                 ; clear whatever the last job or a hand command left")
    w(f"SET_GCODE_OFFSET Z={zoff:.3f} MOVE=0   ; the ONE correction: commanded Z + this + the "
      f"{zerr:+.3f} machine error = the cell's labelled height")
    w(f"M190 S{bed:.0f}")
    w(f"M109 S{temp}")
    w("M107                                 ; fans OFF — single layer, the plate weld is the job")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")

    # The offset is global and already in force, so the prime lands in cell 1's own gap and is
    # metered for exactly that — the prime IS the part's first layer failing in 8 seconds or not.
    machine.prime(w, printer=a.printer, z=press,
                  rate=machine.layer1_rate(a.w1, hts[0]), feed=f_body,
                  travel_feed=travel_f,
                  avoid=(("rect", x0 - 2, oy - 2, x0 + row_w + 2, dy + dh + 2),),
                  near=(x0, oy))
    w("; BODY_START")

    E = 0.0

    def hop(tx, ty, note):
        w(f"G0 Z{safe_z:.3f} F1800   ; HOP lift, clear of everything laid")
        w(f"G0 X{tx:.3f} Y{ty:.3f} F{travel_f}   ; HOP {note}")

    total_mm = 0.0
    for i, h in enumerate(hts):
        pts, st = cells[i]
        e1 = machine.layer1_rate(a.w1, h)
        w(f"; ---- part {i + 1}: tag cell {i + 1}, first layer {h:.3f}mm REAL "
          f"(commanded Z{zc[i]:.3f} + offset {zoff:.3f} + machine error {zerr:+.3f}), "
          f"{a.w1 * h:.4f} mm2/mm")

        # the digit first, at this cell's own settings — the label is itself a sample
        dx = x0 + i * stride + (TAG_W - dw) / 2.0
        for s in DIGIT[str(i + 1)]:
            u0, v0, u1, v1 = SEG[s]
            ax, ay = dx + u0 * dw, dy + v0 * dh
            bx_, by_ = dx + u1 * dw, dy + v1 * dh
            hop(ax, ay, f"to digit {i + 1} segment '{s}'")
            w(f"G1 F600 Z{zc[i]:.3f}")
            E += math.hypot(bx_ - ax, by_ - ay) * e1
            w(f"G1 F{f_body} X{bx_:.3f} Y{by_:.3f} E{E:.5f} ; digit segment '{s}'")

        hop(pts[0][0], pts[0][1], f"to cell {i + 1} perimeter start")
        w(f"G1 F600 Z{zc[i]:.3f}")
        w(f"; ---- cell {i + 1} net: perimeter + {a.p}:{a.q} billiard, one stroke, "
          f"{st['len']:.0f}mm at {a.speed:g} mm/s")
        w(f"G1 F{f_body} X{pts[1][0]:.3f} Y{pts[1][1]:.3f} "
          f"E{(E := E + math.dist(pts[0], pts[1]) * e1):.5f}")
        for j in range(2, len(pts)):
            E += math.dist(pts[j - 1], pts[j]) * e1
            w(f"G1 X{pts[j][0]:.3f} Y{pts[j][1]:.3f} E{E:.5f}")
        total_mm += st['len']

    w("; ---- done")
    w("SET_GCODE_OFFSET Z=0                 ; hand the machine back at its own zero")
    w("M107"); w("M104 S0"); w("M140 S0")
    w("G0 Z45 F900")
    w(f"G0 X10 Y{by - 10:.0f} F{travel_f}")
    w("M84")

    tag = f"v{a.speed:g}" + ("_OVR" if over else "")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.out,
                       f"hangertag_floor_{a.printer}_{material}_w{a.w1:g}_lh{a.layer_h:g}"
                       f"_h{min(hts):g}-{max(hts):g}x{n}_{tag}.gcode")
    machine.emit_gcode(out, "\n".join(L) + "\n")

    vol = E * A_FIL / 1000.0
    print(out)
    print(f"  {n} tag cells, heights {a.heights} via commanded Z "
          f"{', '.join(f'{z:.3f}' for z in zc)} + one offset {zoff:.3f} against zerr {zerr:+.3f}")
    print(f"  net {cells[0][1]['len']:.0f}mm/cell ({cells[0][1]['verts']} billiard verts), "
          f"coverage ~{cells[0][1]['len'] * a.w1 / (TAG_W * TAG_H) * 100:.0f}%, "
          f"{vol:.2f}cm3 / {vol * 1.24:.1f}g total")

    # MEASURED FROM THE EMITTED FILE, never recomputed from the inputs (nucleon's discipline).
    import re as _re
    _f, _seen, _body = 0.0, {}, False
    _px = _py = None
    _pe = 0.0
    _wflow = 0.0
    for _ln in open(out):
        if 'BODY_START' in _ln:
            _body = True
            continue
        _c = _ln.split(';')[0].strip()
        if not _c.startswith(('G0', 'G1')):
            continue
        _mf = _re.search(r'\bF(\d+(?:\.\d+)?)', _c)
        if _mf:
            _f = float(_mf.group(1)) / 60.0
        _mx = _re.search(r'\bX(-?[\d.]+)', _c)
        _my = _re.search(r'\bY(-?[\d.]+)', _c)
        _me = _re.search(r'\bE(-?[\d.]+)', _c)
        _nx = float(_mx.group(1)) if _mx else _px
        _ny = float(_my.group(1)) if _my else _py
        if _body and _me and _mx and _px is not None:
            _d = math.hypot(_nx - _px, _ny - _py)
            _de = float(_me.group(1)) - _pe
            if _d > 1e-6 and _de > 0 and _f:
                _seen[round(_f, 1)] = _seen.get(round(_f, 1), 0) + 1
                _wflow = max(_wflow, _de * A_FIL / _d * _f)
        if _me:
            _pe = float(_me.group(1))
        _px, _py = _nx, _ny
    _spds = sorted(_seen)
    print(f"  MEASURED in the file: {'/'.join(f'{s:g}' for s in _spds)} mm/s over "
          f"{sum(_seen.values())} extruding moves"
          + ("   !! MORE THAN ONE SPEED — R3 violation" if len(_spds) > 1 else "")
          + (f"   (SPEED_OVERRIDE={a.speed:g} declared)" if over else ""))
    print(f"  peak implied flow {_wflow:.1f} mm3/s (0.4-nozzle ceiling UNMEASURED — "
          f"listen/look past ~150 mm/s)")


if __name__ == "__main__":
    main()
