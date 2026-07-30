#!/usr/bin/env python3
"""ANTI-VIBRATION STAND — FEET: leveling cup + shim washers. Draft, structure-first.

WHAT THIS IS. The compliance layer under the stand (guides/printer-stand.md, "Floor isolation").
Two printed parts, chosen by --part:

  cup   A leveling FOOT CUP: a pressed solid disc with an upward collar the load spigot (column
        base, or the bottom-tray corner) drops into and is retained. It sits on the firm rubber/cork
        pad through a stack of shim washers. --collar-h 0 gives a flat puck (no register) for a
        tray corner; a nonzero collar registers a column base.

  shim  A leveling SHIM WASHER at --thickness (0.5 / 1 / 2 mm). Stack them under the cups and level
        each stand with a spirit level, then lay a straightedge across BOTH tops and shim until the
        two tabletops are flush and coplanar (both stands 600mm, side by side).

ISOLATION DOCTRINE (spec): the printer couples FIRMLY to the mass — no soft mat between printer and
slab. Compliance (firm rubber/cork/EVA, ~40-60 Shore A, NOT soft foam) goes under the WHOLE stand
only. Soft pads under a tall heavy top make a rocking mode that AMPLIFIES; firm pads isolate the
structure-borne path while keeping that mode stiff. These printed parts are the seat + leveler for
that firm pad — the pad itself is bought, not printed.

STRUCTURE vs PROVISIONAL. The cup/shim geometry is settled. The COLLAR FIT (--accept-dia) is
PROVISIONAL — coupon-calibrate against the real column/tray before the fleet. Shim thickness is
exact (the last layer is trimmed to hit --thickness).

Circle-based, pressed 0.1, single continuous stroke per layer — via stand_common."""
import argparse, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine
import stand_common as sc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", default="cup", choices=("cup", "shim"))
    ap.add_argument("--accept-dia", type=float, default=60.0,
                    help="cup: collar INNER diameter — the spigot that drops in (column OD 60, or "
                         "size a bottom-tray corner). PROVISIONAL fit; calibrate on a coupon.")
    ap.add_argument("--clearance", type=float, default=1.0, help="cup: radial slip clearance in the collar")
    ap.add_argument("--collar-h", type=float, default=15.0, help="cup: collar height (0 = flat puck)")
    ap.add_argument("--base-layers", type=int, default=5, help="cup: solid floor layers (~3mm at 0.6)")
    ap.add_argument("--thickness", type=float, default=1.0, help="shim: washer thickness in mm (0.5/1/2)")
    ap.add_argument("--dia", type=float, default=None,
                    help="shim: outer diameter (default = cup footprint so shims stack under it)")
    ap.add_argument("--id", type=float, default=40.0, help="shim: central hole diameter (a washer)")
    ap.add_argument("--layer-h", type=float, default=0.6)
    ap.add_argument("--printer", default="k2plus", choices=sorted(machine.BED))
    ap.add_argument("--material", default=None)
    ap.add_argument("--bed", type=float, default=0, help="bed target C; 0 = COLD (default, solar). Heat only on explicit request, e.g. 120")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    b = sc.Build(a.printer, a.material, a.layer_h, a.bed)
    cx, cy = b.cx, b.cy
    # cup footprint = collar centreline; the collar sits at the disc rim (simple cup, spigot drops in)
    r_out = a.accept_dia / 2.0 + a.clearance + b.bw / 2.0

    if a.part == "cup":
        if not b.fits(2 * r_out, 2 * r_out):
            sys.exit("cup does not fit the plate — smaller --accept-dia or a bigger printer")
        nb = a.base_layers if a.base_layers % 2 == 1 else a.base_layers + 1   # odd -> last ends at rim
        top = b.z2 + (nb - 2) * b.lh + a.collar_h                             # floor top + collar
        laps = int(a.collar_h / b.lh)
        b.preamble(f"STAND FOOT CUP Øfoot{2*r_out:.0f} accept{a.accept_dia:g} collar{a.collar_h:g}",
                   nb + laps, extra_stamps=sc.stamp_dependencies())
        # solid disc floor, alternating direction so no stacked radial welt; layer 1 pressed pitch
        b.begin_at(cx, cy, b.z1, tag="; PRIME-TRAVEL to foot centre")
        z = b.z1
        end_r = b.solid_annulus_layer(cx, cy, r_out, 0.0, z, b.land, outward=True)
        for i in range(1, nb):
            z = b.z1 + i * b.lh if i == 1 else z + b.lh
            b.relevel_z(z)
            end_r = b.solid_annulus_layer(cx, cy, r_out, 0.0, z, b.bw, outward=(end_r <= 1e-6))
        floor_top = z
        # upward collar at the disc rim — head is already at the rim after the last (outward) layer
        if a.collar_h > 1e-6:
            ring = b.circle_pts(cx, cy, r_out, seg=1.0)
            b.climb_loop(ring, floor_top, floor_top + a.collar_h)
        b.finish(top)
        kind = f"foot cup Øfoot{2*r_out:.0f} accept Ø{a.accept_dia:g} collar {a.collar_h:g}mm"
        fn = f"stand_foot_cup_{a.printer}_a{a.accept_dia:g}_c{a.collar_h:g}_T{b.temp:g}.gcode"
    else:
        dia = a.dia if a.dia else 2 * r_out
        r_o = dia / 2.0 - b.bw / 2.0
        r_i = a.id / 2.0
        if not b.fits(dia, dia):
            sys.exit("shim does not fit the plate")
        if r_i >= r_o - b.bw:
            sys.exit("--id too large for --dia (no washer land left)")
        # layer Z ladder: pressed 0.1, then lh steps, last layer trimmed to hit --thickness exactly
        zs = [b.z1]
        while zs[-1] < a.thickness - 1e-6:
            zs.append(min(a.thickness, round(zs[-1] + b.lh, 5)))
        b.preamble(f"STAND SHIM washer Ø{dia:g} id{a.id:g} t{a.thickness:g}", len(zs),
                   extra_stamps=sc.stamp_dependencies())
        b.begin_at(cx + r_o, cy, b.z1, tag="; PRIME-TRAVEL to shim rim")
        end_r = None
        for i, z in enumerate(zs):
            if i == 0:
                end_r = b.solid_annulus_layer(cx, cy, r_o, r_i, z, b.land, outward=False)
            else:
                b.relevel_z(z)
                end_r = b.solid_annulus_layer(cx, cy, r_o, r_i, z, b.bw,
                                              outward=(abs(end_r - r_i) < b.bw))
        b.finish(a.thickness)
        kind = f"shim washer Ø{dia:g} id{a.id:g} thickness {a.thickness:g}mm ({len(zs)} layers)"
        fn = f"stand_shim_{a.printer}_d{dia:g}_t{a.thickness:g}_T{b.temp:g}.gcode"

    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, fn)
    open(path, "w").write(b.text())
    print(f"  stand {kind}")
    print(f"  ~{b.grams():.0f} g, ~{b.minutes():.0f} min. 4 per stand (one under each corner).")
    print(path)


if __name__ == "__main__":
    main()
