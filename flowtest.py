#!/usr/bin/env python3
"""Max volumetric flow test — ONE LAYER, Archimedean SPIRAL, flow ramping outward.

Q (mm3/s) = line_width x layer_height x speed. The hotend can only melt so fast; past that it
under-extrudes no matter what you command. This finds that ceiling.

WHY A SPIRAL AND NOT SERPENTINE ROWS (Oleg, 2026-07-25: "we have sharp turns in this test")
  Serpentine rows reverse 180 degrees at every row end. The head must decelerate to zero and
  accelerate back, so commanded feedrate is NOT actual feedrate near the ends — and a flow test is
  only valid if the head really reaches the speed you asked for. A spiral never turns: one
  continuous path, curvature decreasing smoothly, so speed is genuinely constant.

  Orientation matters too. Flow ramps OUTWARD, so the highest flow lands at the largest radius —
  the gentlest curvature on the plate. The fastest moves get the straightest geometry. Low flow
  sits in the tight centre where the head would be slow anyway.

WHY A SINGLE LAYER (learned the hard way, 2026-07-25)
  v1 stacked a tower with 3 mm lines from a 0.8 mm nozzle. Commanded cross-section (3 x 0.4 =
  1.2 mm2/mm) is conserved, but a round orifice cannot spread that far: the bead landed ~1.4 mm
  wide and therefore ~0.86 mm TALL against a 0.4 mm Z step. The part climbed ~0.46 mm/layer past
  the nozzle, which ploughed into it and dragged it off the plate at 56%. Narrow bead means tall
  bead means collision. A single layer cannot stack into itself, so wide commanded lines are safe —
  which is what makes the filament visible at low speed.

FAN 20%, not 100%. Two reasons, the second being the important one:
  1. Nothing prints above it, so cooling buys nothing — but a heavy single-layer sheet of fat beads
     will curl and lift with full fan behind it.
  2. Full fan chills the melt and can make extrusion fail on its own. That would read as the flow
     ceiling when it is really the fan, and every downstream parameter would then be set too low.
     A melt-rate test must not have a second cooling variable fighting the hotend.

BED 120 C (Oleg, 2026-07-25). Far above PLA's glass transition, so adhesion is excellent — which is
  what a 40 g single-layer sheet needs. Trade-off to know: the sheet stays rubbery while hot, so let
  the plate cool before lifting it or it will stretch out of shape as you peel.

HOW TO READ IT
  Centre = lowest flow, outer edge = highest. It degrades gradually, not in steps: find where the
  bead stops being CONTINUOUS PLASTIC — first gaps, first skips, first matte stretches.

  SELF-LABELLING: at every multiple of 5 mm3/s the spiral makes a small outward BUMP, and every bump
  sits at the same polar angle, so they line up into one radial spoke of pimples. Count outward from
  the centre: the first pimple is the first multiple of 5 above the start flow, each one after +5.
  No ruler needed. The bump is 1 mm against 3 mm turn spacing, so it cannot touch its neighbour, and
  it is a SHAPE change rather than a gap — it can never be mistaken for the extrusion failure we are
  hunting for.

BONUS MEASUREMENT: turn spacing equals the COMMANDED line width. Where the spiral seals into a
  continuous surface the bead really is that wide; where there is a gap, landed width = spacing -
  gap. That number feeds the crackle strand model.

LIVE: `python3 where.py` prints the exact mm3/s being extruded at this instant.

Usage:
  python3 flowtest.py --no-home                       # spiral, 50..90 mm3/s
  python3 flowtest.py --no-home --flows 60,100
"""
import argparse, math, os
import sys as _sys

import machine
import pathstats

# MATERIALS COME FROM machine.py, NOT FROM A SECOND TABLE HERE. This file kept its own copy, so
# `--material pla-matte` was rejected by the one tool whose entire job is measuring a new filament.
# A material list in two places is the same defect as SHRINK sizing both metal and bamboo: the
# tables drift, and the one that drifts is the one nobody is looking at.
MATERIALS = {m: dict(temp=machine.temp_for(m),
                     bed=machine.BED_TEMP.get(m, 60),
                     flows=[20, 90] if m.startswith("pla") else
                           [10, 38] if m == "petg" else
                           [2, 12] if m == "tpu" else [8, 36])
             for m in machine.MATERIAL_TEMP}
# NO MODULE-LEVEL BED. This was (350,350) while --printer only selected the FAN syntax, so
# `--printer k1c` emitted a 350mm-plate spiral — X 10..335 on a 220mm machine — saved under a "k2"
# filename, and validate.py (which hardcoded the same 350) passed it clean. The plate now comes
# from machine.BED[printer], like every other generator.


def emit(q_lo, q_hi, layer_h, line_w, temp, bed, fan, fil_d, home, margin, r0, seg_len,
         inward,
         bump_h, bump_arc, bump_every, spacing_mm, fixed_speed=None, bed_xy=None,
         printer='k2plus', aux=1.0):
    """With --fixed-speed the ramp varies LINE WIDTH instead of speed.

    Q = width x height x speed, so a flow ramp can be driven by either factor. Driving it with
    speed (the original design) means the flow test is also a speed test: every reading carries an
    acceleration and junction-limit confound, and at the fast end the planner may not even reach the
    commanded rate. Driving it with WIDTH at a fixed 50 mm/s removes that entirely — one speed for
    the whole plate, and the only thing changing is how much plastic per mm.
    Safe here because it is a single layer: nothing stacks, so a 5mm commanded width cannot land
    tall and plough. (Oleg, 2026-07-25: cap head movement at 50 mm/s, thick walls always.)"""
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (line_w * layer_h) / area
    _B = bed_xy
    cx, cy = _B[0] / 2, _B[1] / 2
    r_max = min(cx, cy) - margin
    # PITCH MUST FOLLOW THE REAL RIBBON WIDTH, NOT THE NOMINAL LINE.
    # Pressing the layer to 0.1 for adhesion means the flow is carried by WIDTH: at 60 mm/s a
    # 0.1mm-tall ribbon is 11.7mm across at 70 mm3/s and 15.0mm at 90. Spiralling those on a 3mm
    # pitch lays them five deep — which is not a flow test, it is a pile, and over-extrusion is
    # exactly what ploughs work off a plate. Pitch defaults to the width at the HIGHEST flow, so
    # no turn overlaps its neighbour anywhere on the ramp.
    _w_hi = q_hi / (min(machine.MAX_SPEED, q_hi / (line_w * layer_h)) * layer_h)
    _pitch = spacing_mm or max(line_w, _w_hi)
    b = _pitch / (2 * math.pi)              # radius gained per radian
    th_max = (r_max - r0) / b
    turns = th_max / (2 * math.pi)

    def q_at_r(r):                          # flow linear in radius
        return q_lo + (q_hi - q_lo) * (r - r0) / (r_max - r0)

    # Radius at which each multiple of 5 mm3/s is crossed. Each bump is placed on the NEXT pass
    # through angle 0, so all bumps stack into one readable radial spoke.
    marks = []
    m = math.floor(q_lo / bump_every) * bump_every + bump_every
    while m < q_hi:
        r_m = r0 + (m - q_lo) / (q_hi - q_lo) * (r_max - r0)
        marks.append((m, math.ceil(((r_m - r0) / b) / (2 * math.pi)) * 2 * math.pi))
        m += bump_every

    L = []; w = L.append
    w(f"; MAX VOLUMETRIC FLOW — single layer, Archimedean spiral, {turns:.0f} turns")
    w(f"; line_w={line_w}->{_w_hi:.1f} at peak, layer_h={layer_h} temp={temp} bed={bed} fan={fan}, spiral pitch={_pitch:.1f}mm (= widest ribbon, so turns never overlap)")
    w(f"; RAMP {q_lo:g} -> {q_hi:g} mm3/s {'INWARD (peak first, largest radius)' if inward else 'outward'}, r {r0:g}..{r_max:g}mm about ({cx:g},{cy:g})")
    w("; READ IT: centre = lowest flow. Find where the bead stops being continuous plastic.")
    w(f"; BUMPS: {bump_h}mm outward pimples every {bump_every:g} mm3/s, all at one angle -> a spoke.")
    for mq, mth in marks:
        w(f";   bump {mq:g} mm3/s at r{r0 + b*mth:.0f}mm")
    w("; FLOW_TEST=1   this file DELIBERATELY exceeds machine.FLOW — it exists to find the")
    w(";              ceiling, and a ceiling cannot be found from underneath. Not a part.")
    w("; HEADER_BLOCK_START"); w("; total layer number: 1"); w("; HEADER_BLOCK_END")

    w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — direct to print (fails safely if the machine lost home)")
    # M190 ONLY WAITS FOR HEATING. If the bed is already ABOVE target it returns instantly, so a
    # file that says "bed 45" can start printing on a 98C plate left over from the previous job --
    # which is how a TPU test meant for 45C got laid onto a hot bed and welded itself down.
    # TEMPERATURE_WAIT blocks in BOTH directions.
    w(f"M140 S{bed}")
    w(f"TEMPERATURE_WAIT SENSOR='heater_bed' MINIMUM={min(bed - 3, 60 if bed >= 80 else max(bed - 10, 30))} MAXIMUM={bed+5}")
    w(f"M109 S{temp}")
    w("M204 S8000")
    w("M107" if not fan else f"M106 S{fan}")
    for _ln in machine.aux_fans(printer, aux):
        w(_ln)
    w("M82"); w("G92 E0")
    # NO TRAVEL IS A RULE (machine.py): the prime ENDS where the spiral BEGINS, so there is no
    # reposition between priming and printing.
    _sx, _sy = cx + r0, cy
    w(f"G1 Z{layer_h:.2f} F600")
    w(f"G0 F9000 X{_sx - 60:.3f} Y{_sy:.3f}")
    w(f"G1 F1200 X{_sx:.3f} Y{_sy:.3f} E12"); w("G92 E0")

    L.append("; ARGV: " + " ".join(_sys.argv))
    L.append(f"; PRINTER={printer}")
    L.append("; BODY_START")
    e = 0.0
    # DIRECTION. Outward puts the peak flow at the end of the run, by which time the hotend has
    # been soaking for the whole test — so a failure there confounds "too much flow" with "too long
    # hot", which is exactly the confusion that cost a night on the sustained-flow question.
    # Inward prints the peak FIRST, on the largest radius and a clean plate.
    th = th_max if inward else 0.0
    _step = -1 if inward else 1
    px, py = (cx + r0 + b * th, cy) if inward else (cx + r0, cy)
    while (th > 0.0) if inward else (th < th_max):
        r_base = r0 + b * th
        th += _step * min(seg_len / max(r_base, 1.0), 0.25)
        r_base = r0 + b * th
        dr = 0.0
        for mq, mth in marks:                       # raised-cosine blip centred on the marked turn
            d = th - mth
            if abs(d) < bump_arc:
                dr = bump_h * math.cos(math.pi * d / (2 * bump_arc)) ** 2
                break
        r = r_base + dr
        x, y = cx + r * math.cos(th), cy + r * math.sin(th)
        if fixed_speed:
            fixed_speed = min(fixed_speed, machine.MAX_SPEED)
            # ramp WIDTH at constant speed: removes speed as a confound in a flow test
            _w = q_at_r(r_base) / (fixed_speed * layer_h)
            e_local = (_w * layer_h) / area
            f_now = round(min(fixed_speed, machine.MAX_SPEED) * 60)
        else:
            # HARD CAP the head speed (machine.MAX_SPEED). If the flow the ramp wants would need
            # a faster head than the work tolerates, WIDEN THE BEAD instead -- that keeps the flow
            # honest, which is the whole point of a flow test, while the head stays slow. Oleg:
            # "big line height and big line width is our way, that how we get high volume not
            # moving head like crazy".
            _v = q_at_r(r_base) / (line_w * layer_h)
            if _v > machine.MAX_SPEED:
                _w_now = q_at_r(r_base) / (machine.MAX_SPEED * layer_h)
                _v = machine.MAX_SPEED
            else:
                _w_now = line_w
            # E MUST FOLLOW THE WIDENED BEAD. Capping the speed while still metering the original
            # width would deliver LESS flow than the label says, and a flow test that lies about
            # its own flow is worse than no test.
            e_local = (_w_now * layer_h) / area
            f_now = round(_v * 60)
        e += math.dist((px, py), (x, y)) * e_local
        L.append(f"G1 F{f_now} X{x:.3f} Y{y:.3f} E{e:.5f}")
        px, py = x, y

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{layer_h+40:.1f} F900",
          f"G0 X10 Y{_B[1]-10:.0f} F9000"]   # park inside THIS bed, not the K2's
    grams = e * area * 1.24 / 1000
    secs = 0.0
    th = 0.0
    while th < th_max:
        r = r0 + b * th
        dth = min(seg_len / max(r, 1.0), 0.25)
        secs += (r * dth) / (q_at_r(r) / (line_w * layer_h))
        th += dth
    return "\n".join(L) + "\n", dict(turns=round(turns), grams=round(grams, 1),
                                     mins=round(secs / 60, 1), path=round(e / e_per_mm / 1000, 1),
                                     lines=len(L), r_max=r_max, marks=[m for m, _ in marks])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--material", default="pla", choices=list(MATERIALS))
    ap.add_argument("--flows", default=None, help="lo,hi in mm3/s")
    ap.add_argument("--temp", type=int, default=None)
    ap.add_argument("--bed", type=int, default=0,
                    help="0 = machine.BED_TEMP[material] — per-material, not max")
    ap.add_argument("--layer_h", type=float, default=machine.PRESS_HARD,
                    help="PRESSED TO THE PLATE, not a comfortable layer height. Oleg, 2026-07-27,\n"
                         "stopping a run: 'the nozel need to be 0,1 to board. we need adhesion'.\n"
                         "A flow test is a SINGLE layer, so that layer IS the first layer — if it\n"
                         "does not anchor it lifts, curls into the nozzle, and measures curl rather\n"
                         "than flow. machine.PRESS_HARD (0.10) is the project's standing figure for\n"
                         "anything gripping the plate and this tool was ignoring it at 0.4.\n"
                         "The flow is then carried by WIDTH, which is the whole technique: at\n"
                         "60 mm/s a 0.1mm-tall ribbon needs 11.7mm at 70 mm3/s and 15.0mm at 90.\n"
                         "It will not land 15mm wide — it does not need to. It needs to extrude\n"
                         "that much and stay stuck.")
    ap.add_argument("--line_w", type=float, default=3.0)   # single layer: wide is safe
    ap.add_argument("--fan", type=int, default=51)         # 20% — see the FAN note above
    ap.add_argument("--margin", type=float, default=15.0)
    ap.add_argument("--r0", type=float, default=25.0, help="inner radius (tight centre = slow anyway)")
    ap.add_argument("--seg", type=float, default=2.0, help="segment length mm")
    ap.add_argument("--bump", type=float, default=1.0, help="marker bump height mm")
    ap.add_argument("--bump-arc", type=float, default=0.12, help="marker half-width in radians")
    ap.add_argument("--bump-every", type=float, default=5.0, help="mm3/s between markers")
    ap.add_argument("--inward", action="store_true",
                    help="START at the largest diameter and spiral IN (Oleg, 2026-07-27: 'start\n"
                         "with higherst diamenter spiral and go invards'). The highest flow then\n"
                         "prints FIRST, on the gentlest curvature, on a cold clean plate — instead\n"
                         "of arriving at the end after the hotend has been soaking. If it is going\n"
                         "to fail it fails early, and the failure is not confounded by heat soak.")
    ap.add_argument("--spacing", type=float, default=None,
                    help="turn spacing mm; lines OVERLAP when < the landed bead width")
    ap.add_argument("--overlap", type=float, default=1.10,
                    help="material multiple vs spacing (1.10 = 10%% squeeze)")
    ap.add_argument("--fixed-speed", type=float, default=0,
                    # NOT MACHINE_MAX_SPEED. This is the speed the HEAD moves, so it is
                    # bounded by machine.MAX_SPEED (the work cap), not by what the
                    # machine could do. Defaulting it to 120 ran an entire flow ramp at
                    # 120 mm/s in fixed-speed mode, which starves the bead to a thread
                    # at low flow — it reads as "not extruding at all".
                    help="hold this speed and ramp WIDTH instead (0 = ramp speed)")
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--aux", type=float, default=1.0, help="side/chamber fans 0-1")
    ap.add_argument("--bed-size", default=None, help="X,Y bed size, e.g. 229,225 for the K1C")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    if a.spacing:
        # Conservation, not preference: material per unit AREA is line_w*layer_h/spacing. Move the
        # turns closer without narrowing the line and you deposit more height than the Z step,
        # the nozzle ploughs, and you repeat the 2026-07-25 tower failure. So --spacing DERIVES
        # line_w unless one was passed explicitly.
        if a.line_w in (3.0,):
            a.line_w = round(a.spacing * a.overlap, 3)
    m = MATERIALS[a.material]
    bed_xy_for_name = (tuple(float(v) for v in a.bed_size.split(','))
                       if a.bed_size else machine.BED[a.printer])
    fl = [float(x) for x in a.flows.split(",")] if a.flows else m["flows"]
    q_lo, q_hi = min(fl), max(fl)
    temp = a.temp or m["temp"]
    # 0 means "ask the material", not "no heat" — and the material table wins over any
    # habit of maxing the bed. See machine.BED_TEMP.
    bed = a.bed or machine.BED_TEMP.get(a.material, m["bed"])
    g, st = emit(q_lo, q_hi, a.layer_h, a.line_w, temp, bed, a.fan, 1.75,
                 not a.no_home, a.margin, a.r0, a.seg, a.inward,
                 a.bump, a.bump_arc, a.bump_every,
                 a.spacing, a.fixed_speed or None,
                 (tuple(float(v) for v in a.bed_size.split(',')) if a.bed_size
                  else machine.BED[a.printer]),
                 a.printer, a.aux)
    os.makedirs(a.out, exist_ok=True)
    # Machine tag in the filename. Two files that differ ONLY by bed size are a real hazard: the
    # K2's spiral is centred at 175,175 and the K1C's at 114,112, so starting the wrong one by hand
    # on the touchscreen drives the head off the plate. Same-name-different-machine is exactly the
    # kind of thing that reads as harmless right up until it is not.
    _bx, _by = (bed_xy_for_name or BED)
    # THE TAG IS THE PRINTER, not a reverse-lookup of the bed size. The old map only produced
    # 'k1c' for (229,225) — the kinematic reach that machine.py explicitly warns is NOT the plate —
    # so the only input that yielded a machine-named file was the wrong one.
    _tag = a.printer
    fn = (f"{a.out}/flowspiral_{_tag}_{'nohome_' if a.no_home else ''}{a.material}"
          f"_T{temp}_{int(q_lo)}-{int(q_hi)}.gcode")
    open(fn, "w").write(g)
    xs = a.line_w * a.layer_h
    print(f"{fn}\n  ONE layer, spiral {st['turns']} turns to r{st['r_max']:.0f}mm, "
          f"{st['path']} m path, ~{st['mins']} min, {st['grams']} g, {st['lines']} lines")
    # MEASURED FROM THE EMITTED FILE, never recomputed from the inputs. This line used to print
    # "(2->21 mm/s)" while the file it had just written commanded F7200 = 120 mm/s on every move,
    # because --fixed-speed defaulted to a constant that was later redefined under it. The summary
    # was not wrong about its arithmetic -- it was describing a different file from the one on disk,
    # and it hid the bug for hours. See pathstats.measure_text.
    _mt = pathstats.measure_text(g)
    if _mt:
        print(f"  ramp {q_lo:g}->{q_hi:g} mm3/s requested | MEASURED IN FILE: flow "
              f"{_mt['flow'][0]:.1f}->{_mt['flow'][1]:.1f} mm3/s, head "
              f"{_mt['speed'][0]:.0f}->{_mt['speed'][1]:.0f} mm/s, bed {bed}C")
        if _mt['speed'][1] > machine.MAX_SPEED + 0.5:
            raise SystemExit(f"  ABORT: file commands {_mt['speed'][1]:.0f} mm/s, cap is "
                             f"{machine.MAX_SPEED:.0f} (machine.MAX_SPEED)")
    else:
        print(f"  ramp {q_lo:g}->{q_hi:g} mm3/s, bed {bed}C  (COULD NOT MEASURE THE EMITTED FILE)")
    print(f"  bump spoke: {', '.join(f'{x:g}' for x in st['marks'])} mm3/s")
