#!/usr/bin/env python3
"""Render an emitted toolpath to SVG so it can be LOOKED AT before it is printed.

Oleg, 2026-07-25: "you need to turn on visualization of what you doing and imaging beautiful petals.
now you are in the are of single line mostly".

That is the correct criticism. Every geometry decision in this project so far was made by reasoning
about numbers — crossings, flow, segment lengths — and verified by measuring more numbers. Nothing
was ever looked at. A shape can satisfy every constraint and still be ugly, and "ugly" is not
visible in an audit.

Two views, side by side:
  · PLAN   — straight down. Shows the footprint and whether the piece has AREA or is a line.
  · FRONT  — from the side. Shows the arcs, the heights, and what actually flies.

Colour runs with Z: plate is dark, apex is bright. Non-extruding moves are drawn dashed, so a travel
that should not exist is visible rather than merely reported.

Usage: python3 render.py out/thing.gcode [out.svg]
"""
import re, sys, math, os


def read_path(path):
    segs = []                     # (x0,y0,z0, x1,y1,z1, extruding)
    x = y = z = 0.0; e = 0.0
    for ln in open(path):
        t = ln.split(';')[0].strip()
        if not t.startswith(('G0', 'G1')):
            continue
        if t.startswith('G92'):
            continue
        mx = re.search(r'X([-\d.]+)', t); my = re.search(r'Y([-\d.]+)', t)
        mz = re.search(r'Z([-\d.]+)', t); me = re.search(r'E([-\d.]+)', t)
        nx = float(mx.group(1)) if mx else x
        ny = float(my.group(1)) if my else y
        nz = float(mz.group(1)) if mz else z
        ext = bool(me) and float(me.group(1)) > e + 1e-9
        if me: e = float(me.group(1))
        if (nx, ny, nz) != (x, y, z):
            segs.append((x, y, z, nx, ny, nz, ext))
        x, y, z = nx, ny, nz
    return segs


def svg(segs, out, w=1500, h=820, zmax_cut=60.0):
    body = [s for s in segs if s[2] < zmax_cut and s[5] < zmax_cut]   # ignore the park lift
    if not body:
        body = segs
    xs = [s[0] for s in body] + [s[3] for s in body]
    ys = [s[1] for s in body] + [s[4] for s in body]
    zs = [s[2] for s in body] + [s[5] for s in body]
    x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys); z0, z1 = min(zs), max(zs)
    pad = 24
    pw = w / 2 - pad * 2
    sc = min(pw / max(x1 - x0, 1e-6), (h - pad * 3) / max(y1 - y0, 1e-6))
    scf = min(pw / max(x1 - x0, 1e-6), (h - pad * 3) / max(z1 - z0, 1e-6))

    def col(zz):
        t = (zz - z0) / max(z1 - z0, 1e-6)
        # dark teal at the plate -> bright ice at the apex
        r = int(20 + 200 * t ** 1.3); g = int(60 + 175 * t); b = int(70 + 165 * t)
        return f"rgb({r},{g},{b})"

    L = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
         f'viewBox="0 0 {w} {h}"><rect width="{w}" height="{h}" fill="#08090b"/>']
    L.append(f'<text x="{pad}" y="26" fill="#7fe3d4" font-family="monospace" font-size="15">'
             f'PLAN — from above</text>')
    L.append(f'<text x="{w/2+pad}" y="26" fill="#7fe3d4" font-family="monospace" font-size="15">'
             f'FRONT — from the side</text>')
    for (ax, ay, az, bx, by, bz, ext) in body:
        px0 = pad + (ax - x0) * sc; py0 = h - pad - (ay - y0) * sc
        px1 = pad + (bx - x0) * sc; py1 = h - pad - (by - y0) * sc
        d = '' if ext else ' stroke-dasharray="4,4"'
        L.append(f'<line x1="{px0:.1f}" y1="{py0:.1f}" x2="{px1:.1f}" y2="{py1:.1f}" '
                 f'stroke="{col((az+bz)/2)}" stroke-width="{1.1 if ext else 0.7}"{d}/>')
        qx0 = w/2 + pad + (ax - x0) * scf; qy0 = h - pad - (az - z0) * scf
        qx1 = w/2 + pad + (bx - x0) * scf; qy1 = h - pad - (bz - z0) * scf
        L.append(f'<line x1="{qx0:.1f}" y1="{qy0:.1f}" x2="{qx1:.1f}" y2="{qy1:.1f}" '
                 f'stroke="{col((az+bz)/2)}" stroke-width="{1.1 if ext else 0.7}"{d}/>')
    L.append(f'<text x="{pad}" y="{h-6}" fill="#5b6572" font-family="monospace" font-size="12">'
             f'{os.path.basename(sys.argv[1])} — {len(body)} segments, '
             f'X {x0:.0f}..{x1:.0f}  Y {y0:.0f}..{y1:.0f}  Z {z0:.2f}..{z1:.1f}</text>')
    L.append('</svg>')
    open(out, 'w').write('\n'.join(L))
    return dict(segs=len(body), x=(x0, x1), y=(y0, y1), z=(z0, z1))


if __name__ == "__main__":
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else src.rsplit('.', 1)[0] + '.svg'
    st = svg(read_path(src), out)
    print(f"{out}\n  {st['segs']} segments  X {st['x'][0]:.0f}..{st['x'][1]:.0f}  "
          f"Y {st['y'][0]:.0f}..{st['y'][1]:.0f}  Z {st['z'][0]:.2f}..{st['z'][1]:.1f}")
