#!/usr/bin/env python3
"""icecage_render.py -- top view of the ice cage, drawn FROM icecage.stl, never by hand.

House rule: a diagram is generated from the real artifact. Every curve below is the emitted
mesh's own bottom ring, read back out of the binary STL, plus the circle that ring unfolds into
once the contents expand. If the model changes, this picture changes with it or it is wrong.

    python3 icecage_render.py [icecage.stl] [-o icecage_profile.svg]
"""
import argparse
import math
import os
import struct

FG = "#111111"
ORANGE = "#ff7a18"
GREY = "#9a9a9a"


def ring_of(path):
    """The bottom ring (the wall's OUTER face at z=0), ordered by angle, out of the file."""
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        body = f.read()
    seen = {}
    for rec in struct.iter_unpack("<12fH", body):
        for x, y, z in (rec[3:6], rec[6:9], rec[9:12]):
            if abs(z) < 1e-9 and (abs(x) > 1e-9 or abs(y) > 1e-9):
                seen[(round(x, 6), round(y, 6))] = (x, y)
    return sorted(seen.values(), key=lambda p: math.atan2(p[1], p[0])), n


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("stl", nargs="?", default=os.path.join(here, "icecage.stl"))
    ap.add_argument("-o", "--out", default=os.path.join(here, "icecage_profile.svg"))
    ap.add_argument("--wall", type=float, default=0.8)
    a = ap.parse_args()

    pts, ntris = ring_of(a.stl)
    d = a.wall / 2.0
    perim = sum(math.hypot(pts[(i + 1) % len(pts)][0] - p[0],
                           pts[(i + 1) % len(pts)][1] - p[1]) for i, p in enumerate(pts))
    r_unfold = perim / (2.0 * math.pi) - d          # centreline, then in to the bore face
    rmax = max(math.hypot(x, y) for x, y in pts)
    pad = 18.0
    span = 2.0 * max(rmax, r_unfold + d) + 2 * pad
    sc = 900.0 / span
    cx = cy = 450.0

    def P(x, y):
        return "%.2f,%.2f" % (cx + x * sc, cy - y * sc)

    outer = " ".join(P(x, y) for x, y in pts)
    # Inner (bore) face: the same measured ring, offset inward by the full wall along its normal.
    inner = []
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        r = pts[i - 1]
        tx, ty = q[0] - r[0], q[1] - r[1]
        tl = math.hypot(tx, ty)
        inner.append(P(p[0] - a.wall * ty / tl, p[1] + a.wall * tx / tl))
    inner = " ".join(inner)

    svg = []
    svg.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 900" width="900" '
               'height="900" font-family="ui-sans-serif,system-ui,sans-serif">')
    svg.append('<rect width="900" height="900" fill="#ffffff"/>')
    svg.append('<circle cx="%.1f" cy="%.1f" r="%.2f" fill="none" stroke="%s" stroke-width="2" '
               'stroke-dasharray="7 6"/>' % (cx, cy, r_unfold * sc, GREY))
    svg.append('<polygon points="%s" fill="%s" fill-opacity="0.10" stroke="%s" '
               'stroke-width="2.2"/>' % (outer, ORANGE, ORANGE))
    svg.append('<polygon points="%s" fill="#ffffff" stroke="%s" stroke-width="1.4"/>'
               % (inner, ORANGE))
    svg.append('<text x="30" y="44" font-size="26" fill="%s">ice cage, top view, drawn from '
               '%s</text>' % (FG, os.path.basename(a.stl)))
    svg.append('<text x="30" y="76" font-size="18" fill="%s">solid line: the 0.8 mm wall as '
               'modelled, %d points off %d triangles</text>' % (FG, len(pts), ntris))
    svg.append('<text x="30" y="102" font-size="18" fill="%s">dashed circle: where that same '
               'wall length sits once the lobes unfold, bore R %.1f mm</text>' % (GREY, r_unfold))
    svg.append('<text x="30" y="870" font-size="18" fill="%s">the gap between the two is the '
               'expansion the part absorbs by BENDING, before any hoop tension starts</text>'
               % FG)
    svg.append('</svg>')
    with open(a.out, "w") as f:
        f.write("\n".join(svg))
    print("wrote %s  (ring %d pts, perimeter %.2f mm, unfolded bore R %.2f mm)"
          % (a.out, len(pts), perim, r_unfold))


if __name__ == "__main__":
    main()
