#!/usr/bin/env python3
"""BRIDGE-TPU-1: prove the generator's refusals and its bridge-span check fire, and pass a good file.

Known-bads: R2's 0.82x0.42 bead without --over-limit is refused; a bridge whose stamped span
differs from the air its emitted move crosses fails --check. Control: both rows emit and pass
--check and validate.py.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "bridge_tpu.py")
VAL = os.path.join(ROOT, "validate.py")


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=300)


with tempfile.TemporaryDirectory() as d:
    r = run(GEN, "--row", "R2", "--out", d)
    assert r.returncode != 0 and "REFUSING TO EMIT" in (r.stdout + r.stderr), r
    assert not os.listdir(d), "a refused row left a file behind"

    files = {}
    for row, extra in (("R1", []), ("R2", ["--over-limit"])):
        r = run(GEN, "--row", row, "--out", d, *extra)
        assert r.returncode == 0, r.stderr
        files[row] = r.stdout.splitlines()[0].strip()
        txt = open(files[row]).read()
        for stamp in ("; WALL=postbridge", "; CMD=", "; BRIDGE span=", "BED_MESH_PROFILE LOAD="):
            assert stamp in txt, (row, stamp)
        assert "BED_MESH_CALIBRATE" not in txt, "K2 start must reuse the saved mesh, never probe"
        assert ("; BEAD_OVERRIDE=" in txt) == (row == "R2"), row
        c = run(GEN, "--check", files[row])
        assert c.returncode == 0, c.stdout
        v = run(VAL, files[row])
        assert v.returncode == 0, v.stdout[-2000:]

    # tamper one stamp: 7.00 -> 9.00 on the first 7 mm bridge
    bad = os.path.join(d, "tampered.gcode")
    src = open(files["R1"]).read()
    assert "BRIDGE span=7.00" in src
    open(bad, "w").write(src.replace("BRIDGE span=7.00", "BRIDGE span=9.00", 1))
    c = run(GEN, "--check", bad)
    assert c.returncode != 0 and "stamp 9.00 vs measured 7.00" in c.stdout, c.stdout

    # pull one bridge end 3 mm short of its post: the measured air changes, the stamp does not
    lines = src.splitlines()
    i = next(k for k, l in enumerate(lines) if "BRIDGE span=4.00" in l)
    head, tail = lines[i].split(" ; ", 1)
    parts = head.split()
    xi = next(k for k, p in enumerate(parts) if p.startswith("X"))
    parts[xi] = f"X{float(parts[xi][1:]) + 3.0:.3f}"
    lines[i] = " ".join(parts) + " ; " + tail
    open(bad, "w").write("\n".join(lines) + "\n")
    c = run(GEN, "--check", bad)
    assert c.returncode != 0 and "stamp 4.00" in c.stdout, c.stdout

print("bridge_tpu_selftest: refusal, two tampered spans, and both good rows all behave")
