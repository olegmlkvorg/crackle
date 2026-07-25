# Rain generator — TPU printed surfaces that shed water in a regular droplet array

**Oleg, 2026-07-25**, with a photo of a wet dish: water beading into a regular dotted pattern across
a textured surface. *"explore the rain generators using 3d printing TPU — this is just normal hermet
in 4 layers."*

## The observation
A plain hermetic (sealed) print, 4 layers, already organises water into an even array of droplets.
The print's own line texture is acting as a nucleation grid: each bead sits where the surface tells
it to, at a spacing the toolpath set.

## Why it is interesting
Droplet size and spacing would be **designed, not incidental** — the same move that made
crossings-per-layer a dial makes droplet pitch a dial. Line spacing, bead width and layer count are
already parameters we control to a hundredth of a millimetre. Nothing here needs new machinery: the
spiral generator with `--spacing` already sweeps exactly the variable that should matter.

## Why TPU specifically
- flexible, so a panel can flex to release droplets on a cycle rather than needing a pump
- different surface energy from PLA — changes the contact angle, so beads sit taller and detach
  sooner at a given size
- survives repeated wetting and flexing without embrittling

## What it could be
- **rain sound**: a panel that drips at a controlled rate onto a resonant surface — sits directly
  in ORBÉ's ASMR territory alongside the Hilbert tray
- **rain curtain / water feature** with a uniform drip line rather than a random dribble
- **condensation harvesting** (fog nets are exactly this problem: droplet coalescence and release)
- purely visual: an even grid of beads on a clear panel

## First experiments (each is a spiral sweep we can already emit)
1. `flowtest.py --spacing X` over 0.6 / 0.9 / 1.2 / 1.8 mm at 4 layers in TPU — does droplet pitch
   track line spacing? That is the whole hypothesis, and one plate answers it.
2. Layer count 2 / 4 / 8 at the best spacing — does depth matter, or only the top surface?
3. Concentric spiral vs straight rows vs the nucleon ellipses — does path DIRECTION organise the
   droplets, or only spacing?
4. Tilt angle at which droplets release — the number that turns it into a rain generator rather
   than a wet plate.

## Note on TPU
TPU needs its own flow measurement before any of this — `machine.FLOW` is a PLA number.
Existing TPU knowledge in the project: clogging is an S-shape path problem, retraction settings were
worked out separately, filament has been dried 48h+.
