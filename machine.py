"""Measured machine facts. Single source of truth — nothing hardcodes these numbers separately.

Oleg, 2026-07-25: "you should be extruding at max speed we know nozzle can flow. that is not
negotiable. 100% of the time."
"""
import math
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
# CAVEAT, 2026-07-29 — these "cracking/skipping" flow ceilings are now SUSPECT. Oleg's PLA had sat
# ~24h in 45% RH; the crackle "like fire burning" is the signature of WET filament (moisture flashing
# to steam at the nozzle), not the extruder losing grip. So the whole 81→74→70→60 walk may have been
# moisture misread as a flow limit. DO NOT trust any of these numbers, or the standing FLOW=55, until
# the ceiling is re-measured on a KNOWN-DRY spool (dry 45–55°C 4–6h). See memory lesson-wet-pla-crackle.
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
# 50 mm/s IS THE NORTH STAR FOR MOVING -- A DEFAULT, NOT A LAW.
# Oleg, 2026-07-27, correcting me: "speed is not fixed - 50 is north star default unless
# overruled by other constraints."
#
# I implemented it as an immovable constant, which is a different and worse rule. It made two
# legitimate things impossible:
#   * THE WIDE-BEAD TRICK. A fat bead at a fixed speed multiplies flow past anything the machine
#     can deliver (10mm x 0.6 x 50 = 300 mm3/s). The trick has always been to CRAWL with a fat
#     bead -- speed comes DOWN so the flow lands. Pinning speed inverted it and made 7 archived
#     commands unrunnable.
#   * TPU. Its working flow is 15.2 mm3/s. At a fixed 50 that needs a 0.51mm bead, narrower than
#     the nozzle -- so I reported TPU as unprintable. It is not: at the normal 1.2x0.6 bead it
#     simply runs at 21 mm/s. I turned my own over-strict rule into a claim about the material.
#
# What is actually required is CONSTANT movement within a print -- one speed, so material per mm
# does not change where the geometry is tightest. That is the thing worth guarding. The VALUE of
# that one speed is 50 unless a real constraint (flow ceiling, bead width, material) pushes it
# lower. It is never higher: 50 remains the ceiling.
DEFAULT_SPEED = 50.0        # the north star: where speed starts, not where it is stuck
CONSTANT_SPEED = DEFAULT_SPEED   # back-compat alias
MAX_SPEED = DEFAULT_SPEED        # never faster than the north star; slower is legitimate
# ============================================================================================
# LAYER 1 RUNS AT FULL FLOW. THE LINE WIDTH IS WHAT CHANGES. THIS IS NOT NEGOTIABLE.
#
# Oleg, 2026-07-27, after correcting it for the THIRD time in one session:
#   "i am so tierd of you dude. first layer we overextrude ...... how many times i have to yell
#    you first layer is 55 as well just line width is crazy high"
# and earlier:
#   "you have to go 15mm wide in settings do not worry of massive over extrusion, this is what
#    we do"
#   "the nozel need to be 0,1 to board. we need adhesion"
#
# So: same mm2 per mm as the body, laid into a PRESS_HARD gap. The material has nowhere to go
# but sideways, so it lands enormously wide and welds to the plate. A fill ratio of 3x on layer 1
# is the TECHNIQUE, not a defect.
#
# first_w = bead_w * layer_h / PRESS_HARD          <- the width it actually lands at
#
# WHY I KEEP GETTING THIS WRONG, recorded so the next session does not: metering layer 1 down to
# bead_w * PRESS_HARD looks obviously right (conservation of material into a thin gap) and every
# over-fill guard agrees with it. It is still wrong, because the guard models a bead that stays
# its nominal width. This one does not.
# ============================================================================================
FIRST_LAYER_SPEED = CONSTANT_SPEED   # see the note near the top; adhesion is the 0.1 press


def bead_for_flow(flow, layer_h, speed=DEFAULT_SPEED):
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
    # CORRECTED 2026-08-05 by Oleg at the machine: "material is 210c btw pla". This had read
    # pla-matte since 07-27, so every K2 file since then commanded 230C on filament rated 210 --
    # twenty degrees hot. Not cosmetic on a slender tower: hotter plastic stays fluid longer, which
    # is simultaneously the coiling failure and the stringing artifact. Both the six-tower coupon
    # and the collapsed single tower were printed at 230 on this wrong entry.
    "k2plus": "pla",         # 210C, corrected at the machine 2026-08-05
    "k1c":    "pla-matte",   # Oleg swapped 2026-07-27 late: "k1 is now wth pla 230 filament"
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
    "tpu":       15.2,      # MEASURED, not inherited: a ramp that ran clean to turn 27,
                         # with the margin deliberate, and TPU jams the extruder within a minute
                         # above it. Added 2026-07-27 because R6 was failing every TPU file for
                         # having no maintained figure — a real gap, not a reason to weaken R6.
                         # At a 1.2x0.6 bead this resolves to 21.1 mm/s, well under the north star.
    "pla-matte": 60.0,   # Oleg 2026-07-27, SECOND revision — by ear, mid-print: "k2 crack
                         # ocasionally lets reduce flow by 5". 65 ran silent on a 2.3-minute
                         # ramp; on a real multi-minute part the extruder began slipping
                         # occasionally. A burst figure is not a working figure, and the ear
                         # heard it before any instrument could: the firmware logged nothing.
                         # Trimmed live with M220 S92 (E is metered per mm, so cutting speed
                         # cuts flow and leaves deposit per mm untouched).
}
# THE 48.6 STALL WAS NOT A FLOW FAILURE. Oleg, 2026-07-27: "driver coocked because i closed the
# printer top with glass. will not again". The extruder driver over-heated because the enclosure
# was sealed and its heat had nowhere to go -- the flow rate was incidental. Everything built on
# top of that reading was therefore built on a misattributed cause: the duration clamp below
# assumed flow could only be held for N minutes, when what could not be held was a closed lid.
#
# This is the third time tonight the invariant named the cause and I read the variable instead.
# What stayed constant across that failure was the glass, not the mm3/s.
#
# KEPT, because a failure is still a fact -- but recorded with its ACTUAL mechanism so it stops
# being cited as a flow limit:
# FLOW IS A PROPERTY OF THE MACHINE AS WELL AS THE FILAMENT. The maintained figures above were
# established on the K2 Plus. The K1C has a different hotend and a different extruder, so applying
# K2's number to it is the same defect as applying one filament's number to another -- which this
# file has now been bitten by twice.
#
# Oleg, 2026-07-27, mid-print: "k1 is clicking. meaning flow is too much" -- at the inherited 55.
# Clicking is the extruder losing grip, and it is upstream of anything the firmware reports.
# Trimmed live with M220 S85 (46.8 mm3/s). Recorded BELOW that, because the click is the ceiling
# and a ceiling is not a target.
#
# PROVENANCE: by ear, one part, not a soak. Confirm or raise it with a real run before trusting it.
# HOW MUCH SMALLER A PRINTED HOLE COMES OUT THAN THE MODELLED ONE.
# MEASURED TWICE, on different parts, different beads, different machines:
#   rosetta   modelled  9.13 -> printed  3.17   inset 2.978 mm   (bead 2.17, k2plus)
#   pole ring modelled 36.12 -> printed 30.00   inset 3.060 mm   (bead 1.50, k1c)
# As a MULTIPLE of bead width those are 1.37 and 2.04 -- inconsistent, so the "1.373 x bead"
# model that came from the first measurement alone was WRONG. As an ABSOLUTE they agree within
# 3%. The inset is a constant, not a proportion: the material bulges into the void by about
# 3 mm regardless of how wide the bead is.
# A hole must therefore be modelled 6 mm larger in diameter than the hole you want.
# Below ~6 mm modelled, no hole survives at all -- which is exactly why a 2.5 mm eye printed solid.
# Hot enough that a previous print's residue softens and lets go, cool enough that PLA does not
# ooze onto the tip while the probe touches the plate. See the note at the G28 in solid.py.
PROBE_TEMP = 150

BORE_INSET_MM = 3.02          # mean of the two measurements

def bore_model(hole_d):
    """The modelled diameter that yields `hole_d` after printing."""
    return hole_d + 2.0 * BORE_INSET_MM


PRINTER_FLOW_CAP = {
    "k2plus": None,   # the machine the maintained figures were measured on
    "k1c":    45.0,   # clicked at 55; 46.8 ran quiet. Held under that.
    "f022":   45.0,   # same hotend family as the k1c, untested -- assumed, not measured
}


def flow_cap(material, printer):
    """The lower of what the filament can hold and what THIS machine can hold."""
    m = SUSTAINED_FLOW_BY_MATERIAL.get(material)
    p = PRINTER_FLOW_CAP.get(printer)
    if m is None:
        return p
    return m if p is None else min(m, p)


KNOWN_FAILURE = {
    "pla": (48.6, 16),   # 2026-07-26. CAUSE: sealed enclosure (glass top on), driver over-heat.
                         # NOT a flow ceiling. Top stays open now.
}
                           # which is a floor on the true value, not the value itself.
# SUSTAINED_MINS EXISTS ONLY AS A PLACEHOLDER NOW. It was set when the 16-minute stall was read
# as a flow-duration limit; that reading is withdrawn (see KNOWN_FAILURE above). No measurement
# says flow decays with time on an OPEN machine. It stays wired up so a real soak failure has
# somewhere to be recorded, but with both materials' maintained figures at or above what anything
# actually asks for, it no longer clamps real parts.
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
# Oleg, 2026-07-27: "ok lets not start with bed below 100". Not a per-material preference and
# not scaled by part size -- a floor. His earlier "you dont need to wait for 120 plate" set the
# ceiling on waiting; this sets the floor on starting.
# BED_START_MIN retired 2026-07-27 ("everything 120"): the start floor is now always
# 5C under the machine-held target — see bed_start().


def flow_derate_stamp(material, printer, delivered):
    """R8 companion: the ; FLOW_DERATE= line a generator MUST emit when it delivers under 80%
    of the material+printer figure. One source of truth so six generators cannot drift.
    Returns None at a healthy operating point."""
    cap = flow_cap(material, printer)
    if cap and delivered < 0.8 * cap:
        return (f"; FLOW_DERATE=bead pinned at the {BEAD_W:g}x{BEAD_H:g} stacking doctrine -> "
                f"{delivered:g} of {cap:g} mm3/s at the {DEFAULT_SPEED:g} north star. "
                f"Widening the bead is the fix if this part's walls allow it.")
    return None


def bed_start(material, bed):
    """Temperature the plate must actually REACH before printing may begin.

    Oleg, 2026-07-27 (after "why k2 bed only 100?"): "everything 120" — the start-early floor
    is retired; every print now waits for the FULL machine-capped target, minus only the
    stall-safety margin. The old footprint-scaled 100 floor let small parts start while the
    plate was still climbing; he watched the towers start at 100 and does not want that.

    Still clamped UNDER the machine-capped target because this becomes a BLOCKING M190: a
    floor the bed cannot provably cross is an infinite stall, not a rule. The K1C at target 90
    settles at 87.4 with power pinned at 1.00 (measured 2026-07-26), so 5C under the held
    target is the margin: K2 waits to 115 of a held 120, K1C to 85 of its measured ~87-91.
    """
    return bed - 5


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

# ---------------------------------------------------------------- layer 1 ---
# ONE PLACE FOR THE FIRST-LAYER ARITHMETIC, because three copies of it had already drifted.
# On 2026-08-06 bucket_towers.py metered layer 1 as `w1 * PRESS_HARD / A_FIL` while zladder.py
# metered it as `w1 * the height the bead actually lands at`. Those agree only when the machine's
# Z zero is honest, and on this K2 it is not -- it homes about 0.15mm high. So the bucket would have
# laid HALF the width its own header claimed at any first-layer height except 0.10, silently, with
# every gate green: validate.py R1 reads the COMMANDED Z and cannot see where the plate is.
#
# A_FIL lived as a local in five generators as well. A constant copied is a constant that can be
# edited in one place and stay wrong in four.
A_FIL = math.pi * (1.75 / 2) ** 2       # 2.40528 mm2 of 1.75mm filament


def layer1_rate(landed_w, gap):
    """Filament mm per mm of path to land a bead `landed_w` wide in a `gap` high.

    STATED AS A LANDED WIDTH, NOT A FLOW MULTIPLIER, and that is deliberate: a width is the thing
    measurable on the plate with callipers, while a multiplier can only be checked by rerunning the
    arithmetic that produced it, which is not an independent check.

    `gap` IS THE HEIGHT THE BEAD LANDS AT, not PRESS_HARD. Passing PRESS_HARD when the real gap is
    something else is exactly the bug this function exists to stop being written a fourth time."""
    if gap <= 0:
        raise ValueError(f"layer1_rate: gap {gap!r} is not a positive height")
    if landed_w <= 0:
        raise ValueError(f"layer1_rate: landed_w {landed_w!r} is not a positive width")
    return landed_w * gap / A_FIL


def zoff_for(h1, zerr):
    """The SET_GCODE_OFFSET Z that makes a commanded PRESS_HARD first layer land `h1` high.

    `zerr` is how much HIGHER than it reports this machine's Z zero sits. MEASURED on the K2 on
    2026-08-06 off a printed ladder, not by feel: at offset -0.15 the first layer was clean and at
    -0.20 the nozzle dragged through material it had just laid. A paper feeler said 0.30 and was
    wrong by 2x, because the spring-steel sheet flexes under the shim and absorbs the very quantity
    being measured.

    A POSITIVE RESULT IS REFUSED HERE rather than left to a caller. Positive lifts the nozzle AWAY
    from the plate, which is the defect, not a test of it -- and no gate downstream can catch it,
    because validate.py sees only the commanded Z."""
    off = round(h1 - PRESS_HARD - zerr, 4)
    if off > 1e-9:
        raise ValueError(
            f"zoff_for({h1:g}, {zerr:g}) = {off:+g}, which is POSITIVE and would lift the nozzle "
            f"above the machine's own zero. With this zerr the tallest reachable first layer is "
            f"{PRESS_HARD + zerr:.3f}mm.")
    return off


# HOW MUCH HIGHER THAN IT REPORTS EACH MACHINE'S Z ZERO SITS, mm -- the `zerr` above, as a fact
# about a named machine rather than a number a caller passes in. It lives here because the gate
# that reads it (validate.py R9) and the generators that write the offset must not hold two copies
# of it; that is the same drift that put three different first-layer models in three files.
#
# A MACHINE WITH NO ENTRY IS NOT A MACHINE WITH ZERO ERROR. It is a machine nobody has measured,
# and R9 says so and declines to judge its first layer rather than handing out a tick. Defaulting
# a missing measurement to 0.0 would have every k1c file report a pressed 0.100 layer on the
# strength of nothing at all -- which is exactly how the K2 shipped five cancelled starts.
ZERR = {
    "k2plus": 0.15,     # MEASURED 2026-08-06 off a printed ladder; see zoff_for's docstring
}


# THE FIRST-LAYER OPERATING POINTS THAT HAVE PRINTED AND HELD, per machine: (landed height mm,
# landed width mm). NOT a range and NOT a default -- a list of pairs somebody watched come off the
# plate. Anything else is unproven and R9 refuses it unless the file cites the coupon that tested
# it.
#
# WHY A PAIR AND NOT TWO INDEPENDENT NUMBERS. Height and width are one setting: the same material
# squashed into a thinner gap lands wider, so 2.00mm at 0.10 and 2.00mm at 0.15 are different
# welds, and the second is the one that came off Oleg's bamboo bucket as separated lifted strands
# on 2026-08-06. Checking them separately would have passed it.
#
# HOW AN ENTRY GETS ADDED: print the ladder, read the plate, and add the pair with the date and
# what was seen. Not from arithmetic, and not from a print that merely finished.
PROVEN_LAYER1 = {
    # 0.10 x 2.00 -- the 320x300 bucket printed complete and stood (2026-08-06), and the 341.5mm
    # bamboo bucket's base at these numbers was accepted by Oleg the same day. 2.00 landed into a
    # 0.10 gap is 0.200 mm2/mm, which is the body's own 0.82x0.24 bead (0.197) pressed flat: layer
    # 1 is not over-extruded here, it is the same material 2.4x thinner and so 2.4x wider.
    "k2plus": [(0.10, 2.00)],
}


# ------------------------------------------------------------------- the send ledger ---
# THE VALUES THAT HAVE BEEN ON A PLATE AND WERE ACCEPTED, per machine, per send-critical parameter.
# Read by send.py, which is the only path to a printer. PROVEN_LAYER1 above is the first entry of
# this same ledger and is NOT copied here -- send.py asks it directly, because a second copy of the
# proven first layer is exactly the drift that put three different first-layer models in three
# files.
#
# WHY THIS EXISTS SEPARATELY FROM validate.py. Every gate written on 2026-08-06 -- R9, R10, R4e,
# and bucket_towers' own gates 5 and 6 -- runs on a FILE, and all of them passed on files that then
# failed on the plate. Nothing guarded the DECISION TO PRINT: uploading and pressing start was done
# by hand, on judgement, by an actor that is not deterministic. Four plates were lost through that
# gap in one day. This is the ledger that gap is checked against.
#
# EVERY ENTRY IS A THING SOMEBODY WATCHED COME OFF A PLATE, NOT A RANGE AND NOT A DEFAULT. Ranges
# are why the stencil coupon printed: 1.00x coverage sits between 0.80 and 1.25, so any threshold
# would have passed it, and it had already been written down as likely to pinhole before it ran.
# A LIST REFUSES WHAT SITS BETWEEN TWO PROVEN POINTS. That is the whole difference.
#
# HOW AN ENTRY GETS ADDED, and it is deliberately not a function call: a human edits this file.
# send.py has NO code path that writes here. The actor that decides to print must not also hold the
# key to the set it is checked against. `send.py accept` will PRINT a ready-made entry, but only
# for a file that appears in send-log.jsonl as an actual live send, only with `--by oleg`, and only
# on the word `held` -- never on `completed`. COMPLETION IS NOT ACCEPTANCE: the 100mm bucket
# completed for weeks against a wrong Z zero, masked by 1.52x layer-1 flow, and was read as a
# baseline.
#
# THE LAST FIELD OF EVERY TUPLE IS PROVENANCE and it is not decoration. A value with no story is a
# value nobody can argue with, which is how an invented constant labelled MEASURED survived here
# once already.
SEND_LEDGER_VERSION = "2026-08-06.2"

# MOTION-ONLY MINUTES PAST WHICH A COUPON-BACKED VALUE IS NO LONGER ENOUGH ON ITS OWN.
# A coupon proves a value AT COUPON SCALE. The stencil ran 5.7 min and the bore gauge 20.5 min;
# nothing that has ever been read off a plate here took more than half an hour. 90 is ~4x the
# longest coupon anybody has actually read, and it is the point where a failure costs an evening
# rather than a coffee -- which is a different decision from "is this value sound", and so it is
# asked separately. It is deliberately NOT scaled from the estimate's error: validate's number is
# motion-only and the K2 adds a roughly FIXED calibration block (+2.2 min on the stencil, +11.0 on
# the gauge, +1.37 h on the 320 bucket), so a ratio taken from a bucket must never be applied to a
# coupon. Overridable with `--allow-long --why`, which is RECORDED in send-log.jsonl.
LONG_PRINT_MIN = 90.0

PROVEN_SEND = {
    "k2plus": {
        # (landed w1 mm, floor line pitch mm, provenance) -- THE PAIR, because coverage is what
        # welds and either number alone is meaningless. Raising --w1 2 -> 3 -> 5 never closed a
        # gappy floor because the nozzle never travels into the gap; the pitch decides that.
        "coverage": [
            (2.00, 1.6, "320x300 bucket printed complete and STOOD 2026-08-06; 1.25x, a solid "
                        "sheet. Measured off its own moves: 196 gaps at 1.6."),
            (2.00, 2.5, "the 341.5mm bamboo bucket's base at a 2.5 grid was accepted by Oleg "
                        "2026-08-06; 0.80x, an open latch grid on purpose. 132 gaps at 2.5."),
            # 1.00x IS ABSENT ON PURPOSE. It is the stencil coupon, it is the theoretical minimum
            # with zero margin, it was recorded hours before the run as likely to pinhole, and it
            # came off as separated strands. It sits BETWEEN two proven points, which is exactly
            # what a list of watched pairs is for and a threshold is not.
        ],
        # (purge mm of filament, lead-in fat multiplier or None, stationary mm, provenance)
        "prime": [
            (12.0, None, 12.0,
             "the 320x300 bucket that stood, measured: `G1 E12 F300 ; PRIME stationary purge`. "
             "IT IS THE ONLY PRIME WITH AN ACCEPTED PRINT BEHIND IT, AND validate.py R10 NOW "
             "REFUSES IT -- Oleg photographed the clump it leaves on the nozzle and then that "
             "clump dropped into a printing plate. So this entry is unreachable, and saying so is "
             "the point: the 5.0mm moving purge that replaced it in 32 generators has NO accepted "
             "print, and a file carrying it must cite the coupon that ran it."),
            (5.0, 1.2, 0.0,
             "the bore+lock gauge borelock_k2plus_pla_b3.6-4.6x6_w250-280_h18.gcode ran it as rule "
             "6's first proof and COMPLETED: 12.52 min of motion, 1562.7mm of filament against "
             "1550.66 emitted (100.8%), and 11 consecutive homing_origin samples at -0.150. The "
             "charge worked -- 121mm of filament had moved by minute 1, and the watcher's "
             "no-extrusion branch (under 5mm by minute 3) never fired. Oleg read the resulting "
             "plate at the machine on 2026-08-06 and picked a cell off it, so the plate was "
             "USABLE. "
             "WHAT THIS ENTRY DOES NOT REST ON, stated because a ledger that overclaims is worse "
             "than an empty one: nobody has separately reported how the PRIME WITNESS LINE itself "
             "came out. He judged the twelve cells, not the line. So this admits 'the moving prime "
             "produced a plate good enough to read', which is weaker than 'the witness line was "
             "clean'. If that line turns out thin or broken, this row is the thing to retract, and "
             "the fix it points at is a longer lead-in than 50mm at the same 5mm charge -- never a "
             "bigger stationary dump, which is what R10 exists to refuse."),
        ],
        # (max tip-to-tip span of one unsubdivided BRIDGE / THIN CROSS move, mm, provenance)
        "span_mm": [
            (17.85, "every one of the 7000 bridge and 62776 thin-cross moves in the 320x300 bucket "
                    "that stood measures exactly 17.85mm. Its own header calls 16.8mm of that "
                    "UNSUPPORTED AIR, and 16.8 is the only span this project has ever seen hold."),
        ],
        # (mm/s on '; THIN CROSS' moves, provenance)
        "cross_mms": [
            (50.0, "the north star. A crossing at the body's own speed is not a second regime at "
                   "all, and everything this project has printed has laid material at 50."),
            (100.0, "VERIFIED LIVE on the machine: 44 samples at 100 mm/s against 65 at 50, taken "
                    "at z=3.22. Sampling the floor instead would have proved the opposite."),
        ],
        # (nozzle C, bed C, provenance)
        "temps": [
            (210, 60, "Oleg at the machine 2026-08-05: 'material is 210c btw pla'. machine.LOADED "
                      "had read pla-matte since 07-27, so every K2 file commanded 230 on filament "
                      "rated 210 and a tower coiled into a rope; at 210 the identical geometry "
                      "stood. Bed 60 is the mid of the filament's rated 50-70 and the minimum that "
                      "works -- 0 gave 'spagetti, no adhesion' twice and 120 held PLA above Tg so "
                      "a pressed floor never set."),
        ],
        # (bore mm, provenance) -- EMPTY, AND THAT IS THE HONEST STATE.
        # The bore was guessed twice, printed twice and wrong twice before a gauge was printed, and
        # the gauge's answer has not been read back into this file. SHRINK=0.25 was calibrated on a
        # 4mm METAL hole, silently sized every 6.35mm BAMBOO bore, and condemned ~21 printed parts.
        # An empty list means every file that declares a bore must cite a gauge. That is correct.
        # NO LONGER EMPTY as of 2026-08-06: the gauge was printed and READ.
        "fit_bore": [
            # 4.40 SUPERSEDES 4.20, AND THE REASON IS A LENGTH NOBODY RECORDED.
            # Oleg, 2026-08-07: "when you printed coupons it was correctly picked but its near to
            # impossible to inserve on longer span, so we need to selected the one next to one i
            # selected but bigger". Cell 5 of the same gauge, one step up.
            #
            # THE GAUGE'S CHANNELS ARE 18mm TALL. THE BUCKET'S ARE 359mm. A stick that clicks into
            # 18mm of channel has to slide through TWENTY TIMES that, and every per-layer wobble,
            # twist and taper accumulates over the length. The coupon reproduced the bucket's bore,
            # its wrap, its bead and its flow -- and not its INSERTION LENGTH, which is the one
            # dimension that decides whether a stick goes in.
            #
            # So 4.20 was not wrong: it was proven at 18mm and cited at 359mm, and the entry never
            # carried the length that made it true. Same shape as PROVEN_LAYER1's (0.10, 2.00),
            # which was proven at layer 0.24 and silently reused at 0.48.
            (4.40,
             "cell 5 of the bore+lock gauge, taken 2026-08-07 after 4.20 (cell 4) proved "
             "IMPOSSIBLE TO INSERT over the bucket's full 359mm. Oleg: 'near to impossible to "
             "inserve on longer span, so we need to selected the one next to one i selected but "
             "bigger'. Modelled mouth 3.456mm against a 3.175mm stick, +0.281 wider than the stick "
             "on the model, and the gauge's own header predicted 'DROPS IN, no capture' for it -- "
             "which cell 4 also carried and did NOT do, so the printed part runs tighter than the "
             "model by more than 0.117mm and this entry is the second point on that line. "
             "STILL UNMEASURED: nobody has put calipers on a printed channel, and this is a fit "
             "read by hand over 18mm of coupon, now chosen FOR 359mm on the argument that longer "
             "needs looser. That argument is sound and it is not a measurement."),
            (4.20,
             "SUPERSEDED 2026-08-07 by the 4.40 entry above, and kept because it is the FIRST point on the shrink line and because the reason it failed is the lesson. It was read on 18mm-tall coupon channels and then cited for a 359mm part; it grips at coupon length and is near impossible to insert at part length. LEFT HERE so nobody re-derives it. "
             "Oleg read the gauge plate at the machine 2026-08-06 and said 'go with 4'. Cell 4 is "
             "a 4.20mm modelled bore at a 250 degree wrap. "
             "WHY THIS IS A REAL RESULT AND NOT A PREFERENCE: cell 4 was that plate's NEGATIVE "
             "CONTROL. Its modelled mouth is 3.292mm against a 3.175mm stick, +0.117 WIDER, and the "
             "file's own header predicted it would drop straight through with no capture. It was "
             "printed precisely so that a plate which lied would be caught. He chose it, so the "
             "PRINTED part is TIGHTER than the model, which means SHRINK=0.25 understates the real "
             "shrink. That constant was calibrated on a 4mm METAL shaft hole, reused for bamboo, "
             "and condemned ~21 parts. The gauge existed to falsify it and it did.\n"
             "WHAT IS STILL UNMEASURED: 4.20 is the MODELLED bore, which is what a toolpath "
             "measures and therefore what S7 compares against. The PHYSICAL printed bore is "
             "smaller by the true shrink, and nobody has put calipers on a cell. So the shrink "
             "CONSTANT is still unknown; what is known is which modelled bore lands right, and for "
             "a part cut to fit a stick that is the number that matters."),
        ],
    },
}

# THE ONLY BRIDGE SPAN THAT HAS ACTUALLY HELD, mm of unsupported air. towercoupon.py, printed
# 2026-08-05: strands across 16.80mm between 25mm-pitch towers pulled TAUT at full flow and
# 50 mm/s. A LOWER BOUND (16.8 held; nothing says 17 does not). Lived in bucket_towers.py as
# PROVEN_AIR_MM until 2026-08-07, when validate.py's overhang gate needed the same fact -- the
# gate's frame was corrected from fraction-of-points to RUN LENGTH (an unsupported run IS a
# bridge, and this is the span evidence it is judged against), and two files may not hold two
# copies of one measurement. bucket_towers.py imports it from here.
PROVEN_AIR_MM = 16.80

# THE HEAVIEST LIP THAT HAS EVER BEEN INSERTED, per machine: mm3 of deposit per mm2 of wall in the
# WORST per-layer regime at the C-channel's mouth lips. The lips are where every crossing, every
# merge lap and every bridge rod-end lands, so this is the quantity that decides whether a stick
# still goes in -- and it was UNGUARDED until 2026-08-07, when doubling the layer height doubled
# the flows that feed it and Oleg's 1/8in stick stopped entering a bucket whose BORE had just been
# made 0.2mm looser. The bore never changed on the plate; the lips grew inward.
#
# THE NUMBER IS lh-INVARIANT BY CONSTRUCTION, which is why it survives a layer-height change when
# every mm-spacing rule silently does not: one crossing per layer spans one lh of wall height, so
# per-area deposit = flow_fraction x bead_width, and a mult-m bridge every N LAYERS contributes
# m x bead / N -- the lh cancels in both. Preserving mm-spacing across a layer change (bb50x2 at
# 0.48 to imitate bb100x5's 1.2mm) is exactly the mistake this constant exists to refuse: rod ends
# thicken WITH the layer, so the layer-COUNT cadence is the thing to hold, not the millimetres.
#
# MEASURED, not derived: the 2026-08-07 00:53 bucket (d339.5 n28t5.84 w250 b20 bb100x5 x25 j2,
# layer 0.24, bore 4.20) is the only part whose insertion over the full 359mm was ever physically
# attempted. Its emitted bytes read fabric 0.0492mm2/mm (0.25x), laps 0.0492mm2/mm per pass
# (MERGE_MM2=0.0492, follows cross), band bridges 2.00x every 5 layers. Worst regime (the band):
#   bead x (wall 1 + laps 2x0.25 + fabric 0.25 + band 2/5) = 0.82 x 2.15 = 1.7630 mm3/mm2
# AND IT IS A MARGINAL CEILING, NOT A COMFORTABLE PASS: Oleg, 2026-08-07, of that part at bore
# 4.20: "its near to impossible to inserve on longer span". At this lip density insertion works
# only barely -- so a file may match it, never exceed it, and the margin is bought with BORE
# (4.40 supersedes 4.20 in fit_bore above), never by piling more onto the lips.
# The 2026-08-07 15:44 file that Oleg cancelled ran 0.82 x 3.50 = 2.87 = 1.63x this, and did not
# accept the stick at all: that file is this constant's red proof.
PROVEN_LIP = {
    "k2plus": 1.7630,
}

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


# THE PROBED MESH, WHICH IS SMALLER THAN THE PLATE. Until 2026-08-06 these four numbers per machine
# existed ONLY as the comment three lines above BED, so nothing could check them -- and eight
# emitted files primed outside the mesh in consequence: six k1c files laid their prime at X6.0 or
# Y6.0 on a machine whose mesh starts at 10.0 (a `max(6.0, ...)` clamp chosen for the K2 and copied
# across), and two volume_marker files wiped at Y348 on a mesh that ends at 345. Outside the mesh
# Klipper EXTRAPOLATES the bed shape, so a first layer there is laid against a guess.
#
# READ from each machine's own [bed_mesh] mesh_min/mesh_max, 2026-07-25, same reading that produced
# the BED comment above. (x_min, y_min, x_max, y_max).
#
# A MACHINE WITH NO ENTRY IS NOT A MACHINE WITH AN UNLIMITED MESH -- it is one nobody has read, and
# prime() below refuses rather than inventing a window, for the same reason ZERR refuses to default
# to zero. f022 is absent on purpose: nobody has opened its config.
MESH = {
    "k1c":    (10.0, 10.0, 210.0, 210.0),
    "k2plus": (5.0, 5.0, 345.0, 345.0),
}


# ---------------------------------------------------------------------- the prime ---
# EXTRUDATE MUST BE PINNED TO THE PLATE FROM THE FIRST MILLIMETRE IT LEAVES THE NOZZLE.
#
# Oleg, 2026-08-06, photographing a clump of filament hanging off the nozzle and then a lump of it
# dropped into the middle of a printing plate: "The beginning of extrusion need to be improved
# generically" / "Also few unacceptable artifacts".
#
# WHAT WAS THERE BEFORE, AND WHY IT COULD NOT WORK. Thirty-two generators each hand-rolled an
# opening sequence, in seven distinct shapes, and every one of them began by extruding 12 to 25mm
# of filament (28.9 to 60.1 mm3) WITH THE HEAD STANDING STILL. Both ends of the only axis anybody
# varied are already written down in this repo as failures:
#   at the press gap (presstest.py:168) "a 20mm stationary purge (~48mm3) at the 0.1 press gap
#     cannot spread -- it balloons up and COLLARS the nozzle"
#   lifted to Z2 (borelock.py and four others) is Oleg's photograph: 4.0 seconds of extrusion makes
#     ~96mm of 0.8mm strand falling 2.0mm into open air, whose own weight is 0.56 mN against wetted
#     adhesion to hot brass over several mm2. It cannot fall away. It coils onto the tip, and the
#     head then carries it into the part.
# The third option is the one nobody tried: DO NOT EXTRUDE WITHOUT MOVING, at any Z. The only force
# that strips melt off a 210C brass face is tension at the far end of the strand, and the only thing
# that supplies it is a bead already welded to the plate. The plate is the tool. validate.py R10
# refuses the alternative on the emitted artifact so this cannot drift back.
#
# HOW MUCH FILAMENT THE OPENING ACTUALLY NEEDS. DERIVED, NOT MEASURED, and the falsifier is stated.
# The inherited 12/18/20/25 all sit inside the geometric melt-zone bracket (a 2.0mm channel 12-22mm
# long is 37.7-69.1 mm3 = 15.7-28.7mm of filament), which is the tell: they answer "how much fills
# an EMPTY hotend", a filament-change number. At the start of a print the melt zone is already full.
# What is actually missing is two much smaller things:
#   drool during heat-up and probe -- PLA at 1.24 solid to 1.18 melt is +5.1% on ~50mm3 of zone
#     contents = 2.5 mm3, plus gravity creep (driving head rho.g.h = 232 Pa against a Laplace
#     back-pressure 2.gamma/r = 150 Pa, net ~80 Pa, order 0.005 mm3/s over the 200-400s of
#     M190/M109/G28) = 1-2 mm3. Total 3.5 to 5 mm3.
#   pressure re-establishment -- at layer 1's own 5.0 mm3/s the melt pressure is ~5 bar, so 1.2 N on
#     the filament; a 25mm direct-drive column at EA/L = 337 N/mm compresses 0.004mm, and the melt
#     itself 0.017 mm3. Under a worst-case 800mm Bowden at 30 N it is still only 2.9mm of filament.
#     There is no pressure argument for 20mm; the stored compliance is under 0.05 mm3.
# So the purge exists to expel the degraded tip slug, not to fill anything, and 5.0mm of filament
# (12.0 mm3) is 2.5x the high drool estimate and 50x every compliance term.
# FALSIFIER: if the first 20-30mm of the lead-in prints thin, gappy or discontinuous, the slug is
# too small and the fix is a LONGER lead-in, never a stationary dump.
PRIME_PURGE_MM = 5.0        # filament mm of deliberate purge, DERIVED above, not weighed

# The lead-in is over-fat ON PURPOSE, which is the same technique this file already documents for
# layer 1 ("LAYER 1 RUNS AT FULL FLOW. THE LINE WIDTH IS WHAT CHANGES"). It is bounded, because the
# old prime lines ran 2.4x to 5.0x the part's own layer-1 rate -- 0.601 mm2/mm asks a 0.8 orifice to
# spread a 6.0mm bead in one pass at a 0.10 gap, which it cannot do, so the excess goes up and round
# the tip. That is a SECOND blob source, in the moving line, and fixing only the stationary purge
# would have left it. Every rate below is a multiple of the caller's own layer1_rate, so the prime
# physically cannot be a different bead from the part's first layer.
PRIME_FAT = 1.20            # lead-in rate, x the part's layer-1 rate -> 1.2x its landed width
PRIME_FAT_MAX = 1.50        # past this the nozzle ploughs its own bead; refused, not clamped

PRIME_TAPER = (0.60, 0.30, 0.10, 0.00)   # rate multipliers over the last segments
PRIME_TAPER_SEG = 5.0       # mm of path per taper step -- pressure decays WHILE motion continues,
                            # so nothing is left stored when the E word stops. This project has no
                            # retraction (validate.py refuses a backward E as an unintended one), so
                            # the end of a line has to be geometric and hydraulic or nothing.
PRIME_WIPE_MM = 18.0        # E frozen, retraced back over the taper at travel speed: any residue is
                            # ironed into the thinnest, most sacrificial part of the line instead of
                            # dangling, and a drawn thread necks as 1/v.

PRIME_ROW_PITCH = 3.0       # mm between serpentine rows. Wider than the ~2.4mm landed lead-in bead
                            # ON PURPOSE: the rows stay separate strands, so the prime peels off the
                            # sheet as loose lines rather than as a welded patch. A prime pressed to
                            # 0.10 is genuinely hard to remove and that is its real cost.
PRIME_MESH_INSET = 10.0     # mm inside the probed mesh. Half the fattest landed bead is 1.2mm; the
                            # rest is so the bead is not sitting on the outermost probe point.
PRIME_PART_CLEAR = 6.5      # mm from part material: 5.0 plus half the fattest landed prime bead.
PRIME_DEPART_MM = 12.0      # runway reserved at the end of the last row so the break-off wipe has
                            # proven-clear plate to finish on.
# THE WITNESS IS A PATH LENGTH, NOT WHATEVER FITS. First version of this sized the prime to the
# region it found, capped at a flat 200mm -- so zladder, whose prime is laid into a 0.25mm gap and
# therefore takes 2.5x the filament per mm of path, emitted 39.3mm of filament (94.5 mm3) where the
# buckets emitted 10 to 16. The region tells you what is POSSIBLE; the diagnostic value of a witness
# line is how far you can watch it stay continuous and full width, and that is measured in mm of
# line. Everything past it is material to peel off, not information.
PRIME_WITNESS_MM = 80.0     # target witness run
PRIME_WITNESS_MIN = 40.0    # below this there is nothing to read; prime_region refuses instead


def _prime_blocked(shapes, along_y, fixed, clear):
    """Intervals of the moving axis that `shapes` (dilated by `clear`) put material into.

    Analytic, not sampled: a bounding box is the wrong frame for the parts this has to clear. The
    biggest thing this project prints is a 341.5mm circle on a 350mm plate, whose bbox covers the
    whole mesh and would leave no prime region at all, while its front-left corner is in fact wide
    open. Shapes are ('rect', x0, y0, x1, y1) or ('circle', cx, cy, r)."""
    out = []
    for sh in shapes:
        kind = sh[0]
        if kind == "rect":
            x0, y0, x1, y1 = sh[1:]
            # `along_y` = the row runs along Y, so X is the FIXED axis. Getting this pair the wrong
            # way round is invisible on a part centred on the plate (both coordinates are 175) and
            # wrong everywhere else, which is exactly the shape of bug that ships.
            lo_f, hi_f = (x0, x1) if along_y else (y0, y1)
            lo_m, hi_m = (y0, y1) if along_y else (x0, x1)
            if lo_f - clear <= fixed <= hi_f + clear:
                out.append((lo_m - clear, hi_m + clear))
        elif kind == "circle":
            cx, cy, r = sh[1:]
            c_f, c_m = (cx, cy) if along_y else (cy, cx)
            rr = r + clear
            dd = rr * rr - (fixed - c_f) ** 2
            if dd > 0:
                d = math.sqrt(dd)
                out.append((c_m - d, c_m + d))
        else:
            raise ValueError(f"prime: unknown avoid shape {sh!r}")
    return out


def _prime_free(lo, hi, blocked):
    """EVERY clear sub-interval of [lo, hi] once `blocked` is removed, in order.

    Returning all of them rather than the longest is not tidiness. A part centred on the plate
    leaves two mirror-image gaps of IDENTICAL length either side of it, so 'the longest' is decided
    by float noise and picked the left gap on one row and the right gap on the next -- rows that
    cannot be joined, and the search then reported no clear plate at all on a bed that is half
    empty. The rows have to agree on a side, so the caller intersects the full sets."""
    out = []
    cur = lo
    for b0, b1 in sorted(blocked) + [(hi, hi)]:
        if b0 > cur:
            a, b = cur, min(b0, hi)
            if b - a > 1e-9:
                out.append((a, b))
        cur = max(cur, b1)
        if cur >= hi:
            break
    return out


def _prime_intersect(a, b):
    """Intersection of two ordered interval lists."""
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi - lo > 1e-9:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def prime_region(printer, avoid=(), want=None, floor=None, near=None):
    """Pick the rectangle the prime is laid in, and the serpentine rows inside it.

    Returns (rows, meta). `rows` is a list of ((x0,y0),(x1,y1)) segments in print order, already
    joined end to end by construction; `meta` carries the numbers for the emitted comment.

    THE RECTANGLE IS THE POINT. Every generator until today asserted a corner was free in a source
    comment ("this corner is clear of it") and hardcoded px,py = 20,16. solid.py:684 is the one that
    wrote down what that costs: "a blind x0-40, which on a packed plate lies INSIDE layer-1
    material". A rectangle proven clear against the real footprints is a thing a gate can check; a
    comment is not. REFUSES rather than falling back to a default -- a prime laid into the part is
    worse than a job that does not start.

    All N rows share ONE x-span (the intersection across rows), so every connector between rows is
    a pure perpendicular hop of PRIME_ROW_PITCH that is inside the same proven-clear rectangle. The
    obvious alternative -- give each row its own longest span -- makes the connector a chord between
    two points on the part's dilated boundary, which for a circle lies INSIDE the part."""
    if printer not in MESH:
        raise ValueError(
            f"prime: no mesh window recorded for '{printer}'. machine.MESH holds "
            f"{sorted(MESH)}; add the machine's own [bed_mesh] mesh_min/mesh_max rather than "
            f"letting the prime guess where the probed area ends.")
    want = 150.0 if want is None else want
    floor = want if floor is None else floor
    mx0, my0, mx1, my1 = MESH[printer]
    bx0, by0 = mx0 + PRIME_MESH_INSET, my0 + PRIME_MESH_INSET
    bx1, by1 = mx1 - PRIME_MESH_INSET, my1 - PRIME_MESH_INSET

    best = None
    # Four edge strips. Rows run along the edge and step INWARD, so the fat lead-in is the row
    # furthest from the part and the taper ends nearest it -- the head never has to cross its own
    # prime to reach the body.
    edges = (("front", False, by0, +1.0), ("back", False, by1, -1.0),
             ("left", True, bx0, +1.0),  ("right", True, bx1, -1.0))
    for name, along_y, edge0, step in edges:
        mlo, mhi = (by0, by1) if along_y else (bx0, bx1)
        for n in range(2, 7):
            fixed = [edge0 + step * j * PRIME_ROW_PITCH for j in range(n)]
            shared = [(mlo, mhi)]
            for fx in fixed:
                shared = _prime_intersect(
                    shared, _prime_free(mlo, mhi,
                                        _prime_blocked(avoid, along_y, fx, PRIME_PART_CLEAR)))
                if not shared:
                    break
            if not shared:
                continue
            lo, hi = max(shared, key=lambda s: s[1] - s[0])
            run = hi - lo - PRIME_DEPART_MM
            if run <= 0:
                continue
            total = n * run + (n - 1) * PRIME_ROW_PITCH
            if total < floor:
                continue
            # The region says what is possible; `want` says what is worth laying. Trim, never grow.
            if total > want:
                run = max(0.0, (want - (n - 1) * PRIME_ROW_PITCH) / n)
                total = n * run + (n - 1) * PRIME_ROW_PITCH
                if run <= 0:
                    continue
            cand = (name, along_y, fixed, lo, lo + run, total, n)
            if best is None or n < best[6]:
                best = cand
            elif n == best[6] and near is not None:
                # Tie on row count: take the strip whose LAST row ends nearest the body's first
                # point, so the one travel between prime and part is the short one.
                def endpt(c):
                    return (c[4], c[2][-1]) if not c[1] else (c[2][-1], c[4])
                if math.dist(endpt(cand), near) < math.dist(endpt(best), near):
                    best = cand
    if best is None:
        raise ValueError(
            f"prime: no clear {floor:.0f}mm of plate inside {printer}'s mesh window "
            f"({mx0:g},{my0:g})-({mx1:g},{my1:g}) inset {PRIME_MESH_INSET:g}mm, keeping "
            f"{PRIME_PART_CLEAR:g}mm off the part. Move the part or shrink it -- a prime laid into "
            f"layer 1 is worse than a job that does not start.")

    name, along_y, fixed, lo, hi, total, n = best
    # Start end chosen so the LAST row finishes at `hi`, which is the end with PRIME_DEPART_MM of
    # reserved, proven-clear runway behind it for the break-off wipe.
    start_hi = (n % 2 == 0)
    rows = []
    for j, fx in enumerate(fixed):
        rev = start_hi if j % 2 == 0 else not start_hi
        a, b = (hi, lo) if rev else (lo, hi)
        rows.append((((fx, a), (fx, b)) if along_y else (((a, fx), (b, fx)))))
    meta = {"edge": name, "rows": n, "row_mm": hi - lo, "path_mm": total,
            "runway": PRIME_DEPART_MM, "box": (bx0, by0, bx1, by1)}
    return rows, meta


def prime(w, *, printer, z, rate, feed, travel_feed, avoid=(), near=None, reset_e=True, e0=0.0):
    """Emit the whole start-of-extrusion sequence. ONE implementation, for every generator.

    `w`            the emit callable the generator already has
    `printer`      for MESH -- replaces the hardcoded 6.0/20.0/16.0 corner in 32 files
    `z`            the first-layer Z the BODY will use. There is no second Z, because there is no
                   stationary purge to place; the whole lift/descend pair disappears with it.
    `rate`         filament mm per path mm. Pass machine.layer1_rate(w1, h1) -- the SAME call the
                   body's layer 1 makes -- so E stops being a hardcoded constant whose bead width is
                   an accident of part position. One `E37` in hilbert-shaped generators produced
                   THIRTEEN different mm2/mm across the emitted files, a 4.05x spread, because the
                   length was computed and E was not.
    `feed`         the part's own first-layer feedrate (mm/min). Kills F1200-vs-the-part's-own-f.
    `travel_feed`  the file's own travel feedrate, for the break-off wipe.
    `avoid`        ('rect',x0,y0,x1,y1) / ('circle',cx,cy,r) footprints of everything that will be
                   printed. NOT optional in spirit: an empty tuple means "nothing is on this plate".
    `near`         the body's first point, used only to break ties between equally good strips.

    Returns (x, y, e) -- where the head is and what the E axis reads -- so no caller re-derives it.
    Emits no '; BODY_START'; that stays the caller's, because the caller owns what follows."""
    if rate <= 0:
        raise ValueError(f"prime: rate {rate!r} is not a positive filament mm per path mm")
    lead_rate = rate * PRIME_FAT
    if PRIME_FAT > PRIME_FAT_MAX:
        raise ValueError(f"prime: PRIME_FAT {PRIME_FAT} exceeds {PRIME_FAT_MAX}")
    lead_mm = PRIME_PURGE_MM / lead_rate
    taper_mm = PRIME_TAPER_SEG * len(PRIME_TAPER)
    rows, meta = prime_region(printer, avoid=avoid,
                              want=lead_mm + PRIME_WITNESS_MM + taper_mm,
                              floor=lead_mm + PRIME_WITNESS_MIN + taper_mm, near=near)

    # Flatten the serpentine into one polyline: row, perpendicular connector, row, ...
    pts = [rows[0][0]]
    for a, b in rows:
        if pts[-1] != a:
            pts.append(a)
        pts.append(b)
    path = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if path < lead_mm + taper_mm:
        raise ValueError(f"prime: region gives {path:.1f}mm but the lead-in and taper alone need "
                         f"{lead_mm + taper_mm:.1f}mm")

    w(f"; PRIME  {meta['rows']} rows x {meta['row_mm']:.1f}mm on the {meta['edge']} of the mesh, "
      f"{path:.1f}mm of path, ALL OF IT PINNED -- no stationary extrusion at any Z (validate R10)")
    w(f"; PRIME  purge {PRIME_PURGE_MM:g}mm of filament over the first {lead_mm:.1f}mm at "
      f"{PRIME_FAT:g}x layer 1, then layer 1's own {rate:.5f}mm/mm as a first-layer WITNESS")
    w(f"G0 F{travel_feed} Z{max(z + 1.0, 1.0):.3f}   ; PRIME-TRAVEL lift, nothing on the plate yet")
    w(f"G0 F{travel_feed} X{pts[0][0]:.3f} Y{pts[0][1]:.3f}   ; PRIME-TRAVEL to the prime start")
    w(f"G1 F600 Z{z:.3f}   ; PRIME descend to the press gap -- the prime prints at the PART's gap, "
      f"so a thin or broken line here is the first layer failing in 8 seconds, not in 6 hours")

    # Walk the polyline, changing rate at the lead-in/witness boundary and through the taper.
    marks = [(0.0, lead_rate, "lead-in, purge"), (lead_mm, rate, "witness, layer 1's own rate")]
    for k, mul in enumerate(PRIME_TAPER):
        marks.append((path - taper_mm + k * PRIME_TAPER_SEG, rate * mul,
                      f"taper {mul:.2f}x -- pressure decays while motion continues"))
    cuts = sorted({0.0, path} | {m[0] for m in marks})

    def rate_at(s):
        r, lab = marks[0][1], marks[0][2]
        for s0, rr, ll in marks:
            if s >= s0 - 1e-9:
                r, lab = rr, ll
        return r, lab

    e = e0
    done = 0.0
    cx, cy = pts[0]
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        seg = math.dist((ax, ay), (bx, by))
        if seg <= 1e-9:
            continue
        # Split this segment wherever the rate changes, so no emitted move averages two rates.
        inner = [c for c in cuts if done + 1e-9 < c < done + seg - 1e-9]
        prev = 0.0
        for t in [c - done for c in inner] + [seg]:
            r, lab = rate_at(done + (prev + t) / 2.0)
            nx = ax + (bx - ax) * (t / seg)
            ny = ay + (by - ay) * (t / seg)
            e += r * (t - prev)
            w(f"G1 F{feed} X{nx:.3f} Y{ny:.3f} E{e:.5f}   ; PRIME {lab}")
            cx, cy = nx, ny
            prev = t
        done += seg

    # BREAK-OFF. No retraction exists in this project, so the tail is dealt with geometrically:
    # retrace the taper with E frozen at travel speed. The nozzle skims the 0.1mm-tall bead it just
    # laid, so residue is ironed into sacrificial material rather than carried onto layer 1, and the
    # thread necks as 1/v on the fast move.
    ux, uy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
    un = math.hypot(ux, uy) or 1.0
    ux, uy = ux / un, uy / un
    back = min(PRIME_WIPE_MM, math.dist(pts[-2], pts[-1]))
    wx, wy = cx - ux * back, cy - uy * back
    w(f"G0 F{travel_feed} X{wx:.3f} Y{wy:.3f}   ; PRIME break-off wipe -- {back:.0f}mm back over "
      f"the taper, E frozen, ironing the tail into sacrificial material")
    # ...and then OFF it, forward into the runway prime_region reserved and proved clear. The head
    # must not finish the prime standing on the prime: the generator's own first travel starts from
    # wherever this leaves it, and starting it on top of a fresh 0.10 bead drags the whole way out.
    dx, dy = cx + ux * PRIME_DEPART_MM, cy + uy * PRIME_DEPART_MM
    w(f"G0 F{travel_feed} X{dx:.3f} Y{dy:.3f}   ; PRIME break-off -- out onto the reserved "
      f"{PRIME_DEPART_MM:g}mm of clear plate; a drawn thread necks as 1/v, so this runs at travel "
      f"speed and not the F3000 the old break-off used")
    if reset_e:
        w("G92 E0")
        e = 0.0
    return dx, dy, e


# THE Z CEILING, WHICH IS toolhead.axis_maximum AND NOT A PLATE FIGURE. It is here because a part
# tall enough to matter finally got built: on 2026-08-06 the 359mm bucket ended with
# "G0 Z378.90" -- top_z + a hardcoded 20mm retreat -- on a machine whose axis_maximum Z is 360.
# Klipper refuses a move out of range, so the last line of a six-hour print would have aborted the
# job. Nothing caught it because no generator had ever asked for a height near the ceiling and the
# retreat was a constant nobody had reason to bound.
# READ off the K2's own Klipper axis_maximum. None means UNKNOWN for that machine, and a caller
# must then leave its behaviour alone rather than invent a bound -- an unmeasured clamp that
# silently shortens a retreat is a different bug, not a fix.
Z_MAX = {
    "k1c":    None,
    "k2plus": 360.0,      # toolhead.axis_maximum Z, read 2026-08-06
    "f022":   None,
}


def z_retreat(printer, top_z, want=20.0):
    """Where to park Z after a print: `want` above the part, but never above the machine's ceiling.

    Returns (z, capped) so the caller can DECLARE a shortened retreat instead of quietly making
    one. A retreat of zero is still returned rather than refused: the part is finished, and
    parking level with its top is worse than aborting the job on an out-of-range move."""
    ceil = Z_MAX.get(printer)
    z = top_z + want
    if ceil is None or z <= ceil:
        return z, False
    return max(top_z, ceil), True


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


# A SAVED BED MESH THIS MACHINE ALREADY HOLDS, verified present on the printer before being named
# here: `bed_mesh default` exists in the K2's own config. A machine with no entry gets a plain G28,
# because `BED_MESH_PROFILE LOAD=<name>` ERRORS on a missing profile and aborting a six-hour print
# to save twenty minutes is the wrong trade.
SAVED_MESH = {"k2plus": "default"}


def home(w, printer):
    """G28, and then PUT THE BED MESH BACK, because G28 throws it away.

    Oleg, 2026-08-07, on a 3-minute coupon: "why you executing clibration again?" and then "restore
    cache after running g28, or dont run g28 at all".

    WHAT ACTUALLY HAPPENS, and I got this wrong once before correcting it. The K2's
    `homing_override` runs on every G28 and contains `BED_MESH_CLEAR`, so homing DISCARDS the active
    mesh. The firmware then rebuilds it: `bed_mesh` is probe_count [9, 9] over [5,5]..[345,345], so
    81 points, which on a large footprint is about twenty minutes -- SIX TIMES the runtime of a
    3-minute coupon.

    I FIRST TOLD HIM THIS WAS NOT OUR FILE. That was wrong and the evidence I cited was the thing
    that disproved it: the routine runs at nozzle 140 / bed 50, and I argued those could not be ours
    because our files command 210/60. They are `custom_macro.g28_ext_temp` = 140 and
    `default_bed_temp` = 50 -- **G28's OWN probe temperatures**. The temps did not show the routine
    was external, they showed G28 owns it.

    So the fix is his: restore what G28 cleared. `BED_MESH_PROFILE LOAD=<name>` costs nothing and
    puts back a mesh the machine already measured.

    WHY NOT SIMPLY DROP G28, the other half of what he offered: without homing, every commanded
    position is relative to wherever the head happened to be left, and this project's whole
    first-layer doctrine is a 0.1mm gap. A part that skips homing is a part with no Z reference at
    all. Homing is cheap; the MESH REBUILD after it is what costs twenty minutes, and that is the
    thing being fixed.

    NOT EMITTED FOR A MACHINE WITH NO VERIFIED SAVED PROFILE. Klipper errors on a missing profile,
    and killing a print for a mesh is worse than waiting for one.
    """
    w("G28")
    prof = SAVED_MESH.get(printer)
    if prof:
        w(f"BED_MESH_PROFILE LOAD={prof}"
          f"      ; G28's homing_override runs BED_MESH_CLEAR, so this puts back the mesh it")
        w(f";                                       just threw away. Without it the firmware "
          f"re-probes 81 points, ~20 min.")


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
# BED 80 IS THE DEFAULT EVERYWHERE — Oleg, 2026-07-28 ~22:00: "lets also set our default
# print temp to 80 eveywhere." Supersedes the 120-max doctrine (07-26 "PLA maxed to the plate
# ceiling") after a night of first-layer trouble: at 120 a single-layer floor sits above Tg
# indefinitely and never sets. The full-target wait rule (bed_start = bed-5) still applies.
BED_TEMP = {"pla": 60, "pla-matte": 60, "petg": 70, "tpu": 45, "abs": 100}   # PLA 60: filament rated 50-70; 80 was above range + wasted solar (Oleg 2026-07-30)

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
# TPU_FLOW is declared here but SUSTAINED_FLOW_BY_MATERIAL needs it 470 lines earlier, so that
# table carries the literal. Two copies of a number drift; this refuses to import if they do.
assert SUSTAINED_FLOW_BY_MATERIAL["tpu"] == TPU_FLOW, (
    f'tpu flow disagrees between the tables: {SUSTAINED_FLOW_BY_MATERIAL["tpu"]} vs {TPU_FLOW}')
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
# pla-matte's 60 has real provenance — the only entry here that does:
#   55-65 burst ramp at 230C (2.3 min, 57.4 mm3/s mean delivered): SILENT. Oleg: "test was perfecrt".
#   70-90 identical conditions: the extruder CRACKED, by ear, firmware reporting zero stalls.
#   65 on a real multi-minute part: occasional slipping, by ear again — Oleg: "k2 crack
#          ocasionally lets reduce flow by 5". Hence 60, not the 65 the burst ramp allowed.
# A burst figure is not a working figure. Kept in step with SUSTAINED_FLOW_BY_MATERIAL (which
# holds the same 60 with the full story) — two tables disagreeing about the same filament is
# how a stale number survives, and the first version of THIS comment still said 65.
MATERIAL_FLOW = {"pla": FLOW, "pla-matte": 60.0, "petg": 40.0, "tpu": TPU_FLOW, "abs": 30.0}


def check_spool(printer, material):
    """A part generated for one printer with another printer's filament is silently wrong: right
    geometry, wrong temperature, wrong flow ceiling. Say so loudly rather than emit it quietly."""
    want = LOADED.get(printer)
    if want and material != want:
        print(f"  !! {printer} has {want} loaded, but this part is being generated for {material}. "
              f"Either load {material}, or drop --material and let it follow the printer.")
    return material


def decimate(pts, min_seg=0.02):
    """Drop points closer than `min_seg` to the last kept point.

    WHY THIS EXISTS. Curvature-adaptive sampling emits runs of points a few microns apart. XY are
    written to 0.001mm but E to 0.00001mm, so a segment shorter than the XY rounding grid has its
    length quantised away while its extrusion survives intact -- and the IMPLIED flow explodes.
    Measured on a 120mm N=5 nucleon: 1240 of 12240 extruding moves (10.1%) were under 0.01mm,
    contributing 4.08mm of path in total, and 421 of them implied over 65 mm3/s. One asked for
    115 mm3/s, which validate.py correctly refused.

    The moves are not wrong about material -- E per mm of real path is right -- but the printer
    executes what is written, and a 0.001mm move carrying a full segment's extrusion is a
    discontinuity the firmware has to absorb.

    min_seg is 0.02mm: 20x the XY rounding grid, and ~1% of a 2.17mm bead, so the path cannot
    move visibly. Endpoints are always kept so a closed loop stays closed.
    """
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for p in pts[1:-1]:
        if (p[0] - out[-1][0]) ** 2 + (p[1] - out[-1][1]) ** 2 >= min_seg * min_seg:
            out.append(p)
    # CLOSING THE LOOP WITHOUT RE-CREATING THE DEFECT. Appending the final point unconditionally
    # makes a micro-segment whenever it lands within min_seg of the last kept point -- which is
    # exactly the artifact this function removes, reintroduced once per closed loop. Measured: it
    # left 40 such moves in a 40-layer nucleon, one of which implied 68.9 mm3/s against a 65 cap.
    # If the endpoint is too close, MOVE the last kept point onto it instead of adding one.
    if (pts[-1][0] - out[-1][0]) ** 2 + (pts[-1][1] - out[-1][1]) ** 2 < min_seg * min_seg:
        if len(out) > 1:
            out[-1] = pts[-1]
        else:
            out.append(pts[-1])
    else:
        out.append(pts[-1])
    return out


def speed_for_flow(flow, bead_w, layer_h):
    """The one speed this print runs at: as close to the north star as the flow allows.

    Oleg: "50 is north star default unless overruled by other constraints." A fat bead or a
    low-flow material pushes it DOWN -- that is the wide-bead trick working as intended, not a
    violation. Never above DEFAULT_SPEED.
    """
    return min(DEFAULT_SPEED, flow / max(bead_w * layer_h, 1e-9))

# ---------------------------------------------------------------- SLICER TRUTH
# READ OFF HIS ACTUAL SLICER, 2026-08-04, not assumed. Every K2 Plus 0.8-nozzle process profile in
# Creality Print 7.0 carries the SAME line width:
#
#   ~/Library/Application Support/Creality/Creality Print/7.0/system/Creality/process/
#     0.24mm / 0.32mm / 0.40mm / 0.40mm Strength / 0.48mm / 0.56mm  @Creality K2 Plus 0.8 nozzle
#     line_width = 0.82   initial_layer_line_width = 0.82   initial_layer_print_height = 0.40
#
# WHY THIS CONSTANT EXISTS AT ALL. A cage generated with 0.80 mm walls sliced to NOTHING: Creality
# refused it with "One object has empty initial layer and can't be printed". 0.80 is under 0.82, so
# not one feature in the part could hold a single extrusion and the slicer discarded all of it. The
# first layer was merely where it noticed. qa_stl had passed that same file green on every check it
# owns, because none of them knew what the MACHINE can lay down.
#
# THE RULE: NO FEATURE MAY BE THINNER THAN ONE LINE. A wall at exactly SLICER_LINE_W is filled by
# exactly one line with nothing left over, which is the cheapest printable wall that exists.
SLICER_LINE_W = 0.82    # mm, READ from all six K2 Plus 0.8 process profiles, 2026-08-04
SLICER_FIRST_H = 0.40   # mm, initial_layer_print_height, same six profiles
# THE LAYER HEIGHTS HIS SIX K2 PLUS 0.8 PROFILES ACTUALLY OFFER, as a list rather than a sentence.
# It was a comment until 2026-08-07, which meant a generator taking a layer height had nothing to
# check against and would happily lay a height this machine has never been asked for. A height
# outside this set is not "unproven", it is unoffered: no profile on the machine produces it, so
# nothing about the bead geometry, the flow figures or the first-layer numbers was measured there.
SLICER_LAYER_HEIGHTS = (0.24, 0.32, 0.40, 0.48, 0.56)
SLICER_LAYER_H = 0.24   # mm, Oleg 2026-08-04 "yea i meant 0.24 update it", matching the stock
                        # 0.24mm Standard profile. He first said 0.28; when told 0.28 was not among
                        # the stock heights he moved to the profile's own number rather than
                        # hand-setting one, so every constant here now comes off his machine.
