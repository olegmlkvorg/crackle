#!/usr/bin/env python3
"""marble_common — the ONE connection standard + mesh/STL plumbing for the marble-run kit.

Every kit part couples the same way (defined here, used everywhere): BOND v2.1 =
CYLINDRICAL LAND + FRICTION SEAT + DEEP SNAP DETENT.
  BOTTOM = male SPIGOT: a Ø52 CYLINDRICAL LAND for the first LAND_H mm above the tip, then a
           cone out to Ø56 at the base. The land carries a smooth circumferential BUMP
           (sine bulge +0.8 mm radial, 5 mm wide, centred 4 mm above the tip).
  TOP    = female SOCKET: the same shape one wall + one clearance out — a Ø54.64 cylindrical
           bottom zone LAND_H deep (constant 0.12 face clearance), carrying the outward GROOVE
           bulge (+0.9 mm, 6 mm wide, aligned with the bump at full seat), then a ramp out to
           the Ø59.4 mouth (0.5 face clearance: generous entry).
WHY THE LAND (the v2 -> v2.1 fix, adversarial sweep 2026-08-02): on the old 7° cone, withdrawing
by delta opened the clearance by slope*delta (~0.125*delta) — faster than the 0.45 bump could
chase the groove shoulder, so the measured peak interference over the whole withdrawal path was
+0.001 mm: the detent NEVER engaged. On the land both paths are PARALLEL: early withdrawal opens
nothing, and the bump must climb out of the groove and cross the still-tight bottom zone,
compressing the full (BUMP_H - SEAT_CLEAR) = 0.68 mm against the two springy 1.2 mm vase walls
(~1.3% hoop each — the snap you feel, both directions). At rest the bump nests in the deeper
groove with 0.22 mm slack: it seats calmly, zero rest interference.
The land is LAND_H = 8 mm, not the nominal "~4": the 5 mm bump + 6 mm groove + the exit travel
that generates the snap physically need it (a 4 mm land cannot even contain the bump).
ACCEPTANCE IS DYNAMIC: withdrawal_sweep() below slides the male profile out 0..8 mm in 0.25 mm
steps and measures max radial face interference at every step; bond_check.py runs it on the
EMITTED STLs and requires peak >= 0.45 (the snap) with rest-state interference <= 0.05.
Wall-aware, as v1 learned the hard way: single-wall VASE prints put a LINE_W wall centred on the
path, so the FACE clearance = path gap - LINE_W. The old straight Ø55/Ø56 fit JAMMED exactly
there (0.5 mm path gap < 1.2 mm wall). Both bond surfaces stay single-valued r(z); max profile
slope ~0.50 (bump flank, lean ~27° from vertical, vase limit 55°).
Chain: funnel spout -> part socket / part spigot -> next socket, daisy-chained.
Funnel compatibility: stand/funnel_stl.py's plain Ø55 spout (no bump) still drops into a BOND
v2.1 socket — its Ø56.2 outer face wedges in the mouth ramp ~3.4 mm below the rim (computed off
the v2.1 socket path), above the detent zone (groove top ~9.5 mm below the rim). No click,
gravity-seated.

Marbles are ~Ø16; free path anywhere a marble must pass is ≥ Ø22.

Meshes are OPEN single surfaces (funnel_stl.py style): a grid of rings, single-valued r(θ, z),
so slicer VASE mode prints them as one continuous wall. Z-monotonic by construction.
"""
import math, os, struct

# ---- the kit connection standard: BOND v2.1 (surface path dimensions, mm) ----
LINE_W        = 1.2      # vase line width the fit is designed around (Oleg: "assuming 1.2mm line width")
COUPLE_L      = 16.0     # engagement length: socket depth = spigot length
SPIGOT_BASE_D = 56.0     # male path at the base (top of the spigot), end of the exit cone
SPIGOT_TIP_D  = 52.0     # male path at the tip AND over the whole cylindrical land
LAND_H        = 8.0      # cylindrical land: male z<=LAND_H and female d<=LAND_H are PARALLEL
# friction seat: FACE clearance (between printed faces, walls included) vs engagement depth d
SEAT_CLEAR  = 0.12       # constant face clearance over the land, d <= LAND_H (band 0.10-0.15)
ENTRY_CLEAR = 0.50       # face clearance at the mouth (d = COUPLE_L): generous entry
# deep snap detent: male bump + female groove, aligned at full seat, both INSIDE the land
BUMP_H   = 0.80          # bump radial height (sine bulge on the spigot land)
BUMP_W   = 5.0           # bump z-width
BUMP_Z   = 4.0           # bump centre above the male tip = groove centre above the socket bottom
GROOVE_H = 0.90          # groove outward radial depth (bump nests with 0.22 mm slack at rest)
GROOVE_W = 6.0           # groove z-width (wider than the bump: catches despite print drift)
BOND_DZ  = 0.25          # profile sampling step for the bond polylines
SNAP_MIN  = 0.45         # REQUIRED peak radial interference over the withdrawal sweep
REST_MAX  = 0.05         # REQUIRED max interference at the assembled rest state (seats calmly)
SPIGOT_BASE_R, SPIGOT_TIP_R = SPIGOT_BASE_D / 2, SPIGOT_TIP_D / 2
MARBLE_D   = 16.0   # standard marble
BORE_D     = 24.0   # default free marble path (marble + 8 mm of air)
CONE_SLOPE = 1.0    # max |dr/dz| for transition cones (45° from vertical)


def cone_h(r0, r1, slope=CONE_SLOPE):
    """Height a transition cone needs to stay within the print-safe slope."""
    return abs(r1 - r0) / slope


def _spigot_cone(z):
    """Male base shape (no bump): CYLINDRICAL land to LAND_H, then a cone out to the base."""
    if z <= LAND_H:
        return SPIGOT_TIP_R
    return SPIGOT_TIP_R + (SPIGOT_BASE_R - SPIGOT_TIP_R) * (z - LAND_H) / (COUPLE_L - LAND_H)


def _clear(d):
    """Face clearance at engagement depth d (0 = full seat): SEAT_CLEAR constant over the land
    (parallel paths — withdrawal opens NOTHING here), then a linear ramp out to ENTRY_CLEAR."""
    if d <= LAND_H:
        return SEAT_CLEAR
    return SEAT_CLEAR + (ENTRY_CLEAR - SEAT_CLEAR) * (d - LAND_H) / (COUPLE_L - LAND_H)


def _bulge(d, center, width, height):
    """Smooth circumferential bulge: raised-cosine, zero (value AND slope) at both edges."""
    if abs(d - center) >= width / 2:
        return 0.0
    return height * 0.5 * (1.0 + math.cos(2 * math.pi * (d - center) / width))


def spigot_r(z):
    """BOND v2.1 male path radius at z above the tip (0..COUPLE_L): land + cone + snap bump."""
    return _spigot_cone(z) + _bulge(z, BUMP_Z, BUMP_W, BUMP_H)


def socket_r(d):
    """BOND v2.1 female path radius at depth d above the socket bottom (0..COUPLE_L):
    male shape + one wall + clearance (constant over the land) + outward groove bulge."""
    return _spigot_cone(d) + LINE_W + _clear(d) + _bulge(d, BUMP_Z, GROOVE_W, GROOVE_H)


def withdrawal_sweep(male_prof, fem_prof, travel=8.0, step=0.25):
    """DYNAMIC bond acceptance (the v2 lesson: a static seat number said 0.33 snap while the
    real pull-out force was zero). Slide the male profile OUT of the female profile 0..travel
    in `step` increments; at each offset compute the max radial FACE interference
    (male path + LINE_W - female path) over the overlapping engagement. Also scan the other
    way (over-insertion) for the gravity-settled seat.

    male_prof = [(z, r_path)] with the tip at z=0; fem_prof = [(d, r_path)] with the socket
    bottom at d=0 — either designed (spigot_profile/socket_profile) or measured off emitted
    STLs (bond_check.py). Returns a dict:
      curve      [(delta, interference)] for delta = 0..travel
      peak, peak_at   max interference on the way out — the SNAP (require >= SNAP_MIN)
      rest       interference at nominal full seat, delta=0 (require <= REST_MAX)
      settle     gravity-settled seat: deepest over-insertion delta<=0 still interference-free
                 (profile-only: the tip-vs-shoulder hard stop below d=0 is not modelled)
      entry      face clearance at the mouth (require >= 0.4)
    """
    def interp(prof, x):
        for (a, ra), (b, rb) in zip(prof, prof[1:]):
            if a - 1e-9 <= x <= b + 1e-9:
                t = 0.0 if b == a else (x - a) / (b - a)
                return ra + t * (rb - ra)
        return None

    z_hi = male_prof[-1][0]

    def imax(delta):
        worst = -9e9
        n = int(z_hi / 0.05)
        for i in range(n + 1):
            z = z_hi * i / n
            rf = interp(fem_prof, z + delta)
            if rf is None:
                continue
            rm = interp(male_prof, z)
            worst = max(worst, rm + LINE_W - rf)
        return worst

    curve = []
    k = 0
    while k * step <= travel + 1e-9:
        curve.append((k * step, imax(k * step)))
        k += 1
    peak, peak_at = max((i, d) for d, i in curve)
    settle = 0.0
    k = 0
    while True:
        k -= 1
        if imax(k * 0.05) > 0.0 or k * 0.05 < -4.0:
            settle = (k + 1) * 0.05
            break
    entry = interp(fem_prof, fem_prof[-1][0] - 0.01) - interp(male_prof, z_hi - 0.01) - LINE_W
    return dict(curve=curve, peak=peak, peak_at=peak_at, rest=curve[0][1],
                settle=settle, entry=entry)


# derived (kept for parts that cone into/out of the bond ends)
SOCKET_BOT_R,  SOCKET_MOUTH_R = socket_r(0.0), socket_r(COUPLE_L)
SOCKET_BOT_D,  SOCKET_MOUTH_D = 2 * SOCKET_BOT_R, 2 * SOCKET_MOUTH_R


def _bond_zs():
    n = int(round(COUPLE_L / BOND_DZ))
    return [COUPLE_L * i / n for i in range(n + 1)]


def spigot_profile():
    """Male end (bottom): sampled polyline, tip at z=0 -> base at z=COUPLE_L. [(z, r), ...]."""
    return [(z, spigot_r(z)) for z in _bond_zs()]


def socket_profile(z_bottom):
    """Female end (top): sampled polyline, socket-bottom at z_bottom -> mouth at z_bottom+COUPLE_L."""
    return [(z_bottom + d, socket_r(d)) for d in _bond_zs()]


def rev_rings(profile, n_pts):
    """profile = [(z, r), ...] -> ring grid rows [(z, [r]*n)] (surface of revolution)."""
    return [(z, [r] * n_pts) for z, r in profile]


def _row(row):
    """A grid row is (z, radii) or (z, radii, (cx, cy)). The optional centre is what makes a
    LEANING part possible: a vertical shear TRANSLATES each horizontal ring and leaves it
    perfectly circular, so bond ends still mate. Rows without a centre read as (0, 0)."""
    if len(row) == 3:
        z, radii, c = row
        return z, radii, c[0], c[1]
    z, radii = row
    return z, radii, 0.0, 0.0


def shear_rows(rows, lean_deg, z0, z1):
    """Tilt the part between z0 and z1 by lean_deg, holding everything below z0 at x=0 and
    carrying everything above z1 rigidly across at the full offset.

    offset(z) = 0                     z <= z0     (bottom bond zone: untouched, vertical)
              = (z - z0) * tan(lean)  z0 < z < z1 (the tilted body)
              = (z1 - z0) * tan(lean) z >= z1     (top bond zone: translated, still vertical)

    Both bond zones stay vertical and circular, so a leaning segment still couples to every
    straight part in the kit; the stack just steps sideways by the offset each segment.
    """
    t = math.tan(math.radians(lean_deg))
    out = []
    for row in rows:
        z, radii, cx, cy = _row(row)
        dx = 0.0 if z <= z0 else (z1 - z0) * t if z >= z1 else (z - z0) * t
        out.append((z, radii, (cx + dx, cy)))
    return out


def lean_budget(measured_max_lean_deg, ceiling=55.0):
    """Degrees of tilt still available before the vase-printable wall-lean ceiling.
    Shear adds its angle straight onto the downhill wall, so the budget is what is left."""
    return ceiling - measured_max_lean_deg


def grid_tris(rows, n_pts, close=True):
    """rows = [(z, [r_0..r_{n-1}]), ...] or [(z, radii, (cx, cy)), ...] bottom->top;
    quads between rings -> triangles. Same winding as funnel_stl.py."""
    def pt(z, radii, cx, cy, k):
        th = 2 * math.pi * k / n_pts
        return (cx + radii[k] * math.cos(th), cy + radii[k] * math.sin(th), z)
    tris = []
    rng = n_pts if close else n_pts - 1
    for i in range(len(rows) - 1):
        z0, r0, cx0, cy0 = _row(rows[i]); z1, r1, cx1, cy1 = _row(rows[i + 1])
        for k in range(rng):
            k1 = (k + 1) % n_pts
            p00 = pt(z0, r0, cx0, cy0, k); p01 = pt(z0, r0, cx0, cy0, k1)
            p10 = pt(z1, r1, cx1, cy1, k); p11 = pt(z1, r1, cx1, cy1, k1)
            tris.append((p00, p10, p11)); tris.append((p00, p11, p01))
    return tris


def disc_tris(z, r, n_pts, up=False, centre=(0.0, 0.0)):
    """Closed floor cap (for the catch cup): triangle fan at height z."""
    tris = []
    cx, cy = centre
    c = (cx, cy, z)
    for k in range(n_pts):
        th0 = 2 * math.pi * k / n_pts; th1 = 2 * math.pi * (k + 1) / n_pts
        a = (cx + r * math.cos(th0), cy + r * math.sin(th0), z)
        b = (cx + r * math.cos(th1), cy + r * math.sin(th1), z)
        tris.append((c, a, b) if up else (c, b, a))
    return tris


# ---- the sort kit: the chute has always been a sieve, nobody had named it ----
# MEASURED 2026-08-02 off the emitted spiral_chute mesh: the wall is single-valued r(theta,z),
# so the minimum radius over theta is the rail crest at EVERY height (7.50mm, dead constant over
# the whole wave zone). The central shaft is therefore a clear O15.00 tube running the full
# tower, and the rail crest diameter IS the sort threshold: anything smaller free-falls the
# axis, anything larger rides the spiral.
HOLE_SHRINK = 0.25   # printed hole comes out ~0.25mm under the model (Creality vase empirics)
SORT_DRIFT  = 0.35   # crest print drift + marble out-of-round, per side. ASSUMED, not measured
                     # on a printed crest: the gauge print is what turns this into a measurement.


def sort_min_separation():
    """Smallest (hold_d - drop_d) a printed crest can honestly separate.
    The crest has to clear the dropping marble AND block the riding one, so it needs
    SORT_DRIFT of margin on each side, and the whole feature sits HOLE_SHRINK under nominal."""
    return 2 * SORT_DRIFT + HOLE_SHRINK


def sort_gate(hold_d, drop_d):
    """Rail crest diameter that drops <= drop_d and holds >= hold_d. Raises when the two
    marble sizes are too close for a printed crest to tell apart."""
    need = sort_min_separation()
    if hold_d - drop_d < need:
        raise ValueError(
            f"cannot sort O{drop_d:g} from O{hold_d:g}: separation {hold_d - drop_d:.2f}mm < "
            f"{need:.2f}mm required (2 x {SORT_DRIFT:g} drift + {HOLE_SHRINK:g} hole shrink). "
            f"Pick marbles at least {need:.2f}mm apart, or print the gauge and measure the real "
            f"drift before trusting a tighter gate.")
    return (hold_d + drop_d) / 2 + HOLE_SHRINK      # model bigger: it prints smaller


# ---- the structure grid: how close two towers may stand ----
# Derived from the real part faces, not picked: neighbouring towers must clear at their widest,
# which is the socket MOUTH (the pocket wave is narrower), plus a finger gap to assemble.
FINGER_GAP  = 8.0    # mm between neighbouring mouths: enough to get a hand between towers
GRID_PITCH  = SOCKET_MOUTH_D + FINGER_GAP


def write_stl(path, tris):
    """Binary STL, funnel_stl.py style."""
    with open(path, "wb") as f:
        f.write(b"\0" * 80); f.write(struct.pack("<I", len(tris)))
        for t in tris:
            ux, uy, uz = (t[1][0]-t[0][0], t[1][1]-t[0][1], t[1][2]-t[0][2])
            vx, vy, vz = (t[2][0]-t[0][0], t[2][1]-t[0][1], t[2][2]-t[0][2])
            nx, ny, nz = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
            m = math.hypot(nx, ny, nz) or 1.0
            f.write(struct.pack("<3f", nx/m, ny/m, nz/m))
            for p in t: f.write(struct.pack("<3f", *p))
            f.write(b"\0\0")


def verify_stl(path):
    """Read the FILE back (different route than the writer) and measure it:
    size == 84+50n, triangle count, bounds, degenerate (zero-area) count,
    max wall lean from vertical (printability)."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        assert size == 84 + 50 * n, f"{path}: size {size} != 84+50*{n}"
        lo = [1e30] * 3; hi = [-1e30] * 3
        degen = 0; max_lean = 0.0; flat = 0
        for _ in range(n):
            f.read(12)
            vs = [struct.unpack("<3f", f.read(12)) for _ in range(3)]
            f.read(2)
            for v in vs:
                for j in range(3):
                    lo[j] = min(lo[j], v[j]); hi[j] = max(hi[j], v[j])
            ux, uy, uz = (vs[1][0]-vs[0][0], vs[1][1]-vs[0][1], vs[1][2]-vs[0][2])
            vx, vy, vz = (vs[2][0]-vs[0][0], vs[2][1]-vs[0][1], vs[2][2]-vs[0][2])
            cx, cy, cz = (uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx)
            a2 = math.hypot(cx, cy, cz)
            if a2 < 1e-9:
                degen += 1
            else:
                lean = math.degrees(math.asin(min(1.0, abs(cz) / a2)))
                if lean > 89.5:
                    flat += 1          # horizontal face (e.g. a floor disc on the bed)
                else:
                    max_lean = max(max_lean, lean)
    return dict(size=size, tris=n, lo=lo, hi=hi, degen=degen, max_lean=max_lean, flat=flat)


def report(path, v, note=""):
    print(f"{path}: {v['tris']} triangles, {v['size']} bytes (=84+50n OK), "
          f"{v['degen']} degenerate, bounds "
          f"x[{v['lo'][0]:.1f},{v['hi'][0]:.1f}] y[{v['lo'][1]:.1f},{v['hi'][1]:.1f}] "
          f"z[{v['lo'][2]:.1f},{v['hi'][2]:.1f}] mm, max wall lean {v['max_lean']:.0f}° from vertical"
          + (f" (+{v['flat']} flat floor tris on the bed)" if v.get('flat') else ""))
    sw = withdrawal_sweep(spigot_profile(), [(d, socket_r(d)) for d in _bond_zs()])
    print(f"  coupling: BOND v2.1 — spigot Ø{SPIGOT_TIP_D:g} land x{LAND_H:g} -> Ø{SPIGOT_BASE_D:g}base "
          f"+ bump {BUMP_H:g}x{BUMP_W:g}mm at z={BUMP_Z:g} / socket Ø{SOCKET_BOT_D:g}->Ø{SOCKET_MOUTH_D:g}mouth "
          f"+ groove {GROOVE_H:g}x{GROOVE_W:g}mm, {COUPLE_L:g}mm deep; face clearance {ENTRY_CLEAR:g} entry "
          f"-> {SEAT_CLEAR:g} land; DESIGN withdrawal sweep: peak {sw['peak']:+.2f}mm at "
          f"{sw['peak_at']:.2f}mm out (need >= {SNAP_MIN:g}), rest {sw['rest']:+.2f}, settle "
          f"{sw['settle']:+.2f} (emitted-STL sweep = bond_check.py){('. ' + note) if note else ''}")
