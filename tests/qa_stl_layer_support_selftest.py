#!/usr/bin/env python3
"""LAYERSUP selftest (brief A1, print-kb, 2026-10-24): every case runs the real _layer_support on
a fixture under fixtures/a1/ at the defaults (machine.py SLICER_LAYER_H, SLICER_LINE_W,
SLICER_FIRST_H, 45 deg, bridge-max 8), and each of the three earlier prototype bugs is reproduced
by forcing the old behaviour back in and showing the check then gets the fixture WRONG.

Fixtures: the ten print-kb A1 meshes (Assist commit add94ca7, expected.json beside them), the fit
coupon block with and without its labels (labels removed by commenting lines 57-58 of
Assist verticals/print-kb/coupons/fit-coupon.scad, openscad 2021.01), and fabric/chainmail_link.stl,
the tilted ring whose crest motivated LAYERCONT (crackle 53590ca). fixtures/foot_cup_inverted_cap.stl
is stand/foot_cup.stl as committed before its blind-cap fix: a scanline whose winding does not
return to zero must make LAYERSUP decline, never read as overhang (layersup judgement F1).
"""
import os
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import qa_stl as q  # noqa: E402
from machine import SLICER_LINE_W, SLICER_FIRST_H, SLICER_LAYER_H  # noqa: E402

FX = os.path.join(ROOT, "fixtures", "a1")
fails = []


def load(path):
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[80:84])[0]
    return [tuple(tuple(r[3 + 3 * k:6 + 3 * k]) for k in range(3))
            for r in struct.iter_unpack("<12fH", b[84:84 + 50 * n])]


def run(name, deg=q.LS_DEG):
    path = name if os.path.isabs(name) else os.path.join(FX, name + ".stl")
    regs, _n, _f = q._layer_support(load(path), SLICER_LAYER_H, deg, 8.0, SLICER_LINE_W,
                                SLICER_FIRST_H)
    ov = [r for r in regs if r[2] == "overhang"]
    return sum(r[1] for r in ov), sum(r[1] for r in regs if r[2] == "bridge"), ov


def box(x, y, z, sx, sy, sz):
    """Axis-aligned box, 12 outward-wound triangles (the prototype's builder)."""
    v = lambda i: (x + (sx if i & 1 else 0), y + (sy if i & 2 else 0), z + (sz if i & 4 else 0))
    f = ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5))
    return [t for a, b, c, d in f for t in ((v(a), v(b), v(c)), (v(a), v(c), v(d)))]


def run_tris(tris):
    regs, _n, _f = q._layer_support(tris, SLICER_LAYER_H, q.LS_DEG, 8.0, SLICER_LINE_W,
                                SLICER_FIRST_H)
    return sum(r[1] for r in regs if r[2] == "overhang")


# Built here, not read from fixtures/a1: the overlap must be two separate shells (the scad-made
# fixture is already unioned), and the vertex row must sit on THIS gate's plane, first_h + 2 layers.
OVERLAP = box(0, 0, 0, 10, 10, 6) + box(8, 0, 4, 10, 10, 6) + box(8, 0, 0, 10, 10, 4)
ZROW = SLICER_FIRST_H + 2.5 * SLICER_LAYER_H     # a plane centre with the seed removed
VROW = box(0, 0, 0, 20, 20, ZROW) + box(5, 5, ZROW, 10, 10, 3)


def expect(label, cond, detail):
    print("%s %s: %s" % ("ok  " if cond else "FAIL", label, detail))
    if not cond:
        fails.append(label)


# 1. known-good, and the case LAYERCONT gets wrong
for n in ("fit-coupon-block", "fit-coupon-block-nolabels", "solid-box", "ledge-0.15",
          "overlapping-shells", "vertex-row-plane", "wedge-50"):
    o, _b, _ = run(n)
    expect(n, o == 0, "%.2f mm2 overhang (want 0)" % o)
# 2. mid-air island, naming the z
o, _b, ov = run("floating-box")
expect("floating-box", 95 <= o <= 105 and len(ov) == 1 and 4.0 < ov[0][0] < 4.3,
       "%.1f mm2 in %d region(s), z %s (want one 100 mm2 region at the 4 mm island floor; "
       "counted once, it read 600 before)" % (o, len(ov), [round(r[0], 2) for r in ov]))
o, _b, _ = run("ledge-2")
expect("ledge-2", o > 10, "%.1f mm2 (2 mm cantilever)" % o)
# 3. flat roofs: 6 mm bridge passes, 15 mm over bridge-max fails
o, b, _ = run("roof-6")
expect("roof-6", o == 0 and b > 0, "overhang %.1f, bridge %.1f mm2" % (o, b))
o, b, _ = run("roof-15")
expect("roof-15", o > 100, "overhang %.1f mm2 (span past bridge-max 8)" % o)
# 4. angle boundary in 45 deg mode, both ends; and the 0 mode's documented looseness
o40, _b, _ = run("wedge-40")
expect("wedge-40", o40 > 0, "%.1f mm2 at 45 deg mode" % o40)
o40h, _b, _ = run("wedge-40", deg=0)
expect("wedge-40 half-line mode", o40h == 0,
       "%.1f mm2 (half a line on 0.24 layers flags only walls under 30 deg)" % o40h)
# 5. the tilted-ring crest
o, _b, _ = run(os.path.join(ROOT, "fabric", "chainmail_link.stl"))
expect("chainmail_link crest", o > 0, "%.1f mm2" % o)

# -- the three prototype bugs, forced back in: each must make a fixture read WRONG --------------
orig_rows, orig_seed = q._ls_rows, q.LS_SEED


def evenodd_rows(segs, y0, ny):
    """The prototype's first fill: parity, which cancels overlapping shells."""
    out = {}
    for j in range(ny):
        y = y0 + (j + 0.5) * q.LS_PITCH
        xs = sorted(p0[0] + (y - p0[1]) / (p1[1] - p0[1]) * (p1[0] - p0[0])
                    for p0, p1 in segs if (p0[1] - y) * (p1[1] - y) < 0)
        sp = [(xs[k], xs[k + 1]) for k in range(0, len(xs) - 1, 2)]
        if sp:
            out[j] = sp
    return out, 0


expect("overlapping shells (built)", run_tris(OVERLAP) == 0, "%.1f mm2" % run_tris(OVERLAP))
expect("vertex row on a plane (built)", run_tris(VROW) == 0, "%.1f mm2" % run_tris(VROW))
q._ls_rows = evenodd_rows
# parity punches the 2 mm overlap out as a hole, and the layer above it reads as a false roof
regs, _n, _f = q._layer_support(OVERLAP, SLICER_LAYER_H, q.LS_DEG, 8.0, SLICER_LINE_W, SLICER_FIRST_H)
o = sum(r[1] for r in regs)
expect("forced even-odd fill breaks overlapping shells", o > 0,
       "%.1f mm2 false unsupported (bridge + overhang)" % o)
q._ls_rows = orig_rows
q.LS_SEED = 0.0
o = run_tris(VROW)
o2 = 0.0
q.LS_SEED = orig_seed
# with the seed off the box tops sit on planes; at least one layer reads empty -> false overhang
expect("forced zero seed breaks a vertex-row fixture", o > 0 or o2 > 0,
       "vertex-row %.1f, solid-box %.1f mm2" % (o, o2))
orig_w = SLICER_LINE_W
regs, _n, _f = q._layer_support(load(os.path.join(FX, "fit-coupon-block.stl")), SLICER_LAYER_H,
                            q.LS_DEG, 8.0, 0.0, SLICER_FIRST_H)
nz = sum(r[1] for r in regs if r[2] == "overhang")
expect("forced zero noise floor breaks the coupon", nz > 0, "%.2f mm2 of rounding counted" % nz)

# -- an unbalanced winding is a fault, never an overhang (layersup judgement F1, 2026-10-24) -----
# fixtures/foot_cup_inverted_cap.stl is the stand foot cup before its blind-cap fix: the cap is wound
# into the solid, the scanline crossings across it sum to +2, and the old _ls_rows dropped those rows,
# so the layer read a 4 mm band of solid pad as empty and reported 3 overhang regions (4.6 mm2).
CUP = os.path.join(ROOT, "fixtures", "foot_cup_inverted_cap.stl")
regs, _n, faults = q._layer_support(load(CUP), SLICER_LAYER_H, q.LS_DEG, 8.0, SLICER_LINE_W,
                                    SLICER_FIRST_H)
expect("foot_cup inverted cap: unbalanced rows counted", len(faults) > 0 and
       any(9.0 < z < 12.0 for z, _k in faults),
       "%d faulted layer(s), z %s" % (len(faults), [round(z, 2) for z, _k in faults[:6]]))
for n in ("solid-box", "fit-coupon-block", "floating-box"):
    _r, _n, f = q._layer_support(load(os.path.join(FX, n + ".stl")), SLICER_LAYER_H, q.LS_DEG, 8.0,
                                 SLICER_LINE_W, SLICER_FIRST_H)
    expect("%s: no unbalanced rows" % n, not f, "%d faulted layer(s)" % len(f))


def dropping_rows(segs, y0, ny):
    """The old behaviour forced back in: unbalanced rows silently dropped, count hidden."""
    return orig_rows(segs, y0, ny)[0], 0


q._ls_rows = dropping_rows
regs, _n, faults = q._layer_support(load(CUP), SLICER_LAYER_H, q.LS_DEG, 8.0, SLICER_LINE_W,
                                    SLICER_FIRST_H)
q._ls_rows = orig_rows
o = sum(r[1] for r in regs if r[2] == "overhang")
expect("forced silent drop reads foot_cup as overhang", o > 0 and not faults,
       "%.2f mm2 false overhang" % o)

# -- the CLI: on by default, flagged, upside-down retry -------------------------------------------
cli = [sys.executable, os.path.join(ROOT, "tools", "qa_stl.py")]
r = subprocess.run(cli + [CUP], capture_output=True, text=True)
ls = [l for l in r.stdout.splitlines() if "LAYERSUP" in l]
expect("CLI declines foot_cup inverted cap", r.returncode == 1 and ls and
       " ".join(ls[0].split()).startswith("FAIL LAYERSUP could not measure: winding unbalanced at z")
       and "overhang region" not in ls[0], ls)
r = subprocess.run(cli + ["--no-layer-support", os.path.join(FX, "floating-box.stl")],
                   capture_output=True, text=True)
expect("CLI --no-layer-support skips LAYERSUP", "LAYERSUP" not in r.stdout,
       [l for l in r.stdout.splitlines() if "LAYERSUP" in l])
# roof-15 flipped is a slab on the bed with two pillars up, which prints; the island fails both ways
r = subprocess.run(cli + [os.path.join(FX, "floating-box.stl")], capture_output=True, text=True)
expect("CLI fails floating-box", r.returncode == 1 and "FAIL LAYERSUP" in r.stdout,
       [l for l in r.stdout.splitlines() if "LAYERSUP" in l])
r = subprocess.run(cli + [os.path.join(FX, "ledge-2.stl")], capture_output=True, text=True)
expect("CLI passes ledge-2 UPSIDE-DOWN", "PASS LAYERSUP" in r.stdout and "UPSIDE-DOWN" in r.stdout,
       [l for l in r.stdout.splitlines() if "LAYERSUP" in l])

print("FAIL: %d case(s): %s" % (len(fails), fails) if fails else "PASS: all LAYERSUP cases")
sys.exit(1 if fails else 0)
