#!/usr/bin/env python3
"""Slope test vs step-test bridges selftest (2026-10-27, print-kb hanging-hole row).

A hanging hole closes a void in two stacked bridge layers: layer A bridges across the void and
leaves a slot, layer B bridges across the slot and leaves the hole plus 0.5 mm end gaps, so every
bridge is held at both ends. On crackle 57d6b81 two things read it wrong:
  claim 1  LAYERSUP's slope test compared layers A, B and the one above against the open void
           LS_BASE below and reported overhang strips inside and beside the step test's bridges.
  claim 2  PRINTABLE counted the end-gap ceilings, which the step test finds held within its
           allowance, because only bridge regions excused faces.
The fixture is that geometry tiled from boxes (cells that touch share faces, which PRINTABLE's
burial test drops), so each end-gap ceiling is its own face. The fix: bridges since the slope base
join the base (_layer_support), and PRINTABLE excuses a face the step test holds (_held_faces).
Each mutant takes one half away, or widens it, and must make a case read wrong.
"""
import contextlib
import io
import os
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import qa_stl as q  # noqa: E402

fails = []


def expect(label, cond, detail):
    print("%s %s: %s" % ("ok  " if cond else "FAIL", label, detail))
    if not cond:
        fails.append(label)


def box(x, y, z, sx, sy, sz):
    """Axis-aligned box, 12 outward-wound triangles (same builder as the LAYERSUP selftest)."""
    v = lambda i: (x + (sx if i & 1 else 0), y + (sy if i & 2 else 0), z + (sz if i & 4 else 0))
    f = ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5))
    return [t for a, b, c, d in f for t in ((v(a), v(b), v(c)), (v(a), v(c), v(d)))]


XS = (0, 11.5, 12, 14, 16, 18, 18.5, 30)
YS = (0, 5.5, 6, 9, 11, 14, 14.5, 20)
ZS = (0, 2.4, 2.64, 2.88, 4.0)        # slab tops on the plate's boundaries (planes 2.20, 2.44, 2.68)
IN = lambda lo, hi, a, b: lo <= a and b <= hi


def void(k, xa, xb, ya, yb):
    if k == 0:                                           # the 7 x 9 mm void, open from the bed
        return IN(11.5, 18.5, xa, xb) and IN(5.5, 14.5, ya, yb)
    if k == 1:          # layer A: two bridges leave a 2 mm slot, 0.5 mm gaps keep them off the sides
        return IN(11.5, 18.5, xa, xb) and (IN(9, 11, ya, yb) or IN(5.5, 6, ya, yb)
                                           or IN(14, 14.5, ya, yb))
    if k == 2:                                           # layer B: the hole and two 0.5 mm end gaps
        return IN(9, 11, ya, yb) and (IN(11.5, 12, xa, xb) or IN(14, 16, xa, xb)
                                      or IN(18, 18.5, xa, xb))
    return IN(14, 16, xa, xb) and IN(9, 11, ya, yb)       # the hole to the top


def tunnel(w):
    """The bridge-policy selftest's block with a w-wide tunnel: a roof upright AND flipped."""
    side = (30.0 - w) / 2.0
    return (box(side, 0, 0, w, 20, 4) + box(side, 0, 8, w, 20, 4)
            + box(0, 0, 0, side, 20, 12) + box(30 - side, 0, 0, side, 20, 12))


def hanging():
    """Filled cells merged into x runs per slab and y band: two boxes touching in x leave a
    zero-width gap in a scanline's spans, which splits one bridge into cells that never join. A
    run also breaks where the slab below changes from void to solid, so a ceiling over a gap is
    its own face (a run over solid too puts the centroid on solid, and burial drops it)."""
    tris = []
    for k in range(len(ZS) - 1):
        for j in range(len(YS) - 1):
            ya, yb, run, under = YS[j], YS[j + 1], None, None
            for i in range(len(XS)):
                full = i < len(XS) - 1 and not void(k, XS[i], XS[i + 1], ya, yb)
                below = i < len(XS) - 1 and k > 0 and void(k - 1, XS[i], XS[i + 1], ya, yb)
                if run is not None and (not full or below != under):
                    tris += box(run, ya, ZS[k], XS[i] - run, yb - ya, ZS[k + 1] - ZS[k])
                    run = None
                if full and run is None:
                    run, under = XS[i], below
    return tris


def write(tris, path):
    with open(path, "wb") as f:
        f.write(b"slope-bridge fixture".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<12fH", 0, 0, 0, *[c for v in t for c in v], 0))


TMP = tempfile.mkdtemp(prefix="slope-bridge-")
HANG = os.path.join(TMP, "hanging.stl")
write(hanging(), HANG)
ROOF15 = os.path.join(TMP, "tunnel-15.stl")
write(tunnel(15.0), ROOF15)
FX = os.path.join(ROOT, "fixtures", "a1")
LS = lambda tris: q._layer_support(tris, q.SLICER_LAYER_H, q.LS_DEG, 8.0, q.SLICER_LINE_W,
                                   q.SLICER_FIRST_H)


def load(path):
    b = open(path, "rb").read()
    n = struct.unpack("<I", b[80:84])[0]
    return [tuple(tuple(r[3 + 3 * k:6 + 3 * k]) for k in range(3))
            for r in struct.iter_unpack("<12fH", b[84:84 + 50 * n])]


def verdict(path):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = q.run_file(path, "closed", 340, 0, 0.4)
    lines = buf.getvalue().splitlines()
    pick = lambda n: next((l for l in lines if l.split()[1:2] == [n]), "none")
    return ok, pick("PRINTABLE"), pick("LAYERSUP")


def cases(tag):
    before = len(fails)
    regs, _n, _f = LS(hanging())
    ov = [r for r in regs if r[2] == "overhang"]
    br = [r for r in regs if r[2] == "bridge"]
    expect(tag + "hanging hole: no overhang, bridges found", not ov and len(br) >= 4,
           "%d overhang %s, %d bridge" % (len(ov), [(round(r[0], 2), r[7], round(r[1], 2))
                                                    for r in ov], len(br)))
    _ok, p, l = verdict(HANG)
    # upright: flipped, the gap ceilings are floors and PRINTABLE would pass on the retry
    expect(tag + "hanging hole passes PRINTABLE upright", p.startswith("PASS")
           and "UPSIDE-DOWN" not in p, p)
    expect(tag + "hanging hole passes LAYERSUP upright", l.startswith("PASS")
           and "UPSIDE-DOWN" not in l, l)
    for n, lo in (("roof-15", 100), ("floating-box", 95), ("wedge-40", 0)):
        regs, _n, _f = LS(load(os.path.join(FX, n + ".stl")))
        o = sum(r[1] for r in regs if r[2] == "overhang")
        expect(tag + "%s still fails LAYERSUP" % n, o > lo, "%.1f mm2 overhang" % o)
    for n, path in (("15 mm tunnel roof", ROOF15),
                    ("floating-box", os.path.join(FX, "floating-box.stl"))):
        ok, p, l = verdict(path)
        expect(tag + "%s fails PRINTABLE and LAYERSUP" % n,
               not ok and p.startswith("FAIL") and l.startswith("FAIL"), (p, l))
    return fails[before:]


print("-- the fix --")
cases("")

orig_ls, orig_cmp, orig_hf = q._layer_support, q._ls_compare, q._held_faces


def mutant(name, install, restore):
    install()
    try:
        before = len(fails)
        with contextlib.redirect_stdout(io.StringIO()):
            got = cases("[%s] " % name)
        del fails[before:]
    finally:
        restore()
    expect("mutant %s dies" % name, bool(got), got)


def no_bridges_found(cur, prev, allow, x0, y0, half_span, line_w, exclude=None, bridges=None,
                     held=None):
    """57d6b81's slope base: no bridge reaches the floors (nor PRINTABLE's bridge list)."""
    return orig_cmp(cur, prev, allow, x0, y0, half_span, line_w, exclude, None, held)


def every_region_a_floor(cur, prev, allow, x0, y0, half_span, line_w, exclude=None, bridges=None,
                         held=None):
    """Floors that ignore the classification: overhang regions join the slope base too."""
    out, flagged = orig_cmp(cur, prev, allow, x0, y0, half_span, line_w, exclude, bridges, held)
    if bridges is not None and exclude is None:
        fake = []
        orig_cmp(cur, prev, allow, x0, y0, 10 ** 6, line_w, exclude, fake)
        bridges[:] = fake
    return out, flagged


def held_is_all(cur, prev, allow, x0, y0, half_span, line_w, exclude=None, bridges=None,
                held=None):
    """PRINTABLE's excuse widened to every face of the layer, supported or not."""
    out, flagged = orig_cmp(cur, prev, allow, x0, y0, half_span, line_w, exclude, bridges, held)
    if held is not None:
        held.update({j: list(v) for j, v in cur.items()})
    return out, flagged


# M1 claim 1 back: bridges never become floors -> the hanging hole reads slope overhang
mutant("bridges-not-floors", lambda: setattr(q, "_ls_compare", no_bridges_found),
       lambda: setattr(q, "_ls_compare", orig_cmp))
# M2 claim 2 back: nothing held is excused -> the end-gap ceilings fail PRINTABLE
mutant("held-excuses-none", lambda: setattr(q, "_held_faces", lambda *a: set()),
       lambda: setattr(q, "_held_faces", orig_hf))
# M3 overhang regions as floors: the floating box and roof stop failing the slope test
mutant("overhang-as-floor", lambda: setattr(q, "_ls_compare", every_region_a_floor),
       lambda: setattr(q, "_ls_compare", orig_cmp))
# M4 every face held: the 15 mm roof passes PRINTABLE
mutant("held-is-all", lambda: setattr(q, "_ls_compare", held_is_all),
       lambda: setattr(q, "_ls_compare", orig_cmp))
# M5 every spanning face excused by _held_faces: the 15 mm roof passes PRINTABLE
mutant("excuse-all-held", lambda: setattr(q, "_held_faces", lambda idx, *a: set(idx)),
       lambda: setattr(q, "_held_faces", orig_hf))

print("FAIL: %d case(s): %s" % (len(fails), fails) if fails else "PASS: slope vs bridges")
sys.exit(1 if fails else 0)
