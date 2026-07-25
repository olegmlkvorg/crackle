"""Measured machine facts. Single source of truth — nothing hardcodes these numbers separately.

Oleg, 2026-07-25: "you should be extruding at max speed we know nozzle can flow. that is not
negotiable. 100% of the time."
"""
MAX_FLOW = 81.2        # mm3/s, MEASURED (spiral ramp, first skips at 81.2 @ r137, 0.8 nozzle, PLA 230C)
FLOW = 80.0            # what to actually run: the highest flow observed still laying solid.
                       # 81.2 is where skipping STARTS, so commanding exactly 81.2 guarantees a
                       # marginal extruder. 80 is max-known-good, not a safety discount.
NOZZLE = 0.8
MAX_VELOCITY = 800.0
MAX_ACCEL = 30000.0
MAX_Z_V = 30.0
MAX_Z_A = 1000.0
BED_MAX = 120.0        # config claims 135; the machine silently clamps to 120
