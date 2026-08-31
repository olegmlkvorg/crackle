#!/usr/bin/env python3
"""FORCE R7'S COOL-PROBE SEAM TO FIRE IN ALL THREE DIRECTIONS. A guard is worth only what it has
been SEEN to reject.

The seam it guards (2026-08-31): Oleg's nozzle leaks at 210C, so a hot G28 re-zeroes Z through a
drool blob — files now home at a DECLARED 140C ('; PROBE_TEMP='), heat at the machine's chute,
and wipe before printing. R7 must accept exactly that shape and refuse both of its corruptions:
a stamp that disagrees with the commanded temp (the stamped-but-not-applied failure every
declared regime here checks for), and an undeclared cool probe — which is solid.py's recorded
zero-adhesion accident and stays refused.

Built from the live generator, like forced_layer1 and forced_calibrate_line: the failure this is
about is the emitted start block changing.
"""
import os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRACKLE = os.path.dirname(HERE)


def gen(tmp):
    d = os.path.join(tmp, 'probe')
    r = subprocess.run([sys.executable, 'hangertag.py', '--heights', '0.16,0.22,0.28', '--out', d],
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
    tmp = tempfile.mkdtemp(prefix='forced_probetemp_')
    clean = gen(tmp)
    txt = open(clean).read()
    if not re.search(r'^; PROBE_TEMP=140$', txt, re.M) or 'M104 S140\n' not in txt:
        raise SystemExit("FAIL: the generator no longer emits the declared 140C probe — this "
                         "test's subject is gone; re-point it before trusting the seam.")

    rc, out = validate(clean)
    if rc != 0:
        raise SystemExit(f"FAIL: the CLEAN declared-cool-probe file is refused — the seam does "
                         f"not admit the shape it exists for.\n{out[-1200:]}")
    if 'R7: probes at a DECLARED 140' not in out:
        raise SystemExit("FAIL: the clean file passes but R7 never says it judged the declared "
                         "probe — silence is not a verdict.")

    mism = txt.replace('; PROBE_TEMP=140', '; PROBE_TEMP=150', 1)
    if mism == txt:
        raise SystemExit("FAIL: mismatch injection did not land.")
    p = os.path.join(tmp, 'mismatch.gcode'); open(p, 'w').write(mism)
    rc, out = validate(p)
    if rc == 0 or 'declaration and the commands disagree' not in out:
        raise SystemExit(f"FAIL: a stamp claiming 150 over commands at 140 must be refused for "
                         f"exactly that reason.\n{out[-1200:]}")

    undecl = re.sub(r'^; PROBE_TEMP=140\n', '', txt, count=1, flags=re.M)
    if undecl == txt:
        raise SystemExit("FAIL: stamp-strip injection did not land.")
    p = os.path.join(tmp, 'undeclared.gcode'); open(p, 'w').write(undecl)
    rc, out = validate(p)
    if rc == 0 or 'declares no' not in out:
        raise SystemExit(f"FAIL: an UNDECLARED cool probe must still be refused — that is the "
                         f"zero-adhesion accident R7 was written for.\n{out[-1200:]}")

    print("PASS: declared cool probe accepted and judged; mismatched stamp and undeclared cool "
          "probe both refused, each for its stated reason.")


if __name__ == '__main__':
    main()
