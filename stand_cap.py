#!/usr/bin/env python3
"""ANTI-VIBRATION STAND — COLUMN CAP / TOP-FRAME SADDLE. Draft, structure-first.

WHAT THIS IS. A square open-frame saddle that caps each leg column at the top, tying the top-slab
tiles to the columns (guides/printer-stand.md). It does four jobs and only these:
  1. BEARS on the column top rim — the load path from the slab into the column.
  2. Passes the 610mm bamboo SPINE and lets the sand+gypsum POUR run continuously column->slab
     through a large central bore, so the stand casts into one monolith (spec: "cast into both").
  3. SEATS the two bamboo edge rails: they lie in the outer tray, in the L where the wall meets the
     floor band — the tray corner IS the seat (a separate cradle would be a second island and break
     the single-continuous-stroke rule; the pour locks the rails as edge rebar).
  4. Carries the printer-LOCATING LIP: --lip raises the outer wall proud of the slab so the printer
     cannot walk off. (The lip may instead live on the top-slab tile's outer wall — see
     stand_tile.py --lip; use whichever the assembly prefers. Marked provisional in QUESTIONS.)

The four trays lap onto the saddles and one continuous pour bonds everything; the PLA is permanent
skin, the set gypsum + bamboo is the structure (the cup-failure doctrine).

STRUCTURE vs PROVISIONAL. Footprint, bore and the fused haunch are structural. The FIT of the
central bore to the column and the wall/lip mechanics are PROVISIONAL — coupon-calibrate the bore
before the fleet (a printed hole comes out ~6mm under-diameter; here the bore is defined by a wall,
which prints closer, but confirm). Single-bead wall is provisional per the knock-test tile.

Reuses stand_tile's proven pressed-floor + fused-haunch + single-bead-wall via stand_common."""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import stand_common as sc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size", type=float, default=120.0, help="saddle outer edge (square); K2=120, K1C=90")
    ap.add_argument("--bore", type=float, default=56.0,
                    help="central square opening side = column BORE (default Ø56 tube ID), so the "
                         "pour runs through and the spine passes. Keep >= column ID.")
    ap.add_argument("--wall-h", type=float, default=20.0,
                    help="outer tray wall height (seats the Ø6.35 edge rails + laps the slab tiles)")
    ap.add_argument("--lip", type=float, default=0.0,
                    help="extra mm the outer wall stands PROUD above the tray as a printer-locating "
                         "lip (0 = none; the lip can instead live on the top-slab tile outer wall)")
    ap.add_argument("--fillet", type=float, default=8.0, help="height of the FUSED floor->wall haunch")
    ap.add_argument("--wall-beads", type=int, default=3, help="haunch base width in beads, tapering to 1")
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--bed", type=float, default=60, help="bed target C; 0 = COLD (default, solar). Heat only on explicit request, e.g. 120")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    b = sc.Build(a.printer, a.material, a.layer_h, a.bed)
    if not b.fits(a.size, a.size):
        sys.exit(f"cap {a.size:g} does not fit the {a.printer} plate — smaller --size or a bigger printer")
    if a.bore >= a.size - 8:
        sys.exit(f"--bore {a.bore:g} leaves no bearing band inside --size {a.size:g}")

    cx, cy = b.cx, b.cy
    hx = hy = a.size / 2.0 - b.bw / 2.0          # wall centreline half-extent
    rb = a.bore / 2.0                            # central opening half-side
    top = b.z2 + a.wall_h + a.lip
    fillet = max(0.0, min(a.fillet, a.wall_h - b.lh))
    jlayers = int(round(fillet / b.lh))
    laps_wall = int((a.wall_h + a.lip - fillet) / b.lh)
    b.preamble(f"STAND CAP {a.size:g} bore{a.bore:g} wall{a.wall_h:g}+lip{a.lip:g}",
               laps_wall + jlayers + 2, extra_stamps=sc.stamp_dependencies(), corner=True)

    # --- FLOOR band, layer 1 (pressed 0.1): rect rings from the OUTER wall INWARD to the bore,
    #     stopping at the opening so the column bore stays clear. Pressed beads land ~land mm wide
    #     and tile into a solid welded rim (the wide-line press, R4b-exempt via PRESSED_LAYER1).
    #     Every square corner is slowed to corner speed (loop_cornered) — the tile's inner square
    #     peeled on hard turns at 50; the cap band has the same 90deg corners. ---
    ring0 = b.rect_pts(cx, cy, hx, hy)
    b.begin_at(ring0[0][0], ring0[0][1], b.z1, tag="; PRIME-TRAVEL to cap band")
    ix = hx
    while ix > rb + b.land * 0.5:
        b.loop_cornered(b.rect_corners(cx, cy, ix, ix), b.z1)
        ix = max(rb, ix - b.land)
    b.loop_cornered(b.rect_corners(cx, cy, rb, rb), b.z1)   # innermost pressed ring at the bore edge

    # --- FLOOR band, layer 2 (normal bead): rings OUTWARD from the bore to the outer wall ---
    b.relevel_z(b.z2)
    ix = rb
    while ix < hx:
        b.loop_cornered(b.rect_corners(cx, cy, ix, ix), b.z2)
        ix = min(hx, ix + b.bw)
    b.loop_cornered(b.rect_corners(cx, cy, hx, hy), b.z2)   # end on the outer wall line

    # --- FUSED CORNER haunch: the outer wall welds face-to-face into the band over `fillet` mm,
    #     tapering wall_beads -> 1, so the fill push cannot peel the wall off the rim (cup failure). ---
    b.w("; bead 2.00x wall")
    nbase = max(1, a.wall_beads)
    for j in range(1, jlayers + 1):
        zf = b.z2 + j * b.lh
        frac = (j * b.lh) / fillet if fillet > 1e-9 else 1.0
        k = max(1, int(round(nbase - (nbase - 1) * frac)))
        for bd in range(k - 1, -1, -1):
            b.loop_cornered(b.rect_corners(cx, cy, hx - bd * b.bw, hy - bd * b.bw), zf)

    # --- OUTER WALL: single-bead rectangle spiral up to wall_h (+ lip), one continuous stroke ---
    b.climb_loop(ring0, b.z2 + fillet, top)

    b.finish(top)
    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"stand_cap_{a.printer}_{a.size:g}_bore{a.bore:g}_T{b.temp:g}.gcode")
    open(fn, "w").write(b.text())
    print(f"  stand cap {a.size:g} sq, bore {a.bore:g}, wall {a.wall_h:g}mm + {a.lip:g}mm lip, "
          f"{fillet:g}mm fused {nbase}->1 haunch")
    print(f"  ~{b.grams():.0f} g, ~{b.minutes():.0f} min; bears on the column rim, spine + pour pass "
          f"the bore, edge rails seat in the tray. 4 caps + 4 feet per stand.")
    print(fn)


if __name__ == "__main__":
    main()
