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
FIRST_LAYER_SPEED = 20.0  # mm/s CEILING for layer 1 — never a target. It must be applied as
                          # LOWERED 50 -> 20 on 2026-07-26. Oleg: "k2 adhesion broke you moving head
                          # too fast". Layer 1 was running 55 mm/s with a 10mm-wide bead. The wider
                          # the first bead, the more time the plastic needs to spread and wet the
                          # plate — and a 10mm bead from a 0.8mm nozzle is an extreme spread.
                          # THE KEY POINT, ALREADY WRITTEN BELOW AND IGNORED FOR A DAY: slowing does
                          # NOT thin the line. E is metered per mm of PATH, so at 20 mm/s the bead
                          # is still 10.0 x 0.1mm — identical material, laid with four times the
                          # dwell. Only the RATE (mm3/s) falls, and the rate is not what bonds.
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
MAX_SPEED = 60.0
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
SUSTAINED_FLOW = 27.0      # mm3/s the extruder holds INDEFINITELY. Measured as "did not stall",
                           # which is a floor on the true value, not the value itself.
SUSTAINED_MINS = 8.0       # unbroken extrusion beyond this is a soak, not a burst. The observed
                           # stall came at 16 min; half that is the margin, not a second reading.


def flow_for_duration(flow, minutes, label=""):
    """Clamp a flow to what the extruder can hold for `minutes` of UNBROKEN extrusion.

    Oleg's rule is "always max flow" and this does not weaken it — it measures `max` correctly.
    The ceiling is a function of how long you hold it, and every number this project had was taken
    from a burst. A generator that knows its own print time must ask this before emitting.
    """
    if minutes >= SUSTAINED_MINS and flow > SUSTAINED_FLOW:
        print(f"  ! flow {flow:g} mm3/s for {minutes:.0f} min of unbroken extrusion{label} — the "
              f"K2 extruder driver over-heated and stalled at 48.6 mm3/s after 16 min (2026-07-26). "
              f"Using {SUSTAINED_FLOW:g}. Deposit per mm is unchanged; only the clock moves.")
        return SUSTAINED_FLOW
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
    if requested > cap + 1e-9:
        print(f"  ! flow {requested:g} mm3/s is a {'PLA' if abs(requested-FLOW) < 1e-6 else 'carried-over'} "
              f"number on {material}{label} — its measured ceiling is {cap:g}. Using {cap:g}. "
              f"{'TPU jams the extruder within a minute above this.' if material == 'tpu' else ''}")
        return cap
    return requested


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
BED_TEMP = {"pla": 120, "petg": 80, "tpu": 45, "abs": 100}

# PART-COOLING FAN CEILING, PER MATERIAL. Oleg, 2026-07-26: "fans for printing pla should be only on
# 20% at most". Running 80% on PLA — which this project had been doing on 320mm plates — chills the
# bead as it lands, and on layer 1 it chills the bond while it is still forming. It is the cheapest
# possible way to lose adhesion and it looks like nothing in the file.
# TPU is the exception and goes the other way: it needs FULL fans (see the guard in validate.py).
FAN_MAX = {"pla": 0.20, "petg": 0.40, "tpu": 1.00, "abs": 0.10}
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
MATERIAL_TEMP = {"pla": TEMP, "petg": 240, "tpu": TPU_TEMP, "abs": 250}
MATERIAL_FLOW = {"pla": FLOW, "petg": 40.0, "tpu": TPU_FLOW, "abs": 30.0}
