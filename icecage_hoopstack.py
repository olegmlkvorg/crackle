#!/usr/bin/env python3
"""Stacked-hoop ice cage: measure path length off the real geometry, emit STL.

Every constant here states where it came from. Nothing is invented and labelled measured.
"""
import math, sys
import numpy as np
import trimesh

# ---- fixed by the brief (common case, so the four topologies compare) ----
ID     = 250.0          # mm inner diameter        BRIEF
H      = 300.0          # mm height                BRIEF
W      = 0.8            # mm wall = one extrusion  OLEG ("single line 0.8 line width everywhere")
RHO    = 1.24e-3        # g/mm3 PLA                BRIEF (1.24 g/cm3)

# ---- machine, read from ~/dev/crackle/machine.py ----
NOZZLE = 0.8            # machine.py:29
BEAD_W_REPO = 1.2       # machine.py:40  <-- MISMATCH with Oleg's 0.8, reported not substituted
BEAD_H_REPO = 0.6       # machine.py:41
SPEED  = 50.0           # machine.py:101 DEFAULT_SPEED

# ---- chosen by this design ----
LH   = 0.4      # layer height. CHOSEN: bead aspect W/H = 0.8/0.4 = 2.0. At the repo's 0.6 a
                # 0.8-wide bead is 1.33:1, nearly square, minimal interlayer footprint -- and
                # the band's Z bonds are exactly what the bulge mode attacks. NOT measured.
HB   = 2.0      # hoop band height = 5 layers. Set by wanting a band that is a beam in its own
                # right against out-of-plane bulge, not a single ribbon.
P    = 6.0      # band pitch. Set by the WINDOW, not by efficiency (see report).
NRIB = 24       # vertical ties.
LRIB = 10.0     # mm arc length of each tie at the wall centreline.

rc   = (ID + W) / 2.0                 # wall centreline radius = 125.4
C    = 2 * math.pi * rc               # centreline circumference
nlay = int(round(H / LH))
nband = int(round(H / P))
band_layers = int(round(HB / LH))
gap_layers  = nlay - nband * band_layers

hoop_len = nband * band_layers * C
rib_len  = gap_layers * NRIB * LRIB
cyl_len  = hoop_len + rib_len
area     = W * LH                      # mm2 per mm of path
cyl_vol  = cyl_len * area
cyl_g    = cyl_vol * RHO

# base grid, reported separately
BP = 12.0                              # base grid pitch
BL = 3                                 # base layers
R  = ID / 2
base_par = math.pi * R * R / BP         # total chord length of parallel lines at pitch BP
base_len = BL * (2 * base_par + C)
base_g   = base_len * area * RHO

# ---- capacity ----
SIGMA = 45.0    # MPa. CLAIM from literature for printed PLA along the extrusion direction
                # (bulk PLA 50-60 MPa; XY printed typically 40-50). NOT MEASURED HERE.
t_eff = W * (HB / P)                   # smeared wall thickness carrying hoop tension
P_hoop = SIGMA * t_eff / rc            # MPa, thin-wall hoop: p = sigma*t/r
P_solid = SIGMA * W / rc               # same wall with no windows, for reference
t_need_5MPa = 5.0 * rc / SIGMA         # wall needed to hold ice's ~5 MPa compressive strength

print(f"layers {nlay}  bands {nband}  band_layers {band_layers}  gap_layers {gap_layers}")
print(f"C {C:.2f} mm   open fraction of wall height {1-HB/P:.3f}")
print(f"hoop path {hoop_len:.0f} mm   rib path {rib_len:.0f} mm   cyl {cyl_len:.0f} mm")
print(f"hoop share of cyl material {hoop_len/cyl_len*100:.1f}%")
print(f"cyl vol {cyl_vol:.0f} mm3 = {cyl_vol/1000:.1f} cm3   MASS {cyl_g:.1f} g")
print(f"base path {base_len:.0f} mm  MASS {base_g:.1f} g   TOTAL {cyl_g+base_g:.1f} g")
print(f"t_eff {t_eff:.4f} mm  P_hoop {P_hoop:.4f} MPa = {P_hoop*1000:.1f} kPa")
print(f"P_solid(0.8 wall, no windows) {P_solid*1000:.1f} kPa")
print(f"wall needed for 5 MPa ice: {t_need_5MPa:.1f} mm")
print(f"FOM grams per kPa of hoop capacity (cyl only): {cyl_g/(P_hoop*1000):.3f} g/kPa")
print(f"FOM for the same 0.8 wall with NO windows: "
      f"{(nlay*C*area*RHO)/(P_solid*1000):.3f} g/kPa   mass {nlay*C*area*RHO:.1f} g")
print(f"print time at {SPEED} mm/s, cyl+base: {(cyl_len+base_len)/SPEED/3600:.2f} h")
print(f"flow at {SPEED} mm/s with {W}x{LH} bead: {area*SPEED:.2f} mm3/s "
      f"(machine.py FLOW cap 55.0)")

# ---- STL ----
if "--stl" in sys.argv:
    ri, ro = ID / 2, ID / 2 + W
    parts = []
    for i in range(nband):
        z = i * P
        parts.append(trimesh.creation.annulus(r_min=ri, r_max=ro, height=HB,
                                              sections=512,
                                              transform=trimesh.transformations.
                                              translation_matrix([0, 0, z + HB / 2])))
    dth = LRIB / rc
    for k in range(NRIB):
        th = 2 * math.pi * k / NRIB
        n = 16
        a = np.linspace(th - dth / 2, th + dth / 2, n)
        outer = np.stack([ro * np.cos(a), ro * np.sin(a)], 1)
        inner = np.stack([ri * np.cos(a[::-1]), ri * np.sin(a[::-1])], 1)
        poly = np.vstack([outer, inner])
        parts.append(trimesh.creation.extrude_polygon(
            __import__("shapely.geometry", fromlist=["Polygon"]).Polygon(poly), height=H))
    m = trimesh.boolean.union(parts)
    m.export("/Users/olegmalkov/dev/crackle/icecage_hoopstack.stl")
    print(f"STL watertight={m.is_watertight} vol={m.volume:.0f} mm3 "
          f"({m.volume*RHO:.1f} g solid-equivalent) tris={len(m.faces)}")
