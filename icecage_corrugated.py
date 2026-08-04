#!/usr/bin/env python3
"""Corrugated ice cage -- the winning topology, emitted as a slicer VASE-MODE input solid.

WHAT IT IS
    A cylinder whose wall is a 12-lobe cosine corrugation in plan. Every gram sits in HOOPS
    (in-plane extrusion, PLA's strong axis); there are no vertical members at all, because a
    straight prism needs none. When the contents swell, the wavy ring UNFOLDS toward a circle
    by bending only -- zero membrane strain -- and only then does it carry hoop tension. The
    measured perimeter surplus is what sets how far it can unfold before it goes tight.

WHAT IT IS NOT
    Not a vessel. It does not hold liquid and does not need to (Oleg: "does not need to be air
    tight, grid is ok"). It is a restraint cage.

THE MODEL IS A FILLED SOLID ON PURPOSE
    Wall thickness is NOT in this mesh. The slicer's vase (spiralize) mode traces the model's
    outer surface inset by half the line width and lays exactly one 0.8 mm bead per layer. That
    is the repo's proven route for functional single-wall parts. Slicing this file in ORDINARY
    mode produces a ~16 kg cylinder -- vase mode is not optional.

PROVENANCE OF EVERY CONSTANT
    NOZZLE 0.8 / BEAD_W 1.2 / BEAD_H 0.6 / FLOW 55 / speed 50   read from machine.py:29,40,41,7,101
    wall 0.8                                                     Oleg, verbatim ask
    ID 250, H 300, lobes 12, amp 4.37                            the judged verdict for this part
    layer 0.4                                                    CHOSEN so 0.8/0.4 = the repo's
                                                                 proven 2:1 bead aspect. NOT measured.
    PLA 1.24 g/cm3                                               material figure, not measured here
    MISMATCH ON THE RECORD: machine.py says BEAD_W 1.2, Oleg asked for 0.8. 0.8 is used because he
    asked for it. A 0.8 bead from a 0.8 nozzle is UNPROVEN on this machine.
"""
import argparse
import math
import os
import struct

# ---- read from ~/dev/crackle/machine.py, quoted so this file is checkable against it ----
NOZZLE = 0.8        # machine.py:29
BEAD_W_REPO = 1.2   # machine.py:40  -- MISMATCH with Oleg's 0.8, reported not substituted
BEAD_H_REPO = 0.6   # machine.py:41
FLOW_CAP = 55.0     # machine.py:7
SPEED = 50.0        # machine.py:101 DEFAULT_SPEED
BED = 350.0         # K2 Plus real build volume, brief
MAX_MOVES_PER_SEC = 300.0   # machine.py:133


# --------------------------------------------------------------------------- geometry
def profile_r(theta, rc, amp, lobes, half_wall):
    """Radius of the MODEL's outer surface. The printed bead centreline sits half_wall inside it,
    at rc + amp*cos(lobes*theta)."""
    return rc + amp * math.cos(lobes * theta) + half_wall


def path_perimeter(rc, amp, lobes, steps=400000):
    """Exact arc length of the bead-centreline curve r = rc + amp*cos(lobes*t), by midpoint rule."""
    s = 0.0
    dt = 2.0 * math.pi / steps
    for i in range(steps):
        t = (i + 0.5) * dt
        r = rc + amp * math.cos(lobes * t)
        rp = -amp * lobes * math.sin(lobes * t)
        s += math.hypot(r, rp)
    return s * dt


def solve_amp(rc, lobes, vol_gain_pct, lo=0.0, hi=None):
    """Amplitude whose unfolded circle gives this volume gain. Bisection on a monotone function."""
    want = math.sqrt(1.0 + vol_gain_pct / 100.0) * (2.0 * math.pi * rc)
    if hi is None:
        hi = rc * 0.5
    for _ in range(90):
        mid = 0.5 * (lo + hi)
        if path_perimeter(rc, mid, lobes, steps=20000) < want:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def build(rc, amp, lobes, half_wall, height, ppl):
    """Closed corrugated prism: CCW ring extruded 0..height, plus centre-fan caps.

    Star-convex about the axis (min radius > 0), so the centre fan cannot self-intersect."""
    m = lobes * ppl
    ring = []
    for i in range(m):
        t = 2.0 * math.pi * i / m
        r = profile_r(t, rc, amp, lobes, half_wall)
        ring.append((r * math.cos(t), r * math.sin(t)))
    tris = []
    bot_c = (0.0, 0.0, 0.0)
    top_c = (0.0, 0.0, height)
    for i in range(m):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % m]
        a0 = (x0, y0, 0.0)
        a1 = (x1, y1, 0.0)
        b0 = (x0, y0, height)
        b1 = (x1, y1, height)
        tris.append((a0, a1, b1))      # side, outward
        tris.append((a0, b1, b0))
        tris.append((bot_c, a1, a0))   # bottom cap, normal -z
        tris.append((top_c, b0, b1))   # top cap, normal +z
    return tris, ring


# --------------------------------------------------------------------------- stl io
def normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    mag = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (0.0, 0.0, 0.0) if mag < 1e-12 else (nx / mag, ny / mag, nz / mag)


def write_binary_stl(path, tris):
    with open(path, "wb") as fh:
        fh.write(b"crackle icecage_corrugated - SLICE IN VASE MODE ONLY".ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            fh.write(struct.pack("<3f", *normal(a, b, c)))
            for v in (a, b, c):
                fh.write(struct.pack("<3f", *v))
            fh.write(struct.pack("<H", 0))


def read_tris(path):
    with open(path, "rb") as fh:
        fh.read(80)
        (n,) = struct.unpack("<I", fh.read(4))
        body = fh.read()
    out = []
    for rec in struct.iter_unpack("<12fH", body):
        out.append((rec[3:6], rec[6:9], rec[9:12]))
    return n, out


# --------------------------------------------------------------------------- measurement
def measure(path, half_wall):
    """Everything below is MEASURED OFF THE EMITTED FILE, never off the design formula.
    (Named lesson in this project: a summary line is not the file.)"""
    n, tris = read_tris(path)
    size = os.path.getsize(path)
    assert size == 84 + 50 * n, "LAW broken: %d != 84 + 50*%d" % (size, n)

    zs = [v[2] for t in tris for v in t]
    height = max(zs)
    verts0 = set()
    for t in tris:
        for v in t:
            if v[2] == 0.0 and (v[0] * v[0] + v[1] * v[1]) > 1.0:
                verts0.add(v)
    poly = sorted(verts0, key=lambda p: math.atan2(p[1], p[0]))
    poly = [(p[0], p[1]) for p in poly]
    k = len(poly)

    # outer-surface perimeter, straight from the emitted vertices
    p_out = sum(math.dist(poly[i], poly[(i + 1) % k]) for i in range(k))

    # shoelace area of the emitted outer polygon (this is the base-layer footprint)
    area = 0.0
    for i in range(k):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % k]
        area += x0 * y1 - x1 * y0
    area = abs(area) * 0.5

    # bead-centreline path = emitted polygon offset inward by half the line width, exact
    # miter offset (offset both edges, intersect) -- derived from the mesh, not from the formula
    nrm = []
    for i in range(k):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % k]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        nrm.append((-dy / L, dx / L))     # inward for a CCW polygon
    path = []
    for i in range(k):
        ax, ay = nrm[i - 1]
        bx, by = nrm[i]
        dot = ax * bx + ay * by
        sx, sy = (ax + bx) / (1.0 + dot), (ay + by) / (1.0 + dot)
        path.append((poly[i][0] + half_wall * sx, poly[i][1] + half_wall * sy))
    p_path = sum(math.dist(path[i], path[(i + 1) % k]) for i in range(k))
    seg_min = min(math.dist(path[i], path[(i + 1) % k]) for i in range(k))
    seg_max = max(math.dist(path[i], path[(i + 1) % k]) for i in range(k))
    r_path = [math.hypot(x, y) for x, y in path]

    xs = [v[0] for t in tris for v in t]
    ys = [v[1] for t in tris for v in t]
    return {
        "ntris": n, "size": size, "npts": k, "height": height,
        "bbox_x": max(xs) - min(xs), "bbox_y": max(ys) - min(ys),
        "p_out": p_out, "p_path": p_path, "area": area,
        "seg_min": seg_min, "seg_max": seg_max,
        "r_min": min(r_path), "r_max": max(r_path),
    }


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--id", type=float, default=250.0, help="mean INNER diameter mm (default 250)")
    ap.add_argument("--height", type=float, default=300.0, help="mm (default 300)")
    ap.add_argument("--wall", type=float, default=0.8, help="one extrusion, mm (default 0.8)")
    ap.add_argument("--lobes", type=int, default=12, help="corrugation lobes N (default 12)")
    ap.add_argument("--amp", type=float, default=4.37,
                    help="corrugation amplitude mm (default 4.37, the judged value)")
    ap.add_argument("--vol-gain", type=float, default=None, metavar="PCT",
                    help="instead of --amp, solve the amplitude for this unfolded volume gain "
                         "(ice is ~9)")
    ap.add_argument("--layer-h", type=float, default=0.4, help="mm (default 0.4)")
    ap.add_argument("--ppl", type=int, default=96, help="mesh points per lobe (default 96)")
    ap.add_argument("--base-layers", type=int, default=3,
                    help="slicer bottom solid layers, for the mass report only (default 3)")
    ap.add_argument("--rho", type=float, default=1.24, help="PLA g/cm3 (default 1.24)")
    ap.add_argument("--speed", type=float, default=SPEED, help="mm/s (default 50, machine.py:101)")
    ap.add_argument("--out", default="icecage_corrugated.stl")
    a = ap.parse_args()

    half = a.wall / 2.0
    rc = (a.id + a.wall) / 2.0            # bead-centreline mean radius
    amp = solve_amp(rc, a.lobes, a.vol_gain) if a.vol_gain is not None else a.amp

    tris, _ring = build(rc, amp, a.lobes, half, a.height, a.ppl)
    write_binary_stl(a.out, tris)
    m = measure(a.out, half)

    # ---- everything from here is computed from MEASURED quantities ----
    nlay = int(round(m["height"] / a.layer_h))
    base_n = max(0, min(a.base_layers, nlay))
    wall_n = nlay - base_n
    wall_len = m["p_path"] * wall_n                       # mm of bead
    wall_vol = wall_len * a.wall * a.layer_h              # mm3
    base_len = (m["area"] / a.wall) * base_n              # solid infill at one line width
    base_vol = m["area"] * a.layer_h * base_n
    g = lambda v: v * a.rho / 1000.0
    circ = 2.0 * math.pi * rc
    surplus = m["p_path"] / circ - 1.0
    r_unf = m["p_path"] / (2.0 * math.pi)
    vol_gain = (r_unf / rc) ** 2 - 1.0
    flow = a.wall * a.layer_h * a.speed
    mps = a.speed / m["seg_min"]
    secs = (wall_len + base_len) / a.speed

    print("== icecage_corrugated -> %s ==" % a.out)
    print("MESH (measured off the emitted file)")
    print("  triangles %d, filesize %d, LAW 84+50*%d = %d %s"
          % (m["ntris"], m["size"], m["ntris"], 84 + 50 * m["ntris"],
             "OK" if m["size"] == 84 + 50 * m["ntris"] else "BROKEN"))
    print("  ring points %d, height %.3f, bbox %.2f x %.2f (bed %g)"
          % (m["npts"], m["height"], m["bbox_x"], m["bbox_y"], BED))
    print("GEOMETRY (measured)")
    print("  outer-surface perimeter  %.3f mm   OD %.3f" % (m["p_out"], m["bbox_x"]))
    print("  bead-path perimeter      %.3f mm   (offset %.2f inward off the emitted polygon)"
          % (m["p_path"], half))
    print("  plain circle at rc=%.3f  %.3f mm   -> surplus %.4f%%" % (rc, circ, surplus * 100))
    print("  unfolds to R %.3f        -> volume gain %.3f%%  (ice needs ~9%%)"
          % (r_unf, vol_gain * 100))
    print("  path radius %.3f .. %.3f, segment %.4f .. %.4f mm"
          % (m["r_min"], m["r_max"], m["seg_min"], m["seg_max"]))
    print("  base footprint area      %.1f mm2" % m["area"])
    print("MATERIAL (from the measured path, layer %.2f, wall %.2f, rho %.2f g/cm3)"
          % (a.layer_h, a.wall, a.rho))
    print("  layers %d = %d base + %d spiral" % (nlay, base_n, wall_n))
    print("  wall  %.0f mm bead = %.1f cm3 = %.1f g" % (wall_len, wall_vol / 1000, g(wall_vol)))
    print("  base  %.0f mm bead = %.1f cm3 = %.1f g  (%d layers, %.1f g each)"
          % (base_len, base_vol / 1000, g(base_vol), base_n,
             g(m["area"] * a.layer_h) if base_n else 0.0))
    print("  TOTAL %.1f g          floorless (0 base layers) %.1f g"
          % (g(wall_vol + base_vol), g(m["p_path"] * nlay * a.wall * a.layer_h)))
    print("MACHINE")
    print("  flow %.2f mm3/s vs FLOW cap %g (machine.py:7)  %s"
          % (flow, FLOW_CAP, "OK" if flow <= FLOW_CAP else "OVER"))
    print("  %.0f moves/s at %g mm/s vs %g ceiling (machine.py:133)  %s"
          % (mps, a.speed, MAX_MOVES_PER_SEC, "OK" if mps <= MAX_MOVES_PER_SEC else "OVER"))
    print("  bead 0.8 wide from a 0.8 nozzle: machine.py:40 says BEAD_W 1.2 -- UNPROVEN here")
    print("  extrusion time at a constant %g mm/s: %.0f s = %.2f h (no travel/accel/heat-up)"
          % (a.speed, secs, secs / 3600.0))
    print("  ONE CONTINUOUS VASE-MODE SPIRAL. Slice with spiralize ON. Ordinary mode makes a solid.")


if __name__ == "__main__":
    main()
