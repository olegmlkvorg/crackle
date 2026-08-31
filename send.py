#!/usr/bin/env python3
"""THE ONLY PATH TO THE PRINTER, and the gate that guards the DECISION TO PRINT.

Oleg, 2026-08-06: "guards guards guards, AI is not deterministic".

WHY THIS FILE EXISTS, stated as the gap it closes. Five gates were written on 2026-08-06 -- R9
(first layer), R10 (unpinned extrusion), R4e (bridge schedule), and bucket_towers' own gates 5 and
6. EVERY ONE OF THEM RUNS ON A FILE. Every one of them passed on the files that then failed on the
plate, because the thing that failed was not the file, it was the decision to send it: uploading to
Moonraker and pressing start was done by hand, on judgement, by an actor that is not deterministic.
Four plates went that way in one day.

  1  a stencil coupon printed because it was READY, not because it answered a blocked question --
     and its 1.00x floor coverage had already been written down as likely to pinhole before it ran.
     "What the heck is this? ... Think what you doing before printing"
  2  a bamboo base sent with --h1 0.10 -> 0.15 and --w1 2.00 -> 1.33, both first-layer-critical,
     straight to a plate. It came off as lifted strands. "Base has not acceptable artifacts"
  3  PRIME_PURGE_MM changed from an effective 20mm stationary dump to a 5.0mm moving purge across
     32 generators, and sent to a NINE HOUR plate with no coupon. "dude you kidding me why
     baselayer again shit?"
  4  a bore guessed twice, printed twice, wrong twice, before a gauge finally answered it in one
     plate.

The common shape is one sentence: A SEND-CRITICAL VALUE CHANGED SINCE THE LAST PRINT OLEG ACCEPTED,
AND THE FILE WENT TO THE MACHINE ANYWAY. This tool refuses that.

WHAT IT DOES, in order:
  1  runs validate.py and refuses on any failure. The file gate stays the file gate; this wraps it.
  2  MEASURES every send-critical value OFF THE EMITTED FILE. Not off the command line, which is a
     claim, and not off the header, which is prose that has drifted from the moves twice here.
  3  compares each against machine.PROVEN_SEND / machine.PROVEN_LAYER1 -- a list of pairs somebody
     watched come off a plate, never a range.
  4  refuses anything that differs, unless the file carries a '; SEND_COUPON=' citation that a
     coupon on disk actually satisfies when the SAME measurement is run on it.
  5  refuses a long print whose evidence for any value is only a coupon, unless --allow-long --why.
  6  ALLOWS A SHORT PRINT TO ESTABLISH A VALUE NOTHING HAS PROVEN YET -- the mirror of 5, and the
     reason this gate is not a wall. See FIRST_PROOF_MAX_MIN: rule 4 refuses the unproven, and a coupon
     is the ONLY mechanism by which anything here becomes proven, so without this the gate refuses
     its own coupons and nothing can ever reach a plate again. Bounded by the file's own motion
     estimate and never by a claim to be a coupon; granted to ONE file per value; loud in the
     output, in send-log.jsonl and in `ledger`.
  7  records what it saw in send-log.jsonl, so a later failure can be traced to what was in force.
  8  never writes the ledger. Only a human editing machine.py does that (`accept` prints the entry).

ABSTENTION BLOCKS THE SEND. A check that matched no moves has not checked anything, and R4b already
proved how that reads: it printed "NOT MEASURED" on the stencil and on both buckets, and all three
files still reported a green tick. Here a rule that cannot measure its own name says ABSTAIN and
the send is refused, exactly as if it had failed. A rule that does not apply at all says N/A and
names why it does not apply, which is a different sentence and must stay one.

DRY RUN IS THE DEFAULT AND THERE IS NO DEFAULT HOST IN THIS FILE. `--live` refuses without an
explicit `--printer-host`, so no invocation can find a printer by accident.

WHY IT LIVES AT crackle/ AND NOT crackle/bin/: it imports `machine` and `validate` as siblings, the
way all 30-odd generators and both forced-test harnesses already do (sys.path off __file__), and it
is the twin of validate.py -- one gate on the artifact, one on the act. A subdirectory would buy a
tidier listing and cost a path shim in every caller.

Usage:
  python3 send.py FILE.gcode                                  # DRY RUN. the default.
  python3 send.py FILE.gcode --live --printer-host HOST       # upload + start
  python3 send.py FILE.gcode --allow-long --why "..."         # override rule 5, recorded
  python3 send.py accept FILE.gcode --by oleg --verdict held --observed "..."
  python3 send.py ledger
"""
import argparse, collections, datetime, hashlib, json, math, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import validate

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG = os.path.join(HERE, 'send-log.jsonl')

# TOLERANCES, one place. Each is the resolution at which the emitted numbers are stable, not a
# comfort band: the bucket files land 17.8500 and 33.0900 on every single move, and the prime lands
# 5.00000 and 1.20000 to five decimals across three different generators.
TOL = {
    'w1': 0.05, 'pitch': 0.05, 'purge': 0.02, 'fat': 0.01, 'stationary': 0.01,
    'span': 0.05, 'cross': 0.5, 'temp': 0.5, 'bore': 0.02,
}

# ------------------------------------------------------------------------- the first proof ---
# MOTION-ONLY MINUTES UNDER WHICH A FILE MAY ESTABLISH A VALUE NOTHING HAS PROVEN YET.
#
# THE MIRROR OF machine.LONG_PRINT_MIN, AND THE REASON THIS GATE IS NOT A WALL. Only one direction
# was written on 2026-08-06 -- refuse a LONG print whose evidence is coupon-only -- and the
# inverse turned the tool into a deadlock the same afternoon. machine.prime() was rewritten that
# day, so every file in the repo carries (5, 1.2, 0); the only prime with an accepted print behind
# it is (12, None, 12); and that one is itself refused by validate.py R10, which no longer allows
# stationary in-air extrusion. So S3 failed on EVERY file -- including the bore gauge, whose entire
# purpose is to answer a question the ledger cannot. The way to prove a value is to print a coupon
# and read the plate, and the coupon was refused too. NOTHING COULD REACH THE PRINTER, INCLUDING
# THE INSTRUMENT THAT EXISTS TO BREAK THE TIE.
#
# WHY DURATION AND NOT INTENT. A file must not be able to exempt itself by declaring it is a
# coupon: that declaration is one line anybody can type, and this whole tool exists because the
# actor typing it is not deterministic. The house pattern is already that a citation supplies a
# POINTER and never a permission. So the bound is the estimate this tool integrates off the moves,
# and the risk it bounds is real: a ten-minute plate is a coffee, a nine-hour plate is an evening.
#
# WHY 25, AND WHAT KIND OF MINUTES. Motion-only minutes, the number validate.py reports and this
# tool independently re-integrates -- NOT wall clock. The three gauges this project read off a
# plate on 2026-08-06 (motion re-derived here by running validate.py on the files; wall clock as
# recorded by the session that ran them):
#
#     stencil_coupon_..._1L_h0.1_w2      5.70 motion    7.8 wall    +2.1
#     borelock_..._b3.75-4.75x6_...      9.52 motion   20.5 wall   +11.0
#     bucket_sector_..._d341.5_n4_...   21.21 motion   ~30  wall    +~9
#
# THE OVERHEAD IS FIXED, NOT PROPORTIONAL: the K2 runs a calibration block before the job, so the
# gap is minutes of setup and not a ratio. A threshold set on motion is therefore read as wall
# clock by ADDING the worst overhead ever observed here (+11.0), never by scaling one. 25 min of
# motion is about 36 min of wall clock in the worst case.
#
# The number sits above every gauge anybody here has read off a plate (21.21) and below the
# smallest real part in the same day's output (bucket_latch_..._d200_h40_f2p5, 39.27 min of
# motion), so the band it opens is the gauge-sized band and not one part wider. It is 3.6x under
# LONG_PRINT_MIN, and the gap is deliberate: between 25 and 90 minutes an unproven value gets
# neither a grant nor a pass, and the answer there is to print the gauge.
#
# IT LIVES HERE AND NOT IN machine.py because it is a property of this GATE and not of the plate --
# the same reason TOL above is here. machine.py's constants describe what the machine did.
#
# THE NAME CARRIES THE DIRECTION BECAUSE THE SUFFIX CANNOT. It was written FIRST_PROOF_MIN, matching
# machine.LONG_PRINT_MIN, where the trailing MIN is the UNIT -- minutes -- and not "minimum". That
# convention is fine while every constant bounds duration from the same side, and these two do not:
# LONG_PRINT_MIN is a FLOOR (past it, a coupon stops being enough) and this is a CEILING (under it,
# a file may go unproven). Two thresholds that push opposite ways under one identical suffix is a
# name you have to read the body to use, and the body is what the name exists to save. So the
# direction is spelled: MAX minutes.
FIRST_PROOF_MAX_MIN = 25.0

# ---------------------------------------------------------------------------- the citation ---
# THE SAME SHAPE AS R9's '; COUPON=' AND FOR THE SAME REASON: the citation supplies a POINTER and
# ONE HUMAN WORD, and every number in it is re-derived from artifacts. Anchored and total, because
# a stamp that can be partially matched is a stamp that can be padded.
COUPON_RE = re.compile(
    r'^;\s*SEND_COUPON=(\S+)\s+file=(\S+)\s+value=(\S+)\s+verdict=(\S+)\s+read=(\d{4}-\d{2}-\d{2})\s*$',
    re.M)

# THE VERDICT IS A NAMED WORD PER PARAMETER, NOT A BOOLEAN, and the word names what a human had to
# LOOK AT. R9 accepts only `welded` -- not `printed` (it ran) and not `read` (someone looked) --
# because "somebody thumb-peeled a corner and it fought back" is the claim, and a boolean cannot
# carry it. One word per parameter forces the citer to say which observation they are making.
VERDICT = {
    'coverage': ('welded', "the floor was peeled and fought back, with no pinholes between lines"),
    'prime':    ('pinned', "the lead-in printed continuous and full width, and NOTHING came off "
                           "the nozzle onto the part"),
    'span':     ('taut',   "the strand pulled TAUT across the air and did not sag"),
    'cross':    ('clean',  "the crossings at that speed landed clean, no whipping and no drag"),
    'temps':    ('held',   "the geometry stood at that temperature instead of coiling"),
    'fit':      ('gripped', "the actual stick went into that actual bore and GRIPPED"),
}

Finding = collections.namedtuple('Finding', 'rule status text')
PASS, FAIL, NA, ABSTAIN, CITED = 'PASS', 'FAIL', 'N/A', 'ABSTAIN', 'CITED'
# ITS OWN WORD, NOT A CITED AND NOT A PASS. A reader who cannot tell the three apart at a glance
# cannot tell "somebody watched this come off a plate" from "nothing has ever tested this and we
# are about to find out", which is the entire difference rule 6 trades on.
FIRSTPROOF = 'FIRST-PROOF'
BLOCKING = (FAIL, ABSTAIN)


# ------------------------------------------------------------------------------ measurement ---
def header_of(path, cap=4000):
    """Everything before '; BODY_START'. The generators put every declaration there and the moves
    after it; reading the whole 88MB file to find a stamp is 60 seconds nobody needs to spend."""
    out = []
    with open(path) as fh:
        for i, ln in enumerate(fh):
            out.append(ln)
            if 'BODY_START' in ln or i > cap:
                break
    return ''.join(out)


def _fit_circle(P):
    """Least-squares circle through points P. Returns (cx, cy, r, max residual mm) or None.

    THE RESIDUAL IS RETURNED BECAUSE IT IS THE TRUST TEST. A read-only pass over four files found
    that taking 'the first 17 extruding points at a body layer' returned the right radius on two
    files and a nonsense 17.9497 on two others, where it had grabbed a merge lap running off the
    arc. A radius with no residual beside it cannot tell those apart, so this never returns one."""
    if len(P) < 6:
        return None
    A = [[2 * px, 2 * py, 1.0] for px, py in P]
    B = [px * px + py * py for px, py in P]
    M = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(3)] + [
         sum(A[k][i] * B[k] for k in range(len(A)))] for i in range(3)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        if abs(M[i][i]) < 1e-12:
            return None
        for r in range(3):
            if r != i:
                f = M[r][i] / M[i][i]
                for c in range(i, 4):
                    M[r][c] -= f * M[i][c]
    cx, cy, cc = (M[i][3] / M[i][i] for i in range(3))
    rr = cc + cx * cx + cy * cy
    if rr <= 0:
        return None
    r = math.sqrt(rr)
    res = max(abs(math.hypot(px - cx, py - cy) - r) for px, py in P)
    return cx, cy, r, res


# FRACTION OF LAYER-1 GAPS THE MODAL GAP MUST COVER BEFORE IT COUNTS AS A MEASURED PITCH.
# Not a taste: the two coverages actually in the ledger are 196 of 197 gaps (99.5%) and 132 of 134
# (98.5%), while a plate carrying two offset pads splits its gaps roughly in half and lands near
# 0.50. 0.70 sits in the empty middle with room on both sides. Below it the plate has more than one
# lattice on it and the mode is measuring the offset BETWEEN pads, not the pitch within one.
PITCH_DOMINANCE = 0.70


def scan(path, arc_z_min=3.0):
    """ONE streaming pass over the emitted moves. Everything below is MEASURED, never parsed.

    The only things read out of prose are the DECLARATIONS that get cross-examined against these
    numbers -- the bead width and the declared bore -- and a declaration that disagrees with the
    moves is a finding, not a fallback."""
    head = header_of(path)
    x = y = z = None
    z1 = None                       # the body's first bead height, commanded
    eabs, absE, feed = 0.0, True, 3000.0
    body = False
    secs = 0.0
    # prime
    lead_mm = lead_e = wit_mm = wit_e = stat_e = 0.0
    prime_moves = 0
    # layer 1 floor pitch
    hor, ver = set(), set()
    l1_lines = 0
    l1_done = False
    # spans
    span_len = collections.Counter()
    span_max = 0.0
    span_n = 0
    cross_f = collections.Counter()
    cross_n = 0
    # arcs at one body layer
    arc_z = None
    runs, cur = [], []
    arc_done = False

    with open(path) as fh:
        for ln in fh:
            if not body:
                body = 'BODY_START' in ln
            up = ln.upper()
            c = ln.split(';')[0].strip()
            if not c:
                continue
            if c.startswith('M82'):
                absE = True
                continue
            if c.startswith('M83'):
                absE = False
                continue
            if c.startswith('G92'):
                m = re.search(r'\bE(-?\d+(?:\.\d+)?)', c)
                if m:
                    eabs = float(m.group(1))
                continue
            if c[:2] not in ('G0', 'G1'):
                continue
            g = dict(re.findall(r'\b([XYZEF])(-?\d+(?:\.\d+)?)', c))
            if 'F' in g:
                feed = float(g['F'])
            nz = float(g['Z']) if 'Z' in g else z
            nx = float(g['X']) if 'X' in g else x
            ny = float(g['Y']) if 'Y' in g else y
            de = 0.0
            if 'E' in g:
                v = float(g['E'])
                de = (v - eabs) if absE else v
                if absE:
                    eabs = v
            d = math.hypot(nx - x, ny - y) if None not in (x, y, nx, ny) else 0.0
            if d > 0 and feed > 0:
                secs += d / (feed / 60.0)
            isprime = 'PRIME' in up

            # -- THE PRIME. Measured off the moves tagged PRIME, in three parts, because the three
            # failed differently: the stationary dump is the clump in Oleg's photograph, the purge
            # volume is what got changed 20 -> 5, and the fat multiplier is the second blob source
            # in the MOVING line that fixing only the dump would have left behind.
            if isprime and de > 0:
                prime_moves += 1
                if d < 1e-9:
                    stat_e += de
                elif 'lead-in' in ln:
                    lead_mm += d
                    lead_e += de
                elif 'witness' in ln:
                    wit_mm += d
                    wit_e += de

            if body and not isprime and de > 0 and d > 1e-9 and nz is not None:
                # -- LAYER 1 FLOOR PITCH. The floor latch is axis-aligned runs; the pitch is the
                # MODAL gap between the distinct coordinates of the parallel ones. It exists in no
                # machine-readable stamp anywhere -- only in prose ('at 2.5mm pitch') -- and
                # nothing in validate.py reads it. It is half of what welds: 2.00mm lines on a
                # 2.5mm pitch leave 0.50mm of bare plate, and raising --w1 2 -> 3 -> 5 never closed
                # that gap because the nozzle never travels there.
                if z1 is None:
                    z1 = nz
                if not l1_done:
                    if abs(nz - z1) > 1e-9:
                        l1_done = True
                    else:
                        l1_lines += 1
                        if abs(ny - y) < 1e-6 and abs(nx - x) > 0.5:
                            hor.add(round(y, 3))
                        elif abs(nx - x) < 1e-6 and abs(ny - y) > 0.5:
                            ver.add(round(x, 3))

                # -- SPANS. Each crossing is deliberately ONE unsubdivided move so nothing in the
                # planner can slow it and let it sag, which is what makes the length exact here.
                if 'BRIDGE' in up or 'THIN CROSS' in up:
                    span_n += 1
                    span_max = max(span_max, d)
                    if len(span_len) < 5000:
                        span_len[round(d, 3)] += 1
                if 'THIN CROSS' in up:
                    cross_n += 1
                    if len(cross_f) < 500:
                        cross_f[round(feed, 1)] += 1

                # -- ONE BODY LAYER'S ARCS, for the bore. Contiguous short extruding segments
                # only: a run breaks at a travel, at a jump, or at anything longer than a post's
                # own chord, which is what keeps a crossing chord out of the fit.
                if not arc_done and nz >= arc_z_min:
                    if arc_z is None:
                        arc_z = nz
                    if abs(nz - arc_z) > 1e-9 or len(runs) >= 80:
                        # THE END OF THE LAYER IS A BREAK LIKE ANY OTHER. Flushing only on the
                        # branches that noticed a break lost every run on a part whose layer is one
                        # unbroken chain of extrusions -- which is every part in this project,
                        # because it has no retraction and travels are the thing it avoids.
                        if len(cur) >= 8:
                            runs.append(cur)
                        cur = []
                        arc_done = True
                    elif cur and cur[-1] == (x, y) and d <= 1.5:
                        cur.append((nx, ny))
                    else:
                        # A 33mm crossing chord breaks the run. Dropping the run being built
                        # instead of keeping it is how 3388 crossings ate every post arc in the
                        # file and the fit reported 0 of 0.
                        if len(cur) >= 8:
                            runs.append(cur)
                        # AND THE BREAKING MOVE DOES NOT SEED THE NEXT RUN. Its far endpoint is on
                        # the arc; its near endpoint is 33mm away on another post, and one point
                        # that far off the circle drags the least-squares fit and its residual
                        # with it. That is what left 28 of 56 runs untrustworthy on the nine-hour
                        # file -- half the arcs in it, silently.
                        cur = [(x, y), (nx, ny)] if d <= 1.5 else []
            elif not arc_done and cur and d > 1e-9:
                # A REAL TRAVEL BREAKS THE RUN. A move that deposits nothing AND goes nowhere -- a
                # bare feedrate change, of which these files emit one per crossing -- is not a
                # break, and treating it as one wiped `cur` between every pair of arc points and
                # reported 0 runs on a file with 28 posts on every layer.
                if len(cur) >= 8:
                    runs.append(cur)
                cur = []

            x, y, z = nx, ny, nz
    if len(cur) >= 8 and len(runs) < 80:
        runs.append(cur)

    def gap_profile(vals):
        """Modal gap between sorted coordinates -- and it DECLINES when the plate carries more than
        one lattice.

        WHY THE DECLINE HAD TO BE ADDED, 2026-08-06. `vals` is a set of coordinates with the extent
        along the OTHER axis thrown away, so two pads whose rasters are offset from each other are
        indistinguishable from one raster here. Sorted together they INTERLEAVE, and the modal gap
        becomes the OFFSET BETWEEN PADS instead of the pitch within either. Pad A at 0, 1.6, 3.2 and
        pad B at 0.4, 2.0, 3.6 sort to 0, 0.4, 1.6, 2.0, 3.2, 3.6, whose gaps are 0.4, 1.2, 0.4,
        1.2, 0.4 -- mode 0.4, while BOTH rasters are 1.6.

        That is not an imprecise measurement, it is a measurement of a different quantity, and it
        was silently SPENDING rule 6's one-per-value grants on numbers no plate ever had: the span
        ladder took a grant at (2, 0.4) and bucket_sector at (2, 10.481), both from this. Worse,
        `accept` re-measures and offers the bogus number as a paste-ready ledger row.

        A genuine single raster has one gap repeated. On the two coverages actually in the ledger
        the mode covers 196/197 and 132/134 of the gaps. So dominance separates the cases cleanly,
        and where it fails the honest answer is NOT MEASURED -- which S2 already turns into an
        abstention that blocks the send. UNMEASURED is not UNPROVEN, and a gate that guesses here
        is worse than one that declines.
        """
        u = sorted(vals)
        if len(u) < 3:
            return None, len(u), 0.0
        gaps = collections.Counter(round(b - a, 3) for a, b in zip(u, u[1:]))
        top, n_top = gaps.most_common(1)[0]
        dom = n_top / float(sum(gaps.values()))
        if dom < PITCH_DOMINANCE:
            return None, len(u), dom
        return (top, n_top), len(u), dom

    (hg, hn, hdom), (vg, vn, vdom) = gap_profile(hor), gap_profile(ver)
    pitch = None
    if hg and vg:
        pitch = hg[0] if hg[1] >= vg[1] else vg[0]
    elif hg:
        pitch = hg[0]
    elif vg:
        pitch = vg[0]

    fits = [f for f in (_fit_circle(r) for r in runs) if f]
    good = [f for f in fits if f[3] <= 0.01 and 0.5 <= f[2] <= 25.0]

    m = re.search(r'^; PRINTER=(\S+)', head, re.M)
    printer = m.group(1) if m else None
    m = re.search(r'^; bead ([\d.]+)x([\d.]+)', head, re.M)
    bead_w = float(m.group(1)) if m else None
    m = re.search(r'^;\s+bore\s+([\d.]+)mm', head, re.M)
    bore_declared = float(m.group(1)) if m else None
    hot = re.findall(r'^M10[49] S([\d.]+)', head, re.M)
    bed = re.findall(r'^M1[49]0 S([\d.]+)', head, re.M)

    return {
        'head': head, 'printer': printer, 'bead_w': bead_w,
        'est_min': secs / 60.0,
        'z1': z1, 'l1_lines': l1_lines, 'pitch': pitch,
        'pitch_hor': (hg, hn), 'pitch_ver': (vg, vn),
        'prime_moves': prime_moves,
        'purge_mm': (lead_e if lead_mm > 0 else (stat_e if stat_e > 0 else None)),
        'prime_fat': ((lead_e / lead_mm) / (wit_e / wit_mm)) if (lead_mm and wit_mm and wit_e) else None,
        'stationary_mm': stat_e,
        'lead_mm': lead_mm,
        'span_n': span_n, 'span_max': span_max,
        'span_modal': span_len.most_common(1)[0] if span_len else None,
        'cross_n': cross_n,
        'cross_mms': (max(cross_f, key=cross_f.get) / 60.0) if cross_f else None,
        'cross_spread': sorted(round(f / 60.0, 1) for f in cross_f),
        'arc_z': arc_z, 'arc_runs': len(runs), 'arc_fits': len(fits), 'arc_good': len(good),
        'arc_r': (collections.Counter(round(f[2], 3) for f in good).most_common(1)[0]
                  if good else None),
        'bore_declared': bore_declared,
        # The HOTTEST pre-body temp, not the first: the leak-proof start flow (2026-08-31)
        # probes at 140 and only reaches print temp at the chute, so hot[0] read the probe temp
        # as the print temp and S6 judged (140, 80) on a file that prints at 210.
        'hot': max(float(h) for h in hot) if hot else None,
        'bed': float(bed[0]) if bed else None,
    }


def bore_measured(meas):
    """Toolpath radius -> bore. `bore = 2r - bead`, the same arithmetic the generator inverts."""
    if not meas['arc_r'] or meas['bead_w'] is None:
        return None
    return 2 * meas['arc_r'][0] - meas['bead_w']


def part_values(path, meas, zerr):
    """The send-critical values of ONE file, as the ledger stores them. Used on the part AND on
    every cited coupon, by the same code, so a citation cannot be measured more kindly than the
    file it excuses -- the property that makes R9's hatch checkable rather than declarative."""
    fl = validate.first_layer_emitted(path, zerr) if zerr is not None else {'h1': None, 'w1': None}
    return {
        'layer1': (fl['h1'], fl['w1']),
        'coverage': (fl['w1'], meas['pitch']),
        'prime': (meas['purge_mm'], meas['prime_fat'], meas['stationary_mm']),
        'span': (meas['span_max'] if meas['span_n'] else None,),
        'cross': (meas['cross_mms'],),
        'temps': (meas['hot'], meas['bed']),
        'fit': (bore_measured(meas),),
    }


def _close(a, b, tol):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def _vec_close(a, b, tols):
    return len(a) == len(b) and all(_close(u, v, t) for u, v, t in zip(a, b, tols))


TOLS = {
    'layer1': (0.005, TOL['w1']),
    'coverage': (TOL['w1'], TOL['pitch']),
    'prime': (TOL['purge'], TOL['fat'], TOL['stationary']),
    'span': (TOL['span'],),
    'cross': (TOL['cross'],),
    'temps': (TOL['temp'], TOL['temp']),
    'fit': (TOL['bore'],),
}


# -------------------------------------------------------------------------- the escape hatch ---
def check_citations(path, param, want, meas, zerr, today):
    """Does a '; SEND_COUPON=' line on this file legitimately excuse `want` for `param`?

    Returns (ok, note). Every clause here is one of R9's, plus the four holes an audit found in R9
    that a send gate cannot inherit, because the actor writing the citation is the one this whole
    tool exists to distrust:

      A  SELF-CITATION. R9 never checks the cited file is not the citing file, and it was proved by
         running it: the exact bamboo base that lifted passed R9 with EXIT 0 on one added header
         line naming itself. Closed here by realpath.
      C  read= is FORMAT-ONLY in R9 -- captured, printed, never compared with anything. A citation
         may be dated before the coupon existed. Closed here against the coupon's mtime and today.
      D  R9 scores the coupon under the CITING file's machine and never reads the coupon's own
         '; PRINTER='. A coupon from another machine gets re-measured under k2plus's Z error.
         Closed here by requiring the stamp and requiring it to match.
      B  the coupon never had to touch a plate. THIS CANNOT BE CLOSED BY READING FILES and is not
         claimed to be: the physical claim rests on the verdict word, which the citer types. What
         is added instead is that a coupon must be COUPON-SIZED (its own motion estimate under
         LONG_PRINT_MIN), so a nine-hour part cannot be cited as evidence for itself-by-proxy.
    """
    txt = meas['head']          # the declarations live before '; BODY_START', with the moves after
    stamps = COUPON_RE.findall(txt)
    # A MALFORMED CITATION IS A FAILURE, NOT AN ABSENCE. A guard that ignores what it cannot parse
    # is off, and reading a broken attestation as "no constraint applies" is the worst direction
    # for the error to point.
    for ln in re.findall(r'^;\s*SEND_COUPON=.*$', txt, re.M):
        if not COUPON_RE.match(ln):
            return False, (f"It carries a '; SEND_COUPON=' line that does not parse: {ln.strip()!r}"
                           f". The stamp is '; SEND_COUPON=<param> file=<f> value=<a,b,..> "
                           f"verdict=<word> read=<YYYY-MM-DD>', and a citation nothing can check "
                           f"is not evidence.")
    mine = [s for s in stamps if s[0] == param]
    if not mine:
        return False, "It cites no coupon for this."
    _p, _f, _v, _verdict, _read = mine[0]
    if param not in VERDICT:
        return False, f"'{param}' is not a parameter this gate knows how to judge."
    word, means = VERDICT[param]
    if _verdict != word:
        return False, (f"Its {param} citation reads verdict={_verdict}. Only '{word}' is evidence "
                       f"here, and it means: {means}. A print that merely ran excuses nothing.")
    cand = [os.path.join(os.path.dirname(os.path.abspath(path)), _f),
            os.path.join(HERE, 'out', _f), _f]
    cp = next((c for c in cand if os.path.isfile(c)), None)
    if cp is None:
        return False, (f"It cites coupon '{_f}' for {param}, and no such file exists next to it or "
                       f"in out/. A citation to a file nobody can open is the cheapest thing in "
                       f"this system to write.")
    if os.path.realpath(cp) == os.path.realpath(path):
        return False, (f"Its {param} citation names ITSELF as the coupon. A file cannot be its own "
                       f"evidence -- this is the hole R9 still has, and it was demonstrated by "
                       f"running it: the exact bamboo base that came off as lifted strands passes "
                       f"R9 with exit 0 on one added header line naming itself.")
    try:
        cited = tuple(None if t in ('', 'None') else float(t) for t in _v.split(','))
    except ValueError:
        return False, f"Its {param} citation's value={_v!r} is not a list of numbers."
    if len(cited) != len(want):
        return False, (f"Its {param} citation carries {len(cited)} number(s); this parameter is "
                       f"{len(want)} number(s) and they are one setting, not several.")
    # THE CITATION MUST NAME WHAT THIS FILE ACTUALLY LANDS. The clause that stops a valid citation
    # being copy-pasted onto a different part.
    if not _vec_close(cited, want, TOLS[param]):
        return False, (f"Its {param} citation claims {fmt(cited)}, but this file measures "
                       f"{fmt(want)}. The citation has drifted from the part it is supposed to "
                       f"excuse.")
    chead = header_of(cp)
    cm = re.search(r'^; PRINTER=(\S+)', chead, re.M)
    if not cm:
        return False, (f"Coupon '{os.path.basename(cp)}' carries no '; PRINTER=' stamp, so nothing "
                       f"says which machine it came off. It is not re-scored under this file's "
                       f"machine -- that is how a coupon from another printer would be laundered.")
    if cm.group(1) != meas['printer']:
        return False, (f"Coupon '{os.path.basename(cp)}' is stamped PRINTER={cm.group(1)} and this "
                       f"file is {meas['printer']}. Nothing measured on one machine's plate "
                       f"licenses another's.")
    try:
        rd = datetime.date.fromisoformat(_read)
    except ValueError:
        return False, f"Its {param} citation's read={_read} is not a date."
    if rd > today:
        return False, (f"Its {param} citation is dated {rd}, which is in the future. Nobody has "
                       f"read that plate yet.")
    cmt = datetime.date.fromtimestamp(os.path.getmtime(cp))
    if rd < cmt:
        return False, (f"Its {param} citation is dated {rd}, and coupon "
                       f"'{os.path.basename(cp)}' was written {cmt}. The reading predates the "
                       f"file it claims to have read.")
    cmeas = scan(cp)
    if cmeas['est_min'] > machine.LONG_PRINT_MIN:
        return False, (f"Coupon '{os.path.basename(cp)}' is {cmeas['est_min']:.0f} min of motion, "
                       f"past the {machine.LONG_PRINT_MIN:.0f} min a coupon may be. A thing you "
                       f"bet an evening on is the bet, not the evidence for it.")
    czerr = machine.ZERR.get(cm.group(1))
    got = part_values(cp, cmeas, czerr)[param]
    # THE CLAUSE THAT MATTERS, and it is R9c's: the coupon must have EXHIBITED the value. R9's
    # ladder sweeps 0.10 to 0.35 all at 2.00 wide, so it can prove 0.15 and can NEVER prove 1.33 --
    # which is exactly the bamboo base that lifted.
    if not _vec_close(got, cited, TOLS[param]):
        return False, (f"Coupon '{os.path.basename(cp)}' does not exhibit {fmt(cited)} for {param} "
                       f"-- measured off its own moves it is {fmt(got)}. A coupon can only excuse "
                       f"what it actually did.")
    return True, (f"coupon '{os.path.basename(cp)}' measures {fmt(got)} off its own moves, was "
                  f"read as {word} on {_read}, and those are the numbers this file lands.")


def fmt(t):
    return '(' + ', '.join('None' if v is None else f'{v:g}' for v in t) + ')'


# ------------------------------------------------------------------------- the first proof ---
def first_proof_grants(logpath):
    """Every first-proof grant this gate has ever handed out, oldest first, as (row, grant).

    send-log.jsonl IS the register. There is no second file: a grant is a thing this tool did, and
    the log is the record of what this tool did. A separate register would be a second copy of the
    same fact, which is the drift machine.py's own ledger comment warns about twice.

    A ROW CARRIES A GRANT ONLY IF THE GATE ALLOWED THE SEND. A file that took a first-proof finding
    on S3 and was then refused by S8 spent nothing -- its finding is still in the row's `findings`,
    because that is what was judged, but no grant is in `first_proof`, because that is what was
    spent. Those are two different questions and the log answers both.
    """
    out = []
    if not os.path.isfile(logpath):
        return out
    with open(logpath) as fh:
        for ln in fh:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            for g in (r.get('first_proof') or []):
                out.append((r, g))
    return out


def first_proof_holder(logpath, printer, param, measured, sha):
    """Who already holds the one grant for this value on this machine? None if it is free.

    ONE FILE PER VALUE, AND THE HOLDER IS THE BYTES. Keyed on sha256 and never on a path, because a
    path is a rename and the actor at the keyboard is the one this whole tool exists to distrust.
    Keying on the bytes also makes a file hold its OWN grant across re-runs, which it must: the
    default here is a dry run, so anything else would have every dry run lock out the live send it
    was the rehearsal for.

    COMPARED WITH THE LEDGER'S OWN TOLERANCES, not with an exact float. 5.00000 and 5.00001 are one
    value to rule 4 and so they are one value here; an exact-float key would hand out a fresh grant
    per rounding, which is the whole property re-derived away.
    """
    for r, g in first_proof_grants(logpath):
        if r.get('printer') != printer or r.get('sha256') == sha or g.get('param') != param:
            continue
        v = tuple(g.get('value') or ())
        if len(v) == len(measured) and _vec_close(v, measured, TOLS[param]):
            return r
    return None


def audit_layer1(path, meas, printer, measured, zerr, today):
    """S1. R9 decides whether the first layer may print; this re-audits the EVIDENCE R9 accepted.

    A read of R9 found four holes, three of which are checkable off files and all of which a send
    gate inherits unless it says otherwise. The important one was proved by running it, not by
    reasoning: taking the stencil coupon, weakening only its offset so it lands the exact
    0.150 x 1.33 pair that came off Oleg's bamboo bucket as lifted strands, and adding ONE header
    line naming ITSELF as the coupon, turns `exit 1, "It cites no coupon"` into
    `exit 0, "EXCUSED: coupon 'selfcite.gcode' printed 0.150mm x 1.33mm and was read as welded"`.
    R9 never compares the cited path with its own. Neither does it read the coupon's own
    '; PRINTER=' (so a coupon from another machine is re-scored under this one's Z error), nor
    compare read= with anything at all (so a citation may predate the file it claims to have read).
    """
    h1, w1 = measured
    if h1 is None or w1 is None:
        return Finding('S1 first layer (h1,w1)', ABSTAIN,
                       f"no measured Z-zero error exists for {printer!r} (machine.ZERR has "
                       f"{sorted(machine.ZERR)}) or no body move deposits over a distance, so "
                       f"nothing can say where this file's first bead lands. A missing measurement "
                       f"is not a zero.")
    if any(abs(h1 - p[0]) <= 0.005 and abs(w1 - p[1]) <= TOL['w1']
           for p in machine.PROVEN_LAYER1.get(printer, [])):
        return Finding('S1 first layer (h1,w1)', PASS,
                       f"({h1:g}, {w1:g}) — machine.PROVEN_LAYER1, a pair somebody watched come "
                       f"off the plate.")
    if re.search(r'^;\s*Z_LADDER=1\s*$', meas['head'], re.M):
        return Finding('S1 first layer (h1,w1)', CITED,
                       f"({h1:g}, {w1:g}) — not proven, and this file declares '; Z_LADDER=1'. "
                       f"validate.py R9 counts that declaration against the file's own moves (3+ "
                       f"landed heights at one width) rather than believing it. A coupon is "
                       f"allowed to visit unproven gaps; that is what it is for.")
    if re.search(r'^;\s*L1_BENCH=1\s*$', meas['head'], re.M):
        return Finding('S1 first layer (h1,w1)', CITED,
                       f"({h1:g}, {w1:g}) — not proven, and this file declares '; L1_BENCH=1', "
                       f"the extrusion-level benchmark (Z ladder's mirror: one height, 3+ metered "
                       f"rates, counted off the moves by validate.py). A coupon is allowed to "
                       f"visit unproven welds; this one exists to find the flat one.")
    m = validate.COUPON_RE.search(meas['head'])
    if not m:
        return Finding('S1 first layer (h1,w1)', FAIL,
                       f"({h1:g}, {w1:g}) is not in {printer}'s proven set and carries no R9 "
                       f"'; COUPON=' citation. validate.py should already have refused this; if it "
                       f"did not, that is the finding.")
    cf, ch1, cw1, verdict, read = m.group(1), float(m.group(2)), float(m.group(3)), m.group(4), m.group(5)
    cand = [os.path.join(os.path.dirname(os.path.abspath(path)), cf),
            os.path.join(HERE, 'out', cf), cf]
    cp = next((c for c in cand if os.path.isfile(c)), None)
    if cp is None:
        return Finding('S1 first layer (h1,w1)', FAIL,
                       f"its R9 citation names '{cf}' and no such file exists.")
    if os.path.realpath(cp) == os.path.realpath(path):
        return Finding('S1 first layer (h1,w1)', FAIL,
                       f"its R9 '; COUPON=' citation names ITSELF. R9 does not check that and "
                       f"passes it with exit 0; this gate does. A file is not its own evidence.")
    chead = header_of(cp)
    cm = re.search(r'^; PRINTER=(\S+)', chead, re.M)
    if not cm:
        return Finding('S1 first layer (h1,w1)', FAIL,
                       f"coupon '{os.path.basename(cp)}' carries no '; PRINTER=' stamp. R9 scores "
                       f"it under THIS file's machine error regardless; that is laundering, not "
                       f"measurement.")
    if cm.group(1) != printer:
        return Finding('S1 first layer (h1,w1)', FAIL,
                       f"coupon '{os.path.basename(cp)}' is stamped PRINTER={cm.group(1)}, this "
                       f"file is {printer}. R9 re-measures it under {printer}'s Z error anyway.")
    try:
        rd = datetime.date.fromisoformat(read)
    except ValueError:
        return Finding('S1 first layer (h1,w1)', FAIL, f"its R9 citation's read={read} is no date.")
    cmt = datetime.date.fromtimestamp(os.path.getmtime(cp))
    if rd > today:
        return Finding('S1 first layer (h1,w1)', FAIL,
                       f"its R9 citation is dated {rd}, in the future. R9 captures read= and never "
                       f"compares it with anything.")
    if rd < cmt:
        return Finding('S1 first layer (h1,w1)', FAIL,
                       f"its R9 citation is dated {rd} and coupon '{os.path.basename(cp)}' was "
                       f"written {cmt}. The reading predates the file it claims to have read.")
    return Finding('S1 first layer (h1,w1)', CITED,
                   f"({h1:g}, {w1:g}) — not proven, EXCUSED by R9's citation of "
                   f"'{os.path.basename(cp)}' ({ch1:g} x {cw1:g}, {verdict}, read {read}), which "
                   f"R9 checked against that coupon's own moves and which this gate re-audits for "
                   f"self-reference, machine and date.")


# -------------------------------------------------------------------------------- the rules ---
def judge(path, meas, args, today, est_min, sha):
    """Every send-critical value, measured, against the ledger.

    Returns (findings, grants). `grants` are the first-proof grants this file WOULD spend; the
    caller records them only if the gate went on to allow the send, because a refused file spends
    nothing.
    """
    f, grants = [], []
    printer = meas['printer']
    zerr = machine.ZERR.get(printer) if printer else None
    led = machine.PROVEN_SEND.get(printer)

    if printer is None:
        f.append(Finding('S0 machine', ABSTAIN,
                         "the file carries no '; PRINTER=' stamp, so nothing here knows which "
                         "plate it is for. A machine with no name is not a machine with defaults."))
        return f, grants
    if led is None:
        f.append(Finding('S0 machine', ABSTAIN,
                         f"machine.PROVEN_SEND has no entry for {printer!r} — only "
                         f"{sorted(machine.PROVEN_SEND)}. Nothing has been accepted off that "
                         f"machine, so nothing here can say a value is proven on it."))
        return f, grants

    want = part_values(path, meas, zerr)

    def rule(name, param, measured, proven_rows, applies, na_note, abstain_note):
        """One rule, five outcomes, and the difference between N/A and ABSTAIN is still the point.

        `proven_rows` are (value..., provenance) tuples; the provenance is the last element."""
        if not applies:
            f.append(Finding(name, NA, na_note))
            return
        if any(v is None for v in measured):
            # ABSTENTION IS NEVER RELAXED BY RULE 6, and this early return is where that is
            # enforced. First proof is for a value NOTHING HAS PROVEN; an abstention is a value
            # NOTHING HAS MEASURED, and handing the second a grant would mean a file with an
            # unreadable prime goes to a plate on the strength of being short. That is the exact
            # inversion R4b already ran here -- 'NOT MEASURED' printed on three files that all
            # still reported green.
            f.append(Finding(name, ABSTAIN, abstain_note))
            return
        hit = [r for r in proven_rows if _vec_close(tuple(r[:-1]), measured, TOLS[param])]
        if hit:
            f.append(Finding(name, PASS, f"{fmt(measured)} — proven: {hit[0][-1]}"))
            return
        ok, note = check_citations(path, param, measured, meas, zerr, today)
        if ok:
            f.append(Finding(name, CITED, f"{fmt(measured)} — not in the ledger, EXCUSED: {note}"))
            return

        # RULE 6, AND THIS IS THE ONLY PLACE IT REACHES. Everything above has already run: the value
        # is applicable, MEASURED, absent from the ledger, and carries no citation that survives
        # check_citations. That is precisely rule 4's refusal and nothing else, which is why the
        # grant lives inside `rule()` rather than beside the findings list -- S1's R9 audit, S7's
        # header-vs-moves contradiction, S7's unfittable arcs and S8's self-disclaimer are all
        # written outside this function and are all out of reach BY CONSTRUCTION rather than by a
        # list of exceptions somebody has to keep in sync.
        known = ' | '.join(fmt(tuple(r[:-1])) for r in proven_rows) or 'nothing yet'
        base = (f"{fmt(measured)} is NOT proven on {printer}. What has been accepted: {known}. "
                f"{note}")
        cite = (f"Print a coupon, read the plate, then cite it: '; SEND_COUPON={param} file=<f> "
                f"value={','.join('' if v is None else f'{v:g}' for v in measured)} "
                f"verdict={VERDICT[param][0]} read=<date>'.")
        if est_min > FIRST_PROOF_MAX_MIN:
            f.append(Finding(name, FAIL,
                             f"{base} It is {est_min:.1f} min of motion, past the "
                             f"{FIRST_PROOF_MAX_MIN:g} min under which a file may establish a value "
                             f"nothing has proven, so first proof does not reach it. {cite}"))
            return
        held = first_proof_holder(args.log, printer, param, measured, sha)
        if held is not None:
            f.append(Finding(name, FAIL,
                             f"{base} First proof for this value was already granted to "
                             f"'{os.path.basename(held.get('file') or '?')}' "
                             f"(sha256 {(held.get('sha256') or '')[:12]}, {held.get('ts')}), and it "
                             f"is granted to ONE file. A second free pass on the same unproven "
                             f"number is not a first proof, it is the number spreading. Send that "
                             f"file, read the plate, `send.py accept` it — or {cite[0].lower()}"
                             f"{cite[1:]}"))
            return
        grants.append({'rule': name, 'param': param, 'value': list(measured),
                       'est_min': round(est_min, 2), 'known': known})
        f.append(Finding(name, FIRSTPROOF,
                         f"{fmt(measured)} is NOT proven on {printer} (accepted: {known}) and "
                         f"nothing can prove it but a plate. This file is {est_min:.1f} min of "
                         f"motion, inside the {FIRST_PROOF_MAX_MIN:g} min a file may go unproven, "
                         f"so it goes as THE ONE FILE that establishes it."))

    # S1  THE FIRST LAYER. NO SECOND HATCH IS OPENED HERE, deliberately: R9 already owns this
    # parameter and its '; COUPON=' stamp, validate.py has already run, and a send gate that
    # invented a parallel '; SEND_COUPON=layer1' would be a way to opt out of R9 through a door R9
    # cannot see. What this rule adds is an AUDIT of R9's own stamp, closing the three holes an
    # independent read of R9 found and demonstrated by running it.
    f.append(audit_layer1(path, meas, printer, want['layer1'], zerr, today))

    # S2  COVERAGE. w1 AND pitch, as one setting, because either alone is meaningless.
    rule('S2 floor coverage (w1,pitch)', 'coverage', want['coverage'], led['coverage'],
         applies=True, na_note='',
         abstain_note=(f"layer 1 has {meas['l1_lines']} body move(s) and "
                       f"{meas['pitch_hor'][1]}/{meas['pitch_ver'][1]} distinct parallel-run "
                       f"coordinates — under 3 there is no gap to take a mode of, so the pitch is "
                       f"NOT MEASURED and this rule has checked nothing. Abstention blocks the "
                       f"send; R4b printed 'NOT MEASURED' on three files that all still read "
                       f"green."))

    # S3  THE PRIME.
    rule('S3 prime (purge,fat,stationary)', 'prime', want['prime'], led['prime'],
         applies=True, na_note='',
         abstain_note=(f"{meas['prime_moves']} move(s) are tagged PRIME and none of them deposits "
                       f"anything measurable, so the opening sequence is NOT MEASURED. A file with "
                       f"no readable prime is not a file with a proven one."))

    # S4  SPAN.
    rule('S4 bridge span', 'span', want['span'], led['span_mm'],
         applies=meas['span_n'] > 0,
         na_note="no '; BRIDGE' or '; THIN CROSS' move in this file — nothing crosses air.",
         abstain_note="crossings exist but none has a measurable length.")

    # S5  CROSSING SPEED.
    rule('S5 crossing speed', 'cross', want['cross'], led['cross_mms'],
         applies=meas['cross_n'] > 0,
         na_note="no '; THIN CROSS' move in this file — there is no second speed regime.",
         abstain_note="thin crossings exist but carry no feedrate.")

    # S6  TEMPERATURE.
    rule('S6 temps (nozzle,bed)', 'temps', want['temps'], led['temps'],
         applies=True, na_note='',
         abstain_note="the file commands no M104/M109 or no M140/M190 before the body, so nothing "
                      "says what it will be printed at.")

    # S7  THE FIT. Declared bore CROSS-EXAMINED against a measured toolpath radius, because prose
    # has drifted from the moves twice on this project and a bore is the one number here that was
    # guessed twice and wrong twice.
    bd, bm = meas['bore_declared'], bore_measured(meas)
    if bd is None:
        f.append(Finding('S7 fit (bore)', NA,
                         "this file declares no bore — there is no fit to be wrong about."))
    elif bm is None:
        f.append(Finding('S7 fit (bore)', ABSTAIN,
                         f"the header declares a {bd:.3f}mm bore, and no arc at z>={meas['arc_z']} "
                         f"could be fitted to a trustworthy circle "
                         f"({meas['arc_runs']} contiguous run(s), {meas['arc_good']} within 0.01mm "
                         f"residual). A declared bore this gate cannot measure is a declared bore "
                         f"it has not checked."))
    elif abs(bm - bd) > TOL['bore']:
        f.append(Finding('S7 fit (bore)', FAIL,
                         f"the header declares a {bd:.3f}mm bore and the emitted arcs measure "
                         f"{bm:.3f}mm (toolpath radius {meas['arc_r'][0]:.4f} on "
                         f"{meas['arc_r'][1]} run(s), bead {meas['bead_w']}). The header is prose; "
                         f"the moves are the file."))
    else:
        rule('S7 fit (bore)', 'fit', (bm,), led['fit_bore'], applies=True, na_note='',
             abstain_note='')

    # S8  THE FILE'S OWN REFUSAL TO CLAIM SOMETHING A SEND DEPENDS ON.
    # The generators already write down what they could not prove. Nothing read it, so the nine-hour
    # file went to a plate carrying its own sentence saying it DECLINES to claim the fit that whole
    # part is for. This is the cheapest guard in the file and it is pure artifact: the file's bytes.
    SELF = ["DECLINES to claim a fit", "This span is UNPROVEN"]
    said = [s for s in SELF if s in meas['head']]
    if said:
        f.append(Finding('S8 self-declared unproven', FAIL,
                         "this file's own header says " +
                         '; '.join(f'"{s}"' for s in said) +
                         ". The generator wrote down what it could not prove and then nothing read "
                         "it. A part whose own file declines to claim the property it exists for "
                         "does not go to a plate on somebody's judgement."))
    else:
        f.append(Finding('S8 self-declared unproven', PASS,
                         "the header claims nothing it also disclaims."))

    return f, grants


# --------------------------------------------------------------------------------- the send ---
def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def upload_and_start(host, path):
    """Moonraker. Reached ONLY from --live, which refuses without an explicit --printer-host, so
    there is no host constant anywhere in this file for an accident to find."""
    import urllib.request
    # MOONRAKER LISTENS ON :7125; a bare IP lands on the printer's own web UI, which answers
    # "501 Not Implemented". That exact refusal is in send-log.jsonl twice, a month apart
    # (2026-08-06T20:29 and 2026-08-31), each time fixed by retyping the host with the port.
    # The port is a protocol fact — tools/push.py carries the same :7125 on every call — so it
    # is defaulted here. Naming the MACHINE stays on the caller, on purpose.
    if ':' not in host:
        host = f'{host}:7125'
    name = os.path.basename(path)
    boundary = '----crackle' + hashlib.sha1(str(time.time()).encode()).hexdigest()[:16]
    with open(path, 'rb') as fh:
        blob = fh.read()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n').encode() + blob + \
           f'\r\n--{boundary}--\r\n'.encode()
    req = urllib.request.Request(f'http://{host}/server/files/upload', data=body, method='POST')
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    with urllib.request.urlopen(req, timeout=600) as r:
        up = r.read().decode()[:400]
    import urllib.parse
    q = urllib.parse.urlencode({'filename': name})
    req = urllib.request.Request(f'http://{host}/printer/print/start?{q}', data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        st = r.read().decode()[:400]
    return {'upload': up, 'start': st}


def record(logpath, row):
    with open(logpath, 'a') as fh:
        fh.write(json.dumps(row, sort_keys=True) + '\n')


def cmd_send(args):
    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        print(f"send: no such file {path}")
        return 2
    today = datetime.date.today()
    t0 = time.time()

    meas = scan(path)
    sha = sha256(path)
    print(f"\n{'=' * 96}\nSEND GATE  {path}")
    print(f"  {os.path.getsize(path) / 1e6:.1f} MB   ledger {machine.SEND_LEDGER_VERSION}   "
          f"machine.py {sha256(os.path.join(HERE, 'machine.py'))[:12]}")
    print(f"\n-- validate.py (the file gate; this tool refuses on any failure) "
          f"{'-' * 26}")
    try:
        v_ok, v_min = validate.check(path)
    except Exception as e:                                  # noqa: BLE001
        v_ok, v_min = False, meas['est_min']
        print(f"  validate.py RAISED: {type(e).__name__}: {e}")

    print(f"\n-- measured off the emitted file {'-' * 62}")
    print(f"  printer={meas['printer']}  bead={meas['bead_w']}  layer-1 body moves="
          f"{meas['l1_lines']}  arcs={meas['arc_good']}/{meas['arc_runs']} fitted")
    print(f"  est {v_min:.1f} min (validate) / {meas['est_min']:.1f} min (this tool, "
          f"independent integration)")
    print(f"  pitch: horizontal {meas['pitch_hor']}  vertical {meas['pitch_ver']}  -> "
          f"{meas['pitch']}")
    print(f"  prime: purge={meas['purge_mm']} fat={meas['prime_fat']} "
          f"stationary={meas['stationary_mm']} lead-in={meas['lead_mm']:.2f}mm")
    print(f"  spans: n={meas['span_n']} max={meas['span_max']:.2f} modal={meas['span_modal']}   "
          f"cross: n={meas['cross_n']} speeds={meas['cross_spread']}")
    print(f"  bore: declared={meas['bore_declared']} measured={bore_measured(meas)}")

    # THE DURATION RULE 6 IS BOUNDED BY IS THE PESSIMISTIC ONE OF TWO INDEPENDENT INTEGRATIONS --
    # validate.py's and this tool's own pass over the same moves. They agree to 0.01 min on every
    # file here, and taking the max is what makes that agreement load-bearing instead of decorative:
    # if they ever diverge, the disagreement cannot be what buys a longer file a free pass.
    gate_min = max(v_min, meas['est_min'])
    findings, grants = judge(path, meas, args, today, gate_min, sha)
    print(f"\n-- send ledger {'-' * 80}")
    for fi in findings:
        print(f"  {fi.status:11s} {fi.rule:28s} {fi.text}")

    blocked = [fi for fi in findings if fi.status in BLOCKING]
    # A FIRST-PROOF FINDING COUNTS AS COUPON-GRADE EVIDENCE FOR RULE 5, and it is weaker than one.
    # The two bands cannot overlap while 25 < 90, so this line changes nothing today; it is here so
    # that moving either constant cannot silently open a door, because the failure mode of leaving
    # it out is a nine-hour plate carrying a value nothing has ever tested.
    cited = [fi for fi in findings if fi.status in (CITED, FIRSTPROOF)]

    # RULE 5. A coupon proves a value AT COUPON SCALE; betting an evening on it is a second
    # decision and it is asked separately. The override is explicit and it is RECORDED.
    long_block = None
    if cited and v_min > machine.LONG_PRINT_MIN:
        names = ', '.join(fi.rule for fi in cited)
        if args.allow_long and args.why:
            print(f"\n  OVERRIDE  {v_min:.0f} min with coupon-only evidence for {names} — allowed "
                  f"by --allow-long, recorded: {args.why!r}")
        else:
            long_block = (f"{v_min:.0f} min of motion, and the only evidence for {names} is a "
                          f"coupon. A coupon proves a value at coupon scale; "
                          f"{machine.LONG_PRINT_MIN:.0f} min is ~4x the longest coupon anybody "
                          f"here has read off a plate. Re-run with --allow-long --why \"...\" if "
                          f"that bet is deliberate; it will be recorded.")
            print(f"\n  {'FAIL':11s} {'S9 long print':28s} {long_block}")

    ok = v_ok and not blocked and long_block is None
    overridden = []
    if getattr(args, 'oleg_said', None) and not ok and v_ok:
        # THE HUMAN OVERRIDE. This gate exists to stop the AI deciding to print; it was never meant
        # to overrule Oleg, who is the only person who can accept a print at all (`accept` already
        # refuses any --by that is not him). Without this the only way to honour "print it anyway"
        # was a raw Moonraker upload leaving NO RECORD of what was overridden, and an unrecorded
        # bypass is strictly worse than a recorded override. It covers the LEDGER rules only, values
        # nothing has proven YET, which is exactly the axis a human at the machine gets to judge. It
        # never reaches validate.py: that gate catches DEFECTS, and no instruction turns a defect
        # into a plan.
        # Reuse the gate's OWN `blocked` list rather than recomputing which statuses count. A
        # parallel definition of "blocking" is how an override silently stops covering a rule
        # somebody adds later.
        overridden = ['%s (%s)' % (fi.rule, fi.status) for fi in blocked]
        if long_block is not None:
            overridden.append('S9 long print')
        print("\n  OVERRIDE BY OLEG, recorded rather than waived silently.")
        print("    his words:  %r" % (args.oleg_said,))
        print("    overriding: %s" % (', '.join(overridden) or '(nothing was blocking)'))
        print("    validate.py still had to pass, and did. This override never reaches it.")
        ok = True
    if not v_ok:
        print(f"\n  REFUSED: validate.py refuses this file. The send gate does not overrule the "
              f"file gate.")

    # --live WITH NO HOST IS DECIDED HERE, ABOVE THE GRANT, and the order is the whole point. It
    # used to be settled after the row was built, which meant a typed `--live` with no host spent
    # the one first-proof grant for a value and printed "GRANTED, and SPENT" directly above a
    # REFUSED verdict. Nothing was uploaded and nothing was judged differently, so nothing should
    # have been spent: a usage error must not cost the gauge its one pass.
    if ok and args.live and not args.printer_host:
        print("\n  REFUSED: --live needs an explicit --printer-host. There is no default host "
              "in this file, on purpose — nothing can reach a printer by accident.")
        ok = False

    # LOUD, because a grant that reads like a tick is a grant nobody will notice being spent. This
    # block says what has never been tested, that this file is the one about to test it, and that
    # nothing else gets to carry the same number afterwards.
    if grants:
        print(f"\n-- FIRST PROOF (rule 6) {'-' * 71}")
        for g in grants:
            print(f"  {g['rule']}  {fmt(tuple(g['value']))}")
            print(f"      Nothing has ever been accepted here except {g['known']}. No coupon exists "
                  f"to cite, because a coupon is a print and this is the print.")
            print(f"      {gate_min:.1f} min of motion, under the {FIRST_PROOF_MAX_MIN:g} min "
                  f"ceiling. Worst overhead seen on this machine is +11.0 min of wall clock.")
        if ok:
            print(f"\n  GRANTED, and SPENT: after this row, no other file may carry these numbers "
                  f"under first proof.")
            print(f"  Read the plate, then:  python3 send.py accept {os.path.basename(path)} "
                  f"--by oleg --verdict held --observed \"...\"")
        else:
            print(f"\n  NOT GRANTED: this send is REFUSED for the reason(s) above, and a refused "
                  f"file spends nothing. The value is still unproven and still free.")

    row = {
        'ts': datetime.datetime.now().isoformat(timespec='seconds'),
        'file': path, 'sha256': sha, 'bytes': os.path.getsize(path),
        'ledger_version': machine.SEND_LEDGER_VERSION,
        'machine_py_sha256': sha256(os.path.join(HERE, 'machine.py')),
        'printer': meas['printer'],
        'validate_ok': v_ok, 'est_min_validate': round(v_min, 2),
        'est_min_send': round(meas['est_min'], 2),
        'measured': {k: list(v) for k, v in part_values(path, meas, machine.ZERR.get(meas['printer'] or '')).items()},
        'pitch': meas['pitch'], 'span_max': meas['span_max'], 'cross_mms': meas['cross_mms'],
        'bore_declared': meas['bore_declared'], 'bore_measured': bore_measured(meas),
        'findings': [{'rule': fi.rule, 'status': fi.status, 'text': fi.text} for fi in findings],
        'citations': [{'param': s[0], 'file': s[1], 'value': s[2], 'verdict': s[3], 'read': s[4]}
                      for s in COUPON_RE.findall(meas['head'])],
        'long_print_block': long_block,
        # WHAT WAS SPENT, not what was judged. `findings` above already carries every FIRST-PROOF
        # verdict this file drew, refused or not; this key carries only the grants that actually
        # went, and it is what first_proof_holder() reads back. A refused file leaves it [] and its
        # value stays free for the next one -- which is why this is `if ok` and not `if grants`.
        'first_proof': grants if ok else [],
        'first_proof_max_min': FIRST_PROOF_MAX_MIN,
        'override_allow_long': bool(args.allow_long), 'override_why': args.why,
        # His words go in VERBATIM and the overridden rules by name, so a later failure can be
        # traced to the decision that allowed it rather than to a bare "ALLOWED".
        'override_oleg_said': getattr(args, 'oleg_said', None), 'override_rules': overridden,
        'verdict': 'ALLOWED' if ok else 'REFUSED',
        'live': False, 'elapsed_s': round(time.time() - t0, 1),
    }

    if ok and args.live:
        # The missing-host case is already settled above, so reaching here means a host was named.
        row['live'] = True
        row['host'] = args.printer_host
        try:
            row['moonraker'] = upload_and_start(args.printer_host, path)
            print(f"\n  SENT to {args.printer_host}: {row['moonraker']}")
        except Exception as e:                              # noqa: BLE001
            row['moonraker_error'] = f"{type(e).__name__}: {e}"
            row['verdict'] = 'SEND-FAILED'
            ok = False
            # THE GRANT STAYS SPENT ON A FAILED UPLOAD, deliberately, and it is the one case where
            # a REFUSED-looking row keeps one. The gate said yes and this file is the one that was
            # allowed to establish the value; a broken socket does not hand the pass to a different
            # artifact. Re-running these same bytes still holds it, because the holder is the sha.
            print(f"\n  SEND FAILED: {row['moonraker_error']}")

    record(args.log, row)
    print(f"\n  {'ALLOWED' if ok else 'REFUSED'}"
          f"{' (DRY RUN — nothing was uploaded; --live to send)' if ok and not args.live else ''}"
          f"   recorded in {args.log}")
    print('=' * 96)
    return 0 if ok else 1


# ------------------------------------------------------------------------------- acceptance ---
# COMPLETION IS NOT ACCEPTANCE. The 100mm bucket completed for weeks against a wrong Z zero, masked
# by 1.52x layer-1 flow, and was then read as a baseline. So these words are refused by name.
NOT_ACCEPTANCE = {
    'completed': "a print that completed is a print that completed. The 100mm bucket completed for "
                 "weeks against a wrong Z zero and emits no SET_GCODE_OFFSET at all.",
    'finished': "same as completed.",
    'printed': "printed is not read, and read is not held.",
    'done': "done is not a observation of anything.",
    'ok': "'ok' names nothing that was looked at.",
    'success': "success is a summary, not an observation.",
}


def cmd_accept(args):
    """PRINT the ledger entry a human should paste. This tool never writes machine.py.

    WHY IT CANNOT WRITE. The actor that decides to print must not hold the key to the set it is
    checked against; a gate whose evidence it can author is a gate it can talk itself past. So
    admission costs a source edit and a commit message, which is the repo's own durable record --
    and it is bound here to two things this tool cannot fabricate: a LIVE send of this exact
    sha256 already in send-log.jsonl, and a named human saying a named word."""
    path = os.path.abspath(args.file)
    if not os.path.isfile(path):
        print(f"accept: no such file {path}")
        return 2
    if args.by != 'oleg':
        print(f"accept: --by {args.by!r}. Only Oleg accepts a print. Money, commitments and "
              f"'did it hold' are his; everything else is execution.")
        return 1
    if args.verdict in NOT_ACCEPTANCE:
        print(f"accept: verdict={args.verdict!r} — {NOT_ACCEPTANCE[args.verdict]} The word is "
              f"'held': the part came off the plate in one piece and did the thing it was for.")
        return 1
    if args.verdict != 'held':
        print(f"accept: verdict={args.verdict!r} is not a word this gate knows. Use 'held'.")
        return 1
    if not args.observed or len(args.observed) < 25:
        print("accept: --observed must say what was actually LOOKED AT, in a sentence. "
              "A ledger entry with no story is a number nobody can argue with.")
        return 1

    sha = sha256(path)
    sends = []
    if os.path.isfile(args.log):
        for ln in open(args.log):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get('sha256') == sha and r.get('live') and r.get('verdict') == 'ALLOWED':
                sends.append(r)
    if not sends:
        print(f"accept: no LIVE send of this exact file (sha256 {sha[:12]}) appears in "
              f"{args.log}. A value cannot enter the ledger on the strength of a print nobody "
              f"can show went to a machine. If it was sent by hand, that is the thing this gate "
              f"exists to stop, and the honest fix is to send the next one through it.")
        return 1

    meas = scan(path)
    zerr = machine.ZERR.get(meas['printer'])
    vals = part_values(path, meas, zerr)
    print(f"\nACCEPTED by {args.by} on {datetime.date.today()}, verdict={args.verdict}")
    print(f"  file    {path}")
    print(f"  sha256  {sha}")
    print(f"  sent    {sends[-1]['ts']} to {sends[-1].get('host')}")
    print(f"  seen    {args.observed}")
    print(f"\nPASTE INTO machine.PROVEN_SEND[{meas['printer']!r}] (this tool does not write it):\n")
    prov = (f"{args.observed} — {os.path.basename(path)}, sent {sends[-1]['ts'][:10]}, "
            f"accepted by {args.by} {datetime.date.today()}")
    for key, param in (('coverage', 'coverage'), ('prime', 'prime'), ('span_mm', 'span'),
                       ('cross_mms', 'cross'), ('temps', 'temps'), ('fit_bore', 'fit')):
        v = vals[param]
        if any(u is None for u in v):
            continue
        nums = ', '.join('None' if u is None else f'{u:g}' for u in v)
        print(f'    "{key}": [... , ({nums}, "{prov}")],')
    h1, w1 = vals['layer1']
    if h1 is not None and w1 is not None:
        print(f'\n  and machine.PROVEN_LAYER1[{meas["printer"]!r}]: ({h1:g}, {w1:g})   '
              f'# {prov}')
    print("\nBump machine.SEND_LEDGER_VERSION in the same edit, and commit it.")
    return 0


def cmd_ledger(args):
    print(f"send ledger {machine.SEND_LEDGER_VERSION}   "
          f"long-print threshold {machine.LONG_PRINT_MIN:g} min   "
          f"first-proof ceiling {FIRST_PROOF_MAX_MIN:g} min")
    for pr, d in machine.PROVEN_SEND.items():
        print(f"\n{pr}")
        print(f"  layer1 (from machine.PROVEN_LAYER1): "
              f"{machine.PROVEN_LAYER1.get(pr, [])}")
        for k, rows in d.items():
            if not rows:
                print(f"  {k}: EMPTY — nothing here has ever been accepted, so every file that "
                      f"has one must cite a coupon.")
            for r in rows:
                print(f"  {k}: {fmt(tuple(r[:-1]))}\n      {r[-1]}")

    # THE SECOND HALF OF THE LEDGER, AND IT IS NOT THE SAME KIND OF THING. Everything above came off
    # a plate somebody read. Everything below is a value that has never been tested and is on its
    # way to being tested exactly once. Printing them under one heading would be the overselling the
    # whole gate exists to refuse, so they are printed apart and the difference is named.
    print(f"\nFIRST PROOF (rule 6) — values that went to a plate UNPROVEN, one file each.")
    print(f"  NOT evidence. A grant means 'nothing has ever tested this and one file was allowed "
          f"to'. It becomes evidence only when a plate is read and `send.py accept` puts it above.")
    # ONE GRANT PER HOLDER, NOT ONE PER ROW. A file holds its own grant across re-runs, so every
    # dry run of the holder appends another identical row; listing them all would report ONE value
    # as having been granted four times, which is the opposite of what the register is for.
    seen, spent = {}, []
    for r, g in first_proof_grants(args.log):
        k = (r.get('printer'), g.get('param'), r.get('sha256'))
        if k in seen:
            seen[k][2] += 1
            if r.get('live'):
                seen[k][0] = r            # a live send is the row worth naming, whenever it happened
            continue
        seen[k] = [r, g, 1]
        spent.append(k)
    if not spent:
        print(f"\n  nothing yet — no first-proof grant appears in {args.log}.")
    for k in spent:
        r, g, runs = seen[k]
        print(f"\n  {r.get('printer')}  {g.get('param')}: {fmt(tuple(g.get('value') or ()))}")
        print(f"      GRANTED TO  {os.path.basename(r.get('file') or '?')}  "
              f"sha256 {(r.get('sha256') or '')[:12]}")
        print(f"      {r.get('ts')}   {g.get('est_min')} min of motion   "
              f"{'SENT LIVE to ' + str(r.get('host')) if r.get('live') else 'dry run, NOT SENT'}"
              f"{f'   ({runs} runs of these bytes)' if runs > 1 else ''}")
        print(f"      at the time, accepted here was: {g.get('known')}")
        print(f"      SPENT. No other file may carry these numbers under first proof.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd')

    s = sub.add_parser('send', help='check a file and (with --live) send it')
    s.add_argument('file')
    s.add_argument('--live', action='store_true',
                   help='actually upload and start. Default is a dry run.')
    s.add_argument('--printer-host', default=None,
                   help='REQUIRED by --live. There is no default host in this file.')
    s.add_argument('--allow-long', action='store_true')
    s.add_argument('--oleg-said', metavar='WORDS',
                   help="Oleg's VERBATIM instruction to send a file this gate refuses on ledger "
                        "grounds. Only he can accept a print, so only he can overrule an unproven "
                        "value; this makes that decision RECORDED instead of a silent bypass. It "
                        "does not reach validate.py, which catches defects rather than judgements.")
    s.add_argument('--why', default=None)
    s.add_argument('--log', default=DEFAULT_LOG)
    s.set_defaults(fn=cmd_send)

    a = sub.add_parser('accept', help='print the ledger entry for a print Oleg accepted')
    a.add_argument('file')
    a.add_argument('--by', required=True)
    a.add_argument('--verdict', required=True)
    a.add_argument('--observed', default=None)
    a.add_argument('--log', default=DEFAULT_LOG)
    a.set_defaults(fn=cmd_accept)

    l = sub.add_parser('ledger', help='print the ledger, its provenance, and spent first proofs')
    l.add_argument('--log', default=DEFAULT_LOG)
    l.set_defaults(fn=cmd_ledger)

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ('send', 'accept', 'ledger', '-h', '--help'):
        argv = ['send'] + argv          # `send.py FILE` is the common case
    args = ap.parse_args(argv)
    if not getattr(args, 'fn', None):
        ap.print_help()
        return 2
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
