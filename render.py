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
import hashlib, re, sys, math, os


def read_path(path, body_only=False):
    """Parse a gcode file into drawable segments.

    NO PHANTOM FIRST SEGMENT. Position starts unknown, not at (0,0,0). Seeding it at the origin
    invented a segment from the plate corner to the first real move -- which then stretched the
    drawing's X range to 0..235 on a part that lives at 115..235, AND, because that phantom sat at
    Z=0.0, it became "layer 1" in the layer index, so `--layers=1` rendered exactly one bogus line
    instead of the first layer. A diagram that disagrees with the file is worse than no diagram.
    """
    segs = []                     # (x0,y0,z0, x1,y1,z1, extruding)
    x = y = z = None; e = 0.0
    in_body = not body_only
    for ln in open(path):
        if body_only and "BODY_START" in ln:
            in_body = True
            x = y = z = None
            e = 0.0
            continue
        if body_only and in_body and ln.split(';')[0].strip() == "M107":
            break
        if not in_body:
            continue
        t = ln.split(';')[0].strip()
        if not t.startswith(('G0', 'G1')):
            continue
        if t.startswith('G92'):
            continue
        mx = re.search(r'X([-\d.]+)', t); my = re.search(r'Y([-\d.]+)', t)
        mz = re.search(r'Z([-\d.]+)', t); me = re.search(r'E([-\d.]+)', t)
        nx = float(mx.group(1)) if mx else x
        ny = float(my.group(1)) if my else y
        nz = float(mz.group(1)) if mz else (z if z is not None else 0.0)
        ext = bool(me) and float(me.group(1)) > e + 1e-9
        if me: e = float(me.group(1))
        known = None not in (x, y, z)
        if known and (nx, ny, nz) != (x, y, z):
            segs.append((x, y, z, nx, ny, nz, ext))
        x, y, z = nx, ny, nz
    return segs


def svg(segs, out, w=1500, h=820, zmax_cut=None, layers=0, min_seg=0.0,
        source_name="", source_sha256=""):
    # AUTO height cut. A fixed 60mm silently truncated tall parts — the 180mm spiral tower rendered as
    # its bottom third and nobody could see the form. Cut just above the tallest EXTRUDING move (the
    # part), which drops only the non-extruding park lift, at any part height.
    if zmax_cut is None:
        _ext_tops = [max(s[2], s[5]) for s in segs if s[6]]
        zmax_cut = (max(_ext_tops) + 1.0) if _ext_tops else 60.0
    body = [s for s in segs if s[2] < zmax_cut and s[5] < zmax_cut]   # ignore the park lift

    # A DIAGRAM IS NOT A DUMP. A 15-part plate is 392k segments; drawn in full that is a 71MB SVG
    # no browser will open, so "publish as we go" quietly stops publishing. Every part in this
    # family has a CONSTANT cross-section, so the first N layers carry the whole shape and the rest
    # repeat it. That makes cutting layers honest here in a way it would not be for a varying part
    # — so the caller must ask, and the cut is stamped into the footer rather than dropped silently.
    cut = ""
    if layers:
        zs_all = sorted({round(s[2], 3) for s in body})
        keep = set(zs_all[:layers])
        n_before = len(body)
        body = [s for s in body if round(s[2], 3) in keep]
        cut = f" — first {layers} of {len(zs_all)} layers ({n_before} segs total)"
    if min_seg:
        body = [s for s in body
                if math.dist((s[0], s[1]), (s[3], s[4])) >= min_seg or s[2] != s[5]]
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
         f'viewBox="0 0 {w} {h}">']
    if source_sha256:
        L.append(f'<metadata data-source="{source_name}" '
                 f'data-source-sha256="{source_sha256}"/>')
    L.append('<rect width="100%" height="100%" fill="#08090b"/>')
    L.append(f'<text x="{pad}" y="26" fill="#7fe3d4" font-family="monospace" font-size="15">'
             f'PLAN — from above</text>')
    L.append(f'<text x="{w/2+pad}" y="26" fill="#7fe3d4" font-family="monospace" font-size="15">'
             f'FRONT — from the side</text>')
    # ONE <path> PER RUN, NOT ONE <line> PER SEGMENT.
    # Per-segment elements cost ~130 bytes of markup each, so a 13k-segment plate rendered to 2.4MB
    # — a file that is technically correct and practically unpublishable. Consecutive segments that
    # share a colour and a pen are one polyline, which is what they already are on the machine.
    def runs(project):
        out = []
        cur = None
        for s in body:
            ax, ay, az, bx, by, bz, ext = s
            c = col((az + bz) / 2)
            a2 = project(ax, ay, az)
            b2 = project(bx, by, bz)
            if cur and cur[0] == c and cur[1] == ext and \
                    abs(cur[2][-1][0] - a2[0]) < 0.05 and abs(cur[2][-1][1] - a2[1]) < 0.05:
                # DECIMATE IN PIXELS, DO NOT DROP SEGMENTS. Filtering short segments out of `body`
                # punches holes in the path, which SPLITS runs and makes the file bigger, not
                # smaller. Skipping a point inside a run keeps it one continuous polyline, and a
                # point under a pixel from its predecessor cannot be seen anyway.
                if math.dist(cur[2][-1], b2) < 0.9 and len(cur[2]) > 1:
                    cur[2][-1] = b2
                else:
                    cur[2].append(b2)
            else:
                cur = (c, ext, [a2, b2])
                out.append(cur)
        return out

    for project in (lambda ax, ay, az: (pad + (ax - x0) * sc, h - pad - (ay - y0) * sc),
                    lambda ax, ay, az: (w / 2 + pad + (ax - x0) * scf,
                                        h - pad - (az - z0) * scf)):
        for c, ext, pts in runs(project):
            d = '' if ext else ' stroke-dasharray="4,4"'
            pt = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
            L.append(f'<polyline points="{pt}" fill="none" stroke="{c}" '
                     f'stroke-width="{1.1 if ext else 0.7}"{d}/>')
    L.append(f'<text x="{pad}" y="{h-6}" fill="#5b6572" font-family="monospace" font-size="12">'
             f'{source_name or os.path.basename(sys.argv[1])} — {len(body)} segments, '
             f'X {x0:.0f}..{x1:.0f}  Y {y0:.0f}..{y1:.0f}  Z {z0:.2f}..{z1:.1f}{cut}</text>')
    L.append('</svg>')
    open(out, 'w').write('\n'.join(L))
    return dict(segs=len(body), x=(x0, x1), y=(y0, y1), z=(z0, z1))


if __name__ == "__main__":
    src = sys.argv[1]
    args = [a for a in sys.argv[2:] if not a.startswith('--')]
    out = args[0] if args else src.rsplit('.', 1)[0] + '.svg'
    layers = 0
    min_seg = 0.0
    body_only = False
    for a in sys.argv[2:]:
        if a.startswith('--layers='):
            layers = int(a.split('=', 1)[1])
        if a.startswith('--min-seg='):
            min_seg = float(a.split('=', 1)[1])
        if a == '--body-only':
            body_only = True
    source_sha256 = hashlib.sha256(open(src, 'rb').read()).hexdigest()
    st = svg(read_path(src, body_only=body_only), out, layers=layers, min_seg=min_seg,
             source_name=os.path.basename(src), source_sha256=source_sha256)
    print(f"{out}\n  {st['segs']} segments  X {st['x'][0]:.0f}..{st['x'][1]:.0f}  "
          f"Y {st['y'][0]:.0f}..{st['y'][1]:.0f}  Z {st['z'][0]:.2f}..{st['z'][1]:.1f}")
