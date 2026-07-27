"""Measured machine facts. Single source of truth — nothing hardcodes these numbers separately.

Oleg, 2026-07-25: "you should be extruding at max speed we know nozzle can flow. that is not
negotiable. 100% of the time."
"""
MAX_FLOW = 81.2        # mm3/s, MEASURED (spiral ramp, first skips at 81.2 @ r137, 0.8 nozzle, PLA 230C)
FLOW = 55.0            # CAPPED for BOTH machines (Oleg, 2026-07-25). K2 cracks ~74 and
                       # then still cracking at 70. Oleg heard the extruder
                       # CRACKING (skipping) at 80 during sustained printing. The spiral ramp put
                       # first visual skips at 81.2, but a ramp only holds each flow for a few
                       # seconds of a single layer — it measures the INSTANTANEOUS ceiling. Sustained
                       # multi-layer printing loads the extruder continuously and reveals a lower
                       # practical ceiling. Trust the ear over the ramp: audible skipping is the
                       # extruder losing grip, and it is upstream of anything visible on the plate.
                       # healthy nozzle (45-60 ramp printed clean end to end, 2026-07-25).
                       # The true ceiling is HIGHER — 60 was the top of the window, not a limit.
                       # A 60-100 ramp is uploaded to find it.
VOID_MEASUREMENTS = {  # kept visible so nobody re-adopts them
    81.2: "ramp measured with a clog present or developing",
    80.0: "cracked — clog, not flow",
    70.0: "cracked — clog, not flow",
    60.0: "set while still chasing the clog; later printed CLEAN, so never a limit",
}
NOZZLE = 0.8
MAX_VELOCITY = 800.0
MAX_ACCEL = 30000.0     # config ceiling
ACCEL = 5000.0          # what the toolhead ACTUALLY reports while printing — M204 S8000 is clamped
# BEAD FIRST, then speed. Oleg, 2026-07-25: "keep line width and height always at max", and
# "increase speed to 100 something to match max flow".
# The bead is pinned at the largest a 0.8 nozzle can STACK — width 1.5x nozzle, height 0.75x —
# and speed is whatever hits MAX flow with that bead. Nothing here is chosen for comfort:
#     0.72 mm2 x speed = 80 mm3/s  ->  speed = 111 mm/s
# Wider than 1.5x and the bead lands TALLER than the Z step (it cannot spread), the part climbs
# past the nozzle and gets ploughed off the plate — that failure cost a print on 2026-07-25.
BEAD_W = 1.2            # 1.5 x nozzle — stacking ceiling
BEAD_H = 0.6            # 0.75 x nozzle — stacking ceiling
# FIRST LAYER SPEED. Oleg 2026-07-27: "why we need first layer celing at 20 if we already
# pressing at 0.1". No good answer. The 20 was inherited slicer convention and was never measured
# on this machine -- the same species of number as the 27 that was just deleted for pretending to
# be evidence. The slicer default exists to buy adhesion by dwelling; here adhesion is bought
# MECHANICALLY, by pressing the nozzle to 0.1 of the plate, and that mechanism does not care how
# fast the head moves. So the first layer runs at the north star like everything else.
# At a 0.1 gap and a ~3mm first bead that is 0.3mm2 x 50 = 15 mm3/s -- nowhere near any ceiling.
# WHAT WOULD DISPROVE THIS: the first layer dragging, skipping, or lifting at a plate corner.
# If that happens the press is not doing the work and this goes back up -- with a measurement.
# (the assignment lives just below CONSTANT_SPEED, which has to be defined first)
                          # 28 mm/s body ran layer 1 at 50 = 120 mm3/s against a 74 ceiling, so the
                          # extruder skipped from the first millimetre and the part never adhered.
                          # A "slowdown" written for a fast body silently inverts on a slow one.
                          # Layer 1 only. At 111 the bead has no dwell to wet the plate and
                          # adhesion failed twice (Oleg, 2026-07-25). Deposit per mm of PATH is
                          # unchanged by slowing — E is per mm, not per second — so the first layer
                          # is just as thick, it simply has time to bond. Layer 2+ runs at 111.
MACHINE_MAX_SPEED = 120.0   # what the MACHINE can do — headroom above the 111 the bead+flow imply

# HARD PHYSICAL SPEED CAP FOR THE WORK. Oleg, after a pulley printed at 115 mm/s tore off the
# plate: "make sure we have hard checks not to go over 30mm second phisical".
#
# Every generator derives speed from flow / bead area, which is right for FLOW and says nothing
# about whether the PART survives being whipped around at that speed. On a small part the head
# reversing direction transmits straight into a thin wall stuck to glass, and a part that lets go
# becomes a ball of filament. This is a limit of the work, not the machine, so it OVERRIDES the
# flow target: when they conflict, flow drops. validate.py FAILS any file that commands more.
#
# RAISED 30 -> 70 on 2026-07-26. The 30 was stale: Oleg revised the cap himself the same day
# ("movement speed of printer head is not appreciated we areed to cap under 70") and the constant
# was never updated. The cost of leaving it was invisible and large — the cap SILENTLY overrode the
# FLOW target, so every solid part ran at 30 x 0.48 = 14.4 mm3/s while FLOW said 55, and nothing
# ever reported the reduction. Oleg found it by asking "are you using pla 55 flow on k2?".
#
# 70 is his stated ceiling, not a measured limit. The only speed failure on record is 115 mm/s.
# LOWERED 70 -> 60 on 2026-07-26. Oleg: "dont we have a rule that head speed should not exceed
# certain value?" — asked while the body was running at exactly 70, i.e. AT the cap rather than
# under it. His rule is "cap UNDER 70", and his standing principle is "max layer height and width,
# min moving speed". At the 0.72mm2 stacking ceiling the flow target of 55 would need 76 mm/s, so
# speed and flow genuinely trade off here: 60 mm/s delivers 43.2 mm3/s. Deposition per mm of path
# is unaffected — only the rate — so this costs minutes, not material.
# 50 mm/s IS THE NORTH STAR FOR MOVING (Oleg, 2026-07-27). Not a cap to approach -- the speed
# everything runs at. MAX_SPEED is pinned to it so nothing can quietly exceed it.
# CONSTANT SPEED. Oleg 2026-07-27: "keep speed at 50, we want constant movement and material
# distribution". Speed is an INPUT held fixed, not an output solved from flow -- a head that
# slows for corners and small radii deposits more per mm exactly where the geometry is already
# tightest. Flow is reached by widening the bead instead ("we hack with line width, can be set
# to any number even 20mm"), which keeps mm-per-second of travel constant everywhere.
CONSTANT_SPEED = 50.0
MAX_SPEED = CONSTANT_SPEED
FIRST_LAYER_SPEED = CONSTANT_SPEED   # see the note near the top; adhesion is the 0.1 press


def bead_for_flow(flow, layer_h, speed=CONSTANT_SPEED):
    """Bead width that delivers `flow` at the fixed speed. Width is the free variable now."""
    return flow / (speed * layer_h)

MAX_MOVES_PER_SEC = 300.0  # above this Klipper drains its lookahead and the head stalls; measured

# ---------------------------------------------------------------------------------------------
# A FLOW CEILING BELONGS TO A DURATION. Measured on the K2 Plus, 2026-07-26, 02:xx.
#
# The order-5 Moore lattice (320mm plate, 4096 cells, one unbroken extrusion) ran layer 1 at a
# commanded 55 mm3/s and a MEASURED 48.6 (19690mm of filament in 975s = 20.2 mm/s of filament).
# At 975 seconds of continuous extrusion the K2 firmware logged, twice:
#     // extruder stall state:1
#     !! {"code":"key797","msg":"warning_code MCU温度过高","values":["e"]}
# — the EXTRUDER DRIVER over-heated and lost steps, and the firmware auto-paused the print at 19%.
# Not a clog: filament_detected was true, the main MCU sat at 45C, the bed held 120.07/120, and the
# same file had printed 16 minutes clean before it let go. What was constant was the flow; what
# changed was only TIME. A failure at a fixed time under constant load is a soak, not a rate limit.
#
# THIS IS THE SAME NUMBER FAILING THE SAME WAY A THIRD TIME. 81.2 came off a spiral ramp that
# holds each flow for seconds; 55 was set from it; the comment above FLOW already says a ramp
# "measures the INSTANTANEOUS ceiling" and that sustained printing "reveals a lower practical
# ceiling" — and then nothing acted on it. Creality's own profile for this machine advertises
# max_volumetric_speed: 14, which the firmware prints in its log every time it loads a file.
#
# WHY THIS PART AND NOT THE OTHERS. Two rules multiply, and only here:
#   · the wide-first-layer adhesion hack (Oleg: "first layer maintain same 55 flow but put nozzle
#     0.1 to the plate, compensate with line width, set it to 10 if needed") makes layer 1 the
#     THICKEST cross-section in the file — 27.5 x 0.1 = 2.75mm2, 1.14mm of filament per mm of
#     path, 1.5x the body's 0.765;
#   · "always max flow" then runs that worst case at the ceiling;
#   · and a 320mm plate makes layer 1 alone last ~20 minutes with no travel to rest the motor.
# Every smaller part survives because it finishes before the driver saturates. The K1C printing
# the bowl lid at the same moment drew 6.1 mm3/s — geometry-limited, never near this.
#
# THE FIX PRESERVES THE PART EXACTLY. E is per MILLIMETRE, not per second, so halving the feedrate
# halves the extruder's duty cycle and changes not one deposited microgram. M220 S50 mid-print took
# the measured draw from 48.6 to 27.4 mm3/s and the print carried on from 19%.
# WHAT IS PHYSICALLY LOADED IN EACH MACHINE. Material follows the PRINTER -- they are one fact.
# Two independent defaults drift apart silently, and then a part prints the loaded filament at
# another filament's temperature under another filament's flow clamp. Update this when a spool
# changes; nothing else should carry a material or printer name as a literal default.
LOADED = {
    "k2plus": "pla-matte",   # matte gray, 230C, loaded 2026-07-27
    "k1c":    "pla",
    "f022":   "pla",
}
DEFAULT_PRINTER = "k2plus"
DEFAULT_MATERIAL = LOADED[DEFAULT_PRINTER]

# SUSTAINED FLOW PER MATERIAL. There is no global fallback number, deliberately: the old one (27)
# was invented, never measured, and then labelled "measured" -- so it could never be argued with.
# A material with no figure gets NO silent clamp; it gets a loud line saying nothing is known.
#
# MEASURED, sustained  -- a flow held for real minutes without the extruder complaining:
SUSTAINED_FLOW_BY_MATERIAL = {
    "pla":       55.0,   # Oleg 2026-07-27
    "pla-matte": 65.0,   # Oleg 2026-07-27
}
# THE OPEN TENSION, recorded rather than tidied away: on 2026-07-26 this machine stalled at
# 48.6 mm3/s after 16 minutes on pla -- BELOW the 55 now set for that material. Both can be true,
# because that run was confounded: 210C (not 230) and a wide-first-layer hack spread over a 320mm
# plate, so it was the worst case, not the material's limit. The failure is not deleted, because a
# thing that broke once is the first place to look when it breaks again.
KNOWN_FAILURE = {
    "pla": (48.6, 16),   # extruder DRIVER over-heated and stalled, 2026-07-26, 210C, wide layer.
}
                           # which is a floor on the true value, not the value itself.
SUSTAINED_MINS = 8.0       # unbroken extrusion beyond this is a soak, not a burst. The observed
                           # stall came at 16 min; half that is the margin, not a second reading.


# WHAT IS ACTUALLY KNOWN ABOUT FLOW ON THIS MACHINE, 2026-07-27. Read this before quoting a
# number, because four different ones have been treated as "the" ceiling and three were wrong.
#
#   81.2  a spiral ramp at 230C. VOIDED — measured with a clog present or developing.
#   55    the standing rule. Inherited, never re-measured on the current filament.
#   48.6  SUSTAINED for 16 minutes at 210C -> the extruder DRIVER over-heated and stalled.
#         This is the only number that ever came from a failure, and it set SUSTAINED_FLOW=27.
#   55-65 SILENT at 230C — 2.3 min, 57.4 delivered, 0 stalls. Oleg: "test was perfecrt".
#         The highest flow this machine has been DEMONSTRATED to hold, on any material.
#   70-90 CRACKED, by ear, at 230C on pla-matte, pressed 0.1, spiral inward — Oleg stopped it at
#         24.5% ("extruder cracks try 55-65"). Measured 54-72 mm3/s delivered with ZERO firmware
#         stalls and zero over-temp, which is the point: THE FIRMWARE NEVER SAW IT. Cracking is the
#         extruder losing grip on the filament, and it is upstream of anything the logs or the
#         plate can show. The ear caught what 3200Hz of accelerometer and a stall counter did not.
#         Note this happened at 230C, so the ceiling is not purely melt-limited as I had argued.
#   70    commanded on a Moore lattice; DELIVERED 32.2. The lattice's mean segment is 0.292mm and
#         reaching 58 mm/s from a corner needs 0.33mm, so the head never reached commanded speed
#         on a single move. That run measured the SHAPE, not the hotend.
#
# THE THREE THINGS THAT MUST BE TRUE FOR A FLOW NUMBER TO MEAN ANYTHING, all learned the hard way:
#   1. GEOMETRY THAT HOLDS SPEED. A spiral never turns; a lattice turns 199 times a second.
#   2. PRESSED TO THE PLATE. A single-layer test at 0.4 lifts and curls, and measures curl.
#      0.1 with the flow carried by WIDTH — 15mm at 90 mm3/s — is the technique, and the
#      apparent over-extrusion is deliberate (Oleg: "do not worry of massive over extrusion,
#      this is what we do").
#   3. A DIRECTION THAT SEPARATES CAUSES. Ramping INWARD prints the peak first on a clean plate;
#      ramping outward puts it last, after the hotend has soaked, so a failure there cannot be
#      told apart from a heat-soak failure. That confusion cost a night.
#
# And the distinction the whole question turns on: SUSTAINED_FLOW is a FLOOR, not a ceiling. It
# says "did not stall at 27", never "27 is the limit". Only a measurement can raise it.

SOAK_OVERRIDE = False    # set True ONLY by a deliberate measurement, never by a part


def flow_for_duration(flow, minutes, label="", material="pla"):
    """Clamp a flow to what the extruder can hold for `minutes` of UNBROKEN extrusion.

    Oleg's rule is "always max flow" and this does not weaken it — it measures `max` correctly.
    The ceiling is a function of how long you hold it, and every number this project had was taken
    from a burst. A generator that knows its own print time must ask this before emitting.
    """
    # A CEILING CAN ONLY BE RAISED BY MEASURING PAST IT. SUSTAINED_FLOW is a floor — it means
    # "did not stall at 27", not "27 is the limit" — and the only way to learn the real number is to
    # run above it on purpose and watch. So a deliberate soak test may opt out; a PART may never.
    # Oleg, 2026-07-27, switching to a 230C filament: "we also can test higher flow rate of 70".
    # That is the right experiment: the stall happened at 210C, and MAX_FLOW 81.2 was measured at
    # 230C — if the mechanism is melt-limited back-pressure driving extruder torque, 20 more degrees
    # should move the ceiling a long way. If it stalls anyway, the mechanism is not what I claimed.
    _sus = SUSTAINED_FLOW_BY_MATERIAL.get(material)
    _fail = KNOWN_FAILURE.get(material)
    if _sus is None:
        if _fail and flow >= _fail[0] and minutes >= _fail[1]:
            print(f"  !! {material}: {flow:g} mm3/s for {minutes:.0f} min is AT OR ABOVE the flow "
                  f"that actually failed ({_fail[0]:g} after {_fail[1]:g} min). Not clamping -- no "
                  f"sustained figure exists for {material}. Run a soak or stand next to it.")
        else:
            print(f"  ~ {material}: no sustained flow has ever been measured. Running {flow:g} "
                  f"unguarded{label}. Listen for extruder cracking; the firmware will not tell you.")
        return flow
    if SOAK_OVERRIDE and flow > _sus:
        print(f"  ~ SOAK_OVERRIDE: running {flow:g} past the {_sus:g} maintained figure{label}. "
              f"This is a measurement, not a part. Watch it.")
        return flow
    if minutes >= SUSTAINED_MINS and flow > _sus:
        print(f"  ! {flow:g} mm3/s for {minutes:.0f} min exceeds the {_sus:g} mm3/s MAINTAINED "
              f"figure for {material}{label}. Using {_sus:g}. Deposit per mm is unchanged; "
              f"only the clock moves.")
        return _sus
    return flow
    if minutes >= SUSTAINED_MINS and flow > _sus:
        print(f"  ! flow {flow:g} mm3/s for {minutes:.0f} min of unbroken extrusion{label} — the "
              f"K2 extruder driver over-heated and stalled at 48.6 mm3/s after 16 min (2026-07-26). "
              f"Using {_sus:g}. Deposit per mm is unchanged; only the clock moves.")
        return _sus
    return flow


def check_flow(flow, label=""):
    """Say so when a command asks for LESS than the standing flow rule.

    Oleg: "it is rule here we always run max flow". The generators already default to FLOW; the
    failure mode is a human (or me) passing --flow with a number carried over from an earlier
    command and nobody noticing. A shell printed at 36 because that figure was in the previous
    line of shell history. Under-running is invisible in the output — the part looks fine, it just
    took half again as long — so it has to announce itself.
    """
    if flow < FLOW * 0.999:
        print(f"  ! flow {flow:g} mm3/s is {flow/FLOW*100:.0f}% of the {FLOW:g} rule{label}. "
              f"Deliberate? The default is FLOW; passing --flow lower only costs time.")
    return flow


def speed_for(flow, bead_area, label=""):
    """Derive speed from a flow target, and SAY SO when the cap overrides it.

    Every generator computed min(flow/area, MAX_SPEED) inline and then quietly recomputed flow from
    the capped speed. That is how FLOW=55 printed at 14.4 for a day without anyone noticing: the
    number the operator set was not the number that ran, and no line of output compared the two.
    A cap that silently rewrites your input is indistinguishable from a bug.
    """
    want = flow / bead_area
    speed = min(want, MAX_SPEED)
    got = speed * bead_area
    if want > MAX_SPEED * 1.001:
        print(f"  ! flow target {flow:g} mm3/s needs {want:.0f} mm/s, but MAX_SPEED is "
              f"{MAX_SPEED:g} — running {got:.1f} mm3/s ({got/flow*100:.0f}% of target){label}."
              f" Raise the bead, not the speed, to close the gap.")
    return speed
                           # 2026-07-25 as a ~3s stutter at 990 moves/s
MAX_Z_V = 30.0
MAX_Z_A = 1000.0
# BED CEILING IS PER MACHINE, MEASURED, NOT PER CONFIG.
# Oleg's rule is "max out the bed temp for pla always". The K2 holds 120.0 rock steady. The K1C
# CANNOT: measured 2026-07-26 with target 120 and heater power pinned at 1.00, it climbed to 117.4
# before the print started and then FELL — 116.3, 113.5, 110.9 — losing about 2.5C every 30s once
# motion and airflow began. Its config claims max_temp 135; what it can hold under load is another
# thing entirely, and only the second number is real.
# Consequences of ignoring this: ~15 minutes of pre-print heating that never satisfies M190, then a
# bed sagging through the whole print — and twice, klippy_shutdown, because Klipper's verify_heater
# sees a heater at full power losing temperature and concludes the hardware has failed.
#
# MEASURED AGAIN AT TARGET 100 (2026-07-26, mid-print): the K1C settles at 90.6-91.4C with power
# still pinned at 1.00. It does not diverge, so verify_heater tolerates it and the print survives —
# but the bed never reaches target and has no regulation left. Its real sustained ceiling is ~91C,
# so k1c is set to 90: a target it can actually hold with power to spare.
# The K2 by contrast holds 120.0 at power 0.36.
#
# FOLLOW-UP, same evening: at target 90 the K1C settles at 87.4 with power STILL at 1.00. Stable, so
# it prints — but a heater pinned at full power has no headroom to answer a draft or a cold spool.
# Its true regulating ceiling is nearer 85. Left at 90 because it is printing reliably there and
# churn has its own cost; drop it to 85 if a print ever fails on bed temperature.
BED_MAX = {"k2plus": 120.0, "k1c": 90.0, "f022": 90.0}
BED_MAX_DEFAULT = 100.0


# MATERIAL MUST ROUTE THE NOZZLE AND THE FLOW, NOT JUST THE BED AND THE FANS.
# Audited 2026-07-26 across all six generators: `--material tpu` set the bed to 45 and the fans to
# full — correctly — and then emitted `M104 S210` and 43.2 mm3/s in EVERY ONE OF THEM, against a
# MEASURED TPU working flow of 15.2 and a rated 200C. That is 2.8x the material's flow at 10C over
# its temperature, on every TPU file this project has ever produced.
#
# This is almost certainly the TPU CLOG that has been blamed on the hardware for two days. The note
# under TPU_FLOW already records that 220-230 "jammed the extruder ~35 s into a print"; nobody
# connected it to the fact that asking for TPU never actually asked for TPU. The failure was
# consistently read as a nozzle problem because the file looked like it was requesting TPU settings
# — the bed and the fans, the two visible things, were right.
#
# Filed in the audit as a single-file defect (belt.py routing "the bed only"). It was universal.
# (the tables themselves live at the END of this file — they reference TEMP/TPU_TEMP/TPU_FLOW,
#  which are defined further down, and a dict literal resolves its values immediately.)


def temp_for(material):
    """Nozzle temperature this material is rated for."""
    return MATERIAL_TEMP.get(material, TEMP)


def flow_for(material, requested, label=""):
    """Clamp a flow to the material's MEASURED ceiling.

    Directional on purpose: PLA's ceiling is the standing max-flow rule, so this never lowers a PLA
    print. It exists to stop a PLA-shaped default reaching a material that cannot swallow it.
    """
    cap = MATERIAL_FLOW.get(material, FLOW)
    # A measurement may exceed the material cap too — that is what a measurement IS. pla-matte's
    # 55 is inherited from the 210C translucent PLA and is UNMEASURED at 230; MAX_FLOW 81.2 was
    # itself taken at 230, so the honest state is "unknown above 55", not "55".
    if SOAK_OVERRIDE and requested > cap:
        print(f"  ! SOAK OVERRIDE: {requested:g} mm3/s on {material}{label}, above its inherited "
              f"{cap:g} cap. Unmeasured territory — that is the point of the run.")
        return requested
    if requested > cap + 1e-9:
        print(f"  ! flow {requested:g} mm3/s is a {'PLA' if abs(requested-FLOW) < 1e-6 else 'carried-over'} "
              f"number on {material}{label} — its measured ceiling is {cap:g}. Using {cap:g}. "
              f"{'TPU jams the extruder within a minute above this.' if material == 'tpu' else ''}")
        return cap
    return requested


# THE BED TARGET IS NOT A STARTING GATE. Oleg, 2026-07-27, watching a print sit at 0% while the
# plate crawled to 120: "you dont need to wait for 120 plate. 120 is recomendation not a constraint
# to start".
#
# TEMPERATURE_WAIT was blocking on MINIMUM = target-3, so every job waited for the FULL recommended
# bed before laying anything — on a 350mm plate from cold that is minutes of an idle machine, and
# the 120 is chosen for extra grip on tall open geometry, not because 119 fails.
#
# The upper guard STAYS and is the part that matters: it is what stops a file meant for a 45C TPU
# plate printing on a 98C one left hot by the previous job, which welds it down. Only the floor
# moves — the bed goes on climbing to target while layer 1 prints.
BED_START_MIN = {"pla": 60, "pla-matte": 60, "petg": 60, "tpu": 35, "abs": 90}


def bed_start(material, bed):
    """Temperature the plate must actually REACH before printing may begin."""
    return min(bed - 3, BED_START_MIN.get(material, 60))


def bed_for(material, printer):
    """The bed target this material wants, clamped to what this machine can actually hold."""
    want = BED_TEMP.get(material, 60)
    cap = BED_MAX.get(printer, BED_MAX_DEFAULT)
    if want > cap:
        print(f"  ! bed {want}C for {material} exceeds what the {printer} can hold under load "
              f"({cap:.0f}C measured) — using {cap:.0f}. Its config claims more; it cannot keep it.")
    return min(want, cap)

# ---------------------------------------------------------------------------------------------
# NO TRAVEL WAS AN ABSOLUTE RULE. IT IS NOW A NARROWER ONE, AND THIS SAYS SO.
#
# The original (Oleg, 2026-07-25): "always our prints are continuous extrusion. no travel is a
# rule." That held while every print was a single object drawn as one stroke.
#
# It is no longer literally true, and pretending otherwise is worse than the change. An audit on
# 2026-07-26 found 35 of 143 emitted files contain non-extruding moves inside the object — the
# multi-part plates, the shells, the bowl. They arrived deliberately, for reasons that each cost a
# plate to learn:
#   · a thin link between two parts 12mm apart on open glass welds them into one object
#   · a flat travel at layer height drags the nozzle through what it just laid (161 of them
#     destroyed a K1C plate)
#
# THE RULE AS IT ACTUALLY STANDS:
#   INSIDE a part      — no travel. The path is continuous; a jump is a seam.
#   BETWEEN parts      — travel is allowed, and must be ALL of: lifted clear of everything already
#                        printed, non-extruding, no retract, and tagged in the file.
#
# THE TAG IS NOT THE PERMISSION. `; HOP` exempts a move from the no-travel COUNT, and nothing else:
# validate.py independently verifies that every such move clears the standing material, and a
# tagged travel that ploughs still FAILS. That distinction is the whole reason tagging is
# acceptable — a tag that granted exemption from the physical check would be a generator writing
# its own permission slip.
#
# Audit any file with:
#   notravel.py       — every G0 between the first and last extrusion, tagged or not
#   validate.py       — the physical checks, which no tag can turn off
NO_TRAVEL_RULE = "inside a part only; between parts must be lifted, unmetered and tagged"

# ---------------------------------------------------------------------------------------------
# MEASURED BEAD GEOMETRY — 2026-07-25, from a 3-layer probe calipered by Oleg at 4.72 mm.
#
# Commanded 2.0 x 1.2 mm (2.40 mm2). Three layers at a commanded 1.2 would be 3.60 mm; it measured
# 4.72, so the real DEPOSIT is 1.573 mm/layer — the part climbs 0.373 mm every layer.
#
#     LANDED_WIDTH = cross_section / deposit = 2.40 / 1.573 = 1.53 mm
#
# The nozzle only squashes a bead when the gap is UNDER the orifice. At a 1.2 mm gap it sits above
# the plastic, so the bead spreads unaided to ~1.9x the orifice and no further — commanding 2.0 mm
# does not make it 2.0 mm wide, it makes it TALLER.
#
# Two consequences, both previously guessed at:
#   · Z rise must equal the DEPOSIT, not the commanded height  -> nucleon.py --z-step 1.57
#   · a solid surface needs turn spacing <= LANDED_WIDTH       -> this is the number the spiral
#     gap tests were circling all afternoon ("still not a solid surface at points")
DEPOSIT_PER_LAYER = 1.573   # for the 2.0 x 1.2 commanded bead
LANDED_WIDTH = 1.53         # what a 2.0mm command actually lays down at a 1.2mm gap
SPREAD_RATIO = 1.91         # landed width / nozzle, unaided by squish
# ---------------------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------------------
# MATERIAL: translucent PLA, manufacturer-rated 210 C (Oleg, 2026-07-25). We had been running 230.
#
# RESPECT THE RATING, and lower flow rather than raise heat if they conflict:
#   · Overheated PLA DEGRADES in the melt zone — the polymer breaks down, leaves carbonised residue
#     on the nozzle wall, and that residue is how a partial clog forms. It also outgasses, and gas
#     snapping through the melt sounds exactly like the "cracking" that had us walking flow down
#     from 80 to 70 to 60 chasing a ceiling that may never have been the problem.
#   · Overheating CLOUDS translucent PLA. Translucency is what makes the object look like alien
#     tech; losing it costs the product's whole visual argument to buy print speed we do not need.
#
# Caveat, stated honestly: a 210 rating assumes ordinary flow (~10-15 mm3/s). At 60+ the melt zone
# needs more heat, so 210 will lower the achievable ceiling. That is the correct trade here.
TEMP = 210
TEMP_RATED = 210        # manufacturer spec for the translucent PLA
# ---------------------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------------------
# TWO MACHINES, DIFFERENT CEILINGS — measured 2026-07-25.
#
#     K2 Plus, 0.8 nozzle : cracks at ~74 mm3/s   (clean end-to-end through 60)
#     K1C,     1.0 nozzle : cracks at  59.6 mm3/s
#
# The WIDER nozzle passes LESS: 1.56x the orifice area, 0.80x the flow. So the hole is not the
# constraint at all — the heater is, and these are different hotends. A bigger nozzle buys a WIDER
# BEAD, never a faster print, which is the opposite of the usual reason for fitting one.
#
# CORRECTION, recorded because the mistake is instructive: this block first claimed the two ceilings
# were EQUAL, and that claim was published to alien.tech.senku.im for an hour. It came from treating
# the top of a test range as a measured limit — a 45-60 ramp that printed clean proves AT LEAST 60,
# never 60. Widening the range until each machine actually failed gave the real numbers. Do not
# quote a ceiling that equals the top of the range that produced it.
K1C_FLOW = 55.0         # same cap; K1C cracks at 59.6 so 55 sits just under it
K1C_MEASURED = 59.6     # where it began skipping, 1.0 nozzle, 210C
# ---------------------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------------------
# PRESS HARD — the general method for this work. Oleg, 2026-07-25: "pressing to the bed is a key,
# go as low as 0.1mm" ... "in general thats how we should be laying this work".
#
# Everything that touches the plate is CRUSHED into it, not laid on it: feet, hearts, anchors, the
# base. 0.10mm against a 0.8mm orifice is an eighth of the nozzle — the bead is squashed flat and
# wide, which is exactly what grips.
#
# WHY it matters more here than in ordinary printing: this work hangs things in the air. Every
# thrown arc pulls UPWARD on the foot that anchors it, and a foot that was merely laid has nothing
# but its own surface contact to resist. Adhesion is not a first-layer concern in this process, it
# is the structural element. Most of today's detachments trace back to it.
#
# THE RISK, stated: at 0.10mm the nozzle is close enough that bed-levelling error alone can scrape
# the plate. It wants a well-trammed bed and a clean sheet; if the first pass sounds like scratching
# rather than squashing, raise it rather than continue.
PRESS_HARD = 0.10       # absolute Z for anything anchoring to the plate
# ---------------------------------------------------------------------------------------------


# PRINTABLE PLATE, not kinematic reach. Read from each machine's own printer.cfg and confirmed
# against [bed_mesh] limits on 2026-07-25. These differ from toolhead.axis_maximum, which includes
# off-plate overtravel -- the K1C homes X to 229 which is PAST the plate edge, and using 229x225 as
# a bed size silently pushes parts off-centre (and would push them off the plate outright at larger
# sizes). The K2's own PRINTER_PARAM clamps Y to 352 at runtime even though its config says 400.
#   k1c  : "# Printer_size: 220x220x250", bed_mesh 10,10 -> 210,210
#   k2   : product_param bed_size 350/350/350, bed_mesh 5,5 -> 345,345
BED = {
    "k1c":    (220.0, 220.0),
    "k2plus": (350.0, 350.0),
    "f022":   (220.0, 220.0),
}


# THE HEAD IS NOT THE NOZZLE. Oleg, 2026-07-26, after the second collision on the K2:
# "you need to make sure you taking into account diameter of entire head + safety gap".
#
# Sequential (part-by-part) printing was written as if the only thing that could hit a finished part
# was the nozzle tip. It is not. While the head prints part N at first-layer height, the heater
# block, silicone sock and part-cooling shroud sweep through a cylinder of radius HEAD_R around the
# nozzle at every height below GANTRY_H — straight through a finished 13.3mm part standing 12mm
# away. Lifting Z between parts does nothing about this: the collision happens DURING printing, not
# during the hop.
#
# The consequence is severe and worth stating plainly: sequential printing is only safe when every
# already-printed part is further than HEAD_R from the one being printed. At a 12mm gap it is
# impossible on any real machine, and the guard below refuses rather than emitting it.
#
# THESE VALUES ARE NOT MEASURED — they are conservative placeholders, and they are deliberately
# generous so that the failure mode is "refuses to print" rather than "crashes". Measure yours:
# park the head, and with a ruler on the bed find the greatest horizontal distance from the nozzle
# tip to any part of the assembly that hangs lower than your tallest planned part.
HEAD_R = {          # mm, nozzle tip -> outermost point of the head assembly. UNVERIFIED.
    "k1c":    45.0,
    "k2plus": 50.0,
    "f022":   45.0,
}
HEAD_R_MEASURED = False   # flip to True only once a ruler has touched the machine


# AUXILIARY FANS — the syntax DIFFERS PER MACHINE and a wrong command errors mid-print.
# K2 Plus exposes output_pin fan1/fan2 (SET_PIN, 0-255). K1C exposes fan_generic side_fan and
# chassis_fan (SET_FAN_SPEED, 0-1). Hardcoding the K1C form into belt.py -- which defaults to the
# K2 -- would have failed the moment it ran. Ask this function instead of writing the line.
AUX_FANS = {
    "k2plus": [("SET_PIN PIN=fan1 VALUE={v255}"), ("SET_PIN PIN=fan2 VALUE={v255}")],
    "k1c":    [("SET_FAN_SPEED FAN=side_fan SPEED={v:.2f}"),
               ("SET_FAN_SPEED FAN=chassis_fan SPEED={v:.2f}")],
    "f022":   [],
}


def aux_fans(printer, frac):
    """Gcode lines to run the chamber/side fans at `frac` (0-1) on this machine."""
    frac = max(0.0, min(1.0, frac))
    return [t.format(v=frac, v255=int(round(frac * 255)))
            for t in AUX_FANS.get(printer, [])]


# BED TEMPERATURE IS PER MATERIAL, and more is NOT better. Oleg, after a TPU flow test welded
# itself to a 120C plate: "tpu on 120 bed is like glue. how to scrap it away".
#
# 120 came from a PLA part that kept letting go, where max bed was the right answer. Carried into
# TPU it is the WRONG DIRECTION: 120 is above TPU's softening point, so the first layer does not
# stick, it FUSES -- and then has to be torn off, taking the PEI with it. TPU needs 40-50: enough
# to bond, cold enough to release when the plate cools.
# BED TEMPERATURE. Oleg, 2026-07-26: "max out the bed temp for pla always".
# PLA goes to the machine ceiling (BED_MAX 120 — the config claims 135 and silently clamps).
# TPU deliberately does NOT: Oleg ran it at 120 and reported "tpu on 120 bed is like glue, how to
# scrap it away" — the belt welded itself to the plate.
BED_TEMP = {"pla": 120, "pla-matte": 120, "petg": 80, "tpu": 45, "abs": 100}

# PART-COOLING FAN CEILING, PER MATERIAL. Oleg, 2026-07-26: "fans for printing pla should be only on
# 20% at most". Running 80% on PLA — which this project had been doing on 320mm plates — chills the
# bead as it lands, and on layer 1 it chills the bond while it is still forming. It is the cheapest
# possible way to lose adhesion and it looks like nothing in the file.
# TPU is the exception and goes the other way: it needs FULL fans (see the guard in validate.py).
FAN_MAX = {"pla": 0.20, "pla-matte": 0.20, "petg": 0.40, "tpu": 1.00, "abs": 0.10}
# LAYER 1 GETS NO FAN — EXCEPT WHERE THE MATERIAL DEMANDS IT.
# The first layer's job is to weld to the plate, and cooling it works against the only thing that
# matters at that moment. But TPU is the exception in BOTH directions: it needs full fans throughout,
# and validate.py fails any TPU file whose part fan is off. Turning layer 1's fan off for TPU
# satisfied one rule by breaking another — caught by that guard within a minute of writing it.
FAN_FIRST_LAYER = 0.0


def aux_for(material, requested):
    """Chamber/side fan fraction, forced to full where the material requires it.

    validate.py fails a TPU file whose chamber fans are below full, and --aux defaults to 0.2. So a
    TPU print inherited a 51/255 chamber fan and failed its own guard — the part fan had been fixed
    and the auxiliaries forgotten, which is the same half-applied fix twice over.
    """
    if FAN_MAX.get(material, 0.20) >= 1.0:
        return 1.0
    return requested


def fan_first_layer(material):
    """Fan fraction for layer 1: none, unless the material requires full cooling regardless."""
    return 1.0 if FAN_MAX.get(material, 0.20) >= 1.0 else FAN_FIRST_LAYER


def fan_for(material, requested):
    """Clamp a requested part-cooling fraction to what the material tolerates, and say when it bites."""
    cap = FAN_MAX.get(material, 0.20)
    if requested > cap + 1e-9:
        print(f"  ! fan {requested*100:.0f}% requested for {material} — capped to {cap*100:.0f}%. "
              f"Cooling PLA hard is how first layers let go.")
    return min(requested, cap)


# TPU WORKING FLOW — measured 2026-07-25 on the K2 Plus, 0.8 nozzle, 230C, bed 45, all fans max.
# Oleg watched a constant-speed ramp (8->20 mm3/s at a fixed 25 mm/s, width carrying the flow):
# "we go 33 successful layers. settle on 27 layer as our flow". Turn 33 = 16.8 mm3/s was still
# clean; turn 27 = 15.2 is the working number, with the margin deliberate.
#
# Every EARLIER TPU figure today is void: those ramps ran at a flat 120 mm/s because --fixed-speed
# defaulted to the wrong constant, which draws a bead thinner than the nozzle for the whole test.
# The 13.3 "ceiling" measured before this was a partial clog, cleared by Oleg — a limit that moves
# when you push it is the symptom, not the limit.
TPU_FLOW = 15.2
# ...BUT 15.2 IS NOT A VALIDATED WORKING FLOW, AND NEITHER IS 13. As of 2026-07-26 midday TPU has
# printed exactly two things reliably (both belts, 24.5 m and 46 m of filament, no stops) and has
# failed on almost every solid pad since, at BOTH 15.2 and the 13 Oleg then asked for. So the
# number below is "a ramp survived 33 layers at this rate", not "parts print at this rate".
#
# What the 2026-07-26 trace RULES OUT — recorded because each was a live hypothesis that died:
#   · not heat creep / not hotend power — nozzle held 199.4-200.6 C to the moment it stopped, bed
#     steady, chamber flat at 25.4 C, hotend fan 1.0 throughout
#   · not geometry — moore_o1_40mm_L17 COMPLETED at 11:06 and stopped at 11:38. Same file.
#   · not corner density — the belt runs 5.38 deg/mm and completed 46 m; a pad at 5.21 deg/mm did
#     not. Measured from the emitted files, and it killed the hypothesis before it was acted on.
# Oleg's standing correction applies here: do not pattern-match on data this thin. The spool went
# to the dryer on his call; /tmp/k2trace.py records thermals every 5 s so the next stop has a trace.
# TPU_TEMP: 200, NOT the 225-235 the generic TPU guidance says. Measured 2026-07-25 on the K2 Plus.
#
# At 230 and at 220 the extruder jammed roughly 35 SECONDS into a print -- and critically, it did so
# at the same TIME under a ramping flow AND under a constant 15.2 mm3/s. A failure that ignores the
# flow rate and lands at a fixed time is not a rate limit; it is something that accumulates. Here it
# is HEAT CREEP: heat climbing the feed path softens the filament until it buckles and stops
# feeding. Hotter made it worse, which is why every attempt to fix it by lowering flow failed.
# At 200 the same file ran 4x longer and was still feeding.
#
# The hotend heatsink fan was verified running (speed 1.0) before blaming temperature. The K2's
# separate `output_pin extruder_fan` reads 0.0 and is the next lever if 200 ever proves marginal.
TPU_TEMP = 200


# Routing tables for temp_for()/flow_for() above. Defined here because they read TEMP, TPU_TEMP
# and TPU_FLOW, all of which appear further up only after their measurement notes.
# "PLA" IS NOT ONE MATERIAL. Oleg, 2026-07-27, loading the K2: "we switching the filament to pla
# matt gray with 230 temp requirement". The translucent PLA this project was built on is rated 210;
# this one wants 230. Same polymer family, 20 C apart, and the difference is not cosmetic — MAX_FLOW
# 81.2 was measured at 230 while the extruder stall that set SUSTAINED_FLOW happened at 210.
# Treating them as one entry is the same defect as sharing SHRINK between metal and bamboo: a number
# that belongs to ONE material silently governing another.
MATERIAL_TEMP = {"pla": TEMP, "pla-matte": 230, "petg": 240, "tpu": TPU_TEMP, "abs": 250}
# pla-matte's 65 is MEASURED, not inherited — the only material entry here that is.
#   55-65 at 230C, pressed 0.1, 15mm ribbon, spiral inward: 2.3 min, 57.4 mm3/s mean delivered,
#          ZERO firmware stalls, and SILENT. Oleg: "test was perfecrt".
#   70-90 under the identical conditions: the extruder CRACKED, by ear, with the firmware still
#          reporting zero stalls and healthy flow.
# So the BURST ceiling is between 65 and 70, and 65 is the highest figure actually demonstrated.
# This is a BURST number over 2.3 minutes. It says nothing about a 20-minute part — see
# SUSTAINED_FLOW, which came from a 16-minute failure and stays where it is until a soak moves it.
MATERIAL_FLOW = {"pla": FLOW, "pla-matte": 65.0, "petg": 40.0, "tpu": TPU_FLOW, "abs": 30.0}


def check_spool(printer, material):
    """A part generated for one printer with another printer's filament is silently wrong: right
    geometry, wrong temperature, wrong flow ceiling. Say so loudly rather than emit it quietly."""
    want = LOADED.get(printer)
    if want and material != want:
        print(f"  !! {printer} has {want} loaded, but this part is being generated for {material}. "
              f"Either load {material}, or drop --material and let it follow the printer.")
    return material
