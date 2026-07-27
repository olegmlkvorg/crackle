#!/usr/bin/env python3
"""NUCLEON — the flat atom drawing as a toolpath. Oleg, 2026-07-25: "think of flat nucleon drawing".

N ellipses rotated evenly about one centre, drawn as ONE continuous path. It is the best coupon
geometry measured so far, and it satisfies every constraint the project has accumulated:

  · perfectly smooth — no corners anywhere, so the head holds commanded speed
    (N=8: 6.5% of path below 90% speed, vs 93% for the old pillar lattice and 15.9% for a Lissajous)
  · circular outer bound — suits a round object, and it IS a recognisable thing rather than a squiggle
  · crossings land on a RING, not piled at the centre. The star-order lattice put 5 chords through
    one point and half its "crossings" were the same weld; ellipses about a common centre intersect
    each other in 4 points each, away from the middle.
  · crossings scale roughly as 2*N*(N-1) — a clean analytic dial, but a LOWER BOUND, not a count.
    The emitted files run about 18% above it, because the formula counts crossings between distinct
    ellipse pairs and the path also crosses itself where the fold returns. The generator prints the
    formula as "predicted" for exactly this reason; treat it as the dial, never as the answer.

COUNTS — RE-MEASURED FROM THE EMITTED FILES, 2026-07-26:
    N       formula   file      member   below speed
    N= 3        12      ?        13.9mm      11.9%
    N= 6        60     74         6.0mm       8.1%
    N= 8       112    132         4.3mm       6.5%
    N=12       264      ?         2.8mm       4.7%

  The previous table read 70 / 126 / 286 under a "MEASURED" heading and the line above claimed the
  formula was "verified numerically". Both were wrong: at N=6 the file emits 74 against a claimed
  70, at N=8 it emits 132 against 126. THREE different numbers existed for one quantity — formula,
  docstring, and artifact — and the published page quoted a fourth interpretation of them.
  The docstring was measured once and never re-measured after the geometry changed, which is the
  precise failure this project keeps finding: a number that outlived the thing it described.
  N=3 and N=12 are left as "?" rather than carried over — an unverified number is worse than a
  visible gap.

THE TRADE-OFF TO TEST, and it is the real question: more junctions means SHORTER members between
them. Slender spans snap; short stubby ones bend quietly, which is the hex-grid feel that started
this project. At strand 0.85mm, N=6 gives a 7:1 span-to-thickness ratio and N=12 gives 3:1. More
crossings is not obviously better — it may be worse. Print both.

Fatter ellipses (b/a 0.55) print FASTER than thin ones — less curvature at the tips.

WELD CONTROL carries over from weave.py: in a single layer the second pass through a crossing must
lift or plough the bead already down. Lift = interlace, stay = fuse. Phase 1 said fusing is the
mechanism, so --weld defaults to 1.0.
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import smooth
from pathstats import crossings as find_crossings


# WHAT A NUCLEON SPACER IS, AND IS NOT — measured 2026-07-27, before anyone builds one.
#
# WORKS: as a spacer. It carries compression along the post (a 3-ellipse rosette at a=17 is 426mm2
# of cross-section), it threads on with N-point contact and millimetres of relief for a hot bulge,
# and it is ONE continuous stroke — 434 dry moves and 10.4m on the round-bore shell it replaces
# became 1 move.
#
# DOES NOT WORK: as a fillable vessel, which is what the bamboo-shelf spacers are for. The lobes
# are OPEN at the outside near the ellipse major-axis tips — measured at r = 0.92a, the outer band
# is open at 166 of 360 angles for N=3, 134 for N=4, 85 for N=6, 56 for N=8. Gypsum runs straight
# out. More ellipses close it slowly and never fully.
#
# It does have 15 (N=3) to 56 (N=8) SEALED internal cells between crossings, so it is not that
# there is nowhere to put fill — it is that the outermost lobes leak.
#
# THE FIX ALREADY EXISTS IN THIS FILE: nested_path() draws a core plus an outer CAGE as one
# continuous run. An outer ring at r = a is tangent to every ellipse at its major-axis tips, so the
# ring and the rosette meet naturally and the path can walk ring -> ellipse -> ring without lifting.
# That closes the perimeter while keeping the continuous stroke and the lobed bore. Not built yet.

def bore_ratio(a, bore_d, fit=0.70, N=3, bead_w=1.2, speed=58.0):
    """Solve b/a so the emitted central void MEASURES `bore_d + fit` across.

    Oleg, 2026-07-27, after a round bore that "barely fitted stick ... on hot": "imagine a nucleon
    but give it a ineer ring size of 1/4 inch".

    N ellipses about one centre leave a central void bounded by N arcs — it touches the rod at N
    points and opens out between them, which is exactly the relief a hot bulging wall needs and
    exactly what a circle cannot give. And it costs no travel: a nucleon is ONE continuous stroke,
    so the bore, the wall and the cavities between lobes are all the same curve.
    Measured against the round-bore shell it replaces: dry travel 434 moves / 10.4m -> 1 move.

    THE RATIO IS SOLVED, NOT DERIVED, and that is deliberate. b/a = bore_r/a emits a hole 1.2mm too
    small; adding half a bead over-corrects to 8.17 on a 7.05 target, because the fillet and the
    curvature-adaptive sampling move the innermost path by more than the bead alone. Two models,
    two wrong answers — so this bisects on the ACTUAL geometry instead of predicting it, which is
    the same discipline as the fit gauge: the artifact decides.
    """
    # Solve against the path emit() ACTUALLY WRITES — same speed, same fillet — and against the
    # MATERIAL EDGE, which is half a bead inside the centreline. Both corrections are needed and
    # neither is guessable:
    #     ratio 0.2074  raw r 3.526  emitted r 3.648  -> hole 6.10mm   (solving the raw curve)
    #     ratio 0.2321  raw r 3.946  emitted r 4.128  -> hole 7.06mm   (correct)
    #     ratio 0.2426  raw r 4.124  emitted r 4.304  -> hole 7.41mm   (raw + half a bead)
    # The fillet moves the innermost point ~0.18mm outward, so a model that ignores it is wrong by
    # more than the fit tolerance it is trying to hit.
    target = (bore_d + fit) / 2.0 + bead_w / 2.0
    lo, hi = 0.05, 0.60
    for _ in range(48):
        mid = (lo + hi) / 2.0
        pts = nucleon_path(N, a, a * mid, 0.0, 0.0, 600, speed=speed)
        inner = min(math.hypot(x, y) for x, y in pts)
        if inner < target: lo = mid
        else: hi = mid
        if hi - lo < 1e-6: break
    return (lo + hi) / 2.0


def _ellipse_R(a, b, t):
    """Local radius of curvature of the ellipse at parameter t."""
    num = (a * a * math.sin(t) ** 2 + b * b * math.cos(t) ** 2) ** 1.5
    return num / max(a * b, 1e-9)


def nested_path(N, a, ratio, N2, a2, ratio2, cx, cy, n_per, phase, speed, accel, max_seg):
    """Core ellipses, then cage ellipses, as ONE continuous run.

    The cage-around-core nodule is what the pop-up DIG station needs: a brittle outer shell that
    picks away in fragments, around a tough inner ring that survives and goes home in a palm. Both
    in a single job — "one print, one job, no assembly" is the whole claim.

    Toughness and brittleness come from DIFFERENT variables, which is why one file can hold both:
      · core  — few ellipses, THICK strand. Long members, lots of material per junction: tough.
      · cage  — many ellipses, THIN strand. Short members, many junctions: it fragments.
    Fusing is not the lever here (Phase 1 established fused junctions are what snap, so BOTH are
    fused); the lever is strand thickness and junction density.

    Returns (points, cage_start_index) so the caller can switch extrusion width at the boundary.
    The join between core and cage is DRAWN, never travelled — the no-travel rule holds.
    """
    core = nucleon_path(N, a, a * ratio, cx, cy, n_per, phase, speed, accel, max_seg)
    cage = nucleon_path(N2, a2, a2 * ratio2, cx, cy, n_per, phase + 0.37, speed, accel, max_seg)
    return core + cage, len(core)


def nucleon_path(N, a, b, cx, cy, n_per, phase=0.0, speed=None, accel=None, max_seg=None):
    """ADAPTIVE sampling: dense only where the curve is actually tight.

    Uniform sampling at n_per=600 gave 0.237mm segments, which at 235 mm/s is 990 moves/second.
    Klipper drains its lookahead buffer well below that and stalls to refill — the head stopped
    dead roughly every 3 seconds (Oleg spotted it, 2026-07-25). Resolution is only needed where
    curvature is high; an ellipse's radius runs from b^2/a at the major-axis tips to a^2/b at the
    minor ones, a factor of (a/b)^2, so uniform sampling oversamples most of the path by an order
    of magnitude.

    Segment length at each point is the longest that still holds `speed` there, from the same
    junction-deviation model the fillet uses."""
    if speed is None:
        pts = []
        for k in range(N):
            rot = phase + math.pi * k / N
            c, s = math.cos(rot), math.sin(rot)
            for i in range(n_per + 1):
                t = 2 * math.pi * i / n_per
                x, y = a * math.cos(t), b * math.sin(t)
                pts.append((cx + x * c - y * s, cy + x * s + y * c))
        return pts
    accel = accel or machine.ACCEL
    jd = 5.0 ** 2 * (math.sqrt(2.0) - 1.0) / accel
    kk = speed ** 2 / (jd * accel)
    h = math.acos(min(1.0, kk / (1.0 + kk)))          # half turn-angle budget per junction
    pts = []
    for k in range(N):
        rot = phase + math.pi * k / N
        c, s = math.cos(rot), math.sin(rot)
        t = 0.0
        while t < 2 * math.pi:
            x, y = a * math.cos(t), b * math.sin(t)
            pts.append((cx + x * c - y * s, cy + x * s + y * c))
            R = _ellipse_R(a, b, t)
            seg = max(2.0 * R * h, 0.15)              # arc length we may travel before turning
            # SHAPE FIDELITY MUST NOT DEPEND ON SPEED. The budget above is a MOTION budget — how far
            # the head may run before it has to turn — and it grows as speed falls. So a slow print
            # sampled the ellipse COARSELY: at TPU's 21 mm/s the chords cut visibly inside the true
            # curve, layers stopped landing on each other, and validate.py failed the same geometry
            # for OVERHANG (13% of a layer unsupported) that passes clean in PLA. The material had
            # silently changed the shape. Bound the chord's own sagitta as well: for deviation `tol`
            # at local radius R the chord is 2*sqrt(2*R*tol). Motion dominates when fast, geometry
            # when slow, and the emitted curve is the same object either way.
            seg = min(seg, 2.0 * math.sqrt(2.0 * R * 0.05))
            if max_seg:
                # A Z ARCH IS A FEATURE ON THE PATH, and a feature cannot be finer than the
                # sampling that carries it. Curvature-adaptive sampling gives ~1.8mm segments; a
                # 2mm lift window then contains ONE sample, so the arch renders as a single blip
                # and the Z axis barely moves — measured 0.27m of Z travel where the amplitude
                # predicted 3.47m. Same defect the sine-sampling guard was written for; it was
                # never carried across to this generator.
                seg = min(seg, max_seg)
            dRdt = math.hypot(a * math.sin(t), b * math.cos(t))   # |dP/dt|
            t += max(seg / max(dRdt, 1e-9), 1e-4)
        x, y = a, 0.0
        pts.append((cx + x * c - y * s, cy + x * s + y * c))
    # ROUND THE JOINS. Each ellipse ends where it began and the next starts at a different
    # rotation, so the path crosses a chord between them — a genuine ~19deg corner, one per
    # ellipse. At 70 mm/s an 19deg turn caps the head at 28 mm/s, which is where the last 8.6% of
    # speed loss was hiding. Everything else on the curve is already gentle, and fillet() leaves
    # near-straight vertices untouched, so this only affects the joins.
    # (Oleg, 2026-07-25: "not sharp angles, make sure you use semi circlish always".)
    if speed:
        r_min = speed * speed / (accel or machine.ACCEL)
        pts = smooth.fillet(pts, max(2.0 * r_min, 2.0), speed=speed, accel=accel or machine.ACCEL)
    return pts


def emit(N, a, ratio, origin, layers, layer_h, strand_w, flow, weld, lift, lift_win,
         temp, bed, fan, fil_d, home, n_per, first_slow=0, first_speed_frac=1.0,
         first_squish=0.85, vase=False, z_step=None, wave_amp=0.0, wave_len=8.0,
         cage_N=0, cage_a=0.0, cage_ratio=0.55, cage_w=0.0,
         material="pla", printer="k2plus"):
    area = math.pi * (fil_d / 2) ** 2
    e_per_mm = (strand_w * layer_h) / area
    # LAYER 1 IS A DIFFERENT CROSS-SECTION AND MUST BE METERED AS ONE. It is laid at
    # layer_h*first_squish (0.51mm), not layer_h (0.6) — feeding it the body's 0.72mm2 over-fills
    # it 1.18x on the one layer whose only job is to bond. Surplus on layer 1 does not build a
    # thicker layer, it ploughs the part off the plate (the postfoot failure, +10.4%).
    # Already fixed in hilbert, waves, honeycomb and solid; this is the fifth site.
    e_first_mm = (strand_w * layer_h * first_squish) / area
    # Speed is CAPPED, and flow follows from it rather than the other way round. Thick walls and
    # a calm head beat chasing volumetric throughput; and on stacked geometry the two cannot both
    # be satisfied anyway (see machine.MACHINE_MAX_SPEED).
    # machine.MAX_SPEED is the limit of the WORK (30). MACHINE_MAX_SPEED (120) is what the
    # machine could do — capping against it emitted files validate.py rejects outright.
    speed = min(flow / (strand_w * layer_h), machine.MAX_SPEED)
    actual_flow = strand_w * layer_h * speed
    f_mm_min = round(speed * 60)
    b = a * ratio
    cx = cy = origin + a
    # Z RISE IS NOT THE SAME AS BEAD HEIGHT, and assuming it is caused today's tower failure in
    # another form. The part grows by the DEPOSITED height: cross-section / landed width. The
    # nozzle only squashes the bead when the gap is under the orifice; above that the bead lands
    # roughly round and deposits MORE than commanded, so the part climbs into the nozzle.
    # z_step defaults to layer_h (the old behaviour) but can be set to the MEASURED deposit.
    z_rise = z_step if z_step else layer_h
    cage_e_per_mm = ((cage_w or strand_w) * layer_h) / area
    # ARCH vs LAYER STEP — the collision rule. A lift deposits plastic `lift` mm ABOVE the surface
    # it left. The next pass comes round at z_rise. If lift >= z_rise the nozzle arrives BELOW its
    # own arch and knocks the part off the plate — which is exactly what happened at 28% on
    # 2026-07-25 with a 2.5mm lift against a 1.57mm step.
    # Sizing lift just UNDER z_rise is the useful case: the arch tip lands where the next pass runs,
    # so it WELDS to the layer above instead of being run over. That turns stacked sheets into a
    # 3D truss, and it is what lets the amplitude grow — raise z_rise and the arch may grow with it.
    if lift and weld < 1.0 and lift >= z_rise:
        raise SystemExit(
            f"lift {lift}mm >= layer step {z_rise}mm: the nozzle would return BELOW its own arch "
            f"and knock the part loose.\n"
            f"  Either raise --z-step above {lift + 0.2:.2f}, or drop --lift below {z_rise - 0.2:.2f}.\n"
            f"  Sizing lift just under the step (e.g. {z_rise - 0.2:.2f}) makes the arch tip weld to "
            f"the layer above instead — a truss rather than stacked sheets.")

    if wave_amp:
        _vz = speed * 2 * math.pi * wave_amp / wave_len
        _az = (2 * math.pi * speed / wave_len) ** 2 * wave_amp
        if _vz > machine.MAX_Z_V or _az > machine.MAX_Z_A:
            raise SystemExit(
                f"Z wave exceeds the axis: v_peak {_vz:.1f} (limit {machine.MAX_Z_V}), "
                f"a_peak {_az:.0f} (limit {machine.MAX_Z_A}).\n"
                f"  At {speed:.0f} mm/s the largest amplitude for a {wave_len}mm wave is "
                f"{min(machine.MAX_Z_V*wave_len/(2*math.pi*speed), machine.MAX_Z_A*wave_len**2/(4*math.pi**2*speed**2)):.2f} mm.")
        if z_step and 2 * wave_amp >= z_step - 0.0:
            raise SystemExit(
                f"wave peak-to-peak {2*wave_amp:.2f}mm >= layer step {z_step}mm — adjacent layers "
                f"would intersect and the nozzle would strike the one below.\n"
                f"  Raise --z-step above {2*wave_amp + 0.3:.2f} or drop --wave-amp below {(z_step-0.3)/2:.2f}.")
    if strand_w < machine.NOZZLE:
        raise SystemExit(f"strand_w {strand_w} is below the {machine.NOZZLE}mm orifice — a nozzle "
                         f"cannot lay a bead narrower than its hole; the melt stretches thin and "
                         f"breaks into beads that look like retraction stringing.")
    if weld < 1.0:
        vz = math.pi * lift * speed / (2 * lift_win)
        az = (math.pi ** 2) * lift * speed ** 2 / (2 * lift_win ** 2)
        if vz > machine.MAX_Z_V or az > machine.MAX_Z_A:
            need = speed * math.pi * math.sqrt(lift / (2 * machine.MAX_Z_A))
            raise SystemExit(f"Z cannot follow the lift at {speed:.0f} mm/s: a_peak {az:.0f} "
                             f"(limit {machine.MAX_Z_A}). Need --lift-win {math.ceil(need)}.")

    start_xy = nucleon_path(N, a, b, cx, cy, n_per, 0.0, speed=speed)[0]
    L = []; w = L.append
    w(f"; NUCLEON — {N} ellipses a={a} b={b:.1f}, weld={weld}, {layers} layers")
    # THE FLAGSHIP WAS THE ONE FILE EXEMPT FROM BOTH GUARDS. Without `; PRINTER=` validate.py
    # bounds-checks against the K2 plate whatever the target, and push.py's wrong-printer refusal
    # never fires; without `; MATERIAL=` the TPU fan guard cannot see the file at all. The two
    # omissions covered for each other, which is why neither showed up as a failure.
    # DECLARE ARCH GEOMETRY. Z varies WITHIN a layer here by design (the weld lift, the wave), so
    # the layer-pair overhang check cannot read this file: it bins layers by Z, and a continuum of Z
    # values shatters into thousands of pseudo-layers that obviously do not support one another —
    # it reported 100% of "layer Z0.544" unsupported by "layer Z0.540", 4 microns below it. That
    # false FAIL is part of why the hero file was published while failing validate. Saying so in the
    # file is honest; silently skipping the check would not be.
    if weld < 1.0 or wave_amp:
        w(f"; ARCH_LIFT={max(lift if weld < 1.0 else 0.0, 2*wave_amp):.3f}")
    w(f"; PRINTER={printer}")
    w(f"; MATERIAL={material}")
    w("; ARGV: " + " ".join(sys.argv))
    w(f"; flow={actual_flow:.1f} mm3/s at {speed:.0f} mm/s (capped), bead {strand_w}x{layer_h} = {strand_w*layer_h:.2f}mm2")
    w(f"; predicted junctions/layer = 2*N*(N-1) = {2*N*(N-1)}")
    w("; HEADER_BLOCK_START"); w(f"; total layer number: {layers}"); w("; HEADER_BLOCK_END")
    w(f"M140 S{bed}"); w(f"M104 S{temp}"); w("G90")
    w("G28" if home else "; NO HOME — direct to print (fails safely if the machine lost home)")
    # M190 only waits for HEATING; a hotter bed returns instantly and the part prints on
    # whatever the last job left. TEMPERATURE_WAIT blocks both ways.
    w(f"TEMPERATURE_WAIT SENSOR='heater_bed' MINIMUM={machine.bed_start(material, bed)} MAXIMUM={bed+5}")
    w(f"M109 S{temp}")
    w("M204 S8000")
    # FANS OFF FOR LAYER 1, ALWAYS. Cooling the first layer chills the bead before it can wet the
    # plate; on a tall open structure the nozzle drag then peels the whole part. That is what
    # detached the wave print at 46% on 2026-07-25 — max cooling was enabled from the first
    # millimetre because it was needed for the ARCHES, and the layer that has to stick was never
    # exempted. Cooling helps everything above layer 1 and hurts layer 1 specifically.
    # EVERY BRANCH USED TO TEST `fan >= 255`, so --fan 128 emitted NO M106 and NO SET_PIN at all —
    # zero cooling, on the one geometry whose docstring says cooling is what makes it possible —
    # while --fan 255 wrote a raw 255 straight past FAN_MAX['pla']=0.20. A fan argument was either
    # ignored or obeyed absolutely, with nothing in between and no material ever consulted.
    # MAX COOLING means all THREE fans, not just the part fan. Oleg: "to push z to the limits you
    # shall freeze stuff in the air so max air flow on all fans" — an arch that does not freeze
    # mid-flight sags into a droop. M106 drives fan0 only; fan1/fan2 need the per-machine syntax in
    # machine.aux_fans() (SET_PIN 0-255 on the K2, SET_FAN_SPEED 0-1 on the K1C).
    _fan_frac = machine.fan_for(material, (fan or 0) / 255.0)
    _fan_body = int(round(_fan_frac * 255))
    _fan_l1 = int(round(machine.fan_first_layer(material) * 255))
    _aux_body = machine.aux_for(material, _fan_frac)
    # FANS OFF FOR LAYER 1 unless the material demands otherwise (TPU does, and validate.py fails a
    # TPU file whose part fan is off). Cooling the first layer chills the bead before it can wet the
    # plate; on a tall open structure the nozzle drag then peels the whole part — that is what
    # detached the wave print at 46% on 2026-07-25.
    if _fan_l1:
        w(f"M106 S{_fan_l1}      ; {material} needs cooling from the first millimetre")
        for _ln in machine.aux_fans(printer, machine.aux_for(material, _fan_l1 / 255.0)):
            w(_ln)
    else:
        w("M107")
        w(f"; fans OFF through layer 1 ({material}); switched on below once it has bonded")
    w("M82"); w("G92 E0")
    # NO TRAVEL IS A RULE (Oleg, 2026-07-25: "always our prints are continuous extrusion").
    # The prime line therefore ENDS exactly where the object BEGINS, so there is no reposition
    # between priming and printing. From the first millimetre of plastic to the last, the nozzle
    # never lifts and never moves without extruding.
    # One G0 remains BEFORE any plastic exists (the head has to reach the prime start from wherever
    # homing left it) and one after the object is finished (park). Neither is a travel within the
    # object, and there is no way to remove them that does not drag a stray line across the plate.
    _sx, _sy = start_xy
    w(f"G1 Z{layer_h*0.85:.3f} F600")
    w(f"G0 F9000 X{_sx - 55:.3f} Y{_sy - 12:.3f}")
    # STATIONARY PURGE before anything moves. The prime line extrudes WHILE travelling, so it never
    # builds nozzle pressure — Oleg watched the first 4 seconds of a print lay nothing at all
    # (2026-07-25). A cold-start nozzle has drooled its melt away and the filament path is slack;
    # pressure has to be re-established standing still, or the first stretch of the object is air.
    # 25mm of filament at 5mm/s is ~5 seconds of visible extrusion in one spot, off to the side.
    w("G1 E25 F300                      ; ~5s stationary purge — build pressure before moving")
    w(f"G1 F1200 X{_sx:.3f} Y{_sy:.3f} E37   ; prime line, ending exactly where the object begins")
    w("G92 E0")
    if weld < 1.0:
        w("; Z_MODULATED")
    w("; BODY_START")

    e = 0.0; total_x = 0; total_lift = 0

    if vase:
        # VASE MODE — one unbroken extrusion for the whole object. Oleg: "why not continuous
        # nucleon? vasemode style". The layered version travels once per layer to reposition at the
        # path start; twelve layers is twelve visible travel lines. Here Z rises continuously with
        # distance travelled, so there is no layer change, no reposition, and no travel at all after
        # the initial approach.
        #
        # The crossings still weld, and that is not obvious — it needs checking rather than
        # assuming. Within one turn the N ellipses now sit at DIFFERENT heights, spread over
        # layer_h*(N-1)/N. For N=6 that is 0.50mm against a 0.60mm-tall bead, so strands still
        # overlap and fuse. It only fails if the spread exceeds the bead height, i.e. never, since
        # the spread is always < layer_h by construction.
        full = []; cage_marks = []
        for layer in range(layers):
            ph = (math.pi / N) * (layer * 0.5)
            _ms = (lift_win / 6.0) if weld < 1.0 else None
            if cage_N:
                seg, ci = nested_path(N, a, ratio, cage_N, cage_a, cage_ratio,
                                      cx, cy, n_per, ph, speed, None, _ms)
                cage_marks.append((len(full) + (0 if layer == 0 else -1) + ci, len(full) + len(seg)))
            else:
                seg = nucleon_path(N, a, b, cx, cy, n_per, ph, speed=speed, max_seg=_ms)
            full.extend(seg if layer == 0 else seg[1:])
        cum = [0.0]
        for i in range(len(full) - 1):
            cum.append(cum[-1] + math.dist(full[i], full[i + 1]))
        total = cum[-1] or 1.0
        hits, _ = find_crossings(full)
        total_x = len(hits)
        # WELD CONTROL IN VASE MODE. It used to exist only in the layered path, so asking for
        # --weld silently opted out of vase and reintroduced one G0 reposition per layer — Oleg
        # spotted the travels on the printed ladder. The two features were never in conflict; the
        # lift is just a Z bump on top of the continuous Z ramp, so they compose.
        second = []
        for k, (i, j, x, y) in enumerate(sorted(hits, key=lambda h: max(h[0], h[1]))):
            if ((k * 0.6180339887498949) % 1.0) >= weld:
                second.append(cum[max(i, j)]); total_lift += 1
        fans_on_at = 1.0 / layers          # fraction of path where layer 1 ends
        L.append(f"; VASE — one continuous extrusion, {len(full)} points, "
                 f"Z {layer_h*first_squish:.2f} -> {layer_h*layers:.2f}, {total_x} junctions")
        L.append(f"; continuous from the prime — no reposition")
        z_lo = layer_h * first_squish
        z_hi = z_rise * layers
        for i in range(1, len(full)):
            frac = cum[i] / total
            z = z_lo + (z_hi - z_lo) * frac
            # THE COMMENT ATE THE CONDITIONAL. Commit 5fa4d88 appended `# never faster than the
            # body` in FRONT of `if frac < 1.0 / layers else f_mm_min`, so the ternary became part
            # of the comment and EVERY move in the file ran at FIRST_LAYER_SPEED — 3323 of 3323
            # below half the declared flow, under a header still claiming 43.2 mm3/s. Inert while
            # FIRST_LAYER_SPEED was 50; a 50->20 change activated a typo nothing was watching.
            lf = (round(min(machine.FIRST_LAYER_SPEED, speed) * 60)
                  if frac < 1.0 / layers else f_mm_min)
            dz = 0.0
            if wave_amp:
                # CONTINUOUS Z WAVE, independent of crossings. Arches triggered at crossings can
                # never give much total Z travel: crossings sit ~1.3mm apart, so any window wide
                # enough to be printable overlaps its neighbours and the Z sits on a plateau
                # instead of returning. Measured best 10mm of Z per 100mm of XY.
                # A wave along the PATH has no such constraint. Its travel rate is 4A/L, and the
                # Z-velocity limit caps A/L at MAX_Z_V/(2*pi*v) — which works out at ~83mm of Z per
                # 100mm of XY whatever wavelength is chosen. Eight times better, and at the axis
                # limit rather than at an accident of geometry.
                # Biased so the wave never goes BELOW the ramp: sin() from a zero baseline dips
                # negative, and on the first layer that puts the nozzle under the plate-level Z.
                # Offsetting by +amp keeps dz in [0, 2*amp] with the SAME total travel (4*amp per
                # wavelength) — the wave still rises and falls, it just does so above the surface.
                dz = wave_amp * (1.0 + math.sin(2 * math.pi * cum[i] / wave_len))
            if second:
                s_here = cum[i]
                for sv in second:
                    d = s_here - sv
                    if abs(d) < lift_win:
                        dz = max(dz, lift * math.cos(math.pi * d / (2 * lift_win)) ** 2)
            if _fan_body > _fan_l1 and cum[i - 1] / total < fans_on_at <= frac:
                L.append(f"M106 S{_fan_body}      ; blowers on — layer 1 has bonded")
                L += machine.aux_fans(printer, _aux_body)
            _epm = e_first_mm if frac < 1.0 / layers else e_per_mm
            if cage_N:
                for cs, ce in cage_marks:
                    if cs <= i < ce:
                        _epm = cage_e_per_mm      # thin strand in the cage
                        break
            e += math.dist(full[i - 1], full[i]) * _epm
            L.append(f"G1 {'F%d ' % lf if i == 1 or (frac >= 1.0/layers and cum[i-1]/total < 1.0/layers) else ''}"
                     f"X{full[i][0]:.3f} Y{full[i][1]:.3f} Z{z+dz:.4f} E{e:.5f}")
        L += ["M107", "SET_PIN PIN=fan1 VALUE=0", "SET_PIN PIN=fan2 VALUE=0",
              "M104 S0", "M140 S0", f"G1 Z{z_hi+40:.1f} F900",   # Z-only lift, no XY
              f"G0 X10 Y{machine.BED[printer][1]-10:.0f} F9000"]   # park at the plate's OWN back edge
        grams = e * area * 1.24 / 1000
        return "\n".join(L) + "\n", dict(grams=round(grams, 2), speed=round(speed),
                                          flow=round(actual_flow, 1), lines=len(L),
                                          junctions=total_x, lifts=total_lift,
                                          mins=round(total / speed / 60, 1))

    for layer in range(layers):
        z0 = z_rise * (layer + 1)
        # FIRST LAYER. The balls failure (2026-07-25) came from 235 mm/s giving the bead no dwell to
        # wet the plate. With the head now capped at 50 mm/s the whole print runs at what IS a
        # first-layer speed, so no slowdown is needed and --first-slow defaults to 0.
        # The SQUISH stays: it presses the bead into the plate and does not touch flow, which is
        # what Oleg asked for — thick and irregular lines, always.
        if layer < first_slow:
            lf = round(min(machine.FIRST_LAYER_SPEED, speed) * 60)   # never faster than the body
            z0 = layer_h * first_squish
        else:
            lf = f_mm_min
        # rotate each layer off the last so crossings distribute through the volume instead of
        # stacking into welded vertical columns
        # LAYERS MUST START WHERE THE LAST ONE ENDED, or the "one continuous path" claim is false.
        # The phase used to advance by pi/(2N), chosen for crossing distribution alone and with no
        # regard for the head's actual position. A layer's path ENDS at (a,0) rotated by
        # phase + pi(N-1)/N; the next began at (a,0) rotated by its OWN phase, somewhere else
        # entirely. The gap was never emitted as a move — so the first G1 of each layer flew
        # diagonally across the finished part carrying only the E of its own short segment:
        # validate.py, 11 STARVED moves, worst 47.4mm at 0.017mm2 against a 0.722mm2 bead. A thread
        # dragged over the layer below, once per layer, in the flagship.
        # Advancing by exactly pi(N-1)/N makes each layer's start coincide with the previous end —
        # zero gap, nothing to travel, and still a large inter-layer rotation (157.5 deg at N=8)
        # so crossings keep distributing through the volume instead of stacking into columns.
        phase = (math.pi * (N - 1) / N) * layer
        _ms = [x for x in ((lift_win/6.0) if weld < 1.0 else None,
                           (wave_len/8.0) if wave_amp else None) if x]
        pts = nucleon_path(N, a, b, cx, cy, n_per, phase, speed=speed,
                           max_seg=min(_ms) if _ms else None)
        cum = [0.0]
        for i in range(len(pts) - 1):
            cum.append(cum[-1] + math.dist(pts[i], pts[i + 1]))
        hits, _ = find_crossings(pts)
        total_x += len(hits)
        second = []
        for k, (i, j, x, y) in enumerate(sorted(hits, key=lambda h: max(h[0], h[1]))):
            # Deterministic, evenly distributed, and correct for ANY crossing count.
            # The old rule was `(k % 100) >= weld*100`, which silently assumed >=100 crossings per
            # layer. There are 70, so k never reached 75 and --weld 0.75 lifted NOTHING while
            # reporting success; 0.5 lifted 64% and 0.25 lifted 100%. The primary control variable
            # of the whole project was miscalibrated at every setting except 0 and 1.
            # The golden-ratio low-discrepancy sequence: uniform for ANY count, and it spreads
            # the choice through the layer instead of fusing the early crossings and lifting
            # the late ones, which a plain k/n threshold would do. An integer hash mod 1000
            # does NOT work here — 997 = -3 mod 1000, so 70 crossings only ever sampled the
            # top fifth of the range and almost everything lifted.
            if ((k * 0.6180339887498949) % 1.0) >= weld:
                second.append(cum[max(i, j)]); total_lift += 1
        L.append(f"; layer {layer+1}  z{z0:.2f}  junctions {len(hits)}  lifts {len(second)}")
        if _fan_body > _fan_l1 and layer == 1:
            L.append(f"M106 S{_fan_body}      ; blowers on — layer 1 has bonded")
            L += machine.aux_fans(printer, _aux_body)
        L.append(f"G1 F1800 Z{z0:.3f}")   # Z only — no XY reposition   # layer-change Z move: 10 -> 30 mm/s
        for i in range(1, len(pts)):
            dz = 0.0
            if second:
                s = cum[i]
                for sv in second:
                    d = s - sv
                    if abs(d) < lift_win:
                        dz = max(dz, lift * math.cos(math.pi * d / (2 * lift_win)) ** 2)
            e += math.dist(pts[i - 1], pts[i]) * (e_first_mm if layer < first_slow else e_per_mm)
            L.append(f"G1 {'F%d ' % lf if i == 1 else ''}X{pts[i][0]:.3f} "
                     f"Y{pts[i][1]:.3f} Z{z0+dz:.4f} E{e:.5f}")

    L += ["M107", "M104 S0", "M140 S0", f"G1 Z{layer_h*layers+40:.1f} F900", f"G0 X10 Y{machine.BED[printer][1]-10:.0f} F9000"]
    grams = e * area * 1.24 / 1000
    return "\n".join(L) + "\n", dict(grams=round(grams, 2), speed=round(speed), flow=round(actual_flow,1), lines=len(L),
                                     junctions=total_x, lifts=total_lift,
                                     mins=round(e / e_per_mm / speed / 60, 1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=8, help="ellipse count; junctions = 2N(N-1)")
    ap.add_argument("--a", type=float, default=25.0, help="semi-major axis mm")
    ap.add_argument("--ratio", type=float, default=0.55, help="b/a — fatter prints faster")
    ap.add_argument("--origin", type=float, default=40.0)
    ap.add_argument("--layers", type=int, default=12)
    ap.add_argument("--layer_h", type=float, default=machine.BEAD_H)   # stacking ceiling
    ap.add_argument("--strand_w", type=float, default=machine.BEAD_W)  # stacking ceiling.
                    # Together these give the fattest bead a 0.8 nozzle can stack (0.72mm2),
                    # which is what lets max flow run at the SLOWEST possible speed: 111 mm/s
                    # instead of 235. Oleg wanted 5x slower at constant flow; 2.1x is the
                    # physical limit for stacked geometry, and going further would land the
                    # bead taller than the Z step and plough the part off the plate.
    ap.add_argument("--flow", type=float, default=0,
                    help="0 = the material's measured ceiling (PLA keeps the max-flow rule)")
    ap.add_argument("--weld", type=float, default=1.0, help="1=fuse all (Phase 1 winner), 0=weave")
    ap.add_argument("--lift", type=float, default=0.5)
    ap.add_argument("--lift-win", type=float, default=12.0)
    ap.add_argument("--temp", type=int, default=0)
    ap.add_argument("--material", choices=sorted(machine.MATERIAL_TEMP), default="pla")
    ap.add_argument("--printer", choices=sorted(machine.BED), default="k2plus")
    ap.add_argument("--bed", type=int, default=0,
                    help="0 = ask machine.bed_for(material, printer). A hardcoded 120 is what gave\n"
                         "the K1C two klippy_shutdowns: it cannot HOLD 120 under load (90 measured),\n"
                         "and a heater at full power losing temperature is a verify_heater abort.")
    ap.add_argument("--fan", type=int, default=0,
                    help="part-cooling fan 0-255, CLAMPED to what the material tolerates "
                         "(FAN_MAX: pla 20%%, petg 40%%, tpu 100%%, abs 10%%). Layer 1 is exempt "
                         "unless the material demands cooling from the first millimetre.")
    ap.add_argument("--n-per", type=int, default=600, help="samples per ellipse")
    ap.add_argument("--first-slow", type=int, default=1,
                    help="layers slowed for adhesion — 0 by default: the whole print now runs\n                          at 50 mm/s, which IS a first-layer speed, so nothing needs slowing.\n                          Oleg: thick and irregular lines are good, always.")
    ap.add_argument("--first-frac", type=float, default=1.0, help="first-layer speed fraction")
    ap.add_argument("--first-squish", type=float, default=0.85, help="first-layer Z as a fraction")
    ap.add_argument("--z-step", type=float, default=None,
                    help="Z rise per layer — set to the MEASURED deposit, not the bead height")
    ap.add_argument("--cage-N", type=int, default=0, help="ellipses in the brittle outer cage")
    ap.add_argument("--cage-a", type=float, default=0.0, help="cage semi-major axis mm")
    ap.add_argument("--cage-ratio", type=float, default=0.55)
    ap.add_argument("--cage-w", type=float, default=0.9, help="cage strand width — thin = brittle")
    ap.add_argument("--wave-amp", type=float, default=0.0,
                    help="continuous Z wave amplitude mm — the high-Z-travel mode")
    ap.add_argument("--wave-len", type=float, default=8.0, help="wave period, mm of path")
    ap.add_argument("--vase", action="store_true",
                    help="one continuous extrusion, Z rising with path — no travels at all")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    # MATERIAL ROUTES THE NOZZLE AND THE FLOW TOO — see machine.MATERIAL_TEMP.
    a.temp = a.temp or machine.temp_for(a.material)
    a.flow = machine.flow_for(a.material, a.flow or machine.FLOW, ' for nucleon.py')
    g, st = emit(a.N, a.a, a.ratio, a.origin, a.layers, a.layer_h, a.strand_w, a.flow, a.weld,
                 a.lift, a.lift_win, a.temp, a.bed or int(machine.bed_for(a.material, a.printer)),
                 a.fan, 1.75, not a.no_home, a.n_per,
                 a.first_slow, a.first_frac, a.first_squish, a.vase, a.z_step,
                 a.wave_amp, a.wave_len, a.cage_N, a.cage_a, a.cage_ratio, a.cage_w,
                 a.material, a.printer)
    os.makedirs(a.out, exist_ok=True)
    fn = (f"{a.out}/nucleon_{'nohome_' if a.no_home else ''}{'vase_' if a.vase else ''}"
          f"N{a.N}_weld{a.weld:g}_T{a.temp}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}\n  N={a.N} ({2*a.N*(a.N-1)} junctions/layer predicted, {st['junctions']} measured "
          f"over {a.layers} layers), {st['lifts']} lifts")
    print(f"  {st['speed']} mm/s (capped at {machine.MAX_SPEED:.0f}), flow {st['flow']} mm3/s, ~{st['mins']} min, {st['grams']} g, {st['lines']} lines")
