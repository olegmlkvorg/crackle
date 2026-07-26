# crackle — objects made of toolpath, not of shape

Python emits gcode **directly**. No CAD, no mesh, no STL, no slicer.

A slicer's job is to take a shape and hide the machine. This does the opposite: the path *is* the
design, so it can make things a slicer structurally cannot — a 4.57 m belt folded onto a 350 mm
plate as one closed curve, a lattice drawn in a single unbroken stroke, a pulley whose spokes are
simply the route taken between two circles.

Everything here is measured on real printers (Creality K2 Plus and K1C). Numbers that turned out to
be wrong are kept visible in `machine.VOID_MEASUREMENTS`, with the reason each died, rather than
quietly deleted.

## Start here

```bash
pip install shapely                                          # the only dependency

python3 solid.py --part coupler --stick 6.35 --height 14     # emit a real part
python3 validate.py out/coupler_*.gcode                      # ALWAYS — see below
python3 render.py  out/coupler_*.gcode view.svg              # look at it before printing
```

Then send it to a Klipper/Moonraker printer over HTTP:

```bash
python3 push.py --printer k1c out/coupler_k1c_*.gcode
```

**Never skip `validate.py`.** It is not a linter — it is what stands between a generator bug and a
wrecked plate, and it earns that regularly. It has caught a move commanding 539 mm³/s, a file
stamped for the wrong machine that would have printed off the bed, travels sweeping the nozzle
through the part at layer height, and fifteen parts scheduled onto the same spot. Every one of those
was individually valid gcode; each was wrong only in relation to something else.

## What each file makes

| | |
|---|---|
| `solid.py` | solid mechanical parts — brackets, couplers, feet, spacers — as concentric contours. Multi-part plates (`--parts "coupler*3,bracket*2"`), printed part-by-part, sand-fillable cavities (`--cavity`) |
| `hilbert.py` | Moore curve (closed Hilbert) lattices — area fill as one closed loop, no seam, no travel |
| `belt.py` | a cleated closed-loop belt, printed flat, folded onto the plate by the same curve trick |
| `pulley.py` | crowned pulley as one path: rim → spiral spoke inward → bore → spiral back out |
| `nucleon.py` | the flat-atom drawing, where the strands dragged *between* pillars are the product |
| `waves.py` | rippled ribbons, meant to be shaped by hand while still warm |
| `flowtest.py` | maximum volumetric flow: one layer, a spiral, flow ramping outward |
| `machine.py` | every measured constant, in one place. Nothing hardcodes these separately |
| `validate.py` | the pre-print guards described above |
| `render.py` | SVG of the real emitted path — plan and front elevation |
| `push.py` | upload and start over Moonraker, refusing files stamped for another machine |

## The rules the code enforces

Not style preferences. Each was bought with a failed print.

- **Measure the emitted artifact, never the summary line.** Computed values disagreed with the
  emitted file four times out of four. A generator reporting what it *intended* reports nothing.
- **One continuous extrusion inside a part.** Travel is allowed only *between* separate objects, and
  only after lifting clear of everything already standing.
- **Bead first, then speed.** Deposition comes from a big bead moving slowly, not from whipping the
  head around. The bead is capped at what a nozzle can physically stack: 1.5× nozzle wide,
  0.75× tall. Wider than that and it lands *taller* than the Z step, and the part climbs into the
  nozzle.
- **Fail rather than emit.** An unchecked input is not a clean one. The generators refuse to write a
  file whose contours would over-deposit, whose parts would overlap, or whose brims would fuse
  together.

## Adapting it to your machine

Edit `machine.py` — it is the single source of truth. `BED` is the **printable plate**, not the
kinematic reach; they differ, and using the larger number prints off the edge. Set `MAX_SPEED` to
what your *parts* survive rather than what your motors can do: it deliberately overrides the flow
target, and `speed_for()` says so out loud when it does, because a cap that silently rewrites your
input is indistinguishable from a bug.

Then run `flowtest.py` and find your own maximum flow before trusting any number in here.

## Licence

Take it. No attribution required, no permission needed, nothing owed.
Why it is given away: <https://worldview.senku.im>
