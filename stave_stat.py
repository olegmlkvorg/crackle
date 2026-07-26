#!/usr/bin/env python3
"""STAVE statics: mass budget, centre of gravity, tip angle, shelf stiffness, assembly forces.

MEASURED inputs come from the emitted gcode / the region that emitted it (noted per line).
CALCULATED = derived here. ASSUMED = a material property with no measurement in this project;
each one is flagged and each one has a way to measure it in the ten-minute test.
"""
import math, sys
sys.path.insert(0, "/Users/olegmalkov/dev/crackle")
from shapely.geometry import box, Point
from shapely.ops import unary_union

# ---------- MEASURED off the emitted files ----------
M_BASE, Z_BASE_C = 186.5, 12.07     # g, mm above its own base   (stave_hub.py --report)
M_CROWN, Z_CROWN_C = 167.1, 11.29
M_SHELF = 88.8
V_BALLAST = 497.9                   # cm3 cavity, region-integrated
V_FOAM    = 271.6

# ---------- geometry, CALCULATED in stave_geom.py ----------
H_TOT   = 607.1
Z_SHELF = (200.1, 407.0)
R_WAIST = 124.1                     # r_mouth 92 + bow 32.1
BASE_HALF = 80.0                    # 160mm tray
E_ROD, I_ROD = 15000.0, 79.81
R_ARC   = 1079.5
CHORD   = 522.3

# ---------- ASSUMED densities ----------
RHO_MIX  = 1.85     # g/cm3, gypsum15/sand85 — ASSUMED. WEIGH IT: fill the tray with dry sand,
                    # weigh, that is 85% of the mix mass and it takes two minutes.
RHO_FOAM = 0.025    # g/cm3 cured PU — ASSUMED
RHO_BAM  = 0.70     # g/cm3 bamboo — ASSUMED. WEIGH ONE ROD.

m_ball = V_BALLAST * RHO_MIX
m_foam = V_FOAM * RHO_FOAM
m_rod  = math.pi * 3.175**2 * 610 / 1000.0 * RHO_BAM
print(f"MASS BUDGET")
print(f"  PLA  base {M_BASE:.1f} + crown {M_CROWN:.1f} + 2 shelves {2*M_SHELF:.1f}"
      f" = {M_BASE+M_CROWN+2*M_SHELF:.1f} g   [MEASURED off the gcode]")
print(f"  gypsum15/sand85 {m_ball:.0f} g   [{V_BALLAST:.0f} cm3 MEASURED x {RHO_MIX} ASSUMED]")
print(f"  foam {m_foam:.0f} g, bamboo 4 x {m_rod:.1f} = {4*m_rod:.1f} g  [ASSUMED densities]")
TOT = M_BASE + M_CROWN + 2*M_SHELF + m_ball + m_foam + 4*m_rod
print(f"  ASSEMBLED {TOT:.0f} g")

# ---------- centre of gravity ----------
items = [
    ("base PLA",   M_BASE,  Z_BASE_C),
    ("ballast",    m_ball,  2.4 + 22.0/2),
    ("shelf A",    M_SHELF, Z_SHELF[0]),
    ("shelf B",    M_SHELF, Z_SHELF[1]),
    ("rods",       4*m_rod, H_TOT/2),
    ("crown PLA",  M_CROWN, H_TOT - Z_CROWN_C),
    ("foam",       m_foam,  H_TOT - 2.4 - 12.0/2),
]
cg = sum(m*z for _, m, z in items) / sum(m for _, m, z in items)
print(f"\nCENTRE OF GRAVITY  [CALCULATED]")
for n, m, z in items:
    print(f"  {n:<10} {m:>7.1f} g at z={z:>6.1f}")
print(f"  EMPTY CG = {cg:.1f} mm; tips at atan({BASE_HALF}/{cg:.1f}) = "
      f"{math.degrees(math.atan2(BASE_HALF, cg)):.1f} deg")
print(f"  without the ballast CG would be "
      f"{sum(m*z for n,m,z in items if n!='ballast')/sum(m for n,m,z in items if n!='ballast'):.0f}"
      f" mm -> "
      f"{math.degrees(math.atan2(BASE_HALF, sum(m*z for n,m,z in items if n!='ballast')/sum(m for n,m,z in items if n!='ballast'))):.1f} deg."
      f" The pour is worth the difference.")

print(f"\nTIP ANGLE LOADED  [CALCULATED] — the judge's point: rate it loaded, not empty")
for kg, where, z in ((2, "top shelf", Z_SHELF[1]), (3, "top shelf", Z_SHELF[1]),
                     (2, "crown top", H_TOT), (3, "crown top", H_TOT)):
    M = TOT + kg*1000
    ncg = (cg*TOT + kg*1000*z) / M
    ang = math.degrees(math.atan2(BASE_HALF, ncg))
    push = M/1000*9.81*BASE_HALF/z          # horizontal force at the load height to topple
    print(f"  {kg} kg on the {where:<10} CG {ncg:>5.1f} mm, tips at {ang:>4.1f} deg, "
          f"needs {push:>4.1f} N sideways at that height")

print(f"\n  waist half-width {R_WAIST/math.sqrt(2):.1f} mm vs base half-width {BASE_HALF} "
      f"-> the barrel overhangs its own footprint by {R_WAIST/math.sqrt(2)-BASE_HALF:.1f} mm "
      f"across the flats; on the diagonal the rods sit at {R_WAIST:.1f} vs a "
      f"{BASE_HALF*math.sqrt(2):.1f} mm tray corner, i.e. {R_WAIST-BASE_HALF*math.sqrt(2):+.1f} mm.")

# ---------- shelf stiffness, MEASURED off the shelf region ----------
SIDE, T, BORE_AT, RIB, CELL, PAD, BORE = 190.0, 6.0, 84.24, 4.8, 34.0, 10.0, 7.65
S = SIDE/2
body = box(-S, -S, S, S)
innerb = box(-S+RIB, -S+RIB, S-RIB, S-RIB)
holes = []
n = max(1, int((SIDE-2*RIB)//CELL)); c = (SIDE-2*RIB)/n
for i in range(n):
    for j in range(n):
        x0 = -S+RIB+i*c+RIB/2.0; y0 = -S+RIB+j*c+RIB/2.0
        h = box(x0, y0, x0+c-RIB, y0+c-RIB)
        if innerb.contains(h): holes.append(h)
body = body.difference(unary_union(holes))
body = unary_union([body] + [Point(sx*BORE_AT, sy*BORE_AT).buffer(PAD, 64)
                             for sx in (-1, 1) for sy in (-1, 1)])
body = body.difference(unary_union([Point(sx*BORE_AT, sy*BORE_AT).buffer(BORE/2, 64)
                                    for sx in (-1, 1) for sy in (-1, 1)]))
print(f"\nSHELF SECTION  [MEASURED off the same region that emitted the file]")
print(f"  plate area {body.area/100:.1f} cm2 of a {SIDE*SIDE/100:.0f} cm2 square "
      f"= {100*body.area/SIDE**2:.0f}% solid")
widths = []
for xc in [i*2.0 - 60 for i in range(61)]:
    strip = body.intersection(box(xc-0.5, -S, xc+0.5, S))
    widths.append(strip.area/1.0)
wmin = min(widths)
print(f"  material width across the worst section between the bores: {wmin:.1f} mm "
      f"(mean {sum(widths)/len(widths):.1f})")
E_PLA = 3000.0        # MPa, ASSUMED (literature for printed PLA in-plane)
I_pl = wmin * T**3 / 12.0
span = 2*BORE_AT
d_per_N = span**3 / (48 * E_PLA * I_pl)
print(f"  I = {I_pl:.0f} mm4 over a {span:.0f} mm span -> {d_per_N:.3f} mm/N "
      f"[E_PLA {E_PLA} MPa ASSUMED]")
for kg in (1, 2, 3, 5):
    print(f"    {kg} kg central: {kg*9.81*d_per_N:.2f} mm sag")

# ---------- assembly forces ----------
print(f"\nASSEMBLY FORCES  [CALCULATED]")
k_tip = 3*E_ROD*I_ROD/(CHORD**3)
print(f"  a free rod tip is a {CHORD:.0f} mm cantilever: k = 3EI/L^3 = {k_tip:.4f} N/mm")
# THE TIP TRAVEL IS NOT THE BOW DEPTH. Before the crown goes on, a rod sits in the base socket
# only, so it is STRAIGHT and leaning 14 deg: at the height of the top mouth it is way outboard,
# and that whole distance is what the hand has to close. My first pass used the 32.1mm bow depth
# here and understated the pull by 4x.
Z_MOUTH_LO, R_MOUTH = 42.4, 92.0
free_r = R_MOUTH + (CHORD) * math.tan(math.radians(14.0))
pull = free_r - R_MOUTH
print(f"  before the crown is on, a rod is STRAIGHT at 14 deg, so its tip sits at r={free_r:.0f} mm")
print(f"  each tip must be drawn {pull:.0f} mm inward to enter the crown: "
      f"{k_tip*pull:.2f} N ({k_tip*pull/9.81*1000:.0f} g of pull) — one hand, one rod at a time")
print(f"  all four held at once would be {4*k_tip*pull:.1f} N, but they are seated one by one")
print(f"  each rod's socket couple, held forever: M/burial = "
      f"{E_ROD*I_ROD/R_ARC:.0f} N.mm / {40/math.cos(math.radians(14)):.1f} mm = "
      f"{E_ROD*I_ROD/R_ARC/(40/math.cos(math.radians(14))):.1f} N")
print(f"  the 6mm bell relieves the top of the bore, so over the {40/math.cos(math.radians(14))-6:.1f} mm"
      f" that actually grips it is {E_ROD*I_ROD/R_ARC/(40/math.cos(math.radians(14))-6):.1f} N")
print(f"  bearing that over ~10mm of engaged wall x {6.35} mm rod = "
      f"{E_ROD*I_ROD/R_ARC/(40/math.cos(math.radians(14))-6)/(10*6.35):.2f} MPa "
      f"against PLA's ~50 MPa [LITERATURE]")

# ---------- shelf capture: the barrel itself locates the shelf ----------
BORE_PRINTED, R_SHELF = 7.40, 119.13
slop = (BORE_PRINTED - 6.35)/2
lim = R_SHELF + slop
phi = math.degrees(math.acos(1 - (R_WAIST - lim)/R_ARC))
zlim = 303.6 - R_ARC*math.sin(math.radians(phi))
print(f"\nSHELF CAPTURE  [CALCULATED] — the bow is also the shelf's upper stop")
print(f"  bores sit on r={R_SHELF:.1f}; the rods swell to r={R_WAIST:.1f} at the waist, so a shelf")
print(f"  jams once the rods reach r={lim:.2f} (bore slop {slop:.3f} mm/side). That is phi={phi:.2f} deg,")
print(f"  z={zlim:.1f} — only {zlim-Z_SHELF[0]:.1f} mm above station A. A shelf therefore CANNOT cross")
print(f"  the waist: each one is trapped in its own bay, located to a few mm by the barrel and")
print(f"  carried from below by its pins. It also means both shelves must be threaded on BEFORE")
print(f"  the crown closes, one either side of the waist.")
print(f"\nNO CLOSED VERTICAL LOOP: nothing but the four rods sets the crown's height, so the")
print(f"  mouth-to-mouth distance is whatever the rods want and the axial thrust is ZERO by")
print(f"  construction. Rod-length scatter changes the bow by d(bow)/dL = "
      f"{(1-math.cos(math.radians(14)))/(2*math.radians(14)):.4f} mm per mm — a 5 mm short rod")
print(f"  costs {5*(1-math.cos(math.radians(14)))/(2*math.radians(14)):.2f} mm of bow. It tilts the")
print(f"  crown by {5*math.sin(math.radians(14))/math.radians(14):.1f} mm though, so match the")
print(f"  four rods to +-2 mm and cut from the TOP end after marking the pins from the bottom.")
