#!/usr/bin/env python3
"""Render a petalwall panel gcode: hero view (all layers stacked, bead-true widths) plus a
per-layer strip underneath.

Reads the EMITTED file, never the generator's intent — the diagram must be able to
disagree with the code (publish-as-we-go rule: diagrams from the real artifact). Widths are
derived per move from E over distance, so the pressed layer-1 ribbon draws at the ~12mm it
actually lands at and the windows show their true printed size.
"""
import math, re, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

path = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else "out/petalwall_panel.png"

FIL_A = math.pi * (1.75 / 2) ** 2

moves = []          # (x0, y0, x1, y1, zbase, width_mm, is_link)
x = y = z = None
e = 0.0
secs = 0.0
feed = 1200.0
for line in open(path):
    s = line.split(";")[0].strip()
    tag = line.split(";", 1)[1] if ";" in line else ""
    if s.startswith("G92"):
        m = re.search(r"E([-\d.]+)", s)
        if m:
            e = float(m.group(1))
        continue
    if not s.startswith(("G0", "G1")):
        continue
    m = dict(re.findall(r"([XYZEF])(-?\d+\.?\d*)", s))
    nx = float(m["X"]) if "X" in m else x
    ny = float(m["Y"]) if "Y" in m else y
    nz = float(m["Z"]) if "Z" in m else z
    ne = float(m["E"]) if "E" in m else e
    if "F" in m:
        feed = float(m["F"])
    if x is not None and nx is not None and (nx != x or ny != y):
        d = math.hypot(nx - x, ny - y)
        secs += d / max(feed / 60.0, 1e-6)
        if ne > e + 1e-9 and "PRIME" not in tag.upper():
            xsec = (ne - e) * FIL_A / d                    # mm2 laid per mm of path
            lhh = 0.1 if nz < 0.4 else 0.6                 # pressed layer vs body
            moves.append((x, y, nx, ny, round(nz, 3), xsec / lhh, "LINK" in tag.upper()))
    x, y, z, e = nx, ny, nz, ne

grams = sum(math.hypot(m[2] - m[0], m[3] - m[1]) * m[5] * (0.1 if m[4] < 0.4 else 0.6)
            for m in moves) * 1.24 / 1000.0
layers = sorted({m[4] for m in moves})
print(f"{len(moves)} extruding moves, layers at Z {layers}, "
      f"~{grams:.0f} g, ~{secs/60:.0f} min of motion")

xs = [v for m in moves for v in (m[0], m[2])]
ys = [v for m in moves for v in (m[1], m[3])]
x0, x1, y0, y1 = min(xs) - 8, max(xs) + 8, min(ys) - 8, max(ys) + 8
W, H = x1 - x0, y1 - y0

BG = "#0c0c0f"
LAYER_C = ["#5a4420", "#c9a45e", "#f4e8cd", "#ffffff"]      # plate side -> top, dark to bright
LINK_C = "#2e4744"    # links are thin threads later overprinted by full beads — keep them quiet

hero_in = 15.0
fig_h = hero_in * H / W * (1 + 0.36) + 0.6
fig = plt.figure(figsize=(hero_in, fig_h), facecolor=BG)
gs = fig.add_gridspec(2, len(layers), height_ratios=[1.0, 0.34], hspace=0.06, wspace=0.03)
hero = fig.add_subplot(gs[0, :])
minis = [fig.add_subplot(gs[1, i]) for i in range(len(layers))]


def draw(ax, sel, ppm):
    ax.set_facecolor(BG)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_aspect("equal"); ax.axis("off")
    for li, zl in enumerate(sorted(sel)):
        segs, wids, lsegs = [], [], []
        for mx0, my0, mx1, my1, mz, wmm, lnk in moves:
            if mz != zl:
                continue
            if lnk:
                lsegs.append([(mx0, my0), (mx1, my1)])
            else:
                segs.append([(mx0, my0), (mx1, my1)])
                wids.append(max(wmm * ppm, 0.3))
        c = LAYER_C[layers.index(zl)] if len(layers) <= len(LAYER_C) else LAYER_C[-1]
        ax.add_collection(LineCollection(segs, linewidths=wids, colors=c,
                                         capstyle="round", alpha=0.95, zorder=2 + li))
        if zl == max(sel) and len(sel) > 1:
            # bead seams of the top layer: the concentric ripple the printed sheet shows
            ax.add_collection(LineCollection(segs, linewidths=0.35, colors="#d3c19c",
                                             alpha=0.8, zorder=2 + li + 0.5))
        if lsegs:
            ax.add_collection(LineCollection(lsegs, linewidths=0.5, colors=LINK_C,
                                             alpha=0.4, zorder=1))


# points-per-mm for a given axis width fraction of the figure
def ppm_for(frac):
    return hero_in * frac * 72.0 / W


draw(hero, layers, ppm_for(1.0))
hero.set_title(f"{path.split('/')[-1]} — {len(layers)} layers stacked, bead-true widths "
               f"(pressed layer 1 dim, top layer bright) — ~{grams:.0f} g, ~{secs/60:.0f} min",
               color="#d8d0c0", fontsize=12, pad=10)
for i, (ax, zl) in enumerate(zip(minis, layers)):
    draw(ax, [zl], ppm_for(1.0 / len(layers)))
    ax.set_title(f"layer {i+1}  (Z {zl})", color="#8a8478", fontsize=9)

fig.savefig(out, dpi=105, facecolor=BG, bbox_inches="tight")
print(out)
