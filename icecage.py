#!/usr/bin/env python3
"""icecage.py -- the corrugated ice cage. Emits a BINARY STL for slicer VASE mode.

WHAT IT IS. A tall open-topped vessel whose wall is a single 0.8 mm extrusion, corrugated into
12 lobes in plan. Water freezes inside, expands about 9% by volume, and instead of hoop-stretching
the PLA (which would crack it) the lobes UNFOLD toward a circle. Unfolding is pure bending: the
centreline length never changes, so the wall reaches the expanded volume at zero membrane strain
and only then starts carrying hoop tension. A ferment gas load is the same load, much weaker, so
the same part covers it.

WHY CORRUGATED AND NOT A GRID. Judged against stacked hoops, a tri-grid, a diagrid and an ideal
pure hoop on grams-per-MPa of burst pressure. Corrugated won at 958 g/MPa, 1.64x the second place,
because the unfold buys the expansion for free and the wall then carries hoop along PLA's STRONG
axis (in-plane extrusion), never across layer lines.

WHY THE STL IS A SOLID AND NOT AN 0.8 SHELL. The deciding tie-breaker was that this prints as ONE
continuous vase-mode spiral -- no seam, no travel, 0 deg overhang. Spiralize needs a single
non-hollow region per layer, so the slicer's input is the SOLID whose surface is the wall's OUTER
face. Vase mode then insets by half a line width and lays the bead exactly on the design
centreline r(theta). Modelling a hollow 0.8 shell would hand the slicer an annulus and lose vase
mode, which is the whole reason this topology won.

Every number this prints is MEASURED back off the emitted file, never carried from the design
variables (house lesson: a summary line is not the file).

    python3 icecage.py                       # judged defaults -> icecage.stl
    python3 icecage.py --id 180 --height 220 --solve-expand 9
"""
import argparse
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import machine   # noqa: E402  -- the single source of truth for machine constants

FIL_D = 1.75                 # mm, filament this project feeds
FIL_A = math.pi * (FIL_D / 2.0) ** 2
PLA_DENSITY = 1.24           # g/cm3, the house figure (belt.py:455, rotunda.py:422, +13 others)


# ---------------------------------------------------------------------------------------------
# GEOMETRY
# ---------------------------------------------------------------------------------------------
def centre_r(theta, rm, amp, lobes):
    """Radius of the BEAD CENTRELINE at theta. This is the curve the extrusion follows."""
    return rm + amp * math.cos(lobes * theta)


def centre_perimeter(rm, amp, lobes, steps=200000):
    """Arc length of the centreline curve, by direct integration of sqrt(r^2 + r'^2)."""
    total = 0.0
    dth = 2.0 * math.pi / steps
    for i in range(steps):
        th = i * dth
        r = rm + amp * math.cos(lobes * th)
        rp = -amp * lobes * math.sin(lobes * th)
        total += math.hypot(r, rp) * dth
    return total


def solve_amp(rm, lobes, expand_pct, lo=0.0, hi=None):
    """Amplitude whose centreline perimeter unfolds to exactly `expand_pct` more enclosed area.

    Unfolding conserves arc length, so the unfolded radius is P/(2*pi) and the volume gain is
    (P / (2*pi*rm))^2 - 1. Monotone in amp, so bisect.
    """
    want = math.sqrt(1.0 + expand_pct / 100.0) * 2.0 * math.pi * rm
    if hi is None:
        hi = rm * 0.5
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if centre_perimeter(rm, mid, lobes, steps=20000) < want:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def build_mesh(rm, amp, lobes, wall, height, samples):
    """Triangles of the slicer-vase input solid: corrugated prism, flat cap top and bottom.

    The side surface is the wall's OUTER face: the design centreline offset outward by wall/2
    along its own NORMAL, not along the radius. That distinction is not cosmetic -- a radial
    offset leaves a wall of thickness wall*cos(phi) where tan(phi) = r'/r, and on this profile
    r' peaks at amp*lobes = 52.4 against r ~ 125, so phi reaches 22.7 deg and the flanks would
    come out 0.738 mm instead of 0.800. A parallel offset also makes the slicer's own inward
    half-width inset land the bead exactly on the design centreline.

    Perfectly vertical, so every side facet has nz = 0 and there is no overhang anywhere.
    """
    if samples % lobes:
        samples += lobes - (samples % lobes)   # whole lobes, so every crest is sampled alike
    ring = []
    d = wall / 2.0
    for i in range(samples):
        th = 2.0 * math.pi * i / samples
        r = centre_r(th, rm, amp, lobes)
        rp = -amp * lobes * math.sin(lobes * th)
        cx, cy = r * math.cos(th), r * math.sin(th)
        tx = rp * math.cos(th) - r * math.sin(th)          # dc/dtheta
        ty = rp * math.sin(th) + r * math.cos(th)
        tl = math.hypot(tx, ty)
        ring.append((cx + d * ty / tl, cy - d * tx / tl))  # (ty,-tx)/|t| points outward

    tris = []
    c_bot = (0.0, 0.0, 0.0)
    c_top = (0.0, 0.0, height)
    for i in range(samples):
        j = (i + 1) % samples
        bi = (ring[i][0], ring[i][1], 0.0)
        bj = (ring[j][0], ring[j][1], 0.0)
        ti = (ring[i][0], ring[i][1], height)
        tj = (ring[j][0], ring[j][1], height)
        tris.append((c_bot, bj, bi))    # bottom cap, normal -z
        tris.append((c_top, ti, tj))    # top cap, normal +z
        tris.append((bi, bj, tj))       # side, normal radially out
        tris.append((bi, tj, ti))
    return tris, samples


def normal(a, b, c):
    e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    n = (e1[1] * e2[2] - e1[2] * e2[1],
         e1[2] * e2[0] - e1[0] * e2[2],
         e1[0] * e2[1] - e1[1] * e2[0])
    m = math.sqrt(sum(v * v for v in n))
    return (0.0, 0.0, 0.0) if m < 1e-12 else (n[0] / m, n[1] / m, n[2] / m)


def write_binary_stl(path, tris):
    """LAW: filesize == 84 + 50*ntris. 80-byte header that does NOT start b'solid'."""
    with open(path, "wb") as f:
        f.write(b"icecage corrugated vase-mode solid".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            nx, ny, nz = normal(a, b, c)
            f.write(struct.pack("<12fH", nx, ny, nz,
                                a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2], 0))


# ---------------------------------------------------------------------------------------------
# MEASUREMENT -- everything below reads the EMITTED FILE back. Nothing is taken on trust.
# ---------------------------------------------------------------------------------------------
def measure(path, wall, layer, speed):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.read(80)
        (ntris,) = struct.unpack("<I", f.read(4))
        body = f.read()
    law_ok = size == 84 + 50 * ntris

    verts_bot = {}
    cap_area = 0.0
    minz = float("inf")
    maxz = float("-inf")
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for rec in struct.iter_unpack("<12fH", body):
        p = [rec[3:6], rec[6:9], rec[9:12]]
        for x, y, z in p:
            minz = min(minz, z); maxz = max(maxz, z)
            minx = min(minx, x); maxx = max(maxx, x)
            miny = min(miny, y); maxy = max(maxy, y)
        if all(abs(v[2]) < 1e-9 for v in p):
            e1 = (p[1][0] - p[0][0], p[1][1] - p[0][1])
            e2 = (p[2][0] - p[0][0], p[2][1] - p[0][1])
            cap_area += abs(e1[0] * e2[1] - e1[1] * e2[0]) / 2.0
            for x, y, z in p:
                if abs(x) > 1e-9 or abs(y) > 1e-9:
                    verts_bot[(round(x, 6), round(y, 6))] = (x, y)

    pts = sorted(verts_bot.values(), key=lambda q: math.atan2(q[1], q[0]))
    p_outer = 0.0
    area_outer = 0.0
    r_sum = 0.0
    for i, q in enumerate(pts):
        r = pts[(i + 1) % len(pts)]
        p_outer += math.hypot(r[0] - q[0], r[1] - q[1])
        area_outer += q[0] * r[1] - r[0] * q[1]          # shoelace, measured off the ring
        r_sum += math.hypot(q[0], q[1])
    area_outer = abs(area_outer) / 2.0
    r_mean_outer = r_sum / len(pts)

    # Discrete curvature of the measured outer polygon: circumradius of a 3-point stencil spread
    # over ~1.5 mm of arc. NOT the immediate neighbours: STL vertices are float32, so at 130 mm
    # radius a coordinate carries ~1e-5 mm of quantisation, and the sagitta of a 0.14 mm chord on
    # a 22 mm radius is only 4e-4 mm. Measured: shrinking the stencil made the answer WORSE, not
    # better (1.520 -> 1.528 -> 1.544% as samples went 1440 -> 2880 -> 5760), which is noise
    # diverging, not convergence. 1.5 mm keeps the sagitta ~100x the quantisation.
    step = max(1, int(round(1.5 / (p_outer / len(pts)))))
    k_out_max = 0.0
    for i in range(len(pts)):
        a = pts[(i - step) % len(pts)]
        b = pts[i]
        c = pts[(i + step) % len(pts)]
        ab = math.hypot(b[0] - a[0], b[1] - a[1])
        bc = math.hypot(c[0] - b[0], c[1] - b[1])
        ca = math.hypot(a[0] - c[0], a[1] - c[1])
        cross = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        if cross > 1e-12:
            k_out_max = max(k_out_max, 2.0 * cross / (ab * bc * ca))

    # CENTRELINE from the measured OUTER contour, by two exact conversions:
    #   length    Steiner: an inward parallel offset by d shortens a simple closed curve of
    #             rotation index 1 by exactly 2*pi*d. Valid while d stays under the smallest
    #             CONCAVE radius of curvature, which this part checks and prints below.
    #   curvature outward offset d maps k -> k/(1 + d*k), so inward is k_c = k_out/(1 - d*k_out).
    d = wall / 2.0
    p_centre = p_outer - 2.0 * math.pi * d
    k_centre_max = k_out_max / (1.0 - d * k_out_max)

    r_unfold = p_centre / (2.0 * math.pi)             # centreline radius once the lobes open
    r_mean = r_mean_outer - d                         # mean of |r|, a shape descriptor only

    # Steiner again, for AREA this time: an inward parallel offset by t takes a simple closed
    # curve's enclosed area to A - P*t + pi*t^2. Outer contour -> centreline (t = wall/2) and
    # outer contour -> inner contour (t = wall).
    area_centre = area_outer - p_outer * d + math.pi * d * d
    area_inner = area_outer - p_outer * wall + math.pi * wall * wall
    r_eq = math.sqrt(area_centre / math.pi)           # circle of the SAME enclosed area

    # THE ISOPERIMETRIC SURPLUS: how much longer the centreline is than the circle enclosing the
    # same area today. Its two inputs come off the mesh by DIFFERENT routes -- perimeter from a
    # sum of chord lengths, area from a shoelace -- so this is not a number checked against itself.
    surplus = p_centre / (2.0 * math.pi * r_eq) - 1.0
    gain_centreline = (r_unfold / r_eq) ** 2 - 1.0

    # THE HONEST EXPANSION FIGURE is the CONTENTS' volume, so it is the INNER contour that counts.
    area_unfold = math.pi * (r_unfold - d) ** 2
    vol_gain = area_unfold / area_inner - 1.0

    # Crest strain on unfolding: outer fibre of a wall of thickness `wall` bent from the crest
    # curvature to the unfolded circle. eps = (wall/2) * (k_crest - 1/r_unfold).
    crest_strain = d * (k_centre_max - 1.0 / r_unfold)

    n_layers = int(round((maxz - minz) / layer))
    wall_path = p_centre * n_layers
    wall_vol = wall_path * wall * layer
    base_vol = cap_area * layer                        # one solid layer, metered by area
    base_path = base_vol / (wall * layer)
    total_vol = wall_vol + base_vol
    grams = total_vol * PLA_DENSITY / 1000.0
    fil_len = total_vol / FIL_A
    seconds = (wall_path + base_path) / speed
    flow = wall * layer * speed

    return dict(size=size, ntris=ntris, law_ok=law_ok, p_outer=p_outer, p_centre=p_centre,
                r_mean=r_mean, r_unfold=r_unfold, vol_gain=vol_gain, k_centre_max=k_centre_max,
                surplus=surplus, gain_centreline=gain_centreline, area_inner=area_inner,
                r_eq=r_eq, area_outer=area_outer, stencil=step,
                crest_strain=crest_strain, cap_area=cap_area, n_layers=n_layers,
                wall_path=wall_path, wall_vol=wall_vol, base_vol=base_vol, base_path=base_path,
                total_vol=total_vol, grams=grams, fil_len=fil_len, seconds=seconds, flow=flow,
                bbox=(maxx - minx, maxy - miny, maxz - minz), nring=len(pts))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", type=float, default=250.0,
                    help="nominal INNER diameter at the lobe mean, mm (default 250)")
    ap.add_argument("--height", type=float, default=300.0, help="wall height, mm (default 300)")
    ap.add_argument("--wall", type=float, default=0.8,
                    help="single-extrusion wall width, mm (default 0.8, Oleg's spec)")
    ap.add_argument("--lobes", type=int, default=12, help="corrugation count N (default 12)")
    ap.add_argument("--amp", type=float, default=4.37,
                    help="corrugation amplitude A, mm (default 4.37, the judged value)")
    ap.add_argument("--solve-expand", type=float, default=None, metavar="PCT",
                    help="ignore --amp and solve A for this volumetric expansion, %% (ice is ~9)")
    ap.add_argument("--layer", type=float, default=0.4,
                    help="layer height, mm (default 0.4, the repo's proven 2:1 width:height)")
    ap.add_argument("--samples", type=int, default=1440, help="points per ring (default 1440)")
    ap.add_argument("--speed", type=float, default=machine.DEFAULT_SPEED,
                    help="print speed, mm/s (default = machine north star)")
    ap.add_argument("--out", default=None, help="output STL (default icecage.stl beside this file)")
    a = ap.parse_args()

    rm = (a.id + a.wall) / 2.0
    amp = solve_amp(rm, a.lobes, a.solve_expand) if a.solve_expand is not None else a.amp
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "icecage.stl")

    tris, samples = build_mesh(rm, amp, a.lobes, a.wall, a.height, a.samples)
    write_binary_stl(out, tris)
    m = measure(out, a.wall, a.layer, a.speed)

    # Smallest CONCAVE radius of curvature, which is what bounds the parallel offset. Computed
    # from the analytic profile because the mesh only carries the outer face.
    kmin = min((rm + amp * math.cos(a.lobes * t)) ** 2
               + 2.0 * (amp * a.lobes * math.sin(a.lobes * t)) ** 2
               - (rm + amp * math.cos(a.lobes * t)) * (-amp * a.lobes ** 2 * math.cos(a.lobes * t))
               for t in [2 * math.pi * i / 20000 for i in range(20000)])
    kmin_norm = min(((rm + amp * math.cos(a.lobes * t)) ** 2
                     + (amp * a.lobes * math.sin(a.lobes * t)) ** 2) ** 1.5
                    for t in [2 * math.pi * i / 20000 for i in range(20000)])
    r_concave = abs(kmin_norm / kmin) if kmin else float("inf")

    print("icecage -- corrugated single-line ice cage")
    print("  DESIGN   ID %.1f  H %.1f  wall %.2f  lobes %d  amp %.3f  layer %.2f  %d samples"
          % (a.id, a.height, a.wall, a.lobes, amp, a.layer, samples))
    print()
    print("  MEASURED OFF %s" % os.path.basename(out))
    print("    LAW            %d bytes == 84 + 50*%d  -> %s"
          % (m["size"], m["ntris"], "OK" if m["law_ok"] else "BROKEN"))
    print("    bbox           %.2f x %.2f x %.2f mm (plate %.0f x %.0f)"
          % (m["bbox"][0], m["bbox"][1], m["bbox"][2], *machine.BED["k2plus"]))
    print("    outer contour  %.3f mm over %d ring points" % (m["p_outer"], m["nring"]))
    print("    centreline     %.3f mm   (outer - 2*pi*%.2f, Steiner; concave Rc %.1f mm >> %.2f)"
          % (m["p_centre"], a.wall / 2.0, r_concave, a.wall / 2.0))
    print("    mean radius    %.3f mm (mean |r|) ; equal-area radius %.3f mm (shoelace)"
          % (m["r_mean"], m["r_eq"]))
    print("    surplus        %.3f%% longer than the circle enclosing the SAME area today"
          % (m["surplus"] * 100.0))
    print("    UNFOLDS TO     R %.3f mm  = +%.3f%% CONTENTS volume at ZERO membrane strain"
          % (m["r_unfold"], m["vol_gain"] * 100.0))
    print("                   (+%.3f%% on the centreline, which is how the judgement framed it;"
          " the contents figure above is the one that meets ice's ~9%%)"
          % (m["gain_centreline"] * 100.0))
    print("    bore now       %.1f cm2 -> %.2f L at this height; unfolded %.2f L"
          % (m["area_inner"] / 100.0, m["area_inner"] * a.height / 1e6,
             m["area_inner"] * (1.0 + m["vol_gain"]) * a.height / 1e6))
    print("    crest strain   %.3f%% on the outer fibre while unfolding (bending only)"
          % (m["crest_strain"] * 100.0))
    kc = (rm + amp) ** 2 - (rm + amp) * (-amp * a.lobes ** 2)
    kc /= (rm + amp) ** 3
    print("                   cross-check off the analytic profile: %.3f%% (different route)"
          % ((a.wall / 2.0 * (kc - 1.0 / m["r_unfold"])) * 100.0))
    print()
    print("    layers         %d at %.2f mm" % (m["n_layers"], a.layer))
    print("    wall path      %.0f mm  = %.2f m" % (m["wall_path"], m["wall_path"] / 1000.0))
    print("    base path      %.0f mm over a measured %.1f cm2 cap"
          % (m["base_path"], m["cap_area"] / 100.0))
    print("    volume         wall %.1f + base %.1f = %.1f cm3"
          % (m["wall_vol"] / 1000.0, m["base_vol"] / 1000.0, m["total_vol"] / 1000.0))
    print("    MASS           %.1f g at %.2f g/cm3   (wall %.1f g + base %.1f g)"
          % (m["grams"], PLA_DENSITY, m["wall_vol"] * PLA_DENSITY / 1000.0,
             m["base_vol"] * PLA_DENSITY / 1000.0))
    print("    filament       %.1f m of %.2f mm" % (m["fil_len"] / 1000.0, FIL_D))
    print("    flow           %.2f mm3/s at %.0f mm/s (cap %.0f)"
          % (m["flow"], a.speed, machine.FLOW))
    print("    print time     %.0f min = %.1f h at a constant %.0f mm/s"
          % (m["seconds"] / 60.0, m["seconds"] / 3600.0, a.speed))
    print()
    print("  SLICE AS: VASE / SPIRALIZE, one continuous spiral, no seam, 0 deg overhang.")
    print("  Gate:     python3 tools/qa_stl.py %s --class vase-solid" % os.path.basename(out))

    if abs(a.wall - machine.BEAD_W) > 1e-9:
        print()
        print("  ! WALL %.2f IS OLEG'S SPEC, NOT THIS MACHINE'S MEASURED BEAD. machine.py:40-41 "
              "carries BEAD_W %.2f / BEAD_H %.2f as the 0.8-nozzle stacking ceiling. A %.2f x %.2f "
              "bead is UNPROVEN here: narrower than the nozzle-spread figure, so it is the slicer "
              "metering a thin line rather than the measured bead. Reported, not substituted."
              % (a.wall, machine.BEAD_W, machine.BEAD_H, a.wall, a.layer))


if __name__ == "__main__":
    main()
