#!/usr/bin/env python3
"""BUCKET SECTOR COUPON — a short arc of the REAL bucket wall, printed three times at three wrap
angles, with a different bore on every post, so one plate answers both blocking questions at once.

  Oleg, 2026-08-06, on a coupon that tested neither: "We need to test outer layer overlap with base
  and holes fitting. Think what you doing before printing"
  and, holding the printed bucket: "you need to merge the net and outer wall print in many places,
  it cant be separate closly aligned pieces"
  and: "stick holes are too narrow and dos not have enough to click lock a stick"

WHAT THIS IS, AND WHY IT IS NOT A TEST PLATE. The first version of this coupon was a flat plate of
isolated C-channel stubs. It would have measured a bore and told him NOTHING about the two joins he
actually asked about, because a stub standing alone has no net crossing to merge with and no floor
to bond to. So this is a SECTOR OF THE ACTUAL PART: posts on the real 341.5 mm pitch circle at the
real angular pitch, with the real crossings between them, the real merge laps, and a floor under
them -- just 5 posts of the 28 instead of the whole ring.

THE GEOMETRY IS IMPORTED, NOT REIMPLEMENTED. tower_arc, merge_arc, seam_point, arc_segs, dip and
air_span all come from bucket_towers.py, and the per-layer ordering below is the same one build()
uses: arrive at the TRAILING tip, walk CCW through the post's OUTWARD face, lap, cross, lap. A
coupon that re-derived any of that would be testing a part this project does not print. What is
genuinely new here is only the orchestration build() cannot express: an OPEN chain instead of a
closed ring, and a DIFFERENT BORE ON EVERY POST.

WHAT IT ANSWERS

  1  DOES THE NET MERGE INTO THE WALL? Every crossing is lapped back along both posts' own arcs for
     --merge-mm of arc length (bucket_towers.merge_arc, added 2026-08-06). Before that the strand
     departed tangentially at a single point and the wall and net were two structures touching
     along one bead-wide seam. Grab the net between two posts and pull: it should tear the wall
     before it peels off it.

  2  DOES THE WALL BOND TO THE BASE? The floor layers carry the real generator's own floor-layer
     crossing -- a subdivided full-flow RIM tip to tip, kind "R" -- plus a lattice strip inboard
     whose outer edge is placed to just touch the post feet without entering the bore. Try to snap
     a post off its floor.

  3  WHAT BORE ACCEPTS THE STICK, AND WHAT WRAP CLICK-LOCKS IT? Each post in a sector has a
     different --bore-allow, printed as a number beside it.

THE SHRINK CONSTANT IS THE SUSPECT AND THIS PLATE REPLACES IT. Bore has been guessed twice and been
wrong twice, both times off a 0.25 mm shrink calibrated on a 4 mm METAL-SHAFT hole and reused for
bamboo. guides/fit-and-assembly-empirics.md records that same reuse across a size being 0.45 mm too
tight and condemning ~21 parts. It also records the one bamboo fit that WORKED: 6.35 mm nominal
sticks measuring 5.8-6.2 held in a 7.0 mm bore, i.e. +0.65 mm over nominal. Scaled to a 3.175 mm
stick that is --bore-allow near 0.90. What was shipped and rejected was 0.40. So the sweep runs
0.55 to 1.05 and the rejected value sits BELOW the bottom of it.

WHY THESE WRAP ANGLES. mouth = (bore + bead) * sin((360 - wrap)/2) - bead. The rejected part ran
--wrap-deg 220, which models a 3.310 mm mouth against a 3.175 mm stick: THE OPENING WAS WIDER THAN
THE STICK BEFORE ANY SHRINK, so nothing could ever have clicked past it. 210 and 240 are no better
at the old bore. Over THIS bore sweep the three wraps here put the fifteen modelled mouths on both
sides of the stick with the interesting zone densely covered, and gate 4 refuses any wrap set that
does not.

Usage:  python3 bucket_sector.py
        python3 validate.py out/bucket_sector_*.gcode
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import bucket_towers as bt          # geometry: tower_arc, merge_arc, seam_point, arc_segs, dip
import bucket_latch as latch        # line_pts — the same subdivider the real floor rim uses

A_FIL = machine.A_FIL
SHRINK_SUSPECT = 0.25               # the constant under test; see the header

SEG_G = {
    'a': (0.0, 1.0, 1.0, 1.0), 'b': (1.0, 0.5, 1.0, 1.0), 'c': (1.0, 0.0, 1.0, 0.5),
    'd': (0.0, 0.0, 1.0, 0.0), 'e': (0.0, 0.0, 0.0, 0.5), 'f': (0.0, 0.5, 0.0, 1.0),
    'g': (0.0, 0.5, 1.0, 0.5), 'h': (0.5, 0.0, 0.5, 1.0),
}
# '1' is a CENTRE bar, not the seven-segment right-edge pair: a right-hung '1' draws half a glyph
# width off the number's centre, and on a plate whose whole interface is "say the number back" a
# numeral leaning at the wrong post is the one defect that wastes the entire print.
DIGIT = {'0': 'abcdef', '1': 'h', '2': 'abged', '3': 'abgcd', '4': 'fgbc',
         '5': 'afgcd', '6': 'afgedc', '7': 'abc', '8': 'abcdefg', '9': 'abcdfg'}


def mouth_of(bore_d, wrap_deg, bw):
    """Clear opening between the lips. Same expression as bucket_towers' own mouth arithmetic."""
    return (bore_d + bw) * math.sin(math.radians((360.0 - wrap_deg) / 2.0)) - bw


def glyph_segments(label, cx, y_bot, gw, gh, gap):
    """Strokes of `label` with its INK centred on cx -- nobody reads a box, and '1' is a bare bar."""
    out = []
    for k, ch in enumerate(label):
        gx = k * (gw + gap)
        for s in DIGIT[ch]:
            u0, v0, u1, v1 = SEG_G[s]
            out.append(((gx + u0 * gw, y_bot + v0 * gh), (gx + u1 * gw, y_bot + v1 * gh)))
    xs = [p[0] for sgm in out for p in sgm]
    dx = cx - (min(xs) + max(xs)) / 2.0
    return [((p[0] + dx, p[1]), (q[0] + dx, q[1])) for p, q in out]


def strip_path(cx, cy, a_lo, a_hi, r_in, r_out, pitch, parity, seg):
    """The floor lattice under one sector, as ONE continuous serpentine.

    TWO DIRECTIONS ON ALTERNATE LAYERS, which is what bucket_latch does and what makes a floor a
    latch instead of a stack of parallel lines: parity 0 lays radial ribs, parity 1 lays concentric
    arcs, so consecutive layers cross at right angles and lock.

    The OUTER radius is not a free choice -- see fit_floor() -- it stops exactly where the bamboo's
    volume begins, so the lattice touches the post feet and nothing reaches into the bore."""
    pts = []
    if parity == 0:
        n = max(2, int(math.ceil((a_hi - a_lo) * r_out / pitch)) + 1)
        for i in range(n):
            a = a_lo + (a_hi - a_lo) * i / (n - 1)
            r0, r1 = (r_in, r_out) if i % 2 == 0 else (r_out, r_in)
            p0 = (cx + r0 * math.cos(a), cy + r0 * math.sin(a))
            p1 = (cx + r1 * math.cos(a), cy + r1 * math.sin(a))
            if pts:
                pts += latch.line_pts(pts[-1], p0, seg)
            else:
                pts.append(p0)
            pts += latch.line_pts(p0, p1, seg)
    else:
        n = max(2, int(math.ceil((r_out - r_in) / pitch)) + 1)
        for i in range(n):
            r = r_in + (r_out - r_in) * i / (n - 1)
            b0, b1 = (a_lo, a_hi) if i % 2 == 0 else (a_hi, a_lo)
            p0 = (cx + r * math.cos(b0), cy + r * math.sin(b0))
            if pts:
                pts += latch.line_pts(pts[-1], p0, seg)
            else:
                pts.append(p0)
            pts += latch.arc_to(cx, cy, r, b0, b1, seg)
    return pts


def build_sector(cx, cy, posts, stagger, half_rad, n_lay, n_floor, bridges,
                 merge_mm, strip, fwd):
    """Every layer of ONE sector as {pts, kind}, in bucket_towers.build()'s exact ordering.

    THE ONLY TWO DEPARTURES FROM build(), both forced and both stated:
      * OPEN CHAIN. build() closes the ring with `nxt = (k+1) % n`; a sector has no post after the
        last one, so the chain simply ends. There is no crossing back across the missing 300
        degrees, which would be a 300 mm strand through thin air.
      * PER-POST RADIUS. build() takes one r_t for the whole ring because the real part has one
        bore. Here every post has its own, which is the entire point of the coupon, so r_t, the
        tips and the arc segmentation are all indexed by post.
    `fwd` walks the chain backwards on alternate layers, so the last point of one layer IS the first
    point of the next and no travel is needed inside a sector -- the same handoff build() gets for
    free from closing its ring."""
    n = len(posts)
    order = list(range(n)) if fwd else list(range(n))[::-1]
    layers = []
    for li in range(n_lay):
        is_floor = li < n_floor
        cross = "B" if li in bridges else ("R" if is_floor else "T")
        pts, kind = [], []
        if is_floor:
            sp = strip(li % 2)
            if not fwd:
                sp = sp[::-1]
            pts = list(sp)
            kind = ["E"] * (len(sp) - 1)
        for idx, k in enumerate(order):
            c, r_t, phi, narc = posts[k]["c"], posts[k]["r_t"], posts[k]["phi"], posts[k]["narc"]
            # THE HEAD ALWAYS WALKS THE POST'S OUTWARD FACE, in both directions of travel. Forward
            # it enters at the trailing tip and leaves at the leading one; backward it enters at the
            # leading tip and leaves at the trailing one. Same material, same face, opposite hand.
            a_in = phi + stagger + (-half_rad if fwd else half_rad)
            span = (2 * half_rad) if fwd else (-2 * half_rad)
            p_in = bt.seam_point(c, phi, r_t, stagger - half_rad if fwd else stagger + half_rad)
            p_out = bt.seam_point(c, phi, r_t, stagger + half_rad if fwd else stagger - half_rad)
            if not pts:
                pts = [p_in]
            else:
                seg_pts = latch.line_pts(pts[-1], p_in, bt.SEG)
                pts += seg_pts
                kind += ["R" if is_floor else "E"] * len(seg_pts)
            loop = bt.tower_arc(c, r_t, a_in, span, narc, p_out)
            pts += loop
            kind += ["E"] * len(loop)
            if idx == n - 1:
                break                                  # OPEN CHAIN: nothing follows the last post
            nk = order[idx + 1]
            nc, nr, nphi = posts[nk]["c"], posts[nk]["r_t"], posts[nk]["phi"]
            n_in = bt.seam_point(nc, nphi, nr, stagger - half_rad if fwd else stagger + half_rad)
            if cross == "R":
                seg_pts = latch.line_pts(pts[-1], n_in, bt.SEG)
                pts += seg_pts
                kind += ["R"] * len(seg_pts)
            else:
                step = 2.0 * half_rad / narc
                out = bt.merge_arc(c, r_t, a_in + span, -1 if fwd else +1, merge_mm, step)
                if out:
                    lap = out + out[-2::-1] + [p_out]
                    pts += lap
                    kind += ["M"] * len(lap)
                pts.append(n_in)
                kind.append(cross)
                nstep = 2.0 * half_rad / posts[nk]["narc"]
                a_n = nphi + stagger + (-half_rad if fwd else half_rad)
                out = bt.merge_arc(nc, nr, a_n, +1 if fwd else -1, merge_mm, nstep)
                if out:
                    lap = out + out[-2::-1] + [n_in]
                    pts += lap
                    kind += ["M"] * len(lap)
        layers.append({"pts": pts, "kind": kind, "mult": bridges.get(li),
                       "floor": is_floor})
    return layers


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--dia", type=float, default=341.5,
                    help="the REAL bucket pitch circle, mm. The coupon prints a sector of THIS "
                         "circle, so the crossing chord and the tangency angles are the part's own.")
    ap.add_argument("--n-ring", type=int, default=28,
                    help="how many posts the FULL ring has. Only the angular pitch is taken from "
                         "it; the coupon prints --n-post of them. 28 on a 341.5 circle is the real "
                         "part's spacing, 38.3mm between post centres.")
    ap.add_argument("--n-post", type=int, default=5, help="posts per sector")
    ap.add_argument("--stick-d", type=float, default=3.175,
                    help="1/8 inch NOMINAL, and nominal is what is not trusted: the 6.35mm nominal "
                         "bamboo in the empirics guide measured 5.8-6.2 and varied per stick.")
    ap.add_argument("--bore-allow", default="0.55,0.675,0.80,0.925,1.05",
                    help="mm added to --stick-d for the MODELLED bore, ONE PER POST. The rejected "
                         "part ran 0.40, which is below the bottom of this sweep on purpose; the "
                         "one bamboo fit that ever worked scales to about 0.90, which is inside it.")
    ap.add_argument("--wraps", default="240,255,280",
                    help="one SECTOR per wrap angle. 220 (what was rejected), 210 and 240-at-the-"
                         "old-bore all model a mouth WIDER than the stick, so they could not click "
                         "at all; these three straddle it over this bore sweep.")
    ap.add_argument("--height", type=float, default=25.0, help="total height incl. floor, mm")
    ap.add_argument("--floor-layers", type=int, default=5, help="the real part's default")
    ap.add_argument("--floor-pitch", type=float, default=2.5, help="the real part's default")
    ap.add_argument("--floor-w", type=float, default=16.0,
                    help="radial width of the floor strip under each sector, mm. Not the real "
                         "bucket's 165mm floor disc, and the header says so: it is as much base as "
                         "is needed to test whether the WALL BONDS TO IT.")
    ap.add_argument("--merge-mm", type=float, default=2.0,
                    help="arc length the net laps back along each post at both ends of every "
                         "crossing. bucket_towers.merge_arc; --merge-mm 0 reproduces the "
                         "tangential single-point departure Oleg rejected.")
    ap.add_argument("--merge-flow", type=float, default=0.5,
                    help="flow of the lap, as a fraction of the body bead. The lap is a SECOND pass "
                         "over wall the post already laid, so a full-flow lap would put 2.0x of "
                         "bead in the lip; 0.5 lands 1.5x, which is the declared overlap.")
    ap.add_argument("--cross-flow", type=float, default=0.25,
                    help="the net strand, as a fraction of the body bead. There is no retraction in "
                         "this project, so this move was never dry -- it oozed, and the web in the "
                         "printed part IS that ooze. Metering it is choosing it.")
    ap.add_argument("--bridge-every", type=int, default=10, help="0 disables")
    ap.add_argument("--bridge-w-mult", type=float, default=2.0)
    ap.add_argument("--h1", type=float, default=machine.PRESS_HARD)
    ap.add_argument("--w1", type=float, default=2.00)
    ap.add_argument("--speed", type=float, default=machine.DEFAULT_SPEED)
    ap.add_argument("--speed1", type=float, default=25.0)
    ap.add_argument("--fan", type=float, default=1.0)
    ap.add_argument("--digit-layers", type=int, default=3)
    ap.add_argument("--glyph", default="6.0x9.0")
    ap.add_argument("--gap-mm", type=float, default=8.0, help="clear gap between sectors, mm")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    material = a.material or machine.LOADED[a.printer]
    temp = machine.MATERIAL_TEMP[material]
    bed = machine.bed_for(material, a.printer)
    bedx, bedy = machine.BED[a.printer]
    press, lh, bw = machine.PRESS_HARD, machine.SLICER_LAYER_H, machine.SLICER_LINE_W
    gw, gh = (float(v) for v in a.glyph.lower().split("x"))
    ggap = gw * 0.33

    allows = [float(s) for s in a.bore_allow.split(",") if s.strip()]
    wraps = [float(s) for s in a.wraps.split(",") if s.strip()]
    if len(allows) != a.n_post:
        ap.error(f"--bore-allow has {len(allows)} values but --n-post is {a.n_post}; one bore per "
                 f"post is the whole design")

    # ------------------------------------------------------------------------- GATES BEFORE EMIT
    for nm, v in (("--speed", a.speed), ("--speed1", a.speed1)):
        if v > machine.MAX_SPEED + 1e-9:
            sys.exit(f"REFUSING TO EMIT: {nm} {v:g} is above the {machine.MAX_SPEED:g} mm/s north "
                     f"star, which is a ceiling. Slower is legitimate; faster is not.")
    zerr = machine.ZERR.get(a.printer)
    if zerr is None:
        sys.exit(f"REFUSING TO EMIT: no measured Z-zero error for {a.printer!r} "
                 f"(machine.ZERR has {sorted(machine.ZERR)}). Measure it with zladder.py first.")
    zoff = machine.zoff_for(a.h1, zerr)
    if not any(abs(a.h1 - h) <= 0.005 and abs(a.w1 - w) <= 0.05
               for h, w in machine.PROVEN_LAYER1.get(a.printer, [])):
        sys.exit(f"REFUSING TO EMIT: first layer {a.h1:g}x{a.w1:g} is not in {a.printer}'s proven "
                 f"set {machine.PROVEN_LAYER1.get(a.printer, [])}. This coupon measures a bore and "
                 f"two joins; it must not also be an experiment in adhesion.")
    if a.floor_layers < 1:
        sys.exit("REFUSING TO EMIT: --floor-layers 0 removes the base, and whether the wall bonds "
                 "to the base is half of what this coupon exists to answer.")

    cells = []                       # (n, sector, wrap, allow, bore, mouth)
    for s, wd in enumerate(wraps):
        if not (0.0 < wd <= 360.0):
            sys.exit(f"REFUSING TO EMIT: --wraps contains {wd:g}, not in (0, 360].")
        for k, al in enumerate(allows):
            b = a.stick_d + al
            cells.append((len(cells) + 1, s, wd, al, b, mouth_of(b, wd, bw)))
    tight = [c for c in cells if c[5] <= 0.2]
    if tight:
        sys.exit("REFUSING TO EMIT: these posts model a mouth of 0.2mm or less -- the lips close on "
                 "each other and there is no opening to press a stick through:\n  " +
                 "\n  ".join(f"bore {c[4]:.3f} wrap {c[2]:g} -> mouth {c[5]:+.3f}" for c in tight))
    # gate 4  THE SWEEP MUST BRACKET BY MORE THAN THE QUANTITY IT MEASURES. Crossing the stick
    # diameter once is not enough. --wrap-deg 220 (rejected) models every mouth WIDER than the
    # stick; 210/240 at the old bore cross it by 0.167mm on one cell of twelve, the same razor
    # margin as the part that did not click. The shrink is unknown by at least its own suspect
    # value, so the mouths must reach a full SHRINK_SUSPECT past the stick on BOTH sides.
    mn, mx = min(c[5] for c in cells), max(c[5] for c in cells)
    lo_need, hi_need = a.stick_d - SHRINK_SUSPECT, a.stick_d + SHRINK_SUSPECT
    if mn > lo_need or mx < hi_need:
        sys.exit(f"REFUSING TO EMIT: modelled mouths run {mn:.3f}..{mx:.3f}mm against a "
                 f"{a.stick_d:g}mm stick. The sweep must reach {lo_need:.3f} at the tight end and "
                 f"{hi_need:.3f} at the loose end -- this one "
                 f"{'never gets tight enough' if mn > lo_need else ''}"
                 f"{' and ' if mn > lo_need and mx < hi_need else ''}"
                 f"{'never gets loose enough' if mx < hi_need else ''}. mouth = (bore + {bw:g}) * "
                 f"sin((360 - wrap)/2) - {bw:g}: a BIGGER wrap gives a SMALLER mouth.")

    # ------------------------------------------------------------------------------- GEOMETRY
    R = a.dia / 2.0
    dphi = 2 * math.pi / a.n_ring                  # the REAL angular pitch
    n_lay = int(round((a.height - press) / lh)) + 1
    if n_lay <= a.floor_layers + 2:
        sys.exit(f"REFUSING TO EMIT: --height {a.height:g} gives {n_lay} layers against "
                 f"{a.floor_layers} floor layers -- there would be no wall to test.")
    top_z = press + (n_lay - 1) * lh
    bridges = {}
    if a.bridge_every > 0:
        for li in range(a.floor_layers, n_lay):
            if (li - a.floor_layers) % a.bridge_every == 0 and li != a.floor_layers:
                bridges[li] = a.bridge_w_mult
    bridges[n_lay - 1] = a.bridge_w_mult           # the top rim is always a bridge

    sectors = []
    for s, wd in enumerate(wraps):
        half_rad = math.radians(wd) / 2.0
        posts = []
        for k, al in enumerate(allows):
            bore = a.stick_d + al
            tower_d = bore + 2.0 * bw
            if tower_d < 2.0 * bw - 1e-9:
                sys.exit(f"REFUSING TO EMIT: tower {tower_d:g} is under the {2*bw:.2f}mm floor.")
            r_t = (tower_d - bw) / 2.0
            nseg = max(bt.MIN_TOWER_SEGS, int(math.ceil(2 * math.pi * r_t / bt.SEG)))
            phi = math.pi / 2.0 + (k - (a.n_post - 1) / 2.0) * dphi
            posts.append({"c": (R * math.cos(phi), R * math.sin(phi)), "r_t": r_t, "phi": phi,
                          "narc": bt.arc_segs(nseg, wd), "bore": bore, "allow": al})
        sectors.append({"wrap": wd, "half_rad": half_rad, "posts": posts})

    # THE STAGGER IS COMPUTED ON THE FULL RING, WHICH IS WHAT THE REAL PART DOES.
    #
    # This was got wrong first, and the way it failed is worth keeping: seam_window closes the ring
    # with `j = (k + 1) % n`, so handing it only the sector's five posts made it test a wrap-around
    # chord from the last post back to the first -- a 148mm strand straight through the three posts
    # in between. It refused every stagger and reported "no stagger lets the head cross", which
    # reads exactly like a hard geometric limit at wrap 240 and is not one.
    #
    # Feeding it all 28 posts fixes it AND is the more faithful thing: the coupon then crosses at
    # the SAME seam offset the 341.5mm bucket crosses at, rather than at one optimised for a
    # five-post arc that does not exist. A window computed for a part you are not printing is the
    # assumption this project keeps being bitten by.
    r_probe = max(p["r_t"] for sec in sectors for p in sec["posts"])
    ring_phis = [k * dphi for k in range(a.n_ring)]
    ring_cs = [(R * math.cos(p), R * math.sin(p)) for p in ring_phis]
    for sec in sectors:
        offs = bt.seam_window(ring_cs, ring_phis, r_probe, sec["wrap"] / 2.0)
        win_c, win_w = bt.widest_run(offs)
        if win_c is None:
            sys.exit(f"REFUSING TO EMIT: on the FULL {a.n_ring}-post ring there is no stagger at "
                     f"which a wrap-{sec['wrap']:g} post lets the crossing chord clear both walls. "
                     f"That is a real limit of the part, not of the coupon: at this wrap the tips "
                     f"reach so far around that every flat crossing would plough a post. The wall "
                     f"cannot have both this mouth and a flat net.")
        sec["stagger"] = math.radians(win_c)
        sec["win_w"] = win_w

    # EVERY CHORD RE-TESTED AGAINST ITS OWN TWO POSTS. dip() returns how far a segment passes
    # INSIDE a circle; 0.0 means it clears. This is gate 3 of the real generator, applied per pair
    # because the pairs are no longer identical.
    worst_dip = 0.0
    for sec in sectors:
        hr, st = sec["half_rad"], sec["stagger"]
        for k in range(len(sec["posts"]) - 1):
            p, q = sec["posts"][k], sec["posts"][k + 1]
            e = bt.seam_point(p["c"], p["phi"], p["r_t"], st + hr)
            t = bt.seam_point(q["c"], q["phi"], q["r_t"], st - hr)
            worst_dip = max(worst_dip, bt.dip(e, t, p["c"], p["r_t"]),
                            bt.dip(e, t, q["c"], q["r_t"]))
    if worst_dip > 1e-9:
        sys.exit(f"REFUSING TO EMIT: a crossing chord passes {worst_dip:.4f}mm INSIDE a post wall. "
                 f"The head would plough the post it just printed.")

    # THE FLOOR STRIP'S OUTER RADIUS IS DERIVED, NOT CHOSEN -- the same inequality bucket_towers'
    # floor_check enforces on the latch disc. The bamboo's volume begins at R - bore/2, so the
    # lattice may reach out to exactly there and no further: its bead's outer edge touches the post
    # feet and nothing intrudes into the space the stick has to occupy.
    bore_r_max = max(p["bore"] for sec in sectors for p in sec["posts"]) / 2.0
    r_out = R - bore_r_max - bw / 2.0
    r_in = r_out - a.floor_w
    if r_in <= 0:
        sys.exit(f"REFUSING TO EMIT: --floor-w {a.floor_w:g} is wider than the ring radius.")

    # --------------------------------------------------------------------------- PLACE ON BED
    # Built about a ring centre at the origin, then translated so the whole plate is centred. The
    # ring CENTRE lands off the bed by design -- it is 170mm from an arc only 35mm deep, and nothing
    # is ever printed there.
    span = (a.n_post - 1) * dphi
    a_lo, a_hi = math.pi / 2.0 - span / 2.0 - dphi * 0.30, math.pi / 2.0 + span / 2.0 + dphi * 0.30
    def sector_extent(sec):
        ys = [p["c"][1] for p in sec["posts"]]
        rmax = max(p["r_t"] for p in sec["posts"]) + bw / 2.0
        y_hi = max(ys) + rmax
        y_lo = min(r_in * math.sin(a_lo), r_in * math.sin(a_hi)) - gh - 6.0
        xs = [p["c"][0] for p in sec["posts"]]
        return (min(xs) - rmax, max(xs) + rmax, y_lo, y_hi)
    ext = [sector_extent(s) for s in sectors]
    band_h = [e[3] - e[2] for e in ext]
    total_h = sum(band_h) + a.gap_mm * (len(sectors) - 1)
    total_w = max(e[1] - e[0] for e in ext)
    if total_w > bedx - 10 or total_h > bedy - 10:
        sys.exit(f"REFUSING TO EMIT: the plate needs {total_w:.0f}x{total_h:.0f}mm and the "
                 f"{a.printer} bed is {bedx:g}x{bedy:g}. Drop a wrap or a post.")
    y_cursor = (bedy - total_h) / 2.0
    for i, sec in enumerate(sectors):
        e = ext[i]
        sec["ox"] = bedx / 2.0 - (e[0] + e[1]) / 2.0
        sec["oy"] = y_cursor - e[2]
        y_cursor += band_h[i] + a.gap_mm

    # ---------------------------------------------------------------------------- BUILD LAYERS
    for sec in sectors:
        ox, oy = sec["ox"], sec["oy"]
        posts = [dict(p, c=(p["c"][0] + ox, p["c"][1] + oy)) for p in sec["posts"]]
        sec["posts_bed"] = posts
        cxr, cyr = ox, oy                      # ring centre, translated
        sec["ring"] = (cxr, cyr)
        strip = lambda parity, _c=(cxr, cyr): strip_path(_c[0], _c[1], a_lo, a_hi, r_in, r_out,
                                                         a.floor_pitch, parity, bt.SEG)
        sec["layers"] = build_sector(cxr, cyr, posts, sec["stagger"], sec["half_rad"],
                                     n_lay, a.floor_layers, bridges, a.merge_mm, strip, True)
        sec["layers_rev"] = build_sector(cxr, cyr, posts, sec["stagger"], sec["half_rad"],
                                         n_lay, a.floor_layers, bridges, a.merge_mm, strip, False)

    # AIR SPAN, MEASURED OFF THIS COUPON'S OWN CHORDS and reported against the only span this
    # project has actually proven. The real ring already spans more than that; the coupon inherits
    # it rather than quietly printing an easier part.
    air = 0.0
    for sec in sectors:
        hr, st = sec["half_rad"], sec["stagger"]
        ps = sec["posts_bed"]
        for k in range(len(ps) - 1):
            p, q = ps[k], ps[k + 1]
            e = bt.seam_point(p["c"], p["phi"], p["r_t"], st + hr)
            t = bt.seam_point(q["c"], q["phi"], q["r_t"], st - hr)
            air = max(air, bt.air_span(e, t, p["c"], q["c"], max(p["r_t"], q["r_t"]), bw))

    # ------------------------------------------------------------------------------- EMISSION
    e_body = bw * lh / A_FIL
    e_l1 = machine.layer1_rate(a.w1, a.h1)
    mm2_body = bw * lh
    flow = mm2_body * a.speed
    f_b, f_1 = round(a.speed * 60), round(a.speed1 * 60)
    travel_f = round(machine.MACHINE_MAX_SPEED * 60)
    fan1 = machine.fan_first_layer(material)
    fan2 = max(0.0, min(1.0, a.fan))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.out,
                       f"bucket_sector_{a.printer}_{material}_d{a.dia:g}_n{a.n_post}"
                       f"_w{'-'.join(f'{w:g}' for w in wraps)}"
                       f"_ba{min(allows):g}-{max(allows):g}_h{a.height:g}_m{a.merge_mm:g}.gcode")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    L = []
    w = L.append

    w(f"; BUCKET SECTOR COUPON — {len(sectors)} sectors x {a.n_post} posts of the REAL "
      f"{a.dia:g}mm ring, {a.height:g}mm tall")
    w(f"; PRINTER={a.printer}")
    w(f"; MATERIAL={material}")
    w(f"; LAYER_H={lh:g}")
    w(f"; SPEED={a.speed:.4f}")
    w(f"; SPEED_LAYER1={a.speed1:.4f}")
    w(f"; SPEED_CROSS={a.speed:.4f}")
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={press:g}")
    w(f"; LAYER1_WIDTH={a.w1:.2f}mm landed ({a.w1 / (mm2_body / press):.2f}x the body's own flow "
      f"pressed into the {press:g} gap)")
    w(f"; PRINT_TEMP={temp}")
    _mm2s = sorted({round(m * bw * lh, 4) for m in bridges.values()})
    w(f"; BRIDGE_MM2={','.join(f'{v:.4f}' for v in _mm2s)}")
    _cap = machine.flow_cap(material, a.printer)
    w(f"; FLOW_DERATE=this coupon IS the bucket wall, so it carries the bucket's derate: a "
      f"{machine.NOZZLE:g} nozzle laying the slicer's {bw:g}x{lh:g} bead at {a.speed:g} mm/s "
      f"delivers {flow:.2f} mm3/s against the {_cap:g} cap. Reaching the cap would mean WIDENING "
      f"the bead, and a C-channel's wall thickness IS its bead — a wider bead moves the bore and "
      f"the mouth, which are two of the three things being measured here.")
    w(";")
    w("; ---------------- WHAT THIS IS ----------------")
    w(f"; A SECTOR OF THE ACTUAL PART, not a test plate. {a.n_post} posts of the real {a.n_ring}-post")
    w(f"; ring on the real {a.dia:g}mm pitch circle ({2*math.pi*(a.dia/2)/a.n_ring:.1f}mm between post")
    w(f"; centres), with the real crossings, the real merge laps and a floor under them. The")
    w(f"; geometry is IMPORTED from bucket_towers.py (tower_arc, merge_arc, seam_point, arc_segs,")
    w(f"; dip, air_span, seam_window) — a coupon that re-derived it would test a part we do not print.")
    w(";")
    w("; ---------------- THE THREE QUESTIONS ----------------")
    w(f"; 1 DOES THE NET MERGE INTO THE WALL? Every crossing laps {a.merge_mm:g}mm of ARC back along")
    w(f";   both posts, at {a.merge_flow*100:.0f}% flow on top of the wall's own — so the lip carries")
    w(f";   {1+a.merge_flow:.2f}x of bead, declared, not absorbed quietly. --merge-mm 0 reproduces the")
    w(f";   single-point tangential departure that made the net and wall 'separate closly aligned")
    w(f";   pieces'. PULL THE NET between two posts: it should tear before it peels off the wall.")
    w(f"; 2 DOES THE WALL BOND TO THE BASE? {a.floor_layers} floor layers carry the real generator's own")
    w(f";   floor crossing — a subdivided full-flow RIM tip to tip — plus a {a.floor_w:g}mm lattice strip")
    w(f";   at the real {a.floor_pitch:g}mm pitch, crossed 90deg layer to layer. Its outer radius is DERIVED:")
    w(f";   it stops at {r_out:.2f} where the bamboo's volume begins, so it touches the post feet and")
    w(f";   never enters the bore. TRY TO SNAP A POST OFF ITS FLOOR.")
    w(f"; 3 WHAT BORE AND WHAT WRAP? {len(cells)} posts, each numbered, each a different bore.")
    w(";")
    w("; ---------------- THE CONSTANT UNDER SUSPICION ----------------")
    w(f"; THE {SHRINK_SUSPECT:g}mm SHRINK IS A GUESS AND THIS COUPON REPLACES IT. Calibrated on a 4mm")
    w(f"; METAL-SHAFT hole, reused for bamboo. The last time it was carried across a size like that")
    w(f"; it was 0.45mm too tight and condemned ~21 parts. The one bamboo fit that WORKED: 6.35mm")
    w(f"; nominal sticks measuring 5.8-6.2 held in a 7.0mm bore, +0.65 over nominal, which scales to")
    w(f"; --bore-allow ~0.90 for a 3.175 stick. The REJECTED part ran 0.40. This sweep is")
    w(f"; {min(allows):g}..{max(allows):g}, so the rejected value sits below the bottom of it.")
    w(";")
    w("; ---------------- THE POSTS ----------------")
    w(f";   mouth = (bore + {bw:g}) * sin((360 - wrap)/2) - {bw:g}    stick = {a.stick_d:g}mm NOMINAL")
    w(";   post  sector  wrap   bore-allow   modelled bore   expected printed   mouth   vs stick")
    for n, s, wd, al, b, mo in cells:
        d = mo - a.stick_d
        verdict = ("DROPS IN, no capture" if d > 0.05 else
                   "marginal, on the line" if d > -0.15 else "should CLICK past the lips")
        w(f";   {n:>4}  {s+1:>6}  {wd:>4.0f}   {al:>10.3f}   {b:>13.3f}   "
          f"{b - SHRINK_SUSPECT:>16.3f}   {mo:>5.3f}   {d:+.3f}  {verdict}")
    w(";")
    w(f"; THE PLATE CARRIES ITS OWN NEGATIVE CONTROL: the posts marked DROPS IN model a mouth WIDER")
    w(f"; than the stick and must NOT retain it. If they click, the model is wrong somewhere else")
    w(f"; and nothing on this plate can be read. Check those first.")
    w(";")
    w(f"; UNSUPPORTED AIR PER CROSSING: {air:.2f}mm, against the {bt.PROVEN_AIR_MM:g}mm this project")
    w(f"; has actually proven. THE REAL RING ALREADY SPANS THIS — the coupon inherits the part's own")
    w(f"; span rather than quietly printing an easier one. If the net sags or snaps here, it does so")
    w(f"; on the bucket too, and that is a finding about the bucket, not about the coupon.")
    w(";")
    w("; ---------------- HOW TO READ IT ----------------")
    w("; 1 NET-TO-WALL: pull a strand between two posts sideways, then up. Tearing = merged.")
    w(";   Peeling off the post in one piece = still two structures touching.")
    w("; 2 WALL-TO-BASE: try to snap a post off the floor strip. It should break the post.")
    w("; 3 BORE: press a skewer into each numbered post. Report the LOWEST number that goes in")
    w(";   without forcing and does not rattle. Try several skewers — the last bamboo this project")
    w(";   measured varied 0.4mm stick to stick, and if the answer changes with the stick that IS")
    w(";   the finding.")
    w("; 4 LOCK: same bore, three sectors. The wrap that snaps past the lips and holds against a")
    w(";   gentle pull, while still going in by thumb, is the wrap.")
    w("; 5 SHRINK, MEASURED AT LAST: callipers across any post's OUTER diameter and its mouth,")
    w(f";   against the table above. That difference replaces the {SHRINK_SUSPECT:g} guess whether or not")
    w(";   anything clicks, so this plate answers something even if every post is wrong.")
    w("; MATERIAL_PLACEHOLDER")
    _mat_line = len(L) - 1
    w(";")

    w("M82")
    w("G90")
    w(f"M140 S{bed:.0f}")
    w(f"M104 S{temp}")
    w("G28")
    w("SET_GCODE_OFFSET Z=0                 ; start from the machine's own zero, not last run's")
    w(f"M190 S{bed:.0f}")
    w(f"M140 S{bed:.0f}")
    w(f"M109 S{temp}")
    w(f"M106 S{int(round(fan1 * 255))}   ; layer 1: {fan1*100:.0f}% — the plate weld is the job")
    for line in machine.aux_fans(a.printer, 0.0):
        w(line)
    w("G92 E0")
    w(f"SET_GCODE_OFFSET Z={zoff:.3f} MOVE=1   ; commanded Z{press:.3f} lands {a.h1:.3f}mm on a "
      f"machine whose zero sits {zerr:.3f} high")

    px, py = 20.0, 16.0
    w("G1 F600 Z2.000")
    w(f"G0 F{travel_f} X{px:.3f} Y{py:.3f}")
    w("G1 E20 F300                      ; PRIME purge, LIFTED to Z2 so it cannot collar the tip")
    w(f"G1 F600 Z{press:.3f}")
    w(f"G1 F1200 X{px+40:.3f} Y{py:.3f} E30   ; PRIME line, in the clear at the press gap")
    w(f"G0 F3000 X{px+52:.3f} Y{py+12:.3f}  ; PRIME break-off — angled wipe, no extrusion")
    w("G92 E0")
    w("; BODY_START")

    E = 0.0
    d_body = d_l1 = d_trav = d_z = 0.0
    cur = [px + 52.0, py + 12.0, press]

    def hop(tx, ty, z, note):
        nonlocal d_trav, d_z
        sz = max(z + 1.0, 3.0)
        w(f"G0 Z{sz:.3f} F1800   ; HOP lift, clear of the wall AND the Z2 prime purge")
        w(f"G0 X{tx:.3f} Y{ty:.3f} F{travel_f}   ; HOP {note}")
        w(f"G1 F1800 Z{z:.3f}")
        d_trav += math.hypot(tx - cur[0], ty - cur[1])
        d_z += abs(sz - cur[2]) + abs(sz - z)
        cur[0], cur[1], cur[2] = tx, ty, z

    # DIGITS ON THE FLOOR STRIP, one per post, standing on the finished floor. Drawn on the first
    # --digit-layers WALL layers so they are proud of the base and photograph legibly.
    digit_jobs = {}
    for sec_i, sec in enumerate(sectors):
        cxr, cyr = sec["ring"]
        for k, p in enumerate(sec["posts_bed"]):
            n = sec_i * a.n_post + k + 1
            ang = p["phi"]
            rr = r_in + a.floor_w * 0.45
            gx, gy = cxr + rr * math.cos(ang), cyr + rr * math.sin(ang)
            digit_jobs.setdefault(sec_i, []).append((str(n), gx, gy - gh / 2.0))

    fan_on = False
    for li in range(n_lay):
        z = press + li * lh
        w(f"; ---- layer {li+1} of {n_lay}  z {z:.3f}  "
          f"({'floor latch + rim' if li < a.floor_layers else ('wall + BRIDGES' if li in bridges else 'wall + net')})")
        if li == 1 and not fan_on:
            w(f"M106 S{int(round(fan2 * 255))}   ; {fan2*100:.0f}% — a single-bead wall needs it")
            fan_on = True
        # SECTOR ORDER ALTERNATES AND SO DOES THE WALK, so the head finishes each layer standing
        # where the next one starts and there is exactly ONE hop per sector per layer.
        sec_order = list(range(len(sectors))) if li % 2 == 0 else list(range(len(sectors)))[::-1]
        for si in sec_order:
            sec = sectors[si]
            fwd = (li % 2 == 0)
            Lay = (sec["layers"] if fwd else sec["layers_rev"])[li]
            p0 = Lay["pts"][0]
            hop(p0[0], p0[1], z, f"to sector {si+1} (wrap {sec['wrap']:g}) layer {li+1}")
            w(f"G1 F{f_1 if li == 0 else f_b} X{p0[0]:.3f} Y{p0[1]:.3f}")
            ppx, ppy = p0
            for j, (x, y) in enumerate(Lay["pts"][1:]):
                kind = Lay["kind"][j]
                seg = math.hypot(x - ppx, y - ppy)
                if seg < 1e-9:
                    continue
                if kind == "T":
                    E += seg * e_body * a.cross_flow
                    w(f"G1 F{f_1 if li == 0 else f_b} X{x:.3f} Y{y:.3f} E{E:.5f} ; THIN CROSS "
                      f"{a.cross_flow*100:.0f}% -- deliberate strand, not ooze (clears both walls)")
                elif kind == "M":
                    E += seg * e_body * a.merge_flow
                    w(f"G1 F{f_1 if li == 0 else f_b} X{x:.3f} Y{y:.3f} E{E:.5f} ; LINK MERGE "
                      f"{a.merge_flow*100:.0f}% -- net lapped onto the post, {a.merge_mm:g}mm of arc")
                else:
                    _bm = Lay["mult"] if kind == "B" else 1.0
                    E += seg * (e_l1 if li == 0 else e_body * _bm)
                    if kind == "B":
                        _a2 = _bm * bw * lh
                        w(f"G1 F{f_b} X{x:.3f} Y{y:.3f} E{E:.5f} ; BRIDGE {_bm:g}x {_a2:.4f}mm2 "
                          f"rod {2*math.sqrt(_a2/math.pi):.3f}mm, {seg:.2f}mm tip to tip")
                    else:
                        w(f"G1 F{f_1 if li == 0 else f_b} X{x:.3f} Y{y:.3f} E{E:.5f}")

                if li == 0:
                    d_l1 += seg
                else:
                    d_body += seg
                ppx, ppy = x, y
            cur[0], cur[1] = ppx, ppy
        if a.floor_layers <= li < a.floor_layers + a.digit_layers:
            for si in sec_order:
                for lab, gx, gy in digit_jobs[si]:
                    w(f"; ---- post number '{lab}' at Z{z:.3f}")
                    for (ax, ay), (bx_, by_) in glyph_segments(lab, gx, gy, gw, gh, ggap):
                        hop(ax, ay, z, f"to number {lab}")
                        d = math.hypot(bx_ - ax, by_ - ay)
                        E += d * e_body
                        w(f"G1 F{f_b} X{bx_:.3f} Y{by_:.3f} E{E:.5f}")
                        d_body += d
                        cur[0], cur[1] = bx_, by_

    w("; ---- done")
    w("SET_GCODE_OFFSET Z=0                 ; hand the machine back at its own zero")
    w("M107"); w("M104 S0"); w("M140 S0")
    _zr, _zc = machine.z_retreat(a.printer, top_z)
    w(f"G0 F{f_b} Z{_zr:.2f}")
    w(f"G0 X10 Y{bedy-10:.0f} F{travel_f}")
    w("M84")

    mins = (d_l1 / a.speed1 + d_body / a.speed) / 60.0 \
        + d_trav / machine.MACHINE_MAX_SPEED / 60.0 + d_z / 30.0 / 60.0
    vol = E * A_FIL / 1000.0
    L[_mat_line] = (f"; MATERIAL {vol*1.24:.1f}g / {vol:.2f}cm3, ~{mins:.0f} min of motion — "
                    f"measured from this file's own final E and its own emitted moves")

    open(out, "w").write("\n".join(L) + "\n")

    print(out)
    print(f"  {len(sectors)} sectors x {a.n_post} posts on the REAL {a.dia:g}mm ring "
          f"({2*math.pi*(a.dia/2)/a.n_ring:.1f}mm post pitch), {a.height:g}mm, {n_lay} layers")
    print(f"  floor {a.floor_layers} layers, strip r {r_in:.1f}..{r_out:.1f} "
          f"(outer radius DERIVED to touch the feet without entering the bore)")
    print(f"  merge {a.merge_mm:g}mm of arc at {a.merge_flow*100:.0f}% -> {1+a.merge_flow:.2f}x bead "
          f"in the lip; net at {a.cross_flow*100:.0f}%; air per crossing {air:.2f}mm "
          f"(proven {bt.PROVEN_AIR_MM:g})")
    print(f"  first layer {a.h1:.3f}x{a.w1:.2f} via SET_GCODE_OFFSET Z={zoff:.3f} — proven pair")
    print(f"    post  sec  wrap  b-allow    bore  exp.print   mouth  vs stick {a.stick_d:g}")
    for n, s, wd, al, b, mo in cells:
        d = mo - a.stick_d
        print(f"    {n:>4}  {s+1:>3}  {wd:>4.0f}  {al:>7.3f}  {b:>6.3f}  {b-SHRINK_SUSPECT:>9.3f}  "
              f"{mo:>6.3f}  {d:+.3f}  "
              f"{'DROPS IN' if d > 0.05 else 'marginal' if d > -0.15 else 'should CLICK'}")
    print(f"  modelled mouths {mn:.3f}..{mx:.3f} — straddle the {a.stick_d:g} stick by more than "
          f"the {SHRINK_SUSPECT:g} the shrink is unknown by, both ways")
    print(f"  ~{mins:.1f} min of motion, {vol:.2f}cm3")


if __name__ == "__main__":
    main()
