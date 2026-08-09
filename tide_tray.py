#!/usr/bin/env python3
"""ORBE TIDE -- Hilbert ASMR tray generator. Spec: ~/dev/Assist/guides/orbe-tray-spec.md.

A shallow square tray whose floor carries a closed MOORE curve as a field of printed ridges.
Pour in 8mm steel balls, tilt and rake: every crossing is a click, dozens at once are rain.
Path-native: no CAD, no STL, no slicer. One thin line draws everything, every segment starts
where the last ended.

    rim    single-bead wall to 0.66 x ball above the floor top -- captures past the equator
    ridges one closed Moore loop per ridge layer, walked in the same direction every layer
    floor  solid welded plate (L1 + N body layers) -- the soundboard

STAGE, honestly (spec section 6): NOTHING EMITTED HERE HAS PRINTED. Every acoustic number is
UNPROVEN until a coupon converts it through Oleg's ear. The headers say so.

SEQUENCING (spec section 3), one stroke per part:
    floor layers   boustrophedon raster (axis alternating per layer), ending at the perimeter,
                   then the rim ring -- every interface a lap >= 0.2 bead (the qa_weld law;
                   a commanded butt is a landed gap)
    ridge layers   rim ring A -> A, spoke inward A -> B (extruded), full Moore loop B -> B,
                   spoke back B -> A, Z step at A. The doubled spoke is a declared 2x radial
                   rib welding field to rim; the weld gate measures it
    rim layers     closed ring loops to the rim height -- 0.82x0.24 single-bead walls are
                   proven bonding (the bucket towers stand 300mm+ on this profile)

GATES (each proven able to fire -- run --selftest to watch all six refuse):
    bounds             part + layer-1 skirt outside the probed mesh (minus margin)
    ridge-fuse         pitch - bead < 0.3mm: the field welds into a slab, the comb is gone
    channel-impossible --mode channel whose groove cannot pass the ball: refuse the
                       impossible rather than default to it (the wrap-deg 210 lesson)
    one-stroke         any dry XY move inside a part's body; the tray allows none at all,
                       the coupon allows only lifted '; HOP' moves between patches
    weld ATTACH        the raster must lap the rim ring on every judged floor layer
                       (border walked in 0.5mm steps, capsule overlap >= 0.05mm margin)
    weld NO-PILE       no spot deeper than 2.7 bead-heights; the spoke junctions are the
                       declared corridor (reported, never judged); a third spoke pass fires it

DEVIATIONS FROM THE SPEC, NAMED (spec section 3 asks for them here, not in a report):
  * C1 coupon reading: "three order-2 Moore patches at p 5.6/6.9/8.8, two ridge heights per
    plate run" is implemented as ONE plate of SIX patches -- 3 pitches x 2 ridge heights
    (6 and 10 layers) -- so a single run covers the full bracket and one calibration block is
    paid instead of two. The patches are layer-interleaved with lifted tagged hops, not
    sequential (a finished 5mm patch stands taller than the nozzle tip clearance).
  * Coupon motion is ~66 min DERIVED off the emitted moves, not the spec prose's ~15 min:
    six full-code-path floors at the 0.2-bead lap pitch dominate, exactly as the tray's own
    budget paragraph says the floor dominates. The spec's 15 was never derived; this is.
  * Tray budget: the spec prose says ~28g / ~50min "floor dominates (~113m)"; the emitted
    file derives more grams because the prose counted only the floor's metres. The header
    carries the derived numbers.
  * Coupon rim stub height is unstated in the spec; here it is ridge height + 4 rim-only
    layers (~1mm above the field), enough to prove the rim weld and keep raked balls in.
  * CHANNEL mode v1 emits the same geometry as RIDGE once its gate passes (groove >= ball);
    a deeper captive-channel design is deferred -- the spec calls it a documented flag, not
    the first plate.
"""
import argparse
import math
import os
import sys as _sys

import machine
from hilbert import curve, round_corners

BW = machine.SLICER_LINE_W          # 0.82 -- the K2 Plus 0.8-nozzle bead, read off the slicer
FLOOR1_OVERLAP = 0.80               # layer-1 raster pitch = 0.80 x w1 (the ratio law; the only
                                    # floor that has ever welded overlaps by a fifth of a bead)
EDGE_LAP = 0.80                     # every interface laps 0.2 bead: neighbour pitch and the
                                    # raster-to-ring inset are both 0.80 x the landed width
RING_FILLET = 2.0                   # mm -- rim corners become arcs that hold speed
WELD_MARGIN = 0.05                  # mm of capsule overlap below which a joint is a butt
PILE_DEPTH = 2.7                    # bead-heights of material depth a spot may carry
PILE_CELL = 0.4                     # mm -- depth-summing cell (qa_weld's own instrument)
ATTACH_STEP = 0.5                   # mm -- border walk step
JUNCTION_R = 1.6                    # mm around the spoke feet: the declared pile corridor
HOP_LIFT = 0.8                      # mm above the current layer for inter-patch hops
COUPON_GAP = 10.0                   # mm between coupon patch bounding boxes
BED_MARGIN = 6.0                    # mm the part must keep inside the probed mesh window


def sink_mm(ball_d, p):
    """How deep a ball sits between two ridge crowns at pitch p (line-contact model, spec s2).
    None = the pitch exceeds the ball: it falls through to the floor (cell-hop)."""
    r = ball_d / 2.0
    if p >= ball_d:
        return None
    return r - math.sqrt(r * r - (p / 2.0) ** 2)


def ride_verdict(ball_d, p, ridge_h):
    """DERIVED, unheard (claim A3): what the ball does on this field. A model, not a fact."""
    s = sink_mm(ball_d, p)
    if s is None:
        return None, "cell-hop: pitch > ball, it drops to the floor (thunk, not rain)"
    if ridge_h > s:
        return s, f"crown-ride: h {ridge_h:.2f} > sink {s:.2f} (bright, floor decoupled)"
    return s, f"floor-touch: h {ridge_h:.2f} < sink {s:.2f} (soundboard-coupled)"


# ----------------------------------------------------------------------------- geometry ---

def close_ring(pts):
    if math.dist(pts[0], pts[-1]) > 1e-9:
        pts = pts + [pts[0]]
    return pts


def rot_closed(pts, i):
    """Rotate a closed polyline to start (and end) at vertex i."""
    core = pts[:-1]
    return close_ring(core[i:] + core[:i])


def project_onto(pts, p):
    """(point, seg_index) -- the nearest point on polyline `pts` to p."""
    best, bi, bd = pts[0], 0, float("inf")
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 < 1e-18 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
        q = (a[0] + dx * t, a[1] + dy * t)
        d = math.dist(p, q)
        if d < bd:
            best, bi, bd = q, i, d
    return best, bi


def ring_from(pts, p):
    """The closed ring rotated to start at the projection of p onto it (vertex inserted)."""
    q, i = project_onto(pts, p)
    core = pts[:-1]
    if math.dist(q, pts[i]) > 1e-6 and math.dist(q, pts[i + 1]) > 1e-6:
        core = core[:i + 1] + [q] + core[i + 1:]
        i = i + 1
    else:
        i = i if math.dist(q, pts[i]) <= 1e-6 else (i + 1) % len(core)
    return rot_closed(close_ring(core), i)


def rounded_square(side, cx, cy, fillet, min_seg):
    h = side / 2.0
    sq = [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h), (cx - h, cy - h)]
    return machine.decimate(round_corners(sq, fillet), min_seg)


def raster_pts(h, pitch, axis, sx, sy, cx, cy):
    """Serpentine over a square of half-side h centred on (cx,cy). Rows run along `axis`
    ('x'|'y'); (sx,sy) pick the start corner. Row spacing is recomputed to fit exactly, only
    ever DENSER than asked -- an interface lap may grow, never shrink."""
    n = max(2, int(math.floor(2 * h / pitch)) + 1)
    step = 2 * h / (n - 1)
    pts = []
    for j in range(n):
        c = sy * h - sy * j * step          # cross-axis position, walking inward from sy side
        a, b = sx * h, -sx * h              # row runs from the sx side to the far side
        if j % 2 == 1:
            a, b = b, a
        if axis == "x":
            pts += [(cx + a, cy + c), (cx + b, cy + c)]
        else:
            pts += [(cx + c, cy + a), (cx + c, cy + b)]
    return pts, step


class Part:
    """One tray (or coupon patch): geometry precomputed, layers yielded as continuous strokes."""

    def __init__(self, cx, cy, pitch, order, ridge_layers, rim_only_layers,
                 floor_body_layers, w1, h1, lh, fillet=0.0, label="tray",
                 spoke_passes=2, edge_lap=EDGE_LAP):
        self.cx, self.cy, self.p, self.order = cx, cy, pitch, order
        self.label = label
        self.spoke_passes = spoke_passes
        self.edge_lap = edge_lap
        self.w1, self.h1, self.lh = w1, h1, lh
        self.n_floor = 1 + floor_body_layers
        self.n_ridge = ridge_layers
        self.n_rim = rim_only_layers
        self.layers = self.n_floor + self.n_ridge + self.n_rim
        cells = 2 ** (order + 1)                     # Moore order n covers a 2^(n+1) grid
        self.S_c = (cells - 1) * pitch               # curve square: step = span/(cells-1) = p
        self.inner = self.S_c + pitch                # half-cell margin each side
        self.ring_side = self.inner + BW             # rim wall centreline square
        self.od = self.ring_side + BW                # wall outer face
        self.skirt = self.ring_side + w1             # layer-1 ring lands w1 wide: the L1 skirt
        min_seg = machine.DEFAULT_SPEED / machine.MAX_MOVES_PER_SEC * 1.2
        f = fillet or max(0.8, pitch * 0.45)         # hilbert.py's own fillet derivation
        loop = curve(order, self.S_c, closed=True)
        off = (self.inner - self.S_c) / 2.0 - self.inner / 2.0
        loop = [(x + cx + off, y + cy + off) for x, y in loop]
        self.loop = machine.decimate(round_corners(loop, f), min_seg)
        self.ring = rounded_square(self.ring_side, cx, cy, RING_FILLET, min_seg)
        bi = min(range(len(self.loop) - 1),
                 key=lambda i: math.dist(self.loop[i], project_onto(self.ring, self.loop[i])[0]))
        self.B = self.loop[bi]
        self.loop_at_B = rot_closed(self.loop, bi)
        self.ring_at_A = ring_from(self.ring, self.B)
        self.A = self.ring_at_A[0]
        self.fillet = f

    def kind(self, k):
        if k == 1:
            return "floor L1"
        if k <= self.n_floor:
            return "floor"
        if k <= self.n_floor + self.n_ridge:
            return "ridge"
        return "rim"

    def strokes(self, k, entry):
        """[(pts, rate_mm_per_mm, tag)] for 1-based layer k, strokes contiguous, first stroke
        begins at the point the head should reach before extruding. Returns (strokes, exit)."""
        body_rate = BW * self.lh / machine.A_FIL
        kind = self.kind(k)
        if kind in ("floor L1", "floor"):
            l1 = kind == "floor L1"
            w = self.w1 if l1 else BW
            rate = machine.layer1_rate(self.w1, self.h1) if l1 else body_rate
            pitch = (FLOOR1_OVERLAP * self.w1) if l1 else (EDGE_LAP * BW)
            h = self.ring_side / 2.0 - self.edge_lap * w
            axis = "x" if k % 2 == 1 else "y"
            last_floor = k == self.n_floor
            best = None
            for sx in (1, -1):
                for sy in (1, -1):
                    pts, _ = raster_pts(h, pitch, axis, sx, sy, self.cx, self.cy)
                    cost = math.dist(entry, pts[0]) if entry else 0.0
                    if last_floor:
                        cost += 0.5 * math.dist(pts[-1], self.A)
                    if best is None or cost < best[0]:
                        best = (cost, pts)
            pts = best[1]
            ring = ring_from(self.ring, self.A if last_floor else pts[-1])
            return [(pts, rate, "raster"), (ring, rate, "ring")], ring[-1]
        if kind == "ridge":
            s = [(self.ring_at_A, body_rate, "ring")]
            for i in range(self.spoke_passes):
                out = i % 2 == 0
                s.append(([self.B if out else self.A], body_rate,
                          "SPOKE out" if out else "SPOKE back (2x radial rib, declared)"))
                if out and i == 0:
                    s.insert(2, (self.loop_at_B, body_rate, "moore"))
            return s, self.A
        return [(self.ring_at_A, body_rate, "ring")], self.A


# -------------------------------------------------------------------------------- gates ---

def gate_bounds(parts, printer):
    """Part + layer-1 skirt must sit inside the probed mesh, BED_MARGIN in from its edge.
    Outside the mesh Klipper EXTRAPOLATES the bed shape (machine.MESH's own note)."""
    if printer not in machine.MESH:
        raise SystemExit(f"GATE bounds: no probed-mesh window recorded for '{printer}' "
                         f"(machine.MESH has {sorted(machine.MESH)}) -- nothing can say where "
                         f"this plate's edge is. Read the machine's [bed_mesh] first.")
    mx0, my0, mx1, my1 = machine.MESH[printer]
    for pt in parts:
        h = pt.skirt / 2.0
        lo_x, hi_x = pt.cx - h, pt.cx + h
        lo_y, hi_y = pt.cy - h, pt.cy + h
        if (lo_x < mx0 + BED_MARGIN or lo_y < my0 + BED_MARGIN
                or hi_x > mx1 - BED_MARGIN or hi_y > my1 - BED_MARGIN):
            raise SystemExit(
                f"GATE bounds: {pt.label} spans X {lo_x:.1f}..{hi_x:.1f} Y {lo_y:.1f}..{hi_y:.1f} "
                f"(layer-1 skirt included) against {printer}'s probed mesh "
                f"({mx0:g},{my0:g})-({mx1:g},{my1:g}) minus the {BED_MARGIN:g}mm margin. "
                f"Shrink the pitch or the order; the mesh does not negotiate.")


def gate_fuse(pitch, label=""):
    """Adjacent ridges must stay OPEN: pitch - landed bead >= 0.3mm or the comb is a slab."""
    if pitch - BW < 0.3:
        raise SystemExit(
            f"GATE ridge-fuse{label}: pitch {pitch:g} minus the {BW:g}mm landed bead leaves "
            f"{pitch - BW:.2f}mm between ridge flanks -- under 0.3mm they weld into a slab and "
            f"the field stops being a comb. Smallest workable pitch is {BW + 0.3:.2f}mm.")


def gate_channel(mode, pitch, ball_d):
    """CHANNEL mode's groove is pitch - bead; a groove the ball cannot enter can never roll.
    Refuse the impossible rather than default to it (the wrap-deg 210 lesson)."""
    if mode == "channel" and pitch - BW < ball_d:
        raise SystemExit(
            f"GATE channel-impossible: --mode channel at pitch {pitch:g} leaves a "
            f"{pitch - BW:.2f}mm groove against a {ball_d:g}mm ball -- it can NEVER roll in it, "
            f"at any setting of the other knobs. A {ball_d:g}mm ball needs pitch >= "
            f"{ball_d + BW:.2f}mm. RIDGE mode has no such floor.")


def _body_segments(text):
    """(line_no, (x0,y0), (x1,y1), z, de, raw) for every emitted body move, plus part/layer
    labels -- measured off the emitted text, never off the plan that produced it."""
    segs = []
    x = y = None
    z = 0.0
    e = 0.0
    body = False
    part, layer = "", ""
    for i, ln in enumerate(open(text) if os.path.isfile(text) else text.splitlines(), 1):
        if "; BODY_START" in ln:
            body = True
        if ln.startswith("; ---- part"):
            part = ln.strip()
        if ln.startswith("; ---- layer"):
            layer = ln.strip()
        c = ln.split(";")[0].strip()
        if c.startswith("G92"):
            m = _re_E.search(c)
            if m:
                e = float(m.group(1))
            continue
        if c[:2] not in ("G0", "G1"):
            continue
        g = dict(_re_W.findall(c))
        nx = float(g["X"]) if "X" in g else x
        ny = float(g["Y"]) if "Y" in g else y
        if "Z" in g:
            z = float(g["Z"])
        de = 0.0
        if "E" in g:
            v = float(g["E"])
            de, e = v - e, v
        if body and None not in (x, y, nx, ny):
            segs.append((i, (x, y), (nx, ny), z, de, ln.rstrip("\n"), part, layer))
        x, y = nx, ny
    return segs


import re as _re
_re_E = _re.compile(r"\bE(-?\d+(?:\.\d+)?)")
_re_W = _re.compile(r"\b([XYZE])(-?\d+(?:\.\d+)?)")


def gate_one_stroke(text, allow_hops):
    """No dry XY move inside the body. The tray achieves ZERO travel (better than the bucket,
    which crosses air); the coupon may hop between patches only lifted and '; HOP'-tagged."""
    segs = _body_segments(text)
    ext = [s for s in segs if s[4] > 1e-6]
    if not ext:
        raise SystemExit("GATE one-stroke: no body extrusion found at all.")
    first, last = ext[0][0], ext[-1][0]
    lifted = 0.0
    for (i, a, b, z, de, raw, part, layer) in segs:
        if not (first < i < last) or de > 1e-6:
            if de > 1e-6:
                lifted = 0.0
            continue
        d = math.dist(a, b)
        if d < 1e-6:
            if "Z" in raw and "HOP" not in raw:
                lifted = 0.0
            else:
                m = _re.search(r"\bZ(-?\d+(?:\.\d+)?)", raw.split(";")[0])
                if m and "HOP" in raw:
                    lifted = max(lifted, float(m.group(1)) - z + float(m.group(1)) - float(m.group(1)))
            continue
        if not allow_hops:
            raise SystemExit(
                f"GATE one-stroke: line {i} is a dry XY move inside the body "
                f"({d:.1f}mm) -- this part is one continuous extrusion, zero travel, "
                f"and the file breaks its own invariant:\n  {raw}")
        if "; HOP" not in raw:
            raise SystemExit(
                f"GATE one-stroke: line {i} is an UNTAGGED dry XY move inside the body "
                f"({d:.1f}mm). Between patches a travel must be lifted, unmetered and "
                f"'; HOP'-tagged (machine.NO_TRAVEL_RULE):\n  {raw}")


def gate_weld(text, parts_meta, floor_pitch_body):
    """The qa_weld law, applied in-generator to the emitted moves (qa_weld itself re-derives
    bucket geometry from CMD and cannot parse this part -- spec section 3).

    ATTACH   on every judged floor layer (2..n_floor; layer 1 is the plate weld, reported)
             walk the ring in 0.5mm steps: a step is HELD when a raster capsule overlaps the
             ring bead by >= WELD_MARGIN. Longest unheld run <= the layer's own raster pitch.
    NO-PILE  no 0.4mm cell may carry more than 2.7 bead-heights of depth. The spoke feet
             (JUNCTION_R around A and B) are the declared corridor: reported, never judged --
             ring + doubled spoke legitimately meet there, one strip per layer by design.
    """
    segs = _body_segments(text)
    by = {}
    for (i, a, b, z, de, raw, part, layer) in segs:
        if de <= 1e-6 or math.dist(a, b) < 1e-6 or "PRIME" in raw.upper():
            continue
        by.setdefault((part, round(z, 3)), []).append((a, b, de, raw))
    reports = []
    for meta in parts_meta:
        pt = meta["part"]
        zs = sorted({zz for (lbl, zz) in by if lbl == meta["marker"]})
        if len(zs) != pt.layers:
            raise SystemExit(f"GATE weld: {pt.label} emitted {len(zs)} layers, planned "
                             f"{pt.layers} -- the emitted file is not the plan.")
        for li, zz in enumerate(zs, 1):
            moves = by[(meta["marker"], zz)]
            gap = pt.h1 if li == 1 else pt.lh
            caps = []
            for (a, b, de, raw) in moves:
                d = math.dist(a, b)
                w = de * machine.A_FIL / d / gap
                caps.append((a, b, w, raw))
            kind = pt.kind(li)
            if kind in ("floor L1", "floor"):
                ring_caps = [c for c in caps if "ring" in c[3]]
                fill_caps = [c for c in caps if "ring" not in c[3]]
                if not ring_caps or not fill_caps:
                    # a check that cannot measure its name DECLINES loudly, never crashes
                    # and never approves (lesson-check-must-measure-its-name): this fired
                    # for real when the emitter dropped its stroke tags
                    raise SystemExit(
                        f"GATE weld: {pt.label} layer {li} (z {zz:g}) carries "
                        f"{len(ring_caps)} ring-tagged and {len(fill_caps)} fill beads -- "
                        f"the emitted file lacks the stroke tags this gate classifies by, "
                        f"so attachment CANNOT BE MEASURED. The emitter must tag every "
                        f"move; refusing rather than approving blind.")
                bead = sorted(c[2] for c in ring_caps)[len(ring_caps) // 2]
                worst_run, run = 0.0, 0.0
                border = _sample_ring(pt.ring, ATTACH_STEP)
                for bp in border:
                    held = any(_seg_dist(bp, bp, c[0], c[1]) <= (bead + c[2]) / 2.0 - WELD_MARGIN
                               for c in fill_caps)
                    run = 0.0 if held else run + ATTACH_STEP
                    worst_run = max(worst_run, run)
                lim = (FLOOR1_OVERLAP * pt.w1) if li == 1 else floor_pitch_body
                if li == 1:
                    reports.append(f"  {pt.label} layer 1: longest unlapped ring run "
                                   f"{worst_run:.1f}mm (REPORTED, not judged: plate weld, "
                                   f"its evidence is the coupon)")
                elif worst_run > lim:
                    raise SystemExit(
                        f"GATE weld ATTACH: {pt.label} layer {li} (z {zz:g}) leaves "
                        f"{worst_run:.1f}mm of rim ring with no raster welded to it "
                        f"(limit {lim:g}mm = the raster's own pitch; margin {WELD_MARGIN}mm). "
                        f"The border must not be weaker than the lattice welds to itself.")
            # the ring CLOSURE is the third declared corridor point: a closed loop's seam
            # doubles material at exactly one spot (arrive onto the departure), and this
            # path deliberately parks that seam at the raster junction to keep the link
            # short -- one seam per layer by design, same idiom as the bucket's corridor
            ring_caps_all = [c for c in caps if "ring" in c[3]]
            seam_pts = (ring_caps_all[0][0],) if ring_caps_all else ()
            piles, seam = _pile_depths(caps, (pt.A, pt.B) + seam_pts)
            if li == 1:
                if piles:
                    reports.append(f"  {pt.label} layer 1: {len(piles)} spot(s) over "
                                   f"{PILE_DEPTH} bead-heights (REPORTED: pressed sheet)")
                continue
            if piles:
                worst = max(piles)
                raise SystemExit(
                    f"GATE weld NO-PILE: {pt.label} layer {li} (z {zz:g}, {kind}) has "
                    f"{len(piles)} spot(s) carrying more than {PILE_DEPTH} bead-heights of "
                    f"material (worst {worst:.1f}) OUTSIDE the declared spoke-junction "
                    f"corridor. Separate passes are piling onto one line.")
            if seam:
                reports.append(f"  {pt.label} layer {li}: {len(seam)} junction-corridor "
                               f"spot(s), worst {max(seam):.1f} bead-heights (declared: "
                               f"ring + {pt.spoke_passes}x spoke meet there by design)")
    return reports


def _sample_ring(ring, step):
    out = []
    for i in range(len(ring) - 1):
        a, b = ring[i], ring[i + 1]
        d = math.dist(a, b)
        n = max(1, int(d / step))
        for t in range(n):
            out.append((a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n))
    return out


def _seg_dist(p, q, a, b):
    def pt(s, u, v):
        dx, dy = v[0] - u[0], v[1] - u[1]
        l2 = dx * dx + dy * dy
        if l2 < 1e-18:
            return math.dist(s, u)
        t = max(0.0, min(1.0, ((s[0] - u[0]) * dx + (s[1] - u[1]) * dy) / l2))
        return math.hypot(s[0] - u[0] - dx * t, s[1] - u[1] - dy * t)
    if p == q:
        return pt(p, a, b)
    def cross(o, u, v):
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])
    d1, d2 = cross(a, b, p), cross(a, b, q)
    d3, d4 = cross(p, q, a), cross(p, q, b)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(pt(p, a, b), pt(q, a, b), pt(a, p, q), pt(b, p, q))


def _pile_depths(caps, junctions):
    """Depth per PILE_CELL cell in bead-heights (qa_weld's elliptical-section sum; a bead
    continuing through a cell keeps its deepest sample, never sums with itself).

    CONTINUATION means heading ONWARD: index-adjacent + shared endpoint + not doubling
    back (dot >= -0.1 admits raster turnarounds, refuses a reversal). The first version
    merged on index-adjacency alone, and a spoke drawn 4x as consecutive moves read ~2.0
    deep -- the gate would have PASSED a genuinely 4-deep stack on a real plate (found
    2026-08-09 when its own force-fire refused to fire)."""
    cells = {}

    def _dir(a, b):
        d = math.dist(a, b)
        return ((b[0] - a[0]) / d, (b[1] - a[1]) / d) if d > 1e-9 else (0.0, 0.0)

    for idx, (a, b, w, raw) in enumerate(caps):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        r = w / 2.0
        v = _dir(a, b)
        for gx in range(int((x0 - r) / PILE_CELL), int((x1 + r) / PILE_CELL) + 2):
            for gy in range(int((y0 - r) / PILE_CELL), int((y1 + r) / PILE_CELL) + 2):
                ctr = ((gx + .5) * PILE_CELL, (gy + .5) * PILE_CELL)
                d = _seg_dist(ctr, ctr, a, b)
                if d > r:
                    continue
                dep = math.sqrt(max(0.0, 1.0 - (2.0 * d / w) ** 2))
                lst = cells.setdefault((gx, gy), [])
                # ONE BEAD = GEOMETRIC CONTINUITY, judged against this cell's last
                # contributor: it ends exactly where this cap starts AND the head keeps
                # going (dot >= -0.1 admits vertex turns, refuses a reversal). A closed
                # loop's seam is the same one pass (its last cap arrives where its first
                # departed -- index distance says nothing); a spoke redrawn A->B->A
                # reverses and SUMS. The index-window rule this replaces failed both
                # ways at once (measured 2026-08-09: 4 stacked spoke passes read ~2.0,
                # a clean ring seam read ~2.9).
                if lst and math.dist(lst[-1][2], a) < 1e-6 \
                        and lst[-1][3][0] * v[0] + lst[-1][3][1] * v[1] >= -0.1:
                    lst[-1][0] = idx
                    lst[-1][1] = max(lst[-1][1], dep)
                    lst[-1][2] = b
                    lst[-1][3] = v
                else:
                    lst.append([idx, dep, b, v])
    piles, seam = [], []
    for k, v in cells.items():
        tot = sum(entry[1] for entry in v)
        if tot > PILE_DEPTH:
            ctr = ((k[0] + .5) * PILE_CELL, (k[1] + .5) * PILE_CELL)
            if any(math.dist(ctr, j) <= JUNCTION_R for j in junctions):
                seam.append(tot)
            else:
                piles.append(tot)
    return piles, seam


# ----------------------------------------------------------------------------- emission ---

def emit(a, parts, printer, material, temp, bed, allow_hops, inject_travel=False):
    """The full gcode text. Header first (stamps validate.py reads live in the first 4000
    chars), then the machine block, machine.prime(), '; BODY_START', the interleaved layers."""
    lh = a.layer_h
    speed = machine.speed_for_flow(machine.flow_cap(material, printer) or machine.FLOW, BW, lh)
    flow = speed * BW * lh
    f_body = round(speed * 60)
    f_l1 = round(a.speed1 * 60)
    zerr = machine.ZERR[printer]
    zoff = machine.zoff_for(a.h1, zerr)
    l1_rate = machine.layer1_rate(a.w1, a.h1)
    K = max(pt.layers for pt in parts)

    L = []
    w = L.append
    kindname = "COUPON C1" if a.coupon else "TRAY"
    w(f"; ORBE TIDE {kindname} -- Hilbert ASMR tray, {len(parts)} part(s), spec "
      f"guides/orbe-tray-spec.md")
    w(f"; PRINTER={printer}")
    w(f"; MATERIAL={material}")
    w("; CMD=" + " ".join(["tide_tray.py"] + _sys.argv[1:]))
    w(f"; LAYER_H={lh:.3f}")
    w(f"; SPEED={speed:.4f}")
    w(f"; SPEED_LAYER1={a.speed1:.4f}")
    w(f"; FLOW={flow:.4f}")
    w(f"; PRESSED_LAYER1={machine.PRESS_HARD:g}")
    w(f"; LAYER1_WIDTH={a.w1:.2f}mm landed into the {a.h1:g} gap = {a.w1 * a.h1:.4f}mm2/mm "
      f"({a.w1 * a.h1 / (BW * lh):.2f}x the body's own {BW * lh:.4f}mm2 bead)")
    if a.cite_coupon:
        w(f"; COUPON={a.cite_coupon} h1={a.h1:g} w1={a.w1:.2f} verdict=welded "
          f"read={a.coupon_read}")
    w(f"; PRINT_TEMP={temp}")
    w(f"; bead {BW:g}x{lh:g}   nozzle {machine.NOZZLE:g}   (Oleg 2026-08-04; Klipper's "
      f"nozzle_diameter field reads 0.4 on this machine and lies)")
    der = machine.flow_derate_stamp(material, printer, flow)
    if der:
        w(der)
    w(";")
    w("; ---------------- WHAT THIS IS ----------------")
    for pt in parts:
        s, verdict = ride_verdict(a.ball_d, pt.p, pt.n_ridge * lh)
        rho = pt.p / a.ball_d
        n100 = int(pt.inner ** 2 // a.ball_d ** 2)
        w(f"; {pt.label}: Moore order {pt.order} at pitch {pt.p:g} (rho {rho:.2f} vs the "
          f"{a.ball_d:g}mm ball), curve square {pt.S_c:.1f}, tray OD {pt.od:.1f}mm "
          f"(L1 skirt {pt.skirt:.1f}), ridge {pt.n_ridge}x{lh:g}={pt.n_ridge * lh:.2f}mm")
        w(f";   ridge verdict, DERIVED and UNHEARD (A3): {verdict}")
        w(f";   rim {(pt.n_ridge + pt.n_rim) * lh:.2f}mm above floor top "
          f"({pt.n_ridge + pt.n_rim} layers); floor {pt.h1:g} + {pt.n_floor - 1}x{lh:g} = "
          f"{pt.h1 + (pt.n_floor - 1) * lh:.2f}mm solid plate")
        w(f";   fill guidance: 40-60% = {int(0.4 * n100)}-{int(0.6 * n100)} of ~{n100} "
          f"{a.ball_d:g}mm balls that fit one layer deep (A6: proven once, pocket scale)")
    w(f"; floor rasters: layer 1 pitch {FLOOR1_OVERLAP:g} x w1 = {FLOOR1_OVERLAP * a.w1:.3f}mm "
      f"(the ratio law -- a mm constant goes stale when --w1 moves); body floors "
      f"{EDGE_LAP:g} x bead = {EDGE_LAP * BW:.3f}mm; every interface laps 0.2 bead "
      f"(qa_weld law -- a commanded butt is a landed gap)")
    w(f"; one-stroke: {'lifted tagged hops between patches only' if allow_hops else 'ZERO travel -- the whole part is one extrusion'}")
    w(f"; spoke: drawn {parts[0].spoke_passes}x per ridge layer = a declared 2x radial rib "
      f"~p/2 long welding field to rim; the junction corridor is the declared pile "
      f"(reported by the weld gate, never judged)")
    w(f"; offset: SET_GCODE_OFFSET Z={zoff:.3f} -- commanded Z{machine.PRESS_HARD:g} lands "
      f"layer 1 at {a.h1:g}mm on a machine whose zero sits {zerr:g}mm high (machine.ZERR)")
    w(";")
    w("; STAGE (spec s6): SPEC-DERIVED GEOMETRY, NEVER PRINTED. Every acoustic claim A2-A6 is")
    w("; UNPROVEN; the 07-23 original's parameters are unrecorded (C0 not yet calipered). This")
    w("; file is an intention until Oleg's ear converts a coupon (send --oleg-said, ledger on")
    w("; acceptance). The sink arithmetic is a line-contact MODEL; the coupon is the decider.")
    w("; HEADER_BLOCK_START")
    w(f"; total layer number: {K}")
    w("; HEADER_BLOCK_END")

    # ---- machine block: the accepted f3x4r1c bucket's own opening, the sequence that passed
    w("M82")
    w(f"M140 S{bed}")
    w(f"M104 S{temp}")
    w(f"M190 S{bed}   ; BLOCKING: do not start below this")
    w(f"M140 S{bed}")
    w(f"M109 S{temp}")
    machine.home(w, printer)
    w(f"SET_GCODE_OFFSET Z={zoff:.3f}                 ; lands the {a.h1:g} first layer")
    fan_l1 = int(round(machine.fan_first_layer(material) * 255))
    w(f"M106 S{fan_l1}" + ("" if fan_l1 else "                              ; layer 1 gets no fan -- the weld to the plate is the job"))
    for ln in machine.aux_fans(printer, machine.aux_for(material, a.aux)):
        w(ln)
    w("M204 S8000")
    w("G92 E0")

    # ---- prime: pinned from the first millimetre (validate R10); avoid every part's skirt
    avoid = tuple(("rect", pt.cx - pt.skirt / 2, pt.cy - pt.skirt / 2,
                   pt.cx + pt.skirt / 2, pt.cy + pt.skirt / 2) for pt in parts)
    first_strokes, _ = parts[0].strokes(1, None)
    first_pt = first_strokes[0][0][0]
    x, y, e = machine.prime(w, printer=printer, z=machine.PRESS_HARD, rate=l1_rate,
                            feed=f_l1, travel_feed=7200, avoid=avoid, near=first_pt)
    w("; BODY_START")

    cur_f = None
    z = machine.PRESS_HARD
    heads = {id(pt): None for pt in parts}          # each part's exit point, once started
    total_mm = 0.0

    def move(px, py, rate, feed, tag=""):
        nonlocal x, y, e, cur_f, total_mm
        d = math.dist((x, y), (px, py))
        if d < 1e-9:
            return
        # SEGMENTS <= 1.5mm, uniformly: validate's overhang support is a POINT hash at
        # one-bead cells, and a 40mm raster row emitted as one move leaves its interior
        # invisible -- the first coupon read 485.5mm of the Moore loop "floating" over a
        # SOLID floor whose rows had no interior vertices. 1.5mm keeps every query point
        # within 0.8mm of a support vertex (inside the 0.82 cell reach); ~20 moves/s at
        # body speed against the ~300 where Klipper stalls.
        n = max(1, int(math.ceil(d / 1.5)))
        for j in range(1, n + 1):
            qx = x + (px - x) * j / n
            qy = y + (py - y) * j / n
            e += (d / n) * rate
            fword = f"F{feed} " if feed != cur_f else ""
            cur_f = feed
            w(f"G1 {fword}X{qx:.3f} Y{qy:.3f} E{e:.5f}" + (f" ; {tag}" if tag else ""))
        total_mm += d
        x, y = px, py

    order_fwd = list(parts)
    for k in range(1, K + 1):
        z = machine.PRESS_HARD + (k - 1) * lh
        active = [pt for pt in (order_fwd if k % 2 == 1 else order_fwd[::-1])
                  if k <= pt.layers]
        w(f"; ---- layer {k} of {K}  z {z:.3f}  ({active and active[0].kind(k) or 'rim'})")
        if k > 1:
            w(f"G1 F600 Z{z:.3f}")
            cur_f = 600
        feed = f_l1 if k == 1 else f_body
        for pt in active:
            marker = f"; ---- part {pt.label}"
            strokes, exit_pt = pt.strokes(k, heads[id(pt)] or (x, y))
            start = strokes[0][0][0]
            d0 = math.dist((x, y), start)
            if d0 > 1e-6:
                if k == 1 and heads[id(pt)] is None and pt is active[0] and all(
                        heads[id(q)] is None for q in parts):
                    w(marker)
                    w(f"G0 F3000 X{start[0]:.3f} Y{start[1]:.3f} ; HOP prime -> first line, "
                      f"over bare plate")
                    cur_f = None
                    x, y = start
                elif d0 > 3.0:
                    w(marker)
                    w(f"G0 F7200 Z{z + HOP_LIFT:.3f} ; HOP over finished patches, lifted")
                    w(f"G0 F7200 X{start[0]:.3f} Y{start[1]:.3f} ; HOP over finished patches, "
                      f"lifted")
                    w(f"G1 F600 Z{z:.3f} ; HOP down onto the patch")
                    cur_f = 600
                    x, y = start
                else:
                    w(marker)
            else:
                w(marker)
            if inject_travel and k == 2 and pt is active[0]:
                w(f"G0 F7200 X{x + 8:.3f} Y{y:.3f}")     # selftest only: an untagged dry move
                x = x + 8
            # EVERY move carries its stroke tag. gate_weld classifies ring vs fill by
            # reading these tags off the emitted lines -- the first version wrote only
            # SPOKE tags, so ring_caps came back empty on every file ever emitted and the
            # gate crashed at its median instead of measuring (found 2026-08-09: the
            # delivered generator had never once emitted through its own gates).
            for pts, rate, tag in strokes:
                for p in pts:
                    move(p[0], p[1], rate, feed, tag)
            heads[id(pt)] = (x, y)

    top = machine.PRESS_HARD + (K - 1) * lh
    w("M107")
    w("M104 S0")
    w("M140 S0")
    zp, capped = machine.z_retreat(printer, top, 20.0)
    w(f"G0 F3000 Z{zp:.2f}" + ("   ; retreat capped at the machine's Z ceiling" if capped else ""))
    w("G0 F7200 X10 Y10")
    w("SET_GCODE_OFFSET Z=0.000                 ; hand the machine back with its own zero")
    return "\n".join(L) + "\n", e


def derived_budget(text, material):
    """Minutes and grams MEASURED off the emitted file -- never the plan's arithmetic."""
    x = y = None
    z = 0.0
    e = 0.0
    f = 3000.0
    secs = 0.0
    vol = 0.0
    for ln in text.splitlines():
        c = ln.split(";")[0].strip()
        if c.startswith("G92"):
            m = _re_E.search(c)
            if m:
                e = float(m.group(1))
            continue
        if c[:2] not in ("G0", "G1"):
            continue
        g = dict(_re_W.findall(c))
        m = _re.search(r"\bF(\d+(?:\.\d+)?)", c)
        if m:
            f = float(m.group(1))
        nx = float(g["X"]) if "X" in g else x
        ny = float(g["Y"]) if "Y" in g else y
        nz = float(g["Z"]) if "Z" in g else z
        if None not in (x, y, nx, ny):
            d = math.dist((x, y, z), (nx, ny, nz))
            secs += d / (f / 60.0)
        if "E" in g:
            v = float(g["E"])
            if v > e:
                vol += (v - e) * machine.A_FIL
            e = v
        x, y, z = nx, ny, nz
    return secs / 60.0, vol * 1.24 / 1000.0


# ---------------------------------------------------------------------------- selftest ---

def selftest(a):
    """Force every gate red once. A gate that has never fired counts for nothing."""
    import copy
    fired = 0

    def expect(name, fn, needle):
        """The refusal must come from the NAMED gate: the first forcing of the weld gates
        was 'proven' by one-stroke firing first on incidental hops the doctoring created
        (checked 2026-08-09 -- the forcing-lands-in-the-wrong-jurisdiction trap)."""
        nonlocal fired
        try:
            fn()
        except SystemExit as ex:
            msg = str(ex)
            if needle in msg:
                print(f"  RED OK  {name}: {msg.splitlines()[0][:110]}")
                fired += 1
            else:
                print(f"  !! {name}: a DIFFERENT gate fired ({msg.splitlines()[0][:80]}) "
                      f"-- the forcing missed its jurisdiction")
            return
        print(f"  !! {name}: DID NOT FIRE -- the gate is decoration")

    small = copy.copy(a)
    small.coupon = False
    small.order, small.pitch, small.ridge_layers = 1, 6.9, 2

    def build(aa, spoke_passes=2, edge_lap=EDGE_LAP, inject=False, hops=False):
        # hops=True: a weld forcing may legitimately shift layer entries >3mm, emitting
        # lifted tagged hops -- the point is to reach the WELD gate's jurisdiction, so
        # one-stroke is told to allow what the doctoring caused (never what it must catch)
        pt = Part(175, 175, aa.pitch, aa.order, aa.ridge_layers, 3, aa.floor_layers,
                  aa.w1, aa.h1, aa.layer_h, label=f"selftest p{aa.pitch:g}",
                  spoke_passes=spoke_passes, edge_lap=edge_lap)
        gate_bounds([pt], "k2plus")
        text, _ = emit(aa, [pt], "k2plus", "pla", 210, 80, False, inject_travel=inject)
        gate_one_stroke(text, allow_hops=hops)
        gate_weld(text, [{"part": pt, "marker": f"; ---- part {pt.label}"}],
                  EDGE_LAP * BW)

    big = copy.copy(small)
    big.order = 5
    expect("bounds", lambda: gate_bounds(
        [Part(175, 175, big.pitch, big.order, 2, 3, big.floor_layers, big.w1, big.h1,
              big.layer_h, label="order-5 tray")], "k2plus"), "GATE bounds")
    expect("ridge-fuse", lambda: gate_fuse(1.0), "GATE ridge-fuse")
    expect("channel-impossible", lambda: gate_channel("channel", 6.9, 8.0),
           "GATE channel-impossible")
    expect("one-stroke", lambda: build(small, inject=True), "GATE one-stroke")
    # weld forcings sized to stay INSIDE the weld gates' jurisdiction: edge_lap 1.6 pulls
    # the raster 1.31mm off the ring (past the ~0.77 weld reach) without moving any layer
    # entry >3mm (which would hop and fire one-stroke first); spoke_passes must stay EVEN
    # or the layer ends at B while declaring exit A and the next entry hops
    expect("weld ATTACH", lambda: build(small, edge_lap=1.6, hops=True),
           "GATE weld ATTACH")
    expect("weld NO-PILE", lambda: build(small, spoke_passes=4, hops=True),
           "GATE weld NO-PILE")
    print(f"  {fired}/6 gates proven able to fire")
    # and the happy path must PASS, or the gates above are firing on everything:
    build(small)
    print("  clean selftest build passes all gates")
    return 0 if fired == 6 else 1


# -------------------------------------------------------------------------------- main ---

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--coupon", action="store_true",
                    help="emit the C1 coupon plate: six order-2 Moore patches, 3 pitches x "
                         "2 ridge heights, same floor, same rim stub, SAME CODE PATH as the "
                         "tray (spec s2: 'test the REAL geometry')")
    ap.add_argument("--pitch", type=float, default=6.9,
                    help="ridge pitch mm -- THE acoustic knob; size is derived from it, "
                         "never the reverse (spec s3)")
    ap.add_argument("--order", type=int, default=3,
                    help="Moore order; order n covers a 2^(n+1) grid, so n->n+1 doubles the "
                         "grid and ~doubles the tray")
    ap.add_argument("--coupon-pitches", default="5.6,6.9,8.8",
                    help="the C1 bracket: rho 0.70 / 0.86 / 1.10 against an 8mm ball")
    ap.add_argument("--coupon-ridge-layers", default="6,10",
                    help="the two ridge heights per plate run: 6x0.24=1.44, 10x0.24=2.40")
    ap.add_argument("--ball-d", type=float, default=8.0,
                    help="ball diameter mm; the inventory is ~800 8mm steel")
    ap.add_argument("--mode", choices=("ridge", "channel"), default="ridge",
                    help="RIDGE ships v1 (Oleg's actual discovery); CHANNEL is a documented "
                         "flag behind its own impossibility gate")
    ap.add_argument("--ridge-layers", type=int, default=6,
                    help="ridge height in layers: 6 = 1.44mm, 10 = 2.40mm")
    ap.add_argument("--rim-h", type=float, default=0.0,
                    help="rim above floor top; 0 = derive 0.66 x ball (captures past the "
                         "equator, top hemisphere exposed)")
    ap.add_argument("--floor-layers", type=int, default=6,
                    help="solid floor layers ABOVE layer 1 (the soundboard)")
    ap.add_argument("--layer-h", type=float, default=machine.SLICER_LAYER_H)
    ap.add_argument("--h1", type=float, default=0.25,
                    help="landed first-layer height; (0.25, 3.94) and (0.10, 2.00) are the "
                         "K2's proven pairs (machine.PROVEN_LAYER1)")
    ap.add_argument("--w1", type=float, default=3.94,
                    help="landed first-layer width -- height and width are ONE weld")
    ap.add_argument("--speed1", type=float, default=25.0,
                    help="layer-1 speed, declared as its own regime (the accepted bucket's)")
    ap.add_argument("--fan", type=float, default=0.2, help="part fan 0-1 from layer 2")
    ap.add_argument("--aux", type=float, default=0.2, help="chamber/side fans 0-1")
    ap.add_argument("--fillet", type=float, default=0.0,
                    help="Moore corner fillet; 0 = hilbert.py's own max(0.8, 0.45 x pitch)")
    ap.add_argument("--printer", default=machine.DEFAULT_PRINTER, choices=sorted(machine.BED))
    ap.add_argument("--material", default="",
                    help="empty = the filament LOADED in --printer (machine.LOADED)")
    ap.add_argument("--cite-coupon", metavar="FILE",
                    help="the zladder plate that proved this file's first layer; emits the "
                         "'; COUPON=' stamp validate.py R9 verifies four ways")
    ap.add_argument("--coupon-read", metavar="YYYY-MM-DD",
                    help="the date the cited plate was READ (never defaulted to today)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--selftest", action="store_true",
                    help="force every gate red once and exit")
    a = ap.parse_args()

    if a.selftest:
        raise SystemExit(selftest(a))

    printer = a.printer
    material = a.material or machine.LOADED.get(printer, machine.DEFAULT_MATERIAL)
    machine.check_spool(printer, material)
    temp = machine.temp_for(material)
    bed = machine.bed_for(material, printer)

    # ---- generation-time gates, before any geometry is built
    if a.layer_h not in machine.SLICER_LAYER_HEIGHTS:
        raise SystemExit(f"REFUSING: layer height {a.layer_h:g} is UNOFFERED -- no profile on "
                         f"this machine produces it (machine.SLICER_LAYER_HEIGHTS "
                         f"{machine.SLICER_LAYER_HEIGHTS}). Nothing measured here holds at it.")
    if printer not in machine.ZERR or printer not in machine.PROVEN_LAYER1:
        raise SystemExit(f"REFUSING: '{printer}' has no measured Z-zero error or no proven "
                         f"first-layer pair. Any machine but the K2 starts at zero with a "
                         f"zladder (spec s4).")
    proven = machine.PROVEN_LAYER1[printer]
    hit = [p for p in proven if abs(a.h1 - p[0]) <= 0.005 and abs(a.w1 - p[1]) <= 0.05]
    if not hit and not a.cite_coupon:
        raise SystemExit(f"REFUSING: first layer {a.h1:g} x {a.w1:g} is not a proven pair on "
                         f"{printer} ({', '.join(f'{h:g}x{w:g}' for h, w in proven)}) and no "
                         f"--cite-coupon names the zladder plate that tested it. Height and "
                         f"width are one weld; print the ladder, read the plate, cite the cell.")
    if a.cite_coupon:
        if not a.coupon_read:
            raise SystemExit("REFUSING: --cite-coupon needs --coupon-read YYYY-MM-DD, the date "
                             "the plate was READ. A citation with an invented date is a "
                             "citation nobody can check.")
        if not os.path.isfile(a.cite_coupon):
            raise SystemExit(f"REFUSING: --cite-coupon {a.cite_coupon} does not exist. A "
                             f"citation whose coupon is missing is worse than no citation.")

    lh = a.layer_h
    rim_h = a.rim_h or round(0.66 * a.ball_d, 2)
    bx, by = machine.BED[printer]

    if a.coupon:
        pitches = [float(v) for v in a.coupon_pitches.split(",")]
        heights = [int(v) for v in a.coupon_ridge_layers.split(",")]
        for p in pitches:
            gate_fuse(p, f" (coupon pitch {p:g})")
        gate_channel(a.mode, min(pitches), a.ball_d)
        order = 2
        stub = 4                                     # rim-only layers above the ridge field
        widths = []
        for p in pitches:
            probe = Part(0, 0, p, order, heights[0], stub, a.floor_layers, a.w1, a.h1, lh)
            widths.append(probe.skirt)
        total_w = sum(widths) + COUPON_GAP * (len(widths) - 1)
        row_h = max(widths)
        total_h = row_h * len(heights) + COUPON_GAP * (len(heights) - 1)
        parts = []
        x0 = bx / 2.0 - total_w / 2.0
        for ri, rl in enumerate(heights):
            cy = by / 2.0 - total_h / 2.0 + row_h / 2.0 + ri * (row_h + COUPON_GAP)
            cx = x0
            for p, wd in zip(pitches, widths):
                parts.append(Part(cx + wd / 2.0, cy, p, order, rl, stub, a.floor_layers,
                                  a.w1, a.h1, lh, a.fillet,
                                  label=f"patch p{p:g} h{rl * lh:.2f}"))
                cx += wd + COUPON_GAP
        allow_hops = True
        fn = (f"{a.out}/tide_coupon_{printer}_{material}_o{order}_"
              f"p{'-'.join(f'{p:g}' for p in pitches)}_"
              f"h{'+'.join(f'{r * lh:.2f}' for r in heights)}.gcode")
    else:
        gate_fuse(a.pitch)
        gate_channel(a.mode, a.pitch, a.ball_d)
        rim_layers = max(1, round(rim_h / lh))
        rim_only = rim_layers - a.ridge_layers
        if rim_only < 0:
            raise SystemExit(f"REFUSING: ridge {a.ridge_layers} layers "
                             f"({a.ridge_layers * lh:.2f}mm) stands taller than the "
                             f"{rim_h:g}mm rim -- the balls would rake out over the wall.")
        parts = [Part(bx / 2.0, by / 2.0, a.pitch, a.order, a.ridge_layers, rim_only,
                      a.floor_layers, a.w1, a.h1, lh, a.fillet,
                      label=f"tray p{a.pitch:g} o{a.order}")]
        allow_hops = False
        fn = (f"{a.out}/tide_tray_{printer}_{material}_o{a.order}_p{a.pitch:g}_"
              f"h{a.ridge_layers * lh:.2f}_rim{rim_layers * lh:.2f}.gcode")

    gate_bounds(parts, printer)
    text, e_total = emit(a, parts, printer, material, temp, bed, allow_hops)

    # ---- artifact gates: measured off the emitted text, never the plan
    gate_one_stroke(text, allow_hops)
    reports = gate_weld(text, [{"part": pt, "marker": f"; ---- part {pt.label}"}
                               for pt in parts], EDGE_LAP * BW)

    mins, grams = derived_budget(text, material)
    machine.flow_for_duration(machine.speed_for_flow(machine.flow_cap(material, printer)
                                                     or machine.FLOW, BW, lh) * BW * lh,
                              mins, " for this part", material)
    os.makedirs(a.out, exist_ok=True)
    with open(fn, "w") as fh:
        fh.write(text)
    print(fn)
    for r in reports:
        print(r)
    for pt in parts:
        print(f"  {pt.label}: OD {pt.od:.1f}mm, {pt.layers} layers, "
              f"loop {sum(math.dist(pt.loop[i], pt.loop[i + 1]) for i in range(len(pt.loop) - 1)) / 1000:.2f}m/ridge layer")
    print(f"  ~{mins:.0f} min motion (+ the K2's ~10 min calibration block), ~{grams:.0f} g, "
          f"{max(pt.layers for pt in parts)} layers -- DERIVED off the emitted moves")
    print(f"  UNPROVEN: every acoustic claim; this geometry has never printed. "
          f"validate.py + a coupon + Oleg's ear are the path to a plate.")


if __name__ == "__main__":
    main()
