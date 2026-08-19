#!/usr/bin/env python3
"""Build the three approved made-to-measure Nucleon preview artifacts."""
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")
sys.path.insert(0, ROOT)
import machine
import nucleon


SPECS = (
    dict(slug="compact-40", requested_mm=40.0, N=6, a=20.0, ratio=0.62),
    dict(slug="standard-50", requested_mm=50.0, N=8, a=25.0, ratio=0.55),
    dict(slug="statement-64", requested_mm=64.0, N=12, a=32.0, ratio=0.46),
)


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for spec in SPECS:
        origin = machine.BED["k2plus"][0] / 2.0 - spec["a"]
        old_argv = sys.argv
        sys.argv = ["nucleon-preview/build.py", "--variant", spec["slug"]]
        try:
            gcode, stats = nucleon.emit(
                spec["N"], spec["a"], spec["ratio"], origin, 12,
                machine.BEAD_H, machine.BEAD_W,
                machine.flow_for("pla", machine.FLOW, " for Nucleon preview"),
                1.0, 0.5, 12.0, machine.temp_for("pla"),
                int(machine.bed_for("pla", "k2plus")), 0, 1.75, True, 600,
                1, 1.0, 0.85, True, None, 0.0, 8.0,
                0, 0.0, 0.55, 0.9, "pla", "k2plus")
        finally:
            sys.argv = old_argv
        gcode_path = os.path.join(OUT, spec["slug"] + ".gcode")
        svg_path = os.path.join(OUT, spec["slug"] + ".svg")
        open(gcode_path, "w").write(gcode)
        subprocess.run(
            [sys.executable, os.path.join(ROOT, "render.py"), gcode_path, svg_path,
             "--body-only"], check=True)
        rows.append({**spec, "gcode": os.path.basename(gcode_path),
                     "render": os.path.basename(svg_path),
                     "gcode_sha256": sha256(gcode_path),
                     "render_sha256": sha256(svg_path),
                     "generator_stats": stats})
    open(os.path.join(OUT, "manifest.json"), "w").write(
        json.dumps({"stage": "preview; nothing has been printed", "variants": rows},
                   indent=2, sort_keys=True) + "\n")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "verify.py")],
                   check=True)


if __name__ == "__main__":
    main()
