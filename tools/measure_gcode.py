#!/usr/bin/env python3
"""Measure an emitted gcode file. The FILE is the artifact; a generator's summary line is not.

Every number here is read back out of the gcode, never carried across from the code that wrote it.
That is the whole point: crackle has been bitten repeatedly by a printed summary that was recomputed
from the same inputs as the file rather than parsed from it, so a bug in the emitter produced a
label that agreed with it perfectly.

FILAMENT IS MEASURED TWICE, BY TWO ROUTES THAT SHARE NO ARITHMETIC:

  route A — the E axis.  Sum the commanded advance of the extruder, times the cross-section of
                         1.75mm filament, times density. This is what the machine will actually
                         pull off the spool.
  route B — the deposit. Sum the XY path length of the extruding moves, times the bead cross-
                         section read from the file's own '; ' header stamps.

They are computed from different columns of different lines. If they disagree by more than a couple
of percent, one of them is wrong and the file should not be trusted — which is exactly the check
that a single-route measurement cannot make.

FOOTPRINT IS REPORTED OVER EXTRUDING MOVES ONLY. The extents of every move include the prime line
and the park, neither of which is part of the object, and quoting those as the object's size is
the measuring-the-easy-quantity error.

Usage:  python3 tools/measure_gcode.py <file.gcode> [...]
        python3 tools/measure_gcode.py --selftest
"""
import math
import re
import sys

FIL_D = 1.75
FIL_AREA = math.pi * (FIL_D / 2) ** 2      # mm2
PLA_DENSITY = 1.24e-3                      # g/mm3  (1.24 g/cm3)

_AX = re.compile(r'\b([XYZEF])(-?\d+(?:\.\d+)?)')


def measure(path):
    txt = open(path).read()
    lines = txt.split('\n')

    lh = _stamp(txt, 'LAYER_H')
    bead = _bead(txt)

    x = y = z = 0.0
    e = 0.0
    feed = 1200.0
    abs_e = True
    seen_xy = False

    ext_len = 0.0        # XY path length of extruding moves
    trav_len = 0.0       # XY path length of non-extruding moves
    e_total = 0.0        # commanded filament advance, mm
    secs = 0.0
    maxz = 0.0
    ex_min = [float('inf')] * 3
    ex_max = [float('-inf')] * 3
    n_ext = n_trav = 0
    zs = set()

    for raw in lines:
        code = raw.split(';')[0].strip()
        if not code:
            continue
        if code.startswith('M82'):
            abs_e = True
            continue
        if code.startswith('M83'):
            abs_e = False
            continue
        if code.startswith('G92'):
            m = re.search(r'E(-?[\d.]+)', code)
            if m:
                e = float(m.group(1))
            continue
        if not code.startswith(('G0', 'G1')):
            continue
        g = dict(_AX.findall(code))
        nx = float(g['X']) if 'X' in g else x
        ny = float(g['Y']) if 'Y' in g else y
        nz = float(g['Z']) if 'Z' in g else z
        if 'F' in g:
            feed = float(g['F'])
        # 3D distance: F is a 3D feedrate in Klipper, so a move that also climbs takes longer than
        # its XY projection suggests. Ignoring Z here under-reports the time of any helical path.
        d3 = math.dist((x, y, z), (nx, ny, nz))
        secs += d3 / max(feed / 60.0, 1e-9)
        dxy = math.dist((x, y), (nx, ny))

        if 'E' in g:
            ev = float(g['E'])
            de = (ev - e) if abs_e else ev
            e = ev if abs_e else e + de
            if de > 0:
                e_total += de
                ext_len += dxy
                if dxy > 1e-9:
                    n_ext += 1
                # The object's extents are the extents of MATERIAL. A pure-E purge has no XY and
                # must not be allowed to plant the bounding box wherever the head happened to be.
                if dxy > 1e-9 or seen_xy:
                    for i, (a_, b_) in enumerate(((x, nx), (y, ny), (z, nz))):
                        ex_min[i] = min(ex_min[i], a_, b_)
                        ex_max[i] = max(ex_max[i], a_, b_)
                    seen_xy = True
                zs.add(round(nz, 3))
        else:
            trav_len += dxy
            if dxy > 1e-9:
                n_trav += 1

        x, y, z = nx, ny, nz
        maxz = max(maxz, z)

    grams_e = e_total * FIL_AREA * PLA_DENSITY
    grams_path = (ext_len * bead * lh * PLA_DENSITY) if (bead and lh) else None

    return {
        'path': path,
        'lines': len(lines),
        'layers': len(zs),
        'layer_h': lh,
        'bead': bead,
        'ext_m': ext_len / 1000.0,
        'trav_m': trav_len / 1000.0,
        'n_ext': n_ext,
        'n_trav': n_trav,
        'e_mm': e_total,
        'grams_e': grams_e,
        'grams_path': grams_path,
        'mins': secs / 60.0,
        'maxz': maxz,
        'ext_min': ex_min,
        'ext_max': ex_max,
    }


def _stamp(txt, name):
    m = re.search(rf'^; {name}=([\d.]+)', txt, re.M)
    return float(m.group(1)) if m else None


def _bead(txt):
    """Bead WIDTH from the file's own header, in the form validate.py already looks for."""
    m = re.search(r'bead[ =]([\d.]+)', txt[:4000])
    return float(m.group(1)) if m else None


def report(r):
    print(f"\n{r['path']}")
    print(f"  lines={r['lines']}  distinct extruding Z={r['layers']}  "
          f"layer_h={r['layer_h']}  bead={r['bead']}")
    print(f"  extruding moves {r['n_ext']}  ({r['ext_m']:.1f} m of path)")
    print(f"  travel moves    {r['n_trav']}  ({r['trav_m']:.3f} m of path)")
    print(f"  FILAMENT  route A (E axis)   {r['e_mm']:.0f} mm of 1.75 -> {r['grams_e']:.1f} g")
    if r['grams_path'] is not None:
        d = abs(r['grams_path'] - r['grams_e']) / max(r['grams_e'], 1e-9) * 100
        flag = "AGREE" if d < 2.0 else "*** DISAGREE ***"
        print(f"            route B (deposit)  {r['ext_m']*1000:.0f} mm x "
              f"{r['bead']}x{r['layer_h']} -> {r['grams_path']:.1f} g   "
              f"[{flag}, {d:.1f}% apart]")
    else:
        print("            route B unavailable — no bead/layer_h stamp to cross-check against")
    print(f"  TIME      {r['mins']:.1f} min at the commanded feedrates "
          f"(motion only; no accel, no heat-up)")
    print(f"  MAX Z     {r['maxz']:.3f} mm")
    lo, hi = r['ext_min'], r['ext_max']
    print(f"  MATERIAL EXTENTS  X {lo[0]:.1f}..{hi[0]:.1f} ({hi[0]-lo[0]:.1f} mm)"
          f"   Y {lo[1]:.1f}..{hi[1]:.1f} ({hi[1]-lo[1]:.1f} mm)"
          f"   Z {lo[2]:.1f}..{hi[2]:.1f} ({hi[2]-lo[2]:.1f} mm)")


def selftest():
    """A harness that has never been checked against a known answer is a harness, not a measurement.

    Build a file whose every figure is known by hand, then require the parser to reproduce it.
    """
    import os
    import tempfile
    # 100mm of path at a 1.0x0.5 bead. Deposit = 100 * 0.5 = 50 mm3 -> 0.0620 g.
    # E for that = 50 / 2.40528 = 20.7876 mm of filament -> 20.7876 * 2.40528 * 1.24e-3 = 0.0620 g.
    #
    # TIME IS WORKED OUT BY HAND, TERM BY TERM, and the first version of this test got it wrong in
    # a way worth keeping on the record: it asserted 100mm/10mm/s = 10s while the file's extruding
    # move carried no F of its own, so it inherited F9000 from the travel above it and really ran
    # at 150 mm/s. The parser was right and the expectation was wrong. Every move now states its
    # own feedrate, because an inherited F is precisely the thing a hand-checked expectation
    # forgets.
    e = 50.0 / FIL_AREA
    src = "\n".join([
        "; SELFTEST",
        "; LAYER_H=0.5",
        "; bead 1.0",
        "M82",
        "G92 E0",
        "G1 F600 Z0.500",
        "G0 F9000 X10.000 Y10.000",
        f"G1 F600 X110.000 Y10.000 E{e:.4f}",
        "G0 Z50.000 F900",
    ]) + "\n"
    want_secs = (
        0.5 / (600 / 60.0)                       # Z0 -> Z0.5, 0.5mm at 10 mm/s
        + math.dist((0, 0), (10, 10)) / (9000 / 60.0)   # travel to the start, at 150 mm/s
        + 100.0 / (600 / 60.0)                   # the extrusion, 100mm at 10 mm/s
        + (50.0 - 0.5) / (900 / 60.0)            # park lift, 49.5mm at 15 mm/s
    )
    fd, p = tempfile.mkstemp(suffix=".gcode")
    os.write(fd, src.encode())
    os.close(fd)
    r = measure(p)
    os.unlink(p)

    checks = [
        ("extrusion path length", r['ext_m'] * 1000, 100.0, 0.01),
        ("grams route A", r['grams_e'], 0.0620, 0.0005),
        ("grams route B", r['grams_path'], 0.0620, 0.0005),
        ("minutes", r['mins'], want_secs / 60.0, 1e-6),
        ("max Z", r['maxz'], 50.0, 1e-6),
        ("X extent", r['ext_max'][0] - r['ext_min'][0], 100.0, 1e-6),
        ("Y extent", r['ext_max'][1] - r['ext_min'][1], 0.0, 1e-6),
        ("travel counted", r['n_trav'], 1, 0),
        ("extruding counted", r['n_ext'], 1, 0),
    ]
    bad = 0
    for name, got, want, tol in checks:
        ok = abs(got - want) <= tol
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: got {got}, want {want}")

    # THE HARNESS MUST BE SHOWN ABLE TO FAIL, or a green tick means nothing. Halve route B's bead
    # in a copy of the same file and require the two routes to be reported as disagreeing.
    fd, p2 = tempfile.mkstemp(suffix=".gcode")
    os.write(fd, src.replace("; bead 1.0", "; bead 0.5").encode())
    os.close(fd)
    r2 = measure(p2)
    os.unlink(p2)
    d = abs(r2['grams_path'] - r2['grams_e']) / r2['grams_e'] * 100
    ok = d > 2.0
    bad += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} forced disagreement fires: routes {d:.0f}% apart "
          f"(must exceed the 2% agreement threshold)")

    print("SELFTEST", "PASS" if not bad else f"FAIL ({bad})")
    return bad == 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    if "--selftest" in args:
        sys.exit(0 if selftest() else 1)
    if not args:
        print(__doc__)
        sys.exit(2)
    for f in args:
        report(measure(f))
