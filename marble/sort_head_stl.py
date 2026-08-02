#!/usr/bin/env python3
"""SORT HEAD STL -- the piece that makes the sorting chute actually sort.

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

def build_profile(hold, drop, mouth, chute=None, extension=True, tube_len=None):
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
    h_bowl = (rb - tr) / math.tan(math.radians(BOWL_LEAN))
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
    prof += ramp(z, tr, z + h_bowl, rb);                  z += h_bowl

    return dict(prof=prof, tube_d=tube_d, bores=bores, tr=tr, tube_l=tube_l, ext_l=ext_l,
                h_flare=h_flare, h_in=h_in, h_bowl=h_bowl, total=z, seat_local=seat_local,
                chamber=h_in + mc.COUPLE_L + h_flare, fit=fit)


def emit(path, prof, points):
    mc.write_stl(path, mc.grid_tris(mc.rev_rings(prof, points), points))
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
    ap.add_argument("--points", type=int, default=144)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    b = build_profile(a.hold, a.drop, a.mouth, a.chute, a.extension, a.tube_len)
    out = a.out or f"sort_head_{a.hold:g}_{a.drop:g}{'' if a.extension else '_noext'}.stl"
    v = emit(out, b["prof"], a.points)
    seat_out = out.replace(".stl", "_seat0.stl")
    n_shift = shift_z(out, seat_out, -b["seat_local"])
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

    tube_run = max(runs, key=lambda r: r[0])
    tube_meas = tube_run[1] - tube_run[0]
    low_run = min(runs, key=lambda r: r[0])
    ext_meas = (low_run[1] - low_run[0]) if len(runs) > 1 else 0.0
    need_crest = guided_crest_min(a.drop)
    can_drop = max_guided_drop(2 * f["crest_r"]) if f else 0.0

    checks = [
        ("bore measured", abs(2 * meas_r - b["tube_d"]) < 0.05,
         f"emitted narrowest O{2*meas_r:.2f} vs modelled O{b['tube_d']:.2f}"),
        ("upper tube measured", abs(tube_meas - b["tube_l"]) < 0.6,
         f"emitted straight bore z {tube_run[0]:.1f}..{tube_run[1]:.1f} = {tube_meas:.1f}mm vs "
         f"{b['tube_l']:.1f}mm modelled ({tube_meas/a.drop:.1f} marble diameters)"),
        ("lower tube measured", abs(ext_meas - b["ext_l"]) < 0.6,
         f"emitted {ext_meas:.1f}mm vs {b['ext_l']:.1f}mm modelled"
         + ("" if a.extension else "  (none, by request)")),
        ("passes the small one", min(b["bores"].values()) - a.drop >= 2 * BORE_CLEAR - 1e-6,
         f"{(min(b['bores'].values()) - a.drop)/2:.2f}mm per side on the tightest shrink model "
         f"(need {BORE_CLEAR:g})"),
        ("blocks the big one", a.hold - max(b["bores"].values()) >= 0.5,
         f"O{a.hold:g} is {a.hold - max(b['bores'].values()):.2f}mm too fat on the loosest "
         f"shrink model"),
        ("vase printable", v["max_lean"] <= 55.0,
         f"max wall lean {v['max_lean']:.1f} deg (flare {FLARE_LEAN:g}, bowl {BOWL_LEAN:g}, "
         f"exit cone {EXIT_LEAN:g})"),
        ("bed fit", a.mouth <= 340 and v["hi"][2] <= 340,
         f"O{a.mouth:g} x {v['hi'][2]:.0f}mm tall vs a 340 cube"),
        ("sim copy is a pure translation", n_shift == v["tris"],
         f"{seat_out}: {n_shift} triangles shifted {-b['seat_local']:.2f}mm so its z=0 is the "
         f"spigot tip, which is how chain_test.mjs seats a head"),
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
