#!/usr/bin/env python3
"""Render an emitted art_bucket gcode to PNG — the drum-doctrine render, FROM the artifact.

Three panels, all drawn from the file's own moves (never from the plan that produced it):
  FLOOR    every extruded floor move at its measured width; the art is what you see
  WALLS    one wall layer's plan (posts, crossings, the transit V)
  SIDE     elevation: every move projected on XZ, colour by Z

Usage: python3 tools/render_art.py out/art_bucket_*.gcode [out.png]
"""
import math, os, re, sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import machine

path = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(path)[0] + ".png"

floor_segs, floor_w = [], []          # ((x,y),(x,y)), width
wall_segs, wall_kind = [], []         # one chosen wall layer
side_segs, side_z = [], []
n_layers = 0
cur_layer = None
wall_pick = None
x = y = None
z = 0.0
e = 0.0
is_floor = False
for ln in open(path):
    if ln.startswith("; ---- layer"):
        m = re.match(r"; ---- layer (\d+) of (\d+)\s+z ([\d.]+)\s+\((.*)\)", ln)
        cur_layer = int(m.group(1))
        n_layers = int(m.group(2))
        z = float(m.group(3))
        lab = m.group(4)
        is_floor = "floor latch" in lab
        if wall_pick is None and not is_floor and "inner" in lab:
            wall_pick = cur_layer + 40          # a mid-height inner-wall layer
        continue
    c = ln.split(";")[0].strip()
    if not c.startswith(("G0", "G1")):
        if c.startswith("G92"):
            m = re.search(r"E(-?[\d.]+)", c)
            if m:
                e = float(m.group(1))
        continue
    gd = dict(re.findall(r"\b([XYZE])(-?\d+(?:\.\d+)?)", c))
    nx = float(gd["X"]) if "X" in gd else x
    ny = float(gd["Y"]) if "Y" in gd else y
    de = 0.0
    if "E" in gd:
        v = float(gd["E"])
        de, e = v - e, v
    if cur_layer and de > 0 and None not in (x, y, nx, ny) and (nx != x or ny != y):
        d = math.hypot(nx - x, ny - y)
        if is_floor and d > 1e-6:
            floor_segs.append(((x, y), (nx, ny)))
            floor_w.append(de * machine.A_FIL / d / 0.25)
        if cur_layer == wall_pick:
            wall_segs.append(((x, y), (nx, ny)))
            wall_kind.append("cross" if ("THIN CROSS" in ln or "BRIDGE" in ln) else "wall")
        if cur_layer % 6 == 0 or is_floor:
            side_segs.append(((x, z), (nx, z)))
            side_z.append(z)
    if "X" in gd:
        x = nx
    if "Y" in gd:
        y = ny

fig, axes = plt.subplots(1, 3, figsize=(26, 10),
                         gridspec_kw={"width_ratios": [1.15, 1.0, 0.9]})
ax = axes[0]
lw = np.clip(np.array(floor_w) * 0.55, 0.3, 3.2)
ax.add_collection(LineCollection(floor_segs, linewidths=lw, colors=(0.15, 0.15, 0.2, 0.85),
                                 capstyle="round"))
ax.set_title(f"FLOOR — every extruded floor move, width as measured off E "
             f"({len(floor_segs)} moves)")
ax = axes[1]
wcol = {"wall": (0.1, 0.1, 0.15, 0.95), "cross": (0.75, 0.45, 0.1, 0.6)}
ax.add_collection(LineCollection(
    [s for s, k in zip(wall_segs, wall_kind)], linewidths=1.4,
    colors=[wcol[k] for k in wall_kind], capstyle="round"))
ax.set_title(f"WALL layer {wall_pick} — posts (dark) + crossings/transit (orange)")
ax = axes[2]
zz = np.array(side_z)
cols = plt.cm.viridis(zz / max(zz.max(), 1))
ax.add_collection(LineCollection(side_segs, linewidths=0.5, colors=cols))
ax.set_title("SIDE — every 6th layer, colour = Z")
for ax in axes:
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
fig.suptitle(os.path.basename(path) + f"   ({n_layers} layers; rendered FROM the emitted "
             f"bytes, never the plan)", fontsize=13)
fig.tight_layout()
fig.savefig(out, dpi=110)
print(out)
