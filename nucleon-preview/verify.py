#!/usr/bin/env python3
"""Independent G-code parser and provenance gate for the Nucleon previews.

This file does not import the generator or renderer. It measures only committed bytes.
"""
import hashlib
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "artifacts")
BOUNDS = {"k2plus": (350.0, 350.0, 350.0)}
WORD = re.compile(r"\b([XYZEF])(-?\d+(?:\.\d+)?)")


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def measure(path):
    x = y = z = None
    e = 0.0
    body = False
    body_points = []
    body_moves = dry_body_moves = 0
    all_points = []
    printer = None
    for number, line in enumerate(open(path), 1):
        if line.startswith("; PRINTER="):
            printer = line.strip().split("=", 1)[1]
        if "BODY_START" in line:
            body = True
            continue
        code = line.split(";", 1)[0].strip()
        if body and code == "M107":
            body = False
        if code.startswith("G92"):
            words = dict(WORD.findall(code))
            if "E" in words:
                e = float(words["E"])
            continue
        if not code.startswith(("G0", "G1")):
            continue
        words = dict(WORD.findall(code))
        nx = float(words["X"]) if "X" in words else x
        ny = float(words["Y"]) if "Y" in words else y
        nz = float(words["Z"]) if "Z" in words else z
        ne = float(words["E"]) if "E" in words else e
        if nx is not None and ny is not None and nz is not None:
            all_points.append((number, nx, ny, nz))
        xy_move = x is not None and y is not None and (nx != x or ny != y)
        if body and xy_move:
            body_moves += 1
            if "E" not in words or ne <= e:
                dry_body_moves += 1
            body_points.extend(((x, y), (nx, ny)))
        x, y, z, e = nx, ny, nz, ne
    if printer not in BOUNDS:
        raise AssertionError(f"{os.path.basename(path)}: unknown printer {printer!r}")
    bx, by, bz = BOUNDS[printer]
    outside = [(n, px, py, pz) for n, px, py, pz in all_points
               if not (0 <= px <= bx and 0 <= py <= by and 0 <= pz <= bz)]
    if outside:
        raise AssertionError(f"{os.path.basename(path)}: move outside bounds: {outside[0]}")
    if not body_points or dry_body_moves:
        raise AssertionError(f"{os.path.basename(path)}: {dry_body_moves} dry body moves")
    xs = [p[0] for p in body_points]
    ys = [p[1] for p in body_points]
    return {"printer": printer, "body_moves": body_moves,
            "dry_body_moves": dry_body_moves,
            "measured_x_mm": round(max(xs) - min(xs), 3),
            "measured_y_mm": round(max(ys) - min(ys), 3),
            "body_bounds_mm": [round(min(xs), 3), round(min(ys), 3),
                               round(max(xs), 3), round(max(ys), 3)],
            "machine_bounds_mm": list(BOUNDS[printer]),
            "all_moves_inside_bounds": True}


def require_dimension(slug, measured, requested):
    if abs(measured["measured_x_mm"] - requested) > 0.05 or \
            abs(measured["measured_y_mm"] - requested) > 0.05:
        raise AssertionError(f"{slug}: requested dimension mismatch: {measured}")


def selftest():
    source = os.path.join(OUT, "compact-40.gcode")
    original = open(source).read()
    cases = []
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "bad.gcode")
        open(bad, "w").write(original.replace("; BODY_START", "; BODY_START\nG0 X999 Y999", 1))
        try:
            measure(bad)
            cases.append(False)
        except AssertionError as exc:
            cases.append("outside bounds" in str(exc))

        lines = original.splitlines()
        body = False
        for i, line in enumerate(lines):
            if "BODY_START" in line:
                body = True
            elif body and line.startswith("G1") and " X" in line and " E" in line:
                lines[i] = re.sub(r" E-?\d+(?:\.\d+)?", "", line)
                break
        open(bad, "w").write("\n".join(lines) + "\n")
        try:
            measure(bad)
            cases.append(False)
        except AssertionError as exc:
            cases.append("dry body moves" in str(exc))

        measured = measure(source)
        try:
            require_dimension("known-bad-size", measured, 41.0)
            cases.append(False)
        except AssertionError as exc:
            cases.append("dimension mismatch" in str(exc))

        digest = sha256(source)
        svg = open(os.path.join(OUT, "compact-40.svg")).read()
        cases.append(f'data-source-sha256="{digest[:-1]}0"' not in svg)
    failed = len(cases) - sum(cases)
    print(f"nucleon preview selftest: {len(cases)} cases, {sum(cases)} passed, {failed} failed")
    if failed:
        raise SystemExit(1)


def main():
    manifest_path = os.path.join(OUT, "manifest.json")
    manifest = json.load(open(manifest_path))
    report = []
    for variant in manifest["variants"]:
        gcode_path = os.path.join(OUT, variant["gcode"])
        svg_path = os.path.join(OUT, variant["render"])
        digest = sha256(gcode_path)
        svg = open(svg_path).read()
        if digest != variant["gcode_sha256"]:
            raise AssertionError(f"{variant['slug']}: manifest G-code digest mismatch")
        if f'data-source-sha256="{digest}"' not in svg:
            raise AssertionError(f"{variant['slug']}: render is not traced to G-code bytes")
        measured = measure(gcode_path)
        require_dimension(variant["slug"], measured, variant["requested_mm"])
        report.append({"slug": variant["slug"], "requested_mm": variant["requested_mm"],
                       "ellipses": variant["N"], "ratio": variant["ratio"],
                       "gcode_sha256": digest, **measured})
    report_path = os.path.join(OUT, "verification.json")
    open(report_path, "w").write(json.dumps({"parser": "nucleon-preview/verify.py",
                                              "variants": report},
                                             indent=2, sort_keys=True) + "\n")
    for row in report:
        print(f"{row['slug']}: {row['measured_x_mm']:.3f} x "
              f"{row['measured_y_mm']:.3f} mm, {row['body_moves']} extruding body moves, "
              f"0 dry, bounds PASS, sha256 {row['gcode_sha256'][:12]}")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
