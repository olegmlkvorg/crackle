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
import argparse, itertools, math, os, random, sys
from dataclasses import dataclass, asdict, replace

# ---------------------------------------------------------------- parameters
@dataclass
class Params:
    name: str = "A"
    origin: float = 40.0        # BUG FIX: coupon was at 0,0 so edge pillars ran off the bed
    size: float = 60.0          # coupon footprint (mm, square)
    n: int = 4                  # pillars per side (n*n total)
    pitch: float = 20.0         # pillar spacing (mm) — set from size/n if 0
    layer_h: float = 0.30
    layers: int = 20            # ~6 mm tall — enough to stand on, inside the time budget
    line_w: float = 0.60        # extrusion width (0.4 nozzle, fat line = sturdier pillar)
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
    wipe_every: int = 0         # layers between a nozzle-wipe pass (0 = off)
    inset: float = 8.0          # keep pillars off the coupon edge
    prime_f: int = 3000         # from filament_max_volumetric_speed/0.3*60 (PLA ~15mm3/s)
    tally: int = 1              # raised bars on the base = which coupon this is
    home: bool = True           # False = skip G28 (only when already homed; saves the whole calibration)
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
    return [(round(x0 + i * pitch, 3), round(x0 + j * pitch, 3))
            for j in range(p.n) for i in range(p.n)]

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

def _seg_cross(a, b, c, d):
    def o(p, q, r): return (q[1]-p[1])*(r[0]-q[0]) - (q[0]-p[0])*(r[1]-q[1])
    def sgn(v): return (v > 1e-9) - (v < -1e-9)
    return sgn(o(a,b,c)) != sgn(o(a,b,d)) and sgn(o(c,d,a)) != sgn(o(c,d,b))

def count_crossings(pts, order):
    """THE control number: how many times do this layer's travel chords cross each other."""
    segs = [(pts[order[i]], pts[order[i+1]]) for i in range(len(order)-1)]
    n = 0
    for i in range(len(segs)):
        for j in range(i+2, len(segs)):        # skip adjacent (they share an endpoint)
            if _seg_cross(*segs[i], *segs[j]): n += 1
    return n

# ---------------------------------------------------------------- gcode
class G:
    def __init__(self, p: Params):
        self.p = p; self.L = []; self.e = 0.0
        area = math.pi * (p.filament_d/2)**2
        self.mm_per_mm = (p.line_w * p.layer_h) / area * p.flow   # filament mm per mm of travel
    def w(self, s): self.L.append(s)
    def move(self, x, y, f=None):                      # TRAVEL — no retraction: this draws a strand
        self.w(f"G0 F{f or self.p.travel_f} X{x:.3f} Y{y:.3f}")
    def extrude_to(self, x, y, dist, f=None):
        self.e += dist * self.mm_per_mm
        self.w(f"G1 F{f or self.p.print_f} X{x:.3f} Y{y:.3f} E{self.e:.5f}")
    def z(self, z): self.w(f"G0 Z{z:.3f}")

def g_last(g):
    return None

def emit(p: Params) -> tuple[str, dict]:
    pts = pillar_xy(p)
    base_order = visit_order(pts, p.order)
    xr = count_crossings(pts, base_order)

    g = G(p)
    g.w(f"; crackle coupon {p.name} — order={p.order} crossings/layer={xr} passes={p.passes}")
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
        x0, y0 = p.origin + 3.0, p.origin + 3.0
        x1, y1 = p.origin + p.size - 3.0, p.origin + p.size - 3.0
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
    for layer in range(p.layers):
        z = round(z + p.layer_h, 3); g.z(z)
        order = base_order if not p.rotate_per_layer else \
            base_order[layer % len(base_order):] + base_order[:layer % len(base_order)]
        g.w(f"; web layer {layer+1}  crossings~{xr*p.passes}")
        for _ in range(p.passes):
            for i, pi in enumerate(order):
                x, y = pts[pi]
                g.move(x, y)                      # <- the strand: molten drag through open air
                # lay a little material AT the pillar so it has a body to anchor the web
                r = p.line_w * 0.6
                for a in range(4):
                    ang = (a + 1) * math.pi / 2
                    g.extrude_to(x + r*math.cos(ang), y + r*math.sin(ang), r*1.6, f=p.print_f)
                g.extrude_to(x, y, r, f=p.print_f)
        if p.wipe_every and (layer + 1) % p.wipe_every == 0:
            g.w("; wipe pass — shed accumulated ooze on the base edge")
            g.move(p.origin + 3.0, p.origin + 3.0, f=9000); g.extrude_to(p.origin + p.size - 3.0, p.origin + 3.0, p.size - 6.0, f=3000)
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
