#!/usr/bin/env python3
"""STAVE build-spec arithmetic. Every number here is CALCULATED from the brief's givens or
MEASURED from an emitted file elsewhere; nothing is assumed silently.

CORRECTED 2026-08-04 -- THE ROD DIAMETER WAS A NOMINAL WEARING A MEASUREMENT'S LABEL. This file
opened with `ROD_D = 6.35  # mm, GIVEN (1/4")` and spent it on I = pi d^4 / 64. Oleg calipered the
actual sticks on 2026-08-02: they are O5.8-6.2, variable per stick (bamboo/rod_constants.py). d^4
turns that into a 25% error at 6.0 and a 44% error at 5.8, and it was never one-directional, which
is why a single "conservative" substitute would have been the same mistake again:

    quantity                          worst stick   6.35 nominal was
    socket couple F_SOCK, bend moment  FATTEST      CONSERVATIVE (over-states the load)
    pin bending stress (= E d / 2R)    FATTEST      CONSERVATIVE
    plate bore clearance needed        FATTEST      CONSERVATIVE
    pin-hole fraction of I removed     THINNEST     OPTIMISTIC  (under-states the loss)
    bearing on the rod at a pin        THINNEST     OPTIMISTIC

So there is no single ROD_D any more. Each question is asked at the stick that governs IT.

NOT RE-MEASURED: every FORCE and STRESS figure this file prints has moved, and anything already
published from the old run (guides, page copy) is stale until it is re-read off this output. The
BARREL GEOMETRY has NOT moved -- R, bow, chord, arc, burial, the shelf stations and the barrel
radii are functions of ROD_LEN, H_S and THETA only, and none of those changed. No part was
re-emitted and no coupon was re-printed for this edit."""
import math, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bamboo"))
import rod_constants as RC          # THE rod truth. Never retyped.
import solid                        # for STICK_BORE, the stave kit's approved 7.05 plate bore

# ---- GIVENS ----
# Rod diameters MEASURED with calipers by Oleg, 2026-08-02 (rod_constants). Used per-question:
ROD_THIN = RC.ROD_MIN   # governs: pin-hole loss, bearing on the rod
ROD_FAT  = RC.ROD_MAX   # governs: developed moment, socket couple, bore clearance
ROD_L    = RC.ROD_LEN   # mm, the 24in stock length
E        = 15000.0      # MPa, GIVEN as mid-band (brief says E varies ~2x) -- NOT measured on our
                        # bamboo; a 2x band on E swamps the diameter correction below
R_BREAK  = 318.0        # mm, GIVEN
I_THIN   = math.pi * ROD_THIN**4 / 64.0
I_FAT    = math.pi * ROD_FAT**4 / 64.0

print(f"rods MEASURE O{ROD_THIN:g}-{ROD_FAT:g} (calipers 2026-08-02), NOT the 6.35 nominal")
print(f"I_rod = {I_THIN:.2f} mm4 (thin) .. {I_FAT:.2f} mm4 (fat), a {I_FAT/I_THIN:.2f}x spread")
print(f"EI = {E*I_FAT/1000:.0f} N.m.mm -> {E*I_FAT:.3e} N.mm2   (fat stick, the load case)")

# ---- SOCKET DEPTH & FREE ARC ----
# BURIAL, the correction the judge said CINCH and SAIL both skipped. The socket's VERTICAL EXTENT
# is what we print (H_S mm = H_S/0.4 layers); the rod buried in it is longer, because the bore is
# tilted: burial = H_S / cos(theta). Free arc = 610 - 2*burial, and theta depends on the free arc,
# so it has to be solved, not stated.
FLOOR   = 2.4       # mm, solid floor the rod bottoms on
H_S     = 40.0      # mm, CHOSEN socket VERTICAL extent (100 layers)

def barrel(theta_deg):
    th   = math.radians(theta_deg)
    bury = H_S / math.cos(th)
    A    = ROD_L - 2*bury
    R    = A / (2*th)
    s    = R * (1 - math.cos(th))        # sagitta (radial swell)
    L    = 2 * R * math.sin(th)          # chord
    M    = E * I_FAT / R / 1000.0        # N.m -- the FAT stick develops the most moment
    return R, s, L, M, A, bury

print(f"\nsocket vertical extent {H_S}mm -> burial {H_S/math.cos(math.radians(14)):.2f}mm at 14 deg")

print(f"\n{'theta':>6} {'arc':>7} {'R mm':>8} {'bow mm':>8} {'chord':>8} {'R/318':>7} {'M N.m':>7} "
      f"{'F N':>7}")
for t in (10, 12, 13, 14, 15, 16, 18):
    R, s, L, M, A, b = barrel(t)
    print(f"{t:>6} {A:>7.1f} {R:>8.0f} {s:>8.1f} {L:>8.1f} {R/R_BREAK:>7.2f} {M:>7.3f} "
          f"{M*1000/b:>7.1f}")

THETA = 14.0
R, BOW, CHORD, MOM, ARC, BURY = barrel(THETA)
F_SOCK = MOM*1000/BURY
print(f"\nCHOSEN theta={THETA} deg: R={R:.1f} ({R/R_BREAK:.2f}x break), bow={BOW:.1f}mm, "
      f"chord={CHORD:.1f}mm, M={MOM:.3f} N.m, socket couple={F_SOCK:.1f} N")

print(f"  free arc {ARC:.2f}mm, burial {BURY:.2f}mm per end")
WALK = H_S * math.tan(math.radians(THETA))
print(f"socket bore walk over {H_S}mm of vertical extent = {WALK:.2f} mm  "
      f"(step {WALK/(H_S/0.4):.4f} mm/layer = {WALK/(H_S/0.4)/1.2*100:.1f}% of a bead)")

# ---- HEIGHT STACK ----
H_TOT = FLOOR + H_S + CHORD + H_S + FLOOR
print(f"\nheight stack = {FLOOR} floor + {H_S} socket + {CHORD:.1f} chord + {H_S} socket "
      f"+ {FLOOR} roof = {H_TOT:.1f} mm")

# ---- BARREL RADII ----
R_MOUTH = 98.0      # CHOSEN: rod axis radius at the socket mouth
R_FLOORPOS = R_MOUTH - WALK
R_WAIST = R_MOUTH + BOW
Z_MOUTH_LO = FLOOR + H_S
Z_MID = Z_MOUTH_LO + CHORD/2

def at_phi(phi_deg):
    """phi measured from midspan, + = above. returns (z, radius, tangent deg)"""
    ph = math.radians(phi_deg)
    z  = Z_MID + R*math.sin(ph)
    r  = R_WAIST - R*(1 - math.cos(ph))
    return z, r, phi_deg

print(f"\nBARREL: mouth r={R_MOUTH} (x=y={R_MOUTH/math.sqrt(2):.1f}), "
      f"socket-floor r={R_FLOORPOS:.1f} (x=y={R_FLOORPOS/math.sqrt(2):.1f}), "
      f"waist r={R_WAIST:.1f} (x=y={R_WAIST/math.sqrt(2):.1f})")
print(f"  widest silhouette: {2*R_WAIST:.0f} mm across the diagonal, "
      f"{2*R_WAIST/math.sqrt(2)*2/2:.0f}... flats {2*R_WAIST/math.sqrt(2):.0f} mm")
print(f"  z_mouth_lo={Z_MOUTH_LO:.1f}  z_mid={Z_MID:.1f}  z_mouth_hi={Z_MOUTH_LO+CHORD:.1f}")

# ---- SHELF STATIONS ----
print(f"\n{'phi':>6} {'z mm':>8} {'r mm':>8} {'x=y':>7} {'bore sq':>8} {'tan deg':>8}")
for p in (-8, -5.5, -4, 0, 4, 5.5, 8):
    z, r, t = at_phi(p)
    print(f"{p:>6} {z:>8.1f} {r:>8.1f} {r/math.sqrt(2):>7.1f} {2*r/math.sqrt(2):>8.1f} {t:>8.1f}")

PHI_SHELF = 5.5
zA, rA, _ = at_phi(-PHI_SHELF)
zB, rB, _ = at_phi(+PHI_SHELF)
print(f"\nSHELVES at phi=+-{PHI_SHELF}: z={zA:.1f} and {zB:.1f}, both at r={rA:.1f} "
      f"(x=y={rA/math.sqrt(2):.1f}) -> IDENTICAL PART, no handedness in the plate")
print(f"  bays: {zA-Z_MOUTH_LO:.0f} / {zB-zA:.0f} / {Z_MOUTH_LO+CHORD-zB:.0f} mm")

# arc distance from the rod's BOTTOM END to each pin
arcA = BURY + R*math.radians(THETA - PHI_SHELF)
arcB = BURY + R*math.radians(THETA + PHI_SHELF)
print(f"  PIN POSITIONS measured along the rod from its bottom end: "
      f"{arcA:.1f} mm and {arcB:.1f} mm")

# ---- PLATE HOLE SIZE for a rod crossing at phi ----
T_PLATE = 4.8
for p in (5.5,):
    ph = math.radians(p)
    # asked at the FATTEST stick: the bore has to pass the worst rod in the batch, not the average.
    need = ROD_FAT/math.cos(ph) + T_PLATE*math.tan(ph)
    # the bore itself is solid.STICK_BORE, imported. It is the ABSOLUTE 7.05 mm hole Oleg picked off
    # the printed gauge, NOT "rod + 0.70" -- see the pairing note in solid.py. Retyping 0.70 here
    # (which this line used to do) is exactly how the adder gets re-applied to a measured rod.
    # solid.SHRINK is labelled METAL SHAFTS ONLY, and that label is about it being a FIT allowance.
    # It is borrowed here for the other thing it measures: the model->printed hole delta, verified
    # at O6 on the pulley (solid.py). No bamboo fit is taken from it. This line used to retype 0.25.
    printed = solid.STICK_BORE - solid.SHRINK
    print(f"\nplate bore: rod at {p} deg through a {T_PLATE}mm plate needs "
          f"{need:.2f}mm clear; stave bore = {solid.STICK_BORE:.2f}mm modelled "
          f"(~{printed:.2f} printed) -> {'OK' if printed > need else 'TOO TIGHT'}")

# ---- PIN: net second moment with a transverse hole on the neutral axis ----
def I_net(d_hole, n=20001):
    """I about the bending axis after drilling a hole of dia d_hole THROUGH the rod,
    hole axis perpendicular to the bending plane (i.e. on the neutral axis).
    Removed strip: |x| <= a within the circle, integrated x^2 dA.

    Asked at the THINNEST stick: the same drill takes a bigger share of a thinner rod, so 5.8 is
    the stick that governs how much a pin hole costs."""
    Rr, a = ROD_THIN/2, d_hole/2
    tot = 0.0
    for i in range(n):
        x = -a + 2*a*(i+0.5)/n
        tot += x*x * 2*math.sqrt(max(Rr*Rr - x*x, 0)) * (2*a/n)
    return I_THIN - tot, tot

print(f"\nPIN HOLE (drilled TANGENTIALLY, hole axis on the neutral axis) at the THIN stick "
      f"O{ROD_THIN:g}, carrying the moment the FAT stick develops -- worst section, worst load:")
print(f"{'dia':>5} {'I_net':>8} {'% kept':>8} {'sigma MPa':>10}")
for dh in (2.0, 2.5, 3.0):
    Inet, rem = I_net(dh)
    sig = MOM*1000*(ROD_THIN/2)/Inet
    print(f"{dh:>5} {Inet:>8.2f} {100*Inet/I_THIN:>7.1f}% {sig:>10.1f}")
sig0 = MOM*1000*(ROD_FAT/2)/I_FAT
print(f"  undrilled sigma = {sig0:.1f} MPa at the FAT stick (= E d / 2R, so the fat one is the "
      f"worst); bamboo bending strength 100-150 MPa (LITERATURE, not measured on our bamboo)")

# ---- SHELF LOAD ON PINS ----
# bearing is asked at the THIN stick: the same pin force spreads over less rod.
for kg in (2, 3, 5):
    P = kg*9.81
    per = P/4
    print(f"  {kg}kg shelf -> {per:.1f} N per pin; 2mm bamboo pin double shear "
          f"{per/(2*math.pi*1.0**2):.2f} MPa; bearing on the O{ROD_THIN:g} rod "
          f"{per/(2.0*ROD_THIN):.2f} MPa")

# ---- OBLIQUE BORE NARROWING ----
_B = solid.STICK_BORE
print(f"\nOBLIQUE BORE: a round section swept along a {THETA} deg axis is narrower by "
      f"cos = {math.cos(math.radians(THETA)):.4f} across the tilt.")
print(f"  the {_B:.2f}mm modelled stave bore becomes {_B*math.cos(math.radians(THETA)):.3f}mm "
      f"normal to the rod = {_B-_B*math.cos(math.radians(THETA)):.3f}mm tighter")
