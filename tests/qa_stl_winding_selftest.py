#!/usr/bin/env python3
"""WINDING selftest (2026-10-24): a closed mesh may not use any directed edge twice.

WATERTIGHT pairs edges WITHOUT direction, so a triangle wound backwards still pairs every edge and
passes. The motivating artifact is fixtures/foot_cup_inverted_cap.stl, the stand foot cup as
committed before the blind-cap fix: its teardrop caps were written (A, C, B), 178 directed edges
appear twice in the same direction, WATERTIGHT and PRINTABLE pass, and LAYERSUP read the inverted
cap as 4.6 mm2 of overhang (reports/layersup-judgement-2026-10-24.md).

Cases: that known-bad file, a minimal forced failure (a box with one triangle flipped, which still
passes WATERTIGHT), and the correct box as the control.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "fixtures"))
import make_fixtures as mf  # noqa: E402

QA = [sys.executable, os.path.join(ROOT, "tools", "qa_stl.py"), "--no-layer-support"]
fails = []


def expect(label, cond, detail):
    print("%s %s: %s" % ("ok  " if cond else "FAIL", label, detail))
    if not cond:
        fails.append(label)


def lines(path, *names):
    r = subprocess.run(QA + [path], capture_output=True, text=True, timeout=600)
    got = {n: [l for l in r.stdout.splitlines() if l.split()[1:2] == [n]] for n in names}
    return r.returncode, got


rc, got = lines(os.path.join(ROOT, "fixtures", "foot_cup_inverted_cap.stl"), "WATERTIGHT", "WINDING")
expect("foot_cup inverted cap: WATERTIGHT still passes (undirected pairing cannot see it)",
       got["WATERTIGHT"] and got["WATERTIGHT"][0].startswith("PASS"), got["WATERTIGHT"])
expect("foot_cup inverted cap: WINDING fails, 178 same-direction edges",
       rc == 1 and got["WINDING"] and got["WINDING"][0].startswith("FAIL")
       and " 178 " in got["WINDING"][0], got["WINDING"])

tmp = tempfile.mkdtemp(prefix="qa_winding_")
tris = mf.box(0, 20, 0, 20, 0, 20)
a, b, c = tris[3]
flipped = mf.write_stl(os.path.join(tmp, "box_one_flipped.stl"), tris[:3] + [(a, c, b)] + tris[4:])
rc, got = lines(flipped, "WATERTIGHT", "WINDING")
expect("box with one triangle flipped: WATERTIGHT passes",
       got["WATERTIGHT"] and got["WATERTIGHT"][0].startswith("PASS"), got["WATERTIGHT"])
expect("box with one triangle flipped: WINDING fails on its 3 edges",
       rc == 1 and got["WINDING"] and got["WINDING"][0].startswith("FAIL")
       and " 3 " in got["WINDING"][0], got["WINDING"])

rc, got = lines(os.path.join(ROOT, "fixtures", "box.stl"), "WINDING")
expect("correct box: WINDING passes", rc == 0 and got["WINDING"]
       and got["WINDING"][0].startswith("PASS"), got["WINDING"])

print("FAIL: %d case(s): %s" % (len(fails), fails) if fails else "PASS: all WINDING cases")
sys.exit(1 if fails else 0)
