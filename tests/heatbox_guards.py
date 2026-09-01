#!/usr/bin/env python3
"""Re-prove every heatbox.scad guard can still FAIL, and that the shipped config passes.

A guard nobody has watched go red is decoration (CLAUDE.md). The seven asserts in
heatbox.scad were each forced red by hand on 2026-09-01; this program is that session
turned into something that runs, so an edit to the model cannot silently retire one.

THE TRAP THIS PROGRAM EXISTS TO SURVIVE: with an echo-format export, OpenSCAD writes
the assertion failure INTO THE OUTPUT FILE and still exits 0. A test that judged the
exit code would report green on a model whose every guard had been deleted. So the
verdict here is read from the file's CONTENTS, never from the return code.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "heatbox" / "heatbox.scad"
TIMEOUT = 60

# (label, overrides that must trip it, distinctive text the message must carry).
# The two A2 asserts share a code, so each is matched on its own wording — a code
# alone could not tell which of the pair actually fired.
CASES = (
    ("A1 material limit",   {"chamber_target": "120"},  "A1 Hyper PC rated"),
    ("A2 liner required",   {"liner": "false"},         "A2 source 160 C without aluminum liner"),
    ("A2 source ceiling",   {"source_temp": "210"},     "A2 source 210 C exceeds 200 C"),
    ("A3 exhaust area",     {"cap_standoff": "0.3"},    "A3 exit area"),
    ("A4 plenum vs liner",  {"plenum_h": "20"},         "A4 plenum 20 cannot pass"),
    # tong_jaw=4 would ALSO drop the exhaust area below the inlet and trip A3 first,
    # which is the wrong-reason case this file is built to catch. 5 isolates A5.
    ("A5 tong room",        {"tong_jaw": "5"},          "A5 tong_jaw 5"),
    ("A6 jet tangency",     {"jets_per_row": "6"},      "A6 jet spacing"),
    ("A7 wall not whole lines", {"skin": "2.4"},        "A7 skin 2.4"),
    ("A7 rib under two lines",  {"rib_t": "1.2"},       "A7 rib 1.2"),
    ("A8 plate not whole layers", {"deck_t": "3"},      "A8 plates"),
    ("A9 slot too tight",       {"slot_fit": "0.2"},    "A9 slot clearance 0.2"),
    ("A9 slot ribs merge",      {"rib_run": "7"},       "A9 slot ribs pitch"),
    ("A9 groove too shallow",   {"slot_wall": "4"},     "A9 groove 4"),
    ("A10 jet clips slot rib",  {"jet_off": "4"},       "A10 jet inner edge"),
)


def evaluate(workdir, overrides):
    """Evaluate the model and return its echo-format output as text.

    Errors land in the output file rather than on stderr or in the exit code, so both
    streams are folded in: whichever channel OpenSCAD chooses, the caller sees it.
    """
    out = Path(workdir) / "eval.echo"
    cmd = ["openscad", "-o", str(out), "-D", 'part="body"']
    for key, value in overrides.items():
        cmd += ["-D", f"{key}={value}"]
    cmd.append(str(MODEL))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"HUNG: no verdict in {TIMEOUT}s"
    written = out.read_text() if out.is_file() else ""
    return written + proc.stdout + proc.stderr


def main():
    if shutil.which("openscad") is None:
        print("FAIL heatbox guards: openscad absent, so no guard was checked.")
        print("      Install it (brew install --cask openscad) — a skipped guard "
              "must not read as a passing one.")
        return 1
    if not MODEL.is_file():
        print(f"FAIL heatbox guards: model missing at {MODEL}")
        return 1

    failures = []
    with tempfile.TemporaryDirectory() as workdir:
        # The shipped configuration must evaluate clean FIRST. OpenSCAD stops at its
        # first failed assert, so a dirty baseline makes every guard below look absent
        # when it is merely unreachable. Reporting those seven would be seven wrong
        # diagnoses, so the run stops here instead and says what it did not check.
        baseline = evaluate(workdir, {})
        dirty = [line for line in baseline.splitlines()
                 if "ERROR" in line or "WARNING" in line]
        if dirty:
            print("FAIL shipped config does not evaluate clean:")
            for line in dirty[:4]:
                print("     " + line)
            print(f"     {len(CASES)} guard checks NOT RUN — an earlier assert hides "
                  "the later ones, so their result would be meaningless.")
            return 1
        if not re.search(r"ECHO:.*interior", baseline):
            failures.append("shipped config emitted no dimension echo; the probe "
                            "cannot tell a silent model from a working one")

        for label, overrides, wording in CASES:
            text = evaluate(workdir, overrides)
            if not re.search(r'Assertion.*?failed: "' + re.escape(wording), text):
                fired = re.findall(r'Assertion.*?failed: "(A\d[^"]{0,40})', text)
                detail = f"; something else fired: {fired}" if fired else ""
                failures.append(
                    f"{label}: {overrides} did NOT trip \"{wording}\". The guard is "
                    f"gone, renamed, or no longer reachable{detail}.")

    for line in failures:
        print("FAIL " + line)
    if failures:
        print(f"heatbox guards: {len(failures)} of {len(CASES) + 1} checks failed")
        return 1
    print(f"PASS heatbox guards: {len(CASES)} guards each fired for their own reason, "
          "shipped config clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
