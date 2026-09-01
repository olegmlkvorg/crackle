#!/usr/bin/env python3
"""Check heatbox/mass.py against solids whose volume is known by arithmetic.

mass.py produces the gram figures printed in the assembly PDF, so a sign error or a
factor of two there is a published lie rather than a wrong log line. The signed-
tetrahedron sum is validated here against shapes whose exact volume is a formula: a
cube, a cube with a bore through it, and a cube with a corner removed (which is where a
sign error shows up, because the subtracted facets wind the other way).

The tolerance is 0.6% and exists only for the polygon approximation of the cylinder —
the two box cases are exact and are checked at 0.01%.
"""
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "heatbox"))

FACETS = 128            # $fn for the bore case; error falls as 1/n^2

# (label, scad source, exact volume mm3, tolerance fraction)
CASES = [
    ("cube 10", "cube([10,10,10]);", 1000.0, 1e-4),
    ("cube 20 less corner 5",
     "difference(){ cube([20,20,20]); cube([5,5,5]); }",
     8000.0 - 125.0, 1e-4),
    (f"cube 20 bored 6 (fn={FACETS})",
     f"$fn={FACETS}; difference(){{ cube([20,20,20], center=true);"
     f" cylinder(d=6, h=40, center=true); }}",
     8000.0 - FACETS * 0.5 * (3.0 ** 2) * math.sin(2 * math.pi / FACETS) * 20.0,
     6e-3),
]


def main():
    if shutil.which("openscad") is None:
        print("FAIL heatbox mass: openscad absent, so the volume math was NOT checked.")
        return 1
    try:
        import mass
    except ImportError as exc:
        print(f"FAIL heatbox mass: cannot import heatbox/mass.py: {exc}")
        return 1

    failures = []
    with tempfile.TemporaryDirectory() as workdir:
        work = Path(workdir)
        for label, source, exact, tolerance in CASES:
            scad = work / "case.scad"
            stl = work / "case.stl"
            scad.write_text(source + "\n")
            proc = subprocess.run(["openscad", "-o", str(stl), str(scad)],
                                  capture_output=True, text=True, timeout=120)
            if not stl.is_file():
                failures.append(f"{label}: openscad produced no STL\n{proc.stderr[-300:]}")
                continue
            measured, facets, _ = mass.measure(stl)
            error = abs(measured - exact) / exact
            if error > tolerance:
                failures.append(
                    f"{label}: measured {measured:.3f} mm3, exact {exact:.3f}, "
                    f"off by {error*100:.3f}% (limit {tolerance*100:.3f}%)")
            elif facets < 12:
                failures.append(f"{label}: only {facets} facets parsed — parser is "
                                "dropping geometry it should have read")
            stl.unlink()

        # A negative volume would mean the winding was read backwards; abs() in measure()
        # hides that, so confirm the raw sum is positive for a plain outward-wound solid.
        scad = work / "sign.scad"
        scad.write_text("cube([4,4,4]);\n")
        stl = work / "sign.stl"
        subprocess.run(["openscad", "-o", str(stl), str(scad)],
                       capture_output=True, timeout=120)
        raw, _, _ = mass.signed_volume(stl)   # mass.py's OWN sum, not a copy of it:
        # re-implementing the formula here made this check pass against a mass.py whose
        # accumulator had been negated, which is a test proving only that the test works.
        if raw <= 0:
            failures.append(f"signed sum is {raw:.3f} for an outward-wound cube; "
                            "abs() would be masking a reversed winding convention")

    for line in failures:
        print("FAIL " + line)
    if failures:
        print(f"heatbox mass: {len(failures)} of {len(CASES)+1} checks failed")
        return 1
    print(f"PASS heatbox mass: {len(CASES)} known volumes matched, winding sign correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
