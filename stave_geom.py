#!/usr/bin/env python3
"""STAVE build-spec arithmetic. Every number here is CALCULATED from the brief's givens or
MEASURED from an emitted file elsewhere; nothing is assumed silently."""
import math

# ---- GIVENS (from the brief / measured elsewhere) ----
ROD_D   = 6.35      # mm, GIVEN (1/4")
ROD_L   = 610.0     # mm, GIVEN (24")
E       = 15000.0   # MPa, GIVEN as mid-band (brief says E varies ~2x)
R_BREAK = 318.0     # mm, GIVEN
I_ROD   = math.pi * ROD_D**4 / 64.0

print(f"I_rod = {I_ROD:.2f} mm4   EI = {E*I_ROD/1000:.0f} N.m.mm -> {E*I_ROD:.3e} N.mm2")

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
    M    = E * I_ROD / R / 1000.0        # N.m
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
    need = ROD_D/math.cos(ph) + T_PLATE*math.tan(ph)
    print(f"\nplate bore: rod at {p} deg through a {T_PLATE}mm plate needs "
          f"{need:.2f}mm clear; STICK_FIT bore = {ROD_D+0.70:.2f}mm modelled "
          f"(~{ROD_D+0.70-0.25:.2f} printed) -> {'OK' if ROD_D+0.70-0.25 > need else 'TOO TIGHT'}")

# ---- PIN: net second moment with a transverse hole on the neutral axis ----
def I_net(d_hole, n=20001):
    """I about the bending axis after drilling a hole of dia d_hole THROUGH the rod,
    hole axis perpendicular to the bending plane (i.e. on the neutral axis).
    Removed strip: |x| <= a within the circle, integrated x^2 dA."""
    Rr, a = ROD_D/2, d_hole/2
    tot = 0.0
    for i in range(n):
        x = -a + 2*a*(i+0.5)/n
        tot += x*x * 2*math.sqrt(max(Rr*Rr - x*x, 0)) * (2*a/n)
    return I_ROD - tot, tot

print(f"\nPIN HOLE (drilled TANGENTIALLY, hole axis on the neutral axis):")
print(f"{'dia':>5} {'I_net':>8} {'% kept':>8} {'sigma MPa':>10}")
for dh in (2.0, 2.5, 3.0):
    Inet, rem = I_net(dh)
    sig = MOM*1000*(ROD_D/2)/Inet
    print(f"{dh:>5} {Inet:>8.2f} {100*Inet/I_ROD:>7.1f}% {sig:>10.1f}")
sig0 = MOM*1000*(ROD_D/2)/I_ROD
print(f"  undrilled sigma = {sig0:.1f} MPa; bamboo bending strength 100-150 MPa (LITERATURE)")

# ---- SHELF LOAD ON PINS ----
for kg in (2, 3, 5):
    P = kg*9.81
    per = P/4
    print(f"  {kg}kg shelf -> {per:.1f} N per pin; 2mm bamboo pin double shear "
          f"{per/(2*math.pi*1.0**2):.2f} MPa; bearing on rod {per/(2.0*ROD_D):.2f} MPa")

# ---- OBLIQUE BORE NARROWING ----
print(f"\nOBLIQUE BORE: a round section swept along a {THETA} deg axis is narrower by "
      f"cos = {math.cos(math.radians(THETA)):.4f} across the tilt.")
print(f"  a nominal 7.05mm modelled bore becomes {7.05*math.cos(math.radians(THETA)):.3f}mm "
      f"normal to the rod = {7.05-7.05*math.cos(math.radians(THETA)):.3f}mm tighter")
