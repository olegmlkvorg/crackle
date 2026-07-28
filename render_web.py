#!/usr/bin/env python3
"""Renders for the web-bucket parts -> out/web_*.png. Drawn from the EMITTED gcode
(publish-as-we-go: a diagram that disagrees with the file is worse than none); only the
assembly sheet is a schematic, and it takes every number from web.py's constants."""
import math, os, re, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import FancyArrowPatch, Circle, Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import web as W
import machine

BG, INK, DIM = "#0d0d10", "#f2ede6", "#6b665e"
L1C, L2C, CLIPC, LIFTC = "#8a5a28", "#ff9333", "#ffd24d", "#7fd4ff"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def read_segs(path):
    segs, x, y, z, e = [], 0.0, 0.0, 0.0, 0.0
    for line in open(path):
        if not line.startswith(("G0", "G1")):
            continue
        link = "LINK" in line
        m = dict(re.findall(r"([XYZE])([-\d.]+)", line.split(";")[0]))
        nx = float(m.get("X", x)); ny = float(m.get("Y", y)); nz = float(m.get("Z", z))
        ne = float(m.get("E", e))
        if line.startswith("G1") and "E" in m and ne > e and "PRIME" not in line:
            segs.append(((x, y), (nx, ny), nz, link))
        x, y, z, e = nx, ny, nz, ne
    return segs


def draw(ax, segs, zsel, color, lw, alpha=1.0, link_ok=False):
    ss = [(a, b) for a, b, z, lk in segs if zsel(z) and (link_ok or not lk)]
    if ss:
        ax.add_collection(LineCollection(ss, colors=color, linewidths=lw, alpha=alpha,
                                         capstyle="round"))
    return len(ss)


def style(ax, title):
    ax.set_facecolor(BG)
    ax.set_aspect("equal")
    ax.autoscale()
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    for s in ax.spines.values():
        s.set_color("#26262c")
    ax.tick_params(colors=DIM, labelsize=7)


def note(ax, txt, xy, xytext, color=INK):
    ax.annotate(txt, xy=xy, xytext=xytext, color=color, fontsize=8.5,
                arrowprops=dict(arrowstyle="-", color=DIM, lw=0.8))


def fig1(w=11, h=6):
    f = plt.figure(figsize=(w, h), facecolor=BG)
    return f


# --------------------------------------------------------------- coupon
def render_coupon():
    segs = read_segs(os.path.join(OUT, "web_coupon_k1c_T230.gcode"))
    f = fig1(11, 5)
    ax = f.add_subplot(111)
    draw(ax, segs, lambda z: z <= 0.75, L1C, 3.0, 0.8)
    draw(ax, segs, lambda z: 1.0 < z < 4.7, L2C, 1.2)
    draw(ax, segs, lambda z: z >= 4.7, CLIPC, 1.4)
    ox, oy = 45.0, 100.0
    labels = [
        (16, "V1\nbore 9.0", "too tight\nif inset holds"),
        (36, "V2\nbore 9.9", "the predicted fit\n(stick+0.7 = hole 3.9)"),
        (56, "V3\nbore 10.8", "loose\nif inset holds"),
        (76, "V4\nlobed", "3 contact bumps,\nrelief for the hot bulge"),
        (96, "V5\nsnap 2.9", "lay stick along,\npress down"),
        (118, "V6\nsnap 2.5", "tighter snap"),
    ]
    for sx, name, sub in labels:
        ax.text(ox + sx, oy + 26, name, color=INK, fontsize=9, ha="center", va="bottom")
        ax.text(ox + sx, oy - 6, sub, color=DIM, fontsize=7, ha="center", va="top")
    ax.text(ox, oy - 16.5,
            "READ IT BY THE EDGE NOTCHES: 1 notch = V1 ... 6 notches = V6.\n"
            "Push a real 3.175 stick into V1-V4 (straight down), snap one into V5/V6. "
            "Report each: SNUG / SLIDES / SPLITS / WON'T GO.",
            color=INK, fontsize=9)
    ax.text(ox, oy + 33.5, "FIT COUPON — K1C, pla-matte 230C, ~10 g, ~5 min. "
                           "Every socket in the bucket keys off the winner.",
            color=CLIPC, fontsize=10)
    style(ax, "")
    ax.set_xlim(ox - 6, ox + 136)
    ax.set_ylim(oy - 24, oy + 40)
    f.tight_layout()
    f.savefig(os.path.join(OUT, "web_coupon.png"), dpi=150, facecolor=BG)
    plt.close(f)


# --------------------------------------------------------------- base
def render_base():
    segs = read_segs(os.path.join(OUT, "web_base_k2plus_d200_T230.gcode"))
    f = fig1(14.5, 8.2)
    ax = f.add_subplot(121)
    # pressed layer 1 at its landed width (~12 mm), the 9 band laps bright on top
    draw(ax, segs, lambda z: z <= 0.15, L1C, 6.0, 0.45)
    draw(ax, segs, lambda z: z > 0.55, L2C, 1.5)
    cx = cy = 175.0
    for k in range(12):
        a_ = 2 * math.pi * k / 12
        ax.add_patch(Circle((cx + W.R_STICK * math.cos(a_), cy + W.R_STICK * math.sin(a_)),
                            3.175 / 2, fill=False, color="#b7a184", lw=1.2, ls=":"))
    note(ax, "ONE pressed layer is the whole floor:\nrosette + rim + the band's ground pass",
         (cx + 20, cy - 35), (cx - 40, cy - 150))
    note(ax, "9 single-bead laps of ONE closed line:\n12-lobe wave wall + 12 spring-C\n"
             "sockets, drawn in the same stroke", (cx, cy + 91.3), (cx - 170, cy + 100))
    ax.text(cx - 172, cy - 172, "BASE V4 — K2 Plus, d200, 10 layers, ~18 g, ~4 min.\n"
            "Sticks (dotted) push into the C's.", color=CLIPC, fontsize=10.5)
    style(ax, "")
    ax.set_xlim(cx - 178, cx + 112)
    ax.set_ylim(cy - 178, cy + 126)
    ax.axis("off")
    # pocket close-up, drawn from the same gcode segments, beads at real width
    ax2 = f.add_subplot(122)
    S = (cx + W.R_STICK, cy)
    px_mm = 30.0                     # approx px per mm at this axes size/dpi for lw
    ss = [(a, b) for a, b, z, lk in segs if z > 0.55
          and math.dist(a, S) < 12 and math.dist(b, S) < 12]
    ax2.add_collection(LineCollection(ss, colors=L2C, linewidths=0.065 * px_mm * 2.0,
                                      alpha=0.95, capstyle="round"))
    g1 = [(a, b) for a, b, z, lk in segs if z <= 0.15
          and math.dist(a, S) < 14 and math.dist(b, S) < 14]
    ax2.add_collection(LineCollection(g1, colors=L1C, linewidths=0.065 * px_mm * 12.0,
                                      alpha=0.35, capstyle="round"))
    ax2.add_patch(Circle(S, 3.175 / 2, fill=True, color="#b7a184", alpha=0.95))
    ax2.text(S[0], S[1], "stick\n3.175", color=BG, fontsize=8.5, ha="center", va="center")
    note(ax2, "spring-C: 278 deg of the SAME wall\nline, modelled ID 3.9",
         (S[0] + 2.0, S[1] + 2.2), (S[0] + 3.5, S[1] + 8.5))
    note(ax2, "mouth faces the wall — clip pressure\nseats the stick INTO the C back",
         (S[0] - 2.8, S[1] + 0.5), (S[0] - 11.5, S[1] - 7.5))
    ax2.text(S[0] - 11.5, S[1] + 10.5, "ONE POCKET, TO SCALE — pressed ground under it "
             "is its blind floor", color=INK, fontsize=10)
    ax2.text(S[0] - 11.5, S[1] - 11.7,
             "FIT IS WHAT THIS PRINT TESTS: free single-bead shrink is UNMEASURED.\n"
             "ID 3.9 bets on ~1.0 of it (thick bosses measured ~1.7); the C splays ~±0.4.\n"
             "Loose or split -> one constant (POCKET_RC) moves, 4-min reprint.",
             color=CLIPC, fontsize=9)
    ax2.set_xlim(S[0] - 12, S[0] + 12)
    ax2.set_ylim(S[1] - 12.5, S[1] + 11.5)
    ax2.set_aspect("equal")
    ax2.set_facecolor(BG)
    ax2.axis("off")
    f.tight_layout()
    f.savefig(os.path.join(OUT, "web_base.png"), dpi=150, facecolor=BG)
    plt.close(f)


# --------------------------------------------------------------- panel
def render_panel(n):
    segs = read_segs(os.path.join(OUT, f"web_panel{n}_k2plus_w295_h178_T230.gcode"))
    f = fig1(13, 8.6)
    ax = f.add_subplot(111)
    # layer 1 at its LANDED width: full flow pressed to 0.1 spreads to ~12 mm — the
    # ground ribbons really are this fat, and the render says so
    draw(ax, segs, lambda z: z <= 0.15, L1C, 9.0, 0.5)
    draw(ax, segs, lambda z: 0.15 < z <= 0.72, L2C, 1.3)
    n_lift = draw(ax, segs, lambda z: 0.72 < z < 1.2, LIFTC, 1.3)
    draw(ax, segs, lambda z: z >= 1.25, CLIPC, 1.6)
    ox = (350 - 295.4) / 2
    oy = (350 - 177.6) / 2
    pitch = W.stick_pitch()
    for i in range(6):
        ax.plot([ox + 10 + i * pitch] * 2, [oy - 4, oy + 181.6], color="#3d3a35",
                lw=1.0, ls=":")
    ax.text(ox + 10, oy + 184, "bamboo stick lines (sticks stand INSIDE, panel wraps on them)",
            color=DIM, fontsize=8)
    note(ax, "pressed ground ribbons, ~12 mm landed:\nthe web's warp + every clip's foundation",
         (ox + 10 + 2 * pitch, oy + 60), (ox + 40, oy - 26))
    note(ax, f"the NET: ONE closed 5:8 lissajous loop (the floor rose's\nFibonacci family), "
             f"drawn in a single unbroken stroke; where\nstrands cross, the later RIDES the "
             f"earlier ({n_lift} lifted\nsegments, light blue) — weld pools, not point kisses",
         (ox + 150, oy + 100), (ox + 158, oy - 26))
    note(ax, "snap channels (3 per stick line):\ntwo rails + snap lip, printed\nlayer-by-layer "
             "with lifted hops", (ox + 10 + 3 * pitch + 3.15, oy + 88.8), (ox + 226, oy + 186))
    ax.text(ox - 8, oy - 38, f"WEB PANEL {n}/2 — K2 Plus, 295x178, 2-layer web + 4.8 mm "
            f"clips, ~28 g, ~7 min. Print 2; the net pattern differs per panel.",
            color=CLIPC, fontsize=10.5)
    style(ax, "")
    ax.set_xlim(ox - 12, ox + 308)
    ax.set_ylim(oy - 42, oy + 196)
    f.tight_layout()
    f.savefig(os.path.join(OUT, f"web_panel{n}.png"), dpi=150, facecolor=BG)
    plt.close(f)


# --------------------------------------------------------------- net v2 (go/no-go)
def render_net2():
    """Both panels side by side: the redesigned holistic net, drawn from the emitted
    gcode. This image is the client's go/no-go on the new net."""
    f = fig1(15, 6.6)
    ox = (350 - 295.4) / 2
    oy = (350 - 177.6) / 2
    pitch = W.stick_pitch()
    sub = [
        "PANEL 1 — the crisp weave (delta = 2pi/5)",
        "PANEL 2 — its mirror, drawn with a breathing envelope",
    ]
    for n in (1, 2):
        segs = read_segs(os.path.join(OUT, f"web_panel{n}_k2plus_w295_h178_T230.gcode"))
        ax = f.add_subplot(1, 2, n)
        draw(ax, segs, lambda z: z <= 0.15, L1C, 6.5, 0.4)
        draw(ax, segs, lambda z: 0.15 < z <= 0.72, L2C, 1.5)
        draw(ax, segs, lambda z: 0.72 < z < 1.2, LIFTC, 1.4)
        for i in range(6):
            ax.plot([ox + 10 + i * pitch] * 2, [oy - 3, oy + 180.6], color="#4a463f",
                    lw=1.0, ls=":")
        ax.text(ox, oy + 184, sub[n - 1], color=INK, fontsize=11)
        style(ax, "")
        ax.set_xlim(ox - 8, ox + 303)
        ax.set_ylim(oy - 8, oy + 194)
        ax.axis("off")
    f.text(0.035, 0.155,
           "THE NET, REDESIGNED — one closed Lissajous loop per panel: x = sin(5t), "
           "y = sin(8t+d). 5:8 is the pair below the floor rose's 13:8 in the same\n"
           "Fibonacci run — the wall is drawn from the floor's own numbers, in ONE "
           "unbroken stroke with no gap-closes. The 6 stick lines (dotted) are\n"
           "crossed in passing, 10 times each; every stick keeps at least 2 of its 3 "
           "clips directly net-welded (16/18 and 14/18 zones, measured); every\n"
           "turnaround lands on pressed ground (x-hairpins on the frame ribbon, "
           "y-envelope kissing the outer clip hoops).",
           color=INK, fontsize=9.5, va="top")
    f.text(0.035, 0.035,
           "K2 Plus, 2.0x0.6 bead @ 50 mm/s = 60 mm3/s. Net 3.87 / 3.78 m; whole "
           "panel ~27 g, ~7 min each. Light blue = lifted ride-over welds. NOT PRINTED YET.",
           color=CLIPC, fontsize=9.5, va="top")
    f.tight_layout(rect=(0, 0.17, 1, 1.0))
    f.savefig(os.path.join(OUT, "web_net2.png"), dpi=150, facecolor=BG)
    plt.close(f)


# --------------------------------------------------------------- topper
def render_topper():
    segs = read_segs(os.path.join(OUT, "web_topper_k2plus_T230.gcode"))
    f = fig1(9.5, 9.5)
    ax = f.add_subplot(111)
    draw(ax, segs, lambda z: z <= 1.35, L1C, 1.0, 0.6)
    draw(ax, segs, lambda z: z > 1.35, L2C, 1.4)
    cx = cy = 175.0
    note(ax, "the COIL: each cap layer is ONE\nunbroken spiral, no seams",
         (cx + 60, cy + 60), (cx + 102, cy + 122))
    note(ax, "9 single-bead laps of the SAME wave +\nspring-C line as the base; the 12 C's\n"
             "open DOWNWARD after the flip and\nswallow the stick tops",
         (cx + W.R_STICK, cy), (cx + 98, cy - 128))
    ax.text(cx - 132, cy - 138, "TOPPER V4 — K2 Plus, ~31 g, ~7 min. PRINTED FACE-DOWN:\n"
            "flip it over at assembly; the pressed spiral face becomes the rim's top.",
            color=CLIPC, fontsize=10)
    style(ax, "")
    f.tight_layout()
    f.savefig(os.path.join(OUT, "web_topper.png"), dpi=150, facecolor=BG)
    plt.close(f)


# --------------------------------------------------------------- assembly (schematic)
def render_assembly():
    # V4 stack: 10-layer base (1 floor + 9 band laps), 12-layer topper (3 cap + 9
    # pocket laps). Panels stay the delivered 295x178 pending the height decision,
    # so the drum sums to ~190, not the original 200 — stated on the sheet.
    band_top = machine.PRESS_HARD + 9 * 0.6                  # 5.5
    topper_t = machine.PRESS_HARD + (W.CAP_LAYERS + 9 - 1) * 0.6   # 6.7
    H = 177.6
    R = 100.0
    f = fig1(12, 8)
    ax = f.add_subplot(121)
    ax.set_facecolor(BG)
    # side elevation
    ax.add_patch(Rectangle((-R, 0), 2 * R, 2.5, color=L1C))                     # floor
    for sx in (-W.R_STICK, -W.R_STICK / 3, W.R_STICK / 3, W.R_STICK):           # sticks
        ax.plot([sx, sx], [0.7, 0.7 + 187], color="#b7a184", lw=3)
    ax.add_patch(Rectangle((-R, 2.5), 2 * R, band_top - 2.5, color=L2C, alpha=0.85))
    ax.add_patch(Rectangle((-W.wrap_radius() - 1, band_top), 2, H, color=L2C))  # walls
    ax.add_patch(Rectangle((W.wrap_radius() - 1, band_top), 2, H, color=L2C))
    for yy in [band_top + fr * H for fr in W.BAND_Y_FRAC]:                      # clips
        for sx in (-W.wrap_radius(), W.wrap_radius()):
            ax.add_patch(Rectangle((sx - 2.4 * (1 if sx < 0 else 1) - (2.4 if sx < 0 else -0.0),
                                    yy - 6), 2.4, 12, color=CLIPC))
    ax.add_patch(Rectangle((-101, band_top + H), 202, topper_t, color=L2C, alpha=0.9))
    for txt, y in [("1  BASE down, 12 sticks into its spring-C's", 8),
                   (f"2  wrap WEB 1, snap its channels onto 6 sticks", band_top + 0.25 * H),
                   ("3  wrap WEB 2 the same on the other 6", band_top + 0.55 * H),
                   ("4  press the TOPPER onto the stick tops;\n    its pocket ring seats on the panels' rim",
                    band_top + H + 2)]:
        ax.text(108, y, txt, color=INK, fontsize=9.5, va="center")
    ax.text(-100, 214, "ASSEMBLY V4 — drum d200 x ~190. Sticks: 12 x 1/8\" bamboo, "
            "CUT ~187 (recut after fit).", color=CLIPC, fontsize=11)
    ax.text(-100, -22, "stick grip: base 5.4 + 3 panel clips + topper 4.2 engaged "
            "(5.4 deep, 1.2 float)   |   V4 stack sums ~190, not the original 200:\n"
            "panels stay the delivered 295x178 pending the height decision — "
            "regenerating them at 295x188 restores the 200 (one command)",
            color=DIM, fontsize=8.5)
    ax.set_xlim(-115, 235); ax.set_ylim(-30, 222)
    ax.set_aspect("equal"); ax.axis("off")
    # top view: stick circle + clip detail
    ax2 = f.add_subplot(122)
    ax2.set_facecolor(BG)
    ax2.add_patch(Circle((0, 0), 100, fill=False, color=L1C, lw=2))
    ax2.add_patch(Circle((0, 0), W.wrap_radius(), fill=False, color=L2C, lw=2.4))
    for k in range(12):
        a_ = 2 * math.pi * k / 12
        ax2.add_patch(Circle((W.R_STICK * math.cos(a_), W.R_STICK * math.sin(a_)),
                             1.6, color="#b7a184"))
    ax2.annotate("floor edge d200", xy=(0, -100), xytext=(-38, -119), color=DIM,
                 fontsize=8.5, arrowprops=dict(arrowstyle="-", color=DIM, lw=0.8))
    ax2.annotate("web drum d185 on the stick faces", xy=(W.wrap_radius(), 0),
                 xytext=(18, 110), color=DIM, fontsize=8.5,
                 arrowprops=dict(arrowstyle="-", color=DIM, lw=0.8))
    # clip cross-section inset, drawn to scale (s px/mm) from the commanded numbers
    ix, iy, s = 0.0, -34.0, 6.0
    cav, mouth, bead, stick = 4.3, 2.9, 2.0, 3.175
    ax2.text(ix - 30, iy + 40, "clip cross-section (per stick line):", color=INK, fontsize=9)
    ax2.add_patch(Rectangle((ix - 30, iy), 60, 0.7 * s, color=L1C))
    for sgn in (-1, 1):
        xf = sgn * cav / 2 * s                        # rail inner face
        rail_x = min(xf, xf + sgn * bead * s)
        ax2.add_patch(Rectangle((rail_x, iy + 0.7 * s), bead * s, 3.6 * s, color=CLIPC))
        lip_x = min(sgn * mouth / 2 * s, sgn * mouth / 2 * s + sgn * bead * s)
        ax2.add_patch(Rectangle((lip_x, iy + (0.7 + 3.6) * s), bead * s, 1.2 * s,
                                color=CLIPC))
    ax2.add_patch(Circle((ix, iy + 0.7 * s + stick / 2 * s), stick / 2 * s,
                         color="#b7a184"))
    ax2.text(ix + 24, iy + 10, "cavity 4.3\nmouth 2.9\n(coupon decides)", color=DIM,
             fontsize=8)
    ax2.set_xlim(-125, 125); ax2.set_ylim(-125, 125)
    ax2.set_aspect("equal"); ax2.axis("off")
    f.tight_layout()
    f.savefig(os.path.join(OUT, "web_assembly.png"), dpi=150, facecolor=BG)
    plt.close(f)


if __name__ == "__main__":
    render_coupon(); print("out/web_coupon.png")
    render_base(); print("out/web_base.png")
    render_panel(1); print("out/web_panel1.png")
    render_panel(2); print("out/web_panel2.png")
    render_net2(); print("out/web_net2.png")
    render_topper(); print("out/web_topper.png")
    render_assembly(); print("out/web_assembly.png")
