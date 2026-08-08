#!/usr/bin/env python3
"""render_weld — draw ONE gap between two posts, top view, from the EMITTED gcode, so a reader can
SEE what qa_weld measured. Oleg 2026-08-08: "the net and the outer wall line do not have sufficient
connection points".

It is the same instrument as the gate: geometry, floor layers, bead widths and WALL/RIM/RASTER/FILL
classes all come from qa_weld itself, so a figure that disagreed with the verdict could not be
drawn. Every stroke is one extruded move at the width the file's own E delta pays for
(dE * A_FIL / length / layer gap), round-capped -- literally the capsule qa_weld welds with. The
stitch is drawn twice: once as the material it lays, and once as a hairline centreline over it,
because at a 0.66mm pitch under a 0.82mm bead the strokes MERGE, and a solid orange bar is the
truth about the material while the hairline is the truth about the path.

TWO PANELS, ONE WINDOW. Both files are drawn in the same frame at the same scale: rotated so the
gap's own radial points up, so the border runs left to right across the picture. The window is
DERIVED from the geometry (both post centres + their walls, and NET_DEPTH of net below its own
edge), not typed, so it cannot go stale when the part changes.

IT REFUSES RATHER THAN FLATTERS. Before writing anything it re-measures, in frame, all three claims
the picture is making, and refuses to draw if any is not true of the files:
  the BEFORE file has NO floor bead welded to the border anywhere in this frame,
  the AFTER file welds MORE of that border than the BEFORE file does, and
  the AFTER file's stitch crosses the border at --expect-pitch (default 0.66mm, +-10%).
None of the three is a flag you can turn off, because a figure that needs one off is a lie.

Usage: python3 tools/render_weld.py --before A.gcode --after B.gcode --out fig.svg
Exit: 0 drawn, 1 the artifact disagrees with what the figure would claim, 2 cannot measure.
"""
import argparse, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import qa_weld

FLOOR_LAYER = 1          # index into the floor latch layers: layer 2, the first one above the plate
NET_DEPTH = 5.0          # mm of net drawn below its own edge, so it reads as a net and not a line
PAD, LBL, GAPY, FOOT, LOC_R = 2.0, 4.4, 3.4, 4.6, 5.5
COL = {'WALL': 'var(--ink)', 'RIM': 'var(--ink)',
       'RASTER': 'var(--dim)', 'FILL': 'var(--accent)'}


def load(path):
    """(geometry, classified segments of the floor layer) -- all of it qa_weld's own reading."""
    cmd = qa_weld.parse_cmd(path)
    if not cmd:
        sys.exit(f"DECLINE: no '; CMD=' stamp in {path}; the geometry cannot be re-derived.")
    stag = None
    for ln in open(path):
        stag = stag or re.search(r'rotated ([\d.]+) deg', ln)
        if 'BODY_START' in ln:
            break
    if not stag:
        sys.exit(f"DECLINE: no stagger stamp in {path}; the border cannot be placed.")
    g = qa_weld.geometry(cmd, float(stag.group(1)))
    layers = qa_weld.floor_layers(path, g)
    if len(layers) <= FLOOR_LAYER:
        sys.exit(f"DECLINE: {path} has {len(layers)} floor layer(s); wanted index {FLOOR_LAYER}.")
    lab, z, gap, raw = layers[FLOOR_LAYER]
    return g, qa_weld.classify(raw, g), lab, z


def frame(g, k):
    """Look at the gap between posts k and k+1: rotate so its radial is up, tangential across."""
    th = (g['phis'][k] + g['phis'][k + 1]) / 2.0
    s, c = math.sin(th), math.cos(th)
    return th, lambda p: (-(p[0] - g['cx']) * s + (p[1] - g['cy']) * c,
                          (p[0] - g['cx']) * c + (p[1] - g['cy']) * s)


def window(g, k, uv):
    """The frame, DERIVED: both post centres and their full walls across, the net's own edge down."""
    tan_half = abs(uv(g['cs'][k])[0]) + g['r_t'] + 2.0 * g['bw']
    rad_hi = max(uv(g['cs'][j])[1] for j in (k, k + 1)) + g['r_t'] + 1.5 * g['bw']
    return tan_half, g['r_h'] - NET_DEPTH, rad_hi


def in_win(a, b, tan_half, lo, hi, m=0.0):
    return (min(a[0], b[0]) < tan_half + m and max(a[0], b[0]) > -tan_half - m
            and max(a[1], b[1]) > lo - m and min(a[1], b[1]) < hi + m)


def clip(segs, uv, tan_half, lo, hi, m=1.0):
    return [(uv(p), uv(q), w, i, cls) for (p, q, w, i, cls) in segs
            if in_win(uv(p), uv(q), tan_half, lo, hi, m)]


def chain(segs):
    """Consecutive same-class moves that share an endpoint become one polyline: the emitted path,
    drawn as the head actually walked it, and a fraction of the bytes of one <line> per move."""
    out = []
    for s in sorted(segs, key=lambda s: s[3]):
        if out and out[-1][0] == s[4] and out[-1][1][-1] == s[0] and abs(out[-1][2] - s[2]) < .02:
            out[-1][1].append(s[1])
        else:
            out.append([s[4], [s[0], s[1]], s[2]])
    return out


def border_held(g, segs, uv, tan_half, lo, hi):
    """qa_weld's own ATTACH walk, restricted to this frame: (held steps, total steps). The grid is
    built 3mm wider than the picture so a border step is never called unheld by a cropped bead."""
    bead = sorted(s[2] for s in segs)[len(segs) // 2]
    grid, cell = qa_weld.hash_segs([s for s in segs
                                    if in_win(uv(s[0]), uv(s[1]), tan_half, lo, hi, 3.0)])
    held = tot = 0
    for bp in qa_weld.border_path(g):
        u = uv(bp)
        if not (abs(u[0]) <= tan_half and lo <= u[1] <= hi):
            continue
        tot += 1
        for o in qa_weld.near(grid, cell, bp, bp, bead):
            if o[4] in ('FILL', 'RASTER') and \
                    qa_weld.seg_dist(bp, bp, o[0], o[1]) <= (bead + o[2]) / 2.0 - qa_weld.MARGIN:
                held += 1
                break
    return held, tot


def stitch_pitch(g, segs, uv, tan_half, lo, hi):
    """Median spacing of the stitch where it crosses the border's own radius -- measured off the
    path, not read off a flag: every FILL crossing of r_poly minus one bead, sorted along the
    border."""
    R = g['r_poly'] - g['bw']
    xs = []
    for (p, q, w, i, cls) in segs:
        if cls != 'FILL':
            continue
        a, b = uv(p), uv(q)
        if not in_win(a, b, tan_half, lo, hi):
            continue
        r0 = math.hypot(p[0] - g['cx'], p[1] - g['cy'])
        r1 = math.hypot(q[0] - g['cx'], q[1] - g['cy'])
        if (r0 - R) * (r1 - R) < 0:
            xs.append(a[0] + (b[0] - a[0]) * (R - r0) / (r1 - r0))
    xs.sort()
    d = sorted(xs[i + 1] - xs[i] for i in range(len(xs) - 1))
    return (d[len(d) // 2] if d else None), len(xs)


def bare_gap(cs, lo, hi, at=0.0, step=0.02):
    """The longest run of BARE PLATE straight up the middle of the gap, sampled against the beads
    themselves, so it is the material's own answer rather than a subtraction of two radii.
    CALLED FROM THE NET'S OWN EDGE UP, never from the disc centre: below that edge the longest bare
    run is a hole in the 4mm lattice, which is the design rather than the defect, and a probe that
    could return one would not be measuring the thing its label names.
    Returns (length_mm, midpoint_radial)."""
    n = int((hi - lo) / step)
    cov = [False] * (n + 1)
    for (a, b, w, i, cls) in cs:
        if min(a[0], b[0]) - w > at or max(a[0], b[0]) + w < at:
            continue
        for j in range(n + 1):
            if not cov[j] and qa_weld.seg_dist((at, lo + j * step), (at, lo + j * step), a, b) \
                    <= w / 2.0:
                cov[j] = True
    best = run = 0
    end = 0
    for j in range(n + 1):
        run = 0 if cov[j] else run + 1
        if run > best:
            best, end = run, j
    return best * step, lo + (end - best / 2.0) * step


def panel(cs, tan_half, lo, hi, x0, y0):
    """One top view, mm for mm: stroke width IS the measured bead, round caps ARE the capsule."""
    o = [f'<g transform="translate({x0 + tan_half:.3f},{y0 + hi - lo:.3f}) scale(1,-1)">']
    for cls in ('RASTER', 'WALL', 'RIM', 'FILL'):        # stitch drawn last, over what it laps
        for c, pts, w in chain([s for s in cs if s[4] == cls]):
            d = ' '.join(f'{p[0]:.2f},{p[1] - lo:.2f}' for p in pts)
            o.append(f'<polyline points="{d}" fill="none" stroke="{COL[c]}" '
                     f'stroke-width="{w:.2f}" stroke-linecap="round" stroke-linejoin="round"/>')
    for c, pts, w in chain([s for s in cs if s[4] == 'FILL']):
        d = ' '.join(f'{p[0]:.2f},{p[1] - lo:.2f}' for p in pts)
        o.append(f'<polyline points="{d}" fill="none" stroke="var(--bg)" stroke-width="0.09" '
                 f'stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>')
    o.append('</g>')
    return '\n'.join(o)


def locator(g, th_c, k, cx, cy):
    """Where on the floor you are standing: the whole disc, its posts, and the drawn gap lit."""
    o, a = [], lambda j: g['phis'][j] - th_c + math.pi / 2
    pt = lambda ang, r: (cx + r * math.cos(ang), cy - r * math.sin(ang))
    o.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{LOC_R:.2f}" fill="none" '
             f'stroke="var(--faint)" stroke-width="0.25"/>')
    p0, p1 = pt(a(k), LOC_R), pt(a(k + 1), LOC_R)
    o.append(f'<path d="M{p0[0]:.2f},{p0[1]:.2f} A{LOC_R:.2f},{LOC_R:.2f} 0 0 1 '
             f'{p1[0]:.2f},{p1[1]:.2f}" fill="none" stroke="var(--accent)" stroke-width="0.7"/>')
    for j in range(g['n']):
        q = pt(a(j), LOC_R)
        o.append(f'<circle cx="{q[0]:.2f}" cy="{q[1]:.2f}" r="0.42" fill="var(--ink)"/>')
    return '\n'.join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--before', required=True)
    ap.add_argument('--after', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--gap', type=int, default=8, help='draw the gap between post k and post k+1')
    ap.add_argument('--expect-pitch', type=float, default=0.66)
    a = ap.parse_args()

    gb, sb, labb, zb = load(a.before)
    ga, sa, laba, za = load(a.after)
    if (gb['n'], round(gb['r_h'], 3)) != (ga['n'], round(ga['r_h'], 3)):
        sys.exit(f"DECLINE: the two files are not the same geometry ({gb['n']} posts / r_h "
                 f"{gb['r_h']:.2f} vs {ga['n']} / {ga['r_h']:.2f}), so one window cannot frame "
                 f"both and the panels would not be comparable.")
    th_c, uv = frame(gb, a.gap)
    tan_half, lo, hi = window(gb, a.gap, uv)

    hb, tb = border_held(gb, sb, uv, tan_half, lo, hi)
    ha, ta = border_held(ga, sa, uv, tan_half, lo, hi)
    pitch, ncross = stitch_pitch(ga, sa, uv, tan_half, lo, hi)
    cb, ca = clip(sb, uv, tan_half, lo, hi), clip(sa, uv, tan_half, lo, hi)
    bare_b, bare_y = bare_gap(cb, gb['r_h'], hi)
    bare_a, bare_ay = bare_gap(ca, ga['r_h'], hi)
    sys.stderr.write(f"in frame: BEFORE {hb}/{tb} border steps welded, {bare_b:.2f}mm bare up the "
                     f"middle; AFTER {ha}/{ta}, {bare_a:.2f}mm bare; stitch {ncross} crossings at "
                     f"median {pitch and round(pitch, 4)}mm\n")
    if hb != 0:
        sys.exit(f"REFUSE: the BEFORE file welds {hb}/{tb} border steps in this frame, so the "
                 f"figure's claim that nothing joins the net to the wall here is not true of it.")
    if pitch is None or abs(pitch - a.expect_pitch) > 0.1 * a.expect_pitch:
        sys.exit(f"REFUSE: the AFTER file's stitch crosses the border at {pitch}mm, not the "
                 f"{a.expect_pitch}mm the figure would label it.")
    if ha <= hb:
        sys.exit(f"REFUSE: the AFTER file holds {ha}/{ta} border steps against the BEFORE file's "
                 f"{hb}/{tb}; there is no fix here to draw.")

    W, H = 2 * tan_half, hi - lo
    loc_h = 2 * LOC_R + 1.4
    y0 = loc_h + LBL
    y1 = y0 + H + GAPY + LBL
    tw, th = W + 2 * PAD, y1 + H + FOOT
    t = lambda x, y, s, sz=1.5, col='var(--dim)', anc='start': (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{sz}" fill="{col}" text-anchor="{anc}" '
        f'font-family="ui-monospace,monospace">{s}</text>')
    sbx = PAD + W - 10.0
    svg = [f'<svg viewBox="0 0 {tw:.2f} {th:.2f}" xmlns="http://www.w3.org/2000/svg" role="img" '
           f'aria-label="One gap between two posts of the bucket floor, drawn from the emitted '
           f'gcode before and after the border fix">',
           locator(gb, th_c, a.gap, PAD + LOC_R, LOC_R + 0.7),
           t(PAD + 2 * LOC_R + 3, LOC_R - 1.0,
             f'the whole floor seen from above &#183; {2 * gb["r_ring"]:g} mm across &#183; '
             f'{gb["n"]} posts', 1.5, 'var(--ink)'),
           t(PAD + 2 * LOC_R + 3, LOC_R + 1.4,
             'the lit arc is the ONE gap drawn below, at 1:1 with itself', 1.35),
           t(PAD + 2 * LOC_R + 3, LOC_R + 3.6,
             'outward is up &#183; both panels are the same window, same scale', 1.35),
           t(PAD, y0 - 1.3, f'BEFORE &#183; {hb} of {tb} border steps have floor welded to them',
             1.6, 'var(--ink)'),
           panel(cb, tan_half, lo, hi, PAD, y0),
           t(PAD + tan_half, y0 + hi - bare_y + 0.55,
             f'{bare_b:.1f} mm of bare plate', 1.35, 'var(--dim)', 'middle'),
           t(PAD, y1 - 1.3, f'AFTER &#183; {ha} of {ta} welded &#183; a stitch every '
             f'{pitch:.2f} mm', 1.6, 'var(--ink)'),
           panel(ca, tan_half, lo, hi, PAD, y1),
           # the same probe on both panels, or the pair would be a comparison of two questions
           t(PAD + tan_half, y1 + hi - bare_ay + 0.55,
             f'{bare_a:.1f} mm', 1.35, 'var(--dim)', 'middle'),
           f'<line x1="{sbx:.2f}" y1="{th - 2.2:.2f}" x2="{sbx + 10:.2f}" y2="{th - 2.2:.2f}" '
           f'stroke="var(--dim)" stroke-width="0.3"/>',
           t(sbx + 5, th - 0.5, '10 mm', 1.35, 'var(--dim)', 'middle'),
           t(PAD, th - 0.5, f'{labb} of the floor, z {zb:g} mm', 1.35),
           '</svg>']
    open(a.out, 'w').write('\n'.join(svg) + '\n')
    sys.stderr.write(f"wrote {a.out}: window {W:.1f} x {H:.1f} mm, {len(cb)} + {len(ca)} moves, "
                     f"{labb} z{zb:g} vs {laba} z{za:g}\n")


if __name__ == '__main__':
    main()
