#!/usr/bin/env python3
"""SORT HEAD STL -- a sorter that works, and it does NOT use the chute to do it.

READ THIS FIRST, because the name is misleading and the honest version matters more.
Adversarial verification 2026-08-03 measured what actually happens: on all nine sorted pours the
marble travels 0 degrees of gutter and stays within 1.00mm of the axis inside the chute's own wave
band, and the rejected marble never enters the chute at all. NEITHER MARBLE EVER TOUCHES THE
SPIRAL. Delete the chute and the sort result is identical. This part is a standalone sieve that
happens to be shaped like a chute fitting, not the piece that makes a chute sort.

KNOWN FUNCTIONAL DEFECT, measured at all nine offsets under two material settings: the rejected
marble does not stay in the catch bowl to be picked out. It settles at r=0.01, dead centre, ON the
sieve mouth. It PLUGS the bore. The first rejected marble stops the sorter until a hand moves it.

UNTESTED PRINT RISK: the part stands on a O12.60 single-wall tube for its first 133mm, a 10.6:1
slenderness ratio, then carries a O100 bowl at 222mm. That is roughly 237 consecutive layers of
about 0.8s each at the kit speed. Nothing in this kit gates for slenderness or minimum layer time.
It may simply not stand up.

The original framing follows, kept because the geometry reasoning in it is still correct.

SORT HEAD STL -- the piece that was meant to make the sorting chute actually sort.

The chute's rail crest separates marbles by size, but only for a marble arriving on the axis:
MEASURED, 2mm off centre and it clips the crest and rides the spiral. So the crest is the wrong
place to do the sorting. A GUIDE TUBE sized BETWEEN the two marble sizes is its own sieve: the
small marble ENTERS it, the large one CANNOT and stays in the catch bowl for you to pick out.

WHY v1 WAS ONLY HALF RIGHT (head merged onto the real chute, 2026-08-03):
    O16 poured 0 / 20 / 35mm off centre    HELD, every time            <- the sieve works
    O12 poured dead centre                 SORTED, 0.23s down the shaft
    O12 poured anywhere else               RODE THE SPIRAL             <- 1 of 9 pours sorted
A guide tube removes POSITION error but not VELOCITY error, and below the tube v1 flared straight
out to the coupling, so the marble free-fell 68mm to the crest with nothing guiding it.

=============================== WHICH FIX, MEASURED ===============================
A LONGER TUBE DOES NOTHING. Five lengths, same chain, same outcome:
    tube  24mm (v1)  1/9      tube 72mm  1/9      tube 120mm  1/9
    tube  48mm       1/9      tube 96mm  1/9
sort_head_trace.mjs says why, by splitting the lateral velocity into RADIAL (across the bore) and
AZIMUTHAL (around it). Inside a 72mm tube, pour 35mm off centre:
    z=280.5  r=1.13  vr=  2.11  vth=-53.37        <- radial already dead 9mm in
    z=252.1  r=1.12  vr=  1.28  vth=-51.79
    z=220.6  r=1.12  vr=  1.23  vth=-50.01        <- 70mm later, swirl is still there
A round bore kills the radial component in its first millimetres and then CONSERVES SWIRL: a ball
rolling round a circular wall feels no force opposing it, so no length of round tube takes it out.
That is what the v1 note got wrong. It is not that the tube is too short, it is that it is round.
Nor is the swirl removable at its source: a fluted vortex-breaker bowl (N = 4/6/8/10/14, ridge
depth 0.25 and 0.40 of the local radius, capped and uncapped) measured 1-3 of 9, i.e. nothing.
Nor is the corner where the flare meets the tube the problem: rounding it into a tangent bell
measured 1 of 9, WORSE. Nor the bowl (mouth 60/80/100/140, lean 40/50/55), the bore (13.30 to
15.05), a converging exit, or mesh resolution (144/288/576). Thirty-five head variants. None of
them beat 4 of 9, because none of them address the thing that decides it.

A STRAIGHT DROP SECTION BELOW THE TUBE IS THE FIX -- not as a second wall inside the spigot (this
is one vase wall, and two walls at one height is the mistake that shipped unprintable parts
before), but as THE TUBE ITSELF CONTINUING DOWN, PAST THE COUPLING, INTO THE CHUTE'S OWN SHAFT.
r(z) stays single-valued and z-monotonic, so the BOND spigot simply becomes a bulge partway up:
    guide tube -> cone out to the spigot -> BOND v2.1 -> flare in -> guide tube again, all the way
    down the chute.
How far down it has to go is not a taste question. MEASURED, O10 on the same chute, only the
lower tube's length changed:
    lines  5mm of the shaft  1/9        lines  60mm  7/9
    lines 15mm               3/9        lines 120mm  9/9   <- reaches the end of the crest zone
    lines 30mm               6/9        lines 170mm  9/9
The marble has to stay in the tube until it is past the LAST helical crest, because one touch on
that crest is what puts it in the gutter. So the tube runs to the bottom of the chute's crest
zone, measured off the chute's emitted mesh.

=========================== AND WHY O12 CANNOT HAVE IT ===========================
Whether the tube can enter the shaft at all is arithmetic, not effort. Printed faces, not paths:
    bore face   = drop + 2*SORT_DRIFT          the tightest bore that still passes the marble
    tube OD     = bore + 2*LINE_W              one bead per side
    shaft face  = tube OD + 2*FIT_CLEAR        it has to drop in by hand
    crest path  = shaft face + LINE_W          the chute's own bead
For a O12 marble that is a O16.95 crest. A chute that must also keep a O16 marble CAPTIVE can
offer at most O15.90 (marble_common: printed crest = rail - HOLE_SHRINK, and the rider needs
SORT_DRIFT of margin). O12 misses by 1.05mm, and the sort rate says so:
    drop O12   tube stops 1.93mm above the crest   2/9
    drop O11   tube stops 0.81mm above the crest   5/9
    drop O10   tube lines the WHOLE shaft          9/9      <- predicted limit was O10.30
So this head sorts O16 from O10, not O16 from O12, and the gate below REFUSES to build the O12
version rather than shipping a part that sorts 2 pours in 9. The two knobs are named there.

WHAT IS NOT PROVEN. sim_core.mjs's friction 0.5 and restitution 0.15 are ASSUMED, so 9/9 is a
model result, not a printed one. Nothing here has been printed. The lower tube also fills the
chute's shaft end to end, so a chute wearing this head is a sorter, not a chute with a funnel on
it -- and it prints as a long thin straw standing on the bed before it flares, which is the
riskiest thing about the part.

Usage: python3 sort_head_stl.py --chute sort_chute_16_14.stl [--hold 16] [--drop 10]
       python3 sort_head_stl.py --chute sort_chute_16_14.stl --drop 12    # watch the gate fire
       python3 sort_head_stl.py --chute sort_chute_16_14.stl --no-extension   # rebuild v1
"""
import argparse, bisect, collections, math, os, struct

import marble_common as mc

# ---- the two things the printer does to a vase wall, and which one each check must assume ----
# The kit's own rule (marble_common, and how socket_r is built): the bead is laid CENTRED on the
# surface path, so a printed FACE sits LINE_W/2 outside the path and a bore prints LINE_W under
# its modelled diameter. marble_common ALSO carries HOLE_SHRINK = 0.25, "printed hole ~0.25mm
# under the model", from the Creality vase empirics. The two disagree about the same number and
# neither has been measured on THIS part, so nothing here picks a winner: every check uses
# whichever of the two is pessimistic for the thing it is checking.
BORE_MODELS = {
    "half-bead": lambda d: d - mc.LINE_W,                 # wall centred on the path
    "hole-shrink": lambda d: d - mc.HOLE_SHRINK,          # Creality vase empiric
}
WORST_SHRINK = max(mc.LINE_W, mc.HOLE_SHRINK)

BORE_CLEAR = mc.SORT_DRIFT       # 0.35mm per side on the WORST-case printed bore. DERIVED: that
                                 # is exactly the budget marble_common already sets aside for
                                 # print drift plus marble out-of-round, and it is the TIGHTEST
                                 # defensible number -- which is what you want here, because
                                 # every 0.1mm of bore is 0.1mm the chute's shaft has to give
                                 # back before the tube can go in.
FIT_CLEAR  = 2 * mc.SORT_DRIFT   # 0.70mm of face clearance between the hanging lower tube and the
                                 # chute's bore: both parts print off-nominal and the head has to
                                 # drop in by hand down the whole shaft.
BOWL_LEAN  = 50.0                # deg from vertical, catch bowl flare, under the 55 vase ceiling
FLARE_LEAN = 50.0                # deg from vertical, spigot -> lower tube. An OVERHANG (it grows
                                 # outward going up) that also has to thread the chute's own 45deg
                                 # cone: at 45 the two run parallel with 0.37mm between them, at
                                 # 50 they diverge immediately. The fit check measures it on both
                                 # meshes, which is what says so. Rounding this corner into a
                                 # tangent bell was tried and measured WORSE (1/9 vs 3/9).
EXIT_LEAN  = 55.0                # deg from vertical, upper tube -> spigot. At the vase ceiling on
                                 # purpose: this cone is the top of the wide chamber the marble
                                 # crosses unguided between the two tubes, so every mm costs.
TUBE_L_MIN = 2.0                 # upper tube length in marble diameters. The length sweep says
                                 # more buys NOTHING, and the trace says the radial component is
                                 # dead 9mm in, so this is the shortest thing that is a guide
                                 # rather than a hole -- not an aiming device.
BAY_LEAN   = 50.0                # deg from vertical, the cone under the park bays
ROLL_GRADE = 21.0                # deg. MEASURED on this kit's gutter: the grade at which a marble
                                 # RELIABLY MOVES. Reused here as the floor for the bay rim's fall,
                                 # because the job is identical -- get a resting marble to roll.
HUB_BLOCK  = 0.5                 # mm the hub must be too small for the held marble, the same
                                 # margin the sieve bore itself is held to


# ------------------------------------------------- the throat, and why it is shaped like a star
# THE LAW THAT KILLS THE OBVIOUS FIXES. A vase part is ONE closed loop per layer with z monotone
# along the wall, so the vessel has exactly ONE bottom opening and the interior surface has
# exactly ONE low point: that opening. A moat needs two loops at one height. A crown needs the
# floor to fall away outside it, which is the same thing. An off-centre bowl still drains to its
# drain. Every marble in the bowl therefore ends up AT THE DRAIN, and a marble too fat to pass it
# rests on its rim, centred, plugging it -- which is exactly what was measured.
# So the drain's SHAPE is the only free variable, and the fix is a drain the reject can sit in
# WITHOUT covering the way down: a central sieve bore with N radial PARK BAYS off it, each one
# bore-wide (so it still sorts) and each with its rim falling outward (so the reject rolls out of
# the middle and stays out). Bays are capsules of radius tr about spines from the axis, so every
# passage in the throat is exactly the sieve width -- one dimension, one sort threshold.

def bay_half_w(s, reach, tr, w_tip):
    """Half width of the slot at station s along a bay. It OPENS from the sieve bore at the axis
    to w_tip at the park station, then holds w_tip out to the end of the slot. The taper is what
    makes the park a pocket instead of a place the marble merely happens to stop: a O16 sits
    sqrt(hold_r^2 - w^2) above the rim, so a wider slot seats it deeper. Measured, the untapered
    park was a 0.05mm dimple, shallow enough that the mesh's own sampling ripple produced others
    just like it."""
    return tr + (w_tip - tr) * min(abs(s), reach) / reach if reach else tr


def bay_outline_r(theta, reach, tr, bays, w_tip=None, reach_out=None):
    """Polar radius of the throat outline at angle theta: the boundary of the union of `bays`
    tapered capsules whose spines run from the axis out to `reach`. Swept, not solved in closed
    form, so the gate can re-derive the same curve a different way. Swept rather than bisected
    because the taper makes the ray test non-monotone inside the end cap (w gains on d there), and
    a bisection would happily return the wrong crossing."""
    w_tip = tr if w_tip is None else w_tip
    reach_out = reach if reach_out is None else reach_out
    ux, uy = math.cos(theta), math.sin(theta)

    def outside(t):
        for k in range(max(1, bays)):
            a = 2 * math.pi * k / max(1, bays)
            ax, ay = math.cos(a), math.sin(a)
            s = min(max(t * (ux * ax + uy * ay), 0.0), reach_out)
            if math.hypot(t * ux - s * ax, t * uy - s * ay) <= bay_half_w(s, reach, tr, w_tip):
                return False
        return True

    hi = reach_out + w_tip + 1.0
    last, t, step = 0.0, 0.0, 0.05
    while t <= hi:
        if not outside(t):
            last = t
        t += step
    lo, hi = last, last + step
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if outside(mid):
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def outline_pts(reach, tr, bays, w_tip=None, reach_out=None, n=720):
    return [(r * math.cos(t), r * math.sin(t)) for t, r in
            ((2 * math.pi * i / n,
              bay_outline_r(2 * math.pi * i / n, reach, tr, bays, w_tip, reach_out))
             for i in range(n))]


def throat_clear(x, y, pts):
    """Largest disc that fits in the throat outline centred on (x, y): the distance from the point
    to the outline. This is the number that decides BOTH sorts -- a sphere passes a planar opening
    only where a disc of its own radius fits."""
    return min(math.hypot(x - px, y - py) for px, py in pts)


def hub_clear(reach, tr, bays, w_tip=None, reach_out=None):
    """Clearance at the hub, where the bays meet. tr/sin(pi/N) in closed form; measured off the
    sampled outline here so the two routes can be compared."""
    return throat_clear(0.0, 0.0, outline_pts(reach, tr, bays, w_tip, reach_out))


def bay_grade(reach, tr, bays, hold_r, w_tip=None, step=0.25):
    """Rim fall per mm of radius the bays need, DERIVED not chosen.
    A ball resting in the throat sits sqrt(hold_r^2 - clear^2) above the rim, and `clear` is
    LARGEST at the hub (that is where the bays meet), so leaving the hub RAISES the ball and the
    hub is a trap unless the rim falls faster. Requirement: that rise, plus the measured grade at
    which a marble reliably rolls."""
    pts = outline_pts(reach, tr, bays, w_tip)
    prev, rise = None, 0.0
    s = 0.0
    while s <= reach + 1e-9:
        c = min(throat_clear(s, 0.0, pts), hold_r - 1e-6)
        h = math.sqrt(hold_r ** 2 - c ** 2)
        if prev is not None:
            rise = max(rise, (h - prev) / step)
        prev = h
        s += step
    return rise + math.tan(math.radians(ROLL_GRADE)), rise


def max_bays(tr, hold_r):
    """Most bays whose hub still blocks the held marble. Bays meeting at the axis widen it:
    hub = tr/sin(pi/N), so this is arithmetic, not taste."""
    n = 2
    while tr / math.sin(math.pi / (n + 1)) <= hold_r - HUB_BLOCK:
        n += 1
    return n


def bay_station(theta, reach, tr, bays, w_tip=None, reach_out=None):
    """Where a point on the throat outline sits along the ONE direction the rim falls in, which is
    what its height is a function of. Two earlier versions are in the measurements:

    rim height from the outline RADIUS -- WRONG. At N=3 the outline near the hub is nearly
    circular, so the rim under a marble at the hub and under one 3.5mm out came out the same
    height and the hub stayed a 1.16mm WELL (rest 218.17 at r=0 against 219.33 at r=3.5, measured
    off the emitted mesh).

    rim falling SYMMETRICALLY to both tips -- also wrong, and the reason is worth keeping. A ball
    rests on the highest rim point within its own radius, so above a single high point its resting
    height is a circular arc, and an arc is FLAT at its top. The symmetric slot's apex measured a
    2.6 deg seat slope over the bore (rest 210.056 at r=0 against 210.033 at r=0.5) where the
    design asked for 21. There is no shape fix: any symmetric throat has a stationary point on the
    axis, which is exactly where the marble must not be able to stop.

    ONE-SIDED, so the rim falls in a single direction and the point holding the ball is always
    ~2mm BEHIND it -- measured, that gives the full grade everywhere including directly over the
    bore, with no stationary point at all. It is the better shape and it is NOT what this builds,
    for a meshing reason worth recording: a one-way rim makes the horizontal section a wedge whose
    edges run nearly along a radius (the wedge opens at 26 deg while the ray to it leaves at 30),
    and a ring sampled at equal ANGLES cannot follow a boundary that runs radially -- adjacent
    samples came out 20mm apart and the emitted facets read 88.7 deg. It needs a mesh sampled by
    arc length, which this generator does not have.

    So: SYMMETRIC, a park at each end of one slot. The apex over the bore is then a stationary
    point -- unavoidable, since a ball resting on a high point sits directly above it -- but it is
    a MAXIMUM, not a well: every direction off it falls. Nothing can settle there, and the sim
    pours are what have to show that nothing does."""
    r = bay_outline_r(theta, reach, tr, bays, w_tip, reach_out)
    best = 0.0
    for k in range(max(1, bays)):
        a = 2 * math.pi * k / max(1, bays)
        best = max(best, r * math.cos(theta - a))
    return min(max(best, 0.0), reach if reach_out is None else reach_out)


# ------------------------------------------------------------------------------- the law

def guided_crest_min(drop):
    """Smallest chute crest PATH diameter whose shaft will admit a guide tube carrying `drop`.
    All in printed FACES, then converted back to the chute's path by its own bead."""
    bore_face = drop + 2 * BORE_CLEAR
    tube_od = bore_face + 2 * mc.LINE_W
    return tube_od + 2 * FIT_CLEAR + mc.LINE_W


def max_guided_drop(crest_d):
    """Largest marble a guide tube can carry down a shaft of this crest diameter. Inverse of
    guided_crest_min, so the two cannot drift apart."""
    return crest_d - mc.LINE_W - 2 * FIT_CLEAR - 2 * mc.LINE_W - 2 * BORE_CLEAR


def captive_crest_max(hold):
    """Largest crest a chute can carry and still keep its `hold` marble captive (marble_common:
    printed crest = rail - HOLE_SHRINK, and the rider needs SORT_DRIFT of margin over it)."""
    return hold - mc.SORT_DRIFT + mc.HOLE_SHRINK


# ------------------------------------------------------------------ mating-part measurement

def ring_profile(path):
    """Min radius per mesh ring, read off a binary STL. Ring-based (a vase grid shares exact z),
    so the surface between rings interpolates exactly instead of binning -- which matters on a
    45deg cone, where a 1mm bin is 1mm of radius."""
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        d = collections.defaultdict(lambda: 1e30)
        for _ in range(n):
            f.read(12)
            for _ in range(3):
                x, y, z = struct.unpack("<3f", f.read(12))
                k = round(z, 3)
                d[k] = min(d[k], math.hypot(x, y))
            f.read(2)
    zs = sorted(d)
    return zs, [d[z] for z in zs]


def bore_at(zs, rs, z):
    """Narrowest radius of the mating part at height z, linearly interpolated between rings."""
    if z <= zs[0]:
        return rs[0]
    if z >= zs[-1]:
        return rs[-1]
    i = bisect.bisect_left(zs, z)
    z0, z1, r0, r1 = zs[i - 1], zs[i], rs[i - 1], rs[i]
    return r0 if z1 <= z0 else r0 + (r1 - r0) * (z - z0) / (z1 - z0)


def crest_zone(zs, rs, tol=0.01):
    """(top, bottom, radius) of the chute's rail crest: the contiguous run of rings at the
    narrowest radius. The BOTTOM is the number that matters -- it is the last height at which a
    helical crest can still catch the marble, so it is where the guide tube has to reach."""
    lo = min(rs)
    idx = [i for i, r in enumerate(rs) if r <= lo + tol]
    seed = idx[len(idx) // 2]
    a = b = seed
    while a - 1 >= 0 and rs[a - 1] <= lo + tol:
        a -= 1
    while b + 1 < len(rs) and rs[b + 1] <= lo + tol:
        b += 1
    return zs[b], zs[a], lo


# ------------------------------------------------------------------------------ the part

def build_profile(hold, drop, mouth, chute=None, extension=True, tube_len=None, bays=2,
                  parks=1, points=144):
    """The head's (z, r) surface path, bottom-up in PRINT orientation (z=0 on the bed), plus every
    number the report and the gates need. Nothing here is picked: the bore comes from the marbles
    and the two shrink models, the lower tube's length comes from the chute's emitted mesh."""
    tube_d = drop + 2 * BORE_CLEAR + WORST_SHRINK
    bores = {k: f(tube_d) for k, f in BORE_MODELS.items()}
    if min(bores.values()) < drop + 2 * BORE_CLEAR - 1e-6:
        raise SystemExit(f"bore O{min(bores.values()):.2f} does not clear the O{drop:g} marble by "
                         f"{BORE_CLEAR:g}mm per side under every shrink model {bores}")
    if max(bores.values()) >= hold - 0.5:
        raise SystemExit(
            f"bore prints at most O{max(bores.values()):.2f} but the O{hold:g} marble must NOT "
            f"enter it (needs 0.5mm of block, has {hold - max(bores.values()):.2f}). The sizes are "
            f"too close: the gap must exceed {2*BORE_CLEAR + WORST_SHRINK + 0.5:.2f}mm.")

    tr = tube_d / 2
    rb = mouth / 2
    # ---- the park bays: every number below is derived from the two marbles, not chosen ----
    hold_r = hold / 2
    if bays >= 1:
        # REACH: where the parked reject's centre sits. The nearest one has to clear a drop marble
        # coming down the bore, which can itself be BORE_CLEAR off the axis, with both parts
        # printed off nominal (SORT_DRIFT each); every further one queues a marble diameter uphill
        # of it, so the reach is what buys the capacity.
        clear_one = hold_r + drop / 2 + BORE_CLEAR + 2 * mc.SORT_DRIFT
        reach = clear_one
        # the park end is as wide as the sieve rule allows: one HUB_BLOCK of radius short of
        # passing the held marble, so it blocks by exactly the margin the bore itself blocks by
        w_tip = hold_r - HUB_BLOCK
        grade, hub_rise = bay_grade(reach, tr, bays, hold_r, w_tip)
        dip = grade * reach
        # The slot does not stop at the park. MEASURED with it stopping there: a drop marble
        # arriving down the same arm came to rest AGAINST the parked reject, at r=23.2 on the bowl
        # floor just outside the slot, every seed. A trough with something parked in it is a dam.
        # So the slot runs on past the park by the two marbles' radii -- far enough that the spot
        # a drop marble gets held at is OVER THE HOLE, where it falls through instead of stopping
        # -- and its rim RISES again beyond the park at the same rolling grade, so the park stays
        # the low point and rejects still collect there.
        out_grade = math.tan(math.radians(ROLL_GRADE))
        reach_out = reach + hold_r + drop / 2
        # how far the reject's belly sinks below the rim: it rests on an opening tr wide
        seat_drop = hold_r - math.sqrt(max(0.0, hold_r ** 2 - w_tip ** 2))
        prism_h = dip + seat_drop          # the rim must stay a vertical wall under the deepest bay
        h_conv = reach_out / math.tan(math.radians(BAY_LEAN))
        hub = hub_clear(reach, tr, bays, w_tip, reach_out)
        star = [bay_outline_r(2 * math.pi * i / points, reach, tr, bays, w_tip, reach_out)
                for i in range(points)]
        stat = [bay_station(2 * math.pi * i / points, reach, tr, bays, w_tip, reach_out)
                for i in range(points)]
    else:
        clear_one = 0.0
        reach = dip = prism_h = h_conv = grade = hub_rise = seat_drop = 0.0
        reach_out = out_grade = 0.0
        hub = tr
        w_tip = tr
        star = [tr] * points
        stat = [0.0] * points
    # The bowl flares RADIALLY, which is why the slot is short. Measured on a 30mm slot: out there
    # the radial direction is nearly along the slot, so the wall only opens 0.245mm sideways per
    # mm of height, the O16 rode 8.26mm above the rim instead of 5.48 and the seat went flat at
    # x=12 -- the far half of a long slot is not a park. A slot no longer than the clearance it
    # has to buy does not run into it.
    grow = math.tan(math.radians(BOWL_LEAN))
    h_bowl = (rb - tr) / grow
    h_in = (mc.SPIGOT_BASE_R - tr) / math.tan(math.radians(EXIT_LEAN))
    h_flare = (mc.SPIGOT_TIP_R - tr) / math.tan(math.radians(FLARE_LEAN))
    tube_l = TUBE_L_MIN * drop if tube_len is None else tube_len

    fit = None
    if chute is not None:
        zs, rs = ring_profile(chute)
        crest_top, crest_bot, crest_r = crest_zone(zs, rs)
        seat = zs[-1] - mc.COUPLE_L                       # spigot tip = socket bottom
        s = math.tan(math.radians(FLARE_LEAN))
        z_fl = seat - h_flare                             # flare reaches the tube radius here
        flare_min, flare_at, z = 1e9, None, seat
        while z > z_fl:
            c = bore_at(zs, rs, z) - (mc.SPIGOT_TIP_R - s * (seat - z)) - mc.LINE_W
            if c < flare_min:
                flare_min, flare_at = c, z
            z -= 0.05
        z_bot = z_fl                                      # then straight down, as far as it fits
        while (z_bot - 0.05 > zs[0] and z_bot > crest_bot
               and bore_at(zs, rs, z_bot - 0.05) - tr - mc.LINE_W >= FIT_CLEAR):
            z_bot -= 0.05
        n = max(1, int((z_fl - z_bot) / 0.05))
        ext_min = min(bore_at(zs, rs, z_bot + (z_fl - z_bot) * i / n) - tr - mc.LINE_W
                      for i in range(n + 1)) if z_fl > z_bot else FIT_CLEAR
        fit = dict(crest_top=crest_top, crest_bot=crest_bot, crest_r=crest_r, seat=seat,
                   z_fl=z_fl, z_bot=z_bot, flare_min=flare_min, flare_at=flare_at,
                   ext_min=ext_min, unlined=z_bot - crest_bot, chute_top=zs[-1])

    if extension and fit is None:
        raise SystemExit("--chute is required: the lower tube's length is MEASURED off the chute "
                         "it hangs inside, not assumed. Use --no-extension to rebuild v1.")

    def ramp(z0, r0, z1, r1, step=0.5):
        n = max(1, int(round(abs(z1 - z0) / step)))
        return [(z0 + (z1 - z0) * i / n, r0 + (r1 - r0) * i / n) for i in range(1, n + 1)]

    if extension:
        ext_l = fit["z_fl"] - fit["z_bot"]
        seat_local = ext_l + h_flare
        prof = [(0.0, tr)] + ramp(0.0, tr, ext_l, tr, 2.0)
        prof += ramp(ext_l, tr, seat_local, mc.SPIGOT_TIP_R)
    else:
        ext_l, seat_local = 0.0, 0.0
        prof = [(0.0, mc.SPIGOT_TIP_R)]
    prof += [(seat_local + z, r) for z, r in mc.spigot_profile()[1:]]
    z = seat_local + mc.COUPLE_L
    prof += ramp(z, mc.SPIGOT_BASE_R, z + h_in, tr);      z += h_in
    prof += ramp(z, tr, z + tube_l, tr, 2.0);             z += tube_l

    # ---- throat + bowl: the only part of the wall that is not a surface of revolution ----
    z_tube_top = z
    z_conv_top = z_tube_top + h_conv        # bays fully open, prism starts
    z0 = z_conv_top + prism_h               # rim height at the hub
    z_top = z0 + h_bowl

    # Below the throat the slot closes by getting SHORTER, never narrower. Blending radially
    # from the bore to the slot outline instead was measured to pinch it: at half depth the walls
    # came out 9.68mm apart, and a O10 marble rode them and stopped there -- 1 of 9 single pours
    # and a four-marble pile-up in the multi pour, all of them stuck in the cone rather than in
    # the bowl. Anything a marble passes through has to stay at least bore-wide the whole way.
    NU = 24
    conv = []
    for i in range(NU + 1):
        u = i / NU
        conv.append([bay_outline_r(2 * math.pi * j / points, reach * u, tr, bays,
                                   tr + (w_tip - tr) * u, reach_out * u) for j in range(points)])

    def wall_r(k, zz):
        rs = star[k]
        # rim: falls from the apex to the park, then climbs again past it
        sk = stat[k]
        zr = z0 - (grade * sk if sk <= reach else grade * reach - out_grade * (sk - reach))
        if zz <= z_conv_top:
            u = 1.0 if h_conv <= 1e-9 else min(1.0, max(0.0, (zz - z_tube_top) / h_conv))
            g = u * NU
            i0 = min(NU - 1, int(g))
            return conv[i0][k] + (conv[i0 + 1][k] - conv[i0][k]) * (g - i0)
        if zz <= zr:
            return rs
        return rs + (rb - rs) * (zz - zr) / (z_top - zr)

    zs = []
    zz, fine = z_tube_top, z0 + 1.0
    while zz < z_top - 1e-9:
        zz = min(z_top, zz + (0.25 if zz < fine else 0.5))
        zs.append(zz)
    rings = [(zp, [rp] * points) for zp, rp in prof]
    rings += [(zz, [wall_r(k, zz) for k in range(points)]) for zz in zs]

    return dict(prof=prof, rings=rings, tube_d=tube_d, bores=bores, tr=tr, tube_l=tube_l,
                ext_l=ext_l, h_flare=h_flare, h_in=h_in, h_bowl=h_bowl, total=z_top,
                seat_local=seat_local, chamber=h_in + mc.COUPLE_L + h_flare, fit=fit,
                bays=bays, parks=parks, clear_one=clear_one, reach=reach,
                reach_out=reach_out, dip=dip, grade=grade, hub_rise=hub_rise, hub=hub,
                seat_drop=seat_drop, w_tip=w_tip, prism_h=prism_h, h_conv=h_conv, grow=grow,
                z_tube_top=z_tube_top, z_conv_top=z_conv_top, z0=z0, z_top=z_top, points=points)


def emit(path, rings, points):
    mc.write_stl(path, mc.grid_tris(rings, points))
    return mc.verify_stl(path)


def shift_z(src, dst, dz):
    """Write a pure z-translation of an emitted STL. chain_test.mjs seats a head by assuming its
    z=0 IS the spigot tip; this part's z=0 is the bed, so the sim gets a translated copy and the
    printer gets the original. Same triangles, one number moved."""
    with open(src, "rb") as f:
        hdr = f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        rec = f.read()
    out = bytearray()
    for i in range(n):
        r = list(struct.unpack_from("<12fH", rec, i * 50))
        for k in (5, 8, 11):
            r[k] += dz
        out += struct.pack("<12fH", *r)
    with open(dst, "wb") as f:
        f.write(hdr); f.write(struct.pack("<I", n)); f.write(bytes(out))
    return n


def shift_is_pure(src, dst, dz):
    """RE-READ both emitted files and prove dst really is src moved by dz in z and nothing else.
    Counting triangles cannot see a wrong dz, a shifted axis or a scaled copy, and dz is
    load-bearing: chain_test.mjs seats the head by trusting that dst's z=0 IS the spigot tip, so a
    wrong number here silently moves the head against the chute and every sim result with it.
    Returns (n, max |dx|,|dy| error, max |dz - dz_wanted| error, z of the spigot-tip plane in dst)."""
    def recs(p):
        with open(p, "rb") as f:
            f.read(80)
            (n,) = struct.unpack("<I", f.read(4))
            return n, f.read()
    na, a = recs(src)
    nb, b = recs(dst)
    if na != nb:
        return na, 9e9, 9e9, 9e9
    exy = ez = 0.0
    tip_z, tip_r = None, -1.0
    for i in range(na):
        ra = struct.unpack_from("<12fH", a, i * 50)
        rb = struct.unpack_from("<12fH", b, i * 50)
        for k in (3, 6, 9):
            exy = max(exy, abs(rb[k] - ra[k]), abs(rb[k + 1] - ra[k + 1]))
            ez = max(ez, abs((rb[k + 2] - ra[k + 2]) - dz))
            r = math.hypot(rb[k], rb[k + 1])
            if r > tip_r + 1e-6:            # the widest ring is the spigot base; the TIP plane is
                tip_r = r                   # the lowest ring at exactly SPIGOT_TIP_R
    with open(dst, "rb") as f:
        f.read(84)
        lo = 1e30
        for _ in range(na):
            f.read(12)
            for _ in range(3):
                x, y, z = struct.unpack("<3f", f.read(12))
                if abs(math.hypot(x, y) - mc.SPIGOT_TIP_R) < 1e-3:
                    lo = min(lo, z)
            f.read(2)
        tip_z = lo
    return na, exy, ez, tip_z


def straight_runs(path, tol=0.02):
    """Re-read the FILE and find every run of rings at the narrowest radius: this part has two of
    them (the lower tube and the upper tube) and both gates measure them off the mesh."""
    zs, rs = ring_profile(path)
    lo = min(rs)
    runs, cur = [], None
    for z, r in zip(zs, rs):
        if r <= lo + tol:
            cur = [z, z] if cur is None else [cur[0], z]
        elif cur is not None:
            runs.append(tuple(cur)); cur = None
    if cur is not None:
        runs.append(tuple(cur))
    return lo, runs


# ------------------------------------------- where a marble can actually COME TO REST, measured
# The defect this part exists to fix was never a dimension, it was a RESTING PLACE, so the gate
# has to measure resting places -- off the emitted file, by a route the generator never used.

class RestField:
    """Lowest a sphere of radius R can sit on the emitted mesh, as a function of where you hold it.

    rest(x, y) = max over mesh points p within R of the vertical line at (x, y) of
                 p.z + sqrt(R^2 - dxy^2)
    i.e. drop the sphere down that line until something stops it. A marble PARKS at a local
    minimum of this surface, so the whole question "where does the reject end up, and is that on
    top of the hole" is answered by reading it.

    Measured off the file's VERTICES, not its triangles: a sphere could in principle dip a little
    between two of them. On this part the rings are 0.25-0.5 mm apart and the points 0.4-2 mm, so
    that error is bounded by ~(gap/2)^2/(2R) < 0.06 mm; `sag_bound` reports it rather than
    assuming it away."""

    def __init__(self, path, R, z_lo=-1e30):
        self.R = R
        with open(path, "rb") as f:
            f.read(80)
            (n,) = struct.unpack("<I", f.read(4))
            seen = set()
            for _ in range(n):
                f.read(12)
                for _ in range(3):
                    v = struct.unpack("<3f", f.read(12))
                    if v[2] >= z_lo:
                        seen.add((round(v[0], 2), round(v[1], 2), round(v[2], 2)))
                f.read(2)
        self.cell = R
        self.bins = collections.defaultdict(list)
        for x, y, z in seen:
            self.bins[(int(math.floor(x / R)), int(math.floor(y / R)))].append((x, y, z))
        self.n = len(seen)

    def rest(self, x, y):
        R2 = self.R ** 2
        best = None
        cx, cy = int(math.floor(x / self.cell)), int(math.floor(y / self.cell))
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for (px, py, pz) in self.bins.get((cx + i, cy + j), ()):
                    d2 = (px - x) ** 2 + (py - y) ** 2
                    if d2 < R2:
                        h = pz + math.sqrt(R2 - d2)
                        if best is None or h > best:
                            best = h
        return best        # None = nothing in the way: the sphere falls straight through here

    def scan_ray(self, theta, s0, s1, step=0.25):
        out = []
        s = s0
        while s <= s1 + 1e-9:
            out.append((s, self.rest(s * math.cos(theta), s * math.sin(theta))))
            s += step
        return out

    def field_min(self, r_max, dr=0.5, dth=5.0):
        """Lowest resting place anywhere in the head, and where it is. This is where the reject
        ends up."""
        best = (1e30, 0.0, 0.0)
        th = 0.0
        while th < 360.0:
            s = 0.0
            while s <= r_max + 1e-9:
                h = self.rest(s * math.cos(math.radians(th)), s * math.sin(math.radians(th)))
                if h is not None and h < best[0]:
                    best = (h, s, th)
                s += dr
            th += dth
        return best


def layer_offset(path, layer=0.56):
    """The REAL vase-printability number: how far each layer's loop sits from the loop below it,
    measured as curve-to-curve distance off the emitted file, then turned back into a wall lean.

    marble_common.verify_stl measures the lean of each FACET, and a facet joins two rings AT THE
    SAME ANGLE. That is the same thing only while the outline keeps its shape. This throat is a
    capsule whose radius grows with height, and a growing capsule's shoulder -- where the end cap
    meets the flank -- sweeps sideways fast, so same-angle facets measured 88.8 deg on a surface
    that is actually offset a uniform 0.67mm per layer. Slicing does not use facets: it cuts
    horizontal loops and lays one bead along each, so what decides whether the wall stands up is
    how far each loop moved from the one under it. At the kit's 0.56 layer, 55 deg is 0.80mm.

    Returns (max offset mm, the z it happens at, the equivalent lean in deg)."""
    rings = collections.defaultdict(set)
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        for _ in range(n):
            f.read(12)
            for _ in range(3):
                x, y, z = struct.unpack("<3f", f.read(12))
                rings[round(z, 3)].add((round(x, 4), round(y, 4)))
            f.read(2)
    zs = sorted(rings)
    worst, at = 0.0, 0.0
    for za, zb in zip(zs, zs[1:]):
        A, B = list(rings[za]), list(rings[zb])
        if len(A) < 3 or len(B) < 3 or zb - za < 1e-9:
            continue
        for bx, by in B:
            d = min((bx - ax) ** 2 + (by - ay) ** 2 for ax, ay in A) ** 0.5
            d *= layer / (zb - za)               # scale the ring step up to one real layer
            if d > worst:
                worst, at = d, zb
    return worst, at, math.degrees(math.atan2(worst, layer))


def prism_min_radius(path, z_lo, z_hi):
    """Narrowest radius of the emitted wall between two heights = the HUB clearance of the throat,
    because the hub is where the bays meet and the outline comes closest to the axis. Re-read off
    the file, and it is the number that decides whether the held marble drops through the middle."""
    zs, rs = ring_profile(path)
    band = [r for z, r in zip(zs, rs) if z_lo <= z <= z_hi]
    return min(band) if band else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chute", default=None,
                    help="the chute STL this head sits on. The lower tube's length is MEASURED "
                         "off it; without one there is no lower tube.")
    ap.add_argument("--hold", type=float, default=16.0, help="marble that must NOT pass, mm")
    ap.add_argument("--drop", type=float, default=10.0, help="marble that must pass, mm")
    ap.add_argument("--mouth", type=float, default=100.0, help="catch bowl mouth dia mm")
    ap.add_argument("--no-extension", dest="extension", action="store_false",
                    help="rebuild v1: flare straight from the tube out to the coupling. Makes the "
                         "sim chain gate fail, which is the point of having it.")
    ap.add_argument("--tube-len", type=float, default=None, help="override the upper tube, mm")
    ap.add_argument("--parks", type=int, default=1,
                    help="rejected marbles the park has to hold before one is back over the bore. "
                         "Each one costs a marble diameter of reach.")
    ap.add_argument("--bays", type=int, default=2,
                    help="park bays cut off the sieve bore, where a rejected marble goes so it is "
                         "not sitting on the hole. 0 rebuilds the plugging round throat; more than "
                         "the derived maximum widens the hub until the reject drops through it, "
                         "which the transit gate below catches.")
    ap.add_argument("--points", type=int, default=144)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    b = build_profile(a.hold, a.drop, a.mouth, a.chute, a.extension, a.tube_len, a.bays,
                      a.parks, a.points)
    out = a.out or (f"sort_head_{a.hold:g}_{a.drop:g}{'' if a.extension else '_noext'}"
                    f"{'' if a.bays == 2 else f'_b{a.bays}'}.stl")
    v = emit(out, b["rings"], a.points)
    seat_out = out.replace(".stl", "_seat0.stl")
    n_shift = shift_z(out, seat_out, -b["seat_local"])
    n_pure, exy, ez, tip_z = shift_is_pure(out, seat_out, -b["seat_local"])
    meas_r, runs = straight_runs(out)
    f = b["fit"]

    print(f"{out}: {v['tris']} tris | O{a.mouth:g} bowl, sieve bore O{b['tube_d']:.2f} modelled, "
          f"{v['hi'][2]:.0f}mm tall")
    print(f"  bore prints O{b['bores']['half-bead']:.2f} (wall centred on the path) .. "
          f"O{b['bores']['hole-shrink']:.2f} (Creality vase empiric). O{a.drop:g} passes under "
          f"both, O{a.hold:g} enters under neither, so it stays in the bowl.")
    if a.extension:
        print(f"  LOWER TUBE {b['ext_l']:.1f}mm, DERIVED off {os.path.basename(a.chute)}: it hangs "
              f"through the coupling and lines the chute's shaft from z={f['z_fl']:.0f} down to "
              f"z={f['z_bot']:.1f}. The crest that can catch the marble runs z={f['crest_top']:.0f}"
              f"..{f['crest_bot']:.0f}, so {max(0.0, f['unlined']):.2f}mm of it is left unlined.")
    else:
        print(f"  NO LOWER TUBE (v1). Below the upper tube the wall flares straight out to the "
              f"coupling and the marble is on its own from there.")

    # ---- where each marble can come to rest, measured off the emitted file ----
    hold_r, drop_r = a.hold / 2, a.drop / 2
    hub_meas = prism_min_radius(out, b["z_conv_top"] + 0.3, b["z0"] - 0.3) if a.bays else meas_r
    fld = RestField(out, hold_r, z_lo=b["z_tube_top"] - 2 * a.hold)
    park_z, park_s, park_th = fld.field_min(b["reach"] + b["tr"] + 4.0)
    # The reject's resting height walked from directly over the bore out to a park, BOTH ways
    # along the slot. What has to be true is not a slope number, it is that there is nowhere to
    # stop: no step may RISE before the park, or the step before it is a place the marble can
    # settle. The apex over the bore is a maximum, so it is a balance point and not a well; the
    # sim pours are what show nothing balances on it.
    # The blocking zone is everything closer to the axis than clear_one: a marble stopping there
    # is over the hole. Past it, a stopping place IS the park, so the scan is judged only inside
    # the zone that matters. (Past clear_one the profile does ripple by ~0.05mm, which is the
    # 0.25mm ring staircase the tilted rim is meshed with -- it just means the park is a shallow
    # basin from r=13.5 to r=15 rather than a single point, and all of it is clear.)
    zone = b["clear_one"]
    rays = [fld.scan_ray(math.radians(park_th) + k * math.pi, 0.0, max(park_s, zone))
            for k in (0, 1)] if a.bays else [[]]
    steps = [(r[i + 1][1] - r[i][1]) / (r[i + 1][0] - r[i][0]) for r in rays
             for i in range(len(r) - 1)
             if r[i][1] is not None and r[i + 1][1] is not None and r[i + 1][0] <= zone]
    rise_max = max(steps) if steps else 1e9              # >0 inside the zone = a place to stop
    fall_mean = ((rays[0][0][1] - park_z) / park_s) if a.bays and park_s else 0.0
    arms_match = (a.bays < 2 or abs(rays[0][-1][1] - rays[1][-1][1]) < 0.05)
    hub_rest = fld.rest(0.0, 0.0)
    sag = (0.5 / 2) ** 2 / (2 * hold_r)          # worst dip a sphere could take between two rings
    if a.bays:
        print(f"  PARK BAYS {a.bays} x reach {b['reach']:.2f}mm, rim falling {b['dip']:.2f}mm "
              f"(grade {math.degrees(math.atan(b['grade'])):.0f} deg = the {ROLL_GRADE:g} deg the "
              f"kit's gutter rolls at, plus {math.degrees(math.atan(b['hub_rise'])):.0f} deg to "
              f"climb out of the hub). DERIVED: reach = O{a.hold:g}/2 + O{a.drop:g}/2 + "
              f"{BORE_CLEAR:g} bore clear + 2x{mc.SORT_DRIFT:g} drift. MEASURED off the file, the "
              f"O{a.hold:g} rests at r={park_s:.2f} z={park_z:.1f}, not r=0: it is beside the hole, "
              f"not on it.")
    else:
        print(f"  NO PARK BAYS: a plain round throat. The O{a.hold:g} rests at r={park_s:.2f}, "
              f"which is the whole defect.")

    tube_run = max(runs, key=lambda r: r[0])
    tube_meas = tube_run[1] - tube_run[0]
    low_run = min(runs, key=lambda r: r[0])
    ext_meas = (low_run[1] - low_run[0]) if len(runs) > 1 else 0.0
    need_crest = guided_crest_min(a.drop)
    can_drop = max_guided_drop(2 * f["crest_r"]) if f else 0.0

    checks = [
        ("bore measured", abs(2 * meas_r - b["tube_d"]) < 0.05,
         f"emitted narrowest O{2*meas_r:.2f} vs modelled O{b['tube_d']:.2f}"),
        # the park is cut out of ONE side, so the other side of the bore stays a straight wall all
        # the way up to the rim: the emitted run is the tube plus the whole throat
        ("upper tube measured",
         abs(tube_meas - (b["tube_l"] + b["h_conv"] + b["prism_h"])) < 0.6,
         f"emitted straight bore z {tube_run[0]:.1f}..{tube_run[1]:.1f} = {tube_meas:.1f}mm vs "
         f"{b['tube_l']:.1f} tube + {b['h_conv']:.1f} bay cone + {b['prism_h']:.1f} rim wall = "
         f"{b['tube_l'] + b['h_conv'] + b['prism_h']:.1f}mm modelled "
         f"({tube_meas/a.drop:.1f} marble diameters)"),
        ("lower tube measured", abs(ext_meas - b["ext_l"]) < 0.6,
         f"emitted {ext_meas:.1f}mm vs {b['ext_l']:.1f}mm modelled"
         + ("" if a.extension else "  (none, by request)")),
        ("passes the small one", min(b["bores"].values()) - a.drop >= 2 * BORE_CLEAR - 1e-6,
         f"{(min(b['bores'].values()) - a.drop)/2:.2f}mm per side on the tightest shrink model "
         f"(need {BORE_CLEAR:g})"),
        ("blocks the big one", a.hold - max(b["bores"].values()) >= 0.5,
         f"O{a.hold:g} is {a.hold - max(b['bores'].values()):.2f}mm too fat on the loosest "
         f"shrink model"),
        # --- the three that answer "where does the REJECT go", all read off the emitted file ---
        ("reject parks clear of the bore", park_s >= hold_r + drop_r + BORE_CLEAR,
         f"lowest resting place for a O{a.hold:g} anywhere in the head is r={park_s:.2f} "
         f"z={park_z:.1f} (bay at {park_th:.0f} deg); a drop marble coming down the bore needs "
         f"{hold_r + drop_r + BORE_CLEAR:.2f}mm of it. Sphere-vs-vertex sampling, so this is "
         f"+-{sag:.3f}mm"),
        ("nowhere to stop over the bore",
         a.bays >= 1 and rise_max <= 0.02 and arms_match,
         (f"walking a O{a.hold:g} out of the bore, both ways along the slot, its resting height "
          f"NEVER rises anywhere inside the {zone:.2f}mm that would block the bore: worst step "
          f"{rise_max:+.4f}mm/mm (a positive one is a "
          f"place it can settle), mean fall {math.degrees(math.atan(fall_mean)):.1f} deg from "
          f"{hub_rest:.2f} over the axis to {park_z:.2f} at r={park_s:.2f}, and the two arms "
          f"agree to {abs(rays[0][-1][1] - rays[1][-1][1]) if a.bays >= 2 else 0.0:.3f}mm"
          if a.bays else "round throat by request: the bore IS the only seat")),
        ("hub blocks the reject", hub_meas <= hold_r - HUB_BLOCK,
         f"throat hub measures O{2*hub_meas:.2f} off the file, and O{a.hold:g} needs O{a.hold:g} "
         f"to pass: {a.hold - 2*hub_meas:.2f}mm of block (need {2*HUB_BLOCK:g}). Bays meeting at "
         f"the axis widen the hub as tr/sin(pi/N), so at most {max_bays(b['tr'], hold_r)} of them "
         f"fit before the reject drops straight through the middle"),
        ("hub still passes the drop marble", hub_meas >= drop_r + BORE_CLEAR - 1e-6,
         f"hub O{2*hub_meas:.2f} vs O{a.drop:g} + 2x{BORE_CLEAR:g} needed"),
        ("vase printable", v["max_lean"] <= 55.0,
         f"max wall lean {v['max_lean']:.1f} deg (flare {FLARE_LEAN:g}, bowl {BOWL_LEAN:g}, "
         f"exit cone {EXIT_LEAN:g})"),
        ("bed fit", a.mouth <= 340 and v["hi"][2] <= 340,
         f"O{a.mouth:g} x {v['hi'][2]:.0f}mm tall vs a 340 cube"),
        # MEASURED off both files, not counted: same triangles, zero XY movement, the z step is
        # the one asked for, and the spigot-tip plane really lands on z=0 (chain_test.mjs's rule)
        ("sim copy is a pure translation",
         n_shift == v["tris"] and n_pure == v["tris"] and exy <= 1e-4 and ez <= 1e-3
         and abs(tip_z) <= 1e-3,
         f"{seat_out}: {n_shift} triangles, XY moved {exy:.5f}mm (need 0), z step off by "
         f"{ez:.5f}mm from {-b['seat_local']:.2f} (need 0), spigot-tip plane lands at "
         f"z={tip_z:+.4f} (need 0), which is how chain_test.mjs seats a head"),
    ]
    if f:
        checks += [
            ("shaft admits the guide tube", a.drop <= can_drop + 1e-6,
             f"O{a.drop:g} vs O{can_drop:.2f} max for this chute's O{2*f['crest_r']:.2f} crest. "
             f"A guided O{a.drop:g} needs a O{need_crest:.2f} crest; keeping a O{a.hold:g} marble "
             f"captive caps it at O{captive_crest_max(a.hold):.2f}. KNOBS: a drop marble "
             f"<= O{can_drop:.2f}, or a chute crest >= O{need_crest:.2f} (which stops being a "
             f"chute for marbles under O{need_crest + mc.SORT_DRIFT - mc.HOLE_SHRINK:.2f})"),
            # skipped for --no-extension: that build EXISTS to be the known-bad the function gate
            # fails on, so quarantining it here would leave the gate with nothing to fire against
            ("lower tube reaches the last crest", (not a.extension) or f["unlined"] <= 1e-6,
             f"{max(0.0, f['unlined']):.2f}mm of crest left unlined at z={f['crest_bot']:.0f}; "
             f"MEASURED, every mm of it costs sorts (5mm unlined = 1/9, 30mm = 6/9, 0mm = 9/9)"),
            ("head bore <= crest bore", b["tube_d"] <= 2 * f["crest_r"] + 1e-9,
             f"sieve O{b['tube_d']:.2f} vs the chute's crest O{2*f['crest_r']:.2f}"),
            # the flare leaves the spigot tip, where the BOND's own face clearance IS the number,
            # so the floor here is SEAT_CLEAR itself and it is hit exactly: 1e-6 of slack, no more
            ("hangs clear of the chute", f["flare_min"] >= mc.SEAT_CLEAR - 1e-6 and
             (not a.extension or f["ext_min"] >= FIT_CLEAR - 1e-6),
             f"tightest face clearance {f['flare_min']:.2f}mm at chute z={f['flare_at']:.1f} "
             f"(in the coupling cone, where the BOND itself only promises {mc.SEAT_CLEAR:g}), "
             f"{f['ext_min']:.2f}mm along the hanging tube (need {FIT_CLEAR:g})"),
        ]
    ok = True
    for name, good, msg in checks:
        print("  %s %-32s %s" % ("PASS" if good else "FAIL", name, msg))
        ok = ok and good
    if not ok:
        os.replace(out, out + ".FAILED")
        if os.path.exists(seat_out):
            os.replace(seat_out, seat_out + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined")
        raise SystemExit(1)
    print(f"  SELF-VERIFY: PASS  (vase mode, prints lower-tube-down as modelled, no support. It "
          f"stands on a O{b['tube_d']:.0f} footprint for its first {b['ext_l'] + b['h_flare']:.0f}"
          f"mm: brim it, and thread it down the chute before the chute goes on its base.)")
    print("  FUNCTION is NOT proven here. Run sort_head_sweep.py: it pours marbles into this mesh "
          "chained onto the real chute, and it is the check that fails v1.")


if __name__ == "__main__":
    main()
