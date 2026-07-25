"""Measured machine facts. Single source of truth — nothing hardcodes these numbers separately.

Oleg, 2026-07-25: "you should be extruding at max speed we know nozzle can flow. that is not
negotiable. 100% of the time."
"""
MAX_FLOW = 81.2        # mm3/s, MEASURED (spiral ramp, first skips at 81.2 @ r137, 0.8 nozzle, PLA 230C)
FLOW = 70.0            # CORRECTED 2026-07-25 from audible feedback: Oleg heard the extruder
                       # CRACKING (skipping) at 80 during sustained printing. The spiral ramp put
                       # first visual skips at 81.2, but a ramp only holds each flow for a few
                       # seconds of a single layer — it measures the INSTANTANEOUS ceiling. Sustained
                       # multi-layer printing loads the extruder continuously and reveals a lower
                       # practical ceiling. Trust the ear over the ramp: audible skipping is the
                       # extruder losing grip, and it is upstream of anything visible on the plate.
MEASURED_INSTANT = 81.2  # what the ramp showed; kept for the record, not for use
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
FIRST_LAYER_SPEED = 50.0  # mm/s. Layer 1 only. At 111 the bead has no dwell to wet the plate and
                          # adhesion failed twice (Oleg, 2026-07-25). Deposit per mm of PATH is
                          # unchanged by slowing — E is per mm, not per second — so the first layer
                          # is just as thick, it simply has time to bond. Layer 2+ runs at 111.
MAX_SPEED = 120.0       # headroom above the 111 the bead+flow imply; not itself a target
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
