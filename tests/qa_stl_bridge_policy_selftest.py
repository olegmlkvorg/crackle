#!/usr/bin/env python3
"""Bridge policy selftest (2026-10-27): bridges are judged in ONE place, LAYERSUP.

PRINTABLE used to fail every inward downward face, bridge or not, so a hanging hole (a held 5 mm
roof the slicer bridges) failed closed-class qa_stl while LAYERSUP admitted it (print-kb plate
ebcdc3f8, wardrobe-station verticals/print-kb/coupons/out/). Now PRINTABLE excuses a face that is
the underside of a region LAYERSUP classes as a bridge within --bridge-max, and nothing else.

The fixture is a block with a horizontal tunnel through it, built here from overlapping boxes: the
tunnel roof is held by both side walls and the tunnel is in the middle of the block, so it is a
roof upright AND flipped (no upside-down escape). A 5 mm tunnel must pass PRINTABLE and LAYERSUP;
a 15 mm one must fail both. Each mutant forces the old or a broken policy back in and must make
one of those cases read wrong.
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


def tunnel(w):
    """30 x 20 x 12 block, a w-wide, 4 mm tall tunnel along y at z 4..8. The roof and the floor of
    the tunnel are their own boxes, so each face is exactly the tunnel's: a full-width slab puts
    the faces' centroids inside the walls, where PRINTABLE's burial test drops them and the old
    policy passes the hole too (this fixture's first two versions did, upright then flipped)."""
    side = (30.0 - w) / 2.0
    return (box(side, 0, 0, w, 20, 4) + box(side, 0, 8, w, 20, 4)
            + box(0, 0, 0, side, 20, 12) + box(30 - side, 0, 0, side, 20, 12))


def write(tris, path):
    with open(path, "wb") as f:
        f.write(b"bridge-policy fixture".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<12fH", 0, 0, 0, *[c for v in t for c in v], 0))


TMP = tempfile.mkdtemp(prefix="bridge-policy-")
HOLE5, ROOF15 = os.path.join(TMP, "tunnel-5.stl"), os.path.join(TMP, "tunnel-15.stl")
write(tunnel(5.0), HOLE5)
write(tunnel(15.0), ROOF15)


def verdict(path, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = q.run_file(path, "closed", 340, 0, 0.4, **kw)
    lines = buf.getvalue().splitlines()
    pick = lambda n: next((l for l in lines if l.split()[1:2] == [n]), "none")
    return ok, pick("PRINTABLE"), pick("LAYERSUP")


def cases(tag):
    """The four policy assertions. Returns the labels that failed."""
    before = len(fails)
    ok, p, l = verdict(HOLE5)
    expect(tag + "5 mm hanging hole passes PRINTABLE", p.startswith("PASS"), p)
    expect(tag + "5 mm hanging hole passes LAYERSUP", l.startswith("PASS") and "1 bridge" in l, l)
    ok15, p15, l15 = verdict(ROOF15)
    expect(tag + "15 mm roof fails PRINTABLE", p15.startswith("FAIL"), p15)
    expect(tag + "15 mm roof fails LAYERSUP", l15.startswith("FAIL"), l15)
    expect(tag + "15 mm roof fails overall", not ok15, "run_file returned %s" % ok15)
    # --no-layer-support: no LAYERSUP measurement, so nothing is excused (the old PRINTABLE)
    _ok, pn, _ln = verdict(HOLE5, layer_support=False)
    expect(tag + "5 mm hole without LAYERSUP fails PRINTABLE as before", pn.startswith("FAIL"), pn)
    return fails[before:]


print("-- the policy --")
cases("")
policy_fails = list(fails)

# -- mutants: each must make at least one case read wrong ----------------------------------------
orig_bf, orig_cmp = q._bridge_faces, q._ls_compare


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


# M1 excuse every spanning face: the 15 mm roof's PRINTABLE line passes
mutant("excuse-all", lambda: setattr(q, "_bridge_faces", lambda idx, *a: set(idx)),
       lambda: setattr(q, "_bridge_faces", orig_bf))
# M2 the old PRINTABLE, excusing nothing: the 5 mm hole fails PRINTABLE
mutant("excuse-none", lambda: setattr(q, "_bridge_faces", lambda *a: set()),
       lambda: setattr(q, "_bridge_faces", orig_bf))


def all_regions_as_bridges(cur, prev, allow, x0, y0, half_span, line_w, exclude=None, bridges=None,
                           held=None):
    """Footprint collection that ignores the classification: overhang regions handed over too."""
    out, flagged = orig_cmp(cur, prev, allow, x0, y0, half_span, line_w, exclude, bridges, held)
    if bridges is not None:
        fake = []
        orig_cmp(cur, prev, allow, x0, y0, 10 ** 6, line_w, exclude, fake)
        bridges[:] = fake
    return out, flagged


# M3 overhang regions excused as if bridges: the 15 mm roof's PRINTABLE line passes
mutant("overhang-as-bridge", lambda: setattr(q, "_ls_compare", all_regions_as_bridges),
       lambda: setattr(q, "_ls_compare", orig_cmp))

print("FAIL: %d case(s): %s" % (len(fails), fails) if fails else "PASS: bridge policy")
sys.exit(1 if fails else 0)
