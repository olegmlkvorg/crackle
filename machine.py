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
FIRST_LAYER_SPEED = 50.0  # mm/s CEILING for layer 1 — never a target. It must be applied as
                          # min(FIRST_LAYER_SPEED, body_speed), because when the body runs SLOWER
                          # than 50 this becomes a speed-UP: on 2026-07-25 a 2.40mm2 bead with a
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
MAX_SPEED = 30.0
MAX_MOVES_PER_SEC = 300.0  # above this Klipper drains its lookahead and the head stalls; measured
                           # 2026-07-25 as a ~3s stutter at 990 moves/s
MAX_Z_V = 30.0
MAX_Z_A = 1000.0
BED_MAX = 120.0        # config claims 135; the machine silently clamps to 120

# ---------------------------------------------------------------------------------------------
# NO TRAVEL IS A RULE. Oleg, 2026-07-25: "always our prints are continuous extrusion. no travel
# is a rule."
#
# Every generator must emit ZERO non-extruding moves between the first extrusion and the last.
# Two G0 moves are permitted and only two: one to reach the prime start BEFORE any plastic exists,
# and one to park AFTER the object is complete. Removing either would drag a stray line across the
# plate, which is worse than the thing the rule prevents.
#
# How to satisfy it:
#   · the prime line must END exactly where the object BEGINS — no reposition between them
#   · layer changes are Z-only moves; never reposition in XY at a layer change (use vase mode,
#     where Z rises continuously and there is no layer change at all)
#   · the end-of-print lift is Z-only, and the park comes after it
#
# Audit any file with:
#   G0 lines between the first and last "G1 ... E" must be zero.
# ---------------------------------------------------------------------------------------------
NO_TRAVEL_RULE = True

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
BED_TEMP = {"pla": 60, "petg": 80, "tpu": 45, "abs": 100}


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
