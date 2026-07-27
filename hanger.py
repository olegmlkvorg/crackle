#!/usr/bin/env python3
"""HANGER — a hook and a hole, a couple of layers thick.

Oleg, 2026-07-27: "and on k1 lets print hangers, hist a hook and a hole coule layers width".

The whole part is ONE flat 2D region extruded a few layers up, which is the only thing this
toolchain makes natively: vertical walls, no bridges, no supports. A hook lying flat on the plate
is the ideal case for it — the shape IS the cross-section.

WHY THE HOOK OPENS SIDEWAYS, not upward. Printed flat, the layers stack through the hook's
THICKNESS, so a load pulling the hook open peels along layer lines only if the opening faces the
build direction. Lying flat, the load runs across the beads in-plane, which is the strong axis of
an FDM part by a wide margin. This orientation is chosen for strength, not convenience.

The hole is a real hole: the region is a difference, so the toolpath walks around it and the
bore is a printed wall rather than a gap in an infill pattern.
"""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
from shapely.affinity import translate

import machine
import solid as S


def bore_for(hole_d, bead_w):
    """The MODELLED hole that yields `hole_d` after printing.

    A hole is drawn as a centreline ring, but the bead has width and the hot material bulges
    INWARD into the void -- so a 2.5mm modelled hole came out solid. Measured on the rosetta:
    the inset from centreline to material edge is 1.373 x bead, not the geometric half-bead.

    Verified against the printed hanger: modelled 2.5 -> centreline r 0.92 -> material edge
    0.92 - 0.915 = 0.005mm. No hole at all, which is exactly what Oleg reported.
    """
    # was 1.373 x bead -- a proportion fitted to ONE measurement. A second measurement on a
    # different bead disagreed by 50% as a proportion but matched within 3% as an absolute, so
    # the inset is a constant ~3.02 mm. See machine.BORE_INSET_MM.
    return machine.bore_model(hole_d)


def hook_region(shank, hook_r, thick, hole_d, gap_deg, tip):
    """A J: straight shank, a hook curled off the bottom, an eye at the top.

    Everything is built as a fattened CENTRELINE (LineString.buffer), so the wall thickness is one
    number and there are no thin slivers where parts meet -- the union of round-capped strokes is
    always at least `thick` wide.
    """
    r = thick / 2.0
    # THE EYE RING IS SIZED INDEPENDENTLY OF THE STROKE, and never thinner than two beads.
    # It used to be hole_d/2 + thick/2, i.e. a ring exactly `thick` wide. Once the hole was
    # compensated for bead width the inner cut (r 4.27) grew larger than the shank's own
    # half-width (1.84), so the subtraction ATE THE TOP OF THE SHANK and left a one-bead cup
    # with no hole at all -- which is exactly what Oleg got in his hand: "the hook you printed
    # does not have a hole for thread".
    ring = max(thick, 3.7)                      # >= 2 beads of material all round the hole
    eye_r = hole_d / 2.0 + ring
    top = shank                                  # eye centre sits at the top of the shank

    # shank: straight up the middle
    parts = [LineString([(0.0, 0.0), (0.0, top)]).buffer(r, resolution=16)]

    # eye: an annulus at the top
    parts.append(Point(0.0, top).buffer(eye_r, resolution=48))

    # hook: an arc curling from the shank foot, opening to one side
    #   sweeps from -90deg (straight down off the shank) round to the gap
    a0, a1 = -90.0, -90.0 - (360.0 - gap_deg)
    cx, cy = 0.0, -hook_r
    pts = []
    n = max(24, int(abs(a1 - a0) / 3))
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((cx + hook_r * math.cos(a), cy + hook_r * math.sin(a)))
    parts.append(LineString(pts).buffer(r, resolution=16))

    # tip: a short straight run off the hook end so it does not simply stop mid-air
    if tip > 0:
        ax, ay = pts[-1]
        bx, by = pts[-2]
        dx, dy = ax - bx, ay - by
        m = math.hypot(dx, dy) or 1.0
        parts.append(LineString([(ax, ay), (ax + dx / m * tip, ay + dy / m * tip)])
                     .buffer(r, resolution=16))

    body = unary_union(parts)
    return body.difference(Point(0.0, top).buffer(hole_d / 2.0, resolution=48))


def lip_region(wall, grip, shank, hook_r, thick, hole_d, tip):
    """An over-the-edge hook: hangs on a vertical wall by hooking OVER its top.

    Different animal from the J. The J hangs FROM something by its eye. This one grips a lip:
      * a short back leg drops down the far side of the wall
      * a 180-degree arc passes over the top, its inner clearance sized to the WALL THICKNESS
      * the front leg (shank) descends on the near side
      * the load hook curls forward off the bottom

    The mouth is `wall` wide at the inside of the arc, so the part sits on the lip rather than
    being sprung onto it -- a printed part sprung over an edge is a part loaded in cleavage
    along its layer lines, which is the weak direction.
    """
    r = thick / 2.0
    inner = wall / 2.0                       # arc centreline radius: half the wall + half a wall
    cr = inner + r                           # centreline of the stroke going over the lip
    parts = []

    # back leg: down the far side
    bx = -cr
    parts.append(LineString([(bx, 0.0), (bx, -grip)]).buffer(r, resolution=16))

    # the arc over the top of the wall
    pts = []
    n = 48
    for i in range(n + 1):
        a = math.pi - math.pi * i / n        # 180deg -> 0deg
        pts.append((cr * math.cos(a), cr * math.sin(a)))
    parts.append(LineString(pts).buffer(r, resolution=16))

    # front leg / shank: down the near side
    fx = cr
    parts.append(LineString([(fx, 0.0), (fx, -shank)]).buffer(r, resolution=16))

    # load hook: curls FORWARD off the bottom of the shank
    cx, cy = fx + hook_r, -shank
    arc = []
    for i in range(37):
        a = math.radians(180.0 - 150.0 * i / 36.0)
        arc.append((cx + hook_r * math.cos(a), cy + hook_r * math.sin(a)))
    parts.append(LineString(arc).buffer(r, resolution=16))
    if tip > 0:
        ax, ay = arc[-1]; bx2, by2 = arc[-2]
        dx, dy = ax - bx2, ay - by2
        m = math.hypot(dx, dy) or 1.0
        parts.append(LineString([(ax, ay), (ax + dx / m * tip, ay + dy / m * tip)])
                     .buffer(r, resolution=16))

    body = unary_union(parts)
    if hole_d > 0:                            # optional eye through the back leg
        body = body.difference(Point(bx, -grip + hole_d).buffer(hole_d / 2.0, resolution=32))
    return body


def simple_region(length, lip, thick, thread_d, width):
    """A plain hook: flat bar, thread hole at the top, a short upturned lip at the bottom.

    Oleg, 2026-07-27: "the hook you printed does not have a hole for thread and vertical hanger
    is real bad, why make it like a pirate hook".

    Both fair. The J had a dramatic 265-degree curl -- decorative, weak (a long lever arm on a
    thin section) and it had no way to attach a thread. This is the useful shape instead:
      * a straight flat bar, so the load path is a short column, not a lever
      * a THREAD HOLE at the top, sized to pass cord and knot it
      * a short upturned lip at the bottom -- deep enough to retain, shallow enough not to be a
        moment arm

    Width and thickness are separate: `width` is the bar across the face (strength in the load
    direction), `thick` is the stroke of the lip.
    """
    r = thick / 2.0
    # the bar: a fattened vertical line, `width` across
    bar = LineString([(0.0, 0.0), (0.0, length)]).buffer(width / 2.0, resolution=16)
    # the lip: a quarter-turn up off the bottom, short
    lr = max(lip, thick)
    pts = []
    for i in range(25):
        a = math.radians(180.0 + 90.0 * i / 24.0)
        pts.append((lr + lr * math.cos(a), lr * math.sin(a)))
    lipseg = LineString([(0.0, 0.0)] + pts).buffer(r, resolution=16)
    body = unary_union([bar, lipseg])
    # thread hole, one diameter down from the top so there is material all round it
    if thread_d > 0:
        body = body.difference(Point(0.0, length - thread_d).buffer(thread_d / 2.0, resolution=32))
    return body


def pole_region(pole_d, ring, drop, hook_r, thick, tip, bead_w):
    """A CLOSED collar for a vertical pole, with a hook hanging below it.

    Oleg, 2026-07-27: "make the hook proper the hole will pool downwards so the hook has to be
    closed!! on top to vertical poll".

    The load hangs DOWN, so the attachment cannot be a C that could lift off -- it is a full ring
    that drops over the top of the pole and cannot escape sideways no matter how it is loaded.
    Everything below the ring is the hanging part.

    The ring bore is compensated the same way every other hole here is: the printed bore comes out
    smaller than modelled by ~1.373 x bead per side, so the model has to be bigger than the pole.
    A collar that grips is a collar that must be forced on, so this aims for a SLIDING fit and
    lets gravity plus the hook's own offset load do the holding -- the hook hangs off one side, so
    the ring cants and jams against the pole under load, which is how a real pole hook works.
    """
    r = thick / 2.0
    # SLIDING FIT, not line-to-line. bore_model() only compensates the inward bead bulge, so on its
    # own it lands the PRINTED bore AT the pole diameter -- zero clearance, i.e. a press/grip fit.
    # Measured: the k1c inset is 3.060 against the 3.02 mean baked into bore_model, so it is really
    # ~0.08mm of INTERFERENCE at the pole. This collar must SLIDE onto the pole and be held by
    # canting under load (see the docstring), so add a diametral slip clearance on top of the bulge
    # compensation. 0.25mm is the repo's own "slip" value from solid.py's --clearance scale
    # ("0 grip, 0.25 slip, 0.5 loose") -- an engineering convention, CHOSEN, NOT a measured fit for
    # any particular pole (and deliberately NOT STICK_FIT, which is the measured *bamboo* number, or
    # SHRINK, which is a metal *grip* fit). Net printed clearance after the ~0.08 gap is ~0.17mm.
    SLIP_CLEAR = 0.25
    bore = machine.bore_model(pole_d) + SLIP_CLEAR   # modelled for a sliding fit over the pole
    # THE COLLAR WALL IS AN EVEN NUMBER OF BEADS — stricter than the bucket rim's whole-bead
    # rule, for a measured reason. Fractional (--ring 4.0 = 2.67 beads): the ring families
    # collide head-on, the clash filter drops one, and the collar prints with a bead-wide
    # ANNULAR VOID at mid-wall (measured on the x9 plate at r~9.8) — in the wall that carries
    # the hook's whole load. ODD is no better HERE: contours() recovers a dying strip's
    # centreline per-geom now, but the collar fuses with its drop bar, and the junction pocket
    # outlives the bead-wide strip — the strip dies inside a geom that survives, invisible to
    # the trigger (verified: the 3-bead collar still emitted 2 rings after the per-geom fix).
    # EVEN bead counts pair up from both edges and cover fully by construction. Solid and one
    # bead thinner beats nominal-thickness with a void through the middle.
    ring = max(1, round(ring / (2 * bead_w))) * 2 * bead_w
    outer = bore / 2.0 + ring
    parts = [Point(0.0, 0.0).buffer(outer, resolution=64)]

    # the drop: a straight bar down from the ring, offset to one side so the collar cants and
    # bites the pole when loaded -- the offset IS the retention
    dx = outer - r
    parts.append(LineString([(dx, 0.0), (dx, -drop)]).buffer(r, resolution=16))

    # hook curling forward off the bottom of the drop
    cx, cy = dx + hook_r, -drop
    # THE MOUTH FACES UP. Sweeping 180 -> 0 goes over the TOP and makes an n, whose mouth faces
    # down -- anything hung on it falls straight off. Sweeping 180 -> 370 goes UNDER, making a U
    # that a strap or a loop drops into and sits in the bottom of.
    arc = []
    for i in range(41):
        a = math.radians(180.0 + 190.0 * i / 40.0)
        arc.append((cx + hook_r * math.cos(a), cy + hook_r * math.sin(a)))
    parts.append(LineString(arc).buffer(r, resolution=16))
    if tip > 0:
        ax, ay = arc[-1]; bx, by = arc[-2]
        ddx, ddy = ax - bx, ay - by
        m = math.hypot(ddx, ddy) or 1.0
        parts.append(LineString([(ax, ay), (ax + ddx / m * tip, ay + ddy / m * tip)])
                     .buffer(r, resolution=16))

    body = unary_union(parts)
    return body.difference(Point(0.0, 0.0).buffer(bore / 2.0, resolution=64)), bore


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--style", choices=("j", "lip", "simple", "pole"), default="pole",
                    help="simple = flat bar + thread hole + short lip; j = eye-hung curl; lip = over a wall")
    ap.add_argument("--pole", type=float, default=32.0, help="pole style: pole diameter to ring")
    ap.add_argument("--ring", type=float, default=5.5, help="pole style: collar wall thickness")
    ap.add_argument("--drop", type=float, default=26.0, help="pole style: bar length below the ring")
    ap.add_argument("--width", type=float, default=9.0, help="simple style: bar width across the face")
    ap.add_argument("--lip", type=float, default=6.0, help="simple style: how far the lip turns up")
    ap.add_argument("--thread", type=float, default=3.0, help="simple style: thread hole diameter")
    ap.add_argument("--wall", type=float, default=25.0, help="lip style: wall thickness to grip")
    ap.add_argument("--grip", type=float, default=20.0, help="lip style: how far down the far side")
    ap.add_argument("--shank", type=float, default=45.0, help="straight length above the hook")
    ap.add_argument("--hook-r", type=float, default=13.0, help="hook inner curl radius")
    ap.add_argument("--thick", type=float, default=6.0, help="wall thickness of the stroke")
    ap.add_argument("--hole", type=float, default=5.0, help="hole diameter")
    ap.add_argument("--gap", type=float, default=95.0, help="hook mouth opening, degrees")
    ap.add_argument("--tip", type=float, default=6.0, help="straight run at the hook tip")
    ap.add_argument("--layers", type=int, default=4, help="'couple layers width'")
    ap.add_argument("--brim", type=int, default=0, help="brim loops; 0 = none (the default)")
    ap.add_argument("--n", type=int, default=1, help="how many hangers on the plate")
    ap.add_argument("--spacing", type=float, default=0.0, help="0 = auto from part width")
    ap.add_argument("--printer", default="k1c", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--bead-w", type=float, default=None)
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--flow", type=float, default=None)
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    a.material = machine.check_spool(a.printer, a.material or machine.LOADED[a.printer])
    a.flow = a.flow or machine.flow_cap(a.material, a.printer)
    # bead first, then the speed the bead allows -- 50 is the north star, a fat bead pulls it down
    a.bead_w = a.bead_w or machine.bead_for_flow(a.flow, a.layer_h)
    speed = machine.speed_for_flow(a.flow, a.bead_w, a.layer_h)
    temp = machine.temp_for(a.material)

    # THICKNESS SNAPS TO A WHOLE NUMBER OF BEADS. A non-integer wall leaves the inward and
    # outward contour families colliding in the middle, which over-fills the layer and ploughs
    # the part off the plate -- solid.py's own guard refuses it, and it refused 6.0mm here.
    # This is the same bead-multiple rule the thick-profile parts already follow.
    # THE RING WALL SNAPS TOO. Oleg: "why ring layers are not touching eeachother?" -- the ring
    # was 4.00mm against a 1.50mm bead = 2.67 passes, so two contours were laid and a 1mm void was
    # left between them. Same rule as the stroke thickness, which was already snapped; I applied it
    # to one dimension and not the other, which is why only the ring showed the gap.
    if a.style == "pole":
        _rb = max(2, round(a.ring / a.bead_w))
        if abs(_rb * a.bead_w - a.ring) > 1e-6:
            print(f"  ring wall {a.ring:g} -> {_rb*a.bead_w:.2f} mm ({_rb} x {a.bead_w:.2f} bead)")
            a.ring = _rb * a.bead_w
    n_beads = max(2, round(a.thick / a.bead_w))
    snapped = n_beads * a.bead_w
    if abs(snapped - a.thick) > 1e-6:
        print(f"  thickness {a.thick:g} -> {snapped:.2f} mm ({n_beads} x {a.bead_w:.2f} bead)")
        a.thick = snapped

    _bore = None
    if a.style == "pole":
        one, _bore = pole_region(a.pole, a.ring, a.drop, a.hook_r, a.thick, a.tip, a.bead_w)
    elif a.style == "simple":
        one = simple_region(a.shank, a.lip, a.thick, bore_for(a.thread, a.bead_w), a.width)
    elif a.style == "lip":
        one = lip_region(a.wall, a.grip, a.shank, a.hook_r, a.thick, bore_for(a.hole, a.bead_w) if a.hole else 0, a.tip)
    else:
        one = hook_region(a.shank, a.hook_r, a.thick, bore_for(a.hole, a.bead_w), a.gap, a.tip)
    minx, miny, maxx, maxy = one.bounds
    w = maxx - minx
    # GRID, NOT A ROW. A row of 6 x 40mm needs 240mm on a 220mm plate; the off-bed guard would
    # refuse it and a row is the wrong shape for a plate anyway.
    minx, miny, maxx, maxy = one.bounds
    h = maxy - miny
    pitch_x = a.spacing or (w + 8.0)
    pitch_y = h + 8.0
    _bx, _by = machine.BED[a.printer]
    cols = max(1, int((_bx - 20.0) // pitch_x))
    parts = []
    for i in range(a.n):
        parts.append(translate(one, (i % cols) * pitch_x, -(i // cols) * pitch_y))
    region = unary_union(parts)

    height = machine.PRESS_HARD + a.layer_h * (a.layers - 1)
    bx, by = machine.BED[a.printer]
    rminx, rminy, rmaxx, rmaxy = region.bounds
    if _bore is not None:
        _slip = _bore - machine.bore_model(a.pole)          # the slip term added on top of bulge comp
        print(f"  CLOSED ring for a {a.pole:.0f} mm pole -> modelled bore {_bore:.2f} mm "
              f"(+{2*machine.BORE_INSET_MM:.2f} bulge comp + {_slip:.2f} slip); printed bore ~"
              f"{_bore - 2*machine.BORE_INSET_MM:.2f} mm = a sliding fit")
    _mod = bore_for(a.thread if a.style == "simple" else a.hole, a.bead_w)
    _req = a.thread if a.style == "simple" else a.hole
    print(f"  hanger: {rmaxx-rminx:.0f} x {rmaxy-rminy:.0f} mm, {a.layers} layers = "
          f"{height:.2f} mm thick")
    print(f"  hole: {_req:.1f} mm wanted -> modelled {_mod:.2f} mm "
          f"(+{2*machine.BORE_INSET_MM:.2f} for bulge, measured twice)")
    print(f"  {a.bead_w:.2f}mm bead at {speed:.1f} mm/s -> {a.bead_w*a.layer_h*speed:.1f} mm3/s "
          f"on {a.material} ({a.printer})")

    g, st = S.emit(region, height, a.bead_w, a.layer_h, a.flow, temp,
                   machine.bed_for(a.material, a.printer), 1.75, (bx, by),
                   # LAYER 1 RUNS AT FULL FLOW, WITH A CRAZY-HIGH LINE WIDTH. Oleg has said this
                   # repeatedly and I kept "fixing" it back to a metered layer:
                   #   "first layer is 55 as well just line width is crazy high"
                   #   "you have to go 15mm wide in settings do not worry of massive over
                   #    extrusion, this is what we do"
                   # first_w is the SPREAD width the material lands at (mm2 / press), so layer 1
                   # carries the same mm2 per mm as the body. The overlap is deliberate: that is
                   # what welds the part to the plate.
                   True, machine.PRESS_HARD, 100, a.bead_w * a.layer_h / machine.PRESS_HARD,
                   # AUX (side/chassis) FANS AT THE PLA HOUSE NORM, 0.2. A positional True here set
                   # them to 100% (True == 1.0, the full aux fraction) and chilled the first layer
                   # on a material that must not be cooled hard. emit() runs this through aux_for(),
                   # which still forces full aux for materials that require it (e.g. TPU).
                   0.2, a.printer, f"HANGER x{a.n}", material=a.material,
                   # NO BRIM UNLESS ASKED. Oleg, 2026-07-27: "also dont print brim uinless asked".
                   # Layer 1 already over-extrudes into a 0.1mm gap and welds itself down; a brim
                   # on top of that is material to cut off, not adhesion.
                   brim=a.brim)
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"hanger{a.style}_{a.printer}_x{a.n}_h{a.hole:g}_T{temp:g}.gcode")
    open(fn, "w").write(g)
    print(f"{fn}")


if __name__ == "__main__":
    main()
