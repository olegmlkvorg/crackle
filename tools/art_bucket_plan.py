#!/usr/bin/env python3
"""art_bucket_plan — PLAN + RENDER for a bucket whose wall follows an arbitrary silhouette.

Oleg, 2026-08-08: "lets now make outer shape as pikachu and inner hole in the bottom as other
shape of pikachu, pick some fanart from online, show me thr render of the model at end. we want
abound 20% of floor only as solid brim and rest used for the art".

This tool is the RENDER-BEFORE-PLATES half (the drum doctrine): it traces two silhouette PNGs,
plans the post ring / floor brim / net / art hole with the SAME constants the bucket system
proved (tower OD, wrap, mouth-out, lap law), measures what the geometry would build, and draws
it. It emits NO gcode — the generator comes after the render is approved, and the per-plate go
after that.

THE TOOL IS GENERIC ON PURPOSE: it takes any two silhouette PNGs. Character art used as input
is third-party IP — inputs and outputs live in out/ (gitignored), never in the repo, and a part
built from one is for the household, not for a shop page.

Usage:
  python3 tools/art_bucket_plan.py --outer A.png --hole B.png [--size 330] [--pitch 40]
                                   [--smooth 4] [--hole-frac 0.5] [--out out/plan.png]
"""
import argparse, math, os, shlex, sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import machine

BW = machine.SLICER_LINE_W                     # 0.82
STICK, ALLOW, WRAP = 3.175, 1.665, 287.5       # v16's accepted C-channel
TOWER_D = STICK + ALLOW + 2.0 * BW             # 6.48
R_T = (TOWER_D - BW) / 2.0                     # centreline radius 2.83
HALF = math.radians(WRAP / 2.0)
FLOOR1_OVERLAP = 0.80                          # the lap law (bucket_towers.FLOOR1_OVERLAP)
PROVEN_CHORD = 63.8417                         # machine.PROVEN_SEND span_mm, accepted 2026-08-08


def largest_contour(png, alpha_thr=200, dilate_px=0):
    """The silhouette contour with the LARGEST ENCLOSED AREA, in PIXEL coords.

    Area, not length: stock art carries a wide soft drop SHADOW whose flat contour can be LONGER
    than the figure's while enclosing far less — picking by length traced the shadow band on two
    of three sources (measured: 'outer' became a full-width sliver, brim 0.8mm, min width 0.5).
    The high alpha threshold (200) drops the soft shadow before it can merge with the figure
    under dilation."""
    im = Image.open(png).convert("RGBA")
    a = np.array(im.getchannel("A"), dtype=float)
    if a.max() - a.min() < 10:                  # no useful alpha: threshold on luminance.
        # The cut is against WHITE BACKGROUND, not against dark ink: a yellow body reads ~213
        # luminance and a 200 threshold traced only the black outline stroke of the drawing
        # (min width 0.2mm, brim 0.9mm -- measured garbage before this was caught).
        g = np.array(im.convert("L"), dtype=float)
        mask = (g < 242).astype(float)
    else:
        mask = (a >= alpha_thr).astype(float)
    if dilate_px > 0:
        # FATTEN THIN FEATURES (ears): a wall needs two posts of width plus clear air between;
        # a 12mm peninsula cannot carry one. Morphological dilation widens every feature by
        # dilate_px on each side -- the body reads chunkier, the ears become printable.
        # PAD FIRST: a figure grown into the image border splits the level contour into clipped
        # OPEN segments, and the "largest area" of an open segment is garbage (measured: the
        # 63,424mm2 figure became a 6,756mm2 sliver the moment dilation touched the frame).
        pad = int(dilate_px) + 2
        mask = np.pad(mask, pad, constant_values=0.0)
        from PIL import ImageFilter
        mim = Image.fromarray((mask * 255).astype("uint8"))
        k = 2 * int(dilate_px) + 1
        mim = mim.filter(ImageFilter.MaxFilter(k))
        mask = (np.array(mim, dtype=float) >= 128).astype(float)
    fig = plt.figure()
    cs = plt.contour(mask, levels=[0.5])
    segs = [s for lv in cs.allsegs for s in lv]
    plt.close(fig)
    def enc_area(seg):
        pp = np.array(seg)
        return abs(0.5 * float(np.dot(pp[:, 0], np.roll(pp[:, 1], -1))
                               - np.dot(pp[:, 1], np.roll(pp[:, 0], -1))))
    best = max(segs, key=enc_area)
    pts = np.array(best)                        # (x, y) in pixel coords
    if np.hypot(*(pts[0] - pts[-1])) > 2:
        pts = np.vstack([pts, pts[0]])
    return pts


def resample(pts, step):
    """Uniform arc-length resample of a closed polyline."""
    d = np.hypot(*np.diff(pts, axis=0).T)
    s = np.concatenate([[0], np.cumsum(d)])
    total = s[-1]
    n = max(16, int(total / step))
    si = np.linspace(0, total, n, endpoint=False)
    x = np.interp(si, s, pts[:, 0])
    y = np.interp(si, s, pts[:, 1])
    return np.column_stack([x, y])


def smooth_closed(pts, sigma_pts):
    """Circular gaussian smoothing of a closed polyline."""
    if sigma_pts <= 0:
        return pts
    k = int(max(3, sigma_pts * 6)) | 1
    xs = np.arange(k) - k // 2
    w = np.exp(-0.5 * (xs / sigma_pts) ** 2)
    w /= w.sum()
    out = np.empty_like(pts)
    for j in (0, 1):
        col = pts[:, j]
        ext = np.concatenate([col[-(k // 2):], col, col[:k // 2]])
        out[:, j] = np.convolve(ext, w, mode="valid")
    return out


def shoelace(pts):
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def prep(png, size_mm, smooth_mm, dilate_mm=0.0):
    """Trace -> mm scale -> smooth -> CCW closed polyline at 1mm steps."""
    raw0 = largest_contour(png)
    if dilate_mm > 0:
        lo0, hi0 = raw0.min(axis=0), raw0.max(axis=0)
        px_per_mm = max(hi0 - lo0) / size_mm
        raw = largest_contour(png, dilate_px=max(1, int(round(dilate_mm * px_per_mm))))
    else:
        raw = raw0
    raw[:, 1] = -raw[:, 1]                      # image y-down -> plan y-up
    lo, hi = raw.min(axis=0), raw.max(axis=0)
    scale = size_mm / max(hi - lo)
    pts = (raw - (lo + hi) / 2) * scale         # centred on origin, mm
    pts = resample(pts, 1.0)
    pts = smooth_closed(pts, smooth_mm)         # sigma in points == mm after resample
    pts = resample(pts, 1.0)
    if shoelace(pts) < 0:
        pts = pts[::-1]
    return pts


def normals(pts):
    """Outward unit normals of a CCW closed polyline."""
    nxt = np.roll(pts, -1, axis=0)
    prv = np.roll(pts, 1, axis=0)
    t = nxt - prv
    t /= np.hypot(*t.T)[:, None]
    return np.column_stack([t[:, 1], -t[:, 0]])


def offset_inward(pts, d, resmooth=6.0):
    """Approximate inward offset: move along -normal, then smooth + resample. Good enough for a
    plan render; the generator does exact math later."""
    o = pts - normals(pts) * d
    o = smooth_closed(o, resmooth)
    return resample(o, 1.0)


# MOUTH-CENTRE angle per post is phi + stag; MATERIAL is centred opposite it (phi + stag + pi)
# and spans WRAP degrees, so the tips flank the mouth at phi + stag +- tip_off.
tip_off = math.radians((360.0 - WRAP) / 2.0)


def ring_posts(poly, pitch):
    """Equal-arc post centres + outward-normal angles along a closed CCW polyline.

    MODULE LEVEL since 2026-08-08 (was nested in main): the emitter art_bucket.py imports this,
    and two implementations of one placement is the drift this repo keeps paying for."""
    dd = np.hypot(*np.diff(poly, axis=0).T)
    ss = np.concatenate([[0], np.cumsum(dd)])
    n = max(6, int(round(ss[-1] / pitch)))
    qs = np.linspace(0, ss[-1], n, endpoint=False)
    cx = np.interp(qs, ss, poly[:, 0])
    cy = np.interp(qs, ss, poly[:, 1])
    cs = np.column_stack([cx, cy])
    onn = normals(poly)
    ph = np.empty(n)
    for i, q in enumerate(qs):
        j = np.searchsorted(ss, q) % len(onn)
        ph[i] = math.atan2(onn[j, 1], onn[j, 0])
    return cs, ph


def dip(p, q, c, phi, stag=0.0, n=64):
    """dip DEPTH: how far chord p->q passes inside a post's MATERIAL sector (mouth at phi+stag).

    Module level for the same reason as ring_posts. `n` is the sample count -- the emitter's
    gate re-measures at its own finer resolution; 64 is the planner's render-cost setting."""
    worst = 0.0
    for t in np.linspace(0, 1, n):
        x, y = p + (q - p) * t
        r = math.hypot(x - c[0], y - c[1])
        if r >= R_T:
            continue
        off = (math.atan2(y - c[1], x - c[0]) - (phi + stag + math.pi)) % (2 * math.pi)
        off = off - 2 * math.pi if off > math.pi else off
        if abs(off) <= HALF:
            worst = max(worst, R_T - r)
    return worst


def solve_ring(cs, ph):
    """PER-POST MOUTH ROTATION -- the bucket's stagger window, localized. Each post's mouth
    turns within +-40 deg of its outward normal so its two crossings clear the material;
    greedy sweeps, measured not argued. Returns (stag[], chords, violations[(k,j,depth)])."""
    n = len(cs)
    stag = np.zeros(n)

    def tips(i):
        L2 = cs[i] + R_T * np.array([math.cos(ph[i] + stag[i] + tip_off),
                                     math.sin(ph[i] + stag[i] + tip_off)])
        T2 = cs[i] + R_T * np.array([math.cos(ph[i] + stag[i] - tip_off),
                                     math.sin(ph[i] + stag[i] - tip_off)])
        return L2, T2

    def gap_cost(k):
        p2 = tips(k)[0]
        q2 = tips((k + 1) % n)[1]
        c0 = 0.0
        for j in (k - 1, k, (k + 1) % n, (k + 2) % n):
            c0 += dip(p2, q2, cs[j % n], ph[j % n], stag[j % n])
        return c0

    for _sweep in range(4):
        for i in range(n):
            best, bestd = stag[i], None
            for cand in np.radians(np.arange(-40, 41, 5)):
                stag[i] = cand
                dcur = gap_cost(i - 1) + gap_cost(i)
                if bestd is None or dcur < bestd - 1e-12:
                    bestd, best = dcur, cand
            stag[i] = best
    ch = []
    for k in range(n):
        p2 = tips(k)[0]
        q2 = tips((k + 1) % n)[1]
        ch.append((p2, q2, float(np.hypot(*(q2 - p2)))))
    vv = []
    for k, (p2, q2, L2) in enumerate(ch):
        for j in range(n):
            dpt = dip(p2, q2, cs[j], ph[j], stag[j])
            if dpt > 0.05:                    # a bead-scale graze, not a float epsilon
                vv.append((k, j, dpt))
    return stag, ch, vv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outer", required=True)
    ap.add_argument("--hole", required=True)
    ap.add_argument("--size", type=float, default=330.0, help="max extent of wall material, mm")
    ap.add_argument("--pitch", type=float, default=40.0, help="post spacing along the outline, mm")
    ap.add_argument("--smooth", type=float, default=4.0, help="gaussian sigma, mm")
    ap.add_argument("--hole-frac", type=float, default=0.50,
                    help="hole max extent as a fraction of the outer's")
    ap.add_argument("--brim-frac", type=float, default=0.20,
                    help="fraction of floor area laid solid at the wall")
    ap.add_argument("--net-pitch", type=float, default=4.0)
    ap.add_argument("--dilate", type=float, default=0.0,
                    help="fatten every silhouette feature by this many mm per side (ears)")
    ap.add_argument("--wall-h", type=float, default=152.4, help="outer wall height mm (6 in)")
    ap.add_argument("--inner-wall-h", type=float, default=50.8,
                    help="inner (cut) wall height mm (2 in); 0 = no inner wall")
    ap.add_argument("--out", default="out/art_bucket_plan.png")
    a = ap.parse_args()

    outer = prep(a.outer, a.size - BW, a.smooth, dilate_mm=a.dilate)
    per = float(np.hypot(*np.diff(np.vstack([outer, outer[:1]]), axis=0).T).sum())
    area = abs(shoelace(outer))
    n_posts = max(8, int(round(per / a.pitch)))
    # posts at equal arc length
    d = np.hypot(*np.diff(outer, axis=0).T)
    s = np.concatenate([[0], np.cumsum(d)])
    posts_s = np.linspace(0, s[-1], n_posts, endpoint=False)
    px = np.interp(posts_s, s, outer[:, 0])
    py = np.interp(posts_s, s, outer[:, 1])
    centres = np.column_stack([px, py])
    nrm = np.empty_like(centres)
    on = normals(outer)
    for i, ps in enumerate(posts_s):
        j = np.searchsorted(s, ps) % len(on)
        nrm[i] = on[j]
    phis = np.arctan2(nrm[:, 1], nrm[:, 0])              # outward normal angle per post

    stags, chords, viol = solve_ring(centres, phis)
    max_chord = max(c[2] for c in chords)

    # min feature width: nearest non-neighbour outline approach
    m = len(outer)
    minw, minw_at = 1e9, None
    for i in range(0, m, 4):
        d2 = np.hypot(*(outer - outer[i]).T)
        idx = np.arange(m)
        ring = np.minimum(np.abs(idx - i), m - np.abs(idx - i))
        far = ring > 25                                   # >25mm of arc away
        if far.any():
            j = np.argmin(np.where(far, d2, 1e9))
            if d2[j] < minw:
                minw, minw_at = float(d2[j]), outer[i]

    # floor: brim width for the requested solid fraction
    w_brim = a.brim_frac * area / per
    n_rings = max(2, int(round(w_brim / (FLOOR1_OVERLAP * BW))))
    inner_edge = offset_inward(outer, R_T + BW / 2 + w_brim)

    # THE HOLE MUST FIT INSIDE THE NET REGION with clearance: shrink until every hole point
    # sits inside inner_edge inset a further 8mm, nudging toward the interior centroid.
    P_fit = MplPath(offset_inward(inner_edge, 8.0))
    frac = a.hole_frac
    hole = None
    ictr = inner_edge.mean(axis=0)
    for _ in range(16):
        cand0 = prep(a.hole, (a.size - BW) * frac, max(3.0, a.smooth * frac))
        cand0 = cand0 - cand0.mean(axis=0)
        done = False
        for dx in (0, -10, 10, -20, 20):
            for dy in (0, -10, 10, -20, 20, -30, 30):
                cand = cand0 + ictr + (dx, dy)
                if P_fit.contains_points(cand).all():
                    hole, done = cand, True
                    break
            if done:
                break
        if done:
            break
        frac *= 0.94
    if hole is None:
        hole = cand0 + ictr
        print("  ~ hole never fully fit; shipping smallest attempt for the render")
    hole_area = abs(shoelace(hole))

    # THE INNER WALL (Oleg, mid-render: "since we are having the middle cut, lets have walls
    # there as well but only 2 inch, while outer wall is 6 inch"). Posts along the cut's outline.
    # MOUTHS TOWARD THE NET (the bucket interior; sticks clip in from inside the bucket), the
    # CONTINUOUS face toward the cut, so the art hole's edge reads as an unbroken line and the
    # crossings run on the net side, buried against the floor rather than across the art.
    # RETRACTION 2026-08-08: the first caption on this render said "mouths INTO the cut" while
    # the arcs as DRAWN (and as solved -- mouth = phi + stag, phi the outward normal, which for
    # the hole polygon points into the net) faced the net. The drawing was right, the words were
    # wrong, and Oleg approved the DRAWING. Flippable at the emitter if he wants sticks showing
    # through the cut instead (--inner-mouth).
    in_centres = in_phis = None
    in_chords, in_viol = [], []
    if a.inner_wall_h > 0:
        in_centres, in_phis = ring_posts(hole, a.pitch * 0.8)
        in_stags, in_chords, in_viol = solve_ring(in_centres, in_phis)

    # net hatch, clipped inside inner_edge and outside hole
    P_in = MplPath(inner_edge)
    P_hole = MplPath(hole)
    lo, hi = outer.min(axis=0), outer.max(axis=0)
    hatch = []
    y = lo[1]
    while y <= hi[1]:
        xs = np.arange(lo[0], hi[0], 2.0)
        ptsl = np.column_stack([xs, np.full_like(xs, y)])
        ok = P_in.contains_points(ptsl) & ~P_hole.contains_points(ptsl)
        run = None
        for i, o in enumerate(ok):
            if o and run is None:
                run = xs[i]
            if not o and run is not None:
                hatch.append(((run, y), (xs[i - 1], y)))
                run = None
        if run is not None:
            hatch.append(((run, y), (xs[-1], y)))
        y += a.net_pitch
    net_len = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in hatch)

    # ---------------------------------------------------------------- render
    SC, PAD = 4.0, 60
    W = int((hi[0] - lo[0]) * SC) + 2 * PAD
    H = int((hi[1] - lo[1]) * SC) + 2 * PAD
    img = Image.new("RGB", (W + 460, max(H, 900)), "white")
    dr = ImageDraw.Draw(img)

    def T(p):
        return (PAD + (p[0] - lo[0]) * SC, PAD + (hi[1] - p[1]) * SC)

    # brim band: fill between wall inset and inner_edge
    wall_in = offset_inward(outer, R_T + BW / 2)
    dr.polygon([T(p) for p in wall_in], fill=(255, 224, 130))
    dr.polygon([T(p) for p in inner_edge], fill=(255, 255, 255))
    # net
    for p, q in hatch:
        dr.line([T(p), T(q)], fill=(200, 200, 205), width=1)
    # hole: white with drawn outline ring
    dr.polygon([T(p) for p in hole], fill=(255, 255, 255))
    dr.line([T(p) for p in np.vstack([hole, hole[:1]])], fill=(230, 90, 40), width=3)
    # inner wall (2in): posts + crossings on the cut outline
    for pch in (in_chords or []):
        dr.line([T(pch[0]), T(pch[1])], fill=(170, 150, 150), width=2)
    if in_centres is not None:
        for k in range(len(in_centres)):
            c2, ph2 = in_centres[k], in_phis[k]
            a0i = math.degrees(-(ph2 + in_stags[k] + math.pi + HALF))
            a1i = math.degrees(-(ph2 + in_stags[k] + math.pi - HALF))
            bb2 = [T((c2[0] - R_T, c2[1] + R_T)), T((c2[0] + R_T, c2[1] - R_T))]
            dr.arc([bb2[0], bb2[1]], start=min(a0i, a1i), end=max(a0i, a1i),
                   fill=(180, 60, 20), width=5)
        for k, j, dpt in in_viol:
            pp, qq, LL = in_chords[k]
            dr.line([T(pp), T(qq)], fill=(220, 30, 30), width=4)
    # crossings (fabric hint)
    for p, q, L in chords:
        dr.line([T(p), T(q)], fill=(150, 150, 160), width=2)
    # posts: material arcs, mouth out
    for k in range(n_posts):
        c = centres[k]
        a0 = math.degrees(-(phis[k] + stags[k] + math.pi + HALF))
        a1 = math.degrees(-(phis[k] + stags[k] + math.pi - HALF))
        bb = [T((c[0] - R_T, c[1] + R_T)), T((c[0] + R_T, c[1] - R_T))]
        dr.arc([bb[0], bb[1]], start=min(a0, a1), end=max(a0, a1), fill=(20, 20, 30), width=6)
    # violations
    for k, j, dpt in viol:
        p, q, L = chords[k]
        dr.line([T(p), T(q)], fill=(220, 30, 30), width=4)
    if minw_at is not None and minw < 2 * TOWER_D + 10:
        x, y = T(minw_at)
        dr.ellipse([x - 12, y - 12, x + 12, y + 12], outline=(220, 30, 30), width=3)

    # side panel: sources + numbers
    x0 = W + 20
    for i, (path, label) in enumerate(((a.outer, "OUTER = wall"), (a.hole, "HOLE = floor art"))):
        th = Image.open(path).convert("RGBA")
        th.thumbnail((190, 190))
        bg = Image.new("RGBA", th.size, (245, 245, 245, 255))
        img.paste(Image.alpha_composite(bg, th).convert("RGB"), (x0 + i * 210, 20))
        dr.text((x0 + i * 210, 216), label, fill=(0, 0, 0))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 15)
    except Exception:
        font = None
    # THE INVOCATION, VERBATIM, ON THE ARTIFACT. Learned the hard way TODAY: plan D was approved
    # off a render whose exact flags nobody recorded, and reproducing them took a parameter sweep
    # against the render's own numbers panel. Same law as bucket_towers' '; CMD=' stamp.
    cmd_line = "CMD: " + " ".join(shlex.quote(s)
                                  for s in [os.path.basename(sys.argv[0])] + sys.argv[1:])
    lines = [
        "ART BUCKET — PLAN (no gcode yet; render checkpoint)",
        cmd_line,
        f"heights                outer wall {a.wall_h:.0f} mm (6 in)   "
        f"inner cut wall {a.inner_wall_h:.0f} mm (2 in)",
        f"wall material extent   {a.size:.0f} mm   perimeter {per:.0f} mm",
        f"posts                  {n_posts} x OD {TOWER_D:g} C-channels, wrap {WRAP:g}, MOUTH OUT",
        f"post pitch             {per / n_posts:.1f} mm arc",
        f"max crossing chord     {max_chord:.1f} mm  (proven {PROVEN_CHORD:.1f})  "
        + ("INSIDE evidence" if max_chord <= PROVEN_CHORD else "!! PAST EVIDENCE"),
        f"crossing violations    {len(viol)}"
        + (f"  worst dip {max(v[2] for v in viol):.2f} mm (red)" if viol else "  (none; per-post mouth solve)"),
        f"min feature width      {minw:.1f} mm" + ("  !! narrow zone circled" if minw < 2 * TOWER_D + 10 else ""),
        f"floor area             {area / 100:.0f} cm2   brim {a.brim_frac * 100:.0f}% -> "
        f"{w_brim:.1f} mm band = {n_rings} lap rings",
        f"art hole               {(a.size - BW) * frac:.0f} mm (auto-fit), area {hole_area / 100:.0f} cm2 "
        f"({hole_area / area * 100:.0f}% of floor)",
        f"net                    {len(hatch)} strands at {a.net_pitch:g} mm, {net_len / 1000:.1f} m",
        (f"inner wall             {len(in_centres)} posts, mouths toward the NET (as drawn; flippable); "
         f"max chord {max(c[2] for c in in_chords):.1f} mm; violations {len(in_viol)}"
         + (f" worst {max(v[2] for v in in_viol):.2f} mm" if in_viol else "")
         if in_centres is not None else "inner wall             none"),
        "",
        "IP: character art -> household part only, never a shop page.",
        "Nothing here is proven printable until the generator's gates run.",
    ]
    for i, ln in enumerate(lines):
        dr.text((x0, 250 + i * 22), ln, fill=(0, 0, 0), font=font)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    img.save(a.out)
    print(a.out)
    print(f"  {cmd_line}")
    print(f"  posts {n_posts}  max chord {max_chord:.1f} (proven {PROVEN_CHORD:.1f})  "
          f"violations {len(viol)}  min width {minw:.1f}  brim {w_brim:.1f}mm/{n_rings} rings  "
          f"hole {hole_area / area * 100:.0f}% of floor  net {net_len / 1000:.1f}m")
    if in_centres is not None:
        print(f"  inner wall: {len(in_centres)} posts  max chord "
              f"{max(c[2] for c in in_chords):.1f}  violations {len(in_viol)}"
              + (f" worst {max(v[2] for v in in_viol):.2f}mm" if in_viol else ""))


if __name__ == "__main__":
    main()
