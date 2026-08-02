#!/usr/bin/env python3
"""render_marble_run.py — the marble-run kit clicked together, for the owner to react to.

Reads the four binary STLs (funnel + spiral chute + drop tube + catch cup), stacks them
with the kit's 15 mm socket/spigot overlap, and draws three panels: the assembled tower
(isometric), a front elevation, and a CUTAWAY with Ø16 marbles placed on the path so the
route reads at a glance. RENDER ONLY — nothing here has been printed or fit-tested yet.

Usage: python3 render_marble_run.py [out/marble_run_assembly.png]
"""
import math, struct, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.patches import Circle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import marble_common as mc

BG, INK, DIM = "#0d0d10", "#f2ede6", "#6b665e"
MARBLE = "#7ec8e3"

# bottom -> top: (stl, tint, label)
STACK = [("catch_cup.stl",    (1.00, 0.45, 0.15), "CATCH CUP"),
         ("drop_tube.stl",    (0.95, 0.62, 0.25), "DROP TUBE"),
         ("spiral_chute.stl", (1.00, 0.58, 0.20), "SPIRAL CHUTE"),
         ("funnel.stl",       (0.95, 0.68, 0.35), "FUNNEL (hopper)")]


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


def shade(t, base, light=(0.4, -0.5, 0.75)):
    a, b, c = t
    ux, uy, uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx, vy, vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    m = math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
    lm = math.sqrt(sum(c_*c_ for c_ in light))
    d = abs((nx*light[0]+ny*light[1]+nz*light[2]) / (m*lm))
    i = 0.25 + 0.75 * d
    return (base[0]*i, base[1]*i, base[2]*i)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "out/marble_run_assembly.png"
    tris, cols, labels = [], [], []
    z_top = 0.0
    for path, tint, label in STACK:
        part = read_stl(path)
        z0 = 0.0 if z_top == 0.0 else z_top - mc.COUPLE_L   # spigot sinks into the socket
        part = [[(v[0], v[1], v[2] + z0) for v in t] for t in part]
        z_top = max(v[2] for t in part for v in t)
        labels.append((label, z0, z_top, path))
        tris += part
        cols += [tint] * len(part)
    H = z_top

    fig = plt.figure(figsize=(17, 11), facecolor=BG)
    fig.suptitle("MARBLE RUN KIT — pour the funnel, orbit the spiral, fall the tube, land in the cup\n"
                 f"stack {H:.0f} mm tall — every joint: BOND v2 Ø{mc.SOCKET_MOUTH_D:g}-mouth socket over "
                 f"Ø{mc.SPIGOT_BASE_D:g}-base spigot, {mc.COUPLE_L:g} mm overlap, friction seat + snap detent "
                 f"— RENDER ONLY: not yet printed, fit untested",
                 color=INK, family="monospace", fontsize=13)

    # ---- panel 1: assembled tower, isometric ----
    ax = fig.add_subplot(1, 3, 1, projection="3d")
    ax.set_facecolor(BG)
    ax.add_collection3d(Poly3DCollection(tris, facecolors=[shade(t, c) for t, c in zip(tris, cols)],
                                         linewidths=0))
    ax.set_xlim(-105, 105); ax.set_ylim(-105, 105); ax.set_zlim(0, H)
    ax.set_box_aspect((210 / H, 210 / H, 1), zoom=1.25)
    ax.view_init(elev=12, azim=-55); ax.set_axis_off()
    ax.set_title("ASSEMBLED", color=DIM, family="monospace", fontsize=11)

    # ---- panel 2: front elevation ----
    ax2 = fig.add_subplot(1, 3, 2)
    ax2.set_facecolor(BG)
    ax2.add_collection(PolyCollection([[(v[0], v[2]) for v in t] for t in tris],
                                      facecolors=[shade(t, c, light=(0, 0, 1)) for t, c in zip(tris, cols)],
                                      linewidths=0))
    for label, z0, z1, _ in labels:
        ax2.annotate(label, xy=(86, (z0 + z1) / 2), color=INK, family="monospace",
                     fontsize=10, va="center")
        ax2.plot([62, 84], [(z0 + z1) / 2] * 2, color=DIM, lw=0.8)
    ax2.set_xlim(-95, 210); ax2.set_ylim(-8, H + 8); ax2.set_aspect("equal"); ax2.set_axis_off()
    ax2.set_title("FRONT", color=DIM, family="monospace", fontsize=11)

    # ---- panel 3: cutaway (far half) + marbles on the path ----
    ax3 = fig.add_subplot(1, 3, 3)
    ax3.set_facecolor(BG)
    half = [(t, c) for t, c in zip(tris, cols) if (t[0][1] + t[1][1] + t[2][1]) / 3 > 0]
    ax3.add_collection(PolyCollection([[(v[0], v[2]) for v in t] for t, _ in half],
                                      facecolors=[shade(t, c, light=(0.2, 0, 1)) for t, c in half],
                                      linewidths=0))
    cup_z0, cup_z1 = labels[0][1], labels[0][2]
    tube_z0, tube_z1 = labels[1][1], labels[1][2]
    sp_z0, sp_z1 = labels[2][1], labels[2][2]
    fun_z0 = labels[3][1]
    r_m = mc.MARBLE_D / 2
    marbles = [(-59, fun_z0 + 114), (49, fun_z0 + 96),                # rolling down the funnel
               (12.5, sp_z1 - 78), (-12.5, sp_z1 - 110),              # riding the spiral gutter
               (0, (tube_z0 + tube_z1) / 2),                          # falling the drop tube
               (-14, cup_z0 + 0.5), (2, cup_z0 + 0.5), (18, cup_z0 + 0.5)]  # landed in the cup
    for x, z in marbles:
        ax3.add_patch(Circle((x, z + r_m), r_m, facecolor=MARBLE, edgecolor="#0d0d10", lw=0.6, zorder=5))
    ax3.set_xlim(-95, 95); ax3.set_ylim(-8, H + 8); ax3.set_aspect("equal"); ax3.set_axis_off()
    ax3.set_title("CUTAWAY — Ø16 marbles on the path", color=DIM, family="monospace", fontsize=11)

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=110, facecolor=BG)
    print(f"{out}  — stack {H:.0f} mm: " + " -> ".join(l for l, *_ in reversed(labels)))


if __name__ == "__main__":
    main()
