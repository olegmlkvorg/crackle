#!/usr/bin/env python3
"""render_stand_stl.py — LOOK at a binary STL before it is printed (base_stl / platform_stl).

Three orthographic panels so the owner can react to the FORM: an isometric shaded view, a PLAN (from
above — the beautiful-from-above rosette + the socket triangle), and a FRONT elevation. Shading is
flat per-face from a fixed light, so the lobes and sockets read as solid geometry, not a wire dump.
Black + orange to match the stand's identity.

Usage: python3 render_stand_stl.py part.stl [out.png] [--title "BASE plinth"]
"""
import math, os, struct, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

BG, ORANGE, INK, DIM = "#0d0d10", (1.0, 0.576, 0.2), "#f2ede6", "#6b665e"


def read_stl(path):
    tris = []
    with open(path, "rb") as fh:
        fh.read(80)
        (count,) = struct.unpack("<I", fh.read(4))
        for _ in range(count):
            fh.read(12)
            vs = [struct.unpack("<3f", fh.read(12)) for _ in range(3)]
            fh.read(2)
            tris.append(vs)
    return tris


def face_normal(t):
    a, b, c = t
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    m = math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
    return (nx/m, ny/m, nz/m)


def shade(n, light=(0.4, -0.5, 0.75)):
    lm = math.sqrt(sum(c*c for c in light))
    d = abs(sum(a*b for a, b in zip(n, light)) / lm)      # two-sided: normals may not be outward
    i = 0.28 + 0.72 * d                                    # ambient + diffuse
    return (ORANGE[0]*i, ORANGE[1]*i, ORANGE[2]*i)


def main():
    src = sys.argv[1]
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    out = args[0] if args else src.rsplit(".", 1)[0] + ".png"
    title = "STL"
    for a in sys.argv[2:]:
        if a.startswith("--title"):
            title = a.split("=", 1)[1] if "=" in a else "STL"
    if "--title" in sys.argv:
        title = sys.argv[sys.argv.index("--title") + 1]

    tris = read_stl(src)
    normals = [face_normal(t) for t in tris]
    cols = [shade(n) for n in normals]
    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    zs = [v[2] for t in tris for v in t]
    x0, x1, y0, y1, z0, z1 = min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)

    fig = plt.figure(figsize=(18, 6.6), facecolor=BG)
    fig.suptitle(f"{title}   —   {os.path.basename(src)}   —   {len(tris)} triangles   "
                 f"footprint {x1-x0:.0f} x {y1-y0:.0f} mm   height {z1-z0:.1f} mm",
                 color=INK, family="monospace", fontsize=13, y=0.985)

    # ---- panel 1: isometric shaded 3D ----
    ax = fig.add_subplot(1, 3, 1, projection="3d")
    ax.set_facecolor(BG)
    pc = Poly3DCollection(tris, facecolors=cols, edgecolors=(0, 0, 0, 0.12), linewidths=0.15)
    ax.add_collection3d(pc)
    R = max(x1-x0, y1-y0, z1-z0) / 2
    cx, cy, cz = (x0+x1)/2, (y0+y1)/2, (z0+z1)/2
    ax.set_xlim(cx-R, cx+R); ax.set_ylim(cy-R, cy+R); ax.set_zlim(cz-R, cz+R)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=24, azim=-58)
    ax.set_axis_off()
    ax.set_title("ISOMETRIC", color=DIM, family="monospace", fontsize=11)

    # ---- panel 2: PLAN (top-down, XY), shaded by height ----
    ax2 = fig.add_subplot(1, 3, 2)
    ax2.set_facecolor(BG)
    order = sorted(range(len(tris)), key=lambda i: (tris[i][0][2]+tris[i][1][2]+tris[i][2][2]))
    polys = [[(tris[i][0][0], tris[i][0][1]), (tris[i][1][0], tris[i][1][1]),
              (tris[i][2][0], tris[i][2][1])] for i in order]
    hcols = []
    for i in order:
        zc = (tris[i][0][2]+tris[i][1][2]+tris[i][2][2]) / 3
        t = (zc - z0) / max(z1-z0, 1e-6)
        hcols.append((ORANGE[0]*(0.35+0.65*t), ORANGE[1]*(0.35+0.65*t), ORANGE[2]*(0.35+0.65*t)))
    ax2.add_collection(PolyCollection(polys, facecolors=hcols, edgecolors=(0, 0, 0, 0.10),
                                      linewidths=0.1))
    ax2.set_xlim(x0-6, x1+6); ax2.set_ylim(y0-6, y1+6); ax2.set_aspect("equal")
    ax2.set_axis_off()
    ax2.set_title("PLAN — from above (bright = higher)", color=DIM, family="monospace", fontsize=11)

    # ---- panel 3: FRONT elevation (XZ) ----
    ax3 = fig.add_subplot(1, 3, 3)
    ax3.set_facecolor(BG)
    polys3 = [[(v[0], v[2]) for v in t] for t in tris]
    fcols = [shade(n, light=(0.0, 0.0, 1.0)) for n in normals]
    ax3.add_collection(PolyCollection(polys3, facecolors=fcols, edgecolors=(0, 0, 0, 0.08),
                                      linewidths=0.1))
    ax3.set_xlim(x0-6, x1+6); ax3.set_ylim(z0-4, z1+4); ax3.set_aspect("equal")
    ax3.set_axis_off()
    ax3.set_title("FRONT — from the side", color=DIM, family="monospace", fontsize=11)

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out, dpi=110, facecolor=BG)
    print(f"{out}  ({len(tris)} tris, {x1-x0:.0f}x{y1-y0:.0f}x{z1-z0:.1f} mm)")


if __name__ == "__main__":
    main()
