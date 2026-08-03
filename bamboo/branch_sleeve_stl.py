#!/usr/bin/env python3
"""branch_sleeve_stl.py -- THE FORMABLE BRANCH SLEEVE (Oleg, 2026-08-03).

Oleg's idea, verbatim:
  "i suggest alternative for bending. how about we have flat sleves that we use to bend during
   the sleeve is above 60c and wait until it setles, wne print trivial, angles adjustable?"
  "also this bend me sleves can also host additional socket 90% for holding another bambo stick
   that will be a real lego style game changer"
  "we will cool it while holding bend with violant fan"

WHAT IT IS. A straight printed bar. A blind O7.0 socket in each end on the X axis. A third blind
O7.0 socket in a centre block on the Z axis, pointing straight up out of the print bed. Two
identical necks between the centre block and each end. You print it flat, soak it past the glass
transition, close the two ends with a string windlass until a tape says the angle is right, quench
it with a fan, then push straight rods into the three sockets. The angle is chosen while you are
holding the frame, not at design time, and re-heating flattens it back so it can be set again.

STAGE: NOTHING HERE HAS BEEN PRINTED, HEATED, BENT, QUENCHED OR MEASURED ON A PART. This file
emits meshes and measures those meshes. Every physical claim about heat is a MODEL.

THE GATE THAT THIS PART EXISTS FOR. The deleted three-bore bend guide died because a rod would
not thread it: MEASURED middle-bore offset 1.54 mm against 0.55 mm of total clearance. So the
first check here is rod admission, measured off the EMITTED mesh by ray-free geometric probing of
the mesh's own vertices, at ROD_MAX, with the printers' MEASURED 0.25 mm hole undersize applied.
That check is proven able to fire two ways: against a deliberately tight variant, and against a
rebuild of the dead bend guide's own geometry (--knownbad tight / bendguide).

WHY THE ROD NEVER HAS TO THREAD ANYTHING HERE. Three separate blind sockets, each entered from
its own open face. No rod passes through more than one bore. Nothing is threaded, so the
contradiction that killed the bend guide (threading needs offset <= clearance, imposing a bend
needs offset >= 4x clearance) never arises.

THE ONE DECISION THAT MAKES THE BRANCH WORK. The branch socket points along Z, normal to the bend
plane. An in-plane bend curves lines that run in X or Y; a line along Z is only rotated and
translated, never bowed. So the branch bore is the only bore in the part that cannot bow at any
angle, and it is also the only bore with zero overhang because it opens upward. Checked, not
asserted: gate G2.

CONSTANTS. rod_constants.py is THE truth for rod/bore/depth and is imported, never retyped
(gate G12 scans this source for retyped literals). Kit-standard wall/roof/blind-wall/density come
from bamboo_joints_stl.py by import for the same reason. This file WRITES nothing but its own
STLs; no other file in this directory is touched.

DEVIATION FROM KIT STANDARD, stated with its reason: no cross-pins. The kit puts a O3.0 vertical
pin through every socket at 6.0 from the mouth. Here (a) a vertical pin through an end socket
block intersects the horizontal bore, which needs the pocket machinery that lives inside
bamboo_joints_stl.py and which this file must not touch, and (b) more substantively a pin is a
permanent retainer, and this part's whole claim is that it can be re-heated and re-set, which
means every rod must come out again. Grip is the graded split TPU shim (shim_ring_stl.py), which
rod_constants.py already records as having replaced the press fit as the kit's primary grip.

Usage:
  python3 branch_sleeve_stl.py --selftest              # prove every gate can fire, then stop
  python3 branch_sleeve_stl.py --all                   # selftest, then emit + check the family
  python3 branch_sleeve_stl.py --angle 45              # one blank
  python3 branch_sleeve_stl.py --angle 45 --knownbad tight     # watch G1 fail
  python3 branch_sleeve_stl.py --knownbad bendguide            # watch G1 fail on the dead part
"""
import argparse
import math
import os
import re
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import rod_constants as RC                      # THE rod/bore/depth truth. Never retyped.

try:
    import bamboo_joints_stl as KIT             # kit wall/roof/blind-wall/density truth.
except Exception as _e:                          # noqa: BLE001 -- diagnostic, then stop
    sys.stderr.write(
        "FATAL: cannot import bamboo_joints_stl (the kit standard for WALL_MIN, the teardrop "
        "roof, the blind wall and PLA density): %s\n"
        "This generator refuses to retype those constants as literals, so it stops here.\n" % _e)
    raise SystemExit(2)

# ---------------------------------------------------------------- constants NOT in the kit files
# MEASURED, this project (Creality vase-mode empirics, ~/Desktop/spiral-vase coupons): a printed
# hole comes out about 0.25 mm UNDER the modelled diameter on these machines. The kit deliberately
# does NOT compensate for it in the model (the graded TPU shims absorb the difference), so the
# ADMISSION CHECK must apply it instead: a rod meets a bore 0.25 smaller than the mesh says.
HOLE_SHRINK = 0.25
BED = 340.0                # MEASURED usable bed, K2 Plus / SparkX (printer-fleet note)
PLA_YIELD_MPA = 50.0       # ASSUMED, typical FDM PLA in XY. Not measured on our filament.
FORM_STRAIN_CAP = 0.05     # DESIGN CHOICE, deliberately conservative. Not a material limit.
ALPHA_MM2_S = 0.06         # ASSUMED PLA thermal diffusivity (k 0.13 W/mK, rho 1240, cp 1800)
SOAK_BUDGET_S = 600.0      # DESIGN CHOICE: one kettle-fill in a lidded vessel
E_HOT_MPA = 20.0           # ASSUMED rubbery-plateau modulus above Tg. Order of magnitude only.
KINK_RD = 3.0              # fetched mandrel-free tube rule: bend radius >= 3 x OD
STEP_MM = 1.5              # station spacing away from features (bend fidelity, not geometry)
N_ARC = 49                 # circle samples per 135 deg of the teardrop -> 2.8 deg steps
N_BRANCH = 48              # angular samples over the branch bore half-circle
N_ZSUB = 20                # subdivisions of the branch bore wall in Z. The surface is a ruled
#                            vertical cylinder and is EXACT with 0 subdivisions -- but the probe
#                            below measures emitted VERTICES, and a wall carrying vertices only at
#                            its two ends is invisible to it. Built with N_ZSUB = 0 the branch
#                            socket measured 0 wall points, 0 depth and 0.0000 mm of axis wander,
#                            so G2 (the central claim of the design) PASSED having measured
#                            nothing. G5c now gates probe coverage and --knownbad noprobe rebuilds
#                            that exact defect. Subdividing changes no surface: G10 MASS is the
#                            independent witness that the solid is unchanged.
MEAS_TOL = 1e-4            # relative measurement tolerance on gates a correct part meets EXACTLY.
#                            Set by the float32 STL coordinate floor, not by convenience.
GAP_MM = 2.5               # a-gap that ends a bore. Must exceed the coarsest sample spacing on any
#                            bore wall: STEP_MM 1.5 on the end bores, DEPTH/(N_ZSUB+1) on the
#                            branch. Asserted at import (see _assert_sampling).
FAMILY_DEG = (0.0, 15.0, 30.0, 45.0, 60.0, 90.0, 120.0)

# ---- imported, never retyped ----
BORE = RC.BORE                              # O7.0 flat socket bore
DEPTH = RC.derive_socket_depth()            # DERIVED in rod_constants (prying couple)
ROD_MAX = RC.ROD_MAX                        # fattest MEASURED stick
ROD_MIN = RC.ROD_MIN
WALL_MIN = KIT.WALL_MIN                     # kit minimum wall around every bore
LB = KIT.LB                                 # kit boss length = DEPTH + blind wall
BLIND = LB - DEPTH                          # the kit blind wall, recovered not retyped
APEXF = KIT.APEXF                           # teardrop apex height above bore centre, in radii
ROOF_DEG = KIT.ROOF_DEG
RHO = KIT.PLA_G_PER_MM3


def _assert_sampling():
    """GAP_MM decides where a bore ends. If it were smaller than the wall's own sample spacing the
    depth scan would stop inside the bore and every depth in this file would be wrong, silently."""
    zstep = DEPTH / (N_ZSUB + 1.0)
    if not (GAP_MM > STEP_MM and GAP_MM > zstep):
        raise SystemExit("FATAL: GAP_MM %.2f must exceed both STEP_MM %.2f and the branch wall "
                         "z-step %.3f, or the bore-depth scan stops inside the bore."
                         % (GAP_MM, STEP_MM, zstep))


_assert_sampling()


# ================================================================ derivations
def clearance_diametral():
    """What a rod actually meets, AS PRINTED. The mesh bore is BORE; the printed bore is
    HOLE_SHRINK smaller (MEASURED); the stick is ROD_MAX at its fattest (MEASURED)."""
    return BORE - HOLE_SHRINK - ROD_MAX


def bow_cap():
    """How far a socket bore's axis may bow before it stops taking a straight rod.

    A straight rod in a bowed bore can be centred to split the bow, so the demand on the
    clearance is half the sagitta. Cap the sagitta at HALF the radial clearance, i.e. a quarter
    of the diametral clearance, so the bend may never eat more than a quarter of what the fit has.
    NOTE this corrects the spec, which used the 0.80 mm nominal clearance and so ignored the
    MEASURED 0.25 hole shrink. The honest number is 0.55/4, not 0.80/4."""
    return clearance_diametral() / 4.0


def neck_thickness(w):
    """Neck thickness t, DERIVED twice; the binding route wins.

    ROUTE 1, soak budget. Centre-to-bath time for a slab of half-thickness a is about a^2/alpha.
        t <= 2*sqrt(SOAK_BUDGET_S * ALPHA_MM2_S)

    ROUTE 2, socket-bow gate. Under a pure couple the moment is constant along the part, so
    curvature is M/(EI) and each element's share of the angle goes as its length/I. With socket
    blocks of length LB and second moment I_s, and a neck whose length is set by the forming
    strain cap (L_n = t*theta/(2*FORM_STRAIN_CAP)), the sockets' share of the total angle
    SATURATES as theta grows:
        share_max = (2*LB/I_s) / (L_n/I_n) * theta  ->  (2*LB/I_s) * I_n/(L_n/theta)
                  = (2*LB/I_s) * (h t^3/12) / (t/(2*eps))
                  = LB * h * t^2 * eps / (3 * I_s)
    and that share, spread over the two socket blocks, must keep each socket's sagitta under
    bow_cap():   sagitta = LB^2/(8R), R = LB/(share_max/2)  ->  sagitta = LB*share_max/16
        => share_max <= 16*bow_cap()/LB
    Solve for t."""
    a = 2.0 * math.sqrt(SOAK_BUDGET_S * ALPHA_MM2_S)
    i_s = section_I(w, present_hole=True, c=0.0)
    share_max = 16.0 * bow_cap() / LB
    b = math.sqrt(share_max * 3.0 * i_s / (LB * H_SECTION * FORM_STRAIN_CAP))
    t = min(a, b)
    return math.floor(t * 2.0) / 2.0, a, b        # floor to the 0.5 grid = the margin


def section_I(w, present_hole=False, c=0.0):
    """In-plane second moment of the section about the bend axis (z), for the curvature model.
    The teardrop is treated as its circle: the roof sits at |y| < r*cos45 where its contribution
    to I is small, so this UNDERSTATES the removed material slightly, which understates the
    socket's compliance -- the conservative direction is the other way, so gate G3 measures the
    emitted mesh rather than trusting this."""
    i = H_SECTION * w ** 3 / 12.0
    if present_hole:
        i -= math.pi * (BORE / 2.0) ** 4 / 4.0
    if c > 0.0:
        i -= (H_SECTION - ZFLOOR) * (2.0 * c) ** 3 / 12.0
    return i


H_SECTION = LB           # section height = one kit socket plus its blind floor. DERIVED: the
#                          branch socket is a blind hole along Z, so the part must be exactly as
#                          tall as a kit boss. Uniform over the part -> one prismatic plan view.
ZFLOOR = H_SECTION - DEPTH        # branch socket floor = the kit blind wall
ZBORE = H_SECTION / 2.0           # end-bore axis height: centred, so both rods lie on the
#                                   part's mid-plane and the section is symmetric about them


def block_width():
    """Block width w. DESIGN CHOICE, not derived, and the code prints the trade it was chosen
    from. w drives I_s, which caps t (see neck_thickness), which sets the neck's strength. Full
    kit strength needs w ~ 24 and then a 90 degree blank does not fit a 340 bed. 18.0 is the
    smallest 0.5-grid width whose derived neck still carries a third of the kit's own design
    abuse case; the trade table is printed by --trade."""
    return 18.0


def m_allow(w, t):
    """Allowable bending moment of the neck in the bend plane, at PLA_YIELD_MPA/SAFETY."""
    z = H_SECTION * t * t / 6.0
    return z * PLA_YIELD_MPA / RC.SAFETY


def kit_design_moment():
    return RC.DESIGN_LOAD_N * RC.ROD_LEN


def trade_table():
    rows = []
    ww = 13.0
    while ww <= 26.01:
        t, _a, _b = neck_thickness(ww)
        ln = t * math.radians(90.0) / (2.0 * FORM_STRAIN_CAP)
        total = 2.0 * LB + 4.0 * (ww - t) / 2.0 + ww + ln
        rows.append((ww, t, m_allow(ww, t), m_allow(ww, t) / kit_design_moment(), total))
        ww += 0.5
    return rows


# ================================================================ mesh sink
class Sink:
    def __init__(self):
        self.tris = []
        self.min_cross = float("inf")

    def tri(self, a, b, c):
        # Drop ONLY exact coincidences. A triangle with a repeated vertex contributes its one
        # real edge TWICE, so removing it preserves edge parity; a merely thin triangle does not,
        # which is why near-degenerate slivers are kept and audited by min_cross instead.
        if a == b or b == c or a == c:
            return
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        m = math.sqrt(nx * nx + ny * ny + nz * nz)
        if m < self.min_cross:
            self.min_cross = m
        self.tris.append((a, b, c))

    def quad(self, a0, a1, b1, b0):
        self.tri(a0, a1, b1)
        self.tri(a0, b1, b0)


def ring_merge(outer, hole, centre):
    """Annulus between a star-shaped CCW outer loop and a CW hole loop, both star-shaped about
    `centre`. Ported unchanged in method from bamboo_joints_stl.ring_merge (angle two-pointer)."""
    cx, cy = centre

    def ang(p):
        return math.atan2(p[1] - cy, p[0] - cx)

    def unwrap(loop, ref=None):
        raw = [ang(p) for p in loop]
        if ref is None:
            i0 = min(range(len(loop)), key=lambda i: raw[i])
            base = raw[i0]
        else:
            i0 = min(range(len(loop)), key=lambda i: (raw[i] - ref) % (2 * math.pi))
            base = ref + ((raw[i0] - ref) % (2 * math.pi))
        rot = loop[i0:] + loop[:i0]
        a = [base] + [base + ((ang(p) - base) % (2 * math.pi)) for p in rot[1:]]
        for k in range(1, len(a)):
            if a[k] < a[k - 1]:
                a[k] = a[k - 1]
        return rot, a

    O, Oa = unwrap(outer)
    H, Ha = unwrap(hole[::-1], ref=Oa[0])
    no, nh = len(O), len(H)
    tris = []
    i = j = 0
    end_o = Oa[0] + 2 * math.pi
    end_h = Ha[0] + 2 * math.pi
    while i < no or j < nh:
        na_o = Oa[i + 1] if i + 1 < no else end_o
        na_h = Ha[j + 1] if j + 1 < nh else end_h
        if i < no and (j >= nh or na_o <= na_h):
            tris.append((O[i % no], O[(i + 1) % no], H[j % nh]))
            i += 1
        else:
            tris.append((H[(j + 1) % nh], H[j % nh], O[i % no]))
            j += 1
    return tris


def dedupe(loop):
    out = []
    for p in loop:
        if not out or (abs(p[0] - out[-1][0]) > 1e-12 or abs(p[1] - out[-1][1]) > 1e-12):
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-12 and abs(out[0][1] - out[-1][1]) < 1e-12:
        out.pop()
    return out


# ================================================================ the part
class Part:
    """All geometry of one blank. Nothing here is a magic number: every field traces to an
    import, to a derivation above, or to a stated DESIGN CHOICE."""

    def __init__(self, theta_deg, sab=None):
        sab = sab or {}
        self.sab = sab
        self.theta = math.radians(theta_deg)
        self.theta_deg = theta_deg
        self.h = H_SECTION
        self.w = block_width()
        if "w" in sab:
            self.w = sab["w"]
        self.t, self.t_soak, self.t_bow = neck_thickness(self.w)
        if "t" in sab:
            self.t = sab["t"]
        self.bore_r = (sab.get("bore_d", BORE)) / 2.0
        self.depth = sab.get("depth", DEPTH)
        self.zfloor = self.h - self.depth
        self.zbore = self.h / 2.0
        self.lb = self.depth + BLIND
        self.flare = (self.w - self.t) / 2.0          # per-side step -> nominal 45 deg plan taper
        self.cb = self.w                              # centre block: square in plan
        # neck length from the forming strain cap: eps = t*theta/(2 L_n)
        self.ln = self.t * self.theta / (2.0 * FORM_STRAIN_CAP) * sab.get("neck_scale", 1.0)
        self.split = sab.get("split", 0.5)            # neck length split A/B (0.5 = symmetric)
        self.lna = self.ln * self.split
        self.lnb = self.ln * (1.0 - self.split)
        self.L = 2.0 * self.lb + 4.0 * self.flare + self.cb + self.ln
        self.branch_down = bool(sab.get("branch_down", False))
        self.branch_r = self.bore_r
        self.zsub = 0 if sab.get("no_zsub") else N_ZSUB
        self.branch_bow = float(sab.get("branch_bow", 0.0))
        if sab.get("branch_on_neck"):
            # put the branch bore in the middle of neck A instead of the centre block
            self.branch_x = self.lb + self.flare + self.lna / 2.0
        else:
            self.branch_x = self.lb + 2.0 * self.flare + self.lna + self.cb / 2.0
        self.stations = self._stations()

    # ---- plan width profile ----
    def width(self, x):
        w, t, f = self.w, self.t, self.flare
        x0 = self.lb                       # end of socket block A
        if x <= x0:
            return w
        if x <= x0 + f:                    # flare down
            s = (x - x0) / f
            return t + (w - t) * (0.5 + 0.5 * math.cos(math.pi * s))
        x1 = x0 + f + self.lna
        if x <= x1:
            return t
        if x <= x1 + f:                    # flare up
            s = (x - x1) / f
            return t + (w - t) * (0.5 + 0.5 * math.cos(math.pi * (1.0 - s)))
        x2 = x1 + f + self.cb
        if x <= x2:
            return w
        if x <= x2 + f:                    # flare down (B)
            s = (x - x2) / f
            return t + (w - t) * (0.5 + 0.5 * math.cos(math.pi * s))
        x3 = x2 + f + self.lnb
        if x <= x3:
            return t
        if x <= x3 + f:
            s = (x - x3) / f
            return t + (w - t) * (0.5 + 0.5 * math.cos(math.pi * (1.0 - s)))
        return w

    def hole_on(self, x):
        return x <= self.depth + 1e-9 or x >= self.L - self.depth - 1e-9

    def _stations(self):
        """(x, hole_scale, c, zs) per station. Duplicate x values carry the flat transitions."""
        f, lb, cb = self.flare, self.lb, self.cb
        x1 = lb + f + self.lna
        x2 = x1 + f + cb
        x3 = x2 + f + self.lnb
        keys = sorted(set([0.0, self.depth, lb, lb + f, x1, x1 + f, x2, x2 + f, x3, x3 + f,
                           self.L - self.depth, self.L]))
        xs = []
        for a, b in zip(keys, keys[1:]):
            n = max(1, int(math.ceil((b - a) / STEP_MM)))
            for k in range(n):
                xs.append(a + (b - a) * k / n)
        xs.append(self.L)
        # branch bore stations, uniform in ANGLE so the polygon's inradius error is 0.001 mm
        br, bx = self.branch_r, self.branch_x
        bs = [bx + br * math.cos(math.pi * (1.0 - k / float(N_BRANCH))) for k in range(N_BRANCH + 1)]
        xs = [x for x in xs if not (bs[0] - 1e-9 <= x <= bs[-1] + 1e-9)] + bs
        xs = sorted(xs)
        out = []
        for x in xs:
            s = 1.0 if self.hole_on(x) else 0.0
            inb = bs[0] - 1e-9 <= x <= bs[-1] + 1e-9
            d = abs(x - bx)
            c = math.sqrt(max(0.0, br * br - d * d)) if inb else 0.0
            zs = self.zfloor if inb else self.h
            if self.branch_down:
                zs = self.h - self.zfloor if inb else self.h   # blind from BELOW: known-bad
            out.append([x, s, c, zs])
        # flat transitions: bore floor at x = depth and x = L-depth
        res = []
        for i, st in enumerate(out):
            x, s, c, zs = st
            if abs(x - self.depth) < 1e-9:
                res.append([x, 1.0, c, zs])
                res.append([x, 0.0, c, zs])
                continue
            if abs(x - (self.L - self.depth)) < 1e-9:
                res.append([x, 0.0, c, zs])
                res.append([x, 1.0, c, zs])
                continue
            if abs(x - bs[0]) < 1e-9:
                res.append([x, s, 0.0, self.h])
                res.append([x, s, 0.0, self.zfloor if not self.branch_down
                            else self.h - self.zfloor])
                continue
            if abs(x - bs[-1]) < 1e-9:
                res.append([x, s, 0.0, self.zfloor if not self.branch_down
                            else self.h - self.zfloor])
                res.append([x, s, 0.0, self.h])
                continue
            res.append(st)
        return res

    # ---- section loops ----
    def outer_loop(self, x, c, zs):
        """Plan cross-section in (y, z) at station x. The two vertical runs at y = +-c are the
        branch bore wall; they carry self.zsub intermediate points so the emitted mesh SAMPLES that
        cylinder rather than merely bounding it. The points are collinear, so the surface is
        identical for any zsub -- G10 MASS is the witness. Loop length is 4 + 2*(zsub+2) at EVERY
        station, so the loft stays index-aligned; where c = 0 the added points coincide exactly and
        their triangles are dropped by Sink.tri, which preserves edge parity."""
        w2 = self.width(x) / 2.0
        h = self.h
        n = self.zsub + 1
        # Where the bore has zero width (every station outside it, and its two tangent stations)
        # the run must COLLAPSE to a single repeated point, not subdivide a zero-width slit. A
        # subdivided slit emits collinear triangles: |cross| 0.0 and 80 unpaired edges on the first
        # build with subdivision on. Collapsed, the points coincide exactly and Sink.tri drops
        # their triangles in pairs, which is what keeps edge parity.
        flat = h if not self.branch_down else 0.0
        if c <= 1e-9:
            zs = flat

        def ybow(z):
            """Deliberate bow of the branch bore axis, known-bad only (0.0 in every real build).
            Zero at both the mouth and the floor, maximum at mid-depth, so it moves the AXIS
            without moving the mouth the probe seeds from."""
            if self.branch_bow == 0.0 or self.depth <= 0.0:
                return 0.0
            return self.branch_bow * math.sin(math.pi * abs(h - z) / self.depth)

        def run(y, za, zb):
            out = []
            for k in range(n + 1):
                z = za + (zb - za) * k / n
                out.append((y + ybow(z), z))
            return out

        if self.branch_down:
            # slot open at the BOTTOM instead: the known-bad that must fail qa_stl PRINTABLE
            return ([(-w2, 0.0)] + run(-c, 0.0, zs) + run(c, zs, 0.0)
                    + [(w2, 0.0), (w2, h), (-w2, h)])
        return ([(-w2, 0.0), (w2, 0.0), (w2, h)] + run(c, h, zs) + run(-c, zs, h)
                + [(-w2, h)])

    def teardrop(self):
        """Kit 46 deg teardrop roof, CW in (y, z) about the bore centre -> a hole loop."""
        r = self.bore_r
        pts = []
        for k in range(N_ARC):
            a = math.radians(-90.0 + 135.0 * k / (N_ARC - 1.0))
            pts.append((r * math.cos(a), r * math.sin(a)))
        pts.append((0.0, r * APEXF))
        for k in range(N_ARC):
            a = math.radians(135.0 + 135.0 * k / (N_ARC - 1.0))
            pts.append((r * math.cos(a), r * math.sin(a)))
        pts.pop()                                    # last == first
        return pts[::-1]                             # CCW -> CW

    def hole_loop(self, s):
        if s <= 0.0:
            return [(0.0, self.zbore)] * (2 * N_ARC)
        return [(y, self.zbore + z) for (y, z) in self.teardrop()]


# ================================================================ bend model
def bend_frames(part, theta):
    """Curvature distribution under a PURE COUPLE: M constant along the part, so kappa = M/(EI)
    and every element bends in inverse proportion to its own second moment. The socket blocks are
    stiff but not rigid, so they bow a little -- which is exactly the thing gate G3 measures.
    Returns per-station (origin_x, origin_y, alpha)."""
    st = part.stations
    inv = []
    for x, s, c, zs in st:
        i = section_I(part.width(x), present_hole=(s > 0.0), c=c)
        inv.append(1.0 / i)
    tot = 0.0
    for k in range(len(st) - 1):
        dx = st[k + 1][0] - st[k][0]
        tot += 0.5 * (inv[k] + inv[k + 1]) * dx
    kk = theta / tot if tot > 0 else 0.0
    alpha = [-theta / 2.0]
    for k in range(len(st) - 1):
        dx = st[k + 1][0] - st[k][0]
        alpha.append(alpha[-1] + kk * 0.5 * (inv[k] + inv[k + 1]) * dx)
    ox, oy = [0.0], [0.0]
    for k in range(len(st) - 1):
        dx = st[k + 1][0] - st[k][0]
        am = 0.5 * (alpha[k] + alpha[k + 1])
        ox.append(ox[-1] + dx * math.cos(am))
        oy.append(oy[-1] + dx * math.sin(am))
    return list(zip(ox, oy, alpha))


def make_tf(part, theta):
    if theta == 0.0:
        cx = part.L / 2.0

        def tf(i, y, z):
            return (part.stations[i][0] - cx, y, z)
        return tf
    fr = bend_frames(part, theta)
    cx = 0.5 * (fr[0][0] + fr[-1][0])
    cy = 0.5 * (fr[0][1] + fr[-1][1])

    def tf(i, y, z):
        ox, oy, a = fr[i]
        return (ox - cx - y * math.sin(a), oy - cy + y * math.cos(a), z)
    return tf


# ================================================================ build
def build(part, theta):
    sk = Sink()
    st = part.stations
    tf = make_tf(part, theta)
    outers = [part.outer_loop(x, c, zs) for (x, s, c, zs) in st]
    holes = [part.hole_loop(s) for (x, s, c, zs) in st]
    for k in range(len(st) - 1):
        for la, lb_, rev in ((outers[k], outers[k + 1], False), (holes[k], holes[k + 1], False)):
            n = len(la)
            for i in range(n):
                j = (i + 1) % n
                a0 = tf(k, *la[i]); a1 = tf(k, *la[j])
                b1 = tf(k + 1, *lb_[j]); b0 = tf(k + 1, *lb_[i])
                sk.quad(a0, a1, b1, b0)
    # end caps
    for k, flip in ((0, True), (len(st) - 1, False)):
        o = dedupe(outers[k])
        hl = dedupe(holes[k])
        tris = ring_merge(o, hl, (0.0, part.zbore))
        for a, b, c in tris:
            pa, pb, pc = tf(k, *a), tf(k, *b), tf(k, *c)
            if flip:
                sk.tri(pa, pc, pb)
            else:
                sk.tri(pa, pb, pc)
    return sk


# ================================================================ the dead bend guide (known-bad)
def build_bendguide():
    """A rebuild of the geometry that Oleg could NOT push a stick through: three collinear
    O(SLIDE_BORE) bores, the middle one offset by the MEASURED 1.54 mm, total clearance 0.55.
    This is the strongest known-bad available in the project because it is physically confirmed.
    If the admission probe says a rod threads THIS, the probe is lying."""
    OFFSET = 1.54                       # MEASURED on the printed part, 2026-08-03
    r = RC.SLIDE_BORE / 2.0
    w, h, L = 18.0, 18.0, 120.0
    zc = h / 2.0
    segs = [(0.0, 30.0, 0.0), (45.0, 75.0, OFFSET), (90.0, 120.0, 0.0)]
    keys = sorted({0.0, 30.0, 45.0, 75.0, 90.0, 120.0})
    xs = []
    for a, b in zip(keys, keys[1:]):
        n = max(1, int(math.ceil((b - a) / STEP_MM)))
        for k in range(n):
            xs.append(a + (b - a) * k / n)
    xs.append(L)
    st = []
    for x in xs:
        on, dy = 0.0, 0.0
        for a, b, o in segs:
            if a - 1e-9 <= x <= b + 1e-9:
                on, dy = 1.0, o
        st.append((x, on, dy))
    res = []
    for x, on, dy in st:
        for a, b, o in segs:
            if abs(x - a) < 1e-9 and a > 0.0:
                res.append((x, 0.0, o))
            elif abs(x - b) < 1e-9 and b < L:
                res.append((x, 1.0, o))
        res.append((x, on, dy))
    sk = Sink()
    n_c = 64

    def circle(on, dy):
        if on <= 0.0:
            return [(dy, zc)] * n_c
        return [(dy + r * math.cos(-2 * math.pi * k / n_c),
                 zc + r * math.sin(-2 * math.pi * k / n_c)) for k in range(n_c)]

    def rect():
        return [(-w / 2, 0.0), (w / 2, 0.0), (w / 2, h), (-w / 2, h)]

    for k in range(len(res) - 1):
        xa, oa, da = res[k]
        xb, ob, db = res[k + 1]
        for la, lb_ in ((rect(), rect()), (circle(oa, da), circle(ob, db))):
            n = len(la)
            for i in range(n):
                j = (i + 1) % n
                sk.quad((xa,) + la[i], (xa,) + la[j], (xb,) + lb_[j], (xb,) + lb_[i])
    for k, flip in ((0, True), (len(res) - 1, False)):
        x, on, dy = res[k]
        tris = ring_merge(rect(), circle(on, dy), (dy, zc))
        for a, b, c in tris:
            pa, pb, pc = (x,) + a, (x,) + b, (x,) + c
            sk.tri(pa, pc, pb) if flip else sk.tri(pa, pb, pc)
    return sk


# ================================================================ STL io
def write_stl(path, tris, header):
    hdr = header.encode("ascii", "replace")[:80].ljust(80, b" ")
    with open(path, "wb") as f:
        f.write(hdr)
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            m = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            f.write(struct.pack("<12fH", nx / m, ny / m, nz / m,
                                a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2], 0))


def read_stl(path):
    with open(path, "rb") as f:
        blob = f.read()
    n = struct.unpack("<I", blob[80:84])[0]
    tris = []
    for rec in struct.iter_unpack("<12fH", blob[84:84 + 50 * n]):
        tris.append((rec[3:6], rec[6:9], rec[9:12]))
    return tris


# ================================================================ measurement (mesh only)
def verts_of(tris):
    s = set()
    for t in tris:
        for v in t:
            s.add((round(v[0], 6), round(v[1], 6), round(v[2], 6)))
    return list(s)


def signed_volume(tris):
    v = 0.0
    for a, b, c in tris:
        v += (a[0] * (b[1] * c[2] - b[2] * c[1])
              - a[1] * (b[0] * c[2] - b[2] * c[0])
              + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return v


def edge_parity(tris):
    from collections import Counter
    e = Counter()
    for t in tris:
        vs = [tuple(round(c, 3) for c in v) for v in t]
        for i in range(3):
            a, b = vs[i], vs[(i + 1) % 3]
            e[(a, b) if a <= b else (b, a)] += 1
    return sum(1 for c in e.values() if c != 2), len(e)


def planar_faces(tris):
    """Cluster triangles into planes by (rounded unit normal, rounded plane offset)."""
    cl = {}
    for a, b, c in tris:
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        m = math.sqrt(nx * nx + ny * ny + nz * nz)
        if m < 1e-12:
            continue
        nx, ny, nz = nx / m, ny / m, nz / m
        d = nx * a[0] + ny * a[1] + nz * a[2]
        key = (round(nx, 3), round(ny, 3), round(nz, 3), round(d, 2))
        cen = ((a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0, (a[2] + b[2] + c[2]) / 3.0)
        e = cl.setdefault(key, [0.0, [0.0, 0.0, 0.0], (nx, ny, nz)])
        e[0] += m / 2.0
        for i in range(3):
            e[1][i] += cen[i] * m / 2.0
    out = []
    for key, (ar, cw, n) in cl.items():
        out.append((ar, tuple(c / ar for c in cw), n))
    out.sort(reverse=True, key=lambda r: r[0])
    return out


def end_face_seeds(tris):
    """The two end faces: the largest near-vertical planar clusters whose centroids are farthest
    from the mesh centroid. Pure mesh operation -- no generator knowledge."""
    vs = verts_of(tris)
    gx = sum(v[0] for v in vs) / len(vs)
    gy = sum(v[1] for v in vs) / len(vs)
    gz = sum(v[2] for v in vs) / len(vs)
    cands = [f for f in planar_faces(tris) if abs(f[2][2]) < 0.2 and f[0] > 50.0]
    cands.sort(reverse=True, key=lambda f: math.dist(f[1], (gx, gy, gz)))
    picked = []
    for ar, cen, n in cands:
        if all(math.dist(cen, p[0]) > 20.0 for p in picked):
            picked.append((cen, tuple(-x for x in n)))     # inward = -outward normal
        if len(picked) == 2:
            break
    return picked


def branch_seed(tris):
    """The branch bore mouth: the DENSE cluster of vertices in the top face. The bore's 48-gon
    packs many neighbours inside 4 mm; the plan outline's 1.5 mm stations pack few."""
    vs = verts_of(tris)
    zmax = max(v[2] for v in vs)
    top = [v for v in vs if abs(v[2] - zmax) < 1e-4]
    best = None
    dense = []
    for v in top:
        n = sum(1 for u in top if math.dist((u[0], u[1]), (v[0], v[1])) < 4.0)
        dense.append((n, v))
    mx = max(d[0] for d in dense)
    sel = [v for n, v in dense if n > mx * 0.5]
    cx = sum(v[0] for v in sel) / len(sel)
    cy = sum(v[1] for v in sel) / len(sel)
    best = ((cx, cy, zmax), (0.0, 0.0, -1.0))
    return best


def basis(d):
    d = tuple(d)
    m = math.sqrt(sum(c * c for c in d))
    d = tuple(c / m for c in d)
    a = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0)
    e1 = (d[1] * a[2] - d[2] * a[1], d[2] * a[0] - d[0] * a[2], d[0] * a[1] - d[1] * a[0])
    m = math.sqrt(sum(c * c for c in e1))
    e1 = tuple(c / m for c in e1)
    e2 = (d[1] * e1[2] - d[2] * e1[1], d[2] * e1[0] - d[0] * e1[2], d[0] * e1[1] - d[1] * e1[0])
    return d, e1, e2


def _max_ang_gap(pts2):
    """Largest angular gap, in degrees, between successive points as seen from their own centroid.
    A full bore section reads a few degrees; a one-sided fragment reads well over 180."""
    cx = sum(p[0] for p in pts2) / len(pts2)
    cy = sum(p[1] for p in pts2) / len(pts2)
    ang = sorted(math.atan2(p[1] - cy, p[0] - cx) for p in pts2)
    gap = ang[0] + 2 * math.pi - ang[-1]
    for i in range(len(ang) - 1):
        gap = max(gap, ang[i + 1] - ang[i])
    return math.degrees(gap)


class Socket:
    """One socket, measured entirely off the mesh from a seed (origin on the mouth plane,
    direction into the part)."""

    def __init__(self, tris, seed, tag, through=False):
        """through=True: this bore is THREADED, so it does not end at the first gap. A blind socket
        must stop at its floor or it swallows the opposite socket; a thread-through bore must NOT,
        or the probe measures only the first of the bores a rod has to pass. With the blind rule
        applied to the dead bend guide the probe read +0.600 mm of clearance -- the clearance of
        its FIRST bore alone -- on the part Oleg physically could not push a stick through."""
        self.tag = tag
        self.through = through
        o, d = seed
        self.o0 = o
        d, e1, e2 = basis(d)
        self.d0, self.e1, self.e2 = d, e1, e2
        vs = verts_of(tris)
        self.pts = []
        rej = []
        for v in vs:
            rx, ry, rz = v[0] - o[0], v[1] - o[1], v[2] - o[2]
            a = rx * d[0] + ry * d[1] + rz * d[2]
            u = rx * e1[0] + ry * e1[1] + rz * e1[2]
            w = rx * e2[0] + ry * e2[1] + rz * e2[2]
            r = math.hypot(u, w)
            if a < -0.2:
                continue
            if r <= BORE:
                self.pts.append((a, u, w))
            elif a > 0.2:
                rej.append((a, r))
        # DEPTH BY CONTIGUITY, not by finding the axis point. The old rule (shallowest vertex
        # within 1 mm of the axis) read 0.000 on the branch socket, because a bore whose wall
        # carries no interior vertices has no such vertex to find. This walks the sorted along-axis
        # coordinates from the mouth and stops at the first gap wider than GAP_MM: on a real bore
        # that gap is the solid material past the floor. It also stops before the OPPOSITE end
        # socket, whose bore is collinear with this one and 112 mm away.
        aa = sorted(p[0] for p in self.pts)
        self.depth = 0.0
        if through:
            self.depth = aa[-1] if aa else 0.0
        else:
            for i in range(len(aa) - 1):
                self.depth = aa[i]
                if aa[i + 1] - aa[i] > GAP_MM:
                    break
            else:
                self.depth = aa[-1] if aa else 0.0
        # A socket measures ITS OWN bore and nothing else. The seed cylinder is unbounded along the
        # axis, so without this it also swallows the opposite end socket's bore and any branch-wall
        # vertex that happens to pass within BORE of the extended axis -- which dropped G5b's
        # separation reading from 6.28 to 0.04 mm the moment the branch wall gained vertices.
        lim = self.depth + 0.05
        self.pts = [p for p in self.pts if p[0] <= lim]
        rejected = [r for a, r in rej if a <= lim]
        self.sep = (min(rejected) if rejected else float("inf")) - \
                   max((math.hypot(p[1], p[2]) for p in self.pts), default=0.0)
        self.wall = [p for p in self.pts if 0.5 <= p[0] <= self.depth - 0.5
                     and math.hypot(p[1], p[2]) > 1.0]
        self._bins = None
        self._clear = {}

    # ---- largest inscribed circle in a section bin ----
    def _incircle(self, pts2, seed=(0.0, 0.0)):
        """Largest circle centred inside the bbox of pts2 whose centre is farthest from all of
        them. The CLAMP is not a fudge, it is what makes this terminate: the ascent objective
        min-distance-to-the-cloud grows without bound as the centre walks away from a cloud that
        does not surround it, so on a one-sided bin the unclamped loop never halves its step and
        never returns. It ran for over ten minutes on the first bent mesh before this. The incircle
        centre of a closed contour lies inside that contour's bbox, so clamping to the bbox cannot
        move the true answer, and it makes the domain compact so the step must halve."""
        xs = [q[0] for q in pts2]
        ys = [q[1] for q in pts2]
        lox, hix, loy, hiy = min(xs), max(xs), min(ys), max(ys)

        def f(p):
            return min(math.hypot(q[0] - p[0], q[1] - p[1]) for q in pts2)

        p = (min(max(seed[0], lox), hix), min(max(seed[1], loy), hiy))
        best = f(p)
        step = 1.0
        while step > 0.002:
            moved = False
            for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step),
                           (step, step), (-step, step), (step, -step), (-step, -step)):
                q = (min(max(p[0] + dx, lox), hix), min(max(p[1] + dy, loy), hiy))
                v = f(q)
                if v > best + 1e-12:
                    best, p, moved = v, q, True
            if not moved:
                step *= 0.5
        return p, best

    def bins(self):
        """Bore sections, recovered as the mesh's OWN RINGS -- one closed loop of wall vertices per
        emitted station -- not as slices of an arbitrary grid.

        A fixed grid was the first version and it is wrong on a bent mesh. Each ring is tilted
        relative to the seed axis, so its vertices spread about 0.29 mm in depth; a ring landing on
        a bin edge is split, and the larger fragment still looked plausible (64 points, a 94 degree
        angular gap, just inside the 100 degree guard). The circle fitted to that fragment escaped
        into the missing sector and reported a O8.378 bore and 2.65 mm of axis bow on a part whose
        real bow is 0.10 mm. It failed safe -- G5 caught the impossible diameter -- but it failed
        for a reason that was not in the part.

        Rings are separated in depth by the station pitch (about 1.13 mm of clear gap here) while
        vertices inside one ring sit about 0.003 mm apart, so the split is unambiguous by three
        orders of magnitude. The threshold is taken from the mesh's own median vertex spacing, not
        typed in."""
        if self._bins is not None:
            return self._bins
        pts = sorted(self.wall, key=lambda p: p[0])
        self._bins = []
        if len(pts) < 8:
            return self._bins
        gaps = sorted(pts[i + 1][0] - pts[i][0] for i in range(len(pts) - 1))
        thr = max(20.0 * gaps[len(gaps) // 2], 0.05)
        rings, cur = [], [pts[0]]
        for a, b in zip(pts, pts[1:]):
            if b[0] - a[0] > thr:
                rings.append(cur)
                cur = [b]
            else:
                cur.append(b)
        rings.append(cur)
        pop = sorted(len(r) for r in rings)
        modal = pop[len(pop) // 2]         # the population of a COMPLETE ring, from the mesh
        out = []
        for rg in rings:
            if len(rg) < 8 or len(rg) != modal or _max_ang_gap([(p[1], p[2]) for p in rg]) > 100.0:
                continue                   # a partial ring is not a section; drop it, and let G5c
                #                            fail the part if too few complete rings survive
            c, r = self._incircle([(p[1], p[2]) for p in rg])
            out.append((sum(p[0] for p in rg) / len(rg), c, r, rg))
        self._bins = out
        return out

    def axis_clearance(self, probe_r, refine=True):
        """Best straight cylinder of radius probe_r along ANY straight line. Seeded by the
        least-squares line through the per-bin inscribed centres, then coordinate-descent
        refined. Returns (clearance, axis_point2d, axis_slope2d)."""
        key = round(probe_r, 6)
        if key in self._clear:
            return self._clear[key]
        bs = self.bins()
        if not bs:
            return (-99.0, (0.0, 0.0), (0.0, 0.0))
        n = len(bs)
        sa = sum(b[0] for b in bs)
        saa = sum(b[0] ** 2 for b in bs)
        par = []
        for k in (0, 1):
            su = sum(b[1][k] for b in bs)
            sau = sum(b[0] * b[1][k] for b in bs)
            den = n * saa - sa * sa
            m = (n * sau - sa * su) / den if abs(den) > 1e-12 else 0.0
            c = (su - m * sa) / n
            par.append([c, m])
        p = [par[0][0], par[1][0], par[0][1], par[1][1]]

        def clear(p):
            worst = 1e9
            for a, u, w in self.wall:
                du = u - (p[0] + p[2] * a)
                dw = w - (p[1] + p[3] * a)
                r = math.hypot(du, dw) - probe_r
                if r < worst:
                    worst = r
            return worst

        best = clear(p)
        if refine:
            step = [0.2, 0.2, 0.01, 0.01]
            for _ in range(40):
                moved = False
                for i in range(4):
                    for sgn in (1, -1):
                        q = list(p)
                        q[i] += sgn * step[i]
                        v = clear(q)
                        if v > best + 1e-9:
                            best, p, moved = v, q, True
                if not moved:
                    step = [s * 0.5 for s in step]
                    if max(step) < 1e-4:
                        break
        self._clear[key] = (best, (p[0], p[1]), (p[2], p[3]))
        return self._clear[key]

    def bow(self):
        """Sagitta of the bore axis over the socket length, from the per-bin inscribed centres."""
        bs = self.bins()
        if len(bs) < 3:
            return 0.0, 0.0
        a0, c0 = bs[0][0], bs[0][1]
        a1, c1 = bs[-1][0], bs[-1][1]
        worst = 0.0
        for a, c, _r, _rg in bs:
            tt = (a - a0) / (a1 - a0) if a1 != a0 else 0.0
            lu = c0[0] + (c1[0] - c0[0]) * tt
            lw = c0[1] + (c1[1] - c0[1]) * tt
            worst = max(worst, math.hypot(c[0] - lu, c[1] - lw))
        span = a1 - a0
        rad = span * span / (8.0 * worst) if worst > 1e-9 else float("inf")
        return worst, rad

    def radii(self):
        bs = self.bins()
        return [b[2] for b in bs]

    def roundness(self):
        """Per-bin max-minus-min wall radius about the inscribed centre, over the CIRCULAR part
        only: points above the 45 deg tangent belong to the teardrop roof and are excluded by
        taking the lower 60 percent of the radius distribution."""
        out = []
        for _a, c, _r, rg in self.bins():
            # the ring's OWN vertices, not a depth window: a window of +-1.0 mm on a 1.418 mm
            # station pitch pulls in the neighbouring rings and smears the reading
            rs = sorted(math.hypot(p[1] - c[0], p[2] - c[1]) for p in rg)
            if len(rs) < 8:
                continue
            k = max(4, int(len(rs) * 0.6))
            out.append(rs[k - 1] - rs[0])
        return max(out) if out else 0.0

    def world_axis(self):
        cl, p, m = self.axis_clearance((ROD_MAX + HOLE_SHRINK) / 2.0)
        o = tuple(self.o0[i] + p[0] * self.e1[i] + p[1] * self.e2[i] for i in range(3))
        d = tuple(self.d0[i] + m[0] * self.e1[i] + m[1] * self.e2[i] for i in range(3))
        n = math.sqrt(sum(c * c for c in d))
        return o, tuple(c / n for c in d)

    def _local(self, v):
        o, d, e1, e2 = self.o0, self.d0, self.e1, self.e2
        rx, ry, rz = v[0] - o[0], v[1] - o[1], v[2] - o[2]
        a = rx * d[0] + ry * d[1] + rz * d[2]
        u = rx * e1[0] + ry * e1[1] + rz * e1[2]
        w = rx * e2[0] + ry * e2[1] + rz * e2[2]
        return a, math.hypot(u, w)

    def radial_wall(self, tris):
        """Minimum material AROUND this bore: shortest distance from a bore wall vertex to any
        triangle that is neither part of this bore nor one of the two faces the bore's own axis
        passes through.

        Excluding those two faces is the whole correction. The previous version did not, so on the
        end sockets it returned 1.418 mm and failed the part -- 1.418 mm being the distance from
        the first wall station to the socket's own OPEN MOUTH, which is a hole, not a wall. And on
        the branch socket it would have returned 1.4, which is the kit's deliberate blind floor.
        Radial material and axial material are different quantities with different kit gates, so
        they are now measured and gated separately (see floor_material)."""
        far = []
        o, d, e1, e2 = self.o0, self.d0, self.e1, self.e2
        for t in tris:
            loc = [self._local(v) for v in t]
            if all(a <= 0.2 for a, _r in loc):
                continue                                   # the open mouth plane
            if all(a >= self.depth - 0.2 for a, _r in loc):
                continue                                   # at or past the floor: axial, not radial
            if not any(r > BORE or a < -0.2 for a, r in loc):
                continue                                   # this bore's own wall
            if not any(r < 3.0 * BORE and -2.0 < a < self.depth + 2.0 for a, r in loc):
                continue                                   # too far away to hold the minimum
            far.append(t)
        best = 1e9
        step = max(1, len(self.wall) // 150)
        for p in self.wall[::step]:
            pw = tuple(o[i] + p[0] * d[i] + p[1] * e1[i] + p[2] * e2[i] for i in range(3))
            for t in far:
                dd = _pt_tri_d2(pw, *t)
                if dd < best:
                    best = dd
        return math.sqrt(best) if best < 1e9 else float("inf")

    def floor_material(self, tris):
        """Minimum material BEYOND this bore's floor: distance from the floor centre to the nearest
        triangle lying entirely past the floor plane. On the branch socket that is the kit blind
        wall; on an end socket the bore floor is buried in solid stock and the nearest free surface
        is the block's own side, so the number is large and the gate is slack by construction."""
        o, d, e1, e2 = self.o0, self.d0, self.e1, self.e2
        fc = tuple(o[i] + self.depth * d[i] for i in range(3))
        best = 1e9
        for t in tris:
            loc = [self._local(v) for v in t]
            if not all(a >= self.depth + 0.05 for a, _r in loc):
                continue
            dd = _pt_tri_d2(fc, *t)
            if dd < best:
                best = dd
        return math.sqrt(best) if best < 1e9 else float("inf")


def _pt_tri_d2(p, a, b, c):
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    ap = (p[0] - a[0], p[1] - a[1], p[2] - a[2])
    d1 = ab[0] * ap[0] + ab[1] * ap[1] + ab[2] * ap[2]
    d2 = ac[0] * ap[0] + ac[1] * ap[1] + ac[2] * ap[2]
    if d1 <= 0 and d2 <= 0:
        return ap[0] ** 2 + ap[1] ** 2 + ap[2] ** 2
    bp = (p[0] - b[0], p[1] - b[1], p[2] - b[2])
    d3 = ab[0] * bp[0] + ab[1] * bp[1] + ab[2] * bp[2]
    d4 = ac[0] * bp[0] + ac[1] * bp[1] + ac[2] * bp[2]
    if d3 >= 0 and d4 <= d3:
        return bp[0] ** 2 + bp[1] ** 2 + bp[2] ** 2
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3) if (d1 - d3) else 0.0
        q = (a[0] + v * ab[0], a[1] + v * ab[1], a[2] + v * ab[2])
        return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
    cp = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
    d5 = ab[0] * cp[0] + ab[1] * cp[1] + ab[2] * cp[2]
    d6 = ac[0] * cp[0] + ac[1] * cp[1] + ac[2] * cp[2]
    if d6 >= 0 and d5 <= d6:
        return cp[0] ** 2 + cp[1] ** 2 + cp[2] ** 2
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6) if (d2 - d6) else 0.0
        q = (a[0] + w * ac[0], a[1] + w * ac[1], a[2] + w * ac[2])
        return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        den = (d4 - d3) + (d5 - d6)
        w = (d4 - d3) / den if den else 0.0
        q = (b[0] + w * (c[0] - b[0]), b[1] + w * (c[1] - b[1]), b[2] + w * (c[2] - b[2]))
        return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
    den = va + vb + vc
    v = vb / den if den else 0.0
    w = vc / den if den else 0.0
    q = (a[0] + v * ab[0] + w * ac[0], a[1] + v * ab[1] + w * ac[1], a[2] + v * ab[2] + w * ac[2])
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2


def width_profile(tris):
    """Plan width against x, measured off the mesh at the x values the mesh actually has. Reads
    emitted vertices only; knows nothing of the generator's width().

    NOT fixed-width bins. Bins of 1 mm over stations spaced 1.5 mm leave a third of the bins empty,
    those bins get dropped, and a neck length summed over the survivors came out 52.2 mm against a
    true 74.6 -- which failed G4 with a forming strain of 0.0715 on a part whose strain is 0.0500
    by construction. Grouping by the mesh's own x and integrating between consecutive groups has no
    such bias."""
    grp = {}
    for v in verts_of(tris):
        k = round(v[0], 3)                 # grouping key only: an STL stores float32, so vertices
        e = grp.setdefault(k, [1e9, -1e9, 0.0, 0])   # meant to share an x do not share it exactly
        e[0] = min(e[0], v[1])
        e[1] = max(e[1], v[1])
        e[2] += v[0]                       # ... and the station's x is the MEAN of the real values,
        e[3] += 1                          # not the rounded key, which would bias every length
    return [(grp[k][2] / grp[k][3], grp[k][1] - grp[k][0]) for k in sorted(grp)]


def neck_length(prof, wmin, tol=0.05):
    """Total x covered by the narrowest section: sum of the gaps between consecutive profile
    stations that are BOTH at the minimum width. Both endpoints of the two necks sit exactly at
    the neck width (the flare's cosine lands on t), so this integrates the necks and nothing else.
    Returns (length, count of stations at minimum width)."""
    at = [x for x, w in prof if w <= wmin + tol]
    idx = {x: i for i, (x, _w) in enumerate(prof)}
    ln = 0.0
    for a, b in zip(at, at[1:]):
        if idx[b] - idx[a] == 1:
            ln += b - a
    return ln, len(at)


def seg_seg_dist(p0, d0, l0, p1, d1, l1):
    best = 1e9
    for i in range(41):
        a = l0 * i / 40.0
        pa = tuple(p0[k] + d0[k] * a for k in range(3))
        for j in range(41):
            b = l1 * j / 40.0
            pb = tuple(p1[k] + d1[k] * b for k in range(3))
            best = min(best, math.dist(pa, pb))
    return best


# ================================================================ the gates
class Gates:
    def __init__(self):
        self.rows = []

    def add(self, name, ok, note):
        self.rows.append((name, bool(ok), note))
        return ok

    def failed(self):
        return [r for r in self.rows if not r[1]]

    def dump(self, prefix=""):
        for n, ok, note in self.rows:
            print("%s  %-22s %s  %s" % (prefix, n, "PASS" if ok else "FAIL", note))


def source_purity(extra_line=None):
    """G12. Scan THIS source for retyped values of the geometry constants that must only ever
    arrive by import. The known-bad injects a synthetic offending line into the scanned text, so
    the scanner is proven to fire without ever committing a bad literal to the file."""
    txt = open(os.path.abspath(__file__)).read()
    if extra_line:
        txt += "\n" + extra_line + "\n"
    banned = {"BORE": BORE, "DEPTH": DEPTH, "ROD_MAX": ROD_MAX, "ROD_MIN": ROD_MIN,
              "SLIDE_BORE": RC.SLIDE_BORE, "LB": LB}
    hits = []
    for i, line in enumerate(txt.splitlines(), 1):
        code = line.split("#")[0]
        if "import" in code or "RC." in code or "KIT." in code:
            continue
        for num in re.findall(r"(?<![\w.])\d+\.\d+", code):
            v = float(num)
            for nm, cv in banned.items():
                if abs(v - cv) < 5e-3 or abs(v - round(cv, 2)) < 5e-4:
                    hits.append((i, nm, num, line.strip()[:60]))
    return hits


def check_mesh(path, part, theta, bent, g, tris=None):
    tris = tris if tris is not None else read_stl(path)
    tag = "BENT" if bent else "STRAIGHT"
    probe_r = (ROD_MAX + HOLE_SHRINK) / 2.0
    admit_min = clearance_diametral() / 4.0

    # --- G0 mesh sanity ---
    unp, ne = edge_parity(tris)
    g.add("G0 WATERTIGHT", unp == 0, "%d non-paired edges of %d" % (unp, ne))
    vol = signed_volume(tris)
    g.add("G0 ORIENTATION", vol > 0, "signed volume %+.1f mm3 (must be positive = outward)" % vol)

    seeds = end_face_seeds(tris)
    if len(seeds) < 2:
        g.add("G1 ROD ADMISSION", False, "could not recover two end faces from the mesh")
        return {}
    socks = [Socket(tris, seeds[0], "endA"), Socket(tris, seeds[1], "endB"),
             Socket(tris, branch_seed(tris), "branch")]

    # --- G5c PROBE COVERAGE: run FIRST, because every gate below is only worth the coverage of
    # the probe that feeds it. Built with the branch bore wall unsampled, the probe found 0 wall
    # points there and G2 reported 0.0000 mm of axis wander -- a PASS that had measured nothing.
    cov = []
    covok = True
    for s in socks:
        bs = s.bins()
        span = (bs[-1][0] - bs[0][0]) if len(bs) >= 2 else 0.0
        # measured against the socket's OWN depth, because this gate asks "did the probe see this
        # bore", not "is this bore deep enough". That second question is G5's, and conflating them
        # made G5c mask G5 so the --knownbad shallow artifact never reached it.
        ok = s.depth > 0.0 and len(bs) >= 8 and span >= 0.7 * s.depth and len(s.wall) >= 100
        covok &= ok
        cov.append("%s %d bins over %.1f of %.1f mm from %d wall pts%s"
                   % (s.tag, len(bs), span, s.depth, len(s.wall), "" if ok else " <-- BLIND"))
    g.add("G5c PROBE COVERAGE", covok,
          "%s: every socket must give >= 8 section fits spanning >= 0.7 of its own measured depth "
          "from >= 100 wall points | %s" % (tag, "; ".join(cov)))

    # --- G1 ROD ADMISSION: the gate this part exists for ---
    worst = 1e9
    naive_worst = 1e9
    det = []
    for s in socks:
        cl, _p, _m = s.axis_clearance(probe_r)
        nl, _p2, _m2 = s.axis_clearance(ROD_MAX / 2.0)
        worst = min(worst, cl)
        naive_worst = min(naive_worst, nl)
        det.append("%s %+.3f" % (s.tag, cl))
    g.add("G1 ROD ADMISSION",
          worst >= admit_min,
          "%s: min radial clearance %+.3f mm for a O%.1f stick in a bore printed %.2f under "
          "(gate >= %.4f) [%s] | model-only probe would read %+.3f"
          % (tag, worst, ROD_MAX, HOLE_SHRINK, admit_min, ", ".join(det), naive_worst))

    # --- G5 depth + bore diameter ---
    dmin = min(s.depth for s in socks)
    rr = [r for s in socks for r in s.radii()]
    # gated against the IMPORTED depth, not part.depth. part.depth is what this build asked for,
    # so comparing to it asks "did you get what you asked for" and can never catch a bad ask --
    # which is why --knownbad shallow, a rebuild of the v1 12 mm socket that sat AT the PLA crush
    # figure, sailed through this gate.
    g.add("G5 DEPTH+BORE", dmin >= DEPTH - 0.05 and
          abs(min(rr) * 2 - BORE) < 0.05 and abs(max(rr) * 2 - BORE) < 0.05,
          "min depth %.3f (need >= %.3f, DERIVED in rod_constants); bore O%.3f..%.3f "
          "(need %.3f +-0.05)" % (dmin, DEPTH, min(rr) * 2, max(rr) * 2, BORE))
    g.add("G5b PROBE SEPARATION", min(s.sep for s in socks) > 1.0,
          "bore-wall vs outer-surface vertex populations separated by %.2f mm "
          "(the classification is unambiguous)" % min(s.sep for s in socks))

    # --- G2 branch bore straightness + roundness ---
    br = socks[2]
    bwander, brad = br.bow()
    g.add("G2 BRANCH STRAIGHT", bwander <= 0.10 and br.roundness() <= 0.20,
          "%s: branch axis wander %.4f mm (gate 0.10), out-of-round %.4f mm (gate 0.20)"
          % (tag, bwander, br.roundness()))

    # --- G3 socket bow ---
    bows = [s.bow()[0] for s in socks[:2]]
    g.add("G3 SOCKET BOW", max(bows) <= bow_cap(),
          "%s: end-socket axis sagitta %.4f / %.4f mm (gate %.4f = a quarter of the %.2f mm "
          "as-printed clearance)" % (tag, bows[0], bows[1], bow_cap(), clearance_diametral()))

    # --- G8 kink ---
    rads = [s.bow()[1] for s in socks[:2]]
    rmin = min(rads)
    g.add("G8 KINK", rmin / part.w >= KINK_RD,
          "%s: hollow socket block forms at R %.0f mm on a %.1f mm section, R/OD %.1f "
          "(mandrel-free rule >= %.0f). The neck is SOLID so kinking has no purchase there."
          % (tag, rmin, part.w, rmin / part.w, KINK_RD))

    # --- G11 branch on the bisector ---
    if theta > 1e-6:
        oa, da = socks[0].world_axis()
        ob, db = socks[1].world_axis()
        oc, dc = socks[2].world_axis()
        nx = da[1] * db[2] - da[2] * db[1]
        ny = da[2] * db[0] - da[0] * db[2]
        nz = da[0] * db[1] - da[1] * db[0]
        m = math.sqrt(nx * nx + ny * ny + nz * nz)
        ang = math.degrees(math.acos(min(1.0, abs((nx * dc[0] + ny * dc[1] + nz * dc[2]) / m))))
        dif = abs(math.dist(oc, oa) - math.dist(oc, ob))
        g.add("G11 BISECTOR", ang <= 0.5 and dif <= 0.3,
              "%s: branch axis is %.3f deg off normal to the two leg axes (gate 0.5); branch "
              "origin equidistant from the two mouths to %.3f mm (gate 0.3)" % (tag, ang, dif))
    return {"socks": socks, "vol": vol}


def check_straight_only(path, part, g, tris=None):
    tris = tris if tris is not None else read_stl(path)
    seeds = end_face_seeds(tris)
    socks = [Socket(tris, seeds[0], "endA"), Socket(tris, seeds[1], "endB"),
             Socket(tris, branch_seed(tris), "branch")]

    # --- G6a radial wall, G6b blind floor: two different quantities, two different kit gates ---
    rad = [(s.tag, s.radial_wall(tris)) for s in socks]
    wt = min(r for _t, r in rad)
    g.add("G6a RADIAL WALL", wt >= WALL_MIN - 0.02,
          "min material around any bore %.3f mm (kit gate %.1f) [%s]"
          % (wt, WALL_MIN, ", ".join("%s %.2f" % r for r in rad)))
    flo = [(s.tag, s.floor_material(tris)) for s in socks]
    fmin = min(f for _t, f in flo)
    g.add("G6b BLIND FLOOR", fmin >= BLIND - 0.02,
          "min material past any bore floor %.3f mm (kit blind wall %.1f, recovered as LB - "
          "DEPTH) [%s]" % (fmin, BLIND, ", ".join("%s %.2f" % f for f in flo)))

    # --- G7 bore non-intersection ---
    oa, da = socks[0].world_axis()
    oc, dc = socks[2].world_axis()
    d1 = seg_seg_dist(oa, da, socks[0].depth, oc, dc, socks[2].depth) - BORE
    ob, db = socks[1].world_axis()
    d2 = seg_seg_dist(ob, db, socks[1].depth, oc, dc, socks[2].depth) - BORE
    g.add("G7 BORE CLEARANCE", min(d1, d2) >= WALL_MIN,
          "branch bore surface to end bore surfaces: %.2f / %.2f mm (gate %.1f)"
          % (d1, d2, WALL_MIN))

    # --- G4 neck strain ---
    prof = width_profile(tris)
    wmin = min(p[1] for p in prof)
    ln, nat = neck_length(prof, wmin)
    if part.theta > 1e-9:
        eps = wmin * part.theta / (2.0 * ln) if ln > 0 else 9.9
        # Ln is DERIVED from the cap, so a correct part sits exactly ON the boundary and the
        # comparison is decided by measurement noise. MEAS_TOL is that noise: an STL holds float32,
        # so a 160 mm coordinate carries about 1e-5 mm of error. 1e-4 relative is ~100x that floor
        # and 1000x below the smallest real violation any known-bad here produces (--knownbad
        # neckscale doubles the strain to 0.10).
        g.add("G4 NECK STRAIN", eps <= FORM_STRAIN_CAP * (1.0 + MEAS_TOL),
              "measured neck t %.2f mm over %.1f mm of neck (%d stations at minimum width) -> "
              "forming strain %.4f (cap %.2f); forming radius %.0f mm"
              % (wmin, ln, nat, eps, FORM_STRAIN_CAP, ln / part.theta if part.theta else 0))
    else:
        g.add("G4 NECK STRAIN", True, "theta = 0: rigid T blank, no neck, no forming strain")

    # --- G9 bed ---
    vs = verts_of(tris)
    bx = max(v[0] for v in vs) - min(v[0] for v in vs)
    by = max(v[1] for v in vs) - min(v[1] for v in vs)
    g.add("G9 BED", max(bx, by) <= BED, "footprint %.1f x %.1f mm (bed %.0f)" % (bx, by, BED))

    # --- G10 mass by two routes ---
    vmesh = signed_volume(tris)
    st = part.stations
    area = 0.0
    for k in range(len(st) - 1):
        dx = st[k + 1][0] - st[k][0]
        area += 0.5 * (part.width(st[k][0]) + part.width(st[k + 1][0])) * dx
    td = part.teardrop()
    at = abs(sum(td[i][0] * td[(i + 1) % len(td)][1] - td[(i + 1) % len(td)][0] * td[i][1]
                 for i in range(len(td)))) / 2.0
    vbranch = 0.0
    for k in range(len(st) - 1):
        vbranch += (st[k][2] + st[k + 1][2]) * (st[k + 1][0] - st[k][0])
    vbranch *= (part.h - part.zfloor)
    vexp = part.h * area - 2.0 * at * part.depth - vbranch
    err = abs(vmesh - vexp) / vexp
    g.add("G10 MASS", err < 0.01,
          "mesh volume %.0f mm3 = %.1f g at %.2f g/cm3; analytic route %.0f mm3, %.3f%% apart"
          % (vmesh, vmesh * RHO, RHO * 1000.0, vexp, err * 100.0))
    return vmesh


# ================================================================ known-bads
KNOWNBADS = {
    "tight":       ("G1 ROD ADMISSION", {"bore_d": ROD_MAX + 0.2},
                    "bore modelled at ROD_MAX+0.2: looks fine on the model, but the MEASURED "
                    "0.25 hole shrink makes the printed bore SMALLER than the stick"),
    "shallow":     ("G5 DEPTH+BORE", {"depth": 12.0},
                    "socket depth back to the v1 12 mm that sat AT the PLA crush figure"),
    "thinwall":    ("G6a RADIAL WALL", {"w": 11.0},
                    "block width 11.0 -> 2.0 mm side wall, under the kit's 2.4"),
    "thinfloor":   ("G6b BLIND FLOOR", {"depth": LB - 0.5},
                    "socket sunk to within 0.5 mm of the far face: the blind floor is thinner "
                    "than the kit's own 1.4 mm blind wall"),
    "noprobe":     ("G5c PROBE COVERAGE", {"no_zsub": True},
                    "branch bore wall emitted with no interior vertices. THIS IS THE DEFECT THAT "
                    "WAS IN THIS FILE: the probe measured nothing there and G2 passed anyway"),
    "noneck":      ("G3 SOCKET BOW", {"t": block_width()},
                    "neck as thick as the block: no neck, so the sockets take the whole bend"),
    "bowbranch":   ("G2 BRANCH STRAIGHT", {"branch_bow": 0.30},
                    "branch bore axis bowed 0.30 mm at mid-depth, zero at the mouth and the floor "
                    "so the probe's seed is untouched: the wander probe must find it"),
    "branchneck":  ("G5b PROBE SEPARATION", {"branch_on_neck": True},
                    "branch bore moved into the middle of a 9.5 mm neck, leaving 1.25 mm of wall. "
                    "The bore wall and the outer surface stop being separable populations at all"),
    "asym":        ("G11 BISECTOR", {"split": 0.6},
                    "necks split 60/40: the branch leaves the bisector"),
    "neckscale":   ("G4 NECK STRAIN", {"neck_scale": 0.5},
                    "neck length halved: forming strain doubles past the 5 percent cap"),
    "flipbranch":  ("qa_stl PRINTABLE", {"branch_down": True},
                    "branch socket blind from BELOW: a 7 mm ceiling to bridge inside the block"),
}


QA_STL = "/Users/olegmalkov/dev/crackle/tools/qa_stl.py"


def run_qa(paths, quiet=False):
    """Shell out to THE project gate. Returns (passed, tail of its output). Never reimplemented
    here: qa_stl.py is the thing that caught the sealed cast cavity, and a private copy of its
    rules would be a second source of truth that could drift."""
    import subprocess
    cmd = [sys.executable, QA_STL] + list(paths) + ["--class", "closed", "--bed", str(int(BED))]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not quiet:
        sys.stdout.write(r.stdout)
        sys.stdout.write(r.stderr)
    return r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()


def emit(part, theta, out_dir, name, note):
    sk = build(part, theta)
    path = os.path.join(out_dir, name + ".stl")
    write_stl(path, sk.tris, note)
    return path, sk


def run_one(theta_deg, out_dir, sab=None, sabname="", quiet=False):
    part = Part(theta_deg, sab)
    tagn = ("_KB-" + sabname) if sabname else ""
    base = "branch_sleeve_b%d%s" % (int(round(theta_deg)), tagn)
    g = Gates()
    hits = source_purity()
    g.add("G12 SOURCE PURITY", not hits,
          "no retyped rod_constants/kit literals in this source" if not hits
          else "retyped literals: %s" % hits[:3])
    pstr, sk = emit(part, 0.0, out_dir, base,
                    "branch_sleeve %s deg blank PRINT THIS FLAT" % theta_deg)
    g.add("G0 MIN TRI", sk.min_cross > 1e-6,
          "smallest kept triangle |cross| %.3e (qa_stl degenerate gate 1e-9)" % sk.min_cross)
    check_mesh(pstr, part, 0.0, False, g)
    check_straight_only(pstr, part, g)
    pbent = None
    if theta_deg > 0:
        pbent, _ = emit(part, part.theta, out_dir, base + "_BENT_MODEL",
                        "MODEL ONLY do not print: bent-shape verification mesh")
        check_mesh(pbent, part, part.theta, True, g)
    if not quiet:
        print("\n=== %s  theta %.0f deg  ===" % (base, theta_deg))
        print("  length %.1f  section %.3f x %.3f  neck t %.1f  Ln %.1f  mass %.1f g"
              % (part.L, part.w, part.h, part.t, part.ln,
                 signed_volume(read_stl(pstr)) * RHO))
        g.dump()
    return part, g, pstr, pbent


def selftest(out_dir):
    print("=" * 100)
    print("SELFTEST: every gate is run against an artifact built to break it. A gate that has "
          "never said FAIL")
    print("has not been shown able to fire, so nothing is emitted until all of these fire.")
    print("=" * 100)
    ok = True

    # G12 first: prove the source scanner fires on an injected literal
    hits = source_purity("    bore = %s   # retyped literal" % repr(BORE))
    fired = bool(hits)
    print("  %-14s %-22s %s   %s" % ("literal", "G12 SOURCE PURITY", "FIRED" if fired else "SILENT",
                                     "synthetic retyped-literal line injected into the scanned text"))
    ok &= fired

    # the historical known-bad: the part Oleg could not push a stick through
    sk = build_bendguide()
    p = os.path.join(out_dir, "branch_sleeve_KB-bendguide.stl.FAILED")
    write_stl(p, sk.tris, "KNOWN-BAD: the deleted 3-bore bend guide, 1.54 offset")
    tris = read_stl(p)
    os.remove(p)                                  # round-tripped through a real STL, then deleted
    seeds = end_face_seeds(tris)
    s = Socket(tris, seeds[0], "through", through=True)
    cl, _pp, _mm = s.axis_clearance((ROD_MAX + HOLE_SHRINK) / 2.0)
    fired = cl < clearance_diametral() / 4.0
    print("  %-14s %-22s %s   %s" % ("bendguide", "G1 ROD ADMISSION", "FIRED" if fired else "SILENT",
                                     "3 collinear O%.2f bores, middle offset 1.54 MEASURED: probe "
                                     "reads %+.3f mm clearance for a O%.1f stick"
                                     % (RC.SLIDE_BORE, cl, ROD_MAX)))
    ok &= fired

    for nm, (gate, sab, why) in sorted(KNOWNBADS.items()):
        _pt, g, pa, pb = run_one(45.0, out_dir, sab, nm, quiet=True)
        if nm == "flipbranch":
            # the ONLY known-bad whose gate lives outside this file. It was previously skipped
            # here with a comment promising it would "run separately below", and there was no
            # below: the printability gate had never been shown to fire on this part at all.
            passed, tail = run_qa([pa], quiet=True)
            fired = not passed
            print("  %-14s %-22s %s   %s" % (nm, gate, "FIRED" if fired else "SILENT", why))
            for line in tail[-3:]:
                print("      qa_stl| %s" % line)
        else:
            names = [r[0] for r in g.failed()]
            fired = gate in names
            print("  %-14s %-22s %s   %s" % (nm, gate, "FIRED" if fired else "SILENT", why))
            if not fired:
                print("      >>> gates that DID fail: %s" % (names or "none"))
        # Delete every known-bad artifact. It must not survive under a plain .stl name -- somebody
        # could print it -- and it should not survive as .FAILED either: 13 known-bads times two
        # meshes is 16 MB of binaries in a shared kit directory, and the verdict is the line above,
        # not the file. To inspect one, rebuild it alone with --knownbad NAME, which does leave a
        # .FAILED behind on purpose.
        for f in (pa, pb):
            if f and os.path.exists(f):
                os.remove(f)
        ok &= fired
    return ok


# ================================================================ process card
def process_card(part):
    tip = 300.0
    gap = 2.0 * tip * math.sin(part.theta / 2.0)
    soak = (part.t / 2.0) ** 2 / ALPHA_MM2_S
    i_n = part.h * part.t ** 3 / 12.0
    r_form = part.t / (2.0 * FORM_STRAIN_CAP)
    m_hot = E_HOT_MPA * i_n / r_form
    string = m_hot / (250.0 * math.cos(math.pi / 4.0)) if part.theta > 0 else 0.0
    pry = m_hot / part.depth
    print("\n  PROCESS (nothing below has been done to a real part):")
    print("    soak      %.0f s at 75 C, DERIVED from an ASSUMED diffusivity %.2f mm2/s -- the "
          "largest untested number here" % (soak, ALPHA_MM2_S))
    print("    fixture   two 300 mm SACRIFICIAL bamboo offcuts in the end sockets, a cotton "
          "string loop at 250 mm, a stick as windlass. Nothing printed.")
    print("    hold      string tension %.1f N on an ASSUMED %.0f MPa hot modulus; prying force "
          "in each end socket %.1f N" % (string, E_HOT_MPA, pry))
    print("    target    tip gap over 300 mm handles = %.1f mm; 1 mm of tape reads %.2f deg"
          % (gap, math.degrees(2.0 * math.asin(min(1.0, 0.5 / tip))) if part.theta > 0 else 0.0))
    print("    quench    fan hard on the whole triangle 3 min, then release and re-measure cold")
    print("    NOTHING goes in the branch socket during the bath: the fixture never touches the "
          "centre block.")


# ================================================================ main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--angle", type=float, default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--trade", action="store_true")
    ap.add_argument("--knownbad", choices=sorted(KNOWNBADS), default=None)
    ap.add_argument("--out-dir", default=_HERE)
    ap.add_argument("--no-selftest", action="store_true",
                    help="emit without proving the gates fire first (for debugging only)")
    a = ap.parse_args()

    t, t_soak, t_bow = neck_thickness(block_width())
    print("BRANCH SLEEVE -- formable branch fitting. NOTHING HAS BEEN PRINTED, HEATED OR BENT.")
    print("  imported : bore O%.2f flat, socket depth %.3f DERIVED in rod_constants, rods MEASURE "
          "O%.1f-%.1f," % (BORE, DEPTH, ROD_MIN, ROD_MAX))
    print("             kit wall >= %.1f, blind wall %.1f, boss length %.3f, teardrop roof %.0f deg"
          % (WALL_MIN, BLIND, LB, ROOF_DEG))
    print("  measured : printed holes come out %.2f mm UNDER the model -> as-printed diametral "
          "clearance on the fattest stick is %.2f mm, not %.2f"
          % (HOLE_SHRINK, clearance_diametral(), BORE - ROD_MAX))
    print("  derived  : section height %.3f = one kit boss; neck t %.1f = min(soak route %.2f, "
          "socket-bow route %.2f)" % (H_SECTION, t, t_soak, t_bow))
    print("             neck length = t*theta/(2*%.2f) so the forming radius is %.0f mm at EVERY "
          "angle" % (FORM_STRAIN_CAP, t / (2 * FORM_STRAIN_CAP)))
    print("  choice   : block width %.1f (DESIGN CHOICE, --trade prints what it was chosen from); "
          "neck carries %.0f%% of the kit's %.0f N.mm abuse case"
          % (block_width(), 100.0 * m_allow(block_width(), t) / kit_design_moment(),
             kit_design_moment()))
    print("  assumed  : PLA yield %.0f MPa, hot modulus %.0f MPa, diffusivity %.2f mm2/s, "
          "shape fixity. None measured on our filament." % (PLA_YIELD_MPA, E_HOT_MPA, ALPHA_MM2_S))

    if a.trade:
        print("\n  w      t     M_allow    of kit   total@90deg   note")
        for w, tt, ma, fr, tot in trade_table():
            note = ""
            if tot > BED:
                note = "does not fit the bed at 90 deg"
            print("  %4.1f  %4.1f  %8.0f    %5.2f    %6.1f       %s" % (w, tt, ma, fr, tot, note))
        return

    if a.knownbad:
        gate, sab, why = KNOWNBADS[a.knownbad]
        print("\nKNOWN-BAD '%s': %s\n  expected to fire: %s" % (a.knownbad, why, gate))
        part, g, p, pb = run_one(45.0, a.out_dir, sab, a.knownbad)
        for f in (p, pb):
            if f and g.failed():
                os.rename(f, f + ".FAILED")
                print("  quarantined -> %s.FAILED" % os.path.basename(f))
        raise SystemExit(0 if g.failed() else 1)

    if a.selftest or a.all or a.angle is not None:
        if not a.no_selftest:
            if not selftest(a.out_dir):
                print("\nREFUSING TO EMIT: at least one gate did not fire against its known-bad.")
                raise SystemExit(1)
            print("\nAll gates fired against their known-bads. Emitting.\n")
        if a.selftest and not (a.all or a.angle is not None):
            return

    angles = FAMILY_DEG if a.all else ([a.angle] if a.angle is not None else [])
    if not angles:
        ap.print_help()
        return
    bad = 0
    for th in angles:
        part, g, p, pb = run_one(th, a.out_dir, None, "")
        if g.failed():
            bad += 1
            for f in (p, pb):
                if f:
                    os.rename(f, f + ".FAILED")
                    print("  QUARANTINED -> %s.FAILED" % os.path.basename(f))
        else:
            process_card(part)
    print("\n%d/%d blanks passed the in-file gates." % (len(angles) - bad, len(angles)))
    good = [os.path.join(a.out_dir, "branch_sleeve_b%d.stl" % int(round(th))) for th in angles]
    good = [p for p in good if os.path.exists(p)]
    if good:
        print("\nTHE PROJECT GATE, on the printable blanks (the BENT_MODEL meshes are verification "
              "artifacts and are never printed, so they are not offered to it):")
        qaok, _tail = run_qa(good)
        if not qaok:
            bad += 1
            for p in good:
                os.rename(p, p + ".FAILED")
                print("  QUARANTINED -> %s.FAILED" % os.path.basename(p))
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
