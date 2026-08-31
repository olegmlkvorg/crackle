#!/usr/bin/env python3
"""FORCE THE BED_MESH_CALIBRATE COMMENT RULE TO FIRE. A guard is worth only what it has been
SEEN to reject.

The defect it guards: Creality's BED_MESH_CALIBRATE handler parses everything after the command
name as key=value args, so an inline '; comment' aborts the whole JOB — key514 "Malformed command
args ... not enough values to unpack (expected 2, got 1)", measured 2026-08-31 when the first
calibrate-mode hangertag plate died on the machine in second one after passing every gate. The
file gate now refuses the shape; this proves the refusal exists, fires for the right reason, and
does not fire on the clean form (comment on its own line — which is what machine.home emits now).

Built from the live generator, like forced_layer1: a stored fixture freezes the emitted start
block as it was, and the failure this is about is the emitted start block CHANGING.
"""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRACKLE = os.path.dirname(HERE)


def gen(tmp):
    d = os.path.join(tmp, 'cal')
    r = subprocess.run([sys.executable, 'hangertag.py', '--calibrate',
                        '--heights', '0.16,0.22,0.28', '--out', d],
                       cwd=CRACKLE, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"generator failed: {r.stderr[-800:]}")
    f = [x for x in os.listdir(d) if x.endswith('.gcode')]
    if len(f) != 1:
        raise SystemExit(f"expected one gcode, got {f}")
    return os.path.join(d, f[0])


def validate(path):
    r = subprocess.run([sys.executable, 'validate.py', path],
                       cwd=CRACKLE, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main():
    tmp = tempfile.mkdtemp(prefix='forced_calline_')
    clean = gen(tmp)
    txt = open(clean).read()
    if not re.search(r'^BED_MESH_CALIBRATE\s*$', txt, re.M):
        raise SystemExit("FAIL: the generator no longer emits a bare BED_MESH_CALIBRATE — this "
                         "test's subject is gone; re-point it before trusting the gate.")

    rc, out = validate(clean)
    if rc != 0:
        raise SystemExit(f"FAIL: the CLEAN calibrate file (comment on its own line) is refused — "
                         f"the guard cries wolf and will be switched off.\n{out[-1200:]}")

    # THE INJECTION, and proof it landed: the exact line that killed the 2026-08-31 job.
    doctored = txt.replace(
        "BED_MESH_CALIBRATE\n",
        "BED_MESH_CALIBRATE                   ; full probe, ~6 min measured end to end\n", 1)
    if doctored == txt:
        raise SystemExit("FAIL: the injection did not land — a mutant that fails to apply reads "
                         "exactly like a passing guard.")
    bad = os.path.join(tmp, 'doctored.gcode')
    open(bad, 'w').write(doctored)
    rc, out = validate(bad)
    if rc == 0:
        raise SystemExit("FAIL: validate PASSES the inline-comment BED_MESH_CALIBRATE — the exact "
                         "line that aborted the job on the machine (key514) sails through the gate.")
    if 'BED_MESH_CALIBRATE carries an inline comment' not in out:
        raise SystemExit(f"FAIL: the doctored file is refused, but not for this reason — 'the "
                         f"guard passed the failure' is a lesson already paid for here.\n{out[-1200:]}")
    print("PASS: bare calibrate accepted; the job-killing inline-comment form refused, "
          "for the stated reason.")


if __name__ == '__main__':
    main()
