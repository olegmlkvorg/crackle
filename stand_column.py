#!/usr/bin/env python3
"""ANTI-VIBRATION STAND — LEG COLUMN (gypsum-filled printed tube). Draft, structure-first.

WHAT THIS IS. One stackable Ø60 single-bead tube segment — the leg. Two segments (~232.5mm each)
stack to the 465mm clear column height that makes a 600mm stand with the two slabs. The tube is
OPEN AT BOTH ENDS on purpose: a 610mm bamboo spine threads down the centre and a sand+gypsum pour
fills it continuously into the bottom tray below and the top slab above, so the whole stand casts
into one bamboo-reinforced monolith (guides/printer-stand.md, "Legs and frame").

WHY A FILLED TUBE, NOT A BAMBOO LEG. A bare 6.35mm bamboo rod buckles at ~33N against the ~98N each
corner carries; a Ø60 filled PLA tube gives P_cr ~11,000N (margin ~110x) and ~380x the lateral
stiffness. The bamboo does what it is good at — spine (anti-shear), diagonal bracing, slab rebar —
never a slender column in compression. See the spec's buckling arithmetic.

STRUCTURE vs PROVISIONAL. The tube diameter (buckling), height (600mm math) and the external brace
flat are structural and settled. The SINGLE-BEAD wall is PROVISIONAL: if the knock-test tile bursts
its wall under wet fill, bump --wall-beads (a thicker hoop) or add a liner — a parameter, not a
rewrite. Spine centring is deferred to the cap (top) and a bottom-tray nib, so the tube stays a
plain continuous loop per layer (single-stroke rule); it is NOT modelled here.

BRACE MOUNT. Oleg's design (QUESTIONS Q-STAND): bamboo is VISIBLE glued diagonal bracing. --brace-
faces flats the tube on the outward faces to give the diagonal a flat glue+lash land (a concave
cradle cannot be single-bead). A corner column takes 2 flats (the two faces it shares); an
edge/test cylinder takes 0.

Prints on either machine. pressed 0.1, 50 mm/s, single-bead — the house doctrine, via stand_common."""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import stand_common as sc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia", type=float, default=60.0, help="tube OUTER diameter (Ø60 per buckling math)")
    ap.add_argument("--height", type=float, default=232.5,
                    help="segment height; 2 x 232.5 = 465mm clear column (600 stand with slabs)")
    ap.add_argument("--wall-mm", type=float, default=None,
                    help="wall (hoop) thickness in mm = the bead width. Default = the flow-derived "
                         "single bead. PROVISIONAL: widen this (e.g. 4) ONLY if the knock-test tile "
                         "bursts a single-bead wall under wet fill — a wider bead crawls slower to "
                         "hold flow at the cap, staying one continuous stroke (a second concentric "
                         "loop would print in the first's shadow and fail the dive guard).")
    ap.add_argument("--brace-faces", type=int, default=2, choices=range(0, 5),
                    help="number of external flat glue-lands for the diagonal bamboo (corner col=2, "
                         "test cylinder=0)")
    ap.add_argument("--brace-angle", type=float, default=0.0,
                    help="direction (deg) of the first brace flat; the rest are +90 apart")
    ap.add_argument("--brace-flat", type=float, default=24.0,
                    help="perpendicular distance centre->flat (< dia/2); smaller = wider glue land")
    ap.add_argument("--brim", type=int, default=0,
                    help="sacrificial pressed skirt rings around the base for print stability "
                         "(0 = none; the pressed flange alone usually holds a vase tube)")
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--bed", type=float, default=60, help="bed target C; 0 = COLD (default, solar). Heat only on explicit request, e.g. 120")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    b = sc.Build(a.printer, a.material, a.layer_h, a.bed, bead=a.wall_mm)
    r_out = a.dia / 2.0 - b.bw / 2.0                 # wall CENTRELINE radius so OD == --dia
    if not b.fits(a.dia + 2 * a.brim * b.bw, a.dia + 2 * a.brim * b.bw):
        sys.exit(f"column Ø{a.dia:g} (+brim) does not fit the {a.printer} plate — smaller dia or printer")
    if a.height > machine.BED.get(a.printer, (350, 350, 350))[0] and a.printer:  # height uses Z, checked below
        pass
    zmax = {"k2plus": 350.0, "k1c": 250.0, "f022": 250.0}.get(a.printer, 250.0)
    if a.height > zmax - 5:
        sys.exit(f"segment height {a.height:g} exceeds the {a.printer} Z build ({zmax:g}) — split "
                 f"into more/shorter segments (they stack on the spine).")

    chords = tuple((math.radians(a.brace_angle + 90 * k), a.brace_flat) for k in range(a.brace_faces))
    if a.brace_faces and a.brace_flat >= r_out:
        sys.exit(f"--brace-flat {a.brace_flat:g} must be < wall radius {r_out:.1f}")

    cx, cy = b.cx, b.cy
    laps = int(round((a.height - b.z2) / b.lh))
    b.preamble(f"STAND COLUMN Ø{a.dia:g} h{a.height:g} ({a.brace_faces}-flat, {b.bw:.1f}mm wall)",
               laps + 2, extra_stamps=sc.stamp_dependencies())

    seg = 1.0
    ring0 = b.circle_pts(cx, cy, r_out, seg=seg, chords=chords)

    # --- base flange: two flat laps of the wall ring. Layer 1 is pressed to 0.1, so the single
    #     ring lands ~land mm wide (bead*lh/0.1) — that wide flange IS the adhesion for the tower. ---
    b.begin_at(ring0[0][0], ring0[0][1], b.z1, tag="; PRIME-TRAVEL to column base")
    if a.brim:
        # sacrificial skirt OUTSIDE the wall, layer-1 only; spirals inward into the wall ring
        r = r_out + a.brim * b.bw
        while r > r_out + 1e-6:
            b.loop(b.circle_pts(cx, cy, r, seg=seg, chords=chords), b.z1)
            r -= b.bw
    b.loop(ring0, b.z1)
    b.relevel_z(b.z2)
    b.loop(ring0, b.z2)

    # --- WALL: one continuous bead (thickness = --wall-mm) spiralling up to the segment height.
    #     Open both ends: the flange ended on this ring at z2, so it climbs straight on, no travel. ---
    b.climb_loop(ring0, b.z2, a.height)

    b.finish(a.height)

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"stand_column_{a.printer}_d{a.dia:g}_h{a.height:g}_T{b.temp:g}.gcode")
    machine.emit_gcode(fn, b.text())

    fill_ml = math.pi * (a.dia / 2.0 - b.bw) ** 2 * a.height / 1000.0
    kg = fill_ml * 1.9 / 1000.0
    print(f"  stand column Ø{a.dia:g} h{a.height:g}: {b.bw:.1f}mm open tube wall @ {b.speed:.0f}mm/s, "
          f"{a.brace_faces} brace flat(s), {laps}-lap wall")
    print(f"  ~{b.grams():.0f} g shell, ~{b.minutes():.0f} min; holds ~{fill_ml:.0f} mL gypsum "
          f"(~{kg:.1f} kg) per segment")
    print(f"  2 segments = one {2*a.height:g}mm column; 4 columns/stand ~{8*kg:.1f} kg fill")
    print(fn)


if __name__ == "__main__":
    main()
