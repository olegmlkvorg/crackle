#!/usr/bin/env python3
"""shim_ring_stl.py -- the GRADED TPU SHIM FAMILY (feedback 2026-08-02: "the sticks are
5.8-6.2 ... print 7mm bores and also design tpu rings of different width to put on the rods to
match the diameter").

The sticks MEASURE O5.8-6.2 variable per stick (rod_constants). Every socket bore is a FLAT
O7.0. A shim ring slips onto the rod and fills the per-stick difference:

  RING per 0.1 mm grade (5.8 5.9 6.0 6.1 6.2):
    ID    = the rod grade (TPU stretches a hair onto the stick = stays put)
    wall  = (BORE + SHIM_COMPRESS - rod)/2, floored at TPU_WALL_MIN 0.4 -- the stack
            rod+2*wall is SHIM_COMPRESS (0.15) OVER the bore, so the TPU must be squeezed
            to enter and that squeeze is the grip. It read 'under' until 2026-08-03 and every
            shim rattled; a shim smaller than its bore holds nothing.
            The 6.1 and 6.2 grades sit ON the 0.4 print floor, so their squeeze allowance
            shrinks to 0.10/0.00 (noted per ring; a 6.2 stick is a direct TPU-free-ish fit).
    SPLIT by a 20deg gap: clips onto a rod mid-length, and the gap is extra squeeze room.
    7 mm tall, prints flat (annulus on the bed), many per plate.
    TPU on the K1C: 205C, model fan 20%.

  SHIM_GAUGE comb (PLA, rigid): five open slots 5.8..6.2 -- push the stick into slots from the
  small end; the first slot it enters names its grade. Slots are modelled +0.25 oversize:
  printed hole ~= model -0.25 (Creality calibration-coin empiric, memory 2026-07). That
  empiric came from vase-mode round bores -- UNPROVEN on sliced slots: caliper the first
  gauge print. A corner chamfer marks the 5.8 end.

Self-verify measures the EMITTED mesh (ID, OD, wall, split, slot widths); a FAIL quarantines
the file as .FAILED. --sabotage wall proves the gate fires.

Usage:
  python3 shim_ring_stl.py [--out-dir DIR]              # the 5 rings + the gauge
  python3 shim_ring_stl.py --sabotage wall --out-dir /tmp/x
"""
import argparse
import math
import os
import struct
import sys

import rod_constants as RC
from bamboo_joints_stl import earclip, mesh_volume, parity, read_stl

HEIGHT = 7.0                 # ring height: short, per the spec's 6-8 band
SPLIT_DEG = 20.0             # ring gap: clip-on + squeeze room
N = 96                       # arc segments (full circle)
GAUGE_T = 4.0                # gauge plate thickness
GAUGE_SLOT_DEPTH = 14.0      # > 2 rod diameters: the stick seats fully
GAUGE_FINGER = 4.0           # finger width between slots
SLOT_PRINT_COMP = 0.25       # printed hole ~= model -0.25 (Creality coin empiric; UNPROVEN
                             # on sliced slots -- caliper the first print)
PLA_G_PER_MM3 = 1.24e-3
TPU_G_PER_MM3 = 1.21e-3


def grades():
    n = int(round((RC.ROD_MAX - RC.ROD_MIN) / 0.1))
    return [round(RC.ROD_MIN + 0.1 * i, 1) for i in range(n + 1)]


def ring_dims(rod):
    """(ID, wall, OD, squeeze) for a grade. All from rod_constants -- no magic numbers."""
    wall = max(RC.TPU_WALL_MIN, (RC.BORE + RC.SHIM_COMPRESS - rod) / 2.0)
    od = rod + 2.0 * wall
    return rod, wall, od, RC.BORE - od


# ------------------------------------------------------------------ meshing
def write_stl(path, tris):
    hdr = b"crackle bamboo shim family - graded TPU rings for O5.8-6.2 sticks in O7.0 bores"
    assert len(hdr) <= 80
    with open(path, "wb") as fh:
        fh.write(hdr.ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            m = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            fh.write(struct.pack("<3f", nx / m, ny / m, nz / m))
            for v in (a, b, c):
                fh.write(struct.pack("<3f", *v))
            fh.write(struct.pack("<H", 0))


def prism(loop, h):
    """Extrude a simple CCW polygon 0..h: walls + earclipped caps. Watertight."""
    tris = []
    n = len(loop)
    for i in range(n):
        j = (i + 1) % n
        a = (loop[i][0], loop[i][1], 0.0)
        b = (loop[j][0], loop[j][1], 0.0)
        c = (loop[j][0], loop[j][1], h)
        d = (loop[i][0], loop[i][1], h)
        tris.append((a, b, c))
        tris.append((a, c, d))
    for i0, i1, i2 in earclip(loop):
        p = [loop[i0], loop[i1], loop[i2]]
        tris.append(((p[0][0], p[0][1], 0.0), (p[2][0], p[2][1], 0.0), (p[1][0], p[1][1], 0.0)))
        tris.append(((p[0][0], p[0][1], h), (p[1][0], p[1][1], h), (p[2][0], p[2][1], h)))
    return tris


def ring_loop(id_d, od_d):
    """Split-annulus cross-section, CCW. Inner verts OUTSCRIBED so the chord-inscribed bore
    equals the ID exactly; outer verts AT the OD (chord sag at N=96 is 2 microns)."""
    a0 = math.radians(SPLIT_DEG / 2.0)
    a1 = 2.0 * math.pi - a0
    ri = (id_d / 2.0) / math.cos(math.pi / N)
    ro = od_d / 2.0
    steps = N - int(N * SPLIT_DEG / 360.0)
    outer = [(ro * math.cos(a0 + (a1 - a0) * k / steps),
              ro * math.sin(a0 + (a1 - a0) * k / steps)) for k in range(steps + 1)]
    inner = [(ri * math.cos(a0 + (a1 - a0) * k / steps),
              ri * math.sin(a0 + (a1 - a0) * k / steps)) for k in range(steps + 1)]
    return outer + inner[::-1]


def gauge_layout():
    """Slot x-windows for the comb, smallest grade first. Returns (slots, width, height)
    with slots = [(grade, x_left, x_right)]."""
    slots = []
    x = 5.0
    for g in grades():
        w = g + SLOT_PRINT_COMP
        slots.append((g, x, x + w))
        x += w + GAUGE_FINGER
    return slots, x - GAUGE_FINGER + 5.0, GAUGE_SLOT_DEPTH + 8.0


def gauge_loop():
    """Comb outline, CCW: base with a 5.8-end chamfer, slots opening through the top edge."""
    slots, W, Hp = gauge_layout()
    ch = 3.0
    pts = [(ch, 0.0), (W, 0.0), (W, Hp)]
    for g, xl, xr in reversed(slots):           # walk the top edge right -> left
        pts += [(xr, Hp), (xr, Hp - GAUGE_SLOT_DEPTH), (xl, Hp - GAUGE_SLOT_DEPTH), (xl, Hp)]
    pts += [(0.0, Hp), (0.0, ch)]               # chamfered corner marks the 5.8 end
    return pts


# -------------------------------------------------------------- self-verify
def _fail(path, checks):
    ok = all(c[1] for c in checks)
    for name, good, msg in checks:
        print("  %s %-26s %s" % ("PASS" if good else "FAIL", name, msg))
    if not ok:
        os.replace(path, path + ".FAILED")
        print("  SELF-VERIFY: FAIL -> quarantined %s.FAILED" % path)
        raise SystemExit(1)
    print("  SELF-VERIFY: PASS")


def verify_ring(path, rod, wall, od, squeeze):
    tris = read_stl(path)
    verts = {tuple(v) for t in tris for v in t}
    vol = mesh_volume(tris)
    rads = sorted(math.hypot(v[0], v[1]) for v in verts)
    id_meas = 2.0 * rads[0] * math.cos(math.pi / N)     # chord-inscribed bore off the mesh
    od_meas = 2.0 * rads[-1]
    wall_meas = (od_meas - id_meas) / 2.0
    gap_half = math.radians(SPLIT_DEG / 2.0)
    in_gap = [v for v in verts
              if abs(math.atan2(v[1], v[0])) < gap_half - 1e-6 and math.hypot(v[0], v[1]) > 0.1]
    unpaired = len(parity(tris))
    print("%s: %d tris, %.0f mm3 = %.2f g TPU" % (path, len(tris), vol, vol * TPU_G_PER_MM3))
    _fail(path, [
        ("watertight", unpaired == 0, "%d unpaired edges" % unpaired),
        ("bore ID == rod %.1f" % rod, abs(id_meas - rod) < 0.02,
         "%.3f measured (TPU squeezes onto the stick)" % id_meas),
        ("OD == %.2f = bore + %.2f" % (od, squeeze), abs(od_meas - od) < 0.02,
         "%.3f measured; squeeze allowance %.2f%s" % (od_meas, squeeze,
          " (ON the 0.4 wall floor)" if wall <= RC.TPU_WALL_MIN + 1e-9 else "")),
        # ABSOLUTE grip test, added 2026-08-03. The check above compares the emitted OD to a
        # number computed by the SAME formula that sizes it, so it passed happily while every
        # shim came out 0.15 UNDER the bore and gripped nothing. Self-consistency is not
        # correctness. This one tests the only thing that matters against an external constant:
        # a shim grips if and only if it is BIGGER than the hole it must be squeezed into.
        ("GRIPS: OD %.2f > bore %.2f" % (od_meas, RC.BORE), od_meas > RC.BORE + 0.05,
         "squeeze into the bore %+.2f mm (a shim smaller than its bore holds nothing)"
         % (od_meas - RC.BORE)),

        ("wall >= %.1f" % RC.TPU_WALL_MIN, wall_meas >= RC.TPU_WALL_MIN - 0.02,
         "%.3f measured" % wall_meas),
        ("split gap present", not in_gap, "%d verts inside the %gdeg gap window"
         % (len(in_gap), SPLIT_DEG)),
        ("height %.0f" % HEIGHT, abs(max(v[2] for v in verts) - HEIGHT) < 1e-6,
         "%.2f" % max(v[2] for v in verts)),
    ])


def verify_gauge(path):
    tris = read_stl(path)
    verts = {tuple(v) for t in tris for v in t}
    vol = mesh_volume(tris)
    slots, W, Hp = gauge_layout()
    unpaired = len(parity(tris))
    checks = [("watertight", unpaired == 0, "%d unpaired edges" % unpaired)]
    for g, xl, xr in slots:
        wanted = g + SLOT_PRINT_COMP
        deep = [v for v in verts if Hp - GAUGE_SLOT_DEPTH - 1e-6 <= v[1] <= Hp
                and xl - 1.0 < v[0] < xr + 1.0]
        cx = (xl + xr) / 2.0
        left = max(v[0] for v in deep if v[0] < cx)
        right = min(v[0] for v in deep if v[0] > cx)
        checks.append(("slot %.1f == %.2f modelled" % (g, wanted),
                       abs((right - left) - wanted) < 0.02,
                       "%.3f measured (prints ~%.1f after the -%.2f hole shrink)"
                       % (right - left, right - left - SLOT_PRINT_COMP, SLOT_PRINT_COMP)))
    print("%s: %d tris, %.0f mm3 = %.2f g PLA (rigid gauge)" % (path, len(tris), vol,
                                                                vol * PLA_G_PER_MM3))
    _fail(path, checks)


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--sabotage", choices=("wall",), default=None,
                    help="undersize a wall to PROVE the gate fires")
    a = ap.parse_args()
    print("SHIM FAMILY: rods MEASURE %g-%g -> ring per 0.1 grade; bore O%g FLAT; "
          "stack = rod + 2*wall = bore + %g squeeze (wall floored at %g). "
          "TPU on the K1C, 205C, model fan 20%%; gauge in PLA."
          % (RC.ROD_MIN, RC.ROD_MAX, RC.BORE, RC.SHIM_COMPRESS, RC.TPU_WALL_MIN))
    for rod in grades():
        rid, wall, od, squeeze = ring_dims(rod)
        if a.sabotage == "wall":
            wall -= 0.15
            od = rod + 2.0 * wall
        out = os.path.join(a.out_dir, "shim_%.1f.stl" % rod)
        write_stl(out, prism(ring_loop(rid, od), HEIGHT))
        verify_ring(out, rod, wall, ring_dims(rod)[2], ring_dims(rod)[3])
    out = os.path.join(a.out_dir, "shim_gauge.stl")
    write_stl(out, prism(gauge_loop(), GAUGE_T))
    verify_gauge(out)


if __name__ == "__main__":
    main()

