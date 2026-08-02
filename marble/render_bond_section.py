#!/usr/bin/env python3
"""render_bond_section.py — BOND v2 joint section + one re-rendered part, FROM THE EMITTED STLs.

Panel 1: the mated joint in section (male spigot seated in the female socket), walls drawn as
LINE_W bands around the MEASURED surface paths (bond_check ring extraction — not the design
formulas). Panel 2: zoom on the detent. Panel 3: the measured face-clearance profile.
Second image: drop_tube.stl re-rendered (iso + front) from the same emitted mesh.

Usage: python3 render_bond_section.py
Outputs: bond_section.png, drop_tube_render.png
"""
import math, struct

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

import marble_common as mc
from bond_check import read_verts, rings, interp

BG, INK, DIM = "#0d0d10", "#f2ede6", "#6b665e"
MALE_C, FEM_C = "#f2a03d", "#c2571a"
W2 = mc.LINE_W / 2


def band(ax, prof, color, sign=1, label=None, alpha=0.95):
    """Wall band: LINE_W wide, centred on the measured path. sign=-1 mirrors to the left side."""
    zs = [z for z, _ in prof]
    inner = [sign * (r - W2) for _, r in prof]
    outer = [sign * (r + W2) for _, r in prof]
    ax.fill_betweenx(zs, inner, outer, color=color, alpha=alpha, lw=0, label=label)


def main():
    male = rings(read_verts("drop_tube.stl"), 0.0, mc.COUPLE_L)
    cupv = read_verts("catch_cup.stl")
    ztop = max(v[2] for v in cupv)
    fem = [(z - (ztop - mc.COUPLE_L), r) for z, r in rings(cupv, ztop - mc.COUPLE_L, ztop)]

    ds = [i * 0.1 for i in range(161)]
    clear = [interp(fem, d) - interp(male, d) - mc.LINE_W for d in ds]

    fig = plt.figure(figsize=(14, 10), facecolor=BG)
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.5])
    ax = fig.add_subplot(gs[0, :])
    axz = fig.add_subplot(gs[1, 0])
    axc = fig.add_subplot(gs[1, 1])
    fig.suptitle("BOND v2 — friction seat + snap detent (kit coupling, marble_common)\n"
                 "profiles MEASURED off the emitted STLs (drop_tube spigot in catch_cup socket) — "
                 "geometry gated, printed fit UNTESTED",
                 color=INK, family="monospace", fontsize=12)

    # ---- panel 1: full mated joint, both sides ----
    ax.set_facecolor(BG)
    for s in (1, -1):
        band(ax, fem, FEM_C, s, "female socket wall" if s == 1 else None)
        band(ax, male, MALE_C, s, "male spigot wall" if s == 1 else None)
    ax.axhline(mc.COUPLE_L, color=DIM, lw=0.6, ls=":")
    ax.annotate("female rim", xy=(0, mc.COUPLE_L + 0.7), color=DIM, family="monospace",
                fontsize=8, ha="center")
    ax.annotate("marble path stays open (>= O%g)" % mc.BORE_D, xy=(0, 4), color=DIM,
                family="monospace", fontsize=8, ha="center")
    ax.annotate("detent", xy=(-interp(male, mc.BUMP_Z) - W2, mc.BUMP_Z), xytext=(-16, 8),
                color=INK, family="monospace", fontsize=8,
                arrowprops=dict(arrowstyle="->", color=INK, lw=0.8))
    ax.set_xlim(-36, 36); ax.set_ylim(-2.5, 19)
    ax.set_aspect("equal")
    ax.tick_params(colors=DIM, labelsize=8)
    for sp in ax.spines.values(): sp.set_color(DIM)
    ax.set_title("MATED JOINT, SECTION (mm)", color=DIM, family="monospace", fontsize=10)
    ax.legend(loc="center", fontsize=8, facecolor=BG, edgecolor=DIM,
              labelcolor=INK, prop={"family": "monospace"})

    # ---- panel 2: zoom on the detent + seat ----
    axz.set_facecolor(BG)
    band(axz, fem, FEM_C, 1, alpha=0.95)
    band(axz, male, MALE_C, 1, alpha=0.95)
    axz.annotate("bump +%.2f\n(male)" % mc.BUMP_H, xy=(interp(male, mc.BUMP_Z) + W2, mc.BUMP_Z),
                 xytext=(23.2, 3.0), color=INK, family="monospace", fontsize=9,
                 arrowprops=dict(arrowstyle="->", color=INK, lw=0.8))
    axz.annotate("groove +%.2f\n(female)" % mc.GROOVE_H, xy=(interp(fem, mc.BUMP_Z) + W2, mc.BUMP_Z),
                 xytext=(30.2, 6.5), color=INK, family="monospace", fontsize=9,
                 arrowprops=dict(arrowstyle="->", color=INK, lw=0.8))
    axz.annotate("seat gap %.2f" % clear[5], xy=(interp(male, 0.5) + W2, 0.5),
                 xytext=(23.2, -1.2), color=INK, family="monospace", fontsize=9,
                 arrowprops=dict(arrowstyle="->", color=INK, lw=0.8))
    axz.annotate("net snap %.2f:\nbump %.2f - seat %.2f\n(two springy %.1f\n walls flex)"
                 % (mc.BUMP_H - clear[5], mc.BUMP_H, clear[5], mc.LINE_W),
                 xy=(22.9, 12.2), color=INK, family="monospace", fontsize=8,
                 bbox=dict(facecolor=BG, alpha=0.8, edgecolor="none"))
    axz.set_xlim(22.5, 33.5); axz.set_ylim(-2, 17)
    axz.set_aspect("equal")
    axz.tick_params(colors=DIM, labelsize=8)
    for sp in axz.spines.values(): sp.set_color(DIM)
    axz.set_title("DETENT + SEAT (zoom, mm)", color=DIM, family="monospace", fontsize=10)

    # ---- panel 3: measured clearance profile ----
    axc.set_facecolor(BG)
    axc.plot(clear, ds, color=INK, lw=1.6)
    axc.axvspan(0.10, 0.15, color=MALE_C, alpha=0.18)
    axc.annotate("seat band\n0.10-0.15", xy=(0.125, 15.2), color=MALE_C, family="monospace",
                 fontsize=8, ha="center")
    axc.annotate("detent zone:\ngroove over bump", xy=(0.30, mc.BUMP_Z), color=DIM,
                 family="monospace", fontsize=8)
    axc.annotate("entry %.2f" % clear[-1], xy=(clear[-1] - 0.03, 14.4), color=INK,
                 family="monospace", fontsize=8, ha="right")
    axc.set_xlim(0, 0.6); axc.set_ylim(-2, 17)
    axc.set_xlabel("face clearance (mm)", color=DIM, family="monospace", fontsize=9)
    axc.set_ylabel("engagement above full seat (mm)", color=DIM, family="monospace", fontsize=9)
    axc.tick_params(colors=DIM, labelsize=8)
    for sp in axc.spines.values(): sp.set_color(DIM)
    axc.set_title("MEASURED CLEARANCE", color=DIM, family="monospace", fontsize=10)

    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig("bond_section.png", dpi=130, facecolor=BG)
    plt.close(fig)
    print("bond_section.png — male %d rings, female %d rings, seat %.3f entry %.3f snap %.3f"
          % (len(male), len(fem), clear[5], clear[-1], mc.BUMP_H - clear[5]))

    # ---- second image: re-render drop_tube from the emitted mesh ----
    from render_marble_run import read_stl, shade
    tris = read_stl("drop_tube.stl")
    H = max(v[2] for t in tris for v in t)
    fig = plt.figure(figsize=(10, 8), facecolor=BG)
    fig.suptitle("DROP TUBE — BOND v2 ends (bump at the spigot, groove in the socket)\n"
                 "render of the emitted drop_tube.stl — not yet printed",
                 color=INK, family="monospace", fontsize=11)
    a3 = fig.add_subplot(1, 2, 1, projection="3d")
    a3.set_facecolor(BG)
    tint = (0.95, 0.62, 0.25)
    a3.add_collection3d(Poly3DCollection(tris, facecolors=[shade(t, tint) for t in tris],
                                         linewidths=0))
    a3.set_xlim(-62, 62); a3.set_ylim(-62, 62); a3.set_zlim(0, H)
    a3.set_box_aspect((124 / H, 124 / H, 1), zoom=1.3)
    a3.view_init(elev=10, azim=-55); a3.set_axis_off()
    a3.set_title("ISO", color=DIM, family="monospace", fontsize=10)
    a2 = fig.add_subplot(1, 2, 2)
    a2.set_facecolor(BG)
    a2.add_collection(PolyCollection([[(v[0], v[2]) for v in t] for t in tris],
                                     facecolors=[shade(t, tint, light=(0, 0, 1)) for t in tris],
                                     linewidths=0))
    a2.annotate("socket + groove", xy=(31, H - 8), color=INK, family="monospace", fontsize=9)
    a2.annotate("spigot + bump", xy=(31, 4), color=INK, family="monospace", fontsize=9)
    a2.set_xlim(-64, 96); a2.set_ylim(-6, H + 6)
    a2.set_aspect("equal"); a2.set_axis_off()
    a2.set_title("FRONT", color=DIM, family="monospace", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig("drop_tube_render.png", dpi=130, facecolor=BG)
    print("drop_tube_render.png — %d tris, %.0f mm tall" % (len(tris), H))


if __name__ == "__main__":
    main()
