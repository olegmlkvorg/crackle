#!/usr/bin/env python3
"""rod_constants.py -- THE bamboo rod truth. Every bamboo generator imports THIS; a literal
rod/bore/depth number anywhere else in the kit is a bug.

MEASURED (Oleg, calipers on the actual sticks, 2026-08-02): the rods are NOT the nominal 1/4in
6.35 the v1 kit assumed. They measure O5.8-6.2, variable per stick.

BORE = 7.0 FLAT -- stick to the stick size, no extra. The bore clears the fattest stick (6.2)
by 0.8 and the thinnest (5.8) by 1.2; graded TPU shim rings (shim_ring_stl.py) fill the gap per
stick. The old +0.70 press-fit constant is DEAD in the socket kit: that constant bought
bare-PLA-on-bamboo grip, which the TPU shims now provide better. (The bend guide's O7.65
thread-THROUGH bore survives as SLIDE_BORE: a rod must slide three bores in a row there.)

SOCKET DEPTH IS DERIVED, NOT PICKED -- derive_socket_depth() below. A joint fails by PRYING:
the rod levers in the socket and crushes the PLA at the mouth and at the blind end. The v1 kit's
12 mm sockets sat AT the crush figure; the derived depth (~24 mm) sits at crush/4.
"""
import math

# ---- the sticks (MEASURED, calipers, 2026-08-02) ----
ROD_MIN = 5.8            # thinnest stick in the batch
ROD_MAX = 6.2            # fattest stick in the batch
ROD_NOM = 6.0            # middle of the measured band (bearing width for the depth math)

# ---- the sockets ----
BORE = 7.0               # FLAT socket bore, every joint: ROD_MAX + TPU shim wall, no fit adder
SLIDE_BORE = 7.65        # thread-THROUGH bore (bend guide only): rod slides 3 bores in a row
                         # (stave coupon slide constant 2026-07-27; untouched by the 7.0 move)

# ---- the load case + material (for the depth derivation) ----
ROD_LEN = 610.0          # mm, the 24 in stock length
DESIGN_LOAD_N = 20.0     # N hung on the free end of a full rod = the design abuse case
PLA_CRUSH_MPA = 28.0     # printed-PLA bearing crush. PROVENANCE: handbook-ballpark ASSUMED
                         # value, not measured on our PLA -- it is the figure the v1 12 mm
                         # socket sat AT (the v1 joints creaked; consistent, not proof)
SAFETY = 4.0             # crush / working stress
SHIM_COMPRESS = 0.15     # mm the TPU shim stack is OVERSIZED vs the bore, so it must be squeezed
                         # to enter and that squeeze IS the grip. The comment here used to read
                         # "undersized ... so it squeezes", which is self-contradictory: undersized
                         # rattles. The generator followed the wrong half of that sentence and every
                         # shim came out 0.15 UNDER the bore, gripping nothing. Fixed 2026-08-03.
TPU_WALL_MIN = 0.4       # thinnest printable TPU shim wall (single perimeter)


def derive_socket_depth(load_N=DESIGN_LOAD_N, rod_len=ROD_LEN, bearing_width=ROD_NOM,
                        pla_limit_MPa=PLA_CRUSH_MPA / SAFETY):
    """Socket depth d from the prying math. RETURNS the depth in mm -- nobody types it.

    Cantilever: a rod of length L with end load P puts a moment on the joint
        M = P * L                       = 20 N * 610 mm = 12200 N.mm  (~12 Nm)
    The socket reacts with a prying COUPLE: two opposed bearing patches, one at the mouth,
    one at the blind end, arm ~ d apart:
        F = M / d
    Each patch spreads over the rod's bearing width w and about half the socket depth:
        A = w * d/2
        sigma = F / A = 2*M / (w * d^2)
    Check against v1 (d = 12, w = 6.0):  sigma = 2*12200/(6*144)  = 28.2 MPa  = AT crush.
    Solve for sigma <= limit:
        d = sqrt(2*M / (w * sigma_limit))
          = sqrt(2*12200 / (6.0 * 7.0))  = 24.10 mm   at crush/4 = 7 MPa     (right)
    Depth goes with 1/sqrt(sigma): doubling depth quarters the stress.
    """
    M = load_N * rod_len                                  # N.mm
    return math.sqrt(2.0 * M / (bearing_width * pla_limit_MPa))


if __name__ == "__main__":
    d = derive_socket_depth()
    M = DESIGN_LOAD_N * ROD_LEN
    print("rods MEASURE O%g-%g (nom %g)  |  socket bore O%g FLAT  |  slide bore O%g"
          % (ROD_MIN, ROD_MAX, ROD_NOM, BORE, SLIDE_BORE))
    print("depth derivation: M = %g N x %g mm = %g N.mm; sigma = 2M/(w d^2); "
          "limit = %g/%g = %g MPa" % (DESIGN_LOAD_N, ROD_LEN, M, PLA_CRUSH_MPA, SAFETY,
                                      PLA_CRUSH_MPA / SAFETY))
    print("DERIVED SOCKET DEPTH d = sqrt(2*%g/(%g*%g)) = %.2f mm  "
          "(v1's 12 mm sat at %.1f MPa = crush)"
          % (M, ROD_NOM, PLA_CRUSH_MPA / SAFETY, d, 2 * M / (ROD_NOM * 12.0 ** 2)))
