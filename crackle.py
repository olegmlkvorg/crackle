#!/usr/bin/env python3
"""Crackle coupon generator — emits gcode directly. Phase 1: is the effect controllable?

THE THESIS (refined from the PRD, and the reason this emits gcode rather than CAD):
The crackle is fused strand CROSSINGS breaking under load. Strands come from travel moves with
retraction off. So the control variable is crossings-per-volume — and crossings are a *computable
function of the order you visit the pillars in*, not an accident.

  · visit pillars around the perimeter  -> chords never cross      -> ~0 crossings/layer
  · visit pillars in "star" order       -> nearly every chord crosses -> max crossings/layer

That is why this tool COUNTS crossings before printing (segment-intersection test) and prints the
number in the filename and header. You dial a number; you don't sweep and hope. If crossing count
turns out NOT to predict the feel, that falsifies the thesis cheaply — which is a valid Phase 1
result and the fastest way to learn it.

Deviations from the PRD's starting guess, and why:
 1. **Travel ORDER is axis #1, not last.** Per the argument above it is the only axis that changes
    crossings-per-layer by an order of magnitude. Temperature/fan change whether crossings *weld*;
    order changes how many there ARE.
 2. **A solid anchor base under the pillars.** The PRD lists bed adhesion and "must release intact
    and be stood on" as rig problems. One feature solves both: 2 solid layers that tie every pillar
    together, survive the nozzle dragging across them, and give a coupon you can peel off and stand
    on without it disintegrating. Cost: ~1 g and ~40 s.
 3. **Per-layer rotation of the visit order.** Without it, every layer crosses at the same XY points
    and you build vertical welded columns (which press, like the hex grid, instead of crackling).
    Rotating the order spreads crossings through the volume — that is the "per-volume" in the thesis.
 4. **Web density is decoupled from pillar count** via `--passes`: extra crossing passes per layer
    cost travel time only, ~no filament. This is the cheap knob the PRD predicted.

Usage:
  python3 crackle.py --preset A            # emit one coupon
  python3 crackle.py --sweep order         # emit a one-factor-at-a-time sweep
  python3 crackle.py --list                # show presets
"""
from __future__ import annotations
import argparse, random
import machine, itertools, math, os, random, sys
from dataclasses import dataclass, asdict, replace

# ---------------------------------------------------------------- parameters
@dataclass
class Params:
    name: str = "A"
    origin: float = 40.0        # BUG FIX: coupon was at 0,0 so edge pillars ran off the bed
    size: float = 60.0          # coupon footprint (mm, square)
    n: int = 4                  # pillars per side (n*n total)
    pitch: float = 20.0         # pillar spacing (mm) — set from size/n if 0
    layer_h: float = 0.40       # 0.8 nozzle: ~50% of orifice
    layers: int = 15            # ~6 mm tall at 0.4 layers
    line_w: float = 0.90        # 0.8 NOZZLE — you cannot extrude narrower than the orifice.
                                # v1 used 0.6 here, which a 0.8 nozzle physically cannot lay down;
                                # that plus oozed strands is why coupon A's web never built.
    pillar_turns: float = 1.0   # how much material to lay down AT each pillar per layer
    order: str = "star"         # perimeter | serpentine | star | random | maxcross
    passes: int = 1             # extra crossing passes per layer (travel-only cost)
    rotate_per_layer: bool = True
    temp: int = 230
    bed: int = 60
    fan: int = 0                # 0 = crossings weld. This is the "does it fuse" axis.
    travel_f: int = 6000        # mm/min. Slower = thicker, more-welded strands.
    print_f: int = 1200
    base_layers: int = 2        # solid anchor slab (adhesion + handleable coupon)
    filament_d: float = 1.75
    flow: float = 1.0
    pillar_flow: float = 1.1854 # explicit over-extrusion at the pillar body. Was an accident —
                                # a wrong distance argument inflated it 1.13-1.6x — but it is what
                                # makes the pillar deposit ~0.406mm against a 0.400mm layer, so it
                                # is preserved deliberately rather than silently.
    jitter: float = 1.0         # mm of deterministic pillar offset — BREAKS GRID SYMMETRY.
                                # Measured 2026-07-25: a perfect grid makes star-order chords
                                # concurrent through the same points, and HALF of all crossing
                                # pairs collapse into shared welds (30 junctions from 60 pairs).
                                # 0.5mm of jitter recovers every one of them — 30 -> 66 junctions
                                # from identical material, order and mass. Symmetry was silently
                                # halving the control variable. Seeded, so coupons stay reproducible.
    jitter_seed: int = 7
    nozzle_d: float = 0.8       # orifice — sets the safe ceiling on line_w for STACKED geometry
    wipe_every: int = 0         # layers between a nozzle-wipe pass (0 = off)
    inset: float = 8.0          # keep pillars off the coupon edge
    prime_f: int = 3000         # from filament_max_volumetric_speed/0.3*60 (PLA ~15mm3/s)
    tally: int = 1              # raised bars on the base = which coupon this is
    home: bool = True           # False = skip G28 (only when already homed; saves the whole calibration)
    strand_w: float = 0.85      # STRAND width (mm) — ABSOLUTE, decoupled from line_w, but NEVER
                                # below the orifice (0.8): a nozzle cannot lay a narrower bead.
                                # Pillars and strands want opposite things: pillars chunky (wide
                                # line = sturdy anchor), strands THIN. The crackle is thin fused
                                # crossings SNAPPING; a fat strand bends quietly instead. So a wide
                                # pillar line must NOT drag the strand thickness up with it.
    strand_ratio: float = 0.35  # (legacy; strand_w wins when set)
    fast: bool = False          # skip calibration/nozzle-clean ceremony (see notes)
    machine: str = "k2"         # k2 | generic — k2 uses Creality's START_PRINT/END_PRINT macros
    start_gcode: str = ""       # if set, used VERBATIM instead of the generic start (see README)
    end_gcode: str = ""         # ditto
    base_f: int = 3000          # base is structural, not pretty — run it fast


PRESETS = {
    # The PRD's guess, made concrete — the control.
    "A": Params(name="A", tally=2, order="star"),
    # Axis 1: ORDER (the thesis says this dominates). Same everything else.
    "B": Params(name="B", tally=1, order="perimeter"),      # ~0 crossings -> should NOT crackle
    "C": Params(name="C", tally=3, order="serpentine"),     # few crossings
    "D": Params(name="D", tally=4, order="maxcross"),       # most crossings
    # Axis 2: crossing DENSITY at fixed order (travel-only cost)
    "E": Params(name="E", tally=7, order="star", passes=3),
    # Axis 3: does it WELD? fan on should kill the crackle if welding matters
    "F": Params(name="F", tally=5, order="star", fan=255),
    # Axis 4: finer web
    "G": Params(name="G", tally=6, order="star", n=6, pitch=0, layer_h=0.25, layers=16),  # time-budgeted
}

# ---------------------------------------------------------------- geometry
def pillar_xy(p: Params):
    """Pillars inset from the coupon edge, and the whole coupon offset onto the bed.
    (Both were bugs the validator caught: span==size put pillars ON the edge, and origin 0,0
    pushed their extrusion loops to negative coordinates.)"""
    pitch = p.pitch if p.pitch else (p.size - 2 * p.inset) / max(p.n - 1, 1)
    span = pitch * (p.n - 1)
    x0 = p.origin + (p.size - span) / 2
    grid = [(x0 + i * pitch, x0 + j * pitch) for j in range(p.n) for i in range(p.n)]
    if not p.jitter:
        return [(round(x, 3), round(y, 3)) for x, y in grid]
    # Deterministic symmetry-breaking. A perfect grid makes star-order chords concurrent through
    # the same points; measured 2026-07-25, half the crossing pairs collapsed into shared welds.
    # Sub-millimetre offset recovers all of them (30 -> 66 junctions) at zero material cost.
    # Seeded so a coupon is byte-reproducible and B/A stay comparable.
    rnd = random.Random(p.jitter_seed)
    return [(round(x + rnd.uniform(-p.jitter, p.jitter), 3),
             round(y + rnd.uniform(-p.jitter, p.jitter), 3)) for x, y in grid]
def visit_order(pts, mode, seed=0):
    k = len(pts)
    idx = list(range(k))
    if mode == "serpentine":
        return idx
    if mode == "perimeter":
        cx = sum(x for x, _ in pts) / k; cy = sum(y for _, y in pts) / k
        return sorted(idx, key=lambda i: math.atan2(pts[i][1] - cy, pts[i][0] - cx))
    if mode == "random":
        r = random.Random(seed); o = idx[:]; r.shuffle(o); return o
    if mode == "star":
        # walk the convex-angular order with a large stride -> star polygon -> many crossings
        cx = sum(x for x, _ in pts) / k; cy = sum(y for _, y in pts) / k
        ring = sorted(idx, key=lambda i: math.atan2(pts[i][1] - cy, pts[i][0] - cx))
        stride = max(2, k // 2 - 1)
        while math.gcd(stride, k) != 1 and stride > 2:   # coprime stride visits every point once
            stride -= 1
        return [ring[(m * stride) % k] for m in range(k)]
    if mode == "maxcross":
        # greedy: always jump to the farthest unvisited pillar -> long chords -> maximal crossing
        o = [0]; rest = set(idx) - {0}
        while rest:
            cur = pts[o[-1]]
            nxt = max(rest, key=lambda i: (pts[i][0]-cur[0])**2 + (pts[i][1]-cur[1])**2)
            o.append(nxt); rest.discard(nxt)
        return o
    raise SystemExit(f"unknown order: {mode}")

def _orient(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

def _seg_cross(a, b, c, d):
    """PROPER crossing only. The previous version used sign-inequality, which treats a TOUCH as a
    crossing: on a square grid, chords routinely pass exactly through another pillar's centre, and
    every one of those was counted. That inflated coupon A from 60 real crossings to 77."""
    d1, d2 = _orient(c, d, a), _orient(c, d, b)
    d3, d4 = _orient(a, b, c), _orient(a, b, d)
    if not (((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))):
        return None
    if min(abs(d1), abs(d2), abs(d3), abs(d4)) <= 1e-9:
        return None
    den = (b[0]-a[0])*(d[1]-c[1]) - (b[1]-a[1])*(d[0]-c[0])
    if abs(den) < 1e-12:
        return None
    t = ((c[0]-a[0])*(d[1]-c[1]) - (c[1]-a[1])*(d[0]-c[0])) / den
    return (a[0] + t*(b[0]-a[0]), a[1] + t*(b[1]-a[1]))

def count_crossings(pts, order):
    """THE control number — and it is DISTINCT JUNCTION POINTS, not crossing pairs.

    Measured 2026-07-25 against the emitted gcode: on a symmetric grid the star order makes many
    chords concurrent through the SAME point (12 hubs on coupon A, the busiest carrying 5 pairs at
    the grid centre). Half of all crossing pairs collapse onto shared locations. Physically that is
    one fused weld, not five independent ones, and the thesis is about junctions SNAPPING — so
    distinct points is the quantity that matches the mechanism.

    Consequence worth keeping in view: 'star = maximal crossings' is false in this sense. Star
    maximises pairs while concentrating them; maxcross distributes better and yields MORE distinct
    junctions despite a lower pair count.

    Returns (distinct_points, pairs) — pairs kept because a 5-way hub is a stronger weld than a
    2-way one, so it is a real secondary variable, just not the control.
    """
    segs = [(pts[order[i]], pts[order[i+1]]) for i in range(len(order)-1)]
    locs = []
    for i in range(len(segs)):
        for j in range(i+2, len(segs)):        # skip adjacent (they share an endpoint)
            r = _seg_cross(*segs[i], *segs[j])
            if r: locs.append((round(r[0], 2), round(r[1], 2)))
    return len(set(locs)), len(locs)

# ---------------------------------------------------------------- gcode
class G:
    def __init__(self, p: Params):
        self.p = p; self.L = []; self.e = 0.0
        area = math.pi * (p.filament_d/2)**2
        # STACKING GUARD (added after the 2026-07-25 tower failure — see notes/ and flowtest.py).
        # A commanded width far wider than the orifice does not give a wide bead, it gives a TALL
        # one: cross-section line_w*layer_h is conserved, the nozzle can only spread it so far, so
        # the excess goes into height. The part then climbs faster than Z does, the nozzle ploughs
        # into it, and it drags the part off the plate. The crackle coupon STACKS, so it is exposed
        # to exactly this. Cap the commanded width at 1.5x the orifice.
        max_w = p.nozzle_d * 1.5
        if p.line_w > max_w + 1e-9:
            landed = p.nozzle_d * 1.2                     # realistic spread from a round orifice
            grew = (p.line_w * p.layer_h) / landed
            raise SystemExit(
                f"line_w={p.line_w} is too wide for a {p.nozzle_d}mm nozzle on STACKED geometry.\n"
                f"  It would land ~{landed:.1f}mm wide and therefore ~{grew:.2f}mm TALL against a "
                f"{p.layer_h}mm Z step,\n  so the part gains ~{grew - p.layer_h:.2f}mm per layer on "
                f"the nozzle and gets ploughed off the plate.\n"
                f"  Use line_w <= {max_w:.1f}, or make it a SINGLE layer (flowtest.py) where nothing "
                f"stacks and any width is safe.")
        self.mm_per_mm = (p.line_w * p.layer_h) / area * p.flow   # filament mm per mm of travel
    def w(self, s): self.L.append(s)
    def move(self, x, y, f=None):                      # plain travel, no material (base/setup only)
        self.w(f"G0 F{f or self.p.travel_f} X{x:.3f} Y{y:.3f}")
    def strand(self, x, y, dist, f=None):
        """DRAW the strand instead of hoping for ooze.
        v1 used a bare G0 here and relied on the nozzle bleeding material across the move. It does
        not: pressure drops over a long fast travel, so the pillars got almost nothing and the top
        of the coupon failed to extrude (observed 2026-07-25 on coupon A — base fine, web empty).
        A small deliberate E gives a thin strand AND keeps nozzle pressure up so pillars build."""
        # strand flow uses its OWN width, not the pillar line width
        per_mm = (self.p.strand_w * self.p.layer_h) / (math.pi * (self.p.filament_d/2)**2)
        self.e += dist * per_mm
        self.w(f"G1 F{f or self.p.travel_f} X{x:.3f} Y{y:.3f} E{self.e:.5f}")
    def extrude_to(self, x, y, dist, f=None):
        self.e += dist * self.mm_per_mm
        self.w(f"G1 F{f or self.p.print_f} X{x:.3f} Y{y:.3f} E{self.e:.5f}")
    def z(self, z): self.w(f"G0 Z{z:.3f}")

def g_last(g):
    return None

def emit(p: Params) -> tuple[str, dict]:
    pts = pillar_xy(p)
    base_order = visit_order(pts, p.order)
    xr, xpairs = count_crossings(pts, base_order)   # junctions, pairs

    g = G(p)
    g.w(f"; crackle coupon {p.name} — order={p.order} junctions/layer={xr} (pairs={xpairs}) passes={p.passes}")
    g.w(f"; {p.size}mm, {p.n}x{p.n} pillars, {p.layers}x{p.layer_h}mm, T{p.temp} fan{p.fan}")
    g.w("; RETRACTION / COMBING / Z-HOP / WIPE ARE DELIBERATELY ABSENT — the travels are the product.")
    for k, v in asdict(p).items(): g.w(f"; param {k}={v}")
    # --- start ---
    # PREFER THE MACHINE'S OWN START BLOCK. Rather than me guessing a K2 Plus start sequence,
    # slice anything in Creality Print, open the .gcode, and copy everything before the first layer
    # into a file -> pass it with --start-gcode. It already has the right homing, probing, chamber
    # and prime for this machine. The generic block below is only a fallback.
    if p.machine == "k2" and p.fast and not p.start_gcode.strip():
        # FAST START — for iterating. Skips START_PRINT's 140C soak, its TWO nozzle-clean passes and
        # its second Z home. That ceremony can cost more minutes than a 4-minute coupon.
        # KEPT: G28. Homing is not ceremony — Klipper refuses to move an unhomed axis, and a wrong
        # Z here gouges the plate. This is the one thing that must not be removed.
        # TRADE-OFF, honestly: no nozzle clean before probing means an oozy nozzle can bias Z. This
        # print doesn't need a pretty first layer — it needs the lattice to STICK. Eyeball the first
        # layer on your first fast run; if adhesion is poor, do one normal (non-fast) print to
        # re-establish a clean Z, then go back to fast.
        g.w("; HEADER_BLOCK_START"); g.w(f"; total layer number: {p.base_layers + p.layers}")
        g.w("; HEADER_BLOCK_END")
        g.w("; FAST START — no START_PRINT macro, no nozzle clean, no 140C soak, single home.")
        g.w(f"M140 S{p.bed}"); g.w(f"M104 S{p.temp}")
        g.w("G90")
        if p.home:
            g.w("G28")     # NOTE: on the K2 this is the expensive bit — it heats to 140C and
                           # strain-gauge probes. THAT is the "calibration" you see, not START_PRINT.
        else:
            g.w("; NO HOME — reusing the position from the previous print (steppers were left on).")
            g.w("; If the machine was powered/disabled since, this errors safely: 'Must home axis first'.")
        g.w(f"M190 S{p.bed}"); g.w(f"M109 S{p.temp}")
        g.w("M204 S2000"); g.w("M83")
        g.w("G1 Z0.3 F600")                                  # short prime line at the bed edge
        g.w("G1 X10 Y10 F9000"); g.w("G1 X90 Y10 E9 F1200")
        g.w("G92 E0"); g.w("G1 Z1 F600")
        g.w(f"M106 S{p.fan}" if p.fan else "M107")
    elif p.machine == "k2" and not p.start_gcode.strip():
        # EXTRACTED VERBATIM from this machine's own profile on this laptop:
        #   Creality Print 7.0 / system/Creality/machine/"Creality K2 Plus 0.4 nozzle.json"
        #   -> machine_start_gcode, single-colour ({else}) branch, template vars resolved.
        # Ground truth beats a reconstruction. DO NOT hand-roll G28: the K2 probes with a strain
        # gauge through the nozzle and START_PRINT cleans it twice before homing Z.
        g.w("; HEADER_BLOCK_START")
        g.w(f"; total layer number: {p.base_layers + p.layers}")
        g.w("; HEADER_BLOCK_END")
        g.w("; SET PRINT AREA MIN AND MAX COORDINATES TO ENABLE ADAPTIVE PROBING")
        g.w(f"; MINX = {p.origin:.1f}"); g.w(f"; MINY = {p.origin:.1f}")
        g.w(f"; MAXX = {p.origin + p.size:.1f}"); g.w(f"; MAXY = {p.origin + p.size:.1f}")
        g.w("M140 S0"); g.w("M104 S0")
        g.w(f"START_PRINT EXTRUDER_TEMP={p.temp} BED_TEMP={p.bed}")
        g.w("T0")
        g.w(f"M104 S{p.temp}")
        g.w("M204 S2000")
        g.w("G1 Z3 F600")
        g.w("M83")
        g.w("G1 Y150 F12000"); g.w("G1 X0 F12000")
        g.w("G1 Z0.2 F600"); g.w("G1 X0 Y150 F6000")
        g.w("G1 E0.8 F300")
        g.w(f"G1 X0 Y0 E9 F{p.prime_f}"); g.w(f"G1 X150 Y0 E9 F{p.prime_f}")
        g.w("G92 E0"); g.w("G1 Z1 F600")
        g.w(f"M109 S{p.temp}")
        g.w(f"M106 S{p.fan}" if p.fan else "M107")   # OUR fan — the experiment depends on it
    elif p.start_gcode.strip():
        g.w("; ---- machine start block (supplied verbatim) ----")
        for line in p.start_gcode.splitlines(): g.w(line)
        g.w("; ---- end machine start block ----")
        g.w(f"M104 S{p.temp}"); g.w(f"M109 S{p.temp}")     # enforce OUR temp, whatever the block set
        g.w(f"M106 S{p.fan}" if p.fan else "M107")         # and OUR fan — the experiment depends on it
    else:
        g.w("; GENERIC start — replace with your machine's own block via --start-gcode (see README)")
        g.w("M190 S%d" % p.bed); g.w("M104 S%d" % p.temp)
        g.w("G28"); g.w("G90"); g.w("M83")
        g.w("M109 S%d" % p.temp)
        g.w(f"M106 S{p.fan}" if p.fan else "M107")
        g.w("; prime line")
        g.w(f"G0 Z{p.layer_h:.2f} F3000"); g.w("G0 X5 Y5 F6000")
        g.w("G1 X55 Y5 E14 F1200"); g.w("G1 X55 Y5.6 E0.6 F1200"); g.w("G1 X5 Y5.6 E14 F1200")
    g.w("G92 E0")
    g.e = 0.0
    g.w("M82"); g.w("G92 E0")                              # body is absolute-E

    z = 0.0
    # --- anchor base: solid-ish slab so pillars survive drag AND the coupon peels off intact ---
    for b in range(p.base_layers):
        z = round(z + p.layer_h, 3); g.z(z)
        g.w(f"; base layer {b+1} — LATTICE, not a solid slab.")
        # The validator showed a solid slab was ~88% of print time and blew the 6-min budget.
        # The base only has two jobs: anchor every pillar against nozzle drag, and hold the coupon
        # together so it peels off and can be stood on. A perimeter frame + ribs through every
        # pillar row/column does both for ~1/8 the extrusion.
        # Frame sized from the ACTUAL pillar bounding box, not from origin/size.
        # Those two were computed by different formulas and diverged silently: pitch defaults to
        # 20.0 (truthy), so `inset` is never applied, and the pillar span is pitch*(n-1) while the
        # base stayed origin+3 .. origin+size-3. At the defaults the corner pillars land exactly ON
        # the coupon edge with no base under them; on the dose-response ladder (--vary n=4,5,6,7)
        # the span grows to 120mm while the base stays 54mm, leaving 16 of 49 pillars unanchored
        # and 8 ribs laid OUTSIDE the frame as loose lines on bare plate. Unanchored pillars are
        # dragged loose by the first strand travel, and the ladder stops being a one-factor sweep
        # because the footprint doubles too. Found by the adversarial audit, 2026-07-25.
        _px = [q[0] for q in pts]; _py = [q[1] for q in pts]
        x0, y0 = min(_px) - 3.0, min(_py) - 3.0
        x1, y1 = max(_px) + 3.0, max(_py) + 3.0
        g.move(x0, y0)
        for (tx, ty) in [(x1, y0), (x1, y1), (x0, y1), (x0, y0)]:      # frame, 2 loops
            g.extrude_to(tx, ty, math.dist((g_last(g) or (x0, y0)), (tx, ty)) if False else abs(tx - x0) + abs(ty - y0) or p.size, f=p.base_f)
        off = p.line_w * 0.9
        g.move(x0 + off, y0 + off)
        for (tx, ty) in [(x1-off, y0+off), (x1-off, y1-off), (x0+off, y1-off), (x0+off, y0+off)]:
            g.extrude_to(tx, ty, p.size, f=p.base_f)
        # ID TALLY — N raised bars at the front-left corner, N = coupon index.
        # Six identical 60mm black squares are unscoreable in a pile; this is countable by eye and
        # by fingertip, which matters because the protocol asks you to score BLIND.
        tally = p.tally
        for t in range(tally):
            bx = x0 + 4.0 + t * (p.line_w * 2.2)
            g.move(bx, y0 + 1.5); g.extrude_to(bx, y0 + 7.5, 6.0, f=p.base_f)
        rows = sorted({y for _, y in pts}); cols = sorted({x for x, _ in pts})
        for yy in rows:                                                 # rib per pillar row
            g.move(x0, yy); g.extrude_to(x1, yy, x1 - x0, f=p.base_f)
        for xx in cols:                                                 # rib per pillar column
            g.move(xx, y0); g.extrude_to(xx, y1, y1 - y0, f=p.base_f)

    # --- web: pillars + crossing travels ---
    last_x = last_y = None
    for layer in range(p.layers):
        z = round(z + p.layer_h, 3); g.z(z)
        order = base_order if not p.rotate_per_layer else \
            base_order[layer % len(base_order):] + base_order[:layer % len(base_order)]
        g.w(f"; web layer {layer+1}  crossings~{xr*p.passes}")
        for _pass in range(p.passes):
            for i, pi in enumerate(order):
                x, y = pts[pi]
                d = math.dist((last_x, last_y), (x, y)) if last_x is not None else 0.0
                if d > 0: g.strand(x, y, d)        # <- the strand, deliberately drawn
                else: g.move(x, y)
                last_x, last_y = x, y
                # Lay a little material AT the pillar so it has a body to anchor the web —
                # but ONLY on the first pass. Re-running it deposited the pillar body once PER
                # PASS at the same XY and the same Z: preset E (passes=3) put 4.32mm3 into a
                # ~3.55mm2 footprint = 1.22mm of height against a 0.40mm Z step, gaining
                # +0.82mm/layer on the nozzle. That is the tower failure again, except on 16 rigid
                # pillars glued to a base rather than a thin wall that could peel — it would shear
                # the coupon off the plate or stall the gantry. The docstring already promised
                # extra passes cost "travel time only, ~no filament"; now that is true.
                # Found 2026-07-25 by the adversarial toolchain audit; verified by counting pillar
                # re-visits in the emitted gcode (3x per layer for preset E).
                if _pass == 0:
                    r = p.line_w * 0.6
                    # extrude_to's third argument is the DISTANCE used to compute E. It used to be
                    # passed as r*1.6 while the head actually moved r (or r*sqrt(2) between arms),
                    # so the pillar silently over-extruded 1.6x on the first arm and 1.13x on the
                    # rest. Measured from the emitted gcode as bead cross-sections of 0.58 and 0.41
                    # against a nominal 0.36 mm2.
                    # That inflation turned out to be LOAD-BEARING by accident: it is what brings
                    # the pillar to ~0.406mm of deposit per 0.400mm layer. Removing it naively
                    # would under-fill the pillars and the web would stop anchoring. So the
                    # distance is now truthful and the extra material is an EXPLICIT multiplier
                    # that preserves the current physical result.
                    prev = (x, y)
                    for a in range(4):
                        ang = (a + 1) * math.pi / 2
                        tip = (x + r*math.cos(ang), y + r*math.sin(ang))
                        g.extrude_to(tip[0], tip[1], math.dist(prev, tip) * p.pillar_flow,
                                     f=p.print_f)
                        prev = tip
                    g.extrude_to(x, y, math.dist(prev, (x, y)) * p.pillar_flow, f=p.print_f)
        if p.wipe_every and (layer + 1) % p.wipe_every == 0:
            g.w("; wipe pass — shed accumulated ooze on the base edge")
            _wx = [q[0] for q in pts]; _wy = [q[1] for q in pts]
            g.move(min(_wx) - 3.0, min(_wy) - 3.0, f=9000)
            g.extrude_to(max(_wx) + 3.0, min(_wy) - 3.0, max(_wx) - min(_wx) + 6.0, f=3000)
    # --- end ---
    if p.machine == "k2" and not p.end_gcode.strip():
        if p.fast:
            g.w("M107"); g.w("M104 S0"); g.w("M140 S0")
            g.w(f"G1 Z{z + 30:.1f} F900")                    # lift clear so you can grab the coupon
            g.w("G1 X10 Y330 F9000")                          # park at the BACK — head clear of the plate
            g.w("; steppers deliberately LEFT ON: disabling them loses the homed position and the")
            g.w("; next coupon would have to re-run the 140C strain-gauge calibration.")
        else:
            g.w("END_PRINT")
            g.w("M84")
    elif p.end_gcode.strip():
        g.w("; ---- machine end block (supplied verbatim) ----")
        for line in p.end_gcode.splitlines(): g.w(line)
    else:
        g.w("M107"); g.w("M104 S0"); g.w("M140 S0")
        g.w(f"G0 Z{z + 20:.2f} F1200"); g.w("G0 X5 Y{:.0f} F6000".format(p.origin + p.size + 20))
        g.w("M84")
    grams = g.e * math.pi * (p.filament_d/2)**2 * 1.24 / 1000
    stats = {"crossings_per_layer": xr, "crossings_total": xr * p.passes * p.layers,
             "filament_mm": round(g.e, 1), "grams": round(grams, 2),
             "moves": len(g.L)}
    return "\n".join(g.L) + "\n", stats

# ---------------------------------------------------------------- cli
def write(p: Params, outdir="out"):
    gcode, st = emit(p)
    os.makedirs(outdir, exist_ok=True)
    tag = ("iter_" if (p.fast and not p.home) else "fast_") if p.fast else ""
    fn = f"{outdir}/crackle_{tag}{p.name}_{p.order}_x{st['crossings_per_layer']}_T{p.temp}_fan{p.fan}.gcode"
    open(fn, "w").write(gcode)
    print(f"{p.name:>3}  order={p.order:<11} crossings/layer={st['crossings_per_layer']:>3} "
          f"total={st['crossings_total']:>5}  {st['grams']:>5.2f} g  -> {fn}")
    return fn, st

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default=None)
    ap.add_argument("--sweep", default=None, choices=["order", "all"])
    ap.add_argument("--max-flow", type=float, default=None,
                    help="measured max volumetric flow (mm3/s) from flowtest — derives speeds")
    ap.add_argument("--layers", type=int, default=None, help="override layer count (ladders: keep constant)")
    ap.add_argument("--vary", default=None,
                    help="one-factor-at-a-time sweep of ANY parameter, e.g. --vary n=4,5,6,7 "
                         "or --vary passes=1,2,4 or --vary temp=210,230,250 (base preset via --preset)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", default="out")
    ap.add_argument("--no-home", action="store_true", help="skip G28 — for back-to-back coupons on an already-homed printer")
    ap.add_argument("--fast", action="store_true", help="skip calibration + nozzle cleaning for quick iteration")
    ap.add_argument("--machine", default="k2", choices=["k2","generic"])
    ap.add_argument("--start-gcode", default=None, help="file with your machine's start block, used verbatim")
    ap.add_argument("--end-gcode", default=None, help="file with your machine's end block")
    a = ap.parse_args()
    if a.max_flow:
        # Derive strand + travel settings from the MEASURED melt ceiling instead of guessing.
        # Working flow = 0.85 x measured. Pillars extrude at that; strands get strand_ratio of it.
        # Travel speed is then set so the strand is thin but continuous:
        #   strand_area = line_w*layer_h*strand_ratio  ->  v = working_flow / strand_area
        # Oleg, 2026-07-25: "you should be extruding at max speed we know nozzle can flow. that is
        # not negotiable. 100% of the time" and "i dont care of uneven lines". So no 0.85 discount:
        # machine.FLOW is already the max-known-good (highest flow observed still laying solid,
        # below the 81.2 where skipping starts).
        wf = a.max_flow
        for k, P in PRESETS.items():
            sa = P.strand_w * P.layer_h
            v = wf / sa                     # mm/s
            # Caps are the MACHINE's limit now, not numbers I picked. The old 12000/9000 held the
            # strand to 68 mm3/s and the pillar to 54 against a measured 80 ceiling.
            PRESETS[k] = replace(P, travel_f=int(min(max(v*60, 1800), machine.MAX_VELOCITY*60)),
                                 print_f=int(min(wf/(P.line_w*P.layer_h)*60,
                                                 machine.MAX_VELOCITY*60)))
        print(f"tuned from measured max flow {a.max_flow} mm3/s -> working {wf:.1f}; "
              f"strand travel {PRESETS['A'].travel_f/60:.0f} mm/s, pillar {PRESETS['A'].print_f/60:.0f} mm/s")
    _sg = open(a.start_gcode).read() if a.start_gcode else ""
    _eg = open(a.end_gcode).read() if a.end_gcode else ""
    for k in PRESETS: PRESETS[k] = replace(PRESETS[k], fast=a.fast, home=not a.no_home, machine=a.machine, start_gcode=_sg, end_gcode=_eg)
    if a.list:
        for k, v in PRESETS.items(): print(f"{k}: order={v.order} passes={v.passes} fan={v.fan} n={v.n}")
        sys.exit(0)
    if a.vary:
        # One factor at a time, per the PRD. Everything else stays at the base preset so a
        # difference in feel is attributable to ONE change.
        key, _, vals = a.vary.partition("=")
        base = PRESETS[a.preset or "A"]
        if not hasattr(base, key): raise SystemExit(f"no such parameter: {key}")
        cast = type(getattr(base, key))
        for i, raw in enumerate(v.strip() for v in vals.split(",")):
            val = cast(raw) if cast is not bool else raw.lower() in ("1", "true", "yes")
            # Ladder coupons keep layers CONSTANT (thickness must not vary — a thicker coupon has
            # more to crush and would confound the comparison) but shorter than the main sweep,
            # because print time rises with crossing density. Override with --layers.
            write(replace(base, **{key: val}, name=f"{base.name}{key[:3]}{raw}", tally=i + 1,
                          layers=a.layers or base.layers), a.out)
        sys.exit(0)
    if a.sweep == "order":
        for k in ["B", "C", "A", "D"]: write(PRESETS[k], a.out)     # ~0 -> max crossings
    elif a.sweep == "all":
        for k in PRESETS: write(PRESETS[k], a.out)
    else:
        write(PRESETS[a.preset or "A"], a.out)
