#!/usr/bin/env python3
"""Render a petalwall panel gcode: both layers, crossing lifts highlighted.

Reads the EMITTED file, never the generator's intent — the diagram must be able to
disagree with the code (publish-as-we-go rule: diagrams from the real artifact).
"""
import re, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

path = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else "out/petalwall_panel.png"

moves = []          # (x0,y0,x1,y1,z1,extruding)
x = y = z = None
e_prev = 0.0
for line in open(path):
    if line.startswith(";"):
        continue
    m = dict(re.findall(r"([XYZEF])(-?\d+\.?\d*)", line.split(";")[0]))
    if not line.startswith(("G0", "G1")):
        continue
    nx = float(m["X"]) if "X" in m else x
    ny = float(m["Y"]) if "Y" in m else y
    nz = float(m["Z"]) if "Z" in m else z
    ne = float(m["E"]) if "E" in m else e_prev
    if x is not None and nx is not None and (nx != x or ny != y):
        moves.append((x, y, nx, ny, nz, ne > e_prev + 1e-9))
    x, y, z, e_prev = nx, ny, nz, (ne if "E" in m else e_prev)

zs = sorted({round(m[4], 3) for m in moves if m[5]})
print(f"extruding Z range: {zs[0]}..{zs[-1]} ({len(zs)} values)")
# layer 1 lives at 0.1 + lifts to 0.5; layer 2 at 0.7 + lifts to 1.1 — split at 0.6
fig, axes = plt.subplots(1, 2, figsize=(20, 7.2), facecolor="#111114")
for ax, (lo, hi), name in zip(
        axes, [(0.0, 0.6), (0.6, 99)],
        ["layer 1 (pressed 0.1)", "layer 2 (0.7)"]):
    ax.set_facecolor("#111114")
    n_flat = n_lift = 0
    for x0, y0, x1, y1, z1, ext in moves:
        if not ext or not (lo <= z1 < hi):
            continue
        lifted = z1 > lo + 0.15   # above the layer's base = crossing lift
        if lifted:
            ax.plot([x0, x1], [y0, y1], color="#ff9d33", lw=1.6, alpha=0.95, zorder=3)
            n_lift += 1
        else:
            ax.plot([x0, x1], [y0, y1], color="#5fd4d0", lw=0.7, alpha=0.8, zorder=2)
            n_flat += 1
    ax.set_aspect("equal")
    ax.set_title(f"{name} — {n_flat} moves, {n_lift} lifted (orange)",
                 color="#eeeeee", fontsize=13)
    ax.tick_params(colors="#888888", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#444444")
fig.suptitle(path.split("/")[-1], color="#aaaaaa", fontsize=10)
fig.tight_layout()
fig.savefig(out, dpi=110, facecolor="#111114")
print(out)
